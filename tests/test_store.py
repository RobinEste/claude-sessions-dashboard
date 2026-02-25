"""Tests for lib/store.py — CRUD, locking, tasks, stale cleanup.

All tests use real file I/O via tmp_path fixtures. Module-level paths
are monkeypatched so tests never touch the real dashboard data.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from lib import store
from lib.models import SessionStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Redirect all store paths to a temp directory."""
    monkeypatch.setattr(store, "DASHBOARD_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    store._ensure_dirs()


@pytest.fixture
def session_id():
    """Create a session and return its ID."""
    s = store.create_session(project_slug="test-project", intent="Test session")
    return s.session_id


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_load_creates_default(self, tmp_path):
        config = store.load_config()
        assert config.version == 1
        assert config.projects == {}
        assert (tmp_path / "config.json").exists()

    def test_save_and_load_roundtrip(self):
        config = store.load_config()
        config.settings.dashboard_port = 8080
        store.save_config(config)

        reloaded = store.load_config()
        assert reloaded.settings.dashboard_port == 8080


# ---------------------------------------------------------------------------
# Project registration
# ---------------------------------------------------------------------------


class TestRegisterProject:
    def test_register_returns_slug(self):
        slug = store.register_project("My Project", "/tmp/my-project")
        assert slug == "my-project"

    def test_register_is_idempotent(self):
        store.register_project("Proj", "/tmp/proj")
        store.register_project("Proj", "/tmp/proj")
        config = store.load_config()
        assert len(config.projects) == 1

    def test_get_registered_projects(self):
        store.register_project("A", "/tmp/a")
        store.register_project("B", "/tmp/b")
        projects = store.get_registered_projects()
        assert "a" in projects
        assert "b" in projects


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------


class TestSchemaVersioning:
    def test_new_session_has_schema_version(self):
        s = store.create_session(project_slug="proj", intent="Test")
        path = store.SESSIONS_DIR / f"{s.session_id}.json"
        with open(path) as f:
            data = json.load(f)
        assert data["schema_version"] == store.SCHEMA_VERSION

    def test_v1_session_migrated_on_read(self):
        """A v1 session (no schema_version) is migrated transparently."""
        sid = "sess_20260101T0000_abcd"
        path = store.SESSIONS_DIR / f"{sid}.json"
        v1_data = {
            "session_id": sid,
            "project_slug": "proj",
            "status": "active",
            "intent": "Legacy session",
            "started_at": "2026-01-01T00:00:00+00:00",
            "last_heartbeat": "2026-01-01T00:00:00+00:00",
        }
        with open(path, "w") as f:
            json.dump(v1_data, f)

        s = store.get_session(sid)
        assert s is not None
        assert s.intent == "Legacy session"
        assert s.tasks == []  # v1 → v2 migration adds tasks

    def test_v2_session_not_modified(self):
        """A v2 session passes through migration unchanged."""
        s = store.create_session(project_slug="proj", intent="Modern")
        loaded = store.get_session(s.session_id)
        assert loaded.intent == "Modern"


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class TestSessionCRUD:
    def test_create_session(self):
        s = store.create_session(
            project_slug="proj",
            intent="Build feature",
            roadmap_ref="A1",
            git_branch="feature/x",
        )
        assert s.session_id.startswith("sess_")
        assert s.status == SessionStatus.ACTIVE
        assert s.intent == "Build feature"
        assert s.roadmap_ref == "A1"
        assert s.git_branch == "feature/x"
        assert s.started_at != ""

    def test_get_session(self, session_id):
        s = store.get_session(session_id)
        assert s is not None
        assert s.session_id == session_id
        assert s.intent == "Test session"

    def test_get_session_not_found(self):
        assert store.get_session("sess_20000101T0000_0000") is None

    def test_update_session(self, session_id):
        s = store.update_session(session_id, current_activity="Writing tests")
        assert s is not None
        assert s.current_activity == "Writing tests"

        reloaded = store.get_session(session_id)
        assert reloaded.current_activity == "Writing tests"

    def test_update_session_not_found(self):
        assert store.update_session("sess_20000101T0000_0000", intent="x") is None

    def test_update_session_ignores_unknown_fields(self, session_id):
        s = store.update_session(session_id, nonexistent_field="value")
        assert s is not None
        assert not hasattr(s, "nonexistent_field")

    def test_complete_session(self, session_id):
        s = store.complete_session(
            session_id,
            outcome="Done",
            next_steps=["Deploy", "Test", "Document"],
            files_changed=["store.py"],
            decisions=["Use JSON"],
        )
        assert s.status == SessionStatus.COMPLETED
        assert s.outcome == "Done"
        assert s.ended_at is not None
        assert s.next_steps == ["Deploy", "Test", "Document"]
        assert s.files_changed == ["store.py"]
        assert s.decisions == ["Use JSON"]

    def test_complete_session_truncates_next_steps(self, session_id):
        s = store.complete_session(
            session_id,
            outcome="Done",
            next_steps=["A", "B", "C", "D", "E"],
        )
        assert len(s.next_steps) == 3

    def test_park_session(self, session_id):
        s = store.park_session(session_id, reason="Waiting for review")
        assert s.status == SessionStatus.PARKED
        assert s.parked_reason == "Waiting for review"
        assert s.ended_at is not None

    def test_resume_session(self, session_id):
        store.park_session(session_id, reason="Break")
        new_session = store.resume_session(session_id, new_intent="Continue work")

        assert new_session.status == SessionStatus.ACTIVE
        assert new_session.intent == "Continue work"
        assert new_session.session_id != session_id

        old = store.get_session(session_id)
        assert old.status == SessionStatus.COMPLETED
        assert "Resumed as" in old.outcome

    def test_resume_session_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            store.resume_session("sess_20000101T0000_0000")


# ---------------------------------------------------------------------------
# Events, commits, decisions
# ---------------------------------------------------------------------------


class TestAppendOperations:
    def test_add_event(self, session_id):
        s = store.add_event(session_id, "Started coding")
        assert len(s.events) == 1
        assert s.events[0]["message"] == "Started coding"
        assert "timestamp" in s.events[0]

    def test_add_multiple_events(self, session_id):
        store.add_event(session_id, "Event 1")
        s = store.add_event(session_id, "Event 2")
        assert len(s.events) == 2

    def test_add_event_not_found(self):
        assert store.add_event("sess_20000101T0000_0000", "msg") is None

    def test_add_commit(self, session_id):
        s = store.add_commit(session_id, "abc1234567890", "Initial commit")
        assert len(s.commits) == 1
        assert s.commits[0]["sha"] == "abc1234567890"

    def test_add_commit_deduplicates(self, session_id):
        store.add_commit(session_id, "abc1234567890", "First")
        s = store.add_commit(session_id, "abc1234999999", "Second with same prefix")
        assert len(s.commits) == 1  # same SHA[:7]

    def test_add_decision(self, session_id):
        s = store.add_decision(session_id, "Use JSON storage")
        assert "Use JSON storage" in s.decisions

    def test_add_decision_deduplicates(self, session_id):
        store.add_decision(session_id, "Decision A")
        s = store.add_decision(session_id, "Decision A")
        assert s.decisions.count("Decision A") == 1

    def test_request_and_clear_action(self, session_id):
        s = store.request_action(session_id, "Need approval")
        assert s.awaiting_action == "Need approval"

        s = store.clear_action(session_id)
        assert s.awaiting_action is None


# ---------------------------------------------------------------------------
# Task operations
# ---------------------------------------------------------------------------


class TestTaskOperations:
    def test_add_task(self, session_id):
        s = store.add_task(session_id, "Write tests")
        assert len(s.tasks) == 1
        assert s.tasks[0]["subject"] == "Write tests"
        assert s.tasks[0]["status"] == "pending"
        assert s.tasks[0]["id"].startswith("t")

    def test_add_tasks_batch(self, session_id):
        s = store.add_tasks(session_id, ["Task A", "Task B", "Task C"])
        assert len(s.tasks) == 3
        subjects = {t["subject"] for t in s.tasks}
        assert subjects == {"Task A", "Task B", "Task C"}

    def test_add_task_deduplicates(self, session_id):
        store.add_task(session_id, "Same task")
        s = store.add_task(session_id, "Same task")
        assert len(s.tasks) == 1

    def test_add_tasks_batch_deduplicates(self, session_id):
        store.add_tasks(session_id, ["A", "B"])
        s = store.add_tasks(session_id, ["B", "C"])
        assert len(s.tasks) == 3

    def test_add_task_not_found(self):
        assert store.add_task("sess_20000101T0000_0000", "task") is None

    def test_update_task_status(self, session_id):
        s = store.add_task(session_id, "My task")
        task_id = s.tasks[0]["id"]

        s = store.update_task(session_id, task_id, "in_progress")
        assert s.tasks[0]["status"] == "in_progress"

        s = store.update_task(session_id, task_id, "completed")
        assert s.tasks[0]["status"] == "completed"

    def test_update_task_with_subject_rename(self, session_id):
        s = store.add_task(session_id, "Old name")
        task_id = s.tasks[0]["id"]

        s = store.update_task(session_id, task_id, "pending", subject="New name")
        assert s.tasks[0]["subject"] == "New name"

    def test_update_task_invalid_status(self, session_id):
        s = store.add_task(session_id, "Task")
        task_id = s.tasks[0]["id"]

        with pytest.raises(ValueError, match="Invalid status"):
            store.update_task(session_id, task_id, "invalid_status")

    def test_update_task_not_found_task_id(self, session_id):
        store.add_task(session_id, "Task")
        with pytest.raises(ValueError, match="not found"):
            store.update_task(session_id, "t_nonexistent", "completed")

    def test_update_task_duplicate_subject_rejected(self, session_id):
        store.add_tasks(session_id, ["Task A", "Task B"])
        s = store.get_session(session_id)
        task_b_id = s.tasks[1]["id"]

        with pytest.raises(ValueError, match="already exists"):
            store.update_task(session_id, task_b_id, "pending", subject="Task A")

    def test_update_task_not_found_session(self):
        assert store.update_task("sess_20000101T0000_0000", "t1", "completed") is None

    def test_add_tasks_with_legacy_tasks_without_subject(self, session_id):
        """LOG-001 regression: tasks without 'subject' key should not crash."""
        s = store.get_session(session_id)
        # Manually inject a legacy task without 'subject'
        s.tasks.append({"id": "t_legacy", "status": "pending"})
        store._save_session(s)

        # Should not raise KeyError
        s = store.add_task(session_id, "New task")
        assert len(s.tasks) == 2

    def test_update_task_validates_before_mutating(self, session_id):
        """LOG-002 regression: subject check must happen before status mutation."""
        store.add_tasks(session_id, ["Existing", "Target"])
        s = store.get_session(session_id)
        target_id = s.tasks[1]["id"]

        with pytest.raises(ValueError, match="already exists"):
            store.update_task(session_id, target_id, "completed", subject="Existing")

        # Verify the task was NOT mutated
        s = store.get_session(session_id)
        target = next(t for t in s.tasks if t["id"] == target_id)
        assert target["status"] == "pending"  # should still be pending


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self, session_id):
        before = store.get_session(session_id).last_heartbeat
        time.sleep(0.01)
        s = store.heartbeat(session_id)
        assert s.last_heartbeat > before

    def test_heartbeat_only_active_sessions(self, session_id):
        store.complete_session(session_id, outcome="Done")
        s = store.heartbeat(session_id)
        # Returns the session but doesn't update heartbeat
        assert s is not None

    def test_heartbeat_project(self):
        store.register_project("P", "/tmp/p")
        store.create_session(project_slug="p", intent="S1")
        store.create_session(project_slug="p", intent="S2")

        updated = store.heartbeat_project("p")
        assert len(updated) == 2


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestQueries:
    def test_list_sessions_empty(self):
        sessions = store.list_sessions()
        assert sessions == []

    def test_list_sessions_all(self):
        store.create_session(project_slug="a", intent="A")
        store.create_session(project_slug="b", intent="B")
        assert len(store.list_sessions()) == 2

    def test_list_sessions_filter_project(self):
        store.create_session(project_slug="a", intent="A")
        store.create_session(project_slug="b", intent="B")
        assert len(store.list_sessions(project_slug="a")) == 1

    def test_list_sessions_filter_status(self, session_id):
        store.complete_session(session_id, outcome="Done")
        store.create_session(project_slug="test-project", intent="New")

        active = store.list_sessions(status=SessionStatus.ACTIVE)
        completed = store.list_sessions(status=SessionStatus.COMPLETED)
        assert len(active) == 1
        assert len(completed) == 1

    def test_get_active_sessions(self):
        store.create_session(project_slug="p", intent="Active")
        s2 = store.create_session(project_slug="p", intent="To complete")
        store.complete_session(s2.session_id, outcome="Done")

        active = store.get_active_sessions("p")
        assert len(active) == 1
        assert active[0].intent == "Active"

    def test_get_parked_sessions(self, session_id):
        store.park_session(session_id, reason="Break")
        parked = store.get_parked_sessions("test-project")
        assert len(parked) == 1


