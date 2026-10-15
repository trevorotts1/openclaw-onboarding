// Role tokens for the typography hierarchy (Directive MG-013).
//
// The canonical table lives in references/typography-tokens.json so design
// documents and code read the same numbers. It is loaded, never copied: if
// the file is missing or malformed, loading throws rather than letting the
// audit run on remembered values.

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { TypographyError } from "./font-metrics";

export interface RoleException {
  id: string;
  bound: string;
}

export interface RoleToken {
  role: string;
  purpose: string;
  essential: boolean;
  minPx: number;
  maxPx: number;
  floorPx: number;
  exception: RoleException | null;
  measurementBasis: string;
}

export interface TypographyTokens {
  statement: string;
  substitutionLaw: string;
  overflowLaw: string;
  roles: RoleToken[];
  role(role: string): RoleToken | null;
}

interface RawRole {
  role: string;
  purpose: string;
  essential: boolean;
  min_px: number;
  max_px: number;
  floor_px: number;
  exception: RoleException | null;
  measurement_basis: string;
}

export function tokensPath(): string {
  const override = process.env.MOTION_TYPOGRAPHY_TOKENS;
  if (override) return resolve(override);
  // Compiled module lives at runtime/dist/src/typography; the skill root is
  // four levels up. When run from source under ts-node the same relative
  // shape holds one level shallower, so probe both.
  const candidates = [
    resolve(__dirname, "..", "..", "..", "..", "references", "typography-tokens.json"),
    resolve(__dirname, "..", "..", "..", "references", "typography-tokens.json"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return candidates[0];
}

export function loadTypographyTokens(path: string = tokensPath()): TypographyTokens {
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(path, "utf8")) as unknown;
  } catch {
    throw new TypographyError(
      "TYPO_TOKENS_MISSING",
      `Typography tokens file could not be read: ${path}. The role table is loaded from references/typography-tokens.json, never remembered.`
    );
  }
  const doc = raw as {
    statement?: string;
    substitution_law?: string;
    overflow_law?: string;
    roles?: RawRole[];
  };
  if (!doc.roles || !Array.isArray(doc.roles) || doc.roles.length === 0) {
    throw new TypographyError(
      "TYPO_TOKENS_MISSING",
      `Typography tokens file ${path} declares no roles.`
    );
  }
  const roles: RoleToken[] = doc.roles.map((r) => ({
    role: r.role,
    purpose: r.purpose,
    essential: r.essential,
    minPx: r.min_px,
    maxPx: r.max_px,
    floorPx: r.floor_px,
    exception: r.exception ?? null,
    measurementBasis: r.measurement_basis,
  }));
  return {
    statement: doc.statement ?? "",
    substitutionLaw: doc.substitution_law ?? "",
    overflowLaw: doc.overflow_law ?? "",
    roles,
    role(name: string): RoleToken | null {
      return roles.find((r) => r.role === name) ?? null;
    },
  };
}
