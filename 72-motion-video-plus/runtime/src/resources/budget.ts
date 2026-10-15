// The shared render resource budget (Directive MG-028).
//
// One RenderBudget instance per process, backed by an on-disk ledger
// in the shared runtime state directory, so the budget is global
// across every render process on the machine: two agent processes
// rendering at once account into the same ledger, not into two
// private guesses.
//
// Mechanics, and why they are what they are:
// - The ledger is one JSON file per reservation. Capacity checks sum
//   the live records; a reservation is created only when the sum plus
//   the candidate fits every dimension (memory, browsers, encoders,
//   disk). Check-and-create runs inside a short mkdir mutex so two
//   processes cannot both pass the check and overbook.
// - Holders heartbeat their record. A record whose owner process is
//   gone is reaped by the next acquire or snapshot, so a crashed
//   render frees its capacity without operator action; a record whose
//   heartbeat has been silent far past any legitimate render is
//   reaped even if the pid was recycled.
// - Cancellation is honored while WAITING: an acquire whose caller is
//   cancelled aborts promptly and never launches anything. A running
//   render is cancelled by the adapter's own engine-level cancel; the
//   reservation is then released by the operation's finally block,
//   which is what frees the capacity.
// - Within one process, holds are reference-counted per job: adapter
//   operations nest (a Remotion final is a video render plus a poster
//   still), and the nested operation must not deadlock against its
//   own outer reservation or double-count it.

import { randomBytes } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { deriveBudgetPolicy } from "./preflight";
import { profileFor } from "./profiles";
import {
  ResourceCancelledError,
  ResourceExhaustedError,
  type AcquireOptions,
  type BudgetPolicy,
  type Reservation,
  type ReservationRecord,
  type ReservationRequest,
  type ResourceProfile,
} from "./types";

const WAIT_POLL_MS = 100;
const HEARTBEAT_MS = 15_000;
const LOCK_STEAL_MS = 30_000;

function pidAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but is not ours to signal.
    return (err as NodeJS.ErrnoException).code === "EPERM";
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface Hold {
  record: ReservationRecord;
  count: number;
  heartbeat: NodeJS.Timeout | null;
}

export interface BudgetSnapshot {
  records: ReservationRecord[];
  totals: { memoryMB: number; browserUnits: number; encodeUnits: number; diskMB: number };
  policy: BudgetPolicy;
}

export class RenderBudget {
  readonly policy: BudgetPolicy;
  private readonly reservationsDir: string;
  private readonly lockDir: string;
  private readonly holds = new Map<string, Hold>();

  constructor(policy: BudgetPolicy) {
    this.policy = policy;
    this.reservationsDir = join(policy.stateDir, "reservations");
    this.lockDir = join(policy.stateDir, "lock");
    mkdirSync(this.reservationsDir, { recursive: true });
  }

  // -- ledger primitives (synchronous; always under the mutex) -------

  private withLock<T>(fn: () => T): T {
    const ownerPath = join(this.lockDir, "owner.json");
    const deadline = Date.now() + 30_000;
    for (;;) {
      try {
        mkdirSync(this.lockDir, { recursive: false });
        writeFileSync(
          ownerPath,
          JSON.stringify({ pid: process.pid, at: Date.now() }) + "\n",
          "utf8"
        );
        break;
      } catch (err) {
        if ((err as NodeJS.ErrnoException).code !== "EEXIST") throw err;
        let steal = false;
        try {
          const owner = JSON.parse(readFileSync(ownerPath, "utf8")) as {
            pid?: number;
            at?: number;
          };
          if (
            typeof owner.pid === "number" &&
            (!pidAlive(owner.pid) || Date.now() - (owner.at ?? 0) > LOCK_STEAL_MS)
          ) {
            steal = true;
          }
        } catch {
          try {
            if (Date.now() - statSync(this.lockDir).mtimeMs > LOCK_STEAL_MS) steal = true;
          } catch {
            steal = true;
          }
        }
        if (steal) {
          rmSync(this.lockDir, { recursive: true, force: true });
          continue;
        }
        if (Date.now() > deadline) {
          throw new Error(
            `render budget lock in ${this.policy.stateDir} stayed contended for 30 s`
          );
        }
        const until = Date.now() + 5;
        while (Date.now() < until) {
          // Brief spin: the critical section it waits for is a few
          // file operations, never a render.
        }
      }
    }
    try {
      return fn();
    } finally {
      rmSync(this.lockDir, { recursive: true, force: true });
    }
  }

