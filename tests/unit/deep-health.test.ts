/**
 * deep-health.test.ts — unit tests for src/lib/health/deep-checks.ts
 *
 * Truth-table coverage: docs/B1-truth-table.md
 *
 * Each test corresponds to a named row in the truth table.  The row number
 * is included in the test name so diffs and failures are traceable to the spec.
 *
 * REDO #1 fix: Row 31a test added — covers the previously untested quadrant
 * NEXT_PUBLIC_APP_URL=unset + CC_PUBLIC_URL=non-localhost public domain → FAIL.
 * The existing 'NEXT_PUBLIC_APP_URL unset' test (formerly line ~9260) left
 * CC_PUBLIC_URL also unset, exercising Row 40/41 (PASS), not Row 31a.
 */

import { checkNextPublicAppUrl } from '../../src/lib/health/deep-checks';

// ── Helpers ───────────────────────────────────────────────────────────────────

const APP_URL_KEY = 'NEXT_PUBLIC_APP_URL';
const CC_URL_KEY  = 'CC_PUBLIC_URL';

function setEnv(appUrl?: string, ccUrl?: string) {
  if (appUrl !== undefined) {
    process.env[APP_URL_KEY] = appUrl;
  } else {
    delete process.env[APP_URL_KEY];
  }
  if (ccUrl !== undefined) {
    process.env[CC_URL_KEY] = ccUrl;
  } else {
    delete process.env[CC_URL_KEY];
  }
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  delete process.env[APP_URL_KEY];
  delete process.env[CC_URL_KEY];
});

afterEach(() => {
  delete process.env[APP_URL_KEY];
  delete process.env[CC_URL_KEY];
});

// ── Row 40/41 — both unset → PASS ─────────────────────────────────────────────

describe('checkNextPublicAppUrl', () => {
  it('Row 40/41: NEXT_PUBLIC_APP_URL unset + CC_PUBLIC_URL unset → pass=true (localhost/dev mode)', async () => {
    setEnv(undefined, undefined);
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });

  it('Row 41: NEXT_PUBLIC_APP_URL="" + CC_PUBLIC_URL="" → pass=true', async () => {
    setEnv('', '');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });

  // ── Row 31a — REDO #1 false-green fix ──────────────────────────────────────
  //
  // This test was MISSING before REDO #1.  The quadrant:
  //   NEXT_PUBLIC_APP_URL = unset
  //   CC_PUBLIC_URL       = non-localhost public domain
  // was not exercised.  The early-return guard returned pass=true (false-green).
  // The fix changes the guard to return pass=false for this quadrant.

  it('Row 31a: NEXT_PUBLIC_APP_URL unset + CC_PUBLIC_URL=non-localhost → pass=false (CF-tunnel mode, missing app URL)', async () => {
    delete process.env[APP_URL_KEY];
    process.env[CC_URL_KEY] = 'https://demo.zerohumanworkforce.com';
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
    expect(result.detail).toMatch(/CF-tunnel mode detected/i);
  });

  it('Row 31a variant: NEXT_PUBLIC_APP_URL="" + CC_PUBLIC_URL=https://karen.zerohumanworkforce.com → pass=false', async () => {
    setEnv('', 'https://karen.zerohumanworkforce.com');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
  });

  it('Row 31a variant: CC_PUBLIC_URL=https://corey.zerohumanworkforce.com → detail mentions tunnel', async () => {
    setEnv(undefined, 'https://corey.zerohumanworkforce.com');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
    expect(result.detail).toMatch(/tunnel/i);
  });

  // ── Row 31 — both set and matching → PASS ──────────────────────────────────

  it('Row 31: NEXT_PUBLIC_APP_URL=x.zhw.com + CC_PUBLIC_URL=x.zhw.com (matching) → pass=true', async () => {
    const url = 'https://x.zerohumanworkforce.com';
    setEnv(url, url);
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });

  it('Row 31: trailing-slash normalisation — pass=true', async () => {
    setEnv('https://x.zerohumanworkforce.com/', 'https://x.zerohumanworkforce.com');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });

  // ── Row 32 — non-localhost URL + CC_PUBLIC_URL absent/invalid → FAIL ────────

  it('Row 32: NEXT_PUBLIC_APP_URL=non-localhost + CC_PUBLIC_URL unset → pass=false', async () => {
    setEnv('https://x.zerohumanworkforce.com', undefined);
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
  });

  it('Row 32: NEXT_PUBLIC_APP_URL=non-localhost + CC_PUBLIC_URL mismatched → pass=false', async () => {
    setEnv('https://x.zerohumanworkforce.com', 'https://y.zerohumanworkforce.com');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
  });

  it('Row 50: CC_PUBLIC_URL="not-a-url" → pass=false', async () => {
    setEnv('https://x.zerohumanworkforce.com', 'not-a-url');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(false);
  });

  // ── Row 20/42 — localhost primary URL → PASS ────────────────────────────────

  it('Row 20: NEXT_PUBLIC_APP_URL=localhost:3000 + CC_PUBLIC_URL unset → pass=true', async () => {
    setEnv('http://localhost:3000', undefined);
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });

  it('Row 42: NEXT_PUBLIC_APP_URL=localhost + invalid CC_PUBLIC_URL hint → pass=true (intentional)', async () => {
    setEnv('http://localhost:3000', 'https://x.zerohumanworkforce.com');
    const result = await checkNextPublicAppUrl();
    expect(result.pass).toBe(true);
  });
});
