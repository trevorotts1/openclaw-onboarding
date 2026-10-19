#!/usr/bin/env node
// Measures the smallest observed bytes / usage.input_tokens ratio for one
// route and prints the resulting entry as JSON on stdout. Optional
// engineering tool: the council convenes without it, using built-in defaults.
//
//   node scripts/measure-route-bytes-per-token.mjs --route ID [--model M]
//        [--samples N] [--measurements FILE] [--save-measurements FILE]
//        [--context-window TOKENS] [--max-output TOKENS] [--write]
//
// Live mode (no --measurements) sends fixed sample payloads through the
// route and spends the client's model allowance, so run it only with the
// operator's go. Offline mode recomputes the identical entry from recorded
// (bytes, input_tokens) pairs and makes no provider call.
//
// --write updates the route-budgets config only (WISE_ELDERS_ROUTE_BUDGETS
// or config/route-budgets.json). It prints no credential: errors are
// scrubbed of any secret-looking environment value first.

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const skillRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const runtimeDir = join(skillRoot, 'runtime');

// Built dist when present, else the TypeScript source through the
// runtime's own tsx, so the script works before and after `npm run build`.
async function loadRuntime(rel) {
  const dist = join(runtimeDir, 'dist', `${rel}.js`);
  if (existsSync(dist)) return import(pathToFileURL(dist).href);
  const src = join(runtimeDir, 'src', `${rel}.ts`);
  if (!existsSync(src)) throw new Error(`runtime module ${rel} is not available`);
  const require = createRequire(join(runtimeDir, 'package.json'));
  const { tsImport } = await import(pathToFileURL(require.resolve('tsx/esm/api')).href);
  return tsImport(pathToFileURL(src).href, import.meta.url);
}

function scrub(text) {
  let out = String(text);
  for (const [k, v] of Object.entries(process.env)) {
    if (v && v.length >= 8 && /KEY|TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL/i.test(k)) {
      out = out.split(v).join('[redacted]');
    }
  }
  return out.slice(0, 500);
}

function die(code, message) {
  console.error(scrub(message));
  process.exit(code);
}

function parseArgs(argv) {
  const opts = {};
  const valued = new Set([
    '--route', '--model', '--samples', '--measurements', '--save-measurements',
    '--context-window', '--max-output',
  ]);
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--write') opts.write = true;
    else if (valued.has(a)) {
      if (i + 1 >= argv.length) die(2, `${a} needs a value`);
      opts[a.slice(2)] = argv[(i += 1)];
    } else die(2, `unknown argument ${a}`);
  }
  return opts;
}

function posInt(value, name) {
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n <= 0) die(2, `${name} must be a positive integer`);
  return n;
}

// Deterministic fixed samples. Dense text (hex, base64, CJK, symbols) is
// included on purpose: the SMALLEST ratio is what protects the window.
const SAMPLE_BYTES = 12_000;
function fill(unit) {
  let out = '';
  while (Buffer.byteLength(out) < SAMPLE_BYTES) out += unit;
  return out;
}
function hashChain(encoding) {
  let h = createHash('sha256').update('wise-elders route bytes sample').digest();
  let out = '';
  while (out.length < SAMPLE_BYTES) {
    h = createHash('sha256').update(h).digest();
    out += h.toString(encoding);
  }
  return out;
}
function buildSamples() {
  const prose =
    'A decision is easier to make well when the facts, the constraints and the people affected are written down plainly before anyone argues for an answer. ';
  const code =
    'export function clamp(value: number, low: number, high: number): number {\n  if (!Number.isFinite(value)) throw new RangeError("value");\n  return Math.min(high, Math.max(low, value));\n}\n';
  const json = JSON.stringify({ id: 'a1b2c3', tags: ['x', 'y'], n: 12345, ok: true, nested: { k: [1, 2, 3], s: 'text' } }) + '\n';
  const cjk = '先把事实和限制条件写清楚，再讨论每个选项的利弊与风险，最后形成一个可以执行的建议。';
  const mixed = '🙂 café naïve \u2014 Привет мир \u2014 مرحبا \u2014 नमस्ते \u2014 ¿qué tal? ✓ → ≈ ∑ ';
  return [
    ['prose', fill(prose)],
    ['code', fill(code)],
    ['json', fill(json)],
    ['hex', hashChain('hex')],
    ['base64', hashChain('base64')],
    ['cjk', fill(cjk)],
    ['mixed_unicode', fill(mixed)],
    ['digits_symbols', fill('3.14159 2.71828 -0.00042 [12,45,78] {9:0} #f0f0f0 @@ ~~ ')],
  ];
}

