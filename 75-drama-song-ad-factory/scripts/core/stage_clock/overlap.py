"""overlap.py - N-68: the stages that run beside others (section 10B).

Character masters start when the look is locked and the cast is named.
Picture remakes are sent the minute a check fails. The remake burst goes when
9 in 10 clips are back. Side-by-side passes, overlays and the placeholder
timeline run beside the bursts. The action question joins the one vision call
(3F.4).

Stdlib only. The table is read from references/time-budgets.json so the
schedule has one source.
"""
try:
    from .clock import load_budgets
except ImportError:                                  # solo-file invocation
    from clock import load_budgets


def overlap_table(budgets=None):
    budgets = budgets or load_budgets()
    return list(budgets.get("overlaps", []))


def concurrent(stage, budgets=None):
    """Everything that may run at the same time as ``stage``."""
    out = []
    for row in overlap_table(budgets):
        if row.get("stage") == stage:
            out.extend(row.get("runs_beside", []))
        elif stage in row.get("runs_beside", []):
            out.append(row.get("stage"))
    return sorted(set(x for x in out if x))


def can_start(stage, state, budgets=None):
    """May the stage start now? Every ``starts_when`` condition must hold.

    ``state`` carries booleans such as look_locked, cast_named, check_failed,
    nine_in_ten_clips_back, pictures_picked, clips_landing,
    storyboard_approved.
    """
    for row in overlap_table(budgets):
        if row.get("stage") != stage:
            continue
        needs = list(row.get("starts_when") or [])
        joins = row.get("joins")
        waiting = [n for n in needs if not (state or {}).get(n)]
        return {"ok": not waiting, "stage": stage, "waiting_for": waiting,
                "runs_beside": list(row.get("runs_beside") or []),
                "gates": list(row.get("gates") or []),
                "joins": joins,
                "detail": None if not waiting else
                "%s waits for %s" % (stage, ", ".join(waiting))}
    return {"ok": False, "stage": stage, "waiting_for": [],
            "detail": "no overlap row names %r" % stage}


def ready_stages(state, budgets=None):
    """Every stage whose start conditions are already met, in table order."""
    out = []
    for row in overlap_table(budgets):
        stage = row.get("stage")
        if stage and can_start(stage, state, budgets)["ok"]:
            out.append(stage)
    return out
