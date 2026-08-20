"""Tests for the AF-C8 ARCHETYPE CARVE-OUT (value-stack / offer-stack slides).

THE RULING (operator/Trevor, doctrine reconciliation, 2026-08-20): AF-C8 (the
per-slide TOTAL on-slide word ceiling) gets an explicit ARCHETYPE CARVE-OUT
for value-stack / offer-stack slides:

    DEFAULT slides ............ 30 words max   (UNCHANGED)
    ARCHETYPE CARVE-OUT -- value-stack / offer-stack slides:
      headline ......... <= 9 words
      sub-copy ......... <= 18 words
      line items ....... <= 6 items x <= 7 words
      ceiling .......... 62 words

THE FAULT this reconciles (root cause, live run pres-wave-e-v3-1787240658,
2026-08-20): slide-copywriter.md's OWN hard limits already instruct "value
stack slides: maximum 6 line items ... 7 words per name" -- which, once a
9-word headline and an 18-word sub-copy are added (both also already
mandated by the same document), mechanically produces up to 62 on-slide
words. AF-C8 capped the SAME slide at a flat 30 with no archetype exception.
A fully SOP-compliant value-stack slide was mechanically guaranteed to fail
QC (that is the exact defect the real run's copy_qc_report.json recorded).

This ruling must be documented IDENTICALLY (same numbers, same wording) in
all three of:
  23-ai-workforce-blueprint/templates/role-library/presentations/slide-copywriter.md
  23-ai-workforce-blueprint/templates/role-library/presentations/sops/slide-copywriter-sops.md
  universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md

so the two doctrines can never drift apart again. AF-C8 has no mechanical
Python check anywhere in this codebase (it is graded by the QC Specialist
role reading slides_copy.md -- see test_af_c8_copy_contract.py's own docstring
in this same directory), so the "reference checker" below is a TEST-ONLY
implementation of the ruling's own arithmetic. It exists to prove two things
mechanically: (1) a fully compliant value-stack slide clears the carve-out
ceiling once the carve-out text is present in the doctrine; (2) an ordinary
teaching slide is held to the untouched default 30-word ceiling regardless --
the carve-out never leaks onto non-archetype slides.

The checker DERIVES its value-stack ceiling from the doctrine file's own text
(regex-parsed out of the ARCHETYPE CARVE-OUT block) rather than hardcoding
62, so that reverting the doctrine edit (no carve-out block present) makes
the checker fall back to the DEFAULT 30-word ceiling for every archetype --
this is what makes the compliant-value-stack-slide test RED before the fix
and GREEN after it.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_af_c8_copy_contract.py, test_dispatcher_autospawn.py).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

# Same walk-up resolution every sibling test in this directory uses
# (test_dispatcher_autospawn.py._canonical_manifest_path,
# test_presentation_job.py._canonical_manifest, et al.) -- walk up from
# SCRIPTS looking for the universal-sops/presentation-slide-craft/ doctrine
# home, capped at 12 hops so a broken layout fails loudly instead of
# scanning the whole filesystem.
def _find_repo_file(rel_path: str) -> Path:
    deployed = SCRIPTS.parent / "sops" / Path(rel_path).name
    if deployed.is_file() and "sops/" in rel_path:
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / rel_path
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        f"{rel_path} not found walking up from {SCRIPTS} "
        "(universal-sops/presentation-slide-craft walk-up)"
    )


MASTER_RULESET_REL = "universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md"
SLIDE_COPYWRITER_REL = "23-ai-workforce-blueprint/templates/role-library/presentations/slide-copywriter.md"
SLIDE_COPYWRITER_SOPS_REL = "23-ai-workforce-blueprint/templates/role-library/presentations/sops/slide-copywriter-sops.md"

DEFAULT_CEILING = 30
DEFAULT_HEADLINE_MAX = 9
DEFAULT_SUBCOPY_MAX = 18
DEFAULT_ITEM_COUNT_MAX = 6
DEFAULT_ITEM_WORDS_MAX = 7

_CARVEOUT_BLOCK_RE = re.compile(
    r"ARCHETYPE CARVE-OUT.*?ceiling\s*\.+\s*(\d+)\s*words",
    re.IGNORECASE | re.DOTALL,
)


def _word_count(text: str) -> int:
    return len(text.split())


class _AfC8Checker:
    """TEST-ONLY reference implementation of the AF-C8 doctrine, parsed live
    from MASTER-QC-AUTOFAIL-RULESET.md so this test cannot pass by simply
    hardcoding the post-fix numbers -- it reflects whatever the doctrine file
    on disk actually says right now."""

    def __init__(self, doctrine_text: str):
        self.doctrine_text = doctrine_text
        match = _CARVEOUT_BLOCK_RE.search(doctrine_text)
        self.carveout_ceiling = int(match.group(1)) if match else None

    def ceiling_for(self, archetype: str) -> int:
        if archetype in ("value-stack", "offer-stack") and self.carveout_ceiling is not None:
            return self.carveout_ceiling
        return DEFAULT_CEILING

    def check_value_stack_slide(self, headline: str, subcopy: str, items: list[str]) -> bool:
        """Returns True (PASS) only if every per-field sub-limit AND the
        archetype's total ceiling are satisfied."""
        if _word_count(headline) > DEFAULT_HEADLINE_MAX:
            return False
        if _word_count(subcopy) > DEFAULT_SUBCOPY_MAX:
            return False
        if len(items) > DEFAULT_ITEM_COUNT_MAX:
            return False
        if any(_word_count(item) > DEFAULT_ITEM_WORDS_MAX for item in items):
            return False
        total = _word_count(headline) + _word_count(subcopy) + sum(_word_count(i) for i in items)
        return total <= self.ceiling_for("value-stack")

    def check_default_slide(self, *fields: str) -> bool:
        total = sum(_word_count(f) for f in fields)
        return total <= self.ceiling_for("default")


