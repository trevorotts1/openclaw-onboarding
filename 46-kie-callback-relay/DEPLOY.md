# Deploy Guide: Kie Callback Relay Worker

Operator account: <CF_ACCOUNT_ID>
Zone: <your-cf-zone> (ID: <CF_ZONE_ID>)
Worker name: kie-callback-relay
Public URL: https://kie-callback.<your-cf-zone>/

---

## Prerequisites

1. Wrangler CLI installed: `npm install -g wrangler` or `npx wrangler`
2. Wrangler authenticated to operator CF account:
   ```
   npx wrangler login
   ```
   Confirm account ID <CF_ACCOUNT_ID> is selected.
3. Your `webhookHmacKey` from https://kie.ai/settings (enable it there first).

---

## Step 1: Create KV Namespace

Run from `46-kie-callback-relay/worker/`:

```bash
cd 46-kie-callback-relay/worker
npx wrangler kv namespace create KIE_CALLBACK_KV \
  --account-id <CF_ACCOUNT_ID>
```

Expected output:
```
Add the following to your configuration file in your kv_namespaces array:
{ binding = "KIE_CALLBACK_KV", id = "<YOUR_KV_ID>" }
```

Copy the `id` value. Repeat for the preview namespace:

```bash
npx wrangler kv namespace create KIE_CALLBACK_KV --preview \
  --account-id <CF_ACCOUNT_ID>
```

Edit `wrangler.toml` and replace:
- `REPLACE_WITH_KV_NAMESPACE_ID` with the production id
- `REPLACE_WITH_KV_PREVIEW_NAMESPACE_ID` with the preview id

---

## Step 2: Set the Three Worker Secrets

The Worker requires THREE secrets. All three are set the same way and NEVER go in
wrangler.toml or the repo. Missing any one breaks the relay: without
`KIE_CALLBACK_HMAC_KEY` every valid callback is dropped, and without `KVREAD_TOKEN`
every `/kv-read` returns 500.

```bash
# 1. Kie's webhook signing key (from https://kie.ai/settings)
npx wrangler secret put KIE_WEBHOOK_HMAC_KEY --name kie-callback-relay

# 2. Fleet MASTER callback key -- derives each client's callback validator + secret HMAC.
#    Generate a fresh 32-byte random value and paste it when prompted:
#      openssl rand -hex 32
npx wrangler secret put KIE_CALLBACK_HMAC_KEY --name kie-callback-relay

# 3. Fleet MASTER /kv-read bearer token -- derives each client's per-box read token.
#      openssl rand -hex 32
npx wrangler secret put KVREAD_TOKEN --name kie-callback-relay
```

`KIE_CALLBACK_HMAC_KEY` and `KVREAD_TOKEN` are FLEET MASTER keys. They never leave
the Worker. Each client box gets only a PER-CLIENT value DERIVED from them
(see Step 4b), so one compromised box exposes exactly one client -- not the fleet.

---

## Step 3: Deploy the Worker

```bash
npx wrangler deploy --name kie-callback-relay
```

Expected output:
```
Deployed kie-callback-relay triggers:
  https://kie-callback.<your-cf-zone>/*
```

---

## Step 4: Verify

```bash
curl https://kie-callback.<your-cf-zone>/healthz
```

Expected:
```json
{ "status": "ok", "worker": "kie-callback-relay", "version": "1.1.0", ... }
```

---

## Step 4b: Provision Per-Client Box Credentials (fix F)

Each client box needs its OWN derived credentials -- never the fleet master keys.
Derive them once per client from the two master values you set in Step 2:

```bash
CLIENT_SLUG="operator-demo"                 # this box's c= identifier
MASTER_CB="<the KIE_CALLBACK_HMAC_KEY master value>"
MASTER_KVR="<the KVREAD_TOKEN master value>"

PER_CLIENT_CALLBACK_KEY="$(printf '%s' "$CLIENT_SLUG" | openssl dgst -sha256 -hmac "$MASTER_CB" | awk '{print $NF}')"
PER_CLIENT_KVREAD_TOKEN="$(printf '%s' "$CLIENT_SLUG" | openssl dgst -sha256 -hmac "$MASTER_KVR" | awk '{print $NF}')"
```

