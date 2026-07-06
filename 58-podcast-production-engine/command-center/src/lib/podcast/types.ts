/**
 * Podcast Production Engine dashboard: shared types.
 *
 * The row shapes mirror the schema created and owned EXCLUSIVELY by the
 * engine's writer module (58-podcast-production-engine/scripts/podcast_state.py,
 * dashboard-design.md Section 5.1). The dashboard never creates or migrates
 * this schema; it only reads it (plus the narrow token-auth write path in
 * Section 5.5 / 11 of the design).
 *
 * Serialized shapes come in two flavors, enforced at the API boundary
 * (design Section 9.3): ClientJob is a strict WHITELIST; OperatorJob extends
 * it with operator-only fields. New columns are private by default because
 * the client serializer never spreads raw rows.
 */

export type PodcastMode = 'personal_podcast_style' | 'interview_style_podcast';

export type PodcastStyle =
  | 'counter_intuitive'
  | 'vulnerable'
  | 'provocative'
  | 'passionate';

export type PodcastStatus =
  | 'received'
  | 'researching'
  | 'writing'
  | 'in_qc'
  | 'generating_art'
  | 'producing_audio'
  | 'publishing'
  | 'enrolling'
  | 'complete'
  | 'failed'
  | 'queued_credit_out';

export type QueueState = 'none' | 'held' | 'resumed' | 'aged_out';

/** Raw podcast_jobs row exactly as stored by podcast_state.py. Server only. */
export interface PodcastJobRow {
  job_id: string;
  client_id: string;
  location_id: string;
  contact_id: string;
  submission_fingerprint: string;
  mode: PodcastMode;
  style: PodcastStyle;
  show_name: string | null;
  host_name: string | null;
  submitter_first_name: string | null;
  submitter_last_name: string | null;
  submitter_email: string | null;
  submitter_phone: string | null;
  status: PodcastStatus;
  resume_stage: string | null;
  attempt_count: number;
  failed_step: string | null;
  last_error: string | null;
  queue_state: QueueState;
  queued_at: string | null;
  queued_service: string | null;
  queue_deadline: string | null;
  aged_out_at: string | null;
  cost_accrued_usd: number;
  writing_model: string | null;
  research_tool: string | null;
  episode_title: string | null;
  episode_description: string | null;
  episode_number: number | null;
  podbean_permalink: string | null;
  episode_package_url: string | null;
  speech_script_url: string | null;
  book_teaser_url: string | null;
  mp3_media_url: string | null;
  cover_image_url: string | null;
  spoken_word_count: number | null;
  runtime_minutes: number | null;
  publish_timestamp: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  pii_scrubbed_at: string | null;
}

/** Raw podcast_job_events row. Server only. */
export interface PodcastJobEventRow {
  event_id: number;
  job_id: string;
  at: string;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  cost_delta_usd: number;
}

/** Raw podcast_dashboard_tokens row. Server only; token_hash never serialized. */
export interface PodcastDashboardTokenRow {
  token_id: string;
  client_id: string;
  token_hash: string;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  revoked_reason: string | null;
}

/** Raw podcast_client_state row. Server only. */
export interface PodcastClientStateRow {
  client_id: string;
  active: number;
  deactivated_at: string | null;
  note: string | null;
}

/* ------------------------------------------------------------------ */
/* Serialized shapes (design Section 9): client-clean vs operator.     */
/* ------------------------------------------------------------------ */

/** Output links panel; only non-null links render (design Section 8.1). */
export interface EpisodeLinks {
  podbeanPermalink: string | null;
  episodePackageUrl: string | null;
  speechScriptUrl: string | null;
  bookTeaserUrl: string | null;
  mp3MediaUrl: string | null;
  coverImageUrl: string | null;
}

/**
 * Client-clean job. STRICT WHITELIST. Never add cost, attempts, errors,
 * model names, service names, or any credential-shaped value here.
 * SPEC client_dashboard requires submitter identity to be visible.
 */
export interface ClientJob {
  jobId: string;
  submitterFirstName: string | null;
  submitterLastName: string | null;
  submitterEmail: string | null;
  submitterPhone: string | null;
  episodeTitle: string | null;
  episodeDescription: string | null;
  episodeNumber: number | null;
  mode: PodcastMode;
  style: PodcastStyle;
  showName: string | null;
  hostName: string | null;
  status: PodcastStatus;
  queueState: QueueState;
  heldDays: number | null;
  links: EpisodeLinks;
  spokenWordCount: number | null;
  runtimeMinutes: number | null;
  publishTimestamp: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  agedOutAt: string | null;
  piiScrubbed: boolean;
}

/** Operator-verbose job: everything the client sees plus internals. */
export interface OperatorJob extends ClientJob {
  clientId: string;
  locationId: string;
  contactId: string;
  attemptCount: number;
  failedStep: string | null;
  lastError: string | null;
  costAccruedUsd: number;
  writingModel: string | null;
  researchTool: string | null;
  queuedService: string | null;
  queuedAt: string | null;
  queueDeadline: string | null;
  resumeStage: string | null;
}

/** Client-clean event: stage transitions only, no notes, no cost. */
export interface ClientEvent {
  eventId: number;
  at: string;
  fromStatus: string | null;
  toStatus: string | null;
}

/** Operator event: adds the sanitized note and the cost delta. */
export interface OperatorEvent extends ClientEvent {
  note: string | null;
  costDeltaUsd: number;
}

/** Queue rows (design Section 8.2). Client copy never names the service. */
export interface ClientQueueRow {
  jobId: string;
  submitterFirstName: string | null;
  submitterLastName: string | null;
  episodeTitle: string | null;
  mode: PodcastMode;
  style: PodcastStyle;
  queueState: QueueState;
  heldDays: number | null;
  agedOutAt: string | null;
  createdAt: string;
}

export interface OperatorQueueRow extends ClientQueueRow {
  queuedService: string | null;
  queuedAt: string | null;
  queueDeadline: string | null;
  resumeStage: string | null;
  payloadPresent: boolean;
}

/** Summary KPIs (design Section 13). Spend appears only for operators. */
export interface PodcastSummary {
  inProduction: number;
  published: number;
  publishedThisMonth: number;
  held: number;
  failed: number;
  spendThisMonth?: number;
}

/** Token listing shape for /podcast/ops/access. Hash never leaves the server. */
export interface TokenListItem {
  tokenId: string;
  label: string | null;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
  revokedReason: string | null;
}
