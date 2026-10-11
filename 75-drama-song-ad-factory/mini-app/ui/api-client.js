// =============================================================================
// Drama Song Ad Factory mini-app — U3/U2 service boundary
// -----------------------------------------------------------------------------
// mini-app/ui/api-client.js
//
// THE INTERFACE U3 (this UI) CONSUMES FROM U2 (the service). Nothing here
// implements service behaviour — keys, inbox, uploads, retention, per-client
// isolation, lifecycle/timer precedence and the once-per-day operator record
// all live on U2's side of this line. This file is the whole contract.
//
// HOW THE UI FINDS THE SERVICE. The deploy shell (U4) or the service itself
// installs `globalThis.studioService` before studio.js runs. There is no other
// discovery path and deliberately no fallback: a page with no service says so
// in plain words rather than pretending to save anything.
//
// CONTRACT (input shape -> output shape). Every call is async and may reject
// with { code, message }.
//
//   getSession({ clientId })
//     -> { clientId, answers: { [questionId]: value }, approvals: { script: bool,
//          song: id|null, storyboard: bool }, stage: string, updatedAt: iso }
//
//   saveAnswer({ clientId, questionId, value })            // value: string
//     -> { ok: true, updatedAt: iso }
//
//   getOptions()
//     -> { questions: [{ id, label, prompt, hint, choices: [{ id, label, hint }] }],
//          looks:     [{ id, label, hint, sampleUrl }],
//          songs:     [{ id, label, hint, audioUrl }] }
//
//   listInbox({ clientId })                                // client <-> studio messages
//     -> { messages: [{ id, from: "client"|"studio", body, at }] }
//
//   postInbox({ clientId, body })
//     -> { ok: true, message: { id, at } }
//
//   requestUpload({ clientId, filename, contentType, bytes })
//     -> { key, uploadUrl, expiresAt }                     // service owns keys + retention
//
//   advance({ clientId, stage })                           // lifecycle/timer precedence
//     -> { ok: true, stage, operatorRecorded: bool }       // one operator record per client/day
//
//   getDelivery({ clientId, runId })
//     -> { masterUrl, clips: [{ label, url, bytes }], shareUrl, qrPayload }
//
//   verifyDeliveryLink(url)                                // service-side HEAD, no redirect follow
//     -> { ok, status, contentLength, contentType, disposition }
//
// OPTIONAL, version-2 only (U20). The page calls these ONLY when it wants the
// optional web-push surface; the version-0 page never does, and the service
// answers `enabled: false` for every studio with DS_WEB_PUSH_ENABLED unset.
//
//   getPushStatus()
//     -> { enabled: bool }                                  // false unless an operator opted in
//
//   subscribePush({ clientId, subscription })              // subscription: the browser's own
//     -> { ok: true, subscriptionId }                      // refused (503) and stores NOTHING when off
//
//   unsubscribePush({ clientId, subscriptionId })
//     -> { ok: true, subscriptionId, status: "revoked" }
// =============================================================================

export const ENTRYPOINTS = [
  "getSession",
  "saveAnswer",
  "getOptions",
  "listInbox",
  "postInbox",
  "requestUpload",
  "advance",
  "getDelivery",
  "verifyDeliveryLink",
];

/** U20 — the optional, version-2 push surface. Never required by version 0. */
export const OPTIONAL_PUSH_ENTRYPOINTS = [
  "getPushStatus",
  "subscribePush",
  "unsubscribePush",
];

export class ServiceUnavailableError extends Error {
  constructor() {
    super(
      "The studio service is not connected on this page, so nothing can be "
      + "saved or started yet. Nothing you typed has been sent anywhere.",
    );
    this.name = "ServiceUnavailableError";
    this.code = "STUDIO_SERVICE_UNAVAILABLE";
  }
}

function resolveService() {
  const service = globalThis.studioService;
  if (!service) throw new ServiceUnavailableError();
  return service;
}

function call(name, ...args) {
  const service = resolveService();
  const fn = service[name];
  if (typeof fn !== "function") {
    const err = new ServiceUnavailableError();
    err.code = "STUDIO_SERVICE_ENTRYPOINT_MISSING";
    err.message = `The studio service does not provide ${name}(). Nothing was saved.`;
    throw err;
  }
  return fn.apply(service, args);
}

export const studio = {
  getSession: (p) => call("getSession", p),
  saveAnswer: (p) => call("saveAnswer", p),
  getOptions: (p) => call("getOptions", p),
  listInbox: (p) => call("listInbox", p),
  postInbox: (p) => call("postInbox", p),
  requestUpload: (p) => call("requestUpload", p),
  advance: (p) => call("advance", p),
  getDelivery: (p) => call("getDelivery", p),
  verifyDeliveryLink: (p) => call("verifyDeliveryLink", p),
  // U20 — optional, version-2. Called only after getPushStatus() said enabled.
  getPushStatus: (p) => call("getPushStatus", p),
  subscribePush: (p) => call("subscribePush", p),
  unsubscribePush: (p) => call("unsubscribePush", p),
};

export function serviceConnected() {
  return !!globalThis.studioService;
}
