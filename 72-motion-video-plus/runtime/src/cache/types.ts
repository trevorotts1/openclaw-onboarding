// Content-addressed caching and crash-safe resume for the Skill 72
// Motion Graphics V2 runtime (Directive MG-027, defect D-RESUME-KEY).
//
// The legacy renderer's resume state keyed reuse on scene id and fps
// alone (plus dimensions after MG-024): a job whose assets, scene
// source, data, fonts, timing, export settings, or tool versions had
// changed silently reused frames rendered for a different revision.
// This module is the V2 replacement. A scene's work is reusable only
// when a cache key derived from every input that can change its pixels
// matches the current job revision AND the recorded artifact still
// verifies (existence, size, sha256, and a media probe where the
// artifact is media). State is written atomically so a crash or kill
// mid-render leaves a resumable, never-torn record. The
// human-readable authority is references/caching-and-resume.md.

/** Finding categories emitted by the cache layer. Findings are data,
 * never silent behavior: a caller (orchestrator, test, reviewer) sees
 * exactly why a scene was re-rendered or a state file rejected. */
export const CacheFindings = {
  /** Recorded state belongs to a different job id than the session's. */
  StateJobMismatch: "MG_CACHE_STATE_JOB_MISMATCH",
  /** The state file has the legacy render.js shape (scene, fps,
   * doneThrough) and carries no content keys. It is never trusted:
   * this is the D-RESUME-KEY shape. */
  StateLegacyShape: "MG_CACHE_STATE_LEGACY_SHAPE",
  /** The current state file was unreadable (torn write or crash
   * mid-save) and the previous generation was recovered. */
  StateTornRecovered: "MG_CACHE_STATE_TORN_RECOVERED",
  /** No readable state generation exists although state files are
   * present; the session starts empty rather than guessing. */
  StateUnreadable: "MG_CACHE_STATE_UNREADABLE",
  /** One scene record inside an otherwise valid state document is
   * malformed; that scene alone is treated as unrecorded. */
  StateRecordInvalid: "MG_CACHE_STATE_RECORD_INVALID",
  /** A scene's recorded cache key differs from the key derived from
   * the current job revision. The named input classes that changed
   * are listed in the finding message. */
  StaleRevision: "MG_CACHE_STALE_REVISION",
  /** A recorded artifact is absent from disk. */
  ArtifactMissing: "MG_CACHE_ARTIFACT_MISSING",
  /** A recorded artifact's size or sha256 differs from its record. */
  ArtifactCorrupt: "MG_CACHE_ARTIFACT_CORRUPT",
  /** A recorded artifact's probed media facts differ from its record
   * (or two independent probes of it disagree). */
  ArtifactProbeMismatch: "MG_CACHE_ARTIFACT_PROBE_MISMATCH",
  /** A scene renderer threw; the failure was recorded with bounded
   * evidence and the scene marked failed. */
  RenderFailed: "MG_CACHE_RENDER_FAILED",
  /** A key-derivation input file was absent; the key was derived
   * with an explicit absent sentinel so the absence itself changes
   * the key (never a silent reuse of a complete-input revision). */
  InputAbsent: "MG_CACHE_INPUT_ABSENT",
  /** A caller violated the cache API contract (a review-evidence
   * path outside the work directory, an out-of-range chunk report,
   * job-level key inputs that differ between scenes of one job). */
  InputInvalid: "MG_CACHE_INPUT_INVALID",
} as const;

export type CacheFindingCategory = (typeof CacheFindings)[keyof typeof CacheFindings];

export interface CacheFinding {
  category: CacheFindingCategory;
  /** Scene the finding belongs to, or null for job/state level. */
  sceneId: string | null;
  message: string;
}

/** Error thrown for programmer/contract violations inside the cache
 * layer (a renderer that returns without producing its artifact, a
 * review-evidence path outside the work directory, an out-of-range
 * chunk report). Render failures reported by renderers are recorded
 * as findings instead; see CachedRenderSession. */
