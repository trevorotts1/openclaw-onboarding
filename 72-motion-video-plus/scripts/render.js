#!/usr/bin/env node
/*
 * Skill 72 frame renderer.
 *
 * Renders ONE scene from a manifest: opens the scene HTML in headless
 * Chromium via playwright-core, seeks window.__setTime(t) per frame,
 * screenshots at the manifest fps, encodes the scene segment with FFmpeg,
 * then deletes the scene PNGs (cleanup is load-bearing: 30s of frames is
 * about 359MB; a 2-hour video would need about 86GB without cleanup).
 *
 * Fresh browser every --chunk-frames (default 300). Chromium died at frame
 * 809 of 909 in testing from memory exhaustion during sequential
 * screenshots, so chunking is not optional.
 *
 * --resume continues from the last completed frame recorded in
 * <outdir>/.render-state.json and never restarts a finished chunk.
 * On encode failure the PNGs are KEPT so --resume can finish the scene;
 * the error message prints the exact cleanup command. On encode success
 * the PNGs are deleted in a finally block.
 *
 * Headless only, always. The browser closes in a finally block.
 *
 * Usage:
 *   node scripts/render.js --manifest run/manifest.json --scene scene-01 \
 *     --outdir work/scenes/scene-01 [--preview] [--resume] [--chunk-frames 300]
 *
 * Review modes (no scene render; each exits after running):
 *   node scripts/render.js --still 12.5 --manifest run/manifest.json \
 *     --scene scene-01 --outdir work/review
 *       Save one timestamped still frame for close inspection.
 *   node scripts/render.js --cliprange 10,15 --manifest run/manifest.json \
 *     --scene scene-01 --outdir work/review
 *       Render a short MP4 clip for motion checks.
 *   node scripts/render.js --mux work/audio/mix2.mp3 --video final.mp4 --out final2.mp4
 *       Re-mux new audio into an existing render without re-rendering video.
 *   node scripts/render.js --beatsheet --beats work/audio/beats.json \
 *     --video final.mp4 --out work/beats.jpg
 *       One frame per beat (a quarter beat after the hit), tiled into a sheet.
 *
 * Run one process per scene in parallel; worker count comes from
 * scripts/preflight.js. Never hardcode it here.
 */
'use strict';
const fs = require('fs');
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

