/**
 * The ONE canonical run authorization service (CWE-049, directive
 * Sections 1.2, 11, 15, 17.5, 25.6, 28).
 *
 * This service issues, resolves, and revokes purpose-bound run grants
 * (the RunGrant contract of CWE-003) over CWE-006's scoped store. The
 * durable grant record is the council_approvals row with
 * kind 'run_grant': it is the money authority CWE-028's budget service
 * reads (max_cost_minor, status, expiry, session binding), and the full
 * binding (installation, owner, route pin, brief hash, ceilings,
 * revocation epoch, preview hash, standing-parent link) travels in the
 * row's scope_proof as canonical JSON, with the seat allowlist in
 * seat_allowlist_json.
 *
 * Surface (Section 25.6, exactly): previewRun, approveRun,
 * resolveRunGrant, revokeRunGrant here; admitOperation and
 * recordConsumption live in admission.ts, composed on this service and
 * CWE-028's DurableBudgetService. No other module in this build issues
 * grants. Standing authorizations are PRE-EXISTING records by design
 * (Section 25.6: "the host verifies a pre-existing standing grant");
 * provisionStandingAuthorization is the host provisioning path that
 * records one, kept visibly separate from the six canonical operations.
 *
 * Laws enforced here:
 * - Purpose binding: a grant binds principal, scope (installation,
 *   tenant, company, owner), session, purpose, the pinned route
 *   snapshot fingerprint, the frozen brief hash, mode and seats, pack
 *   and protocol versions, allowed operation kinds, ceilings, and
 *   expiry. Previews default to 15 minutes validity, grants to 24
 *   hours; a stricter chosen limit wins; a standing parent's earlier
 *   expiry wins over both.
 * - No bypass: there is no code path in this module that reads a flag,
 *   an environment variable, a file, or model output as approval.
 *   Approval is an explicit decision object carrying a TrustedPrincipal
 *   resolved by the host (CWE-007 ports): a local interactive owner
 *   must additionally present the host's controlling-terminal
 *   confirmation, a managed principal must arrive on a managed channel,
 *   and a standing grant satisfies approval only through the coverage
 *   check in approveRun itself, never through a side door. Headless
 *   approval without one of those three is RUN_AUTHORIZATION_REQUIRED
 *   and the preview (and any draft session) is preserved untouched.
 * - No authority before approval: council_run_previews.grant_id is a
 *   foreign key to council_approvals, so previewRun writes the grant
 *   row and the preview row in one transaction. The pre-approval row is
 *   born with status 'expired' and the preview's own expiry: it is a
 *   durable anchor that confers NOTHING (CWE-028 refuses reservations
 *   under non-active grants, and resolveRunGrant returns null for it).
 *   approveRun is the only transition that makes a row 'active'.
 * - Revocation and expiry are durable and immediate: revocation flips
 *   the row in the same transaction that journals grant_revoked, and
 *   every resolve or admission re-reads the row, so a revoked or
 *   expired grant admits nothing, including replays of an earlier
 *   admission (admission.ts re-checks through this service and through
 *   CWE-028's in-transaction grant check). Expiry is lazy but journaled:
 *   the first resolve or admission that observes a lapsed active grant
 *   flips it to 'expired' and journals the transition; a worker restart
 *   or browser refresh never extends an expiry.
 * - Preview-to-session binding and revoked authority: approveRun
 *   enforces `expected_session_id` when the caller names the approval
 *   session (a preview from session B can never approve session A,
 *   even under one owner), and refuses a preview whose revocation
 *   epoch was overtaken by the session's revocation generation. Both
 *   checks run before the single approval transaction, so a refusal
 *   writes nothing. `resolveRunGrant(..., { mutate_on_expiry: false })`
 *   lets a read-only caller (the WER-009 Start gate) refuse an expired
 *   grant without the lazy expiry transition.
 * - Renewal never resets accounting: reservations and consumption are
 *   session-scoped in CWE-028's ledger, so a renewal grant for the same
 *   session inherits the session's consumed and reserved totals (and a
 *   standing parent's aggregate, which is the same session ledger when
 *   the parent serves that session). approveRun records the renewed
 *   grant id in the new grant's proof; nothing here zeroes a counter.
 * - The journal is the audit trail: preview, approval (including
 *   standing satisfaction), revocation, and observed expiry are
 *   journaled in CWE-006's hash-chained journal under the bound session
 *   with the frozen vocabulary (grant_issued and grant_revoked carry a
 *   grant_kind 'run_grant' discriminator and a lifecycle field, the
 *   same payload-discriminator pattern CWE-006's diagnostic grants and
 *   CWE-028's route outcomes established; no event type is invented).
 *   Admission refusals are journaled by admission.ts.
 * - No credential values exist anywhere in a grant record, a preview,
 *   a journal payload, or an outbox intent: the shapes carry hashes,
 *   references, and presence only.
 */

import {
  CONTRACT_PACKAGE_VERSION,
  canonicalHash,
  canonicalStringify,
  validateRunGrant,
  validateRunPreview,
  type Clock,
  type GrantStatus,
  type IdSource,
  type RunCeilings,
  type RunGrant,
  type RunGrantAuthorityMode,
  type RunPreview,
  type RunPurpose,
} from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  routeSnapshotFingerprint,
  type PinnedRouteSnapshot,
} from '../budgets/route-snapshot.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import {
  assertEnvelopePurpose,
  type AuthorizationEnvelope,
} from '../persistence/envelope.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from '../persistence/sqlite.js';
import {
  AuthorizationError,
  assertSessionMutate,
  type TrustedPrincipal,
} from './scope.js';

// ------------------------------------------------------------------ errors

export type RunAuthorizationErrorCode =
  | 'RUN_AUTHORIZATION_REQUIRED'
  | 'RUN_CONFIRMATION_REQUIRED'
  | 'RUN_AUTHORITY_MODE_MISMATCH'
  | 'RUN_INVALID_INPUT'
  | 'RUN_SESSION_NOT_FOUND'
  | 'RUN_PREVIEW_NOT_FOUND'
  | 'RUN_PREVIEW_EXPIRED'
  | 'RUN_PREVIEW_STALE'
  | 'RUN_PREVIEW_TAMPERED'
  | 'RUN_MONEY_UNBOUNDED'
  | 'RUN_GRANT_NOT_FOUND'
  | 'RUN_GRANT_INACTIVE'
  | 'RUN_GRANT_SCOPE_MISMATCH'
  | 'RUN_GRANT_ROUTE_MISMATCH'
  | 'RUN_GRANT_PURPOSE_MISMATCH'
  | 'RUN_GRANT_KIND_NOT_ALLOWED'
  | 'RUN_GRANT_PARENT_INVALID'
  | 'RUN_GRANT_WOULD_BROADEN'
  | 'RUN_OPERATION_GRANT_MISMATCH'
  | 'RUN_PREVIEW_SESSION_MISMATCH'
  | 'RUN_AUTHORITY_REVOKED'
  | 'RUN_APPROVAL_IDEMPOTENCY_CONFLICT'
  | 'RUN_APPROVAL_RECEIPT_UNAVAILABLE'
  | 'RUN_START_APPROVAL_NOT_FOUND'
  | 'RUN_START_GRANT_REVOKED'
  | 'RUN_START_GRANT_EXPIRED'
  | 'RUN_START_GRANT_INACTIVE'
  | 'RUN_START_SCOPE_MISMATCH';

/**
 * Stable typed refusal for run authorization. Callers branch on `code`,
 * never on message text (Section 17.3 style, matching CWE-006/CWE-028).
 * Messages never carry credential values or private decision text.
 */
export class RunAuthorizationError extends Error {
  readonly code: RunAuthorizationErrorCode;
  readonly retryable: boolean;
  readonly action: string;
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: RunAuthorizationErrorCode,
    message: string,
    options: {
      retryable?: boolean;
      action?: string;
      detail?: Record<string, unknown> | null;
    } = {},
  ) {
    super(message);
    this.name = 'RunAuthorizationError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.action =
      options.action ?? 'Review the reported problem and try again.';
    this.detail = options.detail ?? null;
  }
}

export function isRunAuthorizationError(
  value: unknown,
): value is RunAuthorizationError {
  return value instanceof RunAuthorizationError;
}

