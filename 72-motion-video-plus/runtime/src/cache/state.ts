// Atomic, crash-safe persistence of the MG-027 cache state.
//
// Writes follow a write-temp-then-rename protocol: the full document
// is written to a temporary file in the same directory, fsynced, the
// current state file is rotated to render-state.json.prev, and the
// temporary file is renamed over render-state.json. Rename is atomic
// on the filesystems the runtime targets, so a reader always sees a
// complete document: the previous generation or the new one, never a
// torn mixture. A crash between the two renames leaves the main file
// absent and the previous generation intact; load recovers it and
// reports MG_CACHE_STATE_TORN_RECOVERED. A state file in the legacy
// render.js shape (scene, fps, doneThrough, with no content keys) is
// rejected by name as MG_CACHE_STATE_LEGACY_SHAPE: it is the
// D-RESUME-KEY shape and is never trusted as resume evidence.

import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import {
  CacheFindings,
  type CacheFinding,
  type CacheState,
} from "./types";

export const STATE_FILE_NAME = "render-state.json";
export const STATE_PREV_FILE_NAME = "render-state.json.prev";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The legacy state shape written by scripts/render.js: scene id, fps,
 * dimensions, and a done-through frame counter, with no content keys. */
export function isLegacyStateShape(value: unknown): boolean {
  if (!isRecord(value)) return false;
  if ("schemaVersion" in value || "schema_version" in value) return false;
  return "doneThrough" in value && ("scene" in value || "fps" in value);
}

function isValidState(value: unknown): value is CacheState {
  if (!isRecord(value)) return false;
  return (
    value.schemaVersion === "1.0" &&
    typeof value.jobId === "string" &&
    isRecord(value.scenes)
  );
}

function tryReadState(path: string): {
  parsed: unknown;
  valid: boolean;
  legacy: boolean;
} {
  try {
    const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));
    return { parsed, valid: isValidState(parsed), legacy: isLegacyStateShape(parsed) };
  } catch {
    return { parsed: null, valid: false, legacy: false };
  }
}

function fsyncDir(dir: string): void {
  try {
    const fd = openSync(dir, "r");
    try {
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
  } catch {
    // Directory fsync is a durability best effort; the rename protocol
    // is what guarantees readers never see a torn document.
  }
}

export interface StateLoadResult {
  state: CacheState | null;
  findings: CacheFinding[];
}

export class CacheStateStore {
  readonly workDir: string;
  readonly statePath: string;
  readonly prevPath: string;
  private lastGeneration = 0;
  private tmpCounter = 0;

  constructor(workDir: string) {
    this.workDir = workDir;
    this.statePath = join(workDir, STATE_FILE_NAME);
    this.prevPath = join(workDir, STATE_PREV_FILE_NAME);
  }

  /** A brand-new empty state document for a job. The store assigns
   * the generation on the first save. */
  fresh(jobId: string, jobKey: string): CacheState {
    const now = new Date().toISOString();
    return {
      schemaVersion: "1.0",
      item: "MG-027",
      jobId,
      jobKey,
      generation: 0,
      createdAt: now,
      updatedAt: now,
      scenes: {},
      reviewEvidence: [],
    };
  }

  /** Load the current state, recovering the previous generation when
   * the current file is torn or missing. Never throws on bad content:
   * every anomaly is a named finding and the worst case is an empty
   * state (render from scratch), never a trusted stale one. */
  load(): StateLoadResult {
    const findings: CacheFinding[] = [];
    const mainExists = existsSync(this.statePath);
    const prevExists = existsSync(this.prevPath);
    if (!mainExists && !prevExists) {
      this.lastGeneration = 0;
      return { state: null, findings };
    }

    if (mainExists) {
      const main = tryReadState(this.statePath);
      if (main.valid) {
        const state = main.parsed as CacheState;
        this.lastGeneration = state.generation;
        return { state, findings };
      }
      if (main.legacy) {
        findings.push({
          category: CacheFindings.StateLegacyShape,
          sceneId: null,
          message:
            `${STATE_FILE_NAME} has the legacy resume shape (scene id, fps, ` +
            "doneThrough) and carries no content keys; it is rejected and " +
            "never used as resume evidence (defect D-RESUME-KEY).",
        });
      }
    }

    if (prevExists) {
      const prev = tryReadState(this.prevPath);
      if (prev.valid) {
        const state = prev.parsed as CacheState;
        this.lastGeneration = state.generation;
        findings.push({
          category: CacheFindings.StateTornRecovered,
          sceneId: null,
          message:
            `The current state file was ${mainExists ? "unreadable" : "missing"} ` +
            `(a torn write or a crash mid-save); recovered generation ` +
            `${state.generation} from ${STATE_PREV_FILE_NAME}. At most the ` +
            "last chunk update was lost, which only ever costs a re-render.",
        });
        return { state, findings };
      }
    }

    findings.push({
      category: CacheFindings.StateUnreadable,
      sceneId: null,
      message:
        "State files are present but no generation is readable; starting " +
        "with an empty state rather than trusting unreadable resume data.",
    });
    this.lastGeneration = 0;
    return { state: null, findings };
  }

  /** Persist the state atomically. Assigns the next generation and
   * the updatedAt timestamp; the caller owns the document content. */
  save(state: CacheState): CacheState {
    mkdirSync(this.workDir, { recursive: true });
    this.lastGeneration += 1;
    state.generation = this.lastGeneration;
    state.updatedAt = new Date().toISOString();
    const serialized = `${JSON.stringify(state, null, 2)}\n`;
    this.tmpCounter += 1;
    const tmpPath = join(
      this.workDir,
      `${STATE_FILE_NAME}.tmp-${process.pid}-${this.tmpCounter}`
    );
    writeFileSync(tmpPath, serialized, "utf8");
    const fd = openSync(tmpPath, "r");
    try {
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    if (existsSync(this.statePath)) {
      renameSync(this.statePath, this.prevPath);
    }
    renameSync(tmpPath, this.statePath);
    fsyncDir(this.workDir);
    return state;
  }
}
