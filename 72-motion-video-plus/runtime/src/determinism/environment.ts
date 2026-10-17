// Environment record for the determinism verifier (Directive MG-026).
// A golden result is only meaningful with the environment that produced
// it: the MG-026 promise is "same engine, same pinned environment, same
// input revision gives the same decoded pixels". This module captures
// that environment from primary sources only: engine versions come from
// the shared runtime lock file (the same lock the adapters render
// with), font identity is the sha256 of the exact font files both
// engines resolve for the fixture job, and the runtime lock id names
// the pinned install. Nothing here is typed in by hand, so the record
// cannot drift from the environment that actually rendered.

import { readFileSync } from "node:fs";
import { arch as osArch, cpus, platform as osPlatform, release as osRelease } from "node:os";
import { basename } from "node:path";
import { resolveSharedRuntime } from "../adapters/hyperframes";
import type { ValidatedMotionJob } from "../adapters/types";
import { resolveFont as resolveHyperframesFont } from "../hyperframes/project";
import { loadC05Job } from "../remotion/job-props";

export interface FontFileEvidence {
  weight: number;
  fileName: string;
  sha256: string;
}

export interface DeterminismEnvironment {
  /** Basename of the promoted runtime install, for example
   * lock-314fc289b233ca9e. Two runs with different lock ids are
   * different environments even on the same machine. */
  runtimeLockId: string;
  lockGeneratedAt: string;
  lockResult: string;
  engines: {
    remotion: string;
    hyperframes: string;
    gsap: string;
  };
  node: {
    /** Node running this verifier process. */
    process: string;
    /** Node recorded in the runtime lock at provision time. */
    lockRecorded: string;
  };
  platform: {
    os: string;
    arch: string;
    osRelease: string;
    lockRecorded: string;
    cpuCount: number;
  };
  browser: {
    revision: string;
    versionString: string;
  };
  ffmpegFirstLine: string;
  /** The exact font bytes both engines resolve for the C05 fixture
   * job, by content hash. A different hash is a different environment
   * (a different font renderer input), and pixel identity is not
   * promised across it. */
  fonts: {
    requirementId: string;
    remotion: FontFileEvidence[];
    hyperframes: FontFileEvidence[];
  };
}

interface RuntimeLockShape {
  timestamp?: string;
  result?: string;
  node?: string;
  platform?: { os?: string; arch?: string };
  packages?: Record<string, string>;
  browser?: { revision?: string; versionString?: string };
  ffmpeg?: string;
}

/** Build the environment record. The Remotion side reads the job
 * through the adapter's own loader, so the recorded font files are the
 * bytes that actually enter the composition props. */
export function buildEnvironmentRecord(remotionJob: ValidatedMotionJob): DeterminismEnvironment {
  const runtime = resolveSharedRuntime();
  const lock = JSON.parse(readFileSync(runtime.lockPath, "utf8")) as RuntimeLockShape;
  const loaded = loadC05Job(remotionJob);
  const hyperframesFont = resolveHyperframesFont(loaded.design.font_ref);
  const ffmpegFirstLine = (lock.ffmpeg ?? "").split("\n")[0];
  return {
    runtimeLockId: runtime.runtimeLockId,
    lockGeneratedAt: lock.timestamp ?? "unknown",
    lockResult: lock.result ?? "unknown",
    engines: {
      remotion: lock.packages?.["remotion"] ?? "unknown",
      hyperframes: lock.packages?.["hyperframes"] ?? "unknown",
      gsap: lock.packages?.["gsap"] ?? "unknown",
    },
    node: {
      process: process.version,
      lockRecorded: lock.node ?? "unknown",
    },
    platform: {
      os: osPlatform(),
      arch: osArch(),
      osRelease: osRelease(),
      lockRecorded: `${lock.platform?.os ?? "unknown"}/${lock.platform?.arch ?? "unknown"}`,
      cpuCount: cpus().length,
    },
    browser: {
      revision: lock.browser?.revision ?? "unknown",
      versionString: lock.browser?.versionString ?? "unknown",
    },
    ffmpegFirstLine,
    fonts: {
      requirementId: loaded.font.requirementId,
      remotion: loaded.font.files.map((f) => ({
        weight: f.weight,
        fileName: basename(f.path),
        sha256: f.sha256,
      })),
      hyperframes: hyperframesFont.files.map((f) => ({
        weight: f.weight,
        fileName: f.fileName,
        sha256: f.sha256,
      })),
    },
  };
}
