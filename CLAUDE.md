# Claude Sessions Dashboard — Dev Conventions

## Project overview

File-based session tracker and web dashboard for Claude Code.
Core has zero external dependencies; web dashboard uses FastAPI + uvicorn.

## Directory structure

```
manage.py          # CLI entry point (_dispatch handles all commands)
lib/
  models.py        # Dataclasses + StrEnum (Session, ProjectState, etc.)
  store.py         # CRUD on JSON files, atomic writes, fcntl locking
web/
  app.py           # FastAPI routes (/api/overview, /api/session/{id})
  dashboard.html   # Single-page vanilla JS dashboard
tests/
  test_models.py   # 22 tests — serialization, ID generation
  test_store.py    # 65 tests — CRUD, locking, tasks, stale cleanup
  test_cli.py      # 34 tests — _dispatch() + subprocess JSON output
  test_web.py      # 9 tests — FastAPI TestClient
```

## Commands

```bash
# Run tests
pytest

# Lint
ruff check .

# Start web dashboard
python manage.py serve

# CLI example
python manage.py create-session --project my-proj --intent "Build feature"
```

## Code conventions

- **Python >= 3.13** (uses StrEnum, type unions with `|`)
- **No external deps** in `lib/` — stdlib only
- **Atomic writes**: all JSON saves go through `tempfile.mkstemp` + `os.replace`
- **File locking**: `fcntl.flock` for session read-modify-write cycles
- **Test isolation**: monkeypatch `store.DASHBOARD_DIR`, `SESSIONS_DIR`, `PROJECTS_DIR`, `CONFIG_PATH` to `tmp_path`
- **No mocking** of the JSON store — tests use real file I/O

## Git workflow

- Commit messages in Dutch, conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`
- Push after local tests + ruff pass
- CI runs on push to main and on PRs

## Adding a new CLI command

1. Add subparser in `manage.py` (around line 80-140)
2. Add handler in `_dispatch()` (around line 160-300)
3. Add store function in `lib/store.py` if needed
4. Add tests in `test_cli.py` (via `_dispatch(ns(...))`) and `test_store.py`

## Adding a new API route

1. Add route in `web/app.py`
2. Add tests in `test_web.py` using `TestClient`