const PROBE_SYSTEM =
  'Measurement probe. Do not analyse the input. Reply with the single word OK.';

// Real tokenizers stay inside this band on diverse text. A ratio outside
// it means usage.input_tokens did not count the whole prompt (for example
// cached tokens reported separately) and must not be proposed.
const PLAUSIBLE_MIN = 0.5;
const PLAUSIBLE_MAX = 6;

async function measureLive(opts, rb) {
  let rc;
  try {
    rc = await loadRuntime('service/route-choice');
  } catch (err) {
    die(2, `live mode needs runtime/src/service/route-choice.ts: ${err.message}`);
  }
  const harnessFor = {
    'claude-nine-configured': 'claude-nine',
    'claude-configured': 'claude-code',
    'deepseek-configured': 'deepseek',
  };
  const scope = {
    tenantId: 'route-budget-measure',
    companyId: 'route-budget-measure',
    installationId: 'route-budget-measure',
    ownerSubject: null,
  };
  const resolved = await rc.resolveSessionRoute(
    {
      route_id: opts.route,
      model: opts.model ?? null,
      harness: opts.model ? null : (harnessFor[opts.route] ?? null),
    },
    { env: process.env, scope, nowUtc: () => new Date().toISOString() },
  );
  const transport = rc.transportForSnapshot(resolved.snapshot, { env: process.env });
  if (!transport) die(2, `route ${opts.route} has no usable transport on this machine`);
  console.error(`measuring route ${opts.route} model ${resolved.model_label}`);

  let samples = buildSamples();
  if (opts.samples) samples = samples.slice(0, posInt(opts.samples, '--samples'));
  const pairs = [];
  for (const [name, text] of samples) {
    const input = { sample: name, text };
    const bytes = rb.requestBytes(PROBE_SYSTEM, input);
    let tokens = null;
    try {
      const res = await transport.generate({
        purpose: 'consult',
        session_id: 'route-budget-measure',
        seat_id: 'simon-sinek',
        round: null,
        route_id: opts.route,
        model_policy: resolved.model_policy,
        system: PROBE_SYSTEM,
        input,
      });
      tokens = res.usage?.input_tokens ?? null;
    } catch (err) {
      console.error(`sample ${name} failed: ${scrub(err?.message ?? err)}`);
    }
    pairs.push({ bytes, input_tokens: tokens });
  }
  return {
    pairs,
    measured_at: new Date().toISOString(),
    pinned_model: resolved.snapshot.requestedModelOrAlias ?? null,
    capability: resolved.snapshot.capabilitySnapshot ?? {},
  };
}

function readMeasurements(file) {
  let rec;
  try {
    rec = JSON.parse(readFileSync(file, 'utf8'));
  } catch (err) {
    die(2, `could not read measurements file: ${err.message}`);
  }
  if (!rec || !Array.isArray(rec.pairs)) die(2, 'measurements file needs a "pairs" array');
  for (const p of rec.pairs) {
    if (!p || typeof p.bytes !== 'number') die(2, 'each pair needs numeric "bytes"');
  }
  return rec;
}

const opts = parseArgs(process.argv.slice(2));
const rb = await loadRuntime('budgets/route-budget');
const configPath = rb.routeBudgetConfigPath(skillRoot, process.env);

