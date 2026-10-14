/**
 * CWE-003 contract tests, including test contract T148 (Section 35.14):
 * "Canonical hashes agree across all consumers and reject
 * ambiguous/nonfinite/duplicate-key payloads; display rounding changes no
 * decision."
 *
 * Runner (Node built-in test runner via tsx, the repo's dominant unit
 * convention):
 *   node --import tsx --test 77-council-of-wise-elders/runtime/src/contracts/contracts.test.ts
 *
 * Evidence status note: these tests prove the deterministic core only.
 * They are Tier A tests per Section 32.1: no network, credentials, owner
 * notifications, or production DB access.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ContractError,
  canonicalBytes,
  canonicalHash,
  canonicalStringify,
  parseCanonicalJson,
  sha256Hex,
  computeOptionScore,
  labelForScore,
  isNearTie,
  GO_COVERAGE_THRESHOLD,
  assertTransition,
  canTransition,
  evaluateCapture,
  isCaptureExpired,
  DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
  DEFAULT_COUNCIL_SETTINGS,
  validateSessionSpec,
  validateDecisionBrief,
  validateCardAuthor,
  validateCard,
  validateCardAgainstBrief,
  validateSessionStateRecord,
  validateDiagnosticRetentionPolicy,
  validateCouncilSettings,
  validateEndpointContract,
  validateRunGrant,
  validateRunPreview,
  checkSchemaVersionCompatibility,
  SCHEMA_VERSIONS,
  money,
  isMoney,
  GOLDEN_EXPECTED,
  GOLDEN_SCORES,
  GOLDEN_TOTAL_WEIGHT,
  HASH_FIXTURE_A,
  HASH_FIXTURE_B,
  HASH_FIXTURE_CANONICAL_TEXT,
  generateJsonSchemaArtifact,
  JSON_SCHEMA_ARTIFACT_PATH,
} from './index';
import {
  invalidFixtures,
  validAdvisorCardAuthor,
  validBrief,
  validHostStamp,
  validSessionSpec,
  FIXTURE_HASH_A,
  FIXTURE_HASH_B,
} from './fixtures/examples';

// ---------------------------------------------------------------------------
// T148: canonical hashes agree across consumers
// ---------------------------------------------------------------------------

test('T148: pure SHA-256 matches the published FIPS vectors', () => {
  const enc = new TextEncoder();
  assert.equal(
    sha256Hex(enc.encode('')),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  );
  assert.equal(
    sha256Hex(enc.encode('abc')),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  );
});

test('T148: canonical hash agrees with the host crypto implementation', () => {
  const bytes = canonicalBytes(HASH_FIXTURE_A);
  const hostDigest = createHash('sha256').update(bytes).digest('hex');
  assert.equal(sha256Hex(bytes), hostDigest);
  assert.equal(canonicalHash(HASH_FIXTURE_A), hostDigest);
});

test('T148: key order does not change canonical text or hash', () => {
  assert.equal(canonicalStringify(HASH_FIXTURE_A), HASH_FIXTURE_CANONICAL_TEXT);
  assert.equal(canonicalStringify(HASH_FIXTURE_B), HASH_FIXTURE_CANONICAL_TEXT);
  assert.equal(canonicalHash(HASH_FIXTURE_A), canonicalHash(HASH_FIXTURE_B));
});

test('T148: array order is preserved and semantically significant', () => {
  const forward = canonicalStringify({ ids: ['a', 'b'] });
  const reversed = canonicalStringify({ ids: ['b', 'a'] });
  assert.notEqual(forward, reversed);
});

test('T148: duplicate keys are rejected at parse time', () => {
  assert.throws(
    () => parseCanonicalJson('{"a":1,"a":2}'),
    (err: unknown) => err instanceof ContractError && err.code === 'DUPLICATE_KEY',
  );
  assert.throws(
    () => parseCanonicalJson('{"outer":{"x":1,"x":2}}'),
    (err: unknown) => err instanceof ContractError && err.code === 'DUPLICATE_KEY',
  );
});

test('T148: nonfinite numbers are rejected in values and in parsed text', () => {
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    assert.throws(
      () => canonicalStringify({ score: bad }),
      (err: unknown) => err instanceof ContractError && err.code === 'NON_FINITE_NUMBER',
    );
  }
  for (const text of ['{"a":NaN}', '{"a":Infinity}', '{"a":1e999}']) {
    assert.throws(() => parseCanonicalJson(text), ContractError);
  }
});

test('T148: canonical round trip is stable', () => {
  const parsed = parseCanonicalJson(HASH_FIXTURE_CANONICAL_TEXT);
  assert.equal(canonicalStringify(parsed), HASH_FIXTURE_CANONICAL_TEXT);
  assert.throws(() => parseCanonicalJson('{"a":1} trailing'), ContractError);
});

test('T148: display rounding changes no decision', () => {
  // 7.46 displays as 7.5, which would read as GO if display values decided;
  // the label is computed from full precision and stays GO_WITH_CONDITIONS.
  const result = computeOptionScore(
    [{ seat_id: 'simon-sinek', weight: 1, score: 7.46 }],
    1,
  );
  assert.equal(result.display_score, 7.5);
  assert.equal(labelForScore(result.score as number), 'GO_WITH_CONDITIONS');
  // Golden B: 7.63636... displays 7.6 and the unrounded value labels GO.
  const b = computeOptionScore(GOLDEN_SCORES.B, GOLDEN_TOTAL_WEIGHT);
  assert.equal(b.display_score, 7.6);
  assert.equal(labelForScore(b.score as number), 'GO');
});

// ---------------------------------------------------------------------------
// Golden arithmetic (Section 32.2)
// ---------------------------------------------------------------------------

test('golden vectors: A, B, C weighted sums, scores, coverage, spread', () => {
  for (const key of ['A', 'B', 'C'] as const) {
    const result = computeOptionScore(GOLDEN_SCORES[key], GOLDEN_TOTAL_WEIGHT);
    const expected = GOLDEN_EXPECTED[key];
    assert.equal(result.weighted_sum, expected.weighted_sum, key);
    assert.equal(result.denominator, expected.denominator, key);
    assert.equal(result.score, expected.score, key);
    assert.equal(result.display_score, expected.display_score, key);
    assert.equal(result.coverage, expected.coverage, key);
    assert.equal(result.spread, expected.spread, key);
  }
});

test('golden vectors: Tiffany abstains on B (150 over 19, coverage 19/22)', () => {
  const result = computeOptionScore(
    GOLDEN_SCORES.B_TIFFANY_ABSTAINS,
    GOLDEN_TOTAL_WEIGHT,
  );
  const expected = GOLDEN_EXPECTED.B_TIFFANY_ABSTAINS;
  assert.equal(result.weighted_sum, 150);
  assert.equal(result.denominator, 19);
  assert.equal(result.score, expected.score);
  assert.ok(Math.abs(result.coverage - 19 / 22) < 1e-12);
  assert.ok(result.coverage > GO_COVERAGE_THRESHOLD);
  assert.equal(result.spread, 2);
});

test('scoring: all abstain gives a null score, never zero', () => {
  const result = computeOptionScore(
    [{ seat_id: 'les-brown', weight: 2, score: null }],
    2,
  );
  assert.equal(result.score, null);
  assert.equal(result.display_score, null);
  assert.equal(result.denominator, 0);
});

test('scoring: out-of-range and NaN scores throw SCORE_OUT_OF_RANGE', () => {
  for (const bad of [11, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.throws(
      () => computeOptionScore([{ seat_id: 's', weight: 1, score: bad }], 1),
      (err: unknown) => err instanceof ContractError && err.code === 'SCORE_OUT_OF_RANGE',
    );
  }
});

test('scoring: near tie band is 0.25 and label bands match Section 12.4', () => {
  assert.equal(isNearTie(7.6, 7.45), true);
  assert.equal(isNearTie(7.6, 7.3), false);
  assert.equal(labelForScore(7.5), 'GO');
  assert.equal(labelForScore(6.0), 'GO_WITH_CONDITIONS');
  assert.equal(labelForScore(4.5), 'RESHAPE');
  assert.equal(labelForScore(4.49), 'DONT_DO_IT');
});

// ---------------------------------------------------------------------------
// CWE-003 acceptance proof: invalid payloads fail validation
// ---------------------------------------------------------------------------

test('valid fixtures pass validation', () => {
  assert.equal(validateSessionSpec(validSessionSpec).ok, true);
  assert.equal(validateDecisionBrief(validBrief).ok, true);
  assert.equal(validateCardAuthor(validAdvisorCardAuthor).ok, true);
  const card = validateCard({ ...validAdvisorCardAuthor, host: validHostStamp });
  assert.equal(card.ok, true);
  assert.equal(validateDiagnosticRetentionPolicy(DEFAULT_DIAGNOSTIC_RETENTION_POLICY).ok, true);
  assert.equal(validateCouncilSettings(DEFAULT_COUNCIL_SETTINGS).ok, true);
});

test('unknown states fail validation', () => {
  const result = validateSessionStateRecord(invalidFixtures.unknownState);
  assert.equal(result.ok, false);
});

test('duplicate options fail validation', () => {
  const result = validateSessionSpec(invalidFixtures.duplicateOptions);
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.ok(result.issues.some((i) => i.message.includes('duplicate option')));
  }
});

test('out-of-range scores fail validation', () => {
  const result = validateCardAuthor(invalidFixtures.scoreOutOfRange);
  assert.equal(result.ok, false);
});

test('unknown enum values fail validation', () => {
  assert.equal(validateSessionSpec(invalidFixtures.unknownMode).ok, false);
});

test('an author cannot assign its own tenant or other host-only fields', () => {
  const result = validateCardAuthor(invalidFixtures.authorAssignsTenant);
  assert.equal(result.ok, false);
});

test('invalid references fail semantic card validation', () => {
  const briefResult = validateDecisionBrief(validBrief);
  assert.equal(briefResult.ok, true);
  if (!briefResult.ok) return;
  const brief = briefResult.value;

  const goodCard = validateCardAuthor(validAdvisorCardAuthor);
  assert.equal(goodCard.ok, true);
  if (goodCard.ok) {
    assert.equal(validateCardAgainstBrief(goodCard.value, brief).ok, true);
  }

  for (const bad of [
    invalidFixtures.invalidPreferredOption,
    invalidFixtures.invalidScoredOption,
    invalidFixtures.invalidEvidenceReference,
  ]) {
    const parsed = validateCardAuthor(bad);
    assert.equal(parsed.ok, true);
    if (parsed.ok) {
      const checked = validateCardAgainstBrief(parsed.value, brief);
      assert.equal(checked.ok, false);
      assert.ok(checked.issues.every((i) => i.code === 'INVALID_REFERENCE'));
    }
  }
});

test('consult cards cannot smuggle scored-mode fields', () => {
  const consult = {
    schema_version: 'wise-elders.card/v1',
    card_kind: 'consult',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    seat_id: 'oprah-winfrey',
    input_manifest_sha256: FIXTURE_HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    answer: 'A bounded answer.',
    framework_applications: [],
    evidence_ids: [],
    assumptions: [],
    limits: [],
    next_step: 'Review the answer.',
    option_scores: [],
  };
  assert.equal(validateCardAuthor(consult).ok, false);
  const { option_scores: _dropped, ...clean } = consult;
  assert.equal(validateCardAuthor(clean).ok, true);
});

test('ratification cards require the exact resolution hash and stance', () => {
  const ratification = {
    schema_version: 'wise-elders.card/v1',
    card_kind: 'ratification',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    round: 3,
    seat_id: 'simon-sinek',
    input_manifest_sha256: FIXTURE_HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    draft_resolution_sha256: FIXTURE_HASH_A,
    resolution_stance: 'conditional_support',
    stance: 'conditional',
    preferred_option_id: 'B',
    option_scores: [],
    amendments: [],
    accepted_condition_ids: [],
    unresolved_objections: [],
    evidence_strength: 'medium',
  };
  assert.equal(validateCardAuthor(ratification).ok, true);
  const { draft_resolution_sha256: _h, ...missingHash } = ratification;
  assert.equal(validateCardAuthor(missingHash).ok, false);
});

test('run preview and grant schemas validate complete records', () => {
  const preview = {
    schema_version: 'wise-elders.run-preview/v1',
    preview_id: 'preview-fixture-1',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    brief_sha256: FIXTURE_HASH_A,
    mode: 'full',
    seat_ids: ['simon-sinek'],
    purpose: 'council_run',
    route_policy_sha256: FIXTURE_HASH_B,
    pack_version: 'pack-fixture-1.0.0',
    ceilings: {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    },
    money_bounded: false,
    created_at: '2026-10-14T02:00:00Z',
    expires_at: '2026-10-14T02:15:00Z',
    preview_sha256: FIXTURE_HASH_A,
  };
  assert.equal(validateRunPreview(preview).ok, true);
  const grant = {
    schema_version: 'wise-elders.run-grant/v1',
    grant_id: 'grant-fixture-1',
    authority_mode: 'managed_principal',
    issuer_principal: 'principal-fixture',
    scope: {
      tenant_id: 'tenant-fixture',
      company_id: 'company-fixture',
      installation_id: 'install-fixture',
      owner_subject: null,
    },
    purpose: 'council_run',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    brief_sha256: FIXTURE_HASH_A,
    mode: 'full',
    seat_ids: ['simon-sinek'],
    route_policy_sha256: FIXTURE_HASH_B,
    account_ref: null,
    pack_version: 'pack-fixture-1.0.0',
    protocol_version: 'wise-elders.core/1.0.0',
    allowed_operation_kinds: ['advisor_card'],
    ceilings: preview.ceilings,
    created_at: '2026-10-14T02:00:00Z',
    expires_at: '2026-10-15T02:00:00Z',
    revocation_epoch: 0,
    status: 'active',
    standing_parent_grant_id: null,
    preview_sha256: FIXTURE_HASH_A,
    consumed: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
    reserved: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
  };
  assert.equal(validateRunGrant(grant).ok, true);
});

test('endpoint contract requires scope, owner, and both gates', () => {
  const endpoint = {
    schema_version: 'wise-elders.endpoint-contract/v1',
    contract_id: 'endpoint-sessions-create',
    method: 'POST',
    path: '/api/council/sessions',
    request_schema: 'SessionSpec',
    response_schema: 'SessionStateRecord',
    authorization_purpose: 'council_run',
    idempotency: 'required_key',
    version_rule: 'schema_version must equal wise-elders.session/v1',
    service_owner: 'CWE-029 foundation; CWE-050 final assembly',
    contract_test_gate: 'contract tests pass',
    live_integration_gate: 'live integration verified separately',
  };
  assert.equal(validateEndpointContract(endpoint).ok, true);
  assert.equal(
    validateEndpointContract({ ...endpoint, path: 'api/council/sessions' }).ok,
    false,
  );
});

test('schema version compatibility is exact, never silent', () => {
  assert.equal(checkSchemaVersionCompatibility('session', SCHEMA_VERSIONS.session), true);
  assert.equal(checkSchemaVersionCompatibility('session', 'wise-elders.session/v2'), false);
  assert.equal(checkSchemaVersionCompatibility('session', undefined), false);
});

// ---------------------------------------------------------------------------
// State machine (Sections 15.1 and 11.7)
// ---------------------------------------------------------------------------

test('state machine: full mode walks the complete round path', () => {
  const path = [
    'DRAFT', 'READY', 'QUEUED', 'PREPARING', 'ROUND_1', 'CRUX_REVIEW',
    'ROUND_2', 'DRAFT_RESOLUTION', 'ROUND_3', 'VERIFYING', 'COMPLETED',
  ] as const;
  for (let i = 0; i < path.length - 1; i++) {
    assert.equal(canTransition('full', path[i], path[i + 1]), true, `${path[i]} -> ${path[i + 1]}`);
  }
});

test('state machine: consult branch uses CONSULTING and never rounds', () => {
  assert.equal(canTransition('consult', 'PREPARING', 'CONSULTING'), true);
  assert.equal(canTransition('consult', 'CONSULTING', 'VERIFYING'), true);
  assert.equal(canTransition('consult', 'PREPARING', 'ROUND_1'), false);
  assert.equal(canTransition('full', 'PREPARING', 'CONSULTING'), false);
});

test('state machine: COMPLETED is immutable and skips are illegal', () => {
  assert.equal(canTransition('full', 'COMPLETED', 'ROUND_1'), false);
  assert.equal(canTransition('full', 'DRAFT', 'ROUND_1'), false);
  assert.equal(canTransition('full', 'ROUND_1', 'ROUND_2'), false);
});

test('state machine: pause, cancel, block, resume discipline', () => {
  assert.equal(canTransition('full', 'ROUND_1', 'PAUSE_REQUESTED'), true);
  assert.equal(canTransition('full', 'PAUSE_REQUESTED', 'PAUSED'), true);
  assert.equal(canTransition('full', 'PAUSED', 'RESUMING'), true);
  assert.equal(canTransition('full', 'RESUMING', 'ROUND_1', 'ROUND_1'), true);
  assert.equal(canTransition('full', 'RESUMING', 'ROUND_2', 'ROUND_1'), false);
  assert.equal(canTransition('full', 'ROUND_2', 'BLOCKED'), true);
  assert.equal(canTransition('full', 'BLOCKED', 'RESUMING'), true);
  assert.equal(canTransition('full', 'COMPLETED', 'PAUSE_REQUESTED'), false);
});

test('state machine: version and cancel generation are enforced', () => {
  assert.deepEqual(
    assertTransition({
      mode: 'full', from: 'DRAFT', to: 'READY',
      expectedVersion: 3, currentVersion: 3, actor: 'owner',
    }),
    { stateVersion: 4 },
  );
  assert.throws(
    () => assertTransition({
      mode: 'full', from: 'DRAFT', to: 'READY',
      expectedVersion: 2, currentVersion: 3, actor: 'owner',
    }),
    (err: unknown) => err instanceof ContractError && err.code === 'VERSION_MISMATCH',
  );
  assert.throws(
    () => assertTransition({
      mode: 'full', from: 'ROUND_1', to: 'CANCEL_REQUESTED',
      expectedVersion: 1, currentVersion: 1, actor: 'owner',
      cancelGeneration: 5, currentCancelGeneration: 3,
    }),
    (err: unknown) => err instanceof ContractError && err.code === 'ILLEGAL_TRANSITION',
  );
  assert.deepEqual(
    assertTransition({
      mode: 'full', from: 'ROUND_1', to: 'CANCEL_REQUESTED',
      expectedVersion: 1, currentVersion: 1, actor: 'owner',
      cancelGeneration: 4, currentCancelGeneration: 3,
    }),
    { stateVersion: 2 },
  );
});

// ---------------------------------------------------------------------------
// Diagnostic retention policy (Section 16.6)
// ---------------------------------------------------------------------------

const enabledPolicy = {
  ...DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
  enabled: true,
  authorized_by_principal: 'principal-owner',
  authorization_kind: 'owner' as const,
  session_id: 'sess-fixture-1',
};

test('diagnostics: capture is disabled by default', () => {
  const decision = evaluateCapture({
    policy: DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
    sessionId: 'sess-fixture-1',
    dataClass: 'provider_response_body',
    byteLength: 100,
    sessionBytesAlreadyCaptured: 0,
    minutesSinceWindowStart: 0,
    protectionEstablished: true,
    sessionDeletedOrRevoked: false,
  });
  assert.equal(decision.allowed, false);
});

test('diagnostics: never-captured classes stay prohibited when enabled', () => {
  for (const dataClass of ['hidden_reasoning', 'access_token', 'cookie', 'authentication_header', 'private_key']) {
    const decision = evaluateCapture({
      policy: enabledPolicy,
      sessionId: 'sess-fixture-1',
      dataClass,
      byteLength: 10,
      sessionBytesAlreadyCaptured: 0,
      minutesSinceWindowStart: 0,
      protectionEstablished: true,
      sessionDeletedOrRevoked: false,
    });
    assert.equal(decision.allowed, false, dataClass);
  }
});

test('diagnostics: one named session, window, ceilings, labeled truncation', () => {
  const base = {
    policy: enabledPolicy,
    sessionId: 'sess-fixture-1',
    dataClass: 'provider_response_body',
    byteLength: 100,
    sessionBytesAlreadyCaptured: 0,
    minutesSinceWindowStart: 0,
    protectionEstablished: true,
    sessionDeletedOrRevoked: false,
  };
  assert.deepEqual(evaluateCapture(base), { allowed: true, truncated: false, effectiveBytes: 100 });
  assert.equal(evaluateCapture({ ...base, sessionId: 'sess-other' }).allowed, false);
  assert.equal(evaluateCapture({ ...base, minutesSinceWindowStart: 61 }).allowed, false);
  assert.equal(evaluateCapture({ ...base, protectionEstablished: false }).allowed, false);
  assert.equal(evaluateCapture({ ...base, sessionDeletedOrRevoked: true }).allowed, false);
  const big = evaluateCapture({ ...base, byteLength: 6 * 1024 * 1024 });
  assert.equal(big.allowed, true);
  if (big.allowed) {
    assert.equal(big.truncated, true);
    assert.equal(big.effectiveBytes, 5 * 1024 * 1024);
  }
});

test('diagnostics: policy bounds and TTL expiry', () => {
  assert.equal(
    validateDiagnosticRetentionPolicy({ ...enabledPolicy, capture_window_minutes: 241 }).ok,
    false,
  );
  assert.equal(
    validateDiagnosticRetentionPolicy({ ...enabledPolicy, payload_ttl_hours: 73 }).ok,
    false,
  );
  assert.equal(
    validateDiagnosticRetentionPolicy({ ...enabledPolicy, authorized_by_principal: null }).ok,
    false,
  );
  assert.equal(isCaptureExpired(0, 24 * 3600 * 1000, 24), true);
  assert.equal(isCaptureExpired(0, 23 * 3600 * 1000, 24), false);
});

// ---------------------------------------------------------------------------
// Primitives and generated artifact drift
// ---------------------------------------------------------------------------

test('money is integer minor units with a currency code', () => {
  assert.deepEqual(money(12500, 'USD'), { amount_minor: 12500, currency: 'USD' });
  assert.equal(isMoney({ amount_minor: 12.5, currency: 'USD' }), false);
  assert.equal(isMoney({ amount_minor: 100, currency: 'usd' }), false);
  assert.throws(() => money(1.5, 'USD'), ContractError);
});

test('generated JSON Schema artifact matches the canonical definitions', () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const committed = readFileSync(join(here, JSON_SCHEMA_ARTIFACT_PATH), 'utf8');
  assert.equal(generateJsonSchemaArtifact(), committed);
});
