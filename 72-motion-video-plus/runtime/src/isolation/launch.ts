// The isolation launcher CLI (Directive MG-029): run any command as
// a render job child, under the full isolation boundary.
//
//   node dist/isolation/launch.js --job <jobId> [--network off|loopback|deny]
//       [--work-root <dir>] [--registry-dir <dir>] -- <bin> [args...]
//
// This is how in-process engines get the boundary the subprocess
// engines get inside the adapters: launch the engine's host process
// through here and the host (and the browsers it spawns) inherits the
// scrubbed environment, the job work directories, the network
// namespace, and the process registry record.
//
// Behavior: the child's stdio is inherited, so its output is the
// caller's output. SIGINT/SIGTERM delivered to the launcher terminate
// the job's recorded processes (ownership-aware) before the launcher
// exits. A one-line JSON evidence record (job id, pid, withheld
// environment NAMES, network mode; never values) is written to stderr
// at exit. The launcher exits with the child's exit code, or 128+signo
// when the child died by signal.

import { spawn } from "node:child_process";
import {
  buildRenderEnv,
  redactSecrets,
  secretValuesOf,
} from "./env";
import { IsolationError } from "./errors";
import {
  applyNetworkPolicy,
  networkModeFromEnv,
  type RenderNetworkMode,
} from "./network";
import { ProcessRegistry, readStartTimeTicks, terminateJobProcesses } from "./processes";
import { createJobWorkDir, defaultWorkRoot } from "./workdir";

interface LaunchArgs {
  jobId: string;
  network: RenderNetworkMode | null;
  workRoot: string | null;
  registryDir: string | null;
  bin: string;
  args: string[];
}

function parseArgs(argv: string[]): LaunchArgs {
  const sep = argv.indexOf("--");
  if (sep < 0) {
    throw new IsolationError(
      "LAUNCH_USAGE",
      "usage: launch.js --job <jobId> [--network M] [--work-root D] [--registry-dir D] -- <bin> [args...]"
    );
  }
  const flags = argv.slice(0, sep);
  const command = argv.slice(sep + 1);
  if (command.length === 0) {
    throw new IsolationError("LAUNCH_USAGE", "no command given after --");
  }
  const out: LaunchArgs = {
    jobId: "",
    network: null,
    workRoot: null,
    registryDir: null,
    bin: command[0],
    args: command.slice(1),
  };
  for (let i = 0; i < flags.length; i += 2) {
    const name = flags[i];
    const value = flags[i + 1];
    if (value === undefined) {
      throw new IsolationError("LAUNCH_USAGE", `flag ${name} needs a value`);
    }
    if (name === "--job") out.jobId = value;
    else if (name === "--network") {
      if (value !== "off" && value !== "loopback" && value !== "deny") {
        throw new IsolationError("LAUNCH_USAGE", `--network must be off, loopback, or deny`);
      }
      out.network = value;
    } else if (name === "--work-root") out.workRoot = value;
    else if (name === "--registry-dir") out.registryDir = value;
    else throw new IsolationError("LAUNCH_USAGE", `unknown flag ${name}`);
  }
  if (!out.jobId) throw new IsolationError("LAUNCH_USAGE", "--job is required");
  return out;
}

async function main(): Promise<number> {
  const parsed = parseArgs(process.argv.slice(2));
  const registry = new ProcessRegistry(parsed.registryDir ?? undefined);
  const token = registry.tokenFor(parsed.jobId);
  const work = createJobWorkDir(parsed.jobId, token, parsed.workRoot ?? defaultWorkRoot());
  const mode = parsed.network ?? networkModeFromEnv(process.env);
  const wrapped = applyNetworkPolicy(parsed.bin, parsed.args, mode);
  const built = buildRenderEnv(process.env, {
    jobId: parsed.jobId,
    jobToken: token,
    tmpDir: work.tmp,
    homeDir: work.home,
    extra: { XDG_CACHE_HOME: work.cache },
  });
  const secretValues = secretValuesOf(process.env);
  const child = spawn(wrapped.bin, wrapped.args, {
    env: built.env,
    shell: false,
    detached: true,
    stdio: "inherit",
  });
  const pid = child.pid ?? -1;
  if (pid > 0) {
    registry.record({
      jobId: parsed.jobId,
      token,
      role: "launch",
      bin: parsed.bin,
      argv: parsed.args.map((a) => redactSecrets(a, secretValues)),
      cwd: process.cwd(),
      pid,
      pgid: pid,
      startTimeTicks: readStartTimeTicks(pid),
      startedAt: new Date().toISOString(),
      state: "running",
      exitCode: null,
    });
  }
  let terminating = false;
  const onSignal = (signal: NodeJS.Signals): void => {
    if (terminating) return;
    terminating = true;
    void terminateJobProcesses(registry, parsed.jobId, { graceMs: 400 }).finally(() => {
      process.exit(128 + (signal === "SIGINT" ? 2 : 15));
    });
  };
  process.on("SIGINT", onSignal);
  process.on("SIGTERM", onSignal);
  const { code, signal } = await new Promise<{
    code: number | null;
    signal: NodeJS.Signals | null;
  }>((resolvePromise) => {
    child.on("error", () => resolvePromise({ code: null, signal: null }));
    child.on("close", (c, s) => resolvePromise({ code: c, signal: s }));
  });
  if (pid > 0) registry.markExited(parsed.jobId, pid, code);
  process.stderr.write(
    JSON.stringify({
      isolation: "mg029-launch",
      jobId: parsed.jobId,
      pid,
      network: mode,
      workDir: work.root,
      removedEnvNames: built.removedNames,
      exitCode: code,
      signal,
    }) + "\n"
  );
  if (signal) return 128 + (signal === "SIGINT" ? 2 : signal === "SIGKILL" ? 9 : 15);
  return code ?? 1;
}

main()
  .then((code) => process.exit(code))
  .catch((err: unknown) => {
    const e = err as Error & { code?: string };
    process.stderr.write(`launch: ${e.code ? `[${e.code}] ` : ""}${e.message}\n`);
    process.exit(2);
  });
