// agent-exchange-telemetry — passive capture of the native agent exchange path.
//
// Bound by (read, never guessed):
//   SPEC.md rev 4 §S5 "Exact supported native exchange path" (steps 1-6, outbox defaults)
//   evidence/contracts/capture-bindings.md (P03, frozen) — hook names, field names and
//   native status literals below are taken from that contract, which was verified
//   against the installed OpenClaw 2026.9.8 declarations and implementation.
//
// PASSIVE. Registers observers only: no tool replacement, no param edits, no new
// agents, no model changes, no dialogue synthesis, no gateway-core modification.
// Every hook body is wrapped: a telemetry failure is swallowed and can never
// block the underlying business call (S5 step 2: "Hook return is void").
//
// Privacy is structural, not cosmetic: text is attached to a record ONLY when
// ancestry is proven public, so a private/unknown text field cannot reach local
// persistence or the outbox because it was never built. See buildPayload().

'use strict';

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';

// ── Frozen contract constants ────────────────────────────────────────────
export const TOOL_MATCHER = ['sessions_send', 'sessions_spawn'];
export const TERMINAL_SUBSCRIPTION_ID = 'hq-exchange-terminal';
export const EXCHANGE_PHASES = ['requested', 'accepted', 'replied', 'failed', 'uncertain'];
/** Native statuses S7 accepts. Anything else is an unsupported-capture diagnostic. */
export const NATIVE_STATUSES = ['accepted', 'ok', 'timeout', 'error', 'forbidden', 'no_reply', 'queued', 'end'];
export const TARGET_DISPOSITIONS = ['queued', 'steered'];
export const CORRELATION_STATUSES = ['linked', 'unresolved', 'unsupported'];

/** S5 safe content: full captured exchange message 8,000 chars, summary 2,000. */
export const MESSAGE_MAX_CHARS = 8000;
const SUMMARY_MAX_CHARS = 2000;

/** S5 frozen pending-join bounds and S5 outbox bounds. */
export const BOUNDS = {
  maxEntries: 1000,
  maxBytes: 8 * 1024 * 1024,
  expiryMs: 24 * 60 * 60 * 1000,
  outboxMaxFiles: 1000,
  outboxMaxBytes: 8 * 1024 * 1024,
  outboxPayloadBytes: 128 * 1024,
};

// ── exchangeId: frozen length-prefixed SHA-256 tuple (capture-bindings §4) ──
// Tuple order is positional and fixed: installationId, callerSessionKey,
// callerRunId, toolCallId. Preimage per element: "<decimal byte length>:<utf8 bytes>",
// concatenated with no separator. Missing/empty element => NO exchangeId is
// minted (S5 step 1: missing identity records uncorrelated health, never guessed).
export function exchangePreimage(tuple) {
  let out = '';
  for (const element of tuple) {
    const value = typeof element === 'string' ? element : '';
    if (value === '') return null;
    out += `${Buffer.byteLength(value, 'utf8')}:${value}`;
  }
  return out;
}

export function mintExchangeId(tuple) {
  const preimage = exchangePreimage(tuple);
  if (preimage === null) return null;
  return createHash('sha256').update(preimage, 'utf8').digest('hex');
}

// ── S7 semantic hash: contentHash over the event only ────────────────────
// SPEC S7 line 293: "Semantic hash is SHA-256 of UTF-8 serialization of `event`
// only: lexicographically sorted ASCII keys at every object level; no extra
// whitespace; UTF-8 Unicode emitted directly; JSON control/quote/backslash
// escapes; reject lone surrogates, NaN, duplicate keys and non-integer numbers."
// Byte-identical to P01 `hqSemanticSerialize` (the receiver's own copy, which
// B07 route gate 9 recomputes with) and to Python
// `json.dumps(event,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)`.
function assertNoLoneSurrogate(text) {
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) throw new Error('semantic value contains a lone surrogate');
      i += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw new Error('semantic value contains a lone surrogate');
    }
  }
}

