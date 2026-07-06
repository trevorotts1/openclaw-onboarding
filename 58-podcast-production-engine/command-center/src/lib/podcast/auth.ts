/**
 * Podcast Production Engine dashboard: auth (design Section 11).
 *
 * Two layers, fail closed:
 *   Layer 1: Cloudflare Access on the public hostname. Enforced by the
 *            existing Command Center middleware (REQUIRE_CF_ACCESS). This
 *            module additionally surfaces the authenticated email.
 *   Layer 2: the revocable podcast dashboard token, scoped to /podcast and
 *            /api/podcast/*. Raw token values are NEVER stored or logged;
 *            only sha256 hashes live in podcast_dashboard_tokens (written by
 *            podcast_state.py at mint time, or by the operator token screen
 *            through the guarded auth handle).
 *
 * Session cookie: after a successful one-time token paste, the app sets an
 * HttpOnly, Secure, SameSite=Lax cookie holding a SESSION REFERENCE (token id
 * plus an HMAC over a box-local secret), never the token itself. Every
 * request re-validates against the token row, so revocation is immediate:
 * a single UPDATE setting revoked_at kills the session on the very next
 * request (acceptance criterion 7). podcast_client_state.active = 0 (the
 * application blade of the kill switch) also fails every client session.
 *
 * Operator access: Cloudflare Access authenticated email matching the box's
 * operator allowlist (PODCAST_OPERATOR_EMAILS, falling back to
 * OPERATOR_EMAILS), or a valid MC_API_TOKEN bearer for scripts. Client
 * dashboard tokens NEVER unlock operator fields.
 *
 * Secrecy: no token value, hash, or credential is ever included in an error
 * message, a log line, or a serialized response from this module.
 */

import { createHash, createHmac, randomBytes, timingSafeEqual } from 'crypto';
import path from 'path';
import fs from 'fs';
import type { NextRequest } from 'next/server';
import type Database from 'better-sqlite3';
import {
  getPodcastAuthDb,
  getPodcastReadDb,
  isClientActive,
  resolvePodcastClientId,
  resolvePodcastDbPath,
} from './db';
import type { PodcastDashboardTokenRow, TokenListItem } from './types';

export const PODCAST_SESSION_COOKIE = 'pdt_session';
const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60; // 30 days (design 11.2)
const LAST_USED_TOUCH_MIN_MS = 60 * 1000; // throttle last_used_at writes

export type PodcastViewer =
  | { kind: 'operator'; email: string | null }
  | { kind: 'client'; tokenId: string }
  | { kind: 'none' };

/* ------------------------------------------------------------------ */
/* Cookie-signing secret: box-local, 0600, beside the DB directory.    */
/* ------------------------------------------------------------------ */

let cachedSecret: Buffer | null = null;

