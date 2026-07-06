import { NextRequest, NextResponse } from 'next/server';
import { getLastUpdatedAt, getPodcastReadDb, resolvePodcastClientId } from '@/lib/podcast/db';
import { viewerFromRequest } from '@/lib/podcast/auth';
import { listJobs } from '@/lib/podcast/queries';
import { toClientJob, toOperatorJob } from '@/lib/podcast/serializers';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * GET /api/podcast/jobs?status=&mode=&style=&q=&cursor=&limit=25&since=
 * Read-only job listing (design Section 13). The serializer boundary
 * (Section 9.3) picks client-clean vs operator-verbose per session; a client
 * token NEVER receives operator fields.
 */
export function GET(req: NextRequest): NextResponse {
  const viewer = viewerFromRequest(req);
  if (viewer.kind === 'none') {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const db = getPodcastReadDb();
  if (!db) {
    return NextResponse.json(
      { jobs: [], nextCursor: null, lastUpdatedAt: null },
      { headers: NO_STORE }
    );
  }
  const clientId = resolvePodcastClientId(db);
  if (!clientId) {
    return NextResponse.json(
      { jobs: [], nextCursor: null, lastUpdatedAt: null },
      { headers: NO_STORE }
    );
  }
  const sp = req.nextUrl.searchParams;
  const limitRaw = Number(sp.get('limit') ?? '25');
  const { rows, nextCursor } = listJobs(db, clientId, {
    status: sp.get('status'),
    mode: sp.get('mode'),
    style: sp.get('style'),
    q: sp.get('q'),
    cursor: sp.get('cursor'),
    since: sp.get('since'),
    limit: Number.isFinite(limitRaw) ? limitRaw : 25,
  });
  const serialize = viewer.kind === 'operator' ? toOperatorJob : toClientJob;
  return NextResponse.json(
    {
      jobs: rows.map(serialize),
      nextCursor,
      lastUpdatedAt: getLastUpdatedAt(db, clientId),
    },
    { headers: NO_STORE }
  );
}
