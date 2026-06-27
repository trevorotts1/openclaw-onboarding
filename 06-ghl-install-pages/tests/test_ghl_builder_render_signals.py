"""MOCK-only unit tests — render_check anti-fabricated-pass signal helpers.

These cover the P0-1 / P0-2 / P1-3 signal-integrity hardening of
``ghl_builder.render_check``: the pure, side-effect-free helpers that strip the
non-visible DOM machinery, measure REAL visible text, parse a REAL navigation
HTTP status (fail-closed on unknown), robustly classify console errors, compute
the structural content-richness floor, and pixel-inspect a screenshot for a
blank render.

The helpers are deliberately factored OUT of ``render_check`` (which needs the
singleton agent-browser) precisely so the load-bearing pass/fail logic is
unit-testable WITHOUT any browser, network, or live GoHighLevel. Nothing here
touches the network or opens a browser.

Background — the bugs these close (a blank / crashed GoHighLevel preview page
that previously scored ``ok=True``):
  * P0-1a: ``http = 200 if dom_bytes > 100 else 500`` credited any non-empty
    error page as HTTP 200.
  * P0-1b: visible-text length was measured over the RAW DOM, so a blank page's
    large Nuxt ``__NUXT__`` hydration <script> blob counted as "content".
  * P0-1c: the marker was matched against the raw DOM, so a marker echoed into a
    hydration <script> (never rendered) counted as "marker in rendered DOM".
  * P0-1d: console errors emitted as PLAIN TEXT (no structured type) were
    silently dropped — the ``TypeError: Cannot read properties of undefined
    (reading 'colors')`` GoHighLevel crash never failed the check.
  * P0-2: the screenshot was captured but never pixel-inspected.
"""

from __future__ import annotations

import os
import sys

# Make the tools/ dir importable regardless of cwd — same convention as the
# sibling tests in this suite.
_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_builder as b


# ── strip_non_visible_html (P0-1b/c substrate) ────────────────────────────────

def test_strip_removes_script_style_template_noscript_and_comments():
    html = (
        "<div id='real'>Hello</div>"
        "<script>window.__NUXT__={a:1};</script>"
        "<style>.x{color:red}</style>"
        "<template><p>tpl</p></template>"
        "<noscript>nojs</noscript>"
        "<!-- secret-marker -->"
    )
    out = b.strip_non_visible_html(html)
    assert "Hello" in out
    assert "id='real'" in out
    assert "__NUXT__" not in out
    assert "color:red" not in out
    assert "tpl" not in out
    assert "nojs" not in out
    assert "secret-marker" not in out


def test_strip_handles_truncated_unclosed_script_tail():
    # A captured DOM truncated mid-<script> must not leave the blob behind.
    html = "<div>visible</div><script>var x = 'huge hydration blob never closed"
    out = b.strip_non_visible_html(html)
    assert "visible" in out
    assert "hydration blob" not in out


def test_strip_is_case_insensitive():
    html = "<DIV>keep</DIV><SCRIPT>drop</SCRIPT>"
    out = b.strip_non_visible_html(html)
    assert "keep" in out
    assert "drop" not in out


# ── visible_text length (P0-1b blank-page signal) ─────────────────────────────

def test_visible_text_excludes_script_blob_so_blank_page_is_short():
    # A blank page: tiny visible text + a massive hydration script.
    blob = "x" * 5000
    blank = f"<body><script>window.__NUXT__='{blob}';</script><div></div></body>"
    assert len(b.visible_text(blank)) < b.MIN_RENDERED_TEXT


def test_visible_text_counts_real_copy_and_decodes_entities():
    para = "Welcome to the funnel. " * 40
    rich = f"<body><h1>Hi&amp;Bye</h1><p>{para}</p></body>"
    text = b.visible_text(rich)
    assert len(text) >= b.MIN_RENDERED_TEXT
    assert "Hi&Bye" in text  # entity decoded, not "Hi&amp;Bye"
    assert "__NUXT__" not in text


# ── content_richness (P1-3 structural floor) ──────────────────────────────────

def test_content_richness_counts_images_blocks_and_headline():
    html = (
        "<section><h2>Headline</h2>"
        "<div><p>Para one</p></div>"
        "<img src='https://cdn/x.jpg'>"
        "<img src=''>"  # empty src — NOT counted as loaded
        "<img>"          # no src — NOT counted
        "</section>"
    )
    r = b.content_richness(b.strip_non_visible_html(html))
    assert r["img_count"] == 1
    assert r["has_headline"] is True
    assert r["block_count"] >= 3  # section, div, p, h2


