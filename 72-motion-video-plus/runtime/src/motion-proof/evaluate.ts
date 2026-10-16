// The motion proof evaluator (Directive MG-032). Given a motion
// proof case and the artifacts under test (a rendered video and its
// MG-031 coverage record), it produces a proof package: checkpoint
// frames extracted at full resolution, a full-fps clip around the
// action, and a proof record that states, per checkpoint, what the
// scene specification required, what the renderer's own frame
// functions compute, and what the decoded raster actually shows,
// restricted to the subject's region.
//
// The evaluator is deliberately hard to satisfy with decoration:
// - Expectations are derived from the scene specification, and the
//   scene's own declared assertions are cross-checked against that
//   derivation; a specification that lies is refused as a contract
//   error (MG_SCHEMA_INVALID), not graded against its own lie.
// - The MG-031 coverage record must be complete, must bind the exact
//   video under test (sha256), and must name the same job; a
//   checkpoint the bundle never captured is incomplete evidence.
// - A rough_layout_only artifact cannot satisfy a full-fps evidence
//   requirement: reduced-frame-rate evidence is layout evidence.
// - A depth claim without occlusion or depth evidence is refused by
//   name (MG_CAPABILITY_UNSUPPORTED); depth-map evidence is not an
//   implemented family in this evaluator, and the refusal says so.
// - Semantic cases route to human judgment: without an attached human
//   verdict record the verdict is needs_human_judgment, never a
//   fabricated automated pass.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { decodeFrameRgb, probeVideoFile } from "../remotion/decode";
import {
  deriveBarsGeometry,
  deriveTransitGeometry,
  type BarsGeometry,
  type TransitGeometry,
} from "./geometry";
import {
  accentCentroidInWindow,
  accentCountInBox,
  meanAbsDiffOutsideRegions,
  measureBarWidthInRegion,
} from "./measure";
import { validateMotionProofCase } from "./schema";
import type {
  CheckpointAssertion,
  HumanVerdict,
  MotionFinding,
  MotionProofCase,
  MotionProofInputs,
  MotionProofRecord,
  MotionProofResult,
  MotionVerdict,
  SourceBox,
} from "./types";

const EXIT_BY_CATEGORY: Record<string, number> = {
  MG_SCHEMA_INVALID: 2,
  MG_INPUT_MISSING: 3,
  MG_CAPABILITY_UNSUPPORTED: 3,
  MG_ENCODE_FAILED: 5,
  MG_FAKE_MOTION: 6,
  MG_COVERAGE_INCOMPLETE: 6,
  MG_QC_FAILED: 6,
  MG_FOREIGN_JOB: 9,
  MG_HASH_MISMATCH: 9,
};

/** Blocking-class rank in the Section 16.9 order (validation,
 * dependency, authority, execution, QC, delivery); security findings
 * stop the evaluation before this ranking is ever consulted. */
function classRank(category: string): number {
  const exit = EXIT_BY_CATEGORY[category] ?? 6;
  if (exit === 2) return 0;
  if (exit === 3) return 1;
  if (exit === 5) return 3;
  return 4;
}

interface CoverageSample {
  frame?: number;
  status?: string;
  files?: { full?: string };
}

