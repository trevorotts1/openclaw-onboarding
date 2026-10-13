// W1-studio-page-U4: the upload page reads the key from the link fragment.
// No framework, no network, no browser: a DOM shim and a fake transport.
import assert from 'node:assert/strict';
import { linkKey } from './upload.js';

const KEY = '00112233445566778899aabbccddeeff'; // fake key shaped like a link key, never a real one

// ── the fragment rule ────────────────────────────────────────────────────────
assert.equal(linkKey(`#k=${KEY}`), KEY, 'bare fragment key');
assert.equal(linkKey(`#k=${KEY}&p=upload`), KEY, 'key with a page after it');
assert.equal(linkKey(`#${KEY}`), null, 'no k= parameter');
assert.equal(linkKey('#p=upload'), null, 'other parameter only');
assert.equal(linkKey(`#k=${KEY.slice(0, 31)}`), null, 'too short');
assert.equal(linkKey(`#k=${'z'.repeat(32)}`), null, 'not lowercase hex');
assert.equal(linkKey(''), null, 'no hash at all');

// ── the page: key present hides the paste box and drives the upload ─────────
const els = (extra) => ({ hidden: false, required: false, value: '', accept: '', disabled: false, files: [], listeners: {},
  addEventListener(type, fn) { this.listeners[type] = fn; }, ...extra });
const byId = {
  'upload-form': els(), channel: els({ value: 'image' }), file: els(), send: els(), status: els(),
  'paste-key': els(), 'studio-key': els({ required: true }),
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
assert.equal(byId['paste-key'].hidden, true, 'paste box hidden when the link carries the key');
assert.equal(byId['studio-key'].required, false, 'hidden key field must not block the form');
byId['studio-key'].value = 'a-pasted-key-that-must-not-win';
byId['file'].files = [{ name: 'photo.png', size: 12, slice: () => ({ arrayBuffer: async () => new ArrayBuffer(16) }) }];
await byId['upload-form'].listeners.submit({ preventDefault() {} });
assert.equal(usedKey, KEY, 'the hash key is the key sent to the studio');

// ── the fallback: no key in the fragment keeps the paste box ────────────────
for (const id of Object.keys(byId)) byId[id] = els(id === 'studio-key' ? { required: true } : id === 'channel' ? { value: 'image' } : {});
globalThis.location = { hash: '#p=upload' };
const withoutHash = await import(`./upload.js?v=nohash${Date.now()}`);
assert.equal(withoutHash.linkKey(), null);
assert.equal(byId['paste-key'].hidden, false, 'paste box stays when there is no key');
assert.equal(byId['studio-key'].required, true, 'paste box still demands its key');

console.log('fragment-check OK: 7 fragment rules, hidden paste box, hash key sent, fallback intact');
