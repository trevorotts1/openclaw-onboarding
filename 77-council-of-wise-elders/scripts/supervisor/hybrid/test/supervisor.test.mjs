import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  applySweepResult,
  attemptAutomaticRestart,
  claimLeadership,
  commitUnderFence,
  createLeadership,
  createRestartGovernor,
  createSupervisor,
  createLeaseStore,
  canRestart,
  dueSweep,
  DuplicateStartError,
  finishStop,
  FULL_SWEEP_INTERVAL_MS,
  InvalidTransitionError,
  makeSweepSchedule,
  NATIVE_ADAPTER_BINDING,
  nextDueAt,
  NotLeaderError,
  observeHealth,
  parseLeadership,
  POLICY,
  recordReconciliationOutcome,
  requestExplicitStop,
  runSweep,
  serializeLeadership,
  StaleFencingGenerationError,
  startSupervisor,
  SUPERVISOR_STATE,
  SweepTimeoutError,
  SWEEP_KIND,
  transition,
} from '../supervisor.mjs';

const S = 1000; // fake-time seconds

// ---------------------------------------------------------------------------
// Sweep cadence: fixed schedule anchor, next_due_at = prior due + cadence.
// Never completion+interval — the cadence provably cannot drift.
// ---------------------------------------------------------------------------

describe('sweep planner cadence (pure over fake time)', () => {
  it('keeps next due on the anchor grid no matter how long sweeps run', () => {
    let schedule = makeSweepSchedule({ anchorMs: 1_000_000, cadenceMs: 600 * S });

    // Three scheduled sweeps, each running 130s (well past one cadence step).
    const dues = [];
    for (let i = 0; i < 3; i += 1) {
      const dueAtMs = schedule.nextDueAtMs;
      dues.push(dueAtMs);
      const startedAtMs = dueAtMs + 40 * S;
      const finishedAtMs = dueAtMs + 130 * S;
      const after = applySweepResult(schedule, {
        kind: SWEEP_KIND.SCHEDULED,
        dueAtMs,
        startedAtMs,
        finishedAtMs,
        outcome: 'SUCCESS',
      });
      // The drift bug would compute finish+600; the anchor rule must win.
      assert.notEqual(after.nextDueAtMs, finishedAtMs + 600 * S);
      assert.equal(after.nextDueAtMs, dueAtMs + 600 * S);
      schedule = after;
    }
    assert.deepEqual(dues, [1_000_000, 1_600_000, 2_200_000]);
    assert.equal(schedule.nextDueAtMs, 2_800_000);
  });

  it('nextDueAt is prior-due + cadence and takes no finish time at all', () => {
    assert.equal(nextDueAt(600 * S, FULL_SWEEP_INTERVAL_MS), 1200 * S);
  });
});

describe('EXTRA sweeps never consume a scheduled slot', () => {
  it('EXTRA at t=590s leaves scheduled t=600s pending and later records real lateness', () => {
    let schedule = makeSweepSchedule({ anchorMs: 600 * S, cadenceMs: 600 * S });

    // EXTRA sweep at t=590s, done at t=595s.
    schedule = applySweepResult(schedule, {
      kind: SWEEP_KIND.EXTRA,
      startedAtMs: 590 * S,
      finishedAtMs: 595 * S,
      outcome: 'SUCCESS',
    });
    assert.equal(schedule.nextDueAtMs, 600 * S, 'EXTRA must not advance the schedule');
    assert.equal(schedule.runs[0].consumesScheduledSlot, false);
    assert.equal(dueSweep(schedule, 595 * S).due, false, 'scheduled t=600s still pending');

    // The scheduled sweep really starts at t=655s: 55s of real lateness.
    const gate = dueSweep(schedule, 655 * S);
    assert.equal(gate.due, true);
    assert.equal(gate.dueAtMs, 600 * S);
    assert.equal(gate.latenessMs, 55 * S, 'real lateness measured from due, not from EXTRA');
    assert.equal(gate.unhealthy, true, '55s late trips the due+30s unhealthy gate');

    schedule = applySweepResult(schedule, {
      kind: SWEEP_KIND.SCHEDULED,
      dueAtMs: 600 * S,
      startedAtMs: 655 * S,
      finishedAtMs: 700 * S,
      outcome: 'SUCCESS',
    });
    const record = schedule.runs[1];
    assert.equal(record.consumesScheduledSlot, true);
    assert.equal(record.latenessMs, 55 * S, 'real lateness recorded on the scheduled run');
    assert.equal(schedule.nextDueAtMs, 1200 * S);
  });
});

