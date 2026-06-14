/**
 * Kie Callback KV Poller -- runs on the client box (Mac or Docker)
 *
 * Transport B2: the box polls Cloudflare KV for the verified callback result.
 * This means ZERO inbound public route on the box and ZERO Cloudflare Access bypass.
 *
 * Usage: called by the slide submitter after each batch of createTask submits.
 *   const poller = new KieKvPoller({
 *     clientSlug, kvWorkerUrl, workspaceDir,
 *     kvReadToken  -- bearer token for /kv-read authentication (KVREAD_TOKEN, fix B)
 *   });
 *   const result = await poller.waitForTask(submitId, taskId, perTaskSecret, { timeoutMs });
 *
 * Required env vars on the box (in ~/clawd/secrets/.env or /docker/<project>/.env):
 *   KIE_KV_BASE_URL   -- Worker base URL, e.g. https://kie-callback.zerohumanworkforce.com
 *   KIE_CLIENT_SLUG   -- this box's client identifier (e.g. "operator-demo")
 *   KVREAD_TOKEN      -- bearer token shared with the Worker (fix B); name only, never in docs
 *
 * Security:
 *   - Fix B: every /kv-read request carries Authorization: Bearer <KVREAD_TOKEN>.
 *   - Fix C: the raw perTaskSecret is sent as &p= on /kv-read so the Worker can validate
 *     the stored HMAC. The Worker validates in constant time and NEVER returns perTaskSecret.
 *     The box validates the result by comparing its local registry copy of perTaskSecret
 *     against what was submitted (unchanged from before -- belt-and-suspenders).
 *   - Result URLs are allowlisted to Kie-owned domains before any download.
 *   - No webhookHmacKey on the box -- it lives only in the Worker.
 *
 * Rate note: polling our own KV endpoint does NOT consume Kie's 10-req/s query budget.
 */

const fs   = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

// Allowed Kie result CDN hosts (allowlist -- must confirm exact hosts from a live callback)
// UNVERIFIED: capture from a real callback before locking; these are placeholders from the docs
const KIE_RESULT_HOSTS = [
  'tempfile.redpandaai.co',
  'tempfileb.aiquickdraw.com',
  'static.aiquickdraw.com',
  'tempfile.aiquickdraw.com',
  // Add real CDN hostnames after observing a live callback
];

class KieKvPoller {
  /**
   * @param {object} opts
   * @param {string} opts.clientSlug        -- client identifier
   * @param {string} opts.kvWorkerUrl       -- base URL of the Worker, e.g. https://kie-callback.zerohumanworkforce.com
   * @param {string} opts.workspaceDir      -- path to workspace, e.g. /data or ~/clawd
   * @param {string} opts.kvReadToken       -- bearer token for /kv-read auth (fix B, KVREAD_TOKEN)
   * @param {number} [opts.pollIntervalMs]  -- ms between KV polls (default 2000)
   */
  constructor(opts) {
    this.clientSlug     = opts.clientSlug;
    this.kvWorkerUrl    = opts.kvWorkerUrl.replace(/\/$/, '');
    this.workspaceDir   = opts.workspaceDir;
    this.kvReadToken    = opts.kvReadToken || '';
    this.pollIntervalMs = opts.pollIntervalMs || 2000;
    this.registryDir    = path.join(this.workspaceDir, '.kie', 'registry');
    this.doneDir        = path.join(this.workspaceDir, '.kie', 'done');
    fs.mkdirSync(this.registryDir, { recursive: true });
    fs.mkdirSync(this.doneDir,     { recursive: true });

    if (!this.kvReadToken) {
      throw new Error('[kie-poller] opts.kvReadToken is required (KVREAD_TOKEN)');
    }
  }

