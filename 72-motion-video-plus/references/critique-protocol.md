# Creative critique protocol (rebuilt, MG-033)

This protocol governs how a Skill 72 motion graphic is judged as a
viewer experience. It replaces the legacy criteria list (hook,
readability, motion quality, pacing, brand, sound sync, formats,
polish) with the eight directive dimensions below, and it replaces
opinion-based scoring with evidence-bound scoring: every score cites
the frames, bundle samples, proof records, or measured records it
rests on, and states explicitly how the artifact compares with the
job's approved reference.

The rules in this document are enforced structurally by
`scripts/review_rubric.py` against
`references/review-rubric-schema.json`. A review that violates them
is refused by name, not debated.

## Inputs

A review consumes records produced by the layers upstream of it. It
never re-derives what those layers already measured.

- The MG-031 coverage bundle for the exact artifact under review:
  the canonical coverage record (`<job>__coverage.json`) with
  verdict `complete`, the full-resolution frames, the
  destination-size frames for every variant of the job's mode, and
  the paginated sheets. A bundle whose coverage verdict is not
  `complete` is never scored; the tooling refuses it as
  `REVIEW_COVERAGE_INCOMPLETE`. The legacy bundle artifacts named
  by earlier versions of this protocol (the 8x8 tile sheet and its
  companion files) are retired; `scripts/critique_bundle.py` is the
  only bundle builder.
- MG-032 motion-proof records for the job's required non-text
  motion beats (`proof-record.json` per case), where they exist.
- Audio evidence records where sound is judged: for a final
  artifact, the MG-034 technical QC record for those exact bytes
  (`qc/final-qc.json`: its audio checks consume the MG-023
  measurement code and carry the measured loudness, clipping,
  narration-presence, and final-words results) is the shipped
  source. MG-023 audio verification records and the loudness block
  of the MG-031 metrics record remain the sources for preview-stage
  judgments, before a final QC record exists. A sound judgment
  without an attached measured audio record is refused.
- The job's director's brief and design record (the approval
  surface), the Section 17.3 reference registry entry for the job's
  reference, and the calibrated reference artifact itself.
- Every previous round's review record for the job. Review history
  is append-only; round N is validated against rounds 1 to N-1.

A preview record labeled `rough_layout_only` is layout evidence. It
can be reviewed for composition and story at layout fidelity, and
the record must say so; it can never support a finishing score or a
ship verdict for the final artifact.

## Who reviews

A review record names two identities: the author of the artifact
(the person, agent, or render pipeline that produced it) and the
reviewer. The tooling refuses a record where they are the same
identity (`REVIEW_SELF_APPROVAL`). There is no author self-approval,
in any round, for any reason.

Capabilities are recorded, not assumed:

- A reviewer records `vision_capable` honestly. A reviewer who
  cannot see frames may author work and may sign
  `data_proof_integrity` from records alone (proof records,
  coverage records, measured values). They cannot sign any other
  dimension; the tooling refuses it (`REVIEW_VISION_INCAPABLE`).
- A reviewer signing a dimension whose score rests on hearing the
  artifact sets `audio_judgment` and cites the measured audio
  record. Claims that audio exists are not audio evidence.

Reviewer prompts implementing this protocol for an independent
reviewer agent live in `references/reviewer-prompts.md`.

## The eight dimensions

Each dimension is scored 1 to 10, or recorded `unscored` with the
reason, or `not_applicable` with the reason. No evidence, no score:
a dimension without cited evidence is unscored, never estimated.

### 1. Visual storytelling

Does the piece say something a viewer understands, in order, at
viewing speed? The hook, the sequence of ideas, the moment the
piece becomes clear. Evidence: the bundle's opening samples and
full-timeline sheets, the beat list from the timeline. A piece
whose point only emerges from its script, not from its frames,
scores low here no matter how correct its parts are.

### 2. Asset relevance

Every image, clip, chart, and prop earns its place and matches the
brief: real, bright, human-looking material where people appear;
nothing generic standing in for the subject. Evidence: the frames
where each asset appears, the asset provenance sidecars. An
off-brief or uncanny asset is a defect here even when it is
technically flawless. Fictional product fixtures stay labeled as
fixtures (Section 17.3).

