// The MG-027 cached render session: plans reuse versus render per
// scene from content keys, executes renders with atomic per-chunk
// state saves, verifies artifacts before trusting them, and applies
// the cleanup policy (intermediate frames are removed after a
// verified successful encode; the frames needed for resume and a
// bounded failure record survive a failure; registered review
// evidence is never removed by cleanup).
//
// Layout under the session work directory:
//   render-state.json / render-state.json.prev   (CacheStateStore)
//   artifacts/<sceneId>/<cacheKey>/<file>        (verified artifacts)
//   chunks/<sceneId>/<cacheKey>/...              (in-progress frames)
//   quarantine/<sceneId>/<oldKey>-<file>         (superseded artifacts,
//                                                 bounded per scene)
// Artifact and chunk paths embed the cache key, so a path minted for
// one revision can never be selected for another: leakage of stale
// frames into a new output is excluded structurally, and then also
// verified by hash at reuse time.
//
// The session is engine-agnostic. A scene renderer is any async
// function that produces the scene artifact at the given path and
// reports chunk completions; in production an orchestrator supplies
// renderers backed by the Section 5.5 adapters. Wiring this session
// into the dispatcher is deliberately NOT done here: dispatch.ts is
// under MG-025's in-flight claims, and the brief for this item names
// that wiring a documented follow-up (see
// references/caching-and-resume.md, Integration).

import {
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import {
  changedClasses,
  deriveJobCacheKey,
  deriveSceneCacheKey,
} from "./keys";
import { CacheStateStore } from "./state";
import {
  CacheError,
  CacheFindings,
  MAX_FAILURE_LOG_CHARS,
  MAX_FAILURE_RECORDS,
  MAX_QUARANTINE_PER_SCENE,
  type CacheFinding,
  type CacheState,
  type FailureRecord,
  type MediaProbeFacts,
  type ReviewEvidenceRecord,
  type SceneKeyClassDigests,
  type ScenePlan,
  type SceneRenderContext,
  type SceneRenderer,
  type SceneRunResult,
  type SceneStateRecord,
  type SceneWorkUnit,
  type SessionRunReport,
} from "./types";
import {
  probeFactsEqual,
  probeKindForFile,
  probeMediaFile,
  sha256File,
  verifyRecordedArtifact,
} from "./verify";

export interface CacheSessionOptions {
  /** Remove a scene's intermediate chunk files once its artifact is
   * complete and verified. Default true. The frames needed for resume
   * are only needed while a scene is incomplete or failed, so this
   * never destroys resume capability. */
  cleanChunksOnSuccess?: boolean;
}

interface DerivedUnit {
  unit: SceneWorkUnit;
  key: string;
  classDigests: SceneKeyClassDigests;
}

function isValidSceneRecord(value: unknown): value is SceneStateRecord {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r.key === "string" &&
    typeof r.classDigests === "object" &&
    r.classDigests !== null &&
    (r.status === "in_progress" || r.status === "complete" || r.status === "failed") &&
    Array.isArray(r.chunksCompleted) &&
    Array.isArray(r.failures)
  );
}

function nowIso(): string {
  return new Date().toISOString();
}

/** Remove a chunk directory's files, preserving registered review
 * evidence paths. Returns the removed paths. Used both by the
 * post-encode cleanup and by stale-revision reconciliation: review
 * evidence survives every kind of frame cleanup. */
function removeChunkFilesPreserving(
  workDir: string,
  dir: string,
  preservedAbsPaths: Set<string>
): string[] {
  if (!existsSync(dir)) return [];
  const removed: string[] = [];
  const walk = (current: string): void => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const abs = join(current, entry.name);
      if (entry.isDirectory()) {
        walk(abs);
        try {
          rmSync(abs, { recursive: false });
        } catch {
          // Directory still holds preserved evidence; leave it.
        }
      } else if (!preservedAbsPaths.has(resolve(abs))) {
        rmSync(abs, { force: true });
        removed.push(relative(workDir, abs).split(sep).join("/"));
      }
    }
  };
  walk(dir);
  try {
    rmSync(dir, { recursive: false });
  } catch {
    // Preserved evidence remains inside; the directory stays.
  }
  return removed;
}

/** Move a superseded scene artifact into quarantine/<sceneId>/,
 * keeping at most MAX_QUARANTINE_PER_SCENE files per scene. */
