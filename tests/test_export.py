"""Tests for lib/export.py — JSON and Markdown export formatting.

Tests verify output structure, section rendering, and edge cases
without any file I/O. All inputs are constructed in-memory.
"""

from __future__ import annotations

from lib.export import (
    _format_duration,
    _format_iso_short,
    export_project_json,
    export_project_markdown,
    export_session_json,
    export_session_markdown,
)
from lib.models import Session, SessionStatus, TaskStatus

# ---------------------------------------------------------------------------
# Helpers for building test sessions
# ---------------------------------------------------------------------------


def _make_session(**overrides) -> Session:
    defaults = {
        "session_id": "sess_20260228T1000_abcd",
        "project_slug": "test-project",
        "status": SessionStatus.COMPLETED,
        "intent": "Build export feature",
        "started_at": "2026-02-28T10:00:00+00:00",
        "last_heartbeat": "2026-02-28T12:15:00+00:00",
        "ended_at": "2026-02-28T12:15:00+00:00",
        "git_branch": "main",
    }
    defaults.update(overrides)
    return Session(**defaults)


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_hours_and_minutes(self):
        assert _format_duration(
            "2026-02-28T10:00:00+00:00",
            "2026-02-28T12:15:00+00:00",
        ) == "2u 15m"

    def test_only_hours(self):
        assert _format_duration(
            "2026-02-28T10:00:00+00:00",
            "2026-02-28T13:00:00+00:00",
        ) == "3u"

    def test_only_minutes(self):
        assert _format_duration(
            "2026-02-28T10:00:00+00:00",
            "2026-02-28T10:45:00+00:00",
        ) == "45m"

    def test_zero_minutes(self):
        assert _format_duration(
            "2026-02-28T10:00:00+00:00",
            "2026-02-28T10:00:00+00:00",
        ) == "0m"

    def test_missing_start(self):
        assert _format_duration(None, "2026-02-28T10:00:00+00:00") == ""

    def test_missing_end(self):
        assert _format_duration("2026-02-28T10:00:00+00:00", None) == ""

    def test_invalid_iso(self):
        assert _format_duration("not-a-date", "also-not") == ""


# ---------------------------------------------------------------------------
# _format_iso_short
# ---------------------------------------------------------------------------


class TestFormatIsoShort:
    def test_formats_correctly(self):
        result = _format_iso_short("2026-02-28T10:00:00+00:00")
        assert result == "2026-02-28 10:00"

    def test_none_returns_empty(self):
        assert _format_iso_short(None) == ""

    def test_empty_string_returns_empty(self):
        assert _format_iso_short("") == ""

    def test_invalid_returns_empty(self):
        assert _format_iso_short("bad") == ""


# ---------------------------------------------------------------------------
# export_session_json
# ---------------------------------------------------------------------------


class TestExportSessionJson:
    def test_basic_structure(self):
        session = _make_session()
        data = export_session_json(session)
        assert data["session_id"] == "sess_20260228T1000_abcd"
        assert data["intent"] == "Build export feature"
        assert data["status"] == "completed"

    def test_includes_task_summary(self):
        session = _make_session(tasks=[
            {"id": "t1", "subject": "Task A", "status": TaskStatus.COMPLETED},
            {"id": "t2", "subject": "Task B", "status": TaskStatus.PENDING},
        ])
        data = export_session_json(session)
        assert data["task_summary"]["total"] == 2
        assert data["task_summary"]["completed"] == 1
        assert data["task_summary"]["pending"] == 1

    def test_includes_duration(self):
        session = _make_session()
        data = export_session_json(session)
        assert data["duration"] == "2u 15m"

    def test_no_duration_when_active(self):
        session = _make_session(status=SessionStatus.ACTIVE, ended_at=None)
        data = export_session_json(session)
        assert data["duration"] == ""


# ---------------------------------------------------------------------------
# export_session_markdown
# ---------------------------------------------------------------------------


