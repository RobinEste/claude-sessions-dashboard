# Roadmap — Claude Sessions Dashboard

This roadmap tracks the path from "working prototype" to "reliable tool". The dashboard is
functionally complete (session CRUD, task tracking, web UI, skills integration) and has been
through 5 rounds of AI-assisted code review with 16 documented fixes. What's missing is the
engineering foundation: tests, packaging, CI/CD, and data lifecycle management.

## Status overview

| # | Item | Phase | Status |
|---|------|-------|--------|
| A1 | `pyproject.toml` with metadata and optional `[web]` extra | A | `[x]` |
| A2 | `requirements.txt` for quick installs | A | `[x]` |
| A3 | pytest: model tests (serialization round-trip, ID generation) | A | `[x]` |
| A4 | pytest: store tests (CRUD, locking, atomic writes, stale cleanup) | A | `[x]` |
| A5 | pytest: CLI tests (manage.py commands, JSON output) | A | `[x]` |
| A6 | pytest: web tests (FastAPI TestClient, API routes) | A | `[x]` |
| B1 | GitHub Actions: test + lint on push/PR | B | `[x]` |
| B2 | CHANGELOG.md (retroactive from git log) | B | `[x]` |
| B3 | Lock file cleanup — remove orphaned `.lock` files (PYT-001) | B | `[x]` |
| B4 | Project CLAUDE.md with dev conventions | B | `[x]` |
| B5 | Ruff / flake8 config in pyproject.toml | B | `[x]` |
| C1 | Schema versioning in session JSON (`"schema_version": 2`) | C | `[x]` |
| C2 | Archive implementation — move old sessions to `archive/` | C | `[ ]` |
| C3 | Input validation on CLI arguments and JSON payloads | C | `[ ]` |
| C4 | Structured error responses (consistent JSON errors from API) | C | `[ ]` |
| C5 | Security hardening — path traversal checks, safe deserialization | C | `[ ]` |
| D1 | Session index file for fast lookup without scanning all files | D | `[ ]` |
| D2 | Search / filter in web dashboard | D | `[ ]` |
| D3 | Session detail view in web dashboard | D | `[ ]` |
| D4 | Export (JSON / Markdown) of session history | D | `[ ]` |
| D5 | Optional desktop notifications for stale sessions | D | `[ ]` |

**Legend:** `[x]` done · `[~]` in progress · `[ ]` todo

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

---

## Not on the roadmap

These are deliberately out of scope for this project:

| Item | Reason |
|------|--------|
| **SQLite migration** | File-based JSON storage is a core design choice. It's simple, inspectable, and works without dependencies. The current locking mechanism (fcntl.flock) handles concurrency well enough for a single-user tool. |
| **Multi-user support** | This is a personal productivity tool. Adding auth, permissions, and user isolation would add complexity without matching the use case. |
| **Cloud sync** | Sessions are local by design. If sync is needed, the user can put `~/.claude/dashboard/` in a synced folder (Syncthing, git, etc.). |
| **Plugin system** | Keep the tool simple. If someone needs different behavior, they can fork or extend `store.py` directly. |
| **Electron / desktop app** | The web dashboard served on localhost is sufficient. A desktop wrapper adds build complexity without meaningful UX benefit. |

---

## References

- `docs/knowledge/INDEX.md` — 5 architectural and development insights from code review
- `docs/solutions/INDEX.md` — 16 documented bug fixes (SOL-2026-001 through SOL-2026-016)
- `code-review/output/` — Full review reports (5 iterations)
