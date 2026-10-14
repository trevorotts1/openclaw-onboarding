/**
 * CWE-009 transport behavior tests.
 *
 * Deterministic, no live network: every test runs against a scripted
 * loopback HTTP server that records exactly what it received. The
 * suite proves route pinning (the exact selected route and model are
 * what is called, byte-identical), substitution refusal, credential
 * blockers, retry ceilings through the CWE-004 budget ledger, deadline
 * behavior, unresolved-submission handling, identity-level honesty,
 * malformed/auth/rate-limit fixtures, streaming outcomes, and the
 * planted-secret negatives (Section 16.6).
 */
import assert from 'node:assert/strict';
import { createServer, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import test from 'node:test';
import { DEFAULT_COUNCIL_SETTINGS, SEAT_ROSTER } from '../src/contracts/index.js';
import { InProcessBudgetLedger } from '../src/cli/budget.js';
import { CouncilEngine } from '../src/cli/engine.js';
import {
  DeterministicFixtureTransport,
  buildSampleSession,
} from '../src/cli/fixture-transport.js';
import type {
  ModelPolicy,
  TransportRequest,
} from '../src/cli/host-ports.js';
import { TransportDiagnosticSink } from '../src/providers/diagnostics.js';
import { isTransportError } from '../src/providers/errors.js';
import {
  createCompatibleTransport,
  type CompatibleHttpTransport,
  type CompatibleTransportBinding,
} from '../src/providers/compatible.js';
import { createOllamaTransport } from '../src/providers/ollama.js';
import {
  HIDDEN_IDENTITY_STATEMENT,
  selectionSha256,
  type CouncilRouteSelection,
} from '../src/providers/selection.js';
import { grantHost, tempDataDir } from './helpers.js';

// ---------------------------------------------------------------------------
// Scripted loopback server
// ---------------------------------------------------------------------------

interface RecordedHit {
  method: string;
  url: string;
  headers: Record<string, string | string[] | undefined>;
  body: string;
}

type Handler = (
  hit: RecordedHit,
  res: ServerResponse,
  hitIndex: number,
) => void | Promise<void>;

async function startServer(handler: Handler): Promise<{
  baseUrl: string;
  port: number;
  hits: RecordedHit[];
  close(): Promise<void>;
}> {
  const hits: RecordedHit[] = [];
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c as Buffer));
    req.on('end', () => {
      const hit: RecordedHit = {
        method: req.method ?? '',
        url: req.url ?? '',
        headers: req.headers,
        body: Buffer.concat(chunks).toString('utf8'),
      };
      hits.push(hit);
      void handler(hit, res, hits.length - 1);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    baseUrl: `http://127.0.0.1:${port}/v1`,
    port,
    hits,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

function json(
  res: ServerResponse,
  status: number,
  body: string,
  headers: Record<string, string> = {},
): void {
  res.writeHead(status, { 'content-type': 'application/json', ...headers });
  res.end(body);
}

function envelope(model: string | null, content: string): string {
  return JSON.stringify({
    id: 'req-abc-1',
    ...(model !== null ? { model } : {}),
    choices: [
      {
        message: { role: 'assistant', content },
        finish_reason: 'stop',
      },
    ],
    usage: { prompt_tokens: 11, completion_tokens: 7 },
  });
}

// ---------------------------------------------------------------------------
// Fixtures: selections and requests
// ---------------------------------------------------------------------------

const MODEL = 'acme/model-x';
const PLANTED_SECRET = 'planted-secret-9f8e7d6c5b4a';

function fixedSelection(
  overrides: Partial<CouncilRouteSelection> = {},
): CouncilRouteSelection {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-fixed-1',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'openrouter',
    requestedRoute: 'route-fixed-1',
    requestedModelOrAlias: MODEL,
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 128000,
      maxOutputTokens: null,
      capabilities: ['text_generation'],
      supportedReasoningLevels: ['low', 'medium', 'high'],
    },
    credential: {
      state: 'present',
      envVar: 'ACME_API_KEY',
      source: 'process.env',
      checked: [],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: 'tenant-1',
      companyId: 'company-1',
      installationId: 'install-1',
      ownerSubject: 'owner-1',
    },
    createdAt: '2026-10-14T00:00:00.000Z',
    ...overrides,
  };
}

