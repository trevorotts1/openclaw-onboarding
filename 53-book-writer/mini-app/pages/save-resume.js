/* ============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U11 — SAVE & RESUME
 * ----------------------------------------------------------------------------
 * Turns "Save & come back later — your answers are safe." into a real promise.
 *
 * Three pieces, matching the master plan (section 5):
 *
 *  1. DEBOUNCED PERSIST — every answer is written to the Worker on entry,
 *     debounced ~800ms. A dedicated POST /api/save (worker/src/save.js, U11)
 *     stages the draft idempotently under the SAME per-step consumed counter
 *     as U03's /api/answers, so a replayed save can never duplicate and a
 *     legit resume edit overwrites in place.
 *
 *  2. RESUME AT THE NEXT UNANSWERED QUESTION — on reopen, GET /api/save/resume
 *     returns the staged answers + a hint; the renderer jumps to the first
 *     question with no non-empty answer.
 *
 *  3. EMAIL OPT-IN FOR A RESUME REMINDER — only at completion, opt-in and
 *     skippable ("Email me my draft"). The default path is always
 *     "Keep this link — it's your way back" with a copy affordance. No signup
 *     wall, no email until the end.
 *
 * This module is a pure-ish logic layer: it holds no DOM, no fetch by itself
 * (callers pass an `http` adapter), so every rule is testable offline with
 * `node save-resume.js --selftest`. Syntax check: `node -c save-resume.js`.
 *
 * No Anthropic ids. No banned strings. No real zone/account ids.
 * ========================================================================== */
'use strict';

