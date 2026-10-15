# Preview and review (MG-024)

How V2 previews work, why they can be trusted for review, and what may
never be inferred from them. This document describes the preview model
implemented in `runtime/src/preview/` and used by both production
adapters. It replaces the legacy preview behavior recorded as defect
D-PREVIEW-FORCE.

## The defect this closes

The legacy preview path (`scripts/render.js --preview`, the preview
gate of the V1 compatibility pipeline) forced every scene to 960x540
at 15 fps regardless of the manifest. Measured on this tree before
the fix, a 1080x1920 scene's preview came out at 1080x1920 (the
forced size never reached the pixels: Playwright screenshots the
stage element at its authored size, whatever the viewport says) and
at 15 fps: half the authored frames, which is exactly when motion
quality was being judged. The V2 adapters never forced anything:
their previews were the canonical render at full fps, which is
correct but expensive and carried no review metadata. The model
below gives both layers one honest preview semantics.

## The model

A preview is the same composition as the final, with exactly one
permitted difference: lower spatial resolution.

- **Author at canonical dimensions, then scale.** The composition is
  authored and laid out at the job's canvas size. A preview applies a
  scale in (0, 1] that preserves aspect ratio exactly; scaled
  dimensions are rounded to even numbers (the delivery pixel format
  requires them), minimum 2. A 1080x1920 job gets a 540x960 preview at
  scale 0.5: vertical in, vertical out, never a horizontal viewport.
- **Full fps by default.** Timing, sound synchronization, and motion
  review are only meaningful at the final's frame rate, so a preview
  renders at the full authored fps with the identical frame count and
  duration as the final.
- **Rough layout is the only reduced-fps artifact, and it is
  labeled.** A caller may request `roughLayout`; the plan then runs
  at 15 fps when the authored fps is higher, else at half the
  authored fps (floored, at least 1). Duration in frames rescales so
  the timeline in seconds is unchanged: the same events happen at the
  same times, sampled less often. The artifact is named
  `preview-rough.mp4`, its review record carries the label
  `rough_layout_only`, and the motion gate below refuses it.

## Identical props, proven by hash

Preview and final consume identical content. Two hashes make that
checkable instead of assumed:

- **Source hash** (`hashJobSourceInputs`): sha256 over the job's
  manifest, storyboard, asset manifest, timeline, design document,
  and every scene's spec, dataset, and design file. It is identical
  for the preview, the rough preview, and the final of one job
  revision.
- **Props hash** (`hashPropsPayload` on Remotion; a hash of the
  generated project files on Hyperframes): the exact content payload
  the engine consumed for the render. A full-fps preview's props hash
  equals the final's. A rough Remotion preview's props differ only in
  the fps and duration fields; a rough Hyperframes preview consumes
  the identical project and differs only in the render invocation's
  fps.

## The review record

Every V2 preview render produces a `PreviewReviewRecord`
(`runtime/src/preview/types.ts`):

- `engine`, `jobId`, `label` ("preview" or "rough_layout_only"),
  `roughLayoutOnly`, `scale`, and `scaleMethod`;
- `sourceHash`, `propsHash`, and `previewHash` (the sha256 of the
  produced artifact file);
- `final`: the canvas width, height, fps, and duration in frames;
- `preview`: the produced width, height, fps, duration in frames,
  and duration in seconds, all from the post-render probe, never
  from the plan alone;
- `generatedAt`.

The record rides on the returned evidence (`previewReview`), is
written as a sidecar beside the artifact (`preview.review.json`, or
`preview-<variant>.review.json` for scaled or rough variants), and,
for Hyperframes, is embedded in the render receipt as well.

`scaleMethod` names honestly how the scale was realized per engine:
`render_scale` (Remotion's renderMedia scale option renders at the
scale), `post_encode_scale` (Hyperframes: the pinned CLI's only scale
mechanism, `--resolution`, offers integer-multiple upscales from
fixed presets and no sub-native render scale, so the adapter scales
the engine's canonical frames at encode time with a lanczos filter;
frame count, fps, and timing are untouched), or `none` at scale 1.

## The full-fps motion gate

`checkPreviewMotionGate(record)` in `runtime/src/preview/gate.ts`
decides whether a preview record may serve as evidence for motion
judgment. It accepts a scaled full-fps preview. It refuses, with
named findings:

- `MG_PREVIEW_ROUGH_LAYOUT_ONLY`: the record is labeled
  rough_layout_only;
- `MG_PREVIEW_FPS_MISMATCH`: the preview fps differs from the final
  fps (checked independently of the label, so a rough artifact that
  lost its label is still refused);
- `MG_PREVIEW_ASPECT_MISMATCH`: the preview's aspect ratio does not
  preserve the final's.

Layout-approved 15 fps evidence can therefore never satisfy the
full-fps motion gate, which is the MG-024 acceptance rule.

## Review frames and contact sheets

Review material is produced at destination size: individual frames
are extracted from the rendered videos without rescaling
(`extractFramePng`), so a frame from the final is full delivery size
and a frame from a scaled preview is exactly the size a reviewer
watches. A contact sheet (`buildContactSheet`) tiles destination
frames at a stated tile size for side-by-side comparison. The MG-024
evidence set under `tests/evidence/mg024/` shows the pattern: final
and scaled-preview frames plus a three-across contact sheet, with
the measured landmark agreement recorded by the test suite.

## The legacy path

`scripts/render.js --preview` now follows the same model: the scale
derives from the manifest's canvas (default `--preview-scale 0.5`),
the capture applies the same scale to the stage element so the
output really is the scaled composition, the fps is the manifest
fps, and `--rough` is the only reduced-fps mode, labeled
`rough_layout_only` in the `<scene>.preview.json` sidecar and in the
stdout record. Resume state now keys on capture dimensions as well
as scene and fps, because a full-fps preview's frames are otherwise
indistinguishable from a final's. Non-preview renders are unchanged.

Reachability, traced: the V2 dispatcher registers only the Remotion
and Hyperframes adapters; no legacy adapter exists in the runtime,
so render.js is not reachable from the V2 preview path. It is the
live preview path of the legacy compatibility pipeline (the legacy
section of INSTRUCTIONS.md), which is why the fix landed there.

The two legacy texts that still stated the old forced numbers when
this document was written (the legacy preview gate step in
INSTRUCTIONS.md and the defaults line at the end of
references/animation-contract.md) were reconciled to the model
above by the documentation reconciliation item (MG-042); neither
states a forced preview size or frame rate any longer.

## Verification

`runtime/tests/run-preview.ts` proves the acceptance anchors with
decoded pixels: C05 preview/final landmark agreement after scaling
(bar widths measured in decoded frames from both renders, scaled back
to canonical coordinates, tolerance 4 canonical px against the
Section 17.2 table), a 9:16 preview for a 9:16 job, and a labeled
15 fps rough preview refused by the gate while the full-fps preview
passes. Expectations live in `tests/evidence/mg024/measurements.json`
as a static record the suite asserts and never rewrites.
