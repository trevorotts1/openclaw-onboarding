"""test_pd_runfacts_317_missing_instrument.py -- PD-317 acceptance (A1).

PD-317: a sealed-record check FAILS when its instrument is missing.

The unit owns exactly TWO branches in ``presentation_job/runfacts.py``:

  A1-notes-missing  the notes-pane renderer (build_deck) is unreachable -> the
                    sealed ``notes_pane_result`` carries
                    "AF-EMPTY-NOTES-PANE: could not be measured" -> FAIL naming it.
  A1-notes-crash    build_deck._chk_notes_pane raises -> the same named FAIL.
  A1-notes-ok       control: a healthy renderer returning "" still PASSes, so
                    the two tests above fail for the right reason.
  A1-pypdf-missing  pypdf is unimportable in a production context -> FAIL naming
                    pypdf, NOT the old silent "degraded ... (pass)".
  A1-pypdf-rule     the same missing pypdf, with the PD-201 test rule on
                    (PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1) -> PASS with the
                    note, which is the one exemption the spec grants.

No network, no credentials. Stdlib + pytest/tmp_path only.
"""
import json
import pathlib
import sys
import types

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
for _p in (SCRIPTS, SCRIPTS / "presentation_job"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from presentation_job import runfacts as rf  # noqa: E402

UNMEASURED = "AF-EMPTY-NOTES-PANE: could not be measured"

def _notes_run(tmp_path: pathlib.Path) -> pathlib.Path:
    rd = tmp_path / "run"
    ck = rd / "working" / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "notes_sync.json").write_text(json.dumps({
        "status": "synced",
        "slides_total": 3,
        "slides_with_notes": 3,
        "bundle_pptx": str(rd / "working" / "deliverables" / "BUNDLE.pptx"),
    }), encoding="utf-8")
    return rd

def _notes_verdict(rd: pathlib.Path):
    fact = rf._notes_sync_fact(rd)
    return fact, rf.verify_notes_sync(types.SimpleNamespace(notes_sync=fact))

def test_notes_pane_missing_renderer_fails_naming_it(tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "_import_build_deck", lambda: None)
    fact, (verdict, reason) = _notes_verdict(_notes_run(tmp_path))
    assert fact.value.notes_pane_result == UNMEASURED
    assert verdict is rf.Verdict.FAIL
    assert UNMEASURED in reason

def test_notes_pane_crashing_renderer_fails_naming_it(tmp_path, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(rf, "_import_build_deck",
                        lambda: types.SimpleNamespace(_chk_notes_pane=_boom))
    fact, (verdict, reason) = _notes_verdict(_notes_run(tmp_path))
    assert fact.value.notes_pane_result == UNMEASURED
    assert verdict is rf.Verdict.FAIL
    assert UNMEASURED in reason

def test_notes_pane_healthy_renderer_still_passes(tmp_path, monkeypatch):
    """Control: the new branch must not turn a real clean scan into a failure."""
    monkeypatch.setattr(rf, "_import_build_deck",
                        lambda: types.SimpleNamespace(_chk_notes_pane=lambda *_a, **_k: ""))
    _fact, (verdict, _reason) = _notes_verdict(_notes_run(tmp_path))
    assert verdict is rf.Verdict.PASS

def _workbook_run(tmp_path: pathlib.Path) -> pathlib.Path:
    rd = tmp_path / "run"
    dl = rd / "working" / "deliverables"
    dl.mkdir(parents=True)
    (dl / "A-WORKBOOK.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 4096)
    (dl / "A-WORKBOOK-FILLABLE.pdf").write_bytes(b"%PDF-1.4\n" + b"y" * 4096)
    return rd

def _production_context(monkeypatch):
    """No test-rule signal at all: no env var, no CI marker, no marker file."""
    for name in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(name, raising=False)

def _workbook_verdict(rd: pathlib.Path):
    fact = rf._workbook_fact(rd)
    return fact, rf.verify_workbook(types.SimpleNamespace(workbook=fact))

def test_pypdf_missing_fails_naming_pypdf(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)  # `from pypdf import ...` -> ImportError
    _production_context(monkeypatch)
    fact, (verdict, reason) = _workbook_verdict(_workbook_run(tmp_path))
    assert fact.value.pypdf_available is False
    assert fact.value.degraded_allowed is False
    assert verdict is rf.Verdict.FAIL
    assert "pypdf" in reason
    # The pre-PD-317 read passed here with this exact note. It must not any more.
    assert "NOTE: pypdf not importable" not in reason

def test_pypdf_missing_passes_only_under_the_pd201_rule(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)
    _production_context(monkeypatch)
    monkeypatch.setenv("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "1")
    fact, (verdict, reason) = _workbook_verdict(_workbook_run(tmp_path))
    assert fact.value.pypdf_available is False
    assert fact.value.degraded_allowed is True
    assert verdict is rf.Verdict.PASS
    assert "PD-201" in reason
