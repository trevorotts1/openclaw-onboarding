/**
 * Session authority resolution (WER-021).
 *
 * One authority per session. A managed session is LINKED to its owning
 * Command Center URL and is never started locally; a standalone session
 * lives on this service's verified origin. A managed record without a
 * valid owner URL is BLOCKED — never silently converted into a local
 * session.
 */

import {
  type SessionAuthorityRecord,
  type SessionTarget,
} from './types.js';

/** Canonical local session path; the shared CC UI route is /council/<id>. */
export function sessionPath(sessionId: string): string {
  return `/council/${encodeURIComponent(sessionId)}`;
}

export function eventsPath(sessionId: string): string {
  return `/api/council/sessions/${encodeURIComponent(sessionId)}/events`;
}

function absoluteHttpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url;
  } catch {
    return null;
  }
}

/**
 * Build the true local session URL from the ACTUAL bound origin (the
 * origin the listener reported), never from a configured pretty host.
 */
export function sessionUrl(origin: string, sessionId: string): string {
  const base = absoluteHttpUrl(origin);
  if (!base) {
    throw new Error(`Origin "${origin}" is not an absolute HTTP(S) URL.`);
  }
  return new URL(sessionPath(sessionId), base).toString();
}

function blocked(
  record: SessionAuthorityRecord,
  code: string,
  detail: string,
  recovery: string,
): SessionTarget {
  return {
    kind: 'blocked',
    session_id: record.session_id,
    url: null,
    authority:
      record.authority === 'managed' || record.authority === 'standalone'
        ? record.authority
        : 'unknown',
    launched_locally: false,
    blocker: { code, detail },
    recovery,
  };
}

export function resolveSessionTarget(
  record: SessionAuthorityRecord,
  options: { origin: string | null },
): SessionTarget {
  if (!record.session_id || record.session_id.trim().length === 0) {
    return blocked(
      record,
      'SESSION_ID_MISSING',
      'The session record carries no session id.',
      'Supply the durable session id returned by the owning authority.',
    );
  }

  if (record.authority === 'managed') {
    const owner = record.owning_session_url?.trim();
    if (!owner) {
      return blocked(
        record,
        'MANAGED_SESSION_OWNER_URL_MISSING',
        `Managed session ${record.session_id} has no owning Command Center URL.`,
        'Link the session to its owning Command Center URL; a managed session is never duplicated locally.',
      );
    }
    if (!absoluteHttpUrl(owner)) {
      return blocked(
        record,
        'MANAGED_SESSION_OWNER_URL_INVALID',
        `Managed session ${record.session_id} carries an owner URL that is not absolute HTTP(S).`,
        'Correct the recorded owning Command Center URL; do not start a local copy.',
      );
    }
    return {
      kind: 'external',
      session_id: record.session_id,
      url: owner,
      authority: 'managed',
      launched_locally: false,
    };
  }

  if (record.authority === 'standalone') {
    if (!options.origin || !absoluteHttpUrl(options.origin)) {
      return blocked(
        record,
        'SERVICE_ORIGIN_UNAVAILABLE',
        'The standalone service is not bound to a verified local origin.',
        'Start the front-door service and re-resolve the session URL from its reported origin.',
      );
    }
    return {
      kind: 'local',
      session_id: record.session_id,
      url: sessionUrl(options.origin, record.session_id),
      authority: 'standalone',
      launched_locally: true,
    };
  }

  return blocked(
    record,
    'SESSION_AUTHORITY_UNKNOWN',
    `Session ${record.session_id} has no recognised authority.`,
    'Record exactly one authority (standalone or managed) for the session.',
  );
}