function quarantineArtifact(
  workDir: string,
  sceneId: string,
  record: SceneStateRecord
): void {
  if (!record.artifact) return;
  const src = join(workDir, record.artifact.path);
  if (!existsSync(src)) return;
  const dir = join(workDir, "quarantine", sceneId);
  mkdirSync(dir, { recursive: true });
  const existing = readdirSync(dir)
    .map((name) => ({ name, mtime: statSync(join(dir, name)).mtimeMs }))
    .sort((a, b) => a.mtime - b.mtime);
  while (existing.length >= MAX_QUARANTINE_PER_SCENE) {
    const oldest = existing.shift();
    if (!oldest) break;
    rmSync(join(dir, oldest.name), { force: true });
  }
  renameSync(src, join(dir, `${record.key}-${basename(record.artifact.path)}`));
}

export class CachedRenderSession {
  readonly workDir: string;
  readonly jobId: string;
  readonly jobKey: string;
  /** Findings from opening the session (state load, job mismatch,
   * stale revision reconciliation). Run reports include these. */
  readonly openFindings: CacheFinding[];

  private readonly store: CacheStateStore;
  private readonly units: DerivedUnit[];
  private readonly unitsById: Map<string, DerivedUnit>;
  private readonly options: Required<CacheSessionOptions>;
  private state: CacheState;
  private readonly reconciledFindings: Map<string, CacheFinding[]>;

  private constructor(init: {
    workDir: string;
    jobId: string;
    jobKey: string;
    store: CacheStateStore;
    state: CacheState;
    units: DerivedUnit[];
    openFindings: CacheFinding[];
    reconciledFindings: Map<string, CacheFinding[]>;
    options: Required<CacheSessionOptions>;
  }) {
    this.workDir = init.workDir;
    this.jobId = init.jobId;
    this.jobKey = init.jobKey;
    this.store = init.store;
    this.state = init.state;
    this.units = init.units;
    this.unitsById = new Map(init.units.map((u) => [u.unit.sceneId, u]));
    this.openFindings = init.openFindings;
    this.reconciledFindings = init.reconciledFindings;
    this.options = init.options;
  }

  static async open(init: {
    workDir: string;
    jobId: string;
    units: SceneWorkUnit[];
    options?: CacheSessionOptions;
  }): Promise<CachedRenderSession> {
    const { workDir, jobId, units } = init;
    if (units.length === 0) {
      throw new CacheError({
        category: CacheFindings.InputInvalid,
        message: "A cache session needs at least one scene work unit.",
      });
    }
    const first = units[0].keyInputs;
    for (const u of units) {
      if (
        u.keyInputs.timingHash !== first.timingHash ||
        u.keyInputs.runtimeLockId !== first.runtimeLockId ||
        JSON.stringify(u.keyInputs.exportSettings) !==
          JSON.stringify(first.exportSettings)
      ) {
        throw new CacheError({
          category: CacheFindings.InputInvalid,
          message:
            `Scene ${u.sceneId} carries job-level key inputs (timing, export ` +
            "settings, runtime lock) that differ from the first scene's; a " +
            "job revision is defined once per job, not once per scene.",
        });
      }
    }
    const derived: DerivedUnit[] = units.map((unit) => {
      const d = deriveSceneCacheKey(unit.keyInputs);
      return { unit, key: d.key, classDigests: d.classDigests };
    });
    const jobKey = deriveJobCacheKey({
      jobId,
      sceneKeys: derived.map((d) => ({ sceneId: d.unit.sceneId, key: d.key })),
      timingHash: first.timingHash,
      exportSettings: first.exportSettings,
      runtimeLockId: first.runtimeLockId,
    });

    const store = new CacheStateStore(workDir);
    const loaded = store.load();
    const findings: CacheFinding[] = [...loaded.findings];
    let state = loaded.state;
    let dirty = false;

    if (state && state.jobId !== jobId) {
      findings.push({
        category: CacheFindings.StateJobMismatch,
        sceneId: null,
        message:
          `The state in ${workDir} belongs to job ${state.jobId}, not ` +
          `${jobId}; it is not used. A work directory serves one job.`,
      });
      state = null;
    }
    if (!state) {
      state = store.fresh(jobId, jobKey);
      dirty = loaded.state !== null;
    }
    if (state.jobKey !== jobKey) {
      state.jobKey = jobKey;
      dirty = true;
    }

    // Reconcile recorded scenes against the current revision. A
    // record whose key no longer matches is stale: its artifact is
    // quarantined (bounded), its chunk files are deleted (those
    // frames belong to a dead revision and must never be assembled
    // into new output; registered review evidence is excepted), and
    // its record is dropped so the scene plans as a fresh render
    // carrying the stale finding.
    const reconciledFindings = new Map<string, CacheFinding[]>();
    for (const d of derived) {
      const sceneId = d.unit.sceneId;
      const record = state.scenes[sceneId];
      if (record === undefined) continue;
      if (!isValidSceneRecord(record)) {
        findings.push({
          category: CacheFindings.StateRecordInvalid,
          sceneId,
          message:
            `The state record for scene ${sceneId} is malformed; it is ` +
            "dropped and the scene is treated as never rendered.",
        });
        delete state.scenes[sceneId];
        dirty = true;
        continue;
      }
      if (record.key !== d.key) {
        const changed = changedClasses(record.classDigests, d.classDigests);
        const finding: CacheFinding = {
          category: CacheFindings.StaleRevision,
          sceneId,
          message:
            `Scene ${sceneId} was recorded under a different job revision: ` +
            `changed input classes: ${changed.length > 0 ? changed.join(", ") : "unknown"}. ` +
            `Recorded key ${record.key.slice(0, 16)}... does not match the ` +
            `current key ${d.key.slice(0, 16)}...; the recorded artifact is ` +
            "quarantined and the scene will be recomputed. (This is the " +
            "case the legacy state, which keyed only on scene id and fps, " +
            "silently reused: defect D-RESUME-KEY.)",
        };
        findings.push(finding);
        reconciledFindings.set(sceneId, [finding]);
        quarantineArtifact(workDir, sceneId, record);
        const staleChunkDir = join(workDir, "chunks", sceneId, record.key);
        removeChunkFilesPreserving(
          workDir,
          staleChunkDir,
          new Set(state.reviewEvidence.map((r) => resolve(workDir, r.path)))
        );
        delete state.scenes[sceneId];
        dirty = true;
      }
    }
    if (dirty) store.save(state);
    return new CachedRenderSession({
      workDir,
      jobId,
      jobKey,
      store,
      state,
      units: derived,
      openFindings: findings,
      reconciledFindings,
      options: { cleanChunksOnSuccess: init.options?.cleanChunksOnSuccess ?? true },
    });
  }

