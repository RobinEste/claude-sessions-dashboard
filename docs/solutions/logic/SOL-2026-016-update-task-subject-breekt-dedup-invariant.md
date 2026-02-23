# SOL-2026-016: update_task subject-rename breekt dedup-invariant van add_tasks

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v4
- **Finding ID:** LOG-001
- **Severity:** MEDIUM (P2)
- **Category:** logic

## Probleem
`add_tasks` dedupliceert op subject zodat er nooit twee taken met hetzelfde onderwerp bestaan.
`update_task` kon echter een subject overschrijven naar een waarde die al in gebruik was door een
andere taak. Dit brak de dedup-invariant stil: de check in `add_tasks` herkende het duplicaat
niet meer en kon er later een tweede taak met hetzelfde subject aanmaken.

## Oplossing
Dedup-check toegevoegd in `update_task` vóórdat het subject wordt overschreven: bouw een set
van bestaande subjects (exclusief de taak zelf) en gooi een `ValueError` als het nieuwe subject
al voorkomt.

## Patroon
**Wanneer een collectie een uniekheids-invariant heeft (deduplicatie op een veld), moet elke
mutatieoperatie op dat veld dezelfde invariant afdwingen.** Controleer bij het toevoegen van
een update-functie altijd of er een gelijksoortige check in de create/add-variant bestaat en
kopieer die logica. Een `ValueError` is de juiste reactie op een invariant-schending.

## Code voorbeeld

### Voor (probleem)
```python
for task in session.tasks:
    if task["id"] == task_id:
        task["status"] = status
        task["updated_at"] = _now_iso()
        if subject is not None:
            task["subject"] = subject  # geen dedup-check!
        ...
```

### Na (fix)
```python
for task in session.tasks:
    if task["id"] == task_id:
        task["status"] = status
        task["updated_at"] = _now_iso()
        if subject is not None:
            existing = {t["subject"] for t in session.tasks if t["id"] != task_id}
            if subject in existing:
                raise ValueError(
                    f"Task subject '{subject}' already exists in session {session_id}"
                )
            task["subject"] = subject
        ...
```

## Gerelateerde bestanden
- `lib/store.py` — functies `add_tasks` (dedup-bron) en `update_task` (fix, regel ~282–290)
