// ============================================================================
// push.js — Drama Studio service: OPTIONAL web push (U20)
//
// Joint plan line 1091, the U20 row:
//   | U20 | Optional web push | U3 | onboarding planned service |
//     U3; never version-0 gate | 6 | 3 | Optional owner | 2 |
// and joint plan line 832, the version table:
//   | **Version 2** | Optional web push U20 and optional U10 extras: Telegram
//     button, Open in Drama Studio card link, measurement view. ... none blocks
//     version 0 |
//
// WHAT THIS MODULE IS. The optional, version-2 web-push capability for the
// studio. Three facts bind it, all three read straight off those two lines:
//
//   1. OPTIONAL and OFF BY DEFAULT. Nothing here runs, stores, sends or changes
//      anything until an operator sets DS_WEB_PUSH_ENABLED. With it unset the
//      whole surface is inert: the status route says "off", the subscribe route
//      refuses and stores nothing, and the send path refuses before it touches a
//      subscription.
//   2. NEVER A VERSION-0 GATE. No version-0 route, page or test calls this
//      module, and a disabled (or enabled) push surface can never make another
//      behaviour required or different.
//   3. CONFIGURED, NEVER COMMITTED. The VAPID material is read from env
//      (schema.sql declares the names). No key value is stored, echoed or
//      printed; only the browser's PUBLIC keys and the push endpoint (both
//      non-secret) ever reach a stored record.
//
// It follows the existing service discipline instead of inventing a parallel
// one: identity and path scoping from ids.js, the isolated key-record-lookup
// pattern from isolation.js, a status lifecycle ('active' | 'revoked') like a
// key record in keys.js, and a retention kind in retention.js so a sweep
// partitions subscriptions out of a delete list.
//
// PURE apart from the INJECTED store. The service never opens a socket of its
// own: the actual RFC 8291 encryption + VAPID JWT signing is a TRANSPORT the
// runtime injects, so this unit ships no vendor, no key and no network call.
// ponytail: the transport is the ceiling. Upgrade path: when a push provider is
// chosen, vendor a vetted web-push implementation behind the same transport
// shape ({ subscription, payload, vapid }) -> { status } and nothing else here
// changes.
// ============================================================================

'use strict';

import { isClientId, randomHex } from './ids.js';

// ---------------------------------------------------------------------------
// Named refusals — a refusal always names itself, never a silent blank
// ---------------------------------------------------------------------------

export const AF_PUSH_DISABLED = 'AF-DS-PUSH-DISABLED';
export const AF_PUSH_MALFORMED = 'AF-DS-PUSH-MALFORMED';
export const AF_PUSH_MISSING = 'AF-DS-PUSH-MISSING';

/** Subscription ids look like the other studio ids: "push_<24 hex>". */
const SUBSCRIPTION_ID_RE = /^push_[0-9a-f]{24}$/;

// ---------------------------------------------------------------------------
// Configuration — OFF by default, keys from env only
// ---------------------------------------------------------------------------

/**
 * OFF BY DEFAULT. True only when an operator set the flag to an exact on-value.
 * Any other value (unset, '', 'false', 'yes', 'TRUE') leaves the surface off.
 */
export function pushEnabled(env) {
  if (!env || (env.DS_WEB_PUSH_ENABLED !== 'true' && env.DS_WEB_PUSH_ENABLED !== '1')) return false; // U20-GUARD:default-off
  return true;
}

/**
 * The VAPID material, read from env. Never logged, never stored, never returned
 * to a client. A missing value is the empty string, never undefined, so nothing
 * here can throw on an unconfigured studio.
 */
export function vapidFrom(env) {
  const e = env || {};
  return {
    publicKey: typeof e.DS_WEB_PUSH_PUBLIC_KEY === 'string' ? e.DS_WEB_PUSH_PUBLIC_KEY : '',
    subject: typeof e.DS_WEB_PUSH_SUBJECT === 'string' ? e.DS_WEB_PUSH_SUBJECT : '',
    privateKey: typeof e.DS_WEB_PUSH_PRIVATE_KEY === 'string' ? e.DS_WEB_PUSH_PRIVATE_KEY : '',
  };
}

