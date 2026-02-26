# Changelog

Alle noemenswaardige wijzigingen aan dit project worden hier bijgehouden.
Format gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/).

## [Unreleased]

### Toegevoegd
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
- Test suite: 133 tests over models, store, CLI en web (A3–A6)
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
