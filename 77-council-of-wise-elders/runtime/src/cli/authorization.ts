/**
 * Authorization CLI handlers and the standalone composition for the
 * run authorization service (CWE-049, directive Sections 25.3, 25.4,
 * 25.6).
 *
 * This module owns the `authorization preview|approve|status|revoke`
 * command handlers behind CWE-004's stable dispatcher interface. The
 * dispatcher case for `authorization` still returns FEATURE_NOT_READY
 * in the foundation build; CWE-050 performs the final composition by
 * delegating that case to handleAuthorizationCommand below (named in
 * the CWE-049 build report). Handlers here are complete and tested in
 * an isolated profile without the final packaging.
 *
 * Standalone trust boundary (stated precisely, Section 25.4): the
 * standalone host is a single-user local profile. The trust boundary
 * is the local OS account: whoever controls the OS account controls
 * the profile's data directory and can approve runs as the local
 * owner. This protects against other OS accounts and against remote
 * or model-side actors; it does NOT protect against a malicious
 * process running with the same owner's privileges, and nothing here
 * claims otherwise. A local installation UUID is a workspace
 * namespace, never cross-company authority.
 *
 * First standalone use provisions a stable local installation UUID
 * and workspace namespace in protected configuration
 * (council-installation.json in the data directory, mode 0600). The
 * provisioned scope is what this module's sessions, envelopes, and
 * grants bind to.
 *
 * Approval interaction law: approve renders the exact saved preview
 * and takes confirmation from the controlling terminal through the
 * injected confirmPreview callback (the host shell wires it to the
 * terminal; it is never stdin data, never a flag, never a file). In
 * --json mode, machine results go to stdout and confirmation still
 * uses the controlling terminal callback. When no callback is wired
 * (headless), approval is refused with RUN_AUTHORIZATION_REQUIRED
 * unless a valid standing grant covers the preview, and the draft and
 * preview are preserved. There is deliberately no --yes flag, no
 * environment variable, and no approval-file path anywhere in this
 * module: the argument parser below reads only the documented flags,
 * and a test proves that presenting bypass-shaped flags changes
 * nothing.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import {
  canonicalHash,
  type RunCeilings,
  type RunGrant,
  type RunPreview,
  type ScopeFields,
} from '../contracts/index.js';
import { DurableBudgetService, type PinnedRouteSnapshot } from '../budgets/index.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../persistence/envelope.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import {
  RunAdmissionService,
  RunAuthorizationService,
  isRunAuthorizationError,
  type TrustedPrincipal,
} from '../authorization/index.js';
import type { AuthorizationProvider, CouncilHost } from './host-ports.js';
import { CouncilError, invalidInput, usageError } from './errors.js';

// ------------------------------------------------------------- installation

export interface StandaloneInstallation {
  installation_id: string;
  tenant_id: string;
  company_id: string;
  owner_subject: string;
  created_at: string;
}

const INSTALLATION_FILE = 'council-installation.json';

/**
 * Resolve the standalone installation scope, provisioning it on first
 * use: a stable local installation UUID and workspace namespace in
 * protected configuration (Section 25.4). An existing file is read,
 * never regenerated, so the namespace is stable across restarts.
 */
export function resolveStandaloneInstallation(dataDir: string): StandaloneInstallation {
  const path = join(dataDir, INSTALLATION_FILE);
  if (existsSync(path)) {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as StandaloneInstallation;
    if (
      typeof parsed.installation_id === 'string' &&
      typeof parsed.tenant_id === 'string' &&
      typeof parsed.company_id === 'string' &&
      typeof parsed.owner_subject === 'string'
    ) {
      return parsed;
    }
    throw new CouncilError(
      'COUNCIL_STATE_CONFLICT',
      `The standalone installation record at ${path} is malformed. It was not regenerated or overwritten.`,
      { retryable: false, exitCode: 3 },
    );
  }
  mkdirSync(dataDir, { recursive: true });
  const installation: StandaloneInstallation = {
    installation_id: randomUUID(),
    tenant_id: 'local-tenant',
    company_id: 'local-company',
    owner_subject: 'local-owner',
    created_at: new Date().toISOString(),
  };
  writeFileSync(path, `${JSON.stringify(installation, null, 2)}\n`, {
    encoding: 'utf8',
    mode: 0o600,
  });
  return installation;
}

