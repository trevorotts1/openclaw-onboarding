#!/usr/bin/env python3
"""validate_page.py — Skill 71 check C2 (enforcement order 2026-10-05).

Renders an HTML page at 320/390/768/1440 with Playwright (Chromium) and checks,
after the same eager-load routine render_page.py uses:

  1. Colors        every visible element's computed color, background-color,
                   per-side border colors (only when border width > 0), and SVG
                   fill/stroke must sit within `color_tolerance` per RGB channel
                   of a brand palette color; `logo_only_colors` are allowed only
                   inside a [data-brand="logo"] subtree. Offenders are reported
                   as `selector -> rgb -> nearest brand color`.
  2. Fonts         the first family of computed font-family on every element
                   with text must be a brand font and never in banned_fonts;
                   document.fonts.check must be true for each brand font.
  3. Logo          (BlackCEO pages) a visible [data-brand="logo"] element within
                   the first viewport at every width.
  4. Founder photo (BlackCEO pages) the image in [data-slot="founder"] must have
                   a SHA-256 equal to one of brand founder_photos. A generated
                   image or an empty box fails. No founder slot at all = pass
                   (not every page type carries one).
  5. Placeholders  visible text and alt/title/aria-label must not match
                   \\[[A-Z0-9_ ]{3,}\\], PLACEHOLDER, NOT WIRED, TODO,
                   lorem ipsum, {{. WARN instead of FAIL when intake.test_run.
  6. Images        mode page: all loaded, none shipping loading="lazy", and each
                   mapped image's rendered width at 1440 >= 90% of its
                   desktop_slot_px from image-map.json.
                   mode mockup: [data-image-slot] blocks at the exact declared
                   slot size.
  7. Overflow      document.scrollingElement.scrollWidth <= innerWidth at every
                   width.
  8. Copy parity   every paragraph/heading/button label in copy/public-copy.md
                   (whitespace-normalized) appears in the DOM innerText.
  9. Mobile 390    body text >= 18px, microcopy ([data-microcopy], small,
                   figcaption, cite, footer) >= 16px, buttons >= 56px tall.
 10. Layout        (Item 15) six structural metrics measured at the widest
                   viewport (1440 when requested): section signature
                   diversity, image ratio diversity, centering ratio,
                   repeated card grids, empty section width, CTA sameness.
                   Thresholds come from the brand file's `layout_thresholds`
                   object, falling back to DEFAULT_LAYOUT_THRESHOLDS. Each
                   metric prints its measured value on PASS (`LAYOUT PASS:`)
                   and a named `LAYOUT:` failure line on FAIL. The metric
                   functions are pure Python over the geometry extracted by
                   LAYOUT_JS, so they are unit-testable without a browser;
                   compare_sheet.py imports section_signature from here.

Writes <run_dir>/responsive-html/validate-page.json (page mode) or
<run_dir>/visual-mockup/validate-page.json (mockup mode).

Exit codes: 0 pass, 1 fail (each reason on its own line), 2 unreadable input.
Python 3 stdlib + Pillow + Playwright only.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import composition  # noqa: E402  composition treatments: budget and pixel checks

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    # Non-fatal at import time: this module is also imported as a library
    # (compare_sheet.py imports the Item 15 signature function, and the
    # layout-metric unit tests import the pure geometry functions). The CLI
    # still fails closed with exit 2 in main() when Playwright is absent.
    sync_playwright = None

    class PWTimeout(Exception):  # type: ignore[no-redef]
        pass

DEFAULT_WIDTHS = [320, 390, 768, 1440]
VIEWPORT_H = 800
LOAD_TIMEOUT_MS = 30000
UNSUPPLIED = ("TREVOR_MUST_SUPPLY", "CLIENT_MUST_SUPPLY")

PLACEHOLDER_PATTERNS = [
    (re.compile(r"\[[A-Z0-9_ ]{3,}\]"), "bracket placeholder"),
    (re.compile(r"\bPLACEHOLDER\b", re.I), "PLACEHOLDER text"),
    (re.compile(r"\bNOT WIRED\b", re.I), "NOT WIRED text"),
    (re.compile(r"\bTODO\b"), "TODO text"),
    (re.compile(r"lorem ipsum", re.I), "lorem ipsum"),
    (re.compile(r"\{\{"), "unfilled template braces"),
]

EAGER_JS = """() => {
  document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
  return true;
}"""

SCROLL_JS = """() => new Promise(resolve => {
  let y = 0;
  const step = () => {
    window.scrollTo(0, y);
    y += 400;
    if (y <= document.body.scrollHeight + 800) { setTimeout(step, 40); }
    else { window.scrollTo(0, 0); setTimeout(resolve, 120); }
  };
  step();
})"""

ALL_IMAGES_LOADED_JS = (
    "() => Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)"
)

COLORS_JS = """(args) => {
  const palette = args.palette, logoOnly = args.logoOnly, tol = args.tolerance;
  const parse = (v) => {
    if (!v || v === 'none') return null;
    const m = v.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const parts = m[1].split(/[,/\\s]+/).filter(Boolean).map(Number);
    if (parts.length < 3) return null;
    return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
  };
  const nearest = (rgb, list) => {
    let best = null, bd = Infinity;
    for (const c of list) {
      const d = Math.max(Math.abs(rgb.r - c.r), Math.abs(rgb.g - c.g), Math.abs(rgb.b - c.b));
      if (d < bd) { bd = d; best = c; }
    }
    return best ? {name: best.name, hex: best.hex, dist: bd} : null;
  };
  const sel = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) return s + '#' + el.id;
    if (typeof el.className === 'string' && el.className.trim())
      return s + '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.');
    return s;
  };
  const out = [];
  const push = (el, kind, v) => {
    const rgb = parse(v);
    if (!rgb || rgb.a === 0) return;
    const inLogo = !!(el.closest && el.closest('[data-brand="logo"]'));
    const allowed = inLogo ? palette.concat(logoOnly) : palette;
    const n = nearest(rgb, allowed);
    if (n && n.dist > tol) {
      const nAll = nearest(rgb, palette.concat(logoOnly));
      out.push({selector: sel(el), kind: kind, value: v, nearest: nAll.name + ' ' + nAll.hex});
    }
  };
  const els = [document.body].concat(Array.from(document.body.querySelectorAll('*')));
  for (const el of els) {
    if (!el || el.nodeType !== 1) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (el.namespaceURI === 'http://www.w3.org/2000/svg') {
      push(el, 'fill', st.fill);
      push(el, 'stroke', st.stroke);
      continue;
    }
    push(el, 'color', st.color);
    push(el, 'background', st.backgroundColor);
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const w = parseFloat(st['border' + side + 'Width']);
      if (w > 0) push(el, 'border-' + side.toLowerCase(), st['border' + side + 'Color']);
    }
  }
  return out;
}"""

FONTS_JS = """(args) => {
  const norm = (f) => (f || '').replace(/["']/g, '').trim().toLowerCase();
  const brandSet = new Set(args.brandFonts.map(norm));
  const bannedSet = new Set(args.banned.map(norm));
  const bad = [];
  const seen = new Set();
  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    if (el instanceof SVGElement || el.namespaceURI === 'http://www.w3.org/2000/svg') continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    let hasText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) { hasText = true; break; }
    }
    if (!hasText) continue;
    const first = st.fontFamily.split(',')[0].trim();
    const key = norm(first);
    if (seen.has(key)) continue;
    seen.add(key);
    let s = el.tagName.toLowerCase();
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\\s+/)[0];
    const bannedHit = bannedSet.has(key);
    if (bannedHit || !brandSet.has(key))
      bad.push({selector: s, font: first, banned: bannedHit});
  }
  const unavailable = [];
  for (const f of args.brandFonts) {
    try {
      if (!document.fonts.check('16px "' + f + '"')) unavailable.push(f);
    } catch (e) { unavailable.push(f + ' (check error)'); }
  }
  return {bad: bad, unavailable: unavailable};
}"""

LOGO_JS = """(args) => {
  const el = document.querySelector('[data-brand="logo"]');
  if (!el) return {found: false, visible: false};
  const st = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const visible = st.display !== 'none' && st.visibility !== 'hidden' &&
    r.width > 0 && r.height > 0 && r.top < args.viewportH && r.bottom > 0;
  return {found: true, visible: visible};
}"""

PLACEHOLDER_JS = """(args) => {
  const pats = args.patterns.map(p => [new RegExp(p.source, p.flags), p.name]);
  const res = [];
  const scan = (where, text) => {
    if (!text) return;
    for (const [re, name] of pats) {
      const m = re.exec(text);
      if (m) res.push({where: where, match: m[0].slice(0, 80), name: name});
    }
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seenEls = new Set();
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent;
    if (!t || !t.trim()) continue;
    const el = n.parentElement;
    if (!el || seenEls.has(el)) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    seenEls.add(el);
    scan('text:' + el.tagName.toLowerCase(), t);
  }
  for (const el of document.querySelectorAll('[alt],[title],[aria-label]')) {
    for (const attr of ['alt', 'title', 'aria-label']) {
      scan(attr + ':' + el.tagName.toLowerCase(), el.getAttribute(attr));
    }
  }
  return res;
}"""

IMAGES_JS = """() => {
  const out = {imgs: [], slots: []};
  for (const img of document.images) {
    const r = img.getBoundingClientRect();
    const st = getComputedStyle(img);
    const visible = st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    out.imgs.push({
      src: img.currentSrc || img.src,
      slot: img.getAttribute('data-image-slot'),
      founder: !!(img.closest && img.closest('[data-slot="founder"]')) ||
               img.getAttribute('data-slot') === 'founder',
      complete: img.complete && img.naturalWidth > 0,
      width: r.width,
      visible: visible
    });
  }
  for (const el of document.querySelectorAll('[data-image-slot]')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    const kind = el.tagName.toLowerCase() === 'img' ? 'img' : 'block';
    out.slots.push({slot: el.getAttribute('data-image-slot'), width: r.width, height: r.height, kind: kind});
  }
  return out;
}"""

OVERFLOW_JS = "() => ({scrollWidth: document.scrollingElement.scrollWidth, innerWidth: window.innerWidth})"

FOUNDER_JS = """() => {
  const host = document.querySelector('[data-slot="founder"]');
  if (!host) return {present: false};
  const img = host.tagName.toLowerCase() === 'img' ? host : host.querySelector('img');
  if (!img) return {present: true, hasImg: false};
  const st = getComputedStyle(img);
  const r = img.getBoundingClientRect();
  const empty = st.display === 'none' || r.width === 0;
  return {present: true, hasImg: true, src: img.currentSrc || img.src, empty: empty};
}"""

INNERTEXT_JS = "() => document.body.innerText"

MOBILE_TEXT_JS = """() => {
  const issues = [];
  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    if (el instanceof SVGElement || el.namespaceURI === 'http://www.w3.org/2000/svg') continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    let hasText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) { hasText = true; break; }
    }
    if (!hasText) continue;
    let s = el.tagName.toLowerCase();
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\\s+/)[0];
    const micro = el.matches('[data-microcopy], small, figcaption, cite, footer, footer *');
    const floorPx = micro ? 16 : 18;
    const size = parseFloat(st.fontSize);
    if (size < floorPx) issues.push({selector: s, size: size, floorPx: floorPx, micro: micro});
  }
  return issues;
}"""

MOBILE_BUTTONS_JS = """() => {
  const issues = [];
  for (const el of document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    if (el.tagName === 'A' && st.display === 'inline') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    let s = el.tagName.toLowerCase();
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\\s+/)[0];
    if (r.height < 56) issues.push({selector: s, height: r.height});
  }
  return issues;
}"""

# --------------------------------------------------------------------------
# Item 15: layout metrics (pure geometry layer + browser extraction).
#
# LAYOUT_JS extracts raw geometry only. Every metric below is a pure Python
# function over that data, so the whole layer is unit-testable without a
# browser (tests/test_layout_metrics.py). compare_sheet.py imports
# section_signature / image_placement_class / heading_body_ratio from here:
# one implementation, two callers.
# --------------------------------------------------------------------------

LAYOUT_JS = """() => {
  const vis = (el) => {
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden';
  };
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {x: r.x + window.scrollX, y: r.y + window.scrollY,
            width: r.width, height: r.height,
            left: r.left + window.scrollX, right: r.right + window.scrollX,
            top: r.top + window.scrollY, bottom: r.bottom + window.scrollY};
  };
  const selOf = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) return s + '#' + el.id;
    if (typeof el.className === 'string' && el.className.trim())
      return s + '.' + el.className.trim().split(/ +/).filter(Boolean).slice(0, 2).join('.');
    return s;
  };
  const skeleton = (el, depth) => {
    const kids = Array.from(el.children || []);
    if (depth <= 0 || kids.length === 0) return el.tagName.toLowerCase();
    return el.tagName.toLowerCase() + '(' +
      kids.slice(0, 8).map(c => skeleton(c, depth - 1)).join(',') + ')';
  };
  const hasDirectText = (el) => {
    for (const n of el.childNodes)
      if (n.nodeType === 3 && n.textContent.trim()) return true;
    return false;
  };
  const sections = Array.from(document.querySelectorAll('section'))
    .filter(s => !s.parentElement || !s.parentElement.closest('section'))
    .filter(vis);
  const sectionData = sections.map((sec, idx) => {
    const sr = rectOf(sec);
    const st = getComputedStyle(sec);
    let layoutKids = Array.from(sec.children).filter(vis);
    if (layoutKids.length === 1) {
      const inner = Array.from(layoutKids[0].children).filter(vis);
      if (inner.length >= 2) layoutKids = inner;
    }
    const children = layoutKids.map(ch => {
      const cst = getComputedStyle(ch);
      return {selector: selOf(ch), rect: rectOf(ch), textAlign: cst.textAlign,
              display: cst.display, hasText: hasDirectText(ch)};
    });
    const radiusPx = (st, key, r) => {
      const v = (st[key] || '0').split(' ')[0];
      const n = parseFloat(v) || 0;
      const cap = Math.min(r.width, r.height) / 2;
      const px = v.endsWith('%') ? Math.min(n / 100 * r.width, n / 100 * r.height) : n;
      return Math.min(px, cap);
    };
    const images = Array.from(sec.querySelectorAll('img')).filter(vis).map(im => {
      const r = rectOf(im);
      const ist = getComputedStyle(im);
      const tr = im.closest('[data-treatment]');
      return {selector: selOf(im), rect: r, width: r.width, height: r.height,
              slot: im.getAttribute('data-image-slot'),
              treatment: tr ? tr.getAttribute('data-treatment') : null,
              subjectZone: im.getAttribute('data-subject-zone'),
              clipPath: ist.clipPath,
              radii: ['borderTopLeftRadius', 'borderTopRightRadius',
                      'borderBottomRightRadius', 'borderBottomLeftRadius']
                .map(k => radiusPx(ist, k, r))};
    });
    const bgImages = [sec].concat(Array.from(sec.querySelectorAll('*'))).filter(vis)
      .filter(el => (getComputedStyle(el).backgroundImage || '').includes('url('))
      .map(el => rectOf(el));
    const headRects = Array.from(sec.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(vis)
      .slice(0, 1).map(h => rectOf(h));
    const texts = Array.from(sec.querySelectorAll('*'))
      .filter(el => vis(el) && hasDirectText(el))
      .map(el => {
        const tst = getComputedStyle(el);
        return {selector: selOf(el), textAlign: tst.textAlign,
                fontSize: parseFloat(tst.fontSize)};
      });
    const heads = Array.from(sec.querySelectorAll('h1,h2,h3,h4,h5,h6'))
      .filter(vis)
      .map(h => parseFloat(getComputedStyle(h).fontSize)).filter(v => v > 0);
    const paras = Array.from(sec.querySelectorAll('p')).filter(vis)
      .map(p => parseFloat(getComputedStyle(p).fontSize)).filter(v => v > 0);
    const contentRects = [];
    sec.querySelectorAll('*').forEach(el => {
      if (!vis(el)) return;
      const tag = el.tagName.toLowerCase();
      if (hasDirectText(el) || ['img', 'button', 'video', 'input'].includes(tag)) {
        const r = rectOf(el);
        if (r.width > 0) contentRects.push(r);
      }
    });
    return {index: idx, selector: selOf(sec), id: sec.id || null, rect: sr,
            background: st.backgroundColor, display: st.display,
            gridColumns: st.gridTemplateColumns,
            flexDirection: st.flexDirection,
            children: children, images: images, texts: texts,
            bgImages: bgImages, headRects: headRects,
            treatment: sec.getAttribute('data-treatment'),
            headingFontSize: heads.length ? heads[0] : null,
            bodyFontSize: paras.length ? paras[Math.floor(paras.length / 2)] : null,
            contentRects: contentRects};
  });
  const groups = [];
  const walk = (el) => {
    const kids = Array.from(el.children || []).filter(vis);
    if (kids.length >= 3) {
      groups.push({parent: selOf(el), children: kids.map(k => {
        const r = rectOf(k);
        return {selector: selOf(k), width: r.width, height: r.height,
                structure: skeleton(k, 3)};
      })});
    }
    kids.forEach(walk);
  };
  if (document.body) walk(document.body);
  const ctaSel = 'button, [role="button"], input[type="submit"], ' +
    'input[type="button"], a.cta, a.btn, a.button, .cta';
  const ctaSeen = new Set();
  const ctas = [];
  document.querySelectorAll(ctaSel).forEach(el => {
    if (ctaSeen.has(el) || !vis(el)) return;
    ctaSeen.add(el);
    const r = rectOf(el);
    if (r.width === 0 && r.height === 0) return;
    ctas.push({selector: selOf(el), width: r.width, height: r.height,
               background: getComputedStyle(el).backgroundColor});
  });
  const contentImages = [];
  document.querySelectorAll('img').forEach(im => {
    if (!vis(im)) return;
    if (im.closest && im.closest('[data-brand="logo"]')) return;
    const r = rectOf(im);
    if (r.width === 0 || r.height === 0) return;
    contentImages.push({selector: selOf(im), width: r.width, height: r.height,
                        ratio: r.width / r.height,
                        slot: im.getAttribute('data-image-slot')});
  });
  return {sections: sectionData, siblingGroups: groups, ctas: ctas,
          contentImages: contentImages};
}"""

COMPOSITION_JS = """() => {
  const vis = (el) => { const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden'; };
  const rect = (el) => { const r = el.getBoundingClientRect();
    return {left: r.left + scrollX, right: r.right + scrollX, top: r.top + scrollY,
            bottom: r.bottom + scrollY, width: r.width, height: r.height}; };
  const rgbOf = (c) => { const m = (c || '').match(/rgba?\\(([^)]+)\\)/);
    return m ? m[1].split(',').slice(0, 3).map(Number) : null; };
  const bgOf = (el) => { let n = el;
    while (n) { const c = getComputedStyle(n).backgroundColor;
      const m = c.match(/rgba?\\(([^)]+)\\)/);
      if (m) { const p = m[1].split(',').map(Number);
        if (p.length < 4 || p[3] > 0.99) return p.slice(0, 3); }
      n = n.parentElement; }
    return [255, 255, 255]; };
  // band-light-field: everything painted in front of the field (buttons, cards,
  // icons, pictures) is marked so the field can be sampled with it hidden. A
  // descendant that covers 60 percent or more of the band is the field itself
  // (a full-bleed image or tint layer), and so is any ancestor of one.
  const markForeground = (el) => {
    const fr = el.getBoundingClientRect(); const frameArea = fr.width * fr.height;
    const isField = (d) => { const r = d.getBoundingClientRect();
      return frameArea > 0 && r.width * r.height >= 0.6 * frameArea; };
    const fields = Array.from(el.querySelectorAll('*')).filter(isField);
    Array.from(el.querySelectorAll('*')).forEach(d => {
      if (fields.some(f => f === d || f.contains(d) || d.contains(f))) return;
      const st = getComputedStyle(d); const bg = rgbOf(st.backgroundColor);
      const a = (st.backgroundColor.match(/rgba\\(([^)]+)\\)/) || [])[1];
      const alpha = a ? parseFloat(a.split(',')[3]) : 1;
      const solid = bg && alpha > 0.05;
      const bordered = ['Top', 'Right', 'Bottom', 'Left'].some(k =>
        parseFloat(st['border' + k + 'Width']) > 0 && st['border' + k + 'Style'] !== 'none');
      const media = ['IMG', 'SVG', 'VIDEO', 'CANVAS', 'PICTURE'].includes(d.tagName.toUpperCase());
      const bgImage = (st.backgroundImage || '').includes('url(') || (st.backgroundImage || '').includes('gradient');
      if (solid || bordered || media || bgImage || (st.boxShadow && st.boxShadow !== 'none'))
        d.setAttribute('data-comp-fg', '1');
    });
  };
  Array.from(document.querySelectorAll('[data-treatment="band-light-field"]')).filter(vis).forEach(markForeground);
  return Array.from(document.querySelectorAll('[data-treatment]')).filter(vis).map(el => {
    const img = el.tagName === 'IMG' ? el : el.querySelector('img');
    const texts = Array.from(el.querySelectorAll('h1,h2,h3,h4,h5,h6,p,figcaption,a,button,span,li'))
      .filter(t => vis(t) && Array.from(t.childNodes).some(n => n.nodeType === 3 && n.textContent.trim()))
      .slice(0, 8).map(t => { const st = getComputedStyle(t);
        return {rect: rect(t), color: rgbOf(st.color), fontSize: parseFloat(st.fontSize),
                bold: parseInt(st.fontWeight, 10) >= 700, onField: !t.closest('[data-comp-fg]'),
                words: (t.innerText || '').trim().split(/\\s+/).filter(Boolean).length}; });
    return {treatment: el.getAttribute('data-treatment'), frame: rect(el),
            slot: img ? img.getAttribute('data-image-slot') : el.getAttribute('data-image-slot'),
            img: img ? rect(img) : null, imgBackground: img ? bgOf(img.parentElement || img) : null,
            surface: bgOf(el), subjectZone: img ? img.getAttribute('data-subject-zone') : null,
            texts: texts};
  });
}"""

HIDE_TEXT_CSS = ("*{color:transparent!important;text-shadow:none!important}"
                 "[data-comp-fg]{visibility:hidden!important}")
TEXT_OVER_PHOTO = ("overlay-light", "overlay-dark-scrim", "caption-over-photo", "band-over-texture")


def composition_pixel_failures(page):
    """Q2, Q3, Q4 and Q6 on a built page, for elements that declare
    data-treatment. Pages that declare none are not touched. Two passes:
    the backdrop under each text box is sampled in a render with all text
    transparent, because sampling the normal render reads the glyphs."""
    from PIL import Image

    items = page.evaluate(COMPOSITION_JS)
    if not items:
        return []

    def shot(box):
        clip = {"x": max(0, int(box["left"])), "y": max(0, int(box["top"])),
                "width": max(1, int(box["right"] - box["left"])),
                "height": max(1, min(4000, int(box["bottom"] - box["top"])))}
        return Image.open(io.BytesIO(page.screenshot(full_page=True, clip=clip))).convert("RGB")

    out = []
    handle = page.add_style_tag(content=HIDE_TEXT_CSS)
    try:
        for item in items:
            tid, slot = item["treatment"], item.get("slot") or "section"
            where = f"COMPOSITION: slot {slot} treatment {tid}"
            if tid not in composition.treatments():
                out.append(f"{where}: unknown treatment id")
                continue
            if tid in ("mask-circle", "mask-pill", "mask-arch") and item.get("img"):
                ok, detail = composition.corner_test(
                    shot(item["img"]), tuple(item["imgBackground"]), tid.split("-")[1])
                if not ok:
                    out.append(f"{where}: shape check failed: {detail}")
            if tid == "band-light-field":
                # the field behind the type: text and foreground elements are
                # hidden in this render, and the ratio form holds on any palette
                ok, detail = composition.light_field_check(
                    shot(item["frame"]), tuple(item["surface"]))
                if not ok:
                    out.append(f"{where}: light-field check failed: {detail}")
            zone = None
            if item.get("subjectZone"):
                try:
                    zone = [float(v) for v in item["subjectZone"].split(",")]
                except ValueError:
                    zone = None
            frame = item.get("img") or item["frame"]
            for text in item.get("texts") or []:
                if tid == "band-light-field" and text.get("onField") and text.get("color"):
                    display = text["fontSize"] >= 24 or (text["fontSize"] >= 18.66 and text["bold"])
                    ok, ratio, need = composition.backdrop_contrast(
                        shot(text["rect"]), tuple(text["color"]), display)
                    if not ok:
                        out.append(f"{where}: text at {int(text['rect']['left'])},"
                                   f"{int(text['rect']['top'])} has contrast {ratio}:1 over the light field, "
                                   f"needs {need}:1")
                over = tid in TEXT_OVER_PHOTO
                if over and text.get("color"):
                    display = text["fontSize"] >= 24 or (text["fontSize"] >= 18.66 and text["bold"])
                    ok, ratio, need = composition.backdrop_contrast(
                        shot(text["rect"]), tuple(text["color"]), display)
                    if not ok:
                        out.append(f"{where}: text at {int(text['rect']['left'])},"
                                   f"{int(text['rect']['top'])} has contrast {ratio}:1 over its backdrop, "
                                   f"needs {need}:1")
                if over and text["words"] > composition.library()["thresholds"]["long_copy_words"]:
                    out.append(f"{where}: {text['words']} words sit directly on the photo "
                               f"(over {composition.library()['thresholds']['long_copy_words']}); "
                               "move long copy to a card, the scrim side, or a plain band")
                if over and not composition.safe_margin_ok(text["rect"], item["frame"]):
                    out.append(f"{where}: text sits inside the 5 percent safe margin of its frame")
                if zone and composition.face_zone_overlap(text["rect"], frame, zone):
                    out.append(f"{where}: text overlaps the subject zone (words over a face)")
    finally:
        try:
            handle.evaluate("e => e.remove()")
            page.evaluate("() => document.querySelectorAll('[data-comp-fg]')"
                          ".forEach(e => e.removeAttribute('data-comp-fg'))")
        except Exception:
            pass
    return out


WRAP_JS = """() => {
  const out = {scrollWidth: document.scrollingElement.scrollWidth,
               innerWidth: window.innerWidth, clipped: []};
  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    if (el instanceof SVGElement) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    if (el.children.length > 0) continue;
    if (el.scrollWidth > el.clientWidth + 2) {
      let s = el.tagName.toLowerCase();
      if (typeof el.className === 'string' && el.className.trim())
        s += '.' + el.className.trim().split(/ +/)[0];
      out.clipped.push({selector: s, scrollWidth: el.scrollWidth,
                        clientWidth: el.clientWidth});
      if (out.clipped.length >= 10) break;
    }
  }
  return out;
}"""

DEFAULT_LAYOUT_THRESHOLDS = {
    "signature_monotony_max_share": 0.60,
    "image_ratio_same_class_tolerance": 0.05,
    "image_ratio_min_images": 3,
    "centering_max_share": 0.70,
    "card_grid_min_repetitions": 3,
    "card_grid_size_tolerance": 0.02,
    "empty_width_min_span": 0.60,
    "cta_size_tolerance_px": 2,
    "single_cta_design": False,
    "card_grid_allowlist": [],
}

_LAYOUT_FLOAT_KEYS = (
    "signature_monotony_max_share",
    "image_ratio_same_class_tolerance",
    "centering_max_share",
    "card_grid_size_tolerance",
    "empty_width_min_span",
)
_LAYOUT_INT_KEYS = ("image_ratio_min_images", "card_grid_min_repetitions",
                    "cta_size_tolerance_px")


def load_layout_thresholds(brand):
    """Merge the brand file's layout_thresholds over the plan defaults.

    Reads the top-level `layout_thresholds` object; if page_design_rules is
    ever converted from a list to an object, its nested layout_thresholds is
    honored too. Unknown keys are ignored; unparseable values fall back to
    the code defaults (which are the FIX-PLAN Item 15 defaults)."""
    merged = dict(DEFAULT_LAYOUT_THRESHOLDS)
    sources = []
    if isinstance(brand.get("layout_thresholds"), dict):
        sources.append(brand["layout_thresholds"])
    rules = brand.get("page_design_rules")
    if isinstance(rules, dict) and isinstance(rules.get("layout_thresholds"), dict):
        sources.append(rules["layout_thresholds"])
    for src in sources:
        for key, value in src.items():
            if key in merged and value is not None:
                merged[key] = value
    for key in _LAYOUT_FLOAT_KEYS:
        try:
            merged[key] = float(merged[key])
        except (TypeError, ValueError):
            merged[key] = DEFAULT_LAYOUT_THRESHOLDS[key]
    for key in _LAYOUT_INT_KEYS:
        try:
            merged[key] = int(merged[key])
        except (TypeError, ValueError):
            merged[key] = DEFAULT_LAYOUT_THRESHOLDS[key]
    merged["single_cta_design"] = bool(merged.get("single_cta_design"))
    merged["card_grid_allowlist"] = [
        str(x) for x in (merged.get("card_grid_allowlist") or [])
    ]
    return merged


def _norm_align(value):
    v = (value or "").strip().lower()
    if v in ("start", "-webkit-left"):
        return "left"
    if v in ("end", "-webkit-right"):
        return "right"
    return v or "left"


def _vertical_overlap_ratio(a, b):
    top = max(a["top"], b["top"])
    bottom = min(a["bottom"], b["bottom"])
    overlap = bottom - top
    denom = min(a["height"], b["height"])
    if denom <= 0:
        return 0.0
    return overlap / denom


def column_count(section):
    """Column structure class input: how many of the section's direct
    children sit side by side (grid columns when the section is a grid)."""
    children = [c for c in (section.get("children") or [])
                if (c.get("rect") or {}).get("width", 0) > 0]
    if not children:
        return 0
    if section.get("display") == "grid":
        gc = (section.get("gridColumns") or "").strip()
        if gc and gc != "none":
            return max(1, len(gc.split()))
    import itertools

    rects = [c["rect"] for c in children]

    def side_by_side(i, j):
        a, b = rects[i], rects[j]
        disjoint_x = a["right"] <= b["left"] + 1 or b["right"] <= a["left"] + 1
        return disjoint_x and _vertical_overlap_ratio(a, b) > 0.5

    best = 1
    for size in range(min(len(rects), 8), 1, -1):
        found = False
        for combo in itertools.combinations(range(len(rects)), size):
            if all(side_by_side(i, j)
                   for i, j in itertools.combinations(combo, 2)):
                found = True
                break
        if found:
            best = size
            break
    return best


def primary_image(section):
    imgs = section.get("images") or []
    if not imgs:
        return None
    return max(imgs, key=lambda im: im["width"] * im["height"])


def image_placement_class(section, image=None):
    """Where the section's (primary) image sits: none, full-bleed, left,
    center, right; prefixed multi- when the section carries >1 image."""
    imgs = section.get("images") or []
    if not imgs:
        return "none"
    img = image or primary_image(section)
    sec = section["rect"]
    if sec["width"] <= 0:
        return "center"
    prefix = "multi-" if len(imgs) > 1 else ""
    if img["width"] >= 0.95 * sec["width"]:
        return prefix + "full-bleed"
    center_rel = ((img["rect"]["left"] + img["rect"]["right"]) / 2 - sec["left"]) / sec["width"]
    if center_rel < 0.4:
        return prefix + "left"
    if center_rel > 0.6:
        return prefix + "right"
    return prefix + "center"


def alignment_class(section):
    texts = section.get("texts") or []
    if not texts:
        return "none"
    vals = {_norm_align(t.get("textAlign")) for t in texts}
    if len(vals) == 1:
        return next(iter(vals))
    return "mixed"


def is_center_aligned_section(section):
    """Fully center-aligned: every text element centered and no offset
    media (a left/right placed image breaks the centering)."""
    texts = section.get("texts") or []
    if not texts:
        return False
    if alignment_class(section) != "center":
        return False
    placement = image_placement_class(section)
    return not placement.endswith("left") and not placement.endswith("right")


def section_signature(section):
    """Item 15 signature: (column structure, image placement, alignment,
    background token) as one comparable string."""
    return "cols={}|img={}|align={}|bg={}".format(
        column_count(section),
        image_placement_class(section),
        alignment_class(section),
        (section.get("background") or "").replace(" ", ""),
    )


def heading_body_ratio(section):
    head = section.get("headingFontSize")
    body = section.get("bodyFontSize")
    if head and body:
        return head / body
    return None


def cluster_ratio_classes(ratios, tolerance):
    """Group aspect ratios: within `tolerance` (relative) of the group's
    first ratio counts as the same class (the plan's 5% rule)."""
    classes = []
    for ratio in sorted(ratios):
        placed = False
        for group in classes:
            ref = group[0]
            if ref > 0 and abs(ratio - ref) / ref <= tolerance:
                group.append(ratio)
                placed = True
                break
        if not placed:
            classes.append([ratio])
    return classes


def load_declared_exemptions(run_dir, html_path):
    """Amendment 6, Item 15 delta (a): declared exemptions as data.

    Sources: the run's style-selection record
    (<run_dir>/image-inventory-prompts/style-selection.json, Part B1 fields
    declared_style_traits / declared_series / style_id) and the section
    plan (<run_dir>/desktop-wireframe/section-plan.json or
    mobile-tablet/section-plan.json; per-section `declared_traits`).
    Returns {traits: set of normalized trait strings, style_ids: [...],
    series: bool, per_section: {index or section_id: set of traits},
    sources: [paths read]}. Absent records mean no exemptions: the plain
    FAIL behavior is the default and exemptions are never assumed."""
    result = {"traits": set(), "style_ids": [], "series": False,
              "per_section": {}, "sources": []}
    candidates = []
    search_roots = []
    if run_dir:
        search_roots.append(Path(run_dir))
    if html_path is not None:
        search_roots += [html_path.parent, html_path.parent.parent]
    for root in search_roots:
        candidates.append(root / "image-inventory-prompts" / "style-selection.json")
        candidates.append(root / "desktop-wireframe" / "section-plan.json")
        candidates.append(root / "mobile-tablet" / "section-plan.json")
    seen = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        result["sources"].append(str(path))
        if path.name == "style-selection.json":
            records = []
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                if isinstance(data.get("selections"), list):
                    records = data["selections"]
                else:
                    records = [data]
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                for trait in rec.get("declared_style_traits") or []:
                    result["traits"].add(str(trait).strip().lower())
                if rec.get("declared_series"):
                    result["series"] = True
                if rec.get("style_id"):
                    result["style_ids"].append(str(rec["style_id"]))
        else:  # section plan
            sections = data.get("sections") if isinstance(data, dict) else data
            if isinstance(sections, list):
                for pos, entry in enumerate(sections):
                    if not isinstance(entry, dict):
                        continue
                    traits = {str(t).strip().lower()
                              for t in (entry.get("declared_traits") or [])}
                    if not traits:
                        continue
                    result["per_section"][pos] = traits
                    if entry.get("section_id"):
                        result["per_section"][str(entry["section_id"])] = traits
    return result


def _trait_matches(traits, *needles):
    for trait in traits:
        for needle in needles:
            if needle in trait:
                return trait
    return None


def compute_layout_metrics(data, thresholds, reference_width=1440, exemptions=None):
    """The six Item 15 metrics over LAYOUT_JS data. Returns
    {measured, failures, passes, declared}: failures are named LAYOUT
    lines; passes carry measured values; declared lists Amendment 6
    DECLARED exemptions (metric governed by a declared trait or series,
    cited by name, never a failure). Guards: signature and centering are
    share metrics and are only evaluated at 3+ sections (below that the
    share is reported as measured, not failed); the plan's own guards
    apply elsewhere (>=3 images, >=3 siblings, >=2 CTAs)."""
    th = thresholds
    ex = exemptions or {"traits": set(), "style_ids": [], "series": False,
                        "per_section": {}}
    measured = {}
    failures = []
    passes = []
    declared = []
    sections = data.get("sections") or []
    n = len(sections)
    measured["section_count"] = n
    measured["viewport_width"] = reference_width
    style_cite = ", ".join(ex.get("style_ids") or []) or "selection record"

    def section_traits(idx, section):
        traits = set(ex.get("traits") or set())
        per = ex.get("per_section") or {}
        traits |= per.get(idx, set())
        traits |= per.get(str(idx), set())
        if section.get("id"):
            traits |= per.get(str(section["id"]), set())
        return traits

    # 1. section signature diversity
    sigs = [section_signature(s) for s in sections]
    measured["signatures"] = sigs
    if n >= 3:
        from collections import Counter

        top_sig, top_count = Counter(sigs).most_common(1)[0]
        share = top_count / n
        measured["signature_top_share"] = round(share, 4)
        measured["signature_top"] = top_sig
        if share > th["signature_monotony_max_share"]:
            failures.append(
                "LAYOUT: section signature monotony: {} of {} sections share "
                "signature {} ({:.0%} over the {:.0%} max)".format(
                    top_count, n, top_sig, share,
                    th["signature_monotony_max_share"]))
        else:
            passes.append(
                "LAYOUT PASS: section signature diversity: top signature "
                "share {:.0%} ({} of {} sections), max allowed {:.0%}".format(
                    share, top_count, n, th["signature_monotony_max_share"]))
    else:
        measured["signature_top_share"] = None

    # 2. image ratio diversity (declared series exempt, Amendment 6)
    images = [im for im in (data.get("contentImages") or [])
              if im.get("ratio", 0) > 0]
    ratios = [im["ratio"] for im in images]
    classes = cluster_ratio_classes(ratios, th["image_ratio_same_class_tolerance"])
    measured["image_count"] = len(ratios)
    measured["image_ratio_class_count"] = len(classes)
    series_trait = _trait_matches(ex.get("traits") or set(), "uniform")
    if len(ratios) >= th["image_ratio_min_images"] and len(classes) == 1:
        if ex.get("series") or series_trait:
            declared.append(
                "LAYOUT DECLARED: image ratio diversity: all {} content "
                "images share one aspect-ratio class (ratio {:.2f}), exempt "
                "under declared series (style {})".format(
                    len(ratios), ratios[0], style_cite))
            measured["image_ratio_status"] = "declared"
        else:
            failures.append(
                "LAYOUT: image ratio monotony: all {} content images share "
                "one aspect-ratio class (ratio {:.2f}); the brand bans the "
                "same image ratio everywhere".format(len(ratios), ratios[0]))
            measured["image_ratio_status"] = "fail"
    elif ratios:
        passes.append(
            "LAYOUT PASS: image ratio diversity: {} ratio class(es) across "
            "{} content images".format(len(classes), len(ratios)))
        measured["image_ratio_status"] = "pass"
    else:
        measured["image_ratio_status"] = "not-evaluated"

    # 3. centering ratio (declared centered composition exempt per section)
    if n >= 3:
        centered_idx = []
        exempt_centered = []
        for idx, s in enumerate(sections):
            if not is_center_aligned_section(s):
                continue
            trait = _trait_matches(section_traits(idx, s), "center")
            if trait:
                exempt_centered.append((idx, trait))
            else:
                centered_idx.append(idx)
        share = len(centered_idx) / n
        measured["centered_sections"] = len(centered_idx)
        measured["centered_share"] = round(share, 4)
        for idx, trait in exempt_centered:
            declared.append(
                "LAYOUT DECLARED: centering: section {} is fully "
                "center-aligned, exempt under declared style trait "
                "'{}' (style {})".format(idx + 1, trait, style_cite))
        if share > th["centering_max_share"]:
            failures.append(
                "LAYOUT: centering monotony: {} of {} sections are fully "
                "center-aligned ({:.0%} over the {:.0%} max)".format(
                    len(centered_idx), n, share, th["centering_max_share"]))
        else:
            passes.append(
                "LAYOUT PASS: centering ratio: {:.0%} of sections fully "
                "center-aligned ({} of {}), max allowed {:.0%}".format(
                    share, len(centered_idx), n, th["centering_max_share"]))
    else:
        measured["centered_share"] = None

    # 4. repeated card grid
    allowlist = th["card_grid_allowlist"]
    card_failures = 0
    for group in data.get("siblingGroups") or []:
        kids = group.get("children") or []
        by_structure = {}
        for kid in kids:
            by_structure.setdefault(kid.get("structure", ""), []).append(kid)
        for structure, members in by_structure.items():
            members = sorted(members, key=lambda k: (k["width"], k["height"]))
            clusters = []
            for kid in members:
                placed = False
                for cluster in clusters:
                    ref = cluster[0]
                    if ref["width"] > 0 and ref["height"] > 0 and \
                            abs(kid["width"] - ref["width"]) / ref["width"] <= th["card_grid_size_tolerance"] and \
                            abs(kid["height"] - ref["height"]) / ref["height"] <= th["card_grid_size_tolerance"]:
                        cluster.append(kid)
                        placed = True
                        break
                if not placed:
                    clusters.append([kid])
            for cluster in clusters:
                if len(cluster) < th["card_grid_min_repetitions"]:
                    continue
                keys = {group.get("parent", ""), structure,
                        "{} {}".format(group.get("parent", ""), structure)}
                if any(entry in keys for entry in allowlist):
                    passes.append(
                        "LAYOUT PASS: repeated card grid allowlisted: {} "
                        "near-identical siblings under {} (structure {})".format(
                            len(cluster), group.get("parent"), structure))
                    continue
                card_failures += 1
                failures.append(
                    "LAYOUT: repeated card grid: {} near-identical sibling "
                    "elements under {} share structure {} and size {:.0f}x"
                    "{:.0f}px ({} or more is a banned repeated card grid "
                    "unless allowlisted; declare mandated editorial structures in the brand file at layout_thresholds.card_grid_allowlist — parent selector, structure signature, or the pair joined by a space)".format(
                        len(cluster), group.get("parent"), structure,
                        cluster[0]["width"], cluster[0]["height"],
                        th["card_grid_min_repetitions"]))
    measured["card_grid_failures"] = card_failures
    if not card_failures and not any("card grid" in p for p in passes):
        passes.append(
            "LAYOUT PASS: repeated card grid: no sibling group of {} or "
            "more near-identical elements".format(th["card_grid_min_repetitions"]))

    # 5. empty width per section (declared spacious/sparse exempt per section)
    empty_failures = 0
    for idx, s in enumerate(sections):
        rect = s["rect"]
        if rect["width"] <= 0:
            continue
        rects = s.get("contentRects") or []
        if rects:
            span = (max(r["right"] for r in rects)
                    - min(r["left"] for r in rects)) / rect["width"]
        else:
            span = 0.0
        measured.setdefault("section_content_spans", []).append(round(span, 4))
        if span < th["empty_width_min_span"]:
            trait = _trait_matches(section_traits(idx, s),
                                   "spacious", "sparse", "negative space")
            if trait:
                declared.append(
                    "LAYOUT DECLARED: empty width: section {} ({}) content "
                    "spans {:.0%} of section width, exempt under declared "
                    "style trait '{}' (style {})".format(
                        idx + 1, s.get("selector"), span, trait, style_cite))
                continue
            empty_failures += 1
            failures.append(
                "LAYOUT: empty width: section {} ({}) content spans {:.0%} "
                "of section width at {}px (under the {:.0%} minimum; the "
                "brand bans 40% or more empty section width)".format(
                    idx + 1, s.get("selector"), span, reference_width,
                    th["empty_width_min_span"]))
    measured["empty_width_failures"] = empty_failures
    if sections and not empty_failures and not any(
            "empty width" in d for d in declared):
        passes.append(
            "LAYOUT PASS: empty width: every section's content spans at "
            "least {:.0%} of its width at {}px (min measured {:.0%})".format(
                th["empty_width_min_span"], reference_width,
                min(measured.get("section_content_spans") or [1.0])))
    elif sections and not empty_failures:
        passes.append(
            "LAYOUT PASS: empty width: no non-exempt section under the "
            "{:.0%} span minimum at {}px".format(
                th["empty_width_min_span"], reference_width))

    # 6. CTA sameness (brand-declared single-CTA design exempt: this is
    # also the Amendment 6 home for v6's one-CTA-treatment continuity)
    ctas = data.get("ctas") or []
    measured["cta_count"] = len(ctas)
    if len(ctas) >= 2:
        first = ctas[0]
        tol = th["cta_size_tolerance_px"]
        same = all(
            abs(c["width"] - first["width"]) <= tol
            and abs(c["height"] - first["height"]) <= tol
            and c["background"] == first["background"]
            for c in ctas[1:])
        if same and th["single_cta_design"]:
            declared.append(
                "LAYOUT DECLARED: CTA sameness: {} CTAs share identical "
                "dimensions {:.0f}x{:.0f}px and background {}, exempt "
                "under the brand-declared single-CTA design".format(
                    len(ctas), first["width"], first["height"],
                    first["background"]))
            measured["cta_status"] = "declared"
        elif same:
            failures.append(
                "LAYOUT: CTA sameness: {} CTAs share identical dimensions "
                "{:.0f}x{:.0f}px and identical background {} (the brand "
                "bans identical CTA rectangles unless a single-CTA design "
                "is declared)".format(
                    len(ctas), first["width"], first["height"],
                    first["background"]))
            measured["cta_status"] = "fail"
        else:
            passes.append(
                "LAYOUT PASS: CTA variety: {} CTAs differ in dimensions "
                "or background".format(len(ctas)))
            measured["cta_status"] = "pass"
    else:
        measured["cta_status"] = "not-evaluated"

    return {"measured": measured, "failures": failures, "passes": passes,
            "declared": declared}


def compute_v6_baseline(data_by_width, image_map_entries, thresholds):
    """Amendment 6, Item 15 delta (b): Standard v6's own checkable layout
    law as a WARN-only family (v6 labels its geometry a baseline, not
    requirements). Returns warning lines named V6-BASELINE plus measured
    data. Checks: (1) frame-ratio truth: a slot's declared ratio (from the
    image map's desktop_slot_px / desktop_slot_h_px pair, or an explicit
    declared_ratio / aspect_ratio field) must equal the rendered ratio;
    (2) wrap checks at 320/360/390/430: no horizontal overflow and no
    clipped leaf text at those widths; (3) the 56px full-width button
    target at the widest width."""
    warnings_out = []
    measured = {}
    tol = thresholds["image_ratio_same_class_tolerance"]
    base = data_by_width.get(1440) or {}
    # (1) frame-ratio truth
    declared_by_slot = {}
    for entry in image_map_entries or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        ratio = None
        w = entry.get("desktop_slot_px") or entry.get("intended_desktop_slot")
        h = entry.get("desktop_slot_h_px")
        if w and h:
            ratio = float(w) / float(h)
        elif entry.get("declared_ratio"):
            ratio = float(entry["declared_ratio"])
        elif entry.get("aspect_ratio"):
            ratio = float(entry["aspect_ratio"])
        if ratio:
            declared_by_slot[str(entry["id"])] = ratio
    frame_checked = 0
    for img in base.get("contentImages") or []:
        slot = img.get("slot")
        if not slot or slot not in declared_by_slot:
            continue
        frame_checked += 1
        declared_ratio = declared_by_slot[slot]
        actual = img["ratio"]
        if declared_ratio > 0 and abs(actual - declared_ratio) / declared_ratio > tol:
            warnings_out.append(
                "V6-BASELINE: frame ratio: image {} declared ratio {:.2f} "
                "but renders at {:.2f} (frame-ratio truth: a declared frame "
                "must match its actual geometry)".format(
                    slot, declared_ratio, actual))
    measured["frame_ratio_checked"] = frame_checked
    # (2) wrap checks
    wrap = {}
    for width in (320, 360, 390, 430):
        res = data_by_width.get("wrap", {}).get(width)
        if res is None:
            continue
        wrap[width] = res
        if res["scrollWidth"] > res["innerWidth"]:
            warnings_out.append(
                "V6-BASELINE: wrap: horizontal overflow at {}px "
                "(scrollWidth {} over innerWidth {})".format(
                    width, res["scrollWidth"], res["innerWidth"]))
        for item in res.get("clipped") or []:
            warnings_out.append(
                "V6-BASELINE: wrap: {} text clipped at {}px "
                "(scrollWidth {} over clientWidth {})".format(
                    item["selector"], width, item["scrollWidth"],
                    item["clientWidth"]))
    measured["wrap_widths_checked"] = sorted(wrap.keys())
    # (3) 56px full-width button target at the widest width
    sections = base.get("sections") or []
    full_width_checked = 0
    for cta in base.get("ctas") or []:
        is_full = False
        for s in sections:
            if s["rect"]["width"] > 0 and cta["width"] >= 0.9 * s["rect"]["width"]:
                is_full = True
                break
        if is_full:
            full_width_checked += 1
            if cta["height"] < 56:
                warnings_out.append(
                    "V6-BASELINE: button target: full-width CTA {} is "
                    "{:.0f}px tall, under the 56px full-width button "
                    "target".format(cta["selector"], cta["height"]))
    measured["full_width_ctas_checked"] = full_width_checked
    return {"warnings": warnings_out, "measured": measured}


def hex_to_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return None
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def die2(message):
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(2)


def load_brand(path):
    try:
        brand = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        die2(f"could not read brand file {path}: {exc}")
    if not isinstance(brand, dict):
        die2(f"brand file {path} is not a JSON object")
    return brand


def brand_colors(brand):
    palette, logo_only = [], []
    for name, value in (brand.get("palette") or {}).items():
        rgb = hex_to_rgb(str(value))
        if rgb is None:
            die2(f"brand palette entry '{name}' is not a hex color: {value!r}")
        palette.append({"name": name, "hex": str(value), "r": rgb[0], "g": rgb[1], "b": rgb[2]})
    for name, value in (brand.get("logo_only_colors") or {}).items():
        rgb = hex_to_rgb(str(value))
        if rgb is None:
            die2(f"brand logo_only_colors entry '{name}' is not a hex color: {value!r}")
        logo_only.append({"name": name, "hex": str(value), "r": rgb[0], "g": rgb[1], "b": rgb[2]})
    if not palette:
        die2("brand file has no palette")
    return palette, logo_only


def brand_fonts(brand):
    """Return (fonts, derived): derived=True when brand fonts are MUST_SUPPLY
    placeholders under a derive-document font_policy — the page then carries
    agent-derived fonts and the font checks degrade to WARN, never FAIL."""
    fonts = brand.get("fonts") or {}
    policy = brand.get("font_policy") or {}
    derived_policy = (isinstance(policy, dict)
                      and policy.get("when_brand_fonts_missing") == "derive-document")
    values = []
    placeholders = []
    for key, value in fonts.items():
        text = str(value).strip()
        if any(marker in text for marker in UNSUPPLIED):
            placeholders.append(key)
            continue
        if text:
            values.append(text)
    if placeholders:
        if not derived_policy:
            die2(f"brand file fonts.{placeholders[0]} is not supplied yet "
                 f"({str(fonts[placeholders[0]]).strip()}); fail-closed per order 0.5")
        # derived fonts: the bible's fonts_source/font_rationale/font_reviewer
        # gate this elsewhere (validate_visual_direction.py); here the page
        # check degrades to WARN.
        return values, True
    if not values:
        die2("brand file has no fonts")
    return values, False


def load_intake(args, html_path):
    candidates = []
    if args.intake:
        candidates.append(Path(args.intake))
    if args.run_dir:
        candidates.append(Path(args.run_dir) / "intake.json")
    candidates.append(html_path.parent / "intake.json")
    candidates.append(html_path.parent.parent / "intake.json")
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, path
        except Exception:
            continue
    return {}, None


def load_image_map(args, html_path):
    candidates = []
    if args.image_map:
        candidates.append(Path(args.image_map))
    if args.run_dir:
        base = Path(args.run_dir)
        candidates += [base / "image-map-upload" / "image-map.json", base / "image-map.json"]
    candidates += [html_path.parent / "image-map.json", html_path.parent.parent / "image-map.json"]
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = data.get("images") if isinstance(data, dict) else data
        if isinstance(entries, list):
            return entries, path
    return None, None


def load_copy(args, html_path):
    if args.copy:
        path = Path(args.copy)
    elif args.run_dir and (Path(args.run_dir) / "copy" / "public-copy.md").exists():
        path = Path(args.run_dir) / "copy" / "public-copy.md"
    else:
        return None, None
    try:
        return path.read_text(encoding="utf-8"), path
    except Exception as exc:
        die2(f"could not read public copy {path}: {exc}")


def copy_candidates(md_text):
    found = []
    for raw in md_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        for match in re.finditer(r"\[([^\]]+)\]\([^)]*\)", line):
            found.append(match.group(1))
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        text = text.replace("**", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            found.append(text)
    return [c for c in found if len(c) >= 3]


def norm_text(value):
    return " ".join(value.split())


def find_lazy_images(html_text):
    hits = []
    for match in re.finditer(r"<img\b[^>]*>", html_text, re.I):
        tag = match.group(0)
        if re.search(r"loading\s*=\s*[\"']?lazy", tag, re.I):
            src_m = re.search(r"src\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            hits.append(src_m.group(1) if src_m else tag[:80])
    return hits


CSS_COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\brgba?\([^()]*\)"
    r"|\bhsla?\([^()]*\)"
    r"|\b(?:transparent|currentcolor)\b",
    re.I,
)
CSS_NEUTRAL_KEYWORDS = {"transparent", "currentcolor"}
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CSS_VAR_RE = re.compile(r"var\(")


def authored_css_tokens(html_text, html_path):
    """Collect authored color tokens from the page's own CSS.

    Sources: inline <style> blocks and local <link rel="stylesheet"> files.
    Every hex/rgb/hsl token in the authored CSS must be an exact brand palette
    or logo-only hex, or a var() reference. This is the gate the 2026-10-01
    test page slipped through: its stylesheet-authored ivory #F6F1E8 renders
    within a 1-per-channel computed distance of Cream #F5F0E8, so a purely
    computed check passes it. Authored hex cannot approximate: it is the token
    itself.
    Returns a list of (source, token) pairs plus the raw CSS text.
    """
    tokens = []
    css_chunks = []
    for match in re.finditer(r"<style\b[^>]*>(.*?)</style>", html_text, re.I | re.S):
        css_chunks.append(("style:" + html_path.name, match.group(1)))
    for match in re.finditer(
        r"<link\b[^>]*rel=[\"']stylesheet[\"'][^>]*>", html_text, re.I
    ):
        href_m = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", match.group(0), re.I)
        if not href_m:
            continue
        href = href_m.group(1)
        if re.match(r"^[a-z]+://", href, re.I):
            continue  # remote stylesheet: computed layer still covers it
        path = (html_path.parent / href.split("?")[0].split("#")[0]).resolve()
        try:
            css_chunks.append(("css:" + href, path.read_text(encoding="utf-8")))
        except OSError:
            continue
    for source, css in css_chunks:
        css = CSS_COMMENT_RE.sub(" ", css)
        for token_m in CSS_COLOR_RE.finditer(css):
            token = token_m.group(0)
            if token.lower() in CSS_NEUTRAL_KEYWORDS or CSS_VAR_RE.search(token):
                continue
            tokens.append((source, token))
    return tokens


def check_authored_tokens(tokens, palette, logo_only):
    """Errors for authored color tokens that are not exact brand hex values."""
    allowed = {
        ("#" + c["hex"].lstrip("#").upper()) for c in palette + logo_only
    }
    errors = []
    seen = set()
    for source, token in tokens:
        value = token.strip()
        if not value.lower().startswith("#"):
            # rgb()/hsl() functionals: only flag when they are NOT resolving to
            # a brand color; the computed layer handles per-element truth, so
            # functionals are reported only when they cannot be a token.
            errors.append(
                f"authored color uses {value!r} in {source}: "
                "CSS color functions are not brand tokens; use a palette hex or var()"
            )
            continue
        norm = value.upper()
        if len(norm) == 4:  # #ABC -> #AABBCC
            norm = "#" + "".join(ch * 2 for ch in norm[1:])
        if norm in allowed:
            continue
        key = (source, norm)
        if key in seen:
            continue
        seen.add(key)
        nearest = min(
            palette + logo_only,
            key=lambda c: max(
                abs(int(norm[1:3], 16) - c["r"]),
                abs(int(norm[3:5], 16) - c["g"]),
                abs(int(norm[5:7], 16) - c["b"]),
            ),
        )
        errors.append(
            f"authored color {norm} in {source} is not a brand token "
            f"(nearest {nearest['name']} {nearest['hex']}); brand colors are exact hex only"
        )
    return errors


def resolve_image_bytes(page, src, page_url_dir):
    """Fetch the bytes behind an img src for SHA-256 (file, http, data URI)."""
    if src.startswith("data:"):
        header, _, payload = src.partition(",")
        if "base64" in header:
            return base64.b64decode(payload)
        return urllib.parse.unquote(payload).encode("utf-8")
    if src.startswith("http://") or src.startswith("https://"):
        response = page.context.request.get(src, timeout=LOAD_TIMEOUT_MS)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status} for {src}")
        return response.body()
    if src.startswith("file://"):
        path = Path(urllib.parse.unquote(urllib.parse.urlparse(src).path))
    else:
        clean = src.split("#")[0].split("?")[0]
        path = (page_url_dir / clean).resolve()
    return path.read_bytes()


FOUNDER_PHOTO_FORMS = (
    "a bare 64-character hex SHA-256",
    "a 'sha256:' value",
    "the path of an existing file",
)


def founder_photo_entry_form(entry, path_exists=None):
    """Classify one brand founder_photos entry by the forms founder_allowed_hashes
    accepts. Returns "unsupplied", "sha256", "hash", "path", or None when the
    entry is in none of the accepted forms. This function is the single source
    of the acceptance forms: write_intake.py's intake check (update plan
    Item 10) classifies with it too, so intake and this validator cannot
    drift. path_exists, when given, decides whether a path candidate names an
    existing file (intake probes several bases); by default it is
    Path(text).exists() from the caller's working directory, exactly as
    founder_allowed_hashes has always resolved it."""
    text = str(entry).strip()
    if any(marker in text for marker in UNSUPPLIED):
        return "unsupplied"
    if text.lower().startswith("sha256:"):
        return "sha256"
    if re.fullmatch(r"[0-9a-fA-F]{64}", text):
        return "hash"
    exists = Path(text).exists() if path_exists is None else bool(path_exists(text))
    return "path" if exists else None


def founder_allowed_hashes(brand):
    photos = brand.get("founder_photos")
    if photos is None:
        return None  # check not armed
    if isinstance(photos, str):
        photos = [photos]
    hashes = set()
    for entry in photos:
        text = str(entry).strip()
        form = founder_photo_entry_form(entry)
        if form == "unsupplied":
            die2(f"brand founder_photos is not supplied yet ({text}); fail-closed per order 0.5")
        if form == "sha256":
            hashes.add(text.split(":", 1)[1].strip().lower())
        elif form == "hash":
            hashes.add(text.lower())
        elif form == "path":
            hashes.add(hashlib.sha256(Path(text).read_bytes()).hexdigest())
        else:
            die2(f"brand founder_photos entry is neither a sha256 value nor a file: {text}")
    return hashes


def main():
    parser = argparse.ArgumentParser(
        description="Validate a BlackCEO Signature page against the run's brand file (Skill 71 order C2)."
    )
    parser.add_argument("html", type=Path)
    parser.add_argument("--brand", type=Path, required=True)
    parser.add_argument("--mode", choices=["page", "mockup"], default="page")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--image-map", type=Path, default=None)
    parser.add_argument("--copy", type=Path, default=None, help="copy/public-copy.md for copy parity")
    parser.add_argument("--intake", type=Path, default=None)
    parser.add_argument("--widths", default=",".join(str(w) for w in DEFAULT_WIDTHS))
    parser.add_argument("--json", action="store_true", help="also print the JSON report")
    args = parser.parse_args()

    html_path = args.html
    if not html_path.exists():
        die2(f"HTML file not found: {html_path}")
    try:
        html_text = html_path.read_text(encoding="utf-8")
    except Exception as exc:
        die2(f"could not read HTML file {html_path}: {exc}")

    brand = load_brand(args.brand)
    palette, logo_only = brand_colors(brand)
    fonts, fonts_derived = brand_fonts(brand)
    layout_thresholds = load_layout_thresholds(brand)
    declared_exemptions = load_declared_exemptions(args.run_dir, html_path)
    banned = [str(f) for f in (brand.get("banned_fonts") or [])]
    try:
        tolerance = int(brand.get("color_tolerance", 0))
    except (TypeError, ValueError):
        die2(f"brand color_tolerance is not an integer: {brand.get('color_tolerance')!r}")
    is_blackceo = brand.get("is_blackceo") is True or str(brand.get("brand_id", "")) == "blackceo"

    intake, intake_path = load_intake(args, html_path)
    test_run = bool(intake.get("test_run", False))

    widths = []
    for token in str(args.widths).split(","):
        token = token.strip()
        if token:
            try:
                widths.append(int(token))
            except ValueError:
                die2(f"invalid width: {token}")
    if not widths:
        die2("no widths given")

    image_map, image_map_path = load_image_map(args, html_path)
    copy_text, copy_path = load_copy(args, html_path)

    errors = []
    warnings = []
    checks = {
        "colors": {"palette": [c["hex"] for c in palette],
                   "logo_only": [c["hex"] for c in logo_only],
                   "color_tolerance": tolerance},
        "fonts": {"brand": fonts, "banned": banned},
        "widths": widths,
        "mode": args.mode,
        "intake": str(intake_path) if intake_path else None,
        "test_run": test_run,
        "image_map": str(image_map_path) if image_map_path else None,
        "public_copy": str(copy_path) if copy_path else None,
        "layout_thresholds": layout_thresholds,
        "declared_exemption_sources": declared_exemptions["sources"],
    }
    layout_report = None
    v6_baseline_report = None
    layout_pass_lines = []
    layout_declared_lines = []

    page_url = html_path.resolve().as_uri()
    page_url_dir = html_path.resolve().parent
    lazy_hits = find_lazy_images(html_text)
    for src in lazy_hits:
        errors.append(f"image ships with loading=lazy: {src} (Signature pages are eager-loaded)")

    for err in check_authored_tokens(
        authored_css_tokens(html_text, html_path), palette, logo_only
    ):
        errors.append(err)

    inner_text_max = ""
    max_width = max(widths)
    layout_width = 1440 if 1440 in widths else max_width
    layout_data_by_width = {}
    logo_missing_widths = []
    logo_hidden_widths = []
    overflow_widths = []
    width_results = {}

    if sync_playwright is None:
        die2("playwright is required (import playwright).")

    try:
        with sync_playwright() as pw:
            # launch_persistent_context (NOT a bare launch()) — headless, D6-safe
            # (guard-agent-browser-managed section 5).
            udd = tempfile.mkdtemp(prefix="skill71-validate-")
            context = None
            try:
                context = pw.chromium.launch_persistent_context(
                    udd,
                    headless=True,
                    viewport={"width": widths[0], "height": VIEWPORT_H},
                )
                page = context.pages[0] if context.pages else context.new_page()
                for width in widths:
                    page.set_viewport_size({"width": width, "height": VIEWPORT_H})
                    page.goto(page_url, wait_until="load", timeout=LOAD_TIMEOUT_MS)
                    page.evaluate(EAGER_JS)
                    page.evaluate(SCROLL_JS)
                    try:
                        page.evaluate("() => document.fonts.ready.then(() => true)")
                        page.wait_for_function(ALL_IMAGES_LOADED_JS, timeout=LOAD_TIMEOUT_MS)
                    except PWTimeout:
                        pass  # reported below from the images check

                    width_results[width] = {}

                    # 1. colors
                    offenders = page.evaluate(
                        COLORS_JS,
                        {"palette": palette, "logoOnly": logo_only, "tolerance": tolerance},
                    )
                    width_results[width]["color_offenders"] = offenders
                    for off in offenders:
                        errors.append(
                            f"color: {off['selector']} {off['kind']} {off['value']} -> "
                            f"nearest brand color {off['nearest']} (exceeds color_tolerance {tolerance})"
                        )

                    # 2. fonts (derived-font runs degrade to WARN, never FAIL —
                    # banned fonts always FAIL)
                    fonts_res = page.evaluate(
                        FONTS_JS, {"brandFonts": fonts, "banned": banned}
                    )
                    width_results[width]["fonts"] = fonts_res
                    for entry in fonts_res["bad"]:
                        if entry["banned"]:
                            errors.append(
                                f"font: {entry['selector']} uses {entry['font']} (banned font)")
                        elif fonts_derived:
                            warnings.append(
                                f"WARN font (derived): {entry['selector']} uses {entry['font']} "
                                f"(agent-derived font; bible fonts_source/font_rationale/"
                                f"font_reviewer govern this run)")
                        else:
                            errors.append(
                                f"font: {entry['selector']} uses {entry['font']} (not a brand font)")
                    for name in fonts_res["unavailable"]:
                        if fonts_derived:
                            warnings.append(
                                f"WARN font (derived): {name} not loadable in document.fonts "
                                f"(agent-derived font run)")
                        else:
                            errors.append(f"font: brand font not loadable in document.fonts: {name}")

                    # 3. logo
                    if is_blackceo:
                        logo_res = page.evaluate(LOGO_JS, {"viewportH": VIEWPORT_H})
                        width_results[width]["logo"] = logo_res
                        if not logo_res["found"]:
                            logo_missing_widths.append(width)
                        elif not logo_res["visible"]:
                            logo_hidden_widths.append(width)

                    # 5. placeholders
                    placeholder_hits = page.evaluate(
                        PLACEHOLDER_JS,
                        {"patterns": [
                            {"source": pat.pattern,
                             "flags": "gi" if pat.flags & re.IGNORECASE else "g",
                             "name": name}
                            for pat, name in PLACEHOLDER_PATTERNS
                        ]},                    )
                    width_results[width]["placeholders"] = placeholder_hits
                    seen_hits = set()
                    for hit in placeholder_hits:
                        key = (hit["where"], hit["match"], hit["name"])
                        if key in seen_hits:
                            continue
                        seen_hits.add(key)
                        message = f"placeholder ({hit['name']}) in {hit['where']}: {hit['match']}"
                        (warnings if test_run else errors).append(message)

                    # 6/7. images, slots, overflow
                    imgs_res = page.evaluate(IMAGES_JS)
                    width_results[width]["images"] = imgs_res
                    if args.mode == "page":
                        for img in imgs_res["imgs"]:
                            if img["visible"] and not img["complete"]:
                                errors.append(f"image not loaded: {img['src']}")
                        if image_map is None:
                            if width == max_width:
                                warnings.append(
                                    "image-map.json not found; slot-width check skipped"
                                )
                        else:
                            by_id = {}
                            for entry in image_map:
                                if isinstance(entry, dict) and entry.get("id"):
                                    by_id[str(entry["id"])] = entry
                            if width == max_width:
                                for img in imgs_res["imgs"]:
                                    if not img["slot"] or not img["visible"]:
                                        continue
                                    entry = by_id.get(img["slot"])
                                    if entry is None:
                                        warnings.append(
                                            f"image {img['slot']} ({img['src']}) has no image-map entry"
                                        )
                                        continue
                                    slot_px = entry.get("desktop_slot_px") or entry.get("intended_desktop_slot")
                                    if slot_px is None:
                                        continue
                                    min_px = 0.9 * float(slot_px)
                                    if img["width"] < min_px:
                                        errors.append(
                                            f"image {img['slot']} rendered at {img['width']:.0f}px at {max_width}px, "
                                            f"below 90% of its {slot_px}px slot"
                                        )
                        if width == max_width:
                            founder_res = page.evaluate(FOUNDER_JS)
                            width_results[width]["founder"] = founder_res
                            if is_blackceo and founder_res.get("present"):
                                if not founder_res.get("hasImg"):
                                    errors.append("founder slot [data-slot=founder] has no image")
                                elif founder_res.get("empty"):
                                    errors.append("founder slot image is empty/hidden")
                                else:
                                    allowed = founder_allowed_hashes(brand)
                                    if allowed is not None:
                                        try:
                                            data = resolve_image_bytes(
                                                page, founder_res["src"], page_url_dir
                                            )
                                        except Exception as exc:
                                            errors.append(
                                                f"founder image could not be hashed: {exc}"
                                            )
                                        else:
                                            digest = hashlib.sha256(data).hexdigest()
                                            width_results[width]["founder"]["sha256"] = digest
                                            if digest not in allowed:
                                                errors.append(
                                                    f"founder image sha256 {digest} is not one of brand founder_photos "
                                                    "(generated image or wrong photo)"
                                                )
                    else:  # mockup mode: [data-image-slot] blocks at exact slot size
                        if image_map is None and width == max_width:
                            warnings.append("image-map.json not found; slot-size check skipped")
                        elif image_map and width == max_width:
                            by_id = {}
                            for entry in image_map:
                                if isinstance(entry, dict) and entry.get("id"):
                                    by_id[str(entry["id"])] = entry
                            for slot in imgs_res["slots"]:
                                entry = by_id.get(slot["slot"])
                                if entry is None:
                                    warnings.append(
                                        f"mockup slot {slot['slot']} has no image-map entry"
                                    )
                                    continue
                                slot_px = entry.get("desktop_slot_px") or entry.get("intended_desktop_slot")
                                if slot_px is not None and abs(slot["width"] - float(slot_px)) > 2:
                                    errors.append(
                                        f"mockup slot {slot['slot']} is {slot['width']:.0f}px wide, "
                                        f"expected {slot_px}px"
                                    )
                                slot_h = entry.get("desktop_slot_h_px")
                                if slot_h is not None and abs(slot["height"] - float(slot_h)) > 2:
                                    errors.append(
                                        f"mockup slot {slot['slot']} is {slot['height']:.0f}px tall, "
                                        f"expected {slot_h}px"
                                    )

                    overflow = page.evaluate(OVERFLOW_JS)
                    width_results[width]["overflow"] = overflow
                    if overflow["scrollWidth"] > overflow["innerWidth"]:
                        overflow_widths.append(width)

                    # 9. mobile baseline at 390
                    if width == 390:
                        text_issues = page.evaluate(MOBILE_TEXT_JS)
                        button_issues = page.evaluate(MOBILE_BUTTONS_JS)
                        width_results[width]["mobile_text"] = text_issues
                        width_results[width]["mobile_buttons"] = button_issues
                        for issue in text_issues:
                            label = "microcopy" if issue["micro"] else "body text"
                            errors.append(
                                f"mobile {label}: {issue['selector']} is {issue['size']:.0f}px, "
                                f"below the {issue['floorPx']}px floor at 390px"
                            )
                        for issue in button_issues:
                            errors.append(
                                f"mobile button: {issue['selector']} is {issue['height']:.0f}px tall, "
                                f"below the 56px floor at 390px"
                            )

                    # 10. layout metrics (Item 15) at the reference width
                    if width == layout_width:
                        layout_data = page.evaluate(LAYOUT_JS)
                        layout_data_by_width[width] = layout_data
                        layout_report = compute_layout_metrics(
                            layout_data, layout_thresholds,
                            reference_width=width,
                            exemptions=declared_exemptions)
                        width_results[width]["layout"] = layout_report
                        errors.extend(layout_report["failures"])
                        comp_lines = (composition.page_failures(layout_data, composition.composition_cues(brand))
                                      + composition_pixel_failures(page))
                        width_results[width]["composition"] = {"failures": comp_lines}
                        errors.extend(comp_lines)
                        layout_pass_lines = layout_report["passes"]
                        layout_declared_lines = layout_report["declared"]

                    # V6-BASELINE wrap capture at baseline widths that are
                    # part of this pass; the remaining widths run below.
                    if width in (320, 360, 390, 430):
                        layout_data_by_width.setdefault("wrap", {})[width] = (
                            page.evaluate(WRAP_JS))

                    if width == max_width:
                        inner_text_max = page.evaluate(INNERTEXT_JS) or ""

                # V6-BASELINE wrap widths not covered by the main pass
                wrap_done = layout_data_by_width.get("wrap", {})
                for extra_width in (320, 360, 390, 430):
                    if extra_width in wrap_done or extra_width in widths:
                        continue
                    page.set_viewport_size(
                        {"width": extra_width, "height": VIEWPORT_H})
                    page.goto(page_url, wait_until="load",
                              timeout=LOAD_TIMEOUT_MS)
                    page.evaluate(EAGER_JS)
                    page.evaluate(SCROLL_JS)
                    layout_data_by_width.setdefault("wrap", {})[
                        extra_width] = page.evaluate(WRAP_JS)
                if layout_data_by_width.get(1440) is None and \
                        layout_data_by_width.get(layout_width) is not None:
                    layout_data_by_width[1440] = layout_data_by_width[layout_width]
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass
                shutil.rmtree(udd, ignore_errors=True)
    except Exception as exc:
        die2(f"Playwright failure while validating {html_path}: {exc}")

    # Item 15 results into the report; the v6-native baseline family
    # (Amendment 6 delta b) is WARN-only and runs for built pages.
    if layout_report is not None:
        checks["layout"] = layout_report
    if args.mode == "page" and layout_report is not None:
        v6_baseline_report = compute_v6_baseline(
            layout_data_by_width, image_map, layout_thresholds)
        warnings.extend(v6_baseline_report["warnings"])
        checks["v6_baseline"] = v6_baseline_report

    # 3. logo verdicts
    if is_blackceo:
        if logo_missing_widths:
            errors.append(
                "logo: no [data-brand=\"logo\"] element on the page "
                f"(checked at widths {', '.join(map(str, logo_missing_widths))})"
            )
        if logo_hidden_widths:
            errors.append(
                "logo: [data-brand=\"logo\"] element not visible in the first viewport at widths "
                f"{', '.join(map(str, logo_hidden_widths))}"
            )

    # 7. overflow verdicts
    if overflow_widths:
        errors.append(
            f"overflow: scrollWidth exceeds innerWidth at widths {', '.join(map(str, overflow_widths))}"
        )

    # 8. copy parity
    if copy_text is not None:
        page_text = norm_text(inner_text_max)
        missing = [
            cand for cand in copy_candidates(copy_text) if norm_text(cand) not in page_text
        ]
        checks["copy_parity_checked"] = len(copy_candidates(copy_text))
        for cand in missing:
            errors.append(f"copy parity: public copy line missing from page: {cand}")

    # dedupe repeated findings across widths, preserving order
    seen_errors = set()
    deduped = []
    for item in errors:
        if item not in seen_errors:
            seen_errors.add(item)
            deduped.append(item)
    errors = deduped

    report = {
        "tool": "validate_page.py",
        "skill": "71-blackceo-signature-page",
        "mode": args.mode,
        "html": str(html_path),
        "brand": str(args.brand),
        "run_dir": str(args.run_dir) if args.run_dir else None,
        "widths": widths,
        "test_run": test_run,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "width_results": width_results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
    }

    # write report
    if args.run_dir:
        sub = "responsive-html" if args.mode == "page" else "visual-mockup"
        out_dir = Path(args.run_dir) / sub
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "validate-page.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            report["report_path"] = str(out_dir / "validate-page.json")
        except OSError as exc:
            warnings.append(f"could not write validate-page.json: {exc}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if not errors else f"FAIL ({len(errors)} reasons)"
        print(f"{status}: {html_path} [{args.mode}]")
        for item in layout_pass_lines:
            print(item)
        for item in layout_declared_lines:
            print(item)
        for item in warnings:
            print(f"WARNING: {item}")
        for item in errors:
            print(f"FAIL: {item}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
