/**
 * The validated report export service (CWE-038, directive Section
 * 24; graph: consumes CWE-007 trusted-authorization-ports and the
 * CWE-026 deterministic-decision-validator).
 *
 * Pipeline, in order, for every export:
 * 1. Request shape: the idempotency request ID and the host-supplied
 *    export timestamp must be well formed.
 * 2. Authorization through the CWE-007 ports: the scope barrier and
 *    session visibility decision run first, exports of a private
 *    session are owner-only (a support read never includes export),
 *    and a machine principal must satisfy its approved binding for the
 *    'export' operation. Nothing renders for an unauthorized caller.
 * 3. Format readiness: a requested format that is registered not ready
 *    (PDF, pending the approved renderer) refuses with a typed error
 *    naming the missing piece.
 * 4. Currency: the verdict must be the session's current validated
 *    revision. An older revision is superseded and refuses; a revision
 *    ahead of the session record is invalid.
 * 5. Liveness: a session under a deletion tombstone refuses before any
 *    rendering, and again after rendering before anything is journaled
 *    or registered, so a deletion racing an active export cannot
 *    expose a deleted private artifact (T059).
 * 6. Validation: CWE-026 validateVerdictForPublication must return
 *    publishable for the exact revision, with final cards required for
 *    scored verdicts. Invalid or incomplete verdicts refuse with a
 *    typed error carrying the failed checks. No partial documents.
 * 7. Render: one model, all formats, byte-deterministic.
 * 8. Journal: one CWE-006 journal record per format (who, revision,
 *    format, hashes). A retry with the same request ID replays: the
 *    recorded artifact hash must match the re-rendered bytes, and no
 *    second journal record is written (export retry states, build
 *    step 4).
 * 9. Register: each artifact is registered as a deliverable bound to
 *    the session scope and the exact verdict revision (B15).
 *
 * Reads and deletes of registered deliverables recheck authorization
 * and liveness on every call (Section 24.4).
 */

import {
  isUtcTimestamp,
  isValidId,
  type CouncilCard,
  type DecisionBrief,
  type DraftResolution,
  type ScopeFields,
  type SeatId,
  type SessionVisibility,
  type Verdict,
} from '../contracts/index.js';
import {
  AuthorizationError,
  assertMachineBinding,
  checkSessionMutate,
  checkSessionRead,
  type MachineBinding,
  type TrustedPrincipal,
} from '../authorization/index.js';
import { validateVerdictForPublication } from '../protocol/verdict.js';
import {
  ReportExportError,
  exportRequestInvalid,
  sessionDeleted,
  verdictIncomplete,
  verdictInvalid,
  verdictSuperseded,
} from './errors.js';
import {
  assertRedactionComplete,
  buildReportModel,
  DEFAULT_ROUTE_DISPLAY,
  type RedactionProfile,
  type ReportContext,
} from './model.js';
import {
  renderMarkdown,
  renderPrintHtml,
  renderRecordJson,
  sha256OfText,
  type SiblingArtifact,
} from './render.js';
import {
  isReportFormat,
  REPORT_FORMAT_REGISTRY,
  REPORT_FORMATS,
  reportFilename,
  type DeliverableRegistry,
  type ReportFormat,
} from './registry.js';
import {
  exportEventId,
  type ExportJournalPort,
  type ExportJournalRecord,
  type SessionLivenessPort,
} from './journal.js';

export interface ReportExportContextInput {
  /** Host-supplied display date for the report header. */
  report_date: string;
  /** True when the session is a shipped sample session (F-047-1 badge). */
  sample?: boolean;
  session_mode?: string | null;
  route_display?: string;
  seat_qualifications?: Partial<Record<SeatId, string>>;
}

export interface ReportExportRequest {
  /** Idempotency key from the caller; retries reuse it (retry states). */
  request_id: string;
  principal: TrustedPrincipal;
  session_id: string;
  session_scope: ScopeFields;
  session_visibility: SessionVisibility;
  verdict: Verdict;
  brief: DecisionBrief;
  final_cards?: readonly CouncilCard[];
  draft_resolution?: DraftResolution;
  /** The session's current validated verdict revision, from the host's store. */
  current_verdict_revision: number;
  formats: readonly ReportFormat[] | 'all';
  redaction?: RedactionProfile | null;
  context: ReportExportContextInput;
  /** Host clock timestamp recorded in the journal and registry. */
  exported_at: string;
  machine_binding?: MachineBinding | null;
}

