'use client';

/**
 * Episode detail (design Section 8.1): header with cover thumbnail, the
 * "Your episode" links panel, facts grid, event timeline, hold and failed
 * banners. Rendered inside the desktop drawer or the mobile full page.
 * Client view shows friendly stage transitions only; operator view adds
 * notes, cost deltas, and failure internals. Fixed client copy strings are
 * used verbatim (Section 8.3, acceptance criterion 13).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BookOpen,
  FileText,
  Headphones,
  Image as ImageIcon,
  Music4,
  ScrollText,
  X,
} from 'lucide-react';
import StagePill from './StagePill';
import ProgressMeter from './ProgressMeter';
import { ErrorState, LoadingState } from './states';
import type { ClientEvent, OperatorEvent, PodcastStatus } from '@/lib/podcast/types';
import type { AnyJob } from './EpisodeRow';
import {
  FAILED_BANNER_COPY,
  MODE_LABELS,
  STAGE_META,
  STYLE_LABELS,
  holdBannerCopy,
  stageMetaFor,
} from '@/lib/podcast/stages';
import {
  absoluteTime,
  displayName,
  relativeTime,
  runtimeCopy,
} from '@/lib/podcast/format';

type AnyEvent = ClientEvent & Partial<Pick<OperatorEvent, 'note' | 'costDeltaUsd'>>;

interface DetailPayload {
  job: AnyJob & {
    lastError?: string | null;
    failedStep?: string | null;
    attemptCount?: number;
    queuedService?: string | null;
    queueDeadline?: string | null;
    resumeStage?: string | null;
  };
  events: AnyEvent[];
}

function LinkButton({
  href,
  label,
  icon,
  primary,
  badge,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  primary?: boolean;
  badge?: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={
        primary
          ? 'flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700'
          : 'flex items-center gap-2 rounded-xl border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:border-brand-300'
      }
    >
      {icon}
      <span>{label}</span>
      {badge ? (
        <span className="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
          {badge}
        </span>
      ) : null}
    </a>
  );
}

function stageLabelOf(status: string | null): string {
  if (!status) return '';
  const meta = STAGE_META[status as PodcastStatus];
  return meta ? meta.clientLabel : status;
}

export function EpisodeDetailContent({
  data,
  operator,
}: {
  data: DetailPayload;
  operator: boolean;
}) {
  const { job, events } = data;
  const name = displayName(job.submitterFirstName, job.submitterLastName);
  const held = job.queueState === 'held';
  const inFlight = job.status !== 'complete' && job.status !== 'failed';
  const scheduledFuture = (() => {
    if (!job.publishTimestamp) return false;
    const t = Date.parse(job.publishTimestamp);
    return Number.isFinite(t) && t > Date.now();
  })();

  const links: Array<{ href: string | null; label: string; icon: React.ReactNode; primary?: boolean; badge?: string }> = [
    { href: job.links.podbeanPermalink, label: 'Listen on Podbean', icon: <Headphones className="h-4 w-4" aria-hidden="true" />, primary: true },
    { href: job.links.episodePackageUrl, label: 'Episode Package', icon: <FileText className="h-4 w-4" aria-hidden="true" /> },
    { href: job.links.speechScriptUrl, label: 'Speech Script', icon: <ScrollText className="h-4 w-4" aria-hidden="true" /> },
    ...(job.mode === 'interview_style_podcast'
      ? [{ href: job.links.bookTeaserUrl, label: 'Book Teaser', icon: <BookOpen className="h-4 w-4" aria-hidden="true" />, badge: 'Bonus' }]
      : []),
    { href: job.links.coverImageUrl, label: 'Cover image', icon: <ImageIcon className="h-4 w-4" aria-hidden="true" /> },
    { href: job.links.mp3MediaUrl, label: 'Audio file', icon: <Music4 className="h-4 w-4" aria-hidden="true" /> },
  ];
  const visibleLinks = links.filter((l) => l.href);

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        {job.links.coverImageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={job.links.coverImageUrl}
            alt="Episode cover art"
            className="h-16 w-16 flex-shrink-0 rounded-xl object-cover border border-gray-200"
          />
        ) : (
          <span className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-xl bg-gray-100">
            <ImageIcon className="h-6 w-6 text-gray-400" aria-hidden="true" />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-card-title text-gray-900">
            {job.episodeTitle ?? 'Untitled, in progress'}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StagePill status={job.status} queueState={job.queueState} showRaw={operator} />
            <span className="text-caption text-gray-500">{name}</span>
          </div>
          {inFlight ? (
            <div className="mt-2">
              <ProgressMeter status={job.status} resumeStage={job.resumeStage ?? null} />
            </div>
          ) : null}
        </div>
      </div>

      {held ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800">
          {holdBannerCopy(job.heldDays ?? 0)}
          {operator ? (
            <div className="mt-2 font-mono text-xs text-amber-700">
              service: {job.queuedService ?? 'unknown'} · deadline: {job.queueDeadline ?? 'unset'} · resume: {job.resumeStage ?? 'unset'}
            </div>
          ) : null}
        </div>
      ) : null}

      {job.status === 'failed' ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
          {operator ? (
            <div className="space-y-1">
              <div className="font-medium">Failed at step: <span className="font-mono">{job.failedStep ?? 'unknown'}</span></div>
              {typeof job.attemptCount === 'number' ? (
                <div>QC attempts: {job.attemptCount}</div>
              ) : null}
              {job.lastError ? <div className="font-mono text-xs break-words">{job.lastError}</div> : null}
            </div>
          ) : (
            FAILED_BANNER_COPY
          )}
        </div>
      ) : null}

      {visibleLinks.length > 0 ? (
        <div>
          <h3 className="text-sub-heading text-gray-900 mb-3">Your episode</h3>
          <div className="flex flex-col gap-2">
            {visibleLinks.map((l) => (
              <LinkButton
                key={l.label}
                href={l.href as string}
                label={l.label}
                icon={l.icon}
                primary={l.primary}
                badge={l.badge}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <h3 className="text-sub-heading text-gray-900 mb-3">Details</h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
          <div>
            <dt className="text-label text-gray-500">Mode</dt>
            <dd className="text-body text-gray-900">{MODE_LABELS[job.mode] ?? job.mode}</dd>
          </div>
          <div>
            <dt className="text-label text-gray-500">Style</dt>
            <dd className="text-body text-gray-900">{STYLE_LABELS[job.style] ?? job.style}</dd>
          </div>
          {job.episodeNumber !== null && job.episodeNumber !== undefined ? (
            <div>
              <dt className="text-label text-gray-500">Episode number</dt>
              <dd className="text-body text-gray-900">{job.episodeNumber}</dd>
            </div>
          ) : null}
          {job.runtimeMinutes ? (
            <div>
              <dt className="text-label text-gray-500">Runtime</dt>
              <dd className="text-body text-gray-900">{runtimeCopy(job.runtimeMinutes)}</dd>
            </div>
          ) : null}
          {job.spokenWordCount ? (
            <div>
              <dt className="text-label text-gray-500">Word count</dt>
              <dd className="text-body text-gray-900">{job.spokenWordCount.toLocaleString()}</dd>
            </div>
          ) : null}
          <div>
            <dt className="text-label text-gray-500">Submitted</dt>
            <dd className="text-body text-gray-900" title={absoluteTime(job.createdAt)}>
              {relativeTime(job.createdAt)}
            </dd>
          </div>
          {job.completedAt ? (
            <div>
              <dt className="text-label text-gray-500">Published</dt>
              <dd className="text-body text-gray-900" title={absoluteTime(job.completedAt)}>
                {relativeTime(job.completedAt)}
              </dd>
            </div>
          ) : null}
          {scheduledFuture ? (
            <div>
              <dt className="text-label text-gray-500">Scheduled for</dt>
              <dd className="text-body text-gray-900" title={absoluteTime(job.publishTimestamp)}>
                {absoluteTime(job.publishTimestamp)}
              </dd>
            </div>
          ) : null}
          {operator ? (
            <>
              <div>
                <dt className="text-label text-gray-500">Writing model</dt>
                <dd className="font-mono text-caption text-gray-700">{(job as { writingModel?: string | null }).writingModel ?? 'unset'}</dd>
              </div>
              <div>
                <dt className="text-label text-gray-500">Cost accrued</dt>
                <dd className="font-mono text-caption text-gray-700">${(job.costAccruedUsd ?? 0).toFixed(2)}</dd>
              </div>
            </>
          ) : null}
        </dl>
      </div>

      <div>
        <h3 className="text-sub-heading text-gray-900 mb-3">Timeline</h3>
        {events.length === 0 ? (
          <p className="text-caption text-gray-500">No activity recorded yet.</p>
        ) : (
          <ol className="relative ml-2 border-l border-gray-200 pl-5 space-y-4">
            {events.map((e) => (
              <li key={e.eventId} className="relative">
                <span
                  className="absolute -left-[27px] top-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand-500"
                  aria-hidden="true"
                />
                <div className="text-body text-gray-900">
                  {e.toStatus ? stageLabelOf(e.toStatus) : 'Update'}
                  {operator && e.fromStatus ? (
                    <span className="ml-2 font-mono text-xs text-gray-400">
                      {e.fromStatus} to {e.toStatus}
                    </span>
                  ) : null}
                </div>
                <div className="timestamp-only font-mono text-gray-500" title={absoluteTime(e.at)}>
                  {relativeTime(e.at)}
                </div>
                {operator && e.note ? (
                  <div className="mt-1 text-caption text-gray-600">{e.note}</div>
                ) : null}
                {operator && (e.costDeltaUsd ?? 0) !== 0 ? (
                  <div className="font-mono text-xs text-gray-500">
                    cost +${(e.costDeltaUsd ?? 0).toFixed(2)}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/** Fetching wrapper shared by the drawer and the standalone page. */
