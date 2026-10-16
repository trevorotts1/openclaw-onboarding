# Mobile VSL vertical derivative: the recomposition contract (MG-038)

Status: implemented and acceptance-tested on the build's fixtures
(`tests/unit/test_vsl_mobile.py`,
`tests/unit/test_vsl_mobile_acceptance.py`, evidence in
`tests/evidence/mg038/`). The parties are the same as the desktop
handoff (MG-037, `references/vsl-desktop-handoff.md`): the
**parent job** owns the VSL; **Skill 72** owns the motion insert.
This layer derives the mobile presentation of the same approved
message. The governed mode configuration is
`references/vsl-mobile-mode.json`; the machine-readable record
contract is `references/vsl-mobile-schema.json` (this layer's own
versioned schema; the canonical `contracts-v2.schema.json` is not
edited by this layer), executed by `scripts/vsl_mobile.py`.

## The one rule

The vertical presentation is **recomposed, never derived from
the desktop master's pixels**. No crop, no uniform scale, no
letterbox. The derivative is its own job: staged from the same
handoff facts (parent identity, slot, spoken-word cue, copy,
dataset, visual direction), with the scene's `layout_variant`
set to `portrait`, so the shipped component renders the design
record's portrait layout and the chart geometry is re-derived
from the dataset against the portrait plot. For the shipped C05
fixture that means plot x 200, width 740, rows at y 520, 820,
1120, bar height 100 on a 1080x1920 canvas, where the landscape
layout is plot x 420, width 1200, rows at y 360, 520, 680. The
delivery record proves the distinction numerically (below).

## Ownership

Unchanged from the desktop contract: narration, music, captions,
and the delivery ledger belong to the parent; the insert belongs
to Skill 72; slot timing is declared by the parent and enforced
by both sides. The derivative contributes no audio of its own:
the mode manifest pins its audio to `inherited` with
`create_voiceover: false` and `create_music: false`, exactly as
the desktop mode does.

## The mobile handoff record

One JSON document (`vsl_mobile_handoff`, schema version 1.0).
Everything the desktop handoff carries, plus the mobile facts:

- `parent`: the same parent identity, slot, fps, and
  spoken-word narration cue as the desktop handoff, with
  `parent.canvas` at 1080x1920. The slot and the cue are the
  parent's, shared by both modes: the derivative answers the
  same cue in the same slot of the same parent timeline.
- `derivative_of {desktop_handoff_id, desktop_job_id}`: the
  desktop production this derivative derives from. A mobile
  handoff that names no desktop job is refused
  (`VSL_MOBILE_DERIVATIVE_MISSING`): the vertical delivery is
  bound to an approved desktop production, never an unrelated
  composition wearing a mobile canvas.
- `narration {asset_ref, sample_rate, segments}`: the parent's
  narration timing record: the asset reference the parent
  declares as `parent.audio_ref`, and the segments with their
  word timings in absolute samples. This is the record the fit
  check resolves the cue against.
- `captions` and `caption_profile`: the parent's caption spans
  (id, frame range, role) and the mobile caption profile
  (authored size and placement; the governed defaults live in
  the mode configuration: 64 px, lower third, role
  `essential_support`).
- `insert`: the insert's own facts, as on desktop. Its job id is
  its own (`fixture-vsl-mobile` on the fixtures): the derivative
  is a separate job with a separate approval and layout hash,
  not a variant flag on the desktop job.
- `return_requirements`: as on desktop.

### Named failures (all before anything renders, unless noted)

