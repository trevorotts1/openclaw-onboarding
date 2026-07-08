# Slide Submitter SOP -- Webhook-Primary, Poll-Fallback (v1.1.0)

This SOP replaces the sequential per-image polling loop that was in Skill 07.
It applies to any role or agent that submits images to Kie.ai for slide decks.

**This SOP is the hardened contract. It matches `worker/src/index.js`,
`kie-slide-submitter.js`, and `box-kv-poller.js` exactly.** Do not copy the
pre-hardening callback URL (`&s=<perTaskSecret>`) from anywhere -- that leaked the
raw per-task secret into Kie's request logs. The current contract is below.

---

## The Big Shift

Old behavior: submit one image, poll until done, then submit the next.
New behavior: submit ALL images first (respecting rate limits), then wait for
results in parallel.

This single change removes most of the latency waste on large decks, regardless
of whether callbacks are enabled.

---

## Security Contract (read first)

Four values travel per task. Only ONE ever leaves the box, and it is not secret:

| Value | Where it lives | In the callback URL? | Secret? |
|-------|----------------|----------------------|---------|
| `perClientCallbackKey` | box env `KIE_CALLBACK_HMAC_KEY` (a PER-CLIENT derived key, not the fleet master) | no | yes |
| `perClientKvReadToken` | box env `KVREAD_TOKEN` (per-client derived) | no | yes |
| `perTaskSecret` | local registry only; sent to OUR Worker over TLS in the `X-Kie-Preimage` header | no | yes |
| `submitId` | the `j=` param | yes | no (128-bit random) |
| `callbackValidator` (`s=`) | the `s=` param | yes | no (a keyed HMAC) |
| `perTaskSecretHmac` (`h=`) | the `h=` param | yes | no (a hash of the secret) |

Per-client keys (fix F): the operator derives each box's `KIE_CALLBACK_HMAC_KEY`
and `KVREAD_TOKEN` as `HMAC-SHA256(clientSlug, <fleet master>)`. A box only ever
holds its own derived values, so one compromised box exposes exactly one client's
callback path -- never the fleet. The Worker re-derives the same per-client value
from its master + the `c=` slug on every request.

---

## Step-by-Step

### Step 1: Decide Whether to Use Callbacks

Count the slides in the deck.

- **At or below the threshold (default 5):** use efficient batch polling. Submit
  all slides with NO `callBackUrl`, then poll Kie's `recordInfo` directly with
  backoff (fix 33). No Worker, no `KIE_CALLBACK_HMAC_KEY`, no `KVREAD_TOKEN`.
- **Above the threshold:** use callback mode. Include `callBackUrl` in each
  createTask and pull results from the Worker KV. Requires the two per-client
  Worker secrets on the box.

The threshold is configurable via `callbackThreshold` in the submitter options.

### Step 2: Generate the Random submitId + Per-Task Secret, Write Registry (Before Submitting)

For each slide, generate a **128-bit random** `submitId` (never `deckId_slideId` --
a guessable id lets an attacker forge callbacks):

```
submitId = crypto.randomBytes(16).toString('hex')   // 32 hex chars
```

In callback mode, also generate a 256-bit (64-hex) per-task secret:

```
perTaskSecret = crypto.randomBytes(32).toString('hex')
```

Write the registry row to `.kie/registry/<submitId>.json` BEFORE sending the
createTask request. The human-readable `deckId`/`slideId` live in a `label` field
for resume; the KV key is the random `submitId`, not the label.

> **MODEL NOTE:** The model in these examples is `gpt-image-2-text-to-image` -- the canonical primary for all client presentations. The producing role ALWAYS sources the model from the client's pinned config (intake.json / MODEL MANIFEST), NEVER copies it from example code. `nano-banana-pro` is a FALLBACK-ONLY model and may only appear in a registry row after a logged hard API failure of the primary.

Callback-mode registry row:

```json
{
  "submitId": "<32 hex chars, 128-bit random>",
  "label": "<deckId>_<slideId>",
  "clientSlug": "<clientSlug>",
  "deckId": "<deckId>",
  "slideId": "<slideId>",
  "model": "gpt-image-2-text-to-image",
  "targetPath": "/abs/path/to/output.png",
  "perTaskSecret": "<64 hex chars, local only>",
  "callBackUrl": "https://kie-callback.<your-cf-zone>/cb?c=<clientSlug>&j=<submitId>&s=<callbackValidator>&h=<perTaskSecretHmac>",
  "submittedAt": "<iso8601>",
  "status": "submitting",
  "taskId": null,
  "fallbackPolledAt": null
}
```

