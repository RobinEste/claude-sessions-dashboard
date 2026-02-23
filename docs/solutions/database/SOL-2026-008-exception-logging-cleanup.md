# SOL-2026-008: Exceptions geabsorbeerd zonder logging in cleanup

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v2
- **Finding ID:** PYT-002
- **Severity:** P2
- **Category:** database

## Probleem
In `cleanup_stale_sessions` ving een `except Exception: continue` alle fouten op zonder enige vorm van logging. Bij geautomatiseerde uitvoering (via launchd) waren fouten volledig onzichtbaar, waardoor stale sessies nooit opgeruimd werden zonder dat iemand het merkte.

## Oplossing
`logger.warning(...)` toegevoegd in het except-blok met `session.session_id` en de exception details. De `continue` blijft behouden zodat een fout bij een sessie de verwerking van andere sessies niet blokkeert.

## Patroon
**Geabsorbeerde exceptions moeten altijd gelogd worden.** Wanneer een `except` blok bewust `continue` of `pass` gebruikt om door te gaan, moet er minimaal een `logger.warning` zijn met voldoende context (ID, operatie, exception). Zoek bij reviews naar bare `except: continue/pass` zonder logging.

## Code voorbeeld

### Voor (probleem)
```python
for session in stale:
    try:
        # ... cleanup logic ...
        _save_session(session)
    except Exception:
        continue  # Fout volledig onzichtbaar!
```

### Na (fix)
```python
for session in stale:
    try:
        # ... cleanup logic ...
        _save_session(fresh)
    except Exception as exc:
        logger.warning(
            "Failed to close stale session %s: %s", session.session_id, exc
        )
        continue
```

## Gerelateerde bestanden
- `lib/store.py`
