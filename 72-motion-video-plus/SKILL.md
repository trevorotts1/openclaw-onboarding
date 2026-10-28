---
name: motion-video-plus
description: Produces motion graphics in four delivery modes (PowerPoint graphic, desktop VSL insert, mobile VSL insert, standalone video) through one canonical V2 pipeline: mode-first intake, a schema-validated job package, typed component scenes rendered through the production adapters, and gated review and QC. Use for animated charts, explainers, and product or brand motion graphics sized for a slide, a VSL slot, or a standalone video. Do not use for AI video-model generation (Skill 67 kie-video) or documentary montage and whole-VSL production (Skill 47 movie-producer).
version: 2.0.0
---

# Motion Video Plus: Skill 72

Skill 72 produces motion graphics: animated charts, explainers, and
product or brand pieces built from code-driven animation. In V2 there is
one canonical pipeline, and it starts with the destination, not with a
renderer or a script.

## Start every job with the mode

Before any job setup, resolve which of the four delivery modes the work is
for. Resolve it from the current task or an existing manifest first; if it
is still unknown, ask: "Is this for a PowerPoint slide, a desktop VSL, a
mobile VSL, or a standalone video?" A plain "VSL" request defaults to
desktop 16:9 and records that default. The full intake contract, including
what each mode changes, the linked-variant rule for desktop plus mobile,
and the parent handoff for VSL work, is `references/intake-and-modes.md`.

| Mode | Canvas | Audio | Delivered |
|---|---|---|---|
| `powerpoint_graphic` | 16:9, default 1920x1080 | Silent | MP4, poster, placement/playback metadata, source package |
| `vsl_desktop` | 16:9, default 1920x1080 | Parent owns narration and music | Slot-length MP4, poster, timing/source metadata |
| `vsl_mobile` | 9:16, default 1080x1920, recomposed, never a crop | Parent owns narration and music | Vertical MP4, poster, mobile safe-area metadata |
| `standalone_video` | 16:9 default; 9:16 when explicitly requested | Its own, only when the brief requires it | Finished MP4, poster, source/timeline package |

Platform truth for the first row: playback inside Microsoft
PowerPoint is UNVERIFIED on every platform. What the packaging layer
proves is structural (the media embedded in the deck file itself,
byte-identical after relocation, the poster as the slide image); no
document in this skill may state or imply that PowerPoint playback
has been tested. See `references/powerpoint-packaging.md` and
`references/integration-contracts.md`.

Mode, content scope, audio ownership, and approval policy are four
separate decisions recorded in four separate manifest fields. Never mix
them (directive Section 4.3).

## Route boundaries first

Use this skill when the request is motion graphics: kinetic typography,
animated charts and explainers, brand and product pieces built from
code-driven animation, sized for one of the four modes.

Route elsewhere when the assignment is specifically:

- **Skill 67 `kie-video`**: AI video-model generation (Kie.ai), for
  footage-style or generative clips.
- **Skill 47 `movie-producer`**: documentary montage, talking-head
  pipelines, and whole VSLs. Skill 72 makes the graphics a VSL needs; the
  VSL itself, including its narration and music, stays owned by its
  producer, and VSL inserts are handed back to that parent.
- **Skill 27 / video-editor**: hands-on editing of existing footage.

If the owner explicitly asks for this motion-graphics pipeline, use it even
when the finished piece later hands off to another rail for distribution.

## The one canonical pipeline

`intake (mode first) -> brief and brand -> job package -> storyboard and
design -> scene authoring -> compile -> validate -> preview -> approvals
-> render -> QC -> package and deliver`

`INSTRUCTIONS.md` is the stage-by-stage runbook for this pipeline. The job
package created at its stage 3 is the production contract: `manifest.json`,
`storyboard.json`, `assets.json`, `design.json`, `timeline.json`, typed
scene specs under `scenes/`, datasets under `data/`, and, for VSL modes,
`parent-handoff.json`. JSON Schema is canonical
(`references/contracts-v2.schema.json`); the same contracts validate in
Python (`scripts/motion_contracts.py`) and TypeScript
(`runtime/src/validation/`). One validated example job per mode ships in
`assets/examples/`, derived from the normative fixtures in
`tests/fixtures/modes/`.

Everything else in this skill is a supporting script in service of that
pipeline, not a peer workflow: the shared-runtime provisioner, the
validators, the migrator, the TTS and sound-synthesis scripts, the assembly
and QC scripts. No supporting script defines its own route to delivery.

Status, recovery, and delivery are part of the same pipeline, not an
afterthought: one task identity runs from intake through delivery, the
structured status ledger lives in the job directory, and delivery is
recorded in a receipt built from measured facts only. That layer,
including its Skill 47 bridge (`47-movie-producer/scripts/motion_status.py`),
is specified in `references/status-and-delivery.md`. A job is reported
at the readiness level its evidence has actually reached, and
`DELIVERED` is claimed only through that layer's delivery gate.

