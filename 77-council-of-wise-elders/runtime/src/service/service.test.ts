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
import type { AdmissionRequest, ServiceIdentity } from './types.js';

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
    },
    {
      route_id: 'route-b',
      provider_slug: 'provider-b',
      kind: 'harness',
      identity_level: 'configured',
      composed: false,
      not_composed_reason: 'ROUTE_HARNESS_EXECUTABLE_MISSING',
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
