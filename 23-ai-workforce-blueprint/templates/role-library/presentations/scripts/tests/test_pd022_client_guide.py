"""PD-022 -- the owner-facing Presentations guide stays a CLIENT document.

WHY THIS FILE EXISTS
--------------------
`how-to-use-this-department.md` is read by non-technical owners, and it is
rendered from developer material: role-file identity sentences, a
suggested-roles "Department Purpose" paragraph written for an engineer, and a
generator appendix of AUTO-FAIL codes. The rendered guide therefore shipped
mid-sentence fragments ("... every deck run has."), the operator's own brand
name instead of the company, `AF-` codes, `.py` paths, and an appendix of build
rules no owner can act on.

The contract this test holds (PD-022 acceptance rows, verbatim):
  "regenerate for a fixture company named `Example Co`; the output contains no
   sentence that ends without a period in the specialist table, no occurrence of
   a hard-coded brand name, no `AF-` code, no `.py`; the specialist count equals
   the roster count."

It renders the guide in memory for the fixture company, so it tests the
generator, not a committed artifact that could have been hand-edited.
"""
import importlib.util
import pathlib
import re

HERE = pathlib.Path(__file__).resolve()
DEPT = HERE.parents[2]           # .../role-library/presentations
LIB = DEPT.parent                # .../role-library
SKILL = LIB.parents[1]           # .../23-ai-workforce-blueprint
GENERATOR = SKILL / "scripts" / "how_to_use_department.py"


def _load_generator():
    if not GENERATOR.is_file():
        return None
    spec = importlib.util.spec_from_file_location("htu_pd022", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


htu = _load_generator()


def _roster_specialist_count():
    """Count the client-facing specialists in the department's own roster table.

    A roster row is client-facing when its type column is `specialist` or
    `strategist`; the director, the QC roles, deep research, the on-call
    challenger and the healer are not things an owner asks for by name.
    """
    roster = DEPT / "00-START-HERE.md"
    rows = re.findall(
        r"^\|\s*[A-Z]+-[0-9A-Za-z]+\s*\|\s*([a-z0-9-]+)\s*\|\s*([a-z-]+)\s*\|",
        roster.read_text(encoding="utf-8"), re.M)
    return sum(1 for _slug, rtype in rows if rtype in ("specialist", "strategist"))


def _fixture_guide():
    assert htu is not None, f"generator not found at {GENERATOR}"
    return htu.render_how_to_use(
        "presentations",
        tokens={"COMPANY_NAME": "Example Co", "GENERATION_DATE": "2026-11-13"})


def _table_cells(guide):
    return re.findall(r"^\| \*\*(.+?)\*\* \| (.+?) \|$", guide, re.M)


def test_every_specialist_cell_is_a_complete_sentence():
    guide = _fixture_guide()
    cells = _table_cells(guide)
    assert cells, "no specialist table rows rendered -- the scanner proved nothing"

    broken = []
    for name, what in cells:
        if not what.rstrip().endswith((".", "!", "?")):
            broken.append(f"{name}: no terminal punctuation -> {what!r}")
        if what.count("(") != what.count(")"):
            broken.append(f"{name}: unbalanced parentheses -> {what!r}")
    assert not broken, "specialist table cells are not complete sentences:\n  " + \
        "\n  ".join(broken)


def test_no_brand_codes_or_code_paths_in_the_guide():
    guide = _fixture_guide()
    assert "BlackCEO" not in guide, "hard-coded brand name in the client guide"
    assert "AF-" not in guide, "developer AUTO-FAIL code in the client guide"
    assert ".py" not in guide, "code-file path in the client guide"
    # The moved developer sections must not come back through the generator.
    assert "Canonical Entry Command" not in guide
    assert "AF-CANONICAL-RENDER-BYPASS" not in guide


def test_what_to_say_opener_is_exact():
    guide = _fixture_guide()
    expected = (
        'Say: "I need a presentation." I will ask a few questions, one at a '
        "time. You will pick a look from 3 samples. Then I build it and send "
        "it to you.")
    assert "## What to say" in guide, "missing the 'What to say' section"
    assert expected in guide, "the 'What to say' wording drifted from the spec"
    # Top of the guide: the opener precedes Section 1.
    assert guide.index("## What to say") < guide.index("## 1."), \
        "'What to say' is not at the top of the guide"


def test_specialist_count_equals_roster_count():
    guide = _fixture_guide()
    assert len(_table_cells(guide)) == _roster_specialist_count()


def test_company_token_is_the_only_company_name():
    guide = _fixture_guide()
    assert "Example Co" in guide, "fixture company name never reached the guide"
    assert "{{COMPANY_NAME}}" not in guide, "unfilled company token"
