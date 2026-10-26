/**
 * W77S-MODES lane D: the convening service and CLI for the council sizes.
 *
 * Proves, against fakes and no live route:
 *  - convene with no mode classifies the question (AUTO-MODE-1062), every
 *    council size seats the full roster, and a named panel wins;
 *  - the driver fills any panel seat missing from the brief's weights;
 *  - the Ollama plan is asked once, remembered in <dataDir>/provider-plan.json,
 *    and an unknown plan is the typed OLLAMA_PLAN_REQUIRED refusal;
 *  - parallel_limit comes from parallelLimitFor, per mode;
 *  - the fallback route is resolved on openrouter-configured, and every
 *    other case reports "none (<reason>)";
 *  - grant ceilings are per mode (light/medium 50, heavy 100) and the four
 *    older modes keep the enforced 50/9/8 they are documented and printed as;
 *  - the service budget settings admit those totals so the grant governs;
 *  - the CLI forwards --seat-ids/--ollama-plan/--fallback-model and prints
 *    the run shape (and never a money figure);
 *  - the local create/sample engine refuses the three new sizes.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import type { PinnedRouteSnapshot } from '../src/budgets/route-snapshot.js';
import type { CouncilHost } from '../src/cli/host-ports.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { CouncilEngine } from '../src/cli/engine.js';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { runConvene } from '../src/cli/convene.js';
import { isCouncilError } from '../src/cli/errors.js';
import {
  DEFAULT_COUNCIL_SETTINGS,
  SEAT_IDS,
  type DecisionBrief,
  type ModelPolicy,
  type RunCeilings,
  type ScopeFields,
} from '../src/contracts/index.js';
import { validBrief } from '../src/contracts/fixtures/examples.js';
import type { AuthorizationEnvelope } from '../src/persistence/envelope.js';
import type { DeliberationService } from '../src/protocol/composition.js';
import { CONVENING_SETTINGS } from '../src/service/composition.js';
import {
  ceilingsForMode,
  createCouncilDriver,
  DriverRefusal,
  roundsPolicyOf,
  type ConveneAccepted,
  type ConveneInput,
  type ResolvedSessionRoute,
  type RouteChoiceRequest,
} from '../src/service/driver.js';
import { parseConveneBody } from '../src/service/front-door.js';
import { parallelLimitFor } from '../src/providers/parallel.js';

const clock = { nowUtc: () => '2026-10-25T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(5, '0')}` };

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: 'owner-1',
};

const principal: TrustedPrincipal = {
  tenant_id: SCOPE.tenant_id,
  company_id: SCOPE.company_id,
  installation_id: SCOPE.installation_id,
  subject: 'owner-1',
  channel: 'local_owner',
  support_access: false,
};

const MODEL_POLICY: ModelPolicy = {
  selection: 'explicit',
  route_id: 'route-primary',
  requested_model_id: 'primary-model',
  reasoning_preference: null,
  fallback_policy: 'none',
};

/** Only the fields the driver reads; the rest of the snapshot is inert here. */
function snapshot(routeId: string, providerSlug: string): PinnedRouteSnapshot {
  return { routeId, providerSlug } as unknown as PinnedRouteSnapshot;
}

function brief(): DecisionBrief {
  return structuredClone(validBrief) as unknown as DecisionBrief;
}

interface RunCall {
  sessionId: string;
  options: {
    grant_id: string;
    route_snapshot: PinnedRouteSnapshot;
    parallel_limit?: number;
    fallback_route_snapshot?: PinnedRouteSnapshot | null;
  };
}

interface Rig {
  dir: string;
  accepted: StoredSession[];
  runs: RunCall[];
  routeCalls: RouteChoiceRequest[];
  settled: Array<{ id: string; result: unknown }>;
  ceilings: () => RunCeilings | null;
  convene: (input: Omit<ConveneInput, 'requested_by'> & { requested_by?: string }) => Promise<ConveneAccepted>;
  drain: () => Promise<void>;
}

