#!/usr/bin/env python3
"""
verify-persona-adherence.py — Post-task persona-adherence verification.

Called by the dispatcher after a task completes. Reads:
  - The assigned persona's blueprint methodology
  - The actual task output
And asks an LLM (DeepSeek V4 Pro via Ollama Cloud / OpenRouter fallback) to
score adherence on a 0.0-1.0 scale and surface the top 2-3 deviations.

Result is written:
  - To persona_assignment.verification_json in the dashboard DB (new column)
  - To stdout as JSON for the dispatcher

The protocol (persona-matching-protocol.md §"Post-Task Persona Verification")
mandates this check on every task completion. Phase 8 PM4 scored 1.0/10
because no code implemented it. This script closes that gap.

Usage:
    python3 verify-persona-adherence.py \\
        --persona-id alex-hormozi \\
        --task-id ceo-task-01 \\
        --department sales \\
        --task-text "write a follow-up email to the prospect" \\
        --output-file /tmp/task-output.md
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))

try:
    from llm_score import _build_prompt, _attempt_ollama_cloud, _attempt_openrouter  # type: ignore
    from llm_score import summarize_persona_blueprint, _cache_path  # type: ignore
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


ADHERENCE_PROMPT_TEMPLATE = """You are evaluating whether an AI agent's task output
followed the assigned persona's methodology.

PERSONA: {persona_id}
PERSONA METHODOLOGY (excerpt):
{persona_methodology}

TASK TEXT:
{task_text}

ACTUAL OUTPUT:
{task_output}

Score adherence on a 0.0–1.0 continuous scale:
  0.0–0.3 = output ignored the persona; could have been written by anyone
  0.4–0.6 = surface-level persona influence (some vocabulary, no methodology)
  0.7–0.85 = persona methodology clearly applied; standards mostly held
  0.86–1.0 = full embodiment; this is how the persona would have actually done it

Also identify the top 2-3 specific deviations (if any) where the output drifted
from the persona's approach.

