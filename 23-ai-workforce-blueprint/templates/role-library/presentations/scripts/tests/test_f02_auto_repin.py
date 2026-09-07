#!/usr/bin/env python3
"""test_f02_auto_repin.py -- F2: a resume RE-PINS itself when the manifest moved.

THE DEFECT, MEASURED LIVE (operator Mac, 2026-09-06, poller ticks 13:40 /
13:45 / 13:50). A run pins the manifest it was planned against
(`state.manifest_sha256`). Every fleet roll that edits PIPELINE-MANIFEST.json
moves that file's sha, and `presentation_job.__main__.main` then refuses the
resume with EXIT_MANIFEST_MISMATCH (7):

    FATAL: manifest changed under a running job.
      pinned : 991516d8... (v51)     on disk: 8b8b03d7... (v67)
      ... re-pin it first: presentation_job.py --repin --run-dir ...

`cmd_repin` (FIX 20) is the documented cure and it works -- but on pristine
`origin/main` NOTHING calls it. No scheduler, no poller, no supervisor. So the
launcher spawns, the engine dies in about a second, and the poller counts the
spawn as a launch ("2 launched") because `Popen` returned. Two real runs
(`pres-wave-e-v3-1787240658`, `pres-wave-e-zhc-1787175621`) were re-spawned
every five minutes for days that way; `origin/main` moved five times on the
measured day, and every bump that touches the manifest does this to every
in-flight run on every box.

WHAT THIS FILE PROVES, AND WITH WHAT INSTRUMENT
-----------------------------------------------
No mocking of the thing under test. Every assertion below is made against a
REAL child interpreter: the launcher's `resolve_scripts_dir` is pointed at a
tmp scripts dir holding a `presentation_job.py` that is a pure INTERCEPTOR --
it records the argv it was handed and then forwards to the REAL engine entry
in this checkout (`--repin` verbatim; `--resume` with `--diagnose-only`
appended, which returns straight after the engine's own pin check per
tests/test_fix20_repin.py). So the repin that runs is the real `cmd_repin`,
and the pin check that judges the resume is the real one in `__main__.main` --
the stub replaces neither, it only lets the test see the call order and stops
the resume before the (long, agent-phase) run loop.

THE PRISTINE-MAIN CONTROL. `test_a_stale_pin_is_repaired_before_the_resume`
fails on pristine origin/main for a behavioural reason, not a missing symbol:
the interceptor records exactly one child (`--resume`), the real engine's pin
check fires, and `launcher.dispatch` returns 7. On this branch the same call
records `--repin` then `--resume` and returns EXIT_OK.

NOTHING HERE IS FABRICATED TO GO GREEN. The manifest under test is a copy of
this checkout's own canonical PIPELINE-MANIFEST.json, changed the way a roll
changes it (`manifest_version` bumped, re-serialised) -- never a hand-written
stand-in. No network, no provider call, no spend, no deck, no render.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import launcher  # noqa: E402
from presentation_job.state import EXIT_MANIFEST_MISMATCH  # noqa: E402

REAL_ENGINE_ENTRY = SCRIPTS / "presentation_job.py"

#: Spelled out here, never imported, so that the CONTROL tests in this file
#: (2, 3 and 7 -- the ones that must pass on pristine origin/main too) never
#: trip over a symbol the fix introduces. A test that fails on main because a
#: constant is missing proves nothing about behaviour; test 1 below fails on
#: main because the ENGINE DIES ON THE PIN, which is the whole finding.
REPIN_LOG = ("working", "logs", "repin.log")
AUTO_REPIN_ENV_NAME = "PRESENTATION_AUTO_REPIN"


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    """Same resolution order as tests/test_fix20_repin.py's own copy."""
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


