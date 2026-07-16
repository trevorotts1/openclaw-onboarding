# U114 (E5-9, closes G3) — Product-voice-engine local-voice-logic
DECOMMISSION + no-exemption blend-governance conformance — evidence

Unit: U114 (P3, ONB). Implements the D1 binding ruling's ENFORCEMENT half
that U98 adopts. Deps confirmed already merged on `origin/main` before this
build started (verified via `git merge-base --is-ancestor`, never by ledger
prose — the reconciler snapshot at `ledgers/recovery-state.md` currently
shows U98 as `mergedIntoMain: False / pending`, which is STALE; direct git
ancestry is authoritative and shows U98's merge commit `f1ba3fb2` IS an
ancestor of the current `origin/main` HEAD `85996770`):

- **D1** — the binding ruling this unit implements (RULED).
- **U1** — `persona_for_job.py` (the shared seam every governance call
  routes through) — merged, on `origin/main`.
- **U7** — Skill 6 convergence — merged, on `origin/main`.
- **U98** — "Blend GOVERNS the product-voice engines" — merged via
  `f1ba3fb2` ("Merge U98 (E4-1/v1 U28)..."), confirmed an ancestor of the
  current `origin/main` HEAD by direct `git merge-base --is-ancestor`.

## First act (Honesty clause) — the audit, file:line grounded

