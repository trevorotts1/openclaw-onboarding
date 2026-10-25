"""Regression locks for findings 31 and 32 in qc-ghl-install-pages.sh.

31 — a failed capability probe only warned, and the later assertions read
     whatever working/skill6-capability.json was on disk, so a stale success
     greened a currently broken probe. The QC must require THIS invocation to
     succeed and write the receipt before any assertion consumes it.

32 — the refresh-token gate hard-asserted three process environment variables,
     bypassing the documented resolver (GHL_REFRESH_TOKEN_FILE -> alias chain ->
     canonical stores), so a properly mounted token was rejected. The QC must
     use the resolver-backed `seed-ghl-auth.py --check`.

Each test builds an isolated copy of the skill (with a stub lib-shared.sh so
every path resolves inside the temp box) and runs the REAL QC script, then reads
the verdict of the two named assertions. No network, no real credentials.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
QC = SKILL_DIR / "qc-ghl-install-pages.sh"

GOOD_PROBE = """#!/usr/bin/env python3
import json, os, sys
out = sys.argv[sys.argv.index("--out") + 1]
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"selectedLane": "agent_browser", "blockers": [],
               "iframeDrag": {"available": True}}, fh)
sys.exit(0)
"""

BROKEN_PROBE = """#!/usr/bin/env python3
import sys
sys.exit(1)
"""


def _make_box(tmp_path: Path, probe_body: str):
    box = tmp_path / "box"
    dest = box / "06-ghl-install-pages"
    shutil.copytree(
        SKILL_DIR, dest,
        ignore=shutil.ignore_patterns("tests", "working", "evidence", "examples", "__pycache__"),
    )
    # The QC sources <skill>/../lib-shared.sh; stub it so SKILLS_DIR_DEFAULT,
    # SECRETS_ENV and WORKSPACE all point inside the temp box (no operator env).
    (box / "lib-shared.sh").write_text(
        "resolve_platform_paths() {\n"
        f'  export SECRETS_ENV="{box}/secrets.env"\n'
        f'  export WORKSPACE="{box}/workspace"\n'
        f'  export SKILLS_DIR_DEFAULT="{box}"\n'
        "}\n"
    )
    (box / "workspace").mkdir()
    (box / "home").mkdir()
    (dest / "tools" / "capability_probe.py").write_text(probe_body)
    return box, dest


def _run(box: Path, dest: Path, extra_env=None):
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
                     "CAF_FIREBASE_REFRESH_TOKEN",
                     "GHL_FIREBASE_REFRESH_TOKEN",
                     "GHL_REFRESH_TOKEN_FILE")
    }
    env["HOME"] = str(box / "home")
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(dest / "qc-ghl-install-pages.sh")],
        env=env, capture_output=True, text=True, timeout=600,
    )


def _verdict(stdout: str, label: str) -> str:
    """'PASS' / 'FAIL' / 'WARN' / 'ABSENT' for the assertion carrying `label`."""
    for line in stdout.splitlines():
        if label in line:
            if "✓ PASS" in line:
                return "PASS"
            if "✗ FAIL" in line:
                return "FAIL"
            if "⚠ WARN" in line:
                return "WARN"
    return "ABSENT"


def test_stale_receipt_never_greens_a_broken_probe(tmp_path):
    """Findings 31: broken probe + stale green receipt => the QC must FAIL."""
    box, dest = _make_box(tmp_path, BROKEN_PROBE)
    stale = dest / "working" / "skill6-capability.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(json.dumps(
        {"selectedLane": "agent_browser", "blockers": [],
         "iframeDrag": {"available": True}}
    ))

    proc = _run(box, dest)
    stdout = proc.stdout

    assert _verdict(stdout, "capability probe ran") == "FAIL", (
        "a probe that failed in THIS run must not be reported as a pass/warn\n"
        + stdout[-3000:]
    )
    assert _verdict(stdout, "capability probe selected a browser lane") == "FAIL", (
        "the stale receipt was consumed: a broken probe greened the lane check\n"
        + stdout[-3000:]
    )
    assert proc.returncode != 0, "QC exited 0 with a broken probe"


def test_mounted_token_file_satisfies_the_auth_gate(tmp_path):
    """Findings 32: GHL_REFRESH_TOKEN_FILE is a documented source; honour it."""
    box, dest = _make_box(tmp_path, GOOD_PROBE)
    token = box / "mounted-token"
    token.write_text("1//0gRegressionTokenValueForTheResolverCheck000\n")
    os.chmod(token, 0o600)

    proc = _run(box, dest, {"GHL_REFRESH_TOKEN_FILE": str(token)})
    stdout = proc.stdout

    assert _verdict(stdout, "Firebase refresh token") == "PASS", (
        "a mounted GHL_REFRESH_TOKEN_FILE was rejected although the runtime "
        "resolver accepts it\n" + stdout[-3000:]
    )
