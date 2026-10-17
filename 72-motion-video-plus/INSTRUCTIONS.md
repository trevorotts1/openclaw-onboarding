# Skill 72 Operator / Agent Instructions

## Trigger

Use Skill 72 when a client asks for motion graphics: an animated chart,
explainer, or product or brand piece built from code-driven animation, for
a PowerPoint slide, a desktop VSL, a mobile VSL, or a standalone video.

Do not use Skill 72 when the request clearly names AI video-model
generation (Skill 67 `kie-video`), documentary montage or a whole VSL
(Skill 47 `movie-producer` owns the VSL itself; Skill 72 supplies its
graphics), or hands-on editing of existing footage (video-editor).

## The wrapper in one paragraph

These stages are the one canonical production path for every Skill 72 job.
They wrap the contracts, the adapters, and the supporting scripts; the
scripts are tools the stages call, not peer workflows with their own route
to delivery. Stage 1 resolves the destination (the mode) before anything
is set up. Stage 3 creates the V2 job package, the production contract
every later stage works from. Do not skip the hard gates. The legacy V1
pipeline survives only as the explicitly chosen compatibility path at the
end of this document.

Status, recovery, and delivery run through the same wrapper: one task
identity from stage 1 to stage 15, the status ledger in the job
directory, and the delivery receipt at the end. That contract is
`references/status-and-delivery.md`; stages 11, 14, and 15 below are
its production surface, and its Skill 47 bridge
(`47-movie-producer/scripts/motion_status.py`) carries the identity
to the parent board for VSL work.

### What parallelizes and what stays sequential

The decision chain stays sequential: mode, brief, storyboard, narration
measurement for narrated work, timeline, authoring, approvals. Inside a
stage, independent units parallelize: scene specs are authored
concurrently once the design is locked, per-scene renders run
concurrently up to the resource budget, and review stills are produced
for all scenes at once. Asset research and style frames may proceed
earlier, in parallel, when they do not depend on timing. Never start a
stage that depends on a decision an earlier stage has not made.

### 1. Intake: mode first

Resolve known information from the current task and any existing manifest
first. The full intake contract is `references/intake-and-modes.md`; the
essentials:

- If the mode is unknown, ask: "Is this for a PowerPoint slide, a desktop
  VSL, a mobile VSL, or a standalone video?" Ask only the next missing
  material question after that; never run a repeated questionnaire.
- A plain "VSL" request defaults to `vsl_desktop` (16:9); record that the
  default was applied. When desktop and mobile are both requested, create
  linked variants, one job per mode, each recording the other in its
  manifest `variants` list.
- Capture, resolving from context before asking: the message, audience,
  intended change in belief or understanding, intended use and placement,
  actual assets and data with their source rights, brand specification,
  essential copy, duration (presenter length, parent slot, or approved
  standalone timeline), desired action, and the render approval policy.
- For VSL modes, capture the parent handoff facts: parent job and task,
  the slot in the parent's timeline, and the narration cue. Never invent a
  parent.
- Keep the four operating dimensions separate: `mode`, `content_scope`,
  `audio.mode`, `approval_policy`.

No job setup of any kind starts before the mode is resolved.

### 2. Storage root and job folder

Resolve the storage root per environment, never hardcode it: Mac uses
`~/Downloads/openclaw-master-files/motion-videos/`; a Docker VPS uses a
persistent volume such as `/data/motion-videos`, never ephemeral container
storage. Create the job folder under it and record the resolved root with
the run's records. The job package (stage 3) lives in this folder.

### 3. Create the V2 job package

Write the job package, the serialized production contract:

- `manifest.json`: job identity, mode, canvas, fps, content scope, engine
  choices, audio policy, approval policy, linked artifact names, delivery
  requirements.
- `storyboard.json`: story beats with states, not a list of headlines.
- `assets.json`: actual local assets with hashes, rights, and font
  requirements. A remote URL is not a downloaded file.
- `design.json` plus a `frame.md` rationale: the machine-readable visual
  system and its human-readable notes.
- `timeline.json`: the compiled frame intervals (stage 6 refines it).
- `scenes/*.json`: one typed scene spec per scene.
- `data/*.json`: source-backed datasets.
- `parent-handoff.json`: VSL modes only (stage 1 facts, in the handoff
  shape `references/intake-and-modes.md` documents).

