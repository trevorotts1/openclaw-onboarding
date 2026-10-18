/**
 * WER-023 remote access tests (application-side half).
 *
 * Runner (the runtime's own runner):
 *   node --import tsx --test src/remote/remote.test.ts
 *
 * Tier A only: a LOCAL RSA keypair and a fixture JWKS are injected, the
 * clock is fixed, and `globalThis.fetch` is replaced by a counting spy
 * that throws. The suite therefore makes ZERO network calls and touches
 * no Cloudflare resource.
 *
 * Proven here:
 * - a correctly signed JWT for the pinned audience/issuer/exp is accepted;
 * - a bad signature, a wrong audience, an expired token and a wrong
 *   issuer are each refused with distinct typed reasons;
 * - a forwarded identity header with NO valid JWT is refused (the plan's
 *   "arbitrary forwarded headers do not establish identity" rule);
 * - a valid JWT whose Host/Origin is outside the exact allowed set is
 *   refused;
 * - a disabled configuration leaves local operation working and refuses
 *   remote resolution with a typed reason and no localhost URL;
 * - the resolver returns exactly ONE owning endpoint URL or a typed
 *   failure, never two candidates;
 * - reauthentication resumes the SAME durable session id and issues ZERO
 *   billable Start calls;
 * - connection loss is not reinterpreted as cancellation;
 * - a cross-user refusal is indistinguishable from an unknown session.
 *
 * DEFERRED, never claimed: a real phone/tablet reaching the origin, a
 * real authenticated remote session, live SSE delivery from a device and
 * a real VPS path. Those belong to WER-026/WER-027 acceptance.
 */

import assert from 'node:assert/strict';
import {
  generateKeyPairSync,
  sign as cryptoSign,
  type KeyObject,
} from 'node:crypto';
import test, { after, before } from 'node:test';

import { resolveSessionTarget } from '../service/sessions.js';
import { ACCESS_EMAIL_HEADER, ACCESS_JWT_HEADER, verifyAccessJwt } from './access-jwt.js';
import { authenticateRemoteRequest } from './auth.js';
import {
  buildRemoteConfiguration,
  RemoteSessionBridge,
  resolveRemoteSession,
} from './sessions.js';
import type {
  JsonWebKeySet,
  RemoteConfiguration,
  RemoteEnabledConfig,
  RemoteHeaders,
  RemoteSessionRecord,
  SessionLookup,
} from './types.js';
import { REMOTE_CONFIG_SCHEMA } from './types.js';

// ----------------------------------------------------------- live topology

const TEAM_DOMAIN = 'sweet-wave-ca28.cloudflareaccess.com';
const AUDIENCE = '6bf040e24b8aaf595d8be843f9a22f477cd71a25a5e42872f2ec25f73f25d45c';
const COUNCIL_ORIGIN = 'https://council.zerohumanworkforce.com';
const COUNCIL_HOST = 'council.zerohumanworkforce.com';
const ENDPOINT_ID = 'council-origin';

// Fixed epoch seconds, 2027-01-15T08:00:00Z.
const NOW = 1_800_000_000;
const KID = 'wer023-test-key';

// ------------------------------------------------------- local key material

const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2_048 });
const importedJwk = publicKey.export({ format: 'jwk' }) as Record<string, unknown>;
const JWKS: JsonWebKeySet = {
  keys: [{ ...importedJwk, kid: KID, alg: 'RS256', use: 'sig' }],
};
const OTHER_KEYPAIR = generateKeyPairSync('rsa', { modulusLength: 2_048 });

let jwksReads = 0;
const injectedJwks = async (): Promise<JsonWebKeySet> => {
  jwksReads += 1;
  return JWKS;
};

// ------------------------------------------------------------ network spy

const realFetch = globalThis.fetch;
let networkCalls = 0;

before(() => {
  globalThis.fetch = (async () => {
    networkCalls += 1;
    throw new Error('Network access is disabled in the WER-023 test suite.');
  }) as typeof fetch;
});

after(() => {
  globalThis.fetch = realFetch;
  assert.equal(networkCalls, 0, 'the suite must make zero network calls');
});

// ------------------------------------------------------------- JWT helpers

interface SignOptions {
  kid?: string | null;
  key?: KeyObject;
  alg?: string;
}

