/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN
 * prove/prove_pairing_guardrails.mjs
 * -----------------------------------------------------------------------------
 * Drives the LIVE U2 service (75-drama-song-ad-factory/mini-app/service/) with
 * real requests through its own `handle()` and an injected in-memory store, and
 * refuses to pass on anything it has not seen refused.
 *
 *   (a) Option 3 is refused without a well-formed approval, and refused when
 *       the approval is present but malformed — with a PLANTED DEFECT run that
 *       proves the check can go red.
 *   (b) A pairing code is single-use: the second use of the same code is
 *       refused, with a planted-defect run on the burn.
 *   (c) A wrong or absent admin_key is refused with the service's own stable
 *       code — never a silent success — with a planted-defect run.
 *   (d) No key value is printed anywhere: no request path carries a query
 *       string, `keyLabel` shares no run of the key, no response body in the
 *       whole run contains a key, and the shipped sources persist nothing.
 *
 * Every check has a POSITIVE CONTROL on the same instrument (the same route,
 * same store shape, same request builder), because a 403 is only meaningful
 * when a 200 is reachable on the same path.
 *
 * exit 0 = every check passed, 2 = a named check failed, 3 = the prover could
 * not run (a missing service file, a crash). A planted-defect run that FAILS to
 * go red is itself a exit-2 failure: that is a vacuous check, not a pass.
 * ========================================================================== */

'use strict';