function invalidInput(message: string): RunAuthorizationError {
  return new RunAuthorizationError('RUN_INVALID_INPUT', message, {
    action: 'Correct the authorization input and retry.',
  });
}

// ------------------------------------------------------------------ shapes

/** Default preview validity (Section 25.6): 15 minutes. */
export const DEFAULT_PREVIEW_TTL_MS = 900_000;
/** Default grant validity (Section 25.6): 24 hours. */
export const DEFAULT_GRANT_TTL_MS = 86_400_000;

/** The full grant binding carried in council_approvals.scope_proof. */
export interface RunGrantProof {
  proof_version: 'run-grant-proof/v1';
  /** 'preview' until approveRun flips the row active; then 'granted'. */
  stage: 'preview' | 'granted';
  standing: boolean;
  installation_id: string;
  owner_subject: string | null;
  route_policy_sha256: string;
  route_snapshot: PinnedRouteSnapshot | null;
  route_snapshot_fingerprint: string | null;
  brief_sha256: string | null;
  brief_revision: number | null;
  mode: string | null;
  pack_version: string | null;
  protocol_version: string;
  allowed_operation_kinds: string[];
  ceilings: RunCeilings;
  account_ref: string | null;
  preview_id: string | null;
  preview_sha256: string | null;
  revocation_epoch: number;
  renews_grant_id: string | null;
}

/** One council_approvals run_grant row, decoded. */
export interface RunGrantRecord {
  grant_id: string;
  session_id: string | null;
  authority_mode: RunGrantAuthorityMode;
  purpose: RunPurpose;
  issuer_principal: string;
  /** The seat allowlist column, decoded (requested seats for session grants, covered seats for standing records). */
  seat_ids: string[];
  status: GrantStatus;
  issued_at: string;
  expires_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  consumed_at: string | null;
  max_cost_minor: number | null;
  currency: string | null;
  parent_grant_id: string | null;
  proof: RunGrantProof;
}

export interface PreviewRunInput {
  session_id: string;
  /** Defaults to 'council_run' (Section 25.6). */
  purpose?: RunPurpose;
  /** The pinned CWE-008 route selection this run charges against. */
  route_snapshot: PinnedRouteSnapshot;
  route_policy_sha256: string;
  /** The requested envelope: ceilings the approver will see and bind. */
  ceilings: RunCeilings;
  /** Defaults by purpose; may only name kinds the purpose allows. */
  allowed_operation_kinds?: string[];
  account_ref?: string | null;
  /**
   * When true, the caller requires a hard currency ceiling: a preview
   * whose ceilings carry no money bound is refused rather than allowed
   * to imply a guarantee (an unknown price is not zero, Section 25.6).
   */
  require_money_bound?: boolean;
}

export interface ApproveRunDecision {
  /** The trusted approver, resolved by the host (CWE-007 ports). */
  principal: TrustedPrincipal;
  authority_mode: RunGrantAuthorityMode;
  /**
   * Required true when authority_mode is 'local_interactive_owner':
   * the host asserts the authorized owner confirmed the exact saved
   * preview on the controlling terminal. The service never reads a
   * terminal, a file, or stdin itself; without this assertion the
   * approval is headless and refused.
   */
  interactive_confirmation?: boolean;
  /** Required when authority_mode is 'existing_standing_grant'. */
  standing_parent_grant_id?: string | null;
  /** A stricter chosen expiry; a later one is refused, never applied. */
  chosen_expires_at?: string | null;
  /** May only tighten the previewed ceilings, field by field. */
  chosen_ceilings?: Partial<RunCeilings> | null;
  /** The grant this approval renews, when it is a renewal. */
  renews_grant_id?: string | null;
  /**
   * The route snapshot the host re-resolved at approval time, when it
   * re-resolves: its fingerprint must equal the preview's pin or the
   * preview is stale (a route change is a material change).
   */
  current_route_snapshot?: PinnedRouteSnapshot | null;
  /**
   * The session whose approval URL / approval command was used. When
   * present, the stored preview must belong to exactly this session.
   * Submitting session B's preview through session A's approval URL is
   * refused BEFORE any grant, state, event, or outbox write, even when
   * both sessions share the same owner.
   */
  expected_session_id?: string | null;
}

export interface StandingAuthorizationInput {
  principal: TrustedPrincipal;
  purpose: RunPurpose;
  route_policy_sha256: string;
  pack_version: string;
  /** Seat allowlist the standing authorization covers (superset rule). */
  seat_ids: string[];
  ceilings: RunCeilings;
  allowed_operation_kinds?: string[];
  account_ref?: string | null;
  /** Standing authorizations always carry an explicit expiry. */
  expires_at: string;
}

const OPERATION_KINDS_BY_PURPOSE: Readonly<Record<RunPurpose, string[]>> = {
  council_run: [
    'provider_request',
    'output_repair',
    'transport_retry',
    'semantic_verification',
  ],
  follow_up: [
    'provider_request',
    'output_repair',
    'transport_retry',
    'semantic_verification',
  ],
  capability_probe: ['provider_request'],
  intake_refinement: ['provider_request'],
};

interface ApprovalRow {
  id: string;
  session_id: string | null;
  authority_mode: string;
  purpose: string;
  actor_subject: string;
  actor_role: string;
  parent_approval_id: string | null;
  scope_proof: string;
  max_cost_minor: number | null;
  currency: string | null;
  seat_allowlist_json: string | null;
  status: string;
  issued_at: string;
  expires_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  consumed_at: string | null;
}

interface PreviewRow {
  id: string;
  session_id: string;
  grant_id: string;
  preview_json: string;
  preview_hash: string;
  expires_at: string | null;
  created_at: string;
}

const APPROVAL_COLUMNS = `id, session_id, authority_mode, purpose, actor_subject,
  actor_role, parent_approval_id, scope_proof, max_cost_minor, currency,
  seat_allowlist_json, status, issued_at, expires_at, revoked_at, revoked_by,
  consumed_at`;

// ------------------------------------------------------------------ service

export interface RunAuthorizationServiceDeps {
  db: CouncilDatabase;
  clock: Clock;
  ids: IdSource;
  /** Preview validity; defaults to DEFAULT_PREVIEW_TTL_MS (15 minutes). */
  previewTtlMs?: number;
  /** Grant validity; defaults to DEFAULT_GRANT_TTL_MS (24 hours). */
  grantTtlMs?: number;
}

export class RunAuthorizationService {
  private readonly db: CouncilDatabase;
  private readonly clock: Clock;
  private readonly ids: IdSource;
  private readonly previewTtlMs: number;
  private readonly grantTtlMs: number;
  readonly repositories: CouncilRepositories;

  constructor(deps: RunAuthorizationServiceDeps) {
    this.db = deps.db;
    this.clock = deps.clock;
    this.ids = deps.ids;
    this.previewTtlMs = deps.previewTtlMs ?? DEFAULT_PREVIEW_TTL_MS;
    this.grantTtlMs = deps.grantTtlMs ?? DEFAULT_GRANT_TTL_MS;
    this.repositories = new CouncilRepositories(deps.db, {
      clock: deps.clock,
      ids: deps.ids,
      config: parsePersistenceConfig(),
    });
  }

  // ------------------------------------------------------------ previewRun

