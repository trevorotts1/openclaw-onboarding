# Changelog - Skill 40: ZHC Public Records Scraper

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