function signJwt(claims: Record<string, unknown>, options: SignOptions = {}): string {
  const header: Record<string, unknown> = { alg: options.alg ?? 'RS256', typ: 'JWT' };
  if (options.kid !== null) header.kid = options.kid ?? KID;
  const encode = (value: unknown): string => Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
  const signingInput = `${encode(header)}.${encode(claims)}`;
  const signature = cryptoSign('RSA-SHA256', Buffer.from(signingInput, 'utf8'), options.key ?? privateKey);
  return `${signingInput}.${signature.toString('base64url')}`;
}

function claims(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    iss: `https://${TEAM_DOMAIN}`,
    aud: AUDIENCE,
    sub: 'user-1',
    email: 'user1@example.test',
    iat: NOW - 30,
    nbf: NOW - 30,
    exp: NOW + 3_600,
    ...overrides,
  };
}

function validToken(overrides: Record<string, unknown> = {}): string {
  return signJwt(claims(overrides));
}

function headersFor(token: string | null, overrides: RemoteHeaders = {}): RemoteHeaders {
  const headers: Record<string, string> = {
    host: COUNCIL_HOST,
    origin: COUNCIL_ORIGIN,
  };
  if (token !== null) headers[ACCESS_JWT_HEADER] = token;
  return { ...headers, ...overrides };
}

// ------------------------------------------------------------- configuration

function enabledConfiguration(overrides: Partial<Parameters<typeof buildRemoteConfiguration>[0]> = {}): RemoteEnabledConfig {
  const config = buildRemoteConfiguration({
    enabled: true,
    team_domain: TEAM_DOMAIN,
    audience: AUDIENCE,
    allowed_origins: [COUNCIL_ORIGIN],
    endpoints: [{ endpoint_id: ENDPOINT_ID, origin: COUNCIL_ORIGIN, verified: true }],
    jwks: injectedJwks,
    clock_skew_seconds: 60,
    ...overrides,
  });
  if (config.enabled !== true) throw new Error('test configuration must be enabled');
  return config;
}

const CONFIG: RemoteEnabledConfig = enabledConfiguration();

function verify(token: string) {
  return verifyAccessJwt(token, {
    team_domain: TEAM_DOMAIN,
    audience: AUDIENCE,
    jwks: injectedJwks,
    now_seconds: () => NOW,
    clock_skew_seconds: 60,
  });
}

function authenticate(headers: RemoteHeaders) {
  return authenticateRemoteRequest(headers, CONFIG, { now_seconds: () => NOW });
}

// ------------------------------------------------------------- session data

const OWN_SESSION: RemoteSessionRecord = {
  session_id: 'sess-main',
  owner_subject: 'user-1',
  authority: 'standalone',
  endpoint_ids: [ENDPOINT_ID],
};

function lookupOf(records: RemoteSessionRecord[]): SessionLookup {
  const map = new Map(records.map((record) => [record.session_id, record]));
  return (sessionId) => map.get(sessionId) ?? null;
}

// ------------------------------------------------------------------- tests

test('a correctly signed JWT for the pinned audience with valid iss/exp is accepted', async () => {
  const verification = await verify(validToken());
  assert.equal(verification.ok, true);
  if (!verification.ok) return;
  assert.equal(verification.claims.sub, 'user-1');
  assert.equal(verification.claims.iss, `https://${TEAM_DOMAIN}`);

  const authentication = await authenticate(headersFor(validToken()));
  assert.equal(authentication.ok, true);
  if (!authentication.ok) return;
  assert.equal(authentication.identity.subject, 'user-1');
  assert.equal(authentication.identity.email, 'user1@example.test');
});

test('a bad signature is refused', async () => {
  // Same kid so key selection succeeds; the signature itself is wrong.
  const token = signJwt(claims(), { key: OTHER_KEYPAIR.privateKey });
  const verification = await verify(token);
  assert.equal(verification.ok, false);
  if (verification.ok) return;
  assert.equal(verification.code, 'REMOTE_TOKEN_SIGNATURE_INVALID');

  const authentication = await authenticate(headersFor(token));
  assert.equal(authentication.ok, false);
  if (authentication.ok) return;
  assert.equal(authentication.code, 'REMOTE_TOKEN_SIGNATURE_INVALID');
});

test('a wrong audience is refused', async () => {
  const verification = await verify(validToken({ aud: 'some-other-application-audience' }));
  assert.equal(verification.ok, false);
  if (verification.ok) return;
  assert.equal(verification.code, 'REMOTE_TOKEN_AUDIENCE_MISMATCH');
});

