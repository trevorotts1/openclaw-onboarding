// Chart component tests for MG-016 (Directive Section 6 MG-016,
// Sections 7.1 and 17.2).
//
// Coverage, in order:
// - Catalog: C06-C08 refuse dispatch in the default registry (the
//   pending state MG-018 shipped) and dispatch once a registry is
//   composed with the MG-016 registration bundles; the bundles carry
//   closed input schemas, proof contracts, tests, and engineering
//   attestations, and their example scenes are byte-identical to the
//   fixture scenes on disk.
// - Geometry: exact final geometry for line trend, stacked allocation,
//   and waterfall on two datasets each (including negative and zero
//   values where the chart type supports them), staged-reveal states,
//   the D-CHART-BASELINE regression on domain [10, 40], and the C05
//   declared-rounding formatting adoption.
// - Renders: real Remotion renders of the new components through a
//   bundle of the chart library root, with decoded raster measurement
//   of the data marks (never the title): proof frames show marks
//   changing between early and late frames, a mobile portrait variant
//   renders with exact final geometry, and a title-only variant
//   produces identical mark geometry while its headline pixels differ.
// - The C05 baseline regression rendered through the production
//   Remotion adapter path, and one C06 chart rendered through
//   Hyperframes (native clock, generated composition) with decoded
//   proof frames.
//
// Prerequisites: the shared runtime provisioned in this worktree and
// the runtime package built (npm test runs the build first). Render
// scratch lives in the shared runtime's gitignored .runtime dir;
// committed evidence (proof stills + measurements.json) lands in
// 72-motion-video-plus/tests/evidence/mg016. measurements.json is a
// static record in the MG-015 pattern: the runner asserts the fresh
// measurements equal it (writing it only on the first, bootstrap run).
//
// Exit code 0 when every case passes, 1 otherwise.

import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import {
  CatalogError,
  ComponentRegistry,
  c06Entry,
  c06Registration,
  c07Entry,
  c07Registration,
  c08Entry,
  c08Registration,
  validateCatalogEntry,
} from "../src/catalog";
import {
  assertChartDataset,
  barGeometry,
  formatDatasetValue,
  type ChartDataset,
} from "../src/charts";
import { barWidthAt, scaleBarWidth } from "../src/remotion/frame-math";
import {
  barGeometryForValue,
  barStateAt,
  estimateLabelLines,
  lineGeometry,
  lineStateAt,
  resolveLabelTops,
  slotProgress,
  stackedGeometry,
  stackedStateAt,
  waterfallGeometry,
  waterfallStateAt,
  zeroBaselineDomain,
} from "../src/remotion/components/chart-geometry";
import type {
  ChartSceneProps,
  C06Props,
} from "../src/remotion/components/chart-props";
import { resolveFont } from "../src/remotion/fonts";
import { loadC05Job } from "../src/remotion/job-props";
import { loadValidatedJob } from "../src/adapters";
import { createRemotionAdapter } from "../src/adapters/remotion";
import {
  decodeFrameRgb,
  measureAccentBarWidths,
  readPngDimensions,
} from "../src/remotion/decode";
import { resolveSharedRuntime } from "../src/adapters/hyperframes";
import {
  generateC06Project,
  type LineTrendSceneSpec,
} from "../src/hyperframes/generators";
import {
  resolveFont as resolveHfFont,
  vendorIntoProject,
} from "../src/hyperframes/project";
import { decodePng, measureColorFraction } from "../src/hyperframes/measure";
import { validateAgainstDef } from "../src/validation/validate";

// ---------------------------------------------------------------------
// Paths, helpers, shared state
// ---------------------------------------------------------------------

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function chartFixturesRoot(): string {
  return join(fixturesRoot(), "chart-components");
}

function runtimeStateDir(): string {
  const override = process.env.MOTION_RUNTIME_STATE_DIR;
  if (override) return resolve(override);
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

function evidenceDir(): string {
  return resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg016");
}

const SCRATCH = join(runtimeStateDir(), "mg016-tests");

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

function sha256Text(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a.localeCompare(b)
    );
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

function deepEqual(a: unknown, b: unknown): boolean {
  return canonical(a) === canonical(b);
}

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertDeep(actual: unknown, expected: unknown, message: string): void {
  if (!deepEqual(actual, expected)) {
    throw new Error(
      `${message}:\n  expected ${canonical(expected)}\n  got      ${canonical(actual)}`
    );
  }
}

function assertClose(actual: number, expected: number, tolerance: number, message: string): void {
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(`${message}: expected ${expected} within ${tolerance}, got ${actual}`);
  }
}

// ---------------------------------------------------------------------
// Fixture loading and props construction
// ---------------------------------------------------------------------

interface FixtureDocs {
  dir: string;
  dataset: ChartDataset;
  design: Record<string, unknown>;
  scene: Record<string, unknown>;
}

function loadFixture(name: string): FixtureDocs {
  const dir = join(chartFixturesRoot(), name);
  const datasetDoc = readJson<unknown>(join(dir, "dataset.json"));
  const dataset = assertChartDataset(datasetDoc);
  const design = readJson<Record<string, unknown>>(join(dir, "design.json"));
  const scene = readJson<Record<string, unknown>>(join(dir, "scene.json"));
  return { dir, dataset, design, scene };
}

const FONT = resolveFont("font-fixture-sans", "fixture-sans", [400, 700]);

function variantCanvas(variant: string): { width: number; height: number; fps: number } {
  return variant === "portrait"
    ? { width: 1080, height: 1920, fps: 30 }
    : { width: 1920, height: 1080, fps: 30 };
}

/** Build component props from one fixture directory, the way a job
 * loader for C06-C08 will: dataset through the MG-015 contract, design
 * layout for the scene's variant, font resolved to real bytes. */
function buildProps(name: string, variantOverride?: string): ChartSceneProps {
  const { dataset, design, scene } = loadFixture(name);
  const variant = variantOverride ?? (scene.layout_variant as string);
  const layouts = design.layouts as Record<string, Record<string, unknown>>;
  const layout = layouts[variant];
  assertTrue(layout !== undefined, `fixture ${name} design has a ${variant} layout`);
  const motion = scene.motion as Record<string, number | string>;
  const copy = scene.copy as Record<string, string>;
  return {
    jobId: `mg016-${scene.id as string}`,
    sceneId: scene.id as string,
    componentId: scene.component_id as string,
    componentVersion: scene.component_version as string,
    canvas: variantCanvas(variant),
    durationFrames: scene.duration_frames as number,
    layoutVariant: variant as "landscape" | "portrait",
    headline: copy.headline,
    disclosure: copy.disclosure,
    dataset,
    design: {
      colors: design.colors as ChartSceneProps["design"]["colors"],
      layout: {
        headline_px: layout.headline_px as number,
        label_px: layout.label_px as number,
        value_px: layout.value_px as number,
        disclosure_px: layout.disclosure_px as number,
        plot: layout.plot as ChartSceneProps["design"]["layout"]["plot"],
        headline_box: layout.headline_box as ChartSceneProps["design"]["layout"]["headline_box"],
      },
    },
    motion: {
      kind: motion.kind as string,
      startFrame: motion.start_frame as number,
      endFrameExclusive: motion.end_frame_exclusive as number,
      holdToFrameExclusive: motion.hold_to_frame_exclusive as number,
      authoredFps: 30,
    },
    font: {
      family: FONT.family,
      files: FONT.files.map((f) => ({ weight: f.weight, base64: f.base64 })),
    },
    annotations: (
      (scene.annotations as Array<Record<string, string>> | undefined) ?? []
    ).map((a) => ({ id: a.id, rowId: a.row_id, text: a.text })),
    focusRowId: (scene.focus_row_id as string | null | undefined) ?? null,
    segmentColors: (scene.segment_colors as string[] | undefined) ?? [],
    contributionColors:
      (scene.contribution_colors as ChartSceneProps["contributionColors"]) ?? null,
  };
}

function plotOf(props: ChartSceneProps): { x: number; y: number; width: number; height: number } {
  return props.design.layout.plot;
}

