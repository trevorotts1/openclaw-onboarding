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

# Default weights (used as fallback when no specific profile matches)
DEFAULT_WEIGHTS = {
    "mission":      0.20,
    "owner_values": 0.30,
    "company_kpis": 0.15,
    "dept_kpis":    0.15,
    "task_fit":     0.20,
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
    # Try to import infer_task_category from the workforce scripts folder
    category = "general"
    try:
        import sys
        from pathlib import Path
        scripts_dir = Path(__file__).parent.parent / "23-ai-workforce-blueprint" / "scripts"
        if scripts_dir.exists() and str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from infer_task_category import infer_task_category  # type: ignore
        category = infer_task_category(task_text)
    except Exception:
        # Inline minimal fallback so this module stays usable standalone
        category = _inline_infer_category(task_text)

    # For hybrid mode, average between leadership and coaching weights
    if mode == "hybrid":
        leader = WEIGHT_PROFILES.get((category, "leadership"))
        coach = WEIGHT_PROFILES.get((category, "coaching"))
        if leader and coach:
            combined = {k: (leader[k] + coach[k]) / 2 for k in DEFAULT_WEIGHTS}
            return _normalize(combined)
        # Fall through to single-mode lookup
        mode = "leadership"

    profile = WEIGHT_PROFILES.get((category, mode))
    if not profile:
        return DEFAULT_WEIGHTS.copy()
    return _normalize(profile)


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
