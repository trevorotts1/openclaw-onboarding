# Performance benchmarks (MG-045)

This document is the human-readable authority for the MG-045
benchmarks. The raw records are the data of record and live in
`tests/evidence/mg045/`:

- `rep-1.json`, `rep-2.json`: the two full repetitions of the
  six-cell matrix, one record per cell per repetition, with per-stage
  timings, per-stage resource peaks, machine metadata, and the
  runtime lock, all inside each record.
- `cache.json`: the MG-027 cache program (cold, warm, partial
  executions) with per-scene actions, renderer call logs, and the
  per-stage savings accounting.
- `analysis.json`: the derived analysis over the raw records:
  stage tables, cross-repetition variance, failure accounting,
  pixel-fidelity comparisons, the degraded demonstration, and the
  speed rankings with their exclusions.

The harness is `runtime/tests/measure-benchmarks.ts`. It runs
representative production work through the shipped pipeline only:
the production Remotion and Hyperframes adapters (Section 5.5), the
MG-021 timeline compiler, the MG-027 cached render session, and the
MG-031 critique bundle builder as the QC stage. It adds no render
path of its own.

QC stage re-point note (MG-048): the QC stage measured here is the
MG-031 critique bundle because MG-034's fail-closed technical QC
(`scripts/qc.py`) was not on MG-045's base. Future benchmark
refreshes should measure `qc.py` as the QC stage (the critique
bundle may still be reported alongside it as the review-coverage
stage). The figures below are not retroactively changed by this
note; they measure what they say they measure.

Every figure below carries its conditions. A figure quoted without
the machine, the runtime lock, the scene, and the repetition count
is not supported by this document.

## Conditions (apply to every figure unless a row says otherwise)

- Machine: 2 CPU cores, 7935 MB total RAM, Linux x64, Node
  v24.20.0. Measured by the MG-028 resource layer
  (`measureMachineCapacity`) and recorded inside every run record.
- Runtime lock: `lock-314fc289b233ca9e`, pinning Remotion 4.0.535
  and Hyperframes 0.8.155 (with GSAP 3.15.0, TypeScript 5.9.3, and
  Chromium 157.0.8080.0). The worktree's own shared runtime was
  provisioned fresh for this work (`provision.sh` with
  `MOTION_RUNTIME_SKIP_APT=1`; the probe passed for both engines;
  the apt step itself is UNVERIFIED, as in every worktree run).
