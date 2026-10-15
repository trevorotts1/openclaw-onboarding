// MG-044 image component tests: the C01, C02, and C03 catalog
// bundles end to end.
//
// What this suite proves, per bundle:
// - the catalog resolves C01, C02, and C03 as dispatchable and
//   validates the shipped fixture scenes against their registered
//   closed schemas (the same scenes the catalog examples carry);
// - C01: the shipped fixture scene (the MG-005 acceptance reveal)
//   validates through the Hyperframes adapter and its subject_reveal
//   assertions pass from decoded frames. The C01 full-fps clip is
//   proven by the MG-005 suite; this suite adds the catalog lane.
// - C02: the new detail_closeup generator's geometry is the MG-012
//   close-up geometry (zoom window, annotation anchor round-trip,
//   upscale assessment within the 2x limit), the adapter validates
//   the job, the detail fraction measured from decoded frames grows
//   from the wide state to the close state as declared, and the
//   final render holds exactly 180 frames.
// - C03: the new wipe_reveal generator validates through the
//   adapter, its state_fraction assertions pass from decoded frames
//   (before only, boundary mid-travel, both states held at the rest
//   fraction), and the final render holds exactly 180 frames.
//
// Jobs are built as ValidatedMotionJob objects through the direct
// adapter lane, the same lane MG-005 and MG-039 use, because the
// canonical contracts scene $def is closed on C05; the catalog
// bundles registered by MG-044 are the governed validation and
// dispatch layer for these components, and the entries record the
// contracts limitation plainly.
//
// Evidence: curated frames and measurements.json are written to
// tests/evidence/mg044/ under the MG-043 static-record pattern: this
// runner derives measurements into the work directory and compares
// them against the committed record, failing on drift instead of
// rewriting it. Clips stay in the git-ignored work directory; their
// decoded-frame hashes are recorded in measurements.json.
//
// Exit code 0 when every case passes, 1 otherwise.

import { execFile } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { ComponentRegistry } from "../src/catalog";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import type {
  ApprovedMotionJob,
  ValidatedMotionJob,
} from "../src/adapters/types";
import type { Approval, Manifest } from "../src/validation/generated-types";
import {
  decodePng,
  measureColorFraction,
} from "../src/hyperframes/measure";
import {
  annotationAnchorAt,
  assessUpscale,
  sourcePointFromAnchor,
  zoomWindowAt,
} from "../src/compositing/closeup";
import { generateC02Project } from "../src/hyperframes/generators";
import type { ProductDetailSceneSpec } from "../src/hyperframes/generators";
import { resolveFont } from "../src/hyperframes/project";
import { checkStaticEvidenceRecord } from "./evidence-record";

const execFileP = promisify(execFile);

// The box's /tmp is a small shared tmpfs; keep every child's temp
// usage on the home filesystem (the MG-005 pattern).
const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

const FIXTURES_ROOT = process.env.MOTION_FIXTURES_ROOT
  ? resolve(process.env.MOTION_FIXTURES_ROOT)
  : join(SKILL_DIR, "tests", "fixtures");
