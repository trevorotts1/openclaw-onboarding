# Determinism and Reproducibility

Directive MG-026. This document is the human-readable contract for the
determinism verifier in `runtime/src/determinism/` and its suite,
`runtime/tests/run-determinism.ts`. It states what the runtime
promises about repeat renders, what it deliberately does not promise,
and the tolerance doctrine that keeps the difference honest.

## The one-sentence promise

Given the same engine, the same pinned environment, and the same
input revision, a repeated render of an approved job produces the
same decoded pixels. Anything outside those three conditions is
reported, never hidden, and never asserted away.

## The seek contract, per engine

Seek safety means a frame is a pure function of the frame (or time) it
is asked for. Each engine reaches that property through its own
controlled timeline, and the verifier drives each engine only through
that timeline.

### Remotion

- Motion derives from the frame clock (`useCurrentFrame` and values
  computed from it). Wall clock reads, `Date.now`, `setTimeout` driven
  motion, CSS transitions, and unseeded randomness are forbidden in
  component code (see `references/animation-contract.md`).
- Randomness, where a component needs it, is seeded from the frame
  number, so frame N draws the same values in every process.
- Inputs are frozen: the composition renders only the validated job
  files, and the exact font bytes enter through input props.
- Assets are awaited by the render call itself; a still is captured
  only after the composition has loaded.
- The verifier calls the shipped adapter's `renderStill`, which seeks
  the composition to the requested frame. There is no other clock.

### Hyperframes

- Motion lives in registered, seekable timelines (GSAP timelines the
  runtime registers), and the snapshot path steps the timeline to the
  requested time. Unregistered wall clock animation is out.
- The verifier calls the shipped adapter's `renderStill`, which runs
  the pinned Hyperframes CLI snapshot with software rasterization
  (`--no-browser-gpu`), so the rasterizer is the deterministic CPU
  path, not a GPU whose driver could vary by machine.
- Project materialization is deterministic: the same job spec
  generates the same project bytes, fonts and GSAP are vendored from
  the pinned shared runtime, and declared assets are copied in before
  the snapshot runs.

### Legacy `__setTime` scenes

- A scene exposes `window.__setTime(t)`; calling it must put the stage
  in exactly the state for time t, regardless of what times were set
  before, how often it is called, or how much wall clock time passed
  between calls. `references/animation-contract.md` carries the full
  scene rules (no timers, no unseeded randomness, no network during
  the timeline, no viewport dependent layout).
- The V2 runtime has no adapter for this surface, so the verifier
  drives fixture scenes directly in the pinned browser through the
  seek harness (`runtime/src/determinism/scene-harness.ts`). The same
  purity rule is what the production adapters rely on, so it is
  verified at this surface too.

## How the verifier tests it: access patterns

For each engine, the shipped C05 fixture scene (Section 17.2) is
rendered at the proof frames 0, 15, 45, 75, 150, 179, which cover the
opening frame, the transition start, the transition midpoint, the
proof frame, a hold frame, and the final frame. Each frame is
rendered under four access patterns:

- **Cold**: a fresh process renders exactly one frame. No warm engine
  state, no bundle or composition cache inside the process, no prior
  frame. Cold renders become the golden results.
- **Forward**: one process renders the frames in ascending order.
- **Reverse**: one process renders the frames in descending order.
- **Randomized**: one process renders the frames in a shuffled order
  drawn from a seeded generator (`prng.ts`). The seed is recorded in
  the evidence, so the pattern itself is reproducible and a failure
  can be replayed order for order.

Every pattern output is decoded to raw pixels (ffmpeg decode of the
PNG, never a comparison of PNG file bytes) and compared against the
cold golden for the same frame: differing pixel count and fraction,
largest channel difference, and mean absolute difference. Identical
decoded pixels are the expectation on these CPU paths, and the
tolerance applied is exact (see the tolerance doctrine below).

## What is not promised

- **No identical images across engines.** Remotion and Hyperframes
  rasterize the same logical scene through different page stacks and
  text pipelines. The verifier renders the same logical C05 scene
  through both engines and records the measured pixel difference in
  the evidence record; it never asserts equality. In the MG-026
  recorded environment, frame 75 differed in about 2.7 percent of
  pixels (56,385 of 2,073,600, mean absolute channel difference about
  3.75), which is the honest size of the rasterization gap, mostly
  text antialiasing and edge treatment. The cross-engine claim that
  IS made is decoded data geometry: both engines' frames measure the
  Section 17.2 bar widths within 2 px.
