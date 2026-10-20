/**
 * L4: accurate repair prompts, and BLOCKED sessions that explain themselves.
 *
 * Runner:
 *   node --import tsx --test tests/repair-and-blocked-reason.test.ts
 *
 * One real service (composition root + HTTP listener on an ephemeral
 * loopback port) with a scripted fixture transport:
 * - simon-sinek: first reply is broken JSON ({"a","b"}), then valid;
 * - td-jakes: first reply is valid JSON with an unknown lens, then valid;
 * - michelle-obama: transport_rejected with an ECONNREFUSED message;
 * - les-brown: transport_rejected with a key-shaped string in the message.
 * The two rejected seats leave full mode one short of nine, so the
 * session ends BLOCKED and must say why.
 *
 * No provider request, no credential, no network beyond 127.0.0.1.
 */

import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { SEAT_ROSTER } from '../src/contracts/index.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type { TransportRequest, TransportResponse } from '../src/cli/host-ports.js';
import { TransportError } from '../src/providers/errors.js';
import { startCouncilService } from '../src/service/composition.js';
import { buildBlockedReason } from '../src/service/sessions.js';

class ScriptedTransport extends DeterministicFixtureTransport {
  readonly systems = new Map<string, string[]>();

  async generate(request: TransportRequest): Promise<TransportResponse> {
    const seat = request.seat_id as string;
    const seen = this.systems.get(`${seat}:${request.round ?? 1}`) ?? [];
    seen.push(request.system);
    this.systems.set(`${seat}:${request.round ?? 1}`, seen);
    const first = seen.length === 1 && (request.round ?? 1) === 1;
    if (seat === 'michelle-obama') {
      throw new TransportError('TRANSPORT_NETWORK_FAILED', 'connect ECONNREFUSED 127.0.0.1:20128');
    }
    if (seat === 'les-brown') {
      throw new TransportError('TRANSPORT_NETWORK_FAILED', 'denied for key sk-abcdefgh12345 by upstream');
    }
    const response = await super.generate(request);
    if (seat === 'simon-sinek' && first) {
      return { ...response, text: '{"card_kind":"advisor","strongest_objection","x"}' };
    }
    if (seat === 'td-jakes' && first) {
      const card = JSON.parse(response.text) as Record<string, unknown>;
      card.lenses_used = ['made-up-lens'];
      return { ...response, text: JSON.stringify(card) };
    }
    return response;
  }
}

async function until<T>(read: () => T | null | undefined, timeoutMs = 60_000): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = read();
    if (value !== null && value !== undefined) return value;
    assert.ok(Date.now() < deadline, 'timed out waiting');
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

