"""Dashboard data models — pure stdlib, no external dependencies."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PARKED = "parked"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class ProjectRegistration:
    """Entry in config.json — registers a project with the dashboard."""

    name: str
    path: str
    registered_at: str  # ISO 8601


@dataclass
class Session:
    """One work session — stored as a JSON file in sessions/."""

    session_id: str
    project_slug: str
    status: SessionStatus
    intent: str
    roadmap_ref: str | None = None
    started_at: str = ""
    last_heartbeat: str = ""
    ended_at: str | None = None
    outcome: str | None = None
    parked_reason: str | None = None
    current_activity: str | None = None
    awaiting_action: str | None = None  # Reason user action is needed
    events: list[dict] = field(default_factory=list)
    git_branch: str = "main"
    files_changed: list[str] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)


@dataclass
class RoadmapSummary:
    """Derived roadmap status per project."""

    completed: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    next_up: list[str] = field(default_factory=list)  # max 3


@dataclass
class ProjectState:
    """Project-level state cache — derived from sessions + roadmap."""

    project_slug: str
    current_phase: str = ""
    roadmap_summary: RoadmapSummary = field(default_factory=RoadmapSummary)
    active_sessions: int = 0
    parked_sessions: int = 0
    total_sessions: int = 0
    last_activity: str = ""
    recent_commits: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class DashboardSettings:
    dashboard_port: int = 9000
    stale_threshold_hours: int = 24
    archive_after_days: int = 30
    notifications_enabled: bool = False
    parked_notify_hours: int = 48
    notify_cooldown_hours: int = 12


@dataclass
class DashboardConfig:
    version: int = 1
    projects: dict[str, ProjectRegistration] = field(default_factory=dict)
    settings: DashboardSettings = field(default_factory=DashboardSettings)


def generate_session_id() -> str:
    """Generate readable + unique session ID: sess_20260210T1430_a1b2."""
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M")
    suffix = secrets.token_hex(2)
    return f"sess_{timestamp}_{suffix}"
