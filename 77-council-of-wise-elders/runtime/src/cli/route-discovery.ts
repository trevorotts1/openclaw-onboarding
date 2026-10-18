/**
 * Read-only discovery of the client's EXISTING configured routes
 * (RP-046-1 repair for DEFECT-046-A; WER-007 host-configuration slice;
 * directive Sections 13.4, 25.2 step 7, 25.6).
 *
 * The standalone composition binds to the route configuration the
 * client already has on this machine. Discovery reads that
 * configuration; it never writes it, never creates a parallel config
 * format, never registers a new surface, and never copies a credential
 * value anywhere (credential state is recorded as presence by NAME only;
 * a value is resolved at flight time through the resolver the local host
 * composes, Section 13.7).
 *
 * HOST LAYOUT (WER-007). Nothing here assumes `~/.openclaw` and nothing
 * assumes JSON:
 *
 * - the config root is `OPENCLAW_ROOT`, then `OC_ROOT`, then `OC_CONFIG`,
 *   then the existing platform default (`$HOME/.openclaw`, or
 *   `/data/.openclaw` on a Linux box where that installation exists);
 * - the config file is the explicit `OPENCLAW_CONFIG_PATH` / `OC_JSON` /
 *   `CONFIG_JSON`, else `openclaw.json`, `openclaw.json5` or
 *   `openclaw.jsonc` inside that root. `.json5`/`.jsonc` are parsed with
 *   the JSON5 reader below, so a host that uses comments, unquoted keys,
 *   single quotes or trailing commas is read as written;
 * - the selected agent's workspace is
 *   `OPENCLAW_WORKSPACE_PATH` / `OPENCLAW_WORKSPACE_ROOT`, then the
 *   selected agent entry (`agents.entries.<id>.workspace`, legacy
 *   `agents.list[id].workspace`), then `agents.defaults.workspace`, then
 *   `<root>/workspace` — the same resolver `install.sh` and
 *   `update-skills.sh` use;
 * - the state root is the host root itself (agent homes, logs,
 *   credentials, secrets env and skills all live under it);
 * - extra skill directories come from `OPENCLAW_SKILLS_DIR` /
 *   `OC_SKILLS_DIR`, `<root>/skills`, and the configuration's own
 *   `skills.load.extraDirs` / `skills.extraDirs`.
 *
 * ROUTES. Two existing configuration families are discovered:
 *
 * 1. Harness config roots (Section 13.4 adapter 3): a Claude Code /
 *    Claude-Nine config root that exists on this machine
 *    (~/.claude-nine, ~/.claude, or the directory CLAUDE_CONFIG_DIR
 *    names for the .claude root) is a configured harness route. The
 *    route id is `<slug>-configured`, exactly the id a session spec
 *    pins for that harness (the CWE-046 canary pinned
 *    `claude-nine-configured`).
 *
 * 2. OpenClaw provider configuration (Section 13.4 adapter 1): each
 *    `models.providers` entry is a configured route, route id
 *    `<provider>-configured`. The wire model is the configuration's OWN
 *    selection: the agent default primary when it names this provider,
 *    else the single allowed model, else the provider's single listed
 *    model. More than one candidate is AMBIGUOUS and is refused, never
 *    guessed. The API family is classified from the provider's declared
 *    `api`; only an OpenAI-compatible endpoint is composed here, and a
 *    provider of another family fails explicitly instead of being
 *    reinterpreted as compatible.
 *
 * FAILURE IS EXPLICIT. Every route carries a typed `failure`
 * (`ROUTE_MODEL_AMBIGUOUS`, `ROUTE_API_FAMILY_UNSUPPORTED`,
 * `ROUTE_SECRET_REFERENCE_UNRESOLVED`, ...). `discoverConfiguredRoutes`
 * stays total and reports discovered-but-uncomposed routes; the strict
 * `resolveRouteForDispatch` / `discoverRouteSnapshot` entry points throw
 * a `RouteDiscoveryError` with the same code, so no developer default
 * can silently stand in for the host's real answer.
 *
 * IDENTITY. A discovered route is `configured` identity only.
 * `buildRouteSnapshot` freezes it through the WER-006 contract
 * (`freezeRouteSnapshot`), where configured identity and
 * transport-reported identity are separate fields. Discovery never
 * reports transport identity: an unreported fixed route and every
 * unreported combination member stay `UNKNOWN` with an explicit reason.
 *
 * SECRETS. A named reference (`${NAME}`, `$NAME`, `env:NAME`, or an
 * object form) is resolved by NAME through the host's existing stores
 * (process env, the config's own `env` block, `<root>/secrets/.env`,
 * `<root>/.env`). The reference text and the stores checked are
 * recorded; the VALUE never is, and every error message built here is
 * scrubbed of candidate values before it is thrown.
 */

import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import {
  basename,
  delimiter,
  dirname,
  isAbsolute,
  join,
  resolve,
} from 'node:path';
import type { CredentialSourceName } from '../providers/selection.js';
import {
  freezeRouteSnapshot,
  UNKNOWN_ROUTE_IDENTITY,
  type CouncilRouteSnapshot,
  type RouteApiFamily,
  type RouteSnapshotDraft,
  type RouteSnapshotLimits,
  type RouteSnapshotReasoning,
  type TransportReportedRouteIdentity,
} from '../providers/route-snapshot.js';
import type {
  CredentialPresence,
  RouteCapabilitySnapshot,
  TrustedScope,
} from '../providers/selection.js';
import {
  defaultRuntimePrefix,
  resolveInstalledCli,
} from '../bridges/installed-cli.js';

// ---------------------------------------------------------------------------
// Public shapes
// ---------------------------------------------------------------------------

export type DiscoveredRouteKind = 'harness' | 'compatible' | 'unsupported';

/** Precise, secret-free route-discovery failure codes. */
export type RouteDiscoveryFailureCode =
  | 'ROUTE_HOST_ROOT_AMBIGUOUS'
  | 'ROUTE_HOST_CONFIG_AMBIGUOUS'
  | 'ROUTE_HOST_CONFIG_MISSING'
  | 'ROUTE_HOST_CONFIG_INVALID'
  | 'ROUTE_ID_UNKNOWN'
  | 'ROUTE_HARNESS_EXECUTABLE_MISSING'
  | 'ROUTE_ENDPOINT_MISSING'
  | 'ROUTE_API_FAMILY_UNSUPPORTED'
  | 'ROUTE_MODEL_MISSING'
  | 'ROUTE_MODEL_AMBIGUOUS'
  | 'ROUTE_SECRET_REFERENCE_UNRESOLVED';

export interface RouteFailure {
  code: RouteDiscoveryFailureCode;
  /** Secret-free explanation: names, API families and paths only. */
  detail: string;
}

/** Typed, secret-free discovery failure. */
export class RouteDiscoveryError extends Error {
  readonly code: RouteDiscoveryFailureCode;
  readonly checked: string[];

  constructor(code: RouteDiscoveryFailureCode, detail: string, checked: string[] = []) {
    super(`${code}: ${detail}`);
    this.name = 'RouteDiscoveryError';
    this.code = code;
    this.checked = [...checked];
  }
}

