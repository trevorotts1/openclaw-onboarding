/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U09 — RECORDER / UPLOAD WIDGETS SELF-TEST
 * -----------------------------------------------------------------------------
 * Standalone .mjs runner for the U09 self-test. Loads recorder.js (a UMD-ish
 * module that mounts on globalThis under node) and runs its selftest().
 *
 * The selftest exercises:
 *   - the pure core (widget wiring, channel resolution, one-question-per-screen,
 *     reduced-motion, capability + camera gates, MIME picking, file validation,
 *     magic-byte sniff, the U04 upload-body contract, txt/PDF extraction incl.
 *     the stub-friendly pdf.js import, the AF-BW-MA-ANTHROPIC re-check, and
 *     banned-word-free copy)
 *   - a DOM-stub render proof (mounts the recorder + file widgets against a
 *     minimal document stub, exactly like U05's e2e DOM-stub render)
 *
 * Exit 0 = PASS, exit 2 = FAIL.
 * ============================================================================= */
'use strict';

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Load recorder.js into globalThis (it self-registers as global.BWRecorder and
// runs selftest() only when --selftest is present, which it is not here).
await import(join(__dirname, 'recorder.js'));

const api = globalThis.BWRecorder;
if (!api || typeof api.selftest !== 'function') {
  process.stdout.write('U09 recorder/upload widgets self-test: FAIL (module did not register global.BWRecorder)\n');
  process.exit(2);
}

const pass = await api.selftest();
process.exit(pass ? 0 : 2);
