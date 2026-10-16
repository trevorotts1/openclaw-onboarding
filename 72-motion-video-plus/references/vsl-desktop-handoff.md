# Desktop VSL handoff: the Skill 72 / Skill 47 integration contract (MG-037)

Status: implemented and acceptance-tested on the build's fixtures
(`tests/unit/test_vsl_handoff.py`,
`tests/unit/test_vsl_assembly.py`, evidence in
`tests/evidence/mg037/`). The parties: the **parent job** owns the
VSL (today a Skill 47 movie production); **Skill 72** owns the
motion insert. This document is the contract between them. The
machine-readable contract is `references/vsl-handoff-schema.json`
(this layer's own versioned schema; the canonical
`contracts-v2.schema.json` is not edited by this layer), executed
by `scripts/vsl_handoff.py` (Skill 72 producer) and
`47-movie-producer/scripts/vsl_handoff.py` (the Skill 47 bridge).

## Ownership

| Concern | Owner |
| --- | --- |
| Narration (voice, timing, words) | parent |
| Music bed | parent |
| Captions | parent |
| Delivery ledger, job identity | parent (its job manifest) |
| The motion insert (render, poster, proof) | Skill 72 |
| Slot timing in the parent timeline | parent declares, both sides enforce |
| Final assembly of the VSL | the shipped assembler, driven with the parent's compiled program |

The insert contributes **no audio of its own** in this mode. The
mode manifest pins the insert job's audio to `inherited` with
`create_voiceover: false` and `create_music: false`, and the
assembled VSL's audio is resolved exactly once, from the parent
program's compiled timeline plus the parent's media registry,
through the MG-023 audio policy inside the assembler.

## The handoff record

One JSON document (`vsl_handoff`, schema version 1.0):

- `parent.job_id`, `parent.task_id`, `parent.company_id`: the
  parent job's identity. The insert job and every return record
  carry the same parent id; a return that answers a different
  parent is foreign and refused (`MG_FOREIGN_JOB`, exit 9).
- `parent.scene_id`: the parent scene whose span holds the slot.
- `parent.slot {start_frame, end_frame_exclusive}`: the slot in
  the PARENT timeline, integer half-open frames.
- `parent.fps`, `parent.canvas`: 30 or 60 fps; 1920x1080 for
  `vsl_desktop` (the mode is 16:9).
- `parent.narration_cue {id, segment_id, word_index, frame, kind:
  "spoken_word"}`: the cue the insert answers to, anchored to one
  word of one parent narration segment. `frame` is that word's
  frame in the parent timeline and must equal the slot's first
  frame.
- `parent.audio_ref`: the parent audio asset the insert job's
  manifest names as `parent_audio_ref`.
- `parent.allow_speed_change: false`,
  `parent.allow_slot_resize: false`: fixed by the mode. There is
  no negotiated variant.
- `audio_ownership {narration, music, insert_sound}`: who owns
  each side of the soundtrack. In this mode narration is
  `parent`, music is `parent` (or `none` when the parent program
  has no bed), insert sound is `none`.
- `insert {job_id, scene_id, component_id, component_version,
  duration_frames, copy, dataset, motion, design_ref}`: the
  insert's own facts: its proof and copy (`copy.headline`,
  `copy.disclosure`), its data (the full dataset document the
  component renders), its visual direction (`design_ref` resolves
  to a registered design or an inline design document), and its
  motion window (defaults: reveal frames 15 to 75, hold to the
  end, the shipped C05 convention).
- `return_requirements {artifacts, poster_frame, qc_required}`:
  what the return must contain (any of `mp4`, `poster`,
  `source_package`, `placement_metadata`) and the poster frame.

### Named failures (all before anything renders)

