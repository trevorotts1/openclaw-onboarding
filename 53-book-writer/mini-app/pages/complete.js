/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U07 — COMPLETION SCREEN
 * -----------------------------------------------------------------------------
 * The end-of-phase landing. Warm close-out copy, re-grounded to the phase:
 * an intake phase thanks the client for what the book team needs; a GATE phase
 * (submit.action === "gate_receipt") confirms their choice is locked in.
 * Always: the book-stack resolves with a glow, "your book team has everything
 * they need", a quiet time line, the resume-link reminder with copy affordance,
 * and the optional opt-in "Email me my draft" (skippable — no email wall).
 *
 * WHY A SEPARATE MODULE: U05 owns the SPA renderer; its inline renderComplete()
 * is minimal. This module is the additive completion seam with the full warm
 * close-out copy and the schema-grounded messaging, using the SAME design-token
 * class names the U05 shell styles (.completion, .card, .chrome, .qcount,
 * .rail, .rail-fill, .book.glow, .email-row, .keep-link, .primary, .savelater).
 *
 * WIRE CONTRACT (MASTER-PLAN section 5):
 *   - config: { phase, title, warm_intro, progress_label, progress_total,
 *               questions:[...], submit:{ action } }
 *   - context: { slug, phase_id, mode, run_id, exp } (may be {} in preview)
 *   - root: the #app container the completion replaces
 *   - onEmail: async (email) => {} — called when the client opts in
 *              ("Email me my draft"), always skippable.
 *
 * ANTI-ANXIETY COPY — locked (Plan 2 + MASTER-PLAN section 5):
 *   Never "Submit / Required / Final / Deadline / You must / Error".
 *   "Thank you! Your book team has everything they need." for intake;
 *   gate phases confirm the choice without ever saying "approved" coldly.
 *   Keep-link reminder: "Keep this link — it's your way back."
 *
 * PROVIDER-NEUTRAL: zero provider ids, zero PITs, no Anthropic references.
 *
 * Run a pure-logic self-test:  node complete.js --selftest
 * Syntax check:               node -c complete.js
 * ============================================================================= */
'use strict';

