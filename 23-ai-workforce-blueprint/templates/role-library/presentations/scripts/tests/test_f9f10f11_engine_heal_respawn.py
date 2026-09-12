"""Regression tests for F9 + F10 + F11 (Fable review section 15) -- the three
coordination defects that live in phases.Engine._run_agent_phase / run_phase and
heal.py, shipped as one chain because they edit the same functions in that order.

WHAT EACH ONE IS, AND WHAT IT COST (measured on the 22 h run):

F9 -- THE ENGINE IGNORED THE DISPATCHER'S PARK MARKER.
    dispatcher._park_blocked writes working/work-orders/<phase>.dispatch-blocked.txt
    the instant a phase hits DISPATCH_REPEAT_CEILING, and the marker's own text
    says re-dispatch "resumes automatically if the Engine reissues the work
    order". Engine._run_agent_phase never read it: it kept polling for an
    artifact nothing was going to write, for the REST of the phase budget. The
    dispatcher was waiting on the Engine; the Engine was waiting on the
    dispatcher. MEASURED: P4-COPY and P4-PROMPT together burned 8.3 hours in one
    run across ten fail-park-resume cycles -- 60-90 minutes of budget thrown away
    each time before a human noticed and resumed it.

F10 -- THE HEAL LADDER DID NOTHING FOR AGENT PHASES.
    heal.rung2_regenerate and heal.rung2_provider_failover both re-executed
    `engine._build_executor_argv(phase.executor_cmd, ...)`. An agent phase has no
    executor_cmd -- its artifact is authored by work_order_dispatcher.py from
    working/work-orders/<id>.json -- so the argv came back EMPTY and both rungs
    returned EXIT_EXECUTOR_FAILED without doing anything at all. 38 of the 62
    manifest phases are agent-authored, so the ladder was inert for roughly two
    thirds of the pipeline. And Engine._run_agent_phase never even reached it:
    on failure it went straight to _fail_unit. MEASURED: 9 of the 21 human
    --resumes on that run SUCCEEDED IMMEDIATELY on the very next try -- transient
    failures any retry would have cleared, and nothing retried them.

F11 -- A DEAD DISPATCHER SILENTLY STRANDED A LIVE RUN.
    work_order_dispatcher.py --watch exits on its own --max-lifetime-minutes
    ceiling (default 360 = 6 h) as well as on any crash/OOM/kill. Measured runs
    last 22 hours. Nothing noticed: every agent phase queued after the death
    burned its FULL budget producing nothing, one at a time, which to an operator
    is indistinguishable from slow progress.

HOW THESE TESTS PROVE DIRECTION -- measured, not asserted. Against pristine
origin/main (ea331f82a) this file scores 18 failed / 3 passed; on the branch,
21 passed.

The 18 failures are the fix: each one lands either on a symbol that does not
exist on pristine (autospawn, _respawn_dispatcher_if_dead, _await_agent_artifact,
_apply_route_override, resolve_max_lifetime_minutes) or on an observable the old
code never produced (the "dispatcher retry ceiling" quarantine reason, a
heal_reason / route_override on a reissued work order, a heal rung reached at
all for an agent phase). Every one of those 18 was individually inspected for
its failure REASON, so none is an incidental error masquerading as proof.

The 3 that pass on pristine are the CONTROL, and they are load-bearing twice
over: they prove the harness itself really runs against pristine (so the 18
failures are behavioural differences, not an import abort), and they pin
behaviour these fixes must NOT change --
  * test_f9_a_fresh_work_order_clears_a_marker_that_survived_a_crash
    (F9 must not over-react to an orphaned marker),
  * test_f9_guard_a_finished_artifact_beats_a_stale_park_marker,
  * test_guard_a_parked_run_still_refuses_to_queue_new_work.

Flat file inside tests/, manages its own import path -- matching every sibling in
this directory (test_f16_agent_phase_wait_race.py, test_heal.py, etc.).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job import heal  # noqa: E402
from presentation_job.state import (  # noqa: E402
    StateStore, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_EXECUTOR_FAILED,
)


# ---------------------------------------------------------------------------
# Harness -- same shape as tests/test_f16_agent_phase_wait_race.py
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
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
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


def _engine(tmp_path) -> Engine:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar", "creation_mode": "from_scratch"}))
    manifest = Manifest(_canonical_manifest())
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


class FakeClock:
    """Deterministic stand-in for time.time()/time.sleep() so a real phase
    budget can be exhausted without waiting real wall-clock time."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start
        self.sleep_calls = 0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls += 1
        self.now += seconds


