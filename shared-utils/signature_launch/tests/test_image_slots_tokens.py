"""One image-slot contract and brand tokens for every 78-82 page renderer.

IMG-17: the page a buyer sees carries the client's own colors and fonts, never
a banned font. IMG-18: every image on the page maps to an image-map entry and
hashes to the QC'd file. STR-22: a modified or missing design.css refuses a
token-driven page (launch_context) and fails the preflight.

Run from the repository root:
    python3 -m pytest shared-utils/signature_launch/tests/test_image_slots_tokens.py -q
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / "shared-utils" / "signature_launch" / "design"
SKILL = ROOT / "71-blackceo-signature-page"
SCRIPTS = SKILL / "scripts"
PY = sys.executable


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


image_slots = _load("sl_image_slots", DESIGN / "image_slots.py")
tokens = _load("sl_tokens_t", DESIGN / "tokens" / "tokens.py")
sys.path.insert(0, str(SCRIPTS))
launch_context = _load("lc_under_test", SCRIPTS / "launch_context.py")
preflight = _load("pf_under_test", SCRIPTS / "preflight_installed.py")

URL = "https://storage.googleapis.com/msgsndr/loc123/media/hero.png"

BRAND = {
    "brand_id": "test-only-vivid",
    "palette": {"gold": "#E4572E", "navy": "#0B3C49", "cream": "#F7F0DE"},
    "logo_only_colors": {"black": "#000000", "white": "#FFFFFF"},
    "color_tolerance": 3,
    "fonts": {"display": "Playfair Display", "body": "Space Grotesk", "accent": "Bebas Neue"},
    "banned_fonts": ["Inter", "Arial", "Helvetica", "Roboto", "system-ui", "Segoe UI"],
}
ROLES = ("landing", "product_selection", "order", "upsell", "downsell", "thank_you")


def _png(path, color):
    from PIL import Image
    Image.new("RGB", (1180, 400), color).save(path)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- contract

def test_slot_map_gives_slot_id_to_ghl_url_and_renders_the_img():
    entries = [{"id": "PKG-1", "ghl_media_url": URL, "sha256": "ab" * 32, "alt_text": "Package one"}]
    slots = image_slots.build_slots({"images": entries})
    assert image_slots.slot_url(slots, "PKG-1") == URL
    tag = image_slots.render_img(slots, "PKG-1")
    assert 'data-image-slot="PKG-1"' in tag and 'src="%s"' % URL in tag
    assert "lazy" not in tag
    for bad in (lambda: image_slots.render_img(slots, "PKG-9"),
                lambda: image_slots.build_slots([{"id": "A", "ghl_media_url": "http://x/y.png"}]),
                lambda: image_slots.build_slots([{"id": "A"}, {"id": "A"}])):
        with pytest.raises(image_slots.ImageSlotError):
            bad()
    not_uploaded = image_slots.build_slots([{"id": "PKG-2", "alt_text": "x"}])
    with pytest.raises(image_slots.ImageSlotError, match="upload"):
        image_slots.render_img(not_uploaded, "PKG-2")


def test_check_page_images_flags_unmapped_src_and_changed_bytes():
    good = b"qc'd bytes"
    slots = image_slots.build_slots([{"id": "IMG-001", "ghl_media_url": URL,
                                      "sha256": hashlib.sha256(good).hexdigest(),
                                      "alt_text": "hero"}])
    ok = [{"src": URL, "slot": "IMG-001"}]
    assert image_slots.check_page_images(slots, ok, lambda s: good) == []
    swapped = image_slots.check_page_images(slots, ok, lambda s: b"other bytes")
    assert len(swapped) == 1 and "differ from the QC'd file" in swapped[0]
    stray = image_slots.check_page_images(slots, [{"src": "https://x.test/stray.png"}], lambda s: good)
    assert len(stray) == 1 and "does not map to an image-map entry" in stray[0]
    wrong_slot = image_slots.check_page_images(slots, [{"src": URL, "slot": "IMG-777"}], lambda s: good)
    assert "does not map to an image-map entry" in wrong_slot[0]
    other_src = image_slots.check_page_images(slots, [{"src": "https://x.test/o.png", "slot": "IMG-001"}], lambda s: good)
    assert "neither" in other_src[0]


# ------------------------------------------------------------------ tokens

def test_page_css_carries_the_brand_and_never_a_banned_font():
    css = tokens.page_css(tokens.resolve_tokens(BRAND))
    assert "--sl-color-accent: #E4572E;" in css
    assert '--sl-font-body: "Space Grotesk";' in css
    assert "font-family: var(--sl-font-body)" in css
    banned = dict(BRAND, fonts={"display": "Arial", "body": "Space Grotesk", "accent": "Bebas Neue"})
    res = tokens.resolve_tokens(banned)
    assert res["typography"]["display"] is None and not res["complete"]
    assert {"field": "fonts.display", "state": "banned_font"} in res["missing"]
    assert "Arial" not in tokens.page_css(res)


# --------------------------------------------------------------- STR-22

def _tree(tmp, css_edit=None, with_shared=True):
    skill = Path(tmp) / "71-blackceo-signature-page"
    (skill / "scripts").mkdir(parents=True)
    for name in ("launch_context.py", "copy_forms.py"):
        shutil.copy(SCRIPTS / name, skill / "scripts" / name)
    if with_shared:
        shutil.copytree(DESIGN, Path(tmp) / "shared-utils/signature_launch/design",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
        if css_edit:
            css = Path(tmp) / "shared-utils/signature_launch/design/design.css"
            css.write_text(css.read_text(encoding="utf-8") + css_edit, encoding="utf-8")
    return skill


def test_design_css_in_the_real_tree_matches_the_recorded_hash():
    rec = launch_context.verify_design_css(SKILL)
    assert rec["status"] == "verified" and rec["actual_sha256"] == launch_context.DESIGN_CSS_SHA256


def test_modified_design_css_fails_launch_context_and_preflight_with_a_hash_mismatch():
    with tempfile.TemporaryDirectory() as td:
        skill = _tree(td, css_edit="\n.sl-extra { color: red; }\n")
        with pytest.raises(launch_context.LaunchContextError, match="hash mismatch"):
            launch_context.verify_design_css(skill)
        rows = preflight.check_shared(skill)
        mismatch = [r for r in rows if r[0] == "FAIL" and "hash mismatch" in r[1]]
        assert mismatch, rows
        assert not preflight.verdict_is_ready(True, True, True, rows)


def test_missing_component_refuses_a_token_driven_page_only():
    with tempfile.TemporaryDirectory() as td:
        skill = _tree(td, with_shared=False)
        assert launch_context.verify_design_css(skill)["status"] == "component_not_in_tree"
        _, record = launch_context.emit_design_tokens(skill, None)
        assert record["status"] == "component_not_in_tree"
        with pytest.raises(launch_context.LaunchContextError, match="design.css is not in the tree"):
            launch_context.verify_design_css(skill, token_driven=True)
        with pytest.raises(launch_context.LaunchContextError, match="component_not_in_tree"):
            launch_context.emit_design_tokens(skill, None, token_driven=True)
        rows = preflight.check_shared(skill)
        assert any(r[0] == "DEGRADED" and "refused" in r[2] for r in rows), rows


def test_launch_run_without_an_image_map_fails_each_image_and_other_runs_warn():
    validate_page = _load("vp_under_test", SCRIPTS / "validate_page.py")
    imgs = [{"src": "file:///run/img.png", "slot": None}]
    out = validate_page.image_contract_errors(imgs, None, [], lambda s: b"", require_map=True)
    assert len(out) == 1 and "does not map to an image-map entry" in out[0]
    assert validate_page.image_contract_errors(imgs, None, [], lambda s: b"") == []


# ---------------------------------------------- validate_page, in a browser

def _require_browser():
    try:
        from playwright.sync_api import sync_playwright
        probe = tempfile.mkdtemp(prefix="img06-probe-")
        try:
            with sync_playwright() as p:
                p.chromium.launch_persistent_context(probe, headless=True).close()
        finally:
            shutil.rmtree(probe, ignore_errors=True)
    except Exception as exc:  # a skip is named, never a pass
        pytest.skip("Playwright + Chromium not available: %s" % exc)


def _page(role, css, body_img, extra_css=""):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>%s</title><style>%s\nbody{margin:0}section{padding:32px}"
            "p{font-size:18px;line-height:1.5}.sl-cta{display:block;min-height:56px;"
            "padding:0 24px;font-size:18px;border:0}%s</style></head><body><section>"
            "<h1>%s page</h1>%s<p>The %s page copy at the mobile baseline.</p>"
            "<button class=\"sl-cta\" type=\"button\">Continue</button></section></body></html>"
            % (role, css, extra_css, role, body_img, role))


def _workspace(td, hero_color=(200, 30, 30)):
    td = Path(td)
    qc_hash = _png(td / "hero.png", hero_color)
    brand = td / "brand.json"
    brand.write_text(json.dumps(BRAND), encoding="utf-8")
    entry = {"id": "IMG-001", "ghl_media_url": URL, "sha256": qc_hash,
             "asset_file": "hero.png", "alt_text": "Section hero", "desktop_slot_px": 600}
    (td / "image-map.json").write_text(json.dumps([entry]), encoding="utf-8")
    return td, brand, entry


def _validate(td, name, brand, extra=()):
    proc = subprocess.run(
        [PY, str(SCRIPTS / "validate_page.py"), str(Path(td) / name), "--brand", str(brand),
         "--mode", "page", "--image-map", str(Path(td) / "image-map.json"),
         "--run-dir", str(Path(td) / "run"), "--widths", "390,1440", *extra],
        capture_output=True, text=True, timeout=300)
    return proc, proc.stdout


def _render_role(td, role):
    slots = image_slots.build_slots(image_slots.load_entries(Path(td) / "image-map.json"), [td])
    img = image_slots.render_img(slots, "IMG-001").replace(URL, "hero.png")  # the CDN copy, served locally
    css = tokens.page_css(tokens.resolve_tokens(BRAND))
    name = "%s.html" % role
    (Path(td) / name).write_text(_page(role, css, img), encoding="utf-8")
    return name


def _brand_and_image_errors(stdout):
    keys = ("FAIL: color:", "FAIL: font:", "FAIL: authored color", "FAIL: image")
    return [ln for ln in stdout.splitlines() if ln.startswith(keys)]


def _case_pages(td, case):
    """Build one workspace for a case; returns the page name."""
    if case in ROLES:
        return _render_role(td, case)
    name = _render_role(td, "order")
    page = Path(td) / name
    text = page.read_text(encoding="utf-8")
    if case == "banned_font":
        text = text.replace("</style>", "body{font-family:Arial;background:#112233}</style>")
    elif case == "unmapped_src":
        _png(Path(td) / "stray.png", (10, 200, 10))
        text = text.replace(
            "</section>", '<img src="stray.png" alt="stray" width="100" height="40"></section>')
    elif case == "changed_bytes":
        _png(Path(td) / "hero.png", (20, 20, 200))  # swapped after QC; the map keeps the QC'd hash
    page.write_text(text, encoding="utf-8")
    return name


@pytest.fixture(scope="module")
def validated():
    """validate_page on every case, run concurrently (each launch is a browser)."""
    _require_browser()
    from concurrent.futures import ThreadPoolExecutor
    cases = ROLES + ("banned_font", "unmapped_src", "changed_bytes")
    root = tempfile.mkdtemp(prefix="img06-")

    def one(case):
        td, brand, _ = _workspace(Path(root) / case)
        return case, _validate(td, _case_pages(td, case), brand)

    try:
        for case in cases:
            (Path(root) / case).mkdir()
        with ThreadPoolExecutor(max_workers=5) as pool:
            return dict(pool.map(one, cases))
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("role", ROLES)
def test_every_role_renders_in_brand_colors_and_fonts_with_no_banned_font(validated, role):
    _, out = validated[role]
    assert _brand_and_image_errors(out) == [], "%s\n%s" % (role, out)
    assert "banned font" not in out, (role, out)


def test_page_with_banned_font_and_off_brand_color_fails(validated):
    proc, out = validated["banned_font"]
    assert proc.returncode == 1
    assert "Arial (banned font)" in out and "authored color #112233" in out


def test_page_img_whose_src_maps_to_no_image_map_entry_fails(validated):
    proc, out = validated["unmapped_src"]
    assert proc.returncode == 1
    assert "does not map to an image-map entry" in out and "stray.png" in out


def test_page_img_whose_bytes_differ_from_the_qcd_file_fails(validated):
    proc, out = validated["changed_bytes"]
    assert proc.returncode == 1
    assert "differ from the QC'd file" in out
