// Cache work-unit derivation for the dispatcher (MG-046,
// Settlement A from MG-027's closure).
//
// MG-027 shipped the content-addressed cache as a library and named
// this wiring the follow-up: the orchestrator opens a cache session
// per job, supplies per-scene renderers backed by the routed
// adapter, and assembles outputs only from artifactPathFor. This
// module derives the per-scene work units from a validated job's own
// files, and stages the scene-scoped job package a production
// adapter consumes for one scene.
//
// Key inputs are derived from the job's declared inputs, hashed as
// the cache contract requires (references/caching-and-resume.md):
// the scene spec bytes (scene source), the canonical scene spec plus
// the design document it renders from (props), the declared asset
// files' bytes (assets), the declared font requirement record
// (fonts: the job declares font requirements by id, alias, and
// weights; the resolved font bytes are an adapter concern, so the
// key binds the declared requirement the adapter must satisfy), the
// dataset bytes (data), the job's timeline documents (timing: the
// authoring timeline, plus the compiled timeline and sidecar when
// the job carries them), the canvas geometry, the delivery export
// settings, and the routed engine's adapter version, the timeline
// compiler version, and the runtime lock id from the capability
// record the render is pinned to.

import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import type { Manifest } from "../validation/generated-types";
import type { ValidatedMotionJob } from "../adapters/types";
import { hashCanonical, hashInputFiles } from "../cache/keys";
import type { SceneWorkUnit } from "../cache/types";

function sha256Hex(data: string | Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

function readJsonIfPresent(jobDir: string, rel: string): unknown {
  const abs = join(jobDir, rel);
  if (!existsSync(abs)) return null;
  try {
    return JSON.parse(readFileSync(abs, "utf8"));
  } catch {
    return null;
  }
}

export interface DeriveUnitsOptions {
  /** The engine the scene renders on (its routing assignment) and
   * that engine's exact adapter version from its probed capability
   * record. Engine and adapter version are per-scene key inputs
   * (the versions class). */
  engineFor: (sceneId: string) => { engine: string; adapterVersion: string };
  /** The runtime lock id the job's render is pinned to. A job
   * revision is defined once per job (the cache session enforces
   * this), so the lock is a job-level input: the assembly owner's
   * probed record supplies it. */
  runtimeLockId: string;
  /** Artifact file name per scene (extension selects the probe). */
  artifactFileNameFor: (sceneId: string) => string;
}

/** Derive one SceneWorkUnit per manifest scene, in manifest order. */
export function deriveSceneWorkUnits(
  job: ValidatedMotionJob,
  opts: DeriveUnitsOptions
): SceneWorkUnit[] {
  const manifest = job.manifest;
  const jobDir = job.jobDir;

  const timelineDoc = readJsonIfPresent(jobDir, manifest.timeline);
  const compiledDoc = readJsonIfPresent(jobDir, "compiled-timeline.json");
  const sidecarDoc = readJsonIfPresent(jobDir, "timeline-sidecar.json");
  const timingHash = hashCanonical({
    timeline: timelineDoc,
    compiledTimeline: compiledDoc,
    sidecar: sidecarDoc,
  });
  const timelineSchema =
    (timelineDoc as { schema_version?: string } | null)?.schema_version ?? "2.0";
  const compilerVersion = `mg021-timeline/${timelineSchema}`;

  const profile = EXPORT_SETTINGS_BY_PROFILE[manifest.delivery.video_profile] ?? {
    container: "mp4",
    videoProfile: manifest.delivery.video_profile,
  };
  const exportSettings: Record<string, unknown> = { ...profile };

  const assetsDoc = readJsonIfPresent(jobDir, manifest.assets) as {
    assets?: Array<{ id: string; path: string }>;
    font_requirements?: Array<Record<string, unknown>>;
  } | null;
  const designDoc = readJsonIfPresent(jobDir, manifest.design);
  const designFontRef =
    (designDoc as { font_ref?: string } | null)?.font_ref ?? null;
  const fontRequirement = (assetsDoc?.font_requirements ?? []).find(
    (f) => f.id === designFontRef
  );
  const fontHashes: Record<string, string> = fontRequirement
    ? { [String(fontRequirement.id)]: hashCanonical(fontRequirement) }
    : {};

  return manifest.scenes.map((entry) => {
    const specAbs = join(jobDir, entry.spec);
    const specBytes = readFileSync(specAbs);
    const spec = JSON.parse(specBytes.toString("utf8")) as Record<string, unknown>;
    const sceneDesign = readJsonIfPresent(jobDir, String(spec.design_path ?? manifest.design));
    const declaredAssets = ((spec.asset_ids ?? []) as string[])
      .map((id) => (assetsDoc?.assets ?? []).find((a) => a.id === id))
      .filter((a): a is { id: string; path: string } => a !== undefined);
    const assetHashes = hashInputFiles(
      declaredAssets.map((a) => ({ id: a.id, absPath: join(jobDir, a.path) }))
    ).hashes;
    const dataRel = String(spec.data_path ?? "");
    const dataHashes = dataRel
      ? hashInputFiles([{ id: dataRel, absPath: join(jobDir, dataRel) }]).hashes
      : {};
    const engineInfo = opts.engineFor(entry.id);
    return {
      sceneId: entry.id,
      keyInputs: {
        sceneId: entry.id,
        engine: engineInfo.engine,
        sceneSourceHash: sha256Hex(specBytes),
        propsHash: hashCanonical({ spec, design: sceneDesign }),
        assetHashes,
        fontHashes,
        dataHashes,
        timingHash,
        width: manifest.canvas.width,
        height: manifest.canvas.height,
        fps: manifest.canvas.fps,
        exportSettings,
        adapterVersion: engineInfo.adapterVersion,
        compilerVersion,
        runtimeLockId: opts.runtimeLockId,
      },
      chunksTotal: 1,
      artifactFileName: opts.artifactFileNameFor(entry.id),
    } satisfies SceneWorkUnit;
  });
}

const EXPORT_SETTINGS_BY_PROFILE: Record<string, Record<string, unknown>> = {
  h264_opaque: { container: "mp4", videoProfile: "h264_opaque" },
  prores_4444_alpha: { container: "mov", videoProfile: "prores_4444_alpha" },
  vp9_alpha: { container: "webm", videoProfile: "vp9_alpha" },
};

/** Container extension for the job's delivery profile. */
export function containerExtensionForProfile(profile: string): string {
  switch (profile) {
    case "prores_4444_alpha":
      return ".mov";
    case "vp9_alpha":
      return ".webm";
    default:
      return ".mp4";
  }
}

/**
 * Stage a scene-scoped view of a job: a copy of the job package
 * whose manifest lists only the one scene (with that scene's own
 * duration), and whose storyboard and timeline are filtered to it.
 * Production adapters render single-scene packages; the
 * orchestrator, not the adapter, owns the decomposition. The staged
 * package carries the same job id: it is the same task, viewed one
 * scene at a time. Already-staged output under the staging root is
 * replaced, so a resume re-derives the identical view.
 */
/** Recursively copy a job package tree, skipping one subtree (the
 * working tree) and replacing the destination wholesale so a resume
 * re-derives the identical staged view. */
function copyPackageTree(src: string, dest: string, skipAbs: string): void {
  rmSync(dest, { recursive: true, force: true });
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src, { withFileTypes: true })) {
    const srcPath = join(src, entry.name);
    if (srcPath === skipAbs) continue;
    const destPath = join(dest, entry.name);
    if (entry.isDirectory()) {
      copyPackageTree(srcPath, destPath, skipAbs);
    } else if (entry.isFile()) {
      copyFileSync(srcPath, destPath);
    }
  }
}

