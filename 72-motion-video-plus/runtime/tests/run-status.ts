// MG-046 test runner: status, recovery, and delivery evidence
// integrated with the existing task surfaces, plus the two wiring
// settlements this item owns.
//
//   - One task identity from intake through delivery: the
//     MotionStatusTracker ledger in the job directory, with
//     RENDERED, QC_PASSED, APPROVED, and DELIVERED distinguished
//     from the separate release axis, production approval events
//     (MG-025 gate semantics) kept distinct from code-review
//     approval, inserts reporting under their parent task (the
//     MG-037 bridge identity), and delivery blocked BY NAME when a
//     mandatory artifact, the final QC record, or the delivery
//     approval is missing.
//   - Settlement A (MG-027): the dispatcher opens a cache session
//     per job, supplies per-scene renderers backed by the routed
//     adapter, and assembles only from artifactPathFor. Proven
//     with a fake-adapter fast cycle (render once, reuse,
//     re-render only the corrupted scene) and with a real
//     production-path job killed mid-render by SIGKILL and
//     resumed in a fresh process, the finished scene byte-identical
//     and unre-rendered.
//   - Settlement B (MG-040): routeJob consults selectExportRoute
//     when the caller supplies an export toolchain probe, so a
//     probe-qualified alpha job routes and renders through the
//     qualified profile and an unqualifiable alpha job refuses
//     MG_CAPABILITY_UNSUPPORTED by name before authoring. Without
//     the opt-in the matrix-only refusal is unchanged, and the
//     shipped capability matrix is never written.
//
// Run with: npm run build && node dist/tests/run-status.js

import Ajv2020 from "ajv/dist/2020";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import {
  AdapterError,
  createRegistry,
  loadCapabilityMatrix,
  loadValidatedJob,
  MotionDispatcher,
  type ArtifactEvidence,
  type ApprovedMotionJob,
  type CapabilityMatrix,
  type Engine,
  type EngineCapabilityRecord,
  type MotionEvidence,
  type MotionRendererAdapter,
  type RuntimeEvidence,
  type RuntimeIdentity,
  type ValidatedMotionJob,
  type ValidationEvidence,
} from "../src/adapters";
import { probeVideoFile } from "../src/remotion/decode";
import type { Approval } from "../src/validation/generated-types";
import {
  ExportError,
  probeExportToolchain,
  type ExportToolchainProbe,
} from "../src/export";
import {
  computeRevisionLock,
  signApprovalEvent,
  type GateRuntimeIdentity,
} from "../src/orchestrator";
import {
  MotionStatusTracker,
  StatusError,
  validateDeliveryReceipt,
  type DeliveryReceipt,
} from "../src/status";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function skillRoot(): string {
  return resolve(__dirname, "..", "..", "..");
}

function runtimeStateDir(): string {
  const override = process.env.MOTION_RUNTIME_STATE_DIR;
  if (override) return resolve(override);
  return resolve(
    __dirname, "..", "..", "..", "..",
    "shared-utils", "motion-render-runtime", ".runtime"
  );
}

const FIXTURES = fixturesRoot();
const APPROVALS_DIR = join(FIXTURES, "approvals");
const DIST_SRC = resolve(__dirname, "..", "src");
const MATRIX_PATH = join(skillRoot(), "references", "renderer-capabilities.json");
const RECEIPT_SCHEMA_PATH = join(skillRoot(), "references", "delivery-receipt-schema.json");
const EVIDENCE_DIR = resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg046");

const RUNTIME: GateRuntimeIdentity = {
  engine: "remotion",
  engineVersion: "4.0.535",
  runtimeLockId: "lock-mg025-test",
};

function fakeRuntime(engine: Engine): RuntimeIdentity {
  return {
    engine,
    engineVersion: "fake",
    runtimeLockId: "lock-fake",
    nodeVersion: process.version,
    platform: "linux x64",
    probedAt: "2026-10-15T00:00:00.000Z",
  };
}

// ---- assertion helpers (repo convention) ---------------------------

function assertTrue(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`assertion failed: ${msg}`);
}

