"""budget.py - N-96: the run-time budget never stops work (10D).

Checkpoints at minutes 20, 30, 40 and 45; at 60 minutes, 2 hours 30 minutes
and 3 hours the run keeps working and the automatic steps and the diagnosis
start. Work never stops for the clock and no quality rule is dropped. The
numbers live in references/time-budgets.json.
"""
CHECKPOINTS = {
    "picture_gate_passed_by": 20,
    "video_burst_back_by": 30,
    "remake_burst_back_by": 40,
    "master_joined_by": 45,
}
DIAGNOSIS_MINUTES = (60, 150, 180)
TRENDING_SLACK_MIN = 10


def _budgets(path=None):
    try:
        try:
            from .clock import load_budgets
        except ImportError:
            from clock import load_budgets
        return load_budgets(path) or {}
    except Exception:                      # noqa: BLE001
        return {}


def checkpoints(path=None):
    return dict(_budgets(path).get("checkpoints_minutes") or CHECKPOINTS)


def diagnosis_minutes(path=None):
    return sorted(_budgets(path).get("diagnosis_starts_at_minutes")
                  or DIAGNOSIS_MINUTES)


def missed_checkpoints(elapsed_min, done=None, *, path=None):
    """Checkpoints whose minute has passed and whose step is not done."""
    done = set(done or ())
    return [{"checkpoint": name, "by_minute": minute,
             "late_by": round(elapsed_min - minute, 1)}
            for name, minute in checkpoints(path).items()
            if name not in done and elapsed_min > minute]


def trending(elapsed_min, done=None, *, path=None):
    """A checkpoint missed by more than 10 minutes means the run is trending."""
    slack = _budgets(path).get("trending_overrun_minutes", TRENDING_SLACK_MIN)
    return any(item["late_by"] > slack
               for item in missed_checkpoints(elapsed_min, done, path=path))


def diagnosis_due(elapsed_min, *, path=None):
    """Which diagnosis thresholds have been reached (each starts one agent)."""
    return [minute for minute in diagnosis_minutes(path) if elapsed_min >= minute]


def phase(elapsed_min, done=None, *, path=None):
    """The clock's one word for the run; it never stops the run."""
    due = diagnosis_due(elapsed_min, path=path)
    return {"elapsed_min": round(elapsed_min, 1),
            "on_track": not missed_checkpoints(elapsed_min, done, path=path),
            "trending": trending(elapsed_min, done, path=path),
            "diagnosis_due": due,
            "never_stop": True,
            "stop": False,
            "quality_rules_dropped": [],
            "next": ("start the overrun diagnosis beside the run"
                     if due else "keep working")}


def should_stop(_elapsed_min):
    """The clock is never a reason to stop (S-40, 10D)."""
    return False


def quality_rules_dropped():
    """No quality rule is dropped for the clock (10D)."""
    return []
