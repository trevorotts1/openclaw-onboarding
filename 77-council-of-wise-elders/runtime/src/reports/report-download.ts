/**
 * Saved-session PDF download composition (CWE-038 PDF deliverable,
 * CTR-136).
 *
 * One composition serves `GET /council/<id>/report.pdf`:
 *
 *   saved session record  ->  the caller's own access boundary
 *   committed verdict     ->  CWE-026 publication validation
 *   frozen brief + cards  ->  the one report model
 *   print HTML            ->  host PDF renderer  ->  real PDF bytes
 *
 * Rules carried from CWE-038/CWE-050 and the CTR-136 requirement:
 * - the report is built ONLY from the saved record: no provider call,
 *   no model inference, no new spend, no re-scoring;
 * - a session that is not COMPLETED or has no validated verdict is
 *   refused with a typed, human-readable code instead of a document;
 * - every download rechecks authorization and the deletion tombstone
 *   through the composed export service before bytes are returned;
 * - missing historical fields stay exactly as the model renders them
 *   ("not recorded"/"none") — nothing is invented to fill a gap;
 * - no renderer on the host is EXPORT_FORMAT_NOT_READY, never an HTML
 *   or placeholder file served as `application/pdf`.
 *
 * This module never opens a database or resolves identity itself: the
 * caller binds the read functions, the trusted principal, the journal
 * port and the renderer.
 */

import type { TrustedPrincipal } from '../authorization/index.js';
import type { CouncilCard, ScopeFields, SeatId, Verdict } from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { InstallationCapabilitySnapshot } from './capability-snapshot.js';
import { loadSeatDescriptors } from './seat-descriptors.js';
import {
  ReportExportError,
  ReportExportService,
  type DeliverableRegistry,
  type ExportJournalPort,
  type ExportJournalRecord,
  type PdfRenderPort,
  type ReportDeliverable,
  type ReportFormat,
} from './index.js';

/** One served PDF download. */
export interface CouncilReportDownload {
  session_id: string;
  bytes: Buffer;
  filename: string;
  media_type: 'application/pdf';
  sha256: string;
  verdict_content_sha256: string;
  verdict_revision: number;
  report_revision_id: string;
}

/** A typed refusal the front door turns into a JSON status response. */
export interface CouncilReportDownloadRefusal {
  ok: false;
  status: number;
  code: string;
  detail: string;
  recovery: string;
}

export type CouncilReportDownloadResult =
  | ({ ok: true } & CouncilReportDownload)
  | CouncilReportDownloadRefusal;

export interface CouncilReportDownloadPort {
  readPdf(args: { session_id: string }): Promise<CouncilReportDownloadResult>;
}

export interface CouncilReportDownloadDeps {
  readSession(sessionId: string): StoredSession | null;
  listCards(sessionId: string): CouncilCard[];
  readVerdict(sessionId: string): Verdict | null;
  isSessionDeleted(scope: ScopeFields, sessionId: string): boolean;
  journal: ExportJournalPort;
  principal: TrustedPrincipal;
  pdf: PdfRenderPort;
  nowUtc(): string;
  /** Override the per-download export request ID (tests, callers). */
  requestIdFor?(sessionId: string, verdictRevision: number): string;
  /**
   * CTR-146: this installation's own skills/departments for the reader
   * section. Supplied by the caller that owns the sitting (see
   * `discoverInstallationCapabilities`), because only that caller knows
   * the snapshot belongs to this session's installation. Omitted or
   * `false` means the report says the inventory was not recorded — it
   * never guesses one from whatever box happens to run the download.
   */
  capabilitySnapshot?:
    | ((args: {
        installationId: string | null;
        capturedAt: string;
      }) => InstallationCapabilitySnapshot | null)
    | false;
  /** CTR-146: recorded sitting-size provenance, when the host stores it. */
  modeSelection?(sessionId: string):
    | { mode: string; source: 'client' | 'auto'; reason: string }
    | null;
  /** CTR-146: shipped seat descriptors; defaults to the advisor profiles. */
  seatDescriptors?(): Partial<
    Record<SeatId, { lane: string | null; owned_question: string | null }>
  >;
  /** CTR-146: compressed cover image derivative, supplied by asset wiring. */
  coverImageDataUri?(): string | null;
}

/**
 * Latest-per-session deliverable registry. The service registers one
 * artifact per export request; a local download endpoint would
 * otherwise accumulate every rendered PDF for the process lifetime.
 * Reads still go through the service's authorization recheck.
 */
class LatestPerSessionDeliverableRegistry implements DeliverableRegistry {
  private readonly bySessionFormat = new Map<string, ReportDeliverable>();

  private key(deliverable: Pick<ReportDeliverable, 'session_id' | 'format'>): string {
    return `${deliverable.session_id}\u0000${deliverable.format}`;
  }

  register(deliverable: ReportDeliverable): void {
    this.bySessionFormat.set(this.key(deliverable), deliverable);
  }

  get(deliverable_id: string): ReportDeliverable | null {
    for (const deliverable of this.bySessionFormat.values()) {
      if (deliverable.deliverable_id === deliverable_id) return deliverable;
    }
    return null;
  }

