/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U10 — EDITABLE TRANSCRIPT + ANSWER-YOUR-WAY
 * -----------------------------------------------------------------------------
 * The editable-transcript contract (MASTER-PLAN section 4) and the
 * answer-your-way tab set (section 5).
 *
 * WHAT THIS UNIT OWNS:
 *   1. Inline editable transcript: after a recording is transcribed the words
 *      appear INLINE and EDITABLE, labeled "from your recording", with the
 *      spoken language shown for confirmation. The client edits freely; the
 *      edit is stored under the SAME answer_id (an edit, not a new recording).
 *   2. Re-record SUPERSEDES by answer_id — a fresh recording carries a NEW
 *      answer_id and REPLACES the earlier recording's text for that question.
 *      It NEVER appends. `selectLiveAnswer` implements this: only the newest
 *      recording's text is live; older answer_ids are dropped, never merged.
 *   3. Answer-your-way tab set — Type / Upload PDF / Upload text / Audio /
 *      Video — config-driven per question (a question only offers the modes
 *      listed in its `answer_your_way`), with warm labels and a gentle
 *      best-fit highlight. Choice fields keep a single segmented enum (no
 *      tab wall, AF-BK-VERSION).
 *
 * PROVIDER-NEUTRAL: this module performs NO transcription and names NO model
 * provider. It includes `verifyNoAnthropic` as the AF-BW-MA-ANTHROPIC re-check
 * on any resolved transcription job: a model id matching /anthropic|claude/i
 * hard-fails the label path — never a silent fallback, never an Anthropic id.
 *
 * WARM LOW-OVERWHELM: every screen ends with "Save & come back later — your
 * answers are safe." The banned anti-anxiety words (Submit / Required / Final /
 * Deadline / You must / Error) never render; `scanBannedCopy` lint-proves this
 * module's own copy strings on every run of --selftest.
 *
 * INTEGRATION: pure core is DOM-free and unit-testable under node. The DOM
 * render helper (`renderTranscriptRegion`) is exported for the SPA (U05/U09)
 * to mount inside a media tab panel; it only touches the DOM when `document`
 * exists. A wiring seam is left for U13 (the transcription engine) — this
 * module consumes a job view shaped like the U04 job registry:
 *     { answer_id, status, text, transcript_json: { language? }, error? }
 *
 * Run the self-test:        node editable-transcript.js --selftest
 * Syntax check:             node -c editable-transcript.js
 * ============================================================================= */