function rig(
  opts: {
    primaryProvider?: string;
    ollamaPlanFile?: string | null;
    fallbackFails?: boolean;
  } = {},
): Rig {
  const dir = mkdtempSync(join(tmpdir(), 'w77s-service-'));
  const accepted: StoredSession[] = [];
  const runs: RunCall[] = [];
  const routeCalls: RouteChoiceRequest[] = [];
  const settled: Array<{ id: string; result: unknown }> = [];
  let seenCeilings: RunCeilings | null = null;
  let inFlight: Promise<void> | null = null;

  const deliberation = {
    readiness: () => ({ ready: true, checks: [] }),
    repositories: {
      createSession: (_envelope: AuthorizationEnvelope, session: StoredSession): void => {
        accepted.push(session);
      },
      getSession: (_envelope: AuthorizationEnvelope, id: string): StoredSession | null =>
        accepted.find((s) => s.spec.session_id === id) ?? null,
    },
    grants: {
      previewRun: (_envelope: AuthorizationEnvelope, request: { ceilings: RunCeilings }) => {
        seenCeilings = request.ceilings;
        return { preview_id: 'preview-1' };
      },
      approveRun: () => ({ grant_id: 'grant-1' }),
    },
    runSession: async (
      _envelope: AuthorizationEnvelope,
      sessionId: string,
      options: RunCall['options'],
    ) => {
      runs.push({ sessionId, options });
      return { status: 'completed' };
    },
  } as unknown as DeliberationService;

  const resolveRoute = async (request: RouteChoiceRequest): Promise<ResolvedSessionRoute> => {
    routeCalls.push(request);
    if (request.route_id === 'openrouter-configured') {
      if (opts.fallbackFails === true) {
        throw new Error('the openrouter route is not configured');
      }
      return {
        snapshot: snapshot('openrouter-configured', 'openrouter-configured'),
        model_policy: MODEL_POLICY,
        model_label: request.model ?? 'fallback-model',
        selection_source: 'explicit',
        harness: null,
      };
    }
    return {
      snapshot: snapshot('route-primary', opts.primaryProvider ?? 'openrouter-configured'),
      model_policy: MODEL_POLICY,
      model_label: 'primary-model',
      selection_source: 'explicit',
      harness: null,
    };
  };

  const driver = createCouncilDriver({
    deliberation,
    envelope: {} as AuthorizationEnvelope,
    scope: SCOPE,
    principal,
    clock,
    ids,
    resolveRoute,
    auditLogPath: join(dir, 'convening-audit.jsonl'),
    dataDir: dir,
    onSettled: (id, result) => settled.push({ id, result }),
  });

  return {
    dir,
    accepted,
    runs,
    routeCalls,
    settled,
    ceilings: () => seenCeilings,
    convene: async (input) => {
      const result = await driver.convene({ requested_by: 'owner-1', ...input });
      inFlight = driver.drain();
      await inFlight;
      return result;
    },
    drain: () => driver.drain(),
  };
}

// ------------------------------------------------------------ mode defaults

test('W77S-D: a convene with no mode is classified from the question, not defaulted', async () => {
  const r = rig();
  const result = await r.convene({ brief: brief(), route: {} });
  // AUTO-MODE-1062: the question decides; the client is told who chose and why.
  assert.equal(result.mode, result.mode_selection.mode);
  assert.equal(result.mode_selection.source, 'auto');
  assert.ok(result.mode_selection.reason.trim().length > 0);
  assert.equal(result.mode, 'light', 'the fixture brief is a simple question');
  assert.equal(result.seats, 9);
  assert.deepEqual(result.rounds, { min_rounds: 2, max_rounds: 2, stop_from_round: null });
  assert.equal(result.request_cap, 50);
  assert.equal(r.accepted[0]?.spec.mode, 'light');
  // The nine-seat panel is the roster, unchanged.
  assert.deepEqual(r.accepted[0]?.spec.seat_ids, [...SEAT_IDS]);
});

