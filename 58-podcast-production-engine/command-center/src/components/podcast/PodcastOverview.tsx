'use client';

/**
 * Pipeline overview (design Section 7): page header with a mount-gated
 * "Updated" caption, the KPI row, filters, and the episode pipeline as a
 * stage-grouped list (default) with a display-only board toggle on desktop.
 * Polling per Section 7.4: every 15 seconds while the tab is visible, no
 * websockets, no sounds, no client toasts (move in silence). Desktop row
 * clicks open the right-side drawer; mobile navigates to the episode page.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LayoutGrid, List, Search } from 'lucide-react';
import KpiRow from './KpiRow';
import EpisodeRow, { type AnyJob } from './EpisodeRow';
import StagePill from './StagePill';
import { EpisodeDrawer } from './EpisodeDetail';
import { EmptyState, ErrorState, LoadingState } from './states';
import type { PodcastStatus, PodcastSummary } from '@/lib/podcast/types';
import {
  MODE_LABELS,
  PIPELINE_ORDER,
  STYLE_LABELS,
  stageMetaFor,
} from '@/lib/podcast/stages';
import { relativeTime } from '@/lib/podcast/format';

const POLL_MS = 15000;
const PAGE_SIZE = 25;

/** Board column gradient headers: the .column-pill-* 135deg convention applied to the stage hue bases of Section 7.2. */
const COLUMN_GRADIENTS: Record<string, string> = {
  received: 'linear-gradient(135deg, #3B82F6, #2563EB)',
  researching: 'linear-gradient(135deg, #6366F1, #4F46E5)',
  writing: 'linear-gradient(135deg, #10B981, #059669)',
  in_qc: 'linear-gradient(135deg, #F59E0B, #D97706)',
  generating_art: 'linear-gradient(135deg, #8B5CF6, #7C3AED)',
  producing_audio: 'linear-gradient(135deg, #06B6D4, #0891B2)',
  publishing: 'linear-gradient(135deg, var(--brand-500, #4CAF50), var(--brand-700, #388E3C))',
  enrolling: 'linear-gradient(135deg, #0D9488, #0F766E)',
  complete: 'linear-gradient(135deg, #059669, #047857)',
};

interface JobsResponse {
  jobs: AnyJob[];
  nextCursor: string | null;
  lastUpdatedAt: string | null;
}

const ACTIVE_ORDER: PodcastStatus[] = PIPELINE_ORDER.filter((s) => s !== 'complete');

