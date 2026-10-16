// Job-specific writable directories (Directive MG-029).
//
// A render job writes into its own directory set and nowhere else:
// a root named for the job and the run's ownership token, with tmp,
// home, cache, and asset-staging subdirectories. The launcher points
// the child's HOME, TMPDIR, and XDG_CACHE_HOME at these, so browser
// profiles, font caches, and bundler scratch stay inside the job's
// boundary where ownership-aware cleanup can see them, instead of
// spreading across the operator's real home directory.

import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { sanitizeJobSegment } from "./paths";

export interface JobWorkDir {
  root: string;
  tmp: string;
  home: string;
  cache: string;
  assets: string;
  /** Environment overrides that confine the child's writable paths. */
  env: Record<string, string>;
}

/** Default root for job work directories; overridable through
 * MOTION_JOB_WORK_ROOT. */
export function defaultWorkRoot(env: NodeJS.ProcessEnv = process.env): string {
  if (env.MOTION_JOB_WORK_ROOT) return env.MOTION_JOB_WORK_ROOT;
  return join(homedir(), ".local", "state", "motion-render", "work");
}

export function createJobWorkDir(
  jobId: string,
  token: string,
  workRoot?: string
): JobWorkDir {
  const root = join(
    workRoot ?? defaultWorkRoot(),
    `${sanitizeJobSegment(jobId)}-${token.slice(0, 8)}`
  );
  const dirs = {
    root,
    tmp: join(root, "tmp"),
    home: join(root, "home"),
    cache: join(root, "cache"),
    assets: join(root, "assets"),
  };
  for (const dir of Object.values(dirs)) mkdirSync(dir, { recursive: true });
  return {
    ...dirs,
    env: {
      HOME: dirs.home,
      TMPDIR: dirs.tmp,
      XDG_CACHE_HOME: dirs.cache,
    },
  };
}
