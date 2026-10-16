// Adapter contract tests for the MG-004 contracts layer.
//
// The real Hyperframes and Remotion adapters are MG-005 and MG-006. MG-004
// freezes the Section 5.5 interface and tests it here against fake adapters
// that implement the interface, covering: success for every operation,
// receipts that name the engine and exact runtime, an invalid-schema job
// rejected before any adapter call, an unsupported export as an explicit
// capability error, timeout enforcement, cancellation (before start, in
// flight, and through the dispatcher), a missing engine as a
// dependency-class error, the approval gate on final render, the Section
// 3.2 routing table, explicit-choice precedence, capability-driven
// substitution for table defaults only, the legacy compatibility path, and
// the capability matrix honesty rules, including the checked-in matrix,
// which must state every engine unprobed until a real probe record exists.
//
// Fixtures root resolution matches run-corpus.ts: MOTION_FIXTURES_ROOT when
// set, otherwise ../../../tests/fixtures relative to this compiled file.
//
// Exit code 0 when every case passes, 1 otherwise.

import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  AdapterError,
  AdapterErrorCategory,
  ApprovedMotionJob,
  ArtifactEvidence,
  buildMatrixFromProbeRecords,
  CallContext,
  CapabilityMatrix,
  createRegistry,
  Engine,
  EngineCapabilityRecord,
  loadCapabilityMatrix,
  MotionDispatcher,
  MotionEvidence,
  MotionRendererAdapter,
  route,
  RoutingRequest,
  RuntimeEvidence,
  RuntimeIdentity,
  SceneRequirement,
  ValidatedMotionJob,
  ValidationEvidence,
  validateCapabilityMatrix,
} from "../src/adapters";
import type { Approval } from "../src/validation/generated-types";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

const FAKE_VERSION = "9.9.9-test";
const FAKE_LOCK = "test-lock-0001";
const PROBED_AT = "2026-10-14T00:00:00.000Z";
const SHA = "0".repeat(64);

class FakeAdapter implements MotionRendererAdapter {
  readonly engine: Engine;
  calls: string[] = [];
  cancelCalls: string[] = [];
  contexts: CallContext[] = [];
  delayMs = 0;

  constructor(engine: Engine) {
    this.engine = engine;
  }

  beginCall(ctx: CallContext): void {
    this.contexts.push(ctx);
  }

  count(op: string): number {
    return this.calls.filter((c) => c === op || c.startsWith(`${op}:`)).length;
  }

  totalCalls(): number {
    return this.calls.length;
  }

  private runtime(): RuntimeIdentity {
    return {
      engine: this.engine,
      engineVersion: FAKE_VERSION,
      runtimeLockId: FAKE_LOCK,
      nodeVersion: process.version,
      platform: "linux x64",
      probedAt: PROBED_AT,
    };
  }

  private async pause(): Promise<void> {
    if (this.delayMs > 0) {
      await new Promise((r) => setTimeout(r, this.delayMs));
    }
  }

  private artifact(
    job: ValidatedMotionJob,
    kind: ArtifactEvidence["kind"],
    name: string
  ): ArtifactEvidence {
    const now = new Date().toISOString();
    return {
      engine: this.engine,
      runtime: this.runtime(),
      jobId: job.jobId,
      kind,
      artifacts: [{ path: `renders/${name}`, sha256: SHA }],
      outputPaths: [`renders/${name}`],
      exitCode: 0,
      stderrLog: null,
      startedAt: now,
      finishedAt: now,
      durationMs: 1,
    };
  }

