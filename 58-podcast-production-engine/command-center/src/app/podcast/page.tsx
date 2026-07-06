import { cookies, headers } from 'next/headers';
import { Breadcrumb } from '@/components/Breadcrumb';
import PodcastOverview from '@/components/podcast/PodcastOverview';
import { PODCAST_SESSION_COOKIE, resolveViewer } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';

/**
 * /podcast: the client pipeline overview (design Section 7). The client
 * bundle receives only client-clean serializations; the operator flag here
 * merely widens what an ALREADY authenticated operator sees, and the API
 * decides per request what it will actually serve.
 */
export default function PodcastPage() {
  const viewer = resolveViewer(
    headers(),
    cookies().get(PODCAST_SESSION_COOKIE)?.value ?? null
  );
  return (
    <div>
      <Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Podcast' }]} />
      <PodcastOverview operator={viewer.kind === 'operator'} />
    </div>
  );
}
