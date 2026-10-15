// Diagram tests for MG-017 (Directive Section 6, tests T10/T11).
//
// Real tests, no mocks: the fixtures are resolved with label widths
// measured from the actual Liberation Sans binary (MG-013 typography),
// the frame functions are checked mechanically (subject persistence,
// causality ordering, path termination, label non-collision, the
// title-change negative), and one pattern is rendered end to end
// through the shared runtime's real Remotion install, with the subject
// located in the decoded stills and compared against the geometry.
//
// Prerequisites: the shared runtime must be provisioned
// (shared-utils/motion-render-runtime/provision.sh) and the runtime
// package built (npm test runs the build first). Render outputs go to
// scratch space inside the shared runtime's gitignored .runtime dir;
// the committed evidence (proof stills + measurements.json) lands in
// 72-motion-video-plus/tests/evidence/mg017.
//
// Exit code 0 when every case passes, 1 otherwise.

import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import {
  ComponentRegistry,
  c04Entry,
  c09Entry,
  validateCatalogEntry,
} from "../src/catalog";
import {
  FontTextMeasurer,
  edgeDrawnLengthAt,
  edgeDrawnPoints,
  evaluateAssertions,
  evaluateCausality,
  labelCollisions,
  nodeBoxAt,
  resolveDiagram,
  subjectArcAt,
  subjectPositionAt,
  subjectStateAt,
  validateDiagramSceneDoc,
  type DiagramSceneDoc,
  type ResolvedDiagram,
} from "../src/diagrams";
import { resolveFont } from "../src/remotion/fonts";
import { decodeFrameRgb, readPngDimensions } from "../src/remotion/decode";
import { renderDiagramStills } from "../src/diagrams/render/render-stills";

// ---------------------------------------------------------------------------
// Paths, fixtures, harness
// ---------------------------------------------------------------------------

function fixturesDir(): string {
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures", "diagrams");
}
function evidenceDir(): string {
  return resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg017");
}
function runtimeStateDir(): string {
  return resolve(
    __dirname,
    "..",
    "..",
    "..",
    "..",
    "shared-utils",
    "motion-render-runtime",
    ".runtime"
  );
}
const FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf";
const measurer = new FontTextMeasurer(FONT_PATH);

function loadFixture(name: string): DiagramSceneDoc {
  return JSON.parse(readFileSync(join(fixturesDir(), name), "utf8")) as DiagramSceneDoc;
}
function resolveFixture(name: string): { doc: DiagramSceneDoc; resolved: ResolvedDiagram } {
  const doc = loadFixture(name);
  const result = resolveDiagram(doc.diagram, measurer);
  if (!result.ok) {
    throw new Error(`fixture ${name} must resolve: ${JSON.stringify(result.findings)}`);
  }
  return { doc, resolved: result.resolved };
}

