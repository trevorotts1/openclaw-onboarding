"""
Adaptive 5-layer scoring weights based on task category and interaction mode.

Replaces the static (25/25/20/15/15) weights in select-persona-for-task.py with
a task-taxonomy-driven matrix.

Different tasks need different weighting:
- Pure execution tasks (write an email): Task Fit should weight ~40%
- Coaching tasks: Owner Values should weight ~50%+
- Strategic decisions: Company Mission should weight ~40%
- Routine ops: Department KPIs should weight ~30%

Usage:
    from adaptive_weights import get_weights_for_task
    weights = get_weights_for_task("write a follow-up email", mode="leadership")
    # -> {'mission': 0.10, 'owner_values': 0.20, 'company_kpis': 0.10, 'dept_kpis': 0.20, 'task_fit': 0.40}
"""

import os

# Default weights — PRD §10 canonical (20/25/20/20/15). Sums to 1.0.
# This is the single source of truth across v1, v2, and the PRD. Earlier
# versions of v1 (select-persona-for-task.py) used 25/25/20/15/15 and v2 used
# 20/30/15/15/20 — both wrong. Wave 3 unified them to this set.
DEFAULT_WEIGHTS = {
    "mission":      0.20,
    "owner_values": 0.25,
    "company_kpis": 0.20,
    "dept_kpis":    0.20,
    "task_fit":     0.15,
}

# Override profiles keyed by (task_category, mode). All values sum to 1.0.
WEIGHT_PROFILES = {
    # ---- Execution-heavy tasks: task fit matters most ----
    ("email-outreach", "leadership"): {
        "mission": 0.10, "owner_values": 0.20, "company_kpis": 0.10,
        "dept_kpis": 0.20, "task_fit": 0.40,
    },
    ("content-write", "leadership"): {
        "mission": 0.10, "owner_values": 0.30, "company_kpis": 0.10,
        "dept_kpis": 0.10, "task_fit": 0.40,
    },
    ("social-post", "leadership"): {
        "mission": 0.10, "owner_values": 0.30, "company_kpis": 0.10,
        "dept_kpis": 0.15, "task_fit": 0.35,
    },
    ("video-script", "leadership"): {
        "mission": 0.10, "owner_values": 0.30, "company_kpis": 0.10,
        "dept_kpis": 0.15, "task_fit": 0.35,
    },
    ("design", "leadership"): {
        "mission": 0.15, "owner_values": 0.25, "company_kpis": 0.05,
        "dept_kpis": 0.15, "task_fit": 0.40,
    },

    # ---- Coaching tasks: owner values dominate ----
    ("coaching-prompt", "coaching"): {
        "mission": 0.10, "owner_values": 0.55, "company_kpis": 0.05,
        "dept_kpis": 0.10, "task_fit": 0.20,
    },
    ("review-feedback", "coaching"): {
        "mission": 0.10, "owner_values": 0.50, "company_kpis": 0.05,
        "dept_kpis": 0.10, "task_fit": 0.25,
    },

    # ---- Strategic decisions: mission dominates ----
    ("strategy", "leadership"): {
        "mission": 0.40, "owner_values": 0.25, "company_kpis": 0.20,
        "dept_kpis": 0.05, "task_fit": 0.10,
    },

    # ---- Routine ops: department KPIs dominate ----
    ("ops", "leadership"): {
        "mission": 0.10, "owner_values": 0.15, "company_kpis": 0.10,
        "dept_kpis": 0.45, "task_fit": 0.20,
    },
    ("customer-service", "leadership"): {
        "mission": 0.15, "owner_values": 0.25, "company_kpis": 0.05,
        "dept_kpis": 0.30, "task_fit": 0.25,
    },

    # ---- Sensitive: mission + owner values dominate ----
    ("legal", "leadership"): {
        "mission": 0.30, "owner_values": 0.30, "company_kpis": 0.20,
        "dept_kpis": 0.10, "task_fit": 0.10,
    },
    ("finance", "leadership"): {
        "mission": 0.20, "owner_values": 0.30, "company_kpis": 0.30,
        "dept_kpis": 0.10, "task_fit": 0.10,
    },
    ("hr", "leadership"): {
        "mission": 0.25, "owner_values": 0.30, "company_kpis": 0.15,
        "dept_kpis": 0.10, "task_fit": 0.20,
    },

    # ---- Research: balanced with task fit edge ----
    ("research", "leadership"): {
        "mission": 0.15, "owner_values": 0.20, "company_kpis": 0.15,
        "dept_kpis": 0.15, "task_fit": 0.35,
    },
}