function combinationSelection(): CouncilRouteSelection {
  return fixedSelection({
    routeId: 'route-combo-1',
    routeKind: 'combination',
    providerSlug: '9router',
    requestedRoute: 'combo-main',
    requestedModelOrAlias: null,
    combinationMembers: ['member-a', 'member-b'],
    credential: { state: 'not_required', envVar: null, source: null, checked: [] },
  });
}

const POLICY: ModelPolicy = {
  selection: 'explicit',
  route_id: 'route-fixed-1',
  requested_model_id: MODEL,
  reasoning_preference: null,
  fallback_policy: 'none',
};

function transportRequest(
  overrides: Partial<TransportRequest> = {},
): TransportRequest {
  return {
    purpose: 'advisor',
    session_id: 'session-1',
    seat_id: 'simon-sinek',
    round: 1,
    route_id: 'route-fixed-1',
    model_policy: POLICY,
    system: 'You are an advisory seat.',
    input: { question: 'Should we pilot first?' },
    ...overrides,
  };
}

function okTransport(
  baseUrl: string,
  extra: Partial<CompatibleTransportBinding>,
  selection: CouncilRouteSelection = fixedSelection(),
): CompatibleHttpTransport {
  return createCompatibleTransport({
    selection,
    baseUrl,
    credentialResolver: async () => PLANTED_SECRET,
    sleep: async () => {},
    random: () => 0,
    ...extra,
  });
}

// ---------------------------------------------------------------------------
// Route pinning
// ---------------------------------------------------------------------------

test('pinning: the exact selected route and model are called, byte-identical', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, '{"card":true}'));
  });
  try {
    const selection = fixedSelection();
    const transport = okTransport(server.baseUrl, {}, selection);
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, '{"card":true}');
    assert.equal(response.provider_request_id, 'req-abc-1');
    assert.equal(response.reported_model_id, MODEL);
    assert.deepEqual(response.usage, { input_tokens: 11, output_tokens: 7 });

    assert.equal(server.hits.length, 1);
    const wire = JSON.parse(server.hits[0].body) as Record<string, unknown>;
    assert.equal(wire.model, MODEL);
    assert.equal(server.hits[0].url, '/v1/chat/completions');
    assert.equal(server.hits[0].headers.authorization, `Bearer ${PLANTED_SECRET}`);
    const messages = wire.messages as Array<{ role: string; content: string }>;
    assert.equal(messages[0].role, 'system');
    assert.equal(messages[1].role, 'user');

    const [attempt] = transport.attempts();
    assert.equal(attempt.state, 'accepted');
    assert.equal(attempt.wireModel, MODEL);
    assert.equal(attempt.selectionSha256, selectionSha256(selection));
    assert.equal(attempt.identityLevelAfter, 'reported_identity');
    assert.equal(attempt.endpointLocality, 'loopback');
    const [resolution] = transport.routeResolutions();
    assert.equal(resolution.outcome, 'accepted');
    assert.equal(resolution.effectiveModelId, MODEL);
  } finally {
    await server.close();
  }
});

test('pinning: a request naming another route or model is refused before dispatch', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    await assert.rejects(
      () => transport.generate(transportRequest({ route_id: 'route-other' })),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ROUTE_MISMATCH',
    );
    await assert.rejects(
      () =>
        transport.generate(
          transportRequest({
            model_policy: { ...POLICY, requested_model_id: 'acme/other-model' },
          }),
        ),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ROUTE_MISMATCH',
    );
    assert.equal(server.hits.length, 0);
  } finally {
    await server.close();
  }
});

