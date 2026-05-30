# Skill 40: ZHC Public Records Scraper

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file) — overview, the 4-tier model, honest real-vs-stub status
2. INSTALL.md — one-time setup: prerequisites + the numbered install scripts (`00`–`07`) + cost/rate caps
3. INSTRUCTIONS.md — runtime guide: auto-detect routing, caching, cost-cap + rate limits, compliance, the `public-records-queries.jsonl` schema
4. CORE_UPDATES.md — what gets appended to AGENTS.md + MEMORY.md + TOOLS.md
5. EXAMPLES.md — worked example queries (UNIVERSAL placeholders, honest gaps shown)
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.

## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See `QC-PROTOCOL.md` Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 40 is the public-records intelligence layer** — a TIERED, compliance-first system that resolves an address/ZIP to a county+state and retrieves public records (ownership, tax, deeds, permits, and — prioritized for real estate — pre-foreclosure / Notice-of-Default and tax-delinquency). It is the data SIBLING of Skill 39 (Real Estate Playbook): Skill 40 finds the records; Skill 39 runs the outreach. Skill 40 NEVER runs outreach and NEVER fabricates a record.

## The 4-tier model (the core architecture)

Auto-detection routes every query through the tiers in order: **address/ZIP → county+state → Tier 1? → Tier 2? → Tier 3? → else Tier 4 (honest gap).**

| Tier | What it is | Status |
|---|---|---|
| **Tier 1** | Curated scrapers for major counties — a config + selectors per county, validated before live use | REAL (config + framework) for the shipped counties below; live retrieval is gated on the operator accepting each target's ToS + robots |
| **Tier 2** | Platform-adapter FRAMEWORK — one adapter per records-platform VENDOR (e.g. Tyler Technologies), so any county on that vendor reuses the adapter | REAL framework + example adapters; vendor specifics are operator-confirmed |
| **Tier 3** | Operator-buildable scraper CONFIG — the operator supplies URL + search-form fields + result selectors; the skill VALIDATES the config (a dry probe) before any live run | REAL (config schema + validator) |
| **Tier 4** | HONEST GAP — no online database, or the target blocks automated access | REAL behavior: tell the operator the honest gap; NEVER fabricate a record |

### Tier 1 counties shipped (curated configs)

A curated set of 21 major-population counties spanning the largest metros. Each ships a Tier-1 config (`references/tier1-counties/<slug>.json`) with the portal URL, the platform it runs on (which links it to a Tier-2 adapter where applicable), the record types available, and the result selectors:

1. Cook County, IL (Chicago)
2. Los Angeles County, CA
3. Maricopa County, AZ (Phoenix)
4. Harris County, TX (Houston)
5. San Diego County, CA
6. Orange County, CA
7. Miami-Dade County, FL
8. Kings County, NY (Brooklyn)
9. Dallas County, TX
10. King County, WA (Seattle)
11. Clark County, NV (Las Vegas)
12. Santa Clara County, CA (San Jose)
13. Tarrant County, TX (Fort Worth)
14. Riverside County, CA
15. Wayne County, MI (Detroit)
16. Broward County, FL
17. Bexar County, TX (San Antonio)
18. Sacramento County, CA
19. San Bernardino County, CA
20. Hillsborough County, FL (Tampa)
21. Pierce County, WA (Tacoma)

> **Honest status note:** the Tier-1 configs ship the routing metadata, record-type map, and selector contract for each county. Live retrieval requires the operator to (a) accept the target's robots.txt + ToS and (b) run the Tier-1 config validator (`05-validate-target.sh`) against the live portal — county portals change their markup, and a stale selector must surface as a Tier-4 honest gap, never as fabricated data. The configs are the curated starting point; they are NOT a promise that every selector is live-valid on install day.

### Tier 2 example adapters shipped

- **Tyler Technologies** (`references/tier2-adapters/tyler-technologies.md`) — the platform behind many county records/court portals; one adapter, many counties.
- **One additional example adapter** (`references/tier2-adapters/govos-landmark.md`) — a second vendor framework to prove the pattern.

## What This Skill Does NOT Do

- Does NOT fabricate records. No owner, deed, lien, NOD, tax balance, or permit is ever invented. No source → Tier 4 honest gap.
- Does NOT run outreach. Pre-foreclosure / distressed-owner outreach is Skill 39's job; Skill 40 only surfaces the records.
- Does NOT bypass robots.txt or a target's ToS. Compliance is enforced (see below); a disallowed target is a Tier-4 honest gap.
- Does NOT run bulk operations without an explicit operator-confirmed cost estimate.
- Does NOT store or transmit PII beyond what the operator's lawful use requires; the event log records counts + cache status, never raw record contents.
- Does NOT provide legal advice on permissible use; the operator is responsible for lawful, permissible-purpose use of public records (FCRA/DPPA/state restrictions where applicable).

## Compliance posture (enforced, not advisory)

- **robots.txt respected** — every target is checked against its robots.txt before any fetch; disallowed → Tier-4 honest gap.
- **ToS reference per target** — each Tier-1 config + Tier-3 config carries a `tos_url` the operator must acknowledge.
- **Attribution** — every retrieved record is stamped with `source` + `retrieved_at` (timestamp). A record with no provenance is not a record.
- **Rate + cost limits** — per-day cap, per-target rate limit, and a global cost cap; bulk ops require an up-front cost estimate the operator confirms.

## Cost & rate controls (default caps)

| Control | Default | Env override |
|---|---|---|
| Global daily query cap | 200 | `PR_DAILY_CAP` |
| Per-target rate limit | 1 request / 5s | `PR_PER_TARGET_MIN_INTERVAL_S` |
| Bulk-op confirm threshold | 25 queries | `PR_BULK_CONFIRM_THRESHOLD` |
| Estimated cost per query (paid targets) | $0.00 default | `PR_COST_PER_QUERY` |
| Cache TTL | 30 days | `PR_CACHE_TTL_DAYS` |

