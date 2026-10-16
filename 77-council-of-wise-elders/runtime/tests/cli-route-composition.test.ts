/**
 * RP-046-1 composition tests: the standalone host binds real
 * transports to the client's EXISTING configured routes, discovered
 * read-only (DEFECT-046-A repair; Sections 13.4, 25.2 step 7, 25.6).
 *
 * (a) a configured harness route gets the CWE-010 bridge transport
 *     registered and dispatches through the subprocess delegate
 *     boundary (a real child process at the outer boundary);
 * (b) a configured compatible-endpoint route gets the CWE-009
 *     transport registered;
 * (c) an unconfigured route still refuses COUNCIL_ROUTE_UNAVAILABLE;
 * (d) a full local session dispatches through the composed path to
 *     a verdict against a loopback test double at the outer boundary,
 *     with provider requests counted by the real budget ledger;
 * (e) no route is ever silently replaced.
 *
 * Test doubles live only at the outermost boundary: a fake harness
 * executable script and a loopback HTTP server. Everything between
 * (discovery, guard, transports, engine, ledger, grants) is the real
 * shipped code.
 */
import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { GuardedTransport } from '../src/bridges/host-bridge.js';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { CouncilError } from '../src/cli/errors.js';
import { CouncilEngine } from '../src/cli/engine.js';
import {
  buildSampleSession,
  DeterministicFixtureTransport,
} from '../src/cli/fixture-transport.js';
import type { TransportRequest } from '../src/cli/host-ports.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { CompatibleHttpTransport } from '../src/providers/compatible.js';
import { TransportError } from '../src/providers/errors.js';
import { buildTestGrant, tempDataDir } from './helpers.js';

const SEAT_BY_DISPLAY_NAME: Record<string, string> = {
  'Simon Sinek': 'simon-sinek',
  'T. D. Jakes': 'td-jakes',
  'Oprah Winfrey': 'oprah-winfrey',
  'Tiffany Aliche': 'tiffany-aliche',
  'Russell Brunson': 'russell-brunson',
  'Michelle Obama': 'michelle-obama',
  'Brené Brown': 'brene-brown',
  'Dr. Dennis Kimbro': 'dennis-kimbro',
  'Les Brown': 'les-brown',
};

function makeHome(label: string): string {
  return mkdtempSync(join(tmpdir(), `rp0461-${label}-`));
}

function captureIo() {
  let out = '';
  let err = '';
  const io: CliIo = {
    out: (t: string) => {
      out += t;
    },
    err: (t: string) => {
      err += t;
    },
  };
  return { io, out: () => out, err: () => err };
}

