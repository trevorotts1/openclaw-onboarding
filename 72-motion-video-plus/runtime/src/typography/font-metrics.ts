// Font metrics parsed from the actual font binary (Directive MG-013).
//
// The typography system measures text with the font the job actually names:
// its units per em, per-glyph advance widths, cap height, line metrics, and
// weight class are all read out of that file's own SFNT tables (head, maxp,
// hhea, hmtx, OS/2, cmap, name). Nothing here falls back to a different
// font: if the file cannot be read or parsed, the caller gets a thrown
// TypographyError and reports a named finding. Measurement uses advance
// widths from hmtx; pair kerning (kern/GPOS) is intentionally not applied,
// because the un-kerned sum is the conservative (wider) estimate, so a fit
// decision made on it is safe at render time.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export class TypographyError extends Error {
  readonly kind: string;
  constructor(kind: string, message: string) {
    super(message);
    this.name = "TypographyError";
    this.kind = kind;
  }
}

export interface ParsedFont {
  /** Absolute path of the exact font file parsed. */
  path: string;
  sha256: string;
  /** Family name from the font's own name table (typographic family, ID 16, else family, ID 1). */
  familyName: string;
  /** Subfamily from the name table (ID 2), for example "Regular" or "Bold". */
  subfamily: string | null;
  /** OS/2 usWeightClass, for example 400 or 700. Null when the OS/2 table is absent. */
  weightClass: number | null;
  unitsPerEm: number;
  numGlyphs: number;
  /** OS/2 sCapHeight in font units. Null when the OS/2 table predates version 2. */
  capHeightUnits: number | null;
  ascentUnits: number;
  descentUnits: number;
  lineGapUnits: number;
  /** Advance width in font units for a glyph id (the last hmetric repeats, per spec). */
  advanceOfGlyph(glyphId: number): number;
  /** Glyph id for a Unicode codepoint, or 0 (.notdef) when the font has no glyph for it. */
  glyphForCodepoint(codepoint: number): number;
}

interface TableRecord {
  offset: number;
  length: number;
}

function u16(buf: Buffer, off: number): number {
  return buf.readUInt16BE(off);
}
function i16(buf: Buffer, off: number): number {
  return buf.readInt16BE(off);
}
function u32(buf: Buffer, off: number): number {
  return buf.readUInt32BE(off);
}

function tableDirectory(buf: Buffer): Map<string, TableRecord> {
  if (buf.length < 12) {
    throw new TypographyError("TYPO_FONT_PARSE", "Font file is too short to hold an SFNT header.");
  }
  const numTables = u16(buf, 4);
  const tables = new Map<string, TableRecord>();
  for (let i = 0; i < numTables; i += 1) {
    const rec = 12 + i * 16;
    if (rec + 16 > buf.length) break;
    const tag = buf.toString("latin1", rec, rec + 4);
    tables.set(tag, { offset: u32(buf, rec + 8), length: u32(buf, rec + 12) });
  }
  return tables;
}

function requireTable(
  tables: Map<string, TableRecord>,
  tag: string,
  path: string
): TableRecord {
  const rec = tables.get(tag);
  if (!rec) {
    throw new TypographyError(
      "TYPO_FONT_PARSE",
      `Font file ${path} has no "${tag}" table; its metrics cannot be measured.`
    );
  }
  return rec;
}

// ---------------------------------------------------------------- cmap --

type CmapLookup = (codepoint: number) => number;

function parseCmapFormat4(buf: Buffer, off: number): CmapLookup {
  const segCount = u16(buf, off + 6) / 2;
  const endBase = off + 14;
  const startBase = endBase + 2 * segCount + 2;
  const deltaBase = startBase + 2 * segCount;
  const rangeBase = deltaBase + 2 * segCount;
  const ends: number[] = [];
  const starts: number[] = [];
  const deltas: number[] = [];
  const ranges: number[] = [];
  for (let s = 0; s < segCount; s += 1) {
    ends.push(u16(buf, endBase + 2 * s));
    starts.push(u16(buf, startBase + 2 * s));
    deltas.push(i16(buf, deltaBase + 2 * s));
    ranges.push(u16(buf, rangeBase + 2 * s));
  }
  return (cp: number): number => {
    if (cp > 0xffff) return 0;
    for (let s = 0; s < segCount; s += 1) {
      if (cp >= starts[s] && cp <= ends[s]) {
        if (ranges[s] === 0) return (cp + deltas[s]) & 0xffff;
        const glyphIndexOff =
          rangeBase + 2 * s + ranges[s] + 2 * (cp - starts[s]);
        const gid = u16(buf, glyphIndexOff);
        return gid === 0 ? 0 : (gid + deltas[s]) & 0xffff;
      }
    }
    return 0;
  };
}

function parseCmapFormat12(buf: Buffer, off: number): CmapLookup {
  const nGroups = u32(buf, off + 12);
  const groups: Array<{ start: number; end: number; glyph: number }> = [];
  for (let g = 0; g < nGroups; g += 1) {
    const rec = off + 16 + g * 12;
    groups.push({
      start: u32(buf, rec),
      end: u32(buf, rec + 4),
      glyph: u32(buf, rec + 8),
    });
  }
  return (cp: number): number => {
    let lo = 0;
    let hi = groups.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const g = groups[mid];
      if (cp < g.start) hi = mid - 1;
      else if (cp > g.end) lo = mid + 1;
      else return g.glyph + (cp - g.start);
    }
    return 0;
  };
}

