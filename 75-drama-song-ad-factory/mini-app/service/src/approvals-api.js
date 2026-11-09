// ============================================================================
// approvals-api.js — Drama Studio service: approvals on the service (U3 / P07)
//
// Routes:
//   POST /api/studio/orders/<oid>/approvals                          machine/box
//   GET  /api/studio/orders/<oid>/approvals                          any key
//   POST /api/studio/orders/<oid>/approvals/<stage>/answer           link only
//   POST /api/studio/orders/<oid>/approvals/<stage>/<v>/finalize     machine/box
//   GET  /api/studio/orders/<oid>/approvals/<stage>/<v>/<digest>/file/<name>
//                                                                    any key
//
// The rules this layer owns, now enforced by the store instead of by a
// read-modify-write over key-value:
//   1. FIRST ANSWER WINS — the decision is created once with an R2
//      `If-None-Match: *` put. Competing requests cannot both win; the loser
//      reads the committed winner and is refused by name (409
//      APPROVAL_ANSWER_TAKEN). There is no process-local lock.
//   2. SAME VERSION = SAME IMMUTABLE PRESENTATION — the intent object is
//      created BEFORE any upload link is minted. A retry with the same
//      presentation digest resumes; a different digest for the same version is
//      refused (409 APPROVAL_REVISION_CONFLICT) before a single presign.
//   3. READY OR NOTHING — files are copied from staging to `files/` only after
//      their length and SHA-256 match the intent, and `ready.json` is created
//      after every one of them is frozen. Only a ready manifest is answerable.
//   4. EXACT MEDIA — the file URL names stage, version and presentation digest,
//      so one basename can never resolve to another version's bytes. The key
//      authorization is the existing `x-ds-key` header; no query key, no
//      public-media exception.
//
// Machine and box keys may publish and finalize. Only the client's link may
// ANSWER. That is a narrowed authority, not proof of a human: the producer
// still mints the link (P05/P06 own real isolation).
//
// Authority objects live in the `approvals-v2` R2 namespace (approval-store.js).
// The old KV records and the old revisionless file route are kept for reading
// nothing: they are refused by name and never converted into new authority.
//
// approvalsRoute(request, ctx) returns a Response for a path it owns and null
// for anything else. ctx = { store, env, auth, body, url, nowMs, ok, fail }.
// ============================================================================

'use strict';

import { isClientId, scopePath } from './ids.js';
import { presignPut } from './uploads.js';
import {
  AF_APPROVAL_BYTES,
  AF_APPROVAL_STORAGE,
  ApprovalStorageError,
  DIGEST_RE,
  approvalBucket,
  createOnce,
  decisionPath,
  frozenPath,
  intentPath,
  listReady,
  objectMatches,
  putFrozen,
  readJson,
  readObject,
  readyPath,
  sha256Hex,
  stagingPath,
} from './approval-store.js';

/** The three approvals the studio asks for, in order. */
export const STAGES = ['script', 'song', 'storyboard'];

/** One plain file name: no slashes, no spaces, no traversal. */
export const FILE_NAME_RE = /^[A-Za-z0-9._-]{1,80}$/;

/** `.` and `..` match FILE_NAME_RE but are directory segments, never files. */
function safeFileName(name) {
  return typeof name === 'string' && FILE_NAME_RE.test(name) && name !== '.' && name !== '..';
}

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
/** Same version, different presentation: still immutable, still refused. */
export const AF_APPROVAL_REVISION = 'APPROVAL_REVISION_CONFLICT';
/** An upload never arrived, or arrived with different bytes. */
export const AF_APPROVAL_UPLOAD = 'APPROVAL_UPLOAD_UNVERIFIED';
/** The revisionless URL cannot name bytes, so it is refused, never redirected. */
export const AF_REVISION_REQUIRED = 'APPROVAL_REVISION_REQUIRED';

// ---------------------------------------------------------------------------
// Legacy key/URL helpers — kept exported so existing importers do not break.
// They describe the OLD namespace, which is no longer read for authority.
// ---------------------------------------------------------------------------

