# Core File Updates — Skill 40 (ZHC Public Records Scraper v1.0.0)

Appended to AGENTS.md / MEMORY.md / TOOLS.md by `scripts/07-update-core-files.sh`, each behind a
clearly-named `<!-- BEGIN/END skill-40 ... -->` marker, idempotent, backups written before any edit.

**Versioning:** semver-tagged starting at v1.0.0.

---

## [ADD TO AGENTS.md] — appended by `scripts/07-update-core-files.sh`

Behind `<!-- BEGIN skill-40 public-records v1.0.0 -->` / `<!-- END skill-40 public-records v1.0.0 -->`:

Key behaviors added:
- **Tiered retrieval** — for any public-records query, auto-detect county+state, then route Tier 1 → Tier 2 → Tier 3 → else Tier 4 (honest gap). NEVER fabricate a record; no source → say so.
- **Compliance first** — check robots.txt before any fetch; honor each target's ToS (`tos_url` acknowledged); stamp every record with `source` + `retrieved_at`. A disallowed target or unattributed result → honest gap.
- **Cost + rate caps** — respect `PR_DAILY_CAP`, the per-target rate limit, and require an operator-confirmed cost estimate for any bulk op above `PR_BULK_CONFIRM_THRESHOLD`.
- **30-day cache** — serve fresh cache hits free; `--force-refresh` to bypass for one query.
- **RE pairing** — surface pre-foreclosure/NOD, tax-delinquency, comps, permits, tax, ownership records for Skill 39; Skill 40 never runs outreach itself.
- **Event log** — append one line to `<MASTER_FILES_DIR>/public-records-queries.jsonl` for every query, cache hit, tier decision, cost estimate, rate-limit wait, compliance block, and honest gap (record TYPES + counts only, never raw record contents).

## [ADD TO MEMORY.md] — appended by `scripts/07-update-core-files.sh`

Behind `<!-- BEGIN skill-40 memory-rules v1.0.0 -->` / `<!-- END skill-40 memory-rules v1.0.0 -->`:

Public-records design rules:
1. **No-Fabrication Rule** — never invent a record; no source → Tier 4 honest gap. A record without `source` + `retrieved_at` is not a record.
2. **Compliance Rule** — robots.txt is binding; each target's ToS must be acknowledged; every record is attributed. Disallowed → honest gap, never an override.
3. **Cost-Cap Rule** — per-day cap + per-target rate limit are binding; bulk ops require an up-front cost estimate + operator confirm. No silent bulk runs.
4. **Cache Rule** — 30-day cache; cache key is a hash of (target + query), never a raw address as a filename.
5. **Stay-In-Lane Rule** — Skill 40 finds + attributes + caches + logs records; it never runs outreach (that's Skill 39).
6. **Permissible-Use Rule** — the operator owns lawful, permissible-purpose use (FCRA/DPPA/state limits); the skill surfaces the reminder, it does not give legal advice.
7. **Event-Log Rule** — every action appends one line to public-records-queries.jsonl (types + counts + status, never raw record contents).

## [ADD TO TOOLS.md] — appended by `scripts/07-update-core-files.sh`

Behind `<!-- BEGIN skill-40 tools v1.0.0 -->` / `<!-- END skill-40 tools v1.0.0 -->`:

Skill 40 libraries (UNIVERSAL; no keys, no client data):
- `scripts/lib-records.sh query "<address-or-zip>" "<record-type>" [--force-refresh]` — the tiered router (compliance + cache + honest gap).
- `scripts/lib-cost-cap.sh` — cost estimate + per-day + per-target rate guard (bulk confirm).
- `scripts/lib-pr-events.sh pr_event <type> <json>` — append one line to public-records-queries.jsonl.
Caps (env): PR_DAILY_CAP, PR_PER_TARGET_MIN_INTERVAL_S, PR_BULK_CONFIRM_THRESHOLD, PR_COST_PER_QUERY, PR_CACHE_TTL_DAYS.

## What does NOT get touched

- Skill 39 — Skill 40 only PRODUCES records for it; it never edits Skill 39.
- Operator's SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md — only AGENTS.md, MEMORY.md, and TOOLS.md are appended to, behind clear markers, with backups first.
