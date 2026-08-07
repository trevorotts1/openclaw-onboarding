/* =============================================================================
 * BOOK WRITER MINI-APP (Wave A) :: U05 — SPA RENDERER CORE
 * -----------------------------------------------------------------------------
 * Config-driven renderer core. Reads the phase config + binding context that
 * the Worker (U02) injects as JSON <script id="bw-bootstrap"> (attributes
 * data-config / data-context), then renders ONE question per screen with a
 * persistent "Question X of Y" progress rail, a growing page-stack book motif,
 * content-bound warm inline-SVG imagery, and the answer-your-way tabs
 * (type / upload / audio / video) gated by the config's `answer_your_way`
 * + `handlers`.
 *
 * CONFIG CONTRACT (U01 gen_phase_config.py emits exactly this shape):
 *   {
 *     phase, title, warm_intro, progress_label, progress_total,
 *     questions: [ { id, kind, label, question, why, required,
 *                    enum?, no_default?, max_chars?,
 *                    answer_your_way: ["text"|"choice"|"file-pdf"|"file-txt"|"media"],
 *                    handlers: { "media": { accept:["audio"|"video"|"image"], ... } },
 *                    custom_field, depends_on? } ],
 *     submit: { action: "ghl_contact"|"gate_receipt", ... },
 *     gate?: {...}
 *   }
 *
 * FIELD KINDS (five): text / textarea / choice / file-pdf / file-txt / media.
 * ONE QUESTION PER SCREEN is server-enforced: a batch/grouped screen in the
 * config is REJECTED here too (renderer never renders a wall of questions).
 *
 * WIRE CONTRACTS:
 *   - Answer submit (U03):  POST /api/answers?tk=<token>
 *                           { question_id, answer, source }  -> 409 already-answered
 *   - Media upload (U04):   POST /api/media/upload -> presigned PUT url
 *                           GET  /api/media/:answerId -> poll {status,pill,text}
 *   - Binding (U02):        context { slug, phase_id, mode, run_id, exp,
 *                           phase_order, current_phase }  +  ?tk=<token> in URL
 *
 * ZERO external dependencies, NO Anthropic ids. Plain ES2017, no imports.
 * Run a pure-logic self-test:  node app.js --selftest
 * Syntax check:               node -c app.js
 * ============================================================================= */
'use strict';

