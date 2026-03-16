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
| C2 | Archive implementation — move old sessions to `archive/` | C | `[x]` |
| C3 | Input validation on CLI arguments and JSON payloads | C | `[x]` |
| C4 | Structured error responses (consistent JSON errors from API) | C | `[x]` |
| C5 | Security hardening — path traversal checks, safe deserialization | C | `[x]` |
| D1 | Session index file for fast lookup without scanning all files | D | `[x]` |
| D2 | Search / filter in web dashboard | D | `[x]` |
| D3 | Session detail view in web dashboard | D | `[x]` |
| D4 | Export (JSON / Markdown) of session history | D | `[x]` |
| D5 | Optional desktop notifications for stale sessions | D | `[x]` |

**Legend:** `[x]` done · `[~]` in progress · `[ ]` todo

> All phases (A–D) are complete. Detailed descriptions have been archived to
> [`docs/ROADMAP-HISTORY.md`](docs/ROADMAP-HISTORY.md).

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