def _install_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr("time.time", clock.time)
    monkeypatch.setattr("time.sleep", clock.sleep)
    return clock


# P1Q-COPY-QC: executor_kind "agent", ONE exact produces_artifact path (no glob,
# so the wait's completion rule is the simple one), budget 20 minutes = 80 poll
# ticks at the loop's fixed 15 s cadence. Asserted here rather than assumed, so
# a manifest change that invalidates these tests says so out loud.
AGENT_PHASE_ID = "P1Q-COPY-QC"
AGENT_PHASE_BUDGET_MIN = 20
FULL_BUDGET_SLEEPS = AGENT_PHASE_BUDGET_MIN * 60 // 15  # 80


def _agent_phase(eng: Engine):
    phase = eng.manifest.phase(AGENT_PHASE_ID)
    assert phase.executor_kind == "agent", (
        f"{AGENT_PHASE_ID} is no longer an agent phase in the manifest -- these "
        "tests measure the agent path and must be re-pointed")
    assert phase.budget_minutes == AGENT_PHASE_BUDGET_MIN
    return phase


def _park_marker_path(eng: Engine, phase_id: str) -> Path:
    """The marker path from the module that WRITES it, never a literal retyped
    here -- if dispatcher ever renames it, these tests must move with it."""
    from presentation_job import dispatcher as _dispatcher
    return _dispatcher._blocked_marker_path(eng.run_dir, phase_id)