function getSessionSecret(): Buffer | null {
  if (cachedSecret) return cachedSecret;
  const dir = path.dirname(resolvePodcastDbPath());
  const secretPath = path.join(dir, '.dashboard-session-secret');
  try {
    if (fs.existsSync(secretPath)) {
      const hex = fs.readFileSync(secretPath, 'utf8').trim();
      if (hex.length >= 32) {
        cachedSecret = Buffer.from(hex, 'hex');
        return cachedSecret;
      }
    }
    if (!fs.existsSync(dir)) return null; // engine never provisioned; fail closed
    const fresh = randomBytes(32);
    fs.writeFileSync(secretPath, fresh.toString('hex'), { mode: 0o600 });
    cachedSecret = fresh;
    return cachedSecret;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Token hashing and lookups                                           */
/* ------------------------------------------------------------------ */

export function sha256Hex(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function findTokenByHash(db: Database.Database, tokenHash: string): PodcastDashboardTokenRow | undefined {
  return db
    .prepare('SELECT * FROM podcast_dashboard_tokens WHERE token_hash = ?')
    .get(tokenHash) as PodcastDashboardTokenRow | undefined;
}

function findTokenById(db: Database.Database, tokenId: string): PodcastDashboardTokenRow | undefined {
  return db
    .prepare('SELECT * FROM podcast_dashboard_tokens WHERE token_id = ?')
    .get(tokenId) as PodcastDashboardTokenRow | undefined;
}

function touchLastUsed(tokenId: string, lastUsedAt: string | null): void {
  if (lastUsedAt) {
    const then = Date.parse(lastUsedAt.endsWith('Z') ? lastUsedAt : lastUsedAt + 'Z');
    if (!Number.isNaN(then) && Date.now() - then < LAST_USED_TOUCH_MIN_MS) return;
  }
  const authDb = getPodcastAuthDb();
  if (!authDb) return;
  try {
    authDb
      .prepare("UPDATE podcast_dashboard_tokens SET last_used_at = datetime('now') WHERE token_id = ?")
      .run(tokenId);
  } catch {
    // A failed touch never blocks a valid request.
  }
}

/* ------------------------------------------------------------------ */
/* Session cookie encode / decode                                      */
/* ------------------------------------------------------------------ */

function signSession(tokenId: string, issuedAtSeconds: number): string | null {
  const secret = getSessionSecret();
  if (!secret) return null;
  const payload = `${tokenId}.${issuedAtSeconds}`;
  const mac = createHmac('sha256', secret).update(payload, 'utf8').digest('hex');
  return `${payload}.${mac}`;
}

function verifySessionValue(value: string): { tokenId: string } | null {
  const secret = getSessionSecret();
  if (!secret) return null;
  const parts = value.split('.');
  if (parts.length !== 3) return null;
  const [tokenId, iatRaw, mac] = parts;
  if (!/^pdt_[A-Za-z0-9_-]+$/.test(tokenId)) return null;
  const iat = Number(iatRaw);
  if (!Number.isFinite(iat)) return null;
  const ageSeconds = Math.floor(Date.now() / 1000) - iat;
  if (ageSeconds < 0 || ageSeconds > SESSION_MAX_AGE_SECONDS) return null;
  const expected = createHmac('sha256', secret).update(`${tokenId}.${iatRaw}`, 'utf8').digest('hex');
  const a = Buffer.from(mac, 'utf8');
  const b = Buffer.from(expected, 'utf8');
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  return { tokenId };
}

/* ------------------------------------------------------------------ */
/* Operator detection                                                  */
/* ------------------------------------------------------------------ */

function operatorAllowlist(): string[] {
  const raw = process.env.PODCAST_OPERATOR_EMAILS || process.env.OPERATOR_EMAILS || '';
  return raw
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter((e) => e.length > 0);
}

/** Minimal header reader so both NextRequest.headers and next/headers work. */
export interface HeaderReader {
  get(name: string): string | null;
}

export function isOperatorRequest(headers: HeaderReader): { operator: boolean; email: string | null } {
  const email = headers.get('cf-access-authenticated-user-email');
  if (email) {
    const allow = operatorAllowlist();
    if (allow.length > 0 && allow.includes(email.trim().toLowerCase())) {
      return { operator: true, email };
    }
  }
  // Script path: MC_API_TOKEN bearer (fail closed when the env is unset).
  const mcToken = process.env.MC_API_TOKEN;
  const authHeader = headers.get('authorization');
  if (mcToken && authHeader && authHeader.startsWith('Bearer ')) {
    const presented = authHeader.substring(7);
    const a = Buffer.from(presented, 'utf8');
    const b = Buffer.from(mcToken, 'utf8');
    if (a.length === b.length && timingSafeEqual(a, b)) {
      return { operator: true, email };
    }
  }
  return { operator: false, email };
}

/* ------------------------------------------------------------------ */
/* The main resolution: who is viewing?                                */
/* ------------------------------------------------------------------ */

/**
 * Resolve the viewer for a request. Validation order per design 11.2:
 * client active check, then token row exists and revoked_at IS NULL, then
 * serve. Operators bypass the token layer but never through a client token.
 */
export function resolveViewer(headers: HeaderReader, cookieValue: string | null): PodcastViewer {
  const op = isOperatorRequest(headers);
  if (op.operator) return { kind: 'operator', email: op.email };

  if (!cookieValue) return { kind: 'none' };
  const parsed = verifySessionValue(cookieValue);
  if (!parsed) return { kind: 'none' };

  const db = getPodcastReadDb();
  if (!db) return { kind: 'none' };
  const clientId = resolvePodcastClientId(db);
  if (!clientId) return { kind: 'none' };
  if (!isClientActive(db, clientId)) return { kind: 'none' }; // kill switch blade 1

  const row = findTokenById(db, parsed.tokenId);
  if (!row || row.revoked_at !== null) return { kind: 'none' };
  if (row.client_id !== clientId) return { kind: 'none' };

  touchLastUsed(row.token_id, row.last_used_at);
  return { kind: 'client', tokenId: row.token_id };
}

/** Convenience for route handlers. */
export function viewerFromRequest(req: NextRequest): PodcastViewer {
  const cookie = req.cookies.get(PODCAST_SESSION_COOKIE)?.value ?? null;
  return resolveViewer(req.headers, cookie);
}

/**
 * Exchange a pasted raw token for a session cookie value. Returns null on
 * any failure (unknown token, revoked, client inactive, engine not
 * provisioned). The raw token is hashed immediately and never retained.
 */
export function createSessionFromRawToken(rawToken: string): string | null {
  const trimmed = rawToken.trim();
  if (!/^pdt_[A-Za-z0-9_]+_[0-9a-f]{32}$/.test(trimmed) && !/^pdt_[A-Za-z0-9_-]{8,128}$/.test(trimmed)) {
    return null;
  }
  const db = getPodcastReadDb();
  if (!db) return null;
  const clientId = resolvePodcastClientId(db);
  if (!clientId) return null;
  if (!isClientActive(db, clientId)) return null;
  const row = findTokenByHash(db, sha256Hex(trimmed));
  if (!row || row.revoked_at !== null || row.client_id !== clientId) return null;
  const cookieValue = signSession(row.token_id, Math.floor(Date.now() / 1000));
  if (!cookieValue) return null;
  touchLastUsed(row.token_id, row.last_used_at);
  return cookieValue;
}

export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true as const,
  secure: true as const,
  sameSite: 'lax' as const,
  path: '/' as const,
  maxAge: SESSION_MAX_AGE_SECONDS,
};

/* ------------------------------------------------------------------ */
/* Token management (operator only; the sole write endpoints)          */
/* ------------------------------------------------------------------ */

function ulidLike(): string {
  // Sortable-enough id for tokens minted from the dashboard: millisecond
  // timestamp base36 plus 10 random base36 chars. podcast_state.py mints
  // true ULIDs; both live in the same TEXT primary key space.
  const time = Date.now().toString(36).toUpperCase();
  const rand = randomBytes(8).toString('hex').slice(0, 10).toUpperCase();
  return (time + rand).slice(0, 26);
}

export function mintToken(clientId: string, label: string | null): {
  tokenId: string;
  rawTokenShownOnce: string;
} | null {
  const authDb = getPodcastAuthDb();
  if (!authDb) return null;
  const raw = `pdt_${clientId}_${randomBytes(16).toString('hex')}`;
  const tokenId = `pdt_${ulidLike()}`;
  try {
    authDb
      .prepare(
        'INSERT INTO podcast_dashboard_tokens (token_id, client_id, token_hash, label) VALUES (?, ?, ?, ?)'
      )
      .run(tokenId, clientId, sha256Hex(raw), label);
  } catch {
    return null;
  }
  return { tokenId, rawTokenShownOnce: raw };
}

export function revokeToken(tokenId: string, reason: string | null): { revokedAt: string } | null {
  const authDb = getPodcastAuthDb();
  if (!authDb) return null;
  try {
    const result = authDb
      .prepare(
        "UPDATE podcast_dashboard_tokens SET revoked_at = datetime('now'), revoked_reason = ? " +
          'WHERE token_id = ? AND revoked_at IS NULL'
      )
      .run(reason, tokenId);
    if (result.changes === 0) return null;
    const row = findTokenById(getPodcastReadDb() as Database.Database, tokenId);
    return { revokedAt: row?.revoked_at ?? new Date().toISOString() };
  } catch {
    return null;
  }
}

export function listTokens(clientId: string): TokenListItem[] {
  const db = getPodcastReadDb();
  if (!db) return [];
  const rows = db
    .prepare(
      'SELECT token_id, label, created_at, last_used_at, revoked_at, revoked_reason ' +
        'FROM podcast_dashboard_tokens WHERE client_id = ? ORDER BY created_at DESC'
    )
    .all(clientId) as Array<{
    token_id: string;
    label: string | null;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
    revoked_reason: string | null;
  }>;
  return rows.map((r) => ({
    tokenId: r.token_id,
    label: r.label,
    createdAt: r.created_at,
    lastUsedAt: r.last_used_at,
    revokedAt: r.revoked_at,
    revokedReason: r.revoked_reason,
  }));
}
