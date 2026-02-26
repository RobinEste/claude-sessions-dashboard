"""Dashboard data store — CRUD operations on JSON files.

All writes are atomic (temp file + os.replace) to prevent corruption
when parallel sessions write simultaneously.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import (
    DashboardConfig,
    DashboardSettings,
    ProjectRegistration,
    ProjectState,
    RoadmapSummary,
    Session,
    SessionStatus,
    TaskStatus,
    generate_session_id,
)
from .validation import (
    MAX_ACTIVITY,
    MAX_DECISION,
    MAX_INTENT,
    MAX_MESSAGE,
    MAX_OUTCOME,
    MAX_PROJECT_NAME,
    MAX_REASON,
    MAX_ROADMAP_REF,
    MAX_TASK_SUBJECT,
    validate_commits_json,
    validate_git_branch,
    validate_optional_string,
    validate_positive_int,
    validate_project_slug,
    validate_sha,
    validate_string_length,
)

DASHBOARD_DIR = Path.home() / ".claude" / "dashboard"
SESSIONS_DIR = DASHBOARD_DIR / "sessions"
ARCHIVE_DIR = DASHBOARD_DIR / "sessions" / "archive"
PROJECTS_DIR = DASHBOARD_DIR / "projects"
CONFIG_PATH = DASHBOARD_DIR / "config.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _safe_read_json(path: Path) -> dict:
    """Read and parse a JSON file with size limit and symlink rejection.

    Uses O_NOFOLLOW to atomically reject symlinks (no TOCTOU race).

    Raises:
        ValueError: if file is a symlink or exceeds size limit.
        json.JSONDecodeError: if file contains invalid JSON.
    """
    import errno

    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.EMLINK):
            raise ValueError(f"Refusing to read symlink: {path.name}") from e
        raise
    size = os.fstat(fd).st_size
    if size > MAX_JSON_FILE_SIZE:
        os.close(fd)
        raise ValueError(
            f"File too large: {path.name} ({size} bytes, max {MAX_JSON_FILE_SIZE})"
        )
    with os.fdopen(fd) as f:
        return json.load(f)


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


logger = logging.getLogger(__name__)

_SESSION_ID_RE = re.compile(r"^sess_\d{8}T\d{4}_[0-9a-f]{4}$")

MAX_JSON_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _validate_session_id(session_id: str) -> None:
    """Reject session IDs that could escape the sessions directory."""
    if not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session ID format: {session_id}")


@contextmanager
def _session_lock(session_id: str):
    """Acquire an exclusive file lock for a session's read-modify-write cycle."""
    _validate_session_id(session_id)
    _ensure_dirs()
    lock_path = SESSIONS_DIR / f"{session_id}.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config() -> DashboardConfig:
    _ensure_dirs()
    if not CONFIG_PATH.exists():
        config = DashboardConfig()
        save_config(config)
        return config

    data = _safe_read_json(CONFIG_PATH)

    projects = {}
    for slug, proj_data in data.get("projects", {}).items():
        projects[slug] = ProjectRegistration(**proj_data)

    settings_data = data.get("settings", {})
    settings = DashboardSettings(**settings_data)

    return DashboardConfig(
        version=data.get("version", 1),
        projects=projects,
        settings=settings,
    )


def save_config(config: DashboardConfig) -> None:
    _ensure_dirs()
    data = {
        "version": config.version,
        "projects": {slug: asdict(proj) for slug, proj in config.projects.items()},
        "settings": asdict(config.settings),
    }
    _atomic_write(CONFIG_PATH, data)


# ---------------------------------------------------------------------------
# Project Registration
# ---------------------------------------------------------------------------


def register_project(name: str, path: str) -> str:
    """Register a project. Returns the slug. Idempotent."""
    name = validate_string_length(name, "project name", MAX_PROJECT_NAME)
    slug = _slugify(os.path.basename(path))
    validate_project_slug(slug)
    config = load_config()

    if slug not in config.projects:
        config.projects[slug] = ProjectRegistration(
            name=name,
            path=path,
            registered_at=_now_iso(),
        )
        save_config(config)

    return slug