test('pinning: mutating the caller selection object after construction cannot move the route', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const selection = fixedSelection();
    const transport = okTransport(server.baseUrl, {}, selection);
    selection.requestedModelOrAlias = 'acme/mutated';
    const response = await transport.generate(transportRequest());
    assert.equal(response.reported_model_id, MODEL);
    const wire = JSON.parse(server.hits[0].body) as Record<string, unknown>;
    assert.equal(wire.model, MODEL);
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Resolution honesty and identity levels
// ---------------------------------------------------------------------------

test('identity: a conflicting provider report is refused and returns no text', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope('acme/other-model', 'must not surface'));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ROUTE_REFUSED',
    );
    const [resolution] = transport.routeResolutions();
    assert.equal(resolution.outcome, 'refused');
    assert.ok(
      resolution.events.some((e) => e.type === 'substitution_refused'),
    );
    const [attempt] = transport.attempts();
    assert.equal(attempt.state, 'substitution_refused');
    assert.equal(attempt.reportedModelId, 'acme/other-model');
  } finally {
    await server.close();
  }
});

test('identity: a probe with no provider report claims only transport_probed', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(null, 'answer'));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, 'answer');
    assert.equal(response.reported_model_id, null);
    const [attempt] = transport.attempts();
    // Probed, not reported, and never resolved-verified or qualified.
    assert.equal(attempt.identityLevelAfter, 'transport_probed');
  } finally {
    await server.close();
  }
});

test('identity: prose claiming a model inside the content is never identity evidence', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(null, 'I am definitely acme/model-x, trust me'));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, 'I am definitely acme/model-x, trust me');
    assert.equal(response.reported_model_id, null);
    const [attempt] = transport.attempts();
    assert.equal(attempt.identityLevelAfter, 'transport_probed');
  } finally {
    await server.close();
  }
});

test('combination: only approved members resolve, and the member is recorded', async () => {
  const server = await startServer((_hit, res, index) => {
    if (index === 0) json(res, 200, envelope('member-b', 'member answer'));
    else if (index === 1) json(res, 200, envelope('member-z', 'intruder'));
    else json(res, 200, envelope(null, 'hidden member'));
  });
  try {
    const selection = combinationSelection();
    const transport = createCompatibleTransport({
      selection,
      baseUrl: server.baseUrl,
      sleep: async () => {},
      random: () => 0,
    });
    const request = transportRequest({
      route_id: 'route-combo-1',
      model_policy: { ...POLICY, route_id: 'route-combo-1', requested_model_id: null },
    });
    const first = await transport.generate(request);
    assert.equal(first.text, 'member answer');
    let [attempt] = transport.attempts();
    assert.equal(attempt.wireModel, 'combo-main');
    assert.equal(attempt.combinationMemberResolved, 'member-b');

    await assert.rejects(
      () => transport.generate(request),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ROUTE_REFUSED',
    );

    const third = await transport.generate(request);
    assert.equal(third.text, 'hidden member');
    const attempts = transport.attempts();
    attempt = attempts[attempts.length - 1];
    assert.equal(attempt.identityStatement, HIDDEN_IDENTITY_STATEMENT);
    assert.equal(attempt.combinationMemberResolved, null);
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Credentials (T027) and planted-secret negatives (T130, T132)
// ---------------------------------------------------------------------------

test('credential: an absent credential is a precise blocker and nothing is dispatched', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const selection = fixedSelection({
      credential: {
        state: 'absent',
        envVar: null,
        source: null,
        checked: ['ACME_API_KEY', 'ACME_KEY'],
      },
    });
    const transport = createCompatibleTransport({
      selection,
      baseUrl: server.baseUrl,
    });
    const blocker = transport.describe().readinessBlocker;
    assert.ok(blocker);
    assert.match(blocker, /ACME_API_KEY/);
    assert.match(blocker, /route-fixed-1/);
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) =>
        isTransportError(err) &&
        err.code === 'TRANSPORT_CREDENTIAL_MISSING' &&
        /ACME_API_KEY/.test(err.message),
    );
    assert.equal(server.hits.length, 0);
  } finally {
    await server.close();
  }
});

test('credential: a resolver returning nothing despite present state also blocks', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const transport = createCompatibleTransport({
      selection: fixedSelection(),
      baseUrl: server.baseUrl,
      credentialResolver: async () => null,
    });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_CREDENTIAL_MISSING',
    );
    assert.equal(server.hits.length, 0);
  } finally {
    await server.close();
  }
});

