import type { ConversionAction } from "./types";
import { GhlFormEmbedFrame } from "./GhlFormEmbedFrame";
import styles from "./scroll-stage.module.css";

/**
 * GhlFormEmbed.tsx — renders a client's GHL-hosted form/calendar widget
 * inside the direct-hosted Next.js page (spec Section 14.1: "The hosted
 * page may embed GHL forms, calendars, chat widgets... "; this engine never
 * grows its own GHL build client, Skill 6 already provisions the widget
 * this component only embeds it).
 *
 * DELIBERATELY a Server Component (no "use client" directive): resolving
 * `process.env[action.embedUrlEnvVar]` requires a DYNAMIC key lookup, which
 * only works correctly on the server. Next.js's client-bundle inliner only
 * replaces LITERAL `process.env.NEXT_PUBLIC_X` member expressions — a
 * computed/dynamic access in client code would silently evaluate to
 * `undefined` at runtime instead of failing loudly at build/request time,
 * which is exactly the "looks wired but isn't" failure mode the directive's
 * fail-closed requirement rules out. Resolving here means a missing/invalid
 * env var is caught on every request, server-side, before anything renders.
 *
 * Fail-closed: any resolution failure (wrong action kind, unset env var,
 * malformed URL) renders an explicit, visibly-marked unavailable message —
 * never a broken iframe, never a guessed fallback URL.
 */

export interface GhlFormEmbedProps {
  ctaId: string;
  action: ConversionAction;
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

export function GhlFormEmbed({ ctaId, action }: GhlFormEmbedProps) {
  if (action.kind !== "ghl-form-embed" || !action.embedUrlEnvVar) {
    // Operator diagnostic only; no secret value included.
    console.error(`[cwfe-conversion] "${ctaId}" passed to GhlFormEmbed with kind "${action.kind}"`);
    return unavailable(ctaId, action.label);
  }

  const embedUrl = process.env[action.embedUrlEnvVar];
  if (!embedUrl || embedUrl.trim().length === 0) {
    // Logs the env VAR NAME only, never a value (spec Section 20).
    console.error(`[cwfe-conversion] "${ctaId}": env var "${action.embedUrlEnvVar}" is not set`);
    return unavailable(ctaId, action.label);
  }

  let validUrl: string;
  try {
    validUrl = new URL(embedUrl).toString();
  } catch {
    // Logs the env VAR NAME only, never its (malformed) value.
    console.error(`[cwfe-conversion] "${ctaId}": env var "${action.embedUrlEnvVar}" is not a valid URL`);
    return unavailable(ctaId, action.label);
  }

  return (
    <div className={styles.conversionEmbedWrapper} data-cwfe-cta={ctaId}>
      <GhlFormEmbedFrame ctaId={ctaId} src={validUrl} title={action.label} />
    </div>
  );
}
