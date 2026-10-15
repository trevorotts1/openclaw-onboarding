// Approval gate tests for MG-025: revisions, issuer trust, the three
// gates, the dispatcher binding, the catalog consult wiring, and the
// narration record flow.
//
// Fixtures live in tests/fixtures/approvals/: a production job and a
// fixture job whose approvals were signed with the labeled test keys
// in that directory's keyring.json (test fixtures, not production
// credentials), plus a narration job. Golden revisions are pinned in
// tests/evidence/mg025/measurements.json, a static record this runner
// asserts and never rewrites. Mutation cases stage copies in a temp
// directory so the committed fixtures stay pristine.
//
// Exit code 0 when every case passes, 1 otherwise.

import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  AdapterError,
  ApprovedMotionJob,
  ArtifactEvidence,
  CallContext,
  CapabilityMatrix,
  createRegistry,
  Engine,
  MotionDispatcher,
  MotionEvidence,
  MotionRendererAdapter,
  RuntimeEvidence,
  RuntimeIdentity,
  ValidatedMotionJob,
  ValidationEvidence,
} from "../src/adapters";
import { CatalogError } from "../src/catalog/errors";
import type { Approval } from "../src/validation/generated-types";
import {
  assertDeliveryPromotable,
  buildApprovedJob,
  computeRevisionLock,
  diffComponents,
  evaluateDeliveryGate,
  evaluateDesignGate,
  evaluateRenderGate,
  GateError,
  loadNarrationRecord,
  loadIssuerTrust,
  projectToVoiceoverTexts,
  signApprovalEvent,
  toNarrationSegments,
  writeRevisionLock,
  type GateRuntimeIdentity,
  type IssuerTrust,
} from "../src/orchestrator";
import { compileTimeline } from "../src/timeline";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function skillRoot(): string {
  return resolve(__dirname, "..", "..", "..");
}

const APPROVALS = () => join(fixturesRoot(), "approvals");
const RUNTIME: GateRuntimeIdentity = {
  engine: "remotion",
  engineVersion: "4.0.535",
  runtimeLockId: "lock-mg025-test",
};
const SHA = "0".repeat(64);

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function keyring(): Record<string, string> {
  return JSON.parse(readFileSync(join(APPROVALS(), "keyring.json"), "utf8")) as Record<string, string>;
}

function fixtureTrust(): IssuerTrust {
  const raw = JSON.parse(readFileSync(join(APPROVALS(), "registry.json"), "utf8")) as Array<{
    actor_id: string;
    role: "owner" | "authorized_reviewer" | "test";
    policies: string[];
  }>;
  return {
    registry: raw.map((e) => ({ actorId: e.actor_id, role: e.role, policies: e.policies })),
    keyring: keyring(),
    registrySource: "mg025 test registry",
    keyringSource: "mg025 test keyring",
  };
}

function measurements(): Record<string, any> {
  return JSON.parse(
    readFileSync(join(skillRoot(), "tests", "evidence", "mg025", "measurements.json"), "utf8")
  ) as Record<string, any>;
}

function stage(name: string): string {
  const staging = mkdtempSync(join(tmpdir(), "motion-approvals-"));
  const dir = join(staging, name);
  cpSync(join(APPROVALS(), name), dir, { recursive: true });
  return dir;
}

function editJson(path: string, fn: (doc: Record<string, any>) => void): void {
  const doc = JSON.parse(readFileSync(path, "utf8")) as Record<string, any>;
  fn(doc);
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}

function readApprovals(dir: string): Approval[] {
  return JSON.parse(readFileSync(join(dir, "approvals.json"), "utf8")) as Approval[];
}

function writeApprovals(dir: string, approvals: Approval[]): void {
  writeFileSync(join(dir, "approvals.json"), JSON.stringify(approvals, null, 2) + "\n", "utf8");
}

/** Sign an approval the way the trusted workflow does at import time:
 * write the detached event artifact, then bind its hash in the
 * approval's artifact_refs. Returns the approval record. */
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
  writeFileSync(join(dir, eventRel), JSON.stringify(event, null, 2) + "\n", "utf8");
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

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertSetEq(actual: string[], expected: string[], message: string): void {
  const a = [...actual].sort();
  const e = [...expected].sort();
  if (JSON.stringify(a) !== JSON.stringify(e)) {
    throw new Error(`${message}: expected ${JSON.stringify(e)}, got ${JSON.stringify(a)}`);
  }
}