function assertEq<T>(actual: T, expected: T, msg: string): void {
  if (actual !== expected) {
    throw new Error(
      `assertion failed: ${msg} (expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)})`
    );
  }
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

function writeJson(path: string, doc: unknown): void {
  writeFileSync(path, `${JSON.stringify(doc, null, 2)}\n`, "utf8");
}

function editJson(path: string, fn: (doc: Record<string, unknown>) => void): void {
  const doc = readJson(path);
  fn(doc);
  writeJson(path, doc);
}

// ---- staging helpers ------------------------------------------------

function stageFixture(mode: string): string {
  const staging = mkdtempSync(join(tmpdir(), "motion-status-"));
  const dir = join(staging, mode);
  cpSync(join(FIXTURES, "modes", mode), dir, { recursive: true });
  return dir;
}

function editManifestFile(dir: string, fn: (doc: Record<string, unknown>) => void): void {
  editJson(join(dir, "manifest.json"), fn);
}

/** Stages the powerpoint_graphic fixture as a two-scene program:
 * a second C05 scene (bar-02, its own dataset) placed after bar-01,
 * with manifest, storyboard, and timeline updated consistently so
 * the contracts layer validates the package. */
function stageTwoSceneJob(label: string): string {
  const dir = stageFixture("powerpoint_graphic");
  // Second dataset (same domain, different rows).
  const dataB = readJson(join(dir, "data", "bars.json"));
  dataB.id = "bars-b-illustrative";
  dataB.rows = [
    { id: "a", label: "Group A", value: 6 },
    { id: "b", label: "Group B", value: 24 },
    { id: "c", label: "Group C", value: 30 },
  ];
  writeJson(join(dir, "data", "bars-b.json"), dataB);
  // Second scene spec with assertions derived from its dataset
  // (values 6/24/30 on domain [0,30], plot width 1200).
  const specB = readJson(join(dir, "scenes", "bar-01.json"));
  specB.id = "bar-02";
  specB.data_path = "data/bars-b.json";
  const assertionList = specB.semantic_motion_assertions as Record<string, unknown>[];
  for (const assertion of assertionList) {
    if (assertion.id === "half-reveal") assertion.expected_values = [120, 480, 600];
    if (assertion.id === "final-ratios") assertion.expected_values = [240, 960, 1200];
  }
  writeJson(join(dir, "scenes", "bar-02.json"), specB);
  // Manifest and storyboard.
  editManifestFile(dir, (doc) => {
    (doc.scenes as unknown[]).push({ id: "bar-02", spec: "scenes/bar-02.json" });
    doc.duration_frames = 360;
  });
  editJson(join(dir, "storyboard.json"), (doc) => {
    const beats = doc.beats as Record<string, unknown>[];
    const second = JSON.parse(JSON.stringify(beats[0])) as Record<string, unknown>;
    second.id = "beat-bars-b";
    second.scene_id = "bar-02";
    second.data_ids = ["bars-b-illustrative"];
    beats.push(second);
  });
  editJson(join(dir, "timeline.json"), (doc) => {
    doc.total_frames = 360;
    const scenes = doc.scenes as Record<string, unknown>[];
    scenes.push({
      id: "bar-02",
      start_frame: 180,
      end_frame_exclusive: 360,
      source_start_frame: 0,
      transition_in_frames: 0,
      transition_out_frames: 0,
    });
    const events = doc.events as Record<string, unknown>[];
    const copies = events
      .filter((e) => e.scene_id === "bar-01")
      .map((e) => ({
        ...e,
        id: `${String(e.id)}-b`,
        scene_id: "bar-02",
        frame: (e.frame as number) + 180,
      }));
    events.push(...copies);
  });
  void label;
  return dir;
}

// ---- fake adapters ----------------------------------------------------

class FakeAdapter implements MotionRendererAdapter {
  readonly engine: Engine;
  readonly calls: string[] = [];
  /** When true, renderFinal writes a real renders/final.mp4 into
   * the job directory so the status tracker can measure it. */
  writeFinalIntoJob = false;

  constructor(engine: Engine) {
    this.engine = engine;
  }

  count(method: string): number {
    return this.calls.filter((c) => c === method).length;
  }

  totalCalls(): number {
    return this.calls.length;
  }

  private evidence(job: ValidatedMotionJob, kind: "still" | "preview" | "final"): ArtifactEvidence {
    let artifacts: ArtifactEvidence["artifacts"] = [];
    let outputPaths: string[] = [];
    if (this.writeFinalIntoJob && kind === "final") {
      const rendersDir = join(job.jobDir, "renders");
      mkdirSync(rendersDir, { recursive: true });
      const abs = join(rendersDir, "final.mp4");
      writeFileSync(abs, "mg046 fake final render bytes\n", "utf8");
      artifacts = [{ path: "renders/final.mp4", sha256: sha256File(abs) }];
      outputPaths = [abs];
    }
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      kind,
      artifacts,
      outputPaths,
      exitCode: 0,
      stderrLog: null,
      startedAt: "2026-10-15T00:00:00.000Z",
      finishedAt: "2026-10-15T00:00:01.000Z",
      durationMs: 1000,
    };
  }

  async probeRuntime(): Promise<RuntimeEvidence> {
    this.calls.push("probeRuntime");
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      status: "ready",
      capabilities: null,
      checkedAt: "2026-10-15T00:00:00.000Z",
      detail: "fake adapter",
    };
  }

  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    this.calls.push("validate");
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      valid: true,
      findings: [],
      firstErrorCategory: null,
      checkedAt: "2026-10-15T00:00:00.000Z",
    };
  }

  async renderStill(job: ValidatedMotionJob, _frame: number): Promise<ArtifactEvidence> {
    this.calls.push("renderStill");
    return this.evidence(job, "still");
  }

  async renderPreview(job: ValidatedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderPreview");
    return this.evidence(job, "preview");
  }

  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderFinal");
    return this.evidence(job, "final");
  }

  async inspectMotion(
    job: ValidatedMotionJob,
    range: { startFrame: number; endFrameExclusive: number }
  ): Promise<MotionEvidence> {
    this.calls.push("inspectMotion");
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      range,
      assertionsChecked: 0,
      assertionsPassed: 0,
      observations: [],
      inspectedAt: "2026-10-15T00:00:00.000Z",
    };
  }

  async cancel(_jobId: string): Promise<void> {
    this.calls.push("cancel");
  }
}

/** A fake adapter that writes real, tiny ffmpeg videos (12 frames
 * at 320x180) so the cache session's probe verification runs on
 * genuine media. One render per staged scene job. */
