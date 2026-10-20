#!/usr/bin/env node
// Builds public/chamber/portraits/<seat>.webp: transparent 480x600 busts.
// Usage: node scripts/build-chamber-portraits.mjs [source-dir]
// source-dir default: ~/.claude/state/council-elders/portraits-cartoon
// (opaque <seat>.webp from the portrait workflow; originals/ is never read).
// Cutout: macOS Vision via portrait-cutout.swift, else an ImageMagick
// flood-fill from the border. Needs magick and cwebp. Seats with no source
// are reported and skipped (exit 0); a source that fails to build exits 1.
// A portrait newer than its source and both scripts is left untouched, so a
// re-run is a no-op (Vision output is not byte-stable); CHAMBER_FORCE=1 rebuilds.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, renameSync, rmSync, statSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const W = 480;
const H = 600;
const here = dirname(fileURLToPath(import.meta.url));
const chamber = resolve(here, '..', 'public', 'chamber');
const outDir = join(chamber, 'portraits');
const srcDir = resolve(process.argv[2] ?? join(homedir(), '.claude/state/council-elders/portraits-cartoon'));

const sandbox = {};
runInNewContext(readFileSync(join(chamber, 'chamber-seats.js'), 'utf8'), sandbox);
const seats = sandbox.councilChamber.seats.order;

const run = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });

function visionCutout(src, dst) {
  if (process.platform !== 'darwin') return false;
  try {
    run('swift', [join(here, 'portrait-cutout.swift'), src, dst]);
    return true;
  } catch {
    return false; // exit 2 (no foreground) or Vision unavailable: fall back
  }
}

function floodCutout(src, dst) {
  // ponytail: assumes a near-uniform background colour sampled at the corner.
  const bg = run('magick', [src, '-format', '%[pixel:p{2,2}]', 'info:']).trim();
  run('magick', [src, '-alpha', 'set', '-bordercolor', bg, '-border', '1', '-fuzz', '9%', '-fill', 'none',
    '-floodfill', '+0+0', bg, '-shave', '1x1', dst]);
}

function build(seat, src) {
  const tmp = mkdtempSync(join(tmpdir(), `chamber-${seat}-`));
  try {
    const cut = join(tmp, 'cut.png');
    const method = visionCutout(src, cut) ? 'vision' : (floodCutout(src, cut), 'flood-fill');
    // Soften the edge: pull the mask in 2px (full-res) so no background fringe
    // survives, then feather it a touch.
    const soft = join(tmp, 'soft.png');
    run('magick', [cut, '-channel', 'A', '-morphology', 'Erode', 'Disk:2', '-blur', '0x1', '+channel', soft]);
    // Crop to the subject, then place it bottom-anchored, centred, in a 4:5 box.
    // At most 10% of the width (shoulder tips) is trimmed; any other shortfall
    // becomes transparent headroom, so heads are never clipped.
    // The subject touches the bottom edge, and %@ trims solid edge rows as
    // background, which cuts the chest off. A 1px black border keeps them.
    const [bw, bh, bxb, byb] = run('magick', [soft, '-alpha', 'extract', '-threshold', '10%', '-bordercolor', 'black', '-border', '1',
      '-format', '%@', 'info:']).trim().split(/[x+]/).map(Number);
    const bx = bxb - 1;
    const by = byb - 1;
    // 4% headroom above the head.
    const w = Math.max(Math.round(bw * 0.9), Math.ceil(bh * 1.04 * 0.8));
    const h = Math.round(w * 1.25);
    const png = join(tmp, 'bust.png');
    run('magick', [soft, '-crop', `${bw}x${bh}+${bx}+${by}`, '+repage', '-gravity', 'south', '-background', 'none',
      '-extent', `${w}x${h}`, '-resize', `${W}x${H}!`,
      // Round the bottom corners like shoulders so the frame edge never shows
      // as a hard square corner (the table hides the rest).
      '(', '-size', `${W}x${H}`, 'xc:none', '-fill', 'white', '-draw', `roundrectangle 0,0 ${W - 1},${H - 1} 70,70`, ')',
      '-compose', 'DstIn', '-composite', png]);
    const out = join(outDir, `${seat}.webp`);
    const part = `${out}.tmp`;
    run('cwebp', ['-quiet', '-q', '82', '-alpha_q', '90', '-f', '0', png, '-o', part]);
    renameSync(part, out);
    return { method, out };
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

function check(out) {
  const [w, h, a0, a1, a2, a3] = run('magick', [out, '-format',
    '%w %h %[fx:p{0,0}.a] %[fx:p{w-1,0}.a] %[fx:p{0,h-1}.a] %[fx:p{w-1,h-1}.a]', 'info:'])
    .trim().split(' ').map(Number);
  const kb = statSync(out).size / 1024;
  const hasAlpha = run('magick', [out, '-format', '%A', 'info:']).trim() !== 'False';
  const ok = w === W && h === H && hasAlpha && [a0, a1, a2, a3].every((a) => a < 0.01) && kb <= 120;
  return { ok, w, h, kb: Math.round(kb) };
}

const missing = [];
let failed = false;
for (const seat of seats) {
  const src = join(srcDir, `${seat}.webp`);
  if (!existsSync(src)) {
    missing.push(seat);
    console.log(`skip ${seat}: no source at ${src}`);
    continue;
  }
  const out0 = join(outDir, `${seat}.webp`);
  const newest = Math.max(...[src, fileURLToPath(import.meta.url), join(here, 'portrait-cutout.swift')].map((f) => statSync(f).mtimeMs));
  if (!process.env.CHAMBER_FORCE && existsSync(out0) && statSync(out0).mtimeMs > newest) {
    console.log(`kept ${seat}: up to date`);
    continue;
  }
  try {
    const { method, out } = build(seat, src);
    const c = check(out);
    console.log(`${c.ok ? 'ok  ' : 'FAIL'} ${seat}: ${c.w}x${c.h} ${c.kb}KB via ${method}`);
    if (!c.ok) failed = true;
  } catch (e) {
    console.error(`FAIL ${seat}: ${e.message.split('\n')[0]}`);
    failed = true;
  }
}
console.log(missing.length ? `missing sources: ${missing.join(', ')}` : 'all nine sources built');
process.exit(failed ? 1 : 0);
