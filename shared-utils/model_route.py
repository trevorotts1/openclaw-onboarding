#!/usr/bin/env python3
"""RF-014 `model` mode: the box's OWN default model picks the department.

Used ONLY when the rules (JEV, then the lexical/rule fallback) could not place a
task and the box's mode is `model`. Sovereignty: the model id is read from THIS
box's openclaw.json (agents.defaults.model.primary, then the main agent, then the
defaults' fallbacks) and is NEVER hardcoded here. Anthropic ids and free-tier ids
are not valid defaults for a client box (same rule as the Command Center
installer's cc_resolve_sovereign_model), so they do not count as "resolved".

No default resolves -> pick() answers {"status": "no_default_model"} and the
caller falls back to legacy and logs it. Anything the model says that is not
exactly one department slug from the box's own list becomes general-task: a
model can never invent a department, and an unplaceable task always lands in
general-task (RF-013).

ponytail: one blocking CLI call per unplaced task with a short timeout; add a
per-task cache or a batch call when unplaced traffic is high enough to matter.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

GENERAL = "general-task"
TIMEOUT_ENV = "OPENCLAW_MODEL_ROUTE_TIMEOUT_S"
BIN_ENV = "OPENCLAW_BIN"
# Command Center kills the bridge at a 3 s root deadline; stay well under it by default.
DEFAULT_TIMEOUT_S = 2.0
_MAX_TASK_CHARS = 1200
_MAX_DEPTS = 80
_REPLY_KEYS = ("text", "output", "content", "reply", "message", "response", "result")


def model_is_sovereign(model_id) -> bool:
    m = str(model_id or "").strip().lower()
    if not m or m == "openrouter/free" or m.endswith(":free"):
        return False
    return "anthropic" not in m and "claude" not in m


def _primary(node):
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return node.get("primary")
    return None


def resolve_default_model(config_path):
    """The box's own default text model id, or None. Read-only; never guesses."""
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict):
        return None
    defaults = agents.get("defaults") if isinstance(agents.get("defaults"), dict) else {}
    cands = [_primary(defaults.get("model"))]
    entries = agents.get("entries")
    if isinstance(entries, dict) and isinstance(entries.get("main"), dict):
        cands.append(_primary(entries["main"].get("model")))
    legacy = agents.get("list")
    if isinstance(legacy, list):
        named = [a for a in legacy if isinstance(a, dict)
                 and str(a.get("name") or a.get("id") or "").lower() == "main"]
        for agent in named or [a for a in legacy[:1] if isinstance(a, dict)]:
            cands.append(_primary(agent.get("model")))
    model = defaults.get("model")
    if isinstance(model, dict) and isinstance(model.get("fallbacks"), list):
        cands.extend(model["fallbacks"])
    for cand in cands:
        if isinstance(cand, str) and model_is_sovereign(cand):
            return cand.strip()
    return None


def find_openclaw():
    explicit = os.environ.get(BIN_ENV)
    if explicit and os.access(explicit, os.X_OK):
        return explicit
    for cand in (shutil.which("openclaw"), "/opt/homebrew/bin/openclaw",
                 "/usr/local/bin/openclaw",
                 str(Path.home() / ".openclaw" / "bin" / "openclaw"),
                 "/data/.npm-global/bin/openclaw",
                 "/data/linuxbrew/.linuxbrew/bin/openclaw"):
        if cand and os.access(cand, os.X_OK):
            return cand
    return None


def build_prompt(task, catalog):
    lines = []
    for entry in catalog[:_MAX_DEPTS]:
        label = " ".join(str(entry.get("text") or "").split())[:120]
        lines.append("- %s%s" % (entry["slug"], (": " + label) if label else ""))
    lines.append("- %s: anything that fits none of the above" % GENERAL)
    return (
        "You route one task to exactly one department of a company. "
        "Reply with ONLY the department slug from the list, nothing else.\n\n"
        "Departments:\n%s\n\nTask:\n%s\n\nSlug:"
        % ("\n".join(lines), " ".join(str(task).split())[:_MAX_TASK_CHARS]))


def _ask_cli(prompt, model_id, timeout_s):
    """One-shot model turn through the box's own OpenClaw. Returns text or None."""
    binary = find_openclaw()
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "infer", "model", "run", "--model", model_id,
             "--prompt", prompt, "--json"],
            capture_output=True, text=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _reply_text(raw):
    """The model's reply from either plain text or a JSON envelope."""
    raw = (raw or "").strip()
    try:
        node = json.loads(raw)
    except ValueError:
        return raw
    found = []

    def walk(n):
        if isinstance(n, str):
            found.append(n)
        elif isinstance(n, dict):
            for key in _REPLY_KEYS:
                if key in n:
                    walk(n[key])
        elif isinstance(n, list):
            for item in n:
                walk(item)
    walk(node)
    return found[-1].strip() if found else ""


def parse_slug(raw, catalog):
    """The slug the model named, only if it is EXACTLY one catalog slug (or general-task)."""
    lines = [ln for ln in _reply_text(raw).splitlines() if ln.strip()]
    if not lines:
        return None
    answer = re.sub(r"^[\s`'\"*_>\-:]+|[\s`'\"*_.,;:!]+$", "", lines[-1]).lower()
    slugs = {e["slug"].lower(): e["slug"] for e in catalog}
    slugs[GENERAL] = GENERAL
    return slugs.get(answer)


def pick(task, catalog, config_path, *, ask=None, timeout_s=None):
    """Ask the box's default model which department owns `task`.

    status: ok | no_default_model | model_failed. department is always a catalog slug
    or general-task; the caller decides what each status means.
    """
    model_id = resolve_default_model(config_path)
    if not model_id:
        return {"status": "no_default_model", "department": None, "model": None}
    if timeout_s is None:
        try:
            timeout_s = float(os.environ.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT_S)
        except ValueError:
            timeout_s = DEFAULT_TIMEOUT_S
    try:
        raw = (ask or _ask_cli)(build_prompt(task, catalog), model_id, timeout_s)
    except Exception:  # noqa: BLE001 -- a model hiccup must never break routing
        raw = None
    if raw is None:
        return {"status": "model_failed", "department": GENERAL, "model": model_id,
                "detail": "no reply from the box's default model"}
    slug = parse_slug(raw, catalog)
    if slug is None:
        return {"status": "ok", "department": GENERAL, "model": model_id,
                "detail": "reply was not exactly one department slug"}
    return {"status": "ok", "department": slug, "model": model_id, "detail": "model_pick"}
