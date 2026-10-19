/**
 * Token-to-byte conversion per route (W28 decision 3).
 *
 * The context assembler works in canonical bytes; providers publish
 * limits in tokens. This module converts one into the other from a
 * conservative bytes-per-token ratio so a request never overflows the
 * model's window. There is no approval step: a convene on any route
 * just works.
 *
 * - The shipped config (config/route-budgets.json) holds the numbers
 *   measured so far (DeepSeek Flash). A route without measured numbers
 *   uses the built-in conservative defaults below, so it still convenes.
 * - The window and answer limits come from the shipped entry, else from
 *   the limits the route itself reports, else from a safe fallback.
 * - The measurement script is an optional engineering tool that refines
 *   the numbers; nothing requires running it.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { canonicalStringify } from '../contracts/index.js';
import type { PinnedRouteSnapshot } from './route-snapshot.js';

export const ROUTE_BUDGET_SCHEMA = 'wise-elders.route-budgets/v1';
export const MAX_SAFETY_FACTOR = 0.9;

export interface RouteBudgetEntry {
  route_id: string;
  /** null = any model on this route. */
  model: string | null;
  context_window_tokens: number | null;
  max_output_tokens: number | null;
  measured_min_bytes_per_token: number | null;
  /** In (0, 0.9]. */
  safety_factor: number;
  response_schema_bytes: number;
  measured_at: string | null;
  /** Sample set + count + provider usage field used. */
  measurement_basis: string;
}

export interface RouteBudgetConfig {
  schema: typeof ROUTE_BUDGET_SCHEMA;
  entries: RouteBudgetEntry[];
}

export interface ComputedRouteBudget {
  context_limit_bytes: number;
  response_schema_bytes: number;
  output_reserve_bytes: number;
}

export class RouteBudgetConfigError extends Error {
  readonly code = 'ROUTE_BUDGET_CONFIG_INVALID';
  constructor(message: string) {
    super(message);
    this.name = 'RouteBudgetConfigError';
  }
}

export function routeBudgetConfigPath(
  skillRoot: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const override = env.WISE_ELDERS_ROUTE_BUDGETS;
  return override && override.length > 0
    ? override
    : join(skillRoot, 'config', 'route-budgets.json');
}

// ---------------------------------------------------------------- parsing

const ENTRY_KEYS = [
  'route_id',
  'model',
  'context_window_tokens',
  'max_output_tokens',
  'measured_min_bytes_per_token',
  'safety_factor',
  'response_schema_bytes',
  'measured_at',
  'measurement_basis',
] as const;

