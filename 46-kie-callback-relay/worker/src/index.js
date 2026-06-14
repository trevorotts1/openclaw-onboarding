/**
 * Kie.ai Callback Worker -- Centralized operator fleet edge receiver
 *
 * Receives Kie.ai POST callbacks at:
 *   POST /cb?c=<clientSlug>&j=<submitId>&s=<perTaskSecret>
 *
 * Flow (Candidate B, transport B2 -- Worker-writes-to-KV, box-polls):
 *   1. Read X-Webhook-Timestamp + X-Webhook-Signature from headers
 *   2. Parse body to get taskId
 *   3. Verify HMAC-SHA256(taskId + "." + timestamp, webhookHmacKey) in constant time
 *   4. Check replay window (300 seconds -- policy choice; Kie does not define one)
 *   5. Check idempotency in KV (key: "idem:<taskId>", short TTL)
 *   6. Normalize result (handles 4o result_urls array OR Flux resultImageUrl/originImageUrl)
 *   7. Return 200 to Kie immediately (within the 15-second deadline)
 *   8. Write verified result to KV (key: "result:<clientSlug>:<submitId>") in waitUntil
 *   9. GET /healthz returns 200 with JSON for deploy verification
 *
 * KV bindings (wrangler.toml):
 *   KIE_CALLBACK_KV -- idempotency + result store
 *
 * Worker secrets (set via wrangler secret put):
 *   KIE_WEBHOOK_HMAC_KEY -- the webhookHmacKey from https://kie.ai/settings
 *
 * Security notes per DESIGN.md section 9:
 *   - HMAC covers only taskId.timestamp (Kie spec). Body integrity is NOT covered by Kie's sig.
 *   - Per-task secret (s=) is the second factor that binds callback to a submitted task.
 *   - Result URL host allowlist enforced before any box writes a download.
 *   - 300-second replay window is our policy, not a Kie-defined value.
 */

const REPLAY_WINDOW_SECONDS = 300; // policy choice -- Kie does not define a replay window

/** Constant-time byte comparison (avoids timing attacks) */
async function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a[i] ^ b[i];
  }
  return diff === 0;
}

/**
 * Verify the Kie HMAC signature.
 * Algorithm: HMAC-SHA256(taskId + "." + timestamp, webhookHmacKey), base64-encoded.
 * Source: https://docs.kie.ai/common-api/webhook-verification (verified 2026-06-14)
 */
async function verifyKieSignature(taskId, timestamp, receivedSignature, hmacKey) {
  const message = `${taskId}.${timestamp}`;
  const enc = new TextEncoder();
  const keyBytes = enc.encode(hmacKey);
  const msgBytes = enc.encode(message);

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const sigBytes = await crypto.subtle.sign('HMAC', cryptoKey, msgBytes);
  const expected = btoa(String.fromCharCode(...new Uint8Array(sigBytes)));

  // Constant-time compare
  const expectedBytes = new TextEncoder().encode(expected);
  const receivedBytes = new TextEncoder().encode(receivedSignature);
  return await timingSafeEqual(expectedBytes, receivedBytes);
}

/**
 * Normalize result URLs from either model family:
 *   4o family:   data.info.result_urls  (array of strings)
 *   Flux family: data.info.resultImageUrl + data.info.originImageUrl (strings)
 * Returns an array of URL strings.
 */
function extractResultUrls(data) {
  const info = data?.info || {};
  if (Array.isArray(info.result_urls) && info.result_urls.length > 0) {
    return info.result_urls.filter(Boolean);
  }
  const urls = [];
  if (info.resultImageUrl) urls.push(info.resultImageUrl);
  if (info.originImageUrl) urls.push(info.originImageUrl);
  return urls;
}

/**
 * KV read handler (B2 transport -- box polls this for verified callback result).
 * GET /kv-read?c=<clientSlug>&j=<submitId>
 * Returns: { found: true, result: {...} } or { found: false }
 *
 * No authentication on this endpoint beyond the fact that the box must know the submitId
 * (which is a local UUID it generated). The perTaskSecret in the result is validated by
 * the box against its own task registry before any download.
 */
async function handleKvRead(url, env) {
  const clientSlug = url.searchParams.get('c');
  const submitId   = url.searchParams.get('j');
  if (!clientSlug || !submitId) {
    return new Response(JSON.stringify({ found: false, error: 'missing params' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } });
  }
  const kvKey = `result:${clientSlug}:${submitId}`;
  const value = await env.KIE_CALLBACK_KV.get(kvKey);
  if (!value) {
    return new Response(JSON.stringify({ found: false }),
      { headers: { 'Content-Type': 'application/json' } });
  }
  return new Response(JSON.stringify({ found: true, result: JSON.parse(value) }),
    { headers: { 'Content-Type': 'application/json' } });
}