/** Presence-only credential record (Section 13.7): names, never values. */
export interface DiscoveredCredential {
  state: 'present' | 'absent' | 'not_required';
  envVar: string | null;
  source: CredentialSourceName | null;
  /** The reference text as configured (for example `${OPENAI_API_KEY}`). */
  reference: string | null;
  /** Stores checked, by name/path. Never a value. */
  checked: string[];
}

export interface RouteHostBinding {
  configRoot: string;
  stateRoot: string;
  workspace: string;
  selectedAgentId: string;
  configProfile: string;
}

export interface DiscoveredRoute {
  routeId: string;
  providerSlug: string;
  kind: DiscoveredRouteKind;
  identityLevel: 'configured';
  /** True when a real transport can be composed for this route now. */
  composable: boolean;
  /** Why the route is not composable, when it is not. */
  notComposableReason: string | null;
  /** Typed reason, so strict callers never re-parse prose. */
  failure: RouteFailure | null;
  host: RouteHostBinding;
  harness?: {
    configDir: string;
    configRootName: string;
    /** Absolute path of the harness executable, when found. */
    executable: string | null;
  };
  compatible?: {
    baseUrl: string;
    /** The configuration's own model for this provider, when unambiguous. */
    modelId: string | null;
    /** Every configured candidate model id (never a secret). */
    modelCandidates: string[];
    /** Declared API family; only `openai_compatible` is composed here. */
    apiFamily: RouteApiFamily;
    credential: DiscoveredCredential;
    /** The existing config file the credential resolver re-reads at flight time. */
    configPath: string;
    configFormat: 'json' | 'json5';
    /** Existing secret env stores the flight-time resolver also checks. */
    envFiles: string[];
    providerId: string;
    capabilitySnapshot: RouteCapabilitySnapshot;
  };
}

/** The secret-free shape surfaced by `models` and the doctor. */
export interface RouteDiscoveryInfo {
  route_id: string;
  provider_slug: string;
  kind: DiscoveredRouteKind;
  identity_level: 'configured';
  composed: boolean;
  not_composed_reason: string | null;
}

export function routeDiscoveryInfo(route: DiscoveredRoute, composed: boolean): RouteDiscoveryInfo {
  return {
    route_id: route.routeId,
    provider_slug: route.providerSlug,
    kind: route.kind,
    identity_level: route.identityLevel,
    composed,
    not_composed_reason: composed ? null : route.notComposableReason,
  };
}

/** The WER-005 receipt bridge's answer about the installed runtime. */
export interface HostRuntimeReceipt {
  installed: boolean;
  prefix: string;
  releaseId: string | null;
  dataDir: string | null;
  cliPath: string | null;
  failureCode: string | null;
  checked: string[];
}

/** The ACTUAL host layout discovery resolved, with its provenance. */
export interface HostLayout {
  homeDir: string;
  /** OpenClaw installation root (not assumed to be ~/.openclaw). */
  configRoot: string;
  configRootName: string;
  configPath: string;
  configExists: boolean;
  configFormat: 'json' | 'json5';
  /** Root of the host's own state (agents, logs, credentials, skills). */
  stateRoot: string;
  statePaths: {
    agents: string;
    logs: string;
    credentials: string;
    authProfiles: string;
    secretsEnv: string;
    skills: string;
  };
  workspace: string;
  workspaceSource: 'env_pin' | 'agent_override' | 'agents_default' | 'root_default';
  selectedAgentId: string;
  /** Existing skill directories the host actually has. */
  skillDirs: string[];
  /** Configured extra skill directories (may not exist yet). */
  extraSkillDirs: string[];
  /** Secret env files checked for named references, by path. */
  secretsEnvFiles: string[];
  /** Every input consulted, by name/path (negative-result evidence). */
  sources: string[];
  /** The WER-005 installed-runtime receipt answer, consumed not re-derived. */
  runtime: HostRuntimeReceipt;
}

export interface HostLayoutOptions {
  /** Home directory to resolve under. Default: the OS home directory. */
  homeDir?: string;
  /** Environment for root/config/workspace/skills/credential presence. Default: process.env. */
  env?: NodeJS.ProcessEnv;
  /** Explicit root; wins over the environment. */
  root?: string;
  /** Explicit config file; wins over the environment and the root candidates. */
  configPath?: string;
  /** Selected agent id. Default: OPENCLAW_AGENT_ID, else `main`. */
  agentId?: string;
  /** Platform override for the Linux /data installation check (tests). */
  platform?: string;
  /** When true, a missing config file is an explicit failure. */
  requireConfig?: boolean;
}

export type RouteDiscoveryOptions = HostLayoutOptions;

export interface DiscoveredHostRoutes {
  layout: HostLayout;
  routes: DiscoveredRoute[];
}

export interface ResolvedRoute {
  route: DiscoveredRoute;
  layout: HostLayout;
}

/** Snapshot input for the frozen WER-006 contract. */
export interface RouteSnapshotOptions {
  sessionId: string;
  sessionOwner: string;
  policySha256: string;
  createdAt: string;
  scope: TrustedScope;
  capabilityVersion: string;
  routeRevision?: number;
  /** Absent means UNKNOWN/not_probed. Never inferred from configuration. */
  transportReported?: TransportReportedRouteIdentity;
  /** Optional combination pin; each unreported member freezes as UNKNOWN. */
  combination?: { alias: string; members: string[] };
  reasoning?: Partial<RouteSnapshotReasoning>;
  limits?: Partial<RouteSnapshotLimits>;
}

const ROUTE_ROOT_ENV = ['OPENCLAW_ROOT', 'OC_ROOT', 'OC_CONFIG'] as const;
const ROUTE_CONFIG_ENV = ['OPENCLAW_CONFIG_PATH', 'OC_JSON', 'CONFIG_JSON'] as const;
const ROUTE_WORKSPACE_ENV = ['OPENCLAW_WORKSPACE_PATH', 'OPENCLAW_WORKSPACE_ROOT'] as const;
const ROUTE_SKILLS_ENV = ['OPENCLAW_SKILLS_DIR', 'OC_SKILLS_DIR'] as const;
const ROUTE_SECRETS_ENV = ['OC_SECRETS_ENV', 'OPENCLAW_SECRETS_ENV', 'SECRETS_ENV'] as const;

const CONFIG_FILE_CANDIDATES = ['openclaw.json', 'openclaw.json5', 'openclaw.jsonc'] as const;

// ---------------------------------------------------------------------------
// Small filesystem helpers
// ---------------------------------------------------------------------------

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function isExecutableFile(path: string): boolean {
  try {
    const st = statSync(path);
    return st.isFile() && (st.mode & 0o111) !== 0;
  } catch {
    return false;
  }
}

function canonicalOrResolved(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return resolve(path);
  }
}

function expandHome(value: string, home: string): string {
  if (value === '~') return home;
  if (value.startsWith('~/')) return join(home, value.slice(2));
  return value;
}

