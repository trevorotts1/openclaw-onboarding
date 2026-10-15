// Capability matrix handling for Skill 72 Motion Graphics V2 (MG-004).
//
// The matrix lives at references/renderer-capabilities.json and states what
// each renderer can do on this machine. It is a consumer-side contract for
// the shared runtime's records: MG-002's SKILL.md promises that an adapter
// counts as ready only when the shared runtime holds a current capability
// record and a successful launch record for it. This module loads and
// validates the matrix, and refreshes it from runtime probe records
// (the shared provisioner, MG-003, writes a runtime lock carrying measured
// versions and probe results).
//
// HONESTY RULES, enforced by validateCapabilityMatrix:
// - A record may claim probeStatus "ready" only with a non-null installed
//   version, a non-null runtime lock identity, a probe timestamp, and at
//   least one evidence note. Readiness is never asserted from a document
//   classification alone.
// - "unprobed" records must carry null version fields and empty capability
//   lists: an unprobed engine confirms nothing.
// - Until a real probe record exists on disk, the checked-in matrix marks
//   every engine unprobed. Do not hand-edit a record to "ready"; refresh
//   from a runtime record instead.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import {
  AdapterError,
  ALL_ENGINES,
  CapabilityMatrix,
  Engine,
  EngineCapabilityRecord,
} from "./types";

let cachedMatrixPath: string | null = null;

/** Resolve the checked-in capability matrix path. */
export function capabilityMatrixPath(): string {
  if (cachedMatrixPath) return cachedMatrixPath;
  const override = process.env.MOTION_CAPABILITIES_PATH;
  if (override) {
    cachedMatrixPath = resolve(override);
    return cachedMatrixPath;
  }
  // Walk up from this module (runtime/src/adapters in source form, or
  // runtime/dist/src/adapters once compiled) to the skill root, the
  // directory holding references/renderer-capabilities.json.
  let dir = __dirname;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "references", "renderer-capabilities.json");
    if (existsSync(candidate)) {
      cachedMatrixPath = candidate;
      return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new AdapterError({
    category: "MG_ENGINE_MISSING",
    message:
      "renderer-capabilities.json not found above " +
      __dirname +
      "; set MOTION_CAPABILITIES_PATH to its path.",
  });
}

function unprobedRecord(engine: Engine): EngineCapabilityRecord {
  return {
    engine,
    probeStatus: "unprobed",
    installedVersion: null,
    runtimeLockId: null,
    probedAt: null,
    platform: null,
    codecs: [],
    transparency: { alphaVideo: false, profiles: [] },
    mediaTypes: [],
    features3d: [],
    evidence: [],
  };
}

/** A matrix that states nothing: every engine unprobed, no versions, no
 * evidence. This is the correct content until probe records exist. */
export function emptyCapabilityMatrix(source: string): CapabilityMatrix {
  return {
    schemaVersion: "1.0",
    generatedAt: null,
    source,
    engines: ALL_ENGINES.map(unprobedRecord),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/**
 * Structural and honesty validation of a capability matrix document.
 * Returns a list of problems; an empty list means the document is a valid
 * matrix that routing may consume.
 */
export function validateCapabilityMatrix(doc: unknown): string[] {
  const problems: string[] = [];
  if (!isRecord(doc)) return ["capability matrix must be a JSON object"];
  if (doc.schemaVersion !== "1.0") {
    problems.push(`schemaVersion must be "1.0", got ${JSON.stringify(doc.schemaVersion)}`);
  }
  if (!Array.isArray(doc.engines)) {
    problems.push("engines must be an array");
    return problems;
  }
  const seen = new Set<string>();
  for (const raw of doc.engines) {
    if (!isRecord(raw)) {
      problems.push("each engine record must be an object");
      continue;
    }
    const engine = raw.engine;
    if (typeof engine !== "string" || !(ALL_ENGINES as string[]).includes(engine)) {
      problems.push(`unknown engine in matrix: ${JSON.stringify(engine)}`);
      continue;
    }
    if (seen.has(engine)) problems.push(`duplicate record for engine ${engine}`);
    seen.add(engine);
    const status = raw.probeStatus;
    if (status !== "ready" && status !== "unprobed" && status !== "unavailable") {
      problems.push(`${engine}: probeStatus must be ready, unprobed, or unavailable`);
      continue;
    }
    for (const field of ["codecs", "mediaTypes", "features3d", "evidence"] as const) {
      if (!isStringArray(raw[field])) problems.push(`${engine}: ${field} must be an array of strings`);
    }
    if (!isRecord(raw.transparency) || typeof raw.transparency.alphaVideo !== "boolean") {
      problems.push(`${engine}: transparency.alphaVideo must be a boolean`);
    }
    if (status === "ready") {
      if (typeof raw.installedVersion !== "string" || raw.installedVersion.length === 0) {
        problems.push(`${engine}: a ready record must name the measured installed version`);
      }
      if (typeof raw.runtimeLockId !== "string" || raw.runtimeLockId.length === 0) {
        problems.push(`${engine}: a ready record must name its runtime lock identity`);
      }
      if (typeof raw.probedAt !== "string" || raw.probedAt.length === 0) {
        problems.push(`${engine}: a ready record must carry its probe timestamp`);
      }
      if (!isStringArray(raw.evidence) || raw.evidence.length === 0) {
        problems.push(`${engine}: a ready record must carry at least one evidence note`);
      }
    }
    if (status === "unprobed") {
      if (raw.installedVersion !== null || raw.runtimeLockId !== null || raw.probedAt !== null) {
        problems.push(`${engine}: an unprobed record must carry null version fields`);
      }
      if (
        (Array.isArray(raw.codecs) && raw.codecs.length > 0) ||
        (Array.isArray(raw.features3d) && raw.features3d.length > 0) ||
        (isRecord(raw.transparency) && raw.transparency.alphaVideo === true)
      ) {
        problems.push(`${engine}: an unprobed record confirms no capabilities`);
      }
    }
  }
  for (const engine of ALL_ENGINES) {
    if (!seen.has(engine)) problems.push(`matrix has no record for engine ${engine}`);
  }
  return problems;
}

/** Parse and validate a capability matrix document. Throws AdapterError
 * (MG_SCHEMA_INVALID, exit class 2) when the document is malformed or
 * violates the honesty rules. */
export function parseCapabilityMatrix(doc: unknown): CapabilityMatrix {
  const problems = validateCapabilityMatrix(doc);
  if (problems.length > 0) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      message: `Invalid capability matrix: ${problems.join("; ")}`,
    });
  }
  return doc as CapabilityMatrix;
}

