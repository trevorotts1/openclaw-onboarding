# Tier Routing Protocol

The auto-detect tier-selection runtime. Implemented by `scripts/lib-records.sh`.

## The decision flow

```
query (address or ZIP)
   │
   ▼
resolve county + state  ── fail ──►  Tier 4 honest gap (county_unresolved)
   │
   ▼
Tier 1 curated config for this county?  ── yes ──►  use it (after compliance + cache + cost gates)
   │ no
   ▼
Tier 2 known platform vendor adapter for this county?  ── yes ──►  use the vendor adapter
   │ no
   ▼
Tier 3 operator-built + validated config for this target?  ── yes ──►  use it
   │ no
   ▼
Tier 4 — HONEST GAP (no_online_db). Tell the operator. NEVER fabricate.
```

## Rules

- **County resolution** reuses the keyless US Census geocoder (the same source
  Skill 39 uses) to get the county FIPS. From a ZIP, the matched FIPS is used.
  No FIPS → Tier 4 (`county_unresolved`).
- **Tier order is strict.** Try Tier 1, then 2, then 3, then 4. No skipping.
- **Every routing decision** appends a `tier_decision` event with the chosen
  tier, county FIPS, state, and reason.
- **Tier 4 is an answer, not a failure to hide.** The honest gap is logged
  (`honest_gap`) and reported plainly to the operator.
- **No tier ever returns a record without provenance.** See the compliance
  protocol.

## What "config-driven" means

Tier 1 membership is determined by whether a curated config in
`references/tier1-counties/<slug>.json` has a `county_fips` matching the resolved
county. Tier 2 membership is determined by the config's `platform` field linking
to a `references/tier2-adapters/<vendor>.md` adapter. Tier 3 is whatever
validated config the operator built under their master files. This keeps routing
data-driven — adding a county is adding a config, not editing the router.