/** The fake harness executable: a real subprocess at the boundary. */
const FAKE_HARNESS_SCRIPT = `#!/usr/bin/env node
let data = '';
process.stdin.on('data', (c) => { data += c; });
process.stdin.on('end', () => {
  const idx = data.lastIndexOf('\\n\\n');
  const system = data.slice(0, idx);
  const input = JSON.parse(data.slice(idx + 2));
  const names = ${JSON.stringify(SEAT_BY_DISPLAY_NAME)};
  const seat = names[input.seat_display_name];
  const brief = input.brief;
  const ev = brief.evidence_manifest[0] ? brief.evidence_manifest[0].evidence_id : null;
  const scores = brief.options.map((o, i) => ({
    option_id: o.id,
    score: [6, 8, 7][i % 3],
    rationale: 'harness double score for ' + o.id,
    evidence_ids: ev ? [ev] : [],
  }));
  const top = scores.reduce((a, b) => (b.score > a.score ? b : a));
  const base = {
    schema_version: 'wise-elders.card/v1',
    session_id: brief.session_id,
    brief_revision: brief.revision,
    seat_id: seat,
    input_manifest_sha256: input.input_manifest_sha256,
    pack_version: input.pack_version,
  };
  let card;
  if (system.includes('ratification round')) {
    card = {
      ...base,
      card_kind: 'ratification',
      round: 3,
      draft_resolution_sha256: input.draft_resolution.semantic_sha256,
      resolution_stance: 'support',
      stance: 'support',
      preferred_option_id: top.option_id,
      option_scores: scores,
      amendments: [],
      accepted_condition_ids: [],
      unresolved_objections: [],
      evidence_strength: 'medium',
    };
  } else {
    card = {
      ...base,
      card_kind: 'advisor',
      round: system.includes('focused challenge round') ? 2 : 1,
      stance: 'conditional',
      preferred_option_id: top.option_id,
      option_scores: scores,
      framework_applications: [{
        framework_id: 'harness-double-framework',
        source_evidence_ids: ev ? [ev] : [],
        case_evidence_ids: [],
        application: 'Applied the seat framework to the frozen brief only.',
        attribution_kind: 'blackceo_adaptation',
      }],
      decisive_arguments: ['The bounded option produces evidence first.'],
      strongest_objection: 'Retention evidence is not yet measured.',
      conditions: [],
      critical_unknowns: ['Measured retention for the pilot cohort.'],
      change_my_mind: 'Evidence the binding constraint no longer holds.',
      challenges_answered: (input.challenges_for_seat || []).map((c) => c.crux_id),
      quotes: [],
      evidence_strength: 'medium',
      minority_position: null,
    };
  }
  process.stdout.write(JSON.stringify({
    result: JSON.stringify(card),
    session_id: 'harness-double-session',
    usage: { input_tokens: 11, output_tokens: 7 },
    modelUsage: { 'harness-reported-model': {} },
  }));
});
`;

function writeFakeHarness(home: string, rootName: string): void {
  mkdirSync(join(home, rootName), { recursive: true });
  const binDir = join(home, '.local', 'bin');
  mkdirSync(binDir, { recursive: true });
  const exe = join(binDir, rootName === '.claude-nine' ? 'claude-nine' : 'claude');
  writeFileSync(exe, FAKE_HARNESS_SCRIPT, 'utf8');
  chmodSync(exe, 0o755);
}

/** Loopback compatible-endpoint double, fed by the accepted fixture logic. */
async function startLoopbackDouble(): Promise<{ baseUrl: string; server: Server; calls: () => number }> {
  const fixture = new DeterministicFixtureTransport();
  let calls = 0;
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => {
      body += c;
    });
    req.on('end', async () => {
      calls += 1;
      const parsed = JSON.parse(body) as {
        model: string;
        messages: Array<{ role: string; content: string }>;
      };
      const system = parsed.messages[0].content;
      const input = JSON.parse(parsed.messages[1].content) as {
        seat_display_name: string;
      };
      const purpose = system.includes('one-seat consult')
        ? 'consult'
        : system.includes('ratification round')
          ? 'ratification'
          : 'advisor';
      const round = purpose === 'ratification' ? 3 : system.includes('focused challenge round') ? 2 : 1;
      const response = await fixture.generate({
        purpose: purpose as TransportRequest['purpose'],
        session_id: 'loopback-double',
        seat_id: SEAT_BY_DISPLAY_NAME[input.seat_display_name] as TransportRequest['seat_id'],
        round: round as TransportRequest['round'],
        route_id: 'loopback-configured',
        model_policy: {} as TransportRequest['model_policy'],
        system,
        input,
      });
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          id: 'chatcmpl-loopback-double',
          model: parsed.model,
          choices: [{ message: { role: 'assistant', content: response.text } }],
          usage: { prompt_tokens: 5, completion_tokens: 5 },
        }),
      );
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const port = typeof address === 'object' && address !== null ? address.port : 0;
  return { baseUrl: `http://127.0.0.1:${port}/v1`, server, calls: () => calls };
}

function writeOpenClawConfig(home: string, baseUrl: string): void {
  mkdirSync(join(home, '.openclaw'), { recursive: true });
  writeFileSync(
    join(home, '.openclaw', 'openclaw.json'),
    JSON.stringify({
      models: {
        providers: {
          loopback: {
            baseUrl,
            api: 'openai-completions',
            models: [{ id: 'loopback-model' }],
          },
        },
      },
    }),
    'utf8',
  );
}