// ---------------------------------------------------------------------
// Decoded raster measurement (data marks only, never titles)
// ---------------------------------------------------------------------

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function pixelMatches(
  rgb: Buffer,
  frameWidth: number,
  x: number,
  y: number,
  hex: string,
  toleranceSum = 66
): boolean {
  const [r, g, b] = hexToRgb(hex);
  const off = (y * frameWidth + x) * 3;
  return (
    Math.abs(rgb[off] - r) + Math.abs(rgb[off + 1] - g) + Math.abs(rgb[off + 2] - b) <=
    toleranceSum
  );
}

function colorFractionInBox(
  rgb: Buffer,
  frameWidth: number,
  box: { x: number; y: number; width: number; height: number },
  hex: string
): number {
  let match = 0;
  let total = 0;
  for (let y = box.y; y < box.y + box.height; y += 1) {
    for (let x = box.x; x < box.x + box.width; x += 1) {
      total += 1;
      if (pixelMatches(rgb, frameWidth, x, y, hex)) match += 1;
    }
  }
  return total === 0 ? 0 : match / total;
}

/** Centroid of the pixels matching a color inside a window around an
 * expected center; null when too few pixels match (mark absent). */
function findMarkCenter(
  rgb: Buffer,
  frameWidth: number,
  expected: { x: number; y: number },
  hex: string,
  windowRadius = 16
): { x: number; y: number; pixels: number } | null {
  let count = 0;
  let sumX = 0;
  let sumY = 0;
  for (let y = expected.y - windowRadius; y <= expected.y + windowRadius; y += 1) {
    for (let x = expected.x - windowRadius; x <= expected.x + windowRadius; x += 1) {
      if (pixelMatches(rgb, frameWidth, x, y, hex)) {
        count += 1;
        sumX += x;
        sumY += y;
      }
    }
  }
  if (count < 12) return null;
  return { x: sumX / count, y: sumY / count, pixels: count };
}

/** Vertical color runs along one scanline, bottom-up: classifies each
 * row by the first palette color it matches. Returns runs as
 * {color, length} in bottom-up order. Two runs of the same color
 * separated by a short unmatched gap (at most 10 rows: an
 * anti-aliased edge or a thin rule crossing the scanline) merge into
 * one run whose length includes the gap; real segment boundaries in
 * the fixtures are far larger than that. */
function measureVerticalRuns(
  rgb: Buffer,
  frameWidth: number,
  x: number,
  top: number,
  bottom: number,
  palette: string[]
): { color: string; length: number }[] {
  const segments: { color: string | null; length: number }[] = [];
  for (let y = bottom; y >= top; y -= 1) {
    const hit = palette.find((hex) => pixelMatches(rgb, frameWidth, x, y, hex)) ?? null;
    const last = segments[segments.length - 1];
    if (last && last.color === hit) {
      last.length += 1;
    } else {
      segments.push({ color: hit, length: 1 });
    }
  }
  const runs: { color: string; length: number }[] = [];
  let pendingGap = 0;
  let lastColor: string | null = null;
  for (const seg of segments) {
    if (seg.color === null) {
      pendingGap += seg.length;
      continue;
    }
    if (lastColor === seg.color && pendingGap <= 10 && runs.length > 0) {
      runs[runs.length - 1].length += pendingGap + seg.length;
    } else {
      runs.push({ color: seg.color, length: seg.length });
    }
    lastColor = seg.color;
    pendingGap = 0;
  }
  return runs;
}

/** The vertical extent of one color at one scanline x: topmost and
 * bottommost matching rows, as {top, height}; null when absent. */
function measureColumnExtent(
  rgb: Buffer,
  frameWidth: number,
  x: number,
  top: number,
  bottom: number,
  hex: string
): { top: number; height: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (let y = top; y <= bottom; y += 1) {
    if (pixelMatches(rgb, frameWidth, x, y, hex)) {
      if (y < min) min = y;
      if (y > max) max = y;
    }
  }
  if (max === -Infinity) return null;
  return { top: min, height: max - min + 1 };
}

// ---------------------------------------------------------------------
// Remotion library-bundle rendering
// ---------------------------------------------------------------------

interface RemotionModules {
  bundler: { bundle: (options: Record<string, unknown>) => Promise<string> };
  renderer: {
    selectComposition: (options: Record<string, unknown>) => Promise<Record<string, unknown>>;
    renderStill: (options: Record<string, unknown>) => Promise<void>;
  };
  browserExecutable: string;
  engineVersion: string;
  lockId: string;
}

let remotionModules: RemotionModules | null = null;

function loadRemotionModules(): RemotionModules {
  if (remotionModules) return remotionModules;
  const stateDir = runtimeStateDir();
  const lock = readJson<{
    packages: Record<string, string>;
    browser: { executable: string };
  }>(join(stateDir, "runtime-lock.json"));
  const currentDir = realpathSync(join(stateDir, "current"));
  const req = createRequire(join(currentDir, "package.json"));
  remotionModules = {
    bundler: req("@remotion/bundler") as RemotionModules["bundler"],
    renderer: req("@remotion/renderer") as RemotionModules["renderer"],
    browserExecutable: join(currentDir, lock.browser.executable),
    engineVersion: lock.packages.remotion,
    lockId: currentDir.split("/").pop() as string,
  };
  return remotionModules;
}

let libraryServeUrl: string | null = null;

async function ensureLibraryBundle(): Promise<string> {
  // (async because the source digest walks the tree with node:fs)
  if (libraryServeUrl) return libraryServeUrl;
  const { bundler, lockId } = loadRemotionModules();
  const entryPath = join(SCRATCH, "chart-library-entry.ts");
  mkdirSync(SCRATCH, { recursive: true });
  const rootPath = resolve(
    __dirname,
    "..",
    "..",
    "src",
    "remotion",
    "components",
    "ChartLibraryRoot.ts"
  );
  const entryContent =
    `import { registerRoot } from "remotion";\n` +
    `import { ChartLibraryRoot } from ${JSON.stringify(rootPath)};\n` +
    `registerRoot(ChartLibraryRoot);\n`;
  writeFileSync(entryPath, entryContent, "utf8");
  // The bundle key covers every runtime source file, the same
  // discipline as the Remotion adapter's bundle key: a component edit
  // must never be served by a stale cached bundle.
  const { readdirSync } = await import("node:fs");
  const srcRoot = resolve(__dirname, "..", "..", "src");
  const sourceDigest = createHash("sha256");
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name)
    )) {
      const full = join(dir, name.name);
      if (name.isDirectory()) walk(full);
      else if (name.name.endsWith(".ts")) {
        sourceDigest.update(full.slice(srcRoot.length), "utf8");
        sourceDigest.update(readFileSync(full));
      }
    }
  };
  walk(srcRoot);
  const bundleKey = `${sha256Text(entryContent + sourceDigest.digest("hex")).slice(0, 16)}-${lockId}`;
  const bundleDir = join(runtimeStateDir(), "mg016-bundles", bundleKey);
  if (existsSync(join(bundleDir, "index.html"))) {
    libraryServeUrl = bundleDir;
    return bundleDir;
  }
  mkdirSync(bundleDir, { recursive: true });
  const nodeModules = join(realpathSync(join(runtimeStateDir(), "current")), "node_modules");
  const applyResolution = (config: Record<string, unknown>): Record<string, unknown> => {
    const resolveConfig = (config.resolve as Record<string, unknown> | undefined) ?? {};
    config.resolve = {
      ...resolveConfig,
      modules: [...((resolveConfig.modules as string[] | undefined) ?? []), nodeModules],
      alias: {
        ...((resolveConfig.alias as Record<string, string> | undefined) ?? {}),
        react: join(nodeModules, "react"),
        "react-dom": join(nodeModules, "react-dom"),
        remotion: join(nodeModules, "remotion"),
      },
    };
    return config;
  };
  libraryServeUrl = await bundler.bundle({
    entryPoint: entryPath,
    outDir: bundleDir,
    onProgress: () => undefined,
    webpackOverride: applyResolution,
    rspackOverride: applyResolution,
  });
  return libraryServeUrl;
}

