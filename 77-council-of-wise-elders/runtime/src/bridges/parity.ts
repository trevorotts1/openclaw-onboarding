/**
 * Bridge parity check surface (CWE-010; directive Sections 13, 34).
 *
 * CWE-040 verifies that both harnesses produce the same catalog
 * behavior for the same selection. This module is that surface: a
 * deterministic fixture set plus two checkers.
 *
 * - runParityCheck runs each fixture's selection and resolution attempt
 *   through the shared catalog semantics each bridge is built on and
 *   reports a canonical summary per fixture. Both harnesses must
 *   produce byte-identical summaries.
 * - runBridgeParity goes end to end: it composes the REAL OpenClaw
 *   bridge and the REAL Claude-Nine bridge per fixture (temporary data
 *   directories, fixture delegates that only count calls), feeds the
 *   fixture attempt through each bridge's own resolver port and guard,
 *   and compares the journal outcomes and whether the delegate was
 *   reached. This is the check that proves the isolation did not fork
 *   the semantics: the resolvers differ per harness, the catalog
 *   behavior does not.
 *
 * This module is a verification surface, not a runtime path for either
 * bridge; importing both bridges here does not put either bridge in the
 * other's runtime graph.
 */

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { canonicalHash, type ScopeFields } from '../contracts/index.js';
import type { ModelTransport, TransportRequest } from '../cli/host-ports.js';
import {
  applyHostResolution,
  buildRouteCatalog,
  createRouteSelection,
  findCatalogEntry,
  scopeFieldsFromTrustedScope,
  type HostResolutionAttempt,
  type ProviderRouteDescriptor,
  type RouteEvidence,
  type RouteResolutionOutcome,
  type RouteSelectionRequest,
  type TrustedScope,
} from './host-bridge.js';
import { createOpenClawBridge, type OpenClawResolutionReport } from './openclaw.js';
import {
  createClaudeNineBridge,
  type ClaudeNineResolutionReport,
} from './claude-nine.js';

export interface ParityFixture {
  name: string;
  descriptor: ProviderRouteDescriptor;
  evidence?: RouteEvidence;
  request: RouteSelectionRequest;
  scope: TrustedScope;
  attempt: HostResolutionAttempt;
}

/** Canonical, timestamp-free summary of one resolution outcome. */
export interface ResolutionSummary {
  outcome: RouteResolutionOutcome['outcome'];
  effectiveModelId: string | null;
  identityLevel: RouteResolutionOutcome['identityLevel'];
  identityStatement: string | null;
  changeRecord: RouteResolutionOutcome['changeRecord'];
  eventTypes: string[];
}

export function summarizeResolutionOutcome(
  outcome: RouteResolutionOutcome,
): ResolutionSummary {
  return {
    outcome: outcome.outcome,
    effectiveModelId: outcome.effectiveModelId,
    identityLevel: outcome.identityLevel,
    identityStatement: outcome.identityStatement,
    changeRecord: outcome.changeRecord,
    eventTypes: outcome.events.map((e) => e.type),
  };
}

export interface ParityFixtureResult {
  name: string;
  summary: ResolutionSummary;
  outcomeHash: string;
}

export function runParityCheck(fixtures: ParityFixture[]): {
  ok: boolean;
  results: ParityFixtureResult[];
} {
  const results = fixtures.map((fixture) => {
    const catalog = buildRouteCatalog(
      [fixture.descriptor],
      fixture.evidence
        ? new Map([[fixture.descriptor.routeId, fixture.evidence]])
        : new Map(),
    );
    const entry = findCatalogEntry(catalog, fixture.descriptor.routeId);
    if (!entry) {
      throw new Error(`Parity fixture ${fixture.name}: route missing from catalog.`);
    }
    const selection = createRouteSelection(entry, fixture.request, fixture.scope, {
      routeRevision: 1,
      createdAt: '2026-01-01T00:00:00Z',
    });
    const summary = summarizeResolutionOutcome(
      applyHostResolution(selection, fixture.attempt),
    );
    return { name: fixture.name, summary, outcomeHash: canonicalHash(summary) };
  });
  return { ok: true, results };
}

// ---------------------------------------------------------------------------
// End-to-end bridge parity.
// ---------------------------------------------------------------------------

const FIXTURE_MODEL_POLICY = {
  selection: 'explicit' as const,
  route_id: '',
  requested_model_id: null,
  reasoning_preference: null,
  fallback_policy: 'none' as const,
};