function fail(where: string, what: string): never {
  throw new RouteBudgetConfigError(`${where}: ${what}`);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function exactKeys(
  obj: Record<string, unknown>,
  keys: readonly string[],
  where: string,
): void {
  for (const k of keys) if (!(k in obj)) fail(where, `missing field "${k}"`);
  for (const k of Object.keys(obj)) {
    if (!keys.includes(k)) fail(where, `unknown field "${k}"`);
  }
}

function str(v: unknown, where: string, field: string): string {
  if (typeof v !== 'string' || v.length === 0) fail(where, `"${field}" must be a non-empty string`);
  return v as string;
}

function strOrNull(v: unknown, where: string, field: string): string | null {
  return v === null ? null : str(v, where, field);
}

function posIntOrNull(v: unknown, where: string, field: string): number | null {
  if (v === null) return null;
  if (typeof v !== 'number' || !Number.isSafeInteger(v) || v <= 0) {
    fail(where, `"${field}" must be null or a positive integer`);
  }
  return v as number;
}

export function parseRouteBudgetEntry(raw: unknown, where = 'entry'): RouteBudgetEntry {
  if (!isRecord(raw)) fail(where, 'must be an object');
  const o = raw as Record<string, unknown>;
  exactKeys(o, ENTRY_KEYS, where);
  const ratio = o.measured_min_bytes_per_token;
  if (ratio !== null && (typeof ratio !== 'number' || !Number.isFinite(ratio) || ratio <= 0)) {
    fail(where, '"measured_min_bytes_per_token" must be null or a positive number');
  }
  const sf = o.safety_factor;
  if (typeof sf !== 'number' || !Number.isFinite(sf) || sf <= 0 || sf > MAX_SAFETY_FACTOR) {
    fail(where, `"safety_factor" must be a number in (0, ${MAX_SAFETY_FACTOR}]`);
  }
  const rsb = o.response_schema_bytes;
  if (typeof rsb !== 'number' || !Number.isSafeInteger(rsb) || rsb < 0) {
    fail(where, '"response_schema_bytes" must be a non-negative integer');
  }
  return {
    route_id: str(o.route_id, where, 'route_id'),
    model: strOrNull(o.model, where, 'model'),
    context_window_tokens: posIntOrNull(o.context_window_tokens, where, 'context_window_tokens'),
    max_output_tokens: posIntOrNull(o.max_output_tokens, where, 'max_output_tokens'),
    measured_min_bytes_per_token: ratio as number | null,
    safety_factor: sf as number,
    response_schema_bytes: rsb as number,
    measured_at: strOrNull(o.measured_at, where, 'measured_at'),
    measurement_basis: (() => {
      if (typeof o.measurement_basis !== 'string') fail(where, '"measurement_basis" must be a string');
      return o.measurement_basis as string;
    })(),
  };
}

function readJson(path: string, label: string): unknown {
  let text: string;
  try {
    text = readFileSync(path, 'utf8');
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') throw err;
    fail(label, 'could not be read');
  }
  try {
    return JSON.parse(text);
  } catch {
    return fail(label, 'is not valid JSON');
  }
}

/** Throws RouteBudgetConfigError on any malformed content, incl. a missing file. */
export function loadRouteBudgetConfig(path: string): RouteBudgetConfig {
  let raw: unknown;
  try {
    raw = readJson(path, 'route budget config');
  } catch (err) {
    if (err instanceof RouteBudgetConfigError) throw err;
    throw new RouteBudgetConfigError('route budget config: file not found or unreadable');
  }
  if (!isRecord(raw)) fail('route budget config', 'must be an object');
  const o = raw as Record<string, unknown>;
  exactKeys(o, ['schema', 'entries'], 'route budget config');
  if (o.schema !== ROUTE_BUDGET_SCHEMA) fail('route budget config', `schema must be "${ROUTE_BUDGET_SCHEMA}"`);
  if (!Array.isArray(o.entries)) fail('route budget config', '"entries" must be an array');
  const entries = (o.entries as unknown[]).map((e, i) => parseRouteBudgetEntry(e, `entries[${i}]`));
  const seen = new Set<string>();
  for (const e of entries) {
    const k = JSON.stringify([e.route_id, e.model]);
    if (seen.has(k)) fail('route budget config', `duplicate entry for route "${e.route_id}" model ${e.model ?? 'null'}`);
    seen.add(k);
  }
  return { schema: ROUTE_BUDGET_SCHEMA, entries };
}

// ------------------------------------------------------------ computation

/** Built-in conservative defaults for a route with no measured numbers. */
export const DEFAULT_BYTES_PER_TOKEN = 1.0;
export const DEFAULT_SAFETY_FACTOR = 0.8;
export const DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000;
export const DEFAULT_MAX_OUTPUT_TOKENS = 16_384;
export const DEFAULT_RESPONSE_SCHEMA_BYTES = 10_159;

/**
 * b = bytes-per-token * safety_factor; the context limit rounds down and
 * the output reserve rounds up, so both errors favour a smaller prompt.
 * Window: entry, else what the route reports, else the fallback. An
 * answer limit that is not smaller than the window becomes a quarter of it.
 */
export function computeRouteBudget(
  entry: RouteBudgetEntry | null,
  reported?: { contextWindowTokens: number | null; maxOutputTokens: number | null },
): ComputedRouteBudget {
  const window =
    entry?.context_window_tokens ?? reported?.contextWindowTokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS;
  const reportedOutput =
    entry?.max_output_tokens ?? reported?.maxOutputTokens ?? DEFAULT_MAX_OUTPUT_TOKENS;
  const output = reportedOutput < window ? reportedOutput : Math.floor(window / 4);
  const b =
    (entry?.measured_min_bytes_per_token ?? DEFAULT_BYTES_PER_TOKEN) *
    (entry?.safety_factor ?? DEFAULT_SAFETY_FACTOR);
  return {
    context_limit_bytes: Math.floor(window * b),
    response_schema_bytes: entry?.response_schema_bytes ?? DEFAULT_RESPONSE_SCHEMA_BYTES,
    output_reserve_bytes: Math.ceil(output * b),
  };
}

/**
 * Exact model entry first, then the model:null entry for the route; null
 * when the shipped config has neither (the defaults then apply).
 */
export function findRouteBudgetEntry(
  config: RouteBudgetConfig | null,
  routeId: string,
  model: string | null,
): RouteBudgetEntry | null {
  const forRoute = (config?.entries ?? []).filter((e) => e.route_id === routeId);
  return (
    (model === null ? undefined : forRoute.find((e) => e.model === model)) ??
    forRoute.find((e) => e.model === null) ??
    null
  );
}

/**
 * Always returns limits. Re-reads the shipped config on every call
 * (cheap); a missing or malformed file falls back to the defaults.
 */
export function routeBudgetResolver(input: {
  configPath: string | null;
}): (snapshot: PinnedRouteSnapshot) => ComputedRouteBudget {
  return (snapshot) => {
    let config: RouteBudgetConfig | null = null;
    try {
      if (input.configPath) config = loadRouteBudgetConfig(input.configPath);
    } catch {
      // ponytail: unreadable config means the conservative defaults, never a refusal
    }
    return computeRouteBudget(
      findRouteBudgetEntry(config, snapshot.routeId, snapshot.requestedModelOrAlias),
      snapshot.capabilitySnapshot,
    );
  };
}

// ------------------------------------------------------------ measurement

export interface BytesTokensPair {
  bytes: number;
  input_tokens: number | null;
}

export const SAMPLE_SET_ID = 'wise-elders.route-bytes-samples/v1';
export const USAGE_FIELD = 'usage.input_tokens';
/** The ratio is floored to this many decimals so rounding never raises it. */
const RATIO_DECIMALS = 10_000;

/** Bytes a request puts on the wire as text: system, blank line, canonical input. */
export function requestBytes(system: string, input: unknown): number {
  return new TextEncoder().encode(`${system}\n\n${canonicalStringify(input)}`).length;
}

function validPairs(pairs: readonly BytesTokensPair[]): Array<{ bytes: number; input_tokens: number }> {
  return pairs.filter(
    (p): p is { bytes: number; input_tokens: number } =>
      Number.isFinite(p.bytes) &&
      p.bytes > 0 &&
      typeof p.input_tokens === 'number' &&
      Number.isFinite(p.input_tokens) &&
      p.input_tokens > 0,
  );
}

/**
 * The SMALLEST observed bytes-per-token ratio (never the mean): the
 * densest text is the one that overflows a window first. Null when no
 * pair has a usable token count.
 */
export function minBytesPerToken(pairs: readonly BytesTokensPair[]): number | null {
  const ok = validPairs(pairs);
  if (ok.length === 0) return null;
  const min = Math.min(...ok.map((p) => p.bytes / p.input_tokens));
  return Math.floor(min * RATIO_DECIMALS) / RATIO_DECIMALS;
}

/**
 * Deterministic proposed entry from recorded pairs. Keeps the base
 * entry's window, output limit, safety factor and schema bytes; only
 * the measured fields change. 
 */
export function proposeRouteBudgetEntry(input: {
  base: RouteBudgetEntry | null;
  route_id: string;
  model: string | null;
  pairs: readonly BytesTokensPair[];
  measured_at: string | null;
  usage_field?: string;
}): RouteBudgetEntry {
  const base = input.base;
  const ratio = minBytesPerToken(input.pairs);
  const n = validPairs(input.pairs).length;
  return {
    route_id: input.route_id,
    model: input.model,
    context_window_tokens: base?.context_window_tokens ?? null,
    max_output_tokens: base?.max_output_tokens ?? null,
    measured_min_bytes_per_token: ratio,
    safety_factor: base?.safety_factor ?? 0.8,
    response_schema_bytes: base?.response_schema_bytes ?? 0,
    measured_at: ratio === null ? null : input.measured_at,
    measurement_basis:
      `${SAMPLE_SET_ID}, ${n} of ${input.pairs.length} payloads with a usable token count, ` +
      `min of bytes/${input.usage_field ?? USAGE_FIELD}, ratio floored to 4 decimals`,
  };
}
