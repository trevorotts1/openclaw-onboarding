"use client";

import { useCallback, useMemo } from "react";
import type { ConversionDebugState, ConversionTrackedEvent } from "./types";

/**
 * useConversionTracking.ts — first-party conversion/analytics event bus
 * (build unit U16, P12-CRM; spec 13.3 "analytics events; UTM preservation").
 *
 * Deliberately small and dependency-free (ADR-4/ADR-6: no mandatory
 * proprietary runtime): every tracked event is pushed onto
 * `window.dataLayer` using the widely-adopted GTM/GA4 array-push convention
 * so a client's existing tag manager (installed independently of this
 * engine) picks events up with zero extra wiring, AND mirrored onto
 * `window.__cwfeConversionDebug` (mirrors `useScrollScrub`'s
 * `__cwfeScrollDebug` pattern) so Playwright/E2E tests can assert on real
 * tracked events deterministically instead of intercepting network traffic.
 *
 * This module never calls `fetch` and never talks to GHL directly — actual
 * conversion delivery (form embed view -> GHL, webhook CTA -> GHL) is a
 * separate, explicit action taken by `GhlFormEmbedFrame` / `ConversionCtaWiring`
 * through the server-side `/api/conversion-event` route. Tracking is
 * observability; the webhook/embed path is the CRM integration itself.
 */

const DEBUG_EVENT_CAP = 200;
const UTM_STORAGE_KEY = "cwfe_utm";
const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"] as const;

function readUtmFromLocation(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  const found: Record<string, string> = {};
  for (const key of UTM_KEYS) {
    const value = params.get(key);
    if (value) found[key] = value;
  }
  return found;
}

/**
 * First-touch UTM capture: the first set of UTM params seen this session is
 * persisted to `sessionStorage` and reused for every later event, so a CTA
 * click on page 3 of a multi-step funnel still carries the campaign that
 * brought the visitor in (spec 13.3 "UTM preservation"). A later visit with
 * NEW utm params overwrites the stored set deliberately — that is a new
 * attributable session, not a bug.
 */
function resolveUtm(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const fromUrl = readUtmFromLocation();
  try {
    if (Object.keys(fromUrl).length > 0) {
      window.sessionStorage.setItem(UTM_STORAGE_KEY, JSON.stringify(fromUrl));
      return fromUrl;
    }
    const stored = window.sessionStorage.getItem(UTM_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Record<string, unknown>;
      const clean: Record<string, string> = {};
      for (const [k, v] of Object.entries(parsed)) {
        if (typeof v === "string") clean[k] = v;
      }
      return clean;
    }
  } catch {
    // sessionStorage unavailable (privacy mode, disabled storage) — fail
    // soft to no UTM attribution rather than throwing and breaking tracking.
    return fromUrl;
  }
  return {};
}

function pushToDebugState(event: ConversionTrackedEvent): void {
  if (typeof window === "undefined") return;
  const current: ConversionDebugState = window.__cwfeConversionDebug ?? { events: [] };
  const events = [...current.events, event].slice(-DEBUG_EVENT_CAP);
  window.__cwfeConversionDebug = { events };
}

function pushToDataLayer(event: ConversionTrackedEvent): void {
  if (typeof window === "undefined") return;
  window.dataLayer = window.dataLayer ?? [];
  window.dataLayer.push({
    event: event.name,
    cwfeCtaId: event.ctaId,
    ...event.payload,
    utm: event.utm,
  });
}

export interface UseConversionTrackingResult {
  trackEvent: (name: string, payload?: Record<string, unknown>, ctaId?: string) => ConversionTrackedEvent;
}

export function useConversionTracking(): UseConversionTrackingResult {
  const utm = useMemo(() => resolveUtm(), []);

  const trackEvent = useCallback(
    (name: string, payload: Record<string, unknown> = {}, ctaId?: string): ConversionTrackedEvent => {
      const event: ConversionTrackedEvent = {
        name,
        ctaId,
        payload,
        utm,
        timestamp: Date.now(),
      };
      pushToDataLayer(event);
      pushToDebugState(event);
      return event;
    },
    [utm],
  );

  return { trackEvent };
}
