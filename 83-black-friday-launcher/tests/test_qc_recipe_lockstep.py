"""Issue 33 (83 side): the QC recipe in SKILL.md stays in lockstep with what `check` enforces.

SKILL.md (Launch mode, step 3) tells the operator the one command that can exit 0 and the line that saves the
script's own exit status as `exit_code`. `check_rules/delivery_units.py` refuses an automation whose saved QC
result does not carry `exit_code` 0. If the recipe loses a flag, loses the exit_code line, or names another
refusal code, an operator following it saves a QC file `check` refuses (or none at all). These tests read the
recipe text and pin it.

Every flag the recipe passes must be one the in-tree Skill 44 `qc-built-workflow.sh` accepts. The model flag is
read from that script, not frozen here: today it is `--qc-model`; when Skill 44's QC gates land (WP-07) the script
refuses `--qc-model` and takes `--qc-session <record.json>`, and this test turns red until the recipe in SKILL.md
(Launch mode, step 3, the `--qc-model <model>` line) is changed to match.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core.check_rules import delivery_units as du  # noqa: E402

SKILL_MD = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
STEP = SKILL_MD.split("3. **QC.**", 1)[1].split("4. **Receipt.**", 1)[0]
FENCE = STEP.split("```")[1]                      # the recipe's code block
FLAT = FENCE.replace("\\\n", " ")                 # shell line continuations joined
COMMAND = next(line for line in FLAT.splitlines() if "qc-built-workflow.sh" in line)
TOKENS = COMMAND.replace(";", " ").split()
QC_SCRIPT = SKILL_ROOT.parent / "44-convert-and-flow-operator" / "qc-built-workflow.sh"


def accepted_flags(script: str) -> set:
    """Flags the script's option loop accepts: a `--flag)` case arm that does not refuse (REFUSED, or exit)."""
    return {flag for flag, body in re.findall(r"^\s*(--[\w-]+)\)\s*(.*)$", script, re.M)
            if "REFUSED" not in body and not re.search(r"\bexit\b", body)}


class QcRecipeLockstepTests(unittest.TestCase):
    def test_the_recipe_runs_the_qc_script_on_the_workflow_id(self):
        self.assertEqual(TOKENS[:2], ["./qc-built-workflow.sh", "<workflow-id>"], TOKENS)

    def test_the_recipe_carries_each_flag_the_script_needs_to_exit_zero(self):
        for flag in ("--json", "--launch"):
            with self.subTest(flag=flag):
                self.assertIn(flag, TOKENS)
        for flag, value in (("--plan-mode-file", "<plan.json>"), ("--grades", "<grades.json>"),
                            ("--launch-schedule", "<schedule.json>")):
            with self.subTest(flag=flag):
                self.assertIn(flag, TOKENS)
                self.assertEqual(TOKENS[TOKENS.index(flag) + 1], value)

    def test_the_recipe_carries_the_dependency_manifest_the_script_needs_to_exit_zero(self):
        self.assertEqual(TOKENS[TOKENS.index("--deps") + 1], "<deps.json>")

    def test_every_flag_the_recipe_passes_is_one_the_qc_script_accepts(self):
        accepted = accepted_flags(QC_SCRIPT.read_text(encoding="utf-8"))
        self.assertIn("--json", accepted)                      # the reader finds the option loop
        for flag in re.findall(r"--[\w-]+", COMMAND):
            with self.subTest(flag=flag):
                self.assertIn(flag, accepted)

    def test_the_model_flag_is_the_one_the_qc_script_accepts_with_its_value_placeholder(self):
        accepted = accepted_flags(QC_SCRIPT.read_text(encoding="utf-8"))
        model_flags = [t for t in TOKENS if t in ("--qc-model", "--qc-session")]
        self.assertEqual(len(model_flags), 1, TOKENS)
        self.assertIn(model_flags[0], accepted)
        self.assertEqual(TOKENS[TOKENS.index(model_flags[0]) + 1], {"--qc-model": "<model>",
                                                                   "--qc-session": "<record.json>"}[model_flags[0]])

    def test_a_flag_the_script_refuses_is_not_accepted(self):
        refusing = ('    --qc-session)     QC_SESSION_FILE="${2:-}"; shift 2 ;;\n'
                    '    --qc-model)       echo "REFUSED: --qc-model is a self-reported string" >&2; exit 2 ;;\n'
                    '    -*)               echo "Unknown option: $1" >&2; exit 2 ;;\n')
        self.assertEqual(accepted_flags(refusing), {"--qc-session"})
        self.assertEqual(accepted_flags('    --qc-model)       QC_MODEL="${2:-}"; shift 2 ;;\n'), {"--qc-model"})
        # either mark alone is a refusal: a message with no exit, or an exit with no message
        self.assertEqual(accepted_flags('    --a)  echo "REFUSED: no" >&2 ;;\n    --b)  exit 2 ;;\n    --c)  X=1; shift 2 ;;\n'),
                         {"--c"})
        self.assertEqual(accepted_flags('    --d is only mentioned in prose\n'), set())     # not a case arm

    def test_the_recipe_saves_the_qc_result_the_check_reads(self):
        self.assertIn("> qc-<workflow-id>.json", COMMAND)
        self.assertIn("rc=$?", COMMAND)

    def test_the_recipe_adds_the_scripts_exit_status_as_exit_code(self):
        self.assertIn('d["exit_code"]=rc', FENCE)
        self.assertIn('qc-<workflow-id>.json "$rc"', FENCE)

    def test_the_prose_names_exit_code_zero_and_the_refusal_code_check_uses(self):
        self.assertRegex(STEP, r"`exit_code` 0")
        self.assertRegex(STEP, r"(?<![\w-])" + re.escape(du.CODE_AUTOMATION) + r"(?![\w-])")
        self.assertEqual(du.QC_REQUIRED[0], ("exit_code", 0))

    def test_the_prose_names_the_schedule_file_the_recipe_needs(self):
        self.assertIn("emit_launch_schedule.py", STEP)
        self.assertRegex(STEP, r'\{"waits": \[\.\.\.\]\}')


if __name__ == "__main__":
    unittest.main()
