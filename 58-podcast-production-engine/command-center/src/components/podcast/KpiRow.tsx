'use client';

/**
 * KPI row (design Section 7.1 item 2): 4 white cards in the CEODashboard
 * grid. Client view: In production, Published, On hold, Needs attention.
 * Operator view swaps the fourth card for Spend this month.
 */

import { Activity, AlertTriangle, CheckCircle2, DollarSign, PauseCircle } from 'lucide-react';
import type { PodcastSummary } from '@/lib/podcast/types';
import { usd } from '@/lib/podcast/format';

function KpiCard({
  title,
  value,
  caption,
  icon,
  accent,
}: {
  title: string;
  value: string;
  caption?: string;
  icon: React.ReactNode;
  accent?: 'amber' | 'red' | null;
}) {
  const valueClass =
    accent === 'amber' ? 'text-amber-600' : accent === 'red' ? 'text-red-600' : 'text-gray-900';
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-4 sm:p-5">
      <div className="flex items-center justify-between">
        <span className="text-label text-gray-500">{title}</span>
        <span className="text-gray-400">{icon}</span>
      </div>
      <div className={`text-[40px] leading-[1.1] font-black lg:text-kpi-value ${valueClass}`}>
        {value}
      </div>
      {caption ? <div className="text-caption text-gray-500">{caption}</div> : null}
    </div>
  );
}

export default function KpiRow({
  summary,
  operator,
}: {
  summary: PodcastSummary;
  operator: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KpiCard
        title="In production"
        value={String(summary.inProduction)}
        icon={<Activity className="h-5 w-5" aria-hidden="true" />}
      />
      <KpiCard
        title="Published"
        value={String(summary.published)}
        caption={`+${summary.publishedThisMonth} this month`}
        icon={<CheckCircle2 className="h-5 w-5" aria-hidden="true" />}
      />
      <KpiCard
        title="On hold"
        value={String(summary.held)}
        icon={<PauseCircle className="h-5 w-5" aria-hidden="true" />}
        accent={summary.held > 0 ? 'amber' : null}
      />
      {operator ? (
        <KpiCard
          title="Spend this month"
          value={usd(summary.spendThisMonth ?? 0)}
          icon={<DollarSign className="h-5 w-5" aria-hidden="true" />}
        />
      ) : (
        <KpiCard
          title="Needs attention"
          value={String(summary.failed)}
          icon={<AlertTriangle className="h-5 w-5" aria-hidden="true" />}
          accent={summary.failed > 0 ? 'red' : null}
        />
      )}
    </div>
  );
}