  /** The current state document (live reference; read-only use). */
  get currentState(): CacheState {
    return this.state;
  }

  /** Plan every scene: reuse only a complete record whose key matches
   * the current revision AND whose artifact verifies right now. */
  plan(): ScenePlan[] {
    return this.units.map((d) => {
      const sceneId = d.unit.sceneId;
      const findings: CacheFinding[] = [
        ...(this.reconciledFindings.get(sceneId) ?? []),
      ];
      const record = this.state.scenes[sceneId];
      if (!record) {
        return {
          sceneId,
          key: d.key,
          action: "render" as const,
          resume: false,
          completedChunks: [],
          artifactPath: null,
          findings,
        };
      }
      if (record.status === "complete") {
        if (!record.artifact) {
          findings.push({
            category: CacheFindings.StateRecordInvalid,
            sceneId,
            message:
              `Scene ${sceneId} is marked complete but records no artifact; ` +
              "it will be recomputed.",
          });
          return {
            sceneId,
            key: d.key,
            action: "render" as const,
            resume: false,
            completedChunks: [],
            artifactPath: null,
            findings,
          };
        }
        const verification = verifyRecordedArtifact(
          this.workDir,
          sceneId,
          record.artifact
        );
        findings.push(...verification.findings);
        if (verification.ok) {
          return {
            sceneId,
            key: d.key,
            action: "reuse" as const,
            resume: false,
            completedChunks: [],
            artifactPath: join(this.workDir, record.artifact.path),
            findings,
          };
        }
        return {
          sceneId,
          key: d.key,
          action: "render" as const,
          resume: false,
          completedChunks: [],
          artifactPath: null,
          findings,
        };
      }
      // in_progress or failed under the current key: resume the chunks.
      return {
        sceneId,
        key: d.key,
        action: "render" as const,
        resume: record.chunksCompleted.length > 0,
        completedChunks: [...record.chunksCompleted],
        artifactPath: null,
        findings,
      };
    });
  }

