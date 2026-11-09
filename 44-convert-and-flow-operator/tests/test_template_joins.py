"""Fail the suite if any template graph loses its branch joins.

`automation-templates/_schema/check_joins.py` existed but nothing called it, so
a template could regress with every test still green. This is its caller.

Note on the negative control: the checker takes no path argument — it scans the
templates directory it lives beside. So the control runs against a throwaway
COPY of that directory, never the real one. An earlier version of this test
passed because argparse rejected an extra argument (rc=2), which proved nothing.
"""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

SKILL = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "automation-templates"
CHECKER_REL = pathlib.Path("_schema") / "check_joins.py"


def _run(cwd):
    return subprocess.run(
        [sys.executable, str(cwd / CHECKER_REL), "--check"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def test_join_checker_exists():
    assert (TEMPLATES / CHECKER_REL).is_file(), "join checker missing"


def test_every_template_graph_has_valid_joins():
    """The real gate: the shipped templates must have zero join violations."""
    result = _run(TEMPLATES)
    assert result.returncode == 0, (
        "check_joins.py --check failed (rc=%d)\nstdout:\n%s\nstderr:\n%s"
        % (result.returncode, result.stdout, result.stderr)
    )
    assert "violations=0" in result.stdout, result.stdout


def test_join_checker_rejects_a_branch_body_owned_twice(tmp_path):
    """Positive control: the rule the checker DOES implement must bite."""
    copy = tmp_path / "templates"
    shutil.copytree(TEMPLATES, copy)
    (copy / "launch-a" / "zz_bad_dual_owner.json").write_text(
        json.dumps(
            {
                "id": "zz_bad_dual_owner",
                "build_graph": [
                    {"id": "trg", "type": "trigger"},
                    {"id": "if1", "type": "if_else", "after": "trg",
                     "branches": {"true": "a1", "false": "shared"}},
                    {"id": "if2", "type": "if_else", "after": "a1",
                     "branches": {"true": "b1", "false": "shared"}},
                    {"id": "a1", "type": "wait", "after": "if1"},
                    {"id": "b1", "type": "wait", "after": "if2"},
                    {"id": "shared", "type": "wait",
                     "after": ["if1", "if2"]},
                ],
            }
        )
    )
    result = _run(copy)
    assert result.returncode != 0, (
        "checker accepted a node owned by two branch nodes without a declared join; "
        "stdout:\n%s" % result.stdout
    )


def test_join_checker_flags_a_dead_ending_arm(tmp_path):
    """Control: an arm that neither reaches a declared join nor ends at a
    workflow_goal must be rejected.

    The checker's actual rule (check_joins.py): every arm of an if_else must
    either reach a declared join, or have all of its terminals be
    `workflow_goal`. That rule is what makes a legitimate terminal-vs-continue
    branch (one arm ends at a goal, the other continues to a join) pass while a
    real dead-end fails. An earlier version of this test asserted the opposite
    and passed for the wrong reason.
    """
    copy = tmp_path / "templates"
    shutil.copytree(TEMPLATES, copy)
    (copy / "launch-a" / "zz_bad_one_arm.json").write_text(
        json.dumps(
            {
                "id": "zz_bad_one_arm",
                "build_graph": [
                    {"id": "trg", "type": "trigger"},
                    {"id": "if1", "type": "if_else", "after": "trg",
                     "branches": {"true": "a1", "false": "b1"}},
                    {"id": "a1", "type": "wait", "after": "if1"},
                    {"id": "b1", "type": "wait", "after": "if1"},
                    {"id": "cont", "type": "email", "after": "b1"},
                ],
            }
        )
    )
    result = _run(copy)
    assert result.returncode != 0, (
        "checker accepted an arm that dead-ends on a non-goal node; stdout:\n%s"
        % result.stdout
    )
    assert "dead-ends without a workflow_goal" in result.stdout, result.stdout

