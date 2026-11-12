// =============================================================================
// Drama Song Ad Factory mini-app — the page's service client
// -----------------------------------------------------------------------------
// mini-app/ui/service-client.js
//
// On import this module reads the personal link key out of the URL fragment
// (#k=<64 lowercase hex — what the service mints — or a legacy 32, optionally
// followed by &p=<page>) and, when a real key is there, installs
// `globalThis.studioService` — the fetch-backed object
// the page consumes. With no key in the hash it installs nothing, so the page
// keeps showing its existing "not connected" message and nothing is sent
// anywhere.
//
// Every call is same-origin and carries the key in the `x-ds-key` header; the
// fragment itself never reaches the server (SPEC.md §3, §4). Every method
// resolves the service's JSON body and rejects with the service's
// { code, message } on any non-ok answer.
//
//   getSession()                                  -> GET  /api/studio/session
//     -> { client_id, key_kind, option, option_line, draft, orders }
//   saveDraft({ replies })                        -> PUT  /api/studio/draft
//     -> { ok, updated_at }
//   getQuestions()                                -> GET  /questions.json
//     -> the intake_card studio-json export ({ format, version, questions… })
//   lockIn({ title, replies, upload_ids, order_id }) -> POST /api/studio/orders
//     -> { ok, order, option_line }
//   listApprovals(orderId)                        -> GET  /api/studio/orders/<id>/approvals
//     -> { ok, items }
//   answerApproval(orderId, stage, version, value)
//                                                 -> POST /api/studio/orders/<id>/approvals/<stage>/answer
//     -> { ok, answer }            (second answer: rejects code APPROVAL_ANSWER_TAKEN)
//   requestUpload(body)                           -> POST /api/studio/uploads
//     -> { ok, upload_id, upload_url, … }          (body passed through unchanged)
//   getDelivery(orderId)                          -> GET  /api/studio/orders/<id>
//     -> order.delivery (null until the run delivers)
//   listInbox()      -> { messages: [] }            (not built yet — SPEC.md §1)
//   postInbox()      -> rejects STUDIO_INBOX_UNAVAILABLE (not built yet — SPEC.md §1)
//
// Also exports linkKey() and personalLink() so the page can show the client
// their own link (and its QR) without re-parsing the hash.
// =============================================================================

const KEY_FORMAT = /^(?:[0-9a-f]{32}|[0-9a-f]{64})$/;

function hashParams() {
  const hash = (globalThis.location && globalThis.location.hash) || "";
  return new URLSearchParams(hash.replace(/^#/, ""));
}

/** The link key from the fragment — 64 hex as minted, 32 hex legacy — or null when there is none. */
export function linkKey() {
  const k = hashParams().get("k");
  return k && KEY_FORMAT.test(k) ? k : null;
}

/** The client's own personal link, or null without a key. */
export function personalLink() {
  const key = linkKey();
  return key ? `${globalThis.location.origin}/#k=${key}` : null;
}

const key = linkKey();

async function call(method, path, body) {
  const init = { method, headers: { "x-ds-key": key } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok || !data || data.ok === false) {
    const err = new Error(
      (data && data.message) || `The studio service answered ${res.status} for ${method} ${path}.`,
    );
    err.code = (data && data.code) || `AF-DS-HTTP-${res.status}`;
    throw err;
  }
  return data;
}

/** One exact approval file route: stage, version and presentation digest named. */
const EXACT_MEDIA_ROUTE =
  /^\/api\/studio\/orders\/[^/]+\/approvals\/[^/]+\/[1-9][0-9]*\/[0-9a-f]{64}\/file\/[A-Za-z0-9._-]{1,80}$/;

/**
 * Authenticated read of one approval file. `url` is the exact media route the
 * listing gives (`.../<stage>/<version>/<presentation-digest>/file/<name>`);
 * the key rides in x-ds-key, never the query. Resolves the blob plus the
 * service's declared digest so a caller can verify what it was served.
 * Any other origin or path is refused before a request is made.
 */
export async function fetchApprovalMedia(url) {
  if (typeof url !== "string" || !EXACT_MEDIA_ROUTE.test(url)) {
    const err = new Error("That media address is not this studio's approval route.");
    err.code = "APPROVAL_MEDIA_REFUSED";
    throw err;
  }
  const res = await fetch(url, { headers: { "x-ds-key": key }, cache: "no-store" });
  if (!res.ok) {
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    const err = new Error(
      (data && data.message) || `The studio answered ${res.status} for that file.`,
    );
    err.code = (data && data.code) || `AF-DS-HTTP-${res.status}`;
    throw err;
  }
  return {
    blob: await res.blob(),
    sha256: res.headers.get("x-ds-sha256") || null,
    contentType: res.headers.get("content-type") || null,
  };
}

/**
 * S75-071 — one tap, one order. While a lock-in is in flight, a second tap
 * (or any other caller) joins the SAME request instead of sending a second
 * order; the next tap after it settles starts a fresh one.
 */
let lockInInFlight = null;

const service = {
  getSession: () => call("GET", "/api/studio/session"),

  saveDraft: ({ replies }) => call("PUT", "/api/studio/draft", { replies }),

  // Static asset served with the page; the key rides along for uniformity.
  getQuestions: async () => {
    const res = await fetch("/questions.json", { headers: { "x-ds-key": key } });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data) {
      const err = new Error(`The studio could not load its questions (${res.status}).`);
      err.code = "AF-DS-QUESTIONS-MISSING";
      throw err;
    }
    return data;
  },

  lockIn: ({ title, replies, upload_ids, order_id }) => {
    if (!lockInInFlight) {
      lockInInFlight = call("POST", "/api/studio/orders", { title, replies, upload_ids, order_id })
        .finally(() => { lockInInFlight = null; });
    }
    return lockInInFlight;
  },

  listApprovals: (orderId) =>
    call("GET", `/api/studio/orders/${encodeURIComponent(orderId)}/approvals`),

  answerApproval: (orderId, stage, version, value) =>
    call(
      "POST",
      `/api/studio/orders/${encodeURIComponent(orderId)}/approvals/${encodeURIComponent(stage)}/answer`,
      { version, value },
    ),

  fetchApprovalMedia: (url) => fetchApprovalMedia(url),

  requestUpload: (body) => call("POST", "/api/studio/uploads", body),

  getDelivery: async (orderId) => {
    const data = await call("GET", `/api/studio/orders/${encodeURIComponent(orderId)}`);
    return (data.order && data.order.delivery) || null;
  },

  listInbox: async () => ({ messages: [] }),

  postInbox: async () => {
    const err = new Error("The studio inbox is not available yet. Nothing was sent.");
    err.code = "STUDIO_INBOX_UNAVAILABLE";
    throw err;
  },
};

if (key) globalThis.studioService = service;
