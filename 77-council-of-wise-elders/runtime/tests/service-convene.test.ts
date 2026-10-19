/**
 * W28 service-wiring end to end: the real composition root and the real
 * HTTP listener on an ephemeral loopback port, with a deterministic
 * fixture transport injected through the composition options.
 *
 * Runner:
 *   node --import tsx --test tests/service-convene.test.ts
 *
 * Proven here:
 * - GET /api/council/routes lists the configured routes;
 * - with no operator budget approval POST /api/council/convene is a 503
 *   COMPOSITION_NOT_READY that creates no session;
 * - writing a matching approval file lets the very next convene succeed
 *   with no service restart: 202, then an SSE client on events_path
 *   receives the session's state transitions, cards and verdict, in
 *   order, from council_events;
 * - a route without an approved budget is refused per session;
 * - a malformed body is a typed 422, and the endpoint sits behind the
 *   same fence as admissions.
 *
 * No provider request, no credential, no network beyond 127.0.0.1 and no
 * live model: every card comes from the fixture transport.
 */

import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
  entrySha256,
  routeBudgetApprovalsPath,
  type RouteBudgetEntry,
} from '../src/budgets/route-budget.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import {
  startCouncilService,
  type StartedCouncilService,
} from '../src/service/composition.js';

const TENANT = 'tenant-w28';
const COMPANY = 'company-w28';

interface Fixture {
  root: string;
  dataDir: string;
  configPath: string;
  service: StartedCouncilService;
  origin: string;
}

function entry(routeId: string, model: string | null): RouteBudgetEntry {
  return {
    route_id: routeId,
    model,
    context_window_tokens: 200_000,
    max_output_tokens: 8_000,
    measured_min_bytes_per_token: 3.1,
    safety_factor: 0.8,
    response_schema_bytes: 10_159,
    measured_at: '2026-10-19T12:00:00.000Z',
    measurement_basis: 'fixture',
  };
}

const ENTRIES = [entry('claude-nine-configured', null), entry('claude-configured', 'sonnet')];

function approvalFor(e: RouteBudgetEntry): Record<string, unknown> {
  return {
    route_id: e.route_id,
    model: e.model,
    entry_sha256: entrySha256(e),
    approved_by: 'fixture-operator',
    approved_at: '2026-10-19T12:00:00.000Z',
  };
}

async function startFixture(): Promise<Fixture> {
  const root = mkdtempSync(join(tmpdir(), 'w28-convene-'));
  const dataDir = join(root, 'data');
  const home = join(root, 'home');
  for (const dir of ['.claude-nine', '.claude', '.openclaw', join('.local', 'bin')]) {
    mkdirSync(join(home, dir), { recursive: true });
  }
  for (const name of ['claude-nine', 'claude']) {
    const exe = join(home, '.local', 'bin', name);
    writeFileSync(exe, '#!/bin/sh\nexit 0\n', 'utf8');
    chmodSync(exe, 0o755);
  }
  writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify({ models: { providers: {} } }), 'utf8');
  const configPath = join(root, 'route-budgets.json');
  writeFileSync(
    configPath,
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: ENTRIES }),
    'utf8',
  );
  const service = await startCouncilService({
    tenantId: TENANT,
    companyId: COMPANY,
    dataDir,
    ports: [0],
    routeHomeDir: home,
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    routeBudgetConfigPath: configPath,
    // The fixture route transport: deterministic, spends nothing.
    resolveTransport: () => new DeterministicFixtureTransport(),
    workerPollIntervalMs: 20,
    handleSignals: false,
  });
  assert.equal(service.outcome.outcome, 'started');
  assert.ok(service.origin);
  return { root, dataDir, configPath, service, origin: service.origin as string };
}

async function stopFixture(fixture: Fixture): Promise<void> {
  await fixture.service.stop();
  rmSync(fixture.root, { recursive: true, force: true });
}

