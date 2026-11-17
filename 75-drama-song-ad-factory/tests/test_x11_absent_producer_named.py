#!/usr/bin/env python3
"""S75-018 (U-GEN308): the gate must SAY it cannot allow.

The six s75-x11 records (target.json, backup-authorization.json,
preservation.json, reviewed-manifest.json, applied-verification.json,
operator-decision.json) are written only by tests/test_x11_release_gate_wiring.py
`records()`. No production writer exists in this tree, so a real install arrives
with an empty records directory and the gate can only warn or refuse.

This test runs the shipped gate against an EMPTY records directory - no fixture
present - in both modes, and requires each output to name the absent production
writer. Before the fix the warn text only promised files are kept, never deleted,
and said nothing about the records having no production writer, so this fails.

Run directly:  python3 -I tests/test_x11_absent_producer_named.py   (also collects as pytest)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
GATE_SH = os.path.join(SKILL_ROOT, "scripts", "core", "x11_install_gate.sh")
PHRASE = "no production writer"


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("S75_X11_")}
    env.update(extra)
    return env


def run_empty(env_extra=None):
    empty = tempfile.mkdtemp(prefix="x11-empty-records-")
    proc = subprocess.run(["bash", GATE_SH], capture_output=True, text=True,
                          env=clean_env(S75_X11_RECORDS_DIR=empty, **(env_extra or {})))
    return proc.returncode, proc.stdout + proc.stderr


def test_warn_mode_names_absent_producer():
    rc, out = run_empty()
    assert rc == 10, "empty records in warn mode must exit 10, got %r: %s" % (rc, out)
    assert PHRASE in out, (
        "warn output must name the absent production writer of the six records; "
        "got: %s" % out)


def test_refuse_mode_names_absent_producer():
    rc, out = run_empty({"S75_X11_GATE_MODE": "refuse"})
    assert rc == 20, "empty records in refuse mode must exit 20, got %r: %s" % (rc, out)
    assert PHRASE in out, (
        "refuse output must name the absent production writer of the six records; "
        "got: %s" % out)


def test_install_md_states_it_cannot_allow():
    text = open(os.path.join(SKILL_ROOT, "INSTALL.md"), encoding="utf-8").read()
    assert PHRASE in text, "INSTALL.md must state the six records have no production writer"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    sys.exit(1 if failures else 0)