| Code | Category / exit | Condition |
| --- | --- | --- |
| `VSL_MOBILE_SLOT_TIMING_MISSING` | MG_TIMELINE_INVALID / 2 | no slot, or slot frames missing |
| `VSL_MOBILE_SLOT_RANGE_INVALID` | MG_TIMELINE_INVALID / 2 | slot empty or reversed |
| `VSL_MOBILE_CUE_MISSING` | MG_TIMELINE_INVALID / 2 | no narration cue anchor |
| `VSL_MOBILE_CUE_FRAME_MISMATCH` | MG_TIMELINE_INVALID / 2 | cue frame is not the slot's first frame |
| `VSL_MOBILE_INSERT_EXCEEDS_SLOT` | MG_TIMELINE_INVALID / 2 | insert longer than its slot (the remedy is a parent timeline revision, never a stretch) |
| `VSL_MOBILE_INSERT_UNDERFILLS_SLOT` | MG_TIMELINE_INVALID / 2 | insert shorter than its slot |
| `VSL_MOBILE_AUDIO_OWNERSHIP_VIOLATION` | MG_MODE_MISMATCH / 2 | narration owned by the insert, insert narration assets declared, or insert sound declared in this mode |
| `VSL_MOBILE_CANVAS_MISMATCH` | MG_MODE_MISMATCH / 2 | the handoff's canvas is not 1080x1920 |
| `VSL_MOBILE_DERIVATIVE_MISSING` | MG_INPUT_MISSING / 3 | no desktop job named as the derivation source |
| `VSL_MOBILE_NARRATION_MISSING` | MG_INPUT_MISSING / 3 | no narration timing record |
| `VSL_MOBILE_NARRATION_MISMATCH` | MG_MODE_MISMATCH / 2 | the narration record names a different asset than the parent declares |
| `VSL_MOBILE_CUE_ANCHOR_UNRESOLVED` | MG_TIMELINE_INVALID / 2 | the cue's segment or word is absent from the narration record |
| `VSL_MOBILE_SCHEMA_INVALID` | MG_SCHEMA_INVALID / 2 | any other shape failure |
| `VSL_MOBILE_CUE_NOT_FRAME_ALIGNED` | MG_QC_FAILED / 6 | the cue word's start sample is not a whole frame |
| `VSL_MOBILE_CUE_RESOLUTION_MISMATCH` | MG_QC_FAILED / 6 | the word timing resolves to a frame other than the cue frame and slot start |
| `VSL_MOBILE_NARRATION_DOES_NOT_COVER_SLOT` | MG_QC_FAILED / 6 | the cue segment does not span the whole slot |
| `VSL_MOBILE_TIMELINE_SLOT_MISMATCH` | MG_QC_FAILED / 6 | the compiled vertical timeline does not total the slot length |
| `VSL_MOBILE_TEXT_BELOW_FLOOR` | MG_QC_FAILED / 6 | an essential text element below its MG-013 floor, named in the message |
| `VSL_MOBILE_CAPTION_BELOW_FLOOR` | MG_QC_FAILED / 6 | a caption below its MG-013 floor, named in the message |
| `VSL_MOBILE_CROP_DETECTED` | MG_QC_FAILED / 6 | the artifact's widths match a uniform scale of the landscape master |
| `VSL_MOBILE_RECOMPOSITION_FAILED` | MG_QC_FAILED / 6 | the decoded frames do not carry the portrait geometry, or the proof is not separable from the forbidden derivations |
| `VSL_MOBILE_ASPECT_MISMATCH` | MG_MODE_MISMATCH / 2 | an artifact handed to the packager (or produced) is not 1080x1920 |
| `VSL_MOBILE_ARTIFACT_DURATION_MISMATCH` | MG_QC_FAILED / 6 | an artifact handed to the packager does not carry the slot's frame count |
| `VSL_MOBILE_QC_FAILED` | MG_QC_FAILED / 6 | the MG-034 gate's verdict on the delivery package is not pass |
| `VSL_MOBILE_MOTION_PROOF_FAILED` | MG_QC_FAILED / 6 | the MG-032 evaluator's verdict is not pass |

## Fit checks (the `mobile_fit_report`)

Produced after the vertical timeline compiles and before the
render; every failure aborts production by name.

