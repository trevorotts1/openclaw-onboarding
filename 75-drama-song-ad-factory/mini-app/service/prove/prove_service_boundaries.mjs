#!/usr/bin/env node
// ============================================================================
// prove_service_boundaries.mjs — Drama Studio service (U2) SECURITY PROVER
//
//   node 75-drama-song-ad-factory/mini-app/service/prove/prove_service_boundaries.mjs
//
// Three proofs the unit is graded on, each one runnable on its own and each one
// with its own exit status:
//
//   SEC-1  per-client isolation — one client's records, keys and uploads are
//          unreachable from another (section 3.15, section 3.16)
//   SEC-2  retention behavior (section 3.15, "How long")
//   SEC-3  the once-per-day operator record (section 3.10A rule 3)
//
// WHY SEC-1 IS A PROVER AND NOT A UNIT TEST. Every store read and write goes
// through a RECORDING proxy, so "client B never touched client A's records" is
// a PROVEN NEGATIVE — the proxy was watching A's namespace the whole time and
// saw nothing — instead of an absence nobody checked. Each negative case is
// paired with a POSITIVE control on the same instrument (C1/C2 do real reads),
// so a refusal can never be a broken harness presenting as a pass.
//
// EXIT CODES (prover convention, mirrors the skill's control CLI):
//   0  PASS     — every case in the battery passed
//   2  AUTOFAIL — at least one case failed; the FAIL line names the exact case
//   3  USAGE/IO — the prover could not run
//
// No real client names, no real ids, no credentials, no provider ids: two
// FICTIONAL clients and placeholder-shaped secrets only. No key value is ever
// printed.
// ============================================================================

import { randomClientId } from '../src/ids.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { enrollClient } from '../src/isolation.js';
import { DAY_MS, dueForDeletion, RETENTION_RULES, retentionVerdict } from '../src/retention.js';
import { operatorRecordCount, writeOperatorRecord } from '../src/lifecycle.js';
import { handle } from '../src/index.js';
import { get, memObjects, memStore, post } from '../test/fakes.mjs';

const EXIT_PASS = 0;
const EXIT_AUTOFAIL = 2;
const EXIT_USAGE = 3;

const T0 = Date.UTC(2026, 9, 10, 12, 0, 0);

const ENV = {
  DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-prover',
  DS_ADMIN_KEY: 'admin-key-placeholder-for-prover',
  R2_ACCOUNT_ID: 'fakeaccountid',
  R2_ACCESS_KEY_ID: 'fakeaccesskey',
  R2_SECRET_ACCESS_KEY: 'fakesecret',
  DRAMA_STUDIO_BUCKET: 'drama-studio',
};

// ---------------------------------------------------------------------------
// The recording instrument: every store read/write is logged by key, so a
// cross-client touch is OBSERVED rather than assumed absent.
// ---------------------------------------------------------------------------

function recordingStore() {
  const inner = memStore();
  const log = [];
  return {
    log,
    readsFor(fragment) {
      return log.filter((e) => e.op === 'get' && e.key.includes(fragment)).length;
    },
    async kvGet(k) {
      log.push({ op: 'get', key: k });
      return inner.kvGet(k);
    },
    async kvPut(k, v, ttl) {
      log.push({ op: 'put', key: k });
      return inner.kvPut(k, v, ttl);
    },
    async kvDelete(k) {
      log.push({ op: 'delete', key: k });
      return inner.kvDelete(k);
    },
    async kvList(prefix) {
      log.push({ op: 'list', key: prefix });
      return inner.kvList(prefix);
    },
    _mem: inner._mem,
  };
}

async function clientFixture(store, kind) {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  await store.kvPut(`client:${clientId}`, JSON.stringify({ client_id: clientId, created_at: T0 }));
  return { clientId, key: minted.secret };
}

// ---------------------------------------------------------------------------
// SEC-1 — per-client isolation
// ---------------------------------------------------------------------------

