import { NextRequest, NextResponse } from 'next/server';
import { getPodcastReadDb, resolvePodcastClientId } from '@/lib/podcast/db';
import { viewerFromRequest } from '@/lib/podcast/auth';
import { summaryCounts } from '@/lib/podcast/queries';
import { toSummary } from '@/lib/podcast/serializers';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * GET /api/podcast/summary
 * KPI counts (design Section 13). spendThisMonth appears ONLY in the
 * operator serialization.
 */
export function GET(req: NextRequest): NextResponse {
  const viewer = viewerFromRequest(req);
  if (viewer.kind === 'none') {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const db = getPodcastReadDb();
  const clientId = db ? resolvePodcastClientId(db) : null;
  if (!db || !clientId) {
    return NextResponse.json(
      toSummary(
        { inProduction: 0, published: 0, publishedThisMonth: 0, held: 0, failed: 0, spendThisMonth: 0 },
        viewer.kind === 'operator'
      ),
      { headers: NO_STORE }
    );
  }
  const counts = summaryCounts(db, clientId);
  return NextResponse.json(toSummary(counts, viewer.kind === 'operator'), { headers: NO_STORE });
}