function firstEnv(env: NodeJS.ProcessEnv, names: readonly string[]): { name: string; value: string } | null {
  for (const name of names) {
    const value = env[name];
    if (typeof value === 'string' && value.trim().length > 0) {
      return { name, value: value.trim() };
    }
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function findExecutable(
  home: string,
  env: NodeJS.ProcessEnv,
  names: string[],
): string | null {
  for (const name of names) {
    const local = join(home, '.local', 'bin', name);
    if (isExecutableFile(local)) return local;
  }
  const pathDirs = (env.PATH ?? '').split(delimiter).filter((d) => d.length > 0);
  for (const name of names) {
    for (const dir of pathDirs) {
      const candidate = join(dir, name);
      if (isExecutableFile(candidate)) return candidate;
    }
  }
  return null;
}

function isLoopbackBaseUrl(baseUrl: string): boolean {
  try {
    const host = new URL(baseUrl).hostname.toLowerCase();
    return host === 'localhost' || host === '::1' || host === '[::1]' || /^127\./.test(host);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// JSON5 reader (a host that uses JSON5 must be read as written)
// ---------------------------------------------------------------------------

class Json5SyntaxError extends Error {}

class Json5Reader {
  private index = 0;

  constructor(private readonly text: string) {}

  parse(): unknown {
    const value = this.value();
    this.skipTrivia();
    if (this.index < this.text.length) {
      this.fail('unexpected trailing content');
    }
    return value;
  }

  private fail(message: string): never {
    throw new Json5SyntaxError(`${message} at offset ${this.index}`);
  }

  private skipTrivia(): void {
    for (;;) {
      const ch = this.text[this.index];
      if (ch === undefined) return;
      if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r' || ch === '\f' || ch === '\v' || ch === ' ' || ch === '﻿') {
        this.index += 1;
        continue;
      }
      if (ch === '/' && this.text[this.index + 1] === '/') {
        this.index += 2;
        while (this.index < this.text.length && this.text[this.index] !== '\n') this.index += 1;
        continue;
      }
      if (ch === '/' && this.text[this.index + 1] === '*') {
        const end = this.text.indexOf('*/', this.index + 2);
        if (end < 0) this.fail('unterminated block comment');
        this.index = end + 2;
        continue;
      }
      return;
    }
  }

  private value(): unknown {
    this.skipTrivia();
    const ch = this.text[this.index];
    if (ch === undefined) this.fail('unexpected end of input');
    if (ch === '{') return this.object();
    if (ch === '[') return this.array();
    if (ch === '"' || ch === "'") return this.string();
    if (ch === '+' || ch === '-' || ch === '.' || (ch >= '0' && ch <= '9')) return this.number();
    const identifier = this.identifier();
    if (identifier === 'true') return true;
    if (identifier === 'false') return false;
    if (identifier === 'null') return null;
    if (identifier === 'Infinity') return Infinity;
    if (identifier === 'NaN') return NaN;
    this.fail(`unexpected token ${JSON.stringify(identifier)}`);
  }

  private object(): Record<string, unknown> {
    this.index += 1; // {
    const out: Record<string, unknown> = {};
    for (;;) {
      this.skipTrivia();
      if (this.text[this.index] === '}') {
        this.index += 1;
        return out;
      }
      const ch = this.text[this.index];
      const key = ch === '"' || ch === "'" ? this.string() : this.identifier();
      this.skipTrivia();
      if (this.text[this.index] !== ':') this.fail('expected ":"');
      this.index += 1;
      out[key] = this.value();
      this.skipTrivia();
      const next = this.text[this.index];
      if (next === ',') {
        this.index += 1;
        continue;
      }
      if (next === '}') {
        this.index += 1;
        return out;
      }
      this.fail('expected "," or "}"');
    }
  }

  private array(): unknown[] {
    this.index += 1; // [
    const out: unknown[] = [];
    for (;;) {
      this.skipTrivia();
      if (this.text[this.index] === ']') {
        this.index += 1;
        return out;
      }
      out.push(this.value());
      this.skipTrivia();
      const next = this.text[this.index];
      if (next === ',') {
        this.index += 1;
        continue;
      }
      if (next === ']') {
        this.index += 1;
        return out;
      }
      this.fail('expected "," or "]"');
    }
  }

  private string(): string {
    const quote = this.text[this.index];
    this.index += 1;
    let out = '';
    for (;;) {
      const ch = this.text[this.index];
      if (ch === undefined) this.fail('unterminated string');
      this.index += 1;
      if (ch === quote) return out;
      if (ch !== '\\') {
        out += ch;
        continue;
      }
      const esc = this.text[this.index];
      if (esc === undefined) this.fail('unterminated escape');
      this.index += 1;
      switch (esc) {
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'v': out += '\v'; break;
        case '0': out += '\0'; break;
        case '\n': break; // line continuation
        case 'x': {
          const hex = this.text.slice(this.index, this.index + 2);
          if (!/^[0-9a-fA-F]{2}$/.test(hex)) this.fail('invalid \\x escape');
          out += String.fromCharCode(parseInt(hex, 16));
          this.index += 2;
          break;
        }
        case 'u': {
          const hex = this.text.slice(this.index, this.index + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) this.fail('invalid \\u escape');
          out += String.fromCharCode(parseInt(hex, 16));
          this.index += 4;
          break;
        }
        default:
          out += esc;
      }
    }
  }

  private identifier(): string {
    this.skipTrivia();
    const start = this.index;
    const ch = this.text[this.index];
    if (ch === undefined || !/[A-Za-z_$]/.test(ch)) this.fail('expected an identifier');
    this.index += 1;
    while (this.index < this.text.length && /[A-Za-z0-9_$]/.test(this.text[this.index])) {
      this.index += 1;
    }
    return this.text.slice(start, this.index);
  }

  private number(): number {
    this.skipTrivia();
    const match = /^[+-]?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|Infinity|NaN)/.exec(
      this.text.slice(this.index),
    );
    if (!match) this.fail('invalid number');
    this.index += match[0].length;
    const raw = match[0];
    if (/[xX]/.test(raw)) {
      const negative = raw.startsWith('-');
      const digits = raw.replace(/^[+-]?0[xX]/, '');
      const value = parseInt(digits, 16);
      return negative ? -value : value;
    }
    return Number(raw);
  }
}

/** Parse JSON5 (comments, unquoted keys, single quotes, trailing commas). */
export function parseJson5(text: string): unknown {
  return new Json5Reader(text).parse();
}

function parseConfigText(
  text: string,
  format: 'json' | 'json5',
  path: string,
): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = format === 'json5' ? parseJson5(text) : (JSON.parse(text) as unknown);
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      `The host configuration at ${path} is not valid ${format === 'json5' ? 'JSON5' : 'JSON'} (${reason}). It was not replaced and no default was substituted.`,
      [path],
    );
  }
  const record = asRecord(parsed);
  if (!record) {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      `The host configuration at ${path} is not a JSON object, so no route can be read from it.`,
      [path],
    );
  }
  return record;
}

function formatOf(path: string): 'json' | 'json5' {
  return path.endsWith('.json5') || path.endsWith('.jsonc') ? 'json5' : 'json';
}

// ---------------------------------------------------------------------------
// Secret references (NAME only; the value never leaves the resolver)
// ---------------------------------------------------------------------------

