/**
 * blackceo-council CLI dispatcher (CWE-004; CWE-050 composition).
 *
 * Argument arrays only: no shell strings. Every command prints either
 * clean JSON (--json) or a short human summary, and failures are
 * stable typed envelopes (Section 17.3) with nonzero exit codes. The
 * dispatcher is a thin shell over the engine and the injected host;
 * importing it has no side effects.
 *
 * Composed surface (CWE-050): the authorization commands delegate to
 * CWE-049's handleAuthorizationCommand (preview, approve, status,
 * revoke) with controlling-terminal confirmation wired here; export
 * runs through CWE-038's validated ReportExportService (PDF stays
 * registered not ready by that service, naming CWE-044's renderer).
 * Live route probes remain FEATURE_NOT_READY naming CWE-009/CWE-010
 * with CWE-049: no live transport is composed in the standalone host.
 */

import {
  closeSync,
  existsSync,
  openSync,
  readFileSync,
  readSync,
  writeFileSync,
  writeSync,
} from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  CONTRACT_PACKAGE_VERSION,
  DEFAULT_COUNCIL_SETTINGS,
  canonicalHash,
  type DecisionBrief,
  type RunGrant,
  type SessionSpec,
  type Verdict,
} from '../contracts/index.js';
import { CouncilEngine } from './engine.js';
import {
  CouncilError,
  featureNotReady,
  invalidInput,
  isCouncilError,
  usageError,
} from './errors.js';
import { buildSampleSession, DeterministicFixtureTransport } from './fixture-transport.js';
import type { CouncilHost } from './host-ports.js';
import { createLocalHost, localScope, type LocalHost } from './local-host.js';
import {
  createStandaloneRunAuthorization,
  handleAuthorizationCommand,
  mirrorSession,
} from './authorization.js';
import { exportVerdictReport } from './report-export.js';
import { resolveDataDir } from './paths.js';

export interface CliIo {
  out(text: string): void;
  err(text: string): void;
}

const defaultIo: CliIo = {
  out: (text) => process.stdout.write(text),
  err: (text) => process.stderr.write(text),
};

export interface CliDeps {
  createHost?: (options: { dataDir?: string; skillRoot?: string }) => LocalHost;
}

/**
 * The skill folder that contains this runtime (state must stay outside it).
 *
 * CWE-045 (finding F-4): the fixed three-level climb was written for
 * the src/cli and dist/cli layouts, but the bundled CLI ships as ONE
 * file at dist/blackceo-council.mjs, one level shallower, so the
 * climb landed on the skill folder's PARENT and resolveDataDir's
 * refusal became a fail-closed superset (it refused data directories
 * anywhere in the parent folder, including siblings of the skill).
 * The resolution now walks up from the module directory to the first
 * ancestor carrying the skill folder's signature (a SKILL.md beside
 * a runtime/ directory), which is exact in every shipped layout:
 * runtime/src/cli, runtime/dist/cli, and the bundled
 * runtime/dist/blackceo-council.mjs. When no signature is found
 * (an exotic embedding), the historical three-level climb is kept
 * as the fallback rather than guessing a different boundary.
 */
export function skillRootFromModule(): string {
  const here = dirname(fileURLToPath(import.meta.url));
  let dir = here;
  for (let depth = 0; depth < 8; depth += 1) {
    if (existsSync(join(dir, 'SKILL.md')) && existsSync(join(dir, 'runtime'))) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // src/cli or dist/cli -> cli -> src|dist -> runtime -> skill folder.
  return resolve(here, '..', '..', '..');
}

interface ParsedArgs {
  positionals: string[];
  flags: Map<string, string | true>;
}

function parseArgs(argv: string[]): ParsedArgs {
  const positionals: string[] = [];
  const flags = new Map<string, string | true>();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const name = arg.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith('--')) {
        flags.set(name, next);
        i += 1;
      } else {
        flags.set(name, true);
      }
    } else {
      positionals.push(arg);
    }
  }
  return { positionals, flags };
}

function flagString(flags: Map<string, string | true>, name: string): string | null {
  const value = flags.get(name);
  return typeof value === 'string' ? value : null;
}

/**
 * Controlling-terminal confirmation for interactive approval
 * (Section 25.6): the preview text and the owner's answer travel over
 * /dev/tty, NEVER stdin, so piped input and --json stdout stay clean.
 * Returns undefined when no controlling terminal exists (headless):
 * approval then requires a standing grant, exactly as CWE-049's
 * handler prescribes.
 */