(function (global) {
  'use strict';

  // Banned anti-anxiety words — these strings must NEVER render (T5 warmth
  // guard, MASTER-PLAN section 5). The module's own copy is linted against
  // them on every self-test run.
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  // AF-BW-MA-ANTHROPIC: provider-neutral. Any resolved transcription model id
  // containing anthropic/claude is a HARD FAIL — never a silent fallback.
  var ANTHROPIC_RE = /anthropic|claude/i;

  // The answer-your-way tab set, ordered as in MASTER-PLAN section 5.
  // Labels are the warm mode names; `rendererKey` maps back to the U05
  // renderer's panel keys ('media' for audio/video) for integration.
  var MODE_LABELS = {
    text: 'Type',
    'file-pdf': 'Upload PDF',
    'file-txt': 'Upload text',
    audio: 'Audio',
    video: 'Video'
  };
  var MODE_RENDERER = {
    text: 'text',
    'file-pdf': 'file-pdf',
    'file-txt': 'file-txt',
    audio: 'media',
    video: 'media'
  };

  // ---------------------------------------------------------------------------
  // Pure core — DOM-free, unit-testable
  // ---------------------------------------------------------------------------

  /** The transcript is always labeled "from your recording" (section 4). */
  function transcriptLabel() {
    return 'from your recording';
  }

  /**
   * Extract the spoken language from a job view for confirmation. Returns the
   * language string only when the job actually carries one — a missing
   * language is null (never a fabricated "English").
   */
  function jobLanguage(jobView) {
    if (!jobView) return null;
    if (jobView.transcript_json && typeof jobView.transcript_json.language === 'string'
        && jobView.transcript_json.language.trim()) {
      return jobView.transcript_json.language.trim();
    }
    if (typeof jobView.language === 'string' && jobView.language.trim()) {
      return jobView.language.trim();
    }
    return null;
  }

  /**
   * Build the editable-transcript state for a question from its job view.
   *   {
   *     answerId, text, language, languageKnown:boolean,
   *     confirmed:boolean, edited:boolean, status, failed:boolean
   *   }
   * `text` starts as the job's transcribed text and is edited in place under
   * the SAME answer_id (an edit, never a new recording).
   */
  function transcriptState(question, jobView) {
    var job = jobView || {};
    var lang = jobLanguage(job);
    return {
      answerId: job.answer_id || null,
      text: typeof job.text === 'string' ? job.text : '',
      language: lang,
      languageKnown: !!lang,
      confirmed: false,
      edited: false,
      status: job.status || 'queued',
      failed: job.status === 'failed' || !!job.error || !job.answer_id
    };
  }

  /** Apply a client edit to the transcript text (same answer_id, in place). */
  function applyEdit(state, newText) {
    if (!state) return state;
    state.text = String(newText == null ? '' : newText);
    state.edited = true;
    return state;
  }

  /**
   * Re-record SUPERSEDES by answer_id — NEVER appends. A new recording
   * (next.answer_id !== prev.answer_id) REPLACES the earlier text for the
   * question; the old answer_id is dropped from live view. If next carries the
   * same answer_id it is the same recording (an edit), not a supersede.
   * Returns { superseded, current, droppedAnswerId }.
   */
  function supersede(prev, next) {
    if (!next || !next.answer_id) return { superseded: false, current: prev || null, droppedAnswerId: null };
    if (prev && prev.answer_id && prev.answer_id === next.answer_id) {
      return { superseded: false, current: next, droppedAnswerId: null };
    }
    return {
      superseded: true,
      current: next,
      droppedAnswerId: prev && prev.answer_id ? prev.answer_id : null
    };
  }

  /**
   * Select the LIVE answer for a question from an ordered record list — the
   * newest by sequence wins; older answer_ids are dropped, never concatenated
   * (never appends). Returns the live record, or null when there is none.
   */
  function selectLiveAnswer(records) {
    if (!records || !records.length) return null;
    // The live answer is the record with the highest seq. A different
    // answer_id with a higher seq SUPERSEDES the earlier one; a same
    // answer_id with a higher seq is a later edit of the same recording.
    // Either way the newest seq is the live text — older text is never
    // appended, so the live answer can never contain superseded words.
    var best = records[0];
    for (var i = 1; i < records.length; i++) {
      if (records[i].seq > best.seq) best = records[i];
    }
    return best;
  }

  /** Confirm the shown language — records the client's confirmation. */
  function confirmLanguage(state) {
    if (state) state.confirmed = true;
    return state;
  }

  /** Warm sentence used beneath the editable transcript. */
  function transcriptHelperText() {
    return 'Your words are ready below — feel free to make them exactly yours.';
  }

  /** Warm affordance to re-record (replaces, never appends). */
  function reRecordLabel() {
    return 'Say it again instead';
  }

  /** Warm affordance to switch to another answer-your-way mode. */
  function switchModeLabel() {
    return 'Answer it a different way';
  }

  /**
   * AF-BW-MA-ANTHROPIC re-check on a resolved transcription job. Any model id
   * matching /anthropic|claude/i is a HARD FAIL. Returns { ok:true } or
   * { ok:false, code:'AF-BW-MA-ANTHROPIC', model }.
   */
  function verifyNoAnthropic(job) {
    var model = job && (job.model || (job.transcript_json && job.transcript_json.model));
    if (typeof model === 'string' && ANTHROPIC_RE.test(model)) {
      return { ok: false, code: 'AF-BW-MA-ANTHROPIC', model: model };
    }
    return { ok: true, code: null, model: null };
  }

  /**
   * Answer-your-way tab set for a question (MASTER-PLAN section 5).
   * Returns { order, set } where set[key] = { label, rendererKey } for each
   * offered mode. Choice fields return a single 'choice' entry (no tab wall,
   * AF-BK-VERSION). Audio vs video are separate tabs when the config offers
   * both.
   */
  function tabSetFor(question) {
    var ways = (question && question.answer_your_way) || [];
    var accept = question && question.handlers && question.handlers.media && question.handlers.media.accept;
    var set = {};
    var order = [];

    if (question && question.kind === 'choice') {
      set.choice = { label: 'Choose', rendererKey: 'choice' };
      order.push('choice');
      return { set: set, order: order };
    }

    function offer(key) {
      if (set[key]) return;
      set[key] = { label: MODE_LABELS[key], rendererKey: MODE_RENDERER[key] };
      order.push(key);
    }

    // A question with no explicit modes still gets the warm typing path.
    if (ways.length === 0 || ways.indexOf('text') !== -1 || ways.indexOf('textarea') !== -1) {
      offer('text');
    }
    if (ways.indexOf('file-pdf') !== -1) offer('file-pdf');
    if (ways.indexOf('file-txt') !== -1) offer('file-txt');
    if (ways.indexOf('media') !== -1) {
      var hasAudio = !accept || accept.indexOf('audio') !== -1;
      var hasVideo = accept && accept.indexOf('video') !== -1;
      if (hasAudio) offer('audio');
      if (hasVideo) offer('video');
    }
    return { set: set, order: order };
  }

  /** Human label for a mode key ('text' -> 'Type', 'audio' -> 'Audio', ...). */
  function modeLabel(key) {
    return MODE_LABELS[key] || 'Type';
  }

  /** First tab offered for a question (used to render the initial panel). */
  function firstMode(tabInfo) {
    return (tabInfo && tabInfo.order && tabInfo.order[0]) || 'text';
  }

  /**
   * Which answer-your-way modes a question offers at all — used to highlight
   * the best-fit mode gently, never to force one (section 5).
   */
  function offeredModes(question) {
    return tabSetFor(question).order.slice();
  }

  /**
   * T5 warmth guard: lint a set of copy strings against the banned words.
   * Returns the offending strings (empty array when clean). Used by --selftest
   * to prove this module's own copy never renders a banned word.
   */
  function scanBannedCopy(strings) {
    var hits = [];
    (strings || []).forEach(function (s) {
      var low = String(s).toLowerCase();
      for (var i = 0; i < BANNED_COPY.length; i++) {
        if (low.indexOf(BANNED_COPY[i]) !== -1) { hits.push(s); break; }
      }
    });
    return hits;
  }

  // ---------------------------------------------------------------------------
  // DOM render helper — exported for the SPA; touches the DOM only when it
  // exists. Mounts the editable transcript: label, editable textarea, language
  // confirmation, re-record affordance.
  // ---------------------------------------------------------------------------
  function renderTranscriptRegion(state, opts) {
    if (typeof document === 'undefined') return null;
    opts = opts || {};
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

    var wrap = el('div', { class: 'tr-wrap' });
    var label = el('p', { class: 'tr-label', text: transcriptLabel() });
    wrap.appendChild(label);

    var area = el('textarea', {
      class: 'field-textarea transcript',
      placeholder: 'Your words from the recording appear here, ready to edit.',
      'aria-label': 'Your answer, editable'
    });
    area.value = state && state.text ? state.text : '';
    if (opts.onEdit) {
      area.addEventListener('input', function () {
        if (opts.onEdit) opts.onEdit(area.value);
      });
    }
    wrap.appendChild(area);

    if (state && state.languageKnown) {
      var confirmRow = el('div', { class: 'tr-lang' });
      confirmRow.appendChild(el('span', { class: 'tr-lang-chip', text: 'Spoken in ' + state.language }));
      if (!state.confirmed && opts.onConfirm) {
        var confirmBtn = el('button', {
          type: 'button',
          class: 'tr-lang-ok',
          text: 'That\'s right'
        });
        confirmBtn.addEventListener('click', function () {
          if (opts.onConfirm) opts.onConfirm();
        });
        confirmRow.appendChild(confirmBtn);
      }
      wrap.appendChild(confirmRow);
    }

    if (opts.onReRecord) {
      var again = el('button', {
        type: 'button',
        class: 'tr-link',
        text: reRecordLabel()
      });
      again.addEventListener('click', function () { if (opts.onReRecord) opts.onReRecord(); });
      wrap.appendChild(again);
    }

    if (opts.onSwitchMode) {
      var switchBtn = el('button', {
        type: 'button',
        class: 'tr-link',
        text: switchModeLabel()
      });
      switchBtn.addEventListener('click', function () { if (opts.onSwitchMode) opts.onSwitchMode(); });
      wrap.appendChild(switchBtn);
    }

    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Exports
  // ---------------------------------------------------------------------------
  var api = {
    // pure core
    transcriptLabel: transcriptLabel,
    jobLanguage: jobLanguage,
    transcriptState: transcriptState,
    applyEdit: applyEdit,
    supersede: supersede,
    selectLiveAnswer: selectLiveAnswer,
    confirmLanguage: confirmLanguage,
    transcriptHelperText: transcriptHelperText,
    reRecordLabel: reRecordLabel,
    switchModeLabel: switchModeLabel,
    verifyNoAnthropic: verifyNoAnthropic,
    tabSetFor: tabSetFor,
    modeLabel: modeLabel,
    firstMode: firstMode,
    offeredModes: offeredModes,
    scanBannedCopy: scanBannedCopy,
    // DOM
    renderTranscriptRegion: renderTranscriptRegion
  };

  // ---------------------------------------------------------------------------
  // Self-test (runs under node, no DOM)
  // ---------------------------------------------------------------------------
  function selftest() {
    var results = [];
    function check(name, ok) { results.push([name, !!ok]); }

    // -- transcript label -----------------------------------------------------
    check('label is exactly "from your recording"', transcriptLabel() === 'from your recording');
    check('label never contains a banned word', scanBannedCopy([transcriptLabel()]).length === 0);

    // -- language -------------------------------------------------------------
    check('language from transcript_json', jobLanguage({ transcript_json: { language: 'English' } }) === 'English');
    check('language from top-level', jobLanguage({ language: 'Spanish' }) === 'Spanish');
    check('language unknown -> null (never fabricated)', jobLanguage({ text: 'hi' }) === null);
    check('language blank -> null', jobLanguage({ transcript_json: { language: '  ' } }) === null);

    // -- transcript state -----------------------------------------------------
    var st = transcriptState({ id: 'q' }, { answer_id: 'abc', status: 'done', text: 'Hello world', transcript_json: { language: 'English' } });
    check('state carries answer_id', st.answerId === 'abc');
    check('state carries transcribed text', st.text === 'Hello world');
    check('state knows the language', st.languageKnown === true && st.language === 'English');
    check('state not failed for a done job', st.failed === false);
    var failed = transcriptState({ id: 'q' }, { answer_id: 'x', status: 'failed', error: 'EXTRACT-NO-TEXT' });
    check('failed job surfaces as failed (never a silent blank)', failed.failed === true);
    var queued = transcriptState({ id: 'q' }, { answer_id: 'y', status: 'queued' });
    check('queued job not failed (Transcribing pill)', queued.failed === false);

    // -- edit -----------------------------------------------------------------
    var edited = applyEdit({ text: 'Hello world', edited: false }, 'Hello wonderful world');
    check('edit applies new text', edited.text === 'Hello wonderful world');
    check('edit marks edited', edited.edited === true);

    // -- re-record SUPERSEDES by answer_id, never appends ---------------------
    var r1 = { answer_id: 'rec-1', seq: 1, text: 'first take' };
    var r2 = { answer_id: 'rec-2', seq: 2, text: 'second take' };
    var sup = supersede(r1, r2);
    check('new answer_id supersedes', sup.superseded === true);
    check('supersede keeps only the new text', sup.current.text === 'second take');
    check('supersede never appends', (sup.current.text.indexOf('first take') === -1));
    check('supersede drops the old answer_id', sup.droppedAnswerId === 'rec-1');
    var same = supersede(r2, { answer_id: 'rec-2', seq: 2, text: 'second take edited' });
    check('same answer_id is an edit, not a supersede', same.superseded === false);
    var none = supersede(r1, null);
    check('no next recording -> no supersede', none.superseded === false && none.current === r1);

    // -- selectLiveAnswer (newest wins, never concatenates) --------------------
    var live = selectLiveAnswer([{ answer_id: 'rec-1', seq: 1, text: 'first take' }, { answer_id: 'rec-2', seq: 2, text: 'second take' }]);
    check('live answer is the newest by answer_id', live.answer_id === 'rec-2' && live.text === 'second take');
    check('live answer never appends older text', live.text.indexOf('first take') === -1);
    check('no records -> null', selectLiveAnswer([]) === null);

    // -- language confirmation -------------------------------------------------
    var st2 = { language: 'English', confirmed: false };
    confirmLanguage(st2);
    check('confirm marks confirmed', st2.confirmed === true);

    // -- verifyNoAnthropic (AF-BW-MA-ANTHROPIC) -------------------------------
    var bad = verifyNoAnthropic({ model: 'anthropic/claude-sonnet-4' });
    check('anthropic/claude model id hard-fails', bad.ok === false && bad.code === 'AF-BW-MA-ANTHROPIC');
    var bad2 = verifyNoAnthropic({ transcript_json: { model: 'claude-3' } });
    check('anthropic id inside transcript_json hard-fails', bad2.ok === false);
    var good = verifyNoAnthropic({ model: 'whisper-small' });
    check('provider-neutral model passes', good.ok === true);

    // -- answer-your-way tab set ----------------------------------------------
    var full = tabSetFor({ id: 'q', kind: 'textarea', answer_your_way: ['text', 'media', 'file-pdf', 'file-txt'], handlers: { media: { accept: ['audio', 'video'] } } });
    check('full tab set: Type present', full.set.text && full.set.text.label === 'Type');
    check('full tab set: Upload PDF present', full.set['file-pdf'] && full.set['file-pdf'].label === 'Upload PDF');
    check('full tab set: Upload text present', full.set['file-txt'] && full.set['file-txt'].label === 'Upload text');
    check('full tab set: Audio present', full.set.audio && full.set.audio.label === 'Audio');
    check('full tab set: Video present', full.set.video && full.set.video.label === 'Video');
    check('full tab set order matches section 5', JSON.stringify(full.order) === JSON.stringify(['text', 'file-pdf', 'file-txt', 'audio', 'video']));

    var audioQ = { id: 'q', kind: 'textarea', answer_your_way: ['text', 'media'], handlers: { media: { accept: ['audio'] } } };
    var audioOnly = tabSetFor(audioQ);
    check('audio-only media -> no video tab', !!audioOnly.set.audio && !audioOnly.set.video);

    var videoQ = { id: 'q', kind: 'textarea', answer_your_way: ['media'], handlers: { media: { accept: ['video'] } } };
    var videoOnly = tabSetFor(videoQ);
    check('video-only media -> no audio tab', !!videoOnly.set.video && !videoOnly.set.audio);

    var choiceQ = { id: 'v', kind: 'choice', enum: ['book', 'brand'] };
    var choice = tabSetFor(choiceQ);
    check('choice -> single Choose tab, no tab wall', !!choice.set.choice && choice.order.length === 1);

    var noModesQ = { id: 'q', kind: 'textarea' };
    var noModes = tabSetFor(noModesQ);
    check('no modes -> warm typing path', !!noModes.set.text && firstMode(noModes) === 'text');

    check('modeLabel audio', modeLabel('audio') === 'Audio');
    check('modeLabel unknown -> Type', modeLabel('nope') === 'Type');
    var fullQ = { id: 'q', kind: 'textarea', answer_your_way: ['text', 'media', 'file-pdf', 'file-txt'], handlers: { media: { accept: ['audio', 'video'] } } };
    check('offeredModes mirrors tab order', JSON.stringify(offeredModes(fullQ)) === JSON.stringify(tabSetFor(fullQ).order));

    // -- module copy is banned-word-free --------------------------------------
    var copy = [transcriptLabel(), transcriptHelperText(), reRecordLabel(), switchModeLabel()];
    check('module copy never renders a banned word', scanBannedCopy(copy).length === 0);

    var pass = results.every(function (r) { return r[1]; });
    if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
      results.forEach(function (r) {
        process.stdout.write((r[1] ? 'PASS' : 'FAIL') + '  ' + r[0] + '\n');
      });
      process.stdout.write((pass ? 'U10 editable-transcript + answer-your-way: PASS' : 'U10 editable-transcript + answer-your-way: FAIL') + '\n');
    }
    if (!pass && typeof process !== 'undefined') process.exitCode = 2;
    return pass;
  }

  global.BWEditableTranscript = api;

  if (typeof document !== 'undefined') {
    // SPA will call BWEditableTranscript directly; no auto-boot needed.
  } else if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
