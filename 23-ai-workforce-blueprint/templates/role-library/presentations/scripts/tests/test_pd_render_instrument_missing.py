"""PD-218a — renderer checks fail when their instrument is missing.

Acceptance row A1: each changed branch has one test that FORCES THE INSTRUMENT
AWAY (module gone, read raising, ledger absent, file date unreadable) and sees a
failure that NAMES the missing instrument. Every failure test is paired with the
control that proves the same fixture still passes when the instrument is present,
so a check that could never pass — or could never fail — is caught here.

Branches under test:
  1. _chk_citation_validated  — citation_validator module missing
  2. _chk_citation_validated  — citation inventory read raises
  3. _chk_citation_validated  — research brief exists, FIX 19 retrieval ledger absent
  4. check_speech_qc_teeth    — pitch_engines_check module missing
  5. check_speech_qc_teeth    — pitch_engines_check.run raises
  6. check_image_qc_present   — image-QC report file date unreadable

No network, no credentials. Stdlib + pytest/tmp_path only.
"""

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _production_context(monkeypatch):
    """Strip every PD-201 test-rule signal so _degraded_allowed() sees a real run."""
    for var in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(var, raising=False)


class _StubValidator:
    """Minimal stand-in for presentation_job.citation_validator."""

    class _rw:
        LEDGER_NAME = "retrieval_ledger.jsonl"

    def __init__(self, citations=None, raises=None):
        self._citations = (citations if citations is not None
                           else [{"url": "https://example.com/a", "anchor": "a"}])
        self._raises = raises

    def citation_validation_enabled(self):
        return True

    def load_citation_inventory(self, run_dir):
        if self._raises is not None:
            raise self._raises
        return {"citations": list(self._citations)}

    def check_citations(self, run_dir):
        return ""


def _run(tmp_path):
    rd = tmp_path / "run"
    (rd / "working").mkdir(parents=True)
    return rd


# ---------------------------------------------------------------------------
# 1. citation_validator module missing
# ---------------------------------------------------------------------------

def test_citation_validator_missing_fails_naming_it(tmp_path, monkeypatch):
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    monkeypatch.setattr(bd, "_citation_validator", None)
    reason = bd._chk_citation_validated(rd)
    assert reason.startswith("AF-RESEARCH-UNCITED:"), reason
    assert "citation_validator" in reason, reason
    assert "MISSING" in reason, reason


def test_citation_validator_missing_defers_only_under_pd201_test_rule(
        tmp_path, monkeypatch):
    """Control: the PD-201 test rule is the SINGLE remaining defer path."""
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    (rd / "working" / "checkpoints").mkdir(parents=True)
    (rd / "working" / "checkpoints" / ".test-context").write_text("{}")
    monkeypatch.setattr(bd, "_citation_validator", None)
    assert bd._chk_citation_validated(rd) == ""


# ---------------------------------------------------------------------------
# 2. citation inventory read raises
# ---------------------------------------------------------------------------

def test_citation_inventory_read_failure_fails_naming_it(tmp_path, monkeypatch):
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    monkeypatch.setattr(bd, "_citation_validator",
                        _StubValidator(raises=OSError("ledger unreadable")))
    reason = bd._chk_citation_validated(rd)
    assert "citation inventory could not be read" in reason, reason
    assert "OSError" in reason and "ledger unreadable" in reason, reason


def test_citation_inventory_read_control_passes_when_readable(tmp_path, monkeypatch):
    """Control: same stub, read does not raise, ledger present -> pass."""
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "research" / "retrieval_ledger.jsonl").write_text("")
    monkeypatch.setattr(bd, "_citation_validator", _StubValidator())
    assert bd._chk_citation_validated(rd) == ""


# ---------------------------------------------------------------------------
# 3. research brief exists, FIX 19 retrieval ledger absent
# ---------------------------------------------------------------------------

def test_brief_without_retrieval_ledger_fails_naming_ledger(tmp_path, monkeypatch):
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "research" / "brief-01.md").write_text(
        "Sources: https://example.com/a")
    monkeypatch.setattr(bd, "_citation_validator", _StubValidator())
    reason = bd._chk_citation_validated(rd)
    assert "retrieval ledger" in reason, reason
    assert "brief-01.md" in reason, reason
    assert "retrieval_ledger.jsonl" in reason, reason


def test_no_brief_no_ledger_still_defers(tmp_path, monkeypatch):
    """Control: no research brief at all -> the defer stays (absence is owned by
    the research-brief gate). Same stub, no brief file."""
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    monkeypatch.setattr(bd, "_citation_validator", _StubValidator())
    assert bd._chk_citation_validated(rd) == ""