# ─── CRAFT/SPECIALIST task-type-aware weighting (v14.15.0) ──────────────────
# The WEIGHT_PROFILES above are already task-type-aware in INTENT (design/content
# lean task_fit; strategy/legal lean mission). Two defects stopped that intent
# from reaching CRAFT tasks in production:
#   1. get_weights_for_task() could not import the REAL category inferer (the
#      file is HYPHENATED — infer-task-category.py — so `import infer_task_category`
#      raised ModuleNotFoundError) and silently fell back to the coarse inline
#      heuristic, which misclassifies craft tasks. e.g. "Visually sketchnote and
#      map our customer-onboarding process" matched the inline "process" keyword
#      and resolved to OPS (task_fit 0.20) instead of DESIGN (task_fit 0.40), so
#      the carefully-tuned design profile was DEAD CODE. _resolve_infer_task_category()
#      loads the hyphenated file by path (identical to persona-selector-v2.py's own
#      loader) so weighting uses the SAME authoritative category as the selector —
#      one source of category truth.
#   2. Even the design profile (task_fit 0.40) lets a generic on-brand persona's
#      company_kpis edge out-score the true specialist's ~0.05 task_fit lead. The
#      CRAFT_TASK_FIT_FLOOR guarantees craft categories weight the domain-expertise
#      layer at >= floor, redistributing the shortfall OUT of the four company-fit
#      layers. Principle: for CRAFT work the question is "who is the best
#      specialist", not "who best fits company revenue KPIs". (The persona-selector
#      domain-primary-match bonus is the decisive companion mechanism.)
# Both are provably neutral on non-craft categories (CRAFT_CATEGORIES gate) and
# env-tunable for safe field tuning. CRAFT_TASK_FIT_FLOOR=0 disables defect-2 fix.
CRAFT_CATEGORIES = {
    "design", "video-edit", "video-script", "content-write", "social-post",
    "email-outreach",
}


def _resolve_infer_task_category():
    """Load the REAL infer-task-category.py (hyphenated) by path, or None.

    Mirrors the loader in persona-selector-v2.py so the weighting layer and the
    selection layer always agree on a task's category. Falls back to None (caller
    uses the inline heuristic) only if the file is genuinely absent / unloadable.
    """
    import importlib.util as _ilu
    from pathlib import Path as _P
    here = _P(__file__).resolve().parent
    candidates = [
        here.parent / "23-ai-workforce-blueprint" / "scripts" / "infer-task-category.py",
        here / "infer-task-category.py",
    ]
    for c in candidates:
        if c.is_file():
            try:
                spec = _ilu.spec_from_file_location("itc_for_weights", str(c))
                mod = _ilu.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                fn = getattr(mod, "infer_task_category", None)
                if callable(fn):
                    return fn
            except Exception:
                continue
    return None


_REAL_INFER = _resolve_infer_task_category()


def _craft_task_fit_floor() -> float:
    """Minimum task_fit weight for CRAFT categories (env CRAFT_TASK_FIT_FLOOR)."""
    try:
        v = float(os.environ.get("CRAFT_TASK_FIT_FLOOR", "0.40"))
    except (TypeError, ValueError):
        v = 0.40
    return max(0.0, min(v, 0.85))