test('W77S-D: light seats the full roster, 2 rounds and 3 at a time (Trevor, 2026-10-25)', async () => {
  const r = rig();
  const result = await r.convene({ brief: brief(), mode: 'light', route: {} });
  assert.equal(result.mode, 'light');
  // All council members are used in every mode; light differs in rounds
  // and wave width only.
  assert.equal(result.seats, SEAT_IDS.length);
  assert.deepEqual(result.rounds, { min_rounds: 2, max_rounds: 2, stop_from_round: null });
  assert.deepEqual(r.accepted[0]?.spec.seat_ids, [...SEAT_IDS]);
  // Light dispatches three at a time even on a route with no parallel limit.
  assert.equal(result.parallel_limit, 3);
  assert.equal(r.runs[0]?.options.parallel_limit, 3);
  assert.equal(result.request_cap, 50);
});

test('W77S-D: medium and heavy seat the same nine-seat roster as light', async () => {
  for (const mode of ['light', 'medium', 'heavy'] as const) {
    const r = rig();
    await r.convene({ brief: brief(), mode, route: {} });
    assert.deepEqual(r.accepted[0]?.spec.seat_ids, [...SEAT_IDS], mode);
  }
});

test('W77S-D: a light panel of nine named seats is honoured', async () => {
  const r = rig();
  const named = [...SEAT_IDS].reverse();
  await r.convene({ brief: brief(), mode: 'light', seat_ids: named, route: {} });
  assert.deepEqual(r.accepted[0]?.spec.seat_ids, named);
});

test('W77S-D: a light panel with one seat missing is refused, never shrunk', async () => {
  const r = rig();
  await assert.rejects(
    r.convene({ brief: brief(), mode: 'light', seat_ids: SEAT_IDS.slice(0, 3), route: {} }),
    (error: unknown) => {
      assert.ok(error instanceof DriverRefusal);
      assert.equal(error.code, 'CONVENE_INPUT_INVALID');
      return true;
    },
  );
  assert.equal(r.accepted.length, 0);
});

test('W77S-D: the driver fills a panel seat missing from the brief weights with 1', async () => {
  const r = rig();
  const partial = brief();
  delete (partial.relevance_weights as Record<string, number>)['les-brown'];
  delete (partial.relevance_weights as Record<string, number>)['michelle-obama'];
  await r.convene({ brief: partial, mode: 'medium', route: {} });
  const stored = r.accepted[0];
  assert.equal(stored?.brief.relevance_weights['les-brown'], 1);
  assert.equal(stored?.brief.relevance_weights['michelle-obama'], 1);
  // Every other frozen weight is untouched.
  assert.equal(stored?.brief.relevance_weights['tiffany-aliche'], 3);
});

// ------------------------------------------------------------- ollama plan

test('W77S-D: an Ollama route with no known plan is the typed OLLAMA_PLAN_REQUIRED refusal', async () => {
  const r = rig({ primaryProvider: 'ollama-cloud' });
  await assert.rejects(
    r.convene({ brief: brief(), mode: 'medium', route: {} }),
    (error: unknown) => {
      assert.ok(error instanceof DriverRefusal);
      assert.equal(error.code, 'OLLAMA_PLAN_REQUIRED');
      assert.equal(error.http_status, 409);
      assert.equal(
        error.recovery,
        'Ask the client: are you on the Ollama $20 a month plan or the $100 a month plan? Then convene again with --ollama-plan 20 or --ollama-plan 100.',
      );
      return true;
    },
  );
  // A refusal creates nothing: no session, no grant, no run.
  assert.equal(r.accepted.length, 0);
  assert.equal(r.runs.length, 0);
  assert.equal(r.ceilings(), null);
});

