// ============================================================================
// index.js — Drama Studio service entry (U2)
//
// Joint plan section 3.2: "One shared Drama Studio ... One page service, one
// storage bucket (drama-studio), two secrets. The client's own box (or Claude
// Code computer) is the brain... The box is the brain, the relay is dumb."
//
// This Worker is that dumb relay. It holds ZERO client credentials, ZERO KIE
// keys, ZERO GHL tokens and ZERO provider ids. It stores what the client said,
// mints short-lived direct-upload links, and answers one line to a check-in.
//
// BINDINGS (declared in schema.sql; wrangler.toml is U4's file, not this one)
//   DS_STUDIO             KV   — key records, client records, orders, check-ins,
//                                 upload jobs, the one operator record per
//                                 client per day
//   DRAMA_STUDIO          R2   — the client's inbox object and uploaded bytes
//   DS_ENROLLMENT_SECRET  secret — fleet enrollment (registration only; it
//                                 never reads an existing client's data)
//   DS_ADMIN_KEY          secret — the admin surface U12 consumes
//   R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY — presign only
//
// The presented key ALWAYS travels in the `x-ds-key` header, never in the query
// string, so it cannot land in a URL log.
//
// ROUTES (the interface contract consumed by U3, U4 and U12) — see README.md.
// ============================================================================

'use strict';

import { AF_ID_INVALID, isClientId } from './ids.js';
import { AF_ISO_CROSS, authorizeClient, enrollClient } from './isolation.js';
import { AF_PAIR_LOCKED, PAIRING_MAX_TRIES, attemptPairing, buildKeyRecord, mintKey, mintPairingCode, pairRecordKey } from './keys.js';
import { checkIn, writeInbox } from './inbox.js';
import { acceptUpload, pollUpload } from './uploads.js';
import { resolveOrderState, transition, writeOperatorRecord } from './lifecycle.js';
import { AF_OPT_APPROVAL, lastCheckIn, optionLine, setOption, staleVerdict } from './options.js';
import { listKeys, randomConnectHex } from './support.js';
import { AF_PUSH_DISABLED, pushEnabled, registerSubscription, revokeSubscription, sendPush } from './push.js';
// W2 wiring: the page, the personal link and the approvals live in their own
// modules; index.js only dispatches to them (SPEC §4).
import { AF_LINK_KIND, linkRoute } from './link.js';
import { deleteDraft, pageRoute, validateReplies } from './page-api.js';
import { approvalsRoute } from './approvals-api.js';

export const SERVICE_VERSION = '0.1.0';
export { randomConnectHex };

// ---------------------------------------------------------------------------
// Adapters — the shapes tests inject in memory
// ---------------------------------------------------------------------------

export function kvStore(ns) {
  return {
    kvGet: (k) => ns.get(k),
    kvPut: (k, v, ttl) => (ttl ? ns.put(k, v, { expirationTtl: ttl }) : ns.put(k, v)),
    kvDelete: (k) => ns.delete(k),
    kvList: async (prefix) => {
      const names = [];
      let cursor = null;
      do {
        const page = await ns.list({ prefix, cursor, limit: 1000 });
        names.push(...page.keys.map((k) => k.name));
        cursor = page.list_complete ? null : page.cursor;
      } while (cursor);
      return names;
    },
  };
}

export function r2Store(bucket) {
  return {
    objectGet: async (p) => {
      const o = await bucket.get(p);
      return o ? { value: await o.text() } : null;
    },
    objectPut: (p, v) => bucket.put(p, v),
  };
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    // The whole studio page, the admin page and the upload page are static
    // files under the assets dir (ui/); every JSON route starts with /api/.
    if (request.method === 'GET' && !path.startsWith('/api/')) {
      const assetPath = staticAssetPath(path);
      if (assetPath) return serveAsset(request, env, assetPath);
    }
    const store = kvStore(env.DS_STUDIO);
    const objects = r2Store(env.DRAMA_STUDIO);
    return handle(request, env, store, objects);
  },
};