test('an expired token is refused', async () => {
  const token = validToken({ iat: NOW - 3_600, nbf: NOW - 3_600, exp: NOW - 120 });
  const verification = await verify(token);
  assert.equal(verification.ok, false);
  if (verification.ok) return;
  assert.equal(verification.code, 'REMOTE_TOKEN_EXPIRED');
});

test('a wrong issuer / wrong team domain is refused', async () => {
  const verification = await verify(validToken({ iss: 'https://attacker.cloudflareaccess.com' }));
  assert.equal(verification.ok, false);
  if (verification.ok) return;
  assert.equal(verification.code, 'REMOTE_TOKEN_ISSUER_MISMATCH');

  // The same token is refused under a different configured team domain.
  const mismatched = await verifyAccessJwt(validToken(), {
    team_domain: 'another-team.cloudflareaccess.com',
    audience: AUDIENCE,
    jwks: injectedJwks,
    now_seconds: () => NOW,
    clock_skew_seconds: 60,
  });
  assert.equal(mismatched.ok, false);
  if (mismatched.ok) return;
  assert.equal(mismatched.code, 'REMOTE_TOKEN_ISSUER_MISMATCH');
});

test('a forged forwarded identity header with NO valid JWT is refused', async () => {
  const headers = headersFor(null, {
    [ACCESS_EMAIL_HEADER]: 'victim@example.test',
  });
  const authentication = await authenticate(headers);
  assert.equal(authentication.ok, false);
  if (authentication.ok) return;
  assert.equal(authentication.code, 'REMOTE_UNAUTHENTICATED');
  assert.match(authentication.detail, /forwarded identity header/i);

  // The same forged header does not open a remote session either.
  const bridge = new RemoteSessionBridge({ config: CONFIG, lookupSession: lookupOf([OWN_SESSION]) });
  const resolution = await bridge.establish({
    session_id: OWN_SESSION.session_id,
    headers: { ...headersFor(null), [ACCESS_EMAIL_HEADER]: 'user1@example.test' },
  });
  assert.equal(resolution.kind, 'refused');
  if (resolution.kind !== 'refused') return;
  assert.equal(resolution.code, 'REMOTE_UNAUTHENTICATED');
  assert.equal(resolution.url, null);
});

test('a valid JWT whose Host or Origin is outside the exact allowed set is refused', async () => {
  const token = validToken();

  const badHost = await authenticate(headersFor(token, { host: `${COUNCIL_HOST}.evil.test` }));
  assert.equal(badHost.ok, false);
  if (badHost.ok) return;
  assert.equal(badHost.code, 'REMOTE_ORIGIN_NOT_ALLOWED');

  const badOrigin = await authenticate(headersFor(token, { origin: 'https://evil.test' }));
  assert.equal(badOrigin.ok, false);
  if (badOrigin.ok) return;
  assert.equal(badOrigin.code, 'REMOTE_ORIGIN_NOT_ALLOWED');

  const good = await authenticate(headersFor(token));
  assert.equal(good.ok, true);
});

test('customer-disabled configuration leaves local operation working and refuses remote resolution', async () => {
  const disabled: RemoteConfiguration = buildRemoteConfiguration({ enabled: false });
  assert.equal(disabled.schema_version, REMOTE_CONFIG_SCHEMA);
  assert.equal(disabled.enabled, false);

  const bridge = new RemoteSessionBridge({
    config: disabled,
    lookupSession: () => {
      throw new Error('a disabled remote configuration must not consult the session store');
    },
  });
  const remote = await bridge.establish({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken()),
  });
  assert.equal(remote.kind, 'refused');
  if (remote.kind !== 'refused') return;
  assert.equal(remote.code, 'REMOTE_DISABLED');
  assert.equal(remote.url, null);
  assert.equal(JSON.stringify(remote).includes('127.0.0.1'), false, 'no localhost fallthrough');

  // The local/managed product is fully working.
  const local = resolveSessionTarget(
    { session_id: 'local-1', authority: 'standalone' },
    { origin: 'http://127.0.0.1:8787' },
  );
  assert.equal(local.kind, 'local');
  if (local.kind !== 'local') return;
  assert.equal(local.url, 'http://127.0.0.1:8787/council/local-1');
  assert.equal(local.launched_locally, true);

  const managed = resolveSessionTarget(
    { session_id: 'managed-1', authority: 'managed', owning_session_url: 'https://cc.example.test/council/managed-1' },
    { origin: null },
  );
  assert.equal(managed.kind, 'external');
});

