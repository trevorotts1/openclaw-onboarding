# U22 / B-U8 — LIVE-PROOF tier, operator-box run — 2026-07-16

This directory is the dated operator-box receipt for U22's LIVE-PROOF tier
(the CODE-MERGE tier was already merged: ONB `b64c8166` / tag `v20.0.35`,
CC `ae972738` / tag `v6.0.20` — both confirmed ancestors of current
`origin/main` on their repos as of this run). Nothing in this directory
changes production code; it is proof evidence only, on a dedicated branch,
not merged.

Both repos were fetched fresh from `origin/main` into throwaway clones
(never `~/openclaw-onboarding` or `~/command-center/app`) immediately before
this run:
- `openclaw-onboarding` HEAD at run time: `a2c425da5d488b0d00705e26e67a5676da8d8601` (tag `v20.0.60`; `v20.0.35` confirmed ancestor via `git merge-base --is-ancestor`)
- `blackceo-command-center` HEAD at run time: `7fbae0b6a840efe109bc448130487279678cf13a` (tag `v6.0.39`; `v6.0.20` confirmed ancestor via `git merge-base --is-ancestor`)

## 1. B-U8's OWN criterion (b) — PAID

`06-ghl-install-pages/scripts/prove_skill6_block_u22.py` run fresh against
the current merged tree: **23/23 checks PASS, exit 0** (see `run-log.txt`).
Both prerequisite scope-gap notices self-detected as LANDED:
`[INFO] B-U4/U18 (copy_craft_pool) appears LANDED`,
`[INFO] B-U7/U21 (ingest parity) appears LANDED` — the whole block, not a
partial slice.

A second, persistent-evidence run (`persist_u22_proof.py`, same production
modules, same fixture bundle/template, writing to a real on-disk evidence
root instead of a `tempfile.TemporaryDirectory()`) produced the two
artifacts the spec names explicitly:
- `per-page-blend-receipts.json` — 2/2 pages, both `guardrail_terminated:
  true`, both `persona_mismatch: false`.
- `mismatch-free-card.json` — `receipt_source: "threaded"` (!= absent),
  `pages_guardrail_terminated: 2/2`, `persona_mismatch_events: 0`,
  `fab_qc_d4_score: 10.0`, `fab_qc_overall_passed: true`,
  `mismatch_free: true`.
- `persona-bundle-receipt.json` / `persona-selection-log.md` — the real
  on-disk files `persona_bundle_ladder`/`copy_persona_blend_seam` wrote.

**Verdict: PASS.** receipt source != absent — PASS; every page directive
guardrail-terminated — PASS; log voice == bundle voice — PASS; D4 = 10.0 —
PASS; zero `persona_mismatch` events — PASS.

## 2. Deferred proof from B-U7/U21 — PAID

`producer-cc-ingest-handshake.json` — a REAL running CC dev server (port
4177, isolated scratch SQLite DB via `DATABASE_PATH` override — the C8 guard
refused to start without it, confirming the live `mission-control.db` was
never at risk), fed a REAL HTTP POST from the REAL
`openclaw-onboarding/06-ghl-install-pages/tools/cc_board.py:ingest_task()`
producer function.

- **Producer-pinned case** (`voice_persona_id=hormozi-100m-offers`,
  `topic_persona_id=miller-building-storybrand`, `bundle_sha=...`): task
  `2127953f-50c1-4a90-9bb9-5ddeb25c03a5` created (HTTP 201); `tasks` row and
  the real `task_persona_bundle` row (written by production
  `persistPersonaBundle()`) both carry the producer's ids **verbatim**;
  server log has **0** `resolvePersonaAndPin` lines for this task — the
  selector genuinely never spawned.
- **Control case** (no persona fields, same live server): task
  `ce591bb6-5d99-4a21-b1a3-a4b3e7fe473a` created (HTTP 201); the async
  selector fired exactly as it does today —
  `[resolvePersonaAndPin] Persona landed for task ce591bb6...:
  butow-ultimate-guide-social-media-marketing` — proving the fail-soft
  byte-identical fallback on the SAME live instance, not a separate claim.

**Verdict: PASS.** This is the exact criterion B-U7/U21's own slice deferred
to U22 ("a real producer run emitting the fields into a real CC ingest, the
card pinning them end-to-end with the selector genuinely not spawning").

No CC repository code was changed to produce this proof — it exercises
already-merged production code (`persistPersonaBundle`, `createTaskCore`'s
skip-branch) over a real live HTTP+DB round trip. No client box, no fleet
box, no live/production Command Center instance was touched.

## 3. Deferred proofs from A-U7/U7 and B-U10/U24 — BLOCKED, not attempted

Both remaining deferred items require an actual **live GHL page → Vercel
deploy** (`VERCEL_EMBED` build):
- A-U7/U7: "the live end-to-end funnel build passing the full gate chain
  (live `render_check` + FAB-QC ≥8.5) with the blend consumed."
- B-U10/U24: "an operator-box LIVE VERCEL_EMBED build → `reconcile` exit 0 +
  byte-match against the REAL pushed repo," "a broken-token FAILED-receipt +
  UNAFFECTED live page + `--retry` recovery," "the schedule's first live
  dated log."

**Credential check performed (name/liveness only, no value ever printed):**
`GITHUB_TOKEN` and `VERCEL_TOKEN` in `~/.openclaw/.env` are SET and
independently validated LIVE via read-only whoami calls
(`GET api.github.com/user` → 200, login `trevorotts1`; `GET
api.vercel.com/v2/user` → 200, account `trevor@blackceo.com`).
`GOHIGHLEVEL_API_KEY` is SET but returned `403 Forbidden` on a minimal
read-only validate call — inconclusive on its own (may simply need a
location-scoped endpoint rather than being dead).

**Why this was NOT attempted, stated honestly:** building a genuine
`VERCEL_EMBED` page requires an actual target GoHighLevel **location** to
build against. No CREDENTIALS.md entry, repo doc, or prior ledger row names
a designated "operator's own sandbox GHL location" safe for this kind of
throwaway live-deploy proof. Guessing at a location id and firing a real
page-build + real Vercel deployment + real GitHub repo push without an
operator-confirmed safe target risks creating an unintended public artifact
under the operator's real GitHub/Vercel/GHL accounts (the very tokens above
prove those accounts are real and live, which raises rather than lowers the
stakes of guessing). Per this task's own instruction — "If any acceptance
criterion genuinely cannot be met on this box, do NOT fake it — report
exactly what blocked and why" — this is reported as BLOCKED, not faked and
not silently skipped. It needs one operator decision (name the exact
sandbox GHL location + confirm the Vercel/GitHub destination) before it can
be run for real; nothing else in the repo blocks it — the code paths
(`ghl_vercel.py`, `ghl_github_archive.py`, `ghl_github_reconcile.py`) are
already shipped and were exercised offline (0 failures) at the U24
CODE-MERGE tier.

## Files in this directory
- `run-log.txt` — full stdout of `prove_skill6_block_u22.py` (23/23 PASS) and
  the persistent-evidence wrapper run.
- `mismatch-free-card.json`, `per-page-blend-receipts.json`,
  `persona-bundle-receipt.json`, `persona-selection-log.md` — B-U8's own
  criterion (b) artifacts, real on-disk output of production modules.
- `producer-cc-ingest-handshake.json` — the B-U7/U21 deferred live-proof
  receipt (producer-pinned case + control case, real server + real DB).
