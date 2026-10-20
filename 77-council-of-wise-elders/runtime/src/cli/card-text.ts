/**
 * Provider response text handling for card parsing (RP-046-3 repair
 * for DEFECT-046-B, Cause 2).
 *
 * Harness and chat-style providers do not always return the bare card
 * JSON: the card object may arrive wrapped in prose or a markdown
 * fence. Feeding the whole text to JSON.parse then fails a valid card
 * for a formatting reason ("response is not valid JSON"), while the
 * canonical validator never sees the card at all.
 *
 * This module only LOCATES the card JSON object inside the response
 * text. It never edits field values, never invents a card, and never
 * weakens validation: whatever object is located is handed to the
 * canonical validator unchanged, so a JSON object whose card_kind is
 * outside the closed discriminator enum still fails validation and
 * flows to the one permitted repair, exactly as designed.
 *
 * Behavior for text that is already valid JSON is unchanged: the
 * direct parse result (object or not) is returned untouched, and the
 * validator produces the same issues it always has. Extraction runs
 * only when the direct parse fails.
 */

export type CardTextParse =
  | { ok: true; value: unknown }
  | { ok: false; message: string };

/** Index of the brace matching the opening brace at `start`, or null. */
function matchingBrace(text: string, start: number): number | null {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return null;
}

/**
 * Locate the first balanced-brace JSON object in the text that parses
 * as a JSON object. Brace matching is string and escape aware, so
 * braces inside string values never unbalance the scan; a brace span
 * that does not parse (prose braces, a truncated fragment) is skipped
 * and the scan continues at the next opening brace.
 */
export function extractJsonObject(text: string): Record<string, unknown> | null {
  for (let start = 0; start < text.length; start++) {
    if (text[start] !== '{') continue;
    const end = matchingBrace(text, start);
    if (end === null) continue;
    try {
      const parsed: unknown = JSON.parse(text.slice(start, end + 1));
      if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // Not a JSON object at this span; keep scanning.
    }
  }
  return null;
}

/**
 * Parse a provider response into the candidate card value. Direct
 * JSON keeps its historical semantics; prose-wrapped JSON is located
 * by extraction; anything else reports not-ok, which the engine
 * records with the same "response is not valid JSON" issue it has
 * always used for unparseable output.
 */
export function parseCardResponseText(text: string): CardTextParse {
  let message = 'the reply held no JSON object';
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch (error) {
    // The parser's own message carries the character position.
    if (error instanceof Error) message = error.message;
  }
  const extracted = extractJsonObject(text);
  return extracted !== null ? { ok: true, value: extracted } : { ok: false, message };
}

/**
 * The author payload for one provider reply, plus the parse failure
 * when there is none: an unparseable or non-object reply yields the
 * empty payload (which can never validate) and the reason, so the one
 * bounded repair can say "not valid JSON" instead of a schema error.
 */
export function authorPayloadFromText(text: string): {
  author: Record<string, unknown>;
  parse_error?: string;
} {
  const parsed = parseCardResponseText(text);
  if (!parsed.ok) return { author: {}, parse_error: parsed.message };
  const value = parsed.value;
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return { author: value as Record<string, unknown> };
  }
  return { author: {}, parse_error: 'the reply was JSON but not a single JSON object' };
}
