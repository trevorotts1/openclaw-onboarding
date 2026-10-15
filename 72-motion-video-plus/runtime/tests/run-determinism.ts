// MG-026 determinism suite: adapter-aware seek-safety verification.
//
// For each supported engine (Remotion and Hyperframes) the shipped C05
// fixture scene is rendered at the Section 17.2 proof frames under
// four access patterns (cold: a fresh process per frame; forward;
// reverse; randomized in a seeded order) and the DECODED PIXELS of
// every pattern are compared against the cold goldens. On these
// pinned CPU render paths the expectation is exact pixel identity,
// and the tolerance used is EXACT_PIXELS (zero differing pixels, zero
// channel delta). The suite also:
//
// - renders the same logical C05 scene through both engines and
//   RECORDS the measured cross-engine pixel difference without
//   asserting equality (the honest cross-engine statement is shared
//   decoded geometry, checked against the Section 17.2 widths);
// - proves the tolerance cannot pass a broken layout: a staged job
//   whose plot origin is shifted by 20 px must FAIL the verifier,
//   including under a hypothetical small antialiasing jitter budget;
// - drives standalone __setTime fixture scenes (seeded control, wall
//   clock drift, unseeded randomness) through seek histories in the
//   pinned browser and shows the control passing while both drift
//   fixtures are caught;
// - stores the environment record (engine versions from the runtime
//   lock, Node, OS, font file hashes, runtime lock id) and the
//   frozen-input hashes with the golden results in
//   tests/evidence/mg026/.
//
// The doctrine behind these choices is
// references/determinism-and-reproducibility.md.

import assert from "node:assert";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { loadValidatedJob } from "../src/adapters";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import { createRemotionAdapter } from "../src/adapters/remotion";
import {
  ACCESS_PATTERNS,
  C05_PROOF_FRAMES,
  buildEnvironmentRecord,
  captureSceneFrame,
  compareDecodedPixels,
  decodePngPixels,
  diffInputHashes,
  EXACT_PIXELS,
  hashJobInputs,
  patternOrder,
  RANDOM_PATTERN_SEED,
  runAccessPattern,
  seededOrder,
  stageHyperframesC05Job,
  stageShiftedC05Job,
  toleranceVerdict,
  type AccessPattern,
  type DecodedPixels,
  type DeterminismEnvironment,
  type PixelComparison,
  type PixelTolerance,
} from "../src/determinism";
import { loadC05Job } from "../src/remotion/job-props";
import { measureAccentBarWidths } from "../src/remotion/decode";

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const FIXTURE_JOB = join(SKILL_DIR, "tests", "fixtures", "modes", "powerpoint_graphic");
const FIXTURES_DIR = join(SKILL_DIR, "tests", "fixtures", "determinism");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg026");
const STATE_DIR = join(REPO_ROOT, "shared-utils", "motion-render-runtime", ".runtime");
const SCRATCH = join(STATE_DIR, "mg026-tests");
const TMP_DIR = join(REPO_ROOT, ".scratch", "tmp");
const SHIFT_PX = 20;
const CROSS_ENGINE_FRAMES = [45, 75];
const EXPECTED_WIDTHS: Record<number, number[]> = {
  45: [240, 360, 600],
  75: [480, 720, 1200],
};
/** A deliberately generous antialiasing jitter budget, used only to
 * prove the broken-layout negative case fails even under a tolerance
 * far looser than the exact one this suite enforces. */
const HYPOTHETICAL_JITTER: PixelTolerance = { maxDifferingPixels: 100, maxChannelDelta: 2 };

process.env.TMPDIR = TMP_DIR;

interface EngineRun {
  goldens: Map<number, DecodedPixels>;
  comparisons: Record<string, Record<number, PixelComparison & { verdict: boolean }>>;
  orders: Record<string, number[]>;
}