export class CacheError extends Error {
  readonly category: CacheFindingCategory;
  readonly findings: CacheFinding[];

  constructor(init: {
    category: CacheFindingCategory;
    message: string;
    findings?: CacheFinding[];
  }) {
    super(init.message);
    this.name = "CacheError";
    this.category = init.category;
    this.findings = init.findings ?? [
      { category: init.category, sceneId: null, message: init.message },
    ];
  }
}

/** Every input that can change one scene's rendered pixels. All fields
 * are required: a caller that cannot supply one has not established
 * that reuse is safe, and the type system says so. Hash fields are
 * lowercase hex sha256 digests of the named content; see keys.ts for
 * the derivation helpers and references/caching-and-resume.md for the
 * per-class definitions. */
export interface SceneKeyInputs {
  sceneId: string;
  /** Engine that renders the scene, for example "remotion". */
  engine: string;
  /** Hash of the scene source (the scene spec / scene document bytes). */
  sceneSourceHash: string;
  /** Hash of the exact props payload the engine consumes. */
  propsHash: string;
  /** Asset id to content hash for every asset the scene declares. */
  assetHashes: Record<string, string>;
  /** Font id to content hash for every font the scene resolves. */
  fontHashes: Record<string, string>;
  /** Data id (or job-relative path) to content hash for every data
   * document the scene consumes. */
  dataHashes: Record<string, string>;
  /** Hash of the compiled timing for the job: the MG-021 canonical
   * timeline document plus its sidecar, canonically serialized.
   * Timing is a job-level input: a timing change re-keys every scene
   * whose placement or duration it can move. */
  timingHash: string;
  width: number;
  height: number;
  fps: number;
  /** Export settings record (profile, codec, quality, pixel format,
   * and any other encoder-facing setting), canonically hashed. */
  exportSettings: Record<string, unknown>;
  /** Exact adapter (engine binding) version string. */
  adapterVersion: string;
  /** Timeline compiler version string (MG-021). */
  compilerVersion: string;
  /** Shared runtime lock id the render executes under, for example
   * "lock-314fc289b233ca9e". */
  runtimeLockId: string;
}

/** Per-class digests of a scene key, stored in state so a stale
 * finding can name exactly which input classes changed. */
export type SceneKeyClassDigests = Record<
  | "scene_source"
  | "props"
  | "assets"
  | "fonts"
  | "data"
  | "timing"
  | "geometry"
  | "export_settings"
  | "versions"
  | "runtime",
  string
>;

/** Media facts established by probing an artifact. Video facts carry
 * the frame rate as the exact rational ffprobe reports, so two probes
 * compare without float drift. */
export type MediaProbeFacts =
  | {
      kind: "video";
      width: number;
      height: number;
      fpsNumerator: number;
      fpsDenominator: number;
      /** Exact decoded frame count. */
      frames: number;
    }
  | { kind: "image"; width: number; height: number };

/** A completed artifact as recorded in state. The path is relative to
 * the session work directory and is content-addressed (it contains
 * the scene cache key), so a path minted for one revision can never
 * be the path of another revision. */
export interface ArtifactRecord {
  path: string;
  sha256: string;
  bytes: number;
  /** Probe facts captured when the artifact was verified at
   * completion; null for non-media artifacts. */
  probe: MediaProbeFacts | null;
  /** ISO timestamp of the completion verification. */
  verifiedAt: string;
}

/** Bounded failure evidence for one failed render attempt. */
export interface FailureRecord {
  at: string;
  category: string;
  message: string;
  /** Tail of the renderer's diagnostic output, capped at
   * MAX_FAILURE_LOG_CHARS characters. */
  logTail: string;
}

/** State for one scene. Completed artifacts live here; in-progress
 * frame chunks are tracked as chunk indexes only (their files live
 * under chunks/<sceneId>/<key>/), which keeps the two kinds of work
 * separate: an artifact entry exists only after verification, while
 * chunk progress exists only while a scene is being rendered. */
