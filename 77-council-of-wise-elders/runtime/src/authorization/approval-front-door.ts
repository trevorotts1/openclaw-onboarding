/**
 * The usable approval front door (WER-009 dependency-ready slice).
 *
 * One structured approval command, one idempotency key, one committed
 * receipt. This module is the user-facing front door in front of the
 * ONE existing authority service (`RunAuthorizationService` in
 * run-grants.ts, consumed here, never duplicated). It owns NO second
 * authority database: the durable grant, preview, journal, outbox, and
 * the idempotency registry are the existing CWE-006/CWE-049 rows. The
 * request-key row written here lives in the existing
 * `council_request_keys` table, the same registry WER-011's durable
 * operation producer uses; no new table is introduced.
 *
 * Laws:
 *
 * - The fingerprint covers the ENTIRE normalized approval command:
 *   trusted scope and acting principal, session, preview, authority
 *   mode, interactive confirmation, chosen ceilings, chosen expiry,
 *   standing-parent linkage, renewal linkage, and the route options
 *   (route policy hash, the preview's pinned route fingerprint, the
 *   host's re-resolved CWE-008 snapshot fingerprint, the WER-006
 *   frozen-route snapshot hash, and any host-exposed route options).
 *   An exact retry with the same idempotency key returns the ORIGINAL
 *   committed receipt and creates no second grant. The same key with
 *   ANY changed option conflicts BEFORE any write; the conflict path
 *   is a read-only check outside a transaction.
 *
 * - Preview-to-session association is checked before anything else.
 *   A preview minted for session B and submitted to session A's
 *   approval command is refused with RUN_PREVIEW_SESSION_MISMATCH and
 *   zero grant, session-state, journal, outbox, or request-key writes,
 *   even when both sessions have the same owner. `approveRun` also
 *   enforces `expected_session_id` itself, so the same guard holds for
 *   callers that compose the service directly.
 *
 * - Principal and scope checks are the trusted CWE-007 checks, reused:
 *   the envelope must match the host-resolved TrustedPrincipal, the
 *   preview must belong to the named session in the same tenant,
 *   company, and installation, and the service's existing
 *   assertSessionMutate rule still decides who may approve a private
 *   session.
 *
 * - Revoked and expired authority refuses WITHOUT mutating state. The
 *   start path re-reads the durable record and refuses a revoked
 *   record, an elapsed expiry, or a session whose revocation
 *   generation advanced past the grant's epoch. It deliberately does
 *   NOT call the service's lazy expiry transition on the refusal path,
 *   so a refused Start leaves every row untouched.
 *
 * - Start does not require a fabricated grant id. A new user approves
 *   with a structured command and starts with the SAME idempotency
 *   key: the front door resolves the committed grant through the
 *   request-key row. Start is read-only and therefore idempotent by
 *   construction; retrying it returns the same grant and writes
 *   nothing.
 *
 * Authority separation (directive Section 1.2, non-negotiable):
 * a Council spending authorization is `council_run` ONLY. It is NOT
 * development merge permission and it is NOT `action_plan_approval`
 * or `execution` authority. Nothing here approves a plan, creates a
 * task, executes an external action, or authorizes a merge; those
 * remain separate authorization kinds with separate grants
 * (`AUTHORIZATION_KIND_FOR_PERMISSION` in permissions.ts). A run
 * grant that exists says only that the inferred run's spending
 * envelope was approved.
 */

import {
  canonicalHash,
  validateRunPreview,
  type AuthorizationKind,
  type Clock,
  type RunCeilings,
  type RunGrant,
  type RunGrantAuthorityMode,
  type RunPreview,
  type RunPurpose,
} from '../contracts/index.js';
import {
  routeSnapshotFingerprint,
  type PinnedRouteSnapshot,
} from '../budgets/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { assertEnvelopePurpose } from '../persistence/envelope.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from '../persistence/sqlite.js';
import {
  verifyRouteSnapshotHash,
  type CouncilRouteSnapshot,
} from '../providers/route-snapshot.js';
import {
  RunAuthorizationError,
  RunAuthorizationService,
  type ApproveRunDecision,
  type RunGrantRecord,
} from './run-grants.js';
import { assertSessionMutate, type TrustedPrincipal } from './scope.js';

// ------------------------------------------------------------------ constants

/** The idempotency registry source for approval commands. */
export const APPROVAL_IDEMPOTENCY_SOURCE = 'council-run-approval';
/** The idempotency registry operation for approval commands. */
export const APPROVAL_IDEMPOTENCY_OPERATION = 'approve';
/** Receipt schema identifier. */
export const APPROVAL_RECEIPT_VERSION = 'wise-elders.approval-receipt/v1';
/**
 * A Council spending authorization is this kind and nothing else.
 * `permissions.ts` maps it to the 'run' permission; development merge
 * permission and `action_plan_approval`/`execution` are different
 * kinds and never travel as this constant.
 */
export const COUNCIL_SPENDING_AUTHORIZATION_KIND: AuthorizationKind = 'council_run';