export function stageSceneJobDir(
  job: ValidatedMotionJob,
  sceneId: string,
  stagingRoot: string
): { jobDir: string; manifest: Manifest } {
  const entry = job.manifest.scenes.find((s) => s.id === sceneId);
  if (!entry) {
    throw new Error(`Job ${job.jobId} has no scene ${sceneId} to stage.`);
  }
  const dest = join(stagingRoot, sceneId);
  // Copy the job package, never its working tree: the working tree
  // holds the cache session and the staging root itself, and copying
  // it would recurse and would hand the adapter another job's
  // resume state. The copy is a manual walk because the destination
  // lives under the source's working tree, which fs.cpSync refuses
  // outright (a directory cannot be copied into its own subtree,
  // filter or not). The skipped working tree is exactly the part
  // the filter would have excluded.
  copyPackageTree(job.jobDir, dest, join(job.jobDir, "working"));

  const spec = JSON.parse(readFileSync(join(dest, entry.spec), "utf8")) as {
    duration_frames?: number;
  };
  const manifest = JSON.parse(
    readFileSync(join(dest, "manifest.json"), "utf8")
  ) as Manifest & Record<string, unknown>;
  manifest.scenes = [entry] as Manifest["scenes"];
  if (typeof spec.duration_frames === "number") {
    manifest.duration_frames = spec.duration_frames;
  }
  writeFileSync(join(dest, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

  const storyboardPath = join(dest, job.manifest.storyboard);
  if (existsSync(storyboardPath)) {
    const storyboard = JSON.parse(readFileSync(storyboardPath, "utf8")) as {
      beats?: Array<{ scene_id?: string }>;
    };
    if (Array.isArray(storyboard.beats)) {
      storyboard.beats = storyboard.beats.filter((b) => b.scene_id === sceneId);
      writeFileSync(storyboardPath, `${JSON.stringify(storyboard, null, 2)}\n`, "utf8");
    }
  }
  const timelinePath = join(dest, job.manifest.timeline);
  if (existsSync(timelinePath)) {
    const timeline = JSON.parse(readFileSync(timelinePath, "utf8")) as {
      scenes?: Array<{ id?: string }>;
      events?: Array<{ scene_id?: string }>;
      total_frames?: number;
    };
    if (Array.isArray(timeline.scenes)) {
      timeline.scenes = timeline.scenes.filter((s) => s.id === sceneId);
    }
    if (Array.isArray(timeline.events)) {
      timeline.events = timeline.events.filter((e) => e.scene_id === sceneId);
    }
    if (typeof spec.duration_frames === "number") {
      timeline.total_frames = spec.duration_frames;
    }
    writeFileSync(timelinePath, `${JSON.stringify(timeline, null, 2)}\n`, "utf8");
  }
  return { jobDir: dest, manifest };
}
