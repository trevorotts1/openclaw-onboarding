/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U07 — WELCOME SCREEN
 * -----------------------------------------------------------------------------
 * The link landing. Renders the warm shell BEFORE any question: a promise
 * line, the comfort line, the gentle-question count RE-GROUNDED to the actual
 * schema-driven config (never a hardcoded '8 questions'), a quiet time line,
 * the "answers save as you go" reassurance, and a single CTA.
 *
 * WHY A SEPARATE MODULE (not a rewrite of app.js): U05 owns the one-question-
 * per-screen renderer and its `render()` jumps straight at questions[0]. This
 * module is the additive welcome seam. It renders with the SAME design-token
 * class names the U05 shell styles (.card, .chrome, .qcount, .rail, .rail-fill,
 * .pages, .book.glow, .primary, .savelater), so it drops into the shared SPA
 * with zero CSS changes and NO file collisions at merge time.
 *
 * WIRE CONTRACT (MASTER-PLAN section 5):
 *   - config: { phase, title, warm_intro, progress_label, progress_total,
 *               questions:[...], submit:{action} }
 *   - context: { slug, phase_id, mode, run_id, exp, ... } (from the Worker
 *               binding injected at U02; may be {} in local preview)
 *   - onBegin: called once the client taps the CTA (welcome leaves the stage).
 *
 * ANTI-ANXIETY COPY — locked (Plan 2 + MASTER-PLAN section 5):
 *   Never "Submit / Required / Final / Deadline / You must / Error".
 *   Every screen carries "Save & come back later — your answers are safe."
 *   This landing additionally reassures: "Take your time — your answers save
 *   as you go." and "You can close this link and come back to it."
 *
 * PROVIDER-NEUTRAL: zero provider ids, zero PITs, no Anthropic references.
 * This is a dumb renderer that only ever calls onBegin().
 *
 * Run a pure-logic self-test:  node welcome.js --selftest
 * Syntax check:               node -c welcome.js
 * ============================================================================= */
'use strict';