Before any bulk op above the confirm threshold, the skill prints an estimate (query count × per-query cost + time at the rate limit) and WAITS for operator confirmation.

## 30-day cache

Results cache at `<MASTER_FILES_DIR>/public-records-cache/` for `PR_CACHE_TTL_DAYS` (default 30). A cache hit is free + instant and is logged as `cache_hit`. `--force-refresh` bypasses the cache for a single query. The cache key is a hash of (normalized target + query) — no raw address is used as a filename.

## The `public-records-queries.jsonl` contract (F52)

Skill 40 emits one append-only JSONL event log at `<MASTER_FILES_DIR>/public-records-queries.jsonl` per the F52 master-files event contract. Every query, cache hit, tier decision, cost estimate, rate-limit wait, compliance block, and honest gap appends exactly one line. The schema is documented in INSTRUCTIONS.md → "public-records-queries.jsonl schema" and emitted by `scripts/lib-pr-events.sh`. The log records record TYPES + counts + cache/cost status, never raw record contents — it is the operator's ground truth.

## Prerequisites

| Prerequisite | Required | Why |
|---|---|---|
| `MASTER_FILES_DIR` resolvable | MANDATORY | The cache + event log live there |
| `jq` on PATH | MANDATORY | Config + event JSON parsing |
| `curl` on PATH | MANDATORY | robots.txt check + target fetches |
| Skill 39 (Real Estate Playbook) | RECOMMENDED | Consumes Skill 40 output for pre-foreclosure outreach |
| A headless browser (Playwright/Chromium) | OPTIONAL | Some Tier-1/2 portals are JS-rendered; static fetch handles the rest |

## Files in This Folder

| File | Purpose |
|---|---|
| `SKILL.md` | You are here — 4-tier model, county list, compliance, F52 contract |
| `INSTALL.md` | One-time setup: prerequisites, numbered scripts `00`–`07`, caps |
| `INSTRUCTIONS.md` | Runtime: auto-detect routing, caching, caps, compliance, JSONL schema |
| `CORE_UPDATES.md` | Lines appended to AGENTS.md / MEMORY.md / TOOLS.md |
| `EXAMPLES.md` | Worked example queries (UNIVERSAL placeholders, honest gaps shown) |
| `CHANGELOG.md` | Version history |
| `skill-version.txt` | Currently `1.0.1` |
| `scripts/00-verify-prerequisites.sh` | MASTER_FILES_DIR, jq, curl; reports Skill 39 + browser presence |
| `scripts/01-locate-master-files-folder.sh` | Resolves + persists MASTER_FILES_DIR (reuses Skill 38/39 selection) |
| `scripts/02-init-cache.sh` | Creates the 30-day cache dir + the event log + schema sidecar |
| `scripts/03-load-tier1-counties.sh` | Validates + indexes the shipped Tier-1 county configs |
| `scripts/04-configure-caps.sh` | Records the cost/rate/cache caps (env-overridable); honest summary |
| `scripts/05-validate-target.sh` | Dry-probe validator for a Tier-1/Tier-3 target (robots + selectors) BEFORE live |
| `scripts/06-build-tier3-config.sh` | Interactive builder for an operator Tier-3 scraper config (validated) |
| `scripts/07-update-core-files.sh` | Appends AGENTS.md / MEMORY.md / TOOLS.md pointers (idempotent markers) |
| `scripts/lib-records.sh` | The router: detect county/state, tier selection, robots check, cache, fetch, honest gap |
| `scripts/lib-pr-events.sh` | Append-one-line helper for `public-records-queries.jsonl` |
| `scripts/lib-cost-cap.sh` | Cost estimate + per-day + per-target rate-limit guard (bulk confirm) |
| `scripts/qc-no-personal-data.sh` | UNIVERSAL-skill identifier gate (zero client/personal data) |
| `scripts/qc-no-fabrication.sh` | Asserts the router returns Tier-4 honest gap (never invented records) on a miss |
| `scripts/qc-compliance.sh` | Asserts robots respected, ToS referenced per target, attribution required |
| `protocols/tier-routing-protocol.md` | The auto-detect tier-selection runtime |
| `protocols/compliance-protocol.md` | robots/ToS/attribution/permissible-use enforcement |
| `protocols/cost-cap-protocol.md` | Cost estimate + caps + bulk confirmation runtime |
| `protocols/cache-protocol.md` | 30-day cache + force-refresh runtime |
| `references/tier-model.md` | The 4-tier architecture in depth |
| `references/county-platform-map.md` | County → platform → tier mapping reference |
| `references/tier1-counties/*.json` | The shipped Tier-1 curated county configs |
| `references/tier2-adapters/*.md` | The Tier-2 platform-adapter framework + example adapters |
| `references/real-estate-use-cases.md` | Prioritized RE use cases (pre-foreclosure/NOD, tax delinquency, comps, permits, tax, ownership) |
| `templates/tier3-config.template.json` | Operator-buildable Tier-3 scraper config schema |
| `templates/public-records-queries.schema.json` | The JSONL event schema (machine-readable) |

## Security & honesty note

The skill is UNIVERSAL: no client name, business, address, or location id in the source — `scripts/qc-no-personal-data.sh` enforces it. The no-fabrication floor is machine-enforced by `scripts/qc-no-fabrication.sh`, and the compliance posture by `scripts/qc-compliance.sh`. The operator is responsible for lawful, permissible-purpose use of any retrieved public record.

## Support

- INSTRUCTIONS.md — runtime
- INSTALL.md — one-time setup
- CHANGELOG.md — version history
- https://docs.openclaw.ai — platform docs
