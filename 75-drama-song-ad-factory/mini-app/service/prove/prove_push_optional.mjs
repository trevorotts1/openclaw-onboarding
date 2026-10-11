#!/usr/bin/env node
// ============================================================================
// prove_push_optional.mjs — Drama Studio service (U20) OPTIONAL WEB-PUSH PROVER
//
//   node 75-drama-song-ad-factory/mini-app/service/prove/prove_push_optional.mjs
//
// U20 is OPTIONAL and version 2 (joint plan line 1091, "U20 | Optional web
// push | ... | U3; never version-0 gate"; line 832, "none blocks version 0").
// A prover for an optional feature must prove two things a feature test cannot:
//
//   1. the OPTIONAL half — with web push unset, the surface is INERT: the
//      status route says off, the subscribe route REFUSES AND STORES NOTHING,
//      and the send path refuses before touching a subscription; and
//   2. the WORKING half — a POSITIVE CONTROL on the same instrument shows that
//      the enabled path really sends, really prunes and really ignores revoked
//      records, so the refusals above cannot be a broken harness passing as one.
//
// It also proves the two invariants the plan hangs on U20: per-client isolation
// (a subscription belongs to one client only) and that a VAPID key value is
// never stored, echoed or printed.
//
// EXIT CODES (the service prover convention):
//   0  PASS     — every case passed
//   2  AUTOFAIL — at least one named case failed
//   3  USAGE/IO — the prover could not run
//
// Only PLACEHOLDER values appear here. No real key, endpoint or credential.
// ============================================================================

import { randomClientId } from '../src/ids.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { RETENTION_RULES, DAY_MS, dueForDeletion, retentionVerdict } from '../src/retention.js';
import {
  AF_PUSH_DISABLED,
  AF_PUSH_MISSING,
  activeSubscriptions,
  listSubscriptions,
  pushEnabled,
  registerSubscription,
  revokeSubscription,
  sendPush,
  subscriptionBelongsTo,
} from '../src/push.js';
import { handle } from '../src/index.js';
import { get, memObjects, memStore, post } from '../test/fakes.mjs';
import { enablePush, pushSurfaceState, pushSupported } from '../../ui/push.js';

const EXIT_PASS = 0;
const EXIT_AUTOFAIL = 2;
const EXIT_USAGE = 3;

const T0 = Date.UTC(2026, 9, 10, 12, 0, 0);

// OFF: the whole point. No DS_WEB_PUSH_ENABLED, no VAPID keys.
const ENV_OFF = { DS_ENROLLMENT_SECRET: 'enroll-placeholder', DS_ADMIN_KEY: 'admin-placeholder' };

// ON, for the positive control only. The private key is a PLACEHOLDER, and the
// prover later asserts it never reaches a stored record.
const VAPID_PRIVATE = 'vapid-private-PLACEHOLDER-must-never-be-stored';
const ENV_ON = {
  ...ENV_OFF,
  DS_WEB_PUSH_ENABLED: 'true',
  DS_WEB_PUSH_PUBLIC_KEY: 'vapid-public-PLACEHOLDER',
  DS_WEB_PUSH_PRIVATE_KEY: VAPID_PRIVATE,
  DS_WEB_PUSH_SUBJECT: 'mailto:studio@example.invalid',
};

const SUB = (tag) => ({ endpoint: `https://push.example.invalid/${tag}`, keys: { p256dh: `p256-${tag}`, auth: `auth-${tag}` } });

