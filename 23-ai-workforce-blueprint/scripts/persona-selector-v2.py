#!/usr/bin/env python3
"""
Persona Selector v2 — v2.1-aware persona selection.

This is THE canonical persona selector (PRD item 1.1, v11.3.x+).
select-persona-for-task.py (v1) is a deprecated shim that delegates here.

Features:
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
7. Anti-repetition variety (v10.14.28) — overused personas in the last
   VARIETY_WINDOW_HOURS get a per-use penalty applied to their score, and
   when the top three candidates are within VARIETY_DOMINANCE_RATIO of each
   other we sample from them weighted by adjusted score instead of always
   picking #1. This stops the "Godin every time" failure mode Trevor flagged
   on 2026-05-24. Quality is preserved (top-1 still wins when it dominates
   by ≥1.5x). Disable with `--no-variety` for deterministic debugging.
8. PRE-SCORING FUNNEL (PRD item 1.2 — rebuilt funnel; item 1.1 was the port):
   Stage A — governing-personas.md pool (dept pre-qualified list, or all personas).
   Stage B — category-tag filter: persona-categories.json `domain` key (correct key,
             Defect 1 fix) + infer_task_category derived tags (Defect 3) + _norm_tag
             normalisation so DEPT_DOMAIN_TAGS and persona domains both use lowercase-
             hyphenated form before comparison (Defect 2). Never filters to zero.
   Stage C — gemini-search semantic candidate retrieval (top-10, intersected with B).
             CLI contract fixed to match gemini-search.py: positional query + --limit,
             stdout text parsed for PERSONA: lines (Defect 4). Never filters to zero.
   Stage D — existing 5-layer scoring on survivors only.
   Output JSON includes "funnel": {"pool": N, "category": N, "semantic": N} (canonical
   PRD 1.2 keys) so the dashboard and QC can see the funnel working.

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
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))

from detect_platform import get_openclaw_paths  # type: ignore
from resolve_db import find_dashboard_db, is_db_found  # type: ignore  # PRD 1.3: single shared resolver
from adaptive_weights import get_weights_for_task, DEFAULT_WEIGHTS  # type: ignore
from canonical_slug import canonical_dept_slug  # type: ignore  # PRD 1.5: dept identity contract

try:
    # The category inferer ships as infer-task-category.py (HYPHENATED) — a name Python
    # cannot import as a module via `import infer_task_category` (underscores). The old
    # `from infer_task_category import ...` therefore ALWAYS raised ImportError and the
    # stub below ran, so EVERY task inferred "general" and the category-derived domain
    # tags (incl. the video-edit/montage production split) were never applied. Load the
    # hyphenated file by path so the real inferer is used. Fall back to the safe
    # "general" stub only if the file is genuinely absent (never-to-zero behavior).
    import importlib.util as _ilu
    _itc_path = Path(__file__).parent / "infer-task-category.py"
    if _itc_path.is_file():
        _itc_spec = _ilu.spec_from_file_location("infer_task_category_mod", str(_itc_path))
        _itc_mod = _ilu.module_from_spec(_itc_spec)
        _itc_spec.loader.exec_module(_itc_mod)  # type: ignore
        infer_task_category = _itc_mod.infer_task_category  # type: ignore
    else:
        raise ImportError("infer-task-category.py not found")
except Exception:
    def infer_task_category(task_text: str) -> str:
        return "general"

try:
    from llm_score import score_layer, summarize_persona_blueprint  # type: ignore
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    def score_layer(*args, **kwargs):  # type: ignore
        return {"score": 0.6, "reasoning": "llm_score module not available",
                "model": "stub", "cached": False, "fallback": True}
    def summarize_persona_blueprint(persona_id: str, max_chars: int = 2000) -> str:  # type: ignore
        return f"(no blueprint summary — llm_score module not available)"

try:
    from semantic_task_fit import semantic_task_fit  # type: ignore
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    def semantic_task_fit(persona_id, task_text, paths, persona_summary=""):  # type: ignore
        return {"score": 0.6, "method": "module_missing", "detail": "semantic_task_fit not importable"}

try:
    # G13: in-process Stage-C retrieval that shares ONE task embedding with
    # Layer-5 semantic_task_fit (same module cache). Replaces the gemini-search
    # subprocess as the primary path (subprocess kept as fallback).
    from semantic_task_fit import semantic_persona_ids  # type: ignore
    SEMANTIC_PERSONA_IDS_AVAILABLE = True
except ImportError:
    SEMANTIC_PERSONA_IDS_AVAILABLE = False
    def semantic_persona_ids(task_text, paths, top_k=10):  # type: ignore
        return None


# When env var SCORING_MODE=llm, use LLM evaluation for Layers 1-4.
# When SCORING_MODE=heuristic (default), use the keyword-hit baseline.
# Wave 3 default flips to "llm" once owner has tested in production.
SCORING_MODE = os.environ.get("SCORING_MODE", "llm" if LLM_AVAILABLE else "heuristic").lower()


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
# find_dashboard_db() is imported from shared-utils/resolve_db.py (PRD 1.3).
# The local copy was removed to eliminate divergent candidate lists.

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


def find_selection_log() -> Path:
    """Locate persona-selection-log.md. Returns Path (may not exist)."""
    if "PERSONA_SELECTION_LOG_PATH" in os.environ:
        return Path(os.environ["PERSONA_SELECTION_LOG_PATH"])
    candidates = [
        Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "persona-selection-log.md",
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/persona-selection-log.md"),
        Path.home() / "clawd" / "skills" / "23-ai-workforce-blueprint" / "persona-selection-log.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def write_selection_log_md(log_path: Path, entry: dict):
    """Append a single row to persona-selection-log.md. Best-effort, never raises."""
    try:
        if not log_path.parent.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            log_path.write_text(
                "# Persona Selection Log\n\n"
                "Every task dispatch produces a log entry here. "
                "Append-only.\n\n"
                "| date | task-id | dept | task-cat | selected | score | mode | reasoning |\n"
                "|------|---------|------|----------|----------|-------|------|-----------|\n",
                encoding="utf-8",
            )
        reasoning = (entry.get("reasoning") or "").replace("|", "/").replace("\n", " ")[:240]
        row = (
            f"| {entry.get('date', '?')} "
            f"| {entry.get('task_id', '?')} "
            f"| {entry.get('department', '?')} "
            f"| {entry.get('task_category', '?')} "
            f"| {entry.get('persona_id', '?')} "
            f"| {entry.get('score', 0):.2f} "
            f"| {entry.get('mode', '?')} "
            f"| {reasoning} |\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(row)
    except OSError as e:
        print(f"[persona-selector] WARN: could not write selection log: {e}", file=sys.stderr)


def _ensure_persona_assignment_columns(conn):
    """Ensure consecutive_count + needs_review columns exist (anti-staleness)."""
    cols = {c[1] for c in conn.execute("PRAGMA table_info(persona_assignment)").fetchall()}
    if "consecutive_count" not in cols:
        try:
            conn.execute("ALTER TABLE persona_assignment ADD COLUMN consecutive_count INTEGER DEFAULT 0")
        except sqlite3.Error:
            pass
    if "needs_review" not in cols:
        try:
            conn.execute("ALTER TABLE persona_assignment ADD COLUMN needs_review INTEGER DEFAULT 0")
        except sqlite3.Error:
            pass


ANTI_STALENESS_THRESHOLD = 5  # 5+ consecutive same persona → flag for review

# ─── Anti-repetition variety constants (v10.14.28) ────────────────────────
# Trevor's complaint, 2026-05-24: "the system did not properly assign persona
# to the task and some time i just keep using the same on over and over again
# without any consideration." Fix: recency penalty + top-N weighted sample.
VARIETY_WINDOW_HOURS = 24      # look-back window for recent-use counts
VARIETY_PENALTY_PER_USE = 0.08 # 8% score reduction per recent use
VARIETY_PENALTY_CAP_USES = 5   # penalty saturates at 5 uses (= 40% cap)
VARIETY_DOMINANCE_RATIO = 1.5  # top-1 must be ≥1.5x top-3 to skip sampling
VARIETY_SAMPLE_TOP_N = 3       # weighted-sample pool size when sampling
VARIETY_SAMPLE_SEED_ENV = "PERSONA_VARIETY_SEED"  # set for deterministic tests

# ─── G13: Stage-D fan-out backstop (token-furnace guard) ───────────────────
# On a FRESH box (no governing-personas.md, no domain-tag coverage) the funnel
# can hand the FULL persona library to Stage D. With SCORING_MODE='llm' that is
# 4 LLM calls per persona → ~160 calls on ONE task (the F7 furnace). Two guards
# enforced at the scoring gate in select_persona():
#   1. LLM GATE — LLM layer-scoring only runs when the candidate set can be
#      BOUNDED: a governing pool exists OR an in-process semantic ranking is
#      available to cap finalists. Otherwise this selection silently uses the
#      cheap heuristic path (zero API fan-out). Root-cause kill; no cron, no
#      self-resurrect — the burn simply cannot start on an unbounded fresh box.
#   2. FINALIST CAP — even when bounded, never LLM-score more than
#      STAGE_D_LLM_FINALIST_CAP personas; keep the top-cap by semantic rank.
# Heuristic mode is unaffected (it is already cheap: keyword layers + one shared
# task embed reused across personas), so the full survivor list still scores
# there and selection quality on bounded boxes is preserved.
STAGE_D_LLM_FINALIST_CAP = max(1, int(os.environ.get("STAGE_D_LLM_FINALIST_CAP", "12")))

# ─── PRE-SCORING FUNNEL (PRD item 1.2 — rebuilt funnel) ─────────────────────
# Stage A: governing-personas.md → candidate pool (or all personas fallback)
# Stage B: category-tag filter using persona-categories.json `domain` key +
#          infer-task-category.py derived tags (PRD 1.2 Defects 1-3 fixed)
# Stage C: gemini-search semantic candidate retrieval (top-10 intersected)
#          called via CLI contract that matches gemini-search.py as it exists:
#          positional `query` + `--limit` flag, stdout text parsed for PERSONA:
# Stage D: existing 5-layer scoring on survivors
# Never filters to zero: each stage falls back to prior stage's output.
# Output JSON: "funnel": {"pool": N, "category": N, "semantic": N}
# plus additive diagnostics: pool_source, semantic_engine.

# Department → domain tags. Values use the SAME canonical form as
# persona-categories.json `domain` values: lowercase, hyphenated.
# Both sides are routed through _norm_tag() before comparison (Defect 2 guard).
DEPT_DOMAIN_TAGS = {
    "marketing": ["marketing", "copywriting", "communication", "sales", "strategy-innovation"],
    "paid-advertisement": ["marketing", "copywriting", "strategy-innovation"],
    "sales": ["sales", "communication", "strategy-innovation", "marketing"],
    "billing": ["finance", "operations"],
    "customer-support": ["communication", "operations", "coaching"],
    "operations": ["operations", "productivity-systems", "leadership", "strategy-innovation"],
    "creative": ["copywriting", "communication", "personal-development", "marketing"],
    "hr": ["leadership", "communication", "personal-development", "coaching"],
    "legal": ["operations", "strategy-innovation", "leadership"],
    "it": ["operations", "productivity-systems"],
    "web-development": ["marketing", "sales", "copywriting", "strategy-innovation", "operations"],
    "app-development": ["operations", "productivity-systems"],
    "graphics": ["copywriting", "communication", "marketing"],
    "video": ["video", "editing", "montage", "visual-storytelling", "copywriting", "communication", "marketing"],
    "audio": ["copywriting", "communication", "marketing"],
    "research": ["strategy-innovation", "productivity-systems", "operations"],
    "communications": ["communication", "copywriting", "marketing"],
    "ceo": ["leadership", "strategy-innovation", "mindset", "operations"],
    "com": ["leadership", "strategy-innovation", "mindset"],
    "personal-assistant": ["communication", "productivity-systems", "operations"],
    "general-task": ["leadership", "strategy-innovation", "productivity-systems"],
    "project-architecture-office": ["strategy-innovation", "leadership", "operations"],
}

# Maps infer-task-category.py category slugs → set of persona domain tags.
# Only maps to domains that ACTUALLY EXIST in persona-categories.json:
#   coaching, communication, copywriting, finance, leadership, marketing,
#   mindset, operations, personal-development, productivity-systems,
#   sales, strategy-innovation
# "general" intentionally maps to empty set — contributes nothing so Stage B
# keys solely off department tags (the stub infer_task_category path is safe).
_CATEGORY_DOMAINS: dict = {
    "email-outreach":   {"marketing", "copywriting", "communication"},
    "social-post":      {"marketing", "copywriting", "communication"},
    "content-write":    {"copywriting", "communication"},
    "video-script":     {"copywriting", "marketing", "communication"},
    # video-edit / montage routes to the PRODUCTION-craft domains so an editing/montage
    # task surfaces the editing persona (e.g. Pudovkin), NOT a copy persona. This is the
    # deterministic split between "write the video script" (video-script → copy family)
    # and "edit the montage / pace the cut" (video-edit → production family).
    "video-edit":       {"editing", "montage", "visual-storytelling", "video"},
    "research":         {"strategy-innovation", "productivity-systems"},
    "strategy":         {"strategy-innovation", "leadership", "operations"},
    "design":           {"copywriting", "strategy-innovation"},  # no "design" domain exists
    "ops":              {"operations", "productivity-systems"},
    "finance":          {"finance", "operations"},
    "legal":            {"leadership", "strategy-innovation"},
    "hr":               {"leadership", "communication", "personal-development"},
    "customer-service": {"communication", "coaching"},
    "coaching-prompt":  {"coaching", "mindset", "personal-development"},
    "review-feedback":  {"communication", "coaching"},
    "general":          set(),  # empty: contributes nothing; dept tags carry Stage B alone
}


def _norm_tag(s: str) -> str:
    """Normalize a domain tag to lowercase-hyphenated form.

    Fixes Defect 2: DEPT_DOMAIN_TAGS had Title-Case/slash form (e.g.
    "Strategy/Innovation", "Productivity/Systems") while persona-categories.json
    stores "strategy-innovation", "productivity-systems".  Routing BOTH sides
    through this function ensures set-intersection works.  Centralised here so
    a future vocabulary change only requires editing one place.
    """
    import re as _re
    s = s.lower()
    s = _re.sub(r"[/ _]+", "-", s)
    return s.strip("-")


# ── Perspective bonus: additive-only, never-to-zero ────────────────────────────
# perspective[] tags in persona-categories.json (the 6-tag perspectiveTags vocab)
# describe the lived-experience LENS a persona's SOURCE genuinely carries
# (e.g. african-american-experience, faith-spirituality). They are DESCRIPTIVE
# metadata, never a filter: an empty or absent perspective[] must NEVER eliminate
# or zero-score a persona. _category_filter() (Stage B) keys ONLY off domain[] and
# is deliberately left untouched here. Perspective participates in selection ONLY
# as a small ADDITIVE bonus, and ONLY when the task text explicitly invokes that
# same lens — so perspective routing degrades gracefully (a generic task ignores it
# entirely; the ~41 personas with perspective=[] are never affected) instead of
# being dead weight or a trap. The bonus is bounded so it acts as a gentle
# tiebreaker, never a dominant scoring term.
PERSPECTIVE_BONUS_MAX = 0.05      # hard cap on the total perspective bonus
PERSPECTIVE_BONUS_PER_TAG = 0.025 # per overlapping lens, summed then capped

# Maps each perspectiveTags vocab entry → task-text trigger phrases. Only the lens
# a task EXPLICITLY invokes earns a bonus; no match → 0.0 for everyone.
PERSPECTIVE_KEYWORDS: dict = {
    "african-american-experience": [
        "african american", "african-american", "black community", "black men",
        "black women", "black founder", "black entrepreneur", "racism", "racial",
        "civil rights", "the culture",
    ],
    "womens-challenges": [
        "women", "woman", "female founder", "female entrepreneur", "motherhood",
        "as a mother", "for moms", "girl boss",
    ],
    "mens-challenges": [
        "men's", "for men", "fatherhood", "as a father", "masculinity", "brotherhood",
    ],
    "family-relationships": [
        "family", "parenting", "co-parent", "marriage", "spouse", "raising kids",
        "raising children", "sibling", "in-law",
    ],
    "faith-spirituality": [
        "faith", "spiritual", "god ", "prayer", "church", "ministry", "scripture",
        "biblical", "gospel", "christian",
    ],
    "love-romantic-relationships": [
        "romantic", "dating", "love life", "my partner", "relationship advice",
        "marriage",
    ],
}


def infer_task_perspectives(task_text: str) -> set:
    """Return the set of perspective tags the TASK text explicitly invokes.

    Empty set for the common (generic-task) case — which yields a 0.0 bonus for
    every persona, so perspective is purely opt-in and never harmful.
    """
    text = (task_text or "").lower()
    hits: set = set()
    for tag, kws in PERSPECTIVE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            hits.add(tag)
    return hits


def perspective_bonus(persona_perspectives, task_perspectives) -> float:
    """Additive-only, never-to-zero perspective score adjustment.

    Returns 0.0 when the persona has no perspective[] tags, OR the task invokes
    none, OR the two sets do not overlap. Returns a small POSITIVE bonus (capped at
    PERSPECTIVE_BONUS_MAX) ONLY on genuine overlap. The return value is guaranteed
    >= 0.0, so applying it can never reduce, eliminate, or zero-score a persona.
    """
    if not persona_perspectives or not task_perspectives:
        return 0.0
    overlap = set(persona_perspectives) & set(task_perspectives)
    if not overlap:
        return 0.0
    return min(len(overlap) * PERSPECTIVE_BONUS_PER_TAG, PERSPECTIVE_BONUS_MAX)


# Gemini-search script candidate locations (checked in order)
_GEMINI_SEARCH_CANDIDATES = [
    Path(__file__).parent / "gemini-search.py",
    Path("/data/.openclaw/workspace/scripts/gemini-search.py"),
    Path.home() / ".openclaw" / "workspace" / "scripts" / "gemini-search.py",
    Path.home() / "Downloads" / "openclaw-master-files" / "23-ai-workforce-blueprint" / "scripts" / "gemini-search.py",
]


def _find_gemini_search() -> "Path | None":
    """Locate the gemini-search.py script. Returns None if not found."""
    for c in _GEMINI_SEARCH_CANDIDATES:
        if c.exists():
            return c
    return None


def _load_governing_personas(paths: dict, department: str) -> "list | None":
    """
    Stage A: load governing-personas.md for the department and return the
    pre-qualified persona ID list. Returns None when the file is absent
    (caller falls back to full library — never-to-zero).

    Parser notes:
    - create_role_workspaces.py writes backtick-wrapped IDs in a markdown table
      (e.g. `bly-copywriters-handbook`) — caught by the ID regex below.
    - generate-governing-personas.sh writes author NAMES, not IDs, in the
      "## Available Persona Pool" section; these do NOT match the ID regex, so
      the shell-generated stub legitimately yields None → "all personas" fallback.
      Do NOT expand the regex to match author names — that would produce garbage.
    """
    import re as _re
    company_root = paths.get("company_root")
    if not company_root:
        return None
    # Try canonical path and legacy alternatives
    dept_candidates = [
        company_root / "departments" / department / "governing-personas.md",
        company_root / department / "governing-personas.md",
    ]
    for dept_path in dept_candidates:
        if dept_path.exists():
            text = dept_path.read_text(encoding="utf-8", errors="replace")
            personas: set = set()
            for m in _re.finditer(r"(?:^|\s)([a-z][a-z0-9]+-[a-z0-9-]+)(?=\s|$|,|\))", text, _re.MULTILINE):
                personas.add(m.group(1))
            if personas:
                return sorted(personas)
    return None


def _category_filter(candidates: list, department: str, task_text: str,
                     categories_data: dict) -> list:
    """
    Stage B (PRD item 1.2): narrow candidates to those whose domain tags
    intersect the combined department + task-derived domain tag set.

    Fixes three defects from the prior _dept_keyword_filter() implementation:
      Defect 1 — reads correct key: `domain` (not `domain_tags`/`tags`)
      Defect 2 — normalises both sides via _norm_tag() before intersection
                 (DEPT_DOMAIN_TAGS had Title-Case/slash; personas have lowercase-hyphen)
      Defect 3 — adds task-derived domains from infer_task_category() to the
                 filter set so a finance task in a marketing dept still surfaces
                 finance-aligned personas

    Never-to-zero: returns `candidates` unchanged when:
      - categories_data is empty (fresh install, Skill 22 hasn't run)
      - filter_tags is empty (no dept entry + general task category)
      - intersection is empty (no persona matches the combined tags)
    """
    if not categories_data:
        return candidates  # never-to-zero: Skill 22 not yet run

    # Build normalised department tag set
    raw_dept_tags = DEPT_DOMAIN_TAGS.get(department, [])
    dept_tags = {_norm_tag(t) for t in raw_dept_tags}

    # Add task-category-derived domain tags (Defect 3)
    task_cat = infer_task_category(task_text)  # "general" when stub active
    raw_task_tags = _CATEGORY_DOMAINS.get(task_cat, set())
    task_tags = {_norm_tag(t) for t in raw_task_tags}
    filter_tags = dept_tags | task_tags

    if not filter_tags:
        return candidates  # never-to-zero: no tags to filter by

    personas_data = categories_data.get("personas", {}) or categories_data

    def _match(tagset):
        """Return candidates whose persona domain intersects `tagset`."""
        out = []
        for c in candidates:
            info = personas_data.get(c, {})
            # Primary key: `domain` (Defect 1 fix). Fallback keys kept so a future
            # schema change producing domain_tags/tags still works; primary wins.
            # IMPORTANT: do NOT change persona-categories.json to add domain_tags —
            # fixing Defect 1 is selector-side only (see PRD 1.2 risk note §7.9).
            raw_ptags = (info.get("domain") or info.get("domain_tags") or info.get("tags") or [])
            ptags = {_norm_tag(t) for t in raw_ptags}
            if ptags & tagset:
                out.append(c)
        return out

    # PER-STAGE SPLIT (PRD Deliverable-7): when the inferred task category maps to a
    # SPECIFIC, non-empty domain family (e.g. video-edit -> {editing,montage,
    # visual-storytelling,video}; video-script -> {copywriting,marketing,communication}),
    # PREFER narrowing to that family so a multi-family department (video spans BOTH the
    # production-craft and the copy families in DEPT_DOMAIN_TAGS) routes deterministically:
    # an "edit the montage / pace the cut" task surfaces the editing persona, while a
    # "write the video script/hook" task surfaces a copy persona. Only when the
    # task-family intersection is empty do we fall back to the broad dept-tag union
    # (never-to-zero). When the task category is "general" (task_tags empty) the broad
    # union path below is taken exactly as before — no behavior change for non-craft tasks.
    if task_tags:
        task_family_match = _match(task_tags)
        if task_family_match:
            return task_family_match

    filtered = _match(filter_tags)
    return filtered if filtered else candidates  # never-to-zero guard


def _semantic_candidate_retrieval(task_text: str, paths: dict, top_k: int = 10) -> "list | None":
    """
    Stage C: return an ordered list of persona IDs most similar to the task,
    or None if the search engine is unavailable/errors.

    G13 / PRD item 1.8 — PRIMARY path is now the in-process programmatic API
    semantic_task_fit.semantic_persona_ids(). It embeds the task ONCE and caches
    that embedding in the shared module-level cache, so Layer-5 task-fit reuses
    the SAME vector instead of paying for a second embed. The prior design
    embedded the task twice per selection: once inside the gemini-search.py
    subprocess here, and again in-process for Layer 5. Routing Stage C through
    the shared API collapses that to a single embed (the core G13 efficiency win)
    AND removes a subprocess spawn from the hot path.

    FALLBACK path (unchanged contract) — gemini-search.py subprocess, used only
    when the programmatic API is unavailable or returns no candidates (e.g. the
    semantic_task_fit module is not importable, or numpy/genai is missing but the
    standalone script still works). CLI contract matched to gemini-search.py as
    it exists (PRD item 1.2 Defect 4 fix):
      argv: [python3, gemini-search.py, "--", task_text, "--limit", N]
      stdout: human text; both semantic and keyword-fallback paths print
              "PERSONA: <id>" on each result line — one regex catches both:
                [N] SCORE: 0.83 | PERSONA: hormozi-100m-offers
                [N] KEYWORD-HITS: 4 | PERSONA: bly-copywriters-handbook
      The "--" before task_text guards against task descriptions that begin
      with "-" being parsed by argparse as flags.

    ID-convention note: the index stores persona FOLDER names as IDs (e.g.
    "hormozi-100m-offers").  These are the same IDs used as keys in
    persona-categories.json, so Stage C's intersection with pool_b self-heals
    naming mismatches via never-to-zero (empty intersection → keep pool_b).
    """
    # PRIMARY (G13): in-process, single shared task embedding.
    if SEMANTIC_PERSONA_IDS_AVAILABLE:
        try:
            ids = semantic_persona_ids(task_text, paths, top_k=top_k)
            if ids:
                return ids
        except Exception:
            pass  # fall through to subprocess fallback (never-to-zero)

    # FALLBACK: gemini-search.py subprocess (legacy contract).
    import re as _re
    import subprocess as _subprocess
    sp = _find_gemini_search()
    if not sp:
        return None
    try:
        r = _subprocess.run(
            [sys.executable, str(sp), "--", task_text, "--limit", str(top_k)],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None
        # Parse "PERSONA: <id>" from both embedding and keyword-fallback output.
        ids: list = []
        seen: set = set()
        for m in _re.finditer(r"PERSONA:\s*(\S+)", r.stdout):
            pid = m.group(1).strip()
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
        return ids if ids else None
    except Exception:
        return None


def build_candidate_pool(task_text: str, department: str, all_personas: list,
                          paths: dict) -> tuple:
    """
    Run the three-stage pre-scoring funnel and return
    (candidate_list, funnel_dict, semantic_order).

    semantic_order (G13): the funnel survivors ordered by semantic rank (best
    task-match first), or [] when no semantic signal was available. select_persona
    uses it to cap Stage-D LLM finalists to the most task-relevant personas.

    Safety invariant: each stage count is >= 1 whenever all_personas is non-empty,
    and counts are monotonically non-increasing (pool >= category >= semantic)
    because every stage is a filter-or-fallback, never a strict reduction.
    The no-personas case is handled upstream at select_persona() line ~1055.

    Stage A: governing-personas.md pool, or all_personas if absent.
    Stage B: category-tag filter (persona-categories.json `domain` key +
             infer_task_category derived tags). Never-to-zero.
    Stage C: gemini-search semantic retrieval — intersect with Stage B result.
             If intersection is empty, keep Stage B result (never-to-zero).

    funnel_dict canonical keys (PRD 1.2 contract):
      pool     — Stage A count  (governing pool or full library)
      category — Stage B count  (after category-tag filter)
      semantic — Stage C count  (after semantic intersection)
    Plus additive diagnostics (dashboard use, not canonical):
      pool_source    — "governing-personas.md" | "all (no governing-personas.md)"
      semantic_engine — "gemini-search" | "unavailable (fallback to Stage B)"
    """
    # Load persona-categories.json for Stage B
    pc_file = paths.get("persona_categories")
    categories_data: dict = {}
    if pc_file and Path(pc_file).exists():
        try:
            categories_data = json.loads(Path(pc_file).read_text(encoding="utf-8"))
        except Exception:
            categories_data = {}

    # Stage A — governing pool or full library (never-to-zero)
    governing = _load_governing_personas(paths, department)
    if governing:
        pool_a = [p for p in governing if p in all_personas]
        if not pool_a:
            pool_a = all_personas  # governing list references personas not yet installed
        pool_note = "governing-personas.md"
    else:
        pool_a = list(all_personas)
        pool_note = "all (no governing-personas.md)"  # PRD literal — dashboard greps for this

    # Stage B — category-tag filter (Defects 1-3 fixed; task_text feeds infer_task_category)
    pool_b = _category_filter(pool_a, department, task_text, categories_data)

    # Stage C — semantic retrieval (G13: in-process shared-embed primary;
    # gemini-search subprocess fallback — Defect 4 CLI contract preserved there)
    semantic_ids = _semantic_candidate_retrieval(task_text, paths, top_k=10)
    if semantic_ids:
        semantic_set = set(semantic_ids)
        intersection = [p for p in pool_b if p in semantic_set]
        pool_c = intersection if intersection else pool_b  # never-to-zero
        semantic_note = "gemini-search"
    else:
        pool_c = pool_b
        semantic_note = "unavailable (fallback to Stage B)"

    # G13: survivors ranked by semantic relevance (best first). Used by
    # select_persona to keep the top-N finalists when capping LLM fan-out.
    # Empty when there was no semantic signal (caller degrades gracefully).
    pool_c_set = set(pool_c)
    semantic_order = [p for p in (semantic_ids or []) if p in pool_c_set]

    # Emit canonical 3 keys (PRD 1.2 §3 output contract) + 2 additive diagnostics
    funnel = {
        "pool": len(pool_a),
        "category": len(pool_b),
        "semantic": len(pool_c),
        "pool_source": pool_note,
        "semantic_engine": semantic_note,
    }
    return pool_c, funnel, semantic_order


def read_recent_use_counts(department_id: str, task_category: str,
                            window_hours: int, db_path: Path) -> dict:
    """Return {persona_id: count} of selections in last window_hours for this
    (department, task_category). READS persona_selection_log (which Track A
    is also using for its history table — additive, no conflict). If the DB
    is missing or unreadable, returns {} so the variety penalty becomes a
    no-op and the selector still works."""
    if not db_path or not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        # Match `"task_category":"<cat>"` OR `"task_category": "<cat>"` —
        # we use whitespace-tolerant separate %-clauses chained together so
        # both compact (selector-written, v10.14.28+) and pretty-printed
        # (legacy rows from any external writer) JSON match.
        cur.execute(
            """
            SELECT persona_id, COUNT(*) AS uses
            FROM persona_selection_log
            WHERE department_id = ?
              AND COALESCE(layer_scores, '') LIKE ?
              AND COALESCE(layer_scores, '') LIKE ?
              AND selected_at >= datetime('now', ?)
            GROUP BY persona_id
            """,
            (
                department_id,
                '%task_category%',
                f'%{task_category}%',
                f"-{int(window_hours)} hours",
            ),
        )
        rows = cur.fetchall()
        conn.close()
        return {pid: int(uses) for pid, uses in rows if pid}
    except sqlite3.Error as e:
        print(f"[persona-selector] WARN: recent_use_counts read failed: {e}",
              file=sys.stderr)
        return {}


def variety_penalty_factor(recent_use_count: int) -> float:
    """Return the score multiplier for a persona used N times recently.
    0 uses → 1.0 (no penalty). 5+ uses → 0.6 (40% penalty, capped)."""
    capped = min(max(int(recent_use_count), 0), VARIETY_PENALTY_CAP_USES)
    return 1.0 - VARIETY_PENALTY_PER_USE * capped


def pick_with_variety(scored: list) -> tuple:
    """Pick a persona from `scored` (already sorted desc by adjusted score).
    Returns (picked_dict, picked_index, was_sampled_bool). If the top score
    dominates the #3 (or the last in the pool) by ≥VARIETY_DOMINANCE_RATIO,
    just picks #1 deterministically. Otherwise samples from the top-N
    weighted by adjusted score so variety shows up over many calls without
    introducing noise into clear winners."""
    if not scored:
        return None, -1, False
    pool = scored[:VARIETY_SAMPLE_TOP_N]
    if len(pool) == 1:
        return pool[0], 0, False
    top = pool[0]["score"]
    floor = pool[-1]["score"]
    # If the bottom of the pool is zero/negative, dominance ratio is undefined;
    # fall back to deterministic top-1 to avoid divide-by-zero weirdness.
    if floor <= 0:
        return pool[0], 0, False
    if top >= VARIETY_DOMINANCE_RATIO * floor:
        return pool[0], 0, False
    weights = [max(s["score"], 1e-6) for s in pool]
    seed = os.environ.get(VARIETY_SAMPLE_SEED_ENV)
    rng = random.Random(seed) if seed else random
    picked = rng.choices(pool, weights=weights, k=1)[0]
    idx = scored.index(picked)
    return picked, idx, True


def write_persona_selection_log_row(db_path: Path, entry: dict):
    """Insert a row into persona_selection_log so the next call's variety
    lookup can see this pick. Idempotent-ish: if task_id is repeated we just
    append (the table has no UNIQUE on task_id, only an index). Stuffs
    task_category into layer_scores JSON so read_recent_use_counts can scope
    by category without a schema change."""
    if not db_path or not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        # Compact JSON (no spaces) so read_recent_use_counts can LIKE-match
        # `"task_category":"<cat>"` without worrying about default-pretty-print
        # whitespace drift. Same row format the variety query expects.
        layer_json = json.dumps({
            "task_category":   entry.get("task_category", "general"),
            "layers":          entry.get("layers", {}),
            "variety_applied": entry.get("variety_applied", False),
        }, default=str, separators=(",", ":"))
        cur.execute(
            """
            INSERT INTO persona_selection_log
                (task_id, persona_id, persona_name, mode, score,
                 layer_scores, department_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("task_id") or f"selector-{os.urandom(4).hex()}",
                entry["persona_id"],
                entry.get("persona_name") or entry["persona_id"],
                entry.get("mode") or "leadership",
                float(entry.get("score", 0.0)),
                layer_json,
                entry.get("department", ""),
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"[persona-selector] WARN: persona_selection_log insert failed: {e}",
              file=sys.stderr)


def write_persona_assignment_db(db_path: Path, entry: dict):
    """Upsert into persona_assignment table. Best-effort, never raises.

    Anti-staleness guard (v10.8.0): when the same persona is selected for
    the same (department, task_category) ≥5 times in a row WITHOUT switching,
    `needs_review` is flipped to 1. The orchestrator / dashboard surfaces
    rows with needs_review=1 so a human (or a meta-agent) can decide whether
    the stickiness is genuine or a sign the selector has gone deaf.
    """
    if not db_path or not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        _ensure_persona_assignment_columns(conn)
        cur = conn.cursor()

        cur.execute(
            "SELECT persona_id, switch_count, consecutive_count "
            "FROM persona_assignment "
            "WHERE department_id = ? AND task_category = ?",
            (entry["department"], entry["task_category"]),
        )
        existing = cur.fetchone()
        switch_count = 0
        consecutive_count = 1
        if existing:
            existing_persona_id, existing_switch_count, existing_consecutive = existing
            switch_count = existing_switch_count or 0
            if existing_persona_id == entry["persona_id"]:
                consecutive_count = (existing_consecutive or 0) + 1
            else:
                switch_count += 1
                consecutive_count = 1

        # Anti-staleness flag: same persona ≥ THRESHOLD in a row WITHOUT a switch
        needs_review = 1 if consecutive_count >= ANTI_STALENESS_THRESHOLD else 0
        if needs_review:
            print(
                f"[persona-selector] FLAG: {entry['persona_id']} selected "
                f"{consecutive_count}x in a row for "
                f"({entry['department']}, {entry['task_category']}) — "
                f"needs_review=1",
                file=sys.stderr,
            )

        cur.execute(
            """
            INSERT INTO persona_assignment
                (department_id, task_category, persona_id, persona_name,
                 persona_mode, persona_version, last_score, last_assigned_at,
                 switch_count, consecutive_count, needs_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT (department_id, task_category) DO UPDATE SET
                persona_id        = excluded.persona_id,
                persona_name      = excluded.persona_name,
                persona_mode      = excluded.persona_mode,
                persona_version   = excluded.persona_version,
                last_score        = excluded.last_score,
                last_assigned_at  = excluded.last_assigned_at,
                switch_count      = excluded.switch_count,
                consecutive_count = excluded.consecutive_count,
                needs_review      = CASE
                                      WHEN excluded.needs_review = 1 THEN 1
                                      ELSE persona_assignment.needs_review
                                    END
            """,
            (
                entry["department"],
                entry["task_category"],
                entry["persona_id"],
                entry.get("persona_name") or entry["persona_id"],
                entry.get("mode"),
                int(entry.get("persona_version", 1)),
                float(entry.get("score", 0.0)),
                switch_count,
                consecutive_count,
                needs_review,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"[persona-selector] WARN: persona_assignment upsert failed: {e}", file=sys.stderr)


def record_selection(selection: dict, task_text: str, department: str, db_path: Path):
    """
    Persist a selection to both persona-selection-log.md and the
    persona_assignment DB table. Adds no fields to the selection dict
    (returns None). Safe to call after main() prints the result.
    """
    from datetime import datetime
    if not selection or not selection.get("persona_id"):
        return  # nothing to record (e.g., mechanical task / no persona)

    llm_meta = selection.get("layers", {}).get("_llm_reasoning", {}) if isinstance(selection.get("layers"), dict) else {}
    reasoning_parts = []
    for k in ("mission", "owner_values", "company_kpis", "dept_kpis"):
        v = llm_meta.get(k) if isinstance(llm_meta, dict) else None
        if v:
            reasoning_parts.append(f"{k}: {v[:60]}")
    reasoning = " | ".join(reasoning_parts) if reasoning_parts else "(heuristic mode — no LLM reasoning)"

    entry = {
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "task_id":        os.environ.get("OPENCLAW_TASK_ID", "(no-task-id)"),
        "department":     department,
        "task_category":  selection.get("task_category", "general"),
        "persona_id":     selection["persona_id"],
        "persona_name":   selection.get("persona_name") or selection["persona_id"],
        "mode":           selection.get("interaction_mode") or selection.get("mode") or "leadership",
        "persona_version": selection.get("persona_version", 1),
        "score":          selection.get("score", 0.0),
        "reasoning":      reasoning,
        "layers":         selection.get("layers", {}),
        "variety_applied": selection.get("variety_applied", False),
    }
    write_selection_log_md(find_selection_log(), entry)
    write_persona_assignment_db(db_path, entry)
    # v10.14.28: per-pick history row so the NEXT call's variety penalty can
    # see who's been getting hammered. Track A's perm fix is required for the
    # write to succeed on locked-down clients; failure is logged and ignored
    # (variety degrades to baseline behavior — still correct, just stickier).
    write_persona_selection_log_row(db_path, entry)


def record_task_completion(task_id: str, persona_id: str, department: str,
                            task_category: str, task_text: str, task_output: str,
                            db_path: Path = None) -> dict:
    """
    Invoke verify-persona-adherence.py to score how well the agent's output
    followed the assigned persona's methodology. Writes the result to
    persona_assignment.verification_json + verification_last_score +
    verification_count via the verify script's own DB writer.

    This is the WIRING that the v2.0 audit Phase 16 PM4 flagged as missing:
    the script existed but nothing called it. Now persona-selector-v2.py
    itself can be invoked with --mode record-completion to trigger the
    adherence verification post-task.

    Returns the verify script's JSON result (or an error dict on failure).
    """
    import subprocess
    if db_path is None:
        db_path = find_dashboard_db()

    verify_script = Path(__file__).parent / "verify-persona-adherence.py"
    if not verify_script.exists():
        return {
            "ok": False,
            "error": f"verify-persona-adherence.py not found at {verify_script}",
        }

    # Write task_output to a temp file (CLI takes --output-file or --output-text;
    # using a file avoids any shell quoting / large-content issues).
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                       encoding="utf-8") as tmp:
        tmp.write(task_output)
        tmp_path = tmp.name

    cmd = [
        sys.executable, str(verify_script),
        "--persona-id", persona_id,
        "--task-id",    task_id,
        "--department", department,
        "--task-category", task_category,
        "--task-text",  task_text[:1500],
        "--output-file", tmp_path,
        "--format",     "json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        if proc.returncode != 0:
            return {
                "ok":         False,
                "error":      f"verify exited {proc.returncode}",
                "stderr":     proc.stderr[:500],
            }
        try:
            result = json.loads(proc.stdout)
            result["ok"] = True
            return result
        except json.JSONDecodeError:
            return {
                "ok":     False,
                "error":  "verify output not JSON",
                "stdout": proc.stdout[:500],
            }
    except subprocess.TimeoutExpired:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return {"ok": False, "error": "verify-persona-adherence timed out (120s)"}
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


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
    """Read persona-categories.json or scan personas dir.

    Schema 1.0 wraps the 40 persona IDs under a top-level "personas" key alongside
    metadata fields (schemaVersion, created, domainTags, perspectiveTags). The
    pre-v10.14.27 version returned `list(data.keys())` which yielded the 5 meta
    fields instead of the 40 real persona IDs — causing the selector to score
    "schemaVersion" / "created" / "domainTags" / "perspectiveTags" / "personas"
    as if they were personas and return the title-cased meta-key
    ("Schemaversion") as the chosen persona for every task. Fixed in v10.14.27
    (PR #24); v10.14.28 keeps that fix and adds the variety logic on top.
    """
    pc_file = paths["persona_categories"]
    if pc_file.exists():
        try:
            data = json.loads(pc_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Schema 1.0 (current): personas live under data["personas"].
                if isinstance(data.get("personas"), dict):
                    return list(data["personas"].keys())
                if isinstance(data.get("personas"), list):
                    return [
                        d.get("id") or d.get("name")
                        for d in data["personas"]
                        if isinstance(d, dict)
                    ]
                # Legacy flat-dict schema: filter out known meta-keys.
                META_KEYS = {"schemaVersion", "schema_version", "created",
                             "updated", "domainTags", "domain_tags",
                             "perspectiveTags", "perspective_tags",
                             "personas", "metadata", "version"}
                return [k for k in data.keys() if k not in META_KEYS]
            if isinstance(data, list):
                return [d.get("id") or d.get("name") for d in data if isinstance(d, dict)]
        except Exception:
            pass
    persona_root = paths["coaching_personas"] / "personas"
    if persona_root.exists():
        return [p.name for p in persona_root.iterdir() if p.is_dir()]
    return []


_COMPANY_CONFIG_CACHE = {"path": None, "data": None, "warned": False}


def load_company_config(paths: dict) -> dict:
    """Load company-config.json (schema v2.0). Warns ONCE to stderr if absent."""
    cfg_path = paths.get("company_config")
    if not cfg_path or not cfg_path.exists():
        if not _COMPANY_CONFIG_CACHE["warned"]:
            print(f"[persona-selector] WARN: company-config.json not found at "
                  f"{cfg_path}. Layers 1-3 will fall back to neutral defaults. "
                  f"Re-run Skill 23 build-workforce to generate it.",
                  file=sys.stderr)
            _COMPANY_CONFIG_CACHE["warned"] = True
        return {}
    if _COMPANY_CONFIG_CACHE["path"] == str(cfg_path) and _COMPANY_CONFIG_CACHE["data"] is not None:
        return _COMPANY_CONFIG_CACHE["data"]
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        _COMPANY_CONFIG_CACHE["path"] = str(cfg_path)
        _COMPANY_CONFIG_CACHE["data"] = data
        if data.get("schema_version", "1.0") < "2.0":
            print(f"[persona-selector] WARN: company-config.json is schema "
                  f"v{data.get('schema_version', '1.0')} — Layers 1-3 need v2.0. "
                  f"Re-run Skill 23 build-workforce to upgrade.",
                  file=sys.stderr)
        return data
    except Exception as e:
        print(f"[persona-selector] ERROR reading company-config.json: {e}", file=sys.stderr)
        return {}


def _persona_keywords(persona_id: str) -> list:
    """Tokenize persona-id into lowercase keyword list (filter stopwords)."""
    stop = {"the", "and", "of", "or", "a", "an", "to", "in", "on", "for"}
    parts = persona_id.lower().replace("_", "-").split("-")
    return [p for p in parts if p and p not in stop]


# Human-readable label keys, in priority order, for an object-shaped KPI /
# value entry. company-config.json drifted between two schemas in the wild:
#   schema A (template / upgrade-company-config.py): list[str]
#       e.g. ["monthly recurring revenue", "client retention 90-day"]
#   schema B (some live boxes, e.g. interview-generated):  list[dict]
#       e.g. [{"name": "monthly recurring revenue", "target": "50000"}, ...]
# The pre-v13.8.9 scoring layers did `", ".join(company_kpis)` assuming schema A,
# which raised `TypeError: sequence item 0: expected str instance, dict found`
# on every box carrying a schema-B config (crashing the whole selector).
_KPI_LABEL_KEYS = ("name", "label", "kpi", "metric", "title", "text")


def _kpi_labels(items) -> list:
    """Coerce a company_kpis / owner_values / dept_kpis array to a list of
    human-readable label strings, robust to BOTH config schemas.

    - str item  → used as-is (stripped).
    - dict item → first non-empty value among _KPI_LABEL_KEYS; if none of those
                  keys is present, fall back to the first non-empty string value
                  in the dict, else a compact JSON dump so nothing is silently
                  lost.
    - anything else → str(item).

    Empty / None / non-list input returns []. Never raises — this is the guard
    that keeps `" ".join(_kpi_labels(...))` from ever crashing the selector.
    """
    if not items:
        return []
    if not isinstance(items, (list, tuple)):
        # Defensive: a bare string slipped through (pre-v2.0 comma form, etc.)
        if isinstance(items, str):
            return [p.strip() for p in items.split(",") if p.strip()]
        return [str(items)]
    out = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
        elif isinstance(item, dict):
            label = None
            for k in _KPI_LABEL_KEYS:
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    label = v.strip()
                    break
            if label is None:
                # No known label key — take the first non-empty string value,
                # else compact-JSON the dict so the layer still has *something*.
                for v in item.values():
                    if isinstance(v, str) and v.strip():
                        label = v.strip()
                        break
            if label is None:
                try:
                    label = json.dumps(item, ensure_ascii=False, sort_keys=True)
                except Exception:
                    label = str(item)
            out.append(label)
        else:
            s = str(item).strip()
            if s:
                out.append(s)
    return out


def _heuristic_layer_scores(persona_id: str, task_text: str, owner_profile: str,
                             department_id: str, cc: dict, paths: dict) -> dict:
    """Keyword-hit baseline (SCORING_MODE=heuristic). Cheap, no LLM calls."""
    kws = _persona_keywords(persona_id)

    mission_text = (cc.get("mission") or "").lower()
    soul_md = paths.get("soul_md")
    if soul_md and soul_md.exists():
        mission_text += " " + soul_md.read_text(encoding="utf-8", errors="replace").lower()
    if mission_text:
        hits = sum(1 for kw in kws if kw in mission_text)
        mission_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        mission_score = 0.6

    values_text = " ".join(_kpi_labels(cc.get("owner_values"))).lower()
    if owner_profile:
        values_text += " " + owner_profile.lower()
    if values_text:
        hits = sum(1 for kw in kws if kw in values_text)
        values_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        values_score = 0.6

    company_kpis = _kpi_labels(cc.get("company_kpis"))
    if company_kpis:
        kpi_text = " ".join(company_kpis).lower()
        hits = sum(1 for kw in kws if kw in kpi_text)
        company_kpi_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        company_kpi_score = 0.6

    dept_kpis_map = cc.get("dept_kpis") or {}
    dept_kpis = _kpi_labels(dept_kpis_map.get(department_id) or dept_kpis_map.get(f"dept-{department_id}"))
    if dept_kpis:
        dept_kpi_text = " ".join(dept_kpis).lower()
        hits = sum(1 for kw in kws if kw in dept_kpi_text)
        dept_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        dept_score = 0.6

    # Layer 5 (Task Fit) — semantic similarity via Gemini Embedding 2,
    # falling back to keyword overlap, falling back to neutral 0.6.
    # The pre-v10.8.0 text-length heuristic (0.7 + len/1000) was the gap
    # the v2.0 audit flagged. Replaced with semantic_task_fit module.
    tf = semantic_task_fit(persona_id, task_text, paths)
    task_fit = tf["score"]

    return {
        "mission":      round(mission_score, 4),
        "owner_values": round(values_score, 4),
        "company_kpis": round(company_kpi_score, 4),
        "dept_kpis":    round(dept_score, 4),
        "task_fit":     round(task_fit, 4),
        "_task_fit_method": tf["method"],
    }


def _llm_layer_scores(persona_id: str, task_text: str, owner_profile: str,
                       department_id: str, cc: dict, paths: dict) -> dict:
    """
    LLM-backed scoring for Layers 1-4 (Wave 3). Each layer is one cached LLM
    call to DeepSeek V4 Pro (Ollama Cloud primary, OpenRouter fallback,
    Gemini 3.1 Flash Lite last resort — see llm_score.py).
    """
    persona_summary = summarize_persona_blueprint(persona_id, max_chars=2000)

    soul_excerpt = "(missing)"
    if paths.get("soul_md") and paths["soul_md"].exists():
        soul_excerpt = paths["soul_md"].read_text(encoding="utf-8", errors="replace")[:800]
    mission_ctx = (
        f"Company mission: {cc.get('mission') or '(none stated)'}\n"
        f"Workspace SOUL.md excerpt: {soul_excerpt}"
    )
    mission_res = score_layer(persona_id, "mission", persona_summary, mission_ctx)

    values_list = _kpi_labels(cc.get("owner_values"))
    values_ctx = (
        f"Stated owner values: {', '.join(values_list) if values_list else '(none stated)'}\n\n"
        f"Owner behavioral profile (USER.md excerpt):\n{owner_profile[:1500] if owner_profile else '(no profile)'}"
    )
    values_res = score_layer(persona_id, "owner_values", persona_summary, values_ctx)

    company_kpis = _kpi_labels(cc.get("company_kpis"))
    company_kpi_ctx = (
        f"Company-level KPIs: {', '.join(company_kpis) if company_kpis else '(none defined)'}\n"
        f"Company industry: {cc.get('industry') or '(unspecified)'}"
    )
    company_kpi_res = score_layer(persona_id, "company_kpis", persona_summary, company_kpi_ctx)

    dept_kpis_map = cc.get("dept_kpis") or {}
    dept_kpis = _kpi_labels(dept_kpis_map.get(department_id) or dept_kpis_map.get(f"dept-{department_id}"))
    dept_kpi_ctx = (
        f"Department: {department_id}\n"
        f"Department KPIs: {', '.join(dept_kpis) if dept_kpis else '(none defined)'}"
    )
    dept_kpi_res = score_layer(persona_id, "dept_kpis", persona_summary, dept_kpi_ctx)

    # Layer 5 (Task Fit) — semantic similarity via Gemini Embedding 2.
    # Replaces the v10.7.0 text-length heuristic per v2.0 audit Phase 16 PM1.
    tf = semantic_task_fit(persona_id, task_text, paths, persona_summary)
    task_fit = tf["score"]

    return {
        "mission":      round(mission_res["score"], 4),
        "owner_values": round(values_res["score"], 4),
        "company_kpis": round(company_kpi_res["score"], 4),
        "dept_kpis":    round(dept_kpi_res["score"], 4),
        "task_fit":     round(task_fit, 4),
        "_task_fit_method": tf["method"],
        "_llm_reasoning": {
            "mission":      mission_res.get("reasoning", "")[:200],
            "owner_values": values_res.get("reasoning", "")[:200],
            "company_kpis": company_kpi_res.get("reasoning", "")[:200],
            "dept_kpis":    dept_kpi_res.get("reasoning", "")[:200],
        },
        "_llm_meta": {
            "model": mission_res.get("model", "?"),
            "any_fallback": any(r.get("fallback") for r in (
                mission_res, values_res, company_kpi_res, dept_kpi_res
            )),
        },
    }


def compute_layer_scores(persona_id: str, task_text: str, owner_profile: str,
                          department_id: str, paths: dict,
                          scoring_mode: str = None) -> dict:
    """
    Dispatch to heuristic or LLM-based scoring depending on the EFFECTIVE mode.
    Default mode: 'llm' when llm_score module is importable, else 'heuristic'.
    Override globally with the `SCORING_MODE=heuristic` env var.

    G13: `scoring_mode` lets select_persona() force the cheap heuristic path for
    a SINGLE selection (the LLM fan-out gate) WITHOUT mutating the process-global
    SCORING_MODE. None → fall back to the global SCORING_MODE (unchanged default).
    """
    effective = (scoring_mode or SCORING_MODE)
    cc = load_company_config(paths)
    if effective == "llm" and LLM_AVAILABLE:
        return _llm_layer_scores(persona_id, task_text, owner_profile,
                                   department_id, cc, paths)
    return _heuristic_layer_scores(persona_id, task_text, owner_profile,
                                     department_id, cc, paths)


def score_persona(persona_id: str, task_text: str, owner_profile: str,
                  department_id: str, weights: dict, paths: dict, db_path: Path,
                  scoring_mode: str = None) -> dict:
    """Compute total weighted score with override applied.

    G13: `scoring_mode` is threaded to compute_layer_scores so the caller can
    bound LLM fan-out per selection (None → process-global SCORING_MODE).
    """
    layers = compute_layer_scores(persona_id, task_text, owner_profile,
                                   department_id, paths, scoring_mode=scoring_mode)
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
                   paths: dict, db_path: Path, variety: bool = True) -> dict:
    """Run the pre-scoring funnel then score survivors and return one.

    PRE-SCORING FUNNEL (PRD item 1.1 — ported from v1, native in v2):
      Stage A: governing-personas.md pool (or all personas if absent).
      Stage B: DEPT_DOMAIN_TAGS keyword filter — narrows to domain-relevant.
      Stage C: gemini-search semantic retrieval — intersect top-10 hits.
      Each stage falls back to the previous stage output on empty intersection
      (never filters to zero). funnel counts appear in output JSON.

    Stage D — 5-layer scoring (existing logic):
    With `variety=True` (default), apply the v10.14.28 anti-repetition logic:
      1. Compute base 5-layer scores for funnel survivors only.
      2. Read recent-use counts from persona_selection_log scoped to
         (department, task_category) within VARIETY_WINDOW_HOURS.
      3. Multiply each persona's score by variety_penalty_factor(uses).
      4. If top-1's adjusted score dominates top-3 by ≥VARIETY_DOMINANCE_RATIO
         pick top-1 (clear winner). Otherwise weighted-sample from top-N.

    With `variety=False`, behave as the pre-v10.14.28 selector — pure top-1
    by base score, no penalty, no sampling. Used by `--no-variety` for
    deterministic debugging / regression testing.
    """
    all_personas = list_available_personas(paths)
    owner_profile = read_owner_profile(paths)

    if not all_personas:
        return {
            "persona_id": None,
            "score": 0.0,
            "warning": "NO_PERSONAS_AVAILABLE",
            "message": "Run Skill 22 on at least one book to activate persona-guided work.",
            "mode": mode,
            "funnel": {"pool": 0, "category": 0, "semantic": 0},
        }

    # Stages A-C: build candidate pool via funnel
    personas, funnel, semantic_order = build_candidate_pool(task, department, all_personas, paths)

    # ─── G13: bound LLM fan-out BEFORE Stage-D scoring (token-furnace guard) ──
    # Enforced here at the scoring gate (a rule not enforced does not exist):
    #   • LLM GATE — when SCORING_MODE='llm' but the candidate set cannot be
    #     bounded (no governing pool AND no semantic ranking), force the cheap
    #     heuristic path for THIS selection. A fresh, unbounded box therefore
    #     cannot fan out to ~160 LLM calls. No cron, no resume — the burn never
    #     starts. Bounded boxes are unaffected (full quality preserved).
    #   • FINALIST CAP — when bounded but the survivor set still exceeds
    #     STAGE_D_LLM_FINALIST_CAP, LLM-score only the top-cap survivors by
    #     semantic rank (most task-relevant first).
    effective_scoring_mode = SCORING_MODE
    governing_pool_exists = funnel.get("pool_source") == "governing-personas.md"
    have_semantic_rank = bool(semantic_order)
    funnel["scoring_mode_requested"] = SCORING_MODE
    if SCORING_MODE == "llm" and LLM_AVAILABLE:
        if not (governing_pool_exists or have_semantic_rank):
            effective_scoring_mode = "heuristic"
            funnel["llm_gate"] = "downgraded-heuristic:unbounded-fresh-box"
        elif len(personas) > STAGE_D_LLM_FINALIST_CAP:
            if semantic_order:
                personas_set = set(personas)
                ranked = [p for p in semantic_order if p in personas_set]
                tail = [p for p in personas if p not in set(ranked)]
                personas = (ranked + tail)[:STAGE_D_LLM_FINALIST_CAP]
            else:
                # Bounded by a governing pool but no semantic order to rank by;
                # keep the governing-curated head (deterministic, bounded).
                personas = personas[:STAGE_D_LLM_FINALIST_CAP]
            funnel["llm_gate"] = "capped"
            funnel["llm_finalists"] = len(personas)
        else:
            funnel["llm_gate"] = "ok"
    funnel["scoring_mode_effective"] = effective_scoring_mode

    # Stage D: 5-layer scoring on funnel survivors only
    scored = [score_persona(p, task, owner_profile, department, weights, paths,
                            db_path, scoring_mode=effective_scoring_mode)
              for p in personas]

    task_category = infer_task_category(task)

    # ── Perspective bonus (additive-only, never-to-zero) ──────────────────────
    # Nudge a persona UP when the task EXPLICITLY invokes the lived-experience lens
    # its source genuinely carries. Empty/absent perspective[] -> 0.0 bonus, so this
    # can never eliminate, penalize, or zero-score any persona. Generic tasks invoke
    # no lens -> task_perspectives is empty -> the whole block is skipped (no-op).
    task_perspectives = infer_task_perspectives(task)
    if task_perspectives:
        pc_file = paths.get("persona_categories")
        personas_meta: dict = {}
        if pc_file and Path(pc_file).exists():
            try:
                _cd = json.loads(Path(pc_file).read_text(encoding="utf-8"))
                personas_meta = _cd.get("personas", {}) or {}
            except Exception:
                personas_meta = {}
        if personas_meta:
            for s in scored:
                pinfo = personas_meta.get(s["persona_id"], {})
                bonus = perspective_bonus(pinfo.get("perspective") or [], task_perspectives)
                if bonus > 0.0:
                    s["perspective_bonus"] = round(bonus, 4)
                    s["base_score"] = round(s["base_score"] + bonus, 4)
                    s["score"] = round(s["score"] + bonus, 4)

    if variety:
        recent_uses = read_recent_use_counts(department, task_category,
                                              VARIETY_WINDOW_HOURS, db_path)
        for s in scored:
            uses = recent_uses.get(s["persona_id"], 0)
            factor = variety_penalty_factor(uses)
            s["base_score_pre_variety"] = s["score"]
            s["recent_use_count"]      = uses
            s["variety_factor"]        = round(factor, 4)
            s["score"]                 = round(s["score"] * factor, 4)
        scored.sort(key=lambda x: x["score"], reverse=True)
        picked, picked_idx, was_sampled = pick_with_variety(scored)
        variety_applied = True
    else:
        scored.sort(key=lambda x: x["score"], reverse=True)
        picked = scored[0]
        picked_idx = 0
        was_sampled = False
        variety_applied = False

    top = picked  # selected persona (may not be score-rank #1 if sampled)

    result = {
        "persona_id": top["persona_id"],
        "persona_name": top["persona_id"].replace("-", " ").title(),
        "persona_version": 1,
        "score": top["score"],
        "base_score": top["base_score"],
        "override_factor": top["override_factor"],
        "interaction_mode": mode,
        "task_category": task_category,
        "weights_used": weights,
        "layers": top["layers"],
        "funnel": funnel,
        "variety_applied": variety_applied,
        "variety": {
            "enabled": variety_applied,
            "was_sampled": was_sampled,
            "picked_rank": picked_idx + 1,
            "window_hours": VARIETY_WINDOW_HOURS,
            "penalty_per_use": VARIETY_PENALTY_PER_USE,
            "dominance_ratio": VARIETY_DOMINANCE_RATIO,
            "sample_top_n": VARIETY_SAMPLE_TOP_N,
            "recent_use_count": top.get("recent_use_count", 0),
            "variety_factor": top.get("variety_factor", 1.0),
        },
        "breakdown": {"top_3": scored[:3]},
    }
    if top["score"] < 0.5:
        result["warning"] = "LOW_CONFIDENCE_SELECTION"
        result["message"] = f"Best persona scored {top['score']:.2f}. Consider adding more personas via Skill 22."
    return result


def main():
    parser = argparse.ArgumentParser(description="v2.1-aware persona selector (stickiness + adaptive weights + behavioral profile)")
    parser.add_argument("--mode", default="select",
                        choices=["select", "record-completion"],
                        help="select = pick a persona for a task (default). "
                             "record-completion = invoke verify-persona-adherence "
                             "for an already-completed task (v10.8.0 P0-2 wiring).")
    parser.add_argument("--task", required=False)
    parser.add_argument("--department", required=False)
    parser.add_argument("--format", default="json", choices=["json", "human"])
    parser.add_argument("--skip-stickiness", action="store_true", help="Force fresh selection even if a sticky assignment exists")
    parser.add_argument("--no-variety", action="store_true",
                        help="Disable v10.14.28 anti-repetition variety logic "
                             "(recency penalty + top-N weighted sampling). "
                             "Use for deterministic debugging / regression tests.")
    # record-completion mode args
    parser.add_argument("--task-id", help="(record-completion) task identifier")
    parser.add_argument("--persona-id", help="(record-completion) persona that governed the task")
    parser.add_argument("--task-category", default="general", help="(record-completion)")
    parser.add_argument("--task-output-file", help="(record-completion) path to task output file")
    parser.add_argument("--task-output", help="(record-completion) inline task output")
    args = parser.parse_args()

    # PRD 1.5: normalise --department to the canonical slug form immediately after
    # parsing, before ANY DB write, stickiness key, or dir lookup.  This ensures
    # department_id in every DB row is the bare slug (e.g. "marketing", not
    # "dept-marketing" or "Marketing") regardless of what the caller passed.
    if args.department:
        _raw_dept = args.department
        args.department = canonical_dept_slug(_raw_dept)
        if not args.department:
            print(json.dumps({"error": f"Invalid --department value {_raw_dept!r}: normalises to empty string"}))
            return 1

    paths = get_openclaw_paths()
    db_path = find_dashboard_db()
    # PRD 1.3: expose resolved DB path in every JSON response so a missing DB
    # is visible on every selection, never a silent no-op.
    db_field = str(db_path) if is_db_found(db_path) else "none"

    # ─── record-completion mode (P0-2 wiring) ────────────────────────────
    if args.mode == "record-completion":
        if not (args.task_id and args.persona_id and args.department):
            parser.error("--mode record-completion requires --task-id, --persona-id, --department")
        # Read task output from file or inline
        if args.task_output:
            task_output = args.task_output
        elif args.task_output_file:
            try:
                task_output = Path(args.task_output_file).read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                print(json.dumps({"ok": False, "error": f"could not read output file: {e}"}, indent=2))
                return 2
        else:
            parser.error("--mode record-completion requires --task-output or --task-output-file")
        task_text = args.task or "(no task text supplied)"
        result = record_task_completion(
            task_id=args.task_id,
            persona_id=args.persona_id,
            department=args.department,
            task_category=args.task_category,
            task_text=task_text,
            task_output=task_output,
            db_path=db_path,
        )
        print(json.dumps(result, indent=2) if args.format == "json"
              else f"adherence: {result.get('adherence_score', 'n/a')}")
        return 0 if result.get("ok") else 1

    # ─── select mode (default) ────────────────────────────────────────────
    if not (args.task and args.department):
        parser.error("--task and --department are required for select mode")

    # Mode detection
    mode = detect_interaction_mode(args.task)
    task_category = infer_task_category(args.task)

    # Mechanical task check
    # BUG-FIX v11.6.0: use word-boundary regex for single-word shell commands so
    # substring matches like "emails" (contains "ls "), "shipping" (contains "ping"),
    # and "controls/tools" (contain "ls ") do NOT false-trigger no_persona_required.
    # Multi-word phrases ("check disk", "check memory") are specific enough for plain
    # substring match.  Single-word commands use \b anchors.
    _t = args.task.lower()
    _mechanical_hit = any(m in _t for m in ("check disk", "check memory")) or any(
        re.search(r"\b" + re.escape(m) + r"\b", _t)
        for m in ("restart", "reboot", "ping", "ls", "chmod", "chown")
    )
    if _mechanical_hit:
        out = {
            "persona_id": None,
            "no_persona_required": True,
            "message": "Operational/mechanical task — no persona required.",
            "task_category": task_category,
            "db": db_field,  # PRD 1.3: visible on every response
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
            "db": db_field,  # PRD 1.3: visible on every response
        }
        record_selection(out, args.task, args.department, db_path)
        print(json.dumps(out, indent=2) if args.format == "json" else f"STICKY: {out['persona_name']} ({out['score']:.2f})")
        return 0

    # Fresh selection
    weights = get_weights_for_task(args.task, mode)

    variety_enabled = not args.no_variety

    if mode == "hybrid":
        leader = select_persona(args.task, args.department, "leadership", weights, paths, db_path, variety=variety_enabled)
        coach = select_persona(args.task, args.department, "coaching",
                                get_weights_for_task(args.task, "coaching"), paths, db_path, variety=variety_enabled)
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
            "layers": leader.get("layers", {}),
        }
    else:
        out = select_persona(args.task, args.department, mode, weights, paths, db_path, variety=variety_enabled)

    # PRD 1.3: inject db path so every selection response shows whether the DB was found.
    out["db"] = db_field

    record_selection(out, args.task, args.department, db_path)
    print(json.dumps(out, indent=2) if args.format == "json" else f"{out.get('persona_name','(none)')} ({out.get('score',0):.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
