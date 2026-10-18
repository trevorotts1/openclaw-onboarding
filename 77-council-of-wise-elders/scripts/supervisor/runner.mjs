#!/usr/bin/env node
// Runnable supervisor driver for the Hybrid Council of Wise Elders (WER-026).
//
// Until this module existed the supervisor was a pure reducer with no entry
// point: nothing scheduled a sweep, nothing persisted the restart ledger and
// nothing recovered a pending action after a crash. This driver supplies that
// entry point by WIRING the existing modules. It adds no new policy, no new
// scheduling rule and no native binding: NATIVE_ADAPTER_BINDING in
// supervisor.mjs stays UNKNOWN and this driver does not change it.
//
// Hard limits, asserted by runner.test.mjs:
//   * no child_process, no node:http/https/net/dns/tls, no fetch, no sockets
//   * no credential file is read; every environment read is limited to PATH-free
//     CLI arguments
//   * every durable write is a temp-file-plus-rename inside --data-dir
//
// The injected sweep execute() only appends a receipt to the incident journal.
// It never spawns a process and never touches the network.
import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  NATIVE_ADAPTER_BINDING,
  SUPERVISOR_SCHEMA,
  canAutoRestart,
  createSupervisor,
  isExplicitStopFenced,
  reduceSupervisor,
} from "./supervisor.mjs";
import { defaultPolicy, validatePolicy } from "./policy.mjs";
import { createLeaderState, renewLeadership } from "./leader-state.mjs";
import {
  completeSweep,
  createPlannerState,
} from "./sweep-planner.mjs";
import { executePlannedSweep } from "./sweep-executor.mjs";
import { runPlannedSweep } from "./sweep-runner.mjs";
import { collectHealth } from "./health-collector.mjs";
import { observeHealth } from "./health-observer.mjs";
import { detectOverdue } from "./overdue-detector.mjs";
import {
  appendAction,
  appendIncident,
  createJournal,
  recordAttempt,
} from "./incident-journal.mjs";
import {
  addPendingAction,
  createRestartLedger,
  reconcileAfterRestart,
  recordRestart,
} from "./restart-reconciler.mjs";
import {
  beginDrain,
  completeStop,
  createAdmissionGate,
  startSupervisorInstance,
} from "./singleton.mjs";

export const RUNNER_STATE_SCHEMA = "wise-elders.hybrid-supervisor-runner-state/v1";
export const RUNNER_STATE_FILE = "state.json";
export const RUNNER_LOCK_FILE = "runner.lock";

export const EXIT = Object.freeze({
  OK: 0,
  FAILED: 1,
  USAGE: 2,
  REFUSED: 3,
  STALE_LEDGER: 4,
});

export class UsageError extends Error {
  constructor(message) {
    super(message);
    this.name = "UsageError";
  }
}

function positiveInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new UsageError(`${flag} must be a positive integer, got ${JSON.stringify(value)}`);
  }
  return parsed;
}

function nonNegativeInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new UsageError(`${flag} must be a non-negative integer, got ${JSON.stringify(value)}`);
  }
  return parsed;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

export function parseArgs(argv) {
  const options = {
    dataDir: null,
    ephemeral: false,
    intervalSeconds: 600,
    leaseSeconds: null,
    tickWorkMs: 0,
    instanceId: null,
    once: false,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const take = () => {
      index += 1;
      if (index >= argv.length) throw new UsageError(`${arg} requires a value`);
      return argv[index];
    };
    switch (arg) {
      case "--data-dir":
        options.dataDir = take();
        break;
      case "--ephemeral":
        options.ephemeral = true;
        break;
      case "--interval-seconds":
        options.intervalSeconds = positiveInteger(take(), arg);
        break;
      case "--lease-seconds":
        options.leaseSeconds = positiveInteger(take(), arg);
        break;
      case "--tick-work-ms":
        options.tickWorkMs = nonNegativeInteger(take(), arg);
        break;
      case "--instance-id":
        options.instanceId = take();
        break;
      case "--once":
        options.once = true;
        break;
      case "--help":
      case "-h":
        options.help = true;
        break;
      default:
        throw new UsageError(`unknown argument ${JSON.stringify(arg)}`);
    }
  }
  if (options.dataDir && options.ephemeral) {
    throw new UsageError("--data-dir and --ephemeral are mutually exclusive");
  }
  if (!options.dataDir && !options.ephemeral) {
    throw new UsageError("--data-dir is required; pass --ephemeral to use a temporary directory");
  }
  return options;
}

