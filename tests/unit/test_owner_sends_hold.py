#!/usr/bin/env python3
"""The owner-sends hold stops every automatic owner message, on every path.

Proves, with a stub `openclaw` that records every send:
  * owner_sends_hold.py: absent -> clear, operator-directive consent -> held,
    explicit true/false, hold/release, unreadable state -> held
  * the Presentations welcome sends nothing while held (--force included), and
    still sends when clear (control: the stub does record sends)
  * verify-library-gate.sh fires the welcome ONLY on a full pass: a failing gate
    (rc 9 with every status "done") fires nothing
  * the Skill 37 celebration sender sends nothing while held
  * run-closeout.sh stops before TELEGRAM, and resume-closeout-cron.sh /
    resume-workforce-build.sh HOP-4 check the hold before launching run-closeout.sh
  * nothing but owner_sends_hold.py ever writes ownerSendsHold (it never auto-clears)
  * end to end: a box whose build tree is now found (the resolver fix) and whose
    gate passes sends NOTHING to the owner while held

Run: python3 tests/unit/test_owner_sends_hold.py
"""
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "shared-utils" / "owner_sends_hold.py"
S23 = ROOT / "23-ai-workforce-blueprint" / "scripts"
S37 = ROOT / "37-zhc-closeout" / "scripts"
WELCOME = S23 / "send-presentation-dept-welcome.sh"
GATE = S23 / "verify-library-gate.sh"
CELEBRATE = S37 / "send-telegram-celebration.sh"


def ready_state(**extra):
    s = {"ownerName": "Pat Owner", "companyName": "Fixture Co", "ownerChat": "111",
         "departments": [{"slug": "presentations", "wiringStatus": "done",
                          "roleLibraryFilled": True, "sopLibraryFilled": True}]}
    s.update(extra)
    return s


class _Box(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.home = Path(self._t.name)
        self.ws = self.home / ".openclaw" / "workspace"
        self.ws.mkdir(parents=True)
        self.state = self.ws / ".workforce-build-state.json"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.sends = self.home / "sends.log"
        stub = self.bin / "openclaw"
        stub.write_text('#!/bin/sh\necho "$*" >> "%s"\necho \'{"messageId":"m1"}\'\n' % self.sends)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}",
                        ZHC_STATE_FILE=str(self.state), ZHC_SKIP_TG_PREFLIGHT="1")

    def tearDown(self):
        self._t.cleanup()

    def write(self, state):
        self.state.write_text(json.dumps(state))

    def sent(self):
        return self.sends.read_text() if self.sends.exists() else ""

    def run_sh(self, *args, **kw):
        return subprocess.run(["bash", *map(str, args)], capture_output=True, text=True,
                              env=self.env, timeout=120, **kw)

    def check(self):
        return subprocess.run([sys.executable, str(HELPER), "check", str(self.state)],
                              capture_output=True, text=True).returncode


class TestHelper(_Box):
    def test_states(self):
        self.write(ready_state())
        self.assertEqual(self.check(), 1, "absent flag, owner consent: clear (unchanged)")
        self.write(ready_state(ownerConsent={"source": "operator-directive"}))
        self.assertEqual(self.check(), 0, "operator-built workforce: held by default")
        self.write(ready_state(ownerConsent={"source": "operator-directive"}, ownerSendsHold=False))
        self.assertEqual(self.check(), 1, "explicit release wins")
        self.write(ready_state(ownerSendsHold=True))
        self.assertEqual(self.check(), 0)
        self.state.write_text("{not json")
        self.assertEqual(self.check(), 0, "unreadable state holds")

    def test_hold_and_release_keep_everything_else(self):
        self.write(ready_state(companySlug="fixture-co"))
        subprocess.run([sys.executable, str(HELPER), "hold", str(self.state), "setup in progress"], check=True)
        self.assertEqual(self.check(), 0)
        subprocess.run([sys.executable, str(HELPER), "release", str(self.state)], check=True)
        s = json.loads(self.state.read_text())
        self.assertIs(s["ownerSendsHold"], False)
        self.assertEqual(s["companySlug"], "fixture-co")
        self.assertEqual(self.check(), 1)


