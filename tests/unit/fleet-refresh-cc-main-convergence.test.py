#!/usr/bin/env python3
"""Regression: fleet refresh must not detach/downgrade CC after root update."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = Path(os.environ.get(
    "FLEET_RUNNER_UNDER_TEST",
    REPO_ROOT / "shared-utils" / "fleet_refresh_runner.py",
))


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def load_runner():
    spec = importlib.util.spec_from_file_location("runner_under_test", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FleetRefreshCCMainConvergence(unittest.TestCase):
    def test_feature_branch_converges_to_latest_main_without_tag_downgrade(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory(prefix="fleet-cc-main-") as td:
            root = Path(td)
            origin = root / "origin"
            checkout = root / "checkout"
            origin.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(origin)], check=True)
            git(origin, "config", "user.name", "Fixture")
            git(origin, "config", "user.email", "fixture@example.invalid")
            (origin / "version").write_text("v1\n")
            (origin / "update.sh").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "git fetch origin main\n"
                "git -c user.name=Updater -c user.email=updater@example.invalid merge --no-edit origin/main\n"
                "git branch -f main HEAD\n"
                "git checkout main\n"
            )
            os.chmod(origin / "update.sh", 0o755)
            git(origin, "add", "version", "update.sh")
            git(origin, "commit", "-qm", "initial")
            git(origin, "tag", "v0.1.0")

            subprocess.run(["git", "clone", "-q", str(origin), str(checkout)], check=True)
            git(checkout, "config", "user.name", "Box")
            git(checkout, "config", "user.email", "box@example.invalid")
            git(checkout, "checkout", "-qb", "box-feature")
            (checkout / "box-local.txt").write_text("retained\n")
            git(checkout, "add", "box-local.txt")
            git(checkout, "commit", "-qm", "box local")
            local_commit = git(checkout, "rev-parse", "HEAD")

            (origin / "latest-main.txt").write_text("latest\n")
            git(origin, "add", "latest-main.txt")
            git(origin, "commit", "-qm", "latest main")

            result = runner.BoxResult("fixture-box", dry_run=False)
            runner.step_pull_cc(
                {"cc_dir": checkout}, "v0.1.0", result, dry_run=False, force_cc=False,
            )

            self.assertEqual(result.steps.get("pull-cc"), "ok", result.errors)
            self.assertEqual(git(checkout, "branch", "--show-current"), "main")
            subprocess.run(
                ["git", "-C", str(checkout), "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(checkout), "merge-base", "--is-ancestor", local_commit, "HEAD"],
                check=True,
            )
            self.assertTrue((checkout / "latest-main.txt").is_file())
            feature_tip = git(checkout, "show-ref", "--verify", "--hash", "refs/heads/box-feature")
            subprocess.run(
                ["git", "-C", str(checkout), "merge-base", "--is-ancestor", local_commit, feature_tip],
                check=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
