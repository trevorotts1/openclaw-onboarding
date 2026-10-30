/**
 * CLI report export composition (CWE-050; B15's portable half):
 * rewires the standalone `export` command to CWE-038's validated
 * ReportExportService. Exports are produced ONLY from a verdict
 * revision that passes CWE-026 publication validation, journaled into
 * the host store's event journal (operation_completed with payload
 * kind 'report_export', the frozen-vocabulary convention CWE-038
 * established), and registered as deliverables bound to the exact
 * verdict revision and content hash. PDF is rendered from the same
 * print HTML by the host renderer capability (`createHostPdfRenderer`):
 * on a host with no renderer the service refuses with
 * EXPORT_FORMAT_NOT_READY naming the missing piece; a renderer that
 * fails is EXPORT_RENDER_FAILED. No PDF is faked and HTML is never
 * written with a .pdf name.
 *
 * The deliverable registry here is process-scoped (the standalone CLI
 * is one export per process); the journal record in the store is the
 * durable deliverable record, and its event ID is the deliverable ID,
 * readable back through findExportRecord. The authenticated durable
 * download path for managed hosts is the Command Center stream's
 * composition (CWE-050 CC), over the same service.
 */

import { SCHEMA_VERSIONS } from '../contracts/index.js';
import type { TrustedPrincipal } from '../authorization/index.js';
import {
  createHostPdfRenderer,
  discoverInstallationCapabilities,
  InMemoryDeliverableRegistry,
  loadSeatDescriptors,
  ReportExportError,
  ReportExportService,
  type ExportJournalPort,
  type ExportJournalRecord,
  type ReportFormat,
} from '../reports/index.js';
import { CouncilError } from './errors.js';
import { openclawRoot } from './paths.js';
import type { CouncilStore, StoredSession } from './host-ports.js';
import type { Verdict } from '../contracts/index.js';

/**
 * ExportJournalPort over the CWE-004 CouncilStore port (satisfied by
 * both the standalone LocalSqliteStore and CWE-006's
 * CouncilStoreService), with the same payload convention as CWE-038's
 * createCwe006ExportJournal.
 */
export function createStoreExportJournal(
  store: CouncilStore,
  scope: { tenant_id: string; company_id: string },
): ExportJournalPort {
  return {
    async appendExportRecord(record: ExportJournalRecord): Promise<void> {
      await store.appendEvent({
        schema_version: SCHEMA_VERSIONS.event,
        event_id: record.export_id,
        session_id: record.session_id,
        event_type: 'operation_completed',
        tenant_id: scope.tenant_id,
        company_id: scope.company_id,
        owner_subject: null,
        actor: record.actor,
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
      const events = await store.listEvents(session_id);
      const event = events.find((e) => e.event_id === export_id);
      if (!event) return null;
      const payload = event.payload as Record<string, unknown>;
      return {
        export_id,
        request_id: String(payload.request_id),
        session_id,
        format: payload.format as ReportFormat,
        verdict_revision: Number(payload.verdict_revision),
        verdict_content_sha256: String(payload.verdict_content_sha256),
        artifact_sha256: String(payload.artifact_sha256),
        exporter_subject: String(payload.exporter_subject),
        via: payload.via as 'owner' | 'company',
        actor: event.actor,
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

/** Compose CWE-038's service over a standalone host store. */
export function composeLocalReportExportService(
  store: CouncilStore,
  scope: { tenant_id: string; company_id: string },
): ReportExportService {
  return new ReportExportService({
    journal: createStoreExportJournal(store, scope),
    registry: new InMemoryDeliverableRegistry(),
    // Host renderer capability: ready where the host has one, an honest
    // EXPORT_FORMAT_NOT_READY naming the missing piece where it does not.
    pdf: createHostPdfRenderer(),
  });
}

export type CliExportFormat = 'md' | 'json' | 'pdf';

const FORMAT_MAP: Record<CliExportFormat, ReportFormat> = {
  md: 'markdown',
  json: 'record_json',
  pdf: 'pdf',
};

/**
 * Export one session's validated verdict through the composed
 * service. ReportExportError surfaces as a CouncilError mapped onto
 * the CLI's stable vocabulary (the service code stays in the
 * message): EXPORT_FORMAT_NOT_READY becomes COUNCIL_FEATURE_NOT_READY
 * naming CWE-044's missing renderer, so the dispatcher's error
 * envelope stays truthful.
 */
export async function exportVerdictReport(args: {
  store: CouncilStore;
  session: StoredSession;
  verdict: Verdict;
  format: CliExportFormat;
  requestId: string;
  exportedAt: string;
}): Promise<{
  deliverable_id: string;
  format: ReportFormat;
  filename: string;
  sha256: string;
  bytes: string;
  /** utf8 for text formats, base64 for the binary PDF artifact. */
  encoding: 'utf8' | 'base64';
  verdict_content_sha256: string;
}> {
  const service = composeLocalReportExportService(args.store, args.session.scope);
  const principal: TrustedPrincipal = {
    tenant_id: args.session.scope.tenant_id,
    company_id: args.session.scope.company_id,
    installation_id: args.session.scope.installation_id,
    subject: args.session.scope.owner_subject ?? 'local-owner',
    channel: 'local_owner',
    support_access: false,
  };
  try {
    const result = await service.exportReport({
      request_id: args.requestId,
      principal,
      session_id: args.session.spec.session_id,
      session_scope: args.session.scope,
      session_visibility: args.session.spec.visibility,
      verdict: args.verdict,
      brief: args.session.brief,
      final_cards: await args.store.listCards(args.session.spec.session_id),
      current_verdict_revision: args.verdict.verdict_revision,
      formats: [FORMAT_MAP[args.format]],
      context: {
        report_date: args.exportedAt.slice(0, 10),
        // F-047-1 (CWE-048): the stored session's sample flag rides into
        // the export so sample exports carry the SAMPLE badge.
        sample: args.session.sample,
        // CTR-146: the reader-facing sections. The capability snapshot is
        // read from this box's own OpenClaw folders (names/descriptions
        // only); it is bound to this session's installation by the model.
        installation_id: args.session.scope.installation_id,
        seat_descriptors: loadSeatDescriptors(),
        capability_snapshot: discoverInstallationCapabilities({
          openclaw_root: openclawRoot(),
          installation_id: args.session.scope.installation_id,
          captured_at: args.exportedAt.slice(0, 10),
        }),
      },
      exported_at: args.exportedAt,
    });
    const artifact = result.artifacts[0];
    return {
      deliverable_id: artifact.deliverable_id,
      format: artifact.format,
      filename: artifact.filename,
      sha256: artifact.sha256,
      bytes: artifact.bytes,
      encoding: artifact.encoding,
      verdict_content_sha256: result.verdict_content_sha256,
    };
  } catch (error) {
    if (error instanceof ReportExportError) {
      // Map onto the CLI's stable error vocabulary (CWE-049's
      // toCouncilError precedent): the service code stays in the
      // message; PDF's not-ready is the CLI's FEATURE_NOT_READY.
      throw new CouncilError(
        error.code === 'EXPORT_FORMAT_NOT_READY'
          ? 'COUNCIL_FEATURE_NOT_READY'
          : 'COUNCIL_STATE_CONFLICT',
        `${error.message} [${error.code}]`,
        { retryable: false, exitCode: 3 },
      );
    }
    if (error instanceof Error && error.name === 'AuthorizationError') {
      throw new CouncilError('COUNCIL_STATE_CONFLICT', error.message, {
        retryable: false,
        exitCode: 3,
      });
    }
    throw error;
  }
}
