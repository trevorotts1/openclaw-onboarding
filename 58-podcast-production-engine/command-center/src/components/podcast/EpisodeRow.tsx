'use client';

/**
 * Episode row (design Section 7.3). Desktop: avatar, identity, episode
 * block, stage pill plus progress meter, timing, chevron. Mobile: stacked
 * card (Section 12). Operator rows append cost, QC attempt badge, model,
 * and failed step. Rows are focusable and act as links (Section 14).
 */

import { ChevronRight } from 'lucide-react';
import StagePill from './StagePill';
import ProgressMeter from './ProgressMeter';
import type { ClientJob, OperatorJob } from '@/lib/podcast/types';
import { MODE_LABELS, STYLE_LABELS } from '@/lib/podcast/stages';
import {
  absoluteTime,
  avatarGradientIndex,
  displayName,
  initialsOf,
  relativeTime,
} from '@/lib/podcast/format';

export type AnyJob = ClientJob & Partial<Pick<OperatorJob,
  'costAccruedUsd' | 'attemptCount' | 'writingModel' | 'failedStep'>>;

export default function EpisodeRow({
  job,
  operator,
  onOpen,
}: {
  job: AnyJob;
  operator: boolean;
  onOpen: (jobId: string) => void;
}) {
  const name = displayName(job.submitterFirstName, job.submitterLastName);
  const gradient = avatarGradientIndex(job.submitterFirstName, job.submitterLastName);
  const inFlight = job.status !== 'complete' && job.status !== 'failed';
  const contactLine = [job.submitterEmail, job.submitterPhone].filter(Boolean).join(' · ');
  const qcTone =
    (job.attemptCount ?? 0) >= 3
      ? 'bg-red-50 text-red-600'
      : (job.attemptCount ?? 0) === 2
        ? 'bg-amber-50 text-amber-600'
        : 'bg-gray-100 text-gray-600';

  return (
    <button
      type="button"
      onClick={() => onOpen(job.jobId)}
      aria-label={`Open episode ${job.episodeTitle ?? 'in progress'} from ${name}`}
      className="w-full text-left rounded-xl border border-gray-200 bg-white px-4 py-3 transition-colors hover:border-brand-300 hover:shadow-card focus:outline-none focus:ring-2 focus:ring-brand-500"
    >
      <div className="flex flex-col gap-2 md:grid md:grid-cols-[auto_minmax(0,1.2fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto_auto_auto] md:items-center md:gap-4">
        <div className="flex items-center gap-3 md:contents">
          <span
            className={`avatar-gradient-${gradient} flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold text-white`}
            aria-hidden="true"
          >
            {initialsOf(job.submitterFirstName, job.submitterLastName)}
          </span>
          <div className="min-w-0">
            <div className="text-body font-semibold text-gray-900 truncate">{name}</div>
            {contactLine ? (
              <div className="timestamp-only font-mono text-gray-500 truncate">{contactLine}</div>
            ) : null}
          </div>
        </div>

        <div className="min-w-0">
          {job.episodeTitle ? (
            <div className="text-label font-medium text-gray-900 truncate">{job.episodeTitle}</div>
          ) : (
            <div className="text-label italic text-gray-400">Untitled, in progress</div>
          )}
          <div className="text-caption text-gray-500">
            {MODE_LABELS[job.mode] ?? job.mode} · {STYLE_LABELS[job.style] ?? job.style}
          </div>
        </div>

        <div className="flex flex-col gap-1.5 md:min-w-[160px]">
          <StagePill status={job.status} queueState={job.queueState} />
          {inFlight ? <ProgressMeter status={job.status} /> : null}
        </div>

        <div className="text-caption text-gray-500">
          <div title={absoluteTime(job.createdAt)}>Submitted {relativeTime(job.createdAt)}</div>
          {job.completedAt ? (
            <div title={absoluteTime(job.completedAt)}>Published {relativeTime(job.completedAt)}</div>
          ) : null}
        </div>

        {operator ? (
          <div className="flex items-center gap-2 md:flex-col md:items-end md:gap-1">
            <span className="font-mono text-caption text-gray-700 text-right">
              ${(job.costAccruedUsd ?? 0).toFixed(2)}
            </span>
            {(job.attemptCount ?? 0) > 0 ? (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${qcTone}`}>
                QC x{job.attemptCount}
              </span>
            ) : null}
            {job.writingModel ? (
              <span className="text-caption text-gray-400 truncate max-w-[140px]">{job.writingModel}</span>
            ) : null}
            {job.status === 'failed' && job.failedStep ? (
              <span className="font-mono text-xs text-red-600 truncate max-w-[140px]">{job.failedStep}</span>
            ) : null}
          </div>
        ) : (
          <span aria-hidden="true" className="hidden md:block" />
        )}

        <ChevronRight className="hidden h-4 w-4 flex-shrink-0 text-gray-400 md:block" aria-hidden="true" />
      </div>
    </button>
  );
}
