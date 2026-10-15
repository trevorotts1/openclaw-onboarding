# Integration contracts: motion in the presentation pipeline (MG-036)

How a Skill 72 motion component travels through the EXISTING
presentation pipeline (directive Section 14, patch points P01-P08):
declared in slides.json, authenticated at build time, embedded in the
deck by the pipeline's own assembly, audited by a canonical pipeline
phase, and reused by the webinar build as the same component. There
is no standalone deck builder in this path and no second scheduler.

Code: `build_deck.py`, `motion_phase.py`,
`presentation_job/motion.py`, `presentation_job/defers.py`,
`build_webinar_video.py`, `webinar_ffmpeg.py`,
`presentation_job/deliverables.py` (all in the presentations scripts
tree), plus `slides.schema.json` (P01) and `PIPELINE-MANIFEST.json`
(P08).

## The declaration (P01)

Each slide carries an optional typed `media` object
(`slides.schema.json`). Absent media means `{"kind": "still"}`: the
deterministic KIE still, every existing gate unchanged. The motion
alternative names, with run-relative paths:

- `motion_manifest_path`: the Skill 72 job manifest
  (e.g. `working/motion/slide-02/manifest.json`)
- `approved_render_receipt_path`: the approved render receipt
  (e.g. `working/motion/slide-02/renders/artifacts.json`)
- `poster_path`: the poster PNG
  (e.g. `working/motion/slide-02/delivery/poster.png`)
- `placement`: a rectangle normalized to the slide (inside [0,1],
  preserving the component's 16:9)
- `playback`: `{start, repeat, end}` in the canonical contracts-v2
  playback vocabulary
- `webinar_policy`: `{fit, duplicate_audio}` with fit one of
  `exact_slot`, `hold_final`, `approved_loop`

`media` is the media choice; it is never the image-generation `mode`
field, which still governs still rendering only.

## The election (B14 seam semantics)

Motion is elected per deck, never default: intake field
`want_motion_graphics` (capture key `WANT_MOTION_GRAPHICS`), resolved
through `presentation_job.defers` with the same waiver discipline as
`want_vsl_page`; absent an explicit yes the answer is NO. Hard cap:
2 motion pieces per deck. Slot A is slide 1; Slot B is a section
divider (per the run's arc allocation). A piece is a silent
1920x1080, 30 fps, H.264 (yuv420p) MP4 of 4.0 to 8.0 seconds and at
most 20 MB. Its poster is byte-identical to the package poster and to
the slide's QC PNG (`renders/slide-NN.png`); the still under the
embed is that poster derivative, recorded as such, so PDF/export
shows the readable final state and the movie is never obscured by an
opaque poster layer. A diagnostic deck is never delivered as the
client's presentation.

## The package and the receipt (what validation consumes)

The slide's motion workspace holds the job manifest and receipt at
the declared paths, the poster at the declared path, and the
governed MG-035 delivery package under `package/`
(`package-record.json`, `component.mp4`, `poster.png`,
`final-qc.json`, `source/`). The render receipt contract: a JSON
object carrying the job identity (`job_id`) and the rendered
artifact's sha256 (`artifact_sha256`), with an approval status
(`status: "approved"` or an equivalent completion state) when it
carries one. The package record is the identity authority: the
component counts as the package whose `source_job.manifest_sha256`
equals the declared job manifest's hash, whose QC record (bound by
`qc.record_sha256`, verdict pass) binds the same artifact hash, and
whose poster hash the declared poster matches byte for byte.

## Authentication at build (P02/P03)

`build_deck.validate_motion_slide_artifacts` authenticates every
declared motion slide in the current run, in this order: media
shape; election; slot; placement (inside the slide, 16:9); path
containment (symlinks resolved BEFORE the check; escapes refused);
package record identity and manifest binding; the MG-034 QC verdict
consumed by record (never re-run, never imported); artifact
presence, hash, and the B14 limits judged on the package record's
own probe; receipt binding (job identity, artifact hash, approved
status); poster parity (declared poster, packaged poster, and the
slide's QC PNG when the render exists); playback parity with the
package record; webinar-fit qualification (`approved_loop` requires
a loop-qualified package whose loop-seam check passed; `hold_final`
requires its approved stable final frame); the temporal copy
inventory (every approved copy line must be a state the component
actually shows: its final-state essential text or the validated
dynamic chart labels/values in its job records); and the motion
copy-density policy (the final readable state's essential text must
fit the still-slide copy band ceiling of 180 characters, the ceiling
declared in `presentation_job/motion.py`).

Every failure degrades the slide to its static render with a
`MOTION_*` reason code in `working/checkpoints/motion.json`. The
planner (`plan_motion_media`) runs at preflight
(`_chk_motion_media`, which never hard-fails: degrade is the
contract) and again in `main()` before assembly, so poster parity is
judged against the renders that actually exist. Generated image
assets inside a motion scene keep their own KIE/provider gates; the
motion branch grants no exemption from them.

The two FIX-2 checks take the narrow authenticated path only (P03):
`check_image_qc_vision` exempts a live-authenticated motion poster
from the flat-fill sub-check (never the byte floor) because a data
chart's subject is judged by the motion path's own proofs, and
`check_canonical_render_path` exempts files inside a live
authenticated motion workspace. Authentication is recomputed at
check time (full validation plus live hash parity); a filename, a
declaration, or a stale record earns nothing.

## The embed (P04)

`assemble_pptx(..., motion_media=...)` routes validated slides to
`add_motion_media`, which embeds through python-pptx's movie
primitive (`slide.shapes.add_movie`, explicit geometry from the
normalized placement converted with the deck's actual dimensions,
`poster_frame_image` = the authenticated poster,
`mime_type="video/mp4"`). This replaces the producer mechanism of
MG-035's package-level adapter with the same parts and
relationships, created inside the pipeline. Playback is applied to
the timing node the library writes (start condition indefinite for
`on_click`, 0 for `automatic`; `repeatCount="indefinite"` for loop;
`fill="hold"` for hold_final): no python-pptx autoplay setter exists
or is invented, and the tests pin the written XML against a stored
expected fixture. Assembly builds a fresh Presentation and saves
atomically, so re-running assembly cannot duplicate media;
`finalize_motion_record` then proves each embed from the assembled
deck's own media parts (byte hash against the authenticated
artifact) and records `embedded` or `MOTION_EMBED_MISSING`.
`notes_sync_pass` semantics are untouched (never raises, status
dict, idempotent, atomic save).

## The phase (P08)

`P8.15-MOTION` (order 8.15, owner `pptx-assembly-specialist`,
executor kind `script`, `scripts/motion_phase.py --run-dir
{run_dir}`, dispatched by `Engine.run_phase` like every script
phase) consumes `working/copy/slides.json` and `*-FINAL.pptx` and
produces `working/checkpoints/motion.json` and
`working/checkpoints/slide_media_manifest.json`. It always runs (a
non-elected deck passes with the election recorded). It re-proves
claimed embeds against the delivered deck, requires a reason code
on every degrade, records pieces that authenticated after assembly
as `produced_late_not_embedded`, and writes the slide-media
manifest P9.6 consumes. `phase_verifiers._verify_motion_phase`
independently re-hashes the delivered deck before attesting.
Pipeline lockstep: manifest_version 71 with `MIN_MANIFEST_VERSION`
and the phase budget entry moving together, and the manifest hash
registries (`MANIFEST-SOURCE.txt`,
`universal-sops/_content-manifest.json`) recomputed in the same
change. The version and its mirrors were updated deterministically
in the same commit without running `bump-version.sh`: the note in
`presentation_job/deliverables.py` reserves that script's lockstep
to the orchestrator and no Skill 72 item runs it, and MG-048's
branch update re-checks the mirrors via `sync_check.py`. Divergence note: current main's `phases.py` dispatch was
read at build time; its `executor_kind` structure is identical to
the local base's, so this phase lands against both unchanged (the
addition lives in the manifest, the script, and the verifier
registry, not in `phases.py`).

