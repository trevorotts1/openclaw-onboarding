#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: BOOK TEASER PDF RENDERER (Step 13)
# -----------------------------------------------------------------------------
# Interview mode ONLY. Personal mode never reaches this script.
#
# WHAT THIS IS
#   A deterministic typesetter and verifier. It takes teaser prose that was
#   ALREADY WRITTEN on the runtime content tier (Kimi 2.6, then GLM 5.2, thinking
#   high, then the OpenRouter equivalents, then Gemini 3.1 Flash Lite) and lays it
#   out as a book-typeset PDF. This script writes NO prose, makes NO model call,
#   opens NO network socket, and touches NO MCP tier. Same input, same layout.
#   Its runtime cost is 0.00 dollars.
#
# THE FLOOR IT ENFORCES (the module's mechanical checks)
#   1. No font below 14 point, verified INDEPENDENTLY from the rendered PDF, not
#      merely trusted from the stylesheet.
#   2. At most three pages. Over the cap fails; the script never silently trims.
#   3. Zero em dash characters and zero triple backtick fences in the teaser text
#      (fleet writing law; checked before rendering so a bad draft fails cheap).
#   4. The produced PDF opens, is non empty, and is a real book layout.
#   The semantic checks (own voice fidelity, obvious cliffhanger, no fabrication)
#   belong to the episode gate and the judge tier, never to this script; this
#   script emits them only as advisory hints.
#
# BACKENDS (auto detected, cheapest reliable first)
#   weasyprint  preferred, the fleet PDF toolchain (Skill 53 book writer reuse)
#   chrome      Chrome or Chromium headless print to pdf, automatic fallback
#   If neither is present the typeset HTML is written as a degraded artifact and
#   the script exits 4 so the pipeline surfaces the limitation honestly and never
#   fakes a pass.
#
# EXIT CODES
#   0  PASS       PDF rendered and every mechanical check passed
#   2  VERIFY     text or PDF failed a mechanical check (pages, font, em dash...)
#   3  USAGE/IO   bad arguments, missing input, or a write error
#   4  TOOLCHAIN  no PDF backend available; HTML emitted, PDF not rendered
#
# USAGE
#   render_book_teaser.py --content teaser.json --out teaser.pdf [--json]
#   render_book_teaser.py --content teaser.md --person-name "Ada Lovelace" \
#       --book-title "The Engine Within" --out teaser.pdf
#   render_book_teaser.py --self-test
#
# The generate, verify, retry loop follows the Skill 35 render posture; the pinned
# print stylesheet follows the Skill 53 book writer readability posture, raised to
# the 14 point floor this bonus asset requires.
# =============================================================================
"""Book teaser PDF renderer and mechanical verifier for the Podcast Production Engine."""

import argparse
import html as _html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- constants ---------------------------------------------------------------

FONT_FLOOR_PT = 14.0            # no font below this, ever
FONT_FLOOR_EPS = 0.6           # absorb renderer rounding; a stray 12pt still trips
PAGE_CAP = 3                   # at most three pages, hard
MAX_RENDER_ATTEMPTS = 3        # generate, verify, retry (Skill 35 posture)
WORD_SOFT_FLOOR = 120         # advisory only; a real first chapter intro is not tiny
EM_DASH = chr(0x2014)          # the banned character, built from its code point so
HORIZONTAL_BAR = chr(0x2015)   # this source file itself carries zero literal em dashes
TRIPLE_BACKTICK = chr(96) * 3  # never spelled literally so this file stays fence clean

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)

# --- pinned print stylesheet (14 point floor lives here, one auditable place) --
# Every font-size below is at or above the floor. _assert_css_floor refuses to run
# if that ever stops being true, so the stylesheet cannot silently drift under 14pt.