def _park_phase_like_the_dispatcher(eng: Engine, phase_id: str,
                                    reason: str = "retry ceiling reached") -> Path:
    """Reproduce a REAL dispatcher park: the marker file AND the settling
    `blocked_retry_ceiling` sidecar row, both written by dispatcher.py's own
    _park_blocked. Using the real producer means these tests cannot pass against
    a marker shape the dispatcher does not actually write."""
    from presentation_job import dispatcher as _dispatcher
    (eng.run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    _dispatcher._park_blocked(
        eng.run_dir, phase_id,
        {"blocked_reason": reason, "blocked_at": "2026-09-06T00:00:00+00:00",
         "status": "error", "consecutive": 3, "observations": 3},
        worker_id="dispatcher-test")
    return _park_marker_path(eng, phase_id)


def _write_work_order(eng: Engine, phase) -> Path:
    wo = eng.run_dir / "working" / "work-orders" / f"{phase.id}.json"
    wo.parent.mkdir(parents=True, exist_ok=True)
    wo.write_text(json.dumps({
        "phase": phase.id, "owning_role": phase.owning_role,
        "produces_artifact": list(phase.produces_artifact),
        "verifier": phase.verifier, "budget_minutes": phase.budget_minutes,
        "issued_at": "2026-09-06T00:00:00+00:00",
    }, indent=2), encoding="utf-8")
    return wo


def _read_order(wo: Path) -> dict:
    return json.loads(wo.read_text(encoding="utf-8"))


def _a_dead_pid() -> int:
    """A pid that is genuinely not running. Proven, not assumed: os.kill(pid, 0)
    must raise ProcessLookupError before this returns it."""
    for candidate in range(4_000_000, 4_000_050):
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except OSError:
            continue
    pytest.fail("could not find a dead pid to test with -- the check itself is broken")


# ===========================================================================
# F9 -- react to the dispatcher's park marker
# ===========================================================================
def test_f9_park_marker_ends_the_wait_instead_of_burning_the_whole_budget(
        tmp_path, monkeypatch):
    """THE 8.3-HOUR DEFECT. A parked phase must stop waiting immediately and say
    WHY, not poll a dead dispatcher for the rest of its budget.

    The heal rungs are stubbed out here so this test measures F9 alone -- F10's
    own behaviour is proved separately below."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    clock = _install_clock(monkeypatch)
    _write_work_order(eng, phase)
    _park_phase_like_the_dispatcher(eng, phase.id)

    monkeypatch.setattr(heal, "rung2_regenerate",
                        lambda *a, **k: EXIT_EXECUTOR_FAILED)
    monkeypatch.setattr(heal, "rung2_provider_failover",
                        lambda *a, **k: EXIT_EXECUTOR_FAILED)

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    ps = eng._phase_state(phase.id)
    reason = ps.get("quarantined_reason") or ""
    assert "dispatcher retry ceiling" in reason, (
        "the phase must fail NAMING the dispatcher's park, not with the generic "
        f"budget-timeout reason -- got: {reason!r}")
    assert "retry ceiling reached" in reason, (
        "the dispatcher's own stated reason must ride along, so an operator reads "
        f"one message and not two files -- got: {reason!r}")
    # This reason reaches the CLIENT's chat through Reporter.to_requester, so it
    # must be a summary, never the whole marker file. The marker's internal
    # bookkeeping stays on disk for the operator.
    assert len(reason) < 300, f"the client-facing reason must stay short: {len(reason)} chars"
    for internal in ("consecutive:", "Ledger:", "NEEDS ATTENTION", "worker:"):
        assert internal not in reason, (
            f"internal dispatcher bookkeeping {internal!r} must not be sent to the "
            f"client -- got: {reason!r}")
    assert clock.sleep_calls < FULL_BUDGET_SLEEPS / 4, (
        f"the wait must END at the park, not run out the budget: "
        f"{clock.sleep_calls} sleeps of a {FULL_BUDGET_SLEEPS}-sleep budget")


def test_f9_quarantine_clears_the_park_marker_so_a_resume_re_dispatches(
        tmp_path, monkeypatch):
    """Second half of F9. A marker left behind after the Engine has quarantined
    the unit would (a) lie to the operator reading `ls working/work-orders/` and
    (b) make the NEXT entry into this phase react to a stale park on its first
    tick, without ever waiting for the fresh dispatch."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)
    marker = _park_phase_like_the_dispatcher(eng, phase.id)
    assert marker.is_file(), "control: the marker must exist before the run"

    monkeypatch.setattr(heal, "rung2_regenerate",
                        lambda *a, **k: EXIT_EXECUTOR_FAILED)

    eng._run_agent_phase(phase)

    assert not marker.exists(), (
        "the park marker must not outlive the quarantine that reacted to it")


def test_f9_a_fresh_work_order_clears_a_marker_that_survived_a_crash(
        tmp_path, monkeypatch):
    """The stale-marker hole. A marker that outlived an engine SIGKILL must not
    make the NEXT dispatch quarantine on its first poll tick without ever
    waiting. Reissuing the order is precisely the un-parking condition the
    dispatcher's own marker text names, so the reissue clears it -- and the wait
    then spends the real budget on the fresh dispatch.

    No work order is pre-written here, so the Engine takes its fresh-issue
    branch (the one FIX 09b guards) rather than the reuse branch."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    clock = _install_clock(monkeypatch)
    marker = _park_phase_like_the_dispatcher(eng, phase.id)
    assert marker.is_file(), "control: an orphaned marker exists before the run"

    monkeypatch.setattr(heal, "rung2_regenerate", lambda *a, **k: EXIT_EXECUTOR_FAILED)

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    assert clock.sleep_calls >= FULL_BUDGET_SLEEPS - 1, (
        "a freshly issued order must get its FULL budget, not be cut short by a "
        f"marker from a previous life: {clock.sleep_calls} sleeps")
    ps = eng._phase_state(phase.id)
    assert "dispatcher retry ceiling" not in (ps.get("quarantined_reason") or ""), (
        "the orphaned marker must not be reported as this dispatch's park")


def test_f9_guard_a_finished_artifact_beats_a_stale_park_marker(tmp_path, monkeypatch):
    """GUARD (holds in BOTH directions). The marker check sits AFTER the
    completion check on purpose: a park left over from an earlier attempt must
    never override an artifact that is genuinely finished now."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)
    _park_phase_like_the_dispatcher(eng, phase.id)

    target = eng.run_dir / phase.produces_artifact[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"ok": True}), encoding="utf-8")

    import phase_verifiers
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    assert eng._run_agent_phase(phase) == EXIT_OK, (
        "a complete, verifier-passing artifact must complete the phase even with "
        "a stale park marker on disk")


