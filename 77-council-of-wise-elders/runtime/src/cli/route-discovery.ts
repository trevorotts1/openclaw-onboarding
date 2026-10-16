/**
 * Read-only discovery of the client's EXISTING configured routes
 * (RP-046-1 repair for DEFECT-046-A; directive Sections 13.4, 25.2
 * step 7, 25.6).
 *
 * The standalone composition binds to the route configuration the
 * client already has on this machine. Discovery reads that
 * configuration; it never writes it, never creates a parallel config
 * format, never registers a new surface, and never copies a credential
 * value anywhere (credential state is recorded as presence only, and a
 * value is resolved at flight time through the resolver the local host
 * composes, Section 13.7).
 *
 * Two existing configuration families are discovered:
 *
 * 1. Harness config roots (Section 13.4 adapter 3): a Claude Code /
 *    Claude-Nine config root that exists on this machine
 *    (~/.claude-nine, ~/.claude, or the directory CLAUDE_CONFIG_DIR
 *    names for the .claude root) is a configured harness route. The
 *    route id is `<slug>-configured`, exactly the id a session spec
 *    pins for that harness (the CWE-046 canary pinned
 *    `claude-nine-configured`). The route composes only when the
 *    harness executable the configuration implies is actually found
 *    (the root's ~/.local/bin launcher first, then PATH): the harness
 *    itself owns routing, model choice, and credentials inside its
 *    own configuration, and the council prescribes no model to it.
 *
 * 2. OpenClaw provider configuration (Section 13.4 adapter 1):
 *    ~/.openclaw/openclaw.json `models.providers` entries that name
 *    an OpenAI-compatible base URL are configured compatible-endpoint
 *    routes, one per provider, route id `<provider>-configured`. The
 *    wire model is the configuration's OWN model for that provider:
 *    the agents default primary when it names this provider, else the
 *    provider's single listed model. When the configuration names no
 *    unambiguous model, or no credential is present for a non-loopback
 *    endpoint, the route is discovered but NOT composed: nothing is
 *    guessed, substituted, or invented.
 *
 * A discovered route that cannot be composed stays visible (models
 * lists it with its reason) and dispatch on it keeps refusing with
 * COUNCIL_ROUTE_UNAVAILABLE, exactly as an unconfigured route does.
 * Identity level for every discovered route is `configured`
 * (Section 13.4): discovery is not a probe, and nothing here claims
 * transport_probed or any stronger level.
 */

import { existsSync, readFileSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, join } from 'node:path';

export type DiscoveredRouteKind = 'harness' | 'compatible';

