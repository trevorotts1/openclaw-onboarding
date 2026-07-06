import { Breadcrumb } from '@/components/Breadcrumb';
import OpsAccess from '@/components/podcast/OpsAccess';

export const dynamic = 'force-dynamic';

/**
 * /podcast/ops/access: dashboard token management (design Section 11.3).
 * Mint, label, revoke; raw values shown exactly once; the churn runbook
 * pointer lives here too.
 */
export default function PodcastOpsAccessPage() {
  return (
    <div>
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Podcast', href: '/podcast' },
          { label: 'Ops', href: '/podcast/ops' },
          { label: 'Access' },
        ]}
      />
      <h1 className="text-page-title text-gray-900 mb-2">Dashboard access</h1>
      <OpsAccess />
    </div>
  );
}
