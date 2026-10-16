# Timeline compiler (MG-021)

The shared timeline compiler is the single place where picture and sound
durations become placed frame ranges. Before it existed, the crossfade
chain shortened the picture while narration, caption, and SFX offsets kept
being computed from unshortened scene durations, so every consumer did its
own arithmetic and the copies disagreed. Scenes, transitions, captions,
narration, and SFX now declare durations, overlaps, and cues, and
`compileTimeline` (runtime/src/timeline/) compiles the one authoritative
plan. Downstream code consumes the plan; it never recomputes placement.

## Outputs

A successful compile returns two documents:

1. **timeline.json**, the canonical contracts document
   (references/contracts-v2.schema.json, `$defs/timeline`): placed scene
   ranges (`start_frame`, `end_frame_exclusive`, `source_start_frame`,
   `transition_in_frames`, `transition_out_frames`), cue events,
   `parent_slot`, `audio_owner`, `total_frames`. The compiler validates
   its own output against the canonical schema before returning it; a
   violation is a compiler bug surfaced as a finding, never shipped.
2. **The compiler sidecar** (`TimelineSidecar`, schema_version "1.0"),
   which carries everything the canonical `$def` has no room for:
   - overlap handles: id, the two scenes, the single owner, the placed
     overlap region, its midpoint (frame times two, and in samples);
   - cue resolutions: frame, sample, anchor kind, anchor reference;
   - narration, caption, and SFX placements in frames and samples;
   - per-scene source-media ranges in frames and samples;
   - property-write overlaps that were declared intentional;
   - the slot record: parent range, granted handles, used handles;
   - the sample rate and rounding rule the plan was compiled under.

   The canonical schema is not edited to make room for these fields.
   Integration note: if a future contracts revision wants them in the
   canonical document, the candidates are the handle ownership records
   and the cue anchor records; until then the sidecar is the contract,
   keyed to the timeline by `job_id` and scene id.

## The model

- All internal time is integer frames in half-open intervals
  `[startFrame, endFrameExclusive)` (directive Section 5.4). A scene of
  N frames renders frames 0 through N-1 of its range. Duration is the
  difference of the endpoints.
- Scenes declare content durations only. The compiler places them in
  declaration order: the first scene starts at output frame 0; each
  later scene starts at the previous scene's placed end minus the
  declared transition's frames. **The overlap is subtracted exactly
  once, in that step.** No scene ever subtracts an overlap on its own,
  and two adjacent scenes never each subtract another copy of it.
- A boundary carries at most one transition record. A transition joins
  adjacent scenes only, and its frames must leave both scenes a
  positive solo region (incoming plus outgoing overlaps must total
  less than the scene's duration).
- Every overlap has **exactly one owner** (Section 5.4), one of its two
  scenes, named in the transition record and carried into the sidecar
  handle record. Ownership decides which scene's rendering is
  authoritative inside the shared region when MG-022 assembles the
  overlap; the compiler records it, assembly obeys it.

## Programs and slots

- **Program mode** (full programs): overlaps are explicitly allocated
  in the plan, and the total is whatever the placement produces. Six
  5-second scenes with five half-second overlaps at 30 fps compile to
  825 frames, 27.5 seconds, not 30: the plan says so, in numbers, once.
- **Slot mode** (fixed-duration VSL inserts): scenes are placed in
  slot-local frames starting at 0, and the compiled total must equal
  the parent slot length **exactly**. Longer is `TIMELINE_SLOT_OVERFLOW`,
  shorter is `TIMELINE_SLOT_UNDERFILL` (declare the full duration:
  lengthen a scene or add a hold; unplanned frames are not a plan).
  The slot is never resized, and the parent narration is never
  shortened to make an insert fit.
- **Edge transitions and handles**: an insert may fade across the slot
  boundary only inside handles the parent grants (`grantedHandles`).
  Used handles are recorded on the first scene's `transition_in_frames`
  and the last scene's `transition_out_frames` and in the sidecar slot
  record. They live in the parent's frames, outside the slot, and never
  change the slot total. Using more than granted fails with
  `TIMELINE_HANDLE_NOT_GRANTED`.

## Sound: samples and the one rounding rule

- The compiled timeline's audio rate is **48000 Hz**: the delivery rate
  of the pipelines this compiler feeds (the webinar/VSL assembly
  delivers H.264/AAC in MP4 and its measured presenter audio is
  48000 Hz), and at both contract frame rates it yields an integer
  number of samples per frame (1600 at 30 fps, 800 at 60 fps). Legacy
  Skill 72 synth helpers synthesize source audio at 44100 Hz; those are
  source assets that assembly resamples (MG-023), not the compiled
  rate.
- Integer frame positions convert to samples **exactly**
  (`frame * 48000 / fps`). No rounding is involved and none is applied.
- Sub-frame positions (music-beat grids, measured word boundaries)
  convert under **one rounding rule: round half up**, `floor(x + 0.5)`,
  applied to the exact value, for both frames and samples. A position
  exactly halfway lands on the later unit. There is no second rule and
  no re-rounding downstream.
- **Narration is authoritative.** Narration segments are placed as
  measured (MG-020 compiles scene timing from measured narration). A
  segment ending past the compiled picture fails with
  `TIMELINE_NARRATION_EXCEEDS_PICTURE`; the compiler never truncates,
  pads, or shortens narration to fit picture arithmetic, and `-shortest`
  style concealment has no equivalent here. Overlapping narration
  segments fail (`TIMELINE_NARRATION_OVERLAP`): one stream cannot speak
  twice at once.

## Cues and anchor kinds

Every cue declares exactly one anchor kind:

- `semantic_state`: a named state at a scene-local frame (for example
  the frame a chart reaches its final values). Resolves to
  placed scene start plus the local frame; the local frame must lie
  inside the scene.
- `spoken_word`: a word in a measured narration segment, by segment id
  and word index. The cue's sample is the word's measured start sample,
  exactly; its frame is the frame whose interval contains that sample.
  A missing segment or word fails with `TIMELINE_ANCHOR_UNRESOLVED`.
- `music_beat`: a beat index on the plan's music grid (`bpm`,
  `firstBeatFrame`). Frame and sample are each computed from the same
  exact beat position in seconds under the one rounding rule. A beat
  cue with no grid fails with `TIMELINE_ANCHOR_UNRESOLVED`.

