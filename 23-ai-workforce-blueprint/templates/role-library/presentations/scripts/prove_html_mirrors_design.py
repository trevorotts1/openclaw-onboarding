#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_html_mirrors_design.py — fail-closed prover for design→HTML fidelity
(presentations upsell pipeline, GAUNTLET-LOOP DESIGN-OPUS §9.4).

WAVE 2 = the DETERMINISTIC half. The bounded vision pass is stubbed (returns
"vision-pass PENDING") — the deterministic text/structure check is the deliverable.

The HTML fragment must MIRROR the design prompt that produced it. Deterministically we
can assert, from the design prompt file + the produced HTML:

  * brand colors declared as hex in the design prompt appear in the HTML
    (as CSS `:root`/inline style/class tokens)              -> AF-PRES-MIRROR-COLOR-MISSING
  * the logo reference in the design (image-to-image intent,
    logo file/URL, "logo" token) is referenced in the HTML
    as an <img> / background / media URL (image-to-image)   -> AF-PRES-MIRROR-LOGO-MISSING
  * the page structure (headings/CTA/order-form) matches:
    - every section the design names (headline/CTA/order
      form/gate/offer-summary/etc.) appears in the HTML     -> AF-PRES-MIRROR-SECTION-MISSING
    - copy tokens (headline/subhead/CTA phrases) the design
      embeds as VERBATIM copy appear in the HTML            -> AF-PRES-MIRROR-TOKEN-MISSING
  * the section ORDER declared in the design's structure
    note matches the HTML section order                     -> AF-PRES-MIRROR-ORDER

Design-prompt conventions this prover reads:
  - `#xxxxxx` hex tokens (3- or 6-digit) -> the brand palette the design committed to.
  - `LOGO`/`logo`/`image-to-image`/`reference image` tokens -> logo must be I2I.
  - `HEADLINE: <copy>` / `CTA: <copy>` / `COPY:` / quoted
    strings -> copy tokens that must appear verbatim.
  - a `STRUCTURE:` / `SECTIONS:` list -> the section names in order.

The vision pass is intentionally a stub that returns a non-blocking PENDING note; it does
not gate the deterministic result. Full vision QC is wired in Wave 5 (Playwright headless).

