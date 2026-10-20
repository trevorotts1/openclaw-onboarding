/**
 * `blackceo-council routes` and `blackceo-council convene` (W28).
 *
 * A thin client over the council service HTTP API. Convening is the
 * approval: there is no grant or approval step on this path. The CLI
 * only detects which harness it runs in, forwards the client's model
 * choice verbatim, and reports what the service accepted or refused.
 * It never picks a model itself: the service resolves the route.
 */

import { readFileSync } from 'node:fs';
import type { CliIo } from './dispatcher.js';
import { CouncilError, invalidInput, usageError, type CouncilErrorCode } from './errors.js';

export type Harness = 'claude-nine' | 'claude-code' | 'deepseek' | 'unknown';

const CHOOSABLE_HARNESSES = ['claude-nine', 'claude-code', 'deepseek'] as const;
export const DEFAULT_SERVICE_ORIGIN = 'http://127.0.0.1:8787';
const REQUEST_TIMEOUT_MS = 60_000;

/**
 * claude-nine exports CLAUDE_CONFIG_DIR (default ~/.claude-nine) before
 * it launches Claude Code, and Claude Code itself sets CLAUDECODE=1.
 * So the config dir decides claude-nine first. A DeepSeek-direct
 * harness leaves no reliable marker, so it is only ever chosen with
 * --harness (or by the client); anything else is 'unknown'.
 */
export function detectHarness(env: NodeJS.ProcessEnv): Harness {
  const configDir = env.CLAUDE_CONFIG_DIR;
  if (configDir) {
    const parts = configDir.split(/[\\/]+/).filter((p) => p.length > 0);
    if (parts[parts.length - 1] === '.claude-nine') return 'claude-nine';
  }
  if (env.CLAUDECODE === '1') return 'claude-code';
  return 'unknown';
}

export interface ConveneOpts {
  fetchImpl?: typeof fetch;
  env?: NodeJS.ProcessEnv;
  io: CliIo;
}

interface Parsed {
  flags: Map<string, string | true>;
}

const BOOLEAN_FLAGS = new Set(['sample', 'json']);
const ROUTES_FLAGS = new Set(['origin', 'json', 'data-dir']);
const CONVENE_FLAGS = new Set([
  'sample',
  'brief',
  'route',
  'model',
  'harness',
  'fresh-facts',
  'mode',
  'origin',
  'public-origin',
  'json',
  'data-dir',
]);

function parse(args: string[], allowed: Set<string>, command: string): Parsed {
  const flags = new Map<string, string | true>();
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (!arg.startsWith('--')) throw usageError(`${command} takes flags only; unexpected argument "${arg}".`);
    const name = arg.slice(2);
    if (!allowed.has(name)) throw usageError(`${command} does not accept --${name}.`);
    if (BOOLEAN_FLAGS.has(name)) {
      flags.set(name, true);
      continue;
    }
    const value = args[i + 1];
    if (value === undefined || value.startsWith('--')) throw usageError(`--${name} needs a value.`);
    flags.set(name, value);
    i += 1;
  }
  return { flags };
}

function str(p: Parsed, name: string): string | null {
  const v = p.flags.get(name);
  return typeof v === 'string' ? v : null;
}

function resolveOrigin(p: Parsed, env: NodeJS.ProcessEnv): string {
  const raw = str(p, 'origin') ?? env.WISE_ELDERS_SERVICE_ORIGIN ?? DEFAULT_SERVICE_ORIGIN;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw invalidInput(`The service origin "${raw}" is not a valid URL.`);
  }
  return url.origin;
}

// The address the client opens in a browser (the per-box Cloudflare Access
// hostname). Links only: API calls keep using resolveOrigin (loopback).
// Null when unset; otherwise an https origin with no path, query or login.
function resolvePublicOrigin(p: Parsed, env: NodeJS.ProcessEnv): string | null {
  const raw = str(p, 'public-origin') ?? env.WISE_ELDERS_PUBLIC_ORIGIN;
  if (raw === undefined || raw === '') return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw invalidInput(`The public origin "${raw}" is not a valid URL.`);
  }
  if (url.protocol !== 'https:' || url.pathname !== '/' || url.search || url.hash || url.username || url.password) {
    throw invalidInput(`The public origin "${raw}" must be an https origin with no path, query or login, like https://name.example.com.`);
  }
  return url.origin;
}