function semanticSerialize(value) {
  if (value === null) return 'null';
  if (typeof value === 'string') {
    assertNoLoneSurrogate(value);
    return JSON.stringify(value);
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('semantic value has a non-integer or unsafe number');
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(semanticSerialize).join(',')}]`;
  if (typeof value === 'object') {
    const parts = Object.keys(value)
      .sort()
      .map((key) => `${semanticSerialize(key)}:${semanticSerialize(value[key])}`);
    return `{${parts.join(',')}}`;
  }
  throw new Error(`semantic value has unsupported type ${typeof value}`);
}

/** Lowercase hex SHA-256 of the canonical event bytes (S7 line 293). */
function contentHashFor(event) {
  return createHash('sha256').update(semanticSerialize(event), 'utf8').digest('hex');
}

// ── Ancestry: private / public / unknown (S5 step 1 + step 5 transitivity) ──
// A direct `agent:*:hq-*` session is private, and private classification
// propagates transitively across spawned independent agent:<t>:subagent:* keys —
// the subagent key does not embed its parent, so lineage is carried by the
// observer's own parent->child edges (installed from proven accepted results).
// Unknown is NOT public: an unlisted session with no proven ancestor is unknown.

function isPrivateKey(sessionKey, extraPrivate) {
  if (typeof sessionKey !== 'string' || sessionKey === '') return false;
  if (extraPrivate.has(sessionKey)) return true;
  return sessionKey.split(':').some((segment) => segment === 'hq' || segment.startsWith('hq-'));
}

export function createAncestry(options = {}) {
  const { dir = null, maxEdges = 1000, privateSessionKeys = [], publicSessionKeys = [] } = options;
  const extraPrivate = new Set(privateSessionKeys);
  const publicKeys = new Set(publicSessionKeys);
  const edges = new Map(); // child -> parent
  let droppedEdges = 0;

  const file = dir ? path.join(dir, 'ancestry.json') : null;
  if (file) {
    try {
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
      for (const [child, parent] of Object.entries(parsed.edges ?? {})) edges.set(child, parent);
    } catch (_e) { /* no ancestry yet, or unreadable: start empty (unknown stays unknown) */ }
  }

  function save() {
    if (!file) return;
    try {
      atomicWrite(file, JSON.stringify({ v: 1, edges: Object.fromEntries(edges) }));
    } catch (_e) { /* telemetry may not break the call */ }
  }

  function link(parent, child) {
    if (typeof parent !== 'string' || !parent || typeof child !== 'string' || !child) return false;
    if (parent === child || edges.get(child) === parent) return false;
    if (edges.size >= maxEdges) {
      // Bounded: drop the oldest edge rather than grow without limit.
      const oldest = edges.keys().next().value;
      edges.delete(oldest);
      droppedEdges += 1;
    }
    edges.set(child, parent);
    save();
    return true;
  }

  function classify(sessionKey) {
    if (typeof sessionKey !== 'string' || sessionKey === '') return 'unknown';
    if (isPrivateKey(sessionKey, extraPrivate)) return 'private';
    // Walk the ancestor chain to a root; private anywhere wins, then public root.
    let node = sessionKey;
    let sawPublicRoot = false;
    for (let depth = 0; depth < 64; depth += 1) {
      if (isPrivateKey(node, extraPrivate)) return 'private';
      const parent = edges.get(node);
      if (parent === undefined) {
        if (publicKeys.has(node)) sawPublicRoot = true;
        break;
      }
      node = parent;
    }
    return sawPublicRoot ? 'public' : 'unknown';
  }

  return { classify, link, edges, droppedEdges: () => droppedEdges };
}

// ── Atomic write ─────────────────────────────────────────────────────────
function atomicWrite(file, data) {
  const tmp = `${file}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}

// ── Bounded durable correlation store (S5 step 5) ────────────────────────
// One JSON file per exchange, atomic rename. Reloaded from disk on construct, so
// a join survives a restart. While privacy is unproven a record holds
// identifiers / phase / timestamps only.
export function createCorrelationStore(options = {}) {
  const {
    dir,
    bounds = BOUNDS,
    now = Date.now,
    onExpiredUnknown = null,
  } = options;
  const records = new Map();
  const byTargetRun = new Map();
  let bytes = 0;
  const health = { dropped: 0, expired: 0, degraded: false, lastDegradedAt: null, expiredUnresolved: 0 };

  fs.mkdirSync(dir, { recursive: true });
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith('.json')) continue;
    try {
      const raw = fs.readFileSync(path.join(dir, name), 'utf8');
      const rec = JSON.parse(raw);
      if (!rec || typeof rec.exchangeId !== 'string') continue;
      records.set(rec.exchangeId, rec);
      bytes += Buffer.byteLength(raw, 'utf8');
      if (typeof rec.targetRunId === 'string' && rec.targetRunId) byTargetRun.set(rec.targetRunId, rec.exchangeId);
    } catch (_e) { /* unreadable record is not a fact about the exchange */ }
  }

  function markDegraded(reason) {
    health.degraded = true;
    health.lastDegradedAt = new Date(now()).toISOString();
    health.lastReason = reason;
  }

  function prune() {
    const cutoff = now() - bounds.expiryMs;
    for (const [id, rec] of records) {
      const updated = Date.parse(rec.updatedAt ?? rec.createdAt ?? 0) || 0;
      if (updated >= cutoff) continue;
      records.delete(id);
      if (rec.targetRunId && byTargetRun.get(rec.targetRunId) === id) byTargetRun.delete(rec.targetRunId);
      bytes -= Buffer.byteLength(JSON.stringify(rec), 'utf8');
      health.expired += 1;
      if (rec.privacy !== 'public') {
        // "If audience cannot be proved by expiry, emit a count-only degraded-capture diagnostic."
        health.expiredUnresolved += 1;
        markDegraded('audience-unproven-expiry');
        if (typeof onExpiredUnknown === 'function') onExpiredUnknown(rec);
      }
      try { fs.rmSync(path.join(dir, `${id}.json`), { force: true }); } catch (_e) { /* ignore */ }
    }
    if (bytes < 0) bytes = 0;
  }

  function get(exchangeId) {
    return records.get(exchangeId) ?? null;
  }

  function byRun(runId) {
    const id = typeof runId === 'string' ? byTargetRun.get(runId) : undefined;
    return id ? records.get(id) ?? null : null;
  }

  function put(rec) {
    prune();
    const serialized = JSON.stringify(rec);
    const size = Buffer.byteLength(serialized, 'utf8');
    const existing = records.get(rec.exchangeId);
    const delta = existing ? size - Buffer.byteLength(JSON.stringify(existing), 'utf8') : size;
    if (records.size + (existing ? 0 : 1) > bounds.maxEntries || bytes + delta > bounds.maxBytes) {
      // Overflow => coverage degraded, dropped count recorded. Never attribute
      // the nearest/latest text: the new record is simply not retained.
      health.dropped += 1;
      markDegraded('correlation-bounds');
      return { ok: false, reason: 'bounds' };
    }
    records.set(rec.exchangeId, rec);
    bytes += delta;
    if (typeof rec.targetRunId === 'string' && rec.targetRunId) byTargetRun.set(rec.targetRunId, rec.exchangeId);
    try {
      atomicWrite(path.join(dir, `${rec.exchangeId}.json`), serialized);
    } catch (_e) {
      health.dropped += 1;
      markDegraded('correlation-write');
      return { ok: false, reason: 'write' };
    }
    return { ok: true };
  }

  return {
    get, byRun, put, prune, records,
    size: () => records.size,
    byteSize: () => bytes,
    health,
  };
}