describe('due+30s unhealthy gate', () => {
  it('trips exactly at due+30s, not before', () => {
    const schedule = makeSweepSchedule({ anchorMs: 600 * S });
    assert.equal(dueSweep(schedule, 629 * S + 999).unhealthy, false);
    assert.equal(dueSweep(schedule, 630 * S).unhealthy, true);
    assert.equal(dueSweep(schedule, 631 * S).unhealthy, true);
  });
});

// ---------------------------------------------------------------------------
// Duplicate start, explicit-stop fence, reconciliation outcomes
// ---------------------------------------------------------------------------

describe('supervisor state machine', () => {
  it('duplicate start refuses', () => {
    const machine = createSupervisor({ supervisorId: 'sup-1' });
    assert.equal(machine.state, SUPERVISOR_STATE.STARTING);
    assert.throws(() => startSupervisor(machine), DuplicateStartError);

    const healthy = transition(transition(machine, SUPERVISOR_STATE.RECONCILING), SUPERVISOR_STATE.HEALTHY);
    assert.throws(() => startSupervisor(healthy), DuplicateStartError);

    // A fully stopped supervisor may be started again.
    const stopped = finishStop(requestExplicitStop(healthy));
    assert.equal(stopped.state, SUPERVISOR_STATE.STOPPED);
    assert.equal(startSupervisor(stopped).state, SUPERVISOR_STATE.STARTING);
  });

  it('explicit stop forbids automatic engineering restart', () => {
    const machine = createSupervisor();
    const stopped = finishStop(requestExplicitStop(machine));
    assert.equal(stopped.explicitStop, true);

    const governor = createRestartGovernor(); // full restart budget available
    const attempt = attemptAutomaticRestart(stopped, governor, 1_000_000);
    assert.equal(attempt.ok, false);
    assert.equal(attempt.reason, 'explicit_stop_fence');
    assert.equal(attempt.machine.state, SUPERVISOR_STATE.STOPPED, 'machine untouched');

    // The fence holds no matter how much time passes or budget remains.
    const later = attemptAutomaticRestart(attempt.machine, attempt.governor, 9_999_999_999);
    assert.equal(later.ok, false);
    assert.equal(later.reason, 'explicit_stop_fence');
  });

  it('paused and degraded outcomes are never marked successful reconciliation', () => {
    const machine = transition(createSupervisor(), SUPERVISOR_STATE.RECONCILING);

    const paused = recordReconciliationOutcome(machine, { outcome: SUPERVISOR_STATE.PAUSED, atMs: 10 * S });
    assert.equal(paused.record.successfulReconciliation, false);
    assert.equal(paused.machine.state, SUPERVISOR_STATE.PAUSED);

    const degraded = recordReconciliationOutcome(machine, { outcome: SUPERVISOR_STATE.DEGRADED, atMs: 11 * S });
    assert.equal(degraded.record.successfulReconciliation, false);
    assert.equal(degraded.machine.state, SUPERVISOR_STATE.DEGRADED);

    // Control: only a HEALTHY outcome counts as successful reconciliation.
    const healthy = recordReconciliationOutcome(machine, { outcome: SUPERVISOR_STATE.HEALTHY, atMs: 12 * S });
    assert.equal(healthy.record.successfulReconciliation, true);
    assert.equal(healthy.machine.state, SUPERVISOR_STATE.HEALTHY);
  });

  it('illegal transitions are rejected', () => {
    const machine = createSupervisor();
    assert.throws(() => transition(machine, SUPERVISOR_STATE.HEALTHY), InvalidTransitionError);
    assert.throws(() => transition(machine, SUPERVISOR_STATE.STOPPED), InvalidTransitionError);
  });
});

// ---------------------------------------------------------------------------
// Leader / fencing-generation model
// ---------------------------------------------------------------------------

describe('durable leader / fencing-generation state', () => {
  it('a stale leader generation cannot commit', () => {
    const seed = createLeadership();
    const gen1 = claimLeadership(seed, 'leader-a');
    assert.equal(gen1.fencingGeneration, 1);

    // leader-a commits fine at generation 1.
    assert.equal(
      commitUnderFence(gen1, { fencingGeneration: 1, actorId: 'leader-a', apply: () => 'committed' }).value,
      'committed',
    );

    // leader-b takes over: generation bumps to 2.
    const gen2 = claimLeadership(gen1, 'leader-b');
    assert.equal(gen2.fencingGeneration, 2);

    // leader-a's old generation can never commit again.
    assert.throws(
      () => commitUnderFence(gen2, { fencingGeneration: 1, actorId: 'leader-a', apply: () => 'stale-write' }),
      StaleFencingGenerationError,
    );

    // Nor can the new leader commit under a wrong generation, nor a stranger at all.
    assert.throws(
      () => commitUnderFence(gen2, { fencingGeneration: 3, actorId: 'leader-b', apply: () => 1 }),
      StaleFencingGenerationError,
    );
    assert.throws(
      () => commitUnderFence(gen2, { fencingGeneration: 2, actorId: 'leader-a', apply: () => 1 }),
      NotLeaderError,
    );
  });

  it('survives a durable JSON round-trip', () => {
    const gen2 = claimLeadership(claimLeadership(createLeadership(), 'leader-a'), 'leader-b');
    const restored = parseLeadership(serializeLeadership(gen2));
    assert.deepEqual(restored, gen2);
  });
});

