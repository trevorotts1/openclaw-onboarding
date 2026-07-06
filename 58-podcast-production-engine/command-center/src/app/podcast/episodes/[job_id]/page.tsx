import { cookies, headers } from 'next/headers';
import { Breadcrumb } from '@/components/Breadcrumb';
import { EpisodeDetailLoader } from '@/components/podcast/EpisodeDetail';
import { PODCAST_SESSION_COOKIE, resolveViewer } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';

/**
 * /podcast/episodes/[job_id]: the episode detail as a full page (mobile and
 * direct links; desktop interactions use the in-place drawer, design
 * Section 8.1). Data loads through the same authenticated, serializer-gated
 * API as everything else.
 */
export default function EpisodeDetailPage({ params }: { params: { job_id: string } }) {
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
          { label: 'Episode' },
        ]}
      />
      <div className="mx-auto max-w-2xl">
        <EpisodeDetailLoader jobId={params.job_id} operator={viewer.kind === 'operator'} />
      </div>
    </div>
  );
}
