/**
 * WER-021 standalone front-door service tests.
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/service/service.test.ts
 *
 * Tier A only: loopback HTTP servers on ephemeral ports, injected probes,
 * an injected browser opener and an injected admission sink. No provider
 * request, no credential, no installed service, no launchd/systemd unit,
 * no real browser launch, no live event stream and no live session are
 * claimed by these tests. Those are DEFERRED to WER-021 full packaging,
 * WER-023 (remote access) and WER-026 (installed proof).
 *
 * Proven here:
 * - readiness layers are independent and offline readiness makes zero
 *   provider calls (dispatch count asserted 0);
 * - duplicate start reuses ONLY a verified matching service, and the
 *   reusing handle cannot stop the owner;
 * - an unrelated listener is refused and left running;
 * - a managed session returns its owning external URL rather than a
 *   local duplicate;
 * - the emitted session URL is the true bound URL;
 * - drain fences new admissions while existing sessions stay reachable;
 * - a failed browser open still returns the usable URL.
 */

import assert from 'node:assert/strict';
import { createServer, type Server } from 'node:http';
import test from 'node:test';

import { CouncilFrontDoor } from './front-door.js';
import {
  buildServiceIdentity,
  serviceIdentityMatches,
} from './identity.js';
import {
  evaluateServiceReadiness,
  routeObservationFromDiscovery,
  workerObservationFromHandle,
  type ReadinessObservation,
} from './readiness.js';
import { resolveSessionTarget, sessionUrl } from './sessions.js';
import type {
  AdmissionRequest,
  CouncilConveningPort,
  CouncilRoutesResponse,
  ServiceIdentity,
} from './types.js';
import type { ConveneAccepted, ConveneInput } from './driver.js';

const FIXED_NOW = '2026-10-18T12:00:00.000Z';
const nowUtc = (): string => FIXED_NOW;

function identity(startedAt = FIXED_NOW): ServiceIdentity {
  return buildServiceIdentity({
    tenant_id: 'tenant-w08',
    company_id: 'company-w08',
    data_dir: '/tmp/w08-u001-data',
    started_at: startedAt,
  });
}

const ready: ReadinessObservation = { state: 'ready', artifact: 'observed' };

async function listenRaw(
  handler: (req: import('node:http').IncomingMessage, res: import('node:http').ServerResponse) => void,
): Promise<{ server: Server; port: number; origin: string }> {
  const server = createServer(handler);
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  assert.ok(address && typeof address !== 'string', 'raw listener reports a TCP address');
  return { server, port: address.port, origin: `http://127.0.0.1:${address.port}` };
}

async function closeRaw(server: Server): Promise<void> {
  await new Promise<void>((resolve) => server.close(() => resolve()));
}

// ------------------------------------------------------------------ readiness