PRINT_CSS = """
@page {
  size: 6in 9in;
  margin: 0.95in 0.85in 0.9in 0.85in;
}
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: "Georgia", "Iowan Old Style", "Palatino Linotype", "Palatino", serif;
  font-size: 15pt;
  line-height: 1.62;
  color: #17140f;
  hyphens: auto;
  text-rendering: optimizeLegibility;
}
.opener { margin: 0 0 1.4em; text-align: center; }
.book-title {
  font-size: 30pt;
  line-height: 1.15;
  letter-spacing: 0.01em;
  margin: 0.2em 0 0.35em;
  font-weight: 600;
}
.byline {
  font-size: 16pt;
  font-style: italic;
  color: #4a433a;
  margin: 0 0 1.1em;
}
.rule {
  width: 34%;
  margin: 0.6em auto 1.2em;
  border: none;
  border-top: 1.5px solid #b9ad99;
}
h1.chapter {
  font-size: 22pt;
  line-height: 1.25;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  margin: 0.4em 0 0.15em;
  font-weight: 600;
  page-break-after: avoid;
}
.chapter-title {
  font-size: 18pt;
  font-style: italic;
  color: #35302a;
  margin: 0 0 0.4em;
  page-break-after: avoid;
}
.body { text-align: justify; }
.body p {
  font-size: 15pt;
  margin: 0 0 0.55em;
  orphans: 2;
  widows: 2;
}
.body p + p { text-indent: 1.5em; }
.body p.first { text-indent: 0; }
.body p.first::first-letter {
  font-size: 34pt;
  line-height: 0.9;
  font-weight: 600;
  padding-right: 0.06em;
}
""".strip()


# --- result plumbing ---------------------------------------------------------

class Result:
    """Small collector so the caller gets one JSON verdict on stdout, no fences."""

    def __init__(self):
        self.checks = []          # list of {name, ok, detail}
        self.pages = None
        self.min_font_pt = None
        self.backend = None
        self.pdf_path = None
        self.html_path = None
        self.bytes = None
        self.words = None
        self.hints = []           # advisory, never a gate
        self.exit_code = 0

    def check(self, name, ok, detail=""):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    def hint(self, text):
        self.hints.append(text)

    @property
    def passed(self):
        return all(c["ok"] for c in self.checks)

    def to_dict(self):
        return {
            "ok": self.passed and self.exit_code == 0,
            "exit_code": self.exit_code,
            "backend": self.backend,
            "pages": self.pages,
            "page_cap": PAGE_CAP,
            "min_font_pt": self.min_font_pt,
            "font_floor_pt": FONT_FLOOR_PT,
            "bytes": self.bytes,
            "words": self.words,
            "pdf_path": self.pdf_path,
            "html_path": self.html_path,
            "checks": self.checks,
            "advisory_hints": self.hints,
        }


class RenderError(Exception):
    """Raised when a backend cannot produce a PDF."""


# --- input parsing -----------------------------------------------------------

def _read_content(path, args):
    """Return (meta, paragraphs). Accepts JSON (preferred) or plain text / markdown.

    JSON fields (all optional except the body):
      person_name, book_title, chapter_label, chapter_title, episode_title,
      paragraphs [list of str]  OR  body [str, blank-line separated].
    Flags override JSON metadata when supplied.
    """
    raw = Path(path).read_text(encoding="utf-8")
    meta = {
        "person_name": args.person_name,
        "book_title": args.book_title,
        "chapter_label": args.chapter_label,
        "chapter_title": args.chapter_title,
        "episode_title": args.episode_title,
    }
    paragraphs = []

    stripped = raw.lstrip()
    is_json = path.lower().endswith(".json") or stripped.startswith("{")
    if is_json:
        data = json.loads(raw)
        for k in list(meta.keys()):
            if meta[k] is None and data.get(k):
                meta[k] = str(data[k]).strip()
        if isinstance(data.get("paragraphs"), list):
            paragraphs = [str(p).strip() for p in data["paragraphs"] if str(p).strip()]
        elif isinstance(data.get("body"), str):
            paragraphs = _split_paragraphs(data["body"])
        else:
            raise ValueError("teaser JSON needs a non empty 'paragraphs' list or 'body' string")
    else:
        text = raw
        # a leading markdown H1 is treated as the chapter title, not body
        m = re.match(r"^\s*#\s+(.+?)\s*\n", text)
        if m and not meta["chapter_title"]:
            meta["chapter_title"] = m.group(1).strip()
            text = text[m.end():]
        paragraphs = _split_paragraphs(text)

    if not paragraphs:
        raise ValueError("no teaser body found after parsing %s" % path)
    return meta, paragraphs


def _split_paragraphs(text):
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for b in blocks:
        joined = " ".join(line.strip() for line in b.splitlines() if line.strip())
        if joined:
            out.append(joined)
    return out


# --- pre-render text law -----------------------------------------------------

_MD_LEAK_RE = re.compile(r"(^|\s)(#{1,6}\s|\*{1,2}\S|_{1,2}\S|>\s|-\s|\d+\.\s)")