export interface ExportedArtifact {
  deliverable_id: string;
  format: ReportFormat;
  filename: string;
  media_type: string;
  sha256: string;
  bytes: string;
  redacted: boolean;
  /** True when this artifact was already journaled under the same request ID. */
  replayed: boolean;
}

export interface ReportExportResult {
  request_id: string;
  report_revision_id: string;
  session_id: string;
  verdict_revision: number;
  verdict_content_sha256: string;
  artifacts: ExportedArtifact[];
  /** Pipeline states reached, in order. */
  states: string[];
}

export interface ReportExportServiceDeps {
  journal: ExportJournalPort;
  registry: DeliverableRegistry;
  liveness?: SessionLivenessPort;
}

interface SessionTarget {
  scope: ScopeFields;
  visibility: SessionVisibility;
}

/**
 * The export access decision, composed from the CWE-007 ports. The
 * read decision supplies the scope barrier and visibility rule; export
 * then tightens private sessions to the owner alone, because export is
 * a disclosure beyond reading and the brief fixes private exports as
 * owner-only.
 */
export function checkExportAccess(
  principal: TrustedPrincipal,
  target: SessionTarget,
): 'owner' | 'company' {
  const decision = checkSessionRead(principal, target);
  if (!decision.allowed) {
    throw new AuthorizationError(decision.code, decision.message);
  }
  if (target.visibility === 'private' && decision.via !== 'owner') {
    throw new AuthorizationError(
      'COUNCIL_PRIVATE_OWNER_REQUIRED',
      'Private-session exports are owner-only. Access granted for another purpose (including support reads) does not include export.',
    );
  }
  return decision.via === 'owner' ? 'owner' : 'company';
}

function assertMachineExportBinding(
  principal: TrustedPrincipal,
  binding: MachineBinding | null | undefined,
  session_id: string,
): void {
  if (principal.channel !== 'machine') return;
  if (!binding) {
    throw new AuthorizationError(
      'COUNCIL_MACHINE_BINDING',
      'Machine principals must present their approved binding for export.',
    );
  }
  assertMachineBinding(principal, binding, 'export', session_id);
}

export class ReportExportService {
  private readonly journal: ExportJournalPort;
  private readonly registry: DeliverableRegistry;
  private readonly liveness: SessionLivenessPort | undefined;

  constructor(deps: ReportExportServiceDeps) {
    this.journal = deps.journal;
    this.registry = deps.registry;
    this.liveness = deps.liveness;
  }

