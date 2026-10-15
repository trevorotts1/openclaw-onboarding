// Job loading and input-props construction for the Remotion adapter
// (Directive MG-006). The adapter renders only what the validated job
// files say: scene spec, dataset, and design are read from the job
// directory (paths in the job documents are job-root-relative, Section
// 16.1), the font requirement named by the design is resolved to real
// local bytes, and everything the composition needs is serialized into
// one input-props object. The SAME props object is used to select the
// composition (its metadata is calculated from the props) and to render,
// so composition metadata and render inputs cannot disagree.
//
// Missing files, missing copy, or unsatisfiable font requirements throw
// AdapterError before any render starts: a render that cannot be built
// from the job's own validated inputs fails clearly and claims no
// artifact.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { AdapterError, ValidatedMotionJob } from "../adapters/types";
import type {
  Assets,
  Dataset,
  Design,
  Scene,
} from "../validation/generated-types";
import { barWidthAt, rescaleDurationFrames } from "./frame-math";
import { DEFAULT_FONT_SEARCH_DIRS, resolveFont, ResolvedFont } from "./fonts";

export type LayoutVariant = "landscape" | "portrait";

export interface C05Layout {
  headline_px: number;
  label_px: number;
  value_px: number;
  disclosure_px: number;
  plot: { x: number; y: number; width: number; height: number };
  bar_height: number;
  row_y: number[];
  headline_box: { x: number; y: number; width: number; height: number };
}

/** Serializable input props for the C05 composition. Font bytes travel
 * as base64 so the composition registers the exact resolved files; the
 * sha256 of each file is kept adapter-side in LoadedC05Job.font. */
export interface C05Props {
  jobId: string;
  sceneId: string;
  componentId: "C05";
  componentVersion: string;
  canvas: { width: number; height: number; fps: number };
  durationFrames: number;
  layoutVariant: LayoutVariant;
  headline: string;
  disclosure: string;
  dataset: {
    domain: [number, number];
    units: string;
    rows: { id: string; label: string; value: number }[];
  };
  design: {
    colors: { background: string; ink: string; accent: string };
    layout: C05Layout;
  };
  motion: {
    kind: "linear_bar_reveal";
    startFrame: number;
    endFrameExclusive: number;
    holdToFrameExclusive: number;
    authoredFps: number;
  };
  font: {
    family: string;
    files: { weight: number; base64: string }[];
  };
}

export interface LoadedC05Job {
  scene: Scene;
  dataset: Dataset;
  design: Design;
  layout: C05Layout;
  /** The resolved font, with file paths and hashes for evidence. */
  font: ResolvedFont;
  props: C05Props;
  /** fps the composition renders at (the manifest fps unless a caller
   * explicitly overrides it to demonstrate seconds-based behavior). */
  fps: number;
  /** Duration in frames at the render fps. */
  durationFrames: number;
}

function readJobJson<T>(jobDir: string, rel: string, what: string): T {
  const abs = join(jobDir, rel);
  if (!existsSync(abs)) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Job is missing its ${what} file: ${rel} (job directory ${jobDir}).`,
    });
  }
  try {
    return JSON.parse(readFileSync(abs, "utf8")) as T;
  } catch (err) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Job ${what} file ${rel} is not valid JSON: ${(err as Error).message}`,
    });
  }
}

