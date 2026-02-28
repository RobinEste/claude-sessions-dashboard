"""Desktop notifications for stale and long-parked sessions.

Uses macOS osascript for native notifications; falls back to logging
on other platforms. All dependencies are stdlib-only.
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
from datetime import UTC, datetime

from .store import (
    DASHBOARD_DIR,
    _atomic_write,
    _safe_read_json,
    get_parked_sessions,
    get_stale_sessions,
    load_config,
)

logger = logging.getLogger(__name__)

NOTIFY_STATE_PATH = DASHBOARD_DIR / "notify_state.json"


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------


def _escape_applescript(s: str) -> str:
    """Escape a string for use inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _send_notification(title: str, message: str) -> bool:
    """Send a desktop notification. Returns True if delivered."""
    if platform.system() == "Darwin":
        escaped_title = _escape_applescript(title)
        escaped_message = _escape_applescript(message)
        script = (
            f'display notification "{escaped_message}" '
            f'with title "{escaped_title}"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning("osascript timed out sending notification")
            return False
        except FileNotFoundError:
            logger.warning("osascript not found")
            return False
    else:
        logger.info("Notification: [%s] %s", title, message)
        return False


# ---------------------------------------------------------------------------
# Notification state — tracks what we already notified about
# ---------------------------------------------------------------------------


def _load_notify_state() -> dict:
    """Load notify_state.json. Returns empty dict if missing or corrupt."""
    if not NOTIFY_STATE_PATH.exists():
        return {}
    try:
        data = _safe_read_json(NOTIFY_STATE_PATH)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt notify_state.json, starting fresh")
        return {}


def _save_notify_state(state: dict) -> None:
    """Atomically save notify state."""
    NOTIFY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(NOTIFY_STATE_PATH, state)


def _should_notify(
    session_id: str,
    reason: str,
    state: dict,
    cooldown_hours: int,
) -> bool:
    """Check if we should send a notification (respects cooldown)."""
    entry = state.get(session_id)
    if entry is None:
        return True

    # Different reason → notify again
    if entry.get("reason") != reason:
        return True

    # Check cooldown
    notified_at = entry.get("notified_at")
    if not notified_at:
        return True

    try:
        last = datetime.fromisoformat(notified_at)
    except ValueError:
        return True

    elapsed = (datetime.now(UTC) - last).total_seconds() / 3600
    return elapsed >= cooldown_hours


# ---------------------------------------------------------------------------
# Long-parked session detection
# ---------------------------------------------------------------------------


def get_long_parked_sessions(threshold_hours: int | None = None) -> list:
    """Return parked sessions older than threshold_hours.

    Uses ended_at (set by park_session) as the parked-since timestamp.
    """
    if threshold_hours is None:
        config = load_config()
        threshold_hours = config.settings.parked_notify_hours

    now = datetime.now(UTC)
    result = []
    for session in get_parked_sessions():
        if not session.ended_at:
            continue
        try:
            parked_at = datetime.fromisoformat(session.ended_at)
        except ValueError:
            continue
        age_hours = (now - parked_at).total_seconds() / 3600
        if age_hours > threshold_hours:
            result.append(session)

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_and_notify() -> dict:
    """Check for stale and long-parked sessions, send notifications.

    Returns a summary dict with status and counts.
    """
    config = load_config()
    settings = config.settings

    if not settings.notifications_enabled:
        return {
            "status": "disabled",
            "stale_notified": 0,
            "parked_notified": 0,
        }

    state = _load_notify_state()
    cooldown = settings.notify_cooldown_hours
    stale_notified = 0
    parked_notified = 0

    # Check stale sessions
    stale_sessions = get_stale_sessions()
    stale_ids = set()
    for session in stale_sessions:
        stale_ids.add(session.session_id)
        if _should_notify(session.session_id, "stale", state, cooldown):
            sent = _send_notification(
                "Stale sessie",
                f"{session.project_slug}: \"{session.intent}\" — geen heartbeat",
            )
            if sent:
                stale_notified += 1
                state[session.session_id] = {
                    "reason": "stale",
                    "notified_at": datetime.now(UTC).isoformat(),
                }

    # Check long-parked sessions
    parked_sessions = get_long_parked_sessions()
    parked_ids = set()
    for session in parked_sessions:
        parked_ids.add(session.session_id)
        if _should_notify(session.session_id, "parked", state, cooldown):
            sent = _send_notification(
                "Geparkeerde sessie wacht",
                f"{session.project_slug}: \"{session.intent}\"",
            )
            if sent:
                parked_notified += 1
                state[session.session_id] = {
                    "reason": "parked",
                    "notified_at": datetime.now(UTC).isoformat(),
                }

    # Cleanup: remove entries for sessions no longer stale/parked
    active_ids = stale_ids | parked_ids
    stale_keys = [k for k in state if k not in active_ids]
    for key in stale_keys:
        del state[key]

    _save_notify_state(state)

    return {
        "status": "checked",
        "stale_notified": stale_notified,
        "parked_notified": parked_notified,
    }
