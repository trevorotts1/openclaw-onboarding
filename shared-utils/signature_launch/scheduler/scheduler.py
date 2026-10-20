#!/usr/bin/env python3
"""scheduler.py — Signature Launch unit scheduler (checklist S1, stdlib only).

WHY THIS EXISTS
---------------
Every launch unit (page, email sequence, text set, automation) declares
``waits_for``: the units that must be COMPLETE before it may start. This
module turns that field into waves and enforces the two readiness rules the
runtime swarm depends on:

  * every unit whose ``waits_for`` is complete starts in the SAME wave —
    ready work is never queued behind unrelated work
  * an automation additionally waits for the page URLs its family targets:
    a completed page whose ``url`` is still null has no approved URL, so the
    automation cannot reference it yet. Emails and texts are gated by the
    automation's own ``waits_for`` entries.

A plan with units left but none ready is a stall: ``SchedulerError`` names
the blocked units and why. Nothing is silently dropped.

Start means "handed to the caller's runner". This module executes nothing:
page dispatch is emission, not execution (see dispatch_launch.py). ``start``
fans a wave across a thread pool and contains each unit's failure, so one
failing unit never cancels the rest (spec §4.5).

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
_CONTRACT_DIR = _HERE.parent.parent / "signature_launch_contract"

# plan array name -> lane label used by automation prerequisites
_LANES = {
    "pages": "page",
    "email_sequences": "email",
    "text_sets": "text",
    "automations": "automation",
}

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
    "conversation_ai_reply": (),  # attaches after the reply workflow exists
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


def unit_index(plan: dict) -> dict:
    """id -> {lane, array, data} for every unit in the plan."""
    index = {}
    for array, lane in _LANES.items():
        for unit in plan.get(array, []):
            index[unit["id"]] = {"lane": lane, "array": array, "data": unit}
    return index


def _automation_pages(unit: dict, index: dict) -> set:
    """Page units whose kinds this automation family targets and that exist."""
    kinds = _FAMILY_PAGE_KINDS.get(unit.get("family"), ())
    return {
        unit_id
        for unit_id, entry in index.items()
        if entry["lane"] == "page" and entry["data"].get("kind") in kinds
    }


def blockers(unit_id: str, index: dict, completed: set) -> list:
    """Why this unit may not start yet. Empty list means ready."""
    entry = index[unit_id]
    unit = entry["data"]
    reasons = []
    waits_for = unit.get("waits_for", [])

    for dependency in waits_for:
        if dependency not in completed:
            reasons.append("waits for %s" % dependency)
    if entry["lane"] != "automation":
        return reasons

    # emails/texts are already covered by waits_for; the extra automation
    # rule is that the page URLs it needs must exist, not merely be planned.
    explicit_pages = [dep for dep in waits_for if index[dep]["lane"] == "page"]
    for page_id in explicit_pages:
        if page_id in completed and index[page_id]["data"].get("url") is None:
            reasons.append("page %s has no approved URL" % page_id)
    for page_id in sorted(_automation_pages(unit, index) - set(explicit_pages)):
        if page_id not in completed:
            reasons.append("waits for page %s" % page_id)
        elif index[page_id]["data"].get("url") is None:
            reasons.append("page %s has no approved URL" % page_id)
    return reasons


def ready_units(plan: dict, completed, index: dict = None, skip=()) -> list:
    """Every unit not yet complete, not skipped, whose prerequisites are met."""
    index = index if index is not None else unit_index(plan)
    done = set(completed)
    skipped = set(skip)
    return [
        unit_id
        for unit_id in sorted(index)
        if unit_id not in done
        and unit_id not in skipped
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


def start(plan: dict, completed, runner, max_workers: int = None,
          index: dict = None, skip=()) -> list:
    """Run every currently-ready unit together; return per-unit results.

    ``runner(unit_id, entry)`` is called once per ready unit in the wave.
    A runner exception is recorded as ``ok=False`` and never cancels the rest.
    ``skip`` ids are never handed to the runner (already attempted this run).
    """
    index = index if index is not None else unit_index(plan)
    ready = ready_units(plan, completed, index, skip)
    if not ready:
        return []
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers or len(ready)) as pool:
        futures = {pool.submit(runner, unit_id, index[unit_id]): unit_id for unit_id in ready}
        for future in as_completed(futures):
            unit_id = futures[future]
            try:
                results[unit_id] = {"ok": True, "result": future.result()}
            except Exception as error:  # contained failure, per spec §4.5
                results[unit_id] = {"ok": False, "error": "%s: %s" % (type(error).__name__, error)}
    return [dict(id=unit_id, **results[unit_id]) for unit_id in ready]


def run_all(plan: dict, runner, max_workers: int = None, index: dict = None) -> dict:
    """Drive plan to completion wave by wave.

    A unit is handed to the runner at most once per call: a failed unit is
    never retried here (a page retry would pay KIE twice) — it stays blocked
    in the report until the caller resumes it deliberately.
    """
    index = index if index is not None else unit_index(plan)
    completed = set()
    attempted = set()
    waves = []
    while len(attempted) < len(index):
        started = start(plan, completed, runner, max_workers, index, skip=attempted)
        if not started:
            raise SchedulerError(_stall_message(index, completed, skip=attempted))
        waves.append(started)
        attempted.update(entry["id"] for entry in started)
        completed.update(entry["id"] for entry in started if entry["ok"])
    return {
        "launch_id": plan.get("launch_id"),
        "waves": waves,
        "completed": sorted(completed),
        "blocked": sorted(set(index) - completed),
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
        print(json.dumps({"launch_id": plan["launch_id"], "waves": waves}, indent=2))
    else:
        for number, wave in enumerate(waves, 1):
            print("wave %d: %s" % (number, ", ".join(wave)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
