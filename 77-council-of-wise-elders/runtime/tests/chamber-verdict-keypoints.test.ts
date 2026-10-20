/**
 * The approved chamber look (a8e502990): a finished council shows its verdict only as the
 * table-panel line and compact Key Points, with no "why" box above the room, and no internal
 * id (con-N, fact-N, unk-N, asm-N, ev-N, Crux-N) ever reaches the page. Driven by the first
 * real live council, saved read-only as tests/fixtures/chamber/live-wait-session.json.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-verdict-keypoints.test.ts
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const chamberDir = join(here, '..', 'public', 'chamber');

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

const fixtureText = readFileSync(join(here, 'fixtures', 'chamber', 'live-wait-session.json'), 'utf8');
const fx: Any = JSON.parse(fixtureText);

function load(files: string[]): Any {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  for (const f of files) runInNewContext(readFileSync(join(chamberDir, f), 'utf8'), sandbox);
  return sandbox.councilChamber;
}

function sessionView(): Any {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const m = ns.state.create(fx.readback.session);
  for (const frame of fx.events) ns.state.apply(m, frame);
  ns.state.applyRecord(m, fx.readback.session);
  return JSON.parse(JSON.stringify(ns.state.view(m, Date.parse('2026-10-20T00:30:00Z'))));
}

const INTERNAL_ID = /\b(?:(?:con|fact|unk|asm|ev)-\d+|Crux-\d+)\b/;

function strings(v: unknown, out: string[] = []): string[] {
  if (typeof v === 'string') out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => strings(x, out));
  else if (v && typeof v === 'object') Object.values(v).forEach((x) => strings(x, out));
  return out;
}

test('fixture holds the real session and no keys, tokens or home paths', () => {
  assert.equal(fx.readback.session.state.state, 'COMPLETED');
  assert.equal(fx.readback.session.cards.length, 27);
  assert.equal(fx.readback.session.verdict.label, 'WAIT');
  assert.doesNotMatch(fixtureText, /\/Users\/|\/home\/|sk-[A-Za-z0-9]{8,}|Bearer |BEGIN [A-Z ]*PRIVATE/);
  assert.doesNotMatch(fixtureText, /"[a-zA-Z_]*(api_?key|token|secret|password)[a-zA-Z_]*"\s*:\s*"[^"]/i);
});

test('a finished council says its verdict in one line, with no why box and no extra Key Points body', () => {
  const view = sessionView();
  assert.equal(view.verdict.why, undefined);
  assert.match(view.round.explain, /^Verdict: Wait\. Recommended: Option B: /);
  for (const k of view.keyPoints) assert.equal(k.items, undefined);
  const last = view.keyPoints[view.keyPoints.length - 1];
  assert.equal(last.label, 'VERDICT: WAIT');
  assert.match(last.detail, /^Option B: /);
});

test('the decision header and Key Points panel have no why box or body list', () => {
  for (const f of ['chamber-decision.js', 'chamber-decision.css', 'chamber-keypoints.js', 'chamber-keypoints.css']) {
    assert.doesNotMatch(readFileSync(join(chamberDir, f), 'utf8'), /ch-dec-why|ch-kp-point|whyModel/, f);
  }
});

test('nothing the page shows from a real council contains an internal id', () => {
  assert.doesNotMatch(strings(sessionView()).join('\n'), INTERNAL_ID);
});

test('internal ids in elder text become plain words or are dropped', () => {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const m = ns.state.create({ state: { state: 'ROUND_1_RUNNING' }, cards: [
    { seat_id: 'simon-sinek', round: 1, card_kind: 'advisor', preferred_option_id: 'B',
      decisive_arguments: ['Count the cost: con-1 bounds spend, and with unk-1 unmeasured (asm-1) the pilot is the test (ev-1, ev-2). Crux-2 stays open.'] },
    { seat_id: 'oprah-winfrey', round: 1, card_kind: 'advisor', decisive_arguments: ['Pilot retention is not yet measured (brief unknown unk-1).'] },
  ] });
  const v = JSON.parse(JSON.stringify(ns.state.view(m, 0)));
  const lines = strings(v.session ? v.session.seats : v).join('\n');
  assert.doesNotMatch(lines, INTERNAL_ID);
  assert.match(lines, /Count the cost: the brief's limit bounds spend, and with the brief's open question unmeasured the pilot is the test\. Fault line 2 stays open\./);
  assert.match(lines, /Pilot retention is not yet measured\./);
});
