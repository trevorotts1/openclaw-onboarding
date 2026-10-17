# Visual Storytelling: The Planner

Motion Video Plus plans before it animates. The planner turns a brief into a
beat-by-beat visual story in which every explanatory beat changes something
the viewer can see: a chart develops, an item travels a mechanism, a real
photograph is revealed or compared. Moving typography alone does not explain
a mechanism, a relationship, a contrast, or a transformation, so a plan made
of text beats is not a plan this skill will render.

The planner runs after intake has fixed the mode (see
`references/intake-and-modes.md`) and before any animation code is written.
Its outputs are the storyboard artifact (`storyboard.json`), the planner
record (`planner.json`), and the story-beats section of the director's
brief. Style frames and their approval build on the approved plan later
(see "Style frames and the design gate" below); the planner is where
representation is chosen, and it is chosen before code.

Naming caution: `references/beats-schema.json` is the music beat grid
(tempo, beat times) used by the score tools. It has nothing to do with story
beats. Story beats live in `storyboard.json` under the contracts-v2
`storyboard` definition.

## The beat record

Each beat is recorded twice, in two layers with two owners:

1. The canonical storyboard (`storyboard.json`, contracts-v2 `storyboard`
   and `beat` definitions, owned by the contracts layer, MG-007). This is
   the serialized source of truth the validators and renderers read.
2. The planner record (`planner.json`, owned by this planner, MG-009). The
   canonical beat definition is closed (`additionalProperties: false`) and
   cannot carry several fields the directive requires the planner to
   record. Those fields live in the planner record, keyed by beat id. Do
   not add them to the storyboard file; the schema will reject them, by
   design.

What MG-009 and Section 5.3 require per beat, and where each item lives:

| Required record | Home | Field |
|---|---|---|
| Beat identity and scene | storyboard | `id`, `scene_id`, `job` |
| Viewer question | storyboard | `viewer_question` |
| The idea | planner record | `idea` |
| Intended understanding | storyboard | `intended_understanding` |
| Viewer takeaway | planner record | `viewer_takeaway` |
| Changing subject | storyboard | `subject_ids` (the actual image, object, chart, or diagram; not automatically text) |
| Visual verb | storyboard | `visual_verb` |
| Initial state | storyboard | `initial_state` |
| Transformation | storyboard | `transformation` |
| Proof state | storyboard | `proof_state`, with `proof_frames` naming when it is observable |
| Final state | storyboard | `final_state` |
| Representation | storyboard | `representation` |
| Explanatory or not | storyboard | `explanatory` |
| Exact assets and data | storyboard | `asset_ids`, `data_ids` |
| Essential text | storyboard | `essential_text` |
| Typography exception rationale | storyboard | `typography_only_exception` |
| Literal evidence vs illustrative metaphor | planner record | `evidence_kind` |
| Selected component, engine, and reason | planner record | `component_id`, `engine`, `selection_reason` |
| Reading order | planner record | `reading_order` |
| Readable hold | planner record | `readable_hold_frames` |
| Transition ownership | planner record | `transition_owner` |
| Narrative cue or slot reference | planner record | `narrative_cue_ref` (null when the job has no parent slot or narration cue) |
| Intentional stillness and its reason | planner record | `intentional_stillness`, `stillness_reason` |
| Bound semantic assertions | planner record | `assertion_ids` (ids of assertions declared in the beat's scene file) |

The gap, stated plainly: the canonical `beat` definition has no `idea`,
`viewer_takeaway`, `evidence_kind`, component/engine selection, reading
order, readable hold, transition ownership, or narrative cue field, and its
`semantic_motion_assertions` live on scene files, not on beats. The planner
record layer carries exactly those items. If a future contracts revision
absorbs them, the planner record shrinks; until then, a storyboard without
a planner record is an unfinished plan and the validator says so.

Planner record shape:

```json
{
  "planner_version": "1.0",
  "storyboard_id": "story-chart-proof",
  "beats": [
    {
      "beat_id": "beat-bars",
      "idea": "Grow three bars from one dataset",
      "viewer_takeaway": "Group C is largest, proportionally",
      "evidence_kind": "literal_evidence",
      "component_id": "C05",
      "engine": "remotion",
      "selection_reason": "Parameterized chart; Remotion is the default for data-driven charts",
      "reading_order": ["headline", "bars", "values"],
      "readable_hold_frames": 45,
      "transition_owner": "self",
      "narrative_cue_ref": null,
      "intentional_stillness": false,
      "stillness_reason": null,
      "assertion_ids": ["half-reveal", "final-ratios"]
    }
  ]
}
```

Every storyboard beat needs exactly one planner record. `evidence_kind` is
required for explanatory beats and may be null for non-explanatory beats
(identity and emphasis cards assert nothing). `stillness_reason` is required
whenever `intentional_stillness` is true.

## Choosing a representation

Choose the representation before writing animation code, and record the
reason. The planner's six choices map onto the storyboard `representation`
enum like this:

| Planner choice | `representation` | Counts as non-text |
|---|---|---|
| Chart | `chart` | Yes |
| Diagram | `diagram` | Yes |
| Image-led comparison | `image` | Yes |
| Spatial metaphor | `mechanism` (or `diagram` when nothing travels) | Yes |
| Real product demonstration | `image` (or `mechanism` when the product moves through states) | Yes |
| Purposeful typography | `typography` | No |

Guidance:

- If the beat's truth lives in numbers, it is a chart, and the beat names
  its dataset in `data_ids`. A chart beat with no dataset is a drawing.
- If the beat's truth is a relationship, a flow, or a cause, it is a
  diagram or a mechanism. Mechanisms give one subject a persistent identity
  and move it; diagrams connect named parts.
- If the beat's truth is what something actually looks like, it is an image
  beat, and the beat names the exact asset in `asset_ids`. Never plan to
  recreate a supplied photograph as shapes; the photograph is the evidence.
- Typography is for emphasis, framing, and hooks: one line, set large, held.
  It is a legitimate device and a bounded one (see the coverage rule). A
  typography beat never silently becomes the explanation.
- Engine defaults follow the routing doctrine: charts and parameterized
  diagrams default to Remotion; image-led, editorial, product, and spatial
  compositions default to Hyperframes. Record any departure in
  `selection_reason`.

Vary the plan. A deck or sequence that assigns the same representation and
the same composition to every beat is a template wearing a planner's
clothes; presentation doctrine (SOP-DESIGN-03, variable layout) treats a
layout that never varies as a defect in its own right. Coverage is a floor,
not a house style.

## The coverage rule (Section 1.1)

For a general explainer, presentation graphic, or VSL sequence, at least
two-thirds of the explanatory beats, rounding up, must be
information-bearing non-text: a chart, an image, a mechanism, or a diagram
whose subject carries the information. The validator computes

```
required_non_text = ceil(2 * explanatory_beats / 3)
```

and fails the plan below it.

Counting discipline:

- Only beats with `explanatory: true` enter the count. Opening and closing
  identity cards and short emphasis beats are not explanatory beats; mark
  them `explanatory: false` and they owe no coverage and no assertions.
- A typography beat always counts as text, including when it carries a
  `typography_only_exception`. The exception is the recorded rationale for
  a text-dominant beat (Section 5.3 requires the reason); it is not an
  exemption from arithmetic, and renaming the job "kinetic typography" does
  not change the count.
- A beat that explains nothing cannot pass by declaring zero explanatory
  beats; a storyboard with no explanatory beats fails coverage outright.
- A genuinely typography-only treatment is an owner-level decision recorded
  with an approved rationale in the director's brief. No beat-level
  exception, and no planner setting, can declare it. Even then, semantic
  proof is still required for every qualifying beat.

## Literal evidence vs illustrative metaphor

Every explanatory beat declares its `evidence_kind`:

- `literal_evidence`: the subject shown is the actual thing: the supplied
  photograph itself, the supplied dataset rendered exactly, the real
  product screen. A literal-evidence beat must reference the exact asset or
  dataset in `asset_ids` or `data_ids`, and every referenced id must resolve
  in the job (an entry in `assets.json`, a file under `data/` whose `id`
  matches). Claiming literal evidence with nothing referenced, or with a
  reference the job does not contain, fails validation.
- `illustrative_metaphor`: the subject stands in for the idea: a work item
  traveling a stylized pipeline, a balance standing in for trade-offs.
  Metaphor is a legitimate teaching device and a dishonest proof. Never
  let a metaphor beat borrow the language of evidence: its copy,
  `intended_understanding`, and takeaway must not claim the viewer has seen
  the real thing. Datasets carry their own honesty label (`kind`:
  `illustrative` or `observed`, plus a `source_note`); illustrative numbers
  stay labeled illustrative wherever they appear.

## Semantic motion assertions

Every qualifying beat (every explanatory beat) binds at least one semantic
motion assertion, by id, from its scene file's `semantic_motion_assertions`.
Assertions are the plan's falsifiable claims about motion: "the same item
passes through three named stages", "bar heights preserve the supplied
values". Rules:

- The assertion must concern the beat's own changing subjects: at least one
  of the assertion's `subject_ids` must be one of the beat's `subject_ids`.
  An assertion about a moving background, a drifting gradient, or any other
  unrelated subject does not satisfy the beat, and binding one fails
  validation with `MG_PLANNER_ASSERTION_SUBJECT_MISMATCH`.
- Assertion kinds are the contracts vocabulary: `bar_widths`,
  `subject_identity`, `text_readability`, `timeline_bounds`. Pick the kind
  that matches the claim, name the frame at which it is observable, and let
  the beat's `proof_frames` include that frame.
- Binding happens at plan time so the proof obligation exists before
  animation code does. Whether the rendered frames actually satisfy the
  assertion is a render-review question for the evidence pipeline; the
  planner gate proves the obligation is declared, bound to the right
  subject, and checkable.

## Visual verbs

Name the change with a verb that describes what the subject does:
accumulate, compare, connect, isolate, transform, reveal, traverse,
expand, compress, reorganize, demonstrate. "Fade in the words" is not an
adequate visual verb for a mechanism scene. If the only honest verb for a
beat is that text appears, the beat is typography and counts as text.

## Typography inside a plan

Motion typography in this skill inherits the presentation department's
typography doctrine, which the planner respects at plan time:

- One reading order per beat. `reading_order` names the elements in the
  order the eye should take them; the first element is the beat's hero.
  Two elements competing to be read first is a hierarchy failure
  (SOP-DESIGN-01, section 2.4). Decide the order in the plan; do not leave
  it to the renderer.
- Type has roles, not vibes. Essential text in a beat should know its role
  in the locked hierarchy (hero line, supporting line, label, caption),
  the hierarchy the design record locks with at least four distinct weights
  (SOP-DESIGN-01, section 2.1). The measurable size floors for rendered
  output are MG-013's concern; the planner's job is that no beat's
  explanation depends on small print.
- Pure typography is a dedicated-beat device. Presentation doctrine gives
  the hook its own pure-typography slides, set large over a quiet ground,
  never stamped as a footer on other slides (SOP-DESIGN-02). The motion
  analogue: a typography emphasis beat is its own beat, held and legible,
  never a caption strip pasted under a visual beat that was supposed to
  explain.
- Type is decided before production, not during it. The planner fixes each
  beat's essential text and reading order before scene authoring for the
  same reason the presentation pipeline locks its type system in Phase 1.5
  before prompts exist: typography decided late becomes typography
  improvised.

## The Design Intelligence boundary

Skill 45 (Design Intelligence Library) owns image style analysis and
style-faithful image generation: a 12-dimension style analysis (render,
composition, subject, color, grading, lighting, typography, layering,
subject-background, negative space, workflow, unity), style cards that
separate content from aesthetic DNA, and a fidelity protocol (average score
at least 4.0, no dimension under 3, zero hard-rule violations). MG-010
builds the explicit bridge that lets style frames use those concepts
through a component-level handoff. The planner's obligations under that
boundary are simpler:

- The planner may cite a style card or a style-analysis result as the
  design source for a beat's look (record it in the director's brief); it
  does not perform style analysis itself.