Start from the validated example for the mode in `assets/examples/` and
adapt it; the normative fixtures in `tests/fixtures/modes/` are the
reference originals and are never edited to fit a job. Validate as soon as
the package exists:

```bash
python3 scripts/motion_contracts.py validate <job-dir>
```

Zero findings is the floor for everything after this stage. Schema-valid
is not asset-ready, approved, rendered, or delivered.

An existing V1 job enters here, and only here, through migration (see the
legacy section at the end of this document): the migrator writes the V2
manifest scaffold and lists the companion artifacts that must still be
authored before the job can move forward.

### 4. Brief and brand

Write the director's brief and get the operator's explicit approval before
any scene code exists. The pre-production chapters
(`references/pre-production/`) are the brief-writing craft for this stage:
studio setup, brand assets, the one-liner, steal-the-grammar, and the
brief itself, with `references/directors-brief-template.md` as the brief's
shape. Load the brand bible (built from
`references/brand-bible-template.md`) on this run and every later run for
the brand. Bright, human defaults: no dark-style designs, no generic
AI-polished look.

### 5. Storyboard and design

Author the storyboard beats: each beat names its job, the viewer's
question, the visual verb, the changing subject, and its initial, proof,
and final states, bound to the exact assets and data that carry it.
Distinguish literal evidence from illustrative metaphor. Author
`design.json` (canvas layouts per mode, type roles and sizes, color,
motion scale) with its `frame.md` rationale; unresolved conflict with the
brand bible stops the stage. Mobile is authored as its own layout record,
never derived by cropping the desktop layout.

### 6. Lock timing, then compile the timeline

This stage locks the job's timing before any scene is authored (stage 8)
and before any final motion timing exists. It runs in exactly one of two
branches, decided by the audio policy recorded in the manifest at
stage 3.

**Narrated branch** (`audio.mode` `own`, with narration), in order:

1. Approved copy: the narration text is final under the stage 4 brief
   approval.
2. Narration production and measurement: synthesize the approved copy
   with `python3 scripts/tts.py --manifest <manifest.json> --outdir
   work/audio`, or measure the supplied audio file when the job supplies
   its own recording. `tts.py` segments the narration at sentence
   boundaries into provider-limited transport chunks (a per-request cap,
   never a per-scene quota; there is no minimum length and no padding),
   and writes `durations.json`: the measured speech duration of every
   scene plus the narration fingerprint, a hash of the exact narration
   text and the provider settings that produced it. For speech-sensitive
   events, use existing alignment capabilities or verified cue points,
   record the alignment confidence, and correct the cue when alignment
   is uncertain rather than letting the picture drift against the words.
3. Compile the story-beat timeline from the measured durations: scene
   frame intervals derive from measured speech. The picture is timed to
   the approved audio, never the reverse.

**Silent branch** (`audio.mode` `none`, or `inherited` for VSL inserts),
in order:

1. Approved duration: the parent slot for a VSL insert, or the approved
   playback duration for a PowerPoint graphic or a silent standalone
   piece.
2. Compile the story-beat timeline from that duration; animation and
   preview follow at stages 8 and 10.

No TTS step exists in this branch: no narration is produced, no TTS
credential is required or consulted, and `tts.py` run against a silent
job exits cleanly with a recorded no-narration result.

Either branch compiles one authoritative timeline: integer frame
intervals in half-open form, `[start_frame, end_frame_exclusive)`, for
the whole job and each scene, with audio alignment and transition
handles. Author everything on the selected canonical output timeline at
the declared fps (30 by default; 60 only as a deliberate override). For
VSL modes the parent slot length equals the insert length exactly; the
insert is never sped up, slowed down, or stretched to conceal a timing
error.

**Invalidation.** Changing narration copy, the narration provider
settings (model, voice reference, temperature, chunk cap), or the
supplied audio after this stage changes the narration fingerprint and
invalidates the compiled timeline, every scene timing derived from it,
and any approval bound to those revisions. Re-run the narration
measurement and recompile before authoring or rendering proceeds.
Approvals at stage 11 bind to content revisions that include the
fingerprint, so a stale approval cannot authorize a re-timed job.

