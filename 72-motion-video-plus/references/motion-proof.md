# Motion proof: proving actual subject motion (MG-032)

Skill 72's anti-gaming rule for motion: pixel change alone is not
motion. A title can slide, a background can shimmer, a progress bar
can sweep, and the chart the beat is ABOUT can sit perfectly still.
This layer exists so that cannot pass review. For every required
non-text motion beat, the evaluator produces semantic and temporal
evidence: the named subject's initial, intermediate proof, and final
states, confirmed in rendered frames against the geometry the scene
specification requires, plus a full-fps clip around the action.

Code: `runtime/src/motion-proof/`. Tests:
`runtime/tests/run-motion-proof.ts` (in the npm chain). Committed
evidence: `tests/evidence/mg032/measurements.json`.

## The motion proof case

A case is a small JSON document (schema:
`references/motion-assertion-schema.json`, the layer's own versioned
schema; the canonical contracts schema is untouched by this item).
It names:

- the job, scene, and component under judgment;
- the subjects (by the ids the scene specification uses) and each
  subject's role: `data_mark`, `traveling_object`, `layered_subject`,
  or `semantic_subject`;
- the transformation claimed: `linear_reveal`, `path_transit`,
  `depth_transit`, or `semantic_change`, with the motion interval in
  frames and an explicit `claims_depth` flag;
- checkpoints: at least three, including one `initial`, one `proof`
  (intermediate), and one `final`; a `hold` checkpoint may be added;
- the evidence the verdict must rest on: `geometry`, `decoded_frame`,
  `full_fps_clip`, `occlusion`, `depth`;
- the judgment mode: `automated`, or `human` with a reason.

For depth cases the case also declares `occlusion_checkpoints`: the
subject, the occluder, the frame, and the expected visible fraction,
before, during, and after the occlusion. The first and last must
expect (nearly) full visibility; a dip is only depth evidence against
full visibility on both sides.

## How the evaluator judges

`evaluateMotionProof` (runtime/src/motion-proof/evaluate.ts) runs in
phases, and the proof record it writes
(`proof-record.json`, written atomically into the case's output
directory) states the verdict, the stable failure category, and the
Section 16.9 exit code.

1. **Case validity.** A case that fails its schema is refused
   (`MG_SCHEMA_INVALID`, exit 2).
2. **Binding.** The MG-031 coverage record must bind the exact
   artifact under test: the record's video sha256 must equal the
   file's (`MG_HASH_MISMATCH`, exit 9) and its job id must equal the
   case's (`MG_FOREIGN_JOB`, exit 9).
3. **Gates, before any measurement.**
   - A depth claim (`claims_depth` or `depth_transit`) whose evidence
     plan includes neither occlusion nor depth evidence is refused
     (`MG_CAPABILITY_UNSUPPORTED`, exit 3). Depth-map evidence alone
     is also refused, by name: that measurement family is not
     implemented in this evaluator, and occlusion is the supported
     depth path. Occlusion evidence without at least three occlusion
     checkpoints is refused the same way.
   - A coverage record whose verdict is not `complete`, a checkpoint
     frame the bundle never extracted, or a bundle file listed but
     missing fails the case (`MG_COVERAGE_INCOMPLETE`, exit 6). An
     assertion built on an incomplete bundle cannot pass.
   - A bound review record labeled `rough_layout_only` cannot satisfy
     a case that requires a full-fps clip: reduced-frame-rate
     evidence is layout evidence (exit 6, same category).
   - A `human` judgment case with no human verdict record attached
     returns verdict `needs_human_judgment` (exit 3,
     `MG_INPUT_MISSING`). The evaluator never fabricates the verdict.