export function standaloneScope(installation: StandaloneInstallation): ScopeFields {
  return {
    installation_id: installation.installation_id,
    tenant_id: installation.tenant_id,
    company_id: installation.company_id,
    owner_subject: installation.owner_subject,
  };
}

export function standalonePrincipal(installation: StandaloneInstallation): TrustedPrincipal {
  return {
    tenant_id: installation.tenant_id,
    company_id: installation.company_id,
    installation_id: installation.installation_id,
    subject: installation.owner_subject,
    channel: 'local_owner',
    support_access: false,
  };
}

export function standaloneEnvelope(
  installation: StandaloneInstallation,
  purpose: AuthorizationEnvelope['purpose'] = 'write',
): AuthorizationEnvelope {
  return envelopeFromScope(
    standaloneScope(installation),
    installation.owner_subject,
    'owner',
    purpose,
  );
}

// -------------------------------------------------------------- composition

export interface RunAuthorizationComposition {
  installation: StandaloneInstallation;
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  budget: DurableBudgetService;
  grants: RunAuthorizationService;
  admission: RunAdmissionService;
  envelope: AuthorizationEnvelope;
  principal: TrustedPrincipal;
  /** The host-ports AuthorizationProvider the engine resolves through. */
  authorize: AuthorizationProvider;
  close(): void;
}

/**
 * Compose the standalone run authorization stack over the profile's
 * own authorization database in the data directory (canonical CWE-005
 * schema, CWE-006 store). Sessions are mirrored into this store from
 * the host's session store by mirrorSession before preview, so the
 * journal, budget, and grant records share one durable home.
 */
/**
 * Compose the standalone run authorization stack over the installation's
 * ONE canonical council database (`<dataDir>/council.db`).
 *
 * Store-seam law (W25-U001 Lane E): the CLI host store, this authorization
 * composition and the service composition engine all open the same file.
 * A separate `council-authorization.db` made `mirrorSession` write canonical
 * `council_sessions`/`council_events` rows into a database the service never
 * reads, so a session created by `blackceo-council create` was invisible to
 * `GET /council/<id>` and its event stream. The local foundation tables
 * (`sessions`, `events`, ...) and the canonical `council_*` tables share the
 * file without collision because their names are disjoint.
 */