/** Configured enough to send: the flag is on AND a private key is present. */
export function pushConfigured(env) {
  return pushEnabled(env) && vapidFrom(env).privateKey.length > 0;
}

// ---------------------------------------------------------------------------
// Subscription keys and the one ownership predicate
// ---------------------------------------------------------------------------

/** `push:<client_id>:<subscription_id>`. The client_id is in the key, so
 *  another client's key can never even name the record (same rule as orders). */
export function subscriptionKey(clientId, subscriptionId) {
  if (!isClientId(clientId) || typeof subscriptionId !== 'string' || !SUBSCRIPTION_ID_RE.test(subscriptionId)) {
    throw new Error(AF_PUSH_MALFORMED);
  }
  return `push:${clientId}:${subscriptionId}`;
}

export function subscriptionPrefix(clientId) {
  if (!isClientId(clientId)) throw new Error(AF_PUSH_MALFORMED);
  return `push:${clientId}:`;
}

/** The one predicate every read/revoke funnels through: a stored record belongs
 *  to a client ONLY when its own client_id says so. */
export function subscriptionBelongsTo(record, clientId) {
  if (!record) return false;
  if (record.client_id !== clientId) return false; // U20-GUARD:owns
  return true;
}

// ---------------------------------------------------------------------------
// Store operations
// ---------------------------------------------------------------------------

/** Validate the browser-supplied subscription. Endpoint + the two PUBLIC keys. */
export function normalizeSubscription(input) {
  const sub = input && typeof input === 'object' ? input : {};
  const endpoint = typeof sub.endpoint === 'string' ? sub.endpoint.trim() : '';
  const keys = sub.keys && typeof sub.keys === 'object' ? sub.keys : {};
  const p256dh = typeof keys.p256dh === 'string' ? keys.p256dh : '';
  const auth = typeof keys.auth === 'string' ? keys.auth : '';
  if (!endpoint || !/^https:\/\//.test(endpoint) || !p256dh || !auth) {
    return {
      ok: false,
      code: AF_PUSH_MALFORMED,
      message: 'A subscription needs an https endpoint and its two public keys.',
    };
  }
  return { ok: true, value: { endpoint, keys: { p256dh, auth } } };
}

/** A deterministic-or-random subscription id. */
export function newSubscriptionId(entropyHex) {
  const hex = typeof entropyHex === 'string' && /^[0-9a-f]{24}$/.test(entropyHex) ? entropyHex : randomHex(12);
  return `push_${hex}`;
}

export function buildSubscriptionRecord({ clientId, subscriptionId, subscription, userAgent, nowMs }) {
  return {
    subscription_id: subscriptionId,
    client_id: clientId,
    endpoint: subscription.endpoint,
    keys: { p256dh: subscription.keys.p256dh, auth: subscription.keys.auth },
    user_agent: typeof userAgent === 'string' && userAgent ? userAgent.slice(0, 200) : null,
    status: 'active',
    created_at: nowMs,
    updated_at: nowMs,
    revoked_at: null,
    last_sent_at: null,
  };
}

/** Every stored subscription record for ONE client, scope checked by the key. */
export async function listSubscriptions(store, clientId) {
  const prefix = subscriptionPrefix(clientId);
  const names = typeof store.kvList === 'function' ? await store.kvList(prefix) : [];
  const out = [];
  for (const name of Array.isArray(names) ? names : []) {
    const raw = await store.kvGet(name);
    if (!raw) continue;
    try {
      out.push(JSON.parse(raw));
    } catch {
      // An unreadable record is skipped, never guessed at.
    }
  }
  return out;
}

export async function activeSubscriptions(store, clientId) {
  return (await listSubscriptions(store, clientId)).filter((r) => r && r.status === 'active');
}

/**
 * Store one subscription. The SAME endpoint for the SAME client REPLACES its
 * record (one record per endpoint, never a growing pile of duplicates — the
 * same single-record discipline as the operator line).
 */