class FakeVideoAdapter implements MotionRendererAdapter {
  readonly engine: Engine = "remotion";
  readonly sceneCalls: string[] = [];
  private readonly outDir: string;

  constructor(outDir: string) {
    this.outDir = outDir;
    mkdirSync(outDir, { recursive: true });
  }

  private evidence(job: ValidatedMotionJob, kind: "still" | "preview" | "final", paths: string[] = []): ArtifactEvidence {
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      kind,
      artifacts: paths.map((p) => ({ path: p, sha256: sha256File(p) })),
      outputPaths: paths,
      exitCode: 0,
      stderrLog: null,
      startedAt: "2026-10-15T00:00:00.000Z",
      finishedAt: "2026-10-15T00:00:01.000Z",
      durationMs: 1000,
    };
  }

  async probeRuntime(): Promise<RuntimeEvidence> {
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      status: "ready",
      capabilities: null,
      checkedAt: "2026-10-15T00:00:00.000Z",
      detail: "fake video adapter",
    };
  }

  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      valid: true,
      findings: [],
      firstErrorCategory: null,
      checkedAt: "2026-10-15T00:00:00.000Z",
    };
  }

  async renderStill(job: ValidatedMotionJob, _frame: number): Promise<ArtifactEvidence> {
    return this.evidence(job, "still");
  }

  async renderPreview(job: ValidatedMotionJob): Promise<ArtifactEvidence> {
    return this.evidence(job, "preview");
  }

  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    const sceneId = (job.manifest.scenes as unknown as { id: string }[])[0].id;
    this.sceneCalls.push(sceneId);
    const color = sceneId === "bar-01" ? "0xC04A26" : "0x2456A6";
    const out = join(this.outDir, `${sceneId}.mp4`);
    const result = spawnSync(
      "ffmpeg",
      ["-y", "-v", "error", "-f", "lavfi", "-i", `color=c=${color}:s=320x180:r=30:d=0.4`,
       "-frames:v", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
      { encoding: "utf8" }
    );
    if (result.status !== 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: this.engine,
        message: `fake video render failed: ${result.stderr}`,
      });
    }
    return this.evidence(job, "final", [out]);
  }

  async inspectMotion(
    job: ValidatedMotionJob,
    range: { startFrame: number; endFrameExclusive: number }
  ): Promise<MotionEvidence> {
    return {
      engine: this.engine,
      runtime: fakeRuntime(this.engine),
      jobId: job.jobId,
      range,
      assertionsChecked: 0,
      assertionsPassed: 0,
      observations: [],
      inspectedAt: "2026-10-15T00:00:00.000Z",
    };
  }

  async cancel(_jobId: string): Promise<void> {}
}

// ---- matrices and approvals ------------------------------------------

function readyRecord(engine: Engine): EngineCapabilityRecord {
  return {
    engine,
    probeStatus: "ready",
    installedVersion: engine === "remotion" ? "4.0.535" : "0.8.155",
    runtimeLockId: "lock-mg025-test",
    probedAt: "2026-10-15T00:00:00.000Z",
    platform: "linux",
    codecs: ["h264", "prores", "vp9"],
    transparency: { alphaVideo: true, profiles: ["prores_4444_alpha", "vp9_alpha"] },
    mediaTypes: ["image/png", "video/mp4"],
    features3d: [],
    evidence: ["run-status fixture record"],
  };
}

function dispatcherMatrix(): CapabilityMatrix {
  return {
    schemaVersion: "1.0",
    generatedAt: "2026-10-15T00:00:00.000Z",
    source: "run-status fixture",
    engines: [readyRecord("hyperframes"), readyRecord("remotion")],
  };
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg046-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg046-test-runner",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

function readApprovals(dir: string): Approval[] {
  return JSON.parse(readFileSync(join(dir, "approvals.json"), "utf8")) as Approval[];
}

function writeApprovals(dir: string, approvals: Approval[]): void {
  writeFileSync(join(dir, "approvals.json"), `${JSON.stringify(approvals, null, 2)}\n`, "utf8");
}

function keyring(): Record<string, string> {
  return readJson(join(APPROVALS_DIR, "keyring.json")) as Record<string, string>;
}

/** The run-approvals makeApproval pattern: sign the approval
 * event with the fixture keyring, write the detached event
 * artifact, then bind its hash in the approval's artifact_refs. */
function makeApproval(
  dir: string,
  spec: {
    approval_id: string;
    scope: Approval["scope"];
    subject_revision: string;
    actor_id: string;
    artifact_refs: Array<{ path: string; sha256: string }>;
  }
): Approval {
  const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8")) as Record<string, string>;
  const eventRel = `approvals/${spec.approval_id}.event.json`;
  const event = signApprovalEvent(
    {
      event_id: `evt-${spec.approval_id}`,
      approval_id: spec.approval_id,
      job_id: manifest.job_id,
      company_id: manifest.company_id,
      scope: spec.scope,
      decision: "approved",
      subject_revision: spec.subject_revision,
      actor_id: spec.actor_id,
      artifact_refs: spec.artifact_refs,
    },
    keyring()[spec.actor_id]
  );
  mkdirSync(join(dir, "approvals"), { recursive: true });
  writeFileSync(join(dir, eventRel), `${JSON.stringify(event, null, 2)}\n`, "utf8");
  return {
    schema_version: "2.0",
    approval_id: spec.approval_id,
    job_id: manifest.job_id,
    company_id: manifest.company_id,
    scope: spec.scope,
    decision: "approved",
    subject_revision: spec.subject_revision,
    artifact_refs: [...spec.artifact_refs, { path: eventRel, sha256: sha256File(join(dir, eventRel)) }],
    actor_id: spec.actor_id,
    source_event_ref: eventRel,
    authority_status: "verified",
  };
}

function stageApprovalsFixture(name: string): string {
  const staging = mkdtempSync(join(tmpdir(), "motion-status-"));
  const dir = join(staging, name);
  cpSync(join(APPROVALS_DIR, name), dir, { recursive: true });
  return dir;
}

function readEvents(dir: string): Record<string, unknown>[] {
  const path = join(dir, "working", "checkpoints", "motion-status-events.jsonl");
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l) as Record<string, unknown>);
}

