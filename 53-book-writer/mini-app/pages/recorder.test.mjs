/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U09 — RECORDER / UPLOAD WIDGETS
 * node --test suite
 * -----------------------------------------------------------------------------
 * Runs the U09 pure-core + DOM-stub render assertions under `node --test`,
 * mirroring the module's `--selftest`. Exit 0 = all pass.
 *
 *   node --test pages/recorder.test.mjs
 * ============================================================================= */
'use strict';

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
await import(join(__dirname, 'recorder.js'));
const BW = globalThis.BWRecorder;

test('widget wiring resolves channel + start label per mode', () => {
  assert.equal(BW.widgetForMode('audio').channel, 'audio');
  assert.equal(BW.widgetForMode('video').channel, 'video');
  assert.equal(BW.widgetForMode('file-pdf').channel, 'file-pdf');
  assert.equal(BW.widgetForMode('file-txt').channel, 'file-txt');
  assert.equal(BW.widgetForMode('nope'), null);
});

test('media accept resolves to video (camera gate) or audio', () => {
  assert.equal(BW.mediaChannelFor({ handlers: { media: { accept: ['video'] } } }), 'video');
  assert.equal(BW.mediaChannelFor({ handlers: { media: { accept: ['audio'] } } }), 'audio');
  assert.equal(BW.mediaChannelFor({ handlers: { media: { accept: ['audio', 'video'] } } }), 'video');
  assert.equal(BW.mediaChannelFor({}), 'audio');
});

test('one-question-per-screen is enforced', () => {
  assert.equal(BW.assertOneQuestion({ questions: [{ id: 'a' }] }).ok, true);
  assert.equal(BW.assertOneQuestion({ questions: [{ id: 'a' }, { id: 'b' }] }).ok, false);
  assert.equal(BW.assertOneQuestion({ questions: [{ screen: { questions: [{ id: 'a' }, { id: 'b' }] } }] }).ok, false);
  assert.equal(BW.assertOneQuestion({}).ok, false);
});

test('reduced-motion branch is respected', () => {
  assert.equal(BW.motionOk(true).ok, false);
  assert.equal(BW.motionOk(false).ok, true);
});

test('capability gates fail closed', () => {
  assert.equal(BW.canRecord('audio', { MediaRecorder: undefined, mediaDevices: { getUserMedia() {} } }).reason, 'no-mediarecorder');
  assert.equal(BW.canRecord('audio', { MediaRecorder: function () {}, mediaDevices: null }).reason, 'no-media-devices');
  assert.equal(BW.canRecord('audio', { MediaRecorder: function () {}, mediaDevices: { getUserMedia() {} } }).ok, true);
});

test('async camera gate detects missing video input', async () => {
  const noCam = await BW.canRecordAsync('video', {
    mediaDevices: { enumerateDevices: () => Promise.resolve([{ kind: 'audioinput' }]) }
  });
  assert.equal(noCam.ok, false);
  assert.equal(noCam.reason, 'no-camera');

  const hasCam = await BW.canRecordAsync('video', {
    mediaDevices: { enumerateDevices: () => Promise.resolve([{ kind: 'videoinput' }]) }
  });
  assert.equal(hasCam.ok, true);

  const audioGate = await BW.canRecordAsync('audio', {
    mediaDevices: { enumerateDevices: () => Promise.resolve([]) }
  });
  assert.equal(audioGate.ok, true);

  const noEnum = await BW.canRecordAsync('video', { mediaDevices: {} });
  assert.equal(noEnum.ok, true);
});

test('MIME picking prefers the first supported hint, null fallback', () => {
  const MR = function () {};
  MR.isTypeSupported = (t) => t.indexOf('webm') !== -1;
  assert.equal(BW.pickMime('audio', MR), 'audio/webm;codecs=opus');
  assert.equal(BW.pickMime('video', MR), 'video/webm;codecs=vp9,opus');
  const none = function () {};
  none.isTypeSupported = () => false;
  assert.equal(BW.pickMime('video', none), null);
  assert.equal(BW.pickMime('audio', undefined), null);
});

test('recording file info names a webm blob', () => {
  assert.ok(BW.recordingFileInfo('video', 'abc123').filename.endsWith('.webm'));
  assert.equal(BW.recordingFileInfo('video', 'abc123').contentType, 'video/webm');
  assert.equal(BW.recordingFileInfo('audio', 'abc123').contentType, 'audio/webm');
});

test('file validation rejects wrong / empty types', () => {
  assert.equal(BW.validateFile({ name: 'draft.pdf', size: 10 }, 'file-pdf').ok, true);
  assert.equal(BW.validateFile({ name: 'draft.txt', size: 10 }, 'file-pdf').ok, false);
  assert.equal(BW.validateFile({ name: 'draft.pdf', size: 0 }, 'file-pdf').ok, false);
  assert.equal(BW.validateFile({ name: 'notes.txt', size: 5 }, 'file-txt').ok, true);
  assert.equal(BW.validateFile({ name: 'notes.text', size: 5 }, 'file-txt').ok, true);
  assert.equal(BW.validateFile({ name: 'draft.pdf', size: 5 }, 'file-txt').ok, false);
  assert.equal(BW.validateFile(null, 'file-txt').ok, false);
});

test('magic-byte sniff agrees with the worker gate', () => {
  assert.equal(BW.sniffFileHeader([0x25, 0x50, 0x44, 0x46], 'file-pdf').ok, true);
  assert.equal(BW.sniffFileHeader([0x49, 0x44, 0x33], 'file-pdf').ok, false);
  assert.equal(BW.sniffFileHeader([0x48, 0x69], 'file-txt').ok, true);
});