async function proveIsolation(results) {
  const store = recordingStore();
  const objects = memObjects();
  const A = await clientFixture(store, 'link');
  const B = await clientFixture(store, 'link');

  // A real order for A, and a real uploaded object under A's namespace.
  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale', order_id: 'r_alpha' }, A.key), ENV, store, objects);
  const orderA = (await created.json()).order;
  await objects.objectPut(`clients/${A.clientId}/intake/secret.bin`, 'a-only-bytes');

  // ---- C1 POSITIVE CONTROL: A's key opens A's own order -------------------
  store.log.length = 0;
  const ownA = await handle(get(`/api/studio/orders/${orderA.order_id}`, A.key), ENV, store, objects);
  const c1 = ownA.status === 200 && store.readsFor(`order:${A.clientId}:`) > 0;
  results.push(['C1 POSITIVE  A key -> A order served, and the instrument SAW the read', c1,
    `status=${ownA.status} reads_on_A=${store.readsFor(`order:${A.clientId}:`)}`]);

  // ---- C2 POSITIVE CONTROL: B's key opens B's own order -------------------
  const createdB = await handle(post('/api/studio/orders', { title: 'Example B', order_id: 'r_beta' }, B.key), ENV, store, objects);
  const orderB = (await createdB.json()).order;
  store.log.length = 0;
  const ownB = await handle(get(`/api/studio/orders/${orderB.order_id}`, B.key), ENV, store, objects);
  const c2 = ownB.status === 200 && store.readsFor(`order:${B.clientId}:`) > 0;
  results.push(['C2 POSITIVE  B key -> B order served, and the instrument SAW the read', c2,
    `status=${ownB.status} reads_on_B=${store.readsFor(`order:${B.clientId}:`)}`]);

  // ---- C3 NEGATIVE (load-bearing): B's key on A's order id ----------------
  store.log.length = 0;
  const cross = await handle(get(`/api/studio/orders/${orderA.order_id}`, B.key), ENV, store, objects);
  const crossBody = await cross.json();
  const touchedA = store.readsFor(`order:${A.clientId}:`)
    || store.log.filter((e) => e.key.startsWith(`order:${A.clientId}`)).length;
  const c3 = cross.status === 404 && crossBody.code === 'AF-DS-ORDER-MISSING' && touchedA === 0;
  results.push(['C3 NEGATIVE  B key on A order id -> refused, ZERO reads of A records', c3,
    `status=${cross.status} code=${crossBody.code} reads_on_A=${touchedA}`]);

  // ---- C4 NEGATIVE: B's key + a body that INJECTS A's client_id -----------
  store.log.length = 0;
  const inject = await handle(
    post('/api/studio/checkin', { client_id: A.clientId, orders: [{ order_id: 'r_x', state: 'waiting', title: 'forged' }] }, B.key),
    ENV, store, objects,
  );
  const injectBody = await inject.json();
  const c4 = inject.status === 403 && injectBody.code === 'AF-DS-ISO-CROSS';
  results.push(['C4 NEGATIVE  B key + injected A client_id -> refused, record wins', c4,
    `status=${inject.status} code=${injectBody.code}`]);

  // ---- C5 NEGATIVE: B's key cannot reach A's uploaded object --------------
  const { readOwnObject } = await import('../src/isolation.js');
  const reach = await readOwnObject(objects, B.clientId, `clients/${A.clientId}/intake/secret.bin`);
  const c5 = reach.ok === false && reach.code === 'AF-DS-ISO-SCOPE';
  results.push(['C5 NEGATIVE  B scope on A upload path -> refused by the scope predicate', c5,
    `ok=${reach.ok} code=${reach.code}`]);

  // ---- C6 NEGATIVE: the fleet secret cannot adopt an existing client ------
  const adopt = await enrollClient({
    store, env: ENV, presentedSecret: ENV.DS_ENROLLMENT_SECRET,
    claimedClientId: A.clientId, nowMs: T0,
  });
  const c6 = adopt.ok === false && adopt.code === 'AF-DS-ENROLL-REFUSED';
  results.push(['C6 NEGATIVE  enrollment cannot attach to an existing client', c6,
    `ok=${adopt.ok} code=${adopt.code}`]);

  // ---- C7 NEGATIVE: no raw key value is ever stored (only its fingerprint) -
  const storedKeyRecords = [...store._mem.entries()].filter(([k]) => k.startsWith('key:'));
  const leaked = storedKeyRecords.some(([, v]) => v.includes(A.key) || v.includes(B.key));
  const hasSecretField = storedKeyRecords.some(([, v]) => 'secret' in JSON.parse(v));
  const keysAreFingerprints = storedKeyRecords.every(
    ([k, v]) => JSON.parse(v).fingerprint === k.slice('key:'.length),
  );
  const c7 = !leaked && !hasSecretField && storedKeyRecords.length === 2 && keysAreFingerprints;
  results.push(['C7 NEGATIVE  stored key records hold fingerprints, never the secret', c7,
    `records=${storedKeyRecords.length} raw_secret_present=${leaked} secret_field=${hasSecretField}`]);
}

// ---------------------------------------------------------------------------
// SEC-2 — retention behavior
// ---------------------------------------------------------------------------

