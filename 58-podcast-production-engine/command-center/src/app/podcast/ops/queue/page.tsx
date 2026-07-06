import { Breadcrumb } from '@/components/Breadcrumb';
import QueueView from '@/components/podcast/QueueView';

export const dynamic = 'force-dynamic';

/**
 * /podcast/ops/queue: the operator queue view with service names, deadlines,
 * resume stages, and the age-out ledger (design Sections 6 and 8.2).
 */
export default function PodcastOpsQueuePage() {
  return (
    <div>
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Podcast', href: '/podcast' },
          { label: 'Ops', href: '/podcast/ops' },
          { label: 'Queue' },
        ]}
      />
      <h1 className="text-page-title text-gray-900 mb-2">Credit-out queue</h1>
      <QueueView operator />
    </div>
  );
}
