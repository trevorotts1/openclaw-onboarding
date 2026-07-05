# Changelog - Skill 40: ZHC Public Records Scraper

## [1.1.0] - 2026-07-05 - Enforcement-not-description: wire the compliance + cost gates into query()

Merge-train **T-40-public-records-scraper** (Wave-0). The tiered router documented caps + compliance
but never executed them in the query path; this release makes every claimed gate a real, tested code
path. Changes are scoped entirely to `40-zhc-public-records-scraper/`.

### Fixed
- **Caps now bite (FIX-S36-12):** `query()` invokes `estimate` (logs `cost_estimate`), `rate_wait`
  (per-target min interval, logs `rate_limit_wait`), and `record_query` (increments today's counter) at
  the real fetch call site — previously `record_query`/`rate_wait` were defined but called by nothing, so
  the counter file never existed and the 200/day cap could never block.
- **Compliance is in the execution path (FIX-S36-13):** `query()` itself now gates a live fetch on
  `robots_ok` passing, a **persisted per-target ToS acknowledgement** (`ack_tos`/`tos_ack_present`), and
  attribution — emitting `compliance_block` (`robots_disallow` / `tos_unacknowledged` / `unattributed`)
  instead of the events being emitted by zero code.
- **Tier 2/3 routing is real (FIX-S36-14):** `tier()` iterates the executable adapters in
  `scripts/adapters/*.sh` (`--covers`) on a Tier-1 miss, then an operator Tier-3 config, before falling
  to Tier-4. `scripts/adapters/` + `lib-command-center.sh` documented in the SKILL.md files table.
- **Validation gate exists (FIX-S36-15):** a Tier-1 config is servable only when `validated:true` AND its
  `portal_url`/`tos_url` are non-placeholder; `validated:false` or a placeholder URL falls through,
  forcing `05-validate-target.sh` (all 21 shipped configs ship `validated:false`).
- **Cache write path (FIX-S36-16):** new attribution-gated `cache_put` helper (refuses a record missing
  `source`+`retrieved_at`) is the sole cache writer, so `cache_hit` is reachable and never fabricated.
- **CC integration + robots wildcards (FIX-S36-17):** added `scripts/lib-command-center.sh` — Skill 41's
  fail-soft, health-gated Kanban helper (silent no-op when the Command Center is down, never fatal); and
  replaced the literal robots matcher (`Disallow: /*` never matched) with a wildcard-safe matcher that
  fails CLOSED on any unevaluable wildcard.
- **Persisted-state cache dir, no Downloads fallback (FIX-XC-10c):** `_cache_dir` in both `lib-records.sh`
  and `lib-cost-cap.sh` resolves `MASTER_FILES_DIR` from env → persisted `~/.openclaw` selection, and
  FAILS LOUD (fail-closed on the cap) if unresolved, instead of silently using `~/Downloads` and handing a
  fresh caller a zero-count cap.
- **Behavioral compliance QC (FIX-XC-03e):** `qc-compliance.sh` rewritten from comment-greps to behavioral
  assertions against a mock target — asserts a disallowed-robots path blocks, a placeholder `tos_url` is
  rejected and non-servable, a persisted ToS-ack is required, and a record missing `source`/`retrieved_at`
  is refused.

## [1.0.1] - 2026-05-30 - Round-3 canonical reconciliation: add executable Tier-2 adapters + F52 contract

Aligns Skill 40 with the canonical Round-3 decision (this repo's build is the canonical base; the
sibling VPS repo's named capabilities are merged IN). Additive only — this repo's richer build
(qc-compliance + qc-no-fabrication gates, cost-cap + cache protocols, per-county JSON configs, helper
libs) is unchanged.

### Added
- `scripts/adapters/govos-landmark.sh` + `scripts/adapters/tyler-technologies.sh` — the executable
  Tier-2 vendor adapter shells (from the sibling repo) alongside the existing adapter DOCS under
  `references/tier2-adapters/`, so the adapters are runnable, not just documented.
- `references/master-files-event-contract-F52.md` — the F52 event-contract reference doc (from the
  sibling repo).
- Tier-1 county UNION reconcile: added 3 curated per-county configs —
  `references/tier1-counties/san-bernardino-county-ca.json` (FIPS 06071),
  `hillsborough-county-fl.json` (FIPS 12057), `pierce-county-wa.json` (FIPS 53053). The shipped
  Tier-1 set is now **21** counties (was 18), matching the sibling VPS repo's curated set exactly.
  SKILL.md county list + count updated accordingly.

### Fixed
- **Single log contract (no internal contradiction):** rewrote
  `references/master-files-event-contract-F52.md` to document the canonical PII-free event schema
  (opaque `query_ref`/`target_ref`; event enum `cache_init`/`tier_decision`/`cache_hit`/`force_refresh`/
  `query`/`compliance_block`/`cost_estimate`/`cost_block`/`rate_limit_wait`/`honest_gap`) so it matches
  `INSTRUCTIONS.md`, `SKILL.md`, and `templates/public-records-queries.schema.json`. It previously
  documented the OLD `records_query` event that embedded a raw input `address`/`zip` — that PII-bearing
  schema is removed. There is now exactly ONE log contract in the skill.
- `install.sh` `install_skill_40_*` now `chmod +x`'s `scripts/adapters/*.sh` as well as `scripts/*.sh`
  (the v1.0.1 executable Tier-2 adapters were not being made executable on install).

## [1.0.0] - 2026-05-30 - Initial release

First release of the tiered, compliance-first public-records intelligence layer. The data SIBLING of
Skill 39 (Real Estate Playbook): Skill 40 finds + attributes + caches + logs records; Skill 39 runs the
outreach. The skill NEVER fabricates a record.

### The 4-tier model
- **Tier 1** — curated scraper configs for 18 major counties (Cook IL, Los Angeles CA, Maricopa AZ,
  Harris TX, San Diego CA, Orange CA, Miami-Dade FL, Kings NY, Dallas TX, King WA, Clark NV, Santa Clara
  CA, Tarrant TX, Riverside CA, Wayne MI, Broward FL, Bexar TX, Sacramento CA). Each ships routing
  metadata + record-type map + selector contract; live retrieval is gated on the operator accepting the
  target's robots/ToS and running the validator (`05-validate-target.sh`) — a stale selector surfaces as
  a Tier-4 honest gap, never as fabricated data.
- **Tier 2** — a platform-adapter FRAMEWORK (one adapter per records-platform vendor) + two example
  adapters: Tyler Technologies and GovOS/Landmark.
- **Tier 3** — an operator-buildable scraper CONFIG schema (`templates/tier3-config.template.json`) + an
  interactive builder (`06-build-tier3-config.sh`) that VALIDATES the config (robots + selectors
  dry-probe) before any live run.
- **Tier 4** — HONEST GAP: when nothing can serve a query (no online DB / county unresolved / target
  blocked), tell the operator; never fabricate.

### Auto-detect routing + controls
- `scripts/lib-records.sh` router: address/ZIP → county+state → Tier 1 → Tier 2 → Tier 3 → else Tier 4.
- 30-day cache at `<MASTER_FILES_DIR>/public-records-cache/` (cache key = hash(target+query); `--force-refresh`).
- Cost cap + per-day cap + per-target rate limit (`scripts/lib-cost-cap.sh`); bulk ops above the confirm
  threshold print an up-front cost+time estimate and WAIT for operator confirmation.

### Compliance (enforced, not advisory)
- robots.txt checked before any fetch (disallow → honest gap).
- ToS reference per target (`tos_url` acknowledged).
- Every record stamped `source` + `retrieved_at`; unattributed results are refused.
- `scripts/qc-compliance.sh` machine-enforces robots-respected + ToS-referenced + attribution-required.

### RE use cases (prioritized)
- Pre-foreclosure/NOD, tax delinquency, comps support, permits, tax records, ownership/deeds
  (`references/real-estate-use-cases.md`). Surfaced for Skill 39; Skill 40 never runs outreach.

### F52 event contract
- `<MASTER_FILES_DIR>/public-records-queries.jsonl` append-only event log (`scripts/lib-pr-events.sh`),
  machine-readable schema at `templates/public-records-queries.schema.json`. Records record TYPES +
  counts + cache/cost/compliance status and opaque handles, never raw record contents. Schema documented
  in INSTRUCTIONS.md.

### Quality
- UNIVERSAL: zero client/personal data; machine-enforced by `scripts/qc-no-personal-data.sh`.
- No-fabrication floor machine-enforced by `scripts/qc-no-fabrication.sh`.
- Governed by `../QC-PROTOCOL.md` (8.5 threshold, 10-category rubric).
- Registered in `install.sh` (`install_skill_40_zhc_public_records_scraper`) + the README skill catalog.
