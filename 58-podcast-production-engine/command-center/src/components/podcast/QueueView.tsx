'use client';

/**
 * Credit-out queue view (design Section 8.2): ON HOLD rows oldest first
 * with the 0 to 60 day age meter (green, amber, red bands), a red left
 * border at 50 days and up, and the EXPIRED group collapsed by default
 * covering the last 90 days. Client copy never names the depleted service
 * or says "credits"; the operator view adds service, deadline, and resume
 * stage. The dashboard displays all of this and mutates none of it.
 */

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, PauseCircle } from 'lucide-react';
import { EmptyState, ErrorState, LoadingState } from './states';
import type { ClientQueueRow, OperatorQueueRow } from '@/lib/podcast/types';
import { EXPIRED_ROW_COPY, MODE_LABELS, STYLE_LABELS } from '@/lib/podcast/stages';
import { absoluteTime, avatarGradientIndex, displayName, initialsOf, relativeTime } from '@/lib/podcast/format';

type AnyQueueRow = ClientQueueRow & Partial<OperatorQueueRow>;

interface QueueResponse {
  held: AnyQueueRow[];
  agedOut: AnyQueueRow[];
}

const HOLD_LIMIT_DAYS = 60;

function AgeMeter({ heldDays }: { heldDays: number }) {
  const clamped = Math.min(heldDays, HOLD_LIMIT_DAYS);
  const pct = (clamped / HOLD_LIMIT_DAYS) * 100;
  const barColor = heldDays > 45 ? 'bg-red-500' : heldDays >= 30 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="flex w-full items-center gap-3">
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={HOLD_LIMIT_DAYS}
        aria-label={`${heldDays} of 60 days on hold`}
        className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100"
      >
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-caption text-gray-600 whitespace-nowrap">
        {heldDays} of 60 days
      </span>
    </div>
  );
}

function QueueRowCard({ row, operator }: { row: AnyQueueRow; operator: boolean }) {
  const name = displayName(row.submitterFirstName, row.submitterLastName);
  const gradient = avatarGradientIndex(row.submitterFirstName, row.submitterLastName);
  const heldDays = row.heldDays ?? 0;
  const nearDrop = heldDays >= 50;
  return (
    <div
      className={`rounded-xl border border-gray-200 bg-white px-4 py-3 ${
        nearDrop ? 'border-l-[3px] border-l-red-500' : ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`avatar-gradient-${gradient} flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold text-white`}
          aria-hidden="true"
        >
          {initialsOf(row.submitterFirstName, row.submitterLastName)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-body font-semibold text-gray-900 truncate">{name}</div>
          <div className="text-caption text-gray-500 truncate">
            {row.episodeTitle ?? 'Untitled, in progress'} · {MODE_LABELS[row.mode] ?? row.mode} · {STYLE_LABELS[row.style] ?? row.style}
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-orange-50 px-2.5 py-0.5 text-badge text-orange-600 whitespace-nowrap">
          <PauseCircle className="h-3.5 w-3.5" aria-hidden="true" />
          Held for {heldDays} days
        </span>
      </div>
      <div className="mt-3">
        <AgeMeter heldDays={heldDays} />
      </div>
      {operator ? (
        <div className="mt-2 font-mono text-xs text-gray-500">
          service: {row.queuedService ?? 'unknown'} · deadline: {row.queueDeadline ?? 'unset'} · resume: {row.resumeStage ?? 'unset'} · payload: {row.payloadPresent ? 'present' : 'absent'}
          {nearDrop && row.queueDeadline ? (
            <span className="ml-2 text-red-600">Ages out on {absoluteTime(row.queueDeadline)}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function QueueView({ operator }: { operator: boolean }) {
  const [data, setData] = useState<QueueResponse | null>(null);
  const [error, setError] = useState(false);
  const [expiredOpen, setExpiredOpen] = useState(false);

  const load = useCallback(() => {
    setError(false);
    fetch('/api/podcast/queue', { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error('bad status');
        return res.json() as Promise<QueueResponse>;
      })
      .then(setData)
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState onRetry={load} />;
  if (!data) return <LoadingState rows={4} kpis={0} />;

  const { held, agedOut } = data;

  return (
    <div className="space-y-8">
      <p className="text-caption text-gray-500 max-w-2xl">
        Episodes shown here are paused, not lost. Each one resumes automatically, and nothing is
        removed without appearing in the expired list below.
      </p>

      <section aria-label="On hold">
        <h2 className="text-section text-gray-900 mb-3">On hold</h2>
        {held.length === 0 ? (
          <EmptyState message="Nothing is on hold right now." />
        ) : (
          <div className="space-y-2">
            {held.map((row) => (
              <QueueRowCard key={row.jobId} row={row} operator={operator} />
            ))}
          </div>
        )}
      </section>

      <section aria-label="Expired">
        <button
          onClick={() => setExpiredOpen((o) => !o)}
          className="mb-3 flex items-center gap-2 text-section text-gray-900"
          aria-expanded={expiredOpen}
        >
          {expiredOpen ? (
            <ChevronDown className="h-5 w-5 text-gray-400" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-5 w-5 text-gray-400" aria-hidden="true" />
          )}
          Expired
          <span className="text-caption font-normal text-gray-500">{agedOut.length}</span>
        </button>
        {expiredOpen ? (
          agedOut.length === 0 ? (
            <p className="text-caption text-gray-500">Nothing has expired in the last 90 days.</p>
          ) : (
            <div className="space-y-2">
              {agedOut.map((row) => (
                <div key={row.jobId} className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-body font-medium text-gray-700 truncate">
                        {displayName(row.submitterFirstName, row.submitterLastName)}
                        {row.episodeTitle ? ` · ${row.episodeTitle}` : ''}
                      </div>
                      <div className="text-caption text-gray-500">{EXPIRED_ROW_COPY}</div>
                    </div>
                    <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-badge text-gray-600 ring-1 ring-red-200 whitespace-nowrap">
                      Expired
                    </span>
                    {row.agedOutAt ? (
                      <span className="timestamp-only font-mono text-gray-400" title={absoluteTime(row.agedOutAt)}>
                        {relativeTime(row.agedOutAt)}
                      </span>
                    ) : null}
                  </div>
                  {operator ? (
                    <div className="mt-2 font-mono text-xs text-gray-500">
                      service: {row.queuedService ?? 'unknown'} · payload: {row.payloadPresent ? 'present' : 'purged'}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )
        ) : null}
      </section>
    </div>
  );
}
