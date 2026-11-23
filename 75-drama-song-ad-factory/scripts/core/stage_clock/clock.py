"""clock.py - N-02: the stage clock.

A time-budget file holds the section 10B stage table (references/time-budgets.json).
Every stage stamps its start and end here; an overrun is logged and follows the
never-restart rule: work never stops for the clock, and a stage that is already
started keeps its original start time.

Stdlib only. State lives at control/stage-clock.json inside the run folder.
"""
import json
import os
import time

BUDGET_REL = os.path.join("references", "time-budgets.json")


def _skill_root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(d, BUDGET_REL)
        if os.path.isfile(cand):
            return d
        d = os.path.dirname(d)
    return None


def budgets_path(path=None):
    return path or (_skill_root() and os.path.join(_skill_root(), BUDGET_REL))


def load_budgets(path=None):
    p = budgets_path(path)
    if not p or not os.path.isfile(p):
        return {"schema": "blackceo.time-budgets/v1", "stages": [],
                "error": "time-budget file not found"}
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def budget_for(stage_id, length_s, budgets=None):
    """Minutes allowed for one stage at the run's length (nearest listed length)."""
    budgets = budgets or load_budgets()
    for stage in budgets.get("stages", []):
        if stage.get("id") != stage_id:
            continue
        table = stage.get("minutes", {})
        keys = sorted(int(k) for k in table)
        if not keys:
            return None
        best = min(keys, key=lambda k: abs(k - int(length_s or 180)))
        return table.get(str(best))
    return None


def _atomic_write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


class StageClock:
    def __init__(self, run_dir, length_s=180, budgets=None, path=None, now=None):
        self.run_dir = os.path.abspath(os.fspath(run_dir))
        self.state_path = path or os.path.join(self.run_dir, "control", "stage-clock.json")
        self.budgets = budgets or load_budgets()
        self.now = time.time if now is None else now
        self.state = self._load()
        self.state["length_s"] = int(length_s or self.state.get("length_s") or 180)

    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = {}
        doc.setdefault("schema", "blackceo.stage-clock/v1")
        doc.setdefault("stages", {})
        doc.setdefault("overruns", [])
        doc.setdefault("stamps", [])
        return doc

    def _save(self):
        _atomic_write(self.state_path, self.state)
        return self.state

    def start(self, stage):
        """Stamp a stage's start. A second start never restarts it (N-02)."""
        t = self.now()
        rec = self.state["stages"].get(stage)
        if rec and rec.get("start") is not None:
            self.state["stamps"].append({"stage": stage, "kind": "start-repeat",
                                         "at": t, "kept": rec["start"]})
            self._save()
            return {"stage": stage, "start": rec["start"], "restarted": False}
        self.state["stages"][stage] = {"start": t, "end": None}
        self.state["stamps"].append({"stage": stage, "kind": "start", "at": t})
        self._save()
        return {"stage": stage, "start": t, "restarted": False}

    def end(self, stage):
        """Stamp a stage's end, log an overrun, never stop anything."""
        t = self.now()
        rec = self.state["stages"].setdefault(stage, {"start": t, "end": None})
        if rec.get("start") is None:
            rec["start"] = t
        if rec.get("end") is not None:
            return {"stage": stage, "end": rec["end"], "elapsed_minutes":
                    rec.get("elapsed_minutes"), "overrun": rec.get("overrun", False),
                    "restarted": False}
        rec["end"] = t
        elapsed_min = round((t - rec["start"]) / 60.0, 3)
        allowed = budget_for(stage, self.state.get("length_s"), self.budgets)
        overrun = bool(allowed is not None and elapsed_min > allowed)
        rec["elapsed_minutes"] = elapsed_min
        rec["budget_minutes"] = allowed
        rec["overrun"] = overrun
        if overrun:
            self.state["overruns"].append({
                "stage": stage, "elapsed_minutes": elapsed_min,
                "budget_minutes": allowed, "at": t,
                "action": "logged; work never stops for the clock (never restart)",
            })
        self.state["stamps"].append({"stage": stage, "kind": "end", "at": t})
        self._save()
        return {"stage": stage, "end": t, "elapsed_minutes": elapsed_min,
                "budget_minutes": allowed, "overrun": overrun, "restarted": False}

    def stamp(self, stage, kind="start"):
        return self.start(stage) if kind == "start" else self.end(stage)

    def overruns(self):
        return list(self.state.get("overruns", []))

    def elapsed_minutes(self):
        starts = [r.get("start") for r in self.state["stages"].values() if r.get("start")]
        if not starts:
            return 0.0
        return round((self.now() - min(starts)) / 60.0, 3)

    def snapshot(self):
        return {"schema": "blackceo.stage-clock-snapshot/v1",
                "now": self.now(), "elapsed_minutes": self.elapsed_minutes(),
                "length_s": self.state.get("length_s"),
                "stages": self.state.get("stages", {}),
                "overruns": self.overruns()}