test('readiness layers are independent and offline readiness makes zero provider calls', async () => {
  let dispatchCalls = 0;
  let callableCalls = 0;

  const result = await evaluateServiceReadiness(
    {
      nowUtc,
      origin: 'http://127.0.0.1:43210',
      discovery: () => ({ state: 'ready', artifact: 'host-layout observed' }),
      executable: () => ({ state: 'ready', artifact: `node ${process.version}` }),
      store: () => {
        throw new Error('database is locked');
      },
      route: () => ({
        state: 'blocked',
        artifact: 'route-a',
        blocker: {
          code: 'ROUTE_NOT_COMPOSABLE',
          detail: 'route-a: ROUTE_ENDPOINT_MISSING',
        },
        recovery: 'Fix the route-a endpoint.',
      }),
      routeCallable: () => {
        callableCalls += 1;
        return ready;
      },
      packs: () => ({ state: 'ready', artifact: '9/9 seat packs' }),
      worker: () => ({ state: 'unknown' }),
      ui: () => ({
        state: 'blocked',
        blocker: { code: 'UI_NOT_BUNDLED', detail: 'no UI build' },
        recovery: 'Package the UI build.',
      }),
      providerDispatch: async () => {
        dispatchCalls += 1;
        return 'dispatched';
      },
    },
    { offline: true },
  );

  assert.deepEqual(
    result.layers.map((layer) => layer.layer),
    ['discovery', 'executable', 'store', 'route', 'packs', 'worker', 'ui'],
  );
  for (const layer of result.layers) {
    assert.equal(layer.observed_at, FIXED_NOW);
    assert.equal(layer.offline, true);
  }

  const byLayer = new Map(result.layers.map((layer) => [layer.layer, layer]));
  assert.equal(byLayer.get('discovery')?.state, 'ready');
  assert.equal(byLayer.get('executable')?.state, 'ready');
  assert.equal(byLayer.get('store')?.state, 'blocked');
  assert.equal(byLayer.get('store')?.blocker?.code, 'READINESS_PROBE_FAILED');
  assert.ok(byLayer.get('store')?.blocker?.detail.includes('database is locked'));
  assert.equal(byLayer.get('route')?.state, 'blocked');
  assert.equal(byLayer.get('route')?.blocker?.code, 'ROUTE_NOT_COMPOSABLE');
  assert.equal(byLayer.get('packs')?.state, 'ready');
  assert.equal(byLayer.get('worker')?.state, 'unknown');
  assert.equal(byLayer.get('ui')?.state, 'blocked');

  assert.equal(dispatchCalls, 0, 'offline readiness never dispatches a provider');
  assert.equal(callableCalls, 0, 'the route-callable probe is not reached offline');
  assert.equal(result.provider_calls, 0);
  assert.equal(result.usable, false);
  assert.deepEqual(result.blocked_layers, ['store', 'route', 'ui']);
});

test('usable is true only when every layer is ready', async () => {
  const result = await evaluateServiceReadiness(
    {
      nowUtc,
      discovery: () => ready,
      executable: () => ready,
      store: () => ready,
      route: () => ready,
      packs: () => ready,
      worker: () => ready,
      ui: () => ready,
    },
    { offline: true },
  );
  assert.equal(result.usable, true);
  assert.deepEqual(result.blocked_layers, []);
  assert.equal(result.provider_calls, 0);
});

test('an offline probe that tries to dispatch is refused, counted and blocked', async () => {
  let providerCalls = 0;
  const result = await evaluateServiceReadiness(
    {
      nowUtc,
      route: async (context) => {
        await context.dispatchProvider();
        return ready;
      },
      providerDispatch: async () => {
        providerCalls += 1;
        return 'dispatch';
      },
    },
    { offline: true },
  );
  const routeLayer = result.layers.find((layer) => layer.layer === 'route');
  assert.equal(routeLayer?.state, 'blocked');
  assert.equal(routeLayer?.blocker?.code, 'READINESS_PROBE_FAILED');
  assert.equal(result.provider_calls, 1);
  assert.equal(providerCalls, 0, 'the provider port itself was never called');
});

test('route discovery and worker handles map into honest independent observations', () => {
  assert.equal(routeObservationFromDiscovery([]).state, 'blocked');
  assert.equal(routeObservationFromDiscovery([]).blocker?.code, 'ROUTE_NOT_CONFIGURED');
  assert.equal(routeObservationFromDiscovery(null).blocker?.code, 'ROUTE_NOT_CONFIGURED');

  const notComposed = routeObservationFromDiscovery([
    {
      route_id: 'route-a',
      provider_slug: 'provider-a',
      kind: 'compatible',
      identity_level: 'configured',
      composed: false,
      not_composed_reason: 'ROUTE_ENDPOINT_MISSING',
      usable_with_model: false,
      model_candidates: [],
    },
  ]);
  assert.equal(notComposed.state, 'blocked');
  assert.equal(notComposed.blocker?.code, 'ROUTE_NOT_COMPOSABLE');
  assert.ok(notComposed.blocker?.detail.includes('route-a'));

  const composed = routeObservationFromDiscovery([
    {
      route_id: 'route-a',
      provider_slug: 'provider-a',
      kind: 'compatible',
      identity_level: 'configured',
      composed: true,
      not_composed_reason: null,
      usable_with_model: false,
      model_candidates: ['model-a'],
    },
    {
      route_id: 'route-b',
      provider_slug: 'provider-b',
      kind: 'harness',
      identity_level: 'configured',
      composed: false,
      not_composed_reason: 'ROUTE_HARNESS_EXECUTABLE_MISSING',
      usable_with_model: false,
      model_candidates: [],
    },
  ]);
  assert.equal(composed.state, 'ready');
  assert.ok(composed.artifact?.includes('1/2'));

  assert.equal(workerObservationFromHandle(null).blocker?.code, 'WORKER_NOT_STARTED');
  assert.equal(workerObservationFromHandle({ running: false }).blocker?.code, 'WORKER_NOT_RUNNING');
  assert.equal(workerObservationFromHandle({ running: true }).state, 'ready');
});