// ---------------------------------------------------------------------------
// Restart budget: max 3 per rolling 30 minutes
// ---------------------------------------------------------------------------

describe('restart governor', () => {
  it('allows 3 restarts per rolling 30 minutes and refuses the 4th', () => {
    let governor = createRestartGovernor();
    const t0 = 1_000_000;
    for (let i = 0; i < 3; i += 1) {
      assert.equal(canRestart(governor, t0 + i * S), true);
      const attempt = attemptAutomaticRestart(
        { ...createSupervisor(), state: SUPERVISOR_STATE.STOPPED },
        governor,
        t0 + i * S,
      );
      assert.equal(attempt.ok, true);
      governor = attempt.governor;
    }
    const fourth = attemptAutomaticRestart(
      { ...createSupervisor(), state: SUPERVISOR_STATE.STOPPED },
      governor,
      t0 + 3 * S,
    );
    assert.equal(fourth.ok, false);
    assert.equal(fourth.reason, 'restart_budget_exhausted');

    // Old restarts age out of the rolling window.
    assert.equal(canRestart(governor, t0 + 30 * 60 * S + 10 * S), true);
  });
});

// ---------------------------------------------------------------------------
// Sweep runner: sweep_max_runtime 120s, ownership-safe cleanup on every
// return and exception
// ---------------------------------------------------------------------------

