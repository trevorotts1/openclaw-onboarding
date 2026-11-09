/**
 * stage-receipts.ts — six-stage distribution receipts (UNIT R2 CC-RECEIPTS).
 *
 * One status truth for "did the artifact actually arrive?", on SIX stages,
 * each measured on its own axis, each row carrying its OWN evidence pointer:
 *
 *   source_merged     commit_sha      (e.g. build-inventory.json source_sha)
 *   package_built     package_hash    (e.g. inventory_digest / bundle sha256)
 *   target_installed  install_path
 *   agent_selected    resolver_path   (the path the agent's resolver selects)
 *   runtime_adopted   process_ref     (the running process that serves it)
 *   live_outcome      live_check
 *
 * This EXTENDS the existing status/event/ledger contracts — it does not fork
 * them:
 *   - Vocabulary: the fleet-status / claim-gate ledger row tokens — CURRENT /
 *     BEHIND / UNKNOWN / UNREACHABLE, plus BLOCKED for resolver failure. A
 *     claim-gate style consumer says BEHIND/UNKNOWN per stage on the same
 *     words it uses today, one axis per row, never conflated into one note.
 *   - Evidence kinds: the pointers deployment status rows already record
 *     (build-inventory manifest source_sha / inventory_digest, install dir),
 *     plus the runtime-model.ts resolution axis (what was selected vs what
 *     the running gateway/session actually adopted vs `none`).
 *   - Fail-closed rule (claim-gate receipts / capability manifests): an
 *     unverifiable stage is UNKNOWN or BLOCKED, NEVER a pass. A completed
 *     build must never turn unknown runtime selection green — a missing
 *     agent-selection or runtime-adoption measurement renders that stage
 *     UNKNOWN, not pass. A verdict without its own evidence pointer is
 *     downgraded to UNKNOWN the same way. Resolver failure is BLOCKED.
 *     Source-only packaging that builds externally (e.g. 999) is not a
 *     failure: absent in-tree dist is simply an unmeasured package_built
 *     stage = UNKNOWN until the external build's package hash is supplied.
 *   - Roll-up: worst-status-wins, the same discipline probes/types.ts
 *     worstStatus() and computeOverallTiered() apply to the status pill —
 *     not a clean pass on every stage must never read as healthy.
 *
 * Rows are additive to the fleet-status ledger row: existing keys stay as
 * they are, `stages` joins them, and the single `status` becomes the
 * fail-closed roll-up of the six stage statuses.
 */

/** The six stages, in delivery order. */
export const STAGE_ORDER = [
  'source_merged',
  'package_built',
  'target_installed',
  'agent_selected',
  'runtime_adopted',
  'live_outcome',
] as const;

export type Stage = (typeof STAGE_ORDER)[number];

/** What counts as evidence for each stage. One pointer kind per stage. */
export type EvidenceKind =
  | 'commit_sha'
  | 'package_hash'
  | 'install_path'
  | 'resolver_path'
  | 'process_ref'
  | 'live_check';

export const STAGE_EVIDENCE: Record<Stage, EvidenceKind> = {
  source_merged: 'commit_sha',
  package_built: 'package_hash',
  target_installed: 'install_path',
  agent_selected: 'resolver_path',
  runtime_adopted: 'process_ref',
  live_outcome: 'live_check',
};

/** Per-stage status vocabulary — the claim-gate row tokens, per axis. */
export type StageStatus = 'CURRENT' | 'BEHIND' | 'BLOCKED' | 'UNKNOWN' | 'UNREACHABLE';

/** Worst-first. A stage at a worse rank drags the roll-up to it. */
const RANK: readonly StageStatus[] = ['UNREACHABLE', 'BEHIND', 'BLOCKED', 'UNKNOWN', 'CURRENT'];

/** A measurement of one stage — or its explicit absence (omit / null). */
export interface StageMeasurement {
  /** true = measured pass, false = measured divergence. Omit only if
   * blocked/unreachable; a measurement without a verdict is UNKNOWN. */
  ok?: boolean;
  /** The stage's own evidence pointer. Observed verdicts (CURRENT/BEHIND)
   * REQUIRE a non-empty one; without it the verdict is downgraded to
   * UNKNOWN — a claim with no proof is not a pass. */
  evidence?: string | null;
  /** Resolver failure / explicit refusal. Renders BLOCKED — never a pass. */
  blocked?: boolean;
  /** The measurement itself could not be obtained (probe/box unreachable). */
  unreachable?: boolean;
  note?: string;
}

export interface StageRow {
  stage: Stage;
  status: StageStatus;
  evidence_type: EvidenceKind;
  evidence: string | null;
  note: string;
}

