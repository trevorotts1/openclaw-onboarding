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
    }
    write_selection_log_md(find_selection_log(), entry)
    write_persona_assignment_db(db_path, entry)


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

    values_text = " ".join(cc.get("owner_values") or []).lower()
    if owner_profile:
        values_text += " " + owner_profile.lower()
    if values_text:
        hits = sum(1 for kw in kws if kw in values_text)
        values_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        values_score = 0.6

    company_kpis = cc.get("company_kpis") or []
    if company_kpis:
        kpi_text = " ".join(company_kpis).lower()
        hits = sum(1 for kw in kws if kw in kpi_text)
        company_kpi_score = min(0.6 + (hits * 0.10), 0.95) if hits > 0 else 0.6
    else:
        company_kpi_score = 0.6

    dept_kpis_map = cc.get("dept_kpis") or {}
    dept_kpis = dept_kpis_map.get(department_id) or dept_kpis_map.get(f"dept-{department_id}") or []
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

    values_list = cc.get("owner_values") or []
    values_ctx = (
        f"Stated owner values: {', '.join(values_list) if values_list else '(none stated)'}\n\n"
        f"Owner behavioral profile (USER.md excerpt):\n{owner_profile[:1500] if owner_profile else '(no profile)'}"
    )
    values_res = score_layer(persona_id, "owner_values", persona_summary, values_ctx)

    company_kpis = cc.get("company_kpis") or []
    company_kpi_ctx = (
        f"Company-level KPIs: {', '.join(company_kpis) if company_kpis else '(none defined)'}\n"
        f"Company industry: {cc.get('industry') or '(unspecified)'}"
    )
    company_kpi_res = score_layer(persona_id, "company_kpis", persona_summary, company_kpi_ctx)

    dept_kpis_map = cc.get("dept_kpis") or {}
    dept_kpis = dept_kpis_map.get(department_id) or dept_kpis_map.get(f"dept-{department_id}") or []
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
                          department_id: str, paths: dict) -> dict:
    """
    Dispatch to heuristic or LLM-based scoring depending on SCORING_MODE.
    Default: 'llm' when llm_score module is importable, else 'heuristic'.
    Override with `SCORING_MODE=heuristic` env var (for offline tests or
    when API keys are missing).
    """
    cc = load_company_config(paths)
    if SCORING_MODE == "llm" and LLM_AVAILABLE:
        return _llm_layer_scores(persona_id, task_text, owner_profile,
                                   department_id, cc, paths)
    return _heuristic_layer_scores(persona_id, task_text, owner_profile,
                                     department_id, cc, paths)


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
    parser.add_argument("--mode", default="select",
                        choices=["select", "record-completion"],
                        help="select = pick a persona for a task (default). "
                             "record-completion = invoke verify-persona-adherence "
                             "for an already-completed task (v10.8.0 P0-2 wiring).")
    parser.add_argument("--task", required=False)
    parser.add_argument("--department", required=False)
    parser.add_argument("--format", default="json", choices=["json", "human"])
    parser.add_argument("--skip-stickiness", action="store_true", help="Force fresh selection even if a sticky assignment exists")
    # record-completion mode args
    parser.add_argument("--task-id", help="(record-completion) task identifier")
    parser.add_argument("--persona-id", help="(record-completion) persona that governed the task")
    parser.add_argument("--task-category", default="general", help="(record-completion)")
    parser.add_argument("--task-output-file", help="(record-completion) path to task output file")
    parser.add_argument("--task-output", help="(record-completion) inline task output")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    db_path = find_dashboard_db()

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
        record_selection(out, args.task, args.department, db_path)
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
            "layers": leader.get("layers", {}),
        }
    else:
        out = select_persona(args.task, args.department, mode, weights, paths, db_path)

    record_selection(out, args.task, args.department, db_path)
    print(json.dumps(out, indent=2) if args.format == "json" else f"{out.get('persona_name','(none)')} ({out.get('score',0):.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
