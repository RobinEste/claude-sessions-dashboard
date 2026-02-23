# SOL-2026-012: update_task() crasht bij niet-bestaande sessie

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v3
- **Finding ID:** LOG-002
- **Severity:** HIGH (P1)
- **Category:** logic

## Probleem
`update_task()` deed geen None-check op het resultaat van `get_session()`. Bij een niet-bestaande sessie crashte de functie met een AttributeError bij het itereren over `session.tasks`. Bovendien stond de `raise ValueError` voor een onbekende task_id buiten de lock.

## Oplossing
Een expliciete `if not session: return None` check is toegevoegd na `get_session()`, binnen het lock-blok. De `raise ValueError` voor een niet-gevonden task staat nu ook binnen de lock, na de volledige iteratie.

## Patroon
Elke functie die `get_session()` aanroept moet het None-geval afhandelen voordat verdere attributen worden benaderd. Dit is een defensief programmeerpatroon: valideer altijd de aanwezigheid van een resource voor je er operaties op uitvoert.

## Code voorbeeld

### Voor (probleem)
```python
def update_task(session_id, task_id, status, subject=None):
    if status not in VALID_TASK_STATUSES:
        raise ValueError(...)
    session = get_session(session_id)
    # Geen None-check -> AttributeError bij session.tasks
    for task in session.tasks:
        ...
```

### Na (fix)
```python
def update_task(session_id, task_id, status, subject=None):
    if status not in VALID_TASK_STATUSES:
        raise ValueError(...)
    with _session_lock(session_id):
        session = get_session(session_id)
        if not session:
            return None
        for task in session.tasks:
            ...
        raise ValueError(f"Task {task_id} not found in session {session_id}")
```

## Gerelateerde bestanden
- `lib/store.py`
