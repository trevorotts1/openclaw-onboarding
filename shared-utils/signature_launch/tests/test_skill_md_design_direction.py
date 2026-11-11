"""Skills 78 to 82 state where their design direction comes from (fix spec M4 / issue 9).

Until now none of the five page skills named Skill 45, and the one design input they take
(design-prose.json) had no producer. Each SKILL.md now carries the same sentence, and the producer it
names exists and writes the sha-bearing file the consumers check. A skill that drops the sentence, or a
producer that loses its CLI, fails here.

Run from the repository root:
    python3 -m pytest shared-utils/signature_launch/tests/test_skill_md_design_direction.py -q
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SENTENCE = "Design direction = Skill 71 structure + Skill 45 card/rules via `design_prose.py`."
SKILLS = ("78-signature-product-selection", "79-signature-order-form", "80-signature-upsell",
          "81-signature-downsell", "82-signature-thank-you")


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_md_names_where_its_design_direction_comes_from(skill):
    text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
    assert SENTENCE in text, f"{skill}/SKILL.md lost the Skill 45 design-direction sentence"
    assert "design_prose.check_design_prose" in text
    assert "Skill 45 is only read, never written" in text


def test_the_producer_the_sentence_names_exists_with_its_cli():
    producer = ROOT / "shared-utils" / "signature_launch" / "design_prose.py"
    text = producer.read_text(encoding="utf-8")
    for flag in ("--launch", "--style", "--card", "--out"):
        assert flag in text
    assert "def check_design_prose" in text
