/**
 * deep-checks.ts — Wave-5 Command Center health checks.
 *
 * Each exported function returns a CheckResult.  The duck CI test
 * (tests/e2e/duck-test --mock) exercises every check in mock mode before
 * a Wave-5 deploy is marked green.
 *
 * Truth-table spec: docs/B1-truth-table.md
 * Guidance: DUCK-PIPELINE-GUIDANCE.md §5
 */

export interface CheckResult {
  pass: boolean;
  detail: string;
}

// ── checkNextPublicAppUrl ─────────────────────────────────────────────────────
//
// Truth-table rows implemented (see docs/B1-truth-table.md for full spec):
//
//   Row 40/41 — NEXT_PUBLIC_APP_URL unset + CC_PUBLIC_URL unset/empty → PASS
//               (pure localhost / dev mode)
//   Row 31a   — NEXT_PUBLIC_APP_URL unset + CC_PUBLIC_URL = non-localhost public
//               domain → FAIL (CF-tunnel mode detected, missing app URL breaks
//               cross-origin SSE and webhooks)
//   Row 31    — Both set and matching → PASS
//   Row 32    — NEXT_PUBLIC_APP_URL set non-localhost + CC_PUBLIC_URL absent /
//               invalid / mismatched → FAIL
//   Row 20/42 — NEXT_PUBLIC_APP_URL = localhost → PASS regardless of CC_PUBLIC_URL
//
// REDO #1 fix: the original early-return guard `if (!appUrl) { return { pass: true } }`
// fired unconditionally, which incorrectly returned PASS for Row 31a.  The guard
// now checks CC_PUBLIC_URL first and returns FAIL when CF-tunnel mode is detected.

function _isNonLocalhostPublicUrl(url: string): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    const host = u.hostname;
    return (
      (u.protocol === 'http:' || u.protocol === 'https:') &&
      host !== 'localhost' &&
      host !== '127.0.0.1' &&
      host !== '::1'
    );
  } catch {
    return false;
  }
}

function _isLocalhostUrl(url: string): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    const host = u.hostname;
    return (
      host === 'localhost' ||
      host === '127.0.0.1' ||
      host === '::1'
    );
  } catch {
    return false;
  }
}

export async function checkNextPublicAppUrl(): Promise<CheckResult> {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? '';
  const ccPublicUrl = process.env.CC_PUBLIC_URL ?? '';

  // ── NEXT_PUBLIC_APP_URL is unset / empty ─────────────────────────────────
  if (!appUrl) {
    // Row 31a: CC_PUBLIC_URL is a non-localhost public domain → CF-tunnel mode
    // detected.  NEXT_PUBLIC_APP_URL is required in this configuration;
    // without it, cross-origin SSE and webhooks fail for remote clients
    // through the tunnel.  Return FAIL — this is NOT a safe localhost deploy.
    if (_isNonLocalhostPublicUrl(ccPublicUrl)) {
      return {
        pass: false,
        detail:
          `CF-tunnel mode detected (CC_PUBLIC_URL=${ccPublicUrl}) but ` +
          `NEXT_PUBLIC_APP_URL is unset — cross-origin SSE and webhooks ` +
          `will fail for remote clients through the tunnel. ` +
          `Set NEXT_PUBLIC_APP_URL to match CC_PUBLIC_URL.`,
      };
    }

    // Row 40/41: both unset (or CC_PUBLIC_URL is also localhost / empty) →
    // pure localhost / development mode → PASS.
    return {
      pass: true,
      detail: 'acceptable for localhost deploys (both NEXT_PUBLIC_APP_URL and CC_PUBLIC_URL unset)',
    };
  }

  // ── NEXT_PUBLIC_APP_URL is set ────────────────────────────────────────────

  // Row 20/42: primary URL is localhost → PASS regardless of CC_PUBLIC_URL.
  if (_isLocalhostUrl(appUrl)) {
    return {
      pass: true,
      detail: `localhost deploy (NEXT_PUBLIC_APP_URL=${appUrl})`,
    };
  }

  // Non-localhost primary URL: CC_PUBLIC_URL must be present and matching.
  if (!ccPublicUrl) {
    return {
      pass: false,
      detail:
        `NEXT_PUBLIC_APP_URL is set to a non-localhost URL (${appUrl}) but ` +
        `CC_PUBLIC_URL is unset — CF-tunnel configuration incomplete.`,
    };
  }

  if (!_isNonLocalhostPublicUrl(ccPublicUrl)) {
    return {
      pass: false,
      detail:
        `CC_PUBLIC_URL is set but is not a valid non-localhost URL: "${ccPublicUrl}". ` +
        `Expected a public https:// domain matching NEXT_PUBLIC_APP_URL.`,
    };
  }

  // Normalize trailing slash for comparison.
  const normalise = (u: string) => u.replace(/\/+$/, '');
  if (normalise(appUrl) !== normalise(ccPublicUrl)) {
    return {
      pass: false,
      detail:
        `NEXT_PUBLIC_APP_URL (${appUrl}) does not match CC_PUBLIC_URL (${ccPublicUrl}). ` +
        `Both must point to the same public domain for CF-tunnel mode.`,
    };
  }

  // Row 31: both set and matching → PASS.
  return {
    pass: true,
    detail: `CF-tunnel deploy confirmed (NEXT_PUBLIC_APP_URL=${appUrl} matches CC_PUBLIC_URL)`,
  };
}