class TestExportSessionMarkdown:
    def test_heading_contains_intent(self):
        md = export_session_markdown(_make_session())
        assert md.startswith("# Session: Build export feature")

    def test_metadata_table(self):
        md = export_session_markdown(_make_session())
        assert "| Session ID |" in md
        assert "| Status | completed |" in md
        assert "| Duration | 2u 15m |" in md

    def test_outcome_section(self):
        md = export_session_markdown(_make_session(outcome="All tests pass"))
        assert "## Outcome" in md
        assert "All tests pass" in md

    def test_parked_reason_section(self):
        md = export_session_markdown(_make_session(
            status=SessionStatus.PARKED,
            parked_reason="Waiting for review",
        ))
        assert "## Parked reason" in md
        assert "Waiting for review" in md

    def test_tasks_as_checkboxes(self):
        session = _make_session(tasks=[
            {"id": "t1", "subject": "Write tests", "status": TaskStatus.COMPLETED},
            {"id": "t2", "subject": "Write docs", "status": TaskStatus.PENDING},
            {"id": "t3", "subject": "Refactor", "status": TaskStatus.IN_PROGRESS},
            {"id": "t4", "subject": "Old task", "status": TaskStatus.SKIPPED},
        ])
        md = export_session_markdown(session)
        assert "## Tasks (1/4)" in md
        assert "- [x] Write tests" in md
        assert "- [ ] Write docs" in md
        assert "*(in progress)*" in md
        assert "~~Old task~~" in md
        assert "(skipped)" in md

    def test_decisions_section(self):
        md = export_session_markdown(_make_session(decisions=["Use JSON", "No ORM"]))
        assert "## Decisions" in md
        assert "- Use JSON" in md

    def test_commits_section(self):
        session = _make_session(commits=[
            {"sha": "abc1234567890", "message": "feat: add export"},
        ])
        md = export_session_markdown(session)
        assert "## Commits" in md
        assert "`abc1234`" in md
        assert "feat: add export" in md

    def test_events_section(self):
        session = _make_session(events=[
            {"timestamp": "2026-02-28T10:30:00+00:00", "message": "Started coding"},
        ])
        md = export_session_markdown(session)
        assert "## Events" in md
        assert "Started coding" in md

    def test_next_steps_section(self):
        md = export_session_markdown(_make_session(next_steps=["Deploy", "Monitor"]))
        assert "## Next steps" in md
        assert "- Deploy" in md

    def test_empty_sections_omitted(self):
        session = _make_session()  # no tasks, decisions, commits, etc.
        md = export_session_markdown(session)
        assert "## Tasks" not in md
        assert "## Decisions" not in md
        assert "## Commits" not in md
        assert "## Events" not in md
        assert "## Next steps" not in md
        assert "## Open questions" not in md

    def test_roadmap_ref_in_metadata(self):
        md = export_session_markdown(_make_session(roadmap_ref="D4"))
        assert "| Roadmap ref | D4 |" in md

    def test_no_roadmap_ref_row_when_none(self):
        md = export_session_markdown(_make_session(roadmap_ref=None))
        assert "Roadmap ref" not in md

    def test_files_changed_section(self):
        md = export_session_markdown(_make_session(files_changed=["lib/export.py"]))
        assert "## Files changed" in md
        assert "`lib/export.py`" in md

    def test_open_questions_section(self):
        md = export_session_markdown(_make_session(open_questions=["What about edge cases?"]))
        assert "## Open questions" in md
        assert "- What about edge cases?" in md


# ---------------------------------------------------------------------------
# export_project_json
# ---------------------------------------------------------------------------


class TestExportProjectJson:
    def test_basic_structure(self):
        sessions = [_make_session(), _make_session(session_id="sess_20260228T1100_efgh")]
        data = export_project_json("test-project", sessions)
        assert data["project"] == "test-project"
        assert data["session_count"] == 2
        assert len(data["sessions"]) == 2
        assert "exported_at" in data

    def test_empty_project(self):
        data = export_project_json("empty", [])
        assert data["session_count"] == 0
        assert data["sessions"] == []


# ---------------------------------------------------------------------------
# export_project_markdown
# ---------------------------------------------------------------------------


class TestExportProjectMarkdown:
    def test_project_heading(self):
        md = export_project_markdown("my-project", [_make_session()])
        assert md.startswith("# Project: my-project")

    def test_session_count(self):
        sessions = [_make_session(), _make_session(session_id="sess_20260228T1100_efgh")]
        md = export_project_markdown("proj", sessions)
        assert "**Sessions:** 2" in md

    def test_sessions_at_lower_heading_level(self):
        md = export_project_markdown("proj", [_make_session()])
        assert "## Session: Build export feature" in md

    def test_separator_between_sessions(self):
        sessions = [
            _make_session(intent="First"),
            _make_session(session_id="sess_20260228T1100_efgh", intent="Second"),
        ]
        md = export_project_markdown("proj", sessions)
        assert "---" in md

    def test_empty_project(self):
        md = export_project_markdown("empty", [])
        assert "# Project: empty" in md
        assert "**Sessions:** 0" in md