This is exactly `HMAC-SHA256(clientSlug, master)` in hex -- the same derivation the
Worker performs on every request. Distribute ONLY the two derived values onto the
box env store (`~/clawd/secrets/.env` or `/docker/<project>/.env`):

```
KIE_KV_BASE_URL=https://kie-callback.<your-cf-zone>
KIE_CLIENT_SLUG=operator-demo
KIE_CALLBACK_HMAC_KEY=<PER_CLIENT_CALLBACK_KEY>   # per-client, NOT the master
KVREAD_TOKEN=<PER_CLIENT_KVREAD_TOKEN>            # per-client, NOT the master
```

The fleet master keys stay ONLY in the Worker secrets. A box never holds a master.

---

## Step 5: Enable webhookHmacKey on Kie

Go to https://kie.ai/settings, find the webhook section, and enable the
`webhookHmacKey`. Copy the value -- you already set it as the Worker secret
in Step 2. These must match.

---

## Step 6: Smoke Test

First, run the offline security regression suite (no network -- proves the three
components agree on the hardened contract before you spend a Kie credit):

```bash
bash 46-kie-callback-relay/qc-kie-callback-relay.sh
```

Then submit a live test deck. A 6-slide deck triggers callback mode, so you MUST
pass this box's PER-CLIENT `callbackHmacKey` and `kvReadToken` (derived in Step 4b)
-- `submitDeck` throws in callback mode without them:

```javascript
const { KieSlideSubmitter } = require('./46-kie-callback-relay/kie-slide-submitter');

const submitter = new KieSlideSubmitter({
  clientSlug:      'operator-test',
  kieApiKey:       process.env.KIE_API_KEY,
  kvWorkerUrl:     'https://kie-callback.<your-cf-zone>',
  workspaceDir:    '/tmp/kie-test',
  callbackHmacKey: process.env.KIE_CALLBACK_HMAC_KEY, // per-client derived value (Step 4b)
  kvReadToken:     process.env.KVREAD_TOKEN           // per-client derived value (Step 4b)
});

// Use a 6-slide deck to trigger callback mode (above the threshold of 5)
const slides = Array.from({ length: 6 }, (_, i) => ({
  deckId:     'test-deck-01',
  slideId:    `slide-${i+1}`,
  prompt:     'A professional blue gradient background, no text, clean and minimal',
  // PRIMARY model for all client presentations. Sourced from client's pinned config in production, never hard-coded.
  model:      'gpt-image-2-text-to-image',
  targetPath: `/tmp/kie-test/slide-${i+1}.png`
}));

const results = await submitter.submitDeck(slides, { callbackThreshold: 5 });
console.log(results);
```

To smoke-test the small-deck path (no Worker, no secrets), submit a ≤5-slide deck
with the same call but omit `callbackHmacKey`/`kvReadToken`; it batch-polls Kie
recordInfo directly (fix 33).

Verify:
- A callback arrives at the Worker (check Worker logs: `npx wrangler tail --name kie-callback-relay`)
- The done marker appears at `/tmp/kie-test/.kie/done/<taskId>.json`
- The image downloads to `/tmp/kie-test/slide-N.png`

Force a lost-callback test by pointing one slide at a bad callback URL
(change the Worker URL to a non-existent host), confirm the fallback poll
resolves the slide via `kie-poll` source in the done marker.

---

## Updating the Worker

```bash
cd 46-kie-callback-relay/worker
npx wrangler deploy --name kie-callback-relay
```

Workers deploy atomically with zero downtime.

---

## Secret Rotation

### Rotate webhookHmacKey:

1. Generate a new key on https://kie.ai/settings
2. The Worker currently supports only one key. During the rotation window,
   some in-flight callbacks may fail HMAC. Keep the rotation window brief.
3. Set the new secret:
   ```bash
   npx wrangler secret put KIE_WEBHOOK_HMAC_KEY --name kie-callback-relay
   ```
4. Verify with a live test image immediately after rotation.

To support zero-downtime rotation, the Worker can be extended to accept either
the old or new key during a brief overlap window (add `KIE_WEBHOOK_HMAC_KEY_OLD`
secret and check both in `verifyKieSignature`).