(function (global) {
  // -------------------------------------------------------------------------
  // Constants
  // -------------------------------------------------------------------------
  var DEBOUNCE_MS = 800;                       // debounced persist on entry
  var TOKEN_RE = /^[0-9a-f]{32}$/;
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  // Banned anti-anxiety words — must NEVER render (T5 warmth guard).
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  // Warm completion copy (re-grounded; no banned strings).
  var COPY = {
    keepLink: 'Keep this link — it’s your way back.',
    copyButton: 'Copy link',
    copied: 'Link copied — keep it somewhere safe.',
    emailPlaceholder: 'Email me my draft (optional)',
    emailButton: 'Remind me',
    emailOk: 'Got it — we’ll be in touch when your draft is ready.',
    emailBad: 'That address didn’t look quite right — you can keep the link instead.',
    savedWhisper: 'Saved — your answers are safe.',
    resumeWhisper: 'Welcome back — you’re right where you left off.'
  };

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------
  function isValidToken(token) {
    return typeof token === 'string' && TOKEN_RE.test(token);
  }

  function isValidEmail(email) {
    if (typeof email !== 'string') return false;
    var e = email.trim();
    if (e.length < 3 || e.length > 254) return false;
    if (!EMAIL_RE.test(e)) return false;
    if (/[<>\s]/.test(e)) return false; // no markup / spaces
    return true;
  }

  function safeCopy(s) {
    var out = String(s || '');
    for (var i = 0; i < BANNED_COPY.length; i++) {
      out = out.replace(new RegExp(BANNED_COPY[i], 'gi'), function (m) {
        return m.charAt(0).toUpperCase() + m.slice(1).replace(/[aeiou]/g, '*');
      });
    }
    return out;
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  // -------------------------------------------------------------------------
  // Resume computation (mirrors U05's firstUnansweredIndex, unit-testable)
  // -------------------------------------------------------------------------
  // A question counts as answered ONLY when its answer has non-empty text.
  // A cleared draft (text === '') is NOT answered — resume goes back to it.
  function firstUnansweredIndex(questions, answers) {
    var qs = questions || [];
    for (var i = 0; i < qs.length; i++) {
      var q = qs[i];
      if (!q || !q.id) continue;
      var a = answers && answers[q.id];
      if (!a || typeof a.text !== 'string' || a.text.length === 0) return i;
    }
    return -1;
  }

  function answeredCount(questions, answers) {
    var qs = questions || [];
    var n = 0;
    for (var i = 0; i < qs.length; i++) {
      var q = qs[i];
      if (!q || !q.id) continue;
      var a = answers && answers[q.id];
      if (a && typeof a.text === 'string' && a.text.length > 0) n++;
    }
    return n;
  }

  // -------------------------------------------------------------------------
  // Persist client — debounced write to the Worker
  // -------------------------------------------------------------------------
  // `http` adapter: { post(url, body) -> Promise<Response-ish {status,json()}>,
  //                  get(url) -> Promise<{json()}> }
  // `onResult` receives {ok, idempotent, changed, status} after each flush.
  // `onError` receives a non-ok result (network / 4xx / 5xx).
  function Persister(opts) {
    this.token = opts.token;
    this.http = opts.http;
    this.onResult = opts.onResult || function () {};
    this.onError = opts.onError || function () {};
    this._pending = {};          // qid -> {answer, source}
    this._flush = debounce(this._doFlush.bind(this), DEBOUNCE_MS);
    this._inFlight = false;
  }

  Persister.prototype.save = function (qid, answer, source) {
    if (!qid) return;
    this._pending[qid] = { answer: answer, source: source || 'typed' };
    this._flush();
  };

  Persister.prototype._doFlush = function () {
    var self = this;
    if (this._inFlight) return Promise.resolve(); // coalesce — pending is flushed next tick
    var pending = this._pending;
    this._pending = {};
    var qids = Object.keys(pending);
    if (!qids.length) return Promise.resolve();

    this._inFlight = true;
    var chain = Promise.resolve();
    qids.forEach(function (qid) {
      chain = chain.then(function () {
        return self._sendOne(qid, pending[qid]);
      });
    });
    chain.then(function () {
      self._inFlight = false;
      if (Object.keys(self._pending).length) self._flush();
    }).catch(function () {
      self._inFlight = false;
    });
    return chain;
  };

  Persister.prototype._sendOne = function (qid, entry) {
    var self = this;
    var url = '/api/save?tk=' + encodeURIComponent(this.token);
    return this.http.post(url, { question_id: qid, answer: entry.answer, source: entry.source })
      .then(function (res) {
        return res.json().then(function (body) {
          var ok = res.status >= 200 && res.status < 300 && body && body.ok;
          if (ok) {
            self.onResult({ ok: true, idempotent: !!body.idempotent, changed: !!body.changed, status: res.status, qid: qid });
          } else {
            self.onError({ ok: false, status: res.status, error: (body && body.error) || 'save-refused', qid: qid });
          }
          return ok;
        });
      })
      .catch(function () {
        // Network hiccup — re-queue so the answer is not silently lost; the
        // next keystroke (or the next flush) retries. Answers are never
        // dropped: they also live in localStorage on the client.
        self._pending[qid] = entry;
        self.onError({ ok: false, status: 0, error: 'network', qid: qid });
        return false;
      });
  };

  // -------------------------------------------------------------------------
  // Resume fetch
  // -------------------------------------------------------------------------
  function fetchResume(http, token) {
    return http.get('/api/save/resume?tk=' + encodeURIComponent(token))
      .then(function (res) {
        return res.json().then(function (body) {
          if (!body || body.ok !== true) {
            return { ok: false, answers: {}, error: (body && body.error) || 'resume-refused' };
          }
          return { ok: true, answers: body.answers || {}, hint: body.resume || {} };
        });
      })
      .catch(function () { return { ok: false, answers: {}, error: 'network' }; });
  }

  // Merge worker answers into the local map, keeping local-only values too
  // (token absent in local preview, or answers staged before the link existed).
  function mergeAnswers(local, remote) {
    var out = {};
    if (local && typeof local === 'object') Object.keys(local).forEach(function (k) { out[k] = local[k]; });
    if (remote && typeof remote === 'object') Object.keys(remote).forEach(function (k) { out[k] = remote[k]; });
    return out;
  }

  // -------------------------------------------------------------------------
  // Email opt-in (completion only, skippable)
  // -------------------------------------------------------------------------
  function emailPayload(email) {
    var e = email.trim();
    if (!isValidEmail(e)) return { ok: false, error: 'email-not-valid' };
    return { ok: true, email: e };
  }

  function sendEmailOptIn(http, token, email) {
    var check = emailPayload(email);
    if (!check.ok) return Promise.resolve({ ok: false, error: check.error });
    return http.post('/api/save/reminder?tk=' + encodeURIComponent(token), { email: check.email })
      .then(function (res) {
        return res.json().then(function (body) {
          var ok = res.status >= 200 && res.status < 300 && body && body.ok;
          return { ok: ok, status: res.status, error: ok ? null : (body && body.error) || 'reminder-refused' };
        });
      })
      .catch(function () { return { ok: false, error: 'network' }; });
  }

  // -------------------------------------------------------------------------
  // Warmed-up module surface
  // -------------------------------------------------------------------------
  var SaveResume = {
    DEBOUNCE_MS: DEBOUNCE_MS,
    COPY: COPY,
    isValidToken: isValidToken,
    isValidEmail: isValidEmail,
    safeCopy: safeCopy,
    debounce: debounce,
    firstUnansweredIndex: firstUnansweredIndex,
    answeredCount: answeredCount,
    mergeAnswers: mergeAnswers,
    emailPayload: emailPayload,
    Persister: Persister,
    fetchResume: fetchResume,
    sendEmailOptIn: sendEmailOptIn
  };

  // -------------------------------------------------------------------------
  // Pure-logic self-test (runs under node, no DOM, no fetch)
  // -------------------------------------------------------------------------
  function selftest() {
    var results = [];

    // token / email validation
    results.push(['token: valid accepted', isValidToken('a'.repeat(32)) === true]);
    results.push(['token: non-hex rejected', isValidToken('g'.repeat(32)) === false]);
    results.push(['token: short rejected', isValidToken('short') === false]);
    results.push(['email: valid', isValidEmail('reader@example.com') === true]);
    results.push(['email: junk rejected', isValidEmail('not-an-email') === false]);
    results.push(['email: markup blocked', isValidEmail('<script>@x.com') === false]);

    // resume-at-next-unanswered
    var questions = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    results.push(['resume: none answered -> index 0', firstUnansweredIndex(questions, {}) === 0]);
    results.push(['resume: a answered -> index 1', firstUnansweredIndex(questions, { a: { text: 'hi' } }) === 1]);
    results.push(['resume: cleared draft NOT answered -> index 1', firstUnansweredIndex(questions, { a: { text: 'hi' }, b: { text: '' } }) === 1]);
    results.push(['resume: all answered -> -1', firstUnansweredIndex(questions, { a: { text: '1' }, b: { text: '2' }, c: { text: '3' } }) === -1]);
    results.push(['answeredCount: 2 of 3', answeredCount(questions, { a: { text: '1' }, c: { text: '3' } }) === 2]);

    // merge (local + worker)
    var merged = mergeAnswers({ a: { text: 'local' }, b: { text: 'keep' } }, { b: { text: 'remote-wins' }, c: { text: 'new' } });
    results.push(['merge: remote wins on conflict', merged.b.text === 'remote-wins']);
    results.push(['merge: local-only survives', merged.a.text === 'local']);
    results.push(['merge: remote-only added', merged.c.text === 'new']);

    // email payload
    results.push(['emailPayload: ok', emailPayload(' reader@example.com ').ok === true && emailPayload(' reader@example.com ').email === 'reader@example.com']);
    results.push(['emailPayload: bad rejected', emailPayload('nope').ok === false]);

    // safeCopy (banned-string guard)
    results.push(['safeCopy: softens banned words', /submit/i.test(safeCopy('Submit your answer')) === false]);
    results.push(['safeCopy: no banned words -> unchanged', safeCopy('Keep this link — it’s your way back.') === 'Keep this link — it’s your way back.']);

    // Persister debounce + idempotent flush with a fake http adapter.
    // The debounce is 800ms, so we drive _doFlush directly in the test.
    var calls = [];
    var http = {
      post: function (url, body) {
        calls.push({ url: url, body: body });
        return Promise.resolve({
          status: 201,
          json: function () { return Promise.resolve({ ok: true, changed: true, idempotent: false }); }
        });
      },
      get: function () { return Promise.resolve({ json: function () { return Promise.resolve({ ok: true, answers: {} }); } }); }
    };
    var p = new Persister({ token: 'a'.repeat(32), http: http });
    p.save('a', 'one', 'typed');
    p.save('a', 'one and a half', 'typed');
    p.save('b', 'two', 'typed');
    results.push(['persister: pending coalesced to last edit per qid', Object.keys(p._pending).length === 2 && p._pending.a.answer === 'one and a half']);
    // freeze the debounce timer so it can't double-fire during the test
    p._flush = function () {};

    return p._doFlush().then(function () {
      // a single coalesced flush sent exactly one call per qid
      results.push(['persister: flush coalesced to one call per qid', calls.length === 2]);
      results.push(['persister: sent the final edited value', calls[0] && calls[0].body.answer === 'one and a half']);
      results.push(['persister: sent each qid once', calls[0] && calls[0].body.question_id === 'a' && calls[1] && calls[1].body.question_id === 'b']);

      // error path requeues
      var httpFail = {
        post: function () { return Promise.reject(new Error('net')); },
        get: function () { return Promise.resolve({ json: function () { return Promise.resolve({ ok: true, answers: {} }); } }); }
      };
      var pf = new Persister({ token: 'a'.repeat(32), http: httpFail, onError: function () {} });
      pf._flush = function () {}; // freeze debounce for the test
      return pf._sendOne('q', { answer: 'x', source: 'typed' }).then(function () {
        results.push(['persister: network failure requeues pending', Object.keys(pf._pending).length === 1 && pf._pending.q.answer === 'x']);

        var pass = results.every(function (r) { return r[1]; });
        var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
        if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
          lines.forEach(function (l) { process.stdout.write(l + '\n'); });
          process.stdout.write((pass ? 'U11 save & resume SPA self-test: PASS' : 'U11 save & resume SPA self-test: FAIL') + '\n');
        }
        if (!pass && typeof process !== 'undefined') process.exitCode = 2;
        return pass;
      });
    });
  }

  global.BWSaveResume = SaveResume;

  if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