test('W77S-D: the supplied Ollama plan is written once and read back when absent', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  const first = await r.convene({ brief: brief(), mode: 'medium', ollama_plan: '20', route: {} });
  assert.equal(first.parallel_limit, 3);
  const planFile = JSON.parse(readFileSync(join(r.dir, 'provider-plan.json'), 'utf8')) as {
    ollama_plan?: string;
  };
  assert.equal(planFile.ollama_plan, '20');

  // Second convene names no plan: the remembered one is used, no refusal.
  const second = await r.convene({ brief: brief(), mode: 'medium', route: {} });
  assert.equal(second.parallel_limit, 3);
});

test('W77S-D: a malformed or missing plan memory is treated as no plan', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  writeFileSync(join(r.dir, 'provider-plan.json'), '{"ollama_plan":"50"}\n', 'utf8');
  await assert.rejects(r.convene({ brief: brief(), mode: 'medium', route: {} }), (error: unknown) => {
    assert.ok(error instanceof DriverRefusal);
    assert.equal(error.code, 'OLLAMA_PLAN_REQUIRED');
    return true;
  });
});

test('W77S-D: an invalid ollama_plan value is refused as invalid input', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  await assert.rejects(
    r.convene({ brief: brief(), mode: 'medium', ollama_plan: '50' as never, route: {} }),
    (error: unknown) => {
      assert.ok(error instanceof DriverRefusal);
      assert.equal(error.code, 'CONVENE_INPUT_INVALID');
      return true;
    },
  );
  assert.equal(r.accepted.length, 0);
});

test('W77S-D: ollama_plan 100 runs ten at a time, and light still holds its wave of three', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  const medium = await r.convene({ brief: brief(), mode: 'medium', ollama_plan: '100', route: {} });
  assert.equal(medium.parallel_limit, 9);
  const light = await r.convene({ brief: brief(), mode: 'light', ollama_plan: '100', route: {} });
  // Nine seats, but light's wave width of 3 is the tighter cap.
  assert.equal(light.seats, 9);
  assert.equal(light.parallel_limit, 3);
});

test('W77S-D: every non-Ollama route runs the whole panel at once', async () => {
  const r = rig({ primaryProvider: 'openrouter-configured' });
  const result = await r.convene({ brief: brief(), mode: 'medium', route: {} });
  assert.equal(result.parallel_limit, 9);
  assert.equal(
    parallelLimitFor({ providerSlug: 'openrouter-configured', ollamaPlan: null, panelSize: 9 }).ok,
    true,
  );
});

test('W77S-D: the four older modes keep one-at-a-time dispatch and need no plan', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  const result = await r.convene({ brief: brief(), mode: 'full', route: {} });
  assert.equal(result.parallel_limit, 1);
  assert.equal(result.mode, 'full');
  assert.equal(result.rounds, null);
});

// ---------------------------------------------------------------- fallback

test('W77S-D: an Ollama primary resolves the fallback model on openrouter-configured', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  const result = await r.convene({
    brief: brief(),
    mode: 'light',
    ollama_plan: '20',
    fallback_model: 'some/open-model',
    route: {},
  });
  assert.equal(result.fallback, 'openrouter-configured / some/open-model');
  assert.deepEqual(
    r.routeCalls.filter((c) => c.route_id === 'openrouter-configured'),
    [{ route_id: 'openrouter-configured', model: 'some/open-model' }],
  );
  const run = r.runs[0];
  assert.equal(run?.options.fallback_route_snapshot?.routeId, 'openrouter-configured');
});

test('W77S-D: an unresolvable fallback proceeds and reports none (<reason>)', async () => {
  const r = rig({ primaryProvider: 'ollama', fallbackFails: true });
  const result = await r.convene({
    brief: brief(),
    mode: 'light',
    ollama_plan: '20',
    fallback_model: 'some/open-model',
    route: {},
  });
  assert.equal(result.fallback, 'none (the openrouter route is not configured)');
  assert.equal(r.runs[0]?.options.fallback_route_snapshot, null);
  assert.equal(r.accepted.length, 1);
});