## Production renderers and readiness

Skill 72 V2 renders through two production adapters, Hyperframes and
Remotion, provisioned by the shared rendering runtime
(`shared-utils/motion-render-runtime/`). Which adapter a scene uses is
decided by the routing authority, `references/renderer-routing.md`: routing
is per scene, driven by what the scene needs, and the delivery mode never
decides the engine by itself. What each adapter can do on a given machine
is recorded in the capability matrix,
`references/renderer-capabilities.json`. An adapter counts as ready on a
machine only when the shared runtime holds a current capability record and
a successful launch record for it; a classification in a document is not
readiness, and no renderer is presented as ready without those records.
Renderer status, including what is still untested and its specific gap,
lives in `references/untested-alternatives.md`.

Both adapters are implemented in `runtime/src/adapters/` and registered
with the one dispatcher (`MotionDispatcher`); callers never invoke an
engine directly. A request for an engine with no registered adapter, or
for a capability no ready record confirms, fails explicitly
(`MG_ENGINE_MISSING`, `MG_CAPABILITY_MISSING`) rather than substituting
another renderer. See `references/renderer-routing.md` for the error
behavior.

## Authoring-model freedom

This skill never prescribes which model writes the animation code, and no
model vendor is banned or required. Resolve the authoring model for each
job in this order: (a) an explicit choice made for this job; (b) a choice
already recorded for the current task; (c) the client's configuration,
meaning the model the client selected or their configured default; (d) if
none of those resolves, ask one question and use the answer. Record the
actual model, provider, and harness identifiers used in the job manifest.
A recommendation may be offered with its reasons as guidance only; it
never becomes the choice unless the client or the configuration makes it
the choice, and it is never a hidden prescription or default. Rendering
approved scene source is a local deterministic operation: it needs no LLM
credential and must succeed when none is present.

## Legacy V1 jobs: an explicit compatibility choice only

The V1 pipeline (HTML scenes honoring `window.__setTime(t)`, rendered by
`scripts/render.js` and assembled by `scripts/assemble.sh`) is the legacy
compatibility path. It is reached only by explicit choice, through
migration: `scripts/migrate_manifest.py` converts a V1 manifest into a V2
job scaffold non-destructively, with the mode and company supplied by the
operator, never guessed, and every unmapped value preserved in the
migration receipt. Migrated scenes stay on the declared compatibility path
until each is re-authored against a registered component. Legacy rendering
is never a default, never a fallback for a failed V2 render, and never
offered as a peer workflow. The V1 manifest shape is preserved as
`references/legacy-manifest-schema.json` with its example at
`assets/example-manifest.json`.

## Read only what the current stage needs

Start with `references/authority-map.md`, then use:

- Intake and modes (the first decision of every job):
  `references/intake-and-modes.md`
- Canonical contracts: `references/contracts-v2.schema.json`, with the
  per-artifact entrypoints `references/manifest-schema.json`,
  `references/scene-schema.json`, `references/asset-schema.json`,
  `references/timeline-schema.json`, `references/review-schema.json`
- Example jobs, one per mode, validated: `assets/examples/`
- Renderer routing authority: `references/renderer-routing.md`
- Renderer capability matrix: `references/renderer-capabilities.json`
- Renderer status reference: `references/untested-alternatives.md`
- Component catalog: `references/component-catalog.md`
- Approvals and gates: `references/approvals-and-gates.md`
- Preview and review: `references/preview-and-review.md`
- Review evidence bundles: `references/review-evidence.md`
- Critique protocol: `references/critique-protocol.md`
- Technical QC: `references/technical-qc.md`
- Audio policy (mode ownership, resolved plan, measured narration):
  `references/audio-policy.md`
- Status, recovery, and delivery (the delivery receipt and the Skill 47
  bridge): `references/status-and-delivery.md`
- PowerPoint packaging: `references/powerpoint-packaging.md`
- Presentation pipeline integration: `references/integration-contracts.md`
- VSL handoffs: `references/vsl-desktop-handoff.md`,
  `references/vsl-mobile-handoff.md`
- Design Intelligence bridge: `references/design-intelligence-bridge.md`
- Installation and migration: `references/install-and-migration.md`
- Brand bible template: `references/brand-bible-template.md`
- Director's brief template: `references/directors-brief-template.md`
- Pre-production chapters (brief-writing craft):
  `references/pre-production/`
