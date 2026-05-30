# Skill 40 — ZHC Public Records Scraper: Install Guide

## What this installs

A TIERED, compliance-first public-records intelligence layer:

- **Tier 1** — curated scraper configs for 18 major counties (routing metadata + record-type map + selector contract; live retrieval gated on operator ToS/robots acceptance + the validator).
- **Tier 2** — a platform-adapter FRAMEWORK (one adapter per records-platform vendor) + two example adapters (Tyler Technologies, GovOS/Landmark).
- **Tier 3** — an operator-buildable scraper CONFIG schema + an interactive builder that VALIDATES the config (robots + selectors dry-probe) before any live run.
- **Tier 4** — HONEST GAP behavior: when nothing can serve a query, tell the operator; never fabricate.
- **Auto-detect routing**, a **30-day cache**, **cost cap + per-day + per-target rate limits** (with up-front bulk cost estimate + operator confirm), and an enforced **compliance posture** (robots respected, ToS referenced per target, source + timestamp attribution).
- A `public-records-queries.jsonl` append-only event log per the F52 master-files contract.

## Prerequisites

This skill REFUSES to proceed until the mandatory prerequisites pass (`00-verify-prerequisites.sh`).

1. **`MASTER_FILES_DIR`** — resolvable (Skill 38/39 persist it). The cache + event log live there.
2. **`jq`** on PATH — config + event JSON parsing.
3. **`curl`** on PATH — robots.txt check + target fetches.

Recommended / optional:
- **Skill 39 (Real Estate Playbook)** — consumes Skill 40 output for pre-foreclosure outreach.
- **Headless browser (Playwright/Chromium)** — for JS-rendered portals; static fetch handles the rest.

## What this does NOT do

- Does NOT fabricate records — no source → Tier 4 honest gap.
- Does NOT run outreach (that's Skill 39).
- Does NOT bypass robots.txt or a target's ToS — a disallowed target is an honest gap.
- Does NOT run bulk ops without an operator-confirmed cost estimate.
- Does NOT give legal advice on permissible use; the operator owns lawful use (FCRA/DPPA/state limits).

## Install order (run in this order; each is idempotent)

```bash
cd ~/.openclaw/skills/40-zhc-public-records-scraper/scripts

./00-verify-prerequisites.sh      # MASTER_FILES_DIR, jq, curl; Skill 39 + browser report
./01-locate-master-files-folder.sh# reuse Skill 38/39 MASTER_FILES_DIR selection (or resolve it)
./02-init-cache.sh                # 30-day cache dir + public-records-queries.jsonl + schema sidecar
./03-load-tier1-counties.sh       # validate + index the shipped Tier-1 county configs
./04-configure-caps.sh            # record cost/rate/cache caps (env-overridable); honest summary
# Per-target, before any live run:
./05-validate-target.sh <slug>    # dry-probe a Tier-1/Tier-3 target (robots + selectors) BEFORE live
./06-build-tier3-config.sh        # (optional) build + validate an operator Tier-3 scraper config
./07-update-core-files.sh         # AGENTS.md / MEMORY.md / TOOLS.md pointers (idempotent markers)
```

## Cost / rate / cache caps (env-overridable)

| Env var | Default | Meaning |
|---|---|---|
| `PR_DAILY_CAP` | 200 | Global queries per day |
| `PR_PER_TARGET_MIN_INTERVAL_S` | 5 | Minimum seconds between requests to the same target |
| `PR_BULK_CONFIRM_THRESHOLD` | 25 | Batch size above which a cost estimate + operator confirm is required |
| `PR_COST_PER_QUERY` | 0.00 | Estimated cost per query for paid targets |
| `PR_CACHE_TTL_DAYS` | 30 | Cache time-to-live |

## OS support

`darwin` (Mac mini operators) and `linux` (VPS operators). Scripts detect OS via `uname -s`:
- **Darwin:** `$HOME/.openclaw/skills`
- **Linux:** `/data/.openclaw/skills`

## QC gates shipped with this skill

```bash
bash scripts/qc-no-personal-data.sh   # UNIVERSAL: zero client/personal identifiers
bash scripts/qc-no-fabrication.sh     # router returns Tier-4 honest gap (never invented records) on a miss
bash scripts/qc-compliance.sh         # robots respected, ToS referenced per target, attribution required
```

All three must PASS before the skill is considered installed cleanly (per `../QC-PROTOCOL.md` Rule 5).

## Where to read next

- `INSTRUCTIONS.md` — runtime routing, caching, caps, compliance + the JSONL schema
- `references/tier-model.md` — the 4-tier architecture in depth
- `references/county-platform-map.md` — county → platform → tier mapping
- `references/real-estate-use-cases.md` — prioritized RE use cases