/** Presence-only credential record (Section 13.7): names, never values. */
export interface DiscoveredCredential {
  state: 'present' | 'absent' | 'not_required';
  envVar: string | null;
  source: 'process.env' | 'openclaw_json' | null;
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
    credential: DiscoveredCredential;
    /** The existing config file the credential resolver re-reads at flight time. */
    configPath: string;
    providerId: string;
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

export interface RouteDiscoveryOptions {
  /** Home directory to discover under. Default: the OS home directory. */
  homeDir?: string;
  /** Environment for PATH, CLAUDE_CONFIG_DIR, and credential presence. Default: process.env. */
  env?: NodeJS.ProcessEnv;
}

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

function readJsonFile(path: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
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

function discoverHarnessRoutes(
  home: string,
  env: NodeJS.ProcessEnv,
): DiscoveredRoute[] {
  const routes: DiscoveredRoute[] = [];
  for (const candidate of HARNESS_ROOTS) {
    let configDir = join(home, candidate.rootName);
    // CLAUDE_CONFIG_DIR is the harness's own existing configuration
    // for where its config root lives; honor it for the .claude root.
    if (candidate.rootName === '.claude' && env.CLAUDE_CONFIG_DIR) {
      configDir = env.CLAUDE_CONFIG_DIR;
    }
    if (!isDirectory(configDir)) continue;
    const executable = findExecutable(home, env, candidate.executableNames);
    routes.push({
      routeId: `${candidate.slug}-configured`,
      providerSlug: candidate.slug,
      kind: 'harness',
      identityLevel: 'configured',
      composable: executable !== null,
      notComposableReason:
        executable === null
          ? `harness config root ${configDir} exists, but no harness executable (${candidate.executableNames.join(' or ')}) was found in ~/.local/bin or on PATH, so no host-call delegate can be composed`
          : null,
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

function discoverOpenClawRoutes(
  home: string,
  env: NodeJS.ProcessEnv,
): DiscoveredRoute[] {
  const configPath = join(home, '.openclaw', 'openclaw.json');
  if (!existsSync(configPath)) return [];
  const config = readJsonFile(configPath);
  if (!config) return [];
  const providers = asRecord(asRecord(config.models)?.providers);
  if (!providers) return [];

  // The configuration's own default model, "provider/model" form.
  const agents = asRecord(config.agents);
  const defaults = asRecord(agents?.defaults);
  const modelField = asRecord(defaults?.model);
  const primary =
    typeof modelField?.primary === 'string'
      ? (modelField.primary as string)
      : typeof defaults?.model === 'string'
        ? (defaults.model as string)
        : null;

  const routes: DiscoveredRoute[] = [];
  for (const [providerId, rawProvider] of Object.entries(providers)) {
    const provider = asRecord(rawProvider);
    if (!provider) continue;
    const baseUrl = typeof provider.baseUrl === 'string' ? provider.baseUrl : null;
    if (!baseUrl) continue;
    // Only endpoints the configuration itself declares
    // OpenAI-compatible belong to adapter 1. Other API families are
    // not silently reinterpreted as compatible endpoints.
    const api = typeof provider.api === 'string' ? provider.api : null;
    if (api !== null && !/openai/i.test(api)) continue;

    let modelId: string | null = null;
    if (primary !== null && primary.startsWith(`${providerId}/`)) {
      modelId = primary.slice(providerId.length + 1);
    } else if (Array.isArray(provider.models) && provider.models.length === 1) {
      const only = asRecord(provider.models[0]);
      if (only && typeof only.id === 'string') modelId = only.id;
    }

    const envVarGuess = `${providerId.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase()}_API_KEY`;
    let credential: DiscoveredCredential;
    const apiKey = typeof provider.apiKey === 'string' ? provider.apiKey : null;
    if (apiKey !== null && apiKey.length > 0 && !apiKey.startsWith('${')) {
      credential = { state: 'present', envVar: null, source: 'openclaw_json' };
    } else if (apiKey !== null && apiKey.startsWith('${') && apiKey.endsWith('}')) {
      const named = apiKey.slice(2, -1);
      credential = {
        state: env[named] ? 'present' : 'absent',
        envVar: named,
        source: 'process.env',
      };
    } else if (env[envVarGuess]) {
      credential = { state: 'present', envVar: envVarGuess, source: 'process.env' };
    } else if (isLoopbackBaseUrl(baseUrl)) {
      // A loopback endpoint the client configured on their own machine
      // (for example a local daemon) normally requires no credential;
      // when the daemon does require one, the transport's resolver
      // still runs and the request fails honestly without one.
      credential = { state: 'not_required', envVar: envVarGuess, source: null };
    } else {
      credential = { state: 'absent', envVar: envVarGuess, source: 'process.env' };
    }

    const reasons: string[] = [];
    if (modelId === null) {
      reasons.push(
        'the configuration names no unambiguous model for this provider (no agents default primary for it and not exactly one listed model), and the council never picks one',
      );
    }
    if (credential.state === 'absent') {
      reasons.push(
        `no credential is present for this provider (checked the config file and ${credential.envVar ?? 'the environment'})`,
      );
    }
    routes.push({
      routeId: `${providerId}-configured`,
      providerSlug: providerId,
      kind: 'compatible',
      identityLevel: 'configured',
      composable: reasons.length === 0,
      notComposableReason: reasons.length > 0 ? reasons.join('; ') : null,
      compatible: { baseUrl, modelId, credential, configPath, providerId },
    });
  }
  return routes;
}

// ---------------------------------------------------------------------------
// Discovery entry point. Read-only and total: any unreadable or
// malformed configuration yields fewer routes, never an exception and
// never an invented route.
// ---------------------------------------------------------------------------

export function discoverConfiguredRoutes(
  options: RouteDiscoveryOptions = {},
): DiscoveredRoute[] {
  const home = options.homeDir ?? homedir();
  const env = options.env ?? process.env;
  return [
    ...discoverHarnessRoutes(home, env),
    ...discoverOpenClawRoutes(home, env),
  ];
}

/**
 * Resolve a discovered compatible route's credential VALUE at flight
 * time, through the existing configuration only: the provider's apiKey
 * in the config file it was discovered from, or the named environment
 * variable. The value is returned to the transport for the in-flight
 * Authorization header only; it is never recorded (Section 13.7).
 */
export function resolveDiscoveredCredential(
  route: DiscoveredRoute,
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const compatible = route.compatible;
  if (!compatible) return null;
  const { credential } = compatible;
  if (credential.source === 'openclaw_json') {
    const config = readJsonFile(compatible.configPath);
    const providers = asRecord(asRecord(config?.models)?.providers);
    const provider = asRecord(providers?.[compatible.providerId]);
    const apiKey = provider && typeof provider.apiKey === 'string' ? provider.apiKey : null;
    return apiKey !== null && apiKey.length > 0 && !apiKey.startsWith('${') ? apiKey : null;
  }
  if (credential.envVar) {
    return env[credential.envVar] ?? null;
  }
  return null;
}