### 7. Authoring-model selection (authoring-model freedom)

No model vendor is banned and none is prescribed. Resolve which model
writes the scene code in this order: (a) an explicit choice made for this
job; (b) a choice already recorded for the current task; (c) the client's
configuration, meaning the model the client selected or their configured
default; (d) if none of those resolves, ask the operator one question and
use the answer. A recommendation may be offered with its reasons as
guidance only; it is never a hidden prescription or default, and it
becomes the choice only if the client or the configuration makes it the
choice. Record the resolved choice in the manifest's `authoring` block:
`selection` (`explicit` when a choice was made for this job,
`inherit_config` when the configuration supplied it) with the actual
provider, model, and harness identifiers. Do not ask about a model when
one is already configured. Later stages render approved scene source
locally and deterministically: rendering requires no LLM credential and
proceeds when none is present.

### 8. Scene authoring

Author each scene as a typed spec against a registered component
(`scenes/<scene-id>.json`): component id and version, engine where the job
fixes one, layout variant, duration, asset and data references, copy, the
motion declaration, and the semantic motion assertions the render must
prove. Scene state is a pure function of frame and fps, so any frame can
be produced cold, in any order, with the same result. Which engine renders
a scene is decided per scene by `references/renderer-routing.md`, never by
the delivery mode alone. Author scenes in parallel once stages 4 to 6 are
locked, then unify. Scenes are authored against the stage 6 locked
timings: in the narrated branch a scene's duration is its measured speech
duration from `durations.json`, and the animation is timed to the audio,
never the reverse.

### 9. Validate the package (HARD GATE)

Re-run the stage 3 validation over the complete package, scenes and
datasets included:

```bash
python3 scripts/motion_contracts.py validate <job-dir>
```

Zero findings, or the job does not render. The gate also owns determinism
at the contract level: a scene whose state depends on seek order, wall
clock, or unseeded randomness fails here, not after the render. Readiness
levels, stated honestly at every report: `SCHEMA_VALID` (this gate),
`INPUTS_READY` (every file, font, and runtime reference resolves with its
hash), `PREVIEW_READY` (stage 10 evidence exists), `DELIVERED` (stage 15).
Nothing is reported at a level it has not reached.

### 10. Preview

Render previews and proof stills through the adapter layer at the job's
actual canvas, aspect, and timing; a preview that differs from the final
composition in layout or timing proves nothing. The preview model is
`references/preview-and-review.md`: the composition is authored at the
canonical canvas and scaled with aspect preserved, at the full authored
fps; the only reduced-fps artifact is the labeled `rough_layout_only`
preview, which the motion gate refuses as motion evidence. Produce the
proof states the storyboard declares (initial, proof, final) and
full-runtime review material (the MG-031 bundle,
`references/review-evidence.md`: covered plus omitted runtime accounts
for exactly 100 percent, and the bundle tool never prints PASS), and
look at them before asking for approval. For narrated work
the preview is synchronized: proof states and timed events are checked
against the locked narration on the compiled frames, not against a
guessed duration.

### 11. Approvals

Approvals are records, not chat memory: authenticated approval entries
bound to the exact content revision they approve, under the job's
`approval_policy`. The gate contract (design, render, and delivery
gates, issuer trust, and the revision each approval binds) is
`references/approvals-and-gates.md`. The production render permit is
the gate-verified preview approval for the current full revision; the
delivery approval is enforced later, at stage 15, after final QC. The
dispatcher refuses a final render attempted without that permit with
`MG_APPROVAL_REQUIRED`. Nobody writes their own approval, and a diagnostic
or fixture render is never promoted as client-ready.

### 12. Render

Render through the `MotionDispatcher` and the production adapters; callers
never invoke an engine's CLI or an adapter directly. Routing follows
`references/renderer-routing.md`, capability requirements beyond the
baseline must be confirmed by a ready capability record, and a capability
failure is an explicit error (`MG_CAPABILITY_MISSING`), never a quiet
downgrade or a substitution. Every render result is a receipt naming the
engine and the exact runtime (version and runtime-lock identity) that
produced it. Per-scene renders parallelize up to the resource budget.