4. **Expectation derivation.** Expectations come from the scene
   specification through code independent of the renderer:
   - bars (C05): the MG-015 chart scale over the job's dataset and
     design records (`barGeometry` + `revealWidth`);
   - mechanism transit (C04): the diagrams frame functions over the
     resolved scene (`subjectPositionAt`, `subjectArcAt`);
   - occlusion: the case's own declared visible fractions (the case
     is the specification of record for a depth beat).
   The scene's own declared `semantic_motion_assertions` are
   cross-checked against the derivation; a specification that
   contradicts itself is refused as a contract error
   (`MG_SCHEMA_INVALID`), never graded against its own lie.
5. **Measurement, inside the subject region only.** Each checkpoint
   compares three sources where the family provides them: the derived
   expectation, the component's own instrumented frame functions, and
   the decoded raster (accent run extent inside each bar's row region;
   accent centroid inside a window around the subject's expected
   position; visible accent fraction inside the subject region for
   occlusion). The evaluator also measures how much the frame changed
   OUTSIDE the subject regions and records it as `context_change`:
   that number is evidence about decoration, and it can never turn a
   failing subject into a pass. Temporal checks require the subject
   itself to move between the initial and proof states (and to hold
   at a hold checkpoint); a static subject under moving decoration
   fails with `MG_FAKE_MOTION` (exit 6).
6. **Proof package.** The evaluator extracts the checkpoint frames at
   full resolution and, when the case requires it, a full-fps clip
   spanning exactly the motion interval, probed to confirm its frame
   count and frame rate. Extraction failures are refused
   (`MG_ENCODE_FAILED`, exit 5).

With a human verdict record attached, the decision is honored after
the same binding and coverage gates: `approved` passes with every
assertion labeled as human-decided (never dressed as measurement),
`rejected` fails as `MG_FAKE_MOTION`.

## Verdict vocabulary

| Verdict | Meaning |
| --- | --- |
| `pass` | The named subject performed the declared transformation, proven in the rendered frames. |
| `fail` | The evidence was complete and the subject did not perform (or a human reviewer rejected the claim). |
| `refused` | The case could not be judged: invalid case, unbound or missing artifacts, or a claim this evaluator does not implement. |
| `needs_human_judgment` | The case routes to human judgment and no verdict record was supplied. |

Categories and exits follow Section 16.9: `MG_SCHEMA_INVALID` 2,
`MG_INPUT_MISSING` 3, `MG_CAPABILITY_UNSUPPORTED` 3,
`MG_ENCODE_FAILED` 5, `MG_FAKE_MOTION` 6, `MG_COVERAGE_INCOMPLETE` 6,
`MG_HASH_MISMATCH` 9, `MG_FOREIGN_JOB` 9. When several gates fail,
the reported category is the earliest blocking class in the Section
16.9 order (validation, dependency, authority, execution, QC,
delivery); security bindings stop the evaluation immediately.

## Catalog declarations

`ComponentEntry.motionProof` (optional) declares, per component, the
subjects whose motion is the claim, the raster measurement the
evaluator applies, the transformation family, and the depth policy
(`not_claimed`, or `requires_occlusion_or_depth_evidence`). It is
populated today for C04 (`path_transit`, accent centroid) and C05
(`linear_reveal`, accent run extent). Components without a
declaration have no implemented measurement family: a motion claim
for one is refused by the evaluator by name, or routed to human
judgment, never waved through.

## Honest limits

- Implemented measurement families: data-mark linear reveal (C05),
  traveling-object path transit (C04), and occlusion-based depth.
  C06 to C09 assertion families (path drawing, state morphs, camera
  moves, layer assemblies) are not implemented; cases for them are
  refused with `MG_CAPABILITY_UNSUPPORTED` until their families land.
- Depth-map (`depth` evidence) measurement is not implemented; the
  refusal says so. Occlusion is the supported depth path.
- Semantic transformations (emphasis that reads as endorsement,
  before/after implication, any claim about what motion MEANS) route
  to the human judgment path by design.
- Raster measurement matches the subject's declared color within the
  suite-wide tolerance (per-channel absolute difference summing to at
  most 66, the MG-006/MG-017 rule). A subject rendered in a color the
  case does not declare will not be found, by design: the case must
  describe the artifact it judges.
