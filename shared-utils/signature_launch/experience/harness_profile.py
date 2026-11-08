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
    "claude-code": {"question_shape": "structured", "progress_shape": "table",
                    "question_tool": True},
    "claude-nine": {"question_shape": "structured", "progress_shape": "table",
                    "question_tool": True},
    # Codex drives claude-nine but has NO structured question tool: the guided
    # interview runs as one numbered chat message per question, over the SAME
    # answers file and resume state. It is an explicit profile, not a guess.
    "claude-codex": {"question_shape": "chat", "progress_shape": "messages",
                     "question_tool": False},
    "openclaw": {"question_shape": "chat", "progress_shape": "messages",
                 "question_tool": False},
    "plain": {"question_shape": "chat", "progress_shape": "messages",
              "question_tool": False},
}
ALIASES = {"claude_code": "claude-code", "claude": "claude-code",
           "claude_nine": "claude-nine", "nine": "claude-nine",
           "codex": "claude-codex", "claude_codex": "claude-codex",
           "claude-codex": "claude-codex"}


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
    profile = str(env.get("NINE_PROFILE") or env.get("CLAUDE_PROFILE") or "").strip()
    n = _name(profile)
    if n:
        return n, "env:NINE_PROFILE"
    if "claude-nine" in str(env.get("CLAUDE_CONFIG_DIR", "")):
        return "claude-nine", "env:CLAUDE_CONFIG_DIR"
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE"):
        if env.get(var):
            return "claude-code", "env:" + var
    return None, None


def detect(flag=None, answers=None, env=None, skills_root=None, question_tool=None):
    """The harness profile, with the question tool's real availability applied.

    ``question_tool`` is the CALLER'S observation of whether this session actually
    exposes the structured question tool. When it is False and the profile would
    otherwise be structured, the same guided interview falls back to one numbered
    plain-chat message per question, over the SAME answers file and resume state —
    a capability downgrade, never a second interview.
    """
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
    profile = dict(PROFILES[name])
    tool = profile["question_tool"] if question_tool is None else bool(question_tool)
    if not tool and profile["question_shape"] == "structured":
        profile.update({"question_shape": "chat", "progress_shape": "messages",
                        "fallback": "question tool not available; plain-chat interview"})
    profile["question_tool"] = tool
    return {"harness": name, "source": source, "skills_root": skills_root,
            **profile}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harness")
    ap.add_argument("--answers-file")
    ap.add_argument("--skills-root")
    ap.add_argument("--question-tool", choices=("yes", "no"),
                    help="the caller's observation of whether this session exposes the "
                         "structured question tool; 'no' selects the plain-chat fallback")
    a = ap.parse_args(argv)
    answers = None
    if a.answers_file:
        with open(a.answers_file, encoding="utf-8") as fh:
            answers = json.load(fh)
    tool = None if a.question_tool is None else a.question_tool == "yes"
    print(json.dumps(detect(a.harness, answers, skills_root=a.skills_root,
                            question_tool=tool), indent=2))


if __name__ == "__main__":
    main()