function parseEnvFile(path: string): Record<string, string> | null {
  let text: string;
  try {
    text = readFileSync(path, 'utf8');
  } catch {
    return null;
  }
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/u)) {
    const trimmed = line.trim();
    if (trimmed.length === 0 || trimmed.startsWith('#')) continue;
    const withoutExport = trimmed.startsWith('export ') ? trimmed.slice(7).trim() : trimmed;
    const eq = withoutExport.indexOf('=');
    if (eq <= 0) continue;
    const key = withoutExport.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
    let value = withoutExport.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

interface SecretLookup {
  found: boolean;
  value: string | null;
  source: CredentialSourceName | null;
  checked: string[];
}

/**
 * Resolve a named secret reference through the host's existing stores.
 * The returned value is for the in-flight Authorization header only; the
 * caller must never record it.
 */
function lookupSecret(
  name: string,
  env: NodeJS.ProcessEnv,
  configEnv: Record<string, unknown> | null,
  envFiles: string[],
): SecretLookup {
  const checked: string[] = [`process.env:${name}`];
  if (typeof env[name] === 'string' && env[name]!.length > 0) {
    return { found: true, value: env[name]!, source: 'process.env', checked };
  }
  checked.push(`openclaw.json:env.${name}`);
  if (configEnv && typeof configEnv[name] === 'string' && (configEnv[name] as string).length > 0) {
    return { found: true, value: configEnv[name] as string, source: 'openclaw_json', checked };
  }
  for (const file of envFiles) {
    checked.push(file);
    const parsed = parseEnvFile(file);
    if (parsed && typeof parsed[name] === 'string' && parsed[name].length > 0) {
      return { found: true, value: parsed[name], source: 'env_file', checked };
    }
  }
  return { found: false, value: null, source: null, checked };
}

interface ParsedCredentialReference {
  name: string;
  reference: string;
}

function parseApiKeyReference(apiKey: unknown): ParsedCredentialReference | null {
  if (typeof apiKey === 'string') {
    const trimmed = apiKey.trim();
    const braced = /^\$\{([^}]+)\}$/.exec(trimmed);
    if (braced) return { name: braced[1].trim(), reference: trimmed };
    const prefixed = /^(?:env|secret):(.+)$/i.exec(trimmed);
    if (prefixed) return { name: prefixed[1].trim(), reference: trimmed };
    const bare = /^\$([A-Za-z_][A-Za-z0-9_]*)$/.exec(trimmed);
    if (bare) return { name: bare[1], reference: trimmed };
    return null;
  }
  const record = asRecord(apiKey);
  if (!record) return null;
  for (const key of ['env', 'envVar', 'name', '$secret']) {
    const value = record[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return { name: value.trim(), reference: `${key}:${value.trim()}` };
    }
  }
  return null;
}

function guessedEnvVar(providerId: string): string {
  return `${providerId.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase()}_API_KEY`;
}

function scrubSecretValues(message: string, values: string[]): string {
  let safe = message;
  for (const value of values) {
    if (value.length > 0) safe = safe.split(value).join('[REDACTED]');
  }
  return safe;
}

// ---------------------------------------------------------------------------
// Host layout (WER-007)
// ---------------------------------------------------------------------------

function readConfigEnv(config: Record<string, unknown> | null): Record<string, unknown> | null {
  return config ? asRecord(config.env) : null;
}

function configWorkspace(config: Record<string, unknown> | null, agentId: string): {
  workspace: string | null;
  source: HostLayout['workspaceSource'] | null;
} {
  if (!config) return { workspace: null, source: null };
  const agents = asRecord(config.agents);
  const entries = agents ? asRecord(agents.entries) : null;
  const entry = entries ? asRecord(entries[agentId]) : null;
  if (entry && typeof entry.workspace === 'string' && entry.workspace.trim().length > 0) {
    return { workspace: entry.workspace.trim(), source: 'agent_override' };
  }
  if (agents && Array.isArray(agents.list)) {
    for (const raw of agents.list) {
      const item = asRecord(raw);
      if (item && item.id === agentId && typeof item.workspace === 'string' && item.workspace.trim().length > 0) {
        return { workspace: item.workspace.trim(), source: 'agent_override' };
      }
    }
  }
  const defaults = agents ? asRecord(agents.defaults) : null;
  if (defaults && typeof defaults.workspace === 'string' && defaults.workspace.trim().length > 0) {
    return { workspace: defaults.workspace.trim(), source: 'agents_default' };
  }
  return { workspace: null, source: null };
}

function collectExtraSkillDirs(config: Record<string, unknown> | null, home: string): string[] {
  const out: string[] = [];
  if (!config) return out;
  const skills = asRecord(config.skills);
  const load = skills ? asRecord(skills.load) : null;
  for (const holder of [load, skills]) {
    if (!holder) continue;
    for (const key of ['extraDirs', 'extra_dirs'] as const) {
      const raw = holder[key];
      if (!Array.isArray(raw)) continue;
      for (const entry of raw) {
        if (typeof entry !== 'string' || entry.trim().length === 0) continue;
        out.push(resolve(expandHome(entry.trim(), home)));
      }
    }
  }
  return [...new Set(out)];
}

/**
 * Resolve the ACTUAL OpenClaw host layout. Throws a typed
 * `RouteDiscoveryError` when the host itself is ambiguous or malformed;
 * never substitutes a developer default.
 */