import { mkdtempSync, cpSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const PAIRING_DIR = dirname(HERE);
const SERVICE_DIR = join(PAIRING_DIR, '..', 'service');

// Test fixtures, not secrets: they exist only inside this process.
const ADMIN = 'fixture-admin-key-not-a-real-secret-000000';
const ENROLLMENT = 'fixture-enrollment-secret-not-a-real-secret';

const seenBodies = [];
const results = [];

function check(id, ok, detail) {
  results.push({ id, ok, detail });
  process.stdout.write((ok ? 'PASS ' : 'FAIL ') + id + '  ' + detail + '\n');
}

// ---------------------------------------------------------------------------
// Loading the live service, and copies of it with defects planted
// ---------------------------------------------------------------------------

async function loadService(srcDir) {
  return import(pathToFileURL(join(srcDir, 'index.js')).href);
}

const fakes = await import(pathToFileURL(join(SERVICE_DIR, 'test', 'fakes.mjs')).href);
const { memStore, memObjects, post, get } = fakes;

/** A copy of the service with one line surgically replaced. */
function plantedCopy(replacements) {
  const dir = mkdtempSync('/tmp/trevor-macmini-U12-U1-planted-');
  cpSync(join(SERVICE_DIR, 'src'), join(dir, 'src'), { recursive: true });
  for (const [file, from, to] of replacements) {
    const p = join(dir, 'src', file);
    const text = readFileSync(p, 'utf8');
    if (!text.includes(from)) throw new Error('planted defect could not find its anchor in ' + file);
    writeFileSync(p, text.split(from).join(to));
  }
  return dir;
}

async function drive(mod, request, store) {
  const res = await mod.handle(request, { DS_ADMIN_KEY: ADMIN, DS_ENROLLMENT_SECRET: ENROLLMENT }, store, memObjects());
  const text = await res.text();
  seenBodies.push(text);
  let json = null;
  try { json = JSON.parse(text); } catch { json = null; }
  return { status: res.status, json: json, text: text };
}

// ---------------------------------------------------------------------------
// The checks, written once and run against both the live service and a copy
// with a defect planted — that is what makes them non-vacuous.
// ---------------------------------------------------------------------------

/** (a) Option 3 without a well-formed approval is refused. */
async function option3Refused(mod) {
  const store = memStore();
  const target = 'c_' + 'a'.repeat(32);
  const malformed = [
    undefined,
    {},
    { option3: true },
    { client_name: 'Ann Example' },
    { option3: 'true', client_name: 'Ann Example' },
    { option3: true, client_name: '' },
    { option3: true, client_name: 123 },
    { option3: 1, client_name: 'Ann Example' },
  ];
  for (const approval of malformed) {
    const body = { admin_key: ADMIN, target_client_id: target, option: 3 };
    if (approval !== undefined) body.approval = approval;
    const res = await drive(mod, post('/api/studio/options', body), store);
    if (!(res.status === 403 && res.json && res.json.ok === false && res.json.code === 'AF-DS-OPT-APPROVAL')) {
      return { ok: false, detail: 'approval ' + JSON.stringify(approval) + ' answered ' + res.status + ' ' + res.text };
    }
  }
  return { ok: true, detail: malformed.length + ' malformed approvals all refused 403 AF-DS-OPT-APPROVAL' };
}

/** (a) positive control — the same route with a well-formed approval succeeds. */
async function option3AcceptedWithApproval(mod) {
  const store = memStore();
  const target = 'c_' + 'b'.repeat(32);
  const res = await drive(
    mod,
    post('/api/studio/options', {
      admin_key: ADMIN,
      target_client_id: target,
      option: 3,
      approval: { option3: true, client_name: 'Ann Example' },
    }),
    store,
  );
  if (!(res.status === 200 && res.json && res.json.ok === true && res.json.option === 3)) {
    return { ok: false, detail: 'well-formed approval answered ' + res.status + ' ' + res.text };
  }
  const stored = store._mem.get('client:' + target);
  if (!stored || JSON.parse(stored).option !== 3) {
    return { ok: false, detail: 'option 3 was accepted but not stored' };
  }
  return { ok: true, detail: '200, option 3 stored, line "' + res.json.line + '"' };
}

/** (a) a plain option never needs an approval — the gate is not refusing all. */
async function option2Accepted(mod) {
  const store = memStore();
  const res = await drive(mod, post('/api/studio/options', { admin_key: ADMIN, target_client_id: 'c_' + 'c'.repeat(32), option: 2 }), store);
  if (!(res.status === 200 && res.json.ok === true && res.json.option === 2)) {
    return { ok: false, detail: 'option 2 answered ' + res.status + ' ' + res.text };
  }
  return { ok: true, detail: '200, option 2 set with no approval' };
}

/** (b) a pairing code is single use. */
async function pairingCodeIsSingleUse(mod) {
  const store = memStore();
  const minted = await drive(mod, post('/api/studio/admin/pairing-code', { admin_key: ADMIN, client_id: 'c_' + 'd'.repeat(32) }), store);
  if (!(minted.status === 201 && minted.json.ok === true && typeof minted.json.code === 'string')) {
    return { ok: false, detail: 'mint answered ' + minted.status + ' ' + minted.text };
  }
  const code = minted.json.code;
  if (!/^[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(code)) {
    return { ok: false, detail: 'minted code "' + code + '" is not ABCD-2345 shaped' };
  }

  const first = await drive(mod, post('/api/studio/pair', { code: code, computer_name: 'office-mac' }), store);
  if (!(first.status === 201 && first.json.ok === true && typeof first.json.key === 'string')) {
    return { ok: false, detail: 'first pair answered ' + first.status + ' ' + first.text };
  }

  const second = await drive(mod, post('/api/studio/pair', { code: code, computer_name: 'office-mac' }), store);
  if (!(second.status === 403 && second.json.ok === false && second.json.code === 'AF-DS-PAIR-UNKNOWN')) {
    return { ok: false, detail: 'second use of the same code answered ' + second.status + ' ' + second.text };
  }

  const leftovers = [...store._mem.keys()].filter((k) => k.startsWith('pair:'));
  if (leftovers.length !== 0) {
    return { ok: false, detail: 'the pairing record survived the burn: ' + leftovers.join(',') };
  }
  return { ok: true, detail: 'code burned on first use; second use 403 AF-DS-PAIR-UNKNOWN; no pair: record left' };
}

/** (b) positive control — a FRESH code still pairs. */
async function freshCodeStillPairs(mod) {
  const store = memStore();
  const minted = await drive(mod, post('/api/studio/admin/pairing-code', { admin_key: ADMIN, client_id: 'c_' + 'e'.repeat(32) }), store);
  const res = await drive(mod, post('/api/studio/pair', { code: minted.json.code }), store);
  if (!(res.status === 201 && res.json.ok === true)) {
    return { ok: false, detail: 'a fresh code answered ' + res.status + ' ' + res.text };
  }
  return { ok: true, detail: '201 on a fresh code' };
}

/** (c) a wrong or absent admin_key is refused, by the service's own code. */
async function adminKeyRefused(mod) {
  const store = memStore();
  const attempts = [
    ['wrong key', { admin_key: 'not-the-admin-key-at-all-00000000', client_id: 'c_' + 'f'.repeat(32) }],
    ['absent key', { client_id: 'c_' + 'f'.repeat(32) }],
    ['empty key', { admin_key: '', client_id: 'c_' + 'f'.repeat(32) }],
    ['null key', { admin_key: null, client_id: 'c_' + 'f'.repeat(32) }],
    ['object key', { admin_key: { toString: () => ADMIN }, client_id: 'c_' + 'f'.repeat(32) }],
  ];
  for (const [what, body] of attempts) {
    const minted = await drive(mod, post('/api/studio/admin/pairing-code', body), store);
    if (!(minted.status === 403 && minted.json.ok === false && minted.json.code === 'AF-DS-ADMIN-REFUSED')) {
      return { ok: false, detail: what + ' on the mint route answered ' + minted.status + ' ' + minted.text };
    }
    const set = await drive(mod, post('/api/studio/options', { ...body, target_client_id: 'c_' + 'f'.repeat(32), option: 1 }), store);
    if (!(set.status === 403 && set.json.ok === false && set.json.code === 'AF-DS-ADMIN-REFUSED')) {
      return { ok: false, detail: what + ' on the options route answered ' + set.status + ' ' + set.text };
    }
  }
  const parked = [...store._mem.keys()].filter((k) => k.startsWith('pair:'));
  if (parked.length !== 0) {
    return { ok: false, detail: 'a refused admin call still wrote ' + parked.length + ' pair record(s)' };
  }
  return { ok: true, detail: attempts.length + ' bad admin keys refused 403 AF-DS-ADMIN-REFUSED on both admin routes, nothing written' };
}

/** (c) positive control — the right admin_key still mints. */
async function rightAdminKeyMints(mod) {
  const store = memStore();
  const res = await drive(mod, post('/api/studio/admin/pairing-code', { admin_key: ADMIN, client_id: 'c_' + '1'.repeat(31) + '0' }), store);
  if (!(res.status === 201 && res.json.ok === true)) {
    return { ok: false, detail: 'the right admin key answered ' + res.status + ' ' + res.text };
  }
  return { ok: true, detail: '201 with the correct admin key' };
}

/** (d) no key value is printed: request paths carry no query string. */
async function noKeyInAnyUrl(adminClient) {
  const key = 'a-key-value-that-must-never-appear-in-a-url-0000';
  const built = [
    adminClient.mintPairingCodeRequest(key, 'c_1'),
    adminClient.setOptionRequest(key, 'c_1', 1),
    adminClient.setOptionRequest(key, 'c_1', 3, { option3: true, client_name: 'Ann' }),
    adminClient.checkKeyRequest(key),
  ];
  for (const req of built) {
    if (!req.ok) return { ok: false, detail: 'a builder refused: ' + req.code };
    if (req.path.includes('?')) return { ok: false, detail: 'a path carries a query string: ' + req.path };
    if (req.path.includes(key)) return { ok: false, detail: 'a key reached a path' };
    if (req.body && JSON.stringify(req.body).includes('?x-ds-key=')) return { ok: false, detail: 'a key reached a query string' };
  }
  const probe = adminClient.checkKeyRequest(key);
  if (!probe.header || probe.header['x-ds-key'] !== key.trim()) {
    return { ok: false, detail: 'the key surface stopped using the x-ds-key header' };
  }
  return { ok: true, detail: built.length + ' built requests: no query string, key only ever in the x-ds-key header or a POST body' };
}

/** (d) keyLabel never shares a run of the key. */
function keyLabelLeaksNothing(adminClient) {
  const key = 'Zx7Qw3Lm9Vt2Bp5Rk8Hd1Fn4Gs6Jc0Ya';
  const label = adminClient.keyLabel(key);
  for (let i = 0; i + 4 <= key.length; i++) {
    if (label.includes(key.slice(i, i + 4))) {
      return { ok: false, detail: 'the label leaked "' + key.slice(i, i + 4) + '"' };
    }
  }
  return { ok: true, detail: 'label "' + label + '" shares no 4-character run with the key' };
}

/** (d) no response body in the whole run contains a key. */
function noKeyInAnyBody(secretValues) {
  for (const text of seenBodies) {
    for (const secret of secretValues) {
      const needle = typeof secret === 'string' && secret.length >= 8 ? secret : null;
      if (needle && text.includes(needle)) {
        return { ok: false, detail: 'a response body echoed a key value' };
      }
    }
  }
  return { ok: true, detail: seenBodies.length + ' response bodies captured; none echoed a key value' };
}

/** (d) the shipped sources persist nothing and never build a keyed URL. */
function shippedSourcesPersistNothing() {
  const files = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, name.name);
      if (name.isDirectory()) walk(p);
      else if (/\.(js|mjs|html)$/.test(name.name)) files.push(p);
    }
  };
  walk(PAIRING_DIR);
  const banned = [
    ['localStorage', /localStorage/],
    ['sessionStorage', /sessionStorage/],
    ['document.cookie', /document\.cookie/],
    ['keyed query string', /\?(admin_key|x-ds-key|key)=/],
  ];
  for (const file of files) {
    if (file === fileURLToPath(import.meta.url)) continue; // this prover names the patterns
    const text = readFileSync(file, 'utf8');
    for (const [what, re] of banned) {
      if (re.test(text)) {
        return { ok: false, detail: what + ' appears in ' + file.slice(PAIRING_DIR.length + 1) };
      }
    }
  }
  return { ok: true, detail: files.length - 1 + ' shipped js/mjs/html files: no browser storage, no keyed query string' };
}