  /** Execute the plan. Reused scenes are not touched. Rendered scenes
   * run in unit order; a scene that fails is recorded with bounded
   * evidence and the remaining scenes still run, because resume is
   * the recovery path and one bad scene must not strand the rest. */
  async run(
    rendererFor: (unit: SceneWorkUnit) => SceneRenderer
  ): Promise<SessionRunReport> {
    const plans = this.plan();
    const results: SceneRunResult[] = [];
    for (const plan of plans) {
      const derived = this.unitsById.get(plan.sceneId);
      if (!derived) continue;
      if (plan.action === "reuse") {
        results.push({
          sceneId: plan.sceneId,
          key: plan.key,
          action: "reused",
          resumedChunks: [],
          artifactPath: plan.artifactPath,
          findings: plan.findings,
        });
        continue;
      }
      results.push(
        await this.runScene(derived, plan, rendererFor(derived.unit))
      );
    }
    const findings: CacheFinding[] = [
      ...this.openFindings,
      ...results.flatMap((r) => r.findings),
    ];
    return {
      jobId: this.jobId,
      jobKey: this.jobKey,
      ok: results.every((r) => r.action !== "failed"),
      results,
      findings,
    };
  }

  private async runScene(
    derived: DerivedUnit,
    plan: ScenePlan,
    renderer: SceneRenderer
  ): Promise<SceneRunResult> {
    const { unit, key, classDigests } = derived;
    const sceneId = unit.sceneId;
    const existing = this.state.scenes[sceneId];
    const record: SceneStateRecord = {
      key,
      classDigests,
      status: "in_progress",
      chunksTotal: unit.chunksTotal,
      chunksCompleted: [...plan.completedChunks],
      artifact: null,
      failures: existing && existing.key === key ? existing.failures : [],
      updatedAt: nowIso(),
    };
    this.state.scenes[sceneId] = record;
    this.store.save(this.state);

    const chunkDir = join(this.workDir, "chunks", sceneId, key);
    const artifactRel = join(
      "artifacts",
      sceneId,
      key,
      unit.artifactFileName
    );
    const artifactPath = join(this.workDir, artifactRel);
    mkdirSync(chunkDir, { recursive: true });
    mkdirSync(dirname(artifactPath), { recursive: true });

    const ctx: SceneRenderContext = {
      sceneId,
      key,
      artifactPath,
      chunkDir,
      completedChunks: [...plan.completedChunks],
      reportChunkComplete: async (chunkIndex: number) => {
        if (
          !Number.isInteger(chunkIndex) ||
          chunkIndex < 0 ||
          chunkIndex >= unit.chunksTotal
        ) {
          throw new CacheError({
            category: CacheFindings.InputInvalid,
            message:
              `Scene ${sceneId} reported chunk ${chunkIndex}, outside its ` +
              `declared range 0..${unit.chunksTotal - 1}.`,
          });
        }
        if (!record.chunksCompleted.includes(chunkIndex)) {
          record.chunksCompleted.push(chunkIndex);
          record.chunksCompleted.sort((a, b) => a - b);
          record.updatedAt = nowIso();
          this.store.save(this.state);
        }
      },
    };

    try {
      const outcome = await renderer(ctx);
      if (!existsSync(artifactPath)) {
        throw new CacheError({
          category: CacheFindings.ArtifactMissing,
          message:
            `Renderer for scene ${sceneId} returned success but produced ` +
            `no artifact at ${artifactRel}.`,
        });
      }
      const bytes = statSync(artifactPath).size;
      const sha256 = sha256File(artifactPath);
      let probe: MediaProbeFacts | null = null;
      if (probeKindForFile(artifactPath) !== null) {
        try {
          probe = probeMediaFile(artifactPath);
        } catch (err) {
          throw new CacheError({
            category: CacheFindings.ArtifactProbeMismatch,
            message:
              `Artifact for scene ${sceneId} could not be probed after ` +
              `render: ${(err as Error).message}`,
          });
        }
        if (outcome.probe && !probeFactsEqual(outcome.probe, probe)) {
          throw new CacheError({
            category: CacheFindings.ArtifactProbeMismatch,
            message:
              `Renderer-reported probe for scene ${sceneId} ` +
              `(${JSON.stringify(outcome.probe)}) disagrees with the ` +
              `session probe (${JSON.stringify(probe)}); the artifact is ` +
              "not trusted.",
          });
        }
      } else if (outcome.probe) {
        throw new CacheError({
          category: CacheFindings.ArtifactProbeMismatch,
          message:
            `Renderer for scene ${sceneId} reported media probe facts for ` +
            "a non-media artifact; the artifact is not trusted.",
        });
      }
      record.artifact = {
        path: artifactRel.split(sep).join("/"),
        sha256,
        bytes,
        probe,
        verifiedAt: nowIso(),
      };
      record.status = "complete";
      record.updatedAt = nowIso();
      this.store.save(this.state);
      if (this.options.cleanChunksOnSuccess) {
        this.cleanChunkDir(sceneId, key);
      }
      return {
        sceneId,
        key,
        action: "rendered",
        resumedChunks: plan.completedChunks,
        artifactPath,
        findings: plan.findings,
      };
    } catch (err) {
      const category =
        err instanceof CacheError ? err.category : CacheFindings.RenderFailed;
      const message = err instanceof Error ? err.message : String(err);
      const rawLog =
        (err as { logTail?: unknown }).logTail ??
        (err as { stderrLog?: unknown }).stderrLog ??
        message;
      const failure: FailureRecord = {
        at: nowIso(),
        category,
        message: message.slice(0, MAX_FAILURE_LOG_CHARS),
        logTail: String(rawLog).slice(-MAX_FAILURE_LOG_CHARS),
      };
      record.failures = [...record.failures, failure].slice(
        -MAX_FAILURE_RECORDS
      );
      record.status = "failed";
      record.artifact = null;
      record.updatedAt = nowIso();
      this.store.save(this.state);
      return {
        sceneId,
        key,
        action: "failed",
        resumedChunks: plan.completedChunks,
        artifactPath: null,
        findings: [
          ...plan.findings,
          { category, sceneId, message },
        ],
      };
    }
  }

