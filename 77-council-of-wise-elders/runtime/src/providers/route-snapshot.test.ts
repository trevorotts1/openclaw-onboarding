/**
 * WER-006 route-snapshot contract tests.
 *
 * Runner (the runtime's own runner):
 *   node --import tsx --test src/providers/route-snapshot.test.ts
 *
 * Tier A only: no network, no credentials, no provider dispatch, no live
 * probe. The bounded probe/transport work is deliberately deferred.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { TransportError } from './errors.js';
import type { CouncilRouteSelection } from './selection.js';
import {
  ROUTE_SNAPSHOT_SCHEMA,
  UNKNOWN_ROUTE_IDENTITY,
  computeRouteSnapshotSha256,
  freezeRouteSnapshot,
  requirePermittedCombinationMember,
  verifyRouteSnapshotHash,
  withTransportReportedIdentity,
  type RouteSnapshotDraft,
  type RouteSnapshotReasoning,
} from './route-snapshot.js';

const POLICY_SHA = 'a'.repeat(64);

function selection(overrides: Partial<CouncilRouteSelection> = {}): CouncilRouteSelection {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-elders-primary',
    routeRevision: 3,
    routeKind: 'fixed_model',
    providerSlug: 'openai_compatible',
    requestedRoute: 'elders.primary',
    requestedModelOrAlias: 'gpt-5.1',
    combinationMembers: null,
    reasoning: { requested: 'high', applied: 'high', supported: true, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: 'acct-operator-1',
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 32000,
      capabilities: ['chat'],
      supportedReasoningLevels: ['low', 'medium', 'high'],
    },
    credential: {
      state: 'present',
      envVar: 'OPENAI_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: 'tenant-1',
      companyId: 'company-1',
      installationId: 'install-1',
      ownerSubject: 'owner-1',
    },
    createdAt: '2026-10-18T10:00:00.000Z',
    ...overrides,
  };
}

function reasoning(overrides: Partial<RouteSnapshotReasoning> = {}): RouteSnapshotReasoning {
  return {
    requested: 'high',
    supported: ['low', 'medium', 'high'],
    applied: 'high',
    limitation: null,
    paramStyle: 'reasoning_effort',
    ...overrides,
  };
}

function draft(overrides: Partial<RouteSnapshotDraft> = {}): RouteSnapshotDraft {
  return {
    selection: selection(),
    sessionId: 'session-1',
    sessionOwner: 'owner-1',
    host: {
      baseUrl: 'https://api.example.test/v1',
      configProfile: 'operator-default',
      apiFamily: 'openai_compatible',
    },
    reasoning: reasoning(),
    capabilityVersion: 'catalog-2026-10-18',
    policySha256: POLICY_SHA,
    limits: { requestsPerMinute: 600, tokensPerMinute: 200000, maxConcurrency: 8 },
    createdAt: '2026-10-18T10:00:01.000Z',
    ...overrides,
  };
}

test('publishes an explicit schema id, a stable hash, and a verified pin', () => {
  const snap = freezeRouteSnapshot(draft());
  assert.equal(snap.schema, ROUTE_SNAPSHOT_SCHEMA);
  assert.match(snap.snapshotSha256, /^[0-9a-f]{64}$/);
  assert.equal(verifyRouteSnapshotHash(snap), true);
  assert.equal(computeRouteSnapshotSha256(snap), snap.snapshotSha256);
  assert.equal(snap.selection.routeId, 'route-elders-primary');
  assert.equal(snap.identity.configured.accountRef, 'acct-operator-1');
  assert.equal(snap.identity.configured.modelId, 'gpt-5.1');
  assert.equal(snap.capabilityVersion, 'catalog-2026-10-18');
  assert.equal(snap.policySha256, POLICY_SHA);
  assert.equal(snap.limits.maxConcurrency, 8);
});

test('snapshot hash is stable across serialization and deep-frozen', () => {
  const snap = freezeRouteSnapshot(draft());
  const roundTripped = JSON.parse(JSON.stringify(snap)) as typeof snap;
  assert.equal(computeRouteSnapshotSha256(roundTripped), snap.snapshotSha256);
  assert.equal(verifyRouteSnapshotHash(roundTripped), true);
  assert.equal(Object.isFrozen(snap), true);
  assert.equal(Object.isFrozen(snap.identity.configured), true);
  assert.equal(Object.isFrozen(snap.limits), true);
  assert.throws(() => {
    (snap as { host: { baseUrl: string } }).host.baseUrl = 'https://evil.test';
  }, TypeError);
});

test('configured identity and transport-reported identity are separate; unreported stays UNKNOWN', () => {
  const snap = freezeRouteSnapshot(draft());
  assert.deepEqual(snap.identity.transportReported, {
    state: 'unknown',
    modelId: UNKNOWN_ROUTE_IDENTITY,
    reason: 'probe_deferred',
  });

  const observed = withTransportReportedIdentity(snap, {
    state: 'reported',
    modelId: 'gpt-5.1',
    providerRequestId: 'req_123',
  });

  assert.equal(observed.identity.transportReported.state, 'reported');
  assert.equal(observed.identity.configured.modelId, 'gpt-5.1');
  // The pin is untouched by evidence: same schema, same hash, and the
  // OBSERVED snapshot still satisfies that hash when recomputed.
  assert.equal(observed.snapshotSha256, snap.snapshotSha256);
  assert.equal(verifyRouteSnapshotHash(observed), true);
  assert.equal(computeRouteSnapshotSha256(observed), snap.snapshotSha256);
  // The original snapshot was not mutated.
  assert.equal(snap.identity.transportReported.state, 'unknown');
});

test('a contradicting transport report is refused, never relabelled', () => {
  const snap = freezeRouteSnapshot(draft());
  assert.throws(
    () =>
      withTransportReportedIdentity(snap, {
        state: 'reported',
        modelId: 'some-other-model',
        providerRequestId: null,
      }),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_MISMATCH',
  );
});

test('changing a global default profile does NOT reroute an already-frozen snapshot', () => {
  const defaults = { configProfile: 'operator-default' };
  const source = draft({
    host: {
      baseUrl: 'https://api.example.test/v1',
      configProfile: defaults.configProfile,
      apiFamily: 'openai_compatible',
    },
  });
  const snap = freezeRouteSnapshot(source);
  const before = snap.snapshotSha256;

  // Someone changes the global default and mutates the objects the
  // snapshot was built from.
  defaults.configProfile = 'operator-default-v2';
  source.host.configProfile = 'operator-default-v2';
  source.selection.requestedModelOrAlias = 'other-model';

  assert.equal(snap.host.configProfile, 'operator-default');
  assert.equal(snap.selection.requestedModelOrAlias, 'gpt-5.1');
  assert.equal(snap.snapshotSha256, before);
  assert.equal(verifyRouteSnapshotHash(snap), true);

  // A NEW session frozen under the new default is genuinely different.
  const rerouted = freezeRouteSnapshot(
    draft({
      host: {
        baseUrl: 'https://api.example.test/v1',
        configProfile: defaults.configProfile,
        apiFamily: 'openai_compatible',
      },
    }),
  );
  assert.equal(rerouted.host.configProfile, 'operator-default-v2');
  assert.notEqual(rerouted.snapshotSha256, before);
});

test('two concurrent sessions selecting different aliases stay isolated', async () => {
  const freeze = async (sessionId: string, alias: string) =>
    freezeRouteSnapshot(
      draft({
        sessionId,
        selection: selection({ requestedModelOrAlias: alias, routeId: `route-${alias}` }),
      }),
    );

  const [a, b] = await Promise.all([
    freeze('session-a', 'model-a'),
    freeze('session-b', 'model-b'),
  ]);

  assert.equal(a.snapshotSha256 !== b.snapshotSha256, true);
  assert.equal(a.selection.requestedModelOrAlias, 'model-a');
  assert.equal(b.selection.requestedModelOrAlias, 'model-b');
  assert.equal(a.identity.configured.modelId, 'model-a');
  assert.equal(b.identity.configured.modelId, 'model-b');

  const aObserved = withTransportReportedIdentity(a, {
    state: 'reported',
    modelId: 'model-a',
    providerRequestId: 'req_a',
  });
  assert.equal(b.identity.transportReported.state, 'unknown');
  assert.equal(aObserved.identity.transportReported.modelId, 'model-a');
});

test('an unsupported effort raises a concrete error and never substitutes', () => {
  assert.throws(
    () =>
      freezeRouteSnapshot(
        draft({ reasoning: reasoning({ requested: 'max', applied: null, supported: ['low', 'high'] }) }),
      ),
    (error: unknown) =>
      error instanceof TransportError &&
      error.code === 'TRANSPORT_REASONING_UNSUPPORTED' &&
      /"max"/.test(error.message),
  );

  // Applied differing from requested is the silent-substitution shape.
  assert.throws(
    () =>
      freezeRouteSnapshot(
        draft({ reasoning: reasoning({ requested: 'high', applied: 'medium', supported: ['low', 'medium', 'high'] }) }),
      ),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_REASONING_UNSUPPORTED',
  );
});

test('a level with no verified wire mapping is refused, not renamed', () => {
  assert.throws(
    () =>
      freezeRouteSnapshot(
        draft({ reasoning: reasoning({ requested: 'high', applied: 'high', paramStyle: 'none' }) }),
      ),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_REASONING_UNMAPPED',
  );
});

test('combination members are pinned, all UNKNOWN until reported, and non-members refused', () => {
  const snap = freezeRouteSnapshot(
    draft({
      selection: selection({
        routeKind: 'combination',
        requestedModelOrAlias: 'elders-trio',
        combinationMembers: ['model-a', 'model-b', 'model-c'],
      } as Partial<CouncilRouteSelection>),
    }),
  );

  assert.deepEqual(
    snap.identity.combinationMembers?.map((member) => member.reported.state),
    ['unknown', 'unknown', 'unknown'],
  );
  assert.equal(snap.identity.combinationMembers?.[0].reported.modelId, UNKNOWN_ROUTE_IDENTITY);

  requirePermittedCombinationMember(snap, 'model-b');
  assert.throws(
    () => requirePermittedCombinationMember(snap, 'model-z'),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_COMBINATION_MEMBER_UNKNOWN',
  );
  assert.throws(
    () =>
      withTransportReportedIdentity(snap, {
        state: 'reported',
        modelId: 'model-z',
        providerRequestId: null,
      }),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_COMBINATION_MEMBER_UNKNOWN',
  );

  const observed = withTransportReportedIdentity(snap, {
    state: 'reported',
    modelId: 'model-b',
    providerRequestId: 'req_b',
  });
  assert.equal(observed.snapshotSha256, snap.snapshotSha256);
  assert.equal(observed.identity.transportReported.modelId, 'model-b');
  assert.equal(
    observed.identity.combinationMembers?.find((m) => m.memberModelId === 'model-b')?.reported
      .state,
    'reported',
  );
  // Recompute the pin from the OBSERVED snapshot. Asserting only
  // observed.snapshotSha256 === snap.snapshotSha256 reasserts the stale
  // published field and never proves the observed snapshot satisfies it.
  assert.equal(verifyRouteSnapshotHash(observed), true);
  assert.equal(computeRouteSnapshotSha256(observed), observed.snapshotSha256);
});

test('combination evidence does not move the pin: observed snapshot still satisfies its own hash', () => {
  const snap = freezeRouteSnapshot(
    draft({
      selection: selection({
        routeKind: 'combination',
        requestedModelOrAlias: 'elders-trio',
        combinationMembers: ['model-a', 'model-b', 'model-c'],
      } as Partial<CouncilRouteSelection>),
    }),
  );
  assert.equal(verifyRouteSnapshotHash(snap), true);
  const frozenHash = snap.snapshotSha256;

  // Two members report, plus the route-level report: the whole evidence
  // surface a combination route can carry.
  const observed = withTransportReportedIdentity(
    withTransportReportedIdentity(snap, {
      state: 'reported',
      modelId: 'model-b',
      providerRequestId: 'req_b',
    }),
    {
      state: 'reported',
      modelId: 'model-a',
      providerRequestId: 'req_a',
    },
  );

  // The evidence really landed — otherwise a vacuous pin would pass.
  assert.equal(
    observed.identity.combinationMembers?.filter((m) => m.reported.state === 'reported').length,
    2,
  );
  assert.equal(observed.identity.transportReported.state, 'reported');
  if (observed.identity.transportReported.state !== 'reported') {
    throw new Error('expected a reported route-level transport identity');
  }
  assert.equal(observed.identity.transportReported.modelId, 'model-a');

  // Evidence never changes the pin, and the observed snapshot verifies.
  assert.equal(observed.snapshotSha256, frozenHash);
  assert.equal(verifyRouteSnapshotHash(observed), true);
  assert.equal(computeRouteSnapshotSha256(observed), frozenHash);
  assert.equal(snap.identity.combinationMembers?.every((m) => m.reported.state === 'unknown'), true);
});

test('a genuinely mutated pin is refused — recompute, not the stale stamp', () => {
  const snap = freezeRouteSnapshot(
    draft({
      selection: selection({
        routeKind: 'combination',
        requestedModelOrAlias: 'elders-trio',
        combinationMembers: ['model-a', 'model-b', 'model-c'],
      } as Partial<CouncilRouteSelection>),
    }),
  );
  assert.equal(verifyRouteSnapshotHash(snap), true);

  // 1) Tampering with configured contract state: the published stamp is
  //    left untouched, so only a recomputation can catch it.
  const tampered = {
    ...snap,
    policySha256: 'b'.repeat(64),
  } as typeof snap;
  assert.notEqual(tampered.snapshotSha256, computeRouteSnapshotSha256(tampered));
  assert.equal(verifyRouteSnapshotHash(tampered), false);

  // 2) Tampering with the PINNED member set: same stale stamp, refused.
  const memberTampered = {
    ...snap,
    identity: {
      ...snap.identity,
      combinationMembers: [
        { memberModelId: 'model-z', reported: snap.identity.combinationMembers![0].reported },
        ...snap.identity.combinationMembers!.slice(1),
      ],
    },
  } as typeof snap;
  assert.equal(memberTampered.snapshotSha256, snap.snapshotSha256);
  assert.equal(verifyRouteSnapshotHash(memberTampered), false);

  // 3) A mutated pin must never have evidence attached to it.
  assert.throws(
    () =>
      withTransportReportedIdentity(tampered, {
        state: 'reported',
        modelId: 'model-b',
        providerRequestId: 'req_b',
      }),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_MISMATCH',
  );
  assert.throws(
    () =>
      withTransportReportedIdentity(memberTampered, {
        state: 'reported',
        modelId: 'model-b',
        providerRequestId: 'req_b',
      }),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_MISMATCH',
  );
});

test('empty or contradictory route shapes are refused', () => {
  assert.throws(
    () =>
      freezeRouteSnapshot(
        draft({
          selection: selection({
            routeKind: 'combination',
            requestedModelOrAlias: 'elders-trio',
            combinationMembers: [],
          } as Partial<CouncilRouteSelection>),
        }),
      ),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
  );

  assert.throws(
    () =>
      freezeRouteSnapshot(
        draft({
          selection: selection({ combinationMembers: ['model-a'] }),
        }),
      ),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
  );

  assert.throws(
    () => freezeRouteSnapshot(draft({ policySha256: 'not-a-hash' })),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
  );

  assert.throws(
    () => freezeRouteSnapshot(draft({ limits: { requestsPerMinute: -1, tokensPerMinute: null, maxConcurrency: null } })),
    (error: unknown) =>
      error instanceof TransportError && error.code === 'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
  );
});
