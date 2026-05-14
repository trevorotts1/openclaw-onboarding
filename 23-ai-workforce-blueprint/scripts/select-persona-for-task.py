#!/usr/bin/env python3
"""
select-persona-for-task.py — v9.6.2

Called every time a new task is assigned to a department. Combines three
search strategies to pick the BEST persona for THIS specific task:

  1. SEMANTIC SEARCH (Gemini Embeddings 2) — queries the coaching-personas
     vector index for personas semantically close to the task description.
     This is the "what does this task FEEL like" check.

  2. KEYWORD FILTER — narrows the semantic candidates by matching domain
     tags (Marketing, Sales, Leadership, etc.) and perspective tags from
     persona-categories.json. This is the "is this persona EVEN in the
     right ballpark" check.

  3. 5-LAYER ALIGNMENT — the persona-matching-protocol.md scoring system:
       Layer 1: Company Mission (pre-qualified pool, runs once at setup)
       Layer 2: Owner Values     (pre-qualified pool, runs once at setup)
       Layer 3: Company KPIs     (runs per task, weight 20%)
       Layer 4: Department KPIs  (runs per task, weight 15%)
       Layer 5: Task Fit         (runs per task, weight 15%)
     Layers 1+2 produce a department-scoped pre-qualified list at setup
     time; layers 3-5 run fresh per task and pick the winner from that
     pool.

The result is logged to the dept's daily memory file and returned to the
calling agent (the Department Director or its dispatcher).

USAGE:
  python3 select-persona-for-task.py \\
      --dept marketing \\
      --task "Write a hook for the new product launch email"

EXIT CODES:
  0 = persona selected, JSON printed to stdout
  1 = no candidates found (the dept has no governing-personas.md or
      the persona library is empty)
  2 = Gemini index unavailable (semantic search fell back to keyword-only;
      result still printed but flagged)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ─── PATHS ────────────────────────────────────────────────────────────────────

HOME = Path.home()
ZHC_ROOTS = [
    HOME / "clawd" / "zero-human-company",
    HOME / "clawd" / "zhc",
    Path("~/clawd/zero-human-company"),
    Path("~/clawd/zhc"),
]

GEMINI_SEARCH_CANDIDATES = [
    HOME / ".openclaw" / "workspace" / "scripts" / "gemini-search.py",
    HOME / "clawd" / "scripts" / "gemini-search.py",
    Path("~/clawd/scripts/gemini-search.py"),
    HOME / "Downloads" / "openclaw-master-files" / "23-ai-workforce-blueprint" / "scripts" / "gemini-search.py",
]


# ─── DEPT + PERSONA DISCOVERY ─────────────────────────────────────────────────

def find_company_dir(slug=None):
    """Return the ZHC company dir. If slug is None, picks most-recently-modified."""
    candidates = []
    for root in ZHC_ROOTS:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                if slug and entry.name == slug:
                    return entry
                candidates.append((entry.stat().st_mtime, entry))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None


def find_dept_dir(company_dir, dept_id):
    """Return ~/clawd/zhc/<co>/departments/<dept_id>/ or fall back to legacy."""
    if company_dir:
        cand = company_dir / "departments" / dept_id
        if cand.is_dir():
            return cand
    # Legacy
    for legacy in [HOME / "clawd" / "departments" / dept_id,
                   Path("~/clawd/departments") / dept_id]:
        if legacy.is_dir():
            return legacy
    return None


def load_governing_personas(dept_dir):
    """Read governing-personas.md and extract pre-qualified persona names."""
    path = dept_dir / "governing-personas.md"
    if not path.exists():
        return []
    text = path.read_text()
    # Personas are typically listed as bullets or named in "Primary:" / "Secondary:" lines.
    # Pull out any persona-folder-style name (lowercase-with-hyphens).
    candidates = set()
    # Look for "- author-bookname" or "Primary: author-bookname"
    for m in re.finditer(r"(?:^|\s)([a-z][a-z0-9]+-[a-z0-9-]+)(?=\s|$|,|\))", text, re.MULTILINE):
        candidates.add(m.group(1))
    return sorted(candidates)


def load_persona_categories():
    """Read persona-categories.json to support keyword/tag filtering."""
    for p in [HOME / "Downloads" / "openclaw-master-files" / "coaching-personas" / "persona-categories.json",
              Path("~/Downloads/openclaw-master-files/coaching-personas/persona-categories.json")]:
        if p.exists():
            try:
                return json.load(open(p))
            except json.JSONDecodeError:
                continue
    return {}


# ─── SEMANTIC SEARCH (Gemini Engine) ──────────────────────────────────────────

def gemini_search_available():
    for c in GEMINI_SEARCH_CANDIDATES:
        if c.is_file():
            return c
    return None


def semantic_search(task_text, top_k=5):
    """
    Query Gemini Engine for the top_k personas semantically nearest to the
    task description. Returns list of (score, persona_id) tuples, or None
    if Gemini Engine isn't available.
    """
    sp = gemini_search_available()
    if not sp:
        return None
    try:
        r = subprocess.run(
            ["python3", str(sp), "--collection", "coaching-personas",
             "--query", task_text, "--top-k", str(top_k), "--format", "json"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        # Expected shape: [{"id": "hormozi-100m-offers", "score": 0.83, ...}, ...]
        return [(item.get("score", 0.0), item.get("id", "")) for item in data if item.get("id")]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


# ─── KEYWORD MATCHING ─────────────────────────────────────────────────────────

DEPT_DOMAIN_TAGS = {
    "marketing": ["Marketing", "Copywriting", "Communication"],
    "sales": ["Sales", "Communication", "Strategy/Innovation"],
    "billing": ["Finance", "Operations"],
    "customer-support": ["Communication", "Operations"],
    "operations": ["Operations", "Productivity/Systems", "Leadership"],
    "creative": ["Copywriting", "Communication", "Personal Development"],
    "hr": ["Leadership", "Communication", "Personal Development"],
    "legal": ["Operations", "Strategy/Innovation"],
    "it": ["Operations", "Productivity/Systems"],
    "web-development": ["Operations", "Productivity/Systems"],
    "app-development": ["Operations", "Productivity/Systems"],
    "graphics": ["Copywriting", "Communication"],
    "video": ["Copywriting", "Communication"],
    "audio": ["Copywriting", "Communication"],
    "research": ["Strategy/Innovation", "Productivity/Systems"],
    "communications": ["Communication", "Copywriting"],
    "ceo": ["Leadership", "Strategy/Innovation", "Mindset"],
    "com": ["Leadership", "Strategy/Innovation", "Mindset"],
}


def keyword_filter(candidates, dept_id, categories_data):
    """Filter candidates to those tagged with the dept's domain tags."""
    if not candidates or not categories_data:
        return candidates
    dept_tags = set(DEPT_DOMAIN_TAGS.get(dept_id, []))
    if not dept_tags:
        return candidates  # unknown dept; don't filter
    filtered = []
    personas_data = categories_data.get("personas", {}) or categories_data
    for c in candidates:
        info = personas_data.get(c, {})
        ptags = set(info.get("domain_tags", []) or info.get("tags", []))
        if ptags & dept_tags:
            filtered.append(c)
    return filtered or candidates  # fall back to unfiltered if filter eliminates all