function requireString(value: unknown, what: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Missing required prop: ${what} must be a non-empty string.`,
    });
  }
  return value;
}

export interface LoadC05Options {
  /** Render at this fps instead of the manifest fps. The scene's
   * seconds-based behavior is preserved (see frame-math). */
  fpsOverride?: number;
  /** Directories searched for font files (tests point this at an empty
   * directory to prove missing fonts fail). */
  fontSearchDirs?: string[];
}

/**
 * Load the (single) C05 scene of a validated job and build its input
 * props. Throws AdapterError for anything the render would need that the
 * job does not provide. Multi-scene programs are assembled by the
 * timeline compiler (MG-021); this adapter renders one C05 scene per
 * composition and says so plainly when a job carries more.
 */
export function loadC05Job(job: ValidatedMotionJob, opts?: LoadC05Options): LoadedC05Job {
  const manifest = job.manifest;
  if (manifest.scenes.length !== 1) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message:
        `Job ${job.jobId} carries ${manifest.scenes.length} scenes; the Remotion adapter ` +
        "renders single-scene C05 jobs in this implementation. Multi-scene program " +
        "assembly belongs to the timeline compiler (MG-021) and is never faked here.",
    });
  }
  const entry = manifest.scenes[0];
  const scene = readJobJson<Scene>(job.jobDir, entry.spec, "scene spec");
  if (scene.component_id !== "C05") {
    throw new AdapterError({
      category: "MG_UNKNOWN_COMPONENT",
      engine: "remotion",
      message: `Scene ${entry.id} declares component "${scene.component_id}"; this adapter implements C05 only.`,
    });
  }
  if (scene.engine !== "remotion") {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Scene ${entry.id} declares engine "${scene.engine}" but was routed to the Remotion adapter.`,
    });
  }
  const dataset = readJobJson<Dataset>(job.jobDir, scene.data_path, "dataset");
  const design = readJobJson<Design>(job.jobDir, scene.design_path, "design");
  const assets = readJobJson<Assets>(job.jobDir, manifest.assets, "assets");

  const headline = requireString(scene.copy?.headline, `scene ${entry.id} copy.headline`);
  const disclosure = requireString(scene.copy?.disclosure, `scene ${entry.id} copy.disclosure`);
  if (!Array.isArray(dataset.rows) || dataset.rows.length === 0) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Dataset ${scene.data_path} has no rows; there is nothing truthful to render.`,
    });
  }
  const domainRaw = dataset.domain as unknown;
  if (
    !Array.isArray(domainRaw) ||
    domainRaw.length !== 2 ||
    typeof domainRaw[0] !== "number" ||
    typeof domainRaw[1] !== "number" ||
    !(domainRaw[0] < domainRaw[1])
  ) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Dataset ${scene.data_path} domain must be two increasing numbers.`,
    });
  }
  const domain: [number, number] = [domainRaw[0], domainRaw[1]];

  const layoutVariant = scene.layout_variant;
  const layout = design.layouts[layoutVariant] as C05Layout | undefined;
  if (!layout) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message: `Design ${scene.design_path} has no layout for variant "${layoutVariant}".`,
    });
  }
  if (layout.row_y.length < dataset.rows.length) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message:
        `Design layout "${layoutVariant}" provides ${layout.row_y.length} row positions ` +
        `for ${dataset.rows.length} dataset rows.`,
    });
  }

  const fontRequirement = assets.font_requirements.find((f) => f.id === design.font_ref);
  if (!fontRequirement) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message:
        `Design references font "${design.font_ref}" but the job's assets document ` +
        `(${manifest.assets}) declares no such font requirement.`,
    });
  }
  const font = resolveFont(
    fontRequirement.id,
    fontRequirement.family_alias,
    [...fontRequirement.weights],
    opts?.fontSearchDirs ?? DEFAULT_FONT_SEARCH_DIRS
  );

  const authoredFps = manifest.canvas.fps;
  const fps = opts?.fpsOverride ?? authoredFps;
  const durationFrames =
    fps === authoredFps
      ? manifest.duration_frames
      : rescaleDurationFrames(manifest.duration_frames, authoredFps, fps);

  const props: C05Props = {
    jobId: job.jobId,
    sceneId: entry.id,
    componentId: "C05",
    componentVersion: scene.component_version,
    canvas: { width: manifest.canvas.width, height: manifest.canvas.height, fps },
    durationFrames,
    layoutVariant,
    headline,
    disclosure,
    dataset: {
      domain,
      units: dataset.units,
      rows: dataset.rows.map((r) => ({ id: r.id, label: r.label, value: r.value })),
    },
    design: {
      colors: { ...design.colors },
      layout: {
        headline_px: layout.headline_px,
        label_px: layout.label_px,
        value_px: layout.value_px,
        disclosure_px: layout.disclosure_px,
        plot: { ...layout.plot },
        bar_height: layout.bar_height,
        row_y: [...layout.row_y],
        headline_box: { ...layout.headline_box },
      },
    },
    motion: {
      kind: scene.motion.kind,
      startFrame: scene.motion.start_frame,
      endFrameExclusive: scene.motion.end_frame_exclusive,
      holdToFrameExclusive: scene.motion.hold_to_frame_exclusive,
      authoredFps,
    },
    font: {
      family: font.family,
      files: font.files.map((f) => ({ weight: f.weight, base64: f.base64 })),
    },
  };

  return { scene, dataset, design, layout: props.design.layout, font, props, fps, durationFrames };
}

/** Subject ids for the scene's bars, in dataset row order ("bar-a", ...),
 * matching the storyboard and the scene's semantic assertions. */
export function barSubjectIds(props: C05Props): string[] {
  return props.dataset.rows.map((r) => `bar-${r.id}`);
}

/** Instrumented geometry: the exact bar widths the component renders at
 * a frame, from the shared scale calculation. */
export function instrumentedBarWidths(props: C05Props, frame: number): number[] {
  return props.dataset.rows.map((row) =>
    barWidthAt(row.value, props.dataset.domain, props.design.layout.plot.width, frame, props.canvas.fps, {
      startFrame: props.motion.startFrame,
      endFrameExclusive: props.motion.endFrameExclusive,
      authoredFps: props.motion.authoredFps,
    })
  );
}
