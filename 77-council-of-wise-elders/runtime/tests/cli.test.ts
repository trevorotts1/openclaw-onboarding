/**
 * CWE-004 CLI dispatcher tests: runCli with captured IO against real
 * local hosts in temporary data directories, including a data directory
 * path containing spaces.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { skillRootFromModule } from '../src/cli/dispatcher.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { tempDataDir } from './helpers.js';

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let outText = '';
  let errText = '';
  return {
    io: {
      out: (t) => {
        outText += t;
      },
      err: (t) => {
        errText += t;
      },
    },
    out: () => outText,
    err: () => errText,
  };
}

test('cli: no arguments prints the command list and exits 0', async () => {
  const c = capture();
  const code = await runCli([], c.io);
  assert.equal(code, 0);
  assert.ok(c.out().includes('blackceo-council'));
  assert.ok(c.out().includes('convene'));
  for (const stale of ['authorization', 'grant-ref', 'approve']) {
    assert.equal(c.out().includes(stale), false, `help no longer mentions ${stale}`);
  }
});

test('cli: unknown command is a usage error with exit 2', async () => {
  const c = capture();
  const code = await runCli(['frobnicate'], c.io);
  assert.equal(code, 2);
  assert.ok(c.err().includes('COUNCIL_USAGE'));
});

test('cli: doctor is offline, JSON clean, and reports honest not-ready items', async () => {
  const c = capture();
  const dir = tempDataDir('cli doctor');
  // A bare doctor on a machine with configured harness roots truthfully
  // reports live_routes_composed true (real transports compose; pinned by
  // the rp0461 cases in cli-route-composition.test.ts). This case pins the
  // not-ready contract, so route discovery is explicitly disabled to make
  // the environment deterministic instead of asserting per-machine state.
  const code = await runCli(['doctor', '--json', '--data-dir', dir], c.io, {
    createHost: (opts) => createLocalHost({ ...opts, discoverRoutes: false }),
  });
  assert.equal(code, 0);
  const data = JSON.parse(c.out()) as {
    ok: boolean;
    contracts: string;
    checks: Array<{ name: string; ok: boolean }>;
  };
  assert.equal(data.ok, true);
  assert.equal(data.contracts, 'wise-elders.core/1.0.0');
  const byName = new Map(data.checks.map((x) => [x.name, x.ok]));
  assert.equal(byName.get('node_sqlite'), true);
  assert.equal(byName.get('local_store'), true);
  assert.equal(byName.get('live_routes_composed'), false);
  // CWE-050 disclosure: CWE-049's standalone composition list item 1
  // composed the authorization service into this CLI, so the doctor
  // check now reports it ready (it was an honest not-ready before).
  assert.equal(byName.get('run_authorization_service'), true);
});

test('cli: data directory inside the skill tree is rejected', async () => {
  const c = capture();
  const inside = join(skillRootFromModule(), 'state-should-never-live-here');
  const code = await runCli(['create', '--sample', '--data-dir', inside], c.io);
  assert.equal(code, 2);
  assert.ok(c.err().includes('COUNCIL_INVALID_INPUT'));
});

test('cli: create, status, verdict-not-ready, and authorization honesty', async () => {
  const dir = tempDataDir('cli-flow');
  let c = capture();
  assert.equal(await runCli(['create', '--sample', '--data-dir', dir], c.io), 0);
  assert.ok(c.out().includes('SAMPLE session created: sess-fixture-1'));

  c = capture();
  assert.equal(
    await runCli(['status', 'sess-fixture-1', '--json', '--data-dir', dir], c.io),
    0,
  );
  const status = JSON.parse(c.out()) as { state: string; sample: boolean };
  assert.equal(status.state, 'DRAFT');
  assert.equal(status.sample, true);

  c = capture();
  const verdictCode = await runCli(
    ['verdict', 'sess-fixture-1', '--json', '--data-dir', dir],
    c.io,
  );
  assert.equal(verdictCode, 3);
  const envelope = JSON.parse(c.err()) as { error: { code: string } };
  assert.equal(envelope.error.code, 'COUNCIL_VERDICT_NOT_READY');

  c = capture();
  const startCode = await runCli(
    ['start', 'sess-fixture-1', '--grant-ref', 'anything', '--json', '--data-dir', dir],
    c.io,
  );
  assert.equal(startCode, 3);
  const startEnvelope = JSON.parse(c.err()) as { error: { code: string } };
  assert.equal(startEnvelope.error.code, 'RUN_AUTHORIZATION_REQUIRED');

  // CWE-050 disclosure: the authorization commands are composed now
  // (CWE-049 standalone list item 1): preview without a session ID is
  // a usage error from the real handler, not the retired
  // COUNCIL_FEATURE_NOT_READY placeholder.
  c = capture();
  assert.equal(
    await runCli(['authorization', 'preview', '--json', '--data-dir', dir], c.io),
    2,
  );
  assert.equal(
    (JSON.parse(c.err()) as { error: { code: string } }).error.code,
    'COUNCIL_USAGE',
  );

  c = capture();
  assert.equal(await runCli(['probe', '--json', '--data-dir', dir], c.io), 3);
  assert.equal(
    (JSON.parse(c.err()) as { error: { code: string } }).error.code,
    'COUNCIL_FEATURE_NOT_READY',
  );
});

test('cli: sample run completes, exports markdown and json, refuses pdf, replays events', async () => {
  const dir = tempDataDir('cli-sample');
  let c = capture();
  const code = await runCli(['sample', 'run', '--json', '--data-dir', dir], c.io);
  assert.equal(code, 0);
  const data = JSON.parse(c.out()) as {
    sample: boolean;
    state: string;
    verdict: { result_kind: string; label?: string; recommended_option_id?: string };
  };
  assert.equal(data.sample, true);
  assert.equal(data.state, 'COMPLETED');
  assert.equal(data.verdict.result_kind, 'scored');
  assert.equal(data.verdict.label, 'WAIT');
  assert.equal(data.verdict.recommended_option_id, 'B');

  c = capture();
  assert.equal(
    await runCli(['export', 'sess-fixture-1', '--format', 'md', '--data-dir', dir], c.io),
    0,
  );
  // CWE-050 disclosure: exports run through CWE-038's
  // ReportExportService (B15 portable half), so the markdown is the
  // CWE-038 decision report naming the session and the exact verdict
  // hash, replacing CWE-004's local verdictMarkdown rendering.
  assert.ok(c.out().includes('# Council of Wise Elders: Decision Report'));
  assert.ok(c.out().includes('Session: sess-fixture-1'));
  assert.ok(c.out().includes('Verdict content SHA-256:'));

  c = capture();
  assert.equal(
    await runCli(['export', 'sess-fixture-1', '--format', 'pdf', '--json', '--data-dir', dir], c.io),
    3,
  );
  assert.equal(
    (JSON.parse(c.err()) as { error: { code: string } }).error.code,
    'COUNCIL_FEATURE_NOT_READY',
  );

  c = capture();
  assert.equal(await runCli(['replay', 'sess-fixture-1', '--data-dir', dir], c.io), 0);
  assert.ok(c.out().includes('session_created'));
  assert.ok(c.out().includes('verdict_validated'));
});

test('cli: session not found is a stable typed error', async () => {
  const c = capture();
  const dir = tempDataDir('cli-missing');
  const code = await runCli(['status', 'sess-nope', '--json', '--data-dir', dir], c.io);
  assert.equal(code, 3);
  assert.equal(
    (JSON.parse(c.err()) as { error: { code: string } }).error.code,
    'COUNCIL_SESSION_NOT_FOUND',
  );
});

test('package import has no side effects (no database, no data directory)', () => {
  const home = tempDataDir('cli-import-home');
  const cwd = tempDataDir('cli-import-cwd');
  const indexPath = join(process.cwd(), 'src', 'index.ts');
  const tsxLoader = join(process.cwd(), 'node_modules', 'tsx', 'dist', 'loader.mjs');
  execFileSync(
    process.execPath,
    [
      '--import',
      tsxLoader,
      '--input-type=module',
      '-e',
      `await import(${JSON.stringify(indexPath)});`,
    ],
    {
      cwd,
      env: {
        ...process.env,
        HOME: home,
        XDG_DATA_HOME: join(home, 'xdg'),
        BLACKCEO_COUNCIL_DATA_DIR: '',
      },
      stdio: 'pipe',
    },
  );
  assert.deepEqual(readdirSync(cwd), []);
  assert.deepEqual(readdirSync(home), []);
});
