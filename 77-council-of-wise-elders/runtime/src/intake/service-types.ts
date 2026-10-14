/**
 * CWE-023 service-level record types: the freeze record and the
 * pre-start review summary (directive Sections 9.4, 10, 13.1).
 * Kept apart from types.ts so the store layer can persist them
 * without importing the service.
 */
import type {
  DecisionBrief,
  SessionSpec,
} from '../contracts/index.js';
import type { PanelAssessment } from './panel.js';
import type { RouteSnapshot } from './routes.js';
import type { INTAKE_SCHEMA_VERSION } from './types.js';

/**
 * The freeze record: everything a run start binds, in one place.
 * The brief revision and its evidence manifest are frozen; the route
 * snapshot is pinned; the panel assessment (with any not_assessed
 * critical domains and the quick-mode policy record) is recorded
 * exactly as displayed before start.
 */
export interface FreezeRecord {
  readonly schema_version: typeof INTAKE_SCHEMA_VERSION;
  readonly session_id: string;
  readonly brief_revision: number;
  readonly brief_sha256: string;
  /** Canonical hash of the frozen evidence manifest (CWE-022). */
  readonly evidence_manifest_sha256: string;
  readonly route_snapshot: RouteSnapshot;
  readonly panel_assessment: PanelAssessment;
  readonly frozen_at: string;
}

/** The result of a successful freeze: the canonical records a run needs. */
export interface FreezeResult {
  readonly brief: DecisionBrief;
  readonly spec: SessionSpec;
  readonly freeze_record: FreezeRecord;
}

/**
 * What the review screen shows before start (Section 9.4): options,
 * facts, assumptions, unknowns, mode, panel with its required critical
 * responsibilities, the pinned route (always displayed), the evidence
 * manifest, and what is still missing.
 */
export interface IntakeReviewSummary {
  readonly session_id: string;
  readonly status: 'in_progress' | 'frozen';
  readonly brief_preview: DecisionBrief | null;
  readonly panel_assessment: PanelAssessment | null;
  readonly route_snapshot: RouteSnapshot | null;
  readonly evidence_manifest_count: number;
  readonly missing_material_questions: readonly string[];
  readonly ready_to_freeze: boolean;
}