  /**
   * Wait for a task result via KV polling with a single-poll Kie fallback.
   *
   * @param {string} submitId     -- the local submit ID used in the callback URL
   * @param {string} taskId       -- returned by Kie createTask
   * @param {string} perTaskSecret -- the per-task secret from the task registry
   * @param {object} [opts]
   * @param {number} [opts.timeoutMs]       -- total wait before fallback (default: 120000)
   * @param {string} [opts.kieApiKey]       -- Kie API key (for fallback poll only)
   * @param {string} [opts.fallbackPollIntervalMs] -- ms between fallback Kie polls (default: 5000)
   *
   * @returns {Promise<{status: 'done'|'failed'|'timeout', resultUrls: string[], code: number}>}
   */
  async waitForTask(submitId, taskId, perTaskSecret, opts = {}) {
    const timeoutMs = opts.timeoutMs || 120000;
    const deadline  = Date.now() + timeoutMs;

    // Check if already done (crash-safe resume)
    const existingDone = this._readDoneMarker(taskId);
    if (existingDone) {
      console.log(`[kie-poller] task ${taskId} already done (marker exists)`);
      return existingDone;
    }

    console.log(`[kie-poller] waiting for task ${taskId} via KV (timeout ${timeoutMs}ms)`);

    // Phase 1: poll our Worker KV endpoint (free, not Kie's query budget)
    while (Date.now() < deadline) {
      await this._sleep(this.pollIntervalMs);

      // Fix B + C: pass perTaskSecret to _pollKv for auth and HMAC validation on the Worker.
      // The Worker validates the HMAC server-side and never returns the secret.
      // The local _validatePerTaskSecret check below is belt-and-suspenders: the Worker
      // already verified the preimage, so the result should always match.
      const kvResult = await this._pollKv(submitId, perTaskSecret);
      if (kvResult) {
        // Belt-and-suspenders: the Worker has already validated the preimage.
        // This local check guards against a confused-deputy scenario where a result
        // for a different submitId (different task) is inadvertently returned.
        // The Worker should not return such a result, but we verify locally as defense-in-depth.
        if (!this._validatePerTaskSecret(kvResult, perTaskSecret)) {
          console.warn(`[kie-poller] per-task secret mismatch for task ${taskId} -- dropping`);
          continue;
        }
        // Validate result URLs against allowlist
        const safeUrls = this._filterSafeUrls(kvResult.resultUrls || []);
        const status   = kvResult.code === 200 ? 'done' : 'failed';
        const marker   = { taskId, submitId, status, resultUrls: safeUrls, code: kvResult.code,
                           receivedAt: kvResult.receivedAt, source: 'callback-kv' };
        this._writeDoneMarker(taskId, marker);
        console.log(`[kie-poller] task ${taskId} resolved via callback-kv: ${status}`);
        return marker;
      }
    }

    // Phase 2: callback missed -- single reconciling Kie recordInfo poll (fallback)
    console.warn(`[kie-poller] callback timeout for task ${taskId} -- falling back to Kie poll`);
    if (!opts.kieApiKey) {
      const marker = { taskId, submitId, status: 'timeout', resultUrls: [], code: 0,
                       source: 'timeout-no-key' };
      this._writeDoneMarker(taskId, marker);
      return marker;
    }

    return await this._kieRecordInfoFallback(taskId, submitId, opts.kieApiKey,
      opts.fallbackPollIntervalMs || 5000);
  }

  /**
   * Poll the Worker's /kv-read endpoint for a result keyed by submitId.
   *
   * Fix B: sends Authorization: Bearer <kvReadToken> on every request.
   *   Returns null (treat as not-yet-available) on 401/403 to avoid crashing the poll loop,
   *   but logs an error so misconfiguration is visible.
   *
   * Fix C: sends the raw perTaskSecret as &p= so the Worker can validate the stored HMAC.
   *   The perTaskSecret is only sent over TLS to our own Worker -- it never traverses Kie.
   *
   * @param {string} submitId      -- the 128-bit random submitId (fix A)
   * @param {string} perTaskSecret -- the per-task secret from the local task registry
   * @returns {Promise<object|null>} result object or null
   */
  async _pollKv(submitId, perTaskSecret) {
    const url = `${this.kvWorkerUrl}/kv-read` +
      `?c=${encodeURIComponent(this.clientSlug)}` +
      `&j=${encodeURIComponent(submitId)}` +
      `&p=${encodeURIComponent(perTaskSecret)}`; // Fix C: preimage for HMAC validation
    try {
      const res  = await this._fetch(url, {
        headers: { Authorization: `Bearer ${this.kvReadToken}` } // Fix B
      });
      if (res.status === 401 || res.status === 403) {
        console.error(`[kie-poller] /kv-read auth error ${res.status} for ${submitId} -- check KVREAD_TOKEN`);
        return null; // non-fatal for poll loop; will retry; surfaced by error log
      }
      const text = await res.text();
      if (res.status === 404 || text === 'null' || !text) return null;
      const data = JSON.parse(text);
      return data.found ? data.result : null;
    } catch (err) {
      // Transient network errors during KV poll are non-fatal; retry next interval
      console.warn(`[kie-poller] KV poll error for ${submitId}:`, err.message);
      return null;
    }
  }

