"""Issue 33 (83 side): the QC recipe in SKILL.md, run verbatim, yields a result `check` accepts.

The recipe is run as written (only the angle-bracket placeholders are filled and the optional `[--fab]` is left
out) inside the harness Skill 44's own `tests/test_qc_built_workflow.sh` uses: the real `qc-built-workflow.sh`
copied into a scratch tree, a stub `caf` that hands back a fixture export, and a stub approval verifier with
the real verifier's call shape. Nothing live is contacted. Exit 0 must save a QC file with `exit_code` 0, an
exit gate PASS and a PLAN MODE gate PASS, and Skill 83's `qc_violations` must accept that file.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core.check_rules import delivery_units as du  # noqa: E402

SKILL_44 = SKILL_ROOT.parent / "44-convert-and-flow-operator"
STEP = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split("3. **QC.**", 1)[1].split("4. **Receipt.**", 1)[0]
RECIPE = STEP.split("```")[1]
WORKFLOW = "WFTEST001"
HUMAN = "WF-1 WF-2 WF-8 WF-9 WF-10 WF-11 WF-13 WF-14 WF-16 WF-17 WF-19 WF-20".split()

VERIFIER = '''class ApprovalRefused(Exception):
    def __init__(self, code, message=""):
        super().__init__(code + ": " + message)
        self.code = code

def verify(approval_id, kind, plan_hash, scope, **kw):
    ok = {("appr-good-0001", "launch_plan_build"), ("appr-qc-0001", "qc_session")}
    if (approval_id, kind) not in ok or plan_hash != "abcd1234":
        raise ApprovalRefused("APPROVAL-NOT-FROM-AUTHORITY", "unknown approval")
    return {"ok": True}
'''
CAF = '#!/usr/bin/env bash\nwhile [ $# -gt 0 ]; do [ "$1" = "--out" ] && { cp "$QC_TEST_EXPORT" "$2"; exit 0; }; shift; done\nexit 1\n'
EXPORT = {"id": WORKFLOW, "name": "ZHC-test", "status": "draft", "allowMultiple": False, "active": False,
          "workflowData": {"templates": [
              {"id": "n1", "type": "add_contact_tag", "name": "Tag", "parentKey": None, "next": "n2",
               "attributes": {"tags": []}},  # no SMS step: WF-25 (WP-07) needs saved SMS conditions and the verifier tree
              {"id": "n2", "type": "wait", "name": "Wait 2 Days", "parentKey": "n1", "next": "n3",
               "attributes": {"type": "time", "startAfter": {"type": "days", "value": 2, "when": "after"}}},
              {"id": "n3", "type": "end", "name": "Finish", "parentKey": "n2"}]},
          "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "n1"}]}
SCHEDULE = {"waits": [{"kind": "delay", "value": 2, "unit": "days"}]}


def recipe_command() -> str:
    """The recipe's code block with only its placeholders filled; the optional `[--fab]` is left out."""
    text = RECIPE.replace(" [--fab]", "").replace("<workflow-id>", WORKFLOW).replace("<plan.json>", "plan.json") \
        .replace("<record.json>", "qc-session.json").replace("<grades.json>", "grades.json").replace("<schedule.json>", "schedule.json") \
        .replace("<deps.json>", "deps.json")
    assert not re.search(r"<[\w.-]+>|\[--", text), text
    return text


class QcRecipeRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cwd = self.root / "44-convert-and-flow-operator"
        self.cwd.mkdir()
        shutil.copy2(SKILL_44 / "qc-built-workflow.sh", self.cwd)
        (self.cwd / "tools").symlink_to(SKILL_44 / "tools")
        verifier = self.root / "shared-utils" / "signature_launch_contract" / "approval_record.py"
        verifier.parent.mkdir(parents=True)
        verifier.write_text(VERIFIER, encoding="utf-8")
        (self.root / "bin").mkdir()
        caf = self.root / "bin" / "caf"
        caf.write_text(CAF, encoding="utf-8")
        caf.chmod(0o755)
        (self.root / "home").mkdir()
        (self.root / "export.json").write_text(json.dumps(EXPORT), encoding="utf-8")
        self.write("plan.json", {"approval_id": "appr-good-0001", "plan_hash": "abcd1234", "publish_intent": "DRAFT",
                                 "re_entry": "ONCE", "build_model": "build-model-a"})
        self.write("grades.json", {"workflow_id": WORKFLOW, "grades": {
            item: {"grade": "PASS", "observed": "read from export"} for item in HUMAN}})
        self.write("schedule.json", SCHEDULE)
        self.write("deps.json", {})

    def write(self, name: str, doc) -> None:
        (self.cwd / name).write_text(json.dumps(doc), encoding="utf-8")

    def run_recipe(self, model: str = "qc-model-b") -> subprocess.CompletedProcess:
        # the QC model is not typed any more: the signed QC session record names it
        self.write("qc-session.json", {"approval_id": "appr-qc-0001", "plan_hash": "abcd1234",
                                       "qc_model": model, "session_id": "qc-sess-0001"})
        env = {"PATH": f"{self.root / 'bin'}:/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(self.root / "home"),
               "OPENCLAW_PLATFORM": "mac", "QC_TEST_EXPORT": str(self.root / "export.json")}
        return subprocess.run(["/bin/bash", "-c", recipe_command()], cwd=self.cwd, env=env,
                              capture_output=True, text=True, timeout=120)

    def saved(self) -> dict:
        return json.loads((self.cwd / f"qc-{WORKFLOW}.json").read_text(encoding="utf-8"))

    def violations(self) -> list:
        raw = (self.cwd / f"qc-{WORKFLOW}.json").read_bytes()
        artifact = {"path": f"qc-{WORKFLOW}.json", "sha256": hashlib.sha256(raw).hexdigest()}
        return du.qc_violations("unit 'u1'", WORKFLOW, [artifact], self.cwd)

    def test_the_recipe_run_verbatim_saves_a_passing_result_check_accepts(self):
        done = self.run_recipe()
        qc = self.saved()
        self.assertEqual(qc.get("exit_code"), 0, (done.stderr[-600:], qc))
        self.assertEqual(qc["plan_mode_gate"]["status"], "PASS", qc["plan_mode_gate"])
        self.assertEqual((qc["exit_gate"], qc["overall_mechanical"], qc["workflow_id"]), ("PASS", "PASS", WORKFLOW))
        self.assertEqual(self.violations(), [])

    def test_a_qc_model_equal_to_the_build_model_saves_a_result_check_refuses(self):
        self.run_recipe(model="build-model-a")
        qc = self.saved()
        self.assertNotEqual(qc.get("exit_code"), 0)
        self.assertEqual(qc["plan_mode_gate"]["status"], "FAIL")
        refusal = self.violations()
        self.assertEqual(len(refusal), 1, refusal)
        self.assertIn("QC did not pass", refusal[0])


if __name__ == "__main__":
    unittest.main()
