// ============================================================================
// link.js — Drama Studio service: the client's personal link (DSF W1-studio-service-U1)
//
// SPEC §1.1 and §3: every client has ONE personal link,
//   https://<studio>/#k=<LINK>
// with the key in the URL FRAGMENT, so the browser never sends it to the server
// and it cannot land in a URL log (the service rule in index.js:22-23). The page
// reads the fragment and sends it back in the `x-ds-key` header.
//
// Minting a new link sets the previous link key's record to `status: 'revoked'`
// (resolveKey already refuses revoked keys) and replaces the `link:<client_id>`
// pointer, so exactly one link works at a time.
//
// Route signature shared by link.js, page-api.js and approvals-api.js:
//   route(request, ctx)  with
//   ctx = { store, env, auth, body, url, nowMs, ok, fail, isAdmin }
// Returns a Response for its own path, otherwise null so the dispatcher can try
// the next module.
// ============================================================================

'use strict';

import { isClientId } from './ids.js';
import { buildKeyRecord, mintKey } from './keys.js';

/** A link key may not mint links (SPEC §3) — only a computer or a box may. */
export const AF_LINK_KIND = 'AF-DS-LINK-KIND';

/**
 * The client's one active link.
 *
 * @param {object} store  kv adapter (kvGet / kvPut)
 * @param {object} args
 * @param {string} args.clientId
 * @param {string} args.origin  e.g. `https://studio.example` (no trailing slash)
 * @param {boolean} args.rotate  mint a new link even if one exists
 * @param {number} args.nowMs
 * @returns {Promise<{ok:true, link:string} | {ok:true, link:null, exists:true}>}
 */
export async function mintLink(store, { clientId, origin, rotate, nowMs }) {
  const pointerKey = `link:${clientId}`;
  const raw = await store.kvGet(pointerKey);
  const pointer = raw ? JSON.parse(raw) : null;
  if (pointer && !rotate) return { ok: true, link: null, exists: true };

  const minted = await mintKey();
  const record = await buildKeyRecord({
    clientId,
    kind: 'link',
    label: 'personal link',
    secret: minted.secret,
    nowMs,
  });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));

  // Rotation kills the old link at once: its key record stops resolving, so the
  // previous URL is dead the moment this pointer moves.
  if (pointer && pointer.fingerprint) {
    const oldRaw = await store.kvGet(`key:${pointer.fingerprint}`);
    if (oldRaw) {
      const old = JSON.parse(oldRaw);
      old.status = 'revoked';
      await store.kvPut(`key:${pointer.fingerprint}`, JSON.stringify(old));
    }
  }

  await store.kvPut(pointerKey, JSON.stringify({ fingerprint: record.fingerprint, created_at: nowMs }));
  return { ok: true, link: `${origin}/#k=${minted.secret}` };
}

/**
 * `POST /api/studio/link`       — machine or box key of the caller's own client.
 * `POST /api/studio/admin/link`  — admin_key in the body, any client, always rotates.
 * Any other method or path returns null.
 */
export async function linkRoute(request, ctx) {
  const { url } = ctx;
  if (request.method !== 'POST') return null;
  const body = ctx.body || {};

  if (url.pathname === '/api/studio/link') {
    const auth = ctx.auth;
    const kind = auth && auth.ok && auth.record ? auth.record.kind : null;
    if (kind !== 'machine' && kind !== 'box') {
      return ctx.fail(403, AF_LINK_KIND, 'Only a computer or a box can mint a personal link.');
    }
    const out = await mintLink(ctx.store, {
      clientId: auth.client_id,
      origin: url.origin,
      rotate: Boolean(body.rotate),
      nowMs: ctx.nowMs,
    });
    return ctx.ok(out.exists ? { link: null, exists: true } : { link: out.link });
  }

  if (url.pathname === '/api/studio/admin/link') {
    if (!adminAllowed(ctx, body.admin_key)) {
      return ctx.fail(403, 'AF-DS-ADMIN-REFUSED', 'Not the admin.');
    }
    // Refuse BEFORE minting: a junk id must never become a link pointer.
    if (typeof body.client_id !== 'string' || !body.client_id) {
      return ctx.fail(400, 'AF-DS-ADMIN-INVALID', 'client_id is required.');
    }
    if (!isClientId(body.client_id)) {
      return ctx.fail(400, 'AF-DS-ADMIN-INVALID', 'client_id must be a studio-issued id (c-<32 hex>).');
    }
    const out = await mintLink(ctx.store, {
      clientId: body.client_id,
      origin: url.origin,
      rotate: true,
      nowMs: ctx.nowMs,
    });
    return ctx.ok({ link: out.link });
  }

  return null;
}

/** ctx.isAdmin arrives either as the raw isAdmin(env, presented) helper, as a
 *  key-only closure, or as a plain boolean — accept every shape, fail closed. */
function adminAllowed(ctx, presented) {
  const check = ctx.isAdmin;
  if (typeof check !== 'function') return Boolean(check);
  return Boolean(check(ctx.env, presented)) || Boolean(check(presented));
}
