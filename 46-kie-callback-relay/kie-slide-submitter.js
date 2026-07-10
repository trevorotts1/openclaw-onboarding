/**
 * Kie Slide Submitter -- webhook-primary, poll-fallback, crash-safe
 *
 * Implements the DESIGN.md section 7 + 8 submit-and-wait loop:
 *   1. For each slide: generate perTaskSecret + random submitId, write registry row
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
 *   const submitter = new KieSlideSubmitter({
 *     clientSlug, kieApiKey, kvWorkerUrl, workspaceDir,
 *     callbackHmacKey,  -- shared with Worker (KIE_CALLBACK_HMAC_KEY)
 *     kvReadToken       -- shared with Worker (KVREAD_TOKEN)
 *   });
 *   const results = await submitter.submitDeck(slides, { model, callbackThreshold });
 *
 * callBackUrl format (security-hardened, 2026-06-14):
 *   /cb?c=<clientSlug>&j=<submitId>&s=<callbackValidator>&h=<perTaskSecretHmac>
 *
 *   submitId          -- 128-bit random hex (fix A); never deckId_slideId
 *   callbackValidator -- HMAC-SHA256(clientSlug + ":" + submitId, callbackHmacKey) (fix D)
 *   perTaskSecretHmac -- HMAC-SHA256(perTaskSecret, callbackHmacKey) (fix C)
 *
 * Neither the raw perTaskSecret nor any other secret appears in the URL (fixes C + D).
 */

const fs     = require('fs');
const path   = require('path');
const crypto = require('crypto');
const { KieKvPoller } = require('./box-kv-poller');

const KIE_CREATE_TASK_URL = 'https://api.kie.ai/api/v1/jobs/createTask';
// The relay Worker base URL is per-deployment. Read it from KIE_KV_BASE_URL (set per box in the
// box .env; see DEPLOY.md) or pass opts.kvWorkerUrl. The placeholder default carries no operator
// zone -- an unconfigured box fails loudly on DNS rather than silently hitting someone else's relay.
const CALLBACK_WORKER_URL = process.env.KIE_KV_BASE_URL || 'https://kie-callback.<your-cf-zone>';

// 20 requests per 10 seconds per account -- source: https://docs.kie.ai/ (verified 2026-06-14)
const RATE_LIMIT_MAX    = 20;
const RATE_LIMIT_WINDOW = 10000; // ms

// Callback mode threshold: use webhook+KV for decks with more slides than this;
// use efficient batch polling (Candidate C from DESIGN.md) for smaller decks.
const DEFAULT_CALLBACK_THRESHOLD = 5;

// MODEL TIMEOUTS -- primary model is gpt-image-2-text-to-image. nano-banana-pro is FALLBACK-ONLY.
// Per-model callback timeout defaults (ms) before falling back to Kie poll
const MODEL_TIMEOUTS = {
  'gpt-image-2-text-to-image':  300000,  // 5 minutes (primary model for all client presentations)
  'gpt-image-2-image-to-image': 300000,  // 5 minutes (primary model with reference images)
  // FALLBACK-ONLY: nano-banana-pro fires only on hard API failure of the primary. Never use as primary.
  'nano-banana-pro': 120000,  // 2 minutes (fast model -- FALLBACK-ONLY)
  'default':         180000   // 3 minutes fallback
};

