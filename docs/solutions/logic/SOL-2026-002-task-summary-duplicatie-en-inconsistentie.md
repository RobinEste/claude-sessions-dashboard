# SOL-2026-002: task_summary inconsistentie en code duplicatie

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** LOG-001
- **Finding ID:** LOG-001-DUP-001
- **Severity:** medium
- **Category:** logic

## Probleem
`task_summary.total` telde alle tasks inclusief `skipped`, maar de overige velden (`completed + in_progress + pending`) sloten `skipped` uit. Hierdoor klopte de optelling niet. Bovenop dit data-integriteitsprobleem was hetzelfde summary-blok driemaal gedupliceerd in `build_overview()`.

## Oplossing
Geëxtraheerd naar een `_task_summary()` helper die alle statussen expliciet telt (`completed`, `in_progress`, `pending`, `skipped`). De drie duplicaten zijn vervangen door één aanroep van de helper.

## Patroon
Wanneer een dict met telwaarden op meerdere plekken wordt opgebouwd: extraheer naar een helper. Zorg dat `total` altijd gelijk is aan de som van alle afzonderlijke status-velden, zodat consumers van de data kunnen vertrouwen op interne consistentie.

## Code voorbeeld

### Voor (probleem)
```python
# Driemaal gedupliceerd in build_overview(), skipped ontbreekt
"task_summary": {
    "total": len(tasks),
    "completed": sum(1 for t in tasks if t.get("status") == "completed"),
    "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
    "pending": sum(1 for t in tasks if t.get("status") == "pending"),
    # skipped ontbreekt → total != completed + in_progress + pending
}
```

### Na (fix)
```python
def _task_summary(tasks: list[dict]) -> dict:
    """Build task status summary for API output."""
    return {
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t.get("status") == "completed"),
        "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
        "skipped": sum(1 for t in tasks if t.get("status") == "skipped"),
    }

# Gebruik (één aanroep vervangt drie duplicaten)
"task_summary": _task_summary(s.tasks),
```

## Gerelateerde bestanden
- `lib/models.py`