  async probeRuntime(): Promise<RuntimeEvidence> {
    this.calls.push("probeRuntime");
    await this.pause();
    return {
      engine: this.engine,
      runtime: this.runtime(),
      status: "ready",
      capabilities: null,
      checkedAt: new Date().toISOString(),
      detail: "fake adapter probe",
    };
  }

  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    this.calls.push("validate");
    await this.pause();
    return {
      engine: this.engine,
      runtime: this.runtime(),
      jobId: job.jobId,
      valid: true,
      findings: [],
      firstErrorCategory: null,
      checkedAt: new Date().toISOString(),
    };
  }

  async renderStill(job: ValidatedMotionJob, frame: number): Promise<ArtifactEvidence> {
    this.calls.push(`renderStill:${frame}`);
    await this.pause();
    return this.artifact(job, "still", `still-${frame}.png`);
  }

  async renderPreview(job: ValidatedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderPreview");
    await this.pause();
    return this.artifact(job, "preview", "preview.mp4");
  }

  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderFinal");
    await this.pause();
    return this.artifact(job, "final", "final.mp4");
  }

  async inspectMotion(
    job: ValidatedMotionJob,
    range: { startFrame: number; endFrameExclusive: number }
  ): Promise<MotionEvidence> {
    this.calls.push("inspectMotion");
    await this.pause();
    return {
      engine: this.engine,
      runtime: this.runtime(),
      jobId: job.jobId,
      range,
      assertionsChecked: 2,
      assertionsPassed: 2,
      observations: [`inspected frames ${range.startFrame}..${range.endFrameExclusive - 1}`],
      inspectedAt: new Date().toISOString(),
    };
  }

  async cancel(jobId: string): Promise<void> {
    this.cancelCalls.push(jobId);
  }
}

function readyRecord(
  engine: Engine,
  overrides?: Partial<EngineCapabilityRecord>
): EngineCapabilityRecord {
  return {
    engine,
    probeStatus: "ready",
    installedVersion: FAKE_VERSION,
    runtimeLockId: FAKE_LOCK,
    probedAt: PROBED_AT,
    platform: "linux x64",
    codecs: ["h264", "prores", "vp9"],
    transparency: { alphaVideo: true, profiles: ["prores_4444_alpha", "vp9_alpha"] },
    mediaTypes: ["image", "video", "audio", "svg", "font"],
    features3d: ["webgl-depth"],
    evidence: ["synthetic test record, not a real probe"],
    ...overrides,
  };
}

function matrixOf(records: EngineCapabilityRecord[]): CapabilityMatrix {
  return {
    schemaVersion: "1.0",
    generatedAt: PROBED_AT,
    source: "adapter contract tests",
    engines: records,
  };
}

function fullMatrix(): CapabilityMatrix {
  return matrixOf([readyRecord("hyperframes"), readyRecord("remotion"), readyRecord("legacy")]);
}

function noAlphaMatrix(): CapabilityMatrix {
  const noAlpha: Partial<EngineCapabilityRecord> = {
    codecs: ["h264"],
    transparency: { alphaVideo: false, profiles: [] },
  };
  return matrixOf([
    readyRecord("hyperframes", noAlpha),
    readyRecord("remotion", noAlpha),
    readyRecord("legacy", noAlpha),
  ]);
}

function approval(decision: Approval["decision"], scope: Approval["scope"]): Approval {
  return {
    schema_version: "2.0",
    approval_id: "test-approval",
    job_id: "fixture-powerpoint-graphic",
    company_id: "fixture-company",
    scope,
    decision,
    subject_revision: "test-revision",
    artifact_refs: [],
    actor_id: "test-actor",
    source_event_ref: null,
    authority_status: "verified",
  };
}

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

async function expectAdapterError(
  promise: Promise<unknown>,
  category: AdapterErrorCategory,
  exitClass: number
): Promise<AdapterError> {
  try {
    await promise;
  } catch (err) {
    assertTrue(err instanceof AdapterError, `expected AdapterError, got ${String(err)}`);
    const e = err as AdapterError;
    assertEq(e.category, category, "error category");
    assertEq(e.exitClass, exitClass, "error exit class");
    return e;
  }
  throw new Error(`expected AdapterError ${category}, but the operation succeeded`);
}

