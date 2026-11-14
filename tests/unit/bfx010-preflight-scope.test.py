#!/usr/bin/env python3
"""BFX-010 (a): fleet_preflight run scope, notify env, and the paused line.

  1. A repo-only run and an --only run whose skills use no paid provider skip the
     provider-billing gates (storage and memory still apply).
  2. FLEET_PREFLIGHT_NO_NOTIFY=1 means notify=False (no client note).
  3. The paused line stays byte-exact: FLEET-PREFLIGHT-PAUSED: <reasons>
     (the roll skill reads it; leading spaces are tolerated, nothing else changes).

Hermetic: temp box, stub `openclaw` on PATH, provider smoke checks replaced, no network.

    python3 tests/unit/bfx010-preflight-scope.test.py
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
for _k in ("FLEET_PREFLIGHT_NOW", "FLEET_PREFLIGHT_FREE_BYTES", "FLEET_PREFLIGHT_MEM_FREE_PCT",
           "FLEET_PREFLIGHT_MAC_LEVEL", "FLEET_PREFLIGHT_PSI_SOME", "FLEET_PREFLIGHT_PSI_FULL",
           "FLEET_PROVIDER_STANDING_FILE", "FLEET_PREFLIGHT_RUN_ID", "FLEET_PREFLIGHT_NO_SEND",
           "FLEET_PREFLIGHT_NO_NOTIFY", "FLEET_PREFLIGHT_SCOPE", "FLEET_PREFLIGHT_BYPASS"):
    os.environ.pop(_k, None)
import fleet_preflight as fp  # noqa: E402

GIB = 1024 ** 3
OWNER = "424242424"
AFTER_GRACE = "2026-11-06"


class Box:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bfx010-pf-"))
        self.root = self.tmp / ".openclaw"
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "openclaw.json").write_text("{}")
        (self.root / "workspace" / ".workforce-build-state.json").write_text(json.dumps({"ownerChat": OWNER}))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.sent = self.tmp / "sent.jsonl"
        cli = self.bin / "openclaw"
        cli.write_text(
            "#!/usr/bin/env python3\nimport json,sys\n"
            "a=sys.argv[1:]\n"
            "t=a[a.index('--target')+1]; m=a[a.index('--message')+1]\n"
            f"open({str(self.sent)!r},'a').write(json.dumps({{'to':t,'text':m}})+'\\n')\n"
            "print(json.dumps({'ok':True,'payload':{'ok':True,'messageId':'7','chatId':t,'channel':'telegram'}}))\n")
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
        self.env = mock.patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}"})
        self.env.start()

    def messages(self):
        return [json.loads(l) for l in self.sent.read_text().splitlines()] if self.sent.exists() else []

    def close(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.box = Box()
        self.addCleanup(self.box.close)
        p = mock.patch.dict(os.environ, {}, clear=False)
        p.start(); self.addCleanup(p.stop)
        os.environ["FLEET_PREFLIGHT_NOW"] = AFTER_GRACE
        os.environ["FLEET_PROVIDER_STANDING_FILE"] = str(self.box.root / "provider-standing.json")
        os.environ.update(FLEET_PREFLIGHT_MEM_FREE_PCT="60", FLEET_PREFLIGHT_MAC_LEVEL="1",
                          FLEET_PREFLIGHT_FREE_BYTES=str(50 * GIB))
        # Every provider is failing at the external read point: any gate that runs would pause.
        stamp = AFTER_GRACE + "T00:00:00Z"
        (self.box.root / "provider-standing.json").write_text(json.dumps(
            {k: {"status": "fail", "checked_at": stamp, "detail": "402"} for k in fp.PROVIDERS}))
        m = mock.patch.object(fp, "_repo_smoke", return_value=None)
        m.start(); self.addCleanup(m.stop)

    def cli(self, *a, **env):
        e = {**os.environ, **env, "OPENCLAW_ROOT": str(self.box.root)}
        return subprocess.run([sys.executable, str(REPO / "shared-utils/fleet_preflight.py"), *a],
                              capture_output=True, text=True, env=e)


class ProviderGateScope(Base):
    def test_full_run_still_pauses_on_a_failing_provider(self):
        r = fp.run("checks", self.box.root, "unknown", False, "r1")
        self.assertEqual(r["status"], "paused-preflight")
        self.assertIn("kie.ai standing", r["pause_reasons"])

    def test_repo_only_run_skips_every_provider_gate(self):
        r = fp.run("checks", self.box.root, "unknown", False, "r1", scope="repo-only")
        self.assertEqual((r["status"], r["pause_reasons"]), ("proceed", []))
        for p in fp.PROVIDERS:
            self.assertEqual(r["checks"]["providers"][p]["status"], "skipped")

    def test_only_run_with_no_provider_skill_skips_the_provider_gates(self):
        r = fp.run("checks", self.box.root, "unknown", False, "r1", only="05,06")
        self.assertEqual((r["status"], r["pause_reasons"]), ("proceed", []))

    def test_only_run_checks_just_the_providers_its_skills_use(self):
        r = fp.run("checks", self.box.root, "unknown", False, "r1", only="66, 63")
        self.assertEqual(sorted(r["pause_reasons"]), ["Agnes AI standing", "kie.ai standing"])
        self.assertEqual(r["checks"]["providers"]["gemini"]["status"], "skipped")
        self.assertEqual(r["checks"]["providers"]["openrouter"]["status"], "skipped")

    def test_unrelated_provider_failure_does_not_block_an_only_run(self):
        stamp = AFTER_GRACE + "T00:00:00Z"
        (self.box.root / "provider-standing.json").write_text(json.dumps(
            {"gemini": {"status": "fail", "checked_at": stamp, "detail": "402"}}))
        r = fp.run("checks", self.box.root, "unknown", False, "r1", only="66")
        self.assertEqual(r["status"], "proceed")

    def test_storage_and_memory_still_pause_a_repo_only_run(self):
        os.environ["FLEET_PREFLIGHT_FREE_BYTES"] = "1"
        r = fp.run("checks", self.box.root, "unknown", False, "r1", scope="repo-only")
        self.assertEqual(r["pause_reasons"], ["storage"])

    def test_cli_flags_and_scope_env(self):
        out = self.cli("--phase", "checks", "--no-notify", "--scope", "repo-only")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.cli("--phase", "checks", "--no-notify", "--only", "05")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.cli("--phase", "checks", "--no-notify", FLEET_PREFLIGHT_SCOPE="repo-only")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.cli("--phase", "checks", "--no-notify")
        self.assertEqual(out.returncode, 10, out.stdout + out.stderr)


class NoNotifyEnv(Base):
    def setUp(self):
        super().setUp()
        os.environ["FLEET_PREFLIGHT_FREE_BYTES"] = "1"   # storage fails: a note would normally go out

    def test_default_sends_the_note(self):
        r = fp.run("checks", self.box.root, "unknown", True, "r1", scope="repo-only")
        self.assertEqual(r["notices"]["storage"], "sent")
        self.assertEqual(len(self.box.messages()), 1)

    def test_env_maps_to_notify_false_in_run(self):
        os.environ["FLEET_PREFLIGHT_NO_NOTIFY"] = "1"
        r = fp.run("checks", self.box.root, "unknown", True, "r1", scope="repo-only")
        self.assertEqual(r["notices"], {})
        self.assertEqual(self.box.messages(), [])
        self.assertEqual(r["status"], "paused-preflight")   # the pause itself is unchanged

    def test_env_maps_to_notify_false_through_the_cli(self):
        out = self.cli("--phase", "checks", "--scope", "repo-only", FLEET_PREFLIGHT_NO_NOTIFY="1")
        self.assertEqual(out.returncode, 10)
        self.assertEqual(self.box.messages(), [])

    def test_only_the_value_one_counts(self):
        os.environ["FLEET_PREFLIGHT_NO_NOTIFY"] = "0"
        fp.run("checks", self.box.root, "unknown", True, "r1", scope="repo-only")
        self.assertEqual(len(self.box.messages()), 1)


class PausedLineIsByteExact(Base):
    def test_python_prints_exactly_the_marker_and_the_reasons(self):
        os.environ.update(FLEET_PREFLIGHT_FREE_BYTES="1", FLEET_PREFLIGHT_MAC_LEVEL="2")
        out = self.cli("--phase", "checks", "--no-notify", "--scope", "repo-only")
        self.assertEqual(out.returncode, 10)
        lines = [l for l in out.stdout.splitlines() if l.startswith("FLEET-PREFLIGHT-PAUSED")]
        self.assertEqual(lines, ["FLEET-PREFLIGHT-PAUSED: storage, memory pressure"])
        self.assertIn(b"FLEET-PREFLIGHT-PAUSED: storage, memory pressure\n", out.stdout.encode())

    def test_marker_constant_in_the_repo_reader_matches(self):
        import fleet_refresh_runner as runner
        self.assertEqual(runner.PREFLIGHT_PAUSED_MARK, "FLEET-PREFLIGHT-PAUSED")
        self.assertEqual(runner._preflight_reasons("FLEET-PREFLIGHT-PAUSED: storage, memory pressure\n"),
                         "storage, memory pressure")

    def test_the_shell_wrapper_only_adds_leading_spaces(self):
        sh = (REPO / "update-skills.sh").read_text()
        blk = sh[sh.index("#=== BEGIN FLEET-PREFLIGHT-V1 ==="):sh.index("#=== END FLEET-PREFLIGHT-V1 ===")]
        blk = re.sub(r"^[ \t]*fleet_preflight_checks[ \t]*$", ":", blk, count=1, flags=re.M)
        f = self.box.tmp / "blk.sh"
        f.write_text(blk + '\nfleet_preflight_checks\n')
        (self.box.root / "skills").mkdir()
        (self.box.root / "skills" / "shared-utils").symlink_to(REPO / "shared-utils")
        e = {**os.environ, "OPENCLAW_ROOT": str(self.box.root), "OC_CONFIG": str(self.box.root),
             "HOME": str(self.box.tmp), "FLEET_PREFLIGHT_NO_SEND": "1", "FLEET_PREFLIGHT_FREE_BYTES": "1",
             "FLEET_PREFLIGHT_SCOPE": "repo-only"}
        out = subprocess.run(["bash", str(f)], capture_output=True, text=True, env=e)
        hits = [l for l in out.stdout.splitlines() if "FLEET-PREFLIGHT-PAUSED" in l]
        self.assertEqual([l.lstrip(" ") for l in hits], ["FLEET-PREFLIGHT-PAUSED: storage"])


class ShellPassesTheScope(Base):
    """The block runs at top level before main() parses args, so it prescans them itself."""

    def run_block(self, *args, **env):
        sh = (REPO / "update-skills.sh").read_text()
        blk = sh[sh.index("#=== BEGIN FLEET-PREFLIGHT-V1 ==="):sh.index("#=== END FLEET-PREFLIGHT-V1 ===")]
        blk = re.sub(r"^[ \t]*fleet_preflight_checks[ \t]*$", ":", blk, count=1, flags=re.M)
        f = self.box.tmp / "blk.sh"
        f.write_text("set -euo pipefail\nSELF_SYNC_ARGS=(\"$@\")\n" + blk + '\nfleet_preflight_checks\necho __AFTER__\n')
        if not (self.box.root / "skills").exists():
            (self.box.root / "skills").mkdir()
            (self.box.root / "skills" / "shared-utils").symlink_to(REPO / "shared-utils")
        e = {**os.environ, "OPENCLAW_ROOT": str(self.box.root), "OC_CONFIG": str(self.box.root),
             "HOME": str(self.box.tmp), "FLEET_PREFLIGHT_NO_SEND": "1", **env}
        return subprocess.run(["bash", str(f), *args], capture_output=True, text=True, env=e)

    def test_full_run_is_paused_by_the_failing_providers(self):
        r = self.run_block()
        self.assertNotIn("__AFTER__", r.stdout)
        self.assertIn("FLEET-PREFLIGHT-PAUSED: ", r.stdout)

    def test_onboarding_only_goes_on(self):
        r = self.run_block("--onboarding-only")
        self.assertIn("__AFTER__", r.stdout, r.stdout + r.stderr)

    def test_onboarding_only_env_goes_on(self):
        r = self.run_block(ONBOARDING_ONLY="1")
        self.assertIn("__AFTER__", r.stdout, r.stdout + r.stderr)

    def test_only_with_a_provider_unrelated_skill_goes_on(self):
        for args in (("--only", "05,06"), ("--only=05,06")):
            r = self.run_block(*([args] if isinstance(args, str) else args))
            self.assertIn("__AFTER__", r.stdout, r.stdout + r.stderr)

    def test_only_with_a_provider_skill_is_still_paused(self):
        r = self.run_block("--only", "66")
        self.assertNotIn("__AFTER__", r.stdout)
        self.assertIn("kie.ai standing", r.stdout)

    def test_storage_still_pauses_an_onboarding_only_run(self):
        r = self.run_block("--onboarding-only", FLEET_PREFLIGHT_FREE_BYTES="1")
        self.assertNotIn("__AFTER__", r.stdout)
        self.assertIn("FLEET-PREFLIGHT-PAUSED: storage", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
