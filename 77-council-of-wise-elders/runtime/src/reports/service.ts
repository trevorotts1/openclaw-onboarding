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
  assertCoverImageDataUri,
  assertRedactionComplete,
  buildReportModel,
  DEFAULT_ROUTE_DISPLAY,
  type RedactionProfile,
  type ReportContext,
} from './model.js';
import type { InstallationCapabilitySnapshot } from './capability-snapshot.js';
import {
  renderMarkdown,
  renderPrintHtml,
  renderRecordJson,
  sha256OfText,
  type SiblingArtifact,
} from './render.js';
import {
  isReportFormat,
  PDF_MISSING_PIECE,
  REPORT_FORMAT_REGISTRY,
  REPORT_FORMATS,
  reportFilename,
  reportFormatRegistry,
  type DeliverableRegistry,
  type ReportFormat,
} from './registry.js';
import { sha256OfBytes, type PdfRenderPort } from './pdf-renderer.js';
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
  /** CTR-146: the trusted installation binding for a capability snapshot. */
  installation_id?: string | null;
  /** CTR-146: recorded sitting-size provenance, when the host has it. */
  mode_selection?: {
    mode: string;
    source: 'client' | 'auto';
    reason: string;
  } | null;
  /** CTR-146: shipped seat descriptors (lane, owned question). */
  seat_descriptors?: Partial<
    Record<SeatId, { lane: string | null; owned_question: string | null }>
  >;
  /** CTR-146: this installation's own skills/departments, validated in the model. */
  capability_snapshot?: InstallationCapabilitySnapshot | null;
  /** CTR-146: compressed cover image derivative; asset wiring owns it. */
  cover_image_data_uri?: string | null;
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
  /** Exact bytes; base64 when `encoding` is base64 (PDF), else UTF-8 text. */
  bytes: string;
  encoding: 'utf8' | 'base64';
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
  /**
   * Host PDF renderer capability (directive Section 24.3). Bound only
   * when the host actually has a renderer; the pdf deliverable is
   * ready only when this port is present and its probe passes.
   */
  pdf?: PdfRenderPort;
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
  private readonly pdf: PdfRenderPort | undefined;

  constructor(deps: ReportExportServiceDeps) {
    this.journal = deps.journal;
    this.registry = deps.registry;
    this.liveness = deps.liveness;
    this.pdf = deps.pdf;
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

    // Format readiness: typed refusal naming the missing piece. PDF is
    // ready only when this host's renderer capability probe passes.
    const formats = reportFormatRegistry(this.pdfReadiness());
    for (const format of requestedFormats) {
      const descriptor = formats[format];
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
      installation_id: request.context.installation_id ?? null,
      mode_selection: request.context.mode_selection ?? null,
      seat_descriptors: request.context.seat_descriptors ?? {},
      capability_snapshot: request.context.capability_snapshot ?? null,
    };
    // CTR-146: the cover image is transport, not report content; validate
    // it once and hand it only to the print renderer.
    const coverImageDataUri = assertCoverImageDataUri(
      request.context.cover_image_data_uri ?? null,
    );
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
    // A redacted report never embeds image bytes: a redaction target
    // cannot be proven absent from compressed pixels, so the cover prints
    // the redaction note and no image at all (no portraits and no wordmark
    // band), rather than risk a leak or a false pass.
    const printHtml = renderPrintHtml(model, {
      cover_image_data_uri: redaction === null ? coverImageDataUri : null,
      // CTR-147: the frame and divider are generated decoration, but a
      // redacted export embeds no image bytes at all, so they are
      // explicitly disabled rather than left to the packaged default.
      frame_image_data_uri: redaction === null ? undefined : null,
      divider_image_data_uri: redaction === null ? undefined : null,
    });
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
    const rendered = new Map<
      ReportFormat,
      { bytes: string; encoding: 'utf8' | 'base64'; redaction_text: string }
    >();
    rendered.set('markdown', { bytes: markdown, encoding: 'utf8', redaction_text: markdown });
    rendered.set('print_html', { bytes: printHtml, encoding: 'utf8', redaction_text: printHtml });

    // PDF is the same print document, rendered to real PDF bytes by the
    // host renderer. No renderer means the readiness loop above already
    // refused; a renderer that fails is a typed EXPORT_RENDER_FAILED.
    if (requestedFormats.includes('pdf')) {
      const pdf = await this.renderPdf(printHtml);
      const pdfSha256 = sha256OfBytes(pdf);
      rendered.set('pdf', {
        bytes: pdf.toString('base64'),
        encoding: 'base64',
        // The PDF's own content is the print document it was made from.
        redaction_text: printHtml,
      });
      siblings.push({
        format: 'pdf',
        filename: reportFilename({
          session_id: request.session_id,
          verdict_revision: verdict.verdict_revision,
          format: 'pdf',
          redacted,
        }),
        sha256: pdfSha256,
        status: 'ready',
        missing_piece: null,
      });
    }
    if (requestedFormats.includes('record_json')) {
      const recordJson = renderRecordJson(model, siblings);
      rendered.set('record_json', {
        bytes: recordJson,
        encoding: 'utf8',
        redaction_text: recordJson,
      });
    }
    states.push('rendered');

    const artifacts: ExportedArtifact[] = [];
    for (const format of requestedFormats) {
      const entry = rendered.get(format);
      if (entry === undefined) continue;
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
        sha256:
          entry.encoding === 'base64'
            ? sha256OfBytes(Buffer.from(entry.bytes, 'base64'))
            : sha256OfText(entry.bytes),
        bytes: entry.bytes,
        encoding: entry.encoding,
        redacted,
        replayed: false,
      });
    }
    if (redaction !== null) {
      assertRedactionComplete(
        artifacts.map((a) => ({
          filename: a.filename,
          bytes: rendered.get(a.format)?.redaction_text ?? a.bytes,
        })),
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
        encoding: artifact.encoding,
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
    encoding: 'utf8' | 'base64';
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
      encoding: deliverable.encoding ?? 'utf8',
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

  /** Render the print document to real PDF bytes through the host. */
  private async renderPdf(printHtml: string): Promise<Buffer> {
    if (!this.pdf) {
      throw new ReportExportError(
        'EXPORT_FORMAT_NOT_READY',
        `The pdf deliverable is registered but not ready: ${PDF_MISSING_PIECE}.`,
        { missing_piece: PDF_MISSING_PIECE },
      );
    }
    return this.pdf.render(printHtml);
  }

  /** Host renderer readiness; a missing port is a missing renderer. */
  private pdfReadiness(): { pdf_available: boolean; pdf_detail?: string } {
    if (!this.pdf) return { pdf_available: false, pdf_detail: PDF_MISSING_PIECE };
    const capability = this.pdf.probe();
    return {
      pdf_available: capability.available,
      pdf_detail: capability.detail,
    };
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
