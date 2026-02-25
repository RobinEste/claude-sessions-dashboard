"""Tests for input validation — lib/validation.py and store-level integration."""

from __future__ import annotations

import pytest

from lib.validation import (
    MAX_DECISION,
    MAX_INTENT,
    MAX_MESSAGE,
    MAX_PROJECT_NAME,
    MAX_TASK_SUBJECT,
    validate_commits_json,
    validate_git_branch,
    validate_optional_string,
    validate_port,
    validate_positive_int,
    validate_project_slug,
    validate_sha,
    validate_string_length,
)

# ---------------------------------------------------------------------------
# validate_string_length
# ---------------------------------------------------------------------------


class TestValidateStringLength:
    def test_valid_string(self):
        assert validate_string_length("hello", "field", 100) == "hello"

    def test_strips_whitespace(self):
        assert validate_string_length("  hello  ", "field", 100) == "hello"

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_string_length("", "field", 100)

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_string_length("   ", "field", 100)

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="too long"):
            validate_string_length("a" * 101, "field", 100)

    def test_exact_max_length_accepted(self):
        assert validate_string_length("a" * 100, "field", 100) == "a" * 100


class TestValidateOptionalString:
    def test_none_allowed(self):
        assert validate_optional_string(None, "field", 100) is None

    def test_valid_string(self):
        assert validate_optional_string("hello", "field", 100) == "hello"

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="too long"):
            validate_optional_string("a" * 101, "field", 100)

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_optional_string("", "field", 100)


# ---------------------------------------------------------------------------
# validate_project_slug
# ---------------------------------------------------------------------------


class TestValidateProjectSlug:
    def test_valid_slug(self):
        assert validate_project_slug("my-project") == "my-project"

    def test_valid_slug_with_numbers(self):
        assert validate_project_slug("project123") == "project123"

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_project_slug("")

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError, match="Invalid project slug"):
            validate_project_slug("MyProject")

    def test_underscore_rejected(self):
        with pytest.raises(ValueError, match="Invalid project slug"):
            validate_project_slug("my_project")

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match="Invalid project slug"):
            validate_project_slug("my project")

    def test_starting_with_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid project slug"):
            validate_project_slug("-my-project")

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="Invalid project slug"):
            validate_project_slug("../etc")


# ---------------------------------------------------------------------------
# validate_sha
# ---------------------------------------------------------------------------


class TestValidateSha:
    def test_valid_short_sha(self):
        assert validate_sha("abcd1234") == "abcd1234"

    def test_valid_full_sha(self):
        sha = "a" * 40
        assert validate_sha(sha) == sha

    def test_valid_7_char_sha(self):
        assert validate_sha("1234abc") == "1234abc"

    def test_too_short_rejected(self):
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            validate_sha("abc")

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            validate_sha("a" * 41)

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            validate_sha("xyz12345")

    def test_min_length_accepted(self):
        assert validate_sha("abcd") == "abcd"


# ---------------------------------------------------------------------------
# validate_git_branch
# ---------------------------------------------------------------------------


class TestValidateGitBranch:
    def test_valid_main(self):
        assert validate_git_branch("main") == "main"

    def test_valid_feature_branch(self):
        assert validate_git_branch("feature/my-feature") == "feature/my-feature"

    def test_valid_with_dots(self):
        assert validate_git_branch("release/v1.2.3") == "release/v1.2.3"

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_git_branch("")

    def test_starting_with_dot_rejected(self):
        with pytest.raises(ValueError, match="Invalid git branch"):
            validate_git_branch(".hidden")

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match="Invalid git branch"):
            validate_git_branch("my branch")

    def test_starting_with_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid git branch"):
            validate_git_branch("-branch")


# ---------------------------------------------------------------------------
# validate_positive_int
# ---------------------------------------------------------------------------


class TestValidatePositiveInt:
    def test_valid(self):
        assert validate_positive_int(5, "field") == 5

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            validate_positive_int(0, "field")

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            validate_positive_int(-1, "field")

    def test_max_val_respected(self):
        with pytest.raises(ValueError, match="too large"):
            validate_positive_int(100, "field", max_val=50)

    def test_at_max_val_accepted(self):
        assert validate_positive_int(50, "field", max_val=50) == 50


# ---------------------------------------------------------------------------
# validate_port
# ---------------------------------------------------------------------------


class TestValidatePort:
    def test_valid_port(self):
        assert validate_port(9000) == 9000

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="Port must be"):
            validate_port(0)

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="Port must be"):
            validate_port(-1)

    def test_too_high_rejected(self):
        with pytest.raises(ValueError, match="Port must be"):
            validate_port(70000)

    def test_max_port_accepted(self):
        assert validate_port(65535) == 65535


# ---------------------------------------------------------------------------
# validate_commits_json
# ---------------------------------------------------------------------------


