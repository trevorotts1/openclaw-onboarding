import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { SEAT_IDS, type SeatId } from '../src/contracts/index.js';
import { CouncilError } from '../src/cli/errors.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { loadInstalledSeatPack } from '../src/cli/installed-seat-pack.js';
import { tempDataDir } from './helpers.js';

const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('all nine real installed advisor packs load distinct, bounded briefing contexts', () => {
  const seen = new Set<string>();
  for (const seatId of SEAT_IDS) {
    const pack = loadInstalledSeatPack(skillRoot, seatId);
    assert.ok(pack.pack_version.includes('+sha256.'), seatId);
    assert.ok(pack.briefing_text.includes(`seat_id=${seatId}`), seatId);
    assert.ok(pack.briefing_text.includes('ADVISOR BRIEFING'), seatId);
    assert.ok(pack.briefing_text.includes('SHARED FRAMEWORK EXCERPTS'), seatId);
    assert.ok(pack.briefing_text.includes('SHARED DECISION RULE EXCERPTS'), seatId);
    const sourceFrameworks = JSON.parse(readFileSync(join(skillRoot, 'advisors', seatId, 'frameworks.json'), 'utf8')).items;
    const extracted = JSON.parse(pack.briefing_text.split('SHARED FRAMEWORK EXCERPTS (existing pack; attribution unchanged):\n')[1].split('\n\n')[0]).items;
    if (sourceFrameworks.length) {
      assert.ok(extracted.length, `${seatId}: existing framework content must reach the prompt`);
      const field = ['summary', 'concept', 'application', 'description'].find((key) => sourceFrameworks[0][key]);
      assert.ok(field, `${seatId}: substantive source field exists`);
      assert.deepEqual(extracted[0][field], sourceFrameworks[0][field]);
    }
    assert.ok(pack.briefing_text.length > 500, seatId);
    assert.ok(pack.briefing_text.length <= 20000, seatId);
    assert.equal(seen.has(pack.pack_version), false, `${seatId} should have its own frozen hash`);
    seen.add(pack.pack_version);
  }
  assert.equal(seen.size, 9);
});

test('standalone host makes real advisor pack context available to the engine', async () => {
  const local = createLocalHost({
    dataDir: tempDataDir('installed-seat-loader'),
    skillRoot,
    discoverRoutes: false,
  });
  const pack = await local.host.evidence.loadSeatPack('simon-sinek');
  assert.ok(pack);
  assert.match(pack.briefing_text, /Start with Why/);
  assert.match(pack.briefing_text, /Source qualification/);
});

test('packs cannot leak user-private source material into a shared prompt', () => {
  const pack = loadInstalledSeatPack(skillRoot, 'russell-brunson');
  assert.doesNotMatch(pack.briefing_text, /user_private/);
  assert.doesNotMatch(pack.briefing_text, /private_scope/);
  const frameworks = JSON.parse(readFileSync(join(skillRoot, 'advisors/russell-brunson/frameworks.json'), 'utf8'));
  for (const item of frameworks.items.filter((item: { scope?: string }) => item.scope === 'private_scope')) {
    assert.equal(pack.briefing_text.includes(item.id), false);
  }
  assert.match(pack.briefing_text, /rule-demand-before-diagram/);
  assert.match(pack.briefing_text, /blackceo_adaptation/);
});

test('existing structured frameworks and rules reach the prompt without claiming new source approval', () => {
  const pack = loadInstalledSeatPack(skillRoot, 'simon-sinek');
  const frameworks = JSON.parse(readFileSync(join(skillRoot, 'advisors/simon-sinek/frameworks.json'), 'utf8'));
  const rules = JSON.parse(readFileSync(join(skillRoot, 'advisors/simon-sinek/decision-rules.json'), 'utf8'));
  const serializedFrameworks = pack.briefing_text.split('SHARED FRAMEWORK EXCERPTS (existing pack; attribution unchanged):\n')[1].split('\n\n')[0];
  const serializedRules = pack.briefing_text.split('SHARED DECISION RULE EXCERPTS (existing pack; attribution unchanged):\n')[1];
  assert.ok(frameworks.items[0].concept.length > 0);
  assert.equal(JSON.parse(serializedFrameworks).items[0].concept, frameworks.items[0].concept);
  assert.equal(JSON.parse(serializedRules).items[0].rule, rules.items[0].rule);
  assert.match(pack.briefing_text, /bibliographic_only/);
});

test('missing, modified or wrong-seat installed pack fails before any request', () => {
  const temp = mkdtempSync(join(tmpdir(), 'council-pack-check-'));
  const seat = 'simon-sinek';
  const source = join(skillRoot, 'advisors', seat);
  try {
    cpSync(source, join(temp, 'advisors', seat), { recursive: true });
    cpSync(join(skillRoot, 'manifest.json'), join(temp, 'manifest.json'));
    assert.ok(loadInstalledSeatPack(temp, seat).briefing_text);
    writeFileSync(join(temp, 'advisors', seat, 'briefing.md'), '# tampered');
    assert.throws(() => loadInstalledSeatPack(temp, seat), (err: unknown) =>
      err instanceof CouncilError && err.code === 'COUNCIL_STORE_UNAVAILABLE');
    cpSync(join(source, 'briefing.md'), join(temp, 'advisors', seat, 'briefing.md'));
    cpSync(join(source, 'profile.json'), join(temp, 'advisors', seat, 'profile.json'));
    unlinkSync(join(temp, 'advisors', seat, 'profile.json'));
    assert.throws(() => loadInstalledSeatPack(temp, seat), CouncilError);
    assert.throws(() => loadInstalledSeatPack(temp, '../../other' as SeatId), CouncilError);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