- **Narration fit.** `narration.asset_ref` must equal the
  parent's declared `audio_ref` (the same approved narration
  serves both modes; a different asset is refused at validation).
  The cue word's `startSample`, multiplied by the fps and divided
  by the record's sample rate, must be a whole frame and must
  equal both the declared cue frame and the slot's first frame
  (sample-exact integer arithmetic at 48000 Hz, the resolution
  the shipped compiler records as its sidecar cue anchor). The
  cue's segment must cover the whole slot. And the vertical
  insert's own compiled timeline (the shipped MG-021 compiler in
  slot mode) must total exactly the slot length. If the vertical
  composition genuinely needs more visual time, the handoff is
  where a parent timeline revision is requested; the insert is
  never stretched and the narration never shortened (the mode
  pins `allow_speed_change: false` and `allow_slot_resize:
  false`).
- **Text fit.** Every essential element of the portrait layout
  (headline, category labels, values, disclosure) is measured
  against its MG-013 floor from
  `references/typography-tokens.json` (headline 96, chart
  category label 54, chart value 60, disclosure 40). The
  vertical canvas is a full-frame recomposed canvas, so the
  effective displayed size is the authored size on that canvas:
  the tokens' own measurement basis, and MG-035's placement
  audit with a placement scale of 1. The shipped portrait design
  measures headline 112, labels 60, values 64, disclosure 48:
  all above their floors. A staged design with labels at 40 px
  fails `VSL_MOBILE_TEXT_BELOW_FLOOR` naming `category_labels`.
- **Caption fit.** Each caption entry is measured at the
  profile's authored size against its role's floor
  (`essential_support`, 54). The governed profile (64 px, lower
  third) passes for every fixture caption; a 40 px profile fails
  `VSL_MOBILE_CAPTION_BELOW_FLOOR` naming the caption.

## The recomposition proof

Measured on the decoded vertical artifact, recorded in the
delivery record:

- Bar widths at the half-reveal frame (45) and the final frame
  (75), measured in the portrait plot's coordinates, must match
  the portrait derivation from the dataset (half
  [148, 222, 370], final [296, 444, 740]) within 3 px.
- Bar row centroids at the final frame must sit at the portrait
  rows' centers (570, 870, 1170) within 4 px.
- The same numbers are compared against the two forbidden
  derivations. A uniform scale of the landscape master to 1080
  wide predicts widths [270, 405, 675] (and a 1080x607.5 canvas,
  not 1080x1920): the measured widths differ from it by at least
  26 px. A center crop of the landscape master scaled to 1920
  high predicts row centroids at [720, 1004.44, 1288.89]: the
  measured centroids differ by at least 118 px, and the
  landscape plot origin (x 420) falls outside the crop's centered
  source window [656.25, 1263.75], so under a crop the bars'
  left edges would be clipped away entirely, where the measured
  artifact carries all three bars whole from the portrait plot
  origin at x 200. An artifact whose widths match the scale
  prediction is refused as `VSL_MOBILE_CROP_DETECTED`; one that
  matches neither derivation is refused as
  `VSL_MOBILE_RECOMPOSITION_FAILED`.

The artifact also passes the shipped MG-032 motion-proof
evaluator under a portrait case (subject regions taken from the
portrait layout), with an MG-031 coverage bundle bound to the
artifact's own hash: on the acceptance build all four
checkpoint assertions agree three ways (spec derivation,
component geometry, decoded raster) and the verdict is `pass`.

## QC under the mode's own profile

The delivery package (the staged job, the rendered final in
place, the compiled plan) is gated by the shipped MG-034 gate
in its package lane; the manifest the gate reads carries
`mode: "vsl_mobile"`, so the gate judges the package under the
mobile mode's own promises (inherited audio: no audio stream,
no loudness promise; the designed final hold read from plan
data). On the acceptance build the gate's verdict is `pass`.

