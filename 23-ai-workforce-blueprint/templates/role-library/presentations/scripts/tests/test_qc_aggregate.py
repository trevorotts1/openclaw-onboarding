"""qc_aggregate.py tests -- the P-QC-AGGREGATE phase producer.

PR 748 made the `qc` gate fail-closed against working/qc/final_qc_report.json, but
no phase produced that file, so the fixed gate blocked EVERY job, including a
flawless one. qc_aggregate.py is that producer: it reads the six domain QC reports
(copy/typography/prompt/image/priority_shift/speech), verifies provenance via
qc_generator_guard.py's existing AF-QC-GENERATOR-UNGOVERNED / AF-QC-RUBRIC-CORRUPT /
AF-QC-REPORT-UNTRUSTED checks plus build_deck._qc_independence_reason, computes the
combined score, and writes final_qc_report.json. These tests prove: a genuine
flawless set of six reports aggregates to a pass; a missing/untrusted/sub-threshold/
self-graded input BLOCKS and the report never carries a fabricated numeric average.
"""
import json
import subprocess
import sys
import pathlib
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import qc_aggregate  # noqa: E402


def _rd() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _w(rd: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _wj(rd: pathlib.Path, rel: str, obj) -> pathlib.Path:
    return _w(rd, rel, json.dumps(obj))


def _genuine_domain_report(gate: str, average: float = 9.4) -> dict:
    return {
        "gate": gate,
        "average": average,
        "pass": average >= 8.5,
        "triggered_autofails": [],
        "qc_independence": {
            "graded_by": "qc-specialist-independent-reviewer",
            "independent": True,
        },
    }


def _genuine_priority_shift_report(passing: bool = True) -> dict:
    return {
        "schema": "priority_shift_report/v1",
        "gate": "AF-PRIORITY-SHIFT",
        "phase": "P-SHIFT-QC (order 7.5)",
        "pass": passing,
        "items": [
            {"item": f"item_{i}", "pass": passing, "evidence": "ok"}
            for i in range(15)
        ],
    }


def _seed_six_genuine_reports(rd: pathlib.Path, average: float = 9.4) -> None:
    _wj(rd, "working/qc/copy_qc_report.json", _genuine_domain_report("Phase 1Q", average))
    _wj(rd, "working/qc/typography_qc_report.json",
        _genuine_domain_report("Phase Typography-QC", average))
    _wj(rd, "working/qc/prompt_qc_report.json",
        _genuine_domain_report("Phase Prompt-QC", average))
    _wj(rd, "working/qc/image_qc_report.json",
        _genuine_domain_report("Phase Image-QC", average))
    _wj(rd, "working/qc/speech_qc_report.json",
        _genuine_domain_report("Phase Speech-QC", average))
    _wj(rd, "working/qc/priority_shift_report.json", _genuine_priority_shift_report(True))


# ---------------------------------------------------------------------------
# The flawless case: all six genuine, passing reports aggregate to a real pass.
# ---------------------------------------------------------------------------
def test_aggregate_passes_with_six_genuine_reports():
    rd = _rd()
    _seed_six_genuine_reports(rd, average=9.4)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is True, report
    assert report["average"] == 9.4, report
    assert report["computed_average"] == 9.4
    assert report["missing_domains"] == []
    assert report["blocking_reasons"] == []
    assert report["generator_guard"]["clean"] is True


def test_aggregate_writes_final_qc_report_file():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    qc_aggregate.aggregate(rd)  # aggregate() alone does not write; main()/CLI does
    out = rd / qc_aggregate.FINAL_REPORT_REL
    assert not out.exists(), "aggregate() is pure -- only the CLI entrypoint writes the file"
    # Now go through the real entrypoint (mirrors what the manifest's script executor runs).
    rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", str(rd)],
        capture_output=True, text=True, timeout=60,
    )
    assert rc.returncode == 0, rc.stderr
    assert out.is_file()
    obj = json.loads(out.read_text())
    assert obj["pass"] is True
    assert obj["average"] == 9.4


# ---------------------------------------------------------------------------
# Missing domain -- BLOCKED, message names which.
# ---------------------------------------------------------------------------
def test_aggregate_blocks_on_missing_domain_and_names_it():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    (rd / "working" / "qc" / "speech_qc_report.json").unlink()
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None, "a blocked verdict must never carry a numeric average"
    assert "speech" in report["missing_domains"]
    assert any("speech_qc_report.json" in r for r in report["blocking_reasons"]), \
        report["blocking_reasons"]
    assert any("P-SPEECH-QC" in r for r in report["blocking_reasons"])