### 13. Sound by mode

The mode's audio ownership decides this stage; there is no other branch:

- `powerpoint_graphic`: silent. No voiceover, no music, nothing attached.
- `vsl_desktop` and `vsl_mobile`: silent inserts. The parent owns narration
  and music; this job creates neither and attaches neither. Timing answers
  to the parent slot and narration cue (stage 6).
- `standalone_video`: the job owns its audio only when the brief requires
  it (`audio.mode` `own`); a silent standalone piece records `none`.
  Narration is not produced at this stage: it was synthesized and
  measured at stage 6, where its durations locked the timeline. This
  stage only finishes the sound (music when the brief requires it,
  stems, mix). The narration is never truncated, re-timed, or
  re-recorded here to fit the picture; a narration change goes back to
  stage 6 and invalidates the timeline and its approvals.

### 14. QC gate (HARD GATE)

Technical QC passes on real evidence before delivery: decoded frame count
and dimensions exactly as planned, event timing on the compiled frames,
audio integrity per the mode's ownership, text legibility at target size,
and review coverage of the full runtime rather than its opening. The QC
contract is `references/technical-qc.md`: every check is named PASS,
FAIL, SKIPPED_WITH_REASON, or NOT_RUN against the compiled plan, and
the report at `qc/final-qc.json` is the record the delivery gate
consumes. Creative review is judged separately under the evidence-bound
rubric (`references/critique-protocol.md`), validated on write by
`scripts/review_rubric.py`; the dashboard receipt renders from those
records and is never edited by hand. A check
that did not run is reported as not run. A failed check blocks delivery;
it is never relabeled as passed.

### 15. Package and deliver

Deliver exactly what the mode contract requires (directive Section 4.1):

- `powerpoint_graphic`: H.264 MP4, poster PNG, placement and playback
  metadata, and the source package.
- `vsl_desktop`: the slot-length MP4, poster, and timing/source metadata,
  handed back to the parent VSL job named in the handoff (plus a qualified
  alpha master only when one was requested and confirmed).
- `vsl_mobile`: the recomposed vertical MP4, poster, and mobile safe-area
  metadata, handed back to the same parent.
- `standalone_video`: the finished MP4, poster, and the source and
  timeline package, with audio stems and captions when they apply.

Each mode is delivered by its shipped producer: PowerPoint components
by the governed packager (`scripts/powerpoint_package.py`,
`references/powerpoint-packaging.md`), desktop and mobile VSL inserts
through their handoff producers (`scripts/vsl_handoff.py`,
`scripts/vsl_mobile.py`), and standalone videos by
`scripts/build_standalone.py`. Presentation decks consume the packaged
component through the existing presentation pipeline
(`references/integration-contracts.md`), never a second deck builder.
Playback inside Microsoft PowerPoint is UNVERIFIED on every platform;
the package proves embed structure and hashes only.

Record the delivery in `delivery/deliverables.json` with the actual
artifact hashes, and close the job through the status layer
(`references/status-and-delivery.md`): `deliver()` re-checks every
mandatory artifact by measurement, names anything missing, and writes
the delivery receipt only when the job is complete. "Done" is never
recorded for a missing output.

## Legacy compatibility path (explicit choice only)

The V1 pipeline is a compatibility path for existing V1 jobs, reached only
by an explicit operator choice. It is never the default for a new job,
never a fallback when a V2 render fails, and never presented as a peer
workflow. A V2 job's manifest pins `rendering.allow_legacy_fallback` to
false; there is no silent route from a V2 job to this path.

Entry is through migration, non-destructively:

```bash
python3 scripts/migrate_manifest.py <v1-manifest.json> --mode <mode> --company-id <id> [--job-id <id>] [--engine remotion|hyperframes]
```

The migrator refuses to guess: without `--mode` or `--company-id` it
writes only a needs-input receipt and exits 2, and it refuses VSL modes
because a V1 manifest carries no parent. It preserves the V1 input
untouched, accounts for every V1 value in `migration-receipt.json` (mapped,
inferred, or preserved unmapped, with reasons), and writes each V1 scene
record verbatim to `scenes/<scene-id>.legacy.json`. Those scenes stay on
this compatibility path until each is re-authored against a registered V2
component; they are never rendered as native V2 scenes.