test('invalid JSON and closed-set repairs are precise; a blocked session says why', async () => {
  const root = mkdtempSync(join(tmpdir(), 'l4-repair-'));
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
  const transport = new ScriptedTransport();

  const lines: string[] = [];
  const realWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = ((chunk: string | Uint8Array, ...rest: unknown[]) => {
    if (typeof chunk === 'string' && chunk.includes('"session_settled"')) lines.push(chunk);
    return (realWrite as (...args: unknown[]) => boolean)(chunk, ...rest);
  }) as typeof process.stdout.write;

  const service = await startCouncilService({
    tenantId: 'tenant-l4',
    companyId: 'company-l4',
    dataDir: join(root, 'data'),
    ports: [0],
    routeHomeDir: home,
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    resolveTransport: () => transport,
    workerPollIntervalMs: 20,
    handleSignals: false,
  });
  try {
    const origin = service.origin as string;
    const accepted = await fetch(`${origin}/api/council/convene`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sample: true, route_id: 'claude-nine-configured', requested_by: 'l4-test' }),
    });
    assert.equal(accepted.status, 202);
    const { session_id: sessionId } = (await accepted.json()) as { session_id: string };

    // The service prints exactly one session_settled line for the run.
    const line = await until(() => lines.find((l) => l.includes(sessionId)));
    const settled = JSON.parse(line) as Record<string, unknown>;
    assert.equal(settled.event, 'session_settled');
    assert.equal(settled.session_id, sessionId);
    assert.equal(settled.status, 'incomplete');
    assert.deepEqual([...(settled.missing_seats as string[])].sort(), ['les-brown', 'michelle-obama']);
    assert.equal(lines.filter((l) => l.includes(sessionId)).length, 1);

    // Invalid JSON: the repair says so and does not blame card_kind.
    const simon = transport.systems.get('simon-sinek:1') ?? [];
    assert.equal(simon.length, 2, 'one first call and one repair');
    assert.match(simon[1], /not valid JSON/);
    assert.doesNotMatch(simon[1], /Invalid discriminator/);
    assert.match(simon[1], /Reply with exactly one JSON object and nothing else/);

    // Closed set: the repair lists the validator's own lens list.
    const jakes = transport.systems.get('td-jakes:1') ?? [];
    assert.equal(jakes.length, 2);
    const lenses = SEAT_ROSTER.find((s) => s.seat_id === 'td-jakes')?.lenses ?? [];
    assert.ok(lenses.length > 0);
    assert.ok(jakes[1].includes(`lenses_used may contain only these values: ${lenses.join(', ')}.`));
    assert.equal(jakes[0].includes('only these values'), false, 'the first call carries no repair');

    // The session status JSON explains the block.
    const status = (await (await fetch(`${origin}/council/${sessionId}`)).json()) as {
      blocked_reason: {
        code: string;
        missing_seats: string[];
        last_errors: Array<{ seat_id: string; outcome_code: string; message: string }>;
      };
      session: { state: { state: string }; blocked_reason: unknown };
    };
    assert.equal(status.session.state.state, 'BLOCKED');
    assert.equal(status.blocked_reason.code, 'FULL_MODE_SEATS_MISSING');
    assert.deepEqual([...status.blocked_reason.missing_seats].sort(), ['les-brown', 'michelle-obama']);
    const bySeat = new Map(status.blocked_reason.last_errors.map((e) => [e.seat_id, e]));
    assert.equal(bySeat.get('michelle-obama')?.outcome_code, 'transport_rejected');
    assert.match(bySeat.get('michelle-obama')?.message ?? '', /ECONNREFUSED/);
    assert.match(bySeat.get('les-brown')?.message ?? '', /\[redacted\]/);
    assert.doesNotMatch(JSON.stringify(status), /sk-abcdefgh12345/);

    // The sessions list carries it too.
    const list = (await (await fetch(`${origin}/api/council/sessions`)).json()) as {
      sessions: Array<{ session_id: string; blocked_reason?: { missing_seats: string[] } }>;
    };
    assert.equal(list.sessions.find((s) => s.session_id === sessionId)?.blocked_reason?.missing_seats.length, 2);
  } finally {
    process.stdout.write = realWrite as typeof process.stdout.write;
    await service.stop();
    rmSync(root, { recursive: true, force: true });
  }
});

test('a session blocked before messages were journaled still lists its failed seats', () => {
  const seats = SEAT_ROSTER.map((s) => s.seat_id);
  const reason = buildBlockedReason({
    state: 'BLOCKED',
    mode: 'full',
    seat_ids: seats,
    cards: seats
      .filter((s) => s !== 'td-jakes')
      .map((seat_id) => ({ card_kind: 'advisor', round: 1, seat_id })),
    failures: [{ seat_id: 'td-jakes', outcome_code: 'output_validation_failed' }],
    events: [],
  });
  assert.deepEqual(reason?.missing_seats, ['td-jakes']);
  assert.deepEqual(reason?.last_errors, [
    { seat_id: 'td-jakes', outcome_code: 'output_validation_failed', message: null },
  ]);
  assert.equal(buildBlockedReason({ state: 'COMPLETED', mode: 'full', seat_ids: seats, cards: [], failures: [], events: [] }), null);
});