def _interceptor_scripts_dir(tmp_path: Path) -> tuple:
    """A tmp scripts dir whose presentation_job.py records and FORWARDS.

    Records `sys.argv[1:]` into a JSON marker, then hands the same arguments to
    the REAL engine entry in this checkout. `--resume` additionally gets
    `--diagnose-only`, which `__main__.main` honours immediately after the
    manifest pin check -- so the pin verdict is the engine's own, and the test
    never enters the run loop.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "engine_invocations.json"
    (scripts / "presentation_job.py").write_text(
        "import json, pathlib, subprocess, sys\n"
        "MARKER = pathlib.Path(" + repr(str(marker)) + ")\n"
        "REAL = " + repr(str(REAL_ENGINE_ENTRY)) + "\n"
        "REAL_DIR = " + repr(str(SCRIPTS)) + "\n"
        "rows = json.loads(MARKER.read_text()) if MARKER.exists() else []\n"
        "rows.append(list(sys.argv[1:]))\n"
        "MARKER.write_text(json.dumps(rows))\n"
        "args = list(sys.argv[1:])\n"
        "if '--resume' in args:\n"
        "    args.append('--diagnose-only')\n"
        "sys.exit(subprocess.run([sys.executable, REAL] + args,\n"
        "                        cwd=REAL_DIR).returncode)\n",
        encoding="utf-8")
    return scripts, marker


def _rig(monkeypatch, tmp_path):
    """Everything dispatch() insists on before it reaches the F2 gate.

    Each line disarms ONE unrelated launch gate through its own documented
    surface -- none of them is the surface under test, and none is weakened
    for the run: the OCR probe and the capacity probe are box facts, and a
    unit test that depended on this box's tesseract install would be measuring
    the box, not the fix.
    """
    scripts, marker = _interceptor_scripts_dir(tmp_path)
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: scripts)
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.setenv("PRESENTATION_OCR_VERIFY", "0")   # documented rollback
    monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")  # no dispatcher child
    monkeypatch.delenv(AUTO_REPIN_ENV_NAME, raising=False)
    return scripts, marker


def _make_run(tmp_path: Path, *, moved: bool) -> tuple:
    """A parked run pinned to a copy of the canonical manifest.

    moved=True reproduces a fleet roll: the pin is taken, THEN the manifest
    file changes underneath it (manifest_version bumped and re-serialised --
    the same kind of edit a real bump makes). moved=False leaves pin and file
    in agreement.
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
    state = {
        "schema_version": 1,
        "job_id": "pj_test_f02",
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


# ===========================================================================
# 1. THE REGRESSION. Fails on pristine origin/main: one child, exit 7.
# ===========================================================================
def test_a_stale_pin_is_repaired_before_the_resume(monkeypatch, tmp_path):
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)

    rc = launcher.dispatch(str(run), resume=True, background=False)

    rows = _rows(marker)
    assert rc != EXIT_MANIFEST_MISMATCH, (
        "the resume still died on the manifest pin -- nothing re-pinned it. "
        f"engine invocations: {rows}")
    assert rc == 0, (rc, rows)

    # The cure ran FIRST, and it was the engine's own documented one.
    assert len(rows) == 2, rows
    assert "--repin" in rows[0] and "--run-dir" in rows[0], rows
    assert str(run) in rows[0], rows
    assert "--resume" in rows[1] and "--repin" not in rows[1], rows

    # The pin actually moved, and both shas are on the record.
    st = _state(run)
    assert st["manifest_sha256"] == _sha(man)
    assert st["manifest_sha256_prev"] == pinned
    hist = st["manifest_repin_history"]
    assert len(hist) == 1 and hist[0]["old_sha256"] == pinned
    assert hist[0]["new_sha256"] == _sha(man)

    # ...and it is recorded as AUTOMATIC, not as an operator running --repin.
    auto = st["auto_repin_history"]
    assert len(auto) == 1, auto
    assert auto[0]["by"] == "launcher.auto_repin_gate"
    assert auto[0]["old_sha256"] == pinned
    assert auto[0]["new_sha256"] == _sha(man)

    log = run.joinpath(*REPIN_LOG)
    assert log.is_file(), "no repin log -- the repin left no evidence"
    assert "auto-repin rc=0" in log.read_text(encoding="utf-8")


# ===========================================================================
# 2. A MATCHING PIN IS NOT AN EXCUSE TO REPIN
# ===========================================================================
def test_an_unmoved_manifest_spawns_no_repin_at_all(monkeypatch, tmp_path):
    """Every poller tick hits this path. It must cost one child, not two, and
    it must not touch state."""
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=False)

    rc = launcher.dispatch(str(run), resume=True, background=False)

    rows = _rows(marker)
    assert rc == 0, (rc, rows)
    assert len(rows) == 1 and "--resume" in rows[0], rows
    st = _state(run)
    assert st["manifest_sha256"] == pinned
    assert "manifest_repin_history" not in st
    assert "auto_repin_history" not in st
    assert not run.joinpath(*REPIN_LOG).exists()


