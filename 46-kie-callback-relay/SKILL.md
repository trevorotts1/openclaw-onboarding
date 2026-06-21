---
name: kie-callback-relay
description: >
  Centralized Cloudflare Worker that receives Kie.ai image-generation callbacks
  for the entire operator fleet, verifies the HMAC signature once, and writes
  verified results to Worker KV. Client boxes poll the Worker KV endpoint instead
  of Kie's status API. Implements webhook-primary with a single-poll fallback and
  crash-safe on-disk task registry. Applies to large decks (above configurable
  threshold); smaller decks use efficient batch polling per Candidate C of the
  design.
metadata:
  version: "1.0.0"
  skill_number: 46
  requires_skills: [07]
  priority: HIGH
---

# Skill 46: Kie Callback Relay (Centralized Worker + KV Pull)

## What This Skill Does

Moves large-deck image generation from sequential per-image polling to a
webhook-primary architecture. A single Cloudflare Worker at
`kie-callback.zerohumanworkforce.com` receives every Kie.ai callback for
all client boxes, verifies the HMAC signature centrally, and stores the
result in Worker KV. The box polls the Worker KV (not Kie) for its result.
If the callback does not arrive within the per-model timeout, the box falls
back to a single reconciling poll of Kie's `recordInfo` endpoint.

## When to Use This Skill

- A client deck has more slides than the callback threshold (default: 5)
- You want to reduce Kie API query budget consumption on large jobs
- You are setting up the operator fleet Worker for the first time

## Architecture (Candidate B, transport B2)

```
Kie servers
   |  POST https://kie-callback.zerohumanworkforce.com/cb?c=<client>&j=<submitId>&s=<secret>
   |        X-Webhook-Signature, X-Webhook-Timestamp
   v
Cloudflare Worker (centralized, single fleet Worker)
   |  - HMAC-SHA256 verify (taskId.timestamp, webhookHmacKey)
   |  - Replay window: 300s (policy choice; Kie docs do not define one)
   |  - Idempotency: KV key idem:<taskId>, TTL 24h
   |  - Return 200 to Kie in < 1s
   |  - Write result to KV key result:<client>:<submitId> in waitUntil
   v
Worker KV (KIE_CALLBACK_KV namespace)
   ^
   |  GET /kv-read?c=<client>&j=<submitId>  (box polls every 2s)
Box (Mac or Docker)
   |  - Validates perTaskSecret from KV result against local registry
   |  - Downloads image from result URLs (allowlist: Kie CDN hosts)
   |  - Writes .kie/done/<taskId>.json (done marker, idempotent)
   v
Slide rendered
```

## Files in This Folder

- `SKILL.md` -- you are here
- `worker/src/index.js` -- the Cloudflare Worker code
- `worker/wrangler.toml` -- Wrangler config with deploy commands
- `worker/package.json` -- devDependencies (wrangler)
- `box-kv-poller.js` -- box-side KV polling module
- `kie-slide-submitter.js` -- slide submitter (webhook-primary, poll-fallback)
- `SUBMITTER-SOP.md` -- operator SOP for the slide submitter
- `DEPLOY.md` -- step-by-step deploy guide for Trevor

## Key Design Decisions

1. HMAC key (`webhookHmacKey`) lives ONLY in the Worker secret and the Kie account.
   It never lands on a client box. This is why verification is centralized.

2. Per-task secret (`s=` in the callback URL) is the second security factor.
   Kie's HMAC signs only `taskId.timestamp`, not the result body. The per-task
   secret binds the callback to a task we actually submitted.

3. Replay window of 300 seconds is an operator policy choice.
   Kie's docs do not define a timestamp tolerance as of 2026-06-14.

4. Callbacks are used only for decks above the threshold (default 5 slides).
   Smaller decks use efficient batch polling (submit all, then backoff-poll).
   This is intentional -- webhook complexity does not pay off on small jobs.

5. Zero inbound public route on client boxes (B2 transport).
   No Cloudflare Access bypass needed per box. The box only makes outbound
   requests to the Worker KV endpoint it already controls.

## Rate Limits

- Kie creation: 20 requests per 10 seconds per account
  Source: https://docs.kie.ai/ (verified 2026-06-14)
- Kie status query: 10 requests per second per API key
  Source: in-repo 07-kie-setup/kie-setup-full.md lines 603-605
- Worker KV reads: effectively unlimited on the operator plan

## Daily GHL Firebase Token Liveness Check

Per operator instruction the daily `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` liveness check
is cross-referenced here alongside Skill 44.

**Note:** this Kie Callback Relay does **not** itself consume the GHL Firebase token —
the token, its dependency, and the check are owned by **Skill 44 (convert-and-flow-operator)**.
This section is a discoverability pointer so an operator working in Skill 46 knows the
check exists; it does not imply Skill 46 makes GoHighLevel writes.

A daily cron (`ghl-token-liveness`, registered by `scripts/ensure-pipeline-crons.sh` at
08:00 UTC) runs on every client box where Skill 44 is installed.

**What the check does:**

1. Resolves `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` from the standard env-store search
   order (`secrets/.env` → `openclaw.json env.vars` → `workspace/.env`).
2. Exchanges it at `securetoken.googleapis.com/v1/token` (same endpoint as the
   Skill 44 transport engine and `seed-ghl-auth.py`).
3. On **VALID** (HTTP 200 + `id_token` returned): exits silently, no notification.
4. On **INVALID** (`TOKEN_EXPIRED` / `USER_DISABLED` / `INVALID_REFRESH_TOKEN`):
   sends a plain-English notification to the CLIENT's own Telegram chat with
   step-by-step instructions to re-grab the token via the Convert and Flow Token
   Grabber Chrome extension (Skill 44 `tools/chrome-extension/`).

The check is idempotent (once per calendar day). The script lives at:
`44-convert-and-flow-operator/tools/check-ghl-token-liveness.sh`

**Agent action on notification:** when the client replies with a new token, wire it in:
```bash
openclaw config set env.vars.GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "<new-token>"
```
Then verify with `caf doctor` (Skill 44) before any workflow write.

---

## Unverified Items (do not present as fact)

- Exact Kie CDN hostname(s) for the result URL allowlist -- must confirm from a
  real callback before locking the allowlist in box-kv-poller.js KIE_RESULT_HOSTS
- Replay window: Kie does not document one; 300s is our policy
- Kie retry interval/backoff between the ~3 callback retries: not documented
