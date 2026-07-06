import { NextRequest, NextResponse } from 'next/server';
import { revokeToken, viewerFromRequest } from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * DELETE /api/podcast/ops/tokens/[tokenId] { reason } -> { revokedAt }
 * Revocation is a single UPDATE setting revoked_at; the effect is immediate
 * on the next request because sessions re-validate against the token row
 * every time (design 11.3, acceptance criterion 7).
 */
export async function DELETE(
  req: NextRequest,
  { params }: { params: { tokenId: string } }
): Promise<NextResponse> {
  const viewer = viewerFromRequest(req);
  if (viewer.kind !== 'operator') {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const tokenId = params.tokenId;
  if (!/^pdt_[A-Za-z0-9_-]+$/.test(tokenId)) {
    return NextResponse.json({ error: 'Not found' }, { status: 404, headers: NO_STORE });
  }
  let reason: string | null = null;
  try {
    const body = (await req.json()) as { reason?: unknown };
    if (typeof body?.reason === 'string') reason = body.reason.slice(0, 240);
  } catch {
    reason = null;
  }
  const result = revokeToken(tokenId, reason);
  if (!result) {
    return NextResponse.json({ error: 'Not found' }, { status: 404, headers: NO_STORE });
  }
  return NextResponse.json(result, { headers: NO_STORE });
}