// ------------------------------------------------------------------- identity

test('identity matching ignores started_at and rejects an owner mismatch', () => {
  const first = identity('2026-10-18T12:00:00.000Z');
  const restarted = identity('2026-10-19T09:00:00.000Z');
  assert.equal(serviceIdentityMatches(first, restarted), true);

  const otherOwner: ServiceIdentity = {
    ...first,
    owner: { ...first.owner, data_dir_sha256: 'f'.repeat(64) },
  };
  assert.equal(serviceIdentityMatches(first, otherOwner), false);
  assert.equal(serviceIdentityMatches(first, null), false);
});

// ------------------------------------------------------------ duplicate start

test('duplicate start reuses a verified matching service and never owns it', async () => {
  const first = new CouncilFrontDoor({ identity: identity(), ports: [0] });
  const started = await first.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const second = new CouncilFrontDoor({
    identity: identity('2026-10-18T12:00:05.000Z'),
    ports: [started.port],
  });
  const reused = await second.start();
  assert.equal(reused.outcome, 'reused');
  if (reused.outcome !== 'reused') return;
  assert.equal(reused.origin, started.origin);
  assert.equal(
    reused.identity.owner.data_dir_sha256,
    started.identity.owner.data_dir_sha256,
  );

  const stopped = await second.stop();
  assert.deepEqual(stopped, {
    stopped: false,
    reason: 'REUSED_SERVICE_NOT_OWNED',
  });

  const health = await fetch(`${started.origin}/healthz`);
  assert.equal(health.status, 200);
  const body = (await health.json()) as { ok: boolean };
  assert.equal(body.ok, true);

  await first.stop();
});

test('an unrelated listener is refused and left running', async () => {
  const unrelated = await listenRaw((_req, res) => {
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('not council');
  });
  try {
    const service = new CouncilFrontDoor({
      identity: identity(),
      ports: [unrelated.port],
    });
    const outcome = await service.start();
    assert.equal(outcome.outcome, 'refused');
    if (outcome.outcome !== 'refused') return;
    assert.equal(outcome.blockers.length, 1);
    assert.equal(outcome.blockers[0].code, 'PORT_IN_USE_UNRELATED');
    assert.ok(outcome.blockers[0].detail.includes('left running'));
    assert.match(outcome.blockers[0].recovery, /never kills an unrelated process/);
    assert.equal(service.getOrigin(), null);
    assert.equal(service.getPort(), null);

    const response = await fetch(`${unrelated.origin}/`);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'not council');
  } finally {
    await closeRaw(unrelated.server);
  }
});

test('a non-loopback bind host is refused', async () => {
  const service = new CouncilFrontDoor({
    identity: identity(),
    host: '0.0.0.0',
    ports: [0],
  });
  const outcome = await service.start();
  assert.equal(outcome.outcome, 'refused');
  if (outcome.outcome !== 'refused') return;
  assert.equal(outcome.blockers[0].code, 'SERVICE_HOST_NOT_LOOPBACK');
});

// ---------------------------------------------------------------- sessions

