#!/usr/bin/env python3
"""scheduler.py — Signature Launch unit scheduler (checklist S1, stdlib only).

WHY THIS EXISTS
---------------
Every launch unit (page, email sequence, text set, automation) declares
``waits_for``: the units that must be COMPLETE before it may start. This
module turns that field into waves and enforces the readiness rules the
runtime swarm depends on:

  * every unit whose ``waits_for`` is complete starts in the SAME wave —
    ready work is never queued behind unrelated work
  * an automation additionally waits for the page URLs its family targets:
    a completed page whose ``url`` is still null has no approved URL, so the
    automation cannot reference it yet
  * a unit a runner is executing right now is not "ready": ready-to-start and
    running are separate sets, so a concurrent resume never restarts it

The authoritative unit expansion and the result envelope live in
``scheduler/model.py`` (lane L03).  A runner result is judged by that envelope:
a failure *returned normally* is a failure, never a satisfied dependency.

A plan with units left but none ready is a stall.  ``schedule_waves`` raises
``SchedulerError`` (planning cannot proceed); ``run_all`` does NOT raise — it
returns the partial results plus each blocked unit's causal blockers, so a
stalled run is reported and persisted rather than thrown away.

Start means "handed to the caller's runner". This module executes nothing:
page dispatch is emission, not execution (see dispatch_launch.py). ``start``
fans a wave across a thread pool and contains each unit's failure, so one
failing unit never cancels the rest (spec §4.5).  A runner needs execution
ownership of a unit before it produces side effects; that ownership is the
progress file's lease (progress.py ``claim``/``heartbeat``/``complete``).

USAGE
-----
    python3 shared-utils/signature_launch/scheduler/scheduler.py PLAN.json [--json]
    python3 shared-utils/signature_launch/scheduler/test_scheduler.py

Exit 0 = schedule printed; 1 = invalid plan or stall; 2 = usage/IO.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:  # package import (shared-utils/signature_launch/scheduler/__init__.py)
    from . import model  # type: ignore[import-not-found]
except ImportError:  # direct script import
    import model  # noqa: E402  (authoritative expansion + envelope)

_CONTRACT_DIR = _HERE.parent.parent / "signature_launch_contract"

# plan array name -> lane label used by automation prerequisites
_LANES = {array: lane for array, _kind, lane in model.LANES}

# ponytail: derived map until the plan carries an explicit automation->page
# link. Upgrade when the launch planner emits page ids on the automation.
_FAMILY_PAGE_KINDS = {
    "pre_launch": ("landing", "sales"),
    "opt_in": ("landing",),
    "event_reminders": ("landing", "sales"),
    "post_sale": ("checkout", "order", "thank_you"),
    "upsell_downsell": ("checkout", "upsell", "downsell"),
    "abandoned_checkout": ("checkout",),
    "page_retargeting": ("landing", "sales"),
    "onboarding_review": ("thank_you",),
    "win_back": ("landing", "sales"),
    "failed_payment": ("checkout",),
    "conversation_ai_reply": (),  # reply wiring; the requested AI config is separate
}

_VALIDATOR = None


class SchedulerError(Exception):
    """Invalid plan, or a plan that can make no further progress."""


def _validator():
    global _VALIDATOR
    if _VALIDATOR is None:
        import importlib.util

        path = _CONTRACT_DIR / "validate_launch_plan.py"
        spec = importlib.util.spec_from_file_location("signature_launch_contract_validator", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _VALIDATOR = module
    return _VALIDATOR


def validate_plan(plan: dict) -> None:
    """Raise SchedulerError unless the contract validator accepts the plan."""
    schema = json.loads((_CONTRACT_DIR / "launch-plan.schema.json").read_text(encoding="utf-8"))
    errors = _validator().validate_plan(plan, schema)
    if errors:
        raise SchedulerError("invalid launch plan: " + "; ".join(errors))


def load_plan(path) -> dict:
    with open(path, encoding="utf-8") as handle:
        plan = json.load(handle)
    validate_plan(plan)
    return plan


def expansion(plan: dict) -> dict:
    """The authoritative expansion (see scheduler/model.py)."""
    try:
        return model.expand_plan(plan)
    except model.ExpansionError as error:
        raise SchedulerError(str(error))


def unit_index(plan: dict) -> dict:
    """id -> expanded unit (lane, array, waits_for, family, data, ...)."""
    return expansion(plan)["by_id"]


def ai_state(plan: dict) -> dict:
    """Requested AI configuration and reply-workflow wiring, kept distinct."""
    return expansion(plan)["ai"]


def _automation_pages(unit: dict, index: dict) -> set:
    """Page units whose kinds this automation family targets and that exist."""
    kinds = _FAMILY_PAGE_KINDS.get(unit.get("family"), ())
    return {
        unit_id
        for unit_id, entry in index.items()
        if entry["lane"] == "page" and entry["data"].get("kind") in kinds
    }


def _resolved_set(completed, outcomes=None) -> set:
    """Ids whose work may unlock dependents.

    ``outcomes`` (id -> envelope or runner value) is authoritative when given:
    only ``model.satisfies_dependency`` unlocks.  A plain ``completed`` set is
    accepted for callers that already made that judgement.
    """
    if outcomes is None:
        return set(completed)
    return {unit_id for unit_id, value in outcomes.items()
            if model.satisfies_dependency(value)}


def blockers(unit_id: str, index: dict, completed, outcomes=None) -> list:
    """Why this unit may not start yet. Empty list means ready.

    A dependency whose runner returned a failure is reported as failed and
    never counted complete, whether it arrived by exception or by return.
    """
    entry = index.get(unit_id)
    if entry is None:
        return ["unknown unit %s" % unit_id]
    unit = entry["data"]
    reasons = []
    waits_for = entry.get("waits_for") or unit.get("waits_for") or []
    done = _resolved_set(completed, outcomes)

    for dependency in waits_for:
        if dependency in done:
            continue
        outcome = (outcomes or {}).get(dependency)
        if outcome is None:
            reasons.append("waits for %s" % dependency)
        else:
            status = model.normalize_result(outcome)["status"]
            reasons.append("waits for %s (%s returned)" % (dependency, status))

    if entry["lane"] != "automation":
        return reasons

    # emails/texts are already covered by waits_for; the extra automation
    # rule is that the page URLs it needs must exist, not merely be planned.
    explicit_pages = [dep for dep in waits_for if dep in index and index[dep]["lane"] == "page"]
    for page_id in explicit_pages:
        if page_id in done and index[page_id]["data"].get("url") is None:
            reasons.append("page %s has no approved URL" % page_id)
    for page_id in sorted(_automation_pages(unit, index) - set(explicit_pages)):
        if page_id not in done:
            reasons.append("waits for page %s" % page_id)
        elif index[page_id]["data"].get("url") is None:
            reasons.append("page %s has no approved URL" % page_id)
    return reasons


def ready_units(plan: dict, completed, index: dict = None, skip=(),
                running=(), outcomes=None) -> list:
    """Every unit not complete, not skipped, not running, prerequisites met.

    ``running`` ids are units an execution owner already claimed; they are
    reported separately and never handed out as fresh work.
    """
    index = index if index is not None else unit_index(plan)
    done = _resolved_set(completed, outcomes)
    skipped = set(skip)
    active = set(running)
    return [
        unit_id
        for unit_id in sorted(index)
        if unit_id not in done
        and unit_id not in skipped
        and unit_id not in active
        and not blockers(unit_id, index, done)
    ]


def _stall_message(index: dict, completed: set, skip=()) -> str:
    left = sorted(set(index) - completed - set(skip))
    detail = "; ".join(
        "%s (%s)" % (unit_id, ", ".join(blockers(unit_id, index, completed)) or "unknown")
        for unit_id in left
    )
    return "stalled with %d unit(s) left: %s" % (len(left), detail)


def schedule_waves(plan: dict, index: dict = None) -> list:
    """All units grouped into waves; every ready unit shares its wave."""
    index = index if index is not None else unit_index(plan)
    completed = set()
    waves = []
    while len(completed) < len(index):
        ready = ready_units(plan, completed, index)
        if not ready:
            raise SchedulerError(_stall_message(index, completed))
        waves.append(ready)
        completed.update(ready)
    return waves


def _outcome_entry(unit_id, envelope, error=None) -> dict:
    satisfied = model.satisfies_dependency(envelope)
    return {
        "id": unit_id,
        "ok": envelope["status"] == model.VERIFIED_SUCCESS and envelope["verified"] is True,
        "terminal": satisfied,
        "status": envelope["status"],
        "verified": envelope["verified"],
        "envelope": envelope,
        "result": envelope.get("payload"),
        "error": error,
    }


def start(plan: dict, completed, runner, max_workers: int = None,
          index: dict = None, skip=(), running=(), outcomes=None) -> list:
    """Run every currently-ready unit together; return per-unit results.

    ``runner(unit_id, entry)`` is called once per ready unit in the wave.
    A runner exception is recorded as ``failed`` and never cancels the rest.
    A runner *return* is judged by ``model.normalize_result``: a normally
    returned failure is ``ok=False`` and does not satisfy dependencies.
    ``skip`` ids are never handed to the runner (already attempted this run);
    ``running`` ids belong to another execution owner and are left alone.
    """
    index = index if index is not None else unit_index(plan)
    ready = ready_units(plan, completed, index, skip, running, outcomes)
    if not ready:
        return []
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers or len(ready)) as pool:
        futures = {pool.submit(runner, unit_id, index[unit_id]): unit_id for unit_id in ready}
        for future in as_completed(futures):
            unit_id = futures[future]
            try:
                declared = model.normalize_result(future.result())
                results[unit_id] = _outcome_entry(unit_id, declared)
            except Exception as error:  # contained failure, per spec §4.5
                message = "%s: %s" % (type(error).__name__, error)
                results[unit_id] = _outcome_entry(
                    unit_id, model.envelope(model.FAILED, detail=message), error=message)
    return [dict(results[unit_id]) for unit_id in ready]


def run_all(plan: dict, runner, max_workers: int = None, index: dict = None,
            running=()) -> dict:
    """Drive plan to completion wave by wave; never raise on a stall.

    A unit is handed to the runner at most once per call: a failed unit is
    never retried here (a page retry would pay KIE twice) — it is reported as
    retryable and the caller resumes it deliberately.

    The report keeps partial results: ``completed`` (verified successes),
    ``dropped`` (client-terminal units), ``resolved`` (both), ``failed``,
    and ``blocked`` where every entry names its causal blockers.  ``stall`` is
    None only when every unit resolved.  An empty plan is explicitly empty:
    zero units, complete, percent 0 — never a fake 100% or an exception.
    """
    index = index if index is not None else unit_index(plan)
    resolved = set()
    attempted = set()
    outcomes = {}
    success, dropped, failed = [], [], []
    waves = []
    while len(attempted) < len(index):
        started = start(plan, resolved, runner, max_workers, index,
                        skip=attempted, running=running, outcomes=outcomes)
        if not started:
            break
        waves.append(started)
        for entry in started:
            unit_id = entry["id"]
            attempted.add(unit_id)
            outcomes[unit_id] = entry["envelope"]
            if entry["ok"]:
                success.append(unit_id)
            if entry["status"] == model.DROPPED:
                dropped.append(unit_id)
            elif not entry["terminal"]:
                failed.append(unit_id)
            if entry["terminal"]:
                resolved.add(unit_id)

    blocked = []
    for unit_id in sorted(set(index) - resolved):
        outcome = outcomes.get(unit_id)
        if outcome is not None:
            status = model.normalize_result(outcome)["status"]
        elif unit_id in set(running):
            status = "running"
        else:
            status = "not_started"
        blocked.append({
            "id": unit_id,
            "status": status,
            "retryable": status in (model.FAILED, model.AWAITING_FACTS),
            "blockers": blockers(unit_id, index, resolved, outcomes),
            "causal": model.causal_blockers(unit_id, index, resolved),
        })

    stall = None
    if blocked:
        stall = {
            "units": len(blocked),
            "detail": "; ".join(
                "%s (%s)" % (row["id"], ", ".join(row["blockers"]) or row["status"])
                for row in blocked),
        }

    return {
        "launch_id": plan.get("launch_id"),
        "empty": not index,
        "complete": not blocked,
        "ai": ai_state(plan),
        "waves": waves,
        "completed": sorted(success),
        "dropped": sorted(dropped),
        "resolved": sorted(resolved),
        "failed": sorted(failed),
        "blocked": blocked,
        "stall": stall,
    }


def main(argv: list) -> int:
    args = [item for item in argv if not item.startswith("--")]
    if not args:
        print("usage: scheduler.py PLAN.json [--json]", file=sys.stderr)
        return 2
    try:
        plan = load_plan(Path(args[0]))
        waves = schedule_waves(plan)
    except SchedulerError as error:
        print("FAIL %s" % error, file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print("cannot read plan: %s" % error, file=sys.stderr)
        return 2
    if "--json" in argv:
        print(json.dumps({"launch_id": plan["launch_id"], "waves": waves,
                          "ai": ai_state(plan)}, indent=2))
    else:
        for number, wave in enumerate(waves, 1):
            print("wave %d: %s" % (number, ", ".join(wave)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