function parseCmap(buf: Buffer, rec: TableRecord): CmapLookup {
  const numSubtables = u16(buf, rec.offset + 2);
  const candidates: Array<{ rank: number; offset: number }> = [];
  for (let i = 0; i < numSubtables; i += 1) {
    const entry = rec.offset + 4 + i * 8;
    const platform = u16(buf, entry);
    const encoding = u16(buf, entry + 2);
    const subOff = rec.offset + u32(buf, entry + 4);
    if (subOff + 2 > buf.length) continue;
    const format = u16(buf, subOff);
    let rank = -1;
    if (format === 12 && platform === 3 && encoding === 10) rank = 0;
    else if (format === 12 && platform === 0) rank = 1;
    else if (format === 4 && platform === 3 && encoding === 1) rank = 2;
    else if (format === 4 && platform === 0) rank = 3;
    else if (format === 4 && platform === 1) rank = 4;
    if (rank >= 0) candidates.push({ rank, offset: subOff });
  }
  candidates.sort((a, b) => a.rank - b.rank);
  if (candidates.length === 0) {
    throw new TypographyError(
      "TYPO_FONT_PARSE",
      "Font cmap has no format 4 or format 12 subtable; glyphs cannot be mapped."
    );
  }
  const best = candidates[0];
  const format = u16(buf, best.offset);
  return format === 12
    ? parseCmapFormat12(buf, best.offset)
    : parseCmapFormat4(buf, best.offset);
}

// ---------------------------------------------------------------- name --

interface FontNames {
  family: string | null;
  typographicFamily: string | null;
  subfamily: string | null;
}

function decodeName(buf: Buffer, off: number, length: number, platform: number): string {
  if (platform === 1) return buf.toString("latin1", off, off + length);
  // Platforms 0 and 3 store UTF-16BE.
  let out = "";
  for (let i = 0; i + 1 < length; i += 2) {
    out += String.fromCharCode(buf.readUInt16BE(off + i));
  }
  return out;
}

function parseNameTable(buf: Buffer, rec: TableRecord): FontNames {
  const count = u16(buf, rec.offset + 2);
  const storage = rec.offset + u16(buf, rec.offset + 4);
  const found = new Map<string, string>();
  for (let i = 0; i < count; i += 1) {
    const entry = rec.offset + 6 + i * 12;
    const platform = u16(buf, entry);
    const nameId = u16(buf, entry + 6);
    const length = u16(buf, entry + 8);
    const offset = u16(buf, entry + 10);
    if (![1, 2, 16].includes(nameId)) continue;
    const key = `${nameId}`;
    // Prefer the Unicode/Microsoft record over a Macintosh one.
    if (found.has(key) && platform === 1) continue;
    found.set(key, decodeName(buf, storage + offset, length, platform));
  }
  return {
    family: found.get("1") ?? null,
    typographicFamily: found.get("16") ?? null,
    subfamily: found.get("2") ?? null,
  };
}

// ------------------------------------------------------------- parsing --

export function parseFontBytes(path: string, bytes: Buffer): ParsedFont {
  const tables = tableDirectory(bytes);
  const head = requireTable(tables, "head", path);
  const maxp = requireTable(tables, "maxp", path);
  const hhea = requireTable(tables, "hhea", path);
  const hmtx = requireTable(tables, "hmtx", path);
  const cmapRec = requireTable(tables, "cmap", path);

  const unitsPerEm = u16(bytes, head.offset + 18);
  if (unitsPerEm === 0) {
    throw new TypographyError("TYPO_FONT_PARSE", `Font file ${path} declares zero units per em.`);
  }
  const numGlyphs = u16(bytes, maxp.offset + 4);
  const numberOfHMetrics = u16(bytes, hhea.offset + 34);
  const advances: number[] = [];
  for (let g = 0; g < numberOfHMetrics; g += 1) {
    advances.push(u16(bytes, hmtx.offset + g * 4));
  }
  if (advances.length === 0) {
    throw new TypographyError("TYPO_FONT_PARSE", `Font file ${path} declares no horizontal metrics.`);
  }
  const glyphForCodepoint = parseCmap(bytes, cmapRec);

  let capHeightUnits: number | null = null;
  let weightClass: number | null = null;
  const os2 = tables.get("OS/2");
  if (os2) {
    weightClass = u16(bytes, os2.offset + 4);
    const version = u16(bytes, os2.offset);
    if (version >= 2 && os2.length >= 90) {
      capHeightUnits = i16(bytes, os2.offset + 88);
    }
  }

  let familyName: string | null = null;
  let subfamily: string | null = null;
  const nameRec = tables.get("name");
  if (nameRec) {
    const names = parseNameTable(bytes, nameRec);
    familyName = names.typographicFamily ?? names.family;
    subfamily = names.subfamily;
  }
  if (!familyName) {
    throw new TypographyError(
      "TYPO_FONT_PARSE",
      `Font file ${path} has no family name in its name table; substitution cannot be checked.`
    );
  }

  return {
    path,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    familyName,
    subfamily,
    weightClass,
    unitsPerEm,
    numGlyphs,
    capHeightUnits,
    ascentUnits: i16(bytes, hhea.offset + 4),
    descentUnits: i16(bytes, hhea.offset + 6),
    lineGapUnits: i16(bytes, hhea.offset + 8),
    advanceOfGlyph(glyphId: number): number {
      if (glyphId < advances.length) return advances[glyphId];
      return advances[advances.length - 1];
    },
    glyphForCodepoint,
  };
}

