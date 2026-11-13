"""PD-079 -- small stale text and a home-folder guess in the dispatcher.

Finding PD-079 (PASS4-ENGINE), consolidation amendments binding:
  * the `--reset-allowance` help must state the REAL range (1..128, the value
    of PHASE_TOTAL_PAID_HARD_CAP at dispatcher.py:246), not "(1..retry cap)";
  * the ROOT-CAUSE comment in `dispatch_one` must stop claiming the copy QC
    phase never reads its own report -- `phase_verifiers.py` wires
    P1Q-COPY-QC to `_verify_qc_report("working/qc/copy_qc_report.json",
    "_chk_copy_qc", "AF-COPY-QC")`, so it does;
  * `_json_load_manifest_fallback` must resolve the manifest with the
    canonical resolver the rest of the engine uses, never a guessed
    `~/openclaw-onboarding/...` copy.

What is proven here (no paid call, no network):
  * the parser's own help text carries the constant's value;
  * the stale sentence is gone from the source AND the verifier mapping it
    contradicts is still the report gate;
  * the fallback resolves with HOME pointed at an empty directory -- the
    base version raised FileNotFoundError there while the repo copy was
    present, which is the defect.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402

PV = SCRIPTS / "phase_verifiers.py"

STALE_SENTENCE = (
    "which only ever reads working/copy/slides_copy.md and never looks at"
)

def test_reset_allowance_help_states_the_real_range():
    help_text = D.build_parser().format_help()
    assert "provider calls allowed by --authorize-paid-retry-reset" in help_text
    assert f"1..{D.PHASE_TOTAL_PAID_HARD_CAP}" in help_text
    assert D.PHASE_TOTAL_PAID_HARD_CAP == 128
    assert "(1..retry cap)" not in help_text

def test_copy_qc_comment_matches_the_verifier_mapping():
    src = Path(inspect.getsourcefile(D)).read_text(encoding="utf-8")
    assert STALE_SENTENCE not in src, (
        "dispatcher.py still says the copy QC phase never reads its report")
    assert "P1Q-COPY-QC was exactly that" in src

    pv = PV.read_text(encoding="utf-8")
    assert '"P1Q-COPY-QC":        _verify_qc_report(' in pv
    assert '"working/qc/copy_qc_report.json", "_chk_copy_qc", "AF-COPY-QC")' in pv

def test_manifest_fallback_never_guesses_a_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PRESENTATION_MANIFEST", raising=False)

    fn_src = inspect.getsource(D._json_load_manifest_fallback)
    assert "openclaw-onboarding" not in fn_src
    assert ".home()" not in fn_src

    resolved = D._qc_manifest_for_run()
    assert resolved is not None and resolved.is_file(), (
        "the repo copy must resolve for this test to mean anything")
    loaded = D._json_load_manifest_fallback()
    assert loaded.get("manifest_version") == \
        __import__("json").loads(resolved.read_text(encoding="utf-8"))["manifest_version"]
