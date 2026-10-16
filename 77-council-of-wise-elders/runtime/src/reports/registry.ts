/**
 * Registered deliverables for council reports (CWE-038, directive
 * Sections 24.1, 24.3, 24.4; binding B15).
 *
 * The format registry is the single list of deliverables an export may
 * produce. Markdown, the canonical record JSON, and print HTML are
 * rendered deterministically by this unit from the validated verdict
 * revision. PDF is a REGISTERED deliverable whose renderer is the
 * approved Playwright/Chromium capability named in Section 24.3; that
 * renderer is not present in this runtime's dependency bill (the
 * package depends on zod only), so the PDF deliverable is registered
 * as not ready and names the missing piece. Rendered-PDF production
 * and visual QA belong to CWE-044. A PDF is never faked with renamed
 * bytes.
 *
 * The deliverable registry records real register, read, delete, and
 * redaction-produced artifacts (B15): every successful export registers
 * its artifacts under a deliverable ID bound to the session scope, the
 * exact verdict revision, and the artifact content hash. Reads recheck
 * authorization and session liveness in the service layer before any
 * bytes are returned (Section 24.4; test contract T059).
 */

import type { ScopeFields } from '../contracts/index.js';

export const REPORT_FORMATS = [
  'record_json',
  'markdown',
  'print_html',
  'pdf',
] as const;
export type ReportFormat = (typeof REPORT_FORMATS)[number];

export interface ReportFormatDescriptor {
  format: ReportFormat;
  status: 'ready' | 'not_ready';
  media_type: string;
  file_extension: string;
  /** Set only when status is 'not_ready': the missing piece, named. */
  missing_piece: string | null;
}

export const PDF_MISSING_PIECE =
  'the approved Playwright/Chromium PDF renderer (directive Section 24.3) is not present in the runtime dependency bill (package dependencies: zod only); rendered PDF production and visual QA are owned by CWE-044';

export const REPORT_FORMAT_REGISTRY: Readonly<
  Record<ReportFormat, ReportFormatDescriptor>
> = {
  record_json: {
    format: 'record_json',
    status: 'ready',
    media_type: 'application/json',
    file_extension: 'json',
    missing_piece: null,
  },
  markdown: {
    format: 'markdown',
    status: 'ready',
    media_type: 'text/markdown; charset=utf-8',
    file_extension: 'md',
    missing_piece: null,
  },
  print_html: {
    format: 'print_html',
    status: 'ready',
    media_type: 'text/html; charset=utf-8',
    file_extension: 'html',
    missing_piece: null,
  },
  pdf: {
    format: 'pdf',
    status: 'not_ready',
    media_type: 'application/pdf',
    file_extension: 'pdf',
    missing_piece: PDF_MISSING_PIECE,
  },
};

export function isReportFormat(value: string): value is ReportFormat {
  return (REPORT_FORMATS as readonly string[]).includes(value);
}

/** Safe download filename (Section 24.4): built from IDs only, never caller paths. */
export function reportFilename(args: {
  session_id: string;
  verdict_revision: number;
  format: ReportFormat;
  redacted: boolean;
}): string {
  const descriptor = REPORT_FORMAT_REGISTRY[args.format];
  const redactionSuffix = args.redacted ? '-redacted' : '';
  return `council-report-${args.session_id}-r${args.verdict_revision}${redactionSuffix}.${descriptor.file_extension}`;
}

/**
 * One registered deliverable artifact. Bytes are the exact rendered
 * bytes; sha256 is the SHA-256 of those bytes; the verdict identity
 * fields bind the artifact to one exact validated revision.
 */
export interface ReportDeliverable {
  deliverable_id: string;
  request_id: string;
  session_id: string;
  scope: ScopeFields;
  visibility: 'private' | 'company';
  format: ReportFormat;
  filename: string;
  media_type: string;
  bytes: string;
  sha256: string;
  verdict_revision: number;
  verdict_content_sha256: string;
  report_revision_id: string;
  redacted: boolean;
  redaction_profile_id: string | null;
  registered_at: string;
}

/**
 * The deliverable registry port. Hosts back this with durable storage
 * at composition (CWE-050); this unit ships the contract plus an
 * in-memory implementation used by the service's own tests.
 */
export interface DeliverableRegistry {
  register(deliverable: ReportDeliverable): void;
  /** Returns the deliverable or null; absence and foreign scope are indistinguishable to callers above the service layer. */
  get(deliverable_id: string): ReportDeliverable | null;
  delete(deliverable_id: string): boolean;
  listForSession(session_id: string): ReportDeliverable[];
}

export class InMemoryDeliverableRegistry implements DeliverableRegistry {
  private readonly byId = new Map<string, ReportDeliverable>();

  register(deliverable: ReportDeliverable): void {
    this.byId.set(deliverable.deliverable_id, deliverable);
  }

  get(deliverable_id: string): ReportDeliverable | null {
    return this.byId.get(deliverable_id) ?? null;
  }

  delete(deliverable_id: string): boolean {
    return this.byId.delete(deliverable_id);
  }

  listForSession(session_id: string): ReportDeliverable[] {
    return [...this.byId.values()].filter((d) => d.session_id === session_id);
  }
}
