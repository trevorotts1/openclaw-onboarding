/**
 * Packaging guarantee (W25): the installable tarball carries the chamber.
 *
 * `files` is npm's pack allowlist. `public/chamber/` is the directory
 * front-door.ts resolves through CHAMBER_ASSET_ROOTS when serving
 * GET /chamber/*; if the allowlist omits it, every tarball install serves
 * 404 for the chamber even though the development checkout serves 200.
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(runtimeDir, 'package.json'), 'utf8')) as {
  main: string;
  bin: Record<string, string>;
  files: string[];
};

test('package files allowlist carries dist and the chamber assets', () => {
  assert.deepEqual(pkg.files, ['dist', 'public/chamber']);
  assert.equal(pkg.main, 'dist/index.js');
  assert.equal(pkg.bin['blackceo-council'], 'dist/blackceo-council.mjs');
});

/**
 * Files other W29 units own (theme, decision, room, key points, seat card,
 * seat data and state). They land in their own branches; unit A's lane may
 * run before they merge, so only these may be missing, and the missing list
 * is printed. After integration the list is empty and every file is checked.
 */
const OTHER_UNIT_FILES = [
  'chamber-theme.css',
  'chamber-decision.css',
  'chamber-room.css',
  'chamber-keypoints.css',
  'chamber-seatcard.css',
  'chamber-seats.js',
  'chamber-state.js',
  'chamber-decision.js',
  'chamber-room.js',
  'chamber-keypoints.js',
  'chamber-seatcard.js',
  'demo-replay.json',
];

test('every chamber file the front door serves exists on disk', (t) => {
  const chamber = join(runtimeDir, 'public', 'chamber');
  for (const name of [
    'index.html',
    'advisors.html',
    'not-packaged.html',
    'council-theme.css',
    'council-room.css',
    'council-journey.css',
    'chamber-shell.css',
    'chamber-shell.js',
    'chamber-live.js',
    'blackceo-logo.png',
    'RECEIPT.md',
  ]) {
    assert.ok(existsSync(join(chamber, name)), `${name} must exist`);
  }
  const missing = OTHER_UNIT_FILES.filter((name) => !existsSync(join(chamber, name)));
  // Strict once the four renderer units have landed (or when forced): then nothing may be missing.
  const strict =
    process.env.CHAMBER_REQUIRE_ALL === '1' ||
    ['chamber-decision.js', 'chamber-room.js', 'chamber-keypoints.js', 'chamber-seatcard.js'].every((n) =>
      existsSync(join(chamber, n)),
    );
  assert.ok(!strict || missing.length === 0, `integrated chamber is missing: ${missing.join(', ')}`);
  if (missing.length > 0) t.diagnostic(`other units' files not merged yet: ${missing.join(', ')}`);
  const portraits = readdirSync(join(chamber, 'portraits')).filter((n) => /\.(svg|webp)$/.test(n));
  assert.ok(portraits.length > 0, 'portrait svgs or webps must exist');
  assert.ok(
    portraits.some((n) => n.endsWith('.svg')),
    'the svg fallback portraits must still exist',
  );
});

test('every stylesheet and script the chamber page loads is on the front door allowlist', () => {
  const html = readFileSync(join(runtimeDir, 'public', 'chamber', 'index.html'), 'utf8');
  const door = readFileSync(join(runtimeDir, 'src', 'service', 'front-door.ts'), 'utf8');
  const refs = [...html.matchAll(/(?:href|src)="\.\/([A-Za-z0-9._-]+\.(?:css|js))"/g)].map((m) => m[1]);
  assert.ok(refs.length >= 14, 'the page loads six stylesheets and eight scripts');
  for (const name of refs) {
    assert.ok(door.includes(`['${name}',`), `${name} must be in CHAMBER_ROOT_FILES`);
  }
});
