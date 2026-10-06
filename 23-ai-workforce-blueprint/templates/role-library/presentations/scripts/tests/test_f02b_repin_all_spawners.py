#!/usr/bin/env python3
"""test_f02b_repin_all_spawners.py -- F2b: ALL THREE engine spawners re-pin.

THE GAP F2 LEFT
---------------
F2 put an auto-repin gate in `launcher.dispatch()`: on a resume it hashes the
run's pinned manifest against the file on disk and, on a PROVEN difference,
runs the engine's own `presentation_job.py --repin` synchronously before argv
is built -- refusing the dispatch if the repin fails rather than spawning an
engine that dies EXIT_MANIFEST_MISMATCH (7) a second later and is then counted
as a launch.

That covers the POLLER, because the poller goes through the launcher. It does
NOT cover the other two spawners, which `Popen` the engine DIRECTLY:

    presentation_job/supervisor.py :: _restart              (Popen, line ~327)
    cc_board.py                    :: _dispatch_engine_if_idle (Popen, ~242)

Measured on pristine origin/main (3d441d12d) with a python3 substring scan of
each file: `auto_repin_gate` appears at lines 1314/1402/1714 of launcher.py and
at NO line of supervisor.py or cc_board.py, while all three carry an engine
Popen. The control is launcher.py itself -- same instrument, same scan, gate
found -- so an empty result for the other two is a fact about those files, not
a broken check.

WHY IT MATTERS MORE THAN THE POLLER PATH DOES
---------------------------------------------
The supervisor has a BOUNDED restart budget (--max-restarts, default 3) and
raises a persistent SUPERVISOR-ALARM.json when it is spent. After any roll that
edits PIPELINE-MANIFEST.json, an uncovered supervisor spends all three restarts
re-spawning engines that die on the stale pin and then alarms -- about the
restart budget, not about the manifest, which is the actual fault. Self-healing
becomes an alarm generator. `test_d_supervisor_refusal_is_not_a_restart_attempt`
below reproduces exactly that on pristine main.

WHAT THIS FILE PROVES, AND WITH WHAT INSTRUMENT
-----------------------------------------------
No mocking of the thing under test. The repin that runs is the REAL
`cmd_repin` in a REAL child interpreter: `scripts_dir` is a tmp directory whose
`presentation_job.py` is an INTERCEPTOR that records the argv it was handed and
forwards `--repin` verbatim to the real engine entry in this checkout. The gate
being called is the REAL `launcher.auto_repin_gate` -- imported, never stubbed,
never reimplemented.

`subprocess.Popen` is wrapped by a RECORDER that intercepts ONLY `--run` /
`--resume` argv and delegates everything else -- the repin child included,
since `subprocess.run` is itself built on Popen -- to the real Popen. That is
deliberate, and it is what makes the "nothing was spawned" assertions sound
rather than racy:
a detached Popen that has not written its marker yet is indistinguishable from
one that never ran, and an absence proved by a timeout is not proof. The
recorder also snapshots `state.manifest_sha256` AT THE MOMENT OF THE SPAWN, so
the ordering claim ("the repin ran BEFORE anything spawned") is measured, not
inferred.

`test_a_a_stale_pin_really_does_kill_a_dispatch` is the reality control: it runs
the REAL engine, no interceptor, and shows a stale pin exits 7 on `--run` (the
argv cc_board uses) -- so "spawning a corpse" is a measurement, not a phrase.
It passes on pristine main and on this branch: it is the premise, not the fix.

NOTHING HERE IS FABRICATED TO GO GREEN. The manifest under test is a copy of
this checkout's own canonical PIPELINE-MANIFEST.json, changed the way a roll
changes it (manifest_version bumped, re-serialised). The UNCURABLE case is a
real uncurable case: the pinned manifest file is left unparseable, so the real
`Manifest()` in the real `cmd_repin` dies EXIT_MANIFEST_MISMATCH -- no stubbed
non-zero exit anywhere. No network, no provider call, no spend, no deck, no
render.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cc_board  # noqa: E402
from presentation_job import supervisor  # noqa: E402
from presentation_job.state import EXIT_MANIFEST_MISMATCH  # noqa: E402

REAL_ENGINE_ENTRY = SCRIPTS / "presentation_job.py"

#: Spelled out, never imported, so the CONTROL tests in this file never fail on
#: pristine main for the trivial reason that a symbol the fix introduces does
#: not exist yet. A test that fails on main because of an ImportError proves
#: nothing about behaviour.
REPIN_LOG = ("working", "logs", "repin.log")
AUTO_REPIN_ENV_NAME = "PRESENTATION_AUTO_REPIN"
ALARM_FILENAME = "SUPERVISOR-ALARM.json"
LEDGER_FILENAME = "supervisor-restarts.json"


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _restore_sys_path():
    """cc_board._dispatch_engine_if_idle inserts its own directory on sys.path.
    Under test that directory is a tmp dir holding a `presentation_job.py`
    MODULE, which must not be left where a later import could shadow the real
    `presentation_job` PACKAGE."""
    before = list(sys.path)
    yield
    sys.path[:] = before


def _canonical_manifest() -> Path:
    """Same resolution order as tests/test_f02_auto_repin.py's own copy."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    pytest.skip("PIPELINE-MANIFEST.json not found from this checkout root")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _interceptor_scripts_dir(tmp_path: Path):
    """A tmp scripts dir whose presentation_job.py records, and forwards --repin.

    `--repin` is handed to the REAL engine entry in this checkout, so the repin
    under test is the real `cmd_repin` with its real phase diff and its real
    exit codes. Every other invocation is recorded and returns 0 without
    forwarding: this file never enters the engine's run loop.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "engine_invocations.json"
    (scripts / "presentation_job.py").write_text(
        "import json, pathlib, subprocess, sys\n"
        "MARKER = pathlib.Path(" + repr(str(marker)) + ")\n"
        "REAL = " + repr(str(REAL_ENGINE_ENTRY)) + "\n"
        "REAL_DIR = " + repr(str(SCRIPTS)) + "\n"
        "args = list(sys.argv[1:])\n"
        "rows = json.loads(MARKER.read_text()) if MARKER.exists() else []\n"
        "rows.append(args)\n"
        "MARKER.write_text(json.dumps(rows))\n"
        "if '--repin' in args:\n"
        "    sys.exit(subprocess.run([sys.executable, REAL] + args,\n"
        "                            cwd=REAL_DIR).returncode)\n"
        "sys.exit(0)\n",
        encoding="utf-8")
    return scripts, marker


class _FakeProc:
    def __init__(self, pid=424242):
        self.pid = pid

    def poll(self):
        return None


def _popen_recorder(monkeypatch, run: Path):
    """Record the ENGINE LAUNCH, and only the engine launch.

    Records argv AND the run's pinned sha at the instant of the spawn, which is
    what makes the ordering claim measurable rather than inferred, and what
    makes "nothing was spawned" a fact rather than a race with a detached child
    that has not written its marker yet.

    Only `--run`/`--resume` argv is intercepted. Everything else -- crucially
    the repin child, since `subprocess.run` is itself built on Popen -- is
    handed to the REAL Popen, so the repin under test stays a real child
    interpreter running the real `cmd_repin`.
    """
    calls = []
    real_popen = subprocess.Popen

    def fake_popen(argv, *a, **kw):
        args = [str(x) for x in argv] if isinstance(argv, (list, tuple)) else [str(argv)]
        if not ({"--run", "--resume"} & set(args)):
            return real_popen(argv, *a, **kw)
        try:
            pin = json.loads((run / "state.json").read_text(
                encoding="utf-8")).get("manifest_sha256")
        except (OSError, json.JSONDecodeError):
            pin = None
        calls.append({"argv": args, "pin_at_spawn": pin})
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return calls


def _make_run(tmp_path: Path, *, moved: bool, uncurable: bool = False):
    """A parked run pinned to a copy of the canonical manifest.

    moved=True reproduces a fleet roll: the pin is taken, THEN the manifest file
    changes underneath it (manifest_version bumped and re-serialised -- the same
    kind of edit a real bump makes).

    uncurable=True additionally leaves the pinned manifest file UNPARSEABLE, so
    the real `cmd_repin` reaches `Manifest(path)` and dies
    EXIT_MANIFEST_MISMATCH. That is a genuine uncurable mismatch produced by
    the real engine -- not a stubbed non-zero exit.
    """
    run = tmp_path / "run"
    (run / "working").mkdir(parents=True, exist_ok=True)
    man = run / "manifest.json"
    man.write_text(_canonical_manifest().read_text(encoding="utf-8"),
                   encoding="utf-8")
    pinned = _sha(man)
    version = int(json.loads(man.read_text(encoding="utf-8"))
                  .get("manifest_version") or 0)
    if moved:
        raw = json.loads(man.read_text(encoding="utf-8"))
        raw["manifest_version"] = version + 1
        man.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        assert _sha(man) != pinned, "the manifest edit did not move the sha"
    if uncurable:
        man.write_text("{ this is not json", encoding="utf-8")
        assert _sha(man) != pinned
    state = {
        "schema_version": 1,
        "job_id": "pj_test_f02b",
        "run_dir": str(run),
        "created_at": "2026-09-06T00:00:00Z",
        "manifest_path": str(man),
        "manifest_version": version,
        "manifest_sha256": pinned,
        "phases": [{"id": "P4-COPY", "status": "done", "artifacts": [],
                    "sha256": {}}],
        "gates": {}, "events": [], "sent": {}, "terminal": None,
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run, man, pinned


def _state(run: Path) -> dict:
    return json.loads((run / "state.json").read_text(encoding="utf-8"))


def _rows(marker: Path) -> list:
    return json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else []


def _dead_pid() -> int:
    """A pid that is really gone: start a child, reap it, hand back its pid."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _mark_worker_dead(run: Path) -> None:
    """`.job.lock` present, flock free, pid gone == supervisor.DEAD."""
    (run / ".job.lock").write_text(f"{_dead_pid()} 2026-09-06T00:00:00Z\n",
                                   encoding="utf-8")


