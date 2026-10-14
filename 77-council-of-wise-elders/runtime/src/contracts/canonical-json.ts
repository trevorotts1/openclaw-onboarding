/**
 * Canonical JSON serializer and strict parser (directive Section 11.6).
 *
 * One documented serializer governs every cross-language hash in the Council
 * of Wise Elders system:
 * - object keys are sorted by UTF-16 code unit order;
 * - array order is preserved exactly as given (semantically significant);
 * - output is UTF-8 encoded with no insignificant whitespace;
 * - NaN and infinity are rejected, never serialized;
 * - duplicate object keys are rejected at parse time;
 * - unknown values are represented as null, never as empty strings;
 * - money is integer minor units with a currency code (see primitives.ts);
 * - only explicitly enumerated self-referential hash/signature fields may be
 *   excluded before hashing (see SELF_REFERENTIAL_FIELDS and hashCanonical).
 *
 * Hashes are computed over exactly these normalized bytes: the bytes accepted
 * and stored, never a UI reserialization.
 */

import { ContractError } from './errors';
import { sha256Hex } from './sha256';

export type CanonicalValue =
  | null
  | boolean
  | number
  | string
  | CanonicalValue[]
  | { [key: string]: CanonicalValue };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return false;
  const proto = Object.getPrototypeOf(value) as unknown;
  return proto === Object.prototype || proto === null;
}

function serializeNumber(value: number, path: string): string {
  if (!Number.isFinite(value)) {
    throw new ContractError(
      'NON_FINITE_NUMBER',
      `Canonical JSON rejects non-finite number at ${path}: ${String(value)}`,
      path,
    );
  }
  if (Object.is(value, -0)) return '0';
  // JSON.stringify gives the shortest round-trip decimal for finite numbers.
  return JSON.stringify(value);
}

function serialize(value: unknown, path: string): string {
  if (value === null || value === undefined) return 'null';
  switch (typeof value) {
    case 'boolean':
      return value ? 'true' : 'false';
    case 'number':
      return serializeNumber(value, path);
    case 'string':
      return JSON.stringify(value);
    case 'object': {
      if (Array.isArray(value)) {
        return `[${value.map((item, i) => serialize(item, `${path}[${i}]`)).join(',')}]`;
      }
      if (isPlainObject(value)) {
        const keys = Object.keys(value).sort();
        const parts = keys.map(
          (key) => `${JSON.stringify(key)}:${serialize(value[key], `${path}.${key}`)}`,
        );
        return `{${parts.join(',')}}`;
      }
      throw new ContractError(
        'UNSUPPORTED_VALUE',
        `Canonical JSON accepts plain objects only at ${path}`,
        path,
      );
    }
    default:
      throw new ContractError(
        'UNSUPPORTED_VALUE',
        `Canonical JSON rejects value of type ${typeof value} at ${path}`,
        path,
      );
  }
}

/**
 * Serialize a value to its canonical JSON text. `undefined` becomes null
 * (unknown), functions/symbols/bigints/class instances are rejected, and
 * non-finite numbers throw NON_FINITE_NUMBER.
 */
export function canonicalStringify(value: unknown): string {
  return serialize(value, '$');
}

const textEncoder = new TextEncoder();

/** The exact normalized UTF-8 bytes for a value. */
export function canonicalBytes(value: unknown): Uint8Array {
  return textEncoder.encode(canonicalStringify(value));
}

/** SHA-256 hex digest over exactly the canonical bytes of a value. */
export function canonicalHash(value: unknown): string {
  return sha256Hex(canonicalBytes(value));
}

/**
 * Field names that are self-referential (a hash or signature of the object
 * that contains them). These, and only these, may be excluded before hashing
 * when a caller explicitly requests exclusion via hashCanonicalExcluding.
 */
export const SELF_REFERENTIAL_FIELDS: ReadonlySet<string> = new Set([
  'content_sha256',
  'semantic_sha256',
  'draft_resolution_sha256',
  'brief_sha256',
  'input_manifest_sha256',
  'preview_sha256',
  'signature',
]);

function stripSelfReferential(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripSelfReferential);
  if (isPlainObject(value)) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value)) {
      if (SELF_REFERENTIAL_FIELDS.has(key)) continue;
      out[key] = stripSelfReferential(value[key]);
    }
    return out;
  }
  return value;
}

/**
 * Hash a value after removing only the enumerated self-referential fields.
 * Used for the record that carries its own hash (for example a draft
 * resolution's semantic hash or a run preview's preview hash).
 */
