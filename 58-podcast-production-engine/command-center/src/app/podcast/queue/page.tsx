import { cookies, headers } from 'next/headers';
import { Breadcrumb } from '@/components/Breadcrumb';
import QueueView from '@/components/podcast/QueueView';
import { PODCAST_SESSION_COOKIE, resolveViewer } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';

/**
 * /podcast/queue: the credit-out queue with client-clean framing ("On
 * hold"), the 60-day age meter, and the collapsed Expired group (design
 * Section 8.2). Display only; the engine owns every queue mutation.
 */
export default function PodcastQueuePage() {
  const viewer = resolveViewer(
    headers(),
    cookies().get(PODCAST_SESSION_COOKIE)?.value ?? null
  );
  return (
    <div>
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Podcast', href: '/podcast' },
          { label: 'On hold' },
        ]}
      />
      <h1 className="text-page-title text-gray-900 mb-2">On hold</h1>
      <QueueView operator={viewer.kind === 'operator'} />
    </div>
  );
}
