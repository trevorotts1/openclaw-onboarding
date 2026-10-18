/**
 * Claude-Nine host bridge (CWE-010; directive Sections 13, 14, 25).
 *
 * Composes the portable council core under the Claude-Nine host (the
 * 999 / Claude Code harness): the same CWE-004 host ports, the same
 * shared local store and data profile, and a guarded transport per
 * selected route (host-bridge.ts).
 *
 * Harness isolation is structural here. The 999 side resolves routes
 * inside the Claude Code harness through its own native mechanisms (its
 * own skills and vendored modules under parity), never by borrowing the
 * other host's tree at runtime: the same operator commonly has both
 * installs, and a cross-repo dependency is a cross-HARNESS problem. This
 * module therefore imports nothing from the other bridge and nothing
 * from any other host's tree; the isolation test walks the import graph
 * and fails if that ever changes. The only shared code is the
 * harness-neutral bridge machinery in host-bridge.ts, which contains no
 * host-specific resolution logic at all.
 *
 * Config roots (Section 25.2): both Mac Claude config roots
 * (~/.claude and ~/.claude-nine) use the SAME council data profile. The
 * bridge records which root it was composed for, and the data directory
 * still resolves through the one shared profile in paths.ts; no
 * duplicate history is created per skill root.
 *
 * Expired host OAuth (T035): the bridge never scrapes OAuth tokens or
 * cookies and never manufactures unsupported API access from a
 * subscription (Section 13.4 adapter 3). An expired host credential
 * surfaces through the host's supported renewal flow; until it renews,
 * requests fail through the normal transport error path.
 */

import type { TransportRequest } from '../cli/host-ports.js';
import type { LocalHost } from '../cli/local-host.js';
import {
  composeBridgeHost,
  type BridgeHostOptions,
  type BridgeInstance,
  type CouncilRouteSelection,
  type HostResolutionAttempt,
  type RouteCatalogEntry,
} from './host-bridge.js';

// ---------------------------------------------------------------------------
// The Claude-Nine native resolver port. Resolution happens inside the
// Claude Code harness: the harness's own skills and vendored modules
// report what they resolved for a council request, and the shared guard
// decides whether that resolution may stand. A 9Router combination
// selected by the client stays a combination: the harness may expose
// which configured member served the request (viaCombinationMember), or
// hide it, in which case the bridge states the hidden-identity sentence
// and invents nothing.
// ---------------------------------------------------------------------------

export interface ClaudeNineResolutionReport {
  /** Model the harness used or tried to use, when exposed. */
  attemptedModelId: string | null;
  /** Structured transport/provider-reported identity, when exposed. */
  reportedModelId?: string | null;
  /** Identity claimed in model prose. Recorded as ignored, never used. */
  proseClaimedModelId?: string | null;
  /** Client approval for a fallback change, when one exists. */
  approval?: HostResolutionAttempt['approval'];
  /** True when attemptedModelId is a resolved combination member. */
  viaCombinationMember?: boolean;
}

export interface ClaudeNineNativeResolver {
  reportResolution(
    selection: CouncilRouteSelection,
    request: TransportRequest,
  ): ClaudeNineResolutionReport | Promise<ClaudeNineResolutionReport>;
}

export function claudeNineAttemptFromReport(
  report: ClaudeNineResolutionReport,
): HostResolutionAttempt {
  return {
    source: report.viaCombinationMember ? 'combination_member' : 'explicit_route',
    attemptedModelId: report.attemptedModelId,
    reportedModelId: report.reportedModelId ?? null,
    proseClaimedModelId: report.proseClaimedModelId ?? null,
    approval: report.approval ?? null,
  };
}

/**
 * The pinned-route native resolver: the harness runs the selected route
 * exactly as selected. For a combination, the harness hides the member
 * by default (attemptedModelId null), which the guard accepts with the
 * hidden-identity statement rather than inventing a member. Wiring the
 * live 999-native probe belongs to the bundle packaging (CWE-040)
 * behind this same port.
 */
export class PinnedClaudeNineResolver implements ClaudeNineNativeResolver {
  reportResolution(
    selection: CouncilRouteSelection,
  ): ClaudeNineResolutionReport {
    if (selection.routeKind === 'combination') {
      return { attemptedModelId: null, reportedModelId: null };
    }
    return {
      attemptedModelId: selection.requestedModelOrAlias,
      reportedModelId: null,
    };
  }
}

// ---------------------------------------------------------------------------
// The bridge factory. Bindings supplied by the caller carry delegates
// only; the resolution guard is wired here from the bridge's native
// resolver, so no caller can register an unguarded transport for a
// council route through this bridge.
// ---------------------------------------------------------------------------

