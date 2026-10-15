// Shared project materialization for the Hyperframes adapter (MG-005).
//
// A Hyperframes project is a directory with an index.html composition, a
// hyperframes.json config, a meta.json, and local assets. Everything a
// generated project needs is vendored locally from measured sources: GSAP
// 3.15.0 comes from the shared runtime install (never a CDN, compositions
// must not fetch the network), and the fixture font is resolved to actual
// local font bytes with their hashes recorded. No silent substitution: an
// unresolvable font or a missing vendored asset is a hard structured
// failure, per Directive M06 and the fixture assets contract
// (substitution: "forbidden").

import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { AdapterError } from "../adapters/types";

/** The shared-runtime locations the adapter depends on. Resolved once by
 * the adapter from the runtime lock; generators never guess paths. */
export interface SharedRuntimePaths {
  runtimeRoot: string;
  /** The promoted install: .runtime/current resolved to a real directory. */
  currentDir: string;
  /** Basename of currentDir, for example "lock-314fc289b233ca9e". */
  runtimeLockId: string;
  lockPath: string;
  cliBin: string;
  gsapPath: string;
}

export interface FontFileRecord {
  weight: number;
  sourcePath: string;
  fileName: string;
  sha256: string;
}

export interface ResolvedFont {
  /** The assets-contract alias, for example "font-fixture-sans". */
  alias: string;
  /** The CSS family name generated projects use. */
  cssFamily: string;
  files: FontFileRecord[];
}

export function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function sha256Text(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

interface FontCandidate {
  weight: number;
  paths: string[];
}

/**
 * The fixture-sans registry. The V2 fixture assets contract names exactly
 * one font requirement (font-fixture-sans, alias fixture-sans, weights 400
 * and 700, substitution forbidden). On this platform the alias resolves to
 * Liberation Sans, whose regular and bold bytes are installed system
 * fonts; DejaVu Sans is the documented fallback candidate if Liberation
 * is absent. Any other alias is unresolved by definition until a later
 * item registers it.
 */
const FONT_REGISTRY: Record<string, { cssFamily: string; candidates: FontCandidate[] }> = {
  "font-fixture-sans": {
    cssFamily: "FixtureSans",
    candidates: [
      {
        weight: 400,
        paths: [
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
      },
      {
        weight: 700,
        paths: [
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
      },
    ],
  },
};

/** Resolve a font alias to actual local bytes, or throw a structured
 * failure naming the alias. Returns paths plus content hashes so evidence
 * can prove which bytes were used (M06, M16). */
export function resolveFont(alias: string): ResolvedFont {
  const entry = FONT_REGISTRY[alias];
  if (!entry) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "hyperframes",
      message:
        `Font alias "${alias}" is not in the runtime font registry. Registered: ` +
        `${Object.keys(FONT_REGISTRY).join(", ")}. Register the font with actual ` +
        "local bytes before rendering; substitution is forbidden.",
    });
  }
  const files: FontFileRecord[] = [];
  for (const candidate of entry.candidates) {
    const found = candidate.paths.find((p) => existsSync(p));
    if (!found) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: "hyperframes",
        message:
          `Font alias "${alias}" weight ${candidate.weight} could not be resolved ` +
          `to local font bytes. Looked for: ${candidate.paths.join(", ")}. ` +
          "Silent substitution is forbidden; install the font or register its path.",
      });
    }
    files.push({
      weight: candidate.weight,
      sourcePath: found,
      fileName: basename(found),
      sha256: sha256File(found),
    });
  }
  return { alias, cssFamily: entry.cssFamily, files };
}

/** The @font-face block generated projects embed. The font files are
 * copied into the project's fonts/ directory by vendorIntoProject. */
export function fontFaceCss(font: ResolvedFont): string {
  return font.files
    .map(
      (f) =>
        `@font-face {\n  font-family: "${font.cssFamily}";\n  src: url("./fonts/${f.fileName}") format("truetype");\n  font-weight: ${f.weight};\n  font-style: normal;\n}`
    )
    .join("\n");
}

/**
 * Write the project shell files and vendor the local dependencies every
 * generated composition needs: GSAP from the shared runtime install and
 * the resolved font bytes. Deterministic content only; meta.json carries
 * no timestamps so a regenerated source bundle is byte-stable.
 */
export function vendorIntoProject(
  projectDir: string,
  projectId: string,
  runtime: SharedRuntimePaths,
  font: ResolvedFont
): void {
  mkdirSync(join(projectDir, "vendor"), { recursive: true });
  mkdirSync(join(projectDir, "fonts"), { recursive: true });
  mkdirSync(join(projectDir, "assets"), { recursive: true });
  mkdirSync(join(projectDir, "compositions"), { recursive: true });
  if (!existsSync(runtime.gsapPath)) {
    throw new AdapterError({
      category: "MG_ENGINE_MISSING",
      engine: "hyperframes",
      message:
        `GSAP bundle not found in the shared runtime install at ${runtime.gsapPath}. ` +
        "The shared runtime is provisioned without its pinned GSAP package; " +
        "re-run shared-utils/motion-render-runtime/provision.sh.",
    });
  }
  copyFileSync(runtime.gsapPath, join(projectDir, "vendor", "gsap.min.js"));
  for (const f of font.files) {
    copyFileSync(f.sourcePath, join(projectDir, "fonts", f.fileName));
  }
  // autoProxy stays off: adapter-generated media is browser-native by
  // construction (locally encoded H.264/yuv420p), and a proxy transcode
  // would change pixels and timing without any record in the receipt.
  writeFileSync(
    join(projectDir, "hyperframes.json"),
    JSON.stringify(
      {
        paths: { blocks: "compositions", components: "compositions/components", assets: "assets" },
        media: { autoProxy: false },
      },
      null,
      2
    ) + "\n",
    "utf8"
  );
  writeFileSync(
    join(projectDir, "meta.json"),
    JSON.stringify({ id: projectId, name: projectId, generator: "skill72-mg005" }, null, 2) + "\n",
    "utf8"
  );
}

/** Escape a string for an HTML text node or a double-quoted attribute. */
export function esc(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Serialize data for embedding inside a <script> block, safely. */
export function embeddedJson(value: unknown): string {
  return JSON.stringify(value).replace(/<\//g, "<\\/");
}

/** Seconds for a frame count at a frame rate, as the decimal string the
 * composition attributes carry (frame-exact for the rates in use). */
export function seconds(frames: number, fps: number): number {
  return frames / fps;
}

export function secondsAttr(frames: number, fps: number): string {
  const value = frames / fps;
  return Number.isInteger(value) ? String(value) : value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}