## The webinar reuse (P05/P06)

`build_webinar_video.resolve_slide_media` reads the slide-media
manifest (or derives it from `motion.json`) and hash-verifies every
clip inside the run root before use; a broken record fails the
build by name. `webinar_ffmpeg.render_webinar(..., slide_media=...)`
routes those slides to `prepare_motion_clip`: the preanimated
component is conformed to the output geometry and its parent slot
under its declared fit (frame-exact for `exact_slot`; final-frame
hold for `hold_final`; looping for `approved_loop`) with no Ken
Burns pass, no fade pair, no speed change, and no audio (`-an`).
Prepared clips join the same per-slide clip list as the stills, so
the xfade chain is computed from ACTUAL probed durations exactly as
before, and the parent narration slice is unchanged: the narration
keeps its length and no second TTS/music branch exists. A clip
longer than its slot is refused by name
(`MOTION_CLIP_EXCEEDS_SLOT`): reauthoring or a parent timeline
revision is the remedy, never silent truncation.

## Deliverables (P07)

Motion artifacts are conditional component dependencies nested
under the canonical deliverables in
`presentation_job.deliverables.MOTION_COMPONENT_DEPENDENCIES`
(the clip and poster under `deck_pptx`, the poster under
`deck_pdf`, the clip and its source evidence under `webinar_mp4`),
resolved against the live `DELIVERABLE_AUDIT_SPEC` by
`motion_component_dependencies()`. They are never top-level bundle
items: the canonical bundle stays exactly the manifest's
`build_bundle_files`, and a still-only deck owes no motion
components.

## Platform truth and known seams

- PowerPoint playback is UNVERIFIED on every platform. What is
  proven is structural: the media is embedded in the deck file,
  byte-identical after the deck is moved, with the poster as the
  slide's image. PDF fallback evidence comes from the tools this
  platform actually has (LibreOffice), never from PowerPoint's name.
- Poster rule divergence, recorded: the B14 trimmed mode speaks of
  frame 0 matching the poster; a governed MG-035 package's poster
  is deliberately the piece's FINAL readable state (its poster
  selector refuses mid-reveal frames). The governed path enforces
  poster byte-identity (declared poster = packaged poster = the
  slide's QC PNG) and does not claim frame-0 parity for reveal
  pieces.
- The font naming seam (alias token vs resolved family across the
  contracts schema, the runtime registry, and the QC font check) is
  documented in `references/powerpoint-packaging.md`; delivery
  packages restate the requirement under the resolved family name
  with the intake record retained.