export function EpisodeDetailLoader({
  jobId,
  operator,
}: {
  jobId: string;
  operator: boolean;
}) {
  const [data, setData] = useState<DetailPayload | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    fetch(`/api/podcast/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error('bad status');
        return res.json() as Promise<DetailPayload>;
      })
      .then((payload) => {
        setData(payload);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState rows={4} kpis={0} />;
  if (error || !data) return <ErrorState onRetry={load} />;
  return <EpisodeDetailContent data={data} operator={operator} />;
}

/**
 * Desktop right-side drawer (480px, slide-in). Traps focus, closes on
 * Escape, and returns focus to the invoking row (Section 14).
 */
export function EpisodeDrawer({
  jobId,
  operator,
  onClose,
}: {
  jobId: string;
  operator: boolean;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    panel?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'Tab' && panel) {
        const focusables = panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Episode detail">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="animate-slide-in absolute right-0 top-0 h-full w-[min(480px,85vw)] overflow-y-auto bg-white border-l border-gray-200 shadow-card-hover p-6 focus:outline-none"
      >
        <div className="mb-4 flex items-center justify-between">
          <span className="text-label text-gray-500">Episode detail</span>
          <button
            onClick={onClose}
            aria-label="Close episode detail"
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <EpisodeDetailLoader jobId={jobId} operator={operator} />
      </div>
    </div>
  );
}
