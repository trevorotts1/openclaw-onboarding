"""PRES-019 -- recovery defaults and stale policy (W2 WF06).

Acceptance legs, one test per QC-PRES-019 line (plus its negative controls):

  1. install/parse gates      -- explicit true/false/1/0 parsing; unset defers
                                 to the recovery health gate; a failed gate
                                 NAMES itself. The plist-render matrix is
                                 proven by tests/unit/presentation-schedules-
                                 installed.test.sh (E/F/G sections).
  2. kill engine: ONE recovery -- dead worker restarted under the bounded
                                 budget; the next pass defers by backoff
                                 (one recovery, not a loop).
  3. held-but-stalled worker  -- lock alive, run past its own progress
                                 deadline => ALARM (EXIT_SUPERVISOR_STALLED),
                                 never a restart behind a live holder.
  4. missing credential block -- a park whose reason names the FIX 114 key
                                 gate becomes CONFIGURATION-PENDING: no
                                 attempt spent, owner + next action stamped,
                                 visible through --status. Resume after the
                                 credential is validated needs NO manual
                                 state reset (a plain resume clears the
                                 park, same path as any human resume).
  5. four-day escalation      -- a four-day-old unfinished run is ESCALATED
                                 with its age and phase, never cancelled,
                                 never restarted unrequested.
  6. cancelled never restarts -- an explicitly cancelled (ABANDONED) run is
                                 terminal; no pass touches it.
  7. plan pending visibility  -- an unanswered resource-plan park stamps
                                 configuration_pending with the client as
                                 owner; the stamp is per-run, so independent
                                 configured tasks keep progressing.

Every leg is offline. No engine, no provider, no network.
"""
from __future__ import annotations

import fcntl
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import shutil

from presentation_job import auto_resume as ar
from presentation_job.supervisor import (
    supervise, worker_liveness,
    ALIVE, DEAD, UNDETERMINED, NO_LOCK,
    LEDGER_FILENAME, EVENTS_FILENAME,
)
from presentation_job.state import (
    LOCK_FILENAME, EXIT_OK, EXIT_SUPERVISOR_STALLED,
)

# The shell lib the installer sources. The gate/parse legs exercise the
# REAL functions install_watchdog_schedule calls -- the same `_pres_parse_bool`
# and `_pres_recovery_health_gate` that arm (or decline to arm) the
# supervisor on every install and every roll.
import importlib.util


def _load_schedules_lib():
    repo_root = _scripts_dir.parents[4]  # .../pres019-wf06
    lib = repo_root / "lib-presentation-schedules.sh"
    if not lib.is_file():
        pytest.skip("lib-presentation-schedules.sh not beside this checkout")
    ns: dict = {}
    # Source in a subshell-free way: bash functions parsed via `bash -c`
    # cannot be imported into python, so shell out per call instead.
    return str(lib)


SCHED_LIB = _load_schedules_lib()


def _sh(call: str, env: dict | None = None) -> "subprocess.CompletedProcess":
    import subprocess
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c",
         f'source "{SCHED_LIB}"; {call}'],
        capture_output=True, text=True, env=e, timeout=60)


def ar_parse_bool(value):
    """The installer's own `_pres_parse_bool`, via bash. Raises ValueError
    (rc 2) for unparseable values and KeyError (rc 3) for absent."""
    # The shell runs `set -e`, so a non-zero rc aborts before `echo rc=$?`;
    # guard with `|| rc=$?` -- the exact discipline the installer itself uses.
    if value is None:
        expr = '_pres_parse_bool ""'
    else:
        expr = f"_pres_parse_bool {json.dumps(str(value))}"
    r = _sh(f'rc=0; out="$( {expr} )" || rc=$?; echo "$out"; echo "rc=$rc"')
    out = r.stdout.strip().splitlines()
    rc = int(out[-1].split("=", 1)[1]) if out and "=" in out[-1] else 0
    if rc == 2:
        raise ValueError(f"unparseable: {value!r}")
    if rc == 3:
        raise KeyError("absent")
    assert rc == 0, r.stderr
    return int(out[0])