export interface SceneStateRecord {
  /** Cache key of the revision this record describes. */
  key: string;
  classDigests: SceneKeyClassDigests;
  status: "in_progress" | "complete" | "failed";
  chunksTotal: number;
  /** Chunk indexes completed for this key, sorted ascending. */
  chunksCompleted: number[];
  artifact: ArtifactRecord | null;
  /** Newest last, capped at MAX_FAILURE_RECORDS entries. */
  failures: FailureRecord[];
  updatedAt: string;
}

/** Review evidence registered with the session (proof stills, review
 * records, measurement files). Cleanup never removes these paths,
 * even when they sit inside a scene's chunk directory. */
export interface ReviewEvidenceRecord {
  /** Path relative to the session work directory. */
  path: string;
  sha256: string;
  kind: string;
  recordedAt: string;
}

/** The state document persisted as render-state.json in the session
 * work directory. */
export interface CacheState {
  schemaVersion: "1.0";
  item: "MG-027";
  jobId: string;
  jobKey: string;
  /** Monotonic save generation, owned by the state store. */
  generation: number;
  createdAt: string;
  updatedAt: string;
  scenes: Record<string, SceneStateRecord>;
  reviewEvidence: ReviewEvidenceRecord[];
}

/** One scene's unit of work for a session. */
export interface SceneWorkUnit {
  sceneId: string;
  keyInputs: SceneKeyInputs;
  /** Number of frame chunks the renderer reports for this scene.
   * A monolithic renderer (a whole-video adapter render) declares 1;
   * a frame-chunk renderer declares its chunk count. */
  chunksTotal: number;
  /** File name the renderer writes the scene artifact to, inside the
   * content-addressed artifact directory. The extension selects the
   * verification probe (.mp4/.mov/.webm video, .png/.jpg image,
   * anything else existence plus hash only). */
  artifactFileName: string;
}

/** Context handed to a scene renderer by the session. */
export interface SceneRenderContext {
  sceneId: string;
  /** Cache key of the revision being rendered. */
  key: string;
  /** Absolute path the renderer must produce the artifact at. */
  artifactPath: string;
  /** Absolute per-revision chunk workspace. Intermediate frames live
   * here; the session cleans it after a verified successful encode
   * and retains it after a failure so resume can use the frames. */
  chunkDir: string;
  /** Chunks already complete for this key from an earlier attempt.
   * A renderer resuming a chunked render skips these (after checking
   * the chunk files it relies on still exist, since state alone is
   * never proof of bytes). */
  completedChunks: number[];
  /** Record one chunk as complete. Each call saves state atomically,
   * so a kill between chunks loses at most the in-flight chunk. */
  reportChunkComplete: (chunkIndex: number) => Promise<void>;
}

/** What a scene renderer returns on success. The probe is the
 * renderer's own measurement; the session probes independently and
 * fails the scene on disagreement. */
export interface SceneRenderOutcome {
  probe: MediaProbeFacts | null;
}

export type SceneRenderer = (
  ctx: SceneRenderContext
) => Promise<SceneRenderOutcome>;

/** The plan for one scene: reuse a verified artifact, or render (with
 * the findings that decided it and any chunks that can be resumed). */
export interface ScenePlan {
  sceneId: string;
  key: string;
  action: "reuse" | "render";
  /** True when a render continues earlier chunk progress for the
   * same key. */
  resume: boolean;
  completedChunks: number[];
  artifactPath: string | null;
  findings: CacheFinding[];
}

export interface SceneRunResult {
  sceneId: string;
  key: string;
  action: "reused" | "rendered" | "failed";
  resumedChunks: number[];
  artifactPath: string | null;
  findings: CacheFinding[];
}

export interface SessionRunReport {
  jobId: string;
  jobKey: string;
  ok: boolean;
  results: SceneRunResult[];
  findings: CacheFinding[];
}

/** Bounds for retained failure and quarantine material. */
export const MAX_FAILURE_RECORDS = 3;
export const MAX_FAILURE_LOG_CHARS = 1000;
export const MAX_QUARANTINE_PER_SCENE = 1;