def test_aggregate_blocks_on_missing_priority_shift():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    (rd / "working" / "qc" / "priority_shift_report.json").unlink()
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    assert "priority_shift" in report["missing_domains"]
    assert any("priority_shift_report.json" in r for r in report["blocking_reasons"])


# ---------------------------------------------------------------------------
# Sub-threshold domain -- BLOCKED.
# ---------------------------------------------------------------------------
def test_aggregate_blocks_on_sub_threshold_domain():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    _wj(rd, "working/qc/image_qc_report.json", _genuine_domain_report("Phase Image-QC", 6.0))
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    assert any("6.0" in r and "Image QC" in r for r in report["blocking_reasons"]), \
        report["blocking_reasons"]
    # computed_average is still informational when every number IS readable, even
    # though the deck fails -- it must never leak into the gate-facing "average".
    assert report["computed_average"] is not None


def test_aggregate_blocks_on_priority_shift_failed_items():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    _wj(rd, "working/qc/priority_shift_report.json", _genuine_priority_shift_report(False))
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    assert any("AF-PRIORITY-SHIFT" in r for r in report["blocking_reasons"])
    assert report["domains"]["priority_shift"]["failed_items"], \
        "the failed items must be named, not just a bare fail"


# ---------------------------------------------------------------------------
# Untrusted / ungoverned generator -- BLOCKED via the EXISTING AF codes
# (qc_generator_guard.py, not a new mechanism).
# ---------------------------------------------------------------------------
def test_aggregate_blocks_on_ungoverned_generator_script():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    _w(rd, "_build_qc_report.py",
       "def score_prompt_length(text):\n"
       "    words = len(text.split())\n"
       "    return 10 if 80 <= words <= 180 else 3\n"
       "import json\n"
       "json.dump({'average': 10}, open('working/qc/rogue_qc_report.json', 'w'))\n")
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None, \
        "an ungoverned generator finding must null the average even if all six domain " \
        "reports individually look fine"
    assert report["generator_guard"]["clean"] is False
    codes = {f["af_code"] for f in report["generator_guard"]["blocking"]}
    assert "AF-QC-GENERATOR-UNGOVERNED" in codes, report["generator_guard"]
    assert "AF-QC-RUBRIC-CORRUPT" in codes, report["generator_guard"]
    assert any("AF-QC-GENERATOR-UNGOVERNED" in r for r in report["blocking_reasons"])


def test_aggregate_blocks_on_untrusted_report_fingerprint():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    obj = _genuine_domain_report("Phase Image-QC", 9.4)
    obj["typography_overlay_readiness"] = True  # the eliminated corrupt-rubric fingerprint
    _wj(rd, "working/qc/image_qc_report.json", obj)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    codes = {f["af_code"] for f in report["generator_guard"]["blocking"]}
    assert "AF-QC-REPORT-UNTRUSTED" in codes, report["generator_guard"]


# ---------------------------------------------------------------------------
# Self-graded / no independent-reviewer provenance -- BLOCKED (AF-QC-INDEPENDENCE,
# the EXISTING check build_deck.py already uses for every domain gate).
# ---------------------------------------------------------------------------
def test_aggregate_blocks_on_self_graded_report():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    obj = _genuine_domain_report("Phase 1Q", 9.4)
    obj["qc_independence"] = {"graded_by": "build_deck.py", "independent": True}
    _wj(rd, "working/qc/copy_qc_report.json", obj)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    assert any("AF-QC-INDEPENDENCE" in r for r in report["blocking_reasons"]), \
        report["blocking_reasons"]


def test_aggregate_blocks_on_report_with_no_independence_provenance_at_all():
    """A report that OMITS provenance entirely must fail -- independence must be
    proven, never assumed (mirrors _qc_independence_reason's own contract)."""
    rd = _rd()
    _seed_six_genuine_reports(rd)
    obj = {"gate": "Phase Typography-QC", "average": 9.4, "pass": True,
           "triggered_autofails": []}  # no qc_independence block at all
    _wj(rd, "working/qc/typography_qc_report.json", obj)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None
    assert any("AF-QC-INDEPENDENCE" in r for r in report["blocking_reasons"])