  /**
   * Freeze a run preview: the exact data-sharing scope, mode and seats,
   * route pin, and maximum allowance the approver will be shown. A
   * preview confers no authority. It is stale immediately on any
   * material change, which approveRun detects by re-deriving the
   * session facts and comparing hashes. No provider call happens here.
   */
  previewRun(
    envelope: AuthorizationEnvelope,
    input: PreviewRunInput,
  ): RunPreview {
    assertEnvelopePurpose(envelope, 'write', 'Run preview');
    const purpose: RunPurpose = input.purpose ?? 'council_run';
    this.assertCeilings(input.ceilings);
    if (input.require_money_bound === true && input.ceilings.max_money === null) {
      throw new RunAuthorizationError(
        'RUN_MONEY_UNBOUNDED',
        'This run requires a hard currency ceiling, but the requested envelope carries no money bound and no reliable upper bound can be computed. Admission is blocked rather than promised on an unknown price (an unknown price is not zero).',
        {
          action:
            'Supply ceilings with a max_money bound, or drop the hard-ceiling requirement knowingly.',
        },
      );
    }
    const snapScope = input.route_snapshot.scope;
    if (
      snapScope.tenantId !== envelope.tenant_id ||
      snapScope.companyId !== envelope.company_id ||
      snapScope.installationId !== envelope.installation_id
    ) {
      throw new RunAuthorizationError(
        'RUN_GRANT_SCOPE_MISMATCH',
        'The pinned route snapshot scope does not match the authorization envelope. A preview is never minted against a snapshot from another scope.',
        { detail: { session_id: input.session_id } },
      );
    }
    const session = this.sessionFor(envelope, input.session_id);
    const allowedKinds = this.allowedKinds(purpose, input.allowed_operation_kinds);
    const now = this.clock.nowUtc();
    const expiresAt = new Date(Date.parse(now) + this.previewTtlMs).toISOString();
    const previewId = this.ids.newId();
    const grantId = this.ids.newId();
    const fingerprint = routeSnapshotFingerprint(input.route_snapshot);
    // Brief facts bind to the CURRENT brief revision (the brief row
    // the repository serves), not the creation spec: a later brief
    // revision is a material change and must stale this preview.
    const briefRevision = session.brief.revision;
    const briefSha256 = canonicalHash(session.brief);
    const previewContent = {
      schema_version: 'wise-elders.run-preview/v1' as const,
      preview_id: previewId,
      session_id: session.spec.session_id,
      brief_revision: briefRevision,
      brief_sha256: briefSha256,
      mode: session.spec.mode,
      seat_ids: [...session.spec.seat_ids],
      purpose,
      route_policy_sha256: input.route_policy_sha256,
      pack_version: session.spec.source_pack_version,
      ceilings: input.ceilings,
      money_bounded: input.ceilings.max_money !== null,
      created_at: now,
      expires_at: expiresAt,
    };
    const previewSha = canonicalHash(previewContent);
    const preview: RunPreview = { ...previewContent, preview_sha256: previewSha };
    const check = validateRunPreview(preview);
    if (!check.ok) {
      throw invalidInput(
        `The preview does not satisfy the canonical RunPreview contract: ${check.issues.map((i) => i.message).join('; ')}`,
      );
    }
    const proof: RunGrantProof = {
      proof_version: 'run-grant-proof/v1',
      stage: 'preview',
      standing: false,
      installation_id: envelope.installation_id,
      owner_subject: session.scope.owner_subject,
      route_policy_sha256: input.route_policy_sha256,
      route_snapshot: input.route_snapshot,
      route_snapshot_fingerprint: fingerprint,
      brief_sha256: briefSha256,
      brief_revision: briefRevision,
      mode: session.spec.mode,
      pack_version: session.spec.source_pack_version,
      protocol_version: CONTRACT_PACKAGE_VERSION,
      allowed_operation_kinds: allowedKinds,
      ceilings: input.ceilings,
      account_ref: input.account_ref ?? null,
      preview_id: previewId,
      preview_sha256: previewSha,
      revocation_epoch: session.state.revocation_generation,
      renews_grant_id: null,
    };
    this.db.write((handle) => {
      // The anchor grant row: born 'expired' at the preview's own
      // expiry, so it confers no authority and CWE-028 refuses any
      // reservation under it. approveRun is the only path that makes
      // this row active. See the module header for the FK rationale.
      handle
        .prepare(
          `INSERT INTO council_approvals
             (tenant_id, company_id, id, kind, session_id, action_proposal_id,
              authority_mode, purpose, actor_subject, actor_role,
              parent_approval_id, scope_proof, current_plan_hash, verdict_hash,
              max_cost_minor, currency, seat_allowlist_json,
              company_scope_verified, status, issued_at, expires_at,
              revoked_at, revoked_by, consumed_at)
           VALUES (?, ?, ?, 'run_grant', ?, NULL, ?, ?, ?, 'requester', NULL, ?,
                   NULL, NULL, ?, ?, ?, 1, 'expired', ?, ?, NULL, NULL, NULL)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          grantId,
          session.spec.session_id,
          anchorAuthorityModePlaceholder(),
          purpose,
          envelope.actor_subject,
          canonicalStringify(proof),
          input.ceilings.max_money?.amount_minor ?? null,
          input.ceilings.max_money?.currency ?? null,
          canonicalStringify([...session.spec.seat_ids]),
          now,
          expiresAt,
        );
      handle
        .prepare(
          `INSERT INTO council_run_previews
             (tenant_id, company_id, session_id, id, grant_id, preview_json,
              preview_hash, estimate_minor, currency, cost_confirmed,
              frozen_seat_count, risk_class, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          session.spec.session_id,
          previewId,
          grantId,
          canonicalStringify(preview),
          previewSha,
          // Schema filler only when money is unbounded: the canonical
          // preview_json carries money_bounded false and max_money
          // null, and no reader may treat this 0 as a price.
          input.ceilings.max_money?.amount_minor ?? 0,
          input.ceilings.max_money?.currency ?? '',
          input.ceilings.max_money !== null ? 1 : 0,
          session.spec.seat_ids.length,
          previewRiskClass(input.ceilings),
          expiresAt,
          now,
        );
      const event = this.repositories.journal.append(
        handle,
        envelope,
        session.spec.session_id,
        {
          event_id: this.ids.newId(),
          type: 'grant_issued',
          from_state: null,
          to_state: null,
          actor_subject: envelope.actor_subject,
          payload: {
            grant_kind: 'run_grant',
            lifecycle: 'preview',
            authority: 'none',
            preview_id: previewId,
            prospective_grant_id: grantId,
            preview_sha256: previewSha,
            purpose,
            expires_at: expiresAt,
          },
          created_at: now,
        },
      );
      this.repositories.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: session.spec.session_id,
        event_sequence: event.sequence,
        topic: 'run_authorization.preview',
        idempotency_key: `run-authorization:preview:${previewId}`,
        payload: {
          preview_id: previewId,
          session_id: session.spec.session_id,
          preview_sha256: previewSha,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
    });
    return preview;
  }

  // ------------------------------------------------------------ approveRun

  /**
   * Approve a preview into an active grant. Three authority paths, and
   * no fourth: an authorized owner approving interactively on the
   * controlling terminal (local_interactive_owner), a host-verified
   * managed principal (managed_principal), or a pre-existing standing
   * grant that verifiably covers the exact envelope
   * (existing_standing_grant). No provider call happens here.
   */
  approveRun(
    envelope: AuthorizationEnvelope,
    previewId: string,
    decision: ApproveRunDecision,
  ): RunGrant {
    assertEnvelopePurpose(envelope, 'write', 'Run approval');
    const principal = decision.principal;
    this.assertPrincipalMatchesEnvelope(envelope, principal);
    const previewRow = this.db.read((handle) =>
      this.previewRow(handle, envelope, previewId),
    );
    if (!previewRow) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_NOT_FOUND',
        `No run preview ${previewId} exists in this scope. Approval can only act on a stored preview.`,
        { detail: { preview_id: previewId } },
      );
    }
    // Preview-to-session association. The preview id alone is NOT
    // authority: an approval URL/caller names the session it is
    // approving, and a preview minted for any other session is refused
    // here, before any read-derived decision can write. This check
    // happens before verifyPreviewRow, the size checks, and the single
    // approval transaction below, so a cross-session submission leaves
    // the grant, session state, journal, and outbox untouched even
    // when the same owner owns both sessions.
    if (
      decision.expected_session_id !== undefined &&
      decision.expected_session_id !== null &&
      previewRow.session_id !== decision.expected_session_id
    ) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_SESSION_MISMATCH',
        `Preview ${previewId} belongs to session ${previewRow.session_id}, not to the approval session ${decision.expected_session_id}. Nothing was approved or written.`,
        {
          detail: {
            preview_id: previewId,
            preview_session_id: previewRow.session_id,
            expected_session_id: decision.expected_session_id,
          },
        },
      );
    }
    const preview = this.verifyPreviewRow(previewRow);
    const session = this.sessionFor(envelope, previewRow.session_id);
    this.assertPreviewFresh(envelope, preview, previewRow, session, decision);
    // The approver must hold mutation rights over the session: a
    // private session's run is approved only by its owner, and support
    // access never approves (CWE-007 decision, reused, not re-derived).
    assertSessionMutate(principal, {
      scope: session.scope,
      visibility: session.spec.visibility,
    });
    const now = this.clock.nowUtc();
    const anchor = this.db.read((handle) =>
      this.approvalRow(handle, envelope, previewRow.grant_id),
    );
    if (!anchor || anchor.session_id !== previewRow.session_id) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_TAMPERED',
        `Preview ${previewId} references a grant anchor that is missing or bound to another session. Approval is refused.`,
        { detail: { preview_id: previewId } },
      );
    }
    const anchorProof = parseProof(anchor);
    if (anchorProof.stage !== 'preview' || anchorProof.preview_sha256 !== preview.preview_sha256) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_TAMPERED',
        `Preview ${previewId} was already consumed or its anchor does not match the preview hash. Approval is refused.`,
        { detail: { preview_id: previewId } },
      );
    }
    // Revoked or expired authority refuses BEFORE any write. The
    // preview anchor recorded the session's revocation generation when
    // it was frozen; if the session has been revoked since then, the
    // preview (and any approval of it) is dead. The anchor's own durable
    // status is checked too: a record already revoked is never
    // re-approved. Expiry of the preview, of a chosen limit, and of the
    // standing parent is checked before the approval transaction as
    // well (assertPreviewFresh and the effective-expiry checks below);
    // this branch adds the revocation generation fence that a preview
    // could otherwise outlive.
    if (anchor.status === 'revoked') {
      throw new RunAuthorizationError(
        'RUN_AUTHORITY_REVOKED',
        `Approval authority for preview ${previewId} was revoked. Nothing was approved or written; a new preview is required.`,
        { detail: { preview_id: previewId, grant_id: anchor.id } },
      );
    }
    if (session.state.revocation_generation > anchorProof.revocation_epoch) {
      throw new RunAuthorizationError(
        'RUN_AUTHORITY_REVOKED',
        `Session ${session.spec.session_id} advanced its revocation generation to ${session.state.revocation_generation}, past preview ${previewId}'s epoch ${anchorProof.revocation_epoch}. Approval authority is revoked; nothing was approved or written.`,
        {
          detail: {
            preview_id: previewId,
            grant_revocation_epoch: anchorProof.revocation_epoch,
            session_revocation_generation: session.state.revocation_generation,
          },
        },
      );
    }

    // Authority-mode discipline: the declared mode must match how the
    // principal actually arrived, and the local interactive path must
    // carry the host's controlling-terminal confirmation.
    let parent: RunGrantRecord | null = null;
    if (decision.authority_mode === 'local_interactive_owner') {
      if (principal.channel !== 'local_owner') {
        throw new RunAuthorizationError(
          'RUN_AUTHORITY_MODE_MISMATCH',
          'local_interactive_owner approval requires a principal that arrived through the local owner channel.',
          { detail: { channel: principal.channel } },
        );
      }
      if (decision.interactive_confirmation !== true) {
        throw new RunAuthorizationError(
          'RUN_AUTHORIZATION_REQUIRED',
          'Standalone approval requires the authorized owner to confirm the exact saved preview on the controlling terminal. No confirmation was presented, so nothing is approved and the preview and draft are preserved.',
          {
            action:
              'Run the approval interactively, or rely on a valid standing grant that covers this envelope.',
            detail: { preview_id: previewId },
          },
        );
      }
    } else if (decision.authority_mode === 'managed_principal') {
      if (principal.channel === 'local_owner') {
        throw new RunAuthorizationError(
          'RUN_AUTHORITY_MODE_MISMATCH',
          'A local owner principal cannot claim managed_principal authority.',
          { detail: { channel: principal.channel } },
        );
      }
    } else if (decision.authority_mode === 'existing_standing_grant') {
      const parentId = decision.standing_parent_grant_id ?? null;
      if (!parentId) {
        throw invalidInput(
          'existing_standing_grant approval requires standing_parent_grant_id.',
        );
      }
      parent = this.loadGrantRecord(envelope, parentId);
      if (!parent) {
        throw new RunAuthorizationError(
          'RUN_GRANT_PARENT_INVALID',
          `Standing grant ${parentId} does not exist in this scope.`,
          { detail: { standing_parent_grant_id: parentId } },
        );
      }
      this.assertStandingCoverage(envelope, parent, preview, session, anchorProof, now);
    }

    // Effective envelope: the previewed ceilings, tightened by any
    // chosen ceilings and bounded by the standing parent's ceilings
    // (field-wise minimum: the parent is an outer bound, never a
    // broadening, and coverage was already proven above). Nothing in
    // an approval may loosen the preview the owner saw.
    let ceilings = tightenCeilings(preview.ceilings, decision.chosen_ceilings ?? null, previewId);
    if (parent) {
      ceilings = minCeilings(ceilings, parent.proof.ceilings);
    }
    let expiresAt = new Date(Date.parse(now) + this.grantTtlMs).toISOString();
    if (decision.chosen_expires_at) {
      if (Date.parse(decision.chosen_expires_at) > Date.parse(expiresAt)) {
        throw new RunAuthorizationError(
          'RUN_GRANT_WOULD_BROADEN',
          'A chosen expiry later than the default grant validity would broaden the approval. A stricter chosen limit wins; a looser one is refused.',
          { detail: { chosen_expires_at: decision.chosen_expires_at } },
        );
      }
      expiresAt = decision.chosen_expires_at;
    }
    if (parent && Date.parse(parent.expires_at) < Date.parse(expiresAt)) {
      expiresAt = parent.expires_at;
    }
    if (Date.parse(expiresAt) <= Date.parse(now)) {
      throw new RunAuthorizationError(
        'RUN_GRANT_PARENT_INVALID',
        'The resulting grant would already be expired (the standing parent or the chosen limit ends first). Approval is refused.',
        { detail: { preview_id: previewId } },
      );
    }

    const proof: RunGrantProof = {
      ...anchorProof,
      stage: 'granted',
      ceilings,
      revocation_epoch: session.state.revocation_generation,
      renews_grant_id: decision.renews_grant_id ?? null,
    };
    const actorRole =
      decision.authority_mode === 'local_interactive_owner'
        ? 'owner'
        : decision.authority_mode === 'managed_principal'
          ? 'managed_principal'
          : 'standing_grant';
    this.db.write((handle) => {
      const result = handle
        .prepare(
          `UPDATE council_approvals
              SET authority_mode = ?, actor_subject = ?, actor_role = ?,
                  parent_approval_id = ?, scope_proof = ?,
                  max_cost_minor = ?, currency = ?, status = 'active',
                  issued_at = ?, expires_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND status = 'expired'`,
        )
        .run(
          decision.authority_mode,
          principal.subject,
          actorRole,
          parent ? parent.grant_id : null,
          canonicalStringify(proof),
          ceilings.max_money?.amount_minor ?? null,
          ceilings.max_money?.currency ?? null,
          now,
          expiresAt,
          envelope.tenant_id,
          envelope.company_id,
          previewRow.grant_id,
        );
      if (Number(result.changes) !== 1) {
        throw new RunAuthorizationError(
          'RUN_PREVIEW_TAMPERED',
          `Preview ${previewId} changed state while approval was in flight. Approval is refused.`,
          { detail: { preview_id: previewId } },
        );
      }
      const event = this.repositories.journal.append(
        handle,
        envelope,
        session.spec.session_id,
        {
          event_id: this.ids.newId(),
          type: 'grant_issued',
          from_state: null,
          to_state: null,
          actor_subject: principal.subject,
          payload: {
            grant_kind: 'run_grant',
            lifecycle: 'approved',
            grant_id: previewRow.grant_id,
            preview_id: previewId,
            preview_sha256: preview.preview_sha256,
            authority_mode: decision.authority_mode,
            standing_parent_grant_id: parent ? parent.grant_id : null,
            renews_grant_id: decision.renews_grant_id ?? null,
            purpose: preview.purpose,
            expires_at: expiresAt,
          },
          created_at: now,
        },
      );
      this.repositories.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: session.spec.session_id,
        event_sequence: event.sequence,
        topic: 'run_authorization.grant_issued',
        idempotency_key: `run-authorization:grant:${previewRow.grant_id}:issued`,
        payload: {
          grant_id: previewRow.grant_id,
          session_id: session.spec.session_id,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
    });
    const grant = this.resolveRunGrant(envelope, previewRow.grant_id, session.spec.session_id);
    if (!grant) {
      throw new RunAuthorizationError(
        'RUN_GRANT_INACTIVE',
        `Grant ${previewRow.grant_id} was approved but does not resolve as active. The store is inconsistent; the grant must not be used.`,
        { detail: { grant_id: previewRow.grant_id } },
      );
    }
    return grant;
  }

  // ---------------------------------------------------------- resolveRunGrant

  /**
   * Resolve a grant reference to the canonical RunGrant, or null. Null
   * covers: unknown id, another scope's grant, a session mismatch, a
   * pre-approval preview anchor, a revoked grant, an expired grant
   * (lazily transitioned and journaled on first observation), a grant
   * whose standing parent no longer stands, and a grant fenced by the
   * session's revocation generation. Callers never learn which case
   * from this method; admission reports its own typed reason.
   */
  resolveRunGrant(
    envelope: AuthorizationEnvelope,
    grantRef: string,
    sessionId?: string,
    options: { mutate_on_expiry?: boolean } = {},
  ): RunGrant | null {
    const record = this.loadGrantRecord(envelope, grantRef);
    if (!record) return null;
    if (record.proof.stage !== 'granted') return null;
    // A standing authorization is not a session RunGrant: it satisfies
    // approvals through approveRun's coverage check, never by being
    // resolved as a grant for a session.
    if (record.proof.standing || record.session_id === null) return null;
    if (sessionId !== undefined && record.session_id !== sessionId) return null;
    if (record.status === 'revoked' || record.status === 'exhausted') return null;
    const now = this.clock.nowUtc();
    if (record.status === 'expired') return null;
    if (Date.parse(record.expires_at) <= Date.parse(now)) {
      // Read-only refusals (the WER-009 Start gate) pass
      // mutate_on_expiry: false so an expired authority refuses with
      // zero writes; the default keeps the lazy, journaled expiry
      // transition for resolve/admission callers.
      if (options.mutate_on_expiry !== false) {
        this.expireGrantIfLapsed(envelope, record);
      }
      return null;
    }
    if (record.session_id !== null) {
      const session = this.repositories.getSession(envelope, record.session_id);
      if (!session) return null;
      if (session.state.revocation_generation > record.proof.revocation_epoch) {
        return null;
      }
    }
    if (record.parent_grant_id) {
      const parent = this.loadGrantRecord(envelope, record.parent_grant_id);
      if (!parent || !this.standingParentStands(parent)) return null;
    }
    return this.toRunGrant(envelope, record);
  }

  // ----------------------------------------------------------- revokeRunGrant

  /**
   * Revoke a grant, durably and immediately: the row flip and the
   * grant_revoked journal event commit in one transaction, and every
   * later resolve or admission re-reads the row. Revoking an already
   * revoked or expired grant is reported, not re-journaled.
   */
  revokeRunGrant(
    envelope: AuthorizationEnvelope,
    grantId: string,
    revoker: TrustedPrincipal,
  ): { grant_id: string; status: GrantStatus; already_final: boolean } {
    assertEnvelopePurpose(envelope, 'write', 'Run grant revocation');
    this.assertPrincipalMatchesEnvelope(envelope, revoker);
    const record = this.loadGrantRecord(envelope, grantId);
    if (!record || record.proof.stage !== 'granted') {
      throw new RunAuthorizationError(
        'RUN_GRANT_NOT_FOUND',
        `No active run grant ${grantId} exists in this scope. Nothing was revoked.`,
        { detail: { grant_id: grantId } },
      );
    }
    if (record.session_id !== null) {
      const session = this.sessionFor(envelope, record.session_id);
      // Mutation rights: the owner of a private session, or an in-scope
      // principal for a company session. Support never revokes.
      assertSessionMutate(revoker, {
        scope: session.scope,
        visibility: session.spec.visibility,
      });
    } else if (
      revoker.subject !== record.issuer_principal &&
      revoker.channel !== 'local_owner'
    ) {
      throw new AuthorizationError(
        'COUNCIL_PERMISSION_DENIED',
        'A standing authorization can be revoked only by its issuer or the local owner.',
      );
    }
    if (record.status === 'revoked') {
      return { grant_id: grantId, status: 'revoked', already_final: true };
    }
    if (record.status === 'expired' || record.status === 'exhausted') {
      return { grant_id: grantId, status: record.status, already_final: true };
    }
    const now = this.clock.nowUtc();
    this.db.write((handle) => {
      const result = handle
        .prepare(
          `UPDATE council_approvals
              SET status = 'revoked', revoked_at = ?, revoked_by = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND status = 'active'`,
        )
        .run(now, revoker.subject, envelope.tenant_id, envelope.company_id, grantId);
      if (Number(result.changes) !== 1) {
        throw new RunAuthorizationError(
          'RUN_GRANT_INACTIVE',
          `Grant ${grantId} changed state while revocation was in flight.`,
          { detail: { grant_id: grantId } },
        );
      }
      if (record.session_id !== null) {
        const event = this.repositories.journal.append(
          handle,
          envelope,
          record.session_id,
          {
            event_id: this.ids.newId(),
            type: 'grant_revoked',
            from_state: null,
            to_state: null,
            actor_subject: revoker.subject,
            payload: {
              grant_kind: 'run_grant',
              lifecycle: 'revoked',
              grant_id: grantId,
              purpose: record.purpose,
            },
            created_at: now,
          },
        );
        this.repositories.outbox.enqueue(handle, envelope, {
          id: this.ids.newId(),
          session_id: record.session_id,
          event_sequence: event.sequence,
          topic: 'run_authorization.grant_revoked',
          idempotency_key: `run-authorization:grant:${grantId}:revoked`,
          payload: {
            grant_id: grantId,
            session_id: record.session_id,
            event_sequence: event.sequence,
          },
          created_at: now,
        });
      }
    });
    return { grant_id: grantId, status: 'revoked', already_final: false };
  }

  // ------------------------------------------- standing authorization records

  /**
   * Host provisioning for a PRE-EXISTING standing authorization (the
   * record approveRun's existing_standing_grant path verifies). This is
   * not one of the six canonical operations: standing authorizations are
   * created by host administration (managed tenant configuration or the
   * standalone owner's recorded standing instruction), never by a run
   * flow, and this method is the single write path for such a record.
   * A standing record binds scope, purpose, route policy, pack, a seat
   * allowlist, and ceilings; it can never authorize task creation or
   * external execution (Section 1.2: it is a council_run authorization
   * only, and its purpose field cannot name anything else).
   */
  provisionStandingAuthorization(
    envelope: AuthorizationEnvelope,
    input: StandingAuthorizationInput,
  ): RunGrantRecord {
    assertEnvelopePurpose(envelope, 'write', 'Standing authorization provisioning');
    this.assertPrincipalMatchesEnvelope(envelope, input.principal);
    this.assertCeilings(input.ceilings);
    const now = this.clock.nowUtc();
    if (Date.parse(input.expires_at) <= Date.parse(now)) {
      throw invalidInput('A standing authorization must expire in the future.');
    }
    const authorityMode: RunGrantAuthorityMode =
      input.principal.channel === 'local_owner'
        ? 'local_interactive_owner'
        : 'managed_principal';
    const grantId = this.ids.newId();
    const proof: RunGrantProof = {
      proof_version: 'run-grant-proof/v1',
      stage: 'granted',
      standing: true,
      installation_id: envelope.installation_id,
      owner_subject: input.principal.subject,
      route_policy_sha256: input.route_policy_sha256,
      route_snapshot: null,
      route_snapshot_fingerprint: null,
      brief_sha256: null,
      brief_revision: null,
      mode: null,
      pack_version: input.pack_version,
      protocol_version: CONTRACT_PACKAGE_VERSION,
      allowed_operation_kinds: this.allowedKinds(
        input.purpose,
        input.allowed_operation_kinds,
      ),
      ceilings: input.ceilings,
      account_ref: input.account_ref ?? null,
      preview_id: null,
      preview_sha256: null,
      revocation_epoch: 0,
      renews_grant_id: null,
    };
    this.db.write((handle) => {
      handle
        .prepare(
          `INSERT INTO council_approvals
             (tenant_id, company_id, id, kind, session_id, action_proposal_id,
              authority_mode, purpose, actor_subject, actor_role,
              parent_approval_id, scope_proof, current_plan_hash, verdict_hash,
              max_cost_minor, currency, seat_allowlist_json,
              company_scope_verified, status, issued_at, expires_at,
              revoked_at, revoked_by, consumed_at)
           VALUES (?, ?, ?, 'run_grant', NULL, NULL, ?, ?, ?, 'standing_authorization',
                   NULL, ?, NULL, NULL, ?, ?, ?, 1, 'active', ?, ?, NULL, NULL, NULL)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          grantId,
          authorityMode,
          input.purpose,
          input.principal.subject,
          canonicalStringify(proof),
          input.ceilings.max_money?.amount_minor ?? null,
          input.ceilings.max_money?.currency ?? null,
          canonicalStringify([...input.seat_ids]),
          now,
          input.expires_at,
        );
    });
    const record = this.loadGrantRecord(envelope, grantId);
    if (!record) {
      throw new RunAuthorizationError(
        'RUN_GRANT_NOT_FOUND',
        `Standing authorization ${grantId} was recorded but does not read back. The store is inconsistent.`,
        { detail: { grant_id: grantId } },
      );
    }
    return record;
  }

  // --------------------------------------------------------- shared internals

  /** Load one run_grant record in the envelope scope, or null. */
  loadGrantRecord(
    envelope: AuthorizationEnvelope,
    grantId: string,
  ): RunGrantRecord | null {
    const row = this.db.read((handle) =>
      this.approvalRow(handle, envelope, grantId),
    );
    if (!row) return null;
    const proof = parseProof(row);
    // The approvals table keys on tenant and company; the installation
    // binding lives in the proof and is enforced here, centrally: a
    // record bound to another installation is not found in this scope.
    if (proof.installation_id !== envelope.installation_id) return null;
    let seatIds: string[] = [];
    if (row.seat_allowlist_json) {
      try {
        const parsed = JSON.parse(row.seat_allowlist_json) as unknown;
        if (Array.isArray(parsed)) {
          seatIds = parsed.filter((s): s is string => typeof s === 'string');
        }
      } catch {
        seatIds = [];
      }
    }
    return {
      grant_id: row.id,
      session_id: row.session_id,
      authority_mode: row.authority_mode as RunGrantAuthorityMode,
      purpose: row.purpose as RunPurpose,
      issuer_principal: row.actor_subject,
      seat_ids: seatIds,
      status: row.status as GrantStatus,
      issued_at: row.issued_at,
      expires_at: row.expires_at,
      revoked_at: row.revoked_at,
      revoked_by: row.revoked_by,
      consumed_at: row.consumed_at,
      max_cost_minor: row.max_cost_minor,
      currency: row.currency,
      parent_grant_id: row.parent_approval_id,
      proof,
    };
  }

  /** The bound session, or a typed not-found refusal. */
  sessionFor(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): StoredSession {
    const session = this.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new RunAuthorizationError(
        'RUN_SESSION_NOT_FOUND',
        `Council session ${sessionId} does not exist in this scope, or is not visible to the envelope actor. The two cases are indistinguishable by design.`,
        { detail: { session_id: sessionId } },
      );
    }
    return session;
  }

  /**
   * Flip an active-but-lapsed grant to 'expired' and journal the
   * transition. Returns true when this call performed the transition.
   * Called on the resolve and admission paths, so expiry takes effect
   * at first observation and never depends on a sweep or a restart.
   */
  expireGrantIfLapsed(
    envelope: AuthorizationEnvelope,
    record: RunGrantRecord,
  ): boolean {
    const now = this.clock.nowUtc();
    if (record.status !== 'active') return false;
    if (Date.parse(record.expires_at) > Date.parse(now)) return false;
    let flipped = false;
    this.db.write((handle) => {
      const result = handle
        .prepare(
          `UPDATE council_approvals SET status = 'expired'
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND status = 'active'`,
        )
        .run(envelope.tenant_id, envelope.company_id, record.grant_id);
      flipped = Number(result.changes) === 1;
      if (flipped && record.session_id !== null) {
        const event = this.repositories.journal.append(
          handle,
          envelope,
          record.session_id,
          {
            event_id: this.ids.newId(),
            type: 'operation_completed',
            from_state: null,
            to_state: null,
            actor_subject: envelope.actor_subject,
            payload: {
              grant_kind: 'run_grant',
              lifecycle: 'expired',
              outcome: 'grant_expired',
              grant_id: record.grant_id,
              expires_at: record.expires_at,
            },
            created_at: now,
          },
        );
        this.repositories.outbox.enqueue(handle, envelope, {
          id: this.ids.newId(),
          session_id: record.session_id,
          event_sequence: event.sequence,
          topic: 'run_authorization.grant_expired',
          idempotency_key: `run-authorization:grant:${record.grant_id}:expired`,
          payload: {
            grant_id: record.grant_id,
            session_id: record.session_id,
            event_sequence: event.sequence,
          },
          created_at: now,
        });
      }
    });
    return flipped;
  }

  /** True when a standing parent currently stands (active, unexpired, granted stage). */
  standingParentStands(parent: RunGrantRecord): boolean {
    const nowIso = this.clock.nowUtc();
    return (
      parent.proof.standing &&
      parent.proof.stage === 'granted' &&
      parent.status === 'active' &&
      Date.parse(parent.expires_at) > Date.parse(nowIso)
    );
  }

  /**
   * Journal an admission refusal under its session (admission.ts calls
   * this in its own transaction, so the refusal is durable even though
   * the admission itself is refused). No-ops when the session does not
   * exist in scope: there is no journal to write to, and the typed
   * error still reaches the caller.
   */
  journalAdmissionRefused(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    detail: { grant_id: string | null; operation_id: string; code: string },
  ): void {
    const session = this.repositories.getSession(envelope, sessionId);
    if (!session) return;
    const now = this.clock.nowUtc();
    this.db.write((handle) => {
      const event = this.repositories.journal.append(handle, envelope, sessionId, {
        event_id: this.ids.newId(),
        type: 'operation_completed',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          grant_kind: 'run_grant',
          lifecycle: 'admission_refused',
          outcome: 'admission_refused',
          grant_id: detail.grant_id,
          operation_id: detail.operation_id,
          reason_code: detail.code,
        },
        created_at: now,
      });
      this.repositories.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: sessionId,
        event_sequence: event.sequence,
        topic: 'run_authorization.admission_refused',
        idempotency_key: `run-authorization:refused:${detail.operation_id}:${event.sequence}`,
        payload: {
          session_id: sessionId,
          operation_id: detail.operation_id,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
    });
  }

  /** Mark a grant's first consumption time (accounting bookkeeping). */
  markConsumed(envelope: AuthorizationEnvelope, grantId: string): void {
    const now = this.clock.nowUtc();
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_approvals SET consumed_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND consumed_at IS NULL`,
        )
        .run(now, envelope.tenant_id, envelope.company_id, grantId);
    });
  }

  // ------------------------------------------------------------ private parts

  private approvalRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    grantId: string,
  ): ApprovalRow | null {
    const row = handle
      .prepare(
        `SELECT ${APPROVAL_COLUMNS} FROM council_approvals
          WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'run_grant'`,
      )
      .get(envelope.tenant_id, envelope.company_id, grantId) as
      | ApprovalRow
      | undefined;
    return row ?? null;
  }

  private previewRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    previewId: string,
  ): PreviewRow | null {
    const row = handle
      .prepare(
        `SELECT id, session_id, grant_id, preview_json, preview_hash, expires_at, created_at
           FROM council_run_previews
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, previewId) as
      | PreviewRow
      | undefined;
    return row ?? null;
  }

  /** Recompute the preview hash from the stored JSON; tamper is a refusal. */
  private verifyPreviewRow(row: PreviewRow): RunPreview {
    let parsed: RunPreview;
    try {
      parsed = JSON.parse(row.preview_json) as RunPreview;
    } catch {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_TAMPERED',
        `Preview ${row.id} does not parse. Approval is refused.`,
        { detail: { preview_id: row.id } },
      );
    }
    const { preview_sha256: _recorded, ...content } = parsed;
    if (
      canonicalHash(content as unknown as Record<string, unknown>) !== row.preview_hash ||
      parsed.preview_sha256 !== row.preview_hash
    ) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_TAMPERED',
        `Preview ${row.id} content does not match its recorded hash. Approval is refused.`,
        { detail: { preview_id: row.id } },
      );
    }
    const check = validateRunPreview(parsed);
    if (!check.ok) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_TAMPERED',
        `Preview ${row.id} no longer satisfies the canonical RunPreview contract. Approval is refused.`,
        { detail: { preview_id: row.id } },
      );
    }
    return parsed;
  }

  /**
   * Freshness at approval: the preview must be inside its validity, and
   * every material input (brief revision and hash, mode, seats, pack,
   * scope, route pin) must still equal what the preview froze. Any
   * change stales the preview immediately (Section 25.6).
   */
  private assertPreviewFresh(
    envelope: AuthorizationEnvelope,
    preview: RunPreview,
    previewRow: PreviewRow,
    session: StoredSession,
    decision: ApproveRunDecision,
  ): void {
    const now = this.clock.nowUtc();
    if (Date.parse(preview.expires_at) <= Date.parse(now)) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_EXPIRED',
        `Preview ${preview.preview_id} expired at ${preview.expires_at}. Create a fresh preview; an expired preview cannot be approved.`,
        { detail: { preview_id: preview.preview_id } },
      );
    }
    const stale: string[] = [];
    if (canonicalHash(session.brief) !== preview.brief_sha256) stale.push('brief');
    if (session.brief.revision !== preview.brief_revision) stale.push('brief_revision');
    if (session.spec.mode !== preview.mode) stale.push('mode');
    if (canonicalStringify([...session.spec.seat_ids]) !== canonicalStringify([...preview.seat_ids])) {
      stale.push('seats');
    }
    if (session.spec.source_pack_version !== preview.pack_version) stale.push('pack');
    if (
      session.scope.tenant_id !== envelope.tenant_id ||
      session.scope.company_id !== envelope.company_id ||
      session.scope.installation_id !== envelope.installation_id
    ) {
      stale.push('scope');
    }
    if (decision.current_route_snapshot) {
      const anchor = this.db.read((handle) =>
        this.approvalRow(handle, envelope, previewRow.grant_id),
      );
      const pinned = anchor ? parseProof(anchor).route_snapshot_fingerprint : null;
      if (
        pinned !== null &&
        routeSnapshotFingerprint(decision.current_route_snapshot) !== pinned
      ) {
        stale.push('route');
      }
    }
    if (stale.length > 0) {
      throw new RunAuthorizationError(
        'RUN_PREVIEW_STALE',
        `Preview ${preview.preview_id} is stale: ${stale.join(', ')} changed since it was frozen. A material change invalidates the preview and any grant bound to it; create a fresh preview.`,
        { detail: { preview_id: preview.preview_id, changed: stale } },
      );
    }
  }

  /**
   * Standing coverage: the parent must stand in the same tenant and
   * company, bind the same installation, owner, purpose, route policy,
   * and pack, cover every requested seat, and carry ceilings at least
   * the previewed ones, field by field, in the same currency. A parent
   * that fails any field covers nothing (T141: no broader scope, ever).
   */
  private assertStandingCoverage(
    envelope: AuthorizationEnvelope,
    parent: RunGrantRecord,
    preview: RunPreview,
    session: StoredSession,
    anchorProof: RunGrantProof,
    nowIso: string,
  ): void {
    const fail = (reason: string): never => {
      throw new RunAuthorizationError(
        'RUN_GRANT_PARENT_INVALID',
        `Standing grant ${parent.grant_id} does not cover this preview: ${reason}.`,
        { detail: { standing_parent_grant_id: parent.grant_id, reason } },
      );
    };
    if (!this.standingParentStands(parent)) {
      fail('the standing grant is not active and unexpired');
    }
    if (parent.proof.installation_id !== envelope.installation_id) {
      fail('different installation');
    }
    if (parent.proof.owner_subject !== session.scope.owner_subject) {
      fail('different owner');
    }
    if (parent.purpose !== preview.purpose) fail('different purpose');
    if (parent.proof.route_policy_sha256 !== preview.route_policy_sha256) {
      fail('different route policy');
    }
    if (parent.proof.pack_version !== preview.pack_version) fail('different pack version');
    const parentSeats = new Set(parent.seat_ids);
    for (const seat of preview.seat_ids) {
      if (!parentSeats.has(seat)) fail(`seat ${seat} is outside the standing allowlist`);
    }
    const p = parent.proof.ceilings;
    const r = preview.ceilings;
    if (p.max_provider_requests < r.max_provider_requests) fail('request ceiling below the preview');
    if (p.max_output_repairs < r.max_output_repairs) fail('repair ceiling below the preview');
    if (p.max_transport_retries < r.max_transport_retries) fail('retry ceiling below the preview');
    if (
      r.max_input_tokens !== null &&
      (p.max_input_tokens === null || p.max_input_tokens < r.max_input_tokens)
    ) {
      fail('input token ceiling below the preview');
    }
    if (
      r.max_output_tokens !== null &&
      (p.max_output_tokens === null || p.max_output_tokens < r.max_output_tokens)
    ) {
      fail('output token ceiling below the preview');
    }
    if (r.max_money !== null) {
      const parentMoney = p.max_money;
      if (parentMoney === null) {
        fail('the standing grant carries no money bound');
      } else if (parentMoney.currency !== r.max_money.currency) {
        fail('different currency');
      } else if (parentMoney.amount_minor < r.max_money.amount_minor) {
        fail('money ceiling below the preview');
      }
    }
    for (const kind of anchorProof.allowed_operation_kinds) {
      if (!parent.proof.allowed_operation_kinds.includes(kind)) {
        fail(`operation kind ${kind} is outside the standing grant`);
      }
    }
  }

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
      throw new AuthorizationError(
        'COUNCIL_SCOPE_MISMATCH',
        'The authorization envelope does not match the trusted principal. Approval and revocation act only inside the principal that the host verified.',
      );
    }
  }

  private assertCeilings(ceilings: RunCeilings): void {
    for (const [name, value] of Object.entries({
      max_provider_requests: ceilings.max_provider_requests,
      max_output_repairs: ceilings.max_output_repairs,
      max_transport_retries: ceilings.max_transport_retries,
    })) {
      if (!Number.isSafeInteger(value) || value < 0) {
        throw invalidInput(`ceilings.${name} must be a safe integer >= 0.`);
      }
    }
    if (ceilings.max_money !== null) {
      if (
        !Number.isSafeInteger(ceilings.max_money.amount_minor) ||
        ceilings.max_money.amount_minor < 0 ||
        typeof ceilings.max_money.currency !== 'string' ||
        ceilings.max_money.currency.length === 0
      ) {
        throw invalidInput('ceilings.max_money must carry a safe integer amount_minor >= 0 and a currency.');
      }
    }
  }

  private allowedKinds(purpose: RunPurpose, requested?: string[]): string[] {
    const allowed = OPERATION_KINDS_BY_PURPOSE[purpose];
    if (!requested) return [...allowed];
    for (const kind of requested) {
      if (!allowed.includes(kind)) {
        throw invalidInput(
          `Operation kind ${kind} is not available to purpose ${purpose}.`,
        );
      }
    }
    return [...requested];
  }

  /**
   * Build the canonical RunGrant for an active record: the stored
   * binding plus live consumed and reserved counters derived from
   * CWE-028's reservation ledger for this grant (never a second
   * ledger: the counters are a read model over the reservation rows).
   */
  private toRunGrant(
    envelope: AuthorizationEnvelope,
    record: RunGrantRecord,
  ): RunGrant {
    const counters = this.grantCounters(envelope, record);
    const grant: RunGrant = {
      schema_version: 'wise-elders.run-grant/v1',
      grant_id: record.grant_id,
      authority_mode: record.authority_mode,
      issuer_principal: record.issuer_principal,
      scope: {
        tenant_id: envelope.tenant_id,
        company_id: envelope.company_id,
        installation_id: record.proof.installation_id,
        owner_subject: record.proof.owner_subject,
      },
      purpose: record.purpose,
      session_id: record.session_id as string,
      brief_revision: record.proof.brief_revision as number,
      brief_sha256: record.proof.brief_sha256 as string,
      mode: record.proof.mode as RunGrant['mode'],
      seat_ids: [...record.seat_ids] as RunGrant['seat_ids'],
      route_policy_sha256: record.proof.route_policy_sha256,
      account_ref: record.proof.account_ref,
      pack_version: record.proof.pack_version as string,
      protocol_version: record.proof.protocol_version,
      allowed_operation_kinds: [...record.proof.allowed_operation_kinds],
      ceilings: record.proof.ceilings,
      created_at: record.issued_at,
      expires_at: record.expires_at,
      revocation_epoch: record.proof.revocation_epoch,
      status: record.status,
      standing_parent_grant_id: record.parent_grant_id,
      preview_sha256: record.proof.preview_sha256 as string,
      consumed: counters.consumed,
      reserved: counters.reserved,
    };
    const check = validateRunGrant(grant);
    if (!check.ok) {
      throw new RunAuthorizationError(
        'RUN_INVALID_INPUT',
        `Stored grant ${record.grant_id} does not satisfy the canonical RunGrant contract: ${check.issues.map((i) => i.message).join('; ')}`,
        { detail: { grant_id: record.grant_id } },
      );
    }
    return grant;
  }

  private grantCounters(
    envelope: AuthorizationEnvelope,
    record: RunGrantRecord,
  ): {
    consumed: RunGrant['consumed'];
    reserved: RunGrant['reserved'];
  } {
    const consumed = { provider_requests: 0, output_repairs: 0, transport_retries: 0 };
    const reserved = { provider_requests: 0, output_repairs: 0, transport_retries: 0 };
    if (record.session_id === null) return { consumed, reserved };
    // Kind facts ride the operation_reserved journal events (the same
    // read model CWE-028's snapshot uses); reservation states ride the
    // reservation rows. Semantic verifications count toward the
    // provider_requests totals only: the contract counters carry no
    // semantic field, exactly as in CWE-028's snapshot.
    const kindByOperation = new Map<string, string>();
    for (const event of this.repositories.journal.list(envelope, record.session_id, 0)) {
      if (event.type !== 'operation_reserved') continue;
      if (typeof event.payload.operation_id === 'string') {
        kindByOperation.set(
          event.payload.operation_id,
          String(event.payload.kind ?? 'provider_request'),
        );
      }
    }
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT operation_id, state FROM council_budget_reservations
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND grant_id = ?`,
        )
        .all(
          envelope.tenant_id,
          envelope.company_id,
          record.session_id as string,
          record.grant_id,
        ),
    ) as Array<{ operation_id: string; state: string }>;
    const bump = (
      bucket: typeof consumed,
      kind: string | undefined,
    ): void => {
      bucket.provider_requests += 1;
      if (kind === 'output_repair') bucket.output_repairs += 1;
      if (kind === 'transport_retry') bucket.transport_retries += 1;
    };
    for (const row of rows) {
      const kind = kindByOperation.get(row.operation_id);
      if (row.state === 'committed' || row.state === 'unknown') bump(consumed, kind);
      else if (row.state === 'reserved') bump(reserved, kind);
    }
    return { consumed, reserved };
  }
}

