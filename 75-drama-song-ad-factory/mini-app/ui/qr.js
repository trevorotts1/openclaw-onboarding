// =============================================================================
// Drama Song Ad Factory mini-app — U3 version-0 QR surface
// -----------------------------------------------------------------------------
// mini-app/ui/qr.js
//
// A dependency-free QR Code generator, byte mode, error-correction level M,
// versions 1..10 (capacity 271 bytes — a delivery URL or a share URL fits with
// room to spare). Self-contained: no CDN, no npm package, no font, no network.
// The browser renders it as inline SVG; the runnable check (checks/qr-roundtrip.mjs)
// renders the SAME matrix to a PNG and decodes it back with zbarimg, so the
// proof covers the code that actually ships.
//
// ponytail: byte mode + EC level M + versions 1..10 only. That is the whole
// ceiling — if a payload ever needs more than 271 bytes or a different EC
// level, extend ECC_BLOCKS_M and ALIGN_POS, nothing else changes.
// =============================================================================

// ── EC level M block structure, versions 1..10 ────────────────────────────────
// [eccCodewordsPerBlock, [[blockCount, dataCodewordsPerBlock], ...]]
const ECC_BLOCKS_M = [
  null,
  [10, [[1, 16]]],
  [16, [[1, 28]]],
  [26, [[1, 44]]],
  [18, [[2, 32]]],
  [24, [[2, 43]]],
  [16, [[4, 27]]],
  [18, [[4, 31]]],
  [22, [[2, 38], [2, 39]]],
  [22, [[3, 36], [2, 37]]],
  [26, [[4, 43], [1, 44]]],
];

// Alignment-pattern centre coordinates, versions 1..10 (v1 has none).
const ALIGN_POS = [
  null,
  [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34],
  [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
];

const MAX_VERSION = 10;
const MIN_VERSION = 1;

function dataCodewords(version) {
  const [, groups] = ECC_BLOCKS_M[version];
  return groups.reduce((n, [count, len]) => n + count * len, 0);
}

function eccCodewordsPerBlock(version) {
  return ECC_BLOCKS_M[version][0];
}

// ── Galois field GF(256), primitive polynomial 0x11D ──────────────────────────
const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(function initGaloisField() {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
})();

function gfMul(a, b) {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

function reedSolomonGenerator(degree) {
  let poly = [1];
  for (let i = 0; i < degree; i++) {
    const next = new Array(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], GF_EXP[i]);
    }
    poly = next;
  }
  return poly; // length degree+1, leading coefficient 1
}

function reedSolomonRemainder(data, degree) {
  const gen = reedSolomonGenerator(degree);
  const rem = new Array(degree).fill(0);
  for (const byte of data) {
    const factor = byte ^ rem.shift();
    rem.push(0);
    for (let i = 0; i < degree; i++) rem[i] ^= gfMul(gen[i + 1], factor);
  }
  return rem;
}

// ── Data encoding: byte mode → codewords ──────────────────────────────────────
function chooseVersion(byteLen) {
  for (let v = MIN_VERSION; v <= MAX_VERSION; v++) {
    const countBits = v <= 9 ? 8 : 16;
    const needed = 4 + countBits + byteLen * 8;
    if (needed <= dataCodewords(v) * 8) return v;
  }
  throw new RangeError(`payload of ${byteLen} bytes exceeds version ${MAX_VERSION} level M capacity`);
}

class BitBuffer {
  constructor() { this.bits = []; }
  append(value, len) {
    for (let i = len - 1; i >= 0; i--) this.bits.push((value >>> i) & 1);
  }
  get length() { return this.bits.length; }
}

function buildCodewords(text, version) {
  const utf8 = new TextEncoder().encode(text);
  const capacityBits = dataCodewords(version) * 8;
  const buffer = new BitBuffer();
  buffer.append(0b0100, 4); // byte mode indicator
  buffer.append(utf8.length, version <= 9 ? 8 : 16);
  for (const b of utf8) buffer.append(b, 8);

  // Terminator: up to four zero bits.
  const terminator = Math.min(4, capacityBits - buffer.length);
  buffer.append(0, terminator);
  // Pad to a byte boundary.
  buffer.append(0, (8 - (buffer.length % 8)) % 8);
  // Pad bytes until the capacity is filled.
  for (let pad = 0xec; buffer.length < capacityBits; pad ^= 0xec ^ 0x11) {
    buffer.append(pad, 8);
  }

  const bytes = [];
  for (let i = 0; i < buffer.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | buffer.bits[i + j];
    bytes.push(byte);
  }
  return interleaveWithEcc(bytes, version);
}

function interleaveWithEcc(dataBytes, version) {
  const eccLen = eccCodewordsPerBlock(version);
  const [, groups] = ECC_BLOCKS_M[version];
  const blocks = [];
  let offset = 0;
  for (const [count, len] of groups) {
    for (let i = 0; i < count; i++) {
      const data = dataBytes.slice(offset, offset + len);
      offset += len;
      blocks.push({ data, ecc: reedSolomonRemainder(data, eccLen) });
    }
  }
  const maxData = Math.max(...blocks.map((b) => b.data.length));
  const out = [];
  for (let i = 0; i < maxData; i++) {
    for (const block of blocks) if (i < block.data.length) out.push(block.data[i]);
  }
  for (let i = 0; i < eccLen; i++) {
    for (const block of blocks) out.push(block.ecc[i]);
  }
  return out;
}

