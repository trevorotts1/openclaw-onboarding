/**
 * Chamber theme tests (unit G).
 *
 * Runner:
 *   node --import tsx --test tests/chamber-theme.test.ts
 *
 * Reads the shipped stylesheets and scripts as text. Proves the BlackCEO
 * palette rule (no navy, blue, purple or green anywhere), that only
 * chamber-theme.css holds colour literals, that the token pairs meet WCAG
 * 4.5:1, and that the layout, dialog, focus and reduced-motion primitives
 * the other chamber units build on are present.
 */

import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const read = (name: string): string => readFileSync(join(chamberDir, name), 'utf8');

type Rgba = { r: number; g: number; b: number; a: number };

// ── colour parsing ─────────────────────────────────────────────────────────

const LITERAL = /#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b|\b(?:rgba?|hsla?)\(\s*[^)]*\)/g;

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"\w])\/\/[^\n]*/g, '$1');
}

function stripSvg(html: string): string {
  return html.replace(/<svg[\s\S]*?<\/svg>/gi, '');
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const k = (n: number): number => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number): number => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}

function parseColour(literal: string): Rgba | null {
  const text = literal.trim().toLowerCase();
  if (text.startsWith('#')) {
    let hex = text.slice(1);
    if (hex.length <= 4) hex = [...hex].map((c) => c + c).join('');
    const n = (i: number): number => parseInt(hex.slice(i, i + 2), 16);
    return { r: n(0), g: n(2), b: n(4), a: hex.length === 8 ? n(6) / 255 : 1 };
  }
  const m = /^(rgba?|hsla?)\(\s*([^)]*)\)$/.exec(text);
  if (!m) return null;
  const parts = m[2].split(/[\s,/]+/).filter(Boolean);
  if (parts.length < 3) return null;
  const num = (v: string, scale: number): number => (v.endsWith('%') ? (parseFloat(v) / 100) * scale : parseFloat(v));
  const alpha = parts[3] === undefined ? 1 : num(parts[3], 1);
  if (m[1].startsWith('rgb')) {
    return { r: num(parts[0], 255), g: num(parts[1], 255), b: num(parts[2], 255), a: alpha };
  }
  const [r, g, b] = hslToRgb(parseFloat(parts[0]), num(parts[1], 1), num(parts[2], 1));
  return { r, g, b, a: alpha };
}

/** Hue in degrees (0..360) and HSL saturation (0..1). */
function hueSat(c: Rgba): { hue: number; sat: number } {
  const r = c.r / 255, g = c.g / 255, b = c.b / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const d = max - min;
  if (d === 0) return { hue: 0, sat: 0 };
  const l = (max + min) / 2;
  const sat = d / (1 - Math.abs(2 * l - 1));
  let hue: number;
  if (max === r) hue = ((g - b) / d) % 6;
  else if (max === g) hue = (b - r) / d + 2;
  else hue = (r - g) / d + 4;
  hue = (hue * 60 + 360) % 360;
  return { hue, sat };
}

function literalsIn(text: string): string[] {
  return stripComments(text).match(LITERAL) ?? [];
}

// ── WCAG contrast ──────────────────────────────────────────────────────────

const channel = (v: number): number => {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const luminance = (c: { r: number; g: number; b: number }): number =>
  0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);

function over(fg: Rgba, bg: Rgba): Rgba {
  return {
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  };
}

