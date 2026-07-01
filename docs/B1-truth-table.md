# B.1 Health-Check Truth Table

This document is the **authoritative spec** for `checkNextPublicAppUrl()` in
`src/lib/health/deep-checks.ts` (blackceo-command-center).  Per
DUCK-PIPELINE-GUIDANCE.md §5, the table IS the spec: every enumerated row must
have a matching implementation and a matching test in
`tests/unit/deep-health.test.ts`.  A wrong-verdict state MUST appear as an
explicit row; omitting it is a spec gap.

---

## Legend

| Column | Meaning |
|--------|---------|
| `NEXT_PUBLIC_APP_URL` | Value of the env var at health-check time |
| `CC_PUBLIC_URL` | Value of the env var at health-check time |
| Expected verdict | `PASS` or `FAIL` (or `UNKNOWN` when indeterminate) |
| Reason | Why the check produces this verdict |

"non-localhost public domain" means any value whose hostname is neither
`localhost` nor `127.0.0.1` nor `::1` and that starts with `http://` or
`https://`.

---

## Row table

| Row | `NEXT_PUBLIC_APP_URL` | `CC_PUBLIC_URL` | Expected verdict | Reason |
|-----|-----------------------|-----------------|-----------------|--------|
| 10  | `https://app.example.com` | `https://app.example.com` (matching) | PASS | Both set, matching — nominal CF-tunnel deploy |
| 11  | `https://app.example.com` | `https://app.example.com` | PASS | Exact match (case-sensitive, trailing-slash-normalised) |
| 20  | `http://localhost:3000` | _(unset / empty)_ | PASS | Pure localhost deploy; CC_PUBLIC_URL not required |
| 21  | `http://localhost:3000` | `http://localhost:3000` | PASS | Localhost with matching hint — fine |
| 22  | `http://localhost:3000` | `https://x.zerohumanworkforce.com` | PASS | Localhost primary URL overrides non-localhost hint (intentional; Row 42 variant) |
| 30  | `https://<client>.zerohumanworkforce.com` | _(unset / empty)_ | FAIL | Non-localhost URL set but CC_PUBLIC_URL absent — CF-tunnel misconfiguration |
| **31** | **`https://x.zerohumanworkforce.com`** | **`https://x.zerohumanworkforce.com`** | **PASS** | **Both set and matching — correct CF-tunnel deploy** |
| **31a** | **_(unset / empty)_** | **`https://x.zerohumanworkforce.com`** | **FAIL** | **CF-tunnel mode detected (CC_PUBLIC_URL is a non-localhost public domain) but NEXT_PUBLIC_APP_URL is missing — breaks cross-origin SSE and webhooks for remote clients through the tunnel.  The early-return guard `if (!appUrl) { return { pass: true } }` MUST NOT fire here; it must check CC_PUBLIC_URL first.** |
| 32  | `https://x.zerohumanworkforce.com` | _(unset / empty or invalid / mismatched)_ | FAIL | Non-localhost primary URL present but CC_PUBLIC_URL unset, invalid, or mismatched |
| 33  | `https://x.zerohumanworkforce.com` | `https://y.zerohumanworkforce.com` (different subdomain) | FAIL | URL mismatch between primary and tunnel hint |
| 40  | _(unset / empty)_ | _(unset / empty)_ | PASS | Pure localhost / development mode; neither env var is required |
| 41  | _(unset / empty)_ | _(unset / empty)_ | PASS | Same as Row 40 — explicit double-unset case |
| 42  | `http://localhost:3000` | _(unset)_ | PASS | Localhost primary + no tunnel hint — intentional (dev / single-box) |
| 50  | `https://x.zerohumanworkforce.com` | `not-a-url` | FAIL | CC_PUBLIC_URL present but not a valid URL |
| 51  | `https://x.zerohumanworkforce.com` | `ftp://x.zerohumanworkforce.com` | FAIL | CC_PUBLIC_URL protocol mismatch (not http/https) |

---

## Row 31a — implementation requirement

Row 31a is the **false-green fix** tracked in REDO #1.  The code path that
must be changed is in `src/lib/health/deep-checks.ts`:

```ts
// BEFORE (wrong — hits early-return without reading CC_PUBLIC_URL):
const appUrl = process.env.NEXT_PUBLIC_APP_URL;
if (!appUrl) {
  return { pass: true, detail: 'acceptable for localhost deploys' };
}

// AFTER (correct — check CC_PUBLIC_URL before the early-return):
const appUrl = process.env.NEXT_PUBLIC_APP_URL;
const ccPublicUrl = process.env.CC_PUBLIC_URL ?? '';
const ccIsNonLocalhost =
  ccPublicUrl.length > 0 &&
  !ccPublicUrl.includes('localhost') &&
  !ccPublicUrl.includes('127.0.0.1');

if (!appUrl) {
  if (ccIsNonLocalhost) {
    // Row 31a: CF-tunnel mode detected, NEXT_PUBLIC_APP_URL missing → FAIL
    return {
      pass: false,
      detail:
        `CF-tunnel mode detected (CC_PUBLIC_URL=${ccPublicUrl}) but ` +
        `NEXT_PUBLIC_APP_URL is unset — cross-origin SSE and webhooks ` +
        `will fail for remote clients through the tunnel.`,
    };
  }
  // Row 40/41: pure localhost / dev mode → PASS
  return { pass: true, detail: 'acceptable for localhost deploys' };
}
```

The corresponding test (Row 31a) must be:

```ts
it('Row 31a: NEXT_PUBLIC_APP_URL unset + CC_PUBLIC_URL=non-localhost → FAIL', async () => {
  delete process.env.NEXT_PUBLIC_APP_URL;
  process.env.CC_PUBLIC_URL = 'https://demo.zerohumanworkforce.com';
  const result = await checkNextPublicAppUrl();
  expect(result.pass).toBe(false);
});
```

---

_Last updated: 2026-06-10 — Row 31a added (REDO #1 false-green fix)._