function grantOverride(
  host: ReturnType<typeof createLocalHost>['host'],
  spec: Parameters<typeof buildTestGrant>[0],
  scope: Parameters<typeof buildTestGrant>[1],
): void {
  const grant = buildTestGrant(spec, scope);
  host.authorize = {
    async resolveRunGrant(ref: string, sessionId: string) {
      return ref === 'test-grant' && sessionId === spec.session_id ? grant : null;
    },
  };
}

test('rp0461 (a): a configured harness route composes the CWE-010 bridge transport and dispatches through the subprocess delegate', async () => {
  const home = makeHome('harness');
  writeFakeHarness(home, '.claude-nine');
  const { host, routeDiscovery } = createLocalHost({
    dataDir: tempDataDir('rp0461-harness'),
    homeDir: home,
    env: { PATH: '/usr/bin:/bin' },
  });
  const info = (routeDiscovery ?? []).find((r) => r.route_id === 'claude-nine-configured');
  assert.ok(info, 'the claude-nine harness route is discovered');
  assert.equal(info.composed, true);
  assert.equal(info.identity_level, 'configured');
  assert.equal(info.kind, 'harness');

  const transport = host.transportRegistry.resolve('claude-nine-configured');
  assert.ok(transport instanceof GuardedTransport, 'the registered transport is the CWE-010 guarded bridge transport');

  const sample = buildSampleSession();
  const response = await transport!.generate({
    purpose: 'advisor',
    session_id: sample.spec.session_id,
    seat_id: 'simon-sinek',
    round: 1,
    route_id: 'claude-nine-configured',
    model_policy: sample.spec.model_policy,
    system: 'You are an AI advisory perspective. This is the opening round.',
    input: {
      brief: sample.brief,
      seat_display_name: 'Simon Sinek',
      input_manifest_sha256: 'a'.repeat(64),
      pack_version: sample.spec.source_pack_version,
    },
  });
  const card = JSON.parse(response.text) as { seat_id: string; input_manifest_sha256: string };
  assert.equal(card.seat_id, 'simon-sinek');
  assert.equal(card.input_manifest_sha256, 'a'.repeat(64));
  assert.equal(response.provider_request_id, 'harness-double-session');
  assert.equal(response.reported_model_id, 'harness-reported-model');
});

test('rp0461 (b): a configured compatible-endpoint route composes the CWE-009 transport', async () => {
  const home = makeHome('compatible');
  const loopback = await startLoopbackDouble();
  try {
    writeOpenClawConfig(home, loopback.baseUrl);
    const { host, routeDiscovery } = createLocalHost({
      dataDir: tempDataDir('rp0461-compatible'),
      homeDir: home,
      env: { PATH: '/usr/bin:/bin' },
    });
    const info = (routeDiscovery ?? []).find((r) => r.route_id === 'loopback-configured');
    assert.ok(info, 'the configured provider route is discovered');
    assert.equal(info.composed, true);
    assert.equal(info.kind, 'compatible');
    const transport = host.transportRegistry.resolve('loopback-configured');
    assert.ok(
      transport instanceof CompatibleHttpTransport,
      'the registered transport is the CWE-009 compatible HTTP transport',
    );
  } finally {
    loopback.server.close();
  }
});

test('rp0461 (c): an unconfigured route still refuses COUNCIL_ROUTE_UNAVAILABLE', async () => {
  const home = makeHome('empty');
  const dataDir = tempDataDir('rp0461-unconfigured');
  const { host, routeDiscovery } = createLocalHost({
    dataDir,
    homeDir: home,
    env: { PATH: '' },
  });
  assert.deepEqual(routeDiscovery, []);
  assert.deepEqual(host.transportRegistry.listRoutes(), []);

  const sample = buildSampleSession();
  grantOverride(host, sample.spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ ...sample, sample: true });
  await assert.rejects(
    () => engine.startSession(sample.spec.session_id, 'test-grant'),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_ROUTE_UNAVAILABLE',
  );
  const session = await engine.getSession(sample.spec.session_id);
  assert.equal(session.state.state, 'DRAFT');
});