def _check_text_law(meta, paragraphs, r):
    """Fleet writing law on the teaser text, checked before rendering (fails cheap)."""
    corpus = "\n".join(paragraphs) + "\n" + "\n".join(
        v for v in meta.values() if v)

    r.check("no_em_dash",
            EM_DASH not in corpus and HORIZONTAL_BAR not in corpus,
            "em dash characters are forbidden fleet wide")
    r.check("no_triple_backtick",
            TRIPLE_BACKTICK not in corpus,
            "no triple backtick code fences in produced content")
    r.check("non_empty_body",
            len(paragraphs) >= 1 and any(len(p.split()) >= 3 for p in paragraphs),
            "teaser body is present")

    words = sum(len(p.split()) for p in paragraphs)
    r.words = words
    if words < WORD_SOFT_FLOOR:
        r.hint("teaser is %d words, below the %d word soft floor for a real first "
               "chapter intro; advisory only, not a gate" % (words, WORD_SOFT_FLOOR))

    # markdown leakage is advisory: the writer should hand clean prose, but a stray
    # marker is not a hard fail here (the PDF text and the episode gate catch style).
    for p in paragraphs:
        if _MD_LEAK_RE.search(p):
            r.hint("possible markdown marker in the teaser body; the teaser should "
                   "read as clean book prose, not a document with markup")
            break

    # cliffhanger is a SEMANTIC check owned by the episode gate; advisory hint only.
    last = paragraphs[-1].rstrip()
    if not (last.endswith("...") or last.endswith("…") or last.endswith("?")
            or re.search(r"\b(but|until|then|and that is when|what I did not)\b",
                         last, re.I)):
        r.hint("final line has no obvious cliffhanger signal; the episode gate and "
               "judge tier make the real cliffhanger call, this is advisory only")


# --- html assembly -----------------------------------------------------------

def _assert_css_floor(css):
    """Refuse to run if the pinned stylesheet ever declares a font below the floor."""
    for m in re.finditer(r"font-size:\s*([0-9.]+)pt", css):
        if float(m.group(1)) < FONT_FLOOR_PT:
            raise RenderError("stylesheet declares %spt, below the %.0fpt floor"
                              % (m.group(1), FONT_FLOOR_PT))


def _build_html(meta, paragraphs, css):
    _assert_css_floor(css)

    def esc(s):
        return _html.escape(s, quote=False)

    head = ['<article class="teaser">']
    opener = ['<header class="opener">']
    if meta.get("book_title"):
        opener.append('<div class="book-title">%s</div>' % esc(meta["book_title"]))
    if meta.get("person_name"):
        opener.append('<div class="byline">by %s</div>' % esc(meta["person_name"]))
    opener.append('<hr class="rule" />')
    opener.append('<h1 class="chapter">%s</h1>'
                  % esc(meta.get("chapter_label") or "Chapter One"))
    if meta.get("chapter_title"):
        opener.append('<div class="chapter-title">%s</div>' % esc(meta["chapter_title"]))
    opener.append('</header>')

    body = ['<section class="body">']
    for i, p in enumerate(paragraphs):
        cls = ' class="first"' if i == 0 else ''
        body.append('<p%s>%s</p>' % (cls, esc(p)))
    body.append('</section>')

    head.extend(opener)
    head.extend(body)
    head.append('</article>')
    inner = "\n".join(head)

    title = esc(meta.get("book_title") or meta.get("chapter_title") or "Book Teaser")
    doc = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8" />\n'
        '<title>%s</title>\n'
        '<style>\n%s\n</style>\n'
        '</head>\n<body>\n%s\n</body>\n</html>\n'
    ) % (title, css, inner)
    return doc


# --- backends ----------------------------------------------------------------

def _have_weasyprint():
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


def _find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c):
            if os.path.exists(c):
                return c
        else:
            found = shutil.which(c)
            if found:
                return found
    return None


def _render_weasyprint(html_doc, out_pdf, css):
    from weasyprint import HTML, CSS
    doc = HTML(string=html_doc).render(stylesheets=[CSS(string=css)])
    doc.write_pdf(out_pdf)
    return len(doc.pages)