stdlib only. Exit 0 = pass, 2 = violation (autofail), 3 = usage/IO (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_COLOR = "AF-PRES-MIRROR-COLOR-MISSING"
AF_LOGO = "AF-PRES-MIRROR-LOGO-MISSING"
AF_SECTION = "AF-PRES-MIRROR-SECTION-MISSING"
AF_TOKEN = "AF-PRES-MIRROR-TOKEN-MISSING"
AF_ORDER = "AF-PRES-MIRROR-ORDER"
AF_DESIGN = "AF-PRES-MIRROR-DESIGN-LOAD"
AF_EMPTY = "AF-PRES-MIRROR-EMPTY"

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_TOKEN_LINE_RE = re.compile(
    r"^\s*(?:headline|subhead|cta|copy|headline_copy|subhead_copy|cta_copy|body_copy)"
    r"\s*[:=]\s*(.+?)\s*$", re.I | re.M)
_SECTION_LIST_RE = re.compile(
    r"^\s*(?:structure|sections|section_order)\s*[:=]\s*(.+?)\s*$", re.I | re.M)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _phrase_in(norm_text: str, phrase: str) -> bool:
    p = _norm(phrase)
    if not p or not norm_text:
        return False
    # A copy token is VERBATIM: allow the text to contain the exact phrase. A very long
    # phrase (> 30 words) is broken into first-12 + last-12 word anchors to avoid flagging
    # whitespace-only reflow as a mismatch.
    words = p.split()
    if len(words) <= 30:
        return re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", norm_text) is not None
    head = re.escape(" ".join(words[:12]))
    tail = re.escape(" ".join(words[-12:]))
    return bool(re.search(r"(?<![a-z0-9])" + head, norm_text)) and \
        bool(re.search(r"(?<![a-z0-9])" + tail, norm_text))


def _strip_tags(blob: str) -> str:
    return re.sub(r"<[^>]+>", " ", blob)


def _body(html: str) -> str:
    low = html.lower()
    m = re.search(r"<body[^>]*>(.*)</body>", low, re.S)
    if m:
        return html[m.start(1):m.end(1)]
    m = re.search(r"</head[^>]*>", low, re.S)
    if m:
        return html[m.end():]
    return html


# ---------------------------------------------------------------------------
# Design-prompt parsing (deterministic).
# ---------------------------------------------------------------------------
def _extract_colors(prompt: str) -> List[str]:
    """Brand colors as hex tokens. Skips obviously generic '#fff'/'#000' unless they are
    the only colors the design names (still checked)."""
    return list(_HEX_RE.findall(prompt))


def _extract_copy_tokens(prompt: str) -> List[str]:
    """Copy tokens from `HEADLINE:` / `CTA:` / `COPY:` / quoted strings."""
    tokens: List[str] = []
    for m in _TOKEN_LINE_RE.finditer(prompt):
        val = m.group(1).strip().strip('"').strip("'")
        if val and len(val.split()) >= 3:
            tokens.append(val)
    # quoted verbatim copy: "..." (designs embed the exact page copy)
    for q in re.findall(r'"([^"\n]{8,})"', prompt):
        tokens.append(q)
    return tokens


def _extract_sections(prompt: str) -> List[str]:
    """Section names from `STRUCTURE:` / `SECTIONS:` lines, split on commas/pipes/bullets."""
    names: List[str] = []
    for m in _SECTION_LIST_RE.finditer(prompt):
        raw = m.group(1)
        for part in re.split(r"[,\|]", raw):
            part = part.strip()
            part = re.sub(r"^\s*[-*]\s*", "", part)
            if part and not re.match(r"^#?[0-9a-fA-F]{3,6}$", part):
                names.append(part)
    return names


def _logo_intent(prompt: str) -> Optional[str]:
    """Return a truthy marker if the design declares logo/brand usage, or None if it does
    NOT (F1: no logo on file is a legitimate pass). An explicit no-logo declaration
    (logo_used:false / no logo on file / logo: none) OVERRIDES any later mention."""
    low = prompt.lower()
    # Explicit no-logo declaration (design F1 / QC F13).
    if re.search(r"logo_used\s*[:=]\s*(?:false|no|0)|no logo (?:on file|available)|"
                 r"logo\s*[:=]\s*(?:none|n/?a)|without (?:a|the) logo", low):
        return None
    if re.search(r"logo|brand.?mark|image-to-image|\bi2i\b|reference image", low):
        return "logo (design declares logo/brand usage)"
    return None


# ---------------------------------------------------------------------------
# HTML assertions.
# ---------------------------------------------------------------------------
def _logo_in_html(html: str) -> bool:
    raw = html.lower()
    patterns = [
        r'<img\b[^>]*src="[^"]+"',
        r'<img\b[^>]*src=\'[^\']+\'',
        r'background[^:]*:\s*url\(',
        r'logo',
        r'brand-?mark',
        r'data-logo=',
    ]
    return any(re.search(p, raw) for p in patterns)


def _color_in_html(html: str, hex_token: str) -> bool:
    raw = html.lower()
    hx = hex_token.lower()
    # css var / inline style / class token / meta theme-color / data-palette
    patterns = [
        r'--[a-z0-9-]*:\s*' + re.escape(hx) + r'\s*;',
        r'color\s*:\s*' + re.escape(hx),
        r'background(?:-color)?\s*:\s*' + re.escape(hx),
        r'#[a-z0-9-]+\s*[:{]\s*' + re.escape(hx),
        r'"' + re.escape(hx) + r'"',
        r'=' + re.escape(hx),
    ]
    return any(re.search(p, raw) for p in patterns)


def _attr_section_present(html: str, name: str) -> bool:
    raw = html.lower()
    n = _norm(name)
    if not n:
        return False
    return bool(re.search(r'class="[^"]*\b' + re.escape(n) + r'\b[^"]*"', raw)) or \
        bool(re.search(r'id="[^"]*\b' + re.escape(n) + r'\b[^"]*"', raw)) or \
        bool(re.search(r'data-section="[^"]*\b' + re.escape(n) + r'\b[^"]*"', raw)) or \
        bool(re.search(r'<[a-z0-9]+[^>]*(?:class|id|data-section)="[^"]*' + re.escape(n),
                       raw))


def _verify_design_prompt(prompt: str, html: str) -> Tuple[List[Tuple[str, str]], str]:
    """Deterministic design→HTML fidelity. Returns (failures, vision_note)."""
    fails: List[Tuple[str, str]] = []
    body_html = _body(html)
    body_norm = _norm(_strip_tags(body_html))

    if not body_norm:
        return ([(AF_EMPTY, "HTML has no body content (fail-closed)")], "vision-pass PENDING")

    # 1) brand colors.
    colors = _extract_colors(prompt)
    if not colors:
        # design names no color -> not a color violation; nothing to mirror
        pass
    else:
        missing = [c for c in colors if not _color_in_html(html, c)]
        if missing:
            fails.append((AF_COLOR,
                          f"brand color(s) {missing} from the design prompt do not appear "
                          f"in the HTML (design committed to them; HTML must carry them)"))

    # 2) logo.
    logo_ref = _logo_intent(prompt)
    if logo_ref is not None and not _logo_in_html(html):
        fails.append((AF_LOGO,
                      f"design declares logo/brand usage ({logo_ref!r}) but the HTML has "
                      f"no <img> / background / logo reference (image-to-image violated)"))

    # 3) copy tokens (verbatim headline/subhead/CTA).
    tokens = _extract_copy_tokens(prompt)
    missing_tokens = [t for t in tokens if not _phrase_in(body_norm, t)]
    if missing_tokens:
        fails.append((AF_TOKEN,
                      f"{len(missing_tokens)} copy token(s) from the design are absent from "
                      f"the HTML verbatim: {[t[:40] for t in missing_tokens]}"))

    # 4) structure: design-named sections present + order.
    sections = _extract_sections(prompt)
    if sections:
        present: List[Tuple[str, int]] = []
        for name in sections:
            pos = _body_phrase_pos(body_html, body_norm, name)
            if pos is None:
                fails.append((AF_SECTION,
                              f"design-named section {name!r} missing from the HTML"))
            else:
                present.append((name, pos))
        # order: positions must be ascending (as declared)
        for i in range(1, len(present)):
            if present[i][1] < present[i - 1][1]:
                fails.append((AF_ORDER,
                              f"sections out of design-declared order: "
                              f"{present[i - 1][0]!r} before {present[i][0]!r}"))
                break

    vision_note = "vision-pass PENDING"
    return (fails, vision_note)


def _body_phrase_pos(body_html: str, body_norm: str, name: str) -> Optional[int]:
    """Position of a section/copy marker in the body. First checks the RAW body HTML for a
    class/id/data-section attribute naming the section (class="hero" survives tag-strip
    removal), then the verbatim phrase, then a camelCase/PascalCase word split."""
    n = _norm(name)
    if not n:
        return None
    raw = body_html.lower()
    attr_patterns = [
        rf'class="[^"]*\b{re.escape(n)}\b[^"]*"',
        rf'id="[^"]*\b{re.escape(n)}\b[^"]*"',
        rf'data-section="[^"]*\b{re.escape(n)}\b[^"]*"',
        rf'<{re.escape(n)}(?=[\s>])',
    ]
    found: List[int] = []
    for pat in attr_patterns:
        m = re.search(pat, raw)
        if m:
            found.append(m.start())
    if found:
        return min(found)

    m = re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", body_norm)
    if m:
        return m.start()
    # camelCase/PascalCase split: 'offer-summary' -> ['offer','summary']; require both
    parts = [p for p in re.split(r"[-_ ]+", n) if p]
    if len(parts) >= 2:
        hits = [re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", body_norm)
                for p in parts]
        if all(h for h in hits):
            return min(h.start() for h in hits if h)
    return None


def _emit(source: str, failures: List[Tuple[str, str]], vision_note: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "presentations-html-mirrors-design", "source": source,
                          "pass": not failures,
                          "vision": vision_note,
                          "failures": [{"code": c, "message": m} for c, m in failures]},
                         indent=2))
        return
    print("== Presentations :: HTML mirrors design (deterministic) ==")
    print(f"source: {source}")
    print(f"vision: {vision_note}")
    if not failures:
        print("RESULT: PASS — brand colors, logo reference, copy tokens, and design-named "
              "sections all mirror the design prompt.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


def prove(design_path: str, html_path: str, as_json: bool = False) -> int:
    dp = Path(design_path)
    hp = Path(html_path)
    if not dp.is_file():
        _emit(str(dp), [("USAGE", f"design prompt file not found: {dp}")], "vision-pass PENDING",
              as_json)
        return EXIT_USAGE
    if not hp.is_file():
        _emit(str(hp), [("USAGE", f"HTML file not found: {hp}")], "vision-pass PENDING", as_json)
        return EXIT_USAGE
    try:
        prompt = dp.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _emit(str(dp), [("USAGE", f"cannot read design prompt: {exc}")], "vision-pass PENDING",
              as_json)
        return EXIT_USAGE
    try:
        html = hp.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _emit(str(hp), [("USAGE", f"cannot read HTML: {exc}")], "vision-pass PENDING", as_json)
        return EXIT_USAGE
    fails, vision_note = _verify_design_prompt(prompt, html)
    _emit(str(hp), fails, vision_note, as_json)
    return EXIT_PASS if not fails else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test — must DISCRIMINATE.
# ---------------------------------------------------------------------------
def _valid_design_prompt() -> str:
    return """SALES PAGE DESIGN PROMPT

Brand palette: primary #0A2540, secondary #F2B134. Use these exact hex values across the
page so the rendered design carries the palette.

Logo: use image-to-image generation with the attached logo as a reference image via
extra_body.image. Style-reference-only directive: use the attached images only as style
reference for color grading, lighting, and composition — do not copy their subjects,
faces, or text.

HEADLINE: Stop Guessing. Start Closing.
SUBHEAD: The founder's calm path from overwhelm to a system that sells while you sleep.
CTA: Get Instant Access Now

STRUCTURE: hero, problem-solution, benefits, final-cta, footer
"""


def _valid_mirror_html() -> str:
    return """<!doctype html><html><head>
<title>Sales</title>
<style>:root{--primary:#0a2540;--secondary:#f2b134;}</style>
</head><body>
<header class="site-header"><img src="https://cdn.example.com/logo.png" alt="logo" /></header>
<section class="hero"><h1>Stop Guessing. Start Closing.</h1>
<p>The founder's calm path from overwhelm to a system that sells while you sleep.</p></section>
<section class="problem-solution"><h2>The Problem & Solution</h2>
<p>This section names the exact frustration and the calm deliberate path forward.</p></section>
<section class="benefits"><h2>Core Benefits</h2>
<p>Three clear benefits that rebuild confidence and show one first move.</p></section>
<section class="final-cta"><h2>Get Instant Access Now</h2>
<button>Get Instant Access Now</button></section>
<footer class="site-footer">Privacy · Terms · Copyright 2026</footer>
</body></html>"""


def _strip_block(html: str, marker: str) -> str:
    """Remove a <section ...>...</section> block whose class contains marker."""
    m = re.search(r"<section[^>]*\b" + re.escape(marker) + r"\b[^>]*>.*?</section>",
                  html, re.S)
    if m:
        return html[:m.start()] + html[m.end():]
    return html


def self_test() -> int:
    ok = True

    def check_pass(name: str, fails: List[Tuple[str, str]]) -> None:
        nonlocal ok
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:20s} -> exit "
              f"{EXIT_PASS if good else EXIT_AUTOFAIL}" + ("" if good else f" ({fails})"))

    def check_fail(name: str, fails: List[Tuple[str, str]], expect: str) -> None:
        nonlocal ok
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} "
              f"(want {expect})")

    prompt = _valid_design_prompt()
    html = _valid_mirror_html()

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("design-mirrors-html", _verify_design_prompt(prompt, html)[0])
    # design without a logo reference + HTML without logo must still pass (F1 no-logo path)
    no_logo_prompt = re.sub(r"Logo:.*?no image-to-image call[^.]*\.", "", prompt, flags=re.S)
    if "logo" in no_logo_prompt.lower():
        no_logo_prompt = no_logo_prompt.replace("Logo: use image-to-image generation",
                                                "Brand mark: no logo on file")
    no_logo_html = html.replace('<img src="https://cdn.example.com/logo.png" alt="logo" />', "")
    check_pass("no-logo-pass", _verify_design_prompt(no_logo_prompt, no_logo_html)[0])

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    # missing brand color
    bad_color_html = html.replace("#f2b134", "#ffffff")
    check_fail("color-missing", _verify_design_prompt(prompt, bad_color_html)[0], AF_COLOR)
    # logo removed but design demands it
    check_fail("logo-missing", _verify_design_prompt(prompt, no_logo_html)[0], AF_LOGO)
    # copy token dropped
    bad_token_html = html.replace("Stop Guessing. Start Closing.", "Start Selling Now.")
    check_fail("token-missing", _verify_design_prompt(prompt, bad_token_html)[0], AF_TOKEN)
    # design-named section dropped
    check_fail("section-missing", _verify_design_prompt(prompt, _strip_block(html, "benefits"))[0],
               AF_SECTION)
    # section order swapped (footer before hero)
    reordered = html.replace("</section>\n<footer class=\"site-footer\">",
                             "<footer class=\"site-footer\">").replace(
        "<footer class=\"site-footer\">", "</section>\n<footer class=\"site-footer\">", 1)
    # Simpler: move the footer block above the hero.
    import re as _re
    mm = _re.search(r"<footer.*?</footer>", html, _re.S)
    footer = mm.group(0) if mm else ""
    bodyless = html.replace(footer, "")
    # put footer right after <body>
    order_viol = bodyless.replace("<body>", "<body>" + footer)
    check_fail("section-order", _verify_design_prompt(prompt, order_viol)[0], AF_ORDER)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for design→HTML fidelity.")
    ap.add_argument("--design", help="path to the design prompt file (prompts/<page>.design.txt)")
    ap.add_argument("--html", help="path to the produced HTML fragment")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.design or not args.html:
        print("USAGE ERROR: pass --design <design.txt> --html <fragment.html> "
              "(or --self-test).")
        return EXIT_USAGE
    return prove(args.design, args.html, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
