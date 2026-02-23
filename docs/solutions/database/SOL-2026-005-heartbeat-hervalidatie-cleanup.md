# SOL-2026-005: Heartbeat timing window in cleanup sluit actieve sessie

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v2
- **Finding ID:** ASD-002
- **Severity:** P1
- **Category:** database

## Probleem
`cleanup_stale_sessions` haalde eerst een lijst stale sessies op met `get_stale_sessions()`, en itereerde daar vervolgens overheen om ze te sluiten. Tussen het ophalen van de lijst en het daadwerkelijk sluiten kon een sessie een heartbeat sturen. De cleanup overschreef de verse heartbeat met `status=COMPLETED`, waardoor een actief werkende sessie onterecht werd afgesloten.

## Oplossing
Na het acquiren van de session lock wordt de sessie opnieuw geladen (`fresh = get_session(...)`) en opnieuw gecontroleerd of deze nog steeds stale is. Pas als de hervalidatie bevestigt dat de sessie echt stale is, wordt deze gesloten.

## Patroon
**Bij elke deferred-action op state: hervalideer de conditie binnen de lock.** Wanneer je een lijst items ophaalt om te verwerken, kan de state tussen ophalen en verwerken veranderd zijn. Check altijd opnieuw of de actie nog geldig is nadat je de lock hebt verkregen (double-check patroon).

## Code voorbeeld

### Voor (probleem)
```python
def cleanup_stale_sessions():
    stale = get_stale_sessions(threshold_hours)
    for session in stale:
        session.status = SessionStatus.COMPLETED
        session.ended_at = _now_iso()
        _save_session(session)  # Overschrijft eventuele heartbeat!
```

### Na (fix)
```python
def cleanup_stale_sessions(threshold_hours=None):
    stale = get_stale_sessions(threshold_hours)
    for session in stale:
        try:
            with _session_lock(session.session_id):
                # Revalidate: re-read session to check it's still stale
                fresh = get_session(session.session_id)
                if not fresh or fresh.status != SessionStatus.ACTIVE:
                    continue
                hb = datetime.fromisoformat(fresh.last_heartbeat)
                if (now - hb).total_seconds() / 3600 <= threshold_hours:
                    continue
                fresh.status = SessionStatus.COMPLETED
                fresh.ended_at = ended
                fresh.last_heartbeat = ended
                _save_session(fresh)
```

## Gerelateerde bestanden
- `lib/store.py`
