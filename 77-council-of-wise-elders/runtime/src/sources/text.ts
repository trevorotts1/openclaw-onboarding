/**
 * Documented text normalization for quotation verification (Section 8.4).
 *
 * "Normalize only documented typographic differences." The complete list
 * of permitted normalizations is:
 * - Unicode NFKC compatibility folding;
 * - curly single/double quotation marks to straight ASCII quotes;
 * - em dash and en dash to a hyphen;
 * - the horizontal ellipsis character to three periods;
 * - any run of whitespace (including newlines) to one space, trimmed.
 *
 * Letter case is NOT folded: a quotation must match the source's words,
 * including capitalization. No words are removed or reordered.
 */
export function normalizeQuotedText(text: string): string {
  return text
    .normalize('NFKC')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2014\u2013]/g, '-')
    .replace(/\u2026/g, '...')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Speaker-name comparison key. Names are compared case-insensitively,
 * without punctuation, and without an honorific prefix ("Dr."), so
 * "Dr. Dennis Kimbro" and "Dennis Kimbro" name the same speaker while a
 * different person never matches.
 */
export function normalizeSpeakerName(name: string): string {
  return name
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[.,'\u2019]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^dr /, '');
}

export function sameSpeaker(a: string, b: string): boolean {
  return normalizeSpeakerName(a) === normalizeSpeakerName(b);
}

/** Title comparison key for work matching (coverage gate). */
export function normalizeTitle(title: string): string {
  return title
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[.,'\u2019:!?"\u201c\u201d\u2018]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * A tuple locator is a plain string (the CWE-003 VerifiedQuoteCandidate
 * carries `locator: string`). It matches an evidence locator when it
 * equals the locator value ("41") or the kind-qualified form
 * ("page:41"). Anything else is a mismatch, never a fuzzy pass.
 */
export function locatorMatches(
  tupleLocator: string,
  locator: { kind: string; value: string },
): boolean {
  return tupleLocator === locator.value ||
    tupleLocator === `${locator.kind}:${locator.value}`;
}