  async exportReport(request: ReportExportRequest): Promise<ReportExportResult> {
    const states: string[] = [];
    if (!isValidId(request.request_id)) {
      throw exportRequestInvalid('request_id must be an opaque ID');
    }
    if (!isUtcTimestamp(request.exported_at)) {
      throw exportRequestInvalid('exported_at must be a UTC ISO 8601 timestamp');
    }
    const requestedFormats = this.resolveFormats(request.formats);

    // Authorization before any verdict work (CWE-007).
    const via = checkExportAccess(request.principal, {
      scope: request.session_scope,
      visibility: request.session_visibility,
    });
    assertMachineExportBinding(
      request.principal,
      request.machine_binding,
      request.session_id,
    );
    states.push('authorized');

    // Format readiness: typed refusal naming the missing piece.
    for (const format of requestedFormats) {
      const descriptor = REPORT_FORMAT_REGISTRY[format];
      if (descriptor.status === 'not_ready') {
        throw new ReportExportError(
          'EXPORT_FORMAT_NOT_READY',
          `The ${format} deliverable is registered but not ready: ${descriptor.missing_piece}.`,
          { missing_piece: descriptor.missing_piece ?? undefined },
        );
      }
    }

    const { verdict, brief } = request;
    if (
      verdict.session_id !== request.session_id ||
      brief.session_id !== request.session_id
    ) {
      throw verdictInvalid(
        'verdict and brief must belong to the session being exported',
        ['session_binding'],
      );
    }
    if (verdict.verdict_revision < request.current_verdict_revision) {
      throw verdictSuperseded(
        `verdict revision ${verdict.verdict_revision} is superseded by revision ${request.current_verdict_revision}; only the current validated revision may be exported`,
      );
    }
    if (verdict.verdict_revision > request.current_verdict_revision) {
      throw verdictInvalid(
        `verdict revision ${verdict.verdict_revision} is ahead of the session's current validated revision ${request.current_verdict_revision}`,
        ['revision_currency'],
      );
    }

    await this.assertSessionAlive(request.session_scope, request.session_id);

    const scored = verdict.result_kind === 'scored';
    if (scored && (!request.final_cards || request.final_cards.length === 0)) {
      throw verdictIncomplete(
        'a scored verdict export requires the final cards so CWE-026 can recompute the exact revision before anything renders',
      );
    }
    const validation = validateVerdictForPublication({
      verdict,
      brief,
      final_cards: request.final_cards ? [...request.final_cards] : undefined,
      draft_resolution: request.draft_resolution,
      require_final_cards: scored,
    });
    if (!validation.publishable) {
      const failed = validation.checks.filter((c) => c.status === 'fail');
      throw verdictInvalid(
        `verdict revision ${verdict.verdict_revision} failed CWE-026 publication validation: ${failed
          .map((c) => `${c.name}: ${c.detail}`)
          .join('; ')}`,
        failed.map((c) => c.name),
      );
    }
    states.push('validated');

    const context: ReportContext = {
      report_date: request.context.report_date,
      sample: request.context.sample === true,
      session_mode: request.context.session_mode ?? null,
      route_display: request.context.route_display ?? DEFAULT_ROUTE_DISPLAY,
      seat_qualifications: request.context.seat_qualifications ?? {},
    };
    const redaction = request.redaction ?? null;
    const model = buildReportModel({
      verdict,
      brief,
      final_cards: request.final_cards ?? [],
      context,
      redaction,
    });
    const report_revision_id = String(model.report_revision_id);
    const redacted = redaction !== null;

    // Render every ready format from the one model, even when only
    // some are requested: the record JSON binds the sibling hashes.
    const markdown = renderMarkdown(model);
    const printHtml = renderPrintHtml(model);
    const siblings: SiblingArtifact[] = [
      {
        format: 'markdown',
        filename: reportFilename({
          session_id: request.session_id,
          verdict_revision: verdict.verdict_revision,
          format: 'markdown',
          redacted,
        }),
        sha256: sha256OfText(markdown),
        status: 'ready',
        missing_piece: null,
      },
      {
        format: 'print_html',
        filename: reportFilename({
          session_id: request.session_id,
          verdict_revision: verdict.verdict_revision,
          format: 'print_html',
          redacted,
        }),
        sha256: sha256OfText(printHtml),
        status: 'ready',
        missing_piece: null,
      },
    ];
    const bytesByFormat = new Map<ReportFormat, string>();
    bytesByFormat.set('markdown', markdown);
    bytesByFormat.set('print_html', printHtml);
    if (requestedFormats.includes('record_json')) {
      bytesByFormat.set('record_json', renderRecordJson(model, siblings));
    }
    states.push('rendered');

    const artifacts: ExportedArtifact[] = [];
    for (const format of requestedFormats) {
      const bytes = bytesByFormat.get(format);
      if (bytes === undefined) continue;
      artifacts.push({
        deliverable_id: exportEventId(request.request_id, format),
        format,
        filename: reportFilename({
          session_id: request.session_id,
          verdict_revision: verdict.verdict_revision,
          format,
          redacted,
        }),
        media_type: REPORT_FORMAT_REGISTRY[format].media_type,
        sha256: sha256OfText(bytes),
        bytes,
        redacted,
        replayed: false,
      });
    }
    if (redaction !== null) {
      assertRedactionComplete(
        artifacts.map((a) => ({ filename: a.filename, bytes: a.bytes })),
        redaction,
      );
    }

    // Deletion race recheck (T059): after rendering, before exposure.
    await this.assertSessionAlive(request.session_scope, request.session_id);

    const actor: ExportJournalRecord['actor'] =
      via === 'owner'
        ? 'owner'
        : request.principal.channel === 'machine'
          ? 'system'
          : 'worker';
    for (const artifact of artifacts) {
      const existing = await this.journal.findExportRecord(
        request.session_id,
        artifact.deliverable_id,
      );
      if (existing) {
        if (
          existing.artifact_sha256 !== artifact.sha256 ||
          existing.verdict_content_sha256 !== verdict.content_sha256 ||
          existing.verdict_revision !== verdict.verdict_revision
        ) {
          throw new ReportExportError(
            'EXPORT_JOURNAL_MISMATCH',
            `request ${request.request_id} was already journaled for format ${artifact.format} with different content; refusing to attach this export to that record`,
          );
        }
        artifact.replayed = true;
      } else {
        await this.journal.appendExportRecord({
          export_id: artifact.deliverable_id,
          request_id: request.request_id,
          session_id: request.session_id,
          format: artifact.format,
          verdict_revision: verdict.verdict_revision,
          verdict_content_sha256: verdict.content_sha256,
          artifact_sha256: artifact.sha256,
          exporter_subject: request.principal.subject,
          via,
          actor,
          redacted,
          redaction_profile_id: redaction?.profile_id ?? null,
          created_at: request.exported_at,
        });
      }
      this.registry.register({
        deliverable_id: artifact.deliverable_id,
        request_id: request.request_id,
        session_id: request.session_id,
        scope: request.session_scope,
        visibility: request.session_visibility,
        format: artifact.format,
        filename: artifact.filename,
        media_type: artifact.media_type,
        bytes: artifact.bytes,
        sha256: artifact.sha256,
        verdict_revision: verdict.verdict_revision,
        verdict_content_sha256: verdict.content_sha256,
        report_revision_id,
        redacted,
        redaction_profile_id: redaction?.profile_id ?? null,
        registered_at: request.exported_at,
      });
    }
    states.push('journaled', 'registered');

    return {
      request_id: request.request_id,
      report_revision_id,
      session_id: request.session_id,
      verdict_revision: verdict.verdict_revision,
      verdict_content_sha256: verdict.content_sha256,
      artifacts,
      states,
    };
  }

