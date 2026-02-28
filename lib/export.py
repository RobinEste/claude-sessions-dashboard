"""Export session and project data as JSON or Markdown.

Formatting-only module — no file I/O, no external dependencies.
All functions accept model objects and return dicts or strings.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from .models import Session, TaskStatus


def _format_duration(started_at: str | None, ended_at: str | None) -> str:
    """Format duration between two ISO timestamps as '2u 15m'."""
    if not started_at or not ended_at:
        return ""
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except (ValueError, TypeError):
        return ""
    delta = end - start
    total_minutes = int(delta.total_seconds()) // 60
    if total_minutes < 0:
        return ""
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}u {minutes}m"
    if hours:
        return f"{hours}u"
    return f"{minutes}m"


def _format_iso_short(iso_str: str | None) -> str:
    """Format ISO timestamp as '2026-02-28 10:00'."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ""


def _task_summary(tasks: list[dict]) -> dict:
    """Build task status summary."""
    counts = {"completed": 0, "in_progress": 0, "pending": 0, "skipped": 0}
    for t in tasks:
        status = t.get("status", "")
        if status in counts:
            counts[status] += 1
    counts["total"] = len(tasks)
    return counts


# ---------------------------------------------------------------------------
# Session export
# ---------------------------------------------------------------------------


def export_session_json(session: Session) -> dict:
    """Export a single session as a rich JSON dict."""
    data = asdict(session)
    data["task_summary"] = _task_summary(session.tasks)
    data["duration"] = _format_duration(session.started_at, session.ended_at)
    return data


def export_session_markdown(
    session: Session, heading_level: int = 1,
) -> str:
    """Export a single session as a readable Markdown document.

    heading_level controls the top-level heading depth (1 = '#', 2 = '##').
    Sub-sections are one level deeper.
    """
    h = "#" * heading_level
    hsub = "#" * (heading_level + 1)
    lines: list[str] = []

    lines.append(f"{h} Session: {session.intent}")
    lines.append("")

    # Metadata table
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Session ID | `{session.session_id}` |")
    lines.append(f"| Project | {session.project_slug} |")
    lines.append(f"| Status | {session.status} |")
    lines.append(f"| Branch | `{session.git_branch}` |")
    if session.started_at:
        lines.append(f"| Started | {_format_iso_short(session.started_at)} |")
    if session.ended_at:
        lines.append(f"| Ended | {_format_iso_short(session.ended_at)} |")
    duration = _format_duration(session.started_at, session.ended_at)
    if duration:
        lines.append(f"| Duration | {duration} |")
    if session.roadmap_ref:
        lines.append(f"| Roadmap ref | {session.roadmap_ref} |")
    lines.append("")

    # Outcome / parked reason
    if session.outcome:
        lines.append(f"{hsub} Outcome")
        lines.append("")
        lines.append(session.outcome)
        lines.append("")

    if session.parked_reason:
        lines.append(f"{hsub} Parked reason")
        lines.append("")
        lines.append(session.parked_reason)
        lines.append("")

    # Tasks
    if session.tasks:
        summary = _task_summary(session.tasks)
        lines.append(f"{hsub} Tasks ({summary['completed']}/{summary['total']})")
        lines.append("")
        for task in session.tasks:
            status = task.get("status", "pending")
            check = "x" if status == TaskStatus.COMPLETED else " "
            subject = task.get("subject", "")
            if status == TaskStatus.SKIPPED:
                lines.append(f"- [x] ~~{subject}~~ (skipped)")
            elif status == TaskStatus.IN_PROGRESS:
                lines.append(f"- [ ] {subject} *(in progress)*")
            else:
                lines.append(f"- [{check}] {subject}")
        lines.append("")

    # Decisions
    if session.decisions:
        lines.append(f"{hsub} Decisions")
        lines.append("")
        for decision in session.decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # Commits
    if session.commits:
        lines.append(f"{hsub} Commits")
        lines.append("")
        for commit in session.commits:
            sha = commit.get("sha", "")[:7]
            msg = commit.get("message", "")
            lines.append(f"- `{sha}` {msg}")
        lines.append("")

    # Files changed
    if session.files_changed:
        lines.append(f"{hsub} Files changed")
        lines.append("")
        for f in session.files_changed:
            lines.append(f"- `{f}`")
        lines.append("")

    # Events
    if session.events:
        lines.append(f"{hsub} Events")
        lines.append("")
        for event in session.events:
            ts = _format_iso_short(event.get("timestamp"))
            msg = event.get("message", "")
            lines.append(f"- **{ts}** — {msg}")
        lines.append("")

    # Open questions
    if session.open_questions:
        lines.append(f"{hsub} Open questions")
        lines.append("")
        for q in session.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    # Next steps
    if session.next_steps:
        lines.append(f"{hsub} Next steps")
        lines.append("")
        for step in session.next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Project export
# ---------------------------------------------------------------------------


def export_project_json(name: str, sessions: list[Session]) -> dict:
    """Export all sessions for a project as a JSON dict with metadata."""
    return {
        "project": name,
        "exported_at": datetime.now(UTC).isoformat(),
        "session_count": len(sessions),
        "sessions": [export_session_json(s) for s in sessions],
    }


def export_project_markdown(name: str, sessions: list[Session]) -> str:
    """Export all sessions for a project as a single Markdown document."""
    lines: list[str] = []

    lines.append(f"# Project: {name}")
    lines.append("")
    lines.append(f"**Sessions:** {len(sessions)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, session in enumerate(sessions):
        lines.append(export_session_markdown(session, heading_level=2))
        if i < len(sessions) - 1:
            lines.append("---")
            lines.append("")

    return "\n".join(lines)
