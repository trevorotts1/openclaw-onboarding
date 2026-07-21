---
name: signature-presentation
description: Builds a Trevor Otts Signature Presentation — the 4-phase, minimum-100-slide signature-talk methodology (Avatar → Signature Story → Transformational Teaching → Purpose Pitch) — as a governed deck TYPE that runs THROUGH the existing Presentations department engine. Gates the sacred method with three fail-closed provers: the 8-Questions-in-one-block intake gate, the sacred-structure ledger (phase ranges, ≥100 floor with client-exact override, ≤2 case studies, 3–7 teaching steps, suggested-image-per-slide, central-hook + section-hooks, N.E.E.I.T./4-Quadrant), and Phase-3 no-pitch hygiene. Ships four client-facing teaching frames — The Rulebook, The Vault, The Quest, The Original. Never forks the render path; the department's canonical entry (build_deck.py) does all rendering, assembly, delivery, and Kanban.
version: 1.0.11
---

# Signature Presentation (Skill 51)

The methodology layer for the Trevor Otts **"How To Create A Signature Presentation"** — a
4-phase, minimum-100-slide signature talk — added to the Presentations department as a new
governed **deck type** (`deck_type: signature_presentation`). This skill owns the *IP and the
gates*; the department engine owns *execution*. It never builds a deck itself and never forks
`build_deck.py`.

> The method captured in `MASTERDOC.md` is **SACRED** — never floored, reordered, or
> reinterpreted. Every rule below is machine-enforced by a fail-closed prover, never advisory.

## What this skill produces / owns

- `MASTERDOC.md` — the anonymized canonical methodology (Prime Directives, the 8 Questions,
  the four phases, N.E.E.I.T., the 4-Quadrant method, the hook doctrine).
- `intake/sp-8-questions.json` — the 8-Questions + frame-selection spec. The owner CONVERSATION is
  choice-first (a QUICK vs IN-DEPTH interview) and asks **one question at a time**, never a wall of
  questions (dumping the batch is **AF-INTAKE-BATCH**); the answers are then recorded as ONE atomic
  machine block that the intake prover validates before slide authoring unlocks.
- `frame-templates/the-rulebook.md`, `the-vault.md`, `the-quest.md`, `the-original.md` — the four
  client-facing teaching frames, each mapped to the 4 phases and slide ranges.