let passed = 0;
let failed = 0;
const failures: string[] = [];
function check(name: string, fn: () => void): void {
  try {
    fn();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (err) {
    failed += 1;
    const message = err instanceof Error ? err.message : String(err);
    failures.push(`${name}: ${message}`);
    console.log(`FAIL ${name}: ${message}`);
  }
}
async function checkAsync(name: string, fn: () => Promise<void>): Promise<void> {
  try {
    await fn();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (err) {
    failed += 1;
    const message = err instanceof Error ? err.message : String(err);
    failures.push(`${name}: ${message}`);
    console.log(`FAIL ${name}: ${message}`);
  }
}
function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}
function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const FLOW = "c04-flow-mechanism.json";
const RETITLED = "c04-flow-retitled.json";
const BEFORE_AFTER = "c04-before-after.json";
const BOTTLENECK = "c04-bottleneck.json";
const BRANCHING = "c09-branching.json";
const DENSE = "c09-dense-branching.json";
const COLLIDING = "c04-colliding-chain.json";

// ---------------------------------------------------------------------------
// Catalog registration
// ---------------------------------------------------------------------------

check("catalog: C04 and C09 entries are well-formed and available", () => {
  assertEq(validateCatalogEntry(c04Entry()).length, 0, "C04 entry problems");
  assertEq(validateCatalogEntry(c09Entry()).length, 0, "C09 entry problems");
  const registry = ComponentRegistry.createDefault();
  assertEq(registry.list().length, 12, "the default registry holds twelve entries");
  const c04 = registry.requireDispatchable("C04", "1.0.0");
  const c09 = registry.requireDispatchable("C09", "1.0.0");
  assertEq(c04.availability, "available", "C04 availability");
  assertEq(c09.availability, "available", "C09 availability");
  const c05 = registry.requireDispatchable("C05", "1.0.0");
  assertEq(c05.availability, "available", "C05 remains available and untouched");
});

check("catalog: example scenes validate and match the fixtures structurally", () => {
  const registry = ComponentRegistry.createDefault();
  for (const [file, componentId] of [
    [FLOW, "C04"],
    [BRANCHING, "C09"],
  ] as const) {
    const fixture = loadFixture(file);
    const verdict = registry.validateSceneProps(fixture);
    assertTrue(verdict.valid, `fixture ${file} must validate through the catalog: ${JSON.stringify(verdict.findings)}`);
    const entry = registry.get(componentId, "1.0.0");
    const example = entry?.examples[0]?.scene as unknown as DiagramSceneDoc;
    const fixtureStripped: DiagramSceneDoc = {
      ...fixture,
      semantic_motion_assertions: fixture.semantic_motion_assertions.filter(
        (assertion) => assertion.kind !== "subject_identity"
      ),
    };
    assertTrue(
      deepEqual(example, fixtureStripped),
      `catalog example for ${componentId} must equal fixture ${file} modulo its font-measured subject_identity assertions`
    );
  }
});

// ---------------------------------------------------------------------------
// Schema and structural validation
// ---------------------------------------------------------------------------

check("schema: every valid fixture passes document validation", () => {
  for (const file of [FLOW, RETITLED, BEFORE_AFTER, BOTTLENECK, BRANCHING, DENSE, COLLIDING]) {
    const findings = validateDiagramSceneDoc(loadFixture(file));
    assertEq(findings.length, 0, `fixture ${file} findings: ${JSON.stringify(findings)}`);
  }
});

check("schema: an unknown top-level key is refused", () => {
  const doc = loadFixture(FLOW) as unknown as Record<string, unknown>;
  doc.surprise = true;
  const findings = validateDiagramSceneDoc(doc);
  assertTrue(
    findings.some((finding) => finding.category === "MG_SCHEMA_INVALID"),
    `expected MG_SCHEMA_INVALID, got ${JSON.stringify(findings)}`
  );
});

check("schema: an orphan edge (target never declared) is refused", () => {
  const doc = loadFixture(FLOW);
  doc.diagram.edges.push({
    id: "edge-ghost",
    source: "intake",
    target: "nowhere",
    kind: "flow",
  });
  const findings = validateDiagramSceneDoc(doc);
  assertTrue(
    findings.some(
      (finding) => finding.category === "MG_SCHEMA_INVALID" && finding.message.includes("orphan")
    ),
    `expected an orphan-edge MG_SCHEMA_INVALID, got ${JSON.stringify(findings)}`
  );
});

check("schema: branching without a declared selection is refused", () => {
  const doc = loadFixture(BRANCHING);
  doc.diagram.selected_branch_edge_id = null;
  const findings = validateDiagramSceneDoc(doc);
  assertTrue(
    findings.some(
      (finding) =>
        finding.category === "MG_SCHEMA_INVALID" &&
        finding.message.includes("declared, never inferred")
    ),
    `expected the declared-branch refusal, got ${JSON.stringify(findings)}`
  );
});

check("schema: envelope duration disagreeing with the diagram hold is refused", () => {
  const doc = loadFixture(FLOW);
  doc.duration_frames = 999;
  const findings = validateDiagramSceneDoc(doc);
  assertTrue(
    findings.some((finding) => finding.category === "MG_TIMELINE_INVALID"),
    `expected MG_TIMELINE_INVALID, got ${JSON.stringify(findings)}`
  );
});

// ---------------------------------------------------------------------------
// Patterns, subject persistence, causality
// ---------------------------------------------------------------------------

check("patterns: all four patterns instantiate and resolve", () => {
  for (const file of [FLOW, BEFORE_AFTER, BOTTLENECK, BRANCHING]) {
    const { doc } = resolveFixture(file);
    assertTrue(doc.diagram.pattern.length > 0, "pattern named");
  }
  const patterns = new Set(
    [FLOW, BEFORE_AFTER, BOTTLENECK, BRANCHING].map((file) => loadFixture(file).diagram.pattern)
  );
  assertEq(patterns.size, 4, "four distinct patterns across the fixtures");
});

check("subject persistence: same id at every proof frame, position a deterministic function of frame", () => {
  const { resolved } = resolveFixture(FLOW);
  const subjectId = resolved.subject?.id;
  assertEq(subjectId, "lead-001", "subject id");
  const positions = [15, 30, 75, 120, 135, 170].map((frame) => {
    const first = subjectPositionAt(resolved, frame);
    const second = subjectPositionAt(resolved, frame);
    assertTrue(deepEqual(first, second), `position at frame ${frame} must be seek-stable`);
    return first;
  });
  const distinct = new Set(positions.map((p) => `${p?.x},${p?.y}`));
  assertTrue(distinct.size >= 4, `the subject must actually travel; got ${distinct.size} distinct positions`);
  const arcs = [15, 45, 75, 105, 135].map((frame) => subjectArcAt(resolved, frame));
  for (let i = 1; i < arcs.length; i += 1) {
    assertTrue(arcs[i] > arcs[i - 1], "subject arc must increase monotonically through the motion window");
  }
  assertEq(subjectArcAt(resolved, 170), subjectArcAt(resolved, 135), "the subject rests during the hold");
});

check("causality: no node activates before its upstream cause completes", () => {
  for (const file of [FLOW, BEFORE_AFTER, BOTTLENECK, BRANCHING, DENSE]) {
    const { resolved } = resolveFixture(file);
    const evaluation = evaluateCausality(resolved);
    assertTrue(
      evaluation.pass,
      `${file} causality failed: ${JSON.stringify(evaluation.checks.filter((c) => !c.ok))}`
    );
    assertTrue(evaluation.pathOrderOk, `${file} subject arrival order must be strictly increasing`);
  }
  const { resolved } = resolveFixture(FLOW);
  const activation = (id: string): number =>
    resolved.nodes.find((node) => node.id === id)?.activationFrame ?? -1;
  assertTrue(activation("qualify") > activation("intake"), "Qualify activates after Intake");
  assertTrue(activation("proposal") > activation("qualify"), "Proposal activates after Qualify");
  assertTrue(activation("delivery") > activation("proposal"), "Delivery activates after Proposal");
});

check("causality: a tampered activation order is caught", () => {
  const { resolved } = resolveFixture(FLOW);
  const tampered: ResolvedDiagram = JSON.parse(JSON.stringify(resolved)) as ResolvedDiagram;
  const delivery = tampered.nodes.find((node) => node.id === "delivery");
  if (delivery) delivery.activationFrame = 1;
  assertTrue(
    !evaluateCausality(tampered).pass,
    "moving Delivery's activation before its cause must fail the causality evaluation"
  );
});

// ---------------------------------------------------------------------------
// Geometry: termination, drawing, labels
// ---------------------------------------------------------------------------

/** The anchor rule restated independently: an edge exits the source
 * side facing the target and enters the target side facing the source. */
function expectedAnchors(
  resolved: ResolvedDiagram,
  sourceId: string,
  targetId: string
): { exit: { x: number; y: number }; entry: { x: number; y: number } } {
  const s = resolved.nodes.find((node) => node.id === sourceId);
  const t = resolved.nodes.find((node) => node.id === targetId);
  if (!s || !t) throw new Error("anchor restatement lost a node");
  if (resolved.orientation === "landscape") {
    const forward = t.center.x >= s.center.x;
    return {
      exit: forward
        ? { x: s.box.x + s.box.width, y: s.center.y }
        : { x: s.box.x, y: s.center.y },
      entry: forward
        ? { x: t.box.x, y: t.center.y }
        : { x: t.box.x + t.box.width, y: t.center.y },
    };
  }
  const forward = t.center.y >= s.center.y;
  return {
    exit: forward
      ? { x: s.center.x, y: s.box.y + s.box.height }
      : { x: s.center.x, y: s.box.y },
    entry: forward
      ? { x: t.center.x, y: t.box.y }
      : { x: t.center.x, y: t.box.y + t.box.height },
  };
}

check("geometry: every path terminates exactly at its target anchor", () => {
  const TOLERANCE = 1e-6;
  for (const file of [FLOW, BEFORE_AFTER, BOTTLENECK, BRANCHING, DENSE]) {
    const { resolved } = resolveFixture(file);
    for (const edge of resolved.edges) {
      const expected = expectedAnchors(resolved, edge.source, edge.target);
      const first = edge.points[0];
      const last = edge.points[edge.points.length - 1];
      const startErr = Math.hypot(first.x - expected.exit.x, first.y - expected.exit.y);
      const endErr = Math.hypot(last.x - expected.entry.x, last.y - expected.entry.y);
      assertTrue(startErr <= TOLERANCE, `${file}/${edge.id} starts ${startErr}px from the source exit anchor`);
      assertTrue(endErr <= TOLERANCE, `${file}/${edge.id} terminates ${endErr}px from the target entry anchor (tolerance ${TOLERANCE})`);
    }
  }
});

check("geometry: connection drawing progresses along the path and the drawn tip is the subject", () => {
  const { resolved } = resolveFixture(FLOW);
  const edge = resolved.edges.find((candidate) => candidate.id === "edge-qualify-proposal");
  assertTrue(edge !== undefined, "edge exists");
  if (!edge) return;
  assertEq(edgeDrawnLengthAt(resolved, edge, 15), 0, "nothing of the second edge is drawn before the subject reaches it");
  const mid = edgeDrawnLengthAt(resolved, edge, 75);
  assertTrue(mid > 0 && mid < edge.length, `mid-traversal drawn length must be partial, got ${mid} of ${edge.length}`);
  assertEq(edgeDrawnLengthAt(resolved, edge, 135), edge.length, "the edge is fully drawn when the subject completes it");
  const drawn = edgeDrawnPoints(resolved, edge, 75);
  const tip = drawn[drawn.length - 1];
  const subject = subjectPositionAt(resolved, 75);
  assertTrue(subject !== null, "subject exists at frame 75");
  if (subject) {
    const err = Math.hypot(tip.x - subject.x, tip.y - subject.y);
    assertTrue(err <= 1e-6, `the drawn tip must be the subject's position; off by ${err}px`);
  }
  let previous = -1;
  for (let frame = 15; frame <= 135; frame += 5) {
    const length = edgeDrawnLengthAt(resolved, edge, frame);
    assertTrue(length >= previous, "drawn length never retreats");
    previous = length;
  }
});

check("labels: the dense branching fixture resolves with zero label collisions", () => {
  const { resolved } = resolveFixture(DENSE);
  assertEq(resolved.nodes.length, 8, "dense fixture node count");
  assertEq(labelCollisions(resolved).length, 0, "dense fixture label collisions");
});

check("labels: a colliding chain is refused with the named impossibility", () => {
  const doc = loadFixture(COLLIDING);
  const result = resolveDiagram(doc.diagram, measurer);
  assertTrue(!result.ok, "the colliding chain must not resolve");
  if (!result.ok) {
    assertEq(result.findings[0].category, "MG_LAYOUT_IMPOSSIBLE", "impossibility category");
    assertTrue(
      result.findings[0].message.includes("chain_exceeds_canvas"),
      `the impossibility must be named; got: ${result.findings[0].message}`
    );
  }
});

check("labels: a hand-moved label overlap is detected", () => {
  const { resolved } = resolveFixture(BRANCHING);
  const tampered: ResolvedDiagram = JSON.parse(JSON.stringify(resolved)) as ResolvedDiagram;
  const enroll = tampered.nodes.find((node) => node.id === "enroll");
  const nurture = tampered.nodes.find((node) => node.id === "nurture");
  if (enroll && nurture) enroll.labelBox = { ...nurture.labelBox };
  assertTrue(labelCollisions(tampered).length >= 1, "the overlap must be found");
});

// ---------------------------------------------------------------------------
// Pattern semantics
// ---------------------------------------------------------------------------

check("branching: the subject takes the declared branch and never enters the untaken ones", () => {
  const { doc, resolved } = resolveFixture(BRANCHING);
  assertEq(doc.diagram.selected_branch_edge_id, "edge-qualified-enroll", "declared selection");
  const selected = resolved.edges.find((edge) => edge.id === "edge-qualified-enroll");
  assertTrue(selected?.isPathEdge === true, "the selected branch is the subject path edge");
  const final = subjectPositionAt(resolved, 170);
  const enroll = resolved.nodes.find((node) => node.id === "enroll");
  assertTrue(final !== null && enroll !== undefined, "final position and Enroll node exist");
  if (final && enroll) {
    assertTrue(
      Math.hypot(final.x - enroll.center.x, final.y - enroll.center.y) <= 1e-6,
      "the subject ends at the selected outcome's center"
    );
  }
  for (const otherId of ["nurture", "decline"]) {
    const other = resolved.nodes.find((node) => node.id === otherId);
    if (!other || !resolved.subject) continue;
    const nearest = Math.min(
      ...resolved.subject.points.map((point) =>
        Math.hypot(point.x - other.center.x, point.y - other.center.y)
      )
    );
    assertTrue(nearest > 100, `the subject path must never enter ${otherId}; nearest approach ${nearest}px`);
    const edge = resolved.edges.find((candidate) => candidate.target === otherId);
    const decision = resolved.nodes.find((node) => node.id === "qualified");
    assertTrue(
      edge !== undefined &&
        decision?.activationFrame !== null &&
        decision?.activationFrame !== undefined &&
        edge.drawStartFrame >= decision.activationFrame,
      `the untaken branch to ${otherId} draws only after the decision activates`
    );
  }
});

check("before/after: the subject keeps its identity and flips state at the transform midpoint", () => {
  const { resolved } = resolveFixture(BEFORE_AFTER);
  assertEq(resolved.subject?.id, "request-001", "subject identity persists across the transformation");
  assertEq(subjectStateAt(resolved, 30), "before", "state before the transform midpoint");
  assertEq(subjectStateAt(resolved, 140), "after", "state after the transform midpoint");
  const early = subjectPositionAt(resolved, 30);
  const late = subjectPositionAt(resolved, 140);
  assertTrue(
    early !== null && late !== null && late.x > early.x,
    "the same subject is trackable on both sides of the transformation"
  );
});

check("bottleneck: the subject creeps before relief, speeds after, and the constraint visibly widens", () => {
  const { doc, resolved } = resolveFixture(BOTTLENECK);
  const relief = doc.diagram.relief;
  assertTrue(relief !== null, "relief declared");
  if (!relief) return;
  const part = resolved.subject?.parts.find((p) => p.type === "node" && p.id === "review");
  assertTrue(part !== undefined, "constraint part exists");
  if (!part) return;
  const arcAtRelief = subjectArcAt(resolved, relief.frame);
  const expectedCreep = part.from + relief.creep_share * (part.to - part.from);
  assertTrue(
    Math.abs(arcAtRelief - expectedCreep) <= 1e-6,
    `at relief the subject has crept exactly creep_share through the constraint: arc ${arcAtRelief} vs ${expectedCreep}`
  );
  const speedBefore = (subjectArcAt(resolved, relief.frame) - subjectArcAt(resolved, relief.frame - 10)) / 10;
  const speedAfter = (subjectArcAt(resolved, relief.frame + 10) - subjectArcAt(resolved, relief.frame)) / 10;
  assertTrue(
    speedAfter > speedBefore * 1.5,
    `flow must visibly speed after relief: ${speedBefore.toFixed(2)} px/f before, ${speedAfter.toFixed(2)} px/f after`
  );
  const review = resolved.nodes.find((node) => node.id === "review");
  assertTrue(review !== undefined, "review node exists");
  if (review) {
    const base = nodeBoxAt(resolved, review, relief.frame - 5).width;
    const widened = nodeBoxAt(resolved, review, relief.frame + 30).width;
    assertEq(base, review.box.width, "the constraint is at base width before relief");
    assertTrue(
      Math.abs(widened - review.box.width * (1 + relief.widen_ratio)) <= 0.5,
      `after relief the constraint is widened by widen_ratio: ${base} -> ${widened}`
    );
  }
});

check("title-change negative: retitling changes no geometry", () => {
  const a = resolveFixture(FLOW);
  const b = resolveFixture(RETITLED);
  assertTrue(a.doc.copy.headline !== b.doc.copy.headline, "the two scenes really do differ only in title (sanity)");
  assertTrue(deepEqual(a.doc.diagram, b.doc.diagram), "the diagram specs are identical (sanity)");
  const strip = (resolved: ResolvedDiagram): unknown =>
    JSON.parse(
      JSON.stringify({
        nodes: resolved.nodes,
        edges: resolved.edges,
        subject: resolved.subject,
      })
    );
  assertTrue(
    deepEqual(strip(a.resolved), strip(b.resolved)),
    "node boxes, edge geometry, and the subject path must be identical when only the title changes: the title cannot satisfy the test"
  );
});

check("assertions: every fixture's declared semantic assertions pass", () => {
  for (const file of [FLOW, BEFORE_AFTER, BOTTLENECK, BRANCHING, DENSE]) {
    const { doc, resolved } = resolveFixture(file);
    const results = evaluateAssertions(doc, resolved);
    const failing = results.filter((result) => !result.pass);
    assertEq(
      failing.length,
      0,
      `${file} failing assertions: ${failing.map((f) => `${f.assertion_id} (${f.detail})`).join("; ")}`
    );
  }
});

// ---------------------------------------------------------------------------
// Render proof: one pattern end to end through the real Remotion engine
// ---------------------------------------------------------------------------

const measurements: Record<string, unknown> = {
  item: "MG-017",
  section: "Section 6 causal diagrams; deliverable 4 render proof (C04 flow_through through Remotion)",
};

function accentCentroid(pngPath: string, width: number, height: number): { x: number; y: number; pixels: number } {
  const rgb = decodeFrameRgb(pngPath, null, width, height);
  const [ar, ag, ab] = [0xc0, 0x4a, 0x26];
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 3;
      const diff =
        Math.abs(rgb[offset] - ar) + Math.abs(rgb[offset + 1] - ag) + Math.abs(rgb[offset + 2] - ab);
      if (diff <= 66) {
        sumX += x;
        sumY += y;
        count += 1;
      }
    }
  }
  if (count === 0) return { x: -1, y: -1, pixels: 0 };
  return { x: sumX / count, y: sumY / count, pixels: count };
}