function convene(origin: string, body: unknown): Promise<Response> {
  return fetch(`${origin}/api/council/convene`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

interface SseFrame {
  sequence: number;
  type: string;
  from_state: string | null;
  to_state: string | null;
}

/** Read the live SSE stream until the session reaches `untilState`. */
async function readEvents(
  url: string,
  untilState: string,
  timeoutMs = 60_000,
): Promise<SseFrame[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const frames: SseFrame[] = [];
  try {
    const response = await fetch(url, { signal: controller.signal });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type') ?? '', /text\/event-stream/);
    const reader = response.body?.getReader();
    assert.ok(reader);
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split: number;
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const data = block
          .split('\n')
          .find((line) => line.startsWith('data: '))
          ?.slice('data: '.length);
        if (!data) continue;
        const frame = JSON.parse(data) as SseFrame;
        frames.push(frame);
        if (frame.to_state === untilState) {
          controller.abort();
          return frames;
        }
      }
    }
    return frames;
  } catch (error) {
    if (controller.signal.aborted && frames.some((f) => f.to_state === untilState)) return frames;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

test('GET /api/council/routes lists the configured routes through the real listener', async () => {
  const fixture = await startFixture();
  try {
    const response = await fetch(`${fixture.origin}/api/council/routes`);
    assert.equal(response.status, 200);
    const body = (await response.json()) as {
      routes: Array<{ route_id: string; composable: boolean; default_for: string[] }>;
      harness_defaults: Record<string, { route_id: string; model: string }>;
      budgets: Array<{ route_id: string; model: string | null; state: string }>;
    };
    assert.deepEqual(
      body.routes.map((r) => r.route_id).sort(),
      ['claude-configured', 'claude-nine-configured'],
    );
    assert.ok(body.routes.every((r) => r.composable));
    assert.deepEqual(body.harness_defaults['claude-nine'], {
      route_id: 'claude-nine-configured',
      model: 'harness_default',
    });
    assert.deepEqual(
      body.budgets.map((b) => [b.route_id, b.model, b.state]),
      [
        ['claude-nine-configured', null, 'awaiting_approval'],
        ['claude-configured', 'sonnet', 'awaiting_approval'],
      ],
    );
  } finally {
    await stopFixture(fixture);
  }
});

test('convene is refused 503 until the operator approves, then runs with no restart', async () => {
  const fixture = await startFixture();
  try {
    const db = fixture.service.composition.backend.repositories;
    // 1. No approval: refused before any session or grant exists.
    const refused = await convene(fixture.origin, { sample: true, route_id: 'claude-nine-configured' });
    assert.equal(refused.status, 503);
    const refusedBody = (await refused.json()) as {
      code: string;
      detail: { unbound: string[]; checks: Array<{ name: string; detail: string }> };
      recovery: string;
    };
    assert.equal(refusedBody.code, 'COMPOSITION_NOT_READY');
    assert.deepEqual(refusedBody.detail.unbound, ['route_budget']);
    assert.match(refusedBody.detail.checks[0].detail, /awaiting operator approval/);
    assert.match(refusedBody.detail.checks[0].detail, /3\.1 min bytes per token/);
    assert.ok(refusedBody.recovery.length > 0);
    assert.equal(
      db.listSessions(fixture.service.composition.backend.ownerEnvelope).length,
      0,
      'a refused convene creates no session',
    );

    // 2. The operator approval is one file in the service data dir.
    writeFileSync(
      routeBudgetApprovalsPath(fixture.dataDir),
      JSON.stringify([approvalFor(ENTRIES[0])]),
      'utf8',
    );

    // 3. The very next convene succeeds. Nothing restarted.
    const accepted = await convene(fixture.origin, {
      sample: true,
      route_id: 'claude-nine-configured',
      requested_by: 'fixture-client',
    });
    assert.equal(accepted.status, 202);
    const body = (await accepted.json()) as {
      session_id: string;
      sample: boolean;
      route_id: string;
      model_label: string;
      selection_source: string;
      grant_id: string;
      session_path: string;
      events_path: string;
    };
    assert.equal(body.sample, true);
    assert.equal(body.route_id, 'claude-nine-configured');
    assert.equal(body.selection_source, 'explicit');
    assert.equal(body.session_path, `/council/${body.session_id}`);
    assert.equal(body.events_path, `/api/council/sessions/${body.session_id}/events`);

    // 4. The SSE client sees the run, in order, from council_events.
    const frames = await readEvents(`${fixture.origin}${body.events_path}`, 'COMPLETED');
    assert.deepEqual(
      frames.map((f) => f.sequence),
      frames.map((_, i) => i + 1),
      'sequences are contiguous from 1',
    );
    assert.equal(frames[0].type, 'session_created');
    // Per-seat job events repeat the round state; collapse the repeats.
    const states = frames
      .filter((f) => f.type === 'session_state_changed')
      .map((f) => f.to_state)
      .filter((state, i, all) => state !== all[i - 1]);
    assert.deepEqual(states, [
      'READY',
      'QUEUED',
      'PREPARING',
      'ROUND_1',
      'CRUX_REVIEW',
      'ROUND_2',
      'DRAFT_RESOLUTION',
      'ROUND_3',
      'VERIFYING',
      'COMPLETED',
    ]);
    const firstCard = frames.findIndex((f) => f.type === 'card_accepted');
    const verdict = frames.findIndex((f) => f.type === 'verdict_validated');
    const completed = frames.findIndex((f) => f.to_state === 'COMPLETED');
    assert.ok(firstCard > 0, 'cards were journaled');
    assert.ok(verdict > firstCard, 'the verdict follows the cards');
    assert.ok(completed > verdict, 'the session completes after its verdict');

    // 5. The session route and the audit record agree with the run.
    const session = (await (await fetch(`${fixture.origin}${body.session_path}`)).json()) as {
      session: { state: { state: string }; sample: boolean };
    };
    assert.equal(session.session.state.state, 'COMPLETED');
    assert.equal(session.session.sample, true);
    const audit = readFileSync(join(fixture.dataDir, 'convening-audit.jsonl'), 'utf8')
      .trim()
      .split('\n');
    assert.equal(audit.length, 1, 'exactly one audit line per run');
    const line = JSON.parse(audit[0]) as Record<string, unknown>;
    assert.equal(line.session_id, body.session_id);
    assert.equal(line.requested_by, 'fixture-client');
    assert.match(String(line.approval_basis), /convening_is_approval/);
  } finally {
    await stopFixture(fixture);
  }
});

test('a route whose budget is not approved is refused per session, even when another is approved', async () => {
  const fixture = await startFixture();
  try {
    writeFileSync(
      routeBudgetApprovalsPath(fixture.dataDir),
      JSON.stringify([approvalFor(ENTRIES[0])]),
      'utf8',
    );
    const backend = fixture.service.composition.backend;
    const refused = await convene(fixture.origin, {
      sample: true,
      route_id: 'claude-configured',
      model: 'sonnet',
    });
    assert.equal(refused.status, 503);
    const body = (await refused.json()) as {
      code: string;
      detail: { route_id: string; route_budget_state: string; summary: string };
    };
    assert.equal(body.code, 'COMPOSITION_NOT_READY');
    assert.equal(body.detail.route_id, 'claude-configured');
    assert.equal(body.detail.route_budget_state, 'awaiting_approval');
    assert.match(body.detail.summary, /awaiting operator approval/);
    assert.equal(backend.repositories.listSessions(backend.ownerEnvelope).length, 0);
  } finally {
    await stopFixture(fixture);
  }
});

test('a malformed convene body is a typed 422 and creates nothing', async () => {
  const fixture = await startFixture();
  try {
    for (const raw of ['{"sample":"yes"}', '{"sample":true,"harness":"gpt"}', '{broken', '[]']) {
      const response = await convene(fixture.origin, raw);
      assert.equal(response.status, 422, raw);
      const body = (await response.json()) as { code: string };
      assert.match(body.code, /^CONVENE_BODY_/);
    }
    // An unknown route is the driver's typed refusal, not a crash.
    writeFileSync(
      routeBudgetApprovalsPath(fixture.dataDir),
      JSON.stringify([approvalFor(ENTRIES[0])]),
      'utf8',
    );
    const unknown = await convene(fixture.origin, { sample: true, route_id: 'nope-configured' });
    assert.equal(unknown.status, 409);
    assert.equal(((await unknown.json()) as { code: string }).code, 'ROUTE_NOT_CONFIGURED');
    const noChoice = await convene(fixture.origin, { sample: true });
    assert.equal(noChoice.status, 422);
    assert.equal(((await noChoice.json()) as { code: string }).code, 'ROUTE_CHOICE_REQUIRED');
    const backend = fixture.service.composition.backend;
    assert.equal(backend.repositories.listSessions(backend.ownerEnvelope).length, 0);
    assert.equal(existsSync(join(fixture.dataDir, 'convening-audit.jsonl')), false);
  } finally {
    await stopFixture(fixture);
  }
});

test('both endpoints sit behind the admission fence: a draining service convenes nothing', async () => {
  const fixture = await startFixture();
  try {
    writeFileSync(
      routeBudgetApprovalsPath(fixture.dataDir),
      JSON.stringify([approvalFor(ENTRIES[0])]),
      'utf8',
    );
    fixture.service.composition.door.drain();
    const fenced = await convene(fixture.origin, { sample: true, route_id: 'claude-nine-configured' });
    assert.equal(fenced.status, 503);
    assert.equal(((await fenced.json()) as { code: string }).code, 'SERVICE_DRAINING');
    const backend = fixture.service.composition.backend;
    assert.equal(backend.repositories.listSessions(backend.ownerEnvelope).length, 0);
    // The admission route answers through the very same fence.
    const admission = await fetch(`${fixture.origin}/api/council/admissions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ session_id: 's', operation_id: 'o' }),
    });
    assert.equal(((await admission.json()) as { code: string }).code, 'SERVICE_DRAINING');
  } finally {
    await stopFixture(fixture);
  }
});