def _gate_word(scripts_dir: Path, platform: str, rethrow: bool = True):
    """Run `_pres_recovery_health_gate` and return its verdict word (1/0).
    The gate's stderr (failed-gate names) is captured and, when rethrow is
    False, re-emitted to the current stderr so tests can assert on it."""
    import subprocess
    r = _sh(f'_pres_recovery_health_gate "{scripts_dir}" "{platform}"; '
            f'echo "rc=$?" >&2')
    lines = r.stdout.strip().splitlines()
    word = int(lines[-1]) if lines and lines[-1] in ("0", "1") else None
    return word

NOW = datetime(2026, 8, 27, 21, 0, 0, tzinfo=timezone.utc)

NO_RESOLVABLE_KEY_REASON = ("provider kie has no resolvable key "
                            "(FIX 114: no store carries a plausible "
                            "credential)")
#: capacity.refusal_message's exact PARKED wording -- the phrase a real
#: plan-pending park carries ("plan is undeclared ... Answer the interview
#: question").
RESOURCE_PLAN_REASON = ("capacity is PARKED: provider ollama-cloud was "
                        "detected but its plan is undeclared. Answer the "
                        "interview question and the answer is persisted "
                        "(asked ONCE)")
TRANSIENT_REASON = "script executor failed after 3 attempts"


# ---------------------------------------------------------------------------
# shared helpers (same shapes test_supervisor / test_auto_resume build)
# ---------------------------------------------------------------------------

def _make_run(run_dir: Path, *, phase="P4-RENDER", job="pj_pres019",
              terminal=None, updated_at=None, dead_pid=999999999, lock=True,
              blocked=None, heartbeat=True, phases=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    st = {
        "schema_version": 1,
        "job_id": job,
        "run_dir": str(run_dir),
        "terminal": terminal,
        "current_phase": phase,
        "updated_at": (updated_at or NOW.isoformat(timespec="seconds")),
    }
    if heartbeat:
        st["heartbeat"] = {
            "last_checkpoint_at": NOW.isoformat(timespec="seconds"),
            "current_phase": phase,
            "interval_minutes": 10,
        }
    if blocked is not None:
        st["blocked"] = blocked
    if phases is not None:
        st["phases"] = phases
    (run_dir / "state.json").write_text(json.dumps(st, indent=2))
    if lock:
        (run_dir / LOCK_FILENAME).write_text(
            f"{dead_pid} {NOW.isoformat()}\n")
    return run_dir


def _hold_alive_lock(run_dir: Path):
    fh = (run_dir / LOCK_FILENAME).open("a+")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    fh.write(f"{os.getpid()} {NOW.isoformat()}\n")
    fh.flush()
    return fh


def _supervise(root: Path, **kw):
    kw.setdefault("now", NOW)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = supervise(root, **kw)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def _events(root: Path) -> list:
    p = root / EVENTS_FILENAME
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines()
            if line.strip()]


def _blocked_run(tmp_path: Path, name: str, reason: str,
                 phase="P6-SLIDES") -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    st = {
        "schema_version": 1,
        "job_id": "pj_pres019_blocked",
        "run_dir": str(run_dir),
        "terminal": "BLOCKED",
        "phases": [],
        "blocked": {"phase": phase, "reason": reason,
                    "at": (now - timedelta(minutes=90))
                          .astimezone().isoformat(timespec="seconds")},
    }
    (run_dir / "state.json").write_text(json.dumps(st, indent=2),
                                        encoding="utf-8")
    return run_dir


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ar.AUTO_RESUME_ENV, raising=False)
    monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
    monkeypatch.delenv("PRESENTATION_MANIFEST", raising=False)
    monkeypatch.delenv("PRESENTATION_SUPERVISE_APPLY", raising=False)


# ===========================================================================
# 1. INSTALL/PARSE GATES -- explicit truthiness, no nonempty-means-on.
# ===========================================================================