- `structure/sp_structure.json` — the sacred-structure ledger CONTRACT the structure prover loads.
- `scripts/prove_sp_intake.py`, `prove_sp_structure.py`, `prove_sp_no_pitch.py` — the three
  fail-closed provers (installed into the department's `scripts/` at wire time).
- `scripts/intake_trace_check.py` — the AF-INTAKE-BATCH conversation-trace scanner: a
  **fail-closed, GATING** deterministic scan over the intake transcript
  (`<RUN_DIR>/working/interview/intake_transcript.json`, written mechanically by the driver's
  turn-gate). It is wired into the department engine as the required preflight
  `P-SP-INTAKE-TRACE` (`build_deck._chk_sp_intake_trace`, phase order 0.16) and DEFERS for
  every non-signature deck. A batched or choice-less intake CONVERSATION now blocks the build,
  and an ABSENT transcript is a fail — otherwise the cheapest way past a conversation gate is
  to record no conversation. The QC Specialist / Healer still run it out-of-band as a
  post-hoc scan (SOP 9.1 / SOP 9.13); that duty is unchanged.
  > Corrected in A10 / T0-12: this scanner was previously documented as advisory and
  > non-gating on the same page that declares every rule machine-enforced and never advisory.
  > The rule that defines this skill's value — choice-first, one question per turn — was the
  > one rule nothing enforced, so a batched eight-question interaction that afterwards
  > produced a structurally valid intake RECORD passed every preflight and reached a signed
  > certificate. The run supplied its own record as the only evidence of how the intake had
  > been conducted.

## The methodology in one screen

**Gather the 8 Questions choice-first, ONE at a time — before writing anything** (Prime Directives
6–7, under Trevor's ruling that one-question-at-a-time wins). Open by offering the owner a QUICK vs
IN-DEPTH interview, then ask exactly **one question at a time** and wait for each answer — never a
wall of questions (dumping the batch, or opening with no quick-vs-in-depth choice, is
**AF-INTAKE-BATCH**, an intake-conversation autofail enforced by the QC/Healer scan that NEVER gates
`build_deck.py`). The answers are then assembled into ONE atomic machine RECORD
(`working/copy/sp_intake.json`) — that assembled block is what the intake prover validates. Once
every answer is locked, write all slides at one time (Directive 8). The eight, verbatim ids `q1..q8`:

1. Title of the Signature Presentation
2. Do you want alternate titles proposed first?
3. Specific pain points for the avatar section?
4. Key elements of your story to weave into the personal-story section?
5. What to teach in the transformational-teaching section ("7 Secrets to ___", "The ___ Blueprint to ___")?
6. Do you want alternate teaching-section titles proposed?
7. What product(s) will you offer at the end?
8. Anything else to consider before writing?

A **frame-selection question** is asked as its own turn in the same one-at-a-time flow (additive to
the 8, never replacing one): The Rulebook / The Vault / The Quest / The Original.

### The four phases (labeled with name + purpose before each phase's slides — Directive 10)

| # | Phase | Slide range (per-phase floor) | Method |
|---|---|---|---|
| 1 | **Avatar Section** — "Mastering the Audience Avatar" | 1–11 (≥11) | N.E.E.I.T. + 4 Quadrants. First you tell THEIR story, then you tell yours. |
| 2 | **Signature Story** — "Crafting Your Personal Story" | 12–24 (≥13) | Relatability, vulnerability, pain→purpose, legacy. End on a gripping "why". |
| 3 | **Transformational Teaching** | 25–60 (≥36) | 3–7 steps. **FORBIDDEN to pitch.** The final step bridges to the offer (transition, not pitch). |
| 4 | **Purpose Pitch** | 61–100 (≥40) | N.E.E.I.T. + 4 Quadrants. Purpose pitch, not profit pitch. |

Phase bands are **contiguous floors** starting at slide 1: when a phase expands past its band to
hit the ≥100 floor (Directive 11), later phases shift by the same amount, still in order.

### The hard rules (all fail-closed — see `structure/sp_structure.json`)

- **≥100 slides** by default (Prime Directives 3 + 11). **Client-exact override:** if the client
  states an EXACT slide count, the client's number wins — the floor is skipped ONLY when the
  override is logged (`client_overrode_slide_floor: true`) and noted on the process certificate.
  (Client-exact count is the fleet-wide absolute law; the ≥100 floor is the DEFAULT, not a cap.)
- **≤2 case studies** per deck (Directive 12); floor of 1 from the department's proof battery → band 1–2.
- **Suggested image on every slide** (Directive 4) — the authoring seed the Prompt Author expands
  to the full rich prompt; it never replaces the 9,000-char prompt floor. Each frame template
  carries a **"Visual identity & suggested-image seed craft"** section (v1.0.4): the six seed
  anchors (archetype + subject/emotion + setting + light + STYLE-BLOCK palette + copy zone) plus
  the frame's controlling visual motif and series discipline — author seeds to that contract.
- **One central hook repeated like a chorus + four section hooks** that ladder up to it (distinct lines).
- **N.E.E.I.T. + 4-Quadrant markers** present in Phases 1, 2, 4.
- **Phase 3 never pitches** — no price, offer name, enroll/scarcity/guarantee language in slides 25–60.

## The four teaching frames

Each frame runs the identical 4-phase skeleton; only the teaching devices, refrains, and close change.

| Frame | Phase-3 signature | Phase-4 close |
|---|---|---|
| **The Rulebook** | Numbered non-negotiable Rules (3–7), each = teaching + affirmation + 3-step action plan; recap of all Rules; a teased bonus Rule | Purpose-vs-profit framing; roll-call ending "…AND YOU!" + the offer URL |
| **The Vault** | Numbered Secrets unlocked one at a time, each = a famous quote + a numbered affirmation; one running metaphor motif deck-wide; a personal-manifesto triad | A blessing close ("My Prayer for YOU") |
| **The Quest** | A named Blueprint organized as Quests (steps + named affirmations); the richest hashtag-driven narrative; riddle / definition-pair / literary-passage devices | A poetic manifesto with a fill-in-the-blank affirmation close (**Directive 13 singles out this ending**) |
| **The Original** | The client's own methodology chunked into 3–7 steps, devices designed fresh | A manifesto-grade emotional close designed fresh |

## How it runs — THROUGH the engine, never a second build path

This skill is a **methodology + gate** layer. It authors `slides.json` and the machine ledgers,
then hands off to the department's ONE sanctioned build command — it does **not** render, assemble,
or deliver anything itself:

```
bash 23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh \
    --run-dir <RUN_DIR> --slides slides.json --out <OUT>.pptx
```

That entry runs the department's fail-closed gates and then `run_signature_deck.py` → `build_deck.py`
(kie.ai gpt-image-2 only; every word baked into the image; zero native on-slide text; the full
phase-attestation chain). Writing and running your own per-deck driver — `python3 working/*.py` — is
the **ungoverned path and is FORBIDDEN** (`AF-CANONICAL-RENDER-BYPASS` / `AF-LOCAL-CANVAS`). All
rendering, PPTX assembly, speech/guide/audio, delivery, and the Command Center Kanban card belong to
the engine; this skill only adds the sacred-method gates on top.

**What the engine gives us for free (no new code):** the 9,000–18,000-char rich-prompt floor,
phase-skip impossibility (`run_signature_deck.py`), the delivery-blocking process certificate
(`prove-deck.py`), and the full existing auto-fail battery (hook, one-big-idea, density, typography,
logo, canonical-render, image-QC). The three SP provers add ONLY the sacred-method rules and install
as manifest phases + thin `_chk_sp_*` preflight wrappers that DEFER unless
`deck_type == "signature_presentation"`.

## Integration surface (wired by `wire-signature-presentation.sh`)

- `PIPELINE-MANIFEST.json` — three SP phases + `AF-SP-*` autofail rows + a manifest_version bump.
- `build_deck.py` — three ≤6-line thin `_chk_sp_*` wrappers appended to `PREFLIGHT_REQUIRED`,
  each deferring when the deck type is not signature_presentation.
- `phase_verifiers.py`, `prove-deck.py` (declared steps), `test_preflight.py` (golden + adversarial),
  `SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md` rows — the full SOP-SLIDE-06 lockstep, so
  `sync_check.py` stays green.
- Command Center — one keyword (`signature presentation`) + one `sops` row; no schema change, no new
  lane, no new persona table.

## Voice governance (Skill 6 U98, D1 binding ruling)

The deck's **written voice** (word choice, cadence, register) is GOVERNED by the blended persona
directive — never advisory, no exemptions, per the D1 ruling. `scripts/blend_voice_governance.py`
resolves one governing blend bundle PER PHASE (all four: Avatar Section, Signature Story,
Transformational Teaching, Purpose Pitch) through the shared U1 seam
(`shared-utils/persona_for_job.py`, `blend=True`) before slide authoring. This is **additive
governance**, never a structural change: `MASTERDOC.md`, the four `frame-templates/*.md`, and
`structure/sp_structure.json` remain SACRED and byte-identical (pinned in
`scripts/sacred-structure-hashes.json`, re-hashed and diffed by
`blend_voice_governance.py --hash-structure` / `--prove`) — the N.E.E.I.T./4-Quadrant methodology,
the phase bands, and the per-quadrant "Tone:" craft notes baked into MASTERDOC.md are untouched;
only WHO governs the actual written voice changes. Flag-guarded: `SKILL51_BLEND_GOVERNS=0` reverts
to intake-tone-only governance (director-of-presentations-sops.md's pre-existing rule — nothing to
re-implement, it was never removed).

## Install / Wire / Verify

This skill does **not** ship its own `install.sh` or `wire.sh` — it installs via the main installer
and wires via the department lockstep. The three legs:

- **Install** — the main `install.sh` function `install_skill_51_signature_presentation()` copies
  this skill into the box (`$SKILLS_DIR/51-signature-presentation`) and marks the provers executable.
  Skill 23 (the Presentations engine) is the prerequisite and installs alongside it.
- **Wire** — the **SOP-SLIDE-06 lockstep** (`universal-sops/presentation-slide-craft/SOP-SLIDE-06-EXTENSION-AND-SYNC.md`).
  It installs the three SP manifest phases (`P-SP-INTAKE` / `P-SP-STRUCTURE` / `P-SP-P3-HYGIENE`),
  the `AF-SP-*` autofail rows, and the ≤6-line `_chk_sp_*` preflight wrappers into the department
  engine (`build_deck.py`, `phase_verifiers.py`, `prove-deck.py`, `PIPELINE-MANIFEST.json`,
  `test_preflight.py`, the MASTER QC ruleset). The wiring is already in the engine; `sync_check.py`
  stays green. There is **no** separate `wire.sh` — re-running the lockstep is how the wiring is
  changed, per SOP-SLIDE-06.
- **Verify** — `51-signature-presentation/verify.sh` (idempotent, read-only): runs the five
  fail-closed provers in `--self-test` mode — including the AF-INTAKE-BATCH scanner
  (`scripts/intake_trace_check.py --self-test`), added in A10 / T0-12 — plus the engine
  wire-presence assertion (all five `_chk_sp_*` wrappers defined AND registered in
  `PREFLIGHT_REQUIRED`) and the `register-library-additions.py --check` sanity (both SP roles
  registered in `role-library/_index.json`). Exits nonzero on any failure, so it can gate a
  merge / CI / a post-install check. Run it with `bash 51-signature-presentation/verify.sh`.
  The intake-conversation guard (`tests/unit/presentation-intake-conversation.test.sh`) is
  self-tested separately in CI. The scanner remains a QC Specialist / Healer duty out-of-band
  (SOP 9.1 / SOP 9.13) **in addition to** being a build gate, not instead of it.

## Prerequisites

- Skill 07 (Kie.ai setup) — the render provider for the canonical pipeline.
- Skill 23 (AI Workforce Blueprint) — materializes the Presentations department on the box.
- The Presentations department (role library) present and SOP-locked.

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys** — never the
operator's, never Anthropic model ids. Role files and SOPs name client-provider tiers only (e.g. the
department already pins client-side QC to `qwen3-vl:235b-cloud` primary with a DeepSeek fallback on
the client's own keys). This SKILL is provider-neutral by construction.
