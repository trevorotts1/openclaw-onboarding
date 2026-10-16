// Real-font text measurement for diagram layout (Directive MG-017,
// consuming MG-013).
//
// Label collision checks are only honest if label widths come from the
// actual font binary, not from a character-count heuristic: proportional
// fonts make two labels of equal length different widths. This measurer
// parses the exact font file through the MG-013 typography module and
// measures with its advance tables. A missing font throws the
// typography module's named TYPO_FONT_MISSING error; there is no
// fallback font and no estimated width, by the same substitution law
// the render adapters enforce.

import { loadFontFile, measureString, type ParsedFont } from "../typography";
import type { TextMeasurer } from "./layout";

export class FontTextMeasurer implements TextMeasurer {
  private readonly font: ParsedFont;

  constructor(fontPath: string) {
    this.font = loadFontFile(fontPath);
  }

  measure(text: string, sizePx: number): number {
    return measureString(this.font, text, sizePx).widthPx;
  }

  get fontPath(): string {
    return this.font.path;
  }

  get fontSha256(): string {
    return this.font.sha256;
  }

  get familyName(): string {
    return this.font.familyName;
  }
}
