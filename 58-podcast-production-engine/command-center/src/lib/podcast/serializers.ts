/**
 * Podcast Production Engine dashboard: the serializer boundary.
 *
 * THIS FILE IS THE ENFORCEMENT POINT for client-clean vs operator-verbose
 * (design Sections 2 D5, 9, 9.3). The client serializers WHITELIST fields;
 * they never spread a raw row, so any column added to the schema later is
 * private by default. The React client bundle only ever receives the output
 * of these functions, so verbose data never reaches a client browser at all.
 *
 * NEVER add to the client shapes: cost, attempt counts, error text, failed
 * step names, model names, research tools, depleted service names, queue
 * deadlines, resume stages, location or contact ids, or anything
 * credential-shaped. Those exist only in the operator serializers.
 */

import type {
  ClientEvent,
  ClientJob,
  ClientQueueRow,
  OperatorEvent,
  OperatorJob,
  OperatorQueueRow,
  PodcastJobEventRow,
  PodcastJobRow,
  PodcastSummary,
} from './types';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** Whole days since an ISO timestamp (UTC), floored at 0. */
export function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const then = Date.parse(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((Date.now() - then) / MS_PER_DAY));
}

/** Client-clean job: strict whitelist (design Section 9 matrix). */
export function toClientJob(row: PodcastJobRow): ClientJob {
  return {
    jobId: row.job_id,
    submitterFirstName: row.submitter_first_name,
    submitterLastName: row.submitter_last_name,
    submitterEmail: row.submitter_email,
    submitterPhone: row.submitter_phone,
    episodeTitle: row.episode_title,
    episodeDescription: row.episode_description,
    episodeNumber: row.episode_number,
    mode: row.mode,
    style: row.style,
    showName: row.show_name,
    hostName: row.host_name,
    status: row.status,
    queueState: row.queue_state,
    heldDays: row.queue_state === 'held' ? daysSince(row.queued_at) : null,
    links: {
      podbeanPermalink: row.podbean_permalink,
      episodePackageUrl: row.episode_package_url,
      speechScriptUrl: row.speech_script_url,
      bookTeaserUrl: row.book_teaser_url,
      mp3MediaUrl: row.mp3_media_url,
      coverImageUrl: row.cover_image_url,
    },
    spokenWordCount: row.spoken_word_count,
    runtimeMinutes: row.runtime_minutes,
    publishTimestamp: row.publish_timestamp,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    completedAt: row.completed_at,
    agedOutAt: row.aged_out_at,
    piiScrubbed: row.pii_scrubbed_at !== null,
  };
}

/** Operator-verbose job: the client shape plus internals. */
export function toOperatorJob(row: PodcastJobRow): OperatorJob {
  return {
    ...toClientJob(row),
    clientId: row.client_id,
    locationId: row.location_id,
    contactId: row.contact_id,
    attemptCount: row.attempt_count,
    failedStep: row.failed_step,
    lastError: row.last_error,
    costAccruedUsd: row.cost_accrued_usd,
    writingModel: row.writing_model,
    researchTool: row.research_tool,
    queuedService: row.queued_service,
    queuedAt: row.queued_at,
    queueDeadline: row.queue_deadline,
    resumeStage: row.resume_stage,
  };
}

/**
 * Client-clean events: stage transitions only. Events with no status change
 * (pure notes, cost markers) are dropped entirely for clients.
 */
export function toClientEvents(rows: PodcastJobEventRow[]): ClientEvent[] {
  return rows
    .filter((e) => e.to_status !== null && e.to_status !== e.from_status)
    .map((e) => ({
      eventId: e.event_id,
      at: e.at,
      fromStatus: e.from_status,
      toStatus: e.to_status,
    }));
}

/** Operator events: everything, including notes and cost deltas. */
export function toOperatorEvents(rows: PodcastJobEventRow[]): OperatorEvent[] {
  return rows.map((e) => ({
    eventId: e.event_id,
    at: e.at,
    fromStatus: e.from_status,
    toStatus: e.to_status,
    note: e.note,
    costDeltaUsd: e.cost_delta_usd,
  }));
}

/** Client queue row: age and identity, never the service name. */
export function toClientQueueRow(row: PodcastJobRow): ClientQueueRow {
  return {
    jobId: row.job_id,
    submitterFirstName: row.submitter_first_name,
    submitterLastName: row.submitter_last_name,
    episodeTitle: row.episode_title,
    mode: row.mode,
    style: row.style,
    queueState: row.queue_state,
    heldDays: row.queue_state === 'held' ? daysSince(row.queued_at) : null,
    agedOutAt: row.aged_out_at,
    createdAt: row.created_at,
  };
}

/** Operator queue row: adds service, deadline, resume stage, payload flag. */
export function toOperatorQueueRow(row: PodcastJobRow, payloadPresent: boolean): OperatorQueueRow {
  return {
    ...toClientQueueRow(row),
    queuedService: row.queued_service,
    queuedAt: row.queued_at,
    queueDeadline: row.queue_deadline,
    resumeStage: row.resume_stage,
    payloadPresent,
  };
}

/** Summary counts; spendThisMonth is attached only for operator sessions. */
export function toSummary(counts: {
  inProduction: number;
  published: number;
  publishedThisMonth: number;
  held: number;
  failed: number;
  spendThisMonth: number;
}, operator: boolean): PodcastSummary {
  const base: PodcastSummary = {
    inProduction: counts.inProduction,
    published: counts.published,
    publishedThisMonth: counts.publishedThisMonth,
    held: counts.held,
    failed: counts.failed,
  };
  if (operator) base.spendThisMonth = counts.spendThisMonth;
  return base;
}

/**
 * The operator-only key set, exported so tests can assert the client
 * serializer never emits any of them (acceptance criterion 6).
 */
export const OPERATOR_ONLY_JOB_KEYS = [
  'clientId',
  'locationId',
  'contactId',
  'attemptCount',
  'failedStep',
  'lastError',
  'costAccruedUsd',
  'writingModel',
  'researchTool',
  'queuedService',
  'queuedAt',
  'queueDeadline',
  'resumeStage',
] as const;
