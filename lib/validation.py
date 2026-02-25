"""Input validation for CLI arguments and store operations.

Centralised validation rules so both CLI and store layer
share the same constraints.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# String length limits
# ---------------------------------------------------------------------------

MAX_INTENT = 500
MAX_OUTCOME = 1000
MAX_MESSAGE = 2000
MAX_REASON = 500
MAX_DECISION = 500
MAX_TASK_SUBJECT = 300
MAX_ACTIVITY = 300
MAX_ROADMAP_REF = 100
MAX_PROJECT_NAME = 100
MAX_GIT_BRANCH = 200

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_PROJECT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")
_GIT_BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/\-]*$")


# ---------------------------------------------------------------------------
# Validators — all raise ValueError on failure
# ---------------------------------------------------------------------------


def validate_string_length(value: str, field: str, max_len: int) -> str:
    """Validate string is non-empty and within length limit."""
    if not value or not value.strip():
        raise ValueError(f"{field} cannot be empty")
    stripped = value.strip()
    if len(stripped) > max_len:
        raise ValueError(f"{field} too long ({len(stripped)} chars, max {max_len})")
    return stripped


def validate_optional_string(value: str | None, field: str, max_len: int) -> str | None:
    """Validate optional string — None is allowed, but if set must be within limit."""
    if value is None:
        return None
    return validate_string_length(value, field, max_len)


def validate_project_slug(slug: str) -> str:
    """Validate project slug format (lowercase alphanumeric + hyphens)."""
    if not slug:
        raise ValueError("Project slug cannot be empty")
    if not _PROJECT_SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid project slug: '{slug}'. "
            "Must be lowercase alphanumeric with hyphens, starting with alphanumeric."
        )
    return slug


def validate_sha(sha: str) -> str:
    """Validate git commit SHA (4-40 hex characters)."""
    if not _SHA_RE.match(sha):
        raise ValueError(f"Invalid commit SHA: '{sha}'. Must be 4-40 hex characters.")
    return sha


def validate_git_branch(branch: str) -> str:
    """Validate git branch name."""
    if not branch:
        raise ValueError("Git branch cannot be empty")
    if not _GIT_BRANCH_RE.match(branch):
        raise ValueError(
            f"Invalid git branch name: '{branch}'. "
            "Must start with alphanumeric, contain only [a-zA-Z0-9._/-]."
        )
    return branch


def validate_positive_int(value: int, field: str, max_val: int | None = None) -> int:
    """Validate integer is positive (> 0), optionally with upper bound."""
    if value < 1:
        raise ValueError(f"{field} must be positive (got {value})")
    if max_val is not None and value > max_val:
        raise ValueError(f"{field} too large ({value}, max {max_val})")
    return value


def validate_port(port: int) -> int:
    """Validate TCP port number (1024-65535 for unprivileged)."""
    if port < 1 or port > 65535:
        raise ValueError(f"Port must be 1-65535 (got {port})")
    return port


MAX_COMMITS = 500


def validate_commits_json(commits: list) -> list[dict]:
    """Validate that commits is a list of {sha, message} dicts."""
    if not isinstance(commits, list):
        raise ValueError("Commits must be a JSON array")
    if len(commits) > MAX_COMMITS:
        raise ValueError(f"Too many commits ({len(commits)}, max {MAX_COMMITS})")
    for i, entry in enumerate(commits):
        if not isinstance(entry, dict):
            raise ValueError(f"Commit entry {i} must be an object")
        if "sha" not in entry or "message" not in entry:
            raise ValueError(f"Commit entry {i} must have 'sha' and 'message' fields")
        validate_sha(str(entry["sha"]))
    return commits
