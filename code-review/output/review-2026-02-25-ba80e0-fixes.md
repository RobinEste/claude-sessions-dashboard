# Code Review — 2026-02-25 (fixes)

## Samenvatting

| Aspect | Waarde |
|--------|--------|
| **Verdict** | changes_requested |
| **Risk Score** | 35/100 (Matig) |
| **Bestanden** | 1 gereviewed |
| **Bevindingen** | 4 (gefilterd van 8) |
| **Agents** | security-sentinel, logic-correctness, async-data-integrity, python-specialist, performance-reviewer |

## Vereist menselijke beoordeling

### MERGED-001 (HIGH) — OPGELOST
**archive_old_sessions archiveert actieve sessie: status-hercontrole ontbreekt binnen lock**
- Bestand: `lib/store.py:738-743`
- Agents: security-sentinel, logic-correctness, python-specialist, async-data-integrity
- Status: **Opgelost** — sessiedata wordt nu opnieuw geladen en status hervalideerd binnen het lock-blok (SOL-2026-004 patroon)

### ASD-002 (MEDIUM) — OPGELOST
**Lock-bestand verwijderd buiten _session_lock veroorzaakt gebroken locking-invariant**
- Bestand: `lib/store.py:689-691`
- Agent: async-data-integrity
- Status: **Opgelost** — `lock.unlink()` verplaatst naar binnen het `with _session_lock` blok in beide functies

## Overige bevindingen

### PYT-002 (MEDIUM) — OPGELOST
**KeyError op data["session_id"] breekt volledige archive_old_sessions-iteratie bij corrupt bestand**
- Bestand: `lib/store.py:731`
- Agent: python-specialist
- Status: **Opgelost** — `data.get("session_id")` met `continue` bij ontbrekend veld

### PRF-001 (MEDIUM) — Open
**Migratie wordt herhaald op elke list_sessions-aanroep zonder persistentie**
- Bestand: `lib/store.py:566`
- Agent: performance-reviewer
- Status: **Niet toegepast** — performance-impact is minimaal, write-back in read-pad introduceert nieuw risico