  /** Remove a scene revision's chunk files, preserving any file that
   * is registered review evidence. Returns the removed paths
   * (relative to the work directory). */
  private cleanChunkDir(sceneId: string, key: string): string[] {
    return removeChunkFilesPreserving(
      this.workDir,
      join(this.workDir, "chunks", sceneId, key),
      new Set(this.state.reviewEvidence.map((r) => resolve(this.workDir, r.path)))
    );
  }

  /** Cleanup entry point for orchestrators: clean the chunk files of
   * every scene whose artifact is complete and verified. Review
   * evidence is preserved. Returns removed paths per scene. */
  cleanupCompletedScenes(): Record<string, string[]> {
    const removed: Record<string, string[]> = {};
    for (const d of this.units) {
      const record = this.state.scenes[d.unit.sceneId];
      if (record && record.status === "complete" && record.key === d.key) {
        removed[d.unit.sceneId] = this.cleanChunkDir(d.unit.sceneId, d.key);
      }
    }
    return removed;
  }

  /** Register a file inside the work directory as review evidence.
   * Cleanup never removes registered paths, and the record (with the
   * file's hash) survives in state even after frame cleanup. */
  registerReviewEvidence(
    absPath: string,
    kind: string
  ): ReviewEvidenceRecord {
    const rel = relative(this.workDir, absPath);
    if (rel.startsWith("..") || resolve(this.workDir, rel) !== resolve(absPath)) {
      throw new CacheError({
        category: CacheFindings.InputInvalid,
        message:
          `Review evidence must live inside the session work directory; ` +
          `${absPath} does not.`,
      });
    }
    if (!existsSync(absPath)) {
      throw new CacheError({
        category: CacheFindings.ArtifactMissing,
        message: `Review evidence file does not exist: ${absPath}`,
      });
    }
    const record: ReviewEvidenceRecord = {
      path: rel.split(sep).join("/"),
      sha256: sha256File(absPath),
      kind,
      recordedAt: nowIso(),
    };
    this.state.reviewEvidence = [
      ...this.state.reviewEvidence.filter((r) => r.path !== record.path),
      record,
    ];
    this.store.save(this.state);
    return record;
  }

  /** Re-verify registered review evidence against disk. */
  verifyReviewEvidence(): CacheFinding[] {
    const findings: CacheFinding[] = [];
    for (const entry of this.state.reviewEvidence) {
      const abs = join(this.workDir, entry.path);
      if (!existsSync(abs)) {
        findings.push({
          category: CacheFindings.ArtifactMissing,
          sceneId: null,
          message: `Registered review evidence is missing: ${entry.path}`,
        });
      } else if (sha256File(abs) !== entry.sha256) {
        findings.push({
          category: CacheFindings.ArtifactCorrupt,
          sceneId: null,
          message: `Registered review evidence changed on disk: ${entry.path}`,
        });
      }
    }
    return findings;
  }

  /** Absolute path of a scene's verified artifact, or null when the
   * scene has no complete, current record. Callers assembling an
   * output must use this (never a path they construct themselves):
   * it is the structural guarantee that only current-revision,
   * verified artifacts reach an output. */
  artifactPathFor(sceneId: string): string | null {
    const derived = this.unitsById.get(sceneId);
    const record = this.state.scenes[sceneId];
    if (!derived || !record) return null;
    if (record.status !== "complete" || record.key !== derived.key) return null;
    if (!record.artifact) return null;
    return join(this.workDir, record.artifact.path);
  }
}