Small-deck (batch-poll) rows are identical but `perTaskSecret` and `callBackUrl`
are `null`.

Compute the two non-secret URL params with the **per-client** key:

```
callbackValidator = HMAC-SHA256(clientSlug + ":" + submitId, perClientCallbackKey)   // s=
perTaskSecretHmac = HMAC-SHA256(perTaskSecret,               perClientCallbackKey)   // h=
```

### Step 3: Submit All Slides (Rate-Limited Batch)

POST to `https://api.kie.ai/api/v1/jobs/createTask`. Include `callBackUrl` ONLY in
callback mode:

```json
{
  "model": "gpt-image-2-text-to-image",
  "callBackUrl": "https://kie-callback.<your-cf-zone>/cb?c=<clientSlug>&j=<submitId>&s=<callbackValidator>&h=<perTaskSecretHmac>",
  "input": {
    "prompt": "<slide image prompt>",
    "aspect_ratio": "16:9",
    "resolution": "2K",
    "output_format": "png"
  }
}
```

The URL carries `s=` (the callback validator) and `h=` (the per-task-secret HMAC).
It NEVER carries the raw `perTaskSecret`.

Rate limit: 20 requests per 10 seconds per account.
Source: https://docs.kie.ai/ (verified 2026-06-14).

Use a token bucket (see kie-slide-submitter.js `_throttle()`). If you hit 429,
wait and retry. After each successful createTask response, record the returned
`taskId` in the registry row and write a taskId index:
`.kie/index/<taskId>.json = { taskId, submitId }`.

Do NOT wait for results during this phase. Submit all slides, then proceed.

### Step 4a: Wait for Results via KV Poll (callback mode only)

For each taskId, poll the Worker KV in parallel:

1. `GET https://kie-callback.<your-cf-zone>/kv-read?c=<clientSlug>&j=<submitId>`
   every 2 seconds, with **two request pieces**:
   - Header `Authorization: Bearer <perClientKvReadToken>` (fix B/F)
   - Header `X-Kie-Preimage: <perTaskSecret>` (fix G -- the raw secret rides in a
     header, never a query param, so it is not captured in edge access logs)
2. On `401`/`403`: log a misconfiguration error and keep retrying (non-fatal for
   the loop). The Worker validates the bearer token AND recomputes the HMAC of the
   preimage; it returns the result only when both pass.
3. On `{ found: true, result: {...} }`:
   a. Confirm `result.submitId === submitId` exactly (fix 34 -- confused-deputy
      guard; a result for any other task is dropped). The Worker never returns
      `perTaskSecret` or `perTaskSecretHmac`, so do not look for them.
   b. Filter `result.resultUrls` against the Kie CDN allowlist
      (`KIE_RESULT_HOSTS` in box-kv-poller.js).
   c. **A `code === 200` with zero surviving (allowlisted) URLs is a FAILURE**
      (fix 35), status `failed` / reason `allowlist-rejected` -- there is no file
      to download. Only `code === 200` AND at least one allowlisted URL is `done`.
   d. Download the first valid URL to `targetPath`.
   e. A slide counts as `done` ONLY when the file exists on disk (fix 35). A
      `done` status with no downloaded file is downgraded to `failed`.
   f. Write `.kie/done/<taskId>.json` (create-if-absent, idempotent).

This polling does NOT consume Kie's 10-req/s query budget (it hits the Worker).

### Step 4b: Small Decks -- Direct Kie recordInfo Poll (fix 33)

When callbacks are disabled (deck at/below threshold), there is NO Worker and NO
KV. Skip the KV phase entirely and batch-poll Kie directly:

1. Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>` per slide
   with backoff (2s -> 5s -> 15s -> 30s max), in parallel across the small batch.
2. On `data.state === 'success'`: parse `data.resultJson`, allowlist-filter,
   download, write the done-marker.
3. On `fail`: write a `failed` done-marker with `failCode`/`failMsg`.
4. Respect the 10-req/s Kie query limit.

### Step 5: Fallback if a Callback Does Not Arrive (callback mode only)

If a callback-mode slide's done-marker is not found within the per-model callback
timeout, fall back to a single reconciling Kie poll, then backoff:

Per-model callback timeouts (ms), from `kie-slide-submitter.js` MODEL_TIMEOUTS:

| Model | Timeout |
|-------|---------|
| `gpt-image-2-text-to-image` (primary) | 300000 (5 min) |
| `gpt-image-2-image-to-image` (primary, reference images) | 300000 (5 min) |
| `nano-banana-pro` (FALLBACK-ONLY) | 120000 (2 min) |
| default | 180000 (3 min) |

1. Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>`.
2. Inspect `data.state`:
   - `success`: parse `data.resultJson`, download, write done-marker, done.
   - `fail`: write done-marker with status `failed`; surface the failure.
   - `waiting | queuing | generating`: backoff and retry (2s -> 5s -> 15s -> 30s max).
   - After 10 minutes of fallback polling: mark the slide `timeout` and surface it.
