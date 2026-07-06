/**
 * Podcast Production Engine dashboard: stage taxonomy.
 *
 * The single binding label and color map from design Section 7.2. Client
 * labels are what clients see; operator surfaces may also show the raw
 * status. Colors reference existing Command Center palette tokens only, and
 * the publishing stage rides the brand-* utilities so BrandTheme recoloring
 * flows through per client.
 */

import type { PodcastStatus, QueueState } from './types';

/** Pipeline order, received through complete: the 9 progress segments. */
export const PIPELINE_ORDER: PodcastStatus[] = [
  'received',
  'researching',
  'writing',
  'in_qc',
  'generating_art',
  'producing_audio',
  'publishing',
  'enrolling',
  'complete',
];

export interface StageMeta {
  /** Raw status value (operator label). */
  status: PodcastStatus;
  /** Client-facing label (design 7.2, verbatim). */
  clientLabel: string;
  /** Pill classes: light tinted bg plus strong text of the same hue. */
  pillClass: string;
  /** Named icon key; components map this to the lucide icon. */
  icon: 'none' | 'check' | 'pause' | 'alert';
}

export const STAGE_META: Record<PodcastStatus, StageMeta> = {
  received: {
    status: 'received',
    clientLabel: 'Received',
    pillClass: 'bg-blue-50 text-blue-600',
    icon: 'none',
  },
  researching: {
    status: 'researching',
    clientLabel: 'Researching',
    pillClass: 'bg-indigo-50 text-indigo-600',
    icon: 'none',
  },
  writing: {
    status: 'writing',
    clientLabel: 'Writing',
    pillClass: 'bg-emerald-50 text-emerald-600',
    icon: 'none',
  },
  in_qc: {
    status: 'in_qc',
    clientLabel: 'Quality review',
    pillClass: 'bg-amber-50 text-amber-600',
    icon: 'none',
  },
  generating_art: {
    status: 'generating_art',
    clientLabel: 'Creating artwork',
    pillClass: 'bg-violet-50 text-violet-600',
    icon: 'none',
  },
  producing_audio: {
    status: 'producing_audio',
    clientLabel: 'Producing audio',
    pillClass: 'bg-cyan-50 text-cyan-600',
    icon: 'none',
  },
  publishing: {
    status: 'publishing',
    clientLabel: 'Publishing',
    pillClass: 'bg-brand-50 text-brand-700',
    icon: 'none',
  },
  enrolling: {
    status: 'enrolling',
    clientLabel: 'Finalizing',
    pillClass: 'bg-teal-50 text-teal-600',
    icon: 'none',
  },
  complete: {
    status: 'complete',
    clientLabel: 'Live',
    pillClass: 'bg-emerald-50 text-emerald-700',
    icon: 'check',
  },
  queued_credit_out: {
    status: 'queued_credit_out',
    clientLabel: 'On hold',
    pillClass: 'bg-orange-50 text-orange-600',
    icon: 'pause',
  },
  failed: {
    status: 'failed',
    clientLabel: 'Needs attention',
    pillClass: 'bg-red-50 text-red-600',
    icon: 'alert',
  },
};

/** Expired treatment for queue_state = aged_out rows (design 7.2 last row). */
export const AGED_OUT_META = {
  clientLabel: 'Expired',
  pillClass: 'bg-gray-100 text-gray-600 ring-1 ring-red-200',
  icon: 'none' as const,
};

/** Effective stage meta for a job, honoring the aged-out override. */
export function stageMetaFor(status: PodcastStatus, queueState: QueueState): {
  clientLabel: string;
  pillClass: string;
  icon: 'none' | 'check' | 'pause' | 'alert';
  rawStatus: PodcastStatus;
} {
  if (queueState === 'aged_out') {
    return { ...AGED_OUT_META, rawStatus: status };
  }
  const meta = STAGE_META[status] ?? STAGE_META.received;
  return {
    clientLabel: meta.clientLabel,
    pillClass: meta.pillClass,
    icon: meta.icon,
    rawStatus: status,
  };
}

/**
 * Progress index for the 9-segment meter (design 7.2). Returns the count of
 * filled segments and whether the current one pulses. Held jobs freeze at
 * their resume stage position; failed jobs freeze where they failed.
 */
export function progressFor(status: PodcastStatus, resumeStage: string | null): {
  filled: number;
  total: number;
  pulsing: boolean;
} {
  const total = PIPELINE_ORDER.length;
  if (status === 'complete') return { filled: total, total, pulsing: false };
  if (status === 'failed') return { filled: 0, total, pulsing: false };
  if (status === 'queued_credit_out') {
    const idx = PIPELINE_ORDER.indexOf((resumeStage ?? 'received') as PodcastStatus);
    return { filled: Math.max(idx, 0) + 1, total, pulsing: false };
  }
  const idx = PIPELINE_ORDER.indexOf(status);
  return { filled: Math.max(idx, 0) + 1, total, pulsing: true };
}

/** Friendly labels for mode and style values. */
export const MODE_LABELS: Record<string, string> = {
  personal_podcast_style: 'Personal',
  interview_style_podcast: 'Interview',
};

export const STYLE_LABELS: Record<string, string> = {
  counter_intuitive: 'Counter Intuitive',
  vulnerable: 'Vulnerable',
  provocative: 'Provocative',
  passionate: 'Passionate',
};

/** Fixed client-facing hold copy (design Section 8.3, verbatim). */
export const HOLD_PILL_COPY = 'On hold';
export function holdBannerCopy(heldDays: number): string {
  return (
    'Production is briefly paused. Your episode is safe, nothing you submitted ' +
    'has been lost, and it will resume automatically. Held for ' +
    String(heldDays) +
    ' days.'
  );
}

/** Fixed client-facing failed copy (design Section 8.1 item 6, verbatim). */
export const FAILED_BANNER_COPY =
  'This episode needs attention. Our team has been notified and is on it. Nothing is required from you.';

/** Fixed client-facing expired copy (design Section 8.2 item 2, verbatim). */
export const EXPIRED_ROW_COPY =
  'This submission expired before it could be completed. Please resubmit when ready.';

/** Empty state copy (design Section 8.5, verbatim). */
export const EMPTY_STATE_COPY =
  'No episodes yet. Your first submission will appear here the moment it arrives.';
