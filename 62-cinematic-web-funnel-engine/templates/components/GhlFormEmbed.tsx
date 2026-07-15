import type { GhlEmbedResolution } from "./types";
import { GhlFormEmbedFrame } from "./GhlFormEmbedFrame";
import styles from "./scroll-stage.module.css";

/**
 * GhlFormEmbed.tsx — renders a client's GHL-hosted form/calendar widget
 * inside the direct-hosted Next.js page (spec Section 14.1: "The hosted
 * page may embed GHL forms, calendars, chat widgets... "; this engine never
 * grows its own GHL build client, Skill 6 already provisions the widget
 * this component only embeds it).
 *
 * Purely presentational (build unit U16 QC fix): this component NEVER reads
 * `process.env` itself. It used to, guarded only by having no `"use client"`
 * directive of its own — but under React Server Component rules a
 * component's actual render boundary is decided by its nearest ancestor's
 * `"use client"`, not its own file, and every caller on the path from here
 * to the page (`ConversionSection.tsx`, `ScrollScrubEngine.tsx`) is a
 * Client Component. That silently pulled the dynamic
 * `process.env[action.embedUrlEnvVar]` lookup into the browser bundle,
 * where it always resolves to `undefined`.
 *
 * The real env-var resolution now happens in `lib/resolve-ghl-embeds.ts`,
 * called only from the Server Component `app/page.tsx`, and is threaded
 * down through props as an already-resolved `GhlEmbedResolution` — this
 * component only ever sees the final URL (or an explicit failure), never a
 * secret name or a guessed fallback.
 *
 * Fail-closed: any resolution failure (wrong action kind, unset env var,
 * malformed URL) renders an explicit, visibly-marked unavailable message —
 * never a broken iframe, never a guessed fallback URL. A missing
 * `resolution` prop (a ctaId the caller never resolved) fails closed the
 * same way as an explicit `{ ok: false }`.
 */

export interface GhlFormEmbedProps {
  ctaId: string;
  resolution: GhlEmbedResolution | undefined;
}

function unavailable(ctaId: string, label: string) {
  return (
    <p
      className={styles.conversionErrorMessage}
      data-cwfe-conversion-error="true"
      data-cwfe-cta={ctaId}
    >
      {label} is temporarily unavailable.
    </p>
  );
}

export function GhlFormEmbed({ ctaId, resolution }: GhlFormEmbedProps) {
  if (!resolution) {
    // Operator diagnostic only; no secret value included.
    console.error(`[cwfe-conversion] "${ctaId}": no resolved GHL embed for this cta id`);
    return unavailable(ctaId, ctaId);
  }

  if (!resolution.ok) {
    return unavailable(ctaId, resolution.label);
  }

  return (
    <div className={styles.conversionEmbedWrapper} data-cwfe-cta={ctaId}>
      <GhlFormEmbedFrame ctaId={ctaId} src={resolution.url} title={resolution.label} />
    </div>
  );
}
