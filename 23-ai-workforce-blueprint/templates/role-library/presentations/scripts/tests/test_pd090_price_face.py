"""PD-090: AF-PRICE-FACE must not be both passable and failable on one slide.

THE FAULT. The rule carried two exceptions -- (a) a price-ladder DROP slide and
(b) the re-pitch value-stack where price is the running total -- and then, in
the same row, an "always an auto-fail regardless of slide type" list whose item
(a) banned a per-component dollar value and whose item (b) banned a
"Total Value So Far: $X" tally. A DROP slide and a value-stack/tally slide were
therefore required by the exceptions and banned by the always-fail list at the
same time: no copy could pass both halves of one rule.

THE FIX. The two exceptions are replaced by one class list (ANCHOR, DROP1,
DROP2, DROP3, FINAL, VALUE_STACK, TALLY, RE_PITCH, the value-gap slide, the
callback slide, and component cards listed in offer_stack.json components[]),
and the always-fail list keeps only clause (c), the undeclared-figure clause.

WHAT THIS PROVES. Two sections state this rule: the role file's Vision-Gate
summary row and the sops/ mirror's full definition. This test reads both and
asserts that no slide class the rule authorizes is banned by either section,
that the two retired exceptions are gone, and that always-fail clauses (a) and
(b) are gone while (c) survives. It is the acceptance checker for PD-090; it
does not score a deck.
"""
from __future__ import annotations

from pathlib import Path

ROLE_REL = "qc-specialist-presentations.md"
MIRROR_REL = Path("sops") / "qc-specialist-presentations-sops.md"

# The class list, in the order the rule states it. Every one of these is
# authorized to carry dollar figures that reconcile to price_ladder.json or
# offer_stack.json.
AUTHORIZED_CLASSES = (
    "ANCHOR",
    "DROP1",
    "DROP2",
    "DROP3",
    "FINAL",
    "VALUE_STACK",
    "TALLY",
    "RE_PITCH",
    "value-gap",
    "callback",
    "component card",
)

# Wording that, if present in a banning context, re-creates the overlap this
# unit removes. The always-fail list may not name any of these.
RETIRED_ALWAYS_FAIL_WORDING = (
    "per-component dollar value",
    "Total Value So Far",
    "non-tally slide",
)

# The two retired exceptions. Neither may survive as an exception.
RETIRED_EXCEPTIONS = (
    "the slide is a price-ladder DROP slide",
    "the slide is the re-pitch value-stack where price is the running total",
)


def _presentations_dir() -> Path:
    """Walk up from this test file to the presentations/ directory.

    Written as a walk rather than a fixed parent index so the test survives the
    folder moving a level; an empty result means the two sections cannot be
    found, and every assertion below fails rather than silently passing.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / ROLE_REL).is_file() and (parent / MIRROR_REL).is_file():
            return parent
    raise AssertionError(
        "PD-090: could not locate %s and %s above %s"
        % (ROLE_REL, MIRROR_REL, Path(__file__).resolve())
    )


def _price_face_row(path: Path) -> str:
    """Return the AF-PRICE-FACE table row text from one procedure file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| AF-PRICE-FACE |"):
            return stripped
    raise AssertionError("PD-090: no AF-PRICE-FACE row in %s" % path)


def _unless_clause(row: str) -> str:
    """The authorized-class clause: from 'auto-fails unless' to its full stop."""
    marker = "auto-fails unless"
    start = row.find(marker)
    assert start != -1, "PD-090: the rule no longer states an 'auto-fails unless' scope"
    clause = row[start + len(marker):]
    end = clause.find("On those slides every dollar figure")
    assert end != -1, (
        "PD-090: the authorized-class clause is not closed by the "
        "'On those slides every dollar figure' sentence"
    )
    return clause[:end]


def _always_fail_clause(row: str) -> str:
    """The always-an-auto-fail list: from its marker to the sanctioned-price line."""
    start = row.find("always an auto-fail regardless of slide type")
    assert start != -1, "PD-090: the always-fail list is missing from the rule"
    end = row.find("The SINGLE sanctioned price")
    assert end != -1, "PD-090: the sanctioned-price sentence is missing from the rule"
    return row[start:end]


