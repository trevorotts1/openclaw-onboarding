// U-Z08: the upload page reads the key from the link fragment and has no key
// box of its own. No framework, no network, no browser: a DOM shim and a fake
// transport.
import assert from 'node:assert/strict';
import { linkKey } from './upload.js';

const KEY = '00112233445566778899aabbccddeeff'; // fake key shaped like a link key, never a real one
const KEY64 = KEY + KEY; // the 64-hex key the service mints today

// ── the fragment rule ────────────────────────────────────────────────────────
assert.equal(linkKey(`#k=${KEY}`), KEY, 'bare fragment key (legacy 32 hex)');
assert.equal(linkKey(`#k=${KEY64}`), KEY64, 'the 64-hex key the service mints');
assert.equal(linkKey(`#k=${KEY}&p=upload`), KEY, 'key with a page after it');
assert.equal(linkKey(`#${KEY}`), null, 'no k= parameter');
assert.equal(linkKey('#p=upload'), null, 'other parameter only');
assert.equal(linkKey(`#k=${KEY.slice(0, 31)}`), null, 'too short');
assert.equal(linkKey(`#k=${'z'.repeat(32)}`), null, 'not lowercase hex');
assert.equal(linkKey(''), null, 'no hash at all');

// ── the page: the link carries the key, so there is no key box at all ───────
const els = (extra) => ({ hidden: false, value: '', disabled: false, files: [], textContent: '', listeners: {},
  addEventListener(type, fn) { this.listeners[type] = fn; }, ...extra });
const byId = {
  'upload-form': els(), file: els(), send: els(), status: els(), 'key-line': els({ hidden: true }),
};
let usedKey = null;
globalThis.fetch = async (url, opts) => {
  usedKey = opts.headers['x-ds-key'];
  return new Response(JSON.stringify({ ok: false, code: 'AF-DS-TEST' }), { status: 500 });
};
globalThis.document = { getElementById: (id) => byId[id] };
globalThis.location = { hash: `#k=${KEY}` };

const withHash = await import(`./upload.js?v=hash${Date.now()}`);
assert.equal(withHash.linkKey(), KEY, 'the page reads its own hash');
assert.equal(byId['key-line'].hidden, true, 'no key line when the link carries the key');
byId.file.files = [{ name: 'photo.png', size: 12, slice: () => ({ arrayBuffer: async () => new ArrayBuffer(16) }) }];
await byId['upload-form'].listeners.submit({ preventDefault() {} });
assert.equal(usedKey, KEY, 'the hash key is the key sent to the studio');
// A refusal with no message of its own reads as the one plain sentence.
assert.equal(byId.status.textContent, 'The studio could not take that file. Please try again.');

// ── the fallback: no key in the fragment shows where to open the page ───────
for (const id of Object.keys(byId)) byId[id] = els(id === 'key-line' ? { hidden: true } : {});
let sent = 0;
globalThis.fetch = async () => { sent += 1; return new Response('{}', { status: 200 }); };
globalThis.location = { hash: '#p=upload' };
const withoutHash = await import(`./upload.js?v=nohash${Date.now()}`);
assert.equal(withoutHash.linkKey(), null);
assert.equal(byId['upload-form'].hidden, true, 'no form without a key in the link');
assert.equal(byId['key-line'].hidden, false, 'the page says where to open it');
assert.equal(byId['key-line'].textContent, 'Open this page from your personal studio link.');
assert.equal(sent, 0, 'nothing is sent without a key');

console.log('fragment-check OK: 8 fragment rules (32 and 64 hex), no key box, hash key sent, no-link sentence, nothing sent without a key');
