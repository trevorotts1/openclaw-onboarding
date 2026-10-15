// Expected-geometry derivation for motion proof (Directive MG-032).
// Expectations are DERIVED from the scene specification, never copied
// from the case document: for chart components, from the job's dataset
// and design records through the shared scale the renderer itself
// uses; for diagram components, from the resolved frame functions the
// composition renders with. The scene's own declared semantic
// assertions are cross-checked against the derivation, so a scene
// specification that lies about its expectations is caught as a
// contract inconsistency instead of grading the render against the
// lie.

import { readFileSync } from "node:fs";
import { loadValidatedJob } from "../adapters";
import { barGeometry, clampProgress, revealWidth } from "../charts/scale";
import {
  FontTextMeasurer,
  resolveDiagram,
  subjectArcAt,
  subjectPositionAt,
  type DiagramSceneDoc,
} from "../diagrams";
import {
  barSubjectIds,
  instrumentedBarWidths,
  loadC05Job,
} from "../remotion/job-props";
import type { SourceBox } from "./types";

export interface SceneAssertionFact {
  id: string;
  kind: string;
  frame: number;
  expected_values: number[];
  tolerance: number;
}

export interface BarsGeometry {
  family: "bars";
  subjectIds: string[];
  /** The subject color, from the job design record. */
  accent: string;
  canvas: { width: number; height: number; fps: number };
  /** One subject region per subject id, in dataset row order. */
  regions: SourceBox[];
  /** Bar widths from the component's own instrumented frame
   * functions (the "geometry" evidence: what the renderer computed). */
  widthsAt(frame: number): number[];
  /** Bar widths derived independently from the dataset and design
   * records through the MG-015 chart scale (the expectation: what the
   * scene specification requires). A separate code path from the
   * component's frame math, arithmetically aligned by design. */
  expectedWidthsAt(frame: number): number[];
  /** The scene's own declared bar_widths assertions, for the
   * derivation cross-check. */
  sceneAssertions: SceneAssertionFact[];
  motionInterval: { start_frame: number; end_frame_exclusive: number };
}

export function deriveBarsGeometry(jobDir: string): BarsGeometry {
  const job = loadValidatedJob(jobDir);
  const loaded = loadC05Job(job);
  const props = loaded.props;
  const layout = props.design.layout;
  const subjectIds = barSubjectIds(props);
  const regions = subjectIds.map((_, i) => ({
    x: layout.plot.x,
    y: layout.row_y[i],
    width: layout.plot.width,
    height: layout.bar_height,
  }));
  const sceneAssertions: SceneAssertionFact[] = (
    loaded.scene.semantic_motion_assertions ?? []
  )
    .filter((a) => a.kind === "bar_widths")
    .map((a) => ({
      id: a.id,
      kind: a.kind,
      frame: a.frame,
      expected_values: [...a.expected_values],
      tolerance: a.tolerance,
    }));
  const { startFrame, endFrameExclusive, authoredFps } = props.motion;
  const renderFps = props.canvas.fps;
  // Reveal progress in seconds, mirroring the frame-math convention:
  // the motion interval is authored at authoredFps and the render runs
  // at the canvas fps; the fixture family authors and renders at 30.
  const progressAt = (frame: number): number => {
    const t = frame / renderFps;
    const startT = startFrame / authoredFps;
    const endT = endFrameExclusive / authoredFps;
    return clampProgress((t - startT) / (endT - startT));
  };
  return {
    family: "bars",
    subjectIds,
    accent: props.design.colors.accent,
    canvas: { ...props.canvas },
    regions,
    widthsAt: (frame: number) => instrumentedBarWidths(props, frame),
    expectedWidthsAt: (frame: number) =>
      props.dataset.rows.map((row) =>
        revealWidth(
          barGeometry(row.value, props.dataset.domain, layout.plot.width).width,
          progressAt(frame)
        )
      ),
    sceneAssertions,
    motionInterval: {
      start_frame: props.motion.startFrame,
      end_frame_exclusive: props.motion.endFrameExclusive,
    },
  };
}

export interface TransitGeometry {
  family: "subject_transit";
  subjectId: string;
  canvas: { width: number; height: number; fps: number };
  /** Derived subject position (source px) at a frame; null when the
   * subject has no position there. */
  positionAt(frame: number): { x: number; y: number } | null;
  /** Derived arc length along the subject path at a frame. */
  arcAt(frame: number): number;
  /** The scene's own declared subject_identity assertions. */
  sceneAssertions: SceneAssertionFact[];
  motionInterval: { start_frame: number; end_frame_exclusive: number };
}

export function deriveTransitGeometry(
  scenePath: string,
  fontPath: string
): TransitGeometry {
  const doc = JSON.parse(readFileSync(scenePath, "utf8")) as DiagramSceneDoc;
  const measurer = new FontTextMeasurer(fontPath);
  const result = resolveDiagram(doc.diagram, measurer);
  if (!result.ok) {
    throw new Error(
      `diagram scene ${scenePath} does not resolve: ${JSON.stringify(result.findings)}`
    );
  }
  const resolved = result.resolved;
  if (!resolved.subject) {
    throw new Error(`diagram scene ${scenePath} has no traveling subject`);
  }
  const sceneAssertions: SceneAssertionFact[] = (
    doc.semantic_motion_assertions ?? []
  )
    .filter((a) => a.kind === "subject_identity")
    .map((a) => ({
      id: a.id,
      kind: a.kind,
      frame: a.frame,
      expected_values: [...a.expected_values],
      tolerance: a.tolerance,
    }));
  return {
    family: "subject_transit",
    subjectId: resolved.subject.id,
    canvas: { ...doc.diagram.canvas },
    positionAt: (frame: number) => subjectPositionAt(resolved, frame),
    arcAt: (frame: number) => subjectArcAt(resolved, frame),
    sceneAssertions,
    motionInterval: {
      start_frame: doc.diagram.timing.start_frame,
      end_frame_exclusive: doc.diagram.timing.end_frame_exclusive,
    },
  };
}