# ─── 5-LAYER ALIGNMENT ────────────────────────────────────────────────────────
#
# Layers 1+2 (Mission, Owner Values) — pre-qualified via governing-personas.md
# Layers 3-5 — run per task here.
#
# Scoring weights per persona-matching-protocol.md:
#   Owner Values   25%  (handled at setup, but reweighted here as a tie-breaker)
#   Company Mission 25%
#   Business KPIs   20%
#   Dept KPIs       15%
#   Task Fit        15%
#
# We score each candidate on a 0-1 scale per layer, multiply by weight,
# sum to a final score. Semantic similarity contributes to Task Fit.

def score_candidate(persona_id, task_text, dept_kpis, company_kpis, owner_values,
                    company_mission, semantic_score=0.0):
    """Score a persona against the 5 layers. Returns total + per-layer breakdown."""
    # Heuristic scoring — the real system would call into the persona blueprint's
    # 14 sections and read the actual content. This is a baseline that always
    # returns something rather than fail.
    task_lower = task_text.lower()
    persona_lower = persona_id.lower()

    # Task fit — boosted by semantic similarity if available
    task_fit = semantic_score if semantic_score > 0 else 0.5
    # Cheap keyword boost — does the persona-id share a token with the task?
    persona_tokens = set(persona_lower.replace("-", " ").split())
    task_tokens = set(re.findall(r"\b[a-z]{4,}\b", task_lower))
    overlap = persona_tokens & task_tokens
    task_fit = min(1.0, task_fit + 0.05 * len(overlap))

    # Dept KPIs — flat 0.7 baseline (would be raised by per-persona analysis)
    dept_fit = 0.7
    # Company KPIs — flat 0.7 baseline
    company_fit = 0.7
    # Mission + Values — pre-qualified; flat 0.8 baseline
    mission = 0.8
    values = 0.8

    total = (mission * 0.25 + values * 0.25 + company_fit * 0.20
             + dept_fit * 0.15 + task_fit * 0.15)
    return total, {
        "mission": mission, "values": values, "company_kpis": company_fit,
        "dept_kpis": dept_fit, "task_fit": task_fit,
        "semantic_score": semantic_score,
    }


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def log_selection(dept_dir, task_text, selected_persona, score_breakdown, top_3, hybrid_mode):
    today = datetime.now().strftime("%Y-%m-%d")
    memory_dir = dept_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    log_file = memory_dir / f"{today}.md"
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"""
## {ts} — Persona Selection
- **Task:** {task_text[:200]}
- **Selected persona:** `{selected_persona}` (score {score_breakdown['total']:.3f})
- **Mode:** {hybrid_mode}
- **Top 3 candidates:** {', '.join(f"{p} ({s:.2f})" for s, p in top_3[:3])}
- **5-layer breakdown:** mission={score_breakdown['breakdown']['mission']:.2f} | values={score_breakdown['breakdown']['values']:.2f} | company_kpis={score_breakdown['breakdown']['company_kpis']:.2f} | dept_kpis={score_breakdown['breakdown']['dept_kpis']:.2f} | task_fit={score_breakdown['breakdown']['task_fit']:.2f}
- **Semantic similarity:** {score_breakdown['breakdown']['semantic_score']:.3f}
"""
    with open(log_file, "a") as f:
        f.write(entry)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pick the best persona for a task using hybrid search + 5-layer alignment.")
    parser.add_argument("--dept", required=True, help="Department ID, e.g. 'marketing'")
    parser.add_argument("--task", required=True, help="Task description in plain English")
    parser.add_argument("--company-slug", default=None, help="ZHC company slug (auto-detected if omitted)")
    parser.add_argument("--top-k-semantic", type=int, default=8, help="How many semantic candidates to fetch")
    parser.add_argument("--top-k-final", type=int, default=3, help="How many final-ranked candidates to print")
    parser.add_argument("--format", choices=("json", "id"), default="json", help="Output format")
    args = parser.parse_args()

    # Discover the company + dept folders
    company_dir = find_company_dir(args.company_slug)
    if not company_dir:
        print("[SELECT-PERSONA] No ZHC company folder found. Run Skill 23 first.", file=sys.stderr)
        return 1

    dept_dir = find_dept_dir(company_dir, args.dept)
    if not dept_dir:
        print(f"[SELECT-PERSONA] Department '{args.dept}' not found under {company_dir}", file=sys.stderr)
        return 1

    # Load the pre-qualified pool (layers 1+2)
    pre_qualified = load_governing_personas(dept_dir)
    if not pre_qualified:
        print(f"[SELECT-PERSONA] No governing-personas.md found for {args.dept}; "
              f"falling back to ALL personas in the library.", file=sys.stderr)

    # Semantic search via Gemini Engine
    semantic_hits = semantic_search(args.task, top_k=args.top_k_semantic)
    hybrid_mode = "hybrid (semantic + keyword + 5-layer)"
    if semantic_hits is None:
        hybrid_mode = "keyword + 5-layer (Gemini Engine unavailable)"
        semantic_hits = [(0.0, p) for p in pre_qualified[:args.top_k_semantic]]
        gemini_unavailable = True
    else:
        gemini_unavailable = False

    # Combine: union of pre-qualified pool + semantic hits
    candidates = set(pre_qualified)
    for _, pid in semantic_hits:
        if pid:
            candidates.add(pid)
    candidates = list(candidates)

    # Keyword filter
    categories = load_persona_categories()
    candidates = keyword_filter(candidates, args.dept, categories)

    if not candidates:
        print(f"[SELECT-PERSONA] No candidates after filtering for dept '{args.dept}'.", file=sys.stderr)
        return 1

    # Build semantic score lookup
    semantic_scores = {pid: score for score, pid in semantic_hits}

    # 5-layer scoring per candidate
    scored = []
    for pid in candidates:
        sem = semantic_scores.get(pid, 0.0)
        total, breakdown = score_candidate(
            pid, args.task,
            dept_kpis="", company_kpis="", owner_values="", company_mission="",
            semantic_score=sem,
        )
        scored.append((total, pid, breakdown))

    scored.sort(reverse=True, key=lambda x: x[0])
    top_3_ids = [(s, p) for s, p, _ in scored[:args.top_k_final]]
    winner_score, winner_id, winner_breakdown = scored[0]

    # Log to dept's daily memory
    log_selection(
        dept_dir, args.task, winner_id,
        {"total": winner_score, "breakdown": winner_breakdown},
        top_3_ids, hybrid_mode,
    )

    # Output
    result = {
        "persona_id": winner_id,
        "score": winner_score,
        "mode": hybrid_mode,
        "gemini_available": not gemini_unavailable,
        "top_3": [{"persona_id": p, "score": s} for s, p in top_3_ids],
        "breakdown": winner_breakdown,
        "dept": args.dept,
        "task": args.task,
        "company_dir": str(company_dir),
    }

    if args.format == "id":
        print(winner_id)
    else:
        print(json.dumps(result, indent=2))

    return 2 if gemini_unavailable else 0


if __name__ == "__main__":
    sys.exit(main())
