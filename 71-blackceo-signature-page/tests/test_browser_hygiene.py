#!/usr/bin/env python3
"""Acceptance tests for Item 33 (browser teardown and hygiene gate).

Assembly: a scratch copy of S1's skill tree + the Item 20 patch + the
Item 33 patch (scripts/stage-gate-browser-hygiene.patch) + this
stream's scripts/browser_sessions.py and scripts/swarm_runner.py. No
real browser anywhere: tests/fake_browser.py stands in for an engine
(a session is alive while its marker file exists, or while its
recorded owner pid lives).

Covered, per the item:
- clean run: opened == closed, unaccounted 0, the stage closes and
  the receipt says so
- leaked session reaped at pre-close: orphans_found 1, reaped 1,
  unaccounted 0, close allowed with the reap recorded
- unreapable session: close refused, the session named
- runner death mid-stage: the registry keeps the opens; the gate's
  reaper pass accounts for them (browser process gone: verified and
  reaped; browser process still alive: torn down and reaped)
- headed launch counted and flagged; an owner override on record
  lets the close proceed with the violation visible in the receipt
- check performs the reaper pass before evaluating anything else
- REPORT.md gains the hygiene line; REPORT.json's frozen hygiene
  object is filled in S6's exact field names and validates against
  the frozen schema
- runner paths: a normal run registers and closes its session; a
  SIGTERM makes the runner tear its sessions down; a SIGKILL leaves
  them open for the gate, which then reaps the worker's browser
"""
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
S6_REPORT_EXAMPLE = (Path.home() / "workspace/skill-71-build/s6-tracking"
                     / "skill71/71-blackceo-signature-page/references"
                     / "report-json.example.json")
S6_REPORT_SCHEMA = S6_REPORT_EXAMPLE.with_name("report-json.schema.json")

WORKER = '''
import json, os, subprocess, sys, time
from pathlib import Path
run = Path.cwd()
mode = os.environ.get("FAKE_BROWSER_MODE", "write")
if mode in ("write", "enrich"):
    p = run / "ghl-install-test" / "install-steps.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("steps\\n", encoding="utf-8")
if mode == "enrich":
    # The worker-side adapter enriches the runner's named session with
    # the browser process it actually launched (detached: it survives
    # both the worker and the runner), then sleeps mid-stage.
    skill_scripts = Path(os.environ["SKILL_SCRIPTS"])
    hold = subprocess.Popen(
        [sys.executable, str(skill_scripts.parent / "tests" / "fake_browser.py"),
         "hold", "--marker", str(run / "private" / "fake-browser.alive"),
         "--seconds", "600"],
        start_new_session=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    (run / "private" / "hold.pid").write_text(str(hold.pid), encoding="utf-8")
    sys.path.insert(0, str(skill_scripts))
    import browser_sessions as bs
    sessions = bs.fold_sessions(run)
    name = sorted(n for n, s in sessions.items()
                  if s.get("stage") == "ghl-install-test"
                  and s.get("status") == "open")[-1]
    bs.register_open(run, session_name=name, stage="ghl-install-test",
                     engine="fake", binding="test",
                     owner_pid=hold.pid, via="fake-adapter")
    time.sleep(600)
if mode == "sleep":
    time.sleep(600)
print("SESSION: fake-worker-session")
'''


