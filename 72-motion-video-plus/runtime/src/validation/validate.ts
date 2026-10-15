// Schema validation for the Skill 72 Motion Graphics V2 contracts.
//
// The canonical contract is references/contracts-v2.schema.json (JSON Schema
// Draft 2020-12, $id urn:blackceo:motion:contracts:2.0). This module loads
// that checked-in file at runtime and compiles one Ajv 2020-12 validator per
// $defs entry. The schema text is used exactly as checked in; in particular
// its path patterns carry escaped backslashes that reject Windows-style
// separators, and Ajv handles them as written. Do not rewrite the schema.

import Ajv2020, { ErrorObject, ValidateFunction } from "ajv/dist/2020";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export interface SchemaValidationError {
  /** JSON Pointer into the validated document ("" means the root). */
  instancePath: string;
  /** JSON Pointer into the schema that produced the error. */
  schemaPath: string;
  keyword: string;
  message: string;
  params: Record<string, unknown>;
}

export type ContractsSchema = Record<string, unknown> & {
  $defs: Record<string, unknown>;
};

let cachedSchema: ContractsSchema | null = null;
let cachedSchemaPath: string | null = null;
const validators = new Map<string, ValidateFunction>();

/** Resolve the checked-in contracts schema path. */
export function contractsSchemaPath(): string {
  if (cachedSchemaPath) return cachedSchemaPath;
  const override = process.env.MOTION_CONTRACTS_SCHEMA;
  if (override) {
    cachedSchemaPath = resolve(override);
    return cachedSchemaPath;
  }
  // Walk up from this module (runtime/src/validation in source form, or
  // runtime/dist/src/validation once compiled) until a directory holding
  // references/contracts-v2.schema.json is found. That directory is the
  // skill root, 72-motion-video-plus/.
  let dir = __dirname;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "references", "contracts-v2.schema.json");
    if (existsSync(candidate)) {
      cachedSchemaPath = candidate;
      return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    "contracts-v2.schema.json not found above " +
      __dirname +
      "; set MOTION_CONTRACTS_SCHEMA to its path."
  );
}

/** Load and cache the parsed contracts schema. */
export function loadContractsSchema(): ContractsSchema {
  if (cachedSchema) return cachedSchema;
  const parsed = JSON.parse(readFileSync(contractsSchemaPath(), "utf8")) as ContractsSchema;
  if (!parsed.$defs || typeof parsed.$defs !== "object") {
    throw new Error("contracts-v2.schema.json has no $defs object.");
  }
  cachedSchema = parsed;
  return parsed;
}

/** Names of every $defs entry in the contracts schema. */
export function contractDefNames(): string[] {
  return Object.keys(loadContractsSchema().$defs);
}

function validatorFor(defName: string): ValidateFunction {
  const hit = validators.get(defName);
  if (hit) return hit;
  const schema = loadContractsSchema();
  if (!(defName in schema.$defs)) {
    throw new Error(
      `Unknown contracts $defs entry "${defName}". Known: ${contractDefNames().join(", ")}`
    );
  }
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  // Compile a wrapper whose root points at the requested def. The full $defs
  // travel with the wrapper so internal "#/$defs/..." references resolve
  // exactly as they do inside the canonical document.
  const wrapper: Record<string, unknown> = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $defs: schema.$defs,
    $ref: `#/$defs/${defName}`,
  };
  const validate = ajv.compile(wrapper);
  validators.set(defName, validate);
  return validate;
}

/**
 * Validate a document against one $defs entry of the contracts schema.
 * Returns structured errors; an empty array means the document is valid.
 */
export function validateAgainstDef(defName: string, doc: unknown): SchemaValidationError[] {
  const validate = validatorFor(defName);
  if (validate(doc)) return [];
  return (validate.errors ?? []).map((e: ErrorObject) => ({
    instancePath: e.instancePath ?? "",
    schemaPath: e.schemaPath ?? "",
    keyword: e.keyword,
    message: e.message ?? "schema validation failed",
    params: (e.params ?? {}) as Record<string, unknown>,
  }));
}

const adhocValidators = new Map<string, ValidateFunction>();

/**
 * Validate a document against an ad hoc subschema of the contracts schema
 * (for example one if/then branch). The contracts $defs are attached so
 * internal "#/$defs/..." references resolve. Results are cached by the
 * subschema text.
 */
export function validateWithSchema(subschema: unknown, doc: unknown): SchemaValidationError[] {
  const key = JSON.stringify(subschema);
  let validate = adhocValidators.get(key);
  if (!validate) {
    const schema = loadContractsSchema();
    const wrapped: Record<string, unknown> = {
      ...(subschema as Record<string, unknown>),
      $defs: schema.$defs,
    };
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    validate = ajv.compile(wrapped);
    adhocValidators.set(key, validate);
  }
  if (validate(doc)) return [];
  return (validate.errors ?? []).map((e: ErrorObject) => ({
    instancePath: e.instancePath ?? "",
    schemaPath: e.schemaPath ?? "",
    keyword: e.keyword,
    message: e.message ?? "schema validation failed",
    params: (e.params ?? {}) as Record<string, unknown>,
  }));
}

export interface ConditionalClause {
  if: Record<string, unknown>;
  then?: Record<string, unknown>;
  else?: Record<string, unknown>;
}

function isModeConditional(clause: unknown): clause is ConditionalClause {
  if (typeof clause !== "object" || clause === null) return false;
  const c = clause as Record<string, unknown>;
  const ifSchema = c.if as Record<string, unknown> | undefined;
  if (!ifSchema || typeof ifSchema !== "object") return false;
  const props = ifSchema.properties as Record<string, unknown> | undefined;
  return !!props && typeof props === "object" && "mode" in props;
}

/**
 * The manifest $def carries mode-agreement rules as if/then allOf clauses
 * whose condition tests the delivery "mode" field (content scope per mode,
 * PowerPoint audio, VSL parent and inherited audio). Section 16.9 assigns
 * mode disagreement to MG_MODE_MISMATCH, not MG_SCHEMA_INVALID, so the
 * contracts layer validates those clauses separately from the core schema:
 *
 * - coreManifestSchema(): the manifest def with the mode-conditional
 *   clauses removed. Violations are MG_SCHEMA_INVALID.
 * - modeConditionalClauses(): the removed clauses. When a clause's "if"
 *   matches a document, violations of its "then" (or of its "else" when
 *   the "if" does not match) are MG_MODE_MISMATCH.
 */
export function coreManifestSchema(): Record<string, unknown> {
  const schema = loadContractsSchema();
  const manifestDef = schema.$defs.manifest as Record<string, unknown>;
  const clauses = Array.isArray(manifestDef.allOf) ? manifestDef.allOf : [];
  const core: Record<string, unknown> = {
    ...manifestDef,
    allOf: clauses.filter((c) => !isModeConditional(c)),
  };
  return core;
}

export function modeConditionalClauses(): ConditionalClause[] {
  const schema = loadContractsSchema();
  const manifestDef = schema.$defs.manifest as Record<string, unknown>;
  const clauses = Array.isArray(manifestDef.allOf) ? manifestDef.allOf : [];
  return clauses.filter(isModeConditional);
}
