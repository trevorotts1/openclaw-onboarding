/**
 * Council remote access contract (WER-023 code half).
 *
 * This directory is the APPLICATION-side half of the Cloudflare remote
 * topology. It never creates, modifies or calls a Cloudflare resource:
 * the Tunnel, the Access application, the audience and the origin already
 * exist and are bound here as configuration.
 *
 * Non-negotiables encoded by these types:
 * - a forwarded identity header is NEVER identity on its own; only a
 *   verified Access JWT yields a subject;
 * - remote resolution is opt-in per customer; a disabled configuration
 *   refuses remote resolution with a typed reason while local/managed
 *   operation stays untouched;
 * - one session resolves to exactly ONE owning endpoint URL, or a typed
 *   failure — never two candidates, never a fallback to localhost.
 */

import type { SessionAuthority } from '../service/types.js';

export const REMOTE_CONFIG_SCHEMA = 'wise-elders.remote-config/v1';

/**
 * Every refusal is typed and distinct. `REMOTE_SESSION_NOT_AVAILABLE` is
 * deliberately shared by "unknown session" and "another subject's
 * session" so a cross-user probe cannot learn that a session exists.
 */
export type RemoteRefusalCode =
  | 'REMOTE_DISABLED'
  | 'REMOTE_CONFIG_INVALID'
  | 'REMOTE_UNAUTHENTICATED'
  | 'REMOTE_TOKEN_MALFORMED'
  | 'REMOTE_TOKEN_ALGORITHM_UNSUPPORTED'
  | 'REMOTE_TOKEN_KEY_UNKNOWN'
  | 'REMOTE_TOKEN_SIGNATURE_INVALID'
  | 'REMOTE_TOKEN_ISSUER_MISMATCH'
  | 'REMOTE_TOKEN_AUDIENCE_MISMATCH'
  | 'REMOTE_TOKEN_EXPIRED'
  | 'REMOTE_TOKEN_NOT_YET_VALID'
  | 'REMOTE_TOKEN_SUBJECT_MISSING'
  | 'REMOTE_ORIGIN_NOT_ALLOWED'
  | 'REMOTE_SESSION_ID_MISSING'
  | 'REMOTE_SESSION_NOT_AVAILABLE'
  | 'REMOTE_SESSION_ENDPOINT_MISSING'
  | 'REMOTE_SESSION_ENDPOINT_AMBIGUOUS'
  | 'REMOTE_SESSION_ENDPOINT_UNKNOWN'
  | 'REMOTE_SESSION_ENDPOINT_UNVERIFIED'
  | 'REMOTE_REAUTH_SESSION_MISMATCH';

export interface RemoteRefusal {
  code: RemoteRefusalCode;
  detail: string;
  recovery: string;
}

/** One verified HTTPS origin the Council is reachable through. */
export interface RemoteEndpoint {
  endpoint_id: string;
  /** Absolute HTTPS origin, e.g. https://council.zerohumanworkforce.com */
  origin: string;
  /** True only for an endpoint whose HTTPS origin is verified. */
  verified: true;
}

export interface RemoteEnabledConfig {
  schema_version: typeof REMOTE_CONFIG_SCHEMA;
  enabled: true;
  /** e.g. sweet-wave-ca28.cloudflareaccess.com (no scheme). */
  team_domain: string;
  /** The Access application's pinned `aud` claim. */
  audience: string;
  /** Exact allowed origins. Nothing is matched by prefix or suffix. */
  allowed_origins: readonly string[];
  /** Exactly the endpoints a session may resolve to. */
  endpoints: readonly RemoteEndpoint[];
  /** Source of the Access JWKS. Injectable so tests make zero network calls. */
  jwks: JwksSource;
  /** Applied to exp and nbf. Default 60 seconds. */
  clock_skew_seconds?: number;
}

export interface RemoteDisabledConfig {
  schema_version: typeof REMOTE_CONFIG_SCHEMA;
  enabled: false;
}

export type RemoteConfiguration = RemoteEnabledConfig | RemoteDisabledConfig;

/** Minimal JWK shape; `kid` selects the signing key. */
export interface AccessSigningKey {
  kty?: string;
  kid?: string;
  alg?: string;
  use?: string;
  n?: string;
  e?: string;
  [member: string]: unknown;
}

export interface JsonWebKeySet {
  keys: AccessSigningKey[];
}

/** Injected JWKS source. Production resolves the live endpoint; tests inject. */
export type JwksSource = () => Promise<JsonWebKeySet>;

/** Request headers as delivered to the application behind Access. */
export type RemoteHeaders = Readonly<
  Record<string, string | string[] | undefined>
>;

/** The subject established by a VERIFIED Access JWT. */
export interface RemoteIdentity {
  subject: string;
  email: string | null;
  issuer: string;
  audience: readonly string[];
  issued_at: number | null;
  expires_at: number;
}

export type RemoteAuthentication =
  | { ok: true; identity: RemoteIdentity }
  | ({ ok: false } & RemoteRefusal);

/**
 * Durable ownership of one session. `endpoint_ids` must name exactly one
 * configured endpoint; anything else is refused rather than guessed.
 */
export interface RemoteSessionRecord {
  session_id: string;
  owner_subject: string;
  authority: SessionAuthority;
  endpoint_ids: readonly string[];
  /** The owning Command Center URL for a managed session, if recorded. */
  owning_session_url?: string | null;
}

export type SessionLookup = (
  sessionId: string,
) => RemoteSessionRecord | null | Promise<RemoteSessionRecord | null>;

export type RemoteSessionResolution =
  | {
      kind: 'resolved';
      session_id: string;
      /** Exactly one verified HTTPS URL. There is no candidates list. */
      url: string;
      endpoint_id: string;
      authority: SessionAuthority;
      subject: string;
      /** True when a durable session was resumed rather than re-created. */
      resumed: boolean;
      billable_starts: number;
    }
  | ({
      kind: 'refused';
      session_id: string | null;
      /** No URL is ever emitted on a refusal. */
      url: null;
      billable_starts: number;
    } & RemoteRefusal);

/**
 * Connection loss is a transport state, never a cancellation. The durable
 * session id survives and the same session is resumable after
 * reauthentication.
 */
export interface RemoteConnectionLoss {
  state: 'reconnecting';
  session_id: string;
  cancelled: false;
  detail: string;
  billable_starts: number;
  cancellations: number;
}