export function usage() {
  return [
    "usage: runner.mjs --data-dir <dir> [--interval-seconds 600] [--lease-seconds N]",
    "                  [--tick-work-ms N] [--instance-id ID] [--once]",
    "                  | --ephemeral [same options]",
    "",
    "The driver never spawns a process and never uses the network.",
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Durable state (temp file + rename, generation fenced)
// ---------------------------------------------------------------------------

let tempCounter = 0;

export function statePath(dataDir) {
  return join(dataDir, RUNNER_STATE_FILE);
}

export function parseState(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`runner state is not valid JSON: ${error.message}`);
  }
  if (parsed?.schema !== RUNNER_STATE_SCHEMA) {
    throw new Error(`runner state schema must be ${RUNNER_STATE_SCHEMA}`);
  }
  if (!Number.isInteger(parsed.ledger_generation) || parsed.ledger_generation < 0) {
    throw new Error("runner state ledger_generation must be a non-negative integer");
  }
  if (parsed.supervisor?.schema !== SUPERVISOR_SCHEMA) {
    throw new Error("runner state is missing the supervisor state");
  }
  return parsed;
}

export function readState(dataDir) {
  const path = statePath(dataDir);
  if (!existsSync(path)) return null;
  return parseState(readFileSync(path, "utf8"));
}

export function writeStateAtomic(dataDir, state) {
  const finalPath = statePath(dataDir);
  tempCounter += 1;
  const tempPath = join(
    dataDir,
    `.${RUNNER_STATE_FILE}.tmp-${process.pid}-${tempCounter}`,
  );
  const fd = openSync(tempPath, "wx", 0o600);
  try {
    writeSync(fd, `${JSON.stringify(state, null, 2)}\n`);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tempPath, finalPath);
  // Fsync the directory so the rename is durable across a kill -9.
  try {
    const dirFd = openSync(dataDir, "r");
    try {
      fsyncSync(dirFd);
    } finally {
      closeSync(dirFd);
    }
  } catch {
    // Directory fsync is best effort on platforms that refuse opening a dir.
  }
}

// A write is accepted only while the on-disk ledger generation still matches
// the caller's generation. A second instance that took over advances the
// generation, so this runner's stale write is refused rather than clobbering it.
export function commitState(dataDir, state, { expectedGeneration, nextGeneration = expectedGeneration, now_ms }) {
  if (!Number.isInteger(expectedGeneration) || expectedGeneration < 0) {
    throw new TypeError("expectedGeneration must be a non-negative integer");
  }
  if (!Number.isInteger(nextGeneration) || nextGeneration < expectedGeneration) {
    throw new TypeError("nextGeneration must be an integer >= expectedGeneration");
  }
  const disk = readState(dataDir);
  const diskGeneration = disk ? disk.ledger_generation : 0;
  if (diskGeneration !== expectedGeneration) {
    return Object.freeze({
      committed: false,
      reason: "STALE_LEDGER_GENERATION",
      expected_generation: expectedGeneration,
      disk_generation: diskGeneration,
    });
  }
  const next = {
    ...state,
    ledger_generation: nextGeneration,
    updated_at_ms: now_ms,
  };
  writeStateAtomic(dataDir, next);
  return Object.freeze({ committed: true, reason: "COMMITTED", state: next });
}

// ---------------------------------------------------------------------------
// Startup lock: short critical section around read-admit-persist only.
// The durable leader lease, not this lock, keeps a second instance out while a
// supervisor is running.
// ---------------------------------------------------------------------------

export function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

class LockRefusal extends Error {
  constructor(reason, ownerPid) {
    super(reason);
    this.name = "LockRefusal";
    this.reason = reason;
    this.ownerPid = ownerPid;
  }
}

function acquireStartupLock(dataDir, { alive = isPidAlive } = {}) {
  const lockPath = join(dataDir, RUNNER_LOCK_FILE);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = openSync(lockPath, "wx", 0o600);
      writeSync(fd, String(process.pid));
      closeSync(fd);
      return () => {
        try {
          unlinkSync(lockPath);
        } catch {
          // A vanished lock is already released.
        }
      };
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      let ownerPid = null;
      try {
        ownerPid = Number.parseInt(readFileSync(lockPath, "utf8").trim(), 10);
      } catch {
        ownerPid = null;
      }
      if (Number.isInteger(ownerPid) && alive(ownerPid)) {
        throw new LockRefusal("LOCK_HELD", ownerPid);
      }
      try {
        unlinkSync(lockPath);
      } catch {
        // Another starter won the race; the next attempt reports it.
      }
    }
  }
  throw new LockRefusal("LOCK_HELD", null);
}

// ---------------------------------------------------------------------------
// State creation and admission
// ---------------------------------------------------------------------------