const IMAGE_FIXTURES = join(FIXTURES_ROOT, "image-components");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg044");
const WORK_DIR = join(EVIDENCE_DIR, "work");
const RUNTIME_ROOT = join(REPO_ROOT, "shared-utils", "motion-render-runtime");

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(
      `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

async function ffprobeFrames(
  path: string
): Promise<{ frames: number; width: number; height: number }> {
  const { stdout } = await execFileP("ffprobe", [
    "-v", "error", "-count_frames", "-select_streams", "v:0",
    "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", path,
  ]);
  const parsed = JSON.parse(stdout) as {
    streams: Array<{ width: number; height: number; nb_read_frames: string }>;
  };
  const s = parsed.streams[0];
  return { frames: parseInt(s.nb_read_frames, 10), width: s.width, height: s.height };
}

function sha256File(path: string): string {
  const { createHash } = require("node:crypto") as typeof import("node:crypto");
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

/** SHA-256 of the decoded video frames (ffmpeg streamhash), not of
 * the container bytes: two renders of the same job produce identical
 * pixels but different MP4 container bytes (observed during MG-044:
 * the same C02 job rendered file hashes 5299940b and a3d95dbd on
 * consecutive runs), so a static evidence record can only pin the
 * decoded content hash. */
async function decodedVideoHash(path: string): Promise<string> {
  const { stdout } = await execFileP("ffmpeg", [
    "-v", "error", "-i", path, "-map", "0:v:0",
    "-f", "streamhash", "-hash", "sha256", "-",
  ]);
  const match = stdout.match(/SHA256=([0-9a-f]+)/);
  if (!match) throw new Error(`ffmpeg streamhash gave no SHA256 for ${path}: ${stdout}`);
  return match[1];
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

// ---------------------------------------------------------------------
// Job builders (the MG-005 shell pattern)
// ---------------------------------------------------------------------

function baseManifest(jobId: string, durationFrames: number): Manifest {
  const manifest = {
    schema_version: "2.0",
    job_id: jobId,
    company_id: "fixture-company",
    execution_context: "fixture",
    parent: null,
    mode: "standalone_video",
    content_scope: "insert",
    canvas: { width: 1920, height: 1080, fps: 30 },
    duration_frames: durationFrames,
    authoring: { selection: "inherit_config", provider: null, model: null, harness: null },
    rendering: { default_engine: "hyperframes", allow_legacy_fallback: false, runtime_lock: "runtime-lock.json" },
    storyboard: "storyboard.json",
    assets: "assets.json",
    design: "design.json",
    timeline: "timeline.json",
    audio: { mode: "none", parent_audio_ref: null, create_voiceover: false, create_music: false, source_assets: [] },
    approval_policy: "fixture_only",
    variants: [],
    scenes: [] as Array<{ id: string; spec: string }>,
    delivery: {
      video_profile: "h264_opaque",
      poster_frame: 0,
      placement: "full_frame",
      playback: { start: "automatic", repeat: "once", end: "hold_final" },
      required: ["mp4", "poster", "source_package", "placement_metadata"],
    },
  };
  return manifest as unknown as Manifest;
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg044-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg044-fixture",
    artifact_refs: [],
    actor_id: "mg044-image-components-test",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

function buildJob(
  jobName: string,
  sceneFile: string,
  assetFiles: string[]
): { jobDir: string; job: ValidatedMotionJob } {
  const jobDir = join(WORK_DIR, jobName);
  rmSync(jobDir, { recursive: true, force: true });
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  mkdirSync(join(jobDir, "scenes"), { recursive: true });
  const scene = JSON.parse(
    readFileSync(join(IMAGE_FIXTURES, sceneFile), "utf8")
  ) as Record<string, unknown>;
  for (const asset of assetFiles) {
    cpSync(join(IMAGE_FIXTURES, asset), join(jobDir, "assets", asset));
  }
  // The job-level asset hashes are computed at staging time (the
  // MG-005 pattern); the registered fixture scenes carry none.
  if (typeof scene.asset_file === "string") {
    scene.asset_sha256 = sha256File(
      join(jobDir, scene.asset_file as string)
    );
  }
  if (typeof scene.before_file === "string") {
    scene.before_sha256 = sha256File(join(jobDir, scene.before_file as string));
    scene.after_sha256 = sha256File(join(jobDir, scene.after_file as string));
  }
  writeFileSync(
    join(jobDir, "scenes", `${String(scene.id)}.json`),
    JSON.stringify(scene, null, 2) + "\n",
    "utf8"
  );
  const duration = scene.duration_frames as number;
  const manifest = baseManifest(`mg044-${jobName}`, duration);
  manifest.scenes = [
    { id: String(scene.id), spec: `scenes/${String(scene.id)}.json` },
  ] as Manifest["scenes"];
  writeFileSync(
    join(jobDir, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
    "utf8"
  );
  writeFileSync(
    join(jobDir, "timeline.json"),
    JSON.stringify(
      {
        schema_version: "2.0",
        job_id: `mg044-${jobName}`,
        fps: 30,
        total_frames: duration,
        scenes: [],
        events: [],
        parent_slot: null,
        audio_owner: "none",
      },
      null,
      2
    ) + "\n",
    "utf8"
  );
  return {
    jobDir,
    job: { jobDir, jobId: `mg044-${jobName}`, manifest },
  };
}

interface Case {
  name: string;
  run: () => Promise<void>;
}

async function main(): Promise<number> {
  mkdirSync(WORK_DIR, { recursive: true });
  const adapter = new HyperframesAdapter({ runtimeRoot: RUNTIME_ROOT });
  const registry = ComponentRegistry.createDefault();
  const measurements: Record<string, unknown> = {
    suite: "mg044-image-components",
    note:
      "C01, C02, and C03 catalog bundles (MG-044): catalog dispatch, " +
      "MG-012 geometry, adapter validation, decoded-frame proof, and " +
      "final frame counts. Clips live in the git-ignored work directory; " +
      "their decoded-frame hashes are recorded here.",
  };

  const c01 = buildJob("c01-job", "c01-reveal.scene.json", ["subject.svg"]);
  const c02 = buildJob("c02-job", "c02-detail.scene.json", ["product.svg"]);
  const c03 = buildJob("c03-job", "c03-compare.scene.json", [
    "before.svg",
    "after.svg",
  ]);
  const c02Scene = JSON.parse(
    readFileSync(join(IMAGE_FIXTURES, "c02-detail.scene.json"), "utf8")
  ) as unknown as ProductDetailSceneSpec;

  const cases: Case[] = [
    {
      name: "catalog: C01, C02, C03 resolve as dispatchable and their fixture scenes validate",
      run: async () => {
        for (const id of ["C01", "C02", "C03"]) {
          assertEq(
            registry.requireDispatchable(id, "1.0.0").componentId,
            id,
            `dispatch ${id}`
          );
        }
        for (const file of [
          "c01-reveal.scene.json",
          "c02-detail.scene.json",
          "c03-compare.scene.json",
        ]) {
          const scene = JSON.parse(
            readFileSync(join(IMAGE_FIXTURES, file), "utf8")
          ) as Record<string, unknown>;
          const result = registry.validateSceneProps(scene);
          assertTrue(
            result.valid,
            `${file} should validate: ${result.findings
              .map((finding) => finding.message)
              .join("; ")}`
          );
        }
        measurements.catalog = {
          available: ["C01", "C02", "C03"],
          fixture_scenes_validated: 3,
        };
      },
    },
    {
      name: "c02 geometry: zoom window, anchor round-trip, and upscale assessment follow MG-012",
      run: async () => {
        const source = c02Scene.product.source;
        const output = c02Scene.zoom.output;
        // The MG-012 geometry works in source pixels; the scene's
        // detail point is normalized, so convert once.
        const detailPx = {
          x: c02Scene.detail.point.x * source.width,
          y: c02Scene.detail.point.y * source.height,
        };
        const window = zoomWindowAt(source, detailPx, c02Scene.zoom.max_zoom);
        assertEq(window.width, 480, "window width at zoom 2.5");
        assertEq(window.height, 276, "window height at zoom 2.5");
        assertEq(window.x, 711, "window x at zoom 2.5");
        assertEq(window.y, 292, "window y at zoom 2.5");
        const anchor = annotationAnchorAt(detailPx, window, output);
        const roundTrip = sourcePointFromAnchor(anchor, window, output);
        assertTrue(
          Math.abs(roundTrip.x - detailPx.x) <= 1 &&
            Math.abs(roundTrip.y - detailPx.y) <= 1,
          `anchor round-trip lands on the detail point: ${JSON.stringify(roundTrip)}`
        );
        const assessment = assessUpscale({
          source,
          detail: detailPx,
          maxZoom: c02Scene.zoom.max_zoom,
          output,
        });
        assertEq(assessment.factor, 1.5, "upscale factor");
        assertTrue(assessment.withinLimit, "upscale within the 2x limit");
        const project = generateC02Project({
          spec: c02Scene,
          font: resolveFont("font-fixture-sans"),
          fps: 30,
          assetFileName: "product.svg",
        });
        const html = project.files["index.html"];
        const kfMatch = html.match(/const KF = (\[.*?\]);/s);
        assertTrue(kfMatch !== null, "generator embeds its keyframe table");
        const kf = JSON.parse((kfMatch as RegExpMatchArray)[1]) as Array<{
          bgW: number;
          bgH: number;
          bgX: number;
          bgY: number;
          ax: number;
          ay: number;
        }>;
        assertEq(kf.length, 3, "generator emits three zoom keyframes");
        const maxKf = kf[2];
        const near = (a: number, b: number): boolean => Math.abs(a - b) <= 0.6;
        assertTrue(
          near(maxKf.bgW, source.width * (output.width / window.width)) &&
            near(maxKf.bgH, source.height * (output.height / window.height)) &&
            near(maxKf.bgX, -window.x * (output.width / window.width)) &&
            near(maxKf.bgY, -window.y * (output.height / window.height)) &&
            near(maxKf.ax, anchor.x) &&
            near(maxKf.ay, anchor.y),
          `maximum-zoom keyframe matches the MG-012 window and anchor: ${JSON.stringify(maxKf)}`
        );
        measurements.c02_geometry = {
          window,
          anchor: { x: round6(anchor.x), y: round6(anchor.y) },
          upscale: assessment,
        };
      },
    },
    {
      name: "c01: adapter validation passes and the reveal assertions pass from decoded frames",
      run: async () => {
        const validation = await adapter.validate(c01.job);
        assertTrue(
          validation.valid,
          `C01 job should validate: ${JSON.stringify(validation.findings)}`
        );
        const motion = await adapter.inspectMotion(c01.job, {
          startFrame: 0,
          endFrameExclusive: 150,
        });
        assertEq(motion.assertionsChecked, 3, "C01 assertions checked");
        assertEq(motion.assertionsPassed, 3, "C01 assertions passed");
        measurements.c01_reveal = { observations: motion.observations };
        for (const frame of [0, 60, 149]) {
          const still = await adapter.renderStill(c01.job, frame);
          cpSync(
            join(c01.jobDir, still.outputPaths[0]),
            join(EVIDENCE_DIR, `c01-f${frame}.png`)
          );
        }
      },
    },
    {
      name: "c02: detail fraction grows from the wide state to the close state as declared",
      run: async () => {
        const validation = await adapter.validate(c02.job);
        assertTrue(
          validation.valid,
          `C02 job should validate: ${JSON.stringify(validation.findings)}`
        );
        const out = c02Scene.zoom.output;
        const color = c02Scene.detail.measure_color;
        const fractions: Record<string, number> = {};
        for (const frame of [0, 60, 150]) {
          const still = await adapter.renderStill(c02.job, frame);
          const img = await decodePng(join(c02.jobDir, still.outputPaths[0]));
          fractions[`f${frame}`] = measureColorFraction(img, out, color);
          cpSync(
            join(c02.jobDir, still.outputPaths[0]),
            join(EVIDENCE_DIR, `c02-f${frame}.png`)
          );
        }
        const hold = fractions.f150;
        assertTrue(hold > 0.04, `hold detail fraction should be substantial: ${hold}`);
        const wide = fractions.f0 / hold;
        const mid = fractions.f60 / hold;
        assertTrue(
          wide >= 0 && wide <= 0.35,
          `wide state normalized fraction ${wide} within the declared [0, 0.35]`
        );
        assertTrue(
          mid >= 0.35 && mid <= 0.65,
          `mid-zoom normalized fraction ${mid} near the geometric 0.49`
        );
        measurements.c02_detail = {
          raw_fractions: {
            f0: round6(fractions.f0),
            f60: round6(fractions.f60),
            f150: round6(fractions.f150),
          },
          normalized: { f0: round6(wide), f60: round6(mid), f150: 1 },
        };
      },
    },
    {
      name: "c02: final render holds exactly 180 frames at 1920x1080",
      run: async () => {
        const approved: ApprovedMotionJob = {
          ...c02.job,
          approval: fixtureApproval("mg044-c02-job"),
        };
        const fin = await adapter.renderFinal(approved);
        const finalPath = join(c02.jobDir, fin.outputPaths[0]);
        const probe = await ffprobeFrames(finalPath);
        assertEq(probe.frames, 180, "C02 final decoded frames");
        assertEq(probe.width, 1920, "C02 final width");
        measurements.c02_clip = {
          path: finalPath,
          decoded_sha256: await decodedVideoHash(finalPath),
          frames: probe.frames,
        };
      },
    },
    {
      name: "c03: adapter validation passes and the state assertions pass from decoded frames",
      run: async () => {
        const validation = await adapter.validate(c03.job);
        assertTrue(
          validation.valid,
          `C03 job should validate: ${JSON.stringify(validation.findings)}`
        );
        const motion = await adapter.inspectMotion(c03.job, {
          startFrame: 0,
          endFrameExclusive: 180,
        });
        assertEq(motion.assertionsChecked, 3, "C03 assertions checked");
        assertEq(motion.assertionsPassed, 3, "C03 assertions passed");
        measurements.c03_compare = { observations: motion.observations };
        for (const frame of [0, 60, 179]) {
          const still = await adapter.renderStill(c03.job, frame);
          cpSync(
            join(c03.jobDir, still.outputPaths[0]),
            join(EVIDENCE_DIR, `c03-f${frame}.png`)
          );
        }
      },
    },
    {
      name: "c03: final render holds exactly 180 frames at 1920x1080",
      run: async () => {
        const approved: ApprovedMotionJob = {
          ...c03.job,
          approval: fixtureApproval("mg044-c03-job"),
        };
        const fin = await adapter.renderFinal(approved);
        const finalPath = join(c03.jobDir, fin.outputPaths[0]);
        const probe = await ffprobeFrames(finalPath);
        assertEq(probe.frames, 180, "C03 final decoded frames");
        assertEq(probe.width, 1920, "C03 final width");
        measurements.c03_clip = {
          path: finalPath,
          decoded_sha256: await decodedVideoHash(finalPath),
          frames: probe.frames,
        };
      },
    },
  ];

  let passed = 0;
  let failed = 0;
  for (const c of cases) {
    try {
      await c.run();
      passed += 1;
      console.log(`PASS ${c.name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${c.name}: ${(err as Error).message}`);
    }
  }
  measurements.cases = { passed, failed, total: cases.length };
  const recordCheck = checkStaticEvidenceRecord({
    derived: measurements,
    recordPath: join(EVIDENCE_DIR, "measurements.json"),
    scratchPath: join(WORK_DIR, "measurements.derived.json"),
    repoRoot: REPO_ROOT,
  });
  if (recordCheck.ok) {
    console.log(
      "Static evidence record matches (tests/evidence/mg044/measurements.json)"
    );
  } else {
    failed += 1;
    console.log(
      "FAIL static evidence record drift (tests/evidence/mg044/measurements.json):"
    );
    for (const d of recordCheck.diffs) console.log(`  ${d}`);
    console.log(`  derived measurements: ${recordCheck.scratchPath}`);
    console.log(
      "  if this change is intentional, adopt it by copying the derived file over the record in a reviewed change"
    );
  }
  console.log(
    `Image components: ${passed}/${cases.length} cases passed, ${failed} failed.`
  );
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`run-image-components setup failed: ${(err as Error).message}`);
    process.exit(1);
  }
);
