"use client";

import { useEffect } from "react";
import type { ScrollDebugState, EmbedConfig } from "./types";

export interface EmbedBridgeProps {
  debugState: ScrollDebugState;
  embed: EmbedConfig;
}

const CWFE_MESSAGE_NAMESPACE = "cwfe";

interface CwfeResizeMessage {
  namespace: typeof CWFE_MESSAGE_NAMESPACE;
  type: "resize";
  height: number;
}

interface CwfeProgressMessage {
  namespace: typeof CWFE_MESSAGE_NAMESPACE;
  type: "scroll-progress";
  overallProgress: number;
  activeSceneId: string | null;
}

interface CwfeConversionMessage {
  namespace: typeof CWFE_MESSAGE_NAMESPACE;
  type: "conversion-event";
  eventName: string;
  detail?: Record<string, unknown>;
}

type CwfeOutboundMessage = CwfeResizeMessage | CwfeProgressMessage | CwfeConversionMessage;

/**
 * EmbedBridge — the iframe parent-messaging half of spec 13.2's "provide
 * iframe parent messaging in embed mode" requirement (the full embed HTML
 * package, allowed-origin allowlist file, and parent-side script live in a
 * later unit, U18, per spec 14.2; this component is the child-side runtime
 * piece that ships with every generated site regardless of which unit wires
 * the parent page).
 *
 * Only active when the page is actually running inside an iframe
 * (`window.parent !== window`). In direct-hosted mode this component is a
 * no-op — it never creates its own scroll container or intercepts anything,
 * so it cannot introduce a nested-scroll trap (spec 13.2).
 *
 * Every outbound postMessage is scoped under a `cwfe` namespace and sent
 * with an explicit `targetOrigin` — `embed.allowedAncestors[0]` when the
 * project's manifest names an allowlisted parent origin, or `"*"` only when
 * no allowlist was configured (matches an un-iframed preview/dev use, never
 * silently widened once an allowlist exists).
 */
export function EmbedBridge({ debugState, embed }: EmbedBridgeProps) {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const isEmbedded = window.parent !== window;
    if (!isEmbedded) return;

    const targetOrigin = embed.allowedAncestors[0] ?? "*";

    const post = (message: CwfeOutboundMessage) => {
      window.parent.postMessage(message, targetOrigin);
    };

    const postHeight = () => {
      const height = document.documentElement.scrollHeight;
      post({ namespace: CWFE_MESSAGE_NAMESPACE, type: "resize", height });
    };

    postHeight();
    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(postHeight) : null;
    resizeObserver?.observe(document.documentElement);
    window.addEventListener("resize", postHeight, { passive: true });

    // Defense: only ever act on an inbound message from an allowlisted
    // ancestor origin (spec 20 "validate iframe origins"). With no
    // allowlist configured, inbound messages are ignored entirely rather
    // than defaulting to "trust everything".
    const onMessage = (event: MessageEvent) => {
      if (embed.allowedAncestors.length === 0) return;
      if (!embed.allowedAncestors.includes(event.origin)) return;
      const data = event.data as { namespace?: string; type?: string } | undefined;
      if (!data || data.namespace !== CWFE_MESSAGE_NAMESPACE) return;
      // Reserved for future parent -> child commands (e.g. scrollTo). No
      // commands are implemented yet in this unit; unknown types are
      // ignored rather than acted on.
    };
    window.addEventListener("message", onMessage);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", postHeight);
      window.removeEventListener("message", onMessage);
    };
  }, [embed]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.parent === window) return;
    const targetOrigin = embed.allowedAncestors[0] ?? "*";
    window.parent.postMessage(
      {
        namespace: CWFE_MESSAGE_NAMESPACE,
        type: "scroll-progress",
        overallProgress: debugState.overallProgress,
        activeSceneId: debugState.activeSceneId,
      } satisfies CwfeProgressMessage,
      targetOrigin,
    );
  }, [debugState.overallProgress, debugState.activeSceneId, embed]);

  return null;
}

/** Called by ConversionSection CTA handlers (wired in a later unit) to
 * forward a conversion event to the embedding parent, e.g. for GHL/CRM
 * analytics stitching (spec 13.3 "analytics events"). Exported so it can be
 * unit-tested and reused outside this component's own effect scope. */
export function postConversionEvent(
  eventName: string,
  embed: EmbedConfig,
  detail?: Record<string, unknown>,
): void {
  if (typeof window === "undefined" || window.parent === window) return;
  const targetOrigin = embed.allowedAncestors[0] ?? "*";
  window.parent.postMessage(
    { namespace: CWFE_MESSAGE_NAMESPACE, type: "conversion-event", eventName, detail } satisfies CwfeConversionMessage,
    targetOrigin,
  );
}