function findFiles(root: string, suffix: string): string[] {
  const out: string[] = [];
  const walk = (d: string): void => {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name.endsWith(suffix)) out.push(p);
    }
  };
  if (existsSync(root)) walk(root);
  return out.sort();
}

// ---- cases -------------------------------------------------------------

interface Case {
  name: string;
  run: () => void | Promise<void>;
}

const CASES: Case[] = [
  {
    name: "status: one identity, RENDERED then QC_PASSED, fixture delivery blocked by name",
    run: async () => {
      const dir = stageFixture("powerpoint_graphic");
      try {
        const remo = new FakeAdapter("remotion");
        remo.writeFinalIntoJob = true;
        const dispatcher = new MotionDispatcher(createRegistry([remo]));
        const tracker = MotionStatusTracker.open(dir, loadValidatedJob(dir));
        assertEq(tracker.doc.identity.taskId, "fixture-powerpoint-graphic", "standalone task id is the job id");
        assertEq(tracker.doc.identity.taskOrigin, "own", "standalone origin");
        assertEq(tracker.doc.identity.stageSlug, "motion-fixture-powerpoint-graphic", "stage slug");
        assertEq(tracker.doc.productionStatus, null, "production status starts unset");
        assertEq(tracker.doc.phase, "CREATED", "initial phase");
        assertEq(tracker.doc.releaseStatus, null, "release axis starts unset");

        await dispatcher.renderFinal(dir, fixtureApproval("fixture-powerpoint-graphic"), {
          matrix: dispatcherMatrix(),
          tracker,
        });
        assertEq(tracker.doc.productionStatus, "RENDERED", "render receipt advances to RENDERED");
        assertEq(tracker.doc.phase, "FINAL_RENDERED", "phase after render");
        assertEq(tracker.doc.artifacts.length, 1, "one artifact recorded");
        assertEq(tracker.doc.artifacts[0].kind, "mp4", "artifact kind");

        const mp4 = tracker.doc.artifacts[0];
        await tracker.recordQcVerdict({
          verdict: "pass",
          artifactPath: mp4.path,
          artifactSha256: mp4.sha256 ?? "",
          source: "run-status",
        });
        assertEq(tracker.doc.productionStatus, "QC_PASSED", "passing QC advances to QC_PASSED");
        assertEq(tracker.doc.releaseStatus, null, "release axis untouched by production flow");

        let blocked: unknown = null;
        try {
          await tracker.deliver({
            runtime: RUNTIME,
            finalArtifact: { path: mp4.path, sha256: mp4.sha256 ?? "" },
            qc: null,
          });
        } catch (err) {
          blocked = err;
        }
        assertTrue(blocked instanceof StatusError, "fixture deliver throws StatusError");
        const missing = (blocked as StatusError).missing;
        assertTrue(missing.includes("poster"), `poster named missing: ${JSON.stringify(missing)}`);
        assertTrue(missing.includes("source_package"), "source_package named missing");
        assertTrue(missing.includes("placement_metadata"), "placement_metadata named missing");
        assertTrue(missing.includes("delivery_approval"), "delivery_approval named missing");
        assertTrue(missing.includes("production_context"), "production_context named missing");
        assertEq(tracker.doc.productionStatus, "QC_PASSED", "blocked delivery advances nothing");
        const events = readEvents(dir);
        assertTrue(
          events.some((e) => e.kind === "delivery_blocked"),
          "a delivery_blocked event is on the ledger"
        );
        assertTrue(
          events.some((e) => e.kind === "render_receipt") &&
            events.some((e) => e.kind === "review_verdict"),
          "render receipt and review verdict events are on the ledger"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "status: an insert reports under its parent task (MG-037 bridge identity)",
    run: () => {
      const dir = stageFixture("vsl_desktop");
      try {
        const tracker = MotionStatusTracker.open(dir, loadValidatedJob(dir));
        assertEq(tracker.doc.identity.taskOrigin, "parent", "insert origin");
        assertEq(tracker.doc.identity.taskId, "fixture-parent-task", "task id is the parent task id");
        assertEq(tracker.doc.identity.boardJobId, "fixture-parent-vsl", "board job is the parent job");
        assertEq(tracker.doc.identity.parentJobId, "fixture-parent-vsl", "parent job id recorded");
        assertEq(tracker.doc.identity.stageSlug, "motion-fixture-vsl-desktop", "stage rides the parent campaign");
        assertTrue(
          !existsSync(join(dir, "working", "checkpoints", "cc-board.created")),
          "no campaign marker is written for an insert"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "status: reopening preserves identity and event sequence; failure records a recovery point; transport is fail-soft",
    run: async () => {
      const dir = stageFixture("powerpoint_graphic");
      try {
        const dispatcher = new MotionDispatcher(createRegistry([new FakeAdapter("remotion")]));
        const job = loadValidatedJob(dir);
        const first = MotionStatusTracker.open(dir, job);
        const routed = await dispatcher.routeJob(dir, { matrix: dispatcherMatrix() });
        await first.recordRouting(routed.routing, routed.exportSelection);
        await first.recordFailure({ category: "MG_RENDER_FAILED", message: "synthetic render failure" });
        const eventsBefore = readEvents(dir).length;
        assertTrue(eventsBefore >= 3, "events written before reopen");
        assertEq(first.doc.recovery?.lastFailure?.category, "MG_RENDER_FAILED", "failure category recorded");

        const second = MotionStatusTracker.open(dir, job);
        assertEq(second.doc.identity.taskId, first.doc.identity.taskId, "same task identity after reopen");
        assertEq(second.doc.identity.stageSlug, first.doc.identity.stageSlug, "same stage after reopen");
        const events = readEvents(dir);
        assertTrue(events.length > eventsBefore, "event sequence continues, never restarts");
        assertTrue(
          events.some(
            (e) => e.kind === "phase_transition" && (e.detail as Record<string, unknown>)?.resumed === true
          ),
          "the reopen is recorded as a resume of the same task"
        );
        assertTrue(
          events.some((e) => e.kind === "recovery_point"),
          "a recovery point is on the ledger"
        );
        assertEq(second.doc.recovery?.lastFailure?.category, "MG_RENDER_FAILED", "resume context survives the reopen");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }

      // Fail-soft transport: a throwing board transport never
      // fails the production call.
      const dir2 = stageFixture("powerpoint_graphic");
      try {
        const dispatcher2 = new MotionDispatcher(createRegistry([new FakeAdapter("remotion")]));
        const tracker = MotionStatusTracker.open(dir2, loadValidatedJob(dir2), {
          transport: {
            sync: () => {
              throw new Error("board unreachable");
            },
          },
        });
        const routed2 = await dispatcher2.routeJob(dir2, { matrix: dispatcherMatrix() });
        await tracker.recordRouting(routed2.routing, routed2.exportSelection);
        assertEq(tracker.doc.board.lastSync?.ok, false, "transport failure recorded, not raised");
        assertTrue(
          String(tracker.doc.board.lastSync?.detail ?? "").includes("board unreachable"),
          "transport failure detail kept"
        );
      } finally {
        rmSync(dir2, { recursive: true, force: true });
      }
    },
  },
  {
    name: "status: production lifecycle reaches DELIVERED through the MG-025 delivery gate, receipt validates",
    run: async () => {
      process.env.MOTION_ISSUER_REGISTRY = join(APPROVALS_DIR, "registry.json");
      process.env.MOTION_APPROVER_KEYS = join(APPROVALS_DIR, "keyring.json");
      const dir = stageApprovalsFixture("prod-job");
      try {
        const remo = new FakeAdapter("remotion");
        remo.writeFinalIntoJob = true;
        const dispatcher = new MotionDispatcher(createRegistry([remo]));
        const tracker = MotionStatusTracker.open(dir, loadValidatedJob(dir));
        const permit = readApprovals(dir).find((a) => a.scope === "preview") as unknown as Approval;
        await dispatcher.renderFinal(dir, permit, { matrix: dispatcherMatrix(), tracker });
        assertEq(tracker.doc.productionStatus, "RENDERED", "production render advances to RENDERED");

        // Record every remaining mandatory artifact kind with a
        // real file on disk.
        const manifest = readJson(join(dir, "manifest.json"));
        const required = (manifest.delivery as Record<string, unknown>).required as string[];
        for (const kind of required) {
          if (kind === "mp4") continue;
          const rel = `renders/${kind}.txt`;
          mkdirSync(join(dir, "renders"), { recursive: true });
          writeFileSync(join(dir, rel), `mg046 ${kind} stand-in\n`, "utf8");
          await tracker.recordArtifactLocation(kind, rel, sha256File(join(dir, rel)));
        }
        const finalAbs = join(dir, "renders", "final.mp4");
        const finalSha = sha256File(finalAbs);
        await tracker.recordQcVerdict({
          verdict: "pass",
          artifactPath: "renders/final.mp4",
          artifactSha256: finalSha,
          source: "run-status-qc",
        });
        assertEq(tracker.doc.productionStatus, "QC_PASSED", "QC pass advances");

        // Delivery before the delivery approval exists: blocked
        // by name, and the gate is named too.
        let blocked: unknown = null;
        try {
          await tracker.deliver({
            runtime: RUNTIME,
            finalArtifact: { path: "renders/final.mp4", sha256: finalSha },
            qc: { artifact_path: "renders/final.mp4", artifact_sha256: finalSha, verdict: "pass" },
          });
        } catch (err) {
          blocked = err;
        }
        assertTrue(blocked instanceof StatusError, "early deliver throws StatusError");
        const missing = (blocked as StatusError).missing;
        assertTrue(missing.includes("delivery_approval"), `delivery_approval named: ${JSON.stringify(missing)}`);
        assertTrue(
          missing.some((m) => m.startsWith("delivery_gate:")),
          `the blocking gate named: ${JSON.stringify(missing)}`
        );
        assertEq(missing.length, 2, "only the approval-side names are missing");
        assertEq(tracker.doc.productionStatus, "QC_PASSED", "still QC_PASSED");

        // Add the owner delivery approval bound to the artifact
        // and the current revision, then deliver.
        const lock = computeRevisionLock(dir, RUNTIME);
        const approvals = readApprovals(dir);
        approvals.push(
          makeApproval(dir, {
            approval_id: "appr-prod-delivery",
            scope: "delivery",
            subject_revision: lock.fullRevision!,
            actor_id: "owner-t-otts",
            artifact_refs: [{ path: "renders/final.mp4", sha256: finalSha }],
          })
        );
        writeApprovals(dir, approvals);
        const receipt: DeliveryReceipt = await tracker.deliver({
          runtime: RUNTIME,
          finalArtifact: { path: "renders/final.mp4", sha256: finalSha },
          qc: { artifact_path: "renders/final.mp4", artifact_sha256: finalSha, verdict: "pass" },
        });
        assertEq(receipt.production_status, "DELIVERED", "receipt status");
        assertEq(receipt.task.task_id, "mg025-prod-job", "receipt task identity");
        assertEq(receipt.release_status, null, "release axis stays separate on the receipt");
        assertTrue(
          receipt.approvals.every((a) => a.kind === "production_approval"),
          "every receipt approval is a production approval (no code-review approvals)"
        );
        assertTrue(
          receipt.approvals.some((a) => a.gate === "delivery" && a.scope === "delivery"),
          "the delivery gate approval is on the receipt"
        );
        assertEq(tracker.doc.productionStatus, "DELIVERED", "doc reaches DELIVERED");
        assertEq(validateDeliveryReceipt(receipt).length, 0, "receipt passes the layer validator");
        const schema = readJson(RECEIPT_SCHEMA_PATH) as Record<string, unknown>;
        const ajv = new Ajv2020({ strict: false });
        const validate = ajv.compile({ ...schema, $ref: "#/$defs/delivery_receipt" });
        assertTrue(validate(receipt), `receipt validates against delivery-receipt-schema.json: ${JSON.stringify(validate.errors)}`);
        const written = readJson(join(dir, "working", "checkpoints", "delivery-receipt.json"));
        assertEq(written.job_id, "mg025-prod-job", "receipt filed in the job directory");
        const events = readEvents(dir);
        assertTrue(events.some((e) => e.kind === "delivered"), "delivered event on the ledger");
        assertTrue(
          events.some((e) => e.kind === "approval_event" && (e.detail as Record<string, unknown>)?.gate === "delivery"),
          "delivery approval event on the ledger"
        );
      } finally {
        delete process.env.MOTION_ISSUER_REGISTRY;
        delete process.env.MOTION_APPROVER_KEYS;
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "settlement B: a probe-qualified alpha job routes and renders through the qualified profile; the shipped matrix is untouched",
    run: async () => {
      const matrixBefore = sha256File(MATRIX_PATH);
      const dir = stageFixture("powerpoint_graphic");
      const scratch = mkdtempSync(join(tmpdir(), "motion-status-probe-"));
      try {
        editManifestFile(dir, (doc) => {
          (doc.delivery as Record<string, unknown>).video_profile = "prores_4444_alpha";
        });
        const toolchain = probeExportToolchain(scratch);
        assertTrue(
          toolchain.profiles["prores_4444_alpha"]?.qualified === true,
          "the live probe qualifies the ProRes alpha profile on this machine"
        );
        const remo = new FakeAdapter("remotion");
        const hyper = new FakeAdapter("hyperframes");
        const dispatcher = new MotionDispatcher(createRegistry([remo, hyper]));
        const routed = await dispatcher.routeJob(dir, { matrix: loadCapabilityMatrix(), exportToolchain: toolchain });
        assertEq(routed.routing.primaryEngine, "remotion", "alpha job routes to the manifest default engine");
        assertTrue(routed.exportSelection !== null, "an export selection is recorded");
        assertEq(routed.exportSelection!.profile.id, "prores_4444_alpha", "selection profile");
        assertEq(routed.exportSelection!.confirmedBy, "export_toolchain_probe", "qualification authority is the probe");
        assertEq(routed.exportSelection!.route.kind, "image_sequence_encode", "qualified route kind");

        const outcome = await dispatcher.renderFinal(dir, fixtureApproval("fixture-powerpoint-graphic"), {
          matrix: loadCapabilityMatrix(),
          exportToolchain: toolchain,
        });
        assertEq(outcome.evidence.kind, "final", "alpha job renders through the qualified profile");
        assertEq(remo.count("renderFinal"), 1, "the routed adapter rendered");
        assertEq(sha256File(MATRIX_PATH), matrixBefore, "the shipped capability matrix is byte-identical");
      } finally {
        rmSync(dir, { recursive: true, force: true });
        rmSync(scratch, { recursive: true, force: true });
      }
    },
  },
  {
    name: "settlement B: an alpha job no route qualifies refuses MG_CAPABILITY_UNSUPPORTED by name before authoring",
    run: async () => {
      const dir = stageFixture("powerpoint_graphic");
      try {
        editManifestFile(dir, (doc) => {
          (doc.delivery as Record<string, unknown>).video_profile = "prores_4444_alpha";
        });
        const unqualified: ExportToolchainProbe = {
          probedAt: "2026-10-15T00:00:00.000Z",
          ffmpegVersion: "ffmpeg version fixture",
          encoders: {},
          profiles: {
            prores_4444_alpha: {
              profile: "prores_4444_alpha",
              qualified: false,
              route: "image_sequence_encode",
              measuredCodec: null,
              measuredPixelFormat: null,
              distinctAlphaValues: 0,
              partialAlphaPixels: 0,
              evidence: ["fixture: no qualifying encoder measured"],
            },
          },
          hyperframesCli: null,
        };
        const remo = new FakeAdapter("remotion");
        const hyper = new FakeAdapter("hyperframes");
        const dispatcher = new MotionDispatcher(createRegistry([remo, hyper]));
        let refused: unknown = null;
        try {
          await dispatcher.routeJob(dir, { matrix: loadCapabilityMatrix(), exportToolchain: unqualified });
        } catch (err) {
          refused = err;
        }
        assertTrue(refused instanceof ExportError, `refusal is the export layer's ExportError, got ${String(refused)}`);
        assertEq((refused as ExportError).category, "MG_CAPABILITY_UNSUPPORTED", "refusal category");
        assertEq((refused as ExportError).exitClass, 3, "refusal exit class");
        assertEq((refused as ExportError).check, "export.route_qualified", "refusal check name");
        assertEq(remo.totalCalls() + hyper.totalCalls(), 0, "no adapter was called before the refusal");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "settlement B: without the probe opt-in, alpha routing keeps the matrix-only refusal",
    run: async () => {
      const dir = stageFixture("powerpoint_graphic");
      try {
        editManifestFile(dir, (doc) => {
          (doc.delivery as Record<string, unknown>).video_profile = "prores_4444_alpha";
        });
        const dispatcher = new MotionDispatcher(createRegistry([new FakeAdapter("remotion")]));
        let refused: unknown = null;
        try {
          await dispatcher.routeJob(dir, { matrix: loadCapabilityMatrix() });
        } catch (err) {
          refused = err;
        }
        assertTrue(refused instanceof AdapterError, "matrix-only refusal stays an AdapterError");
        assertEq((refused as AdapterError).category, "MG_CAPABILITY_MISSING", "matrix-only refusal category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "settlement A: cached dispatch renders once, reuses, and re-renders only the corrupted scene",
    run: async () => {
      const dir = stageTwoSceneJob("cached-fast");
      const scratch = mkdtempSync(join(tmpdir(), "motion-status-"));
      try {
        const adapter = new FakeVideoAdapter(join(scratch, "adapter-out"));
        const dispatcher = new MotionDispatcher(createRegistry([adapter]));
        const tracker = MotionStatusTracker.open(dir, loadValidatedJob(dir));
        const approval = fixtureApproval("fixture-powerpoint-graphic");
        const opts = { matrix: dispatcherMatrix(), tracker };

        const first = await dispatcher.renderFinalCached(dir, approval, opts);
        assertEq(adapter.sceneCalls.length, 2, "first pass renders both scenes");
        assertTrue(
          first.cache.results.every((r) => r.action === "rendered"),
          "first pass renders every scene"
        );
        const finalPath = join(dir, "renders", "final.mp4");
        assertTrue(existsSync(finalPath), "assembled final exists");
        assertEq(probeVideoFile(finalPath).frameCount, 24, "assembly is the two 12-frame scene artifacts");
        const finalSha = sha256File(finalPath);
        assertEq(tracker.doc.productionStatus, "RENDERED", "tracker records the cached render");
        assertEq(tracker.doc.recovery?.cacheJobKey, first.cache.jobKey, "recovery point carries the cache job key");

        const second = await dispatcher.renderFinalCached(dir, approval, opts);
        assertEq(adapter.sceneCalls.length, 2, "second pass renders nothing");
        assertTrue(
          second.cache.results.every((r) => r.action === "reused"),
          "second pass reuses every scene"
        );
        assertEq(sha256File(finalPath), finalSha, "assembled output is byte-identical on reuse");

        // Corrupt the bar-02 artifact on disk: only that scene
        // may re-render.
        const artifactFiles = findFiles(join(dir, "working", "cache", "artifacts", "bar-02"), ".mp4");
        assertEq(artifactFiles.length, 1, "one cached bar-02 artifact");
        const bytes = readFileSync(artifactFiles[0]);
        bytes[Math.floor(bytes.length / 2)] = bytes[Math.floor(bytes.length / 2)] ^ 0xff;
        writeFileSync(artifactFiles[0], bytes);
        const third = await dispatcher.renderFinalCached(dir, approval, opts);
        assertEq(adapter.sceneCalls.length, 3, "exactly one scene re-renders after corruption");
        assertEq(adapter.sceneCalls[2], "bar-02", "the corrupted scene is the one re-rendered");
        const byScene = new Map(third.cache.results.map((r) => [r.sceneId, r.action]));
        assertEq(byScene.get("bar-01"), "reused", "the intact scene is still reused");
        assertEq(byScene.get("bar-02"), "rendered", "the corrupted scene re-rendered");
        assertTrue(
          third.cache.findings.some((f) => f.category === "MG_CACHE_ARTIFACT_CORRUPT"),
          "the corruption is detected and named"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
        rmSync(scratch, { recursive: true, force: true });
      }
    },
  },
  {
    name: "settlement A: a production-path job killed mid-render resumes byte-identical through dispatch",
    run: async () => {
      const scratchRoot = join(runtimeStateDir(), "mg046-tests");
      rmSync(scratchRoot, { recursive: true, force: true });
      mkdirSync(scratchRoot, { recursive: true });
      const dir = join(scratchRoot, "two-scene-job");
      cpSync(stageTwoSceneJob("real"), dir, { recursive: true });
      const outDir = join(scratchRoot, "adapter-out");
      const configPath = join(scratchRoot, "driver-config.json");
      writeJson(configPath, { distSrc: DIST_SRC, jobDir: dir, outDir });
      const driverPath = join(FIXTURES, "status", "cached-render-driver.cjs");
      const statePath = join(dir, "working", "cache", "render-state.json");

      const spawnDriver = (): ChildProcess =>
        spawn(process.execPath, [driverPath, configPath], { stdio: ["ignore", "pipe", "pipe"] });

      const waitExit = (child: ChildProcess): Promise<{ code: number | null; stdout: string }> =>
        new Promise((resolvePromise) => {
          let stdout = "";
          child.stdout?.on("data", (d: Buffer) => {
            stdout += d.toString("utf8");
          });
          child.on("close", (code) => resolvePromise({ code, stdout }));
        });

      // First pass: kill mid-render, once bar-01 is complete and
      // bar-02 is in flight (state file and staged scene dir
      // agree, the MG-027 harness lesson).
      const first = spawnDriver();
      const deadline = Date.now() + 900_000;
      let killed = false;
      while (Date.now() < deadline) {
        if (existsSync(statePath)) {
          try {
            const state = readJson(statePath) as {
              scenes?: Record<string, { status?: string }>;
            };
            const bar01 = state.scenes?.["bar-01"]?.status;
            const bar02 = state.scenes?.["bar-02"]?.status;
            if (bar01 === "complete" && bar02 === "in_progress" && existsSync(join(dir, "working", "scene-jobs", "bar-02"))) {
              await sleep(3_000);
              first.kill("SIGKILL");
              killed = true;
              break;
            }
          } catch {
            // Torn read of the state file mid-write; keep polling.
          }
        }
        if (first.exitCode !== null) break;
        await sleep(500);
      }
      await waitExit(first);
      assertTrue(killed, "the first pass was killed while bar-02 was in flight");

      const artifacts = findFiles(join(dir, "working", "cache", "artifacts", "bar-01"), ".mp4");
      assertEq(artifacts.length, 1, "bar-01 artifact survives the kill");
      const beforeSha = sha256File(artifacts[0]);
      const beforeMtimeNs = statSync(artifacts[0], { bigint: true }).mtimeNs;

      // Resume in a fresh process through the same production
      // entry point.
      const resumed = spawnSync(process.execPath, [driverPath, configPath], {
        encoding: "utf8",
        timeout: 1_200_000,
        maxBuffer: 64 * 1024 * 1024,
      });
      assertEq(resumed.status, 0, `resume driver exits 0: ${resumed.stdout} ${resumed.stderr}`);
      const reportLine = resumed.stdout.split("\n").find((l) => l.startsWith("REPORT "));
      assertTrue(reportLine !== undefined, "resume driver prints a report");
      const report = JSON.parse(reportLine!.slice("REPORT ".length)) as {
        cache: { results: { sceneId: string; action: string }[] };
        outputPaths: string[];
      };
      const byScene = new Map(report.cache.results.map((r) => [r.sceneId, r.action]));
      assertEq(byScene.get("bar-01"), "reused", "the finished scene is reused on resume");
      assertEq(byScene.get("bar-02"), "rendered", "the interrupted scene renders on resume");
      assertEq(sha256File(artifacts[0]), beforeSha, "the finished scene artifact is byte-identical after resume");
      assertEq(
        statSync(artifacts[0], { bigint: true }).mtimeNs,
        beforeMtimeNs,
        "the finished scene artifact was not rewritten (unre-rendered)"
      );
      const finalPath = join(dir, "renders", "final.mp4");
      assertTrue(existsSync(finalPath), "the resumed job assembles its final");
      assertEq(probeVideoFile(finalPath).frameCount, 360, "the assembled final carries both scenes in full");

      mkdirSync(EVIDENCE_DIR, { recursive: true });
      writeJson(join(EVIDENCE_DIR, "record.json"), {
        item: "MG-046",
        recorded_at: new Date().toISOString(),
        settlement_a_resume: {
          killed_mid_render: true,
          bar01_artifact_sha256: beforeSha,
          bar01_reused_on_resume: true,
          assembled_final_frames: 360,
        },
      });
    },
  },
];

// ---- runner -------------------------------------------------------------

async function main(): Promise<void> {
  let passed = 0;
  const failures: string[] = [];
  for (const c of CASES) {
    try {
      await c.run();
      passed += 1;
      console.log(`PASS ${c.name}`);
    } catch (err) {
      failures.push(c.name);
      console.log(`FAIL ${c.name}\n  ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  console.log(`\nrun-status: ${passed}/${CASES.length} cases passed`);
  if (failures.length > 0) process.exit(1);
}

void main();