const IDEMPOTENCY_KEY_MAX_LENGTH = 300;
const ROUTE_OPTION_SCALARS = new Set(['string', 'number', 'boolean']);

// ------------------------------------------------------------------ commands

/** Host-exposed route options the approver can change (scalar map). */
export type RouteOptions = Readonly<Record<string, string | number | boolean | null>>;

/**
 * The structured approval command. This is the front door's input: a
 * caller supplies typed values, never raw JSON, and never a grant id.
 */
export interface ApprovalCommand {
  /** One approval interaction. The retry key; never a grant id. */
  idempotency_key: string;
  /** The session whose approval surface received this command. */
  session_id: string;
  preview_id: string;
  authority_mode: RunGrantAuthorityMode;
  /** Required true for local_interactive_owner (host confirmation). */
  interactive_confirmation?: boolean;
  /** Required for existing_standing_grant. */
  standing_parent_grant_id?: string | null;
  /** May only tighten the previewed expiry. */
  chosen_expires_at?: string | null;
  /** May only tighten the previewed ceilings, field by field. */
  chosen_ceilings?: Partial<RunCeilings> | null;
  /** The grant this approval renews, when it is a renewal. */
  renews_grant_id?: string | null;
  /** The host's re-resolved CWE-008 route snapshot (approval-time pin). */
  current_route_snapshot?: PinnedRouteSnapshot | null;
  /** The WER-006 frozen route snapshot, when the host carries it. */
  route_snapshot?: CouncilRouteSnapshot | null;
  /** Additional route options shown to the approver. */
  route_options?: RouteOptions | null;
}

/** The structured preview command: no route-snapshot JSON file needed. */
export interface PreviewCommand {
  session_id: string;
  purpose?: RunPurpose;
  route_snapshot: PinnedRouteSnapshot;
  route_policy_sha256: string;
  ceilings: RunCeilings;
  allowed_operation_kinds?: string[];
  account_ref?: string | null;
  require_money_bound?: boolean;
}

/**
 * The Start command. It names the session and the approval's
 * idempotency key. It has no grant-id field: the front door resolves
 * the committed grant itself, so a user never fabricates one.
 */
export interface StartCommand {
  session_id: string;
  approval_idempotency_key: string;
}

/** The normalized command the fingerprint is computed over. */
export interface NormalizedApprovalCommand {
  idempotency_key: string;
  session_id: string;
  preview_id: string;
  authority_mode: RunGrantAuthorityMode;
  interactive_confirmation: boolean;
  standing_parent_grant_id: string | null;
  chosen_expires_at: string | null;
  chosen_ceilings: Partial<RunCeilings> | null;
  renews_grant_id: string | null;
  current_route_snapshot: PinnedRouteSnapshot | null;
  route_snapshot_sha256: string | null;
  route_options: RouteOptions | null;
}

// ------------------------------------------------------------------- receipt

/**
 * The committed approval receipt. Built only from durable rows
 * (grant record + committed request-key row), so an exact retry
 * reconstructs the ORIGINAL receipt byte for byte. It intentionally
 * reports what was approved, not the grant's live status: a later
 * revocation changes Start admission, never the historical receipt.
 */
export interface ApprovalReceipt {
  schema_version: typeof APPROVAL_RECEIPT_VERSION;
  /** Canonical hash of every other receipt field. */
  receipt_id: string;
  idempotency_key: string;
  command_fingerprint: string;
  preview_id: string;
  preview_sha256: string;
  grant_id: string;
  session_id: string;
  authority_mode: RunGrantAuthorityMode;
  purpose: RunPurpose;
  approved_ceilings: RunCeilings;
  issued_at: string;
  expires_at: string;
  standing_parent_grant_id: string | null;
  renews_grant_id: string | null;
  /** The Start handle: no fabricated grant id is ever required. */
  start: {
    session_id: string;
    approval_idempotency_key: string;
  };
}

export interface ApprovalOutcome {
  /** True when this call replayed the committed receipt. */
  replayed: boolean;
  receipt: ApprovalReceipt;
}

/** The two command fields a committed receipt is reconstructed from. */
interface ReceiptCommandRef {
  idempotency_key: string;
  session_id: string;
}

export interface StartOutcome {
  /** The resolved active grant; identical on every idempotent retry. */
  grant: RunGrant;
  /** The ORIGINAL committed approval receipt. */
  receipt: ApprovalReceipt;
  start: {
    session_id: string;
    /** The caller passes this to the existing Start command. */
    grant_ref: string;
  };
}

// ---------------------------------------------------------------- validation

function invalidCommand(message: string): RunAuthorizationError {
  return new RunAuthorizationError('RUN_INVALID_INPUT', message, {
    action: 'Correct the approval command and retry.',
  });
}

function requireNonEmpty(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw invalidCommand(`${field} must be a non-empty string.`);
  }
  return value;
}

function nullableNonEmpty(value: unknown, field: string): string | null {
  if (value === undefined || value === null) return null;
  return requireNonEmpty(value, field);
}

