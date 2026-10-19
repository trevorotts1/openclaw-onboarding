/**
 * F-seatdata: the chamber seat data is real (copied from each shipped pack,
 * guarded against drift) and the bust portraits are transparent cutouts.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
import { SEAT_IDS } from '../src/contracts/enums.ts';

const runtimeDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const chamber = join(runtimeDir, 'public', 'chamber');
const advisors = join(runtimeDir, '..', 'advisors');

interface Seat {
  id: string;
  name: string;
  short: string;
  pill?: string;
  domain: string;
  owns: string;
  weighing: string;
  sources: string[];
  disclaimer: string;
}
interface Seats {
  order: string[];
  get(id: string): Seat;
  portraitSources(id: string): string[];
}

const sandbox: { councilChamber?: { seats: Seats } } = {};
runInNewContext(readFileSync(join(chamber, 'chamber-seats.js'), 'utf8'), sandbox);
const seats = sandbox.councilChamber!.seats;

const profile = (id: string) =>
  JSON.parse(readFileSync(join(advisors, id, 'profile.json'), 'utf8')) as {
    name: string;
    role: string;
    owned_question: string;
    source_basis: Array<{ title: string }>;
  };

test('order is the canonical roster', () => {
  assert.deepEqual([...seats.order], [...SEAT_IDS]);
});

test('name, domain, owns and sources equal the shipped profile.json (drift guard)', () => {
  for (const id of seats.order) {
    const p = profile(id);
    const s = seats.get(id);
    assert.equal(s.id, id);
    assert.equal(s.name, p.name, `${id} name`);
    assert.equal(s.domain, p.role, `${id} domain`);
    assert.equal(s.owns, p.owned_question, `${id} owns`);
    assert.deepEqual([...s.sources], p.source_basis.map((b) => b.title), `${id} sources`);
  }
});

test('short names are unique and weighing lines are well formed', () => {
  const shorts = Array.from(seats.order, (id) => seats.get(id).short);
  assert.equal(new Set(shorts).size, shorts.length);
  assert.deepEqual(shorts, ['Sinek', 'Jakes', 'Oprah', 'Aliche', 'Brunson', 'Obama', 'Brené Brown', 'Kimbro', 'Les Brown']);
  assert.equal(seats.get('dennis-kimbro').pill, 'Dennis Kimbro');
  for (const id of seats.order) {
    const w = seats.get(id).weighing;
    assert.ok(w.length > 0 && w.length <= 90, `${id} weighing length ${w.length}`);
    assert.match(w, /^[a-z]/, `${id} starts lowercase`);
    assert.match(w, /\?$/, `${id} ends with ?`);
  }
});

test('disclaimer names the author and book titles and ends Not the person', () => {
  for (const id of seats.order) {
    const s = seats.get(id);
    assert.match(s.disclaimer, /^A simulated advisor built from .+'s public work \(.+\)\. Not the person\.$/);
    assert.equal(s.disclaimer, `A simulated advisor built from ${s.name}'s public work (${s.sources.join(', ')}). Not the person.`);
  }
});

test('unknown id gives a neutral object; portrait sources are webp then svg', () => {
  const u = seats.get('nobody');
  assert.equal(u.name, 'nobody');
  assert.equal(u.domain, '');
  assert.equal(u.owns, '');
  assert.equal(u.weighing, '');
  assert.equal(u.disclaimer, '');
  assert.deepEqual([...seats.portraitSources('simon-sinek')], ['portraits/simon-sinek.webp', 'portraits/simon-sinek.svg']);
});

const magick = (args: string[]) => execFileSync('magick', args, { encoding: 'utf8' }).trim();
let hasMagick = true;
try {
  execFileSync('magick', ['-version'], { stdio: 'ignore' });
} catch {
  hasMagick = false;
}

test('generated portraits are 480x600 alpha cutouts with clear corners, <=120KB', { skip: !hasMagick && 'magick missing' }, () => {
  const dir = join(chamber, 'portraits');
  const webps = readdirSync(dir).filter((n) => n.endsWith('.webp'));
  assert.ok(webps.length >= 8, `expected at least 8 portraits, found ${webps.length}`);
  for (const f of webps) {
    assert.ok(seats.order.includes(f.replace(/\.webp$/, '')), `${f} is not a seat`);
    const file = join(dir, f);
    assert.ok(statSync(file).size <= 120 * 1024, `${f} over 120KB`);
    const out = magick([file, '-format', '%w %h %A %[fx:p{0,0}.a] %[fx:p{w-1,0}.a] %[fx:p{0,h-1}.a] %[fx:p{w-1,h-1}.a]', 'info:']).split(' ');
    assert.equal(out[0], '480', `${f} width`);
    assert.equal(out[1], '600', `${f} height`);
    assert.notEqual(out[2], 'False', `${f} has no alpha channel`);
    for (const a of out.slice(3).map(Number)) assert.ok(a < 0.01, `${f} corner alpha ${a}`);
    // The figure itself is opaque and the background is not: guards a cream rectangle.
    const mean = Number(magick([file, '-alpha', 'extract', '-format', '%[fx:mean]', 'info:']));
    assert.ok(mean > 0.3 && mean < 0.8, `${f} alpha coverage ${mean}`);
    // Chest-up framing: the shoulders reach row 590 (clear of the mask edge row) (outside the 70px rounded corners)
    // and the empty space above the head is at most 10% of the frame.
    const bottom = Number(magick([file, '-alpha', 'extract', '-crop', '340x1+70+590', '+repage', '-format', '%[fx:mean]', 'info:']));
    assert.ok(bottom > 0.8, `${f} bottom row not opaque (${bottom}): chest cut off`);
    const trimmed = magick([file, '-alpha', 'extract', '-threshold', '10%', '-bordercolor', 'black', '-border', '1', '-format', '%@', 'info:']);
    const top = Number(trimmed.split('+')[2]) - 1;
    assert.ok(top <= 60, `${f} figure starts ${top}px down, more than 10% headroom`);
  }
});

test('nothing but svg and webp portraits is shipped; scripts are not packaged', () => {
  for (const f of readdirSync(join(chamber, 'portraits'))) assert.match(f, /\.(svg|webp)$/);
  assert.equal(existsSync(join(chamber, 'portraits', 'originals')), false);
  const files = (JSON.parse(readFileSync(join(runtimeDir, 'package.json'), 'utf8')) as { files: string[] }).files;
  assert.ok(!files.some((f) => f.startsWith('scripts')));
});

test('portrait script exits 0 and reports a missing source, idempotently', { skip: !hasMagick && 'magick missing' }, () => {
  // Empty source dir: every seat is reported missing, nothing is written or removed.
  const empty = mkdtempSync(join(tmpdir(), 'chamber-empty-src-'));
  const before = readdirSync(join(chamber, 'portraits')).sort();
  const out = execFileSync('node', [join(runtimeDir, 'scripts', 'build-chamber-portraits.mjs'), empty], { encoding: 'utf8' });
  assert.match(out, /missing sources: simon-sinek, .*oprah-winfrey/);
  assert.deepEqual(readdirSync(join(chamber, 'portraits')).sort(), before);
});