// ── Matrix construction ───────────────────────────────────────────────────────
function newGrid(size, fill) {
  return Array.from({ length: size }, () => new Array(size).fill(fill));
}

class QrMatrix {
  constructor(version) {
    this.version = version;
    this.size = version * 4 + 17;
    this.modules = newGrid(this.size, false);
    this.isFunction = newGrid(this.size, false);
  }
  setFunction(x, y, dark) {
    this.modules[y][x] = dark;
    this.isFunction[y][x] = true;
  }
  drawFinderPattern(x, y) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const dist = Math.max(Math.abs(dx), Math.abs(dy));
        const xx = x + dx, yy = y + dy;
        if (xx >= 0 && xx < this.size && yy >= 0 && yy < this.size) {
          this.setFunction(xx, yy, dist !== 2 && dist !== 4);
        }
      }
    }
  }
  drawAlignmentPattern(x, y) {
    for (let dy = -2; dy <= 2; dy++) {
      for (let dx = -2; dx <= 2; dx++) {
        this.setFunction(x + dx, y + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }
  }
  drawFunctionPatterns() {
    // Timing patterns first; the finders overwrite their corners.
    for (let i = 0; i < this.size; i++) {
      this.setFunction(6, i, i % 2 === 0);
      this.setFunction(i, 6, i % 2 === 0);
    }
    // Three finder patterns, complete with separators.
    this.drawFinderPattern(3, 3);
    this.drawFinderPattern(this.size - 4, 3);
    this.drawFinderPattern(3, this.size - 4);

    // Alignment patterns, skipping the three finder corners.
    const pos = ALIGN_POS[this.version];
    for (let i = 0; i < pos.length; i++) {
      for (let j = 0; j < pos.length; j++) {
        const corner = (i === 0 && j === 0)
          || (i === 0 && j === pos.length - 1)
          || (i === pos.length - 1 && j === 0);
        if (!corner) this.drawAlignmentPattern(pos[i], pos[j]);
      }
    }

    // Reserve the format-info areas, then draw them (all-dark for now; the
    // real mask bits land in drawFormatBits).
    this.drawFormatBits(0);
    // Version information (versions 7 and up).
    this.drawVersion();
  }
  drawFormatBits(mask) {
    const data = mask; // EC level M has format bits 0b00, so data = mask
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;
    const bit = (i) => ((bits >>> i) & 1) !== 0;

    // First copy, around the top-left finder.
    for (let i = 0; i <= 5; i++) this.setFunction(8, i, bit(i));
    this.setFunction(8, 7, bit(6));
    this.setFunction(8, 8, bit(7));
    this.setFunction(7, 8, bit(8));
    for (let i = 9; i < 15; i++) this.setFunction(14 - i, 8, bit(i));

    // Second copy, under/right of the other two finders.
    for (let i = 0; i < 8; i++) this.setFunction(this.size - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i++) this.setFunction(8, this.size - 15 + i, bit(i));
    this.setFunction(8, this.size - 8, true); // always-dark module
  }
  drawVersion() {
    if (this.version < 7) return;
    let rem = this.version;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (this.version << 12) | rem; // 18 bits
    for (let i = 0; i < 18; i++) {
      const dark = ((bits >>> i) & 1) !== 0;
      const a = this.size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      this.setFunction(a, b, dark);
      this.setFunction(b, a, dark);
    }
  }
  drawCodewords(codewords) {
    let i = 0; // bit index into codewords
    const totalBits = codewords.length * 8;
    for (let right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5; // skip the vertical timing column
      for (let vert = 0; vert < this.size; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? this.size - 1 - vert : vert;
          if (!this.isFunction[y][x] && i < totalBits) {
            this.modules[y][x] = ((codewords[i >>> 3] >>> (7 - (i & 7))) & 1) !== 0;
            i++;
          }
        }
      }
    }
  }
  applyMask(mask) {
    const s = this.size;
    for (let y = 0; y < s; y++) {
      for (let x = 0; x < s; x++) {
        if (this.isFunction[y][x]) continue;
        let invert;
        switch (mask) {
          case 0: invert = (x + y) % 2 === 0; break;
          case 1: invert = y % 2 === 0; break;
          case 2: invert = x % 3 === 0; break;
          case 3: invert = (x + y) % 3 === 0; break;
          case 4: invert = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
          case 5: invert = ((x * y) % 2) + ((x * y) % 3) === 0; break;
          case 6: invert = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          case 7: invert = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          default: throw new RangeError("mask out of range");
        }
        if (invert) this.modules[y][x] = !this.modules[y][x];
      }
    }
  }
  penaltyScore() {
    const s = this.size;
    const N1 = 3, N2 = 3, N3 = 40, N4 = 10;
    let result = 0;

    const addHistory = (runLength, history) => {
      let len = runLength;
      if (history[0] === 0) len += s; // light border before the first run
      for (let i = history.length - 1; i > 0; i--) history[i] = history[i - 1];
      history[0] = len;
    };
    const countPatterns = (history) => {
      const n = history[1];
      const core = n > 0 && history[2] === n && history[3] === n * 3
        && history[4] === n && history[5] === n;
      return (core && history[0] >= n * 4 && history[6] >= n ? 1 : 0)
        + (core && history[6] >= n * 4 && history[0] >= n ? 1 : 0);
    };
    const terminateAndCount = (runColor, runLength, history) => {
      let len = runLength;
      if (runColor) { addHistory(len, history); len = 0; }
      len += s;
      addHistory(len, history);
      return countPatterns(history);
    };

    const scanLine = (getter) => {
      let runColor = false;
      let runLength = 0;
      const history = new Array(7).fill(0);
      for (let i = 0; i < s; i++) {
        if (getter(i) === runColor) {
          runLength++;
          if (runLength === 5) result += N1;
          else if (runLength > 5) result++;
        } else {
          addHistory(runLength, history);
          if (!runColor) result += countPatterns(history) * N3;
          runColor = getter(i);
          runLength = 1;
        }
      }
      result += terminateAndCount(runColor, runLength, history) * N3;
    };

    for (let y = 0; y < s; y++) scanLine((x) => this.modules[y][x]);
    for (let x = 0; x < s; x++) scanLine((y) => this.modules[y][x]);

    for (let y = 0; y < s - 1; y++) {
      for (let x = 0; x < s - 1; x++) {
        const c = this.modules[y][x];
        if (c === this.modules[y][x + 1] && c === this.modules[y + 1][x]
          && c === this.modules[y + 1][x + 1]) result += N2;
      }
    }

    let dark = 0;
    for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) if (this.modules[y][x]) dark++;
    const total = s * s;
    const k = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
    result += k * N4;
    return result;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────
export function encode(text) {
  if (typeof text !== "string") throw new TypeError("encode() takes a string");
  if (text.length === 0) throw new RangeError("encode() takes a non-empty string");
  const byteLen = new TextEncoder().encode(text).length;
  const version = chooseVersion(byteLen);
  const codewords = buildCodewords(text, version);

  const matrix = new QrMatrix(version);
  matrix.drawFunctionPatterns();
  matrix.drawCodewords(codewords);

  let bestMask = 0;
  let bestScore = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    matrix.applyMask(mask);
    matrix.drawFormatBits(mask);
    const score = matrix.penaltyScore();
    if (score < bestScore) { bestScore = score; bestMask = mask; }
    matrix.applyMask(mask); // mask XOR is its own inverse
  }
  matrix.applyMask(bestMask);
  matrix.drawFormatBits(bestMask);

  return { size: matrix.size, version, mask: bestMask, modules: matrix.modules };
}