def get_registered_projects() -> dict[str, ProjectRegistration]:
    return load_config().projects


# ---------------------------------------------------------------------------
# Sessions — CRUD
# ---------------------------------------------------------------------------


def create_session(
    project_slug: str,
    intent: str,
    roadmap_ref: str | None = None,
    git_branch: str = "main",
) -> Session:
    """Create a new active session."""
    validate_project_slug(project_slug)
    intent = validate_string_length(intent, "intent", MAX_INTENT)
    roadmap_ref = validate_optional_string(roadmap_ref, "roadmap_ref", MAX_ROADMAP_REF)
    git_branch = validate_git_branch(git_branch)
    session = Session(
        session_id=generate_session_id(),
        project_slug=project_slug,
        status=SessionStatus.ACTIVE,
        intent=intent,
        roadmap_ref=roadmap_ref,
        started_at=_now_iso(),
        last_heartbeat=_now_iso(),
        git_branch=git_branch,
    )
    _save_session(session)
    _refresh_project_state(project_slug)
    return session


def get_session(session_id: str) -> Session | None:
    _validate_session_id(session_id)
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        # Fall back to archive
        path = ARCHIVE_DIR / f"{session_id}.json"
        if not path.exists():
            return None

    data = _safe_read_json(path)

    data = _migrate_session_data(data)
    return _session_from_dict(data)


def _session_from_dict(data: dict) -> Session:
    return Session(
        session_id=data["session_id"],
        project_slug=data["project_slug"],
        status=SessionStatus(data["status"]),
        intent=data["intent"],
        roadmap_ref=data.get("roadmap_ref"),
        started_at=data.get("started_at", ""),
        last_heartbeat=data.get("last_heartbeat", ""),
        ended_at=data.get("ended_at"),
        outcome=data.get("outcome"),
        parked_reason=data.get("parked_reason"),
        current_activity=data.get("current_activity"),
        awaiting_action=data.get("awaiting_action"),
        events=data.get("events", []),
        git_branch=data.get("git_branch", "main"),
        files_changed=data.get("files_changed", []),
        commits=data.get("commits", []),
        decisions=data.get("decisions", []),
        open_questions=data.get("open_questions", []),
        next_steps=data.get("next_steps", []),
        tasks=data.get("tasks", []),
    )


SCHEMA_VERSION = 2


def _migrate_session_data(data: dict) -> dict:
    """Migrate session data from older schema versions to current."""
    version = data.get("schema_version", 1)
    if version < 2:
        # v1 → v2: add schema_version and tasks field
        data.setdefault("tasks", [])
        data["schema_version"] = SCHEMA_VERSION
    return data


def _save_session(session: Session) -> None:
    _ensure_dirs()
    path = SESSIONS_DIR / f"{session.session_id}.json"
    data = asdict(session)
    data["schema_version"] = SCHEMA_VERSION
    _atomic_write(path, data)
    _update_index(session)


# ---------------------------------------------------------------------------
# Session index — lightweight lookup without scanning all files
# ---------------------------------------------------------------------------


def _index_path() -> Path:
    return SESSIONS_DIR / "_index.json"


def _index_entry(session: Session) -> dict:
    """Build a lightweight index entry from a session."""
    return {
        "project_slug": session.project_slug,
        "status": session.status,
        "intent": session.intent,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "last_heartbeat": session.last_heartbeat,
    }


def _load_index() -> dict[str, dict]:
    """Load the session index. Returns empty dict if missing or corrupt."""
    path = _index_path()
    if not path.exists():
        return {}
    try:
        data = _safe_read_json(path)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, ValueError):
        logger.warning("Session index corrupt, will rebuild on next write")
        return {}


def _save_index(index: dict[str, dict]) -> None:
    """Atomically write the session index."""
    _atomic_write(_index_path(), index)


