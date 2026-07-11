---
name: anthology-engine
description: The Anthology Engine, the per-client orchestrator that turns ONE participant's universal Convert and Flow form submission into ONE gated, quality-controlled 2,000 to 3,500 word anthology chapter (never twelve), delivered as BOTH a Google Doc and a designed PDF with no font below 14 point, links pushed to standardized Convert and Flow contact custom fields keyed by contact_id. It owns ALL external input and output and CALLS Skill 54 (Anthology Writer) as its authoring core; it never re-authors the chapter pipeline. Four layers: a deterministic intake router; a durable multi-participant ledger (contact_id plus anthology_id); the Skill 54 authoring core extended with the Skill 52 avatar handoff and the newly pinned prompts; Google Drive plus PDF plus Convert and Flow delivery; and the producer and participant surfaces INSIDE the client's own Command Center (a seeded Anthology department board, home-screen tiles, and a token-scoped participant page). Every stage is an idempotent, resumable job against the ledger; a crash, a credit outage, or a six-month pause costs nothing. Runs S0 intake to S9 anthology assembly through one sanctioned entry (anthology-engine-entry.sh). The producer is the OpenClaw box owner; participants are external co-authors with no login. Runtime is NEVER an Anthropic-family model: the client's own NON-Anthropic provider chain only. Move in silence: operator-verbose, client-silent, only three sanctioned nudge templates ever reach a client. Sibling of Skill 53 (Book Writer) and Skill 54 (Anthology Writer); it deprecates neither. Trigger with "run the anthology engine", "start an anthology", "onboard an anthology producer", "assemble the anthology", or an inbound anthology intake webhook.
version: 0.1.4
---

# Anthology Engine (Skill 59)

The per-client orchestrator for a MULTI-CONTRIBUTOR anthology: many external
co-authors each contribute ONE chapter around a shared theme, and a producer (the
OpenClaw box owner) curates, gates, and assembles them. This skill owns ALL
external input and output and the durable state; it CALLS Skill 54 as its
authoring core and never re-authors the chapter pipeline. It is INTEGRATION plus
HARDENING of assets the fleet already owns, not a from-scratch build, and reuse
fidelity is a scored requirement of the build gate.

> An anthology is many authors writing ONE chapter each, curated by an editor.
> That is why Skill 53 (single author, twelve chapters) stays untouched, why
> Skill 54 (the per-chapter writer) is the authoring core, and why the genuinely
> new surface is the curation-and-assembly layer (S9) plus the multi-participant
> orchestration around it.

## The silence doctrine and the responsibility boundary (binding)

Move in silence. Every code path honors these:

1. ZERO client-facing messages except the three sanctioned nudge templates in
   `config/nudge-templates/`. The recipient is ALWAYS resolved from the ledger row
   for the given contact_id (participant gates) or the producer record (producer
   gates); NO literal recipient exists anywhere in the engine.
2. OPERATOR-VERBOSE, CLIENT-SILENT. Operator and founder surfaces are rich; client
   surfaces are silent. Delivery reports and alerts go to the OPERATOR channel only.
3. NEVER print, echo, grep, or paste a secret value. Credentials are documented by
   LABEL and LOCATION only; a check reports SET or NOT SET plus a behavior probe.
4. NEVER commingle clients. Only the NAMED client's OWN accounts and keys are ever
   used. Per-client isolation is structural (physical box separation, tenant check,
   private integration token fingerprint, per-client secrets, contact_id keying).
5. CONFIG WRITES RUN AS THE NODE USER, never root. A root-owned config freezes the
   gateway.
6. The client-facing platform name is Convert and Flow, on every surface.
7. NOTHING Anthropic-family ships at runtime: the client's own NON-Anthropic chain
   only. `model_router.py` deny patterns refuse Anthropic-family ids at call time
   and `guard-no-anthropic-runtime.py` refuses them statically over every shipped
   file including every Command Center edit.
8. CANARY, THEN HOLD. The engine is proven on the operator box first; fleet rollout
   is HELD at repo-only until the operator gives the explicit OK. No client box is
   touched by the build.