export function hashCanonicalExcludingSelfReferential(value: unknown): string {
  return canonicalHash(stripSelfReferential(value));
}

/**
 * Strict JSON parser for canonical payloads. Unlike JSON.parse it rejects
 * duplicate object keys, trailing content, and non-JSON number tokens such as
 * NaN or Infinity. Parsed numbers that are not finite are rejected.
 */
export function parseCanonicalJson(text: string): CanonicalValue {
  let pos = 0;
  const len = text.length;

  function fail(message: string): never {
    throw new ContractError('INVALID_JSON', `${message} at offset ${pos}`, '$');
  }

  function skipWhitespace(): void {
    while (pos < len) {
      const ch = text[pos];
      if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') pos++;
      else break;
    }
  }

  function parseValue(): CanonicalValue {
    skipWhitespace();
    if (pos >= len) fail('Unexpected end of input');
    const ch = text[pos];
    if (ch === '{') return parseObject();
    if (ch === '[') return parseArray();
    if (ch === '"') return parseString();
    if (ch === 't') return parseLiteral('true', true);
    if (ch === 'f') return parseLiteral('false', false);
    if (ch === 'n') return parseLiteral('null', null);
    if (ch === '-' || (ch >= '0' && ch <= '9')) return parseNumber();
    return fail(`Unexpected character ${JSON.stringify(ch)}`);
  }

  function parseLiteral<T extends boolean | null>(word: string, value: T): T {
    if (text.slice(pos, pos + word.length) !== word) fail(`Invalid literal, expected ${word}`);
    pos += word.length;
    return value;
  }

  function parseNumber(): number {
    const start = pos;
    if (text[pos] === '-') pos++;
    while (pos < len && /[0-9.eE+-]/.test(text[pos])) pos++;
    const raw = text.slice(start, pos);
    if (!/^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$/.test(raw)) {
      throw new ContractError('INVALID_JSON', `Invalid number token ${JSON.stringify(raw)}`, '$');
    }
    const num = Number(raw);
    if (!Number.isFinite(num)) {
      throw new ContractError('NON_FINITE_NUMBER', `Non-finite number ${raw}`, '$');
    }
    return num;
  }

  function parseString(): string {
    // Delegate escape handling to JSON.parse on the exact token span.
    const start = pos;
    pos++; // opening quote
    let escaped = false;
    while (pos < len) {
      const ch = text[pos];
      if (escaped) {
        escaped = false;
        pos++;
        continue;
      }
      if (ch === '\\') {
        escaped = true;
        pos++;
        continue;
      }
      if (ch === '"') {
        pos++;
        const token = text.slice(start, pos);
        try {
          return JSON.parse(token) as string;
        } catch {
          throw new ContractError('INVALID_JSON', `Invalid string token at offset ${start}`, '$');
        }
      }
      if (ch < ' ') fail('Unescaped control character in string');
      pos++;
    }
    return fail('Unterminated string');
  }

  function parseArray(): CanonicalValue[] {
    pos++; // [
    const out: CanonicalValue[] = [];
    skipWhitespace();
    if (text[pos] === ']') {
      pos++;
      return out;
    }
    for (;;) {
      out.push(parseValue());
      skipWhitespace();
      if (text[pos] === ',') {
        pos++;
        continue;
      }
      if (text[pos] === ']') {
        pos++;
        return out;
      }
      fail('Expected , or ] in array');
    }
  }

  function parseObject(): { [key: string]: CanonicalValue } {
    pos++; // {
    const out: { [key: string]: CanonicalValue } = {};
    skipWhitespace();
    if (text[pos] === '}') {
      pos++;
      return out;
    }
    for (;;) {
      skipWhitespace();
      if (text[pos] !== '"') fail('Expected string key in object');
      const key = parseString();
      if (Object.prototype.hasOwnProperty.call(out, key)) {
        throw new ContractError('DUPLICATE_KEY', `Duplicate object key ${JSON.stringify(key)}`, '$');
      }
      skipWhitespace();
      if (text[pos] !== ':') fail('Expected : in object');
      pos++;
      out[key] = parseValue();
      skipWhitespace();
      if (text[pos] === ',') {
        pos++;
        continue;
      }
      if (text[pos] === '}') {
        pos++;
        return out;
      }
      fail('Expected , or } in object');
    }
  }

  const value = parseValue();
  skipWhitespace();
  if (pos !== len) fail('Trailing content after JSON value');
  return value;
}