def test_both_sections_are_present_and_parse():
    dept = _presentations_dir()
    mirror_row = _price_face_row(dept / MIRROR_REL)
    role_row = _price_face_row(dept / ROLE_REL)
    assert "AF-PRICE-FACE" in mirror_row
    assert "AF-PRICE-FACE" in role_row
    assert mirror_row != role_row, "the summary row and the full definition are the same text"


def test_mirror_authorizes_every_class_in_the_one_clause():
    row = _price_face_row(_presentations_dir() / MIRROR_REL)
    clause = _unless_clause(row)
    missing = [name for name in AUTHORIZED_CLASSES if name not in clause]
    assert not missing, (
        "PD-090: authorized slide classes absent from the rule's one clause: %s"
        % ", ".join(missing)
    )
    assert "arc_allocation.json" in clause, (
        "PD-090: the clause must say where the class tags are read from"
    )
    assert "offer_stack.json components[]" in clause, (
        "PD-090: the clause must say where a component card is listed"
    )


def test_mirror_reconciles_every_authorized_figure_to_a_declared_source():
    row = _price_face_row(_presentations_dir() / MIRROR_REL)
    start = row.find("On those slides every dollar figure")
    assert start != -1, "PD-090: the reconciliation sentence is missing"
    sentence = row[start:row.find("Any of the following", start)]
    assert "must equal a figure in price_ladder.json or offer_stack.json" in sentence, (
        "PD-090: authorized figures must reconcile to price_ladder.json or offer_stack.json"
    )


def test_mirror_drops_both_retired_exceptions():
    clause = _unless_clause(_price_face_row(_presentations_dir() / MIRROR_REL))
    survivors = [text for text in RETIRED_EXCEPTIONS if text in clause]
    assert not survivors, (
        "PD-090: the retired exceptions are still in the rule: %s" % "; ".join(survivors)
    )


def test_mirror_drops_always_fail_a_and_b_and_keeps_c():
    always = _always_fail_clause(_price_face_row(_presentations_dir() / MIRROR_REL))
    survivors = [text for text in RETIRED_ALWAYS_FAIL_WORDING if text in always]
    assert not survivors, (
        "PD-090: always-fail clauses (a) or (b) survive: %s" % "; ".join(survivors)
    )
    assert "(c) any dollar value on the face not declared in price_ladder.json" in always, (
        "PD-090: always-fail clause (c) was not kept"
    )


def test_role_summary_does_not_ban_the_classes_the_rule_authorizes():
    role_row = _price_face_row(_presentations_dir() / ROLE_REL)
    assert "Unauthorized per-item dollar values" not in role_row, (
        "PD-090: the summary row still bans per-item dollar values as a class"
    )
    assert "multiple prices on the offer face" not in role_row, (
        "PD-090: the summary row still bans multiple prices on the offer face"
    )


def test_role_summary_names_the_same_authorized_classes():
    role_row = _price_face_row(_presentations_dir() / ROLE_REL)
    for family in ("value-stack", "tally", "re-pitch", "value-gap", "callback", "component-card"):
        assert family in role_row, (
            "PD-090: the summary row does not name the authorized class family %r, so the two "
            "sections no longer describe the same rule" % family
        )


def test_no_authorized_class_is_banned_by_either_section():
    """The acceptance invariant: no class required by one section, banned by the other."""
    dept = _presentations_dir()
    mirror_row = _price_face_row(dept / MIRROR_REL)
    role_row = _price_face_row(dept / ROLE_REL)
    always = _always_fail_clause(mirror_row)

    bans = {
        "mirror always-fail list": [t for t in RETIRED_ALWAYS_FAIL_WORDING if t in always],
        "role summary row": [
            t
            for t in ("Unauthorized per-item dollar values", "multiple prices on the offer face")
            if t in role_row
        ],
        "mirror exception list": [t for t in RETIRED_EXCEPTIONS if t in _unless_clause(mirror_row)],
    }
    offenders = {where: hits for where, hits in bans.items() if hits}
    assert not offenders, (
        "PD-090: a slide class is authorized by one section and banned by the other: %s"
        % offenders
    )