// ── Bounded local outbox (S5 outbox defaults, local half) ────────────────
// One JSON file per event, atomic rename, byte-checked before enqueue, bounded
// count and bytes, 24h expiry, degraded on overflow. Transport (retry/backoff/HTTP
// delivery to the Command Center address) is install wiring owned outside this
// unit; this file is the durable, sanitized boundary it will drain.
export function createOutbox(options = {}) {
  const { dir, bounds = BOUNDS, now = Date.now } = options;
  fs.mkdirSync(dir, { recursive: true });
  const health = { dropped: 0, duplicate: 0, conflicts: 0, expired: 0, degraded: false, lastDegradedAt: null };

  function markDegraded(reason) {
    health.degraded = true;
    health.lastDegradedAt = new Date(now()).toISOString();
    health.lastReason = reason;
  }

  function pending() {
    return fs.readdirSync(dir).filter((name) => name.endsWith('.json') && !name.endsWith('.diagnostic.json'));
  }

  function prune() {
    const cutoff = now() - bounds.expiryMs;
    let files = pending();
    let total = 0;
    for (const name of files) {
      const full = path.join(dir, name);
      let stat;
      try { stat = fs.statSync(full); } catch (_e) { continue; }
      if (stat.mtimeMs < cutoff) {
        try { fs.rmSync(full, { force: true }); health.expired += 1; } catch (_e) { /* ignore */ }
        continue;
      }
      total += stat.size;
    }
    return { count: pending().length, total };
  }

  function enqueue(envelope, slug) {
    const file = path.join(dir, `${slug}.json`);
    const serialized = JSON.stringify(envelope);
    const size = Buffer.byteLength(serialized, 'utf8');
    // Check encoded bytes, not string length.
    if (size > bounds.outboxPayloadBytes) {
      health.dropped += 1;
      markDegraded('outbox-payload-bytes');
      return 'dropped';
    }
    if (fs.existsSync(file)) {
      let prior = null;
      try { prior = fs.readFileSync(file, 'utf8'); } catch (_e) { /* ignore */ }
      if (prior === serialized) { health.duplicate += 1; return 'duplicate'; }
      // Same key / different content is a conflict recorded diagnostically, never an overwrite.
      health.conflicts += 1;
      markDegraded('source-key-conflict');
      diagnostic('source-key-conflict', { slug, at: new Date(now()).toISOString() });
      return 'conflict';
    }
    prune();
    const stats = pending();
    let total = 0;
    for (const name of stats) {
      try { total += fs.statSync(path.join(dir, name)).size; } catch (_e) { /* ignore */ }
    }
    if (stats.length + 1 > bounds.outboxMaxFiles || total + size > bounds.outboxMaxBytes) {
      health.dropped += 1;
      markDegraded('outbox-bounds');
      return 'dropped';
    }
    try {
      atomicWrite(file, serialized);
    } catch (_e) {
      health.dropped += 1;
      markDegraded('outbox-write');
      return 'dropped';
    }
    return 'written';
  }

  /** Count-only diagnostic. Never carries message or reply text. */
  function diagnostic(name, counts) {
    try {
      atomicWrite(path.join(dir, `${name}.diagnostic.json`), JSON.stringify({ v: 1, at: new Date(now()).toISOString(), ...counts }));
    } catch (_e) { /* ignore */ }
  }

  return { enqueue, prune, diagnostic, health, dir };
}

// ── Envelope construction (S7 shape: all keys present, null is not omission) ──
export function slugFor(exchangeId, phase) {
  return `exchange_${exchangeId}_${phase}`;
}

/** S5 safe content caps: message 8,000 chars, summary 2,000 (never split a surrogate pair). */
function clampText(value, maxChars) {
  if (value.length <= maxChars) return value;
  let end = maxChars;
  const last = value.charCodeAt(end - 1);
  if (last >= 0xd800 && last <= 0xdbff) end -= 1;
  return value.slice(0, end);
}

