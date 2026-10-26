/**
 * W77S-MODES lane A: council sizes (light / medium / heavy).
 *
 * Proves the new single source of truth (contracts/modes.ts), the schema
 * seat and round rules, the three new state-machine paths including the
 * CRUX_REVIEW re-entry loop, the light panel selector, and the parallel
 * dispatch limits. The four older modes keep their own tests elsewhere.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  COUNCIL_SIZES,
  CONSENSUS_LEAD,
  CONSENSUS_MIN_SEATS,
  MAX_ADVISOR_ROUND,
  MODE_ROUND_POLICY,
  MODE_SEATS,
  SEAT_IDS,
  SESSION_MODES,
  allowedTransitions,
  canTransition,
  isCouncilSize,
  validateSessionSpec,
  type SessionMode,
  type SessionState,
} from '../src/contracts/index.js';
import { validSessionSpec } from '../src/contracts/fixtures/examples.js';
import {
  isOllamaProvider,
  parallelLimitFor,
} from '../src/providers/parallel.js';

// ------------------------------------------------------------ modes.ts

test('W77S: council sizes are light, medium and heavy', () => {
  assert.deepEqual([...COUNCIL_SIZES], ['light', 'medium', 'heavy']);
  assert.ok(isCouncilSize('light'));
  assert.ok(isCouncilSize('heavy'));
  assert.equal(isCouncilSize('full'), false);
  assert.equal(isCouncilSize('medium '), false);
  // The old four modes still exist and are untouched.
  assert.deepEqual(
    [...SESSION_MODES],
    ['full', 'selected', 'quick', 'consult', 'light', 'medium', 'heavy'],
  );
});

test('W77S: round policy matches the design for every size', () => {
  // Every council size seats the full roster; mode owns rounds and
  // concurrency only (Trevor, 2026-10-25).
  assert.equal(MODE_SEATS, SEAT_IDS.length);
  assert.deepEqual(MODE_ROUND_POLICY.light, {
    seats: SEAT_IDS.length,
    min_rounds: 2,
    max_rounds: 2,
    stop_from_round: null,
    max_provider_requests: 50,
    max_concurrent_calls: 3,
  });
  assert.deepEqual(MODE_ROUND_POLICY.medium, {
    seats: SEAT_IDS.length,
    min_rounds: 1,
    max_rounds: 4,
    stop_from_round: 1,
    max_provider_requests: 50,
    max_concurrent_calls: SEAT_IDS.length,
  });
  assert.deepEqual(MODE_ROUND_POLICY.heavy, {
    seats: SEAT_IDS.length,
    min_rounds: 3,
    max_rounds: 10,
    stop_from_round: 3,
    max_provider_requests: 100,
    max_concurrent_calls: SEAT_IDS.length,
  });
  assert.equal(CONSENSUS_MIN_SEATS, 7);
  assert.equal(CONSENSUS_LEAD, 1.5);
  assert.equal(MAX_ADVISOR_ROUND, 10);
});

test('W77S: every council size seats the same full roster', () => {
  const seats = COUNCIL_SIZES.map((mode) => MODE_ROUND_POLICY[mode].seats);
  assert.deepEqual(seats, [SEAT_IDS.length, SEAT_IDS.length, SEAT_IDS.length]);
  assert.deepEqual(new Set(seats), new Set([9]));
});

// -------------------------------------------------------- schema rules

function specWith(mode: string, seatCount: number): unknown {
  return {
    ...validSessionSpec,
    mode,
    seat_ids: validSessionSpec.seat_ids.slice(0, seatCount),
  };
}

test('W77S: light mode requires all nine seats, like every council size', () => {
  assert.equal(validateSessionSpec(specWith('light', 9)).ok, true);
  for (const count of [2, 3, 4, 8]) {
    const result = validateSessionSpec(specWith('light', count));
    assert.equal(result.ok, false, `light accepted ${count} seats`);
  }
});

test('W77S: medium and heavy require all nine seats', () => {
  for (const mode of ['medium', 'heavy']) {
    assert.equal(validateSessionSpec(specWith(mode, 9)).ok, true, mode);
    for (const count of [3, 8]) {
      assert.equal(validateSessionSpec(specWith(mode, count)).ok, false, `${mode} accepted ${count} seats`);
    }
  }
});

test('W77S: settings schema admits a heavy 100-request cap', async () => {
  const { DEFAULT_COUNCIL_SETTINGS, councilSettingsSchema } = await import(
    '../src/contracts/schemas.js'
  );
  assert.equal(
    councilSettingsSchema.safeParse({ ...DEFAULT_COUNCIL_SETTINGS, max_session_provider_requests: 100 })
      .success,
    true,
  );
  assert.equal(
    councilSettingsSchema.safeParse({ ...DEFAULT_COUNCIL_SETTINGS, max_session_provider_requests: 101 })
      .success,
    false,
  );
  // The default itself is untouched: the old CLI path stays on 50.
  assert.equal(DEFAULT_COUNCIL_SETTINGS.max_session_provider_requests, 50);
});

test('W77S: advisor card rounds run 1..10, ratification stays literal 3', async () => {
  const { z } = await import('zod');
  const { advisorCardAuthorSchema, ratificationCardAuthorSchema } = await import(
    '../src/contracts/schemas.js'
  );
  const advisorRound = z.object({ round: advisorCardAuthorSchema.shape.round });
  for (let round = 1; round <= MAX_ADVISOR_ROUND; round += 1) {
    assert.equal(advisorRound.safeParse({ round }).success, true, `round ${round}`);
  }
  for (const round of [0, 11, 1.5]) {
    assert.equal(advisorRound.safeParse({ round }).success, false, `round ${round}`);
  }
  const ratificationRound = z.object({ round: ratificationCardAuthorSchema.shape.round });
  assert.equal(ratificationRound.safeParse({ round: 3 }).success, true);
  assert.equal(ratificationRound.safeParse({ round: 4 }).success, false);
});

// ------------------------------------------------------ state machine

/** Forward path only: the table always also offers the control states. */
function forward(mode: SessionMode, from: SessionState): SessionState[] {
  const control = new Set<SessionState>([
    'PAUSE_REQUESTED',
    'CANCEL_REQUESTED',
    'BLOCKED',
    'FAILED',
  ]);
  return allowedTransitions(mode, from).filter((s) => !control.has(s));
}

