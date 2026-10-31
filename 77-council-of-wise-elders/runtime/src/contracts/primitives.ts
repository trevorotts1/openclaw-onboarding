/**
 * ID, time, and money primitives for the canonical contracts (CWE-003).
 *
 * Rules from directive Sections 11.1 and 11.6:
 * - IDs are opaque: they must not contain client names, decision text, or
 *   secrets, so only a conservative character set is accepted.
 * - Timestamps are UTC ISO 8601; a display timezone is stored separately.
 * - Money is integer minor units plus an ISO 4217 currency code; fractional
 *   major-unit floats are never a money representation.
 * - Unknown is null, never an empty string masquerading as a fact.
 *
 * Clock and ID generation are host concerns. The core never reads a clock or
 * a random source: hosts inject values through the Clock and IdSource seams
 * below, and the core only validates what it is given.
 */

import { ContractError } from './errors.js';

/** Opaque identifier: letters, digits, hyphen, underscore, dot, colon. */
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;
export const MAX_ID_LENGTH = 128;

export function isValidId(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length >= 1 &&
    value.length <= MAX_ID_LENGTH &&
    ID_PATTERN.test(value) &&
    !value.includes(' ')
  );
}

export function assertValidId(value: unknown, field: string): string {
  if (!isValidId(value)) {
    throw new ContractError(
      'INVALID_ID',
      `Invalid opaque ID for ${field}: must be 1-${MAX_ID_LENGTH} chars of [A-Za-z0-9._:-], starting alphanumeric`,
      field,
    );
  }
  return value;
}

/** SHA-256 hex digest: exactly 64 lowercase hex characters. */
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export function isSha256Hex(value: unknown): value is string {
  return typeof value === 'string' && SHA256_PATTERN.test(value);
}

export function assertSha256Hex(value: unknown, field: string): string {
  if (!isSha256Hex(value)) {
    throw new ContractError('INVALID_HASH', `Expected SHA-256 hex digest for ${field}`, field);
  }
  return value;
}

/** UTC ISO 8601 timestamp, for example 2026-10-14T02:00:00Z (fraction allowed). */
const UTC_TIMESTAMP_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$/;

export function isUtcTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || !UTC_TIMESTAMP_PATTERN.test(value)) return false;
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return false;
  // Round-trip check rejects impossible dates such as 2026-02-31.
  const d = new Date(ms);
  return d.toISOString().startsWith(value.slice(0, 19));
}

export function assertUtcTimestamp(value: unknown, field: string): string {
  if (!isUtcTimestamp(value)) {
    throw new ContractError(
      'INVALID_TIMESTAMP',
      `Expected UTC ISO 8601 timestamp for ${field}`,
      field,
    );
  }
  return value;
}

/** Money in integer minor units with an ISO 4217 alphabetic currency code. */
export interface Money {
  amount_minor: number;
  currency: string;
}

const CURRENCY_PATTERN = /^[A-Z]{3}$/;

export function isMoney(value: unknown): value is Money {
  if (typeof value !== 'object' || value === null) return false;
  const m = value as Record<string, unknown>;
  return (
    typeof m.amount_minor === 'number' &&
    Number.isSafeInteger(m.amount_minor) &&
    typeof m.currency === 'string' &&
    CURRENCY_PATTERN.test(m.currency)
  );
}

export function money(amountMinor: number, currency: string): Money {
  const candidate = { amount_minor: amountMinor, currency };
  if (!isMoney(candidate)) {
    throw new ContractError(
      'INVALID_MONEY',
      'Money requires a safe-integer amount_minor and a 3-letter uppercase currency code',
      'money',
    );
  }
  return candidate;
}

/**
 * Injection seams. The core defines these interfaces only; hosts supply the
 * implementations. Nothing in the core calls Date.now, Math.random, or any
 * host clock/ID source directly.
 */
export interface Clock {
  /** Current time as a UTC ISO 8601 timestamp string. */
  nowUtc(): string;
}

export interface IdSource {
  /** A fresh opaque ID. Implementations must satisfy isValidId. */
  newId(): string;
}