def _cc_board_at(monkeypatch, scripts: Path) -> None:
    """cc_board resolves the engine from its OWN file location, so pointing the
    test at an interceptor means moving cc_board.__file__. `here` is computed
    inside the function from module globals, so this takes effect per call."""
    monkeypatch.setattr(cc_board, "__file__", str(scripts / "cc_board.py"))


# ===========================================================================
# A. THE PREMISE, MEASURED AGAINST THE REAL ENGINE (control: passes on main)
# ===========================================================================
def test_a_a_stale_pin_really_does_kill_a_dispatch(tmp_path, monkeypatch):
    """No interceptor, no fix, no mock: the real engine, the argv cc_board uses.

    This is the corpse the other tests talk about. It exits 7 -- before the run
    loop, in about a second -- which is exactly why a spawn on a stale pin is
    not a launch. Passes on pristine origin/main: it is the premise.
    """
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    run, man, pinned = _make_run(tmp_path, moved=True)

    proc = subprocess.run(
        [sys.executable, str(REAL_ENGINE_ENTRY), "--run", "--run-dir", str(run)],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=180)

    assert proc.returncode == EXIT_MANIFEST_MISMATCH, (
        f"expected the engine to die on the stale pin; rc={proc.returncode}\n"
        f"stdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}")
    assert "manifest changed under a running job" in (proc.stdout + proc.stderr)

    # CONTROL on the same instrument: cure the pin, and the same argv no longer
    # dies that way. An always-7 engine would prove nothing.
    cure = subprocess.run(
        [sys.executable, str(REAL_ENGINE_ENTRY), "--repin", "--run-dir", str(run)],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=180)
    assert cure.returncode == 0, (cure.returncode, cure.stdout, cure.stderr)
    assert _state(run)["manifest_sha256"] == _sha(man)


