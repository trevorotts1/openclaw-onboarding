// End-to-end diagram still rendering through the real Remotion engine
// (Directive MG-017, deliverable 4).
//
// This harness renders a resolved diagram scene through the shared
// runtime's pinned Remotion install: the diagrams entry is bundled
// once per source-plus-runtime hash (the same discipline as the MG-006
// adapter), the composition is selected with the exact input props the
// stills use, and every still's PNG dimensions are verified against
// the scene canvas before any artifact is claimed. It is a diagrams
// harness, not a second adapter: production dispatch stays with the
// MG-004 adapter surface, and contracts-level dispatch for C04/C09 is
// the MG-025 integration note recorded by MG-018 and this item.

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import type { ResolvedFont } from "../../remotion/fonts";
import { readPngDimensions } from "../../remotion/decode";
import type { ResolvedDiagram } from "../frame";
import type { DiagramSceneDoc } from "../model";
import type { DiagramCompositionProps } from "./DiagramComposition";
import { DIAGRAM_COMPOSITION_ID } from "./ids";
import { resolveDiagramRuntime, type DiagramRuntime } from "./runtime";

interface BundlerModule {
  bundle: (options: Record<string, unknown>) => Promise<string>;
}
interface RendererModule {
  selectComposition: (options: Record<string, unknown>) => Promise<{
    id: string;
    width: number;
    height: number;
    fps: number;
    durationInFrames: number;
  }>;
  renderStill: (options: Record<string, unknown>) => Promise<void>;
}
interface WebpackConfigLike {
  resolve?: {
    modules?: string[];
    alias?: Record<string, string | false>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface DiagramStill {
  frame: number;
  path: string;
  sha256: string;
}

export interface DiagramRenderResult {
  runtime: DiagramRuntime;
  bundleKey: string;
  stills: DiagramStill[];
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sourceEntry(): string {
  const candidates = [
    resolve(__dirname, "entry.ts"),
    resolve(__dirname, "..", "..", "..", "..", "src", "diagrams", "render", "entry.ts"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  throw new Error(`diagram composition entry (entry.ts) not found near ${__dirname}.`);
}

function sourceHash(): string {
  const entry = sourceEntry();
  const dir = dirname(entry);
  const hash = createHash("sha256");
  const walk = (d: string): void => {
    for (const item of readdirSync(d, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name)
    )) {
      const p = join(d, item.name);
      if (item.isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(item.name)) {
        hash.update(item.name);
        hash.update(readFileSync(p));
      }
    }
  };
  walk(resolve(dir, ".."));
  return hash.digest("hex").slice(0, 24);
}

export async function renderDiagramStills(input: {
  doc: DiagramSceneDoc;
  resolved: ResolvedDiagram;
  font: ResolvedFont;
  frames: number[];
  outputDir: string;
  filePrefix: string;
  sharedRuntimeDir?: string;
}): Promise<DiagramRenderResult> {
  const runtime = resolveDiagramRuntime(input.sharedRuntimeDir);
  const req = createRequire(join(runtime.currentDir, "package.json"));
  const bundler = req("@remotion/bundler") as BundlerModule;
  const renderer = req("@remotion/renderer") as RendererModule;

  const bundleKey = `${sourceHash()}-${runtime.lockId ?? "nolock"}`;
  const bundleDir = join(runtime.stateDir, "mg017-bundles", bundleKey);
  let serveUrl = bundleDir;
  if (!existsSync(join(bundleDir, "index.html"))) {
    mkdirSync(bundleDir, { recursive: true });
    const nodeModules = join(runtime.currentDir, "node_modules");
    const applyResolution = (config: WebpackConfigLike): WebpackConfigLike => {
      config.resolve = config.resolve ?? {};
      config.resolve.modules = [...(config.resolve.modules ?? []), nodeModules];
      config.resolve.alias = {
        ...(config.resolve.alias ?? {}),
        react: join(nodeModules, "react"),
        "react-dom": join(nodeModules, "react-dom"),
        remotion: join(nodeModules, "remotion"),
      };
      return config;
    };
    serveUrl = await bundler.bundle({
      entryPoint: sourceEntry(),
      outDir: bundleDir,
      onProgress: () => undefined,
      webpackOverride: applyResolution,
      rspackOverride: applyResolution,
    });
  }

  const props: DiagramCompositionProps = {
    resolved: input.resolved,
    headline: input.doc.copy.headline,
    disclosure: input.doc.copy.disclosure,
    durationFrames: input.doc.duration_frames,
    font: {
      family: input.font.family,
      files: input.font.files.map((file) => ({ weight: file.weight, base64: file.base64 })),
    },
  };
  const composition = await renderer.selectComposition({
    serveUrl,
    id: DIAGRAM_COMPOSITION_ID,
    inputProps: props,
    browserExecutable: runtime.browserExecutable,
  });
  if (
    composition.width !== input.doc.diagram.canvas.width ||
    composition.height !== input.doc.diagram.canvas.height ||
    composition.fps !== input.doc.diagram.canvas.fps ||
    composition.durationInFrames !== input.doc.duration_frames
  ) {
    throw new Error(
      `composition metadata ${composition.width}x${composition.height} at ${composition.fps} fps ` +
        `for ${composition.durationInFrames} frames disagrees with the scene document ` +
        `(${input.doc.diagram.canvas.width}x${input.doc.diagram.canvas.height} at ` +
        `${input.doc.diagram.canvas.fps} fps for ${input.doc.duration_frames} frames).`
    );
  }

  mkdirSync(input.outputDir, { recursive: true });
  const stills: DiagramStill[] = [];
  for (const frame of input.frames) {
    if (!Number.isInteger(frame) || frame < 0 || frame >= input.doc.duration_frames) {
      throw new Error(`still frame ${frame} lies outside the scene's frames 0..${input.doc.duration_frames - 1}.`);
    }
    const output = join(input.outputDir, `${input.filePrefix}-f${frame}.png`);
    await renderer.renderStill({
      composition,
      serveUrl,
      frame,
      output,
      inputProps: props,
      browserExecutable: runtime.browserExecutable,
      imageFormat: "png",
      overwrite: true,
      timeoutInMilliseconds: 240_000,
    });
    const dims = readPngDimensions(output);
    if (!dims || dims.width !== input.doc.diagram.canvas.width || dims.height !== input.doc.diagram.canvas.height) {
      throw new Error(
        `rendered still ${output} has dimensions ${dims ? `${dims.width}x${dims.height}` : "unreadable"}, ` +
          `expected ${input.doc.diagram.canvas.width}x${input.doc.diagram.canvas.height}.`
      );
    }
    stills.push({ frame, path: output, sha256: sha256File(output) });
  }
  return { runtime, bundleKey, stills };
}