U98's own evidence (`ledgers/evidence/U98/README.md`) named the exact local
voice authority it reconciled per engine and left the fleet-wide sweep
explicitly to this unit ("a fleet-wide conformance sweep is U114's job, not
duplicated or pre-empted here"; `tone_persona_autopick.py`'s own docstring:
"the decommissioned single-persona call path is retained behind this flag
**until U114's independent-voice-path invariant lands fleet-wide**").

This unit's first act was a direct, end-to-end read of every `*.py` file
under the four named engines' `scripts/` trees (Skill 51: 6 files; Skill 58:
24 files plus `webhook/`/`caf/`/`tests/` subtrees; Skill 54: 11 files; Skill
59: 51 files) plus the shared `tone-writing-core`. Findings, VERIFIED this
pass by direct read (never grep, per the build's own constraint):

| Engine | Sanctioned voice-selection call site | Legacy/revert path restored at flag=0 |
|---|---|---|
| Skill 51 (signature-presentation) | `51-signature-presentation/scripts/blend_voice_governance.py:99-121` (`governed_phase_voice`, U1 seam, `blend=True`) | `director-of-presentations-sops.md`'s pre-existing intake-tone-only rule; raises `LegacyIntakeVoiceRequired` (`blend_voice_governance.py:109-112`) — never a silent fallback |
| Skill 58 (podcast-production-engine) | `58-podcast-production-engine/scripts/blend_voice_governance.py:104-129` (`governed_script_voice`, U1 seam, `blend=True`) | the selected style engine's own `style-engines/*.md` VOICE DNA section (STRUCTURE, hash-pinned); raises `LegacyStyleEngineVoiceRequired` (`blend_voice_governance.py:115-118`) |
| Anthology (Skills 54/59, shared tone-core, consumed by 52/53/54) | `shared-utils/tone-writing-core/tone_persona_autopick.py:90-172` (`autopick_slot`, `blend=True` when governed) | byte-for-byte pre-U98 single-persona (`blend=False`) shape, `governed=False`, no `blend_directive` key — `tone_persona_autopick.py:37-43,110-111` |

**Conclusion of the audit: no additional rogue/independent voice-selection
module survives beyond the three sanctioned governance seams U98 already
built, plus their own explicitly-logged, flag-guarded, spec-sanctioned
revert paths.** Skill 59's `stage_s2_tone.py` is a thin WIRING dispatcher
(no module logic of its own — confirmed by direct read of its 289 lines) that
hands off entirely to `54-anthology-writer/anthology-entry.sh`, the Layer-1
authoring core; direct read of every file under `54-anthology-writer/`
confirms zero `tone_persona_autopick` / `persona_for_job` references inside
Skill 54's own tree — the shared tone-core is consumed at the prompt/SOP
authoring layer via the Layer-1 entry point, not a second in-skill Python
call site UNVERIFIED beyond that. There is therefore nothing further to
physically delete without either (a) touching SACRED structure
(`MASTERDOC.md`, `frame-templates/*.md`, `style-engines/*.md`, the shared
tone-core `prompts/04..08` — all fail this unit's own "STRUCTURE untouched"
acceptance clause), or (b) removing the explicit, honest, already-logged
revert affordance this unit's OWN revert clause sanctions as a last resort
("reverting an engine restores its local voice path behind the flag —
last resort").

## What was built, in the spec's required order (51 -> 58 -> Anthology LAST)

The enforcement half U98 anticipated and deferred: a **fleet-wide, always-on,
CI-enforced no-exemption invariant guard**
(`tests/unit/u114-no-exemption-blend-governance-conformance.test.py` +
`.github/workflows/u114-no-exemption-blend-governance-conformance-guard.yml`),
modeled on U95's orchestrator-only invariant guard (one static scan + one
behavioral fixture + one CI-checkable mutation proof, never advisory), never
touching `blend_voice_governance.py`, `tone_persona_autopick.py`, or any
SACRED structure file — zero risk to U98's already-verified golden fixtures.

1. **Static scan (criterion a)** — an AST-based scan (never grep) of every
   `*.py` file under each of the four engines' `scripts/` trees (excluding
   the sanctioned governance module itself and each engine's own `tests/`),
   flagging: (i) any `persona_for_job(..., blend=False)` call outside the
   sanctioned seam, (ii) any voice/persona-selector function that never
   routes through a sanctioned governance symbol, (iii) any hardcoded
   module-level `VOICE_*`/`PERSONA_*` table. One individually-failable test
   per engine (`test_skill51_static_scan_zero_rogue_voice_paths`,
   `test_skill58_...`, `test_skill54_...`, `test_skill59_...`,
   `test_shared_tone_core_...`) — all five PASS this run (zero findings).
2. **Behavioral fixture (criterion b)** — for each of the three concrete
   seams (Skill 51, Skill 58, the shared anthology tone-core), two DIFFERENT
   `PERSONA_FOR_JOB_FIXTURE` bundles are resolved back-to-back; the returned
   `persona_id` and `blend_directive` are asserted to DIFFER and to trace
   back to their OWN bundle (`voice.collapsed_persona_id == persona_id`) —
   proving the written voice is GOVERNED, not cached or hardcoded.
3. **Mutation proof (criterion c)** — a scratch copy of Skill 58's
   `scripts/` tree is made in a throwaway tempdir (the real repo tree is
   NEVER touched); a hand-authored rogue module
   (`PERSONA_MAP` + `select_voice_for_engine()`, never routing through a
   sanctioned seam) is planted, the static scanner is proven to FAIL
   (findings non-empty, pointing at the planted file); the rogue file is
   then deleted and the scanner is proven to PASS again (findings empty) —
   the guard's own self-proof that it is genuinely failable, never hollow.
4. **Regression (criterion d)** — U98's own full proof suite
   (`tests/unit/u98-blend-governs-product-voice-engines.test.py`), each
   engine's own `--self-test`, and all three tone-core consumers'
   `verify_tone_core_sync.py` are re-run via subprocess and asserted exit 0
   — proving every STRUCTURAL golden fixture and prover suite this unit
   depends on passes UNCHANGED.

## Binary acceptance — PASS/FAIL per criterion, as actually proven

**(a) per engine: a static scan finds ZERO surviving independent
voice-selection path outside the blend directive.** — **PASS**, all five
scan targets (Skill 51, Skill 58, Skill 54, Skill 59, shared tone-core).
Proof: `tests/unit/u114-no-exemption-blend-governance-conformance.test.py`,
run this build (all 12 tests PASS — command + output below).

**(b) a behavioral fixture proves the written voice is GOVERNED by the
blend (voice attributes trace to the bundle; forcing a different bundle
changes the voice).** — **PASS**, all three concrete seams (Skill 51,
Skill 58, anthology).

**(c) the CI invariant guard FAILS on a scratch-branch mutation
re-introducing a local voice path, then passes with it removed (mutation
proof).** — **PASS**, proven against a scratch copy of Skill 58's `scripts/`
tree (never the real repo tree).

**(d) each STRUCTURAL golden fixture + prover suite passes unchanged, and
every voice-path hash re-pin carries a committed proof receipt + judge
sign-off.** — **PARTIAL, judge sign-off OWED TO OPERATOR.** The golden
fixture / prover-suite regression half is **PASS** (U98's own suite +
per-engine self-tests + all three tone-core sync provers all re-run green
this build, proving no STRUCTURAL drift). This unit ships **zero voice-path
hash re-pins** — `sacred-structure-hashes.json` and
`style-engine-format-hashes.json` are byte-identical, untouched by this
unit's diff (confirmed: this unit adds two NEW files — the test + the CI
workflow — and edits zero lines inside `blend_voice_governance.py` x2,
`tone_persona_autopick.py`, any `*.json` hash-pin file, or any SACRED
structure file). Because no re-pin occurs, there is no NEW hash to
sign off on this pass; the **judge (!= builder) sign-off owed from U98's own
criterion (c)** remains explicitly **OWED TO OPERATOR** — this is the same
honest posture U98's own evidence recorded, never self-certified by the
building agent.