function normalizeAuthorityMode(value: unknown): RunGrantAuthorityMode {
  const modes: readonly RunGrantAuthorityMode[] = [
    'managed_principal',
    'local_interactive_owner',
    'existing_standing_grant',
  ];
  if ((modes as readonly unknown[]).includes(value)) {
    return value as RunGrantAuthorityMode;
  }
  throw invalidCommand(
    `authority_mode must be one of ${modes.join(', ')}; received ${String(value)}.`,
  );
}

function normalizeCeilings(chosen: unknown): Partial<RunCeilings> | null {
  if (chosen === undefined || chosen === null) return null;
  if (typeof chosen !== 'object' || chosen === null || Array.isArray(chosen)) {
    throw invalidCommand('chosen_ceilings must be an object when supplied.');
  }
  const input = chosen as Record<string, unknown>;
  const out: Partial<RunCeilings> = {};
  const count = (field: keyof RunCeilings): void => {
    if (!(field in input)) return;
    const value = input[field];
    if (!Number.isSafeInteger(value) || (value as number) < 0) {
      throw invalidCommand(`chosen_ceilings.${field} must be a safe integer >= 0.`);
    }
    (out as Record<string, unknown>)[field] = value;
  };
  count('max_provider_requests');
  count('max_output_repairs');
  count('max_transport_retries');
  for (const field of ['max_input_tokens', 'max_output_tokens'] as const) {
    if (!(field in input)) continue;
    const value = input[field];
    if (value === null) {
      out[field] = null;
      continue;
    }
    if (!Number.isSafeInteger(value) || (value as number) < 0) {
      throw invalidCommand(`chosen_ceilings.${field} must be null or a safe integer >= 0.`);
    }
    out[field] = value as number;
  }
  if ('max_money' in input) {
    const money = input.max_money;
    if (money === null) {
      out.max_money = null;
    } else if (
      typeof money === 'object' &&
      money !== null &&
      !Array.isArray(money) &&
      Number.isSafeInteger((money as { amount_minor?: unknown }).amount_minor) &&
      (money as { amount_minor: number }).amount_minor >= 0 &&
      typeof (money as { currency?: unknown }).currency === 'string' &&
      ((money as { currency: string }).currency.length > 0)
    ) {
      out.max_money = {
        amount_minor: (money as { amount_minor: number }).amount_minor,
        currency: (money as { currency: string }).currency,
      };
    } else {
      throw invalidCommand(
        'chosen_ceilings.max_money must be null or { amount_minor: safe integer >= 0, currency: non-empty string }.',
      );
    }
  }
  return out;
}

function normalizeRouteOptions(options: unknown): RouteOptions | null {
  if (options === undefined || options === null) return null;
  if (typeof options !== 'object' || Array.isArray(options)) {
    throw invalidCommand('route_options must be a plain object of scalar values when supplied.');
  }
  const out: Record<string, string | number | boolean | null> = {};
  for (const [key, value] of Object.entries(options as Record<string, unknown>)) {
    if (key.length === 0) throw invalidCommand('route_options keys must be non-empty.');
    if (value === null) {
      out[key] = null;
      continue;
    }
    if (!ROUTE_OPTION_SCALARS.has(typeof value)) {
      throw invalidCommand(
        `route_options.${key} must be a string, number, boolean, or null. A changed route option is a material change, so nested values are not accepted.`,
      );
    }
    if (typeof value === 'number' && !Number.isFinite(value)) {
      throw invalidCommand(`route_options.${key} must be a finite number.`);
    }
    out[key] = value as string | number | boolean;
  }
  return out;
}

function normalizeExpiry(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) {
    throw invalidCommand('chosen_expires_at must be a valid ISO timestamp or null.');
  }
  return new Date(Date.parse(value)).toISOString();
}

/**
 * Normalize one approval command. Pure: no database access, no writes.
 * Every value the fingerprint covers is present in the returned shape.
 */