class TestValidateCommitsJson:
    def test_valid_commits(self):
        commits = [{"sha": "abcd1234", "message": "fix bug"}]
        assert validate_commits_json(commits) == commits

    def test_not_a_list_rejected(self):
        with pytest.raises(ValueError, match="must be a JSON array"):
            validate_commits_json("not a list")

    def test_entry_not_dict_rejected(self):
        with pytest.raises(ValueError, match="must be an object"):
            validate_commits_json(["not a dict"])

    def test_missing_sha_rejected(self):
        with pytest.raises(ValueError, match="must have 'sha' and 'message'"):
            validate_commits_json([{"message": "fix"}])

    def test_missing_message_rejected(self):
        with pytest.raises(ValueError, match="must have 'sha' and 'message'"):
            validate_commits_json([{"sha": "abcd1234"}])

    def test_invalid_sha_in_commit_rejected(self):
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            validate_commits_json([{"sha": "xyz", "message": "fix"}])

    def test_empty_list_accepted(self):
        assert validate_commits_json([]) == []


# ---------------------------------------------------------------------------
# Store-level integration: validation enforced by store functions
# ---------------------------------------------------------------------------


class TestStoreValidation:
    """Test that store functions enforce validation via ValueError."""

    @pytest.fixture(autouse=True)
    def _isolate_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lib.store.DASHBOARD_DIR", tmp_path)
        monkeypatch.setattr("lib.store.SESSIONS_DIR", tmp_path / "sessions")
        monkeypatch.setattr("lib.store.ARCHIVE_DIR", tmp_path / "sessions" / "archive")
        monkeypatch.setattr("lib.store.PROJECTS_DIR", tmp_path / "projects")
        monkeypatch.setattr("lib.store.CONFIG_PATH", tmp_path / "config.json")

    def test_create_session_empty_intent_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="cannot be empty"):
            store.create_session("test-project", "")

    def test_create_session_intent_too_long_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="too long"):
            store.create_session("test-project", "x" * (MAX_INTENT + 1))

    def test_create_session_invalid_slug_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="Invalid project slug"):
            store.create_session("../escape", "valid intent")

    def test_create_session_invalid_branch_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="Invalid git branch"):
            store.create_session("test-project", "valid intent", git_branch=".bad")

    def test_create_session_valid(self):
        from lib import store

        session = store.create_session("test-project", "Build feature X")
        assert session.intent == "Build feature X"
        assert session.project_slug == "test-project"

    def test_add_event_empty_message_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="cannot be empty"):
            store.add_event(session.session_id, "")

    def test_add_event_message_too_long_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="too long"):
            store.add_event(session.session_id, "x" * (MAX_MESSAGE + 1))

    def test_add_commit_invalid_sha_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="Invalid commit SHA"):
            store.add_commit(session.session_id, "not-hex", "message")

    def test_add_commit_valid(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        result = store.add_commit(session.session_id, "abcdef1", "fix bug")
        assert len(result.commits) == 1

    def test_add_decision_empty_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="cannot be empty"):
            store.add_decision(session.session_id, "")

    def test_add_decision_too_long_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="too long"):
            store.add_decision(session.session_id, "x" * (MAX_DECISION + 1))

    def test_complete_session_empty_outcome_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="cannot be empty"):
            store.complete_session(session.session_id, "")

    def test_complete_session_invalid_commits_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="must be a JSON array"):
            store.complete_session(session.session_id, "done", commits="bad")

    def test_park_session_empty_reason_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="cannot be empty"):
            store.park_session(session.session_id, "")

    def test_request_action_empty_reason_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="cannot be empty"):
            store.request_action(session.session_id, "")

    def test_add_task_subject_too_long_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="too long"):
            store.add_task(session.session_id, "x" * (MAX_TASK_SUBJECT + 1))

    def test_archive_old_sessions_negative_days_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="must be positive"):
            store.archive_old_sessions(days=0)

    def test_archive_old_sessions_excessive_days_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="too large"):
            store.archive_old_sessions(days=5000)

    def test_register_project_empty_name_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="cannot be empty"):
            store.register_project("", "/some/path")

    def test_register_project_name_too_long_rejected(self):
        from lib import store

        with pytest.raises(ValueError, match="too long"):
            store.register_project("x" * (MAX_PROJECT_NAME + 1), "/some/path")

    def test_update_session_intent_too_long_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        with pytest.raises(ValueError, match="too long"):
            store.update_session(session.session_id, intent="x" * (MAX_INTENT + 1))

    def test_update_task_subject_too_long_rejected(self):
        from lib import store

        session = store.create_session("test-project", "intent")
        session = store.add_task(session.session_id, "task 1")
        task_id = session.tasks[0]["id"]
        with pytest.raises(ValueError, match="too long"):
            store.update_task(
                session.session_id, task_id, "pending",
                subject="x" * (MAX_TASK_SUBJECT + 1),
            )