# ===========================================================================
# B. SUPERVISOR -- REGRESSION. Fails on pristine main: no repin, corpse spawned.
# ===========================================================================
def test_b_supervisor_repins_before_it_restarts(tmp_path, monkeypatch):
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)
    scan_root = tmp_path / "scan"

    ok, detail = supervisor._restart(scan_root, run, scripts)

    assert ok is True, (ok, detail)
    # The cure ran, and it was the engine's own documented one.
    rows = _rows(marker)
    assert len(rows) == 1, f"expected exactly one --repin child, got {rows}"
    assert "--repin" in rows[0] and str(run) in rows[0], rows
    # ...and it ran BEFORE the spawn. Measured at the spawn, not inferred.
    assert len(calls) == 1, calls
    assert "--resume" in calls[0]["argv"], calls
    assert calls[0]["pin_at_spawn"] == _sha(man), (
        "the engine was spawned while the run was still on the OLD pin -- it "
        f"would have died EXIT_MANIFEST_MISMATCH. {calls}")
    # The pin really moved, on the record, marked AUTOMATIC.
    st = _state(run)
    assert st["manifest_sha256"] == _sha(man)
    assert st["manifest_sha256_prev"] == pinned
    auto = st["auto_repin_history"]
    assert len(auto) == 1 and auto[0]["by"] == "launcher.auto_repin_gate", auto
    assert run.joinpath(*REPIN_LOG).is_file()