export type ClaudeNineConfigRoot = '.claude' | '.claude-nine';

export interface ClaudeNineBridgeOptions extends BridgeHostOptions {
  resolver?: ClaudeNineNativeResolver;
  /** Which harness config root this bridge instance serves. */
  configRoot?: ClaudeNineConfigRoot;
}

export interface ClaudeNineBridgeInstance extends BridgeInstance {
  configRoot: ClaudeNineConfigRoot;
}

export function createClaudeNineBridge(
  options: ClaudeNineBridgeOptions = {},
): ClaudeNineBridgeInstance {
  const resolver = options.resolver ?? new PinnedClaudeNineResolver();
  const bindings = (options.bindings ?? []).map((binding) => ({
    ...binding,
    reportAttempt: async (
      selection: CouncilRouteSelection,
      request: TransportRequest,
    ) =>
      claudeNineAttemptFromReport(
        await resolver.reportResolution(selection, request),
      ),
  }));
  const instance = composeBridgeHost('claude-nine', { ...options, bindings });
  return { ...instance, configRoot: options.configRoot ?? '.claude-nine' };
}

/**
 * The Claude-Nine host view handed to the CLI dispatcher (WER-005).
 *
 * `runCli`'s `createHost` port is the CWE-004 `LocalHost` shape. Returning
 * only `{ host, dataDir, store }` silently dropped `routeDiscovery`, so
 * `models` and `doctor` lost every discovered-route diagnostic once the
 * bridge wrapper sat in front of the canonical CLI. This view is the same
 * local host the bridge composed, plus the bridge's own route catalog: no
 * field is re-derived here, so the wrapper reports exactly what the
 * canonical CLI reports for the same input.
 */
export interface ClaudeNineLocalHostView extends LocalHost {
  catalog: RouteCatalogEntry[];
  bridge: ClaudeNineBridgeInstance;
}

export function composeClaudeNineLocalHost(
  options: ClaudeNineBridgeOptions = {},
): ClaudeNineLocalHostView {
  const bridge = createClaudeNineBridge(options);
  return {
    host: bridge.host,
    dataDir: bridge.dataDir,
    store: bridge.store,
    routeDiscovery: bridge.routeDiscovery,
    catalog: bridge.catalog,
    bridge,
  };
}

// ---------------------------------------------------------------------------
// The generated host wrapper source for the 999 portable bundle
// (directive Section 34 CWE-010 owned path: "999: generated host
// wrapper"). CWE-040's bundler emits this file into the bundle beside
// the vendored runtime; it is the bundle's only bridge entry point. It
// composes the Claude-Nine bridge with the bundle's native resolver and
// hands the resulting host to the same blackceo-council dispatcher the
// other host uses, so the CLI behaves identically under both harnesses.
// It imports nothing from any other host's tree.
// ---------------------------------------------------------------------------

export const CLAUDE_NINE_WRAPPER_FILE_NAME = 'claude-nine-host-wrapper.mjs';

export function renderClaudeNineWrapper(): string {
  return [
    '// GENERATED by the Skill 77 portable bundler (CWE-040) from the',
    '// CWE-010 wrapper template. Do not edit in the bundle; edit',
    '// runtime/src/bridges/claude-nine.ts in the canonical package.',
    "import { createClaudeNineBridge, composeClaudeNineLocalHost } from './bridges/claude-nine.js';",
    "import { runCli } from './cli/dispatcher.js';",
    '',
    '/**',
    ' * Compose the council host for the Claude-Nine (999 / Claude Code)',
    ' * harness and run the blackceo-council dispatcher against it.',
    ' * nativeResolver is supplied by the bundle: it resolves routes',
    ' * through the harness-native skills and vendored modules only.',
    ' *',
    ' * The view is the canonical LocalHost shape, including routeDiscovery',
    ' * and the bridge route catalog, so `models`/`doctor` diagnostics are',
    ' * never swallowed by this wrapper.',
    ' */',
    'export function createClaudeNineHost(options = {}, nativeResolver) {',
    '  return composeClaudeNineLocalHost({',
    '    ...options,',
    '    resolver: nativeResolver ?? options.resolver,',
    "    configRoot: '.claude-nine',",
    '  });',
    '}',
    '',
    'export async function main(argv, nativeResolver, io) {',
    '  return runCli(argv, io, {',
    '    createHost: (opts) =>',
    '      createClaudeNineHost(opts, nativeResolver),',
    '  });',
    '}',
    '',
  ].join('\n');
}