test('upload body matches the U04 worker POST contract and carries no id fields', () => {
  const body = BW.uploadBody({
    channel: 'audio', answerId: 'story-1', filename: 'rec.webm',
    sizeBytes: 4096, contentType: 'audio/webm',
    headerBytes: [0x1a, 0x45, 0xdf, 0xa3], session: 'run-A'
  });
  assert.deepEqual(body, {
    channel: 'audio', answer_id: 'story-1', filename: 'rec.webm',
    size_bytes: 4096, content_type: 'audio/webm',
    header_bytes: [0x1a, 0x45, 0xdf, 0xa3], session: 'run-A'
  });
});

test('verifyNoAnthropic hard-fails any anthropic/claude model id', () => {
  assert.equal(BW.verifyNoAnthropic({ model: 'anthropic/claude-sonnet-4' }).ok, false);
  assert.equal(BW.verifyNoAnthropic({ transcript_json: { model: 'claude-3' } }).ok, false);
  assert.equal(BW.verifyNoAnthropic({ model: 'whisper-small' }).ok, true);
});

test('module copy never renders a banned anti-anxiety word', () => {
  const copy = Object.keys(BW.COPY).map((k) => BW.COPY[k]);
  assert.equal(BW.scanBannedCopy(copy).length, 0);
});

test('pdf.js extraction works against a stub (stub-friendly import)', async () => {
  const stubPdf = {
    getDocument: () => ({ promise: Promise.resolve({
      numPages: 2,
      getPage: (n) => ({ promise: Promise.resolve({
        getTextContent: () => ({ promise: Promise.resolve({ items: [{ str: 'Page ' + n + ' word' }] }) })
      }) })
    }) })
  };
  const ok = await BW.extractPdfText({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) }, stubPdf);
  assert.equal(ok.ok, true);
  assert.ok(ok.text.includes('Page 1 word') && ok.text.includes('Page 2 word'));

  const noLib = await BW.extractPdfText({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) }, null);
  assert.equal(noLib.ok, false);
  assert.equal(noLib.reason, 'pdfjs-unavailable');

  const bad = await BW.extractPdfText({ arrayBuffer: () => Promise.reject(new Error('x')) }, stubPdf);
  assert.equal(bad.ok, false);
  assert.equal(bad.reason, 'parse-failed');
});

test('txt read returns trimmed text via a reader stub', async () => {
  const stubReaderFactory = () => {
    const r = {};
    r.onload = null;
    r.readAsText = () => r.onload();
    r.result = '  hello from the file  ';
    return r;
  };
  const res = await BW.readTxt({ name: 'notes.txt', size: 5 }, stubReaderFactory);
  assert.equal(res.ok, true);
  assert.equal(res.text, 'hello from the file');
});

test('DOM-stub render mounts the recorder and file widgets', () => {
  const stubDoc = domStub();
  const recEl = BW.renderRecorder(stubDoc, { channel: 'audio' });
  assert.equal(recEl.getAttribute('class'), 'rec');
  assert.equal(recEl.querySelector('.rec-btn').textContent, 'Tap to talk');

  const fileEl = BW.renderFileWidget(stubDoc, { channel: 'file-pdf' });
  assert.equal(fileEl.getAttribute('class'), 'file-widget');
  assert.ok(fileEl.querySelector('input[type=file]').getAttribute('accept').includes('.pdf'));
});

// Minimal DOM stub mirroring the one inside recorder.js (used to prove the
// render helpers mount real nodes without a browser).
function domStub() {
  function NodeStub(tag) {
    this.tagName = String(tag).toUpperCase();
    this.attributes = {};
    this.children = [];
    this.textContent = '';
    this.classList = { add() {}, remove() {}, toggle() {} };
    this._listeners = {};
  }
  NodeStub.prototype.setAttribute = function (k, v) { this.attributes[k] = String(v); };
  NodeStub.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null;
  };
  NodeStub.prototype.appendChild = function (c) { if (c) { this.children.push(c); c.parentNode = this; } return c; };
  NodeStub.prototype.addEventListener = function (ev, fn) {
    (this._listeners[ev] = this._listeners[ev] || []).push(fn);
  };
  NodeStub.prototype.querySelector = function (sel) {
    const tag = (sel.match(/^[a-z0-9]+/i) || [null])[0];
    const cls = (sel.match(/\.([a-z0-9_-]+)/i) || [])[1] || null;
    const attr = (sel.match(/\[([a-z0-9_-]+)=([^\]]+)\]/) || [])[1] || null;
    const val = (sel.match(/\[([a-z0-9_-]+)=([^\]]+)\]/) || [])[2] || null;
    let stack = this.children.slice();
    while (stack.length) {
      const n = stack.shift();
      if (n && n.tagName &&
          (!tag || n.tagName === tag.toUpperCase()) &&
          (!cls || (n.getAttribute('class') || '').split(/\s+/).includes(cls)) &&
          (!attr || n.getAttribute(attr) === (val ? val.replace(/["']/g, '') : null))) {
        return n;
      }
      stack = stack.concat(n.children || []);
    }
    return null;
  };
  return {
    createElement: (t) => new NodeStub(t),
    createTextNode: (s) => ({ nodeType: 3, text: String(s), children: [] })
  };
}