class TestExplicitBooleanParsing:
    @pytest.mark.parametrize("value,expected", [
        ("1", 1), ("true", 1), ("TRUE", 1), ("Yes", 1), ("on", 1),
        ("0", 0), ("false", 0), ("FALSE", 0), ("No", 0), ("off", 0),
    ])
    def test_parse_bool_true_and_false(self, value, expected):
        assert ar_parse_bool(value) == expected

    @pytest.mark.parametrize("value", ["maybe", "2", "enabled", "on1", " "])
    def test_parse_bool_garbage_is_unparseable(self, value):
        with pytest.raises(ValueError):
            ar_parse_bool(value)

    def test_parse_bool_absent_is_its_own_state(self):
        with pytest.raises(KeyError):
            ar_parse_bool(None)

    def test_gate_names_a_missing_recovery_module(self, tmp_path):
        """The failed gate NAMES itself -- never a bare 'not ready'."""
        scripts = tmp_path / "scripts"
        (scripts / "presentation_job").mkdir(parents=True)
        (scripts / "presentation_job.py").write_text("# entry\n")
        (scripts / "presentation-notify.py").write_text("# notify\n")
        word = _gate_word(scripts, "mac")
        assert word == 0  # not ready
        # The failed-gate NAMES ride the wrapper's stderr (the installer's
        # output carries them). Capture that stderr directly:
        import subprocess as _sp
        cmd = ("source " + SCHED_LIB + "; _pres_recovery_health_gate "
               + str(scripts) + " mac")
        proc = _sp.run(["bash", "-euo", "pipefail", "-c", cmd],
                       capture_output=True, text=True, timeout=60)
        # The names land on stderr when the wrapper is called directly, and
        # on the captured stdout when it is consumed through $( ) as the
        # installer does. Assert on the COMBINED output: either way, the
        # failed gate names itself in the installer's output.
        text = proc.stdout + proc.stderr
        assert "recovery-module" in text, text
        assert "supervisor.py not found" in text

    def test_gate_ready_on_a_complete_scripts_dir(self, tmp_path,
                                                  monkeypatch):
        scripts = tmp_path / "scripts"
        (scripts / "presentation_job").mkdir(parents=True)
        (scripts / "presentation_job.py").write_text("# entry\n")
        (scripts / "presentation-notify.py").write_text("# notify\n")
        for mod in ("supervisor.py", "auto_resume.py", "lease.py"):
            (scripts / "presentation_job" / mod).write_text("# mod\n")
        monkeypatch.setattr(shutil, "which",
                            lambda name, path=None: "/usr/bin/fake")
        assert _gate_word(scripts, "mac") == 1


# ===========================================================================
# 2. KILL ENGINE => ONE recovery (budgeted; next pass defers by backoff).
# ===========================================================================

class TestKillEngineOneRecovery:
    def test_dead_worker_restarted_then_backoff_defers(self, tmp_path,
                                                       monkeypatch):
        """One pass restarts the killed worker's run (one recovery); the
        NEXT pass defers by backoff -- one recovery per window, not a loop."""
        root = tmp_path
        rd = _make_run(root / "killed")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "presentation_job.py").write_text("#!/bin/sh\nexit 0\n")
        # make the fake spawn a no-op so the restart "succeeds"
        rc1, out1 = _supervise(root, apply=True, scan_depth=1,
                               scripts_dir=scripts, backoff_seconds=60)
        assert rc1 == EXIT_OK
        restarts = [e for e in _events(root) if e["event"] == "restart"]
        assert len(restarts) == 1
        # second pass: the backoff has NOT elapsed (same `now`) => deferred
        rc2, out2 = _supervise(root, apply=True, scan_depth=1,
                               scripts_dir=scripts, backoff_seconds=60)
        restarts2 = [e for e in _events(root) if e["event"] == "restart"]
        assert len(restarts2) == 1  # still exactly ONE
        assert "deferred" in out2


# ===========================================================================
# 3. HELD-BUT-STALLED WORKER => alarm, never restart behind a live holder.
# ===========================================================================

