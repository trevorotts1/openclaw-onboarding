# Deploy Guide: Kie Callback Relay Worker

Operator account: 13f808b72eb78027a8046357c6cf1afa
Zone: zerohumanworkforce.com (ID: a9ecc0a067f52eaa4c59dc9b11d9dd55)
Worker name: kie-callback-relay
Public URL: https://kie-callback.zerohumanworkforce.com/

---

## Prerequisites

1. Wrangler CLI installed: `npm install -g wrangler` or `npx wrangler`
2. Wrangler authenticated to operator CF account:
   ```
   npx wrangler login
   ```
   Confirm account ID 13f808b72eb78027a8046357c6cf1afa is selected.
3. Your `webhookHmacKey` from https://kie.ai/settings (enable it there first).

---

## Step 1: Create KV Namespace

Run from `46-kie-callback-relay/worker/`:

```bash
cd 46-kie-callback-relay/worker
npx wrangler kv namespace create KIE_CALLBACK_KV \
  --account-id 13f808b72eb78027a8046357c6cf1afa
```

Expected output:
```
Add the following to your configuration file in your kv_namespaces array:
{ binding = "KIE_CALLBACK_KV", id = "<YOUR_KV_ID>" }
```

Copy the `id` value. Repeat for the preview namespace:

```bash
npx wrangler kv namespace create KIE_CALLBACK_KV --preview \
  --account-id 13f808b72eb78027a8046357c6cf1afa
```

Edit `wrangler.toml` and replace:
- `REPLACE_WITH_KV_NAMESPACE_ID` with the production id
- `REPLACE_WITH_KV_PREVIEW_NAMESPACE_ID` with the preview id

---

## Step 2: Set the HMAC Secret

```bash
npx wrangler secret put KIE_WEBHOOK_HMAC_KEY --name kie-callback-relay
```

Paste the value from https://kie.ai/settings when prompted.
This secret NEVER goes in wrangler.toml or the repo.

---

## Step 3: Deploy the Worker

```bash
npx wrangler deploy --name kie-callback-relay
```

Expected output:
```
Deployed kie-callback-relay triggers:
  https://kie-callback.zerohumanworkforce.com/*
```

---

## Step 4: Verify

```bash
curl https://kie-callback.zerohumanworkforce.com/healthz
```

Expected:
```json
{ "status": "ok", "worker": "kie-callback-relay", "version": "1.0.0", ... }
```

---

## Step 5: Enable webhookHmacKey on Kie

Go to https://kie.ai/settings, find the webhook section, and enable the
`webhookHmacKey`. Copy the value -- you already set it as the Worker secret
in Step 2. These must match.

---

## Step 6: Smoke Test

Submit one test image using the KieSlideSubmitter with a 1-slide deck:

```javascript
const { KieSlideSubmitter } = require('./46-kie-callback-relay/kie-slide-submitter');

const submitter = new KieSlideSubmitter({
  clientSlug:   'operator-test',
  kieApiKey:    process.env.KIE_API_KEY,
  kvWorkerUrl:  'https://kie-callback.zerohumanworkforce.com',
  workspaceDir: '/tmp/kie-test'
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
