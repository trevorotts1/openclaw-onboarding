"""
llm_score.py — LLM-backed scoring helper for OpenClaw.

Used by Skill 23's persona-selector to evaluate Layers 1-4 (mission /
owner_values / company_kpis / dept_kpis) against persona blueprints.
Returns a single float in [0.0, 1.0] with a short reasoning string.

Per company policy (memory: feedback-no-anthropic-for-subagents) no
Anthropic models are used in this pipeline. The model chain is:

    1. Ollama Cloud  — DeepSeek V4 Pro (primary, cheap + 1M context)
       Env: OLLAMA_CLOUD_API_KEY, OLLAMA_CLOUD_URL
            (default: https://ollama.com/api)

    2. OpenRouter    — DeepSeek V4 Pro (same model, paid fallback)
       Env: OPENROUTER_API_KEY  (already in ~/.openclaw/openclaw.json)

    3. OpenRouter    — Gemini 3.1 Flash Lite (cheapest last-resort)
       Env: OPENROUTER_API_KEY

A simple SQLite cache keyed by SHA-256(persona_id + layer + context) keeps
repeat scoring of the same persona for the same company free. TTL = 30 days.

Usage:
    from llm_score import score_layer
    result = score_layer(
        persona_id="alex-hormozi",
        layer="mission",
        persona_blueprint_summary="Hormozi values...",
        context="BlackCEO's mission is...",
    )
    # result == {"score": 0.82, "reasoning": "...", "model": "...", "cached": False}

This module never raises on LLM failure — it falls through the chain and
returns a NEUTRAL_FALLBACK score with reasoning="all models failed: <error>"
so the caller can keep working (degraded mode).
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_TTL_SECONDS = 30 * 24 * 60 * 60   # 30 days
HTTP_TIMEOUT_SECONDS = 30
NEUTRAL_FALLBACK_SCORE = 0.6


def _openclaw_env() -> dict:
    """Read .env-style values from ~/.openclaw/openclaw.json into a dict."""
    paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "/data/.openclaw/openclaw.json",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json.load(f)
                return data.get("env", {}) or {}
            except Exception:
                pass
    return {}


def _env(key: str, default: str = "") -> str:
    """Look up env var; fall back to openclaw.json env block."""
    v = os.environ.get(key)
    if v:
        return v
    return _openclaw_env().get(key, default) or default


# ───────────────────────────────────────────────────────────────────────
# Cache
# ───────────────────────────────────────────────────────────────────────

def _cache_path() -> Path:
    """Cache lives under workspace/data/, falling back to /tmp."""
    candidates = [
        Path.home() / "clawd" / "data" / "llm-score-cache.sqlite",
        Path.home() / ".openclaw" / "workspace" / "data" / "llm-score-cache.sqlite",
        Path("/tmp") / "openclaw-llm-score-cache.sqlite",
    ]
    for c in candidates:
        try:
            c.parent.mkdir(parents=True, exist_ok=True)
            return c
        except OSError:
            continue
    return candidates[-1]


def _cache_key(persona_id: str, layer: str, persona_summary: str, context: str) -> str:
    h = hashlib.sha256()
    h.update(persona_id.encode("utf-8"))
    h.update(b"|")
    h.update(layer.encode("utf-8"))
    h.update(b"|")
    h.update(persona_summary.encode("utf-8"))
    h.update(b"|")
    h.update(context.encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str):
    try:
        path = _cache_path()
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_cache (
                key TEXT PRIMARY KEY,
                score REAL NOT NULL,
                reasoning TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        cur = conn.execute(
            "SELECT score, reasoning, model, created_at FROM score_cache WHERE key = ?",
            (key,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        score, reasoning, model, created_at = row
        if time.time() - created_at > CACHE_TTL_SECONDS:
            return None
        return {"score": float(score), "reasoning": reasoning, "model": model, "cached": True}
    except sqlite3.Error:
        return None


def _cache_put(key: str, score: float, reasoning: str, model: str):
    try:
        path = _cache_path()
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_cache (
                key TEXT PRIMARY KEY,
                score REAL NOT NULL,
                reasoning TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO score_cache (key, score, reasoning, model, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, score, reasoning, model, int(time.time())),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


# ───────────────────────────────────────────────────────────────────────
# Prompt
# ───────────────────────────────────────────────────────────────────────

LAYER_PROMPTS = {
    "mission": (
        "How well does this persona's philosophy align with the company's "
        "mission?"
    ),
    "owner_values": (
        "How well does this persona's methodology match the company owner's "
        "behavioral identity and stated values?"
    ),
    "company_kpis": (
        "How well does this persona's expertise advance the company-level "
        "KPIs?"
    ),
    "dept_kpis": (
        "How well does this persona's methodology fit this specific "
        "department's KPIs and operational goals?"
    ),
}

SCORING_INSTRUCTIONS = """You are a persona-fit evaluator for a zero-human company.
Score on a 0.0–1.0 continuous scale where:
  0.0–0.3 = poor fit (philosophy clashes, wrong domain, or actively counterproductive)
  0.4–0.6 = neutral / generic fit (could work, no strong signal either way)
  0.7–0.85 = good fit (clear alignment, persona advances this dimension)
  0.86–1.0 = excellent fit (this persona is a top-tier match for this dimension)