function resolveHostContext(options: HostLayoutOptions = {}): {
  layout: HostLayout;
  config: Record<string, unknown> | null;
} {
  const home = resolve(options.homeDir ?? homedir());
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const sources: string[] = [];
  const checked: string[] = [];

  // -- root ---------------------------------------------------------------
  let configRoot: string;
  const rootEnv = firstEnv(env, ROUTE_ROOT_ENV);
  if (options.root && options.root.trim().length > 0) {
    configRoot = options.root.trim();
    sources.push('option:root');
  } else if (rootEnv) {
    configRoot = rootEnv.value;
    sources.push(`${rootEnv.name}=${rootEnv.value}`);
  } else {
    const homeRoot = join(home, '.openclaw');
    sources.push('.openclaw-under-home');
    configRoot = homeRoot;
    if (platform === 'linux' && isDirectory('/data/.openclaw')) {
      if (isDirectory(homeRoot)) {
        const a = canonicalOrResolved(homeRoot);
        const b = canonicalOrResolved('/data/.openclaw');
        if (a !== b) {
          throw new RouteDiscoveryError(
            'ROUTE_HOST_ROOT_AMBIGUOUS',
            `Two OpenClaw roots exist: ${homeRoot} and /data/.openclaw resolve to different installations. Set OPENCLAW_ROOT to the intended client installation; discovery will not choose one.`,
            [homeRoot, '/data/.openclaw'],
          );
        }
      }
      configRoot = '/data/.openclaw';
      sources.push('/data/.openclaw');
    }
  }
  if (!isAbsolute(configRoot)) {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      `The OpenClaw root ${JSON.stringify(configRoot)} is not absolute. A relative root would make discovery depend on the process working directory.`,
      [configRoot],
    );
  }
  configRoot = resolve(configRoot);
  if (configRoot === '/') {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      'The OpenClaw root cannot be the filesystem root.',
      [configRoot],
    );
  }

  // -- config file --------------------------------------------------------
  const configEnv = firstEnv(env, ROUTE_CONFIG_ENV);
  let configPath: string;
  if (options.configPath && options.configPath.trim().length > 0) {
    configPath = options.configPath.trim();
    sources.push('option:configPath');
  } else if (configEnv) {
    configPath = configEnv.value;
    sources.push(`${configEnv.name}=${configEnv.value}`);
  } else {
    const present = CONFIG_FILE_CANDIDATES.map((name) => join(configRoot, name)).filter((p) =>
      existsSync(p),
    );
    for (const candidate of CONFIG_FILE_CANDIDATES) checked.push(join(configRoot, candidate));
    if (present.length > 1) {
      throw new RouteDiscoveryError(
        'ROUTE_HOST_CONFIG_AMBIGUOUS',
        `Multiple host configuration files exist in ${configRoot} (${present
          .map((p) => basename(p))
          .join(', ')}). Set OPENCLAW_CONFIG_PATH to the one this host actually uses; discovery will not pick one.`,
        present,
      );
    }
    configPath = present[0] ?? join(configRoot, CONFIG_FILE_CANDIDATES[0]);
    sources.push(present.length > 0 ? configPath : 'no-config-file');
  }
  if (!isAbsolute(configPath)) {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      `The OpenClaw configuration path ${JSON.stringify(configPath)} is not absolute.`,
      [configPath],
    );
  }
  configPath = resolve(configPath);
  const configExists = existsSync(configPath);
  const configFormat = formatOf(configPath);
  if (!configExists && options.requireConfig === true) {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_MISSING',
      `No OpenClaw configuration exists at ${configPath}. Discovery does not invent a route from a default. Point OPENCLAW_ROOT or OPENCLAW_CONFIG_PATH at the host's real configuration.`,
      [...checked, configPath],
    );
  }
  const config =
    configExists ? parseConfigText(readFileSync(configPath, 'utf8'), configFormat, configPath) : null;
  if (configExists) checked.push(configPath);

  // -- selected agent and workspace --------------------------------------
  const selectedAgentId =
    (options.agentId && options.agentId.trim().length > 0 ? options.agentId.trim() : null) ??
    (typeof env.OPENCLAW_AGENT_ID === 'string' && env.OPENCLAW_AGENT_ID.trim().length > 0
      ? env.OPENCLAW_AGENT_ID.trim()
      : 'main');
  const configuredWorkspace = configWorkspace(config, selectedAgentId);

  let workspace: string;
  let workspaceSource: HostLayout['workspaceSource'];
  const workspacePins: Array<{ name: string; value: string }> = [];
  for (const name of ROUTE_WORKSPACE_ENV) {
    const value = env[name];
    if (typeof value === 'string' && value.trim().length > 0) {
      workspacePins.push({ name, value: value.trim() });
    }
  }
  if (workspacePins.length > 1) {
    const a = resolve(expandHome(workspacePins[0].value.trim(), home));
    const b = resolve(expandHome(workspacePins[1].value.trim(), home));
    if (a !== b) {
      throw new RouteDiscoveryError(
        'ROUTE_HOST_CONFIG_INVALID',
        `OPENCLAW_WORKSPACE_PATH and OPENCLAW_WORKSPACE_ROOT conflict (${a} versus ${b}). Discovery will not choose one.`,
        [a, b],
      );
    }
  }
  if (workspacePins.length > 0) {
    workspace = resolve(expandHome(workspacePins[0].value.trim(), home));
    workspaceSource = 'env_pin';
    sources.push(`${workspacePins[0].name}=${workspacePins[0].value.trim()}`);
  } else if (configuredWorkspace.workspace) {
    workspace = resolve(expandHome(configuredWorkspace.workspace, home));
    workspaceSource = configuredWorkspace.source ?? 'agents_default';
    sources.push(configPath);
  } else {
    workspace = join(configRoot, 'workspace');
    workspaceSource = 'root_default';
    sources.push('root/workspace');
  }

  // -- state root and extra skills ---------------------------------------
  const stateRoot = configRoot;
  const skillsEnv = firstEnv(env, ROUTE_SKILLS_ENV);
  const extraSkillDirs = collectExtraSkillDirs(config, home);
  const skillCandidates = [
    ...(skillsEnv ? [resolve(expandHome(skillsEnv.value, home))] : []),
    ...(skillsEnv ? [] : [join(configRoot, 'skills')]),
    ...extraSkillDirs,
  ];
  const skillDirs = [...new Set(skillCandidates.filter((p) => isDirectory(p)))];

  const secretsEnvFiles = [
    ...ROUTE_SECRETS_ENV.map((name) => env[name]).filter(
      (value): value is string => typeof value === 'string' && value.trim().length > 0,
    ),
    join(configRoot, 'secrets', '.env'),
    join(configRoot, '.env'),
  ]
    .map((p) => resolve(expandHome(p.trim(), home)))
    .filter((p) => isFile(p));
  const uniqueSecretsEnvFiles = [...new Set(secretsEnvFiles)];

  // -- installed runtime receipts (WER-005, consumed unchanged) ----------
  const installed = resolveInstalledCli({ homeDir: home, env });
  const runtime: HostRuntimeReceipt = installed.ok
    ? {
        installed: true,
        prefix: installed.prefix,
        releaseId: installed.releaseId,
        dataDir: installed.dataDir,
        cliPath: installed.cliPath,
        failureCode: null,
        checked: [
          installed.activeReceiptPath,
          installed.releaseReceiptPath,
          installed.artifactReceiptPath,
        ],
      }
    : {
        installed: false,
        prefix: defaultRuntimePrefix(env, home),
        releaseId: null,
        dataDir: null,
        cliPath: null,
        failureCode: installed.code,
        checked: [...installed.checked],
      };

  const layout: HostLayout = {
    homeDir: home,
    configRoot,
    configRootName: basename(configRoot) || 'openclaw',
    configPath,
    configExists,
    configFormat,
    stateRoot,
    statePaths: {
      agents: join(stateRoot, 'agents'),
      logs: join(stateRoot, 'logs'),
      credentials: join(stateRoot, 'credentials'),
      authProfiles: join(stateRoot, 'agents', selectedAgentId, 'agent', 'auth-profiles.json'),
      secretsEnv: join(stateRoot, 'secrets', '.env'),
      skills: join(stateRoot, 'skills'),
    },
    workspace,
    workspaceSource,
    selectedAgentId,
    skillDirs,
    extraSkillDirs,
    secretsEnvFiles: uniqueSecretsEnvFiles,
    sources: [...new Set(sources)],
    runtime,
  };
  return { layout, config };
}

/**
 * The public layout view. It deliberately carries NO raw configuration
 * object, so a literal apiKey or an `env` block can never be copied out
 * of discovery by accident.
 */