def _render_chrome(chrome_bin, html_doc, out_pdf):
    with tempfile.TemporaryDirectory() as td:
        html_path = os.path.join(td, "teaser.html")
        Path(html_path).write_text(html_doc, encoding="utf-8")
        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=3000",
            "--print-to-pdf=%s" % out_pdf,
            "file://%s" % html_path,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=90)
        if not os.path.exists(out_pdf) or os.path.getsize(out_pdf) == 0:
            # retry once with the legacy flag names for older Chrome builds
            cmd2 = [
                chrome_bin, "--headless", "--disable-gpu", "--no-sandbox",
                "--print-to-pdf-no-header",
                "--print-to-pdf=%s" % out_pdf, "file://%s" % html_path,
            ]
            subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=90)
        if not os.path.exists(out_pdf) or os.path.getsize(out_pdf) == 0:
            raise RenderError("chrome headless produced no pdf: %s"
                              % proc.stderr.decode("utf-8", "replace")[:400])
    return None  # page count comes from independent verification


# --- independent verification of the produced pdf ----------------------------

def _verify_pdf(out_pdf, r):
    """Measure pages and the minimum font size from the PDF itself, backend agnostic."""
    size = os.path.getsize(out_pdf) if os.path.exists(out_pdf) else 0
    r.bytes = size
    if size == 0:
        r.check("pdf_nonempty", False, "rendered PDF is empty or missing")
        return
    r.check("pdf_nonempty", True, "%d bytes" % size)

    pages, min_font = _measure_pdf(out_pdf)
    r.pages = pages
    r.min_font_pt = round(min_font, 2) if min_font is not None else None

    if pages is None:
        r.check("page_cap", False, "could not read page count from the PDF")
    else:
        r.check("page_cap", pages <= PAGE_CAP,
                "%d page(s); cap is %d" % (pages, PAGE_CAP))

    if min_font is None:
        # no measurable spans (for example an image only PDF); treat as a fail so
        # the pipeline never assumes the floor held when it could not be proven.
        r.check("font_floor", False,
                "no measurable text spans; the 14 point floor could not be proven")
    else:
        r.check("font_floor", min_font >= (FONT_FLOOR_PT - FONT_FLOOR_EPS),
                "smallest measured font %.2fpt; floor %.0fpt" % (min_font, FONT_FLOOR_PT))


def _measure_pdf(out_pdf):
    """Return (page_count, min_font_pt). Prefer pymupdf; fall back to pdfinfo/pypdf."""
    # primary: pymupdf reads per span sizes, the load bearing font measurement
    try:
        import fitz  # pymupdf
        doc = fitz.open(out_pdf)
        pages = doc.page_count
        min_font = None
        for page in doc:
            d = page.get_text("dict")
            for block in d.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not span.get("text", "").strip():
                            continue
                        sz = float(span.get("size", 0.0))
                        if sz <= 0:
                            continue
                        min_font = sz if min_font is None else min(min_font, sz)
        doc.close()
        return pages, min_font
    except Exception:
        pass

    # fallback page count only (font floor unprovable without a span reader)
    pages = _page_count_fallback(out_pdf)
    return pages, None


def _page_count_fallback(out_pdf):
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            out = subprocess.run([pdfinfo, out_pdf], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, timeout=30)
            for line in out.stdout.decode("utf-8", "replace").splitlines():
                if line.lower().startswith("pages:"):
                    return int(line.split(":", 1)[1].strip())
        except Exception:
            pass
    try:
        import pypdf
        return len(pypdf.PdfReader(out_pdf).pages)
    except Exception:
        return None


# --- orchestration -----------------------------------------------------------

