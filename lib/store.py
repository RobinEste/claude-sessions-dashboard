"""Dashboard data store — CRUD operations on JSON files.

All writes are atomic (temp file + os.replace) to prevent corruption
when parallel sessions write simultaneously.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import secrets
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    DashboardConfig,
    DashboardSettings,
    ProjectRegistration,
    ProjectState,
    RoadmapSummary,
    Session,
    SessionStatus,
    generate_session_id,
)

DASHBOARD_DIR = Path.home() / ".claude" / "dashboard"
SESSIONS_DIR = DASHBOARD_DIR / "sessions"
PROJECTS_DIR = DASHBOARD_DIR / "projects"
CONFIG_PATH = DASHBOARD_DIR / "config.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


logger = logging.getLogger(__name__)


@contextmanager
def _session_lock(session_id: str):
    """Acquire an exclusive file lock for a session's read-modify-write cycle."""
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

    with open(CONFIG_PATH) as f:
        data = json.load(f)

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
    slug = _slugify(os.path.basename(path))
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
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

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


def _save_session(session: Session) -> None:
    _ensure_dirs()
    path = SESSIONS_DIR / f"{session.session_id}.json"
    _atomic_write(path, asdict(session))


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
    updated = []
    for session in get_active_sessions(project_slug):
        result = heartbeat(session.session_id)
        if result:
            updated.append(result)
    return updated


def update_session(session_id: str, **kwargs) -> Session | None:
    """Update arbitrary fields on a session."""
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


VALID_TASK_STATUSES = {"pending", "in_progress", "completed", "skipped"}


def _generate_task_id() -> str:
    """Generate a collision-resistant task ID."""
    return f"t{secrets.token_hex(4)}"


def add_task(session_id: str, subject: str) -> Session | None:
    """Append a task to the session. Deduplicates on subject."""
    return add_tasks(session_id, [subject])


def add_tasks(session_id: str, subjects: list[str]) -> Session | None:
    """Batch-append tasks to the session. Deduplicates on subject."""
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None

        existing_subjects = {t["subject"] for t in session.tasks}
        now = _now_iso()
        added = False

        for subject in subjects:
            if subject in existing_subjects:
                continue
            session.tasks.append({
                "id": _generate_task_id(),
                "subject": subject,
                "status": "pending",
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
                task["status"] = status
                task["updated_at"] = _now_iso()
                if subject is not None:
                    existing = {t["subject"] for t in session.tasks if t["id"] != task_id}
                    if subject in existing:
                        raise ValueError(f"Task subject '{subject}' already exists in session {session_id}")
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
    with _session_lock(session_id):
        old = get_session(session_id)
        if not old:
            raise ValueError(f"Session {session_id} not found")

        intent = new_intent or old.intent
        new_session = create_session(
            project_slug=old.project_slug,
            intent=intent,
            roadmap_ref=old.roadmap_ref,
            git_branch=old.git_branch,
        )
        new_session.open_questions = old.open_questions
        _save_session(new_session)

        # Mark old session as completed (resumed into new)
        old.status = SessionStatus.COMPLETED
        old.outcome = f"Resumed as {new_session.session_id}"
        old.ended_at = _now_iso()
        _save_session(old)

    _refresh_project_state(old.project_slug)
    return new_session


# ---------------------------------------------------------------------------
# Sessions — Queries
# ---------------------------------------------------------------------------


def list_sessions(
    project_slug: str | None = None,
    status: SessionStatus | None = None,
) -> list[Session]:
    """List sessions, optionally filtered by project and/or status."""
    _ensure_dirs()
    sessions = []
    for path in SESSIONS_DIR.glob("sess_*.json"):
        with open(path) as f:
            data = json.load(f)
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

    now = datetime.now(timezone.utc)
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
                current_now = datetime.now(timezone.utc)
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
    return cleaned


# ---------------------------------------------------------------------------
# Project State
# ---------------------------------------------------------------------------


def get_project_state(project_slug: str) -> ProjectState | None:
    path = PROJECTS_DIR / f"{project_slug}.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

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
                    {
                        "session_id": s.session_id,
                        "intent": s.intent,
                        "started_at": s.started_at,
                        "last_heartbeat": s.last_heartbeat,
                        "is_stale": s.session_id in stale_ids,
                        "current_activity": s.current_activity,
                        "awaiting_action": s.awaiting_action,
                        "roadmap_ref": s.roadmap_ref,
                        "events": s.events[-5:],
                        "git_branch": s.git_branch,
                        "files_changed": s.files_changed,
                        "decisions": s.decisions,
                        "open_questions": s.open_questions,
                        "commits": s.commits,
                        "next_steps": s.next_steps,
                        "event_count": len(s.events),
                        "tasks": s.tasks,
                        "task_summary": _task_summary(s.tasks),
                    }
                    for s in active
                ],
                "parked_sessions": [
                    {
                        "session_id": s.session_id,
                        "intent": s.intent,
                        "parked_reason": s.parked_reason,
                        "current_activity": s.current_activity,
                        "awaiting_action": s.awaiting_action,
                        "roadmap_ref": s.roadmap_ref,
                        "events": s.events[-5:],
                        "git_branch": s.git_branch,
                        "files_changed": s.files_changed,
                        "decisions": s.decisions,
                        "open_questions": s.open_questions,
                        "commits": s.commits,
                        "next_steps": s.next_steps,
                        "event_count": len(s.events),
                        "started_at": s.started_at,
                        "ended_at": s.ended_at,
                        "tasks": s.tasks,
                        "task_summary": _task_summary(s.tasks),
                    }
                    for s in parked
                ],
                "completed_sessions": [
                    {
                        "session_id": s.session_id,
                        "intent": s.intent,
                        "outcome": s.outcome,
                        "started_at": s.started_at,
                        "ended_at": s.ended_at,
                        "last_heartbeat": s.last_heartbeat,
                        "roadmap_ref": s.roadmap_ref,
                        "events": s.events[-5:],
                        "files_changed": s.files_changed,
                        "decisions": s.decisions,
                        "open_questions": s.open_questions,
                        "commits": s.commits,
                        "next_steps": s.next_steps,
                        "event_count": len(s.events),
                        "tasks": s.tasks,
                        "task_summary": _task_summary(s.tasks),
                    }
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