## The four layers

    Convert and Flow universal form (visible: name, email, phone, Q1 ideal avatar,
    Q2 niche, Q3 primary goal; hidden: contact_id, anthology_id, stage)
      -> POST inbound webhook (Cloudflare Tunnel -> OpenClaw gateway route
         /hooks/anthology-intake, per-client secret ANTHOLOGY_INTAKE_HOOK_SECRET)
        -> LAYER 2 ORCHESTRATION: intake_router.py (deterministic, no model call,
           acknowledges in under 2 seconds) -> anthology_state.py (the SOLE ledger
           writer, keyed contact_id plus anthology_id) -> advance exactly ONE stage
          -> LAYER 1 AUTHORING CORE: Skill 54, invoked as a LOCAL subprocess through
             54-anthology-writer/anthology-entry.sh with a run dir per participant
             per stage; model chain per the tier map; measured provers; budget 2
            -> LAYER 3 DELIVERY ADAPTERS: drive_adapter.py (direct Drive and Docs
               API, existing service account, existing shared root); pdf_render.py
               (deterministic HTML-to-PDF, 14-point floor); caf_delivery.py (media
               upload, exact-key field writes by contact_id, read-back, control
               fields, per-gate pipeline-stage update); cover_render.py (Kie.ai
               portrait); nudge_send.py; alerts through the gateway only
              -> LAYER 4 SURFACES, ALL INSIDE THE CLIENT'S OWN COMMAND CENTER: the
                 seeded Anthology department board (cards via mc_board.py -> POST
                 /api/tasks/ingest, HMAC plus Bearer, fail-soft; review column is
                 the approval queue; the QC scorer at or above 8.5 promotes review
                 to done; an Assembly card for the S9 trigger and sign-off); the
                 home-screen tiles; the NEW participant token page

Layer boundaries as code contracts: Layer 2 is the ONLY layer that touches the
ledger, the model router, and the gates. Layer 1 (Skill 54) never performs network
I/O beyond its own model calls and returns artifacts on disk plus its run ledger
and prover verdicts; its certification model (hash gate, nonce, fail-closed
provers) is preserved untouched. Layer 3 adapters are stateless functions whose
every external write is followed by a read-back in the same job. Layer 4 holds NO
base credential; its only write path is shelling `anthology_state.py`.

## The canonical pipeline S0 to S9

Every stage is ONE idempotent job: an event arrives, the router advances exactly
one stage, persists, and stops. No stage ever blocks waiting for a human; the
ledger holds the cursor for weeks or months at zero cost. At EVERY gate the
registry-bound Convert and Flow pipeline-stage update fires.

| Stage | What it does | Gate |
|---|---|---|
| S0 intake and routing | create or advance the participant (contact_id plus anthology_id); provision the Drive path; card the participant onto the board; unroutable submissions go to the exceptions queue with the raw payload | none (deterministic) |
| S1 avatar | the Skill 52 handoff (Questions 1 to 30, then 31 and 32 with the auto-detected web search, then Rewrite, then Primary Goal extraction); Avatar Doc plus PDF | producer, board review column |
| S2 tone | the shared tone core 04 to 08 byte-identical; Write Tone Style 1 to 4 and Blended Tone; 3,000 measured words; Tone Doc plus PDF | producer |
| S3 title | Suggested Titles; the participant picks title and subtitle on the token page; TITLE LOCK byte-exact, one-way | participant selection |
| S4 blurb and outline | Book Blurb then single-chapter Create Outline placing every personal story; Docs plus PDFs | producer, then participant outline approval |
| S5 chapter | ONE complete chapter, 2,000 to 3,500 measured stripped words, title locked, every story placed; full Gate B battery BEFORE the gate opens | participant: Approve as-is OR Request rewrite with notes |
| S6 chapter rewrite | optional, budget 2; notes become chapter_updates; the Thornfield persona rewrites inside the band; re-enters the S5 gate | re-enters S5 |
| S7 cover image | the cover prompt generator, then Kie.ai GPT-image-2 PORTRAIT 1024x1536 via Skills 07 and 46 against the verified text-to-image portrait endpoint; PNG to Drive | none |
| S8 package and deliver | Google Doc plus 14-point-floor PDF; Convert and Flow media upload; exact-key field writes by contact_id read back byte-for-byte; control fields; per-gate pipeline-stage update; signed certificate; card to review | card to review (QC scorer owns review to done) |
| S9 anthology assembly | fired ONLY by the producer ready-to-assemble trigger; order curation, editor's introduction in the producer's voice, front and back matter, contributor bios; compile from FROZEN approved chapters byte-identical; full manuscript Doc plus PDF; producer sign-off closes it | s9_ready then s9_producer |