def test_c_supervisor_refuses_instead_of_spawning_a_corpse(tmp_path, monkeypatch):
    """The repin cannot cure it (the real cmd_repin dies 7 on the unparseable
    manifest). Nothing may be spawned. On pristine main the resume spawns."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True, uncurable=True)
    calls = _popen_recorder(monkeypatch, run)
    scan_root = tmp_path / "scan"

    ok, detail = supervisor._restart(scan_root, run, scripts)

    assert calls == [], (
        f"an engine was spawned on a pin that could not be re-pinned -- it "
        f"dies EXIT_MANIFEST_MISMATCH in about a second: {calls}")
    assert ok is not True, (ok, detail)
    assert "AF-MANIFEST-REPIN-FAILED" in detail, detail
    # The repin was really attempted, by the real engine, and left evidence.
    rows = _rows(marker)
    assert len(rows) == 1 and "--repin" in rows[0], rows
    log = run.joinpath(*REPIN_LOG)
    assert log.is_file(), "the refused repin left no log"
    assert "auto-repin rc=" in log.read_text(encoding="utf-8")
    # The pin was NOT quietly moved by a failed cure.
    assert _state(run)["manifest_sha256"] == pinned


def test_d_supervisor_refusal_is_not_a_restart_attempt(tmp_path, monkeypatch):
    """PROOF (c): a refusal must not spend a slot of the bounded budget.

    Four full --apply passes with --max-restarts 3 and no backoff. On this
    branch: nothing spawned, attempts stay at 0, no SUPERVISOR-ALARM.json ever.
    On pristine main the same four passes spawn three corpses, exhaust the
    budget and leave a standing alarm -- about the restart budget, not about
    the manifest, which is the fault.
    """
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "")
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    scan_root = tmp_path / "scan"
    scan_root.mkdir(parents=True, exist_ok=True)
    run_parent = scan_root / "runs"
    run_parent.mkdir(parents=True, exist_ok=True)
    run, man, pinned = _make_run(run_parent, moved=True, uncurable=True)
    _mark_worker_dead(run)
    calls = _popen_recorder(monkeypatch, run)

    for _ in range(4):
        supervisor.supervise(scan_root, scan_depth=4, apply=True,
                             max_restarts=3, backoff_seconds=0,
                             scripts_dir=scripts)

    assert calls == [], f"corpses were spawned across four passes: {calls}"
    alarm = scan_root / ALARM_FILENAME
    assert not alarm.is_file(), (
        "the restart budget was burned on a manifest fault no restart can fix, "
        f"and the supervisor alarmed about the wrong thing: "
        f"{alarm.read_text(encoding='utf-8') if alarm.is_file() else ''}")
    ledger = json.loads((scan_root / LEDGER_FILENAME).read_text(encoding="utf-8")) \
        if (scan_root / LEDGER_FILENAME).is_file() else {}
    entry = (ledger.get("runs") or ledger).get(str(run), {}) \
        if isinstance(ledger, dict) else {}
    assert int((entry or {}).get("attempts") or 0) == 0, (
        f"a repin refusal was charged to the restart budget: {entry}")


def test_e_supervisor_unmoved_pin_spawns_no_repin(tmp_path, monkeypatch):
    """CONTROL -- passes on pristine main too. Every supervise pass on a healthy
    run hits this: it must cost one child, not two, and must not touch state."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=False)
    calls = _popen_recorder(monkeypatch, run)

    ok, detail = supervisor._restart(tmp_path / "scan", run, scripts)

    assert ok is True, (ok, detail)
    assert _rows(marker) == [], "a repin child ran against a pin that had not moved"
    assert len(calls) == 1 and "--resume" in calls[0]["argv"], calls
    st = _state(run)
    assert st["manifest_sha256"] == pinned
    assert "auto_repin_history" not in st
    assert not run.joinpath(*REPIN_LOG).exists()


