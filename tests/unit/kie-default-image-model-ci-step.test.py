#!/usr/bin/env python3
"""X-97: the CI step that runs Skill 74's default-image-model check cannot be softened.

Skill 74's own tests also run on a box (qc-74-kie-live-adapter.sh), where this repository's .github folder does not
exist, so the check of the workflow lives here instead, where the folder always does. The step must run the check
script exactly once and let any non-zero exit fail the job: no continue-on-error on the step or its job, no
"|| true", no "set +e", no "if:".
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "version-consistency.yml")
RUN = "run: python3 -I 74-kie-live-adapter/scripts/check_default_image_model.py"


class CiStepRunsTheCheck(unittest.TestCase):
    def test_the_ci_step_runs_the_check_and_lets_any_non_zero_exit_fail_the_job(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            lines = f.read().splitlines()
        runs = [i for i, l in enumerate(lines) if "check_default_image_model.py" in l and l.strip().startswith("run:")]
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(lines[runs[0]].strip(), RUN)
        start = max(i for i in range(runs[0]) if lines[i].lstrip().startswith("- name:"))
        stop = min([i for i in range(runs[0] + 1, len(lines)) if lines[i].lstrip().startswith("- name:") or (lines[i] and not lines[i].startswith(" "))] or [len(lines)])
        step = "\n".join(lines[start:stop])
        for weak in ("continue-on-error", "|| true", "|| :", "set +e", "if:"):
            self.assertNotIn(weak, step)
        self.assertIn("shell: bash", step)
        job = [l for l in lines[:start] if l.startswith("  ") and not l.startswith("   ") and l.rstrip().endswith(":")][-1]
        self.assertNotIn("continue-on-error", "\n".join(lines[lines.index(job):start]))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
