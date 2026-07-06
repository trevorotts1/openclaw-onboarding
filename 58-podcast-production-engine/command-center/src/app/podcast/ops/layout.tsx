import { headers } from 'next/headers';
import { ShieldAlert } from 'lucide-react';
import { isOperatorRequest } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';

/**
 * /podcast/ops gate (design Section 9.3, 11.3): operator sessions only.
 * A client dashboard token NEVER unlocks this subtree; the check here is
 * Cloudflare Access operator email or MC_API_TOKEN bearer, nothing else.
 * Non-operators get a clean branded refusal with zero detail (fail closed),
 * and the ops nav entry never renders for them in the first place.
 */
export default function PodcastOpsLayout({ children }: { children: React.ReactNode }) {
  const { operator } = isOperatorRequest(headers());
  if (!operator) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-card">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
            <ShieldAlert className="h-6 w-6 text-gray-400" aria-hidden="true" />
          </span>
          <h1 className="mt-4 text-card-title text-gray-900">Access unavailable</h1>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