  delete(deliverable_id: string): boolean {
    for (const [key, deliverable] of this.bySessionFormat) {
      if (deliverable.deliverable_id === deliverable_id) {
        this.bySessionFormat.delete(key);
        return true;
      }
    }
    return false;
  }

  listForSession(session_id: string): ReportDeliverable[] {
    return [...this.bySessionFormat.values()].filter((d) => d.session_id === session_id);
  }
}

function refusal(
  status: number,
  code: string,
  detail: string,
  recovery: string,
): CouncilReportDownloadRefusal {
  return { ok: false, status, code, detail, recovery };
}

function mapExportError(error: unknown, sessionId: string): CouncilReportDownloadRefusal {
  if (error instanceof ReportExportError) {
    switch (error.code) {
      case 'EXPORT_FORMAT_NOT_READY':
        return refusal(
          503,
          'REPORT_RENDERER_UNAVAILABLE',
          error.message,
          'Install a headless Chrome/Chromium or the CUPS PDF filter on this box, or set CHROME_PATH, then retry the download.',
        );
      case 'EXPORT_RENDER_FAILED':
        return refusal(
          502,
          'REPORT_RENDER_FAILED',
          error.message,
          'The renderer ran but produced no valid PDF. Retry once; if it persists, report the renderer name and version.',
        );
      case 'EXPORT_SESSION_DELETED':
        return refusal(
          410,
          'REPORT_SESSION_DELETED',
          error.message,
          'This session was deleted; its report is no longer available.',
        );
      case 'EXPORT_JOURNAL_MISMATCH':
        return refusal(
          409,
          'REPORT_EXPORT_CONFLICT',
          error.message,
          'Retry the download; a new export record is written for the new bytes.',
        );
      case 'EXPORT_REDACTION_INCOMPLETE':
        return refusal(
          422,
          'REPORT_REDACTION_INCOMPLETE',
          error.message,
          'Fix the redaction profile and retry the export.',
        );
      case 'EXPORT_VERDICT_INCOMPLETE':
      case 'EXPORT_VERDICT_INVALID':
      case 'EXPORT_VERDICT_SUPERSEDED':
        return refusal(
          409,
          'REPORT_VERDICT_NOT_EXPORTABLE',
          error.message,
          'Only a current verdict that passes publication validation can be downloaded.',
        );
      case 'EXPORT_DELIVERABLE_NOT_FOUND':
        return refusal(
          404,
          'REPORT_DELIVERABLE_NOT_FOUND',
          error.message,
          'Request the report again with the session id; a fresh export is rendered from the saved record.',
        );
      default:
        return refusal(400, error.code, error.message, 'Correct the request and retry.');
    }
  }
  if (error instanceof Error && error.name === 'AuthorizationError') {
    return refusal(
      403,
      'REPORT_ACCESS_DENIED',
      error.message,
      'Use the owner session for this private council report.',
    );
  }
  return refusal(
    500,
    'REPORT_INTERNAL',
    error instanceof Error ? error.message : `report export for ${sessionId} failed`,
    'Check the service log, then retry the download.',
  );
}

/** True when a session record has reached its completed sitting. */
export function isCompletedSession(session: StoredSession): boolean {
  return session.state.state === 'COMPLETED';
}

/**
 * Compose the PDF download port over the saved session record and the
 * unchanged CWE-038 export pipeline.
 */