@contextmanager
def _index_lock():
    """Acquire an exclusive file lock for the session index."""
    _ensure_dirs()
    lock_path = _index_path().with_suffix(".lock")
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def _update_index(session: Session) -> None:
    """Add or update a session entry in the index."""
    with _index_lock():
        index = _load_index()
        index[session.session_id] = _index_entry(session)
        _save_index(index)


def _remove_from_index(session_id: str) -> None:
    """Remove a session from the index (e.g. after archiving)."""
    with _index_lock():
        index = _load_index()
        if session_id in index:
            del index[session_id]
            _save_index(index)


def rebuild_index() -> dict[str, dict]:
    """Rebuild the index by scanning all session files.

    Used as fallback when the index is missing or corrupt.
    Returns the rebuilt index.
    """
    _ensure_dirs()
    index: dict[str, dict] = {}
    for path in SESSIONS_DIR.glob("sess_*.json"):
        try:
            data = _safe_read_json(path)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Skipping corrupt file during index rebuild: %s: %s", path.name, exc)
            continue
        data = _migrate_session_data(data)
        session = _session_from_dict(data)
        index[session.session_id] = _index_entry(session)
    _save_index(index)
    return index


def heartbeat(session_id: str) -> Session | None:
    """Update last_heartbeat timestamp. Only for active sessions."""
    session = None
    with _session_lock(session_id):
        session = get_session(session_id)
        if session and session.status == SessionStatus.ACTIVE:
            session.last_heartbeat = _now_iso()
            _save_session(session)
    return session


def heartbeat_project(project_slug: str) -> list[Session]:
    """Update heartbeat for ALL active sessions of a project."""
    validate_project_slug(project_slug)
    updated = []
    for session in get_active_sessions(project_slug):
        result = heartbeat(session.session_id)
        if result:
            updated.append(result)
    return updated


_UPDATE_FIELD_LIMITS = {
    "intent": MAX_INTENT,
    "current_activity": MAX_ACTIVITY,
    "roadmap_ref": MAX_ROADMAP_REF,
    "outcome": MAX_OUTCOME,
    "parked_reason": MAX_REASON,
}


def update_session(session_id: str, **kwargs) -> Session | None:
    """Update arbitrary fields on a session."""
    for key, value in kwargs.items():
        if isinstance(value, str) and key in _UPDATE_FIELD_LIMITS:
            kwargs[key] = validate_string_length(value, key, _UPDATE_FIELD_LIMITS[key])
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)

        _save_session(session)
        return session


def add_event(session_id: str, message: str) -> Session | None:
    """Append an event to the session event log (append-only)."""
    message = validate_string_length(message, "event message", MAX_MESSAGE)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        session.events.append({"timestamp": _now_iso(), "message": message})
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session


def add_commit(session_id: str, sha: str, message: str) -> Session | None:
    """Append a commit to the session. Deduplicates on SHA[:7]."""
    validate_sha(sha)
    message = validate_string_length(message, "commit message", MAX_MESSAGE)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        short_sha = sha[:7]
        existing = {(c.get("sha", "")[:7]) for c in session.commits}
        if short_sha not in existing:
            session.commits.append({"sha": sha, "message": message})
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session


def add_decision(session_id: str, decision: str) -> Session | None:
    """Append a decision to the session. Deduplicates on text."""
    decision = validate_string_length(decision, "decision", MAX_DECISION)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        if decision not in session.decisions:
            session.decisions.append(decision)
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session


def request_action(session_id: str, reason: str) -> Session | None:
    """Mark a session as awaiting user action."""
    reason = validate_string_length(reason, "reason", MAX_REASON)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        session.awaiting_action = reason
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session


def clear_action(session_id: str) -> Session | None:
    """Clear the awaiting_action flag."""
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        session.awaiting_action = None
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session


VALID_TASK_STATUSES = set(TaskStatus)


def _generate_task_id() -> str:
    """Generate a collision-resistant task ID."""
    return f"t{secrets.token_hex(4)}"


def add_task(session_id: str, subject: str) -> Session | None:
    """Append a task to the session. Deduplicates on subject."""
    return add_tasks(session_id, [subject])