One disclosure, stated wherever it applies: the gate's font
check compares family names against fontconfig, while the
canonical assets record declares the font requirement by its
runtime-registry alias token (`fixture-sans`), which the gate
cannot resolve (the pending checker fix is recorded in the
MG-037 contract document). Following the MG-035 delivery-stage
convention, the delivery package's QC-facing assets record
declares the requirement under the resolved family name
(`Liberation Sans`, resolved by reading the runtime's shipped
registry source, the same registry the adapter resolves
through and refuses to render without), and the intake record
is retained in the package as `intake-assets.json`. The
delivery record's `font_declaration` carries both names and
this reason. The render itself resolved the alias through the
runtime registry; nothing was substituted.

## The delivery record

`mobile_delivery_record`, written to the delivery directory
beside the artifact: mode, handoff and job identities,
`derivative_of` naming the desktop handoff and job, canvas and
slot, the cue with its resolved frame, the layout block
(variant, the variant's own `layout_hash` over the portrait
layout, canvas, and variant, the portrait plot, and the expected
widths), the mobile variant's own approval record (separate
from the desktop production's approval; fixture context states
`authority_status: "not_verified"`, as the shipped suites do),
the artifact records bound by SHA-256 (MP4, poster at the
required poster frame, source package), the recomposition
proof, the fit verdicts, the motion-proof and QC verdicts, and
the font declaration disclosure.

The packager's gate runs before any of it is written:
`assert_deliverable_artifact` probes the artifact, and a 16:9
desktop master fails `VSL_MOBILE_ASPECT_MISMATCH` with no
delivery record and no copied artifact produced. A vertical
artifact of the wrong length fails
`VSL_MOBILE_ARTIFACT_DURATION_MISMATCH`.

## Producing the derivative

`python3 scripts/vsl_mobile.py produce HANDOFF.json --work DIR`:

1. Validates the handoff (above).
2. Stages the vsl_mobile job package and validates it through
   the shipped contracts layer: zero findings required.
3. Compiles the insert's timeline in slot mode through the
   shipped MG-021 compiler and runs the fit checks; the fit
   report is written into the work directory.
4. Renders the final through the shipped dispatcher and adapter
   under the mobile delivery approval.
5. Measures the recomposition proof on the decoded artifact.
6. Runs the MG-032 motion proof under the portrait case.
7. Builds the QC delivery package and runs the MG-034 gate.
8. Writes the delivery (artifact, poster, compiled timeline
   and sidecar, and the delivery record).

## Honest limits

- The acceptance build is fixture-context (engineering
  fixtures, `authority_status: "not_verified"` approval), the
  same standing as the desktop layer and the shipped mode
  fixtures. A production derivative runs the identical code
  path under the parent pipeline's real approval.
- Captions are fit-checked and ride the parent's caption spans;
  this layer does not burn captions into the picture, on either
  mode.
- Parent-side assembly of the vertical insert into a mobile
  player program is the parent's existing path and is not
  rebuilt here: the slot, cue, and return semantics are the
  desktop contract's, so the parent consumes the derivative
  through the same handoff discipline. The Skill 47 bridge's
  measured assembly report is desktop-shaped (its measurements
  read the landscape layout); extending that report to the
  portrait layout is parent-side work this layer does not
  claim.
- One component is wired end to end (C05, Remotion), as on
  desktop. The contract is component-neutral; a component with
  a genuine portrait layout returns through the same record
  shapes, and one without a portrait layout cannot be staged
  (the adapter fails by name when the design record has no
  layout for the variant).
- The fixture composition shows all three chart categories at
  once, as the desktop composition does; the portrait plot
  carries them truthfully at the measured sizes. A composition
  whose categories cannot stay readable in portrait must reduce
  or stage them without altering totals or comparisons; that is
  an authoring decision the handoff's dataset carries, and the
  text fit check is the gate that refuses a composition which
  tries to shrink its way out instead.