  private recordPath(id: string): string {
    return join(this.reservationsDir, `${id}.json`);
  }

  private readRecordsLocked(): ReservationRecord[] {
    const out: ReservationRecord[] = [];
    for (const name of readdirSync(this.reservationsDir)) {
      if (!name.endsWith(".json")) continue;
      try {
        const parsed = JSON.parse(
          readFileSync(join(this.reservationsDir, name), "utf8")
        ) as ReservationRecord;
        if (parsed && typeof parsed.id === "string" && parsed.profile) out.push(parsed);
      } catch {
        // Corrupt record: reapStaleLocked removes it once it is old
        // enough not to be a half-written create (creates are atomic
        // renames, so a corrupt file is never a live reservation).
      }
    }
    return out;
  }

  /** Remove records that can no longer belong to a live render.
   * Called inside the mutex before every capacity decision. */
  private reapStaleLocked(): ReservationRecord[] {
    const reaped: ReservationRecord[] = [];
    const hardStaleMs = Math.max(this.policy.staleHeartbeatMs * 5, 600_000);
    const now = Date.now();
    for (const name of readdirSync(this.reservationsDir)) {
      if (!name.endsWith(".json")) continue;
      const path = join(this.reservationsDir, name);
      let record: ReservationRecord | null = null;
      try {
        record = JSON.parse(readFileSync(path, "utf8")) as ReservationRecord;
      } catch {
        try {
          if (now - statSync(path).mtimeMs > 60_000) rmSync(path, { force: true });
        } catch {
          // Already gone.
        }
        continue;
      }
      const heartbeatAge = now - Date.parse(record.heartbeatAt || record.acquiredAt);
      const ownerGone = !pidAlive(record.pid);
      if (ownerGone || heartbeatAge > hardStaleMs) {
        // Never reap this process's own live holds, however old the
        // heartbeat looks (a blocked event loop stalls heartbeats,
        // not renders).
        if (record.pid === process.pid && this.holds.has(record.jobId)) continue;
        rmSync(path, { force: true });
        reaped.push(record);
      }
    }
    return reaped;
  }

  private totals(records: ReservationRecord[]): BudgetSnapshot["totals"] {
    const totals = { memoryMB: 0, browserUnits: 0, encodeUnits: 0, diskMB: 0 };
    for (const r of records) {
      totals.memoryMB += r.profile.memoryMB;
      totals.browserUnits += r.profile.browserUnits;
      totals.encodeUnits += r.profile.encodeUnits;
      totals.diskMB += r.profile.diskMB;
    }
    return totals;
  }

  private fits(records: ReservationRecord[], profile: ResourceProfile): boolean {
    const t = this.totals(records);
    return (
      t.memoryMB + profile.memoryMB <= this.policy.memoryBudgetMB &&
      t.browserUnits + profile.browserUnits <= this.policy.maxBrowserUnits &&
      t.encodeUnits + profile.encodeUnits <= this.policy.maxEncodeUnits &&
      t.diskMB + profile.diskMB <= this.policy.maxDiskMB
    );
  }

  private describeLoad(records: ReservationRecord[]): string {
    const t = this.totals(records);
    return (
      `active reservations ${records.length} using ${t.memoryMB}/${this.policy.memoryBudgetMB} MB, ` +
      `${t.browserUnits}/${this.policy.maxBrowserUnits} browsers, ` +
      `${t.encodeUnits}/${this.policy.maxEncodeUnits} encoders, ` +
      `${t.diskMB}/${this.policy.maxDiskMB} MB disk`
    );
  }

  // -- public API ------------------------------------------------------

  /** Current accounting, after reaping stale records. */
  snapshot(): BudgetSnapshot {
    return this.withLock(() => {
      this.reapStaleLocked();
      const records = this.readRecordsLocked();
      return { records, totals: this.totals(records), policy: this.policy };
    });
  }