export function createState({ now_ms, instance_id, pid, intervalSeconds, leaseMs }) {
  const policy = defaultPolicy();
  const verdict = validatePolicy(policy);
  if (!verdict.ok) {
    throw new Error(`invalid supervisor policy: ${verdict.errors.join("; ")}`);
  }
  return {
    schema: RUNNER_STATE_SCHEMA,
    ledger_generation: 0,
    instance_id,
    pid,
    created_at_ms: now_ms,
    updated_at_ms: now_ms,
    tick_seq: 0,
    completed_sweeps: 0,
    interrupted_ticks: 0,
    supervisor: createSupervisor({ policy, now_ms, leader_id: instance_id }),
    planner: createPlannerState({
      anchor_ms: now_ms,
      cadence_ms: intervalSeconds * 1000,
    }),
    leader: createLeaderState({ owner_id: null, now_ms, lease_ms: leaseMs }),
    journal: createJournal(),
    admission: createAdmissionGate({ now_ms }),
    restart_ledger: createRestartLedger(),
    reconciled_actions: [],
    last_health: null,
    last_observation: null,
    last_overdue: null,
    stopped_at_ms: null,
  };
}

// A lease whose recorded owner process is gone is a crash, not a live leader.
// Clearing it keeps the fencing generation intact and lets this start reclaim
// leadership with an ADVANCED generation.
export function recoverDeadLeader(state, { now_ms, alive = isPidAlive }) {
  const leader = state.leader;
  const leaseLive = Boolean(leader.leader_id) && now_ms < leader.lease_expires_at_ms;
  if (!leaseLive || alive(state.pid)) {
    return { state, recovered: false, reason: "NO_RECOVERY_NEEDED" };
  }
  const recoveredLeader = Object.freeze({
    ...leader,
    leader_id: null,
    lease_expires_at_ms: 0,
    revision: leader.revision + 1,
  });
  const { journal } = appendIncident(state.journal, {
    at_ms: now_ms,
    kind: "STALE_LEASE_RECOVERED",
    severity: "WARNING",
    detail: {
      prior_leader: leader.leader_id,
      prior_pid: state.pid ?? null,
      prior_fencing_generation: leader.fencing_generation,
    },
  });
  return {
    state: { ...state, leader: recoveredLeader, journal },
    recovered: true,
    reason: "DEAD_OWNER_RECOVERED",
  };
}

function writeJsonAtomicAt(path, value, dataDir) {
  tempCounter += 1;
  const base = path.slice(path.lastIndexOf("/") + 1);
  const tempPath = join(dataDir, `.${base}.tmp-${process.pid}-${tempCounter}`);
  const fd = openSync(tempPath, "wx", 0o600);
  try {
    writeSync(fd, `${JSON.stringify(value, null, 2)}\n`);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tempPath, path);
}

function writeRefusalReceipt(dataDir, receipt) {
  const path = join(dataDir, `refusal-${receipt.at_ms}-${process.pid}.json`);
  writeJsonAtomicAt(path, receipt, dataDir);
  return path;
}

// A start that follows a previous run is a durable restart event. The ledger
// budget is recorded, and an exhausted budget is journaled rather than hidden.
export function recordStartRestart(state, { now_ms }) {
  const priorRun = state.tick_seq > 0 || state.completed_sweeps > 0 || state.supervisor.state !== "STARTING";
  if (!priorRun) {
    return Object.freeze({ recorded: false, reason: "FIRST_START", state });
  }
  const restart = recordRestart(state.restart_ledger, { at_ms: now_ms });
  let journal = state.journal;
  if (!restart.allowed) {
    journal = appendIncident(journal, {
      at_ms: now_ms,
      kind: "RESTART_BUDGET_EXHAUSTED",
      severity: "WARNING",
      detail: { reason: restart.reason, restarts_in_window: restart.restarts_in_window },
    }).journal;
  }
  return Object.freeze({
    recorded: restart.allowed,
    reason: restart.reason,
    state: { ...state, restart_ledger: restart.ledger, journal },
  });
}

/**
 * admitInstance: read/create state, recover a dead owner's lease, then take the
 * singleton lease through singleton.mjs. A second live instance is refused with
 * the module's own reason (LEASE_HELD) and never advances the ledger generation.
 */
