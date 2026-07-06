import { NextRequest, NextResponse } from 'next/server';
import { getPodcastReadDb, resolvePodcastClientId } from '@/lib/podcast/db';
import { listTokens, mintToken, viewerFromRequest } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * Operator-only token management (design Sections 11.3 and 13). These are
 * the SOLE write endpoints of the podcast dashboard, and they write only
 * podcast_dashboard_tokens through the guarded auth handle. Raw token values
 * are returned exactly once at mint time and never persisted or logged.
 */

function requireOperator(req: NextRequest): NextResponse | null {
  const viewer = viewerFromRequest(req);
  if (viewer.kind !== 'operator') {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  return null;
}

/** GET /api/podcast/ops/tokens: list (ids, labels, timestamps; never hashes). */
export function GET(req: NextRequest): NextResponse {
  const denied = requireOperator(req);
  if (denied) return denied;
  const db = getPodcastReadDb();
  const clientId = db ? resolvePodcastClientId(db) : null;
  if (!db || !clientId) {
    return NextResponse.json({ tokens: [] }, { headers: NO_STORE });
  }
  return NextResponse.json({ tokens: listTokens(clientId) }, { headers: NO_STORE });
}

/** POST /api/podcast/ops/tokens { label } -> { tokenId, rawTokenShownOnce } */
export async function POST(req: NextRequest): Promise<NextResponse> {
  const denied = requireOperator(req);
  if (denied) return denied;
  const db = getPodcastReadDb();
  const clientId = db ? resolvePodcastClientId(db) : null;
  if (!db || !clientId) {
    return NextResponse.json(
      { error: 'The podcast engine has not been provisioned on this box yet.' },
      { status: 409, headers: NO_STORE }
    );
  }
  let label: string | null = null;
  try {
    const body = (await req.json()) as { label?: unknown };
    if (typeof body?.label === 'string') label = body.label.slice(0, 120);
  } catch {
    label = null;
  }
  const minted = mintToken(clientId, label);
  if (!minted) {
    return NextResponse.json({ error: 'Unable to mint a token.' }, { status: 500, headers: NO_STORE });
  }
  return NextResponse.json(minted, { headers: NO_STORE });
}
