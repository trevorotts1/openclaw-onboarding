/**
 * Kie Callback KV Poller -- runs on the client box (Mac or Docker)
 *
 * Transport B2: the box polls Cloudflare KV for the verified callback result.
 * This means ZERO inbound public route on the box and ZERO Cloudflare Access bypass.
 *
 * Usage: called by the slide submitter after each batch of createTask submits.
 *   const poller = new KieKvPoller({ clientSlug, kvBaseUrl, kvApiToken, workspaceDir });
 *   const result = await poller.waitForTask(submitId, taskId, perTaskSecret, { timeoutMs });
 *
 * Required env vars on the box (in ~/clawd/secrets/.env or /docker/<project>/.env):
 *   KIE_KV_BASE_URL   -- the Worker KV read endpoint, e.g. https://kie-callback.zerohumanworkforce.com/kv-read
 *   KIE_CLIENT_SLUG   -- this box's client identifier (e.g. "operator-demo")
 *
 * Security:
 *   - perTaskSecret is validated against the local task registry before trusting the result.
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
   * @param {number} [opts.pollIntervalMs]  -- ms between KV polls (default 2000)
   */
  constructor(opts) {
    this.clientSlug     = opts.clientSlug;
    this.kvWorkerUrl    = opts.kvWorkerUrl.replace(/\/$/, '');
    this.workspaceDir   = opts.workspaceDir;
    this.pollIntervalMs = opts.pollIntervalMs || 2000;
    this.registryDir    = path.join(this.workspaceDir, '.kie', 'registry');
    this.doneDir        = path.join(this.workspaceDir, '.kie', 'done');
    fs.mkdirSync(this.registryDir, { recursive: true });
    fs.mkdirSync(this.doneDir,     { recursive: true });
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

      const kvResult = await this._pollKv(submitId);
      if (kvResult) {
        // Validate per-task secret against registry
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
   * Returns the parsed result object or null if not yet available.
   */
  async _pollKv(submitId) {
    const url = `${this.kvWorkerUrl}/kv-read?c=${encodeURIComponent(this.clientSlug)}&j=${encodeURIComponent(submitId)}`;
    try {
      const res  = await this._fetch(url);
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

  /** Check per-task secret matches what is stored in the KV result */
  _validatePerTaskSecret(kvResult, perTaskSecret) {
    return kvResult.perTaskSecret === perTaskSecret;
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
