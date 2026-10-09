#!/usr/bin/env python3
"""Control CLI for the DEL-16 shot planner (PKG-07-U2).

Stdlib only. One JSON envelope on stdout, exit code agrees with outcome,
same map as the skill's control CLI (ok 0, error 1, waiting 2, parked 3,
rejected 4). Commands:

  vocabulary  print the full camera vocabulary
  plan        build a plan of shot briefs from a shot-spec list
  check       run every DEL-16 rule over a plan file

A plan file: {"briefs": [...], "transitions": [...], "scenes": {...}} or a
bare list of briefs. Briefs may be built from specs: a spec is a dict of
build_shot_brief keyword args (plus any override keys the checks read).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import brief as B          # noqa: E402
import rules as R          # noqa: E402
import vocabulary as V     # noqa: E402

SCHEMA_VERSION = "blackceo.shot-planner-cli/v1"
TOOL_VERSION = V.TOOL_VERSION
EXIT = {"ok": 0, "error": 1, "waiting": 2, "parked": 3, "rejected": 4}


def envelope(command, outcome, reason_code, next_action, data=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "command": command,
        "outcome": outcome,
        "reason_code": reason_code,
        "next_action": next_action,
        "evidence": [],
        "data": data or {},
    }


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _brief_from_spec(spec):
    """build_shot_brief(**spec) with a few read-through defaults."""
    if not isinstance(spec, dict):
        raise B.BriefError("BAD_SPEC", "brief spec must be an object")
    args = dict(spec)
    overrides = {}
    for key in ("camera_motivation", "subject_position", "crosses_axis",
                "axis_cross_motivation", "direction_change"):
        if key in args:
            overrides[key] = args.pop(key)
    try:
        shot = B.build_shot_brief(**args)
    except TypeError as exc:
        raise B.BriefError("BAD_SPEC", "brief spec: %s" % exc)
    shot.update(overrides)
    return shot


def cmd_vocabulary(_args):
    return envelope("vocabulary", "ok", "VOCABULARY_OK",
                    "vocabulary printed", V.full_vocabulary())


def cmd_plan(args):
    try:
        specs = _load_json(args.specs)
    except (OSError, ValueError) as exc:
        return envelope("plan", "error", "BAD_SPECS", str(exc))
    if isinstance(specs, dict):
        specs = specs.get("briefs")
    if not isinstance(specs, list) or not specs:
        return envelope("plan", "error", "BAD_SPECS",
                        "specs file must hold a list of brief specs")
    built = []
    for i, spec in enumerate(specs):
        try:
            built.append(_brief_from_spec(spec))
        except B.BriefError as exc:
            return envelope("plan", "rejected", exc.code,
                            "briefs[%d]: %s" % (i, exc))
    result = R.run_rule_checks(built)
    outcome = "ok" if result["outcome"] == "ok" else "rejected"
    return envelope("plan", outcome, result["reason_code"],
                    "plan built; run check or fix the briefs",
                    {"briefs": built, "rule_result": result})


def _plan_briefs(plan):
    """Briefs + transitions + scenes from a plan file's parsed shape."""
    if isinstance(plan, list):
        return plan, [], None
    if isinstance(plan, dict):
        return (plan.get("briefs"), plan.get("transitions"),
                plan.get("scenes"))
    return None, None, None


def cmd_check(args):
    try:
        plan = _load_json(args.plan)
    except (OSError, ValueError) as exc:
        return envelope("check", "error", "BAD_PLAN", str(exc))
    briefs, transitions, scenes = _plan_briefs(plan)
    if not isinstance(briefs, list):
        return envelope("check", "error", "BAD_PLAN",
                        "plan must be a list of briefs or an object with "
                        "briefs[]")
    result = R.run_rule_checks(briefs, transitions=transitions,
                               scenes=scenes)
    outcome = "ok" if result["outcome"] == "ok" else "rejected"
    nxt = ("plan passes every DEL-16 rule"
           if outcome == "ok" else
           "fix the briefs: %d reason(s)" % len(result["reasons"]))
    return envelope("check", outcome, result["reason_code"], nxt,
                    {"rule_result": result,
                     "planning_ranges_label": V.PLANNING_RANGE_LABEL})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="camera_shot_rules", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("vocabulary", help="print the full vocabulary")
    p_plan = sub.add_parser("plan", help="build briefs from specs")
    p_plan.add_argument("--specs", required=True)
    p_check = sub.add_parser("check", help="run every DEL-16 rule")
    p_check.add_argument("--plan", required=True)
    args = ap.parse_args(argv)
    if args.command == "vocabulary":
        out = cmd_vocabulary(args)
    elif args.command == "plan":
        out = cmd_plan(args)
    else:
        out = cmd_check(args)
    sys.stdout.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return EXIT[out["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