function buildPayload(rec, phase, extra) {
  // The privacy gate lives HERE, at the single construction point, so a
  // private/unknown text value cannot be persisted or enqueued by any caller.
  const visible = rec.privacy === 'public';
  return {
    message: visible && typeof extra.message === 'string' ? clampText(extra.message, MESSAGE_MAX_CHARS) : null,
    summary: visible && typeof extra.summary === 'string' ? clampText(extra.summary, SUMMARY_MAX_CHARS) : '',
    toolName: rec.toolName ?? null,
    toolCallId: rec.toolCallId ?? null,
    callerRunId: rec.callerRunId ?? null,
    targetRunId: rec.targetRunId ?? null,
    callerSessionKey: rec.callerSessionKey ?? null,
    targetSessionKey: rec.targetSessionKey ?? null,
    sourceHook: extra.sourceHook,
    nativeStatus: extra.nativeStatus ?? null,
    targetDisposition: rec.targetDisposition ?? null,
    correlationStatus: extra.correlationStatus ?? rec.correlationStatus ?? 'unresolved',
  };
}

function buildEvent(rec, phase, payload, meta) {
  return {
    eventId: meta.eventId,
    sourceKey: `exchange:${rec.exchangeId}:${phase}`,
    // S7 line 291: `phase` is a required event key (kinds/phases pairing).
    phase,
    installationId: rec.installationId ?? null,
    companyId: rec.companyId ?? null,
    issuedAt: meta.issuedAt,
    occurredAt: meta.occurredAt ?? null,
    kind: 'exchange',
    // The plugin sends run IDs; the server resolves taskId from the trusted
    // hq_run_bindings mapping (S5 step 6). Never inferred here, never invented.
    taskId: null,
    actorRuntimeId: rec.callerSessionKey ?? null,
    recipientRuntimeId: rec.targetSessionKey ?? null,
    fromWorkspaceId: null,
    toWorkspaceId: null,
    exchangeId: rec.exchangeId,
    payload,
  };
}

