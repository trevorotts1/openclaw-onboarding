// ============================================================================
// asset-allowlist.test.mjs — the studio domain serves an allow-list only
// (DSF CF-2, the #1950 + #1952 leak)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/asset-allowlist.test.mjs
//
// #1950 points the Worker's assets directory at the WHOLE mini-app/ui folder
// and #1952's staticAssetPath used to return any non-/api/ path unchanged, so
// on the client's studio domain checks/run-all.sh, admin/test/pairing.test.mjs,
// package.json and README.md would all have been served. This proves:
//   (a) every allow-listed page path is served 200;
//   (b) the checks, the tests, the prover, the dotfiles, package.json,
//       README.md, upload/fragment-check.mjs and a traversal attempt are all
//       refused with 404 and never reach the assets binding;
//   (c) /api/* never reaches the assets binding at all.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import worker from '../src/index.js';
import { memObjects, memStore } from './fakes.mjs';

const ORIGIN = 'https://studio.example';

// ---------------------------------------------------------------------------
// A fake assets binding shaped exactly like the one worker.fetch builds, that
// serves only what the bundle really holds and records everything it was asked
// for — so a refused path is provable by absence, not by a 404 from the bucket.
// ---------------------------------------------------------------------------

function assetsBinding(files) {
  const asked = [];
  return {
    asked,
    fetch: async (req) => {
      const path = new URL(req.url).pathname;
      asked.push(path);
      const body = files[path];
      if (body === undefined) return new Response('not found', { status: 404 });
      return new Response(body, { status: 200, headers: { 'Content-Type': 'text/html' } });
    },
  };
}

/** An environment with KV, R2 and the assets binding, all in memory. */
function envWith(assets) {
  const store = memStore();
  const objects = memObjects();
  return {
    env: {
      DS_ADMIN_KEY: 'admin-key-placeholder-for-tests',
      DS_STUDIO: {
        get: async (k) => store.kvGet(k),
        put: async (k, v) => store.kvPut(k, v),
        delete: async (k) => store.kvDelete(k),
        list: async ({ prefix }) => ({ keys: (await store.kvList(prefix)).map((name) => ({ name })), list_complete: true }),
      },
      DRAMA_STUDIO: {
        get: async (p) => {
          const found = await objects.objectGet(p);
          return found ? { text: async () => found.value } : null;
        },
        put: async (p, v) => objects.objectPut(p, v),
      },
      DS_UPLOAD_ASSETS: assets,
    },
  };
}

/** The real bundle's shape: the page files, plus the junk the bundle carries. */
const BUNDLE = {
  '/index.html': '<html>studio</html>',
  '/studio.js': 'window.studio = 1;',
  '/studio.css': 'body{}',
  '/qr.js': 'export const qr = 1;',
  '/download.js': 'export const download = 1;',
  '/api-client.js': 'export const api = 1;',
  '/service-client.js': 'export const svc = 1;',
  '/approvals-view.js': 'export const view = 1;',
  '/questions.json': '[]',
  '/admin/index.html': '<html>admin</html>',
  '/admin/lib/admin_client.js': 'export const admin = 1;',
  '/admin/lib/qr.js': 'export const qr = 1;',
  '/upload/index.html': '<html>upload</html>',
  '/upload/upload.js': 'export const upload = 1;',
  // Everything below must NEVER be served on the client's domain.
  '/checks/run-all.sh': '#!/usr/bin/env bash',
  '/checks/ui-contract.mjs': 'x',
  '/admin/test/pairing.test.mjs': 'x',
  '/admin/prove/prove_pairing_guardrails.mjs': 'x',
  '/upload/fragment-check.mjs': 'x',
  '/package.json': '{"name":"ui"}',
  '/README.md': '# ui',
  '/push.js': 'export const push = 1;',
  '/.assetsignore': 'checks/',
  '/admin/.env': 'SECRET=1',
};

async function ask(path) {
  const assets = assetsBinding(BUNDLE);
  const { env } = envWith(assets);
  const response = await worker.fetch(new Request(`${ORIGIN}${path}`), { ...env });
  return { response, asked: assets.asked };
}

// ---------------------------------------------------------------------------
// (a) Every allow-listed page path is served 200 — the studio page still works.
// ---------------------------------------------------------------------------