export function normalizeApprovalCommand(
  command: ApprovalCommand,
): NormalizedApprovalCommand {
  if (typeof command !== 'object' || command === null) {
    throw invalidCommand('An approval command object is required.');
  }
  const idempotencyKey = requireNonEmpty(command.idempotency_key, 'idempotency_key');
  if (idempotencyKey.length > IDEMPOTENCY_KEY_MAX_LENGTH) {
    throw invalidCommand(
      `idempotency_key must be at most ${IDEMPOTENCY_KEY_MAX_LENGTH} characters.`,
    );
  }
  const authorityMode = normalizeAuthorityMode(command.authority_mode);
  const standingParent = nullableNonEmpty(
    command.standing_parent_grant_id,
    'standing_parent_grant_id',
  );
  if (authorityMode === 'existing_standing_grant' && standingParent === null) {
    throw invalidCommand(
      'existing_standing_grant approval requires standing_parent_grant_id.',
    );
  }
  if (authorityMode !== 'existing_standing_grant' && standingParent !== null) {
    throw invalidCommand(
      'standing_parent_grant_id is only meaningful with authority_mode existing_standing_grant.',
    );
  }
  const routeSnapshot = command.route_snapshot ?? null;
  if (routeSnapshot !== null) {
    if (
      typeof routeSnapshot !== 'object' ||
      typeof routeSnapshot.snapshotSha256 !== 'string' ||
      !/^[0-9a-f]{64}$/.test(routeSnapshot.snapshotSha256) ||
      verifyRouteSnapshotHash(routeSnapshot) !== true
    ) {
      throw invalidCommand(
        'route_snapshot must be a WER-006 frozen route snapshot whose published snapshotSha256 verifies. A frozen snapshot whose hash does not verify is never approved.',
      );
    }
  }
  return {
    idempotency_key: idempotencyKey,
    session_id: requireNonEmpty(command.session_id, 'session_id'),
    preview_id: requireNonEmpty(command.preview_id, 'preview_id'),
    authority_mode: authorityMode,
    interactive_confirmation: command.interactive_confirmation === true,
    standing_parent_grant_id: standingParent,
    chosen_expires_at: normalizeExpiry(command.chosen_expires_at),
    chosen_ceilings: normalizeCeilings(command.chosen_ceilings),
    renews_grant_id: nullableNonEmpty(command.renews_grant_id, 'renews_grant_id'),
    current_route_snapshot: command.current_route_snapshot ?? null,
    route_snapshot_sha256: routeSnapshot === null ? null : routeSnapshot.snapshotSha256,
    route_options: normalizeRouteOptions(command.route_options),
  };
}

/** Normalize the Start command. Pure; no grant id is accepted or needed. */
export function normalizeStartCommand(command: StartCommand): StartCommand {
  if (typeof command !== 'object' || command === null) {
    throw invalidCommand('A Start command object is required.');
  }
  return {
    session_id: requireNonEmpty(command.session_id, 'session_id'),
    approval_idempotency_key: requireNonEmpty(
      command.approval_idempotency_key,
      'approval_idempotency_key',
    ),
  };
}

// --------------------------------------------------------- preview context

interface PreviewRow {
  id: string;
  session_id: string;
  grant_id: string;
}

interface ApprovalRow {
  id: string;
  session_id: string | null;
  status: string;
  scope_proof: string;
}

interface RequestKeyRow {
  payload_fingerprint: string;
  response_operation_id: string | null;
  session_id: string | null;
}

interface PreviewContext {
  preview: PreviewRow;
  anchor: ApprovalRow;
  routePolicySha256: string;
  pinnedRouteSnapshotFingerprint: string | null;
  previewSha256: string;
  revocationEpoch: number;
}

interface ProofFacts {
  preview_sha256?: unknown;
  route_policy_sha256?: unknown;
  route_snapshot_fingerprint?: unknown;
  revocation_epoch?: unknown;
}

// ------------------------------------------------------------------ service

export interface ApprovalFrontDoorDeps {
  /** The ONE existing authority service. Not a second one. */
  grants: RunAuthorizationService;
  db: CouncilDatabase;
  clock: Clock;
}

export class ApprovalFrontDoor {
  private readonly grants: RunAuthorizationService;
  private readonly db: CouncilDatabase;
  private readonly clock: Clock;

  constructor(deps: ApprovalFrontDoorDeps) {
    this.grants = deps.grants;
    this.db = deps.db;
    this.clock = deps.clock;
  }

  // -------------------------------------------------------------- preview

  /**
   * Freeze a run preview from structured values. A caller never has to
   * author a route-snapshot JSON file or a limits file; the host
   * supplies the already-resolved CWE-008 snapshot in memory.
   */
  preview(envelope: AuthorizationEnvelope, command: PreviewCommand): RunPreview {
    assertEnvelopePurpose(envelope, 'write', 'Run preview');
    const preview = this.grants.previewRun(envelope, {
      session_id: command.session_id,
      purpose: command.purpose,
      route_snapshot: command.route_snapshot,
      route_policy_sha256: command.route_policy_sha256,
      ceilings: command.ceilings,
      allowed_operation_kinds: command.allowed_operation_kinds,
      account_ref: command.account_ref ?? null,
      require_money_bound: command.require_money_bound,
    });
    const check = validateRunPreview(preview);
    if (!check.ok) {
      throw invalidCommand(
        `The preview does not satisfy the canonical RunPreview contract: ${check.issues.map((i) => i.message).join('; ')}`,
      );
    }
    return preview;
  }

  // -------------------------------------------------------------- approve