export async function handle(request, env, store, objects, deps = {}) {
  const url = new URL(request.url);
  const parts = url.pathname.replace(/^\/+|\/+$/g, '').split('/');
  const nowMs = Date.now();
  const key = request.headers.get('x-ds-key') || '';
  let body = {};
  if (request.method === 'POST' || request.method === 'PUT') {
    try {
      body = await request.json();
    } catch {
      body = {};
    }
  }

  // GET /api/studio/health
  if (request.method === 'GET' && url.pathname === '/api/studio/health') {
    return ok({ service: 'drama-studio-service', version: SERVICE_VERSION });
  }

  // GET /api/studio/push — is the OPTIONAL web-push surface on? (U20)
  // Public and inert: it reveals one boolean and nothing else. Unset
  // DS_WEB_PUSH_ENABLED means `false` for every studio, forever.
  if (request.method === 'GET' && url.pathname === '/api/studio/push') {
    return ok({ enabled: pushEnabled(env) });
  }

  // POST /api/studio/enroll — a box registers itself ONCE and invents nothing
  if (request.method === 'POST' && url.pathname === '/api/studio/enroll') {
    const enrolled = await enrollClient({
      store,
      env,
      presentedSecret: body.enrollment_secret || '',
      claimedClientId: body.client_id,
      nowMs,
    });
    if (!enrolled.ok) return fail(403, enrolled.code, 'Registration was refused.');
    const minted = await mintKey();
    const record = await buildKeyRecord({ clientId: enrolled.client_id, kind: 'box', label: body.label, secret: minted.secret, nowMs });
    await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
    // The key is returned exactly once, to its owner. It is never stored raw.
    return ok({ client_id: enrolled.client_id, key: minted.secret }, 201);
  }

  // POST /api/studio/pair — U12 mints the code, this burns it (section 3.11)
  if (request.method === 'POST' && url.pathname === '/api/studio/pair') {
    // The 5-try lock has to hold per CALLER, not per code: a wrong code finds
    // no record, so a per-code counter never increments (section 3.11).
    const pairFailKey = `pairfail:${request.headers.get('CF-Connecting-IP') || 'unknown'}`;
    const pairFails = Number(await store.kvGet(pairFailKey)) || 0;
    if (pairFails >= PAIRING_MAX_TRIES) {
      return fail(403, AF_PAIR_LOCKED, 'Too many wrong codes from this address. Try again later.');
    }
    const recordRaw = await store.kvGet(await pairRecordKey(body.code || ''));
    const attempt = await attemptPairing(recordRaw ? JSON.parse(recordRaw) : null, body.code, nowMs);
    if (!attempt.ok) {
      if (attempt.record && recordRaw) {
        // Persist the incremented try count so the 5-try lock is real state,
        // not a per-request guess.
        await store.kvPut(`pair:${attempt.record.fingerprint}`, JSON.stringify(attempt.record), 900);
      }
      await store.kvPut(pairFailKey, String(pairFails + 1), 900);
      return fail(403, attempt.code, 'That pairing code cannot be used.');
    }
    await store.kvDelete(pairFailKey);
    await store.kvDelete(`pair:${attempt.record.fingerprint}`);
    const minted = await mintKey();
    const machine = await buildKeyRecord({
      clientId: attempt.record.client_id,
      kind: 'machine',
      label: body.computer_name,
      secret: minted.secret,
      nowMs,
    });
    await store.kvPut(`key:${machine.fingerprint}`, JSON.stringify(machine));
    return ok({ client_id: attempt.record.client_id, key: minted.secret, tools: body.tools || null }, 201);
  }

  // POST /api/studio/admin/pairing-code — admin surface U12 consumes
  if (request.method === 'POST' && url.pathname === '/api/studio/admin/pairing-code') {
    if (!isAdmin(env, body.admin_key)) return fail(403, 'AF-DS-ADMIN-REFUSED', 'Not the admin.');
    if (!body.client_id) return fail(400, 'AF-DS-ADMIN-INVALID', 'client_id is required.');
    if (!isClientId(body.client_id)) {
      // The studio INVENTS the identifier (ids.js) — never a name or a slug.
      // Refuse BEFORE minting: no code is created and nothing is stored, so a
      // bad id can never reach a key record and crash a later route.
      return fail(400, 'AF-DS-ADMIN-INVALID', 'client_id must be a studio-issued id (c-<32 hex>).');
    }
    const code = await mintPairingCode();
    await store.kvPut(
      `pair:${code.fingerprint}`,
      JSON.stringify({
        client_id: body.client_id,
        fingerprint: code.fingerprint,
        exp: nowMs + 15 * 60 * 1000,
        tries: 0,
        status: 'open',
      }),
      15 * 60,
    );
    return ok({ code: code.code, expires_in: 900 }, 201);
  }

  // POST /api/studio/options — admin sets the option (Option 3 behind approval)
  if (request.method === 'POST' && url.pathname === '/api/studio/options') {
    if (!isAdmin(env, body.admin_key)) return fail(403, 'AF-DS-ADMIN-REFUSED', 'Not the admin.');
    const target = body.target_client_id;
    if (!target) return fail(400, 'AF-DS-ADMIN-INVALID', 'target_client_id is required.');
    const record = await clientRecord(store, target);
    const set = setOption(record, body.option, { nowMs, approval: body.approval });
    if (!set.ok) return fail(set.code === AF_OPT_APPROVAL ? 403 : 400, set.code, set.message);
    await store.kvPut(`client:${target}`, JSON.stringify(set.record));
    return ok({ option: set.record.option, line: optionLine(set.record, nowMs, await lastCheckIn(objects, target)) });
  }

  // POST /api/studio/admin/push/send — operator-triggered, explicitly opt-in (U20)
  // Until a transport is injected (deps.pushTransport) this REFUSES and sends
  // nothing: an unconfigured studio is inert, never a half-send.
  if (request.method === 'POST' && url.pathname === '/api/studio/admin/push/send') {
    if (!isAdmin(env, body.admin_key)) return fail(403, 'AF-DS-ADMIN-REFUSED', 'Not the admin.');
    if (!body.target_client_id) return fail(400, 'AF-DS-ADMIN-INVALID', 'target_client_id is required.');
    const out = await sendPush({
      env, store, clientId: body.target_client_id, payload: body.payload, transport: deps.pushTransport, nowMs,
    });
    if (!out.ok) return fail(503, out.code || AF_PUSH_DISABLED, out.message || 'Web push is off.');
    return ok({ attempted: out.attempted, sent: out.sent, failed: out.failed, pruned: out.pruned });
  }

  // POST /api/studio/admin/link — the one route with no key: the admin page
  // presents the admin_key in the body, for any client (SPEC §4).
  if (request.method === 'POST' && url.pathname === '/api/studio/admin/link') {
    const adminLink = await linkRoute(request, { store, env, body, url, nowMs, ok, fail, isAdmin });
    if (adminLink) return adminLink;
  }

  // Everything below needs a key.
  const auth = await authorizeClient(store, key, body.client_id);
  if (!auth.ok) {
    if (auth.code === AF_ISO_CROSS) return fail(403, auth.code, 'That key cannot open this.');
    if (auth.code === AF_ID_INVALID) {
      // The key is known but its client_id is not a studio-issued id, so no
      // scoped path can be built. A structured refusal here — instead of
      // scopePath throwing deeper in the route — is what stops the Worker
      // returning 500 / error code 1101 (CHECKIN-500).
      return fail(401, auth.code, 'This key is not bound to a studio client id. Pair this computer again.');
    }
    return fail(401, auth.code, 'That key cannot open this.');
  }
  const clientId = auth.client_id;

  // W2 dispatch: link, page and approvals routes answer their own paths; the
  // first non-null Response wins and everything else falls through to the
  // routes below (SPEC §4).
  const ctx = { store, env, objects, auth, body, url, nowMs, ok, fail, isAdmin, project };
  for (const route of [linkRoute, pageRoute, approvalsRoute]) {
    const routed = await route(request, ctx);
    if (routed) return routed;
  }

  // POST /api/studio/push/subscribe — a browser registers its OWN subscription.
  // With web push off this refuses and stores NOTHING (section 5.2: a refusal
  // that writes is not a refusal).
  if (request.method === 'POST' && url.pathname === '/api/studio/push/subscribe') {
    if (!pushEnabled(env)) return fail(503, AF_PUSH_DISABLED, 'Web push is off. Nothing was stored.');
    const reg = await registerSubscription(store, {
      clientId, subscription: body.subscription, userAgent: request.headers.get('user-agent'), nowMs,
    });
    return reg.ok ? ok({ subscription_id: reg.record.subscription_id }, 201) : fail(400, reg.code, reg.message);
  }

  // POST /api/studio/push/unsubscribe — revoke one of the caller's own records.
  if (request.method === 'POST' && url.pathname === '/api/studio/push/unsubscribe') {
    const out = await revokeSubscription(store, { clientId, subscriptionId: body.subscription_id, nowMs });
    return out.ok
      ? ok({ subscription_id: out.record.subscription_id, status: out.record.status })
      : fail(404, out.code, out.message || 'No such subscription for this key.');
  }

  // POST /api/studio/checkin — the 2-minute network call. Zero model tokens.
  if (request.method === 'POST' && url.pathname === '/api/studio/checkin') {
    const result = await checkIn(objects, { clientId, nowMs, orders: body.orders });
    if (Array.isArray(body.orders)) await writeInbox(objects, { clientId, orders: body.orders, nowMs });
    return ok(result);
  }

  // POST /api/studio/uploads — presigned DIRECT R2 PUT, bytes never here
  if (request.method === 'POST' && url.pathname === '/api/studio/uploads') {
    const out = await acceptUpload({ store, env, clientId, body, nowUtc: new Date(nowMs).toISOString() });
    return out.ok ? ok(out, out.status) : fail(out.status, out.code, out.message);
  }

  // POST /api/studio/orders — the client tapped Lock it in
  if (request.method === 'POST' && url.pathname === '/api/studio/orders') {
    // The answers are the order: the box replays them through factory.py, so
    // they are validated against the SPEC §4 limits and stored on the record
    // (they used to be dropped — only the title survived).
    const checked = validateReplies(body.replies === undefined ? [] : body.replies, body.upload_ids);
    if (!checked.ok) return fail(400, checked.code, checked.message);
    const orderId = body.order_id || `r_${randomConnectHex(4)}`;
    const order = {
      order_id: orderId,
      client_id: clientId,
      title: String(body.title || 'your video'),
      replies: checked.replies,
      upload_ids: checked.uploadIds,
      state: 'waiting',
      paid_started: false,
      created_at: nowMs,
      updated_at: nowMs,
    };
    await store.kvPut(`order:${clientId}:${orderId}`, JSON.stringify(order));
    // Lock it in ends the draft: the order holds the answers now.
    await deleteDraft(objects, clientId);
    const waiting = await waitingList(store, clientId);
    await writeInbox(objects, { clientId, orders: waiting, nowMs });
    return ok({
      order: project(order, nowMs),
      option_line: optionLine(await clientRecord(store, clientId), nowMs, await lastCheckIn(objects, clientId)),
    }, 201);
  }

  // /api/studio/orders/<id> and /api/studio/orders/<id>/<verb>
  if (parts.length >= 4 && parts[0] === 'api' && parts[1] === 'studio' && parts[2] === 'orders') {
    const orderId = parts[3];
    const verb = parts[4];
    const raw = await store.kvGet(`order:${clientId}:${orderId}`);
    if (!raw) return fail(404, 'AF-DS-ORDER-MISSING', 'No such order for this key.');

    if (!verb && request.method === 'GET') {
      const stale = staleVerdict({
        record: await clientRecord(store, clientId),
        lastCheckMs: await lastCheckIn(objects, clientId),
        hasWaitingOrder: JSON.parse(raw).state === 'waiting',
        nowMs,
      });
      if (stale.stale && stale.operator_line) {
        // Rule 3: replaced, never stacked. One record per client per day.
        await writeOperatorRecord(store, { clientId, line: stale.operator_line, nowMs });
      }
      return ok({ order: project(JSON.parse(raw), nowMs), stale_page_line: stale.page_line });
    }

    if (verb === 'state' && request.method === 'POST') {
      // SPEC §3: the phone may cancel its own order and nothing else — claim,
      // deliver and every other event belong to the box or the computer.
      if (auth.record.kind === 'link' && body.event !== 'cancel') {
        return fail(403, AF_LINK_KIND, 'A personal link may only cancel an order.');
      }
      const moved = transition(JSON.parse(raw), body.event, { nowMs, actor: body.actor || auth.record.kind });
      if (!moved.ok) return fail(409, moved.code, moved.message);
      if (body.event === 'claim' || body.event === 'needs_you') moved.order.paid_started = Boolean(body.paid_started);
      if (body.event === 'deliver' && body.delivery && typeof body.delivery === 'object') {
        // The page shows WHERE the video is (GHL library first, R2 copy
        // second). Only an https URL and one of the two known kinds are stored.
        const deliveryUrl = typeof body.delivery.url === 'string' ? body.delivery.url : '';
        const deliveryKind = body.delivery.kind === 'ghl' || body.delivery.kind === 'r2' ? body.delivery.kind : null;
        if (deliveryUrl.startsWith('https://') && deliveryKind) {
          moved.order.delivery = { url: deliveryUrl, kind: deliveryKind };
        }
      }
      await store.kvPut(`order:${clientId}:${orderId}`, JSON.stringify(moved.order));
      await writeInbox(objects, { clientId, orders: await waitingList(store, clientId), nowMs });
      return ok({ order: project(moved.order, nowMs) });
    }

    if (verb === 'cancel' && request.method === 'POST') {
      const moved = transition(JSON.parse(raw), 'cancel', { nowMs, actor: auth.record.kind });
      if (!moved.ok) return fail(409, moved.code, moved.message);
      await store.kvPut(`order:${clientId}:${orderId}`, JSON.stringify(moved.order));
      await writeInbox(objects, { clientId, orders: await waitingList(store, clientId), nowMs });
      return ok({ order: project(moved.order, nowMs) });
    }
  }

  // GET /api/studio/options — the real-wait line for the client's record
  if (request.method === 'GET' && url.pathname === '/api/studio/options') {
    const record = await clientRecord(store, clientId);
    return ok({ option: record.option || 1, line: optionLine(record, nowMs, await lastCheckIn(objects, clientId)) });
  }

  // POST /api/studio/uploads/<id>/complete — the poll view for a phone
  if (parts.length === 5 && parts[4] === 'complete' && request.method === 'POST') {
    const poll = await pollUpload(store, { clientId, uploadId: parts[3] });
    return poll.ok ? ok(poll.job) : fail(poll.status, poll.code, poll.message);
  }

  return fail(404, 'AF-DS-NOT-FOUND', `No route for ${request.method} ${url.pathname}.`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function isAdmin(env, presented) {
  const expected = env && env.DS_ADMIN_KEY;
  return typeof expected === 'string' && expected.length > 0 && presented === expected;
}

/** The one place that maps a public GET path onto a file inside the assets
 *  directory (ui/). Everything that is not /api/ is a page file (SPEC §4). */
function staticAssetPath(path) {
  if (path === '/' || path === '/index.html') return '/index.html';
  if (path === '/admin' || path === '/admin/') return '/admin/index.html';
  if (path === '/uploads' || path === '/uploads/') return '/upload/index.html';
  if (path === '/upload.js') return '/upload/upload.js';
  if (path.startsWith('/api/')) return null;
  return path;
}

/** Serve one file from the assets binding with the service's own headers.
 *  The upload page moved from the assets root into ui/upload/, so a bundle
 *  deployed before that move still answers at the root: try ui/upload/ first,
 *  then the root. */
async function serveAsset(request, env, assetPath) {
  if (!env.DS_UPLOAD_ASSETS) return fail(503, 'AF-DS-UP-PAGE', 'That page is not ready.');
  const candidates = assetPath === '/upload/index.html' ? [assetPath, '/index.html'] : [assetPath];
  let asset = null;
  for (const candidate of candidates) {
    try {
      const got = await env.DS_UPLOAD_ASSETS.fetch(new Request(new URL(candidate, request.url), request));
      if (got && got.status >= 200 && got.status < 300) {
        asset = got;
        break;
      }
    } catch {
      // A bundle without that file: try the next candidate.
    }
  }
  if (!asset) return fail(404, 'AF-DS-UP-PAGE', 'That page is not ready.');
  const headers = new Headers(asset.headers);
  headers.set('Cache-Control', 'no-store');
  headers.set('Referrer-Policy', 'no-referrer');
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.r2.cloudflarestorage.com; frame-ancestors 'none'; form-action 'self'; base-uri 'none'");
  return new Response(asset.body, { status: asset.status, headers });
}

async function clientRecord(store, clientId) {
  const raw = await store.kvGet(`client:${clientId}`);
  return raw ? JSON.parse(raw) : { client_id: clientId, option: 1, last_check_in: null };
}

async function waitingList(store, clientId) {
  const keys = await listKeys(store, `order:${clientId}:`);
  const orders = [];
  for (const k of keys) {
    const raw = await store.kvGet(k);
    if (raw) orders.push(JSON.parse(raw));
  }
  return orders;
}

/** The projection U3 renders: state with timers applied, plus availability.
 *  R2 availability is a SEPARATE field, never an order state (section 3.10A). */
export function project(order, nowMs) {
  const resolved = resolveOrderState(order, nowMs);
  const out = { ...order, state: resolved.state, state_reason: resolved.reason };
  if (resolved.timer) out.state_from_timer = true;
  if (typeof order.delivered_at === 'number') {
    out.availability = nowMs >= order.delivered_at + 7 * 24 * 60 * 60 * 1000 ? 'r2-expired' : 'available';
  } else {
    out.availability = 'not-delivered';
  }
  return out;
}

function ok(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), {
    status,
    headers: JSON_RESPONSE_HEADERS,
  });
}

function fail(status, code, message) {
  return new Response(JSON.stringify({ ok: false, code, message }), {
    status,
    headers: JSON_RESPONSE_HEADERS,
  });
}

const JSON_RESPONSE_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};