3. Update registry `fallbackPolledAt` timestamp.

### Step 6: Handle Failures Explicitly

Failed slides (callback `code != 200`, allowlist-rejected, download-missing,
fallback state `fail`, or timeout) MUST be surfaced to the caller. Do NOT silently
skip them. Return a result array where each entry has
`status: 'done' | 'failed' | 'timeout'`. `done` means a real file on disk.

### Step 7: Crash-Safe Resume

On restart the submitter scans `.kie/registry/` by `label` (fix 37i):

- A crash between the createTask POST and its response can leave TWO rows for one
  label: an orphan with `taskId: null` and, if Kie actually accepted the task, a
  paid task. Per label the submitter picks the row that HAS a `taskId` (else the
  newest `submittedAt`) and marks every other row `superseded` so it is never
  re-submitted -- this is what prevents paying for a task twice.
- If the winning row has a `taskId`:
  - If `.kie/done/<taskId>.json` exists: slide is done. Skip.
  - Else: re-enter the wait queue (no re-submit).
- If the winning row has no `taskId`: re-submit (the prior submit crashed before
  Kie returned a taskId).
- If no registry row: first-time submit.

---

## Rate Limit Reference

| Operation          | Limit                     | Source                          |
|--------------------|---------------------------|---------------------------------|
| Create task        | 20 per 10 seconds/account | docs.kie.ai (verified 2026-06-14) |
| Status query (Kie) | 10 per second/API key     | 07-kie-setup/kie-setup-full.md  |
| KV read (Worker)   | No Kie budget consumed    | operator-owned infra            |

---

## Callback URL Format (hardened)

```
https://kie-callback.<your-cf-zone>/cb?c=<clientSlug>&j=<submitId>&s=<callbackValidator>&h=<perTaskSecretHmac>
```

- `c`: client identifier (alphanumeric, no spaces)
- `j`: submitId (128-bit random hex; you control it; NOT the Kie taskId)
- `s`: callback validator = `HMAC-SHA256(clientSlug + ":" + submitId, perClientCallbackKey)` -- not secret, safe in logs
- `h`: per-task-secret HMAC = `HMAC-SHA256(perTaskSecret, perClientCallbackKey)` -- a hash, not the secret

The raw `perTaskSecret` NEVER appears in the URL. The `taskId` (Kie-controlled) is
not in the URL because you do not know it before createTask returns; the Worker
reads it from the POST body and keys the KV result by `submitId`.

/kv-read request (box -> Worker):

```
GET /kv-read?c=<clientSlug>&j=<submitId>
Authorization: Bearer <perClientKvReadToken>
X-Kie-Preimage: <perTaskSecret>
```

---

## Security Checklist

- Kie HMAC verified centrally by the Worker (never on the box)
- `submitId` is 128-bit random -- callbacks are unguessable (fix A)
- `s=` / `h=` are keyed HMACs; the raw `perTaskSecret` never enters a URL (fix C/D)
- `perTaskSecret` reaches the Worker only in the `X-Kie-Preimage` header, over TLS,
  to our own host -- never a query param, never through Kie (fix G)
- /kv-read requires a per-client bearer token (fix B/F); the box validates the
  returned `submitId` matches exactly (fix 34)
- A `code 200` with zero allowlisted URLs is a failure, not a silent empty `done` (fix 35)
- Per-client keys derived from a fleet master (fix F): one box compromise != fleet compromise
- Result URLs filtered against the Kie CDN allowlist before download
- Replay window: 300 seconds (operator policy; Kie does not define one)
- Idempotency: done-marker write is create-if-absent (no double-download)
- `webhookHmacKey` and the fleet master keys live ONLY in the Worker; never on a box

---

## Unverified Items

- Exact Kie CDN hosts: update `KIE_RESULT_HOSTS` in box-kv-poller.js after
  observing a real callback.
- Kie retry interval/backoff between the ~3 callback retries: not documented.