# ---------------------------------------------------------------------------
# Stale detection and cleanup
# ---------------------------------------------------------------------------


class TestStaleDetection:
    def _make_stale_session(self, hours_ago: int = 48) -> str:
        """Create a session with an old heartbeat."""
        s = store.create_session(project_slug="test", intent="Stale session")
        old_time = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
        # Directly update the file to set old heartbeat
        path = store.SESSIONS_DIR / f"{s.session_id}.json"
        with open(path) as f:
            data = json.load(f)
        data["last_heartbeat"] = old_time
        with open(path, "w") as f:
            json.dump(data, f)
        return s.session_id

    def test_get_stale_sessions(self):
        self._make_stale_session(hours_ago=48)
        store.create_session(project_slug="test", intent="Fresh")

        stale = store.get_stale_sessions(threshold_hours=24)
        assert len(stale) == 1

    def test_get_stale_sessions_respects_threshold(self):
        self._make_stale_session(hours_ago=2)
        stale = store.get_stale_sessions(threshold_hours=24)
        assert len(stale) == 0

    def test_cleanup_stale_sessions(self):
        store.register_project("Test", "/tmp/test")
        sid = self._make_stale_session(hours_ago=48)

        cleaned = store.cleanup_stale_sessions(threshold_hours=24)
        assert len(cleaned) == 1
        assert cleaned[0].session_id == sid

        s = store.get_session(sid)
        assert s.status == SessionStatus.COMPLETED
        assert "stale" in s.outcome.lower()

    def test_cleanup_skips_recently_heartbeated(self):
        store.register_project("Test", "/tmp/test")
        store.create_session(project_slug="test", intent="Fresh")

        cleaned = store.cleanup_stale_sessions(threshold_hours=24)
        assert len(cleaned) == 0


