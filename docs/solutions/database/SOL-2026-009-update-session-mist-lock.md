# SOL-2026-009: update_session mist _session_lock

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** ASD-001
- **Severity:** HIGH (P1)
- **Category:** database

## Probleem
De functie `update_session` voerde een read-modify-write cyclus uit (get_session, setattr, _save_session) zonder exclusieve lock. Alle andere schrijffuncties waren wel voorzien van `_session_lock`, waardoor een inconsistente lock-strategie ontstond met race conditions bij parallelle schrijfacties.

## Oplossing
De gehele body van `update_session` is gewrapt in `with _session_lock(session_id):`, zodat get, modify en save atomair verlopen.

## Patroon
Elke functie die een read-modify-write cyclus uitvoert op gedeelde state moet onder dezelfde lock vallen. Controleer bij het toevoegen van nieuwe schrijffuncties altijd of de lock consistent is toegepast.

## Code voorbeeld

### Voor (probleem)
```python
def update_session(session_id: str, **kwargs) -> Session | None:
    session = get_session(session_id)
    if not session:
        return None
    for key, value in kwargs.items():
        if hasattr(session, key):
            setattr(session, key, value)
    _save_session(session)
    return session
```

### Na (fix)
```python
def update_session(session_id: str, **kwargs) -> Session | None:
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        _save_session(session)
        return session
```

## Gerelateerde bestanden
- `lib/store.py`
