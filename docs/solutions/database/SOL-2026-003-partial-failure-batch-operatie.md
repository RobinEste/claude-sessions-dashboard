# SOL-2026-003: Partial failure in batch-operatie laat state permanent inconsistent achter

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** ASD-003
- **Finding ID:** ASD-003
- **Severity:** medium
- **Category:** database

## Probleem
`cleanup_stale_sessions` itereert over stale sessies zonder foutafhandeling per item. Als `_save_session` slaagt maar `_refresh_project_state` een exception gooit, stopt de hele loop. Overgebleven stale sessies worden niet verwerkt en de project-state blijft permanent inconsistent.

## Oplossing
De sessie-loop omgeven met `try/except ... continue` zodat een fout bij één sessie de rest niet blokkeert. `_refresh_project_state` verplaatst naar een aparte loop na de sessie-loop, per uniek project-slug uit een `affected_projects` set. Dit scheidt de twee verantwoordelijkheden en voorkomt dat een state-refresh-fout de cleanup-loop onderbreekt.

## Patroon
**Scheid batch-mutaties van afgeleide state-updates.** Verwerk elk item in een batch met een individuele `try/except/continue`. Verzamel affected keys in een set en voer de afgeleide updates pas uit nadat de batch volledig is doorlopen. Zo is de batch maximaal tolerant voor deelfouten en blijft de state uiteindelijk consistent.

## Code voorbeeld

### Voor (probleem)
```python
def cleanup_stale_sessions(threshold_hours: int | None = None) -> list[Session]:
    stale = get_stale_sessions(threshold_hours)
    cleaned = []
    for session in stale:
        session.status = SessionStatus.COMPLETED
        session.ended_at = _now_iso()
        session.outcome = "Automatisch afgesloten (stale — geen heartbeat)"
        _save_session(session)
        _refresh_project_state(session.project_slug)  # gooit? loop stopt
        cleaned.append(session)
    return cleaned
```

### Na (fix)
```python
def cleanup_stale_sessions(threshold_hours: int | None = None) -> list[Session]:
    stale = get_stale_sessions(threshold_hours)
    cleaned = []
    affected_projects: set[str] = set()
    for session in stale:
        try:
            session.status = SessionStatus.COMPLETED
            session.ended_at = _now_iso()
            session.outcome = "Automatisch afgesloten (stale — geen heartbeat)"
            _save_session(session)
            affected_projects.add(session.project_slug)
            cleaned.append(session)
        except Exception:
            continue
    for slug in affected_projects:
        _refresh_project_state(slug)
    return cleaned
```

## Gerelateerde bestanden
- `lib/store.py`
