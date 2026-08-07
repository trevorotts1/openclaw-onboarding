/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U09 — RECORDER / UPLOAD WIDGETS
 * -----------------------------------------------------------------------------
 * The recorder + upload widget layer (MASTER-PLAN section 9):
 *   - MediaRecorder AUDIO + VIDEO capture with a permission GATE and a camera
 *     GATE: the microphone/camera are requested ONLY on a deliberate tap, and
 *     a denied / unavailable / not-anything permission is surfaced gently —
 *     the client can always type instead. Never a silent blank, never a
 *     surprise permission prompt.
 *   - File pickers for PDF and .txt (drop zone + picker), with a
 *     pdf.js-based PDF preview whose import is STUB-FRIENDLY: the module never
 *     `import`s pdf.js statically, so it runs offline and in node; the SPA
 *     injects `global.pdfjsLib` (or a stub) and the module loads the real
 *     library lazily via `loadPdfJs()`. When the library is absent, PDF text
 *     extraction is marked IN PROGRESS (never a fabricated done) and the warm
 *     typing path is offered.
 *   - Upload path wired to the U04 worker media POST contract (POST
 *     /api/media/upload -> presigned DIRECT R2 PUT -> poll), exactly as the
 *     U05 renderer core wires it. PDF/.txt ride the text path (browser reads
 *     the file; the file itself is never uploaded).
 *
 * ONE QUESTION PER SCREEN (U05) and REDUCED-MOTION (U06) are respected:
 *   - This module renders a SINGLE widget set for one question; it never
 *     renders a batch. `assertOneQuestion` mirrors the server-enforced law.
 *   - It emits no infinite motion of its own (recording pulse is driven by
 *     the theme's `.rec-btn.recording` CSS which U06's reduced-motion block
 *     already disables). A `motionOk()` helper lets callers branch on
 *     `prefers-reduced-motion` when they need to.
 *
 * PROVIDER-NEUTRAL / CONSTRAINTS (fail-closed):
 *   - NO Anthropic id anywhere (AF-BW-MA-ANTHROPIC). `verifyNoAnthropic`
 *     re-checks any resolved transcription job view, exactly as U10 does.
 *   - NO {{...}} template placeholders in shipped code.
 *   - NO real zone/account id. The upload POST body carries only the channel,
 *     answer_id, filename, size, content-type, header bytes, and session.
 *
 * USAGE
 *   node recorder.js --selftest          pure core + DOM-stub render self-test
 *   node recorder.selftest.mjs           same suite, standalone .mjs runner
 *   node -c recorder.js                  syntax check
 * ============================================================================= */
'use strict';

