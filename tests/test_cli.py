"""Tests for manage.py CLI commands — JSON output, exit codes, error handling.

Tests call _dispatch() directly with argparse Namespace objects to avoid
subprocess overhead while still testing the full command → store → JSON pipeline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import store

# Import _dispatch from manage.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from manage import _dispatch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Redirect all store paths to a temp directory."""
    monkeypatch.setattr(store, "DASHBOARD_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(store, "ARCHIVE_DIR", tmp_path / "sessions" / "archive")
    monkeypatch.setattr(store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    store._ensure_dirs()


def ns(**kwargs) -> argparse.Namespace:
    """Shorthand for creating argparse Namespace objects."""
    return argparse.Namespace(**kwargs)


@pytest.fixture
def project_slug():
    store.register_project("Test", "/tmp/test")
    return "test"


@pytest.fixture
def session_id(project_slug):
    s = store.create_session(project_slug=project_slug, intent="CLI test")
    return s.session_id


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------


class TestProjectCommands:
    def test_register_project(self):
        result = _dispatch(ns(command="register-project", name="My Proj", path="/tmp/my-proj"))
        assert result["slug"] == "my-proj"
        assert result["status"] == "registered"

    def test_list_projects(self):
        store.register_project("A", "/tmp/a")
        result = _dispatch(ns(command="list-projects"))
        assert "a" in result


# ---------------------------------------------------------------------------
# Session CRUD commands
# ---------------------------------------------------------------------------


class TestSessionCommands:
    def test_create_session(self, project_slug):
        result = _dispatch(ns(
            command="create-session",
            project=project_slug,
            intent="Build feature",
            roadmap_ref="A1",
            git_branch="main",
        ))
        assert "session_id" in result
        assert result["intent"] == "Build feature"
        assert result["status"] == "active"

    def test_get_session(self, session_id):
        result = _dispatch(ns(command="get-session", session_id=session_id))
        assert result["session_id"] == session_id

    def test_get_session_not_found(self):
        result = _dispatch(ns(command="get-session", session_id="sess_20000101T0000_0000"))
        assert "error" in result

    def test_update_session(self, session_id):
        result = _dispatch(ns(
            command="update-session",
            session_id=session_id,
            intent="Updated intent",
            current_activity="Testing",
            roadmap_ref=None,
        ))
        assert result["intent"] == "Updated intent"
        assert result["current_activity"] == "Testing"

    def test_complete_session(self, session_id):
        result = _dispatch(ns(
            command="complete-session",
            session_id=session_id,
            outcome="All done",
            next_steps=["Deploy"],
            commits=None,
            files_changed=["test.py"],
        ))
        assert result["status"] == "completed"
        assert result["outcome"] == "All done"

    def test_park_session(self, session_id):
        result = _dispatch(ns(
            command="park-session",
            session_id=session_id,
            reason="Lunch break",
            next_steps=[],
        ))
        assert result["status"] == "parked"
        assert result["parked_reason"] == "Lunch break"

    def test_resume_session(self, session_id):
        store.park_session(session_id, reason="Break")
        result = _dispatch(ns(
            command="resume-session",
            session_id=session_id,
            intent="Continue",
        ))
        assert result["status"] == "active"
        assert result["intent"] == "Continue"

    def test_heartbeat(self, session_id):
        result = _dispatch(ns(command="heartbeat", session_id=session_id))
        assert result["session_id"] == session_id

    def test_heartbeat_project(self, project_slug, session_id):
        result = _dispatch(ns(command="heartbeat-project", project_slug=project_slug))
        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# Event, commit, decision commands
# ---------------------------------------------------------------------------


class TestAppendCommands:
    def test_add_event(self, session_id):
        result = _dispatch(ns(command="add-event", session_id=session_id, message="Started"))
        assert len(result["events"]) == 1
        assert result["events"][0]["message"] == "Started"

    def test_add_commit(self, session_id):
        result = _dispatch(ns(
            command="add-commit",
            session_id=session_id,
            sha="abc1234567890",
            message="Initial commit",
        ))
        assert len(result["commits"]) == 1

    def test_add_decision(self, session_id):
        result = _dispatch(ns(
            command="add-decision",
            session_id=session_id,
            decision="Use JSON",
        ))
        assert "Use JSON" in result["decisions"]

    def test_request_action(self, session_id):
        result = _dispatch(ns(
            command="request-action",
            session_id=session_id,
            reason="Need approval",
        ))
        assert result["awaiting_action"] == "Need approval"

    def test_clear_action(self, session_id):
        store.request_action(session_id, "Need review")
        result = _dispatch(ns(command="clear-action", session_id=session_id))
        assert result["awaiting_action"] is None


# ---------------------------------------------------------------------------
# Task commands
# ---------------------------------------------------------------------------


class TestTaskCommands:
    def test_add_task(self, session_id):
        result = _dispatch(ns(
            command="add-task",
            session_id=session_id,
            subject="Write tests",
        ))
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["subject"] == "Write tests"

    def test_add_tasks(self, session_id):
        result = _dispatch(ns(
            command="add-tasks",
            session_id=session_id,
            subjects=["Task A", "Task B"],
        ))
        assert len(result["tasks"]) == 2

    def test_update_task(self, session_id):
        store.add_task(session_id, "My task")
        s = store.get_session(session_id)
        task_id = s.tasks[0]["id"]

        result = _dispatch(ns(
            command="update-task",
            session_id=session_id,
            task_id=task_id,
            status="completed",
            subject=None,
        ))
        assert result["tasks"][0]["status"] == "completed"

    def test_update_task_invalid_returns_error(self, session_id):
        store.add_task(session_id, "Task")
        result = _dispatch(ns(
            command="update-task",
            session_id=session_id,
            task_id="nonexistent",
            status="completed",
            subject=None,
        ))
        assert "error" in result


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------


class TestQueryCommands:
    def test_active_sessions(self, project_slug, session_id):
        result = _dispatch(ns(command="active-sessions", project=project_slug))
        assert isinstance(result, list)
        assert len(result) == 1

    def test_parked_sessions(self, project_slug, session_id):
        store.park_session(session_id, reason="Break")
        result = _dispatch(ns(command="parked-sessions", project=project_slug))
        assert len(result) == 1

    def test_stale_sessions(self):
        result = _dispatch(ns(command="stale-sessions"))
        assert isinstance(result, list)

    def test_cleanup_stale(self):
        result = _dispatch(ns(command="cleanup-stale"))
        assert result["cleaned"] == 0

    def test_cleanup_locks(self):
        orphan = store.SESSIONS_DIR / "sess_orphan_0000.lock"
        orphan.touch()
        result = _dispatch(ns(command="cleanup-locks"))
        assert result["removed"] == 1
        assert "sess_orphan_0000.lock" in result["files"]

    def test_list_sessions(self, session_id):
        result = _dispatch(ns(
            command="list-sessions",
            project=None,
            status=None,
            limit=20,
            include_archived=False,
        ))
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_list_sessions_with_filter(self, project_slug, session_id):
        result = _dispatch(ns(
            command="list-sessions",
            project=project_slug,
            status="active",
            limit=10,
            include_archived=False,
        ))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Project state commands
# ---------------------------------------------------------------------------


class TestProjectStateCommands:
    def test_project_state_not_found(self):
        result = _dispatch(ns(command="project-state", project_slug="nonexistent"))
        assert "error" in result

    def test_update_project_state(self):
        result = _dispatch(ns(
            command="update-project-state",
            project_slug="test-proj",
            current_phase="Fase A",
            completed=["A1"],
            in_progress=None,
            next_up=["A2", "A3"],
        ))
        assert result["current_phase"] == "Fase A"
        assert result["roadmap_summary"]["completed"] == ["A1"]

    def test_project_state_roundtrip(self):
        _dispatch(ns(
            command="update-project-state",
            project_slug="proj",
            current_phase="B",
            completed=None,
            in_progress=None,
            next_up=None,
        ))
        result = _dispatch(ns(command="project-state", project_slug="proj"))
        assert result["current_phase"] == "B"


# ---------------------------------------------------------------------------
# Overview command
# ---------------------------------------------------------------------------


class TestOverviewCommand:
    def test_overview(self, project_slug, session_id):
        result = _dispatch(ns(command="overview"))
        assert "projects" in result
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# JSON output via subprocess
# ---------------------------------------------------------------------------


class TestCLISubprocess:
    """Run manage.py as a subprocess to verify JSON output and exit codes."""

    def _run(self, *args, env_override=None) -> subprocess.CompletedProcess:
        manage_py = str(Path(__file__).resolve().parent.parent / "manage.py")
        return subprocess.run(
            [sys.executable, manage_py, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_no_command_shows_help(self):
        result = self._run()
        assert result.returncode == 1

    def test_json_output_format(self):
        result = self._run("list-projects")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_overview_returns_json(self):
        result = self._run("overview")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "projects" in data


# ---------------------------------------------------------------------------
# rebuild-index (D1)
# ---------------------------------------------------------------------------


class TestRebuildIndex:
    def test_rebuild_index_command(self):
        store.create_session(project_slug="test", intent="Session 1")
        store.create_session(project_slug="test", intent="Session 2")

        # Delete index to force rebuild
        store._index_path().unlink()

        result = _dispatch(ns(command="rebuild-index"))
        assert result["status"] == "rebuilt"
        assert result["entries"] == 2
