/**
 * Measured, operator-approved token-to-byte conversion per route
 * (W28 decision 3).
 *
 * The context assembler works in canonical bytes; providers publish
 * limits in tokens. This module converts one into the other from a
 * MEASURED, conservative bytes-per-token ratio, and uses it only after
 * the operator approves the exact numbers:
 *
 * - The shipped config (config/route-budgets.json) holds PROPOSED
 *   entries. Any number not yet measured is null; nothing is guessed.
 * - Approvals live in the service data dir, outside the skill folder,
 *   because update sync replaces skill folders. Each approval is bound
 *   to the sha256 of the exact proposed entry, so changed numbers need
 *   a fresh approval.
 * - The resolver returns null for any route that is unmeasured or
 *   unapproved, so planning reports the seat unplannable and dispatch
 *   refuses before any provider call (Section 9.5).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { canonicalHash, canonicalStringify } from '../contracts/index.js';
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

export interface RouteBudgetApproval {
  route_id: string;
  model: string | null;
  entry_sha256: string;
  approved_by: string;
  approved_at: string;
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

/**
 * What a refusal for a missing route budget tells the client. One text for
 * every refusal path, so the first-run message never says less than the
 * per-route one. Nothing here approves anything.
 */
export function routeBudgetRecovery(
  routeId: string = '<route_id>',
  state?: 'awaiting_approval' | 'not_measured' | 'no_entry',
): string {
  const approve =
    `run "node scripts/approve-route-budget.mjs --route ${routeId} --approved-by <name> --data-dir <council service data folder>" to record the approval. ` +
    'No restart is needed: convene again afterwards. A route that already has an approved budget can be used meanwhile.';
  if (state === 'awaiting_approval') {
    // Already measured: measuring again would overwrite the numbers under review.
    return (
      `This route is measured and waiting for the operator to approve the proposed numbers (shown above). Do not measure it again: that replaces the numbers under review. ` +
      'Nothing is approved automatically, and a client cannot approve it. ' +
      `The operator, from the council skill folder: (1) review the proposed numbers; (2) ${approve}`
    );
  }
  return (
    'This route cannot start a council until its token budget is measured and approved by the operator. ' +
    'Nothing is approved automatically, and a client cannot approve it. ' +
    'The operator, from the council skill folder: ' +
    `(1) run "node scripts/measure-route-bytes-per-token.mjs --route ${routeId} --write" (a few small real model calls; it writes PROPOSED numbers into this skill folder's config/route-budgets.json, or the file named by WISE_ELDERS_ROUTE_BUDGETS, and approves nothing; a fleet skill update replaces that file, so the approved numbers must also be committed to the shipped config); ` +
    '(2) review the proposed numbers it prints; ' +
    `(3) ${approve}`
  );
}

export function routeBudgetApprovalsPath(serviceDataDir: string): string {
  return join(serviceDataDir, 'route-budget-approvals.json');
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
const APPROVAL_KEYS = [
  'route_id',
  'model',
  'entry_sha256',
  'approved_by',
  'approved_at',
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

/** Missing file -> []. A present but malformed file throws (fail closed). */
export function loadRouteBudgetApprovals(path: string): RouteBudgetApproval[] {
  let raw: unknown;
  try {
    raw = readJson(path, 'route budget approvals');
  } catch (err) {
    if (err instanceof RouteBudgetConfigError) throw err;
    return [];
  }
  if (!Array.isArray(raw)) fail('route budget approvals', 'must be an array');
  return (raw as unknown[]).map((a, i) => {
    const where = `approvals[${i}]`;
    if (!isRecord(a)) fail(where, 'must be an object');
    const o = a as Record<string, unknown>;
    exactKeys(o, APPROVAL_KEYS, where);
    return {
      route_id: str(o.route_id, where, 'route_id'),
      model: strOrNull(o.model, where, 'model'),
      entry_sha256: str(o.entry_sha256, where, 'entry_sha256'),
      approved_by: str(o.approved_by, where, 'approved_by'),
      approved_at: str(o.approved_at, where, 'approved_at'),
    };
  });
}

// ------------------------------------------------------------ computation

/** sha256 over the canonical form of the WHOLE entry: any changed number changes it. */
export function entrySha256(entry: RouteBudgetEntry): string {
  return canonicalHash(entry);
}

/**
 * Null when any measured field is null. b = measured_min_bytes_per_token
 * * safety_factor; the context limit rounds down and the output reserve
 * rounds up, so both errors favour a smaller prompt.
 */
export function computeRouteBudget(entry: RouteBudgetEntry): ComputedRouteBudget | null {
  if (
    entry.context_window_tokens === null ||
    entry.max_output_tokens === null ||
    entry.measured_min_bytes_per_token === null
  ) {
    return null;
  }
  const b = entry.measured_min_bytes_per_token * entry.safety_factor;
  return {
    context_limit_bytes: Math.floor(entry.context_window_tokens * b),
    response_schema_bytes: entry.response_schema_bytes,
    output_reserve_bytes: Math.ceil(entry.max_output_tokens * b),
  };
}

export type RouteBudgetState =
  | { state: 'approved'; budget: ComputedRouteBudget | null }
  | {
      state: 'awaiting_approval' | 'not_measured' | 'no_entry';
      proposed: RouteBudgetEntry | null;
    };

/**
 * Exact model entry first, then the model:null entry for the route. The
 * first entry found decides; an unmeasured exact entry does not fall
 * through to a broader one.
 */
export function routeBudgetStatus(
  config: RouteBudgetConfig,
  approvals: RouteBudgetApproval[],
  routeId: string,
  model: string | null,
): RouteBudgetState {
  const forRoute = config.entries.filter((e) => e.route_id === routeId);
  const entry =
    (model === null ? undefined : forRoute.find((e) => e.model === model)) ??
    forRoute.find((e) => e.model === null);
  if (!entry) return { state: 'no_entry', proposed: null };
  const budget = computeRouteBudget(entry);
  if (budget === null) return { state: 'not_measured', proposed: entry };
  const sha = entrySha256(entry);
  const approved = approvals.some(
    (a) => a.route_id === entry.route_id && a.model === entry.model && a.entry_sha256 === sha,
  );
  return approved ? { state: 'approved', budget } : { state: 'awaiting_approval', proposed: entry };
}

/** Reads both files fresh; throws RouteBudgetConfigError when either is malformed. */
export function routeBudgetStatusFromFiles(
  input: { configPath: string; approvalsPath: string },
  routeId: string,
  model: string | null,
): RouteBudgetState {
  return routeBudgetStatus(
    loadRouteBudgetConfig(input.configPath),
    loadRouteBudgetApprovals(input.approvalsPath),
    routeId,
    model,
  );
}

/**
 * Re-reads both files on every call (cheap), so an approval written
 * while the service runs is picked up without a restart. Anything not
 * approved, and any unreadable or malformed file, yields null.
 */
export function routeBudgetResolver(input: {
  configPath: string;
  approvalsPath: string;
}): (snapshot: PinnedRouteSnapshot) => ComputedRouteBudget | null {
  return (snapshot) => {
    try {
      const s = routeBudgetStatusFromFiles(input, snapshot.routeId, snapshot.requestedModelOrAlias);
      return s.state === 'approved' ? s.budget : null;
    } catch {
      return null;
    }
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
 * the measured fields change. Never touches approvals.
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