def add_tasks(session_id: str, subjects: list[str]) -> Session | None:
    """Batch-append tasks to the session. Deduplicates on subject."""
    subjects = [validate_string_length(s, "task subject", MAX_TASK_SUBJECT) for s in subjects]
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        existing_subjects = {t["subject"] for t in session.tasks if "subject" in t}
        now = _now_iso()
        added = False

        for subject in subjects:
            if subject in existing_subjects:
                continue
            session.tasks.append({
                "id": _generate_task_id(),
                "subject": subject,
                "status": TaskStatus.PENDING,
                "added_at": now,
                "updated_at": now,
            })
            existing_subjects.add(subject)
            added = True

        if added:
            session.last_heartbeat = now
            _save_session(session)
        return session


def update_task(
    session_id: str, task_id: str, status: str, subject: str | None = None
) -> Session | None:
    """Update a task's status (and optionally subject). Raises ValueError if task_id not found."""
    subject = validate_optional_string(subject, "task subject", MAX_TASK_SUBJECT)
    if status not in VALID_TASK_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(VALID_TASK_STATUSES)}"
        )

    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        for task in session.tasks:
            if task["id"] == task_id:
                if subject is not None:
                    existing = {
                        t["subject"] for t in session.tasks
                        if t["id"] != task_id and "subject" in t
                    }
                    if subject in existing:
                        msg = f"Task subject '{subject}' already exists in session {session_id}"
                        raise ValueError(msg)
                task["status"] = status
                task["updated_at"] = _now_iso()
                if subject is not None:
                    task["subject"] = subject
                session.last_heartbeat = _now_iso()
                _save_session(session)
                return session

        raise ValueError(f"Task {task_id} not found in session {session_id}")


def complete_session(
    session_id: str,
    outcome: str,
    next_steps: list[str] | None = None,
    commits: list[dict] | None = None,
    files_changed: list[str] | None = None,
    decisions: list[str] | None = None,
) -> Session | None:
    """Mark session as completed."""
    outcome = validate_string_length(outcome, "outcome", MAX_OUTCOME)
    if commits is not None:
        validate_commits_json(commits)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        session.status = SessionStatus.COMPLETED
        session.ended_at = _now_iso()
        session.outcome = outcome
        if next_steps is not None:
            session.next_steps = next_steps[:3]
        if commits is not None:
            session.commits = commits
        if files_changed is not None:
            session.files_changed = files_changed
        if decisions is not None:
            session.decisions = decisions

        _save_session(session)
    _refresh_project_state(session.project_slug)
    return session


def park_session(
    session_id: str,
    reason: str,
    next_steps: list[str] | None = None,
) -> Session | None:
    """Park a session with a reason."""
    reason = validate_string_length(reason, "reason", MAX_REASON)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        session.status = SessionStatus.PARKED
        session.ended_at = _now_iso()
        session.parked_reason = reason
        if next_steps is not None:
            session.next_steps = next_steps[:3]

        _save_session(session)
    _refresh_project_state(session.project_slug)
    return session


def resume_session(session_id: str, new_intent: str | None = None) -> Session:
    """Resume a parked session — creates a new active session
    with the old session's context, and marks the old one as completed."""
    # Pre-generate new session ID so we can write the definitive outcome immediately
    new_session_id = generate_session_id()

    with _session_lock(session_id):
        old = get_session(session_id)
        if not old:
            raise ValueError(f"Session {session_id} not found")

        # Capture context before releasing lock
        intent = new_intent or old.intent
        project_slug = old.project_slug
        roadmap_ref = old.roadmap_ref
        git_branch = old.git_branch
        open_questions = old.open_questions

        # Mark old session as completed (resumed into new)
        old.status = SessionStatus.COMPLETED
        old.ended_at = _now_iso()
        old.outcome = f"Resumed as {new_session_id}"
        _save_session(old)

    # Create new session with pre-generated ID (outside lock to avoid nesting)
    new_session = Session(
        session_id=new_session_id,
        project_slug=project_slug,
        status=SessionStatus.ACTIVE,
        intent=intent,
        roadmap_ref=roadmap_ref,
        started_at=_now_iso(),
        last_heartbeat=_now_iso(),
        git_branch=git_branch,
        open_questions=open_questions,
    )
    _save_session(new_session)

    _refresh_project_state(project_slug)
    return new_session


