// Render resource budget tests for MG-028 (Directive MG-028,
// acceptance: concurrent job stress within configured limits,
// cancellation frees reservations, one failed job does not kill
// another's render).
//
// Layers, all against the real implementation:
// - preflight and budget accounting units (fast, exact);
// - stale-ledger reaping: dead owners, wedged heartbeats, corrupt
//   records are reaped; live records survive;
// - cross-process proof: a child process's reservation is visible
//   in this process's accounting and blocks it (the ledger is the
//   machine-wide budget, not a per-process guess);
// - stress, cancellation, and failure isolation with real worker
//   processes carrying real memory footprints (fake-render-worker);
// - the measurement case: real Remotion and Hyperframes renders of
//   the shipped C05 fixture regenerate the capacity evidence, and the
//   shipped profiles must cover the measured peaks;
// - adapter wiring: concurrent real stills serialize on one browser
//   slot, a Hyperframes snapshot holds and releases a reservation,
//   and cancelling a real preview through the dispatcher frees its
//   reservation and its browser.
//
// Exit code 0 when every case passes, 1 otherwise.

import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import {
  AdapterError,
  createRegistry,
  loadValidatedJob,
  MotionDispatcher,
} from "../src/adapters";
import { createRemotionAdapter } from "../src/adapters/remotion";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import type { ValidatedMotionJob } from "../src/adapters/types";
import { readPngDimensions } from "../src/remotion/decode";
import {
  deriveBudgetPolicy,
  getSharedRenderBudget,
  MEASURED_PEAKS_MB,
  preflightReport,
  profileFor,
  RenderBudget,
  ResourceCancelledError,
  ResourceExhaustedError,
  setSharedRenderBudgetForTests,
  type BudgetPolicy,
  type Reservation,
  type ResourceProfile,
} from "../src/resources";

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const SCRATCH = join(REPO_ROOT, ".scratch", "mg028-tests");
const TMP_SCRATCH = join(SCRATCH, "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;
const FIXTURES_ROOT = join(SKILL_DIR, "tests", "fixtures");
const WORKER = join(FIXTURES_ROOT, "resources", "fake-render-worker.cjs");
const HOLD_SLOT = join(FIXTURES_ROOT, "resources", "hold-slot.cjs");
const EVIDENCE_MEASUREMENTS = join(SKILL_DIR, "tests", "evidence", "mg028", "measurements.json");

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return (err as NodeJS.ErrnoException).code === "EPERM";
  }
}

function smallPolicy(stateDir: string, over?: Partial<BudgetPolicy>): BudgetPolicy {
  return {
    stateDir,
    sharedStateDir: false,
    hostReserveMB: 0,
    memoryBudgetMB: 4096,
    maxBrowserUnits: 2,
    maxEncodeUnits: 2,
    maxDiskMB: 10_000,
    acquireTimeoutMs: 60_000,
    staleHeartbeatMs: 120_000,
    ...over,
  };
}

function prof(memoryMB: number, over?: Partial<ResourceProfile>): ResourceProfile {
  return {
    memoryMB,
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 16,
    nestedConcurrency: 1,
    label: "test profile",
    ...over,
  };
}

// ---------------------------------------------------------------------
// Fake render jobs: the budget plus a real worker process, mirroring
// how an adapter behaves (acquire, run engine processes, release in
// finally; cancel kills the job's processes and frees the slot).
// ---------------------------------------------------------------------

interface FakeJobHandle {
  done: Promise<string>;
  cancel: () => void;
  pid: () => number | null;
  spawnedAt: () => number | null;
}

