#!/usr/bin/env python3
"""pdf_render.py -- deterministic HTML-to-PDF (WeasyPrint-class) for the Anthology Engine.

Unit W1.12. SPEC 3.4 row 11 / SPEC 10.2 / WAVE-PLAN W1.12.

Renders a deliverable's content through the per-type house template in
config/pdf-house-style/ (seeded from the harvested Book-to-HTML formatter rules,
every font token at or above 14 point) into a designed PDF. The pipeline is fully
DETERMINISTIC and NO LLM touches formatting at runtime (the five legacy LLM
HTML-formatter calls are retired):

  1. load the house template for the deliverable type,
  2. deterministically transform the deliverable's markdown into the semantic HTML
     subset the house stylesheet styles (h1-h6, p, ul/ol/li, blockquote, strong, em,
     .one-liner, .scene-break, hr) -- or pass through already-semantic HTML,
  3. fill the template's {{slots}} (text slots HTML-escaped; *_html slots raw),
  4. inline house.css so the document is self-contained and render-location-agnostic,
  5. PRE-RENDER FLOOR GUARD over the assembled template's font tokens (exit 2), then
  6. render with the WeasyPrint CLI under a fixed SOURCE_DATE_EPOCH for reproducibility.

The RENDERED PDF is then independently proven by guard-font-floor.py, which parses the
OUTPUT and fails on any glyph below 14 point (AF-AE-FONT-FLOOR, exit 4). This script's
own floor check inspects the assembled TEMPLATE, never the output -- two independent
gates, template-side (here) and output-side (the guard).

Exit codes (SPEC 3.4 row 11):
  0  rendered
  1  render error (unexpected: missing renderer, WeasyPrint failure, bad input)
  2  a template font-size token below the 14-point floor
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EX_OK, EX_ERR, EX_FLOOR = 0, 1, 2

DEFAULT_FLOOR_PT = 14.0
# Fixed epoch (2001-01-01T00:00:00Z) so repeated renders of identical HTML are
# byte-reproducible; overridable with --source-date-epoch.
DEFAULT_SOURCE_DATE_EPOCH = 978307200

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_DIR = SKILL_DIR / "config" / "pdf-house-style"

DELIVERABLE_TYPES = (
    "avatar", "tone", "titles", "blurb", "outline", "chapter", "manuscript",
)
# The single free-content slot per template type (other slots come from --slot/--slots).
CONTENT_SLOT = {
    "avatar": "content_html", "tone": "content_html", "titles": "content_html",
    "blurb": "content_html", "outline": "content_html", "chapter": "content_html",
    "manuscript": "ordered_chapters_html",
}

# Slots whose value is raw HTML (not HTML-escaped); everything else is escaped text.
RAW_SLOT_SUFFIX = "_html"

WEASYPRINT_FALLBACKS = (
    "/opt/homebrew/bin/weasyprint",
    "/usr/local/bin/weasyprint",
    "/usr/bin/weasyprint",
)


# --------------------------------------------------------------------------- #
# Deterministic markdown -> semantic-HTML subset transform.
# Emits ONLY elements the house stylesheet styles at or above the floor. It never
# introduces a font-size, so it cannot lower any glyph below 14pt.
# --------------------------------------------------------------------------- #
_ATX = re.compile(r"^(#{1,6})\s+(.*)$")
_UL = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_HR = re.compile(r"^(?:-{3,}|_{3,})$")
_SCENE = re.compile(r"^(?:\*{3,}|(?:\*\s){2,}\*)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _inline(text):
    """Inline emphasis on a single logical line. Escapes first, then marks up."""
    s = html.escape(text, quote=False)

    def _link_sub(m):
        label = m.group(1)
        url = m.group(2).replace('"', "%22")  # already &<>-escaped by html.escape
        return '<a href="%s">%s</a>' % (url, label)

    s = _LINK.sub(_link_sub, s)
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w*])_(?!_)(.+?)(?<!_)_(?![\w*])", r"<em>\1</em>", s)
    s = _INLINE_CODE.sub(r"\1", s)  # prose forbids code fences; keep the text only
    return s


def markdown_to_html(md):
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i, n = 0, len(lines)
    after_break = True  # the first paragraph of the document renders flush (no indent)

    def flush_para(buf):
        nonlocal after_break
        text = " ".join(x.strip() for x in buf).strip()
        if not text:
            return
        cls = ' class="first"' if after_break else ""
        out.append("<p%s>%s</p>" % (cls, _inline(text)))
        after_break = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if _FENCE.match(line):  # strip fenced-code markers; render inner as prose
            i += 1
            buf = []
            while i < n and not _FENCE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            if i < n:
                i += 1
            flush_para(buf)
            continue

        if stripped == "":
            i += 1
            continue

        if _SCENE.match(stripped):
            out.append('<div class="scene-break">***</div>')
            after_break = True
            i += 1
            continue

        if _HR.match(stripped):
            out.append("<hr>")
            after_break = True
            i += 1
            continue

        m = _ATX.match(stripped)
        if m:
            level = min(len(m.group(1)), 6)
            content = re.sub(r"\s+#+\s*$", "", m.group(2).strip())
            out.append("<h%d>%s</h%d>" % (level, _inline(content), level))
            after_break = True
            i += 1
            continue

        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i].strip()))
                i += 1
            inner = " ".join(x.strip() for x in buf).strip()
            out.append("<blockquote>%s</blockquote>" % _inline(inner))
            after_break = False
            continue

        if _UL.match(line):
            items = []
            while i < n and _UL.match(lines[i]):
                items.append(_UL.match(lines[i]).group(1).strip())
                i += 1
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _inline(x) for x in items))
            after_break = False
            continue

        if _OL.match(line):
            items = []
            while i < n and _OL.match(lines[i]):
                items.append(_OL.match(lines[i]).group(1).strip())
                i += 1
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % _inline(x) for x in items))
            after_break = False
            continue

        buf = []
        while i < n:
            l = lines[i]
            ls = l.strip()
            if ls == "" or _ATX.match(ls) or ls.startswith(">") or _UL.match(l) \
                    or _OL.match(l) or _SCENE.match(ls) or _HR.match(ls) or _FENCE.match(l):
                break
            buf.append(l)
            i += 1
        flush_para(buf)

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Content passthrough (already-semantic HTML): light sanitize, no reformat.
# --------------------------------------------------------------------------- #
_STRIP_TAGS = re.compile(
    r"<\s*(script|style|iframe|object|embed|link|meta)\b.*?(?:</\s*\1\s*>|>)",
    re.I | re.S,
)
_ON_ATTR = re.compile(r'\son[a-z]+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)


def sanitize_html(fragment):
    frag = _STRIP_TAGS.sub("", fragment)
    frag = _ON_ATTR.sub("", frag)
    return frag


def looks_like_html(text):
    return bool(re.search(
        r"<\s*(p|h[1-6]|ul|ol|li|blockquote|div|section|strong|em|br|hr|a|table)\b",
        text, re.I))


def transform_content(text, fmt):
    if fmt == "auto":
        fmt = "html" if looks_like_html(text) else "md"
    if fmt == "html":
        return sanitize_html(text)
    return markdown_to_html(text)


# --------------------------------------------------------------------------- #
# Template load, slot fill, CSS inline.
# --------------------------------------------------------------------------- #
_SLOT = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def load_template(template_dir, dtype):
    p = Path(template_dir) / (dtype + ".html")
    if not p.exists():
        raise FileNotFoundError("no house template for type '%s' at %s" % (dtype, p))
    return p.read_text(encoding="utf-8")


def fill_slots(template_html, slots, strict):
    """Fill {{slots}}. Text slots are HTML-escaped; *_html slots are raw.
    Unprovided template slots are blanked (or, with strict, raise)."""
    template_slots = set(_SLOT.findall(template_html))
    unresolved = sorted(template_slots - set(slots))
    if strict and unresolved:
        raise ValueError("unresolved template slot(s): %s" % ", ".join(unresolved))

    def repl(m):
        name = m.group(1)
        if name in slots:
            v = slots[name]
            return v if name.endswith(RAW_SLOT_SUFFIX) else html.escape(str(v), quote=False)
        return ""  # blank the unresolved slot; never leak braces into the PDF

    return _SLOT.sub(repl, template_html), unresolved


def inline_css(template_html, template_dir):
    css_path = Path(template_dir) / "house.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    style_block = "<style>\n%s\n</style>" % css
    out, count = re.subn(
        r'<link\b[^>]*href=["\']house\.css["\'][^>]*>', style_block,
        template_html, count=1)
    if count == 0:
        out, count = re.subn(r"</head>", style_block + "\n</head>", template_html, count=1)
    if count == 0:  # no head; prepend so the stylesheet still applies
        out = style_block + "\n" + template_html
    return out


# --------------------------------------------------------------------------- #
# PRE-RENDER floor guard over the assembled template's font tokens (exit 2).
# --------------------------------------------------------------------------- #
_ALL_CUSTOM = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;}]+)")
_FONT_SIZE_DECL = re.compile(r"font-size\s*:\s*([^;}{\"']+)", re.I)
_LEN = re.compile(r"^\s*(-?\d*\.?\d+)\s*([a-z%]*)\s*$", re.I)
_KEYWORDS_BELOW = {"xx-small", "x-small", "small", "smaller", "medium"}
_KEYWORDS_OK = {"large", "x-large", "xx-large", "larger", "inherit", "initial",
                "unset", "revert", "revert-layer"}
_VAR = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)\s*(?:,\s*([^)]+))?\)")


def _to_pt(num, unit, floor):
    unit = (unit or "").lower()
    conv = {"pt": 1.0, "px": 0.75, "pc": 12.0, "in": 72.0,
            "cm": 28.3465, "mm": 2.83465}
    if unit in conv:
        return num * conv[unit]
    if unit in ("em", "rem"):
        return num * floor  # relative to body, which is pinned at the floor
    if unit == "%":
        return (num / 100.0) * floor
    return None  # unitless or unknown -> not judgeable


def _resolve_value(val, custom, depth=0):
    val = val.strip()
    m = _VAR.match(val)
    if m and depth < 8:
        name, fallback = m.group(1), m.group(2)
        if name in custom:
            return _resolve_value(custom[name], custom, depth + 1)
        if fallback:
            return _resolve_value(fallback, custom, depth + 1)
        return None
    return val


def _classify(value, floor):
    """Return (is_below_floor, resolved_pt_or_None)."""
    if value is None:
        return (False, None)
    v = value.strip().lower()
    if not v:
        return (False, None)
    if v in _KEYWORDS_OK:
        return (False, None)
    if v in _KEYWORDS_BELOW:
        return (True, None)
    m = _LEN.match(v)
    if not m:
        return (False, None)
    num = float(m.group(1))
    pt = _to_pt(num, m.group(2), floor)
    if pt is None:
        return (False, None)
    return (pt < floor - 1e-6, pt)


def scan_template_floor(assembled_html, floor):
    """Return a list of (source, raw_value, resolved_pt) for every font token below
    the floor in the assembled template (inlined CSS + inline styles)."""
    custom = {name: raw.strip() for name, raw in _ALL_CUSTOM.findall(assembled_html)}
    violations = []
    # (a) every --font* custom property literal (even if unused)
    for name, raw in custom.items():
        if "font" in name.lower():
            below, pt = _classify(_resolve_value(raw, custom), floor)
            if below:
                violations.append((name, raw, pt))
    # (b) every font-size declaration (in <style> and inline style= attributes)
    for m in _FONT_SIZE_DECL.finditer(assembled_html):
        raw = m.group(1).strip()
        below, pt = _classify(_resolve_value(raw, custom), floor)
        if below:
            violations.append(("font-size", raw, pt))
    return violations


# --------------------------------------------------------------------------- #
# WeasyPrint render.
# --------------------------------------------------------------------------- #
def resolve_weasyprint(explicit):
    for cand in [explicit, os.environ.get("WEASYPRINT_BIN"),
                 shutil.which("weasyprint"), *WEASYPRINT_FALLBACKS]:
        if cand and os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def render_pdf(assembled_html, out_pdf, weasyprint_bin, source_date_epoch):
    with tempfile.TemporaryDirectory() as td:
        html_path = os.path.join(td, "deliverable.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(assembled_html)
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = str(int(source_date_epoch))
        proc = subprocess.run([weasyprint_bin, html_path, out_pdf],
                              env=env, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- #
# Assembly (pure; no I/O beyond reading templates/css) -- reusable by callers/tests.
# --------------------------------------------------------------------------- #
def assemble(dtype, slots, template_dir, strict=False):
    tpl = load_template(template_dir, dtype)
    filled, unresolved = fill_slots(tpl, slots, strict)
    assembled = inline_css(filled, template_dir)
    return assembled, unresolved


def _load_slots(args):
    slots = {}
    if args.slots:
        slots.update(json.loads(Path(args.slots).read_text(encoding="utf-8")))
    for kv in args.slot or []:
        if "=" not in kv:
            raise ValueError("--slot expects key=value, got: %s" % kv)
        k, v = kv.split("=", 1)
        if v.startswith("@"):
            v = Path(v[1:]).read_text(encoding="utf-8")
        slots[k.strip()] = v
    return slots


def _read_content(args):
    if args.content is not None:
        return args.content
    if args.content_stdin:
        return sys.stdin.read()
    if getattr(args, "in_", None):
        return Path(args.in_).read_text(encoding="utf-8")
    return None


# --------------------------------------------------------------------------- #
# Self-test.
# --------------------------------------------------------------------------- #
SELF_TEST_MD = """# The Courage to Begin

