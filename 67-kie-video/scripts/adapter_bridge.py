#!/usr/bin/env python3
"""Skill 67 -> Skill 74 bridge. STDLIB ONLY. Finds the sibling kie_live_adapter.py and runs one subcommand.

The adapter is optional: absent, unreachable, slow or broken -> every function returns None and the caller
falls back to models.json (the curated policy registry). Never raises. Never prints or handles a key (the adapter resolves it itself).
Env: KIE_LIVE_ADAPTER_PATH overrides the adapter location; set it to the empty string to disable the bridge.
"""
import json
import os
import subprocess
import sys

TIMEOUT = 60  # first call may read the live catalog and two schemas (spaced 1.1 s); later calls hit the cache


def find_adapter():
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env is not None:
        return env if env and os.path.isfile(env) else None
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.abspath(os.path.join(here, "..", "..")), os.path.join(os.path.expanduser("~"), ".openclaw", "skills"),
             "/data/.openclaw/skills"]
    for r in roots:
        for name in ("74-kie-live-adapter", "kie-live-adapter"):
            p = os.path.join(r, name, "scripts", "kie_live_adapter.py")
            if os.path.isfile(p):
                return p
    return None


def run(args, stdin=None, timeout=TIMEOUT):
    """-> (returncode, parsed JSON dict) or None when the adapter cannot answer."""
    path = find_adapter()
    if not path:
        return None
    try:
        p = subprocess.run([sys.executable, path] + list(args), input=stdin, capture_output=True, text=True,
                           timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return p.returncode, json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def validate(model, input_obj):
    """Skill 74 `validate` against the live schema (registry fallback) -> result dict or None."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "input.json")
        with open(f, "w") as fh:
            json.dump(input_obj, fh)
        got = run(["validate", "--model", model, "--payload", f, "--json"])
    return got[1] if got else None
