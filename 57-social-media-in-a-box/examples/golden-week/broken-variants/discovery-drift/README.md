# Broken variant — discovery-drift (AF-SM-DISCOVERY-DRIFT)

**C2 live connected-accounts discovery (merge plan C2/R8).** The fixture's discovery probe shows
the client's GHL location has a live-connected **twitter** account, but the config `platforms`
enum is only `["facebook", "instagram"]` and no `platformsExcluded` entry logs a deliberate skip.

That is the **BANNED silent-miss** a fixed enum causes — the exact failure Skill 35 hardened
against: a channel the client actually connected being silently skipped by the weekly run.

Expected: `preflight_gate.py` exits **2** with `AF-SM-DISCOVERY-DRIFT` (fail-closed; run blocked).
The fix is either adding `twitter` to `platforms` or recording the client's explicit choice in
`platformsExcluded` — the client's choice is FINAL, and visible, never silent.

```
python3 scripts/preflight_gate.py examples/golden-week/broken-variants/discovery-drift/config.json
```