/** @deprecated old KV record key; kept for readers of existing records. */
export function approvalKey(clientId, orderId, stage, version) {
  return `approval:${clientId}:${orderId}:${stage}:${version}`;
}

/** @deprecated old KV prefix; kept for readers of existing records. */
export function approvalPrefix(clientId, orderId, stage = '') {
  return `approval:${clientId}:${orderId}:${stage ? `${stage}:` : ''}`;
}

/** @deprecated revisionless file URL — refused by this module by name. */
export function fileRouteUrl(orderId, stage, name) {
  return `/api/studio/orders/${encodeURIComponent(orderId)}/approvals/${encodeURIComponent(stage)}/file/${encodeURIComponent(name)}`;
}

/** @deprecated old object path; the v2 frozen path is `frozenPath()`. */
export function approvalFilePath(clientId, orderId, stage, version, name) {
  return scopePath(clientId, 'orders', orderId, 'approvals', `${stage}-v${version}`, name);
}

/** The exact media route: stage, version and presentation digest are named. */
export function exactFileRouteUrl(orderId, stage, version, digest, name) {
  return [
    '/api/studio/orders',
    encodeURIComponent(orderId),
    'approvals',
    encodeURIComponent(stage),
    encodeURIComponent(String(version)),
    encodeURIComponent(digest),
    'file',
    encodeURIComponent(name),
  ].join('/');
}

function bad(message) {
  return { ok: false, code: AF_APPROVAL_BAD, message };
}

/**
 * SPEC section 4 shape of a publish body, checked before anything is stored.
 * Every file declares its own length and SHA-256; that declaration is what the
 * frozen copy is later verified against.
 */
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
  const numbers = new Set();
  const cleanChoices = [];
  for (const c of choices) {
    if (!c || typeof c !== 'object' || !Number.isInteger(c.n) || c.n < 1
      || typeof c.label !== 'string' || c.label.trim() === '') {
      return bad('every choice needs a whole number n and a label.');
    }
    if (numbers.has(c.n)) return bad('choice numbers must be unique.');
    numbers.add(c.n);
    cleanChoices.push({ n: c.n, label: c.label });
  }

  const files = b.files === undefined || b.files === null ? [] : b.files;
  if (!Array.isArray(files)) return bad('files must be a list.');
  if (files.length > MAX_APPROVAL_FILES) return bad(`at most ${MAX_APPROVAL_FILES} files.`);
  const names = new Set();
  const cleanFiles = [];
  for (const f of files) {
    if (!f || typeof f !== 'object') return bad('every file needs a name, type, size and digest.');
    if (!safeFileName(f.name)) {
      return bad('file names may use letters, digits, dot, dash and underscore, 1-80 characters.');
    }
    if (names.has(f.name)) return bad('file names must be unique.');
    names.add(f.name);
    if (typeof f.content_type !== 'string' || !/^(audio|image)\//.test(f.content_type)) {
      return bad('approval files must be audio or image.');
    }
    if (!Number.isSafeInteger(f.bytes) || f.bytes <= 0 || f.bytes > MAX_APPROVAL_FILE_BYTES) {
      return bad('each file must be a whole number of bytes, under 25 MB.');
    }
    if (typeof f.sha256 !== 'string' || !DIGEST_RE.test(f.sha256)) {
      return bad('every file needs its lowercase SHA-256 digest.');
    }
    cleanFiles.push({ name: f.name, content_type: f.content_type, bytes: f.bytes, sha256: f.sha256 });
  }

  return { ok: true, stage: b.stage, version, text: b.text, choices: cleanChoices, files: cleanFiles };
}

/**
 * The digest of one presentation: text, choices and every file declaration, in
 * the order the producer wrote them. Changing any of those makes a different
 * presentation, and a same-version publish with a different digest is refused.
 */
export async function presentationDigest(p) {
  const canonical = JSON.stringify({
    stage: p.stage,
    version: p.version,
    text: p.text,
    choices: p.choices.map((c) => [c.n, c.label]),
    files: p.files.map((f) => [f.name, f.content_type, f.bytes, f.sha256]),
  });
  return sha256Hex(new TextEncoder().encode(canonical));
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
  let raw;
  try {
    raw = await store.kvGet(`order:${clientId}:${orderId}`);
  } catch {
    throw new ApprovalStorageError('The order record could not be read.');
  }
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    throw new ApprovalStorageError('The order record could not be read.');
  }
}

