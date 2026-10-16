// The isolated process runner (Directive MG-029): one spawn path that
// composes every control in this layer.
//   - environment: buildRenderEnv allowlist scrub, plus the job's
//     ownership token and job-specific TMPDIR;
//   - network: applyNetworkPolicy namespace wrap when a policy is in
//     force (requested per call or through MOTION_RENDER_NETWORK);
//   - process ownership: the child is spawned detached (its own
//     process group) and recorded in the ProcessRegistry with its
//     kernel start-time before this function returns a running handle;
//   - secrets: captured output is redacted with the host's secret
//     values before it is handed back or stored anywhere.
//
// The hyperframes adapter wires its subprocess helper to the same
// primitives; this runner serves the launcher CLI and any caller that
// wants a complete run-to-completion call.

import { spawn, type ChildProcess } from "node:child_process";
import { mkdirSync } from "node:fs";
import { basename, join } from "node:path";
import {
  buildRenderEnv,
  redactSecrets,
  secretValuesOf,
} from "./env";
import {
  applyNetworkPolicy,
  networkModeFromEnv,
  type RenderNetworkMode,
} from "./network";
import {
  ProcessRegistry,
  readStartTimeTicks,
} from "./processes";
import { sanitizeJobSegment } from "./paths";

export interface IsolatedRunOptions {
  jobId: string;
  /** Role label recorded in the registry, defaults to the binary name. */
  role?: string;
  cwd: string;
  /** Network policy for this child; defaults to MOTION_RENDER_NETWORK. */
  network?: RenderNetworkMode;
  /** Registry to record into; defaults to the shared registry dir. */
  registry?: ProcessRegistry;
  /** Host environment to scrub; defaults to process.env. */
  baseEnv?: NodeJS.ProcessEnv;
  /** Job work root: the child's TMPDIR becomes <root>/<job>/tmp. */
  jobWorkRoot?: string;
  /** Extra non-secret variables applied after scrubbing. */
  extraEnv?: Record<string, string>;
  /** Kill the child (tree) after this many milliseconds. */
  timeoutMs?: number;
}

export interface IsolatedRunResult {
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  /** Captured output, secret-redacted. */
  stdout: string;
  stderr: string;
  durationMs: number;
  /** The registry record's pid (the spawned process-group leader). */
  pid: number;
  /** Host variable names withheld from the child, sorted. */
  removedEnvNames: string[];
}

export interface IsolatedChild {
  child: ChildProcess;
  pid: number;
  jobToken: string;
  removedEnvNames: string[];
  /** Resolves when the child exits; output is redacted. */
  completion: Promise<IsolatedRunResult>;
}

const OUTPUT_TAIL_CHARS = 200_000;

function tail(text: string): string {
  return text.length > OUTPUT_TAIL_CHARS ? text.slice(-OUTPUT_TAIL_CHARS) : text;
}

/** Spawn one command under the isolation controls and return a handle
 * immediately; await `completion` for the run-to-completion result. */
export function spawnIsolated(
  bin: string,
  args: string[],
  opts: IsolatedRunOptions
): IsolatedChild {
  const baseEnv = opts.baseEnv ?? process.env;
  const registry = opts.registry ?? new ProcessRegistry();
  const token = registry.tokenFor(opts.jobId);
  let tmpDir: string | undefined;
  if (opts.jobWorkRoot) {
    tmpDir = join(opts.jobWorkRoot, sanitizeJobSegment(opts.jobId), "tmp");
    mkdirSync(tmpDir, { recursive: true });
  }
  const built = buildRenderEnv(baseEnv, {
    jobId: opts.jobId,
    jobToken: token,
    tmpDir,
    extra: opts.extraEnv,
  });
  const mode = opts.network ?? networkModeFromEnv(baseEnv);
  const wrapped = applyNetworkPolicy(bin, args, mode);
  const secretValues = secretValuesOf(baseEnv);
  const started = Date.now();
  const child = spawn(wrapped.bin, wrapped.args, {
    cwd: opts.cwd,
    env: built.env,
    shell: false,
    detached: true,
  });
  const pid = child.pid ?? -1;
  if (pid > 0) {
    registry.record({
      jobId: opts.jobId,
      token,
      role: opts.role ?? basename(bin),
      bin,
      argv: args.map((a) => redactSecrets(a, secretValues)),
      cwd: opts.cwd,
      pid,
      pgid: pid,
      startTimeTicks: readStartTimeTicks(pid),
      startedAt: new Date().toISOString(),
      state: "running",
      exitCode: null,
    });
  }
  let stdout = "";
  let stderr = "";
  let timer: NodeJS.Timeout | null = null;
  const completion = new Promise<IsolatedRunResult>((resolvePromise) => {
    child.stdout?.on("data", (d: Buffer) => {
      stdout = tail(stdout + d.toString("utf8"));
    });
    child.stderr?.on("data", (d: Buffer) => {
      stderr = tail(stderr + d.toString("utf8"));
    });
    if (opts.timeoutMs && pid > 0) {
      timer = setTimeout(() => {
        try {
          process.kill(-pid, "SIGKILL");
        } catch {
          try {
            child.kill("SIGKILL");
          } catch {
            // Already exited.
          }
        }
      }, opts.timeoutMs);
      timer.unref();
    }
    let settled = false;
    const settle = (exitCode: number | null, signal: NodeJS.Signals | null): void => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (pid > 0) registry.markExited(opts.jobId, pid, exitCode);
      resolvePromise({
        exitCode,
        signal,
        stdout: redactSecrets(stdout, secretValues),
        stderr: redactSecrets(stderr, secretValues),
        durationMs: Date.now() - started,
        pid,
        removedEnvNames: built.removedNames,
      });
    };
    child.on("error", () => settle(null, null));
    child.on("close", (code, signal) => settle(code, signal));
  });
  return { child, pid, jobToken: token, removedEnvNames: built.removedNames, completion };
}

/** Run one command to completion under the isolation controls. */
export async function runIsolated(
  bin: string,
  args: string[],
  opts: IsolatedRunOptions
): Promise<IsolatedRunResult> {
  return spawnIsolated(bin, args, opts).completion;
}