/** The alphabet this surface accepts must be the alphabet the service mints. */
async function alphabetMatchesLiveService(mod, adminClient) {
  const store = memStore();
  for (let i = 0; i < 64; i++) {
    const res = await drive(mod, post('/api/studio/admin/pairing-code', { admin_key: ADMIN, client_id: 'c_' + '0'.repeat(29) + String(100 + i).slice(-3) }), store);
    if (!(res.status === 201)) return { ok: false, detail: 'mint ' + i + ' answered ' + res.status };
    const checked = adminClient.checkCode(res.json.code);
    if (!checked.ok) {
      return { ok: false, detail: 'the live service minted "' + res.json.code + '" and this surface refused it (' + checked.code + ')' };
    }
  }
  return { ok: true, detail: '64 live-minted codes all pass this surface’s shape check' };
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

let plantedDir = null;
try {
  const live = await loadService(join(SERVICE_DIR, 'src'));
  await import(pathToFileURL(join(PAIRING_DIR, 'lib', 'admin_client.js')).href);
  await import(pathToFileURL(join(PAIRING_DIR, 'lib', 'qr.js')).href);
  const adminClient = globalThis.DSAdmin;
  if (!adminClient) throw new Error('lib/admin_client.js did not register globalThis.DSAdmin');

  // ---- live run -----------------------------------------------------------
  const a1 = await option3Refused(live);
  check('A1-option3-refused-without-approval', a1.ok, a1.detail);
  const a2 = await option3AcceptedWithApproval(live);
  check('A2-control-option3-with-good-approval', a2.ok, a2.detail);
  const a3 = await option2Accepted(live);
  check('A3-control-plain-option-needs-no-approval', a3.ok, a3.detail);

  const b1 = await pairingCodeIsSingleUse(live);
  check('B1-pairing-code-single-use', b1.ok, b1.detail);
  const b2 = await freshCodeStillPairs(live);
  check('B2-control-a-fresh-code-still-pairs', b2.ok, b2.detail);

  const c1 = await adminKeyRefused(live);
  check('C1-wrong-or-absent-admin-key-refused', c1.ok, c1.detail);
  const c2 = await rightAdminKeyMints(live);
  check('C2-control-right-admin-key-mints', c2.ok, c2.detail);

  const d1 = await noKeyInAnyUrl(adminClient);
  check('D1-no-key-in-any-request-url', d1.ok, d1.detail);
  const d2 = keyLabelLeaksNothing(adminClient);
  check('D2-key-label-leaks-no-run-of-the-key', d2.ok, d2.detail);
  const d3 = noKeyInAnyBody([ADMIN]);
  check('D3-no-response-body-echoes-a-key', d3.ok, d3.detail);
  const d4 = shippedSourcesPersistNothing();
  check('D4-shipped-sources-persist-nothing', d4.ok, d4.detail);

  const e1 = await alphabetMatchesLiveService(live, adminClient);
  check('E1-surface-alphabet-matches-live-service', e1.ok, e1.detail);

  // ---- planted-defect runs: every gate must go RED when its defect lands ---
  plantedDir = plantedCopy([
    ['options.js', "    const approved = approval && approval.option3 === true && typeof approval.client_name === 'string' && approval.client_name;",
      '    const approved = true;'],
  ]);
  const neuteredApproval = await loadService(join(plantedDir, 'src'));
  const p1 = await option3Refused(neuteredApproval);
  check('P1-planted-option3-gate-neutered-turns-A1-red', !p1.ok, p1.ok ? 'A1 stayed green with the approval gate removed — the check is vacuous' : 'A1 went red as required');

  plantedDir = plantedCopy([
    ['index.js', '    await store.kvDelete(`pair:${attempt.record.fingerprint}`);', '    // burn removed by the planted defect'],
  ]);
  const burnRemoved = await loadService(join(plantedDir, 'src'));
  const p2 = await pairingCodeIsSingleUse(burnRemoved);
  check('P2-planted-missing-burn-turns-B1-red', !p2.ok, p2.ok ? 'B1 stayed green with the burn removed — the check is vacuous' : 'B1 went red as required');

  plantedDir = plantedCopy([
    ['index.js', "  return typeof expected === 'string' && expected.length > 0 && presented === expected;", '  return true;'],
  ]);
  const adminAlways = await loadService(join(plantedDir, 'src'));
  const p3 = await adminKeyRefused(adminAlways);
  check('P3-planted-open-admin-gate-turns-C1-red', !p3.ok, p3.ok ? 'C1 stayed green with the admin gate opened — the check is vacuous' : 'C1 went red as required');

  const d5 = noKeyInAnyBody([ADMIN]);
  check('D5-no-response-body-echoes-a-key-after-defects', d5.ok, d5.detail);
} catch (err) {
  process.stdout.write('COULD NOT RUN  ' + (err && err.stack ? err.stack : err) + '\n');
  if (plantedDir) rmSync(plantedDir, { recursive: true, force: true });
  process.exit(3);
}

if (plantedDir) rmSync(plantedDir, { recursive: true, force: true });

const failed = results.filter((r) => !r.ok);
process.stdout.write('\n' + results.length + ' checks, ' + (results.length - failed.length) + ' pass, ' + failed.length + ' fail\n');
process.exit(failed.length === 0 ? 0 : 2);