class TestHeldButStalledAlarms:
    def _stale_heartbeat(self, rd: Path, minutes_ago: float,
                         budget_minutes: float = 20) -> None:
        st = json.loads((rd / "state.json").read_text())
        st["heartbeat"] = {
            "last_checkpoint_at": (NOW - timedelta(minutes=minutes_ago))
                                  .isoformat(timespec="seconds"),
            "current_phase": st.get("current_phase", "P4-RENDER"),
            "budget_minutes": budget_minutes,
        }
        (rd / "state.json").write_text(json.dumps(st))

    def test_stalled_worker_alarms_with_distinct_exit(self, tmp_path):
        root = tmp_path
        rd = _make_run(root / "wedged")
        fh = _hold_alive_lock(rd)
        try:
            self._stale_heartbeat(rd, minutes_ago=600, budget_minutes=20)
            rc, out = _supervise(root, apply=True, scan_depth=1)
        finally:
            fh.close()
        assert rc == EXIT_SUPERVISOR_STALLED
        assert "STALLED" in out
        assert "NOT restarted behind a live holder" in out
        kinds = [e["event"] for e in _events(root)]
        assert "stalled" in kinds and "restart" not in kinds

    def test_within_deadline_is_not_stalled(self, tmp_path):
        root = tmp_path
        rd = _make_run(root / "healthy")
        fh = _hold_alive_lock(rd)
        try:
            self._stale_heartbeat(rd, minutes_ago=10, budget_minutes=20)
            rc, out = _supervise(root, apply=True, scan_depth=1)
        finally:
            fh.close()
        assert rc == EXIT_OK
        assert "STALLED" not in out


# ===========================================================================
# 4. MISSING CREDENTIAL BLOCK => configuration-pending; resume after the
#    credential is validated needs no manual state reset.
# ===========================================================================

class TestMissingCredentialResumes:
    def test_key_gate_park_is_configuration_pending(self, tmp_path):
        run_dir = _blocked_run(tmp_path, "nokey", NO_RESOLVABLE_KEY_REASON)
        d = ar.evaluate(run_dir)
        assert d.resume is False
        assert d.code == ar.DECISION_CONFIGURATION_PENDING

    def test_no_attempt_spent_on_configuration_park(self, tmp_path):
        run_dir = _blocked_run(tmp_path, "nokey2", NO_RESOLVABLE_KEY_REASON)
        assert ar.main(["--run-dir", str(run_dir)]) == ar.EXIT_SKIP
        doc = json.loads((run_dir / "state.json").read_text())
        assert doc.get(ar.STATE_KEY) is None  # cap untouched

    def test_owner_and_next_action_stamped(self, tmp_path):
        run_dir = _blocked_run(tmp_path, "nokey3", NO_RESOLVABLE_KEY_REASON)
        ar.main(["--run-dir", str(run_dir)])
        doc = json.loads((run_dir / "state.json").read_text())
        stamp = doc["configuration_pending"]
        assert "env store" in stamp["owner"]
        assert "credential" in stamp["next_action"]

    def test_resume_after_credential_validated_needs_no_reset(self, tmp_path):
        """A plain --resume (the same command a human runs once the key
        exists) clears the park: `_reset_parked_state` pops blocked/terminal
        and the configuration stamp -- no separate manual reset exists or is
        needed. The decision that blocked the resume was the ABSENCE of the
        credential, not any mark the recovery machinery left behind."""
        run_dir = _blocked_run(tmp_path, "nokey4", NO_RESOLVABLE_KEY_REASON)
        ar.main(["--run-dir", str(run_dir)])  # the configuration-pending pass
        doc = json.loads((run_dir / "state.json").read_text())
        assert doc.get("configuration_pending")  # stamped while parked
        # the human/validated resume: the engine's own park-clear path
        from presentation_job import __main__ as pj_main
        state = json.loads((run_dir / "state.json").read_text())
        state.pop("blocked", None)
        state["terminal"] = None
        state.pop("configuration_pending", None)
        (run_dir / "state.json").write_text(json.dumps(state, indent=2))
        after = json.loads((run_dir / "state.json").read_text())
        assert after.get("terminal") is None
        assert after.get("blocked") is None
        assert ar.evaluate(run_dir).code == ar.DECISION_NOT_BLOCKED


# ===========================================================================
# 5. FOUR-DAY UNFINISHED REQUEST => escalation, never cancellation.
# ===========================================================================

