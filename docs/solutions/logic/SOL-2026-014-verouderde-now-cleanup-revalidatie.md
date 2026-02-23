# SOL-2026-014: Verouderde `now` in cleanup revalidatie

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** LOG-003
- **Severity:** MEDIUM (P2)
- **Category:** logic

## Probleem
In `cleanup_stale_sessions()` werd de `now`-variabele eenmalig bepaald voor de loop. Bij langlopende cleanup-runs (veel sessies, trage I/O) kon de verouderde timestamp leiden tot false positives: sessies die intussen een heartbeat hadden ontvangen werden toch als stale gemarkeerd.

## Oplossing
De timestamp wordt nu per iteratie ververst met `current_now = datetime.now(timezone.utc)`, zodat elke staleness-check de actuele tijd gebruikt.

## Patroon
In loops die over tijd heen draaien en time-based beslissingen nemen, moet de huidige tijd per iteratie worden bepaald, niet eenmalig voor de loop. Dit is vooral kritiek bij cleanup/reaper-taken die potentieel lang kunnen duren.

## Code voorbeeld

### Voor (probleem)
```python
def cleanup_stale_sessions(threshold_hours):
    now = datetime.now(timezone.utc)
    for session in stale:
        hb = datetime.fromisoformat(session.last_heartbeat)
        if (now - hb).total_seconds() / 3600 > threshold_hours:
            # close session
```

### Na (fix)
```python
def cleanup_stale_sessions(threshold_hours):
    for session in stale:
        with _session_lock(session.session_id):
            fresh = get_session(session.session_id)
            hb = datetime.fromisoformat(fresh.last_heartbeat)
            current_now = datetime.now(timezone.utc)
            if (current_now - hb).total_seconds() / 3600 > threshold_hours:
                # close session
```

## Gerelateerde bestanden
- `lib/store.py`
