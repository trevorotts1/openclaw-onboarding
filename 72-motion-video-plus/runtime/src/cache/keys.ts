// Cache key derivation for MG-027: canonical serialization plus
// sha256 over every input class that can change a scene's pixels.
// Two revisions share a key only when all of it matches: scene
// source, props, asset contents, font contents, data contents, the
// compiled timing (MG-021 timeline plus sidecar), geometry, fps,
// export settings, adapter and compiler versions, and the runtime
// lock id. The derivation is pure and deterministic: the same inputs
// always produce the same key on any machine, and key equality is
// the only reuse signal the session trusts (state alone never is).

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import {
  CacheFindings,
  type SceneKeyClassDigests,
  type SceneKeyInputs,
} from "./types";

export function sha256Hex(data: string | Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

/** Canonical JSON: object keys sorted recursively, arrays in order,
 * undefined object members dropped (JSON semantics). Two values with
 * the same canonical form are the same input for key purposes. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map((v) => canonicalJson(v)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record)
    .filter((k) => record[k] !== undefined)
    .sort();
  const parts = keys.map(
    (k) => `${JSON.stringify(k)}:${canonicalJson(record[k])}`
  );
  return `{${parts.join(",")}}`;
}

export function hashCanonical(value: unknown): string {
  return sha256Hex(canonicalJson(value));
}

/** A hash map (id to digest) as sorted pairs, so insertion order can
 * never move a key. */
function sortedPairs(map: Record<string, string>): [string, string][] {
  return Object.keys(map)
    .sort()
    .map((k) => [k, map[k]] as [string, string]);
}

/** Sentinel hashed in place of an absent input file. An absent asset,
 * font, or data file therefore changes the key instead of being
 * silently dropped from it: the render that follows fails on the
 * missing input in the open, never reuses a complete-input revision. */
export const ABSENT_INPUT_SENTINEL = "mg027-absent-input";

export function hashFileOrSentinel(absPath: string): {
  hash: string;
  absent: boolean;
} {
  if (!existsSync(absPath)) {
    return { hash: sha256Hex(`${ABSENT_INPUT_SENTINEL}:${absPath}`), absent: true };
  }
  return { hash: sha256Hex(readFileSync(absPath)), absent: false };
}

/** Hash a set of declared input files (assets, data documents) for
 * key derivation. Absent files contribute the absent sentinel and a
 * MG_CACHE_INPUT_ABSENT finding; the caller decides whether absence
 * is fatal for its own layer, but the key always changes. */
export function hashInputFiles(entries: { id: string; absPath: string }[]): {
  hashes: Record<string, string>;
  findings: { category: typeof CacheFindings.InputAbsent; sceneId: null; message: string }[];
} {
  const hashes: Record<string, string> = {};
  const findings: {
    category: typeof CacheFindings.InputAbsent;
    sceneId: null;
    message: string;
  }[] = [];
  for (const entry of entries) {
    const result = hashFileOrSentinel(entry.absPath);
    hashes[entry.id] = result.hash;
    if (result.absent) {
      findings.push({
        category: CacheFindings.InputAbsent,
        sceneId: null,
        message:
          `Key input ${entry.id} is absent at ${entry.absPath}; the absent ` +
          "sentinel was hashed into the key so this revision cannot reuse " +
          "a revision that had the file.",
      });
    }
  }
  return { hashes, findings };
}

/** Derive the per-class digests and the scene cache key. The key is a
 * hash of a versioned envelope over the class digests, so the class
 * structure is part of the format: adding a class later changes the
 * format string and every key with it. */
export function deriveSceneCacheKey(inputs: SceneKeyInputs): {
  key: string;
  classDigests: SceneKeyClassDigests;
} {
  const classDigests: SceneKeyClassDigests = {
    scene_source: sha256Hex(inputs.sceneSourceHash),
    props: sha256Hex(inputs.propsHash),
    assets: hashCanonical(sortedPairs(inputs.assetHashes)),
    fonts: hashCanonical(sortedPairs(inputs.fontHashes)),
    data: hashCanonical(sortedPairs(inputs.dataHashes)),
    timing: sha256Hex(inputs.timingHash),
    geometry: hashCanonical({
      width: inputs.width,
      height: inputs.height,
      fps: inputs.fps,
    }),
    export_settings: hashCanonical(inputs.exportSettings),
    versions: hashCanonical({
      engine: inputs.engine,
      adapter: inputs.adapterVersion,
      compiler: inputs.compilerVersion,
    }),
    runtime: sha256Hex(inputs.runtimeLockId),
  };
  const key = hashCanonical({
    format: "mg027-scene-key-v1",
    sceneId: inputs.sceneId,
    classes: classDigests,
  });
  return { key, classDigests };
}

/** The job key binds the ordered scene keys, the job-level compiled
 * timing hash, the export settings, and the runtime lock. It names a
 * whole job revision; per-scene staleness is decided by scene keys. */
export function deriveJobCacheKey(init: {
  jobId: string;
  sceneKeys: { sceneId: string; key: string }[];
  timingHash: string;
  exportSettings: Record<string, unknown>;
  runtimeLockId: string;
}): string {
  return hashCanonical({
    format: "mg027-job-key-v1",
    jobId: init.jobId,
    scenes: init.sceneKeys.map((s) => [s.sceneId, s.key]),
    timing: init.timingHash,
    exportSettingsDigest: hashCanonical(init.exportSettings),
    runtime: init.runtimeLockId,
  });
}

/** Names of the input classes whose digests differ between a recorded
 * scene state and the current revision, in stable order. This is what
 * a MG_CACHE_STALE_REVISION finding reports. */
export function changedClasses(
  recorded: SceneKeyClassDigests,
  current: SceneKeyClassDigests
): (keyof SceneKeyClassDigests)[] {
  const order: (keyof SceneKeyClassDigests)[] = [
    "scene_source",
    "props",
    "assets",
    "fonts",
    "data",
    "timing",
    "geometry",
    "export_settings",
    "versions",
    "runtime",
  ];
  return order.filter((name) => recorded[name] !== current[name]);
}

export { CacheFindings };
