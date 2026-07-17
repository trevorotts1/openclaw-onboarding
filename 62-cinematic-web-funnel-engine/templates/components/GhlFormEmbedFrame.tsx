"use client";

import { useEffect, useRef, useState } from "react";
import { useConversionTracking } from "./useConversionTracking";
import styles from "./scroll-stage.module.css";

/**
 * GhlFormEmbedFrame.tsx — the interactive half of the "ghl-form-embed"
 * conversion kind (build unit U16, P12-CRM). The actual embed URL is
 * resolved from an env var by name in `lib/resolve-ghl-embeds.ts`, called
 * only from the Server Component `app/page.tsx` and threaded down through
 * `GhlFormEmbed.tsx`; this component only ever receives the final,
 * already-resolved, non-secret URL string as a prop — it never touches
 * `process.env` itself.
 *
 * Auto-resize listens for a `postMessage({height})` from the embedded GHL
 * widget (the common pattern GHL/LeadConnector hosted forms use) and
 * validates `event.origin` against the embed URL's own origin before
 * trusting the payload (spec Section 20: "validate iframe origins").
 */

export interface GhlFormEmbedFrameProps {
  ctaId: string;
  src: string;
  title: string;
}

const DEFAULT_HEIGHT_PX = 480;
const MAX_HEIGHT_PX = 4000;

export function GhlFormEmbedFrame({ ctaId, src, title }: GhlFormEmbedFrameProps) {
  const { trackEvent } = useConversionTracking();
  const [height, setHeight] = useState(DEFAULT_HEIGHT_PX);
  const originRef = useRef<string | null>(null);

  useEffect(() => {
    try {
      originRef.current = new URL(src).origin;
    } catch {
      originRef.current = null;
    }
    trackEvent("form_embed_view", { origin: originRef.current ?? "invalid-origin" }, ctaId);
    // Intentionally runs once per mount/src change only — trackEvent is
    // stable across renders (useConversionTracking memoizes it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, ctaId]);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (!originRef.current || event.origin !== originRef.current) return;
      const data: unknown = event.data;
      const reportedHeight =
        typeof data === "object" && data !== null && "height" in data
          ? Number((data as { height: unknown }).height)
          : NaN;
      if (Number.isFinite(reportedHeight) && reportedHeight > 0) {
        setHeight(Math.min(Math.max(reportedHeight, 1), MAX_HEIGHT_PX));
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  return (
    <iframe
      src={src}
      title={title}
      data-cwfe-form-embed={ctaId}
      className={styles.conversionEmbedFrame}
      style={{ height }}
      loading="lazy"
    />
  );
}
