#!/usr/bin/env python3
"""Acceptance tests for Item 21 (scripts/swarm_runner.py).

Assembly: a scratch copy of S1's skill tree + the Item 20 patch + this
stream's runner, profiles, and briefs, plus a fixture contract whose prompt
validator is a real content check (so the validation lane has real validator
output) and gate:noop elsewhere. Workers are tests/fake_worker.py driven by
a scenario file; no real KIE calls happen anywhere (the KIE token bucket is
exercised with a simulated clock).

Scenarios required by the fix plan:
- fan-out within profile limits (concurrency measured from worker intervals)
- token bucket pacing with a simulated clock, shared across two buckets
- validation failure returning to the author lane with validator output
- transport failure with an existing submitted Skill 74 receipt: the retry
  polls and the createTask counter stays at 1 (never resubmits)
- capability-absent readiness: the item waits, the sequential fallback is
  declared in the run record, and the item still completes
- fan-in naming the failed item
- timeout lane: one retry, recorded with its class
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# The S1 foundation tree this suite assembles from is not shipped in this
# repo. Resolve it relative to this test file, never as a hardcoded home
# path, so the suite runs wherever the fixture is placed and SKIPs (never
# passes) where it is not.
DEV_TREE = (Path(__file__).resolve().parent / "fixtures" / "s1-foundation"
            / "71-blackceo-signature-page")
DEV_TREE_REASON = (
    f"S1 foundation fixture absent: {DEV_TREE} "
    "(place the build-box tree there to run this suite)")

LONG_NOTE = "Checked against the artifact bytes and the stage rubric line by line."

VALIDATE_CONTENT = '''import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    text = path.read_text(encoding="utf-8", errors="replace")
except OSError:
    text = ""
if "OK" not in text:
    print(f"content check failed: {path} must contain the marker OK")
    sys.exit(1)
'''


def write(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


class Assembly:
    """S1 tree + Item 20 patch + S7 deliverables, in a temp dir."""

    def __init__(self, base: Path):
        s1 = DEV_TREE
        self.skill = base / "71-blackceo-signature-page"
        shutil.copytree(s1, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        patch = ROOT / "scripts" / "stage-gate-item-commands.patch"
        proc = subprocess.run(["patch", "-p1", "-d", str(base)],
                              stdin=open(patch), text=True, capture_output=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for rel in ("scripts/swarm_runner.py", "scripts/browser_sessions.py",
                    "references/runner-profiles.json"):
            shutil.copy(ROOT / rel, self.skill / rel)
        shutil.copytree(ROOT / "references" / "swarm-briefs",
                        self.skill / "references" / "swarm-briefs")
        write(self.skill / "scripts" / "validate_content.py", VALIDATE_CONTENT)
        contract = json.loads((self.skill / "references" / "stage-contract.json").read_text())
        for name, stage in contract["stages"].items():
            stage["validators"] = (["python3 scripts/validate_content.py {file}"]
                                   if name == "image-inventory-prompts"
                                   else ["gate:noop"])
        self.contract = base / "contract-fixture.json"
        self.contract.write_text(json.dumps(contract, indent=2), encoding="utf-8")
        self.base = base

    def gate(self, *args):
        env = {**os.environ, "STAGE_GATE_CONTRACT": str(self.contract)}
        return subprocess.run([PY, str(self.skill / "scripts" / "stage_gate.py"),
                               *[str(a) for a in args]],
                              text=True, capture_output=True, env=env)

    def write_review(self, run, stage, item, session, artifact=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
                            "CLAUDE_SESSION_ID")}
        env["OPENCLAW_SESSION_ID"] = session
        env["STAGE_GATE_CONTRACT"] = str(self.contract)
        cmd = [PY, str(self.skill / "scripts" / "write_review.py"), str(run),
               stage, item, "--scores",
               json.dumps({"quality": {"score": 10, "note": LONG_NOTE}}),
               "--verdict", "pass", "--author-session", "sess-author-1",
               "--performed-check",
               "Read the artifact end to end and scored each rubric criterion.",
               "--next-current-artifact", "the artifact named in this review"]
        if artifact:
            cmd += ["--artifact", artifact]
        return subprocess.run(cmd, text=True, capture_output=True, env=env)

    def new_run(self, image_ids):
        run = self.base / f"run-{len(list(self.base.glob('run-*')))}"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json",
              json.dumps({"fonts": {"display": "T", "body": "T", "accent": "T"}}))
        proc = self.gate("init", run)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        write(run / "mobile-tablet" / "part-01.png", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(run / "mobile-tablet" / "section-plan.json", "{}")
        write(run / "private" / "receipts" / "mobile-tablet.json", json.dumps({
            "stage": "mobile-tablet", "status": "pass",
            "author_agent": "builder-agent", "author_session": "sess-author-1",
            "started_at": "2026-10-13T10:00:00+00:00",
            "finished_at": "2026-10-13T10:30:00+00:00", "artifacts": []}))
        proc = self.write_review(run, "mobile-tablet", "stage", "sess-rev-mt",
                                 artifact="mobile-tablet/part-01.png")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        proc = self.gate("close", run, "mobile-tablet")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": i} for i in image_ids]}))
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        return run

    def close_prompt_item(self, run, item):
        write(run / "image-inventory-prompts" / f"{item}.txt", "OK prompt body")
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        write(run / "private" / "receipts" / "image-inventory-prompts.json",
              json.dumps({"stage": "image-inventory-prompts", "status": "pass",
                          "author_agent": "builder-agent",
                          "author_session": "sess-author-1",
                          "started_at": "2026-10-13T10:00:00+00:00",
                          "finished_at": "2026-10-13T10:30:00+00:00",
                          "artifacts": []}))
        proc = self.write_review(run, "image-inventory-prompts", item,
                                 "sess-rev-prompt")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        proc = self.gate("close-item", run, "image-inventory-prompts", item)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def run_runner(self, run, stages, scenario, extra_args=(), profile_file=None):
        write(run / "private" / "test-scenario.json", json.dumps(scenario))
        fake = ROOT / "tests" / "fake_worker.py"
        cmd = [PY, str(self.skill / "scripts" / "swarm_runner.py"), str(run),
               "--stages", stages, "--runtime", "generic-shell",
               "--worker-cmd",
               f"{PY} {fake} --run {{run_dir}} --stage {{stage}} "
               f"--item {{item}} --kind {{kind}} --brief {{brief}} "
               f"--note {{note}}",
               "--contract", str(self.contract),
               "--kie-limiter", str(self.base / "kie-limiter.json")]
        if profile_file:
            cmd += ["--profile-file", str(profile_file)]
        cmd += list(extra_args)
        env = {**os.environ, "OPENCLAW_DATA_DIR": str(self.base / "openclaw")}
        (self.base / "openclaw").mkdir(exist_ok=True)
        return subprocess.run(cmd, text=True, capture_output=True, env=env,
                              timeout=600)

    def runner_state(self, run):
        return json.loads((run / "private" / "runner-state.json").read_text())

    def gate_state(self, run):
        return json.loads((run / "private" / "state.json").read_text())


def max_overlap(intervals):
    events = []
    for iv in intervals:
        events.append((iv["start"], 1))
        events.append((iv["end"], -1))
    events.sort(key=lambda e: (e[0], -e[1]))
    cur = best = 0
    for _t, delta in events:
        cur += delta
        best = max(best, cur)
    return best


@unittest.skipUnless(DEV_TREE.is_dir(), DEV_TREE_REASON)
class SwarmRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = Path(tempfile.mkdtemp(prefix="swarm-runner-"))
        cls.asm = Assembly(cls.td)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def profile_file(self, **over):
        profile = {"max_workers": 4, "reviewers": 2, "playwright_instances": 1,
                   "timeout_multipliers": {},
                   "capabilities": {"render": True, "image_transport": "active",
                                    "browser": True},
                   "disk_soft_cap_bytes": 5368709120}
        for key, value in over.items():
            if isinstance(value, dict) and isinstance(profile.get(key), dict):
                profile[key] = {**profile[key], **value}
            else:
                profile[key] = value
        path = self.td / f"profile-{len(list(self.td.glob('profile-*.json')))}.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return path

    def test_token_bucket_pacing_simulated_clock(self):
        spec = importlib.util.spec_from_file_location(
            "swarm_runner", self.asm.skill / "scripts" / "swarm_runner.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        clock = module.FakeClock()
        path = self.td / "bucket-test.json"
        bucket_a = module.TokenBucket(path, clock)
        bucket_b = module.TokenBucket(path, clock)  # a second runner, same file
        times = []
        for i in range(15):
            bucket_a.consume()
            times.append(clock.now())
        for i in range(10):
            bucket_b.consume()
            times.append(clock.now())
        # Both buckets share one persisted state file: the 20-per-10s budget
        # is per account, not per runner. The first 20 grants are instant;
        # the 21st waits for the window to slide.
        self.assertEqual(len(times), 25)
        self.assertLessEqual(times[19] - times[0], 0.001)
        self.assertGreaterEqual(times[20] - times[0], 10.0)
        self.assertEqual(clock.now(), 1000.0 + 10.0)  # no real time passed
        persisted = json.loads(path.read_text())["grants"]
        self.assertTrue(all(times[0] + 10.0 - g >= -0.001 or g >= times[20]
                            for g in persisted))

    def test_profile_resolution_and_clamps(self):
        spec = importlib.util.spec_from_file_location(
            "swarm_runner2", self.asm.skill / "scripts" / "swarm_runner.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data_dir = self.td / "openclaw-probe"
        data_dir.mkdir(exist_ok=True)
        env = {"OPENCLAW_DATA_DIR": str(data_dir)}
        base_probe = {"container": False, "os": "linux", "fleet_shape": "",
                      "cgroup_mem_bytes": None, "cgroup_cpu_cores": None,
                      "os_cpus": 8, "os_mem_bytes": None}
        # Unknown container defaults to fleet-contabo, loudly.
        probe = {**base_probe, "container": True}
        profile, evidence = module.resolve_profile(env=env, probe=probe)
        self.assertEqual(profile["name"], "fleet-contabo")
        self.assertTrue(any("fleet-contabo" in a for a in evidence["assumptions"]))
        # FLEET_SHAPE wins inside a container.
        probe = {**base_probe, "container": True, "fleet_shape": "fleet-hostinger"}
        profile, _ = module.resolve_profile(env=env, probe=probe)
        self.assertEqual(profile["name"], "fleet-hostinger")
        self.assertEqual(profile["max_workers"], 8)
        # Bare-metal Mac detects fleet-mac; bare Linux detects fleet-hostinger.
        profile, _ = module.resolve_profile(
            env=env, probe={**base_probe, "os": "darwin"})
        self.assertEqual(profile["name"], "fleet-mac")
        self.assertEqual(profile["max_workers"], 6)
        # Memory clamps: under 4 GiB squeezes workers and reviewers.
        probe = {**base_probe, "container": True, "fleet_shape": "fleet-hostinger",
                 "cgroup_mem_bytes": 3 * 1024 ** 3}
        profile, evidence = module.resolve_profile(env=env, probe=probe)
        self.assertLessEqual(profile["max_workers"], 2)
        self.assertLessEqual(profile["reviewers"], 1)
        self.assertTrue(profile["image_qc_sequential"])
        # 80 percent CPU planning ceiling on a finite container CPU limit.
        probe = {**base_probe, "container": True, "fleet_shape": "fleet-hostinger",
                 "cgroup_cpu_cores": 5.0}
        profile, _ = module.resolve_profile(env=env, probe=probe)
        self.assertEqual(profile["cpu_plan_cores"], 4)
        self.assertLessEqual(profile["max_workers"], 4)
        # The per-host override file wins over detection.
        (data_dir / "skill71-runner-profile.json").write_text(json.dumps(
            {"profile": "fleet-mac", "max_workers": 3}), encoding="utf-8")
        profile, evidence = module.resolve_profile(
            env=env, probe={**base_probe, "container": True})
        self.assertEqual(profile["name"], "fleet-mac")
        self.assertEqual(profile["max_workers"], 3)

    def test_fan_out_within_profile_limits(self):
        ids = [f"IMG-00{i}" for i in range(1, 7)]
        run = self.asm.new_run(ids)
        proc = self.asm.run_runner(
            run, "image-inventory-prompts", {"items": {i: ["ok"] for i in ids}},
            profile_file=self.profile_file())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = self.asm.gate_state(run)
        for i in ids:
            self.assertEqual(state["items"]["image-inventory-prompts"][i]["status"],
                             "closed")
        intervals = [json.loads(l) for l in
                     (run / "private" / "attempts" / "intervals.jsonl")
                     .read_text().splitlines()]
        work_intervals = [iv for iv in intervals if iv["kind"] == "work"]
        self.assertEqual(len(work_intervals), 6)
        overlap = max_overlap(work_intervals)
        self.assertLessEqual(overlap, 4)  # profile max_workers
        self.assertGreaterEqual(overlap, 2)  # actually parallel
        rstate = self.asm.runner_state(run)
        node = rstate["nodes"]["image-inventory-prompts:review:IMG-001"]
        # Reviewer assignment recorded per item, matched to the criteria class.
        self.assertEqual(node["assignment"]["criteria_class"], "image-fidelity")
        self.assertEqual(node["assignment"]["brief"], "prompt-reviewer.md")
        self.assertTrue(node["assignment"]["session_id"].startswith("fake-"))

    def test_validation_failure_returns_to_author_lane(self):
        run = self.asm.new_run(["IMG-001"])
        proc = self.asm.run_runner(
            run, "image-inventory-prompts",
            {"items": {"IMG-001": ["bad-content", "ok"]}},
            profile_file=self.profile_file())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rstate = self.asm.runner_state(run)
        node = rstate["nodes"]["image-inventory-prompts:work:IMG-001"]
        self.assertEqual(node["status"], "done")
        self.assertEqual(len(node["attempts"]), 2)
        self.assertEqual(node["attempts"][1]["lane"], "validation")
        brief2 = (run / "private" / "briefs" /
                  "image-inventory-prompts-IMG-001-work-attempt2.md").read_text()
        self.assertIn("failure class: validation", brief2)
        self.assertIn("must contain the marker OK", brief2)  # validator output
        state = self.asm.gate_state(run)
        self.assertEqual(state["items"]["image-inventory-prompts"]["IMG-001"]
                         ["status"], "closed")

    def test_transport_failure_polls_never_resubmits(self):
        run = self.asm.new_run(["IMG-001"])
        self.asm.close_prompt_item(run, "IMG-001")
        proc = self.asm.run_runner(
            run, "image-generation-qc",
            {"items": {"IMG-001": ["gen-transport-fail", "gen-poll-ok"]}},
            profile_file=self.profile_file())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        create_count = int((run / "private" / "attempts" / "createtask.count")
                           .read_text())
        self.assertEqual(create_count, 1)  # the submitted task was polled only
        rstate = self.asm.runner_state(run)
        node = rstate["nodes"]["image-generation-qc:work:IMG-001"]
        self.assertEqual(node["attempts"][1]["lane"], "transport-poll")
        brief2 = (run / "private" / "briefs" /
                  "image-generation-qc-IMG-001-work-attempt2.md").read_text()
        self.assertIn("Poll only", brief2)
        self.assertIn("task-001", brief2)
        state = self.asm.gate_state(run)
        self.assertEqual(state["items"]["image-generation-qc"]["IMG-001"]
                         ["status"], "closed")

    def test_capability_absent_waits_and_declares_fallback(self):
        run = self.asm.new_run(["IMG-001"])
        profile = self.profile_file(capabilities={"render": False})
        proc = self.asm.run_runner(run, "desktop-wireframe",
                                   {"stages": {"desktop-wireframe": ["ok"]}},
                                   profile_file=profile)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rstate = self.asm.runner_state(run)
        self.assertTrue(rstate["fallback"]["declared"])
        self.assertEqual(rstate["fallback"]["capability"], "render")
        self.assertEqual(rstate["fallback"]["mode"], "sequential-fallback")
        self.assertTrue((run / "private" / "runner-fallback.json").exists())
        node = rstate["nodes"]["desktop-wireframe:work:stage"]
        self.assertEqual(node["waited_on_capability"], "render")
        self.assertEqual(node["status"], "done")  # completed sequentially

    def test_fan_in_names_the_failed_item(self):
        run = self.asm.new_run(["IMG-001", "IMG-002"])
        proc = self.asm.run_runner(
            run, "image-inventory-prompts",
            {"items": {"IMG-001": ["ok"],
                       "IMG-002": ["bad-content", "bad-content"]}},
            profile_file=self.profile_file())
        self.assertEqual(proc.returncode, 1)
        self.assertIn("IMG-002", proc.stdout)
        rstate = self.asm.runner_state(run)
        self.assertIn("image-inventory-prompts:work:IMG-002",
                      rstate["summary"]["blocked_items"])
        close_node = rstate["nodes"]["image-inventory-prompts:stageclose:stage"]
        self.assertEqual(close_node["status"], "blocked")
        self.assertIn("IMG-002", close_node["blocked_reason"])  # gate fan-in
        self.assertIn("fan-in", close_node["blocked_reason"])
        state = self.asm.gate_state(run)
        self.assertEqual(state["items"]["image-inventory-prompts"]["IMG-002"]
                         ["status"], "blocked")

    def test_timeout_retries_once_in_retry_lane(self):
        run = self.asm.new_run(["IMG-001"])
        proc = self.asm.run_runner(
            run, "image-inventory-prompts",
            {"items": {"IMG-001": ["sleep", "ok"]}},
            extra_args=("--timeout-work", "1"),
            profile_file=self.profile_file())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rstate = self.asm.runner_state(run)
        node = rstate["nodes"]["image-inventory-prompts:work:IMG-001"]
        self.assertEqual(len(node["attempts"]), 2)
        self.assertTrue(node["attempts"][0]["timed_out"])
        self.assertEqual(node["attempts"][1]["lane"], "timeout")


if __name__ == "__main__":
    if not DEV_TREE.is_dir():
        print(f"SKIPMOD {Path(__file__).name}: {DEV_TREE_REASON}")
    unittest.main()
