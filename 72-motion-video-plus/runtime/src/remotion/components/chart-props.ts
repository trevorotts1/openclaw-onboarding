// Input props for the MG-016 chart components (C06 line trend, C07
// stacked allocation, C08 waterfall), following the C05 props pattern:
// one serializable object carries everything a composition needs, the
// composition metadata is calculated from the same props, and the font
// bytes travel as base64 so the exact resolved files are what render.
//
// The dataset prop is a full MG-015 ChartDataset (the chart data
// contract, with its declared missing-value policy and display
// rounding), so components format printed values with the dataset's own
// declared rule through charts/format.ts. The canonical contracts
// scene schema is closed on C05 today, so C06-C08 scene documents are
// validated by the catalog entries in runtime/src/catalog (c06.ts,
// c07.ts, c08.ts) rather than the contracts layer; the props below are
// what a loader builds from one of those scene documents plus its
// dataset and design records. Promotion of the C06-C08 scene shapes
// into the canonical schema is a contracts-revision item, recorded in
// the MG-016 integration notes.

import type { ChartDataset } from "../../charts";
import type { PlotBox } from "./chart-geometry";

export interface ChartFontProps {
  /** CSS family name the composition registers the faces under. */
  family: string;
  files: { weight: number; base64: string }[];
}

export interface ChartLayoutProps {
  headline_px: number;
  label_px: number;
  value_px: number;
  disclosure_px: number;
  plot: PlotBox;
  headline_box: { x: number; y: number; width: number; height: number };
}

export interface ChartDesignProps {
  colors: { background: string; ink: string; accent: string };
  layout: ChartLayoutProps;
}

/** One annotation pinned to a data row (C06 proof obligation: a
 * specific annotated change, Section 7.1). */
export interface ChartAnnotation {
  id: string;
  rowId: string;
  text: string;
}

export interface ChartMotionProps {
  kind: string;
  startFrame: number;
  endFrameExclusive: number;
  holdToFrameExclusive: number;
  /** The fps the authored frame numbers are expressed at. */
  authoredFps: number;
}

export interface ChartSceneProps {
  jobId: string;
  sceneId: string;
  componentId: string;
  componentVersion: string;
  canvas: { width: number; height: number; fps: number };
  durationFrames: number;
  layoutVariant: "landscape" | "portrait";
  headline: string;
  disclosure: string;
  dataset: ChartDataset;
  design: ChartDesignProps;
  motion: ChartMotionProps;
  font: ChartFontProps;
  /** C06 annotations (empty for C07/C08). */
  annotations: ChartAnnotation[];
  /** Row the final focus settles on; null settles on the most recent
   * mark (C06) or is unused (C07/C08 emphasize by construction). */
  focusRowId: string | null;
  /** C07: the declared color for each segment, in row order. The
   * color/label mapping is data, never inferred (Section 7.1 C07
   * minimum proof). Empty for C06/C08. */
  segmentColors: string[];
  /** C08: declared colors for positive and negative contributions.
   * Null for C06/C07. */
  contributionColors: { positive: string; negative: string } | null;
}

export type C06Props = ChartSceneProps & { componentId: "C06" };
export type C07Props = ChartSceneProps & { componentId: "C07" };
export type C08Props = ChartSceneProps & { componentId: "C08" };
