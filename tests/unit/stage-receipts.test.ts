/**
 * stage-receipts.test.ts — focused regression checks for the six-stage
 * distribution receipts (UNIT R2 CC-RECEIPTS). Small fixtures, one concern
 * per test:
 *
 *   (a) a completed build never turns unknown runtime selection green;
 *   (b) every stage row carries its own evidence pointer kind, and a
 *       verdict with no pointer fails closed to UNKNOWN;
 *   (c) claim-gate style consumers get BEHIND/UNKNOWN per stage on their
 *       own axis — one stage's verdict never drags another stage's;
 *   (d) resolver failure is BLOCKED, never a pass.
 *
 * Pure logic — no DB, no network, no fixtures beyond the literals below.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  STAGE_ORDER,
  STAGE_EVIDENCE,
  buildStageRows,
  buildLedgerRow,
  rollUpStatus,
  projectStageRows,
  type StageMeasurements,
} from '../../src/lib/stage-receipts';

test('(a) completed build with unmeasured selection/adoption is UNKNOWN overall, never green', () => {
  const buildComplete: StageMeasurements = {
    source_merged: { ok: true, evidence: 'e3a1c0ffee' },
    package_built: { ok: true, evidence: 'sha256:b10bb16b' },
    target_installed: { ok: true, evidence: '/opt/skills/thing' },
    // agent_selected / runtime_adopted / live_outcome deliberately unmeasured
  };
  const rows = buildStageRows(buildComplete);
  const byStage = Object.fromEntries(rows.map((r) => [r.stage, r]));

  assert.equal(byStage.agent_selected.status, 'UNKNOWN');
  assert.equal(byStage.runtime_adopted.status, 'UNKNOWN');
  assert.equal(byStage.live_outcome.status, 'UNKNOWN');

  const overall = rollUpStatus(rows);
  assert.notEqual(overall, 'CURRENT', 'a completed build must not turn unknown runtime selection green');
  assert.equal(overall, 'UNKNOWN');
});

test('(b) evidence pointers: one kind per stage, and verdicts without a pointer fail closed', () => {
  assert.deepEqual(
    STAGE_ORDER.map((s) => STAGE_EVIDENCE[s]),
    ['commit_sha', 'package_hash', 'install_path', 'resolver_path', 'process_ref', 'live_check']
  );

  const rows = buildStageRows({
    source_merged: { ok: true, evidence: null }, // pass claimed, no commit sha
    package_built: { ok: true, evidence: 'sha256:deadbeef' },
    target_installed: { ok: false, evidence: null }, // divergence claimed, no pointer
  });
  const byStage = Object.fromEntries(rows.map((r) => [r.stage, r]));

  assert.equal(byStage.source_merged.status, 'UNKNOWN', 'CURRENT without its evidence pointer is UNKNOWN');
  assert.equal(byStage.source_merged.evidence, null);
  assert.equal(byStage.package_built.status, 'CURRENT');
  assert.equal(byStage.package_built.evidence, 'sha256:deadbeef');
  assert.equal(byStage.target_installed.status, 'UNKNOWN', 'BEHIND without its evidence pointer is UNKNOWN');

  // every row names its own evidence kind
  for (const r of rows) assert.equal(r.evidence_type, STAGE_EVIDENCE[r.stage]);
});

test('(c) consumer rows say BEHIND/UNKNOWN per stage without conflating axes', () => {
  const mixed: StageMeasurements = {
    source_merged: { ok: false, evidence: 'oldsha1234', note: 'onboarding commit behind' },
    package_built: { ok: true, evidence: 'sha256:feedface' },
    target_installed: { ok: true, evidence: '~/.claude/skills/thing' },
    agent_selected: null, // unmeasured
    runtime_adopted: { ok: true, evidence: 'pid:4242' },
    live_outcome: { ok: true, evidence: 'http://localhost:18789/api/health' },
  };
  const rows = buildStageRows(mixed);
  const consumer = projectStageRows('rescue-example', rows, '2026-10-24T00:00:00Z');

  assert.equal(consumer.length, 6, 'one row per (slug, stage)');
  const byStage = Object.fromEntries(consumer.map((r) => [r.stage, r]));
  assert.equal(byStage.source_merged.status, 'BEHIND');
  assert.equal(byStage.agent_selected.status, 'UNKNOWN');
  // axes stay independent: a BEHIND on one axis does not taint its neighbours
  assert.equal(byStage.package_built.status, 'CURRENT');
  assert.equal(byStage.runtime_adopted.status, 'CURRENT');
  assert.equal(byStage.live_outcome.status, 'CURRENT');
  assert.equal(byStage.source_merged.evidence, 'oldsha1234');
  assert.equal(byStage.agent_selected.evidence, null);

  assert.equal(rollUpStatus(rows), 'BEHIND');
});

test('(d) resolver failure is BLOCKED, never a pass', () => {
  const rows = buildStageRows({
    source_merged: { ok: true, evidence: 'abc' },
    package_built: { ok: true, evidence: 'sha256:abc' },
    target_installed: { ok: true, evidence: '/x' },
    agent_selected: { blocked: true, note: 'resolver refused' },
    runtime_adopted: { ok: true, evidence: 'pid:1' },
    live_outcome: { ok: true, evidence: 'live' },
  });
  const byStage = Object.fromEntries(rows.map((r) => [r.stage, r]));

  assert.equal(byStage.agent_selected.status, 'BLOCKED');
  assert.equal(byStage.agent_selected.evidence, null);
  assert.notEqual(rollUpStatus(rows), 'CURRENT');
  assert.equal(rollUpStatus(rows), 'BLOCKED');
});

test('ledger row keeps the claim-gate shape and derives status fail-closed', () => {
  const row = buildLedgerRow('rescue-example', {
    source_merged: { ok: true, evidence: 'abc' },
  }, '2026-10-24T00:00:00Z');

  assert.equal(row.slug, 'rescue-example');
  assert.equal(row.measured_utc, '2026-10-24T00:00:00Z');
  assert.equal(row.status, 'UNKNOWN', 'five unmeasured stages cannot roll up green');
  assert.equal(Object.keys(row.stages).length, 6);
  assert.ok(row.note.includes('runtime_adopted=UNKNOWN'), 'roll-up note names the axes, not one conflated verdict');

  const unreachable = buildLedgerRow('rescue-other', {
    source_merged: { unreachable: true },
    package_built: { ok: true, evidence: 'sha256:x' },
    target_installed: { ok: false, evidence: '/old/path', note: 'stale install' },
  });
  assert.equal(unreachable.status, 'UNREACHABLE', 'worst status wins');
});