function terminalConfirmPreview():
  | ((previewText: string) => Promise<boolean>)
  | undefined {
  let inFd: number;
  let outFd: number;
  try {
    outFd = openSync('/dev/tty', 'w');
    inFd = openSync('/dev/tty', 'r');
  } catch {
    return undefined;
  }
  return async (previewText: string) => {
    try {
      writeSync(outFd, `${previewText}\nType "yes" to approve this exact envelope: `);
      const buffer = Buffer.alloc(256);
      let line = '';
      for (;;) {
        const read = readSync(inFd, buffer, 0, buffer.length, null);
        if (read === 0) break;
        line += buffer.subarray(0, read).toString('utf8');
        if (line.includes('\n')) break;
      }
      return /^y(es)?$/i.test(line.trim());
    } catch {
      return false;
    } finally {
      try {
        closeSync(inFd);
        closeSync(outFd);
      } catch {
        // The CLI process is exiting anyway; a close failure is moot.
      }
    }
  };
}

function printResult(io: CliIo, json: boolean, human: string, data: unknown): void {
  io.out(json ? `${JSON.stringify(data, null, 2)}\n` : `${human}\n`);
}

function verdictHuman(verdict: Verdict, sample: boolean): string {
  const lines: string[] = [];
  if (sample) lines.push('SAMPLE SESSION (synthetic fixture data, not a real council run)');
  if (verdict.result_kind === 'consult') {
    lines.push(`Consult result for session ${verdict.session_id}`);
    lines.push(`Next step: ${verdict.next_step}`);
    lines.push(`Validation: ${verdict.validation_status}`);
    return lines.join('\n');
  }
  lines.push(`Verdict for session ${verdict.session_id}: ${verdict.label}`);
  lines.push(
    verdict.recommended_option_id
      ? `Recommended option: ${verdict.recommended_option_id}`
      : 'Recommended option: none (the evidence does not support a recommendation)',
  );
  for (const score of verdict.option_scores) {
    lines.push(
      `  Option ${score.option_id}: ${score.display_score === null ? 'no score' : score.display_score.toFixed(1)} (coverage ${score.coverage.toFixed(2)})`,
    );
  }
  if (verdict.main_reasons.length > 0) {
    lines.push(`Main reasons: ${verdict.main_reasons.join(' | ')}`);
  }
  if (verdict.strongest_dissent) {
    lines.push(`Strongest dissent: ${verdict.strongest_dissent}`);
  }
  if (verdict.prerequisites.length > 0) {
    lines.push(`Prerequisites: ${verdict.prerequisites.join(' | ')}`);
  }
  lines.push(`Ratification: ${verdict.ratification_status}`);
  return lines.join('\n');
}

/** A grant that exists only for the labeled sample path. */
function sampleGrant(host: CouncilHost): RunGrant {
  return {
    schema_version: 'wise-elders.run-grant/v1',
    grant_id: 'grant-sample-fixture',
    authority_mode: 'local_interactive_owner',
    issuer_principal: 'local-owner',
    scope: {
      tenant_id: 'sample-tenant',
      company_id: 'sample-company',
      installation_id: 'sample-installation',
      owner_subject: null,
    },
    purpose: 'council_run',
    session_id: 'sess-fixture-1',
    brief_revision: 1,
    brief_sha256: '',
    mode: 'full',
    seat_ids: [],
    route_policy_sha256: canonicalHash({ policy: 'sample-fixture-route' }),
    account_ref: null,
    pack_version: 'pack-fixture-1.0.0',
    protocol_version: CONTRACT_PACKAGE_VERSION,
    allowed_operation_kinds: ['provider_request'],
    ceilings: {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    },
    created_at: '2026-01-01T00:00:00Z',
    expires_at: '2099-01-01T00:00:00Z',
    revocation_epoch: 0,
    status: 'active',
    standing_parent_grant_id: null,
    preview_sha256: canonicalHash({ preview: 'sample-fixture' }),
    consumed: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
    reserved: { provider_requests: 0, output_repairs: 0, transport_retries: 0 },
  };
}

