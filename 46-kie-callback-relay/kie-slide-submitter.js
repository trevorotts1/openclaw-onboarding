/**
 * Kie Slide Submitter -- webhook-primary, poll-fallback, crash-safe
 *
 * Implements the DESIGN.md section 7 + 8 submit-and-wait loop:
 *   1. For each slide: generate perTaskSecret, write registry row (status: submitted)
 *   2. POST createTask with callBackUrl pointing at the central Worker
 *   3. Record returned taskId into registry; write taskId->submitId index
 *   4. Submit ALL slides first (respecting 20-per-10-seconds rate limit), THEN wait
 *   5. Wait by polling local done-markers (cheap, local disk, not Kie's query budget)
 *   6. Fallback: if done-marker not found within timeout, poll Kie recordInfo once,
 *      then backoff, then mark failed-timeout at ceiling
 *   7. Crash-safe resume: on restart, skip slides already in registry with a taskId
 *
 * Rate limits observed (source: https://docs.kie.ai/, verified 2026-06-14):
 *   Creation: 20 requests per 10 seconds per account
 *   Status query: 10 requests per second per API key (in-repo kie-setup-full.md)
 *
 * Usage:
 *   const submitter = new KieSlideSubmitter({ clientSlug, kieApiKey, kvWorkerUrl, workspaceDir });
 *   const results = await submitter.submitDeck(slides, { model, callbackThreshold });
 *
 * The callBackUrl format: https://kie-callback.zerohumanworkforce.com/cb?c=<client>&j=<submitId>&s=<secret>
 */

const fs     = require('fs');
const path   = require('path');
const crypto = require('crypto');
const { KieKvPoller } = require('./box-kv-poller');

const KIE_CREATE_TASK_URL = 'https://api.kie.ai/api/v1/jobs/createTask';
const CALLBACK_WORKER_URL = 'https://kie-callback.zerohumanworkforce.com';

// 20 requests per 10 seconds per account -- source: https://docs.kie.ai/ (verified 2026-06-14)
const RATE_LIMIT_MAX    = 20;
const RATE_LIMIT_WINDOW = 10000; // ms

// Callback mode threshold: use webhook+KV for decks with more slides than this;
// use efficient batch polling (Candidate C from DESIGN.md) for smaller decks.
const DEFAULT_CALLBACK_THRESHOLD = 5;

// Per-model callback timeout defaults (ms) before falling back to Kie poll
const MODEL_TIMEOUTS = {
  'nano-banana-pro': 120000,  // 2 minutes (fast model)
  'default':         180000   // 3 minutes fallback
};

class KieSlideSubmitter {
  /**
   * @param {object} opts
   * @param {string} opts.clientSlug    -- client identifier (no spaces/special chars)
   * @param {string} opts.kieApiKey     -- Kie API key (Bearer token)
   * @param {string} opts.kvWorkerUrl   -- Worker base URL
   * @param {string} opts.workspaceDir  -- path to workspace directory
   */
  constructor(opts) {
    this.clientSlug   = opts.clientSlug;
    this.kieApiKey    = opts.kieApiKey;
    this.kvWorkerUrl  = opts.kvWorkerUrl || CALLBACK_WORKER_URL;
    this.workspaceDir = opts.workspaceDir;

    this.registryDir  = path.join(this.workspaceDir, '.kie', 'registry');
    this.indexDir     = path.join(this.workspaceDir, '.kie', 'index');
    this.doneDir      = path.join(this.workspaceDir, '.kie', 'done');
    fs.mkdirSync(this.registryDir, { recursive: true });
    fs.mkdirSync(this.indexDir,    { recursive: true });
    fs.mkdirSync(this.doneDir,     { recursive: true });

    this.poller = new KieKvPoller({
      clientSlug:   this.clientSlug,
      kvWorkerUrl:  this.kvWorkerUrl,
      workspaceDir: this.workspaceDir
    });

    // Token bucket for rate limiting (20 per 10s)
    this._bucket = { tokens: RATE_LIMIT_MAX, lastRefill: Date.now() };
  }

