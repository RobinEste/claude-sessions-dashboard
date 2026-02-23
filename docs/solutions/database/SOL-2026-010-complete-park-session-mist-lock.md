# SOL-2026-010: complete_session en park_session missen _session_lock

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** ASD-002
- **Severity:** HIGH (P1)
- **Category:** database

## Probleem
De functies `complete_session` en `park_session` voerden status-transities uit (lezen, muteren, opslaan) zonder exclusieve lock. Een race met `cleanup_stale_sessions` kon leiden tot een willekeurige eindtoestand, omdat beide functies dezelfde sessie tegelijk konden overschrijven.

## Oplossing
Beide functies zijn gewrapt in `with _session_lock(session_id):`. De `_refresh_project_state()` call staat bewust buiten de lock om deadlocks te voorkomen.

## Patroon
Status-transities (ACTIVE naar COMPLETED/PARKED) zijn kritieke momenten die altijd atomair moeten verlopen. Wanneer meerdere codepaden dezelfde state-transitie kunnen triggeren (handmatig en automatisch), is een lock essentieel.

## Code voorbeeld

### Voor (probleem)
```python
def complete_session(session_id, outcome, ...):
    session = get_session(session_id)
    if not session:
        return None
    session.status = SessionStatus.COMPLETED
    session.ended_at = _now_iso()
    _save_session(session)
    _refresh_project_state(session.project_slug)
    return session
```

### Na (fix)
```python
def complete_session(session_id, outcome, ...):
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None
        session.status = SessionStatus.COMPLETED
        session.ended_at = _now_iso()
        _save_session(session)
    _refresh_project_state(session.project_slug)
    return session
```

## Gerelateerde bestanden
- `lib/store.py`
