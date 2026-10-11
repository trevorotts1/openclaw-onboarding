/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN
 * prove/prove_qr_against_apple.mjs
 * -----------------------------------------------------------------------------
 * lib/qr.js is compared MODULE FOR MODULE against an implementation nobody in
 * this repo wrote: Apple's own CIQRCodeGenerator (CoreImage), reached through a
 * small Swift program this prover compiles on the spot. A decoder written in
 * the same file as the encoder can only prove the encoder agrees with itself;
 * this is the check that says the squares actually scan.
 *
 * The comparison payloads are deliberately BYTE-MODE-ONLY strings (no run of
 * digits or capitals), because a conformant encoder is free to split a message
 * into segments — Apple encodes "ABCD-2345" in ALPHANUMERIC mode, which is a
 * different but equally valid QR of the same text. That is a difference in
 * encoder choice, not a defect, and this prover does not hide it: the pairing
 * code's own matrix is proved instead by decoding it back in test/pairing.test.mjs.
 *
 *   exit 0 = every case matched Apple's matrix exactly
 *   exit 2 = a named case differed
 *   exit 3 = the prover could not run (no Swift toolchain, a compile failure)
 * ========================================================================== */

'use strict';

import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const PAIRING_DIR = dirname(HERE);

const SWIFT = `
import CoreImage
import CoreGraphics
import Foundation

let args = CommandLine.arguments
guard args.count >= 2 else { FileHandle.standardError.write("usage: qrgen <text> [L|M|Q|H]\\n".data(using: .utf8)!); exit(3) }
let text = args[1]
let level = args.count > 2 ? args[2] : "M"
guard let filter = CIFilter(name: "CIQRCodeGenerator") else { exit(3) }
filter.setValue(Data(text.utf8), forKey: "inputMessage")
filter.setValue(level, forKey: "inputCorrectionLevel")
guard let out = filter.outputImage else { exit(3) }
let ctx = CIContext()
guard let cg = ctx.createCGImage(out, from: out.extent) else { exit(3) }
let w = cg.width, h = cg.height
guard w > 0, h > 0, w == h else { exit(3) }
var buf = [UInt8](repeating: 0, count: w * h)
guard let g = CGContext(data: &buf, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                        space: CGColorSpaceCreateDeviceGray(),
                        bitmapInfo: CGImageAlphaInfo.none.rawValue) else { exit(3) }
g.interpolationQuality = .none
g.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
var lines = ["SIZE \\(w)"]
for y in 0..<h { var line = ""; for x in 0..<w { line.append(buf[y * w + x] < 128 ? "1" : "0") }; lines.append(line) }
print(lines.joined(separator: "\\n"))
exit(0)
`;

// Byte-mode-only payloads: nothing here gives a conformant encoder the option
// to split the message, so a correct encoder must produce the identical matrix.
const CASES = [
  ['abcdefgh', 'L'], ['abcdefgh', 'M'], ['abcdefgh', 'Q'], ['abcdefgh', 'H'],
  ['abcdefghijklmnop', 'L'], ['abcdefghijklmnop', 'M'], ['abcdefghijklmnop', 'Q'], ['abcdefghijklmnop', 'H'],
  ['pairing-code-xyz', 'L'], ['pairing-code-xyz', 'M'], ['pairing-code-xyz', 'Q'], ['pairing-code-xyz', 'H'],
  ['a', 'L'], ['zzzzzzzzzzzzzzzzzzzzzzzzzzzz', 'M'],
];

const results = [];
function check(id, ok, detail) {
  results.push(ok);
  process.stdout.write((ok ? 'PASS ' : 'FAIL ') + id + '  ' + detail + '\n');
}

let dir = null;
try {
  execFileSync('swiftc', ['--version'], { stdio: 'ignore' });
} catch {
  process.stdout.write('COULD NOT RUN  swiftc is not on this machine, so Apple’s encoder cannot be asked. Nothing was proved.\n');
  process.exit(3);
}

try {
  await import(pathToFileURL(join(PAIRING_DIR, 'lib', 'qr.js')).href);
  const DSQR = globalThis.DSQR;

  dir = mkdtempSync('/tmp/trevor-macmini-U12-U1-qrcheck-');
  const src = join(dir, 'qrgen.swift');
  const bin = join(dir, 'qrgen');
  writeFileSync(src, SWIFT);
  execFileSync('swiftc', ['-O', src, '-o', bin], { stdio: 'pipe' });

  for (const [text, level] of CASES) {
    const out = execFileSync(bin, [text, level], { encoding: 'utf8' }).trim().split('\n');
    const ref = out.slice(1).map((line) => line.split('').map((ch) => (ch === '1' ? 1 : 0)));
    const refSize = ref.length;

    const q = DSQR.encode(text, { level });
    if (!q.ok) {
      check(`${level}-${text.length}`, false, 'our encoder refused: ' + q.code);
      continue;
    }
    // CIQRCodeGenerator adds a one-module quiet zone on every side.
    const quiet = (refSize - q.size) / 2;
    if (!Number.isInteger(quiet) || quiet < 0) {
      check(`${level}-${text.length}`, false, `size ${refSize} vs ours ${q.size}`);
      continue;
    }

    let differing = 0;
    for (let r = 0; r < q.size; r++) {
      for (let c = 0; c < q.size; c++) {
        if (ref[r + quiet][c + quiet] !== q.modules[r][c]) differing++;
      }
    }
    check(
      `level-${level}-len-${text.length}`,
      differing === 0,
      differing === 0
        ? `version ${q.version}, mask ${q.mask}, ${q.size}x${q.size} — identical to Apple's matrix`
        : `${differing} of ${q.size * q.size} modules differ (ours version ${q.version} mask ${q.mask})`,
    );
  }

  process.stdout.write('\nNote: Apple encodes "ABCD-2345" in alphanumeric mode, so its matrix for the\n');
  process.stdout.write('pairing code legitimately differs from the byte-mode matrix here. scanability of\n');
  process.stdout.write('THIS surface’s pairing-code matrix is proved by decoding it back in\n');
  process.stdout.write('test/pairing.test.mjs; the checks above prove the encoder itself is correct.\n');
} catch (err) {
  process.stdout.write('COULD NOT RUN  ' + (err && err.message ? err.message : err) + '\n');
  if (dir) rmSync(dir, { recursive: true, force: true });
  process.exit(3);
}

if (dir) rmSync(dir, { recursive: true, force: true });

const failed = results.filter((ok) => !ok).length;
process.stdout.write('\n' + results.length + ' cases, ' + (results.length - failed) + ' identical to Apple, ' + failed + ' differing\n');
process.exit(failed === 0 ? 0 : 2);