- Motion grammar (the design constitution): `references/motion-grammar.md`
- Legacy compatibility path only: `references/animation-contract.md` (the
  `__setTime` scene contract), `references/fish-audio-tts.md` (the Fish
  Audio provider rules the narration tooling follows),
  `assets/example-manifest.json` (the V1 example)

## The gates

1. **Package validation gate.** The job package validates with zero
   findings (`scripts/motion_contracts.py validate <job-dir>`) before any
   render is claimed or started. Schema-valid is the floor: it is not
   asset-ready, approved, rendered, or delivered.
2. **Preview and approval gate.** Previews render at the actual
   composition's aspect and full fps (a reduced-fps artifact is labeled
   `rough_layout_only` and can never satisfy the motion gate), and the
   approvals the job's `approval_policy` requires are recorded against
   exact content revisions before the final render. Nobody iterates on a
   full render, and nobody writes their own approval. The gate contract
   is `references/approvals-and-gates.md`; the preview model is
   `references/preview-and-review.md`.
3. **Determinism gate.** Scene state is a pure function of frame and fps:
   seeking to a frame cold produces the same frame as seeking after any
   other frame. Drift fails the gate.
4. **Review gate.** Creative review runs on the complete-runtime
   evidence bundle (`references/review-evidence.md`): covered plus
   omitted runtime accounts for exactly 100 percent, the bundle tool
   never prints PASS, and scoring follows the evidence-bound rubric in
   `references/critique-protocol.md` (self-approval refused, no minimum
   round count, five-round cap, a claimed 10 refused against an
   uncalibrated reference).
5. **QC gate.** Technical QC passes on real evidence before delivery:
   decoded frame counts and dimensions match the plan, timing and audio
   ownership match the mode contract, and review evidence covers the full
   runtime. A check that did not run is reported as not run, never as
   passed. The QC contract is `references/technical-qc.md`.

Jobs on the legacy compatibility path additionally keep that path's own
gates (preview, critique, determinism, and `scripts/qc.sh`), run through
the same `INSTRUCTIONS.md` wrapper.

## Decisions and where they live

1. **Four modes, mode-first intake.** Directive Section 4;
   `references/intake-and-modes.md`; enforced by the mode rules in
   `scripts/motion_contracts.py` and the TypeScript validation layer.
2. **One canonical pipeline, one job package.** `INSTRUCTIONS.md`;
   contracts in `references/contracts-v2.schema.json`.
3. **Two production render adapters, readiness by record.** Hyperframes
   and Remotion, routed per `references/renderer-routing.md`; readiness
   lives in the shared runtime's capability and launch records
   (`references/renderer-capabilities.json`). Status reference:
   `references/untested-alternatives.md`.
4. **Authoring-model freedom.** No vendor banned, none prescribed.
   `INSTRUCTIONS.md` stage 7 resolves the model in order (explicit job
   choice, existing task choice, client configuration or configured
   default, then one question) and records the actual model, provider, and
   harness identifiers in the manifest.
5. **Typed component scenes.** V2 scenes are typed specs against
   registered components, never arbitrary unvalidated component names.
   The shipped catalog (`references/component-catalog.md`) registers
   C04 through C09 as available for production dispatch; C01, C02, C03,
   C10, C11, and C12 are registered identities with explicit unavailable
   reasons and are refused by name until their schema, proof contract,
   and tests register together. The catalog grows only that way. One
   shipped seam: the canonical job-package validators still admit
   C05 scenes only, so a package naming another available component
   fails package validation until the validators are wired to the
   catalog; the catalog reference records this in full.
6. **Audio ownership by mode.** PowerPoint silent; VSL inserts inherit the
   parent's audio and never create voiceover or music; standalone owns its
   audio only when the brief requires it. Audio follows the resolved
   plan of `references/audio-policy.md`, resolved once at plan load:
   narration is produced and measured at stage 6 of `INSTRUCTIONS.md`
   (never assumed), silent jobs produce none and need no TTS credential,
   and the Fish Audio provider rules for the narration tooling
   (`scripts/tts.py`) live in `references/fish-audio-tts.md`.
7. **Parent handoff for VSL work.** The manifest `parent` block plus
   `parent-handoff.json`: parent job and task, slot, narration cue, and
   the hard rules that the insert is never sped up or resized to fit.
   The shipped producers are the desktop handoff
   (`references/vsl-desktop-handoff.md`, `scripts/vsl_handoff.py` with
   its Skill 47 bridge) and the mobile recomposition
   (`references/vsl-mobile-handoff.md`, `scripts/vsl_mobile.py`).
8. **Four shipped mode producers.** PowerPoint components are packaged
   by the governed packager (`references/powerpoint-packaging.md`);
   desktop and mobile VSL inserts return through the handoff producers
   above; standalone videos are built by `scripts/build_standalone.py`.
   Presentation decks consume motion components through the existing
   presentation pipeline (`references/integration-contracts.md`), never
   through a second deck builder.
