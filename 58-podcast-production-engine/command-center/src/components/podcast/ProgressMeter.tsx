'use client';

/**
 * Thin 9-segment pipeline progress meter (design Section 7.2): filled
 * segments in brand-500 (BrandTheme recolors them per client), the current
 * segment pulsing while in flight. Carries a real progressbar role with
 * aria values (Section 14).
 */

import { progressFor } from '@/lib/podcast/stages';
import type { PodcastStatus } from '@/lib/podcast/types';

export default function ProgressMeter({
  status,
  resumeStage,
}: {
  status: PodcastStatus;
  resumeStage?: string | null;
}) {
  const { filled, total, pulsing } = progressFor(status, resumeStage ?? null);
  return (
    <div
      role="progressbar"
      aria-valuenow={filled}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-label={`Pipeline progress: step ${filled} of ${total}`}
      className="flex items-center gap-0.5 w-full max-w-[180px]"
    >
      {Array.from({ length: total }).map((_, i) => {
        const isFilled = i < filled;
        const isCurrent = i === filled - 1 && pulsing;
        return (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full ${
              isFilled ? 'bg-brand-500' : 'bg-gray-200'
            } ${isCurrent ? 'animate-pulse' : ''}`}
          />
        );
      })}
    </div>
  );
}
