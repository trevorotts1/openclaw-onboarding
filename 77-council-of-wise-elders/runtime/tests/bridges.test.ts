/**
 * CWE-010 host bridge tests: OpenClaw and Claude-Nine bridges behind
 * the CWE-004 host ports.
 *
 * Deterministic fixtures only: no live provider calls, no real keys.
 * The delegate transport in most tests is a counter that proves whether
 * the guard let a request through; the CLI sample tests use CWE-004's
 * deterministic fixture transport and the golden verdict values.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import type { ModelPolicy } from '../src/contracts/index.js';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { CouncilEngine } from '../src/cli/engine.js';
import {
  buildSampleSession,
  DeterministicFixtureTransport,
} from '../src/cli/fixture-transport.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import { localScope } from '../src/cli/local-host.js';
import {
  applyHostResolution,
  buildRouteCatalog,
  createRouteSelection,
  HIDDEN_IDENTITY_STATEMENT,
  RouteResolutionRefusedError,
  selectionClientPayload,
  trustedScopeFromScopeFields,
  type CouncilRouteSelection,
  type ProviderRouteDescriptor,
  type RouteEvidence,
} from '../src/bridges/host-bridge.js';
import {
  createOpenClawBridge,
  OPENCLAW_REPLACEMENT_POINTS,
  type OpenClawHostResolver,
} from '../src/bridges/openclaw.js';
import {
  createClaudeNineBridge,
  renderClaudeNineWrapper,
  CLAUDE_NINE_WRAPPER_FILE_NAME,
  type ClaudeNineNativeResolver,
} from '../src/bridges/claude-nine.js';
import {
  PARITY_FIXTURES,
  runBridgeParity,
  runParityCheck,
  summarizeResolutionOutcome,
} from '../src/bridges/parity.js';
import { buildTestGrant } from './helpers.js';

function tempBridgeDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe010-${label}-`));
}

const FIXED_DESCRIPTOR: ProviderRouteDescriptor = {
  routeId: 'route-fixture-1',
  providerSlug: 'fixture-provider',
  displayLabel: 'Fixture fixed route',
  kind: 'fixed_model',
  modelId: 'model-selected-by-client',
  combinationMembers: [],
  providerAccountRef: 'fixture-account',
  capability: {
    contextWindowTokens: 128000,
    maxOutputTokens: 4096,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  },
  credential: { state: 'not_required', envVar: null, source: null, checked: [] },
};

const COMBO_DESCRIPTOR: ProviderRouteDescriptor = {
  routeId: 'route-combo-1',
  providerSlug: 'fixture-router',
  displayLabel: 'Fixture combination route',
  kind: 'combination',
  modelId: null,
  combinationMembers: ['member-a', 'member-b'],
  providerAccountRef: 'fixture-account',
  capability: {
    contextWindowTokens: null,
    maxOutputTokens: null,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  },
  credential: { state: 'not_required', envVar: null, source: null, checked: [] },
};

function policyFor(
  descriptor: ProviderRouteDescriptor,
  fallback: ModelPolicy['fallback_policy'] = 'none',
): ModelPolicy {
  return {
    selection: 'explicit',
    route_id: descriptor.routeId,
    requested_model_id: descriptor.modelId,
    reasoning_preference: null,
    fallback_policy: fallback,
  };
}

function requestFor(descriptor: ProviderRouteDescriptor): TransportRequest {
  return {
    purpose: 'advisor',
    session_id: 'sess-bridge-test',
    seat_id: 'simon-sinek',
    round: 1,
    route_id: descriptor.routeId,
    model_policy: policyFor(descriptor),
    system: 'bridge test',
    input: {},
  };
}

class CountingTransport implements ModelTransport {
  calls = 0;
  async generate(): Promise<TransportResponse> {
    this.calls += 1;
    return {
      text: '{}',
      provider_request_id: `counting-${this.calls}`,
      reported_model_id: null,
      usage: { input_tokens: null, output_tokens: null },
    };
  }
}

// ---------------------------------------------------------------------------
// Catalog and selection semantics
// ---------------------------------------------------------------------------

test('bridges: catalog lists routes as UNTESTED with configured identity until evidence exists', () => {
  const catalog = buildRouteCatalog([FIXED_DESCRIPTOR]);
  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].readiness, 'UNTESTED');
  assert.equal(catalog[0].identityLevel, 'configured');
  assert.equal(catalog[0].qualityQualified, false);
});

test('bridges: readiness and identity levels rise only with real evidence', () => {
  const evidence = (patch: Partial<RouteEvidence>): RouteEvidence => ({
    transportProbed: false,
    reportedModelId: null,
    identityVerification: null,
    evaluation: null,
    ...patch,
  });
  const build = (ev: RouteEvidence) =>
    buildRouteCatalog([FIXED_DESCRIPTOR], new Map([[FIXED_DESCRIPTOR.routeId, ev]]))[0];

  const probed = build(evidence({ transportProbed: true }));
  assert.equal(probed.readiness, 'PROBED');
  assert.equal(probed.identityLevel, 'transport_probed');
  assert.equal(probed.qualityQualified, false);

  const reported = build(
    evidence({ transportProbed: true, reportedModelId: 'model-selected-by-client' }),
  );
  assert.equal(reported.identityLevel, 'reported_identity');
  assert.equal(reported.readiness, 'PROBED');

  const verified = build(
    evidence({
      transportProbed: true,
      reportedModelId: 'model-selected-by-client',
      identityVerification: { verified: true, method: 'fixture-check' },
    }),
  );
  assert.equal(verified.identityLevel, 'resolved_identity_verified');
  assert.equal(verified.qualityQualified, false);

  const qualified = build(
    evidence({
      transportProbed: true,
      evaluation: { status: 'passed', evaluationId: 'eval-1', recordedAt: '2026-01-01T00:00:00Z' },
    }),
  );
  assert.equal(qualified.readiness, 'QUALIFIED');
  assert.equal(qualified.identityLevel, 'quality_qualified');
  assert.equal(qualified.qualityQualified, true);

  const failed = build(
    evidence({
      transportProbed: true,
      evaluation: { status: 'failed', evaluationId: 'eval-2', recordedAt: '2026-01-01T00:00:00Z' },
    }),
  );
  assert.equal(failed.qualityQualified, false);
  assert.equal(failed.readiness, 'PROBED');
});

test('bridges: catalog and selection payloads carry credential presence only, never a planted value', () => {
  const planted = 'PLANTED-SECRET-VALUE-DO-NOT-EMIT';
  const descriptor: ProviderRouteDescriptor = {
    ...FIXED_DESCRIPTOR,
    credential: {
      state: 'present',
      envVar: 'PLANTED_KEY_NAME',
      source: 'process.env',
      checked: [],
      // A value that must never survive into any emitted structure.
      value: planted,
    } as ProviderRouteDescriptor['credential'],
  };
  const catalog = buildRouteCatalog([descriptor]);
  assert.ok(!JSON.stringify(catalog).includes(planted));
  assert.equal(catalog[0].credential.envVar, 'PLANTED_KEY_NAME');
  assert.equal(catalog[0].credential.state, 'present');

  const selection = createRouteSelection(
    catalog[0],
    { routeId: descriptor.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  assert.ok(!JSON.stringify(selection).includes(planted));
  assert.ok(!JSON.stringify(selectionClientPayload(selection)).includes(planted));
  assert.equal(selectionClientPayload(selection).credential.envVar, 'PLANTED_KEY_NAME');
});

test('bridges: selection pins the exact selected model and rejects a different one', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const scope = trustedScopeFromScopeFields(localScope());
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId, requestedModelOrAlias: 'model-selected-by-client' },
    scope,
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  assert.equal(selection.requestedModelOrAlias, 'model-selected-by-client');
  assert.equal(selection.fallbackPolicy, 'none');

  assert.throws(
    () =>
      createRouteSelection(
        entry,
        { routeId: entry.routeId, requestedModelOrAlias: 'model-someone-else' },
        scope,
        { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
      ),
    (err: unknown) =>
      err instanceof Error && (err as { code?: string }).code === 'INVALID_SELECTION',
  );
  assert.throws(
    () =>
      createRouteSelection(
        entry,
        { routeId: 'route-not-in-catalog' },
        scope,
        { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
      ),
    (err: unknown) =>
      err instanceof Error && (err as { code?: string }).code === 'ROUTE_NOT_IN_CATALOG',
  );
});

test('bridges: selection rejects a conflicting body-supplied scope field', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  assert.throws(
    () =>
      createRouteSelection(
        entry,
        { routeId: entry.routeId, company_id: 'company-not-yours' },
        trustedScopeFromScopeFields(localScope()),
        { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
      ),
    (err: unknown) =>
      err instanceof Error && (err as { code?: string }).code === 'UNTRUSTED_SCOPE_FIELD',
  );
});

test('bridges: combination selection requires the pinned member list', () => {
  const emptyCombo: ProviderRouteDescriptor = { ...COMBO_DESCRIPTOR, combinationMembers: [] };
  const entry = buildRouteCatalog([emptyCombo])[0];
  assert.throws(
    () =>
      createRouteSelection(
        entry,
        { routeId: entry.routeId },
        trustedScopeFromScopeFields(localScope()),
        { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
      ),
    (err: unknown) =>
      err instanceof Error &&
      (err as { code?: string }).code === 'COMBINATION_MEMBER_REQUIRED',
  );
});

test('bridges: unsupported reasoning preference is retained as requested with a limitation, never renamed', () => {
  const probedDescriptor: ProviderRouteDescriptor = {
    ...FIXED_DESCRIPTOR,
    capability: { ...FIXED_DESCRIPTOR.capability, supportedReasoningLevels: ['low', 'high'] },
  };
  const entry = buildRouteCatalog([probedDescriptor])[0];
  const scope = trustedScopeFromScopeFields(localScope());
  const unsupported = createRouteSelection(
    entry,
    { routeId: entry.routeId, reasoningPreference: 'ultra' },
    scope,
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  assert.equal(unsupported.reasoning.requested, 'ultra');
  assert.equal(unsupported.reasoning.applied, null);
  assert.equal(unsupported.reasoning.supported, false);
  assert.ok(unsupported.reasoning.limitation?.includes('not supported'));

  const unprobed = createRouteSelection(
    buildRouteCatalog([FIXED_DESCRIPTOR])[0],
    { routeId: FIXED_DESCRIPTOR.routeId, reasoningPreference: 'high' },
    scope,
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  assert.equal(unprobed.reasoning.requested, 'high');
  assert.equal(unprobed.reasoning.applied, null);
  assert.equal(unprobed.reasoning.supported, null);
  assert.ok(unprobed.reasoning.limitation?.includes('not been probed'));
});

// ---------------------------------------------------------------------------
// OpenClaw bridge guard behavior
// ---------------------------------------------------------------------------

function openClawBridgeWith(
  resolver: OpenClawHostResolver,
  descriptor: ProviderRouteDescriptor = FIXED_DESCRIPTOR,
  fallback: ModelPolicy['fallback_policy'] = 'none',
) {
  const delegate = new CountingTransport();
  const bridge = createOpenClawBridge({
    dataDir: tempBridgeDir('openclaw'),
    resolver,
    routes: [descriptor],
    bindings: [
      {
        routeId: descriptor.routeId,
        delegate,
        reportAttempt: () => {
          throw new Error('factory must wire reportAttempt');
        },
        policy: policyFor(descriptor, fallback),
      },
    ],
  });
  return { bridge, delegate };
}

test('openclaw bridge: pinned route reaches the delegate unchanged', async () => {
  const { bridge, delegate } = openClawBridgeWith({
    reportResolution: (selection: CouncilRouteSelection) => ({
      attemptedModelId: selection.requestedModelOrAlias,
      reportedModelId: null,
    }),
  });
  const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
  assert.ok(transport);
  await transport.generate(requestFor(FIXED_DESCRIPTOR));
  assert.equal(delegate.calls, 1);
  const records = bridge.journal.list();
  assert.equal(records.length, 1);
  assert.equal(records[0].harness, 'openclaw');
  assert.equal(records[0].outcome.outcome, 'accepted');
  assert.equal(records[0].outcome.effectiveModelId, 'model-selected-by-client');
  assert.equal(bridge.journal.routeChanges().length, 0);
});

test('openclaw bridge: every mapped select_model.py replacement point is refused under fallback policy none and recorded', async () => {
  for (const point of OPENCLAW_REPLACEMENT_POINTS) {
    const { bridge, delegate } = openClawBridgeWith({
      reportResolution: () => ({
        attemptedModelId: 'model-not-selected',
        reportedModelId: null,
        viaReplacementPoint: point.id,
      }),
    });
    const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
    assert.ok(transport);
    await assert.rejects(
      () => transport.generate(requestFor(FIXED_DESCRIPTOR)),
      (err: unknown) => err instanceof RouteResolutionRefusedError,
    );
    assert.equal(delegate.calls, 0, `${point.id}: delegate must never be called`);
    const records = bridge.journal.list();
    assert.equal(records.length, 1, `${point.id}: refusal must be recorded`);
    const refusal = records[0].outcome.events.find(
      (e) => e.type === 'substitution_refused',
    );
    assert.ok(refusal && refusal.type === 'substitution_refused');
    assert.equal(refusal.source, point.source, `${point.id}: source mapping`);
    assert.equal(refusal.attemptedModelId, 'model-not-selected');
    assert.equal(bridge.journal.routeChanges().length, 1);
  }
});

test('openclaw bridge: substitution under client_approved_only without an approval record is refused', async () => {
  const { bridge, delegate } = openClawBridgeWith(
    {
      reportResolution: () => ({
        attemptedModelId: 'model-unapproved',
        reportedModelId: null,
        viaReplacementPoint: 'agent-model-fallback-array',
      }),
    },
    FIXED_DESCRIPTOR,
    'client_approved_only',
  );
  const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
  assert.ok(transport);
  await assert.rejects(
    () => transport.generate(requestFor(FIXED_DESCRIPTOR)),
    (err: unknown) => err instanceof RouteResolutionRefusedError,
  );
  assert.equal(delegate.calls, 0);
  assert.equal(bridge.journal.routeChanges().length, 1);
});

test('openclaw bridge: approved substitution proceeds and is recorded as a route change with a new revision', async () => {
  const { bridge, delegate } = openClawBridgeWith(
    {
      reportResolution: () => ({
        attemptedModelId: 'model-approved-fallback',
        reportedModelId: null,
        viaReplacementPoint: 'agent-model-fallback-array',
        approval: {
          approvalRef: 'approval-test-1',
          reason: 'Selected route unavailable; client approved the change.',
          costImplication: 'Stated in the approval record.',
        },
      }),
    },
    FIXED_DESCRIPTOR,
    'client_approved_only',
  );
  const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
  assert.ok(transport);
  await transport.generate(requestFor(FIXED_DESCRIPTOR));
  assert.equal(delegate.calls, 1);
  const records = bridge.journal.list();
  assert.equal(records.length, 1);
  assert.equal(records[0].outcome.outcome, 'substituted_with_approval');
  assert.equal(records[0].outcome.effectiveModelId, 'model-approved-fallback');
  assert.equal(records[0].outcome.changeRecord?.newRouteRevision, 2);
  assert.equal(records[0].outcome.changeRecord?.originalRoute, FIXED_DESCRIPTOR.routeId);
  assert.equal(records[0].outcome.changeRecord?.replacementRoute, 'model-approved-fallback');
  assert.equal(records[0].outcome.changeRecord?.approvalRef, 'approval-test-1');
  assert.ok(
    records[0].outcome.events.some((e) => e.type === 'substitution_approved'),
  );
});

test('bridges: a request for a different route than the guarded selection is refused before the delegate', async () => {
  const { bridge, delegate } = openClawBridgeWith({
    reportResolution: (selection: CouncilRouteSelection) => ({
      attemptedModelId: selection.requestedModelOrAlias,
    }),
  });
  const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
  assert.ok(transport);
  const wrong = requestFor(FIXED_DESCRIPTOR);
  wrong.route_id = 'route-somewhere-else';
  await assert.rejects(
    () => transport.generate(wrong),
    (err: unknown) =>
      err instanceof Error &&
      (err as { code?: string }).code === 'COUNCIL_ROUTE_UNAVAILABLE',
  );
  assert.equal(delegate.calls, 0);
  assert.equal(bridge.journal.list().length, 0);
});

// ---------------------------------------------------------------------------
// Claude-Nine bridge guard behavior
// ---------------------------------------------------------------------------

function claudeNineBridgeWith(
  resolver: ClaudeNineNativeResolver,
  descriptor: ProviderRouteDescriptor = FIXED_DESCRIPTOR,
) {
  const delegate = new CountingTransport();
  const bridge = createClaudeNineBridge({
    dataDir: tempBridgeDir('claude-nine'),
    resolver,
    routes: [descriptor],
    bindings: [
      {
        routeId: descriptor.routeId,
        delegate,
        reportAttempt: () => {
          throw new Error('factory must wire reportAttempt');
        },
        policy: policyFor(descriptor),
      },
    ],
  });
  return { bridge, delegate };
}

test('claude-nine bridge: pinned route reaches the delegate unchanged and the journal names the harness', async () => {
  const { bridge, delegate } = claudeNineBridgeWith({
    reportResolution: (selection: CouncilRouteSelection) => ({
      attemptedModelId: selection.requestedModelOrAlias,
      reportedModelId: null,
    }),
  });
  const transport = bridge.host.transportRegistry.resolve(FIXED_DESCRIPTOR.routeId);
  assert.ok(transport);
  await transport.generate(requestFor(FIXED_DESCRIPTOR));
  assert.equal(delegate.calls, 1);
  const records = bridge.journal.list();
  assert.equal(records.length, 1);
  assert.equal(records[0].harness, 'claude-nine');
  assert.equal(records[0].outcome.outcome, 'accepted');
  assert.equal(bridge.harness, 'claude-nine');
  assert.equal(bridge.configRoot, '.claude-nine');
});

test('claude-nine bridge: combination member resolved and logged; outsider refused; hidden member stated exactly', async () => {
  const member = claudeNineBridgeWith(
    {
      reportResolution: () => ({
        attemptedModelId: 'member-b',
        reportedModelId: null,
        viaCombinationMember: true,
      }),
    },
    COMBO_DESCRIPTOR,
  );
  const memberTransport = member.bridge.host.transportRegistry.resolve(COMBO_DESCRIPTOR.routeId);
  assert.ok(memberTransport);
  await memberTransport.generate(requestFor(COMBO_DESCRIPTOR));
  assert.equal(member.delegate.calls, 1);
  const memberOutcome = member.bridge.journal.list()[0].outcome;
  assert.equal(memberOutcome.outcome, 'accepted');
  assert.equal(memberOutcome.effectiveModelId, 'member-b');
  assert.ok(
    memberOutcome.events.some((e) => e.type === 'combination_member_resolved'),
  );

  const outsider = claudeNineBridgeWith(
    {
      reportResolution: () => ({
        attemptedModelId: 'member-not-in-the-combination',
        reportedModelId: null,
        viaCombinationMember: true,
      }),
    },
    COMBO_DESCRIPTOR,
  );
  const outsiderTransport = outsider.bridge.host.transportRegistry.resolve(COMBO_DESCRIPTOR.routeId);
  assert.ok(outsiderTransport);
  await assert.rejects(
    () => outsiderTransport.generate(requestFor(COMBO_DESCRIPTOR)),
    (err: unknown) => err instanceof RouteResolutionRefusedError,
  );
  assert.equal(outsider.delegate.calls, 0);

  const hidden = claudeNineBridgeWith(
    { reportResolution: () => ({ attemptedModelId: null, reportedModelId: null }) },
    COMBO_DESCRIPTOR,
  );
  const hiddenTransport = hidden.bridge.host.transportRegistry.resolve(COMBO_DESCRIPTOR.routeId);
  assert.ok(hiddenTransport);
  await hiddenTransport.generate(requestFor(COMBO_DESCRIPTOR));
  assert.equal(hidden.delegate.calls, 1);
  const hiddenOutcome = hidden.bridge.journal.list()[0].outcome;
  assert.equal(hiddenOutcome.outcome, 'accepted');
  assert.equal(hiddenOutcome.effectiveModelId, null);
  assert.equal(hiddenOutcome.identityStatement, HIDDEN_IDENTITY_STATEMENT);
});

// ---------------------------------------------------------------------------
// Identity law through both guards
// ---------------------------------------------------------------------------

test('bridges: hidden identity yields the exact statement and the identity level stays configured', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  const outcome = applyHostResolution(selection, {
    source: 'explicit_route',
    attemptedModelId: null,
    reportedModelId: null,
  });
  assert.equal(outcome.outcome, 'accepted');
  assert.equal(
    outcome.identityStatement,
    'Selected route used; underlying model identity not independently exposed.',
  );
  assert.equal(outcome.identityLevel, 'configured');
});

test('bridges: prose identity claim is recorded as ignored and never raises the identity level', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  const outcome = applyHostResolution(selection, {
    source: 'explicit_route',
    attemptedModelId: 'model-selected-by-client',
    reportedModelId: null,
    proseClaimedModelId: 'model-claimed-in-prose',
  });
  assert.equal(outcome.outcome, 'accepted');
  assert.equal(outcome.identityLevel, 'configured');
  assert.ok(
    outcome.events.some((e) => e.type === 'prose_identity_claim_ignored'),
  );
});

test('bridges: provider-reported identity conflict is refused and identities stay distinct', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  const outcome = applyHostResolution(selection, {
    source: 'explicit_route',
    attemptedModelId: 'model-selected-by-client',
    reportedModelId: 'model-actually-someone-else',
  });
  assert.equal(outcome.outcome, 'refused');
  assert.equal(outcome.effectiveModelId, null);
});

test('bridges: reported identity raises the level only to reported_identity, never verified', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  const outcome = applyHostResolution(selection, {
    source: 'explicit_route',
    attemptedModelId: 'model-selected-by-client',
    reportedModelId: 'model-selected-by-client',
  });
  assert.equal(outcome.outcome, 'accepted');
  assert.equal(outcome.identityLevel, 'reported_identity');
});

// ---------------------------------------------------------------------------
// Harness isolation, enforced on the import graph
// ---------------------------------------------------------------------------

function moduleClosure(entryFile: string): Set<string> {
  const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
  const seen = new Set<string>();
  const queue = [resolve(srcRoot, entryFile)];
  const specifierPattern = /(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g;
  while (queue.length > 0) {
    const file = queue.pop() as string;
    if (seen.has(file)) continue;
    seen.add(file);
    let text: string;
    try {
      text = readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    for (const match of text.matchAll(specifierPattern)) {
      const spec = match[1];
      if (!spec.startsWith('.')) continue;
      const resolvedPath = resolve(dirname(file), spec.replace(/\.js$/, '.ts'));
      if (!seen.has(resolvedPath)) queue.push(resolvedPath);
    }
  }
  return seen;
}

function importSpecifiers(file: string): string[] {
  const text = readFileSync(file, 'utf8');
  const specs: string[] = [];
  const pattern = /(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g;
  for (const match of text.matchAll(pattern)) specs.push(match[1]);
  return specs;
}

test('bridges: harness isolation, neither bridge import graph reaches the other bridge', () => {
  const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
  const openclawEntry = join(srcRoot, 'bridges', 'openclaw.ts');
  const claudeNineEntry = join(srcRoot, 'bridges', 'claude-nine.ts');

  const claudeNineClosure = moduleClosure('bridges/claude-nine.ts');
  assert.ok(
    ![...claudeNineClosure].some((f) => f.endsWith('bridges/openclaw.ts')),
    'claude-nine closure must not reach the openclaw bridge module',
  );
  const openclawClosure = moduleClosure('bridges/openclaw.ts');
  assert.ok(
    ![...openclawClosure].some((f) => f.endsWith('bridges/claude-nine.ts')),
    'openclaw closure must not reach the claude-nine bridge module',
  );

  for (const spec of importSpecifiers(claudeNineEntry)) {
    assert.ok(!spec.includes('openclaw'), `claude-nine imports ${spec}`);
  }
  for (const spec of importSpecifiers(openclawEntry)) {
    assert.ok(!spec.includes('claude-nine'), `openclaw imports ${spec}`);
  }
  // The shared machinery is harness-neutral: it imports no bridge.
  const sharedEntry = join(srcRoot, 'bridges', 'host-bridge.ts');
  for (const spec of importSpecifiers(sharedEntry)) {
    assert.ok(!spec.includes('openclaw'), `host-bridge imports ${spec}`);
    assert.ok(!spec.includes('claude-nine'), `host-bridge imports ${spec}`);
  }
  // Every file in the bridges directory is one of the four known modules.
  const bridgeFiles = readdirSync(join(srcRoot, 'bridges')).sort();
  assert.deepEqual(bridgeFiles, [
    'claude-nine.ts',
    'host-bridge.ts',
    'openclaw.ts',
    'parity.ts',
  ]);
});

// ---------------------------------------------------------------------------
// State authority: one store, one mode, both bridges
// ---------------------------------------------------------------------------

test('bridges: state authority is shared, a session created through one bridge runs and is read through the other', async () => {
  const dir = tempBridgeDir('shared-state');
  const sample = buildSampleSession();
  const descriptor: ProviderRouteDescriptor = {
    ...FIXED_DESCRIPTOR,
    routeId: sample.spec.model_policy.route_id,
    modelId: sample.spec.model_policy.requested_model_id as string,
  };
  const bindings = (delegate: ModelTransport) => [
    {
      routeId: descriptor.routeId,
      delegate,
      reportAttempt: () => {
        throw new Error('factory must wire reportAttempt');
      },
      policy: sample.spec.model_policy,
      scope: sample.scope,
    },
  ];

  const openclaw = createOpenClawBridge({
    dataDir: dir,
    routes: [descriptor],
    bindings: bindings(new DeterministicFixtureTransport()),
  });
  const createEngine = new CouncilEngine(openclaw.host);
  await createEngine.createSession({ ...sample, sample: true });
  const viaOpenclaw = await openclaw.store.getSession(sample.spec.session_id);
  assert.ok(viaOpenclaw);
  assert.equal(viaOpenclaw?.sample, true);

  const claudeNine = createClaudeNineBridge({
    dataDir: dir,
    routes: [descriptor],
    bindings: bindings(new DeterministicFixtureTransport()),
  });
  assert.equal(claudeNine.dataDir, openclaw.dataDir);
  const grant = buildTestGrant(sample.spec, sample.scope);
  claudeNine.host.authorize = {
    async resolveRunGrant(grantRef: string, sessionId: string) {
      return grantRef === 'test-grant' && sessionId === sample.spec.session_id
        ? grant
        : null;
    },
  };
  const runEngine = new CouncilEngine(claudeNine.host);
  const done = await runEngine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');

  const verdict = await openclaw.store.getVerdict(sample.spec.session_id);
  assert.ok(verdict);
  assert.equal(verdict?.result_kind, 'scored');
});

test('bridges: state-authority mode is local_interactive_owner on both bridges and a different mode fails closed', () => {
  const openclaw = createOpenClawBridge({ dataDir: tempBridgeDir('mode-oc') });
  const claudeNine = createClaudeNineBridge({ dataDir: tempBridgeDir('mode-cn') });
  assert.equal(openclaw.authorityMode, 'local_interactive_owner');
  assert.equal(claudeNine.authorityMode, 'local_interactive_owner');

  for (const make of [
    () =>
      createOpenClawBridge({
        dataDir: tempBridgeDir('mode-bad'),
        authorityMode: 'command_center',
      }),
    () =>
      createClaudeNineBridge({
        dataDir: tempBridgeDir('mode-bad'),
        authorityMode: 'managed_principal',
      }),
  ]) {
    assert.throws(
      make,
      (err: unknown) =>
        err instanceof Error &&
        (err as { code?: string }).code === 'COUNCIL_FEATURE_NOT_READY',
    );
  }
});

test('bridges: both Claude config roots share the one data profile', () => {
  const dir = tempBridgeDir('shared-profile');
  const previous = process.env.BLACKCEO_COUNCIL_DATA_DIR;
  process.env.BLACKCEO_COUNCIL_DATA_DIR = dir;
  try {
    const fromClaude = createClaudeNineBridge({ configRoot: '.claude' });
    const fromNine = createClaudeNineBridge({ configRoot: '.claude-nine' });
    assert.equal(fromClaude.configRoot, '.claude');
    assert.equal(fromNine.configRoot, '.claude-nine');
    assert.equal(fromClaude.dataDir, dir);
    assert.equal(fromNine.dataDir, dir);
    assert.equal(fromClaude.dataDir, fromNine.dataDir);
  } finally {
    if (previous === undefined) delete process.env.BLACKCEO_COUNCIL_DATA_DIR;
    else process.env.BLACKCEO_COUNCIL_DATA_DIR = previous;
  }
});

// ---------------------------------------------------------------------------
// The blackceo-council CLI through each bridge (sample mode)
// ---------------------------------------------------------------------------

function captureIo(): { io: CliIo; out: () => string; err: () => string } {
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

async function sampleThroughBridge(
  harness: 'openclaw' | 'claude-nine',
): Promise<{ out: string; journalAccepted: number; routeChanges: number }> {
  const dir = tempBridgeDir(`cli-${harness}`);
  const sample = buildSampleSession();
  const descriptor: ProviderRouteDescriptor = {
    ...FIXED_DESCRIPTOR,
    routeId: sample.spec.model_policy.route_id,
    modelId: sample.spec.model_policy.requested_model_id as string,
  };
  const makeBridge = (withGrant: boolean) => {
    const shared = {
      dataDir: dir,
      routes: [descriptor],
      bindings: [
        {
          routeId: descriptor.routeId,
          delegate: new DeterministicFixtureTransport(),
          reportAttempt: () => {
            throw new Error('factory must wire reportAttempt');
          },
          policy: sample.spec.model_policy,
          scope: sample.scope,
        },
      ],
    };
    const bridge =
      harness === 'openclaw'
        ? createOpenClawBridge(shared)
        : createClaudeNineBridge(shared);
    if (withGrant) {
      const grant = buildTestGrant(sample.spec, sample.scope);
      bridge.host.authorize = {
        async resolveRunGrant(grantRef: string, sessionId: string) {
          return grantRef === 'test-grant' && sessionId === sample.spec.session_id
            ? grant
            : null;
        },
      };
    }
    return bridge;
  };

  const bridge = makeBridge(true);
  const engine = new CouncilEngine(bridge.host);
  await engine.createSession({ ...sample, sample: true });
  const done = await engine.startSession(sample.spec.session_id, 'test-grant');
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine.getVerdict(sample.spec.session_id);
  assert.ok(verdict && verdict.result_kind === 'scored');
  if (verdict && verdict.result_kind === 'scored') {
    const scores = new Map(
      verdict.option_scores.map((s) => [s.option_id, s.display_score]),
    );
    assert.equal(scores.get('A'), 6.0);
    assert.equal(scores.get('B'), 7.6);
    assert.equal(scores.get('C'), 6.6);
    assert.equal(verdict.label, 'WAIT');
    assert.equal(verdict.recommended_option_id, 'B');
  }
  const journalAccepted = bridge.journal
    .list()
    .filter((r) => r.outcome.outcome === 'accepted').length;
  assert.ok(journalAccepted > 0);
  assert.ok(
    bridge.journal.list().every((r) => r.harness === harness),
    'every journal record names the harness that produced it',
  );

  // The dispatcher itself, composed through this bridge's factory.
  const c = captureIo();
  const code = await runCli(
    ['verdict', sample.spec.session_id, '--data-dir', dir],
    c.io,
    { createHost: () => makeBridge(false) },
  );
  assert.equal(code, 0, c.err());
  return {
    out: c.out(),
    journalAccepted,
    routeChanges: bridge.journal.routeChanges().length,
  };
}

test('cli through the OpenClaw bridge: sample run completes with the SAMPLE SESSION label and golden values', async () => {
  const result = await sampleThroughBridge('openclaw');
  assert.ok(result.out.includes('SAMPLE SESSION'));
  assert.ok(result.out.includes('Verdict for session sess-fixture-1: WAIT'));
  assert.ok(result.out.includes('Recommended option: B'));
  assert.ok(result.out.includes('Option A: 6.0'));
  assert.ok(result.out.includes('Option B: 7.6'));
  assert.ok(result.out.includes('Option C: 6.6'));
  assert.equal(result.routeChanges, 0);
});

test('cli through the Claude-Nine bridge: sample run completes with the SAMPLE SESSION label and golden values', async () => {
  const result = await sampleThroughBridge('claude-nine');
  assert.ok(result.out.includes('SAMPLE SESSION'));
  assert.ok(result.out.includes('Verdict for session sess-fixture-1: WAIT'));
  assert.ok(result.out.includes('Recommended option: B'));
  assert.ok(result.out.includes('Option A: 6.0'));
  assert.ok(result.out.includes('Option B: 7.6'));
  assert.ok(result.out.includes('Option C: 6.6'));
  assert.equal(result.routeChanges, 0);
});

test('cli through bridges: doctor reports the bridge-composed route as live', async () => {
  for (const harness of ['openclaw', 'claude-nine'] as const) {
    const dir = tempBridgeDir(`doctor-${harness}`);
    const descriptor: ProviderRouteDescriptor = {
      ...FIXED_DESCRIPTOR,
      routeId: 'route-fixture-1',
      modelId: 'model-selected-by-client',
    };
    const makeBridge = () => {
      const shared = {
        dataDir: dir,
        routes: [descriptor],
        bindings: [
          {
            routeId: descriptor.routeId,
            delegate: new CountingTransport(),
            reportAttempt: () => {
              throw new Error('factory must wire reportAttempt');
            },
            policy: policyFor(descriptor),
          },
        ],
      };
      return harness === 'openclaw'
        ? createOpenClawBridge(shared)
        : createClaudeNineBridge(shared);
    };
    const c = captureIo();
    const code = await runCli(['doctor', '--json', '--data-dir', dir], c.io, {
      createHost: () => makeBridge(),
    });
    assert.equal(code, 0, c.err());
    const data = JSON.parse(c.out()) as {
      checks: Array<{ name: string; ok: boolean; detail: string }>;
    };
    const live = data.checks.find((x) => x.name === 'live_routes_composed');
    assert.equal(live?.ok, true);
    assert.ok(live?.detail.includes('route-fixture-1'));
  }
});

// ---------------------------------------------------------------------------
// Parity surface for CWE-040
// ---------------------------------------------------------------------------

test('parity: runParityCheck produces a canonical outcome for every fixture', () => {
  const { ok, results } = runParityCheck(PARITY_FIXTURES);
  assert.equal(ok, true);
  assert.equal(results.length, PARITY_FIXTURES.length);
  const byName = new Map(results.map((r) => [r.name, r.summary]));
  assert.equal(
    byName.get('fixed route reaches execution unchanged')?.outcome,
    'accepted',
  );
  assert.equal(
    byName.get('cascade substitution refused under fallback policy none')?.outcome,
    'refused',
  );
  assert.equal(
    byName.get('approved substitution recorded under client approved only')?.outcome,
    'substituted_with_approval',
  );
  assert.equal(
    byName.get('hidden identity accepted with the exact statement')?.identityStatement,
    HIDDEN_IDENTITY_STATEMENT,
  );
  assert.equal(
    byName.get('combination outsider refused')?.outcome,
    'refused',
  );
  for (const result of results) {
    assert.match(result.outcomeHash, /^[0-9a-f]{64}$/);
  }
});

test('parity: runBridgeParity proves both bridges behave identically on every fixture', async () => {
  const { ok, results } = await runBridgeParity(PARITY_FIXTURES);
  assert.equal(results.length, PARITY_FIXTURES.length);
  for (const result of results) {
    assert.equal(result.equal, true, `fixture diverged: ${result.name}`);
  }
  assert.equal(ok, true);
});

test('parity: the summary surface detects divergence between different attempts', () => {
  const entry = buildRouteCatalog([FIXED_DESCRIPTOR])[0];
  const selection = createRouteSelection(
    entry,
    { routeId: entry.routeId },
    trustedScopeFromScopeFields(localScope()),
    { routeRevision: 1, createdAt: '2026-01-01T00:00:00Z' },
  );
  const accepted = summarizeResolutionOutcome(
    applyHostResolution(selection, {
      source: 'explicit_route',
      attemptedModelId: 'model-selected-by-client',
    }),
  );
  const refused = summarizeResolutionOutcome(
    applyHostResolution(selection, {
      source: 'cascade',
      attemptedModelId: 'model-someone-else',
    }),
  );
  assert.notDeepEqual(accepted, refused);
});

// ---------------------------------------------------------------------------
// The generated 999 host wrapper (CWE-040 consumes the template)
// ---------------------------------------------------------------------------

test('claude-nine wrapper: the generated wrapper template composes only the Claude-Nine bridge', () => {
  assert.equal(CLAUDE_NINE_WRAPPER_FILE_NAME, 'claude-nine-host-wrapper.mjs');
  const source = renderClaudeNineWrapper();
  assert.ok(source.includes('createClaudeNineBridge'));
  assert.ok(source.includes('runCli'));
  const importLines = source
    .split('\n')
    .filter((line) => line.trim().startsWith('import'));
  assert.ok(importLines.length >= 2);
  for (const line of importLines) {
    assert.ok(!line.includes('openclaw'), `wrapper imports another host tree: ${line}`);
  }
});
