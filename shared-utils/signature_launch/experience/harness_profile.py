#!/usr/bin/env python3
"""Which harness is the client in, and so which shapes do we use?

Order: explicit --harness flag, then the answers file, then environment
signals, then `plain`. It never guesses a skills path: skills_root is only
what the caller passed. Pure stdlib, no network, no credentials read.
"""
import argparse
import json
import os

PROFILES = {
    "claude-code": {"question_shape": "structured", "progress_shape": "table"},
    "claude-nine": {"question_shape": "structured", "progress_shape": "table"},
    "openclaw": {"question_shape": "chat", "progress_shape": "messages"},
    "plain": {"question_shape": "chat", "progress_shape": "messages"},
}
ALIASES = {"claude_code": "claude-code", "claude": "claude-code",
           "claude_nine": "claude-nine", "nine": "claude-nine"}


def _name(value):
    """A recognised harness name, or None."""
    v = str(value or "").strip().lower()
    v = ALIASES.get(v, v)
    return v if v in PROFILES else None


def _env_signal(env):
    """(harness, 'env:VAR') from ambient signals the existing 51/71 adapters use."""
    n = _name(env.get("SKILL71_RUNTIME"))
    if n:
        return n, "env:SKILL71_RUNTIME"
    if env.get("OPENCLAW_SESSION_ID"):
        return "openclaw", "env:OPENCLAW_SESSION_ID"
    if "claude-nine" in str(env.get("CLAUDE_CONFIG_DIR", "")):
        return "claude-nine", "env:CLAUDE_CONFIG_DIR"
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE"):
        if env.get(var):
            return "claude-code", "env:" + var
    return None, None


def detect(flag=None, answers=None, env=None, skills_root=None):
    env = os.environ if env is None else env
    name, source = None, None
    if flag:
        name = _name(flag)
        source = "flag" if name else "flag:unrecognised"
    if name is None and not flag:
        for key in ("harness", "runtime"):
            name = _name((answers or {}).get(key))
            if name:
                source = "answers:" + key
                break
    if name is None and not flag:
        name, source = _env_signal(env)
    if name is None:
        name, source = "plain", source or "default"
    return {"harness": name, "source": source, "skills_root": skills_root,
            **PROFILES[name]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harness")
    ap.add_argument("--answers-file")
    ap.add_argument("--skills-root")
    a = ap.parse_args(argv)
    answers = None
    if a.answers_file:
        with open(a.answers_file, encoding="utf-8") as fh:
            answers = json.load(fh)
    print(json.dumps(detect(a.harness, answers, skills_root=a.skills_root), indent=2))


if __name__ == "__main__":
    main()
