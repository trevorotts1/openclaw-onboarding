/**
 * Podcast Production Engine dashboard: read queries.
 *
 * Every query is parameterized by the box's own client_id (design 10.1.2)
 * and runs on the read-only handle. No query here can mutate anything: the
 * connection is opened { readonly: true } and better-sqlite3 throws on any
 * write attempt at the SQLite layer.
 */

import type Database from 'better-sqlite3';
import type { PodcastJobEventRow, PodcastJobRow } from './types';

export interface JobListFilters {
  status?: string | null;
  mode?: string | null;
  style?: string | null;
  q?: string | null;
  cursor?: string | null;
  limit?: number;
  since?: string | null;
}

const MAX_LIMIT = 100;

export function listJobs(
  db: Database.Database,
  clientId: string,
  filters: JobListFilters
): { rows: PodcastJobRow[]; nextCursor: string | null } {
  const clauses: string[] = ['client_id = @clientId'];
  const params: Record<string, unknown> = { clientId };

  if (filters.status) {
    clauses.push('status = @status');
    params.status = filters.status;
  }
  if (filters.mode) {
    clauses.push('mode = @mode');
    params.mode = filters.mode;
  }
  if (filters.style) {
    clauses.push('style = @style');
    params.style = filters.style;
  }
  if (filters.q) {
    clauses.push(
      "(COALESCE(episode_title,'') LIKE @q OR COALESCE(submitter_first_name,'') LIKE @q " +
        "OR COALESCE(submitter_last_name,'') LIKE @q)"
    );
    params.q = `%${filters.q}%`;
  }
  if (filters.since) {
    clauses.push('updated_at > @since');
    params.since = filters.since;
  }
  if (filters.cursor) {
    // job_id is a ULID: lexically sortable by creation time. Cursor pages
    // walk newest-first, so the next page is strictly smaller ids.
    clauses.push('job_id < @cursor');
    params.cursor = filters.cursor;
  }

  const limit = Math.min(Math.max(filters.limit ?? 25, 1), MAX_LIMIT);
  const rows = db
    .prepare(
      `SELECT * FROM podcast_jobs WHERE ${clauses.join(' AND ')} ` +
        'ORDER BY job_id DESC LIMIT @limit'
    )
    .all({ ...params, limit: limit + 1 }) as PodcastJobRow[];

  let nextCursor: string | null = null;
  if (rows.length > limit) {
    rows.length = limit;
    nextCursor = rows[rows.length - 1]?.job_id ?? null;
  }
  return { rows, nextCursor };
}

export function getJob(db: Database.Database, clientId: string, jobId: string): PodcastJobRow | null {
  const row = db
    .prepare('SELECT * FROM podcast_jobs WHERE client_id = ? AND job_id = ?')
    .get(clientId, jobId) as PodcastJobRow | undefined;
  return row ?? null;
}

export function getJobEvents(db: Database.Database, jobId: string): PodcastJobEventRow[] {
  return db
    .prepare('SELECT * FROM podcast_job_events WHERE job_id = ? ORDER BY at ASC, event_id ASC')
    .all(jobId) as PodcastJobEventRow[];
}

export function hasPayload(db: Database.Database, jobId: string): boolean {
  const row = db
    .prepare('SELECT 1 AS present FROM podcast_job_payloads WHERE job_id = ?')
    .get(jobId) as { present: number } | undefined;
  return row !== undefined;
}

export function listHeld(db: Database.Database, clientId: string): PodcastJobRow[] {
  return db
    .prepare(
      "SELECT * FROM podcast_jobs WHERE client_id = ? AND queue_state = 'held' " +
        'ORDER BY queued_at ASC'
    )
    .all(clientId) as PodcastJobRow[];
}

/** Aged-out rows from the last 90 days (design Section 8.2 item 2). */
export function listAgedOut(db: Database.Database, clientId: string): PodcastJobRow[] {
  return db
    .prepare(
      "SELECT * FROM podcast_jobs WHERE client_id = ? AND queue_state = 'aged_out' " +
        "AND aged_out_at >= datetime('now', '-90 days') ORDER BY aged_out_at DESC"
    )
    .all(clientId) as PodcastJobRow[];
}

export function summaryCounts(db: Database.Database, clientId: string): {
  inProduction: number;
  published: number;
  publishedThisMonth: number;
  held: number;
  failed: number;
  spendThisMonth: number;
} {
  const one = (sql: string): number => {
    const row = db.prepare(sql).get(clientId) as { n: number } | undefined;
    return row?.n ?? 0;
  };
  const inProduction = one(
    "SELECT COUNT(*) AS n FROM podcast_jobs WHERE client_id = ? AND status NOT IN ('complete','failed','queued_credit_out')"
  );
  const published = one(
    "SELECT COUNT(*) AS n FROM podcast_jobs WHERE client_id = ? AND status = 'complete'"
  );
  const publishedThisMonth = one(
    "SELECT COUNT(*) AS n FROM podcast_jobs WHERE client_id = ? AND status = 'complete' " +
      "AND completed_at >= datetime('now', 'start of month')"
  );
  const held = one(
    "SELECT COUNT(*) AS n FROM podcast_jobs WHERE client_id = ? AND queue_state = 'held'"
  );
  const failed = one(
    "SELECT COUNT(*) AS n FROM podcast_jobs WHERE client_id = ? AND status = 'failed'"
  );
  const spendRow = db
    .prepare(
      'SELECT COALESCE(SUM(cost_accrued_usd), 0) AS n FROM podcast_jobs WHERE client_id = ? ' +
        "AND updated_at >= datetime('now', 'start of month')"
    )
    .get(clientId) as { n: number } | undefined;
  return {
    inProduction,
    published,
    publishedThisMonth,
    held,
    failed,
    spendThisMonth: Math.round((spendRow?.n ?? 0) * 100) / 100,
  };
}