interface CoverageRecordShape {
  job_id?: string;
  verdict?: string;
  video?: { sha256?: string; fps?: string };
  samples?: CoverageSample[];
  inputs?: {
    review_record?: {
      engine?: string;
      label?: string;
      rough_layout_only?: boolean;
    } | null;
  } | null;
  findings?: string[];
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function runFfmpeg(args: string[], what: string): void {
  const result = spawnSync("ffmpeg", args, { maxBuffer: 64 * 1024 * 1024 });
  if (result.error) {
    throw new Error(`${what}: ffmpeg could not run: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString("utf8").slice(-600) : "";
    throw new Error(`${what}: ffmpeg exited ${result.status}: ${stderr}`);
  }
}

function extractPng(video: string, frame: number, out: string): void {
  // Remove any stale artifact first: an interrupted earlier run must
  // never leave a file this evaluation could mistake for its own.
  rmSync(out, { force: true });
  runFfmpeg(
    [
      "-v", "error",
      "-i", video,
      "-vf", `select='eq(n\\,${frame})'`,
      "-frames:v", "1",
      out,
    ],
    `extract frame ${frame}`
  );
  if (!existsSync(out)) {
    throw new Error(`extract frame ${frame}: ffmpeg produced no file at ${out}`);
  }
}

function extractClip(
  video: string,
  start: number,
  endExclusive: number,
  fpsNumerator: number,
  fpsDenominator: number,
  out: string
): void {
  const rate = fpsNumerator / fpsDenominator;
  rmSync(out, { force: true });
  runFfmpeg(
    [
      "-v", "error",
      "-i", video,
      "-vf",
      `select='between(n\\,${start}\\,${endExclusive - 1})',setpts=N/(${rate}*TB)`,
      "-r", String(rate),
      "-an",
      "-c:v", "libx264",
      "-pix_fmt", "yuv420p",
      out,
    ],
    `extract clip [${start}, ${endExclusive})`
  );
  if (!existsSync(out)) {
    throw new Error(`extract clip: ffmpeg produced no file at ${out}`);
  }
}

export function evaluateMotionProof(inputs: MotionProofInputs): MotionProofResult {
  const findings: MotionFinding[] = [];
  const record: MotionProofRecord = {
    schema_version: "1.0",
    kind: "motion_proof_record",
    item: "MG-032",
    case_id: "unknown",
    job_id: "unknown",
    scene_id: "unknown",
    component_id: "unknown",
    verdict: "refused",
    category: null,
    exit_code: 0,
    bindings: {
      video_sha256: null,
      coverage_job_id: null,
      coverage_verdict: null,
      review_label: null,
      review_engine: null,
    },
    assertions: [],
    occlusion: null,
    context_change: null,
    clip: null,
    frames: [],
    human_verdict: inputs.humanVerdict ?? null,
    findings,
    generated_at: new Date().toISOString(),
  };

  const finish = (verdict: MotionVerdict, category: string | null): MotionProofResult => {
    record.verdict = verdict;
    record.category = category;
    record.exit_code = category === null ? 0 : EXIT_BY_CATEGORY[category] ?? 6;
    record.generated_at = new Date().toISOString();
    mkdirSync(inputs.outputDir, { recursive: true });
    const target = join(inputs.outputDir, "proof-record.json");
    const tmp = `${target}.tmp-${process.pid}`;
    writeFileSync(tmp, JSON.stringify(record, null, 2) + "\n", "utf8");
    renameSync(tmp, target);
    return { record, exitCode: record.exit_code };
  };
  const refuse = (category: string, message: string): MotionProofResult => {
    findings.push({ category, message });
    return finish("refused", category);
  };

  // ----- Phase A: the case document itself. -----
  const validated = validateMotionProofCase(inputs.caseDoc);
  if (validated.caseDoc === null) {
    const raw = inputs.caseDoc as { id?: unknown } | null;
    if (raw && typeof raw.id === "string") record.case_id = raw.id;
    return refuse(
      "MG_SCHEMA_INVALID",
      `motion proof case fails its schema: ${validated.problems.join("; ")}`
    );
  }
  const caseDoc: MotionProofCase = validated.caseDoc;
  record.case_id = caseDoc.id;
  record.job_id = caseDoc.job_id;
  record.scene_id = caseDoc.scene_id;
  record.component_id = caseDoc.component_id;

  const kind = caseDoc.transformation.kind;
  if (kind !== "semantic_change" && caseDoc.transformation.interval === null) {
    return refuse(
      "MG_SCHEMA_INVALID",
      `transformation kind ${kind} requires a motion interval`
    );
  }

  // ----- Phase A2: artifact presence and binding. -----
  if (!existsSync(inputs.videoPath)) {
    return refuse("MG_INPUT_MISSING", `video not found: ${inputs.videoPath}`);
  }
  if (!existsSync(inputs.coverageRecordPath)) {
    return refuse(
      "MG_INPUT_MISSING",
      `coverage record not found: ${inputs.coverageRecordPath}`
    );
  }
  let coverage: CoverageRecordShape;
  try {
    coverage = JSON.parse(
      readFileSync(inputs.coverageRecordPath, "utf8")
    ) as CoverageRecordShape;
  } catch (err) {
    return refuse(
      "MG_INPUT_MISSING",
      `coverage record is not readable JSON: ${(err as Error).message}`
    );
  }
  const videoSha = sha256File(inputs.videoPath);
  record.bindings.video_sha256 = videoSha;
  record.bindings.coverage_job_id = coverage.job_id ?? null;
  record.bindings.coverage_verdict = coverage.verdict ?? null;
  const reviewRecord = coverage.inputs?.review_record ?? null;
  record.bindings.review_label = reviewRecord?.label ?? null;
  record.bindings.review_engine = reviewRecord?.engine ?? null;

  if (!coverage.video?.sha256 || coverage.video.sha256 !== videoSha) {
    return refuse(
      "MG_HASH_MISMATCH",
      `coverage record binds video sha256 ${coverage.video?.sha256 ?? "(none)"}, ` +
        `but the artifact under test hashes to ${videoSha}`
    );
  }
  if (coverage.job_id !== caseDoc.job_id) {
    return refuse(
      "MG_FOREIGN_JOB",
      `coverage record names job "${coverage.job_id ?? "(none)"}", ` +
        `but the case names job "${caseDoc.job_id}"`
    );
  }

  let probe: ReturnType<typeof probeVideoFile>;
  try {
    probe = probeVideoFile(inputs.videoPath);
  } catch (err) {
    return refuse(
      "MG_INPUT_MISSING",
      `artifact under test cannot be probed as video: ${(err as Error).message}`
    );
  }

  // ----- Phase B: gates. Any gate finding ends the evaluation before
  // measurement; the reported category is the earliest blocking class.
  const gateFindings: MotionFinding[] = [];
  const claimsDepth = caseDoc.transformation.claims_depth || kind === "depth_transit";
  if (claimsDepth) {
    const evidence = caseDoc.evidence_required;
    if (!evidence.includes("occlusion") && !evidence.includes("depth")) {
      gateFindings.push({
        category: "MG_CAPABILITY_UNSUPPORTED",
        message:
          "this case claims depth (front/back or perspective), and a depth claim " +
          "requires occlusion or depth evidence (catalog C10 minimum proof: " +
          "occlusion/perspective evidence plus readable final composition); the " +
          "evidence plan provides neither, so the claim cannot pass",
      });
    } else if (!evidence.includes("occlusion")) {
      gateFindings.push({
        category: "MG_CAPABILITY_UNSUPPORTED",
        message:
          "depth-map evidence is not an implemented measurement family in this " +
          "evaluator; occlusion evidence is the supported depth path, and this " +
          "case does not provide it",
      });
    } else if (
      !caseDoc.occlusion_checkpoints ||
      caseDoc.occlusion_checkpoints.length < 3
    ) {
      gateFindings.push({
        category: "MG_CAPABILITY_UNSUPPORTED",
        message:
          "the case requires occlusion evidence but declares fewer than three " +
          "occlusion checkpoints (before, during, and after the occlusion are " +
          "all required); the depth claim cannot be evaluated",
      });
    } else {
      const ordered = [...caseDoc.occlusion_checkpoints].sort(
        (a, b) => a.frame - b.frame
      );
      if (
        ordered[0].expected_visible_fraction < 0.95 ||
        ordered[ordered.length - 1].expected_visible_fraction < 0.95
      ) {
        gateFindings.push({
          category: "MG_SCHEMA_INVALID",
          message:
            "occlusion checkpoints must begin and end with the subject (nearly) " +
            "fully visible (expected_visible_fraction >= 0.95); a dip is only " +
            "depth evidence against full visibility on both sides",
        });
      }
    }
  }

  if (coverage.verdict !== "complete") {
    gateFindings.push({
      category: "MG_COVERAGE_INCOMPLETE",
      message:
        `the MG-031 coverage record's verdict is "${coverage.verdict ?? "(none)"}", ` +
        `not "complete"; an assertion built on an incomplete bundle cannot pass` +
        (coverage.findings && coverage.findings.length > 0
          ? `: ${coverage.findings.join("; ")}`
          : ""),
    });
  }
  const samples = coverage.samples ?? [];
  const bundleDir = dirname(inputs.coverageRecordPath);
  for (const checkpoint of caseDoc.checkpoints) {
    const sample = samples.find((s) => s.frame === checkpoint.frame);
    if (!sample || sample.status !== "extracted") {
      gateFindings.push({
        category: "MG_COVERAGE_INCOMPLETE",
        message:
          `checkpoint frame ${checkpoint.frame} (${checkpoint.role}) has no extracted ` +
          "sample in the coverage record; the bundle never captured the state the " +
          "assertion must judge",
      });
    } else if (sample.files?.full) {
      const fullPath = join(bundleDir, sample.files.full);
      if (!existsSync(fullPath)) {
        gateFindings.push({
          category: "MG_COVERAGE_INCOMPLETE",
          message:
            `the coverage record lists frame ${checkpoint.frame} as extracted to ` +
            `${sample.files.full}, but that file does not exist`,
        });
      }
    }
  }
  if (
    reviewRecord &&
    (reviewRecord.label === "rough_layout_only" ||
      reviewRecord.rough_layout_only === true) &&
    caseDoc.evidence_required.includes("full_fps_clip")
  ) {
    gateFindings.push({
      category: "MG_COVERAGE_INCOMPLETE",
      message:
        "the bound review record is labeled rough_layout_only; reduced-frame-rate " +
        "evidence is layout evidence and cannot satisfy a full-fps motion claim",
    });
  }

