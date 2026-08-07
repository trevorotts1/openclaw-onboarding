# Book Writer Mini-App — Recorder / Upload widgets (U09)

Wave B, unit U09 of the Book Writer Mini-App Gauntlet. Owns the
**recorder + upload widget layer** from MASTER-PLAN section 9: MediaRecorder
audio/video capture with permission + camera gates, PDF/.txt file pickers, and
a pdf.js-based PDF preview whose import is stub-friendly.

## What it does

`recorder.js` is a self-contained, dependency-free module (pure core has no DOM,
no fetch, no media capture of its own — callers pass adapters). The SPA
(U05/U10) mounts its render helpers inside the media / file tab panels.

1. **MediaRecorder audio + video with gates.** The microphone/camera are
   requested ONLY on a deliberate tap. `canRecord` / `canRecordAsync` are the
   fail-closed capability + camera gates: a denied, unavailable, or
   not-supported capture surfaces a warm message and the typing path — never a
   silent blank, never a surprise permission prompt. `pickMime` picks the first
   supported webm MIME hint (falling back to the browser default).
2. **PDF + .txt pickers.** Drop zone + hidden file input per channel, with
   magic-byte sniff that agrees with the worker's hard REJECT-FORMAT gate and
   size checks. `.txt` rides the FileReader path; `.pdf` rides pdf.js.
3. **pdf.js preview, stub-friendly.** The module never statically imports
   pdf.js, so it runs offline and under node. The SPA injects
   `global.pdfjsLib` (loaded from a local vendored script — never a CDN); when
   the library is absent, PDF extraction is marked IN PROGRESS (`pdfjs-
   unavailable`), never a fabricated done, and the warm typing path is offered.
   The self-test proves `extractPdfText` against a stub pdf.js implementation.
4. **Upload wired to the U04 worker contract.** `uploadBody` builds exactly the
   POST `/api/media/upload` body (channel, answer_id, filename, size_bytes,
   content_type, header_bytes, session) → presigned DIRECT R2 PUT → poll, as the
   U05 renderer core wires it. PDF/.txt ride the text path — the file itself is
   never uploaded.

## Constraints (fail-closed)

- **NO Anthropic id anywhere** (AF-BW-MA-ANTHROPIC). `verifyNoAnthropic`
  re-checks any resolved transcription job view — an anthropic/claude model id
  is a hard fail, never a silent fallback.
- **NO {{...}} placeholders** in shipped code.
- **NO real zone/account id.** The upload body carries no such field (the
  self-test asserts the exact key set).
- **Provider-neutral**: no model providers named.
- One-question-per-screen (U05) and reduced-motion (U06) are respected.

## Files

- `recorder.js` — the module: pure core + DOM render helpers
  (`renderRecorder`, `renderFileWidget`) + `--selftest` (62 assertions).
- `recorder.selftest.mjs` — standalone runner: `node recorder.selftest.mjs`
  (exit 0 = pass, exit 2 = fail).
- `recorder.test.mjs` — the same suite under `node --test` (16 tests).
- `README-U09-RECORDER.md` — this file.

## Gate

```sh
cd 53-book-writer/mini-app/pages
node recorder.selftest.mjs
node --test recorder.test.mjs
node -c recorder.js
```

Self-test exit 0 = pass; exit 2 = fail. The worker regression suite stays
green: `cd ../worker && node --test src/*.test.mjs` (90/90).