async function main() {
  // ---- review modes (exit after running; no scene render) ----
  if (has('mux')) return void await muxMode();
  if (has('beatsheet')) return void await beatsheetMode();

  const manifestPath = arg('manifest');
  const sceneId = arg('scene');
  const outDir = arg('outdir');
  if (has('still')) return void await stillMode(manifestPath, sceneId, outDir);
  if (has('cliprange')) return void await cliprangeMode(manifestPath, sceneId, outDir);
  const preview = has('preview');
  const resume = has('resume');
  const chunkFrames = parseInt(arg('chunk-frames', '300'), 10);
  if (!manifestPath || !sceneId || !outDir) {
    log('usage: render.js --manifest M --scene ID --outdir D [--preview] [--resume]');
    process.exit(2);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const scene = manifest.scenes.find(s => s.id === sceneId);
  if (!scene) { log('scene not found: ' + sceneId); process.exit(2); }

  const fps = preview ? 15 : manifest.fps;
  const width = preview ? 960 : manifest.width;
  const height = preview ? 540 : manifest.height;
  const totalFrames = Math.round(scene.duration_seconds * fps);
  const htmlPath = path.resolve(path.dirname(manifestPath), scene.file);
  if (!fs.existsSync(htmlPath)) { log('missing scene file: ' + htmlPath); process.exit(2); }

  fs.mkdirSync(outDir, { recursive: true });
  const statePath = path.join(outDir, '.render-state.json');
  let doneThrough = -1;
  if (resume && fs.existsSync(statePath)) {
    try {
      const st = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      if (st.scene === sceneId && st.fps === fps) doneThrough = st.doneThrough;
    } catch (e) { log('unreadable state file, starting over: ' + e.message); }
  }
  const saveState = (n) => fs.writeFileSync(statePath, JSON.stringify({ scene: sceneId, fps, doneThrough: n }));

  const frameName = (n) => path.join(outDir, 'frame_' + String(n).padStart(6, '0') + '.png');
  let start = doneThrough + 1;
  if (start >= totalFrames) {
    log('all ' + totalFrames + ' frames already rendered, skipping to encode');
  }

  // Render in browser chunks.
  for (let c0 = start; c0 < totalFrames; c0 += chunkFrames) {
    const c1 = Math.min(c0 + chunkFrames, totalFrames);
    let browser = null;
    try {
      browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
      const page = await browser.newPage({ viewport: { width, height } });
      await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      const ok = await page.evaluate(() => typeof window.__setTime === 'function');
      if (!ok) throw new Error('scene does not expose window.__setTime(t): ' + scene.file);
      const dur = await page.evaluate(() => window.__sceneDuration);
      if (typeof dur === 'number' && Math.abs(dur - scene.duration_seconds) > 0.05) {
        throw new Error('__sceneDuration ' + dur + ' != manifest ' + scene.duration_seconds);
      }
      for (let n = c0; n < c1; n++) {
        const t = n / fps;
        await page.evaluate((tt) => window.__setTime(tt), t);
        await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
        await page.locator('#stage').screenshot({ path: frameName(n) });
        if (n % 50 === 0) log(sceneId + ' frame ' + n + '/' + totalFrames);
      }
      saveState(c1 - 1);
      log(sceneId + ' chunk done through frame ' + (c1 - 1));
    } finally {
      if (browser) await browser.close(); // headless only; always closed
    }
  }

  // Verify every frame exists and is non-empty before encoding.
  for (let n = 0; n < totalFrames; n++) {
    const p = frameName(n);
    if (!fs.existsSync(p) || fs.statSync(p).size === 0) {
      log('MISSING or empty frame: ' + p + ' -- rerun with --resume');
      process.exit(3);
    }
  }

  // Encode the scene segment.
  const segPath = path.join(outDir, sceneId + '.mp4');
  const ff = spawnSync('ffmpeg', ['-y', '-framerate', String(fps), '-i',
    path.join(outDir, 'frame_%06d.png'),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', segPath],
    { stdio: 'inherit' });
  if (ff.status !== 0) {
    log('ENCODE FAILED for ' + sceneId + '. PNGs kept for --resume.');
    log('To abandon and clean: rm -rf ' + outDir);
    process.exit(4);
  }

  // Cleanup: delete PNGs now that the segment exists. Finally-grade.
  try {
    for (let n = 0; n < totalFrames; n++) fs.unlinkSync(frameName(n));
    if (fs.existsSync(statePath)) fs.unlinkSync(statePath);
    log(sceneId + ' segment encoded and ' + totalFrames + ' PNGs deleted');
  } catch (e) {
    log('cleanup warning: ' + e.message);
  }
  process.stdout.write(JSON.stringify({ scene: sceneId, segment: segPath, frames: totalFrames }) + '\n');
}

main().catch(e => { log('FATAL: ' + (e && e.stack || e)); process.exit(1); });

// ---- review modes ----

// --mux <newaudio> --video <in.mp4> --out <out.mp4>
// Re-mux new audio into an existing render without re-rendering video.
// The mix changed but the picture did not: minutes, not hours.
async function muxMode() {
  const audio = arg('mux');
  const video = arg('video');
  const out = arg('out');
  if (!audio || !video || !out) {
    log('usage: render.js --mux <newaudio> --video <in.mp4> --out <out.mp4>');
    process.exit(2);
  }
  for (const [p, n] of [[video, 'video'], [audio, 'audio']]) {
    if (!fs.existsSync(p)) { log('missing ' + n + ' file: ' + p); process.exit(2); }
  }
  const r = spawnSync('ffmpeg', ['-y', '-i', video, '-i', audio,
    '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0',
    '-c:a', 'aac', '-b:a', '192k', '-shortest', out], { stdio: 'inherit' });
  if (r.status !== 0) { log('mux failed'); process.exit(4); }
  log('muxed: ' + out);
}

// --beatsheet --beats <beats.json> --video <in.mp4> --out <sheet.jpg>
// One frame per beat (a quarter beat after the hit), tiled into a sheet.
async function beatsheetMode() {
  const beatsPath = arg('beats');
  const video = arg('video');
  const out = arg('out');
  if (!beatsPath || !video || !out) {
    log('usage: render.js --beatsheet --beats <beats.json> --video <in.mp4> --out <sheet.jpg>');
    process.exit(2);
  }
  const beats = JSON.parse(fs.readFileSync(beatsPath, 'utf8'));
  const step = beats.beat_seconds || 0.5;
  const os = require('os');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mvplus-beat-'));
  try {
    const shots = [];
    beats.beat_times.slice(0, 64).forEach((t, i) => {
      const p = path.join(tmp, 'beat_' + String(i).padStart(4, '0') + '.jpg');
      execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
        '-ss', String(t + step * 0.25), '-i', video, '-frames:v', '1', '-q:v', '4', p]);
      shots.push(p);
    });
    const cols = 8;
    const rows = Math.ceil(shots.length / cols);
    const args = ['-hide_banner', '-loglevel', 'error', '-y'];
    shots.forEach(s => args.push('-i', s));
    args.push('-filter_complex', 'tile=' + cols + 'x' + rows, '-q:v', '4', out);
    execFileSync('ffmpeg', args);
    log('beat sheet: ' + out + ' (' + shots.length + ' beats)');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

async function openScenePage(manifestPath, scene, width, height) {
  const htmlPath = path.resolve(path.dirname(manifestPath), scene.file);
  if (!fs.existsSync(htmlPath)) { log('missing scene file: ' + htmlPath); process.exit(2); }
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage({ viewport: { width, height } });
  await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  if (!(await page.evaluate(() => typeof window.__setTime === 'function'))) {
    await browser.close();
    throw new Error('scene does not expose window.__setTime(t): ' + scene.file);
  }
  return { browser, page };
}

function loadScene(manifestPath, sceneId) {
  if (!manifestPath || !sceneId) {
    log('modes --still/--cliprange need --manifest, --scene, --outdir');
    process.exit(2);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const scene = manifest.scenes.find(s => s.id === sceneId);
  if (!scene) { log('scene not found: ' + sceneId); process.exit(2); }
  return { manifest, scene };
}

// --still <t> : save one timestamped still frame for close inspection.
async function stillMode(manifestPath, sceneId, outDir) {
  const t = parseFloat(arg('still'));
  if (!outDir || isNaN(t)) {
    log('usage: render.js --manifest M --scene ID --outdir D --still <seconds>');
    process.exit(2);
  }
  const { manifest, scene } = loadScene(manifestPath, sceneId);
  fs.mkdirSync(outDir, { recursive: true });
  const opened = await openScenePage(manifestPath, scene, manifest.width, manifest.height);
  try {
    await opened.page.evaluate((tt) => window.__setTime(tt), t);
    await opened.page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
    const out = path.join(outDir, 'still_' + String(t).replace('.', 'p') + 's.png');
    await opened.page.locator('#stage').screenshot({ path: out });
    log('still: ' + out);
  } finally {
    await opened.browser.close();
  }
}

// --cliprange <a,b> : render a short MP4 clip for motion checks.
async function cliprangeMode(manifestPath, sceneId, outDir) {
  const range = arg('cliprange');
  if (!outDir || !range || range.indexOf(',') === -1) {
    log('usage: render.js --manifest M --scene ID --outdir D --cliprange <start,end>');
    process.exit(2);
  }
  const { manifest, scene } = loadScene(manifestPath, sceneId);
  const [a, b] = range.split(',').map(parseFloat);
  const fps = manifest.fps;
  const n0 = Math.max(0, Math.round(a * fps));
  const n1 = Math.min(Math.round(scene.duration_seconds * fps) - 1, Math.round(b * fps));
  fs.mkdirSync(outDir, { recursive: true });
  const opened = await openScenePage(manifestPath, scene, manifest.width, manifest.height);
  try {
    for (let n = n0; n <= n1; n++) {
      const t = n / fps;
      await opened.page.evaluate((tt) => window.__setTime(tt), t);
      await opened.page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
      await opened.page.locator('#stage')
        .screenshot({ path: path.join(outDir, 'clip_' + String(n).padStart(6, '0') + '.png') });
    }
  } finally {
    await opened.browser.close();
  }
  const out = path.join(outDir, 'clip_' + a + '_' + b + '.mp4');
  const r = spawnSync('ffmpeg', ['-y', '-framerate', String(fps), '-i',
    path.join(outDir, 'clip_%06d.png'),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', out], { stdio: 'inherit' });
  if (r.status !== 0) { log('clip encode failed'); process.exit(4); }
  for (let n = n0; n <= n1; n++) {
    fs.unlinkSync(path.join(outDir, 'clip_' + String(n).padStart(6, '0') + '.png'));
  }
  log('clip: ' + out);
}

main().catch(e => { log('FATAL: ' + (e && e.stack || e)); process.exit(1); });
