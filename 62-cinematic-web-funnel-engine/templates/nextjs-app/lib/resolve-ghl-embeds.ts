/**
 * resolve-ghl-embeds.ts — the server side of the "ghl-form-embed" conversion
 * kind (build unit U16, P12-CRM QC fix). Mirrors `lib/conversion-webhook.ts`:
 * this module is never imported from a `"use client"` component, only from
 * `app/page.tsx` (a genuine Server Component with no `"use client"` in its
 * own file or any ancestor), so a dynamic `process.env[name]` lookup here is
 * guaranteed to run server-side on every request.
 *
 * QC fix (U16): `GhlFormEmbed.tsx` used to resolve `process.env[...]`
 * itself, justified by having no `"use client"` directive of its own. That
 * reasoning doesn't hold under React Server Component rules — a component's
 * *nearest client boundary* decides where it actually renders, and every
 * caller between `GhlFormEmbed` and the page (`ConversionSection.tsx`,
 * `ScrollScrubEngine.tsx`) declares `"use client"`. That pulled
 * `GhlFormEmbed` into the client bundle, where the dynamic env lookup
 * silently evaluates to `undefined` instead of failing loudly server-side.
 * Resolving here, in a module only `app/page.tsx` ever imports, and passing
 * the result down as a plain `GhlEmbedResolution` prop closes that gap: the
 * *value* crossing the Server → Client Component boundary is fine (it's
 * already-resolved, non-secret data by the time it's serialized into the
 * client tree) — it's the *code that reads `process.env`* that must never
 * execute client-side, and now it never does.
 *
 * Fail-closed (spec Section 20 "record secret presence by name only"): logs
 * the env var NAME only, never a value, on every rejection path.
 */
import { parseConversionMap } from "@/components/conversion-map";
import type { GhlEmbedResolution } from "@/components/types";

export function resolveGhlFormEmbeds(ctaMap: Record<string, unknown>): Record<string, GhlEmbedResolution> {
  const { actions } = parseConversionMap(ctaMap);
  const resolved: Record<string, GhlEmbedResolution> = {};

  for (const [ctaId, action] of Object.entries(actions)) {
    if (action.kind !== "ghl-form-embed" || !action.embedUrlEnvVar) continue;

    const rawValue = process.env[action.embedUrlEnvVar];
    if (!rawValue || rawValue.trim().length === 0) {
      // Logs the env VAR NAME only, never a value (spec Section 20).
      console.error(`[cwfe-conversion] "${ctaId}": env var "${action.embedUrlEnvVar}" is not set`);
      resolved[ctaId] = { ok: false, label: action.label };
      continue;
    }

    try {
      resolved[ctaId] = { ok: true, label: action.label, url: new URL(rawValue).toString() };
    } catch {
      // Logs the env VAR NAME only, never its (malformed) value.
      console.error(`[cwfe-conversion] "${ctaId}": env var "${action.embedUrlEnvVar}" is not a valid URL`);
      resolved[ctaId] = { ok: false, label: action.label };
    }
  }

  return resolved;
}