function fixtureRequest(fixture: ParityFixture): TransportRequest {
  return {
    purpose: 'advisor',
    session_id: 'sess-parity-fixture',
    seat_id: 'simon-sinek',
    round: 1,
    route_id: fixture.descriptor.routeId,
    model_policy: {
      ...FIXTURE_MODEL_POLICY,
      route_id: fixture.descriptor.routeId,
      requested_model_id: fixture.descriptor.modelId,
      fallback_policy: fixture.request.fallbackPolicy ?? 'none',
    },
    system: 'parity fixture',
    input: {},
  };
}

function openClawReportFor(attempt: HostResolutionAttempt): OpenClawResolutionReport {
  const viaReplacementPoint =
    attempt.source === 'cascade'
      ? 'purpose-tier-cascade'
      : attempt.source === 'sovereign_default'
        ? 'department-default-resolution'
        : attempt.source === 'runtime_reconcile'
          ? 'runtime-model-reconcile'
          : attempt.source === 'fallback'
            ? 'agent-model-fallback-array'
            : null;
  return {
    attemptedModelId: attempt.attemptedModelId,
    reportedModelId: attempt.reportedModelId ?? null,
    proseClaimedModelId: attempt.proseClaimedModelId ?? null,
    approval: attempt.approval ?? null,
    viaReplacementPoint,
  };
}

function claudeNineReportFor(
  attempt: HostResolutionAttempt,
): ClaudeNineResolutionReport {
  return {
    attemptedModelId: attempt.attemptedModelId,
    reportedModelId: attempt.reportedModelId ?? null,
    proseClaimedModelId: attempt.proseClaimedModelId ?? null,
    approval: attempt.approval ?? null,
    viaCombinationMember: attempt.source === 'combination_member',
  };
}

interface BridgeRunResult {
  summary: ResolutionSummary | null;
  delegateCalls: number;
  refused: boolean;
}

async function runFixtureThroughBridge(
  fixture: ParityFixture,
  harness: 'openclaw' | 'claude-nine',
): Promise<BridgeRunResult> {
  const dataDir = mkdtempSync(join(tmpdir(), `cwe010-parity-${harness}-`));
  let delegateCalls = 0;
  const delegate: ModelTransport = {
    async generate() {
      delegateCalls += 1;
      return {
        text: '{}',
        provider_request_id: 'parity-fixture',
        reported_model_id: null,
        usage: { input_tokens: null, output_tokens: null },
      };
    },
  };
  const scope: ScopeFields = scopeFieldsFromTrustedScope(fixture.scope);
  const shared = {
    dataDir,
    scope,
    routes: [fixture.descriptor],
    evidenceByRouteId: fixture.evidence
      ? new Map([[fixture.descriptor.routeId, fixture.evidence]])
      : new Map(),
    bindings: [
      {
        routeId: fixture.descriptor.routeId,
        delegate,
        // Placeholder that must never run: each bridge factory replaces
        // reportAttempt with its own resolver wiring before composing.
        reportAttempt: () => {
          throw new Error('Bridge factory did not wire reportAttempt.');
        },
        request: fixture.request,
        scope,
      },
    ],
  };
  const report = fixture.attempt;
  const bridge =
    harness === 'openclaw'
      ? createOpenClawBridge({
          ...shared,
          resolver: { reportResolution: () => openClawReportFor(report) },
        })
      : createClaudeNineBridge({
          ...shared,
          resolver: { reportResolution: () => claudeNineReportFor(report) },
        });
  const transport = bridge.host.transportRegistry.resolve(fixture.descriptor.routeId);
  if (!transport) throw new Error(`Parity fixture ${fixture.name}: no transport.`);
  let refused = false;
  try {
    await transport.generate(fixtureRequest(fixture));
  } catch {
    refused = true;
  }
  const records = bridge.journal.list();
  const last = records[records.length - 1];
  return {
    summary: last ? summarizeResolutionOutcome(last.outcome) : null,
    delegateCalls,
    refused,
  };
}

export interface BridgeParityResult {
  name: string;
  equal: boolean;
  openclaw: BridgeRunResult;
  claudeNine: BridgeRunResult;
}

export async function runBridgeParity(
  fixtures: ParityFixture[],
): Promise<{ ok: boolean; results: BridgeParityResult[] }> {
  const results: BridgeParityResult[] = [];
  for (const fixture of fixtures) {
    const openclaw = await runFixtureThroughBridge(fixture, 'openclaw');
    const claudeNine = await runFixtureThroughBridge(fixture, 'claude-nine');
    const equal =
      canonicalHash(openclaw.summary) === canonicalHash(claudeNine.summary) &&
      openclaw.delegateCalls === claudeNine.delegateCalls &&
      openclaw.refused === claudeNine.refused;
    results.push({ name: fixture.name, equal, openclaw, claudeNine });
  }
  return { ok: results.every((r) => r.equal), results };
}