# ===========================================================================
# 3. THE DOCUMENTED ROLLBACK IS REAL
# ===========================================================================
def test_rollback_env_restores_the_pre_fix_death(monkeypatch, tmp_path):
    """PRESENTATION_AUTO_REPIN=0 -> exactly pristine main: no repin child, and
    the engine dies on the pin. A rollback that does not restore the old
    behaviour is not a rollback."""
    scripts, marker = _rig(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTO_REPIN_ENV_NAME, "0")
    run, man, pinned = _make_run(tmp_path, moved=True)

    rc = launcher.dispatch(str(run), resume=True, background=False)

    rows = _rows(marker)
    assert rc == EXIT_MANIFEST_MISMATCH, (rc, rows)
    assert len(rows) == 1 and "--resume" in rows[0], rows
    assert _state(run)["manifest_sha256"] == pinned
    assert not run.joinpath(*REPIN_LOG).exists()


# ===========================================================================
# 4. A REPIN THAT FAILS REFUSES THE DISPATCH -- IT NEVER SPAWNS A CORPSE
# ===========================================================================
def _unparseable_manifest_run(tmp_path):
    """Pin taken over valid JSON, then the file is replaced by something the
    engine cannot load. The sha moved (so F2 fires) and cmd_repin cannot
    succeed (Manifest() dies EXIT_MANIFEST_MISMATCH) -- the shape a truncated
    or half-written manifest actually has mid-roll."""
    run, man, pinned = _make_run(tmp_path, moved=False)
    man.write_text('{"manifest_version": 67, "phases": [', encoding="utf-8")
    return run, man, pinned


def test_a_failed_repin_refuses_and_nothing_is_spawned(monkeypatch, tmp_path):
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _unparseable_manifest_run(tmp_path)

    rc = launcher.dispatch(str(run), resume=True, background=False)

    rows = _rows(marker)
    assert rc == launcher.DISPATCH_REPIN_FAILED, (rc, rows)
    # The repin was attempted; the ENGINE never was.
    assert len(rows) == 1, rows
    assert "--repin" in rows[0], rows
    assert all("--resume" not in r for r in rows), rows
    assert _state(run)["manifest_sha256"] == pinned, "a failed repin moved the pin"
    log = run.joinpath(*REPIN_LOG)
    assert log.is_file()
    assert "auto-repin rc=0" not in log.read_text(encoding="utf-8")


def test_the_refusal_reaches_the_poller_as_a_non_zero_exit(monkeypatch, tmp_path):
    """The poller reads `${PIPESTATUS[0]}` from
    `python3 -m presentation_job.launcher --resume ...` and counts rc 0 as a
    launch. A repin refusal must therefore leave main() with its OWN non-zero
    code -- not 0, and not indistinguishable from a spawn."""
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _unparseable_manifest_run(tmp_path)

    rc = launcher.main(["--resume", "--run-dir", str(run)])

    assert rc == launcher.EXIT_REPIN_FAILED, (rc, _rows(marker))
    assert rc != 0
    assert all("--resume" not in r for r in _rows(marker)), _rows(marker)


# ===========================================================================
# 5. UNDETERMINED IS SAID OUT LOUD, AND CHANGES NOTHING
# ===========================================================================
@pytest.mark.parametrize("break_it,expect", [
    ("no_state", "no state.json"),
    ("no_pin", "no manifest_sha256"),
    ("corrupt_state", "state.json unreadable"),
    ("manifest_gone", "is gone"),
])
def test_an_undetermined_pin_is_named_and_never_acted_on(monkeypatch, tmp_path,
                                                         capsys, break_it, expect):
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)
    if break_it == "no_state":
        (run / "state.json").unlink()
    elif break_it == "no_pin":
        st = _state(run)
        del st["manifest_sha256"]
        (run / "state.json").write_text(json.dumps(st), encoding="utf-8")
    elif break_it == "corrupt_state":
        (run / "state.json").write_text("{not json", encoding="utf-8")
    elif break_it == "manifest_gone":
        man.unlink()

    verdict = launcher.auto_repin_gate(run, scripts / "presentation_job.py",
                                       scripts)

    assert verdict is None, "an UNDETERMINED pin refused a dispatch"
    out = capsys.readouterr()
    text = out.out + out.err
    assert "auto-repin skipped" in text, text[-800:]
    assert expect in text, text[-800:]
    assert _rows(marker) == [], "a child ran on an UNDETERMINED pin"


# ===========================================================================
# 6. --new NEVER REPINS (there is no pin yet, and F2 is a resume-path gate)
# ===========================================================================
def test_a_new_launch_never_repins(monkeypatch, tmp_path):
    scripts, marker = _rig(monkeypatch, tmp_path)
    run, man, pinned = _make_run(tmp_path, moved=True)

    launcher.dispatch(str(run), client="acme", deck_type="standard",
                      resume=False, background=False)

    rows = _rows(marker)
    assert all("--repin" not in r for r in rows), rows
    assert _state(run)["manifest_sha256"] == pinned