describe('sweep runner', () => {
  it('releases its lease on success and on exception (cleanup on every return)', async () => {
    const leaseStore = createLeaseStore();

    const ok = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-1',
      leaseStore,
      nowMsFn: () => 0,
      scheduler: null,
      work: async () => 'did-the-work',
    });
    assert.equal(ok.outcome, 'SUCCESS');
    assert.equal(leaseStore.owner(), null, 'lease released after success');

    const boom = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-1',
      leaseStore,
      nowMsFn: () => 0,
      scheduler: null,
      work: async () => {
        throw new Error('sweep blew up');
      },
    });
    assert.equal(boom.outcome, 'FAILED');
    assert.equal(boom.error.message, 'sweep blew up');
    assert.equal(leaseStore.owner(), null, 'lease released after exception');
  });

  it('cleanup is ownership-safe: a foreign token can neither release nor steal the lease', async () => {
    const leaseStore = createLeaseStore();
    assert.equal(leaseStore.acquire('runner-a').ok, true);
    const foreign = leaseStore.release('runner-b');
    assert.equal(foreign.ok, false);
    assert.equal(foreign.reason, 'foreign_owner');
    assert.equal(leaseStore.owner(), 'runner-a', 'lease still held by its owner');

    // A second runner gets refused and must not clobber the holder.
    const refused = await runSweep({
      kind: SWEEP_KIND.EXTRA,
      ownerToken: 'runner-b',
      leaseStore,
      nowMsFn: () => 0,
      scheduler: null,
      work: async () => 'never-runs',
    });
    assert.equal(refused.outcome, 'REFUSED');
    assert.equal(leaseStore.owner(), 'runner-a', 'refusal path performed no cleanup on the foreign lease');

    leaseStore.release('runner-a');
    assert.equal(leaseStore.owner(), null);
  });

  it('enforces sweep_max_runtime 120s', async () => {
    // Timer path: the 120s timer fires mid-sweep and the sweep is aborted.
    const fakeScheduler = {
      setTimeout(fn) {
        this.fn = fn;
        return 1;
      },
      clearTimeout() {},
    };
    const viaTimer = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-t',
      leaseStore: createLeaseStore(),
      nowMsFn: () => 0,
      scheduler: fakeScheduler,
      sweepMaxRuntimeMs: 120 * S,
      work: async ({ shouldAbort }) => {
        fakeScheduler.fn(); // 120s elapsed
        return { aborted: shouldAbort() };
      },
    });
    assert.equal(viaTimer.outcome, 'TIMEOUT');
    assert.ok(viaTimer.error instanceof SweepTimeoutError);

    // Fake-clock path: work that overruns 120s is recorded TIMEOUT too.
    let tick = 0;
    const viaClock = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-c',
      leaseStore: createLeaseStore(),
      nowMsFn: () => (tick++ === 0 ? 0 : 121 * S),
      scheduler: null,
      sweepMaxRuntimeMs: 120 * S,
      work: async () => 'slow',
    });
    assert.equal(viaClock.outcome, 'TIMEOUT');
    assert.equal(viaClock.runtimeMs, 121 * S);
  });

  // Regression (repair:supervisor-hang-1063 defect 1): the budget timer only
  // flipped a flag, so work that never settled wedged the sweep and its lease.
  it('terminates a work fn that never settles and frees the lease', { timeout: 3000 }, async () => {
    const leaseStore = createLeaseStore();
    const startedAtMs = Date.now();
    const hung = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-hung',
      leaseStore,
      sweepMaxRuntimeMs: 50,
      work: () => new Promise(() => {}), // never settles, never cooperates
    });
    const elapsedMs = Date.now() - startedAtMs;

    assert.equal(hung.outcome, 'TIMEOUT');
    assert.ok(hung.error instanceof SweepTimeoutError);
    assert.equal(leaseStore.owner(), null, 'lease released after a hung sweep');
    assert.ok(elapsedMs < 2500, `runSweep returned promptly (${elapsedMs}ms), not wedged`);

    // The consequence that mattered: a later sweep is not refused with lease_held.
    const later = await runSweep({
      kind: SWEEP_KIND.EXTRA,
      ownerToken: 'runner-hung',
      leaseStore,
      scheduler: null,
      nowMsFn: () => 0,
      work: async () => 'after-timeout',
    });
    assert.equal(later.outcome, 'SUCCESS');
    assert.equal(later.workResult, 'after-timeout');
  });

  // Regression (defect 1, late-result half): a result arriving after the breach
  // must never be accepted or recorded.
  it('discards a work result that arrives after the runtime breach', { timeout: 3000 }, async () => {
    const leaseStore = createLeaseStore();
    let releaseWork;
    const result = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-late',
      leaseStore,
      sweepMaxRuntimeMs: 40,
      work: () => new Promise((resolve) => { releaseWork = resolve; }),
    });

    assert.equal(result.outcome, 'TIMEOUT');
    assert.equal('workResult' in result, false, 'no late work result recorded');

    releaseWork('late-value');
    await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(result.outcome, 'TIMEOUT', 'late settlement cannot change the recorded outcome');
    assert.equal('workResult' in result, false, 'late value still not accepted');
    assert.equal(leaseStore.owner(), null);
  });

  // Regression (defect 2): a breached sweep that then threw was recorded FAILED,
  // losing the runtime-budget breach.
  it('classifies a breached sweep that then throws as TIMEOUT, not FAILED', async () => {
    const fakeScheduler = {
      setTimeout(fn) {
        this.fn = fn;
        return 1;
      },
      clearTimeout() {},
    };
    const viaTimer = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-tt',
      leaseStore: createLeaseStore(),
      nowMsFn: () => 0,
      scheduler: fakeScheduler,
      sweepMaxRuntimeMs: 120 * S,
      work: async () => {
        fakeScheduler.fn(); // 120s elapsed
        throw new Error('blew up after the deadline');
      },
    });
    assert.equal(viaTimer.outcome, 'TIMEOUT');
    assert.ok(viaTimer.error instanceof SweepTimeoutError);
    assert.equal(viaTimer.error.cause.message, 'blew up after the deadline', 'original error kept as cause');

    // Clock path: work throws after fake time has already overrun the budget.
    let tick = 0;
    const viaClock = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-tt-clock',
      leaseStore: createLeaseStore(),
      nowMsFn: () => (tick++ === 0 ? 0 : 121 * S),
      scheduler: null,
      sweepMaxRuntimeMs: 120 * S,
      work: async () => {
        throw new Error('late failure');
      },
    });
    assert.equal(viaClock.outcome, 'TIMEOUT');
    assert.ok(viaClock.error instanceof SweepTimeoutError);

    // Control: a throw well inside the budget is still FAILED.
    const inBudget = await runSweep({
      kind: SWEEP_KIND.SCHEDULED,
      ownerToken: 'runner-tt-control',
      leaseStore: createLeaseStore(),
      nowMsFn: () => 0,
      scheduler: null,
      work: async () => {
        throw new Error('simple failure');
      },
    });
    assert.equal(inBudget.outcome, 'FAILED');
    assert.equal(inBudget.error.message, 'simple failure');
  });
});

