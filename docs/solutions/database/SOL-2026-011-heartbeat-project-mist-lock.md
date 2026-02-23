# SOL-2026-011: heartbeat_project mist _session_lock

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** ASD-003
- **Severity:** MEDIUM (P2)
- **Category:** database

## Probleem
De bulk-variant `heartbeat_project` schreef direct naar sessies zonder lock, terwijl de enkelvoudige `heartbeat()` wel gelockt was. Dit maakte de lock-strategie inconsistent: directe heartbeats waren veilig, maar bulk-heartbeats niet.

## Oplossing
In plaats van de lock-logica te dupliceren, delegeert `heartbeat_project` nu naar de al gelocked `heartbeat()` functie per sessie. Dit voorkomt duplicatie en garandeert consistente locking.

## Patroon
Wanneer een bulk-operatie dezelfde mutaties uitvoert als een enkelvoudige operatie, delegeer dan naar de enkelvoudige (gelocked) variant in plaats van de logica te kopieren. Dit voorkomt dat de bulk-variant per ongeluk een lock overslaat.

## Code voorbeeld

### Voor (probleem)
```python
def heartbeat_project(project_slug: str) -> list[Session]:
    updated = []
    for session in get_active_sessions(project_slug):
        session.last_heartbeat = _now_iso()
        _save_session(session)
        updated.append(session)
    return updated
```

### Na (fix)
```python
def heartbeat_project(project_slug: str) -> list[Session]:
    updated = []
    for session in get_active_sessions(project_slug):
        result = heartbeat(session.session_id)
        if result:
            updated.append(result)
    return updated
```

## Gerelateerde bestanden
- `lib/store.py`