# ===========================================================================
# F10 -- real heal rungs for agent phases
# ===========================================================================
def test_f10_agent_phase_failure_reaches_the_heal_ladder_at_all(tmp_path, monkeypatch):
    """The routing defect itself: _run_agent_phase went straight to _fail_unit,
    so heal.rung2_* was never reached for ANY of the 38 agent phases."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)

    seen = []

    def fake_regen(engine, ph, deficiency, **kw):
        seen.append((ph.id, str(deficiency)))
        return EXIT_EXECUTOR_FAILED

    monkeypatch.setattr(heal, "rung2_regenerate", fake_regen)

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    assert seen, ("an agent phase that produced nothing must reach the heal "
                  "ladder before it is quarantined -- 9 of 21 measured resumes "
                  "succeeded on the very next try")
    assert seen[0][0] == phase.id
    assert "produced nothing" in seen[0][1], (
        f"the rung must receive the REAL failure reason -- got: {seen[0][1]!r}")


def test_f10_a_successful_heal_completes_the_phase_no_resume_typed(tmp_path, monkeypatch):
    """The whole point of the ladder: when the retry works, the phase advances.
    Pristine returns EXIT_GATE_BLOCKED here and waits for a human."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)

    monkeypatch.setattr(heal, "rung2_regenerate", lambda *a, **k: EXIT_OK)

    assert eng._run_agent_phase(phase) == EXIT_OK, (
        "a heal rung that reports success must complete the phase, not quarantine it")


def test_f10_heal_is_capped_at_one_ladder_pass_per_phase_per_run(tmp_path, monkeypatch):
    """Bounded exactly like run_phase's own verifier_regen_done arm: a --resume
    must not be able to spin the ladder forever."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)

    calls = []
    monkeypatch.setattr(heal, "rung2_regenerate",
                        lambda *a, **k: calls.append(1) or EXIT_EXECUTOR_FAILED)

    eng._run_agent_phase(phase)
    first = len(calls)
    assert first == 1

    # Simulate a --resume re-entering the same phase.
    ps = eng._phase_state(phase.id)
    ps["status"] = "pending"
    _write_work_order(eng, phase)
    eng._run_agent_phase(phase)

    assert len(calls) == first, (
        "the ladder must run once per phase per run, not on every re-entry")


def test_f10_owner_decision_reasons_never_heal(tmp_path, monkeypatch):
    """A decision only the client can make is parked and announced, never
    retried -- FIX 10's rule, preserved through the new agent path."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)

    called = []
    monkeypatch.setattr(heal, "rung2_regenerate",
                        lambda *a, **k: called.append(1) or EXIT_OK)
    monkeypatch.setattr(heal, "rung2_provider_failover",
                        lambda *a, **k: called.append(1) or EXIT_OK)

    rc = eng._heal_or_fail_agent_phase(
        phase, "gate declined: the owner has not approved this section")

    assert rc == EXIT_GATE_BLOCKED
    assert not called, "an owner-decision failure must never enter a heal rung"
    assert eng.state.get("terminal") == "BLOCKED", (
        "an owner decision parks the run (park and notify), it does not quarantine")