// ---------------------------------------------------------------------------
// Recorded sweep outcomes are a closed set (repair:supervisor-hang-1063 defect 3)
// ---------------------------------------------------------------------------

describe('applySweepResult outcome validation', () => {
  const base = { kind: SWEEP_KIND.SCHEDULED, startedAtMs: 0, finishedAtMs: S };

  it('rejects any outcome outside SUCCESS/FAILED/TIMEOUT', () => {
    const schedule = makeSweepSchedule({ anchorMs: 0 });
    for (const badOutcome of ['success', 'SUCCESS ', '', 'REFUSED', undefined, null]) {
      assert.throws(
        () => applySweepResult(schedule, { ...base, outcome: badOutcome }),
        TypeError,
        `outcome ${String(badOutcome)} must be rejected`,
      );
    }
    assert.equal(schedule.runs.length, 0, 'nothing recorded on rejection');
  });

  it('accepts exactly the three legal outcomes, successful only for SUCCESS', () => {
    let schedule = makeSweepSchedule({ anchorMs: 0 });
    schedule = applySweepResult(schedule, { ...base, outcome: 'SUCCESS' });
    schedule = applySweepResult(schedule, { ...base, kind: SWEEP_KIND.EXTRA, outcome: 'FAILED' });
    schedule = applySweepResult(schedule, { ...base, kind: SWEEP_KIND.EXTRA, outcome: 'TIMEOUT' });

    assert.deepEqual(
      schedule.runs.map((run) => [run.outcome, run.successful]),
      [
        ['SUCCESS', true],
        ['FAILED', false],
        ['TIMEOUT', false],
      ],
    );
  });
});

// ---------------------------------------------------------------------------
// Deterministic health observer (~60s tick, no LLM calls)
// ---------------------------------------------------------------------------

describe('health observer', () => {
  it('is deterministic over injected time and flags a suspect heartbeat after 180s', () => {
    assert.equal(observeHealth({ nowMs: 180 * S, lastHeartbeatAtMs: 0, dueInfo: null }).status, 'HEALTHY');
    const suspect = observeHealth({ nowMs: 180 * S + 1, lastHeartbeatAtMs: 0, dueInfo: null });
    assert.equal(suspect.status, 'DEGRADED');
    assert.deepEqual(suspect.reasons, ['heartbeat_suspect']);
    assert.equal(suspect.tickIntervalMs, 60 * S, '60s tick');
  });

  it('reports UNHEALTHY when the due+30s gate is tripped', () => {
    const snapshot = observeHealth({
      nowMs: 700 * S,
      lastHeartbeatAtMs: 700 * S,
      dueInfo: dueSweep(makeSweepSchedule({ anchorMs: 600 * S }), 700 * S),
    });
    assert.equal(snapshot.status, 'UNHEALTHY');
    assert.ok(snapshot.reasons.includes('sweep_overdue'));
  });
});

// ---------------------------------------------------------------------------
// Policy schema + explicit native-adapter UNKNOWN
// ---------------------------------------------------------------------------

describe('policy schema wise-elders.hybrid-supervisor-policy/v2', () => {
  const schemaPath = join(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    'wise-elders.hybrid-supervisor-policy',
    'v2',
  );

  it('carries the exact v2.4 field set with pinned values', () => {
    const schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
    assert.equal(schema.$id, 'wise-elders.hybrid-supervisor-policy/v2');

    const expected = {
      full_sweep_interval_seconds: 600,
      health_tick_seconds: 60,
      heartbeat_suspect_after_seconds: 180,
      max_concurrent_workflows: 50,
      max_agents_per_workflow: 10,
      max_total_agents: 500,
      require_independent_non_author_review: true,
      require_exact_head_checks: true,
      require_atomic_expected_head_merge_guard: true,
      standing_repository_merge_authorized: true,
      vercel_required: false,
      cloudflare_build_required: true,
      customer_remote_access_opt_in: true,
      explicit_stop_disables_automatic_engineering_restart: true,
      binding_status: 'TEMPLATE_NOT_BOUND',
      document_version: '2.4',
    };

    assert.deepEqual(Object.keys(schema.properties).sort(), Object.keys(expected).sort());
    assert.deepEqual(schema.required.slice().sort(), Object.keys(expected).sort());
    for (const [field, value] of Object.entries(expected)) {
      assert.deepEqual(schema.properties[field], { const: value }, `schema pins ${field}`);
      assert.deepEqual(POLICY[field], value, `module constant ${field} matches schema`);
    }
  });

  it('native-adapter binding stays an explicit UNKNOWN (later unit)', () => {
    assert.equal(NATIVE_ADAPTER_BINDING.status, 'UNKNOWN');
  });
});
