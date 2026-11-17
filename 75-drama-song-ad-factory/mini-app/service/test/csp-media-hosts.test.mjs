// ============================================================================
// csp-media-hosts.test.mjs — the page can play a delivery, and only that
// (S75-070)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/csp-media-hosts.test.mjs
//
// The delivery screen is a <video> player now, so the pages the service serves
// must allow media from the two hosts a finished video is delivered from:
// the Google bucket and the r2.dev domain. The rule is narrow on purpose —
// media-src only. `connect-src` is the surface the page's own fetch code uses
// and it is asserted unchanged, character for character, so a delivery fix can
// never quietly widen what the page may talk to.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import worker from '../src/index.js';

const ORIGIN = 'https://studio.example';

/** The assets binding, shaped like the one worker.fetch is handed in production. */
const assets = {
  fetch: async () => new Response('<html>studio</html>', {
    status: 200,
    headers: { 'Content-Type': 'text/html' },
  }),
};

async function cspFor(path) {
  const response = await worker.fetch(new Request(`${ORIGIN}${path}`), { DS_UPLOAD_ASSETS: assets });
  assert.equal(response.status, 200, `${path} is served`);
  const csp = response.headers.get('Content-Security-Policy');
  assert.ok(csp, `${path} carries a Content-Security-Policy`);
  return csp;
}

function directive(csp, name) {
  const found = new RegExp(`(?:^|;\\s*)${name}([^;]*)`).exec(csp);
  return found ? found[1].trim().split(/\s+/).filter(Boolean) : null;
}

test('media-src names both delivery hosts and keeps its own files and blobs', async () => {
  for (const path of ['/', '/studio.js', '/index.html']) {
    const sources = directive(await cspFor(path), 'media-src');
    assert.ok(sources, `${path}: the CSP has a media-src directive`);
    assert.ok(sources.includes("'self'"), `${path}: media-src still serves the page's own files`);
    assert.ok(sources.includes('blob:'), `${path}: media-src still allows blob: URLs`);
    assert.ok(sources.includes('https://storage.googleapis.com'),
      `${path}: media-src names the Google bucket host`);
    assert.ok(sources.includes('https://*.r2.dev'), `${path}: media-src names the r2.dev delivery host`);
  }
});

test('the delivery hosts are added to media-src only — connect-src is unchanged', async () => {
  for (const path of ['/', '/studio.js', '/admin/index.html']) {
    const csp = await cspFor(path);
    assert.match(csp, /connect-src 'self' https:\/\/\*\.r2\.cloudflarestorage\.com;/,
      `${path}: connect-src is exactly what it was`);
    const connect = directive(csp, 'connect-src') || [];
    assert.ok(!connect.includes('https://storage.googleapis.com'),
      `${path}: connect-src must not name the Google bucket host`);
    assert.ok(!connect.some((source) => source.endsWith('.r2.dev')),
      `${path}: connect-src must not name the r2.dev host`);
  }
});

test('the other directives are untouched', async () => {
  const csp = await cspFor('/studio.js');
  assert.match(csp, /default-src 'self'/, 'default-src is still self only');
  assert.match(csp, /script-src 'self';/, 'script-src is still self only');
  assert.match(csp, /frame-ancestors 'none'/, 'the page still refuses framing');
  assert.ok(!/script-src[^;]*storage\.googleapis\.com/.test(csp), 'no delivery host was added to scripts');
  assert.ok(!/img-src[^;]*r2\.dev/.test(csp), 'no delivery host was added to images');
});
