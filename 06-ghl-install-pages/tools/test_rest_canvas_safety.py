"""Splice safety for ghl_rest_canvas: head assets kept (S06-09), raw card fields
refused (S06-10), images must be GHL media for funnel builds (S06-11)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import ghl_rest_canvas as rc  # noqa: E402

GHL_IMG = "https://storage.googleapis.com/msgsndr/loc123/media/hero.png"


def _doc(head="", body="<p>MARK</p>"):
    return f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>"


# ── S06-09: head assets ──────────────────────────────────────────────────────
def test_remote_head_assets_are_hoisted():
    head = (
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'
        '<script src="https://cdn.example.com/countdown.js"></script>'
        "<script>window.TIMER=1</script>"
        "<style>.a{color:red}</style>"
    )
    out = rc.html_fragment(_doc(head))
    for needle in ('name="viewport"', 'rel="preconnect"', "css2?family=Inter",
                   "cdn.example.com/countdown.js", "window.TIMER=1", ".a{color:red}", "MARK"):
        assert needle in out
    assert "<head" not in out.lower() and "<html" not in out.lower()


def test_local_stylesheet_and_script_are_inlined(tmp_path):
    (tmp_path / "site.css").write_text(".hero{background:#123}", encoding="utf-8")
    (tmp_path / "t.js").write_text("window.LOCAL_JS=1", encoding="utf-8")
    head = '<link rel="stylesheet" href="site.css"><script src="t.js"></script>'
    out = rc.html_fragment(_doc(head), base_dir=tmp_path)
    assert ".hero{background:#123}" in out and "window.LOCAL_JS=1" in out
    assert "site.css" not in out and 'src="t.js"' not in out


def test_local_asset_without_base_dir_raises_naming_the_tag():
    with pytest.raises(ValueError, match="site.css"):
        rc.html_fragment(_doc('<link rel="stylesheet" href="site.css">'))


def test_local_asset_cannot_escape_base_dir(tmp_path):
    inner = tmp_path / "src"
    inner.mkdir()
    (tmp_path / "secret.css").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes base_dir"):
        rc.html_fragment(_doc('<link rel="stylesheet" href="../secret.css">'), base_dir=inner)


def test_uncarriable_head_link_raises():
    with pytest.raises(ValueError, match="icon.png"):
        rc.html_fragment(_doc('<link rel="icon" href="icon.png">'))


# ── S06-10: raw card fields ──────────────────────────────────────────────────
@pytest.mark.parametrize("field", [
    '<input name="cardnumber">',
    '<input id="cc-number" autocomplete="cc-number">',
    '<input type="text" autocomplete="cc-csc">',
    '<input name="cvv">',
    '<input name="card_cvc">',
    "<input name='cc-exp'>",
    '<input name="exp_month">',
])
def test_card_fields_refused(field):
    body = f"<form>{field}</form>"
    with pytest.raises(ValueError, match="card-data fields refused"):
        rc.html_fragment(body)  # bare fragment path
    with pytest.raises(ValueError, match="card-data fields refused"):
        rc.html_fragment(_doc(body=body))  # full-document path
    with pytest.raises(ValueError, match="card-data fields refused"):
        rc.new_page_blob(body, require_ghl_media=False)
    assert not rc.lint_ghl_fragment(body)["ok"]


def test_ordinary_form_fields_pass():
    body = '<form><input name="email"><input name="company"><input name="expand"></form>'
    assert rc.html_fragment(body) == body
    assert rc.lint_ghl_fragment(body)["ok"]


# ── S06-11: images must be GHL media ─────────────────────────────────────────
def test_new_page_blob_funnel_refuses_relative_image():
    with pytest.raises(ValueError, match=r"images/hero\.png"):
        rc.new_page_blob('<p>MARK</p><img src="images/hero.png">')


def test_new_page_blob_funnel_refuses_external_image():
    with pytest.raises(ValueError, match="kie-temp"):
        rc.new_page_blob('<img src="https://kie-temp.example.com/x.png">')


def test_new_page_blob_accepts_ghl_media_and_explicit_opt_out():
    assert rc.new_page_blob(f'<p>MARK</p><img src="{GHL_IMG}">')["sections"]
    assert rc.new_page_blob('<img src="images/hero.png">', require_ghl_media=False)["sections"]


def test_lint_errors_on_non_ghl_image_and_passes_ghl_image():
    bad = rc.lint_ghl_fragment('<img src="images/hero.png">')
    assert not bad["ok"] and any("images/hero.png" in e for e in bad["errors"])
    assert rc.lint_ghl_fragment(f'<img src="{GHL_IMG}">')["ok"]
    assert rc.lint_ghl_fragment('<img src="images/hero.png">', require_ghl_media=False)["ok"]


# ── Combined reporting (probe doc, row 3 + row 5) ────────────────────────────
PROBE_DOC = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.gstatic.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&display=swap">
<link rel="stylesheet" href="styles.css"><script src="https://cdn.example/countdown.js"></script>
<style>.h{font-family:Anton}</style></head><body><h1 class="h">BF</h1><img src="images/hero.png"><script>startCountdown()</script></body></html>"""


def test_new_page_blob_probe_doc_names_hero_png():
    with pytest.raises(ValueError) as ei:
        rc.new_page_blob(PROBE_DOC)
    assert "images/hero.png" in str(ei.value) and "styles.css" in str(ei.value)


def test_html_fragment_probe_doc_names_dropped_stylesheet():
    with pytest.raises(ValueError, match="styles.css"):
        rc.html_fragment(PROBE_DOC)


def test_head_and_card_problems_reported_together():
    with pytest.raises(ValueError) as ei:
        rc.html_fragment(_doc(head='<link rel="stylesheet" href="site.css">', body='<input name="cvv">'))
    assert "card-data fields refused" in str(ei.value) and "site.css" in str(ei.value)
