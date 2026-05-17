#!/usr/bin/env python3
"""
Persona Selector v2 — v2.1-aware persona selection.

The v1.x `select-persona-for-task.py` still works for backward compatibility.
This v2 version is a DROP-IN ALTERNATIVE that adds:

1. Stickiness check — looks at the `persona_assignment` table (Command Center DB)
   first. If a sticky assignment exists for (department, task_category) with
   score ≥0.5, returns it without re-scoring.
2. Adaptive weights — uses `adaptive_weights.get_weights_for_task()` instead of
   static (25/25/20/15/15).
3. Behavioral profile reading — Layer 2 (Owner Values) reads the v2.0 Ch 12
   `## Behavioral Identity Profile` section of USER.md instead of the v1.1
   value-based section.
4. Persona version pinning — records persona_version on the task at dispatch.
5. Hybrid mode — when detect_interaction_mode returns 'hybrid', selects TWO
   personas (one per mode) instead of one.
6. Emit task_category in the output so the dashboard / Command Center can
   write to persona_assignment for stickiness on the NEXT task.

Output: JSON with persona_id, persona_name, score, interaction_mode, breakdown,
and (if hybrid) secondary_persona_*.

Usage:
    python3 23-ai-workforce-blueprint/scripts/persona-selector-v2.py \
        --task "write a follow-up email to the prospect" \
        --department sales \
        --format json
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))

from detect_platform import get_openclaw_paths  # type: ignore
from adaptive_weights import get_weights_for_task, DEFAULT_WEIGHTS  # type: ignore

try:
    from infer_task_category import infer_task_category  # type: ignore
except ImportError:
    def infer_task_category(task_text: str) -> str:
        return "general"


# -------- Coaching/Leadership/Hybrid mode detection (copied from v1 for portability) --------
COACHING_SIGNALS = [
    "i'm stuck", "i don't know", "help me decide", "what should i do",
    "i'm not sure", "can you help me", "i feel", "i'm struggling",
    "advice", "should i", "what do you think", "i need guidance",
    "confused", "overwhelmed", "not working", "failing", "lost",
    "perspective", "opinion", "feedback on my", "review my thinking",
]
LEADERSHIP_SIGNALS = [
    "write", "create", "build", "design", "publish", "send", "post",
    "analyze", "research", "draft", "update", "edit", "format",
    "generate", "produce", "execute", "implement", "run", "deploy",
    "schedule", "automate", "set up", "configure", "test",
]


def detect_interaction_mode(task_description: str) -> str:
    """Returns 'leadership' | 'coaching' | 'hybrid'."""
    task_lower = task_description.lower()
    c_score = sum(1 for s in COACHING_SIGNALS if s in task_lower)
    l_score = sum(1 for s in LEADERSHIP_SIGNALS if s in task_lower)
    if c_score >= 2 and l_score >= 2:
        return "hybrid"
    return "coaching" if c_score > l_score else "leadership"


# -------- Dashboard DB lookups (stickiness + weight overrides) --------
def find_dashboard_db() -> Path:
    """Locate mission-control.db across platforms."""
    candidates = []
    if "DASHBOARD_DB_PATH" in os.environ:
        candidates.append(Path(os.environ["DASHBOARD_DB_PATH"]))
    candidates.extend([
        Path("/data/mission-control/mission-control.db"),
        Path.home() / "projects" / "mission-control" / "mission-control.db",
        Path.home() / "blackceo-command-center" / "mission-control.db",
    ])
    for c in candidates:
        if c.exists():
            return c
    return Path("")


def check_sticky_assignment(department_id: str, task_category: str, db_path: Path):
    """Returns sticky assignment dict or None."""
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("""
            SELECT persona_id, persona_name, persona_mode, persona_version, last_score
            FROM persona_assignment
            WHERE department_id = ? AND task_category = ?
        """, (department_id, task_category))
        row = cur.fetchone()
        conn.close()
        if row and row[4] is not None and row[4] >= 0.5:
            return {
                "persona_id": row[0],
                "persona_name": row[1] or row[0],
                "persona_mode": row[2],
                "persona_version": row[3] or 1,
                "last_score": row[4],
            }
    except sqlite3.Error:
        return None
    return None


def apply_weight_overrides(persona_id: str, base_score: float, department_id: str,
                            task_category: str, db_path: Path) -> tuple:
    """Returns (adjusted_score, applied_factor)."""
    if not db_path or not db_path.exists():
        return base_score, 1.0
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("""
            SELECT adjustment_factor FROM persona_weight_overrides
            WHERE persona_id = ?
              AND (department_id = ? OR department_id IS NULL)
              AND (task_category = ? OR task_category IS NULL)
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY applied_at DESC LIMIT 1
        """, (persona_id, department_id, task_category))
        row = cur.fetchone()
        conn.close()
        if row:
            return base_score * row[0], row[0]
    except sqlite3.Error:
        pass
    return base_score, 1.0


# -------- Persona scoring (reads behavioral profile from USER.md) --------
def read_owner_profile(paths: dict) -> str:
    """Read the behavioral profile section of USER.md (fallback to full USER.md)."""
    user_md = paths["user_md"]
    if not user_md.exists():
        return ""
    content = user_md.read_text(encoding="utf-8", errors="replace")
    marker = "## Behavioral Identity Profile"
    if marker in content:
        start = content.index(marker)
        # Stop at next ## not part of behavioral
        rest = content[start:]
        next_sec = rest.find("\n## ", 100)
        if next_sec > 0:
            return rest[:next_sec]
        return rest[:2000]
    fallback = "## Owner Identity Profile"
    if fallback in content:
        start = content.index(fallback)
        return content[start : start + 1500]
    return content[:600]


def list_available_personas(paths: dict) -> list:
    """Read persona-categories.json or scan personas dir."""
    pc_file = paths["persona_categories"]
    if pc_file.exists():
        try:
            data = json.loads(pc_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return list(data.keys())
            if isinstance(data, list):
                return [d.get("id") or d.get("name") for d in data if isinstance(d, dict)]
        except Exception:
            pass
    persona_root = paths["coaching_personas"] / "personas"
    if persona_root.exists():
        return [p.name for p in persona_root.iterdir() if p.is_dir()]
    return []


def compute_layer_scores(persona_id: str, task_text: str, owner_profile: str,
                          department_id: str, paths: dict) -> dict:
    """
    Compute the 5 component scores. Without a heavy LLM call this is heuristic;
    the real scoring runs through the Gemini index in v1.x.

    For v2 we keep it portable: each layer returns a value in [0,1].
    """
    # Layer 1 (Mission): look at workspace SOUL.md vs persona name
    mission_score = 0.7
    soul_md = paths["soul_md"]
    if soul_md.exists():
        mission_text = soul_md.read_text(encoding="utf-8", errors="replace").lower()
        if persona_id.lower().replace("-", " ").split()[0] in mission_text:
            mission_score = 0.85

    # Layer 2 (Owner Values): match persona keywords against behavioral profile
    values_score = 0.65
    if owner_profile:
        op_lower = owner_profile.lower()
        persona_keywords = persona_id.lower().replace("-", " ").split()
        hits = sum(1 for kw in persona_keywords if kw in op_lower)
        if hits > 0:
            values_score = min(0.65 + (hits * 0.10), 0.95)

    # Layer 3 (Company KPIs): read company-config.json
    company_kpi_score = 0.7
    cfg = paths["company_config"]
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            kpis = json.dumps(data.get("companyKPIs") or data.get("kpis") or [])
            if persona_id.lower().split("-")[0] in kpis.lower():
                company_kpi_score = 0.82
        except Exception:
            pass

    # Layer 4 (Dept KPIs): dept SOUL.md / HEARTBEAT.md
    dept_score = 0.7
    dept_path = paths["workspace"] / "departments" / f"{department_id}-dept"
    if not dept_path.exists():
        dept_path = paths["workspace"] / "departments" / department_id
    if dept_path.exists():
        dept_soul = dept_path / "SOUL.md"
        if dept_soul.exists():
            dept_score = 0.75

    # Layer 5 (Task Fit): heuristic based on task length & specificity
    task_fit = 0.7 + min(len(task_text) / 1000.0, 0.2)

    return {
        "mission":      round(mission_score, 4),
        "owner_values": round(values_score, 4),
        "company_kpis": round(company_kpi_score, 4),
        "dept_kpis":    round(dept_score, 4),
        "task_fit":     round(task_fit, 4),
    }


def score_persona(persona_id: str, task_text: str, owner_profile: str,
                  department_id: str, weights: dict, paths: dict, db_path: Path) -> dict:
    """Compute total weighted score with override applied."""
    layers = compute_layer_scores(persona_id, task_text, owner_profile, department_id, paths)
    base = (
        layers["mission"]      * weights["mission"] +
        layers["owner_values"] * weights["owner_values"] +
        layers["company_kpis"] * weights["company_kpis"] +
        layers["dept_kpis"]    * weights["dept_kpis"] +
        layers["task_fit"]     * weights["task_fit"]
    )
    task_category = infer_task_category(task_text)
    adjusted, factor = apply_weight_overrides(persona_id, base, department_id, task_category, db_path)
    return {
        "persona_id": persona_id,
        "base_score": round(base, 4),
        "score": round(adjusted, 4),
        "override_factor": factor,
        "layers": layers,
    }


def select_persona(task: str, department: str, mode: str, weights: dict,
                   paths: dict, db_path: Path) -> dict:
    """Score all available personas and return the top one."""
    personas = list_available_personas(paths)
    owner_profile = read_owner_profile(paths)

    if not personas:
        return {
            "persona_id": None,
            "score": 0.0,
            "warning": "NO_PERSONAS_AVAILABLE",
            "message": "Run Skill 22 on at least one book to activate persona-guided work.",
            "mode": mode,
        }

    scored = [score_persona(p, task, owner_profile, department, weights, paths, db_path) for p in personas]
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[0]

    result = {
        "persona_id": top["persona_id"],
        "persona_name": top["persona_id"].replace("-", " ").title(),
        "persona_version": 1,
        "score": top["score"],
        "base_score": top["base_score"],
        "override_factor": top["override_factor"],
        "interaction_mode": mode,
        "task_category": infer_task_category(task),
        "weights_used": weights,
        "layers": top["layers"],
        "breakdown": {"top_3": scored[:3]},
    }
    if top["score"] < 0.5:
        result["warning"] = "LOW_CONFIDENCE_SELECTION"
        result["message"] = f"Best persona scored {top['score']:.2f}. Consider adding more personas via Skill 22."
    return result


def main():
    parser = argparse.ArgumentParser(description="v2.1-aware persona selector (stickiness + adaptive weights + behavioral profile)")
    parser.add_argument("--task", required=True)
    parser.add_argument("--department", required=True)
    parser.add_argument("--format", default="json", choices=["json", "human"])
    parser.add_argument("--skip-stickiness", action="store_true", help="Force fresh selection even if a sticky assignment exists")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    db_path = find_dashboard_db()

    # Mode detection
    mode = detect_interaction_mode(args.task)
    task_category = infer_task_category(args.task)

    # Mechanical task check
    mechanical = ["restart", "reboot", "ping", "check disk", "check memory", "ls ", "chmod", "chown"]
    if any(m in args.task.lower() for m in mechanical):
        out = {
            "persona_id": None,
            "no_persona_required": True,
            "message": "Operational/mechanical task — no persona required.",
            "task_category": task_category,
        }
        print(json.dumps(out, indent=2) if args.format == "json" else out["message"])
        return 0

    # Stickiness check (unless skipped)
    sticky = None
    if not args.skip_stickiness:
        sticky = check_sticky_assignment(args.department, task_category, db_path)

    if sticky:
        out = {
            "persona_id": sticky["persona_id"],
            "persona_name": sticky["persona_name"],
            "persona_version": sticky["persona_version"],
            "score": sticky["last_score"],
            "interaction_mode": sticky["persona_mode"] or mode,
            "task_category": task_category,
            "breakdown": {"stickiness": True},
        }
        print(json.dumps(out, indent=2) if args.format == "json" else f"STICKY: {out['persona_name']} ({out['score']:.2f})")
        return 0

    # Fresh selection
    weights = get_weights_for_task(args.task, mode)

    if mode == "hybrid":
        leader = select_persona(args.task, args.department, "leadership", weights, paths, db_path)
        coach = select_persona(args.task, args.department, "coaching",
                                get_weights_for_task(args.task, "coaching"), paths, db_path)
        out = {
            "mode": "hybrid",
            "task_category": task_category,
            "persona_id": leader["persona_id"],
            "persona_name": leader.get("persona_name"),
            "score": leader["score"],
            "interaction_mode": "leadership",
            "secondary_persona_id": coach["persona_id"],
            "secondary_persona_name": coach.get("persona_name"),
            "secondary_persona_score": coach["score"],
            "weights_used": weights,
        }
    else:
        out = select_persona(args.task, args.department, mode, weights, paths, db_path)

    print(json.dumps(out, indent=2) if args.format == "json" else f"{out.get('persona_name','(none)')} ({out.get('score',0):.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
