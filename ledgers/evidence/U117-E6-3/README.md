# U117 (E6-3/G9) — comms-artifact QC + per-part-governance / audience-prompt conformance invariant — evidence

Unit: U117 (P1, both — this evidence covers the ONB (`openclaw-onboarding`)
leg only). Implements ADD-3, folding ADD-1 (U115) + ADD-2 (U116) into the
quality gates and the D1/FAB-QC conformance invariant: per-part governance
and the comms audience prompt are made FIRST-CLASS in the QC layer — SCORED
and ENFORCED, never merely documented. Deps: U25/B-U11 (`shared-utils/
page_qc.py`, the semantic scorer this unit extends — VERIFIED merged), U19/
B-U5 (`shared-utils/fab_qc.py`'s bundle-aware voice-grounding D4 — VERIFIED
merged), U26/B-U12 (the QC-contract fix — VERIFIED merged, `blackceo-
command-center` repo, out of scope here), U115 (per-part governance —
VERIFIED merged, `670043c5`), U116 (comms audience trigger — VERIFIED
merged, `cef6c474`). D1 RULED (the invariant this unit enforces).

## What this unit builds (ONB leg)

Four ADDITIONAL checks specific to an outside-world COMMUNICATION artifact
(U116's five `comms_type`s: page, blog, email, sms, social), additive /
flag-gated behind `COMMS_QC_CONFORMANCE=1` (unset = byte-identical no-op,
this unit's own `revert:` clause):

1. **`shared-utils/page_qc.py`** — the four checks + the public entry point:
   - `check_part_governance(inp)` — **C1, per-part persona governance**
     (extends U115): the artifact's `part_id` must be governed by ITS OWN
     assigned blend, read from U115's `routing/part-persona-map.json`
     record for that part — never another part's. N/A (never blocks) when
     no per-part context is supplied at all.
   - `check_topic_considered(inp)` — **C2, topic considered**: the topic
     slot (U116's `_derive_topic`/`topic_factored` contract) was populated
     before writing. Deterministic, key-free.
   - `check_audience_confirmed(inp)` — **C3, audience confirmed**:
     `audience_source` recorded `standard`|`specific` (U116's
     `resolve_comms_audience` contract — the ADD-2 prompt having fired).
     Deterministic, key-free.
   - `score_blend_used(inp, judge_fn)` — **C4, blend actually used**: the
     SEMANTIC upgrade of FAB-QC D4 (name-match in a log line) and this
     module's own S3 (general voice/persona fidelity) — the bundle's
     declared voice attributes must trace through into the copy, judged by
     the client's own judge. Reuses `fab_qc.voice_persona_grounded` (see
     below) as a deterministic evidence signal handed to the judge
     alongside the voice attributes — real mechanism reuse, not a second
     independent name-match rule. Returns `None` (SKIP, never a fabricated
     score) with no judge key.
   - `grade_comms_conformance(inp, *, judge_fn=None, env=None)` — the
     public entry point: runs the three deterministic checks (C1/C2/C3)
     ALWAYS, key-free; runs C4 only when a judge is available (a SKIP never
     blocks the other three — the same SKIP-not-fabricate / SKIP-never-
     blocks doctrine `grade()`'s own S1-S6 scorecard already uses).
   - `validate_comms_schema(result)` — structural validator, mirrors
     `validate_schema` for the S1-S6 scorecard.
   - `--comms` CLI flag on `main()` — scores `--inputs`/`--evidence` as a
     comms-conformance check instead of the six-dimension page scorecard.
2. **`shared-utils/fab_qc.py`** — `voice_persona_grounded(text,
   voice_persona_id)` extracted as a standalone reusable predicate from
   `score_d4`'s previously-inlined token-match rule. Pure refactor, ZERO
   behavior change to `score_d4` (proven: the full pre-existing D4
   regression suite — 21/21 — passes unmodified; two new direct tests of
   the extracted helper added). `page_qc.py`'s C4 check now calls this SAME
   predicate rather than re-deriving the match rule a second time.
3. **`scripts/guard-fab-qc-gate.sh`** — new section 10: asserts the four
   checks + the flag + the mechanism-reuse import (`fab_qc.
   voice_persona_grounded`) are present, AND runs a BEHAVIORAL proof (not
   just grep-presence — a residual call-site string would otherwise keep
   matching after a function's `def` is deleted): actually calls each of
   the four check functions with a real fixture and asserts the literal
   ADD-2 regressions ("skip the audience prompt", "skip the topic slot")
   and the U115 "wrong part's blend" regression are all caught live.
4. **`tests/unit/u117-comms-qc-conformance.test.py`** — 26 tests covering
   BINARY acceptance (a), (b), (c), (f) (this repo's leg).
5. **`tests/unit/u117-comms-qc-guard.test.sh`** — the CI mutation-proof
   guard, BINARY acceptance (e): mirrors the established
   `page-qc-gate-guard.test.sh` pattern (copy real files into an isolated
   tmp tree, seed a literal source-code mutation, prove the guard fails,
   restore, prove the guard passes again) — run twice, once per named
   ADD-2 regression (skip audience prompt, skip topic slot), each with its
   own restore-and-repass cycle (4 mutation/restore cases + 1 sanity case,
   5/5 green).
6. **`.github/workflows/funnel-automation-libraries-guard.yml`** — wired
   the new suites in, AND closed a real pre-existing gap found while
   wiring: `shared-utils/page_qc.py` and `tests/unit/page-qc.test.py` /
   `page-qc-gate-guard.test.sh` (U25/B-U11, merged `d177e7e7`) were NEVER
   wired into any CI job — added here alongside U117's own two suites.
7. **`tests/unit/page-qc-gate-guard.test.sh`** — fixed a latent staleness
   bug found in the course of wiring it into CI (item 6): its directory-
   copy list had drifted behind `guard-fab-qc-gate.sh`'s own growth
   (missing `49-signature-funnel/` and `tests/` — the U10 anti-copy-guard
   proof and this unit's own two new proof files), so its own "Case 1:
   unmodified copy -> PASS" sanity check was silently failing even before
   any mutation. Reproducible on the pre-U117 tree via `git stash && bash
   tests/unit/page-qc-gate-guard.test.sh`. Corrected to the derived-from-
   the-guard-script directory union (same derivation `u117-comms-qc-
   guard.test.sh` uses); re-verified 2/2 green.
8. **`tests/unit/fab-qc.test.py`** — two new direct tests of the extracted
   `voice_persona_grounded` helper (item 2).

## BINARY acceptance — ONB leg

- (a) a comms fixture whose part is written under the WRONG part's blend
  hard-misses the per-part-governance check; a correctly-governed part
  passes — PROVEN (`TestPerPartGovernance`, 6/6).
- (b) a comms fixture with the topic un-factored hard-misses the topic-
  considered check — PROVEN (`TestTopicConsidered`, 4/4).
- (c) a comms fixture with no recorded audience decision hard-misses the
  audience-confirmed check; one recording `audience_source=standard|
  specific` passes — PROVEN (`TestAudienceConfirmed`, 6/6).
- (d) review->done for a comms source card is refused when any of the four
  checks fails, allowed when all pass + both existing gates pass — **OWED,
  routed to `blackceo-command-center` (the U26 QC-contract train)**, same
  per-repo/offline split A-U5/U115/U116 already established. NOT built or
  faked here. This repo's leg produces the exact `passed`/`checks` scorecard
  shape a CC-side gate reads directly.
- (e) the CI conformance guard FAILS on a scratch-branch mutation skipping
  the audience prompt or the topic slot on a comms path, then passes when
  restored (mutation proof) — PROVEN (`u117-comms-qc-guard.test.sh`, 5/5:
  sanity + skip-audience-prompt fail/restore + skip-topic-slot
  fail/restore).
- (f) a no-judge-key box SKIPs the semantic checks honestly (no fabricated
  score) while the deterministic checks (audience recorded, topic slot
  populated, part->blend match) still run key-free — PROVEN
  (`TestBlendUsedSemanticAndSkip`, 6/6, incl. the SKIP-never-blocks vs
  SKIP-never-fails distinction: a genuine deterministic hard miss still
  fails the gate with no judge key present).

## Proof commands (all green, run foreground/bounded)

```
python3 -m py_compile shared-utils/fab_qc.py shared-utils/page_qc.py
python3 tests/unit/fab-qc.test.py                       # 23 passed (21 pre-existing + 2 new)
python3 tests/unit/page-qc.test.py                       # 21 passed (0 regressions)
python3 tests/unit/u117-comms-qc-conformance.test.py     # 26 passed
bash scripts/guard-fab-qc-gate.sh                        # PASSED
bash tests/unit/page-qc-gate-guard.test.sh                # 2 passed, 0 failed
bash tests/unit/u117-comms-qc-guard.test.sh               # 5 passed, 0 failed
python3 -m pytest 06-ghl-install-pages/tests/test_funnel_matcher.py \
  06-ghl-install-pages/tests/test_v2_dispatcher.py \
  06-ghl-install-pages/tests/test_prove_skill6_block_u22.py \
  06-ghl-install-pages/tests/test_a_u7_convergence.py \
  06-ghl-install-pages/tests/test_a_u9_exemplar_injection.py \
  44-convert-and-flow-operator/tests/test_automation_matcher.py \
  49-signature-funnel/scripts/test_copy_persona_blend_seam.py -q  # 106 passed, 3 skipped
python3 shared-utils/comms_audience_trigger.py --self-test        # ALL PASSED
python3 23-ai-workforce-blueprint/scripts/test-persona-blend-matcher.py   # 57 passed
python3 23-ai-workforce-blueprint/scripts/test-u115-part-persona-governance.py  # 37 passed
```

## Revert

The four added QC dimensions + the conformance guard are additive behind
`COMMS_QC_CONFORMANCE=1` — unset (default) degrades `grade_comms_
conformance` to a true no-op (`applicable=False`, `checks={}`,
`passed=None`), byte-identical to pre-U117 `page_qc.py` for every existing
caller (proven: `test_flag_off_is_a_true_noop_byte_identical`). Full revert
= flip the flag, then revert the commits; the CI guard reverts
independently by deleting `tests/unit/u117-comms-qc-guard.test.sh` and
section 10 of `scripts/guard-fab-qc-gate.sh`.

## Scope note

Repo/surface for U117 is `both` (ONB + `blackceo-command-center`, two
separate serial merge trains). This build session's mandate is the ONB leg
only. The CC leg (U26 QC-contract review->done refusal wiring, BINARY
acceptance (d)) is OWED on the `blackceo-command-center` train — recorded
above, never silently dropped, same split A-U5/U115/U116 already
established for this exact repo boundary.