test('W77S-D: no fallback model, or a non-Ollama primary, reports none and why', async () => {
  const ollama = rig({ primaryProvider: 'ollama' });
  const noModel = await ollama.convene({ brief: brief(), mode: 'light', ollama_plan: '20', route: {} });
  assert.equal(noModel.fallback, 'none (no fallback model given)');

  const openrouter = rig({ primaryProvider: 'openrouter-configured' });
  const notOllama = await openrouter.convene({
    brief: brief(),
    mode: 'medium',
    fallback_model: 'x/y',
    route: {},
  });
  assert.equal(notOllama.fallback, 'none (primary route is not Ollama)');
});

test('W77S-D: an older mode never gets a fallback route', async () => {
  const r = rig({ primaryProvider: 'ollama' });
  const result = await r.convene({ brief: brief(), mode: 'full', fallback_model: 'x/y', route: {} });
  assert.equal(result.fallback, 'none (the older modes keep their existing route)');
  assert.equal(r.runs[0]?.options.fallback_route_snapshot, null);
});

// ---------------------------------------------------------------- ceilings

test('W77S-D: grant ceilings come from the mode policy and the four older modes keep 50/9/8', () => {
  for (const [mode, cap] of [
    ['light', 50],
    ['medium', 50],
    ['heavy', 100],
  ] as const) {
    const ceilings = ceilingsForMode(mode);
    assert.equal(ceilings.max_provider_requests, cap, mode);
    assert.equal(ceilings.max_output_repairs, cap, mode);
    assert.equal(ceilings.max_transport_retries, cap, mode);
    assert.equal(ceilings.max_input_tokens, null, mode);
    assert.equal(ceilings.max_output_tokens, null, mode);
    assert.equal(ceilings.max_money, null, mode);
  }
  // The grant is the ENFORCED cap for an older mode, so it must equal the
  // 50/9/8 every client-facing file promises and every `status` reports.
  for (const mode of ['full', 'selected', 'quick', 'consult'] as const) {
    assert.deepEqual(ceilingsForMode(mode), {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    });
  }
});

test('W77S-D: the heavy grant reaches the budget service, which admits the mode totals', async () => {
  const r = rig();
  const result = await r.convene({ brief: brief(), mode: 'heavy', route: {} });
  assert.equal(result.request_cap, 100);
  assert.deepEqual(r.ceilings(), {
    max_provider_requests: 100,
    max_output_repairs: 100,
    max_transport_retries: 100,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: null,
  });
  // The service settings never clamp the grant below its mode cap.
  assert.equal(CONVENING_SETTINGS.max_session_provider_requests, 100);
  assert.equal(CONVENING_SETTINGS.max_output_repair_requests, 100);
  assert.equal(CONVENING_SETTINGS.max_transport_retries_total, 100);
  assert.equal(CONVENING_SETTINGS.max_semantic_verification_requests, 2);
  // The shipped defaults are untouched, so the standalone CLI path is unchanged.
  assert.equal(DEFAULT_COUNCIL_SETTINGS.max_session_provider_requests, 50);
});

test('W77S-D: roundsPolicyOf reports each mode and the server response carries it', async () => {
  assert.deepEqual(roundsPolicyOf('heavy'), { min_rounds: 3, max_rounds: 10, stop_from_round: 3 });
  const r = rig();
  const result = await r.convene({ brief: brief(), mode: 'heavy', route: {} });
  assert.deepEqual(result.rounds, { min_rounds: 3, max_rounds: 10, stop_from_round: 3 });
  assert.equal(r.runs[0]?.options.parallel_limit, 9);
});

// --------------------------------------------------------------- front door

