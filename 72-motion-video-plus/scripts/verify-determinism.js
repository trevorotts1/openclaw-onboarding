#!/usr/bin/env node
/*
 * Skill 72 determinism verifier.
 *
 * A scene animation is a pure function of t: the same t must paint the same
 * pixels whether the frame is rendered cold (fresh page, direct seek) or
 * after the page has previously painted other times. State leaking between
 * frames (timers, unseeded randomness, GPU-layer raster caches) shows up as
 * pixel drift here, long before it ruins a full render.
 *
 * For each probe time t: render cold on a fresh page, then render again on a
 * page that has already painted several other times, and compare the pair
 * with FFmpeg's psnr filter. Any pair under --threshold-db fails the gate.
 *
 * Headless only, always. Browsers close in finally blocks.
 *
 * Usage:
 *   node scripts/verify-determinism.js --manifest run/manifest.json \
 *     --scene scene-01 [--probes 12] [--threshold-db 60]
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');
const { chromium } = require('playwright-core');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return def;
  if (process.argv[i + 1] && !process.argv[i + 1].startsWith('--')) return process.argv[i + 1];
  return true;
}
function has(name) { return process.argv.includes('--' + name); }
function log(msg) { process.stderr.write(new Date().toISOString() + ' ' + msg + '\n'); }

// Deterministic pseudo-random times for the "seek elsewhere first" path.
function lcg(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

async function shoot(page, t, out) {
  await page.evaluate((tt) => window.__setTime(tt), t);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
  await page.locator('#stage').screenshot({ path: out });
}

function psnrDb(a, b) {
  // psnr stats print to stderr, so use spawnSync and read r.stderr
  const r = spawnSync('ffmpeg', ['-hide_banner', '-i', a, '-i', b,
    '-lavfi', 'psnr', '-f', 'null', '-'], { encoding: 'utf8' });
  const m = (r.stderr || '').match(/average:([0-9.]+|inf)/);
  if (!m) throw new Error('could not parse psnr output');
  return m[1] === 'inf' ? Infinity : parseFloat(m[1]);
}

async function main() {
  const manifestPath = arg('manifest');
  const sceneId = arg('scene');
  const nProbes = parseInt(arg('probes', '12'), 10);
  const thresholdDb = parseFloat(arg('threshold-db', '60'));
  if (!manifestPath || !sceneId) {
    log('usage: verify-determinism.js --manifest M --scene ID [--probes 12] [--threshold-db 60]');
    process.exit(2);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const scene = manifest.scenes.find(s => s.id === sceneId);
  if (!scene) { log('scene not found: ' + sceneId); process.exit(2); }
  const htmlPath = path.resolve(path.dirname(manifestPath), scene.file);
  if (!fs.existsSync(htmlPath)) { log('missing scene file: ' + htmlPath); process.exit(2); }

  const dur = scene.duration_seconds;
  const probes = [];
  for (let i = 0; i < nProbes; i++) probes.push((dur * (i + 0.5)) / nProbes);
  const rand = lcg(1234);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mvplus-det-'));

  let browser = null;
  let failed = 0;
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

    // One shared page for the "seek elsewhere first" renders.
    const seekPage = await browser.newPage({ viewport: { width: manifest.width, height: manifest.height } });
    await seekPage.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
    await seekPage.evaluate(() => document.fonts.ready);
    if (!(await seekPage.evaluate(() => typeof window.__setTime === 'function'))) {
      throw new Error('scene does not expose window.__setTime(t): ' + scene.file);
    }

    for (let i = 0; i < probes.length; i++) {
      const t = probes[i];
      const coldP = path.join(tmp, 'cold_' + i + '.png');
      const seekP = path.join(tmp, 'seek_' + i + '.png');

      // Cold: brand-new page, direct seek.
      let coldBrowser = null;
      try {
        coldBrowser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
        const coldPage = await coldBrowser.newPage({ viewport: { width: manifest.width, height: manifest.height } });
        await coldPage.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
        await coldPage.evaluate(() => document.fonts.ready);
        await shoot(coldPage, t, coldP);
      } finally {
        if (coldBrowser) await coldBrowser.close();
      }

      // Seeked: paint three other times first, then come back to t.
      for (let k = 0; k < 3; k++) await shoot(seekPage, rand() * dur, path.join(tmp, 'junk_' + i + '_' + k + '.png'));
      await shoot(seekPage, t, seekP);

      const db = psnrDb(coldP, seekP);
      const ok = db === Infinity || db >= thresholdDb;
      log('probe t=' + t.toFixed(3) + 's psnr=' + (db === Infinity ? 'inf' : db.toFixed(2)) + 'dB ' + (ok ? 'OK' : 'DRIFT'));
      if (!ok) failed++;
    }
    await seekPage.close();
  } finally {
    if (browser) await browser.close();
  }

  fs.rmSync(tmp, { recursive: true, force: true });
  if (failed > 0) {
    log('DETERMINISM FAIL: ' + failed + '/' + probes.length + ' probes drifted. ' +
        'Likely causes: timers, unseeded Math.random, or GPU-layer tricks ' +
        '(translate3d/translateZ(0)/will-change). See references/animation-contract.md.');
    process.exit(1);
  }
  log('determinism OK: ' + probes.length + ' probes, no drift above threshold');
}

main().catch(e => { log('FATAL: ' + (e && e.stack || e)); process.exit(1); });
