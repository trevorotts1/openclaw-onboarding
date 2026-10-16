// Font resolution for the Remotion production adapter (Directive MG-006).
//
// Job assets declare font requirements by alias (the fixture design uses
// font_ref "font-fixture-sans"; the assets document names the requirement
// id with family_alias "fixture-sans" and substitution "forbidden").
// Substitution is forbidden by contract, so resolution is a lookup of
// actual local font bytes for the alias and each required weight. When
// the bytes cannot be found, resolution fails with a structured error
// naming the alias, the weight and the directories searched; the adapter
// never falls back to a different family silently.
//
// The registry maps the fixture alias to Liberation Sans, which is
// installed on this box under /usr/share/fonts/truetype/liberation (and
// is part of the shared runtime's documented apt set). DejaVu Sans is the
// second search root. The resolved bytes travel into the composition as
// base64 input props, and their sha256 is recorded in render evidence.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { AdapterError } from "../adapters/types";

export interface ResolvedFontFile {
  weight: number;
  /** Absolute path of the exact font file whose bytes are used. */
  path: string;
  sha256: string;
  /** The file bytes, base64 encoded for transport in input props. */
  base64: string;
}

export interface ResolvedFont {
  /** The assets-document requirement id, for example "font-fixture-sans". */
  requirementId: string;
  /** The family alias from the assets document, for example "fixture-sans". */
  alias: string;
  /** The CSS family name the composition registers the faces under. */
  family: string;
  files: ResolvedFontFile[];
}

interface AliasRegistration {
  family: string;
  /** File name per weight within a search directory. */
  fileByWeight: Record<number, string>;
}

/** Aliases with known local bytes. An alias absent here cannot resolve
 * and fails loudly rather than substituting another family. */
const ALIAS_REGISTRY: Record<string, AliasRegistration> = {
  "fixture-sans": {
    family: "Liberation Sans",
    fileByWeight: {
      400: "LiberationSans-Regular.ttf",
      700: "LiberationSans-Bold.ttf",
    },
  },
};

export const DEFAULT_FONT_SEARCH_DIRS: string[] = [
  "/usr/share/fonts/truetype/liberation",
  "/usr/share/fonts/truetype/dejavu",
];

/**
 * Resolve a font requirement to actual local bytes for every required
 * weight. Throws AdapterError (MG_SCHEMA_INVALID) when the alias is
 * unregistered or any weight's file is missing from every search dir.
 */
export function resolveFont(
  requirementId: string,
  alias: string,
  weights: number[],
  searchDirs: string[] = DEFAULT_FONT_SEARCH_DIRS
): ResolvedFont {
  const registration = ALIAS_REGISTRY[alias];
  if (!registration) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      engine: "remotion",
      message:
        `Font requirement "${requirementId}" names family alias "${alias}", which has no ` +
        "registered local font bytes. Substitution is forbidden by the job's font " +
        "requirements, so rendering cannot proceed until the alias is registered with " +
        "real font files.",
    });
  }
  const files: ResolvedFontFile[] = [];
  for (const weight of weights) {
    const fileName = registration.fileByWeight[weight];
    if (!fileName) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: "remotion",
        message:
          `Font alias "${alias}" (${registration.family}) has no registered file for ` +
          `weight ${weight}; required weights are ${weights.join(", ")}.`,
      });
    }
    let found: string | null = null;
    for (const dir of searchDirs) {
      const candidate = join(dir, fileName);
      if (existsSync(candidate)) {
        found = candidate;
        break;
      }
    }
    if (!found) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: "remotion",
        message:
          `Font file for alias "${alias}" weight ${weight} (${fileName}) was not found in ` +
          `any search directory: ${searchDirs.join(", ")}. The job forbids font ` +
          "substitution, so the render fails instead of silently using another font.",
      });
    }
    const bytes = readFileSync(found);
    files.push({
      weight,
      path: found,
      sha256: createHash("sha256").update(bytes).digest("hex"),
      base64: bytes.toString("base64"),
    });
  }
  return { requirementId, alias, family: registration.family, files };
}
