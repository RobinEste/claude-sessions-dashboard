# SOL-2026-007: Geen status validatie in update_task

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v2
- **Finding ID:** PYT-001
- **Severity:** P2
- **Category:** database

## Probleem
De `update_task` functie accepteerde elke willekeurige string als `status` parameter zonder validatie. Een directe aanroep met een ongeldige waarde (bijv. `"donee"` of `""`) schreef corrupte data naar disk, die vervolgens door de hele applicatie heen propageerde.

## Oplossing
Een `VALID_TASK_STATUSES` set gedefinieerd met de toegestane waarden (`pending`, `in_progress`, `completed`, `skipped`). Bij entree van `update_task` wordt gevalideerd of de status in deze set zit, en anders een `ValueError` geraised met een duidelijke foutmelding.

## Patroon
**Valideer enum-achtige parameters aan de service-laag grens.** Wanneer een functie een string-parameter accepteert die slechts een beperkt aantal waarden mag hebben, definieer een constante set met toegestane waarden en valideer bij entree. Vertrouw niet op de aanroeper.

## Code voorbeeld

### Voor (probleem)
```python
def update_task(session_id: str, task_id: str, status: str) -> Session | None:
    # Geen validatie — elke string wordt geaccepteerd
    for task in session.tasks:
        if task["id"] == task_id:
            task["status"] = status  # Kan corrupte data zijn
            _save_session(session)
```

### Na (fix)
```python
VALID_TASK_STATUSES = {"pending", "in_progress", "completed", "skipped"}

def update_task(session_id: str, task_id: str, status: str, subject=None):
    if status not in VALID_TASK_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(VALID_TASK_STATUSES)}"
        )
    with _session_lock(session_id):
        session = get_session(session_id)
        for task in session.tasks:
            if task["id"] == task_id:
                task["status"] = status
                _save_session(session)
```

## Gerelateerde bestanden
- `lib/store.py`
- `manage.py`