// ---------------------------------------------------------------------------
// The deterministic parity fixture set. Same selection in, same catalog
// behavior out, on both harnesses.
// ---------------------------------------------------------------------------

const PARITY_SCOPE: TrustedScope = {
  tenantId: 'parity-tenant',
  companyId: 'parity-company',
  installationId: 'parity-installation',
  ownerSubject: 'parity-owner',
};

const FIXED_DESCRIPTOR: ProviderRouteDescriptor = {
  routeId: 'route-parity-fixed',
  providerSlug: 'parity-provider',
  displayLabel: 'Parity fixed route',
  kind: 'fixed_model',
  modelId: 'model-parity-selected',
  combinationMembers: [],
  providerAccountRef: 'parity-account',
  capability: {
    contextWindowTokens: 128000,
    maxOutputTokens: 4096,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  },
  credential: { state: 'not_required', envVar: null, source: null, checked: [] },
};

const COMBINATION_DESCRIPTOR: ProviderRouteDescriptor = {
  routeId: 'route-parity-combo',
  providerSlug: 'parity-router',
  displayLabel: 'Parity combination route',
  kind: 'combination',
  modelId: null,
  combinationMembers: ['model-parity-member-a', 'model-parity-member-b'],
  providerAccountRef: 'parity-account',
  capability: {
    contextWindowTokens: null,
    maxOutputTokens: null,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  },
  credential: { state: 'not_required', envVar: null, source: null, checked: [] },
};

export const PARITY_FIXTURES: ParityFixture[] = [
  {
    name: 'fixed route reaches execution unchanged',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'explicit_route',
      attemptedModelId: 'model-parity-selected',
      reportedModelId: null,
    },
  },
  {
    name: 'cascade substitution refused under fallback policy none',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed', fallbackPolicy: 'none' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'cascade',
      attemptedModelId: 'model-parity-cheaper',
      reportedModelId: null,
    },
  },
  {
    name: 'department default substitution refused under fallback policy none',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed', fallbackPolicy: 'none' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'sovereign_default',
      attemptedModelId: 'model-parity-dept-default',
      reportedModelId: null,
    },
  },
  {
    name: 'approved substitution recorded under client approved only',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed', fallbackPolicy: 'client_approved_only' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'fallback',
      attemptedModelId: 'model-parity-approved-fallback',
      reportedModelId: null,
      approval: {
        approvalRef: 'approval-parity-1',
        reason: 'Selected route unavailable; client approved the change.',
        costImplication: 'Stated in the approval record.',
      },
    },
  },
  {
    name: 'substitution without approval refused under client approved only',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed', fallbackPolicy: 'client_approved_only' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'fallback',
      attemptedModelId: 'model-parity-unapproved',
      reportedModelId: null,
    },
  },
  {
    name: 'reported identity conflict refused',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'explicit_route',
      attemptedModelId: 'model-parity-selected',
      reportedModelId: 'model-parity-someone-else',
    },
  },
  {
    name: 'hidden identity accepted with the exact statement',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'explicit_route',
      attemptedModelId: null,
      reportedModelId: null,
    },
  },
  {
    name: 'prose identity claim ignored, route accepted unchanged',
    descriptor: FIXED_DESCRIPTOR,
    request: { routeId: 'route-parity-fixed' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'explicit_route',
      attemptedModelId: 'model-parity-selected',
      reportedModelId: null,
      proseClaimedModelId: 'model-parity-prose-claim',
    },
  },
  {
    name: 'combination member resolved and logged',
    descriptor: COMBINATION_DESCRIPTOR,
    request: { routeId: 'route-parity-combo' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'combination_member',
      attemptedModelId: 'model-parity-member-b',
      reportedModelId: null,
    },
  },
  {
    name: 'combination outsider refused',
    descriptor: COMBINATION_DESCRIPTOR,
    request: { routeId: 'route-parity-combo' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'combination_member',
      attemptedModelId: 'model-parity-outsider',
      reportedModelId: null,
    },
  },
  {
    name: 'combination hidden member accepted with the exact statement',
    descriptor: COMBINATION_DESCRIPTOR,
    request: { routeId: 'route-parity-combo' },
    scope: PARITY_SCOPE,
    attempt: {
      source: 'combination_member',
      attemptedModelId: null,
      reportedModelId: null,
    },
  },
];