const USAGE = [
  'blackceo-council: Council of Wise Elders portable core (foundation build)',
  '',
  'Commands:',
  '  doctor [--json]                     Offline readiness checks (no paid work)',
  '  models [--json]                     Composed routes and model policy notes',
  '  probe                               Live route probe (not ready in this build)',
  '  create --spec FILE --brief FILE     Create a session from frozen spec and brief JSON',
  '  create --sample                     Create the labeled synthetic sample session',
  '  sample run [--json]                 Run the labeled sample end to end (fixture transport, spends nothing)',
  '  start SESSION --grant-ref REF       Start a session under a resolved run grant',
  '  resume SESSION --grant-ref REF      Resume a paused or blocked session',
  '  status SESSION [--json]             Session state summary',
  '  pause SESSION                       Pause an active session',
  '  cancel SESSION                      Cancel a session (late results are fenced out)',
  '  verdict SESSION [--json]           The validated verdict, when one exists',
  '  replay SESSION [--json]             Committed event history (read only, spends nothing)',
  '  export SESSION --format md|json|pdf [--out FILE]',
  '  authorization preview|approve|status|revoke   Run authorization service (CWE-049)',
  '',
  'Global flags: --json, --data-dir DIR (default: per-user council data directory)',
].join('\n');

export async function runCli(
  argv: string[],
  io: CliIo = defaultIo,
  deps: CliDeps = {},
): Promise<number> {
  const json = argv.includes('--json');
  try {
    const { positionals, flags } = parseArgs(argv);
    const [command, sub, third] = positionals;
    const dataDir = flagString(flags, 'data-dir') ?? undefined;
    const skillRoot = skillRootFromModule();
    const makeHost =
      deps.createHost ?? ((opts) => createLocalHost({ ...opts, skillRoot }));
    const hostFor = (): LocalHost => makeHost({ dataDir, skillRoot });
    const engineFor = (host: CouncilHost) => new CouncilEngine(host);

    if (command === undefined) {
      io.out(`${USAGE}\n`);
      return 0;
    }

    switch (command) {
      case 'doctor': {
        const checks: Array<{ name: string; ok: boolean; detail: string }> = [];
        checks.push({
          name: 'node_sqlite',
          ok: (() => {
            try {
              createRequire(import.meta.url)('node:sqlite');
              return true;
            } catch {
              return false;
            }
          })(),
          detail: 'node:sqlite module availability for the standalone store',
        });
        let dir: string | null = null;
        try {
          dir = resolveDataDir({ override: dataDir ?? null, skillRoot });
          checks.push({
            name: 'data_dir_outside_skill_tree',
            ok: true,
            detail: dir,
          });
        } catch (err) {
          checks.push({
            name: 'data_dir_outside_skill_tree',
            ok: false,
            detail: err instanceof Error ? err.message : String(err),
          });
        }
        let routes: string[] = [];
        let uncomposed: string[] = [];
        let storeOk = false;
        if (dir) {
          const local = hostFor();
          routes = local.host.transportRegistry.listRoutes();
          uncomposed = (local.routeDiscovery ?? [])
            .filter((r) => !r.composed)
            .map((r) => r.route_id);
          storeOk = true;
        }
        checks.push({
          name: 'local_store',
          ok: storeOk,
          detail: storeOk ? 'SQLite store opened in the data directory' : 'store did not open',
        });
        checks.push({
          name: 'live_routes_composed',
          ok: routes.length > 0,
          detail:
            routes.length > 0
              ? `routes: ${routes.join(', ')}`
              : uncomposed.length > 0
                ? `configured routes were discovered but none could be composed (${uncomposed.join(', ')}); see models for the per-route reason. Runs on uncomposed routes refuse with COUNCIL_ROUTE_UNAVAILABLE`
                : 'no configured route was discovered on this machine, so no live transport is composed; runs on uncomposed routes refuse with COUNCIL_ROUTE_UNAVAILABLE',
        });
        checks.push({
          name: 'run_authorization_service',
          ok: true,
          detail:
            'grant service composed (CWE-049, composed by CWE-050): authorization preview/approve/status/revoke are live and session starts resolve grants through the authorization store',
        });
        const data = {
          ok: checks.every((c) => c.ok || c.name === 'live_routes_composed' || c.name === 'run_authorization_service'),
          contracts: CONTRACT_PACKAGE_VERSION,
          data_dir: dir,
          settings: {
            max_session_provider_requests: DEFAULT_COUNCIL_SETTINGS.max_session_provider_requests,
            operation_lease_ttl_seconds: 60,
            operation_lease_heartbeat_seconds: 15,
          },
          checks,
        };
        printResult(
          io,
          json,
          [
            `Council core doctor (offline, no paid work)`,
            `Contracts: ${CONTRACT_PACKAGE_VERSION}`,
            `Data directory: ${dir ?? 'unresolved'}`,
            ...checks.map((c) => `  [${c.ok ? 'ok' : 'not ready'}] ${c.name}: ${c.detail}`),
          ].join('\n'),
          data,
        );
        return data.ok ? 0 : 3;
      }

      case 'models': {
        const local = hostFor();
        const routes = local.host.transportRegistry.listRoutes();
        const discovered = local.routeDiscovery ?? [];
        const data = {
          routes,
          discovered,
          note: 'The client selects the model, or the client configured default applies. This core never prescribes a specific named model and never falls back silently.',
        };
        const discoveredLines = discovered.map(
          (r) =>
            `  ${r.route_id} (${r.provider_slug}, ${r.kind}, identity level ${r.identity_level}): ${
              r.composed ? 'transport composed' : `not composed: ${r.not_composed_reason ?? 'reason not recorded'}`
            }`,
        );
        printResult(
          io,
          json,
          [
            routes.length > 0
              ? `Composed routes: ${routes.join(', ')}`
              : 'No live routes are composed on this machine.',
            ...(discoveredLines.length > 0
              ? ['Discovered configured routes:', ...discoveredLines]
              : []),
            data.note,
          ].join('\n'),
          data,
        );
        return 0;
      }

      case 'probe': {
        throw featureNotReady(
          'Live route probing',
          'CWE-009, CWE-010, and CWE-049',
        );
      }

      case 'authorization': {
        // CWE-050 composition (CWE-049 build report, standalone list
        // item 1): delegate to CWE-049's handler over the standalone
        // authorization store in the resolved data directory.
        // Confirmation is wired to the controlling terminal, never
        // stdin; in --json mode results stay on stdout and the
        // confirmation still uses the terminal.
        const dir = resolveDataDir({ override: dataDir ?? null, skillRoot });
        await handleAuthorizationCommand(sub, positionals.slice(2), flags, {
          dataDir: dir,
          json,
          io,
          confirmPreview: terminalConfirmPreview(),
        });
        return 0;
      }

      case 'create': {
        const { host } = hostFor();
        const engine = engineFor(host);
        if (flags.has('sample')) {
          const sample = buildSampleSession();
          const created = await engine.createSession({ ...sample, sample: true });
          printResult(
            io,
            json,
            `SAMPLE session created: ${created.spec.session_id} (mode ${created.spec.mode}, state ${created.state.state}). Synthetic fixture data only.`,
            {
              ok: true,
              session_id: created.spec.session_id,
              mode: created.spec.mode,
              state: created.state.state,
              sample: true,
            },
          );
          return 0;
        }
        const specPath = flagString(flags, 'spec');
        const briefPath = flagString(flags, 'brief');
        if (!specPath || !briefPath) {
          throw usageError('create requires --spec FILE and --brief FILE (or --sample).');
        }
        let spec: SessionSpec;
        let brief: DecisionBrief;
        try {
          spec = JSON.parse(readFileSync(specPath, 'utf8')) as SessionSpec;
          brief = JSON.parse(readFileSync(briefPath, 'utf8')) as DecisionBrief;
        } catch (err) {
          throw invalidInput(
            `Could not read session input files: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
        const dir = resolveDataDir({ override: dataDir ?? null, skillRoot });
        const created = await engine.createSession({
          spec,
          brief,
          scope: localScope(dir),
        });
        // CWE-050 composition (CWE-049 standalone list item 2): mirror
        // the session into the authorization store at creation time,
        // in the same provisioned installation namespace, so
        // `authorization preview` freezes exactly what was created.
        // (Sample sessions are labeled fixtures on their own scope and
        // are not mirrored; their grant path is the sample fixture's.)
        const authorization = createStandaloneRunAuthorization({ dataDir: dir });
        try {
          mirrorSession(authorization, created);
        } finally {
          authorization.close();
        }
        printResult(
          io,
          json,
          `Session created: ${created.spec.session_id} (mode ${created.spec.mode}, state ${created.state.state}).`,
          {
            ok: true,
            session_id: created.spec.session_id,
            mode: created.spec.mode,
            state: created.state.state,
            sample: false,
          },
        );
        return 0;
      }

      case 'sample': {
        if (sub !== 'run') {
          throw usageError('Usage: blackceo-council sample run [--json]');
        }
        const sample = buildSampleSession();
        const { host } = createLocalHost({
          dataDir,
          skillRoot,
          transports: [
            {
              routeId: sample.spec.model_policy.route_id,
              transport: new DeterministicFixtureTransport(),
            },
          ],
        });
        const grant = sampleGrant(host);
        grant.session_id = sample.spec.session_id;
        grant.brief_sha256 = sample.spec.brief_sha256;
        grant.mode = sample.spec.mode;
        grant.seat_ids = [...sample.spec.seat_ids];
        grant.scope = { ...sample.scope };
        host.authorize = {
          async resolveRunGrant(grantRef: string, sessionId: string) {
            return grantRef === 'sample-grant' && sessionId === sample.spec.session_id
              ? grant
              : null;
          },
        };
        const engine = engineFor(host);
        const existing = await host.store.getSession(sample.spec.session_id);
        if (!existing) {
          await engine.createSession({ ...sample, sample: true });
        }
        const done =
          existing && existing.state.state === 'COMPLETED'
            ? existing
            : await engine.startSession(sample.spec.session_id, 'sample-grant');
        const verdict = await engine.getVerdict(sample.spec.session_id);
        if (!verdict) {
          throw new CouncilError(
            'COUNCIL_VERDICT_NOT_READY',
            `Sample session ended in state ${done.state.state} without a verdict.`,
            { retryable: false, exitCode: 3 },
          );
        }
        printResult(io, json, verdictHuman(verdict, true), {
          ok: true,
          sample: true,
          session_id: verdict.session_id,
          state: done.state.state,
          verdict,
        });
        return 0;
      }

      case 'start':
      case 'resume': {
        const sessionId = sub;
        if (!sessionId) throw usageError(`${command} requires a session ID.`);
        const grantRef = flagString(flags, 'grant-ref');
        if (!grantRef) {
          throw usageError(
            `${command} requires --grant-ref REF. A run cannot start without a resolved run grant (Section 25.6).`,
          );
        }
        const { host } = hostFor();
        const engine = engineFor(host);
        const session =
          command === 'start'
            ? await engine.startSession(sessionId, grantRef)
            : await engine.resumeSession(sessionId, grantRef);
        printResult(
          io,
          json,
          `Session ${sessionId}: state ${session.state.state} (version ${session.state.state_version}).`,
          {
            ok: true,
            session_id: sessionId,
            state: session.state.state,
            state_version: session.state.state_version,
            sample: session.sample,
          },
        );
        return session.state.state === 'COMPLETED' ? 0 : 3;
      }

      case 'status': {
        const sessionId = sub;
        if (!sessionId) throw usageError('status requires a session ID.');
        const { host } = hostFor();
        const engine = engineFor(host);
        const session = await engine.getSession(sessionId);
        const budget = host.budget.snapshot(sessionId);
        printResult(
          io,
          json,
          [
            `Session ${sessionId}${session.sample ? ' (SAMPLE)' : ''}`,
            `  mode: ${session.spec.mode}`,
            `  state: ${session.state.state} (version ${session.state.state_version})`,
            `  brief revision: ${session.state.brief_revision}`,
            `  provider requests consumed: ${budget.consumed.provider_requests} of ${budget.ceilings.max_provider_requests}`,
          ].join('\n'),
          {
            ok: true,
            session_id: sessionId,
            mode: session.spec.mode,
            state: session.state.state,
            state_version: session.state.state_version,
            brief_revision: session.state.brief_revision,
            sample: session.sample,
            budget,
          },
        );
        return 0;
      }

      case 'pause':
      case 'cancel': {
        const sessionId = sub;
        if (!sessionId) throw usageError(`${command} requires a session ID.`);
        const { host } = hostFor();
        const engine = engineFor(host);
        const session =
          command === 'pause'
            ? await engine.pauseSession(sessionId)
            : await engine.cancelSession(sessionId);
        printResult(
          io,
          json,
          `Session ${sessionId}: state ${session.state.state}.`,
          { ok: true, session_id: sessionId, state: session.state.state },
        );
        return 0;
      }

      case 'verdict': {
        const sessionId = sub;
        if (!sessionId) throw usageError('verdict requires a session ID.');
        const { host } = hostFor();
        const engine = engineFor(host);
        const session = await engine.getSession(sessionId);
        const verdict = await engine.getVerdict(sessionId);
        if (!verdict) {
          throw new CouncilError(
            'COUNCIL_VERDICT_NOT_READY',
            `Session ${sessionId} is ${session.state.state} and has no validated verdict yet.`,
            {
              retryable: false,
              action: 'Check status; a verdict exists only after VERIFYING completes.',
              exitCode: 3,
            },
          );
        }
        printResult(io, json, verdictHuman(verdict, session.sample), {
          ok: true,
          sample: session.sample,
          verdict,
        });
        return 0;
      }

      case 'replay': {
        const sessionId = sub;
        if (!sessionId) throw usageError('replay requires a session ID.');
        const { host } = hostFor();
        const engine = engineFor(host);
        const session = await engine.getSession(sessionId);
        const events = await engine.replaySession(sessionId);
        printResult(
          io,
          json,
          [
            `Committed events for session ${sessionId}${session.sample ? ' (SAMPLE)' : ''} (read only):`,
            ...events.map(
              (e) => `  ${e.sequence}. ${e.event_type} by ${e.actor} at ${e.created_at}`,
            ),
          ].join('\n'),
          { ok: true, sample: session.sample, events },
        );
        return 0;
      }

      case 'export': {
        const sessionId = sub;
        if (!sessionId) throw usageError('export requires a session ID.');
        const format = flagString(flags, 'format') ?? 'md';
        if (format !== 'md' && format !== 'json' && format !== 'pdf') {
          throw usageError('export --format must be md, json, or pdf.');
        }
        const { host } = hostFor();
        const engine = engineFor(host);
        const session = await engine.getSession(sessionId);
        const verdict = await engine.getVerdict(sessionId);
        if (!verdict) {
          throw new CouncilError(
            'COUNCIL_VERDICT_NOT_READY',
            `Session ${sessionId} has no validated verdict to export.`,
            { retryable: false, exitCode: 3 },
          );
        }
        // CWE-050 composition (B15 portable half): exports run through
        // CWE-038's validated ReportExportService: publication
        // validation, journaling, and deliverable registration on the
        // exact verdict hash. PDF is registered not ready by that
        // service and refuses with EXPORT_FORMAT_NOT_READY (CWE-044).
        const artifact = await exportVerdictReport({
          store: host.store,
          session,
          verdict,
          format,
          requestId: host.ids.newId(),
          exportedAt: host.clock.nowUtc(),
        });
        const outPath = flagString(flags, 'out');
        if (outPath) {
          writeFileSync(outPath, artifact.bytes, 'utf8');
          printResult(
            io,
            json,
            `Exported ${format} report for ${sessionId} to ${outPath} (deliverable ${artifact.deliverable_id}, sha256 ${artifact.sha256}).`,
            {
              ok: true,
              written: outPath,
              format,
              deliverable_id: artifact.deliverable_id,
              sha256: artifact.sha256,
              verdict_content_sha256: artifact.verdict_content_sha256,
            },
          );
        } else if (json && format !== 'json') {
          printResult(io, json, '', {
            ok: true,
            format,
            deliverable_id: artifact.deliverable_id,
            filename: artifact.filename,
            sha256: artifact.sha256,
            verdict_content_sha256: artifact.verdict_content_sha256,
            content: artifact.bytes,
          });
        } else {
          io.out(artifact.bytes);
        }
        return 0;
      }

      default:
        throw usageError(`Unknown command: ${[command, sub, third].filter(Boolean).join(' ')}`);
    }
  } catch (err) {
    const council = isCouncilError(err)
      ? err
      : err instanceof Error && err.name === 'ContractError'
        ? new CouncilError('COUNCIL_STATE_CONFLICT', err.message, {
            retryable: false,
            exitCode: 3,
          })
        : new CouncilError(
            'COUNCIL_INTERNAL',
            err instanceof Error ? err.message : String(err),
            { retryable: false, exitCode: 1 },
          );
    if (json) {
      io.err(`${JSON.stringify(council.toEnvelope(), null, 2)}\n`);
    } else {
      io.err(`Error [${council.code}]: ${council.message}\nNext action: ${council.action}\n`);
    }
    return council.exitCode;
  }
}