def render(meta, paragraphs, out_pdf, css, backend_choice, r):
    """Generate, verify, retry. Returns the exit code."""
    _check_text_law(meta, paragraphs, r)
    if not r.passed:
        # a text law failure is cheap and terminal; do not spend a render on it
        r.exit_code = 2
        return r.exit_code

    html_doc = _build_html(meta, paragraphs, css)

    # write the typeset HTML next to the PDF as a durable, backend independent
    # artifact and the degraded deliverable when no PDF backend exists
    html_path = str(Path(out_pdf).with_suffix(".html"))
    Path(html_path).write_text(html_doc, encoding="utf-8")
    r.html_path = html_path

    backends = _resolve_backends(backend_choice)
    if not backends:
        r.backend = "none"
        r.hint("no PDF backend found; install weasyprint (pip install weasyprint) "
               "or Chrome/Chromium; the typeset HTML was written instead")
        r.check("pdf_rendered", False, "no PDF backend available")
        r.exit_code = 4
        return r.exit_code

    # Retries absorb TRANSIENT render exceptions (a backend that threw). A render
    # that succeeds but fails verification is DETERMINISTIC for that input, so we
    # do not re-render the identical HTML on the same backend; we advance to the
    # next backend, whose pagination may differ, and otherwise report the failure.
    last_err = None
    verify_names = ("pdf_nonempty", "page_cap", "font_floor", "pdf_rendered")
    for name, fn in backends:
        rendered = False
        for attempt in range(1, MAX_RENDER_ATTEMPTS + 1):
            try:
                fn(html_doc, out_pdf, css) if name == "weasyprint" else fn(html_doc, out_pdf)
                rendered = True
                break
            except Exception as e:  # noqa: BLE001
                last_err = "%s attempt %d: %s" % (name, attempt, e)
                continue
        if not rendered:
            continue
        # clear any verify verdicts from a prior backend before scoring this one
        r.checks = [c for c in r.checks if c["name"] not in verify_names]
        r.backend = name
        r.check("pdf_rendered", True, "backend=%s" % name)
        _verify_pdf(out_pdf, r)
        if r.passed:
            r.exit_code = 0
            return r.exit_code
        last_err = "verification failed on backend %s" % name

    # exhausted every backend
    if not any(c["name"] == "pdf_rendered" and c["ok"] for c in r.checks):
        r.check("pdf_rendered", False, last_err or "render failed on every backend")
    r.exit_code = 2
    r.hint(last_err or "render and verify did not converge")
    return r.exit_code


def _resolve_backends(choice):
    weasy = ("weasyprint", lambda h, o, c: _render_weasyprint(h, o, c))
    chrome_bin = _find_chrome()
    chrome = ("chrome", lambda h, o: _render_chrome(chrome_bin, h, o)) if chrome_bin else None

    if choice == "weasyprint":
        return [weasy] if _have_weasyprint() else []
    if choice == "chrome":
        return [chrome] if chrome else []
    # auto: weasyprint first (fleet toolchain), then chrome
    ordered = []
    if _have_weasyprint():
        ordered.append(weasy)
    if chrome:
        ordered.append(chrome)
    return ordered


# --- self test ---------------------------------------------------------------

_SELF_TEST_TEASER = {
    "person_name": "Dr. Amara Okafor",
    "book_title": "The Quiet Ledger",
    "chapter_label": "Chapter One",
    "chapter_title": "The Numbers Nobody Read",
    "episode_title": "How A Rural Clinic Rewrote Its Own Odds",
    "paragraphs": [
        "The first spreadsheet I ever saved did not look like hope. It looked like a "
        "wall of red, forty rows of a clinic that most people had already decided was "
        "going to close. I was twenty nine, three months into a job nobody else wanted, "
        "and I was the only person in the building who still believed the numbers were "
        "telling a story instead of writing an obituary.",
        "My grandmother used to say that a ledger is a diary that refuses to lie. She "
        "kept the books for a market stall for thirty one years, and she taught me that "
        "if you read the columns slowly enough, they start to whisper. So I read them "
        "slowly. I read them at midnight when the generators hummed and the corridors "
        "went the particular kind of quiet that only a small hospital knows.",
        "What the columns whispered was not a shortage of money. It was a shortage of "
        "attention. Every leak in that budget traced back to a decision no one had "
        "revisited in years, a habit dressed up as a policy, a truth everyone had agreed "
        "to stop looking at. I did not need a rescue. I needed permission to look.",
        "So on a Tuesday I did the one thing they tell you never to do in a place that "
        "is barely surviving. I called a meeting and I put the wall of red on the "
        "projector, and I told forty exhausted people the number I was most afraid of. "
        "And then I told them what I had found underneath it, the thing that would change "
        "everything, the thing I had checked and rechecked until my hands stopped shaking.",
        "What happened in that room over the next ninety minutes is the reason you are "
        "holding this book. But to understand why it worked, you have to understand what "
        "I saw in row thirty seven, the single line I almost deleted, the one that turned "
        "out to be worth more than the entire grant we had been begging for. I have never "
        "told this part to anyone. Until now.",
    ],
}