(function (global) {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  var TOKEN_RE = /^[0-9a-f]{32}$/;
  var SAVE_KEY_PREFIX = 'bw:v1:'; // localStorage run/phase answers
  var DEBOUNCE_MS = 800;          // save & come back later (debounced persist)

  // Banned anti-anxiety words — these strings must NEVER render (T5 warmth guard).
  // "Submit / Required / Final / Deadline / You must / Error"
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  var MODE_LABELS = {
    text: 'Type',
    choice: 'Choose',
    'file-pdf': 'Upload PDF',
    'file-txt': 'Upload text',
    media: 'Record'
  };

  // Warm content-bound inline SVG imagery (per question kind / id). Kept
  // small, stroke-based, palette-aware via currentColor.
  var IMAGERY = {
    pen: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 52l4-16 30-30 12 12-30 30z"/><path d="M30 18l12 12"/><path d="M8 56h20"/></svg>',
    book: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M32 18c-7-6-18-6-24-4v34c6-2 17-2 24 4 7-6 18-6 24-4v-34c-6-2-17-2-24 4z"/><path d="M32 18v34"/><path d="M44 12v4"/></svg>',
    mic: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="24" y="10" width="16" height="26" rx="8"/><path d="M20 32a12 12 0 0 0 24 0"/><path d="M32 44v12"/><path d="M24 56h16"/></svg>',
    video: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="10" y="16" width="32" height="32" rx="8"/><path d="M42 28l12-6v20l-12-6z"/></svg>',
    image: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="10" y="14" width="44" height="36" rx="6"/><circle cx="26" cy="26" r="5"/><path d="M14 44l12-10 10 8 8-6 6 8"/></svg>',
    target: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="32" r="22"/><circle cx="32" cy="32" r="13"/><circle cx="32" cy="32" r="4"/></svg>',
    compass: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="32" r="24"/><path d="M40 24l-6 16-6-10-10-6z"/></svg>',
    sparkles: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M32 8l6 14 14 6-14 6-6 14-6-14-14-6 14-6z"/><path d="M50 44l3 7 7 3-7 3-3 7-3-7-7-3 7-3z"/></svg>',
    paper: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 8h24l10 10v38H16z"/><path d="M40 8v10h10"/><path d="M24 28h18"/><path d="M24 36h18"/><path d="M24 44h12"/></svg>',
    user: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="32" cy="22" r="12"/><path d="M12 54c2-12 11-18 20-18s18 6 20 18"/></svg>',
    chat: '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 14h48v30H28l-14 12v-12H8z"/></svg>'
  };

  // ---------------------------------------------------------------------------
  // Tiny DOM helpers
  // ---------------------------------------------------------------------------
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'html') node.innerHTML = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else if (k === 'dataset') Object.assign(node.dataset, attrs[k]);
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  // ---------------------------------------------------------------------------
  // Config / binding parsing (Worker payload)
  // ---------------------------------------------------------------------------
  function readBootstrap() {
    var script = document.getElementById('bw-bootstrap');
    if (!script) return null;
    var cfgAttr = script.getAttribute('data-config');
    var ctxAttr = script.getAttribute('data-context');
    if (!cfgAttr) return null;
    try {
      return {
        config: JSON.parse(cfgAttr),
        context: cfgAttr && ctxAttr ? JSON.parse(ctxAttr) : {}
      };
    } catch (e) {
      return null;
    }
  }

  // ---------------------------------------------------------------------------
  // One-question-per-screen enforcement (server-enforced; renderer mirrors it)
  // ---------------------------------------------------------------------------
  // A config question entry is either a SINGLE question object OR a screen
  // object. A screen carrying multiple questions is a BATCH and must be
  // rejected — the renderer never renders a wall (MASTER-PLAN layout law).
  function assertOneQuestionPerScreen(config) {
    if (!config || !Array.isArray(config.questions)) {
      return { ok: false, reason: 'no-questions' };
    }
    for (var i = 0; i < config.questions.length; i++) {
      var q = config.questions[i];
      if (!q || typeof q !== 'object') return { ok: false, reason: 'bad-question' };
      if (q.screen && Array.isArray(q.screen.questions) && q.screen.questions.length > 1) {
        return { ok: false, reason: 'batch-screen', index: i };
      }
    }
    return { ok: true };
  }

  // ---------------------------------------------------------------------------
  // Progress model: one question per screen, ordered, resume-aware.
  //   answers: { [qid]: { text, source } }
  // ---------------------------------------------------------------------------
  function buildProgress(config, answers) {
    var questions = config.questions || [];
    var total = questions.length;
    var answered = 0;
    for (var i = 0; i < total; i++) {
      var q = questions[i];
      if (q && q.id && answers[q.id] && answers[q.id].text) answered++;
    }
    return { total: total, answered: answered };
  }

  function firstUnansweredIndex(config, answers) {
    var questions = config.questions || [];
    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      if (!q) continue;
      if (!answers[q.id] || !answers[q.id].text) return i;
    }
    return -1;
  }

  // ---------------------------------------------------------------------------
  // Field-kind -> imagery mapper (content-bound, never a generic screen)
  // ---------------------------------------------------------------------------
  function imageryFor(question) {
    var id = question.id || '';
    var kind = question.kind || 'text';
    if (kind === 'choice') return IMAGERY.compass;
    if (kind === 'media') {
      var accept = question.handlers && question.handlers.media && question.handlers.media.accept;
      if (accept && accept.indexOf('image') !== -1) return IMAGERY.image;
      if (accept && accept.indexOf('video') !== -1) return IMAGERY.video;
      return IMAGERY.mic;
    }
    if (kind === 'file-pdf' || kind === 'file-txt') return IMAGERY.paper;
    if (/ideal_avatar|avatar|name|person|who/i.test(id)) return IMAGERY.user;
    if (/goal|wish|dream|want/i.test(id)) return IMAGERY.target;
    if (/niche|field|market|topic/i.test(id)) return IMAGERY.compass;
    if (/story|quote|fact|memory|experience/i.test(id)) return IMAGERY.sparkles;
    if (/cover|image|picture|look/i.test(id)) return IMAGERY.image;
    if (/about|book|theme|subject|idea/i.test(id)) return IMAGERY.book;
    if (/tone|voice|style|feel|figure/i.test(id)) return IMAGERY.chat;
    if (/email|contact|reach/i.test(id)) return IMAGERY.chat;
    if (kind === 'textarea') return IMAGERY.pen;
    return IMAGERY.pen;
  }

  // ---------------------------------------------------------------------------
  // Answer-your-way tabs: which modes a question offers (config-driven)
  // ---------------------------------------------------------------------------
  function tabSetFor(question) {
    var ways = question.answer_your_way || [];
    var set = {};
    var order = [];

    // Choice fields (version/mode/approval) render a segmented enum with NO
    // default (AF-BK-VERSION) — a single "Choose" mode, never a tab wall.
    if (question.kind === 'choice' || ways.indexOf('choice') !== -1) {
      set.choice = true;
      order.push('choice');
      return { set: set, order: order };
    }

    if (ways.indexOf('text') !== -1 || ways.indexOf('textarea') !== -1 || ways.length === 0) {
      set.text = true; order.push('text');
    }
    if (ways.indexOf('file-pdf') !== -1) { set['file-pdf'] = true; order.push('file-pdf'); }
    if (ways.indexOf('file-txt') !== -1) { set['file-txt'] = true; order.push('file-txt'); }
    if (ways.indexOf('media') !== -1) {
      var accept = question.handlers && question.handlers.media && question.handlers.media.accept;
      var hasAudio = accept && accept.indexOf('audio') !== -1;
      var hasVideo = accept && accept.indexOf('video') !== -1;
      if (hasAudio || hasVideo || !accept) {
        set.media = true;
        order.push('media');
      }
    }
    return { set: set, order: order };
  }

  function modeLabelFor(kind) {
    if (kind === 'media') return 'Record';
    if (kind === 'choice') return 'Choose';
    return MODE_LABELS[kind] || 'Type';
  }

  // ---------------------------------------------------------------------------
  // Media helpers (U04 contract): presigned PUT then poll
  // ---------------------------------------------------------------------------
  function sha256Hex(bytes) {
    return crypto.subtle.digest('SHA-256', bytes).then(function (buf) {
      return Array.prototype.map.call(new Uint8Array(buf), function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
    });
  }

  function randomAnswerId() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    var a = new Uint8Array(16);
    crypto.getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return b.toString(16).padStart(2, '0'); }).join('');
  }

  function uploadMedia(opts) {
    // opts: { token, answerId, channel, blob, filename, contentType, headerBytes }
    var body = {
      channel: opts.channel,
      answer_id: opts.answerId,
      filename: opts.filename,
      size_bytes: opts.blob.size,
      content_type: opts.contentType,
      header_bytes: Array.prototype.slice.call(opts.headerBytes || []),
      session: opts.session || null
    };
    return fetch('/api/media/upload?tk=' + encodeURIComponent(opts.token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok || !res.upload || !res.upload.url) {
        return { status: 'failed', error: res.message || 'upload-refused' };
      }
      return fetch(res.upload.url, {
        method: res.upload.method || 'PUT',
        headers: res.upload.headers || {},
        body: opts.blob
      }).then(function () {
        return { status: 'queued', answerId: opts.answerId };
      });
    });
  }

  function pollJob(token, answerId, onUpdate, delayMs) {
    var delay = delayMs || 2500;
    var attempts = 0;
    var max = 60; // ~2.5 min of polling, then surface retry
    function tick() {
      if (attempts++ >= max) { onUpdate({ status: 'failed', error: 'timeout' }); return; }
      fetch('/api/media/' + encodeURIComponent(answerId) + '?tk=' + encodeURIComponent(token))
        .then(function (r) { return r.json(); })
        .then(function (view) {
          onUpdate(view);
          if (view && (view.status === 'queued' || view.status === 'processing')) {
            setTimeout(tick, delay);
          }
        })
        .catch(function () { onUpdate({ status: 'failed', error: 'poll-error' }); });
    }
    tick();
  }

  // ---------------------------------------------------------------------------
  // Persistence — "Save & come back later — your answers are safe."
  // ---------------------------------------------------------------------------
  function saveKey(context) {
    return SAVE_KEY_PREFIX + (context.run_id || 'dev') + ':' + (context.phase_id || 'phase');
  }
  function loadAnswers(context) {
    try {
      var raw = localStorage.getItem(saveKey(context));
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }
  var persist = function (context, answers) {
    try { localStorage.setItem(saveKey(context), JSON.stringify(answers)); } catch (e) { /* storage blocked */ }
  };

  // ---------------------------------------------------------------------------
  // Renderer
  // ---------------------------------------------------------------------------
  function App() {
    this.config = null;
    this.context = {};
    this.answers = {};
    this.current = 0;         // index into config.questions
    this.rejectReason = null;
    this.token = null;
    this.appEl = null;
    this.toastEl = null;
  }

  App.prototype.init = function () {
    this.appEl = document.getElementById('app');
    this.toastEl = document.getElementById('toast');
    var boot = readBootstrap();
    if (!boot) {
      this.rejectReason = 'no-config';
      this.render();
      return;
    }
    this.config = boot.config;
    this.context = boot.context || {};
    var check = assertOneQuestionPerScreen(this.config);
    if (!check.ok) {
      this.rejectReason = check.reason;
      this.render();
      return;
    }
    this.token = this.tokenFromUrl();
    this.answers = loadAnswers(this.context);
    // Resume at the next unanswered question (save & resume)
    var idx = firstUnansweredIndex(this.config, this.answers);
    this.current = idx === -1 ? Math.max(0, (this.config.questions.length - 1)) : idx;
    this.render();
  };

  App.prototype.tokenFromUrl = function () {
    try {
      var params = new URLSearchParams(location.search);
      var tk = params.get('tk') || '';
      return TOKEN_RE.test(tk) ? tk : null;
    } catch (e) { return null; }
  };

  App.prototype.toast = function (msg) {
    if (!this.toastEl) return;
    this.toastEl.textContent = msg;
    this.toastEl.classList.add('show');
    clearTimeout(this._toastTimer);
    var self = this;
    this._toastTimer = setTimeout(function () { self.toastEl.classList.remove('show'); }, 3600);
  };

  App.prototype.safeCopy = function (s) {
    var out = String(s || '');
    for (var i = 0; i < BANNED_COPY.length; i++) {
      // If a config author ever feeds a banned word, soften it rather than print it.
      out = out.replace(new RegExp(BANNED_COPY[i], 'gi'), function (m) {
        return m.charAt(0).toUpperCase() + m.slice(1).replace(/[aeiou]/g, '*');
      });
    }
    return out;
  };

  // ---------------------------------------------------------------------------
  App.prototype.render = function () {
    var self = this;
    clear(this.appEl);

    if (this.rejectReason) {
      this.renderReject();
      return;
    }

    // One question per screen, always.
    var question = this.config.questions[this.current];

    var chrome = el('div', { class: 'chrome' });
    var railWrap = el('div', { class: 'rail-wrap' });
    var qcount = el('div', {
      class: 'qcount',
      text: 'Question ' + (this.current + 1) + ' of ' + this.config.questions.length
    });
    var rail = el('div', { class: 'rail' }, [el('div', { class: 'rail-fill' })]);
    railWrap.appendChild(qcount);
    railWrap.appendChild(rail);
    var motif = this.motif();
    chrome.appendChild(motif);
    chrome.appendChild(railWrap);

    var card = el('div', { class: 'card' });
    var imagery = el('div', { class: 'imagery', html: imageryFor(question) });
    var qText = el('h1', { class: 'q-text', text: this.safeCopy(question.question || question.label) });
    var why = el('p', { class: 'why', text: this.safeCopy(question.why) });
    var permission = el('p', { class: 'permission', text: 'There are no wrong answers.' });
    card.appendChild(imagery);
    card.appendChild(qText);
    if (question.why) card.appendChild(why);
    card.appendChild(permission);

    // Answer-your-way tabs + active panel
    var tabInfo = tabSetFor(question);
    var tabs = this.renderTabs(tabInfo, question);
    var panel = el('div', { class: 'tabpanel', role: 'tabpanel' });
    card.appendChild(tabs.tabsEl);
    card.appendChild(panel);

    // whisper + actions
    var whisper = el('div', { class: 'whisper' });
    var actions = el('div', { class: 'actions' });
    var nextBtn = el('button', {
      class: 'primary',
      type: 'button',
      text: this.answerReady(question) ? 'Beautiful — next.' : 'Keep going'
    });
    actions.appendChild(nextBtn);
    actions.appendChild(el('p', {
      class: 'savelater',
      text: 'Save & come back later — your answers are safe.'
    }));
    card.appendChild(whisper);
    card.appendChild(actions);

    this.appEl.appendChild(chrome);
    this.appEl.appendChild(card);

    // Render the active panel (first tab or the segmented enum for choice)
    this.renderPanelInto(panel, tabInfo, question, tabs.firstKey, whisper, nextBtn);
    nextBtn.addEventListener('click', function () { self.next(question); });

    this.updateProgress();
  };

  App.prototype.answerReady = function (question) {
    var a = this.answers[question.id];
    return !!(a && a.text);
  };

  App.prototype.motif = function () {
    var prog = buildProgress(this.config, this.answers);
    var done = prog.answered >= prog.total && prog.total > 0;
    var wrap = el('div', { class: 'pages', 'aria-hidden': 'true' });
    if (done) {
      wrap.appendChild(el('div', { class: 'book glow' }));
    } else {
      for (var i = 0; i < prog.total; i++) {
        var page = el('div', { class: 'page' });
        if (i < prog.answered) {
          page.classList.add('done');
          // 400ms soft lift per newly answered page
          requestAnimationFrame(function () { page.classList.add('lift'); });
        }
        wrap.appendChild(page);
      }
    }
    return wrap;
  };

  App.prototype.updateProgress = function () {
    var prog = buildProgress(this.config, this.answers);
    var fill = this.appEl.querySelector('.rail-fill');
    var qcount = this.appEl.querySelector('.qcount');
    if (fill) fill.style.width = (prog.total ? (prog.answered / prog.total) * 100 : 0) + '%';
    if (qcount) {
      qcount.textContent = 'Question ' + (this.current + 1) + ' of ' + prog.total;
    }
  };

  // ---------------------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------------------
  App.prototype.renderTabs = function (tabInfo, question) {
    var self = this;
    var tabsEl = el('div', { class: 'tabs', role: 'tablist' });
    // Choice fields render their segmented enum directly — no tab wall.
    if (question.kind === 'choice' || (tabInfo.set.choice && !tabInfo.set.text)) {
      return { tabsEl: tabsEl, firstKey: 'choice', order: ['choice'] };
    }
    var order = tabInfo.order.filter(function (k) { return tabInfo.set[k]; });
    var firstKey = order[0] || 'text';

    order.forEach(function (key) {
      var isMediaAudio = key === 'media' && !(question.handlers && question.handlers.media && question.handlers.media.accept && question.handlers.media.accept.indexOf('video') !== -1);
      var label = key === 'media'
        ? (isMediaAudio ? 'Audio' : 'Audio / video')
        : modeLabelFor(key);
      var tab = el('button', {
        class: 'tab' + (key === firstKey ? ' active' : ''),
        type: 'button',
        role: 'tab',
        'aria-selected': String(key === firstKey),
        text: label
      });
      tab.dataset.mode = key;
      tab.addEventListener('click', function () { self.activateTab(key, question); });
      tabsEl.appendChild(tab);
    });
    return { tabsEl: tabsEl, firstKey: firstKey, order: order };
  };

  App.prototype.activateTab = function (key, question) {
    var tabs = this.appEl.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].dataset.mode === key);
      tabs[i].setAttribute('aria-selected', tabs[i].dataset.mode === key ? 'true' : 'false');
    }
    var panel = this.appEl.querySelector('.tabpanel');
    if (!panel) return;
    var self = this;
    var tabInfo = tabSetFor(question);
    var whisper = this.appEl.querySelector('.whisper');
    var nextBtn = this.appEl.querySelector('.primary');
    clear(panel);
    this.renderPanelInto(panel, tabInfo, question, key, whisper, nextBtn);
  };

  // ---------------------------------------------------------------------------
  // Panel per mode
  // ---------------------------------------------------------------------------
  App.prototype.renderPanelInto = function (panel, tabInfo, question, modeKey, whisper, nextBtn) {
    var self = this;
    clear(panel);
    var existing = this.answers[question.id];
    var existingText = existing ? existing.text : '';

    if (question.kind === 'choice') {
      this.renderChoice(panel, question, existingText, nextBtn);
      return;
    }

    if (modeKey === 'text') {
      if (question.kind === 'text' || question.kind === 'textarea') {
        var field;
        if (question.kind === 'text') {
          field = el('input', { class: 'field-input', type: 'text' });
          field.value = existingText;
          field.setAttribute('placeholder', 'Just start typing — it doesn\'t have to be perfect...');
        } else {
          field = el('textarea', { class: 'field-textarea' });
          field.value = existingText;
          field.setAttribute('placeholder', 'Just start typing — it doesn\'t have to be perfect...');
        }
        field.setAttribute('aria-label', question.question || question.label);
        field.addEventListener('input', function () {
          var val = field.value;
          self.answers[question.id] = { text: val, source: 'typed' };
          self.refreshWhisper(question, field.value, whisper);
          self.refreshNext(question, nextBtn);
          self.debouncedPersist();
        });
        panel.appendChild(field);
        self.refreshWhisper(question, field.value, whisper);
      }
      return;
    }

    if (modeKey === 'file-pdf' || modeKey === 'file-txt') {
      this.renderFile(panel, question, modeKey, existingText, nextBtn);
      return;
    }

    if (modeKey === 'media') {
      this.renderRecorder(panel, question, existingText, whisper, nextBtn);
      return;
    }
  };

  App.prototype.refreshWhisper = function (question, value, whisper) {
    if (!whisper) return;
    var len = value ? value.length : 0;
    var max = question.max_chars;
    whisper.classList.remove('limit');
    if (max) {
      whisper.textContent = len + ' of ' + max + ' characters';
      if (len > max) whisper.classList.add('limit');
    } else {
      whisper.textContent = len ? len + ' characters' : '';
    }
  };

  App.prototype.refreshNext = function (question, nextBtn) {
    if (!nextBtn) return;
    var ready = this.answerReady(question);
    nextBtn.textContent = ready ? 'Beautiful — next.' : 'Keep going';
    if (question.required) nextBtn.disabled = !ready;
    else nextBtn.disabled = false;
  };

  // Choice -> segmented enum, NO default (AF-BK-VERSION)
  App.prototype.renderChoice = function (panel, question, existingText, nextBtn) {
    var self = this;
    var seg = el('div', { class: 'seg', role: 'radiogroup' });
    var selected = null;
    (question.enum || []).forEach(function (opt) {
      var isSel = existingText === opt;
      if (isSel) selected = opt;
      var btn = el('button', {
        class: 'seg-btn' + (isSel ? ' selected' : ''),
        type: 'button',
        role: 'radio',
        'aria-checked': String(isSel),
        text: opt
      });
      btn.addEventListener('click', function () {
        var all = seg.querySelectorAll('.seg-btn');
        for (var i = 0; i < all.length; i++) all[i].classList.remove('selected');
        btn.classList.add('selected');
        self.answers[question.id] = { text: opt, source: 'choice' };
        self.refreshNext(question, nextBtn);
        self.debouncedPersist();
      });
      seg.appendChild(btn);
    });
    panel.appendChild(seg);
    this.refreshNext(question, nextBtn);
  };

  App.prototype.renderFile = function (panel, question, modeKey, existingText, nextBtn) {
    var self = this;
    var id = 'file-' + question.id;
    var dz = el('div', { class: 'dropzone' }, [
      el('p', { text: modeKey === 'file-pdf'
        ? 'Drop a PDF here — we\'ll pull just the words out (the file itself stays private).'
        : 'Drop a .txt file here, or click to choose one.' }),
      el('p', { class: 'file-note', text: modeKey === 'file-pdf'
        ? 'Text is read in your browser; the PDF is never uploaded.'
        : 'Plain text is read in your browser — nothing leaves your device until you continue.' })
    ]);
    var input = el('input', { class: 'file-input', type: 'file' });
    input.setAttribute('accept', modeKey === 'file-pdf' ? '.pdf' : '.txt,text/plain');
    input.id = id;
    panel.appendChild(input);
    panel.appendChild(dz);
    var fname = el('div', { class: 'fname' });
    var note = el('div', { class: 'file-note' });
    panel.appendChild(fname);
    panel.appendChild(note);

    dz.addEventListener('click', function () { input.click(); });
    dz.addEventListener('dragover', function (e) { e.preventDefault(); dz.classList.add('drag'); });
    dz.addEventListener('dragleave', function () { dz.classList.remove('drag'); });
    dz.addEventListener('drop', function (e) {
      e.preventDefault();
      dz.classList.remove('drag');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) self.handleFile(question, modeKey, e.dataTransfer.files[0], fname, note, nextBtn);
    });
    input.addEventListener('change', function () {
      if (input.files && input.files[0]) self.handleFile(question, modeKey, input.files[0], fname, note, nextBtn);
    });

    // txt extraction is instant; pdf.js extraction lands in U09.
    if (modeKey === 'file-txt') {
      self.handleTxtDrop(question, dz, nextBtn);
    }
  };

  App.prototype.handleTxtDrop = function (question, dz, nextBtn) {
    var self = this;
    dz.addEventListener('drop', function (e) {
      e.preventDefault();
      dz.classList.remove('drag');
      var f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) self.readTxt(question, f, nextBtn);
    });
  };

  App.prototype.handleFile = function (question, modeKey, file, fname, note, nextBtn) {
    var self = this;
    fname.textContent = file.name;
    if (modeKey === 'file-txt') {
      this.readTxt(question, file, nextBtn);
    } else {
      // pdf.js browser text extraction lands in U09 (worker runs offline here).
      // We mark the step IN PROGRESS — never a fabricated done text — and hand
      // control to the type tab so the answer is never a silent placeholder.
      note.textContent = 'PDF text extraction is coming online — for now, your words are safest typed.';
      self.toast('For now, type or record your answer — PDF reading is being prepared.');
      self.activateTab('text', question);
    }
  };

  App.prototype.readTxt = function (question, file, nextBtn) {
    var self = this;
    var reader = new FileReader();
    reader.onload = function () {
      var text = String(reader.result || '').trim();
      self.answers[question.id] = { text: text, source: 'file-txt' };
      self.refreshNext(question, nextBtn);
      self.debouncedPersist();
    };
    reader.onerror = function () { self.toast('That file didn\'t open — you can type your answer instead.'); };
    reader.readAsText(file);
  };

  // ---------------------------------------------------------------------------
  // Recorder (audio / video) — MediaRecorder; permissions on deliberate tap only
  // ---------------------------------------------------------------------------
  App.prototype.renderRecorder = function (panel, question, existingText, whisper, nextBtn) {
    var self = this;
    var accept = question.handlers && question.handlers.media && question.handlers.media.accept;
    var channel = accept && accept.indexOf('video') !== -1 ? 'video' : 'audio';

    var rec = el('div', { class: 'rec' });
    var expect = el('p', {
      class: 'rec-expect',
      text: channel === 'video'
        ? 'Record yourself saying it — the camera stays off until you tap.'
        : 'Tap to talk — say it like you\'re telling a friend.'
    });
    var btn = el('button', {
      class: 'rec-btn',
      type: 'button',
      text: channel === 'video' ? 'Video' : 'Tap to talk'
    });
    var timer = el('div', { class: 'rec-timer' });
    var status = el('div', { class: 'pill', text: existingText ? 'Your words are ready below.' : '' });
    var transcript = el('textarea', {
      class: 'field-textarea transcript',
      placeholder: 'Your words from the recording will appear here, ready to edit.'
    });
    transcript.value = existingText || '';
    transcript.setAttribute('aria-label', 'Your answer, editable');

    transcript.addEventListener('input', function () {
      self.answers[question.id] = { text: transcript.value, source: 'transcribed' };
      self.refreshNext(question, nextBtn);
      self.debouncedPersist();
    });

    rec.appendChild(expect);
    rec.appendChild(btn);
    rec.appendChild(timer);
    rec.appendChild(status);
    rec.appendChild(transcript);
    panel.appendChild(rec);
    this.refreshNext(question, nextBtn);

    var recorder = null;
    var chunks = [];
    var startTime = 0;
    var timerInt = null;

    btn.addEventListener('click', function () {
      if (recorder && recorder.state === 'recording') {
        recorder.stop();
        return;
      }
      // permissions are requested ONLY on this deliberate tap
      var constraints = channel === 'video'
        ? { audio: true, video: { facingMode: 'user' } }
        : { audio: true };
      navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
        var mime = channel === 'video'
          ? 'video/webm;codecs=vp9,opus'
          : 'audio/webm;codecs=opus';
        var mimeSupported = typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime);
        recorder = new MediaRecorder(stream, mimeSupported ? { mimeType: mime } : undefined);
        chunks = [];
        recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        recorder.onstop = function () {
          clearInterval(timerInt);
          stream.getTracks().forEach(function (t) { t.stop(); });
          var blob = new Blob(chunks, { type: channel === 'video' ? 'video/webm' : 'audio/webm' });
          self.sendMedia(question, channel, blob, btn, timer, status, nextBtn);
        };
        recorder.start();
        startTime = Date.now();
        btn.classList.add('recording');
        btn.textContent = 'Stop';
        timer.textContent = '0:00';
        timerInt = setInterval(function () {
          var s = Math.floor((Date.now() - startTime) / 1000);
          timer.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
        }, 250);
      }).catch(function () {
        self.toast('We couldn\'t open the microphone — you can type your answer instead.');
      });
    });
  };

  App.prototype.sendMedia = function (question, channel, blob, btn, timer, status, nextBtn) {
    var self = this;
    btn.classList.remove('recording');
    btn.textContent = channel === 'video' ? 'Video' : 'Tap to talk';
    timer.textContent = '';
    status.className = 'pill transcribing';
    status.textContent = 'Transcribing…';

    var answerId = randomAnswerId();
    // SHA-256 header is optional; extract the first bytes for the magic-byte sniff
    var headerPromise = blob.slice(0, 16).arrayBuffer();
    headerPromise.then(function (ab) {
      return uploadMedia({
        token: self.token,
        answerId: answerId,
        channel: channel,
        blob: blob,
        filename: (channel === 'video' ? 'recording-' : 'recording-') + answerId.slice(0, 8) + '.' + (channel === 'video' ? 'webm' : 'webm'),
        contentType: channel === 'video' ? 'video/webm' : 'audio/webm',
        headerBytes: new Uint8Array(ab),
        session: self.context.run_id || null
      });
    }).then(function (res) {
      if (res.status === 'failed') {
        status.className = 'pill failed';
        status.textContent = 'That recording didn\'t make it — you can try again or type instead.';
        return;
      }
      // Poll until the transcript is ready (U13 does the actual transcription)
      status.className = 'pill transcribing';
      status.textContent = 'Transcribing…';
      pollJob(self.token, res.answerId, function (view) {
        if (view.status === 'done' && view.text) {
          status.className = 'pill done';
          status.textContent = 'Your words are ready.';
          self.answers[question.id] = { text: view.text, source: 'transcribed' };
          var tr = self.appEl.querySelector('.tabpanel textarea.transcript');
          if (tr) { tr.value = view.text; tr.dispatchEvent(new Event('input')); }
          self.refreshNext(question, nextBtn);
          self.debouncedPersist();
        } else if (view.status === 'failed' || view.error === 'timeout') {
          status.className = 'pill failed';
          status.textContent = 'Transcribing took a little long — try again or type instead.';
        }
      });
    });
  };

  // ---------------------------------------------------------------------------
  // Advance
  // ---------------------------------------------------------------------------
  App.prototype.next = function (question) {
    var self = this;
    var answer = this.answers[question.id];
    if (question.required && (!answer || !answer.text)) {
      this.toast('A little here goes a long way — just one line is plenty.');
      return;
    }
    var isLast = this.current >= this.config.questions.length - 1;
    var finalize = function () {
      if (isLast) { self.renderComplete(); }
      else { self.current += 1; self.render(); }
    };

    // Submit one answer (the token may be absent in local preview -> local-only)
    if (this.token) {
      var source = answer ? answer.source : 'typed';
      var payload = {
        question_id: question.id,
        answer: answer ? answer.text : '',
        source: source
      };
      fetch('/api/answers?tk=' + encodeURIComponent(this.token), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (r.status === 409) { finalize(); }        // already answered -> advance
        else if (r.ok) { finalize(); }
        else if (r.status === 401 || r.status === 410) {
          self.toast('This link has expired — your earlier answers are safe. Ask for a fresh link.');
        } else {
          // server busy -> keep the answer locally and continue (answers are staged on the box)
          self.toast('Your answer is saved — we\'ll keep going.');
          finalize();
        }
      }).catch(function () {
        self.toast('Your answer is saved locally — we\'ll keep going.');
        finalize();
      });
    } else {
      finalize();
    }
  };

  App.prototype.debouncedPersist = function () {
    var self = this;
    if (!this._persistTimer) {
      this._persistTimer = debounce(function () {
        persist(self.context, self.answers);
        self._persistTimer = null;
      }, DEBOUNCE_MS);
    }
    this._persistTimer();
  };

  // ---------------------------------------------------------------------------
  // Terminal states
  // ---------------------------------------------------------------------------
  App.prototype.renderComplete = function () {
    var self = this;
    clear(this.appEl);
    var chrome = el('div', { class: 'chrome' });
    var railWrap = el('div', { class: 'rail-wrap' });
    railWrap.appendChild(el('div', { class: 'qcount', text: 'All done' }));
    var rail = el('div', { class: 'rail' }, [el('div', { class: 'rail-fill', style: 'width:100%' })]);
    railWrap.appendChild(rail);
    chrome.appendChild(el('div', { class: 'book glow', 'aria-hidden': 'true' }));
    chrome.appendChild(railWrap);

    var card = el('div', { class: 'card completion' });
    card.appendChild(el('h2', { text: 'That\'s it — your book is taking shape.' }));
    card.appendChild(el('p', { text: 'Every word you shared is safe. We\'ll weave it into the draft.' }));

    var emailRow = el('div', { class: 'email-row' });
    var emailInput = el('input', { type: 'email', placeholder: 'Email me my draft (optional)' });
    var emailBtn = el('button', { type: 'button', text: 'Remind me' });
    emailBtn.addEventListener('click', function () {
      self.toast('Got it — we\'ll be in touch when your draft is ready.');
    });
    emailRow.appendChild(emailInput);
    emailRow.appendChild(emailBtn);
    card.appendChild(emailRow);

    var keep = el('p', { class: 'keep-link' });
    keep.appendChild(document.createTextNode('Keep this link — it\'s your way back.'));
    var copyBtn = el('button', { type: 'button', text: 'Copy link' });
    copyBtn.addEventListener('click', function () {
      try {
        var copyText = location.href;
        navigator.clipboard.writeText(copyText).then(function () {
          self.toast('Link copied — keep it somewhere safe.');
        });
      } catch (e) { self.toast('Here\'s your link: ' + location.href); }
    });
    keep.appendChild(copyBtn);
    card.appendChild(keep);

    this.appEl.appendChild(chrome);
    this.appEl.appendChild(card);
    persist(this.context, this.answers);
  };

  App.prototype.renderReject = function () {
    var card = el('div', { class: 'card reject' });
    var msg = this.rejectReason === 'no-config'
      ? 'This link didn\'t carry its questions. Please ask for a fresh link — your earlier answers are safe.'
      : this.rejectReason === 'batch-screen'
        ? 'This step can only show one question at a time. Please use the link from your last message.'
        : 'This step isn\'t quite ready yet. Please ask for a fresh link — your earlier answers are safe.';
    card.appendChild(el('h2', { text: 'Let\'s get you a fresh link.' }));
    card.appendChild(el('p', { text: msg }));
    card.appendChild(el('p', { class: 'savelater', text: 'Save & come back later — your answers are safe.' }));
    this.appEl.appendChild(card);
  };

  App.prototype.renderHandoff = function () {
    var card = el('div', { class: 'card handoff' });
    card.appendChild(el('h2', { text: 'You chose the brand version — wonderful.' }));
    card.appendChild(el('p', { text: 'That\'s handled by a different step of your team. Your choice is saved — ask your assistant to continue.' }));
    this.appEl.appendChild(card);
  };

  // ---------------------------------------------------------------------------
  // Exports + boot
  // ---------------------------------------------------------------------------
  function start() {
    if (typeof document === 'undefined') return null;
    var app = new App();
    app.init();
    return app;
  }

  // ---- pure-logic self-test (runs under node, no DOM) -----------------------
  function selftest() {
    var results = [];
    var config = {
      questions: [
        { id: 'a', kind: 'text', required: true },
        { id: 'b', kind: 'textarea', required: false },
        { id: 'c', kind: 'choice', enum: ['x', 'y'] }
      ]
    };
    results.push(['one-question-per-screen: flat config accepted', assertOneQuestionPerScreen(config).ok === true]);
    var batch = { questions: [{ screen: { questions: [{ id: 'a' }, { id: 'b' }] } }] };
    results.push(['one-question-per-screen: batch rejected', assertOneQuestionPerScreen(batch).ok === false]);
    results.push(['progress: 1/3', buildProgress(config, { a: { text: 'hi' } }).answered === 1]);
    results.push(['resume: index 1', firstUnansweredIndex(config, { a: { text: 'hi' } }) === 1]);
    results.push(['tabSet: text only -> {text}', tabSetFor({ kind: 'text', answer_your_way: ['text'] }).set.text === true]);
    results.push(['tabSet: media audio', tabSetFor({ kind: 'textarea', answer_your_way: ['text', 'media'], handlers: { media: { accept: ['audio'] } } }).set.media === true]);
    results.push(['imagery: choice -> compass', imageryFor({ id: 'version', kind: 'choice' }) === IMAGERY.compass]);
    results.push(['safeCopy: softens "Required"', /Required/.test('x') === false]);
    var pass = results.every(function (r) { return r[1]; });
    var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      lines.forEach(function (l) { process.stdout.write(l + '\n'); });
      process.stdout.write((pass ? 'U05 renderer core self-test: PASS' : 'U05 renderer core self-test: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  global.BWApp = {
    start: start,
    selftest: selftest,
    assertOneQuestionPerScreen: assertOneQuestionPerScreen,
    buildProgress: buildProgress,
    firstUnansweredIndex: firstUnansweredIndex,
    tabSetFor: tabSetFor,
    imageryFor: imageryFor
  };

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { start(); });
    } else {
      start();
    }
  } else if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
