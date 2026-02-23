# SOL-2026-001: Race condition op task-ID generatie

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** ASD-001
- **Finding ID:** ASD-001
- **Severity:** high
- **Category:** database

## Probleem
`add_task` en `add_tasks` berekenden het volgende ID via `max(int(t['id'][1:]) for t in session.tasks)`. Bij parallelle aanroepen lezen beide functies dezelfde max-waarde, genereren ze hetzelfde ID en overschrijven ze elkaars taak (ID-collision en dataverlies).

## Oplossing
De incrementele max-ID berekening vervangen door `secrets.token_hex(4)` in een aparte `_generate_task_id()` helper. Cryptografisch sterke random IDs maken ID-collision statistisch verwaarloosbaar zonder dat coördinatie tussen threads/processen nodig is.

## Patroon
**Vermijd sequentiële IDs die berekend worden op basis van de huidige toestand** in code die parallel of concurrent aangeroepen kan worden. Gebruik in plaats daarvan UUIDs of cryptografisch willekeurige tokens die geen globale toestand of locking vereisen.

## Code voorbeeld

### Voor (probleem)
```python
def add_tasks(session_id: str, subjects: list[str]) -> Session | None:
    max_id = max((int(t['id'][1:]) for t in session.tasks), default=0)
    for i, subject in enumerate(subjects):
        session.tasks.append({
            "id": f"t{max_id + i + 1}",
            ...
        })
```

### Na (fix)
```python
import secrets

def _generate_task_id() -> str:
    """Generate a collision-resistant task ID."""
    return f"t{secrets.token_hex(4)}"

def add_task(session_id: str, subject: str) -> Session | None:
    """Append a task to the session. Deduplicates on subject."""
    return add_tasks(session_id, [subject])

def add_tasks(session_id: str, subjects: list[str]) -> Session | None:
    session.tasks.append({
        "id": _generate_task_id(),
        ...
    })
```

## Gerelateerde bestanden
- `lib/store.py`
