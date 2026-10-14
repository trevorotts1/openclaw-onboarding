/**
 * CWE-007 trusted authorization port tests (directive Sections 17.1,
 * 17.5, 28.2; T073, T074, T075, T077). Negative fixtures are the heart of
 * this unit: every denial path is exercised against the real decision
 * functions.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  AuthorizationError,
  assertClaimedScopeMatches,
  assertMachineBinding,
  assertNoQueryCredentialParameter,
  assertSessionMutate,
  assertSessionRead,
  authorizationKindForPermission,
  checkMachineBinding,
  checkSessionMutate,
  checkSessionRead,
  findScopeConflict,
  type SessionAccessTarget,
  type TrustedPrincipal,
} from '../src/authorization/index.js';

const owner: TrustedPrincipal = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  subject: 'owner:alice',
  channel: 'browser',
  support_access: false,
};

const colleague: TrustedPrincipal = {
  ...owner,
  subject: 'user:bob',
};

const support: TrustedPrincipal = {
  ...owner,
  subject: 'support:carol',
  support_access: true,
};

const machine: TrustedPrincipal = {
  ...owner,
  subject: 'operator:api',
  channel: 'machine',
};

function target(
  overrides: Partial<SessionAccessTarget['scope']> & {
    visibility?: SessionAccessTarget['visibility'];
  } = {},
): SessionAccessTarget {
  const { visibility = 'private', ...scopeOverrides } = overrides;
  return {
    visibility,
    scope: {
      tenant_id: 'tenant-a',
      company_id: 'company-a',
      installation_id: 'install-a',
      owner_subject: 'owner:alice',
      ...scopeOverrides,
    },
  };
}

test('claimed scope: equal values tolerated, conflicts rejected by field', () => {
  assert.equal(
    findScopeConflict(owner, { tenant_id: 'tenant-a', companyId: 'company-a' }),
    null,
  );
  assert.equal(findScopeConflict(owner, {}), null);
  assert.equal(findScopeConflict(owner, { tenant_id: 'tenant-b' }), 'tenant_id');
  assert.equal(findScopeConflict(owner, { company_id: 'company-b' }), 'company_id');
  assert.equal(
    findScopeConflict(owner, { installationId: 'install-b' }),
    'installation_id',
  );
  // Claiming another subject as owner is a conflict even in-scope.
  assert.equal(
    findScopeConflict(owner, { owner_subject: 'owner:mallory' }),
    'owner_subject',
  );
  assert.equal(findScopeConflict(owner, { owner_subject: 'owner:alice' }), null);
  assert.throws(
    () => assertClaimedScopeMatches(owner, { company_id: 'company-b' }),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_SCOPE_MISMATCH',
  );
});

test('private session: owner reads, same-company non-owner denied (T073/T074)', () => {
  assert.deepEqual(checkSessionRead(owner, target()), {
    allowed: true,
    via: 'owner',
  });
  const denied = checkSessionRead(colleague, target());
  assert.equal(denied.allowed, false);
  if (!denied.allowed) {
    assert.equal(denied.code, 'COUNCIL_PRIVATE_OWNER_REQUIRED');
  }
  assert.throws(
    () => assertSessionRead(colleague, target()),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_PRIVATE_OWNER_REQUIRED',
  );
});

test('cross-tenant, cross-company, cross-installation reads all fail (T073)', () => {
  for (const foreign of [
    target({ tenant_id: 'tenant-b' }),
    target({ company_id: 'company-b' }),
    target({ installation_id: 'install-b' }),
  ]) {
    const decision = checkSessionRead(owner, foreign);
    assert.equal(decision.allowed, false);
    if (!decision.allowed) assert.equal(decision.code, 'COUNCIL_CROSS_SCOPE');
  }
  // Even the recorded owner cannot read across the scope barrier.
  assert.equal(
    checkSessionRead(owner, target({ company_id: 'company-b' })).allowed,
    false,
  );
});

test('company-visible session: any in-scope principal reads', () => {
  assert.deepEqual(checkSessionRead(colleague, target({ visibility: 'company' })), {
    allowed: true,
    via: 'company',
  });
  assert.equal(
    checkSessionRead(colleague, target({ visibility: 'company', tenant_id: 't-b' }))
      .allowed,
    false,
  );
});

test('support access: explicit audited read path, never a mutation (T075)', () => {
  assert.deepEqual(checkSessionRead(support, target()), {
    allowed: true,
    via: 'support',
  });
  const mutate = checkSessionMutate(support, target());
  assert.equal(mutate.allowed, false);
  assert.throws(
    () => assertSessionMutate(support, target()),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_PRIVATE_OWNER_REQUIRED',
  );
  // A principal without host-granted support gets no support path.
  assert.equal(checkSessionRead(colleague, target()).allowed, false);
});

test('mutations: owner mutates private, colleague mutates company-visible', () => {
  assert.equal(assertSessionMutate(owner, target()), 'owner');
  assert.equal(
    assertSessionMutate(colleague, target({ visibility: 'company' })),
    'company',
  );
});

test('machine binding: channel, scope, operation set, session pin (T077)', () => {
  const binding = {
    installation_id: 'install-a',
    company_id: 'company-a',
    operations: ['read', 'export'] as const,
    session_id: 'session-1',
  };
  assert.equal(
    checkMachineBinding(machine, binding, 'read', 'session-1').allowed,
    true,
  );
  // Wrong session for a pinned binding.
  assert.equal(
    checkMachineBinding(machine, binding, 'read', 'session-2').allowed,
    false,
  );
  // Operation outside the binding.
  assert.equal(
    checkMachineBinding(machine, binding, 'execute', 'session-1').allowed,
    false,
  );
  // Browser principal can never satisfy a machine binding.
  assert.equal(
    checkMachineBinding(owner, binding, 'read', 'session-1').allowed,
    false,
  );
  // Machine principal from another installation or company.
  assert.equal(
    checkMachineBinding(
      { ...machine, installation_id: 'install-b' },
      binding,
      'read',
      'session-1',
    ).allowed,
    false,
  );
  assert.equal(
    checkMachineBinding(
      { ...machine, company_id: 'company-b' },
      binding,
      'read',
      'session-1',
    ).allowed,
    false,
  );
  assert.throws(
    () => assertMachineBinding(machine, binding, 'execute', 'session-1'),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_MACHINE_BINDING',
  );
});

test('the four authorizations stay separate (Section 1.2)', () => {
  assert.equal(authorizationKindForPermission('run'), 'council_run');
  assert.equal(authorizationKindForPermission('approve_plan'), 'action_plan_approval');
  assert.equal(authorizationKindForPermission('create_tasks'), 'action_plan_approval');
  assert.equal(authorizationKindForPermission('execute'), 'execution');
  // A run authorization is never an execution credential.
  assert.notEqual(
    authorizationKindForPermission('run'),
    authorizationKindForPermission('execute'),
  );
  assert.equal(authorizationKindForPermission('read'), null);
  assert.equal(authorizationKindForPermission('export'), null);
});

test('query credential guard: credential parameter names rejected', () => {
  assert.throws(
    () => assertNoQueryCredentialParameter(['session_id', 'api_key']),
    (error: unknown) =>
      error instanceof AuthorizationError &&
      error.code === 'COUNCIL_QUERY_CREDENTIAL' &&
      error.status === 400 &&
      !error.message.includes('api_key'.toUpperCase()),
  );
  assert.throws(
    () => assertNoQueryCredentialParameter(['Access_Token']),
    /COUNCIL|Credentials are not accepted/,
  );
  // Ordinary parameters pass.
  assertNoQueryCredentialParameter(['session_id', 'visibility', 'cursor']);
});