let rec = opts.measurements ? readMeasurements(opts.measurements) : null;
const routeId = opts.route ?? rec?.route_id;
if (!routeId) die(2, '--route ID is required');
if (rec?.route_id && rec.route_id !== routeId) die(2, 'measurements file is for a different route');
let model;
let capability = {};
let configEntries = [];
try {
  configEntries = rb.loadRouteBudgetConfig(configPath).entries;
} catch (err) {
  if (opts.write) die(2, `cannot update config: ${err.message}`);
}
if (rec) {
  // Offline: the recording names the model it was taken on.
  const recModel = rec.model ?? null;
  if (opts.model && 'model' in rec && opts.model !== recModel) {
    die(2, `--model ${opts.model} conflicts with the recording's model ${recModel}`);
  }
  model = opts.model ?? recModel;
} else {
  rec = await measureLive(opts, rb);
  capability = rec.capability;
  const pinned = rec.pinned_model ?? null;
  if (opts.model && opts.model !== pinned) {
    die(2, `--model ${opts.model} conflicts with the resolved route model ${pinned}`);
  }
  // Fill the entry the runtime resolver will read: exact model first, then
  // the route's model:null entry (for example deepseek, whose model id is
  // resolved from the provider list at each run).
  const has = (m) => configEntries.some((e) => e.route_id === routeId && e.model === m);
  model = has(pinned) ? pinned : has(null) ? null : pinned;
}
opts.route = routeId;
if (model !== null) opts.model = model;
const base = configEntries.find((e) => e.route_id === routeId && e.model === model) ?? null;

const entry = rb.proposeRouteBudgetEntry({
  base,
  route_id: routeId,
  model,
  pairs: rec.pairs,
  measured_at: rec.measured_at ?? null,
});
// Window and output limits: flag, then the recording, then the route's own
// capability snapshot. Never guessed; stays null when none supplies it.
const ctx = opts['context-window']
  ? posInt(opts['context-window'], '--context-window')
  : (rec.context_window_tokens ?? capability.contextWindowTokens ?? null);
const out = opts['max-output']
  ? posInt(opts['max-output'], '--max-output')
  : (rec.max_output_tokens ?? capability.maxOutputTokens ?? null);
if (ctx !== null) entry.context_window_tokens = ctx;
if (out !== null) entry.max_output_tokens = out;

if (opts['save-measurements']) {
  writeFileSync(
    opts['save-measurements'],
    `${JSON.stringify(
      {
        route_id: routeId,
        model,
        measured_at: entry.measured_at,
        sample_set: rb.SAMPLE_SET_ID,
        usage_field: rb.USAGE_FIELD,
        context_window_tokens: entry.context_window_tokens,
        max_output_tokens: entry.max_output_tokens,
        pairs: rec.pairs,
      },
      null,
      2,
    )}\n`,
  );
}

const ratio = entry.measured_min_bytes_per_token;
if (ratio === null) die(3, 'no sample returned a usable usage.input_tokens; nothing to propose');
if (ratio < PLAUSIBLE_MIN || ratio > PLAUSIBLE_MAX) {
  die(
    3,
    `implausible ratio ${ratio} bytes/token (expected ${PLAUSIBLE_MIN} to ${PLAUSIBLE_MAX}); ` +
      'the provider usage field probably does not count the whole prompt. Nothing proposed.',
  );
}

console.log(JSON.stringify(entry, null, 2));

if (opts.write) {
  const config = rb.loadRouteBudgetConfig(configPath);
  const i = config.entries.findIndex((e) => e.route_id === routeId && e.model === model);
  if (i >= 0) config.entries[i] = entry;
  else config.entries.push(entry);
  const tmp = `${configPath}.tmp-${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(config, null, 2)}\n`);
  renameSync(tmp, configPath);
  console.error(`updated proposed entry in ${configPath === join(skillRoot, 'config', 'route-budgets.json') ? 'config/route-budgets.json' : 'the configured route budgets file'}`);
}
