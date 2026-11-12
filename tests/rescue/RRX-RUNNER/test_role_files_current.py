#!/usr/bin/env python3
"""RRX-104b: the six role and procedure files name only the live tools.

A line may name `rescue_ledger.py` or `rescue_cc_board.py` only when that line
carries the word "drill", or when the line sits under a `###` heading whose text
contains DRILL TOOLING or HISTORICAL MIGRATION TOOLING (the clerk's drill and
migration sections). No line may carry the retired relay vocabulary. A file that
still mentions ~/.ssh/config must also say whose boxes it covers.

Run: python3 -m unittest tests/rescue/RRX-RUNNER/test_role_files_current.py
(direct execution also works: python3 test_role_files_current.py)
"""
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPARTMENT = (
    REPO_ROOT
    / "23-ai-workforce-blueprint"
    / "templates"
    / "role-library"
    / "rescue-rangers"
)

FILES = [
    DEPARTMENT / "diagnostician--rescue-rangers.md",
    DEPARTMENT / "structured-fix-operator--rescue-rangers.md",
    DEPARTMENT / "ticket-clerk--rescue-rangers.md",
    DEPARTMENT / "qc-postmortem-specialist--rescue-rangers.md",
    DEPARTMENT / "sops" / "SOP-RR-04-structured-fix-discipline.md",
    DEPARTMENT / "sops" / "SOP-RR-05-postmortem-and-prevention.md",
]

RETIRED_TOOLS = ("rescue_ledger.py", "rescue_cc_board.py")
ALLOWED_HEADINGS = ("DRILL TOOLING", "HISTORICAL MIGRATION TOOLING")
RETIRED_PHRASES = (
    "relay's `answer` action",
    'action:"pending"',
    'action:"status"',
)
SSH_COVERAGE = "Mac boxes only"


def lines_with_state(path):
    """Yield (line_number, line, under_allowed_heading) for one file."""
    allowed = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            allowed = line.startswith("###") and any(
                marker in heading for marker in ALLOWED_HEADINGS
            )
        yield number, line, allowed


class RoleFilesCurrentTest(unittest.TestCase):
    def test_the_six_files_exist(self):
        for path in FILES:
            self.assertTrue(path.is_file(), "missing file: %s" % path)

    def test_retired_tools_need_a_drill_line_or_a_drill_heading(self):
        offenders = []
        for path in FILES:
            for number, line, allowed in lines_with_state(path):
                if not any(tool in line for tool in RETIRED_TOOLS):
                    continue
                if "drill" in line.lower() or allowed:
                    continue
                offenders.append("%s:%d: %s" % (path.name, number, line.strip()))
        self.assertEqual(
            offenders,
            [],
            "retired tool named without drill context:\n" + "\n".join(offenders),
        )

    def test_no_retired_relay_vocabulary(self):
        offenders = []
        for path in FILES:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                for phrase in RETIRED_PHRASES:
                    if phrase in line:
                        offenders.append("%s:%d: %s" % (path.name, number, phrase))
        self.assertEqual(
            offenders,
            [],
            "retired relay vocabulary:\n" + "\n".join(offenders),
        )

    def test_ssh_config_is_never_the_roster(self):
        for path in FILES:
            text = path.read_text(encoding="utf-8")
            if "~/.ssh/config" in text:
                self.assertIn(
                    SSH_COVERAGE,
                    text,
                    "%s mentions ~/.ssh/config without '%s'" % (path.name, SSH_COVERAGE),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