def test_f10_dry_run_never_reissues_and_never_waits(tmp_path, monkeypatch):
    """GUARD, and a real bug this chain introduced and then closed.

    `--dry-run` executes nothing and spawns no dispatcher. _run_agent_phase
    returns EXIT_OK before its wait, but F10 gave that wait a SECOND caller --
    the heal rungs, which run_phase reaches from its artifact-missing and
    verifier-failed branches, and those branches ARE live under dry_run. The
    first version of this chain therefore sat in a real 30-minute sleep loop
    inside a dry run, waiting for a dispatcher that a dry run never starts.
    tests/test_checkpoint.py (dry_run engines whose artifact is deliberately
    deleted) hung the entire suite on it.

    A dry run must take the pre-F10 path exactly: do nothing, fail immediately.
    NOTE the deliberate absence of a fake clock here -- a real clock is the
    whole point. If the guard regresses, this test hangs for 30 minutes rather
    than failing politely, which is the honest signal."""
    eng = _engine(tmp_path)
    eng.dry_run = True
    phase = _agent_phase(eng)
    wo = _write_work_order(eng, phase)

    import time as _time
    started = _time.monotonic()
    rc = heal.rung2_regenerate(eng, phase, "produced nothing")
    elapsed = _time.monotonic() - started

    assert rc == EXIT_EXECUTOR_FAILED
    assert elapsed < 5.0, f"a dry run must not wait at all; waited {elapsed:.1f}s"
    assert "heal_reason" not in _read_order(wo), (
        "a dry run must not queue real work by reissuing the order")

    # And the shared wait itself refuses outright, whoever calls it.
    outcome, present, notes, marker = eng._await_agent_artifact(
        phase, budget_seconds=1800, glob_patterns=[], baseline_progress=0.0)
    assert outcome == "timeout" and present is False


def test_f10_regenerate_reissues_the_work_order_carrying_the_real_reason(
        tmp_path, monkeypatch):
    """The agent arm of rung2_regenerate. An agent phase has no executor argv;
    its equivalent of "re-run the executor" is "reissue the work order", and the
    reissue must carry the verbatim failure reason so compose_prompt can feed it
    back to the model instead of letting it start over blind."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    wo = _write_work_order(eng, phase)
    before = _read_order(wo)
    assert "heal_reason" not in before, "control: the fresh order carries no heal reason"

    monkeypatch.setattr(Engine, "_await_agent_artifact",
                        lambda self, ph, **kw: ("timeout", False, [], ""),
                        raising=False)

    deficiency = "substance check failed: copy_qc_report.json has 0 findings"
    rc = heal.rung2_regenerate(eng, phase, deficiency)

    assert rc == EXIT_EXECUTOR_FAILED, "the stubbed wait never produces the artifact"
    after = _read_order(wo)
    assert after.get("heal_reason") == deficiency, (
        "the reissued work order must carry the verbatim failure reason -- got: "
        f"{after.get('heal_reason')!r}")
    assert after.get("attempt_hint"), "the reissue must say which attempt this is"
    assert after.get("reissued_at"), "the reissue must be stamped"
    assert after.get("produces_artifact") == list(phase.produces_artifact), (
        "the reissue must remain a complete, valid work order")


def test_f10_regenerate_clears_the_park_marker_so_the_dispatcher_resumes(
        tmp_path, monkeypatch):
    """The dispatcher's marker says re-dispatch resumes "if the Engine reissues
    the work order". A reissue that leaves the marker in place contradicts the
    very message the dispatcher wrote."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)
    marker = _park_phase_like_the_dispatcher(eng, phase.id)
    assert marker.is_file(), "control: the marker must exist before the rung runs"

    monkeypatch.setattr(Engine, "_await_agent_artifact",
                        lambda self, ph, **kw: ("timeout", False, [], ""),
                        raising=False)

    heal.rung2_regenerate(eng, phase, "transient failure")

    assert not marker.exists(), "reissuing the order must clear the park marker"


