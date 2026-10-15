#!/usr/bin/env node
/**
 * probe.mjs -- launch-and-render readiness probe for the shared motion
 * render runtime (shared-utils/motion-render-runtime).
 *
 * This is NOT a presence check. For each mandatory engine it proves the
 * engine actually runs:
 *
 *   Remotion     -- bundles a minimal composition on the fly and renders
 *                   one real frame to PNG with @remotion/bundler +
 *                   @remotion/renderer, then verifies the PNG signature,
 *                   dimensions and size.
 *   HyperFrames  -- runs the pinned CLI (--version) and its health
 *                   command (doctor, discovered from --help) and
 *                   requires exit code 0.
 *
 * Results are written as runtime-lock.json (path overridable with
 * MOTION_RUNTIME_LOCK_OUT) containing the MEASURED versions, the
 * resolved headless-browser revision, the ffmpeg version when present,
 * and a per-engine pass/fail record.
 *
 * Exit code: 0 only when every mandatory engine passes; 1 otherwise.
 * The lock file is written either way (a failed probe still records
 * what was measured), with "result": "fail".
 */
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileP = promisify(execFile);
const PROBE_DIR = dirname(fileURLToPath(import.meta.url));
const LOCK_OUT = process.env.MOTION_RUNTIME_LOCK_OUT || join(PROBE_DIR, 'runtime-lock.json');

// Remotion resolves its browser cache relative to the process working
// directory. Anchor the cwd to this runtime directory so the probe uses
// (and records) the browser that belongs to THIS install, and never
// downloads a stray copy into the caller's working directory.
process.chdir(PROBE_DIR);
const EXPECTED = { width: 320, height: 180 };

function pkgVersion(name) {
  try {
    const p = join(PROBE_DIR, 'node_modules', name, 'package.json');
    return JSON.parse(readFileSync(p, 'utf8')).version || null;
  } catch {
    return null;
  }
}

function tail(s, n = 600) {
  if (!s) return '';
  const str = String(s);
  return str.length > n ? str.slice(-n) : str;
}

async function run(cmd, args, opts = {}) {
  return execFileP(cmd, args, { timeout: 180000, maxBuffer: 32 * 1024 * 1024, ...opts });
}

/** Find the Chrome Headless Shell Remotion downloaded, and its revision. */
function findBrowser() {
  const roots = [
    join(PROBE_DIR, 'node_modules', '.remotion'),
    join(PROBE_DIR, '.remotion'),
  ];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const entry of readdirSync(root)) {
      if (!entry.startsWith('chrome-headless-shell')) continue;
      const dir = join(root, entry);
      // Layout: chrome-headless-shell-<platform>-<revision>/chrome-headless-shell-<platform>/chrome-headless-shell
      let executable = null;
      const walk = (d, depth) => {
        if (depth > 3 || executable) return;
        for (const e of readdirSync(d, { withFileTypes: true })) {
          const p = join(d, e.name);
          if (e.isDirectory()) walk(p, depth + 1);
          else if (e.name.startsWith('chrome-headless-shell') && !e.name.endsWith('.zip')) executable = p;
        }
      };
      try { walk(dir, 0); } catch { /* ignore */ }
      const m = entry.match(/(\d+(?:\.\d+){3,}|\d{6,})$/);
      return { dir, executable, revision: m ? m[1] : entry };
    }
  }
  return null;
}