export function createStandaloneRunAuthorization(options: {
  dataDir: string;
  clock?: { nowUtc(): string };
  ids?: { newId(): string };
}): RunAuthorizationComposition {
  const clock = options.clock ?? { nowUtc: () => new Date().toISOString() };
  const ids = options.ids ?? { newId: () => randomUUID() };
  const installation = resolveStandaloneInstallation(options.dataDir);
  const db = CouncilDatabase.open(join(options.dataDir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const repositories = new CouncilRepositories(db, {
    clock,
    ids,
    config: parsePersistenceConfig(),
  });
  const budget = new DurableBudgetService({ db, clock, ids });
  const grants = new RunAuthorizationService({ db, clock, ids });
  const admission = new RunAdmissionService(grants, budget);
  const envelope = standaloneEnvelope(installation);
  const principal = standalonePrincipal(installation);
  const authorize: AuthorizationProvider = {
    async resolveRunGrant(grantRef: string, sessionId: string) {
      return grants.resolveRunGrant(envelope, grantRef, sessionId);
    },
  };
  return {
    installation,
    db,
    repositories,
    budget,
    grants,
    admission,
    envelope,
    principal,
    authorize,
    close: () => db.close(),
  };
}

/**
 * Mirror a session from the host's session store into the
 * authorization store (idempotent: an existing mirror is returned).
 * The mirror carries the same spec, brief, scope, and state record, so
 * previews freeze exactly what the host froze.
 */
export function mirrorSession(
  composition: RunAuthorizationComposition,
  session: import('./host-ports.js').StoredSession,
): void {
  const existing = composition.repositories.getSession(
    composition.envelope,
    session.spec.session_id,
  );
  if (existing) return;
  composition.repositories.createSession(composition.envelope, session);
}

/** Compose the service into a local host (CWE-050's integration step, prebuilt here). */
export function withRunAuthorization(
  host: CouncilHost,
  composition: RunAuthorizationComposition,
): CouncilHost {
  return { ...host, authorize: composition.authorize };
}

// ------------------------------------------------------------------ handlers

export interface AuthorizationCliIo {
  out(text: string): void;
  err(text: string): void;
}

export interface AuthorizationCliOptions {
  dataDir: string;
  json: boolean;
  io: AuthorizationCliIo;
  /**
   * Controlling-terminal confirmation for interactive approval: the
   * host shell renders the preview text and returns the owner's
   * decision. Absent means headless: approval then requires a valid
   * standing grant, else RUN_AUTHORIZATION_REQUIRED.
   */
  confirmPreview?: (previewText: string) => Promise<boolean>;
  clock?: { nowUtc(): string };
  ids?: { newId(): string };
}

function flagString(
  flags: Map<string, string | true>,
  name: string,
): string | null {
  const value = flags.get(name);
  return typeof value === 'string' ? value : null;
}

function toCouncilError(error: unknown): CouncilError {
  if (error instanceof CouncilError) return error;
  if (isRunAuthorizationError(error)) {
    // Map onto CWE-004's stable CLI vocabulary: authorization absence
    // keeps its own code; every other typed refusal is a state
    // conflict at the CLI boundary (the service code stays available
    // in the message's detail for API consumers of the service).
    return new CouncilError(
      error.code === 'RUN_AUTHORIZATION_REQUIRED' ||
        error.code === 'RUN_CONFIRMATION_REQUIRED'
        ? 'RUN_AUTHORIZATION_REQUIRED'
        : 'COUNCIL_STATE_CONFLICT',
      `${error.message} [${error.code}]`,
      { retryable: error.retryable, action: error.action, exitCode: 3 },
    );
  }
  if (error instanceof Error && error.name === 'AuthorizationError') {
    return new CouncilError('COUNCIL_STATE_CONFLICT', error.message, {
      retryable: false,
      exitCode: 3,
    });
  }
  if (error instanceof Error && error.name === 'BudgetCapacityError') {
    const code = (error as { code?: unknown }).code;
    return new CouncilError(
      code === 'BUDGET_EXHAUSTED' ? 'COUNCIL_BUDGET_EXHAUSTED' : 'COUNCIL_STATE_CONFLICT',
      error.message,
      { retryable: false, exitCode: 3 },
    );
  }
  return new CouncilError(
    'COUNCIL_INTERNAL',
    error instanceof Error ? error.message : String(error),
    { retryable: false, exitCode: 1 },
  );
}

function renderPreviewText(preview: RunPreview, grantIdNote: string): string {
  const lines = [
    'Run authorization preview (no authority until approved)',
    `  preview: ${preview.preview_id}`,
    `  session: ${preview.session_id}`,
    `  purpose: ${preview.purpose}`,
    `  mode: ${preview.mode}; seats: ${preview.seat_ids.join(', ')}`,
    `  brief revision ${preview.brief_revision}, hash ${preview.brief_sha256}`,
    `  route policy hash: ${preview.route_policy_sha256}`,
    `  ceilings: ${preview.ceilings.max_provider_requests} provider requests, ` +
      `${preview.ceilings.max_output_repairs} output repairs, ` +
      `${preview.ceilings.max_transport_retries} transport retries`,
    preview.ceilings.max_money
      ? `  money ceiling: ${preview.ceilings.max_money.amount_minor} ${preview.ceilings.max_money.currency} (minor units)`
      : '  money ceiling: none (unknown price is not zero; count ceilings still bind)',
    `  preview expires: ${preview.expires_at}`,
    `  preview hash: ${preview.preview_sha256}`,
    grantIdNote,
  ];
  return lines.join('\n');
}

/**
 * The authorization command handlers (preview, approve, status,
 * revoke). Argument arrays and flags arrive from the dispatcher;
 * results print as clean JSON (--json) or a short human summary, and
 * failures are CouncilError envelopes the dispatcher already renders.
 */
export async function handleAuthorizationCommand(
  sub: string | undefined,
  positionals: string[],
  flags: Map<string, string | true>,
  options: AuthorizationCliOptions,
): Promise<void> {
  const { io, json } = options;
  const composition = createStandaloneRunAuthorization({
    dataDir: options.dataDir,
    clock: options.clock,
    ids: options.ids,
  });
  try {
    switch (sub) {
      case 'preview': {
        const sessionId = positionals[0];
        if (!sessionId) {
          throw usageError('authorization preview requires a session ID.');
        }
        const specPath = flagString(flags, 'route-snapshot');
        if (!specPath) {
          throw usageError(
            'authorization preview requires --route-snapshot FILE (the pinned route selection JSON).',
          );
        }
        let routeSnapshot: PinnedRouteSnapshot;
        let ceilings: RunCeilings;
        try {
          routeSnapshot = JSON.parse(readFileSync(specPath, 'utf8')) as PinnedRouteSnapshot;
          const ceilingsPath = flagString(flags, 'limits');
          ceilings = ceilingsPath
            ? (JSON.parse(readFileSync(ceilingsPath, 'utf8')) as RunCeilings)
            : defaultCeilings();
        } catch (error) {
          throw invalidInput(
            `Could not read preview input files: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
        const preview = composition.grants.previewRun(composition.envelope, {
          session_id: sessionId,
          purpose: parsePurpose(flagString(flags, 'purpose')),
          route_snapshot: routeSnapshot,
          route_policy_sha256:
            flagString(flags, 'route-policy-hash') ??
            canonicalHash({ route_snapshot: routeSnapshot }),
          ceilings,
          require_money_bound: flags.has('require-money-bound'),
        });
        const human = renderPreviewText(
          preview,
          '  (approve with: authorization approve --preview PREVIEW_ID)',
        );
        io.out(
          json
            ? `${JSON.stringify({ ok: true, preview }, null, 2)}\n`
            : `${human}\n`,
        );
        return;
      }

      case 'approve': {
        const previewId = flagString(flags, 'preview');
        if (!previewId) {
          throw usageError('authorization approve requires --preview PREVIEW_ID.');
        }
        const standingParent = flagString(flags, 'standing-grant');
        let grant: RunGrant;
        if (standingParent) {
          // The standing path never prompts: the host verifies the
          // pre-existing record through the same approveRun coverage
          // check. No flag value confers authority by itself: the
          // record must exist, stand, and cover the exact envelope.
          grant = composition.grants.approveRun(composition.envelope, previewId, {
            principal: composition.principal,
            authority_mode: 'existing_standing_grant',
            standing_parent_grant_id: standingParent,
          });
        } else {
          const preview = loadPreview(composition, previewId);
          if (!options.confirmPreview) {
            throw new CouncilError(
              'RUN_AUTHORIZATION_REQUIRED',
              'Headless approval is refused: no controlling-terminal confirmation is available and no standing grant was presented. The preview and the draft session are preserved.',
              {
                retryable: false,
                action:
                  'Approve interactively from the controlling terminal, or approve under a valid standing grant with --standing-grant.',
                exitCode: 3,
              },
            );
          }
          const confirmed = await options.confirmPreview(
            renderPreviewText(preview, '  Approve this exact envelope?'),
          );
          if (!confirmed) {
            throw new CouncilError(
              'RUN_AUTHORIZATION_REQUIRED',
              'The owner did not confirm the preview. Nothing was approved; the preview and draft are preserved.',
              { retryable: false, exitCode: 3 },
            );
          }
          grant = composition.grants.approveRun(composition.envelope, previewId, {
            principal: composition.principal,
            authority_mode: 'local_interactive_owner',
            interactive_confirmation: true,
          });
        }
        io.out(
          json
            ? `${JSON.stringify({ ok: true, grant }, null, 2)}\n`
            : [
                `Run grant approved: ${grant.grant_id}`,
                `  session: ${grant.session_id}; purpose: ${grant.purpose}`,
                `  authority: ${grant.authority_mode}; expires: ${grant.expires_at}`,
                `  start with: start ${grant.session_id} --grant-ref ${grant.grant_id}`,
              ].join('\n') + '\n',
        );
        return;
      }

      case 'status': {
        const grantId = positionals[0] ?? flagString(flags, 'grant');
        if (!grantId) {
          throw usageError('authorization status requires a grant ID.');
        }
        const sessionId = flagString(flags, 'session') ?? undefined;
        const grant = composition.grants.resolveRunGrant(
          composition.envelope,
          grantId,
          sessionId,
        );
        const record = composition.grants.loadGrantRecord(composition.envelope, grantId);
        const data = {
          ok: true,
          grant_id: grantId,
          resolvable: grant !== null,
          status: record ? record.status : 'not_found',
          authority_mode: record ? record.authority_mode : null,
          purpose: record ? record.purpose : null,
          expires_at: record ? record.expires_at : null,
          standing_parent_grant_id: record ? record.parent_grant_id : null,
          grant,
        };
        io.out(
          json
            ? `${JSON.stringify(data, null, 2)}\n`
            : [
                `Run grant ${grantId}: ${data.status}${grant ? ' (resolvable)' : ' (not resolvable)'}`,
                `  authority: ${data.authority_mode ?? 'none'}; purpose: ${data.purpose ?? 'none'}; expires: ${data.expires_at ?? 'none'}`,
              ].join('\n') + '\n',
        );
        return;
      }

      case 'revoke': {
        const grantId = positionals[0] ?? flagString(flags, 'grant');
        if (!grantId) {
          throw usageError('authorization revoke requires a grant ID.');
        }
        const result = composition.grants.revokeRunGrant(
          composition.envelope,
          grantId,
          composition.principal,
        );
        io.out(
          json
            ? `${JSON.stringify({ ok: true, ...result }, null, 2)}\n`
            : `Run grant ${grantId}: ${result.status}${result.already_final ? ' (already final; nothing changed)' : ' (revoked; it now admits nothing)'}\n`,
        );
        return;
      }

      default:
        throw usageError(
          'Usage: blackceo-council authorization preview|approve|status|revoke ...',
        );
    }
  } catch (error) {
    throw toCouncilError(error);
  } finally {
    composition.close();
  }
}

function defaultCeilings(): RunCeilings {
  return {
    max_provider_requests: 50,
    max_output_repairs: 9,
    max_transport_retries: 8,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: null,
  };
}

function parsePurpose(raw: string | null): RunPreview['purpose'] | undefined {
  if (raw === null) return undefined;
  const purposes: Array<RunPreview['purpose']> = [
    'council_run',
    'capability_probe',
    'intake_refinement',
    'follow_up',
  ];
  if ((purposes as string[]).includes(raw)) {
    return raw as RunPreview['purpose'];
  }
  throw usageError(
    `--purpose must be one of ${purposes.join(', ')}; got ${raw}.`,
  );
}

function loadPreview(
  composition: RunAuthorizationComposition,
  previewId: string,
): RunPreview {
  const rows = composition.db.read((handle) =>
    handle
      .prepare(
        `SELECT preview_json FROM council_run_previews
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(composition.envelope.tenant_id, composition.envelope.company_id, previewId),
  ) as { preview_json: string } | undefined;
  if (!rows) {
    throw new CouncilError(
      'COUNCIL_INVALID_INPUT',
      `No run preview ${previewId} exists in this profile. Create one with authorization preview first.`,
      { retryable: false, exitCode: 3 },
    );
  }
  return JSON.parse(rows.preview_json) as RunPreview;
}
