// Timeline compiler tests for MG-021 (Directive Sections 5.4, 6
// MG-021, 16): one authoritative picture and sound timeline.
//
// Pure, deterministic, offline: no renders, no engines. The cases pin
// (1) the directive's acceptance anchors exactly: six 5-second scenes
// with five half-second overlaps compile to 27.5 seconds (825 frames);
// a fixed 30-second parent slot stays 900 frames with handles inside
// the slot and with no overlap at all; narration longer than the
// picture fails instead of truncating; (2) frame-to-sample conversion
// under the one documented rounding rule (round half up at 48000 Hz),
// at scene boundaries, at overlap midpoints, on a music-beat grid, and
// on a measured spoken-word boundary; (3) the slot and handle
// doctrine: ungranted handles, overflow, and underfill all fail with
// named findings; (4) overlapping writes to one animated property fail
// unless declared intentional, and declared overlaps are recorded;
// (5) every compiled timeline validates against the canonical
// contracts $defs/timeline.
//
// Expected numbers are pinned in tests/evidence/mg021/measurements.json;
// the suite fails on drift rather than rewriting the record.
//
// Exit code 0 when every case passes, 1 otherwise.

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import {
  compileTimeline,
  frameToSample,
  sampleToFrameFloor,
  secondsToFrame,
  secondsToSample,
  toHyperframesTiming,
  toRemotionTiming,
  type CompileResult,
  type CompiledTimeline,
} from "../src/timeline";
import { validateAgainstDef } from "../src/validation/validate";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  if (!ok && detail) console.log(`  ${detail}`);
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function expectOk(line: string, result: CompileResult): CompiledTimeline | null {
  if (!result.ok) {
    report(false, line, `unexpected findings: ${JSON.stringify(result.findings)}`);
    return null;
  }
  report(true, line);
  return result.compiled;
}

function expectKind(line: string, result: CompileResult, kind: string): void {
  if (result.ok) {
    report(false, line, "compiled successfully, expected a failure");
    return;
  }
  const hit = result.findings.some(
    (f) => f.category === "MG_TIMELINE_INVALID" && f.message.startsWith(`${kind}:`)
  );
  report(hit, line, hit ? undefined : `findings: ${JSON.stringify(result.findings)}`);
}

function expectSchema(line: string, result: CompileResult): void {
  if (result.ok) {
    report(false, line, "compiled successfully, expected a schema failure");
    return;
  }
  const hit = result.findings.some((f) => f.category === "MG_SCHEMA_INVALID");
  report(hit, line, hit ? undefined : `findings: ${JSON.stringify(result.findings)}`);
}

const timelineDir = join(fixturesRoot(), "timeline");
const loadFixture = (name: string): Record<string, unknown> =>
  readJson(join(timelineDir, name)) as Record<string, unknown>;
const clone = (v: unknown): any => JSON.parse(JSON.stringify(v)) as any;

const measurements = readJson(
  resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg021", "measurements.json")
) as any;

// ---------------------------------------------------------------------
// Acceptance anchors and the pinned evidence record.
// ---------------------------------------------------------------------

const programInput = loadFixture("program-six-scenes.json");
const program = expectOk(
  "anchor: six 5 s scenes with five 0.5 s overlaps compile",
  compileTimeline(programInput)
);
const slot = expectOk(
  "anchor: 30 s slot with internal overlaps and granted edge handles compiles",
  compileTimeline(loadFixture("slot-thirty-handles.json"))
);
const slotSingle = expectOk(
  "anchor: 30 s slot, one scene, no overlap, compiles",
  compileTimeline(loadFixture("slot-single-scene.json"))
);
const sixty = expectOk("60 fps program compiles", compileTimeline({
  jobId: "mg021-sixty",
  fps: 60,
  mode: "program",
  audioOwner: "none",
  scenes: [
    { id: "p", durationFrames: 300 },
    { id: "q", durationFrames: 300 },
  ],
  transitions: [{ id: "pq", fromSceneId: "p", toSceneId: "q", frames: 30, ownerSceneId: "q" }],
}));