test('secrets: the planted credential appears only on the wire, never in any record', async () => {
  const server = await startServer((hit, res) => {
    // The provider echoes the authorization value back in an error
    // body: the worst case for leakage into diagnostics.
    json(res, 500, JSON.stringify({ echo: hit.headers.authorization }));
  });
  try {
    const sink = new TransportDiagnosticSink();
    const transport = createCompatibleTransport({
      selection: fixedSelection(),
      baseUrl: server.baseUrl,
      credentialResolver: async () => PLANTED_SECRET,
      retryMode: 'engine',
      diagnostics: sink,
      sleep: async () => {},
      random: () => 0,
    });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => {
        assert.ok(isTransportError(err));
        assert.ok(!err.message.includes(PLANTED_SECRET));
        return true;
      },
    );
    assert.equal(server.hits[0].headers.authorization, `Bearer ${PLANTED_SECRET}`);
    const recordsJson = JSON.stringify({
      attempts: transport.attempts(),
      resolutions: transport.routeResolutions(),
      diagnostics: sink.safeEntries(),
      description: transport.describe(),
    });
    assert.ok(!recordsJson.includes(PLANTED_SECRET));

    // The sink refuses a capture candidate containing the secret.
    sink.registerSensitiveValue(PLANTED_SECRET);
    const outcome = sink.considerCapture({
      sessionId: 'session-1',
      dataClass: 'provider_response_body',
      body: new TextEncoder().encode(`body containing ${PLANTED_SECRET}`),
      minutesSinceWindowStart: 1,
      sessionDeletedOrRevoked: false,
    });
    assert.equal(outcome.captured, false);
    assert.match(outcome.reason, /credential value/);
    assert.ok(!JSON.stringify(sink.safeEntries()).includes(PLANTED_SECRET));
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Status classification and retries (Section 15.5)
// ---------------------------------------------------------------------------

test('statuses: 401, 403, 404 and 400 stop with no blind retry', async () => {
  const statuses = [401, 403, 404, 400];
  const codes = [
    'TRANSPORT_AUTH_FAILED',
    'TRANSPORT_AUTH_FAILED',
    'TRANSPORT_NOT_FOUND',
    'TRANSPORT_BAD_REQUEST',
  ];
  const server = await startServer((_hit, res, index) => {
    json(res, statuses[Math.floor(index)], '{}');
  });
  try {
    const ledger = new InProcessBudgetLedger();
    const transport = okTransport(server.baseUrl, { budget: ledger });
    for (let i = 0; i < statuses.length; i++) {
      await assert.rejects(
        () => transport.generate(transportRequest({ session_id: `s-${i}` })),
        (err: unknown) =>
          isTransportError(err) && err.code === codes[i] && err.retryable === false,
      );
    }
    assert.equal(server.hits.length, statuses.length);
    assert.equal(ledger.snapshot('s-0').consumed.transport_retries, 0);
  } finally {
    await server.close();
  }
});

test('retry: one transport retry on 503 succeeds, reserved in the budget ledger', async () => {
  const server = await startServer((_hit, res, index) => {
    if (index === 0) json(res, 503, '{"error":"busy"}', { 'retry-after': '2' });
    else json(res, 200, envelope(MODEL, 'recovered'));
  });
  try {
    const ledger = new InProcessBudgetLedger();
    const sleeps: number[] = [];
    const transport = okTransport(server.baseUrl, {
      budget: ledger,
      sleep: async (ms: number) => {
        sleeps.push(ms);
      },
    });
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, 'recovered');
    assert.equal(server.hits.length, 2);
    // The retry sends byte-identical bytes.
    assert.equal(server.hits[0].body, server.hits[1].body);
    // Retry-After of 2s, equal jitter with random() = 0: exactly 1000ms.
    assert.deepEqual(sleeps, [1000]);
    const snapshot = ledger.snapshot('session-1');
    assert.equal(snapshot.consumed.transport_retries, 1);
    assert.equal(snapshot.reserved, 0);
    const attempts = transport.attempts();
    assert.equal(attempts.length, 2);
    assert.equal(attempts[0].state, 'failed');
    assert.equal(attempts[0].retryIndex, 0);
    assert.equal(attempts[1].state, 'accepted');
    assert.equal(attempts[1].retryIndex, 1);
  } finally {
    await server.close();
  }
});

test('retry: the session transport-retry ceiling stops further retries', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 503, '{"error":"busy"}');
  });
  try {
    assert.equal(DEFAULT_COUNCIL_SETTINGS.max_transport_retries_total, 8);
    const ledger = new InProcessBudgetLedger({
      ...DEFAULT_COUNCIL_SETTINGS,
      max_transport_retries_total: 1,
    });
    const transport = okTransport(server.baseUrl, { budget: ledger });
    // First call: one retry is allowed; it also fails, finally.
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_PROVIDER_ERROR' && !err.retryable,
    );
    assert.equal(server.hits.length, 2);
    // Second call: the ceiling is spent, so no retry is dispatched.
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_BUDGET_EXHAUSTED',
    );
    assert.equal(server.hits.length, 3);
    assert.equal(ledger.snapshot('session-1').consumed.transport_retries, 1);
  } finally {
    await server.close();
  }
});