test('W77S: light ends after round 2 with no ratification phase', () => {
  assert.deepEqual(forward('light', 'PREPARING'), ['ROUND_1']);
  assert.deepEqual(forward('light', 'ROUND_1'), ['CRUX_REVIEW']);
  assert.deepEqual(forward('light', 'CRUX_REVIEW'), ['ROUND_2']);
  assert.deepEqual(forward('light', 'ROUND_2'), ['DRAFT_RESOLUTION']);
  assert.deepEqual(forward('light', 'DRAFT_RESOLUTION'), ['VERIFYING']);
  assert.deepEqual(forward('light', 'VERIFYING'), ['COMPLETED']);
  assert.equal(canTransition('light', 'DRAFT_RESOLUTION', 'ROUND_3'), false);
  assert.equal(canTransition('light', 'ROUND_2', 'CRUX_REVIEW'), false);
});

test('W77S: medium and heavy allow a stop after round 1 and the challenge re-entry loop', () => {
  for (const mode of ['medium', 'heavy'] as const) {
    assert.deepEqual(forward(mode, 'PREPARING'), ['ROUND_1']);
    assert.deepEqual(forward(mode, 'ROUND_1'), ['CRUX_REVIEW', 'DRAFT_RESOLUTION']);
    assert.deepEqual(forward(mode, 'CRUX_REVIEW'), ['ROUND_2']);
    // The loop: another challenge pass, or done.
    assert.deepEqual(forward(mode, 'ROUND_2'), ['CRUX_REVIEW', 'DRAFT_RESOLUTION']);
    assert.deepEqual(forward(mode, 'DRAFT_RESOLUTION'), ['VERIFYING']);
    assert.equal(canTransition(mode, 'ROUND_2', 'CRUX_REVIEW'), true);
    assert.equal(canTransition(mode, 'CRUX_REVIEW', 'ROUND_2'), true);
    // No separate ratification pass for the council sizes.
    assert.equal(canTransition(mode, 'DRAFT_RESOLUTION', 'ROUND_3'), false);
  }
});

test('W77S: the four old modes keep their paths', () => {
  assert.deepEqual(forward('full', 'CRUX_REVIEW'), ['ROUND_2']);
  assert.deepEqual(forward('full', 'DRAFT_RESOLUTION'), ['ROUND_3']);
  assert.deepEqual(forward('quick', 'DRAFT_RESOLUTION'), ['ROUND_3', 'VERIFYING']);
  assert.deepEqual(forward('selected', 'ROUND_2'), ['DRAFT_RESOLUTION']);
  assert.deepEqual(forward('consult', 'PREPARING'), ['CONSULTING']);
});

// --------------------------------------------------- parallel limits

test('W77S: ollama plans cap how many seats run at once', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '20', panelSize: 9 }),
    { ok: true, limit: 3 },
  );
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '100', panelSize: 12 }),
    { ok: true, limit: 10 },
  );
  // Never more than the panel actually has.
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama-cloud', ollamaPlan: '100', panelSize: 9 }),
    { ok: true, limit: 9 },
  );
});

test('W77S: an unknown ollama plan is a typed refusal, never a guess', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: null, panelSize: 9 }),
    { ok: false, code: 'OLLAMA_PLAN_REQUIRED' },
  );
});

test('W77S: every other provider runs the whole panel at once', () => {
  for (const providerSlug of ['openrouter-configured', 'agnes', 'deepseek', 'harness-route']) {
    assert.deepEqual(
      parallelLimitFor({ providerSlug, ollamaPlan: null, panelSize: 9 }),
      { ok: true, limit: 9 },
      providerSlug,
    );
  }
});

test('W77S: light dispatches three at a time even when the route could run nine', () => {
  // Light seats all nine but runs them in waves of three.
  assert.deepEqual(
    parallelLimitFor({
      providerSlug: 'openrouter-configured',
      ollamaPlan: null,
      panelSize: 9,
      waveWidth: MODE_ROUND_POLICY.light.max_concurrent_calls,
    }),
    { ok: true, limit: 3 },
  );
  // Medium/heavy add no cap of their own: the whole roster goes at once.
  for (const mode of ['medium', 'heavy'] as const) {
    assert.deepEqual(
      parallelLimitFor({
        providerSlug: 'openrouter-configured',
        ollamaPlan: null,
        panelSize: 9,
        waveWidth: MODE_ROUND_POLICY[mode].max_concurrent_calls,
      }),
      { ok: true, limit: 9 },
      mode,
    );
  }
});

test('W77S: isOllamaProvider matches the slug and its variants only', () => {
  assert.equal(isOllamaProvider('ollama'), true);
  assert.equal(isOllamaProvider('ollama-cloud'), true);
  assert.equal(isOllamaProvider('openrouter-configured'), false);
  assert.equal(isOllamaProvider('not-ollama'), false);
});