  /**
   * Submit a deck of slides to Kie and wait for all results.
   *
   * @param {Array<{slideId, prompt, model, targetPath, deckId, inputImages}>} slides
   * @param {object} [opts]
   * @param {string} [opts.model]               -- override model for all slides
   * @param {number} [opts.callbackThreshold]   -- slide count above which callbacks are used
   * @param {number} [opts.timeoutMs]           -- per-slide callback timeout (ms)
   * @returns {Promise<Array<{slideId, status, resultUrls, localPath, code}>>}
   */
  async submitDeck(slides, opts = {}) {
    const threshold = opts.callbackThreshold ?? DEFAULT_CALLBACK_THRESHOLD;
    const useCallbacks = slides.length > threshold;

    console.log(`[kie-submit] deck of ${slides.length} slides; callbacks=${useCallbacks} (threshold=${threshold})`);

    // --- Phase 1: Resume-safe registry load; skip already-submitted slides ---
    const pending   = [];
    const submitted = []; // slides with existing taskId (crash-resume)

    for (const slide of slides) {
      const submitId = this._makeSubmitId(slide.deckId, slide.slideId);
      const existing = this._readRegistry(submitId);

      if (existing?.taskId) {
        // Already submitted; check if done
        const done = this._readDoneMarker(existing.taskId);
        if (done) {
          submitted.push({ ...slide, submitId, taskId: existing.taskId, done });
        } else {
          // Was submitted but not done -- re-enter the wait queue
          pending.push({ ...slide, submitId, taskId: existing.taskId,
                         perTaskSecret: existing.perTaskSecret, existing: true });
        }
      } else {
        pending.push({ ...slide, submitId, taskId: null, existing: false });
      }
    }

    console.log(`[kie-submit] resume: ${submitted.length} already done, ${pending.length} to process`);

    // --- Phase 2: Submit new tasks (rate-limited, 20 per 10s) ---
    const toWait = [...pending.filter(s => s.existing)]; // already submitted, not done

    for (const slide of pending.filter(s => !s.existing)) {
      await this._throttle();

      const model         = slide.model || opts.model || 'nano-banana-pro';
      const perTaskSecret = crypto.randomBytes(32).toString('hex');
      const submitId      = slide.submitId;

      // Write registry BEFORE submitting (crash-safe: write first, then submit)
      const regRow = {
        submitId,
        clientSlug:   this.clientSlug,
        deckId:       slide.deckId,
        slideId:      slide.slideId,
        model,
        targetPath:   slide.targetPath,
        perTaskSecret,
        callBackUrl:  useCallbacks
          ? `${this.kvWorkerUrl}/cb?c=${encodeURIComponent(this.clientSlug)}&j=${encodeURIComponent(submitId)}&s=${perTaskSecret}`
          : null,
        submittedAt:  new Date().toISOString(),
        status:       'submitting',
        taskId:       null,
        fallbackPolledAt: null
      };
      this._writeRegistry(submitId, regRow);

      try {
        const body = {
          model,
          input: {
            prompt:       slide.prompt,
            aspect_ratio: slide.aspect_ratio || '16:9',
            resolution:   slide.resolution   || '2K',
            output_format: 'png'
          }
        };
        if (slide.inputImages?.length) {
          body.input.image_input = slide.inputImages;
        }
        if (useCallbacks) {
          body.callBackUrl = regRow.callBackUrl;
        }

        const res      = await this._kiePost(KIE_CREATE_TASK_URL, body);
        const json     = await res.json();

        if (json.code !== 200 || !json.data?.taskId) {
          console.error(`[kie-submit] createTask failed for slide ${slide.slideId}:`, json);
          regRow.status = 'failed-submit';
          this._writeRegistry(submitId, regRow);
          submitted.push({ ...slide, submitId, taskId: null, done: { status: 'failed', resultUrls: [], code: json.code } });
          continue;
        }

        const taskId = json.data.taskId;
        regRow.taskId = taskId;
        regRow.status = 'submitted';
        this._writeRegistry(submitId, regRow);

        // Write taskId -> submitId index
        this._writeIndex(taskId, submitId);

        toWait.push({ ...slide, submitId, taskId, perTaskSecret });
        console.log(`[kie-submit] slide ${slide.slideId} submitted: taskId=${taskId} callback=${!!useCallbacks}`);
      } catch (err) {
        console.error(`[kie-submit] createTask error for slide ${slide.slideId}:`, err.message);
        regRow.status = 'error-submit';
        this._writeRegistry(submitId, regRow);
        submitted.push({ ...slide, submitId, taskId: null, done: { status: 'failed', resultUrls: [], code: 0 } });
      }
    }

    // --- Phase 3: Wait for all tasks in parallel ---
    if (toWait.length === 0) {
      console.log('[kie-submit] no tasks to wait for');
    }

    const waitResults = await Promise.all(toWait.map(async slide => {
      const timeoutMs = opts.timeoutMs || MODEL_TIMEOUTS[slide.model] || MODEL_TIMEOUTS.default;
      const done = await this.poller.waitForTask(
        slide.submitId,
        slide.taskId,
        slide.perTaskSecret,
        { timeoutMs, kieApiKey: this.kieApiKey }
      );

      // Update registry with final status
      const reg = this._readRegistry(slide.submitId) || {};
      reg.status = done.status;
      reg.fallbackPolledAt = done.fallbackPolledAt || reg.fallbackPolledAt;
      this._writeRegistry(slide.submitId, reg);

      // Download image if done and has URLs
      let localPath = slide.targetPath;
      if (done.status === 'done' && done.resultUrls?.length && slide.targetPath) {
        localPath = await this._downloadFirst(done.resultUrls, slide.targetPath);
      }

      return { slideId: slide.slideId, submitId: slide.submitId, taskId: slide.taskId,
               status: done.status, resultUrls: done.resultUrls, localPath, code: done.code };
    }));

    // Merge already-done slides
    const alreadyDone = submitted.map(s => ({
      slideId: s.slideId, submitId: s.submitId, taskId: s.taskId,
      status: s.done.status, resultUrls: s.done.resultUrls || [],
      localPath: s.targetPath, code: s.done.code
    }));

    const allResults = [...alreadyDone, ...waitResults];

    const failed  = allResults.filter(r => r.status !== 'done').length;
    const success = allResults.filter(r => r.status === 'done').length;
    console.log(`[kie-submit] deck complete: ${success} done, ${failed} failed/timeout`);

    return allResults;
  }