# ---------------------------------------------------------------------------
# Orphaned lock cleanup
# ---------------------------------------------------------------------------


class TestOrphanedLockCleanup:
    def test_cleanup_removes_orphaned_locks(self):
        """Lock files without matching session JSON are removed."""
        orphan = store.SESSIONS_DIR / "sess_fake_0000.lock"
        orphan.touch()

        removed = store.cleanup_orphaned_locks()
        assert "sess_fake_0000.lock" in removed
        assert not orphan.exists()

    def test_cleanup_keeps_locks_with_sessions(self):
        """Lock files with matching session JSON are kept."""
        s = store.create_session(project_slug="test", intent="Active")
        lock = store.SESSIONS_DIR / f"{s.session_id}.lock"
        lock.touch()

        removed = store.cleanup_orphaned_locks()
        assert len(removed) == 0
        assert lock.exists()

    def test_cleanup_stale_also_cleans_locks(self):
        """cleanup_stale_sessions() calls lock cleanup automatically."""
        orphan = store.SESSIONS_DIR / "sess_old_0000.lock"
        orphan.touch()

        store.cleanup_stale_sessions(threshold_hours=24)
        assert not orphan.exists()


# ---------------------------------------------------------------------------
# Project state
# ---------------------------------------------------------------------------


class TestProjectState:
    def test_update_project_state(self):
        state = store.update_project_state(
            "my-proj",
            current_phase="Fase A",
            roadmap_completed=["A1"],
            roadmap_next_up=["A2", "A3", "A4"],
        )
        assert state.current_phase == "Fase A"
        assert state.roadmap_summary.completed == ["A1"]
        assert len(state.roadmap_summary.next_up) == 3

    def test_update_project_state_truncates_next_up(self):
        state = store.update_project_state(
            "proj",
            roadmap_next_up=["A", "B", "C", "D", "E"],
        )
        assert len(state.roadmap_summary.next_up) == 3

    def test_project_state_persists(self):
        store.update_project_state("proj", current_phase="Fase B")
        state = store.get_project_state("proj")
        assert state.current_phase == "Fase B"

    def test_refresh_project_state_after_session_changes(self):
        store.register_project("P", "/tmp/p")
        s = store.create_session(project_slug="p", intent="Work")
        state = store.get_project_state("p")
        assert state.active_sessions == 1

        store.complete_session(s.session_id, outcome="Done")
        state = store.get_project_state("p")
        assert state.active_sessions == 0
        assert state.total_sessions == 1

    def test_get_all_project_states(self):
        store.register_project("A", "/tmp/a")
        store.register_project("B", "/tmp/b")
        states = store.get_all_project_states()
        assert len(states) == 2


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_atomic_write_creates_file(self, tmp_path):
        path = tmp_path / "test.json"
        store._atomic_write(path, {"key": "value"})
        assert path.exists()
        with open(path) as f:
            assert json.load(f) == {"key": "value"}

    def test_atomic_write_no_partial_files_on_success(self, tmp_path):
        path = tmp_path / "test.json"
        store._atomic_write(path, {"ok": True})
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_overwrites(self, tmp_path):
        path = tmp_path / "test.json"
        store._atomic_write(path, {"version": 1})
        store._atomic_write(path, {"version": 2})
        with open(path) as f:
            assert json.load(f)["version"] == 2