// ------------------------------------------------------------------ helpers

function parseProof(row: ApprovalRow): RunGrantProof {
  try {
    return JSON.parse(row.scope_proof) as RunGrantProof;
  } catch {
    throw new RunAuthorizationError(
      'RUN_INVALID_INPUT',
      `Grant ${row.id} carries an unparseable scope proof. The record is not served.`,
      { detail: { grant_id: row.id } },
    );
  }
}

function anchorAuthorityModePlaceholder(): RunGrantAuthorityMode {
  // The anchor row must name an authority mode (schema CHECK). The
  // requester's channel decides nothing about approval authority, so
  // the anchor carries the neutral pre-approval value and approveRun
  // overwrites it with the verified mode. 'existing_standing_grant' is
  // never written here; the placeholder below is replaced at approval
  // and the row is 'expired' until then, so the value confers nothing.
  return 'managed_principal';
}

function previewRiskClass(ceilings: RunCeilings): 'low' | 'medium' | 'high' | 'critical' {
  // Display classification only; no decision reads it. Money unbounded
  // is the loudest risk a preview can show.
  if (ceilings.max_money === null) return 'high';
  if (ceilings.max_provider_requests >= 50) return 'medium';
  return 'low';
}

/** Field-wise minimum of two ceiling sets (the standing-parent merge). */
function minCeilings(a: RunCeilings, b: RunCeilings): RunCeilings {
  const num = (x: number, y: number): number => Math.min(x, y);
  const nullable = (x: number | null, y: number | null): number | null => {
    if (x === null) return y;
    if (y === null) return x;
    return Math.min(x, y);
  };
  let money = a.max_money;
  if (b.max_money !== null) {
    money =
      a.max_money === null
        ? b.max_money
        : {
            amount_minor: Math.min(a.max_money.amount_minor, b.max_money.amount_minor),
            currency: a.max_money.currency,
          };
  }
  return {
    max_provider_requests: num(a.max_provider_requests, b.max_provider_requests),
    max_output_repairs: num(a.max_output_repairs, b.max_output_repairs),
    max_transport_retries: num(a.max_transport_retries, b.max_transport_retries),
    max_input_tokens: nullable(a.max_input_tokens, b.max_input_tokens),
    max_output_tokens: nullable(a.max_output_tokens, b.max_output_tokens),
    max_money: money,
  };
}