interface Ctx {
  environment?: DeterminismEnvironment;
  inputsBefore?: Record<string, Record<string, string>>;
  inputsAfter?: Record<string, Record<string, string>>;
  engines: Partial<Record<"remotion" | "hyperframes", EngineRun>>;
  crossEngine: Record<number, PixelComparison>;
  negative?: { comparison: PixelComparison; exactPass: boolean; jitterPass: boolean };
  scenes: Record<string, Record<string, PixelComparison>>;
}

const ctx: Ctx = { engines: {}, crossEngine: {}, scenes: {} };
const measurements: Record<string, unknown> = { item: "MG-026" };

function recordComparison(cmp: PixelComparison & { verdict?: boolean }): Record<string, unknown> {
  return {
    differingPixels: cmp.differingPixels,
    differingFraction: cmp.differingFraction,
    maxChannelDelta: cmp.maxChannelDelta,
    meanAbsDelta: cmp.meanAbsDelta,
    identical: cmp.identical,
    ...(cmp.verdict !== undefined ? { verdictPass: cmp.verdict } : {}),
  };
}

async function runEngine(
  engine: "remotion" | "hyperframes",
  jobDir: string
): Promise<EngineRun> {
  const goldens = new Map<number, DecodedPixels>();
  const comparisons: EngineRun["comparisons"] = {};
  const orders: Record<string, number[]> = {};
  for (const pattern of ACCESS_PATTERNS as AccessPattern[]) {
    const order = patternOrder(pattern, C05_PROOF_FRAMES, (items) =>
      seededOrder(items, RANDOM_PATTERN_SEED)
    );
    orders[pattern] = order;
    const run = await runAccessPattern({
      engine,
      jobDir,
      pattern,
      frames: C05_PROOF_FRAMES,
      order,
      scratchDir: SCRATCH,
      tmpDir: TMP_DIR,
      timeoutPerProcessMs: 900_000,
    });
    if (pattern === "cold") {
      for (const frame of C05_PROOF_FRAMES) {
        const png = run.pngByFrame.get(frame);
        assert.ok(png, `${engine} cold pattern produced no PNG for frame ${frame}`);
        goldens.set(frame, await decodePngPixels(png));
      }
      continue;
    }
    comparisons[pattern] = {};
    for (const frame of C05_PROOF_FRAMES) {
      const png = run.pngByFrame.get(frame);
      assert.ok(png, `${engine} ${pattern} pattern produced no PNG for frame ${frame}`);
      const decoded = await decodePngPixels(png);
      const golden = goldens.get(frame);
      assert.ok(golden, `${engine} has no cold golden for frame ${frame}`);
      const cmp = compareDecodedPixels(golden, decoded);
      comparisons[pattern][frame] = {
        ...cmp,
        verdict: toleranceVerdict(cmp, EXACT_PIXELS).pass,
      };
    }
  }
  return { goldens, comparisons, orders };
}

async function captureFixture(
  fixture: string,
  label: string,
  seeks: number[],
  waitBeforeFinalSeekMs?: number
): Promise<string> {
  const out = join(SCRATCH, "scenes", fixture, `${label}.png`);
  mkdirSync(dirname(out), { recursive: true });
  await captureSceneFrame({
    htmlPath: join(FIXTURES_DIR, `${fixture}.html`),
    width: 1920,
    height: 1080,
    seeks,
    waitBeforeFinalSeekMs,
    outPath: out,
    profileDir: join(SCRATCH, "profiles", `${fixture}-${label}`),
  });
  return out;
}