test('rp0461 (d): a full local session dispatches through the composed compatible path to a verdict, counted by the real ledger', async () => {
  const home = makeHome('session');
  const loopback = await startLoopbackDouble();
  try {
    writeOpenClawConfig(home, loopback.baseUrl);
    const dataDir = tempDataDir('rp0461-session');
    const { host } = createLocalHost({
      dataDir,
      homeDir: home,
      env: { PATH: '/usr/bin:/bin' },
    });
    const sample = buildSampleSession();
    const spec = JSON.parse(JSON.stringify(sample.spec)) as typeof sample.spec;
    // A session created against this route pins the route snapshot's
    // own model (the configuration's model), exactly as intake's
    // modelPolicyFromSnapshot would freeze it at creation.
    spec.model_policy.route_id = 'loopback-configured';
    spec.model_policy.requested_model_id = 'loopback-model';
    grantOverride(host, spec, sample.scope);
    const engine = new CouncilEngine(host);
    await engine.createSession({ spec, brief: sample.brief, scope: sample.scope });
    const completed = await engine.startSession(spec.session_id, 'test-grant');
    assert.equal(completed.state.state, 'COMPLETED');
    const verdict = await engine.getVerdict(spec.session_id);
    assert.ok(verdict, 'a verdict was produced through the composed path');
    assert.equal(verdict!.recommended_option_id, 'B');
    const byId = new Map(verdict!.option_scores.map((s) => [s.option_id, s]));
    assert.equal(byId.get('A')?.score, 6.0);
    assert.equal(byId.get('B')?.display_score, 7.6);
    assert.equal(byId.get('C')?.display_score, 6.6);
    // 27 provider requests: 9 seats x 3 rounds, counted once each by
    // the real budget ledger, and the loopback double saw exactly 27.
    const budget = host.budget.snapshot(spec.session_id);
    assert.equal(budget.consumed.provider_requests, 27);
    assert.equal(loopback.calls(), 27);
  } finally {
    loopback.server.close();
  }
});

test('rp0461 (e): no route is ever silently replaced', async () => {
  const home = makeHome('noreplace');
  writeFakeHarness(home, '.claude-nine');
  const dataDir = tempDataDir('rp0461-noreplace');
  const { host } = createLocalHost({
    dataDir,
    homeDir: home,
    env: { PATH: '/usr/bin:/bin' },
  });
  const sample = buildSampleSession();

  // (e1) The session pins claude-configured; only claude-nine-configured
  // is composed. The engine refuses rather than rerouting to the
  // available harness.
  const spec = JSON.parse(JSON.stringify(sample.spec)) as typeof sample.spec;
  spec.model_policy.route_id = 'claude-configured';
  grantOverride(host, spec, sample.scope);
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec, brief: sample.brief, scope: sample.scope });
  await assert.rejects(
    () => engine.startSession(spec.session_id, 'test-grant'),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_ROUTE_UNAVAILABLE',
  );

  // (e2) The guarded bridge transport refuses a request naming any
  // other route, before the delegate is reached.
  const guarded = host.transportRegistry.resolve('claude-nine-configured');
  assert.ok(guarded instanceof GuardedTransport);
  await assert.rejects(
    () =>
      guarded!.generate({
        purpose: 'advisor',
        session_id: sample.spec.session_id,
        seat_id: 'simon-sinek',
        round: 1,
        route_id: 'claude-configured',
        model_policy: sample.spec.model_policy,
        system: 'opening',
        input: {},
      }),
    (err: unknown) => err instanceof CouncilError && err.code === 'COUNCIL_ROUTE_UNAVAILABLE',
  );

  // (e3) The pinned CWE-009 transport refuses a request naming a
  // different route before any dispatch.
  const home2 = makeHome('noreplace2');
  const loopback = await startLoopbackDouble();
  try {
    writeOpenClawConfig(home2, loopback.baseUrl);
    const other = createLocalHost({
      dataDir: tempDataDir('rp0461-noreplace2'),
      homeDir: home2,
      env: { PATH: '/usr/bin:/bin' },
    });
    const pinned = other.host.transportRegistry.resolve('loopback-configured');
    assert.ok(pinned instanceof CompatibleHttpTransport);
    await assert.rejects(
      () =>
        pinned!.generate({
          purpose: 'advisor',
          session_id: sample.spec.session_id,
          seat_id: 'simon-sinek',
          round: 1,
          route_id: 'some-other-route',
          model_policy: sample.spec.model_policy,
          system: 'opening',
          input: {},
        }),
      (err: unknown) => err instanceof TransportError && err.code === 'TRANSPORT_ROUTE_MISMATCH',
    );
    assert.equal(loopback.calls(), 0, 'the refused request never reached the endpoint');
  } finally {
    loopback.server.close();
  }
});