- **No identical MP4 bytes.** Video encoding involves timestamps,
  muxing metadata, and encoder threading; byte identity of a
  container is not a reproducibility property and is never required.
  Decoded frames are the comparison surface.
- **No identity across operating systems or font renderers.** A
  different OS, a different Chromium build, or different font bytes
  are a different environment. Differences there are expected, are
  reported as environment changes, and do not fail the within
  environment promise. They also do not excuse drift within one
  environment.

## The environment record

Golden results are stored with the environment that produced them in
`tests/evidence/mg026/` (`measurements.json` and `environment.json`):

- engine versions (Remotion, Hyperframes, GSAP) read from the shared
  runtime lock, never typed in;
- the runtime lock id, which names the pinned install;
- the Node version of the verifier process and the version recorded
  in the lock;
- OS, architecture, and OS release;
- the browser revision and version string from the lock;
- the sha256 of every font file both engines resolve for the job,
  because font bytes are an input to rasterization;
- a sha256 of every job input file, recorded before and after
  rendering, proving the inputs were frozen and rendering did not
  mutate them. Files an adapter adds under a job's `renders/`
  directory are render outputs, not inputs; the check enumerates
  them separately and fails if rendering writes anywhere else in
  the job or changes or removes any input byte.

Two runs whose environment records differ are different environments;
comparing their pixels is a report, not a verdict.

## Tolerance doctrine

- On the pinned CPU render paths (Remotion stills through the
  headless shell, Hyperframes snapshots with software rasterization),
  the tolerance is **exact**: zero differing pixels and zero channel
  delta. Both engines met this bar in the MG-026 verification, across
  all four access patterns and all six proof frames.
- A tolerance may only be introduced for a path where exactness is
  physically unavailable, for example a qualified GPU rasterization
  path whose output varies by driver. When one is introduced it must
  be narrow, justified in writing next to the evidence, and reviewed
  visually (a person looks at the differing frames, not just the
  counts).
- A tolerance is never widened to make a failure pass. The standing
  proof: the suite stages the C05 job with its plot origin shifted by
  20 px, a clearly visible broken layout, and requires the verifier
  to FAIL that frame under the exact tolerance and under a
  deliberately generous antialiasing jitter budget (100 differing
  pixels, channel delta 2). In the recorded run the shifted frame
  differed in 34,164 pixels with a largest channel delta of 222, so
  the failure margin over any plausible jitter budget is more than
  two orders of magnitude. Any future tolerance that would pass this
  frame is by definition wide enough to pass a broken layout and is
  not permitted.
- Antialiasing jitter, if it ever appears on a CPU path, is treated
  as an environment or engine change to investigate, not as a reason
  to loosen the bar silently.

## Drift: what fails, and how it is caught

Two failure shapes are exercised against fixture scenes that commit
them on purpose (fixtures only, under `tests/fixtures/determinism/`;
the patterns are forbidden in shipped scene code):

- **Timer driven drift** (`drift-wallclock.html`): the scene positions
  an element from `Date.now()`. Captures of the same frame before and
  after a 650 ms wall clock wait disagree, and the verifier fails the
  scene. Timer driven motion cannot be seek safe, because the wall
  clock is not the timeline.
- **Unseeded change** (`drift-unseeded.html`): the scene scatters
  elements with `Math.random()` and no seed. Two cold captures of the
  same frame disagree, and the verifier fails the scene.
- The **seeded control** (`control-seeded.html`) renders its scatter
  from a generator seeded by the frame number and passes with
  identical pixels under cold, seek history, and delayed captures.
  That contrast is the point: seeding keyed to the frame is the
  sanctioned pattern, and it is provably stable.

## Running the verifier

The suite is part of the runtime test chain (`npm test` in
`72-motion-video-plus/runtime`) as `run-determinism`, and can be run
on its own after a build:

```
cd 72-motion-video-plus/runtime
npm run build
node dist/tests/run-determinism.js
```

Renders run in scratch space under the shared runtime state directory
(`shared-utils/motion-render-runtime/.runtime/mg026-tests/`), outside
git. The evidence directory holds hashes and statistics only; frame
dumps are not committed.
