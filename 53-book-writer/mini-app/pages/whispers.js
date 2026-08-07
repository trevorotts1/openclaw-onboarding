/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U08 — PER-FIELD "WHY WE ASK" WHISPERS
 * + CELEBRATION COPY
 * -----------------------------------------------------------------------------
 * A map of field_id -> gentle "why we ask" line for EVERY intake and gate
 * field, plus the celebration copy shown after a non-empty answer and the two
 * locked anti-anxiety chrome lines that sit on every question screen.
 *
 * MASTER-PLAN section 5 (locked anti-anxiety copy script):
 *   - every question carries a "why we ask" whisper
 *   - every question ends with permission: "There are no wrong answers."
 *   - after a non-empty answer the button becomes the celebration variant:
 *     "Beautiful — next."
 *   - EVERY screen carries "Save & come back later — your answers are safe."
 *
 * Copy is provider-neutral (no AI-vendor ids anywhere), carries no real
 * zone/account ids, avoids the banned anti-anxiety overwhelm words enforced
 * statically by the U08 sibling lint (mini-app/scripts/lint-banned-strings.js),
 * and contains no {{...}} template placeholders.
 *
 * FIELD ID SET (authority: intake/intake-schema.json + BOOK-WRITER-MANIFEST
 * gates_order). Whispers cover every intake/gate field:
 *   intake: version mode first_name last_name email ideal_avatar niche
 *           primary_goal tone_style_1..4 book_about book_stories
 *           cover_description cover_reference_image avatar_dossier tone_doc
 *   gates:  gate1_title gate1_subtitle gate2_outline
 *           gate3_revision_approval gate4_revision_approval
 *           gate433_avatar_dossier gate433_tone_doc
 *
 * Run a pure-logic self-test:   node whispers.js --selftest
 * Syntax check:                 node -c whispers.js
 * ============================================================================= */
'use strict';