# ---------------------------------------------------------------------------
# Sessions — Queries
# ---------------------------------------------------------------------------


def _session_from_index(sid: str, entry: dict) -> Session:
    """Build a lightweight Session from an index entry (no file I/O)."""
    return Session(
        session_id=sid,
        project_slug=entry.get("project_slug", ""),
        status=entry.get("status", SessionStatus.ACTIVE),
        intent=entry.get("intent", ""),
        started_at=entry.get("started_at"),
        ended_at=entry.get("ended_at"),
        last_heartbeat=entry.get("last_heartbeat"),
    )


def list_sessions(
    project_slug: str | None = None,
    status: SessionStatus | None = None,
    include_archived: bool = False,
    full_load: bool = True,
) -> list[Session]:
    """List sessions, optionally filtered by project and/or status.

    Uses the session index for fast pre-filtering. Falls back to full
    file scan if the index is empty or missing.
    When full_load=False, returns lightweight Session objects from the
    index without reading individual session files (fast path).
    Archived sessions are excluded by default. Pass include_archived=True
    to include them.
    """
    _ensure_dirs()

    # Rebuild index if file doesn't exist; load if it does.
    # _load_index returns {} for both missing and corrupt files,
    # so we check existence first to avoid rebuilding on empty (valid) index.
    idx_path = _index_path()
    if not idx_path.exists():
        index = rebuild_index()
    else:
        index = _load_index()
        # If file exists but returned empty, it might be corrupt — check file
        if not index and idx_path.stat().st_size > 2:
            index = rebuild_index()

    sessions = []
    for sid, entry in index.items():
        if project_slug and entry.get("project_slug") != project_slug:
            continue
        if status and entry.get("status") != status:
            continue
        if full_load:
            session = get_session(sid)
            if session:
                sessions.append(session)
        else:
            sessions.append(_session_from_index(sid, entry))

    # Include archived sessions by scanning archive dir (not indexed)
    if include_archived:
        for path in ARCHIVE_DIR.glob("sess_*.json"):
            try:
                data = _safe_read_json(path)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Skipping corrupt/invalid file %s: %s", path.name, exc)
                continue
            data = _migrate_session_data(data)
            session = _session_from_dict(data)

            if project_slug and session.project_slug != project_slug:
                continue
            if status and session.status != status:
                continue

            sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions


def get_active_sessions(project_slug: str | None = None) -> list[Session]:
    return list_sessions(project_slug=project_slug, status=SessionStatus.ACTIVE)


def get_parked_sessions(project_slug: str | None = None) -> list[Session]:
    return list_sessions(project_slug=project_slug, status=SessionStatus.PARKED)


def get_stale_sessions(threshold_hours: int | None = None) -> list[Session]:
    """Find active sessions whose heartbeat is older than the threshold."""
    if threshold_hours is None:
        config = load_config()
        threshold_hours = config.settings.stale_threshold_hours

    now = datetime.now(UTC)
    stale = []
    for session in get_active_sessions():
        if session.last_heartbeat:
            hb = datetime.fromisoformat(session.last_heartbeat)
            age_hours = (now - hb).total_seconds() / 3600
            if age_hours > threshold_hours:
                stale.append(session)

    return stale