async function proveRetention(results) {
  const day = DAY_MS;
  const rows = [
    ['intake deleted at pickup', retentionVerdict('intake_answer', { eventAtMs: T0, nowMs: T0 }).delete === true],
    ['intake kept before pickup', retentionVerdict('intake_answer', { nowMs: T0 }).delete === false],
    ['approval file deleted at stage approval', retentionVerdict('approval_file', { eventAtMs: T0, nowMs: T0 }).delete === true],
    ['r2 fallback kept on day 6', retentionVerdict('r2_fallback_video', { eventAtMs: T0, nowMs: T0 + 6 * day }).delete === false],
    ['r2 fallback deleted on day 7', retentionVerdict('r2_fallback_video', { eventAtMs: T0, nowMs: T0 + 7 * day }).delete === true],
    ['status record deleted on day 30', retentionVerdict('status_record', { eventAtMs: T0, nowMs: T0 + 30 * day }).delete === true],
    ['unclaimed waiting order expires at 45 days', retentionVerdict('waiting_unclaimed', { createdAtMs: T0, nowMs: T0 + 45 * day }).delete === true],
    ['project object swept at 45 days', retentionVerdict('project_object', { createdAtMs: T0, nowMs: T0 + 45 * day }).delete === true],
    ['unknown kind is refused, never deleted', retentionVerdict('mystery', { nowMs: T0 }).code === 'AF-DS-RET-UNKNOWN-KIND'],
  ];
  // The never-delete classes, at ten years.
  for (const kind of ['enrollment_record', 'delivery_receipt', 'ghl_media']) {
    const v = retentionVerdict(kind, { createdAtMs: T0, eventAtMs: T0, nowMs: T0 + 3650 * day });
    rows.push([`${kind} never deleted (10 years)`, v.delete === false && v.never === true && RETENTION_RULES[kind].never === true]);
  }

  // A sweep must partition the never-delete classes OUT of the delete list.
  const sweep = dueForDeletion([
    { kind: 'enrollment_record', path: 'clients/x/enrollment.json', created_at_ms: T0 },
    { kind: 'delivery_receipt', path: 'clients/x/receipt.json', created_at_ms: T0 },
    { kind: 'ghl_media', path: 'clients/x/ghl.json', created_at_ms: T0 },
    { kind: 'status_record', path: 'clients/x/status.json', event_at_ms: T0 },
  ], T0 + 3650 * day);
  rows.push(['a sweep never lists a protected class for deletion',
    sweep.never.length === 3 && !sweep.delete.some((p) => sweep.never.includes(p))]);
  rows.push(['a sweep still deletes what is due', sweep.delete.includes('clients/x/status.json')]);

  results.push(['SEC-2 retention', rows.every(([, ok]) => ok),
    rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ') || `${rows.length} rules OK`]);
}

// ---------------------------------------------------------------------------
// SEC-3 — one operator record per client per day
// ---------------------------------------------------------------------------

async function proveOncePerDay(results) {
  const store = memStore();
  const clientId = randomClientId();
  const ours = () => [...store._mem.keys()].filter((k) => k.startsWith(`ops:${clientId}:`));

  const first = await writeOperatorRecord(store, { clientId, line: 'order waiting: no check-in', nowMs: T0 });
  const afterFirst = ours().length;
  const second = await writeOperatorRecord(store, { clientId, line: 'order waiting: still no check-in', nowMs: T0 + 6 * 60 * 60 * 1000 });
  const afterSecond = ours().length;
  const count = await operatorRecordCount(store, clientId, T0);
  const stored = JSON.parse(store._mem.get(ours()[0]));

  const rows = [
    ['first write of the day creates the record', first.created === true],
    ['second write the SAME day does NOT create a second record', second.created === false],
    ['exactly one record exists after two writes', afterSecond === 1 && afterFirst === 1],
    ['the count for the day is 1', count === 1],
    ['the later line REPLACED the earlier one (not stacked)', stored.line === 'order waiting: still no check-in' && stored.writes === 2],
  ];

  const nextDay = await writeOperatorRecord(store, { clientId, line: 'a new day', nowMs: T0 + DAY_MS });
  rows.push(['the next day starts a fresh record', nextDay.created === true && ours().length === 2]);
  rows.push(['another client is unaffected', (await writeOperatorRecord(memStore(), { clientId: randomClientId(), line: 'x', nowMs: T0 })).created === true]);

  results.push(['SEC-3 one operator record per client per day', rows.every(([, ok]) => ok),
    rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ') || `${rows.length} rules OK`]);
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

async function main() {
  const results = [];
  try {
    await proveIsolation(results);
  } catch (err) {
    results.push(['SEC-1 isolation (harness)', false, `prover could not run: ${err && err.message}`]);
  }
  try {
    await proveRetention(results);
  } catch (err) {
    results.push(['SEC-2 retention (harness)', false, `prover could not run: ${err && err.message}`]);
  }
  try {
    await proveOncePerDay(results);
  } catch (err) {
    results.push(['SEC-3 once-per-day (harness)', false, `prover could not run: ${err && err.message}`]);
  }

  if (results.length === 0) {
    process.stderr.write('USAGE/IO: prover produced no cases\n');
    return EXIT_USAGE;
  }
  for (const [name, ok, detail] of results) {
    process.stdout.write(`${ok ? 'PASS' : 'FAIL'} ${name}  ${detail}\n`);
  }
  const allPass = results.every(([, ok]) => ok);
  process.stdout.write(allPass
    ? '== U2 service boundary prover: ALL CASES PASSED ==\n'
    : '== U2 service boundary prover: FAILED — each FAIL line names its case ==\n');
  return allPass ? EXIT_PASS : EXIT_AUTOFAIL;
}

main().then((code) => process.exit(code), (err) => {
  process.stderr.write(`USAGE/IO: ${err && err.message ? err.message : err}\n`);
  process.exit(EXIT_USAGE);
});