// The service speaks its own refusal codes (COMPOSITION_NOT_READY, ...), which
// are outside the CLI's closed code union. Exit code 3 matches the other
// not-ready refusals.
function serviceError(code: string, message: string, recovery: string): CouncilError {
  return new CouncilError(code as CouncilErrorCode, message, {
    action: recovery,
    exitCode: 3,
    retryable: false,
  });
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value);
}

// A refusal's plain-English summary when it has one, else the raw detail.
function detailText(detail: unknown): string | null {
  if (detail === undefined) return null;
  const summary = (detail as { summary?: unknown } | null)?.summary;
  return typeof summary === 'string' ? summary : asText(detail);
}

async function callService(
  origin: string,
  path: string,
  init: { method: 'GET' } | { method: 'POST'; body: unknown },
  fetchImpl: typeof fetch,
): Promise<Record<string, unknown>> {
  const url = `${origin}${path}`;
  let res: Response;
  try {
    res = await fetchImpl(url, {
      method: init.method,
      headers:
        init.method === 'POST'
          ? { 'content-type': 'application/json', accept: 'application/json' }
          : { accept: 'application/json' },
      body: init.method === 'POST' ? JSON.stringify(init.body) : undefined,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    const cause = (err as { cause?: { code?: string } } | null)?.cause?.code;
    throw serviceError(
      'SERVICE_UNREACHABLE',
      `The council service did not answer at ${origin}${cause ? ` (${cause})` : ''}.`,
      'Start the council service, or pass --origin (or set WISE_ELDERS_SERVICE_ORIGIN) to the origin it listens on.',
    );
  }
  const text = await res.text();
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw serviceError(
      'SERVICE_BAD_RESPONSE',
      `The council service at ${origin} answered HTTP ${res.status} with a body that is not JSON.`,
      'Check that the origin is the council service and not another program.',
    );
  }
  const obj = body !== null && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  if (!res.ok) {
    throw serviceError(
      typeof obj.code === 'string' ? obj.code : `SERVICE_HTTP_${res.status}`,
      detailText(obj.detail) ?? `The council service refused with HTTP ${res.status}.`,
      typeof obj.recovery === 'string' ? obj.recovery : 'Read the code above and retry once it is resolved.',
    );
  }
  return obj;
}

function report(io: CliIo, json: boolean, err: unknown): number {
  const council =
    err instanceof CouncilError
      ? err
      : new CouncilError('COUNCIL_INTERNAL', err instanceof Error ? err.message : String(err));
  if (json) io.err(`${JSON.stringify(council.toEnvelope(), null, 2)}\n`);
  else io.err(`Error [${council.code}]: ${council.message}\nNext action: ${council.action}\n`);
  return council.exitCode;
}

export async function runRoutes(args: string[], opts: ConveneOpts): Promise<number> {
  const json = args.includes('--json');
  try {
    const p = parse(args, ROUTES_FLAGS, 'routes');
    const origin = resolveOrigin(p, opts.env ?? process.env);
    const body = await callService(origin, '/api/council/routes', { method: 'GET' }, opts.fetchImpl ?? fetch);
    if (json) {
      opts.io.out(`${JSON.stringify(body, null, 2)}\n`);
      return 0;
    }
    const lines: string[] = ['Model routes this council can run on:'];
    const routes = Array.isArray(body.routes) ? (body.routes as Array<Record<string, unknown>>) : [];
    for (const r of routes) {
      const defaults = Array.isArray(r.default_for) && r.default_for.length > 0 ? `, default for ${r.default_for.join(', ')}` : '';
      const state = r.composable ? 'ready' : `not ready (${r.failure_code ?? 'unknown reason'})`;
      lines.push(`  ${r.route_id} (${r.provider_slug}, ${r.kind}): ${state}${defaults}`);
    }
    if (routes.length === 0) lines.push('  none found');
    const hd = body.harness_defaults;
    if (hd !== null && typeof hd === 'object') {
      lines.push('Default model by harness:');
      for (const [harness, d] of Object.entries(hd as Record<string, { route_id?: string; model?: string }>)) {
        lines.push(`  ${harness}: ${d.route_id} / ${d.model}`);
      }
    }
    opts.io.out(`${lines.join('\n')}\n`);
    return 0;
  } catch (err) {
    return report(opts.io, json, err);
  }
}

function readFreshFacts(path: string): unknown[] {
  let facts: unknown;
  try {
    facts = JSON.parse(readFileSync(path, 'utf8'));
  } catch (err) {
    throw invalidInput(`Could not read --fresh-facts file: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!Array.isArray(facts)) throw invalidInput('--fresh-facts must be a JSON array of {claim, url, title, retrieved_at}.');
  facts.forEach((f, i) => {
    const o = f as Record<string, unknown> | null;
    if (!o || typeof o.claim !== 'string' || !o.claim || typeof o.url !== 'string' || !o.url || typeof o.retrieved_at !== 'string') {
      throw invalidInput(`--fresh-facts entry ${i} needs a claim, a url and a retrieved_at.`);
    }
  });
  return facts;
}

export async function runConvene(args: string[], opts: ConveneOpts): Promise<number> {
  const json = args.includes('--json');
  try {
    const env = opts.env ?? process.env;
    const p = parse(args, CONVENE_FLAGS, 'convene');
    const sample = p.flags.has('sample');
    const briefPath = str(p, 'brief');
    if (sample === (briefPath !== null)) {
      throw usageError('convene needs exactly one of --sample or --brief FILE.');
    }
    const harnessFlag = str(p, 'harness');
    if (harnessFlag !== null && !(CHOOSABLE_HARNESSES as readonly string[]).includes(harnessFlag)) {
      throw usageError(`--harness must be one of ${CHOOSABLE_HARNESSES.join(', ')}.`);
    }
    const origin = resolveOrigin(p, env);
    const publicOrigin = resolvePublicOrigin(p, env);

    const body: Record<string, unknown> = {};
    if (sample) body.sample = true;
    if (briefPath !== null) {
      try {
        body.brief = JSON.parse(readFileSync(briefPath, 'utf8'));
      } catch (err) {
        throw invalidInput(`Could not read --brief file: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
    body.harness = harnessFlag ?? detectHarness(env);
    for (const [flag, key] of [['route', 'route_id'], ['model', 'model'], ['mode', 'mode']] as const) {
      const v = str(p, flag);
      if (v !== null) body[key] = v;
    }
    const factsPath = str(p, 'fresh-facts');
    if (factsPath !== null) body.fresh_facts = readFreshFacts(factsPath);

    const res = await callService(origin, '/api/council/convene', { method: 'POST', body }, opts.fetchImpl ?? fetch);
    const sessionId = String(res.session_id);
    const sessionUrl = `${origin}${typeof res.session_path === 'string' ? res.session_path : `/council/${sessionId}`}`;
    const eventsUrl = `${origin}${typeof res.events_path === 'string' ? res.events_path : `/api/council/sessions/${sessionId}/events`}`;
    const chamberUrl = publicOrigin === null ? null : `${publicOrigin}/chamber/#session=${sessionId}`;
    if (json) {
      const extra = chamberUrl === null ? {} : { chamber_url: chamberUrl };
      opts.io.out(`${JSON.stringify({ ...res, session_url: sessionUrl, events_url: eventsUrl, ...extra }, null, 2)}\n`);
      return 0;
    }
    opts.io.out(
      [
        `Council convened${res.sample ? ' (SAMPLE, harmless built-in decision)' : ''}.`,
        `  session_id: ${sessionId}`,
        `  route_id: ${res.route_id}`,
        `  model_label: ${res.model_label}`,
        `  selection_source: ${res.selection_source}`,
        ...(chamberUrl === null ? [] : [`Open the Roast Room: ${chamberUrl}`]),
        `  session: ${sessionUrl}`,
        `  events: ${eventsUrl}`,
        '',
      ].join('\n'),
    );
    return 0;
  } catch (err) {
    return report(opts.io, json, err);
  }
}
