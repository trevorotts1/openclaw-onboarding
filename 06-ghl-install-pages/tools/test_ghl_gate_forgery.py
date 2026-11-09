"""Forgery tests for the Skill 6 verdict gate (S06-04, S06-05, S06-22).

Run from the repo root:
    python3 -m pytest 06-ghl-install-pages/tools/test_ghl_gate_forgery.py -q

No network, no browser: ``ghl_builder.render_check`` is replaced by a stub that
writes real dom/png/console files, so the genuine tree below is produced by the
REAL ``ghl_verify.verify_all`` (live mode) and read by the REAL ``ghl_gate``.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
import uuid

import pytest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_builder  # noqa: E402
import ghl_gate  # noqa: E402
import ghl_verify  # noqa: E402

_VALIDATE_INSTALL = os.path.join(
    _TOOLS, "..", "..", "71-blackceo-signature-page", "scripts", "validate_install.py")

MARKER = "SKILL6-MARKER-1234"
COPY = "Approved headline for the Black Friday offer"
STALE = "Lorem ipsum placeholder copy goes here"


def _dom(marker: str, body: str) -> str:
    return f"<html><body><h1>{body}</h1><p>{marker}</p></body></html>"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    nonce_dir = tmp_path / "nonces"  # box-local, OUTSIDE the evidence tree
    monkeypatch.setenv(ghl_verify.NONCE_DIR_ENV, str(nonce_dir))
    monkeypatch.setattr(ghl_verify, "_live_browser_session",
                        lambda slug="": contextlib.nullcontext())
    run = tmp_path / "run"
    run.mkdir()
    return run, nonce_dir


def _stub_render(dom_by_step):
    """render_check stand-in: writes real artifacts, returns a render_check dict."""
    calls = []

    def render_check(url, marker, *, run_dir, step, timeout=45, **_kw):
        calls.append(step)
        spec = dom_by_step(step) if callable(dom_by_step) else dom_by_step
        dom, errors = spec
        d = os.path.join(run_dir, "render")
        os.makedirs(d, exist_ok=True)
        paths = {k: os.path.join(d, f"{step}.{k}") for k in ("dom.html", "png", "console.json")}
        with open(paths["dom.html"], "w") as f:
            f.write(dom)
        with open(paths["png"], "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        with open(paths["console.json"], "w") as f:
            f.write("[]")
        sha = ghl_verify._sha256_file
        return {
            "ok": not errors and marker in dom, "http": 200,
            "marker_in_rendered_dom": marker in dom, "render_errors": errors,
            "dom_path": paths["dom.html"], "png_path": paths["png"],
            "console_path": paths["console.json"],
            "dom_sha256": sha(paths["dom.html"]), "png_sha256": sha(paths["png"]),
            "console_sha256": sha(paths["console.json"]),
            "dom_bytes": len(dom), "visible_text_len": 500,
        }

    render_check.calls = calls
    return render_check


def _genuine(run, monkeypatch, marker=MARKER, pages=None):
    monkeypatch.setattr(ghl_builder, "render_check",
                        _stub_render((_dom(marker, COPY), [])))
    pages = pages or [{"step": "home", "page_id": "p1",
                       "preview_url": "https://example.invalid/p1", "marker": marker,
                       "copy_fidelity": False}]
    out = ghl_verify.verify_all(str(run), pages, live=True, run_id="r1")
    assert out["summary"]["overall_pass"] is True
    return out


def _forge(run, *, with_manifest=False, with_artifacts=False):
    """What an agent with no working browser would write by hand."""
    (run / "logs").mkdir()
    (run / "scorecard").mkdir()
    raw = [{"step": "home", "PASS": True, "http": 200, "render_errors": [],
            "marker": MARKER, "page_id": "p1"}]
    raw_path = run / ghl_verify.RAW_REL
    raw_path.write_text(json.dumps(raw))
    summary = ghl_verify.derive_summary(
        raw, run_id="r1", run_nonce=str(uuid.uuid4()), trust="LIVE")
    summary["raw_sha256"] = ghl_verify._sha256_file(str(raw_path))
    (run / ghl_verify.SUMMARY_REL).write_text(json.dumps(summary))
    if with_manifest:
        entry = {}
        if with_artifacts:
            (run / "render").mkdir()
            for key, name, data in (("dom", "h.dom.html", _dom(MARKER, COPY).encode()),
                                    ("png", "h.png", b"png-bytes"),
                                    ("console", "h.console.json", b"[]")):
                p = run / "render" / name
                p.write_bytes(data)
                entry[f"{key}_path"] = str(p)
                entry[f"{key}_sha256"] = ghl_verify._sha256_file(str(p))
        (run / ghl_verify.RENDER_MANIFEST_REL).write_text(json.dumps({"home": entry}))
    return summary


# ── S06-04: a hand-forged evidence tree no longer passes ────────────────────


def test_genuine_tree_passes_the_gate(env, monkeypatch):
    run, _ = env
    _genuine(run, monkeypatch)
    assert ghl_gate.require_pass(str(run)) == 0


def test_forged_tree_without_manifest_fails(env):
    run, _ = env
    _forge(run)
    assert ghl_gate.require_pass(str(run)) != 0


def test_forged_tree_with_fabricated_manifest_and_artifacts_fails(env):
    run, nonce_dir = env
    _forge(run, with_manifest=True, with_artifacts=True)
    assert not nonce_dir.exists()  # nothing but verify_all ever wrote a nonce
    assert ghl_gate.require_pass(str(run)) != 0


def test_forged_nonce_file_inside_the_evidence_tree_fails(env, monkeypatch):
    run, _ = env
    summary = _forge(run, with_manifest=True, with_artifacts=True)
    inside = run / "nonces"
    monkeypatch.setenv(ghl_verify.NONCE_DIR_ENV, str(inside))
    inside.mkdir(mode=0o700)
    f = inside / f"{summary['run_nonce']}.nonce"
    f.write_text(ghl_verify._nonce_binding(
        str(run / ghl_verify.RAW_REL), str(run / ghl_verify.RENDER_MANIFEST_REL)))
    os.chmod(f, 0o600)
    assert ghl_gate.require_pass(str(run)) != 0


def test_nonce_file_with_loose_mode_fails(env, monkeypatch):
    run, nonce_dir = env
    out = _genuine(run, monkeypatch)
    os.chmod(nonce_dir / f"{out['run_nonce']}.nonce", 0o644)
    assert ghl_gate.require_pass(str(run)) != 0


@pytest.mark.parametrize("victim", ["dom_path", "png_path", "console_path"])
def test_tampered_or_deleted_artifact_fails(env, monkeypatch, victim):
    run, _ = env
    out = _genuine(run, monkeypatch)
    path = out["raw"][0][victim]
    with open(path, "ab") as f:
        f.write(b"tamper")
    assert ghl_gate.require_pass(str(run)) != 0
    os.remove(path)
    assert ghl_gate.require_pass(str(run)) != 0


def test_empty_artifact_or_dom_without_marker_fails(env, monkeypatch):
    run, _ = env
    out = _genuine(run, monkeypatch)
    dom = out["raw"][0]["dom_path"]
    # Rewrite the DOM so it has no marker, then re-bind EVERYTHING a forger
    # could reach inside the tree (manifest + raw + summary hashes). The nonce
    # file outside the tree still pins the old bytes.
    with open(dom, "w") as f:
        f.write("<html><body>nothing rendered</body></html>")
    man_path = run / ghl_verify.RENDER_MANIFEST_REL
    man = json.loads(man_path.read_text())
    man["home"]["dom_sha256"] = ghl_verify._sha256_file(dom)
    man_path.write_text(json.dumps(man))
    assert ghl_gate.require_pass(str(run)) != 0


def test_marker_check_alone_rejects_dom_without_marker(env):
    run, _ = env
    d = run / "d.html"
    d.write_text("<html><body>no marker</body></html>")
    p, g, c = run / "p.png", run / "c.json", run / "c2.json"
    p.write_bytes(b"png")
    c.write_text("[]")
    sha = ghl_verify._sha256_file
    manifest = {"home": {"dom_path": str(d), "dom_sha256": sha(str(d)),
                         "png_path": str(p), "png_sha256": sha(str(p)),
                         "console_path": str(c), "console_sha256": sha(str(c))}}
    with pytest.raises(ghl_verify.VerifyContradiction, match="marker"):
        ghl_verify.assert_artifacts_rendered(
            [{"step": "home", "PASS": True, "marker": MARKER}], manifest)


def test_nonce_dir_inside_evidence_tree_is_refused(env, monkeypatch):
    run, _ = env
    monkeypatch.setenv(ghl_verify.NONCE_DIR_ENV, str(run / "inside"))
    monkeypatch.setattr(ghl_builder, "render_check", _stub_render((_dom(MARKER, COPY), [])))
    with pytest.raises(ghl_verify.VerifyContradiction):
        ghl_verify.verify_all(str(run), [{"step": "home", "page_id": "p1",
                                          "preview_url": "https://example.invalid/p1",
                                          "marker": MARKER, "copy_fidelity": False}],
                              live=True)


# ── S06-05: the HTML repair re-render keeps the copy-fidelity gate ───────────


def _repair_steps(monkeypatch, repaired_dom):
    """Primary render has a render error (so the repair seam fires); the repair
    re-render comes back clean with ``repaired_dom``."""
    monkeypatch.setattr(ghl_verify, "select_html_repair_model",
                        lambda *a, **k: {"model": "html-role-model"})

    def spec(step):
        if step.endswith("-repair"):
            return repaired_dom, []
        return _dom(MARKER, "x"), ["pageerror: first render failed"]

    monkeypatch.setattr(ghl_builder, "render_check", _stub_render(spec))


def _page(**extra):
    return {"step": "home", "page_id": "p1", "preview_url": "https://example.invalid/p1",
            "marker": MARKER, **extra}


@pytest.mark.parametrize("branch", ["explicit_tokens", "run_dir_copy_fallback"])
def test_repair_with_wrong_copy_fails(env, monkeypatch, branch):
    run, _ = env
    _repair_steps(monkeypatch, _dom(MARKER, STALE))  # clean render, WRONG copy
    if branch == "explicit_tokens":
        page = _page(copy_tokens=[COPY])
    else:
        (run / "routing").mkdir()
        (run / "routing" / "copy.md").write_text(f"# {COPY}\n")
        page = _page()
    rec = ghl_verify.verify_page(page, run_dir=str(run), live=True)
    assert rec["PASS"] is False
    assert any(e.startswith("copy_not_rendered") for e in rec["render_errors"])


@pytest.mark.parametrize("branch", ["explicit_tokens", "run_dir_copy_fallback"])
def test_repair_with_right_copy_still_passes(env, monkeypatch, branch):
    run, _ = env
    _repair_steps(monkeypatch, _dom(MARKER, COPY))
    if branch == "explicit_tokens":
        page = _page(copy_tokens=[COPY])
    else:
        (run / "routing").mkdir()
        (run / "routing" / "copy.md").write_text(f"# {COPY}\n")
        page = _page()
    assert ghl_verify.verify_page(page, run_dir=str(run), live=True)["PASS"] is True


# ── S06-22: one root data-attribute marker, shared with Skill 71 ─────────────

PAGE_RESULT = {
    "launch_id": "L1", "page_id": "P1", "revision": 1,
    "input_hash": "ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12",
}


def _validate_install():
    spec = importlib.util.spec_from_file_location("validate_install_under_test", _VALIDATE_INSTALL)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(_VALIDATE_INSTALL)))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def test_both_sides_read_the_same_root_attribute():
    vi = _validate_install()
    marker = ghl_verify.marker_from_page_result(PAGE_RESULT)
    assert marker.startswith(ghl_verify.ROOT_MARKER_ATTR + '="')
    assert vi.ROOT_MARKER_ATTR == ghl_verify.ROOT_MARKER_ATTR
    found = vi.extract_build_marker(f'<html lang="en" {marker}><body>x</body></html>')
    assert found and found["run_id"] == "L1" and found["page"] == "P1"
    # a comment is NOT the contract: render_check strips it before looking.
    assert ghl_builder.strip_non_visible_html(f"<!-- {marker} -->").find(marker) == -1
    assert ghl_builder.strip_non_visible_html(f"<html {marker}>").find(marker) != -1


def test_verify_page_passes_with_marker_taken_from_the_page_result(env, monkeypatch):
    run, _ = env
    marker = ghl_verify.marker_from_page_result(PAGE_RESULT)
    dom = f"<html {marker}><body><h1>{COPY}</h1></body></html>"
    monkeypatch.setattr(ghl_builder, "render_check", _stub_render((dom, [])))
    page = {"step": "home", "page_id": "P1", "preview_url": "https://example.invalid/p1",
            "page_result": PAGE_RESULT, "copy_fidelity": False}  # NO hand-typed marker
    out = ghl_verify.verify_all(str(run), [page], live=True)
    assert out["raw"][0]["marker"] == marker and out["raw"][0]["PASS"] is True
    assert ghl_gate.require_pass(str(run)) == 0


def test_page_result_missing_identity_yields_no_marker():
    assert ghl_verify.marker_from_page_result({"launch_id": "L1"}) == ""
    assert ghl_verify.marker_from_page_result(None) == ""


# ── S06-11 (verify half): every rendered <img> src must be manifested ────────

GHL_MEDIA = "https://storage.googleapis.com/msgsndr/loc/media/hero.png"


def _verify_with_img(env, monkeypatch, src, **extra):
    run, _ = env
    dom = f'<p>{MARKER}</p><img src="{src}">'
    monkeypatch.setattr(ghl_builder, "render_check", _stub_render((dom, [])))
    page = {"step": "s", "page_id": "p1", "preview_url": "https://x/preview/p1",
            "marker": MARKER, **extra}
    return ghl_verify.verify_page(page, run_dir=str(run), live=True)


def test_relative_img_src_fails_verify(env, monkeypatch):
    rec = _verify_with_img(env, monkeypatch, "images/hero.png")
    assert rec["PASS"] is False
    assert any(e.startswith("unmanifested_image") and "images/hero.png" in e
               for e in rec["render_errors"])


def test_ghl_media_img_src_is_accepted(env, monkeypatch):
    rec = _verify_with_img(env, monkeypatch, GHL_MEDIA)
    assert not any(e.startswith("unmanifested_image") for e in rec["render_errors"])


def test_website_surface_skips_unmanifested_image_gate(env, monkeypatch):
    rec = _verify_with_img(env, monkeypatch, "images/hero.png", surface="website")
    assert not any(e.startswith("unmanifested_image") for e in rec["render_errors"])