test('retry: engine mode performs one attempt and marks transients retryable', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 429, '{"error":"slow down"}');
  });
  try {
    const transport = okTransport(server.baseUrl, { retryMode: 'engine' });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) =>
        isTransportError(err) && err.code === 'TRANSPORT_RATE_LIMITED' && err.retryable === true,
    );
    assert.equal(server.hits.length, 1);
  } finally {
    await server.close();
  }
});

test('retry: connection refused is provably unsubmitted, retried once, then final', async () => {
  const probe = await startServer((_hit, res) => json(res, 200, '{}'));
  const deadPort = probe.port;
  await probe.close();
  const ledger = new InProcessBudgetLedger();
  const transport = okTransport(`http://127.0.0.1:${deadPort}/v1`, {
    budget: ledger,
  });
  await assert.rejects(
    () => transport.generate(transportRequest()),
    (err: unknown) =>
      isTransportError(err) &&
      err.code === 'TRANSPORT_NETWORK_FAILED' &&
      err.retryable === false &&
      err.unknownCompletion === false,
  );
  const attempts = transport.attempts();
  assert.equal(attempts.length, 2);
  assert.equal(ledger.snapshot('session-1').consumed.transport_retries, 1);
});

test('redirect: a 3xx is refused and never followed', async () => {
  const server = await startServer((_hit, res) => {
    res.writeHead(302, { location: '/v1/chat/completions' });
    res.end();
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_REDIRECT_REFUSED',
    );
    assert.equal(server.hits.length, 1);
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Deadlines and unresolved submissions (Sections 15.5, 15.8)
// ---------------------------------------------------------------------------

test('deadline: the initial default is 600 seconds and is displayed as such', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    const description = transport.describe();
    assert.equal(description.deadlineMs, 600_000);
    assert.equal(description.deadlineSource, 'initial_default');
    assert.equal(description.deadlineDisplay, '600 seconds (initial default)');
    const verified = okTransport(server.baseUrl, { verifiedDeadlineMs: 45_000 });
    assert.equal(verified.describe().deadlineSource, 'route_verified');
    assert.equal(verified.describe().deadlineDisplay, '45 seconds (route verified)');
  } finally {
    await server.close();
  }
});

test('unresolved: a submission that times out is provider_submitted_unresolved, never retried', async () => {
  const server = await startServer(() => {
    // Never respond: the request was submitted; completion is unknown.
  });
  try {
    const ledger = new InProcessBudgetLedger();
    const transport = okTransport(server.baseUrl, {
      budget: ledger,
      verifiedDeadlineMs: 120,
    });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) =>
        isTransportError(err) &&
        err.code === 'TRANSPORT_SUBMITTED_UNRESOLVED' &&
        err.unknownCompletion === true &&
        err.retryable === false,
    );
    assert.equal(server.hits.length, 1);
    const [attempt] = transport.attempts();
    assert.equal(attempt.state, 'provider_submitted_unresolved');
    assert.equal(attempt.canonicalOperationStatus, 'provider_completion_unknown');
    assert.equal(attempt.deadlineSource, 'route_verified');
    assert.equal(ledger.snapshot('session-1').consumed.transport_retries, 0);
  } finally {
    await server.close();
  }
});