// Build the QR as a live SVG element with createElementNS. Used by the page so
// no HTML string is ever handed to innerHTML. `doc` defaults to the page's
// document; the check passes a document only if it wants one.
export function toElement(matrix, { quiet = 4, scale = 6, dark = "#141310", light = "#ffffff", doc = globalThis.document } = {}) {
  if (!doc) throw new Error("toElement() needs a document");
  const NS = "http://www.w3.org/2000/svg";
  const dim = matrix.size + quiet * 2;
  const svg = doc.createElementNS(NS, "svg");
  svg.setAttribute("width", String(dim * scale));
  svg.setAttribute("height", String(dim * scale));
  svg.setAttribute("viewBox", `0 0 ${dim} ${dim}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("shape-rendering", "crispEdges");
  const bg = doc.createElementNS(NS, "rect");
  bg.setAttribute("width", String(dim));
  bg.setAttribute("height", String(dim));
  bg.setAttribute("fill", light);
  svg.append(bg);
  const path = doc.createElementNS(NS, "path");
  const parts = [];
  for (let y = 0; y < matrix.size; y++) {
    for (let x = 0; x < matrix.size; x++) {
      if (matrix.modules[y][x]) parts.push(`M${x + quiet},${y + quiet}h1v1h-1z`);
    }
  }
  path.setAttribute("d", parts.join(""));
  path.setAttribute("fill", dark);
  svg.append(path);
  return svg;
}

// Inline SVG for the browser. `quiet` is the quiet-zone width in modules.
export function toSvg(matrix, { quiet = 4, scale = 6, dark = "#141310", light = "#ffffff" } = {}) {
  const dim = matrix.size + quiet * 2;
  const parts = [];
  for (let y = 0; y < matrix.size; y++) {
    for (let x = 0; x < matrix.size; x++) {
      if (matrix.modules[y][x]) {
        parts.push(`M${x + quiet},${y + quiet}h1v1h-1z`);
      }
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${dim * scale}" height="${dim * scale}" `
    + `viewBox="0 0 ${dim} ${dim}" role="img" shape-rendering="crispEdges">`
    + `<rect width="${dim}" height="${dim}" fill="${light}"/>`
    + `<path d="${parts.join("")}" fill="${dark}"/></svg>`;
}