Return ONLY a JSON object — no markdown, no preamble:
{"score": <float 0.0-1.0>, "reasoning": "<one sentence why>"}

Do NOT default to 0.7 when uncertain. If signal is genuinely weak in both
directions, return 0.5 with reasoning="insufficient signal".
"""


def _build_prompt(layer: str, persona_id: str, persona_summary: str, context: str) -> str:
    question = LAYER_PROMPTS.get(layer, "How well does this persona fit?")
    return (
        f"{SCORING_INSTRUCTIONS}\n\n"
        f"Question: {question}\n\n"
        f"Persona: {persona_id}\n"
        f"Persona summary:\n{persona_summary[:2000]}\n\n"
        f"Context (company / owner / KPIs / dept):\n{context[:2000]}\n"
    )


# ───────────────────────────────────────────────────────────────────────
# HTTP — OpenAI-completions-compatible
# ───────────────────────────────────────────────────────────────────────

def _post_chat(url: str, headers: dict, body: dict, timeout: int = HTTP_TIMEOUT_SECONDS) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _extract_message(payload: dict) -> str:
    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


def _parse_score_json(text: str) -> dict:
    """Pull {score, reasoning} out of a model response. Resilient to fluff."""
    if not text:
        return {"score": None, "reasoning": "empty response"}
    # Try direct parse
    try:
        obj = json.loads(text)
        score = float(obj.get("score", -1))
        if 0.0 <= score <= 1.0:
            return {"score": score, "reasoning": str(obj.get("reasoning", ""))[:500]}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Try to find a JSON object inside the text
    match = re.search(r'\{[^{}]*"score"\s*:\s*([0-9.]+)[^{}]*\}', text)
    if match:
        try:
            score = float(match.group(1))
            if 0.0 <= score <= 1.0:
                reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text)
                return {
                    "score": score,
                    "reasoning": reasoning_match.group(1)[:500] if reasoning_match else "parsed from non-JSON",
                }
        except (TypeError, ValueError):
            pass
    return {"score": None, "reasoning": f"parse failed: {text[:160]}"}


# ───────────────────────────────────────────────────────────────────────
# Provider attempts
# ───────────────────────────────────────────────────────────────────────

def _attempt_ollama_cloud(prompt: str) -> dict:
    api_key = _env("OLLAMA_CLOUD_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OLLAMA_CLOUD_API_KEY not set", "model": "ollama/deepseek-v4-pro:cloud"}
    base_url = _env("OLLAMA_CLOUD_URL", "https://ollama.com/api")
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "deepseek-v4-pro:cloud",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    try:
        payload = _post_chat(url, headers, body)
        text = _extract_message(payload)
        parsed = _parse_score_json(text)
        if parsed["score"] is None:
            return {"ok": False, "error": f"unparseable: {parsed['reasoning']}", "model": "ollama/deepseek-v4-pro:cloud"}
        return {"ok": True, "score": parsed["score"], "reasoning": parsed["reasoning"],
                "model": "ollama/deepseek-v4-pro:cloud"}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "model": "ollama/deepseek-v4-pro:cloud"}


def _attempt_openrouter(prompt: str, model_id: str) -> dict:
    api_key = _env("OPENROUTER_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OPENROUTER_API_KEY not set", "model": model_id}
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
        "X-Title": "OpenClaw persona-selector",
    }
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    try:
        payload = _post_chat(url, headers, body)
        text = _extract_message(payload)
        parsed = _parse_score_json(text)
        if parsed["score"] is None:
            return {"ok": False, "error": f"unparseable: {parsed['reasoning']}", "model": model_id}
        return {"ok": True, "score": parsed["score"], "reasoning": parsed["reasoning"],
                "model": model_id}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "model": model_id}


# ───────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────

def score_layer(
    persona_id: str,
    layer: str,
    persona_blueprint_summary: str,
    context: str,
    use_cache: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Score a single persona-layer fit using the configured LLM chain.

    Returns:
        {
          "score":     float in [0.0, 1.0],
          "reasoning": str,
          "model":     str   — which model returned the score
          "cached":    bool  — True if served from cache
          "fallback":  bool  — True if all models failed and we returned NEUTRAL_FALLBACK_SCORE
        }
    """
    key = _cache_key(persona_id, layer, persona_blueprint_summary, context)

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return {**cached, "fallback": False}

    prompt = _build_prompt(layer, persona_id, persona_blueprint_summary, context)

    chain = [
        ("ollama-cloud-deepseek-pro", lambda: _attempt_ollama_cloud(prompt)),
        ("openrouter-deepseek-pro",   lambda: _attempt_openrouter(prompt, "deepseek/deepseek-v4-pro")),
        ("openrouter-gemini-lite",    lambda: _attempt_openrouter(prompt, "google/gemini-3.1-flash-lite")),
    ]

    last_error = ""
    for name, attempt in chain:
        result = attempt()
        if result.get("ok"):
            if verbose:
                print(f"[llm_score] {layer}/{persona_id} via {result['model']} → {result['score']:.2f}",
                      file=sys.stderr)
            _cache_put(key, result["score"], result["reasoning"], result["model"])
            return {
                "score": result["score"],
                "reasoning": result["reasoning"],
                "model": result["model"],
                "cached": False,
                "fallback": False,
            }
        last_error = f"{name}: {result.get('error', 'unknown')}"
        if verbose:
            print(f"[llm_score] {name} failed: {result.get('error')}", file=sys.stderr)

    return {
        "score": NEUTRAL_FALLBACK_SCORE,
        "reasoning": f"all models failed: {last_error[:200]}",
        "model": "fallback",
        "cached": False,
        "fallback": True,
    }