// ---------------------------------------------------------------------------
// SHARED IMAGE-PROMPT GATE PARITY (canonical gate: prompt_gate.py)
// ---------------------------------------------------------------------------
// This relay used to POST any `slide.prompt` to the paid kie.ai API with ZERO quality
// checks. It is SHARED across skills — Skill 47 (movie frames), Skill 59 (Anthology book
// covers), and the video roles all submit through it — so the PRESENTATIONS-specific
// 9,000–18,000-char floor + English/Latin pin + gpt-image-2 mode-pin are OPT-IN via
// KIE_PROMPT_GATE=presentations (mirrors prompt_gate.presentations_gate_enabled). Forcing
// the deck band / English-only pin on a movie frame or a portrait book cover would break
// those skills, so by DEFAULT this relay enforces only the universal-safe floor
// (dead-endpoint + empty-prompt refusal). Keep these constants in lockstep with prompt_gate.py.
const PROMPT_CHAR_FLOOR   = 9000;   // HARD floor (AF-P1)  — mirror of prompt_gate.PROMPT_CHAR_FLOOR
const PROMPT_CHAR_CEILING = 18000;  // HARD ceiling (AF-P2)— mirror of prompt_gate.PROMPT_CHAR_CEILING
const GATE_MODEL_I2I      = 'gpt-image-2-image-to-image';
const DEAD_ENDPOINT_FRAGMENT = '/api/v1/image/gpt-image';
const ENGLISH_PIN =
  'All text rendered in the image MUST be in English, Latin alphabet ONLY. ' +
  'NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled ' +
  'correctly, letter-for-letter. No garbled, misspelled, or invented text.';

function _normWs(s) { return String(s).replace(/\s+/g, ' ').trim().toLowerCase(); }

// True iff the PRESENTATIONS full gate is opted into (KIE_PROMPT_GATE=presentations|full|1|on|true).
function _presentationsGateEnabled() {
  const v = String(process.env.KIE_PROMPT_GATE || '').trim().toLowerCase();
  return v === 'presentations' || v === 'full' || v === '1' || v === 'on' || v === 'true';
}

/**
 * Gate one slide's prompt before it reaches the paid kie.ai createTask call. Throws on any
 * violation (the caller's try/catch marks the slide failed and it is never submitted).
 * Universal-safe checks (dead-endpoint + empty-prompt refusal) ALWAYS run. The presentations
 * length + mode + pin invariants run only when KIE_PROMPT_GATE=presentations, so shared
 * callers (movie / Anthology / video) are unaffected by default.
 * Returns the prompt (with the English/Latin pin appended when the presentations gate is on).
 */
function gateSlidePrompt(slide, model) {
  const raw      = String(slide.prompt || '');
  const stripped = raw.trim();
  const id       = slide.slideId;

  // Universal-safe floor — applies to EVERY caller regardless of skill.
  if (stripped.includes(DEAD_ENDPOINT_FRAGMENT)) {
    throw new Error(`slide ${id}: dead endpoint fragment '${DEAD_ENDPOINT_FRAGMENT}' present in prompt body — refusing`);
  }
  if (!stripped) {
    throw new Error(`slide ${id}: empty / whitespace-only prompt — nothing to render; refusing to submit to the paid API`);
  }

  if (!_presentationsGateEnabled()) {
    return raw;  // shared callers: universal-safe only, behavior unchanged
  }

  // ── PRESENTATIONS gate (opt-in) ──
  const len = stripped.length;
  if (len < PROMPT_CHAR_FLOOR) {
    throw new Error(`slide ${id}: prompt is ${len} chars, UNDER the ${PROMPT_CHAR_FLOOR}-char floor (AF-P1) — a thin/garbled prompt is NOT submitted to the paid kie.ai API. Re-author the rich prompt.`);
  }
  if (len > PROMPT_CHAR_CEILING) {
    throw new Error(`slide ${id}: prompt is ${len} chars, OVER the ${PROMPT_CHAR_CEILING}-char ceiling (AF-P2) — tighten redundant phrasing (never delete the negative block or spelling-lock).`);
  }
  // Mode consistency: reference images present => model MUST be image-to-image, or the
  // references are ignored and the model invents its own logo/portrait.
  if (slide.inputImages?.length && model !== GATE_MODEL_I2I) {
    throw new Error(`slide ${id}: inputImages present but model is '${model}'; a reference-bearing render MUST use '${GATE_MODEL_I2I}' (image-to-image).`);
  }
  // A logo-bearing slide with no reference image invents a NEW mark each render.
  if (slide.logoBearing && !(slide.inputImages?.length)) {
    throw new Error(`slide ${id}: logo-bearing slide with empty inputImages — a text-to-image call invents a NEW mark each render (logo-mutation defect). Pass the real logo via inputImages and use '${GATE_MODEL_I2I}'.`);
  }
  // Make the English/Latin anti-garble pin REAL: append it if the author omitted it.
  if (_normWs(raw).includes(_normWs(ENGLISH_PIN))) return raw;
  return raw.replace(/\s+$/, '') + '\n\n' + ENGLISH_PIN;
}


