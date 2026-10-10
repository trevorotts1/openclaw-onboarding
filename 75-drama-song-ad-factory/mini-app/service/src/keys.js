// ============================================================================
// keys.js — Drama Studio service: service key code (U2)
//
// Joint plan section 3.15 + 3.11. The studio mints every credential and keeps
// ONLY a fingerprint (sha256). A raw key value is returned to its owner exactly
// once, at mint time, and is never stored, logged or echoed back.
//
// Key kinds (all resolved through the same key:<fingerprint> record):
//   'link'    — a client's personal studio link (128-bit), section 3.15
//   'box'     — an OpenClaw box's own key, minted at first enrollment
//   'machine' — a Claude Code / claude-nine computer's key, minted at pairing
//
// Pairing codes (section 3.11): 8 characters from a no-look-alike alphabet,
// displayed ABCD-2345, single use, valid 15 minutes, at most 5 wrong tries.
// The studio stores only the code's fingerprint.
//
// PURE apart from crypto.subtle. No bindings, no I/O.
// ============================================================================

'use strict';

import { randomHex } from './ids.js';

/** 256-bit key, lowercase hex. */
export const KEY_BYTES = 32;

/** Section 3.11: no 0/O, no 1/I/L. 31 symbols, 8 characters = 39.5 bits. */
export const PAIRING_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
export const PAIRING_LENGTH = 8;
export const PAIRING_TTL_MS = 15 * 60 * 1000;
export const PAIRING_MAX_TRIES = 5;

export const KEY_KINDS = ['link', 'box', 'machine'];

export const AF_KEY_MALFORMED = 'AF-DS-KEY-MALFORMED';
export const AF_KEY_UNKNOWN = 'AF-DS-KEY-UNKNOWN';
export const AF_KEY_REVOKED = 'AF-DS-KEY-REVOKED';

export const AF_PAIR_UNKNOWN = 'AF-DS-PAIR-UNKNOWN';
export const AF_PAIR_EXPIRED = 'AF-DS-PAIR-EXPIRED';
export const AF_PAIR_LOCKED = 'AF-DS-PAIR-LOCKED';
export const AF_PAIR_WRONG = 'AF-DS-PAIR-WRONG';

/** sha256 hex — the only form of a secret the studio ever persists. */
export async function fingerprintOf(secret) {
  const data = new TextEncoder().encode(String(secret));
  const buf = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** Mint a fresh 256-bit key. Returns the secret ONCE and its fingerprint. */
export async function mintKey(entropyHex) {
  const entropyBytes = typeof entropyHex === 'string' && /^[0-9a-f]+$/.test(entropyHex)
    ? Math.floor(entropyHex.length / 2)
    : 0;
  const secret = entropyBytes >= KEY_BYTES ? entropyHex.slice(0, KEY_BYTES * 2) : randomHex(KEY_BYTES);
  return { secret, fingerprint: await fingerprintOf(secret) };
}

export function keyRecordKey(fingerprint) {
  return `key:${fingerprint}`;
}

/** A pairing record is stored under the fingerprint of its NORMALIZED code, so
 *  the service can find it from the code the client typed — and never from a
 *  fingerprint the client would have to know. */
export async function pairRecordKey(presentedCode) {
  return `pair:${await fingerprintOf(normalizePairingCode(presentedCode))}`;
}

/**
 * The stored record for one key. It carries the client_id the studio invented
 * for its owner — that record, and nothing in the request, is what decides
 * which client's data a key can reach (isolation.js).
 * `secret` is deliberately NOT a field here.
 */
export async function buildKeyRecord({ clientId, kind, label, secret, nowMs }) {
  if (!KEY_KINDS.includes(kind)) throw new Error(AF_KEY_MALFORMED);
  return {
    client_id: clientId,
    kind,
    label: typeof label === 'string' && label ? label : null,
    fingerprint: await fingerprintOf(secret),
    status: 'active',
    created_at: nowMs,
    last_check_in: null,
  };
}

// ---------------------------------------------------------------------------
// Pairing codes (section 3.11)
// ---------------------------------------------------------------------------

/** ABCD-2345 -> ABCD2345 (the canonical form that is fingerprinted). */
export function normalizePairingCode(input) {
  return String(input || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/** Returns { code: 'ABCD-2345', fingerprint }. The code is shown once. */
export async function mintPairingCode(entropyHex) {
  let raw = '';
  if (typeof entropyHex === 'string' && /^[0-9a-f]+$/.test(entropyHex) && entropyHex.length >= PAIRING_LENGTH * 2) {
    raw = entropyHex
      .slice(0, PAIRING_LENGTH * 2)
      .match(/.{2}/g)
      .map((byte) => PAIRING_ALPHABET[parseInt(byte, 16) % PAIRING_ALPHABET.length])
      .join('');
  } else {
    const bytes = new Uint8Array(PAIRING_LENGTH);
    crypto.getRandomValues(bytes);
    raw = [...bytes].map((b) => PAIRING_ALPHABET[b % PAIRING_ALPHABET.length]).join('');
  }
  return {
    code: `${raw.slice(0, 4)}-${raw.slice(4)}`,
    fingerprint: await fingerprintOf(raw),
  };
}

/**
 * One attempt against a stored pairing record:
 *   { client_id, fingerprint, exp, tries, status: 'open' | 'burned' | 'locked' }
 * On success the CALLER deletes the record (single use). A wrong attempt
 * increments `tries`; the 5th wrong attempt locks the code.
 */
export async function attemptPairing(record, presentedCode, nowMs) {
  if (!record || typeof record !== 'object' || typeof record.fingerprint !== 'string') {
    return { ok: false, code: AF_PAIR_UNKNOWN };
  }
  if (record.status === 'burned') return { ok: false, code: AF_PAIR_UNKNOWN };
  if (record.status === 'locked') return { ok: false, code: AF_PAIR_LOCKED };
  if (typeof record.exp !== 'number' || record.exp <= nowMs) {
    return { ok: false, code: AF_PAIR_EXPIRED };
  }
  const presented = normalizePairingCode(presentedCode);
  if (presented.length !== PAIRING_LENGTH) {
    return { ok: false, code: AF_PAIR_WRONG, record: bumpTries(record) };
  }
  const fingerprint = await fingerprintOf(presented);
  // Hash comparison. Both sides are fixed-length hex digests of a 39.5-bit
  // secret with a 15-minute life and a 5-try lock, so a byte-compare timing
  // signal buys an attacker nothing it cannot get from guessing.
  if (fingerprint !== record.fingerprint) {
    return { ok: false, code: AF_PAIR_WRONG, record: bumpTries(record) };
  }
  return { ok: true, record: { ...record, status: 'burned' } };
}

function bumpTries(record) {
  const tries = (typeof record.tries === 'number' ? record.tries : 0) + 1;
  return { ...record, tries, status: tries >= PAIRING_MAX_TRIES ? 'locked' : record.status };
}