/**
 * Tighten-only ceiling merge: every chosen field must be <= the base
 * field (and money must keep the base currency); anything looser is a
 * broadening and refused. Null token/money fields in the base cannot be
 * tightened into existence by a chosen value unless the chosen value
 * only ADDS a bound where none existed... which narrows, and is
 * allowed for tokens and money (a bound where none existed is stricter,
 * never broader).
 */
function tightenCeilings(
  base: RunCeilings,
  chosen: Partial<RunCeilings> | null,
  previewId: string,
): RunCeilings {
  if (!chosen) return base;
  const broaden = (field: string): never => {
    throw new RunAuthorizationError(
      'RUN_GRANT_WOULD_BROADEN',
      `Chosen ceilings would broaden ${field} beyond the approved preview. A stricter chosen limit wins; a looser one is refused.`,
      { detail: { preview_id: previewId, field } },
    );
  };
  const num = (
    field: string,
    baseValue: number,
    chosenValue: number | undefined,
  ): number => {
    if (chosenValue === undefined) return baseValue;
    if (chosenValue > baseValue) broaden(field);
    return chosenValue;
  };
  const nullableNum = (
    field: string,
    baseValue: number | null,
    chosenValue: number | null | undefined,
  ): number | null => {
    if (chosenValue === undefined) return baseValue;
    if (chosenValue === null) {
      if (baseValue !== null) broaden(field);
      return null;
    }
    if (baseValue !== null && chosenValue > baseValue) broaden(field);
    return chosenValue;
  };
  let money = base.max_money;
  if (chosen.max_money !== undefined) {
    if (chosen.max_money === null) {
      if (base.max_money !== null) broaden('max_money');
      money = null;
    } else if (base.max_money === null) {
      money = chosen.max_money;
    } else {
      if (chosen.max_money.currency !== base.max_money.currency) {
        broaden('max_money.currency');
      }
      if (chosen.max_money.amount_minor > base.max_money.amount_minor) {
        broaden('max_money');
      }
      money = chosen.max_money;
    }
  }
  return {
    max_provider_requests: num(
      'max_provider_requests',
      base.max_provider_requests,
      chosen.max_provider_requests,
    ),
    max_output_repairs: num(
      'max_output_repairs',
      base.max_output_repairs,
      chosen.max_output_repairs,
    ),
    max_transport_retries: num(
      'max_transport_retries',
      base.max_transport_retries,
      chosen.max_transport_retries,
    ),
    max_input_tokens: nullableNum(
      'max_input_tokens',
      base.max_input_tokens,
      chosen.max_input_tokens,
    ),
    max_output_tokens: nullableNum(
      'max_output_tokens',
      base.max_output_tokens,
      chosen.max_output_tokens,
    ),
    max_money: money,
  };
}