  // --- Rate limiter (token bucket, 20 per 10s) ---
  async _throttle() {
    const now     = Date.now();
    const elapsed = now - this._bucket.lastRefill;
    if (elapsed >= RATE_LIMIT_WINDOW) {
      this._bucket.tokens    = RATE_LIMIT_MAX;
      this._bucket.lastRefill = now;
    }
    if (this._bucket.tokens > 0) {
      this._bucket.tokens--;
      return;
    }
    // Wait for the remainder of the window then retry
    const wait = RATE_LIMIT_WINDOW - elapsed + 50;
    console.log(`[kie-submit] rate limit reached; waiting ${wait}ms`);
    await new Promise(res => setTimeout(res, wait));
    this._bucket.tokens    = RATE_LIMIT_MAX - 1;
    this._bucket.lastRefill = Date.now();
  }

  // --- Kie API POST helper ---
  async _kiePost(url, body) {
    return fetch(url, {
      method:  'POST',
      headers: {
        'Authorization': `Bearer ${this.kieApiKey}`,
        'Content-Type':  'application/json'
      },
      body: JSON.stringify(body)
    });
  }

  // --- Download first valid result URL to targetPath ---
  async _downloadFirst(urls, targetPath) {
    for (const url of urls) {
      try {
        const res = await fetch(url);
        if (!res.ok) continue;
        const buf = Buffer.from(await res.arrayBuffer());
        fs.mkdirSync(path.dirname(targetPath), { recursive: true });
        fs.writeFileSync(targetPath, buf);
        console.log(`[kie-submit] downloaded to ${targetPath}`);
        return targetPath;
      } catch (err) {
        console.warn(`[kie-submit] download failed for ${url}:`, err.message);
      }
    }
    return targetPath; // return path even if download failed; caller checks file existence
  }

  // --- Registry helpers ---
  _makeSubmitId(deckId, slideId) {
    return `${deckId}_${slideId}`;
  }

  _readRegistry(submitId) {
    const p = path.join(this.registryDir, `${submitId}.json`);
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; }
  }

  _writeRegistry(submitId, data) {
    const p = path.join(this.registryDir, `${submitId}.json`);
    fs.writeFileSync(p, JSON.stringify(data, null, 2));
  }

  _writeIndex(taskId, submitId) {
    const p = path.join(this.indexDir, `${taskId}.json`);
    fs.writeFileSync(p, JSON.stringify({ taskId, submitId }));
  }

  _readDoneMarker(taskId) {
    const p = path.join(this.doneDir, `${taskId}.json`);
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; }
  }
}

module.exports = { KieSlideSubmitter };