On this path, the run follows the V1 order below, inside this same
wrapper's intake and approval discipline. Its scene contract is
`references/animation-contract.md` (`window.__setTime(t)` as a pure
function of time) with `references/motion-grammar.md` as the design
constitution:

1. Pre-production and brief (stage 4 above), brand bible, storage root
   (stage 2 above); the run folder holds the V1 `manifest.json`,
   `script.txt`, `scenes/`, and `audio/`.
2. Model selection exactly as stage 7; the choice is recorded in the V1
   manifest as `animation_model` with the provider and harness recorded in
   the run records.
3. Scene animation code, one HTML file per scene, linted with
   `python3 scripts/lint-grammar.py <scene.html>`. Lock the BPM in the
   brief (manifest `music_bpm`, default 120); the beat grid is derived
   from it by `scripts/beat-grid.py`, so animation proceeds against the
   theoretical grid while synthesis runs in parallel.
4. Preview gate (HARD): every scene previewed with
   `node scripts/render.js --preview` under the shipped preview model
   (`references/preview-and-review.md`): the scale derives from the
   manifest canvas (default scale 0.5, aspect preserved) at the
   manifest fps. `--rough` is the only reduced-fps mode and its
   artifacts are labeled `rough_layout_only`; they can never satisfy
   the full-fps motion gate. Spot-check stills with `--still`, rough
   cut assembled, operator approval per scene.
5. Critique gate (HARD): build the complete-runtime bundle
   (`bash scripts/critique-bundle.sh`, the MG-031 builder: coverage
   verdict `complete`, covered plus omitted runtime accounting for
   exactly 100 percent; the tool never prints PASS) and have a fresh,
   independent critic score it under
   `references/critique-protocol.md`. The shipped rubric governs:
   self-approval is refused, there is no minimum round count,
   correction is capped at five rounds, a claimed 10 is refused
   against an uncalibrated reference, and a `ship` verdict requires
   every applicable dimension at 9 or higher with no unresolved
   critical defect. Review records are validated on write
   (`scripts/review_rubric.py validate`); the dashboard receipt
   renders from the records.
6. Determinism gate (HARD): `node scripts/verify-determinism.js` per
   scene; cold probe frames must match post-seek frames exactly.
7. Voiceover: `python3 scripts/tts.py` segments the narration text at
   sentence boundaries into provider-limited transport chunks (default
   cap 4,000 characters per request, configurable in the manifest; no
   per-scene minimum and no padding), with the same voice settings on
   every request; models and rules in `references/fish-audio-tts.md`.
   Measured durations land in `durations.json` with the narration
   fingerprint and set scene timing (audio-first: the animation renders
   to the audio); changing the narration changes the fingerprint and
   invalidates those timings.
8. Preflight: `node scripts/preflight.js`; follow its worker and segment
   recommendation, never a hardcoded count.
9. Full render: `node scripts/render.js --resume`, one process per scene
   in parallel up to the preflight count; each scene's frames are deleted
   right after its segment encodes.
10. Sound and assembly: score and SFX synthesized in code
    (`scripts/synth-score.py`, `scripts/synth-sfx.py`) unless the manifest
    names a supplied `music_bed`; `bash scripts/assemble.sh` joins with
    crossfades, lays one continuous score, ducks it under the voiceover,
    lands at -14 LUFS. Mix-only changes re-mux with
    `node scripts/render.js --mux` instead of re-rendering.
11. QC gate (HARD): `bash scripts/qc.sh` (MG-034 technical QC,
    references/technical-qc.md: every check named PASS, FAIL,
    SKIPPED_WITH_REASON, or NOT_RUN against the compiled plan; a tool
    failure or missing evidence fails the gate, never passes it; the
    legacy invocation keeps its manifest-derived lane), then the human
    30-second review of the sheets, then `bash scripts/sweep-chromium.sh`.
12. Delivery: the MP4 from the run folder with the contact sheet; keep the
    animation sources, voiceover audio, script text, manifest, beats,
    score params, and review log. Frame PNGs are always deleted.

## Maintenance check

`bash verify.sh` is for installation and update verification. It is not
part of any normal job, on either path.