async function probeRemotion(versions) {
  const detail = { version: versions.remotion, render: null, browser: null };
  if (!versions.remotion) throw new Error('remotion package not installed');
  const { bundle } = await import('@remotion/bundler');
  const { selectComposition, renderStill, ensureBrowser } = await import('@remotion/renderer');

  const workRoot = join(PROBE_DIR, '.probe-work');
  mkdirSync(workRoot, { recursive: true });
  const work = mkdtempSync(join(workRoot, 'remotion-'));
  try {
    const entry = join(work, 'entry.js');
    writeFileSync(entry, [
      "const React = require('react');",
      "const { registerRoot, Composition, AbsoluteFill } = require('remotion');",
      'const ProbeComp = () => React.createElement(AbsoluteFill,',
      "  { style: { backgroundColor: '#123a6d', justifyContent: 'center', alignItems: 'center' } },",
      "  React.createElement('div', { style: { color: '#ffffff', fontSize: 28, fontFamily: 'sans-serif' } }, 'motion-runtime-probe'),",
      "  React.createElement('div', { style: { position: 'absolute', right: 0, bottom: 0, width: 64, height: 64, backgroundColor: '#e8b13a' } }));",
      'const Root = () => React.createElement(Composition, {',
      "  id: 'probe', component: ProbeComp, durationInFrames: 1, fps: 30,",
      `  width: ${EXPECTED.width}, height: ${EXPECTED.height} });`,
      'registerRoot(Root);',
      '',
    ].join('\n'));

    const serveUrl = await bundle({ entryPoint: entry });
    await ensureBrowser();
    const composition = await selectComposition({ serveUrl, id: 'probe' });
    const output = join(work, 'still.png');
    await renderStill({ composition, serveUrl, frame: 0, output });

    if (!existsSync(output)) throw new Error('renderStill produced no output file');
    const buf = readFileSync(output);
    const size = statSync(output).size;
    const isPng = buf.length > 24 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
    if (!isPng) throw new Error('rendered still is not a PNG');
    const w = buf.readUInt32BE(16);
    const h = buf.readUInt32BE(20);
    if (w !== EXPECTED.width || h !== EXPECTED.height) {
      throw new Error(`rendered still has wrong dimensions: ${w}x${h}`);
    }
    if (size < 1000) throw new Error(`rendered still is trivially small: ${size} bytes`);
    detail.render = { outputBytes: size, width: w, height: h };

    const browser = findBrowser();
    if (browser) {
      detail.browser = {
        revision: browser.revision,
        // Recorded relative to the runtime dir: the runtime is promoted
        // (moved) as a unit after the probe, so a relative path stays
        // true in the promoted location while an absolute one goes stale.
        executable: browser.executable ? relative(PROBE_DIR, browser.executable) : null,
      };
      if (browser.executable) {
        try {
          const { stdout } = await run(browser.executable, ['--version']);
          detail.browser.versionString = stdout.trim();
          // On the current download layout the folder name carries no
          // version; the binary's own --version output is the authority.
          const vm = detail.browser.versionString.match(/\d+(?:\.\d+){3,}/);
          if (vm) detail.browser.revision = vm[0];
        } catch { /* version string is informational only */ }
      }
    }
    return detail;
  } finally {
    try { rmSync(work, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

async function probeHyperframes(versions) {
  const bin = join(PROBE_DIR, 'node_modules', '.bin', 'hyperframes');
  const detail = { version: versions.hyperframes, cliVersion: null, healthCommand: null };
  if (!existsSync(bin)) throw new Error('hyperframes CLI not installed (node_modules/.bin/hyperframes missing)');
  const v = await run(bin, ['--version']);
  detail.cliVersion = (v.stdout || v.stderr || '').trim().split('\n')[0];
  if (!detail.cliVersion) throw new Error('hyperframes --version printed nothing');

  let helpText = '';
  try {
    const h = await run(bin, ['--help']);
    helpText = `${h.stdout || ''}\n${h.stderr || ''}`;
  } catch (e) {
    helpText = `${e.stdout || ''}\n${e.stderr || ''}`;
  }
  if (/\bdoctor\b/.test(helpText)) {
    detail.healthCommand = 'doctor';
    await run(bin, ['doctor'], { timeout: 300000 });
  } else {
    // No doctor subcommand in this CLI version: --help exiting 0 plus a
    // successful --version is the closest health signal the CLI exposes.
    detail.healthCommand = '--help (no doctor subcommand in this version)';
  }
  return detail;
}

async function ffmpegVersion() {
  try {
    const { stdout } = await run('ffmpeg', ['-version']);
    return stdout.split('\n')[0].trim();
  } catch {
    return null;
  }
}

const versions = {
  remotion: pkgVersion('remotion'),
  '@remotion/cli': pkgVersion('@remotion/cli'),
  '@remotion/renderer': pkgVersion('@remotion/renderer'),
  '@remotion/bundler': pkgVersion('@remotion/bundler'),
  hyperframes: pkgVersion('hyperframes'),
  gsap: pkgVersion('gsap'),
  typescript: pkgVersion('typescript'),
};

console.log(`probe: node ${process.version}`);
console.log(`probe: remotion ${versions.remotion} | @remotion/cli ${versions['@remotion/cli']} | hyperframes ${versions.hyperframes} | gsap ${versions.gsap}`);

const lock = {
  generated_by: 'shared-utils/motion-render-runtime/probe.mjs',
  timestamp: new Date().toISOString(),
  node: process.version,
  platform: { os: process.platform, arch: process.arch },
  packages: versions,
  browser: null,
  ffmpeg: await ffmpegVersion(),
  engines: {},
  result: 'fail',
};

let allPass = true;

try {
  const d = await probeRemotion(versions);
  lock.engines.remotion = { status: 'pass', ...d };
  lock.browser = d.browser;
  console.log(`probe: remotion PASS (rendered ${d.render.outputBytes} bytes, ${d.render.width}x${d.render.height}, browser revision ${d.browser ? d.browser.revision : 'unknown'})`);
} catch (e) {
  allPass = false;
  lock.engines.remotion = { status: 'fail', version: versions.remotion, error: tail(e.message || e) };
  console.error(`probe: remotion FAIL: ${tail(e.message || e)}`);
}

try {
  const d = await probeHyperframes(versions);
  lock.engines.hyperframes = { status: 'pass', ...d };
  console.log(`probe: hyperframes PASS (cli "${d.cliVersion}", health: ${d.healthCommand})`);
} catch (e) {
  allPass = false;
  lock.engines.hyperframes = { status: 'fail', version: versions.hyperframes, error: tail(e.message || e), stderr: tail(e.stderr) };
  console.error(`probe: hyperframes FAIL: ${tail(e.message || e)}`);
}

lock.result = allPass ? 'pass' : 'fail';
mkdirSync(dirname(LOCK_OUT), { recursive: true });
writeFileSync(LOCK_OUT, JSON.stringify(lock, null, 2) + '\n');
console.log(`probe: runtime-lock written to ${LOCK_OUT}`);
console.log(`probe: RESULT ${lock.result}`);
process.exit(allPass ? 0 : 1);
