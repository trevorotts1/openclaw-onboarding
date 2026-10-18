/**
 * Cloudflare Access JWT verification (WER-023).
 *
 * The v2.4 plan states that arbitrary forwarded headers do not establish
 * identity. This module is the only place a remote subject is established,
 * and it accepts NOTHING except a real RS256 signature over the token,
 * checked against the Access JWKS, with the issuer, pinned audience and
 * validity window all enforced.
 *
 * The JWKS source is injected. Tests supply a fixture JWKS built from a
 * local keypair, so this adapter makes zero network calls at test time.
 *
 * `ponytail:` the JWKS is read per verification and not cached; a
 * production source may add a TTL cache behind the same `JwksSource`
 * signature when key rotation has been observed live.
 */

import { createPublicKey, verify as cryptoVerify } from 'node:crypto';

import type {
  AccessSigningKey,
  JwksSource,
  JsonWebKeySet,
  RemoteRefusal,
} from './types.js';

/** Header Cloudflare Access sets on an authenticated request. */
export const ACCESS_JWT_HEADER = 'cf-access-jwt-assertion';
/** Identity hint Cloudflare also sets. NEVER trusted without a valid JWT. */
export const ACCESS_EMAIL_HEADER = 'cf-access-authenticated-user-email';

/** Guard against oversized segments before any parsing work. */
const MAX_SEGMENT_BYTES = 16_384;
const BASE64URL = /^[A-Za-z0-9_-]+$/;

export interface AccessJwtExpectations {
  /** Team domain with or without scheme, e.g. sweet-wave-ca28.cloudflareaccess.com */
  team_domain: string;
  audience: string;
  jwks: JwksSource;
  /** Injected clock in epoch seconds. */
  now_seconds?: () => number;
  clock_skew_seconds?: number;
}

export interface AccessClaims {
  iss: string;
  aud: readonly string[];
  sub: string;
  email: string | null;
  iat: number | null;
  nbf: number | null;
  exp: number;
}

export type AccessJwtVerification =
  | { ok: true; claims: AccessClaims }
  | ({ ok: false } & RemoteRefusal);

