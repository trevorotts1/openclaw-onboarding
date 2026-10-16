// Artifact verification for MG-027: an artifact is reused only after
// it is proven to be the artifact its state record claims. Existence
// alone is never enough (the legacy renderer checked existence and
// nonzero size before encoding, which is how corrupt or stale frames
// reached outputs). Verification is existence, exact byte size,
// sha256 of the full contents, and, where the artifact is media, an
// independent probe whose facts must equal the recorded ones.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import {
  CacheFindings,
  type ArtifactRecord,
  type CacheFinding,
  type MediaProbeFacts,
} from "./types";

export function sha256File(absPath: string): string {
  return createHash("sha256").update(readFileSync(absPath)).digest("hex");
}

const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".webm", ".mkv"]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg"]);

/** Probe kind implied by a file name, or null when the artifact is
 * not media and only existence plus hash apply. */
export function probeKindForFile(fileName: string): "video" | "image" | null {
  const ext = extname(fileName).toLowerCase();
  if (VIDEO_EXTENSIONS.has(ext)) return "video";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  return null;
}

function probeVideo(absPath: string): MediaProbeFacts {
  const result = spawnSync(
    "ffprobe",
    [
      "-v",
      "error",
      "-count_frames",
      "-select_streams",
      "v:0",
      "-show_entries",
      "stream=width,height,avg_frame_rate,nb_read_frames",
      "-of",
      "json",
      absPath,
    ],
    { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 }
  );
  if (result.error) {
    throw new Error(`ffprobe could not run: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(
      `ffprobe exited ${String(result.status)} on ${absPath}: ${(result.stderr ?? "").slice(0, 400)}`
    );
  }
  const doc = JSON.parse(result.stdout) as {
    streams?: {
      width?: number;
      height?: number;
      avg_frame_rate?: string;
      nb_read_frames?: string;
    }[];
  };
  const stream = doc.streams?.[0];
  if (!stream || typeof stream.width !== "number" || typeof stream.height !== "number") {
    throw new Error(`ffprobe found no video stream in ${absPath}`);
  }
  const [num, den] = (stream.avg_frame_rate ?? "0/1")
    .split("/")
    .map((s) => Number(s));
  return {
    kind: "video",
    width: stream.width,
    height: stream.height,
    fpsNumerator: num,
    fpsDenominator: den === 0 ? 1 : den,
    frames: Number(stream.nb_read_frames ?? "0"),
  };
}

function probePng(absPath: string): MediaProbeFacts {
  const buf = readFileSync(absPath);
  if (
    buf.length < 24 ||
    buf[0] !== 0x89 ||
    buf[1] !== 0x50 ||
    buf[2] !== 0x4e ||
    buf[3] !== 0x47
  ) {
    throw new Error(`${absPath} is not a PNG (bad signature)`);
  }
  return {
    kind: "image",
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
  };
}

function probeJpeg(absPath: string): MediaProbeFacts {
  const result = spawnSync(
    "ffprobe",
    [
      "-v",
      "error",
      "-select_streams",
      "v:0",
      "-show_entries",
      "stream=width,height",
      "-of",
      "json",
      absPath,
    ],
    { encoding: "utf8", maxBuffer: 8 * 1024 * 1024 }
  );
  if (result.error || result.status !== 0) {
    throw new Error(`ffprobe could not probe JPEG ${absPath}`);
  }
  const doc = JSON.parse(result.stdout) as {
    streams?: { width?: number; height?: number }[];
  };
  const stream = doc.streams?.[0];
  if (!stream || typeof stream.width !== "number" || typeof stream.height !== "number") {
    throw new Error(`ffprobe found no image stream in ${absPath}`);
  }
  return { kind: "image", width: stream.width, height: stream.height };
}

/** Probe a media artifact. Throws on unprobeable media; callers that
 * verify turn the throw into a probe-mismatch finding, because an
 * artifact that cannot be probed cannot be proven intact. */
export function probeMediaFile(absPath: string): MediaProbeFacts {
  const kind = probeKindForFile(absPath);
  if (kind === "video") return probeVideo(absPath);
  if (kind === "image") {
    return extname(absPath).toLowerCase() === ".png"
      ? probePng(absPath)
      : probeJpeg(absPath);
  }
  throw new Error(`no media probe applies to ${absPath}`);
}

export function probeFactsEqual(
  a: MediaProbeFacts | null,
  b: MediaProbeFacts | null
): boolean {
  if (a === null || b === null) return a === b;
  if (a.kind !== b.kind) return false;
  if (a.width !== b.width || a.height !== b.height) return false;
  if (a.kind === "video" && b.kind === "video") {
    return (
      a.frames === b.frames &&
      a.fpsNumerator * b.fpsDenominator === b.fpsNumerator * a.fpsDenominator
    );
  }
  return true;
}

export interface ArtifactVerification {
  ok: boolean;
  /** Freshly measured probe facts (null for non-media artifacts or
   * when the artifact could not be probed). */
  probe: MediaProbeFacts | null;
  findings: CacheFinding[];
}

/** Verify the artifact a state record points at, under the session
 * work directory. Every failed check is a named finding; ok is true
 * only when existence, size, hash, and probe all agree. */
export function verifyRecordedArtifact(
  workDir: string,
  sceneId: string,
  record: ArtifactRecord
): ArtifactVerification {
  const findings: CacheFinding[] = [];
  const absPath = join(workDir, record.path);
  if (!existsSync(absPath)) {
    findings.push({
      category: CacheFindings.ArtifactMissing,
      sceneId,
      message:
        `Recorded artifact for scene ${sceneId} is missing from disk ` +
        `(${record.path}); it will be recomputed, never assumed.`,
    });
    return { ok: false, probe: null, findings };
  }
  const size = statSync(absPath).size;
  if (size !== record.bytes) {
    findings.push({
      category: CacheFindings.ArtifactCorrupt,
      sceneId,
      message:
        `Artifact for scene ${sceneId} has ${size} bytes on disk but its ` +
        `record says ${record.bytes}; it will be recomputed.`,
    });
    return { ok: false, probe: null, findings };
  }
  const digest = sha256File(absPath);
  if (digest !== record.sha256) {
    findings.push({
      category: CacheFindings.ArtifactCorrupt,
      sceneId,
      message:
        `Artifact for scene ${sceneId} hashes to ${digest.slice(0, 16)}... ` +
        `but its record says ${record.sha256.slice(0, 16)}...; the bytes on ` +
        "disk are not the bytes that were verified at completion and the " +
        "artifact will be recomputed.",
    });
    return { ok: false, probe: null, findings };
  }
  let probe: MediaProbeFacts | null = null;
  if (probeKindForFile(absPath) !== null) {
    try {
      probe = probeMediaFile(absPath);
    } catch (err) {
      findings.push({
        category: CacheFindings.ArtifactProbeMismatch,
        sceneId,
        message:
          `Artifact for scene ${sceneId} could not be probed: ` +
          `${(err as Error).message}; it will be recomputed.`,
      });
      return { ok: false, probe: null, findings };
    }
    if (!probeFactsEqual(probe, record.probe)) {
      findings.push({
        category: CacheFindings.ArtifactProbeMismatch,
        sceneId,
        message:
          `Artifact for scene ${sceneId} probes as ${JSON.stringify(probe)} ` +
          `but its record says ${JSON.stringify(record.probe)}; it will be ` +
          "recomputed.",
      });
      return { ok: false, probe, findings };
    }
  }
  return { ok: findings.length === 0, probe, findings };
}
