# The 4-Tier Model (in depth)

Skill 40 retrieves public records through four tiers, tried in strict order. The
design goal: maximize coverage for the common cases while NEVER fabricating data
for the cases we cannot serve.

## Tier 1 — Curated county scrapers

For the highest-population counties, Skill 40 ships a curated config per county
(`references/tier1-counties/<slug>.json`). Each config carries:

- `slug`, `county_fips`, `state` — routing identity
- `portal_url`, `search_path` — where to query
- `platform` — the records platform vendor (links to a Tier-2 adapter when one
  exists), or `custom` for a bespoke portal
- `tos_url` — the target's Terms of Service (operator must acknowledge)
- `record_types` — which of {ownership, deeds, tax, tax_delinquency, permits,
  pre_foreclosure, NOD} the portal exposes
- `selectors` — the result selectors used to extract records

**Honest status:** the configs ship the routing + record-type map + selector
contract. They are NOT a guarantee that every selector is live-valid on install
day — county portals change markup. `05-validate-target.sh` dry-probes a target
(robots + ToS + liveness) before live use, and a stale selector surfaces as a
Tier-4 honest gap, never as fabricated data.

## Tier 2 — Platform-adapter framework

Many counties run their records/court portals on a small number of platform
VENDORS. Instead of one config per county, Tier 2 has one ADAPTER per vendor, so
every county on that vendor reuses the adapter (parameterized by the county's
portal URL). Skill 40 ships the framework + two example adapters:

- `references/tier2-adapters/tyler-technologies.md`
- `references/tier2-adapters/govos-landmark.md`

A Tier-1 config's `platform` field names the vendor; the router uses the matching
adapter. Adding a vendor = adding one adapter doc + wiring it in the
county-platform map.

## Tier 3 — Operator-buildable config

When a county is not in Tier 1 and not on a known Tier-2 vendor, the operator can
build a Tier-3 config: portal URL + search-form fields + result selectors. The
`06-build-tier3-config.sh` builder writes the config from
`templates/tier3-config.template.json` and then VALIDATES it
(`05-validate-target.sh --tier3`) — robots + ToS + liveness — before it can be
used live. An invalid config is treated as a Tier-4 honest gap.

## Tier 4 — Honest gap

When no tier can serve a query — no online database, the county can't be
resolved, or the target blocks/disallows automated access — the answer is the
honest gap. Skill 40 tells the operator plainly and stops. It NEVER invents a
record. The honest gap is logged (`honest_gap`) so the operator sees exactly what
could not be served.