export function composeCouncilReportDownload(
  deps: CouncilReportDownloadDeps,
): CouncilReportDownloadPort {
  const service = new ReportExportService({
    journal: deps.journal,
    registry: new LatestPerSessionDeliverableRegistry(),
    pdf: deps.pdf,
    liveness: {
      isSessionDeleted(scope: ScopeFields, session_id: string) {
        return deps.isSessionDeleted(scope, session_id);
      },
    },
  });

  return {
    async readPdf(args: { session_id: string }): Promise<CouncilReportDownloadResult> {
      const sessionId = args.session_id;
      const session = deps.readSession(sessionId);
      if (session === null) {
        return refusal(
          404,
          'SESSION_NOT_FOUND',
          `No durable council session ${sessionId} is known to the composed store.`,
          'Admit the session through POST /api/council/admissions, then use the session id the store returned.',
        );
      }
      if (!isCompletedSession(session)) {
        return refusal(
          409,
          'REPORT_SESSION_NOT_COMPLETE',
          `Session ${sessionId} is ${session.state.state}; a PDF report is produced only for a COMPLETED sitting with a validated verdict.`,
          'Open the session in the chamber and wait for the council to complete; the report link appears then.',
        );
      }
      const verdict = deps.readVerdict(sessionId);
      if (verdict === null) {
        return refusal(
          409,
          'REPORT_SESSION_NOT_COMPLETE',
          `Session ${sessionId} is COMPLETED but carries no validated verdict; there is no decision to report.`,
          'Re-run the council or open the session in the chamber to see its recorded state.',
        );
      }

      const exportedAt = deps.nowUtc();
      const requestId =
        deps.requestIdFor?.(sessionId, verdict.verdict_revision) ??
        `report-${sessionId}-r${verdict.verdict_revision}-${exportedAt.replace(/[^A-Za-z0-9._:-]/g, '-')}`;
      // CTR-146: only a caller-supplied snapshot is attached. `false` or
      // absent means the reader section reports the inventory as not
      // recorded; the download never reads a catalog it cannot bind.
      const snapshotProvider =
        deps.capabilitySnapshot === false || deps.capabilitySnapshot === undefined
          ? null
          : deps.capabilitySnapshot;

      try {
        const result = await service.exportReport({
          request_id: requestId,
          principal: deps.principal,
          session_id: sessionId,
          session_scope: session.scope,
          session_visibility: session.spec.visibility,
          verdict,
          brief: session.brief,
          final_cards: deps.listCards(sessionId),
          current_verdict_revision: verdict.verdict_revision,
          formats: ['pdf'],
          context: {
            // The report date is the host's export date; the verdict's own
            // revision and hashes identify the recorded decision exactly.
            report_date: exportedAt.slice(0, 10),
            sample: session.sample,
            session_mode: session.spec.mode,
            installation_id: session.scope.installation_id,
            mode_selection: deps.modeSelection?.(sessionId) ?? null,
            seat_descriptors: (deps.seatDescriptors ?? loadSeatDescriptors)(),
            capability_snapshot:
              snapshotProvider === null
                ? null
                : snapshotProvider({
                    installationId: session.scope.installation_id,
                    capturedAt: exportedAt,
                  }),
            cover_image_data_uri: deps.coverImageDataUri?.() ?? null,
          },
          exported_at: exportedAt,
        });
        const artifact = result.artifacts.find((entry) => entry.format === 'pdf');
        if (!artifact) {
          return refusal(
            500,
            'REPORT_INTERNAL',
            'the export pipeline produced no pdf artifact',
            'Report this as a defect; no document was served.',
          );
        }
        const bytes = Buffer.from(artifact.bytes, artifact.encoding);
        return {
          ok: true,
          session_id: sessionId,
          bytes,
          filename: artifact.filename,
          media_type: 'application/pdf',
          sha256: artifact.sha256,
          verdict_content_sha256: result.verdict_content_sha256,
          verdict_revision: result.verdict_revision,
          report_revision_id: result.report_revision_id,
        };
      } catch (error) {
        return mapExportError(error, sessionId);
      }
    },
  };
}

/** One committed event the download journal appends. */
export interface RepositoryEventAppendInput {
  event_id: string;
  type: 'operation_completed';
  payload: Record<string, unknown>;
  created_at: string;
}

/** One committed event row the download journal reads back. */
export interface RepositoryEventRow {
  event_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

/**
 * ExportJournalPort over the canonical repository journal. The payload
 * convention is the one CWE-038 established (operation_completed with
 * payload kind 'report_export'), so a report download is journaled in
 * the same vocabulary as every other export, with the same hash chain.
 */
export function createRepositoryExportJournal(args: {
  envelope: AuthorizationEnvelope;
  appendEvent(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    input: RepositoryEventAppendInput,
  ): unknown;
  listEvents(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    afterSequence?: number,
  ): readonly RepositoryEventRow[];
}): ExportJournalPort {
  const { envelope, appendEvent, listEvents } = args;
  return {
    async appendExportRecord(record: ExportJournalRecord): Promise<void> {
      appendEvent(envelope, record.session_id, {
        event_id: record.export_id,
        type: 'operation_completed',
        payload: {
          kind: 'report_export',
          request_id: record.request_id,
          format: record.format,
          verdict_revision: record.verdict_revision,
          verdict_content_sha256: record.verdict_content_sha256,
          artifact_sha256: record.artifact_sha256,
          exporter_subject: record.exporter_subject,
          via: record.via,
          redacted: record.redacted,
          redaction_profile_id: record.redaction_profile_id,
        },
        created_at: record.created_at,
      });
    },
    async findExportRecord(
      session_id: string,
      export_id: string,
    ): Promise<ExportJournalRecord | null> {
      const events = listEvents(envelope, session_id, 0);
      const event = events.find((entry) => entry.event_id === export_id);
      if (!event) return null;
      const payload = event.payload;
      if (payload.kind !== 'report_export') return null;
      return {
        export_id,
        request_id: String(payload.request_id ?? ''),
        session_id,
        format: payload.format as ReportFormat,
        verdict_revision: Number(payload.verdict_revision ?? 0),
        verdict_content_sha256: String(payload.verdict_content_sha256 ?? ''),
        artifact_sha256: String(payload.artifact_sha256 ?? ''),
        exporter_subject: String(payload.exporter_subject ?? ''),
        via: payload.via === 'owner' ? 'owner' : 'company',
        actor: 'owner',
        redacted: payload.redacted === true,
        redaction_profile_id:
          typeof payload.redaction_profile_id === 'string'
            ? payload.redaction_profile_id
            : null,
        created_at: event.created_at,
      };
    },
  };
}
