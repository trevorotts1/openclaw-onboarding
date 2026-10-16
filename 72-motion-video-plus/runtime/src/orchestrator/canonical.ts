// Canonical JSON and hashing for the orchestrator gate (MG-025,
// Directive Sections 16.7 and 16.9).
//
// Section 16.7 requires revision digests over canonical UTF-8 JSON with
// sorted keys and a defined numeric serialization, identical in the
// TypeScript and Python evaluators. The rules here are that shared
// definition:
//
// - Object keys sort by UTF-16 code unit (the same order Python's
//   json.dumps(sort_keys=True) produces for the ASCII identifiers and
//   hex digests these payloads carry).
// - No whitespace: separators are "," and ":" exactly.
// - Strings are emitted unescaped except where JSON requires escaping
//   (the Python mirror uses ensure_ascii=False).
// - Integers serialize without a decimal point. Non-integer numbers
//   serialize as the shortest decimal that round-trips, expanded out
//   of exponent notation. Hashed gate payloads avoid non-integer
//   numbers by construction (paths, hex digests, integer weights and
//   sample positions only); the rule exists so a stray value hashes
//   identically in both evaluators instead of silently diverging.
// - Non-finite numbers are refused outright: they have no canonical
//   form and must never enter a digest.

import { createHash } from "node:crypto";

/** Expand a shortest round-trip decimal string out of exponent form. */
function expandExponent(text: string): string {
  if (!/[eE]/.test(text)) return text;
  const [mantissa, expText] = text.split(/[eE]/);
  const exponent = Number.parseInt(expText, 10);
  const negative = mantissa.startsWith("-");
  const unsigned = negative ? mantissa.slice(1) : mantissa;
  const dot = unsigned.indexOf(".");
  const intPart = dot === -1 ? unsigned : unsigned.slice(0, dot);
  const fracPart = dot === -1 ? "" : unsigned.slice(dot + 1);
  const digits = intPart + fracPart;
  const point = intPart.length + exponent;
  let out: string;
  if (point <= 0) {
    out = "0." + "0".repeat(-point) + digits;
  } else if (point >= digits.length) {
    out = digits + "0".repeat(point - digits.length);
  } else {
    out = digits.slice(0, point) + "." + digits.slice(point);
  }
  if (out.includes(".")) {
    out = out.replace(/0+$/, "").replace(/\.$/, "");
  }
  return (negative ? "-" : "") + out;
}

/** Canonical serialization of one JSON number. */
export function canonicalNumber(value: number): string {
  if (!Number.isFinite(value)) {
    throw new Error(`canonical JSON cannot carry a non-finite number: ${value}`);
  }
  if (Number.isInteger(value) && Math.abs(value) <= Number.MAX_SAFE_INTEGER) {
    return String(value);
  }
  return expandExponent(String(value));
}

/** Serialize a JSON value canonically: sorted keys, no whitespace,
 * defined numeric serialization. Mirrors check_approvals.py exactly. */
export function canonicalJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return canonicalNumber(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map((entry) => canonicalJson(entry)).join(",") + "]";
  }
  if (typeof value === "object") {
    const doc = value as Record<string, unknown>;
    const keys = Object.keys(doc).sort();
    return (
      "{" +
      keys.map((key) => JSON.stringify(key) + ":" + canonicalJson(doc[key])).join(",") +
      "}"
    );
  }
  throw new Error(`canonical JSON cannot carry a value of type ${typeof value}`);
}

/** sha256 hex of a UTF-8 string. */
export function sha256Hex(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

/** sha256 hex of raw bytes. */
export function sha256Bytes(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}