- Load: this box is shared with other build crews. Load averages
  recorded at the start of the evidence repetitions were
  [5.62, 5.48, 3.48] (repetition 1) and [7.12, 7.89, 5.97]
  (repetition 2) on a 2-core box. Wall times are therefore
  load-dependent upper bounds, never clean-machine figures (the same
  uncertainty practice as MG-028's measurements).
- Scenes, all at 1920x1080 and 30 fps: chart-heavy is the C05 chart
  fixture (`tests/fixtures/modes/powerpoint_graphic`, 180 frames,
  6 seconds, one scene); image-heavy is a C01 mask-reveal scene over
  the reference-suite image-led asset (`mentor-desk.png`, 1200x1000)
  staged in the MG-005 suite pattern (150 frames, 5 seconds, one
  scene); mixed-media is the chart scene plus the reveal scene as
  one two-scene program (330 frames, 11 seconds).
- Repetitions: the full matrix ran twice (repetitions 1 and 2),
  cells sequential, one child process per cell, sampled every 50 ms
  via /proc (the MG-028 method) for peak RSS and every 250 ms for
  peak disk. The cache program ran once with three executions
  (cold, warm, partial).
- Remotion bundle state: the shared Remotion bundle cache (one
  bundle, 28,515,093 bytes) already existed when the evidence run
  started, built during this session's earlier smoke runs on the
  freshly provisioned runtime. Every Remotion cell record carries
  the bundle listing it observed before rendering, so no cell in the
  evidence run claims a cold bundle. See Honest limits.

## Reproduce

```bash
cd 72-motion-video-plus/runtime
npm ci
npm run build
# Self-check of the analysis rules (degraded exclusion, failure
# counting, variance) over synthetic records:
node dist/tests/measure-benchmarks.js --self-check
# The full matrix (two repetitions, six cells, the cache program,
# the analysis), writing evidence copies:
node dist/tests/measure-benchmarks.js --reps 2 --write-evidence
```

Precondition: the shared runtime provisioned in this checkout
(`shared-utils/motion-render-runtime/provision.sh`). The harness is
a standalone driver in the `measure-resources.ts` pattern; it is not
part of the default `npm test` chain because a full matrix takes
tens of minutes.

## Per-stage results

Stage definitions: setup is adapter construction plus the shipped
runtime probe; compile is contracts dispatch (Remotion cells only,
see the asymmetry note), the MG-021 timeline compile, and the
adapter's own validate pass; asset preparation is the shipped
cache-key input collection (hashing scene source, props, assets,
fonts, data); still1 and still2 are two `renderStill` calls (for
Remotion the second runs on a fresh adapter instance, the MG-028
still pattern); preview is `renderPreview`; render is `renderFinal`;
encode is an isolated re-encode of the produced final (libx264,
crf 16, yuv420p, the MG-028 isolation method, reported as the encode
share and never double counted inside render); QC is the MG-031
critique bundle over the final against the compiled timeline. Times
are stage wall seconds, repetition 1 / repetition 2.

### Chart job, Remotion (180 frames)

| Stage | Rep 1 | Rep 2 |
| --- | ---: | ---: |
| setup | 0.02 | 0.00 |
| compile | 0.49 | 0.82 |
| asset prep | 0.05 | 0.06 |
| still 1 (frame 75) | 11.18 | 3.00 |
| still 2 (frame 45, fresh instance) | 2.13 | 2.50 |
| preview | 20.75 | 21.39 |
| render | 32.78 | 28.69 |
| encode (isolated) | 14.59 | 6.66 |
| QC | 9.09 | 3.31 |
| cell wall | 91.1 | 66.4 |
| peak RSS | 1290 MB | 1300 MB |
| peak disk (cell dir) | 2.2 MB | 2.2 MB |
| QC verdict | complete | complete |

### Chart job, Hyperframes (same job, retargeted)

| Stage | Rep 1 | Rep 2 |
| --- | ---: | ---: |
| setup | 0.59 | 0.18 |
| compile | 28.99 | 15.91 |
| asset prep | 0.04 | 0.00 |
| still 1 (frame 75) | 13.34 | 7.37 |
| still 2 (frame 45) | 10.21 | 7.15 |
| preview | 45.68 | 50.73 |
| render | 60.61 | 66.80 |
| encode (isolated) | 11.02 | 12.14 |
| QC | 6.07 | 7.43 |
| cell wall | 176.6 | 167.7 |
| peak RSS | 1334 MB | 1369 MB |
| peak disk (cell dir) | 12.8 MB | 13.0 MB |
| QC verdict | complete | complete |

The compile asymmetry is structural, not an error: Remotion's
compile stage includes the contracts-layer dispatch
(`loadValidatedJob`), which Hyperframes cells do not run because
their jobs are constructed directly (the MG-005 suite pattern; the
contracts scene shapes do not dispatch C01 scenes on this base, the
documented MG-025 divergence, recorded in every Hyperframes cell
record). Conversely, Hyperframes validate runs the engine CLI's
lint plus a one-session browser audit, which is where its 16 to
29 seconds go; Remotion's validate is a local check. The two
compile figures measure different shipped work and are reported
side by side for exactly that reason.

### Image-led job, Hyperframes (C01 reveal, 150 frames)

| Stage | Rep 1 | Rep 2 |
| --- | ---: | ---: |
| setup | 0.50 | 0.46 |
| compile | 22.02 | 21.78 |
| asset prep | 0.00 | 0.00 |
| still 1 (frame 60) | 8.56 | 11.46 |
| still 2 (frame 90) | 8.98 | 12.05 |
| preview | 38.48 | 65.87 |
| render | 43.04 | 71.72 |
| encode (isolated) | 8.61 | 8.42 |
| QC | 4.40 | 5.04 |
| cell wall | 134.6 | 196.9 |
| peak RSS | 1397 MB | 1350 MB |
| peak disk (cell dir) | 12.7 MB | 12.9 MB |
| QC verdict | complete | complete |

There is no Remotion column for this scene: on this base the
Remotion adapter's production job path serves C05 chart jobs, and
no image-led Remotion path exists through the shipped adapters.
The engine comparison in this report is therefore chart-only, and
the image and mixed figures are Hyperframes measurements, stated
as such wherever they are used.

### Mixed-media program, Hyperframes (chart + reveal, 330 frames)

| Stage | Rep 1 | Rep 2 |
| --- | ---: | ---: |
| setup | 0.23 | 0.27 |
| compile | 31.11 | 35.15 |
| asset prep | 0.01 | 0.01 |
| still 1 (frame 75, chart) | 8.09 | 10.52 |
| still 2 (frame 240, reveal) | 7.50 | 8.42 |
| preview | 62.05 | 81.97 |
| render | 59.29 | 87.92 |
| encode (isolated) | 9.94 | 9.39 |
| QC | 5.01 | 5.12 |
| cell wall | 183.3 | 238.8 |
| peak RSS | 1374 MB | 1359 MB |
| peak disk (cell dir) | 6.3 MB | 6.3 MB |
| QC verdict | complete | complete |

## Engine comparison (chart job only)

Same job, same canvas, fps, and duration; both engines produced
probe-verified 1920x1080, 180-frame outputs with QC verdict
complete in both repetitions (VERIFIED from the cell records and
`analysis.json`). On this machine, under the recorded load:
Remotion preview 20.8 / 21.4 s against Hyperframes 45.7 / 50.7 s;
Remotion render 32.8 / 28.7 s against Hyperframes 60.6 / 66.8 s.
Remotion was faster on this job in both repetitions at both stages.
Pixel identity is claimed only within an engine across repetitions
(see Fidelity); the two engines render different compositions of
the same spec, and no cross-engine pixel equality is asserted.

## Fidelity alongside speed

Repetition 2's final was compared against repetition 1's final for
every full cell, decoding frames with the MG-026 determinism
machinery (`decodePngPixels`, `compareDecodedPixels`, tolerance
`EXACT_PIXELS`): chart (frames 0, 45, 75, 179, both engines), image
(frames 0, 60, 90, 149), mixed (frames 0, 75, 240, 329). All 16
comparisons were pixel-identical: 0 differing pixels, maximum
channel delta 0 (VERIFIED, `analysis.json` fidelity section).
Fidelity here is pixel-level at the sampled frames, not byte-level
file equality and not every frame.

## The degraded demonstration

The degraded cell renders the chart job's preview through the
shipped preview options at half scale (`renderPreview` with
`{scale: 0.5}`). It is faster: 10.36 / 9.10 s against the full-scale
preview's 20.75 / 21.39 s, a saving of 10.40 / 12.28 s. Its output
is 960x540, not 1920x1080, and frame 45 upscaled back to 1920x1080
with a plain bilinear scale still differs from the reference frame
in 208,500 of 2,073,600 pixels (10.1 percent), identically in both
repetitions (VERIFIED, `analysis.json` degradedDemonstration). The
analysis judges it DEGRADED in both repetitions and the ranking
machinery excludes it from every speed ranking; the chart preview
and render rankings list only the four full-fidelity runs. A faster
but degraded output cannot win in this machinery, by construction
(self-checked) and by demonstration (measured).

## Failure accounting

Twelve cell runs were attempted across the two repetitions. Two
failed, both the deliberate sabotage cell (the chart job copy with
its declared dataset removed): it failed at the compile stage in
0.80 / 0.71 s when the Remotion adapter's validate pass hit the
missing dataset (MG_SCHEMA_INVALID), and the failure is recorded
with its stage and error in both repetition records, never dropped.
Failure rate: 2 of 12 = 16.7 percent counting the deliberate cell;
0 of 8 = 0 percent excluding deliberate cells. Both figures are
stated with their bases wherever the rate is quoted. The cache
program attempted 3 executions with 0 failures. The harness
self-check additionally proves over synthetic records that a failed
run is counted and excluded from rankings rather than dropped.

## Cache savings (MG-027), by stage

One cache program: the chart fixture as two jobs (the
powerpoint_graphic original and a standalone_video variant), each
one 180-frame C05 scene, rendered through `CachedRenderSession`
with production Remotion `renderFinal` renderers. Three executions
over one session work directory (VERIFIED, `cache.json`):

| Execution | Wall | Derive | Renderer calls | Result |
| --- | ---: | ---: | --- | --- |
| cold | 40,549 ms | 124 ms | 2 | both scenes rendered (16,855 + 20,995 ms of renderer time) |
| warm | 1,314 ms | 53 ms | 0 | both scenes reused after key match and artifact verification |
| partial | 24,351 ms | 21 ms | 1 | scene A reused; scene B re-rendered (22,288 ms) after its dataset changed one value, which changed its content key |

Savings, claimed only where the cache serves the stage:

- Render stage (includes the adapter's internal encode): cold
  renderer time 37,850 ms; warm renderer time 0 ms; saved
  37,850 ms on a full hit. Net wall saved cold-to-warm:
  39,235 ms. On the partial hit, scene A's 16,855 ms of renderer
  time was saved and scene B paid full price; no averaging across
  scenes is performed.
- Encode (standalone): 0 saved, by construction. No standalone
  encode exists in the cache path; the adapter's encode lives
  inside `renderFinal`, so its saving is counted once, inside the
  render stage, never twice.
- Compile (timeline) and asset preparation (key input hashing):
  0 saved, by design. Unit derivation ran on every execution
  (124 / 53 / 21 ms) because the cache can only know a hit after
  the inputs are hashed. The cost repeats; it is reported, not
  hidden.
- QC: 0 saved. The cache session performs no QC.
- Stills and preview: 0 saved. The session renders finals only.

Peak RSS during the cache program was 1,326 MB and its session
directory peaked at about 2.0 MB on disk.

## Capacity figures for the MG-028 budget (measured inputs only)

These figures are inputs to the MG-028 resource layer, measured on
this machine (2 cores, 7935 MB RAM). No budget or profile value was
changed by this item.

- Peak RSS per production cell: 1,290 to 1,397 MB across all cells
  and repetitions (maximum: image cell, repetition 1). MG-028's
  delivered budget for this machine reserves a 6,348 MB memory
  budget; one measured cell therefore occupies about a fifth of the
  budget at peak, and two concurrent cells at the worst measured
  peak sum to about 2.8 GB of RSS, inside the budget with headroom.
  That is a measurement statement, not a scheduling policy: the
  budget layer owns concurrency decisions, and RSS sums overcount
  shared pages (MG-028's stated caveat, the safe direction).
- Peak browser main processes per cell: 1 to 2 for Remotion cells,
  2 to 4 for Hyperframes cells. A single Hyperframes cell's own
  process tree peaked at 4 Chrome mains because the engine CLI
  spawns separate browsers for its audit, snapshot, and render
  steps. The MG-028 browser cap on this box is 2 (cores-bound);
  how a per-job browser accounting should treat a job whose own
  tree peaks at 4 is a budget-layer question, raised here as
  measured data.
- Peak disk per cell directory: 2.2 MB (Remotion chart) to
  13.0 MB (Hyperframes cells, including QC bundle frames). The
  shared Remotion bundle directory is 28.5 MB once per runtime.
- Stage cost shares worth scheduler attention: for the chart job,
  Hyperframes spends 16 to 29 s in its compile stage (lint plus
  browser audit) before any frame exists, where Remotion spends
  0.5 to 0.8 s; the isolated encode of a 6-second 1080p final costs
  6.7 to 14.6 s; the QC bundle costs 3.3 to 9.1 s per job.

No multi-machine or parallel-worker figure appears in this report.
Cells ran sequentially by design; concurrent throughput was not
measured, and no speedup from parallelism is claimed or implied.

## Variance, assumptions, uncertainty

- Two repetitions is a small sample by design (a smaller honest
  matrix over a large unfinished one). Cross-repetition spread
  ((max minus min) over mean, from `analysis.json`): chart preview
  spread 3.0 percent (Remotion) and 10.5 percent (Hyperframes);
  chart render 13.3 and 9.7 percent; image preview and render about
  50 percent under the recorded load difference between
  repetitions; chart-remotion still 1 spread 115 percent
  (11.18 s in repetition 1, which ran minutes after a VM restart
  with cold OS caches, against 3.00 s in repetition 2; the restart
  timing is VERIFIED from the run log, the cold-cache explanation
  is CLAIMED). Quote ranges, not points.
- Sampling: 50 ms /proc sampling can miss short spikes between
  samples; RSS sums overcount shared pages (safe direction). Both
  caveats are inherited from the MG-028 method and stated there.
- The isolated encode stage re-encodes the produced final with
  fixed settings; it measures the encode share of a final, not the
  adapter's internal encode, which remains inside the render stage
  timings.
- Asset preparation timings are small (0 to 57 ms) because the
  fixtures are small (the chart dataset is 398 bytes; the image
  asset is 11,411 bytes). They measure the shipped hashing work for
  these fixtures and do not extrapolate to production-size assets.

## Honest limits

- Cold Remotion bundle cost was not isolated: the bundle existed
  before the evidence run (built during this session's smoke runs
  on the freshly provisioned runtime), and every cell record shows
  the warm state it actually observed. The cold-versus-warm axis is
  measured where this pipeline exposes it cleanly: still 1 versus
  still 2 within Remotion cells, and the cache program's cold,
  warm, and partial executions.
- The QC stage on this base is the MG-031 critique bundle plus
  probe verification of the final. MG-034's `qc.py` is not on this
  base and is not measured here.
- The image-led and mixed scenes are Hyperframes-only measurements
  (no shipped Remotion image path exists on this base); any
  engine comparison is chart-only.
- Hyperframes asset-preparation keys for a retargeted C05 scene
  hash the canonical scene document (the payload that adapter
  consumes), while Remotion keys hash the resolved props from
  `loadC05Job`, which refuses non-Remotion routing by design. The
  two engines' key bases are named in every record and are not
  presented as identical inputs.
- Provisioning used `MOTION_RUNTIME_SKIP_APT=1`; the apt step of
  provisioning is UNVERIFIED.

## Run log

- Smoke runs (scratch only, not evidence): one image cell run that
  caught a caption/fixture-label overlap in the first staged reveal
  spec (the spec's copy and box were adjusted and re-validated), and
  a cache attempt that caught a harness bug (the cache child's
  scratch wipe removed its own TMPDIR; fixed before the matrix).
- First full launch: aborted by the worker after two cells when
  `chart-hyperframes` failed at asset preparation (the props loader
  refusal above; the harness's key collection was fixed to the
  Hyperframes basis and the matrix relaunched on one code version).
- Second full launch: repetition 1 completed; a VM restart killed
  the run during repetition 2. Its repetition 1 records are
  retained in scratch and are consistent with the evidence run
  (same stage structure; slower under its higher load).
- Evidence run: one uninterrupted parent run, log at
  `.scratch-full3.log` in the worktree (scratch, not committed),
  producing `rep-1.json`, `rep-2.json`, `cache.json`, and
  `analysis.json` as committed under `tests/evidence/mg045/`.
