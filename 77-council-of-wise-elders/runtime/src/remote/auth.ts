/**
 * Trusted remote identity (WER-023).
 *
 * The plan's rule is literal: arbitrary forwarded headers do NOT
 * establish identity. `Cf-Access-Authenticated-User-Email` is read only
 * as a hint AFTER a JWT verifies; on its own it establishes nothing and
 * is refused exactly like no credential at all.
 *
 * Identity is also bound to the exact configured origin set. A request
 * whose Host (or, when present, Origin) is outside that set is refused
 * even when it carries a perfectly valid JWT.
 */

import {
  ACCESS_EMAIL_HEADER,
  ACCESS_JWT_HEADER,
  verifyAccessJwt,
} from './access-jwt.js';
import type {
  RemoteAuthentication,
  RemoteEnabledConfig,
  RemoteHeaders,
  RemoteRefusal,
} from './types.js';

function headerValue(headers: RemoteHeaders, name: string): string | null {
  const wanted = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() !== wanted) continue;
    if (typeof value === 'string') return value.trim();
    if (Array.isArray(value)) {
      const first = value.find((entry) => typeof entry === 'string' && entry.trim().length > 0);
      return first ? first.trim() : null;
    }
  }
  return null;
}

function canonicalOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url.origin.toLowerCase();
  } catch {
    return null;
  }
}

function allowedOrigins(config: RemoteEnabledConfig): string[] {
  return config.allowed_origins
    .map((origin) => canonicalOrigin(origin))
    .filter((origin): origin is string => origin !== null);
}

function allowedHosts(config: RemoteEnabledConfig): Set<string> {
  const hosts = new Set<string>();
  for (const origin of config.allowed_origins) {
    try {
      hosts.add(new URL(origin).host.toLowerCase());
    } catch {
      // Validated at configuration time; an unparseable entry matches nothing.
    }
  }
  return hosts;
}

/**
 * Exact origin-set membership. Host is compared as an exact `host[:port]`
 * string, never by suffix, so `council.example.com.evil.test` cannot pass.
 */
export function requestOriginIsAllowed(
  config: RemoteEnabledConfig,
  headers: RemoteHeaders,
): boolean {
  const host = headerValue(headers, 'host');
  if (host === null || !allowedHosts(config).has(host.toLowerCase())) {
    return false;
  }
  const originHeader = headerValue(headers, 'origin');
  if (originHeader !== null) {
    const canonical = canonicalOrigin(originHeader);
    if (canonical === null) return false;
    if (!allowedOrigins(config).includes(canonical)) return false;
  }
  return true;
}

function refuse(code: RemoteRefusal['code'], detail: string, recovery: string): RemoteAuthentication {
  return { ok: false, code, detail, recovery };
}

export interface RemoteAuthOptions {
  /** Injected clock in epoch seconds; tests fix it. */
  now_seconds?: () => number;
}

/**
 * Authenticate one request behind Access.
 *
 * Order matters: the JWT is the only identity input, and it is verified
 * before any claim is read. The origin set is then enforced.
 */
export async function authenticateRemoteRequest(
  headers: RemoteHeaders,
  config: RemoteEnabledConfig,
  options: RemoteAuthOptions = {},
): Promise<RemoteAuthentication> {
  const token = headerValue(headers, ACCESS_JWT_HEADER);
  if (token === null) {
    // A forwarded email header may be present and is deliberately ignored.
    const hint = headerValue(headers, ACCESS_EMAIL_HEADER);
    return refuse(
      'REMOTE_UNAUTHENTICATED',
      hint === null
        ? 'The request carries no Cf-Access-Jwt-Assertion.'
        : 'The request carries only a forwarded identity header. A forwarded header never establishes identity.',
      'Send the request through Cloudflare Access so a Cf-Access-Jwt-Assertion is attached, then retry.',
    );
  }

  const verification = await verifyAccessJwt(token, {
    team_domain: config.team_domain,
    audience: config.audience,
    jwks: config.jwks,
    clock_skew_seconds: config.clock_skew_seconds,
    now_seconds: options.now_seconds,
  });
  if (!verification.ok) {
    return { ok: false, code: verification.code, detail: verification.detail, recovery: verification.recovery };
  }

  if (!requestOriginIsAllowed(config, headers)) {
    return refuse(
      'REMOTE_ORIGIN_NOT_ALLOWED',
      'The request Host or Origin is outside the configured allowed origin set.',
      'Use the configured Council origin exactly; a valid token does not authorize another origin.',
    );
  }

  const { claims } = verification;
  return {
    ok: true,
    identity: {
      subject: claims.sub,
      // The hint is only corroboration once the JWT has established a subject.
      email: headerValue(headers, ACCESS_EMAIL_HEADER) ?? claims.email,
      issuer: claims.iss,
      audience: claims.aud,
      issued_at: claims.iat,
      expires_at: claims.exp,
    },
  };
}