  /**
   * Approve a preview idempotently. Read-only preflight first: a
   * replay returns the committed receipt; a changed option under an
   * already-committed key conflicts with zero writes. Only a genuinely
   * new command enters the single write transaction, which nests the
   * existing `approveRun` write and commits the request-key row with
   * it.
   */
  approve(
    envelope: AuthorizationEnvelope,
    principal: TrustedPrincipal,
    command: ApprovalCommand,
  ): ApprovalOutcome {
    assertEnvelopePurpose(envelope, 'write', 'Run approval command');
    this.assertPrincipalMatchesEnvelope(envelope, principal);
    const normalized = normalizeApprovalCommand(command);

    // Read-only preview association. This is the cross-session guard:
    // it runs before the fingerprint and before any transaction.
    const context = this.readPreviewContext(envelope, normalized.preview_id);
    if (!context) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_NOT_FOUND',
        `No run preview ${normalized.preview_id} exists in this scope. Approval can only act on a stored preview; nothing was written.`,
        { detail: { preview_id: normalized.preview_id } },
      );
    }
    if (context.preview.session_id !== normalized.session_id) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_SESSION_MISMATCH',
        `Preview ${normalized.preview_id} belongs to session ${context.preview.session_id}, not to the approval session ${normalized.session_id}. Nothing was approved or written.`,
        {
          detail: {
            preview_id: normalized.preview_id,
            preview_session_id: context.preview.session_id,
            expected_session_id: normalized.session_id,
          },
        },
      );
    }

    const fingerprint = this.approvalCommandFingerprint(
      envelope,
      principal,
      normalized,
      context,
    );

    // Read-only conflict/replay check: a changed option never starts a
    // write transaction.
    const existing = this.db.read((handle) =>
      this.readRequestKey(handle, envelope, normalized.idempotency_key),
    );
    if (existing) {
      return this.replay(envelope, normalized, fingerprint, existing);
    }

    return this.db.write((handle) => {
      // Re-check inside the transaction: the primary key serializes
      // the race and the loser replays instead of approving twice.
      const again = this.readRequestKey(handle, envelope, normalized.idempotency_key);
      if (again) {
        return this.replay(envelope, normalized, fingerprint, again);
      }
      const decision: ApproveRunDecision = {
        principal,
        authority_mode: normalized.authority_mode,
        interactive_confirmation: normalized.interactive_confirmation,
        standing_parent_grant_id: normalized.standing_parent_grant_id,
        chosen_expires_at: normalized.chosen_expires_at,
        chosen_ceilings: normalized.chosen_ceilings,
        renews_grant_id: normalized.renews_grant_id,
        current_route_snapshot: normalized.current_route_snapshot,
        expected_session_id: normalized.session_id,
      };
      const grant = this.grants.approveRun(envelope, normalized.preview_id, decision);
      this.insertRequestKey(
        handle,
        envelope,
        normalized.idempotency_key,
        fingerprint,
        grant.session_id,
        grant.grant_id,
      );
      const record = this.grants.loadGrantRecord(envelope, grant.grant_id);
      if (!record) {
        throw new RunAuthorizationError(
          'RUN_APPROVAL_RECEIPT_UNAVAILABLE',
          `Grant ${grant.grant_id} was approved but its durable record does not read back. The receipt cannot be served.`,
          { detail: { grant_id: grant.grant_id } },
        );
      }
      return {
        replayed: false,
        receipt: this.buildReceipt(record, normalized, fingerprint),
      };
    });
  }

  // ----------------------------------------------------------------- start

  /**
   * Resolve Start authority from the approval's idempotency key.
   * Read-only: no grant, state, event, or request-key write happens on
   * this path, including every refusal. A revoked record, a lapsed
   * expiry, or an advanced session revocation generation refuses
   * without mutating the store.
   */
  start(
    envelope: AuthorizationEnvelope,
    principal: TrustedPrincipal,
    command: StartCommand,
  ): StartOutcome {
    // Start is a READ-ONLY resolution. The envelope purpose is not
    // restricted beyond the host's normal write envelope: this path
    // never opens a write transaction, so a write envelope here is
    // harmless and does not widen anything.
    assertEnvelopePurpose(envelope, 'write', 'Run Start');
    this.assertPrincipalMatchesEnvelope(envelope, principal);
    const normalized = normalizeStartCommand(command);

    const recorded = this.db.read((handle) =>
      this.readRequestKey(handle, envelope, normalized.approval_idempotency_key),
    );
    if (!recorded || recorded.response_operation_id === null) {
      throw new RunAuthorizationError(
        'RUN_START_APPROVAL_NOT_FOUND',
        `No committed approval exists for idempotency key ${normalized.approval_idempotency_key} in this scope. Start never guesses or accepts a fabricated grant id; approve first.`,
        { detail: { approval_idempotency_key: normalized.approval_idempotency_key } },
      );
    }
    if (recorded.session_id !== normalized.session_id) {
      throw new RunAuthorizationError(
        'RUN_START_SCOPE_MISMATCH',
        `The committed approval for key ${normalized.approval_idempotency_key} belongs to another session. Start refuses and writes nothing.`,
        { detail: { approval_idempotency_key: normalized.approval_idempotency_key } },
      );
    }
    const grantId = recorded.response_operation_id;
    const record = this.grants.loadGrantRecord(envelope, grantId);
    if (!record || record.proof.stage !== 'granted' || record.proof.standing) {
      throw new RunAuthorizationError(
        'RUN_START_GRANT_INACTIVE',
        `The approval for key ${normalized.approval_idempotency_key} does not name a granted, session-bound run grant. Nothing was started or written.`,
        { detail: { grant_id: grantId } },
      );
    }
    if (record.session_id !== normalized.session_id) {
      throw new RunAuthorizationError(
        'RUN_START_SCOPE_MISMATCH',
        `The approval for key ${normalized.approval_idempotency_key} is bound to session ${record.session_id}, not ${normalized.session_id}. Start refuses and writes nothing.`,
        {
          detail: {
            grant_id: grantId,
            approval_session_id: record.session_id,
            start_session_id: normalized.session_id,
          },
        },
      );
    }
    if (record.proof.installation_id !== envelope.installation_id) {
      throw new RunAuthorizationError(
        'RUN_START_SCOPE_MISMATCH',
        `The approval for key ${normalized.approval_idempotency_key} is bound to another installation. Start refuses and writes nothing.`,
        { detail: { grant_id: grantId } },
      );
    }
    if (record.status === 'revoked') {
      throw new RunAuthorizationError(
        'RUN_START_GRANT_REVOKED',
        `Run grant ${grantId} was revoked. Start refuses; nothing was started or written.`,
        { detail: { grant_id: grantId, status: record.status } },
      );
    }
    if (
      record.status === 'expired' ||
      Date.parse(record.expires_at) <= Date.parse(this.clock.nowUtc())
    ) {
      throw new RunAuthorizationError(
        'RUN_START_GRANT_EXPIRED',
        `Run grant ${grantId} expired at ${record.expires_at}. Start refuses; nothing was started, refreshed, or written.`,
        { detail: { grant_id: grantId, status: 'expired' } },
      );
    }
    if (record.purpose !== 'council_run') {
      throw new RunAuthorizationError(
        'RUN_GRANT_PURPOSE_MISMATCH',
        `Run grant ${grantId} has purpose ${record.purpose}; Start requires council_run. It is not an execution or plan-approval credential.`,
        { detail: { grant_id: grantId, purpose: record.purpose } },
      );
    }
    if (record.parent_grant_id !== null) {
      const parent = this.grants.loadGrantRecord(envelope, record.parent_grant_id);
      if (!parent || !this.grants.standingParentStands(parent)) {
        throw new RunAuthorizationError(
          'RUN_START_GRANT_REVOKED',
          `The standing parent of run grant ${grantId} no longer stands. Start refuses; nothing was started or written.`,
          { detail: { grant_id: grantId, standing_parent_grant_id: record.parent_grant_id } },
        );
      }
    }
    // Principal and session scope checks, reusing the CWE-007 rules.
    const session = this.grants.sessionFor(envelope, normalized.session_id);
    if (
      session.scope.tenant_id !== envelope.tenant_id ||
      session.scope.company_id !== envelope.company_id ||
      session.scope.installation_id !== envelope.installation_id
    ) {
      throw new RunAuthorizationError(
        'RUN_START_SCOPE_MISMATCH',
        `Session ${normalized.session_id} is outside the authorization envelope. Start refuses and writes nothing.`,
        { detail: { session_id: normalized.session_id } },
      );
    }
    assertSessionMutate(principal, {
      scope: session.scope,
      visibility: session.spec.visibility,
    });
    if (session.state.revocation_generation > record.proof.revocation_epoch) {
      throw new RunAuthorizationError(
        'RUN_START_GRANT_REVOKED',
        `Session ${normalized.session_id} advanced its revocation generation past grant ${grantId}'s epoch. Start refuses; nothing was started or written.`,
        {
          detail: {
            grant_id: grantId,
            grant_revocation_epoch: record.proof.revocation_epoch,
            session_revocation_generation: session.state.revocation_generation,
          },
        },
      );
    }
    // mutate_on_expiry: false keeps the refusal path read-only even if
    // the clock crosses the expiry between the check above and this
    // resolve.
    const grant = this.grants.resolveRunGrant(
      envelope,
      grantId,
      normalized.session_id,
      { mutate_on_expiry: false },
    );
    if (!grant) {
      const latest = this.grants.loadGrantRecord(envelope, grantId);
      if (
        latest &&
        latest.status === 'active' &&
        Date.parse(latest.expires_at) <= Date.parse(this.clock.nowUtc())
      ) {
        throw new RunAuthorizationError(
          'RUN_START_GRANT_EXPIRED',
          `Run grant ${grantId} expired at ${latest.expires_at}. Start refuses; nothing was started, refreshed, or written.`,
          { detail: { grant_id: grantId, status: 'expired' } },
        );
      }
      throw new RunAuthorizationError(
        'RUN_START_GRANT_INACTIVE',
        `Run grant ${grantId} does not resolve as active. Start refuses; nothing was started or written.`,
        { detail: { grant_id: grantId } },
      );
    }
    const receipt = this.buildReceipt(
      record,
      {
        idempotency_key: normalized.approval_idempotency_key,
        session_id: normalized.session_id,
      },
      recorded.payload_fingerprint,
    );
    return {
      grant,
      receipt,
      start: {
        session_id: normalized.session_id,
        grant_ref: grant.grant_id,
      },
    };
  }

  // ------------------------------------------------------------ internals

  private assertPrincipalMatchesEnvelope(
    envelope: AuthorizationEnvelope,
    principal: TrustedPrincipal,
  ): void {
    if (
      envelope.tenant_id !== principal.tenant_id ||
      envelope.company_id !== principal.company_id ||
      envelope.installation_id !== principal.installation_id ||
      envelope.actor_subject !== principal.subject
    ) {
      throw new RunAuthorizationError(
        'RUN_GRANT_SCOPE_MISMATCH',
        'The authorization envelope does not match the trusted principal. Approval and Start act only inside the principal that the host verified; nothing was written.',
      );
    }
  }

  private readPreviewContext(
    envelope: AuthorizationEnvelope,
    previewId: string,
  ): PreviewContext | null {
    return this.db.read((handle) => {
      const preview = handle
        .prepare(
          `SELECT id, session_id, grant_id FROM council_run_previews
            WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, previewId) as
        | PreviewRow
        | undefined;
      if (!preview) return null;
      const anchor = handle
        .prepare(
          `SELECT id, session_id, status, scope_proof FROM council_approvals
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'run_grant'`,
        )
        .get(envelope.tenant_id, envelope.company_id, preview.grant_id) as
        | ApprovalRow
        | undefined;
      if (!anchor) {
        throw new RunAuthorizationError(
          'RUN_PREVIEW_TAMPERED',
          `Preview ${previewId} references a grant anchor that is missing. Approval is refused and nothing was written.`,
          { detail: { preview_id: previewId } },
        );
      }
      let proof: ProofFacts;
      try {
        proof = JSON.parse(anchor.scope_proof) as ProofFacts;
      } catch {
        throw new RunAuthorizationError(
          'RUN_PREVIEW_TAMPERED',
          `Preview ${previewId}'s grant anchor carries an unparseable proof. Approval is refused and nothing was written.`,
          { detail: { preview_id: previewId } },
        );
      }
      if (
        typeof proof.preview_sha256 !== 'string' ||
        typeof proof.route_policy_sha256 !== 'string'
      ) {
        throw new RunAuthorizationError(
          'RUN_PREVIEW_TAMPERED',
          `Preview ${previewId}'s grant anchor is missing its frozen preview or route policy binding. Approval is refused and nothing was written.`,
          { detail: { preview_id: previewId } },
        );
      }
      return {
        preview,
        anchor,
        routePolicySha256: proof.route_policy_sha256,
        pinnedRouteSnapshotFingerprint:
          typeof proof.route_snapshot_fingerprint === 'string'
            ? proof.route_snapshot_fingerprint
            : null,
        previewSha256: proof.preview_sha256,
        revocationEpoch:
          typeof proof.revocation_epoch === 'number' ? proof.revocation_epoch : 0,
      };
    });
  }

  private approvalCommandFingerprint(
    envelope: AuthorizationEnvelope,
    principal: TrustedPrincipal,
    command: NormalizedApprovalCommand,
    context: PreviewContext,
  ): string {
    return canonicalHash({
      command_version: 'wise-elders.approval-command/v1',
      scope: {
        tenant_id: envelope.tenant_id,
        company_id: envelope.company_id,
        installation_id: envelope.installation_id,
        actor_subject: envelope.actor_subject,
      },
      principal: {
        subject: principal.subject,
        channel: principal.channel,
        support_access: principal.support_access,
      },
      session_id: command.session_id,
      preview_id: command.preview_id,
      preview_sha256: context.previewSha256,
      idempotency_key: command.idempotency_key,
      authority_mode: command.authority_mode,
      interactive_confirmation: command.interactive_confirmation,
      standing_parent_grant_id: command.standing_parent_grant_id,
      renews_grant_id: command.renews_grant_id,
      chosen_expires_at: command.chosen_expires_at,
      // The complete chosen ceiling option, with absent fields explicit.
      chosen_ceilings: ceilingFingerprintBody(command.chosen_ceilings),
      route: {
        route_policy_sha256: context.routePolicySha256,
        pinned_route_snapshot_fingerprint: context.pinnedRouteSnapshotFingerprint,
        preview_revocation_epoch: context.revocationEpoch,
        current_route_snapshot_fingerprint:
          command.current_route_snapshot === null
            ? null
            : routeSnapshotFingerprint(command.current_route_snapshot),
        route_snapshot_sha256: command.route_snapshot_sha256,
        route_options: command.route_options,
      },
    });
  }

  private replay(
    envelope: AuthorizationEnvelope,
    command: NormalizedApprovalCommand,
    fingerprint: string,
    existing: RequestKeyRow,
  ): ApprovalOutcome {
    if (existing.payload_fingerprint !== fingerprint) {
      throw new RunAuthorizationError(
        'RUN_APPROVAL_IDEMPOTENCY_CONFLICT',
        `Idempotency key ${command.idempotency_key} is already committed with a different approval command fingerprint. Nothing was written; use the original command or a new key.`,
        {
          detail: {
            idempotency_key: command.idempotency_key,
            preview_id: command.preview_id,
          },
        },
      );
    }
    const grantId = existing.response_operation_id;
    if (grantId === null) {
      throw new RunAuthorizationError(
        'RUN_APPROVAL_RECEIPT_UNAVAILABLE',
        `Idempotency key ${command.idempotency_key} is recorded without a committed grant id. The receipt cannot be served.`,
        { detail: { idempotency_key: command.idempotency_key } },
      );
    }
    const record = this.grants.loadGrantRecord(envelope, grantId);
    if (!record || record.proof.stage !== 'granted') {
      throw new RunAuthorizationError(
        'RUN_APPROVAL_RECEIPT_UNAVAILABLE',
        `The committed approval ${grantId} no longer reads back. Its receipt is unavailable; nothing was written.`,
        { detail: { grant_id: grantId } },
      );
    }
    return { replayed: true, receipt: this.buildReceipt(record, command, fingerprint) };
  }

  private buildReceipt(
    record: RunGrantRecord,
    command: ReceiptCommandRef,
    fingerprint: string,
  ): ApprovalReceipt {
    const previewId = record.proof.preview_id;
    if (
      record.proof.stage !== 'granted' ||
      record.session_id !== command.session_id ||
      typeof previewId !== 'string' ||
      typeof record.proof.preview_sha256 !== 'string'
    ) {
      throw new RunAuthorizationError(
        'RUN_APPROVAL_RECEIPT_UNAVAILABLE',
        `Grant ${record.grant_id} does not match the committed approval command. The receipt cannot be served.`,
        { detail: { grant_id: record.grant_id } },
      );
    }
    const body: Omit<ApprovalReceipt, 'receipt_id'> = {
      schema_version: APPROVAL_RECEIPT_VERSION,
      idempotency_key: command.idempotency_key,
      command_fingerprint: fingerprint,
      preview_id: previewId,
      preview_sha256: record.proof.preview_sha256,
      grant_id: record.grant_id,
      session_id: command.session_id,
      authority_mode: record.authority_mode,
      purpose: record.purpose,
      approved_ceilings: record.proof.ceilings,
      issued_at: record.issued_at,
      expires_at: record.expires_at,
      standing_parent_grant_id: record.parent_grant_id,
      renews_grant_id: record.proof.renews_grant_id,
      start: {
        session_id: command.session_id,
        approval_idempotency_key: command.idempotency_key,
      },
    };
    return { ...body, receipt_id: canonicalHash(body) };
  }

  /**
   * Namespace the caller's idempotency key by company and installation.
   * The registry's primary key is (tenant, source, operation,
   * request_key); two companies in one tenant must never share an
   * approval slot because they used the same click key.
   */
  private requestKey(
    envelope: AuthorizationEnvelope,
    idempotencyKey: string,
  ): string {
    return canonicalHash({
      company_id: envelope.company_id,
      installation_id: envelope.installation_id,
      idempotency_key: idempotencyKey,
    });
  }

  private readRequestKey(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    idempotencyKey: string,
  ): RequestKeyRow | null {
    const row = handle
      .prepare(
        `SELECT payload_fingerprint, response_operation_id, session_id
           FROM council_request_keys
          WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
      )
      .get(
        envelope.tenant_id,
        APPROVAL_IDEMPOTENCY_SOURCE,
        APPROVAL_IDEMPOTENCY_OPERATION,
        this.requestKey(envelope, idempotencyKey),
      ) as RequestKeyRow | undefined;
    return row ?? null;
  }

  private insertRequestKey(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    idempotencyKey: string,
    fingerprint: string,
    sessionId: string,
    grantId: string,
  ): void {
    handle
      .prepare(
        `INSERT INTO council_request_keys
           (tenant_id, source, operation, request_key, payload_fingerprint,
            session_id, response_operation_id, response_status, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)`,
      )
      .run(
        envelope.tenant_id,
        APPROVAL_IDEMPOTENCY_SOURCE,
        APPROVAL_IDEMPOTENCY_OPERATION,
        this.requestKey(envelope, idempotencyKey),
        fingerprint,
        sessionId,
        grantId,
        this.clock.nowUtc(),
      );
  }
}

// ------------------------------------------------------------------ helpers

/**
 * A canonical fingerprint body for chosen ceilings: every field is
 * explicit (null when not supplied), so an approval command's ceiling
 * options are covered end to end.
 */
function ceilingFingerprintBody(
  chosen: Partial<RunCeilings> | null,
): Record<string, unknown> | null {
  if (chosen === null) return null;
  return {
    max_provider_requests: chosen.max_provider_requests ?? null,
    max_output_repairs: chosen.max_output_repairs ?? null,
    max_transport_retries: chosen.max_transport_retries ?? null,
    max_input_tokens: chosen.max_input_tokens ?? null,
    max_output_tokens: chosen.max_output_tokens ?? null,
    max_money: chosen.max_money ?? null,
  };
}

