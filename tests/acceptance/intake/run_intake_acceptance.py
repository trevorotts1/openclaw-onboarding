#!/usr/bin/env python3
"""Intake acceptance harness: does the CEO model make exactly one card per job?

Sends every corpus message (with its prior turns) straight to an OpenAI-compatible
chat-completions endpoint, with the live intake rule from
shared-utils/ceo_execution_policy.py as system context and one `exec` tool. Tool
calls are NEVER executed: `mc-route.sh` calls get a canned ROUTED line, anything
else gets "sandbox: command not executed". Nothing is sent to Telegram, Command
Center or any client; the only network peer is the model endpoint you configure.

Scores per run: dropped tasks (task with no card), double cards (more cards than
jobs), extra cards (card for a question/small talk/existing task). Pass mark (review
JGT-401 section 4) on the chosen split, every run: 0 dropped, 0 double, extra <= 3%,
0 errors. Stdlib only. See README.md for endpoint setup.
"""
import argparse
import importlib.util
import json
import os
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_PY = HERE.parents[2] / "shared-utils" / "ceo_execution_policy.py"
SPLITS = {"frozen": ["corpus_frozen.json"], "train": ["corpus_train.json"],
          "all": ["corpus_train.json", "corpus_frozen.json"]}
TASK_MARK = "mc-route.sh task"
MAX_EXTRA_RATE = 0.03
MAX_ROUNDS = 4
NOT_CARD_MODES = {"", "-h", "--help", "help"}
ROUTED = "ROUTED workspace=general-task department=general-task resolved_by=harness-sandbox"
PERSONA = ("You are the CEO AI assistant of a small business, chatting with the owner. "
           "You have one tool, `exec`, which runs a shell command on the business server; "
           "`mc-route.sh` is on PATH. Follow the policy below exactly.\n\n")
EXEC_TOOL = {"type": "function", "function": {
    "name": "exec", "description": "Run a shell command on the business server.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                   "required": ["command"]}}}


def load_policy(path=POLICY_PY):
    spec = importlib.util.spec_from_file_location("_ceo_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.POLICY


def load_items(split):
    items = []
    for name in SPLITS[split]:
        items += json.loads((HERE / name).read_text())["items"]
    return items


def parse_cards(command):
    """Return one (mode, args) per mc-route.sh invocation in a shell command."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:  # unbalanced quotes: count invocations, args unknown
        return [("unparsed", [])] * command.count("mc-route.sh")
    out, i = [], 0
    while i < len(toks):
        if os.path.basename(toks[i]) == "mc-route.sh":
            j = i + 1
            while j < len(toks) and not set(toks[j]) <= set(";&|()"):
                j += 1
            args = toks[i + 1:j]
            mode = args[0] if args else ""
            if mode not in NOT_CARD_MODES:
                out.append((mode, args[1:]))
            i = j
        elif "mc-route.sh" in toks[i]:  # e.g. bash -c "mc-route.sh task ..."
            out += parse_cards(toks[i])
            i += 1
        else:
            i += 1
    return out


def check_endpoint(ep):
    u = urllib.parse.urlparse(ep["base_url"])
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError(f"{ep['name']}: base_url must be http(s)://host/...")
    if "telegram" in u.netloc.lower():
        raise ValueError(f"{ep['name']}: refusing a Telegram host; model APIs only")


def post_json(ep, payload, timeout=120):
    check_endpoint(ep)
    req = urllib.request.Request(ep["base_url"].rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    key = os.environ.get(ep.get("api_key_env") or "", "")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run_item(ep, system, item, post=post_json, retries=2):
    """Drive one conversation to the model's final reply. Returns cards made + error."""
    msgs = [{"role": "system", "content": system}] + list(item["history"]) + \
           [{"role": "user", "content": item["message"]}]
    cards = []
    for _ in range(MAX_ROUNDS):
        payload = {"model": ep["model"], "messages": msgs, "tools": [EXEC_TOOL]}
        for attempt in range(retries + 1):
            try:
                resp = post(ep, payload)
                msg = resp["choices"][0]["message"]
                if not isinstance(msg, dict):
                    raise TypeError("response has no message object")
                break
            except (urllib.error.URLError, OSError, KeyError, IndexError, TypeError,
                    ValueError) as e:
                if attempt == retries:
                    return {"cards": cards, "error": f"{type(e).__name__}: {e}"[:300]}
                time.sleep(2 * (attempt + 1))
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"cards": cards, "error": None}
        msgs.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for c in calls:
            try:
                cmd = json.loads(c["function"]["arguments"] or "{}").get("command", "")
            except (ValueError, AttributeError, KeyError, TypeError):
                cmd = ""
            made = parse_cards(cmd) if isinstance(cmd, str) else []
            cards += [{"mode": m, "args": a} for m, a in made]
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""),
                         "content": "\n".join([ROUTED] * len(made)) or
                         "sandbox: command not executed"})
    return {"cards": cards, "error": None}