### 3. Typography and readability

Headlines land, labels read at the destination size, nothing the
viewer must read sits under the size floor, text never competes
with what it labels. Evidence: destination-size frames from the
bundle (the size the audience actually gets), not full-resolution
frames alone. Text that is legible at 1920 wide and mush at phone
width is a defect here.

### 4. Composition

The frame is balanced and stable at every state the piece passes
through, not only the final one: initial, proof, and final states
each read as deliberate. Empty fields, crowding, drifting
baselines, and values stranded far from what they describe are
defects here. Evidence: checkpoint frames across the motion
intervals and the sheets.

### 5. Motion clarity

The subject of each beat actually performs its transformation, and
a viewer can follow it: real subject motion in the right ratio and
direction, no decorative activity impersonating the point, no
double-applied transitions. Evidence: MG-032 motion-proof records
(three-way agreement between derived expectation, component
geometry, and decoded raster) and the full-fps clips. A beat whose
proof record fails or is missing caps this dimension at the score
its remaining evidence supports; pixel change in decoration is
never motion evidence.

### 6. Data and proof integrity

Every number, label, and implication is true: bar lengths match
values, sums and ratios are arithmetically right, nothing on
screen claims more than the source supports, no false data at any
frame including the first. Evidence: proof records, the dataset
record, decoded-frame measurements. An integrity failure is
critical by default: a beautiful lie is the worst output this
skill can ship. This is the one dimension a vision-incapable
reviewer may sign, from the records.

### 7. Destination fit

The piece is right for where it plays: the mode's frame, duration,
and legibility rules; portrait variants genuinely recomposed, not
scaled or cropped landscape; PowerPoint graphics that survive
embedding; VSL pieces paced for their player. Evidence:
destination-size frames for every variant of the mode, the mode
manifest, the bundle's per-destination samples.

### 8. Finishing

The last five percent: clean edges, no blank or placeholder
frames, no leftover debug or fixture artifacts in a client piece,
audio (where the mode has it) mixed and measured, disclosures
present where the content requires them. Evidence: the final
frames and sheets, the metrics record, measured audio records for
any sound judgment. Unfinished surfaces are defects here even when
every earlier dimension passes.

## Scoring discipline

- Every score carries its evidence and its reference comparison:
  what the artifact preserves against the reference and where it
  departs. A score without a comparison is not a judgment about
  this job; the schema refuses it.
- The scale: 9 to 10 is release-exemplar territory, 7 to 8 is
  competent professional work with named gaps, 4 to 6 is work that
  reads as unfinished or off-brief, 1 to 3 is broken.
- A score of 10 is reserved for owner-calibrated excellence. While
  the job's reference is `CALIBRATION_PENDING`,
  `ENGINEERING_FIXTURE_ONLY`, or `BLOCKED_ASSET`, the tooling
  refuses any 10 (`REVIEW_TEN_UNCALIBRATED`). Calibration belongs
  to the owner alone (Section 17.4): the author proposes, an
  independent reviewer checks, and only the owner's recorded
  decision sets `OWNER_APPROVED`. Claiming `OWNER_APPROVED`
  without citing that decision record is refused
  (`REVIEW_CALIBRATION_UNPROVEN`).
- Scores against a reference that is not `OWNER_APPROVED` are
  provisional, and the record says so (`provisional: true`,
  enforced). Provisional scores are engineering information. They
  are never presented, in any report or receipt, as the owner's
  artistic approval.
- A passing gate is a technical result. It is never described as
  artistic approval.

## The release gate

A record may carry verdict `ship` only when the gate passes:

- every applicable dimension is scored at 9 or higher;
- no critical defect is unresolved;
- the coverage verdict for the artifact is `complete`;
- the round is within the five-round correction cap.

The tooling computes the gate and refuses a `ship` verdict against
a failing gate (`REVIEW_VERDICT_INCONSISTENT`). Dimensions recorded
`not_applicable` with a reason are exempt; `unscored` dimensions
fail the gate.

## Defects, rounds, and escalation

Defects are first-class records, not prose. Each defect has a
stable id, a severity (`critical`, `major`, `minor`), a
description, its underlying cause, the round it was first seen,
and its resolution state. Resolution requires resolution evidence:
the frame or record that shows the defect gone.

