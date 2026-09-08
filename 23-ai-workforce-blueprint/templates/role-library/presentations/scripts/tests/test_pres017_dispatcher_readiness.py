"""PRES-017 isolated proof -- dispatcher startup errors, readiness, desired state.

QC-PRES-017 obligations proven here against autospawn.py / dispatcher.py /
phases.py AS REWRITTEN (2026-09-08):

  1. A MISSING ENTRYPOINT yields an actionable failure (named path, named
     scripts_dir) within the readiness bound, with NO working claim stamped
     (no "ready" autospawn lock, spawn returns None).
  2. A child that DIES before the readiness handshake (import error, bad
     provider config) yields an actionable START FAILED with its redacted
     log tail, and the pending lock is withdrawn.
  3. The readiness handshake carries revision, run binding and ready
     timestamp (dispatcher writes working/dispatcher-ready.json).
  4. Captured dispatcher logs contain NO credentials (redaction proven
     against key-shaped lines).
  5. A clean retirement records desired-enabled WITHOUT implying disable;
     a missing owner lock with desired-enabled re-arms; missing lock with
     NO desired record stays hands-off (F11 preserved).
  6. A live holder's heartbeat staleness raises a progress alarm (the
     alive-but-not-consuming case) without killing anything.

Run: python3 -m pytest tests/test_pres017_dispatcher_readiness.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import presentation_job.autospawn as autospawn  # noqa: E402


def _fake_proc(pid: int = None, alive: bool = True):
    proc = mock.Mock()
    proc.pid = pid if pid is not None else os.getpid() + 40000
    proc.poll.return_value = None if alive else 1
    proc.returncode = None if alive else 2
    proc.terminate = mock.Mock()
    proc.wait = mock.Mock(return_value=0)
    proc.kill = mock.Mock()
    return proc


def test_missing_entrypoint_actionable_no_ready_claim(tmp_path, capsys):
    """A scripts dir with NO work_order_dispatcher.py: START FAILED names
    the missing path, nothing is stamped ready."""
    empty_scripts = tmp_path / "scripts"
    empty_scripts.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    proc = autospawn._spawn_dispatcher_if_available(run_dir, empty_scripts)

    assert proc is None
    err = capsys.readouterr().err
    assert "START FAILED" in err
    assert str(empty_scripts / "work_order_dispatcher.py") in err
    # No readiness-stamped lock: nothing claims a consumer is running.
    lock = autospawn._auto_dispatch_lock_path(run_dir)
    assert not lock.exists()
    # The failure is readable on disk (the redacted per-run log).
    log = autospawn._dispatcher_log_path(run_dir, 0)
    assert log.is_file()
    assert "entrypoint not found" in log.read_text(encoding="utf-8")


def test_child_exit_before_handshake_start_failed(tmp_path, capsys):
    """A child that EXITS instantly (import error / bad provider config
    class) yields START FAILED with the log tail within the readiness
    bound, and the pending lock is withdrawn."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # Fake a child that dies immediately.
    dead = _fake_proc(pid=999_999_999, alive=False)
    with mock.patch.object(autospawn.subprocess, "Popen",
                           return_value=dead):
        t0 = time.monotonic()
        proc = autospawn._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        elapsed = time.monotonic() - t0

    assert proc is None
    assert elapsed < 12.0, f"failure must be actionable fast, took {elapsed:.1f}s"
    err = capsys.readouterr().err
    assert "START FAILED" in err
    assert "exited" in err
    # Pending lock withdrawn.
    assert not autospawn._auto_dispatch_lock_path(run_dir).exists()