function startFakeJob(
  budget: RenderBudget,
  spec: {
    id: string;
    profile: ResourceProfile;
    sleepMs: number;
    allocMB: number;
    failCode?: number;
    aliveDir: string;
    outFile: string;
    content: string;
  }
): FakeJobHandle {
  let child: ChildProcess | null = null;
  let cancelled = false;
  let spawnedAtMs: number | null = null;
  const done = (async (): Promise<string> => {
    const reservation = await budget.acquire(
      { engine: "remotion", jobId: spec.id, operation: "renderFinal", profile: spec.profile },
      { isCancelled: () => cancelled, timeoutMs: 120_000 }
    );
    try {
      return await new Promise<string>((resolvePromise, rejectPromise) => {
        child = spawn(
          process.execPath,
          [
            WORKER,
            "--id", spec.id,
            "--out", spec.outFile,
            "--content", spec.content,
            "--sleep-ms", String(spec.sleepMs),
            "--alloc-mb", String(spec.allocMB),
            "--alive-dir", spec.aliveDir,
            "--fail-code", String(spec.failCode ?? 0),
          ],
          { shell: false }
        );
        spawnedAtMs = Date.now();
        let stderr = "";
        child.stderr?.on("data", (d: Buffer) => {
          stderr += d.toString("utf8");
        });
        child.on("error", (err) => rejectPromise(err));
        child.on("close", (code) => {
          if (cancelled) {
            rejectPromise(new Error(`job ${spec.id} was cancelled`));
          } else if (code === 0) {
            resolvePromise(readFileSync(spec.outFile, "utf8"));
          } else {
            rejectPromise(new Error(`job ${spec.id} worker exited ${code}: ${stderr}`));
          }
        });
      });
    } finally {
      await reservation.release();
    }
  })();
  return {
    done,
    cancel: () => {
      cancelled = true;
      if (child) {
        try {
          child.kill("SIGKILL");
        } catch {
          // Already exited.
        }
      }
    },
    pid: () => child?.pid ?? null,
    spawnedAt: () => spawnedAtMs,
  };
}

function aliveWorkerPids(aliveDir: string): number[] {
  if (!existsSync(aliveDir)) return [];
  const pids: number[] = [];
  for (const name of readdirSync(aliveDir)) {
    if (!name.endsWith(".alive")) continue;
    const pid = Number(readFileSync(join(aliveDir, name), "utf8").trim());
    if (Number.isInteger(pid) && pidAlive(pid)) pids.push(pid);
  }
  return pids;
}

function rssMB(pid: number): number {
  try {
    const status = readFileSync(`/proc/${pid}/status`, "utf8");
    const m = status.match(/VmRSS:\s+(\d+) kB/);
    return m ? Number(m[1]) / 1024 : 0;
  } catch {
    return 0;
  }
}

// ---------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