def test_f_supervisor_auto_repin_env_zero_is_the_rollback(tmp_path, monkeypatch):
    """CONTROL -- passes on pristine main too, which is the point: with the
    documented kill switch set, this branch behaves exactly like main."""
    monkeypatch.setenv(AUTO_REPIN_ENV_NAME, "0")
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)

    ok, detail = supervisor._restart(tmp_path / "scan", run, scripts)

    assert ok is True, (ok, detail)
    assert _rows(marker) == [], "the kill switch did not stop the repin child"
    assert len(calls) == 1 and "--resume" in calls[0]["argv"], calls
    assert _state(run)["manifest_sha256"] == pinned


# ===========================================================================
# G. CC_BOARD -- REGRESSION, and the fail-soft invariant.
# ===========================================================================
def test_g_cc_board_repins_before_it_dispatches(tmp_path, monkeypatch):
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    _cc_board_at(monkeypatch, scripts)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)

    assert cc_board._dispatch_engine_if_idle(run) is None

    rows = _rows(marker)
    assert len(rows) == 1 and "--repin" in rows[0], rows
    assert len(calls) == 1 and "--run" in calls[0]["argv"], calls
    assert calls[0]["pin_at_spawn"] == _sha(man), (
        "the engine was dispatched while the run was still on the OLD pin -- "
        f"test_a proves that exits 7. {calls}")
    st = _state(run)
    assert st["manifest_sha256"] == _sha(man)
    assert st["auto_repin_history"][0]["by"] == "launcher.auto_repin_gate"


def test_h_cc_board_does_not_dispatch_a_corpse(tmp_path, monkeypatch):
    """An uncurable pin: no spawn, no raise. Withholding a spawn that would
    exit 7 is not blocking a build -- a corpse builds nothing."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    _cc_board_at(monkeypatch, scripts)
    run, man, pinned = _make_run(tmp_path, moved=True, uncurable=True)
    calls = _popen_recorder(monkeypatch, run)

    assert cc_board._dispatch_engine_if_idle(run) is None  # never raises

    assert calls == [], f"cc_board dispatched an engine that cannot start: {calls}"
    assert len(_rows(marker)) == 1, _rows(marker)
    assert _state(run)["manifest_sha256"] == pinned


def test_i_cc_board_is_fail_soft_when_the_gate_explodes(tmp_path, monkeypatch):
    """PROOF (d): the board MIRRORS, it never gates. If the repin surface itself
    misbehaves, the dispatch proceeds exactly as it did before this fix and the
    callback still returns None. A board helper may never become a build gate."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    _cc_board_at(monkeypatch, scripts)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)

    from presentation_job import launcher as _launcher

    def _boom(*a, **kw):
        raise RuntimeError("gate exploded")

    monkeypatch.setattr(_launcher, "auto_repin_gate", _boom)

    assert cc_board._dispatch_engine_if_idle(run) is None  # no exception escapes

    assert len(calls) == 1 and "--run" in calls[0]["argv"], (
        f"a misbehaving repin surface blocked the dispatch: {calls}")


