# Roadmap History — Claude Sessions Dashboard

Archived completed phases from `ROADMAP.md`.

---

## Phase A — Foundation: packaging & tests

> Goal: make the project installable and get automated test coverage on all layers.

### A1 · `pyproject.toml`

Create a PEP 621 `pyproject.toml` with project metadata, Python ≥ 3.11 requirement, console
script entry point for `manage.py`, and an optional `[web]` extra for `fastapi` + `uvicorn`.

### A2 · `requirements.txt`

A simple `requirements.txt` pointing to the optional web dependencies, for users who prefer
`pip install -r` over `pip install .[web]`.

### A3 · Model tests

Test `models.py`: dataclass instantiation, `StrEnum` values, `generate_session_id()` format
and uniqueness, serialization round-trips via `dataclasses.asdict`.

### A4 · Store tests

Test `store.py` with **real file I/O** (no mocking the JSON store — that's the core
functionality). Use `tmp_path` fixtures for isolation. Cover:
- Session CRUD (create → read → update → complete)
- Task operations (add, deduplicate, update status, batch add)
- File locking behavior (concurrent writes don't corrupt)
- Atomic write safety (interrupted write doesn't leave partial files)
- Stale session detection and cleanup
- Project state refresh after session changes

### A5 · CLI tests

Test `manage.py` commands via `subprocess.run` or by importing command functions directly.
Verify JSON output format, exit codes, and error messages.

### A6 · Web tests

Test FastAPI routes (`/api/overview`, static serving) using `TestClient`. Verify response
structure and status codes.

---

## Phase B — Quality: CI/CD & housekeeping

> Goal: automated quality gates on every push, and project hygiene.
>
> **Depends on:** Phase A (tests must exist before CI can run them).

### B1 · GitHub Actions

Workflow that runs on push and PR:
- `pytest` with coverage report
- Linter (ruff or flake8)
- Python 3.11 + 3.12 matrix

### B2 · CHANGELOG.md

Retroactive changelog derived from git history. Going forward, maintained manually with each
release or significant change.

### B3 · Lock file cleanup (PYT-001)

Orphaned `.lock` files accumulate in `sessions/` after sessions are completed or deleted.
Add a cleanup step to `cleanup_stale_sessions()` or a dedicated `cleanup-locks` CLI command.

See: `docs/solutions/INDEX.md` — related to SOL-2026-001 through SOL-2026-004.

### B4 · Project CLAUDE.md

Add a `CLAUDE.md` to the repository root with project-specific development conventions:
directory structure, test commands, code style, and contribution guidelines for AI-assisted
development.

### B5 · Linter configuration

Add ruff or flake8 configuration to `pyproject.toml`. Align with existing code style (line
length, import ordering, etc.).

---

## Phase C — Robustness: data integrity & hardening

> Goal: protect against data corruption, invalid input, and edge cases.
>
> **Depends on:** Phase B (CI ensures regressions are caught).

### C1 · Schema versioning

Add `"schema_version": 2` to session JSON files. Include a migration function that upgrades
v1 files on read. This allows future schema changes without breaking existing data.

### C2 · Archive implementation

The `archive_after_days` setting exists in config (default: 30) but is not implemented.
Build the archive flow:
- Move completed sessions older than N days to `archive/` subdirectory
- Exclude archived sessions from `list_sessions()` by default
- Add `--include-archived` flag to CLI queries
- Add `archive` CLI command for manual archiving

### C3 · Input validation

Validate CLI arguments and API payloads before they reach the store layer:
- Session ID format (`sess_YYYYMMDDTHHMM_xxxx`)
- Status values (reject unknown statuses)
- Required fields (intent, project slug)
- String length limits

### C4 · Structured error responses

The FastAPI API should return consistent JSON error objects (`{"error": "message",
"code": "NOT_FOUND"}`) instead of unstructured 500 errors.

### C5 · Security hardening

- Path traversal checks: validate that session IDs and project slugs cannot escape the
  data directory
- Safe JSON deserialization: handle malformed JSON files gracefully
- Limit file sizes to prevent abuse

See: `docs/knowledge/security/` — KNW-2026-004 (TOCTOU prevention).

---

## Phase D — Enhancement: performance & UX

> Goal: improve daily usability for power users with many sessions.
>
> **Depends on:** Phase C (stable data layer).

### D1 · Session index

When the number of sessions grows, scanning all JSON files becomes slow. Maintain a
lightweight index file (`sessions/_index.json`) that maps session IDs to status and project,
updated on each write. Rebuild from files if the index is missing or corrupt.

### D2 · Search and filter

Add search/filter to the web dashboard: filter by project, status, date range, or free-text
search across intent and events.

### D3 · Session detail view

Clicking a session in the web dashboard opens a detail view with full event timeline, task
list, commits, decisions, and files changed.

### D4 · Export

Export session history as JSON or Markdown. Useful for including in project documentation or
handoff notes.

### D5 · Notifications

Optional desktop notifications (macOS `osascript` / `terminal-notifier`) when a session
becomes stale or when a parked session has been waiting for a configurable period.