class FakeAdapter implements MotionRendererAdapter {
  readonly engine: Engine;
  calls: string[] = [];
  constructor(engine: Engine) {
    this.engine = engine;
  }
  count(op: string): number {
    return this.calls.filter((c) => c === op).length;
  }
  totalCalls(): number {
    return this.calls.length;
  }
  private runtime(): RuntimeIdentity {
    return {
      engine: this.engine,
      engineVersion: "4.0.535",
      runtimeLockId: "lock-mg025-test",
      nodeVersion: process.version,
      platform: "linux x64",
      probedAt: "2026-10-14T00:00:00.000Z",
    };
  }
  private artifact(job: ValidatedMotionJob, kind: ArtifactEvidence["kind"], name: string): ArtifactEvidence {
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
    return { engine: this.engine, runtime: this.runtime(), status: "ready", capabilities: null, checkedAt: new Date().toISOString(), detail: "fake" };
  }
  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    this.calls.push("validate");
    return { engine: this.engine, runtime: this.runtime(), jobId: job.jobId, valid: true, findings: [], firstErrorCategory: null, checkedAt: new Date().toISOString() };
  }
  async renderStill(job: ValidatedMotionJob, frame: number): Promise<ArtifactEvidence> {
    this.calls.push("renderStill");
    return this.artifact(job, "still", `still-${frame}.png`);
  }
  async renderPreview(job: ValidatedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderPreview");
    return this.artifact(job, "preview", "preview.mp4");
  }
  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    this.calls.push("renderFinal");
    return this.artifact(job, "final", "final.mp4");
  }
  async inspectMotion(job: ValidatedMotionJob, range: { startFrame: number; endFrameExclusive: number }): Promise<MotionEvidence> {
    this.calls.push("inspectMotion");
    return { engine: this.engine, runtime: this.runtime(), jobId: job.jobId, range, assertionsChecked: 0, assertionsPassed: 0, observations: [], inspectedAt: new Date().toISOString() };
  }
  async cancel(_jobId: string): Promise<void> {
    this.calls.push("cancel");
  }
  beginCall(_ctx: CallContext): void {}
}

function dispatcherMatrix(): CapabilityMatrix {
  const record = (engine: Engine, probeStatus: "ready" | "unprobed") => ({
    engine,
    probeStatus,
    installedVersion: probeStatus === "ready" ? "4.0.535" : null,
    runtimeLockId: probeStatus === "ready" ? "lock-mg025-test" : null,
    probedAt: "2026-10-14T00:00:00.000Z",
    platform: "linux x64",
    codecs: ["h264"],
    transparency: { alphaVideo: false, profiles: [] as string[] },
    mediaTypes: ["image", "font"],
    features3d: [] as string[],
    evidence: ["mg025 test record"],
  });
  return {
    schemaVersion: "1.0",
    generatedAt: "2026-10-14T00:00:00.000Z",
    source: "mg025 approvals tests",
    engines: [record("remotion", "ready"), record("hyperframes", "ready"), record("legacy", "unprobed")],
  };
}

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