def test_i2_neither_caller_dies_on_a_systemexit_from_the_gate(tmp_path, monkeypatch):
    """`die()` -- a bare SystemExit -- is how every manifest helper reports
    trouble, and SystemExit is NOT an Exception. One escaping the gate would
    abort the whole launchd supervise pass and the CC ingest callback, which is
    strictly worse than not having the gate. Both callers must absorb it and
    fall back to the pre-fix behaviour: spawn on the existing pin."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    from presentation_job import launcher as _launcher

    def _die(*a, **kw):
        raise SystemExit(7)

    monkeypatch.setattr(_launcher, "auto_repin_gate", _die)

    scripts, marker = _interceptor_scripts_dir(tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)

    ok, detail = supervisor._restart(tmp_path / "scan", run, scripts)
    assert ok is True, (ok, detail)
    assert len(calls) == 1 and "--resume" in calls[0]["argv"], calls

    _cc_board_at(monkeypatch, scripts)
    assert cc_board._dispatch_engine_if_idle(run) is None
    assert len(calls) == 2 and "--run" in calls[1]["argv"], calls


def test_j_cc_board_unmoved_pin_dispatches_untouched(tmp_path, monkeypatch):
    """CONTROL -- passes on pristine main too."""
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    _cc_board_at(monkeypatch, scripts)
    run, man, pinned = _make_run(tmp_path, moved=False)
    calls = _popen_recorder(monkeypatch, run)

    assert cc_board._dispatch_engine_if_idle(run) is None

    assert _rows(marker) == []
    assert len(calls) == 1 and "--run" in calls[0]["argv"], calls
    st = _state(run)
    assert st["manifest_sha256"] == pinned
    assert "auto_repin_history" not in st


# ===========================================================================
# K. THE STRUCTURAL CLAIM, ON THE FILES THEMSELVES.
# ===========================================================================
def test_k_all_three_spawners_reach_the_same_gate(tmp_path):
    """One gate, three callers -- and never a fourth copy of the logic.

    The launcher is the CONTROL: same instrument (an exact substring scan of
    the source), and it must come back non-empty. If it did not, this check
    would be broken rather than the files being clean.
    """
    launcher_src = (SCRIPTS / "presentation_job" / "launcher.py").read_text(encoding="utf-8")
    supervisor_src = (SCRIPTS / "presentation_job" / "supervisor.py").read_text(encoding="utf-8")
    board_src = (SCRIPTS / "cc_board.py").read_text(encoding="utf-8")

    assert "def auto_repin_gate(" in launcher_src, (
        "CONTROL FAILED -- auto_repin_gate is not defined in launcher.py, so "
        "this check cannot say anything about the other two files.")
    assert "auto_repin_gate(run_path, engine_entry, scripts)" in launcher_src

    assert "auto_repin_gate" in supervisor_src, (
        "supervisor.py Popens the engine directly and never reaches the repin "
        "gate -- every restart after a manifest roll spawns a corpse.")
    assert "auto_repin_gate" in board_src, (
        "cc_board.py Popens the engine directly and never reaches the repin "
        "gate -- every board dispatch after a manifest roll spawns a corpse.")

    # The gate is IMPORTED, never re-implemented: no second place where a pin
    # moves. `--repin` as a child argv may appear only in launcher.py.
    for name, src in (("supervisor.py", supervisor_src), ("cc_board.py", board_src)):
        assert '"--repin"' not in src, (
            f"{name} builds its own --repin argv -- that is a second "
            f"implementation of the phase diff. Call auto_repin_gate instead.")
        assert "from presentation_job.launcher import" in src \
            or "from .launcher import" in src, name


def test_l_the_kill_switch_is_one_env_var_for_all_three(tmp_path, monkeypatch):
    """PRESENTATION_AUTO_REPIN=0 must disarm every caller, because it disarms
    the gate itself -- not three separate checks that can drift apart."""
    monkeypatch.setenv(AUTO_REPIN_ENV_NAME, "0")
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    _cc_board_at(monkeypatch, scripts)
    run, man, pinned = _make_run(tmp_path, moved=True)
    calls = _popen_recorder(monkeypatch, run)

    cc_board._dispatch_engine_if_idle(run)

    assert _rows(marker) == [], "the kill switch did not stop the repin child"
    assert len(calls) == 1, calls
    assert _state(run)["manifest_sha256"] == pinned
    assert os.environ[AUTO_REPIN_ENV_NAME] == "0"