| Code | Category / exit | Condition |
| --- | --- | --- |
| `VSL_HANDOFF_SLOT_TIMING_MISSING` | MG_TIMELINE_INVALID / 2 | no slot, or slot frames missing |
| `VSL_HANDOFF_SLOT_RANGE_INVALID` | MG_TIMELINE_INVALID / 2 | slot empty or reversed |
| `VSL_HANDOFF_CUE_MISSING` | MG_TIMELINE_INVALID / 2 | no narration cue anchor |
| `VSL_HANDOFF_CUE_FRAME_MISMATCH` | MG_TIMELINE_INVALID / 2 | cue frame is not the slot's first frame |
| `VSL_HANDOFF_INSERT_EXCEEDS_SLOT` | MG_TIMELINE_INVALID / 2 | insert longer than its slot |
| `VSL_HANDOFF_INSERT_UNDERFILLS_SLOT` | MG_TIMELINE_INVALID / 2 | insert shorter than its slot |
| `VSL_HANDOFF_AUDIO_OWNERSHIP_VIOLATION` | MG_MODE_MISMATCH / 2 | narration owned by the insert, insert narration assets declared, or insert sound declared in this mode |
| `VSL_HANDOFF_SCHEMA_INVALID` | MG_SCHEMA_INVALID / 2 | any other shape failure |
| `VSL_HANDOFF_JOB_INVALID` | (contracts category) / 2 | the staged job package fails the shipped contracts layer |
| `VSL_HANDOFF_TIMELINE_INVALID` | MG_TIMELINE_INVALID / 2 | the shipped compiler refuses a plan (its finding is carried verbatim, e.g. TIMELINE_SLOT_OVERFLOW) |
| `VSL_RETURN_HASH_MISMATCH` | MG_HASH_MISMATCH / 9 | a returned artifact's bytes differ from the record |
| `VSL_RETURN_ARTIFACT_MISSING` | MG_INPUT_MISSING / 3 | a returned artifact is absent |

Missing shared timing is therefore a targeted named error, never
permission to estimate a different duration silently. The same
rule holds downstream: the assembler probes every segment's
ACTUAL duration and refuses a segment shorter than the compiled
plan (`ASSEMBLE_MEDIA_SHORTER_THAN_PLAN`) instead of trimming or
stretching anything.

## Producing the insert

`python3 scripts/vsl_handoff.py produce HANDOFF.json --work DIR`:

1. Validates the handoff (above).
2. Stages a normal V2 job package under the `vsl_desktop` mode
   manifest (manifest, storyboard, the component's scene spec
   with semantic assertions derived from the dataset and design,
   the dataset, the design, the authoring timeline, and the
   canonical `parent-handoff.json`), and validates the package
   through the shipped contracts layer
   (`scripts/motion_contracts.py`): zero findings required.
3. Compiles the insert's timeline in slot mode through the
   shipped MG-021 compiler (`scripts/vsl-compile.mjs`): the
   compiled total must equal the slot length exactly; the slot
   record and the sidecar are packaged with the job.
4. Renders the final through the shipped dispatcher and adapter
   (`scripts/vsl-render.mjs`) under a delivery approval record.
   In fixture context the approval follows the shipped suites'
   convention and says so: `authority_status: "not_verified"`.
5. Writes the return package (`return_package`) into
   `DIR/return/`: `insert.mp4`, `poster.png` (at the required
   poster frame), the compiled timeline and sidecar, and
   `return-package.json` carrying the artifact hashes and the
   timing record (slot, cue id and frame, insert duration,
   placed range).