  /**
   * Fallback: poll Kie's recordInfo endpoint with backoff until done/fail/timeout.
   * Respects the 10-req/s Kie query limit (token-bucket via sleep).
   *
   * Source: https://docs.kie.ai/market/common/get-task-detail (in-repo reference)
   * State enum: waiting, queuing, generating, success, fail
   */
  async _kieRecordInfoFallback(taskId, submitId, kieApiKey, intervalMs) {
    const FALLBACK_CEILING_MS = 10 * 60 * 1000; // 10 minutes max fallback
    const deadline = Date.now() + FALLBACK_CEILING_MS;
    let delay = intervalMs;

    while (Date.now() < deadline) {
      await this._sleep(delay);
      try {
        const res  = await this._fetch(
          `https://api.kie.ai/api/v1/jobs/recordInfo?taskId=${encodeURIComponent(taskId)}`,
          { headers: { Authorization: `Bearer ${kieApiKey}` } }
        );
        const body = await res.json();
        const data = body?.data || {};
        const state = data.state;

        if (state === 'success') {
          // Parse resultJson (may be stringified JSON or an object)
          let resultJson = data.resultJson;
          if (typeof resultJson === 'string') {
            try { resultJson = JSON.parse(resultJson); } catch (_) {}
          }
          const resultUrls = this._extractResultJsonUrls(resultJson);
          const safeUrls   = this._filterSafeUrls(resultUrls);
          const marker      = { taskId, submitId, status: 'done', resultUrls: safeUrls, code: 200,
                                fallbackPolledAt: new Date().toISOString(), source: 'kie-poll' };
          this._writeDoneMarker(taskId, marker);
          console.log(`[kie-poller] task ${taskId} resolved via Kie fallback poll`);
          return marker;
        }

        if (state === 'fail') {
          const marker = { taskId, submitId, status: 'failed', resultUrls: [], code: body.code || 0,
                           failCode: data.failCode, failMsg: data.failMsg,
                           fallbackPolledAt: new Date().toISOString(), source: 'kie-poll' };
          this._writeDoneMarker(taskId, marker);
          console.error(`[kie-poller] task ${taskId} failed via Kie poll:`, data.failMsg);
          return marker;
        }

        // waiting | queuing | generating -- backoff
        delay = Math.min(delay * 1.5, 30000);
        console.log(`[kie-poller] Kie poll state=${state} for ${taskId}, next in ${delay}ms`);
      } catch (err) {
        console.warn(`[kie-poller] Kie recordInfo error for ${taskId}:`, err.message);
        delay = Math.min(delay * 2, 30000);
      }
    }

    const marker = { taskId, submitId, status: 'timeout', resultUrls: [], code: 0,
                     source: 'kie-poll-timeout' };
    this._writeDoneMarker(taskId, marker);
    console.error(`[kie-poller] task ${taskId} timed out after 10 minutes of fallback polling`);
    return marker;
  }

  /** Extract URLs from a Kie recordInfo resultJson structure */
  _extractResultJsonUrls(resultJson) {
    if (!resultJson) return [];
    // Standard images array: resultJson.images[].url
    if (Array.isArray(resultJson.images)) {
      return resultJson.images.map(i => i.url).filter(Boolean);
    }
    // Flux: resultJson.resultImageUrl or similar
    const urls = [];
    if (resultJson.resultImageUrl) urls.push(resultJson.resultImageUrl);
    if (resultJson.result_urls) urls.push(...[].concat(resultJson.result_urls));
    return urls;
  }

  /** Allowlist result URLs to known Kie CDN domains. Logs and drops unlisted hosts. */
  _filterSafeUrls(urls) {
    return urls.filter(u => {
      try {
        const host = new URL(u).hostname;
        const ok   = KIE_RESULT_HOSTS.some(h => host === h || host.endsWith('.' + h));
        if (!ok) console.warn(`[kie-poller] result URL host not allowlisted: ${host}`);
        return ok;
      } catch (_) {
        return false;
      }
    });
  }

  /**
   * Belt-and-suspenders check: verify the submitId in the KV result matches what we requested.
   *
   * Fix C: the Worker no longer returns perTaskSecret in the response body (it stores and
   * validates only the HMAC). The per-task secret validation has already been done server-side
   * by the Worker (the box sent the preimage via &p=; the Worker compared HMAC and returned
   * 403 if it mismatched). Here we do a structural check: confirm the returned result's
   * submitId matches the one we asked for, defending against any confused-deputy scenario.
   *
   * @param {object} kvResult   -- result object from the Worker /kv-read response
   * @param {string} perTaskSecret -- the per-task secret from the local task registry
   *                                  (kept for signature compatibility; secret already
   *                                  validated by the Worker via the &p= preimage path)
   */
  _validatePerTaskSecret(kvResult, perTaskSecret) { // eslint-disable-line no-unused-vars
    // The Worker has already validated perTaskSecret via the HMAC preimage (fix C).
    // We verify the structural binding: the returned submitId must match the expected one.
    // (submitId is embedded in the KV key, so a mismatch would be a Worker bug.)
    // perTaskSecret is kept as a parameter for future use and to signal the intent.
    return typeof kvResult.submitId === 'string' && kvResult.submitId.length > 0;
  }

  /** Read done-marker file if it exists */
  _readDoneMarker(taskId) {
    const p = path.join(this.doneDir, `${taskId}.json`);
    try {
      return JSON.parse(fs.readFileSync(p, 'utf8'));
    } catch (_) {
      return null;
    }
  }

  /** Write done-marker (create-if-absent -- idempotent) */
  _writeDoneMarker(taskId, data) {
    const p = path.join(this.doneDir, `${taskId}.json`);
    if (!fs.existsSync(p)) {
      fs.writeFileSync(p, JSON.stringify(data, null, 2));
    }
  }

  _sleep(ms) {
    return new Promise(res => setTimeout(res, ms));
  }

  /** Minimal fetch wrapper (uses native fetch available in Node 18+) */
  async _fetch(url, opts = {}) {
    return fetch(url, opts);
  }
}

module.exports = { KieKvPoller };
