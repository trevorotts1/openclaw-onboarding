/**
 * Export journaling (CWE-038, brief scope point 4; directive Sections
 * 16.2, 18).
 *
 * Every export writes one journal record per format through the
 * CWE-006 event journal on the stack: who exported (exporter subject
 * and access path), what verdict revision and content hash, what
 * format, and the artifact's own content hash.
 *
 * Vocabulary note: the frozen CWE-003 event vocabulary has no
 * export-specific event type, and the council_events table enforces
 * that vocabulary with a CHECK constraint. An export is therefore
 * journaled as an 'operation_completed' event whose payload carries
 * kind 'report_export' and the full export record. Adding a dedicated
 * event type is a CWE-003 contract amendment for integration to
 * consider; this unit does not modify the frozen contracts.
 */

import { SCHEMA_VERSIONS, type ScopeFields } from '../contracts/index.js';
import type { CouncilStoreService } from '../persistence/store.js';
import type { ReportFormat } from './registry.js';

export interface ExportJournalRecord {
  /** Journal event ID; also the deliverable ID. Deterministic per request and format. */
  export_id: string;
  request_id: string;
  session_id: string;
  format: ReportFormat;
  verdict_revision: number;
  verdict_content_sha256: string;
  artifact_sha256: string;
  exporter_subject: string;
  /** How CWE-007 granted access: 'owner' or 'company'. */
  via: 'owner' | 'company';
  actor: 'owner' | 'system' | 'worker' | 'chair';
  redacted: boolean;
  redaction_profile_id: string | null;
  created_at: string;
}

export interface ExportJournalPort {
  appendExportRecord(record: ExportJournalRecord): Promise<void>;
  findExportRecord(
    session_id: string,
    export_id: string,
  ): Promise<ExportJournalRecord | null>;
}

/** The journal event ID for one export of one format under one request. */
export function exportEventId(request_id: string, format: ReportFormat): string {
  return `export-${request_id}-${format}`;
}

function recordFromPayload(
  payload: Record<string, unknown>,
  session_id: string,
  export_id: string,
  created_at: string,
): ExportJournalRecord | null {
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
    actor:
      payload.actor === 'owner' ||
      payload.actor === 'system' ||
      payload.actor === 'chair'
        ? payload.actor
        : 'worker',
    redacted: payload.redacted === true,
    redaction_profile_id:
      typeof payload.redaction_profile_id === 'string'
        ? payload.redaction_profile_id
        : null,
    created_at,
  };
}

/**
 * The CWE-006 adapter: appends through CouncilStoreService.appendEvent
 * (the composed store's journal port) and reads back through
 * listEvents, which is per-session by construction. The journal row's
 * actor_subject is the composing host's service identity per the
 * CWE-006 port semantics; the export record itself, including the
 * exporter subject, is the event payload.
 */
export function createCwe006ExportJournal(
  store: CouncilStoreService,
  scope: { tenant_id: string; company_id: string },
): ExportJournalPort {
  return {
    async appendExportRecord(record) {
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
          actor: record.actor,
          redacted: record.redacted,
          redaction_profile_id: record.redaction_profile_id,
        },
        created_at: record.created_at,
      });
    },
    async findExportRecord(session_id, export_id) {
      const events = await store.listEvents(session_id);
      const event = events.find((e) => e.event_id === export_id);
      if (!event) return null;
      return recordFromPayload(
        event.payload as Record<string, unknown>,
        session_id,
        export_id,
        event.created_at,
      );
    },
  };
}

/** In-memory journal for tests and standalone composition. */
export class InMemoryExportJournal implements ExportJournalPort {
  private readonly byId = new Map<string, ExportJournalRecord>();

  async appendExportRecord(record: ExportJournalRecord): Promise<void> {
    this.byId.set(record.export_id, record);
  }

  async findExportRecord(
    session_id: string,
    export_id: string,
  ): Promise<ExportJournalRecord | null> {
    const record = this.byId.get(export_id);
    if (!record || record.session_id !== session_id) return null;
    return record;
  }

  /** Test and diagnostic view of everything journaled, in append order. */
  records(): ExportJournalRecord[] {
    return [...this.byId.values()];
  }
}

/**
 * Session liveness for the deletion race (test contract T059): a
 * retention or deletion tombstone recorded by CWE-006 must be visible
 * to the export path before rendering and again before the artifact is
 * journaled and registered, so a deleted private artifact can never be
 * exposed by an export that started earlier.
 */
export interface SessionLivenessPort {
  isSessionDeleted(scope: ScopeFields, session_id: string): boolean | Promise<boolean>;
}

export function createCwe006SessionLiveness(
  store: CouncilStoreService,
): SessionLivenessPort {
  return {
    isSessionDeleted(scope: ScopeFields, session_id: string) {
      return store.repositories.isDeleted(scope.tenant_id, session_id);
    },
  };
}
