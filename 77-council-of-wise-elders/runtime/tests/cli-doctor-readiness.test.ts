import assert from 'node:assert/strict';
import test from 'node:test';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { tempDataDir } from './helpers.js';

function capture() {
  let out = '';
  let err = '';
  const io: CliIo = {
    out: (value) => { out += value; },
    err: (value) => { err += value; },
  };
  return { io, out: () => out, err: () => err };
}

test('offline doctor never advertises an unconfigured Council as usable', async () => {
  const c = capture();
  const code = await runCli(
    ['doctor', '--json', '--data-dir', tempDataDir('doctor-readiness-none')],
    c.io,
    { createHost: (options) => createLocalHost({ ...options, discoverRoutes: false }) },
  );
  assert.equal(code, 0, c.err());
  const data = JSON.parse(c.out()) as {
    ok: boolean;
    usable: boolean;
    readiness: { live_route: string; completed_live_council: string };
    readiness_blockers: string[];
  };
  assert.equal(data.ok, true, 'structural core checks are a distinct result');
  assert.equal(data.usable, false);
  assert.equal(data.readiness.live_route, 'unavailable');
  assert.equal(data.readiness.completed_live_council, 'unverified');
  assert.ok(data.readiness_blockers.some((x) => x.includes('model route')));
});

test('offline doctor does not probe, spend or certify a composed route', async () => {
  const c = capture();
  let calls = 0;
  const code = await runCli(
    ['doctor', '--json', '--data-dir', tempDataDir('doctor-readiness-route')],
    c.io,
    {
      createHost: (options) => createLocalHost({
        ...options,
        discoverRoutes: false,
        transports: [{
          routeId: 'explicit-test-route',
          transport: {
            async generate() {
              calls += 1;
              throw new Error('offline doctor must never invoke a model');
            },
          },
        }],
      }),
    },
  );
  assert.equal(code, 0, c.err());
  const data = JSON.parse(c.out()) as {
    ok: boolean;
    usable: boolean;
    readiness: { live_route: string; durable_worker: string };
  };
  assert.equal(calls, 0);
  assert.equal(data.ok, true);
  assert.equal(data.usable, false, 'a composed route is not an independently proven complete Council');
  assert.equal(data.readiness.live_route, 'composed_not_probed');
  assert.equal(data.readiness.durable_worker, 'unverified');
});