if (program && slot && slotSingle && sixty) {
  const ranges = (c: CompiledTimeline): number[][] =>
    c.sidecar.scenes.map((s) => [s.placedRange.startFrame, s.placedRange.endFrameExclusive]);
  const pinned = {
    conversion_cases: {
      frame_150_at_30fps_samples: frameToSample(150, 30),
      frame_75_at_60fps_samples: frameToSample(75, 60),
      beat7_117bpm_seconds: (7 * 60) / 117,
      beat7_117bpm_sample: secondsToSample((7 * 60) / 117),
      beat7_117bpm_frame_at_30fps: secondsToFrame((7 * 60) / 117, 30),
      word_sample_59256_frame_at_30fps: sampleToFrameFloor(59256, 30),
      half_sample_tie_rounds_up: secondsToSample(1 / 96000),
    },
    program: {
      total_frames: program.sidecar.total_frames,
      total_seconds: toHyperframesTiming(program).durationSec,
      total_samples: program.sidecar.total_samples,
      placed_ranges: ranges(program),
      handles: program.sidecar.handles.map((h) => ({
        id: h.id,
        owner: h.ownerSceneId,
        range: [h.placedRange.startFrame, h.placedRange.endFrameExclusive],
        midpoint_frame_times_two: h.midpointFrameTimesTwo,
        midpoint_sample: h.midpointSample,
      })),
      cues: program.sidecar.cues.map((c) => ({ id: c.id, frame: c.frame, sample: c.sample, anchor: c.anchorKind })),
      narration_samples: program.sidecar.narration.map((n) => [n.startSample, n.endSampleExclusive]),
      s3_source_range: [program.sidecar.scenes[2].sourceRange.startFrame, program.sidecar.scenes[2].sourceRange.endFrameExclusive],
      declared_property_overlap: program.sidecar.property_overlaps_declared[0],
      remotion_scene_s2: toRemotionTiming(program).scenes[1],
      hyperframes_scene_s2: toHyperframesTiming(program).scenes[1],
    },
    slot: {
      total_frames: slot.sidecar.total_frames,
      total_samples: slot.sidecar.total_samples,
      placed_ranges: ranges(slot),
      parent_slot: [slot.sidecar.slot?.parentRange.startFrame, slot.sidecar.slot?.parentRange.endFrameExclusive],
      granted_handles: [slot.sidecar.slot?.grantedHandles.headFrames, slot.sidecar.slot?.grantedHandles.tailFrames],
      used_handles: [slot.sidecar.slot?.usedHandles.headFrames, slot.sidecar.slot?.usedHandles.tailFrames],
      scene_transition_edges: slot.sidecar.scenes.map((s) => [s.transitionInFrames, s.transitionOutFrames]),
      cue_qb: { frame: slot.sidecar.cues[0].frame, sample: slot.sidecar.cues[0].sample },
    },
    slot_single: { total_frames: slotSingle.sidecar.total_frames, placed_ranges: ranges(slotSingle) },
    sixty_fps: { total_frames: sixty.sidecar.total_frames, total_samples: sixty.sidecar.total_samples, placed_ranges: ranges(sixty) },
  };
  const pinnedSubset = {
    conversion_cases: measurements.conversion_cases,
    program: measurements.program,
    slot: measurements.slot,
    slot_single: measurements.slot_single,
    sixty_fps: measurements.sixty_fps,
  };
  report(
    deepEqual(pinned, pinnedSubset),
    "pinned numbers: compiled outputs match tests/evidence/mg021/measurements.json exactly",
    deepEqual(pinned, pinnedSubset) ? undefined : `actual: ${JSON.stringify(pinned)}`
  );

  // The directive's acceptance wording, asserted in its own terms.
  report(program.sidecar.total_frames === 825 && toHyperframesTiming(program).durationSec === 27.5,
    "anchor in directive terms: the program is exactly 27.5 s (825 frames at 30 fps)");
  report(slot.sidecar.total_frames === 900 && slotSingle.sidecar.total_frames === 900,
    "anchor in directive terms: the fixed 30 s parent slot remains 30 s (900 frames) with handles and without overlap");
  report(
    program.timeline.total_frames === 825 && program.timeline.parent_slot === null &&
    slot.timeline.total_frames === 900 && slot.timeline.parent_slot !== null,
    "canonical totals: program 825 with null parent_slot; slot 900 with the parent range recorded"
  );

  for (const [name, compiled] of [["program", program], ["slot", slot], ["slot-single", slotSingle], ["sixty", sixty]] as const) {
    const errors = validateAgainstDef("timeline", compiled.timeline);
    report(errors.length === 0, `canonical schema: compiled ${name} timeline validates against $defs/timeline`,
      errors.length ? JSON.stringify(errors) : undefined);
  }

  const again = compileTimeline(programInput);
  report(again.ok && deepEqual(again.compiled, program), "determinism: recompiling the same input yields the identical plan");
}