- A defect that persists cannot be scored away. While a defect is
  unresolved, its dimension cannot score higher than it scored in
  the earliest round that both carried the defect and scored the
  dimension; the tooling checks the append-only history and
  refuses the inflated score (`REVIEW_SCORE_INFLATED_UNRESOLVED`).
  If no earlier round has scored the dimension while carrying the
  defect, no cap applies yet: the first round that does score it
  sets the baseline, and nothing is fabricated for the unscored
  rounds. A defect is carried in every later record until it is
  recorded resolved; dropping one silently is refused
  (`REVIEW_DEFECT_DROPPED`).
- Remediation is ordered worst cause first: critical before major
  before minor, earliest first-seen first within a severity. The
  record's `remediation` list states the fix order and the tooling
  checks it (`REVIEW_REMEDIATION_ORDER`). Cosmetic order is not a
  fix order.
- Correction is capped at five rounds. A record beyond round five
  is refused (`REVIEW_ROUND_LIMIT`) unless it is an escalation:
  verdict `escalate` with an `escalation_basis` that hands the
  evidence upward. Escalation is the honest ending for a piece
  that will not converge; inflating scores to end the loop is the
  failure this protocol exists to prevent.
- There is no minimum round count. A first-round record that
  passes the gate ships. Rounds exist to correct real defects,
  not to perform diligence. (This supersedes the legacy protocol's
  three-round minimum.)

## Records and the dashboard

One record per round, JSON, validated on write:

```
python3 scripts/review_rubric.py validate <record.json> \
    --history-dir <job review directory>
```

The quality dashboard (receipt) renders the whole history: rounds,
per-dimension scores with their evidence links, the defect ledger
worst first, the round count against the cap, and the calibration
state of the reference used, with the provisional banner where it
applies. The dashboard command renders; it does not validate.
Validate every record on write (the command above) and re-validate
the history before rendering a dashboard from it, so a receipt is
never produced from unvalidated records:

```
python3 scripts/review_rubric.py dashboard <record.json> \
    --history-dir <job review directory> --out <receipt.md>
```

Records live in the job's review directory alongside the bundle.
The dashboard receipt is the rendered review surface; it is
generated from the records, never edited by hand. It replaces the
legacy hand-appended review log block as the human-readable
surface; the JSON records are the source of truth the log used to
approximate.

## Known failure modes

The recurring ways motion work fools its own reviewer. Each maps
to the dimension that owns it.

1. Decoration moves, the subject does not. (Motion clarity; the
   MG-032 proof record exists for exactly this.)
2. Numbers visible before their bars exist, implying data the
   piece has not shown. (Data and proof integrity.)
3. Values stranded in a fixed column far from the marks they
   describe. (Composition, typography.)
4. Portrait output that is landscape, cropped. (Destination fit.)
5. A headline that promises a comparison the piece never makes.
   (Visual storytelling.)
6. Stock-looking or uncanny imagery where the brief wanted real
   people. (Asset relevance.)
7. Text that reads at full size and fails at destination size.
   (Typography and readability.)
8. Placeholder frames, fixture labels, or debug marks in a client
   piece. (Finishing.)
9. Sound that exists but was never measured. (Finishing; no
   judgment without the measured record.)
10. Scores that rise while their defects stand still. (The trend
    rule; refused by the tooling.)
11. Double-exposed captions at swaps, carets lingering after their
    line leaves, glyph slivers at masks. (Finishing.)
12. A scene cutting in over an unfinished wipe, or a hold longer
    than a beat with nothing new happening. (Motion clarity,
    visual storytelling.)

## Calibration states (Section 17.3)

| State | Meaning for scoring |
|---|---|
| `CALIBRATION_PENDING` | The owner has not yet approved the exemplar. Scores are provisional; no 10s. |
| `ENGINEERING_FIXTURE_ONLY` | The reference proves machinery, not taste. Scores are provisional engineering readings; no 10s. |
| `BLOCKED_ASSET` | The reference cannot be completed yet. Scores are provisional; no 10s. |
| `OWNER_APPROVED` | The owner's recorded decision calibrates this reference. Full scale available; scores are no longer provisional. |