def cleanup_stale_sessions(threshold_hours: int | None = None) -> list[Session]:
    """Find and auto-close all stale sessions."""
    if threshold_hours is None:
        config = load_config()
        threshold_hours = config.settings.stale_threshold_hours

    stale = get_stale_sessions(threshold_hours)
    cleaned = []
    affected_projects: set[str] = set()
    for session in stale:
        try:
            with _session_lock(session.session_id):
                # Revalidate: re-read session to check it's still stale
                fresh = get_session(session.session_id)
                if not fresh or fresh.status != SessionStatus.ACTIVE:
                    continue
                hb = datetime.fromisoformat(fresh.last_heartbeat)
                current_now = datetime.now(UTC)
                if (current_now - hb).total_seconds() / 3600 <= threshold_hours:
                    continue

                ended = _now_iso()
                fresh.status = SessionStatus.COMPLETED
                fresh.ended_at = ended
                fresh.last_heartbeat = ended
                fresh.outcome = "Automatisch afgesloten (stale — geen heartbeat)"
                _save_session(fresh)
            affected_projects.add(fresh.project_slug)
            cleaned.append(fresh)
        except Exception as exc:
            logger.warning(
                "Failed to close stale session %s: %s", session.session_id, exc
            )
            continue
    for slug in affected_projects:
        _refresh_project_state(slug)

    cleanup_orphaned_locks()

    return cleaned


def cleanup_orphaned_locks() -> list[str]:
    """Remove .lock files that have no matching session JSON file."""
    _ensure_dirs()
    removed: list[str] = []
    for lock_file in SESSIONS_DIR.glob("*.lock"):
        session_file = lock_file.with_suffix(".json")
        if not session_file.exists():
            try:
                lock_file.unlink()
                removed.append(lock_file.name)
            except OSError as exc:
                logger.warning("Failed to remove orphaned lock %s: %s", lock_file, exc)
    return removed


# ---------------------------------------------------------------------------
# Archiving
# ---------------------------------------------------------------------------


def archive_session(session_id: str) -> bool:
    """Move a completed session to the archive directory.

    Returns True if archived, False if session not found or not completed.
    """
    _validate_session_id(session_id)
    _ensure_dirs()
    with _session_lock(session_id):
        src = SESSIONS_DIR / f"{session_id}.json"
        if not src.exists():
            return False

        data = _safe_read_json(src)

        if data.get("status") != SessionStatus.COMPLETED:
            return False

        dst = ARCHIVE_DIR / f"{session_id}.json"
        shutil.move(str(src), str(dst))
        _remove_from_index(session_id)

    # Clean up lock file after releasing lock (outside block to preserve inode invariant)
    lock = SESSIONS_DIR / f"{session_id}.lock"
    lock.unlink(missing_ok=True)

    return True


def archive_old_sessions(days: int | None = None) -> list[str]:
    """Archive completed sessions older than N days.

    Uses archive_after_days from config if days is not specified.
    Returns list of archived session IDs.
    """
    if days is None:
        config = load_config()
        days = config.settings.archive_after_days
    validate_positive_int(days, "days", max_val=3650)

    _ensure_dirs()
    cutoff = datetime.now(UTC) - timedelta(days=days)
    archived: list[str] = []
    affected_projects: set[str] = set()

    for path in SESSIONS_DIR.glob("sess_*.json"):
        try:
            data = _safe_read_json(path)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Skipping corrupt/invalid file %s: %s", path.name, exc)
            continue

        if data.get("status") != SessionStatus.COMPLETED:
            continue

        ended_at = data.get("ended_at")
        if not ended_at:
            continue

        try:
            ended = datetime.fromisoformat(ended_at)
        except ValueError:
            continue

        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=UTC)

        if ended < cutoff:
            sid = data.get("session_id")
            if not sid:
                logger.warning("Skipping file without session_id: %s", path)
                continue
            try:
                _validate_session_id(sid)
            except ValueError:
                logger.warning("Skipping session with invalid ID in file %s", path)
                continue
            # Move under lock with full re-validation (SOL-2026-004)
            with _session_lock(sid):
                if not path.exists():
                    continue
                fresh = _safe_read_json(path)
                if fresh.get("status") != SessionStatus.COMPLETED:
                    continue
                dst = ARCHIVE_DIR / f"{sid}.json"
                shutil.move(str(path), str(dst))
                _remove_from_index(sid)
            # Clean up lock file after releasing lock
            lock = SESSIONS_DIR / f"{sid}.lock"
            lock.unlink(missing_ok=True)
            archived.append(sid)
            affected_projects.add(data.get("project_slug", ""))

    for slug in affected_projects:
        if slug:
            _refresh_project_state(slug)

    return archived


