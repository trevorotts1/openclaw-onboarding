// =============================================================================
// Drama Song Ad Factory mini-app — U20 OPTIONAL web push surface (browser side)
// -----------------------------------------------------------------------------
// mini-app/ui/push.js
//
// The OPTIONAL, version-2 web-push surface for the studio page (joint plan line
// 1091, "U20 | Optional web push | ... | U3; never version-0 gate"; line 832,
// "none blocks version 0").
//
// IT IS OFF UNTIL ASKED. This module is NOT imported by studio.js or index.html:
// the version-0 page is unchanged by this file, so a studio with web push unset
// behaves exactly as it did before U20 existed. A page turns the surface on only
// by calling it with `enabled: true` after the service's
// `GET /api/studio/push` reported `enabled: true`.
//
// Every function is inert on a false/missing input and names its refusal. No
// service key, no VAPID private key and no credential is ever handled here: the
// page receives only the browser's own subscription object and the service's
// PUBLIC VAPID key.
// =============================================================================

export const PUSH_OFF = "STUDIO_PUSH_OFF";
export const PUSH_UNSUPPORTED = "STUDIO_PUSH_UNSUPPORTED";

/** True only in a browser that can actually take a push subscription. */
export function pushSupported(win) {
  const w = win || (typeof globalThis !== "undefined" ? globalThis : {});
  return Boolean(
    w.PushManager
    && w.Notification
    && w.navigator
    && "serviceWorker" in w.navigator,
  );
}

/**
 * What the page should render. OFF by default: `show` is true ONLY when the
 * SERVICE said the feature is enabled AND the browser supports it. Any other
 * input — the default, an empty object, `enabled: false` — is off.
 */
export function pushSurfaceState({ enabled, supported } = {}) {
  if (enabled !== true || supported !== true) return { show: false, reason: enabled !== true ? PUSH_OFF : PUSH_UNSUPPORTED }; // U20-GUARD:ui-off
  return { show: true, reason: "ready" };
}

/**
 * Ask the browser for a subscription. REFUSES — touches no push manager and
 * requests no permission — unless the caller passes `enabled: true`, which only
 * a page that read `enabled: true` from the service does.
 */
export async function enablePush({ enabled, registration, applicationServerKey } = {}) {
  if (enabled !== true) {
    return { ok: false, code: PUSH_OFF, message: "Web push is off for this studio." };
  }
  if (!registration || !registration.pushManager || typeof registration.pushManager.subscribe !== "function") {
    return { ok: false, code: PUSH_UNSUPPORTED, message: "This browser cannot take a push subscription." };
  }
  if (!applicationServerKey) {
    return { ok: false, code: PUSH_OFF, message: "The studio has no public push key configured." };
  }
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey,
  });
  return { ok: true, subscription };
}

/** Drop the browser-side subscription. Safe to call when there is none. */
export async function disablePush({ subscription } = {}) {
  if (!subscription || typeof subscription.unsubscribe !== "function") {
    return { ok: true, removed: false };
  }
  const removed = await subscription.unsubscribe();
  return { ok: true, removed: Boolean(removed) };
}