const CASES: TestCase[] = [
  {
    name: "golden revisions: the three fixture jobs fingerprint to the pinned evidence values",
    run: () => {
      const m = measurements();
      const prod = computeRevisionLock(join(APPROVALS(), "prod-job"), RUNTIME);
      assertEq(prod.designRevision, m.prod_job.design_revision, "prod design revision");
      assertEq(prod.fullRevision, m.prod_job.full_revision, "prod full revision");
      for (const [name, digest] of Object.entries(m.prod_job.components as Record<string, string>)) {
        assertEq(prod.components[name as keyof typeof prod.components].digest, digest, `prod component ${name}`);
      }
      assertEq(prod.problems.length, 0, "prod revision problems");
      const fixture = computeRevisionLock(join(APPROVALS(), "fixture-job"), RUNTIME);
      assertEq(fixture.designRevision, m.fixture_job.design_revision, "fixture design revision");
      assertEq(fixture.fullRevision, m.fixture_job.full_revision, "fixture full revision");
      const narration = computeRevisionLock(join(APPROVALS(), "narration-job"), RUNTIME);
      assertEq(narration.fullRevision, m.narration_job.full_revision, "narration full revision");
      assertEq(
        narration.components.narration.digest,
        m.narration_job.narration_component,
        "narration component digest (present record differs from the absent marker)"
      );
      assertTrue(
        prod.components.narration.digest !== narration.components.narration.digest,
        "absent narration and present narration hash differently"
      );
    },
  },
  {
    name: "design and render gates pass on the production fixture with trusted issuers",
    run: () => {
      const dir = join(APPROVALS(), "prod-job");
      const trust = fixtureTrust();
      const design = evaluateDesignGate(dir, { trust });
      assertEq(design.verdict, "pass", "design verdict");
      assertEq(design.phase, "DESIGN_APPROVED", "design phase");
      assertEq(design.approvalId, "appr-prod-design", "design approval id");
      const render = evaluateRenderGate(dir, RUNTIME, { trust });
      assertEq(render.verdict, "pass", "render verdict");
      assertEq(render.phase, "PREVIEW_APPROVED", "render phase");
      assertEq(render.approvalId, "appr-prod-preview", "render permit id");
      assertEq(render.authorityBasis, "registry:authorized_reviewer+signed_event", "render authority basis");
      assertEq(render.diagnostic, false, "production is not diagnostic");
      assertEq(render.exitCode, 0, "render exit code");
    },
  },
  {
    name: "fixture job gates pass as diagnostic evidence under the test issuer only",
    run: () => {
      const dir = join(APPROVALS(), "fixture-job");
      const render = evaluateRenderGate(dir, RUNTIME);
      assertEq(render.verdict, "pass", "fixture render verdict");
      assertEq(render.diagnostic, true, "fixture result is diagnostic");
      assertEq(render.authorityBasis, "fixture_test_issuer+signed_event", "fixture authority basis");
    },
  },
  {
    name: "a valid approval for an unchanged revision is reusable, and writing the revision lock changes nothing",
    run: () => {
      const dir = stage("prod-job");
      try {
        const trust = fixtureTrust();
        const first = evaluateRenderGate(dir, RUNTIME, { trust });
        const second = evaluateRenderGate(dir, RUNTIME, { trust });
        assertEq(first.verdict, "pass", "first evaluation");
        assertEq(second.verdict, "pass", "second evaluation reuses the same approval");
        assertEq(first.revision, second.revision, "revision stable across evaluations");
        const before = computeRevisionLock(dir, RUNTIME);
        writeRevisionLock(dir, RUNTIME);
        assertTrue(existsSync(join(dir, "revision-lock.json")), "revision lock written");
        const after = computeRevisionLock(dir, RUNTIME);
        assertEq(after.fullRevision, before.fullRevision, "the lock file is not its own input");
        assertEq(after.designRevision, before.designRevision, "design revision stable");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "headline change moves only the source component and stales preview approval; design approval survives",
    run: () => {
      const dir = stage("prod-job");
      try {
        const before = computeRevisionLock(dir, RUNTIME);
        editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
          (doc.copy as Record<string, unknown>).headline = "A completely new headline";
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(diffComponents(before, after), ["source"], "components moved by a headline change");
        assertEq(after.designRevision, before.designRevision, "design revision survives a copy change");
        assertTrue(after.fullRevision !== before.fullRevision, "full revision moves");
        const trust = fixtureTrust();
        const render = evaluateRenderGate(dir, RUNTIME, { trust });
        assertEq(render.verdict, "blocked", "render blocked");
        assertEq(render.firstErrorCategory, "MG_APPROVAL_STALE", "render first category");
        assertEq(render.exitCode, 4, "render exit class");
        const design = evaluateDesignGate(dir, { trust });
        assertEq(design.verdict, "pass", "design approval survives (Section 16.7 separate digests)");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "image swap moves only the assets component, moves the design revision, and stales the design approval",
    run: () => {
      const dir = stage("prod-job");
      try {
        const before = computeRevisionLock(dir, RUNTIME);
        const heroPath = join(dir, "assets", "hero.png");
        const bytes = readFileSync(heroPath);
        writeFileSync(heroPath, Buffer.concat([bytes, Buffer.from([0])]));
        const newHash = sha256File(heroPath);
        editJson(join(dir, "assets.json"), (doc) => {
          (doc.assets as Array<Record<string, unknown>>)[0].sha256 = newHash;
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(diffComponents(before, after), ["assets"], "components moved by an image swap");
        assertTrue(after.designRevision !== before.designRevision, "design revision moves with imagery");
        const trust = fixtureTrust();
        const design = evaluateDesignGate(dir, { trust });
        assertEq(design.verdict, "blocked", "design blocked");
        assertEq(design.firstErrorCategory, "MG_APPROVAL_STALE", "design first category");
        const render = evaluateRenderGate(dir, RUNTIME, { trust });
        assertEq(render.firstErrorCategory, "MG_APPROVAL_STALE", "render first category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "duration change moves manifest, source and timeline, and stales preview approval only",
    run: () => {
      const dir = stage("prod-job");
      try {
        const before = computeRevisionLock(dir, RUNTIME);
        editJson(join(dir, "manifest.json"), (doc) => {
          doc.duration_frames = 240;
        });
        editJson(join(dir, "timeline.json"), (doc) => {
          doc.total_frames = 240;
          (doc.scenes as Array<Record<string, unknown>>)[0].end_frame_exclusive = 240;
        });
        editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
          doc.duration_frames = 240;
          (doc.motion as Record<string, unknown>).hold_to_frame_exclusive = 240;
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(
          diffComponents(before, after),
          ["manifest", "source", "timeline"],
          "components moved by a duration change"
        );
        assertEq(after.designRevision, before.designRevision, "design revision survives a duration change");
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.firstErrorCategory, "MG_APPROVAL_STALE", "render first category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "font change moves assets and fonts, moves the design revision, and stales the design approval",
    run: () => {
      const dir = stage("prod-job");
      try {
        const before = computeRevisionLock(dir, RUNTIME);
        editJson(join(dir, "assets.json"), (doc) => {
          (doc.font_requirements as Array<Record<string, unknown>>)[0].family_alias = "fixture-sans-alt";
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(diffComponents(before, after), ["assets", "fonts"], "components moved by a font change");
        assertTrue(after.designRevision !== before.designRevision, "design revision moves with fonts");
        const design = evaluateDesignGate(dir, { trust: fixtureTrust() });
        assertEq(design.firstErrorCategory, "MG_APPROVAL_STALE", "design first category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "dataset change moves only the data component and stales preview approval; design survives",
    run: () => {
      const dir = stage("prod-job");
      try {
        const before = computeRevisionLock(dir, RUNTIME);
        editJson(join(dir, "data", "bars.json"), (doc) => {
          (doc.rows as Array<Record<string, unknown>>)[0].value = 13;
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(diffComponents(before, after), ["data"], "components moved by a dataset change");
        assertEq(after.designRevision, before.designRevision, "design revision survives a data change");
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.firstErrorCategory, "MG_APPROVAL_STALE", "render first category");
        const design = evaluateDesignGate(dir, { trust: fixtureTrust() });
        assertEq(design.verdict, "pass", "design approval survives");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "narration text change moves only the narration component; a job with no approvals is refused",
    run: () => {
      const src = join(APPROVALS(), "narration-job");
      const before = computeRevisionLock(src, RUNTIME);
      const dir = stage("narration-job");
      try {
        editJson(join(dir, "narration.json"), (doc) => {
          (doc.scenes as Array<Record<string, unknown>>)[0].text = "Different words for the same scene.";
        });
        const after = computeRevisionLock(dir, RUNTIME);
        assertSetEq(diffComponents(before, after), ["narration"], "components moved by a narration change");
        const render = evaluateRenderGate(src, RUNTIME);
        assertEq(render.verdict, "blocked", "narration job without approvals is blocked");
        assertEq(render.firstErrorCategory, "MG_APPROVAL_REQUIRED", "first category");
        assertEq(render.exitCode, 4, "exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "narration record flows into the MG-021 compiler as measured segments, and overrun fails by name",
    run: () => {
      const dir = join(APPROVALS(), "narration-job");
      const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8")) as {
        job_id: string;
        scenes: Array<{ id: string }>;
      };
      const { record, problems } = loadNarrationRecord(dir, manifest as never);
      assertEq(problems.length, 0, "narration record problems");
      assertTrue(record !== null, "narration record loads");
      const segments = toNarrationSegments(record!, 30);
      assertEq(segments.length, 1, "segment count");
      assertEq(segments[0].startFrame, 0, "segment start frame");
      assertEq(segments[0].endFrameExclusive, 150, "segment end frame (240000 samples at 30 fps)");
      const texts = projectToVoiceoverTexts(record!);
      assertTrue(texts["bar-01"].startsWith("Compare the three groups"), "V1 voiceover projection carries the text");
      const compiled = compileTimeline({
        jobId: manifest.job_id,
        fps: 30,
        mode: "program",
        audioOwner: "self",
        scenes: [{ id: "bar-01", durationFrames: 180 }],
        narration: segments,
      });
      assertTrue(compiled.ok, `compile succeeds: ${JSON.stringify(compiled.ok ? "" : compiled.findings)}`);
      if (compiled.ok) {
        const placed = compiled.compiled.sidecar.narration[0];
        assertEq(placed.startSample, 0, "compiled narration start sample");
        assertEq(placed.endSampleExclusive, 240000, "compiled narration end sample");
      }
      const overrun = compileTimeline({
        jobId: manifest.job_id,
        fps: 30,
        mode: "program",
        audioOwner: "self",
        scenes: [{ id: "bar-01", durationFrames: 180 }],
        narration: [{ id: "narration-bar-01", sceneId: "bar-01", startFrame: 0, endFrameExclusive: 200 }],
      });
      assertTrue(!overrun.ok, "overrunning narration fails compilation");
      if (!overrun.ok) {
        assertTrue(
          JSON.stringify(overrun.findings).includes("TIMELINE_NARRATION_EXCEEDS_PICTURE"),
          "the failure names TIMELINE_NARRATION_EXCEEDS_PICTURE"
        );
      }
    },
  },
  {
    name: "forgery: an event signed with a key the issuer does not hold is a security violation",
    run: () => {
      const dir = stage("prod-job");
      try {
        const approvals = readApprovals(dir);
        const preview = approvals.find((a) => a.scope === "preview")!;
        const eventRel = preview.source_event_ref!;
        const eventPath = join(dir, eventRel);
        const event = JSON.parse(readFileSync(eventPath, "utf8")) as Record<string, unknown>;
        const { signature: _drop, ...payload } = event;
        const forged = signApprovalEvent(payload as never, "attacker-chosen-key");
        writeFileSync(eventPath, JSON.stringify(forged, null, 2) + "\n", "utf8");
        preview.artifact_refs = preview.artifact_refs.map((r) =>
          r.path === eventRel ? { path: eventRel, sha256: sha256File(eventPath) } : r
        );
        writeApprovals(dir, approvals);
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.verdict, "blocked", "forged approval blocked");
        assertEq(render.firstErrorCategory, "MG_SECURITY_VIOLATION", "first category");
        assertEq(render.exitCode, 9, "exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "forgery: an unregistered actor under default trust reports authority unavailable, never a pass",
    run: () => {
      const dir = stage("prod-job");
      try {
        const approvals = readApprovals(dir);
        const preview = approvals.find((a) => a.scope === "preview")!;
        preview.actor_id = "mallory";
        const eventRel = preview.source_event_ref!;
        const eventPath = join(dir, eventRel);
        const event = JSON.parse(readFileSync(eventPath, "utf8")) as Record<string, unknown>;
        const { signature: _drop, ...payload } = event;
        const forged = signApprovalEvent({ ...(payload as object), actor_id: "mallory" } as never, "mallory-key");
        writeFileSync(eventPath, JSON.stringify(forged, null, 2) + "\n", "utf8");
        preview.artifact_refs = preview.artifact_refs.map((r) =>
          r.path === eventRel ? { path: eventRel, sha256: sha256File(eventPath) } : r
        );
        writeApprovals(dir, approvals);
        // No trust override: the built-in defaults recognize only the
        // fixture test issuer, so this production approval has no
        // verifiable authority source at all.
        const render = evaluateRenderGate(dir, RUNTIME);
        assertEq(render.verdict, "blocked", "unregistered actor blocked");
        assertEq(render.firstErrorCategory, "MG_APPROVAL_AUTHORITY_UNAVAILABLE", "first category");
        assertEq(render.exitCode, 4, "exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "production rejects the fixture test issuer even with a correctly signed fixture event",
    run: () => {
      const dir = stage("prod-job");
      try {
        const lock = computeRevisionLock(dir, RUNTIME);
        const approvals = readApprovals(dir).filter((a) => a.scope !== "preview");
        approvals.push(
          makeApproval(dir, {
            approval_id: "appr-prod-preview-fixture-issuer",
            scope: "preview",
            subject_revision: lock.fullRevision!,
            actor_id: "fixture-test-issuer",
            artifact_refs: [{ path: "timeline.json", sha256: sha256File(join(dir, "timeline.json")) }],
          })
        );
        writeApprovals(dir, approvals);
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.verdict, "blocked", "fixture issuer blocked in production");
        assertEq(render.firstErrorCategory, "MG_APPROVAL_AUTHORITY_UNAVAILABLE", "first category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "a foreign approval stops the gate as MG_FOREIGN_JOB at exit 9",
    run: () => {
      const dir = stage("prod-job");
      try {
        const approvals = readApprovals(dir);
        const foreign = { ...approvals[0], approval_id: "appr-foreign", job_id: "some-other-job" };
        approvals.push(foreign as Approval);
        writeApprovals(dir, approvals);
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.verdict, "blocked", "foreign approval blocked");
        assertEq(render.firstErrorCategory, "MG_FOREIGN_JOB", "first category");
        assertEq(render.exitCode, 9, "exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "missing approvals and a pending preview decision are MG_APPROVAL_REQUIRED",
    run: () => {
      const dir = stage("prod-job");
      try {
        rmSync(join(dir, "approvals.json"));
        rmSync(join(dir, "approvals"), { recursive: true, force: true });
        const missing = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(missing.firstErrorCategory, "MG_APPROVAL_REQUIRED", "missing approvals category");
        assertEq(missing.exitCode, 4, "missing approvals exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
      const dir2 = stage("prod-job");
      try {
        const approvals = readApprovals(dir2);
        approvals.find((a) => a.scope === "preview")!.decision = "pending";
        writeApprovals(dir2, approvals);
        const pending = evaluateRenderGate(dir2, RUNTIME, { trust: fixtureTrust() });
        assertEq(pending.firstErrorCategory, "MG_APPROVAL_REQUIRED", "pending decision category");
      } finally {
        rmSync(dir2, { recursive: true, force: true });
      }
    },
  },
  {
    name: "an asset whose bytes disagree with its declared hash is MG_HASH_MISMATCH at exit 9",
    run: () => {
      const dir = stage("prod-job");
      try {
        const heroPath = join(dir, "assets", "hero.png");
        const bytes = readFileSync(heroPath);
        writeFileSync(heroPath, Buffer.concat([bytes, Buffer.from([1])]));
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.verdict, "blocked", "tampered asset blocked");
        assertEq(render.firstErrorCategory, "MG_HASH_MISMATCH", "first category");
        assertEq(render.exitCode, 9, "exit class");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "delivery gate passes on a staged final with owner delivery approval and passing final QC",
    run: () => {
      const dir = stage("prod-job");
      try {
        mkdirSync(join(dir, "renders"), { recursive: true });
        writeFileSync(join(dir, "renders", "final.mp4"), "mg025 fake final render bytes\n");
        const artifact = { path: "renders/final.mp4", sha256: sha256File(join(dir, "renders", "final.mp4")) };
        const lock = computeRevisionLock(dir, RUNTIME);
        const approvals = readApprovals(dir);
        approvals.push(
          makeApproval(dir, {
            approval_id: "appr-prod-delivery",
            scope: "delivery",
            subject_revision: lock.fullRevision!,
            actor_id: "owner-t-otts",
            artifact_refs: [{ path: artifact.path, sha256: artifact.sha256 }],
          })
        );
        writeApprovals(dir, approvals);
        const qc = { artifact_path: artifact.path, artifact_sha256: artifact.sha256, verdict: "pass" as const };
        const delivery = evaluateDeliveryGate(dir, RUNTIME, artifact, qc, { trust: fixtureTrust() });
        assertEq(delivery.verdict, "pass", `delivery verdict: ${JSON.stringify(delivery.findings)}`);
        assertEq(delivery.phase, "FINAL_QC_PASSED", "delivery phase");
        const promoted = assertDeliveryPromotable(dir, RUNTIME, artifact, qc, { trust: fixtureTrust() });
        assertEq(promoted.verdict, "pass", "promotion assertion passes");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "a fixture render can never be promoted, even with a fixture delivery approval and passing QC",
    run: () => {
      const dir = stage("fixture-job");
      try {
        mkdirSync(join(dir, "renders"), { recursive: true });
        writeFileSync(join(dir, "renders", "final.mp4"), "mg025 fake fixture render bytes\n");
        const artifact = { path: "renders/final.mp4", sha256: sha256File(join(dir, "renders", "final.mp4")) };
        const lock = computeRevisionLock(dir, RUNTIME);
        const approvals = readApprovals(dir);
        approvals.push(
          makeApproval(dir, {
            approval_id: "appr-fixture-delivery",
            scope: "delivery",
            subject_revision: lock.fullRevision!,
            actor_id: "fixture-test-issuer",
            artifact_refs: [{ path: artifact.path, sha256: artifact.sha256 }],
          })
        );
        writeApprovals(dir, approvals);
        const qc = { artifact_path: artifact.path, artifact_sha256: artifact.sha256, verdict: "pass" as const };
        const delivery = evaluateDeliveryGate(dir, RUNTIME, artifact, qc);
        assertEq(delivery.verdict, "blocked", "fixture promotion blocked");
        assertEq(delivery.diagnostic, true, "fixture result is diagnostic");
        assertEq(delivery.firstErrorCategory, "MG_APPROVAL_AUTHORITY_UNAVAILABLE", "first category");
        let threw = false;
        try {
          assertDeliveryPromotable(dir, RUNTIME, artifact, qc);
        } catch (err) {
          threw = err instanceof GateError;
        }
        assertTrue(threw, "assertDeliveryPromotable throws GateError for a fixture job");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "delivery gate: failed QC, missing QC, changed artifact, and mis-presented hash each block by name",
    run: () => {
      const setup = (): { dir: string; artifact: { path: string; sha256: string } } => {
        const dir = stage("prod-job");
        mkdirSync(join(dir, "renders"), { recursive: true });
        writeFileSync(join(dir, "renders", "final.mp4"), "mg025 fake final render bytes\n");
        const artifact = { path: "renders/final.mp4", sha256: sha256File(join(dir, "renders", "final.mp4")) };
        const lock = computeRevisionLock(dir, RUNTIME);
        const approvals = readApprovals(dir);
        approvals.push(
          makeApproval(dir, {
            approval_id: "appr-prod-delivery",
            scope: "delivery",
            subject_revision: lock.fullRevision!,
            actor_id: "owner-t-otts",
            artifact_refs: [{ path: artifact.path, sha256: artifact.sha256 }],
          })
        );
        writeApprovals(dir, approvals);
        return { dir, artifact };
      };
      const trust = fixtureTrust();
      {
        const { dir, artifact } = setup();
        try {
          const failed = evaluateDeliveryGate(dir, RUNTIME, artifact, { artifact_path: artifact.path, artifact_sha256: artifact.sha256, verdict: "fail" }, { trust });
          assertEq(failed.firstErrorCategory, "MG_QC_FAILED", "failed QC category");
          assertEq(failed.exitCode, 6, "failed QC exit class");
          const missing = evaluateDeliveryGate(dir, RUNTIME, artifact, null, { trust });
          assertEq(missing.firstErrorCategory, "MG_INPUT_MISSING", "missing QC category");
          const changed = evaluateDeliveryGate(dir, RUNTIME, { path: artifact.path, sha256: "f".repeat(64) }, { artifact_path: artifact.path, artifact_sha256: artifact.sha256, verdict: "pass" }, { trust });
          assertEq(changed.firstErrorCategory, "MG_HASH_MISMATCH", "mis-presented hash category");
          assertEq(changed.exitCode, 9, "hash mismatch exit class");
          writeFileSync(join(dir, "renders", "final.mp4"), "different bytes after approval\n");
          const diskNow = sha256File(join(dir, "renders", "final.mp4"));
          const stale = evaluateDeliveryGate(dir, RUNTIME, { path: artifact.path, sha256: diskNow }, { artifact_path: artifact.path, artifact_sha256: diskNow, verdict: "pass" }, { trust });
          assertEq(stale.firstErrorCategory, "MG_APPROVAL_STALE", "artifact changed after approval category");
        } finally {
          rmSync(dir, { recursive: true, force: true });
        }
      }
    },
  },
  {
    name: "buildApprovedJob constructs the ApprovedMotionJob from the gate-verified permit, not a caller cast",
    run: () => {
      const { job, gate } = buildApprovedJob(join(APPROVALS(), "prod-job"), RUNTIME, { trust: fixtureTrust() });
      assertEq(gate.verdict, "pass", "gate passes");
      assertEq(job.approval.approval_id, "appr-prod-preview", "the job carries the gate permit");
      assertEq(job.approval.scope, "preview", "permit scope");
      const dir = stage("prod-job");
      try {
        editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
          (doc.copy as Record<string, unknown>).headline = "Changed after approval";
        });
        let threw: unknown = null;
        try {
          buildApprovedJob(dir, RUNTIME, { trust: fixtureTrust() });
        } catch (err) {
          threw = err;
        }
        assertTrue(threw instanceof GateError, "stale job throws GateError");
        assertEq((threw as GateError).category, "MG_APPROVAL_STALE", "stale category");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "dispatcher binds production renderFinal to the gate permit and refuses stale or non-permit records",
    run: async () => {
      process.env.MOTION_ISSUER_REGISTRY = join(APPROVALS(), "registry.json");
      process.env.MOTION_APPROVER_KEYS = join(APPROVALS(), "keyring.json");
      try {
        loadIssuerTrust();
        const remo = new FakeAdapter("remotion");
        const dispatcher = new MotionDispatcher(createRegistry([remo]));
        const matrix = dispatcherMatrix();
        const dir = join(APPROVALS(), "prod-job");
        const permit = readApprovals(dir).find((a) => a.scope === "preview")!;
        const ok = await dispatcher.renderFinal(dir, permit, { matrix });
        assertEq(ok.evidence.kind, "final", "production final renders with the gate permit");
        assertEq(remo.count("renderFinal"), 1, "adapter renderFinal calls after permit render");

        const deliveryShaped: Approval = {
          ...permit,
          approval_id: "appr-not-the-permit",
          scope: "delivery",
        };
        let refused: unknown = null;
        try {
          await dispatcher.renderFinal(dir, deliveryShaped, { matrix });
        } catch (err) {
          refused = err;
        }
        assertTrue(refused instanceof AdapterError, "non-permit record refused with AdapterError");
        assertEq((refused as AdapterError).category, "MG_APPROVAL_REQUIRED", "non-permit category");
        assertEq(remo.count("renderFinal"), 1, "adapter not called for the non-permit record");

        const staleDir = stage("prod-job");
        try {
          editJson(join(staleDir, "scenes", "bar-01.json"), (doc) => {
            (doc.copy as Record<string, unknown>).headline = "Changed after approval";
          });
          let staleErr: unknown = null;
          try {
            await dispatcher.renderFinal(staleDir, permit, { matrix });
          } catch (err) {
            staleErr = err;
          }
          assertTrue(staleErr instanceof GateError, "stale production render throws GateError");
          assertEq((staleErr as GateError).category, "MG_APPROVAL_STALE", "stale category");
          assertEq((staleErr as GateError).exitClass, 4, "stale exit class");
          assertEq(remo.count("renderFinal"), 1, "adapter not called for the stale render");
        } finally {
          rmSync(staleDir, { recursive: true, force: true });
        }
      } finally {
        delete process.env.MOTION_ISSUER_REGISTRY;
        delete process.env.MOTION_APPROVER_KEYS;
      }
    },
  },
  {
    name: "dispatcher fixture renderFinal keeps the MG-004 diagnostic contract",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const legacyApproval: Approval = {
        schema_version: "2.0",
        approval_id: "mg025-fixture-approval",
        job_id: "mg025-fixture-job",
        company_id: "mg025-company",
        scope: "delivery",
        decision: "approved",
        subject_revision: "fixture",
        artifact_refs: [],
        actor_id: "mg025-test-runner",
        source_event_ref: null,
        authority_status: "not_verified",
      };
      const outcome = await dispatcher.renderFinal(join(APPROVALS(), "fixture-job"), legacyApproval, {
        matrix: dispatcherMatrix(),
      });
      assertEq(outcome.evidence.kind, "final", "fixture final renders diagnostically");
      assertEq(remo.count("renderFinal"), 1, "adapter renderFinal calls");
    },
  },
  {
    name: "dispatcher catalog consult: unavailable component refused at exit 3 before any adapter call",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      const dir = stage("fixture-job");
      try {
        editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
          doc.component_id = "C10";
        });
        let err: unknown = null;
        try {
          await dispatcher.validate(dir, { matrix: dispatcherMatrix() });
        } catch (e) {
          err = e;
        }
        assertTrue(err instanceof CatalogError, `expected CatalogError, got ${String(err)}`);
        assertEq((err as CatalogError).category, "MG_CAPABILITY_UNSUPPORTED", "catalog category");
        assertEq((err as CatalogError).exitClass, 3, "catalog exit class");
        assertEq(remo.totalCalls(), 0, "adapter calls");
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    },
  },
  {
    name: "dispatcher catalog consult: unknown ids stay MG_UNKNOWN_COMPONENT at exit 2, including catalog-known C04 (canonical schema still gates scene shapes to C05)",
    run: async () => {
      const remo = new FakeAdapter("remotion");
      const dispatcher = new MotionDispatcher(createRegistry([remo]));
      for (const componentId of ["C99", "C04"]) {
        const dir = stage("fixture-job");
        try {
          editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
            doc.component_id = componentId;
          });
          let err: unknown = null;
          try {
            await dispatcher.validate(dir, { matrix: dispatcherMatrix() });
          } catch (e) {
            err = e;
          }
          assertTrue(err instanceof AdapterError, `${componentId}: expected AdapterError, got ${String(err)}`);
          assertEq((err as AdapterError).category, "MG_UNKNOWN_COMPONENT", `${componentId} category`);
          assertEq((err as AdapterError).exitClass, 2, `${componentId} exit class`);
          assertEq(remo.totalCalls(), 0, "adapter calls");
        } finally {
          rmSync(dir, { recursive: true, force: true });
        }
      }
      const ok = await dispatcher.validate(join(APPROVALS(), "fixture-job"), { matrix: dispatcherMatrix() });
      assertTrue(ok.evidence.valid, "the C05 path validates identically");
    },
  },
  {
    name: "render gate catalog consult runs alongside contracts validation",
    run: () => {
      const dir = stage("prod-job");
      try {
        editJson(join(dir, "scenes", "bar-01.json"), (doc) => {
          doc.component_id = "C10";
        });
        const render = evaluateRenderGate(dir, RUNTIME, { trust: fixtureTrust() });
        assertEq(render.verdict, "blocked", "C10 job blocked at the render gate");
        assertTrue(
          render.findings.some((f) => f.category === "MG_CAPABILITY_UNSUPPORTED"),
          "the catalog's MG_CAPABILITY_UNSUPPORTED finding is present"
        );
        assertTrue(
          render.findings.some((f) => f.category === "MG_UNKNOWN_COMPONENT"),
          "the contracts layer's MG_UNKNOWN_COMPONENT finding is also present (alongside, not replaced)"
        );
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
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
  console.log(`Approvals: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