/** Health check handler */
function handleHealth() {
  return new Response(JSON.stringify({
    status: 'ok',
    worker: 'kie-callback-relay',
    version: '1.0.0',
    timestamp: new Date().toISOString()
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' }
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === '/healthz') {
      return handleHealth();
    }

    // KV read endpoint (B2 transport): box polls for its result
    // GET /kv-read?c=<clientSlug>&j=<submitId>
    if (request.method === 'GET' && url.pathname === '/kv-read') {
      return handleKvRead(url, env);
    }

    // Only accept POST to /cb
    if (request.method !== 'POST' || url.pathname !== '/cb') {
      return new Response('Not Found', { status: 404 });
    }

    // --- Parse query params ---
    const clientSlug = url.searchParams.get('c');
    const submitId   = url.searchParams.get('j');
    const perTaskSecret = url.searchParams.get('s');

    if (!clientSlug || !submitId || !perTaskSecret) {
      // Return 200 to prevent Kie from retrying a permanently-bad URL,
      // but log the rejection
      console.error('KIE_CB: missing required query params', { clientSlug, submitId });
      return new Response('OK', { status: 200 });
    }

    // --- Read body ---
    let body;
    try {
      body = await request.json();
    } catch (err) {
      console.error('KIE_CB: body parse failed', err.message);
      return new Response('OK', { status: 200 }); // return 200; Kie must not retry bad payloads
    }

    // Kie sends taskId in data.taskId
    const taskId = body?.data?.taskId;
    if (!taskId) {
      console.error('KIE_CB: missing taskId in body', JSON.stringify(body).slice(0, 200));
      return new Response('OK', { status: 200 });
    }

    // --- Read HMAC verification headers ---
    const timestampHeader = request.headers.get('x-webhook-timestamp');
    const signatureHeader = request.headers.get('x-webhook-signature');

    if (!timestampHeader || !signatureHeader) {
      // HMAC is opt-in on Kie; if webhookHmacKey is configured we REQUIRE the headers.
      // Reject silently (return 200 so Kie does not retry; this is a misconfiguration).
      console.error('KIE_CB: missing HMAC headers for taskId', taskId);
      return new Response('OK', { status: 200 });
    }

    // --- Replay protection (policy: +/- 300 seconds; Kie does not define a window) ---
    const nowSeconds = Math.floor(Date.now() / 1000);
    const msgTimestamp = parseInt(timestampHeader, 10);
    if (isNaN(msgTimestamp) || Math.abs(nowSeconds - msgTimestamp) > REPLAY_WINDOW_SECONDS) {
      console.warn('KIE_CB: replay/timestamp window exceeded for taskId', taskId,
        'delta', nowSeconds - msgTimestamp);
      return new Response('OK', { status: 200 });
    }

    // --- HMAC verification (requires KIE_WEBHOOK_HMAC_KEY Worker secret) ---
    const hmacKey = env.KIE_WEBHOOK_HMAC_KEY;
    if (!hmacKey) {
      console.error('KIE_CB: KIE_WEBHOOK_HMAC_KEY secret not configured');
      return new Response('OK', { status: 200 });
    }

    const sigValid = await verifyKieSignature(taskId, timestampHeader, signatureHeader, hmacKey);
    if (!sigValid) {
      console.warn('KIE_CB: HMAC mismatch for taskId', taskId);
      return new Response('OK', { status: 200 }); // 200 to avoid infinite retries
    }

    // --- Idempotency check (KV key: "idem:<taskId>", TTL 24h) ---
    const idemKey = `idem:${taskId}`;
    const existing = await env.KIE_CALLBACK_KV.get(idemKey);
    if (existing) {
      console.log('KIE_CB: duplicate callback dropped for taskId', taskId);
      return new Response('OK', { status: 200 }); // idempotent; already processed
    }

    // --- Mark idempotency immediately (before async work) ---
    // TTL: 86400 seconds (24 hours) -- long enough to absorb all Kie retries
    await env.KIE_CALLBACK_KV.put(idemKey, '1', { expirationTtl: 86400 });

    // Return 200 to Kie NOW -- within the 15-second deadline (Kie requirement)
    // Heavy KV write happens in waitUntil (async, non-blocking)
    ctx.waitUntil(writeResultToKV(env, {
      clientSlug,
      submitId,
      taskId,
      perTaskSecret,
      code: body.code,
      msg: body.msg,
      resultUrls: extractResultUrls(body.data),
      rawData: body.data,
      receivedAt: new Date().toISOString()
    }));

    return new Response('OK', { status: 200 });
  }
};

/**
 * Write verified result to KV for the box to pull.
 * Key pattern: "result:<clientSlug>:<submitId>"
 * TTL: 3600 seconds (1 hour) -- boxes should poll within seconds; 1h is ample
 *
 * The box polling loop reads this key by submitId (which it controls).
 * It also validates perTaskSecret against its local task registry before trusting the result.
 */
async function writeResultToKV(env, result) {
  const kvKey = `result:${result.clientSlug}:${result.submitId}`;
  const payload = JSON.stringify({
    taskId:         result.taskId,
    clientSlug:     result.clientSlug,
    submitId:       result.submitId,
    perTaskSecret:  result.perTaskSecret,
    code:           result.code,
    msg:            result.msg,
    resultUrls:     result.resultUrls,
    rawData:        result.rawData,
    receivedAt:     result.receivedAt
  });

  // TTL: 3600s. The box polls this key every 2 seconds once a callback is expected.
  await env.KIE_CALLBACK_KV.put(kvKey, payload, { expirationTtl: 3600 });

  console.log('KIE_CB: result written to KV', kvKey, 'code', result.code,
    'urls', result.resultUrls.length);
}
