"""design-prose.json has a producer (fix spec M4 / issue 9, decision D-F).

design_prose.py composes Skill 71's page structure, Skill 45's style card LONG tier and the page
category rules into the file Skill 71's request builder reads, and records the sha256 of every
Skill 45 file it read. check_design_prose refuses a hand-typed, edited or stale file.

Run from the repository root:
    python3 -m pytest shared-utils/signature_launch/tests/test_design_prose.py -q
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "shared-utils" / "signature_launch"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dp = _load("signature_launch_design_prose", DIR / "design_prose.py")
di = dp._di()

LONG_TIER = "Style: bold cinematic gold.\nDo not place text over any face."
LAUNCH = {"tenant_id": "t", "location_id": "l", "launch_id": "launch-1", "revision": 1,
          "journey_mode": "single_simple",
          "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": False}}


@pytest.fixture()
def library(tmp_path):
    lib = tmp_path / "library"
    (lib / "_system").mkdir(parents=True)
    (lib / "funnel-page-designs").mkdir()
    (lib / "INDEX.md").write_text(
        "| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |\n|---|---|---|---|---|---|---|---|\n"
        "| 1 | FN-001 | T | s | production | v1.0 | 2026-11-10 | funnel-page-designs/FN-001.md |\n", encoding="utf-8")
    (lib / "funnel-page-designs" / "FN-001.md").write_text(
        f"# FN-001\n\n### LONG (<=19,000 chars)\n```\n{LONG_TIER}\n```\n", encoding="utf-8")
    (lib / "funnel-page-designs" / "_RULES.md").write_text("# rules\nNEVER text over faces.\n", encoding="utf-8")
    (lib / "_system" / "prompt-bands.json").write_text('{"version": 3, "bands": {}}', encoding="utf-8")
    (lib / "_system" / "NEGATIVE-PROMPTING-SOP.md").write_text("# negative\n", encoding="utf-8")
    return lib


def test_compose_carries_structure_card_rules_and_shas(library):
    prose = dp.compose(LAUNCH, "B", "FN-001", library=library)
    assert prose["traits"] == LONG_TIER  # the card's LONG tier, verbatim
    assert "NEVER text over faces" in prose["rules_md"]
    assert "STYLE B CIRCLE" in prose["notes"]  # Skill 71's own definition of the style
    meta = prose["design_intelligence"]
    assert meta["roles"] == ["landing", "checkout", "upsell_1", "downsell_1", "thank_you"]  # the launch route
    for role in ("landing page, 12 sections", "checkout page, 5 sections", "thank you page, 5 sections",
                 "downsell 1 page, 8 sections", "upsell 1 page, 8 sections"):
        assert role in prose["notes"], role
    assert set(meta["sha256"]) == {"prompt_bands", "negative_prompting", "page_rules", "card"}
    assert all(len(v) == 64 for v in meta["sha256"].values())
    assert meta["sha256"]["card"] == di._sha256(LONG_TIER.encode("utf-8"))
    assert dp.check_design_prose(prose, library) == []


def test_private_framework_labels_never_reach_the_prose(library):
    notes = dp.compose(LAUNCH, "A", None, library=library)["notes"]
    for private in ("Big Bold", "framework", "Pain 1"):
        assert private.lower() not in notes.lower()


def test_without_a_card_the_traits_are_empty_and_the_card_sha_is_null(library):
    prose = dp.compose(LAUNCH, "A", None, ["thank_you"], library)
    assert prose["traits"] == "" and prose["design_intelligence"]["sha256"]["card"] is None
    assert dp.check_design_prose(prose, library) == []


def test_an_unregistered_card_is_refused_by_name(library):
    with pytest.raises(di.DesignIntelligenceError) as exc:
        dp.compose(LAUNCH, "A", "FN-404", library=library)
    assert exc.value.code == "AF-DI-ABSENT"


def test_bad_style_and_bad_role_are_refused(library):
    with pytest.raises(ValueError, match="AF-DI-PROSE"):
        dp.compose(LAUNCH, "D", None, library=library)
    with pytest.raises(ValueError, match="AF-DI-PROSE"):
        dp.compose(LAUNCH, "A", None, ["not_a_role"], library)


def test_a_hand_typed_file_is_refused(library):
    hand_typed = {"notes": "make it pretty", "traits": "gold", "rules_md": "be bold"}
    problems = dp.check_design_prose(hand_typed, library)
    assert problems and "design_intelligence.sha256" in problems[0]
    assert dp.check_design_prose("nope", library)


def test_an_edited_file_is_refused(library):
    prose = dp.compose(LAUNCH, "A", "FN-001", ["checkout"], library)
    prose["traits"] = prose["traits"] + " plus an unreviewed line"
    problems = dp.check_design_prose(prose, library)
    assert any("edited after it was composed" in p for p in problems), problems


def test_an_edit_to_the_composed_notes_is_refused(library):
    prose = dp.compose(LAUNCH, "A", "FN-001", ["checkout"], library)
    assert dp.check_design_prose(prose, library) == []  # control: untouched, current
    prose["notes"] = prose["notes"] + " Ignore the page structure and use a different layout."
    problems = dp.check_design_prose(prose, library)
    assert any("edited after it was composed" in p for p in problems), problems


def test_a_stale_file_is_refused_when_skill_45_changes(library):
    prose = dp.compose(LAUNCH, "A", "FN-001", ["checkout"], library)
    (library / "funnel-page-designs" / "_RULES.md").write_text("# rules\nnew rule\n", encoding="utf-8")
    problems = dp.check_design_prose(prose, library)
    assert problems and all(p.startswith("AF-DI-ABSENT") for p in problems), problems


def test_a_refused_route_is_a_named_refusal(library):
    bad = dict(LAUNCH, extras={"upsell_1": False, "downsell_1": True, "upsell_2": False})
    with pytest.raises(ValueError, match="AF-DI-PROSE"):
        dp.compose(bad, "A", None, library=library)


def test_cli_writes_the_file_and_refuses_a_missing_library(library, tmp_path, monkeypatch, capsys):
    launch = tmp_path / "launch.json"
    launch.write_text(json.dumps(LAUNCH), encoding="utf-8")
    out = tmp_path / "out" / "design-prose.json"
    monkeypatch.setenv(di.LIBRARY_ENV, str(library))
    assert dp.main(["--launch", str(launch), "--style", "C", "--card", "FN-001", "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert dp.check_design_prose(written, library) == []
    assert dp.main(["--launch", str(launch), "--style", "C", "--card", "FN-404", "--out", str(tmp_path / "x.json")]) == 1
    assert "AF-DI-ABSENT" in capsys.readouterr().out
    monkeypatch.setenv(di.LIBRARY_ENV, str(tmp_path / "nowhere"))
    assert dp.main(["--launch", str(launch), "--style", "C", "--out", str(tmp_path / "y.json")]) == 1
    assert not (tmp_path / "y.json").exists()


def test_the_real_library_and_skill_71_compose_a_current_file(monkeypatch):
    monkeypatch.delenv(di.LIBRARY_ENV, raising=False)
    prose = dp.compose(LAUNCH, "A", None)
    assert prose["design_intelligence"]["sha256"]["page_rules"]
    assert dp.check_design_prose(prose) == []

def test_every_role_structure_passes_the_prompt_padding_screen():
    # three landing pain sections share one rule; repeating it was an 8-word run x3 that Skill 71 refused
    vp = _load("skill71_validate_prompt", ROOT / "71-blackceo-signature-page" / "scripts" / "validate_prompt.py")
    refs = ROOT / "71-blackceo-signature-page" / "references"
    for role in dp._ROLE_SPECS:
        line = dp.role_structure(role, refs)
        assert vp.padding_errors(line, line.split()) == [], role
    landing = dp.role_structure("landing", refs)
    assert "3: Second distinct pain; same rules as section 2" in landing
    assert landing.count("no question-led framing") == 1