export function discoverHostLayout(options: HostLayoutOptions = {}): HostLayout {
  return resolveHostContext(options).layout;
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Harness config roots (adapter 3)
// ---------------------------------------------------------------------------

interface HarnessRootCandidate {
  rootName: string;
  slug: string;
  executableNames: string[];
}

const HARNESS_ROOTS: HarnessRootCandidate[] = [
  { rootName: '.claude-nine', slug: 'claude-nine', executableNames: ['claude-nine', 'claude'] },
  { rootName: '.claude', slug: 'claude', executableNames: ['claude'] },
];

function hostBindingFor(
  layout: HostLayout,
  configRoot: string,
  workspace: string,
  configProfile: string,
): RouteHostBinding {
  return {
    configRoot,
    stateRoot: layout.stateRoot,
    workspace,
    selectedAgentId: layout.selectedAgentId,
    configProfile,
  };
}

function discoverHarnessRoutes(
  layout: HostLayout,
  env: NodeJS.ProcessEnv,
): DiscoveredRoute[] {
  const routes: DiscoveredRoute[] = [];
  for (const candidate of HARNESS_ROOTS) {
    let configDir = join(layout.homeDir, candidate.rootName);
    // CLAUDE_CONFIG_DIR is the harness's own existing configuration
    // for where its config root lives; honor it for the .claude root.
    if (candidate.rootName === '.claude' && env.CLAUDE_CONFIG_DIR) {
      configDir = env.CLAUDE_CONFIG_DIR;
    }
    if (!isDirectory(configDir)) continue;
    const executable = findExecutable(layout.homeDir, env, candidate.executableNames);
    const detail =
      executable === null
        ? `harness config root ${configDir} exists, but no harness executable (${candidate.executableNames.join(' or ')}) was found in ~/.local/bin or on PATH, so no host-call delegate can be composed`
        : null;
    routes.push({
      routeId: `${candidate.slug}-configured`,
      providerSlug: candidate.slug,
      kind: 'harness',
      identityLevel: 'configured',
      composable: executable !== null,
      notComposableReason: detail,
      failure:
        detail === null
          ? null
          : { code: 'ROUTE_HARNESS_EXECUTABLE_MISSING', detail },
      host: hostBindingFor(
        layout,
        configDir,
        layout.workspace,
        `${basename(configDir) || candidate.slug}:${candidate.slug}`,
      ),
      harness: {
        configDir,
        configRootName: candidate.rootName,
        executable,
      },
    });
  }
  return routes;
}

// ---------------------------------------------------------------------------
// OpenClaw provider configuration (adapter 1)
// ---------------------------------------------------------------------------

function apiFamilyOf(api: string | null): RouteApiFamily {
  if (api === null) return 'other';
  const normalized = api.trim().toLowerCase();
  if (normalized.startsWith('openai')) return 'openai_compatible';
  if (normalized.startsWith('anthropic')) return 'anthropic_messages';
  if (normalized.startsWith('ollama')) return 'ollama_chat';
  return 'other';
}

function modelPrimaryOf(node: Record<string, unknown> | null): string | null {
  if (!node) return null;
  const model = node.model;
  if (typeof model === 'string' && model.trim().length > 0) return model.trim();
  const record = asRecord(model);
  if (record && typeof record.primary === 'string' && record.primary.trim().length > 0) {
    return record.primary.trim();
  }
  return null;
}

function providerModelIds(provider: Record<string, unknown>): string[] {
  if (!Array.isArray(provider.models)) return [];
  const ids: string[] = [];
  for (const raw of provider.models) {
    if (typeof raw === 'string' && raw.trim().length > 0) {
      ids.push(raw.trim());
      continue;
    }
    const record = asRecord(raw);
    if (record && typeof record.id === 'string' && record.id.trim().length > 0) {
      ids.push(record.id.trim());
    }
  }
  return [...new Set(ids)];
}

function modelEntryOf(provider: Record<string, unknown>, modelId: string): Record<string, unknown> | null {
  if (!Array.isArray(provider.models)) return null;
  for (const raw of provider.models) {
    const record = asRecord(raw);
    if (record && record.id === modelId) return record;
  }
  return null;
}

function capabilitySnapshotOf(entry: Record<string, unknown> | null): RouteCapabilitySnapshot {
  const numberOrNull = (value: unknown): number | null =>
    typeof value === 'number' && Number.isFinite(value) ? value : null;
  const supported = entry && Array.isArray(entry.supportedReasoningLevels)
    ? entry.supportedReasoningLevels.filter((v): v is string => typeof v === 'string')
    : null;
  return {
    contextWindowTokens: entry
      ? numberOrNull(entry.contextWindowTokens ?? entry.contextWindow)
      : null,
    maxOutputTokens: entry ? numberOrNull(entry.maxOutputTokens ?? entry.maxTokens) : null,
    capabilities: ['text'],
    supportedReasoningLevels: supported,
  };
}

interface ModelResolution {
  modelId: string | null;
  entry: Record<string, unknown> | null;
  candidates: string[];
  failure: RouteFailure | null;
}

/**
 * Resolve the configuration's OWN model for one provider. A single
 * explicit selection wins; more than one equally valid candidate is
 * ambiguous and is refused, never guessed.
 */
function resolveConfiguredModel(
  providerId: string,
  provider: Record<string, unknown>,
  config: Record<string, unknown>,
): ModelResolution {
  const listed = providerModelIds(provider);
  const agents = asRecord(config.agents);
  const defaults = agents ? asRecord(agents.defaults) : null;
  const allowList = defaults ? asRecord(defaults.models) : null;
  const allowed = allowList
    ? Object.keys(allowList)
        .filter((key) => key.startsWith(`${providerId}/`))
        .map((key) => key.slice(providerId.length + 1))
        .filter((id) => id.length > 0)
    : [];
  const candidates = [...new Set([...listed, ...allowed])];

  const primary = modelPrimaryOf(defaults);
  if (primary !== null) {
    const slash = primary.indexOf('/');
    const colon = primary.indexOf(':');
    if (slash > 0 && primary.slice(0, slash) === providerId) {
      const id = primary.slice(slash + 1).trim();
      if (id.length > 0) {
        return {
          modelId: id,
          entry: modelEntryOf(provider, id),
          candidates,
          failure: null,
        };
      }
      return {
        modelId: null,
        entry: null,
        candidates,
        failure: {
          code: 'ROUTE_MODEL_MISSING',
          detail: `the agent default primary names provider ${providerId} with no model id, and the council never picks one`,
        },
      };
    }
    if (slash < 0 && colon > 0 && primary.slice(0, colon) === providerId) {
      const id = primary.slice(colon + 1).trim();
      if (id.length > 0) {
        return { modelId: id, entry: modelEntryOf(provider, id), candidates, failure: null };
      }
    }
  }

  if (allowed.length === 1) {
    const id = allowed[0];
    return { modelId: id, entry: modelEntryOf(provider, id), candidates, failure: null };
  }
  if (allowed.length > 1) {
    return {
      modelId: null,
      entry: null,
      candidates,
      failure: {
        code: 'ROUTE_MODEL_AMBIGUOUS',
        detail: `the configuration allows ${allowed.length} models for provider ${providerId} (${allowed.join(', ')}) and names no single default primary for it; the council never picks one`,
      },
    };
  }
  if (listed.length === 1) {
    const id = listed[0];
    return { modelId: id, entry: modelEntryOf(provider, id), candidates, failure: null };
  }
  if (listed.length > 1) {
    return {
      modelId: null,
      entry: null,
      candidates,
      failure: {
        code: 'ROUTE_MODEL_AMBIGUOUS',
        detail: `provider ${providerId} lists ${listed.length} models (${listed.join(', ')}) and the configuration names no default primary for it; the council never picks one`,
      },
    };
  }
  return {
    modelId: null,
    entry: null,
    candidates,
    failure: {
      code: 'ROUTE_MODEL_MISSING',
      detail: `the configuration names no model for provider ${providerId} (no default primary, no allowed entry and no listed model), and the council never invents one`,
    },
  };
}

function resolveCredential(
  providerId: string,
  provider: Record<string, unknown>,
  env: NodeJS.ProcessEnv,
  configEnv: Record<string, unknown> | null,
  envFiles: string[],
  baseUrl: string,
): DiscoveredCredential {
  const apiKey = provider.apiKey;
  const reference = parseApiKeyReference(apiKey);
  if (reference) {
    const lookup = lookupSecret(reference.name, env, configEnv, envFiles);
    return {
      state: lookup.found ? 'present' : 'absent',
      envVar: reference.name,
      source: lookup.source,
      reference: reference.reference,
      checked: lookup.checked,
    };
  }
  if (typeof apiKey === 'string' && apiKey.trim().length > 0) {
    return {
      state: 'present',
      envVar: null,
      source: 'openclaw_json',
      reference: null,
      checked: ['openclaw.json:apiKey'],
    };
  }
  const guess = guessedEnvVar(providerId);
  const lookup = lookupSecret(guess, env, configEnv, envFiles);
  if (lookup.found) {
    return {
      state: 'present',
      envVar: guess,
      source: lookup.source,
      reference: null,
      checked: lookup.checked,
    };
  }
  if (isLoopbackBaseUrl(baseUrl)) {
    // A loopback endpoint the client configured on their own machine
    // (for example a local daemon) normally requires no credential;
    // when the daemon does require one, the transport's resolver
    // still runs and the request fails honestly without one.
    return {
      state: 'not_required',
      envVar: guess,
      source: null,
      reference: null,
      checked: lookup.checked,
    };
  }
  return {
    state: 'absent',
    envVar: guess,
    source: null,
    reference: null,
    checked: lookup.checked,
  };
}

function discoverProviderRoutes(
  layout: HostLayout,
  config: Record<string, unknown> | null,
  env: NodeJS.ProcessEnv,
): DiscoveredRoute[] {
  if (!config) return [];
  const providers = asRecord(asRecord(config.models)?.providers);
  if (!providers) return [];
  const configEnv = readConfigEnv(config);
  const routes: DiscoveredRoute[] = [];

  for (const [providerId, rawProvider] of Object.entries(providers)) {
    const provider = asRecord(rawProvider);
    if (!provider) continue;
    const baseUrl = typeof provider.baseUrl === 'string' ? provider.baseUrl.trim() : '';
    const declaredApi = typeof provider.api === 'string' ? provider.api : null;
    const apiFamily = apiFamilyOf(declaredApi);
    const model = resolveConfiguredModel(providerId, provider, config);
    const credential =
      baseUrl.length > 0
        ? resolveCredential(providerId, provider, env, configEnv, layout.secretsEnvFiles, baseUrl)
        : {
            state: 'absent' as const,
            envVar: guessedEnvVar(providerId),
            source: null,
            reference: null,
            checked: ['openclaw.json:baseUrl'],
          };

    const reasons: string[] = [];
    let failure: RouteFailure | null = null;
    if (baseUrl.length === 0) {
      failure = {
        code: 'ROUTE_ENDPOINT_MISSING',
        detail: `provider ${providerId} declares no baseUrl, so no endpoint can be composed; no default endpoint was substituted`,
      };
      reasons.push(failure.detail);
    }
    if (apiFamily !== 'openai_compatible') {
      const detail = `provider ${providerId} declares API family ${JSON.stringify(
        declaredApi,
      )} (${apiFamily}); this runtime composes only an OpenAI-compatible wire protocol here and will not reinterpret another API family as compatible`;
      if (failure === null) failure = { code: 'ROUTE_API_FAMILY_UNSUPPORTED', detail };
      reasons.push(detail);
    }
    if (model.failure) {
      if (failure === null) failure = model.failure;
      reasons.push(model.failure.detail);
    }
    if (credential.state === 'absent') {
      const detail = `no credential is present for provider ${providerId} (reference ${JSON.stringify(
        credential.reference ?? credential.envVar ?? 'unknown',
      )}; stores checked: ${credential.checked.join(', ')})`;
      if (failure === null) failure = { code: 'ROUTE_SECRET_REFERENCE_UNRESOLVED', detail };
      reasons.push(detail);
    }

    routes.push({
      routeId: `${providerId}-configured`,
      providerSlug: providerId,
      kind: apiFamily === 'openai_compatible' ? 'compatible' : 'unsupported',
      identityLevel: 'configured',
      composable: reasons.length === 0,
      notComposableReason: reasons.length > 0 ? reasons.join('; ') : null,
      failure,
      host: hostBindingFor(
        layout,
        layout.configRoot,
        layout.workspace,
        `${layout.configRootName}:${providerId}`,
      ),
      compatible: {
        baseUrl,
        modelId: model.modelId,
        modelCandidates: model.candidates,
        apiFamily,
        credential,
        configPath: layout.configPath,
        configFormat: layout.configFormat,
        envFiles: layout.secretsEnvFiles,
        providerId,
        capabilitySnapshot: capabilitySnapshotOf(model.entry),
      },
    });
  }
  return routes;
}

// ---------------------------------------------------------------------------
// Discovery entry points
// ---------------------------------------------------------------------------

/**
 * Resolve the host layout and every configured route. Throws a typed,
 * secret-free `RouteDiscoveryError` when the host is ambiguous or
 * malformed, because no developer default may stand in for the host's
 * real answer.
 */
export function discoverHostRoutes(options: RouteDiscoveryOptions = {}): DiscoveredHostRoutes {
  const env = options.env ?? process.env;
  const { layout, config } = resolveHostContext(options);
  return {
    layout,
    routes: [
      ...discoverHarnessRoutes(layout, env),
      ...discoverProviderRoutes(layout, config, env),
    ],
  };
}

/**
 * Total, read-only discovery for listing surfaces (`models`, doctor).
 * A route that cannot be composed stays visible with its typed reason. A
 * host-level ambiguity yields no routes here; strict callers use
 * `resolveRouteForDispatch`/`discoverRouteSnapshot`, which throw it.
 */
export function discoverConfiguredRoutes(
  options: RouteDiscoveryOptions = {},
): DiscoveredRoute[] {
  try {
    return discoverHostRoutes(options).routes;
  } catch {
    return [];
  }
}

/**
 * Strict route resolution for dispatch. Every failure is explicit and
 * secret-free: missing config, unknown route id, unsupported API family,
 * ambiguous model, or an unresolved named secret reference.
 */
export function resolveRouteForDispatch(
  routeId: string,
  options: RouteDiscoveryOptions = {},
): ResolvedRoute {
  const { layout, routes } = discoverHostRoutes(options);
  const route = routes.find((candidate) => candidate.routeId === routeId);
  if (!route) {
    if (!layout.configExists) {
      throw new RouteDiscoveryError(
        'ROUTE_HOST_CONFIG_MISSING',
        `No OpenClaw configuration exists at ${layout.configPath}, so no provider route can be resolved. Discovery does not invent a route from a default. Point OPENCLAW_ROOT or OPENCLAW_CONFIG_PATH at the host's real configuration.`,
        [layout.configPath],
      );
    }
    throw new RouteDiscoveryError(
      'ROUTE_ID_UNKNOWN',
      `No configured route ${JSON.stringify(routeId)} exists on this host. Discovered: ${
        routes.map((r) => r.routeId).join(', ') || 'none'
      }. The council does not fall back to another route.`,
      [layout.configPath],
    );
  }
  if (!route.composable && route.failure) {
    throw new RouteDiscoveryError(route.failure.code, `${route.routeId}: ${route.failure.detail}`, [
      layout.configPath,
    ]);
  }
  return { route, layout };
}

// ---------------------------------------------------------------------------
// Frozen route snapshot (WER-006 contract, consumed not reinvented)
// ---------------------------------------------------------------------------

function familyParamStyle(
  family: RouteApiFamily,
): RouteSnapshotReasoning['paramStyle'] {
  if (family === 'openai_compatible') return 'reasoning_effort';
  if (family === 'anthropic_messages') return 'reasoning_object';
  return 'none';
}

function configuredCredential(route: DiscoveredRoute): CredentialPresence {
  if (route.compatible) {
    const { state, envVar, source, checked } = route.compatible.credential;
    return { state, envVar, source, checked: [...checked] };
  }
  return { state: 'not_required', envVar: null, source: null, checked: [] };
}

/**
 * Freeze one discovered route into the published WER-006 contract. The
 * configured model is the configuration's own; transport-reported
 * identity defaults to UNKNOWN/not_probed and is never inferred.
 */
export function buildRouteSnapshot(
  route: DiscoveredRoute,
  options: RouteSnapshotOptions,
): CouncilRouteSnapshot {
  if (!route.composable && route.failure) {
    throw new RouteDiscoveryError(route.failure.code, `${route.routeId}: ${route.failure.detail}`, [
      route.host.configRoot,
    ]);
  }
  const apiFamily: RouteApiFamily = route.compatible?.apiFamily ?? 'other';
  const combination = options.combination ?? null;
  if (combination && combination.members.length === 0) {
    throw new RouteDiscoveryError(
      'ROUTE_MODEL_MISSING',
      `combination ${JSON.stringify(combination.alias)} lists no permitted member; an empty combination is not permission to select any model`,
      [route.host.configRoot],
    );
  }
  const baseReasoning: RouteSnapshotReasoning = {
    requested: null,
    supported: null,
    applied: null,
    limitation: null,
    paramStyle: familyParamStyle(apiFamily),
  };
  const baseLimits: RouteSnapshotLimits = {
    requestsPerMinute: null,
    tokensPerMinute: null,
    maxConcurrency: null,
  };
  const draft: RouteSnapshotDraft = {
    selection: {
      schema: 'wise-elders.route-selection/v1',
      selectionSource: 'client_default',
      routeId: route.routeId,
      routeRevision: options.routeRevision ?? 1,
      routeKind: combination ? 'combination' : 'fixed_model',
      providerSlug: route.providerSlug,
      requestedRoute: route.routeId,
      requestedModelOrAlias: combination
        ? combination.alias
        : (route.compatible?.modelId ?? null),
      combinationMembers: combination ? [...combination.members] : null,
      reasoning: {
        requested: null,
        applied: null,
        supported: null,
        limitation: null,
      },
      fallbackPolicy: 'none',
      providerAccountRef: null,
      capabilitySnapshot: route.compatible?.capabilitySnapshot ?? {
        contextWindowTokens: null,
        maxOutputTokens: null,
        capabilities: ['text'],
        supportedReasoningLevels: null,
      },
      credential: configuredCredential(route),
      identityLevel: 'configured',
      scope: options.scope,
      createdAt: options.createdAt,
    },
    sessionId: options.sessionId,
    sessionOwner: options.sessionOwner,
    host: {
      baseUrl:
        route.compatible?.baseUrl ??
        `harness://${route.providerSlug}`,
      configProfile: route.host.configProfile,
      apiFamily,
    },
    reasoning: { ...baseReasoning, ...options.reasoning },
    capabilityVersion: options.capabilityVersion,
    policySha256: options.policySha256,
    limits: { ...baseLimits, ...options.limits },
    createdAt: options.createdAt,
  };
  if (options.transportReported) {
    draft.transportReported = options.transportReported;
  }
  const snapshot = freezeRouteSnapshot(draft);
  // Discovery reports configured state only. Every unreported member must
  // remain UNKNOWN; assert the frozen contract rather than trusting it.
  if (
    snapshot.identity.configured.providerSlug !== route.providerSlug ||
    snapshot.identity.configured.configProfile !== route.host.configProfile
  ) {
    throw new RouteDiscoveryError(
      'ROUTE_HOST_CONFIG_INVALID',
      'frozen route snapshot does not carry the discovered configured identity',
      [route.host.configRoot],
    );
  }
  for (const member of snapshot.identity.combinationMembers ?? []) {
    if (
      member.reported.state !== 'unknown' ||
      member.reported.modelId !== UNKNOWN_ROUTE_IDENTITY
    ) {
      throw new RouteDiscoveryError(
        'ROUTE_HOST_CONFIG_INVALID',
        `combination member ${member.memberModelId} carries transport-reported identity from discovery; discovery is not a probe`,
        [route.host.configRoot],
      );
    }
  }
  return snapshot;
}

/** Resolve one route strictly and freeze it through the WER-006 path. */
export function discoverRouteSnapshot(
  routeId: string,
  snapshotOptions: RouteSnapshotOptions,
  discoveryOptions: RouteDiscoveryOptions = {},
): { route: DiscoveredRoute; layout: HostLayout; snapshot: CouncilRouteSnapshot } {
  const { route, layout } = resolveRouteForDispatch(routeId, discoveryOptions);
  return { route, layout, snapshot: buildRouteSnapshot(route, snapshotOptions) };
}

// ---------------------------------------------------------------------------
// Flight-time credential resolution
// ---------------------------------------------------------------------------

/**
 * Resolve a discovered compatible route's credential VALUE at flight
 * time, through the existing configuration only: the provider's literal
 * apiKey in the config file it was discovered from, or the named
 * reference through process env, the config's own `env` block, or the
 * host's existing secret env files. The value is returned to the
 * transport for the in-flight Authorization header only; it is never
 * recorded, and no error built here ever carries it.
 */
export function resolveDiscoveredCredential(
  route: DiscoveredRoute,
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const compatible = route.compatible;
  if (!compatible) return null;
  let config: Record<string, unknown> | null = null;
  try {
    const text = readFileSync(compatible.configPath, 'utf8');
    config = parseConfigText(text, compatible.configFormat, compatible.configPath);
  } catch {
    config = null;
  }
  const provider = config
    ? asRecord(asRecord(asRecord(config.models)?.providers)?.[compatible.providerId])
    : null;
  const apiKey = provider?.apiKey;
  const reference = parseApiKeyReference(apiKey);
  const values: string[] = [];
  try {
    if (reference) {
      const lookup = lookupSecret(
        reference.name,
        env,
        config ? readConfigEnv(config) : null,
        compatible.envFiles,
      );
      if (lookup.value !== null) values.push(lookup.value);
      return lookup.value;
    }
    if (typeof apiKey === 'string' && apiKey.trim().length > 0) {
      values.push(apiKey);
      return apiKey;
    }
    if (compatible.credential.envVar) {
      const lookup = lookupSecret(
        compatible.credential.envVar,
        env,
        config ? readConfigEnv(config) : null,
        compatible.envFiles,
      );
      if (lookup.value !== null) values.push(lookup.value);
      return lookup.value;
    }
    return null;
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw new RouteDiscoveryError(
      'ROUTE_SECRET_REFERENCE_UNRESOLVED',
      scrubSecretValues(
        `the credential reference for provider ${compatible.providerId} could not be resolved from the host's existing stores: ${reason}`,
        values,
      ),
      compatible.credential.checked,
    );
  }
}