def test_content_richness_blank_page_scores_zero():
    r = b.content_richness(b.strip_non_visible_html("<body></body>"))
    assert r["img_count"] == 0
    assert r["block_count"] == 0
    assert r["has_headline"] is False


# ── parse_nav_http_status (P0-1a real status, fail-closed) ────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("navigated, status: 200 ok", 200),
        ('{"statusCode": 404}', 404),
        ("HTTP/1.1 500 Internal Server Error", 500),
        ("response 301 redirect", 301),
        ('"status":403', 403),
    ],
)
def test_parse_nav_http_status_extracts_keyword_anchored_code(text, expected):
    assert b.parse_nav_http_status(text) == expected


def test_parse_nav_http_status_none_when_absent_fails_closed():
    # No status keyword anywhere -> None (caller then falls back to urllib).
    assert b.parse_nav_http_status("opened the page, all good") is None
    assert b.parse_nav_http_status("") is None
    assert b.parse_nav_http_status(None) is None


def test_parse_nav_http_status_ignores_bare_numbers_in_body():
    # A page body mentioning '200 reviews' must NOT be read as HTTP 200.
    assert b.parse_nav_http_status("the testimonial says 200 reviews") is None


def test_parse_nav_http_status_scans_multiple_streams():
    assert b.parse_nav_http_status("", "stderr says status=502") == 502


# ── console_line_is_error (P0-1d robust severity) ─────────────────────────────

@pytest.mark.parametrize(
    "line",
    [
        "TypeError: Cannot read properties of undefined (reading 'colors')",
        "[error] something blew up",
        "pageerror: boom",
        "Uncaught ReferenceError: x is not defined",
        "ERROR  failed to mount",
        "SEVERE: render failed",
        "foo is not a function",
    ],
)
def test_console_line_is_error_true_for_real_errors(line):
    assert b.console_line_is_error(line) is True


@pytest.mark.parametrize(
    "line",
    [
        "info: hydration complete",
        "the error-handling guide loaded fine",  # 'error' mid-sentence, no anchor
        "log: user clicked button",
        "",
    ],
)
def test_console_line_is_error_false_for_benign(line):
    assert b.console_line_is_error(line) is False


# ── png_blank_report (P0-2 screenshot pixel inspection) ───────────────────────

def _save_png(path, color, size=(200, 200)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)


def test_png_blank_report_flags_single_color(tmp_path):
    p = str(tmp_path / "blank.png")
    _save_png(p, (255, 255, 255))
    rep = b.png_blank_report(p)
    assert rep["determinable"] is True
    assert rep["blank"] is True
    assert rep["dominant_fraction"] == 1.0


def test_png_blank_report_passes_rich_image(tmp_path):
    from PIL import Image
    p = str(tmp_path / "rich.png")
    # A noisy multi-colour image — no single colour dominates.
    img = Image.new("RGB", (200, 200))
    px = img.load()
    for y in range(200):
        for x in range(200):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, (x * y) % 256)
    img.save(p)
    rep = b.png_blank_report(p)
    assert rep["determinable"] is True
    assert rep["blank"] is False


def test_png_blank_report_flags_undersized_capture(tmp_path):
    p = str(tmp_path / "tiny.png")
    _save_png(p, (10, 20, 30), size=(8, 8))
    rep = b.png_blank_report(p)
    assert rep["blank"] is True
    assert "below_min_dims" in rep["reason"]


def test_png_blank_report_missing_file_is_undeterminable_not_blank(tmp_path):
    rep = b.png_blank_report(str(tmp_path / "nope.png"))
    assert rep["determinable"] is False
    assert rep["blank"] is False  # cannot inspect => NON-fatal, never a forced pass-block


def test_png_blank_report_near_single_color_above_threshold(tmp_path):
    from PIL import Image
    p = str(tmp_path / "almost_blank.png")
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    # A handful of off pixels (0.05%) — still >= 98% white => blank.
    px = img.load()
    for i in range(5):
        px[i, 0] = (0, 0, 0)
    img.save(p)
    rep = b.png_blank_report(p)
    assert rep["blank"] is True
    assert rep["dominant_fraction"] >= 0.98