def score(items, results):
    """results: {item_id: {"cards": [...], "error": str|None}} -> metrics + pass flag."""
    s = {"items": len(items), "tasks": 0, "non_tasks": 0, "dropped": [], "double": [],
         "extra": [], "under_carded": [], "errors": [], "auto_mode_calls": 0,
         "disagreement_failures": []}
    for it in items:
        r = results.get(it["id"]) or {"cards": [], "error": "missing result"}
        n = len(r["cards"])
        s["auto_mode_calls"] += sum(c["mode"] == "auto" for c in r["cards"])
        bad = None
        if r["error"]:
            s["errors"].append(it["id"])
            bad = "error"
        elif it["expected"] == "task":
            if n == 0:
                bad = "dropped"
            elif n > it["jobs"]:
                bad = "double"
            elif n < it["jobs"]:
                s["under_carded"].append(it["id"])
        elif n and "task" not in it.get("acceptable", []):
            bad = "extra"
        if it["expected"] == "task":
            s["tasks"] += 1
        else:
            s["non_tasks"] += 1
        if bad and bad != "error":
            s[bad].append(it["id"])
        if bad and it.get("disagree"):
            s["disagreement_failures"].append(it["id"])
    s["extra_rate"] = round(len(s["extra"]) / s["non_tasks"], 4) if s["non_tasks"] else 0.0
    s["pass"] = (not s["errors"] and not s["dropped"] and not s["double"]
                 and s["extra_rate"] <= MAX_EXTRA_RATE)
    return s


def load_endpoints(config):
    if config:
        eps = json.loads(Path(config).read_text())["endpoints"]
    elif os.environ.get("INTAKE_ACCEPT_BASE_URL") and os.environ.get("INTAKE_ACCEPT_MODEL"):
        eps = [{"name": os.environ.get("INTAKE_ACCEPT_NAME", "env"),
                "base_url": os.environ["INTAKE_ACCEPT_BASE_URL"],
                "model": os.environ["INTAKE_ACCEPT_MODEL"],
                "api_key_env": os.environ.get("INTAKE_ACCEPT_API_KEY_ENV", "INTAKE_ACCEPT_API_KEY")}]
    else:
        raise ValueError("no endpoints: pass --config FILE or set INTAKE_ACCEPT_BASE_URL "
                         "and INTAKE_ACCEPT_MODEL")
    for ep in eps:
        for k in ("name", "base_url", "model"):
            if not ep.get(k):
                raise ValueError(f"endpoint missing {k!r}: {ep.get('name')}")
        check_endpoint(ep)
    return eps


def main(argv=None, post=post_json):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--config", help="JSON file: {\"endpoints\": [{name, base_url, model, api_key_env}]}")
    p.add_argument("--split", choices=sorted(SPLITS), default="frozen")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--limit", type=int, help="first N items only (smoke test; never a pass)")
    p.add_argument("--policy-file", default=str(POLICY_PY))
    p.add_argument("--allow-legacy-policy", action="store_true",
                   help=f"run even if the rule text lacks '{TASK_MARK}'")
    p.add_argument("--out", help="write the full JSON report here")
    p.add_argument("--dry-run", action="store_true", help="validate setup; no network calls")
    a = p.parse_args(argv)
    try:
        policy = load_policy(a.policy_file)
        if TASK_MARK not in policy and not a.allow_legacy_policy:
            raise ValueError(f"rule text in {a.policy_file} has no '{TASK_MARK}'; this is not "
                             "the V4 intake rule (use --allow-legacy-policy to score it anyway)")
        eps = load_endpoints(a.config)
        items = load_items(a.split)[:a.limit] if a.limit else load_items(a.split)
    except (ValueError, OSError, KeyError) as e:
        print(f"CONFIG ERROR: {e}", file=sys.stderr)
        return 2
    head = policy.strip().splitlines()[0]
    print(f"rule: {head} | split={a.split} items={len(items)} runs={a.runs}")
    for ep in eps:
        print(f"endpoint {ep['name']}: {ep['base_url']} model={ep['model']} "
              f"key_env={ep.get('api_key_env') or '-'} key_set={bool(os.environ.get(ep.get('api_key_env') or ''))}")
    if a.dry_run:
        return 0
    system = PERSONA + policy
    report, ok = {"rule": head, "split": a.split, "limit": a.limit, "models": {}}, True
    for ep in eps:
        runs = []
        for run in range(1, a.runs + 1):
            results = {it["id"]: run_item(ep, system, it, post=post) for it in items}
            s = score(items, results)
            runs.append({"run": run, "score": s, "results": results})
            print(f"{ep['name']} run {run}: dropped={len(s['dropped'])} double={len(s['double'])} "
                  f"extra={len(s['extra'])}/{s['non_tasks']} ({s['extra_rate']:.1%}) "
                  f"errors={len(s['errors'])} under_carded={len(s['under_carded'])} "
                  f"auto_mode={s['auto_mode_calls']} -> {'PASS' if s['pass'] else 'FAIL'}")
        passed = all(r["score"]["pass"] for r in runs) and len(runs) >= 3 and not a.limit
        ok &= passed
        report["models"][ep["name"]] = {"model": ep["model"], "pass": passed, "runs": runs}
        print(f"{ep['name']}: {'PASS' if passed else 'FAIL'}")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