The complete stage contract lives in `ENGINE-MANIFEST.json` (per-stage
produces_artifact, gate, tier, provers, and the AF-AE-* autofail table). The
per-stage thin runners are `scripts/stage_s0_intake.py` through
`scripts/stage_s9_assembly.py`; each composes the pinned prompts, calls Layer 1 or
the router, runs its provers, records artifacts, and opens its gate.

## The Skill 54 call contract (Layer 1)

Layer 1 authoring is invoked as a LOCAL subprocess. A stage runner builds a run
dir per participant per stage, stages the intake and prior artifacts into
`working/`, and calls the Skill 54 sanctioned entry:

    bash 54-anthology-writer/anthology-entry.sh --run-dir <RUN_DIR>

Skill 54 walks P0 to P7 fail-closed and returns artifacts on disk plus
`working/RUN-LEDGER.json` and its prover verdicts; a signed process certificate is
issued only on a full pass. The engine never bypasses this entry and never
re-implements a Skill 54 phase. The ENGINE itself is run through its OWN sanctioned
entry:

    bash 59-anthology-engine/anthology-engine-entry.sh --stage sN --participant-key KEY [--run-dir DIR]
    bash 59-anthology-engine/anthology-engine-entry.sh --stage s9 --anthology-id ID  [--run-dir DIR]
    bash 59-anthology-engine/anthology-engine-entry.sh --plan
    bash 59-anthology-engine/anthology-engine-entry.sh --self-test

The engine entry runs four fail-closed gates (deps, model-map pre-gate, run-dir
bypass scan, enforcement hash pin), mints a run-scoped nonce, and dispatches the
stage runner. Skipping a gate requires a logged owner token in
`working/checkpoints/process_manifest.json`.

## The two quality gates (never conflated)

GATE A (build/merge) is the fleet 10-category rubric at 8.5, administered per
feature by an independent QC agent; it decides whether work merges. GATE B
(content) ships INSIDE the skill and decides whether a deliverable reaches a
producer or participant: Tier 1 deterministic hard-fail checks
(`qc-tier1-anthology.py`), then the ten-dimension rubric at 8 or higher per
dimension on the JUDGE tier (`judge_harness.py`, never the drafting tier), then the
strike cap (`qc-strike-gate.py`: rewrite budget 2, three internal QC attempts). The
independent QC scorer's promotion of a board card from review to done is Gate B's
verdict surfacing on the board. A 9.0 build unit says nothing about a chapter, and
a perfect chapter says nothing about merge readiness.

## Sibling boundaries: Skills 53 and 54

Skill 54 (Anthology Writer) and Skill 53 (Book Writer) are SEPARATE skills sharing
the ONE `shared-utils/tone-writing-core`. The anthology is many contributors, one
chapter each; the book is one author, many chapters. This engine PROMOTES Skill 54
to its authoring core and extends it by exactly three bounded extensions (the
Skill 52 avatar handoff, the newly pinned prompts, the intake fields); it builds NO
duplicate anthology skill (a duplicate is a build failure) and DEPRECATES NEITHER
sibling (the stale "deprecate BookWriter" directive is a scored build failure). A
change to the shared tone core flags both siblings and this engine for review;
forking the tone core is a build failure.

## Verify

    bash 59-anthology-engine/verify.sh       # read-only, idempotent; exits nonzero on drift
    bash 59-anthology-engine/verify-deps.sh  # dependency check (python3)

`verify.sh` proves the house layout and the interface contracts this skill
establishes (the stage machine, the field-map keys, the model-map tiers with no
Anthropic-family id, the em-dash-free and fence-free nudge templates, the 14-point
PDF floor, every stage runner byte-compiling and passing its self-test). It is
scoped so it stays green as the sibling modules land.