export function admitInstance({
  dataDir,
  now_ms,
  instanceId,
  pid,
  intervalSeconds,
  leaseMs,
  alive = isPidAlive,
}) {
  mkdirSync(dataDir, { recursive: true });
  const release = acquireStartupLock(dataDir, { alive });
  try {
    let state = readState(dataDir);
    if (!state) {
      state = createState({ now_ms, instance_id: instanceId, pid, intervalSeconds, leaseMs });
    }
    const recovery = recoverDeadLeader(state, { now_ms, alive });
    state = recovery.state;

    const admission = startSupervisorInstance({
      leaderState: state.leader,
      instance_id: instanceId,
      now_ms,
      lease_ms: leaseMs,
    });
    if (!admission.acquired) {
      const receipt = {
        event: "admission_refused",
        schema: admission.schema,
        at_ms: now_ms,
        instance_id: instanceId,
        pid,
        reason: admission.reason,
        duplicate_start: admission.duplicate_start,
        read_only: admission.read_only,
        ledger_generation: state.ledger_generation,
      };
      writeRefusalReceipt(dataDir, receipt);
      return Object.freeze({ admitted: false, receipt, state });
    }

    const next = {
      ...state,
      instance_id: instanceId,
      pid,
      stopped_at_ms: null,
      leader: admission.leader_state,
    };
    const committed = commitState(dataDir, next, {
      expectedGeneration: state.ledger_generation,
      nextGeneration: state.ledger_generation + 1,
      now_ms,
    });
    if (!committed.committed) {
      return Object.freeze({
        admitted: false,
        receipt: { event: "admission_refused", reason: committed.reason, at_ms: now_ms },
        state,
        stale: true,
      });
    }
    return Object.freeze({
      admitted: true,
      state: committed.state,
      fence: admission.fence,
      recovered: recovery.recovered,
      reason: admission.reason,
    });
  } finally {
    release();
  }
}

// ---------------------------------------------------------------------------
// Startup reconciliation: consume pending actions exactly once, then resume the
// interrupted work through sweep-runner as an EXTRA sweep (no scheduled slot is
// consumed, so a restart can never shift the fixed cadence).
// ---------------------------------------------------------------------------

export async function reconcilePending({ dataDir, state, fence, now_ms }) {
  const reconciliation = reconcileAfterRestart(state.restart_ledger, { now_ms });
  if (reconciliation.pending_action_count === 0) {
    return Object.freeze({ state, consumed: [], stale: false });
  }

  const consumed = reconciliation.pending_actions.map((action) =>
    Object.freeze({
      ...action,
      state: "RECONCILED",
      reconciled_at_ms: now_ms,
    }),
  );

  let journal = state.journal;
  for (const action of consumed) {
    const result = appendIncident(journal, {
      at_ms: now_ms,
      kind: "INTERRUPTED_TICK_RECONCILED",
      severity: "WARNING",
      detail: {
        pending_id: action.id,
        pending_kind: action.kind,
        recorded_at_ms: action.at_ms,
        tick_seq: action.payload?.tick_seq ?? null,
      },
    });
    journal = result.journal;
  }

  // Persist consumption BEFORE resuming, so a crash during the resume cannot
  // consume the same pending action a second time.
  const first = commitState(
    dataDir,
    {
      ...state,
      journal,
      interrupted_ticks: state.interrupted_ticks + consumed.length,
      reconciled_actions: [...state.reconciled_actions, ...consumed],
      restart_ledger: Object.freeze({
        ...reconciliation.ledger,
        pending_actions: Object.freeze([]),
      }),
    },
    { expectedGeneration: state.ledger_generation, now_ms },
  );
  if (!first.committed) {
    return Object.freeze({ state, consumed: [], stale: true, reason: first.reason });
  }
  let next = first.state;

  const resumed = [];
  for (const action of consumed) {
    const result = await runPlannedSweep({
      plannerState: next.planner,
      leaderState: next.leader,
      fence,
      now_ms,
      extra_requested: true,
      execute: async () => ({
        resumed_pending_id: action.id,
        resumed_tick_seq: action.payload?.tick_seq ?? null,
      }),
      cleanup: async () => ({ cleaned: true }),
    });
    if (!result.started) {
      const incident = appendIncident(next.journal, {
        at_ms: now_ms,
        kind: "RECOVERY_SWEEP_REFUSED",
        severity: "WARNING",
        detail: { pending_id: action.id, reason: result.reason },
      });
      next = { ...next, journal: incident.journal };
      continue;
    }
    const actionRes = appendAction(next.journal, {
      at_ms: now_ms,
      kind: "RECOVERY_SWEEP",
      target: action.id,
      payload: {
        decision_kind: result.decision.kind,
        consumes_scheduled_slot: result.decision.consumes_scheduled_slot,
        outcome_ok: result.outcome.ok,
      },
    });
    const attemptRes = recordAttempt(actionRes.journal, {
      action_id: actionRes.action.id,
      at_ms: now_ms,
      outcome: result.outcome.ok ? "SUCCEEDED" : "FAILED",
      detail: result.outcome.ok ? result.outcome.value : String(result.outcome.error),
    });
    next = {
      ...next,
      planner: result.state,
      journal: attemptRes.journal,
    };
    resumed.push(action.id);
  }

  const final = commitState(dataDir, next, {
    expectedGeneration: state.ledger_generation,
    now_ms,
  });
  if (!final.committed) {
    return Object.freeze({ state, consumed: [], stale: true, reason: final.reason });
  }
  return Object.freeze({
    state: final.state,
    consumed: consumed.map((action) => action.id),
    resumed,
    stale: false,
  });
}