9. **Status and delivery evidence.** One task identity from intake to
   delivery, the status ledger in the job directory, and a delivery
   receipt built from measured facts (`references/status-and-delivery.md`).
   The Skill 47 bridge (`47-movie-producer/scripts/motion_status.py`)
   carries that identity onto the parent's board and attestation
   manifest; an insert never creates a task of its own.
10. **Migration, never guessing.** `scripts/migrate_manifest.py` converts
   V1 jobs non-destructively; mode, company, and parent are operator
   decisions the tool refuses to invent.
11. **Per-environment storage root.** Job folders live under a resolved
   storage root (Mac: `~/Downloads/openclaw-master-files/motion-videos/`;
   Docker VPS: a persistent volume such as `/data/motion-videos`, never
   ephemeral container storage), recorded per run.
12. **Bright, human design defaults.** No dark-style designs, no generic
    AI-polished look. Real brand assets, real typography. Encoded here, in
    `INSTRUCTIONS.md`, and in the brand bible template.
13. **Headless only.** Every renderer runs headless; on the legacy path,
    `scripts/sweep-chromium.sh` clears orphaned browsers at the end of a
    run.

## Adapted systems (borrowed concepts, original implementation)

Six systems were adapted from an analysis of a third-party motion-reel
kit. The concepts are standard practice; every file below is our own
original implementation. Nothing from that kit was copied verbatim. They
serve the canonical pipeline as supporting craft and tooling, most of them
on the legacy compatibility path today:

1. **Motion grammar.** `references/motion-grammar.md` plus
   `scripts/lint-grammar.py`: banned-cliche list, named motion presets,
   visual hits leading the beat, masked-word typography rules, 9:16 and
   16:9 safe zones.
2. **Critique system.** `references/critique-protocol.md` plus the
   MG-031 bundle builder (`scripts/critique_bundle.py`, wrapped by
   `scripts/critique-bundle.sh`) and the MG-033 rubric tool
   (`scripts/review_rubric.py`): a fresh, independent critic scores the
   eight dimensions from the complete-runtime bundle, with evidence
   bound to every score, plus a known-failure-modes checklist.
3. **Synthesized sound.** `scripts/synth-score.py`, `scripts/beat-grid.py`,
   `scripts/synth-sfx.py`: original score and UI sounds in code, no stock
   music, no licensing. Synthesis is one option inside the resolved
   audio plan (`references/audio-policy.md`), never a requirement.
4. **Determinism verification.** `scripts/verify-determinism.js` on the
   legacy path; the V2 adapters prove seek determinism by construction and
   by test.
5. **Review tooling.** The MG-031 bundle (full-resolution and
   destination-size frames, paginated sheets, the coverage record) is
   the V2 review surface; on the legacy path, stills and clip ranges
   live in `scripts/render.js`.
6. **Pre-production workflow.** `references/pre-production/` (six chapters:
   studio setup, house rules, brand assets, one-liner, steal-the-grammar,
   director's brief) plus `references/directors-brief-template.md`, wired
   into the brief stage of `INSTRUCTIONS.md`.

## Fleet rendering is frontier, not a promise

Frame ranges are independent units, so splitting a render across multiple
machines is architecturally plausible. This has never been tested end to
end. It is future work, not a capability the skill offers today. Never
present it as one. See `references/untested-alternatives.md`.

## What the operator provides

1. The destination (the mode), when the task does not already make it
   known.
2. The brief facts: message, audience, intended change, assets and data
   with their rights, brand specification, essential copy, and placement.
3. For VSL work, the parent handoff facts: parent job and task, slot, and
   narration cue. Skill 72 never invents a parent.
4. The animation-code model choice, when the operator makes one explicitly
   (stage 7 of `INSTRUCTIONS.md`); otherwise the stage 7 resolution order
   applies.
5. The approvals the job's approval policy requires, before the final
   render.
6. A Fish Audio API key and voice reference only when a job's resolved
   audio plan calls for Fish Audio narration (a narrated standalone
   piece, or a legacy-path job). Silent and inherited-audio jobs need
   neither and never consult the credential.

## What the skill never does

- Never starts job setup before the mode is resolved.
- Never treats a mobile VSL as a crop, or invents a parent, an asset, a
  dataset, or an approval.
- Never presents legacy rendering as a default or a peer workflow.
- Never opens a visible browser window.
- Never renders full quality before preview approval.
- Never stores API keys in the skill directory or in repo files.
- Never presents a renderer as ready without a current capability record
  and launch record in the shared runtime.
- Never prescribes an authoring model or bans a model vendor; the resolved
  choice and its model, provider, and harness identifiers are recorded per
  job.
