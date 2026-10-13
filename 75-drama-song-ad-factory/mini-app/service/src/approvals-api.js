// ============================================================================
// approvals-api.js — Drama Studio service: approvals on the service (U3)
//
// SPEC section 1.6 and section 4 — the four routes that publish, list, answer
// and stream an approval:
//   POST   /api/studio/orders/<oid>/approvals                     machine/box key
//   GET    /api/studio/orders/<oid>/approvals                     any key
//   POST   /api/studio/orders/<oid>/approvals/<stage>/answer      link/machine key
//   GET    /api/studio/orders/<oid>/approvals/<stage>/file/<name> any key
//
// The two rules the approvals layer (mini-app/approvals/approvals.mjs) owns,
// implemented over this service's async KV adapter instead of its sync one:
//   1. FIRST ANSWER WINS — a second answer for the same stage+version is
//      refused by name (409 APPROVAL_ANSWER_TAKEN) and the record is untouched.
//   2. SAME VERSION = SAME ITEM — the key carries the ORDER id
//      (approval:<client>:<order>:<stage>:<version>), so a second order can
//      never collide, and a repeat publish returns the existing item with
//      created:false rather than a second item.
//
// The client_id always comes from the resolved key record (isolation.js), so a
// key only ever reads and answers inside its own scope.
//
// approvalsRoute(request, ctx) returns a Response for a path it owns and null
// for anything else, so index.js can try it after linkRoute/pageRoute (W2).
// ctx = { store, env, auth, body, url, nowMs, ok, fail } — the shared shape.
// ============================================================================

'use strict';

import { scopePath } from './ids.js';
import { listKeys } from './support.js';
import { presignPut } from './uploads.js';

/** The three approvals the studio asks for, in order. */
export const STAGES = ['script', 'song', 'storyboard'];

/** One plain file name: no slashes, no spaces, no traversal. */
export const FILE_NAME_RE = /^[A-Za-z0-9._-]{1,80}$/;

/** SPEC section 4 limits. */
export const MAX_APPROVAL_FILES = 40;
export const MAX_APPROVAL_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_APPROVAL_TEXT = 20000;

export const AF_APPROVAL_BAD = 'APPROVAL_BAD_INPUT';
export const AF_APPROVAL_UNKNOWN = 'APPROVAL_ITEM_UNKNOWN';
export const AF_APPROVAL_TAKEN = 'APPROVAL_ANSWER_TAKEN';
export const AF_APPROVAL_KIND = 'AF-DS-APPROVAL-KIND';
export const AF_LINK_KIND = 'AF-DS-LINK-KIND';
export const AF_ORDER_MISSING = 'AF-DS-ORDER-MISSING';
export const AF_FILE_MISSING = 'AF-DS-FILE-MISSING';
export const AF_STORAGE = 'AF-DS-UP-CAPABILITY';

export function approvalKey(clientId, orderId, stage, version) {
  return `approval:${clientId}:${orderId}:${stage}:${version}`;
}

export function approvalPrefix(clientId, orderId, stage = '') {
  return `approval:${clientId}:${orderId}:${stage ? `${stage}:` : ''}`;
}

/** The file route the page is given in `files[].url` (no version in the URL). */
export function fileRouteUrl(orderId, stage, name) {
  return `/api/studio/orders/${encodeURIComponent(orderId)}/approvals/${encodeURIComponent(stage)}/file/${encodeURIComponent(name)}`;
}

/** The R2 object path of one approval file. Throws on an unsafe segment. */
export function approvalFilePath(clientId, orderId, stage, version, name) {
  return scopePath(clientId, 'orders', orderId, 'approvals', `${stage}-v${version}`, name);
}

function bad(message) {
  return { ok: false, code: AF_APPROVAL_BAD, message };
}

