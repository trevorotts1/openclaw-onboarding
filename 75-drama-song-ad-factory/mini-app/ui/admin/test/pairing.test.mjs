/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN  ::  test/pairing.test.mjs
 * -----------------------------------------------------------------------------
 *   node --test 75-drama-song-ad-factory/mini-app/ui/admin/test/pairing.test.mjs
 *   exit 0 = all pass
 *
 * Two suites, no framework beyond node:test and no browser:
 *   1. lib/qr.js — the encoder is checked by DECODING ITS OWN OUTPUT back to
 *      the pairing code (independent read of the format info, the mask, the
 *      zigzag, the de-interleave and the Reed-Solomon syndromes), plus the
 *      structural invariants the spec fixes regardless of content. A decoder
 *      written in the same file cannot prove the spec is right, which is why
 *      prove/prove_qr_against_apple.mjs compares it to Apple's own encoder.
 *   2. lib/admin_client.js — every local gate, and the request shapes it hands
 *      the page, so a key can never reach a URL.
 * ========================================================================== */

'use strict';

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = join(HERE, '..', 'lib');
const PAGE = join(HERE, '..', 'index.html');

await import(pathToFileURL(join(LIB, 'qr.js')).href);
await import(pathToFileURL(join(LIB, 'admin_client.js')).href);
const DSQR = globalThis.DSQR;
const DSAdmin = globalThis.DSAdmin;

// ---------------------------------------------------------------------------
// A byte-mode QR reader, written against the spec tables independently of the
// encoder's code path — it re-derives the function-module map and re-reads the
// format info rather than asking the encoder what it did.
// ---------------------------------------------------------------------------

const EC_BLOCKS = {
  '1L': [7, 1, 19, 0, 0], '1M': [10, 1, 16, 0, 0], '1Q': [13, 1, 13, 0, 0], '1H': [17, 1, 9, 0, 0],
  '2L': [10, 1, 34, 0, 0], '2M': [16, 1, 28, 0, 0], '2Q': [22, 1, 22, 0, 0], '2H': [28, 1, 16, 0, 0],
  '3L': [15, 1, 55, 0, 0], '3M': [26, 1, 44, 0, 0], '3Q': [18, 2, 17, 0, 0], '3H': [22, 2, 13, 0, 0],
  '4L': [20, 1, 80, 0, 0], '4M': [18, 2, 32, 0, 0], '4Q': [26, 2, 24, 0, 0], '4H': [16, 4, 9, 0, 0],
  '5L': [26, 1, 108, 0, 0], '5M': [24, 2, 43, 0, 0], '5Q': [18, 2, 15, 2, 16], '5H': [22, 2, 11, 2, 12],
  '6L': [18, 2, 68, 0, 0], '6M': [16, 4, 27, 0, 0], '6Q': [24, 4, 19, 0, 0], '6H': [28, 4, 15, 0, 0],
};
const ALIGN = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34] };
const LEVEL_FROM_BITS = { 1: 'L', 0: 'M', 3: 'Q', 2: 'H' };
const LEVEL_TO_BITS = { L: 1, M: 0, Q: 3, H: 2 };

function functionMap(n, version) {
  const func = Array.from({ length: n }, () => new Array(n).fill(false));
  const finder = (r0, c0) => {
    for (let dr = -1; dr <= 7; dr++) {
      for (let dc = -1; dc <= 7; dc++) {
        const r = r0 + dr, c = c0 + dc;
        if (r >= 0 && c >= 0 && r < n && c < n) func[r][c] = true;
      }
    }
  };
  finder(0, 0); finder(0, n - 7); finder(n - 7, 0);
  for (let i = 8; i < n - 8; i++) { func[6][i] = true; func[i][6] = true; }
  for (const cr of ALIGN[version]) for (const cc of ALIGN[version]) {
    if ((cr === 6 && cc === 6) || (cr === 6 && cc === n - 7) || (cr === n - 7 && cc === 6)) continue;
    for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) func[cr + dr][cc + dc] = true;
  }
  func[4 * version + 9][8] = true;
  for (let c = 0; c <= 8; c++) if (c !== 6) func[8][c] = true;
  for (let r = 0; r <= 8; r++) if (r !== 6) func[r][8] = true;
  for (let c = n - 8; c < n; c++) func[8][c] = true;
  for (let r = n - 7; r < n; r++) func[r][8] = true;
  return func;
}