/** Load the capability matrix from disk (the checked-in path by default). */
export function loadCapabilityMatrix(path?: string): CapabilityMatrix {
  const resolved = path ? resolve(path) : capabilityMatrixPath();
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(resolved, "utf8"));
  } catch (err) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      message: `Capability matrix at ${resolved} is not valid JSON: ${(err as Error).message}`,
    });
  }
  return parseCapabilityMatrix(parsed);
}

/** The record for one engine, or null when the matrix has none. */
export function capabilityRecord(
  matrix: CapabilityMatrix,
  engine: Engine
): EngineCapabilityRecord | null {
  return matrix.engines.find((r) => r.engine === engine) ?? null;
}

/**
 * One engine's measured runtime record, as produced by the shared runtime
 * provisioner (MG-003): the runtime lock carries the measured version, the
 * probe outcome, and per-engine probe results. Refresh consumes these
 * records; nothing else may create a "ready" matrix entry.
 */
export interface RuntimeProbeRecord {
  engine: Engine;
  /** Measured installed version from the runtime lock. */
  version: string;
  /** Identity of the runtime lock the measurement came from. */
  runtimeLockId: string;
  /** ISO timestamp of the probe. */
  probedAt: string;
  platform: string;
  /** True only when the probe included a successful launch. */
  launchSucceeded: boolean;
  codecs: string[];
  transparency: { alphaVideo: boolean; profiles: string[] };
  mediaTypes: string[];
  features3d: string[];
  evidence: string[];
}

/**
 * Build a refreshed matrix from runtime probe records. A record turns its
 * engine "ready" only when the probe measured a version AND a launch
 * succeeded; a probe without a successful launch records "unavailable".
 * Engines without a record keep their previous state (unprobed in the
 * shipped matrix).
 */
export function buildMatrixFromProbeRecords(
  records: RuntimeProbeRecord[],
  base?: CapabilityMatrix
): CapabilityMatrix {
  const matrix: CapabilityMatrix = base
    ? { ...base, engines: base.engines.map((r) => ({ ...r })) }
    : emptyCapabilityMatrix("runtime probe records");
  for (const probe of records) {
    const idx = matrix.engines.findIndex((r) => r.engine === probe.engine);
    if (idx < 0) continue;
    if (probe.launchSucceeded && probe.version) {
      matrix.engines[idx] = {
        engine: probe.engine,
        probeStatus: "ready",
        installedVersion: probe.version,
        runtimeLockId: probe.runtimeLockId,
        probedAt: probe.probedAt,
        platform: probe.platform,
        codecs: probe.codecs,
        transparency: probe.transparency,
        mediaTypes: probe.mediaTypes,
        features3d: probe.features3d,
        evidence: probe.evidence,
      };
    } else {
      matrix.engines[idx] = {
        ...unprobedRecord(probe.engine),
        probeStatus: "unavailable",
        evidence: probe.evidence,
      };
    }
  }
  matrix.generatedAt = new Date().toISOString();
  matrix.source = "shared runtime probe records (runtime lock)";
  const problems = validateCapabilityMatrix(matrix);
  if (problems.length > 0) {
    throw new AdapterError({
      category: "MG_SCHEMA_INVALID",
      message: `Refreshed capability matrix is invalid: ${problems.join("; ")}`,
    });
  }
  return matrix;
}

/** Refresh the matrix file on disk from runtime probe records, and return
 * the refreshed matrix. This is the generator path for
 * references/renderer-capabilities.json. */
export function refreshCapabilityMatrix(
  records: RuntimeProbeRecord[],
  path?: string
): CapabilityMatrix {
  const resolved = path ? resolve(path) : capabilityMatrixPath();
  let base: CapabilityMatrix | undefined;
  if (existsSync(resolved)) {
    try {
      base = loadCapabilityMatrix(resolved);
    } catch {
      base = undefined;
    }
  }
  const matrix = buildMatrixFromProbeRecords(records, base);
  writeFileSync(resolved, JSON.stringify(matrix, null, 2) + "\n", "utf8");
  return matrix;
}