@pytest.fixture()
def master_ruleset_text() -> str:
    return _find_repo_file(MASTER_RULESET_REL).read_text(encoding="utf-8")


@pytest.fixture()
def checker(master_ruleset_text: str) -> _AfC8Checker:
    return _AfC8Checker(master_ruleset_text)


# ---------------------------------------------------------------------------
# Doctrine-text assertions: the carve-out's own numbers, present verbatim.
# ---------------------------------------------------------------------------
class TestArchetypeCarveoutDoctrineText:
    def test_master_ruleset_states_the_af_c8_code(self, master_ruleset_text):
        assert "AF-C8" in master_ruleset_text

    def test_master_ruleset_names_the_carveout(self, master_ruleset_text):
        assert "ARCHETYPE CARVE-OUT" in master_ruleset_text

    def test_default_ceiling_stated_unchanged_at_30(self, master_ruleset_text):
        assert re.search(r"30 words max", master_ruleset_text)
        assert "UNCHANGED" in master_ruleset_text

    def test_carveout_headline_ceiling_is_9(self, master_ruleset_text):
        assert re.search(r"headline\s*\.+\s*<=\s*9\s*words", master_ruleset_text)

    def test_carveout_subcopy_ceiling_is_18(self, master_ruleset_text):
        assert re.search(r"sub-copy\s*\.+\s*<=\s*18\s*words", master_ruleset_text)

    def test_carveout_line_items_are_6x7(self, master_ruleset_text):
        assert re.search(
            r"line items\s*\.+\s*<=\s*6\s*items\s*x\s*<=\s*7\s*words",
            master_ruleset_text,
        )

    def test_carveout_total_ceiling_is_62(self, master_ruleset_text):
        checker = _AfC8Checker(master_ruleset_text)
        assert checker.carveout_ceiling == 62

    def test_carveout_scoped_to_value_stack_offer_stack_only(self, master_ruleset_text):
        assert "ONLY to the value-stack / offer-stack archetype" in master_ruleset_text

    def test_carveout_does_not_authorize_raising_the_default(self, master_ruleset_text):
        assert "Do not raise the default 30-word cap" in master_ruleset_text