- Presentation and webinar work stays with the Presentations department.
  Skill 45's own scope contract is explicit that webinar, funnel, sales,
  and audience decks are not DIU work, and that the one legal crossing is a
  reference handed to a Style Analyst whose card comes back across the
  boundary. Motion jobs follow the same shape: concepts cross through an
  explicit handoff, ownership does not move.
- Imagery of real people carries the consent discipline Skill 45 enforces
  on its side of the boundary (documented consent before likeness work).
  A plan that calls for a real person's image names the approved asset; it
  never assumes one can be generated on demand.

## Feeding the storyboard and the brief

The planner writes `storyboard.json` and `planner.json` into the job
directory, then mirrors the same beats into the director's brief's
story-beats section (one block per beat: idea, representation, subject,
verb, states, takeaway, evidence kind, exact assets/data, bound assertions,
component and engine with the reason, reading order, hold, and any
typography exception rationale). The brief is the human-readable approval
surface; the two JSON artifacts are the machine-readable ones. They must
not drift: if a beat changes, change the artifact, the record, and the
brief together, and re-run the validator.

Run the gate before scene authoring:

```bash
python3 scripts/validate_storyboard.py validate <job_dir>
```

Exit 0 means the plan passes. Exit 2 prints the findings as JSON with a
`coverage` summary and a `first_error_category`. The MG-008 intake test
proves the shipped mode fixture storyboards pass the contracts schema;
they predate the planner layer, so the planner gate additionally reports
their missing planner records until a planner pass writes them.

