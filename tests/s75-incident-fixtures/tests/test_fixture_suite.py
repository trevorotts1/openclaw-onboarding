#!/usr/bin/env python3
"""Fixture suite tests (unit S75-W01-U2).

Two obligations, both asserted here:
  1. Every fixture REPRODUCES its documented failure pattern against the real
     product source named in the fixture (paths injected via environment:
     S75_CORE_999, S75_PENDING_HEAD, S75_TIMER_DIR, S75_TMP).
  2. The fixture suite is anonymous: synthetic identities only, and no
     privacy-class strings anywhere in the suite's own artifacts.

Run: python3 -B tests/test_fixture_suite.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXDIR = os.path.join(ROOT, "fixtures")
sys.path.insert(0, os.path.join(ROOT, "harness"))
import run_suite  # noqa: E402

ENV_PATHS = ("S75_CORE_999", "S75_PENDING_HEAD", "S75_TIMER_DIR", "S75_TMP")

PRIVACY_PATTERNS = {
    # Patterns are built from fragments so this detector never matches itself.
    "home_directory": re.compile("(/Use" + "rs/|/ho" + "me/|/Vol" + "umes/|C:\\\\Use" + "rs\\\\|~\\/[A-Za-z])"),
    "ssh_alias": re.compile(r"\brescue-[a-z]+(?:-[a-z]+)+\b|\b[a-z]{2,}-mac\b"),
    "chat_id": re.compile(r"-100\d{6,}|\b\d{7,}\b"),
    "access_bearing_url": re.compile(
        r"https?://[^\s\"']*([?&](access_token|api_key|apikey|token|secret|password|sig|signature|credential)=|://[^/\s\"']+:[^@\s\"']+@)",
        re.I),
    "run_or_host_identity": re.compile(r"\brun-20\d{6}[-\d]*\b|\bhost:[0-9]+:[0-9]+\b"),
    "one_off_override": re.compile(
        r"\b[A-Z0-9_]*(OVERRIDE|BYPASS|EXEMPT)[A-Z0-9_]*\s*[:=]\s*[\"']?(?!<|synthetic|none)[A-Za-z0-9_./-]+"),
}


def _paths():
    missing = [k for k in ENV_PATHS if not os.environ.get(k)]
    if missing:
        raise unittest.SkipTest("injected runtime paths not set: %s" % missing)
    return run_suite.argparse.Namespace(
        core_999=os.environ["S75_CORE_999"],
        pending_head=os.environ["S75_PENDING_HEAD"],
        timer_dir=os.environ["S75_TIMER_DIR"],
        tmp=os.environ["S75_TMP"])


def _fixtures():
    return [f[:-5] for f in sorted(os.listdir(FIXDIR)) if f.endswith(".json")]


class TestReproduction(unittest.TestCase):
    """Each named failure pattern reproduces through its product driver."""

    def test_each_named_pattern_reproduces(self):
        args = _paths()
        failures = []
        for fid in _fixtures():
            with open(os.path.join(FIXDIR, fid + ".json")) as _f:
                fx = json.load(_f)
            res = run_suite.run_one(args, fid)
            if res.get("status") != "ran":
                failures.append("%s: driver-error %s" % (fid, res.get("error")))
                continue
            ok, problems = run_suite.compare(fid, fx["observed_defect"], res["observed"])
            if not ok:
                failures.append("%s: %s" % (fid, "; ".join(problems)))
        self.assertEqual([], failures, "patterns not reproduced:\n" + "\n".join(failures))


class TestAnonymity(unittest.TestCase):
    """Fixtures and suite artifacts depend on no real identity."""

    def test_fixture_identities_are_synthetic(self):
        for fid in _fixtures():
            with open(os.path.join(FIXDIR, fid + ".json")) as _f:
                fx = json.load(_f)
            for k, v in (fx.get("identities") or {}).items():
                self.assertRegex(str(v), r"^[a-z]+-synth-[0-9a-z]+$",
                                 "%s: identity %s not synthetic" % (fid, k))
            for k, v in (fx.get("injected_paths") or {}).items():
                self.assertRegex(str(v), r"^<[^>]+>|^<RUN_DIR>",
                                 "%s: path %s not an injected placeholder" % (fid, k))

    def test_no_fixture_depends_on_real_run_host_chat(self):
        for fid in _fixtures():
            with open(os.path.join(FIXDIR, fid + ".json")) as _f:
                blob = _f.read()
            for cls, rx in PRIVACY_PATTERNS.items():
                self.assertIsNone(rx.search(blob), "%s: %s in fixture" % (fid, cls))

    def test_suite_artifacts_pass_privacy_patterns(self):
        scanned = []
        for dirpath, _dirs, files in os.walk(ROOT):
            if os.sep + ".git" in dirpath:
                continue
            for fn in files:
                p = os.path.join(dirpath, fn)
                if fn.endswith((".py", ".json", ".md", ".txt")):
                    scanned.append(p)
        hits = []
        for p in scanned:
            with open(p, encoding="utf-8", errors="replace") as _f:
                    blob = _f.read()
            for cls, rx in PRIVACY_PATTERNS.items():
                if rx.search(blob):
                    hits.append("%s: %s" % (os.path.relpath(p, ROOT), cls))
        self.assertEqual([], hits, "privacy-class strings in suite artifacts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