def test_f10_provider_failover_pins_route_override_on_the_reissued_order(
        tmp_path, monkeypatch):
    """The provider arm. An agent phase cannot be re-executed on another
    provider by running a different argv -- the pin has to ride on the work
    order, where dispatch_complete can honour it."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    wo = _write_work_order(eng, phase)

    # The provider the dispatcher last routed this phase to, read the way
    # heal._last_routed_provider really reads it.
    tel = eng.run_dir / "working" / "telemetry" / "stage-timings.jsonl"
    tel.parent.mkdir(parents=True, exist_ok=True)
    tel.write_text(json.dumps({"phase_id": phase.id, "event": "model_route",
                               "selected_provider": "deepseek-direct"}) + "\n",
                   encoding="utf-8")

    from presentation_job import model_router
    monkeypatch.setattr(model_router, "resolve_route", lambda *a, **k: {
        "router": "model_router",
        "route": {"provider": "deepseek-direct", "model": "deepseek-flash"},
        "candidates": [
            {"provider": "deepseek-direct", "model": "deepseek-flash",
             "eligible": True},
            {"provider": "ollama-cloud", "model": "qwen3-coder:480b",
             "eligible": True},
        ],
    })
    monkeypatch.setattr(Engine, "_await_agent_artifact",
                        lambda self, ph, **kw: ("timeout", False, [], ""),
                        raising=False)

    heal.rung2_provider_failover(eng, phase, "HTTP 429 rate limit from the provider")

    after = _read_order(wo)
    assert after.get("route_override") == {"provider": "ollama-cloud",
                                           "model": "qwen3-coder:480b"}, (
        "the failover must pin the ALTERNATE provider on the reissued order -- "
        f"got: {after.get('route_override')!r}")
    assert after.get("heal_reason"), "the failover reissue must also carry the reason"


def test_f10_compose_prompt_feeds_the_heal_reason_back_to_the_model(tmp_path, monkeypatch):
    """A reissued order is worthless if the model never sees WHY the last
    attempt failed -- it just produces the same defect again. The heal reason
    must land in the same "fix EXACTLY these named reasons" block the sidecar's
    prior reasons use, not merely inside the dumped work-order JSON."""
    from presentation_job import dispatcher as _dispatcher

    monkeypatch.setattr(_dispatcher, "load_role_context", lambda *a, **k: "ROLE SOP")
    monkeypatch.setattr(_dispatcher, "read_persona_bundle", lambda *a, **k: None)
    monkeypatch.setattr(_dispatcher, "gather_upstream_context", lambda *a, **k: "UPSTREAM")

    reason = "substance check failed: copy_qc_report.json has 0 findings"
    order = {"phase": AGENT_PHASE_ID, "heal_reason": reason}
    _system, user = _dispatcher.compose_prompt(
        phase_id=AGENT_PHASE_ID, owning_role="copy-qc-presentations",
        dept_root=tmp_path, run_dir=tmp_path, order=order,
        attempt=1, prior_reasons=None)

    header = "YOUR PREVIOUS ATTEMPT FAILED THE REAL VERIFIER"
    assert header in user, (
        "a heal reason must open the prior-findings block; without it the model "
        "is handed a fresh-looking order and starts over blind")
    tail = user.split(header, 1)[1]
    assert f"- {reason}" in tail, (
        "the heal reason must appear as a named prior finding, not only inside "
        "the dumped work-order JSON")


def test_f10_route_override_is_honoured_only_for_an_eligible_candidate():
    """The safety property. `candidates` is where client-owned-provider consent,
    catalog health, capability and mode budget have ALREADY been applied, so
    honouring only an eligible candidate means a heal rung can re-point a phase
    but can never widen what the client owns."""
    from presentation_job import dispatcher as _dispatcher

    decision = {
        "router": "model_router",
        "route": {"provider": "deepseek-direct", "model": "deepseek-flash"},
        "candidates": [
            {"provider": "deepseek-direct", "model": "deepseek-flash",
             "eligible": True},
            {"provider": "ollama-cloud", "model": "qwen3-coder:480b",
             "eligible": True},
            {"provider": "not-owned", "model": "whatever", "eligible": False},
        ],
    }

    honoured = _dispatcher._apply_route_override(
        decision, {"provider": "ollama-cloud", "model": "qwen3-coder:480b"})
    assert honoured["route"] == {"provider": "ollama-cloud",
                                 "model": "qwen3-coder:480b"}

    refused = _dispatcher._apply_route_override(
        decision, {"provider": "not-owned", "model": "whatever"})
    assert refused["route"] == decision["route"], (
        "an override naming an INELIGIBLE candidate must be dropped -- a heal "
        "rung is not a back door around provider consent")

    unknown = _dispatcher._apply_route_override(
        decision, {"provider": "never-heard-of-it", "model": "x"})
    assert unknown["route"] == decision["route"], (
        "an override naming an unknown provider must be dropped")

    assert _dispatcher._apply_route_override(decision, None)["route"] == decision["route"]
    assert _dispatcher._apply_route_override(None, {"provider": "x"}) is None


# ===========================================================================
# F11 -- respawn the dispatcher inside long runs
# ===========================================================================
def test_f11_autospawn_helpers_live_outside_main_and_are_still_re_exported():
    """F11's prerequisite: the Engine cannot import __main__ (it imports
    phases.Engine at module scope, and under `python3 -m presentation_job` the
    entry module registers as `__main__`, not `presentation_job.__main__`). The
    helpers moved to presentation_job/autospawn.py -- and __main__ must still
    expose the SAME objects, or every existing caller breaks."""
    from presentation_job import autospawn
    from presentation_job import __main__ as pj_main

    for name in ("_pid_is_alive", "_auto_dispatch_lock_path",
                 "_auto_dispatch_disabled", "_spawn_dispatcher_if_available",
                 "_stop_auto_dispatcher"):
        assert getattr(pj_main, name) is getattr(autospawn, name), (
            f"__main__.{name} must be the very object autospawn defines")


def test_f11_a_dead_dispatcher_is_respawned(tmp_path, monkeypatch):
    """The measured shape: the lock file names a dispatcher that is GONE."""
    from presentation_job import autospawn

    eng = _engine(tmp_path)
    lock = autospawn._auto_dispatch_lock_path(eng.run_dir)
    lock.parent.mkdir(parents=True, exist_ok=True)
    dead = _a_dead_pid()
    lock.write_text(json.dumps({"pid": dead, "started_at": "2026-09-06T00:00:00+00:00",
                                "run_dir": str(eng.run_dir)}), encoding="utf-8")

    spawned = []

    class _FakeProc:
        pid = 424242

    monkeypatch.setattr(autospawn, "_spawn_dispatcher_if_available",
                        lambda rd, sd, disabled=False: (spawned.append((rd, sd))
                                                        or _FakeProc()))

    assert eng._respawn_dispatcher_if_dead(AGENT_PHASE_ID) is True
    assert len(spawned) == 1, "exactly one respawn for one dead dispatcher"
    assert spawned[0][0] == eng.run_dir
    events = [e for e in eng.state.get("events", [])
              if e.get("kind") == "phase.dispatcher_respawned"]
    assert events, "a respawn must be recorded in the run's event log"


def test_f11_a_live_dispatcher_is_never_double_spawned(tmp_path, monkeypatch):
    """FAULT-09's rule holds: two dispatchers must never run against one run
    dir. A live lock holder is left completely alone."""
    from presentation_job import autospawn

    eng = _engine(tmp_path)
    lock = autospawn._auto_dispatch_lock_path(eng.run_dir)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "started_at": "x",
                                "run_dir": str(eng.run_dir)}), encoding="utf-8")

    spawned = []
    monkeypatch.setattr(autospawn, "_spawn_dispatcher_if_available",
                        lambda *a, **k: spawned.append(1))

    assert eng._respawn_dispatcher_if_dead(AGENT_PHASE_ID) is False
    assert not spawned, "a LIVE dispatcher must never be duplicated"
    assert lock.is_file(), "a live holder's lock must not be deleted"


def test_f11_no_lock_at_all_means_hands_off(tmp_path, monkeypatch):
    """--no-auto-dispatch / --dry-run / an operator's own manual --watch leave no
    lock. Arming one from here would race a dispatcher this engine does not own."""
    from presentation_job import autospawn

    eng = _engine(tmp_path)
    spawned = []
    monkeypatch.setattr(autospawn, "_spawn_dispatcher_if_available",
                        lambda *a, **k: spawned.append(1))

    assert eng._respawn_dispatcher_if_dead(AGENT_PHASE_ID) is False
    assert not spawned


def test_f11_the_agent_phase_wait_actually_performs_the_check(tmp_path, monkeypatch):
    """Wiring, not just the helper: the respawn must happen on the path a real
    phase takes, or a 22-hour run is stranded exactly as before."""
    from presentation_job import autospawn

    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    _install_clock(monkeypatch)
    _write_work_order(eng, phase)
    _park_phase_like_the_dispatcher(eng, phase.id)  # ends the wait promptly

    lock = autospawn._auto_dispatch_lock_path(eng.run_dir)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": _a_dead_pid(), "started_at": "x",
                                "run_dir": str(eng.run_dir)}), encoding="utf-8")

    spawned = []

    class _FakeProc:
        pid = 515151

    monkeypatch.setattr(autospawn, "_spawn_dispatcher_if_available",
                        lambda rd, sd, disabled=False: (spawned.append(rd)
                                                        or _FakeProc()))
    monkeypatch.setattr(heal, "rung2_regenerate", lambda *a, **k: EXIT_EXECUTOR_FAILED)

    eng._run_agent_phase(phase)

    assert spawned, ("_run_agent_phase must notice a dead dispatcher before it "
                     "starts waiting on one")


def test_f11_run_dir_watch_outlives_the_run_scan_root_does_not():
    """The 6 h ceiling against 22 h runs. --run-dir is ONE run's companion
    process and must outlive it; --scan-root is a periodic sweeper and keeps 6 h.
    An explicit flag still wins in both modes."""
    from presentation_job import dispatcher as _dispatcher

    assert _dispatcher.resolve_max_lifetime_minutes(None, run_dir_mode=True) == 1440.0
    assert _dispatcher.resolve_max_lifetime_minutes(None, run_dir_mode=False) == 360.0
    assert _dispatcher.resolve_max_lifetime_minutes(15.0, run_dir_mode=True) == 15.0
    assert _dispatcher.resolve_max_lifetime_minutes(15.0, run_dir_mode=False) == 15.0

    args = _dispatcher.build_parser().parse_args(["--run-dir", "/tmp/x"])
    assert args.max_lifetime_minutes is None, (
        "the flag must default to None so main() can pick the per-mode ceiling")
    args = _dispatcher.build_parser().parse_args(
        ["--run-dir", "/tmp/x", "--max-lifetime-minutes", "42"])
    assert args.max_lifetime_minutes == 42.0


# ===========================================================================
# GUARD -- the chain must not disturb what already worked
# ===========================================================================
def test_guard_a_parked_run_still_refuses_to_queue_new_work(tmp_path, monkeypatch):
    """GUARD (holds in BOTH directions). DEADLOCK-2: the Engine must not queue a
    work order for a run whose terminal is set -- every dispatcher exits while a
    terminal is set, so the order could never be serviced. F9/F10/F11 must not
    have moved that check."""
    eng = _engine(tmp_path)
    phase = _agent_phase(eng)
    eng.state["terminal"] = "BLOCKED"
    _install_clock(monkeypatch)

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    wo = eng.run_dir / "working" / "work-orders" / f"{phase.id}.json"
    assert not wo.exists(), "a parked run must never accumulate new work orders"