// ── Telemetry core ───────────────────────────────────────────────────────
export function createTelemetry(options = {}) {
  const {
    config = {},
    dir,
    outboxDir,
    bounds = BOUNDS,
    now = Date.now,
    logger = null,
    observeRunTerminal = null,
  } = options;

  const ancestry = createAncestry({
    dir,
    privateSessionKeys: Array.isArray(config.privateSessionKeys) ? config.privateSessionKeys : [],
    publicSessionKeys: Array.isArray(config.publicSessionKeys) ? config.publicSessionKeys : [],
  });

  const health = {
    uncorrelated: 0, // missing caller/run/tool-call identity: never a guessed sender
    unsupportedNative: 0,
    conflicts: 0,
    degraded: false,
    lastDegradedAt: null,
  };
  const markDegraded = (reason) => {
    health.degraded = true;
    health.lastDegradedAt = new Date(now()).toISOString();
    health.lastReason = reason;
  };

  const store = createCorrelationStore({
    dir,
    bounds,
    now,
    onExpiredUnknown: (rec) => {
      health.expiredUnresolved = (health.expiredUnresolved ?? 0) + 1;
      markDegraded('audience-unproven-expiry');
      outbox.diagnostic('degraded-capture', { reason: 'audience-unproven-expiry', exchangeId: rec.exchangeId, count: health.expiredUnresolved });
    },
  });
  const outbox = createOutbox({ dir: outboxDir, bounds, now });

  // Terminal events that arrive before their linking tool result. Metadata only:
  // IDs/phase/timestamps, never terminalReply.text while privacy is undiscovered.
  const orphanTerminals = new Map();

  const iso = (ms) => new Date(ms).toISOString();

  // Privacy only ever tightens: after the first resolution, a later, weaker
  // observation can never un-suppress text that an earlier one suppressed.
  const RANK = { private: 2, unknown: 1, public: 0 };
  function harden(rec, cls) {
    const next = RANK[cls] === undefined ? 'unknown' : cls;
    if (rec.privacy === null || rec.privacy === undefined) rec.privacy = next;
    else if (RANK[next] > RANK[rec.privacy]) rec.privacy = next;
    return rec.privacy;
  }

  function readIdentity(event, ctx, toolName) {
    const sessionKey = ctx?.sessionKey ?? event?.sessionKey ?? null;
    return {
      installationId: typeof config.installationId === 'string' ? config.installationId : null,
      callerSessionKey: typeof sessionKey === 'string' && sessionKey ? sessionKey : null,
      callerRunId: ctx?.runId ?? event?.runId ?? null,
      toolCallId: ctx?.toolCallId ?? event?.toolCallId ?? null,
      toolName,
    };
  }

  function newRecord(identity, exchangeId) {
    const at = iso(now());
    // While privacy is unproven: identifiers / phase / timestamps only.
    return {
      v: 1,
      exchangeId,
      installationId: identity.installationId,
      companyId: typeof config.companyId === 'string' ? config.companyId : null,
      toolName: identity.toolName,
      callerSessionKey: identity.callerSessionKey,
      callerRunId: identity.callerRunId,
      toolCallId: identity.toolCallId,
      targetRunId: null,
      targetSessionKey: null,
      nativeStatus: null,
      targetDisposition: null,
      // null = ancestry not yet resolved. Unknown is not public, so a null
      // privacy suppresses text exactly as 'unknown' does (buildPayload gate).
      privacy: null,
      correlationStatus: 'unresolved',
      phases: {},
      emits: {},
      conflicts: [],
      corroborations: [],
      createdAt: at,
      updatedAt: at,
    };
  }

  /**
   * Record one phase. The phase's source key is `exchange:<id>:<phase>`, and its
   * eventId/issuedAt are minted once and reused on every replay — including
   * across a restart — so retry/backfill of the same observation is byte-identical
   * and dedupes instead of minting a second envelope (S7: "Do not assign fresh
   * eventId/issuedAt while replaying same source key").
   *
   * A repeat of the same phase with different content is a conflict recorded
   * diagnostically, never an overwrite of the first envelope.
   */
  function emitPhase(rec, phase, extra) {
    const payload = buildPayload(rec, phase, extra);
    const fingerprint = JSON.stringify(payload);
    const prior = rec.emits[phase];
    // Only a comparable (non-suppressed) equal reply proves corroboration; the
    // text itself never enters the correlation store, only its hash.
    const replyHash = typeof payload.message === 'string'
      ? createHash('sha256').update(payload.message, 'utf8').digest('hex') : null;
    let meta;
    if (prior) {
      if (prior.fingerprint !== fingerprint) {
        // S5 line 184: a differing fingerprint is not automatically a conflict.
        // The synchronous result and the lifecycle terminal are different
        // sources for the SAME reply, so compare observed reply content across
        // sources first: equal = corroboration (no second payload), differing =
        // conflict diagnostic, never an overwrite.
        // Only a comparable (non-suppressed) equal reply PROVES corroboration
        // (S5 line 184): two nulls prove nothing, so that pair stays a conflict.
        if (phase === 'replied' && replyHash !== null && prior.replyHash === replyHash) {
          rec.corroborations.push({ phase, at: iso(now()), sourceHook: payload.sourceHook ?? null });
          persist(rec);
          return 'corroboration';
        }
        rec.conflicts.push({ phase, at: iso(now()), reason: 'same-phase-different-content' });
        health.conflicts += 1;
        markDegraded('same-phase-conflict');
        // "Conflict recorded diagnostically, never an overwrite" must survive a
        // restart, so the diagnostic is durable, not memory-only.
        persist(rec);
        return 'conflict';
      }
      meta = { eventId: prior.eventId, issuedAt: prior.issuedAt, occurredAt: rec.occurredAt ?? null };
    } else {
      const at = iso(now());
      meta = { eventId: randomUUID(), issuedAt: at, occurredAt: rec.occurredAt ?? null };
      rec.emits[phase] = { fingerprint, replyHash, eventId: meta.eventId, issuedAt: meta.issuedAt };
    }
    const event = buildEvent(rec, phase, payload, meta);
    // S7 line 291: the envelope carries schemaVersion, sentAt, event, contentHash.
    const envelope = { schemaVersion: 1, sentAt: meta.issuedAt, event, contentHash: contentHashFor(event) };
    // Durable identity first: a crash between this write and the outbox write
    // leaves a retry with the SAME bytes, which the outbox reports as duplicate.
    const persisted = store.put(rec);
    if (!persisted.ok) markDegraded(`correlation-${persisted.reason}`);
    const result = outbox.enqueue(envelope, slugFor(rec.exchangeId, phase));
    if (result === 'dropped') markDegraded('outbox-drop');
    return result;
  }

  function markPhase(rec, phase) {
    rec.phases[phase] = rec.phases[phase] ?? { at: iso(now()) };
    rec.updatedAt = iso(now());
  }

  function persist(rec) {
    const res = store.put(rec);
    if (!res.ok) markDegraded(`correlation-${res.reason}`);
    return res;
  }

  // ── Step 1-2: before_tool_call ────────────────────────────────────────
  function beforeToolCall(event = {}, ctx = {}) {
    try {
      const toolName = ctx.toolName ?? event.toolName;
      const identity = readIdentity(event, ctx, toolName);
      const exchangeId = mintExchangeId([
        identity.installationId,
        identity.callerSessionKey,
        identity.callerRunId,
        identity.toolCallId,
      ]);
      if (exchangeId === null) {
        // Missing caller/run/tool-call identity: uncorrelated capture health only.
        health.uncorrelated += 1;
        return { ok: false, reason: 'uncorrelated' };
      }
      let rec = store.get(exchangeId);
      if (rec === null) rec = newRecord(identity, exchangeId);
      // Resolve ancestry BEFORE any text persistence.
      const privacy = harden(rec, ancestry.classify(rec.callerSessionKey));
      const params = (event.params && typeof event.params === 'object') ? event.params : {};
      markPhase(rec, 'requested');
      persist(rec); // "Persist pending join before returning hook"
      emitPhase(rec, 'requested', {
        sourceHook: 'before_tool_call',
        nativeStatus: null,
        correlationStatus: 'unresolved',
        // params.message is the requested user-visible text; params.sessionKey /
        // label / agentId are REQUESTED target display only and never become
        // targetSessionKey (S5 step 1).
        message: typeof params.message === 'string' ? params.message : null,
        summary: typeof params.summary === 'string' ? params.summary : '',
      });
      return { ok: true, exchangeId, privacy };
    } catch (error) {
      try { logger?.warn?.(`[agent-exchange-telemetry] before_tool_call failed: ${String(error)}`); } catch (_e) { /* ignore */ }
      return { ok: false, reason: 'error' };
    }
  }

  // ── Step 3: after_tool_call ───────────────────────────────────────────
  function afterToolCall(event = {}, ctx = {}) {
    try {
      const toolName = ctx.toolName ?? event.toolName;
      const identity = readIdentity(event, ctx, toolName);
      const exchangeId = mintExchangeId([
        identity.installationId,
        identity.callerSessionKey,
        identity.callerRunId,
        identity.toolCallId,
      ]);
      if (exchangeId === null) {
        health.uncorrelated += 1;
        return { ok: false, reason: 'uncorrelated' };
      }
      let rec = store.get(exchangeId);
      if (rec === null) rec = newRecord(identity, exchangeId);
      // Same ancestry resolution the before-hook applies, so an after-only
      // arrival (result observed with no before) suppresses exactly the same way.
      harden(rec, ancestry.classify(rec.callerSessionKey));

      if (typeof event.error === 'string' && event.error) {
        rec.nativeStatus = 'error';
        markPhase(rec, 'failed');
        persist(rec);
        emitPhase(rec, 'failed', { sourceHook: 'after_tool_call', nativeStatus: 'error', correlationStatus: 'unresolved', message: null, summary: '' });
        return { ok: true, exchangeId, phase: 'failed' };
      }

      const result = event.result;
      const details = (result && typeof result === 'object' && result.details && typeof result.details === 'object' && !Array.isArray(result.details))
        ? result.details
        : null;
      if (details === null) {
        // Read from event.result.details, never .result.status. A sanitized text
        // copy that is not an object is an unsupported-capture diagnostic.
        health.unsupportedNative += 1;
        markDegraded('after-result-unreadable');
        return { ok: false, reason: 'no-details' };
      }

      const status = typeof details.status === 'string' ? details.status : null;
      if (status === null || !NATIVE_STATUSES.includes(status)) {
        health.unsupportedNative += 1;
        markDegraded('unsupported-native-status');
        return { ok: false, reason: 'unsupported-native-status' };
      }
      rec.nativeStatus = status;

      const targetRunId = typeof details.runId === 'string' && details.runId ? details.runId : null;
      const targetSessionKey = (typeof details.sessionKey === 'string' && details.sessionKey)
        ? details.sessionKey
        : ((typeof details.childSessionKey === 'string' && details.childSessionKey) ? details.childSessionKey : null);
      const disposition = TARGET_DISPOSITIONS.includes(details.targetDisposition) ? details.targetDisposition : null;
      rec.targetDisposition = disposition;

      if (status === 'ok' && typeof details.reply === 'string') {
        // A synchronous completed send returns the real reply.
        rec.targetRunId = targetRunId ?? rec.targetRunId;
        rec.targetSessionKey = targetSessionKey ?? rec.targetSessionKey;
        rec.correlationStatus = 'linked';
        rec.replyState = 'returned';
        // "Reply generated" is the strongest label a lifecycle event can prove;
        // only this synchronous return (or a separate delivery receipt) proves a
        // reply was returned to the caller. Neither is recorded as delivered.
        rec.delivered = false;
        markPhase(rec, 'replied');
        linkTargetAncestry(rec);
        if (rec.targetSessionKey) harden(rec, ancestry.classify(rec.targetSessionKey));
        persist(rec);
        emitPhase(rec, 'replied', {
          sourceHook: 'after_tool_call',
          nativeStatus: 'ok',
          correlationStatus: 'linked',
          message: details.reply,
          summary: '',
        });
        return { ok: true, exchangeId, phase: 'replied' };
      }

      if (status === 'accepted' && disposition === 'steered') {
        // The returned runId may be the send-operation id, not a receiver run
        // (capture-bindings F-4): uncertain, never joined.
        rec.correlationStatus = 'unresolved';
        rec.targetRunId = null;
        rec.targetSessionKey = null;
        rec.replyState = 'unobserved';
        markPhase(rec, 'uncertain');
        persist(rec);
        emitPhase(rec, 'uncertain', { sourceHook: 'after_tool_call', nativeStatus: 'accepted', correlationStatus: 'unresolved', message: null, summary: '' });
        return { ok: true, exchangeId, phase: 'uncertain' };
      }

      if (status === 'accepted') {
        // Admission only: not proof a worker executes, but the returned runId
        // binds the receiver run for a queued followup send or a native spawn.
        rec.targetRunId = targetRunId;
        rec.targetSessionKey = targetSessionKey;
        rec.correlationStatus = targetRunId ? 'linked' : 'unresolved';
        markPhase(rec, 'accepted');
        linkTargetAncestry(rec);
        if (rec.targetSessionKey) {
          // Inherit the caller's proven classification to the exact returned
          // target; a child that calls tools before linkage stays unclassified.
          harden(rec, ancestry.classify(rec.targetSessionKey));
        }
        persist(rec);
        emitPhase(rec, 'accepted', {
          sourceHook: 'after_tool_call',
          nativeStatus: 'accepted',
          correlationStatus: rec.correlationStatus,
          message: null,
          summary: '',
        });
        resolveOrphanTerminal(rec);
        return { ok: true, exchangeId, phase: 'accepted' };
      }

      if (status === 'queued') {
        // Notify-only path (runStarted:false): no run id, so no join is possible
        // and none is fabricated.
        rec.correlationStatus = 'unsupported';
        rec.targetRunId = null;
        markPhase(rec, 'accepted');
        persist(rec);
        emitPhase(rec, 'accepted', { sourceHook: 'after_tool_call', nativeStatus: 'queued', correlationStatus: 'unsupported', message: null, summary: '' });
        return { ok: true, exchangeId, phase: 'accepted' };
      }

      if (status === 'timeout' || status === 'error' || status === 'forbidden') {
        const uncertain = details.sentBeforeError === true;
        rec.correlationStatus = 'unresolved';
        rec.replyState = uncertain ? 'unobserved' : rec.replyState ?? null;
        markPhase(rec, uncertain ? 'uncertain' : 'failed');
        persist(rec);
        emitPhase(rec, uncertain ? 'uncertain' : 'failed', {
          sourceHook: 'after_tool_call',
          nativeStatus: status,
          correlationStatus: 'unresolved',
          message: null,
          summary: '',
        });
        return { ok: true, exchangeId, phase: uncertain ? 'uncertain' : 'failed' };
      }

      // no_reply and any other accepted native value: outcome unobserved, no text.
      rec.correlationStatus = 'unresolved';
      rec.replyState = 'unobserved';
      markPhase(rec, status === 'no_reply' ? 'uncertain' : 'accepted');
      persist(rec);
      emitPhase(rec, status === 'no_reply' ? 'uncertain' : 'accepted', {
        sourceHook: 'after_tool_call',
        nativeStatus: status,
        correlationStatus: 'unresolved',
        message: null,
        summary: '',
      });
      return { ok: true, exchangeId, phase: status };
    } catch (error) {
      try { logger?.warn?.(`[agent-exchange-telemetry] after_tool_call failed: ${String(error)}`); } catch (_e) { /* ignore */ }
      return { ok: false, reason: 'error' };
    }
  }

  function linkTargetAncestry(rec) {
    if (rec.targetSessionKey && rec.callerSessionKey) {
      ancestry.link(rec.callerSessionKey, rec.targetSessionKey);
    }
  }

  // ── Step 4-5: run-scoped terminal subscription ────────────────────────
  function handleAgentEvent(event = {}) {
    try {
      if (event.stream !== 'lifecycle') return { ok: false, reason: 'not-lifecycle' };
      const data = (event.data && typeof event.data === 'object') ? event.data : {};
      const terminal = data.phase === 'end' || data.phase === 'error';
      if (!terminal) return { ok: false, reason: 'not-terminal' };
      if (data.executionSettled !== true) return { ok: false, reason: 'not-settled' }; // `finishing` never settles
      const runId = typeof event.runId === 'string' ? event.runId : null;
      if (!runId) return { ok: false, reason: 'no-run' };

      const rec = store.byRun(runId);
      if (rec === null) {
        // Terminal before its linking tool result. Metadata only: IDs/phase/
        // timestamps, no text while privacy is undiscovered.
        if (orphanTerminals.size >= bounds.maxEntries) {
          const oldest = orphanTerminals.keys().next().value;
          orphanTerminals.delete(oldest);
          markDegraded('orphan-terminal-bounds');
        }
        orphanTerminals.set(runId, {
          runId,
          sessionKey: typeof event.sessionKey === 'string' ? event.sessionKey : null,
          agentId: typeof event.agentId === 'string' ? event.agentId : null,
          phase: data.phase,
          at: iso(now()),
        });
        return { ok: true, orphan: true, runId };
      }
      return settleTerminal(rec, event, data);
    } catch (error) {
      try { logger?.warn?.(`[agent-exchange-telemetry] lifecycle handler failed: ${String(error)}`); } catch (_e) { /* ignore */ }
      return { ok: false, reason: 'error' };
    }
  }

  function settleTerminal(rec, event, data, observedReply) {
    // Verified receiver identity: a mismatched session is not a join.
    const eventSessionKey = typeof event.sessionKey === 'string' ? event.sessionKey : null;
    if (rec.targetSessionKey && eventSessionKey && rec.targetSessionKey !== eventSessionKey) {
      rec.conflicts.push({ phase: 'replied', at: iso(now()), reason: 'receiver-session-mismatch' });
      health.conflicts += 1;
      markDegraded('receiver-mismatch');
      persist(rec);
      return { ok: false, reason: 'receiver-mismatch' };
    }

    const snapshot = observedReply ?? data.terminalReply;
    const visible = snapshot && snapshot.disposition === 'visible' && typeof snapshot.text === 'string';

    if (rec.privacy !== 'public') {
      // Private or unclassified ancestry: never persist terminalReply.text.
      if (visible) rec.replyState = rec.replyState ?? 'suppressed';
      markPhase(rec, 'replied');
      rec.correlationStatus = 'linked';
      rec.nativeStatus = 'end';
      persist(rec);
      emitPhase(rec, 'replied', {
        sourceHook: 'lifecycle',
        nativeStatus: 'end',
        correlationStatus: 'linked',
        message: null, // structurally stripped by buildPayload
        summary: '',
      });
      return { ok: true, exchangeId: rec.exchangeId, suppressed: true };
    }

    if (visible) {
      // Reply generation proven; this is NOT proof of parent consumption or
      // owner delivery, so it is recorded as generated, never delivered.
      rec.replyState = rec.replyState === 'returned' ? 'returned' : 'generated';
      rec.delivered = false;
      markPhase(rec, 'replied');
      rec.correlationStatus = 'linked';
      rec.nativeStatus = 'end';
      persist(rec);
      const outcome = emitPhase(rec, 'replied', {
        sourceHook: 'lifecycle',
        nativeStatus: 'end',
        correlationStatus: 'linked',
        message: snapshot.text,
        summary: '',
      });
      return { ok: true, exchangeId: rec.exchangeId, outcome };
    }

    rec.replyState = rec.replyState ?? 'unobserved';
    rec.nativeStatus = 'end';
    markPhase(rec, 'replied');
    rec.correlationStatus = 'linked';
    persist(rec);
    emitPhase(rec, 'replied', { sourceHook: 'lifecycle', nativeStatus: 'end', correlationStatus: 'linked', message: null, summary: '' });
    return { ok: true, exchangeId: rec.exchangeId, outcome: 'unobserved' };
  }

  function resolveOrphanTerminal(rec) {
    if (!rec.targetRunId) return null;
    const orphan = orphanTerminals.get(rec.targetRunId);
    if (!orphan) return null;
    orphanTerminals.delete(rec.targetRunId);
    if (rec.correlationStatus !== 'linked') return null;
    let observed = null;
    // Public ancestry proved only now: recover the exact run receipt through the
    // supported run-specific observation seam when one is wired; otherwise mark
    // reply-unobserved rather than save possibly private text.
    if (rec.privacy === 'public' && typeof observeRunTerminal === 'function') {
      try {
        const snapshot = observeRunTerminal(rec.targetRunId);
        if (snapshot && snapshot.disposition === 'visible' && typeof snapshot.text === 'string') {
          observed = { disposition: 'visible', text: snapshot.text };
        }
      } catch (_e) { observed = null; }
    }
    return settleTerminal(rec, {
      sessionKey: orphan.sessionKey,
      agentId: orphan.agentId,
    }, { phase: orphan.phase, executionSettled: true }, observed);
  }

  return {
    beforeToolCall,
    afterToolCall,
    handleAgentEvent,
    resolveOrphanTerminal,
    health,
    ancestry,
    store,
    outbox,
    records: () => Array.from(store.records.values()),
  };
}