test('a managed session returns its owning external URL and is never started locally', async () => {
  const service = new CouncilFrontDoor({
    identity: identity(),
    ports: [0],
    openUrl: (url) => ({
      url,
      opened: true,
      command: 'injected',
      error: null,
      recovery: null,
    }),
  });
  const started = await service.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const ownerUrl = 'https://command.example.test/council/managed-1';
  const record = {
    session_id: 'managed-1',
    authority: 'managed' as const,
    owning_session_url: ownerUrl,
  };

  const resolved = resolveSessionTarget(record, { origin: started.origin });
  assert.equal(resolved.kind, 'external');
  if (resolved.kind !== 'external') return;
  assert.equal(resolved.url, ownerUrl);
  assert.equal(resolved.launched_locally, false);

  const opened = service.openSession(record);
  assert.equal(opened.target.kind, 'external');
  assert.equal(opened.browser?.url, ownerUrl);

  const missingOwner = service.openSession({
    session_id: 'managed-2',
    authority: 'managed',
  });
  assert.equal(missingOwner.target.kind, 'blocked');
  if (missingOwner.target.kind !== 'blocked') return;
  assert.equal(missingOwner.target.blocker.code, 'MANAGED_SESSION_OWNER_URL_MISSING');
  assert.equal(missingOwner.target.launched_locally, false);
  assert.equal(missingOwner.browser, null);

  await service.stop();
});

test('the emitted session URL is the actual bound URL', async () => {
  const service = new CouncilFrontDoor({ identity: identity(), ports: [0] });
  const started = await service.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const opened = service.openSession(
    { session_id: 'sess-42', authority: 'standalone' },
    { open: false },
  );
  assert.equal(opened.target.kind, 'local');
  if (opened.target.kind !== 'local') return;

  const url = new URL(opened.target.url);
  assert.equal(url.hostname, '127.0.0.1');
  assert.equal(Number(url.port), started.port);
  assert.equal(url.pathname, '/council/sess-42');
  assert.equal(opened.target.url, sessionUrl(started.origin, 'sess-42'));

  const response = await fetch(opened.target.url);
  assert.equal(response.status, 200);
  const body = (await response.json()) as {
    session_id: string;
    ui: string;
    api: { events: string };
  };
  assert.equal(body.session_id, 'sess-42');
  assert.equal(body.ui, 'not_bundled');
  assert.equal(body.api.events, '/api/council/sessions/sess-42/events');

  const events = await fetch(`${started.origin}${body.api.events}`);
  assert.equal(events.status, 501);
  const eventsBody = (await events.json()) as { code: string };
  assert.equal(eventsBody.code, 'EVENT_STREAM_ADAPTER_NOT_BOUND');

  await service.stop();
});

// -------------------------------------------------------------------- drain

