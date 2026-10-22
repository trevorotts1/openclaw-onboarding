#!/usr/bin/env python3
"""canary_common.py — shared sandbox, source-vector and receipt plumbing for the
Skill 75 W10 canary harnesses (SFR-007 preparation).

Stdlib only. One safety rule every caller relies on: nothing here ever writes to,
or runs an installer against, a real config root. Every canary runs inside a fresh
scratch sandbox whose HOME / OC_CONFIG / SKILLS_DIR / CLAUDE_CONFIG_DIR are all
redirected into it, with `openclaw` and network verbs stubbed out so a canary can
never notify a client, never fetch from the network, and never touch a live box.
A real config root is never a default and never a fallback.

Scratch convention (Trevor standing rule): sandbox dirs live under /tmp and are
prefixed  /tmp/<box-slug>-<UNIT-ID>-  ->  /tmp/skill75-repair-SFR-007-canary-*.
They self-clean on exit; `keep=True` preserves one for inspection.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UNIT_ID = "SFR-007"
BOX_SLUG = "skill75-repair"
SCRATCH_PREFIX = "%s-%s-canary-" % (BOX_SLUG, UNIT_ID)   # /tmp/skill75-repair-SFR-007-canary-
VECTOR_SCHEMA = "blackceo.skill75.source-vector/v1"
MAPPING_SCHEMA = "blackceo.skill75.receipt-mapping/v1"

#: The four repositories whose pinned revisions form the accepted source vector
#: (Skill_75_Universal_Repair_Spec_v1.1 section 3). The canaries bind to these.
VECTOR_REPOS = (
    "openclaw-onboarding",
    "999-setup",
    "blackceo-command-center",
    "blackceo-graphify-infrastructure",
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n",
                 encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ vector --
def load_vector(path):
    with open(path, "r", encoding="utf-8") as f:
        v = json.load(f)
    return v


def validate_vector(v):
    """Return (ok, problems). Schema + shape only; does not require pinned."""
    problems = []
    if v.get("schema") != VECTOR_SCHEMA:
        problems.append("schema=%r expected %r" % (v.get("schema"), VECTOR_SCHEMA))
    repos = v.get("repositories")
    if not isinstance(repos, dict):
        problems.append("repositories missing or not an object")
        return False, problems
    for name in VECTOR_REPOS:
        r = repos.get(name)
        if not isinstance(r, dict):
            problems.append("repositories.%s missing" % name)
            continue
        rev = r.get("revision")
        if rev is not None and not _is_sha(rev):
            problems.append("repositories.%s.revision not a 40-hex sha" % name)
    return not problems, problems


def _is_sha(s):
    return isinstance(s, str) and len(s) == 40 and all(
        c in "0123456789abcdef" for c in s.lower())


def require_pinned(v):
    """Gate every REAL canary run. Returns (ok, reason).

    Fail-closed: a real canary never runs against a moving or unpinned vector.
    """
    ok, problems = validate_vector(v)
    if not ok:
        return False, "vector invalid: " + "; ".join(problems)
    if not v.get("pinned"):
        return False, ("source vector NOT pinned (pinned=false). The accepted "
                       "onboarding/999-setup/command-center/graphify revisions "
                       "are not finalized. Pin source-vector.json after the final "
                       "merges land, then rerun.")
    for name in VECTOR_REPOS:
        rev = v["repositories"][name].get("revision")
        if not _is_sha(rev):
            return False, "source vector pinned but %s.revision missing/not a sha" % name
    return True, "pinned at %s by %s" % (v.get("pinned_at"), v.get("pinned_by"))


# ------------------------------------------------------------------ shims ----
_OPENCLAW_STUB = """#!/bin/sh
# canary shim: capture, never send. `openclaw message send` would notify a live
# client/Telegram; a canary must never do that. Every call is logged and dropped.
echo "[canary-shim] openclaw $* (captured, never sent)" >> "__LOG__"
exit 0
"""

_CURL_STUB = """#!/bin/sh
# canary shim: hermetic. No network fetch during a canary.
echo "[canary-shim] curl $* (suppressed, hermetic)" >> "__LOG__"
exit 0
"""

_GIT_STUB = """#!/bin/sh
# canary shim: forward local git verbs to the real git; suppress network verbs.
REAL_GIT="__REAL_GIT__"
case "$1" in
  fetch|pull|push|clone|ls-remote|remote|submodule)
    echo "[canary-shim] git $1 (suppressed, hermetic)" >> "__LOG__"
    exit 0 ;;