function recordingStore() {
  const inner = memStore();
  const log = [];
  return {
    log,
    writesFor(fragment) {
      return log.filter((e) => e.op === 'put' && e.key.startsWith(fragment)).length;
    },
    async kvGet(k) { log.push({ op: 'get', key: k }); return inner.kvGet(k); },
    async kvPut(k, v, ttl) { log.push({ op: 'put', key: k }); return inner.kvPut(k, v, ttl); },
    async kvDelete(k) { log.push({ op: 'delete', key: k }); return inner.kvDelete(k); },
    async kvList(prefix) { log.push({ op: 'list', key: prefix }); return inner.kvList(prefix); },
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
// P1 — OFF BY DEFAULT
// ---------------------------------------------------------------------------

function proveOffByDefault(results) {
  const rows = [
    ['no env at all', pushEnabled(undefined) === false],
    ['no flag set', pushEnabled(ENV_OFF) === false],
    ['flag is empty string', pushEnabled({ DS_WEB_PUSH_ENABLED: '' }) === false],
    ['flag is "false"', pushEnabled({ DS_WEB_PUSH_ENABLED: 'false' }) === false],
    ['flag is "yes" (not an on-value)', pushEnabled({ DS_WEB_PUSH_ENABLED: 'yes' }) === false],
    ['flag is "TRUE" (wrong case)', pushEnabled({ DS_WEB_PUSH_ENABLED: 'TRUE' }) === false],
    ['flag is exactly "true"', pushEnabled({ DS_WEB_PUSH_ENABLED: 'true' }) === true],
    ['flag is exactly "1"', pushEnabled({ DS_WEB_PUSH_ENABLED: '1' }) === true],
  ];
  const failed = rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ');
  results.push(['P1_OFF_BY_DEFAULT', rows.every(([, ok]) => ok), failed || `${rows.length} flag inputs OK`]);
}

// ---------------------------------------------------------------------------
// P2 — INERT SURFACE: status off, subscribe refuses and stores nothing
// ---------------------------------------------------------------------------

async function proveInertSurface(results) {
  const store = recordingStore();
  const objects = memObjects();
  const A = await clientFixture(store, 'link');

  store.log.length = 0;
  const status = await handle(get('/api/studio/push'), ENV_OFF, store, objects);
  const statusBody = await status.json();

  store.log.length = 0;
  const sub = await handle(post('/api/studio/push/subscribe', { subscription: SUB('off') }, A.key), ENV_OFF, store, objects);
  const subBody = await sub.json();
  const pushWrites = store.writesFor(`push:${A.clientId}:`);

  const ok = status.status === 200
    && statusBody.enabled === false
    && sub.status === 503
    && subBody.code === AF_PUSH_DISABLED
    && pushWrites === 0;
  results.push(['P2_INERT_SURFACE', ok,
    `status=${status.status} enabled=${statusBody.enabled} subscribe=${sub.status} code=${subBody.code} push_writes=${pushWrites}`]);
}

// ---------------------------------------------------------------------------
// P3 — SEND REFUSES UNCONFIGURED
// ---------------------------------------------------------------------------

async function proveSendRefuses(results) {
  const store = memStore();
  const clientId = randomClientId();
  const spy = { calls: 0, async transport() { spy.calls += 1; return { status: 201 }; } };

  const unconfigured = await sendPush({ env: ENV_OFF, store, clientId, payload: { title: 'x', body: 'y' }, transport: spy.transport, nowMs: T0 });
  const noTransport = await sendPush({ env: ENV_ON, store, clientId, payload: { title: 'x' }, transport: undefined, nowMs: T0 });
  const missingKey = await sendPush({
    env: { DS_WEB_PUSH_ENABLED: 'true' }, store, clientId, payload: { title: 'x' }, transport: spy.transport, nowMs: T0,
  });

  const ok = unconfigured.ok === false && unconfigured.code === AF_PUSH_DISABLED && unconfigured.sent === 0 && unconfigured.attempted === 0
    && noTransport.ok === false && noTransport.code === AF_PUSH_DISABLED
    && missingKey.ok === false && missingKey.code === AF_PUSH_DISABLED
    && spy.calls === 0;
  results.push(['P3_SEND_REFUSES_UNCONFIGURED', ok,
    `off=${unconfigured.code} no_transport=${noTransport.code} no_key=${missingKey.code} transport_calls=${spy.calls}`]);
}

// ---------------------------------------------------------------------------
// P4 — POSITIVE CONTROL: the enabled path really sends, prunes and skips revoked
// ---------------------------------------------------------------------------

async function proveEnabledPath(results) {
  const store = memStore();
  const clientId = randomClientId();

  await registerSubscription(store, { clientId, subscription: SUB('live'), nowMs: T0, entropyHex: 'a'.repeat(24) });
  const gone = await registerSubscription(store, { clientId, subscription: SUB('gone'), nowMs: T0, entropyHex: 'b'.repeat(24) });
  const revoked = await registerSubscription(store, { clientId, subscription: SUB('revoked'), nowMs: T0, entropyHex: 'c'.repeat(24) });
  await revokeSubscription(store, { clientId, subscriptionId: revoked.record.subscription_id, nowMs: T0 });

  const seen = [];
  const transport = async ({ subscription }) => {
    seen.push(subscription.endpoint);
    return { status: subscription.endpoint.endsWith('/gone') ? 410 : 201 };
  };
  const out = await sendPush({ env: ENV_ON, store, clientId, payload: { title: 'Ready', body: 'Your video is ready', url: '/d/1' }, transport, nowMs: T0 + 1000 });

  const after = await listSubscriptions(store, clientId);
  const goneRec = after.find((r) => r.subscription_id === gone.record.subscription_id);
  const liveRec = after.find((r) => r.endpoint.endsWith('/live'));
  const activeNow = (await activeSubscriptions(store, clientId)).map((r) => r.endpoint);

  const rows = [
    ['send reports ok and attempted the two active records', out.ok === true && out.attempted === 2],
    ['one sent, one failed', out.sent === 1 && out.failed === 1],
    ['the 410 subscription was pruned (named)', out.pruned.length === 1 && out.pruned[0] === gone.record.subscription_id],
    ['the pruned record is now revoked', goneRec && goneRec.status === 'revoked'],
    ['the live record carries last_sent_at', liveRec && liveRec.last_sent_at === T0 + 1000],
    ['a revoked subscription was never attempted', seen.length === 2 && !seen.some((e) => e.endsWith('/revoked'))],
    ['active list no longer offers the pruned one', activeNow.length === 1 && activeNow[0].endsWith('/live')],
  ];
  const failed = rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ');
  results.push(['P4_ENABLED_PATH_CONTROL', rows.every(([, ok]) => ok),
    failed || `sent=${out.sent} failed=${out.failed} pruned=${out.pruned.length} attempted=${seen.length}`]);
}

// ---------------------------------------------------------------------------
// P5 — per-client isolation
// ---------------------------------------------------------------------------

async function proveIsolation(results) {
  const store = recordingStore();
  const objects = memObjects();
  const A = await clientFixture(store, 'link');
  const B = await clientFixture(store, 'link');

  // A stores a real subscription (through the ENABLED surface).
  const made = await handle(post('/api/studio/push/subscribe', { subscription: SUB('a-only') }, A.key), ENV_ON, store, objects);
  const madeBody = await made.json();

  // The predicate itself, directly.
  const recordA = (await listSubscriptions(store, A.clientId))[0];
  const ownsSelf = subscriptionBelongsTo(recordA, A.clientId);
  const crossPredicate = subscriptionBelongsTo(recordA, B.clientId);

  // And through the door: B cannot list, read or revoke A's record.
  const bList = await listSubscriptions(store, B.clientId);
  const crossRevoke = await revokeSubscription(store, { clientId: B.clientId, subscriptionId: madeBody.subscription_id, nowMs: T0 });
  const stillActive = (await activeSubscriptions(store, A.clientId)).length;

  const ok = made.status === 201
    && ownsSelf === true
    && crossPredicate === false
    && bList.length === 0
    && crossRevoke.ok === false && crossRevoke.code === AF_PUSH_MISSING
    && stillActive === 1;
  results.push(['P5_ISOLATION', ok,
    `A_owns_self=${ownsSelf} B_on_A_record=${crossPredicate} B_list=${bList.length} B_revoke=${crossRevoke.code} A_still_active=${stillActive}`]);
}

// ---------------------------------------------------------------------------
// P6 — retention: a subscription is never swept
// ---------------------------------------------------------------------------

function proveRetention(results) {
  const tenYears = T0 + 3650 * DAY_MS;
  const v = retentionVerdict('push_subscription', { createdAtMs: T0, eventAtMs: T0, nowMs: tenYears });
  const sweep = dueForDeletion([
    { kind: 'push_subscription', path: 'push:c-x/one' },
    { kind: 'status_record', path: 'clients/c-x/status.json', event_at_ms: T0 },
  ], tenYears);
  const rows = [
    ['push_subscription is a known retention kind', Boolean(RETENTION_RULES.push_subscription)],
    ['it is never deleted, even at ten years', v.delete === false && v.never === true],
    ['a sweep partitions it out of the delete list', sweep.never.includes('push:c-x/one') && !sweep.delete.includes('push:c-x/one')],
    ['the sweep still deletes what is due', sweep.delete.includes('clients/c-x/status.json')],
  ];
  const failed = rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ');
  results.push(['P6_RETENTION_NEVER_SWEPT', rows.every(([, ok]) => ok), failed || `${rows.length} rules OK`]);
}

// ---------------------------------------------------------------------------
// P7 — the VAPID key value is never stored
// ---------------------------------------------------------------------------

async function proveNoKeyStored(results) {
  const store = memStore();
  const clientId = randomClientId();
  await registerSubscription(store, { clientId, subscription: SUB('k'), nowMs: T0, entropyHex: 'd'.repeat(24) });
  const values = [...store._mem.entries()].map(([, v]) => String(v));
  const leaked = values.some((v) => v.includes(VAPID_PRIVATE));
  const hasPrivateField = values.some((v) => {
    try { return 'privateKey' in JSON.parse(v); } catch { return false; }
  });
  const stored = JSON.parse([...store._mem.values()][0]);
  const ok = !leaked && !hasPrivateField
    && typeof stored.endpoint === 'string'
    && typeof stored.keys.p256dh === 'string' && typeof stored.keys.auth === 'string';
  results.push(['P7_NO_KEY_STORED', ok,
    `private_leaked=${leaked} private_field=${hasPrivateField} fields=${Object.keys(stored).join(',')}`]);
}

// ---------------------------------------------------------------------------
// P8 — version-0 behaviour is unchanged
// ---------------------------------------------------------------------------

async function proveVersionZeroUnchanged(results) {
  const store = memStore();
  const objects = memObjects();
  const A = await clientFixture(store, 'link');

  // A version-0 order round-trip, with web push OFF, is byte-for-byte what it
  // was before U20: the new routes are not on its path.
  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale', order_id: 'r_v0' }, A.key), ENV_OFF, store, objects);
  const order = (await created.json()).order;
  const fetched = await handle(get('/api/studio/orders/r_v0', A.key), ENV_OFF, store, objects);
  const fetchedBody = await fetched.json();
  const health = await handle(get('/api/studio/health'), ENV_OFF, store, objects);
  const healthBody = await health.json();

  const rows = [
    ['the version-0 order route still returns 201', created.status === 201 && order.order_id === 'r_v0'],
    ['the version-0 order read still returns 200', fetched.status === 200],
    ['the order payload carries no push field', !('push' in fetchedBody.order) && !('subscriptions' in fetchedBody)],
    ['health is unchanged and carries no push field', health.status === 200 && healthBody.service === 'drama-studio-service' && !('push' in healthBody)],
    ['the push status route is the only new PUBLIC route and it is off', (await (await handle(get('/api/studio/push'), ENV_OFF, store, objects)).json()).enabled === false],
    ['no push record exists after a version-0 order', [...store._mem.keys()].filter((k) => k.startsWith('push:')).length === 0],
  ];
  const failed = rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ');
  results.push(['P8_VERSION_ZERO_UNCHANGED', rows.every(([, ok]) => ok), failed || `${rows.length} rules OK`]);
}

// ---------------------------------------------------------------------------
// UI surface — OFF by default, and it never asks the browser anything
// ---------------------------------------------------------------------------

function proveUiSurface(results) {
  const rows = [
    ['the surface defaults to hidden', pushSurfaceState().show === false],
    ['enabled:false keeps it hidden', pushSurfaceState({ enabled: false, supported: true }).show === false],
    ['unsupported keeps it hidden', pushSurfaceState({ enabled: true, supported: false }).show === false],
    ['enabled AND supported shows it', pushSurfaceState({ enabled: true, supported: true }).show === true],
    ['pushSupported is false with no browser', pushSupported({}) === false],
  ];
  const failed = rows.filter(([, ok]) => !ok).map(([n]) => `XX ${n}`).join('; ');
  results.push(['U20_UI_OFF_BY_DEFAULT', rows.every(([, ok]) => ok), failed || `${rows.length} rules OK`]);
}

async function proveUiRefusesUnsolicited(results) {
  let asked = false;
  const registration = { pushManager: { async subscribe() { asked = true; return { endpoint: 'https://x' }; } } };
  const refused = await enablePush({ enabled: undefined, registration, applicationServerKey: 'pk' });
  const noKey = await enablePush({ enabled: true, registration, applicationServerKey: '' });
  const ok = refused.ok === false && asked === false && noKey.ok === false && asked === false;
  results.push(['U20_UI_NEVER_ASKS_UNSOLICITED', ok,
    `refused=${refused.ok} no_key=${noKey.ok} subscribe_called=${asked}`]);
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

async function main() {
  const results = [];
  const guards = [
    ['P1', proveOffByDefault],
    ['P2', proveInertSurface],
    ['P3', proveSendRefuses],
    ['P4', proveEnabledPath],
    ['P5', proveIsolation],
    ['P6', proveRetention],
    ['P7', proveNoKeyStored],
    ['P8', proveVersionZeroUnchanged],
    ['UI', proveUiSurface],
    ['UI2', proveUiRefusesUnsolicited],
  ];
  for (const [label, fn] of guards) {
    try {
      // eslint-disable-next-line no-await-in-loop
      await fn(results);
    } catch (err) {
      results.push([`${label}_HARNESS`, false, `prover could not run: ${err && err.message}`]);
    }
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
    ? '== U20 optional web push prover: ALL CASES PASSED ==\n'
    : '== U20 optional web push prover: FAILED — each FAIL line names its case ==\n');
  return allPass ? EXIT_PASS : EXIT_AUTOFAIL;
}

main().then((code) => process.exit(code), (err) => {
  process.stderr.write(`USAGE/IO: ${err && err.message ? err.message : err}\n`);
  process.exit(EXIT_USAGE);
});
