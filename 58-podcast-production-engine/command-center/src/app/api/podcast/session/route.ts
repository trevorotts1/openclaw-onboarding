import { NextRequest, NextResponse } from 'next/server';
import {
  PODCAST_SESSION_COOKIE,
  SESSION_COOKIE_OPTIONS,
  createSessionFromRawToken,
} from '@/lib/podcast/auth';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_STORE = { 'Cache-Control': 'no-store' };

/**
 * POST /api/podcast/session  { token }
 * The one-time token paste gate (design 11.2). On success the response sets
 * an HttpOnly, Secure, SameSite=Lax cookie holding a session REFERENCE, not
 * the token. Failures are uniform and detail-free (fail closed). The raw
 * token is hashed immediately and never stored or logged.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  let token: unknown = null;
  try {
    const body = (await req.json()) as { token?: unknown };
    token = body?.token;
  } catch {
    token = null;
  }
  if (typeof token !== 'string' || token.length < 8 || token.length > 256) {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const cookieValue = createSessionFromRawToken(token);
  if (!cookieValue) {
    return NextResponse.json({ error: 'Access unavailable' }, { status: 401, headers: NO_STORE });
  }
  const res = NextResponse.json({ ok: true }, { headers: NO_STORE });
  res.cookies.set(PODCAST_SESSION_COOKIE, cookieValue, SESSION_COOKIE_OPTIONS);
  return res;
}

/** DELETE /api/podcast/session: sign out (clears the cookie only). */
export function DELETE(): NextResponse {
  const res = NextResponse.json({ ok: true }, { headers: NO_STORE });
  res.cookies.set(PODCAST_SESSION_COOKIE, '', { ...SESSION_COOKIE_OPTIONS, maxAge: 0 });
  return res;
}