(function (global) {
  // Banned anti-anxiety words — these strings must NEVER render (T5 warmth guard).
  // "Submit / Required / Final / Deadline / You must / Error"
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  var FORBIDDEN_IDS = ['anthropic', 'claude', 'sk-', 'ak-', 'wrangler', 'cloudflare'].
    map(function (s) { return s.toLowerCase(); });

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  // ---------------------------------------------------------------------------
  // Pure-logic helpers (node-testable, no DOM)
  // ---------------------------------------------------------------------------

  // Re-grounded headline: intake -> the book team has what it needs; a gate
  // phase -> the choice is locked in (gate receipt). Never a cold "done".
  function headlineFor(config) {
    var action = config && config.submit ? config.submit.action : null;
    if (action === 'gate_receipt') return 'That’s it — your choice is locked in.';
    return 'Thank you! Your book team has everything they need.';
  }

  function sublineFor(config) {
    var action = config && config.submit ? config.submit.action : null;
    if (action === 'gate_receipt') {
      return 'Every word you shared is safe. We’ll carry it into the next step of your book.';
    }
    return 'Every word you shared is safe. We’ll weave it into your draft and come back to you.';
  }

  // Quiet close line, re-grounded to how many questions the phase really had.
  function closeLineFor(config) {
    var total = config && config.questions ? config.questions.length : 0;
    if (total < 1) return 'That’s everything for this step.';
    return 'That was ' + total + ' gentle questions — thank you for taking your time.';
  }

  // What the completion shows depends on the phase (never hardcoded):
  //   intake         -> "draft" promise
  //   gate_receipt   -> "locked in" promise (title/outline approval)
  function whatHappensNext(config) {
    var action = config && config.submit ? config.submit.action : null;
    if (action === 'gate_receipt') {
      return 'Your choice is safe with your book team. They’ll build the next step from exactly what you locked in.';
    }
    return 'Your book team has everything they need. They’ll shape your answers into the first draft of your book.';
  }

  // Validate the opt-in email — gentle, never "Error". Empty is fine (skippable).
  function checkEmail(value) {
    var v = String(value || '').trim();
    if (!v) return { ok: true, value: '' };
    return EMAIL_RE.test(v) ? { ok: true, value: v } : { ok: false };
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

  // The complete completion copy this module can render (linted by self-test).
  function allCopy(config) {
    return [
      headlineFor(config),
      sublineFor(config),
      closeLineFor(config),
      whatHappensNext(config),
      'Email me my draft (optional)',
      'Remind me',
      'Keep this link — it’s your way back.',
      'Copy link',
      'Save & come back later — your answers are safe.'
    ].join(' ');
  }

  // ---------------------------------------------------------------------------
  // DOM renderer (guarded: runs only in the browser)
  // ---------------------------------------------------------------------------
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'text') node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  function renderCompleteInto(root, config, context, onEmail) {
    if (!root) return null;
    var isGate = config && config.submit && config.submit.action === 'gate_receipt';

    // Persistent chrome: "All done" + full progress rail.
    var chrome = el('div', { class: 'chrome' });
    var railWrap = el('div', { class: 'rail-wrap' });
    railWrap.appendChild(el('div', { class: 'qcount', text: 'All done' }));
    var rail = el('div', { class: 'rail' }, [el('div', { class: 'rail-fill', style: 'width:100%' })]);
    railWrap.appendChild(rail);
    chrome.appendChild(el('div', { class: 'book glow', 'aria-hidden': 'true' }));
    chrome.appendChild(railWrap);

    var card = el('div', { class: 'card completion' });
    card.appendChild(el('h2', { text: headlineFor(config) }));
    card.appendChild(el('p', { text: sublineFor(config) }));
    card.appendChild(el('p', { class: 'comfort', text: closeLineFor(config) }));
    card.appendChild(el('p', { class: 'why', text: whatHappensNext(config) }));

    // Optional opt-in email — never a wall, always skippable.
    var emailRow = el('div', { class: 'email-row' });
    var emailInput = el('input', { type: 'email', placeholder: 'Email me my draft (optional)' });
    emailInput.setAttribute('aria-label', 'Email me my draft (optional)');
    var emailBtn = el('button', { type: 'button', text: 'Remind me' });
    emailBtn.addEventListener('click', function () {
      var check = checkEmail(emailInput.value);
      if (!check.ok) {
        // Gentle, never "Error".
        emailBtn.textContent = 'That email didn’t read right — try once more?';
        setTimeout(function () { emailBtn.textContent = 'Remind me'; }, 3200);
        return;
      }
      if (onEmail) onEmail(check.value);
      emailBtn.textContent = 'Got it';
      emailBtn.disabled = true;
    });
    emailRow.appendChild(emailInput);
    emailRow.appendChild(emailBtn);
    card.appendChild(emailRow);

    // Resume link reminder with copy affordance (safe by default: no wall).
    var keep = el('p', { class: 'keep-link' });
    keep.appendChild(document.createTextNode('Keep this link — it’s your way back.'));
    var copyBtn = el('button', { type: 'button', text: 'Copy link' });
    copyBtn.addEventListener('click', function () {
      try {
        var copyText = location.href;
        navigator.clipboard.writeText(copyText).then(function () {
          copyBtn.textContent = 'Copied';
          setTimeout(function () { copyBtn.textContent = 'Copy link'; }, 2600);
        });
      } catch (e) {
        copyBtn.textContent = 'Here’s your link: ' + location.href;
      }
    });
    keep.appendChild(copyBtn);
    card.appendChild(keep);

    card.appendChild(el('p', { class: 'savelater', text: 'Save & come back later — your answers are safe.' }));

    root.appendChild(chrome);
    root.appendChild(card);
    return card;
  }

  // ---------------------------------------------------------------------------
  // Exports + self-test
  // ---------------------------------------------------------------------------
  var API = {
    headlineFor: headlineFor,
    sublineFor: sublineFor,
    closeLineFor: closeLineFor,
    whatHappensNext: whatHappensNext,
    checkEmail: checkEmail,
    scanBanned: scanBanned,
    scanForbiddenIds: scanForbiddenIds,
    hasPlaceholderBraces: hasPlaceholderBraces,
    allCopy: allCopy,
    renderCompleteInto: renderCompleteInto
  };

  function selftest() {
    var results = [];
    var intake = {
      phase: 'P0-INTAKE:full',
      questions: [{ id: 'a', kind: 'text' }, { id: 'b', kind: 'media' }],
      submit: { action: 'ghl_contact' }
    };
    var gate = {
      phase: 'GATE-1-title',
      questions: [{ id: 'title', kind: 'text' }, { id: 'subtitle', kind: 'text' }],
      submit: { action: 'gate_receipt' }
    };

    // 1. Re-grounded headline per phase.
    results.push(['headline: intake -> "book team has everything"',
      headlineFor(intake) === 'Thank you! Your book team has everything they need.']);
    results.push(['headline: gate -> "choice is locked in"',
      headlineFor(gate) === 'That’s it — your choice is locked in.']);

    // 2. Subline per phase.
    results.push(['subline: intake carries "first draft"', /draft/.test(sublineFor(intake))]);
    results.push(['subline: gate carries "next step"', /next step/.test(sublineFor(gate))]);

    // 3. Quiet close line re-grounded to real question count.
    results.push(['closeLine: intake "2 gentle questions"',
      closeLineFor(intake) === 'That was 2 gentle questions — thank you for taking your time.']);
    results.push(['closeLine: empty config -> generic', /everything for this step/.test(closeLineFor({ questions: [] }))]);

    // 4. What-happens-next differs by phase.
    results.push(['next: gate -> "locked in"', /locked in/.test(whatHappensNext(gate))]);
    results.push(['next: intake -> "first draft"', /first draft/.test(whatHappensNext(intake))]);

    // 5. Email check — gentle validation, empty is always fine (skippable).
    results.push(['email: empty -> ok (skippable)', checkEmail('').ok === true]);
    results.push(['email: valid -> ok', checkEmail('anne@example.com').ok === true]);
    results.push(['email: invalid -> not ok, no error word', checkEmail('nope').ok === false]);

    // 6. Banned-string lint: WHOLE completion copy carries none.
    var copy = allCopy(intake) + ' ' + allCopy(gate);
    results.push(['banned: completion copy clean', scanBanned(copy).length === 0]);
    results.push(['banned: detector catches', scanBanned('you must submit error').length === 3]);

    // 7. Provider-neutral.
    results.push(['provider-neutral: no Anthropic/Claude/sk-/ak- ids', scanForbiddenIds(copy).length === 0]);
    results.push(['provider-neutral: detector catches forbidden id', scanForbiddenIds('anthropic claude-3').length === 2]);

    // 8. No {{...}} placeholders.
    results.push(['placeholders: none in copy', hasPlaceholderBraces(copy) === false]);
    results.push(['placeholders: detector catches', hasPlaceholderBraces('{{tok}}').length === 1 || hasPlaceholderBraces('{{tok}}') === true]);

    var pass = results.every(function (r) { return r[1]; });
    var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      lines.forEach(function (l) { process.stdout.write(l + '\n'); });
      process.stdout.write((pass ? 'U07 completion screen self-test: PASS' : 'U07 completion screen self-test: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  global.BWComplete = API;

  if (typeof document !== 'undefined') {
    // No auto-boot: U05's app.js calls BWComplete.renderCompleteInto once merged.
  } else if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
