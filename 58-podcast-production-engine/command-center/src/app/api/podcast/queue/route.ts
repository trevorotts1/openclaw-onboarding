import { NextRequest, NextResponse } from 'next/server';
import { getPodcastReadDb, resolvePodcastClientId } from '@/lib/podcast/db';
import { viewerFromRequest } from '@/lib/podcast/auth';
import { hasPayload, listAgedOut, listHeld } from '@/lib/podcast/queries';
import { toClientQueueRow, toOperatorQueueRow } from '@/lib/podcast/serializers';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * GET /api/podcast/queue -> { held, agedOut }
 * Credit-out queue view (design Section 8.2). Client serialization never
 * names the depleted service or exposes deadlines; operator serialization
 * adds service, deadline, resume stage, and payload presence.
 */
export function GET(req: NextRequest): NextResponse {
  const viewer = viewerFromRequest(req);
  if (viewer.kind === 'none') {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const db = getPodcastReadDb();
  const clientId = db ? resolvePodcastClientId(db) : null;
  if (!db || !clientId) {
    return NextResponse.json({ held: [], agedOut: [] }, { headers: NO_STORE });
  }
  const held = listHeld(db, clientId);
  const agedOut = listAgedOut(db, clientId);
  if (viewer.kind === 'operator') {
    return NextResponse.json(
      {
        held: held.map((r) => toOperatorQueueRow(r, hasPayload(db, r.job_id))),
        agedOut: agedOut.map((r) => toOperatorQueueRow(r, hasPayload(db, r.job_id))),
      },
      { headers: NO_STORE }
    );
  }
  return NextResponse.json(
    { held: held.map(toClientQueueRow), agedOut: agedOut.map(toClientQueueRow) },
    { headers: NO_STORE }
  );
}