class KieSlideSubmitter {
  /**
   * @param {object} opts
   * @param {string} opts.clientSlug       -- client identifier (no spaces/special chars)
   * @param {string} opts.kieApiKey        -- Kie API key (Bearer token)
   * @param {string} opts.kvWorkerUrl      -- Worker base URL
   * @param {string} opts.workspaceDir     -- path to workspace directory
   * @param {string} [opts.callbackHmacKey] -- this client's PER-CLIENT derived callback key
   *                                          (fix F): HMAC-SHA256(clientSlug, fleet master).
   *                                          The Worker re-derives the same value from its
   *                                          master + the c= slug. Required for callback mode
   *                                          only (large decks); omit for small decks (fix 33).
   * @param {string} [opts.kvReadToken]     -- this client's PER-CLIENT derived /kv-read bearer
   *                                          token (fix F). Required for callback mode only.
   */
  constructor(opts) {
    this.clientSlug      = opts.clientSlug;
    this.kieApiKey       = opts.kieApiKey;
    this.kvWorkerUrl     = opts.kvWorkerUrl || CALLBACK_WORKER_URL;
    this.workspaceDir    = opts.workspaceDir;
    // Fix 33: the per-client callback key + /kv-read token are ONLY needed on the
    // callback (large-deck) path. They are validated lazily in submitDeck() once the
    // deck size decides useCallbacks -- a small deck needs neither Worker secret.
    this.callbackHmacKey = opts.callbackHmacKey || '';
    this.kvReadToken     = opts.kvReadToken || '';

    this.registryDir  = path.join(this.workspaceDir, '.kie', 'registry');
    this.indexDir     = path.join(this.workspaceDir, '.kie', 'index');
    this.doneDir      = path.join(this.workspaceDir, '.kie', 'done');
    fs.mkdirSync(this.registryDir, { recursive: true });
    fs.mkdirSync(this.indexDir,    { recursive: true });
    fs.mkdirSync(this.doneDir,     { recursive: true });

    // Poller is created lazily in submitDeck() with callbacksEnabled set from deck size.
    this.poller = null;

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

    // Fix 33: only the callback (large-deck) path needs the Worker secrets. Validate
    // them here, after the deck size decides useCallbacks, instead of in the constructor.
    if (useCallbacks) {
      if (!this.callbackHmacKey) {
        throw new Error('[kie-submit] callbackHmacKey is required for callback mode (KIE_CALLBACK_HMAC_KEY)');
      }
      if (!this.kvReadToken) {
        throw new Error('[kie-submit] kvReadToken is required for callback mode (KVREAD_TOKEN)');
      }
    }

    // Build the poller lazily with the right mode. When callbacks are disabled the poller
    // skips the KV phase entirely and polls Kie recordInfo directly (fix 33) -- no secret.
    this.poller = new KieKvPoller({
      clientSlug:       this.clientSlug,
      kvWorkerUrl:      this.kvWorkerUrl,
      workspaceDir:     this.workspaceDir,
      kvReadToken:      this.kvReadToken,   // Fix B/F: per-client bearer token (callback path only)
      callbacksEnabled: useCallbacks        // Fix 33: false => direct Kie recordInfo poll
    });

    // --- Phase 1: Resume-safe registry load; skip already-submitted slides ---
    // Fix A: submitId is now a 128-bit random hex. Registry files are keyed by that random ID.
    // To resume, scan the registry directory for a file whose deckId+slideId label matches.
    const registryByLabel = this._loadRegistryByLabel();

    const pending   = [];
    const submitted = []; // slides with existing taskId (crash-resume)

    for (const slide of slides) {
      const label    = `${slide.deckId}_${slide.slideId}`; // human-readable label, NOT the KV key
      const existing = registryByLabel[label] || null;

      if (existing?.taskId) {
        const submitId = existing.submitId;
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
        // New slide: generate a 128-bit random submitId (fix A)
        const submitId = crypto.randomBytes(16).toString('hex');
        pending.push({ ...slide, submitId, taskId: null, existing: false });
      }
    }

    console.log(`[kie-submit] resume: ${submitted.length} already done, ${pending.length} to process`);

    // --- Phase 2: Submit new tasks (rate-limited, 20 per 10s) ---
    const toWait = [...pending.filter(s => s.existing)]; // already submitted, not done

    for (const slide of pending.filter(s => !s.existing)) {
      await this._throttle();

      const model    = slide.model || opts.model || 'gpt-image-2-text-to-image';
      const submitId = slide.submitId; // already a 128-bit random hex (fix A)

      // Fix 33: the per-task secret + callback URL only exist on the callback path.
      // A small deck (useCallbacks=false) never sends a callBackUrl, so it needs neither.
      let perTaskSecret = null;
      let callBackUrl   = null;
      if (useCallbacks) {
        perTaskSecret = crypto.randomBytes(32).toString('hex');
        // Fix D: callback validator = HMAC-SHA256(clientSlug + ":" + submitId, callbackHmacKey)
        //   Nothing secret in the URL; the Worker recomputes and verifies.
        // Fix C: perTaskSecretHmac = HMAC-SHA256(perTaskSecret, callbackHmacKey)
        //   A hash of the secret, safe to pass through Kie logs. Stored in KV by Worker.
        // NOTE (fix F): this.callbackHmacKey is the PER-CLIENT derived key (not the fleet
        //   master); the Worker re-derives the same value from the master + slug.
        const callbackValidator = crypto
          .createHmac('sha256', this.callbackHmacKey)
          .update(`${this.clientSlug}:${submitId}`)
          .digest('hex');
        const perTaskSecretHmac = crypto
          .createHmac('sha256', this.callbackHmacKey)
          .update(perTaskSecret)
          .digest('hex');
        // Fix C + D: no raw secret in URL; s= is the callback validator, h= is the secret HMAC
        callBackUrl = `${this.kvWorkerUrl}/cb?c=${encodeURIComponent(this.clientSlug)}` +
          `&j=${encodeURIComponent(submitId)}&s=${callbackValidator}&h=${perTaskSecretHmac}`;
      }

      // Write registry BEFORE submitting (crash-safe: write first, then submit).
      // Store deckId + slideId as human-readable label fields alongside the random submitId.
      const regRow = {
        submitId,                              // Fix A: 128-bit random hex, not deckId_slideId
        label:        `${slide.deckId}_${slide.slideId}`, // human-readable label for resume scan
        clientSlug:   this.clientSlug,
        deckId:       slide.deckId,
        slideId:      slide.slideId,
        model,
        targetPath:   slide.targetPath,
        perTaskSecret,                         // stays on box in local registry only (null for small decks)
        callBackUrl,                           // null when callbacks are disabled (fix 33)
        submittedAt:  new Date().toISOString(),
        status:       'submitting',
        taskId:       null,
        fallbackPolledAt: null
      };
      this._writeRegistry(submitId, regRow);

      try {
        // SHARED-GATE PARITY: enforce the 9,000–18,000-char floor + model/reference
        // mode-consistency and append the mandatory English/Latin pin BEFORE the paid
        // createTask. A violation throws here and the slide is marked failed (never
        // submitted ungated). See gateSlidePrompt / prompt_gate.py.
        const gatedPrompt = gateSlidePrompt(slide, model);
        const body = {
          model,
          input: {
            prompt:       gatedPrompt,
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

      // Download image if done and has URLs
      let localPath = slide.targetPath;
      let status    = done.status;
      if (done.status === 'done' && done.resultUrls?.length && slide.targetPath) {
        localPath = await this._downloadFirst(done.resultUrls, slide.targetPath);
      }

      // Fix 35: 'done' means a real file on disk. A status of 'done' with no downloadable
      // file (download failed, or a 200 that yielded zero allowlisted URLs) is a failure --
      // never report a slide complete when there is nothing rendered on disk.
      if (status === 'done' && !(localPath && fs.existsSync(localPath))) {
        console.warn(`[kie-submit] slide ${slide.slideId}: status 'done' but no file on disk -- marking failed`);
        status = 'failed';
      }

      // Update registry with the reconciled final status
      const reg = this._readRegistry(slide.submitId) || {};
      reg.status = status;
      reg.fallbackPolledAt = done.fallbackPolledAt || reg.fallbackPolledAt;
      this._writeRegistry(slide.submitId, reg);

      return { slideId: slide.slideId, submitId: slide.submitId, taskId: slide.taskId,
               status, resultUrls: done.resultUrls, localPath, code: done.code };
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

  /**
   * Scan the registry directory and build an index keyed by human-readable label
   * (deckId_slideId). Used for crash-safe resume now that submitId is random (fix A).
   * Returns: { [label]: registryRow, ... }
   *
   * Fix 37(i): a crash BETWEEN the createTask POST and its response can leave two rows
   * for one label -- an orphan with taskId=null (looks un-submitted) and, if Kie did
   * accept it, a paid task with no local taskId. Choosing the orphan would RE-SUBMIT and
   * pay twice. So per label we pick the winner deterministically: prefer the row that
   * already has a taskId; among ties (or all-null) prefer the newest submittedAt. Every
   * other row for that label is marked status 'superseded' on disk so it is never
   * re-submitted and the double-charge is contained.
   */
  _loadRegistryByLabel() {
    const groups = {}; // label -> [{ row, file }]
    let files;
    try {
      files = fs.readdirSync(this.registryDir);
    } catch (_) {
      return {};
    }
    for (const f of files) {
      if (!f.endsWith('.json')) continue;
      try {
        const row = JSON.parse(fs.readFileSync(path.join(this.registryDir, f), 'utf8'));
        // Support both new-style (row.label) and legacy (deckId_slideId filename-based) rows
        const label = row.label || (row.deckId && row.slideId ? `${row.deckId}_${row.slideId}` : null);
        if (!label) continue;
        (groups[label] ||= []).push({ row, file: f });
      } catch (_) {
        // Corrupt or partial file; skip
      }
    }

    const result = {};
    for (const [label, entries] of Object.entries(groups)) {
      // Deterministic winner: taskId present beats taskId absent; then newest submittedAt.
      const ranked = entries.slice().sort((a, b) => {
        const at = a.row.taskId ? 1 : 0;
        const bt = b.row.taskId ? 1 : 0;
        if (at !== bt) return bt - at;                       // taskId-present first
        const as = Date.parse(a.row.submittedAt || '') || 0;
        const bs = Date.parse(b.row.submittedAt || '') || 0;
        return bs - as;                                      // newest submittedAt first
      });
      const winner = ranked[0];
      result[label] = winner.row;

      // Mark every non-winning duplicate as superseded so it is never re-submitted (fix 37i).
      for (const loser of ranked.slice(1)) {
        if (loser.row.status === 'superseded') continue;
        loser.row.status = 'superseded';
        loser.row.supersededBy = winner.row.submitId || null;
        try {
          fs.writeFileSync(path.join(this.registryDir, loser.file),
            JSON.stringify(loser.row, null, 2));
          console.warn(`[kie-submit] resume: superseded duplicate registry row ${loser.file} for label ${label}`);
        } catch (_) { /* best-effort; skip on write failure */ }
      }
    }
    return result;
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