// ---------------------------------------------------------------------------
// Supervisor resume
// ---------------------------------------------------------------------------

export function resumeSupervisorState(state, { now_ms, reason = "RUNNER_START" }) {
  let supervisor = state.supervisor;
  let journal = state.journal;
  let admission = state.admission;

  // The prior process's admission door closed when it stopped. This admitted
  // instance owns a new door; the old state is journaled, not silently erased.
  if (admission.state !== "OPEN") {
    journal = appendIncident(journal, {
      at_ms: now_ms,
      kind: "ADMISSION_REOPENED",
      severity: "NOTICE",
      detail: { prior_state: admission.state, prior_since_ms: admission.since_ms ?? null },
    }).journal;
    admission = createAdmissionGate({ now_ms });
  }

  if (isExplicitStopFenced(supervisor)) {
    return Object.freeze({
      ok: false,
      reason: "EXPLICIT_STOP_FENCE",
      state,
    });
  }

  if (supervisor.state !== "STARTING") {
    const gate = canAutoRestart(supervisor, now_ms);
    if (!gate.allowed) {
      return Object.freeze({ ok: false, reason: gate.reason, state });
    }
    const restart = reduceSupervisor(supervisor, {
      type: "AUTO_RESTART",
      at_ms: now_ms,
      by: reason,
    });
    if (!restart.accepted) {
      return Object.freeze({ ok: false, reason: restart.reason, state });
    }
    supervisor = restart.supervisor;
  }

  const begin = reduceSupervisor(supervisor, { type: "BEGIN_RECONCILE", at_ms: now_ms });
  if (!begin.accepted) {
    return Object.freeze({ ok: false, reason: begin.reason, state });
  }
  const done = reduceSupervisor(begin.supervisor, {
    type: "RECONCILE_SUCCEEDED",
    at_ms: now_ms,
  });
  if (!done.accepted) {
    return Object.freeze({ ok: false, reason: done.reason, state });
  }
  journal = appendIncident(journal, {
    at_ms: now_ms,
    kind: "SUPERVISOR_RECONCILED",
    severity: "NOTICE",
    detail: { reason, state: done.supervisor.state },
  }).journal;
  return Object.freeze({
    ok: true,
    reason: "RECONCILED",
    state: { ...state, supervisor: done.supervisor, admission, journal },
  });
}

// ---------------------------------------------------------------------------
// One tick
// ---------------------------------------------------------------------------

function delay(ms) {
  return new Promise((resolveDelay) => {
    setTimeout(resolveDelay, ms);
  });
}