class TestWelcome(_Box):
    def test_held_sends_nothing_even_with_force(self):
        self.write(ready_state(ownerSendsHold=True))
        for extra in ([], ["--force"]):
            r = self.run_sh(WELCOME, *extra)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("HELD", r.stdout)
        self.assertEqual(self.sent(), "")

    def test_clear_still_sends_control(self):
        self.write(ready_state())
        r = self.run_sh(WELCOME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("message send", self.sent())


def _gate_autosend_block():
    src = GATE.read_text()
    a = src.index("# AUTO-SEND: Presentations Department Welcome")
    b = src.index("# ---- exit code = the gate verdict")
    return src[a:b]


class TestGateFiresOnlyOnFullPass(_Box):
    def _run_block(self, gate_rc):
        fake = self.home / "fake-scripts"
        fake.mkdir(exist_ok=True)
        (fake / "send-presentation-dept-welcome.sh").write_text(f'echo fired >> "{self.sends}"\n')
        script = ("GATE_RC=%s; BOUNDARY_STATUS=done; TRIO_STATUS=done; ROLE_STATUS=done; SOP_STATUS=done\n"
                  "SCRIPT_DIR=%s\n%s") % (gate_rc, fake, _gate_autosend_block())
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=self.env)

    def test_failing_gate_fires_nothing(self):
        self._run_block(9)
        self.assertEqual(self.sent(), "", "welcome fired on a FAILED gate (rc 9)")

    def test_passing_gate_fires_control(self):
        self._run_block(0)
        self.assertIn("fired", self.sent())


class TestCloseoutPaths(_Box):
    def test_celebration_sender_sends_nothing_while_held(self):
        self.write(ready_state(ownerSendsHold=True, commandCenterUrl="https://cc.example"))
        r = self.run_sh(CELEBRATE)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.sent(), "", r.stdout + r.stderr)

    def _before(self, path, check_pat, act_pat):
        src = path.read_text()
        c, a = re.search(check_pat, src), re.search(act_pat, src)
        self.assertTrue(c and a, f"{path.name}: pattern missing")
        self.assertLess(c.start(), a.start(), f"{path.name}: hold check must come first")
        return src

    def test_every_launch_path_checks_the_hold_first(self):
        self._before(S37 / "run-closeout.sh", r"if owner_sends_held; then",
                     r'run_step TELEGRAM "\$SKILL_DIR/scripts/send-telegram-celebration.sh"')
        self._before(S37 / "resume-closeout-cron.sh", r"if owner_sends_held; then",
                     r'nohup bash "\$_CLOSEOUT_SCRIPT"')
        self._before(S23 / "resume-workforce-build.sh", r"owner_sends_hold\.py\" check",
                     r'nohup bash "\$_CLOSEOUT_SCRIPT"')

    def test_lib_function_reports_held(self):
        self.write(ready_state(ownerSendsHold=True))
        r = subprocess.run(["bash", "-c", f'STATE_FILE="{self.state}"; source "{S37}/lib-closeout-state.sh"; '
                                          'if owner_sends_held; then echo HELD; else echo CLEAR; fi'],
                           capture_output=True, text=True, env=self.env)
        self.assertIn("HELD", r.stdout, r.stderr)

    def test_nothing_but_the_helper_writes_the_flag(self):
        writers = []
        for p in list(ROOT.rglob("*.sh")) + list(ROOT.rglob("*.py")):
            if p == HELPER or "tests" in p.parts or "archive" in p.parts or "node_modules" in p.parts:
                continue
            try:
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            if re.search(r"ownerSendsHold\s*[=:]|\.ownerSendsHold\s*=", txt):
                writers.append(str(p.relative_to(ROOT)))
        self.assertEqual(writers, [], "only owner_sends_hold.py may write ownerSendsHold")


class TestResolverFixSendsNothingWhileHeld(_Box):
    """A box whose gate newly passes because the build tree is now found."""

    def test_newly_passing_box_is_silent_while_held(self):
        # Build tree in master-files (now found), floor-fill stubs in the workspace.
        build = self.home / "Downloads" / "openclaw-master-files" / "zero-human-company" / "fixture-co"
        for d in ("marketing", "sales", "presentations"):
            (build / "departments" / d).mkdir(parents=True)
            (self.ws / "departments" / d).mkdir(parents=True, exist_ok=True)
        self.write(ready_state(companyRoot=str(build), companySlug="fixture-co",
                               ownerConsent={"source": "operator-directive"}))
        sys.path.insert(0, str(S23))
        from _qc_paths import departments_root_for  # noqa: E402
        self.assertEqual(departments_root_for(self.ws), build / "departments")
        # The gate passes (rc 0): its auto-send block runs the REAL welcome sender.
        script = ("GATE_RC=0; BOUNDARY_STATUS=done; TRIO_STATUS=done; ROLE_STATUS=done; SOP_STATUS=done\n"
                  "SCRIPT_DIR=%s\n%s") % (S23, _gate_autosend_block())
        subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=self.env, timeout=120)
        self.run_sh(CELEBRATE)
        self.assertEqual(self.sent(), "", "an owner message went out while held")


if __name__ == "__main__":
    unittest.main(verbosity=2)