const CASES: TestCase[] = [
  {
    name: "preflight: the derived policy reserves the host share and caps units from measured capacity",
    run: () => {
      const report = preflightReport(join(SCRATCH, "preflight-ledger"));
      assertTrue(report.machine.totalMemMB > 1024, "machine memory measured");
      assertTrue(report.policy.hostReserveMB >= 1024, "host reserve is at least 1 GB");
      assertEq(
        report.policy.memoryBudgetMB,
        report.machine.totalMemMB - report.policy.hostReserveMB,
        "memory budget is total minus the host reserve"
      );
      assertTrue(report.policy.maxBrowserUnits >= 1, "at least one browser unit");
      assertTrue(
        report.policy.maxBrowserUnits <= Math.max(1, report.machine.cpuCount),
        "browser cap does not exceed the core count"
      );
      assertTrue(report.policy.stateDir.endsWith("preflight-ledger"), "explicit state dir honored");
      assertTrue(report.derivation.length >= 5, "derivation is reported in words");
      // Explicit operator override beats derivation.
      process.env.MOTION_RENDER_MAX_BROWSER_UNITS = "7";
      try {
        assertEq(deriveBudgetPolicy().maxBrowserUnits, 7, "env override wins over derivation");
      } finally {
        delete process.env.MOTION_RENDER_MAX_BROWSER_UNITS;
      }
    },
  },
  {
    name: "budget: acquire, totals, per-job nesting, and idempotent release",
    run: async () => {
      const budget = new RenderBudget(smallPolicy(join(SCRATCH, "unit-ledger")));
      const p = prof(256);
      const r1 = await budget.acquire({ engine: "remotion", jobId: "job-nest", operation: "renderFinal", profile: p });
      const r2 = await budget.acquire({ engine: "remotion", jobId: "job-nest", operation: "renderStill", profile: p });
      assertEq(r1.id, r2.id, "a nested acquire for the same job returns the same reservation");
      let snap = budget.snapshot();
      assertEq(snap.records.length, 1, "one ledger record for the nested holds");
      assertEq(snap.totals.memoryMB, 256, "the nested hold is counted once, not twice");
      await r1.release();
      snap = budget.snapshot();
      assertEq(snap.records.length, 1, "the record survives the inner release");
      await r2.release();
      await r2.release();
      snap = budget.snapshot();
      assertEq(snap.records.length, 0, "the last release removes the record; extra releases are no-ops");
    },
  },
  {
    name: "budget: a request that cannot fit waits, then fails naming the load, before anything launches",
    run: async () => {
      const budget = new RenderBudget(
        smallPolicy(join(SCRATCH, "timeout-ledger"), { maxBrowserUnits: 1 })
      );
      const holder = await budget.acquire({
        engine: "remotion",
        jobId: "job-holder",
        operation: "renderFinal",
        profile: prof(256),
      });
      const started = Date.now();
      let caught: unknown = null;
      try {
        await budget.acquire(
          { engine: "hyperframes", jobId: "job-waiter", operation: "renderFinal", profile: prof(256) },
          { timeoutMs: 400 }
        );
      } catch (err) {
        caught = err;
      }
      assertTrue(caught instanceof ResourceExhaustedError, `expected ResourceExhaustedError, got ${String(caught)}`);
      assertTrue(Date.now() - started >= 350, "the waiter actually waited for capacity");
      assertTrue(
        (caught as Error).message.includes("active reservations 1"),
        "the failure names the current load"
      );
      await holder.release();
      const after = await budget.acquire(
        { engine: "hyperframes", jobId: "job-waiter", operation: "renderFinal", profile: prof(256) },
        { timeoutMs: 2000 }
      );
      await after.release();
      assertEq(budget.snapshot().records.length, 0, "ledger empty at the end");
    },
  },
  {
    name: "budget: stale records are reaped (dead owner, wedged heartbeat, corrupt file); live records survive",
    run: async () => {
      const dir = join(SCRATCH, "stale-ledger");
      const budget = new RenderBudget(smallPolicy(dir));
      const reservationsDir = join(dir, "reservations");
      const sleeper = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60000)"], { shell: false });
      try {
        await sleep(150);
        const sleeperPid = sleeper.pid as number;
        assertTrue(pidAlive(sleeperPid), "sleeper is alive");
        const dead = spawnSync(process.execPath, ["-e", "process.exit(0)"]);
        const deadPid = dead.pid;
        assertTrue(!pidAlive(deadPid), "the short-lived process is gone");
        const record = (
          id: string,
          pid: number,
          heartbeatAt: string
        ): Record<string, unknown> => ({
          id,
          jobId: `job-${id}`,
          engine: "remotion",
          operation: "renderFinal",
          pid,
          acquiredAt: heartbeatAt,
          heartbeatAt,
          profile: prof(128),
        });
        const now = new Date().toISOString();
        const longAgo = new Date(Date.now() - 20 * 60_000).toISOString();
        writeFileSync(join(reservationsDir, "res-dead.json"), JSON.stringify(record("res-dead", deadPid, now)));
        writeFileSync(join(reservationsDir, "res-wedged.json"), JSON.stringify(record("res-wedged", sleeperPid, longAgo)));
        writeFileSync(join(reservationsDir, "res-live.json"), JSON.stringify(record("res-live", sleeperPid, now)));
        const corruptPath = join(reservationsDir, "res-corrupt.json");
        writeFileSync(corruptPath, "not json{");
        const old = new Date(Date.now() - 5 * 60_000);
        utimesSync(corruptPath, old, old);
        const snap = budget.snapshot();
        assertEq(snap.records.length, 1, `only the live record survives (found ${snap.records.map((r) => r.id).join(", ")})`);
        assertEq(snap.records[0].id, "res-live", "the survivor is the live record");
        assertEq(snap.totals.memoryMB, 128, "totals count only the survivor");
      } finally {
        sleeper.kill("SIGKILL");
      }
    },
  },
  {
    name: "cross-process: a child process's reservation is visible here and blocks a second unit",
    run: async () => {
      const dir = join(SCRATCH, "xproc-ledger");
      process.env.MOTION_RENDER_MAX_BROWSER_UNITS = "1";
      let child: ChildProcess | null = null;
      try {
        const budget = new RenderBudget(deriveBudgetPolicy(dir));
        assertEq(budget.policy.maxBrowserUnits, 1, "cap of one browser unit for this case");
        const acquiredLine = new Promise<string>((resolvePromise, rejectPromise) => {
          child = spawn(process.execPath, [HOLD_SLOT, dir, "6000"], { shell: false });
          let out = "";
          child.stdout?.on("data", (d: Buffer) => {
            out += d.toString("utf8");
            const m = out.match(/ACQUIRED (\S+)/);
            if (m) resolvePromise(m[1]);
          });
          child.on("error", rejectPromise);
          child.on("close", (code) => {
            if (!out.includes("ACQUIRED")) rejectPromise(new Error(`hold-slot child exited ${code}: ${out}`));
          });
        });
        const childReservationId = await acquiredLine;
        const snap = budget.snapshot();
        assertEq(snap.records.length, 1, "the child's reservation is in this process's accounting");
        assertEq(snap.records[0].id, childReservationId, "the record is the child's");
        assertTrue(snap.records[0].pid !== process.pid, "the record names the child's pid");
        let caught: unknown = null;
        try {
          await budget.acquire(
            { engine: "remotion", jobId: "parent-job", operation: "renderFinal", profile: prof(128) },
            { timeoutMs: 400 }
          );
        } catch (err) {
          caught = err;
        }
        assertTrue(caught instanceof ResourceExhaustedError, "the parent's second unit is refused while the child holds the only slot");
        // The child releases and exits; capacity returns.
        await new Promise<void>((resolvePromise) => child?.on("close", () => resolvePromise()));
        const r = await budget.acquire(
          { engine: "remotion", jobId: "parent-job", operation: "renderFinal", profile: prof(128) },
          { timeoutMs: 5000 }
        );
        await r.release();
        assertEq(budget.snapshot().records.length, 0, "ledger empty at the end");
      } finally {
        delete process.env.MOTION_RENDER_MAX_BROWSER_UNITS;
        const running = child as ChildProcess | null;
        if (running && running.exitCode === null) running.kill("SIGKILL");
      }
    },
  },
  {
    name: "stress: three jobs compete for two slots; concurrency and accounted memory never exceed the budget; every output is correct",
    run: async () => {
      const dir = join(SCRATCH, "stress");
      const aliveDir = join(dir, "alive");
      mkdirSync(aliveDir, { recursive: true });
      const budget = new RenderBudget(
        smallPolicy(join(dir, "ledger"), { memoryBudgetMB: 400, maxBrowserUnits: 2, maxEncodeUnits: 2 })
      );
      const jobs = ["stress-a", "stress-b", "stress-c"].map((id) =>
        startFakeJob(budget, {
          id,
          profile: prof(160),
          sleepMs: 2500,
          allocMB: 60,
          aliveDir,
          outFile: join(dir, `${id}.out`),
          content: `${id}-rendered-ok`,
        })
      );
      let maxAlive = 0;
      let maxAccountedMB = 0;
      let maxRssMB = 0;
      const sampler = setInterval(() => {
        const pids = aliveWorkerPids(aliveDir);
        maxAlive = Math.max(maxAlive, pids.length);
        maxRssMB = Math.max(maxRssMB, pids.reduce((sum, pid) => sum + rssMB(pid), 0));
        maxAccountedMB = Math.max(maxAccountedMB, budget.snapshot().totals.memoryMB);
      }, 50);
      const results = await Promise.all(jobs.map((j) => j.done));
      clearInterval(sampler);
      assertEq(maxAlive, 2, "exactly two workers were ever alive at once (the third waited for a slot)");
      assertTrue(maxAccountedMB <= 400, `accounted memory peaked at ${maxAccountedMB} MB, within the 400 MB budget`);
      assertEq(maxAccountedMB, 320, "both slots' profiles were accounted at the peak");
      for (let i = 0; i < results.length; i += 1) {
        assertEq(results[i], `${["stress-a", "stress-b", "stress-c"][i]}-rendered-ok`, "job output content is exactly its own");
      }
      assertEq(budget.snapshot().records.length, 0, "ledger empty after the stress run");
      console.log(
        `  stress evidence: max alive workers ${maxAlive}, peak accounted ${maxAccountedMB} MB, ` +
          `peak summed worker RSS ${Math.round(maxRssMB)} MB (RSS corroborates; the budget enforces the accounting)`
      );
    },
  },
  {
    name: "cancellation: a waiting acquire aborts promptly; cancelling a running job frees its slot and processes while another job completes",
    run: async () => {
      const dir = join(SCRATCH, "cancel");
      const aliveDir = join(dir, "alive");
      mkdirSync(aliveDir, { recursive: true });
      const budget = new RenderBudget(
        smallPolicy(join(dir, "ledger"), { memoryBudgetMB: 1024, maxBrowserUnits: 1, maxEncodeUnits: 2 })
      );
      const jobA = startFakeJob(budget, {
        id: "cancel-a",
        profile: prof(160),
        sleepMs: 4000,
        allocMB: 32,
        aliveDir,
        outFile: join(dir, "a.out"),
        content: "a-ok",
      });
      // Wait until A actually holds the slot and its worker is up.
      for (let i = 0; i < 100 && aliveWorkerPids(aliveDir).length === 0; i += 1) await sleep(50);
      assertEq(aliveWorkerPids(aliveDir).length, 1, "job A's worker is running");

      // B waits for the only slot; cancelling B's wait aborts it
      // promptly with the cancellation error and spawns nothing.
      const jobB = startFakeJob(budget, {
        id: "cancel-b",
        profile: prof(160),
        sleepMs: 100,
        allocMB: 8,
        aliveDir,
        outFile: join(dir, "b.out"),
        content: "b-ok",
      });
      await sleep(300);
      const bCancelAt = Date.now();
      jobB.cancel();
      let bErr: unknown = null;
      try {
        await jobB.done;
      } catch (err) {
        bErr = err;
      }
      assertTrue(bErr instanceof ResourceCancelledError, `B's wait aborted as cancelled, got ${String(bErr)}`);
      assertTrue(Date.now() - bCancelAt < 2000, "B's wait aborted promptly");
      assertTrue(!existsSync(join(dir, "b.out")), "B never produced output");

      // C queues behind A. Cancelling A frees the slot and its
      // processes; C then runs to a correct completion.
      const jobC = startFakeJob(budget, {
        id: "cancel-c",
        profile: prof(160),
        sleepMs: 600,
        allocMB: 16,
        aliveDir,
        outFile: join(dir, "c.out"),
        content: "c-ok",
      });
      await sleep(200);
      const aPid = jobA.pid();
      assertTrue(aPid !== null && pidAlive(aPid), "job A's worker is alive before the cancel");
      jobA.cancel();
      let aErr: unknown = null;
      try {
        await jobA.done;
      } catch (err) {
        aErr = err;
      }
      assertTrue(aErr instanceof Error, "A's job rejected after cancellation");
      assertTrue(!pidAlive(aPid as number), "A's worker process is gone");
      const cOut = await jobC.done;
      assertEq(cOut, "c-ok", "job C completed correctly after A was cancelled");
      assertTrue((jobC.spawnedAt() as number) > 0, "job C's worker ran");
      assertEq(budget.snapshot().records.length, 0, "ledger empty after cancellation settles");
    },
  },
  {
    name: "failure isolation: one job's hard failure releases its reservation and leaves the other job's output correct",
    run: async () => {
      const dir = join(SCRATCH, "failure");
      const aliveDir = join(dir, "alive");
      mkdirSync(aliveDir, { recursive: true });
      const budget = new RenderBudget(smallPolicy(join(dir, "ledger")));
      const jobA = startFakeJob(budget, {
        id: "fail-a",
        profile: prof(160),
        sleepMs: 400,
        allocMB: 16,
        failCode: 3,
        aliveDir,
        outFile: join(dir, "a.out"),
        content: "a-ok",
      });
      const jobB = startFakeJob(budget, {
        id: "fail-b",
        profile: prof(160),
        sleepMs: 1800,
        allocMB: 32,
        aliveDir,
        outFile: join(dir, "b.out"),
        content: "b-rendered-ok",
      });
      let aErr: unknown = null;
      try {
        await jobA.done;
      } catch (err) {
        aErr = err;
      }
      assertTrue(aErr instanceof Error && (aErr as Error).message.includes("exited 3"), "A failed hard with its exit code");
      assertTrue(!existsSync(join(dir, "a.out")), "A produced no output artifact");
      // While B is still running, A's capacity is already back.
      const midSnap = budget.snapshot();
      assertEq(midSnap.records.length, 1, "only B's reservation remains after A failed");
      assertEq(midSnap.records[0].jobId, "fail-b", "the remaining reservation is B's");
      const bOut = await jobB.done;
      assertEq(bOut, "b-rendered-ok", "B's output is exactly correct despite A's failure");
      assertEq(budget.snapshot().records.length, 0, "ledger empty at the end");
    },
  },
  {
    name: "measurement: real engine renders regenerate the capacity evidence and the shipped profiles cover the measured peaks",
    run: async () => {
      const distMeasure = join(SKILL_DIR, "runtime", "dist", "tests", "measure-resources.js");
      const res = spawnSync(process.execPath, [distMeasure, "--write-evidence"], {
        encoding: "utf8",
        timeout: 1_800_000,
      });
      assertEq(res.status, 0, `measurement driver exit (stderr tail: ${(res.stderr ?? "").slice(-400)})`);
      assertTrue(existsSync(EVIDENCE_MEASUREMENTS), "measurements.json was written");
      const rec = JSON.parse(readFileSync(EVIDENCE_MEASUREMENTS, "utf8")) as {
        remotion: {
          peakRssMB: number;
          peakBrowserMains: number;
          phasePeaks: Record<string, { peakRssMB: number; peakBrowserMains: number }>;
        };
        hyperframes: {
          peakRssMB: number;
          peakBrowserMains: number;
          phasePeaks: Record<string, { peakRssMB: number; peakBrowserMains: number }>;
        };
        encode: Record<string, { wallMs: number; peakRssMB: number }>;
      };
      assertTrue(rec.remotion.peakRssMB >= 200, `remotion render tree peak ${rec.remotion.peakRssMB} MB is a real render`);
      assertTrue(rec.hyperframes.peakRssMB >= 200, `hyperframes render tree peak ${rec.hyperframes.peakRssMB} MB is a real render`);
      assertTrue(rec.remotion.peakBrowserMains >= 1, "a real browser ran for remotion");
      assertTrue(rec.hyperframes.peakBrowserMains >= 1, "a real browser ran for hyperframes");
      assertTrue(rec.encode.remotion.wallMs > 0 && rec.encode.hyperframes.wallMs > 0, "encode share measured for both engines");
      const remotionRenderPeak = rec.remotion.phasePeaks.previewRender?.peakRssMB ?? 0;
      const hyperframesRenderPeak = rec.hyperframes.phasePeaks.previewRender?.peakRssMB ?? 0;
      assertTrue(remotionRenderPeak > 0, "the remotion preview-render phase peak was measured");
      assertTrue(hyperframesRenderPeak > 0, "the hyperframes preview-render phase peak was measured");
      assertTrue(
        profileFor("remotion", "renderFinal").memoryMB >= remotionRenderPeak,
        `remotion render profile ${profileFor("remotion", "renderFinal").memoryMB} MB covers the measured render peak ${remotionRenderPeak} MB`
      );
      assertTrue(
        profileFor("hyperframes", "renderFinal").memoryMB >= hyperframesRenderPeak,
        `hyperframes render profile ${profileFor("hyperframes", "renderFinal").memoryMB} MB covers the measured render peak ${hyperframesRenderPeak} MB`
      );
      assertTrue(
        profileFor("remotion", "renderStill").memoryMB >= (rec.remotion.phasePeaks.stillWarmBundle?.peakRssMB ?? 0),
        "remotion still profile covers the measured warm still peak"
      );
      assertTrue(
        profileFor("hyperframes", "renderStill").memoryMB >= (rec.hyperframes.phasePeaks.stillSnapshot?.peakRssMB ?? 0),
        "hyperframes still profile covers the measured snapshot peak"
      );
      assertTrue(
        profileFor("hyperframes", "validate").memoryMB >= (rec.hyperframes.phasePeaks.validate?.peakRssMB ?? 0),
        "hyperframes validate profile covers the measured validate peak"
      );
      console.log(
        `  measured peaks this run: remotion render phase ${remotionRenderPeak} MB (constant in profiles.ts: ${MEASURED_PEAKS_MB.remotionRender} MB), ` +
          `hyperframes render phase ${hyperframesRenderPeak} MB (constant ${MEASURED_PEAKS_MB.hyperframesRender} MB)`
      );
    },
  },
  {
    name: "wiring (remotion): two concurrent stills serialize on one browser slot and both outputs are correct",
    run: async () => {
      const dir = join(SCRATCH, "wiring-remotion");
      const stageJob = (name: string, mutate?: (doc: Record<string, unknown>) => void): string => {
        const staged = join(dir, name);
        rmSync(staged, { recursive: true, force: true });
        cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), staged, { recursive: true });
        if (mutate) {
          const p = join(staged, "data", "bars.json");
          const doc = JSON.parse(readFileSync(p, "utf8")) as Record<string, unknown>;
          mutate(doc);
          writeFileSync(p, JSON.stringify(doc, null, 2) + "\n", "utf8");
        }
        return staged;
      };
      const dirA = stageJob("job-a");
      const dirB = stageJob("job-b", (d) => {
        d.domain = [0, 40];
        d.rows = [
          { id: "a", label: "Group A", value: 10 },
          { id: "b", label: "Group B", value: 20 },
          { id: "c", label: "Group C", value: 40 },
        ];
      });
      const jobA = loadValidatedJob(dirA);
      const jobB = loadValidatedJob(dirB);
      const adapterA = createRemotionAdapter({ outputDir: join(dir, "out-a") });
      const adapterB = createRemotionAdapter({ outputDir: join(dir, "out-b") });
      let maxRecords = 0;
      let sawReservation = false;
      const poller = setInterval(() => {
        const snap = getSharedRenderBudget().snapshot();
        maxRecords = Math.max(maxRecords, snap.records.length);
        if (snap.records.some((r) => r.engine === "remotion")) sawReservation = true;
      }, 75);
      try {
        const [evA, evB] = await Promise.all([
          adapterA.renderStill(jobA, 75),
          adapterB.renderStill(jobB, 75),
        ]);
        for (const ev of [evA, evB]) {
          const dims = readPngDimensions(ev.outputPaths[0]);
          assertEq(dims?.width, 1920, "still width");
          assertEq(dims?.height, 1080, "still height");
        }
      } finally {
        clearInterval(poller);
      }
      assertTrue(sawReservation, "a remotion reservation was observed in the shared ledger during the stills");
      assertTrue(maxRecords <= 1, `never more than one active reservation on a one-slot budget (saw ${maxRecords})`);
      assertEq(getSharedRenderBudget().snapshot().records.length, 0, "ledger empty after both stills");
    },
  },
  {
    name: "wiring (hyperframes): a snapshot still holds a reservation during the render and releases it after",
    run: async () => {
      const dir = join(SCRATCH, "wiring-hyperframes");
      const jobDir = join(dir, "c05-hf-job");
      rmSync(jobDir, { recursive: true, force: true });
      cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), jobDir, { recursive: true });
      const scenePath = join(jobDir, "scenes", "bar-01.json");
      const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
      scene.engine = "hyperframes";
      writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
      const manifestPath = join(jobDir, "manifest.json");
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as {
        job_id: string;
        rendering: { default_engine: string };
      };
      manifest.rendering.default_engine = "hyperframes";
      writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
      const job: ValidatedMotionJob = { jobDir, jobId: manifest.job_id, manifest: manifest as never };
      const adapter = new HyperframesAdapter();
      let sawReservation = false;
      const poller = setInterval(() => {
        const snap = getSharedRenderBudget().snapshot();
        if (snap.records.some((r) => r.engine === "hyperframes")) sawReservation = true;
      }, 50);
      try {
        const evidence = await adapter.renderStill(job, 75);
        assertEq(evidence.kind, "still", "still evidence kind");
        assertTrue(existsSync(join(jobDir, evidence.outputPaths[0])), "the still artifact exists");
      } finally {
        clearInterval(poller);
      }
      assertTrue(sawReservation, "a hyperframes reservation was observed during the snapshot");
      assertEq(getSharedRenderBudget().snapshot().records.length, 0, "ledger empty after the still");
    },
  },
  {
    name: "wiring (dispatcher cancel): cancelling a real Remotion preview frees its reservation and its browser",
    run: async () => {
      const dir = join(SCRATCH, "wiring-cancel");
      const jobDir = join(FIXTURES_ROOT, "modes", "powerpoint_graphic");
      const adapter = createRemotionAdapter({ outputDir: join(dir, "out") });
      const dispatcher = new MotionDispatcher(createRegistry([adapter]));
      const controller = new AbortController();
      const pending = dispatcher.renderPreview(jobDir, {
        signal: controller.signal,
        timeoutMs: 900_000,
      });
      // Attach a handler now: the assertion below runs seconds before
      // the await, and an unattached rejection in between would be
      // process-fatal instead of a case failure. Awaiting the same
      // promise later still observes the rejection.
      pending.catch(() => undefined);
      // Let the render get properly underway, then cancel it the way
      // the dispatcher contract prescribes.
      await sleep(2000);
      assertTrue(
        getSharedRenderBudget().snapshot().records.some((r) => r.engine === "remotion"),
        "the preview held a reservation while rendering"
      );
      controller.abort();
      let caught: unknown = null;
      try {
        await pending;
      } catch (err) {
        caught = err;
      }
      assertTrue(caught instanceof AdapterError, `expected AdapterError, got ${String(caught)}`);
      assertEq((caught as AdapterError).category, "MG_CANCELLED", "the cancellation category");
      assertEq((caught as AdapterError).exitClass, 8, "the cancellation exit class");
      // The abandoned adapter operation unwinds asynchronously; its
      // finally must release the reservation promptly.
      let emptied = false;
      for (let i = 0; i < 120; i += 1) {
        if (getSharedRenderBudget().snapshot().records.length === 0) {
          emptied = true;
          break;
        }
        await sleep(500);
      }
      assertTrue(emptied, "the cancelled preview's reservation was released");
    },
  },
];

// ---------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------

async function main(): Promise<number> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
  // The module top created TMP_SCRATCH before this wipe; the engines
  // put real temp usage under TMPDIR, so recreate it after the wipe.
  mkdirSync(TMP_SCRATCH, { recursive: true });
  // The wiring cases share one deliberately small budget (one browser
  // unit) through the test seam; unit cases build their own budgets.
  setSharedRenderBudgetForTests(
    new RenderBudget(
      smallPolicy(join(SCRATCH, "wiring-ledger"), {
        memoryBudgetMB: 16_384,
        maxBrowserUnits: 1,
        maxEncodeUnits: 4,
      })
    )
  );
  let passed = 0;
  let failed = 0;
  try {
    for (const c of CASES) {
      try {
        await c.run();
        passed += 1;
        console.log(`PASS ${c.name}`);
      } catch (err) {
        failed += 1;
        console.log(`FAIL ${c.name}`);
        console.log(`  ${(err as Error).message}`);
      }
    }
  } finally {
    setSharedRenderBudgetForTests(null);
  }
  const total = passed + failed;
  console.log(`Resources: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