test('unresolved: a stream that breaks mid-response is unresolved and returns no partial text', async () => {
  const server = await startServer((_hit, res) => {
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    const chunk = {
      id: 'req-sse-1',
      model: MODEL,
      choices: [{ delta: { content: 'partial ' }, finish_reason: null }],
    };
    res.write(`data: ${JSON.stringify(chunk)}\n\n`);
    res.socket?.destroy();
  });
  try {
    const transport = okTransport(server.baseUrl, { stream: true });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) =>
        isTransportError(err) &&
        err.code === 'TRANSPORT_SUBMITTED_UNRESOLVED' &&
        err.unknownCompletion === true,
    );
    const [attempt] = transport.attempts();
    assert.equal(attempt.state, 'provider_submitted_unresolved');
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Response parsing (Section 16.6 safe diagnostics)
// ---------------------------------------------------------------------------

test('parse: malformed JSON records only safe metadata and is not retried', async () => {
  const body = 'this is not json {{{ and it is secret-free';
  const server = await startServer((_hit, res) => {
    json(res, 200, body);
  });
  try {
    const sink = new TransportDiagnosticSink();
    const ledger = new InProcessBudgetLedger();
    const transport = okTransport(server.baseUrl, {
      budget: ledger,
      diagnostics: sink,
    });
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => {
        assert.ok(isTransportError(err));
        assert.equal(err.code, 'TRANSPORT_RESPONSE_MALFORMED');
        assert.equal(err.parseDiagnostics?.schemaPath, '$');
        assert.equal(err.parseDiagnostics?.byteCount, Buffer.byteLength(body));
        assert.match(err.parseDiagnostics?.responseSha256 ?? '', /^[0-9a-f]{64}$/);
        assert.ok(!err.message.includes('not json'));
        return true;
      },
    );
    assert.equal(server.hits.length, 1);
    const [entry] = sink.safeEntries();
    assert.equal(entry.kind, 'parse_failure');
    assert.equal(entry.schemaPath, '$');
    assert.equal(entry.byteCount, Buffer.byteLength(body));
    assert.ok(!JSON.stringify(sink.safeEntries()).includes('not json'));
  } finally {
    await server.close();
  }
});

test('parse: a missing choices array is a malformed envelope at the choices path', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, JSON.stringify({ id: 'req-x', model: MODEL }));
  });
  try {
    const transport = okTransport(server.baseUrl, {});
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) =>
        isTransportError(err) &&
        err.code === 'TRANSPORT_RESPONSE_MALFORMED' &&
        err.parseDiagnostics?.schemaPath === 'choices',
    );
  } finally {
    await server.close();
  }
});