function positiveVersion(raw) {
  const value = Number(raw);
  return Number.isInteger(value) && value >= 1 ? value : null;
}

/** The server-recorded decision envelope. Callers never supply its authority. */
function decisionEnvelope(record) {
  return {
    value: record.value,
    by: record.by,
    source: record.source,
    at: record.at,
    stage: record.stage,
    version: record.version,
    presentation_digest: record.presentation_digest,
    decision_id: record.decision_id,
  };
}

/** One item as the page and the box see it. */
function presentItem(manifest, orderId, decision, ready) {
  return {
    stage: manifest.stage,
    version: manifest.version,
    text: manifest.text,
    choices: manifest.choices,
    presentation_digest: manifest.presentation_digest,
    ready: Boolean(ready),
    files: (manifest.files || []).map((f) => ({
      name: f.name,
      url: ready ? exactFileRouteUrl(orderId, manifest.stage, manifest.version,
        manifest.presentation_digest, f.name) : null,
      content_type: f.content_type,
      bytes: f.bytes,
      sha256: f.sha256,
    })),
    answer: decision ? decisionEnvelope(decision) : null,
    created_at: manifest.created_at,
  };
}

/** Freeze every verified staging file, then create the ready manifest once. */
async function composeReady(bucket, clientId, orderId, intent, nowMs) {
  for (const file of intent.files) {
    const frozen = frozenPath(clientId, orderId, intent.stage, intent.version, file.name);
    const already = await readObject(bucket, frozen);
    if (already) {
      if (!(await objectMatches(already, file.bytes, file.sha256))) {
        return { ok: false, code: AF_APPROVAL_BYTES, message: `The stored copy of ${file.name} does not match the published item.` };
      }
      continue;
    }
    const staged = await readObject(bucket, stagingPath(clientId, orderId, intent.stage, intent.version, file.name));
    if (!staged) {
      return { ok: false, code: AF_APPROVAL_UPLOAD, message: `${file.name} has not finished uploading.` };
    }
    let bytes;
    try {
      bytes = await staged.arrayBuffer();
    } catch {
      // The body of a stored object could not be read. That is a storage
      // outage, not a missing or conflicting upload.
      throw new ApprovalStorageError(`The staged copy of ${file.name} could not be read.`);
    }
    if (!bytes || bytes.byteLength !== file.bytes) {
      return { ok: false, code: AF_APPROVAL_UPLOAD, message: `${file.name} is not the declared size.` };
    }
    if ((await sha256Hex(bytes)) !== file.sha256) {
      return { ok: false, code: AF_APPROVAL_UPLOAD, message: `${file.name} is not the declared bytes.` };
    }
    const frozenWrite = await putFrozen(bucket, frozen, bytes, file.content_type, file.sha256);
    if (frozenWrite.error) {
      return { ok: false, code: AF_APPROVAL_STORAGE, message: 'The approval store refused a file.' };
    }
    if (frozenWrite.exists && !(await objectMatches(await readObject(bucket, frozen), file.bytes, file.sha256))) {
      return { ok: false, code: AF_APPROVAL_BYTES, message: `The stored copy of ${file.name} does not match the published item.` };
    }
  }

  const manifest = {
    stage: intent.stage,
    version: intent.version,
    text: intent.text,
    choices: intent.choices,
    files: intent.files,
    presentation_digest: intent.presentation_digest,
    created_at: intent.created_at,
    finalized_at: nowMs,
  };
  const written = await createOnce(bucket, readyPath(clientId, orderId, intent.stage, intent.version), manifest);
  if (written.error) {
    return { ok: false, code: AF_APPROVAL_STORAGE, message: 'The approval store refused the ready record.' };
  }
  const committed = written.exists
    ? await readJson(bucket, readyPath(clientId, orderId, intent.stage, intent.version))
    : manifest;
  if (!committed) {
    return { ok: false, code: AF_APPROVAL_STORAGE, message: 'The ready record could not be read back.' };
  }
  return { ok: true, manifest: committed, created: Boolean(written.created) };
}