# ---------------------------------------------------------------------------
# Identical documentation across all three files Trevor named.
# ---------------------------------------------------------------------------
class TestCarveoutDocumentedIdenticallyAcrossAllThreeFiles:
    def _carveout_numbers_block(self, text: str) -> str:
        # Anchor on the fenced-block's own first line (lowercase
        # "value-stack / offer-stack slides:" with a trailing colon) rather
        # than on either file's differently-worded prose HEADING ("**AF-C8
        # ARCHETYPE CARVE-OUT (value-stack / offer-stack slides).**" in the
        # two role files vs "## AF-C8 ARCHETYPE CARVE-OUT — Value-Stack /
        # Offer-Stack Slides" in the ruleset file) -- only the fenced numbers
        # block itself is required to be byte-identical across all three.
        match = re.search(
            r"ARCHETYPE CARVE-OUT — value-stack / offer-stack slides:.*?"
            r"ceiling\s*\.+\s*\d+\s*words",
            text, re.DOTALL,
        )
        assert match, "ARCHETYPE CARVE-OUT numbers block not found"
        # Normalize whitespace/indentation so list-nested copies (which must
        # be markdown-indented under a numbered list item) compare equal to
        # the un-nested copy in MASTER-QC-AUTOFAIL-RULESET.md.
        return "\n".join(line.strip() for line in match.group(0).splitlines())

    def test_all_three_files_carry_the_identical_numbers_block(self):
        texts = {
            rel: _find_repo_file(rel).read_text(encoding="utf-8")
            for rel in (MASTER_RULESET_REL, SLIDE_COPYWRITER_REL, SLIDE_COPYWRITER_SOPS_REL)
        }
        normalized = {rel: self._carveout_numbers_block(t) for rel, t in texts.items()}
        blocks = list(normalized.values())
        assert blocks[0] == blocks[1] == blocks[2], normalized

    def test_all_three_files_carry_the_identical_scope_sentence(self):
        sentence = (
            "Do not weaken the offer stack. Do not raise the default "
            "30-word cap on ordinary teaching slides. The carve-out "
            "applies ONLY to the value-stack / offer-stack archetype."
        )
        for rel in (MASTER_RULESET_REL, SLIDE_COPYWRITER_REL, SLIDE_COPYWRITER_SOPS_REL):
            text = _find_repo_file(rel).read_text(encoding="utf-8")
            assert sentence in text, f"{rel} missing identical scope sentence"


# ---------------------------------------------------------------------------
# Mechanical proof: the ruling's own numbers are internally consistent.
# ---------------------------------------------------------------------------
class TestArchetypeCarveoutAppliedToFixtureSlides:
    def test_compliant_value_stack_slide_passes(self, checker):
        headline = "Here Is Everything Included In Your Complete Package Today"  # 9 words
        assert _word_count(headline) == 9
        subcopy = (
            "This full stack gives you the exact tools training support "
            "and accountability you need to win right now"
        )  # 18 words
        assert _word_count(subcopy) == 18
        items = [
            "Weekly Live Coaching Calls, $2000 value",       # 6
            "Private Community Access, $500 value today",    # 6
            "Done For You Templates, $1000 value",            # 6
            "Monthly Strategy Session, $750 value",           # 5
            "Bonus Swipe File Library, $300 value",           # 6
            "Lifetime Updates And Support, $1500 value",      # 6
        ]
        assert len(items) == 6
        assert all(_word_count(i) <= 7 for i in items)
        total = _word_count(headline) + _word_count(subcopy) + sum(_word_count(i) for i in items)
        assert total == 62, f"fixture must land exactly on the 62-word ceiling boundary, got {total}"

        assert checker.check_value_stack_slide(headline, subcopy, items) is True

    def test_ordinary_teaching_slide_at_62_words_still_fails(self, checker):
        headline = "Why Most Small Businesses Never Escape The Owner Trap"  # 9 words
        subcopy = (
            "You are not lazy or undisciplined, you are running a system "
            "that was never designed to run without you in every single seat"
        )  # 24 words on purpose -- combined with headline this alone already exceeds 30
        body = (
            "Every hour you spend doing instead of directing is an hour "
            "your business cannot grow, cannot scale, and cannot survive "
            "without you standing in the exact same spot tomorrow always"
        )  # remaining words to reach 62 total
        total = _word_count(headline) + _word_count(subcopy) + _word_count(body)
        assert total == 62, f"fixture must land exactly on 62 words, got {total}"

        assert checker.check_default_slide(headline, subcopy, body) is False
        # The default ceiling itself must remain exactly 30 -- proves the
        # carve-out never leaked onto the default archetype.
        assert checker.ceiling_for("default") == 30