test('stream: a complete SSE stream assembles text, reported identity, and usage', async () => {
  const server = await startServer((_hit, res) => {
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    const chunk = (content: string, finish: string | null, extra = {}) =>
      `data: ${JSON.stringify({
        id: 'req-sse-9',
        model: MODEL,
        choices: [{ delta: { content }, finish_reason: finish }],
        ...extra,
      })}\n\n`;
    res.write(chunk('Hello ', null));
    res.write(chunk('world', null));
    res.write(
      `data: ${JSON.stringify({
        id: 'req-sse-9',
        model: MODEL,
        choices: [{ delta: {}, finish_reason: 'stop' }],
        usage: { prompt_tokens: 3, completion_tokens: 2 },
      })}\n\n`,
    );
    res.end('data: [DONE]\n\n');
  });
  try {
    const transport = okTransport(server.baseUrl, { stream: true });
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, 'Hello world');
    assert.equal(response.reported_model_id, MODEL);
    assert.equal(response.provider_request_id, 'req-sse-9');
    assert.deepEqual(response.usage, { input_tokens: 3, output_tokens: 2 });
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Reasoning mapping (Section 13.5) and text-only success (T032)
// ---------------------------------------------------------------------------

test('reasoning: an applied level maps through the table; auto sends no vendor parameter', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const high = fixedSelection({
      reasoning: { requested: 'high', applied: 'high', supported: true, limitation: null },
    });
    const t1 = okTransport(server.baseUrl, {}, high);
    await t1.generate(transportRequest());
    let wire = JSON.parse(server.hits[0].body) as Record<string, unknown>;
    assert.equal(wire.reasoning_effort, 'high');

    const auto = fixedSelection({
      reasoning: { requested: 'auto', applied: 'auto', supported: true, limitation: null },
    });
    const t2 = okTransport(server.baseUrl, {}, auto);
    await t2.generate(transportRequest());
    wire = JSON.parse(server.hits[1].body) as Record<string, unknown>;
    assert.ok(!('reasoning_effort' in wire));
    assert.ok(!('reasoning' in wire));

    const unapplied = fixedSelection({
      reasoning: {
        requested: 'high',
        applied: null,
        supported: false,
        limitation: 'not supported by this route',
      },
    });
    const t3 = okTransport(server.baseUrl, {}, unapplied);
    await t3.generate(transportRequest());
    wire = JSON.parse(server.hits[2].body) as Record<string, unknown>;
    assert.ok(!('reasoning_effort' in wire));
  } finally {
    await server.close();
  }
});

test('reasoning: an unmapped applied level (max) is refused, never renamed or sent blindly', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'x'));
  });
  try {
    const selection = fixedSelection({
      reasoning: { requested: 'max', applied: 'max', supported: true, limitation: null },
      capabilitySnapshot: {
        contextWindowTokens: 128000,
        maxOutputTokens: null,
        capabilities: ['text_generation'],
        supportedReasoningLevels: ['max'],
      },
    });
    const transport = okTransport(server.baseUrl, {}, selection);
    await assert.rejects(
      () => transport.generate(transportRequest()),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_REASONING_UNMAPPED',
    );
    assert.equal(server.hits.length, 0);
  } finally {
    await server.close();
  }
});

test('text-only: a route with no tool-calling capability succeeds with no tools in the request', async () => {
  const server = await startServer((_hit, res) => {
    json(res, 200, envelope(MODEL, 'plain text answer'));
  });
  try {
    const selection = fixedSelection({
      capabilitySnapshot: {
        contextWindowTokens: 32000,
        maxOutputTokens: null,
        capabilities: [],
        supportedReasoningLevels: null,
      },
    });
    const transport = okTransport(server.baseUrl, {}, selection);
    const response = await transport.generate(transportRequest());
    assert.equal(response.text, 'plain text answer');
    const wire = JSON.parse(server.hits[0].body) as Record<string, unknown>;
    assert.ok(!('tools' in wire));
    assert.ok(!('tool_choice' in wire));
  } finally {
    await server.close();
  }
});

// ---------------------------------------------------------------------------
// Local profile (T031): same adapter, local guarantees
// ---------------------------------------------------------------------------

test('local: the Ollama profile preserves local and cloud identity byte-identical, with no daemon side effects', async () => {
  const server = await startServer((_hit, res, index) => {
    json(res, 200, envelope(index === 0 ? 'local-model:8b' : 'cloud-model:cloud', 'ok'));
  });
  try {
    for (const [index, model] of [
      [0, 'local-model:8b'],
      [1, 'cloud-model:cloud'],
    ] as const) {
      const selection = fixedSelection({
        providerSlug: 'ollama',
        requestedModelOrAlias: model,
        credential: { state: 'not_required', envVar: null, source: null, checked: [] },
      });
      const transport = createOllamaTransport({
        selection,
        baseUrl: server.baseUrl,
        sleep: async () => {},
        random: () => 0,
      });
      const response = await transport.generate(
        transportRequest({
          model_policy: { ...POLICY, requested_model_id: model },
        }),
      );
      assert.equal(response.text, 'ok');
      const wire = JSON.parse(server.hits[index].body) as Record<string, unknown>;
      assert.equal(wire.model, model);
      assert.equal(server.hits[index].headers.authorization, undefined);
      // No daemon side-effect fields are ever sent.
      assert.ok(!('options' in wire));
      assert.ok(!('keep_alive' in wire));
      assert.equal(transport.describe().endpointLocality, 'loopback');
    }
  } finally {
    await server.close();
  }
});