export function normalizeTeamDomain(value: string): string {
  return value.trim().replace(/^https?:\/\//i, '').replace(/\/+$/, '').toLowerCase();
}

export function expectedIssuer(teamDomain: string): string {
  return `https://${normalizeTeamDomain(teamDomain)}`;
}

/** RFC 7517 endpoint for a Cloudflare Access team. */
export function accessJwksUrl(teamDomain: string): string {
  return `https://${normalizeTeamDomain(teamDomain)}/cdn-cgi/access/certs`;
}

/**
 * The ONLY network path in this module. Constructing it performs no I/O;
 * a fetch happens only when a verification actually reads keys.
 */
export function createAccessJwksSource(
  teamDomain: string,
  fetchImpl: typeof fetch = globalThis.fetch,
  timeoutMs = 5_000,
): JwksSource {
  const url = accessJwksUrl(teamDomain);
  return async () => {
    const response = await fetchImpl(url, {
      method: 'GET',
      headers: { accept: 'application/json' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      throw new Error(`The Access JWKS endpoint answered HTTP ${response.status}.`);
    }
    const body = (await response.json()) as unknown;
    if (!isKeySet(body)) {
      throw new Error('The Access JWKS endpoint did not return a key set.');
    }
    return body;
  };
}

function isKeySet(value: unknown): value is JsonWebKeySet {
  if (typeof value !== 'object' || value === null) return false;
  const keys = (value as { keys?: unknown }).keys;
  return Array.isArray(keys);
}

function fail(code: RemoteRefusal['code'], detail: string): RemoteRefusal {
  return {
    code,
    detail,
    recovery:
      code === 'REMOTE_TOKEN_EXPIRED'
        ? 'Reauthenticate through Cloudflare Access; the durable Council session is resumed without a new billable start.'
        : 'Obtain a fresh Cf-Access-Jwt-Assertion from Cloudflare Access; a forwarded identity header alone is never accepted.',
  };
}

function decodeSegment(segment: string, label: string): Buffer | null {
  if (segment.length === 0 || segment.length > MAX_SEGMENT_BYTES) return null;
  if (!BASE64URL.test(segment)) return null;
  try {
    return Buffer.from(segment, 'base64url');
  } catch {
    return null;
  }
}

function parseJsonObject(buffer: Buffer): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(buffer.toString('utf8'));
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
}

function selectKey(
  keys: readonly AccessSigningKey[],
  kid: string | null,
): AccessSigningKey | null {
  if (kid !== null) {
    return keys.find((key) => key.kid === kid) ?? null;
  }
  // Without a kid, only an unambiguous single-key set is usable.
  return keys.length === 1 ? keys[0] : null;
}

function audienceOf(value: unknown): string[] | null {
  if (typeof value === 'string') return value.length > 0 ? [value] : null;
  if (Array.isArray(value) && value.every((entry) => typeof entry === 'string')) {
    return value as string[];
  }
  return null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Verify one Access JWT end to end. Every failure is typed; no failure
 * ever returns a subject.
 */
export async function verifyAccessJwt(
  token: string,
  expectations: AccessJwtExpectations,
): Promise<AccessJwtVerification> {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_MALFORMED', 'The token is not a three-segment JWT.'),
    };
  }
  const [encodedHeader, encodedPayload, encodedSignature] = parts;

  const headerBytes = decodeSegment(encodedHeader, 'header');
  const payloadBytes = decodeSegment(encodedPayload, 'payload');
  const signatureBytes = decodeSegment(encodedSignature, 'signature');
  if (!headerBytes || !payloadBytes || !signatureBytes) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_MALFORMED', 'A JWT segment is empty, oversized or not base64url.'),
    };
  }

  const header = parseJsonObject(headerBytes);
  const payload = parseJsonObject(payloadBytes);
  if (!header || !payload) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_MALFORMED', 'The JWT header or payload is not a JSON object.'),
    };
  }

  if (header.alg !== 'RS256') {
    return {
      ok: false,
      ...fail(
        'REMOTE_TOKEN_ALGORITHM_UNSUPPORTED',
        `The token algorithm ${JSON.stringify(String(header.alg))} is not RS256; no other algorithm is accepted.`,
      ),
    };
  }
  const kid = typeof header.kid === 'string' && header.kid.length > 0 ? header.kid : null;

  let keySet: JsonWebKeySet;
  try {
    keySet = await expectations.jwks();
  } catch (error) {
    return {
      ok: false,
      ...fail(
        'REMOTE_TOKEN_KEY_UNKNOWN',
        `The Access JWKS could not be read: ${error instanceof Error ? error.message : String(error)}`,
      ),
    };
  }
  const signingKey = selectKey(keySet.keys, kid);
  if (!signingKey || signingKey.kty !== 'RSA' || !signingKey.n || !signingKey.e) {
    return {
      ok: false,
      ...fail(
        'REMOTE_TOKEN_KEY_UNKNOWN',
        kid === null
          ? 'The token names no key id and the JWKS does not hold exactly one usable RSA key.'
          : `The JWKS holds no usable RSA key for key id ${JSON.stringify(kid)}.`,
      ),
    };
  }

  let signatureValid = false;
  try {
    const publicKey = createPublicKey({ key: signingKey, format: 'jwk' });
    signatureValid = cryptoVerify(
      'RSA-SHA256',
      Buffer.from(`${encodedHeader}.${encodedPayload}`, 'utf8'),
      publicKey,
      signatureBytes,
    );
  } catch {
    signatureValid = false;
  }
  if (!signatureValid) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_SIGNATURE_INVALID', 'The JWT signature does not verify against the Access JWKS.'),
    };
  }

  // Signature is valid; only now are the claims trusted.
  const issuer = typeof payload.iss === 'string' ? payload.iss : null;
  if (issuer !== expectedIssuer(expectations.team_domain)) {
    return {
      ok: false,
      ...fail(
        'REMOTE_TOKEN_ISSUER_MISMATCH',
        `The token issuer ${JSON.stringify(issuer)} is not the configured Access team domain.`,
      ),
    };
  }

  const audience = audienceOf(payload.aud);
  if (!audience || !audience.includes(expectations.audience)) {
    return {
      ok: false,
      ...fail(
        'REMOTE_TOKEN_AUDIENCE_MISMATCH',
        'The token audience does not include the Council Access application audience.',
      ),
    };
  }

  const exp = numberOrNull(payload.exp);
  if (exp === null) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_MALFORMED', 'The token carries no numeric exp claim.'),
    };
  }
  const now = (expectations.now_seconds ?? (() => Math.floor(Date.now() / 1_000)))();
  const skew = expectations.clock_skew_seconds ?? 60;

  if (now > exp + skew) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_EXPIRED', 'The token has expired.'),
    };
  }

  const nbf = numberOrNull(payload.nbf);
  if (nbf !== null && now + skew < nbf) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_NOT_YET_VALID', 'The token is not valid yet (nbf is in the future).'),
    };
  }

  const sub = typeof payload.sub === 'string' ? payload.sub.trim() : '';
  if (sub.length === 0) {
    return {
      ok: false,
      ...fail('REMOTE_TOKEN_SUBJECT_MISSING', 'The verified token carries no subject.'),
    };
  }

  return {
    ok: true,
    claims: {
      iss: issuer,
      aud: audience,
      sub,
      email: typeof payload.email === 'string' && payload.email.length > 0 ? payload.email : null,
      iat: numberOrNull(payload.iat),
      nbf,
      exp,
    },
  };
}
