# U22 / B-U8 — LIVE-PROOF tier RE-PROOF, operator-box run — 2026-07-19

This is the dated operator-box receipt for the U22 LIVE-PROOF tier run that
FLIPS the U22 ledger row. The 2026-07-16 run (`u22-live-tier-proof-2026-07-16/`,
branch `proof/u22-live-capstone`) was landed as-committed in the previous merge
commit; per the "paper feeds paper" doctrine its claims were NOT trusted — this
run re-executed both paid legs fresh, live, against current mains, on the
operator's own box, before the row was flipped.

Repo heads at run time (both fetched fresh from origin into scratch clones,
never `~/openclaw-onboarding` or `~/command-center/app`):
- `openclaw-onboarding` `origin/main`: `0324bd807a2ebc4ce2a47bc224c607d36653f8e0`
  (pre-#654; the run is code-identical on the #654 merge commit — #654 touched
  only S58/podcast + ledger surfaces, no Skill-6 persona module)
- `blackceo-command-center` `origin/main`: `fe736ee7a04ac19fdfff2ff84cd2b343d62e40a1`
  (tag `v6.0.59` ancestry confirmed)

## 1. B-U8's OWN criterion (b) — PAID (re-proven)

`06-ghl-install-pages/scripts/prove_skill6_block_u22.py` fresh run:
**23/23 checks PASS, exit 0** (`run-log.txt`). Both scope-gap notices
self-detect `[INFO] ... appears LANDED` (U18 + U21).

Persistent-evidence companion run (same production modules, real on-disk
evidence root) wrote:
- `per-page-blend-receipts.json` — 2/2 pages `guardrail_terminated: true`,
  0 `persona_mismatch`, full `blend_directive_sha256` per page.
- `mismatch-free-card.json` — `receipt_source: "threaded"` (!= absent),
  `fab_qc_d4_score: 10.0`, `fab_qc_overall_passed: true`,
  `persona_mismatch_events: 0`, `mismatch_free: true`, `all_checks_ok: true`.
- `persona-bundle-receipt.json` / `persona-selection-log.md` — the real files
  `persona_bundle_ladder` / `copy_persona_blend_seam` wrote to disk.

**Verdict: PASS.**

## 2. Deferred B-U7/U21 live producer→CC ingest handshake — PAID (re-proven)

`producer-cc-ingest-handshake.json` — a REAL running CC dev server (Next dev,
port 4181, CC main `fe736ee7`) on an isolated scratch `DATABASE_PATH`, fed a
REAL HMAC-signed HTTP POST from the REAL
`06-ghl-install-pages/tools/cc_board.py:ingest_task()` producer.

Isolation proven live, not assumed: the first boot (no auth env) was REFUSED
by the route's own misconfig gate (HTTP 503 `WEBHOOK_SECRET is not set`, then
`MC_API_TOKEN is not set` — CC main has HARDENED since the 7-16 run, which ran
signature-free in dev mode); throwaway scratch auth values were generated for
the run and the producer signed with them. The live `mission-control.db` was
never opened.

- **Producer-pinned case** — task `ff11db0e-beb9-4d2f-8196-9d329b49d9cb`
  (HTTP 201): `voice_persona_id=hormozi-100m-offers`,
  `topic_persona_id=miller-building-storybrand`, `bundle_sha` (sha256 of the
  run's own real bundle receipt) all landed VERBATIM in the `tasks` mirror
  columns AND the real `task_persona_bundle` row
  (`rationale.source: "producer_pinned_ingest"`); **0** `resolvePersonaAndPin`
  log lines for this task — the selector genuinely never spawned.
- **Control case** — task `e5a722f2-72da-4b55-b61f-36fef19c72ee` (HTTP 201, no
  persona fields, SAME live server): the async selector fired as today
  (`[resolvePersonaAndPin] Persona landed ... russell-brunson-lead-funnels`).

**Verdict: PASS.**

## 3. A-U7/U7 + B-U10/U24 live GHL→Vercel legs — STILL OPERATOR-GATED

Unchanged from the 7-16 run: both need a real GHL page → Vercel `VERCEL_EMBED`
deploy against an operator-named sandbox GHL location. No repo doc or ledger
row names one; firing real deploys against guessed targets under the
operator's live accounts is the exact one-way door reserved to the operator.
NOT attempted, NOT faked, NOT silently skipped — still tracked as owed.

## Files
- `run-log.txt` — full stdout: prove run (23/23, exit 0) + persistent run (exit 0).
- `mismatch-free-card.json`, `per-page-blend-receipts.json`,
  `persona-bundle-receipt.json`, `persona-selection-log.md` — criterion (b).
- `producer-cc-ingest-handshake.json` — the B-U7/U21 handshake receipt
  (pinned + control, real server + real DB rows quoted verbatim).
