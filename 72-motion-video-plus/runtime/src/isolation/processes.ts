// Ownership-aware process tracking for render jobs (Directive MG-029).
//
// Every render child the runtime launches is recorded BEFORE it can do
// work: job id, an ownership token, pid, process group, the kernel
// start-time ticks of the pid, and the exact (secret-redacted) argument
// array. The record is persisted to a per-job JSON file so ownership
// survives the death of the launching process: an orphaned Chromium
// can still be attributed to its job afterwards.
//
// Termination is the inverse operation and it is deliberately narrow.
// A process is signaled only when ownership is PROVEN at signal time:
//   - a recorded pid whose current kernel start-time still equals the
//     recorded start-time (a recycled pid fails this check), or
//   - a live pid whose /proc/<pid>/environ carries the job's ownership
//     token (descendants inherit the token from the recorded root).
// Anything else is left running and reported as refused. PID numbers
// and command-line text are never trusted on their own, and nothing in
// this module pattern-matches process names: that was the failure mode
// of the previous sweep, which killed by command-line substring.
//
// The registry file format is shared with scripts/sweep-chromium.sh,
// whose embedded Python implements the same verification rules:
//   { "jobId": string, "token": string, "processes": [ProcessRecord] }

import { randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { sanitizeJobSegment } from "./paths";

export interface ProcessRecord {
  jobId: string;
  /** Ownership token shared by every process of the job. */
  token: string;
  /** What this process is, for example "hyperframes" or "ffmpeg". */
  role: string;
  bin: string;
  /** Argument array as launched, secret-redacted before recording. */
  argv: string[];
  cwd: string;
  pid: number;
  /** Process group id at launch (equals pid for a detached leader). */
  pgid: number | null;
  /** /proc/<pid> start-time ticks recorded at launch; the identity
   * anchor that defeats pid reuse. Null when unreadable at launch. */
  startTimeTicks: number | null;
  startedAt: string;
  state: "running" | "exited" | "terminated";
  exitCode: number | null;
}

export interface JobRegistryFile {
  jobId: string;
  token: string;
  processes: ProcessRecord[];
}

/** Default directory holding one registry file per job. Shared by the
 * adapters, the launcher, and sweep-chromium.sh; overridable through
 * MOTION_PROCESS_REGISTRY_DIR so tests and deployments can relocate
 * it. */
export function defaultRegistryDir(env: NodeJS.ProcessEnv = process.env): string {
  if (env.MOTION_PROCESS_REGISTRY_DIR) return env.MOTION_PROCESS_REGISTRY_DIR;
  const stateBase = env.XDG_STATE_HOME ?? join(homedir(), ".local", "state");
  return join(stateBase, "motion-render", "processes");
}

const MAX_EXITED_KEPT = 200;

export class ProcessRegistry {
  readonly dir: string;

  constructor(dir?: string) {
    this.dir = dir ?? defaultRegistryDir();
  }

  fileFor(jobId: string): string {
    return join(this.dir, `${sanitizeJobSegment(jobId)}.json`);
  }

  /** The job's ownership token, created on first use and stable across
   * every record of the job. */
  tokenFor(jobId: string): string {
    const existing = this.read(jobId);
    if (existing) return existing.token;
    return randomUUID();
  }

  read(jobId: string): JobRegistryFile | null {
    const path = this.fileFor(jobId);
    if (!existsSync(path)) return null;
    try {
      const parsed = JSON.parse(readFileSync(path, "utf8")) as JobRegistryFile;
      if (typeof parsed.jobId !== "string" || !Array.isArray(parsed.processes)) return null;
      return parsed;
    } catch {
      return null;
    }
  }

  records(jobId: string): ProcessRecord[] {
    return this.read(jobId)?.processes ?? [];
  }

  jobIds(): string[] {
    if (!existsSync(this.dir)) return [];
    return readdirSync(this.dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.slice(0, -".json".length));
  }

  loadAll(): ProcessRecord[] {
    const out: ProcessRecord[] = [];
    for (const id of this.jobIds()) {
      const file = this.read(id);
      if (file) out.push(...file.processes);
    }
    return out;
  }

  record(rec: ProcessRecord): void {
    const file = this.read(rec.jobId) ?? { jobId: rec.jobId, token: rec.token, processes: [] };
    file.token = rec.token;
    const idx = file.processes.findIndex((p) => p.pid === rec.pid && p.state === "running");
    if (idx >= 0) file.processes[idx] = rec;
    else file.processes.push(rec);
    const exited = file.processes.filter((p) => p.state !== "running");
    if (exited.length > MAX_EXITED_KEPT) {
      const keepExited = new Set(exited.slice(-MAX_EXITED_KEPT));
      file.processes = file.processes.filter(
        (p) => p.state === "running" || keepExited.has(p)
      );
    }
    this.write(file);
  }

  markExited(
    jobId: string,
    pid: number,
    exitCode: number | null,
    state: "exited" | "terminated" = "exited"
  ): void {
    const file = this.read(jobId);
    if (!file) return;
    let changed = false;
    for (const rec of file.processes) {
      if (rec.pid === pid && rec.state === "running") {
        rec.state = state;
        rec.exitCode = exitCode;
        changed = true;
      }
    }
    if (changed) this.write(file);
  }

  private write(file: JobRegistryFile): void {
    mkdirSync(this.dir, { recursive: true });
    const path = this.fileFor(file.jobId);
    const tmp = `${path}.tmp-${process.pid}`;
    writeFileSync(tmp, JSON.stringify(file, null, 2) + "\n", "utf8");
    renameSync(tmp, path);
  }
}

// ---------------------------------------------------------------------
// /proc identity primitives (Linux). Every function returns null/false
// on any doubt rather than guessing.
// ---------------------------------------------------------------------

function readProcStat(pid: number): { state: string; pgid: number; startTimeTicks: number } | null {
  try {
    const raw = readFileSync(`/proc/${pid}/stat`, "utf8");
    const close = raw.lastIndexOf(")");
    if (close < 0) return null;
    const fields = raw.slice(close + 2).split(" ");
    // fields[0] is stat field 3 (state); starttime is field 22.
    const startTimeTicks = Number(fields[19]);
    const pgid = Number(fields[2]);
    if (!Number.isFinite(startTimeTicks) || !Number.isFinite(pgid)) return null;
    return { state: fields[0], pgid, startTimeTicks };
  } catch {
    return null;
  }
}

export function readStartTimeTicks(pid: number): number | null {
  return readProcStat(pid)?.startTimeTicks ?? null;
}

export function readProcessGroupId(pid: number): number | null {
  return readProcStat(pid)?.pgid ?? null;
}

/** A pid counts as alive when /proc shows it in a non-zombie state. A
 * zombie is already dead; only its parent has not reaped it yet. */
export function pidAlive(pid: number): boolean {
  const stat = readProcStat(pid);
  if (!stat) return false;
  return stat.state !== "Z" && stat.state !== "X";
}

export function readEnviron(pid: number): Record<string, string> | null {
  try {
    const raw = readFileSync(`/proc/${pid}/environ`, "utf8");
    const out: Record<string, string> = {};
    for (const entry of raw.split("\0")) {
      const eq = entry.indexOf("=");
      if (eq > 0) out[entry.slice(0, eq)] = entry.slice(eq + 1);
    }
    return out;
  } catch {
    return null;
  }
}

/** The ownership token a live process carries, read from its own
 * environment. Descendants of a recorded root inherit it. */
export function environToken(pid: number): string | null {
  const env = readEnviron(pid);
  return env?.MOTION_JOB_TOKEN ?? null;
}

/** Identity proof for a recorded pid: the process is alive and its
 * kernel start-time still equals the ticks recorded at launch. When
 * no start-time could be recorded, the token must prove identity
 * instead; a pid with neither proof does not match. */
export function identityMatches(pid: number, rec: ProcessRecord): boolean {
  if (!pidAlive(pid)) return false;
  if (rec.startTimeTicks !== null) {
    return readStartTimeTicks(pid) === rec.startTimeTicks;
  }
  return environToken(pid) === rec.token;
}

/** Every live pid whose environment carries the given job token. */
export function findTokenProcesses(token: string): number[] {
  const out: number[] = [];
  let names: string[];
  try {
    names = readdirSync("/proc");
  } catch {
    return out;
  }
  for (const name of names) {
    if (!/^[0-9]+$/.test(name)) continue;
    const pid = Number(name);
    if (pid === process.pid) continue;
    if (pidAlive(pid) && environToken(pid) === token) out.push(pid);
  }
  return out;
}

/** Signal a process group when its leader identity is proven, else the
 * single pid. Returns true when a signal was delivered. A group that
 * contains the calling process itself is NEVER signaled: a cleanup
 * path must not be able to kill the operator's own session by
 * construction, not merely by convention. */
export function signalProcess(
  pid: number,
  signal: NodeJS.Signals,
  pgid?: number | null
): boolean {
  const ownPgid = readProcessGroupId(process.pid);
  if (pgid !== null && pgid !== undefined && pgid > 0 && pgid !== ownPgid) {
    try {
      process.kill(-pgid, signal);
      return true;
    } catch {
      // Group already gone or not ours to signal; fall through to pid.
    }
  }
  try {
    process.kill(pid, signal);
    return true;
  } catch {
    return false;
  }
}

export interface TerminationReport {
  jobId: string;
  /** Pids proven owned and signaled to completion. */
  terminated: number[];
  /** Recorded pids that were already dead. */
  alreadyExited: number[];
  /** Pids deliberately NOT signaled, with the reason. An unverifiable
   * pid is left running on purpose: it may belong to someone else. */
  refused: Array<{ pid: number; reason: string }>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Terminate every process a job owns, and nothing else. Recorded roots
 * are verified by start-time; descendants are found by the ownership
 * token in their environment. SIGTERM first, a grace period, then
 * SIGKILL for survivors, each re-verified immediately before the kill
 * signal so a pid recycled during the grace period is never hit.
 */
export async function terminateJobProcesses(
  registry: ProcessRegistry,
  jobId: string,
  opts?: { graceMs?: number }
): Promise<TerminationReport> {
  const graceMs = opts?.graceMs ?? 500;
  const report: TerminationReport = { jobId, terminated: [], alreadyExited: [], refused: [] };
  const file = registry.read(jobId);
  if (!file) return report;
  const running = file.processes.filter((p) => p.state === "running");
  if (running.length === 0) return report;

  const targets = new Map<number, ProcessRecord | null>();
  const groups = new Map<number, number>(); // pgid -> verified leader pid
  for (const rec of running) {
    if (!pidAlive(rec.pid)) {
      report.alreadyExited.push(rec.pid);
      registry.markExited(jobId, rec.pid, rec.exitCode, "exited");
      continue;
    }
    if (!identityMatches(rec.pid, rec)) {
      report.refused.push({
        pid: rec.pid,
        reason:
          "recorded start-time does not match the live process (pid may have been recycled); " +
          "left running deliberately",
      });
      continue;
    }
    targets.set(rec.pid, rec);
    if (rec.pgid !== null && rec.pgid > 0) groups.set(rec.pgid, rec.pid);
  }
  // Descendants: any live process carrying the job token that is not
  // itself a recorded root (render grandchildren, helper processes).
  for (const pid of findTokenProcesses(file.token)) {
    if (!targets.has(pid)) targets.set(pid, null);
  }
  if (targets.size === 0) return report;

  for (const [pid, rec] of targets) {
    signalProcess(pid, "SIGTERM", rec?.pgid ?? readProcessGroupId(pid));
  }
  for (const [pgid, leader] of groups) {
    // Group TERM reaches children that scrubbed their own environment;
    // the group itself is only signaled because its leader's identity
    // was verified above. Our own process group is exempt, always.
    if (!targets.has(leader)) continue;
    if (pgid === readProcessGroupId(process.pid)) continue;
    try {
      process.kill(-pgid, "SIGTERM");
    } catch {
      // Group already gone.
    }
  }
  const deadline = Date.now() + graceMs;
  while (Date.now() < deadline) {
    if ([...targets.keys()].every((pid) => !pidAlive(pid))) break;
    await sleep(25);
  }
  for (const [pid, rec] of targets) {
    if (!pidAlive(pid)) continue;
    // Re-verify immediately before SIGKILL.
    const stillOurs =
      rec !== null ? identityMatches(pid, rec) : environToken(pid) === file.token;
    if (!stillOurs) {
      report.refused.push({
        pid,
        reason: "identity could not be re-verified before SIGKILL; left running deliberately",
      });
      targets.delete(pid);
      continue;
    }
    signalProcess(pid, "SIGKILL", rec?.pgid ?? readProcessGroupId(pid));
  }
  if (targets.size > 0) {
    const killDeadline = Date.now() + 1000;
    while (Date.now() < killDeadline) {
      if ([...targets.keys()].every((pid) => !pidAlive(pid))) break;
      await sleep(25);
    }
  }
  for (const [pid, rec] of targets) {
    if (pidAlive(pid)) {
      report.refused.push({ pid, reason: "process survived SIGTERM and SIGKILL" });
      continue;
    }
    report.terminated.push(pid);
    if (rec) registry.markExited(jobId, pid, null, "terminated");
  }
  return report;
}
