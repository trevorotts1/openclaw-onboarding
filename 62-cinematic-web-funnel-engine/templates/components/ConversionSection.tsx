"use client";

import { useMemo, useRef } from "react";
import type { CopySection, GhlEmbedResolution } from "./types";
import { parseConversionMap } from "./conversion-map";
import { ConversionCtaWiring } from "./ConversionCtaWiring";
import { GhlFormEmbed } from "./GhlFormEmbed";
import styles from "./scroll-stage.module.css";

export interface ConversionSectionsProps {
  sections: CopySection[];
  /** Raw `SiteData.ctaMap` — parsed once here via `parseConversionMap`
   * (build unit U16, P12-CRM) so every conversion component downstream
   * shares one validated, fail-closed source of truth. */
  ctaMap: Record<string, unknown>;
  /** Every `kind: "ghl-form-embed"` action's env var already resolved to a
   * URL (or an explicit failure), computed server-side in
   * `lib/resolve-ghl-embeds.ts` and passed down from the Server Component
   * `app/page.tsx` (build unit U16 QC fix — see `GhlFormEmbed.tsx` for why
   * this can't be resolved inside this, or any, Client Component). */
  resolvedEmbeds: Record<string, GhlEmbedResolution>;
}

/**
 * Renders the locked content-manifest's approved copy sections as real DOM
 * text (spec 13.3: "headlines and body copy as real DOM text"; "no critical
 * conversion action may depend solely on animation"). These fragments are
 * resolved at generation time by scripts/build_site.py from a locked
 * content-manifest.json's `approved_copy_paths` — filesystem paths into a
 * delegate skill's own sacred-copy artifacts (ADR-10) or this engine's own
 * fixture fragments, never text this component (or an LLM at request time)
 * authors. That is what makes `dangerouslySetInnerHTML` here safe and
 * correct rather than an XSS smell: the HTML is a build-time, locally
 * resolved, already-approved artifact — not runtime user input.
 *
 * This block renders AFTER the cinematic scroll stage in both the normal
 * and the `prefers-reduced-motion` layouts (ScrollScrubEngine), so every
 * CTA, form, and offer stays reachable and complete even with zero motion.
 *
 * Defense-in-depth: scripts/build_site.py additionally strips
 * `<script>`/`<style>` tags, `on*=` event-handler attributes, and
 * `javascript:`-scheme URLs out of every fragment BEFORE it is written into
 * `lib/site-data.generated.ts` (see `sanitize_copy_fragment()`), so this
 * component never receives markup it hasn't already had adversarial content
 * removed from, even though the source fragments are locked/approved and
 * not runtime user input.
 *
 * Conversion layer (build unit U16, P12-CRM): `ctaMap` is validated once via
 * `parseConversionMap` (fail-closed — a malformed entry never becomes a
 * silently-working default). `ConversionCtaWiring` attaches GHL-webhook
 * behavior to any `data-cwfe-cta` element already present inside the copy
 * fragments above; any resolved `"ghl-form-embed"` action additionally gets
 * its own real GHL-hosted widget rendered below the copy via `GhlFormEmbed`
 * — reachable, complete, and animation-independent either way.
 *
 * `resolvedEmbeds` is NOT computed in this component (this file is
 * `"use client"`, so it and everything it renders — including
 * `GhlFormEmbed` — are Client Components under RSC rules; a dynamic
 * `process.env[...]` lookup anywhere in this tree would silently resolve to
 * `undefined` in the browser). It is resolved once, server-side, in
 * `app/page.tsx` via `lib/resolve-ghl-embeds.ts`, and simply passed through
 * here as already-safe, already-resolved data.
 */
export function ConversionSections({ sections, ctaMap, resolvedEmbeds }: ConversionSectionsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { actions, errors } = useMemo(() => parseConversionMap(ctaMap), [ctaMap]);
  const embeddedActions = useMemo(
    () => Object.entries(actions).filter(([, action]) => action.kind === "ghl-form-embed"),
    [actions],
  );

  return (
    <div ref={containerRef} className={styles.conversionStack} data-cwfe-conversion-sections="true">
      {sections.map((section) => (
        <section
          key={section.id}
          id={section.id}
          className={styles.conversionSection}
          dangerouslySetInnerHTML={{ __html: section.html }}
        />
      ))}

      {embeddedActions.length > 0 && (
        <div className={styles.conversionEmbeds} data-cwfe-conversion-embeds="true">
          {embeddedActions.map(([ctaId]) => (
            <GhlFormEmbed key={ctaId} ctaId={ctaId} resolution={resolvedEmbeds[ctaId]} />
          ))}
        </div>
      )}

      {errors.length > 0 &&
        errors.map((error) => (
          <p
            key={error.ctaId}
            className={styles.conversionErrorMessage}
            data-cwfe-conversion-map-error={error.ctaId}
            hidden
          >
            {error.ctaId}: {error.reason}
          </p>
        ))}

      <ConversionCtaWiring containerRef={containerRef} actions={actions} />
    </div>
  );
}
