"""S44-33 / S44-47: the recipes in SKILL.md carry every flag the scripts demand for success.

An agent that follows a recipe verbatim must be running a command that CAN return 0 / write. The flags
below are the ones qc-built-workflow.sh and `workflows build --from-automation-build` refuse to run without.

Run: python3 -m pytest 44-convert-and-flow-operator/tests/test_skill_md_qc_recipe.py -q
"""
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8")
QC = (SKILL / "qc-built-workflow.sh").read_text(encoding="utf-8")
CLI = (SKILL / "tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py").read_text(encoding="utf-8")


def _block(starts_with):
    for block in re.findall(r"```bash\n(.*?)```", TEXT, re.S):
        if starts_with in block:
            return " ".join(block.replace("\\\n", " ").split())
    raise AssertionError("no recipe block containing %r in SKILL.md" % starts_with)


def test_qc_recipe_has_every_flag_the_script_needs_for_exit_zero():
    recipe = _block("./qc-built-workflow.sh")
    for flag in ("--plan-mode-file", "--qc-session", "--grades", "--deps", "--launch-schedule", "--json",
                 "--publish-intent", "--re-entry"):
        assert flag in recipe, flag
        assert re.search(r"^\s+%s\)" % re.escape(flag), QC, re.M), "%s is not a flag of the script" % flag
    assert "--qc-model" not in recipe


def test_qc_recipe_produces_the_schedule_it_consumes():
    recipe = _block("emit_launch_schedule.py")
    assert "--out schedule.json" in recipe and "--launch-schedule schedule.json" in recipe
    assert (SKILL / "automation-templates/launch-c/emit_launch_schedule.py").is_file()


def test_launch_build_recipe_carries_plan_mode_file():
    recipe = _block("workflows build")
    assert "--from-automation-build" in recipe and "--plan-mode-file" in recipe
    assert '"--plan-mode-file"' in CLI


def test_every_documented_build_command_in_83_skill_md_carries_plan_mode_file():
    text = (SKILL.parent / "83-black-friday-launcher/SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(text.replace("\\\n", " ").split())
    # each documented command: from `workflows build` to the closing backtick or code fence
    cmds = re.findall(r"workflows build\b[^`]*?--from-automation-build[^`]*", flat)
    assert cmds, "83 SKILL.md documents no workflows build --from-automation-build command"
    for cmd in cmds:
        assert "--plan-mode-file" in cmd, cmd


def test_instructions_qc_command_is_the_same_runnable_recipe():
    """INSTRUCTIONS.md Step 9.3 also hands the QC sub-agent a command; it must not drift to the refused flags."""
    text = (SKILL / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    blocks = [" ".join(b.replace("\\\n", " ").split()) for b in re.findall(r"```bash\n(.*?)```", text, re.S)
              if "./qc-built-workflow.sh" in b]
    assert blocks, "no qc-built-workflow.sh command block in INSTRUCTIONS.md"
    for recipe in blocks:
        for flag in ("--plan-mode-file", "--qc-session", "--grades", "--deps", "--json",
                     "--publish-intent", "--re-entry"):
            assert flag in recipe, flag
        assert "--qc-model" not in recipe


def test_skill_md_states_that_a_bare_qc_invocation_is_never_a_pass():
    flat = " ".join(TEXT.split())
    assert "a bare `./qc-built-workflow.sh <id>` is never a pass" in flat
    assert "(exit 1 for a failed gate, 2 for ungraded items)" in flat
