# SOL-2026-006: last_heartbeat niet gesynchroniseerd bij cleanup

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v2
- **Finding ID:** ASD-003
- **Severity:** P2
- **Category:** database

## Probleem
Alle reguliere write-operaties (`heartbeat`, `add_event`, `add_commit`, etc.) updaten `session.last_heartbeat` voor `_save_session`. De `cleanup_stale_sessions` functie deed dit niet: het zette wel `ended_at` maar liet `last_heartbeat` op de oude stale waarde staan. Dit resulteerde in inconsistente data waar `ended_at` recenter was dan `last_heartbeat`.

## Oplossing
In de cleanup-functie wordt nu `fresh.last_heartbeat = ended` gezet op hetzelfde moment als `fresh.ended_at = ended`, zodat beide timestamps consistent zijn.

## Patroon
**Bij het afsluiten of muteren van een record: synchroniseer alle gerelateerde timestamps.** Wanneer een entiteit meerdere tijdgerelateerde velden heeft, moeten ze allemaal consistent bijgewerkt worden. Zoek bij reviews naar write-paden die sommige timestamps wel en andere niet bijwerken.

## Code voorbeeld

### Voor (probleem)
```python
# cleanup_stale_sessions
session.status = SessionStatus.COMPLETED
session.ended_at = _now_iso()
session.outcome = "Automatisch afgesloten (stale)"
_save_session(session)
# last_heartbeat blijft op oude stale waarde!
```

### Na (fix)
```python
ended = _now_iso()
fresh.status = SessionStatus.COMPLETED
fresh.ended_at = ended
fresh.last_heartbeat = ended  # Sync met ended_at
fresh.outcome = "Automatisch afgesloten (stale — geen heartbeat)"
_save_session(fresh)
```

## Gerelateerde bestanden
- `lib/store.py`