test('allow-list: every page file the studio needs is served 200', async () => {
  const pages = [
    ['/', '/index.html'],
    ['/index.html', '/index.html'],
    ['/studio.js', '/studio.js'],
    ['/studio.css', '/studio.css'],
    ['/qr.js', '/qr.js'],
    ['/download.js', '/download.js'],
    ['/api-client.js', '/api-client.js'],
    ['/service-client.js', '/service-client.js'],
    ['/approvals-view.js', '/approvals-view.js'],
    ['/questions.json', '/questions.json'],
    ['/admin', '/admin/index.html'],
    ['/admin/', '/admin/index.html'],
    ['/admin/index.html', '/admin/index.html'],
    ['/admin/lib/admin_client.js', '/admin/lib/admin_client.js'],
    ['/admin/lib/qr.js', '/admin/lib/qr.js'],
    ['/uploads', '/upload/index.html'],
    ['/upload.js', '/upload/upload.js'],
    ['/upload/index.html', '/upload/index.html'],
    ['/upload/upload.js', '/upload/upload.js'],
  ];

  for (const [path, file] of pages) {
    const { response, asked } = await ask(path);
    assert.equal(response.status, 200, `${path} is on the allow-list`);
    assert.equal(asked[asked.length - 1], file, `${path} maps onto ${file}`);
    assert.equal(response.headers.get('Cache-Control'), 'no-store', path);
    assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/, path);
    assert.match(
      response.headers.get('Content-Security-Policy'),
      /connect-src 'self' https:\/\/\*\.r2\.cloudflarestorage\.com/,
      path,
    );
    assert.equal(response.headers.get('X-Content-Type-Options'), 'nosniff', path);
    assert.equal(response.headers.get('Referrer-Policy'), 'no-referrer', path);
  }
});

test('allow-list: /uploads keeps serving the upload page (the phone needs it)', async () => {
  const { response } = await ask('/uploads');
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '<html>upload</html>');
});

// ---------------------------------------------------------------------------
// (b) Everything else 404s AND never reaches the assets binding.
// ---------------------------------------------------------------------------

test('allow-list: the checks, the tests, the prover, the junk and the dotfiles 404', async () => {
  const refused = [
    '/checks/run-all.sh',
    '/checks/ui-contract.mjs',
    '/checks/README.md',
    '/admin/test/pairing.test.mjs',
    '/admin/test/',
    '/admin/prove/prove_pairing_guardrails.mjs',
    '/admin/prove/',
    '/admin/lib/',
    '/admin/lib/admin_client.js.map',
    '/admin/lib/notjs.txt',
    '/upload/fragment-check.mjs',
    '/package.json',
    '/README.md',
    '/push.js',
    '/.assetsignore',
    '/ui/.assetsignore',
    '/admin/.env',
    '/.env',
    '/checks',
    '/nope.js',
  ];

  for (const path of refused) {
    const { response, asked } = await ask(path);
    assert.equal(response.status, 404, `${path} is refused`);
    assert.deepEqual(asked, [], `${path} never reaches the assets binding`);
    const body = await response.json();
    assert.equal(body.ok, false, path);
  }
});

test('allow-list: a traversal attempt cannot reach anything outside the list', async () => {
  const traversals = [
    '/../package.json',
    '/../../package.json',
    '/index.html/../checks/run-all.sh',
    '/%2e%2e/checks/run-all.sh',
    '/%2e%2e%2fpackage.json',
    '/.%2e/checks/run-all.sh',
    '/admin/%2e%2e/checks/run-all.sh',
    '/%2e%2e/%2e%2e/etc/passwd',
    '/..%2fpackage.json',
    '/studio.js%00.png',
    '/studio.js%2f..%2fchecks',
    '/\\..\\package.json',
  ];

  for (const path of traversals) {
    const { response, asked } = await ask(path);
    assert.equal(response.status, 404, `${path} is refused`);
    assert.deepEqual(asked, [], `${path} never reaches the assets binding`);
  }
});

test('allow-list: a malformed percent-escape is refused, never passed through', async () => {
  for (const path of ['/%ZZ', '/%2e%ZZ', '/index.html%']) {
    const { response, asked } = await ask(path);
    assert.equal(response.status, 404, path);
    assert.deepEqual(asked, [], path);
  }
});

test('allow-list: the bundle ships the ignore list that keeps the junk out of it', async () => {
  const fs = await import('node:fs/promises');
  const ignore = await fs.readFile(
    new URL('../../ui/.assetsignore', import.meta.url),
    'utf8',
  );
  for (const pattern of ['checks/', 'admin/test/', 'admin/prove/', 'upload/fragment-check.mjs', 'package.json', 'README.md']) {
    assert.ok(ignore.split('\n').some((l) => l.trim() === pattern), `.assetsignore lists ${pattern}`);
  }
});

// ---------------------------------------------------------------------------
// (c) /api/* is never handed to the assets binding.
// ---------------------------------------------------------------------------

test('allow-list: /api/* never reaches the assets binding', async () => {
  const { response, asked } = await ask('/api/studio/health');
  assert.equal(response.status, 200);
  assert.equal((await response.json()).ok, true);
  assert.deepEqual(asked, [], 'API routes stay in handle()');

  for (const path of ['/api/', '/api/checks/run-all.sh', '/api/studio/push']) {
    const seen = await ask(path);
    assert.deepEqual(seen.asked, [], path);
  }
});

test('allow-list: the fall-through is a clean 404, not a crash', async () => {
  for (const path of ['/checks/run-all.sh', '/package.json']) {
    const { response } = await ask(path);
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('Content-Type'), 'application/json; charset=utf-8');
    const body = await response.json();
    assert.equal(body.code, 'AF-DS-ASSET-NOT-ALLOWED');
    assert.equal(body.ok, false);
  }
});