/** SPEC section 4 shape of a publish body, checked before anything is stored. */
export function validatePublish(body) {
  const b = body && typeof body === 'object' ? body : {};
  if (!STAGES.includes(b.stage)) return bad('stage must be script, song or storyboard.');
  const version = Number(b.version);
  if (!Number.isInteger(version) || version < 1) return bad('version must be a positive integer.');
  if (typeof b.text !== 'string' || b.text.trim() === '' || b.text.length > MAX_APPROVAL_TEXT) {
    return bad(`text is required and must be at most ${MAX_APPROVAL_TEXT} characters.`);
  }
  const choices = b.choices === undefined || b.choices === null ? [] : b.choices;
  if (!Array.isArray(choices)) return bad('choices must be a list.');
  for (const c of choices) {
    if (!c || typeof c !== 'object' || typeof c.n !== 'number' || typeof c.label !== 'string') {
      return bad('every choice needs an n and a label.');
    }
  }
  const files = b.files === undefined || b.files === null ? [] : b.files;
  if (!Array.isArray(files)) return bad('files must be a list.');
  if (files.length > MAX_APPROVAL_FILES) return bad(`at most ${MAX_APPROVAL_FILES} files.`);
  for (const f of files) {
    if (!f || typeof f !== 'object') return bad('every file needs a name and a content type.');
    if (typeof f.name !== 'string' || !FILE_NAME_RE.test(f.name)) {
      return bad('file names may use letters, digits, dot, dash and underscore, 1-80 characters.');
    }
    if (typeof f.content_type !== 'string' || !/^(audio|image)\//.test(f.content_type)) {
      return bad('approval files must be audio or image.');
    }
    if (typeof f.bytes !== 'number' || f.bytes <= 0 || f.bytes > MAX_APPROVAL_FILE_BYTES) {
      return bad('each file must be under 25 MB.');
    }
  }
  return { ok: true, stage: b.stage, version, text: b.text, choices, files };
}

function localOk(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), { status, headers: JSON_HEADERS });
}

function localFail(status, code, message) {
  return new Response(JSON.stringify({ ok: false, code, message }), { status, headers: JSON_HEADERS });
}

const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};