def summarize_persona_blueprint(persona_id: str, max_chars: int = 2000) -> str:
    """
    Read the persona blueprint (if it exists) and return a short summary
    suitable for prompts. Looks under workspace/coaching-personas/personas/<id>/blueprint.md
    falling back to persona-id only if not found.
    """
    candidates = [
        Path.home() / "clawd" / "coaching-personas" / "personas" / persona_id / "blueprint.md",
        Path.home() / ".openclaw" / "workspace" / "coaching-personas" / "personas" / persona_id / "blueprint.md",
        Path("/data/.openclaw/workspace/coaching-personas/personas") / persona_id / "blueprint.md",
    ]
    for c in candidates:
        try:
            if c.exists():
                text = c.read_text(encoding="utf-8", errors="replace")
                return text[:max_chars]
        except OSError:
            continue
    return f"(no blueprint found for {persona_id})"


if __name__ == "__main__":
    # Quick smoke test
    import argparse
    parser = argparse.ArgumentParser(description="LLM-scored persona-layer fit")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--layer", required=True, choices=list(LAYER_PROMPTS.keys()))
    parser.add_argument("--context", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    summary = summarize_persona_blueprint(args.persona)
    result = score_layer(args.persona, args.layer, summary, args.context, verbose=args.verbose)
    print(json.dumps(result, indent=2))
