# SOL-2026-015: resume_session mist _session_lock — TOCTOU race bij concurrent resume

## Metadata
- **Datum:** 2026-02-23
- **Review ID:** review-2026-02-23-0c9c47-v4
- **Finding ID:** ASD-001
- **Severity:** HIGH (P1)
- **Category:** database / concurrency

## Probleem
`resume_session` voerde een read-modify-write cyclus uit op twee sessies (old + new) zonder
file lock. Bij gelijktijdige aanroepen kon dezelfde geparkeerde sessie meerdere keren hervat
worden, wat resulteert in twee actieve sessies die allebei claimen voort te komen uit dezelfde
parent.

## Oplossing
De volledige body van `resume_session` gewrapped in `with _session_lock(session_id):`.
Daarbinnen: lees old-sessie, maak new-sessie, sla both op. De lock beschermt de atomaire
read-check-create-write volgorde.

## Patroon
**Elke functie die een sessie leest en daarna muteert (read-modify-write) moet gewrapped zijn
in `_session_lock(session_id)`.** Controleer bij een nieuwe mutatiefunctie altijd of de lock
aanwezig is. Dit geldt ook voor functies die meerdere sessies raken (zoals resume, waarbij zowel
old als new worden geschreven) — gebruik de lock van de primaire/input sessie-ID.

## Code voorbeeld

### Voor (probleem)
```python
def resume_session(session_id: str, new_intent: str | None = None) -> Session:
    old = get_session(session_id)
    if not old:
        raise ValueError(f"Session {session_id} not found")

    intent = new_intent or old.intent
    new_session = create_session(...)
    new_session.open_questions = old.open_questions
    _save_session(new_session)

    old.status = SessionStatus.COMPLETED
    old.outcome = f"Resumed as {new_session.session_id}"
    old.ended_at = _now_iso()
    _save_session(old)
```

### Na (fix)
```python
def resume_session(session_id: str, new_intent: str | None = None) -> Session:
    with _session_lock(session_id):
        old = get_session(session_id)
        if not old:
            raise ValueError(f"Session {session_id} not found")

        intent = new_intent or old.intent
        new_session = create_session(...)
        new_session.open_questions = old.open_questions
        _save_session(new_session)

        old.status = SessionStatus.COMPLETED
        old.outcome = f"Resumed as {new_session.session_id}"
        old.ended_at = _now_iso()
        _save_session(old)
```

## Gerelateerde bestanden
- `lib/store.py` — functie `resume_session` (regel ~450)