  const humanMode = caseDoc.judgment.mode === "human";
  const humanVerdict: HumanVerdict | null = inputs.humanVerdict ?? null;
  if (humanMode && humanVerdict === null) {
    gateFindings.push({
      category: "MG_INPUT_MISSING",
      message:
        `case "${caseDoc.id}" routes to human judgment` +
        (caseDoc.judgment.reason ? ` (${caseDoc.judgment.reason})` : "") +
        ", and no human verdict record was supplied; the evaluator will not " +
        "fabricate one",
    });
  }

  if (gateFindings.length > 0) {
    findings.push(...gateFindings);
    const sorted = [...gateFindings].sort(
      (a, b) => classRank(a.category) - classRank(b.category)
    );
    const chosen = sorted[0];
    if (
      gateFindings.length === 1 &&
      humanMode &&
      humanVerdict === null &&
      chosen.category === "MG_INPUT_MISSING"
    ) {
      return finish("needs_human_judgment", chosen.category);
    }
    const verdict: MotionVerdict =
      (EXIT_BY_CATEGORY[chosen.category] ?? 6) <= 3 ? "refused" : "fail";
    return finish(verdict, chosen.category);
  }

  // ----- Human judgment, with a verdict record attached. -----
  if (humanMode && humanVerdict !== null) {
    const approved = humanVerdict.decision === "approved";
    record.assertions = caseDoc.checkpoints.map((checkpoint) => ({
      role: checkpoint.role,
      frame: checkpoint.frame,
      expected: [],
      geometry_measured: null,
      raster_measured: null,
      verdict: approved ? "pass" : "fail",
      detail:
        `decided by human verdict from reviewer "${humanVerdict.reviewer_id}" ` +
        `at ${humanVerdict.reviewed_at} (decision: ${humanVerdict.decision}); ` +
        "semantic case, not automated measurement" +
        (humanVerdict.note ? `; note: ${humanVerdict.note}` : ""),
    }));
    if (!approved) {
      findings.push({
        category: "MG_FAKE_MOTION",
        message: `human reviewer "${humanVerdict.reviewer_id}" rejected the motion claim for case "${caseDoc.id}"`,
      });
      return finish("fail", "MG_FAKE_MOTION");
    }
    return finish("pass", null);
  }