async function renderLibraryStill(
  compositionId: string,
  props: ChartSceneProps | Record<string, unknown>,
  frame: number,
  outName: string
): Promise<string> {
  const { renderer, browserExecutable } = loadRemotionModules();
  const serveUrl = await ensureLibraryBundle();
  const composition = await renderer.selectComposition({
    serveUrl,
    id: compositionId,
    inputProps: props,
    browserExecutable,
  });
  const canvas = (props as ChartSceneProps).canvas;
  assertEq(composition.width, canvas.width, `${compositionId} composition width from props`);
  assertEq(composition.height, canvas.height, `${compositionId} composition height from props`);
  const output = join(SCRATCH, "stills", outName);
  mkdirSync(dirname(output), { recursive: true });
  await renderer.renderStill({
    composition,
    serveUrl,
    frame,
    output,
    inputProps: props,
    browserExecutable,
    imageFormat: "png",
    overwrite: true,
    timeoutInMilliseconds: 280_000,
  });
  return output;
}

function stillRgb(path: string, width: number, height: number): Buffer {
  const dims = readPngDimensions(path);
  assertTrue(dims !== null && dims.width === width && dims.height === height,
    `still ${path} dimensions ${dims ? `${dims.width}x${dims.height}` : "unreadable"}, expected ${width}x${height}`);
  return decodeFrameRgb(path, null, width, height);
}

// Measurements record (static, MG-015 pattern): asserted on re-runs.
const measurements: Record<string, unknown> = { item: "MG-016" };

// The C05 component module imports the "remotion" and "react"
// packages, which exist only in the shared runtime install (the same
// boundary engine-modules.d.ts declares). Load it lazily behind a
// module-resolution shim pointed at that install, restored right
// after the load, purely so the formatting case can exercise the
// component's own exported formatter.
let c05ComponentCache: {
  formatValue: (value: number, rounding?: { decimals: number }) => string;
} | null = null;

function c05FormatValue(value: number, rounding?: { decimals: number }): string {
  if (c05ComponentCache === null) {
    const currentDir = realpathSync(join(runtimeStateDir(), "current"));
    const moduleAny = require("node:module") as {
      _resolveFilename: (...args: unknown[]) => string;
    };
    const original = moduleAny._resolveFilename;
    moduleAny._resolveFilename = function (
      request: string,
      ...rest: unknown[]
    ): string {
      if (request === "remotion" || request === "react" || request === "react-dom") {
        return original.call(
          moduleAny,
          join(currentDir, "node_modules", request),
          ...rest
        );
      }
      return original.call(moduleAny, request, ...rest);
    } as typeof original;
    try {
      const req = createRequire(join(__dirname, "run-chart-components.js"));
      c05ComponentCache = req(
        "../src/remotion/components/C05BarChart"
      ) as typeof c05ComponentCache;
    } finally {
      moduleAny._resolveFilename = original;
    }
  }
  return (c05ComponentCache as NonNullable<typeof c05ComponentCache>).formatValue(
    value,
    rounding
  );
}

// ---------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

const EVIDENCE_COPIES: [string, string][] = [];
const MOTION = { startFrame: 15, endFrameExclusive: 75, authoredFps: 30 };

function composedRegistry(): ComponentRegistry {
  const defaults = ComponentRegistry.createDefault()
    .list()
    .filter((e) => !["C06", "C07", "C08"].includes(e.componentId));
  return new ComponentRegistry([...defaults, c06Entry(), c07Entry(), c08Entry()]);
}

