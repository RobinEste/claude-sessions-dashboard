"""Tests for web/app.py — FastAPI routes via TestClient.

Tests the HTTP layer: status codes, response structure, content types.
Store is monkeypatched to use tmp_path for isolation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lib import store
from web.app import app

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


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


class TestIndex:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_index_contains_dashboard_markup(self, client):
        resp = client.get("/")
        assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower()


# ---------------------------------------------------------------------------
# GET /api/overview
# ---------------------------------------------------------------------------


class TestApiOverview:
    def test_overview_returns_json(self, client):
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "timestamp" in data

    def test_overview_with_data(self, client):
        store.register_project("Test", "/tmp/test")
        store.create_session(project_slug="test", intent="Work")

        resp = client.get("/api/overview")
        data = resp.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["slug"] == "test"
        assert len(data["projects"][0]["active_sessions"]) == 1

    def test_overview_includes_task_summary(self, client):
        store.register_project("P", "/tmp/p")
        s = store.create_session(project_slug="p", intent="Tasks")
        store.add_task(s.session_id, "My task")

        resp = client.get("/api/overview")
        active = resp.json()["projects"][0]["active_sessions"][0]
        assert "task_summary" in active
        assert active["task_summary"]["total"] == 1
        assert active["task_summary"]["pending"] == 1


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}
# ---------------------------------------------------------------------------


class TestApiSessionDetail:
    def test_session_detail(self, client):
        s = store.create_session(project_slug="p", intent="Detail test")
        resp = client.get(f"/api/session/{s.session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == s.session_id
        assert data["intent"] == "Detail test"

    def test_session_detail_not_found(self, client):
        resp = client.get("/api/session/sess_20000101T0000_0000")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "Session not found"
        assert data["code"] == "NOT_FOUND"

    def test_session_detail_includes_tasks(self, client):
        s = store.create_session(project_slug="p", intent="With tasks")
        store.add_task(s.session_id, "Task 1")

        resp = client.get(f"/api/session/{s.session_id}")
        data = resp.json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["subject"] == "Task 1"


# ---------------------------------------------------------------------------
# Structured error responses (C4)
# ---------------------------------------------------------------------------


class TestStructuredErrors:
    def test_invalid_session_id_returns_validation_error(self, client):
        resp = client.get("/api/session/bad-id")
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "VALIDATION_ERROR"
        assert "error" in data

    def test_not_found_has_code_field(self, client):
        resp = client.get("/api/session/sess_20000101T0000_0000")
        data = resp.json()
        assert data["code"] == "NOT_FOUND"

    def test_error_response_is_json(self, client):
        resp = client.get("/api/session/bad-id")
        assert "application/json" in resp.headers["content-type"]

    def test_all_error_fields_present(self, client):
        resp = client.get("/api/session/sess_20000101T0000_0000")
        data = resp.json()
        assert set(data.keys()) == {"error", "code"}


# ---------------------------------------------------------------------------
# 404 for unknown routes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Export API routes (D4)
# ---------------------------------------------------------------------------


class TestApiExportSession:
    def test_export_session_json(self, client):
        s = store.create_session(project_slug="p", intent="Export test")
        resp = client.get(f"/api/export/session/{s.session_id}?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == s.session_id
        assert "task_summary" in data
        assert "duration" in data

    def test_export_session_markdown(self, client):
        s = store.create_session(project_slug="p", intent="Export md test")
        resp = client.get(f"/api/export/session/{s.session_id}?format=markdown")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "Content-Disposition" in resp.headers
        assert s.session_id in resp.headers["Content-Disposition"]
        assert "# Session: Export md test" in resp.text

    def test_export_session_not_found(self, client):
        resp = client.get("/api/export/session/sess_20000101T0000_0000?format=json")
        assert resp.status_code == 404

    def test_export_session_default_format_is_json(self, client):
        s = store.create_session(project_slug="p", intent="Default fmt")
        resp = client.get(f"/api/export/session/{s.session_id}")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]


class TestApiExportProject:
    def test_export_project_json(self, client):
        store.create_session(project_slug="proj", intent="Session 1")
        resp = client.get("/api/export/project/proj?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project"] == "proj"
        assert data["session_count"] >= 1

    def test_export_project_markdown(self, client):
        store.create_session(project_slug="proj", intent="Session 1")
        resp = client.get("/api/export/project/proj?format=markdown")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "Content-Disposition" in resp.headers
        assert "# Project: proj" in resp.text

    def test_export_project_not_found(self, client):
        resp = client.get("/api/export/project/nonexistent?format=json")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 for unknown routes
# ---------------------------------------------------------------------------


class TestUnknownRoutes:
    def test_unknown_route(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
