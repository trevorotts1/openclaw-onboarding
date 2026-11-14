"""PD-311 — the two script guards allow by CONTENT, not by NAME (plus PD-317).

Before this unit: a run-dir file whose basename matched a shipped script was
skipped before its bytes were ever read, so a hand-rolled `qc_check.py` or a
copied-then-edited `build_deck.py` was invisible to both guards, and only *.py
was scanned at all.

After: a run-dir script is sanctioned only when its sha256 equals the sha256 of
the shipped script of the same name (shared helper
canonical_render_guard.iter_governed_script_files), and the scan covers
.py/.sh/.js/.mjs/.ts. PD-317: a missing instrument (qc_generator_guard, or
build_deck for the Fix-2 checks) is a named failure, not a silent pass, unless
phase_verifiers._degraded_allowed(run_dir) permits the degrade.

Acceptance (PD-311 probe as tests):
  * qc_check.py with foreign content -> flagged
  * make.sh -> flagged
  * a true copy of a shipped script -> not flagged
"""

import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import canonical_render_guard as crg  # noqa: E402
import phase_verifiers  # noqa: E402
import qc_generator_guard as qcg  # noqa: E402

SHIPPED_QC_CHECK = SCRIPTS / "qc_check.py"

# Foreign content that trips the render guard's own detection: a locally fabricated
# 2048x1152 slide canvas.
FOREIGN_RENDER = (
    "from PIL import Image\n"
    "im = Image.new('RGB', (2048, 1152))\n"
)

# Foreign content that trips the QC-generator guard: a hand-rolled report writer.
FOREIGN_QC = (
    "import json\n"
    "json.dump({}, open('qc_report.json', 'w'))\n"
)


# ---------------------------------------------------------------------------
# PD-311 — content, not name.
# ---------------------------------------------------------------------------
def test_shipped_script_exists_as_control():
    """Control: the basename used below really is a shipped script, so the old
    name allow-list would have skipped it."""
    assert SHIPPED_QC_CHECK.is_file(), SHIPPED_QC_CHECK


def test_shipped_name_with_foreign_content_is_flagged(tmp_path):
    """qc_check.py is a shipped basename; a foreign body under that name must be
    flagged instead of allow-listed."""
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True)
    (run / "working" / "qc_check.py").write_text(FOREIGN_RENDER)

    findings = crg.scan_run_dir(run)
    assert findings, "a foreign-content qc_check.py must not be allow-listed by name"
    assert any(f["file"].endswith("qc_check.py") for f in findings), findings
    assert crg.AF_LOCAL_CANVAS in {f["af_code"] for f in findings}, findings


def test_shell_script_is_scanned_and_flagged(tmp_path):
    """make.sh was never scanned before (only *.py was); it is scanned now."""
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True)
    (run / "working" / "make.sh").write_text(
        "#!/bin/sh\npython3 bypasse.py  # dispatch via createTask\n")

    findings = crg.scan_run_dir(run)
    assert any(f["file"].endswith("make.sh") for f in findings), findings
    assert crg.AF_CANONICAL_RENDER_BYPASS in {f["af_code"] for f in findings}, findings


def test_true_copy_of_a_shipped_script_is_not_flagged(tmp_path):
    """A byte-identical copy of a shipped script is sanctioned by content."""
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True)
    shutil.copy(SHIPPED_QC_CHECK, run / "working" / "qc_check.py")

    assert crg.scan_run_dir(run) == []
    assert qcg.scan_run_dir(run) == []


def test_edited_copy_of_a_shipped_script_is_flagged(tmp_path):
    """The same basename with one foreign line added is no longer a shipped copy."""
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True)
    edited = SHIPPED_QC_CHECK.read_text() + "\n" + FOREIGN_RENDER
    (run / "working" / "qc_check.py").write_text(edited)

    findings = crg.scan_run_dir(run)
    assert any(f["file"].endswith("qc_check.py") for f in findings), findings


def test_qc_generator_guard_skips_name_allow_list(tmp_path):
    """The sibling guard obeys the same content rule: a foreign qc_check.py that
    writes a QC report is an ungoverned generator even though its name ships."""
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True)
    (run / "working" / "qc_check.py").write_text(FOREIGN_QC)

    findings = qcg.scan_run_dir(run)
    assert any(f["af_code"] == qcg.AF_QC_GENERATOR_UNGOVERNED for f in findings), findings


# ---------------------------------------------------------------------------
# PD-317 — a missing instrument is a named failure, not a pass.
# ---------------------------------------------------------------------------
def test_qc_generator_block_fails_when_instrument_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "qc_generator_guard", None)
    msg = crg._qc_generator_block(tmp_path)
    assert "AF-QC-GENERATOR-UNGOVERNED" in msg, msg
    assert "qc_generator_guard" in msg, msg


def test_qc_generator_block_degrades_only_under_explicit_contract(
        monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "qc_generator_guard", None)
    monkeypatch.setattr(phase_verifiers, "_degraded_allowed", lambda run_dir: True)
    assert crg._qc_generator_block(tmp_path) == ""


def test_run_fix2_checks_fails_when_engine_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "build_deck", None)
    failures = crg.run_fix2_checks(tmp_path)
    codes = {af for af, _ in failures}
    assert codes == {crg.AF_CANONICAL_RENDER_BYPASS, crg.AF_IMAGE_QC_VISION}, failures
    assert all("build_deck" in msg for _, msg in failures), failures


def test_run_fix2_checks_degrades_only_under_explicit_contract(
        monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "build_deck", None)
    monkeypatch.setattr(phase_verifiers, "_degraded_allowed", lambda run_dir: True)
    assert crg.run_fix2_checks(tmp_path) == []