async function prepare(): Promise<void> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
  mkdirSync(TMP_DIR, { recursive: true });
  mkdirSync(EVIDENCE_DIR, { recursive: true });

  const hfJobDir = stageHyperframesC05Job(FIXTURE_JOB, join(SCRATCH, "hf-c05-job"));
  const shiftedJobDir = stageShiftedC05Job(FIXTURE_JOB, join(SCRATCH, "shifted-c05-job"), SHIFT_PX);

  ctx.inputsBefore = {
    remotionJob: hashJobInputs(FIXTURE_JOB),
    hyperframesJob: hashJobInputs(hfJobDir),
    shiftedJob: hashJobInputs(shiftedJobDir),
  };

  ctx.engines.remotion = await runEngine("remotion", FIXTURE_JOB);
  ctx.engines.hyperframes = await runEngine("hyperframes", hfJobDir);

  for (const frame of CROSS_ENGINE_FRAMES) {
    const r = ctx.engines.remotion.goldens.get(frame);
    const h = ctx.engines.hyperframes.goldens.get(frame);
    assert.ok(r && h, `missing goldens for cross-engine frame ${frame}`);
    ctx.crossEngine[frame] = compareDecodedPixels(r, h);
  }

  const negativeRun = await runAccessPattern({
    engine: "remotion",
    jobDir: shiftedJobDir,
    pattern: "cold",
    frames: [75],
    order: [75],
    scratchDir: join(SCRATCH, "negative"),
    tmpDir: TMP_DIR,
    timeoutPerProcessMs: 900_000,
  });
  const shiftedPng = negativeRun.pngByFrame.get(75);
  assert.ok(shiftedPng, "negative case produced no PNG");
  const golden75 = ctx.engines.remotion.goldens.get(75);
  assert.ok(golden75, "missing remotion golden for frame 75");
  const cmp = compareDecodedPixels(golden75, await decodePngPixels(shiftedPng));
  ctx.negative = {
    comparison: cmp,
    exactPass: toleranceVerdict(cmp, EXACT_PIXELS).pass,
    jitterPass: toleranceVerdict(cmp, HYPOTHETICAL_JITTER).pass,
  };

  const sceneCaptures: Record<string, Record<string, string>> = {
    "control-seeded": {
      cold: await captureFixture("control-seeded", "cold", [2.5]),
      history: await captureFixture("control-seeded", "history", [0, 5.9, 1.2, 2.5]),
      delayed: await captureFixture("control-seeded", "delayed", [0.5, 2.5], 650),
    },
    "drift-wallclock": {
      cold: await captureFixture("drift-wallclock", "cold", [2.5]),
      delayed: await captureFixture("drift-wallclock", "delayed", [0.5, 2.5], 650),
    },
    "drift-unseeded": {
      coldA: await captureFixture("drift-unseeded", "coldA", [2.5]),
      coldB: await captureFixture("drift-unseeded", "coldB", [2.5]),
      reseek: await captureFixture("drift-unseeded", "reseek", [1.0, 2.5]),
    },
  };
  for (const [fixture, captures] of Object.entries(sceneCaptures)) {
    const decoded: Record<string, DecodedPixels> = {};
    for (const [label, path] of Object.entries(captures)) {
      decoded[label] = await decodePngPixels(path);
    }
    const labels = Object.keys(decoded);
    ctx.scenes[fixture] = {};
    for (let i = 1; i < labels.length; i += 1) {
      ctx.scenes[fixture][`${labels[0]}_vs_${labels[i]}`] = compareDecodedPixels(
        decoded[labels[0]],
        decoded[labels[i]]
      );
    }
  }

  ctx.inputsAfter = {
    remotionJob: hashJobInputs(FIXTURE_JOB),
    hyperframesJob: hashJobInputs(hfJobDir),
    shiftedJob: hashJobInputs(shiftedJobDir),
  };
}

function engineMeasurements(run: EngineRun): Record<string, unknown> {
  const goldens: Record<string, unknown> = {};
  for (const [frame, decoded] of run.goldens) {
    goldens[String(frame)] = {
      pixelSha256: decoded.pixelSha256,
      fileSha256: decoded.fileSha256,
      width: decoded.width,
      height: decoded.height,
    };
  }
  const patterns: Record<string, unknown> = {};
  for (const [pattern, byFrame] of Object.entries(run.comparisons)) {
    const frames: Record<string, unknown> = {};
    for (const [frame, cmp] of Object.entries(byFrame)) {
      frames[frame] = recordComparison(cmp);
    }
    patterns[pattern] = { requestedOrder: run.orders[pattern], frames };
  }
  return { goldens, coldOrder: run.orders["cold"], patterns };
}

