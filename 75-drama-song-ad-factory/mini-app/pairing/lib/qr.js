/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN  ::  lib/qr.js
 * -----------------------------------------------------------------------------
 * The QR presentation of a pairing code (U12 scope: "Pairing/admin/key/cutoff/
 * options behind approval/QR"; plan section 5 row U12).
 *
 * A plain classic script — no imports, no bundler, no CDN, no dependency. It
 * attaches one object, `globalThis.DSQR`, which the admin page loads with a
 * <script> tag and a node test loads with `await import(...)`. This is the same
 * shape 53-book-writer/mini-app/pages/recorder.js uses (self-registration on
 * globalThis), so the repo keeps one page-loading pattern.
 *
 * SCOPE, deliberately narrow (ISO/IEC 18004):
 *   - BYTE mode only. The payload is a pairing code ("ABCD-2345") or a short
 *     studio link, so numeric/kanji/ECI are not implemented and not needed.
 *   - EC levels L, M, Q, H. Versions 1..6 (up to 21..41 modules), which covers
 *     every payload this surface can show. A longer payload is REFUSED with a
 *     named code — never silently truncated.
 *   - Mask selection implements the spec's four penalty rules. `mask` is
 *     injectable so the encoder can be compared module-for-module against an
 *     independent implementation (prove/prove_qr_against_apple.mjs).
 *
 * PURE: no DOM, no clock, no bindings, no I/O. `toSvg` returns a string.
 * ========================================================================== */

'use strict';

(function (root) {
  var AF_QR_TOO_LONG = 'AF-DS-QR-TOO-LONG';
  var AF_QR_BAD_LEVEL = 'AF-DS-QR-BAD-LEVEL';
  var AF_QR_BAD_INPUT = 'AF-DS-QR-BAD-INPUT';

  // Format-info EC level bits (ISO/IEC 18004 table 25).
  var EC_BITS = { L: 0b01, M: 0b00, Q: 0b11, H: 0b10 };

  // [ecCodewordsPerBlock, blocks1, dataCodewords1, blocks2, dataCodewords2]
  var EC_BLOCKS = {
    '1L': [7, 1, 19, 0, 0], '1M': [10, 1, 16, 0, 0], '1Q': [13, 1, 13, 0, 0], '1H': [17, 1, 9, 0, 0],
    '2L': [10, 1, 34, 0, 0], '2M': [16, 1, 28, 0, 0], '2Q': [22, 1, 22, 0, 0], '2H': [28, 1, 16, 0, 0],
    '3L': [15, 1, 55, 0, 0], '3M': [26, 1, 44, 0, 0], '3Q': [18, 2, 17, 0, 0], '3H': [22, 2, 13, 0, 0],
    '4L': [20, 1, 80, 0, 0], '4M': [18, 2, 32, 0, 0], '4Q': [26, 2, 24, 0, 0], '4H': [16, 4, 9, 0, 0],
    '5L': [26, 1, 108, 0, 0], '5M': [24, 2, 43, 0, 0], '5Q': [18, 2, 15, 2, 16], '5H': [22, 2, 11, 2, 12],
    '6L': [18, 2, 68, 0, 0], '6M': [16, 4, 27, 0, 0], '6Q': [24, 4, 19, 0, 0], '6H': [28, 4, 15, 0, 0],
  };

  // Alignment-pattern centre coordinates (table E.1).
  var ALIGN = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34] };

  // Left-over modules after the last codeword, filled with light modules
  // (table 1). Version 1 has none; versions 2-6 have seven.
  var REMAINDER_BITS = { 1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7 };

  // ---------------------------------------------------------------------------
  // GF(256) / Reed-Solomon, primitive polynomial 0x11D
  // ---------------------------------------------------------------------------

  var EXP = new Array(512);
  var LOG = new Array(256);
  (function () {
    var x = 1;
    for (var i = 0; i < 255; i++) {
      EXP[i] = x;
      LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;
    }
    for (var j = 255; j < 512; j++) EXP[j] = EXP[j - 255];
  })();

  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return EXP[LOG[a] + LOG[b]];
  }

  /** Generator polynomial for `n` EC codewords, highest power first (g[0]===1). */
  function rsGenPoly(n) {
    var g = [1];
    for (var i = 0; i < n; i++) {
      var a = EXP[i];
      var next = new Array(g.length + 1).fill(0);
      for (var k = 0; k < g.length; k++) {
        next[k] ^= g[k];
        next[k + 1] ^= gfMul(g[k], a);
      }
      g = next;
    }
    return g;
  }

  /** Remainder of data*x^n divided by the generator — the EC codewords. */
  function rsEncode(data, n) {
    var gen = rsGenPoly(n);
    var rem = new Array(n).fill(0);
    for (var d = 0; d < data.length; d++) {
      var factor = data[d] ^ rem[0];
      rem.shift();
      rem.push(0);
      for (var i = 0; i < n; i++) rem[i] ^= gfMul(gen[i + 1], factor);
    }
    return rem;
  }

  // ---------------------------------------------------------------------------
  // Bit stream
  // ---------------------------------------------------------------------------

  function toBytes(text) {
    // UTF-8, so a non-ASCII label cannot silently become garbage.
    var out = [];
    var s = String(text);
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c < 0x80) out.push(c);
      else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
      else out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    }
    return out;
  }

  function pushBits(bits, value, width) {
    for (var i = width - 1; i >= 0; i--) bits.push((value >> i) & 1);
  }

  /** mode(0100) + 8-bit char count + data + terminator + byte padding + pad words */
  function dataCodewords(bytes, dataCapacityBytes) {
    var bits = [];
    pushBits(bits, 0b0100, 4);
    pushBits(bits, bytes.length, 8);
    for (var i = 0; i < bytes.length; i++) pushBits(bits, bytes[i], 8);

    var capacityBits = dataCapacityBytes * 8;
    var terminator = Math.min(4, capacityBits - bits.length);
    for (var t = 0; t < terminator; t++) bits.push(0);
    while (bits.length % 8 !== 0) bits.push(0);

    var words = [];
    for (var b = 0; b < bits.length; b += 8) {
      var v = 0;
      for (var k = 0; k < 8; k++) v = (v << 1) | bits[b + k];
      words.push(v);
    }
    var pad = [0xec, 0x11];
    var p = 0;
    while (words.length < dataCapacityBytes) words.push(pad[p++ % 2]);
    return words;
  }

  function interleave(words, spec) {
    var ecPerBlock = spec[0];
    var blocks = [];
    var offset = 0;
    var g1 = spec[1] | 0;
    var len1 = spec[2] | 0;
    var g2 = spec[3] | 0;
    var len2 = spec[4] | 0;
    for (var i = 0; i < g1; i++) {
      var d1 = words.slice(offset, offset + len1);
      offset += len1;
      blocks.push({ data: d1, ec: rsEncode(d1, ecPerBlock) });
    }
    for (var j = 0; j < g2; j++) {
      var d2 = words.slice(offset, offset + len2);
      offset += len2;
      blocks.push({ data: d2, ec: rsEncode(d2, ecPerBlock) });
    }
    var out = [];
    var maxData = Math.max.apply(null, blocks.map(function (b) { return b.data.length; }));
    for (var c = 0; c < maxData; c++) {
      for (var bi = 0; bi < blocks.length; bi++) {
        if (c < blocks[bi].data.length) out.push(blocks[bi].data[c]);
      }
    }
    for (var e = 0; e < ecPerBlock; e++) {
      for (var bj = 0; bj < blocks.length; bj++) out.push(blocks[bj].ec[e]);
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Matrix
  // ---------------------------------------------------------------------------

  function makeGrid(size) {
    var g = new Array(size);
    for (var r = 0; r < size; r++) g[r] = new Array(size).fill(0);
    return g;
  }

  function functionMask(version) {
    var size = 17 + 4 * version;
    var f = new Array(size);
    for (var r = 0; r < size; r++) f[r] = new Array(size).fill(false);
    return f;
  }

  function setFinder(grid, func, size, r0, c0) {
    for (var dr = -1; dr <= 7; dr++) {
      for (var dc = -1; dc <= 7; dc++) {
        var r = r0 + dr;
        var c = c0 + dc;
        if (r < 0 || c < 0 || r >= size || c >= size) continue;
        var dark;
        if (dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6) {
          dark = dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4);
        } else {
          dark = false; // separator
        }
        func[r][c] = true;
        grid[r][c] = dark ? 1 : 0;
      }
    }
  }

  function buildFunctionModules(grid, func, version) {
    var size = 17 + 4 * version;
    setFinder(grid, func, size, 0, 0);
    setFinder(grid, func, size, 0, size - 7);
    setFinder(grid, func, size, size - 7, 0);

    // timing patterns
    for (var i = 8; i < size - 8; i++) {
      var bit = i % 2 === 0 ? 1 : 0;
      func[6][i] = true; grid[6][i] = bit;
      func[i][6] = true; grid[i][6] = bit;
    }

    // alignment patterns, skipping the three that collide with finders
    var centres = ALIGN[version] || [];
    for (var a = 0; a < centres.length; a++) {
      for (var b = 0; b < centres.length; b++) {
        var cr = centres[a];
        var cc = centres[b];
        var collide = (cr === 6 && cc === 6) || (cr === 6 && cc === size - 7) || (cr === size - 7 && cc === 6);
        if (collide) continue;
        for (var dr2 = -2; dr2 <= 2; dr2++) {
          for (var dc2 = -2; dc2 <= 2; dc2++) {
            var rr = cr + dr2;
            var ccol = cc + dc2;
            func[rr][ccol] = true;
            grid[rr][ccol] = Math.max(Math.abs(dr2), Math.abs(dc2)) !== 1 ? 1 : 0;
          }
        }
      }
    }

    // the dark module
    func[4 * version + 9][8] = true;
    grid[4 * version + 9][8] = 1;

    // reserve the two format-info copies (values written after masking).
    // Both skip index 6 — that module belongs to the timing pattern.
    for (var c1 = 0; c1 <= 8; c1++) { if (c1 === 6) continue; func[8][c1] = true; grid[8][c1] = 0; }
    for (var r1 = 0; r1 <= 8; r1++) { if (r1 === 6) continue; func[r1][8] = true; grid[r1][8] = 0; }
    for (var c2 = size - 8; c2 < size; c2++) { func[8][c2] = true; grid[8][c2] = 0; }
    for (var r2 = size - 7; r2 < size; r2++) { func[r2][8] = true; grid[r2][8] = 0; }
  }

  function placeData(grid, func, codewords) {
    var size = grid.length;
    var bits = [];
    for (var i = 0; i < codewords.length; i++) pushBits(bits, codewords[i], 8);
    var idx = 0;
    var upward = true;
    for (var col = size - 1; col > 0; col -= 2) {
      if (col === 6) col--; // the timing column is not a data column
      for (var i2 = 0; i2 < size; i2++) {
        var row = upward ? size - 1 - i2 : i2;
        for (var k = 0; k < 2; k++) {
          var c = k === 0 ? col : col - 1;
          if (func[row][c]) continue;
          grid[row][c] = idx < bits.length ? bits[idx] : 0;
          idx++;
        }
      }
      upward = !upward;
    }
    return idx;
  }

  var MASK_FN = [
    function (r, c) { return (r + c) % 2 === 0; },
    function (r) { return r % 2 === 0; },
    function (r, c) { return c % 3 === 0; },
    function (r, c) { return (r + c) % 3 === 0; },
    function (r, c) { return (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0; },
    function (r, c) { return ((r * c) % 2) + ((r * c) % 3) === 0; },
    function (r, c) { return (((r * c) % 2) + ((r * c) % 3)) % 2 === 0; },
    function (r, c) { return (((r + c) % 2) + ((r * c) % 3)) % 2 === 0; },
  ];

  function applyMask(grid, func, mask) {
    var size = grid.length;
    var fn = MASK_FN[mask];
    var out = makeGrid(size);
    for (var r = 0; r < size; r++) {
      for (var c = 0; c < size; c++) {
        out[r][c] = !func[r][c] && fn(r, c) ? grid[r][c] ^ 1 : grid[r][c];
      }
    }
    return out;
  }

  function penalty(grid) {
    var size = grid.length;
    var score = 0;
    var r;
    var c;
    var run;
    var i;

    // N1 — runs of five or more in a row / column
    for (r = 0; r < size; r++) {
      run = 1;
      for (c = 1; c < size; c++) {
        if (grid[r][c] === grid[r][c - 1]) run++;
        else { if (run >= 5) score += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) score += 3 + (run - 5);
    }
    for (c = 0; c < size; c++) {
      run = 1;
      for (r = 1; r < size; r++) {
        if (grid[r][c] === grid[r - 1][c]) run++;
        else { if (run >= 5) score += 3 + (run - 5); run = 1; }
      }
      if (run >= 5) score += 3 + (run - 5);
    }

    // N2 — 2x2 blocks of one colour
    for (r = 0; r < size - 1; r++) {
      for (c = 0; c < size - 1; c++) {
        var v = grid[r][c];
        if (v === grid[r][c + 1] && v === grid[r + 1][c] && v === grid[r + 1][c + 1]) score += 3;
      }
    }

    // N3 — the 1:1:3:1:1 finder-like pattern, with 4 light modules on one side
    var P1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0];
    var P2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1];
    function matches(line, at, pat) {
      for (var k = 0; k < pat.length; k++) if (line[at + k] !== pat[k]) return false;
      return true;
    }
    for (r = 0; r < size; r++) {
      var rowLine = grid[r];
      var colLine = [];
      for (i = 0; i < size; i++) colLine.push(grid[i][r]);
      for (i = 0; i + 11 <= size; i++) {
        if (matches(rowLine, i, P1) || matches(rowLine, i, P2)) score += 40;
        if (matches(colLine, i, P1) || matches(colLine, i, P2)) score += 40;
      }
    }

    // N4 — dark-module balance
    var dark = 0;
    for (r = 0; r < size; r++) for (c = 0; c < size; c++) dark += grid[r][c];
    var percent = (dark * 100) / (size * size);
    score += Math.floor(Math.abs(percent - 50) / 5) * 10;

    return score;
  }

  function formatBits(level, mask) {
    var data = (EC_BITS[level] << 3) | mask;
    var value = data << 10;
    var gen = 0b10100110111;
    for (var i = 14; i >= 10; i--) {
      if ((value >> i) & 1) value ^= gen << (i - 10);
    }
    return ((data << 10) | value) ^ 0b101010000010010;
  }

  function placeFormat(grid, level, mask) {
    var size = grid.length;
    var bits = formatBits(level, mask);
    var bit = function (i) { return (bits >> i) & 1; };
    var i;

    // copy 1 — around the top-left finder. Bit 14 (MSB) sits at (8,0) and the
    // run walks to bit 0 at (0,8), the order the spec numbers them.
    for (i = 0; i <= 5; i++) grid[8][i] = bit(14 - i);
    grid[8][7] = bit(8);
    grid[8][8] = bit(7);
    grid[7][8] = bit(6);
    for (i = 9; i <= 14; i++) grid[14 - i][8] = bit(14 - i);

    // copy 2 — bits 14..8 in column 8 (7 modules) then bits 7..0 in row 8
    // (8 modules): 7 + 8 = 15. The 0x5E7C split is not arbitrary — this is the
    // order ISO/IEC 18004 §8.9 lays the second copy out.
    for (i = 0; i <= 6; i++) grid[size - 1 - i][8] = bit(14 - i);
    for (i = 0; i <= 7; i++) grid[8][size - 8 + i] = bit(7 - i);

    return grid;
  }

  // ---------------------------------------------------------------------------
  // Public entry
  // ---------------------------------------------------------------------------

  /**
   * Encode `text` as a QR matrix.
   * @param {string} text
   * @param {{level?: 'L'|'M'|'Q'|'H', mask?: number}} [opts]
   * @returns {{ok:true,text,level,version,size,mask,modules:number[][]}
   *          |{ok:false,code,message}}
   */
  function encode(text, opts) {
    var options = opts || {};
    var level = options.level || 'M';
    if (!EC_BITS.hasOwnProperty(level)) {
      return { ok: false, code: AF_QR_BAD_LEVEL, message: 'EC level must be L, M, Q or H.' };
    }
    if (typeof text !== 'string' || text.length === 0) {
      return { ok: false, code: AF_QR_BAD_INPUT, message: 'Nothing to encode.' };
    }
    var bytes = toBytes(text);

    var version = 0;
    var spec = null;
    for (var v = 1; v <= 6; v++) {
      var s = EC_BLOCKS[v + level];
      var capacity = (s[1] * s[2]) + (s[3] * s[4]);
      if (bytes.length + 2 <= capacity) { version = v; spec = s; break; }
    }
    if (!version) {
      return { ok: false, code: AF_QR_TOO_LONG, message: 'Too long for a version 1-6 QR code.' };
    }

    var capacityBytes = (spec[1] * spec[2]) + (spec[3] * spec[4]);
    var words = dataCodewords(bytes, capacityBytes);
    var codewords = interleave(words, spec);

    var size = 17 + 4 * version;
    var grid = makeGrid(size);
    var func = functionMask(version);
    buildFunctionModules(grid, func, version);

    var placed = placeData(grid, func, codewords);
    var freeModules = 0;
    for (var r = 0; r < size; r++) for (var c = 0; c < size; c++) if (!func[r][c]) freeModules++;
    if (placed !== freeModules || freeModules !== codewords.length * 8 + REMAINDER_BITS[version]) {
      return {
        ok: false,
        code: 'AF-DS-QR-LAYOUT',
        message: 'Module layout disagrees with the codeword count.',
      };
    }

    var mask = typeof options.mask === 'number' ? options.mask : null;
    if (mask === null) {
      var best = 0;
      var bestScore = Infinity;
      for (var m = 0; m < 8; m++) {
        var candidate = applyMask(grid, func, m);
        placeFormat(candidate, level, m);
        var sc = penalty(candidate);
        if (sc < bestScore) { bestScore = sc; best = m; }
      }
      mask = best;
    } else if (!(mask >= 0 && mask <= 7)) {
      return { ok: false, code: AF_QR_BAD_INPUT, message: 'mask must be 0..7.' };
    }

    var out = applyMask(grid, func, mask);
    placeFormat(out, level, mask);

    return { ok: true, text: text, level: level, version: version, size: size, mask: mask, modules: out };
  }

  /** Terminal / test rendering: '#' dark, ' ' light. */
  function toAscii(qr, opts) {
    var border = (opts && opts.border) || 0;
    var blank = new Array(qr.size + border * 2).fill(' ').join('');
    var lines = [];
    for (var i = 0; i < border; i++) lines.push(blank);
    for (var r = 0; r < qr.size; r++) {
      var line = border ? new Array(border + 1).join(' ') : '';
      for (var c = 0; c < qr.size; c++) line += qr.modules[r][c] ? '#' : ' ';
      lines.push(line);
    }
    for (var j = 0; j < border; j++) lines.push(blank);
    return lines.join('\n');
  }

  /** A single-path SVG. Quiet zone defaults to the 4 modules the spec asks for. */
  function toSvg(qr, opts) {
    var options = opts || {};
    var quiet = options.quiet === undefined ? 4 : options.quiet;
    var scale = options.scale || 6;
    var total = (qr.size + quiet * 2) * scale;
    var d = [];
    for (var r = 0; r < qr.size; r++) {
      for (var c = 0; c < qr.size; c++) {
        if (!qr.modules[r][c]) continue;
        d.push('M' + ((c + quiet) * scale) + ' ' + ((r + quiet) * scale) + 'h' + scale + 'v' + scale + 'h-' + scale + 'z');
      }
    }
    var label = options.label ? String(options.label) : 'Pairing code QR code';
    return [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + total + ' ' + total + '"',
      ' width="' + options.width + '" height="' + options.height + '"',
      ' role="img" aria-label="' + escapeAttr(label) + '" focusable="false">',
      '<title>' + escapeText(label) + '</title>',
      '<rect width="' + total + '" height="' + total + '" fill="#ffffff"/>',
      '<path d="' + d.join('') + '" fill="#000000"/>',
      '</svg>',
    ].join('');
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function escapeText(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  root.DSQR = {
    encode: encode,
    toAscii: toAscii,
    toSvg: toSvg,
    AF_QR_TOO_LONG: AF_QR_TOO_LONG,
    AF_QR_BAD_LEVEL: AF_QR_BAD_LEVEL,
    AF_QR_BAD_INPUT: AF_QR_BAD_INPUT,
    EC_BITS: EC_BITS,
    formatBits: formatBits,
    rsEncode: rsEncode,
    penalty: penalty,
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
