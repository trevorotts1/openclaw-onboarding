# Skill 40 — Public Records Scraper: design rules (canonical deep reference)

> **This file is the CANONICAL, FULL text of Skill 40's design rules.**
> It is a Teach-Yourself-Protocol DEEP FILE and is **never** pasted into a box's
> `MEMORY.md`. `scripts/07-update-core-files.sh` writes exactly ONE compact
> pointer block into `MEMORY.md` (marker `<!-- BEGIN skill-40 memory-rules -->`)
> that points here.
>
> **Why:** core bootstrap files are re-billed to the model on every single turn,
> so rule corpora live in deep files and core files carry pointers only (TYP).
> Per-rule enforcement detail lives in `protocols/*.md` and `references/*.md`.

---

## Public-records design rules

1. **No-Fabrication Rule** — never invent a record; no source → Tier 4 honest gap.
   A record without `source` + `retrieved_at` is not a record.
   See `protocols/tier-routing-protocol.md`, `scripts/qc-no-fabrication.sh`.
2. **Compliance Rule** — robots.txt is binding; each target's ToS must be
   acknowledged; every record is attributed. Disallowed → honest gap, never an
   override. See `protocols/compliance-protocol.md`, `scripts/qc-compliance.sh`.
3. **Cost-Cap Rule** — per-day cap + per-target rate limit are binding; bulk ops
   require an up-front cost estimate + operator confirm. No silent bulk runs.
   See `protocols/cost-cap-protocol.md`, `scripts/lib-cost-cap.sh`.
4. **Cache Rule** — 30-day cache; the cache key is a hash of (target + query),
   never a raw address as a filename. See `protocols/cache-protocol.md`.
5. **Stay-In-Lane Rule** — Skill 40 finds + attributes + caches + logs records; it
   never runs outreach (that is Skill 39).
   See `references/real-estate-use-cases.md`.
6. **Permissible-Use Rule** — the operator owns lawful, permissible-purpose use
   (FCRA / DPPA / state limits); the skill surfaces the reminder, it does not give
   legal advice. See `protocols/compliance-protocol.md`.
7. **Event-Log Rule** — every action appends one line to
   `public-records-queries.jsonl` (types + counts + status, never raw record
   contents). See `references/master-files-event-contract-F52.md`.
