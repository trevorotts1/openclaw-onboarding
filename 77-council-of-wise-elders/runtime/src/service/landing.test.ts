/**
 * WER-021/023 root landing route tests.
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
 * - `GET /` answers 302 with the relative `Location: /chamber/` when the
 *   packaged chamber entry page exists (no loopback host in the header);
 * - `GET /chamber/` serves the chamber HTML, which never carries the
 *   diagnostics banner;
 * - `GET /status` serves the diagnostics page with the identity table,
 *   a link to the packaged Council room (no stale UI_NOT_BUNDLED notice)
 *   and no external asset or foreign origin;
 * - without the packaged assets `GET /` keeps that honest status page and
 *   `/chamber/` falls back to the unchanged catch-all 404;
 * - the catch-all 404 and every existing route keep their prior status
 *   and body;
 * - the front door imports only its own layers, so it can never grow a
 *   second owner of the routes, the store or the browser open.
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import type { CouncilEventStreamAdapter, CouncilSessionReader } from './events.js';
import { CouncilFrontDoor, type FrontDoorOptions } from './front-door.js';
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
  extra: Partial<FrontDoorOptions> = {},
): Promise<T> {
  const service = new CouncilFrontDoor({
    ...extra,
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

// ----------------------------------------------------------- chamber entry

test('GET / redirects to the packaged chamber with a relative Location', async () => {
  await withService(async (_service, origin) => {
    const response = await fetch(`${origin}/`, { redirect: 'manual' });
    const body = await response.text();

    assert.equal(response.status, 302);
    assert.equal(response.headers.get('location'), '/chamber/');
    // A phone reaching the authenticated public origin can never resolve
    // an absolute loopback URL, so the header must stay relative.
    const location = response.headers.get('location') ?? '';
    assert.equal(/^https?:\/\//.test(location), false, 'Location is not absolute');
    assert.equal(location.includes('127.0.0.1'), false, 'no loopback host');
    assert.equal(location.includes('localhost'), false, 'no localhost host');
    assert.equal(body, '', 'the redirect carries no page body');
  });
});

test('GET /chamber/ serves the chamber HTML without the diagnostics banner', async () => {
  await withService(async (_service, origin) => {
    const response = await fetch(`${origin}/chamber/`);
    const body = await response.text();

    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'text/html; charset=utf-8');
    assert.equal(body.includes('UI_NOT_BUNDLED'), false, 'chamber is not a status report');
    assert.ok(body.includes('The chamber'), 'the chamber page is served');
    assert.equal(body.includes('/Users/'), false, 'no macOS home path');
    assert.equal(body.includes('/home/'), false, 'no Linux home path');
  });
});

// ----------------------------------------------------------- status page

test('GET /status serves the diagnostics page', async () => {
  await withService(async (service, origin) => {
    const response = await fetch(`${origin}/status`);
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
    assert.equal(body.includes('<strong>UI_NOT_BUNDLED</strong>'), false, 'the chamber is packaged, so no stale notice');
    assert.equal(body.includes('is not packaged'), false, 'the page never says the chamber is missing');
    assert.ok(body.includes(`href="${origin}/chamber/"`), 'the page points at the Council room');
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

// ------------------------------------------- notices follow the bindings

const boundEvents: CouncilEventStreamAdapter = { open: () => ({ replay: () => [] }) };
const boundReader: CouncilSessionReader = { read: () => null };

test('GET /status drops the not-bound notice when the adapters are bound', async () => {
  await withService(
    async (_service, origin) => {
      const body = await (await fetch(`${origin}/status`)).text();
      assert.equal(
        body.includes('EVENT_STREAM_ADAPTER_NOT_BOUND'),
        false,
        'a bound event stream must not be reported as unbound',
      );
      assert.equal(body.includes('adapter not bound'), false, 'no unbound route wording');
      assert.equal(body.includes('not_bundled'), false, 'no unbound session wording');
      assert.ok(body.includes('durable event stream'), 'the bound event route is described');
      assert.ok(body.includes('durable session record'), 'the bound session route is described');
      assert.equal(body.includes('<strong>UI_NOT_BUNDLED</strong>'), false, 'the packaged chamber is not reported missing');
    },
    { eventsAdapter: boundEvents, sessionReader: boundReader },
  );
});

test('GET /status keeps the not-bound notice when only one adapter is bound', async () => {
  await withService(
    async (_service, origin) => {
      const body = await (await fetch(`${origin}/status`)).text();
      assert.equal(body.includes('EVENT_STREAM_ADAPTER_NOT_BOUND'), true);
      assert.ok(body.includes('durable session record'), 'the bound reader is still described');
    },
    { sessionReader: boundReader },
  );
});

// ------------------------------------------------ without packaged assets

test('without packaged chamber assets GET / keeps the honest status page', async () => {
  // An empty temp dir stands in for a build with no packaged chamber.
  // The shared public/chamber path is never touched, so sibling tests
  // reading it concurrently cannot observe a rename mid-run.
  const emptyChamberDir = mkdtempSync(join(tmpdir(), 'landing-no-chamber-'));
  try {
    await withService(
      async (_service, origin) => {
      const response = await fetch(`${origin}/`, { redirect: 'manual' });
      const body = await response.text();
      assert.equal(response.status, 200, 'no assets: the root serves the status page');
      assert.match(body, /Council of Wise Elders — service landing/);
      assert.ok(body.includes('<strong>UI_NOT_BUNDLED</strong>'), 'the honest blocker is still named');

      const chamber = await fetch(`${origin}/chamber/`, { redirect: 'manual' });
      assert.equal(chamber.status, 404, 'no assets: the chamber route falls through');
      assert.equal(chamber.headers.get('location'), null);
      assert.deepEqual(await chamber.json(), {
        code: 'SERVICE_ROUTE_NOT_FOUND',
        detail: 'No service route for GET /chamber/.',
      });

      const status = await fetch(`${origin}/status`);
      assert.equal(status.status, 200, 'diagnostics stay reachable in every build');
      assert.ok((await status.text()).includes('UI_NOT_BUNDLED'));
      },
      { chamberAssetDir: emptyChamberDir },
    );
  } finally {
    rmSync(emptyChamberDir, { recursive: true, force: true });
  }
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
//
// This replaces the former changed-file proof ("no file outside the owned
// paths differs from the base commit"). That proof read `git status` of the
// checkout the suite ran in, so it failed for every unit that edited the
// runtime and for no real defect, and each such unit had to widen a
// changed-file allowlist to unblock itself. The route behaviour it stood in
// front of is asserted above; what is left to guard is containment: the front
// door may depend only on its own layers, so it can never grow a second owner
// of the routes, the store or the browser open.
const FRONT_DOOR_LAYERS = ['node:', './', '../bridges/', '../contracts/'];

function importedSpecifiers(source: string): string[] {
  return source
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('import ') || line.startsWith('} from '))
    .map((line) => /from\s+'([^']+)'/.exec(line)?.[1])
    .filter((s): s is string => typeof s === 'string');
}

test('the front door imports only its own layers, never a second owner', () => {
  const serviceDir = fileURLToPath(new URL('.', import.meta.url));
  assert.ok(serviceDir.includes('77-council-of-wise-elders'), 'test runs inside the runtime');
  const source = readFileSync(join(serviceDir, 'front-door.ts'), 'utf8');
  const specifiers = importedSpecifiers(source);
  // A source that yields no imports would make the check vacuous.
  assert.ok(specifiers.length >= 5, `front-door.ts imports were read, got ${specifiers.length}`);
  const outside = specifiers.filter((s) => !FRONT_DOOR_LAYERS.some((layer) => s.startsWith(layer)));
  assert.deepEqual(outside, [], `front-door.ts reached outside its own layers: ${outside.join(', ')}`);
  // The real regression shape: the front door reaching into the CLI host or
  // the persistence store directly instead of its injected ports.
  const forbidden = specifiers.filter((s) => s.includes('cli/') || s.includes('persistence/'));
  assert.deepEqual(forbidden, [], `the front door must use its injected ports, not ${forbidden.join(', ')}`);
});
