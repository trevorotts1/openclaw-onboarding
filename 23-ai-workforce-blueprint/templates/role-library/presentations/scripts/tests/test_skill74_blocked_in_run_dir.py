"""Skill 74 artifacts must never be dropped into a Presentations run dir.

`74-kie-live-adapter/scripts/kie_live_adapter.py` is read-only tooling (price,
prompt-budget, latest-family, validate), run from the Skill 74 folder. It carries
direct KIE.ai calls, so copying it into a run directory is a hand-rolled render
path. canonical_render_guard.scan_run_dir must flag it (AF-CANONICAL-RENDER-BYPASS)
and must NOT allow-list its basename. Roles and SOPs say exactly this
(slide-submitter, qc-specialist-prompt-presentations, TOOLS.md).
"""

import pathlib
import shutil
import sys
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import canonical_render_guard as crg  # noqa: E402

ADAPTER = SCRIPTS.parents[4] / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py"


def test_adapter_basename_is_not_allow_listed():
    assert "kie_live_adapter.py" not in crg.canonical_script_names()


@pytest.mark.skipif(not ADAPTER.is_file(), reason="Skill 74 not present in this tree")
def test_adapter_copied_into_run_dir_is_blocked():
    run = pathlib.Path(tempfile.mkdtemp())
    try:
        (run / "working").mkdir()
        shutil.copy(ADAPTER, run / "working" / "kie_live_adapter.py")
        findings = crg.scan_run_dir(run)
        codes = {f["af_code"] for f in findings}
        assert crg.AF_CANONICAL_RENDER_BYPASS in codes, findings
        assert any(f["file"].endswith("kie_live_adapter.py") for f in findings)
    finally:
        shutil.rmtree(run, ignore_errors=True)


def test_clean_run_dir_passes():
    run = pathlib.Path(tempfile.mkdtemp())
    try:
        (run / "working" / "prompts").mkdir(parents=True)
        (run / "working" / "prompts" / "slide-01.txt").write_text("a prompt")
        assert crg.scan_run_dir(run) == []
    finally:
        shutil.rmtree(run, ignore_errors=True)