export async function runOneTick({ dataDir, state, fence, now_ms, tickWorkMs = 0 }) {
  if (state.admission.state !== "OPEN") {
    return Object.freeze({
      executed: false,
      reason: "ADMISSION_FENCED",
      state,
    });
  }

  const renewal = renewLeadership(state.leader, {
    leader_id: fence.leader_id,
    fencing_generation: fence.fencing_generation,
    now_ms,
    lease_ms: state.leader.lease_ms,
  });
  if (!renewal.renewed) {
    const incident = appendIncident(state.journal, {
      at_ms: now_ms,
      kind: "LEASE_RENEWAL_REFUSED",
      severity: "WARNING",
      detail: { reason: renewal.reason },
    });
    const committed = commitState(
      dataDir,
      { ...state, journal: incident.journal },
      { expectedGeneration: state.ledger_generation, now_ms },
    );
    return Object.freeze({
      executed: false,
      reason: renewal.reason,
      state: committed.committed ? committed.state : state,
      stale: !committed.committed,
    });
  }

  let base = {
    ...state,
    leader: renewal.state,
    tick_seq: state.tick_seq + 1,
  };
  const tickSeq = base.tick_seq;

  // The pending action is durable BEFORE any side effect, so a kill -9 midway
  // leaves it on disk for the next start to reconcile.
  const added = addPendingAction(base.restart_ledger, {
    at_ms: now_ms,
    kind: "SCHEDULED_SWEEP_TICK",
    payload: { tick_seq: tickSeq, cadence_ms: base.planner.cadence_ms },
  });
  base = { ...base, restart_ledger: added.ledger };
  const pendingId = added.action.id;

  const pre = commitState(dataDir, base, {
    expectedGeneration: state.ledger_generation,
    now_ms,
  });
  if (!pre.committed) {
    return Object.freeze({ executed: false, reason: pre.reason, state, stale: true });
  }
  let next = pre.state;

  let receipt = null;
  const execute = async ({ decision }) => {
    if (tickWorkMs > 0) await delay(tickWorkMs);
    receipt = {
      receipt_id: `RCPT-${String(tickSeq).padStart(6, "0")}`,
      tick_seq: tickSeq,
      kind: decision.kind,
      due_at_ms: decision.due_at_ms ?? null,
      lateness_ms: decision.lateness_ms ?? 0,
      recorded_at_ms: now_ms,
    };
    return receipt;
  };
  const cleanup = async () => ({ cleaned: true });

  const result = await executePlannedSweep({
    plannerState: next.planner,
    leaderState: next.leader,
    fence,
    now_ms,
    extra_requested: false,
    admission: { fenced: next.admission.state !== "OPEN" },
    prepare: null,
    execute,
    cleanup,
  });

  let journal = next.journal;
  let ledger = next.restart_ledger;
  let planner = next.planner;
  let completed = next.completed_sweeps;
  let outcomeReason = result.reason;

  if (result.executed) {
    planner = completeSweep(result.state, {
      kind: result.decision.kind,
      finished_at_ms: now_ms,
    });
    const actionRes = appendAction(journal, {
      at_ms: now_ms,
      kind: "SWEEP_RECEIPT",
      target: pendingId,
      payload: receipt,
    });
    const attemptRes = recordAttempt(actionRes.journal, {
      action_id: actionRes.action.id,
      at_ms: now_ms,
      outcome: result.outcome.ok ? "SUCCEEDED" : "FAILED",
      detail: result.outcome.ok ? receipt : String(result.outcome.error),
    });
    journal = attemptRes.journal;
    if (result.outcome.ok) completed += 1;
    if (result.cleanup?.called && result.cleanup.ok === false) {
      journal = appendIncident(journal, {
        at_ms: now_ms,
        kind: "SWEEP_CLEANUP_FAILED",
        severity: "WARNING",
        detail: { error: String(result.cleanup.error) },
      }).journal;
    }
  } else {
    journal = appendIncident(journal, {
      at_ms: now_ms,
      kind: "SWEEP_NOT_EXECUTED",
      severity: "NOTICE",
      detail: { reason: result.reason, pending_id: pendingId },
    }).journal;
  }

  // A pending action is never left behind once the tick has returned: it is
  // either completed here or it survives only a real kill, for the reconciler.
  ledger = Object.freeze({
    ...ledger,
    pending_actions: Object.freeze(
      ledger.pending_actions.filter((action) => action.id !== pendingId),
    ),
  });

  const healthCollection = collectHealth({
    now_ms,
    subjects: [
      { id: "supervisor-process", kind: "process", liveness: "ALIVE" },
      { id: "state-directory", kind: "tool", liveness: "ALIVE" },
      // Honest: the native adapter is still unbound in this unit.
      { id: "native-adapter", kind: "native", liveness: "UNKNOWN" },
    ],
    due: { next_due_at_ms: planner.next_due_at_ms },
    previous: next.last_health,
  });
  const observation = observeHealth({
    now_ms,
    policy: next.supervisor.policy,
    heartbeat: { last_seen_ms: now_ms },
    sweep: {},
    leader: {
      lease_expires_at_ms: next.leader.lease_expires_at_ms,
      is_leader: true,
    },
  });
  const overdue = detectOverdue({
    now_ms,
    due_at_ms: planner.next_due_at_ms,
    pid_alive: true,
  });

  if (overdue.overdue) {
    journal = appendIncident(journal, {
      at_ms: now_ms,
      kind: "SUPERVISOR_OVERDUE",
      severity: "DEGRADED",
      detail: { due_at_ms: overdue.due_at_ms, overdue_at_ms: overdue.overdue_at_ms },
    }).journal;
  }

  let supervisor = next.supervisor;
  if (healthCollection.verdict === "DEGRADED" && ["HEALTHY", "RECONCILING"].includes(supervisor.state)) {
    const degraded = reduceSupervisor(supervisor, { type: "HEALTH_DEGRADED", at_ms: now_ms });
    if (degraded.accepted) supervisor = degraded.supervisor;
  } else if (healthCollection.verdict === "HEALTHY" && supervisor.state === "DEGRADED") {
    const recovered = reduceSupervisor(supervisor, { type: "HEALTH_RECOVERED", at_ms: now_ms });
    if (recovered.accepted) supervisor = recovered.supervisor;
  }

  next = {
    ...next,
    supervisor,
    planner,
    journal,
    restart_ledger: ledger,
    completed_sweeps: completed,
    last_health: healthCollection,
    last_observation: observation,
    last_overdue: overdue,
  };
  const committed = commitState(dataDir, next, {
    expectedGeneration: state.ledger_generation,
    now_ms,
  });
  if (!committed.committed) {
    return Object.freeze({ executed: false, reason: committed.reason, state, stale: true });
  }
  return Object.freeze({
    executed: result.executed,
    reason: outcomeReason,
    decision: result.decision,
    receipt,
    state: committed.state,
    stale: false,
  });
}

// ---------------------------------------------------------------------------
// Graceful stop
// ---------------------------------------------------------------------------

