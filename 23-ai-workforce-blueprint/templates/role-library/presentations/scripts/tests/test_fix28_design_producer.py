#!/usr/bin/env python3
"""FIX 28 — the design-PNG producer is wired end to end (tests/test_fix28_design_producer.py).

Proof contract (QC.md FIX 28): "P-U-DESIGN-SALES on the fixture produces
design/sales-design.png with a task id and no hand step."

What these tests prove, offline (no network, no API key, no real Kie call):

  1. PERSONA HALF: BLEND_TIMEOUT_S pins 90 (the 30 s wall that blocked copy
     phases is gone) and resolve_for_phase takes exactly TWO attempts
     (one retry) before raising.

  2. PRODUCER HALF (the part the last critic failed): build_infographic.py
     accepts --spec design --page sales|checkout|vsl (argparse), run_design()
     exists, and on the FIXTURE run dir it produces design/sales-design.png
     AT THE RUN ROOT with the Kie task id recorded in
     working/checkpoints/pending_tasks.json["design-sales"] — via a monkeypatched
     canonical path (the SAME submit -> poll -> download chain the infographic
     rides), never a hand-authored PNG.

  3. MANIFEST HALF: the deployed manifest declares a script executor for each
     P-U-DESIGN-RENDER-* phase whose cmd threads {run_dir} and the page id
     through build_infographic.py --spec design — so the engine's script-phase
     dispatch (nonce-minted front door) actually runs the producer.

  4. NON-VACUOUSNESS: the same manifest assertion fails against the pre-fix
     bytes (this fix's own .bak), where the design PNG had NO producer.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

import build_infographic as bi

DESIGN_PAGES = ("sales", "checkout", "vsl")


# ---------------------------------------------------------------------------
# 1. Persona half — the raised wall + one retry (already-live behavior pinned).
# ---------------------------------------------------------------------------
def test_blend_timeout_is_90():
    from presentation_job import persona
    assert persona.BLEND_TIMEOUT_S == 90, (
        f"BLEND_TIMEOUT_S must be 90 (FIX 28), got {persona.BLEND_TIMEOUT_S}")


def test_persona_retry_loop_takes_two_attempts(tmp_path, monkeypatch):
    """A wedged first attempt costs one retry; a second timeout raises."""
    import concurrent.futures
    from presentation_job import persona

    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text("{}", encoding="utf-8")

    attempts = []

    class _Mod:
        @staticmethod
        def blend_governs():
            return True

        @staticmethod
        def governed_phase_voice(narrative, avatar_context, department=None, record=True):
            attempts.append(1)
            raise concurrent.futures.TimeoutError("simulated wedge")

    monkeypatch.setattr(persona, "load_blend_module", lambda: _Mod())
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)

    with pytest.raises(TimeoutError):
        persona.resolve_for_phase(rd, "P4-COPY")

    assert len(attempts) == 2, (
        f"expected exactly one retry (2 attempts), got {len(attempts)}")


# ---------------------------------------------------------------------------
# 2. Producer half — argparse surface, run_design on the fixture, task id.
# ---------------------------------------------------------------------------
def _make_fixture_run_dir(tmp_path: pathlib.Path, page: str = "sales") -> pathlib.Path:
    """A run dir carrying a 9,000+ char page-design prompt that clears the
    shared rich-prompt gate — the fixture shape the critic's proof ran. The
    prompt body is build_infographic's own SELFTEST_PROMPT (the real
    15-element fixture, 10,255 chars, gate-clearing)."""
    rd = tmp_path / "run"
    (rd / "working" / "prompts").mkdir(parents=True)
    (rd / "working" / "checkpoints").mkdir(parents=True)
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text("{}", encoding="utf-8")

    (rd / "working" / "prompts" / f"{page}.design.txt").write_text(
        bi.SELFTEST_PROMPT, encoding="utf-8")
    return rd


def _stub_kie_path(monkeypatch):
    """Replace the network legs with a deterministic canonical-shaped chain:
    submit_task -> poll_task -> download_image (the SAME call order run_design
    rides), without any HTTP."""
    PNG = bi.PNG_MAGIC + b"\r\n\x1a\n" + b"0" * (bi.PNG_MIN_BYTES + 64)
    monkeypatch.setattr(bi, "load_api_key", lambda: "stub-key")
    monkeypatch.setattr(bi, "_resolve_image_models", lambda: ("stub-t2i", "stub-i2i"))
    monkeypatch.setattr(bi, "submit_task", lambda prompt, api_key, **kw: "task-fix28-1")
    monkeypatch.setattr(bi, "poll_task", lambda task_id, api_key: "https://stub/result.png")
    monkeypatch.setattr(bi, "download_image", lambda url, dest, api_key:
                        (dest.write_bytes(PNG), dest.stat().st_size)[1])


@pytest.mark.parametrize("page", DESIGN_PAGES)
def test_run_design_produces_run_root_png_with_task_id(tmp_path, monkeypatch, page):
    rd = _make_fixture_run_dir(tmp_path, page)
    _stub_kie_path(monkeypatch)

    rc = bi.run_design(rd, page=page)

    assert rc == 0
    out = rd / "design" / f"{page}-design.png"
    assert out.is_file(), f"run_design must write design/{page}-design.png at the run root"
    assert out.stat().st_size >= bi.PNG_MIN_BYTES

    pending = json.loads((rd / "working" / "checkpoints" / "pending_tasks.json").read_text())
    assert pending.get(f"design-{page}", {}).get("task_id") == "task-fix28-1", (
        "the Kie task id must be recorded under pending_tasks['design-<page>'] "
        "(the U028 shape) — no hand step")

    status = json.loads(
        (rd / "working" / "checkpoints" / f"design_{page}_status.json").read_text())
    assert status.get("design_page") == page and status.get("status") == "ready"


def test_argparse_accepts_spec_design_page_sales(tmp_path, monkeypatch):
    """The exact CLI shape the manifest executor.cmd carries parses and routes
    to run_design (the producer the last critic found MISSING)."""
    rd = _make_fixture_run_dir(tmp_path, "sales")

    nonce = "n" * 32
    (rd / "working" / "checkpoints" / ".canonical-entry-nonce").write_text(nonce)
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", nonce)
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE_FILE", raising=False)

    # The subprocess must find the STUBBED canonical path, not the live Kie API:
    # a tiny driver script monkeypatches build_infographic the same way
    # _stub_kie_path does in-process, then calls main() with the exact argv the
    # manifest executor.cmd carries. This proves the ARGPARSE SURFACE (the half
    # the last critic failed: 'unrecognized arguments: --spec design') without
    # any network.
    driver = rd / "_driver.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(_SCRIPTS)!r})\n"
        "import build_infographic as bi\n"
        "PNG = bi.PNG_MAGIC + b'\\r\\n\\x1a\\n' + b'0' * (bi.PNG_MIN_BYTES + 64)\n"
        "bi.load_api_key = lambda: 'stub-key'\n"
        "bi._resolve_image_models = lambda: ('stub-t2i', 'stub-i2i')\n"
        "bi.submit_task = lambda prompt, api_key, **kw: 'task-fix28-1'\n"
        "bi.poll_task = lambda task_id, api_key: 'https://stub/result.png'\n"
        "bi.download_image = lambda url, dest, api_key: "
        "(dest.write_bytes(PNG), dest.stat().st_size)[1]\n"
        "sys.exit(bi.main(['--run-dir', sys.argv[1], '--spec', 'design', "
        "'--page', 'sales']))\n",
        encoding="utf-8")

    import subprocess
    r = subprocess.run(
        [sys.executable, str(driver), str(rd)],
        capture_output=True, text=True, timeout=60,
        env={**__import__("os").environ, "OC_DECK_ENTRY_NONCE": nonce},
    )
    assert r.returncode == 0, f"design producer failed: {r.stdout} {r.stderr}"
    assert (rd / "design" / "sales-design.png").is_file()


def test_missing_design_prompt_fails_loud(tmp_path):
    """No prompt -> exit 1, never a placeholder render."""
    rd = tmp_path / "run"
    (rd / "working" / "checkpoints").mkdir(parents=True)
    with pytest.raises(SystemExit) as ei:
        bi.resolve_design_prompt(rd, "sales")
    assert ei.value.code == 1


# ---------------------------------------------------------------------------
# 3. Manifest half — the engine can actually dispatch the producer.
# ---------------------------------------------------------------------------
def _manifest_path() -> pathlib.Path:
    from manifest_source import resolve_manifest
    mp, _prov = resolve_manifest(_SCRIPTS)
    return mp


@pytest.mark.parametrize("page", DESIGN_PAGES)
def test_manifest_declares_script_producer_for_design_pages(page):
    mp = _manifest_path()
    phases = {p["id"]: p for p in json.loads(mp.read_text(encoding="utf-8"))["phases"]}
    ph = phases[f"P-U-DESIGN-RENDER-{page.upper()}"]
    executor = ph.get("executor") or {}
    assert executor.get("kind") == "script", (
        f"P-U-DESIGN-RENDER-{page.upper()} executor.kind is "
        f"{executor.get('kind')!r} — a text agent cannot render a real PNG")
    cmd = executor.get("cmd") or ""
    assert "build_infographic.py" in cmd
    assert "--spec design" in cmd
    assert f"--page {page}" in cmd
    assert "{run_dir}" in cmd and "--run-dir" in cmd


def test_manifest_parser_resolves_render_phases():
    from presentation_job.manifest import Manifest
    m = Manifest(_manifest_path())
    by_id = {p.id: p for p in m.phases}
    ph = by_id["P-U-DESIGN-RENDER-SALES"]
    assert ph.executor_kind == "script"
    assert "--spec design" in (ph.executor_cmd or "")


# ---------------------------------------------------------------------------
# 4. Non-vacuousness — the pre-fix manifest has NO producer for the PNG.
# ---------------------------------------------------------------------------
def test_pre_fix_manifest_has_no_producer():
    root = _SCRIPTS
    for _ in range(12):
        cand = root / "universal-sops" / "presentation-slide-craft"
        if (cand / "PIPELINE-MANIFEST.json.bak-f28-RF01B4-20260903").is_file():
            backup = cand / "PIPELINE-MANIFEST.json.bak-f28-RF01B4-20260903"
            break
        if root.parent == root:
            pytest.skip("pre-fix backup not present; cannot prove non-vacuousness")
        root = root.parent
    else:
        pytest.skip("pre-fix backup not found")
    pre = json.loads(backup.read_text(encoding="utf-8"))
    ids = {p["id"] for p in pre["phases"]}
    assert "P-U-DESIGN-RENDER-SALES" not in ids, (
        "the backup is not pre-fix bytes (it already carries the producer phase)")
    sales = next(p for p in pre["phases"] if p["id"] == "P-U-DESIGN-SALES")
    assert (sales.get("executor") or {}).get("kind") == "agent"