function contrast(fg: Rgba, bg: Rgba): number {
  const solid = over(fg, bg);
  const a = luminance(solid), b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// ── token resolution ───────────────────────────────────────────────────────

function declarations(css: string, selectorStart: string): Map<string, string> {
  const out = new Map<string, string>();
  const clean = stripComments(css);
  // First top-level rule only: later (media-query) redefinitions must not leak in.
  const re = new RegExp(`(^|\\n)${selectorStart.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{([^}]*)\\}`);
  const m = re.exec(clean);
  assert.ok(m, `${selectorStart} rule missing`);
  for (const d of m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(d[1], d[2].trim());
  return out;
}

function resolveToken(name: string, tokens: Map<string, string>, depth = 0): Rgba {
  const raw = tokens.get(name);
  assert.ok(raw !== undefined, `token ${name} is not defined`);
  assert.ok(depth < 8, `token ${name} loops`);
  const ref = /^var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)$/.exec(raw);
  if (ref) return tokens.has(ref[1]) ? resolveToken(ref[1], tokens, depth + 1) : (parseColour(ref[2]) as Rgba);
  const parsed = parseColour(raw);
  assert.ok(parsed, `token ${name} is not a colour: ${raw}`);
  return parsed;
}

const theme = read('chamber-theme.css');
const chTokens = declarations(theme, ':root');
const councilTokens = declarations(read('council-theme.css'), '.council-theme');
const stageTokens = new Map([...councilTokens, ...declarations(read('council-theme.css'), '.council-theme .council-stage')]);

// ── files under the palette rule ───────────────────────────────────────────

function scannedFiles(): string[] {
  return readdirSync(chamberDir)
    .filter((f) => /\.(css|js)$/.test(f) || f === 'index.html')
    .sort();
}

function offending(file: string, predicate: (c: Rgba) => boolean): string[] {
  const raw = read(file);
  const text = file.endsWith('.html') ? stripSvg(raw) : raw;
  return literalsIn(text).filter((lit) => {
    const c = parseColour(lit);
    return c !== null && predicate(c);
  });
}

test('scanner self-check: it sees the brand literals and flags blue', () => {
  assert.ok(literalsIn(theme).includes('#C9A227'));
  const navy = parseColour('#0B1F3A') as Rgba;
  const { hue, sat } = hueSat(navy);
  assert.ok(hue >= 180 && hue <= 300 && sat > 0.12);
  const purple = parseColour('rgb(91, 33, 182)') as Rgba;
  assert.ok(hueSat(purple).hue >= 180 && hueSat(purple).hue <= 300);
  const warm = parseColour('#14130F') as Rgba;
  assert.ok(hueSat(warm).sat <= 0.12 || hueSat(warm).hue < 180);
});

test('no navy, blue or purple colour literal anywhere in the chamber assets', () => {
  const files = scannedFiles();
  assert.ok(files.includes('chamber-theme.css') && files.includes('council-theme.css'));
  for (const file of files) {
    const bad = offending(file, (c) => {
      const { hue, sat } = hueSat(c);
      return hue >= 180 && hue <= 300 && sat > 0.12;
    });
    assert.deepEqual(bad, [], `${file} carries a cool-hue colour: ${bad.join(', ')}`);
  }
});

test('no green colour literal in the stylesheets (cream, black and gold only)', () => {
  for (const file of scannedFiles().filter((f) => f.endsWith('.css'))) {
    const bad = offending(file, (c) => {
      const { hue, sat } = hueSat(c);
      return hue >= 75 && hue < 180 && sat > 0.12;
    });
    assert.deepEqual(bad, [], `${file} carries a green colour: ${bad.join(', ')}`);
  }
});

test('legacy council-theme.css and council-journey.css carry no brand-external palette variables', () => {
  for (const file of ['council-theme.css', 'council-journey.css']) {
    const text = stripComments(read(file));
    assert.doesNotMatch(text, /var\(--(?:brand|bcc)-/, `${file} still reads the per-client brand scale`);
  }
});

// A colour word only counts when it is not part of an identifier, so var(--ch-gold) is fine.
const NAMED = /(?:color|background(?:-color)?|border(?:-[a-z]+)*|outline(?:-color)?|box-shadow|text-shadow|fill|stroke)\s*:[^;{}]*(?<![\w-])(?:white|black|red|blue|navy|green|gray|grey|gold|cream|purple|orange|yellow)(?![\w-])/i;

test('the named-colour check ignores token references and catches real colour words', () => {
  assert.doesNotMatch('border: 1px solid var(--ch-gold)', NAMED);
  assert.doesNotMatch('color: var(--ch-black); background: var(--ch-cream)', NAMED);
  assert.match('color: gold', NAMED);
  assert.match('border: 1px solid white', NAMED);
  assert.match('background: var(--ch-surface-1) url(x) navy', NAMED);
});

test('only chamber-theme.css holds colour literals among the chamber-*.css files', () => {
  for (const file of ['chamber-shell.css', 'chamber-decision.css', 'chamber-room.css', 'chamber-keypoints.css', 'chamber-seatcard.css']) {
    if (!existsSync(join(chamberDir, file))) continue; // owned by another unit; checked once it lands
    const text = stripComments(read(file));
    assert.deepEqual(text.match(LITERAL) ?? [], [], `${file} has a raw colour literal; use var(--ch-*)`);
    assert.doesNotMatch(text, NAMED, `${file} uses a named colour; use var(--ch-*)`);
  }
  for (const file of readdirSync(chamberDir).filter((f) => /^chamber-.*\.css$/.test(f) && f !== 'chamber-theme.css')) {
    assert.deepEqual(literalsIn(read(file)), [], `${file} has a raw colour literal; use var(--ch-*)`);
  }
});

// ── tokens ─────────────────────────────────────────────────────────────────

test('the contract tokens exist with their exact values', () => {
  const expected: Record<string, string> = {
    '--ch-black': '#000000',
    '--ch-gold': '#C9A227',
    '--ch-cream': '#F5F0E8',
    '--ch-bg': 'var(--ch-black)',
    '--ch-surface-1': '#0C0B09',
    '--ch-surface-2': '#14130F',
    '--ch-surface-3': '#1D1B16',
    '--ch-line': 'rgba(245, 240, 232, .12)',
    '--ch-line-strong': 'rgba(245, 240, 232, .24)',
    '--ch-ink': 'var(--ch-cream)',
    '--ch-ink-muted': 'rgba(245, 240, 232, .70)',
    '--ch-ink-faint': 'rgba(245, 240, 232, .56)',
    '--ch-gold-strong': '#DDB43A',
    '--ch-gold-soft': 'rgba(201, 162, 39, .16)',
    '--ch-on-gold': '#000000',
    '--ch-grid': 'rgba(245, 240, 232, .04)',
    '--ch-font': "'Inter', 'Helvetica Neue', Arial, system-ui, sans-serif",
    '--ch-radius-panel': '18px',
    '--ch-radius-card': '12px',
    '--ch-radius-chip': '6px',
    '--ch-radius-pill': '999px',
    '--ch-space-1': '4px',
    '--ch-space-2': '8px',
    '--ch-space-3': '12px',
    '--ch-space-4': '16px',
    '--ch-space-5': '24px',
    '--ch-space-6': '32px',
    '--ch-dur': '200ms',
    '--ch-ease': 'cubic-bezier(.22, .61, .36, 1)',
  };
  for (const [name, value] of Object.entries(expected)) {
    assert.equal(chTokens.get(name), value, name);
  }
});

test('neutral surfaces are warm black: red >= green >= blue, so nothing reads navy', () => {
  for (const name of ['--ch-bg', '--ch-surface-1', '--ch-surface-2', '--ch-surface-3']) {
    const c = resolveToken(name, chTokens);
    assert.ok(c.r >= c.g && c.g >= c.b, `${name} is not warm neutral: ${c.r},${c.g},${c.b}`);
  }
});

const SURFACES = ['--ch-bg', '--ch-surface-1', '--ch-surface-2', '--ch-surface-3'];

test('WCAG: ink, ink-muted and ink-faint reach 4.5:1 on every chamber surface', () => {
  for (const ink of ['--ch-ink', '--ch-ink-muted', '--ch-ink-faint']) {
    for (const surface of SURFACES) {
      const bg = resolveToken(surface, chTokens);
      const ratio = contrast(resolveToken(ink, chTokens), bg);
      assert.ok(ratio >= 4.5, `${ink} on ${surface} is ${ratio.toFixed(2)}:1`);
    }
  }
});

test('WCAG: gold on black reaches 4.5:1, and black on gold fills do too', () => {
  const black = resolveToken('--ch-black', chTokens);
  assert.ok(contrast(resolveToken('--ch-gold', chTokens), black) >= 4.5);
  assert.ok(contrast(resolveToken('--ch-gold-strong', chTokens), black) >= 4.5);
  for (const fill of ['--ch-gold', '--ch-gold-strong']) {
    const ratio = contrast(resolveToken('--ch-on-gold', chTokens), resolveToken(fill, chTokens));
    assert.ok(ratio >= 4.5, `on-gold on ${fill} is ${ratio.toFixed(2)}:1`);
  }
});

test('WCAG: the legacy council scope (cream canvas) keeps 4.5:1 for its text pairs', () => {
  const light = ['--council-canvas', '--council-surface', '--council-surface-2'];
  for (const ink of ['--council-ink', '--council-ink-soft', '--council-ink-faint', '--council-accent-ink', '--council-state-oppose', '--council-state-support']) {
    for (const surface of light) {
      const ratio = contrast(resolveToken(ink, councilTokens), resolveToken(surface, councilTokens));
      assert.ok(ratio >= 4.5, `${ink} on ${surface} is ${ratio.toFixed(2)}:1`);
    }
  }
  const wash = resolveToken('--council-accent-wash', councilTokens);
  for (const ink of ['--council-ink', '--council-accent-ink', '--council-state-uncertain']) {
    const ratio = contrast(resolveToken(ink, councilTokens), wash);
    assert.ok(ratio >= 4.5, `${ink} on accent-wash is ${ratio.toFixed(2)}:1`);
  }
  for (const fill of ['--council-accent', '--council-accent-hover']) {
    const ratio = contrast(resolveToken('--council-on-accent', councilTokens), resolveToken(fill, councilTokens));
    assert.ok(ratio >= 4.5, `on-accent on ${fill} is ${ratio.toFixed(2)}:1`);
  }
  // Focus ring is a graphic: 3:1 against the canvas.
  assert.ok(contrast(resolveToken('--council-accent-ink', councilTokens), resolveToken('--council-canvas', councilTokens)) >= 3);
});

test('WCAG: the legacy warm-black stage keeps 4.5:1 for its text pairs', () => {
  for (const ink of ['--council-stage-ink', '--council-stage-muted', '--council-state-support', '--council-state-oppose', '--council-state-uncertain', '--council-state-info']) {
    for (const surface of ['--council-stage', '--council-stage-raised']) {
      const ratio = contrast(resolveToken(ink, stageTokens), resolveToken(surface, stageTokens));
      assert.ok(ratio >= 4.5, `${ink} on ${surface} is ${ratio.toFixed(2)}:1`);
    }
  }
  const stage = resolveToken('--council-stage', stageTokens);
  assert.ok(stage.r >= stage.g && stage.g >= stage.b, 'stage is warm black');
});

test('legacy tokens used by the advisors and journey pages are all defined', () => {
  const defined = new Set([...councilTokens.keys(), ...stageTokens.keys()]);
  for (const file of ['council-journey.css', 'council-room.css', 'advisors.html', 'not-packaged.html']) {
    for (const m of stripComments(read(file)).matchAll(/var\(\s*(--council-[\w-]+)\s*([,)])/g)) {
      assert.ok(defined.has(m[1]) || m[2] === ',', `${file} uses undefined ${m[1]}`);
    }
  }
  for (const file of ['advisors.html', 'not-packaged.html']) {
    const html = read(file);
    for (const m of html.matchAll(/<link rel="stylesheet" href="\.\/([^"]+)"/g)) {
      assert.ok(existsSync(join(chamberDir, m[1])), `${file} links missing ${m[1]}`);
    }
  }
});

// ── primitives ─────────────────────────────────────────────────────────────

/** Body of the first rule whose selector is exactly `selector`, ignoring media queries. */
function rule(css: string, selector: string): string {
  const clean = stripComments(css);
  const idx = clean.search(new RegExp(`(^|[\\n}])\\s*${selector.replace(/[.*+?^${}()|[\]\\:]/g, '\\$&')}\\s*\\{`));
  assert.ok(idx >= 0, `rule ${selector} missing`);
  const open = clean.indexOf('{', idx);
  return clean.slice(open + 1, clean.indexOf('}', open));
}

/** The joined bodies of every `@media <query>` block. */
function media(css: string, query: string): string {
  const clean = stripComments(css);
  const bodies: string[] = [];
  for (let from = clean.indexOf(`@media ${query}`); from >= 0; from = clean.indexOf(`@media ${query}`, from + 1)) {
    const open = clean.indexOf('{', from);
    let depth = 0;
    for (let i = open; i < clean.length; i++) {
      if (clean[i] === '{') depth++;
      if (clean[i] === '}' && --depth === 0) {
        bodies.push(clean.slice(open + 1, i));
        break;
      }
    }
  }
  assert.ok(bodies.length > 0, `@media ${query} missing`);
  return bodies.join('\n');
}

test('.ch body, .ch-app frame and .ch-main', () => {
  const ch = rule(theme, '.ch');
  assert.match(ch, /background:\s*var\(--ch-bg\)/);
  assert.match(ch, /color:\s*var\(--ch-ink\)/);
  assert.match(ch, /font-family:\s*var\(--ch-font\)/);
  assert.match(ch, /font-size:\s*16px/);
  const app = rule(theme, '.ch-app');
  assert.match(app, /max-width:\s*1480px/);
  assert.match(app, /margin-inline:\s*auto/);
  assert.match(app, /padding:\s*var\(--ch-space-4\)/, '16px phone gutter');
  assert.match(rule(media(theme, '(min-width: 600px)'), '.ch-app'), /padding:\s*var\(--ch-space-5\)/, '24px wide padding');
  const wide = rule(media(theme, '(min-width: 1200px)'), '.ch-app');
  assert.match(wide, /border-radius:\s*24px/);
  assert.match(wide, /border:\s*1px solid var\(--ch-line\)/);
  assert.ok(rule(theme, '.ch-main'));
});

test('.ch-stage-grid: one column below 1200px, room + 320px key points from 1200px', () => {
  const base = rule(theme, '.ch-stage-grid');
  assert.match(base, /display:\s*grid/);
  assert.match(base, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;/);
  assert.match(base, /gap:\s*var\(--ch-space-4\)/);
  assert.match(base, /align-items:\s*start/);
  const wide = rule(media(theme, '(min-width: 1200px)'), '.ch-stage-grid');
  assert.match(wide, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+320px/);
  // No other breakpoint may split the grid.
  assert.equal((stripComments(theme).match(/grid-template-columns:[^;]*320px/g) ?? []).length, 1);
});

test('.ch-panel, .ch-eyebrow, .ch-chip and .ch-sr-only', () => {
  const panel = rule(theme, '.ch-panel');
  assert.match(panel, /background:\s*var\(--ch-surface-1\)/);
  assert.match(panel, /border:\s*1px solid var\(--ch-line\)/);
  assert.match(panel, /border-radius:\s*var\(--ch-radius-panel\)/);
  const eyebrow = rule(theme, '.ch-eyebrow');
  assert.match(eyebrow, /font-size:\s*11px/);
  assert.match(eyebrow, /font-weight:\s*700/);
  assert.match(eyebrow, /letter-spacing:\s*\.14em/);
  assert.match(eyebrow, /text-transform:\s*uppercase/);
  assert.match(eyebrow, /color:\s*var\(--ch-ink-muted\)/);
  assert.match(rule(theme, '.ch-chip'), /border-radius:\s*var\(--ch-radius-chip\)/);
  assert.match(rule(theme, '.ch-chip--gold'), /background:\s*var\(--ch-gold\)/);
  const sr = rule(theme, '.ch-sr-only');
  assert.match(sr, /position:\s*absolute/);
  assert.match(sr, /width:\s*1px/);
  assert.match(sr, /overflow:\s*hidden/);
});

test('.ch-btn is a pill with gold hover; primary is a gold fill with black text', () => {
  const btn = rule(theme, '.ch-btn');
  assert.match(btn, /border:\s*1px solid var\(--ch-line-strong\)/);
  assert.match(btn, /border-radius:\s*var\(--ch-radius-pill\)/);
  assert.match(btn, /min-height:\s*40px/);
  assert.match(btn, /font:\s*600 13px/);
  assert.match(rule(theme, '.ch-btn:hover'), /border-color:\s*var\(--ch-gold\)/);
  assert.match(rule(media(theme, '(pointer: coarse)'), '.ch-btn'), /min-height:\s*44px/);
  const primary = rule(theme, '.ch-btn--primary');
  assert.match(primary, /background:\s*var\(--ch-gold\)/);
  assert.match(primary, /color:\s*var\(--ch-on-gold\)/);
  assert.match(rule(theme, '.ch-btn--primary:hover'), /background:\s*var\(--ch-gold-strong\)/);
});

test('keyboard focus is a 2px gold ring offset by 2px', () => {
  const focus = rule(theme, '.ch :focus-visible');
  assert.match(focus, /outline:\s*2px solid var\(--ch-focus\)/);
  assert.match(focus, /outline-offset:\s*2px/);
  assert.equal(chTokens.get('--ch-focus'), 'var(--ch-gold)');
});

test('.ch-dialog blurs and dims the whole page behind it', () => {
  const dialog = rule(theme, '.ch-dialog');
  assert.match(dialog, /width:\s*min\(590px,\s*100vw - 32px\)/);
  assert.match(dialog, /padding:\s*20px/);
  assert.match(dialog, /background:\s*var\(--ch-surface-2\)/);
  assert.match(dialog, /border:\s*1px solid var\(--ch-line-strong\)/);
  assert.match(dialog, /border-radius:\s*var\(--ch-radius-card\)/);
  assert.match(dialog, /color:\s*var\(--ch-ink\)/);
  assert.doesNotMatch(dialog, /display\s*:/, 'a display rule would defeat dialog:not([open])');
  const backdrop = rule(theme, '.ch-dialog::backdrop');
  assert.match(backdrop, /background:\s*rgba\(0,\s*0,\s*0,\s*\.55\)/);
  assert.match(backdrop, /(?<!-webkit-)backdrop-filter:\s*blur\(8px\)/);
});

test('prefers-reduced-motion zeroes animation and transition durations everywhere', () => {
  const block = media(theme, '(prefers-reduced-motion: reduce)');
  assert.match(block, /\*,\s*\*::before,\s*\*::after/);
  assert.match(block, /animation-duration:\s*0s\s*!important/);
  assert.match(block, /transition-duration:\s*0s\s*!important/);
  assert.match(block, /animation-iteration-count:\s*1\s*!important/);
});

test('prefers-contrast: more strengthens hairlines and secondary ink', () => {
  const block = media(theme, '(prefers-contrast: more)');
  assert.match(block, /--ch-line-strong/);
  assert.match(block, /--ch-ink-faint/);
});

test('the theme carries no external URL and no import', () => {
  const text = stripComments(theme);
  assert.doesNotMatch(text, /https?:\/\//);
  assert.doesNotMatch(text, /@import/);
  assert.doesNotMatch(text, /url\(/);
});

test('wide app frame floats with a 24px gap on every side from 1200px', () => {
  const block = media(theme, '(min-width: 1200px)');
  assert.match(rule(block, '.ch-app'), /width:\s*calc\(100%\s*-\s*48px\)/);
});

test('the legacy SVG medallions are desaturated and warmed to brand on council-theme pages', () => {
  assert.match(
    read('council-theme.css'),
    /\.council-theme img\[src\$="\.svg"\]\s*\{[^}]*filter:\s*grayscale\(1\)\s*sepia\(/,
  );
});