async function requireOrder(store, clientId, orderId) {
  const raw = await store.kvGet(`order:${clientId}:${orderId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * The four approvals routes. Returns null when the path or method is not one
 * of them, so the caller's own 404 still answers everything else.
 */
export async function approvalsRoute(request, ctx) {
  const c = ctx || {};
  const url = c.url || new URL(request.url);
  const parts = String(url.pathname || '').replace(/\/+$/, '').split('/');
  if (parts[1] !== 'api' || parts[2] !== 'studio' || parts[3] !== 'orders' || !parts[4] || parts[5] !== 'approvals') {
    return null;
  }
  const orderId = parts[4];
  const rest = parts.slice(6);
  const method = request.method;
  const publish = rest.length === 0 && method === 'POST';
  const list = rest.length === 0 && method === 'GET';
  const answer = rest.length === 2 && rest[1] === 'answer' && method === 'POST';
  const file = rest.length === 3 && rest[1] === 'file' && method === 'GET';
  if (!publish && !list && !answer && !file) return null;

  const ok = typeof c.ok === 'function' ? c.ok : localOk;
  const fail = typeof c.fail === 'function' ? c.fail : localFail;
  const store = c.store;
  const env = c.env || {};
  const body = c.body && typeof c.body === 'object' ? c.body : {};
  const nowMs = typeof c.nowMs === 'number' ? c.nowMs : Date.now();
  const auth = c.auth;
  if (!auth || !auth.ok || !auth.record) {
    return fail(401, 'AF-DS-KEY-UNKNOWN', 'That key cannot open this.');
  }
  const clientId = auth.record.client_id;
  const kind = auth.record.kind;

  // Publish: the box or the computer publishes an approval; the phone never does.
  if (publish) {
    if (kind === 'link') return fail(403, AF_LINK_KIND, 'A link key cannot publish an approval.');
    if (kind !== 'machine' && kind !== 'box') return fail(403, AF_APPROVAL_KIND, 'That key cannot publish an approval.');
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    const check = validatePublish(body);
    if (!check.ok) return fail(400, check.code, check.message);
    // Every upload path and presign is settled BEFORE the item is stored, so a
    // refused file name or an unready bucket stores nothing at all.
    const uploads = [];
    for (const f of check.files) {
      let path;
      try {
        path = approvalFilePath(clientId, orderId, check.stage, check.version, f.name);
      } catch {
        return fail(400, AF_APPROVAL_BAD, 'That file name cannot be stored.');
      }
      const signed = await presignPut(env, path, f.content_type);
      if (!signed.ok) return fail(503, AF_STORAGE, 'Upload storage is not ready. Try again shortly.');
      uploads.push({ name: f.name, url: signed.upload.url, method: 'PUT' });
    }
    const key = approvalKey(clientId, orderId, check.stage, check.version);
    const existingRaw = await store.kvGet(key);
    let item = null;
    if (existingRaw) {
      try {
        item = JSON.parse(existingRaw);
      } catch {
        item = null;
      }
    }
    let created = false;
    if (!item) {
      created = true;
      item = {
        stage: check.stage,
        version: check.version,
        text: check.text,
        choices: check.choices,
        files: check.files.map((f) => f.name),
        answer: null,
        created_at: nowMs,
      };
      await store.kvPut(key, JSON.stringify(item));
    }
    // Presigns are stateless, so a retry of an existing item still gets fresh
    // upload links (the item itself is never rewritten: same version, same item).
    return ok({ item, created, uploads }, created ? 201 : 200);
  }

  // List: every item for this order, files mapped to the file route.
  if (list) {
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    const items = [];
    for (const key of await listKeys(store, approvalPrefix(clientId, orderId))) {
      const raw = await store.kvGet(key);
      if (!raw) continue;
      let item;
      try {
        item = JSON.parse(raw);
      } catch {
        continue;
      }
      items.push({
        ...item,
        files: (Array.isArray(item.files) ? item.files : []).map((name) => ({
          name,
          url: fileRouteUrl(orderId, item.stage, name),
        })),
      });
    }
    return ok({ items });
  }

  // Answer: first answer wins, by name and by status.
  if (answer) {
    const stage = rest[0];
    if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
    if (kind !== 'link' && kind !== 'machine') {
      return fail(403, AF_APPROVAL_KIND, 'That key cannot answer an approval.');
    }
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    const version = Number(body.version);
    if (!Number.isInteger(version) || version < 1) return fail(400, AF_APPROVAL_BAD, 'version must be a positive integer.');
    const value = typeof body.value === 'number' ? String(body.value) : body.value;
    if (typeof value !== 'string' || value.trim() === '' || value.length > MAX_APPROVAL_TEXT) {
      return fail(400, AF_APPROVAL_BAD, 'value is required.');
    }
    const key = approvalKey(clientId, orderId, stage, version);
    const raw = await store.kvGet(key);
    if (!raw) return fail(404, AF_APPROVAL_UNKNOWN, 'No such approval to answer.');
    let item;
    try {
      item = JSON.parse(raw);
    } catch {
      return fail(404, AF_APPROVAL_UNKNOWN, 'No such approval to answer.');
    }
    if (item.answer) return fail(409, AF_APPROVAL_TAKEN, 'The first answer for this approval is already recorded.');
    const recorded = { value, by: kind, at: nowMs };
    item.answer = recorded;
    await store.kvPut(key, JSON.stringify(item));
    return ok({ answer: recorded });
  }

  // File: the URL carries no version, so the stored item names the object.
  const stage = rest[0];
  const name = rest[2];
  if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
  if (typeof name !== 'string' || !FILE_NAME_RE.test(name)) {
    return fail(400, AF_APPROVAL_BAD, 'file names may use letters, digits, dot, dash and underscore, 1-80 characters.');
  }
  let published = null;
  for (const key of await listKeys(store, approvalPrefix(clientId, orderId, stage))) {
    const raw = await store.kvGet(key);
    if (!raw) continue;
    try {
      const item = JSON.parse(raw);
      if (Array.isArray(item.files) && item.files.includes(name)) {
        published = item;
        break;
      }
    } catch {
      continue;
    }
  }
  if (!published) return fail(404, AF_FILE_MISSING, 'No such approval file.');
  let path;
  try {
    path = approvalFilePath(clientId, orderId, stage, published.version, name);
  } catch {
    return fail(400, AF_APPROVAL_BAD, 'That file name cannot be stored.');
  }
  const bucket = env.DRAMA_STUDIO;
  const object = bucket && typeof bucket.get === 'function' ? await bucket.get(path) : null;
  if (!object) return fail(404, AF_FILE_MISSING, 'No such approval file.');
  return new Response(object.body, {
    status: 200,
    headers: {
      'Content-Type': (object.httpMetadata && object.httpMetadata.contentType) || 'application/octet-stream',
      'Cache-Control': 'no-store',
    },
  });
}
