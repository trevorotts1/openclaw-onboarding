'use client';

/**
 * Stage pill (design Section 4.5 and 7.2): light tinted background plus
 * strong text of the same hue, rounded-full, text-badge scale. Stage is
 * never conveyed by color alone; the pill always carries its text label and
 * the distinct icon where specified (Section 14).
 */

import { AlertTriangle, CheckCircle2, PauseCircle } from 'lucide-react';
import { stageMetaFor } from '@/lib/podcast/stages';
import type { PodcastStatus, QueueState } from '@/lib/podcast/types';

export default function StagePill({
  status,
  queueState,
  showRaw,
}: {
  status: PodcastStatus;
  queueState: QueueState;
  showRaw?: boolean;
}) {
  const meta = stageMetaFor(status, queueState);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-badge whitespace-nowrap ${meta.pillClass}`}
    >
      {meta.icon === 'check' && <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
      {meta.icon === 'pause' && <PauseCircle className="h-3.5 w-3.5" aria-hidden="true" />}
      {meta.icon === 'alert' && <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
      <span>{meta.clientLabel}</span>
      {showRaw && <span className="font-mono text-xs opacity-70">{meta.rawStatus}</span>}
    </span>
  );
}