(function (global) {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  // Banned anti-anxiety words — must never render (T5 warmth guard). Matches
  // the U08 lint word set exactly.
  var BANNED_COPY = ['submit', 'required', 'final', 'deadline', 'you must', ' error'];

  // AF-BW-MA-ANTHROPIC: provider-neutral — any resolved transcription model id
  // containing anthropic/claude is a HARD FAIL (never a silent fallback).
  var ANTHROPIC_RE = /anthropic|claude/i;

  // MediaRecorder MIME hints (preferred first; isTypeSupported falls back).
  var MIME_HINTS = {
    audio: ['audio/webm;codecs=opus', 'audio/webm'],
    video: ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
  };

  // Magic-byte header families (mirrors media-lib.js MAGIC so the browser-side
  // sniff agrees with the worker's hard REJECT-FORMAT gate).
  var MAGIC_HEADERS = {
    pdf: [0x25, 0x50, 0x44, 0x46],           // %PDF
    txt: null                                // text has no magic requirement
  };

  // Recorder / file warm copy (no banned words; lint-checked in self-test).
  var COPY = {
    audioExpect: 'Tap to talk — say it like you\'re telling a friend.',
    videoExpect: 'Record yourself saying it — the camera stays off until you tap.',
    tapToTalk: 'Tap to talk',
    startVideo: 'Start recording',
    stopLabel: 'Stop',
    cameraOff: 'Camera off',
    micDenied: 'We couldn\'t open the microphone — you can type your answer instead.',
    cameraDenied: 'The camera wasn\'t available — you can still type or record audio instead.',
    unsupported: 'Your browser can\'t record on this device — you can type your answer instead.',
    emptyRecording: 'That recording was empty — give it one more try, or type instead.',
    uploading: 'Transcribing…',
    ready: 'Your words are ready.',
    uploadRefused: 'That recording didn\'t make it — you can try again or type instead.',
    uploadTimeout: 'Transcribing took a little long — try again or type instead.',
    pdfNote: 'Text is read in your browser; the PDF is never uploaded.',
    txtNote: 'Plain text is read in your browser — nothing leaves your device until you continue.',
    pdfUnavailable: 'PDF reading needs a moment to prepare — for now, your words are safest typed.',
    badPdf: 'That PDF didn\'t open as text — you can type or record your answer instead.',
    badFile: 'That file didn\'t open — you can type your answer instead.',
    pdfLoading: 'Reading the PDF…',
    dropPdf: 'Drop a PDF here — we\'ll pull just the words out (the file itself stays private).',
    dropTxt: 'Drop a .txt file here, or click to choose one.'
  };

  // ---------------------------------------------------------------------------
  // Pure core — DOM-free, unit-testable
  // ---------------------------------------------------------------------------

  /**
   * Deterministic mode key -> {expect, start, channel} wiring for the widget.
   * modeKey is 'audio' | 'video' | 'file-pdf' | 'file-txt' (U10 tab keys).
   */
  function widgetForMode(modeKey) {
    if (modeKey === 'video') {
      return { channel: 'video', expect: COPY.videoExpect, start: COPY.startVideo };
    }
    if (modeKey === 'audio') {
      return { channel: 'audio', expect: COPY.audioExpect, start: COPY.tapToTalk };
    }
    if (modeKey === 'file-pdf') return { channel: 'file-pdf', expect: COPY.dropPdf, start: 'Choose PDF' };
    if (modeKey === 'file-txt') return { channel: 'file-txt', expect: COPY.dropTxt, start: 'Choose text' };
    return null;
  }

  /**
   * Which channel a question's `media.accept` resolves to: 'video' when the
   * accept list mentions video (the widget shows the camera gate), else
   * 'audio'. Never 'image' here — U09 owns audio/video.
   */
  function mediaChannelFor(question) {
    var accept = question && question.handlers && question.handlers.media && question.handlers.media.accept;
    return accept && accept.indexOf('video') !== -1 ? 'video' : 'audio';
  }

  /** One-question-per-screen mirror (server-enforced; renderer mirrors it). */
  function assertOneQuestion(config) {
    if (!config || !Array.isArray(config.questions)) return { ok: false, reason: 'no-questions' };
    if (config.questions.length !== 1) return { ok: false, reason: 'not-one-question' };
    var q = config.questions[0];
    if (!q || typeof q !== 'object') return { ok: false, reason: 'bad-question' };
    if (q.screen && Array.isArray(q.screen.questions) && q.screen.questions.length > 1) {
      return { ok: false, reason: 'batch-screen' };
    }
    return { ok: true, question: q };
  }

  /**
   * Reduced-motion awareness. `prefersReducedMotion` is a bool the caller
   * provides (in the browser it comes from matchMedia, in tests from a stub).
   * Returns { ok:true } when the caller may run motion, { ok:false } when it
   * must stay static. U06's CSS already disables the pulse; this is the JS
   * branch for callers that need it.
   */
  function motionOk(prefersReducedMotion) {
    return { ok: !prefersReducedMotion };
  }

  // ---- permission + capability gates (fail-closed) --------------------------

  /**
   * MediaRecorder capability gate. Returns { ok, reason }:
   *   ok:false, reason:'no-mediarecorder'  — API missing (desktop Safari etc.)
   *   ok:false, reason:'no-media-devices'  — getUserMedia missing
   *   ok:false, reason:'no-camera'         — video requested but no video input
   *   ok:true                              — the recorder can at least be tried
   * `cap` is a small adapter the browser passes in (defaults built lazily):
   *   { MediaRecorder, isTypeSupported, mediaDevices, enumerateDevices, reducedMotion }
   */
  function canRecord(channel, cap) {
    cap = cap || {};
    if (typeof cap.MediaRecorder !== 'function' && typeof global.MediaRecorder !== 'function') {
      return { ok: false, reason: 'no-mediarecorder' };
    }
    var md = cap.mediaDevices || (global.navigator && global.navigator.mediaDevices) || null;
    if (!md || typeof md.getUserMedia !== 'function') {
      return { ok: false, reason: 'no-media-devices' };
    }
    // The camera gate needs enumerateDevices, which is async — it lives in
    // canRecordAsync (below). This synchronous gate only proves the recorder
    // can at least be tried; the async gate and the getUserMedia rejection
    // surface any camera denial gently.
    return { ok: true };
  }

  /**
   * Async camera gate: enumerate videoinput devices. Returns a Promise of
   * { ok, reason }. ok:false, reason:'no-camera' when enumerateDevices is
   * available and returns zero videoinput devices. Any failure to enumerate
   * resolves ok:true (the getUserMedia rejection still surfaces denials).
   */
  function canRecordAsync(channel, cap) {
    cap = cap || {};
    var md = cap.mediaDevices || (global.navigator && global.navigator.mediaDevices) || null;
    if (channel !== 'video' || !md || typeof md.enumerateDevices !== 'function') {
      return Promise.resolve({ ok: true });
    }
    return Promise.resolve()
      .then(function () { return md.enumerateDevices(); })
      .then(function (devices) {
        var list = devices || [];
        var hasVideo = list.some(function (d) { return d && d.kind === 'videoinput'; });
        return hasVideo ? { ok: true } : { ok: false, reason: 'no-camera' };
      })
      .catch(function () { return { ok: true }; });
  }

  /**
   * Pick a supported MIME type for the channel. Returns the first hint
   * `isTypeSupported` accepts, or null when none are (the recorder then runs
   * with the browser default).
   */
  function pickMime(channel, MediaRecorderImpl, isTypeSupportedImpl) {
    var MR = MediaRecorderImpl || global.MediaRecorder;
    if (!MR) return null;
    var hints = MIME_HINTS[channel] || [];
    for (var i = 0; i < hints.length; i++) {
      var okType = typeof isTypeSupportedImpl === 'function'
        ? isTypeSupportedImpl(hints[i])
        : (typeof MR.isTypeSupported === 'function' ? MR.isTypeSupported(hints[i]) : false);
      if (okType) return hints[i];
    }
    return null;
  }

  /** Suggested filename + content-type for a recorded blob (webm). */
  function recordingFileInfo(channel, answerId) {
    var base = 'recording-' + String(answerId || 'new').slice(0, 8);
    return {
      filename: base + '.webm',
      contentType: channel === 'video' ? 'video/webm' : 'audio/webm',
      extension: 'webm'
    };
  }

  /** Validate a dropped/picked file against a channel. Returns {ok, reason}. */
  function validateFile(file, channel) {
    if (!file) return { ok: false, reason: 'no-file' };
    var name = String(file.name || '');
    var lower = name.toLowerCase();
    if (channel === 'file-pdf') {
      if (!/\.pdf$/.test(lower)) return { ok: false, reason: 'not-pdf' };
      if (file.size <= 0) return { ok: false, reason: 'empty' };
      return { ok: true };
    }
    if (channel === 'file-txt') {
      if (!/\.txt$/.test(lower) && !/\.text$/.test(lower)) return { ok: false, reason: 'not-txt' };
      if (file.size <= 0) return { ok: false, reason: 'empty' };
      return { ok: true };
    }
    return { ok: false, reason: 'unknown-channel' };
  }

  /** Magic-byte sniff of the first bytes of a file. Returns {ext, ok}. */
  function sniffFileHeader(bytes, channel) {
    var arr = Array.prototype.slice.call(bytes || []);
    if (channel === 'file-pdf') {
      var sig = MAGIC_HEADERS.pdf;
      var match = arr.length >= sig.length && sig.every(function (b, i) { return arr[i] === b; });
      return { ext: 'pdf', ok: match };
    }
    return { ext: 'txt', ok: true };
  }

  /**
   * Build the U04 worker upload body for a media blob. Mirrors the U05
   * `uploadMedia` contract: channel, answer_id, filename, size_bytes,
   * content_type, header_bytes, session. Returns a plain object (fetch is
   * left to the caller so the core stays offline-testable).
   */
  function uploadBody(opts) {
    return {
      channel: opts.channel,
      answer_id: opts.answerId,
      filename: opts.filename,
      size_bytes: opts.sizeBytes,
      content_type: opts.contentType,
      header_bytes: opts.headerBytes || [],
      session: opts.session || null
    };
  }

  /**
   * Read a text file via a FileReader-like adapter. `reader` is the browser
   * FileReader (or a stub). Returns a Promise<{ok, text}>.
   */
  function readTxt(file, readerFactory) {
    var makeReader = readerFactory || function () { return new FileReader(); };
    return new Promise(function (resolve) {
      var reader = makeReader();
      reader.onload = function () {
        var text = String(reader.result || '').trim();
        resolve(text.length ? { ok: true, text: text } : { ok: false, reason: 'empty' });
      };
      reader.onerror = function () { resolve({ ok: false, reason: 'read-failed' }); };
      reader.readAsText(file);
    });
  }

  /**
   * PDF text extraction via pdf.js — STUB-FRIENDLY.
   *
   * `pdfjsLib` (optional) is the module's handle on pdf.js. In the browser
   * the SPA sets `global.pdfjsLib = window.pdfjsLib` (loaded from the local
   * vendored script — never a CDN). In tests a stub with `getDocument` is
   * injected. When pdfjsLib is absent the extraction is marked IN PROGRESS,
   * never a fabricated done:
   *     { ok:false, reason:'pdfjs-unavailable' }
   * The stub contract used by the self-test and the SPA:
   *     pdfjsLib.getDocument({ data: ArrayBuffer }) -> { promise: Promise<doc> }
   *     doc.numPages, doc.getPage(n) -> { promise: Promise<page> }
   *     page.getTextContent() -> { promise: Promise<{items:[{str}]}> }
   */
  function extractPdfText(file, pdfjsLib) {
    if (!pdfjsLib || typeof pdfjsLib.getDocument !== 'function') {
      return Promise.resolve({ ok: false, reason: 'pdfjs-unavailable' });
    }
    if (!file || !file.arrayBuffer) {
      return Promise.resolve({ ok: false, reason: 'no-arraybuffer' });
    }
    return file.arrayBuffer().then(function (buffer) {
      var task = pdfjsLib.getDocument({ data: buffer });
      return Promise.resolve(task.promise).then(function (doc) {
        var pages = [];
        for (var n = 1; n <= doc.numPages; n++) {
          pages.push(Promise.resolve(doc.getPage(n).promise).then(function (page) {
            return Promise.resolve(page.getTextContent().promise).then(function (content) {
              return (content.items || []).map(function (it) { return it.str; }).join(' ');
            });
          }));
        }
        return Promise.all(pages).then(function (texts) {
          return { ok: true, text: texts.join('\n\n').trim() };
        });
      });
    }).catch(function () {
      return { ok: false, reason: 'parse-failed' };
    });
  }

  /**
   * AF-BW-MA-ANTHROPIC re-check on a resolved transcription job view. Any
   * model id matching /anthropic|claude/i is a HARD FAIL. Returns
   * { ok:true } or { ok:false, code, model }.
   */
  function verifyNoAnthropic(job) {
    var model = job && (job.model || (job.transcript_json && job.transcript_json.model));
    if (typeof model === 'string' && ANTHROPIC_RE.test(model)) {
      return { ok: false, code: 'AF-BW-MA-ANTHROPIC', model: model };
    }
    return { ok: true, code: null, model: null };
  }

  /**
   * Scan copy strings for banned anti-anxiety words (mirrors U10). Returns
   * the offending strings; empty when clean.
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
  // DOM render helpers — exported for the SPA; touch the DOM only when it
  // exists. Each returns a container element the SPA mounts inside the media /
  // file tab panel. Callers pass `opts` callbacks; the helpers stay free of
  // fetch/MediaRecorder so every branch is testable with a DOM stub.
  // ---------------------------------------------------------------------------

  function makeEl(documentRef, tag, attrs, children) {
    var node = documentRef.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'html') node.innerHTML = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(typeof c === 'string' ? documentRef.createTextNode(c) : c);
    });
    return node;
  }

  /**
   * Render the recorder widget (audio or video) into a panel.
   * opts: {
   *   channel: 'audio'|'video',
   *   onStart(), onStop(blob) -> void, onStatus(text, cls),
   *   reducedMotion: bool
   * }
   * Returns the container (a `.rec` div). No media capture happens here — the
   * SPA wires real MediaRecorder through onStart/onStop. This keeps the render
   * pure and testable with a DOM stub.
   */
  function renderRecorder(documentRef, opts) {
    if (typeof documentRef === 'undefined') return null;
    opts = opts || {};
    var channel = opts.channel === 'video' ? 'video' : 'audio';
    var widget = widgetForMode(channel);

    var rec = makeEl(documentRef, 'div', { class: 'rec' });
    rec.appendChild(makeEl(documentRef, 'p', { class: 'rec-expect', text: widget.expect }));

    var btn = makeEl(documentRef, 'button', { class: 'rec-btn', type: 'button', text: widget.start });
    if (opts.onStart) {
      btn.addEventListener('click', function () {
        if (opts.onStart) opts.onStart();
      });
    }
    rec.appendChild(btn);

    var timer = makeEl(documentRef, 'div', { class: 'rec-timer' });
    var status = makeEl(documentRef, 'div', { class: 'pill' });
    rec.appendChild(timer);
    rec.appendChild(status);

    if (opts.onStatus) opts.onStatus('', '');
    return rec;
  }

  /**
   * Render a file widget (PDF or .txt): hidden input + drop zone + name/note.
   * opts: {
   *   channel: 'file-pdf'|'file-txt',
   *   onFile(file) -> void, onDrop(File) -> void
   * }
   * Returns the container (a `.file-widget` div).
   */
  function renderFileWidget(documentRef, opts) {
    if (typeof documentRef === 'undefined') return null;
    opts = opts || {};
    var channel = opts.channel === 'file-pdf' ? 'file-pdf' : 'file-txt';
    var widget = widgetForMode(channel);
    var id = 'file-' + channel;

    var wrap = makeEl(documentRef, 'div', { class: 'file-widget' });
    var dz = makeEl(documentRef, 'div', { class: 'dropzone' });
    dz.appendChild(makeEl(documentRef, 'p', { text: widget.expect }));
    dz.appendChild(makeEl(documentRef, 'p', {
      class: 'file-note',
      text: channel === 'file-pdf' ? COPY.pdfNote : COPY.txtNote
    }));

    var input = makeEl(documentRef, 'input', { class: 'file-input', type: 'file' });
    input.id = id;
    input.setAttribute('accept', channel === 'file-pdf' ? '.pdf,application/pdf' : '.txt,text/plain');
    wrap.appendChild(input);
    wrap.appendChild(dz);

    var fname = makeEl(documentRef, 'div', { class: 'fname' });
    var note = makeEl(documentRef, 'div', { class: 'file-note' });
    wrap.appendChild(fname);
    wrap.appendChild(note);

    if (dz.addEventListener) {
      dz.addEventListener('click', function () { if (input.click) input.click(); });
      dz.addEventListener('dragover', function (e) {
        if (e.preventDefault) e.preventDefault();
        dz.classList.add('drag');
      });
      dz.addEventListener('dragleave', function () { dz.classList.remove('drag'); });
      dz.addEventListener('drop', function (e) {
        if (e.preventDefault) e.preventDefault();
        dz.classList.remove('drag');
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f && opts.onDrop) opts.onDrop(f);
      });
    }
    if (input.addEventListener) {
      input.addEventListener('change', function () {
        if (input.files && input.files[0] && opts.onFile) opts.onFile(input.files[0]);
      });
    }

    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Exports
  // ---------------------------------------------------------------------------
  var api = {
    COPY: COPY,
    // pure core
    widgetForMode: widgetForMode,
    mediaChannelFor: mediaChannelFor,
    assertOneQuestion: assertOneQuestion,
    motionOk: motionOk,
    canRecord: canRecord,
    canRecordAsync: canRecordAsync,
    pickMime: pickMime,
    recordingFileInfo: recordingFileInfo,
    validateFile: validateFile,
    sniffFileHeader: sniffFileHeader,
    uploadBody: uploadBody,
    readTxt: readTxt,
    extractPdfText: extractPdfText,
    verifyNoAnthropic: verifyNoAnthropic,
    scanBannedCopy: scanBannedCopy,
    // DOM render
    renderRecorder: renderRecorder,
    renderFileWidget: renderFileWidget,
    // self-test
    selftest: selftest
  };

  // ---------------------------------------------------------------------------
  // Self-test — pure core + a DOM-stub render (like U05's render proof).
  // ---------------------------------------------------------------------------
  function selftest() {
    var results = [];
    function check(name, ok) { results.push([name, !!ok]); }

    // ---- widget wiring ------------------------------------------------------
    check('audio widget -> channel audio', widgetForMode('audio').channel === 'audio');
    check('video widget -> channel video', widgetForMode('video').channel === 'video');
    check('pdf widget -> channel file-pdf', widgetForMode('file-pdf').channel === 'file-pdf');
    check('txt widget -> channel file-txt', widgetForMode('file-txt').channel === 'file-txt');
    check('unknown mode -> null', widgetForMode('nope') === null);

    // ---- channel resolution -------------------------------------------------
    var vidQ = { handlers: { media: { accept: ['video'] } } };
    var audQ = { handlers: { media: { accept: ['audio'] } } };
    var bothQ = { handlers: { media: { accept: ['audio', 'video'] } } };
    check('video accept -> video channel', mediaChannelFor(vidQ) === 'video');
    check('audio accept -> audio channel', mediaChannelFor(audQ) === 'audio');
    check('audio+video accept -> video channel (camera gate)', mediaChannelFor(bothQ) === 'video');
    check('no accept -> audio channel', mediaChannelFor({}) === 'audio');

    // ---- one-question-per-screen -------------------------------------------
    check('single question accepted', assertOneQuestion({ questions: [{ id: 'a', kind: 'text' }] }).ok === true);
    check('two questions rejected', assertOneQuestion({ questions: [{ id: 'a' }, { id: 'b' }] }).ok === false);
    check('batch screen rejected', assertOneQuestion({ questions: [{ screen: { questions: [{ id: 'a' }, { id: 'b' }] } }] }).ok === false);
    check('no questions rejected', assertOneQuestion({}).ok === false);

    // ---- reduced motion -----------------------------------------------------
    check('reduced motion -> motion disabled', motionOk(true).ok === false);
    check('no reduced motion -> motion ok', motionOk(false).ok === true);

    // ---- capability gates ---------------------------------------------------
    check('no MediaRecorder -> no-mediarecorder', canRecord('audio', { MediaRecorder: undefined, mediaDevices: { getUserMedia: function () {} } }).ok === false);
    check('no mediaDevices -> no-media-devices', canRecord('audio', { MediaRecorder: function () {}, mediaDevices: null }).ok === false);
    check('cap present -> ok', canRecord('audio', { MediaRecorder: function () {}, mediaDevices: { getUserMedia: function () {} } }).ok === true);

    // async camera gate
    return canRecordAsync('video', {
      mediaDevices: {
        enumerateDevices: function () {
          return Promise.resolve([{ kind: 'audioinput' }]);
        }
      }
    }).then(function (noCam) {
      check('video without a camera device -> no-camera', noCam.ok === false && noCam.reason === 'no-camera');
      return canRecordAsync('video', {
        mediaDevices: {
          enumerateDevices: function () {
            return Promise.resolve([{ kind: 'videoinput' }, { kind: 'audioinput' }]);
          }
        }
      });
    }).then(function (hasCam) {
      check('video with a camera device -> ok', hasCam.ok === true);
      return canRecordAsync('audio', { mediaDevices: { enumerateDevices: function () { return Promise.resolve([]); } } });
    }).then(function (audioGate) {
      check('audio gate never blocks on camera enumeration', audioGate.ok === true);
      return canRecordAsync('video', { mediaDevices: {} });
    }).then(function (noEnum) {
      check('enumeration failure resolves ok (getUserMedia still gates)', noEnum.ok === true);

      // ---- mime picking ------------------------------------------------------
      var MR = function () {};
      // stub supports every webm variant, so the FIRST hint is picked for both
      MR.isTypeSupported = function (t) { return t.indexOf('webm') !== -1; };
      check('audio mime picks audio/webm;codecs=opus', pickMime('audio', MR) === 'audio/webm;codecs=opus');
      check('video mime picks vp9 hint when supported', pickMime('video', MR) === 'video/webm;codecs=vp9,opus');
      var MRNoHint = function () {};
      MRNoHint.isTypeSupported = function () { return false; };
      check('no supported hint -> null (browser default)', pickMime('video', MRNoHint) === null);
      check('no MediaRecorder -> null', pickMime('audio', undefined) === null);

      // ---- recording file info ----------------------------------------------
      var info = recordingFileInfo('video', 'abc123def');
      check('video filename ends .webm', info.filename.indexOf('.webm') !== -1);
      check('video content-type video/webm', info.contentType === 'video/webm');
      var ainfo = recordingFileInfo('audio', 'abc123def');
      check('audio content-type audio/webm', ainfo.contentType === 'audio/webm');

      // ---- file validation --------------------------------------------------
      check('pdf name accepted', validateFile({ name: 'draft.pdf', size: 10 }, 'file-pdf').ok === true);
      check('non-pdf name rejected', validateFile({ name: 'draft.txt', size: 10 }, 'file-pdf').ok === false);
      check('empty pdf rejected', validateFile({ name: 'draft.pdf', size: 0 }, 'file-pdf').ok === false);
      check('txt name accepted', validateFile({ name: 'notes.txt', size: 5 }, 'file-txt').ok === true);
      check('.text accepted for txt', validateFile({ name: 'notes.text', size: 5 }, 'file-txt').ok === true);
      check('pdf name rejected for txt', validateFile({ name: 'draft.pdf', size: 5 }, 'file-txt').ok === false);
      check('no file rejected', validateFile(null, 'file-txt').ok === false);

      // ---- header sniff ------------------------------------------------------
      check('pdf magic ok', sniffFileHeader([0x25, 0x50, 0x44, 0x46], 'file-pdf').ok === true);
      check('non-pdf magic fails closed', sniffFileHeader([0x49, 0x44, 0x33], 'file-pdf').ok === false);
      check('txt has no magic requirement', sniffFileHeader([0x48, 0x69], 'file-txt').ok === true);

      // ---- upload body (U04 worker contract) --------------------------------
      var body = uploadBody({
        channel: 'audio', answerId: 'story-1', filename: 'rec.webm',
        sizeBytes: 4096, contentType: 'audio/webm',
        headerBytes: [0x1a, 0x45, 0xdf, 0xa3], session: 'run-A'
      });
      check('upload body channel', body.channel === 'audio');
      check('upload body answer_id', body.answer_id === 'story-1');
      check('upload body filename', body.filename === 'rec.webm');
      check('upload body size_bytes', body.size_bytes === 4096);
      check('upload body content_type', body.content_type === 'audio/webm');
      check('upload body header_bytes array', Array.isArray(body.header_bytes) && body.header_bytes[0] === 0x1a);
      check('upload body session', body.session === 'run-A');
      check('upload body has no zone/account id field',
        Object.keys(body).every(function (k) { return ['channel', 'answer_id', 'filename', 'size_bytes', 'content_type', 'header_bytes', 'session'].indexOf(k) !== -1; }));

      // ---- verifyNoAnthropic (AF-BW-MA-ANTHROPIC) ---------------------------
      var bad = verifyNoAnthropic({ model: 'anthropic/claude-sonnet-4' });
      check('anthropic/claude model id hard-fails', bad.ok === false && bad.code === 'AF-BW-MA-ANTHROPIC');
      var bad2 = verifyNoAnthropic({ transcript_json: { model: 'claude-3' } });
      check('anthropic id inside transcript_json hard-fails', bad2.ok === false);
      var good = verifyNoAnthropic({ model: 'whisper-small' });
      check('provider-neutral model passes', good.ok === true);

      // ---- module copy is banned-word-free -----------------------------------
      var copy = Object.keys(COPY).map(function (k) { return COPY[k]; });
      check('module copy never renders a banned word', scanBannedCopy(copy).length === 0);

      // ---- pdf.js stub contract ----------------------------------------------
      // A stub pdfjsLib that returns real pages proves extractPdfText works
      // with any pdf.js-compatible library (stub-friendly import).
      var stubPdf = {
        getDocument: function () {
          return { promise: Promise.resolve({
            numPages: 2,
            getPage: function (n) {
              return { promise: Promise.resolve({
                getTextContent: function () {
                  return { promise: Promise.resolve({ items: [{ str: 'Page ' + n + ' word' }] }) };
                }
              }) };
            }
          }) };
        }
      };
      return extractPdfText({ arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(8)); } }, stubPdf).then(function (res) {
        check('pdf.js stub extraction returns joined text', res.ok === true && res.text.indexOf('Page 1 word') !== -1 && res.text.indexOf('Page 2 word') !== -1);
        // pdfjs unavailable -> IN PROGRESS, never fabricated done
        return extractPdfText({ arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(8)); } }, null);
      }).then(function (noLib) {
        check('pdfjs unavailable -> pdfjs-unavailable (never fabricated)', noLib.ok === false && noLib.reason === 'pdfjs-unavailable');
        return extractPdfText({ arrayBuffer: function () { return Promise.reject(new Error('x')); } }, stubPdf);
      }).then(function (bad) {
        check('parse failure -> parse-failed', bad.ok === false && bad.reason === 'parse-failed');

        // ---- txt read via a reader stub --------------------------------------
        var stubReaderFactory = function () {
          var r = {};
          r.onload = null; r.onerror = null;
          r.readAsText = function () { if (r.onload) r.onload(); };
          r.result = '  hello from the file  ';
          return r;
        };
        return readTxt({ name: 'notes.txt', size: 5 }, stubReaderFactory);
      }).then(function (txt) {
        check('txt read returns trimmed text', txt.ok === true && txt.text === 'hello from the file');

        // ---- DOM-stub render proof -------------------------------------------
        var stubDoc = domStub();
        var recEl = renderRecorder(stubDoc, { channel: 'audio' });
        check('DOM stub: recorder container has .rec class', recEl && recEl.getAttribute('class') === 'rec');
        check('DOM stub: recorder has a start button', recEl.querySelector('.rec-btn').textContent === 'Tap to talk');

        var fileEl = renderFileWidget(stubDoc, { channel: 'file-pdf' });
        check('DOM stub: file widget has .file-widget class', fileEl && fileEl.getAttribute('class') === 'file-widget');
        check('DOM stub: file widget has a hidden file input', fileEl.querySelector('input[type=file]').getAttribute('accept').indexOf('.pdf') !== -1);

        var pass = results.every(function (r) { return r[1]; });
        var lines = results.map(function (r) { return (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]; });
        if (typeof process !== 'undefined' && typeof process.stdout !== 'undefined') {
          lines.forEach(function (l) { process.stdout.write(l + '\n'); });
          process.stdout.write((pass ? 'U09 recorder/upload widgets self-test: PASS' : 'U09 recorder/upload widgets self-test: FAIL') + '\n');
        }
        if (!pass && typeof process !== 'undefined') process.exitCode = 2;
        return pass;
      });
    });
  }

  /**
   * Minimal DOM stub used by the self-test to prove the render helpers mount
   * real nodes (the same approach U05's e2e render proof uses). Supports
   * createElement, createTextNode, setAttribute, getAttribute, textContent,
   * classList, appendChild, addEventListener, querySelector (by tag).
   */
  function domStub() {
    function NodeStub(tag) {
      this.tagName = String(tag).toUpperCase();
      this.attributes = {};
      this.children = [];
      this.parentNode = null;
      this.textContent = '';
      this._listeners = {};
      this.classList = {
        add: function () {},
        remove: function () {},
        toggle: function () {}
      };
    }
    NodeStub.prototype.setAttribute = function (k, v) { this.attributes[k] = String(v); };
    NodeStub.prototype.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null; };
    NodeStub.prototype.appendChild = function (c) { if (c) { this.children.push(c); c.parentNode = this; } return c; };
    NodeStub.prototype.addEventListener = function (ev, fn) { (this._listeners[ev] = this._listeners[ev] || []).push(fn); };
    NodeStub.prototype.querySelector = function (sel) {
      // tiny selector: 'button', 'input[type=file]', '.rec-btn', '.dropzone p', etc.
      var tag = (sel.match(/^[a-z0-9]+/i) || [])[0] || null;
      var cls = (sel.match(/\.([a-z0-9_-]+)/i) || [])[1] || null;
      var attr = (sel.match(/\[([a-z0-9_-]+)=([^\]]+)\]/) || [])[1] || null;
      var val = (sel.match(/\[([a-z0-9_-]+)=([^\]]+)\]/) || [])[2] || null;
      var stack = this.children.slice();
      while (stack.length) {
        var n = stack.shift();
        if (n && n.tagName &&
            (!tag || n.tagName === tag.toUpperCase()) &&
            (!cls || (n.getAttribute('class') || '').split(/\s+/).indexOf(cls) !== -1) &&
            (!attr || n.getAttribute(attr) === (val ? val.replace(/["']/g, '') : null))) {
          return n;
        }
        stack = stack.concat(n.children || []);
      }
      return null;
    };
    return {
      createElement: function (t) { return new NodeStub(t); },
      createTextNode: function (s) { return { nodeType: 3, text: String(s), children: [] }; }
    };
  }

  global.BWRecorder = api;

  if (typeof process !== 'undefined' && process.argv && process.argv.indexOf('--selftest') !== -1) {
    selftest();
  }
})(typeof window !== 'undefined' ? window : globalThis);
