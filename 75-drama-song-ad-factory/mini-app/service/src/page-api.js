// ============================================================================
// page-api.js — Drama Studio service: the phone page's data routes (W1 U2)
//
// The page needs three things nothing served before this unit: its session
// (orders, draft, the real-wait line), a draft that survives closing the page,
// and the answer validation `POST /api/studio/orders` never did (index.js:265
// stored only the title). SPEC §1.3-1.4, §4, §5.
//
// ROUTES (SPEC §4) — `pageRoute` returns a Response, or null when the path is
// not one of its own, so index.js can hand the request to the next module.
//   GET  /api/studio/session  any key
//   PUT  /api/studio/draft    link or machine key
//
// ALSO EXPORTS (consumed by index.js in W2, not routes themselves):
//   validateReplies(replies, uploadIds) — the SPEC §4 limits, one place
//   deleteDraft(objects, clientId)      — R2 has no delete, so `{}` marker
//
// ctx (the shape W2 builds after authorizeClient; the same object link.js and
// approvals-api.js receive) — pageRoute reads exactly these:
//   store, objects, auth, body, url, nowMs, ok, fail, project
//   objects — index.js's r2Store(env.DRAMA_STUDIO): { objectGet, objectPut }
//   project — index.js's project(order, nowMs) projection for each order
// ============================================================================

'use strict';

import { scopePath } from './ids.js';
import { DEFAULT_OPTION, OPTIONS, lastCheckIn, optionLine } from './options.js';
import { listKeys } from './support.js';

export const AF_ORDER_INVALID = 'AF-DS-ORDER-INVALID';
export const AF_DRAFT_KIND = 'AF-DS-DRAFT-KIND';

/** SPEC §4 limits. */
export const MAX_REPLIES = 20;
export const MAX_REPLY_CHARS = 2000;
export const MAX_UPLOAD_IDS = 10;
export const MAX_SESSION_ORDERS = 20;

const DRAFT_FILE = 'draft.json';
/** The R2 object carries no delete in the adapter, so "no draft" is `{}`. */
const DRAFT_NONE = '{}';

/**
 * The one validator for the client's answers, used by PUT /api/studio/draft
 * here and by POST /api/studio/orders in index.js (W2). The strings travel to
 * the box unchanged — intake_card.py stays the only semantic validator; this
 * is the size/type gate that keeps a bad body from reaching storage.
 *
 * @returns {{ok:true, replies:string[], uploadIds:string[]} |
 *           {ok:false, code:string, message:string}}
 */
export function validateReplies(replies, uploadIds) {
  if (!Array.isArray(replies)) {
    return { ok: false, code: AF_ORDER_INVALID, message: 'replies must be the list of answers you gave.' };
  }
  if (replies.length > MAX_REPLIES) {
    return { ok: false, code: AF_ORDER_INVALID, message: `replies must hold at most ${MAX_REPLIES} answers.` };
  }
  for (const reply of replies) {
    if (typeof reply !== 'string') {
      return { ok: false, code: AF_ORDER_INVALID, message: 'every reply must be text.' };
    }
    if (reply.length > MAX_REPLY_CHARS) {
      return { ok: false, code: AF_ORDER_INVALID, message: `each reply must be at most ${MAX_REPLY_CHARS} characters.` };
    }
  }
  const ids = uploadIds === undefined || uploadIds === null ? [] : uploadIds;
  if (!Array.isArray(ids)) {
    return { ok: false, code: AF_ORDER_INVALID, message: 'upload_ids must be a list.' };
  }
  if (ids.length > MAX_UPLOAD_IDS) {
    return { ok: false, code: AF_ORDER_INVALID, message: `upload_ids must hold at most ${MAX_UPLOAD_IDS} entries.` };
  }
  for (const id of ids) {
    if (typeof id !== 'string') {
      return { ok: false, code: AF_ORDER_INVALID, message: 'every upload id must be text.' };
    }
  }
  return { ok: true, replies, uploadIds: ids };
}

/**
 * @param {Request} request
 * @param {object} ctx see the header; the caller already authorized the key.
 * @returns {Promise<Response|null>} null when the path is not this module's
 */
export async function pageRoute(request, ctx) {
  const path = ctx.url.pathname;
  if (request.method === 'GET' && path === '/api/studio/session') return sessionRoute(ctx);
  if (request.method === 'PUT' && path === '/api/studio/draft') return draftRoute(ctx);
  return null;
}

/** R2 has no delete in the adapter, so an empty marker stands for "no draft".
 *  W2 calls this after Lock it in. */
export async function deleteDraft(objects, clientId) {
  await objects.objectPut(scopePath(clientId, DRAFT_FILE), DRAFT_NONE);
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

async function sessionRoute(ctx) {
  const { store, objects, auth, nowMs, ok, project } = ctx;
  const clientId = auth.client_id;

  const orders = [];
  for (const name of await listKeys(store, `order:${clientId}:`)) {
    const raw = await store.kvGet(name);
    if (!raw) continue;
    try {
      orders.push(JSON.parse(raw));
    } catch {
      // A record this route cannot read is skipped, never guessed at.
    }
  }
  orders.sort((a, b) => (Number(b.created_at) || 0) - (Number(a.created_at) || 0));

  const record = await clientRecord(store, clientId);
  return ok({
    client_id: clientId,
    key_kind: auth.record.kind,
    option: OPTIONS.includes(record.option) ? record.option : DEFAULT_OPTION,
    option_line: optionLine(record, nowMs, await lastCheckIn(objects, clientId)),
    draft: await readDraft(objects, clientId),
    orders: orders.slice(0, MAX_SESSION_ORDERS).map((order) => project(order, nowMs)),
  });
}

async function draftRoute(ctx) {
  const { store, objects, auth, body, nowMs, ok, fail } = ctx;
  const kind = auth.record && auth.record.kind;
  // SPEC §3: a box enrolls, checks in and claims; it never speaks for the
  // phone. Only the client's own two keys save the client's own answers.
  if (kind !== 'link' && kind !== 'machine') {
    return fail(403, AF_DRAFT_KIND, 'Only a personal link or a paired computer saves the draft.');
  }
  const checked = validateReplies(body.replies, body.upload_ids);
  if (!checked.ok) return fail(400, checked.code, checked.message);

  const updated_at = nowMs;
  await objects.objectPut(
    scopePath(auth.client_id, DRAFT_FILE),
    JSON.stringify({ replies: checked.replies, updated_at }),
  );
  return ok({ updated_at });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function clientRecord(store, clientId) {
  const raw = await store.kvGet(`client:${clientId}`);
  return raw ? JSON.parse(raw) : { client_id: clientId, option: DEFAULT_OPTION, last_check_in: null };
}

/** `{replies, updated_at}` or null — where null also covers the `{}` marker,
 *  a missing object and anything unparseable (never a throw on the phone). */
async function readDraft(objects, clientId) {
  const obj = await objects.objectGet(scopePath(clientId, DRAFT_FILE));
  if (!obj) return null;
  let draft;
  try {
    draft = JSON.parse(obj.value);
  } catch {
    return null;
  }
  if (!draft || typeof draft !== 'object' || !Array.isArray(draft.replies)) return null;
  return {
    replies: draft.replies,
    updated_at: typeof draft.updated_at === 'number' ? draft.updated_at : null,
  };
}