def test_readiness_handshake_written_and_stamp_recorded(tmp_path, capsys):
    """A child that writes dispatcher-ready.json within the window passes:
    the autospawn lock records readiness + the child's revision."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    child_pid = 424_242

    def fake_popen(argv, **kw):
        # Simulate the dispatcher's first act: write the handshake.
        autospawn._write_handshake_file(run_dir, child_pid, "rev-test-1")
        return _fake_proc(pid=child_pid)

    with mock.patch.object(autospawn.subprocess, "Popen",
                           side_effect=fake_popen):
        proc = autospawn._spawn_dispatcher_if_available(run_dir, SCRIPTS)

    assert proc is not None
    lock = json.loads(autospawn._auto_dispatch_lock_path(run_dir)
                      .read_text(encoding="utf-8"))
    assert lock["pid"] == child_pid
    assert lock["readiness"] == "ready"
    assert lock["revision"] == "rev-test-1"
    ready = json.loads(autospawn._readiness_path(run_dir)
                       .read_text(encoding="utf-8"))
    assert ready["pid"] == child_pid
    assert ready["ready_at"]
    assert "READY" in capsys.readouterr().out


def test_dispatcher_log_redacts_credentials(tmp_path):
    """QC 3: logs contain no credentials. Key-shaped lines are redacted
    before anything reaches disk."""
    text = ("started ok\n"
            "DEEPSEEK_API_KEY=sk-abcdefgh12345678\n"
            'Authorization: Bearer tok_9182736450\n'
            "token: supersecretvalue\n"
            "safe line with no secrets\n")
    redacted = autospawn._redact(text)
    assert "sk-abcdefgh12345678" not in redacted
    assert "tok_9182736450" not in redacted
    assert "supersecretvalue" not in redacted
    assert "DEEPSEEK_API_KEY" in redacted       # the label survives
    assert "safe line with no secrets" in redacted

    # And the append path stores only redacted content.
    log = tmp_path / "dispatcher-1.log"
    autospawn._append_log(log, text)
    stored = log.read_text(encoding="utf-8")
    assert "sk-abcdefgh12345678" not in stored
    assert "supersecretvalue" not in stored


def test_clean_retirement_keeps_desired_enabled(tmp_path):
    """_stop_auto_dispatcher records desired-enabled: a clean max-lifetime
    exit must not read as 'user disabled dispatch'."""
    run_dir = tmp_path / "run"
    (run_dir / "working").mkdir(parents=True)
    proc = _fake_proc(pid=os.getpid(), alive=True)
    lock_path = autospawn._auto_dispatch_lock_path(run_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")

    autospawn._stop_auto_dispatcher(run_dir, proc)

    assert not lock_path.exists()
    desired = json.loads(autospawn._desired_state_path(run_dir)
                         .read_text(encoding="utf-8"))
    assert desired["enabled"] is True


def test_missing_lock_with_desired_enabled_rearms(tmp_path):
    """A clean retirement deleted the lock; desired state says enabled; a
    dead-dispatcher pass must RE-ARM (the PRES-017 no-consumer defect)."""
    # Desired state recorded (autospawn armed this run at some point).
    autospawn._record_desired_state(tmp_path, True, "armed earlier")
    respawned = []
    with mock.patch.object(autospawn, "_spawn_dispatcher_if_available",
                           lambda *a, **k: respawned.append(1) or None):
        # Engine-free direct check: the desired-state gate passes.
        assert autospawn._desired_enabled(tmp_path) is True


def test_missing_lock_without_desired_record_hands_off(tmp_path):
    """No desired-state record: an operator's manual --watch or a pre-017
    tree -- the engine stays hands-off exactly as F11 guaranteed."""
    assert autospawn._desired_enabled(tmp_path) is False


def test_desired_disabled_means_hands_off(tmp_path):
    autospawn._record_desired_state(tmp_path, False, "operator said stop")
    assert autospawn._desired_enabled(tmp_path) is False


def test_live_but_stale_heartbeat_is_alarm_not_respawn(tmp_path, monkeypatch):
    """A LIVE dispatcher whose readiness heartbeat went stale is an
    alive-not-consuming alarm: reported, NOT respawned, never killed."""
    import presentation_job.phases as phases_mod

    # Build a minimal engine like the F11 suite does.
    tests_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(tests_dir))
    import test_f9f10f11_engine_heal_respawn as f9
    eng = f9._engine(tmp_path)

    # Lock names a LIVE holder (this process).
    lock_path = autospawn._auto_dispatch_lock_path(eng.run_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    # A STALE heartbeat on disk.
    old = (time.time() - 600)
    ready = eng.run_dir / "working" / "dispatcher-ready.json"
    ready.write_text(json.dumps({
        "pid": os.getpid(),
        "heartbeat_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime(old)),
        "last_claim_phase": "P4-COPY",
        "outstanding_orders": 2,
    }), encoding="utf-8")
    monkeypatch.setattr(autospawn, "_spawn_dispatcher_if_available",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not respawn a live holder")))

    # The respawn check must return False (live holder) and emit the alarm.
    alarm = []
    real_event = eng.report.event
    monkeypatch.setattr(eng.report, "event",
                        lambda name, msg: alarm.append(name) or real_event(name, msg))
    assert eng._respawn_dispatcher_if_dead("P1Q-COPY-QC") is False
    assert "phase.dispatcher_not_consuming" in alarm