const CASES: { name: string; run: () => void | Promise<void> }[] = [
  {
    name: "runtime probes pass and the environment record is complete",
    run: async () => {
      const remotion = createRemotionAdapter({ outputDir: join(SCRATCH, "probe") });
      const hyperframes = new HyperframesAdapter();
      const [rProbe, hProbe] = await Promise.all([
        remotion.probeRuntime(),
        hyperframes.probeRuntime(),
      ]);
      assert.equal(rProbe.status, "ready", `remotion probe: ${rProbe.detail}`);
      assert.equal(hProbe.status, "ready", `hyperframes probe: ${hProbe.detail}`);
      const job = loadValidatedJob(FIXTURE_JOB);
      ctx.environment = buildEnvironmentRecord(job);
      const env = ctx.environment;
      assert.match(env.runtimeLockId, /^lock-/, "runtime lock id recorded");
      assert.equal(env.engines.remotion, "4.0.535", "remotion version comes from the lock");
      assert.equal(env.engines.hyperframes, "0.8.155", "hyperframes version comes from the lock");
      assert.equal(env.node.process, process.version, "node version recorded from the process");
      const remotionHashes = env.fonts.remotion.map((f) => f.sha256).sort();
      const hyperframesHashes = env.fonts.hyperframes.map((f) => f.sha256).sort();
      assert.deepEqual(
        remotionHashes,
        hyperframesHashes,
        "both engines resolve the same font bytes for the fixture job"
      );
      measurements["environment"] = env;
    },
  },
  {
    name: "remotion: decoded pixels identical across cold, forward, reverse, randomized access",
    run: () => {
      const run = ctx.engines.remotion;
      assert.ok(run, "remotion pattern runs missing");
      for (const [frame, golden] of run.goldens) {
        assert.equal(golden.width, 1920, `frame ${frame} width`);
        assert.equal(golden.height, 1080, `frame ${frame} height`);
      }
      for (const [pattern, byFrame] of Object.entries(run.comparisons)) {
        for (const [frame, cmp] of Object.entries(byFrame)) {
          assert.equal(
            cmp.differingPixels,
            0,
            `remotion ${pattern} frame ${frame} differs from the cold golden in ${cmp.differingPixels} pixels`
          );
          assert.equal(cmp.maxChannelDelta, 0, `remotion ${pattern} frame ${frame} channel delta`);
          assert.ok(cmp.verdict, `remotion ${pattern} frame ${frame} verdict`);
        }
      }
      measurements["remotion"] = engineMeasurements(run);
    },
  },
  {
    name: "hyperframes: decoded pixels identical across cold, forward, reverse, randomized access",
    run: () => {
      const run = ctx.engines.hyperframes;
      assert.ok(run, "hyperframes pattern runs missing");
      for (const [frame, golden] of run.goldens) {
        assert.equal(golden.width, 1920, `frame ${frame} width`);
        assert.equal(golden.height, 1080, `frame ${frame} height`);
      }
      for (const [pattern, byFrame] of Object.entries(run.comparisons)) {
        for (const [frame, cmp] of Object.entries(byFrame)) {
          assert.equal(
            cmp.differingPixels,
            0,
            `hyperframes ${pattern} frame ${frame} differs from the cold golden in ${cmp.differingPixels} pixels`
          );
          assert.equal(cmp.maxChannelDelta, 0, `hyperframes ${pattern} frame ${frame} channel delta`);
          assert.ok(cmp.verdict, `hyperframes ${pattern} frame ${frame} verdict`);
        }
      }
      measurements["hyperframes"] = engineMeasurements(run);
    },
  },
  {
    name: "cross-engine: difference measured and reported, decoded geometry agrees, equality not asserted",
    run: () => {
      const loaded = loadC05Job(loadValidatedJob(FIXTURE_JOB));
      const layout = loaded.layout;
      const record: Record<string, unknown> = {};
      for (const frame of CROSS_ENGINE_FRAMES) {
        const cmp = ctx.crossEngine[frame];
        assert.ok(cmp, `cross-engine comparison missing for frame ${frame}`);
        const r = ctx.engines.remotion?.goldens.get(frame);
        const h = ctx.engines.hyperframes?.goldens.get(frame);
        assert.ok(r && h, `goldens missing for frame ${frame}`);
        const rWidths = measureAccentBarWidths(r.rgb, r.width, layout, "#C04A26");
        const hWidths = measureAccentBarWidths(h.rgb, h.width, layout, "#C04A26");
        const expected = EXPECTED_WIDTHS[frame];
        rWidths.forEach((w, i) =>
          assert.ok(Math.abs(w - expected[i]) <= 2, `remotion frame ${frame} bar ${i}: ${w} vs ${expected[i]}`)
        );
        hWidths.forEach((w, i) =>
          assert.ok(Math.abs(w - expected[i]) <= 2, `hyperframes frame ${frame} bar ${i}: ${w} vs ${expected[i]}`)
        );
        record[String(frame)] = {
          comparison: recordComparison(cmp),
          pixelsIdentical: cmp.identical,
          barWidths: { expected, remotion: rWidths, hyperframes: hWidths },
          note:
            "Cross-engine pixel identity is not promised or asserted (MG-026). " +
            "The recorded difference is the honest rasterization gap between two " +
            "engines in this environment; the shared claim is decoded data geometry.",
        };
      }
      measurements["crossEngine"] = record;
    },
  },
  {
    name: "negative: a 20 px layout shift fails the verifier, even under a loose jitter budget",
    run: () => {
      const neg = ctx.negative;
      assert.ok(neg, "negative case missing");
      assert.equal(neg.exactPass, false, "shifted frame must fail the exact tolerance");
      assert.equal(
        neg.jitterPass,
        false,
        "shifted frame must fail even a generous antialiasing jitter budget"
      );
      assert.ok(
        neg.comparison.differingPixels >= 10000,
        `shifted frame differs in ${neg.comparison.differingPixels} pixels; a clearly visible 20 px shift must move far more than 10000`
      );
      measurements["negativeLayoutShift"] = {
        shiftPx: SHIFT_PX,
        frame: 75,
        comparison: recordComparison(neg.comparison),
        verdictUnderExact: neg.exactPass,
        verdictUnderHypotheticalJitter: neg.jitterPass,
        hypotheticalJitter: HYPOTHETICAL_JITTER,
      };
    },
  },
  {
    name: "legacy control scene: seeded scene is pixel-identical under every seek history",
    run: () => {
      const scenes = ctx.scenes["control-seeded"];
      assert.ok(scenes, "control scene captures missing");
      for (const [pair, cmp] of Object.entries(scenes)) {
        assert.equal(
          cmp.differingPixels,
          0,
          `control scene ${pair} differs in ${cmp.differingPixels} pixels`
        );
      }
      measurements["legacyControl"] = Object.fromEntries(
        Object.entries(scenes).map(([k, v]) => [k, recordComparison(v)])
      );
    },
  },
  {
    name: "legacy drift: wall clock driven scene is caught by the verifier",
    run: () => {
      const scenes = ctx.scenes["drift-wallclock"];
      assert.ok(scenes, "wallclock scene captures missing");
      const cmp = scenes["cold_vs_delayed"];
      assert.ok(cmp, "wallclock cold vs delayed comparison missing");
      assert.ok(
        cmp.differingPixels >= 1000,
        `wall clock drift moved only ${cmp.differingPixels} pixels; the fixture must drift visibly`
      );
      assert.equal(
        toleranceVerdict(cmp, EXACT_PIXELS).pass,
        false,
        "wall clock drift must fail the exact tolerance"
      );
      measurements["legacyWallclockDrift"] = { cold_vs_delayed: recordComparison(cmp) };
    },
  },
  {
    name: "legacy drift: unseeded randomness is caught by the verifier",
    run: () => {
      const scenes = ctx.scenes["drift-unseeded"];
      assert.ok(scenes, "unseeded scene captures missing");
      const cmp = scenes["coldA_vs_coldB"];
      assert.ok(cmp, "unseeded coldA vs coldB comparison missing");
      assert.ok(
        cmp.differingPixels >= 500,
        `unseeded scatter changed only ${cmp.differingPixels} pixels between two cold captures of the same frame`
      );
      assert.equal(
        toleranceVerdict(cmp, EXACT_PIXELS).pass,
        false,
        "unseeded randomness must fail the exact tolerance"
      );
      measurements["legacyUnseededDrift"] = Object.fromEntries(
        Object.entries(scenes).map(([k, v]) => [k, recordComparison(v)])
      );
    },
  },
  {
    name: "frozen inputs: job files are byte-identical before and after all rendering",
    run: () => {
      const before = ctx.inputsBefore;
      const after = ctx.inputsAfter;
      if (!before || !after) {
        throw new Error("input hash records missing");
      }
      // Every input file must survive rendering byte-identical, and
      // nothing may be removed. New files are legitimate only as
      // adapter render outputs under a job's renders/ area (the
      // Hyperframes adapter writes snapshot evidence there); a new
      // file anywhere else means something wrote into the input
      // space. A whole-directory deepEqual cannot express this: it
      // reported the adapter's own snapshot outputs as "mutation"
      // while every actual input byte was unchanged.
      const record: Record<string, unknown> = {};
      for (const job of Object.keys(before)) {
        const diff = diffInputHashes(before[job], after[job]);
        assert.deepEqual(
          diff.changed,
          [],
          `${job}: rendering changed input files: ${diff.changed.join(", ")}`
        );
        assert.deepEqual(
          diff.removed,
          [],
          `${job}: rendering removed input files: ${diff.removed.join(", ")}`
        );
        assert.deepEqual(
          diff.addedOther,
          [],
          `${job}: rendering wrote new files outside the renders/ output area: ${diff.addedOther.join(", ")}`
        );
        record[job] = { inputs: before[job], addedRenderOutputs: diff.addedOutputs };
      }
      measurements["frozenInputs"] = record;
      measurements["tolerance"] = {
        policy: "exact decoded pixels within one engine and one pinned environment",
        maxDifferingPixels: EXACT_PIXELS.maxDifferingPixels,
        maxChannelDelta: EXACT_PIXELS.maxChannelDelta,
        randomPatternSeed: RANDOM_PATTERN_SEED,
        frames: C05_PROOF_FRAMES,
      };
    },
  },
];