async function renderProof(): Promise<void> {
  const { doc, resolved } = resolveFixture(FLOW);
  const font = resolveFont("font-fixture-sans", "fixture-sans", [400, 700]);
  const scratch = join(runtimeStateDir(), "mg017-tests");
  const frames = [30, 75, 170];
  const result = await renderDiagramStills({
    doc,
    resolved,
    font,
    frames,
    outputDir: scratch,
    filePrefix: "c04-flow",
  });
  measurements.runtime = {
    lockId: result.runtime.lockId,
    remotionVersion: result.runtime.remotionVersion,
    bundleKey: result.bundleKey,
  };
  measurements.font = {
    family: font.family,
    files: font.files.map((file) => ({ weight: file.weight, path: file.path, sha256: file.sha256 })),
  };
  const perFrame: Record<string, unknown> = {};
  let previousCentroidX = -1;
  for (const still of result.stills) {
    const dims = readPngDimensions(still.path);
    assertTrue(dims !== null && dims.width === 1920 && dims.height === 1080, `still f${still.frame} dimensions`);
    const centroid = accentCentroid(still.path, 1920, 1080);
    const expected = subjectPositionAt(resolved, still.frame);
    assertTrue(expected !== null, "expected subject position exists");
    if (!expected) continue;
    // The accent pixels are the subject marker plus its id label above
    // it; the marker dominates, so the centroid sits near the marker,
    // biased upward by the label. Tolerance 46px absorbs the label.
    const distance = Math.hypot(centroid.x - expected.x, centroid.y - expected.y);
    assertTrue(centroid.pixels > 400, `frame ${still.frame}: the subject marker must be visibly present (${centroid.pixels} accent px)`);
    assertTrue(
      distance <= 46,
      `frame ${still.frame}: decoded subject centroid (${centroid.x.toFixed(1)}, ${centroid.y.toFixed(1)}) must sit at the geometry position (${expected.x}, ${expected.y}); off by ${distance.toFixed(1)}px`
    );
    assertTrue(
      centroid.x > previousCentroidX,
      `frame ${still.frame}: the rendered subject must have moved right since the previous proof frame`
    );
    previousCentroidX = centroid.x;
    const evidenceName = `c04-flow-f${still.frame}.png`;
    cpSync(still.path, join(evidenceDir(), evidenceName));
    perFrame[`frame_${still.frame}`] = {
      geometry_subject_position: { x: expected.x, y: expected.y },
      decoded_accent_centroid: {
        x: Math.round(centroid.x * 10) / 10,
        y: Math.round(centroid.y * 10) / 10,
        pixels: centroid.pixels,
      },
      centroid_distance_px: Math.round(distance * 10) / 10,
      still: evidenceName,
      sha256: sha256File(join(evidenceDir(), evidenceName)),
    };
  }
  measurements.flow_fixture = {
    scene: FLOW,
    subject_id: resolved.subject?.id,
    frames: perFrame,
  };
}

async function main(): Promise<void> {
  mkdirSync(evidenceDir(), { recursive: true });
  await checkAsync("render: C04 flow renders through Remotion and the decoded subject matches the geometry", renderProof);
  measurements.cases = { passed, failed };
  writeFileSync(join(evidenceDir(), "measurements.json"), JSON.stringify(measurements, null, 2) + "\n");
  console.log(`run-diagrams: ${passed} passed, ${failed} failed`);
  if (failures.length > 0) {
    console.log("failures:\n" + failures.map((failure) => ` - ${failure}`).join("\n"));
  }
  process.exit(failed === 0 ? 0 : 1);
}

void main();
