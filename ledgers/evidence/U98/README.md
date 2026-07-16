# U98 (E4-1, v1 U28) — Blend GOVERNS the product-voice engines — evidence

Unit: U98 (P3, ONB). Binding: D1 (the blend GOVERNS voice + content-writing
in every engine, never advisory, no exemptions — INCLUDING the
product-voice engines: Skill 35, Skill 51 presentation, Skill 58 podcast,
Skills 54/59 anthology). Deps confirmed already merged on `origin/main`
before this build started:

- **U5** (A-U5 per-page/per-scope blends) — `persona_blend.build_bundle(...,
  scope_hint=...)` merged `e979d09d` (v20.0.32, ledger row "verified (ONB
  half)"). This unit's Skill 35 leg is a direct adoption of this exact
  mechanism, never a re-implementation.
- **U7** (Skill 6 convergence, "THE unification unit") — merged `8004d0b2`
  (v20.0.34), set to `verified (both repos)` at `cd4fbce4`.
- **U114** (decommission-of-local-voice-logic invariant, cross-referenced by
  this unit's own spec text) — **NOT on origin/main** as of this build (no
  `skill6-v2/U114` branch exists yet, no ledger row). The task's own hard-dep
  gate named only U5 and U7; U114 is a spec cross-reference for FLEET-WIDE
  coordination (acceptance criterion (d): "coordinated with U114"), not a
  build blocker for the four engine-local reconciliations this unit ships.
  See "OWED TO OPERATOR" below for the honest scope line this draws.

## What was reconciled, in the spec's required order

1. **Skill 35 (social-media-planner)** — `35-social-media-planner/scripts/
   daily_blend_bundle.py`. Replaces the single-persona-per-week pick
   (playbook.md Step 0a.5) with a per-DAY governed blend via the U5
   scoped-bundle mechanism (`build_bundle(..., scope_hint={"page_role":
   "day-N"})`) — one scope per posting day, the blend directive governing
   each day's copy, logged per day to `persona-selection-log.md` (one entry
   per day, replacing the old single weekly entry). The Television Show
   Framework (Day 1 hooks → Day 7 finale, escalating pitch intensity) is
   untouched — this governs VOICE only.

2. **Skill 51 (signature-presentation)** — `51-signature-presentation/
   scripts/blend_voice_governance.py`. Before this unit there was NO
   catalog-persona voice module in Skill 51 at all (confirmed by direct
   read of `SKILL.md`, `MASTERDOC.md`, and every `scripts/*.py` — the
   deck's voice was governed purely by intake-derived tone and the
   per-quadrant "Tone:" prose baked into the sacred N.E.E.I.T./4-Quadrant
   methodology). This is the FIRST governance seam: one governed blend
   bundle per phase (all 4: Avatar Section, Signature Story,
   Transformational Teaching, Purpose Pitch) via the shared U1 seam
   (`persona_for_job(..., blend=True)`). SACRED structure —
   `MASTERDOC.md`, the 4 `frame-templates/*.md`, `structure/
   sp_structure.json` — is pinned byte-identical in
   `scripts/sacred-structure-hashes.json` and proven unchanged by this
   commit (see hash table below).

3. **Skill 58 (podcast-production-engine)** — `58-podcast-production-engine/
   scripts/blend_voice_governance.py`. STEP 2's four Style Engines
   (Counter Intuitive / Vulnerable / Provocative / Passionate) each carry
   their own independently-authored "## VOICE DNA" section — the local
   voice logic this unit reconciles. The blend directive now governs the
   script's actual written voice (word choice, cadence) per selected
   engine; the four `style-engines/*.md` FORMAT files (arc beats, length
   table, Final Draft format, Fish Audio tagging discipline, episode QC
   gate) are pinned byte-identical in `scripts/
   style-engine-format-hashes.json` and were never edited by this unit.