test('the resolver returns exactly ONE owning endpoint URL or a typed failure', async () => {
  const bridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([OWN_SESSION]),
  });
  const resolved = await bridge.establish({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken()),
  });
  assert.equal(resolved.kind, 'resolved');
  if (resolved.kind !== 'resolved') return;
  assert.equal(resolved.url, `${COUNCIL_ORIGIN}/council/${OWN_SESSION.session_id}`);
  assert.equal(resolved.endpoint_id, ENDPOINT_ID);
  assert.equal(Object.keys(resolved).includes('candidates'), false);
  assert.equal(Object.keys(resolved).includes('urls'), false);
  assert.equal(typeof resolved.url, 'string');

  const ambiguous: RemoteSessionRecord = {
    ...OWN_SESSION,
    session_id: 'sess-ambiguous',
    endpoint_ids: [ENDPOINT_ID, 'second-endpoint'],
  };
  const ambiguousBridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([ambiguous]),
  });
  const refused = await ambiguousBridge.establish({
    session_id: ambiguous.session_id,
    headers: headersFor(validToken()),
  });
  assert.equal(refused.kind, 'refused');
  if (refused.kind !== 'refused') return;
  assert.equal(refused.code, 'REMOTE_SESSION_ENDPOINT_AMBIGUOUS');
  assert.equal(refused.url, null);

  // A record pointing at a non-configured endpoint (for example localhost)
  // never falls back; it is refused.
  const localEndpoint: RemoteSessionRecord = {
    ...OWN_SESSION,
    session_id: 'sess-local',
    endpoint_ids: ['localhost'],
  };
  const localRefused = await resolveRemoteSession({
    session_id: localEndpoint.session_id,
    identity: {
      subject: 'user-1',
      email: null,
      issuer: `https://${TEAM_DOMAIN}`,
      audience: [AUDIENCE],
      issued_at: NOW - 30,
      expires_at: NOW + 3_600,
    },
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([localEndpoint]),
    resumed: false,
    billable_starts: 0,
  });
  assert.equal(localRefused.kind, 'refused');
  if (localRefused.kind !== 'refused') return;
  assert.equal(localRefused.code, 'REMOTE_SESSION_ENDPOINT_UNKNOWN');
  assert.equal(localRefused.url, null);
});

test('reauthentication resumes the SAME session id and issues ZERO billable Start calls', async () => {
  const startCalls: string[] = [];
  const bridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([OWN_SESSION]),
    startBillable: ({ session_id }) => {
      startCalls.push(session_id);
    },
  });

  const first = await bridge.establish({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken()),
  });
  assert.equal(first.kind, 'resolved');
  assert.equal(bridge.billableStarts, 1);
  assert.equal(bridge.sessionId, OWN_SESSION.session_id);

  // The token expires: remote resolution is refused, the durable session stays.
  const expired = await bridge.reauthenticate({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken({ exp: NOW - 120, nbf: NOW - 3_600, iat: NOW - 3_600 })),
  });
  assert.equal(expired.kind, 'refused');
  if (expired.kind !== 'refused') return;
  assert.equal(expired.code, 'REMOTE_TOKEN_EXPIRED');
  assert.equal(bridge.sessionId, OWN_SESSION.session_id);

  const startsBeforeReauth = bridge.billableStarts;
  const fresh = validToken({ iat: NOW, nbf: NOW, exp: NOW + 3_600 });
  const reauthenticated = await bridge.reauthenticate({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(fresh),
  });
  assert.equal(reauthenticated.kind, 'resolved');
  if (reauthenticated.kind !== 'resolved') return;
  assert.equal(reauthenticated.session_id, OWN_SESSION.session_id);
  assert.equal(reauthenticated.resumed, true);
  assert.equal(bridge.billableStarts - startsBeforeReauth, 0, 'reauth issues zero billable Starts');
  assert.equal(bridge.reauthenticationBillableStarts, 0);
  assert.equal(startCalls.length, 1, 'only first establishment may start');

  // A bridge that has never established still reauthenticates without a Start.
  const freshBridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([OWN_SESSION]),
    startBillable: ({ session_id }) => {
      startCalls.push(session_id);
    },
  });
  const resumedOnly = await freshBridge.reauthenticate({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(fresh),
  });
  assert.equal(resumedOnly.kind, 'resolved');
  assert.equal(freshBridge.billableStarts, 0);
  assert.equal(freshBridge.reauthenticationBillableStarts, 0);
});