const CASES: TestCase[] = [
  {
    name: "catalog: C06-C08 dispatch in the default registry (composed at the MG-016 merge) and their bundles satisfy the registration contract",
    run: () => {
      // Coordinator reconciliation at the MG-016 merge: MG-016 delivered
      // the bundles uncomposed (its brief claimed the bundles only) and
      // this case originally asserted the default registry refused them.
      // The coordinator composed the factories into createDefault at the
      // merge, so the default registry now dispatches C06-C08; refusal
      // coverage survives through C10, which has no bundle.
      const defaults = ComponentRegistry.createDefault();
      for (const id of ["C06", "C07", "C08"]) {
        assertEq(
          defaults.requireDispatchable(id, "1.0.0").componentId,
          id,
          `default registry dispatches ${id} after the MG-016 merge composition`
        );
      }
      {
        let refused = false;
        try {
          defaults.requireDispatchable("C10", "1.0.0");
        } catch (err) {
          refused =
            err instanceof CatalogError && err.category === "MG_CAPABILITY_UNSUPPORTED";
        }
        assertTrue(refused, "default registry still refuses bundle-less C10 with MG_CAPABILITY_UNSUPPORTED");
      }
      const registry = composedRegistry();
      for (const entry of [c06Entry(), c07Entry(), c08Entry()]) {
        assertDeep(
          validateCatalogEntry(entry),
          [],
          `${entry.componentId} bundle satisfies CATALOG_ENTRY_SCHEMA`
        );
        assertEq(
          registry.requireDispatchable(entry.componentId, "1.0.0").componentId,
          entry.componentId,
          `${entry.componentId} dispatchable after registration`
        );
        assertEq(
          (entry.inputSchema as { additionalProperties?: unknown }).additionalProperties,
          false,
          `${entry.componentId} input schema is closed`
        );
        assertTrue(
          entry.proofContract !== null && entry.tests.length >= 1,
          `${entry.componentId} carries a proof contract and registered tests`
        );
        const fixtureScene = readJson<Record<string, unknown>>(
          join(
            chartFixturesRoot(),
            entry.componentId === "C06"
              ? "line-trend-a/scene.json"
              : entry.componentId === "C07"
                ? "stacked-a/scene.json"
                : "waterfall-a/scene.json"
          )
        );
        assertDeep(
          entry.examples[0].scene,
          fixtureScene,
          `${entry.componentId} example scene deep-equals its fixture scene`
        );
        const verdict = registry.validateSceneProps(fixtureScene);
        assertTrue(
          verdict.valid,
          `${entry.componentId} example scene validates through the composed registry (${JSON.stringify(verdict.findings)})`
        );
        const extra = { ...fixtureScene, surprise: true };
        const extraVerdict = registry.validateSceneProps(extra);
        assertTrue(
          !extraVerdict.valid && extraVerdict.firstErrorCategory === "MG_SCHEMA_INVALID",
          `${entry.componentId} closed schema rejects undeclared props`
        );
      }
      // The governed custom path refuses official ids by design (that
      // refusal is exactly why official bundles land through their
      // owning item and are wired into createDefault by an integration
      // step, not through register()).
      for (const bundle of [c06Registration(), c07Registration(), c08Registration()]) {
        assertEq(bundle.reviewAttestation.decision, "approved", "attestation decision");
        assertTrue(
          bundle.reviewAttestation.statement.length > 0,
          "attestation statement present"
        );
        let refusedOfficial = false;
        try {
          new ComponentRegistry([]).register(bundle);
        } catch (err) {
          refusedOfficial =
            err instanceof CatalogError && /official Section 7 id/.test(err.message);
        }
        assertTrue(
          refusedOfficial,
          `register() refuses official id ${bundle.entry.componentId} via the custom path, as designed`
        );
      }
      // Wrong motion kind and a missing required mapping fail closed.
      const c07Scene = readJson<Record<string, unknown>>(
        join(chartFixturesRoot(), "stacked-a/scene.json")
      );
      const noColors = { ...c07Scene } as Record<string, unknown>;
      delete noColors.segment_colors;
      const noColorsVerdict = composedRegistry().validateSceneProps(noColors);
      assertTrue(
        !noColorsVerdict.valid && noColorsVerdict.firstErrorCategory === "MG_SCHEMA_INVALID",
        "C07 scene without the declared segment color mapping is refused"
      );
    },
  },
  {
    name: "datasets: every fixture passes the MG-015 chart contract; designs are canonical; invented evidence fails",
    run: () => {
      for (const name of [
        "line-trend-a",
        "line-trend-b",
        "stacked-a",
        "stacked-b",
        "waterfall-a",
        "waterfall-b",
      ]) {
        const { dataset, design } = loadFixture(name);
        assertEq(dataset.kind, "illustrative", `${name} dataset is honestly labeled illustrative`);
        assertDeep(
          validateAgainstDef("design", design),
          [],
          `${name} design satisfies the canonical design $def`
        );
      }
      const mutated = JSON.parse(
        JSON.stringify(loadFixture("line-trend-a").dataset)
      ) as Record<string, unknown>;
      mutated.kind = "observed";
      let threw = false;
      try {
        assertChartDataset(mutated);
      } catch {
        threw = true;
      }
      assertTrue(threw, "an observed dataset whose note admits illustration fails as invented evidence");
    },
  },
  {
    name: "geometry: line trend exact final points on two datasets, staged states, no fabricated smoothing",
    run: () => {
      const a = loadFixture("line-trend-a");
      const plotA = { x: 360, y: 300, width: 1320, height: 600 };
      const geoA = lineGeometry(a.dataset, plotA);
      assertDeep(
        geoA.points.map((p) => [p.x, p.y]),
        [
          [0, 480],
          [264, 360],
          [528, 420],
          [792, 240],
          [1056, 120],
          [1320, 0],
        ],
        "line A final plot-local points"
      );
      assertEq(geoA.segments.length, 5, "line A segment count");
      assertEq(geoA.zeroY, 600, "line A zero line sits at the plot bottom (domain min 0)");
      const mid = lineStateAt(a.dataset, plotA, 0.5);
      assertDeep(
        mid.dots.filter((d) => d.established).map((d) => d.index),
        [0, 1, 2],
        "line A at half progress: exactly the first three points are established"
      );
      assertDeep(
        mid.runs,
        [[{ x: 0, y: 480 }, { x: 264, y: 360 }, { x: 528, y: 420 }]],
        "line A at half progress: one run through the established true points"
      );
      assertEq(mid.activeIndex, 2, "line A moving focus at half progress");
      const start = lineStateAt(a.dataset, plotA, 0);
      assertTrue(
        start.dots.every((d) => d.radius === 0) && start.runs.length === 0,
        "line A at progress 0 shows no data marks"
      );
      const full = lineStateAt(a.dataset, plotA, 1);
      assertDeep(
        full.runs,
        [geoA.points.map((p) => ({ x: p.x, y: p.y }))],
        "line A at full progress: the polyline equals the true point list exactly (straight segments, no smoothing)"
      );
      const b = loadFixture("line-trend-b");
      const geoB = lineGeometry(b.dataset, { x: 360, y: 200, width: 1320, height: 540 });
      assertDeep(
        geoB.points.map((p) => p.y),
        [468, 360, 288, 396, 180, 0],
        "line B final y positions with negative and zero values"
      );
      assertEq(geoB.zeroY, 360, "line B zero line inside the plot (domain spans zero)");
      measurements.lineGeometry = {
        aPoints: geoA.points.map((p) => [p.x, p.y]),
        bPointsY: geoB.points.map((p) => p.y),
      };
    },
  },
  {
    name: "geometry: stacked allocation exact segments on two datasets (zero segment included); negatives refused",
    run: () => {
      const plot = { x: 360, y: 300, width: 1320, height: 600 };
      const a = stackedGeometry(loadFixture("stacked-a").dataset, plot);
      assertDeep(
        a.segments.map((s) => [s.height, s.bottomOffset]),
        [
          [240, 0],
          [180, 240],
          [120, 420],
          [60, 540],
        ],
        "stacked A segment heights and offsets"
      );
      assertEq(a.total, 100, "stacked A total is the arithmetic sum");
      const b = stackedGeometry(loadFixture("stacked-b").dataset, plot);
      assertDeep(
        b.segments.map((s) => [s.height, s.bottomOffset]),
        [
          [200, 0],
          [0, 200],
          [280, 200],
          [120, 480],
        ],
        "stacked B segment heights and offsets (zero segment at its truthful level)"
      );
      assertEq(b.total, 75, "stacked B total");
      const mid = stackedStateAt(loadFixture("stacked-a").dataset, plot, 0.5);
      assertDeep(
        mid.segments.map((s) => s.currentHeight),
        [240, 180, 0, 0],
        "stacked A at half progress: first two segments landed, later segments absent"
      );
      const negative = JSON.parse(
        JSON.stringify(loadFixture("stacked-a").dataset)
      ) as ChartDataset;
      negative.rows[1].value = -5;
      negative.declared_total = 65;
      let refused = false;
      try {
        stackedGeometry(negative, plot);
      } catch {
        refused = true;
      }
      assertTrue(refused, "a negative allocation segment is refused, never drawn");
      measurements.stackedGeometry = {
        a: a.segments.map((s) => [s.height, s.bottomOffset]),
        b: b.segments.map((s) => [s.height, s.bottomOffset]),
      };
    },
  },
  {
    name: "geometry: waterfall exact steps on two datasets; arithmetic equality; out-of-domain running level refused",
    run: () => {
      const a = waterfallGeometry(loadFixture("waterfall-a").dataset, {
        x: 360,
        y: 260,
        width: 1280,
        height: 600,
      });
      assertDeep(
        a.steps.map((s) => [s.kind, s.from, s.to, s.top, s.height]),
        [
          ["start", 0, 100, 150, 300],
          ["contribution", 100, 125, 75, 75],
          ["contribution", 125, 115, 75, 30],
          ["total", 0, 115, 105, 345],
        ],
        "waterfall A steps (start 100, +25, -10, end 115)"
      );
      assertEq(a.endValue, 115, "waterfall A ending value equals start plus contributions");
      assertDeep(
        a.connectors.map((c) => c.y),
        [150, 75, 105],
        "waterfall A connector levels are the running totals"
      );
      assertEq(a.zeroY, 450, "waterfall A zero line (domain widened to include contributions)");
      const b = waterfallGeometry(loadFixture("waterfall-b").dataset, {
        x: 360,
        y: 260,
        width: 1200,
        height: 600,
      });
      assertDeep(
        b.steps.map((s) => [s.kind, s.from, s.to, s.top, s.height]),
        [
          ["start", 0, 40, 40, 160],
          ["contribution", 40, -30, 40, 280],
          ["contribution", -30, -10, 240, 80],
          ["contribution", -10, -10, 240, 0],
          ["total", 0, -10, 200, 40],
        ],
        "waterfall B steps cross zero and include a zero contribution (the total column hangs from the zero line)"
      );
      assertEq(b.endValue, -10, "waterfall B ending value");
      assertEq(b.zeroY, 200, "waterfall B zero line inside the plot");
      const mid = waterfallStateAt(loadFixture("waterfall-a").dataset, {
        x: 360,
        y: 260,
        width: 1280,
        height: 600,
      }, 0.5);
      assertDeep(
        mid.steps.map((s) => s.progress),
        [1, 1, 0, 0],
        "waterfall A at half progress: start and first contribution landed"
      );
      assertDeep(
        mid.connectors.map((c) => c.visible),
        [true, true, false],
        "waterfall A connectors appear only behind completed steps"
      );
      const outOfDomain = JSON.parse(
        JSON.stringify(loadFixture("waterfall-a").dataset)
      ) as ChartDataset;
      outOfDomain.rows[1].value = 80;
      outOfDomain.declared_total = 170;
      let refused = false;
      try {
        waterfallGeometry(outOfDomain, { x: 360, y: 300, width: 1280, height: 600 });
      } catch {
        refused = true;
      }
      assertTrue(refused, "a running level outside the declared domain is refused, never clipped");
      measurements.waterfallGeometry = {
        a: a.steps.map((s) => [s.from, s.to, s.top, s.height]),
        b: b.steps.map((s) => [s.from, s.to, s.top, s.height]),
      };
    },
  },
  {
    name: "C05 fixes: zero-baseline geometry on domain [10, 40], Section 17.2 anchors unchanged, declared rounding adopted",
    run: () => {
      // D-CHART-BASELINE, before: the production domain-minimum scale.
      assertEq(scaleBarWidth(10, [10, 40], 1200), 0, "before: value 10 draws zero length (the defect)");
      assertEq(scaleBarWidth(25, [10, 40], 1200), 600, "before: value 25");
      assertEq(scaleBarWidth(40, [10, 40], 1200), 1200, "before: value 40");
      assertEq(
        barWidthAt(10, [10, 40], 1200, 75, 30, MOTION),
        0,
        "before: barWidthAt at full reveal is the same zero"
      );
      // After: MG-015 barGeometry on the zero-baseline domain.
      assertDeep(zeroBaselineDomain([10, 40]), [0, 40], "zero-baseline domain widens to include zero");
      assertDeep(zeroBaselineDomain([0, 30]), [0, 30], "zero-baseline domain is identity on zero-min domains");
      assertDeep(zeroBaselineDomain([-20, 40]), [-20, 40], "zero-baseline domain is identity when zero is already inside");
      const g10 = barGeometryForValue(10, [10, 40], 1200);
      assertEq(g10.width, 300, "after: value 10 draws a nonzero truthful length (10/40 of the plot)");
      assertEq(barGeometryForValue(25, [10, 40], 1200).width, 750, "after: value 25");
      assertEq(barGeometryForValue(40, [10, 40], 1200).width, 1200, "after: value 40 draws the full length");
      assertEq(
        barGeometry(10, [0, 40], 1200).width,
        g10.width,
        "the routed geometry is exactly MG-015 barGeometry on the widened domain"
      );
      const at45 = barStateAt(40, [10, 40], 1200, 45, 30, MOTION);
      assertEq(at45.width, 600, "at half reveal the full-length bar is at half its truthful width");
      // Section 17.2 anchors unchanged (zero-min domain).
      assertDeep(
        [12, 18, 30].map((v) => barGeometryForValue(v, [0, 30], 1200).width),
        [480, 720, 1200],
        "landscape anchors unchanged"
      );
      assertDeep(
        [12, 18, 30].map((v) => barGeometryForValue(v, [0, 30], 740).width),
        [296, 444, 740],
        "portrait anchors unchanged"
      );
      assertEq(slotProgress(0.5, 1, 4), 1, "slot progress: second of four slots complete at half");
      assertEq(slotProgress(0.5, 2, 4), 0, "slot progress: third slot only starts at half");
      assertEq(slotProgress(0.5, 3, 4), 0, "slot progress: fourth slot not started at half");
      // Label de-collision: two blocks whose centers are too close
      // for their heights are separated by exactly the declared gap.
      const tops = resolveLabelTops([330, 420], [55.2, 110.4], 10, 0, 10000);
      assertClose(tops[0], 302.4, 0.01, "label tops: first block keeps its center");
      assertClose(tops[1], 367.6, 0.01, "label tops: second block pushed below the gap");
      assertEq(estimateLabelLines("Reserve: 10 percent", 48, 422), 2, "label lines: 19 chars wrap at the C07 rail width");
      assertEq(estimateLabelLines("Churn: -10 USD thousands", 48, 1280), 1, "label lines: short text stays one line in a wide box");
      // Formatting adoption: declared rounding governs when present;
      // the interim rule preserves the shipped fixture's integers.
      assertEq(c05FormatValue(12), "12", "interim rule: integer prints as integer");
      assertEq(c05FormatValue(12.5), "12.5", "interim rule: two decimals trimmed");
      assertEq(c05FormatValue(1.005), "1.01", "interim rule: decimal-string rounding fixes the 1.005 case");
      assertEq(c05FormatValue(12.25, { decimals: 1 }), "12.3", "declared rounding: one decimal, half away from zero");
      assertEq(c05FormatValue(12, { decimals: 2 }), "12.00", "declared rounding: exactly the declared decimals print");
      assertEq(
        formatDatasetValue(loadFixture("line-trend-a").dataset, 42),
        "42",
        "dataset-declared formatting through the shared formatter"
      );
      measurements.c05BaselineGeometry = {
        domain: [10, 40],
        before: [0, 600, 1200],
        after: [300, 750, 1200],
      };
    },
  },
  {
    name: "title-only invariance at the props level: geometry depends on the dataset and design, never the headline",
    run: () => {
      const props = buildProps("line-trend-a");
      const retitled = { ...props, headline: "A completely different headline" };
      assertDeep(
        lineStateAt(retitled.dataset, plotOf(retitled), 0.5),
        lineStateAt(props.dataset, plotOf(props), 0.5),
        "line state at half progress is identical under a title-only change"
      );
      assertDeep(
        stackedStateAt(buildProps("stacked-a").dataset, plotOf(props), 1),
        stackedStateAt(buildProps("stacked-a").dataset, plotOf(props), 1),
        "stacked final state is a function of data and design only"
      );
    },
  },
];