Return ONLY a JSON object — no markdown, no preamble:
{{
  "adherence_score": <float 0.0-1.0>,
  "applied_standards": ["<short bullet>", "<short bullet>"],
  "deviations":       ["<short bullet>", "<short bullet>"],
  "notes":            "<one sentence>"
}}
"""


def find_dashboard_db() -> Path:
    """Locate mission-control.db across platforms."""
    if "DASHBOARD_DB_PATH" in os.environ:
        return Path(os.environ["DASHBOARD_DB_PATH"])
    for c in [
        Path("/data/mission-control/mission-control.db"),
        Path.home() / "projects" / "mission-control" / "mission-control.db",
        Path.home() / "blackceo-command-center" / "mission-control.db",
    ]:
        if c.exists():
            return c
    return Path("")


def ensure_verification_column(db_path: Path):
    """Add verification_json column to persona_assignment if missing. Idempotent."""
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        cols = conn.execute("PRAGMA table_info(persona_assignment)").fetchall()
        col_names = {c[1] for c in cols}
        if "verification_json" not in col_names:
            conn.execute("ALTER TABLE persona_assignment ADD COLUMN verification_json TEXT")
        if "verification_last_score" not in col_names:
            conn.execute("ALTER TABLE persona_assignment ADD COLUMN verification_last_score REAL")
        if "verification_count" not in col_names:
            conn.execute("ALTER TABLE persona_assignment ADD COLUMN verification_count INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"[verify] WARN: could not add verification columns: {e}", file=sys.stderr)


def write_verification_to_db(db_path: Path, department: str, task_category: str,
                              persona_id: str, result: dict):
    """Update persona_assignment row with the latest verification result."""
    if not db_path or not db_path.exists():
        return
    try:
        ensure_verification_column(db_path)
        conn = sqlite3.connect(str(db_path))
        # Get current verification_count (so we can increment)
        cur = conn.execute(
            "SELECT verification_count FROM persona_assignment "
            "WHERE department_id = ? AND task_category = ? AND persona_id = ?",
            (department, task_category, persona_id),
        )
        row = cur.fetchone()
        count = (row[0] or 0) + 1 if row else 1
        conn.execute(
            """
            UPDATE persona_assignment
               SET verification_json     = ?,
                   verification_last_score = ?,
                   verification_count    = ?
             WHERE department_id = ? AND task_category = ? AND persona_id = ?
            """,
            (json.dumps(result), float(result.get("adherence_score", 0.0)), count,
             department, task_category, persona_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"[verify] WARN: could not write verification to DB: {e}", file=sys.stderr)


def read_task_output(output_file: str, output_text: str) -> str:
    if output_text:
        return output_text
    if output_file:
        try:
            return Path(output_file).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"[verify] WARN: could not read {output_file}: {e}", file=sys.stderr)
    return ""


def call_llm_for_adherence(prompt: str) -> dict:
    """Try Ollama Cloud → OpenRouter DeepSeek → OpenRouter Gemini Flash Lite."""
    if not LLM_AVAILABLE:
        return {
            "adherence_score": 0.6,
            "applied_standards": ["llm_score module unavailable — stub result"],
            "deviations": [],
            "notes": "no LLM available; manual review required",
            "_fallback": True,
        }
    for name, fn in (
        ("ollama-cloud-deepseek-pro", lambda: _attempt_ollama_cloud(prompt)),
        ("openrouter-deepseek-pro",   lambda: _attempt_openrouter(prompt, "deepseek/deepseek-v4-pro")),
        ("openrouter-gemini-lite",    lambda: _attempt_openrouter(prompt, "google/gemini-3.1-flash-lite")),
    ):
        result = fn()
        if not result.get("ok"):
            continue
        # llm_score's _attempt_* return {score, reasoning} for the scoring layers.
        # For adherence we passed a different prompt that returns the full JSON
        # in the message. Re-parse the model's raw text from the cached call.
        # Since _attempt_ functions parse only {score, reasoning}, we need a
        # different call path. Re-call inline here with a manual parse.
        pass
    return _manual_call(prompt)


def _manual_call(prompt: str) -> dict:
    """Direct HTTP call that returns the full JSON the adherence prompt asks for."""
    import urllib.error, urllib.request

    def _env(k, default=""):
        v = os.environ.get(k)
        if v:
            return v
        for p in [os.path.expanduser("~/.openclaw/openclaw.json"),
                  "/data/.openclaw/openclaw.json"]:
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        return json.load(f).get("env", {}).get(k, default) or default
                except Exception:
                    pass
        return default

    def _post(url, headers, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _extract(p):
        return p["choices"][0]["message"]["content"].strip()

    def _parse(text):
        # Pull the top-level JSON object out of the response.
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "adherence_score" in obj:
                return obj
        except Exception:
            pass
        import re
        m = re.search(r"\{[\s\S]*?\"adherence_score\"[\s\S]*?\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

    attempts = []
    ocld_key = _env("OLLAMA_CLOUD_API_KEY")
    if ocld_key:
        attempts.append((
            "ollama-cloud-deepseek-pro",
            _env("OLLAMA_CLOUD_URL", "https://ollama.com/api").rstrip("/") + "/chat/completions",
            {"Authorization": f"Bearer {ocld_key}", "Content-Type": "application/json"},
            "deepseek-v4-pro:cloud",
        ))
    or_key = _env("OPENROUTER_API_KEY")
    if or_key:
        for model in ("deepseek/deepseek-v4-pro", "google/gemini-3.1-flash-lite"):
            attempts.append((
                f"openrouter/{model}",
                "https://openrouter.ai/api/v1/chat/completions",
                {"Authorization": f"Bearer {or_key}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
                 "X-Title": "OpenClaw persona-adherence"},
                model,
            ))

    last_err = "no providers configured"
    for name, url, headers, model_id in attempts:
        try:
            payload = _post(url, headers, {
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 400,
            })
            text = _extract(payload)
            parsed = _parse(text)
            if parsed:
                parsed["_model"] = name
                return parsed
            last_err = f"{name}: unparseable output: {text[:160]}"
        except Exception as e:
            last_err = f"{name}: {type(e).__name__}: {e}"
            continue

    return {
        "adherence_score": 0.6,
        "applied_standards": [],
        "deviations": [],
        "notes": f"all providers failed: {last_err[:200]}",
        "_fallback": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Post-task persona-adherence verification")
    parser.add_argument("--persona-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--department", required=True)
    parser.add_argument("--task-category", default="general")
    parser.add_argument("--task-text", required=True)
    parser.add_argument("--output-file", default="", help="Path to file with task output")
    parser.add_argument("--output-text", default="", help="Inline task output (overrides --output-file)")
    parser.add_argument("--format", default="json", choices=["json", "human"])
    args = parser.parse_args()

    task_output = read_task_output(args.output_file, args.output_text)
    if not task_output:
        print(json.dumps({
            "error": "no task output provided",
            "hint":  "pass --output-file or --output-text",
        }, indent=2))
        return 2

    persona_methodology = (
        summarize_persona_blueprint(args.persona_id, max_chars=3000)
        if LLM_AVAILABLE else f"(no blueprint summary; persona={args.persona_id})"
    )

    prompt = ADHERENCE_PROMPT_TEMPLATE.format(
        persona_id=args.persona_id,
        persona_methodology=persona_methodology[:3000],
        task_text=args.task_text[:1500],
        task_output=task_output[:4000],
    )
    result = _manual_call(prompt)
    result["task_id"]    = args.task_id
    result["persona_id"] = args.persona_id
    result["department"] = args.department
    result["task_category"] = args.task_category
    result["verified_at"] = datetime.now().isoformat()

    db_path = find_dashboard_db()
    write_verification_to_db(db_path, args.department, args.task_category,
                              args.persona_id, result)

    if args.format == "human":
        print(f"Persona: {args.persona_id}")
        print(f"Adherence: {result.get('adherence_score', 0):.2f}")
        print(f"Notes: {result.get('notes', '')}")
        if result.get("deviations"):
            print("Deviations:")
            for d in result["deviations"]:
                print(f"  - {d}")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