A cue whose resolved frame lands outside its declared scene fails with
`TIMELINE_CUE_OUTSIDE_SCENE`: a cue that fires in a different scene than
it claims is a planning error, not a detail.

Cue events enter the canonical timeline's `events` array with the
canonical types (`reveal_start`, `proof`, `hold_start`, `cue`), sorted
by frame then id; the sidecar carries the anchor detail the canonical
event shape cannot.

## Animated property writes

A property track lists the writes to one animated property in one
scene, in scene-local frames. Overlapping writes to the same property
fail with `TIMELINE_PROPERTY_WRITE_OVERLAP` unless the later write
declares `intentionalOverlap: true` (a deliberate crossfade between two
states of one property, for example). Declared overlaps are recorded in
the sidecar with both write indices and the overlapping region, so a
reviewer can see exactly which overlaps were chosen rather than
happened.

## Engine exports (data contracts)

`toRemotionTiming` and `toHyperframesTiming` adapt the compiled plan at
the engine boundary, the one place Section 5.4 permits representation
changes:

- **Remotion** consumes integer frames: per scene, `fromFrame` and
  `durationInFrames` for sequence placement, plus the **inclusive**
  range `[start, end - 1]` for APIs that take a frame range, produced
  by the shared `toInclusiveRange` in remotion/frame-math.ts. The
  exclusive endpoint is never passed through unchanged.
- **Hyperframes** consumes seconds: per scene, `startSec`,
  `durationSec`, `endSec`, and transition seconds, each `frames / fps`,
  the identical definition to `seconds()` in hyperframes/project.ts.

Neither export nests one engine inside the other (Section 3.3); each is
a flat per-scene record.

## Consumption contract for MG-022 and MG-023

- MG-022 (assembly) consumes the compiled plan for concatenation and
  transitions: scene order and placed ranges from the canonical
  timeline, overlap regions and their single owners from the sidecar
  handles, source-media ranges from the sidecar scene records. It must
  not recompute scene starts from durations, and it must not use
  `-shortest` to conceal a mismatch: a mismatch between media and plan
  is an assembly failure with the plan as the reference.
- MG-023 (audio) consumes narration, caption, and SFX placements from
  the sidecar, in samples, under the recorded rate and rounding rule.
  Resampling of 44100 Hz source assets to the compiled 48000 Hz happens
  there, once, against these sample positions. Ducking and mixing read
  narration ranges from the plan; they do not re-measure.
- MG-025 (approvals) binds approval records to the compiled plan: the
  canonical timeline plus sidecar are the timing artifact whose hash an
  approval covers, so any recompilation that changes a placed range, a
  handle, or a cue invalidates timing approvals by construction.

## Failure discipline

Bad input is findings, never exceptions and never silent adjustment.
Shape problems (unknown keys, non-integer frames, fps outside the
contract rates, duplicate ids) are `MG_SCHEMA_INVALID`. Doctrine
violations are `MG_TIMELINE_INVALID` with a stable named rule at the
start of the message (`TIMELINE_NARRATION_EXCEEDS_PICTURE`,
`TIMELINE_SLOT_OVERFLOW`, `TIMELINE_HANDLE_NOT_GRANTED`,
`TIMELINE_PROPERTY_WRITE_OVERLAP`, and the rest; the full list is
exercised in runtime/tests/run-timeline.ts). Exit class follows the
contracts family: 2.

## Tests and evidence

runtime/tests/run-timeline.ts (39 checks) pins the directive's
acceptance anchors and every named failure against the fixtures in
tests/fixtures/timeline/. Expected numbers live in
tests/evidence/mg021/measurements.json, a static record the suite
asserts on every run and never rewrites.
