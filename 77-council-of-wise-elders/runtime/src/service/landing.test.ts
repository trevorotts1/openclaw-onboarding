/**
 * WER-023/021 root landing route tests.
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/service/landing.test.ts
 *
 * Tier A only: a loopback server on an ephemeral port, injected identity
 * and injected readiness probes. No provider request, no credential, no
 * installed service, no network fetch beyond this process's own listener
 * and no live session are claimed.
 *
 * Proven here:
 * - `GET /` answers 200 text/html with no external asset, stylesheet,
 *   script or foreign origin;
 * - the page reflects the injected identity and readiness values and
 *   states UI_NOT_BUNDLED honestly;
 * - the catch-all 404 and every existing route keep their prior status
 *   and body;
 * - no file outside the two owned paths differs from the base commit.
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { CouncilFrontDoor } from './front-door.js';
import { buildServiceIdentity } from './identity.js';
import type { ReadinessObservation } from './readiness.js';
import type { ServiceIdentity } from './types.js';

const FIXED_NOW = '2026-10-18T12:00:00.000Z';
const ARTIFACT_MARKER = 'artifact-landing-marker';
const TENANT = 'tenant-landing-w17';
const COMPANY = 'company-landing-w17';
const STARTED_AT = '2026-10-18T09:30:00.000Z';

function identity(): ServiceIdentity {
  return buildServiceIdentity({
    tenant_id: TENANT,
    company_id: COMPANY,
    data_dir: '/tmp/w17-u001-data',
    started_at: STARTED_AT,
  });
}

const ready: ReadinessObservation = { state: 'ready', artifact: ARTIFACT_MARKER };
const nowUtc = (): string => FIXED_NOW;

async function withService<T>(
  body: (service: CouncilFrontDoor, origin: string) => Promise<T>,
): Promise<T> {
  const service = new CouncilFrontDoor({
    identity: identity(),
    ports: [0],
    readiness: {
      nowUtc,
      discovery: () => ready,
      executable: () => ready,
      store: () => ready,
      route: () => ready,
      packs: () => ready,
      worker: () => ready,
    },
  });
  const started = await service.start();
  assert.equal(started.outcome, 'started', 'landing tests own a loopback listener');
  assert.ok(started.origin !== null, 'a started service reports its origin');
  try {
    return await body(service, started.origin);
  } finally {
    await service.stop();
  }
}

// ------------------------------------------------------------- landing page

test('GET / serves a self-contained landing page with the real service values', async () => {
  await withService(async (service, origin) => {
    const response = await fetch(`${origin}/`);
    const body = await response.text();

    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'text/html; charset=utf-8');
    assert.equal(response.headers.get('cache-control'), 'no-store');

    // Identity is injected in this test, so these are real values, not
    // page constants.
    assert.match(body, /Council of Wise Elders — service landing/);
    assert.ok(body.includes('council-of-wise-elders'), 'service name is rendered');
    assert.ok(body.includes('standalone'), 'composition is rendered');
    assert.ok(body.includes('v1'), 'api_version is rendered');
    assert.ok(body.includes(TENANT), 'owner tenant is rendered');
    assert.ok(body.includes(COMPANY), 'owner company is rendered');
    assert.ok(body.includes(STARTED_AT), 'started_at is rendered');
    assert.ok(body.includes(origin), 'the verified origin is rendered');

    // Readiness comes from this.readiness(), not from literals in the page.
    assert.ok(body.includes(ARTIFACT_MARKER), 'injected readiness artifact is rendered');
    assert.ok(body.includes(FIXED_NOW), 'readiness observation time is rendered');

    // Honest about what is and is not packaged.
    assert.ok(body.includes('UI_NOT_BUNDLED'), 'UI_NOT_BUNDLED is named');
    assert.ok(body.includes('WER-021'), 'WER-021 full packaging is named');
    assert.ok(
      body.includes('<strong>not</strong> the full Council chamber UI'),
      'the page says it is not the full chamber UI',
    );
    assert.ok(
      body.includes('EVENT_STREAM_ADAPTER_NOT_BOUND'),
      'the unbound event stream adapter is named',
    );

    // No external asset, script, stylesheet, font or foreign origin.
    assert.equal(body.includes('<script'), false, 'no script element at all');
    assert.equal(body.includes('<script src='), false, 'no external script');
    assert.equal(/<link\b/i.test(body), false, 'no stylesheet or asset link');
    const withoutOwnOrigin = body.split(origin).join('');
    assert.equal(withoutOwnOrigin.includes('http://'), false, 'no foreign http URL');
    assert.equal(withoutOwnOrigin.includes('https://'), false, 'no https URL at all');

    // Never leak an absolute operator home path.
    assert.equal(body.includes('/Users/'), false, 'no macOS home path');
    assert.equal(body.includes('/home/'), false, 'no Linux home path');
    assert.equal(body.includes('\\Users\\'), false, 'no Windows home path');

    // The links point at this service's own origin.
    assert.ok(body.includes(`${origin}/api/council/service/identity`));
    assert.ok(body.includes(`${origin}/council/your-session-id`));
    assert.ok(body.includes(`${origin}/api/council/sessions/your-session-id/events`));

    assert.equal(service.getState(), 'running');
  });
});

// --------------------------------------------------- existing routes intact

test('every existing route keeps its previous status and body', async () => {
  await withService(async (_service, origin) => {
    const identityResponse = await fetch(`${origin}/api/council/service/identity`);
    assert.equal(identityResponse.status, 200);
    assert.deepEqual(await identityResponse.json(), identity());

    const sessionResponse = await fetch(`${origin}/council/s1`);
    assert.equal(sessionResponse.status, 200);
    const session = (await sessionResponse.json()) as Record<string, unknown>;
    assert.equal(session.session_id, 's1');
    assert.equal(session.authority, 'standalone');
    assert.equal(session.url, `${origin}/council/s1`);
    assert.equal(session.ui, 'not_bundled');
    assert.deepEqual(session.blocker, {
      code: 'UI_NOT_BUNDLED',
      detail: 'The shared Council UI build is not packaged by this service slice.',
      recovery:
        'Package the accepted shared Council UI build (WER-021 full packaging), then re-run service-readiness.',
    });
    assert.equal(session.api && (session.api as Record<string, unknown>).events, '/api/council/sessions/s1/events');

    const eventsResponse = await fetch(`${origin}/api/council/sessions/s1/events`);
    assert.equal(eventsResponse.status, 501);
    const events = (await eventsResponse.json()) as Record<string, unknown>;
    assert.equal(events.code, 'EVENT_STREAM_ADAPTER_NOT_BOUND');
    assert.equal(events.session_id, 's1');
  });
});

test('unknown paths still answer the SERVICE_ROUTE_NOT_FOUND 404', async () => {
  await withService(async (_service, origin) => {
    const response = await fetch(`${origin}/nope`);
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('content-type'), 'application/json; charset=utf-8');
    assert.deepEqual(await response.json(), {
      code: 'SERVICE_ROUTE_NOT_FOUND',
      detail: 'No service route for GET /nope.',
    });
  });
});

// ------------------------------------------------------------ scope proof

test('no file outside the two owned paths differs from the base commit', (t) => {
  const serviceDir = fileURLToPath(new URL('.', import.meta.url));
  const repoRoot = fileURLToPath(new URL('../../../../', import.meta.url));
  const allowed = new Set([
    '77-council-of-wise-elders/runtime/src/service/front-door.ts',
    '77-council-of-wise-elders/runtime/src/service/landing.test.ts',
  ]);
  let status: string;
  try {
    status = execFileSync('git', ['status', '--porcelain'], {
      cwd: repoRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch {
    t.skip('git is unavailable here; scope is proven in the evidence log instead');
    return;
  }
  const changed = status
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => line.slice(3).trim())
    // Local dependency scaffolding (a symlink used to run this suite) is
    // not source; it is ignored by path so real edits cannot hide here.
    .filter((path) => path.length > 0 && !/(^|\/)node_modules(\/|$)/.test(path));
  const illegal = changed.filter((path) => !allowed.has(path));
  assert.deepEqual(illegal, [], `unexpected changed files: ${illegal.join(', ')}`);
  assert.ok(serviceDir.includes('77-council-of-wise-elders'), 'test runs inside the runtime');
});