// ── Registration ─────────────────────────────────────────────────────────
function resolveWorkspace(config, api) {
  if (typeof config.workspaceDir === 'string' && config.workspaceDir) return config.workspaceDir;
  if (typeof api?.rootDir === 'string' && api.rootDir) return api.rootDir;
  return path.join(os.homedir(), '.openclaw', 'workspace');
}

export function register(api) {
  const config = (api && api.pluginConfig && typeof api.pluginConfig === 'object') ? api.pluginConfig : {};
  if (config.enabled === false) return null;
  const base = resolveWorkspace(config, api);
  const logger = api?.logger ?? null;
  const telemetry = createTelemetry({
    config,
    logger,
    dir: path.join(base, 'hq-telemetry', 'correlation'),
    outboxDir: path.join(base, 'hq-telemetry', 'outbox'),
    observeRunTerminal: typeof config.observeRunTerminal === 'function' ? config.observeRunTerminal : null,
  });

  api.on('before_tool_call', (event, ctx) => { telemetry.beforeToolCall(event, ctx); }, { matcher: TOOL_MATCHER });
  api.on('after_tool_call', (event, ctx) => { telemetry.afterToolCall(event, ctx); }, { matcher: TOOL_MATCHER });
  try {
    api.agent.events.registerAgentEventSubscription({
      id: TERMINAL_SUBSCRIPTION_ID,
      description: 'Passive Headquarters exchange terminal observer (reply generation proof).',
      streams: ['lifecycle'],
      handle: (event) => { telemetry.handleAgentEvent(event); },
    });
  } catch (error) {
    try { logger?.warn?.(`[agent-exchange-telemetry] terminal subscription failed: ${String(error)}`); } catch (_e) { /* ignore */ }
  }
  return telemetry;
}

export default (api) => {
  try {
    return register(api);
  } catch (error) {
    try { api?.logger?.error?.(`[agent-exchange-telemetry] registration failed: ${String(error)}`); } catch (_e) { /* ignore */ }
    return null;
  }
};