test('connection loss is NOT treated as cancellation', async () => {
  const cancelCalls: string[] = [];
  const bridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([OWN_SESSION]),
    cancelSession: ({ session_id }) => {
      cancelCalls.push(session_id);
    },
  });

  const established = await bridge.establish({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken()),
  });
  assert.equal(established.kind, 'resolved');

  const loss = bridge.connectionLost({ session_id: OWN_SESSION.session_id });
  assert.equal(loss.state, 'reconnecting');
  assert.equal(loss.cancelled, false);
  assert.equal(loss.session_id, OWN_SESSION.session_id);
  assert.equal(bridge.cancellations, 0);
  assert.equal(cancelCalls.length, 0);
  assert.equal(bridge.sessionId, OWN_SESSION.session_id, 'live state survives the loss');

  const startsBeforeResume = bridge.billableStarts;
  const resumed = await bridge.resume({
    session_id: OWN_SESSION.session_id,
    headers: headersFor(validToken({ iat: NOW, nbf: NOW })),
  });
  assert.equal(resumed.kind, 'resolved');
  if (resumed.kind !== 'resolved') return;
  assert.equal(resumed.session_id, OWN_SESSION.session_id);
  assert.equal(resumed.resumed, true);
  assert.equal(bridge.billableStarts - startsBeforeResume, 0);
  assert.equal(bridge.cancellations, 0);
  assert.equal(cancelCalls.length, 0);
});

test('cross-user refusal does not leak the other user\'s session existence', async () => {
  const otherUserSession: RemoteSessionRecord = {
    ...OWN_SESSION,
    session_id: 'sess-belongs-to-user-2',
    owner_subject: 'user-2',
  };
  const bridge = new RemoteSessionBridge({
    config: CONFIG,
    now_seconds: () => NOW,
    lookupSession: lookupOf([OWN_SESSION, otherUserSession]),
  });

  const crossUser = await bridge.establish({
    session_id: otherUserSession.session_id,
    headers: headersFor(validToken()),
  });
  const unknown = await bridge.establish({
    session_id: 'sess-that-does-not-exist',
    headers: headersFor(validToken()),
  });
  assert.equal(crossUser.kind, 'refused');
  assert.equal(unknown.kind, 'refused');
  if (crossUser.kind !== 'refused' || unknown.kind !== 'refused') return;

  assert.equal(crossUser.code, 'REMOTE_SESSION_NOT_AVAILABLE');
  assert.deepEqual(
    [crossUser.code, crossUser.detail, crossUser.recovery],
    [unknown.code, unknown.detail, unknown.recovery],
    'existence must not be observable',
  );
  assert.equal(crossUser.url, null);
  assert.equal(crossUser.detail.includes('user-2'), false);
  assert.equal(crossUser.detail.includes(otherUserSession.session_id), false);

  // The cross-user reason is distinct from unauthenticated and expired.
  const unauthenticated = await authenticate(headersFor(null));
  const expired = await authenticate(
    headersFor(validToken({ exp: NOW - 120, nbf: NOW - 3_600, iat: NOW - 3_600 })),
  );
  assert.equal(unauthenticated.ok, false);
  assert.equal(expired.ok, false);
  if (unauthenticated.ok || expired.ok) return;
  assert.equal(unauthenticated.code, 'REMOTE_UNAUTHENTICATED');
  assert.equal(expired.code, 'REMOTE_TOKEN_EXPIRED');
  assert.notEqual(crossUser.code, unauthenticated.code);
  assert.notEqual(crossUser.code, expired.code);
});

test('the JWKS source is injectable and the suite makes zero network calls', () => {
  // Constructing an enabled configuration with the default live source
  // performs no I/O; a fetch only happens on an actual verification.
  const withDefaultJwks = buildRemoteConfiguration({
    enabled: true,
    team_domain: TEAM_DOMAIN,
    audience: AUDIENCE,
    allowed_origins: [COUNCIL_ORIGIN],
    endpoints: [{ endpoint_id: ENDPOINT_ID, origin: COUNCIL_ORIGIN, verified: true }],
  });
  assert.equal(withDefaultJwks.enabled, true);
  assert.equal(networkCalls, 0);
  assert.ok(jwksReads > 0, 'verifications read the injected JWKS');
});
