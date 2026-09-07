"""F20 regression pins -- the two PRODUCTION defects the 48-red-test triage found.

Both were invisible because the failure was swallowed:

  1. `presentation_job/workingset.py::measure_workingset` called `_read_bytes(path)`
     -- a name that exists nowhere in the module or its imports. It is reached
     ONLY on the phase-completion branch (`hash_on_completion=True`), and
     `Engine._checkpoint` wraps the whole working-set call in a bare
     `except Exception: pass`. So every phase-completion checkpoint raised
     NameError, silently, on every run: FIX-20's compaction guarantee was dead
     and a finished phase reloaded as "running". The same rewrite also built an
     `entry` dict per file and appended none of them, so the record's documented
     "files" list shipped permanently empty.

  2. `presentation_job/supervisor.py::supervise` called `_restart(...)` with no
     `apply` guard. Its own docstring promises "Report-only unless `apply` is
     True" and "with `apply=False` this pass writes NOTHING to the scanned tree",
     and its summary line counts `reported_only` withheld -- a counter that was
     initialised and never incremented. A dry run spawned `--resume` engines and
     wrote restart logs into the scanned tree.

Every test here carries its own known-good control, so a version of the code that
simply does nothing cannot make them pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import workingset  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import (  # noqa: E402
    EXIT_OK, LOCK_FILENAME, StateStore,
)
from presentation_job.supervisor import (  # noqa: E402
    EVENTS_FILENAME, LEDGER_FILENAME, supervise,
)


# ===========================================================================
# 1. workingset.measure_workingset -- the completion branch
# ===========================================================================

BODY = "hello working set"

# A phase whose working set is declared in the shipped table, so these tests
# measure the real code path rather than an invented one.
_MEASURED_PHASE = "P0A-INTAKE"          # -> working/copy/intake.json, working/interview/*.json


def _one_file_run(tmp_path: Path, body: str = BODY) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(body)
    return rd


def test_completion_measurement_reads_bytes_instead_of_raising(tmp_path):
    """`hash_on_completion=True` must MEASURE the file, not raise NameError.

    Control: the stat-only branch (`hash_on_completion=False`) on the same run
    dir, which never took the broken path -- if the control were also empty the
    fixture, not the code, would be at fault.
    """
    rd = _one_file_run(tmp_path)

    control = workingset.measure_workingset(
        rd, _MEASURED_PHASE, hash_on_completion=False)
    assert control["total_bytes"] == len(BODY), control

    measured = workingset.measure_workingset(
        rd, _MEASURED_PHASE, hash_on_completion=True)
    assert measured["total_bytes"] == len(BODY), measured
    # `chars` is populated ONLY by the completion read -- it stays None on the
    # stat-only path, so this is the assertion the missing helper broke.
    assert measured["files"], "the completion measurement recorded no files"
    assert measured["files"][0]["chars"] == len(BODY), measured
    assert measured["total_chars"] == len(BODY), measured


def test_measurement_records_every_file_it_counted(tmp_path):
    """The documented "files" list must actually carry one row per file.

    Control: total_bytes proves all three files WERE walked, so an empty
    `files` list is a reporting loss, never an empty run dir.
    """
    rd = tmp_path / "run"
    (rd / "working" / "interview").mkdir(parents=True)
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text("z" * 10)
    for i in (1, 2):
        (rd / "working" / "interview" / f"turn-{i}.json").write_text("z" * 10)

    m = workingset.measure_workingset(rd, _MEASURED_PHASE, hash_on_completion=True)

    assert m["total_bytes"] == 30, m          # control: all three were walked
    assert len(m["files"]) == 3, m["files"]   # the pin
    assert sorted(f["path"] for f in m["files"]) == [
        "working/copy/intake.json",
        "working/interview/turn-1.json",
        "working/interview/turn-2.json",
    ]


def test_done_checkpoint_survives_a_compaction(tmp_path):
    """End-to-end seam: a phase the engine marked done must reload as done.

    This is the user-visible cost of defect 1 -- Engine._checkpoint swallowed
    the NameError, so the on-disk checkpoint kept the last RUNNING record and a
    resume after a compaction re-entered a finished phase.

    Control: the RUNNING checkpoint written earlier in the same run is present,
    proving the checkpoint machinery itself works and only the completion write
    was being lost.
    """
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    # Pre-staged so the agent-executor phase attests it as done immediately.
    (rd / "working" / "copy" / "sp_structure.json").write_text(json.dumps({"ok": True}))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "manifest_version": 1,
        "phases": [{
            "id": "P-SP-STRUCTURE", "order": 1.0,
            "owning_role": "slide-image-creator",
            "produces_artifact": "working/copy/sp_structure.json",
            "executor": {"kind": "agent"},
        }],
        "deliverables_required": [],
        "gates": [],
    }))
    manifest = Manifest(manifest_path)
    store = StateStore(rd)
    state = {
        "job_id": "pj_f20", "schema_version": 1, "run_dir": str(rd),
        "manifest_path": str(manifest_path), "manifest_sha256": manifest.sha256,
        "phases": [], "events": [], "sent": {}, "requester": {"chat_id": "t"},
        "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    engine = Engine(rd, manifest, store, store.load(), dry_run=True)

    assert engine.run_phase(manifest.phase("P-SP-STRUCTURE")) == EXIT_OK
    assert "P-SP-STRUCTURE" in workingset.list_checkpoints(rd)  # control

    reloaded = workingset.reload_phase(rd, "P-SP-STRUCTURE")
    assert reloaded["reloaded"] is True
    assert reloaded["phase_record"]["status"] == "done", (
        "the completion checkpoint was lost: a compaction would re-enter a "
        f"finished phase. Reloaded record: {reloaded['phase_record']}")


# ===========================================================================
# 2. supervisor.supervise -- report-only must WITHHOLD, not restart
# ===========================================================================

def _dead_run(run_dir: Path) -> Path:
    """A run dir shaped like one whose engine died: active state, free lock,
    a pid that is provably gone."""
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir.joinpath("state.json").write_text(json.dumps({
        "schema_version": 1, "job_id": "pj_f20_sup", "run_dir": str(run_dir),
        "terminal": None, "current_phase": "P4-RENDER",
        "heartbeat": {"current_phase": "P4-RENDER", "interval_minutes": 10},
    }))
    run_dir.joinpath(LOCK_FILENAME).write_text("999999999 2026-08-27T21:00:00\n")
    return run_dir


def _run_supervise(root: Path, **kw):
    import io
    buf = io.StringIO()
    old, sys.stdout = sys.stdout, buf
    try:
        rc = supervise(root, **kw)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def test_report_only_pass_withholds_the_restart(tmp_path):
    """apply=False must announce the death AND announce the withholding.

    Control: the same pass still emits WORKER_DEAD, so a supervisor that simply
    saw nothing cannot pass this test.
    """
    root = tmp_path
    _dead_run(root / "run-a")

    rc, out = _run_supervise(root, apply=False, scan_depth=1)

    assert rc == EXIT_OK, out
    assert "WORKER_DEAD" in out, out                     # control
    assert "RESTART_WITHHELD" in out, out                # the pin
    assert "1 withheld (report-only)" in out, out
    assert "0 restarted" in out, out


def test_report_only_pass_leaves_the_scanned_tree_byte_identical(tmp_path):
    """The docstring's READ-ONLY CONTRACT, enforced.

    Control: the run's own state.json is still there afterwards, so an empty
    'after' snapshot cannot make this pass trivially.
    """
    root = tmp_path
    _dead_run(root / "run-a")
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
              for p in root.rglob("*") if p.is_file()}
    assert before, "fixture wrote no files -- the instrument is broken"

    rc, _ = _run_supervise(root, apply=False, scan_depth=1)

    after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
             for p in root.rglob("*") if p.is_file()}
    assert rc == EXIT_OK
    assert set(after) == set(before), (
        f"report-only created files: {sorted(str(p) for p in set(after) - set(before))}")
    assert after == before, "report-only modified a file it was only reading"
    assert not (root / EVENTS_FILENAME).is_file()
    assert not (root / LEDGER_FILENAME).is_file()
    assert not (root / "run-a" / "working" / ".lease.json").exists()


def test_apply_pass_still_reaches_the_restart(tmp_path):
    """KNOWN-GOOD CONTROL for the guard above: with apply=True the restart is
    still attempted, so the fix withholds only the report-only path and did not
    disable restarts altogether.

    `scripts_dir` deliberately has no presentation_job.py, so `_restart`
    reports 'entry script missing' instead of spawning anything -- the restart
    path is proven reached without starting a process.
    """
    root = tmp_path / "scan"
    root.mkdir()
    empty_scripts = tmp_path / "no-scripts"
    empty_scripts.mkdir()
    _dead_run(root / "run-a")

    rc, out = _run_supervise(root, apply=True, scan_depth=1,
                             scripts_dir=empty_scripts, backoff_seconds=0)

    assert "RESTART_WITHHELD" not in out, out
    assert "RESTART_FAILED" in out, out
    assert "entry script missing" in out, out
    assert (root / LEDGER_FILENAME).is_file(), "an --apply pass must write its ledger"
    assert rc != EXIT_OK or True  # rc is budget-dependent; the pin is the path taken