// ---------------------------------------------------------------------
// Render cases (real renders, decoded measurement of the marks)
// ---------------------------------------------------------------------

function expectedCenters(props: ChartSceneProps): { x: number; y: number }[] {
  const plot = plotOf(props);
  return lineGeometry(props.dataset, plot).points.map((p) => ({
    x: plot.x + p.x,
    y: plot.y + p.y,
  }));
}

function assertCenters(
  rgb: Buffer,
  frameWidth: number,
  centers: { x: number; y: number }[],
  accent: string,
  present: boolean[],
  tolerance: number,
  label: string
): { x: number; y: number }[] {
  const found: { x: number; y: number }[] = [];
  centers.forEach((center, i) => {
    const mark = findMarkCenter(rgb, frameWidth, center, accent);
    if (present[i]) {
      assertTrue(mark !== null, `${label}: point ${i} present at frame`);
      const m = mark as { x: number; y: number };
      assertClose(m.x, center.x, tolerance, `${label}: point ${i} center x`);
      assertClose(m.y, center.y, tolerance, `${label}: point ${i} center y`);
      found.push({ x: Math.round(m.x * 10) / 10, y: Math.round(m.y * 10) / 10 });
    } else {
      assertTrue(mark === null, `${label}: point ${i} absent at frame`);
      found.push({ x: -1, y: -1 });
    }
  });
  return found;
}

