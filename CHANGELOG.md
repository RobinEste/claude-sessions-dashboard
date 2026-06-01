# Changelog

Alle noemenswaardige wijzigingen aan dit project worden hier bijgehouden.
Format gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/).

## [Unreleased]

### Toegevoegd
- **`worktree_root`-veld op sessies** (schema v3): `create_session()` + `manage.py create-session` accepteren `--worktree-root` (absolute git work-tree root, `rev-parse --show-toplevel`) en persisteren die per sessie. Maakt robuuste gedeelde-checkout-detectie in `/sessie-start` mogelijk (exacte work-tree i.p.v. mapnaam-heuristiek) — ccf #120 Fase 2. Veld is peer van `git_branch`: meegedragen bij `resume_session` + geëxposeerd in de overview-API. Back-compat via `_migrate_session_data` (v2→v3, default `None`) + `.get()`-deserialisatie. +2 tests (v2→v3-migratie, resume-preservatie) + `worktree_root`-asserts in de store/CLI create-session-tests.
- `redact_username()` in `lib/jsonl_reader.py`: redacteert `/Users/<naam>` én de dash-encoded `-Users-<naam>` projectdir-vorm (+ `/home`-varianten) → `[USER]`, geïntegreerd in de export-redactieloop (`manage.py`, naast secrets/PII). Port van `aibuild-lab/agent-conversations-cairn` (claude-code-framework PLAN-2026-031 item E1); alleen delimiter-verankerde patronen overgenomen — de boundary-vorm gaf false-positives op proza. +4 tests.
- System-reminder-strip uit user-turns in de JSONL-reader: `<system-reminder>…</system-reminder>`-blokken worden uit user-content verwijderd (harness-ruis), echte prompt blijft behouden. +1 test.

### Gefixt
- `test_list_sessions` / `test_list_sessions_with_filter` ontbraken `since=None` in de `ns()`-helper (AttributeError sinds commit `79d553f`), en een te lange regel in de list-sessions-handler is gewrapt. `test_cli` weer groen.

> **Bekend issue:** 6 `test_search`-failures (search-ranking) bestaan sinds `79d553f` — getrackt als #3.

## [2.0.0] — 2026-03-07

### Toegevoegd
- Optionele desktop notificaties voor stale en lang-geparkeerde sessies via macOS osascript, met cooldown en state tracking. Opt-in via `notifications_enabled` in config, periodiek draaibaar via launchd (D5)
- Export als JSON of Markdown via CLI (`manage.py export`), API (`/api/export/session/`, `/api/export/project/`) en downloadknoppen in session detail view (D4)
- Session detail view: klik op een sessie voor volledig overzicht met event timeline, tasks, commits, decisions, files en next steps (D3)
- Zoeken en filteren in web dashboard: free-text search, project dropdown, status filters (D2)
- Session index (`_index.json`) voor snelle lookup zonder alle bestanden te scannen (D1)
- Security hardening: symlink check, file size limiet (10MB), slug validatie op alle paden, corrupte JSON overslaan (C5)
- Gestructureerde JSON foutresponses met `{"error", "code"}` format in API (C4)
- Input validatie op CLI-argumenten en store-operaties met `lib/validation.py` (C3)
- Sessie-archivering: voltooide sessies verplaatsen naar `archive/` na N dagen (C2)
- Schema versioning met on-read migratie (`schema_version: 2`) (C1)
- Orphaned lock file cleanup in `cleanup_stale_sessions()` + CLI commando (B3)
- `CLAUDE.md` met projectconventies voor AI-assisted development (B4)
- Ruff linter configuratie in `pyproject.toml` (B5)
- GitHub Actions CI met pytest + ruff, SHA-pinned actions (B1)
- `TaskStatus` StrEnum voor type-safe task statussen (CON-001)
- Session ID validatie tegen path traversal (SEC-001)
- Test suite: 341 tests over models, store, CLI, web, validation, export, notify, search en jsonl_reader (A3–A6 + uitbreidingen)
- `pyproject.toml` met PEP 621 metadata en `[web]`/`[test]` extras (A1)
- `requirements.txt` voor snelle installatie (A2)

### Verbeterd
- `resume_session` lock scope refactored — geen nested locks meer (ASD-001)
- `_session_to_overview_dict` helper vervangt 3 dubbele dict comprehensions (DUP-001)
- None-check na tweede lock-acquisitie in `resume_session` (PYT-001)

### Gefixt
- Defensieve key access voor legacy tasks zonder `subject` veld (LOG-001)
- Validatie-volgorde in `update_task` — check nu voor mutatie (LOG-002)
- Ongebruikte imports en onnodige f-string opgeruimd (ruff)

## [1.1.0] — 2026-02-23

### Toegevoegd
- Task tracking per sessie (add, update, batch add, deduplicatie)
- Auto-cleanup van stale sessies (> 24u zonder heartbeat)
- Concurrency hardening met `fcntl.flock` en atomic writes
- Kennisbank met 5 architectuur-inzichten uit code review
- Roadmap met 4 fases naar projectvolwassenheid

### Verbeterd
- README bijgewerkt met nieuwe features

## [1.0.0] — 2026-02-11

### Toegevoegd
- Session CRUD: create, update, complete, park, resume
- Events, commits en decisions per sessie
- Heartbeat mechanisme voor activiteitsdetectie
- Multi-project ondersteuning met project registratie
- Project state tracking (fase, roadmap voortgang)
- Web dashboard met live overzicht (FastAPI + vanilla JS)
- CLI via `manage.py` met JSON output
- `launchd` auto-start configuratie
- Data pipeline en UI verbeteringen