async function main(): Promise<void> {
  await prepare();
  let passed = 0;
  const failures: { name: string; error: string }[] = [];
  for (const testCase of CASES) {
    try {
      await testCase.run();
      passed += 1;
      console.log(`PASS ${testCase.name}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      failures.push({ name: testCase.name, error: message });
      console.log(`FAIL ${testCase.name}: ${message}`);
    }
  }
  measurements["summary"] = { total: CASES.length, passed, failed: failures.length, failures };
  measurements["generatedAt"] = new Date().toISOString();
  writeFileSync(join(EVIDENCE_DIR, "measurements.json"), JSON.stringify(measurements, null, 2) + "\n", "utf8");
  if (ctx.environment) {
    writeFileSync(
      join(EVIDENCE_DIR, "environment.json"),
      JSON.stringify(ctx.environment, null, 2) + "\n",
      "utf8"
    );
  }
  console.log(`Determinism: ${passed}/${CASES.length} cases passed, ${failures.length} failed.`);
  if (failures.length > 0) process.exit(1);
}

main().catch((err: unknown) => {
  console.error(`run-determinism failed: ${(err as Error)?.stack ?? String(err)}`);
  if (!existsSync(join(EVIDENCE_DIR, "measurements.json"))) {
    mkdirSync(EVIDENCE_DIR, { recursive: true });
  }
  measurements["fatal"] = (err as Error)?.message ?? String(err);
  writeFileSync(join(EVIDENCE_DIR, "measurements.json"), JSON.stringify(measurements, null, 2) + "\n", "utf8");
  process.exit(1);
});