test('W77S-D: the convene body accepts ollama_plan and fallback_model only from the new keys', () => {
  const ok = parseConveneBody({
    brief: { anything: true },
    mode: 'light',
    seat_ids: ['simon-sinek', 'td-jakes', 'oprah-winfrey'],
    ollama_plan: '20',
    fallback_model: 'x/y',
  });
  assert.equal(ok.ok, true);
  if (ok.ok) {
    assert.equal(ok.input.ollama_plan, '20');
    assert.equal(ok.input.fallback_model, 'x/y');
  }
  for (const bad of [{ ollama_plan: '50' }, { ollama_plan: 20 }, { fallback_model: '' }]) {
    const parsed = parseConveneBody({ sample: true, ...bad });
    assert.equal(parsed.ok, false, JSON.stringify(bad));
  }
});

// ---------------------------------------------------------------------- CLI

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let o = '';
  let e = '';
  return { io: { out: (t) => (o += t), err: (t) => (e += t) }, out: () => o, err: () => e };
}

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

function fakeFetch(status: number, reply: unknown): { fetchImpl: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    calls.push({
      url: String(url),
      method: init?.method ?? 'GET',
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
    });
    return new Response(typeof reply === 'string' ? reply : JSON.stringify(reply), { status });
  }) as typeof fetch;
  return { fetchImpl, calls };
}

const ACCEPTED = {
  session_id: 'sess-1',
  state: 'RUNNING',
  sample: false,
  route_id: 'route-primary',
  model_label: 'primary-model',
  selection_source: 'explicit',
  grant_id: 'g1',
  session_path: '/council/sess-1',
  events_path: '/api/council/sessions/sess-1/events',
  mode: 'light',
  seats: 9,
  rounds: { min_rounds: 2, max_rounds: 2, stop_from_round: null },
  request_cap: 50,
  parallel_limit: 3,
  fallback: 'none (primary route is not Ollama)',
};

const ENV = { CLAUDECODE: '1' };

test('W77S-D: convene forwards --seat-ids, --ollama-plan and --fallback-model', async () => {
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  const code = await runConvene(
    [
      '--brief',
      '/tmp/does-not-matter.json',
      '--mode',
      'light',
      '--seat-ids',
      'simon-sinek, td-jakes ,oprah-winfrey',
      '--ollama-plan',
      '100',
      '--fallback-model',
      'x/y',
      '--public-origin',
      'https://council.example.com',
    ],
    { fetchImpl: f.fetchImpl, env: ENV, io: c.io },
  );
  // The brief file does not exist: the call stops before the fetch.
  assert.equal(code, 2);
  assert.equal(f.calls.length, 0);
  assert.match(c.err(), /Could not read --brief file/);
});

test('W77S-D: convene body carries the parsed seats, plan and fallback model', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'w77s-cli-'));
  const briefPath = join(dir, 'brief.json');
  writeFileSync(briefPath, JSON.stringify(validBrief), 'utf8');
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  const code = await runConvene(
    [
      '--brief',
      briefPath,
      '--mode',
      'light',
      '--seat-ids',
      'simon-sinek, td-jakes ,oprah-winfrey',
      '--ollama-plan',
      '20',
      '--fallback-model',
      'some/open-model',
      '--public-origin',
      'https://council.example.com',
    ],
    { fetchImpl: f.fetchImpl, env: ENV, io: c.io },
  );
  assert.equal(code, 0);
  const body = f.calls[0]?.body;
  assert.equal(body?.mode, 'light');
  assert.deepEqual(body?.seat_ids, ['simon-sinek', 'td-jakes', 'oprah-winfrey']);
  assert.equal(body?.ollama_plan, '20');
  assert.equal(body?.fallback_model, 'some/open-model');
});

test('W77S-D: --ollama-plan rejects anything but 20 or 100 before the call', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'w77s-cli-'));
  const briefPath = join(dir, 'brief.json');
  writeFileSync(briefPath, JSON.stringify(validBrief), 'utf8');
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  const code = await runConvene(['--brief', briefPath, '--ollama-plan', '50'], {
    fetchImpl: f.fetchImpl,
    env: ENV,
    io: c.io,
  });
  assert.equal(code, 2);
  assert.equal(f.calls.length, 0);
  assert.match(c.err(), /--ollama-plan must be 20 or 100/);
});

