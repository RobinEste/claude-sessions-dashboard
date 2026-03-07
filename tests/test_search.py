"""Tests for lib/search.py — TF-IDF search index."""

from __future__ import annotations

import os

import pytest

from lib.search import SearchIndex


@pytest.fixture
def exports_dir(tmp_path):
    """Create a mock exports directory with test Markdown files."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Session 1: about auth middleware
    (project_dir / "sess_20260301T1000_a1b2.md").write_text(
        """---
schema_version: 1
session_id: sess_20260301T1000_a1b2
project_slug: test-project
started_at: 2026-03-01T10:00:00Z
ended_at: 2026-03-01T12:00:00Z
intent: "Fix auth middleware bug"
status: completed
---

# Session: Fix auth middleware bug

## Outcome

Fixed the authentication middleware by adding proper token validation.
The JWT tokens were not being verified correctly.

## Conversation Highlights

The auth middleware was failing because the token expiry check used
the wrong timezone. We fixed it by converting to UTC before comparison.
"""
    )

    # Session 2: about database setup
    (project_dir / "sess_20260302T0900_c3d4.md").write_text(
        """---
schema_version: 1
session_id: sess_20260302T0900_c3d4
project_slug: test-project
started_at: 2026-03-02T09:00:00Z
ended_at: 2026-03-02T11:00:00Z
intent: "Setup Neo4j database constraints"
status: completed
---

# Session: Setup Neo4j database constraints

## Outcome

Created unique constraints on Company nodes.
The UNIQUE constraint on :Company(slug) prevents duplicate entries.

## Conversation Highlights

Neo4j constraint types: UNIQUE, EXISTS, NODE KEY.
We chose UNIQUE on slug fields and EXISTS on required properties.
"""
    )

    # Different project
    other_dir = tmp_path / "other-project"
    other_dir.mkdir()
    (other_dir / "sess_20260303T1400_e5f6.md").write_text(
        """---
schema_version: 1
session_id: sess_20260303T1400_e5f6
project_slug: other-project
started_at: 2026-03-03T14:00:00Z
ended_at: 2026-03-03T16:00:00Z
intent: "Deploy frontend to production"
status: completed
---

# Session: Deploy frontend to production

## Outcome

Deployed the React frontend to Hetzner.
"""
    )

    return tmp_path


class TestSearchIndex:
    def test_build_index(self, exports_dir):
        idx = SearchIndex(exports_dir)
        count = idx.build(force=True)
        assert count == 3

    def test_search_finds_relevant(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("auth middleware token")
        assert len(results) > 0
        assert results[0]["session_id"] == "sess_20260301T1000_a1b2"

    def test_search_neo4j(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("Neo4j constraint")
        assert len(results) > 0
        assert results[0]["session_id"] == "sess_20260302T0900_c3d4"

    def test_search_project_filter(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("deploy", project="other-project")
        assert len(results) == 1
        assert results[0]["project"] == "other-project"

    def test_search_no_results(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("kubernetes helm chart")
        assert len(results) == 0

    def test_search_limit(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("session", limit=1)
        assert len(results) <= 1

    def test_snippet_included(self, exports_dir):
        idx = SearchIndex(exports_dir)
        results = idx.search("auth middleware")
        assert results[0]["snippet"]
        assert "auth" in results[0]["snippet"].lower() or "token" in results[0]["snippet"].lower()

    def test_cache_rebuilt_on_new_file(self, exports_dir):
        idx = SearchIndex(exports_dir)
        idx.build(force=True)

        # Add a new file
        project_dir = exports_dir / "test-project"
        (project_dir / "sess_20260304T1000_g7h8.md").write_text(
            """---
schema_version: 1
session_id: sess_20260304T1000_g7h8
project_slug: test-project
started_at: 2026-03-04T10:00:00Z
ended_at: 2026-03-04T12:00:00Z
intent: "Add caching layer"
status: completed
---

# Session: Add caching layer

## Outcome

Added Redis caching for API responses.
"""
        )

        # Touch to ensure mtime is newer
        os.utime(project_dir / "sess_20260304T1000_g7h8.md")

        idx2 = SearchIndex(exports_dir)
        count = idx2.build()  # Should auto-rebuild
        assert count == 4

    def test_index_file_permissions(self, exports_dir):
        idx = SearchIndex(exports_dir)
        idx.build(force=True)
        assert idx.index_path.exists()
        mode = oct(idx.index_path.stat().st_mode)[-3:]
        assert mode == "600"
