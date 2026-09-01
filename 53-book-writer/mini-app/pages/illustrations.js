/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U06 — INLINE SVG ILLUSTRATION SET
 * -----------------------------------------------------------------------------
 * Small, stroke-based, theme-aware inline SVG illustrations, one matched to
 * each question kind / id (MASTER-PLAN section 5: "each question gets an
 * inline SVG (<= 10KB) matched to its content ... never a flat/generic
 * screen"). Each SVG is self-contained markup (~250-550 bytes), uses
 * stroke="currentColor" so it inherits the active theme token, and carries
 * aria-hidden="true" (decorative only — the real label is the question text).
 *
 * CORE SET (the per-question imagery the spec calls for):
 *   book, reader, feather, title-scroll, cover, upload, mic, camera, progress
 * COMPAT SET (kept for renderer/core field-kind fallbacks):
 *   pen, video, image, target, compass, sparkles, paper, user, chat
 *
 * THEME-AWARE: every glyph uses currentColor — no hard-coded fills — so the
 * same set renders correctly on light AND dark palettes with zero duplication.
 *
 * CONSUMPTION (renderer core / U05):
 *   global.BW.Illustrations.all['book']  -> SVG markup string
 *   global.BW.Illustrations.for(q)       -> best SVG for a config question
 *
 * PROVIDER-NEUTRAL: this is a dumb presentation layer. It holds no PITs, no
 * model ids, no account ids. Run a pure-logic self-test:
 *   node illustrations.js --selftest
 * ============================================================================= */
'use strict';

(function (global) {
  var ILLS = {
    /* --- core per-question set ------------------------------------------- */
    book: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M32 14c-8-7-20-7-26-4v38c6-3 18-3 26 4 8-7 20-7 26-4V10c-6-3-18-3-26 4z"/><path d="M32 14v38"/></svg>',

    reader: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="15" r="7"/><path d="M15 50c2-11 9-16 17-16s15 5 17 16"/><path d="M32 34c-5-5-15-5-20-2v12c5-3 15-3 20 2 5-5 15-5 20-2V32c-5-3-15-3-20 2z"/><path d="M32 34v12"/></svg>',

    feather: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 52L48 16"/><path d="M48 16c-4-5-17-3-25 3-6 5-10 15-10 27 12 0 22-4 27-10 6-8 9-16 8-20z"/><path d="M29 27l8 8"/><path d="M23 33l8 8"/></svg>',

    'title-scroll': '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="13" y="12" width="38" height="40" rx="6"/><path d="M13 24h38"/><path d="M13 40h38"/><path d="M13 12c-4 3-4 7 0 9"/><path d="M13 52c-4-3-4-7 0-9"/><path d="M51 12c4 3 4 7 0 9"/><path d="M51 52c4-3 4-7 0-9"/><path d="M23 31h18"/><path d="M23 36h13"/></svg>',

    cover: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="17" y="10" width="30" height="44" rx="5"/><path d="M17 10c-3 2-3 8 0 11"/><path d="M17 53c-3-2-3-8 0-11"/><rect x="22" y="18" width="20" height="6" rx="3"/><rect x="22" y="29" width="13" height="4" rx="2"/><path d="M22 38h8"/></svg>',

    upload: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M32 40V16"/><path d="M20 28l12-12 12 12"/><rect x="13" y="44" width="38" height="12" rx="6"/></svg>',

    mic: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="25" y="10" width="14" height="24" rx="7"/><path d="M20 30a12 12 0 0 0 24 0"/><path d="M32 42v10"/><path d="M25 52h14"/></svg>',

    camera: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="18" width="32" height="28" rx="7"/><path d="M40 28l14-7v22l-14-7z"/><circle cx="24" cy="32" r="8"/></svg>',

    progress: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 45h32"/><path d="M20 37h24"/><path d="M24 29h16"/><rect x="27" y="16" width="10" height="11" rx="2"/><path d="M32 7l2 4 4 1-3 3 1 4-4-2-4 2 1-4-3-3 4-1z"/></svg>',

    /* --- compat / field-kind fallbacks ----------------------------------- */
    pen: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 50l4-16 28-28 12 12-28 28z"/><path d="M32 22l10 10"/><path d="M10 54h18"/></svg>',

    video: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="10" y="16" width="30" height="32" rx="8"/><path d="M40 28l14-7v22l-14-7z"/></svg>',

    image: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="10" y="14" width="44" height="36" rx="6"/><circle cx="26" cy="26" r="5"/><path d="M14 44l12-10 10 8 8-6 6 8"/></svg>',

    target: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="32" r="22"/><circle cx="32" cy="32" r="13"/><circle cx="32" cy="32" r="4"/></svg>',

    compass: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="32" r="24"/><path d="M40 24l-6 16-6-10-10-6z"/></svg>',

    sparkles: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M32 8l6 14 14 6-14 6-6 14-6-14-14-6 14-6z"/><path d="M50 44l3 7 7 3-7 3-3 7-3-7-7-3 7-3z"/></svg>',

    paper: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 8h24l10 10v38H16z"/><path d="M40 8v10h10"/><path d="M24 28h18"/><path d="M24 36h18"/><path d="M24 44h12"/></svg>',

    user: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="22" r="12"/><path d="M12 54c2-12 11-18 20-18s18 6 20 18"/></svg>',

    chat: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 14h48v30H28l-14 12v-12H8z"/></svg>'
  };

  // Per-question content-bound mapping (never a generic screen). Each rule is a
  // regex against the question id, mirroring the renderer core's imageryFor().
  var RULES = [
    [/avatar|name|person|who|identity/i, 'user'],
    [/goal|wish|dream|want/i, 'target'],
    [/niche|field|market|topic|audience/i, 'compass'],
    [/story|quote|fact|memory|experience|real/i, 'sparkles'],
    [/cover|image|picture|look|design/i, 'cover'],
    [/title|subtitle|name-the/i, 'title-scroll'],
    [/tone|voice|style|feel|figure|how-you/i, 'feather'],
    [/why|reflect|reflection|reader/i, 'reader'],
    [/about|theme|subject|idea|outline|chapter|book/i, 'book'],
    [/email|contact|reach/i, 'chat']
  ];

  function forQuestion(q) {
    var id = (q && q.id) || '';
    var kind = (q && q.kind) || 'text';
    // media -> audio/camera; file -> upload; choice -> compass
    if (kind === 'choice') return ILLS.compass;
    if (kind === 'media') {
      var accept = q.handlers && q.handlers.media && q.handlers.media.accept;
      if (accept && accept.indexOf('video') !== -1) return ILLS.camera;
      if (accept && accept.indexOf('image') !== -1) return ILLS.image;
      return ILLS.mic;
    }
    if (kind === 'file-pdf' || kind === 'file-txt') return ILLS.upload;
    for (var i = 0; i < RULES.length; i++) {
      if (RULES[i][0].test(id)) return ILLS[RULES[i][1]];
    }
    return ILLS.pen;
  }

  var api = {
    all: ILLS,
    for: forQuestion,
    keys: Object.keys(ILLS),
    CORE_KEYS: ['book', 'reader', 'feather', 'title-scroll', 'cover', 'upload', 'mic', 'camera', 'progress']
  };

  // ---- pure-logic self-test (runs under node, no DOM) ----------------------
  function selftest() {
    var results = [];
    var coreKeys = api.CORE_KEYS;
    for (var i = 0; i < coreKeys.length; i++) {
      var key = coreKeys[i];
      var svg = ILLS[key];
      results.push([
        'core illustration present: ' + key,
        typeof svg === 'string' && svg.indexOf('<svg') === 0 && svg.indexOf('</svg>') !== -1
      ]);
      results.push([
        'size <= 10KB: ' + key,
        typeof svg === 'string' && svg.length <= 10240
      ]);
      results.push([
        'theme-aware (currentColor, no fill): ' + key,
        typeof svg === 'string' && svg.indexOf('currentColor') !== -1 && /fill="[^n"]/.test(svg) === false
      ]);
      results.push([
        'aria-hidden (decorative): ' + key,
        typeof svg === 'string' && svg.indexOf('aria-hidden="true"') !== -1
      ]);
    }
    results.push(['mapping: choice -> compass', forQuestion({ id: 'version', kind: 'choice' }) === ILLS.compass]);
    results.push(['mapping: media video -> camera', forQuestion({ id: 'video-1', kind: 'media', handlers: { media: { accept: ['video'] } } }) === ILLS.camera]);
    results.push(['mapping: media audio -> mic', forQuestion({ id: 'audio-1', kind: 'media', handlers: { media: { accept: ['audio'] } } }) === ILLS.mic]);
    results.push(['mapping: file -> upload', forQuestion({ id: 'book_pdf', kind: 'file-pdf' }) === ILLS.upload]);
    results.push(['mapping: title -> title-scroll', forQuestion({ id: 'title', kind: 'text' }) === ILLS['title-scroll']]);
    results.push(['mapping: cover -> cover', forQuestion({ id: 'cover_description', kind: 'textarea' }) === ILLS.cover]);
    results.push(['mapping: tone -> feather', forQuestion({ id: 'tone_style_1', kind: 'textarea' }) === ILLS.feather]);
    results.push(['mapping: about -> book', forQuestion({ id: 'book_about', kind: 'textarea' }) === ILLS.book]);
    results.push(['fallback: unknown -> pen', forQuestion({ id: 'zzz', kind: 'text' }) === ILLS.pen]);
    results.push(['keys are unique', new Set(api.keys).size === api.keys.length]);

    var pass = results.every(function (r) { return r[1]; });
    var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      lines.forEach(function (l) { process.stdout.write(l + '\n'); });
      process.stdout.write((pass ? 'U06 illustration set self-test: PASS' : 'U06 illustration set self-test: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  global.BW = global.BW || {};
  global.BW.Illustrations = api;

  if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
