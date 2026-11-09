/**
 * W77S auto-mode wiring: the convene flow resolves the sitting's mode
 * through the ONE selector before deliberation.
 *
 * Proves the product rule at this seam only:
 *   - an explicit client mode passes through as `explicitMode` and wins
 *     verbatim, even when the question reads heavier or lighter;
 *   - with no client mode the question's complexity decides (source
 *     `auto`), and the selector's answer is what deliberation receives;
 *   - an explicit value that is not a council size is refused by name,
 *     never silently replaced by an auto pick;
 *   - the chosen mode, its source and the reason land on the session
 *     record AND the convene output.
 *
 * What a mode DOES (rounds, concurrency, caps) is contracts/modes.ts and
 * is not asserted here.
 *
 * Run standalone: node --import tsx --test src/flow/convene-flow-mode.test.ts
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import type { StoredSession } from '../cli/host-ports.js';
import {
  conveneFlow,
  type ConveneFlowDeps,
  type DeliberationResult,
  type ModeSelection,
} from './convene-flow.js';

const DECISION = 'Should the company open a second office in Austin this year?';
const OPTIONS = ['open the Austin office in Q3', 'wait until next year'];

/** Empty permitted-context root: this check reads mode wiring, not memory. */
function emptyContextRoot(): string {
  return mkdtempSync(join(tmpdir(), 'cwe1062-mode-'));
}

/** A session row is only carried here, never rendered: shape is enough. */
const SESSION = { sample: true } as unknown as StoredSession;

function harness(): {
  deps: ConveneFlowDeps;
  seen: ModeSelection[];
  result: DeliberationResult;
} {
  const seen: ModeSelection[] = [];
  const result: DeliberationResult = {
    sessionId: 'sess-mode-1',
    session: SESSION,
    clientName: 'Example Client Co. (synthetic fixture)',
    modelUsed: 'fixture-model (synthetic fixture)',
    questionCount: 1,
    cards: [],
    verdict: { consensus: 'Synthetic consensus.', action_steps: [] },
    chamberUrl: null,
  };
  const deps: ConveneFlowDeps = {
    deliberate: async ({ mode }) => {
      seen.push(mode);
      return result;
    },
    closePort: {
      lastEventAt: () => null,
      readMarker: () => ({ soft_close_sent_at: null, closed_at: null, close_reason: null }),
      recordSoftClose: () => {},
      recordClientInteraction: () => {},
      markClosed: () => {},
      sessionRecord: () => null,
    },
  };
  return { deps, seen, result };
}

function run(mode?: string) {
  const h = harness();
  return conveneFlow(
    {
      door: 'openclaw',
      contextRoot: emptyContextRoot(),
      decision: DECISION,
      options: OPTIONS,
      ...(mode === undefined ? {} : { mode }),
    },
    h.deps,
  ).then((out) => ({ out, seen: h.seen }));
}

test('W77S: an explicit client mode wins verbatim, source client', async () => {
  const { out, seen } = await run('light');
  assert.equal(out.modeSelection.mode, 'light');
  assert.equal(out.modeSelection.source, 'client');
  assert.ok(out.modeSelection.reason.length > 0, 'the client must see WHY');
  // Deliberation received the SAME selection the output carries.
  assert.deepEqual(seen, [out.modeSelection]);
  // It landed on the session record too.
  assert.deepEqual(out.session.mode_selection, out.modeSelection);
});

test('W77S: the client mode beats the automatic pick in both directions', async () => {
  // A trivially small question forced to heavy, a big one forced to light.
  const small = await run('heavy');
  assert.equal(small.out.modeSelection.mode, 'heavy');
  assert.equal(small.out.modeSelection.source, 'client');

  const big = await run('light');
  assert.equal(big.out.modeSelection.mode, 'light');
  assert.equal(big.out.modeSelection.source, 'client');
});

test('W77S: with no client mode the question complexity decides', async () => {
  const { out, seen } = await run();
  assert.equal(out.modeSelection.source, 'auto');
  assert.ok(
    ['light', 'medium', 'heavy'].includes(out.modeSelection.mode),
    `auto picked an unknown mode: ${out.modeSelection.mode}`,
  );
  assert.ok(out.modeSelection.reason.length > 0, 'the auto pick must state WHY');
  assert.deepEqual(seen, [out.modeSelection]);
  assert.deepEqual(out.session.mode_selection, out.modeSelection);
});

test('W77S: an explicit value that is not a council size is refused by name', async () => {
  await assert.rejects(run('turbo'), /INVALID_MODE/);
});
