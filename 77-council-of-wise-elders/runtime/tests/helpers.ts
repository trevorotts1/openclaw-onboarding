/**
 * Shared test helpers for the CWE-004 foundation tests.
 *
 * The grant built here exists only inside tests: it exercises the
 * engine's grant-admission checks (CWE-049 owns the real issuing
 * service). The fixture transport spends nothing and returns
 * deterministic synthetic cards.
 */
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  CONTRACT_PACKAGE_VERSION,
  canonicalHash,
  type RunGrant,
  type ScopeFields,
  type SessionSpec,
} from '../src/contracts/index.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type { CouncilHost, ModelTransport } from '../src/cli/host-ports.js';
import { createLocalHost } from '../src/cli/local-host.js';

export function tempDataDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe004-${label}-`));
}

export function buildTestGrant(
  spec: SessionSpec,
  scope: ScopeFields,
): RunGrant {
  return {
    schema_version: 'wise-elders.run-grant/v1',
    grant_id: 'grant-test-1',
    authority_mode: 'local_interactive_owner',
    issuer_principal: 'local-owner',
    scope: { ...scope },
    purpose: 'council_run',
    session_id: spec.session_id,
    brief_revision: spec.brief_revision,
    brief_sha256: spec.brief_sha256,
    mode: spec.mode,
    seat_ids: [...spec.seat_ids],
    route_policy_sha256: canonicalHash({ policy: 'test-route-policy' }),
    account_ref: null,
    pack_version: spec.source_pack_version,
    protocol_version: CONTRACT_PACKAGE_VERSION,
    allowed_operation_kinds: ['provider_request'],
    ceilings: {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    },
    created_at: '2026-01-01T00:00:00Z',
    expires_at: '2099-01-01T00:00:00Z',
    revocation_epoch: 0,
    status: 'active',
    standing_parent_grant_id: null,
    preview_sha256: canonicalHash({ preview: 'test' }),
    consumed: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
    reserved: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
  };
}

/** A local host with the fixture transport and a test grant provider. */
export function grantHost(
  dataDir: string,
  spec: SessionSpec,
  scope: ScopeFields,
  transport: ModelTransport = new DeterministicFixtureTransport(),
): CouncilHost {
  const { host } = createLocalHost({
    dataDir,
    transports: [{ routeId: spec.model_policy.route_id, transport }],
  });
  const grant = buildTestGrant(spec, scope);
  host.authorize = {
    async resolveRunGrant(grantRef: string, sessionId: string) {
      return grantRef === 'test-grant' && sessionId === spec.session_id
        ? grant
        : null;
    },
  };
  return host;
}
