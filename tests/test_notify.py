"""Tests for lib/notify.py — desktop notifications for stale/parked sessions."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from lib import store
from lib.notify import (
    _escape_applescript,
    _load_notify_state,
    _save_notify_state,
    _send_notification,
    _should_notify,
    check_and_notify,
    get_long_parked_sessions,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect store + notify state paths to temp directory."""
    monkeypatch.setattr(store, "DASHBOARD_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(store, "ARCHIVE_DIR", tmp_path / "sessions" / "archive")
    monkeypatch.setattr(store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    # Redirect notify state to tmp
    import lib.notify as notify_mod

    monkeypatch.setattr(notify_mod, "NOTIFY_STATE_PATH", tmp_path / "notify_state.json")
    store._ensure_dirs()


@pytest.fixture
def project_slug():
    store.register_project("Test", "/tmp/test")
    return "test"


# ---------------------------------------------------------------------------
# _send_notification
# ---------------------------------------------------------------------------


class TestSendNotification:
    def test_macos_sends_osascript(self):
        with (
            patch("lib.notify.platform.system", return_value="Darwin"),
            patch("lib.notify.subprocess.run") as mock_run,
        ):
            result = _send_notification("Title", "Message")
            assert result is True
            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0][0] == "osascript"

    def test_non_macos_logs_only(self):
        with patch("lib.notify.platform.system", return_value="Linux"):
            result = _send_notification("Title", "Message")
            assert result is False

    def test_timeout_returns_false(self):
        with (
            patch("lib.notify.platform.system", return_value="Darwin"),
            patch(
                "lib.notify.subprocess.run",
                side_effect=subprocess.TimeoutExpired("osascript", 5),
            ),
        ):
            result = _send_notification("Title", "Message")
            assert result is False


# ---------------------------------------------------------------------------
# AppleScript escaping
# ---------------------------------------------------------------------------


class TestEscapeApplescript:
    def test_escapes_quotes(self):
        assert _escape_applescript('say "hello"') == 'say \\"hello\\"'

    def test_escapes_backslashes(self):
        assert _escape_applescript("path\\to") == "path\\\\to"

    def test_plain_text_unchanged(self):
        assert _escape_applescript("hello world") == "hello world"


# ---------------------------------------------------------------------------
# Notify state persistence
# ---------------------------------------------------------------------------


class TestNotifyState:
    def test_load_empty_returns_dict(self):
        state = _load_notify_state()
        assert state == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        import lib.notify as notify_mod

        path = tmp_path / "notify_state.json"
        monkeypatch.setattr(notify_mod, "NOTIFY_STATE_PATH", path)

        data = {"sess_123": {"reason": "stale", "notified_at": "2026-01-01T00:00:00"}}
        _save_notify_state(data)

        loaded = _load_notify_state()
        assert loaded == data

    def test_corrupt_file_returns_empty(self, tmp_path, monkeypatch):
        import lib.notify as notify_mod

        path = tmp_path / "notify_state.json"
        monkeypatch.setattr(notify_mod, "NOTIFY_STATE_PATH", path)
        path.write_text("not json{{{")

        state = _load_notify_state()
        assert state == {}


# ---------------------------------------------------------------------------
# _should_notify (cooldown logic)
# ---------------------------------------------------------------------------


class TestShouldNotify:
    def test_first_time_always_notifies(self):
        assert _should_notify("sess_1", "stale", {}, cooldown_hours=12) is True

    def test_within_cooldown_skips(self):
        now = datetime.now(UTC).isoformat()
        state = {"sess_1": {"reason": "stale", "notified_at": now}}
        assert _should_notify("sess_1", "stale", state, cooldown_hours=12) is False

    def test_after_cooldown_notifies(self):
        old = (datetime.now(UTC) - timedelta(hours=13)).isoformat()
        state = {"sess_1": {"reason": "stale", "notified_at": old}}
        assert _should_notify("sess_1", "stale", state, cooldown_hours=12) is True

    def test_reason_changed_notifies(self):
        now = datetime.now(UTC).isoformat()
        state = {"sess_1": {"reason": "stale", "notified_at": now}}
        assert _should_notify("sess_1", "parked", state, cooldown_hours=12) is True


# ---------------------------------------------------------------------------
# get_long_parked_sessions
# ---------------------------------------------------------------------------


class TestGetLongParkedSessions:
    def test_old_parked_session_returned(self, project_slug):
        s = store.create_session(project_slug=project_slug, intent="Old parked")
        store.park_session(s.session_id, reason="Waiting")
        # Backdate ended_at to 72 hours ago
        old_time = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
        store.update_session(s.session_id, ended_at=old_time)

        result = get_long_parked_sessions(threshold_hours=48)
        assert len(result) == 1
        assert result[0].session_id == s.session_id

    def test_recent_parked_session_excluded(self, project_slug):
        s = store.create_session(project_slug=project_slug, intent="Recent parked")
        store.park_session(s.session_id, reason="Quick break")

        result = get_long_parked_sessions(threshold_hours=48)
        assert len(result) == 0

    def test_active_session_ignored(self, project_slug):
        store.create_session(project_slug=project_slug, intent="Active session")
        result = get_long_parked_sessions(threshold_hours=1)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# check_and_notify
# ---------------------------------------------------------------------------


class TestCheckAndNotify:
    def test_disabled_returns_status(self):
        result = check_and_notify()
        assert result["status"] == "disabled"
        assert result["stale_notified"] == 0
        assert result["parked_notified"] == 0

    def test_stale_session_notified(self, project_slug):
        # Enable notifications
        config = store.load_config()
        config.settings.notifications_enabled = True
        config.settings.stale_threshold_hours = 1
        store.save_config(config)

        # Create session and backdate heartbeat
        s = store.create_session(project_slug=project_slug, intent="Stale test")
        old_hb = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        store.update_session(s.session_id, last_heartbeat=old_hb)

        with patch("lib.notify._send_notification", return_value=True) as mock_send:
            result = check_and_notify()

        assert result["status"] == "checked"
        assert result["stale_notified"] == 1
        mock_send.assert_called_once()
        assert "Stale sessie" in mock_send.call_args[0][0]

    def test_parked_session_notified(self, project_slug):
        config = store.load_config()
        config.settings.notifications_enabled = True
        config.settings.parked_notify_hours = 1
        store.save_config(config)

        s = store.create_session(project_slug=project_slug, intent="Parked test")
        store.park_session(s.session_id, reason="Break")
        old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        store.update_session(s.session_id, ended_at=old_time)

        with patch("lib.notify._send_notification", return_value=True) as mock_send:
            result = check_and_notify()

        assert result["parked_notified"] == 1
        mock_send.assert_called_once()

    def test_dedup_within_cooldown(self, project_slug):
        config = store.load_config()
        config.settings.notifications_enabled = True
        config.settings.stale_threshold_hours = 1
        config.settings.notify_cooldown_hours = 12
        store.save_config(config)

        s = store.create_session(project_slug=project_slug, intent="Dedup test")
        old_hb = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        store.update_session(s.session_id, last_heartbeat=old_hb)

        with patch("lib.notify._send_notification", return_value=True):
            check_and_notify()

        # Second call within cooldown — should not notify again
        with patch("lib.notify._send_notification", return_value=True) as mock_send:
            result = check_and_notify()

        assert result["stale_notified"] == 0
        mock_send.assert_not_called()

    def test_cleanup_resolved_entries(self, project_slug):
        config = store.load_config()
        config.settings.notifications_enabled = True
        config.settings.stale_threshold_hours = 1
        store.save_config(config)

        s = store.create_session(project_slug=project_slug, intent="Cleanup test")
        old_hb = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        store.update_session(s.session_id, last_heartbeat=old_hb)

        with patch("lib.notify._send_notification", return_value=True):
            check_and_notify()

        # Now give it a fresh heartbeat so it's no longer stale
        store.heartbeat(s.session_id)

        with patch("lib.notify._send_notification", return_value=True):
            check_and_notify()

        # State entry should be cleaned up
        state = _load_notify_state()
        assert s.session_id not in state