## Style frames and the design gate

The planner's output is a plan. Before any final animation is authored,
the plan becomes stills: for each representative scene, produce a first,
a key-proof, and a final style frame, rendered from the actual intended
assets and the job's design tokens. An excellent still composition can
be approved, or sent back, without anyone reading animation code; a weak
one is cheapest to fix here. This stage is MG-010; the gate is
`scripts/check_style_frames.py`.

The records, per job:

- `design.json` stays the canonical token record (colors, type scale,
  layout numbers). Its schema is closed and chart-shaped, so per-frame
  composition facts live in the style-frame record, the same layering
  as the planner record and the asset provenance sidecar.
- `style-frames.json` carries, per scene and per frame: the frame kind
  (`first`, `key_proof`, `final`), its path and sha256, its pixel
  dimensions, a record sequence number, its design record (typography
  hierarchy, focal point, crop, layout, colors, reading order), and
  the named reference its critique compares against. It also lists the
  job's animation artifacts with their sequence numbers, so the record
  itself proves the ordering: style frames first, animation after.
- `frame.md` carries the rationale per frame and the reference-specific
  critique: what is stronger, what is weaker, what is different against
  the named reference. A bare score is not a critique and does not
  satisfy the stage. Where a Skill 45 style card exists for the
  reference, the critique quotes its findings through the Design
  Intelligence bridge (`references/design-intelligence-bridge.md`);
  Skill 72 still performs no analysis of its own.
- `approvals.json` carries the canonical approval records. The design
  approval names every representative frame in `artifact_refs` with the
  exact sha256 of its current bytes, and its `subject_revision` is the
  design revision: a deterministic digest over `design.json` and the
  frames' design records. Any change to the design record, to a frame's
  design record, or to a frame's bytes after approval makes the
  approval stale.

Run the gate before claiming design approval or starting final
animation authoring:

```bash
python3 scripts/check_style_frames.py check <job_dir>
```

Exit 0 is a pass at the design gate. Exit 2 (`MG_SCHEMA_INVALID`) means
the record set is malformed or contradicts itself, including an
animation artifact whose sequence does not come after the style frames.
Exit 3 (`MG_INPUT_MISSING`) means a required frame or record is absent.
Exit 4 means the approval leg failed: `MG_APPROVAL_REQUIRED` (no
approval, or a pending or rejected one), `MG_APPROVAL_STALE` (the
approval no longer covers the current design revision or frame bytes),
or `MG_APPROVAL_AUTHORITY_UNAVAILABLE`. Exit 9 (`MG_FOREIGN_JOB`) means
an approval bound to a different job or company was presented; nothing
else is evaluated after it.

Authority follows Section 16.7: the gate invents no trust boundary.
Fixture jobs run under the test-only issuer and their reports carry
`diagnostic: true`; fixture evidence never promotes a production job,
and production rejects the test issuer. Style frames built for fixtures
are engineering material with calibration-pending reference states,
never owner approval; an owner approves a direction from the stills
and `frame.md`, in the director's brief, as a real approval record.

## Finding categories

| Category | Meaning |
|---|---|
| `MG_SCHEMA_INVALID` | The storyboard fails the shipped storyboard schema, or the planner record structurally disagrees with the storyboard |
| `MG_PLANNER_FIELD_MISSING` | A beat has no planner record, or a required planner field is absent, empty, or unusable |
| `MG_PLANNER_COVERAGE` | Non-text coverage is below two-thirds of explanatory beats (rounding up), or the plan declares no explanatory beats |
| `MG_PLANNER_EXCEPTION_MISSING` | An explanatory typography beat carries no exception rationale |
| `MG_PLANNER_REPRESENTATION_REQUIREMENTS` | A chart beat names no dataset, or an image beat names no asset |
| `MG_PLANNER_ASSERTION_MISSING` | An explanatory beat binds no semantic motion assertion |
| `MG_PLANNER_ASSERTION_UNRESOLVED` | A bound assertion id, or the beat's scene, cannot be found in the job |
| `MG_PLANNER_ASSERTION_SUBJECT_MISMATCH` | A bound assertion concerns none of the beat's changing subjects |
| `MG_PLANNER_EVIDENCE_UNRESOLVED` | A referenced asset or dataset is not in the job, or a literal-evidence beat references nothing exact |

Fixtures for every row of this table live under
`tests/fixtures/storyboards/`; the suite that exercises them is
`tests/unit/test_storyboard_planner.py`.
