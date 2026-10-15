// Composition registrations for the MG-016 chart library root.
//
// The production Remotion adapter bundles src/remotion/entry.ts (the
// C05 root in Root.ts). This library root registers the full chart
// library (C05 plus the MG-016 components C06-C08) under the same
// discipline: one composition per component, metadata CALCULATED from
// the input props, and default props that deliberately carry no font
// files, so a render attempted without real input props fails at the
// font gate instead of silently substituting a font. The MG-016 test
// runner bundles this root to render the new components; wiring these
// registrations into the production root belongs to the integration
// step recorded in the MG-016 notes (Root.ts is outside MG-016's file
// claims).

import { createElement } from "react";
import { Composition } from "remotion";
import type { ChartDataset } from "../../charts";
import { C05BarChart } from "./C05BarChart";
import { C06LineTrend } from "./C06LineTrend";
import { C07StackedAllocation } from "./C07StackedAllocation";
import { C08Waterfall } from "./C08Waterfall";
import { C05_COMPOSITION_ID } from "../frame-math";
import type { C05Props } from "../job-props";
import type { ChartSceneProps, C06Props, C07Props, C08Props } from "./chart-props";

export const C06_COMPOSITION_ID = "C06";
export const C07_COMPOSITION_ID = "C07";
export const C08_COMPOSITION_ID = "C08";

const DEFAULT_DATASET: ChartDataset = {
  schema_version: "2.0",
  id: "unregistered-default",
  kind: "illustrative",
  source_note: "Registration default only; never rendered without real input props.",
  units: "items",
  domain: [0, 10],
  scale_type: "linear",
  missing_value_policy: "error",
  display_rounding: { decimals: 0 },
  rows: [{ id: "a", label: "A", value: 10 }],
};

function defaultChartProps(componentId: string): ChartSceneProps {
  return {
    jobId: "unregistered-default",
    sceneId: `${componentId.toLowerCase()}-default`,
    componentId,
    componentVersion: "1.0.0",
    canvas: { width: 1920, height: 1080, fps: 30 },
    durationFrames: 180,
    layoutVariant: "landscape",
    headline: "Unregistered default",
    disclosure: "Illustrative example",
    dataset: DEFAULT_DATASET,
    design: {
      colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" },
      layout: {
        headline_px: 112,
        label_px: 48,
        value_px: 60,
        disclosure_px: 40,
        plot: { x: 360, y: 300, width: 1320, height: 600 },
        headline_box: { x: 120, y: 90, width: 1680, height: 170 },
      },
    },
    motion: {
      kind: "chart_reveal",
      startFrame: 15,
      endFrameExclusive: 75,
      holdToFrameExclusive: 180,
      authoredFps: 30,
    },
    font: { family: "Liberation Sans", files: [] },
    annotations: [],
    focusRowId: null,
    segmentColors: [],
    contributionColors: null,
  };
}

const C05_DEFAULT_PROPS: C05Props = {
  jobId: "unregistered-default",
  sceneId: "bar-01",
  componentId: "C05",
  componentVersion: "1.0.0",
  canvas: { width: 1920, height: 1080, fps: 30 },
  durationFrames: 180,
  layoutVariant: "landscape",
  headline: "Compare the three groups",
  disclosure: "Illustrative example",
  dataset: {
    domain: [0, 30],
    units: "items",
    rows: [
      { id: "a", label: "Group A", value: 12 },
      { id: "b", label: "Group B", value: 18 },
      { id: "c", label: "Group C", value: 30 },
    ],
  },
  design: {
    colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" },
    layout: {
      headline_px: 112,
      label_px: 64,
      value_px: 72,
      disclosure_px: 48,
      plot: { x: 420, y: 360, width: 1200, height: 440 },
      bar_height: 90,
      row_y: [360, 520, 680],
      headline_box: { x: 120, y: 90, width: 1680, height: 170 },
    },
  },
  motion: {
    kind: "linear_bar_reveal",
    startFrame: 15,
    endFrameExclusive: 75,
    holdToFrameExclusive: 180,
    authoredFps: 30,
  },
  font: { family: "Liberation Sans", files: [] },
};

function chartComposition(
  id: string,
  component: unknown,
  defaultProps: ChartSceneProps
): unknown {
  return createElement(Composition, {
    key: id,
    id,
    component: component as never,
    durationInFrames: defaultProps.durationFrames,
    fps: defaultProps.canvas.fps,
    width: defaultProps.canvas.width,
    height: defaultProps.canvas.height,
    defaultProps,
    calculateMetadata: ({ props }: { props: ChartSceneProps }) => ({
      durationInFrames: props.durationFrames,
      fps: props.canvas.fps,
      width: props.canvas.width,
      height: props.canvas.height,
      props,
    }),
  });
}

export function ChartLibraryRoot(): unknown {
  // An array of compositions (the createElement form of the fragment
  // the JSX root would return; the local react declarations carry no
  // Fragment export).
  return [
    createElement(Composition, {
      key: C05_COMPOSITION_ID,
      id: C05_COMPOSITION_ID,
      component: C05BarChart,
      durationInFrames: C05_DEFAULT_PROPS.durationFrames,
      fps: C05_DEFAULT_PROPS.canvas.fps,
      width: C05_DEFAULT_PROPS.canvas.width,
      height: C05_DEFAULT_PROPS.canvas.height,
      defaultProps: C05_DEFAULT_PROPS,
      calculateMetadata: ({ props }: { props: C05Props }) => ({
        durationInFrames: props.durationFrames,
        fps: props.canvas.fps,
        width: props.canvas.width,
        height: props.canvas.height,
        props,
      }),
    }),
    chartComposition(C06_COMPOSITION_ID, C06LineTrend, defaultChartProps("C06") as C06Props),
    chartComposition(C07_COMPOSITION_ID, C07StackedAllocation, defaultChartProps("C07") as C07Props),
    chartComposition(C08_COMPOSITION_ID, C08Waterfall, defaultChartProps("C08") as C08Props),
  ];
}
