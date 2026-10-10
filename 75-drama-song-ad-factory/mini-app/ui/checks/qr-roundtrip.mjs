// =============================================================================
// RUNNABLE CHECK — the QR surface really scans
// -----------------------------------------------------------------------------
// mini-app/ui/checks/qr-roundtrip.mjs
//
// Proves the SHIPPED QR encoder (../qr.js, the same module the page loads)
// produces a real, decodable QR code: it renders the matrix to a PNG with the
// standard library only and decodes that PNG with an INDEPENDENT decoder
// (zbarimg). A QR that only "looks like" a QR fails here.
//
// Exit codes:  0 = pass, 2 = fail (a case failed), 3 = no independent decoder.
//
//   node checks/qr-roundtrip.mjs
// =============================================================================
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import zlib from "node:zlib";
import { encode } from "../qr.js";

// ── Minimal PNG writer (stdlib zlib only) ────────────────────────────────────
const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const body = Buffer.concat([Buffer.from(type, "latin1"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}

function pngFromMatrix(matrix, { quiet = 4, scale = 8 } = {}) {
  const dim = (matrix.size + quiet * 2) * scale;
  const raw = Buffer.alloc((dim * 3 + 1) * dim);
  let p = 0;
  for (let y = 0; y < dim; y++) {
    raw[p++] = 0; // filter: none
    for (let x = 0; x < dim; x++) {
      const mx = Math.floor(x / scale) - quiet;
      const my = Math.floor(y / scale) - quiet;
      const dark = mx >= 0 && my >= 0 && mx < matrix.size && my < matrix.size
        && matrix.modules[my][mx];
      const v = dark ? 0 : 255;
      raw[p++] = v; raw[p++] = v; raw[p++] = v;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(dim, 0);
  ihdr.writeUInt32BE(dim, 4);
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 2;   // truecolour
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ── Independent decoder ──────────────────────────────────────────────────────
function decodeWithZbar(pngPath) {
  return execFileSync("zbarimg", ["--quiet", "--raw", pngPath], { encoding: "utf8" }).trim();
}

// ── Cases ────────────────────────────────────────────────────────────────────
const CASES = [
  { name: "short share link", text: "https://go.blackceo.com/d/7f3a" },
  { name: "delivery download url", text: "https://studio.example.com/api/delivery/abc123/master.mp4" },
  { name: "long sponsor url", text: "https://acme-realty.example.com/listings/4812-maple-ave?utm_source=drama_song_ad&utm_medium=qr&utm_campaign=premiere_oct" },
];

const dir = mkdtempSync("/tmp/operator-U3-U1-qr-");
let failures = 0;
try {
  for (const c of CASES) {
    const matrix = encode(c.text);
    const png = pngFromMatrix(matrix);
    const file = join(dir, "qr.png");
    writeFileSync(file, png);
    let decoded = "";
    let ok = false;
    let note = "";
    try {
      decoded = decodeWithZbar(file);
      ok = decoded === c.text;
      note = ok ? "round-trip exact" : `MISMATCH: decoder read ${JSON.stringify(decoded)}`;
    } catch (err) {
      note = `decoder error: ${err.message.split("\n")[0]}`;
    }
    if (!ok) failures++;
    console.log(`${ok ? "PASS" : "FAIL"}  ${c.name.padEnd(22)} v${matrix.version} mask${matrix.mask} `
      + `${matrix.size}x${matrix.size} png=${png.length}B  ${note}`);
  }
} finally {
  rmSync(dir, { recursive: true, force: true });
}

if (failures > 0) {
  console.log(`\nQR round-trip FAILED: ${failures} of ${CASES.length} case(s)`);
  process.exit(2);
}
console.log(`\nQR round-trip OK: ${CASES.length}/${CASES.length} decoded exactly by zbarimg`);
process.exit(0);