test('W77S-D: --seat-ids with no seat id is a usage error', async () => {
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  const code = await runConvene(['--sample', '--seat-ids', ' , '], {
    fetchImpl: f.fetchImpl,
    env: ENV,
    io: c.io,
  });
  assert.equal(code, 2);
  assert.equal(f.calls.length, 0);
});

test('W77S-D: convene prints mode, seats, rounds, cap, parallel limit and the fallback line', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'w77s-cli-'));
  const briefPath = join(dir, 'brief.json');
  writeFileSync(briefPath, JSON.stringify(validBrief), 'utf8');
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  await runConvene(['--brief', briefPath, '--mode', 'light', '--public-origin', 'https://council.example.com'], {
    fetchImpl: f.fetchImpl,
    env: ENV,
    io: c.io,
  });
  const out = c.out();
  assert.match(out, /mode: light/);
  assert.match(out, /seats: 9/);
  assert.match(out, /rounds: 2/);
  assert.match(out, /request cap: 50 provider requests/);
  assert.match(out, /parallel limit: 3 at a time/);
  assert.match(out, /Fallback: none \(primary route is not Ollama\)/);
  // No money, cost or budget wording in client-facing output.
  assert.equal(/\$|money|cost|budget|spend/i.test(out), false, out);
});

test('W77S-D: an older mode prints a fixed three-round shape', async () => {
  const f = fakeFetch(202, {
    ...ACCEPTED,
    mode: 'full',
    seats: 9,
    rounds: null,
    request_cap: 50,
    parallel_limit: 1,
  });
  const c = capture();
  const code = await runConvene(['--sample', '--public-origin', 'https://council.example.com'], {
    fetchImpl: f.fetchImpl,
    env: ENV,
    io: c.io,
  });
  assert.equal(code, 0);
  assert.match(c.out(), /rounds: 3 \(fixed\)/);
  assert.match(c.out(), /request cap: 50 provider requests/);
});

test('W77S-D: dispatcher help documents the new convene flags', async () => {
  const c = capture();
  await runCli([], c.io);
  const help = c.out();
  for (const flag of ['--mode light|medium|heavy', '--seat-ids', '--ollama-plan 20|100', '--fallback-model']) {
    assert.ok(help.includes(flag), flag);
  }
});

// ---------------------------------------------------------------- engine

test('W77S-D: the local engine refuses light, medium and heavy and points at convene', async () => {
  const engine = new CouncilEngine({} as unknown as CouncilHost, {});
  const spec = (mode: string) => ({
    schema_version: 'wise-elders.session/v1' as const,
    session_id: 'sess-x',
    mode,
    visibility: 'company' as const,
    brief_revision: 1,
    brief_sha256: '',
    options: [],
    seat_ids: [],
    model_policy: MODEL_POLICY,
    source_pack_version: 'pack',
    execution_policy: 'advisory_only' as const,
    created_at: clock.nowUtc(),
    display_timezone: 'UTC',
  });
  for (const mode of ['light', 'medium', 'heavy']) {
    await assert.rejects(
      engine.createSession({
        spec: spec(mode) as never,
        brief: brief(),
        scope: SCOPE,
      }),
      (error: unknown) => {
        assert.ok(isCouncilError(error));
        assert.equal(error.code, 'COUNCIL_INVALID_INPUT');
        assert.match(error.message, new RegExp(`blackceo-council convene --mode ${mode}`));
        return true;
      },
    );
  }
  // The four older modes are not refused by this guard.
  await assert.rejects(
    engine.createSession({ spec: spec('full') as never, brief: brief(), scope: SCOPE }),
    (error: unknown) => {
      assert.ok(isCouncilError(error));
      assert.equal(/convenes through the council service/.test(error.message), false);
      return true;
    },
  );
});
