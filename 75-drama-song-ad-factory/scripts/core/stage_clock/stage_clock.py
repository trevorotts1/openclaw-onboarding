#!/usr/bin/env python3
"""stage_clock.py - N-02: the stage clock. Stdlib only.

A time-budget file (references/time-budgets.json) holds the section 10B stage
table and each stage's average and ceiling minutes. Each stage stamps its start
and its end into ``control/stage-clock.json``. When a stage runs past its
ceiling the clock records an OVERRUN and returns the one instruction the plan
allows: log it and continue, never restart. The clock never stops a run.

State file (control/stage-clock.json):
  {"schema": "blackceo.stage-clock/v1",
   "run_started_unix": <float>,
   "stages": {"2": {"start_unix":..,"end_unix":..,"minutes":..,"overrun":bool,
                    "budget_avg":..,"budget_ceiling":..}},
   "overruns": [{"stage":..,"minutes":..,"ceiling":..}]}
"""
import argparse
import json
import os
import time

SCHEMA = "blackceo.stage-clock/v1"
STATE_REL = os.path.join("control", "stage-clock.json")
NEVER_RESTART = "logged; never restart: the run keeps working (section 10D)"


def _skill_root():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    while d != os.path.dirname(d):
        candidate = os.path.join(d, "references", "time-budgets.json")
        if os.path.isfile(candidate):
            return d
        d = os.path.dirname(d)
    return None


def budget_path():
    root = _skill_root()
    return os.path.join(root, "references", "time-budgets.json") if root else None


def load_budgets(path=None):
    path = path or budget_path()
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("time-budgets.json not found: %r" % (path,))
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc.get("stage_table"), list) or "checkpoints_min" not in doc:
        raise ValueError("time-budgets.json needs stage_table and checkpoints_min")
    return doc


def _state_path(run_dir):
    return os.path.join(run_dir, STATE_REL)


def _read_state(run_dir):
    path = _state_path(run_dir)
    if not os.path.isfile(path):
        return {"schema": SCHEMA, "stages": {}, "overruns": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_state(run_dir, state):
    path = _state_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


class StageClock:
    def __init__(self, run_dir=None, budgets=None, state=None, now=None):
        self.run_dir = run_dir
        self.budgets = budgets if budgets is not None else load_budgets()
        self._now = now or time.time
        if state is not None:
            self.state = state
        elif run_dir:
            self.state = _read_state(run_dir)
        else:
            self.state = {"schema": SCHEMA, "stages": {}, "overruns": []}

    # -- time ------------------------------------------------------------
    def _clock(self):
        return float(self._now())

    def run_started(self):
        return self.state.get("run_started_unix")

    def elapsed_min(self, at=None):
        start = self.run_started()
        if start is None:
            return 0.0
        return max(0.0, ((at if at is not None else self._clock()) - start) / 60.0)

    # -- stage stamps ----------------------------------------------------
    def stage_budget(self, stage_id):
        row = (self.budgets.get("stage_budget_min") or {}).get(str(stage_id)) or {}
        return row.get("average"), row.get("ceiling")

    def stamp_start(self, stage_id, at=None):
        at = float(at if at is not None else self._clock())
        self.state.setdefault("run_started_unix", at)
        row = self.state["stages"].setdefault(str(stage_id), {})
        row["start_unix"] = at
        row.pop("end_unix", None)
        row.pop("minutes", None)
        self._persist()
        return {"stage": str(stage_id), "started_unix": at}

    def stamp_end(self, stage_id, at=None):
        at = float(at if at is not None else self._clock())
        sid = str(stage_id)
        row = self.state["stages"].get(sid)
        if row is None or "start_unix" not in row:
            raise ValueError("stage %r has no start stamp" % sid)
        row["end_unix"] = at
        minutes = round((at - row["start_unix"]) / 60.0, 3)
        row["minutes"] = minutes
        avg, ceiling = self.stage_budget(sid)
        row["budget_avg"], row["budget_ceiling"] = avg, ceiling
        overrun = ceiling is not None and minutes > ceiling
        row["overrun"] = bool(overrun)
        result = {"stage": sid, "minutes": minutes, "budget_avg": avg,
                  "budget_ceiling": ceiling, "overrun": bool(overrun)}
        if overrun:
            record = {"stage": sid, "minutes": minutes, "ceiling": ceiling,
                      "logged_at_unix": at}
            self.state.setdefault("overruns", []).append(record)
            result["action"] = NEVER_RESTART
        self._persist()
        return result

    def stage_state(self, stage_id):
        return self.state.get("stages", {}).get(str(stage_id)) or {}

    def _persist(self):
        if self.run_dir:
            _write_state(self.run_dir, self.state)

    def summary(self):
        return {"elapsed_min": round(self.elapsed_min(), 3),
                "stages": self.state.get("stages", {}),
                "overruns": self.state.get("overruns", []),
                "never_restart": NEVER_RESTART}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "end"):
        p = sub.add_parser(name)
        p.add_argument("--stage", required=True)
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    clock = StageClock(args.run_dir)
    if args.cmd == "start":
        out = clock.stamp_start(args.stage)
    elif args.cmd == "end":
        out = clock.stamp_end(args.stage)
    else:
        out = clock.summary()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