  /**
   * Read one registered deliverable (B15). Authorization and session
   * liveness are rechecked on every read (Section 24.4, T059); a
   * missing deliverable and a deleted session never return bytes.
   */
  async readDeliverable(args: {
    principal: TrustedPrincipal;
    deliverable_id: string;
    machine_binding?: MachineBinding | null;
  }): Promise<{
    deliverable_id: string;
    format: ReportFormat;
    filename: string;
    media_type: string;
    sha256: string;
    bytes: string;
    verdict_revision: number;
    verdict_content_sha256: string;
  }> {
    const deliverable = this.registry.get(args.deliverable_id);
    if (!deliverable) {
      throw new ReportExportError(
        'EXPORT_DELIVERABLE_NOT_FOUND',
        `no registered deliverable ${args.deliverable_id}`,
      );
    }
    checkExportAccess(args.principal, {
      scope: deliverable.scope,
      visibility: deliverable.visibility,
    });
    assertMachineExportBinding(
      args.principal,
      args.machine_binding,
      deliverable.session_id,
    );
    await this.assertSessionAlive(deliverable.scope, deliverable.session_id);
    return {
      deliverable_id: deliverable.deliverable_id,
      format: deliverable.format,
      filename: deliverable.filename,
      media_type: deliverable.media_type,
      sha256: deliverable.sha256,
      bytes: deliverable.bytes,
      verdict_revision: deliverable.verdict_revision,
      verdict_content_sha256: deliverable.verdict_content_sha256,
    };
  }

  /** Delete one registered deliverable (B15). Mutation rules apply. */
  async deleteDeliverable(args: {
    principal: TrustedPrincipal;
    deliverable_id: string;
  }): Promise<boolean> {
    const deliverable = this.registry.get(args.deliverable_id);
    if (!deliverable) {
      throw new ReportExportError(
        'EXPORT_DELIVERABLE_NOT_FOUND',
        `no registered deliverable ${args.deliverable_id}`,
      );
    }
    const decision = checkSessionMutate(args.principal, {
      scope: deliverable.scope,
      visibility: deliverable.visibility,
    });
    if (!decision.allowed) {
      throw new AuthorizationError(decision.code, decision.message);
    }
    return this.registry.delete(args.deliverable_id);
  }

  private resolveFormats(
    formats: readonly ReportFormat[] | 'all',
  ): ReportFormat[] {
    const list = formats === 'all' ? [...REPORT_FORMATS] : [...formats];
    if (list.length === 0) {
      throw exportRequestInvalid('at least one export format is required');
    }
    for (const format of list) {
      if (!isReportFormat(format)) {
        throw new ReportExportError(
          'EXPORT_FORMAT_UNKNOWN',
          `unknown report format ${String(format)}`,
        );
      }
    }
    // Deterministic registry order, duplicates removed.
    return REPORT_FORMATS.filter((format) => list.includes(format));
  }

  private async assertSessionAlive(
    scope: ScopeFields,
    session_id: string,
  ): Promise<void> {
    if (!this.liveness) return;
    const deleted = await this.liveness.isSessionDeleted(scope, session_id);
    if (deleted) {
      throw sessionDeleted(
        `session ${session_id} is under a deletion tombstone; exports and deliverable reads are refused`,
      );
    }
  }
}

export function createReportExportService(
  deps: ReportExportServiceDeps,
): ReportExportService {
  return new ReportExportService(deps);
}
