"""Tests for lib/models.py — dataclasses, enums, and ID generation."""

from __future__ import annotations

import re
from dataclasses import asdict

from lib.models import (
    DashboardConfig,
    DashboardSettings,
    ProjectRegistration,
    ProjectState,
    RoadmapSummary,
    Session,
    SessionStatus,
    generate_session_id,
)


# --- SessionStatus StrEnum ---


class TestSessionStatus:
    def test_values(self):
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.PARKED == "parked"

    def test_is_string(self):
        assert isinstance(SessionStatus.ACTIVE, str)

    def test_from_string(self):
        assert SessionStatus("active") is SessionStatus.ACTIVE
        assert SessionStatus("completed") is SessionStatus.COMPLETED
        assert SessionStatus("parked") is SessionStatus.PARKED

    def test_all_members(self):
        assert set(SessionStatus) == {
            SessionStatus.ACTIVE,
            SessionStatus.COMPLETED,
            SessionStatus.PARKED,
        }


# --- generate_session_id ---


class TestGenerateSessionId:
    ID_PATTERN = re.compile(r"^sess_\d{8}T\d{4}_[0-9a-f]{4}$")

    def test_format(self):
        sid = generate_session_id()
        assert self.ID_PATTERN.match(sid), f"ID format mismatch: {sid}"

    def test_prefix(self):
        sid = generate_session_id()
        assert sid.startswith("sess_")

    def test_uniqueness(self):
        ids = {generate_session_id() for _ in range(50)}
        assert len(ids) == 50, "Expected 50 unique IDs"

    def test_suffix_is_hex(self):
        sid = generate_session_id()
        suffix = sid.rsplit("_", 1)[1]
        int(suffix, 16)  # raises ValueError if not hex


# --- Session dataclass ---


class TestSession:
    def test_required_fields(self):
        s = Session(
            session_id="sess_test_0001",
            project_slug="my-project",
            status=SessionStatus.ACTIVE,
            intent="Testing",
        )
        assert s.session_id == "sess_test_0001"
        assert s.project_slug == "my-project"
        assert s.status == SessionStatus.ACTIVE
        assert s.intent == "Testing"

    def test_defaults(self):
        s = Session(
            session_id="x",
            project_slug="p",
            status=SessionStatus.ACTIVE,
            intent="i",
        )
        assert s.roadmap_ref is None
        assert s.started_at == ""
        assert s.ended_at is None
        assert s.outcome is None
        assert s.parked_reason is None
        assert s.current_activity is None
        assert s.awaiting_action is None
        assert s.events == []
        assert s.git_branch == "main"
        assert s.files_changed == []
        assert s.commits == []
        assert s.decisions == []
        assert s.open_questions == []
        assert s.next_steps == []
        assert s.tasks == []

    def test_list_fields_are_independent(self):
        s1 = Session(session_id="a", project_slug="p", status=SessionStatus.ACTIVE, intent="i")
        s2 = Session(session_id="b", project_slug="p", status=SessionStatus.ACTIVE, intent="i")
        s1.events.append({"msg": "test"})
        assert s2.events == [], "Mutable default should not be shared"

    def test_serialization_roundtrip(self):
        s = Session(
            session_id="sess_20260101T0000_abcd",
            project_slug="test-project",
            status=SessionStatus.PARKED,
            intent="Refactor auth",
            roadmap_ref="FASE B.2",
            started_at="2026-01-01T00:00:00+00:00",
            last_heartbeat="2026-01-01T01:00:00+00:00",
            ended_at=None,
            outcome=None,
            parked_reason="Wacht op feedback",
            current_activity="Code review",
            events=[{"timestamp": "2026-01-01T00:00:00+00:00", "message": "Start"}],
            git_branch="feature/auth",
            tasks=[{"title": "Fix login", "status": "pending"}],
        )
        d = asdict(s)
        assert d["session_id"] == "sess_20260101T0000_abcd"
        assert d["status"] == "parked"
        assert d["parked_reason"] == "Wacht op feedback"
        assert d["events"] == [{"timestamp": "2026-01-01T00:00:00+00:00", "message": "Start"}]
        assert d["tasks"] == [{"title": "Fix login", "status": "pending"}]

        # Reconstruct from dict
        d["status"] = SessionStatus(d["status"])
        s2 = Session(**d)
        assert s2 == s

    def test_status_serializes_as_string(self):
        s = Session(
            session_id="x",
            project_slug="p",
            status=SessionStatus.COMPLETED,
            intent="i",
        )
        d = asdict(s)
        assert d["status"] == "completed"
        assert isinstance(d["status"], str)


# --- ProjectRegistration ---


class TestProjectRegistration:
    def test_fields(self):
        pr = ProjectRegistration(
            name="My Project",
            path="/home/user/projects/my-project",
            registered_at="2026-01-01T00:00:00+00:00",
        )
        assert pr.name == "My Project"
        assert pr.path == "/home/user/projects/my-project"

    def test_serialization_roundtrip(self):
        pr = ProjectRegistration(name="P", path="/tmp/p", registered_at="2026-01-01T00:00:00+00:00")
        d = asdict(pr)
        pr2 = ProjectRegistration(**d)
        assert pr2 == pr


# --- RoadmapSummary ---


class TestRoadmapSummary:
    def test_defaults(self):
        rs = RoadmapSummary()
        assert rs.completed == []
        assert rs.in_progress == []
        assert rs.next_up == []

    def test_serialization_roundtrip(self):
        rs = RoadmapSummary(
            completed=["A1"],
            in_progress=["A2"],
            next_up=["A3", "A4", "A5"],
        )
        d = asdict(rs)
        rs2 = RoadmapSummary(**d)
        assert rs2 == rs


# --- ProjectState ---


class TestProjectState:
    def test_defaults(self):
        ps = ProjectState(project_slug="test")
        assert ps.current_phase == ""
        assert ps.active_sessions == 0
        assert ps.total_sessions == 0
        assert isinstance(ps.roadmap_summary, RoadmapSummary)

    def test_serialization_roundtrip(self):
        ps = ProjectState(
            project_slug="test",
            current_phase="Fase A",
            roadmap_summary=RoadmapSummary(completed=["A1"]),
            active_sessions=2,
            total_sessions=5,
        )
        d = asdict(ps)
        # Reconstruct nested dataclass
        d["roadmap_summary"] = RoadmapSummary(**d["roadmap_summary"])
        ps2 = ProjectState(**d)
        assert ps2 == ps


# --- DashboardSettings ---


class TestDashboardSettings:
    def test_defaults(self):
        ds = DashboardSettings()
        assert ds.dashboard_port == 9000
        assert ds.stale_threshold_hours == 24
        assert ds.archive_after_days == 30


# --- DashboardConfig ---


class TestDashboardConfig:
    def test_defaults(self):
        dc = DashboardConfig()
        assert dc.version == 1
        assert dc.projects == {}
        assert isinstance(dc.settings, DashboardSettings)

    def test_serialization_roundtrip(self):
        dc = DashboardConfig(
            version=1,
            projects={
                "my-proj": ProjectRegistration(
                    name="My Proj",
                    path="/tmp/proj",
                    registered_at="2026-01-01T00:00:00+00:00",
                )
            },
            settings=DashboardSettings(dashboard_port=8080),
        )
        d = asdict(dc)
        assert d["projects"]["my-proj"]["name"] == "My Proj"
        assert d["settings"]["dashboard_port"] == 8080
