/**
 * DiagnosticRetentionPolicy behavior (directive Section 16.6).
 *
 * There is one policy implementation, applied by a single diagnostic sink;
 * other modules cannot write raw bodies directly. This module holds the
 * policy defaults, the bounds, and the pure capture/read decision functions
 * the sink consults. It performs no I/O itself.
 *
 * Non-negotiable rules encoded here:
 * - capture is disabled by default;
 * - enabling requires explicit owner or audited support authorization for
 *   one named session; an enabled flag in a request body is not authority;
 * - defaults: 60 minute capture window (max 4 hours), 24 hour payload TTL
 *   (max 72 hours), at most 5 MiB per operation and 25 MiB per session;
 * - truncation is labeled and never treated as complete source evidence;
 * - hidden reasoning, access tokens, cookies, authentication headers, and
 *   private keys are NEVER captured, in any mode, diagnostic included.
 */

import {
  DEFAULT_DIAGNOSTIC_RETENTION_POLICY,
  DIAGNOSTIC_LIMITS,
  type DiagnosticRetentionPolicy,
} from './schemas.js';

export { DEFAULT_DIAGNOSTIC_RETENTION_POLICY, DIAGNOSTIC_LIMITS };
export type { DiagnosticRetentionPolicy };

/** Data classes that must never be persisted or displayed, in any mode. */
export const NEVER_CAPTURED_DATA_CLASSES: readonly string[] = [
  'hidden_reasoning',
  'access_token',
  'cookie',
  'authentication_header',
  'private_key',
];

export function isNeverCaptured(dataClass: string): boolean {
  return NEVER_CAPTURED_DATA_CLASSES.includes(dataClass);
}

export interface CaptureRequest {
  policy: DiagnosticRetentionPolicy;
  /** Session the capture would record; must equal the authorized session. */
  sessionId: string;
  dataClass: string;
  byteLength: number;
  /** Bytes already captured for this session under this policy. */
  sessionBytesAlreadyCaptured: number;
  /** Minutes since the capture window opened. */
  minutesSinceWindowStart: number;
  /** Whether redaction and a protected store are established. */
  protectionEstablished: boolean;
  /** Whether the session has been deleted or capture revoked. */
  sessionDeletedOrRevoked: boolean;
}

export type CaptureDecision =
  | { allowed: true; truncated: boolean; effectiveBytes: number }
  | { allowed: false; reason: string };

/**
 * Decide whether one payload may be captured. On any failure the sink
 * records only safe metadata (error code, schema path, byte count, response
 * hash); it never falls back to plaintext temporary files.
 */
export function evaluateCapture(req: CaptureRequest): CaptureDecision {
  const { policy } = req;
  if (isNeverCaptured(req.dataClass)) {
    return { allowed: false, reason: 'data class is never captured in any mode' };
  }
  if (!policy.enabled) {
    return { allowed: false, reason: 'diagnostic capture is disabled' };
  }
  if (policy.session_id === null || policy.session_id !== req.sessionId) {
    return { allowed: false, reason: 'capture is authorized for one named session only' };
  }
  if (policy.authorized_by_principal === null || policy.authorization_kind === null) {
    return { allowed: false, reason: 'no owner or audited support authorization on record' };
  }
  if (req.sessionDeletedOrRevoked) {
    return { allowed: false, reason: 'session deleted or capture revoked' };
  }
  if (req.minutesSinceWindowStart > policy.capture_window_minutes) {
    return { allowed: false, reason: 'capture window has closed' };
  }
  if (!req.protectionEstablished) {
    return { allowed: false, reason: 'redaction or protected store unavailable; metadata only' };
  }
  const sessionRemaining = policy.max_bytes_per_session - req.sessionBytesAlreadyCaptured;
  if (sessionRemaining <= 0) {
    return { allowed: false, reason: 'per-session capture byte ceiling reached' };
  }
  const effectiveBytes = Math.min(
    req.byteLength,
    policy.max_bytes_per_operation,
    sessionRemaining,
  );
  return {
    allowed: true,
    truncated: effectiveBytes < req.byteLength,
    effectiveBytes,
  };
}

/** A captured payload is inaccessible at or after its TTL, even before cleanup. */
export function isCaptureExpired(capturedAtMs: number, nowMs: number, ttlHours: number): boolean {
  return nowMs - capturedAtMs >= ttlHours * 60 * 60 * 1000;
}