export async function registerSubscription(store, { clientId, subscription, userAgent, nowMs, entropyHex }) {
  const norm = normalizeSubscription(subscription);
  if (!norm.ok) return norm;
  const existing = (await listSubscriptions(store, clientId)).find((r) => r.endpoint === norm.value.endpoint);
  const subscriptionId = existing ? existing.subscription_id : newSubscriptionId(entropyHex);
  const record = existing
    ? {
        ...existing,
        keys: norm.value.keys,
        user_agent: typeof userAgent === 'string' && userAgent ? userAgent.slice(0, 200) : existing.user_agent,
        status: 'active',
        revoked_at: null,
        updated_at: nowMs,
      }
    : buildSubscriptionRecord({ clientId, subscriptionId, subscription: norm.value, userAgent, nowMs });
  await store.kvPut(subscriptionKey(clientId, subscriptionId), JSON.stringify(record));
  return { ok: true, record, replaced: Boolean(existing) };
}

/** Revoke one of the caller's OWN subscriptions. A record that is not theirs is
 *  reported as missing, so a cross-client probe learns nothing. */
export async function revokeSubscription(store, { clientId, subscriptionId, nowMs }) {
  let key;
  try {
    key = subscriptionKey(clientId, subscriptionId);
  } catch {
    return { ok: false, code: AF_PUSH_MALFORMED, message: 'That subscription id is not valid.' };
  }
  const raw = await store.kvGet(key);
  if (!raw) return { ok: false, code: AF_PUSH_MISSING, message: 'No such subscription for this key.' };
  let record;
  try {
    record = JSON.parse(raw);
  } catch {
    return { ok: false, code: AF_PUSH_MALFORMED, message: 'That subscription record is unreadable.' };
  }
  if (!subscriptionBelongsTo(record, clientId)) {
    return { ok: false, code: AF_PUSH_MISSING, message: 'No such subscription for this key.' };
  }
  const revoked = { ...record, status: 'revoked', revoked_at: nowMs, updated_at: nowMs };
  await store.kvPut(key, JSON.stringify(revoked));
  return { ok: true, record: revoked };
}

// ---------------------------------------------------------------------------
// The send path — explicitly opt-in, refuses before it touches a subscription
// ---------------------------------------------------------------------------

/**
 * Send one payload to a client's active subscriptions.
 *
 * REFUSES, with a named code and zero side effects, when web push is not both
 * enabled AND configured (or when no transport was injected). This is the
 * version-2 boundary in code: a version-0 studio, where DS_WEB_PUSH_ENABLED is
 * unset, can never send and never stores a `last_sent_at`.
 *
 * A push service answering 404/410 means the browser is gone: that subscription
 * is pruned (status 'revoked'), the same way a revoked key fails to resolve.
 */
export async function sendPush({ env, store, clientId, payload, transport, nowMs }) {
  if (!pushConfigured(env) || typeof transport !== 'function') return { ok: false, code: AF_PUSH_DISABLED, message: 'Web push is off or not configured. Nothing was sent.', attempted: 0, sent: 0, failed: 0, pruned: [] }; // U20-GUARD:refuse-unconfigured
  const message = {
    title: typeof payload?.title === 'string' ? payload.title : 'Your video',
    body: typeof payload?.body === 'string' ? payload.body : '',
    url: typeof payload?.url === 'string' ? payload.url : '/',
  };
  const vapid = vapidFrom(env);
  const subs = await activeSubscriptions(store, clientId);
  const out = { ok: true, attempted: subs.length, sent: 0, failed: 0, pruned: [] };
  for (const sub of subs) {
    let result;
    try {
      result = await transport({ subscription: sub, payload: message, vapid });
    } catch (err) {
      result = { status: 0, error: (err && err.message) || 'transport-failed' };
    }
    const status = result && typeof result.status === 'number' ? result.status : 0;
    if (status >= 200 && status < 300) {
      out.sent += 1;
      await store.kvPut(subscriptionKey(clientId, sub.subscription_id), JSON.stringify({ ...sub, last_sent_at: nowMs }));
    } else if (status === 404 || status === 410) {
      out.failed += 1;
      out.pruned.push(sub.subscription_id);
      await store.kvPut(
        subscriptionKey(clientId, sub.subscription_id),
        JSON.stringify({ ...sub, status: 'revoked', revoked_at: nowMs, updated_at: nowMs }),
      );
    } else {
      out.failed += 1;
    }
  }
  return out;
}