# ---------------------------------------------------------------------------
# Concurrent writes (locking)
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    def test_concurrent_events_no_data_loss(self, session_id):
        """Multiple threads adding events should not lose any."""
        n_threads = 5
        events_per_thread = 4
        barrier = threading.Barrier(n_threads)

        def add_events(thread_num):
            barrier.wait()
            for i in range(events_per_thread):
                store.add_event(session_id, f"Thread {thread_num} event {i}")

        threads = [
            threading.Thread(target=add_events, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        s = store.get_session(session_id)
        assert len(s.events) == n_threads * events_per_thread

    def test_concurrent_tasks_no_data_loss(self, session_id):
        """Multiple threads adding tasks should not lose any."""
        n_threads = 5
        barrier = threading.Barrier(n_threads)

        def add_task(thread_num):
            barrier.wait()
            store.add_task(session_id, f"Task from thread {thread_num}")

        threads = [
            threading.Thread(target=add_task, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        s = store.get_session(session_id)
        assert len(s.tasks) == n_threads


# ---------------------------------------------------------------------------
# build_overview
# ---------------------------------------------------------------------------


class TestBuildOverview:
    def test_build_overview_empty(self):
        overview = store.build_overview()
        assert "projects" in overview
        assert "timestamp" in overview
        assert overview["projects"] == []

    def test_build_overview_with_data(self):
        store.register_project("P", "/tmp/p")
        store.create_session(project_slug="p", intent="Work")

        overview = store.build_overview()
        assert len(overview["projects"]) == 1
        proj = overview["projects"][0]
        assert proj["slug"] == "p"
        assert len(proj["active_sessions"]) == 1
        assert "task_summary" in proj["active_sessions"][0]