  // ----- Phase C: measurement. Family dispatch is by the scene
  // specification source supplied with the invocation. -----
  const geometryTol = caseDoc.tolerances?.geometry_px ?? 1;
  const decodedTol = caseDoc.tolerances?.decoded_px ?? 2;
  const positionTol = caseDoc.tolerances?.position_px ?? 48;
  const fractionTol = caseDoc.tolerances?.visible_fraction ?? 0.12;

  interface FamilyOutcome {
    assertions: CheckpointAssertion[];
    regions: SourceBox[];
  }
  type FamilyResult =
    | { refusal: MotionFinding }
    | { outcome: FamilyOutcome };

  const checkpointByRole = (role: string) =>
    caseDoc.checkpoints.find((c) => c.role === role);

  function evaluateBars(geo: BarsGeometry): FamilyResult {
    // The case must describe the specification's own subjects and
    // motion interval; anything else grades the wrong beat.
    const caseSubjects = [...caseDoc.subjects.map((s) => s.id)].sort();
    const specSubjects = [...geo.subjectIds].sort();
    if (JSON.stringify(caseSubjects) !== JSON.stringify(specSubjects)) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            `case subjects [${caseSubjects.join(", ")}] do not match the scene ` +
            `specification's subjects [${specSubjects.join(", ")}]`,
        },
      };
    }
    const interval = caseDoc.transformation.interval;
    if (
      interval &&
      (interval.start_frame !== geo.motionInterval.start_frame ||
        interval.end_frame_exclusive !== geo.motionInterval.end_frame_exclusive)
    ) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            `case motion interval [${interval.start_frame}, ${interval.end_frame_exclusive}) ` +
            `disagrees with the scene specification's [${geo.motionInterval.start_frame}, ` +
            `${geo.motionInterval.end_frame_exclusive})`,
        },
      };
    }
    // Cross-check: the scene's declared assertions against the
    // independent derivation from dataset and design.
    for (const declared of geo.sceneAssertions) {
      const derived = geo.expectedWidthsAt(declared.frame);
      const mismatch = derived.some(
        (v, i) => Math.abs(v - declared.expected_values[i]) > declared.tolerance
      );
      if (mismatch) {
        return {
          refusal: {
            category: "MG_SCHEMA_INVALID",
            message:
              `scene assertion "${declared.id}" at frame ${declared.frame} declares ` +
              `[${declared.expected_values.join(", ")}], but the dataset and design ` +
              `derive [${derived.join(", ")}]: the specification contradicts itself`,
          },
        };
      }
    }

    const rasterByFrame = new Map<number, number[]>();
    const assertions: CheckpointAssertion[] = [];
    for (const checkpoint of caseDoc.checkpoints) {
      const expected = geo.expectedWidthsAt(checkpoint.frame);
      const geometry = geo.widthsAt(checkpoint.frame);
      const rgb = decodeFrameRgb(
        inputs.videoPath,
        checkpoint.frame,
        probe.width,
        probe.height
      );
      const raster = geo.regions.map((region) =>
        measureBarWidthInRegion(rgb, probe.width, region, geo.accent)
      );
      rasterByFrame.set(checkpoint.frame, raster);
      const problems: string[] = [];
      geometry.forEach((v, i) => {
        if (Math.abs(v - expected[i]) > geometryTol) {
          problems.push(
            `subject ${geo.subjectIds[i]}: component geometry ${v} disagrees with the spec derivation ${expected[i]}`
          );
        }
      });
      raster.forEach((v, i) => {
        if (Math.abs(v - expected[i]) > decodedTol) {
          problems.push(
            `subject ${geo.subjectIds[i]}: decoded width ${v}px, expected ${expected[i]}px (tolerance ${decodedTol})`
          );
        }
      });
      assertions.push({
        role: checkpoint.role,
        frame: checkpoint.frame,
        expected,
        geometry_measured: geometry,
        raster_measured: raster,
        verdict: problems.length === 0 ? "pass" : "fail",
        detail:
          problems.length === 0
            ? `bar widths agree three ways at frame ${checkpoint.frame}: spec derivation, component geometry, and decoded raster all read [${raster.join(", ")}]`
            : problems.join("; "),
      });
    }
    // Temporal evidence: the subjects themselves must move between
    // the initial and proof states. A frame can change everywhere
    // else (headline, background, decoration) and still fail here.
    const initial = checkpointByRole("initial");
    const proofCp = checkpointByRole("proof");
    const finalCp = checkpointByRole("final");
    const holdCp = checkpointByRole("hold");
    if (initial && proofCp && finalCp) {
      const atInitial = rasterByFrame.get(initial.frame) ?? [];
      const atProof = rasterByFrame.get(proofCp.frame) ?? [];
      const expectedFinal = geo.expectedWidthsAt(finalCp.frame);
      const proofAssertion = assertions.find((a) => a.frame === proofCp.frame);
      geo.subjectIds.forEach((subjectId, i) => {
        if (expectedFinal[i] > 0 && !(atProof[i] > atInitial[i])) {
          if (proofAssertion && proofAssertion.verdict === "pass") {
            proofAssertion.verdict = "fail";
          }
          if (proofAssertion) {
            proofAssertion.detail +=
              `; subject ${subjectId} did not move between the initial and proof ` +
              `states (decoded ${atInitial[i]}px -> ${atProof[i]}px): the chart is ` +
              "static at this checkpoint whatever else in the frame is moving";
          }
        }
      });
    }
    if (finalCp && holdCp) {
      const atFinal = rasterByFrame.get(finalCp.frame) ?? [];
      const atHold = rasterByFrame.get(holdCp.frame) ?? [];
      const holdAssertion = assertions.find((a) => a.frame === holdCp.frame);
      atFinal.forEach((v, i) => {
        if (Math.abs(atHold[i] - v) > decodedTol) {
          if (holdAssertion) {
            holdAssertion.verdict = "fail";
            holdAssertion.detail +=
              `; subject ${geo.subjectIds[i]} does not hold its final state ` +
              `(${v}px at the final checkpoint, ${atHold[i]}px at the hold checkpoint)`;
          }
        }
      });
    }
    return { outcome: { assertions, regions: geo.regions } };
  }

  function evaluateTransit(geo: TransitGeometry): FamilyResult {
    if (
      caseDoc.subjects.length !== 1 ||
      caseDoc.subjects[0].id !== geo.subjectId
    ) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            `case subjects [${caseDoc.subjects.map((s) => s.id).join(", ")}] do not ` +
            `match the mechanism's traveling subject "${geo.subjectId}"`,
        },
      };
    }
    const interval = caseDoc.transformation.interval;
    if (
      interval &&
      (interval.start_frame !== geo.motionInterval.start_frame ||
        interval.end_frame_exclusive !== geo.motionInterval.end_frame_exclusive)
    ) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            `case motion interval [${interval.start_frame}, ${interval.end_frame_exclusive}) ` +
            `disagrees with the mechanism's [${geo.motionInterval.start_frame}, ` +
            `${geo.motionInterval.end_frame_exclusive})`,
        },
      };
    }
    for (const declared of geo.sceneAssertions) {
      const pos = geo.positionAt(declared.frame);
      if (
        !pos ||
        Math.abs(pos.x - declared.expected_values[0]) > declared.tolerance ||
        Math.abs(pos.y - declared.expected_values[1]) > declared.tolerance
      ) {
        return {
          refusal: {
            category: "MG_SCHEMA_INVALID",
            message:
              `scene assertion "${declared.id}" at frame ${declared.frame} declares ` +
              `the subject at [${declared.expected_values.join(", ")}], but the ` +
              `resolved frame functions place it at ` +
              `${pos ? `[${round2(pos.x)}, ${round2(pos.y)}]` : "(no position)"}: ` +
              "the specification contradicts itself",
          },
        };
      }
    }

    const assertions: CheckpointAssertion[] = [];
    const centroids = new Map<number, { x: number; y: number } | null>();
    for (const checkpoint of caseDoc.checkpoints) {
      const pos = geo.positionAt(checkpoint.frame);
      if (!pos) {
        return {
          refusal: {
            category: "MG_SCHEMA_INVALID",
            message: `the mechanism's subject has no position at checkpoint frame ${checkpoint.frame}`,
          },
        };
      }
      const declared = geo.sceneAssertions.find(
        (a) => a.frame === checkpoint.frame
      );
      const expected = declared
        ? [...declared.expected_values]
        : [round2(pos.x), round2(pos.y)];
      const rgb = decodeFrameRgb(
        inputs.videoPath,
        checkpoint.frame,
        probe.width,
        probe.height
      );
      // The subject's raster color comes from the case's declared
      // appearance when present; the diagrams composition paints its
      // traveling marker in its accent constant otherwise.
      const subjectColor = caseDoc.subject_appearance?.color ?? "#C04A26";
      const centroid = accentCentroidInWindow(
        rgb,
        probe.width,
        probe.height,
        pos,
        positionTol * 3 + 60,
        subjectColor
      );
      centroids.set(
        checkpoint.frame,
        centroid ? { x: centroid.x, y: centroid.y } : null
      );
      const problems: string[] = [];
      if (!centroid) {
        problems.push(
          "the subject was not found in the decoded frame inside its subject window"
        );
      } else {
        if (centroid.pixels < 200) {
          problems.push(
            `the subject marker is barely visible (${centroid.pixels} matching px in its window)`
          );
        }
        const distance = Math.hypot(centroid.x - pos.x, centroid.y - pos.y);
        if (distance > positionTol) {
          problems.push(
            `decoded subject centroid (${round2(centroid.x)}, ${round2(centroid.y)}) is ` +
              `${round2(distance)}px from the geometry position (${round2(pos.x)}, ${round2(pos.y)}), tolerance ${positionTol}`
          );
        }
      }
      assertions.push({
        role: checkpoint.role,
        frame: checkpoint.frame,
        expected,
        geometry_measured: [round2(pos.x), round2(pos.y)],
        raster_measured: centroid
          ? [round2(centroid.x), round2(centroid.y)]
          : null,
        verdict: problems.length === 0 ? "pass" : "fail",
        detail:
          problems.length === 0
            ? `subject "${geo.subjectId}" confirmed at (${round2(pos.x)}, ${round2(pos.y)}) in the decoded frame at frame ${checkpoint.frame}`
            : problems.join("; "),
      });
    }
    // Temporal evidence: the derived arc increases through the
    // mechanism, and the raster centroid actually travels with it.
    const ordered = [...caseDoc.checkpoints].sort((a, b) => a.frame - b.frame);
    for (let i = 1; i < ordered.length; i += 1) {
      const prev = ordered[i - 1];
      const curr = ordered[i];
      const assertion = assertions.find((a) => a.frame === curr.frame);
      if (!(geo.arcAt(curr.frame) > geo.arcAt(prev.frame))) {
        if (assertion) {
          assertion.verdict = "fail";
          assertion.detail +=
            `; the derived subject arc does not increase between frames ` +
            `${prev.frame} and ${curr.frame}: the mechanism does not progress`;
        }
      }
      const cPrev = centroids.get(prev.frame);
      const cCurr = centroids.get(curr.frame);
      if (cPrev && cCurr) {
        const traveled = Math.hypot(cCurr.x - cPrev.x, cCurr.y - cPrev.y);
        if (traveled <= positionTol / 2 && assertion) {
          assertion.verdict = "fail";
          assertion.detail +=
            `; the decoded subject moved only ${round2(traveled)}px between frames ` +
            `${prev.frame} and ${curr.frame}: the raster subject is effectively static`;
        }
      }
    }
    const regions: SourceBox[] = caseDoc.checkpoints.map((checkpoint) => {
      const pos = geo.positionAt(checkpoint.frame) ?? { x: 0, y: 0 };
      return { x: pos.x - 90, y: pos.y - 90, width: 180, height: 180 };
    });
    return { outcome: { assertions, regions } };
  }

  function evaluateOcclusion(): FamilyResult {
    const region = caseDoc.subject_region;
    const appearance = caseDoc.subject_appearance;
    if (!region || !appearance) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            "a depth_transit case must declare subject_region and subject_appearance " +
            "so the subject can be identified inside its region in the raster",
        },
      };
    }
    const occ = [...(caseDoc.occlusion_checkpoints ?? [])].sort(
      (a, b) => a.frame - b.frame
    );
    const occFrames = new Set(occ.map((o) => o.frame));
    const caseFrames = new Set(caseDoc.checkpoints.map((c) => c.frame));
    if (
      occFrames.size !== caseFrames.size ||
      [...occFrames].some((f) => !caseFrames.has(f))
    ) {
      return {
        refusal: {
          category: "MG_SCHEMA_INVALID",
          message:
            "the case checkpoints and the occlusion checkpoints must observe the " +
            "same frames (before, during, and after the occlusion)",
        },
      };
    }
    const counts = new Map<number, number>();
    for (const o of occ) {
      const rgb = decodeFrameRgb(inputs.videoPath, o.frame, probe.width, probe.height);
      counts.set(o.frame, accentCountInBox(rgb, probe.width, region, appearance.color));
    }
    const reference = counts.get(occ[0].frame) ?? 0;
    const roleByFrame = new Map(
      caseDoc.checkpoints.map((c) => [c.frame, c.role])
    );
    const assertions: CheckpointAssertion[] = [];
    record.occlusion = occ.map((o) => {
      const count = counts.get(o.frame) ?? 0;
      const measured = reference > 0 ? count / reference : null;
      const pass =
        measured !== null &&
        Math.abs(measured - o.expected_visible_fraction) <= fractionTol;
      return {
        frame: o.frame,
        subject_id: o.subject_id,
        occluder_id: o.occluder_id,
        expected_visible_fraction: o.expected_visible_fraction,
        measured_visible_fraction: measured === null ? null : round2(measured),
        verdict: (pass ? "pass" : "fail") as "pass" | "fail",
      };
    });
    for (const o of occ) {
      const obs = record.occlusion.find((r) => r.frame === o.frame);
      assertions.push({
        role: roleByFrame.get(o.frame) ?? "proof",
        frame: o.frame,
        expected: [o.expected_visible_fraction],
        geometry_measured: null,
        raster_measured: obs?.measured_visible_fraction === null || obs?.measured_visible_fraction === undefined
          ? null
          : [obs.measured_visible_fraction],
        verdict: obs?.verdict ?? "fail",
        detail:
          reference === 0
            ? "the subject is not visible at the reference frame, so no visibility fraction can be measured"
            : `visible fraction of subject "${o.subject_id}" inside its region at frame ${o.frame}: ` +
              `expected ${o.expected_visible_fraction}, measured ${obs?.measured_visible_fraction} ` +
              `(occluder "${o.occluder_id}"; a subject drawn in front of the occluder would measure about 1.0 throughout)`,
      });
    }
    return { outcome: { assertions, regions: [region] } };
  }

  let family: FamilyResult;
  try {
    if (kind === "semantic_change") {
      family = {
        refusal: {
          category: "MG_CAPABILITY_UNSUPPORTED",
          message:
            "transformation kind semantic_change names a judgment automation must " +
            "not fabricate; declare judgment mode \"human\" for this case",
        },
      };
    } else if (kind === "depth_transit") {
      family = evaluateOcclusion();
    } else if (kind === "linear_reveal") {
      if (!inputs.jobDir) {
        family = {
          refusal: {
            category: "MG_INPUT_MISSING",
            message:
              "a linear_reveal case needs its scene specification: no job directory " +
              "was supplied with the evaluation",
          },
        };
      } else {
        family = evaluateBars(deriveBarsGeometry(inputs.jobDir));
      }
    } else {
      // path_transit
      if (!inputs.diagramScenePath) {
        family = {
          refusal: {
            category: "MG_INPUT_MISSING",
            message:
              "a path_transit case needs its scene specification: no diagram scene " +
              "document was supplied with the evaluation",
          },
        };
      } else {
        family = evaluateTransit(
          deriveTransitGeometry(
            inputs.diagramScenePath,
            inputs.fontPath ??
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
          )
        );
      }
    }
  } catch (err) {
    return refuse(
      "MG_ENCODE_FAILED",
      `proof extraction failed during measurement: ${(err as Error).message}`
    );
  }
  if ("refusal" in family) {
    return refuse(family.refusal.category, family.refusal.message);
  }
  const { assertions, regions } = family.outcome;
  record.assertions = assertions;

  // ----- Phase D: proof package extraction (checkpoint frames and
  // the full-fps clip around the action). -----
  try {
    const framesDir = join(inputs.outputDir, "frames");
    mkdirSync(framesDir, { recursive: true });
    const framesToExtract = [
      ...new Set(caseDoc.checkpoints.map((c) => c.frame)),
    ].sort((a, b) => a - b);
    for (const frame of framesToExtract) {
      const name = `f${frame}.png`;
      extractPng(inputs.videoPath, frame, join(framesDir, name));
      record.frames.push({
        frame,
        path: `frames/${name}`,
        sha256: sha256File(join(framesDir, name)),
      });
    }

    if (caseDoc.evidence_required.includes("full_fps_clip")) {
      const interval = caseDoc.transformation.interval;
      if (interval) {
        const clipPath = join(inputs.outputDir, "clip.mp4");
        extractClip(
          inputs.videoPath,
          interval.start_frame,
          interval.end_frame_exclusive,
          probe.fpsNumerator,
          probe.fpsDenominator,
          clipPath
        );
        const clipProbe = probeVideoFile(clipPath);
        record.clip = {
          path: "clip.mp4",
          frames: clipProbe.frameCount,
          fps: `${clipProbe.fpsNumerator}/${clipProbe.fpsDenominator}`,
          sha256: sha256File(clipPath),
        };
        const expectedFrames = interval.end_frame_exclusive - interval.start_frame;
        if (
          clipProbe.frameCount !== expectedFrames ||
          clipProbe.fpsNumerator !== probe.fpsNumerator ||
          clipProbe.fpsDenominator !== probe.fpsDenominator
        ) {
          findings.push({
            category: "MG_COVERAGE_INCOMPLETE",
            message:
              `the full-fps clip over [${interval.start_frame}, ${interval.end_frame_exclusive}) ` +
              `holds ${clipProbe.frameCount} frames at ${clipProbe.fpsNumerator}/${clipProbe.fpsDenominator}, ` +
              `expected ${expectedFrames} frames at ${probe.fpsNumerator}/${probe.fpsDenominator}: ` +
              "the artifact does not contain the action at full frame rate",
          });
        }
      }
    }

    const initialCp = checkpointByRole("initial");
    const finalCp = checkpointByRole("final");
    if (initialCp && finalCp && initialCp.frame !== finalCp.frame) {
      const a = decodeFrameRgb(inputs.videoPath, initialCp.frame, probe.width, probe.height);
      const b = decodeFrameRgb(inputs.videoPath, finalCp.frame, probe.width, probe.height);
      record.context_change = {
        mean_abs_diff: round2(
          meanAbsDiffOutsideRegions(a, b, probe.width, probe.height, regions)
        ),
        frames: [initialCp.frame, finalCp.frame],
      };
    }
  } catch (err) {
    return refuse(
      "MG_ENCODE_FAILED",
      `proof extraction failed: ${(err as Error).message}`
    );
  }

  // ----- Phase E: verdict assembly. -----
  const failedAssertions = record.assertions.filter((a) => a.verdict === "fail");
  if (failedAssertions.length > 0) {
    findings.push({
      category: "MG_FAKE_MOTION",
      message:
        `${failedAssertions.length} checkpoint assertion(s) failed: the named subject ` +
        "did not perform the declared transformation in the rendered frames",
    });
    return finish("fail", "MG_FAKE_MOTION");
  }
  if (findings.length > 0) {
    return finish("fail", findings[0].category);
  }
  return finish("pass", null);
}
