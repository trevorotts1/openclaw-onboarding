#!/usr/bin/env python3
"""JEV live chain: ask the Jev model to place a message, else say nothing.

Used by shared-utils/decision-engine.py (the CLI bridge Command Center calls).
This module only wires the EXISTING ladder (decision_engine/ladder), providers
and credential resolver to the bridge's two live questions (intent, department):

    1. the box's own Jev key (TYPESAFE_API_KEY / JEV_API_KEY / JEV_TYPESAFE_API_KEY)
    2. else the box's OpenRouter key (the Jev model through OpenRouter)
    3. else (or on ANY error, timeout, bad or low-confidence answer) decide()
       returns None and the caller keeps the local lexical engine exactly as is.

Spending rule: allow spend and transmit for the Jev decision purpose with NO
budget limit (owner decision: Jev costs about 4 cents per million tokens). No
budget store, no reserve hook, no cap.

Latency: Command Center kills the bridge at a 3 s root deadline (live.ts
stampRootDeadline(3000)). The whole Jev attempt is bounded to DEADLINE_MS inside
a worker thread, so a hung socket can never push the bridge past that.

Never raises. Never logs or returns key material (key NAMES only).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

COMPANY = "box"  # a bridge runs on exactly one company's box
CONTEXT = {"single_company_installation": True}

# Whole Jev attempt (own key, then OpenRouter) must finish well inside CC's 3 s,
# leaving room for python start-up, pack validation and the local engine.
DEADLINE_MS = 2200
PROVIDER_TIMEOUT_MS = 1200  # direct gets at most this; OpenRouter gets what is left
SETTLEMENT_RESERVE_MS = 100
MIN_TOP_PROB = 0.6  # same bar the direct transport uses for low confidence
GENERAL = "general-task"
_MAX_TASK_CHARS = 1200
_MAX_DEPTS = 80

INTENTS = (
    "answer_only", "task_request", "mixed_answer_and_task", "existing_task_control",
    "clarification_response", "social_conversation", "unresolved",
)
Q_INTENT, Q_DEPT = "q_intent", "q_department"

PATH_OWN, PATH_OR, PATH_LOCAL = "own-key", "openrouter", "local-only"


def _parse_env_file(path):
    out = {}
    try:
        for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[7:].strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    except OSError:
        pass
    return out


def _json_env_vars(path):
    try:
        vars_ = json.loads(Path(path).read_text(encoding="utf-8")).get("env", {}).get("vars", {})
        return vars_ if isinstance(vars_, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def collect_keys(root, cr):
    """{name: value} for the closed Jev/OpenRouter key-name set only, from this box's
    own stores (process env, <root>/secrets/.env, <root>/.env, openclaw.json env.vars).
    The first USABLE value per name wins, so a placeholder in one store never hides
    a real key in the next. Values stay in this dict; nothing prints them."""
    root = Path(root)
    stores = (dict(os.environ), _parse_env_file(root / "secrets" / ".env"),
              _parse_env_file(root / ".env"), _json_env_vars(root / "openclaw.json"))
    keys = {}
    for name in cr.DIRECT_KEYS + cr.OPENROUTER_KEYS:
        for store in stores:
            value = store.get(name)
            if isinstance(value, str) and cr._classify_value(value) is None:
                keys[name] = value.strip()
                break
    return keys


def _modules():
    from decision_engine.ladder import ladder as lad
    return lad, lad._load_providers()


def would_use_path(root):
    """Which path this box would use, from key-name PRESENCE only (never values).
    Read-only; sends nothing. Raises on a broken install so the health check can say
    UNDETERMINED instead of a false "local-only". For scripts/health/routing-check.sh."""
    _, (_, _, cr) = _modules()
    status = cr.resolve_company_credentials(
        COMPANY, [{"source_category": "box_env", "company_id": None,
                   "values": collect_keys(root, cr)}], CONTEXT)
    if status["direct"].configured:
        return PATH_OWN
    return PATH_OR if status["openrouter"].configured else PATH_LOCAL


def _allow(provider, purpose="decide"):
    return {"spend_ok": True, "transmit_ok": True, "reason": "jev-unlimited"}


def _questions(task, slugs, labels):
    state = {"message": " ".join(str(task).split())[:_MAX_TASK_CHARS]}
    qs = [{"id": Q_INTENT, "type": "select", "candidates": list(INTENTS),
           "prompt": "Classify what the owner's message is: a question to answer, a task to do, "
                     "both, control of an existing task, a reply to a clarification, "
                     "social chatter, or unresolved."}]
    if slugs:
        cands = list(slugs[:_MAX_DEPTS]) + [GENERAL]
        state["departments"] = {s: labels.get(s, "")[:120] for s in cands[:-1]}
        qs.append({"id": Q_DEPT, "type": "select", "candidates": cands,
                   "prompt": "Which department owns this task? %s if none fits." % GENERAL})
    return state, qs


def _pick(payload, qid, cands):
    """(answer, top_prob) for one question, or None when absent/invalid."""
    for j in (payload or {}).get("judgments") or []:
        if isinstance(j, dict) and j.get("question_id") == qid:
            ans, probs = j.get("answer"), j.get("probabilities")
            if ans in cands and isinstance(probs, dict) and isinstance(probs.get(ans), (int, float)):
                return ans, float(probs[ans])
    return None


def _run(task, entries, mode, root, direct_http, openrouter_transport, out):
    lad, (ts, oro, cr) = _modules()
    labels = {e["slug"]: " ".join(str(e.get("text") or "").split()) for e in entries}
    slugs = [e["slug"] for e in entries]
    state, qs = _questions(task, slugs, labels)
    keys = collect_keys(root, cr)
    captured = {}

    def direct_call(**kw):
        r = lad._default_direct_call(**kw)
        if r.get("outcome") == "ok":
            captured["payload"] = r.get("payload")
        return r

    def openrouter_call(**kw):
        r = lad._default_openrouter_call(**kw)
        if r.get("outcome") == "ok":
            captured["payload"] = r.get("payload")
        return r

    specs = {q["id"]: {"type": "select", "candidates": q["candidates"]} for q in qs}
    expected = []
    for q in qs:
        expected.append({"question_id": q["id"], "answer": "choice", "choices": q["candidates"]})
        expected.append({"question_id": q["id"], "answer": "distribution",
                         "candidates": q["candidates"]})
    ladder = lad.DirectFirstLadder(
        policy_fn=_allow, direct_call=direct_call, openrouter_call=openrouter_call,
        root_budget_ms=DEADLINE_MS, stage_budget_ms=DEADLINE_MS,
        provider_timeout_ms=PROVIDER_TIMEOUT_MS, settlement_reserve_ms=SETTLEMENT_RESERVE_MS)
    verdict = ladder.run(
        company_id=COMPANY, stores=[{"source_category": "box_env", "company_id": None,
                                     "values": keys}],
        context=CONTEXT, state=state, questions=qs, keys=keys, direct_specs=specs,
        openrouter_expected=expected, config={"configuredMode": mode},
        direct_http=direct_http, openrouter_transport=openrouter_transport)
    source = verdict.get("decision_source")
    path = {lad.PROVIDER_DIRECT: PATH_OWN, lad.PROVIDER_OPENROUTER: PATH_OR}.get(source)
    if path is None:
        out["reason"] = "no_jev_route"
        return
    intent = _pick(captured.get("payload"), Q_INTENT, INTENTS)
    dept = _pick(captured.get("payload"), Q_DEPT, slugs + [GENERAL]) if slugs else None
    if intent is None or (slugs and dept is None):
        out["reason"] = "invalid_answer"
        return
    if intent[1] < MIN_TOP_PROB or (dept is not None and dept[1] < MIN_TOP_PROB):
        out["reason"] = "low_confidence"
        return
    out.update(ok=True, path=path, intent=intent[0],
               department=dept[0] if dept else None, confidence=dept[1] if dept else intent[1])


def decide(task, entries, mode, root, *, direct_http=None, openrouter_transport=None,
           deadline_ms=DEADLINE_MS):
    """Jev's placement of `task`. Always returns a dict; use it only when ["ok"] is True.

    entries: the department catalog the bridge already built ([{slug, text}]).
    ok result: {"ok": True, "path": "own-key"|"openrouter", "intent", "department",
    "confidence"}. Otherwise {"ok": False, "reason": ...} and the caller keeps the local
    engine. legacy/off/shadow send nothing (the ladder obeys the mode authority).
    Never raises."""
    out = {"ok": False, "reason": "error"}
    try:
        from decision_engine import modes as _modes
        if not _modes.jev_traffic_permitted(mode):
            return {"ok": False, "reason": "mode_" + str(mode)}
        result = {}
        worker = threading.Thread(
            target=_safe, args=(_run, task, entries, mode, root, direct_http,
                                openrouter_transport, result), daemon=True)
        worker.start()
        worker.join(deadline_ms / 1000.0)
        if worker.is_alive():
            return {"ok": False, "reason": "deadline"}  # a late answer is never read
        out = result if result.get("ok") else {"ok": False, "reason": result.get("reason", "error")}
    except Exception:  # noqa: BLE001
        pass
    return out


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:  # noqa: BLE001 -- a Jev hiccup must never break routing
        pass