test('local: the Ollama profile refuses a non-loopback endpoint rather than mislabeling locality', async () => {
  assert.throws(
    () =>
      createOllamaTransport({
        selection: fixedSelection({
          providerSlug: 'ollama',
          credential: { state: 'not_required', envVar: null, source: null, checked: [] },
        }),
        baseUrl: 'https://ollama.com/v1',
      }),
    (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_CONFIG_INVALID',
  );
});

// ---------------------------------------------------------------------------
// Engine integration (T031): the CWE-004 engine drives this transport
// unchanged; only the adapter differs from the fixture transport.
// ---------------------------------------------------------------------------

test('engine: a full council session completes over the compatible HTTP transport', async () => {
  const fixture = new DeterministicFixtureTransport();
  const server = await startServer(async (hit, res, index) => {
    if (index === 0) {
      json(res, 503, '{"error":"warmup"}');
      return;
    }
    const wire = JSON.parse(hit.body) as {
      model: string;
      messages: Array<{ content: string }>;
    };
    const input = JSON.parse(wire.messages[1].content) as Record<string, unknown>;
    const seat = SEAT_ROSTER.find(
      (s) => s.display_name === input.seat_display_name,
    );
    const purpose = input.draft_resolution ? 'ratification' : 'advisor';
    const round = input.draft_resolution
      ? 3
      : 'challenges_for_seat' in input
        ? 2
        : 1;
    const fixtureResponse = await fixture.generate({
      purpose: purpose as 'advisor' | 'ratification',
      session_id: (input.brief as { session_id: string }).session_id,
      seat_id: seat!.seat_id,
      round: round as 1 | 2 | 3,
      route_id: 'route-fixture-1',
      model_policy: POLICY,
      system: '',
      input,
    });
    json(res, 200, envelope(wire.model, fixtureResponse.text));
  });
  try {
    const sample = buildSampleSession();
    const selection = fixedSelection({
      routeId: 'route-fixture-1',
      providerSlug: 'fixture-compatible',
      requestedModelOrAlias: 'model-selected-by-client',
      credential: { state: 'not_required', envVar: null, source: null, checked: [] },
    });
    const transport = createCompatibleTransport({
      selection,
      baseUrl: server.baseUrl,
      sleep: async () => {},
      random: () => 0,
    });
    const host = grantHost(
      tempDataDir('cwe009-engine'),
      sample.spec,
      sample.scope,
      transport,
    );
    const engine = new CouncilEngine(host);
    await engine.createSession({ ...sample, sample: true });
    const done = await engine.startSession(sample.spec.session_id, 'test-grant');
    assert.equal(done.state.state, 'COMPLETED');
    const verdict = await engine.getVerdict(sample.spec.session_id);
    assert.ok(verdict);
    // 27 seat operations plus the single engine-owned retry of the
    // first, 503-failed operation.
    assert.equal(server.hits.length, 28);
    for (const hit of server.hits) {
      const wire = JSON.parse(hit.body) as Record<string, unknown>;
      assert.equal(wire.model, 'model-selected-by-client');
    }
    const snapshot = host.budget.snapshot(sample.spec.session_id);
    assert.equal(snapshot.consumed.transport_retries, 1);
    // 27 accepted attempts plus the one 503 failure the engine retried.
    const attempts = transport.attempts();
    assert.equal(attempts.length, 28);
    assert.equal(attempts.filter((a) => a.state === 'accepted').length, 27);
    const failed = attempts.filter((a) => a.state === 'failed');
    assert.equal(failed.length, 1);
    assert.equal(failed[0].errorCode, 'TRANSPORT_PROVIDER_ERROR');
    assert.equal(failed[0].retryIndex, 0);
    assert.ok(attempts.every((a) => a.wireModel === 'model-selected-by-client'));
  } finally {
    await server.close();
  }
});