def get_archived_session(session_id: str) -> Session | None:
    """Get a session from the archive."""
    _validate_session_id(session_id)
    path = ARCHIVE_DIR / f"{session_id}.json"
    if not path.exists():
        return None

    data = _safe_read_json(path)

    data = _migrate_session_data(data)
    return _session_from_dict(data)


# ---------------------------------------------------------------------------
# Project State
# ---------------------------------------------------------------------------


def get_project_state(project_slug: str) -> ProjectState | None:
    validate_project_slug(project_slug)
    path = PROJECTS_DIR / f"{project_slug}.json"
    if not path.exists():
        return None

    data = _safe_read_json(path)

    roadmap_data = data.get("roadmap_summary", {})
    roadmap = RoadmapSummary(
        completed=roadmap_data.get("completed", []),
        in_progress=roadmap_data.get("in_progress", []),
        next_up=roadmap_data.get("next_up", []),
    )

    return ProjectState(
        project_slug=data["project_slug"],
        current_phase=data.get("current_phase", ""),
        roadmap_summary=roadmap,
        active_sessions=data.get("active_sessions", 0),
        parked_sessions=data.get("parked_sessions", 0),
        total_sessions=data.get("total_sessions", 0),
        last_activity=data.get("last_activity", ""),
        recent_commits=data.get("recent_commits", []),
        open_questions=data.get("open_questions", []),
        updated_at=data.get("updated_at", ""),
    )


def update_project_state(
    project_slug: str,
    current_phase: str | None = None,
    roadmap_completed: list[str] | None = None,
    roadmap_in_progress: list[str] | None = None,
    roadmap_next_up: list[str] | None = None,
) -> ProjectState:
    """Update project state with roadmap info."""
    validate_project_slug(project_slug)
    state = get_project_state(project_slug) or ProjectState(
        project_slug=project_slug
    )

    if current_phase is not None:
        state.current_phase = current_phase
    if roadmap_completed is not None:
        state.roadmap_summary.completed = roadmap_completed
    if roadmap_in_progress is not None:
        state.roadmap_summary.in_progress = roadmap_in_progress
    if roadmap_next_up is not None:
        state.roadmap_summary.next_up = roadmap_next_up[:3]

    state.updated_at = _now_iso()
    _save_project_state(state)
    return state


def _refresh_project_state(project_slug: str) -> ProjectState:
    """Rebuild project state from sessions (called after session changes)."""
    sessions = list_sessions(project_slug=project_slug)
    active = [s for s in sessions if s.status == SessionStatus.ACTIVE]
    parked = [s for s in sessions if s.status == SessionStatus.PARKED]

    # Collect recent commits from recent sessions
    recent_commits: list[dict] = []
    for s in sessions[:10]:
        recent_commits.extend(s.commits)
    recent_commits = recent_commits[:10]

    # Collect open questions from active + parked sessions
    open_questions: list[str] = []
    for s in active + parked:
        open_questions.extend(s.open_questions)
    # Deduplicate, preserve order
    open_questions = list(dict.fromkeys(open_questions))

    # Last activity = most recent heartbeat or start time
    last_activity = ""
    if sessions:
        last_activity = sessions[0].last_heartbeat or sessions[0].started_at

    # Next steps from most recent completed/parked session
    next_up: list[str] = []
    for s in sessions:
        if s.next_steps and s.status in (
            SessionStatus.COMPLETED,
            SessionStatus.PARKED,
        ):
            next_up = s.next_steps[:3]
            break

    # Preserve existing roadmap info (set by session-start skills)
    existing = get_project_state(project_slug)
    roadmap = existing.roadmap_summary if existing else RoadmapSummary()
    current_phase = existing.current_phase if existing else ""
    roadmap.next_up = next_up or roadmap.next_up

    state = ProjectState(
        project_slug=project_slug,
        current_phase=current_phase,
        roadmap_summary=roadmap,
        active_sessions=len(active),
        parked_sessions=len(parked),
        total_sessions=len(sessions),
        last_activity=last_activity,
        recent_commits=recent_commits,
        open_questions=open_questions,
        updated_at=_now_iso(),
    )

    _save_project_state(state)
    return state