(function (global) {
  // Banned anti-anxiety words — these strings must NEVER render (T5 warmth guard).
  // "Submit / Required / Final / Deadline / You must / Error"
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  // Hard-coded provider ids / zone ids must NEVER appear (per-client isolation).
  var FORBIDDEN_IDS = ['anthropic', 'claude', 'sk-', 'ak-', 'wrangler', 'cloudflare'].
    map(function (s) { return s.toLowerCase(); });

  // ---------------------------------------------------------------------------
  // Pure-logic helpers (node-testable, no DOM)
  // ---------------------------------------------------------------------------

  // "Question {n} of {total}" progress indicator — derived from config, never
  // hardcoded. Re-grounded to the schema-driven question count.
  function progressLabel(config, answered) {
    var total = config && config.questions ? config.questions.length : 0;
    var n = answered != null ? answered : 0;
    if (total < 1) return '';
    return 'Question ' + n + ' of ' + total;
  }

  // Gentle count line for the comfort copy — matches the REAL schema field
  // count (version + mode + identity + shared_required + book_required +
  // book_optional + four33_required when applicable), never a hardcoded '8'.
  function gentleCountLine(config) {
    var total = config && config.questions ? config.questions.length : 0;
    if (total < 1) return '';
    if (total === 1) return 'Just one gentle question — no pressure, take your time.';
    return 'About ' + total + ' gentle questions — take them one at a time.';
  }

  // Warm intro block, re-grounded to the schema field kinds actually present
  // (text / choice / file-pdf / file-txt / media), so the promise reflects
  // what the phase really collects.
  function warmIntroLines(config) {
    var lines = [];
    var kinds = {};
    var questions = (config && config.questions) || [];
    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      if (!q || !q.kind) continue;
      kinds[q.kind] = (kinds[q.kind] || 0) + 1;
    }
    lines.push('Take your time — your answers save as you go.');
    lines.push('You can close this link and come back to it.');
    if (kinds.media) {
      lines.push('Type, talk, or drop a file — whichever feels easiest.');
    } else if (kinds['file-pdf'] || kinds['file-txt']) {
      lines.push('Type or drop a file — whichever feels easiest.');
    }
    return lines;
  }

  // The comfort line + permission, always.
  function permissionLine() {
    return 'No wrong answers, no pressure. A little here goes a long way.';
  }

  // ---------------------------------------------------------------------------
  // Banned-string + forbidden-id lint (pure, node-testable)
  // ---------------------------------------------------------------------------
  function scanBanned(text) {
    var hits = [];
    var low = String(text || '').toLowerCase();
    for (var i = 0; i < BANNED_COPY.length; i++) {
      if (low.indexOf(BANNED_COPY[i]) !== -1) hits.push(BANNED_COPY[i]);
    }
    return hits;
  }

  function scanForbiddenIds(text) {
    var hits = [];
    var low = String(text || '').toLowerCase();
    for (var i = 0; i < FORBIDDEN_IDS.length; i++) {
      if (low.indexOf(FORBIDDEN_IDS[i]) !== -1) hits.push(FORBIDDEN_IDS[i]);
    }
    return hits;
  }

  function hasPlaceholderBraces(text) {
    return /\{\{[^{}]*\}\}/.test(String(text || ''));
  }

  // The complete welcome copy this module can render (used by the self-test
  // to lint every shipped string once).
  function allCopy(config) {
    var chunks = [
      (config && config.title) || 'Your book is already in you. We just help it out.',
      (config && config.warm_intro) || '',
      'Begin your book',
      'Roughly ' + ((config && config.questions ? config.questions.length : 0) * 3) + ' minutes, at your own pace.',
      permissionLine(),
      'Save & come back later — your answers are safe.'
    ];
    return chunks.concat(warmIntroLines(config)).concat([gentleCountLine(config)]).
      join(' ');
  }

  // ---------------------------------------------------------------------------
  // DOM renderer (guarded: only runs in the browser)
  // ---------------------------------------------------------------------------
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'html') node.innerHTML = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  function renderWelcomeInto(root, config, context, onBegin) {
    if (!root) return null;
    var total = config && config.questions ? config.questions.length : 0;

    // Warm imagery: an open book with a sparkle — the promise, not a form.
    var imagery = el('div', {
      class: 'imagery',
      html: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M32 18c-7-6-18-6-24-4v34c6-2 17-2 24 4 7-6 18-6 24-4v-34c-6-2-17-2-24 4z"/>' +
        '<path d="M32 18v34"/><path d="M24 10l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/></svg>'
    });

    var card = el('div', { class: 'card welcome' });
    card.appendChild(imagery);

    var h1 = el('h1', {
      text: (config && config.title) || 'Your book is already in you. We just help it out.'
    });
    card.appendChild(h1);

    if (config && config.warm_intro) {
      card.appendChild(el('p', { class: 'why', text: config.warm_intro }));
    }

    // Reassurance — answers are safe, resumable, gentle.
    var lines = warmIntroLines(config);
    var promise = el('div', { class: 'welcome-lines' });
    lines.forEach(function (line) {
      promise.appendChild(el('p', { class: 'welcome-line', text: line }));
    });
    card.appendChild(promise);

    if (total > 0) {
      card.appendChild(el('p', { class: 'comfort', text: gentleCountLine(config) }));
      card.appendChild(el('p', { class: 'permission', text: permissionLine() }));
      card.appendChild(el('p', { class: 'quiet', text: 'Roughly ' + (total * 3) + ' minutes, at your own pace.' }));
    }

    var cta = el('button', {
      class: 'primary',
      type: 'button',
      text: 'Begin your book'
    });
    cta.addEventListener('click', function () { if (onBegin) onBegin(); });
    card.appendChild(cta);

    card.appendChild(el('p', { class: 'savelater', text: 'Save & come back later — your answers are safe.' }));

    root.appendChild(card);
    return card;
  }

  // ---------------------------------------------------------------------------
  // Exports + self-test
  // ---------------------------------------------------------------------------
  var API = {
    progressLabel: progressLabel,
    gentleCountLine: gentleCountLine,
    warmIntroLines: warmIntroLines,
    permissionLine: permissionLine,
    scanBanned: scanBanned,
    scanForbiddenIds: scanForbiddenIds,
    hasPlaceholderBraces: hasPlaceholderBraces,
    allCopy: allCopy,
    renderWelcomeInto: renderWelcomeInto
  };

  function selftest() {
    var results = [];
    var intake = {
      title: 'Your book is already in you. We just help it out.',
      warm_intro: 'A few gentle questions — type, talk, or drop a file. No wrong answers, no pressure; you can save and come back anytime.',
      questions: [
        { id: 'version', kind: 'choice' },
        { id: 'mode', kind: 'choice' },
        { id: 'first_name', kind: 'text' },
        { id: 'last_name', kind: 'text' },
        { id: 'email', kind: 'text' },
        { id: 'ideal_avatar', kind: 'textarea' },
        { id: 'niche', kind: 'textarea' },
        { id: 'primary_goal', kind: 'textarea' },
        { id: 'tone_style_1', kind: 'textarea' },
        { id: 'tone_style_2', kind: 'textarea' },
        { id: 'tone_style_3', kind: 'textarea' },
        { id: 'tone_style_4', kind: 'textarea' },
        { id: 'book_about', kind: 'textarea' },
        { id: 'book_stories', kind: 'media' },
        { id: 'cover_description', kind: 'textarea' },
        { id: 'cover_reference_image', kind: 'media' }
      ],
      submit: { action: 'ghl_contact' }
    };

    // 1. Progress indicator — re-grounded to config, not hardcoded.
    results.push(['progressLabel: "Question 1 of 16"', progressLabel(intake, 1) === 'Question 1 of 16']);
    results.push(['progressLabel: total from config (16)', progressLabel(intake, 0) === 'Question 0 of 16']);
    results.push(['progressLabel: empty config -> ""', progressLabel({ questions: [] }, 1) === '']);
    results.push(['progressLabel: missing config -> ""', progressLabel(null, 1) === '']);

    // 2. Gentle count line re-grounded to schema field count (16, never '8').
    results.push(['gentleCountLine: "About 16 gentle questions"', gentleCountLine(intake) === 'About 16 gentle questions — take them one at a time.']);
    results.push(['gentleCountLine: single question -> singular line', gentleCountLine({ questions: [{ id: 'title', kind: 'text' }] }) === 'Just one gentle question — no pressure, take your time.']);
    results.push(['gentleCountLine: empty -> ""', gentleCountLine({ questions: [] }) === '']);

    // 3. Warm intro block.
    var intro = warmIntroLines(intake);
    results.push(['warmIntro: "answers save as you go"', intro.indexOf('Take your time — your answers save as you go.') !== -1]);
    results.push(['warmIntro: "close this link and come back"', intro.indexOf('You can close this link and come back to it.') !== -1]);
    results.push(['warmIntro: media -> type/talk/drop line', warmIntroLines(intake).indexOf('Type, talk, or drop a file — whichever feels easiest.') !== -1]);

    // 4. Comfort + permission.
    results.push(['permissionLine: no pressure', /no pressure/i.test(permissionLine()) && /no wrong answers/i.test(permissionLine())]);

    // 5. Banned-string lint: the WHOLE welcome copy carries none of
    //    Submit / Required / Final / Deadline / You must / Error.
    var copy = allCopy(intake);
    results.push(['banned: welcome copy clean', scanBanned(copy).length === 0]);
    results.push(['banned: each banned word detected when present', scanBanned('you must submit before the final deadline, error required').length === 6]);

    // 6. Provider-neutral: no Anthropic / Claude / sk- / ak- / wrangler ids.
    results.push(['provider-neutral: no Anthropic/Claude/sk-/ak- ids', scanForbiddenIds(copy).length === 0]);
    results.push(['provider-neutral: detector catches a forbidden id', scanForbiddenIds('use the anthropic claude claude-3 model').length === 2]);

    // 7. No {{...}} placeholders in shipped copy.
    results.push(['placeholders: none in copy', hasPlaceholderBraces(copy) === false]);
    results.push(['placeholders: detector catches {{tok}}', hasPlaceholderBraces('link {{tok}}') === true]);

    var pass = results.every(function (r) { return r[1]; });
    var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      lines.forEach(function (l) { process.stdout.write(l + '\n'); });
      process.stdout.write((pass ? 'U07 welcome screen self-test: PASS' : 'U07 welcome screen self-test: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  global.BWWelcome = API;

  if (typeof document !== 'undefined') {
    // No auto-boot: U05's app.js calls BWWelcome.renderWelcomeInto once merged.
  } else if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
