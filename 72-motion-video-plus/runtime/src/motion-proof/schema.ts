// Loading and validating motion proof case documents against the
// MG-032 schema (references/motion-assertion-schema.json). The schema
// file is the single source of truth for the case shape; this module
// finds it by walking up from the module directory to the skill root,
// the same discipline as the contracts schema loader (MG-007).

import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { MotionProofCase } from "./types";

let cachedSchemaPath: string | null = null;
let cachedValidator: ValidateFunction | null = null;

export function motionAssertionSchemaPath(): string {
  if (cachedSchemaPath) return cachedSchemaPath;
  const override = process.env.MOTION_ASSERTION_SCHEMA;
  if (override) {
    cachedSchemaPath = resolve(override);
    return cachedSchemaPath;
  }
  let dir = __dirname;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "references", "motion-assertion-schema.json");
    if (existsSync(candidate)) {
      cachedSchemaPath = candidate;
      return cachedSchemaPath;
    }
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    "motion-assertion-schema.json not found walking up from " + __dirname
  );
}

export function loadMotionAssertionSchema(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(motionAssertionSchemaPath(), "utf8")
  ) as Record<string, unknown>;
}

function caseValidator(): ValidateFunction {
  if (cachedValidator === null) {
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    cachedValidator = ajv.compile(loadMotionAssertionSchema());
  }
  return cachedValidator;
}

/**
 * Validate an unknown value as a motion proof case. Returns the typed
 * case plus a list of problems; the case is null when problems exist.
 */
export function validateMotionProofCase(
  doc: unknown
): { caseDoc: MotionProofCase | null; problems: string[] } {
  const validate = caseValidator();
  if (validate(doc)) {
    return { caseDoc: doc as MotionProofCase, problems: [] };
  }
  const problems = (validate.errors ?? []).map(
    (error) => `${error.instancePath || "/"} ${error.message ?? error.keyword}`.trim()
  );
  return { caseDoc: null, problems };
}