def _self_test():
    import io  # noqa: F401
    with tempfile.TemporaryDirectory() as td:
        content = os.path.join(td, "teaser.json")
        Path(content).write_text(json.dumps(_SELF_TEST_TEASER), encoding="utf-8")
        out_pdf = os.path.join(td, "teaser.pdf")
        r = Result()
        meta, paragraphs = _read_content(content, _fake_args())
        code = render(meta, paragraphs, out_pdf, PRINT_CSS, "auto", r)
        verdict = r.to_dict()
        print(json.dumps(verdict, indent=2))
        # a self test passes when EITHER a PDF backend proved the floor (exit 0) OR
        # no backend exists on this box (exit 4) but every text law and the HTML
        # artifact were produced. It fails only on a genuine mechanical breach.
        if code == 0:
            print("SELF-TEST: PASS (pdf rendered, %d page(s), min font %.2fpt, backend %s)"
                  % (r.pages, r.min_font_pt, r.backend), file=sys.stderr)
            return 0
        if code == 4:
            law_ok = all(c["ok"] for c in r.checks
                         if c["name"] in ("no_em_dash", "no_triple_backtick",
                                          "non_empty_body"))
            html_ok = r.html_path and os.path.exists(r.html_path)
            if law_ok and html_ok:
                print("SELF-TEST: PASS (no PDF backend on this box; text law held and "
                      "typeset HTML written; install weasyprint or Chrome for the PDF)",
                      file=sys.stderr)
                return 0
        print("SELF-TEST: FAIL (exit %d)" % code, file=sys.stderr)
        return 1


class _FakeArgs:
    person_name = None
    book_title = None
    chapter_label = None
    chapter_title = None
    episode_title = None


def _fake_args():
    return _FakeArgs()


# --- cli ---------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render a book teaser as a book-typeset PDF (Interview mode only) "
                    "and verify the 14 point floor and three page cap.")
    ap.add_argument("--content", help="teaser content file (.json preferred, or .md/.txt)")
    ap.add_argument("--out", help="output PDF path")
    ap.add_argument("--backend", choices=["auto", "weasyprint", "chrome"], default="auto")
    ap.add_argument("--person-name", dest="person_name", default=None)
    ap.add_argument("--book-title", dest="book_title", default=None)
    ap.add_argument("--chapter-label", dest="chapter_label", default=None)
    ap.add_argument("--chapter-title", dest="chapter_title", default=None)
    ap.add_argument("--episode-title", dest="episode_title", default=None)
    ap.add_argument("--css", default=None,
                    help="optional print stylesheet override; re-validated for the floor")
    ap.add_argument("--json", action="store_true", help="print the JSON verdict to stdout")
    ap.add_argument("--self-test", action="store_true", help="render a fixture and verify")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.content or not args.out:
        ap.error("--content and --out are required (or use --self-test)")
    if not os.path.exists(args.content):
        print("ERROR: content file not found: %s" % args.content, file=sys.stderr)
        return 3

    css = PRINT_CSS
    if args.css:
        try:
            css = Path(args.css).read_text(encoding="utf-8")
            _assert_css_floor(css)
        except RenderError as e:
            print("ERROR: %s" % e, file=sys.stderr)
            return 3
        except Exception as e:  # noqa: BLE001
            print("ERROR: could not read --css: %s" % e, file=sys.stderr)
            return 3

    try:
        meta, paragraphs = _read_content(args.content, args)
    except Exception as e:  # noqa: BLE001
        print("ERROR: could not parse teaser content: %s" % e, file=sys.stderr)
        return 3

    out_dir = os.path.dirname(os.path.abspath(args.out))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        print("ERROR: could not create output directory: %s" % e, file=sys.stderr)
        return 3

    r = Result()
    r.pdf_path = os.path.abspath(args.out)
    code = render(meta, paragraphs, args.out, css, args.backend, r)

    verdict = r.to_dict()
    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        status = {0: "PASS", 2: "VERIFY-FAIL", 3: "USAGE/IO", 4: "TOOLCHAIN-ABSENT"}.get(
            code, "FAIL")
        print("%s pages=%s min_font=%spt backend=%s bytes=%s -> %s"
              % (status, verdict["pages"], verdict["min_font_pt"], verdict["backend"],
                 verdict["bytes"], args.out))
        for c in verdict["checks"]:
            if not c["ok"]:
                print("  FAIL %s: %s" % (c["name"], c["detail"]), file=sys.stderr)
        for h in verdict["advisory_hints"]:
            print("  hint: %s" % h, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