test('rp0461: discovery is honest when a route cannot be composed, and the doctor and models surfaces say so', async () => {
  // Harness root exists but no executable anywhere: discovered, not composed.
  const home = makeHome('noexe');
  mkdirSync(join(home, '.claude-nine'), { recursive: true });
  const dataDir = tempDataDir('rp0461-noexe');
  const local = createLocalHost({
    dataDir,
    homeDir: home,
    env: { PATH: '' },
  });
  const info = (local.routeDiscovery ?? []).find((r) => r.route_id === 'claude-nine-configured');
  assert.ok(info);
  assert.equal(info!.composed, false);
  assert.ok(info!.not_composed_reason?.includes('no harness executable'));
  assert.equal(local.host.transportRegistry.resolve('claude-nine-configured'), null);

  // Doctor via the real dispatcher, with the discovery-scoped host:
  // not ready, naming the discovered-but-uncomposed route.
  const c = captureIo();
  const code = await runCli(['doctor', '--json', '--data-dir', dataDir], c.io, {
    createHost: (opts) => createLocalHost({ ...opts, homeDir: home, env: { PATH: '' } }),
  });
  assert.equal(code, 0);
  const doctor = JSON.parse(c.out()) as {
    checks: Array<{ name: string; ok: boolean; detail: string }>;
  };
  const live = doctor.checks.find((x) => x.name === 'live_routes_composed');
  assert.equal(live?.ok, false);
  assert.ok(live?.detail.includes('claude-nine-configured'));
  assert.ok(live?.detail.includes('discovered but none could be composed'));

  // Models lists the discovered route with its honest state.
  const m = captureIo();
  assert.equal(
    await runCli(['models', '--json', '--data-dir', dataDir], m.io, {
      createHost: (opts) => createLocalHost({ ...opts, homeDir: home, env: { PATH: '' } }),
    }),
    0,
  );
  const models = JSON.parse(m.out()) as {
    routes: string[];
    discovered: Array<{ route_id: string; composed: boolean; identity_level: string }>;
  };
  assert.deepEqual(models.routes, []);
  assert.equal(models.discovered.length, 1);
  assert.equal(models.discovered[0].route_id, 'claude-nine-configured');
  assert.equal(models.discovered[0].composed, false);
  assert.equal(models.discovered[0].identity_level, 'configured');
});

test('rp0461: doctor flips live_routes_composed to ready only when a transport is actually composed', async () => {
  const home = makeHome('doctor');
  writeFakeHarness(home, '.claude-nine');
  const dataDir = tempDataDir('rp0461-doctor');
  const c = captureIo();
  const code = await runCli(['doctor', '--json', '--data-dir', dataDir], c.io, {
    createHost: (opts) => createLocalHost({ ...opts, homeDir: home, env: { PATH: '/usr/bin:/bin' } }),
  });
  assert.equal(code, 0, c.err());
  const doctor = JSON.parse(c.out()) as {
    ok: boolean;
    checks: Array<{ name: string; ok: boolean; detail: string }>;
  };
  const live = doctor.checks.find((x) => x.name === 'live_routes_composed');
  assert.equal(live?.ok, true);
  assert.ok(live?.detail.includes('claude-nine-configured'));
});