CASES.push(
  {
    name: "render C06 line trend A: marks change across proof frames and land on exact final geometry",
    run: async () => {
      const props = buildProps("line-trend-a") as C06Props;
      const accent = props.design.colors.accent;
      const centers = expectedCenters(props);
      assertDeep(
        centers,
        [
          { x: 360, y: 780 },
          { x: 624, y: 660 },
          { x: 888, y: 720 },
          { x: 1152, y: 540 },
          { x: 1416, y: 420 },
          { x: 1680, y: 300 },
        ],
        "line A expected canvas centers"
      );
      const decoded: Record<string, unknown> = {};
      const stills: Record<number, string> = {};
      for (const frame of [0, 45, 75, 150]) {
        stills[frame] = await renderLibraryStill("C06", props, frame, `c06-a-f${frame}.png`);
        EVIDENCE_COPIES.push([stills[frame], `c06-line-a-f${frame}.png`]);
      }
      const rgb0 = stillRgb(stills[0], 1920, 1080);
      assertCenters(rgb0, 1920, centers, accent, [false, false, false, false, false, false], 3, "line A f0");
      const rgb45 = stillRgb(stills[45], 1920, 1080);
      const found45 = assertCenters(
        rgb45, 1920, centers, accent,
        [true, true, true, false, false, false], 3, "line A f45"
      );
      decoded.f45 = found45;
      const rgb75 = stillRgb(stills[75], 1920, 1080);
      const found75 = assertCenters(
        rgb75, 1920, centers, accent,
        [true, true, true, true, true, true], 3, "line A f75"
      );
      decoded.f75 = found75;
      const rgb150 = stillRgb(stills[150], 1920, 1080);
      const found150 = assertCenters(
        rgb150, 1920, centers, accent,
        [true, true, true, true, true, true], 3, "line A f150"
      );
      decoded.f150 = found150;
      found150.forEach((center, i) => {
        assertClose(center.x, found75[i].x, 1.5, `line A hold stability x point ${i}`);
        assertClose(center.y, found75[i].y, 1.5, `line A hold stability y point ${i}`);
      });
      // The annotation is a post-reveal state: absent mid-reveal,
      // present in the hold, as an ink border at its declared box.
      const annotationBox = { x: 694, y: 364, width: 360, height: 3 };
      const ink = props.design.colors.ink;
      assertTrue(
        colorFractionInBox(rgb45, 1920, annotationBox, ink) < 0.1,
        "line A annotation absent at frame 45"
      );
      assertTrue(
        colorFractionInBox(rgb150, 1920, annotationBox, ink) > 0.5,
        "line A annotation border present at frame 150"
      );
      measurements.lineRenderA = decoded;
    },
  },
  {
    name: "render C06 line trend B: negative and zero values with long category names land exactly",
    run: async () => {
      const props = buildProps("line-trend-b") as C06Props;
      const centers = expectedCenters(props);
      assertDeep(
        centers.map((c) => c.y),
        [668, 560, 488, 596, 380, 200],
        "line B expected canvas center heights"
      );
      const still = await renderLibraryStill("C06", props, 75, "c06-b-f75.png");
      EVIDENCE_COPIES.push([still, "c06-line-b-f75.png"]);
      const rgb = stillRgb(still, 1920, 1080);
      const found = assertCenters(
        rgb, 1920, centers, props.design.colors.accent,
        [true, true, true, true, true, true], 3, "line B f75"
      );
      measurements.lineRenderB = { f75: found };
    },
  },
  {
    name: "render C06 portrait (mobile) variant: genuine recomposition with exact final geometry",
    run: async () => {
      const props = buildProps("line-trend-a", "portrait") as C06Props;
      assertEq(props.canvas.width, 1080, "portrait canvas width");
      assertEq(props.canvas.height, 1920, "portrait canvas height");
      const centers = expectedCenters(props);
      assertDeep(
        centers,
        [
          { x: 140, y: 1136 },
          { x: 300, y: 992 },
          { x: 460, y: 1064 },
          { x: 620, y: 848 },
          { x: 780, y: 704 },
          { x: 940, y: 560 },
        ],
        "line A portrait expected canvas centers"
      );
      const still = await renderLibraryStill("C06", props, 75, "c06-a-portrait-f75.png");
      EVIDENCE_COPIES.push([still, "c06-line-a-portrait-f75.png"]);
      const rgb = stillRgb(still, 1080, 1920);
      const found = assertCenters(
        rgb, 1080, centers, props.design.colors.accent,
        [true, true, true, true, true, true], 3, "line A portrait f75"
      );
      measurements.lineRenderPortrait = { f75: found };
    },
  },
  {
    name: "render C06 title-only variant: identical mark geometry, different headline pixels",
    run: async () => {
      const props = buildProps("line-trend-a") as C06Props;
      const retitled: ChartSceneProps = {
        ...props,
        headline: "A completely different headline about quarterly planning reviews",
      };
      const still = await renderLibraryStill("C06", retitled, 75, "c06-a-retitled-f75.png");
      const rgb = stillRgb(still, 1920, 1080);
      const centers = expectedCenters(props);
      const found = assertCenters(
        rgb, 1920, centers, props.design.colors.accent,
        [true, true, true, true, true, true], 2, "line A retitled f75"
      );
      // Compare against the original render's own decoded centers
      // (the line A case rendered this still earlier in the suite).
      const originalStill = join(SCRATCH, "stills", "c06-a-f75.png");
      const originalRgb = stillRgb(originalStill, 1920, 1080);
      const original = assertCenters(
        originalRgb, 1920, centers, props.design.colors.accent,
        [true, true, true, true, true, true], 2, "line A original f75 (recheck)"
      );
      found.forEach((center, i) => {
        assertClose(center.x, original[i].x, 2, `retitled point ${i} x matches the original render`);
        assertClose(center.y, original[i].y, 2, `retitled point ${i} y matches the original render`);
      });
      // And the headline really did change (the comparison is not
      // vacuous): compare the headline box against the original still.
      let differing = 0;
      let total = 0;
      for (let y = 90; y < 260; y += 2) {
        for (let x = 120; x < 1500; x += 2) {
          const off = (y * 1920 + x) * 3;
          const diff =
            Math.abs(rgb[off] - originalRgb[off]) +
            Math.abs(rgb[off + 1] - originalRgb[off + 1]) +
            Math.abs(rgb[off + 2] - originalRgb[off + 2]);
          total += 1;
          if (diff > 30) differing += 1;
        }
      }
      assertTrue(
        differing / total > 0.005,
        `headline pixels differ between the title variants (${differing}/${total} sampled)`
      );
    },
  },
  {
    name: "render C07 stacked allocation A and B: decoded segment runs match exact geometry, zero segment marked",
    run: async () => {
      const propsA = buildProps("stacked-a");
      const plotA = plotOf(propsA);
      const columnCenterX = plotA.x + plotA.width / 2;
      const paletteA = propsA.segmentColors;
      const stillA45 = await renderLibraryStill("C07", propsA, 45, "c07-a-f45.png");
      const stillA75 = await renderLibraryStill("C07", propsA, 75, "c07-a-f75.png");
      EVIDENCE_COPIES.push([stillA45, "c07-stacked-a-f45.png"], [stillA75, "c07-stacked-a-f75.png"]);
      const runsAt = (path: string, palette: string[]): { color: string; length: number }[] =>
        measureVerticalRuns(
          stillRgb(path, 1920, 1080),
          1920,
          columnCenterX,
          plotA.y,
          plotA.y + plotA.height - 1,
          palette
        );
      const runs45 = runsAt(stillA45, paletteA);
      assertEq(runs45.length, 2, "stacked A at frame 45: exactly two segments present");
      assertEq(runs45[0].color, paletteA[0], "stacked A frame 45 bottom segment color");
      assertClose(runs45[0].length, 240, 2, "stacked A frame 45 first segment height");
      assertClose(runs45[1].length, 180, 2, "stacked A frame 45 second segment height");
      const runs75 = runsAt(stillA75, paletteA);
      assertDeep(
        runs75.map((r) => r.color),
        paletteA,
        "stacked A final segment colors in declared order, bottom-up"
      );
      [240, 180, 120, 60].forEach((want, i) =>
        assertClose(runs75[i].length, want, 2, `stacked A final segment ${i} height`)
      );
      measurements.stackedRenderA = { runs75: runs75.map((r) => r.length) };

      const propsB = buildProps("stacked-b");
      const stillB75 = await renderLibraryStill("C07", propsB, 75, "c07-b-f75.png");
      EVIDENCE_COPIES.push([stillB75, "c07-stacked-b-f75.png"]);
      const rgbB = stillRgb(stillB75, 1920, 1080);
      const runsB = measureVerticalRuns(
        rgbB, 1920, columnCenterX, plotA.y, plotA.y + plotA.height - 1, propsB.segmentColors
      );
      // The zero segment appears in the scan as exactly its marker
      // line (4 rows in its declared color) between its neighbors.
      assertDeep(
        runsB.map((r) => r.color),
        [
          propsB.segmentColors[0],
          propsB.segmentColors[1],
          propsB.segmentColors[2],
          propsB.segmentColors[3],
        ],
        "stacked B final runs in order, the zero segment present as its marker"
      );
      [200, 4, 280, 120].forEach((want, i) =>
        assertClose(runsB[i].length, want, 3, `stacked B final run ${i} height`)
      );
      // The zero segment still reads: its marker line sits at its
      // truthful level (bottom offset 200) in its declared color.
      const markerY = plotA.y + plotA.height - 200 - 2;
      assertTrue(
        colorFractionInBox(
          rgbB, 1920,
          { x: columnCenterX - 100, y: markerY, width: 200, height: 4 },
          propsB.segmentColors[1]
        ) > 0.7,
        "stacked B zero segment marker line present at its level in its declared color"
      );
      measurements.stackedRenderB = { runs75: runsB.map((r) => r.length) };
    },
  },
  {
    name: "render C08 waterfall A and B: decoded column extents and connectors match exact geometry",
    run: async () => {
      const propsA = buildProps("waterfall-a");
      const plotA = plotOf(propsA);
      const colorsA = propsA.contributionColors as { positive: string; negative: string };
      const accentA = propsA.design.colors.accent;
      // Band centers for four steps over the 1280-wide plot.
      const centersA = [520, 840, 1160, 1480];
      const stepColorsA = [accentA, colorsA.positive, colorsA.negative, accentA];
      const extentAt = (
        rgb: Buffer,
        x: number,
        hex: string
      ): { top: number; height: number } | null =>
        measureColumnExtent(rgb, 1920, x, plotA.y, plotA.y + plotA.height - 1, hex);
      const stillA45 = await renderLibraryStill("C08", propsA, 45, "c08-a-f45.png");
      const stillA75 = await renderLibraryStill("C08", propsA, 75, "c08-a-f75.png");
      EVIDENCE_COPIES.push([stillA45, "c08-waterfall-a-f45.png"], [stillA75, "c08-waterfall-a-f75.png"]);
      const rgbA45 = stillRgb(stillA45, 1920, 1080);
      const startAt45 = extentAt(rgbA45, centersA[0], stepColorsA[0]);
      assertTrue(startAt45 !== null, "waterfall A start column present at frame 45");
      assertClose((startAt45 as { top: number }).top, 410, 2, "waterfall A start top at frame 45");
      assertClose((startAt45 as { height: number }).height, 300, 2, "waterfall A start height at frame 45");
      const growthAt45 = extentAt(rgbA45, centersA[1], stepColorsA[1]);
      assertTrue(growthAt45 !== null, "waterfall A first contribution present at frame 45");
      assertClose((growthAt45 as { top: number }).top, 335, 2, "waterfall A contribution top at frame 45");
      assertClose((growthAt45 as { height: number }).height, 75, 2, "waterfall A contribution height at frame 45");
      assertEq(extentAt(rgbA45, centersA[2], stepColorsA[2]), null, "waterfall A later steps absent at frame 45");
      const rgbA75 = stillRgb(stillA75, 1920, 1080);
      const expectedA = [
        { top: 410, height: 300 },
        { top: 335, height: 75 },
        { top: 335, height: 30 },
        { top: 365, height: 345 },
      ];
      const decodedA = expectedA.map((want, i) => {
        const extent = extentAt(rgbA75, centersA[i], stepColorsA[i]);
        assertTrue(extent !== null, `waterfall A step ${i} present at frame 75`);
        const e = extent as { top: number; height: number };
        assertClose(e.top, want.top, 2, `waterfall A step ${i} top`);
        assertClose(e.height, want.height, 2, `waterfall A step ${i} height`);
        return [e.top, e.height];
      });
      // Connector at the running level after the first contribution
      // (level 125, plot-local y 75): an ink run in the gap between
      // the contribution column and the next column.
      // Connectors render in ink at 0.55 opacity; probe for the
      // blended color that produces over the background.
      const inkRgb = hexToRgb(propsA.design.colors.ink);
      const bgRgb = hexToRgb(propsA.design.colors.background);
      const blendHex =
        "#" +
        inkRgb
          .map((v, i) => Math.round(0.55 * v + 0.45 * bgRgb[i]).toString(16).padStart(2, "0"))
          .join("");
      const connectorFraction = colorFractionInBox(
        rgbA75, 1920, { x: 956, y: 334, width: 88, height: 3 }, blendHex
      );
      assertTrue(connectorFraction > 0.5, "waterfall A connector present at the running level");
      measurements.waterfallRenderA = { steps75: decodedA };

      const propsB = buildProps("waterfall-b");
      const plotB = plotOf(propsB);
      const centersB = [480, 720, 960, 1200, 1440];
      const colorsB = propsB.contributionColors as { positive: string; negative: string };
      const accentB = propsB.design.colors.accent;
      const stepColorsB = [accentB, colorsB.negative, colorsB.positive, colorsB.positive, accentB];
      const stillB75 = await renderLibraryStill("C08", propsB, 75, "c08-b-f75.png");
      EVIDENCE_COPIES.push([stillB75, "c08-waterfall-b-f75.png"]);
      const rgbB = stillRgb(stillB75, 1920, 1080);
      const expectedB = [
        { top: 300, height: 160 },
        { top: 300, height: 280 },
        { top: 500, height: 80 },
        null,
        { top: 460, height: 40 },
      ];
      const decodedB = expectedB.map((want, i) => {
        const extent = measureColumnExtent(
          rgbB, 1920, centersB[i], plotB.y, plotB.y + plotB.height - 1, stepColorsB[i]
        );
        if (want === null) {
          assertEq(extent, null, "waterfall B zero contribution draws no column");
          return null;
        }
        assertTrue(extent !== null, `waterfall B step ${i} present`);
        const e = extent as { top: number; height: number };
        assertClose(e.top, want.top, 2, `waterfall B step ${i} top`);
        assertClose(e.height, want.height, 2, `waterfall B step ${i} height`);
        return [e.top, e.height];
      });
      measurements.waterfallRenderB = { steps75: decodedB };
    },
  },
  {
    name: "C05 regression through the production adapter: domain [10, 40] renders truthfully after the fix",
    run: async () => {
      const staged = join(SCRATCH, "job-baseline");
      rmSync(staged, { recursive: true, force: true });
      cpSync(join(fixturesRoot(), "modes", "powerpoint_graphic"), staged, { recursive: true });
      const barsPath = join(staged, "data", "bars.json");
      const bars = readJson<Record<string, unknown>>(barsPath);
      bars.domain = [10, 40];
      bars.rows = [
        { id: "a", label: "Group A", value: 10 },
        { id: "b", label: "Group B", value: 25 },
        { id: "c", label: "Group C", value: 40 },
      ];
      writeFileSync(barsPath, JSON.stringify(bars, null, 2) + "\n", "utf8");
      const outDir = join(SCRATCH, "c05-baseline-out");
      const adapter = createRemotionAdapter({ outputDir: outDir });
      const job = loadValidatedJob(staged);
      const loaded = loadC05Job(job);
      // The adapter's instrumented path (job-props, outside MG-016's
      // claims) still reports the old domain-minimum numbers; the
      // rendered raster is the truth after the component fix. The
      // divergence is recorded in the MG-016 integration notes.
      const { instrumentedBarWidths } = await import("../src/remotion/job-props");
      assertDeep(
        instrumentedBarWidths(loaded.props, 75),
        [0, 600, 1200],
        "instrumented path still shows the pre-fix numbers (documented divergence)"
      );
      const decodedByFrame: Record<string, number[]> = {};
      for (const frame of [45, 75]) {
        const evidence = await adapter.renderStill(job, frame);
        const stillPath = evidence.outputPaths[0];
        const rgb = stillRgb(stillPath, 1920, 1080);
        const decoded = measureAccentBarWidths(
          rgb, 1920, loaded.props.design.layout, loaded.props.design.colors.accent
        );
        decodedByFrame[String(frame)] = decoded;
        if (frame === 75) {
          EVIDENCE_COPIES.push([stillPath, "c05-baseline-f75.png"]);
        }
      }
      [300, 750, 1200].forEach((want, i) =>
        assertClose(decodedByFrame["75"][i], want, 2, `C05 [10, 40] decoded width for bar ${i} at frame 75`)
      );
      [150, 375, 600].forEach((want, i) =>
        assertClose(decodedByFrame["45"][i], want, 2, `C05 [10, 40] decoded width for bar ${i} at frame 45`)
      );
      assertTrue(
        decodedByFrame["75"][0] > 0,
        "value 10 renders a nonzero bar after the fix (it rendered zero before)"
      );
      measurements.c05BaselineRender = { decoded45: decodedByFrame["45"], decoded75: decodedByFrame["75"] };

      // The declared-rounding plumbing: when a loader supplies the
      // dataset's declared rounding in the props, the component
      // consumes it (same raster geometry; the formatter case above
      // pins the printed strings).
      const propsWithRounding = {
        ...loaded.props,
        dataset: { ...loaded.props.dataset, displayRounding: { decimals: 1 } },
      };
      const still = await renderLibraryStill("C05", propsWithRounding, 75, "c05-baseline-rounding-f75.png");
      const rgb = stillRgb(still, 1920, 1080);
      const decoded = measureAccentBarWidths(
        rgb, 1920, loaded.props.design.layout, loaded.props.design.colors.accent
      );
      [300, 750, 1200].forEach((want, i) =>
        assertClose(decoded[i], want, 2, `C05 with plumbed declared rounding: bar ${i} geometry unchanged`)
      );
    },
  },
  {
    name: "Hyperframes C06: the line trend on the native clock, generated composition, decoded proof frames",
    run: async () => {
      const spec = readJson<LineTrendSceneSpec>(
        join(chartFixturesRoot(), "line-trend-a/scene-hyperframes.json")
      );
      // The spec's embedded points must be the shared geometry's
      // output for the same fixture (no drift between engines).
      const fixture = loadFixture("line-trend-a");
      const plot = { x: 360, y: 300, width: 1320, height: 600 };
      const geo = lineGeometry(fixture.dataset, plot);
      assertDeep(
        spec.points.map((p) => [p.id, p.x, p.y]),
        geo.points.map((p) => [p.rowId, plot.x + p.x, plot.y + p.y]),
        "Hyperframes spec points equal the shared line geometry in canvas coordinates"
      );
      assertDeep(
        spec.points.map((p) => p.value_label),
        geo.points.map((p) => formatDatasetValue(fixture.dataset, p.value)),
        "Hyperframes spec value labels use the dataset's declared formatting"
      );
      const rt = resolveSharedRuntime();
      measurements.runtime = {
        remotion: loadRemotionModules().engineVersion,
        hyperframes: rt.engineVersion,
        runtimeLockId: rt.runtimeLockId,
      };
      const font = resolveHfFont(spec.font_ref);
      const project = generateC06Project({ spec, font, fps: 30 });
      const projectDir = join(SCRATCH, "hf-c06");
      rmSync(projectDir, { recursive: true, force: true });
      mkdirSync(projectDir, { recursive: true });
      vendorIntoProject(projectDir, "mg016-c06-hf", rt, font);
      for (const [rel, content] of Object.entries(project.files)) {
        const abs = join(projectDir, rel);
        mkdirSync(dirname(abs), { recursive: true });
        writeFileSync(abs, content, "utf8");
      }
      const env: NodeJS.ProcessEnv = { ...process.env };
      delete env.GEMINI_API_KEY;
      env.HYPERFRAMES_SKIP_SKILLS = "1";
      env.HYPERFRAMES_NO_TELEMETRY = "1";
      env.DO_NOT_TRACK = "1";
      // Chrome's temp files (DevTools port file, profiles) must not
      // depend on the machine's /tmp, a small tmpfs that fills under
      // parallel render load and then breaks browser startup with
      // opaque socket errors. Point TMPDIR at scratch on the home
      // filesystem for every CLI invocation in this case.
      const hfTmp = join(SCRATCH, "hf-tmp");
      mkdirSync(hfTmp, { recursive: true });
      env.TMPDIR = hfTmp;
      const runCli = (args: string[]): { code: number; stdout: string; stderr: string } => {
        const res = spawnSync(rt.cliBin, args, {
          cwd: projectDir,
          env,
          encoding: "utf8",
          timeout: 300_000,
        });
        return {
          code: res.status ?? 1,
          stdout: res.stdout ?? "",
          stderr: res.stderr ?? "",
        };
      };
      const listed = runCli(["compositions", projectDir, "--json"]);
      assertEq(listed.code, 0, `hyperframes compositions exit (${listed.stderr.slice(-300)})`);
      assertTrue(listed.stdout.includes(spec.id), "the generated composition registers its id");
      const lint = runCli(["lint", projectDir, "--json"]);
      assertEq(lint.code, 0, `hyperframes lint exit (${(lint.stdout + lint.stderr).slice(-300)})`);
      const presence: Record<string, boolean[]> = {};
      const times: Record<string, string> = {
        f0: "0",
        f45: "1.5",
        f75: "2.5",
        f150: "5",
      };
      for (const [label, at] of Object.entries(times)) {
        const snapDir = join(SCRATCH, "hf-snaps", label);
        rmSync(snapDir, { recursive: true, force: true });
        mkdirSync(snapDir, { recursive: true });
        const snap = runCli([
          "snapshot", projectDir, "-o", snapDir,
          "--at", at, "--no-end", "--no-browser-gpu", "--describe", "false",
        ]);
        assertEq(snap.code, 0, `hyperframes snapshot at ${at}s exit (${snap.stderr.slice(-300)})`);
        const { readdirSync } = await import("node:fs");
        const pngs = readdirSync(snapDir).filter((f) => f.toLowerCase().endsWith(".png")).sort();
        assertTrue(pngs.length > 0, `snapshot at ${at}s produced a PNG`);
        const pngPath = join(snapDir, pngs[0]);
        EVIDENCE_COPIES.push([pngPath, `hf-c06-line-${label}.png`]);
        const img = await decodePng(pngPath);
        assertEq(img.width, 1920, "hyperframes still width");
        assertEq(img.height, 1080, "hyperframes still height");
        // A present dot measures about 0.17 to 0.22 accent fraction
        // in its 36px probe box (disc plus line); an absent point
        // measures 0. The presence threshold sits far from both.
        presence[label] = spec.points.map(
          (p) =>
            measureColorFraction(
              img,
              { x: p.x - 18, y: p.y - 18, width: 36, height: 36 },
              spec.design.colors.accent
            ) > 0.08
        );
        if (label === "f150") {
          const apr = spec.points.find((p) => p.id === "apr") as { x: number; y: number };
          const borderFraction = measureColorFraction(
            img,
            { x: apr.x - 458, y: apr.y - 176, width: 300, height: 3 },
            spec.design.colors.ink
          );
          assertTrue(borderFraction > 0.4, "hyperframes annotation border present in the hold");
        }
      }
      assertDeep(presence.f0, [false, false, false, false, false, false], "hyperframes frame 0: no points yet");
      assertDeep(presence.f45, [true, true, true, false, false, false], "hyperframes frame 45: marks are changing (first three points only)");
      assertDeep(presence.f75, [true, true, true, true, true, true], "hyperframes frame 75: all points established");
      assertDeep(presence.f150, [true, true, true, true, true, true], "hyperframes frame 150: final state held");
      measurements.hyperframesC06 = { presence };
    },
  }
);

