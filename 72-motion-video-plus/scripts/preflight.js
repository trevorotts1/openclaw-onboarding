#!/usr/bin/env node
/*
 * Skill 72 preflight.
 *
 * Runs on the host BEFORE every render. Detects CPU cores, free RAM, free
 * disk, then calibrates by rendering 20 real frames to measure the true
 * per-frame rate. The calibration ALSO measures system load with one
 * browser active, and the worker recommendation is capped from that
 * measurement: workers are PROVEN against load, never recommended from
 * core count alone (lesson: 6 workers drove load to 21 on the 12-CPU
 * reference box). Says plainly when the segment route is required
 * instead of dying halfway. Never hardcodes worker counts.
 *
 * Usage:
 *   node scripts/preflight.js --manifest run/manifest.json [--max-hours 8]
 *
 * Exits 0 with a JSON report on stdout. Exits 3 with a plain-language
 * refusal when disk cannot hold the peak or time blows the budget.
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright-core');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return def;
  return process.argv[i + 1];
}
const GB = 1024 * 1024 * 1024;
const PNG_BYTES_EST = 400 * 1024; // measured ~359MB for 909 frames on the reference run
const BROWSER_RAM_BYTES = 500 * 1024 * 1024; // budget per headless browser
// Measured on the 12-CPU / 24GB reference box: 0.56s per frame per worker.
// The 20-frame calibration below refines this per machine; this figure is
// the baseline it is sanity-checked against, not a value the plan assumes.
const REFERENCE_PER_FRAME_SEC = 0.56;
const LOAD_HEADROOM = 0.85; // never plan sustained load above 85% of core count
const MIN_PER_WORKER_LOAD = 0.25; // a headless Chromium doing full-res screenshots always costs something

function diskFreeBytes(p) {
  const out = execFileSync('df', ['-k', p]).toString().split('\n');
  const parts = out[1].trim().split(/\s+/);
  return parseInt(parts[3], 10) * 1024;
}

async function calibrate() {
  // 20 real frames of a minimal __setTime page: the true per-frame rate.
  // Also samples system load with one browser active, so the worker count
  // can be proven against load instead of assumed from core count.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mvplus-cal-'));
  const html = path.join(dir, 'cal.html');
  fs.writeFileSync(html, '<!doctype html><html><body><div id="stage" style="width:1920px;height:1080px;background:#fff">'
    + '<div id="b" style="position:absolute;font:120px sans-serif">Cal</div></div>'
    + '<script>window.__sceneDuration=5;window.__setTime=function(t){'
    + 'var b=document.getElementById("b");b.style.left=(t*200)+"px";b.style.top=(Math.sin(t)*100+400)+"px";};</script>');
  const loadBefore = os.loadavg()[0];
  let peakLoad = loadBefore;
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await page.goto('file://' + html, { waitUntil: 'networkidle' });
    const t0 = Date.now();
    for (let n = 0; n < 20; n++) {
      await page.evaluate((tt) => window.__setTime(tt), n / 30);
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
      await page.locator('#stage').screenshot({ path: path.join(dir, 'c' + n + '.png') });
      if (n % 5 === 4) {
        const l = os.loadavg()[0];
        if (l > peakLoad) peakLoad = l;
      }
    }
    const perFrameSec = (Date.now() - t0) / 1000 / 20;
    return { perFrameSec, loadBefore, peakLoad };
  } finally {
    await browser.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

async function main() {
  const manifestPath = arg('manifest');
  const maxHours = parseFloat(arg('max-hours', '0'));
  if (!manifestPath) { console.error('usage: preflight.js --manifest M [--max-hours H]'); process.exit(2); }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

  const cores = os.cpus().length;
  const freeMem = os.freemem();
  const totalFrames = manifest.scenes.reduce((a, s) => a + Math.round(s.duration_seconds * manifest.fps), 0);
  const sceneCount = manifest.scenes.length;

  let storageRoot = manifest.storage_root.replace(/^~(?=$|\/|\\)/, os.homedir());
  fs.mkdirSync(storageRoot, { recursive: true });
  const freeDisk = diskFreeBytes(storageRoot);

  const perFrame = await calibrate();
  const perFrameSec = perFrame.perFrameSec;
  // Sanity-check the calibration against the reference measurement.
  if (perFrameSec > REFERENCE_PER_FRAME_SEC * 3 || perFrameSec < REFERENCE_PER_FRAME_SEC / 3) {
    console.error('PREFLIGHT WARNING: measured ' + perFrameSec.toFixed(2) + 's/frame vs the '
      + REFERENCE_PER_FRAME_SEC + 's/frame reference baseline. This box behaves very '
      + 'differently; treat the wall-clock estimate with suspicion.');
  }
  // Prove workers against measured load: one browser added
  // (peakLoad - loadBefore) to the 1-minute average, so cap workers before
  // the projected load crosses 85% of core count. Never from core count alone.
  const perWorkerLoad = Math.max(MIN_PER_WORKER_LOAD, perFrame.peakLoad - perFrame.loadBefore);
  const loadBudget = cores * LOAD_HEADROOM;
  if (perFrame.loadBefore >= loadBudget) {
    console.error('PREFLIGHT WARNING: box is already heavily loaded (1-min load '
      + perFrame.loadBefore.toFixed(1) + ' vs budget ' + loadBudget.toFixed(1) + '). '
      + 'Render will be slow; consider a quieter window.');
  }
  const workersByLoad = Math.max(1, Math.floor((loadBudget - perFrame.loadBefore) / perWorkerLoad));
  const ramWorkers = Math.floor(freeMem / BROWSER_RAM_BYTES);
  const uncapped = Math.max(1, Math.min(cores - 2, ramWorkers, sceneCount));
  const workers = Math.min(uncapped, workersByLoad);
  const loadCapped = workersByLoad < uncapped;
  if (loadCapped) {
    console.error('PREFLIGHT NOTE: worker count capped at ' + workers + ' by measured load '
      + '(est. ' + perWorkerLoad.toFixed(2) + ' load per browser); core/RAM math alone allowed ' + uncapped + '.');
  }
  const wallSec = (totalFrames * perFrameSec) / workers;
  // Peak disk: worst segment's frames alive at once across workers, plus encoded segments.
  const maxSegFrames = Math.max(...manifest.scenes.map(s => Math.round(s.duration_seconds * manifest.fps)));
  const peakBytes = maxSegFrames * PNG_BYTES_EST * Math.min(workers, sceneCount) + totalFrames * 30 * 1024;

  const strong = cores >= 12 && freeMem >= 16 * GB && freeDisk > 100 * GB;
  const segmentMinutes = strong ? 15 : 5; // 5-minute segments are the standard

  const report = {
    cores, free_mem_gb: +(freeMem / GB).toFixed(1), free_disk_gb: +(freeDisk / GB).toFixed(1),
    per_frame_sec: +perFrameSec.toFixed(3), reference_per_frame_sec: REFERENCE_PER_FRAME_SEC,
    total_frames: totalFrames,
    baseline_load_1min: +perFrame.loadBefore.toFixed(2),
    peak_load_during_calibration: +perFrame.peakLoad.toFixed(2),
    per_worker_load_est: +perWorkerLoad.toFixed(2),
    load_capped_workers: loadCapped,
    recommended_workers: workers, estimated_wall_hours: +(wallSec / 3600).toFixed(2),
    peak_disk_gb: +(peakBytes / GB).toFixed(1), segment_minutes: segmentMinutes,
    segment_note: segmentMinutes === 15 ? 'strong system: 15-minute segments certified' : 'standard 5-minute segments',
  };

  if (freeDisk < peakBytes * 1.5) {
    console.error('PREFLIGHT REFUSAL: free disk ' + report.free_disk_gb + 'GB cannot hold estimated peak '
      + report.peak_disk_gb + 'GB with margin. Free disk space or use the segment route with per-scene cleanup, then rerun preflight.');
    process.exit(3);
  }
  if (maxHours > 0 && wallSec / 3600 > maxHours) {
    console.error('PREFLIGHT REFUSAL: estimated ' + report.estimated_wall_hours + 'h exceeds budget of '
      + maxHours + 'h. Options: shorten the video, lower to 24fps, or split into more segments on stronger hardware.');
    process.exit(3);
  }
  console.log(JSON.stringify(report, null, 2));
}

main().catch(e => { console.error('FATAL: ' + (e && e.stack || e)); process.exit(1); });