// ---------------------------------------------------------------------
// Failure discipline: named findings, never silent adjustment.
// ---------------------------------------------------------------------

{
  const m = clone(programInput);
  m.narration[2].endFrameExclusive = 900;
  expectKind("no truncation: narration ending past the picture fails", compileTimeline(m), "TIMELINE_NARRATION_EXCEEDS_PICTURE");
}
{
  const m = clone(programInput);
  m.narration[1].startFrame = 250;
  expectKind("overlapping narration segments fail", compileTimeline(m), "TIMELINE_NARRATION_OVERLAP");
}
{
  const m = clone(loadFixture("slot-thirty-handles.json"));
  m.edgeTransition.headFrames = 25;
  expectKind("handles: using more head handle than granted fails", compileTimeline(m), "TIMELINE_HANDLE_NOT_GRANTED");
}
{
  const m = clone(loadFixture("slot-thirty-handles.json"));
  m.edgeTransition.tailFrames = 21;
  expectKind("handles: using more tail handle than granted fails", compileTimeline(m), "TIMELINE_HANDLE_NOT_GRANTED");
}
{
  const m = clone(loadFixture("slot-thirty-handles.json"));
  m.scenes[0].durationFrames = 321;
  expectKind("slot: content longer than the slot fails as overflow", compileTimeline(m), "TIMELINE_SLOT_OVERFLOW");
}
{
  const m = clone(loadFixture("slot-thirty-handles.json"));
  m.scenes[0].durationFrames = 319;
  expectKind("slot: content shorter than the slot fails as underfill", compileTimeline(m), "TIMELINE_SLOT_UNDERFILL");
}
{
  const m = clone(loadFixture("slot-thirty-handles.json"));
  delete m.parentSlot;
  expectKind("slot: a missing parent slot fails", compileTimeline(m), "TIMELINE_SLOT_MISSING");
}
{
  const m = clone(programInput);
  m.parentSlot = { range: { startFrame: 0, endFrameExclusive: 825 }, grantedHandles: { headFrames: 0, tailFrames: 0 } };
  expectKind("slot: a parent slot in program mode fails", compileTimeline(m), "TIMELINE_SLOT_MODE_CONFLICT");
}
{
  const m = clone(programInput);
  m.transitions[0].frames = 150;
  expectKind("overlap: an overlap consuming a whole scene fails", compileTimeline(m), "TIMELINE_OVERLAP_EXCEEDS_SCENE");
}
{
  const m = clone(programInput);
  m.transitions[0].toSceneId = "s3";
  expectKind("overlap: a transition joining non-adjacent scenes fails", compileTimeline(m), "TIMELINE_TRANSITION_NOT_ADJACENT");
}
{
  const m = clone(programInput);
  m.transitions.push({ id: "t1b", fromSceneId: "s1", toSceneId: "s2", frames: 10, ownerSceneId: "s2" });
  expectKind("overlap: a second transition on one boundary fails (no double subtraction)", compileTimeline(m), "TIMELINE_TRANSITION_DUPLICATE");
}
{
  const m = clone(programInput);
  m.transitions[0].ownerSceneId = "s4";
  expectKind("overlap: an owner that is neither boundary scene fails", compileTimeline(m), "TIMELINE_HANDLE_OWNER_INVALID");
}
{
  const m = clone(programInput);
  m.cues[1].anchor.wordIndex = 9;
  expectKind("anchor: a spoken-word cue naming a missing word fails", compileTimeline(m), "TIMELINE_ANCHOR_UNRESOLVED");
}
{
  const m = clone(programInput);
  delete m.musicGrid;
  expectKind("anchor: a music-beat cue with no music grid fails", compileTimeline(m), "TIMELINE_ANCHOR_UNRESOLVED");
}
{
  const m = clone(programInput);
  m.cues[0].anchor.sceneLocalFrame = 150;
  expectKind("anchor: a semantic-state cue past its scene's end fails", compileTimeline(m), "TIMELINE_CUE_OUT_OF_BOUNDS");
}
{
  const m = clone(programInput);
  m.cues[1].sceneId = "s3";
  expectKind("anchor: a spoken-word cue resolving outside its declared scene fails", compileTimeline(m), "TIMELINE_CUE_OUTSIDE_SCENE");
}
{
  const m = clone(programInput);
  m.propertyTracks[1].writes[1].intentionalOverlap = false;
  expectKind("property writes: an undeclared overlap on one property fails", compileTimeline(m), "TIMELINE_PROPERTY_WRITE_OVERLAP");
}
{
  const m = clone(programInput);
  m.propertyTracks[0].writes[0].endFrameExclusive = 151;
  expectKind("property writes: a write past its scene's end fails", compileTimeline(m), "TIMELINE_PROPERTY_WRITE_OUT_OF_BOUNDS");
}
{
  const m = clone(programInput);
  m.propertyTracks[0].sceneId = "nope";
  expectKind("property writes: a track naming an unknown scene fails", compileTimeline(m), "TIMELINE_PROPERTY_SCENE_UNKNOWN");
}
{
  const m = clone(programInput);
  m.scenes[2].sourceDurationFrames = 100;
  expectKind("source media: declared source shorter than the scene fails", compileTimeline(m), "TIMELINE_SOURCE_RANGE_SHORT");
}
{
  const m = clone(programInput);
  m.captions[0].endFrameExclusive = 826;
  expectKind("bounds: a caption past the compiled total fails", compileTimeline(m), "TIMELINE_CAPTION_OUT_OF_BOUNDS");
}
{
  const m = clone(programInput);
  m.sfxCues[0].frame = 825;
  expectKind("bounds: an sfx cue at the exclusive end fails", compileTimeline(m), "TIMELINE_SFX_OUT_OF_BOUNDS");
}
{
  const m = clone(programInput);
  m.bogus = 1;
  expectSchema("shape: an unknown key at the root is MG_SCHEMA_INVALID", compileTimeline(m));
}
{
  const m = clone(programInput);
  m.scenes[0].bogus = 1;
  expectSchema("shape: an unknown key inside a scene is MG_SCHEMA_INVALID", compileTimeline(m));
}
{
  const m = clone(programInput);
  m.fps = 24;
  expectSchema("shape: fps outside the contract rates is MG_SCHEMA_INVALID", compileTimeline(m));
}
{
  const m = clone(programInput);
  m.scenes[1].id = "s1";
  expectSchema("shape: a duplicate scene id is MG_SCHEMA_INVALID", compileTimeline(m));
}

console.log(`\nTimeline: ${passed}/${passed + failed} checks passed, ${failed} failed.`);
process.exit(failed === 0 ? 0 : 1);