The insert is proven by the shipped MG-032 motion-proof evaluator
where the component supports it (C05 does):
`scripts/vsl-proof.mjs` runs the evaluator over the returned MP4
with an MG-031 coverage bundle bound to the artifact's own
SHA-256. On the acceptance build the evaluator's verdict is
`pass` (all four checkpoint assertions agree three ways). The
assembled VSL passes the shipped MG-034 technical QC gate in the
plan lane (20 pass, 0 fail on the acceptance build). The insert
package lane of the same gate passes every media, timing, and
audio check but its verdict is `fail` on exactly one check,
`package.fonts` (`QC_FONT_UNRESOLVED`): the gate compares the
assets record's family alias (`fixture-sans`) directly with
fontconfig's family list, while the runtime resolves that alias
through its own registry to Liberation Sans and refuses to render
with anything else. The isolation experiment is recorded in the
evidence: the identical package, with only the alias string in a
diagnostic assets copy replaced by the resolved family name,
passes the gate in full (19 pass, 0 fail). The mismatch is in the
gate's font premise, not in the package; it is flagged for the
QC owner rather than worked around here, because restating the
package's font record to satisfy the check would break the
adapter's alias resolution. The QC reports name the artifact
hashes they judged; both records are filed beside the return
package in the production work directory, and the acceptance
evidence in `tests/evidence/mg037/` shows the exact commands and
verdicts.

### The canonical parent-handoff cue kind

The canonical schema's `parent_handoff.narration_cue.kind` is
pinned to the constant `fixture_timing_marker_not_real_speech`:
the canonical file can carry the cue's id and frame but not its
spoken-word anchor. The handoff record therefore carries the full
anchor (`segment_id`, `word_index`), the producer maps id and
frame into the canonical `parent-handoff.json`, and the parent
program compile consumes the anchor from the handoff record,
resolving it against the parent's narration word timings (the
sidecar records the resolution as `anchorRef "segment#word"` with
the resolved frame). Widening the canonical cue kind belongs to
the pending contracts-revision decision; this layer does not edit
the canonical schema.

## The Skill 47 bridge

`47-movie-producer/scripts/vsl_handoff.py`, three operations
against the parent's run directory:

- `request --run-dir DIR --handoff H.json`: validates the
  handoff through the Skill 72 producer, checks it names this
  run's parent job (the manifest's `job_id`, or one supplied
  explicitly and recorded; a mismatch is
  `VSL_BRIDGE_PARENT_MISMATCH`, exit 9; no identity anywhere is
  `VSL_BRIDGE_PARENT_IDENTITY_MISSING`, exit 3), files the
  handoff of record at `working/checkpoints/vsl-handoff.json`
  with a request receipt, and opens a `motion_inserts` entry in
  `working/job-manifest.json` (status `requested`). The manifest
  gains one additive key; every existing key keeps its meaning.
- `consume --run-dir DIR --return-dir DIR`: validates the return
  package, checks it answers this run's filed handoff and parent,
  recomputes the artifact hashes, files
  `working/checkpoints/vsl-insert-receipt.json`, and moves the
  ledger entry to `returned` with the artifact records.
