"use client";

import { useEffect, type RefObject } from "react";
import type { ConversionAction, ConversionMap } from "./types";
import { validateSubmission } from "./conversion-map";
import { useConversionTracking } from "./useConversionTracking";
import styles from "./scroll-stage.module.css";

/**
 * ConversionCtaWiring.tsx — attaches GHL webhook behavior to real DOM CTA
 * elements inside the approved copy fragments (build unit U16, P12-CRM).
 *
 * Approved copy (ADR-10: authored by the delegated content methodology —
 * Signature Funnel / Sales-Page-Assets / this engine's own cinematic-native
 * fixtures) marks a CTA button, link, or form with a plain
 * `data-cwfe-cta="<ctaId>"` attribute. This component is the ONLY place
 * that attribute is interpreted at runtime: it never rewrites the copy
 * (still real DOM text, spec 13.3), it only wires behavior onto elements
 * that are already there.
 *
 * Fail-closed contract (directive: "Fail-closed if the conversion wiring is
 * missing required fields"):
 *   - a `data-cwfe-cta` id absent from the resolved `ConversionMap` (i.e.
 *     it failed `parseConversionMap` validation, or content authored an id
 *     the content-manifest never defined) is marked broken in the DOM and
 *     its default action is suppressed — it never silently no-ops as if
 *     nothing were wrong;
 *   - a submission missing one of `action.requiredFields` is rejected
 *     client-side BEFORE any network call, AND independently re-checked by
 *     `/api/conversion-event` server-side (this component never trusts its
 *     own validation to be the only gate);
 *   - `kind: "ghl-form-embed"` entries are never wired here (that kind is
 *     rendered by the dedicated `<GhlFormEmbed>` component, whose embed URL
 *     is resolved server-side in `app/page.tsx`/`lib/resolve-ghl-embeds.ts`)
 *     — a bare element referencing one is treated as a misconfiguration,
 *     not silently ignored.
 */

export interface ConversionCtaWiringProps {
  containerRef: RefObject<HTMLElement | null>;
  actions: ConversionMap;
}

function collectFields(el: HTMLElement): Record<string, string> {
  const form = el instanceof HTMLFormElement ? el : el.closest("form");
  if (form) {
    const data = new FormData(form);
    const fields: Record<string, string> = {};
    for (const [key, value] of data.entries()) {
      if (typeof value === "string" && !(key in fields)) fields[key] = value;
    }
    return fields;
  }
  const fields: Record<string, string> = {};
  for (const [attr, value] of Object.entries(el.dataset)) {
    const match = /^cwfeField([A-Z].*)$/.exec(attr);
    if (match && typeof value === "string") {
      const fieldName = match[1].charAt(0).toLowerCase() + match[1].slice(1);
      fields[fieldName] = value;
    }
  }
  return fields;
}

function showInlineMessage(el: HTMLElement, kind: "error" | "success", text: string): void {
  const existing = el.parentElement?.querySelector<HTMLElement>(
    `[data-cwfe-message-for="${el.dataset.cwfeCta ?? ""}"]`,
  );
  if (existing) existing.remove();

  const message = document.createElement("p");
  message.setAttribute("role", kind === "error" ? "alert" : "status");
  message.dataset.cwfeMessageFor = el.dataset.cwfeCta ?? "";
  message.className = kind === "error" ? styles.conversionErrorMessage : styles.conversionSuccessMessage;
  message.textContent = text;
  el.insertAdjacentElement("afterend", message);
}

function markMisconfigured(el: HTMLElement, ctaId: string, reason: string): void {
  el.dataset.cwfeConversionError = "true";
  el.setAttribute("aria-disabled", "true");
  // Operator-visible diagnostic only; no secret value is ever included.
  console.error(`[cwfe-conversion] "${ctaId}" is not wired: ${reason}`);
  const block = (event: Event) => {
    event.preventDefault();
    showInlineMessage(el, "error", "This action is not available right now.");
  };
  el.addEventListener("click", block);
  if (el instanceof HTMLFormElement) el.addEventListener("submit", block);
  el.dataset.cwfeWired = "true";
}

async function submitConversionEvent(
  ctaId: string,
  action: ConversionAction,
  fields: Record<string, string>,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetch("/api/conversion-event", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ctaId, kind: action.kind, fields }),
    });
    const body = (await response.json().catch(() => ({}))) as { ok?: boolean; error?: string };
    if (!response.ok || body.ok !== true) {
      return { ok: false, error: body.error ?? `request failed (${response.status})` };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "network error" };
  }
}

export function ConversionCtaWiring({ containerRef, actions }: ConversionCtaWiringProps) {
  const { trackEvent } = useConversionTracking();

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return undefined;

    const controller = new AbortController();
    const { signal } = controller;

    const elements = Array.from(root.querySelectorAll<HTMLElement>("[data-cwfe-cta]"));

    for (const el of elements) {
      if (el.dataset.cwfeWired === "true") continue;
      const ctaId = el.dataset.cwfeCta;
      if (!ctaId) continue;

      const action = actions[ctaId];

      if (!action) {
        markMisconfigured(el, ctaId, `no conversion action configured for "${ctaId}"`);
        continue;
      }

      if (action.kind === "external-link") {
        el.addEventListener(
          "click",
          () => {
            trackEvent("cta_click", { kind: action.kind, label: action.label }, ctaId);
          },
          { signal },
        );
        el.dataset.cwfeWired = "true";
        continue;
      }

      if (action.kind === "ghl-form-embed") {
        markMisconfigured(
          el,
          ctaId,
          `kind "ghl-form-embed" must be rendered via <GhlFormEmbed>, not a bare data-cwfe-cta element`,
        );
        continue;
      }

      // kind === "ghl-webhook"
      const handleSubmitLike = async (event: Event) => {
        event.preventDefault();
        const fields = collectFields(el);
        const validation = validateSubmission(action, fields);
        if (!validation.ok) {
          trackEvent("cta_submit_error", { reason: "missing_fields", missing: validation.missing }, ctaId);
          showInlineMessage(el, "error", "Please fill in all required fields.");
          return;
        }
        trackEvent("cta_click", { kind: action.kind, label: action.label }, ctaId);
        const result = await submitConversionEvent(ctaId, action, fields);
        if (result.ok) {
          trackEvent("cta_submit_success", { kind: action.kind }, ctaId);
          showInlineMessage(el, "success", "Thank you — we received your submission.");
        } else {
          trackEvent("cta_submit_error", { reason: result.error }, ctaId);
          showInlineMessage(el, "error", "Something went wrong. Please try again.");
        }
      };

      if (el instanceof HTMLFormElement) {
        el.addEventListener("submit", handleSubmitLike, { signal });
      } else {
        el.addEventListener("click", handleSubmitLike, { signal });
      }
      el.dataset.cwfeWired = "true";
    }

    return () => controller.abort();
  }, [containerRef, actions, trackEvent]);

  return null;
}
