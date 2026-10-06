# KIE Live Adapter - Core File Updates

Update ONLY the files listed below. Do not update files marked NO UPDATE NEEDED.

**These updates are PERFORMED by `wire.sh`, not pasted.** `wire.sh` writes each block behind its `<!-- BEGIN/END skill:74-kie-live-adapter:<target> -->` marker, replacing in place, with the skill path resolved to an absolute path on this box, and stamps `<!-- skill:74-kie-live-adapter:core-update-applied -->`. Never paste the instruction text; run `bash wire.sh`.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## KIE Live Adapter (74)
- Pointer only: scripts/kie_live_adapter.py in the skill 74 folder checks KIE's live catalog and schema and can run a job.
- Default mode is shadow: it records drift and never dispatches a paid job. Mode: KIE_LIVE_ADAPTER_MODE off|shadow|active.
- It never picks or changes a model; pinned models (the fleet image pin) win. The caller owns fallback.
- Never copy it into a Presentations deck run directory.
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## KIE Live Adapter (Skill 74)
- python3 <skill 74 folder>/scripts/kie_live_adapter.py health|discover|schema|validate|upload|submit|wait|run|credits|save --json
- Cache and receipts: ~/.openclaw/cache/kie-live-adapter
```

---

## MEMORY.md - NO UPDATE NEEDED

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