test('drain fences new admissions and keeps existing sessions reachable', async () => {
  const sinkCalls: AdmissionRequest[] = [];
  const service = new CouncilFrontDoor({
    identity: identity(),
    ports: [0],
    admissionSink: (request) => {
      sinkCalls.push(request);
      return { accepted_by_owner: true, operation_id: request.operation_id };
    },
  });
  const started = await service.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const first = await service.admit({ session_id: 's1', operation_id: 'op-1' });
  assert.equal(first.accepted, true);
  assert.equal(sinkCalls.length, 1);

  const drain = service.drain();
  assert.deepEqual(drain, {
    drained: true,
    fenced: true,
    origin: started.origin,
    reason: null,
  });

  const fenced = await service.admit({ session_id: 's1', operation_id: 'op-2' });
  assert.equal(fenced.accepted, false);
  if (!fenced.accepted) {
    assert.equal(fenced.code, 'SERVICE_DRAINING');
    assert.equal(fenced.fenced, true);
  }
  assert.equal(sinkCalls.length, 1, 'no admission reached the owner after drain');

  const httpFenced = await fetch(`${started.origin}/api/council/admissions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ session_id: 's1', operation_id: 'op-3' }),
  });
  assert.equal(httpFenced.status, 503);
  const httpBody = (await httpFenced.json()) as { code: string };
  assert.equal(httpBody.code, 'SERVICE_DRAINING');

  const session = await fetch(`${started.origin}/council/s1`);
  assert.equal(session.status, 200);

  const stopped = await service.stop();
  assert.deepEqual(stopped, { stopped: true, reason: null });
});

test('an unbound admission sink never claims durable work', async () => {
  const service = new CouncilFrontDoor({ identity: identity(), ports: [0] });
  const started = await service.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const decision = await service.admit({
    session_id: 's1',
    operation_id: 'op-1',
  });
  assert.equal(decision.accepted, false);
  if (!decision.accepted) {
    assert.equal(decision.code, 'ADMISSION_SINK_UNBOUND');
    assert.equal(decision.fenced, false);
  }
  await service.stop();
});

// ------------------------------------------------------------------ browser

test('a failed browser open still returns the usable session URL', async () => {
  const service = new CouncilFrontDoor({
    identity: identity(),
    ports: [0],
    openUrl: (url) => ({
      url,
      opened: false,
      command: 'open',
      error: 'no display',
      recovery: `Open this URL manually: ${url}`,
    }),
  });
  const started = await service.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') return;

  const opened = service.openSession({
    session_id: 'sess-open-failure',
    authority: 'standalone',
  });
  assert.equal(opened.target.kind, 'local');
  if (opened.target.kind !== 'local') return;
  assert.equal(opened.browser?.opened, false);
  assert.equal(opened.browser?.url, opened.target.url);
  assert.ok(opened.target.url.startsWith(started.origin));
  assert.match(opened.browser?.recovery ?? '', /Open this URL manually/);

  await service.stop();
});

// ---------------------------------------------------------------- convening

const ROUTES_BODY: CouncilRoutesResponse = {
  routes: [
    {
      route_id: 'claude-nine-configured',
      provider_slug: 'claude-nine',
      kind: 'harness',
      composable: true,
      failure_code: null,
      default_for: ['claude-nine'],
    },
  ],
  harness_defaults: {
    'claude-nine': { route_id: 'claude-nine-configured', model: 'harness_default' },
    'claude-code': { route_id: 'claude-configured', model: 'sonnet' },
    deepseek: { route_id: 'deepseek-configured', model: 'latest_deepseek_flash' },
  },
  budgets: [{ route_id: 'claude-nine-configured', model: null, state: 'approved' }],
};

const ACCEPTED: ConveneAccepted = {
  session_id: 'sess-1',
  state: 'DRAFT',
  sample: true,
  route_id: 'claude-nine-configured',
  model_label: 'claude-nine configured default',
  selection_source: 'explicit',
  grant_id: 'grant-1',
  session_path: '/council/sess-1',
  events_path: '/api/council/sessions/sess-1/events',
};

function conveningStub(
  convene: (input: ConveneInput) => Promise<ConveneAccepted> = async () => ACCEPTED,
): { port: CouncilConveningPort; seen: ConveneInput[] } {
  const seen: ConveneInput[] = [];
  return {
    seen,
    port: {
      routes: () => ROUTES_BODY,
      convene: async (input) => {
        seen.push(input);
        return convene(input);
      },
    },
  };
}

async function withConveningDoor<T>(
  port: CouncilConveningPort | undefined,
  body: (input: { door: CouncilFrontDoor; origin: string }) => Promise<T>,
): Promise<T> {
  const door = new CouncilFrontDoor({ identity: identity(), ports: [0], convening: port });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  if (started.outcome !== 'started') throw new Error('unreachable');
  try {
    return await body({ door, origin: started.origin });
  } finally {
    await door.stop();
  }
}

function postConvene(origin: string, body: string, contentType = 'application/json'): Promise<Response> {
  return fetch(`${origin}/api/council/convene`, {
    method: 'POST',
    headers: { 'content-type': contentType },
    body,
  });
}

test('GET /api/council/routes serves the bound routes, harness defaults and budget states', async () => {
  await withConveningDoor(conveningStub().port, async ({ origin }) => {
    const response = await fetch(`${origin}/api/council/routes`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), ROUTES_BODY);
  });
});

test('with no convening driver bound both routes answer 501 CONVENING_NOT_BOUND', async () => {
  await withConveningDoor(undefined, async ({ origin }) => {
    const routes = await fetch(`${origin}/api/council/routes`);
    assert.equal(routes.status, 501);
    assert.equal(((await routes.json()) as { code: string }).code, 'CONVENING_NOT_BOUND');
    const convene = await postConvene(origin, '{"sample":true}');
    assert.equal(convene.status, 501);
    assert.equal(((await convene.json()) as { code: string }).code, 'CONVENING_NOT_BOUND');
  });
});

test('POST /api/council/convene forwards a validated request and answers 202', async () => {
  const stub = conveningStub();
  await withConveningDoor(stub.port, async ({ origin }) => {
    const response = await postConvene(
      origin,
      JSON.stringify({
        sample: true,
        route_id: 'claude-nine-configured',
        model: 'm1',
        harness: 'claude-nine',
        mode: 'quick',
        seat_ids: ['les-brown'],
        visibility: 'private',
        requested_by: 'tester',
        fresh_facts: [
          {
            claim: 'A current fact',
            url: 'https://example.test/a',
            retrieved_at: '2026-10-19T12:00:00Z',
          },
        ],
      }),
    );
    assert.equal(response.status, 202);
    assert.deepEqual(await response.json(), ACCEPTED);
    assert.deepEqual(stub.seen, [
      {
        sample: true,
        route: { route_id: 'claude-nine-configured', model: 'm1', harness: 'claude-nine' },
        mode: 'quick',
        seat_ids: ['les-brown'],
        visibility: 'private',
        requested_by: 'tester',
        fresh_facts: [
          {
            claim: 'A current fact',
            url: 'https://example.test/a',
            title: null,
            retrieved_at: '2026-10-19T12:00:00Z',
          },
        ],
      },
    ]);

    const bare = await postConvene(origin, '{"sample":true}');
    assert.equal(bare.status, 202);
    assert.equal(stub.seen[1].requested_by, 'service_client');
    assert.deepEqual(stub.seen[1].route, { route_id: undefined, model: undefined, harness: undefined });
  });
});

test('a malformed convene body is a typed 422 and never reaches the driver', async () => {
  const stub = conveningStub();
  await withConveningDoor(stub.port, async ({ origin }) => {
    const cases: Array<[string, string, string]> = [
      ['not json', '{nope', 'CONVENE_BODY_INVALID_JSON'],
      ['empty body', '', 'CONVENE_BODY_EMPTY'],
      ['array body', '[]', 'CONVENE_BODY_INVALID'],
      ['null body', 'null', 'CONVENE_BODY_INVALID'],
      ['neither sample nor brief', '{}', 'CONVENE_BODY_INVALID'],
      ['sample and brief', '{"sample":true,"brief":{}}', 'CONVENE_BODY_INVALID'],
      ['sample not boolean', '{"sample":"yes"}', 'CONVENE_BODY_INVALID'],
      ['unknown field', '{"sample":true,"route":"x"}', 'CONVENE_BODY_INVALID'],
      ['unknown harness', '{"sample":true,"harness":"gpt"}', 'CONVENE_BODY_INVALID'],
      ['unknown mode', '{"sample":true,"mode":"loud"}', 'CONVENE_BODY_INVALID'],
      ['unknown seat', '{"sample":true,"seat_ids":["nobody"]}', 'CONVENE_BODY_INVALID'],
      ['empty route id', '{"sample":true,"route_id":" "}', 'CONVENE_BODY_INVALID'],
      ['fresh fact without url', '{"sample":true,"fresh_facts":[{"claim":"c","retrieved_at":"2026-10-19"}]}', 'CONVENE_BODY_INVALID'],
      ['fresh fact with a bad date', '{"sample":true,"fresh_facts":[{"claim":"c","url":"https://e.test","retrieved_at":"yesterday"}]}', 'CONVENE_BODY_INVALID'],
    ];
    for (const [label, raw, code] of cases) {
      const response = await postConvene(origin, raw);
      assert.equal(response.status, 422, label);
      const body = (await response.json()) as { code: string; detail: string; recovery: string };
      assert.equal(body.code, code, label);
      assert.ok(body.detail.length > 0 && body.recovery.length > 0, label);
    }
    assert.equal(stub.seen.length, 0);

    const wrongType = await postConvene(origin, '{"sample":true}', 'text/plain');
    assert.equal(wrongType.status, 415);
    assert.equal(((await wrongType.json()) as { code: string }).code, 'CONVENE_CONTENT_TYPE');
    assert.equal(stub.seen.length, 0, 'a cross-site form post never reaches the driver');
  });
});

test('typed driver refusals keep their status; other failures are a plain 500', async () => {
  const refusal = (code: string, status: number | undefined) =>
    Object.assign(new Error(`refused ${code} at /Users/someone/secret`), {
      code,
      recovery: 'do the thing',
      detail: { path: '/Users/someone/secret', note: 'n' },
      http_status: status,
    });
  const queue: unknown[] = [
    refusal('COMPOSITION_NOT_READY', 503),
    refusal('CONVENE_INPUT_INVALID', 422),
    refusal('ROUTE_NOT_COMPOSABLE', 409),
    refusal('ROUTE_CHOICE_REQUIRED', undefined),
    new Error('disk exploded at /Users/someone/secret'),
  ];
  const stub = conveningStub(async () => {
    throw queue.shift();
  });
  await withConveningDoor(stub.port, async ({ origin }) => {
    const expected: Array<[number, string]> = [
      [503, 'COMPOSITION_NOT_READY'],
      [422, 'CONVENE_INPUT_INVALID'],
      [409, 'ROUTE_NOT_COMPOSABLE'],
      [422, 'ROUTE_CHOICE_REQUIRED'],
    ];
    for (const [status, code] of expected) {
      const response = await postConvene(origin, '{"sample":true}');
      assert.equal(response.status, status, code);
      const text = await response.text();
      const body = JSON.parse(text) as { code: string; recovery: string };
      assert.equal(body.code, code);
      assert.equal(body.recovery, 'do the thing');
      assert.ok(!text.includes('/Users/someone'), 'host paths are redacted');
    }
    const failed = await postConvene(origin, '{"sample":true}');
    assert.equal(failed.status, 500);
    const failedBody = await failed.text();
    assert.equal((JSON.parse(failedBody) as { code: string }).code, 'SERVICE_REQUEST_FAILED');
    assert.ok(!failedBody.includes('/Users/someone'), 'host paths are redacted in a 500 too');
  });
});

test('convene sits behind the admission fence: draining and reused handles refuse it', async () => {
  const stub = conveningStub();
  await withConveningDoor(stub.port, async ({ door, origin }) => {
    // Loopback-only: the same listener rule the admission route lives under.
    const remote = new CouncilFrontDoor({ identity: identity(), host: '0.0.0.0', ports: [0], convening: stub.port });
    const refused = await remote.start();
    assert.equal(refused.outcome, 'refused');

    door.drain();
    const fenced = await postConvene(origin, '{"sample":true}');
    assert.equal(fenced.status, 503);
    assert.equal(((await fenced.json()) as { code: string }).code, 'SERVICE_DRAINING');
    assert.equal(stub.seen.length, 0, 'a draining service convenes nothing');
    // Existing reads stay reachable while draining, like the session routes.
    assert.equal((await fetch(`${origin}/api/council/routes`)).status, 200);
  });

  await withConveningDoor(stub.port, async ({ origin: ownerOrigin }) => {
    const port = Number(new URL(ownerOrigin).port);
    const reuser = new CouncilFrontDoor({ identity: identity(), ports: [port], convening: stub.port });
    const reused = await reuser.start();
    assert.equal(reused.outcome, 'reused');
    // A reusing handle owns no listener, so convene cannot even arrive; the
    // shared fence is the same one admissions answer through.
    const admission = await reuser.admit({ session_id: 's', operation_id: 'o' });
    assert.equal(admission.accepted, false);
    assert.equal(stub.seen.length, 0);
  });
});
