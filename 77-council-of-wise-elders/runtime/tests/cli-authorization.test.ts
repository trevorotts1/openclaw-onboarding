/**
 * CWE-049 tests: the standalone CLI authorization handlers
 * (src/cli/authorization.ts) in an isolated profile.
 *
 * - T135: a clean standalone profile creates a session, previews,
 *   explicitly approves through the controlling-terminal confirmation,
 *   and starts the session through a controlled (fixture) transport
 *   using the real stored grant: no fabricated grant ID, no manual
 *   SQL, no approval file.
 * - T136 (CLI half): headless approval is refused with
 *   RUN_AUTHORIZATION_REQUIRED and preserves the preview and draft;
 *   presenting a --yes flag changes nothing (no code path reads it).
 * - First standalone use provisions a stable installation UUID in
 *   protected configuration (mode 0600), and the same namespace is
 *   reused on later compositions.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import type { RunGrant, RunPreview } from '../src/contracts/index.js';
import { CouncilEngine } from '../src/cli/engine.js';
import { CouncilError } from '../src/cli/errors.js';
import { buildSampleSession, DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import { createLocalHost } from '../src/cli/local-host.js';
import {
  createStandaloneRunAuthorization,
  handleAuthorizationCommand,
  mirrorSession,
  resolveStandaloneInstallation,
  standaloneScope,
  withRunAuthorization,
} from '../src/cli/authorization.js';
import type { PinnedRouteSnapshot } from '../src/budgets/index.js';

function captureIo() {
  const chunks: string[] = [];
  return {
    io: { out: (t: string) => chunks.push(t), err: (t: string) => chunks.push(t) },
    text: () => chunks.join(''),
    json: () => JSON.parse(chunks.join('')) as Record<string, unknown>,
  };
}

test('T135: clean standalone profile: preview, explicit approve, start, status, revoke', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'cwe049-cli-'));
  // First use provisions the installation record, protected.
  const installation = resolveStandaloneInstallation(dataDir);
  assert.match(installation.installation_id, /^[0-9a-f-]{36}$/);
  assert.equal(statSync(join(dataDir, 'council-installation.json')).mode & 0o777, 0o600);
  assert.equal(
    resolveStandaloneInstallation(dataDir).installation_id,
    installation.installation_id,
    'the installation namespace is stable across uses',
  );
  const scopeFields = standaloneScope(installation);

  // A real session in the standalone host store, bound to the
  // provisioned scope.
  const sample = buildSampleSession();
  const { host } = createLocalHost({ dataDir });
  const engine = new CouncilEngine(host);
  await engine.createSession({ spec: sample.spec, brief: sample.brief, scope: scopeFields });
  const stored = await host.store.getSession(sample.spec.session_id);
  assert.ok(stored);

  // Mirror it into the authorization store (the standalone composition
  // CWE-050 finalizes), then drive the handlers.
  const composition = createStandaloneRunAuthorization({ dataDir });
  mirrorSession(composition, stored);
  composition.close();

  const snapshot: PinnedRouteSnapshot = {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: sample.spec.model_policy.route_id,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-fixture',
    requestedRoute: sample.spec.model_policy.route_id,
    requestedModelOrAlias: 'model-fixture',
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 8000,
      capabilities: ['text'],
      supportedReasoningLevels: null,
    },
    credential: {
      state: 'present',
      envVar: 'PROVIDER_FIXTURE_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: scopeFields.tenant_id,
      companyId: scopeFields.company_id,
      installationId: scopeFields.installation_id,
      ownerSubject: scopeFields.owner_subject,
    },
    createdAt: new Date().toISOString(),
  };
  const snapshotPath = join(dataDir, 'route-snapshot.json');
  writeFileSync(snapshotPath, JSON.stringify(snapshot), 'utf8');
  // limits.json proposes a requested envelope; it is NOT an approval.
  const limitsPath = join(dataDir, 'limits.json');
  writeFileSync(
    limitsPath,
    JSON.stringify({
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: { amount_minor: 100000, currency: 'USD' },
    }),
    'utf8',
  );

  const previewIo = captureIo();
  await handleAuthorizationCommand(
    'preview',
    [sample.spec.session_id],
    new Map<string, string | true>([
      ['route-snapshot', snapshotPath],
      ['limits', limitsPath],
    ]),
    { dataDir, json: true, io: previewIo.io },
  );
  const preview = (previewIo.json() as { preview: RunPreview }).preview;
  assert.ok(preview.preview_id);
  assert.equal(preview.session_id, sample.spec.session_id);

  // Headless approval, with a --yes flag presented: refused, and the
  // flag changes nothing.
  const headlessIo = captureIo();
  await assert.rejects(
    handleAuthorizationCommand(
      'approve',
      [],
      new Map<string, string | true>([
        ['preview', preview.preview_id],
        ['yes', true],
      ]),
      { dataDir, json: true, io: headlessIo.io },
    ),
    (error: unknown) =>
      error instanceof CouncilError && error.code === 'RUN_AUTHORIZATION_REQUIRED',
  );

  // Interactive approval: the handler renders the exact saved preview
  // to the controlling-terminal callback; only its true decision
  // approves.
  let rendered = '';
  const approveIo = captureIo();
  await handleAuthorizationCommand(
    'approve',
    [],
    new Map<string, string | true>([['preview', preview.preview_id]]),
    {
      dataDir,
      json: true,
      io: approveIo.io,
      confirmPreview: async (text) => {
        rendered = text;
        return true;
      },
    },
  );
  assert.ok(rendered.includes(preview.preview_sha256), 'the exact saved preview is rendered');
  const grant = (approveIo.json() as { grant: RunGrant }).grant;
  assert.equal(grant.status, 'active');
  assert.equal(grant.authority_mode, 'local_interactive_owner');
  assert.equal(grant.session_id, sample.spec.session_id);

  // A declined confirmation approves nothing (fresh preview).
  const preview2Io = captureIo();
  await handleAuthorizationCommand(
    'preview',
    [sample.spec.session_id],
    new Map<string, string | true>([['route-snapshot', snapshotPath]]),
    { dataDir, json: true, io: preview2Io.io },
  );
  const preview2 = (preview2Io.json() as { preview: RunPreview }).preview;
  await assert.rejects(
    handleAuthorizationCommand(
      'approve',
      [],
      new Map<string, string | true>([['preview', preview2.preview_id]]),
      {
        dataDir,
        json: true,
        io: captureIo().io,
        confirmPreview: async () => false,
      },
    ),
    (error: unknown) =>
      error instanceof CouncilError && error.code === 'RUN_AUTHORIZATION_REQUIRED',
  );

  // Start through the controlled transport with the real stored grant.
  const { host: host2 } = createLocalHost({
    dataDir,
    transports: [
      {
        routeId: sample.spec.model_policy.route_id,
        transport: new DeterministicFixtureTransport(),
      },
    ],
  });
  const composition2 = createStandaloneRunAuthorization({ dataDir });
  const engine2 = new CouncilEngine(withRunAuthorization(host2, composition2));
  const done = await engine2.startSession(sample.spec.session_id, grant.grant_id);
  assert.equal(done.state.state, 'COMPLETED');
  const verdict = await engine2.getVerdict(sample.spec.session_id);
  assert.ok(verdict, 'the started run produces a verdict under the grant');
  composition2.close();

  // Status, then revoke: the grant stops resolving at once.
  const statusIo = captureIo();
  await handleAuthorizationCommand(
    'status',
    [grant.grant_id],
    new Map<string, string | true>([['session', sample.spec.session_id]]),
    { dataDir, json: true, io: statusIo.io },
  );
  const status = statusIo.json() as { status: string; resolvable: boolean };
  assert.equal(status.status, 'active');
  assert.equal(status.resolvable, true);

  const revokeIo = captureIo();
  await handleAuthorizationCommand('revoke', [grant.grant_id], new Map(), {
    dataDir,
    json: true,
    io: revokeIo.io,
  });
  const status2Io = captureIo();
  await handleAuthorizationCommand(
    'status',
    [grant.grant_id],
    new Map<string, string | true>([['session', sample.spec.session_id]]),
    { dataDir, json: true, io: status2Io.io },
  );
  const status2 = status2Io.json() as { status: string; resolvable: boolean };
  assert.equal(status2.status, 'revoked');
  assert.equal(status2.resolvable, false);
});
