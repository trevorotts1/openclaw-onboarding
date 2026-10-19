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

test('every chamber file the front door serves exists on disk', () => {
  const chamber = join(runtimeDir, 'public', 'chamber');
  for (const name of [
    'index.html',
    'advisors.html',
    'not-packaged.html',
    'council-theme.css',
    'council-room.css',
    'council-journey.css',
    'RECEIPT.md',
  ]) {
    assert.ok(existsSync(join(chamber, name)), `${name} must exist`);
  }
  const portraits = readdirSync(join(chamber, 'portraits')).filter((n) => n.endsWith('.svg'));
  assert.ok(portraits.length > 0, 'portrait svgs must exist');
});