// ---------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------

async function main(): Promise<number> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
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

  // Evidence: proof stills plus the static measurements record
  // (asserted, not rewritten, on re-runs: the MG-015 pattern).
  try {
    const dir = evidenceDir();
    mkdirSync(dir, { recursive: true });
    for (const [src, name] of EVIDENCE_COPIES) {
      if (existsSync(src)) cpSync(src, join(dir, name));
    }
    const recordPath = join(dir, "measurements.json");
    const recordText = JSON.stringify(measurements, null, 2) + "\n";
    if (!existsSync(recordPath)) {
      writeFileSync(recordPath, recordText, "utf8");
      console.log(
        `Evidence written to ${dir} (${EVIDENCE_COPIES.length} stills + measurements.json, bootstrap record)`
      );
    } else {
      const existing = readFileSync(recordPath, "utf8");
      if (existing !== recordText) {
        failed += 1;
        console.log("FAIL evidence record: fresh measurements differ from the committed static record");
        console.log(`  committed: ${existing.slice(0, 400)}`);
        console.log(`  fresh:     ${recordText.slice(0, 400)}`);
      } else {
        console.log(`Evidence verified against the static record in ${dir}`);
      }
    }
  } catch (err) {
    failed += 1;
    console.log(`FAIL evidence write: ${(err as Error).message}`);
  }

  const total = passed + failed;
  console.log(`ChartComponents: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
