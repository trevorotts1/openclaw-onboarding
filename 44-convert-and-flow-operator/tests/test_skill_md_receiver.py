"""S44-82 (44 side): SKILL.md says the siglaunch receiver is not a production entry, everywhere.

SKILL.md used to say both that the receiver is "deliberately NOT a production entry" and that it
"validates the request, drives the governed build, reads back, issues a receipt". The code is the
tie-breaker: receiver.py sets PRODUCTION_ENTRY_ENABLED = False.

Run: python3 -m pytest 44-convert-and-flow-operator/tests/test_skill_md_receiver.py -q
"""
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TEXT = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())  # one line: wraps do not hide a phrase
RECEIVER = (SKILL / "tools" / "siglaunch" / "receiver" / "receiver.py").read_text(encoding="utf-8")


def test_the_code_says_the_receiver_is_not_a_production_entry():
    assert re.search(r"^PRODUCTION_ENTRY_ENABLED = False$", RECEIVER, re.M)


def test_skill_md_states_the_flag_value():
    assert "PRODUCTION_ENTRY_ENABLED = False" in TEXT


def test_skill_md_never_describes_the_receiver_as_driving_a_build():
    sentences = re.split(r"(?<=[.;])\s", TEXT)
    offenders = [s for s in sentences
                 if re.search(r"receiv", s, re.I)
                 and re.search(r"\bdrives?\b[^.;]{0,40}\bbuild|\bdriving\b[^.;]{0,40}\bbuild", s, re.I)]
    assert offenders == []


def test_skill_md_routes_the_automation_request_through_the_build_command():
    assert "caf workflows build --from-automation-build" in TEXT
    assert "receipt is the build journal" in TEXT