- `assemble --run-dir DIR --media-spec S.json`: drives the
  producer's parent assembly (below) with the parent's own media
  package, files the measured assembly report at
  `working/checkpoints/vsl-assembly-report.json`, and records
  the delivery in the ledger entry (status `assembled`, the
  assembled file's hash, byte count, decoded frames, duration).
  A failed measured check records `assembly_failed` and raises
  `VSL_BRIDGE_ASSEMBLY_QC_FAILED` (exit 6).

The bridge does not rebuild or alter
`executive_producer.py`'s attestation or board behavior: status
and board integration with the parent pipeline is a separate
item's scope. The bridge's checkpoints and ledger entries are the
record this handoff owns.

## Assembling the parent VSL

`python3 scripts/vsl_handoff.py assemble-parent HANDOFF.json
--return-dir DIR --media-spec SPEC.json --out FINAL.mp4 --work
DIR`:

1. The return package is re-validated and its hashes recomputed.
2. The parent program is compiled by the shipped MG-021
   compiler in program mode: host scenes around the slot (from
   the parent's media spec), the insert scene at the slot, the
   parent's narration segments with their word timings, the
   parent's captions, and the placement cue anchored to the
   handoff's spoken word. The compiler resolves the cue against
   the word's measured sample position; the sidecar is the
   placement truth.
3. The media registry hands the assembler the RETURNED insert
   MP4 itself (never a copy or re-render), the host segments,
   the parent's narration files, and the parent's music bed,
   with the parent's mix and loudness declarations.
4. The shipped assembler (`scripts/assemble.py`, plan mode)
   builds the final: placement from the compiled timeline only,
   hard cuts at the slot boundaries (the parent granted no
   handle frames, because a boundary-centered crossfade would
   move the insert's first frame off the cue frame; fades the
   parent does grant live in the compiled handles and are
   computed from actual probed durations by the assembler, per
   the P06 discipline), the parent audio resolved once by the
   MG-023 policy, a measured loudnorm finish, and the
   assembler's own encoded-output verification.
5. The assembly workdir also receives
   `qc-approved-intervals.json`: the insert's designed final
   hold, declared from plan data (the handoff's motion window),
   so the QC gate's intent-aware freeze check reads the approval
   from the plan, never from the artifact.
6. Measurements are recorded in an `assembly_report`: decoded
   frame count against the plan total, the cue's resolved frame
   against the slot start, decoded-pixel bar widths at the
   insert's first frame (zero), mid-reveal, and final state
   inside the assembled output, the assembler's input registry
   (exactly the parent's narration segments and one music bed;
   the insert stream set is video-only), per-segment narration
   presence through the MG-023 band analysis, the final-words
   tail report, and the loudness verdict. Any failed check makes
   the report's verdict `fail` and the CLI exit 6.

## Acceptance, as measured on the fixtures

Parent fixture: 1440 frames (48 s at 30 fps), slot [900, 1080),
cue word `narr-cue#0` at sample 1440000. Measured on the
assembled output (full record in `tests/evidence/mg037/`):

- Cue placement: the compiler resolves the cue to parent frame
  900; delta from the slot start is 0 frames (tolerance: one
  output frame). Decoded frame 900 is the insert's first frame
  (bar widths [0, 0, 0]); frame 899 is host content.
- The motion plays in place: decoded widths at parent frame 945
  measure the half reveal [240, 360, 600] within 3 px, and at
  parent frame 975 the final widths [480, 720, 1200] exactly.
- No duplicate narration or music: the assembly's input registry
  holds 3 scene, 3 narration, 1 music, and 1 canvas inputs; the
  insert MP4 has no audio stream; every parent narration segment
  measures present in the output (band ratios 0.86 to 1.02),
  including the segment the insert answers.
- No missing final words: the final segment's tail measures
  present at the planned end (band ratio 0.98).
- No unauthorized duration change: the output decodes to exactly
  1440 frames and 48.0 s; loudness measures -14.35 LUFS against
  the parent's -14 LUFS target (inside the 1.0 LU tolerance).
  The decoded audio carries 774 samples of AAC encoder padding
  beyond the plan's 2304000; the figure is recorded, not hidden.

## Honest limits

- The MG-034 package-lane font check fails the shipped fixture
  font convention (see "Producing the insert" above): until the
  gate resolves runtime-registry aliases the way the runtime
  does, a fixture-convention package cannot pass that one check,
  and this layer reports the gate's verdict as measured rather
  than restating the package to satisfy it.
- The acceptance build is a fixture-context production
  (engineering fixtures, `authority_status: "not_verified"`
  approval), the same standing as the shipped mode fixtures. A
  production handoff runs the identical code path under the
  parent pipeline's real approval and attestation, which are the
  parent side's existing machinery.
- The host segments and narration in the fixture are synthetic
  (test pattern video, word-shaped tone bursts): they exist so
  placement, presence, and duration are measurable. They make no
  claim about real speech intelligibility.
- Captions ride the compiled timeline and the parent's delivery
  ledger; this layer does not burn captions into the picture.
- One component is wired end to end (C05, Remotion). The
  contract is component-neutral; a component the catalog routes
  to Hyperframes returns through the same record shapes.