/**
 * Assess one stage. Fail-closed in every branch: nothing renders CURRENT
 * without a measurement AND its evidence pointer.
 */
export function assessStage(stage: Stage, m?: StageMeasurement | null): StageRow {
  const evidence_type = STAGE_EVIDENCE[stage];
  const row = (status: StageStatus, evidence: string | null, note: string): StageRow => ({
    stage,
    status,
    evidence_type,
    evidence,
    note,
  });
  if (m === null || m === undefined) {
    return row('UNKNOWN', null, 'no measurement — UNKNOWN, not pass');
  }
  if (m.unreachable) {
    return row('UNREACHABLE', null, m.note || 'measurement unreachable');
  }
  if (m.blocked) {
    return row('BLOCKED', null, m.note || 'resolver failure — BLOCKED, not pass');
  }
  const ev = m.evidence ? m.evidence : null;
  if (m.ok === undefined) {
    return row('UNKNOWN', null, 'measurement without a verdict — UNKNOWN, not pass');
  }
  if (m.ok) {
    if (!ev) {
      return row('UNKNOWN', null, 'pass claimed without its evidence pointer — UNKNOWN, not pass');
    }
    return row('CURRENT', ev, m.note || '');
  }
  if (!ev) {
    return row('UNKNOWN', null, 'divergence claimed without its evidence pointer — UNKNOWN');
  }
  return row('BEHIND', ev, m.note || '');
}

/** Measurements per stage. Missing keys (and null) mean unmeasured. */
export type StageMeasurements = Partial<Record<Stage, StageMeasurement | null>>;

/**
 * Build all six stage rows. A stage with no measurement becomes an explicit
 * UNKNOWN row — it can never be inferred green from a completed earlier stage.
 */
export function buildStageRows(measurements: StageMeasurements = {}): StageRow[] {
  return STAGE_ORDER.map((stage) => assessStage(stage, measurements[stage]));
}

/**
 * Fail-closed roll-up over the six stage rows: worst status wins. CURRENT
 * only when every one of the six stages is CURRENT. A stage row missing
 * entirely counts as UNKNOWN.
 */
export function rollUpStatus(rows: StageRow[]): StageStatus {
  const seen = new Set(rows.map((r) => r.stage));
  const statuses: StageStatus[] = rows.map((r) => r.status);
  for (const stage of STAGE_ORDER) {
    if (!seen.has(stage)) statuses.push('UNKNOWN');
  }
  for (const rank of RANK) {
    if (statuses.includes(rank)) return rank;
  }
  return 'UNKNOWN';
}

/**
 * Claim-gate style consumer rows: one row per (slug, stage), each axis
 * independent. This is what lets a fleet-status.sh lineage consumer say
 * "stage 3 BEHIND, stage 4 UNKNOWN" without collapsing axes into one note.
 */
export interface ConsumerStageRow {
  slug: string;
  stage: Stage;
  status: StageStatus;
  evidence_type: EvidenceKind;
  evidence: string | null;
  measured_utc: string;
  note: string;
}

export function projectStageRows(
  slug: string,
  rows: StageRow[],
  measuredUtc: string = new Date().toISOString()
): ConsumerStageRow[] {
  return rows.map((r) => ({
    slug,
    stage: r.stage,
    status: r.status,
    evidence_type: r.evidence_type,
    evidence: r.evidence,
    measured_utc: measuredUtc,
    note: r.note,
  }));
}

/**
 * The ledger row a claim-gate style consumer stores (latest row per slug):
 * the existing row vocabulary with `stages` added and `status` derived
 * fail-closed from them. `note` stays roll-up context only — per-stage
 * detail lives on its own row and never gets conflated into it.
 */
export interface StageLedgerRow {
  slug: string;
  status: StageStatus;
  stages: Record<Stage, StageRow>;
  measured_utc: string;
  note: string;
}

export function buildLedgerRow(
  slug: string,
  measurements: StageMeasurements = {},
  measuredUtc: string = new Date().toISOString()
): StageLedgerRow {
  const rows = buildStageRows(measurements);
  const stages = Object.fromEntries(rows.map((r) => [r.stage, r])) as Record<Stage, StageRow>;
  const status = rollUpStatus(rows);
  const note =
    status === 'CURRENT'
      ? ''
      : rows
          .filter((r) => r.status !== 'CURRENT')
          .map((r) => `${r.stage}=${r.status}${r.note ? ` (${r.note})` : ''}`)
          .join('; ');
  return { slug, status, stages, measured_utc: measuredUtc, note };
}