export default function PodcastOverview({ operator }: { operator: boolean }) {
  const router = useRouter();
  const [summary, setSummary] = useState<PodcastSummary | null>(null);
  const [jobs, setJobs] = useState<AnyJob[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [board, setBoard] = useState(false);
  const [modeFilter, setModeFilter] = useState<string>('all');
  const [styleFilter, setStyleFilter] = useState<string>('all');
  const [query, setQuery] = useState('');
  const [drawerJobId, setDrawerJobId] = useState<string | null>(null);
  const [publishedShown, setPublishedShown] = useState(PAGE_SIZE);
  const [mounted, setMounted] = useState(false);
  const loadingMore = useRef(false);

  useEffect(() => setMounted(true), []);

  const load = useCallback(async (silent = false) => {
    if (!silent) setError(false);
    try {
      const [summaryRes, jobsRes] = await Promise.all([
        fetch('/api/podcast/summary', { cache: 'no-store' }),
        fetch(`/api/podcast/jobs?limit=100`, { cache: 'no-store' }),
      ]);
      if (!summaryRes.ok || !jobsRes.ok) throw new Error('bad status');
      const summaryJson = (await summaryRes.json()) as PodcastSummary;
      const jobsJson = (await jobsRes.json()) as JobsResponse;
      setSummary(summaryJson);
      setJobs(jobsJson.jobs);
      setNextCursor(jobsJson.nextCursor);
      setLastUpdated(jobsJson.lastUpdatedAt);
    } catch {
      if (!silent) setError(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 15 seconds while the tab is visible (Section 7.4).
  useEffect(() => {
    const tick = () => {
      if (!document.hidden) void load(true);
    };
    const id = setInterval(tick, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const loadMorePublished = useCallback(async () => {
    if (loadingMore.current) return;
    if (publishedShown < (jobs?.filter((j) => j.status === 'complete').length ?? 0)) {
      setPublishedShown((n) => n + PAGE_SIZE);
      return;
    }
    if (!nextCursor) {
      setPublishedShown((n) => n + PAGE_SIZE);
      return;
    }
    loadingMore.current = true;
    try {
      const res = await fetch(
        `/api/podcast/jobs?limit=100&cursor=${encodeURIComponent(nextCursor)}`,
        { cache: 'no-store' }
      );
      if (res.ok) {
        const json = (await res.json()) as JobsResponse;
        setJobs((prev) => {
          const seen = new Set((prev ?? []).map((j) => j.jobId));
          return [...(prev ?? []), ...json.jobs.filter((j) => !seen.has(j.jobId))];
        });
        setNextCursor(json.nextCursor);
        setPublishedShown((n) => n + PAGE_SIZE);
      }
    } finally {
      loadingMore.current = false;
    }
  }, [jobs, nextCursor, publishedShown]);

  const openJob = useCallback(
    (jobId: string) => {
      if (typeof window !== 'undefined' && window.innerWidth >= 1024) {
        setDrawerJobId(jobId);
      } else {
        router.push(`/podcast/episodes/${jobId}`);
      }
    },
    [router]
  );

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader lastUpdated={lastUpdated} mounted={mounted} />
        <ErrorState onRetry={() => void load()} />
      </div>
    );
  }

  if (!summary || jobs === null) {
    return (
      <div className="space-y-6">
        <PageHeader lastUpdated={lastUpdated} mounted={mounted} />
        <LoadingState />
      </div>
    );
  }

  // Client-side filtering over the fetched page (Section 7.1 item 4).
  const q = query.trim().toLowerCase();
  const filtered = jobs.filter((j) => {
    if (modeFilter !== 'all' && j.mode !== modeFilter) return false;
    if (styleFilter !== 'all' && j.style !== styleFilter) return false;
    if (q) {
      const hay = `${j.submitterFirstName ?? ''} ${j.submitterLastName ?? ''} ${j.episodeTitle ?? ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const grouped = new Map<string, AnyJob[]>();
  for (const status of ACTIVE_ORDER) grouped.set(status, []);
  grouped.set('queued_credit_out', []);
  grouped.set('failed', []);
  const published: AnyJob[] = [];
  for (const j of filtered) {
    if (j.status === 'complete') {
      published.push(j);
    } else {
      grouped.get(j.status)?.push(j);
    }
  }
  const hasAnything = jobs.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader lastUpdated={lastUpdated} mounted={mounted} />
      <KpiRow summary={summary} operator={operator} />

      {!hasAnything ? (
        <EmptyState />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-full border border-gray-200 bg-white p-1">
              {['all', 'personal_podcast_style', 'interview_style_podcast'].map((m) => (
                <button
                  key={m}
                  onClick={() => setModeFilter(m)}
                  className={`rounded-full px-3 py-1 text-badge transition-colors ${
                    modeFilter === m
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {m === 'all' ? 'All' : MODE_LABELS[m]}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 rounded-full border border-gray-200 bg-white p-1 overflow-x-auto">
              {['all', 'counter_intuitive', 'vulnerable', 'provocative', 'passionate'].map((s) => (
                <button
                  key={s}
                  onClick={() => setStyleFilter(s)}
                  className={`whitespace-nowrap rounded-full px-3 py-1 text-badge transition-colors ${
                    styleFilter === s
                      ? 'bg-brand-50 text-brand-700'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {s === 'all' ? 'All styles' : STYLE_LABELS[s]}
                </button>
              ))}
            </div>
            <label className="relative flex-1 min-w-[180px] max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
                aria-hidden="true"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name or title"
                aria-label="Search by submitter name or episode title"
                className="w-full rounded-full border border-gray-200 bg-white py-1.5 pl-9 pr-3 text-sm text-gray-700 placeholder:text-gray-400 focus:border-brand-300 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </label>
            <button
              onClick={() => setBoard((b) => !b)}
              className="ml-auto hidden lg:flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-badge text-gray-600 transition-colors hover:border-brand-300 hover:text-gray-900"
              aria-pressed={board}
            >
              {board ? <List className="h-4 w-4" aria-hidden="true" /> : <LayoutGrid className="h-4 w-4" aria-hidden="true" />}
              {board ? 'List view' : 'Board view'}
            </button>
          </div>

          {board ? (
            <BoardView jobs={filtered} operator={operator} onOpen={openJob} />
          ) : (
            <div className="space-y-8" aria-live="polite">
              {[...ACTIVE_ORDER, 'queued_credit_out', 'failed'].map((status) => {
                const rows = grouped.get(status) ?? [];
                if (rows.length === 0) return null;
                return (
                  <section key={status}>
                    <div className="mb-3 flex items-center gap-2">
                      <StagePill
                        status={status as PodcastStatus}
                        queueState={status === 'queued_credit_out' ? 'held' : 'none'}
                      />
                      <span className="text-caption text-gray-500">{rows.length}</span>
                    </div>
                    <div className="space-y-2">
                      {rows.map((j) => (
                        <EpisodeRow key={j.jobId} job={j} operator={operator} onOpen={openJob} />
                      ))}
                    </div>
                  </section>
                );
              })}

              {published.length > 0 ? (
                <section>
                  <h2 className="text-section text-gray-900 mb-3">Published</h2>
                  <div className="space-y-2">
                    {published.slice(0, publishedShown).map((j) => (
                      <EpisodeRow key={j.jobId} job={j} operator={operator} onOpen={openJob} />
                    ))}
                  </div>
                  {(published.length > publishedShown || nextCursor) && (
                    <button
                      onClick={() => void loadMorePublished()}
                      className="mt-3 rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:border-brand-300 hover:text-gray-900"
                    >
                      Load more
                    </button>
                  )}
                </section>
              ) : null}
            </div>
          )}
        </>
      )}

      {drawerJobId ? (
        <EpisodeDrawer jobId={drawerJobId} operator={operator} onClose={() => setDrawerJobId(null)} />
      ) : null}
    </div>
  );
}

function PageHeader({ lastUpdated, mounted }: { lastUpdated: string | null; mounted: boolean }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-page-title text-gray-900">Podcast Studio</h1>
        <p className="text-caption text-gray-500">Every episode, from submission to published.</p>
      </div>
      {mounted && lastUpdated ? (
        <span className="timestamp-only font-mono text-gray-400">
          Updated {relativeTime(lastUpdated)}
        </span>
      ) : null}
    </div>
  );
}

/**
 * Board view (desktop only): display-only kanban columns per stage using
 * the .kanban-scroll conventions. No drag and drop; columns never mutate
 * the pipeline (Section 7.1 guardrail).
 */
function BoardView({
  jobs,
  operator,
  onOpen,
}: {
  jobs: AnyJob[];
  operator: boolean;
  onOpen: (jobId: string) => void;
}) {
  const columns = PIPELINE_ORDER.map((status) => ({
    status,
    rows: jobs.filter((j) => j.status === status),
  }));
  const held = jobs.filter((j) => j.status === 'queued_credit_out');
  const failed = jobs.filter((j) => j.status === 'failed');
  const extra: Array<{ status: PodcastStatus; rows: AnyJob[] }> = [];
  if (held.length > 0) extra.push({ status: 'queued_credit_out', rows: held });
  if (failed.length > 0) extra.push({ status: 'failed', rows: failed });

  return (
    <div className="relative">
      <div className="kanban-scroll overflow-x-auto pb-3">
        <div className="flex gap-4 min-w-max">
          {[...columns, ...extra].map(({ status, rows }) => {
            const meta = stageMetaFor(status, status === 'queued_credit_out' ? 'held' : 'none');
            const gradient =
              COLUMN_GRADIENTS[status] ?? 'linear-gradient(135deg, #6B7280, #4B5563)';
            return (
              <div key={status} className="w-[280px] flex-shrink-0">
                <div
                  className="mb-3 flex items-center justify-between rounded-full px-3 py-1.5 text-white shadow-pill"
                  style={{ background: gradient }}
                >
                  <span className="text-badge font-medium">{meta.clientLabel}</span>
                  <span className="text-badge">{rows.length}</span>
                </div>
                <div className="space-y-2">
                  {rows.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-3 py-6 text-center text-caption text-gray-400">
                      Empty
                    </div>
                  ) : (
                    rows.map((j) => (
                      <button
                        key={j.jobId}
                        onClick={() => onOpen(j.jobId)}
                        className="w-full rounded-xl border border-gray-200 bg-white p-3 text-left transition-all hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
                      >
                        <div className="text-label font-medium text-gray-900 truncate">
                          {j.episodeTitle ?? 'Untitled, in progress'}
                        </div>
                        <div className="text-caption text-gray-500 truncate">
                          {`${j.submitterFirstName ?? ''} ${j.submitterLastName ?? ''}`.trim() || 'Submitter'}
                        </div>
                        <div className="mt-1 text-caption text-gray-400">
                          {MODE_LABELS[j.mode]} · {STYLE_LABELS[j.style]}
                        </div>
                        {operator ? (
                          <div className="mt-1 font-mono text-xs text-gray-500">
                            ${((j as { costAccruedUsd?: number }).costAccruedUsd ?? 0).toFixed(2)}
                          </div>
                        ) : null}
                      </button>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
