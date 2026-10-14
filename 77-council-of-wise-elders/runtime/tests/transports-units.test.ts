/**
 * CWE-009 unit tests for the transport support modules: endpoint URL
 * policy (Section 28.4), the reasoning mapping table (Section 13.5),
 * the route-resolution guard and identity derivation (Section 13.4,
 * mirroring CWE-008), the diagnostic sink (Section 16.6), and the
 * http-core parsers. All pure and deterministic.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
  type DiagnosticRetentionPolicy,
} from '../src/contracts/index.js';
import { TransportDiagnosticSink } from '../src/providers/diagnostics.js';
import { isTransportError } from '../src/providers/errors.js';
import {
  parseChatCompletionEnvelope,
  parseRetryAfterMs,
} from '../src/providers/http-core.js';
import {
  REASONING_EFFORT_MAP,
  mapReasoningToParams,
} from '../src/providers/reasoning.js';
import {
  deriveIdentityLevel,
  evaluateRouteResolution,
  selectionSha256,
  type CouncilRouteSelection,
} from '../src/providers/selection.js';
import { assessEndpoint } from '../src/providers/url-policy.js';

function selection(
  overrides: Partial<CouncilRouteSelection> = {},
): CouncilRouteSelection {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-1',
    routeRevision: 3,
    routeKind: 'fixed_model',
    providerSlug: 'openrouter',
    requestedRoute: 'route-1',
    requestedModelOrAlias: 'acme/model-x',
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: null,
      maxOutputTokens: null,
      capabilities: [],
      supportedReasoningLevels: null,
    },
    credential: { state: 'not_required', envVar: null, source: null, checked: [] },
    identityLevel: 'configured',
    scope: {
      tenantId: 't',
      companyId: 'c',
      installationId: 'i',
      ownerSubject: null,
    },
    createdAt: '2026-10-14T00:00:00.000Z',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// URL policy (Section 28.4)
// ---------------------------------------------------------------------------

test('url policy: metadata and link-local targets are always blocked', () => {
  for (const url of [
    'http://169.254.169.254/v1',
    'http://169.254.170.2/v1',
    'http://metadata.google.internal/v1',
    'http://100.100.100.200/v1',
    'http://169.254.10.20/v1',
  ]) {
    assert.throws(
      () => assessEndpoint(url),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ENDPOINT_BLOCKED',
      url,
    );
  }
});

test('url policy: credentials in the URL, bad schemes, and remote http are blocked', () => {
  for (const url of [
    'https://user:pass@api.example.com/v1',
    'ftp://api.example.com/v1',
    'http://api.example.com/v1',
    'not a url',
  ]) {
    assert.throws(
      () => assessEndpoint(url),
      (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_ENDPOINT_BLOCKED',
      url,
    );
  }
  // Explicit opt-in is the only way remote http is accepted.
  const allowed = assessEndpoint('http://api.example.com/v1', {
    allowInsecureRemoteHttp: true,
  });
  assert.equal(allowed.locality, 'public');
});

test('url policy: configured loopback and private endpoints are allowed and classified', () => {
  const loopback = assessEndpoint('http://127.0.0.1:11434/v1');
  assert.equal(loopback.locality, 'loopback');
  assert.equal(loopback.url, 'http://127.0.0.1:11434/v1/chat/completions');
  assert.equal(loopback.origin, 'http://127.0.0.1:11434');
  const localhost = assessEndpoint('http://localhost:1234/v1/');
  assert.equal(localhost.locality, 'loopback');
  assert.equal(localhost.url, 'http://localhost:1234/v1/chat/completions');
  const lan = assessEndpoint('http://192.168.1.50:8080/v1');
  assert.equal(lan.locality, 'private_network');
  const remote = assessEndpoint('https://openrouter.ai/api/v1');
  assert.equal(remote.locality, 'public');
  assert.equal(remote.url, 'https://openrouter.ai/api/v1/chat/completions');
});

// ---------------------------------------------------------------------------
// Reasoning mapping table (Section 13.5)
// ---------------------------------------------------------------------------

test('reasoning: the mapping table is explicit and total for mapped levels', () => {
  assert.deepEqual(
    Object.keys(REASONING_EFFORT_MAP).sort(),
    ['high', 'low', 'medium', 'minimal', 'none', 'off'],
  );
  const high = mapReasoningToParams(
    { requested: 'high', applied: 'high', supported: true, limitation: null },
    'reasoning_effort',
  );
  assert.deepEqual(high.params, { reasoning_effort: 'high' });
  const objectStyle = mapReasoningToParams(
    { requested: 'low', applied: 'low', supported: true, limitation: null },
    'reasoning_object',
  );
  assert.deepEqual(objectStyle.params, { reasoning: { effort: 'low' } });
  const auto = mapReasoningToParams(
    { requested: 'auto', applied: 'auto', supported: true, limitation: null },
    'reasoning_effort',
  );
  assert.deepEqual(auto.params, {});
  const unapplied = mapReasoningToParams(
    { requested: 'high', applied: null, supported: false, limitation: 'no' },
    'reasoning_effort',
  );
  assert.deepEqual(unapplied.params, {});
});

test('reasoning: max has no mapping and is refused rather than renamed', () => {
  assert.throws(
    () =>
      mapReasoningToParams(
        { requested: 'max', applied: 'max', supported: true, limitation: null },
        'reasoning_effort',
      ),
    (err: unknown) => isTransportError(err) && err.code === 'TRANSPORT_REASONING_UNMAPPED',
  );
});

// ---------------------------------------------------------------------------
// Resolution guard and identity derivation (Section 13.4)
// ---------------------------------------------------------------------------

test('resolution: a prose identity claim is recorded as ignored and changes nothing', () => {
  const outcome = evaluateRouteResolution(selection(), {
    source: 'explicit_route',
    attemptedModelId: 'acme/model-x',
    reportedModelId: 'acme/model-x',
    proseClaimedModelId: 'totally/other-model',
  });
  assert.equal(outcome.outcome, 'accepted');
  assert.equal(outcome.effectiveModelId, 'acme/model-x');
  assert.ok(outcome.events.some((e) => e.type === 'prose_identity_claim_ignored'));
  assert.equal(outcome.identityLevel, 'reported_identity');
});

test('resolution: an approved substitution under client_approved_only is an explicit route change', () => {
  const outcome = evaluateRouteResolution(
    selection({ fallbackPolicy: 'client_approved_only' }),
    {
      source: 'fallback',
      attemptedModelId: 'acme/model-y',
      approval: {
        approvalRef: 'approval-1',
        reason: 'client approved the swap',
        costImplication: 'same price class',
      },
    },
  );
  assert.equal(outcome.outcome, 'substituted_with_approval');
  assert.equal(outcome.effectiveModelId, 'acme/model-y');
  assert.equal(outcome.changeRecord?.newRouteRevision, 4);
  assert.equal(outcome.changeRecord?.approvalRef, 'approval-1');
});

test('resolution: the same substitution under policy none is refused', () => {
  const outcome = evaluateRouteResolution(selection(), {
    source: 'cascade',
    attemptedModelId: 'acme/model-y',
  });
  assert.equal(outcome.outcome, 'refused');
  assert.equal(outcome.effectiveModelId, null);
});

test('identity: derivation never exceeds the evidence', () => {
  assert.equal(
    deriveIdentityLevel({
      transportProbed: false,
      reportedModelId: null,
      identityVerification: null,
      evaluation: null,
    }),
    'configured',
  );
  assert.equal(
    deriveIdentityLevel({
      transportProbed: true,
      reportedModelId: null,
      identityVerification: null,
      evaluation: null,
    }),
    'transport_probed',
  );
  assert.equal(
    deriveIdentityLevel({
      transportProbed: true,
      reportedModelId: 'acme/model-x',
      identityVerification: null,
      evaluation: null,
    }),
    'reported_identity',
  );
  // Transport evidence alone cannot reach the top two levels.
  assert.equal(
    deriveIdentityLevel({
      transportProbed: true,
      reportedModelId: 'acme/model-x',
      identityVerification: { verified: true, method: 'signed-attestation' },
      evaluation: null,
    }),
    'resolved_identity_verified',
  );
  assert.equal(
    deriveIdentityLevel({
      transportProbed: true,
      reportedModelId: 'acme/model-x',
      identityVerification: null,
      evaluation: { status: 'passed', evaluationId: 'eval-1', recordedAt: '2026-10-14T00:00:00.000Z' },
    }),
    'quality_qualified',
  );
});

test('selection hash: canonical, stable, and sensitive to any field change', () => {
  const a = selection();
  const b = selection();
  assert.equal(selectionSha256(a), selectionSha256(b));
  assert.notEqual(
    selectionSha256(a),
    selectionSha256(selection({ routeRevision: 4 })),
  );
});

// ---------------------------------------------------------------------------
// Diagnostic sink (Section 16.6)
// ---------------------------------------------------------------------------

test('diagnostics: with the default policy, capture is refused and metadata only is recorded', () => {
  const sink = new TransportDiagnosticSink();
  const outcome = sink.considerCapture({
    sessionId: 'session-1',
    dataClass: 'provider_response_body',
    body: new TextEncoder().encode('raw body'),
    minutesSinceWindowStart: 1,
    sessionDeletedOrRevoked: false,
  });
  assert.equal(outcome.captured, false);
  assert.match(outcome.reason, /disabled/);
});

test('diagnostics: even an enabled policy degrades to metadata only without a protected store', () => {
  const policy: DiagnosticRetentionPolicy = {
    ...DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
    enabled: true,
    authorized_by_principal: 'owner-1',
    authorization_kind: 'owner',
    session_id: 'session-1',
  };
  const sink = new TransportDiagnosticSink(policy);
  const outcome = sink.considerCapture({
    sessionId: 'session-1',
    dataClass: 'provider_response_body',
    body: new TextEncoder().encode('raw body'),
    minutesSinceWindowStart: 1,
    sessionDeletedOrRevoked: false,
  });
  assert.equal(outcome.captured, false);
  assert.match(outcome.reason, /metadata only/);
});

test('diagnostics: never-captured data classes are refused in every mode', () => {
  const policy: DiagnosticRetentionPolicy = {
    ...DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
    enabled: true,
    authorized_by_principal: 'owner-1',
    authorization_kind: 'owner',
    session_id: 'session-1',
  };
  const sink = new TransportDiagnosticSink(policy);
  const outcome = sink.considerCapture({
    sessionId: 'session-1',
    dataClass: 'access_token',
    body: new TextEncoder().encode('token-shaped'),
    minutesSinceWindowStart: 1,
    sessionDeletedOrRevoked: false,
  });
  assert.equal(outcome.captured, false);
  assert.match(outcome.reason, /never captured/);
});

// ---------------------------------------------------------------------------
// http-core parsers
// ---------------------------------------------------------------------------

test('retry-after: seconds and HTTP-date parse; garbage does not', () => {
  assert.equal(parseRetryAfterMs('2', 0), 2000);
  assert.equal(parseRetryAfterMs('0', 0), 0);
  const now = Date.parse('2026-10-14T00:00:00.000Z');
  const date = new Date(now + 5000).toUTCString();
  assert.equal(parseRetryAfterMs(date, now), 5000);
  assert.equal(parseRetryAfterMs('soon', now), null);
  assert.equal(parseRetryAfterMs(null, now), null);
});

test('envelope: text parts join, reported identity and usage are structured only', () => {
  const body = JSON.stringify({
    id: 'req-1',
    model: 'acme/model-x',
    choices: [
      {
        message: {
          role: 'assistant',
          content: [
            { type: 'text', text: 'Hello ' },
            { type: 'text', text: 'there' },
            { type: 'reasoning', text: 'hidden' },
          ],
        },
        finish_reason: 'stop',
      },
    ],
    usage: { prompt_tokens: 5, completion_tokens: 6 },
  });
  const parsed = parseChatCompletionEnvelope(body, body.length, 'f'.repeat(64), null);
  assert.equal(parsed.text, 'Hello there');
  assert.equal(parsed.reportedModelId, 'acme/model-x');
  assert.equal(parsed.providerRequestId, 'req-1');
  assert.deepEqual(parsed.usage, { input_tokens: 5, output_tokens: 6 });
});

test('envelope: hidden-reasoning content never enters the parsed text', () => {
  const body = JSON.stringify({
    id: 'req-2',
    model: 'acme/model-x',
    choices: [
      {
        message: {
          role: 'assistant',
          content: 'visible',
          reasoning_content: 'hidden chain of thought',
        },
        finish_reason: 'stop',
      },
    ],
  });
  const parsed = parseChatCompletionEnvelope(body, body.length, 'f'.repeat(64), null);
  assert.equal(parsed.text, 'visible');
});