def _apply_craft_emphasis(weights: dict, category: str) -> dict:
    """Raise task_fit to at least CRAFT_TASK_FIT_FLOOR for CRAFT categories,
    redistributing the shortfall proportionally OUT of the four company-fit
    layers (preserving their relative shape). No-op when category is non-craft,
    the floor is already met, or the floor is 0. Always re-normalised to 1.0."""
    if category not in CRAFT_CATEGORIES:
        return weights
    floor = _craft_task_fit_floor()
    cur = weights.get("task_fit", 0.0)
    if floor <= 0.0 or cur >= floor:
        return weights
    others = {k: v for k, v in weights.items() if k != "task_fit"}
    others_sum = sum(others.values())
    remainder = 1.0 - floor
    if others_sum <= 0:
        n = max(len(others), 1)
        scaled = {k: remainder / n for k in others}
    else:
        scaled = {k: v / others_sum * remainder for k, v in others.items()}
    scaled["task_fit"] = floor
    return _normalize(scaled)


def _normalize(weights: dict) -> dict:
    """Ensure weights sum to 1.0 (auto-correct rounding drift)."""
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    if abs(total - 1.0) <= 0.01:
        return weights
    return {k: v / total for k, v in weights.items()}


def get_weights_for_task(task_text: str, mode: str = "leadership") -> dict:
    """
    Get the appropriate weight profile for this task.

    Args:
        task_text: The task description (used for category inference)
        mode: 'leadership' | 'coaching' | 'hybrid'

    Returns:
        dict with keys: mission, owner_values, company_kpis, dept_kpis, task_fit
        All values sum to 1.0.
    """
    # Resolve the task category using the REAL (hyphenated) inferer loaded by
    # path — the SAME authoritative inference persona-selector-v2.py uses for
    # Stage-B funnelling and the task_category output. The inline heuristic is
    # used only when that file is genuinely unavailable (keeps this module
    # usable standalone). See _resolve_infer_task_category() for why the old
    # `import infer_task_category` always failed.
    category = "general"
    try:
        if _REAL_INFER is not None:
            category = _REAL_INFER(task_text)
        else:
            category = _inline_infer_category(task_text)
    except Exception:
        category = _inline_infer_category(task_text)

    # For hybrid mode, average between leadership and coaching weights
    if mode == "hybrid":
        leader = WEIGHT_PROFILES.get((category, "leadership"))
        coach = WEIGHT_PROFILES.get((category, "coaching"))
        if leader and coach:
            combined = {k: (leader[k] + coach[k]) / 2 for k in DEFAULT_WEIGHTS}
            return _apply_craft_emphasis(_normalize(combined), category)
        # Fall through to single-mode lookup
        mode = "leadership"

    profile = WEIGHT_PROFILES.get((category, mode))
    base = _normalize(profile) if profile else DEFAULT_WEIGHTS.copy()
    # CRAFT task-type-aware emphasis (no-op on non-craft categories).
    return _apply_craft_emphasis(base, category)


def _inline_infer_category(task_text: str) -> str:
    """Inline minimal fallback if infer_task_category module isn't available."""
    text = task_text.lower()
    quick = {
        "email-outreach":    ["email", "follow-up", "follow up", "cold email"],
        "content-write":     ["article", "blog", "long-form", "essay"],
        "social-post":       ["social", "instagram", "tiktok", "linkedin", "twitter"],
        "video-script":      ["script", "video", "reel", "vsl"],
        "design":            ["design", "graphic", "logo", "mockup"],
        "strategy":          ["strategy", "plan", "roadmap", "vision"],
        "ops":               ["sop", "process", "workflow", "automation"],
        "finance":           ["budget", "p&l", "cashflow", "forecast", "pricing"],
        "legal":             ["contract", "nda", "terms", "policy", "compliance"],
        "hr":                ["hire", "fire", "onboard", "recruit"],
        "customer-service":  ["refund", "ticket", "support", "complaint"],
        "coaching-prompt":   ["stuck", "decide", "advice", "help me think"],
        "review-feedback":   ["review my", "critique my", "feedback on my"],
        "research":          ["research", "analyze", "investigate", "compile"],
    }
    best_cat = "general"
    best_score = 0
    for cat, kws in quick.items():
        score = sum(1 for k in kws if k in text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--mode", default="leadership", choices=["leadership", "coaching", "hybrid"])
    args = parser.parse_args()
    weights = get_weights_for_task(args.task, args.mode)
    print(json.dumps({"task": args.task, "mode": args.mode, "weights": weights}, indent=2))