def _save_project_state(state: ProjectState) -> None:
    _ensure_dirs()
    path = PROJECTS_DIR / f"{state.project_slug}.json"
    _atomic_write(path, asdict(state))


def get_all_project_states() -> list[ProjectState]:
    """Get states for all registered projects."""
    config = load_config()
    states = []
    for slug in config.projects:
        state = get_project_state(slug)
        if state:
            states.append(state)
        else:
            states.append(ProjectState(project_slug=slug, updated_at=_now_iso()))
    return states


def _task_summary(tasks: list[dict]) -> dict:
    """Build task status summary for API output."""
    return {
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t.get("status") == "completed"),
        "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
        "skipped": sum(1 for t in tasks if t.get("status") == "skipped"),
    }


def _session_to_overview_dict(session: Session, **extra) -> dict:
    """Convert a session to a dict for the overview API. Extra fields override defaults."""
    d = {
        "session_id": session.session_id,
        "intent": session.intent,
        "started_at": session.started_at,
        "roadmap_ref": session.roadmap_ref,
        "events": session.events[-5:],
        "git_branch": session.git_branch,
        "files_changed": session.files_changed,
        "decisions": session.decisions,
        "open_questions": session.open_questions,
        "commits": session.commits,
        "next_steps": session.next_steps,
        "event_count": len(session.events),
        "tasks": session.tasks,
        "task_summary": _task_summary(session.tasks),
    }
    d.update(extra)
    return d


def build_overview() -> dict:
    """Build complete dashboard overview — single source of truth for CLI and web."""
    config = load_config()
    stale_ids = {s.session_id for s in get_stale_sessions()}
    projects = []

    for slug, reg in config.projects.items():
        state = get_project_state(slug)
        active = get_active_sessions(slug)
        parked = get_parked_sessions(slug)
        completed = list_sessions(project_slug=slug, status=SessionStatus.COMPLETED)[:5]

        projects.append(
            {
                "slug": slug,
                "name": reg.name,
                "path": reg.path,
                "current_phase": state.current_phase if state else "",
                "active_sessions": [
                    _session_to_overview_dict(
                        s,
                        last_heartbeat=s.last_heartbeat,
                        is_stale=s.session_id in stale_ids,
                        current_activity=s.current_activity,
                        awaiting_action=s.awaiting_action,
                    )
                    for s in active
                ],
                "parked_sessions": [
                    _session_to_overview_dict(
                        s,
                        parked_reason=s.parked_reason,
                        current_activity=s.current_activity,
                        awaiting_action=s.awaiting_action,
                        ended_at=s.ended_at,
                    )
                    for s in parked
                ],
                "completed_sessions": [
                    _session_to_overview_dict(
                        s,
                        outcome=s.outcome,
                        ended_at=s.ended_at,
                        last_heartbeat=s.last_heartbeat,
                    )
                    for s in completed
                ],
                "roadmap_summary": {
                    "completed_count": len(state.roadmap_summary.completed) if state else 0,
                    "in_progress_count": len(state.roadmap_summary.in_progress) if state else 0,
                    "in_progress": state.roadmap_summary.in_progress if state else [],
                },
                "active_count": len(active),
                "parked_count": len(parked),
                "next_steps": (
                    state.roadmap_summary.next_up if state else []
                ),
                "last_activity": state.last_activity if state else "",
                "total_sessions": state.total_sessions if state else 0,
            }
        )

    return {
        "timestamp": _now_iso(),
        "projects": projects,
        "settings": asdict(config.settings),
    }
