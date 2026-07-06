import { Breadcrumb } from '@/components/Breadcrumb';
import PodcastOverview from '@/components/podcast/PodcastOverview';

export const dynamic = 'force-dynamic';

/**
 * /podcast/ops: the operator pipeline overview (design Sections 6 and 9).
 * Same pipeline as the client view plus costs, attempts, errors, and model
 * names, all sourced from the operator serializer at the API boundary.
 */
export default function PodcastOpsPage() {
  return (
    <div>
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Podcast', href: '/podcast' },
          { label: 'Ops' },
        ]}
      />
      <PodcastOverview operator />
    </div>
  );
}
