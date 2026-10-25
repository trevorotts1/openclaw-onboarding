#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dispatch_launch_entry.py - the canonical entry must EXECUTE when the
approved adapter configuration rides in launch-request.json (finding 9), and a
lone-directory install must still EMIT without Skill 71 (finding 12).

Real subprocesses, temp dirs, stub/fake consumers only: no network, no paid
provider, no Skill 71 execution. Run from scripts/: python3 test_dispatch_launch_entry.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CLIENT, WORKER = "client-1", "worker-9"
sys.path.insert(0, str(HERE))
import dispatch_launch as dl  # noqa: E402
from test_page_set import approved_launch  # noqa: E402

# A stand-in consumer that echoes the request exactly (valid L0 page-result).
CONSUMER = """\
import json, sys
req = json.load(open(sys.argv[1]))
res = {'schema_version': '1.0', 'tenant_id': req['tenant_id'],
       'location_id': req['location_id'], 'launch_id': req['launch_id'],
       'revision': req['revision'], 'request_id': req['request_id'],
       'input_hash': req['input_hash'], 'page_id': req['page_id'],
       'status': 'authored', 'artifacts': [], 'author_session': 'entry-test',
       'reviewer_session': None, 'independent_review': False,
       'proof_class': 'L0', 'blockers': [], 'native_bindings_ref': None,
       'test_only': req['test_only']}
json.dump(res, open(sys.argv[2], 'w'))
"""


def make_run_dir(td: Path, *, adapters: bool, parallel="auto") -> Path:
    """A launch run dir exactly as the documented launch mode expects it."""
    launch, approval = approved_launch()
    rd = td / "run"
    rd.mkdir()
    (rd / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
    (rd / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
    consumer = td / "consumer.py"
    consumer.write_text(CONSUMER, encoding="utf-8")
    request = {"mode": "signature_launch", "client_identity_ref": CLIENT,
               "worker_identity_ref": WORKER, "parallel": parallel}
    if adapters:
        request["adapters"] = {
            role: {"command": [sys.executable, str(consumer),
                               "{request}", "{result}"]}
            for role in dl.PAGE_ROLES}
    (rd / "launch-request.json").write_text(json.dumps(request), encoding="utf-8")
    return rd


def lone_install(td: Path) -> Path:
    """Skill 49 copied alone into a skills root: no 71-blackceo-signature-page sibling."""
    dst = td / "skills" / "49-signature-funnel"
    dst.mkdir(parents=True)
    for name in ("signature-funnel-entry.sh", "SKILL.md", "skill-version.txt"):
        shutil.copy2(SKILL / name, dst / name)
    shutil.copytree(SKILL / "structure", dst / "structure")
    shutil.copytree(
        SKILL / "scripts", dst / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "fixtures", "vendor",
                                      "working", "test_*.py"))
    return dst


def run(cmd) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


class TheEntryExecutesApprovedAdapters(unittest.TestCase):
    def test_entry_launch_mode_executes_instead_of_only_emitting(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            rd = make_run_dir(tdp, adapters=True)
            p = run(["bash", str(SKILL / "signature-funnel-entry.sh"),
                     "--mode", "signature_launch", "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertEqual(p.returncode, 0, out)
            manifest = json.loads(
                (rd / "dispatch" / "dispatch-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"], "executed", out)
            self.assertEqual(len(manifest["results"]), len(dl.PAGE_ROLES), out)


class ALoneInstallStillEmits(unittest.TestCase):
    def test_emission_only_needs_no_skill_71_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            skill = lone_install(tdp)
            rd = make_run_dir(tdp, adapters=False)
            p = run([sys.executable, str(skill / "scripts" / "dispatch_launch.py"),
                     "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertNotIn("ModuleNotFoundError", out)
            self.assertEqual(p.returncode, 0, out)
            manifest = json.loads(
                (rd / "dispatch" / "dispatch-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"], "emitted_not_executed", out)

    def test_execution_preflight_names_the_missing_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            skill = lone_install(tdp)
            rd = make_run_dir(tdp, adapters=True)
            p = run([sys.executable, str(skill / "scripts" / "dispatch_launch.py"),
                     "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertEqual(p.returncode, dl.EXIT_VIOLATION, out)
            self.assertIn("71-blackceo-signature-page", out)
            self.assertIn("swarm_runner.py", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
