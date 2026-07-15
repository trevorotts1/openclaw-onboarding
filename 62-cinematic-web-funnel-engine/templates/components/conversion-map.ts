/**
 * conversion-map.ts — the single validation boundary between the raw,
 * open-shaped `SiteData.ctaMap` (a pass-through of the locked
 * content-manifest.json's `cta_map`, spec Section 7.3) and every conversion
 * component in this directory (build unit U16, P12-CRM).
 *
 * Fail-closed by construction: `parseConversionMap` never guesses, coerces,
 * or partially trusts a malformed entry. A `ctaMap[id]` that isn't a
 * complete, well-typed `ConversionAction` is DROPPED from the returned
 * `actions` map and recorded in `errors` instead — callers (ConversionSection,
 * resolve-ghl-embeds, ConversionCtaWiring, the /api/conversion-event route)
 * must treat an id missing from `actions` as "not configured" and refuse to
 * act, never as "no requirement" or "skip validation".
 *
 * This module has no side effects and touches no network/env/DOM, so it is
 * safe to import from both server and client components, and from the
 * `/api/conversion-event` route handler (server-side re-validation must
 * never trust a client's own parse of the same map).
 */
import type { ConversionAction, ConversionActionKind, ConversionMap, ConversionMapError } from "./types";

const VALID_KINDS: ConversionActionKind[] = ["ghl-form-embed", "ghl-webhook", "external-link"];

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === "string");
}

/**
 * Validates one raw `ctaMap` entry. Returns either a fully-typed
 * `ConversionAction` or a human-readable rejection reason — never a
 * partially-filled object with an assumed default for a missing field.
 */
export function parseConversionAction(raw: unknown): { action: ConversionAction } | { error: string } {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { error: "entry is not an object" };
  }
  const candidate = raw as Record<string, unknown>;

  if (!isNonEmptyString(candidate.kind) || !VALID_KINDS.includes(candidate.kind as ConversionActionKind)) {
    return { error: `"kind" must be one of ${VALID_KINDS.join(", ")}` };
  }
  const kind = candidate.kind as ConversionActionKind;

  if (!isNonEmptyString(candidate.label)) {
    return { error: '"label" is required and must be a non-empty string' };
  }

  const requiredFields = candidate.requiredFields === undefined ? [] : candidate.requiredFields;
  if (!isStringArray(requiredFields)) {
    return { error: '"requiredFields" must be an array of strings when present' };
  }

  if (kind === "ghl-form-embed") {
    if (!isNonEmptyString(candidate.embedUrlEnvVar)) {
      return { error: 'kind "ghl-form-embed" requires a non-empty "embedUrlEnvVar" (env var NAME, not a URL)' };
    }
    return {
      action: {
        kind,
        label: candidate.label,
        embedUrlEnvVar: candidate.embedUrlEnvVar,
        requiredFields,
      },
    };
  }

  if (kind === "ghl-webhook") {
    if (!isNonEmptyString(candidate.webhookEnvVar)) {
      return { error: 'kind "ghl-webhook" requires a non-empty "webhookEnvVar" (env var NAME, not a URL)' };
    }
    return {
      action: {
        kind,
        label: candidate.label,
        webhookEnvVar: candidate.webhookEnvVar,
        requiredFields,
      },
    };
  }

  // kind === "external-link"
  if (!isNonEmptyString(candidate.href)) {
    return { error: 'kind "external-link" requires a non-empty "href"' };
  }
  return {
    action: {
      kind,
      label: candidate.label,
      href: candidate.href,
      requiredFields,
    },
  };
}

export function parseConversionMap(raw: Record<string, unknown>): {
  actions: ConversionMap;
  errors: ConversionMapError[];
} {
  const actions: ConversionMap = {};
  const errors: ConversionMapError[] = [];

  for (const [ctaId, rawAction] of Object.entries(raw ?? {})) {
    const result = parseConversionAction(rawAction);
    if ("error" in result) {
      errors.push({ ctaId, reason: result.error });
      continue;
    }
    actions[ctaId] = result.action;
  }

  return { actions, errors };
}

/**
 * Server- and client-safe check for "does this CTA id resolve to a usable
 * action with every field a caller is about to submit present and
 * non-empty" — the shared core of both the client-side fast-fail and the
 * server route's independent re-check (spec: "Fail-closed if the conversion
 * wiring is missing required fields").
 */
export function validateSubmission(
  action: ConversionAction | undefined,
  fields: Record<string, unknown>,
): { ok: true } | { ok: false; missing: string[] } {
  if (!action) {
    return { ok: false, missing: ["<action>"] };
  }
  const missing = action.requiredFields.filter((field) => {
    const value = fields[field];
    return typeof value !== "string" || value.trim().length === 0;
  });
  if (missing.length > 0) {
    return { ok: false, missing };
  }
  return { ok: true };
}
