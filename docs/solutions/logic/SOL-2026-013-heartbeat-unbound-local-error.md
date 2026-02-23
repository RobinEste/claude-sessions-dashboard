# SOL-2026-013: heartbeat() kan UnboundLocalError gooien

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** LOG-001
- **Severity:** MEDIUM (P2)
- **Category:** logic

## Probleem
In `heartbeat()` werd de variabele `session` alleen gedefinieerd binnen het `with`-block. Als `get_session()` None retourneerde, werd de if-body overgeslagen, maar `return session` buiten het block verwees naar een ongedefinieerde variabele, wat een `UnboundLocalError` veroorzaakte.

## Oplossing
De variabele `session` wordt nu geinitialiseerd met `session = None` voor het `with`-block. Hierdoor is de return-waarde altijd gedefinieerd, ongeacht het pad door de functie.

## Patroon
Wanneer een variabele conditioneel wordt geassigned binnen een block (with, try, if) maar onvoorwaardelijk wordt gebruikt na dat block, moet de variabele vooraf geinitialiseerd worden. Dit voorkomt UnboundLocalError op alle codepaden.

## Code voorbeeld

### Voor (probleem)
```python
def heartbeat(session_id: str) -> Session | None:
    session = get_session(session_id)
    if session and session.status == SessionStatus.ACTIVE:
        session.last_heartbeat = _now_iso()
        _save_session(session)
    return session
```

### Na (fix)
```python
def heartbeat(session_id: str) -> Session | None:
    session = None
    with _session_lock(session_id):
        session = get_session(session_id)
        if session and session.status == SessionStatus.ACTIVE:
            session.last_heartbeat = _now_iso()
            _save_session(session)
    return session
```

## Gerelateerde bestanden
- `lib/store.py`
