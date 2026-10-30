/**
 * CTR-147 integration regression. INTENTIONALLY UNEXECUTED in this lane:
 * Trevor owns the run. It is a static contract check over the shipped
 * source and packaged assets, not a renderer, browser, HTTP or live
 * council probe.
 *
 * It covers the requirement matrix this integration must not regress:
 *   - production capability-snapshot wiring in the service composition;
 *   - the 14pt absolute floor and 15pt body on every print path;
 *   - packaged report assets, identities and the 900k data-URI ceiling;
 *   - privacy: names/descriptions only, no prompts, memory or secrets;
 *   - honest missing-dependency rendering;
 *   - the cue files in the front-door allowlist and the chamber page.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const skillDir = join(runtimeDir, '..');
const read = (relative: string): string => readFileSync(join(runtimeDir, relative), 'utf8');
const sha256 = (path: string): string =>
  createHash('sha256').update(readFileSync(path)).digest('hex');

test('production composition wires the installation-bound capability snapshot', () => {
  const composition = read(join('src', 'service', 'composition.ts'));
  assert.match(composition, /capabilitySnapshot:\s*\(\{\s*installationId,\s*capturedAt\s*\}\)/);
  assert.match(composition, /openclawRoot\(\)/);
  assert.match(composition, /discoverInstallationCapabilities\(\{/);
  assert.match(composition, /installationId !== installation\.installation_id/);
  assert.match(composition, /capabilitySnapshots\.get\(cacheKey\)/);
  assert.match(composition, /coverImageDataUri:\s*\(\)\s*=>\s*loadReportCoverDataUri\(\)/);
  assert.doesNotMatch(composition, /\/Users\/blackceomacmini/);
});

test('capability discovery reads names and descriptions only', () => {
  const source = read(join('src', 'reports', 'capability-snapshot.ts'));
  assert.match(source, /SKILL\.md/);
  assert.match(source, /slice\(0,\s*12_000\)/);
  for (const forbidden of [
    'MEMORY.md',
    '.env',
    'secrets',
    'config.json',
    'process.env',
    'fetch(',
    'https://',
    'http://',
  ]) {
    assert.equal(
      source.includes(forbidden),
      false,
      `capability discovery must not touch ${forbidden}`,
    );
  }
});

test('print CSS: body 15pt and every declared font size at least 14pt', () => {
  const render = read(join('src', 'reports', 'render.ts'));
  const sizes = [...render.matchAll(/font-size:\s*([0-9.]+)pt/g)].map((match) =>
    Number(match[1]),
  );
  assert.ok(sizes.length >= 10, 'the print stylesheet declares explicit sizes');
  assert.ok(
    sizes.every((size) => size >= 14),
    `every font-size must be >= 14pt, saw ${sizes.filter((size) => size < 14).join(', ')}`,
  );
  assert.match(render, /body\s*\{[^}]*font-size:\s*15pt/s);
  assert.match(render, /@bottom-center\s*\{[^}]*font-size:\s*14pt/s);
  assert.match(render, /--gold-text:\s*#7A5C1F;/);
  assert.match(render, /--gold-rule:\s*#B08A3E;/);
  assert.doesNotMatch(render, /(?:^|[;{\s])color:\s*var\(--gold-rule\)/m);
});

test('packaged report assets exist, carry their manifest identities, and fit the embed ceiling', () => {
  const reportDir = join(runtimeDir, 'public', 'report');
  const manifest = JSON.parse(
    readFileSync(join(reportDir, 'ASSET-MANIFEST.json'), 'utf8'),
  ) as {
    derivatives: Array<{ id: string; path: string; sha256: string; data_uri_chars: number; bytes: number }>;
    originals_unchanged: Record<string, { path: string; sha256: string } | string>;
    embed_limits: { cover_data_uri_max_chars: number };
  };
  for (const derivative of manifest.derivatives) {
    const path = join(runtimeDir, derivative.path);
    assert.ok(existsSync(path), `${derivative.path} must ship`);
    assert.equal(sha256(path), derivative.sha256, `${derivative.id} identity`);
    assert.ok(
      derivative.data_uri_chars < manifest.embed_limits.cover_data_uri_max_chars,
      `${derivative.id} data URI stays under the report ceiling`,
    );
  }
  const originals = manifest.originals_unchanged;
  for (const key of ['hero', 'page_frame', 'section_divider']) {
    const entry = originals[key] as { path: string; sha256: string };
    const path = join(skillDir, entry.path);
    assert.ok(existsSync(path), `${entry.path} original must remain on disk`);
    assert.equal(sha256(path), entry.sha256, `${key} original unchanged`);
  }
  const cover = manifest.derivatives.find((entry) => entry.id === 'cover-report');
  assert.ok(cover && cover.data_uri_chars < 900000);
});

test('print document never embeds a local path or a network URL', () => {
  const render = read(join('src', 'reports', 'render.ts'));
  const asset = read(join('src', 'reports', 'asset-embed.ts'));
  for (const source of [render, asset]) {
    assert.doesNotMatch(source, /\/Users\//);
    assert.doesNotMatch(source, /file:\/\//);
    assert.doesNotMatch(source, /https?:\/\//);
  }
});

test('a missing recorded dependency is stated, not hidden', () => {
  const render = read(join('src', 'reports', 'render.ts'));
  const model = read(join('src', 'reports', 'model.ts'));
  assert.match(model, /depends_on_missing_action_ids/);
  assert.match(render, /depends_on_missing_action_ids/);
  assert.match(render, /a recorded dependency is not in this plan/);
});

test('assumptions and unknowns are printed once, not duplicated', () => {
  const render = read(join('src', 'reports', 'render.ts'));
  const conditions = render.slice(
    render.indexOf('function pushConditionsMd'),
    render.indexOf('function pushAmendmentsMd'),
  );
  assert.ok(conditions.length > 0);
  assert.doesNotMatch(conditions, /Assumptions:/);
  assert.doesNotMatch(conditions, /Unknowns:/);
});

test('cue assets are served, mapped in the allowlist, and packaged', () => {
  const html = readFileSync(join(runtimeDir, 'public', 'chamber', 'index.html'), 'utf8');
  const door = read(join('src', 'service', 'front-door.ts'));
  assert.match(html, /href="\.\/chamber-cue\.css"/);
  assert.match(html, /src="\.\/chamber-cue\.js"/);
  assert.match(door, /\['chamber-cue\.css', 'text\/css; charset=utf-8'\]/);
  assert.match(door, /\['chamber-cue\.js', 'text\/javascript; charset=utf-8'\]/);
  assert.ok(existsSync(join(runtimeDir, 'public', 'chamber', 'chamber-cue.css')));
  assert.ok(existsSync(join(runtimeDir, 'public', 'chamber', 'chamber-cue.js')));
  const pkg = JSON.parse(readFileSync(join(runtimeDir, 'package.json'), 'utf8')) as {
    files: string[];
  };
  assert.deepEqual(pkg.files, ['dist', 'public/chamber', 'public/report']);
});