const MASK_FN = [
  (r, c) => (r + c) % 2 === 0, (r) => r % 2 === 0, (r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0, (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

const EXP = [], LOG = [];
{
  let x = 1;
  for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
}
const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);

/** Read one matrix back to its text. Throws with a named reason on any defect. */
function readBack(modules) {
  const n = modules.length;
  const version = (n - 17) / 4;
  if (!Number.isInteger(version) || version < 1 || version > 6) throw new Error('bad size');

  const pos1 = [[8, 0], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 7], [8, 8], [7, 8], [5, 8], [4, 8], [3, 8], [2, 8], [1, 8], [0, 8]];
  const pos2 = [[n - 1, 8], [n - 2, 8], [n - 3, 8], [n - 4, 8], [n - 5, 8], [n - 6, 8], [n - 7, 8],
    [8, n - 8], [8, n - 7], [8, n - 6], [8, n - 5], [8, n - 4], [8, n - 3], [8, n - 2], [8, n - 1]];
  const readFmt = (positions) => {
    let v = 0;
    for (const [r, c] of positions) v = (v << 1) | modules[r][c];
    return v;
  };
  const f1 = readFmt(pos1);
  const f2 = readFmt(pos2);
  if (f1 !== f2) throw new Error('the two format-info copies disagree');

  const unmasked = f1 ^ 0b101010000010010;
  if (((unmasked >> 10) ^ ((unmasked >> 10) & 3)) === -1) throw new Error('unreachable');
  const level = LEVEL_FROM_BITS[(unmasked >> 13) & 3];
  const mask = (unmasked >> 10) & 7;

  const func = functionMap(n, version);
  const maskFn = MASK_FN[mask];
  const stream = [];
  let upward = true;
  for (let col = n - 1; col > 0; col -= 2) {
    if (col === 6) col--;
    for (let i = 0; i < n; i++) {
      const row = upward ? n - 1 - i : i;
      for (const c of [col, col - 1]) {
        if (func[row][c]) continue;
        stream.push(modules[row][c] ^ (maskFn(row, c) ? 1 : 0));
      }
    }
    upward = !upward;
  }

  const spec = EC_BLOCKS[version + level];
  const ecPer = spec[0];
  const blocks = [];
  for (let i = 0; i < spec[1]; i++) blocks.push({ data: new Array(spec[2]).fill(0), ec: new Array(ecPer).fill(0) });
  for (let i = 0; i < spec[3]; i++) blocks.push({ data: new Array(spec[4]).fill(0), ec: new Array(ecPer).fill(0) });
  const byteAt = (at) => { let v = 0; for (let k = 0; k < 8; k++) v = (v << 1) | stream[at * 8 + k]; return v; };

  let idx = 0;
  const maxData = Math.max(...blocks.map((b) => b.data.length));
  for (let c = 0; c < maxData; c++) for (const b of blocks) if (c < b.data.length) b.data[c] = byteAt(idx++);
  for (let e = 0; e < ecPer; e++) for (const b of blocks) b.ec[e] = byteAt(idx++);

  blocks.forEach((b, i) => {
    const all = [...b.data, ...b.ec];
    for (let s = 0; s < ecPer; s++) {
      let acc = 0;
      for (const word of all) acc = mul(acc, EXP[s]) ^ word;
      assert.equal(acc, 0, `block ${i} syndrome ${s} is not zero`);
    }
  });

  const payload = blocks.flatMap((b) => b.data);
  let p = 0;
  const take = (k) => { let v = 0; for (let i = 0; i < k; i++) { v = (v << 1) | ((payload[p >> 3] >> (7 - (p & 7))) & 1); p++; } return v; };
  const mode = take(4);
  assert.equal(mode, 0b0100, 'mode indicator is not byte mode');
  const len = take(8);
  const bytes = [];
  for (let i = 0; i < len; i++) bytes.push(take(8));
  return { version, level, mask, text: Buffer.from(bytes).toString('utf8') };
}

// ---------------------------------------------------------------------------
// lib/qr.js
// ---------------------------------------------------------------------------

test('qr: the pairing code encodes and decodes back to itself', () => {
  for (const code of ['ABCD-2345', 'HJKM-NPQR', '2345-6789', 'abcdefgh']) {
    const q = DSQR.encode(code, { level: 'M' });
    assert.equal(q.ok, true, code);
    const back = readBack(q.modules);
    assert.equal(back.text, code);
    assert.equal(back.level, 'M');
  }
});

test('qr: versions 1-6 and all four EC levels round-trip', () => {
  // [payload, level, the smallest version that fits] — version selection and
  // the refusals are both asserted, so neither can be silently loosened.
  const cases = [
    ['ABCD-2345', 'M', 1],
    ['ABCD-2345', 'H', 2],
    ['abcdefghijklmnop', 'L', 1],
    ['pairing-code-xyz', 'Q', 2],
    ['x', 'L', 1],
    ['x'.repeat(30), 'L', 2],
    ['x'.repeat(30), 'Q', 3],
    ['x'.repeat(45), 'M', 4],
    ['x'.repeat(40), 'H', 5],
    ['x'.repeat(50), 'Q', 5],
    ['x'.repeat(58), 'H', 6],
    ['x'.repeat(70), 'Q', 6],
    ['x'.repeat(134), 'L', 6],
  ];
  for (const [text, level, version] of cases) {
    const q = DSQR.encode(text, { level });
    assert.equal(q.ok, true, `${level} ${text.length}`);
    assert.equal(q.version, version, `${level} ${text.length} should need version ${version}`);
    assert.equal(q.size, 17 + 4 * version);
    const back = readBack(q.modules);
    assert.equal(back.version, q.version);
    assert.equal(back.level, level);
    assert.equal(back.mask, q.mask, 'the mask named by the format info is the mask used');
    assert.equal(back.text, text);
  }
  assert.equal(DSQR.encode('x'.repeat(135), { level: 'L' }).code, 'AF-DS-QR-TOO-LONG');
  assert.equal(DSQR.encode('x'.repeat(59), { level: 'H' }).code, 'AF-DS-QR-TOO-LONG');
});

test('qr: the structural invariants hold whatever the payload', () => {
  const q = DSQR.encode('ABCD-2345', { level: 'M' });
  const n = q.size;
  const at = (r, c) => q.modules[r][c];
  // three finder patterns with their separators
  for (const [r0, c0] of [[0, 0], [0, n - 7], [n - 7, 0]]) {
    for (let dr = 0; dr < 7; dr++) {
      for (let dc = 0; dc < 7; dc++) {
        const edge = dr === 0 || dr === 6 || dc === 0 || dc === 6;
        const core = dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4;
        assert.equal(at(r0 + dr, c0 + dc), edge || core ? 1 : 0, `finder ${r0},${c0} at ${dr},${dc}`);
      }
    }
  }
  // timing patterns alternate from the dark module next to each finder
  for (let i = 8; i < n - 8; i++) {
    assert.equal(at(6, i), i % 2 === 0 ? 1 : 0, `row timing ${i}`);
    assert.equal(at(i, 6), i % 2 === 0 ? 1 : 0, `column timing ${i}`);
  }
  // the dark module
  assert.equal(at(4 * q.version + 9, 8), 1);
  // the separator row/column around each finder is light
  for (let i = 0; i < 8; i++) {
    assert.equal(at(7, i), 0);
    assert.equal(at(i, 7), 0);
    assert.equal(at(7, n - 1 - i), 0);
    assert.equal(at(n - 8, i), 0);
  }
});

test('qr: refusal is named, never a silent truncation', () => {
  const tooLong = DSQR.encode('x'.repeat(400), { level: 'M' });
  assert.deepEqual({ ok: tooLong.ok, code: tooLong.code }, { ok: false, code: 'AF-DS-QR-TOO-LONG' });
  assert.equal(DSQR.encode('ABCD-2345', { level: 'Z' }).code, 'AF-DS-QR-BAD-LEVEL');
  assert.equal(DSQR.encode('', { level: 'M' }).code, 'AF-DS-QR-BAD-INPUT');
  assert.equal(DSQR.encode('ABCD-2345', { level: 'M', mask: 9 }).code, 'AF-DS-QR-BAD-INPUT');
});

test('qr: the format value is the spec value, not a lookup we invented', () => {
  // BCH(15,5) with generator 0b10100110111, masked with 0b101010000010010.
  // M2 = 0x5E7C was read back out of Apple's CIQRCodeGenerator for a v1-M code
  // whose format info decoded to level M, mask 2 — so this row is not self-
  // consistent arithmetic, it is a checked value. The rest follow the same BCH.
  assert.equal(DSQR.formatBits('M', 2), 0x5e7c);
  assert.equal(DSQR.formatBits('L', 0), 0x77c4);
  assert.equal(DSQR.formatBits('M', 0), 0x5412);
  assert.equal(DSQR.formatBits('Q', 0), 0x355f);
  assert.equal(DSQR.formatBits('H', 0), 0x1689);
  // every value must carry its own level and mask, and divide by the generator
  for (const level of ['L', 'M', 'Q', 'H']) {
    for (let mask = 0; mask < 8; mask++) {
      const value = DSQR.formatBits(level, mask);
      const unmasked = value ^ 0b101010000010010;
      assert.equal(unmasked >> 13, { L: 1, M: 0, Q: 3, H: 2 }[level]);
      assert.equal((unmasked >> 10) & 7, mask);
      let rem = unmasked;
      for (let i = 14; i >= 10; i--) if ((rem >> i) & 1) rem ^= 0b10100110111 << (i - 10);
      assert.equal(rem & 0x3ff, 0, `${level}${mask} is not a valid BCH codeword`);
    }
  }
});

test('qr: the svg carries a title and an accessible name', () => {
  const q = DSQR.encode('ABCD-2345', { level: 'M' });
  const svg = DSQR.toSvg(q, { label: 'Pairing code AB CD 2345' });
  assert.match(svg, /^<svg /);
  assert.match(svg, /role="img"/);
  assert.match(svg, /<title>Pairing code AB CD 2345<\/title>/);
  assert.match(svg, /aria-label="Pairing code AB CD 2345"/);
  assert.match(svg, /viewBox="0 0 \d+ \d+"/);
  assert.equal(svg.includes('ABCD-2345'), false, 'the code is text on the page, not baked into the svg');
});

// ---------------------------------------------------------------------------
// lib/admin_client.js
// ---------------------------------------------------------------------------

test('admin: Option 3 is refused without a well-formed approval, and only then', () => {
  const approved = DSAdmin.optionApprovalProblem(3, { option3: true, client_name: 'Ann Example' });
  assert.equal(approved, null);
  for (const bad of [undefined, null, {}, { option3: true }, { client_name: 'Ann' }, { option3: 'true', client_name: 'Ann' }, { option3: true, client_name: '   ' }, { option3: true, client_name: 7 }]) {
    const problem = DSAdmin.optionApprovalProblem(3, bad);
    assert.ok(problem, JSON.stringify(bad));
    assert.equal(problem.code, 'AF-DS-OPT-APPROVAL');
  }
  assert.equal(DSAdmin.optionApprovalProblem(1), null);
  assert.equal(DSAdmin.optionApprovalProblem(2), null);
  assert.equal(DSAdmin.optionApprovalProblem(4).code, 'AF-DS-OPT-INVALID');
});

test('admin: the set-option request rebuilds the approval and drops smuggled fields', () => {
  const built = DSAdmin.setOptionRequest('admin-fixture', ' c_1 ', 3, {
    option3: true,
    client_name: '  Ann Example  ',
    admin_key: 'an-injected-key',
    extra: 'nope',
  });
  assert.equal(built.ok, true);
  assert.deepEqual(built.body.approval, { option3: true, client_name: 'Ann Example' });
  assert.equal(built.body.admin_key, 'admin-fixture');
  assert.equal(built.body.target_client_id, 'c_1');
  assert.equal(built.method, 'POST');
  assert.equal(built.path, '/api/studio/options');
  assert.equal(built.path.includes('?'), false);
});

test('admin: the set-option request refuses a malformed approval before any round trip', () => {
  const built = DSAdmin.setOptionRequest('admin-fixture', 'c_1', 3, { option3: true });
  assert.equal(built.ok, false);
  assert.equal(built.code, 'AF-DS-OPT-APPROVAL');
  assert.equal(DSAdmin.setOptionRequest('', 'c_1', 1).code, 'AF-DS-ADMIN-NOKEY');
  assert.equal(DSAdmin.setOptionRequest('k', '', 1).code, 'AF-DS-ADMIN-NOCLIENT');
});

test('admin: the mint request needs both an admin key and a client id', () => {
  assert.deepEqual(
    DSAdmin.mintPairingCodeRequest('admin-fixture', 'c_1'),
    { ok: true, method: 'POST', path: '/api/studio/admin/pairing-code', body: { admin_key: 'admin-fixture', client_id: 'c_1' } },
  );
  assert.equal(DSAdmin.mintPairingCodeRequest('', 'c_1').code, 'AF-DS-ADMIN-NOKEY');
  assert.equal(DSAdmin.mintPairingCodeRequest('k', '  ').code, 'AF-DS-ADMIN-NOCLIENT');
});

test('admin: the make-link request posts the admin key and client id in the body', () => {
  assert.deepEqual(
    DSAdmin.makeLinkRequest('admin-fixture', ' c_1 '),
    { ok: true, method: 'POST', path: '/api/studio/admin/link', body: { admin_key: 'admin-fixture', client_id: 'c_1' } },
  );
  assert.equal(DSAdmin.makeLinkRequest('', 'c_1').code, 'AF-DS-ADMIN-NOKEY');
  assert.equal(DSAdmin.makeLinkRequest('k', '  ').code, 'AF-DS-ADMIN-NOCLIENT');
  // the link key rides in the body, never in a query string
  assert.equal(/\?/.test(DSAdmin.makeLinkRequest('admin-fixture', 'c_1').path), false);
});

test('admin: the key surface uses the x-ds-key header and never a query string', () => {
  const probe = DSAdmin.checkKeyRequest(' a-key ');
  assert.equal(probe.ok, true);
  assert.equal(probe.method, 'GET');
  assert.equal(probe.path, '/api/studio/options');
  assert.deepEqual(probe.header, { 'x-ds-key': 'a-key' });
  assert.equal(DSAdmin.checkKeyRequest('').code, 'AF-DS-ADMIN-NOKEY');
});

test('admin: keyLabel is a count, never a value', () => {
  const key = 'Zx7Qw3Lm9Vt2Bp5Rk8Hd1Fn4Gs6Jc0Ya';
  const label = DSAdmin.keyLabel(key);
  for (let i = 0; i + 4 <= key.length; i++) assert.equal(label.includes(key.slice(i, i + 4)), false);
  assert.equal(label.includes(String(key.length)), true);
  assert.equal(DSAdmin.keyLabel(''), 'no key held');
});

test('admin: a reply is read into the service’s own code, never a blank success', () => {
  assert.equal(DSAdmin.readReply(200, { ok: true, option: 1 }).ok, true);
  const refused = DSAdmin.readReply(403, { ok: false, code: 'AF-DS-ADMIN-REFUSED', message: 'Not the admin.' });
  assert.equal(refused.ok, false);
  assert.equal(refused.code, 'AF-DS-ADMIN-REFUSED');
  assert.equal(refused.message, 'Not the admin.');
  assert.equal(DSAdmin.readReply(500, null).code, 'AF-DS-ADMIN-UNREADABLE');
  assert.equal(DSAdmin.readReply(200, { ok: false }).code, 'AF-DS-ADMIN-UNREADABLE');
});

test('admin: pairing-code shape matches the service alphabet', () => {
  assert.equal(DSAdmin.checkCode('abcd-2345').code, 'ABCD-2345');
  assert.equal(DSAdmin.checkCode('ABCD2345').ok, true);
  assert.equal(DSAdmin.checkCode('ABCD-2340').code, 'AF-DS-PAIR-SHAPE', '0 is never minted');
  assert.equal(DSAdmin.checkCode('ABCD-234O').code, 'AF-DS-PAIR-SHAPE');
  assert.equal(DSAdmin.checkCode('ABCD-2341').code, 'AF-DS-PAIR-SHAPE', '1 is never minted');
  assert.equal(DSAdmin.checkCode('ABCD-I345').code, 'AF-DS-PAIR-SHAPE', 'I is never minted');
  assert.equal(DSAdmin.checkCode('ABCD-L345').code, 'AF-DS-PAIR-SHAPE', 'L is never minted');
  assert.equal(DSAdmin.checkCode('ABC-2345').code, 'AF-DS-PAIR-SHAPE');
  assert.equal(DSAdmin.checkCode('').code, 'AF-DS-PAIR-SHAPE');
});

test('admin: the cutoff is computed and shown, and a save is refused by name', () => {
  const verdict = DSAdmin.cutoffVerdict(18 * 60 + 30, 'UTC', Date.UTC(2026, 0, 5, 9, 0, 0));
  assert.equal(verdict.ok, true);
  assert.equal(verdict.before, true);
  assert.equal(verdict.clock, '6:30 PM');
  assert.match(verdict.line, /New orders stop starting at 6:30 PM \(UTC\)\./);

  const after = DSAdmin.cutoffVerdict(18 * 60 + 30, 'UTC', Date.UTC(2026, 0, 5, 20, 0, 0));
  assert.equal(after.before, false);

  assert.equal(DSAdmin.cutoffVerdict(1440, 'UTC', 0).code, 'AF-DS-CUTOFF-INVALID');
  assert.equal(DSAdmin.cutoffVerdict(600, '', 0).code, 'AF-DS-CUTOFF-INVALID');
  assert.equal(DSAdmin.cutoffVerdict(600, 'Mars/Olympus', 0).code, 'AF-DS-CUTOFF-INVALID');
  assert.equal(DSAdmin.cutoffVerdict(600.5, 'UTC', 0).code, 'AF-DS-CUTOFF-INVALID');

  const saved = DSAdmin.setCutoffRequest(18 * 60 + 30, 'UTC');
  assert.equal(saved.ok, false, 'there is no cutoff route in version 0 — a save must never claim success');
  assert.equal(saved.code, 'AF-DS-CUTOFF-NO-ROUTE');
  assert.match(saved.message, /\/api\/studio\/admin\/cutoff/);
  assert.equal(DSAdmin.setCutoffRequest(9000, 'UTC').code, 'AF-DS-CUTOFF-INVALID');
});

test('admin: cutting a key off is refused by name until the route exists', () => {
  const refused = DSAdmin.revokeKeyRequest();
  assert.equal(refused.ok, false);
  assert.equal(refused.code, 'AF-DS-CUTOFF-NO-ROUTE');
  assert.match(refused.message, /\/api\/studio\/admin\/revoke/);
});

// ---------------------------------------------------------------------------
// admin.html — the accessibility floor, checked statically so it cannot rot.
// ---------------------------------------------------------------------------

/** The page with its comments removed, so a comment can never satisfy a check. */
function pageSource() {
  return readFileSync(PAGE, 'utf8').replace(/<!--[\s\S]*?-->/g, '');
}

test('page: every control is labelled, every id is unique, every id the script uses exists', () => {
  const html = pageSource();

  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(ids.length, new Set(ids).size, 'duplicate ids break <label for> and getElementById');

  for (const target of [...html.matchAll(/<label[^>]*for="([^"]+)"/g)].map((m) => m[1])) {
    assert.ok(ids.includes(target), `<label for="${target}"> points at nothing`);
  }

  for (const control of html.matchAll(/<(input|select|textarea)\b([^>]*)>/g)) {
    const attrs = control[2];
    const id = (attrs.match(/id="([^"]+)"/) || [])[1];
    const wrapped = /<label[^>]*>\s*$/.test(html.slice(0, control.index));
    const labelled = id && new RegExp(`<label[^>]*for="${id}"`).test(html);
    assert.ok(labelled || wrapped || /type="hidden"/.test(attrs), `an unlabelled <${control[1]}> would be invisible to a screen reader`);
  }

  // The inline wiring runs after the two libraries and reaches the DOM by id.
  const script = html.slice(html.indexOf('<script src="lib/qr.js"'));
  const used = [...script.matchAll(/el\('([^']+)'\)/g)].map((m) => m[1]);
  assert.ok(used.length > 8, 'the wiring looks empty — did the page stop using the libs?');
  for (const id of new Set(used)) assert.ok(ids.includes(id), `the script reaches for #${id}, which the page never defines`);

  assert.match(script, /<script src="lib\/qr\.js"><\/script>/);
  assert.match(script, /<script src="lib\/admin_client\.js"><\/script>/);
  assert.equal(/localStorage|sessionStorage|document\.cookie/.test(html), false, 'nothing may be persisted in the page');
});

test('page: every section announces its result and its refusal', () => {
  const html = pageSource();
  const sections = [...html.matchAll(/<section[^>]*>([\s\S]*?)<\/section>/g)].map((m) => m[1]);
  assert.equal(sections.length, 5, 'pairing, key, options, cutoff, link');
  for (const section of sections) {
    assert.match(section, /role="status"/, 'a result needs a polite live region');
    assert.match(section, /role="alert"/, 'a refusal needs an assertive live region');
  }
  // focus order is the reading order: the five headings appear in page order
  const headings = [...html.matchAll(/<h2 id="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(headings, ['pairing-h', 'key-h', 'options-h', 'cutoff-h', 'link-h']);
});