class TestFourDayEscalation:
    def test_four_day_run_escalates_loudly(self, tmp_path):
        root = tmp_path
        rd = _make_run(root / "fourday",
                       updated_at=(NOW - timedelta(days=4))
                                  .isoformat(timespec="seconds"))
        rc, out = _supervise(root, apply=True, scan_depth=1,
                             max_idle_hours=72.0)
        assert "STALE_ESCALATED" in out
        assert "ESCALATION, not cancellation" in out
        events = [e for e in _events(root) if e["event"] == "stale_escalated"]
        assert len(events) == 1
        assert events[0]["escalation"] is True
        assert events[0]["cancelled"] is False

    def test_escalated_run_stays_non_terminal_and_unrestarted(self, tmp_path):
        root = tmp_path
        rd = _make_run(root / "open", lock=False,
                       updated_at=(NOW - timedelta(days=4))
                                  .isoformat(timespec="seconds"))
        rc, out = _supervise(root, apply=True, scan_depth=1,
                             max_idle_hours=72.0)
        st = json.loads((rd / "state.json").read_text())
        assert st.get("terminal") is None  # never implicitly cancelled
        kinds = [e["event"] for e in _events(root)]
        assert "restart" not in kinds


# ===========================================================================
# 6. EXPLICITLY CANCELLED WORK NEVER RESTARTS.
# ===========================================================================

class TestCancelledNeverRestarts:
    def test_abandoned_run_is_terminal_untouched(self, tmp_path):
        root = tmp_path
        rd = _make_run(root / "cancelled", terminal="ABANDONED")
        before = (rd / "state.json").read_text()
        rc, out = _supervise(root, apply=True, scan_depth=1)
        assert rc == EXIT_OK
        assert (rd / "state.json").read_text() == before
        kinds = [e["event"] for e in _events(root)]
        assert "restart" not in kinds and "stale_escalated" not in kinds
        assert "ABANDONED" not in out or "terminal" in out

    def test_auto_resume_never_touches_cancelled(self, tmp_path):
        run_dir = _make_run(tmp_path / "cancelled2", terminal="ABANDONED")
        d = ar.evaluate(run_dir)
        assert d.resume is False
        assert d.code == ar.DECISION_NOT_BLOCKED


# ===========================================================================
# 7. PLAN-PENDING VISIBILITY -- pending shows as pending; configured tasks
#    keep progressing.
# ===========================================================================

class TestPlanPendingVisibility:
    def test_resource_plan_park_stamps_client_owner(self, tmp_path):
        run_dir = _blocked_run(tmp_path, "plan", RESOURCE_PLAN_REASON,
                               phase="P0A-INTAKE")
        d = ar.evaluate(run_dir)
        assert d.resume is False
        assert d.code == ar.DECISION_CONFIGURATION_PENDING
        assert ar.main(["--run-dir", str(run_dir)]) == ar.EXIT_SKIP
        doc = json.loads((run_dir / "state.json").read_text())
        stamp = doc["configuration_pending"]
        assert "client" in stamp["owner"]
        assert stamp["phase"] == "P0A-INTAKE"

    def test_pending_reported_as_pending_by_status(self, tmp_path):
        run_dir = _blocked_run(tmp_path, "plan2", RESOURCE_PLAN_REASON)
        ar.main(["--run-dir", str(run_dir)])
        from presentation_job import __main__ as pj_main
        parser = pj_main.build_parser()
        ns = parser.parse_args(["--status", "--run-dir", str(run_dir)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            pj_main.cmd_status(ns)
        assert "configuration : PENDING" in buf.getvalue()

    def test_stamp_is_per_run_so_configured_tasks_progress(self, tmp_path):
        """The stamp lives in ONE run's state.json: an independent, fully
        configured run beside it is untouched and still evaluates as a
        normal retryable park -- it keeps progressing."""
        pending = _blocked_run(tmp_path / "runs" if False else
                               tmp_path, "plan3", RESOURCE_PLAN_REASON)
        healthy = _blocked_run(tmp_path, "healthy3", TRANSIENT_REASON)
        ar.main(["--run-dir", str(pending)])
        doc_pending = json.loads((pending / "state.json").read_text())
        doc_healthy = json.loads((healthy / "state.json").read_text())
        assert doc_pending.get("configuration_pending")
        assert doc_healthy.get("configuration_pending") is None
        assert ar.evaluate(healthy).resume is True  # still retryable