export function loadFontFile(path: string): ParsedFont {
  let bytes: Buffer;
  try {
    bytes = readFileSync(path);
  } catch {
    throw new TypographyError(
      "TYPO_FONT_MISSING",
      `Font file not found: ${path}. The job names this exact font; substitution is forbidden, so measurement cannot proceed with another font.`
    );
  }
  return parseFontBytes(path, bytes);
}

// ---------------------------------------------------------- measurement --

export interface TextMeasurement {
  /** Total advance width of the string in pixels at the requested size. */
  widthPx: number;
  /** Cap height in pixels at the requested size, null when the font predates OS/2 v2. */
  capHeightPx: number | null;
  /** Cap height as a fraction of the em (capHeightUnits / unitsPerEm). */
  capHeightRatio: number | null;
  /** Codepoints the font has no glyph for (they render as .notdef). */
  missingCodepoints: number[];
}

export function measureString(
  font: ParsedFont,
  text: string,
  sizePx: number
): TextMeasurement {
  const scale = sizePx / font.unitsPerEm;
  let units = 0;
  const missing: number[] = [];
  for (const ch of text) {
    const cp = ch.codePointAt(0) as number;
    const gid = font.glyphForCodepoint(cp);
    if (gid === 0 && cp !== 0) missing.push(cp);
    units += font.advanceOfGlyph(gid);
  }
  return {
    widthPx: units * scale,
    capHeightPx:
      font.capHeightUnits === null ? null : font.capHeightUnits * scale,
    capHeightRatio:
      font.capHeightUnits === null
        ? null
        : font.capHeightUnits / font.unitsPerEm,
    missingCodepoints: missing,
  };
}

/** Line height in pixels from the font's own hhea metrics. */
export function lineHeightPx(font: ParsedFont, sizePx: number): number {
  const units = font.ascentUnits - font.descentUnits + font.lineGapUnits;
  return units * (sizePx / font.unitsPerEm);
}

export interface LaidOutLine {
  text: string;
  widthPx: number;
  /** Set when this line is a single word wider than the box (unbreakable overflow). */
  unbreakableWord: string | null;
}

export interface TextLayout {
  lines: LaidOutLine[];
  lineHeightPx: number;
  totalHeightPx: number;
  widestLinePx: number;
  missingCodepoints: number[];
}

/**
 * Greedy word wrap against a declared box width, using real glyph advances.
 * Paragraphs split on explicit newlines; runs of whitespace collapse to one
 * space, as HTML layout does. A word wider than the box is placed on its own
 * line and flagged unbreakable rather than silently clipped.
 */
export function layoutText(
  font: ParsedFont,
  text: string,
  sizePx: number,
  boxWidthPx: number
): TextLayout {
  const lh = lineHeightPx(font, sizePx);
  const spaceWidth = measureString(font, " ", sizePx).widthPx;
  const missing = new Set<number>();
  const lines: LaidOutLine[] = [];
  for (const paragraph of text.split("\n")) {
    const words = paragraph.split(/\s+/).filter((w) => w.length > 0);
    if (words.length === 0) {
      lines.push({ text: "", widthPx: 0, unbreakableWord: null });
      continue;
    }
    let current: string[] = [];
    let currentWidth = 0;
    const flush = (): void => {
      if (current.length === 0) return;
      const joined = current.join(" ");
      const m = measureString(font, joined, sizePx);
      m.missingCodepoints.forEach((cp) => missing.add(cp));
      lines.push({
        text: joined,
        widthPx: m.widthPx,
        unbreakableWord:
          current.length === 1 && m.widthPx > boxWidthPx ? joined : null,
      });
      current = [];
      currentWidth = 0;
    };
    for (const word of words) {
      const wordWidth = measureString(font, word, sizePx).widthPx;
      const candidate =
        current.length === 0 ? wordWidth : currentWidth + spaceWidth + wordWidth;
      if (current.length > 0 && candidate > boxWidthPx) flush();
      current.push(word);
      currentWidth =
        current.length === 1
          ? wordWidth
          : currentWidth + spaceWidth + wordWidth;
      if (current.length === 1 && wordWidth > boxWidthPx) flush();
    }
    flush();
  }
  const widest = lines.reduce((max, l) => Math.max(max, l.widthPx), 0);
  return {
    lines,
    lineHeightPx: lh,
    totalHeightPx: lines.length * lh,
    widestLinePx: widest,
    missingCodepoints: [...missing],
  };
}