  /**
   * Acquire a reservation, waiting for capacity when the budget is
   * full. The wait honors cancellation promptly and fails with
   * ResourceExhaustedError after the timeout: a render that cannot be
   * afforded is refused BEFORE any browser or encoder launches, which
   * is the entire point of the budget.
   */
  async acquire(request: ReservationRequest, opts?: AcquireOptions): Promise<Reservation> {
    const existing = this.holds.get(request.jobId);
    if (existing && existing.record.engine === request.engine) {
      existing.count += 1;
      return this.reservationFor(existing);
    }
    const profile = request.profile ?? profileFor(request.engine, request.operation);
    const timeoutMs = opts?.timeoutMs ?? this.policy.acquireTimeoutMs;
    const started = Date.now();
    for (;;) {
      if (opts?.isCancelled?.()) {
        throw new ResourceCancelledError(request.engine, request.jobId);
      }
      const acquired = this.withLock(() => {
        this.reapStaleLocked();
        const records = this.readRecordsLocked();
        if (!this.fits(records, profile)) return null;
        const nowIso = new Date().toISOString();
        const record: ReservationRecord = {
          id: `res-${Date.now().toString(36)}-${process.pid}-${randomBytes(4).toString("hex")}`,
          jobId: request.jobId,
          engine: request.engine,
          operation: request.operation,
          pid: process.pid,
          acquiredAt: nowIso,
          heartbeatAt: nowIso,
          profile,
        };
        const tmp = `${this.recordPath(record.id)}.tmp-${process.pid}`;
        writeFileSync(tmp, JSON.stringify(record, null, 2) + "\n", "utf8");
        renameSync(tmp, this.recordPath(record.id));
        return record;
      });
      if (acquired) {
        const hold: Hold = { record: acquired, count: 1, heartbeat: null };
        hold.heartbeat = setInterval(() => {
          try {
            const path = this.recordPath(acquired.id);
            if (!existsSync(path)) return;
            acquired.heartbeatAt = new Date().toISOString();
            const tmp = `${path}.hb-${process.pid}`;
            writeFileSync(tmp, JSON.stringify(acquired, null, 2) + "\n", "utf8");
            renameSync(tmp, path);
          } catch {
            // A missed heartbeat is recovered by the next one; a
            // reaped record makes release a no-op, never an error.
          }
        }, HEARTBEAT_MS);
        hold.heartbeat.unref();
        this.holds.set(request.jobId, hold);
        return this.reservationFor(hold);
      }
      if (Date.now() - started >= timeoutMs) {
        const records = this.withLock(() => this.readRecordsLocked());
        throw new ResourceExhaustedError(
          request.engine,
          request.jobId,
          Date.now() - started,
          `needs ${profile.memoryMB} MB, ${profile.browserUnits} browser(s), ` +
            `${profile.encodeUnits} encoder(s), ${profile.diskMB} MB disk; ${this.describeLoad(records)}`
        );
      }
      await sleep(WAIT_POLL_MS);
    }
  }

  private reservationFor(hold: Hold): Reservation {
    const budget = this;
    let released = false;
    return {
      id: hold.record.id,
      jobId: hold.record.jobId,
      engine: hold.record.engine,
      operation: hold.record.operation,
      profile: hold.record.profile,
      acquiredAt: hold.record.acquiredAt,
      async release(): Promise<void> {
        if (released) return;
        released = true;
        hold.count -= 1;
        if (hold.count > 0) return;
        budget.holds.delete(hold.record.jobId);
        if (hold.heartbeat) clearInterval(hold.heartbeat);
        budget.withLock(() => {
          rmSync(budget.recordPath(hold.record.id), { force: true });
        });
      },
    };
  }
}

let sharedBudget: RenderBudget | null = null;

/** The process-wide shared budget: one instance, policy derived from
 * this machine at first use, ledger in the shared runtime state dir.
 * The adapters acquire from this budget so every render in the
 * process (and every cooperating process on the machine) accounts
 * into the same totals. */
export function getSharedRenderBudget(): RenderBudget {
  if (!sharedBudget) sharedBudget = new RenderBudget(deriveBudgetPolicy());
  return sharedBudget;
}

/** Test seam: replace the shared budget (the MG-028 runner points it
 * at a scratch ledger with a deliberately small policy). */
export function setSharedRenderBudgetForTests(budget: RenderBudget | null): void {
  sharedBudget = budget;
}

/** Acquire, run, and always release: the shape adapter operations
 * use so a failed or cancelled render frees its capacity in the
 * same code path as a successful one. */
export async function withRenderSlot<T>(
  request: ReservationRequest,
  opts: AcquireOptions | undefined,
  fn: (reservation: Reservation) => Promise<T>
): Promise<T> {
  const reservation = await getSharedRenderBudget().acquire(request, opts);
  try {
    return await fn(reservation);
  } finally {
    await reservation.release();
  }
}