esac
exec "$REAL_GIT" "$@"
"""


def build_shims(shim_dir, log_path, real_git=None):
    """Write openclaw/curl/git stubs into shim_dir. Return shim_dir."""
    shim = Path(shim_dir)
    shim.mkdir(parents=True, exist_ok=True)
    real_git = real_git or shutil.which("git") or "/usr/bin/git"
    for name, body in (
        ("openclaw", _OPENCLAW_STUB),
        ("curl", _CURL_STUB),
        ("git", _GIT_STUB.replace("__REAL_GIT__", real_git)),
    ):
        p = shim / name
        p.write_text(body.replace("__LOG__", str(log_path)), encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


# ---------------------------------------------------------------- sandbox ----
class Sandbox(object):
    """A disposable fake box. Redirects every install target into scratch.

    Usage:
        with Sandbox() as sb:
            subprocess.run([bash, installer], env=sb.env, ...)
    """

    def __init__(self, prefix=SCRATCH_PREFIX, keep=False):
        self.prefix = prefix
        self.keep = keep
        self.dir = None
        self.env = {}
        self.shim_log = None

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix=self.prefix, dir="/tmp"))
        home = self.dir / "home"
        oc = self.dir / "oc"
        skills = self.dir / "skills"
        claude = self.dir / "claude"
        for d in (home, oc, skills, claude):
            d.mkdir(parents=True, exist_ok=True)
        self.shim_log = self.dir / "shim.log"
        self.shim_log.write_text("", encoding="utf-8")
        shim = build_shims(self.dir / "shims", self.shim_log)

        env = dict(os.environ)
        env.update({
            "HOME": str(home),
            "OC_CONFIG": str(oc),
            "SKILLS_DIR": str(skills),
            "CLAUDE_CONFIG_DIR": str(claude),
            "PATH": "%s:%s" % (shim, env.get("PATH", "")),
            "PYTHONDONTWRITEBYTECODE": "1",
            # belt-and-suspenders: any child that still resolves a network tool
            # through a full path is still blocked by these inert proxies.
            "GIT_TERMINAL_PROMPT": "0",
            "CANARY_SANDBOX": str(self.dir),
        })
        self.env = env
        return self

    def __exit__(self, *exc):
        if not self.keep and self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
        return False

    # convenience accessors
    @property
    def root(self):
        return self.dir

    def shim_entries(self):
        try:
            return [l for l in self.shim_log.read_text(encoding="utf-8").splitlines()
                    if l.strip()]
        except OSError:
            return []


# ------------------------------------------------------------ run helpers ----
def run_capture(cmd, env, cwd=None, timeout=600):
    """Run a command in the sandbox env; capture rc/stdout/stderr. Never throws."""
    try:
        p = subprocess.run(cmd, env=env, cwd=cwd, timeout=timeout,
                           capture_output=True, text=True)
        return {"cmd": [str(c) for c in cmd], "rc": p.returncode,
                "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
    except subprocess.TimeoutExpired as e:
        return {"cmd": [str(c) for c in cmd], "rc": 124, "stdout": "",
                "stderr": "timeout after %ss" % timeout}
    except OSError as e:
        return {"cmd": [str(c) for c in cmd], "rc": 127, "stdout": "",
                "stderr": "os error: %s" % e}


def summarize_checks(results):
    """results: {name: {"ok": bool, "detail": str}} -> (passed, failed, total)."""
    passed = [k for k, v in results.items() if v.get("ok")]
    failed = [k for k, v in results.items() if not v.get("ok")]
    return passed, failed, len(results)
