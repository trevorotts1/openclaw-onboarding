import type { Metadata } from 'next';
import { cookies, headers } from 'next/headers';
import PodcastShell from '@/components/podcast/PodcastShell';
import TokenGate from '@/components/podcast/TokenGate';
import { PODCAST_SESSION_COOKIE, resolveViewer } from '@/lib/podcast/auth';

export const metadata: Metadata = {
  title: 'Podcast Studio',
  description: 'Every episode, from submission to published.',
};

export const dynamic = 'force-dynamic';

/**
 * /podcast route group layout (design Sections 4.4, 6, 11).
 *
 * Auth is resolved server-side on EVERY request: Cloudflare Access rides in
 * front (existing middleware), then the podcast session cookie or operator
 * identity decides what renders. No valid session means the token gate, and
 * nothing else, is sent to the browser; episode data never reaches an
 * unauthenticated client because the API routes enforce the same check
 * independently (defense in depth, fail closed).
 */
export default function PodcastLayout({ children }: { children: React.ReactNode }) {
  const cookieValue = cookies().get(PODCAST_SESSION_COOKIE)?.value ?? null;
  const viewer = resolveViewer(headers(), cookieValue);
  const isOperator = viewer.kind === 'operator';

  return (
    <PodcastShell isOperator={isOperator}>
      <div className="mx-auto w-full max-w-[1400px] px-4 py-6 md:px-8 md:py-8">
        {viewer.kind === 'none' ? <TokenGate /> : children}
      </div>
    </PodcastShell>
  );
}