## Proof run (this build, repo-side, offline — no live GHL/Podbean/n8n calls)

```
$ python3 tests/unit/u114-no-exemption-blend-governance-conformance.test.py
  [PASS] test_skill51_static_scan_zero_rogue_voice_paths
  [PASS] test_skill58_static_scan_zero_rogue_voice_paths
  [PASS] test_skill54_static_scan_zero_rogue_voice_paths
  [PASS] test_skill59_static_scan_zero_rogue_voice_paths
  [PASS] test_shared_tone_core_static_scan_zero_rogue_voice_paths
  [PASS] test_skill51_behavioral_different_bundle_changes_voice
  [PASS] test_skill58_behavioral_different_bundle_changes_voice
  [PASS] test_anthology_behavioral_different_bundle_changes_voice
  [PASS] test_mutation_proof_guard_fails_closed_then_passes_clean
  [PASS] test_u98_golden_suite_passes_unchanged
  [PASS] test_per_engine_self_tests_pass_unchanged
  [PASS] test_tone_core_sync_provers_pass_unchanged
== U114 no-exemption blend-governance conformance proof: ALL PASSED ==
```

Plus the regression suite re-run standalone (redundant confirmation):
`u98-blend-governs-product-voice-engines.test.py` (6/6 PASS),
`blend_voice_governance.py --self-test` (Skill 51 + Skill 58, both PASS),
`tone_persona_autopick.py --self-test` (PASS),
`verify_tone_core_sync.py` (52/53/54, all exit 0).

## OWED TO OPERATOR

1. **Judge (!= builder) sign-off** on U98's original voice-path governance
   seams — carried forward from U98's own evidence, not resolved by this
   unit (this unit ships no NEW hash re-pin, so there is nothing fresh to
   sign off on, but the ORIGINAL U98 sign-off is still outstanding).
2. **Live fixture-run proof against a REAL deck build (Skill 51) / REAL
   episode build (Skill 58) / REAL anthology run (Skills 54/59)** exercising
   the full pipelines end-to-end with governance ON — this unit is
   REPO/CODE-side only per its build constraints (never deploy live n8n,
   never call live GHL/Podbean/Google Drive); the repo-side static +
   behavioral + mutation-proof above is real and passing, the live-build leg
   is explicitly not run here.
3. **CI guard activation** — `.github/workflows/u114-no-exemption-blend-
   governance-conformance-guard.yml` is committed and paths-triggered; its
   FIRST live GitHub Actions run (on the next push touching a watched path)
   is the operator-visible receipt that the guard is wired, not just present
   in the tree — not fabricated or claimed here.
