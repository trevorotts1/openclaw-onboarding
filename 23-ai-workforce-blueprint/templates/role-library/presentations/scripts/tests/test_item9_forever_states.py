"""Item 9 -- forever-state rescue coverage (canonical engine).

Four behaviours, each pinned with its negative case:

  (a) the watchdog FLAGS terminal-BLOCKED runs and heartbeat-less
      non-terminal runs instead of silently skipping them -- a recorded
      park past the auto-resume window is PARKED-FOR-HUMAN, a park with
      no record at all is ORPHANED-BLOCKED (different operator messages),
      and a healthy running job with a fresh heartbeat is never flagged;
  (b) the supervisor's sweep reclaims a phase left `running` by a dead
      engine (PD-TEST-155's class) mid-run, through the launch path's own
      readmit mechanism, marked FAILED so its subtree is released -- and
      never reclaims a phase whose worker is alive, unadjudicable, or
      owned by a live engine;
  (d) heal caps are cross-invocation: attempts persisted in the phase's
      heal_events inside the rolling 24h window count against the same
      caps, and attempts older than the window refill the budget;
  (e) dead-lettered notifications surface in the watchdog's per-pass
      report and in --status, not only in state["dead_letter"].

No real sleeps, no network, no real engine spawns (the supervisor restart
path is pointed at an empty scripts dir so its spawn fails
deterministically, exactly like test_supervisor.py's budget tests).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.watchdog import watchdog, FOREVER_FLAG_AGE_HOURS
from presentation_job.supervisor import supervise, EVENTS_FILENAME
from presentation_job.state import (
    StateStore, LOCK_FILENAME, EXIT_OK, EXIT_EXECUTOR_FAILED, EXIT_GATE_BLOCKED,
    utcnow,
)
from presentation_job.manifest import Manifest
from presentation_job import heal
from presentation_job.heal import rung2_regenerate, rung3_alt_route
from presentation_job.phases import Engine, _phase_terminal_bad
from presentation_job import dispatcher as _dispatcher


NOW = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _capture(fn, *args, **kwargs):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = fn(*args, **kwargs)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# (a) + (e): watchdog flags
# ---------------------------------------------------------------------------

def _wd_state(run_dir: Path, **over) -> dict:
    st = {
        "schema_version": 1,
        "job_id": "pj_" + run_dir.name,
        "run_dir": str(run_dir),
        "terminal": None,
        "current_phase": "P1-INTAKE",
        "phases": [],
        "heartbeat": {},
    }
    st.update(over)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(st, indent=2))
    return st


def _escalations(root: Path) -> list:
    p = root / "watchdog-escalations.jsonl"
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


class TestWatchdogBlockedFlags:
    def test_parked_for_human_flagged_after_window(self, tmp_path):
        rd = tmp_path / "parked"
        old = _iso(NOW - timedelta(hours=72))
        _wd_state(rd, terminal="BLOCKED", updated_at=old,
                  blocked={"phase": "P9-OWNER-GATE",
                           "reason": "owner decision: waiver approval pending",
                           "at": old})
        before = _sha(rd / "state.json")
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "PARKED-FOR-HUMAN" in out
        assert "P9-OWNER-GATE" in out
        assert "awaiting a human decision" in out
        assert "ORPHANED-BLOCKED" not in out
        esc = _escalations(tmp_path)
        assert [e["kind"] for e in esc] == ["blocked_parked_for_human"]
        assert esc[0]["record"] == "escalation"
        assert esc[0]["age_hours"] >= 71.9
        # flagging is never a state mutation
        assert _sha(rd / "state.json") == before

    def test_recent_park_inside_window_not_flagged(self, tmp_path):
        rd = tmp_path / "freshpark"
        recent = _iso(NOW - timedelta(hours=1))
        _wd_state(rd, terminal="BLOCKED", updated_at=recent,
                  blocked={"phase": "P9-OWNER-GATE",
                           "reason": "owner decision: waiver approval pending",
                           "at": recent})
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "PARKED-FOR-HUMAN" not in out
        assert "1 recent park(s) still inside the auto-resume window" in out
        assert _escalations(tmp_path) == []

    def test_blocked_without_park_record_is_orphaned(self, tmp_path):
        # No state["blocked"], no configuration_pending: nothing owns this
        # park. Flagged immediately (no age gate) with a DIFFERENT message
        # from the parked-for-human one.
        rd = tmp_path / "orphanpark"
        _wd_state(rd, terminal="BLOCKED", updated_at=_iso(NOW))
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "ORPHANED-BLOCKED" in out
        assert "NO recorded park" in out
        assert "PARKED-FOR-HUMAN" not in out
        assert [e["kind"] for e in _escalations(tmp_path)] == ["blocked_orphaned"]

    def test_configuration_pending_stamp_counts_as_recorded_park(self, tmp_path):
        rd = tmp_path / "cfgpark"
        old = _iso(NOW - timedelta(hours=72))
        _wd_state(rd, terminal="BLOCKED", updated_at=old,
                  configuration_pending={
                      "reason": "ollama plan is undeclared",
                      "owner": "client", "next_action": "answer the plan question"})
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert "PARKED-FOR-HUMAN" in out
        assert "ORPHANED-BLOCKED" not in out


class TestWatchdogNoHeartbeat:
    def test_stale_heartbeatless_run_flagged(self, tmp_path):
        rd = tmp_path / "ghost"
        _wd_state(rd, terminal=None,
                  updated_at=_iso(NOW - timedelta(hours=72)))
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "NO-HEARTBEAT" in out
        assert [e["kind"] for e in _escalations(tmp_path)] == ["no_heartbeat"]

    def test_fresh_heartbeatless_run_not_flagged(self, tmp_path):
        # Negative: a run created moments ago (engine still starting) is
        # counted as without-a-heartbeat, never flagged.
        rd = tmp_path / "starting"
        _wd_state(rd, terminal=None, updated_at=_iso(NOW))
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "NO-HEARTBEAT" not in out
        assert "without a heartbeat" in out
        assert _escalations(tmp_path) == []

    def test_healthy_running_job_never_flagged(self, tmp_path):
        # Required negative: fresh heartbeat, inside its interval -- the
        # scan is a clean pass with no forever output of any kind.
        rd = tmp_path / "healthy"
        _wd_state(rd, terminal=None,
                  heartbeat={"last_checkpoint_at": _iso(NOW),
                             "current_phase": "P4-RENDER",
                             "interval_minutes": 10, "budget_minutes": 60})
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "PARKED-FOR-HUMAN" not in out
        assert "ORPHANED-BLOCKED" not in out
        assert "NO-HEARTBEAT" not in out
        assert "DEAD-LETTER" not in out
        assert not (tmp_path / "watchdog-escalations.jsonl").exists()


class TestWatchdogDeadLetter:
    def _dead_letter_state(self, tmp_path):
        rd = tmp_path / "dl"
        _wd_state(rd, terminal="DONE", dead_letter=[
            {"kind": "done", "chat_id": "chat-stale", "attempts": 5,
             "dead_lettered_at": _iso(NOW - timedelta(hours=2)),
             "dead_letter_reason": "undeliverable after 5 attempts"},
            {"kind": "blocked", "chat_id": "chat-stale", "attempts": 5,
             "dead_lettered_at": _iso(NOW - timedelta(hours=1)),
             "dead_letter_reason": "undeliverable after 5 attempts"},
        ])
        return rd

    def test_dead_letters_surfaced_every_pass(self, tmp_path):
        self._dead_letter_state(tmp_path)
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert rc == EXIT_OK
        assert "DEAD-LETTER" in out and "2 dead-lettered" in out
        assert "2 dead-lettered notification(s) across 1 run(s)" in out
        esc = _escalations(tmp_path)
        assert [e["kind"] for e in esc] == ["dead_letter"]
        assert esc[0]["count"] == 2

    def test_status_command_lists_dead_letters(self, tmp_path, capsys):
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        store = StateStore(rd)
        store.save({
            "schema_version": 1, "job_id": "pj_dl", "run_dir": str(rd),
            "manifest_version": 1, "manifest_sha256": "0" * 64,
            "terminal": "DONE", "current_phase": None, "phases": [],
            "gates": {}, "sent": {},
            "dead_letter": [{"kind": "done", "chat_id": "chat-stale",
                             "attempts": 5}],
        })
        from presentation_job.__main__ import cmd_status

        class A:
            run_dir = rd
            json = False
        rc = cmd_status(A())
        out = capsys.readouterr().out
        assert rc == EXIT_OK
        assert "DEAD-LETTERED messages: 1" in out

    def test_forever_flag_sends_one_notification(self, tmp_path, monkeypatch):
        rd = tmp_path / "orphanpark"
        _wd_state(rd, terminal="BLOCKED", updated_at=_iso(NOW))
        log = tmp_path / "notify.log"
        ns = tmp_path / "notify.sh"
        ns.write_text(f"#!/bin/sh\ncat >> {log}\n")
        ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        rc, out = _capture(watchdog, tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert "ORPHANED-BLOCKED" in out
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        assert sum(1 for ln in lines if ln.strip().startswith("{")) == 1
        assert "ORPHANED-BLOCKED" in log.read_text()


# ---------------------------------------------------------------------------
# (b): supervisor orphaned-running reclaim
# ---------------------------------------------------------------------------

SUP_NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)


def _sup_run(run_dir: Path, phases: list, *, lock=True, dead_pid=999999999):
    run_dir.mkdir(parents=True, exist_ok=True)
    st = {
        "schema_version": 1,
        "job_id": "pj_" + run_dir.name,
        "run_dir": str(run_dir),
        "terminal": None,
        "current_phase": "P-ORPHAN",
        "phases": phases,
        "heartbeat": {"last_checkpoint_at": _iso(SUP_NOW),
                      "current_phase": "P-ORPHAN", "interval_minutes": 10},
        "updated_at": _iso(SUP_NOW),
    }
    (run_dir / "state.json").write_text(json.dumps(st, indent=2))
    if lock:
        (run_dir / LOCK_FILENAME).write_text(f"{dead_pid} {_iso(SUP_NOW)}\n")
    return run_dir


def _dispatch_ledger(run_dir: Path, phase_id: str, worker: str):
    p = _dispatcher._ledger_path(run_dir, phase_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"worker": worker,
                             "last_seen_at": _iso(SUP_NOW)}))


def _supervise_capture(root: Path, **kw):
    kw.setdefault("now", SUP_NOW)
    return _capture(supervise, root, **kw)


def _sup_events(root: Path) -> list:
    p = root / EVENTS_FILENAME
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


class TestSupervisorOrphanReclaim:
    def _orphan_run(self, root: Path):
        rd = _sup_run(root / "run-orphan", [
            {"id": "P-ORPHAN", "status": "running", "attempts": 1,
             "waiting_for": ["working/work-orders/P-ORPHAN.json"],
             "waited_seconds": 3600},
            {"id": "P-CHILD", "status": "pending"},
        ])
        _dispatch_ledger(rd, "P-ORPHAN", "dispatcher-999999999-a1b2c3d4")
        return rd

    def test_dead_engine_orphan_reclaimed_as_failed(self, tmp_path):
        rd = self._orphan_run(tmp_path)
        scripts = tmp_path / "no-scripts"  # restart spawn fails, no child runs
        rc, out = _supervise_capture(tmp_path, apply=True, scan_depth=1,
                                     scripts_dir=scripts, backoff_seconds=0)
        assert "ORPHAN_RECLAIMED" in out
        st = json.loads((rd / "state.json").read_text())
        phases = {p["id"]: p for p in st["phases"]}
        assert phases["P-ORPHAN"]["status"] == "failed"
        assert "orphaned running phase reclaimed by the supervisor sweep" \
            in phases["P-ORPHAN"]["failed_reason"]
        assert "is gone" in phases["P-ORPHAN"]["failed_reason"]
        # FAILED is terminal-bad: the subtree is released to the failure
        # path instead of waiting on the orphan forever.
        assert _phase_terminal_bad(phases["P-ORPHAN"]["status"]) is True
        assert phases["P-CHILD"]["status"] == "pending"
        recs = st.get("resume_readmissions") or []
        assert len(recs) == 1
        assert recs[0]["reclaimed_orphaned_running"]
        assert recs[0]["orphan_disposition"] == "failed"
        kinds = [e["event"] for e in _sup_events(tmp_path)]
        assert "orphan_reclaimed" in kinds

    def test_report_only_detects_and_writes_nothing(self, tmp_path):
        rd = self._orphan_run(tmp_path)
        before = _sha(rd / "state.json")
        rc, out = _supervise_capture(tmp_path, apply=False, scan_depth=1)
        assert "ORPHAN_DETECTED" in out
        assert _sha(rd / "state.json") == before
        assert not (tmp_path / EVENTS_FILENAME).is_file()
        st = json.loads((rd / "state.json").read_text())
        assert st["phases"][0]["status"] == "running"

    def test_live_worker_is_never_reclaimed(self, tmp_path):
        # Negative: the dispatch ledger names THIS live process as the
        # worker -- honoured, never reclaimed, even under --apply.
        rd = _sup_run(tmp_path / "run-live", [
            {"id": "P-LIVE", "status": "running", "attempts": 1}])
        _dispatch_ledger(rd, "P-LIVE", f"dispatcher-{os.getpid()}-a1b2c3d4")
        scripts = tmp_path / "no-scripts"
        rc, out = _supervise_capture(tmp_path, apply=True, scan_depth=1,
                                     scripts_dir=scripts, backoff_seconds=0)
        assert "ORPHAN_RECLAIMED" not in out
        assert "ORPHAN_DETECTED" not in out
        st = json.loads((rd / "state.json").read_text())
        assert st["phases"][0]["status"] == "running"

    def test_unadjudicable_worker_is_honoured(self, tmp_path):
        # Negative: a ledger worker that names no dispatcher pid is
        # "unknown" -- fail closed, honoured like a live worker.
        rd = _sup_run(tmp_path / "run-unknown", [
            {"id": "P-UNK", "status": "running", "attempts": 1}])
        _dispatch_ledger(rd, "P-UNK", "human-operator")
        scripts = tmp_path / "no-scripts"
        rc, out = _supervise_capture(tmp_path, apply=True, scan_depth=1,
                                     scripts_dir=scripts, backoff_seconds=0)
        assert "ORPHAN_RECLAIMED" not in out
        st = json.loads((rd / "state.json").read_text())
        assert st["phases"][0]["status"] == "running"

    def test_live_engine_lock_means_no_reclaim(self, tmp_path):
        # Negative: the engine itself is ALIVE (this process holds the
        # run lock). The dead-run path is never entered, so even an
        # orphaned-looking phase is the live engine's own business.
        import fcntl
        rd = self._orphan_run(tmp_path)
        fh = (rd / LOCK_FILENAME).open("a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            rc, out = _supervise_capture(tmp_path, apply=True, scan_depth=1,
                                         backoff_seconds=0)
        finally:
            fh.close()
        assert "ORPHAN_RECLAIMED" not in out
        assert "ORPHAN_DETECTED" not in out
        st = json.loads((rd / "state.json").read_text())
        assert st["phases"][0]["status"] == "running"


# ---------------------------------------------------------------------------
# (d): cross-invocation heal caps
# ---------------------------------------------------------------------------

def _mkmanifest(tmp_path, phases=None, cmd="echo ok"):
    mp = tmp_path / "m.json"
    if phases is None:
        phases = [{"id": "TP", "order": 1, "owning_role": "t",
                   "produces_artifact": ["o.txt"],
                   "executor": {"kind": "script", "cmd": cmd}}]
    mp.write_text(json.dumps({"manifest_version": 25, "phases": phases}))
    return Manifest(mp)


def _mkengine(tmp_path, manifest=None):
    rd = tmp_path / "r"
    rd.mkdir(exist_ok=True)
    store = StateStore(rd)
    if manifest is None:
        manifest = _mkmanifest(tmp_path)
    s = {"schema_version": 1, "job_id": "t", "run_dir": str(rd),
         "created_at": "", "manifest_path": str(manifest.path),
         "manifest_version": 25, "manifest_sha256": manifest.sha256,
         "presentation_type": "from_scratch", "requester": {"chat_id": "t"},
         "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
         "undeliverable": [], "heartbeat": {}, "terminal": None}
    store.save(s)
    return Engine(rd, manifest, store, s), s


def _seed_heal_events(engine, phase_id, events):
    ps = engine._phase_state(phase_id)
    ps.setdefault("heal_events", []).extend(events)
    engine.store.save(engine.state)
    return ps


def _ev(rung, at, cls="transient", reason="exit 99", attempt=1):
    return {"at": at, "rung": rung, "attempt": attempt,
            "reason": reason, "class": cls}


class TestHealWindowCounter:
    def test_counts_only_inside_window(self):
        now = datetime.now(timezone.utc)
        pd = {"heal_events": [
            _ev(1, _iso(now)),
            _ev(1, _iso(now - timedelta(hours=25))),
            _ev(1, "not-a-date"),
            _ev(2, _iso(now)),
        ]}
        assert heal.heal_attempts_in_window(pd, rung=1, now=now) == 1
        assert heal.heal_attempts_in_window(pd, rung=2, now=now) == 1
        assert heal.heal_attempts_in_window(pd, now=now) == 2
        assert heal.heal_budget_remaining(pd, rung=1, cap=3, now=now) == 2

    def test_class_filters(self):
        now = datetime.now(timezone.utc)
        pd = {"heal_events": [
            _ev(2, _iso(now), cls="provider_error"),
            _ev(2, _iso(now), cls="transient"),
        ]}
        assert heal.heal_attempts_in_window(
            pd, rung=2, failure_class="provider_error", now=now) == 1
        assert heal.heal_attempts_in_window(
            pd, rung=2, exclude_failure_class="provider_error", now=now) == 1


class TestHealCapsCrossInvocation:
    def test_rung2_exhausted_by_prior_invocation(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path, cmd="exit 99")
        e, s = _mkengine(tmp_path, m)
        _seed_heal_events(e, "TP", [_ev(2, utcnow()), _ev(2, utcnow())])
        rc = rung2_regenerate(e, m.phase("TP"), "missing artifact")
        assert rc == EXIT_EXECUTOR_FAILED
        ps = e._phase_state("TP")
        assert len(ps["heal_events"]) == 2, "no fresh slice may be spent"
        ladder = (tmp_path / "r" / "working" / "heal" / "ladder.jsonl")
        rows = [json.loads(ln) for ln in ladder.read_text().splitlines()]
        assert rows[-1]["outcome"] == "heal_budget_exhausted_cross_invocation"

    def test_rung2_budget_refills_after_window(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path, cmd="exit 99")
        e, s = _mkengine(tmp_path, m)
        old = _iso(datetime.now(timezone.utc) - timedelta(hours=25))
        _seed_heal_events(e, "TP", [_ev(2, old), _ev(2, old)])
        rc = rung2_regenerate(e, m.phase("TP"), "missing artifact")
        assert rc == EXIT_EXECUTOR_FAILED  # the command still fails...
        ps = e._phase_state("TP")
        # ...but the ladder ran: the two spent attempts aged out of the
        # window, so two fresh attempts were recorded on top of them.
        assert len(ps["heal_events"]) == 4

    def test_rung1_spent_window_still_executes_primary_attempt(
            self, tmp_path, monkeypatch):
        # The PD-TEST-060/080 floor: with the whole rung-1 retry budget
        # spent inside the window, a re-admitted phase still EXECUTES its
        # primary attempt -- so a repair that landed between invocations
        # can actually reach it. Here the (repaired) command succeeds.
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        sentinel = tmp_path / "ran"
        m = _mkmanifest(tmp_path, cmd=f"touch {sentinel}")
        e, s = _mkengine(tmp_path, m)
        _seed_heal_events(e, "TP", [_ev(1, utcnow(), reason="exit 1"),
                                    _ev(1, utcnow(), reason="exit 1"),
                                    _ev(1, utcnow(), reason="exit 1")])
        rc = e._run_script_phase(m.phase("TP"))
        assert rc == EXIT_OK
        assert sentinel.exists(), "the primary attempt must execute"
        ps = e._phase_state("TP")
        assert len([h for h in ps["heal_events"] if h["rung"] == 1]) == 3

    def test_rung1_spent_window_allows_no_retries(self, tmp_path, monkeypatch):
        # The other half of Item 9(d): with the window spent, the primary
        # attempt runs ONCE and, on failure, goes straight to the failure
        # path -- no retry slice (attempts 2 and 3) is spent.
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path, cmd="exit 99")
        e, s = _mkengine(tmp_path, m)
        _seed_heal_events(e, "TP", [_ev(1, utcnow(), reason="exit 99"),
                                    _ev(1, utcnow(), reason="exit 99"),
                                    _ev(1, utcnow(), reason="exit 99")])
        rc = e._run_script_phase(m.phase("TP"))
        assert rc == EXIT_GATE_BLOCKED
        ps = e._phase_state("TP")
        assert ps["status"] == "quarantined"
        assert len([h for h in ps["heal_events"] if h["rung"] == 1]) == 4, \
            "exactly one primary attempt may be spent, never a fresh slice"

    def test_provider_failover_exhausted_by_prior_invocation(
            self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path, cmd="exit 99")
        e, s = _mkengine(tmp_path, m)
        _seed_heal_events(e, "TP", [
            _ev(2, utcnow(), cls="provider_error",
                reason="http 402 payment required")])
        rc = heal.rung2_provider_failover(e, m.phase("TP"),
                                          "http 402 payment required")
        assert rc == EXIT_EXECUTOR_FAILED
        ps = e._phase_state("TP")
        assert len(ps["heal_events"]) == 1, "no second failover may be spent"
        ladder = (tmp_path / "r" / "working" / "heal" / "ladder.jsonl")
        rows = [json.loads(ln) for ln in ladder.read_text().splitlines()]
        assert rows[-1]["outcome"] == "heal_budget_exhausted_cross_invocation"

    def test_rung3_exhausted_by_prior_invocation(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path, phases=[{
            "id": "TP", "order": 1, "owning_role": "t",
            "produces_artifact": ["o.txt"],
            "executor": {"kind": "script", "cmd": "exit 1",
                         "alt_cmd": "echo ok"}}])
        e, s = _mkengine(tmp_path, m)
        _seed_heal_events(e, "TP", [_ev(3, utcnow(), reason="alternate route")])
        rc = rung3_alt_route(e, m.phase("TP"))
        assert rc == EXIT_EXECUTOR_FAILED, \
            "the alt route (which would succeed) must not run on a spent budget"