# ---------------------------------------------------------------------------
# Never-fabricate invariant, swept across every blocking scenario above.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mutate", [
    lambda rd: (rd / "working" / "qc" / "speech_qc_report.json").unlink(),
    lambda rd: _wj(rd, "working/qc/image_qc_report.json",
                   _genuine_domain_report("Phase Image-QC", 3.0)),
    lambda rd: _wj(rd, "working/qc/priority_shift_report.json",
                   _genuine_priority_shift_report(False)),
])
def test_average_is_never_fabricated_when_blocked(mutate):
    rd = _rd()
    _seed_six_genuine_reports(rd)
    mutate(rd)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert report["average"] is None, (
        "MUTANT DETECTED: a blocked aggregation must never carry a numeric "
        f"'average' -- that is exactly the fabricated-score defect this producer "
        f"exists to prevent. Got: {report}"
    )


# ---------------------------------------------------------------------------
# CLI exit codes: default mode mirrors qc_generator_guard.py's own convention
# (0 clean / 5 blocked); --phase-mode always exits 0 once the report is
# mechanically written, deferring pass/fail enforcement to gates.py's qc gate.
# ---------------------------------------------------------------------------
def test_cli_default_mode_exit_0_on_pass():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", str(rd)],
        capture_output=True, text=True, timeout=60,
    )
    assert rc.returncode == 0, rc.stderr


def test_cli_default_mode_exit_5_on_block():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    (rd / "working" / "qc" / "copy_qc_report.json").unlink()
    rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", str(rd)],
        capture_output=True, text=True, timeout=60,
    )
    assert rc.returncode == 5, rc.stdout + rc.stderr
    assert "copy_qc_report.json" in (rc.stdout + rc.stderr)


def test_cli_phase_mode_exits_0_even_when_blocked():
    rd = _rd()
    _seed_six_genuine_reports(rd)
    (rd / "working" / "qc" / "copy_qc_report.json").unlink()
    rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", str(rd), "--phase-mode"],
        capture_output=True, text=True, timeout=60,
    )
    assert rc.returncode == 0, (
        "phase-mode must exit 0 once the report is mechanically written -- pass/fail "
        f"enforcement belongs to gates.py's close()-time qc gate, not this phase. "
        f"stdout={rc.stdout} stderr={rc.stderr}"
    )
    out = rd / qc_aggregate.FINAL_REPORT_REL
    assert out.is_file()
    obj = json.loads(out.read_text())
    assert obj["pass"] is False
    assert obj["average"] is None


def test_cli_usage_error_exits_2():
    rc = subprocess.run(
        [sys.executable, str(SCRIPTS / "qc_aggregate.py"), "--run-dir", "/no/such/dir/at/all"],
        capture_output=True, text=True, timeout=60,
    )
    assert rc.returncode == 2, rc.stdout + rc.stderr


# ---------------------------------------------------------------------------
# The six paths this producer reads must come from the manifest's own
# produces_artifact declarations, not a silently-drifting second copy.
# ---------------------------------------------------------------------------
def test_default_domain_paths_match_the_real_manifest():
    paths, provenance = qc_aggregate._resolve_domain_paths(None)
    assert "manifest" in provenance, provenance
    assert paths["P1Q-COPY-QC"] == "working/qc/copy_qc_report.json"
    assert paths["P-TYPO-QC"] == "working/qc/typography_qc_report.json"
    assert paths["P-PROMPT-QC"] == "working/qc/prompt_qc_report.json"
    assert paths["P-IMAGE-QC"] == "working/qc/image_qc_report.json"
    assert paths["P-SHIFT-QC"] == "working/qc/priority_shift_report.json"
    assert paths["P-SPEECH-QC"] == "working/qc/speech_qc_report.json"


def test_falls_back_to_defaults_when_no_manifest_resolvable(monkeypatch, tmp_path):
    # Simulate an environment where no manifest can be found at all (an isolated
    # fixture with no universal-sops/ ancestor and no sops/ sibling).
    import manifest_source
    monkeypatch.setattr(manifest_source, "find_repo_root", lambda start: None)
    isolated_scripts_dir = tmp_path / "isolated" / "scripts"
    isolated_scripts_dir.mkdir(parents=True)
    monkeypatch.setattr(qc_aggregate, "HERE", isolated_scripts_dir)
    paths, provenance = qc_aggregate._resolve_domain_paths(None)
    assert provenance.startswith("defaults")
    assert paths["P-SPEECH-QC"] == "working/qc/speech_qc_report.json"