/**
 * The approvals routes. Returns null when the path or method is not one of
 * them, so the caller's own 404 still answers everything else.
 *
 * A failed storage read is an OUTCOME, not an exception: any read that could
 * not be completed answers 503 APPROVAL_STORAGE_UNAVAILABLE. It never becomes
 * an empty list or an unanswered card, which would be a false success.
 */
export async function approvalsRoute(request, ctx) {
  const c = ctx || {};
  const fail = typeof c.fail === 'function' ? c.fail : localFail;
  try {
    return await routeFor(request, c);
  } catch (err) {
    if (err && (err.name === 'ApprovalStorageError' || err.code === AF_APPROVAL_STORAGE)) {
      return fail(503, AF_APPROVAL_STORAGE,
        'Approval storage could not be read. Nothing was changed; try again shortly.');
    }
    throw err;
  }
}

async function routeFor(request, c) {
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
  const finalize = rest.length === 3 && rest[2] === 'finalize' && method === 'POST';
  // Old revisionless route: named, refusable, never searched for a basename.
  const legacyFile = rest.length === 3 && rest[1] === 'file' && method === 'GET';
  const exactFile = rest.length === 5 && rest[3] === 'file' && method === 'GET';
  if (!publish && !list && !answer && !finalize && !legacyFile && !exactFile) return null;

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
  if (!isClientId(clientId)) {
    // No scoped path can be built, so no route below may run.
    return fail(401, 'AF-DS-ID-INVALID', 'This key is not bound to a studio client id.');
  }

  const bucket = approvalBucket(env);
  const noStore = () => fail(503, AF_APPROVAL_STORAGE, 'Approval storage is not ready. Nothing was stored.');

  // -------------------------------------------------------------------------
  // Publish: create the immutable intent BEFORE minting any upload link.
  // -------------------------------------------------------------------------
  if (publish) {
    if (kind === 'link') return fail(403, AF_LINK_KIND, 'A link key cannot publish an approval.');
    if (kind !== 'machine' && kind !== 'box') return fail(403, AF_APPROVAL_KIND, 'That key cannot publish an approval.');
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    const check = validatePublish(body);
    if (!check.ok) return fail(400, check.code, check.message);
    if (!bucket) return noStore();

    const digest = await presentationDigest(check);
    const intent = {
      stage: check.stage,
      version: check.version,
      text: check.text,
      choices: check.choices,
      files: check.files,
      presentation_digest: digest,
      created_at: nowMs,
    };
    const written = await createOnce(bucket, intentPath(clientId, orderId, check.stage, check.version), intent);
    if (written.error) return noStore();

    let created = Boolean(written.created);
    let authoritative = intent;
    if (written.exists) {
      const existing = await readJson(bucket, intentPath(clientId, orderId, check.stage, check.version));
      if (!existing || typeof existing.presentation_digest !== 'string') return noStore();
      if (existing.presentation_digest !== digest) {
        return fail(409, AF_APPROVAL_REVISION,
          'That version is already published with different content. Publish a new version.');
      }
      authoritative = existing;
      created = false;
    }

    const ready = await readJson(bucket, readyPath(clientId, orderId, check.stage, check.version));
    if (ready) {
      const decision = await readJson(bucket, decisionPath(clientId, orderId, check.stage, check.version));
      return ok({ item: presentItem(ready, orderId, decision, true), created, ready: true, uploads: [] },
        created ? 201 : 200);
    }

    // Fileless presentations (a script, a brief) are ready as soon as they exist.
    if (authoritative.files.length === 0) {
      const composed = await composeReady(bucket, clientId, orderId, authoritative, nowMs);
      if (!composed.ok) return fail(503, composed.code, composed.message);
      return ok({ item: presentItem(composed.manifest, orderId, null, true), created, ready: true, uploads: [] },
        created ? 201 : 200);
    }

    // Only staging paths are ever presigned; frozen and authority objects never.
    const uploads = [];
    for (const file of authoritative.files) {
      const signed = await presignPut(env, stagingPath(clientId, orderId, check.stage, check.version, file.name), file.content_type);
      if (!signed.ok) return fail(503, AF_STORAGE, 'Upload storage is not ready. Try again shortly.');
      uploads.push({ name: file.name, url: signed.upload.url, method: 'PUT' });
    }
    return ok({ item: presentItem(authoritative, orderId, null, false), created, ready: false, uploads },
      created ? 201 : 200);
  }

  // -------------------------------------------------------------------------
  // List: only ready presentations are answerable.
  // -------------------------------------------------------------------------
  if (list) {
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    if (!bucket || typeof bucket.list !== 'function') return noStore();
    let manifests;
    try {
      manifests = await listReady(bucket, clientId, orderId);
    } catch {
      return noStore();
    }
    const items = [];
    for (const manifest of manifests) {
      const decision = await readJson(bucket, decisionPath(clientId, orderId, manifest.stage, manifest.version));
      items.push(presentItem(manifest, orderId, decision, true));
    }
    items.sort((a, b) => (STAGES.indexOf(a.stage) - STAGES.indexOf(b.stage)) || (a.version - b.version));
    return ok({ items });
  }

  // -------------------------------------------------------------------------
  // Answer: the link, and only the link. The winner is the first create.
  // -------------------------------------------------------------------------
  if (answer) {
    const stage = rest[0];
    if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
    if (kind !== 'link') {
      return fail(403, AF_APPROVAL_KIND, 'Only the client link may answer an approval.');
    }
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    const version = positiveVersion(body.version);
    if (version === null) return fail(400, AF_APPROVAL_BAD, 'version must be a positive integer.');
    const value = typeof body.value === 'number' ? String(body.value) : body.value;
    if (typeof value !== 'string' || value.trim() === '' || value.length > MAX_APPROVAL_TEXT) {
      return fail(400, AF_APPROVAL_BAD, 'value is required.');
    }
    if (!bucket) return noStore();

    const ready = await readJson(bucket, readyPath(clientId, orderId, stage, version));
    if (!ready) return fail(404, AF_APPROVAL_UNKNOWN, 'No such approval to answer.');
    if (body.presentation_digest !== undefined && body.presentation_digest !== ready.presentation_digest) {
      return fail(409, AF_APPROVAL_REVISION, 'That answer names a different presentation.');
    }

    const settled = await readJson(bucket, decisionPath(clientId, orderId, stage, version));
    if (settled) return fail(409, AF_APPROVAL_TAKEN, 'The first answer for this approval is already recorded.');

    const decisionId = `d_${(await sha256Hex(new TextEncoder().encode(
      `${clientId}:${orderId}:${stage}:${version}`))).slice(0, 32)}`;
    const record = {
      value,
      by: kind,
      source: 'link-capability',
      at: nowMs,
      stage,
      version,
      presentation_digest: ready.presentation_digest,
      decision_id: decisionId,
    };
    const written = await createOnce(bucket, decisionPath(clientId, orderId, stage, version), record);
    if (written.error) return noStore();
    if (written.exists) {
      // Another request won the race. Its record stands; this one is refused.
      return fail(409, AF_APPROVAL_TAKEN, 'The first answer for this approval is already recorded.');
    }
    return ok({ answer: decisionEnvelope(record) });
  }

  // -------------------------------------------------------------------------
  // Finalize: verify every staged file, then create the ready manifest once.
  // -------------------------------------------------------------------------
  if (finalize) {
    if (kind !== 'machine' && kind !== 'box') {
      return fail(403, AF_APPROVAL_KIND, 'That key cannot finalize an approval.');
    }
    const stage = rest[0];
    if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
    const version = positiveVersion(rest[1]);
    if (version === null) return fail(400, AF_APPROVAL_BAD, 'version must be a positive integer.');
    if (!(await requireOrder(store, clientId, orderId))) {
      return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
    }
    if (!bucket) return noStore();

    const ready = await readJson(bucket, readyPath(clientId, orderId, stage, version));
    if (ready) {
      const decision = await readJson(bucket, decisionPath(clientId, orderId, stage, version));
      return ok({ item: presentItem(ready, orderId, decision, true), ready: true, created: false });
    }
    const intent = await readJson(bucket, intentPath(clientId, orderId, stage, version));
    if (!intent) return fail(404, AF_APPROVAL_UNKNOWN, 'No such approval to finalize.');
    if (body.presentation_digest !== undefined && body.presentation_digest !== intent.presentation_digest) {
      return fail(409, AF_APPROVAL_REVISION, 'That finalize names a different presentation.');
    }
    const composed = await composeReady(bucket, clientId, orderId, intent, nowMs);
    if (!composed.ok) {
      // A store that refused a write is an outage (503); a file that is absent
      // or different is a conflict the producer can fix (409).
      const status = composed.code === AF_APPROVAL_STORAGE ? 503 : 409;
      return fail(status, composed.code, composed.message);
    }
    return ok({ item: presentItem(composed.manifest, orderId, null, true), ready: true, created: composed.created },
      composed.created ? 201 : 200);
  }

  // -------------------------------------------------------------------------
  // The revisionless route can no longer name bytes: refuse it by name.
  // -------------------------------------------------------------------------
  if (legacyFile) {
    const stage = rest[0];
    if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
    return fail(400, AF_REVISION_REQUIRED,
      'This approval link predates immutable revisions. Reload the card from the studio.');
  }

  // -------------------------------------------------------------------------
  // Exact media: stage + version + presentation digest + name, authenticated.
  // -------------------------------------------------------------------------
  const stage = rest[0];
  const version = positiveVersion(rest[1]);
  const digest = rest[2];
  const name = rest[4];
  if (!STAGES.includes(stage)) return fail(400, AF_APPROVAL_BAD, 'stage must be script, song or storyboard.');
  if (version === null) return fail(400, AF_APPROVAL_BAD, 'version must be a positive integer.');
  if (typeof digest !== 'string' || !DIGEST_RE.test(digest)) {
    return fail(400, AF_APPROVAL_BAD, 'The file URL must name the presentation digest.');
  }
  if (!safeFileName(name)) {
    return fail(400, AF_APPROVAL_BAD, 'file names may use letters, digits, dot, dash and underscore, 1-80 characters.');
  }
  if (!(await requireOrder(store, clientId, orderId))) {
    return fail(404, AF_ORDER_MISSING, 'No such order for this key.');
  }
  if (!bucket) return noStore();

  const ready = await readJson(bucket, readyPath(clientId, orderId, stage, version));
  if (!ready) return fail(404, AF_FILE_MISSING, 'No such approval file.');
  if (ready.presentation_digest !== digest) {
    return fail(409, AF_APPROVAL_REVISION, 'That link names a different presentation.');
  }
  const file = (ready.files || []).find((f) => f.name === name);
  if (!file) return fail(404, AF_FILE_MISSING, 'No such approval file.');

  const object = await readObject(bucket, frozenPath(clientId, orderId, stage, version, name));
  if (!object) return fail(404, AF_FILE_MISSING, 'No such approval file.');
  const size = typeof object.size === 'number' ? object.size : file.bytes;
  if (size !== file.bytes) {
    return fail(409, AF_APPROVAL_BYTES, 'The stored bytes do not match the published item.');
  }
  let bodyBytes = object.body || null;
  if (!bodyBytes) {
    try {
      bodyBytes = await object.arrayBuffer();
    } catch {
      return fail(503, AF_APPROVAL_STORAGE, 'Approval storage could not be read. Nothing was changed; try again shortly.');
    }
  }
  const headers = {
    'Content-Type': file.content_type,
    'Content-Length': String(file.bytes),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'X-DS-SHA256': file.sha256,
  };
  const etag = object.httpEtag || (typeof object.etag === 'string' ? `"${object.etag}"` : null);
  if (etag) headers.ETag = etag;
  return new Response(bodyBytes, { status: 200, headers });
}