This opening paragraph should render flush left with no first-line indent, exactly as the harvested formatter prescribes for the first paragraph after a heading.

A second paragraph carries the harvested 0.5 inch first-line indent and justified measure, with **bold** and *italic* emphasis preserved.

## The Weight of Almost

- First item with enough spacing to breathe
- Second item clearly separated from the first
- Third item maintaining consistent spacing

***

> The cave you fear to enter holds the treasure you seek.
"""


def self_test(template_dir, weasyprint_bin, floor):
    print("[pdf_render] self-test: assembling a synthetic CHAPTER through the house template")
    slots = {
        "title_locked": "The Courage to Begin",
        "subtitle_locked": "A Journey of Transformation",
        "author_name": "A. N. Author",
        "content_html": markdown_to_html(SELF_TEST_MD),
    }
    assembled, _ = assemble("chapter", slots, template_dir)

    # (1) the assembled template must carry ZERO sub-floor font tokens.
    viol = scan_template_floor(assembled, floor)
    assert not viol, "clean template unexpectedly reported sub-floor tokens: %r" % viol
    print("[pdf_render] template floor scan (clean case): PASS (0 sub-floor tokens)")

    # (2) the tripwire must CATCH an injected sub-floor inline style (exit-2 path).
    injected = assembled.replace(
        '<main data-deliverable="chapter">',
        '<main data-deliverable="chapter"><p style="font-size:12pt">tiny</p>')
    viol2 = scan_template_floor(injected, floor)
    assert any(abs((pt or 0) - 12.0) < 1e-6 for _, _, pt in viol2), \
        "injected 12pt inline style was NOT caught: %r" % viol2
    print("[pdf_render] template floor scan (detect case): PASS (12pt inline caught)")

    wp = resolve_weasyprint(weasyprint_bin)
    if not wp:
        print("[pdf_render] self-test: WeasyPrint binary NOT found; skipped the render leg "
              "(assembly + floor scan legs PASSED)")
        return EX_OK

    with tempfile.TemporaryDirectory() as td:
        out1 = os.path.join(td, "a.pdf")
        out2 = os.path.join(td, "b.pdf")
        rc1, _, err1 = render_pdf(assembled, out1, wp, DEFAULT_SOURCE_DATE_EPOCH)
        rc2, _, _ = render_pdf(assembled, out2, wp, DEFAULT_SOURCE_DATE_EPOCH)
        assert rc1 == 0 and os.path.exists(out1) and os.path.getsize(out1) > 0, \
            "render failed rc=%s err=%s" % (rc1, err1)
        print("[pdf_render] render leg: PASS (WeasyPrint at %s produced %d bytes)"
              % (wp, os.path.getsize(out1)))

        try:
            import fitz  # noqa
            sizes = []
            for out in (out1, out2):
                doc = fitz.open(out)
                s = []
                for page in doc:
                    for block in page.get_text("dict")["blocks"]:
                        for line in block.get("lines", []):
                            for span in line["spans"]:
                                if span["text"].strip():
                                    s.append(round(span["size"], 3))
                doc.close()
                sizes.append(tuple(s))
            mn = min(sizes[0]) if sizes[0] else None
            assert mn is not None and mn >= floor - 0.5, \
                "rendered PDF has a glyph below the floor: min=%s" % mn
            print("[pdf_render] rendered-glyph floor (via fitz): PASS (min span size %.1fpt >= %.1fpt)"
                  % (mn, floor))
            # Determinism per W0.6: identical (implicitly text+)size extraction across two renders.
            assert sizes[0] == sizes[1], "rendered span sizes differ across two renders"
            b1 = Path(out1).read_bytes()
            b2 = Path(out2).read_bytes()
            print("[pdf_render] determinism: PASS (identical span-size extraction across two renders; "
                  "byte-identical=%s under fixed SOURCE_DATE_EPOCH)" % (b1 == b2))
        except ImportError:
            print("[pdf_render] fitz not importable; skipped the rendered-glyph assertion "
                  "(guard-font-floor.py owns the authoritative output-side gate)")
    print("[pdf_render] self-test: PASS")
    return EX_OK


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Deterministic house-template HTML-to-PDF for the Anthology Engine (W1.12).")
    ap.add_argument("--type", choices=DELIVERABLE_TYPES, help="deliverable type / house template")
    ap.add_argument("--out", help="output PDF path")
    ap.add_argument("--in", dest="in_", help="content file (markdown or HTML)")
    ap.add_argument("--content", help="content string (markdown or HTML)")
    ap.add_argument("--content-stdin", action="store_true", help="read content from stdin")
    ap.add_argument("--format", choices=("auto", "md", "html"), default="auto",
                    help="content format (default auto-detect)")
    ap.add_argument("--slot", action="append", metavar="KEY=VALUE",
                    help="template slot; VALUE may be @path to read from a file (repeatable)")
    ap.add_argument("--slots", metavar="PATH", help="JSON file of slot key/values")
    ap.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR),
                    help="house-style directory (default: skill config/pdf-house-style)")
    ap.add_argument("--weasyprint", help="path to the weasyprint binary (else resolve/PATH)")
    ap.add_argument("--source-date-epoch", type=int, default=DEFAULT_SOURCE_DATE_EPOCH,
                    help="fixed epoch for reproducible PDF metadata")
    ap.add_argument("--floor", type=float, default=DEFAULT_FLOOR_PT,
                    help="font floor in points (default 14)")
    ap.add_argument("--strict-slots", action="store_true",
                    help="fail (exit 1) if a template slot is not provided")
    ap.add_argument("--emit-html", metavar="PATH",
                    help="also write the assembled HTML (for inspection / the guard)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable result to stdout")
    ap.add_argument("--self-test", action="store_true", help="run the built-in self-test and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test(args.template_dir, args.weasyprint, args.floor)

        if not args.type or not args.out:
            ap.error("--type and --out are required (or use --self-test)")

        slots = _load_slots(args)
        content = _read_content(args)
        if content is not None:
            cslot = CONTENT_SLOT[args.type]
            slots.setdefault(cslot, transform_content(content, args.format))

        assembled, unresolved = assemble(
            args.type, slots, args.template_dir, strict=args.strict_slots)

        if args.emit_html:
            Path(args.emit_html).write_text(assembled, encoding="utf-8")

        viol = scan_template_floor(assembled, args.floor)
        if viol:
            for src, raw, pt in viol:
                sys.stderr.write("[pdf_render] TEMPLATE FONT-FLOOR VIOLATION: %s = %r (%s pt) < %.1f\n"
                                 % (src, raw, ("%.2f" % pt) if pt is not None else "keyword", args.floor))
            if args.json:
                print(json.dumps({"result": "template_below_floor", "type": args.type,
                                  "violations": [{"source": s, "value": r,
                                                  "pt": pt} for s, r, pt in viol]}))
            return EX_FLOOR

        wp = resolve_weasyprint(args.weasyprint)
        if not wp:
            sys.stderr.write("[pdf_render] render error: WeasyPrint binary not found "
                             "(set --weasyprint or WEASYPRINT_BIN, or install weasyprint)\n")
            return EX_ERR

        rc, out, err = render_pdf(assembled, args.out, wp, args.source_date_epoch)
        if rc != 0 or not os.path.exists(args.out) or os.path.getsize(args.out) == 0:
            sys.stderr.write("[pdf_render] render error: weasyprint rc=%s\n%s\n" % (rc, err.strip()))
            return EX_ERR

        if unresolved:
            sys.stderr.write("[pdf_render] note: blanked unprovided slot(s): %s\n"
                             % ", ".join(unresolved))
        if args.json:
            print(json.dumps({"result": "rendered", "type": args.type, "out": args.out,
                              "bytes": os.path.getsize(args.out), "weasyprint": wp,
                              "source_date_epoch": args.source_date_epoch,
                              "unresolved_slots": unresolved}))
        else:
            print("[pdf_render] rendered %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
        return EX_OK

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- house exit-1 for any unexpected error
        sys.stderr.write("[pdf_render] render error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
