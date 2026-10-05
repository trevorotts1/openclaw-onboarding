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

Writes <run_dir>/responsive-html/validate-page.json (page mode) or
<run_dir>/visual-mockup/validate-page.json (mockup mode).

Exit codes: 0 pass, 1 fail (each reason on its own line), 2 unreadable input.
Python 3 stdlib + Pillow + Playwright only.
"""
import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    print("FAIL: playwright is required (import playwright).", file=sys.stderr)
    sys.exit(2)

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
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    let s = el.tagName.toLowerCase();
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\\s+/)[0];
    if (r.height < 56) issues.push({selector: s, height: r.height});
  }
  return issues;
}"""


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
    fonts = brand.get("fonts") or {}
    values = []
    for key, value in fonts.items():
        text = str(value).strip()
        if any(marker in text for marker in UNSUPPLIED):
            die2(f"brand file fonts.{key} is not supplied yet ({text}); fail-closed per order 0.5")
        if text:
            values.append(text)
    if not values:
        die2("brand file has no fonts")
    return values


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
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", " ", line)
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


def founder_allowed_hashes(brand):
    photos = brand.get("founder_photos")
    if photos is None:
        return None  # check not armed
    if isinstance(photos, str):
        photos = [photos]
    hashes = set()
    for entry in photos:
        text = str(entry).strip()
        if any(marker in text for marker in UNSUPPLIED):
            die2(f"brand founder_photos is not supplied yet ({text}); fail-closed per order 0.5")
        if text.lower().startswith("sha256:"):
            hashes.add(text.split(":", 1)[1].strip().lower())
        elif re.fullmatch(r"[0-9a-fA-F]{64}", text):
            hashes.add(text.lower())
        else:
            path = Path(text)
            if path.exists():
                hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
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
    fonts = brand_fonts(brand)
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
    }

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
    logo_missing_widths = []
    logo_hidden_widths = []
    overflow_widths = []
    width_results = {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": widths[0], "height": VIEWPORT_H})
            try:
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

                    # 2. fonts
                    fonts_res = page.evaluate(
                        FONTS_JS, {"brandFonts": fonts, "banned": banned}
                    )
                    width_results[width]["fonts"] = fonts_res
                    for entry in fonts_res["bad"]:
                        reason = "banned font" if entry["banned"] else "not a brand font"
                        errors.append(f"font: {entry['selector']} uses {entry['font']} ({reason})")
                    for name in fonts_res["unavailable"]:
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

                    if width == max_width:
                        inner_text_max = page.evaluate(INNERTEXT_JS) or ""
            finally:
                browser.close()
    except Exception as exc:
        die2(f"Playwright failure while validating {html_path}: {exc}")

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
        for item in warnings:
            print(f"WARNING: {item}")
        for item in errors:
            print(f"FAIL: {item}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