def write(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def load_module(skill: Path, name: str):
    spec = importlib.util.spec_from_file_location(
        name, skill / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Assembly:
    """S1 tree + Item 20 patch + Item 33 patch + S7 scripts, in temp."""

    def __init__(self, base: Path):
        s1 = (Path.home() / "workspace/skill-71-build/s1-foundation"
              / "71-blackceo-signature-page")
        self.skill = base / "71-blackceo-signature-page"
        shutil.copytree(s1, self.skill,
                        ignore=shutil.ignore_patterns("__pycache__"))
        for patch_name in ("stage-gate-item-commands.patch",
                           "stage-gate-browser-hygiene.patch"):
            patch = ROOT / "scripts" / patch_name
            proc = subprocess.run(["patch", "-p1", "-d", str(base)],
                                  stdin=open(patch), text=True,
                                  capture_output=True)
            assert proc.returncode == 0, (patch_name, proc.stdout, proc.stderr)
        for rel in ("scripts/browser_sessions.py", "scripts/swarm_runner.py",
                    "references/runner-profiles.json"):
            shutil.copy(ROOT / rel, self.skill / rel)
        shutil.copytree(ROOT / "references" / "swarm-briefs",
                        self.skill / "references" / "swarm-briefs")
        shutil.copy(ROOT / "tests" / "fake_browser.py",
                    self.skill / "tests" / "fake_browser.py")
        self.bs = load_module(self.skill, "browser_sessions")
        self.base = base

    def gate(self, *args, contract=None):
        env = {**os.environ}
        if contract:
            env["STAGE_GATE_CONTRACT"] = str(contract)
        return subprocess.run(
            [PY, str(self.skill / "scripts" / "stage_gate.py"),
             *[str(a) for a in args]], text=True, capture_output=True, env=env)

    def new_run(self, name="run"):
        run = self.base / name
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json",
              json.dumps({"fonts": {"display": "T", "body": "T",
                                    "accent": "T"}}))
        proc = self.gate("init", run)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return run

    def put_receipt(self, run, stage, **kw):
        receipt = {"stage": stage, "status": "pass",
                   "author_agent": "builder-agent",
                   "author_session": "sess-author-1",
                   "started_at": "2026-10-13T10:00:00+00:00",
                   "finished_at": "2026-10-13T10:30:00+00:00",
                   "artifacts": []}
        receipt.update(kw)
        write(run / "private" / "receipts" / f"{stage}.json",
              json.dumps(receipt))

    def prep_install_stage(self, run):
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        self.put_receipt(run, "ghl-install-test")


class HygieneGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp(prefix="hygiene-gate-"))
        cls.asm = Assembly(cls.td)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def setUp(self):
        self.run = self.asm.new_run(f"run-{self._testMethodName}")
        self.asm.prep_install_stage(self.run)
        self.bs = self.asm.bs

    def open_session(self, name, **kw):
        kw.setdefault("stage", "ghl-install-test")
        kw.setdefault("engine", "fake")
        kw.setdefault("binding", "test")
        self.bs.register_open(self.run, session_name=name, **kw)
        return name

    def receipt(self):
        return json.loads((self.run / "ghl-install-test"
                           / "browser-hygiene.json").read_text())

    def test_clean_run_closes(self):
        self.open_session("s-clean-1")
        self.open_session("s-clean-2")
        self.bs.register_close(self.run, "s-clean-1")
        self.bs.register_close(self.run, "s-clean-2")
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.receipt()
        self.assertEqual((r["sessions_opened"], r["sessions_closed"],
                          r["orphans_found"], r["orphans_reaped"],
                          r["unaccounted"], r["headed_launches"]),
                         (2, 2, 0, 0, 0, 0))
        self.assertTrue(all(s["closed_by"] == "normal"
                            for s in r["sessions"]))

    def test_leaked_session_reaped_at_close(self):
        self.open_session("s-ok")
        self.bs.register_close(self.run, "s-ok")
        marker = self.run / "private" / "leaked.alive"
        marker.write_text("alive\n")
        teardown = (f"{PY} {self.asm.skill}/tests/fake_browser.py teardown "
                    f"--marker {marker}")
        self.open_session("s-leaked", live_marker=str(marker),
                          teardown_cmd=teardown)
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.receipt()
        self.assertEqual((r["orphans_found"], r["orphans_reaped"],
                          r["unaccounted"]), (1, 1, 0))
        by_name = {s["name"]: s for s in r["sessions"]}
        self.assertEqual(by_name["s-leaked"]["closed_by"], "reaped")
        self.assertFalse(marker.exists())

    def test_unreapable_session_blocks_close_named(self):
        marker = self.run / "private" / "stuck.alive"
        marker.write_text("alive\n")
        teardown = (f"{PY} {self.asm.skill}/tests/fake_browser.py teardown "
                    f"--marker {marker} --fail")
        self.open_session("s-stuck", live_marker=str(marker),
                          teardown_cmd=teardown)
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("s-stuck", proc.stdout)
        self.assertIn("unaccounted", proc.stdout)
        r = self.receipt()
        self.assertEqual(r["unaccounted"], 1)
        by_name = {s["name"]: s for s in r["sessions"]}
        self.assertIsNone(by_name["s-stuck"]["closed_by"])
        self.assertTrue(marker.exists())

    def test_runner_death_browser_gone_reaped(self):
        # A browser process that died with its runner: the pid on
        # record no longer answers, the sweep verifies and reaps.
        sleeper = subprocess.Popen([PY, "-c", "import time; time.sleep(30)"])
        pid = sleeper.pid
        sleeper.kill()
        sleeper.wait()
        self.open_session("s-orphan", owner_pid=pid)
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.receipt()
        self.assertEqual((r["orphans_found"], r["orphans_reaped"],
                          r["unaccounted"]), (1, 1, 0))

    def test_live_browser_torn_down_by_reaper(self):
        sleeper = subprocess.Popen([PY, "-c", "import time; time.sleep(30)"])
        try:
            self.open_session("s-live", owner_pid=sleeper.pid)
            proc = self.asm.gate("close", self.run, "ghl-install-test")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIsNotNone(sleeper.poll(),
                                 "reaper must terminate the live session")
            r = self.receipt()
            self.assertEqual((r["orphans_reaped"], r["unaccounted"]), (1, 0))
        finally:
            if sleeper.poll() is None:
                sleeper.kill()
                sleeper.wait()

    def test_headed_launch_blocks_then_override_allows(self):
        self.open_session("s-headed", headed=True)
        self.bs.register_close(self.run, "s-headed")
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("headed", proc.stdout)
        write(self.run / "intake.json", json.dumps({
            "browser_headed_override": {
                "ghl-install-test": {
                    "by": "owner",
                    "reason": "operator watched the click-through live"}}}))
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.receipt()
        self.assertEqual(r["headed_launches"], 1)
        self.assertEqual(r["owner_override_headed"]["by"], "owner")

    def test_check_reaps_before_evaluating(self):
        marker = self.run / "private" / "early.alive"
        marker.write_text("alive\n")
        teardown = (f"{PY} {self.asm.skill}/tests/fake_browser.py teardown "
                    f"--marker {marker}")
        self.open_session("s-early", live_marker=str(marker),
                          teardown_cmd=teardown)
        # Dependencies are unclosed, so check must fail; the reaper
        # pass runs first, so the leak is still accounted.
        proc = self.asm.gate("check", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        folded = self.bs.fold_sessions(self.run)
        self.assertEqual(folded["s-early"]["closed_by"], "reaped")
        self.assertTrue((self.run / "ghl-install-test"
                         / "browser-hygiene.json").exists())

    def test_report_line_and_report_json_rollup(self):
        self.open_session("s-r1")
        self.bs.register_close(self.run, "s-r1")
        marker = self.run / "private" / "rep.alive"
        marker.write_text("alive\n")
        teardown = (f"{PY} {self.asm.skill}/tests/fake_browser.py teardown "
                    f"--marker {marker}")
        self.open_session("s-r2", live_marker=str(marker),
                          teardown_cmd=teardown)
        proc = self.asm.gate("close", self.run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        shutil.copy(S6_REPORT_EXAMPLE, self.run / "REPORT.json")
        self.asm.gate("report", self.run)  # rc 1: other stages open
        report_md = (self.run / "REPORT.md").read_text()
        self.assertIn("Browser hygiene: 2 sessions opened, 1 closed, "
                      "1 orphans reaped.", report_md)
        twin = json.loads((self.run / "REPORT.json").read_text())
        self.assertEqual(twin["hygiene"], {
            "status": "recorded", "opened": 2, "closed": 1,
            "orphans_found": 1, "reaped": 1, "unaccounted": 0,
            "headed_launches": 0})
        import jsonschema
        jsonschema.validate(
            twin, json.loads(S6_REPORT_SCHEMA.read_text()),
            format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)


class HygieneRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp(prefix="hygiene-runner-"))
        cls.asm = Assembly(cls.td)
        cls.worker = cls.td / "browser_worker.py"
        write(cls.worker, WORKER)
        contract = json.loads(
            (cls.asm.skill / "references" / "stage-contract.json").read_text())
        for stage in contract["stages"].values():
            stage["validators"] = ["gate:noop"]
        cls.contract = cls.td / "contract-fixture.json"
        write(cls.contract, json.dumps(contract, indent=2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def start_runner(self, run, mode):
        env = {**os.environ, "FAKE_BROWSER_MODE": mode,
               "SKILL_SCRIPTS": str(self.asm.skill / "scripts")}
        cmd = [PY, str(self.asm.skill / "scripts" / "swarm_runner.py"),
               str(run), "--stages", "ghl-install-test",
               "--runtime", "generic-shell",
               "--worker-cmd", f"{PY} {self.worker}",
               "--contract", str(self.contract)]
        return subprocess.Popen(cmd, env=env, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                start_new_session=True)

    def wait_for_open_session(self, run, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            folded = self.asm.bs.fold_sessions(run)
            opens = [n for n, s in folded.items()
                     if s.get("stage") == "ghl-install-test"
                     and s.get("status") == "open"]
            if opens:
                return opens[0]
            time.sleep(0.25)
        self.fail("runner never registered a browser session")

    def test_runner_registers_and_closes_its_session(self):
        run = self.asm.new_run("run-normal")
        proc = self.start_runner(run, "write")
        out, _ = proc.communicate(timeout=180)
        self.assertEqual(proc.returncode, 0, out)
        folded = self.asm.bs.fold_sessions(run)
        mine = [s for s in folded.values()
                if s.get("stage") == "ghl-install-test"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["status"], "closed")
        self.assertEqual(mine[0]["closed_by"], "normal")
        self.assertIn("ghl-install-test", mine[0]["session_name"])
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["ghl-install-test"]["status"],
                         "closed")
        r = json.loads((run / "ghl-install-test"
                        / "browser-hygiene.json").read_text())
        self.assertEqual((r["sessions_opened"], r["sessions_closed"],
                          r["unaccounted"]), (1, 1, 0))

    def test_runner_sigterm_tears_down(self):
        run = self.asm.new_run("run-sigterm")
        proc = self.start_runner(run, "sleep")
        try:
            name = self.wait_for_open_session(run)
            proc.send_signal(signal.SIGTERM)
            deadline = time.time() + 15
            folded = {}
            while time.time() < deadline:
                folded = self.asm.bs.fold_sessions(run)
                if folded.get(name, {}).get("status") == "closed":
                    break
                time.sleep(0.25)
            self.assertEqual(folded[name]["status"], "closed")
            self.assertEqual(folded[name]["closed_by"], "normal")
            self.assertEqual(folded[name].get("close_via"),
                             "runner-signal-15")
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()

    def test_runner_sigkill_gate_reaps(self):
        run = self.asm.new_run("run-sigkill")
        proc = self.start_runner(run, "enrich")
        hold_pid = None
        try:
            name = self.wait_for_open_session(run)
            pid_file = run / "private" / "hold.pid"
            deadline = time.time() + 30
            while time.time() < deadline and not pid_file.exists():
                time.sleep(0.25)
            self.assertTrue(pid_file.exists(), "worker never enriched")
            hold_pid = int(pid_file.read_text())
            # The pid file lands before the adapter's registry
            # enrichment; wait until the enrichment is on record, or
            # the kill races it and the session keeps no handle.
            deadline = time.time() + 30
            while time.time() < deadline:
                rec = self.asm.bs.fold_sessions(run).get(name, {})
                if rec.get("owner_pid") == hold_pid:
                    break
                time.sleep(0.25)
            self.assertEqual(rec.get("owner_pid"), hold_pid,
                             "adapter enrichment never reached the registry")
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            folded = self.asm.bs.fold_sessions(run)
            self.assertEqual(folded[name]["status"], "open",
                             "a killed runner must leave the session open")
            os.kill(hold_pid, 0)  # the browser outlived the runner
            self.asm.prep_install_stage(run)
            gate = self.asm.gate("close", run, "ghl-install-test")
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            folded = self.asm.bs.fold_sessions(run)
            self.assertEqual(folded[name]["closed_by"], "reaped")
            with self.assertRaises(ProcessLookupError):
                os.kill(hold_pid, 0)
            hold_pid = None
            r = json.loads((run / "ghl-install-test"
                            / "browser-hygiene.json").read_text())
            self.assertEqual((r["orphans_found"], r["orphans_reaped"],
                              r["unaccounted"]), (1, 1, 0))
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            if hold_pid:
                try:
                    os.kill(hold_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
