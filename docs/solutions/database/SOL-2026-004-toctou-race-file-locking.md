# SOL-2026-004: TOCTOU race in read-modify-write zonder file locking

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v2
- **Finding ID:** ASD-001
- **Severity:** P1
- **Category:** database

## Probleem
Alle mutatie-functies (`add_tasks`, `add_event`, `add_commit`, etc.) volgden het patroon: (1) `get_session` (read), (2) muteer in-memory, (3) `_save_session` (write). Er was geen locking tussen stap 1 en 3. Bij gelijktijdige writes overschreef de laatste `_save_session` de wijzigingen van de eerste volledig (TOCTOU race condition).

## Oplossing
Een `_session_lock()` context manager geintroduceerd die `fcntl.flock` (exclusive lock) gebruikt op een dedicated `.lock` bestand per sessie. Alle read-modify-write operaties zijn gewrapped in `with _session_lock(session_id):`.

## Patroon
**Elke read-modify-write cyclus op gedeelde state moet beschermd worden met een exclusieve lock.** Bij file-based storage is `fcntl.flock` op een apart lockbestand het standaardpatroon. Zoek bij reviews naar functies die eerst lezen, dan muteren, dan schrijven zonder tussenliggende lock.

## Code voorbeeld

### Voor (probleem)
```python
def add_event(session_id: str, message: str) -> Session | None:
    session = get_session(session_id)
    if not session:
        return None
    session.events.append({"timestamp": _now_iso(), "message": message})
    session.last_heartbeat = _now_iso()
    _save_session(session)
    return session
```

### Na (fix)
```python
@contextmanager
def _session_lock(session_id: str):
    """Acquire an exclusive file lock for a session's read-modify-write cycle."""
    _ensure_dirs()
    lock_path = SESSIONS_DIR / f"{session_id}.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

def add_event(session_id: str, message: str) -> Session | None:
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None
        session.events.append({"timestamp": _now_iso(), "message": message})
        session.last_heartbeat = _now_iso()
        _save_session(session)
        return session
```

## Gerelateerde bestanden
- `lib/store.py`
