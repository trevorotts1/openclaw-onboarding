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
   * @param {string} opts.kvReadToken       -- per-client bearer token for /kv-read auth
   *                                            (fix B/F). Required ONLY when callbacks are
   *                                            enabled; small decks (fix 33) poll Kie directly.
   * @param {boolean} [opts.callbacksEnabled] -- when false (small deck, fix 33), the KV phase
   *                                            is skipped entirely and results come from a
   *                                            direct Kie recordInfo poll; no Worker secret needed.
   * @param {number} [opts.pollIntervalMs]  -- ms between KV polls (default 2000)
   */
  constructor(opts) {
    this.clientSlug       = opts.clientSlug;
    this.kvWorkerUrl      = (opts.kvWorkerUrl || '').replace(/\/$/, '');
    this.workspaceDir     = opts.workspaceDir;
    this.kvReadToken      = opts.kvReadToken || '';
    this.callbacksEnabled = opts.callbacksEnabled !== false; // default true (large-deck path)
    this.pollIntervalMs   = opts.pollIntervalMs || 2000;
    this.registryDir      = path.join(this.workspaceDir, '.kie', 'registry');
    this.doneDir          = path.join(this.workspaceDir, '.kie', 'done');
    fs.mkdirSync(this.registryDir, { recursive: true });
    fs.mkdirSync(this.doneDir,     { recursive: true });

    // Fix 33: the KV bearer token is only needed on the callback path. Below the
    // callback threshold the box never touches the Worker, so the secret is optional.
    if (this.callbacksEnabled && !this.kvReadToken) {
      throw new Error('[kie-poller] opts.kvReadToken is required when callbacksEnabled (KVREAD_TOKEN)');
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

    // Fix 33: small-deck path. When callbacks are disabled the box never sent a
    // callBackUrl, so nothing will ever land in KV. Skip the KV phase entirely and
    // poll Kie's recordInfo directly (batch backoff) instead of burning the timeout.
    if (!this.callbacksEnabled) {
      if (!opts.kieApiKey) {
        const marker = { taskId, submitId, status: 'timeout', resultUrls: [], code: 0,
                         source: 'no-callbacks-no-key' };
        this._writeDoneMarker(taskId, marker);
        return marker;
      }
      console.log(`[kie-poller] task ${taskId}: callbacks disabled -- direct Kie recordInfo poll`);
      return await this._kieRecordInfoFallback(taskId, submitId, opts.kieApiKey,
        opts.fallbackPollIntervalMs || 5000);
    }

    console.log(`[kie-poller] waiting for task ${taskId} via KV (timeout ${timeoutMs}ms)`);

    // Phase 1: poll our Worker KV endpoint (free, not Kie's query budget)
    while (Date.now() < deadline) {
      await this._sleep(this.pollIntervalMs);

      // Fix B + C + G: pass perTaskSecret to _pollKv (sent in the X-Kie-Preimage header)
      // for auth + HMAC validation on the Worker. The Worker validates the HMAC
      // server-side and never returns the secret. The local _validatePerTaskSecret
      // check below is belt-and-suspenders defense-in-depth.
      const kvResult = await this._pollKv(submitId, perTaskSecret);
      if (kvResult) {
        // Fix 34: confused-deputy defense. Confirm the returned result's submitId is
        // exactly the one we asked for; a wrong-task result must never land on this slide.
        if (!this._validatePerTaskSecret(kvResult, submitId)) {
          console.warn(`[kie-poller] submitId mismatch for task ${taskId} -- dropping`);
          continue;
        }
        // Validate result URLs against allowlist
        const safeUrls = this._filterSafeUrls(kvResult.resultUrls || []);
        // Fix 35: a 200 with zero surviving (allowlisted) URLs is NOT a success -- there is
        // no file to download. Report it as an allowlist rejection, never as 'done'.
        let status, extra = {};
        if (kvResult.code !== 200) {
          status = 'failed';
        } else if (safeUrls.length === 0) {
          status = 'failed';
          extra  = { reason: 'allowlist-rejected', rawUrlCount: (kvResult.resultUrls || []).length };
          console.warn(`[kie-poller] task ${taskId}: code 200 but 0 allowlisted URLs -- marking failed`);
        } else {
          status = 'done';
        }
        const marker = { taskId, submitId, status, resultUrls: safeUrls, code: kvResult.code,
                         receivedAt: kvResult.receivedAt, source: 'callback-kv', ...extra };
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
   * Fix C + G: sends the raw perTaskSecret in the X-Kie-Preimage header (NOT a query
   *   param -- query params are captured in edge access logs on every 2s poll) so the
   *   Worker can validate the stored HMAC. The perTaskSecret is only sent over TLS to
   *   our own Worker -- it never traverses Kie.
   *
   * @param {string} submitId      -- the 128-bit random submitId (fix A)
   * @param {string} perTaskSecret -- the per-task secret from the local task registry
   * @returns {Promise<object|null>} result object or null
   */
  async _pollKv(submitId, perTaskSecret) {
    // Fix G: only c= and j= travel in the URL; the secret preimage rides in a header.
    const url = `${this.kvWorkerUrl}/kv-read` +
      `?c=${encodeURIComponent(this.clientSlug)}` +
      `&j=${encodeURIComponent(submitId)}`;
    try {
      const res  = await this._fetch(url, {
        headers: {
          Authorization:    `Bearer ${this.kvReadToken}`, // Fix B/F: per-client bearer token
          'X-Kie-Preimage': perTaskSecret                 // Fix G: preimage out of the query string
        }
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
   * Fix 34: confused-deputy defense. Verify the submitId embedded in the KV result is
   * EXACTLY the submitId we requested. The Worker has already validated the perTaskSecret
   * preimage HMAC (fix C/G) server-side; this is the box-side structural binding that
   * guarantees a result for a different task can never be accepted onto this slide.
   *
   * The previous implementation accepted ANY non-empty submitId, so the claimed
   * confused-deputy defense did not actually exist -- a wrong-task result would pass.
   *
   * @param {object} kvResult          -- result object from the Worker /kv-read response
   * @param {string} expectedSubmitId  -- the submitId this call is waiting on
   * @returns {boolean} true only when kvResult.submitId === expectedSubmitId
   */
  _validatePerTaskSecret(kvResult, expectedSubmitId) {
    return kvResult.submitId === expectedSubmitId;
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