def test_brief_with_ledger_passes(tmp_path, monkeypatch):
    """Control: the SAME brief fixture passes once the ledger exists."""
    _production_context(monkeypatch)
    rd = _run(tmp_path)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "research" / "brief-01.md").write_text(
        "Sources: https://example.com/a")
    (rd / "working" / "research" / "retrieval_ledger.jsonl").write_text("")
    monkeypatch.setattr(bd, "_citation_validator", _StubValidator())
    assert bd._chk_citation_validated(rd) == ""


# ---------------------------------------------------------------------------
# 4 + 5. speech QC teeth: hook engine missing / crashing
# ---------------------------------------------------------------------------

def _speech_run(tmp_path, words=3600, target_minutes=30):
    rd = _run(tmp_path)
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "delivery").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / "working" / "delivery" / "PRESENTERS-SPEECH.md").write_text(
        " ".join(["word"] * words))
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"target_talk_minutes": target_minutes}))
    return rd


def test_speech_qc_missing_hook_module_is_a_named_problem(tmp_path, monkeypatch):
    rd = _speech_run(tmp_path)
    monkeypatch.setattr(bd, "_import_pitch_engines_check", lambda: None)
    reason = bd.check_speech_qc_teeth(rd)
    assert reason.startswith("AF-SPEECH-QC:"), reason
    assert "pitch_engines_check" in reason, reason
    assert "MISSING" in reason, reason


class _CrashingPitchEngines:
    @staticmethod
    def run(run_dir, phase=None):
        raise RuntimeError("engine blew up")


def test_speech_qc_crashing_hook_module_is_a_named_problem(tmp_path, monkeypatch):
    rd = _speech_run(tmp_path)
    monkeypatch.setattr(bd, "_import_pitch_engines_check",
                        lambda: _CrashingPitchEngines)
    reason = bd.check_speech_qc_teeth(rd)
    assert reason.startswith("AF-SPEECH-QC:"), reason
    assert "CRASHED" in reason, reason
    assert "RuntimeError" in reason and "engine blew up" in reason, reason


def test_speech_qc_control_passes_with_real_hook_module(tmp_path, monkeypatch):
    """Control: the same speech fixture passes when the real engine is present."""
    _production_context(monkeypatch)
    rc = _speech_run(tmp_path)
    assert bd._import_pitch_engines_check() is not None
    assert bd.check_speech_qc_teeth(rc) == ""


# ---------------------------------------------------------------------------
# 6. image QC: unreadable file date
# ---------------------------------------------------------------------------

def _image_run(tmp_path):
    rd = _run(tmp_path)
    (rd / "renders").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / "renders" / "slide-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (rd / "working" / "qc" / "image_qc_report.json").write_text(json.dumps(
        {"slides": [{"slide": 1, "verdict": "PASS"}]}))
    return rd


def test_image_qc_unreadable_file_date_fails_naming_it(tmp_path, monkeypatch):
    rd = _image_run(tmp_path)
    # Control first: readable dates pass on this exact fixture.
    assert bd.check_image_qc_present(rd) == ""

    report = rd / "working" / "qc" / "image_qc_report.json"
    real_stat = pathlib.Path.stat
    calls = {"n": 0}

    def fake_stat(self, *args, **kwargs):
        # Path.exists() on this interpreter resolves through os.stat, so the first
        # Path.stat() the function makes IS its date read — fail it while the file
        # still exists, which is exactly the unreadable-date case.
        if self == report:
            calls["n"] += 1
            if calls["n"] >= 1:
                raise OSError(5, "Input/output error")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", fake_stat)
    reason = bd.check_image_qc_present(rd)
    assert reason.startswith("AF-IMAGE-QC-RAN:"), reason
    assert "file date could not be read" in reason, reason
    assert "OSError" in reason, reason
    assert "image_qc_report.json" in reason, reason


def test_image_qc_unreadable_render_date_names_the_render(tmp_path, monkeypatch):
    """PD-218a: the failure must name the file whose date failed — here the RENDER,
    not the report. A message that always blames the report would send the operator
    to re-run the Image QC Specialist when the render batch is what is unreadable."""
    rd = _image_run(tmp_path)
    assert bd.check_image_qc_present(rd) == ""  # control: same fixture passes

    png = rd / "renders" / "slide-1.png"
    real_stat = pathlib.Path.stat

    def fake_stat(self, *args, **kwargs):
        if self == png:
            raise OSError(5, "Input/output error")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", fake_stat)
    reason = bd.check_image_qc_present(rd)
    assert reason.startswith("AF-IMAGE-QC-RAN:"), reason
    assert "slide-1.png" in reason, reason
    assert "image_qc_report.json" not in reason, reason
