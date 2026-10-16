// Capacity preflight for the render resource budget (Directive
// MG-028).
//
// This is the TypeScript preflight the brief allows in place of a
// Python twin: the scheduler and both of its consumers (the adapters)
// live in this package, so the policy math exists exactly once, in
// the language that enforces it. A second implementation in Python
// would drift from the enforced numbers the first time either was
// tuned. The legacy scripts/preflight.js belongs to the V1 pipeline
// and is untouched.
//
// What the preflight does:
// - measures the machine it runs on (total and free memory, cores);
// - subtracts a host reserve (the OS, the agent processes, and active
//   services keep theirs; renders never budget against it);
// - derives unit caps from the measured per-render profiles, so the
//   number of simultaneous browsers is a consequence of measured
//   capacity, not a copied constant;
// - locates the shared ledger directory (the shared runtime's state
//   dir, so every render process on the machine accounts into the
//   same budget);
// - reports all of it, with the derivation, for evidence.

import { existsSync } from "node:fs";
import { cpus, freemem, tmpdir, totalmem } from "node:os";
import { dirname, join } from "node:path";
import { MEASURED_PEAKS_MB } from "./profiles";
import type { BudgetPolicy, MachineCapacity } from "./types";

const MB = 1024 * 1024;

/** Environment overrides (all optional; unset means derived):
 * MOTION_RENDER_BUDGET_DIR, MOTION_RENDER_MEMORY_BUDGET_MB,
 * MOTION_RENDER_HOST_RESERVE_MB, MOTION_RENDER_MAX_BROWSER_UNITS,
 * MOTION_RENDER_MAX_ENCODE_UNITS, MOTION_RENDER_MAX_DISK_MB,
 * MOTION_RENDER_ACQUIRE_TIMEOUT_MS. Operators raise or lower the
 * budget explicitly through these, never by editing profiles. */
function envInt(name: string): number | null {
  const raw = process.env[name];
  if (!raw) return null;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function measureMachineCapacity(): MachineCapacity {
  return {
    totalMemMB: Math.floor(totalmem() / MB),
    freeMemMB: Math.floor(freemem() / MB),
    cpuCount: Math.max(1, cpus().length),
    platform: `${process.platform} ${process.arch}`,
    nodeVersion: process.version,
    measuredAt: new Date().toISOString(),
  };
}

/** Locate the shared render-budget ledger directory. Search order:
 * the explicit override, MOTION_RENDER_BUDGET_DIR, the shared
 * runtime's state directory discovered by walking up from this module
 * (the repository layout both adapters already use), and finally a
 * per-user temp directory. Only the temp fallback is unshared, and
 * the policy records which case applied. */
export function discoverBudgetStateDir(explicit?: string): { dir: string; shared: boolean } {
  if (explicit) return { dir: explicit, shared: true };
  const fromEnv = process.env.MOTION_RENDER_BUDGET_DIR;
  if (fromEnv) return { dir: fromEnv, shared: true };
  let dir = __dirname;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "shared-utils", "motion-render-runtime", ".runtime");
    if (existsSync(join(dir, "shared-utils", "motion-render-runtime", "provision.sh"))) {
      return { dir: join(candidate, "render-budget"), shared: true };
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return { dir: join(tmpdir(), "motion-render-budget"), shared: false };
}

/** Host reserve rationale: the host keeps the larger of 1 GB or 20%
 * of total memory. The agent runtime, the dispatcher process, the OS,
 * and any active services (browser sessions the owner is using, file
 * watchers, the shell) live in the reserve; a render storm must not
 * be able to starve them, because a machine that swaps or OOM-kills
 * the agent produces failed renders AND a broken session. */
export function hostReserveMB(totalMemMB: number): number {
  return Math.max(1024, Math.ceil(totalMemMB * 0.2));
}

/** Derive the budget policy for this machine. Unit caps come from the
 * measured profiles: the browser cap is how many of the heaviest
 * measured browser profile fit in the memory budget, bounded by core
 * count (browsers are CPU-bound long before a big machine runs out of
 * RAM), and never below 1 (a machine that can render at all can
 * render one thing). */
export function deriveBudgetPolicy(explicitStateDir?: string): BudgetPolicy {
  const machine = measureMachineCapacity();
  const { dir, shared } = discoverBudgetStateDir(explicitStateDir);
  const reserve = envInt("MOTION_RENDER_HOST_RESERVE_MB") ?? hostReserveMB(machine.totalMemMB);
  const memoryBudget =
    envInt("MOTION_RENDER_MEMORY_BUDGET_MB") ??
    Math.max(256, machine.totalMemMB - reserve);
  const heaviestBrowserMB = Math.max(
    MEASURED_PEAKS_MB.remotionRender,
    MEASURED_PEAKS_MB.hyperframesRender
  );
  const byMemory = Math.max(1, Math.floor(memoryBudget / Math.max(1, heaviestBrowserMB)));
  const byCpu = Math.max(1, machine.cpuCount);
  const maxBrowserUnits =
    envInt("MOTION_RENDER_MAX_BROWSER_UNITS") ?? Math.max(1, Math.min(byMemory, byCpu));
  const maxEncodeUnits =
    envInt("MOTION_RENDER_MAX_ENCODE_UNITS") ?? Math.max(1, machine.cpuCount);
  return {
    stateDir: dir,
    sharedStateDir: shared,
    hostReserveMB: reserve,
    memoryBudgetMB: memoryBudget,
    maxBrowserUnits,
    maxEncodeUnits,
    maxDiskMB: envInt("MOTION_RENDER_MAX_DISK_MB") ?? 20_000,
    acquireTimeoutMs: envInt("MOTION_RENDER_ACQUIRE_TIMEOUT_MS") ?? 20 * 60_000,
    staleHeartbeatMs: 120_000,
  };
}

/** The full preflight report: machine, derived policy, and the
 * derivation in words. Consumed by the MG-028 test runner and
 * recorded in the evidence; also the operator-facing answer to "how
 * much rendering can this machine hold". */
export function preflightReport(explicitStateDir?: string): {
  machine: MachineCapacity;
  policy: BudgetPolicy;
  derivation: string[];
} {
  const machine = measureMachineCapacity();
  const policy = deriveBudgetPolicy(explicitStateDir);
  const derivation = [
    `machine total memory ${machine.totalMemMB} MB across ${machine.cpuCount} core(s)`,
    `host reserve ${policy.hostReserveMB} MB (larger of 1024 MB or 20% of total) is never budgeted to renders`,
    `memory budget ${policy.memoryBudgetMB} MB = total - reserve (unless overridden)`,
    `browser cap ${policy.maxBrowserUnits}: min of renders fitting the memory budget at the heaviest measured profile and the core count`,
    `encoder cap ${policy.maxEncodeUnits}: one per core`,
    `ledger directory ${policy.stateDir} (${policy.sharedStateDir ? "shared runtime state dir" : "UNSHARED temp fallback"})`,
  ];
  return { machine, policy, derivation };
}
