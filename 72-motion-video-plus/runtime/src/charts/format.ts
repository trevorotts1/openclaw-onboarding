// Display formatting under a dataset's declared rounding rule
// (Directive MG-015; Section 17.1 M05: displayed rounding matches the
// declared rule).
//
// The rule is: round half away from zero at the declared number of
// fractional decimals, then print exactly that many decimals. The
// rounding is performed on the value's decimal string representation,
// digit by digit, so the result is the mathematically correct rounding
// of the decimal the author wrote, never a binary floating-point
// artifact (the classic 1.005 case rounds to 1.01 at two decimals,
// not 1.00). No thousands separators: the dataset contract declares
// decimals only, and inventing further display rules here would make
// displayed values diverge from the declared rule.

import type { ChartDataset, DisplayRounding } from "./dataset";

interface DecimalParts {
  negative: boolean;
  /** Integer and fraction digits with no decimal point, no exponent. */
  digits: string;
  /** Number of digits after the decimal point within `digits`. */
  fractionDigits: number;
}

/** Expand a finite number to plain decimal parts via its shortest
 * round-trip string form, resolving any exponent notation. */
function toDecimalParts(value: number): DecimalParts {
  let text = String(value);
  let negative = false;
  if (text.startsWith("-")) {
    negative = true;
    text = text.slice(1);
  }
  let exponent = 0;
  const eAt = text.indexOf("e");
  if (eAt >= 0) {
    exponent = Number(text.slice(eAt + 1));
    text = text.slice(0, eAt);
  }
  const dotAt = text.indexOf(".");
  const intDigits = dotAt >= 0 ? text.slice(0, dotAt) : text;
  const fracDigits = dotAt >= 0 ? text.slice(dotAt + 1) : "";
  let digits = intDigits + fracDigits;
  let fractionDigits = fracDigits.length - exponent;
  if (fractionDigits < 0) {
    digits = digits + "0".repeat(-fractionDigits);
    fractionDigits = 0;
  }
  // Strip leading zeros (keeping at least one digit) for stable carry
  // handling; leading zeros do not change the value or its fractions.
  digits = digits.replace(/^0+(?=\d)/, "");
  return { negative, digits, fractionDigits };
}

/** Add one to a string of decimal digits, propagating carry. */
function incrementDigits(digits: string): string {
  const chars = digits.split("");
  let i = chars.length - 1;
  while (i >= 0 && chars[i] === "9") {
    chars[i] = "0";
    i -= 1;
  }
  if (i < 0) return "1" + chars.join("");
  chars[i] = String(Number(chars[i]) + 1);
  return chars.join("");
}

/**
 * Format a finite value under the declared rounding rule: round half
 * away from zero at `decimals` fractional digits and print exactly
 * that many decimals. A result of zero never carries a sign.
 */
export function formatValue(value: number, rounding: DisplayRounding): string {
  if (!Number.isFinite(value)) {
    throw new Error(`cannot format a non-finite value: ${value}`);
  }
  const decimals = rounding.decimals;
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 10) {
    throw new Error(`rounding decimals must be an integer in [0, 10], got ${decimals}`);
  }
  const parts = toDecimalParts(value);
  // Left-pad so the digit string always carries at least one integer
  // digit: every index below then names a real digit (positions the
  // value does not reach are zeros).
  let digits = parts.digits.padStart(parts.fractionDigits + 1, "0");
  const have = parts.fractionDigits;

  if (have > decimals) {
    const drop = have - decimals;
    const kept = digits.slice(0, digits.length - drop) || "0";
    const firstDropped = digits[digits.length - drop];
    digits = firstDropped >= "5" ? incrementDigits(kept) : kept;
  } else if (have < decimals) {
    digits = digits + "0".repeat(decimals - have);
  }

  // digits now holds exactly `decimals` fractional digits.
  let intPart: string;
  let fracPart = "";
  if (decimals === 0) {
    intPart = digits;
  } else {
    const padded = digits.padStart(decimals + 1, "0");
    intPart = padded.slice(0, padded.length - decimals);
    fracPart = padded.slice(padded.length - decimals);
  }
  intPart = intPart.replace(/^0+(?=\d)/, "");
  const isZero = /^0*$/.test(intPart) && /^0*$/.test(fracPart);
  const sign = parts.negative && !isZero ? "-" : "";
  return decimals === 0 ? sign + intPart : `${sign}${intPart}.${fracPart}`;
}

/** Format a value using its own dataset's declared rounding rule. */
export function formatDatasetValue(dataset: ChartDataset, value: number): string {
  return formatValue(value, dataset.display_rounding);
}