function assertReceipt(
  evidence: { engine: Engine; runtime: RuntimeIdentity },
  engine: Engine
): void {
  assertEq(evidence.engine, engine, "receipt engine");
  assertEq(evidence.runtime.engine, engine, "receipt runtime engine");
  assertEq(evidence.runtime.engineVersion, FAKE_VERSION, "receipt names the exact runtime version");
  assertEq(evidence.runtime.runtimeLockId, FAKE_LOCK, "receipt names the runtime lock");
}

function stageFixture(mode: string, mutate?: (manifestPath: string) => void): string {
  const staging = mkdtempSync(join(tmpdir(), "motion-adapters-"));
  const dir = join(staging, mode);
  cpSync(join(fixturesRoot(), "modes", mode), dir, { recursive: true });
  if (mutate) mutate(join(dir, "manifest.json"));
  return dir;
}

function editManifestFile(path: string, fn: (m: Record<string, unknown>) => void): void {
  const doc = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  fn(doc);
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

const CASES: TestCase[] = [
  {
    name: "success: probe, validate, still, preview, final, inspect all return receipts naming engine and exact runtime",
    run: async () => {
      const hyper = new FakeAdapter("hyperframes");
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([hyper, remo]));
      const matrix = fullMatrix();
      const dir = stageFixture("powerpoint_graphic");
      try {
        const probe = await dispatcher.probe("hyperframes", { matrix });
        assertEq(probe.status, "ready", "probe status");
        assertReceipt(probe, "hyperframes");

        const validated = await dispatcher.validate(dir, { matrix });
        assertTrue(validated.evidence.valid, "adapter validate reports valid");
        assertReceipt(validated.evidence, "remotion");
        assertEq(validated.routing.primaryEngine, "remotion", "chart job routes to remotion");

        const still = await dispatcher.renderStill(dir, 45, { matrix });
        assertEq(still.evidence.kind, "still", "still kind");
        assertReceipt(still.evidence, "remotion");
        assertEq(still.evidence.artifacts[0].path, "renders/still-45.png", "still output path");

        const preview = await dispatcher.renderPreview(dir, { matrix });
        assertEq(preview.evidence.kind, "preview", "preview kind");
        assertReceipt(preview.evidence, "remotion");

        const final = await dispatcher.renderFinal(dir, approval("approved", "delivery"), {
          matrix,
        });
        assertEq(final.evidence.kind, "final", "final kind");
        assertReceipt(final.evidence, "remotion");

        const motion = await dispatcher.inspectMotion(
          dir,
          { startFrame: 0, endFrameExclusive: 90 },
          { matrix }
        );
        assertEq(motion.evidence.assertionsPassed, 2, "motion assertions passed");
        assertReceipt(motion.evidence, "remotion");

        assertEq(remo.count("renderStill"), 1, "remotion renderStill calls");
        assertEq(remo.count("renderFinal"), 1, "remotion renderFinal calls");
        assertEq(hyper.totalCalls(), 1, "hyperframes only probed");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "invalid schema job is rejected before any adapter call",
    run: async () => {
      const hyper = new FakeAdapter("hyperframes");
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([hyper, remo]));
      const dir = stageFixture("powerpoint_graphic", (p) =>
        editManifestFile(p, (m) => {
          m["unexpected_extra_key"] = true;
        })
      );
      try {
        const err = await expectAdapterError(
          dispatcher.renderPreview(dir, { matrix: fullMatrix() }),
          "MG_SCHEMA_INVALID",
          2
        );
        assertTrue(err.findings.length > 0, "error carries the contracts findings");
        assertEq(hyper.totalCalls(), 0, "hyperframes adapter calls");
        assertEq(remo.totalCalls(), 0, "remotion adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "unsupported export (alpha profile, no engine confirms alpha) is an explicit capability error",
    run: async () => {
      const hyper = new FakeAdapter("hyperframes");
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([hyper, remo]));
      const dir = stageFixture("powerpoint_graphic", (p) =>
        editManifestFile(p, (m) => {
          (m.delivery as Record<string, unknown>).video_profile = "prores_4444_alpha";
        })
      );
      try {
        await expectAdapterError(
          dispatcher.renderPreview(dir, { matrix: noAlphaMatrix() }),
          "MG_CAPABILITY_MISSING",
          3
        );
        assertEq(hyper.totalCalls(), 0, "hyperframes adapter calls");
        assertEq(remo.totalCalls(), 0, "remotion adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "missing engine is a dependency-class error",
    run: async () => {
      const hyper = new FakeAdapter("hyperframes");
      const dispatcher = new MotionDispatcher(createRegistry([hyper]));
      const dir = stageFixture("powerpoint_graphic");
      try {
        const err = await expectAdapterError(
          dispatcher.renderPreview(dir, { matrix: fullMatrix() }),
          "MG_ENGINE_MISSING",
          3
        );
        assertEq(err.engine, "remotion", "missing engine named");
        assertEq(hyper.totalCalls(), 0, "hyperframes adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "timeout is enforced and the adapter is cancelled",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      remo.delayMs = 500;
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      try {
        await expectAdapterError(
          dispatcher.renderPreview(dir, { matrix: fullMatrix(), timeoutMs: 60 }),
          "MG_TIMEOUT",
          5
        );
        assertTrue(
          remo.cancelCalls.includes("fixture-powerpoint-graphic"),
          "adapter cancel invoked on timeout"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "cancellation in flight is honored and the adapter is cancelled",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      remo.delayMs = 500;
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      const controller = new AbortController();
      try {
        const pending = dispatcher.renderPreview(dir, {
          matrix: fullMatrix(),
          signal: controller.signal,
        });
        setTimeout(() => controller.abort(), 40);
        await expectAdapterError(pending, "MG_CANCELLED", 8);
        assertTrue(
          remo.cancelCalls.includes("fixture-powerpoint-graphic"),
          "adapter cancel invoked on abort"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "cancellation before start reaches no adapter",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      const controller = new AbortController();
      controller.abort();
      try {
        await expectAdapterError(
          dispatcher.renderPreview(dir, { matrix: fullMatrix(), signal: controller.signal }),
          "MG_CANCELLED",
          8
        );
        assertEq(remo.totalCalls(), 0, "remotion adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "dispatcher.cancel aborts an in-flight operation",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      remo.delayMs = 500;
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      try {
        const pending = dispatcher.renderPreview(dir, { matrix: fullMatrix() });
        await new Promise((r) => setTimeout(r, 40));
        await dispatcher.cancel("fixture-powerpoint-graphic");
        await expectAdapterError(pending, "MG_CANCELLED", 8);
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "final render without an approved delivery approval is refused before any adapter call",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      try {
        await expectAdapterError(
          dispatcher.renderFinal(dir, approval("pending", "delivery"), { matrix: fullMatrix() }),
          "MG_APPROVAL_REQUIRED",
          4
        );
        await expectAdapterError(
          dispatcher.renderFinal(dir, approval("approved", "preview"), { matrix: fullMatrix() }),
          "MG_APPROVAL_REQUIRED",
          4
        );
        assertEq(remo.count("renderFinal"), 0, "renderFinal adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "out-of-range still frame and inspection range are timeline errors",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stageFixture("powerpoint_graphic");
      try {
        await expectAdapterError(
          dispatcher.renderStill(dir, 180, { matrix: fullMatrix() }),
          "MG_TIMELINE_INVALID",
          2
        );
        await expectAdapterError(
          dispatcher.inspectMotion(dir, { startFrame: 90, endFrameExclusive: 90 }, { matrix: fullMatrix() }),
          "MG_TIMELINE_INVALID",
          2
        );
        assertEq(remo.totalCalls(), 0, "remotion adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "routing table: defaults per scene requirement",
    run: () => {
      const matrix = fullMatrix();
      const base: RoutingRequest = { scenes: [], allowLegacyFallback: false };
      const editorial = route({ ...base, scenes: [{ sceneId: "s", kind: "editorial_image" }] }, matrix);
      assertTrue(editorial.kind === "routed", "editorial routed");
      if (editorial.kind === "routed") {
        assertEq(editorial.assignments[0].engine, "hyperframes", "editorial default");
        assertEq(editorial.assignments[0].reasonCode, "table_default", "editorial reason");
      }
      const chart = route({ ...base, scenes: [{ sceneId: "s", kind: "data_chart" }] }, matrix);
      assertTrue(chart.kind === "routed", "chart routed");
      if (chart.kind === "routed") {
        assertEq(chart.assignments[0].engine, "remotion", "chart default");
      }
      const variants = route({ ...base, scenes: [{ sceneId: "s", kind: "data_variants" }] }, matrix);
      assertTrue(variants.kind === "routed", "variants routed");
      if (variants.kind === "routed") {
        assertEq(variants.assignments[0].engine, "remotion", "data variants default");
      }
      const ui = route({ ...base, scenes: [{ sceneId: "s", kind: "product_ui" }] }, matrix);
      assertTrue(ui.kind === "routed", "product ui routed");
      if (ui.kind === "routed") {
        assertEq(ui.assignments[0].engine, "hyperframes", "product ui default");
      }
    },
  },
  {
    name: "routing: explicit choices win over defaults and are never silently overridden",
    run: () => {
      const matrix = fullMatrix();
      const jobChoice = route(
        {
          scenes: [{ sceneId: "s", kind: "editorial_image" }],
          explicitEngine: "remotion",
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(jobChoice.kind === "routed", "job choice routed");
      if (jobChoice.kind === "routed") {
        assertEq(jobChoice.assignments[0].engine, "remotion", "explicit remotion honored for editorial");
        assertEq(jobChoice.assignments[0].reasonCode, "explicit_job", "job choice reason");
      }
      const sceneChoice = route(
        {
          scenes: [{ sceneId: "s", kind: "data_chart", explicitEngine: "hyperframes" }],
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(sceneChoice.kind === "routed", "scene choice routed");
      if (sceneChoice.kind === "routed") {
        assertEq(sceneChoice.assignments[0].engine, "hyperframes", "explicit hyperframes honored for chart");
        assertEq(sceneChoice.assignments[0].reasonCode, "explicit_scene", "scene choice reason");
      }
      // Explicit engine that cannot confirm a required capability: error,
      // even though the other engine could confirm it.
      const incompatible = route(
        {
          scenes: [
            { sceneId: "s", kind: "data_chart", explicitEngine: "remotion", requiresAlpha: true },
          ],
          allowLegacyFallback: false,
        },
        noAlphaMatrix()
      );
      assertTrue(incompatible.kind === "error", "incompatible explicit choice errors");
      if (incompatible.kind === "error") {
        assertEq(incompatible.error.category, "MG_CAPABILITY_MISSING", "capability category");
        assertEq(incompatible.error.exitClass, 3, "capability exit class");
      }
      // No-alpha matrix with only remotion lacking alpha: build directly.
      const oneSided = matrixOf([
        readyRecord("hyperframes"),
        readyRecord("remotion", {
          codecs: ["h264"],
          transparency: { alphaVideo: false, profiles: [] },
        }),
        readyRecord("legacy"),
      ]);
      const stillError = route(
        {
          scenes: [
            { sceneId: "s", kind: "data_chart", explicitEngine: "remotion", requiresAlpha: true },
          ],
          allowLegacyFallback: false,
        },
        oneSided
      );
      assertTrue(stillError.kind === "error", "explicit choice is not overridden by a capable alternative");
    },
  },
  {
    name: "routing: preservation rows and manifest default precedence",
    run: () => {
      const matrix = fullMatrix();
      const react = route(
        {
          scenes: [{ sceneId: "s", kind: "existing_react_scene" }],
          manifestDefaultEngine: "hyperframes",
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(react.kind === "routed", "react scene routed");
      if (react.kind === "routed") {
        assertEq(react.assignments[0].engine, "remotion", "existing React scene stays remotion");
      }
      const hfComp = route(
        {
          scenes: [{ sceneId: "s", kind: "existing_hyperframes_composition" }],
          manifestDefaultEngine: "remotion",
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(hfComp.kind === "routed", "hyperframes composition routed");
      if (hfComp.kind === "routed") {
        assertEq(hfComp.assignments[0].engine, "hyperframes", "existing composition stays hyperframes");
      }
      const manifestDefault = route(
        {
          scenes: [{ sceneId: "s", kind: "data_chart" }],
          manifestDefaultEngine: "hyperframes",
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(manifestDefault.kind === "routed", "manifest default routed");
      if (manifestDefault.kind === "routed") {
        assertEq(manifestDefault.assignments[0].engine, "hyperframes", "manifest default beats table default");
        assertEq(manifestDefault.assignments[0].reasonCode, "manifest_default", "manifest reason");
      }
    },
  },
  {
    name: "routing: table default yields only to a fully confirming engine, with the substitution recorded",
    run: () => {
      const matrix = matrixOf([
        readyRecord("hyperframes", {
          codecs: ["h264"],
          transparency: { alphaVideo: false, profiles: [] },
        }),
        readyRecord("remotion"),
        readyRecord("legacy"),
      ]);
      const result = route(
        {
          scenes: [{ sceneId: "s", kind: "editorial_image", requiresAlpha: true }],
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(result.kind === "routed", "capability substitution routed");
      if (result.kind === "routed") {
        assertEq(result.assignments[0].engine, "remotion", "confirming engine takes the scene");
        assertEq(result.assignments[0].reasonCode, "capability_confirmed", "substitution reason");
      }
    },
  },
  {
    name: "routing: 3D scenes route by qualified feature support, with evidence in the reason",
    run: () => {
      const matrix = matrixOf([
        readyRecord("hyperframes"),
        readyRecord("remotion", { features3d: [] }),
        readyRecord("legacy"),
      ]);
      const result = route(
        {
          scenes: [{ sceneId: "s", kind: "three_dimensional", requires3dFeature: "webgl-depth" }],
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(result.kind === "routed", "3D routed");
      if (result.kind === "routed") {
        assertEq(result.assignments[0].engine, "hyperframes", "qualifying engine takes the 3D scene");
        assertTrue(
          result.assignments[0].reason.includes("webgl-depth"),
          "reason records the feature evidence"
        );
      }
      const none = route(
        {
          scenes: [{ sceneId: "s", kind: "three_dimensional", requires3dFeature: "webgl-depth" }],
          allowLegacyFallback: false,
        },
        matrixOf([
          readyRecord("hyperframes", { features3d: [] }),
          readyRecord("remotion", { features3d: [] }),
          readyRecord("legacy"),
        ])
      );
      assertTrue(none.kind === "error", "unqualified 3D scene errors");
      if (none.kind === "error") {
        assertEq(none.error.category, "MG_CAPABILITY_MISSING", "3D capability category");
      }
    },
  },
  {
    name: "routing: mixed program keeps per-scene engines and one assembly owner",
    run: () => {
      const result = route(
        {
          scenes: [
            { sceneId: "a", kind: "editorial_image" },
            { sceneId: "b", kind: "data_chart" },
          ],
          allowLegacyFallback: false,
        },
        fullMatrix()
      );
      assertTrue(result.kind === "routed", "mixed program routed");
      if (result.kind === "routed") {
        assertEq(result.assignments.length, 2, "assignment count");
        assertEq(result.assignments[0].engine, "hyperframes", "first scene engine");
        assertEq(result.assignments[1].engine, "remotion", "second scene engine");
        assertEq(result.assemblyOwner, result.primaryEngine, "single assembly owner");
        assertEq(result.assemblyOwner, "hyperframes", "assembly owner is the primary engine");
      }
    },
  },
  {
    name: "routing: legacy requires the declared compatibility path and an explicit choice",
    run: () => {
      const denied = route(
        {
          scenes: [{ sceneId: "s", kind: "generic", explicitEngine: "legacy" }],
          allowLegacyFallback: false,
        },
        fullMatrix()
      );
      assertTrue(denied.kind === "error", "legacy without the declared path errors");
      if (denied.kind === "error") {
        assertEq(denied.error.category, "MG_CAPABILITY_MISSING", "legacy denial category");
        assertEq(denied.error.exitClass, 3, "legacy denial exit class");
      }
      const allowed = route(
        {
          scenes: [{ sceneId: "s", kind: "generic", explicitEngine: "legacy" }],
          allowLegacyFallback: true,
        },
        fullMatrix()
      );
      assertTrue(allowed.kind === "routed", "legacy through the declared path routes");
      if (allowed.kind === "routed") {
        assertEq(allowed.assignments[0].engine, "legacy", "legacy engine");
        assertEq(
          allowed.assignments[0].reasonCode,
          "legacy_compatibility_path",
          "legacy reason"
        );
      }
      const neverDefault = route(
        { scenes: [{ sceneId: "s", kind: "generic" }], allowLegacyFallback: true },
        fullMatrix()
      );
      assertTrue(neverDefault.kind === "routed", "generic scene routed");
      if (neverDefault.kind === "routed") {
        assertTrue(
          neverDefault.assignments[0].engine !== "legacy",
          "routing never produces legacy on its own"
        );
      }
    },
  },
  {
    name: "capability matrix: honesty rules and refresh from probe records",
    run: () => {
      // A record claiming ready without measured fields is rejected.
      const doctored = {
        schemaVersion: "1.0",
        generatedAt: null,
        source: "doctored",
        engines: [
          {
            engine: "hyperframes",
            probeStatus: "ready",
            installedVersion: null,
            runtimeLockId: null,
            probedAt: null,
            platform: null,
            codecs: [],
            transparency: { alphaVideo: false, profiles: [] },
            mediaTypes: [],
            features3d: [],
            evidence: [],
          },
        ],
      };
      const problems = validateCapabilityMatrix(doctored);
      assertTrue(problems.length > 0, "doctored ready record is rejected");

      // Refresh from a successful probe record produces a ready record;
      // a probe without a launch records unavailable; untouched engines
      // stay unprobed.
      const refreshed = buildMatrixFromProbeRecords([
        {
          engine: "remotion",
          version: "4.0.535",
          runtimeLockId: "runtime-lock.json#test",
          probedAt: PROBED_AT,
          platform: "linux x64",
          launchSucceeded: true,
          codecs: ["h264"],
          transparency: { alphaVideo: false, profiles: [] },
          mediaTypes: ["image", "font"],
          features3d: [],
          evidence: ["probe render succeeded in test"],
        },
        {
          engine: "hyperframes",
          version: "0.8.155",
          runtimeLockId: "runtime-lock.json#test",
          probedAt: PROBED_AT,
          platform: "linux x64",
          launchSucceeded: false,
          codecs: [],
          transparency: { alphaVideo: false, profiles: [] },
          mediaTypes: [],
          features3d: [],
          evidence: ["probe ran, launch failed in test"],
        },
      ]);
      const remo = refreshed.engines.find((r) => r.engine === "remotion");
      const hyper = refreshed.engines.find((r) => r.engine === "hyperframes");
      const legacy = refreshed.engines.find((r) => r.engine === "legacy");
      assertEq(remo?.probeStatus, "ready", "successful probe records ready");
      assertEq(remo?.installedVersion, "4.0.535", "measured version recorded");
      assertEq(hyper?.probeStatus, "unavailable", "failed launch records unavailable");
      assertEq(legacy?.probeStatus, "unprobed", "unprobed engine untouched");
      assertEq(validateCapabilityMatrix(refreshed).length, 0, "refreshed matrix is valid");
    },
  },
  {
    // Refreshed at MG-003 integration (2026-10-14) from the shared runtime
    // probe record lock-314fc289b233ca9e, which the coordinator re-ran and
    // inspected. The honest state is now: both production engines ready
    // with measured versions and cited evidence, legacy unprobed, and no
    // capability claimed beyond what the probe measured (the probe
    // rendered one Remotion PNG still and ran the Hyperframes doctor
    // check; it measured no video codec, no transparency, no 3D).
    name: "capability matrix: the checked-in matrix honestly states the MG-003 probe evidence",
    run: () => {
      const matrix = loadCapabilityMatrix();
      assertTrue(matrix.generatedAt !== null, "checked-in matrix was refreshed from probe records");
      for (const record of matrix.engines) {
        assertEq(record.codecs.length, 0, `${record.engine} confirmed codecs (none measured)`);
        assertEq(record.features3d.length, 0, `${record.engine} confirmed 3D features (none measured)`);
        assertEq(record.transparency.alphaVideo, false, `${record.engine} alpha (not measured)`);
        if (record.engine === "legacy") {
          assertEq(record.probeStatus, "unprobed", "legacy probe status");
          assertEq(record.installedVersion, null, "legacy version");
        } else {
          assertEq(record.probeStatus, "ready", `${record.engine} probe status`);
          assertEq(
            record.runtimeLockId,
            "lock-314fc289b233ca9e",
            `${record.engine} runtime lock identity`
          );
          assertTrue(record.evidence.length > 0, `${record.engine} carries probe evidence`);
        }
      }
      const remotion = matrix.engines.find((r) => r.engine === "remotion");
      assertEq(remotion?.installedVersion, "4.0.535", "remotion measured version");
      assertTrue(
        remotion?.mediaTypes.includes("image/png") ?? false,
        "remotion measured media type is the rendered PNG still"
      );
      const hyperframes = matrix.engines.find((r) => r.engine === "hyperframes");
      assertEq(hyperframes?.installedVersion, "0.8.155", "hyperframes measured version");
      assertEq(
        hyperframes?.mediaTypes.length,
        0,
        "hyperframes measured no media type (doctor check only, no render)"
      );
      // Baseline routing works against the refreshed matrix: a plain chart
      // scene routes, while an alpha requirement still fails explicitly
      // because no ready record confirms alpha.
      const baseline = route(
        { scenes: [{ sceneId: "s", kind: "data_chart" }], allowLegacyFallback: false },
        matrix
      );
      assertTrue(baseline.kind === "routed", "baseline routing works with the refreshed matrix");
      const alpha = route(
        {
          scenes: [{ sceneId: "s", kind: "data_chart", requiresAlpha: true }],
          allowLegacyFallback: false,
        },
        matrix
      );
      assertTrue(alpha.kind === "error", "alpha without a confirming record fails explicitly");
      const sceneReq: SceneRequirement = { sceneId: "s", kind: "data_chart" };
      assertEq(sceneReq.kind, "data_chart", "scene requirement shape");
    },
  },
];

async function main(): Promise<number> {
  let passed = 0;
  let failed = 0;
  for (const c of CASES) {
    try {
      await c.run();
      passed += 1;
      console.log(`PASS ${c.name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${c.name}`);
      console.log(`  ${(err as Error).message}`);
    }
  }
  const total = passed + failed;
  console.log(`Adapters: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
