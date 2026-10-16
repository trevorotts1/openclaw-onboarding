# Intake and the Four Delivery Modes

This is the intake authority for Skill 72. Every job starts here: the
destination (the mode) is decided first, before any job setup, scripting, or
rendering. `INSTRUCTIONS.md` stage 1 runs this intake; stage 3 turns the
answers into the validated V2 job package. The mode contract itself lives in
the canonical schema (`references/contracts-v2.schema.json`) and is enforced
by `scripts/motion_contracts.py`; this document is the plain-language layer
on top of it.

## The first question

Resolve the mode from the current task and any existing manifest first. If
the mode is still unknown, ask exactly this, and nothing else first:

> "Is this for a PowerPoint slide, a desktop VSL, a mobile VSL, or a
> standalone video?"

Then ask only the next missing material question. Never re-ask what the
task, the manifest, or the caller already answered; there is no repeated
questionnaire.

Two defaults, both recorded in the manifest when used:

- A plain "VSL" request with no other signal is `vsl_desktop` (16:9).
  Record that the desktop default was applied. Ask a follow-up only when
  mobile intent is genuinely ambiguous.
- When both desktop and mobile VSL are requested, create linked variants:
  one job per mode, each recording the other in its manifest `variants`
  list. The owner never repeats the brief.

## The four modes

| Mode identifier | Plain language | Canvas | Audio ownership | What comes back |
|---|---|---|---|---|
| `powerpoint_graphic` | A motion graphic that lives on a PowerPoint slide | 16:9, default 1920x1080 | Silent: `audio.mode` is `none` | H.264 MP4, poster PNG, placement and playback metadata, source package |
| `vsl_desktop` | A graphic inserted into a desktop VSL at a named slot | 16:9, default 1920x1080 | The parent owns narration and music: `audio.mode` is `inherited` | Slot-length MP4, poster, timing and source metadata; a qualified alpha master only when requested and confirmed |
| `vsl_mobile` | The same message as a mobile VSL insert, recomposed for vertical | 9:16, default 1080x1920 | The parent owns narration and music: `audio.mode` is `inherited` | Deliberately recomposed vertical MP4, poster, mobile safe-area metadata; a qualified alpha master only when requested and confirmed |
| `standalone_video` | A finished video that stands on its own | 16:9 by default; 9:16 only when explicitly requested | Its own, only when the brief requires it: `audio.mode` is `own`, or `none` for a silent piece | Finished MP4, poster, source and timeline package; audio stems and captions when applicable |

Rules that do not bend:

- PowerPoint output for this assignment is 16:9 and desktop VSL output is
  16:9. A vertical PowerPoint request is rejected under this contract; the
  validator returns `MG_MODE_MISMATCH` for a canvas that breaks its mode's
  aspect.
- Playback inside Microsoft PowerPoint is UNVERIFIED on every
  platform. The mode contract governs the file, the poster, and the
  placement and playback metadata; it does not claim the deck was
  played in PowerPoint. See `references/powerpoint-packaging.md`.
- Mobile VSL is a recomposition, not a crop. The portrait layout is authored
  at 1080x1920 with its own layout record; the mobile example job's scene
  uses the `portrait` layout variant with portrait proof values. Never
  silently turn a desktop VSL vertical because it will be watched on a
  phone, and never call a center crop a mobile composition.
- Default final fps is 30. A deliberate 60 fps override is supported; the
  canvas declares it (`canvas.fps` is 30 or 60) and all timing adapts.
  Playback speed never doubles when fps changes.
- A job may carry several explicitly requested deliverables, each with its
  own layout record (see linked variants above).

## What intake records

Beyond the mode, capture what the job package needs, resolving from context
before asking:

- The message, the audience, and the intended change in belief or
  understanding.
- The intended use and the actual placement (slide position, VSL slot, or
  standalone destination).
- The actual assets and data, with their source rights. Intake never
  invents assets, data, or approvals.
- The brand specification and the essential copy.
- The duration: presenter-friendly length for PowerPoint, the parent slot
  length for VSL inserts, or the approved standalone timeline.
- The desired action the viewer should take.
- The render approval policy (`approval_policy` in the manifest).

## Four separate decisions, never mixed

The manifest keeps four operating dimensions in four distinct fields. Do
not collapse them:

- `mode`: the destination (the four modes above).
- `content_scope`: `insert` versus `full_program` where the mode supports
  it. The three insert modes always record `insert`; the validator enforces
  it.
- `audio.mode`: `none`, `inherited`, or `own`. PowerPoint forces `none`;
  VSL modes force `inherited` with a named `parent_audio_ref`, and a VSL
  insert never creates voiceover or music; standalone never inherits.
- `approval_policy`: who may approve previews and delivery for this job.

Skill 72 normally returns VSL graphics to the existing VSL producer (the
parent). A request for a whole VSL stays owned by that producer, which can
request many Skill 72 components. Standalone motion videos are owned by
Skill 72 when routed here. There are exactly four user-facing modes, not a
menu of subproducts.

## The parent handoff for VSL work

Both VSL modes are inserts into a parent VSL job, and the handoff is a
first-class artifact, `parent-handoff.json`, sitting next to the manifest.
The manifest's `parent` block names the same relationship: `job_id`,
`task_id`, `handoff_path`, the `slot` (a frame range in the parent's
timeline), and the `narration_cue_id` the graphic answers to.

The handoff records:

- The parent job and task identifiers, and the owning company.
- The canvas and fps the insert must match.
- The slot: `start_frame` and `end_frame_exclusive` in the parent's
  timeline. The slot length must equal the insert's `duration_frames`; the
  validator checks this in the manifest, the timeline, and the handoff
  together and returns `MG_TIMELINE_INVALID` when they disagree.
- The narration cue the insert is timed to.
- `audio_owner: parent`, and two hard flags: `allow_speed_change: false`
  and `allow_slot_resize: false`. The insert is never sped up, slowed down,
  or stretched to fit; a slot that cannot hold the message is a brief
  problem to raise with the parent, not a timing problem to hide.

The example jobs for `vsl_desktop` and `vsl_mobile` under
`assets/examples/` each carry a filled handoff of exactly this shape.

## The authoring model is not an intake question

Model selection is not part of mode intake. The authoring model inherits
the explicit current configuration: resolve it in the order in
`INSTRUCTIONS.md` stage 7 (explicit job choice, existing task choice,
client configuration or configured default, then one question). Ask about a
model only when no suitable approved choice exists or an override is
necessary. A recommendation may be offered with reasons as guidance only;
it is never a prescription or a hidden default.

## Legacy V1 jobs

An existing V1 run (the old manifest shape, `references/legacy-manifest-schema.json`,
exemplified by `assets/example-manifest.json`) enters V2 only by explicit
choice, through migration:

```bash
python3 scripts/migrate_manifest.py <v1-manifest.json> --mode <mode> --company-id <id>
```

The migrator never guesses the mode or the owning company; without them it
writes only a needs-input receipt and exits 2. It refuses VSL modes
outright, because a V1 manifest carries no parent and a parent is never
invented. Migration is non-destructive: the V1 input is untouched, every
value the V2 manifest cannot honestly hold is preserved in the migration
receipt, and inferred values are listed as inferred. Migrated scenes stay
on the declared V1 compatibility path (`scenes/<scene-id>.legacy.json`)
until each is re-authored against a registered component; they are never
rendered as native V2 scenes, and legacy rendering is never a default for
any job. See the legacy note in `INSTRUCTIONS.md` for the full statement.