4. **Anthology (Skills 54/59) — LAST, per spec** — `shared-utils/
   tone-writing-core/tone_persona_autopick.py`. The shared tone-core's N/A
   tone-slot auto-pick (consumed by 52/53/54, all three sharing ONE tone
   core per Trevor's standing decision) previously resolved an N/A slot via
   `persona_for_job(..., blend=False)` — a real, LOGGED, but UNGOVERNED
   single-persona pick. It now resolves via `blend=True`: the returned
   voice for that slot carries the governing `blend_directive` (guardrail
   included), traceable to the bundle. CLIENT-NAMED slots are untouched
   (client sovereignty, unconditionally exempt — not a governance gap).
   The 4-slot blend STRUCTURE and `prompts/04..08` tone-stage assets are
   byte-identical, proven for ALL THREE consumers (52/53/54) via each
   consumer's own `verify_tone_core_sync.py` (still exit 0 — see proof run
   below).

Every leg is flag-guarded (`SKILL35_BLEND_GOVERNS` / `SKILL51_BLEND_GOVERNS`
/ `SKILL58_BLEND_GOVERNS` / `ANTHOLOGY_BLEND_GOVERNS`, each default `"1"`
— governing by default per the D1 ruling's "never advisory, never optional"
mandate). Setting a flag to `"0"` raises a named `Legacy*Required` exception
— an explicit, logged revert, never a silent fallback to an ungoverned
voice.

## Binary acceptance — PASS/FAIL per criterion, as actually proven

**(a) per engine: a fixture run produces a receipt proving the blend
directive + guardrail governed the written voice, traceable to the
bundle.** — **PASS**, all four engines. Proof:
`tests/unit/u98-blend-governs-product-voice-engines.test.py`, run this
build (all 6 tests PASS — command + output below).