export function stopState(state, { now_ms, reason = "SIGNAL" }) {
  let supervisor = state.supervisor;
  let journal = state.journal;

  if (supervisor.state !== "STOPPED") {
    const request = reduceSupervisor(supervisor, {
      type: "REQUEST_STOP",
      at_ms: now_ms,
      explicit: false,
      reason,
    });
    if (request.accepted) {
      supervisor = request.supervisor;
      const complete = reduceSupervisor(supervisor, { type: "STOP_COMPLETE", at_ms: now_ms });
      if (complete.accepted) supervisor = complete.supervisor;
    }
  }

  let gate = state.admission;
  if (gate.state === "OPEN") {
    gate = beginDrain(gate, { at_ms: now_ms, reason }).gate;
  }
  if (gate.state === "DRAINING") {
    gate = completeStop(gate, { at_ms: now_ms }).gate;
  }

  journal = appendIncident(journal, {
    at_ms: now_ms,
    kind: "SUPERVISOR_STOPPED",
    severity: "NOTICE",
    detail: { reason, state: supervisor.state },
  }).journal;

  return {
    ...state,
    supervisor,
    admission: gate,
    journal,
    stopped_at_ms: now_ms,
  };
}

export function drainAndStop({ dataDir, state, now_ms, reason }) {
  const drained = stopState(state, { now_ms, reason });
  const committed = commitState(dataDir, drained, {
    expectedGeneration: state.ledger_generation,
    now_ms,
  });
  if (!committed.committed) {
    return Object.freeze({ stopped: false, reason: committed.reason, state });
  }
  return Object.freeze({ stopped: true, reason: "STOPPED", state: committed.state });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function emit(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

export async function main(argv = process.argv.slice(2)) {
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    process.stderr.write(`${error.message}\n${usage()}\n`);
    return EXIT.USAGE;
  }
  if (options.help) {
    process.stdout.write(`${usage()}\n`);
    return EXIT.OK;
  }

  const dataDir =
    options.dataDir !== null
      ? resolve(options.dataDir)
      : mkdtempSync(join(tmpdir(), "wise-elders-supervisor-"));
  mkdirSync(dataDir, { recursive: true });

  const intervalSeconds = options.intervalSeconds;
  const leaseSeconds = options.leaseSeconds ?? Math.max(120, intervalSeconds * 3);
  const instanceId = options.instanceId ?? `runner-${process.pid}`;

  const admission = admitInstance({
    dataDir,
    now_ms: Date.now(),
    instanceId,
    pid: process.pid,
    intervalSeconds,
    leaseMs: leaseSeconds * 1000,
  });
  if (!admission.admitted) {
    emit(admission.receipt);
    return admission.stale ? EXIT.STALE_LEDGER : EXIT.REFUSED;
  }

  let state = admission.state;
  const fence = admission.fence;
  const restart = recordStartRestart(state, { now_ms: Date.now() });
  if (restart.state !== state) {
    const commitRestart = commitState(dataDir, restart.state, {
      expectedGeneration: state.ledger_generation,
      now_ms: Date.now(),
    });
    if (!commitRestart.committed) {
      emit({ event: "stale_ledger_refused", reason: commitRestart.reason });
      return EXIT.STALE_LEDGER;
    }
    state = commitRestart.state;
    emit({ event: "restart_recorded", reason: restart.reason, ledger_generation: state.ledger_generation });
  }
  emit({
    event: "admitted",
    instance_id: instanceId,
    pid: process.pid,
    data_dir: dataDir,
    ledger_generation: state.ledger_generation,
    fencing_generation: state.leader.fencing_generation,
    recovered_dead_owner: admission.recovered,
    native_adapter_binding: NATIVE_ADAPTER_BINDING.status,
  });

  const reconciliation = await reconcilePending({
    dataDir,
    state,
    fence,
    now_ms: Date.now(),
  });
  if (reconciliation.stale) {
    emit({ event: "stale_ledger_refused", reason: reconciliation.reason });
    return EXIT.STALE_LEDGER;
  }
  state = reconciliation.state;
  if (reconciliation.consumed.length > 0) {
    emit({
      event: "reconciled",
      pending_actions: reconciliation.consumed,
      resumed: reconciliation.resumed,
      ledger_generation: state.ledger_generation,
      fencing_generation: state.leader.fencing_generation,
    });
  }

  const resumed = resumeSupervisorState(state, { now_ms: Date.now() });
  if (!resumed.ok) {
    // The durable state must record why this start did not proceed.
    const refusal = {
      ...state,
      journal: appendIncident(state.journal, {
        at_ms: Date.now(),
        kind: "START_REFUSED",
        severity: "WARNING",
        detail: { reason: resumed.reason },
      }).journal,
    };
    const committed = commitState(dataDir, refusal, {
      expectedGeneration: state.ledger_generation,
      now_ms: Date.now(),
    });
    emit({
      event: "start_refused",
      reason: resumed.reason,
      ledger_generation: committed.committed ? committed.state.ledger_generation : state.ledger_generation,
    });
    return EXIT.REFUSED;
  }
  state = resumed.state;
  const commitResumed = commitState(dataDir, state, {
    expectedGeneration: state.ledger_generation,
    now_ms: Date.now(),
  });
  if (!commitResumed.committed) {
    emit({ event: "stale_ledger_refused", reason: commitResumed.reason });
    return EXIT.STALE_LEDGER;
  }
  state = commitResumed.state;
  emit({
    event: "reconciled_state",
    state: state.supervisor.state,
    ledger_generation: state.ledger_generation,
    fencing_generation: state.leader.fencing_generation,
  });

  let stopping = false;
  let stopReason = null;
  let wake = null;

  const onSignal = (signal) => {
    if (stopping) return;
    stopping = true;
    stopReason = signal;
    if (wake) wake();
  };
  process.on("SIGINT", () => onSignal("SIGINT"));
  process.on("SIGTERM", () => onSignal("SIGTERM"));

  const waitForDue = () => {
    const waitMs = Math.max(0, state.planner.next_due_at_ms - Date.now() + 25);
    return new Promise((resolveWait) => {
      if (stopping) {
        resolveWait("signal");
        return;
      }
      const timer = setTimeout(() => {
        wake = null;
        resolveWait("timeout");
      }, waitMs);
      wake = () => {
        clearTimeout(timer);
        wake = null;
        resolveWait("signal");
      };
    });
  };

  for (;;) {
    if (stopping) break;
    try {
      const tick = await runOneTick({
        dataDir,
        state,
        fence,
        now_ms: Date.now(),
        tickWorkMs: options.tickWorkMs,
      });
      if (tick.stale) {
        emit({ event: "stale_ledger_refused", reason: tick.reason });
        return EXIT.STALE_LEDGER;
      }
      state = tick.state;
      emit({
        event: "tick",
        tick_seq: state.tick_seq,
        executed: tick.executed,
        reason: tick.reason,
        decision_kind: tick.decision?.kind ?? null,
        receipt_id: tick.receipt?.receipt_id ?? null,
        completed_sweeps: state.completed_sweeps,
        ledger_generation: state.ledger_generation,
        state: state.supervisor.state,
      });
    } catch (error) {
      // A failed tick is journaled, never silently swallowed.
      const now = Date.now();
      const next = {
        ...state,
        journal: appendIncident(state.journal, {
          at_ms: now,
          kind: "TICK_FAILED",
          severity: "WARNING",
          detail: { error: String(error?.message ?? error) },
        }).journal,
      };
      const committed = commitState(dataDir, next, {
        expectedGeneration: state.ledger_generation,
        now_ms: now,
      });
      if (committed.committed) state = committed.state;
      emit({ event: "tick_failed", error: String(error?.message ?? error) });
    }
    if (options.once || stopping) break;
    const waited = await waitForDue();
    if (waited === "signal") break;
  }

  const final = drainAndStop({
    dataDir,
    state,
    now_ms: Date.now(),
    reason: stopReason ?? (options.once ? "ONCE_COMPLETE" : "RUNNER_EXIT"),
  });
  if (!final.stopped) {
    emit({ event: "stop_refused", reason: final.reason });
    return final.reason === "STALE_LEDGER_GENERATION" ? EXIT.STALE_LEDGER : EXIT.FAILED;
  }
  emit({
    event: "stopped",
    reason: final.reason,
    supervisor_state: final.state.supervisor.state,
    admission_state: final.state.admission.state,
    ledger_generation: final.state.ledger_generation,
    completed_sweeps: final.state.completed_sweeps,
    interrupted_ticks: final.state.interrupted_ticks,
    pid: process.pid,
  });
  return EXIT.OK;
}

// Compare real paths on BOTH sides. A plain `pathToFileURL(process.argv[1])`
// comparison silently no-ops when the script is reached through a symlink: the
// launcher path differs from this module's real URL, so `isEntryPoint` is false,
// the process exits 0 and does nothing at all. macOS makes this the common case
// because /tmp is a symlink to /private/tmp. realpathSync falls back to the
// lexical path when resolution fails, so a genuinely missing argv[1] still just
// fails the comparison rather than throwing.
function realPathOrSame(path) {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

const isEntryPoint =
  process.argv[1] !== undefined &&
  (() => {
    try {
      return realPathOrSame(fileURLToPath(import.meta.url)) === realPathOrSame(process.argv[1]);
    } catch {
      return false;
    }
  })();

if (isEntryPoint) {
  main()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      process.stderr.write(`${error?.stack ?? error}\n`);
      process.exitCode = EXIT.FAILED;
    });
}