(function (global) {
  // ---------------------------------------------------------------------------
  // Per-field "why we ask" whispers (every intake + gate field, one line each)
  // ---------------------------------------------------------------------------
  var FIELD = {
    // P0-INTAKE — version + mode selectors (no default, per AF-BK-VERSION)
    version: 'This just points us to the right set of helpers — books and brands take different roads.',
    mode: 'Your call — a full book or a faster 4x3x3 offer book. Either way, we shape it around you.',

    // P0-INTAKE — identity
    first_name: 'So your book can carry your name, the way it deserves to.',
    last_name: 'Together with your first name, this makes every page of your book read as unmistakably yours.',
    email: 'Only for sending a copy of your draft when it is ready. No lists, no noise.',

    // P0-INTAKE — shared_required
    ideal_avatar: 'Knowing exactly who you are writing for is how your book finds its people.',
    niche: 'A gentle map of the neighborhood your book lives in — it keeps every word pointed at your reader.',
    primary_goal: 'The change your reader is really hoping for becomes the heart of your book.',
    tone_style_1: 'A writer you admire gives us a warm north star for how your book should sound.',
    tone_style_2: 'A second voice we can weave in, so your book sounds like you, never like a copy of anyone else.',

    // P0-INTAKE — tone_style_optional
    tone_style_3: 'Optional, of course — a little more color if you would like it.',
    tone_style_4: 'Only if it feels right. Every line here is your choice, never a box to fill.',

    // P0-INTAKE — book_required
    book_about: 'The idea that has been living in you — we help it grow into a book.',
    book_stories: 'The true stories and moments only you can tell — they are what make this book unmistakably yours.',
    cover_description: 'A hint of what you picture on the front — it steers the cover beautifully.',

    // P0-INTAKE — book_optional
    cover_reference_image: 'If a cover you have seen feels like yours, show it to us — the fastest way to get the look right.',

    // P0-INTAKE — four33_required (mode 4x3x3 only)
    avatar_dossier: 'An existing profile of your reader, if you have one — it saves a step and keeps everything consistent.',
    tone_doc: 'Any notes you already keep on how the book should sound — we honor them.',

    // GATE-1-title (locked title + subtitle, byte-exact downstream)
    gate1_title: 'This is the title your book keeps for life — we just want it to feel right to you.',
    gate1_subtitle: 'The quiet second line that makes your title land even harder.',

    // GATE-2-outline
    gate2_outline: 'A quick look to make sure the shape feels like your book — then we write.',

    // GATE-3-approval + GATE-4-approval-r2 (revision rounds)
    gate3_revision_approval: 'Your say on this revision — we want it exactly as you want it.',
    gate4_revision_approval: 'One more gentle chance to make it perfect in your eyes.',

    // GATE-433 (4x3x3 offer-book handoff — collects dossier + tone only)
    gate433_avatar_dossier: 'The reader profile guiding this offer book — the same warm intent as before.',
    gate433_tone_doc: 'The sound of this book — reuse your notes or start fresh, your call.'
  };

  // ---------------------------------------------------------------------------
  // Celebration copy (shown after a non-empty answer)
  // ---------------------------------------------------------------------------
  var CELEBRATION = {
    // Locked celebration button variant (MASTER-PLAN section 5)
    button: 'Beautiful — next.',
    // Gentle, non-robotic confirmations shown after each answer; selected
    // deterministically by answer count so the flow never feels repetitive
    // and is fully testable (no randomness).
    lines: [
      'Beautiful — that\'s safely tucked in.',
      'Lovely — thank you.',
      'That helps us shape it around you.',
      'Wonderful — on we go.',
      'Got it — that\'s a lovely detail.',
      'Perfect — one more small step.'
    ]
  };

  // ---------------------------------------------------------------------------
  // Locked per-question chrome (every screen)
  // ---------------------------------------------------------------------------
  var PERMISSION = 'There are no wrong answers.';
  var SAVE_LINE = 'Save & come back later — your answers are safe.';

  // The authoritative field id set this unit must cover (self-test proves it).
  var KNOWN_FIELDS = [
    'version', 'mode',
    'first_name', 'last_name', 'email',
    'ideal_avatar', 'niche', 'primary_goal',
    'tone_style_1', 'tone_style_2', 'tone_style_3', 'tone_style_4',
    'book_about', 'book_stories', 'cover_description', 'cover_reference_image',
    'avatar_dossier', 'tone_doc',
    'gate1_title', 'gate1_subtitle', 'gate2_outline',
    'gate3_revision_approval', 'gate4_revision_approval',
    'gate433_avatar_dossier', 'gate433_tone_doc'
  ];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function fieldFor(id) {
    return Object.prototype.hasOwnProperty.call(FIELD, id) ? FIELD[id] : '';
  }

  function hasField(id) {
    return Object.prototype.hasOwnProperty.call(FIELD, id) && typeof FIELD[id] === 'string' && FIELD[id].length > 0;
  }

  // Deterministic celebration for a given answer count.
  function celebrationFor(fieldId, answeredCount) {
    var n = typeof answeredCount === 'number' && answeredCount > 0 ? answeredCount : 0;
    return {
      button: CELEBRATION.button,
      line: CELEBRATION.lines[n % CELEBRATION.lines.length]
    };
  }

  // ---------------------------------------------------------------------------
  // Pure-logic self-test (runs under node, no DOM)
  // ---------------------------------------------------------------------------
  function selftest() {
    var results = [];
    var T = function (name, ok) { results.push([name, !!ok]); };

    T('every known intake/gate field has a whisper', KNOWN_FIELDS.every(hasField));
    T('field map contains no empty strings', Object.keys(FIELD).every(hasField));
    T('celebration button is the locked variant', CELEBRATION.button === 'Beautiful — next.');
    T('celebration lines are all non-empty', CELEBRATION.lines.every(function (l) { return l.length > 0; }));
    T('celebrationFor is deterministic', celebrationFor('book_about', 2).line === celebrationFor('book_about', 2).line);
    T('celebrationFor wraps by count', celebrationFor('x', 0).line === CELEBRATION.lines[0] &&
                                          celebrationFor('x', 6).line === CELEBRATION.lines[0]);
    T('permission line present', PERMISSION === 'There are no wrong answers.');
    T('save line present on every screen', SAVE_LINE === 'Save & come back later — your answers are safe.');

    // Banned-word cleanliness of the copy itself (the lint enforces the same
    // list statically over the shipped file; this guards the module's data).
    var BANNED = ['submit', 'required', 'error', 'deadline', 'you must'];
    var allCopy = Object.keys(FIELD).map(fieldFor)
      .concat(CELEBRATION.lines).concat([CELEBRATION.button, PERMISSION, SAVE_LINE]);
    T('no banned overwhelm word anywhere in the copy', allCopy.every(function (s) {
      var lower = s.toLowerCase();
      return BANNED.every(function (w) { return lower.indexOf(w) === -1; });
    }));

    var pass = results.every(function (r) { return r[1]; });
    var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      lines.forEach(function (l) { process.stdout.write(l + '\n'); });
      process.stdout.write((pass ? 'U08 whispers self-test: PASS' : 'U08 whispers self-test: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  var BWWhispers = {
    field: FIELD,
    celebration: CELEBRATION,
    permission: PERMISSION,
    save: SAVE_LINE,
    knownFields: KNOWN_FIELDS.slice(),
    fieldFor: fieldFor,
    hasField: hasField,
    celebrationFor: celebrationFor,
    selftest: selftest
  };

  global.BWWhispers = BWWhispers;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { BWWhispers: BWWhispers };
  }

  if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
