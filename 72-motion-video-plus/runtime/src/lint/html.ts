// Minimal HTML scanning for the lint layer (Directive MG-030).
//
// Hyperframes compositions and legacy scenes are HTML files whose
// behavior lives in <script> blocks and whose styling lives in <style>
// blocks and style attributes. This scanner extracts those blocks with
// their byte offsets in the original file, so findings computed inside
// a block map back to true file positions. It is a scanner, not a DOM:
// it understands tags, quoted attribute values, and the browser rule
// that a script block ends at the first "</script" even inside a
// string. Anything more structural belongs to the engines themselves.

export interface HtmlAttribute {
  name: string;
  value: string;
  /** Byte offset of the value's first character in the file. */
  valueOffset: number;
}

export interface HtmlTag {
  name: string;
  attrs: HtmlAttribute[];
  /** Byte offset of the "<" that opens the tag. */
  offset: number;
}

export interface HtmlChunk {
  kind: "script" | "style";
  text: string;
  /** Byte offset of the block content's first character in the file. */
  contentOffset: number;
  attrs: HtmlAttribute[];
}

export interface HtmlScan {
  chunks: HtmlChunk[];
  tags: HtmlTag[];
  errors: Array<{ offset: number; message: string }>;
}

function isNameChar(ch: string): boolean {
  return /[A-Za-z0-9-]/.test(ch);
}

export function scanHtml(text: string): HtmlScan {
  const chunks: HtmlChunk[] = [];
  const tags: HtmlTag[] = [];
  const errors: Array<{ offset: number; message: string }> = [];
  const lower = text.toLowerCase();
  const n = text.length;
  let i = 0;

  while (i < n) {
    const lt = text.indexOf("<", i);
    if (lt === -1) break;
    if (lower.startsWith("<!--", lt)) {
      const end = lower.indexOf("-->", lt + 4);
      i = end === -1 ? n : end + 3;
      continue;
    }
    const first = text[lt + 1];
    if (first === undefined || first === "/" || first === "!" || first === "?") {
      i = lt + 1;
      continue;
    }
    // Tag name.
    let j = lt + 1;
    while (j < n && isNameChar(text[j])) j += 1;
    const name = lower.slice(lt + 1, j);
    if (name.length === 0) {
      i = lt + 1;
      continue;
    }
    // Attributes up to ">" or "/>".
    const attrs: HtmlAttribute[] = [];
    let k = j;
    let tagEnd = -1;
    while (k < n) {
      while (k < n && /\s/.test(text[k])) k += 1;
      if (k >= n) break;
      if (text[k] === ">") {
        tagEnd = k;
        break;
      }
      if (text[k] === "/" && text[k + 1] === ">") {
        tagEnd = k + 1;
        break;
      }
      const nameStart = k;
      while (k < n && !/[\s=/>]/.test(text[k])) k += 1;
      const attrName = lower.slice(nameStart, k);
      while (k < n && /\s/.test(text[k])) k += 1;
      let value = "";
      let valueOffset = k;
      if (text[k] === "=") {
        k += 1;
        while (k < n && /\s/.test(text[k])) k += 1;
        const quote = text[k];
        if (quote === "\"" || quote === "'") {
          valueOffset = k + 1;
          const close = text.indexOf(quote, k + 1);
          const end = close === -1 ? n : close;
          value = text.slice(k + 1, end);
          k = close === -1 ? n : close + 1;
        } else {
          valueOffset = k;
          while (k < n && !/[\s>]/.test(text[k])) k += 1;
          value = text.slice(valueOffset, k);
        }
      }
      if (attrName.length > 0) {
        attrs.push({ name: attrName, value, valueOffset });
      }
    }
    tags.push({ name, attrs, offset: lt });
    if (tagEnd === -1) {
      errors.push({ offset: lt, message: `unclosed <${name}> tag` });
      break;
    }
    if (name === "script" || name === "style") {
      const contentStart = tagEnd + 1;
      const closeMarker = `</${name}`;
      const closeAt = lower.indexOf(closeMarker, contentStart);
      if (closeAt === -1) {
        errors.push({
          offset: lt,
          message: `unclosed <${name}> block: no ${closeMarker}> found`,
        });
        chunks.push({
          kind: name,
          text: text.slice(contentStart),
          contentOffset: contentStart,
          attrs,
        });
        i = n;
      } else {
        chunks.push({
          kind: name,
          text: text.slice(contentStart, closeAt),
          contentOffset: contentStart,
          attrs,
        });
        const gt = text.indexOf(">", closeAt);
        i = gt === -1 ? n : gt + 1;
      }
      continue;
    }
    i = tagEnd + 1;
  }

  return { chunks, tags, errors };
}

/** Line-start offsets for position mapping over a whole file. */
export class LineIndex {
  private readonly starts: number[] = [0];

  constructor(text: string) {
    for (let i = 0; i < text.length; i += 1) {
      if (text[i] === "\n") this.starts.push(i + 1);
    }
  }

  /** 1-based line and column for a byte offset. */
  lineCol(offset: number): { line: number; column: number } {
    let lo = 0;
    let hi = this.starts.length - 1;
    while (lo < hi) {
      const mid = Math.floor((lo + hi + 1) / 2);
      if (this.starts[mid] <= offset) lo = mid;
      else hi = mid - 1;
    }
    return { line: lo + 1, column: offset - this.starts[lo] + 1 };
  }
}