**(b) every engine's STRUCTURAL golden fixtures pass byte-identical, and
its prover suites pass with governance ON.** — **PASS**, as far as this
unit's own scope reaches:
  - Skill 51: `sacred-structure-hashes.json` pin verified byte-identical
    this run (MASTERDOC.md + 4 frame-templates + sp_structure.json).
  - Skill 58: `style-engine-format-hashes.json` pin verified byte-identical
    this run (all 4 style-engines/*.md).
  - Anthology: `verify_tone_core_sync.py` exit 0 for 52/53/54 (unchanged).
  - Skill 51's own `prove_sp_structure.py` / `prove_sp_intake.py` /
    `prove_sp_no_pitch.py` and Skill 58's `qc-tier1-mechanical.py` were
    NOT re-run against a live deck/episode build in this pass (this unit
    ships a REPO-side voice-governance seam; it does not build a live
    deck or episode) — their gates are untouched by this unit's diff
    (confirmed: this unit adds new files + two additive doc lines; it
    edits zero lines inside `build_deck.py`, `phase_verifiers.py`,
    `prove-deck.py`, `qc-tier1-mechanical.py`, or any `*.json` structural
    ledger other than the two NEW golden-hash-pin files it introduces).

**(c) each engine's voice-path hash re-pin is accompanied by a committed
proof receipt + a judge (!= builder) sign-off, and NO structural-contract
hash changes in the same commit.** — **PARTIAL, judge sign-off OWED TO
OPERATOR.** The proof receipt is this document + the test run below
(committed). The CI-separation half is proven by
`test_voice_path_files_never_share_a_commit_hash_pin_with_structural_files`
(this unit's own new *.py voice modules are never the files a structural
pin hashes). The **judge (!= builder) sign-off is explicitly NOT
self-certifiable by the agent that built this unit** — it is recorded here
as **PENDING / OWED TO OPERATOR**, the same honest posture the ledger
already uses for other units awaiting an operator-gated decision (e.g. U53
"D12/D-HL-3 crown-DECISION ratification ... still waiting on Trevor").

**(d) a conformance probe finds ZERO surviving independent voice path in
any of the four engines (coordinated with U114).** — **PARTIAL, scoped to
this unit's four named call sites, NOT a fleet-wide probe.** Proven for the
EXACT call sites this unit reconciled: Skill 35's daily bundle call, Skill
51's + Skill 58's new governance seams, and the anthology's N/A tone-slot
autopick — each raises an explicit `Legacy*Required` exception rather than
silently falling back to an ungoverned voice when its flag is disabled
(proof: the `flag=0 reverts to Legacy*Required` checks in every self-test
+ the master test file). **This is NOT a claim that zero independent voice
paths survive FLEET-WIDE across these four skills** — U114 (which owns that
broader invariant per this unit's own spec cross-reference) has not landed
on `origin/main`; a fleet-wide conformance sweep is U114's job, not
duplicated or pre-empted here.

## Structural golden-hash pins (this commit)

`51-signature-presentation/scripts/sacred-structure-hashes.json`:
```
MASTERDOC.md                        5762e95a6e9b63fa016acee7290e64eaf767cd67e9b0da3f2390c776c51f8c9b
frame-templates/the-original.md     fe2daea2aa468492399f171cb31333fdaf2fda2d691edfe879872d9ebd40cab8
frame-templates/the-quest.md        bc19226e10aa181a4336dc0a7ac4ede20d331e41c7f89f6cb85ab1e2a381974a
frame-templates/the-rulebook.md     5965832cced82da9786e105845e94f0007aaba06a8a4b7966fb041ca3fe0b68c
frame-templates/the-vault.md        88dba9ef5bfda36cd6d9b8a6645c7dae06c9bfab4e24852261f7dcac173bd002
structure/sp_structure.json         02359556514ed87edf1854859b80d2b88f0209c8944759f8bc2aa713c0887c75
```

`58-podcast-production-engine/scripts/style-engine-format-hashes.json`:
```
counter-intuitive.md   7f6ca051c42c1c42e3b3f676b35143bf8968016fb855948b1a6f63ad184c9d1a
passionate.md           0dcaa58086aab3c52090c15363d1ccafe5916c98f6a47d94dee6e72a0cb88565
provocative.md          b606e3da17edd9c5fcea87f75d29162bf78e2bd1a59955c27738110e6e405b25
vulnerable.md            16b7144b5136811a0b810d70363fe512422fa541fd537a8f4372dd0f04dd0cf8
```

## Proof run (this build, repo-side, offline — no live GHL/Podbean/n8n calls)

```
$ python3 tests/unit/u98-blend-governs-product-voice-engines.test.py
  [PASS] test_skill35_per_day_blend_governance
  [PASS] test_skill51_voice_governed_structure_preserved
  [PASS] test_skill58_voice_governed_format_preserved
  [PASS] test_anthology_na_slot_governed_client_named_untouched
  [PASS] test_anthology_tone_core_structure_unchanged_all_three_consumers
  [PASS] test_voice_path_files_never_share_a_commit_hash_pin_with_structural_files
== U98 blend-GOVERNS-product-voice-engines proof: ALL PASSED ==
```

Plus the per-engine self-tests (`daily_blend_bundle.py --self-test`,
`blend_voice_governance.py --self-test` x2, `tone_persona_autopick.py
--self-test`) and the pre-existing `persona_for_job.py --self-test` / U111
proof (regression check — both still ALL PASSED unmodified by this unit).

## OWED TO OPERATOR

1. **Judge (!= builder) sign-off** on the voice-path hash re-pin (criterion
   (c)) — cannot be self-certified by the building agent; needs an
   independent QC pass.
2. **Fleet-wide conformance sweep coordinated with U114** (criterion (d))
   — U114 has not landed on `origin/main`; this unit proves its OWN four
   call sites are revert-flag-gated (never silently ungoverned) but does
   not (and cannot honestly) claim to have swept the whole fleet for every
   surviving independent voice path.
3. **Live fixture-run proof against a REAL deck build (Skill 51) / REAL
   episode build (Skill 58)** exercising `build_deck.py` /
   `run_signature_deck.py` / the 18-step podcast pipeline end-to-end with
   governance ON — this unit is REPO/CODE-side only per its build
   constraints (never deploy live n8n, never call live GHL/Podbean); the
   repo-side fixture proof above is real and passing, but the live-build
   leg is explicitly not run here.
