"""Skill 45 read-only consumption (fix spec M4, issues 8 and 9, decision D-F).

design_intelligence.py reads Skill 45's style card LONG tier, prompt bands, negative-prompting
rules and page rules, refuses by name (AF-DI-ABSENT) when any of them is missing, and keeps a
receipt that a later stage re-checks against the live library.

Run from the repository root:
    python3 -m pytest shared-utils/signature_launch/tests/test_design_intelligence.py -q
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "shared-utils" / "signature_launch" / "design_intelligence.py"

_spec = importlib.util.spec_from_file_location("signature_launch_design_intelligence", MODULE)
di = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(di)

LONG_TIER = (
    "Style: bold cinematic gold. Hero subject on the left third, headline room on the right.\n"
    "### Not a heading: this line sits inside the fenced prompt and must survive the cut.\n"
    "Do not place text over any face."
)
CARD = f"""# FN-001 - Test Style

## CARD HEADER
- **ID:** FN-001

## PROMPT TEMPLATES

### SHORT (<=500 chars) - actual count: 10 chars
```
short prompt
```

### LONG (<=19,000 chars) - actual count: {len(LONG_TIER)} chars
```
{LONG_TIER}
```

## AVOID-LIST
```
watermark
```
"""
INDEX = """# DESIGN LIBRARY - MASTER INDEX

## FUNNEL / LANDING / WEBSITE PAGE DESIGNS (FN-)
| Sig # | ID | Style Name | One-Line Summary | Status | Ver | Date | File Path |
|---|---|---|---|---|---|---|---|
| 1 | FN-001 | Test Style | a test card | production | v1.0 | 2026-11-10 | funnel-page-designs/FN-001-test.md |
| 2 | FN-002 | No Long | a card without a LONG tier | draft | v1.0 | 2026-11-10 | funnel-page-designs/FN-002-nolong.md |
| 3 | FN-003 | Ghost | a registered card with no file | draft | v1.0 | 2026-11-10 | funnel-page-designs/FN-003-ghost.md |
"""


@pytest.fixture()
def library(tmp_path):
    lib = tmp_path / "library"
    (lib / "_system").mkdir(parents=True)
    (lib / "funnel-page-designs").mkdir()
    (lib / "INDEX.md").write_text(INDEX, encoding="utf-8")
    (lib / "funnel-page-designs" / "FN-001-test.md").write_text(CARD, encoding="utf-8")
    (lib / "funnel-page-designs" / "FN-002-nolong.md").write_text("# FN-002\n\n### SHORT\n```\nx\n```\n",
                                                                  encoding="utf-8")
    (lib / "funnel-page-designs" / "_RULES.md").write_text("# rules\nNEVER text over faces.\n", encoding="utf-8")
    (lib / "_system" / "prompt-bands.json").write_text(json.dumps({"version": 3, "bands": {}}), encoding="utf-8")
    (lib / "_system" / "NEGATIVE-PROMPTING-SOP.md").write_text("# negative prompting\n", encoding="utf-8")
    return lib


def _code(excinfo):
    return excinfo.value.code


def test_long_tier_equals_the_fixture_slice(library):
    card = di.resolve_style_card("FN-001", library)
    assert card["long_tier"] == LONG_TIER  # verbatim, including the heading-looking line inside the fence
    assert card["id"] == "FN-001"
    assert card["path"] == "funnel-page-designs/FN-001-test.md"
    assert card["sha256"] == di._sha256(LONG_TIER.encode("utf-8"))


def test_card_id_match_is_case_insensitive_and_id_column_only(library):
    assert di.resolve_style_card("fn-001", library)["id"] == "fn-001"
    with pytest.raises(di.DesignIntelligenceError) as exc:
        di.resolve_style_card("production", library)  # the Status cell is not an ID
    assert _code(exc) == "AF-DI-ABSENT"


@pytest.mark.parametrize("card_id", ["FN-999", "FN-002", "FN-003", ""])
def test_unresolvable_card_is_refused_by_name(library, card_id):
    # unregistered, no LONG tier, registered with no file, blank
    with pytest.raises(di.DesignIntelligenceError) as exc:
        di.resolve_style_card(card_id, library)
    assert _code(exc) == "AF-DI-ABSENT"
    assert str(exc.value).startswith("AF-DI-ABSENT")


@pytest.mark.parametrize("loader,args,missing", [
    (di.load_prompt_bands, (), "_system/prompt-bands.json"),
    (di.load_negative_prompting, (), "_system/NEGATIVE-PROMPTING-SOP.md"),
    (di.load_page_rules, ("funnel-page-designs",), "funnel-page-designs/_RULES.md"),
])
def test_every_loader_refuses_when_its_file_is_missing(library, loader, args, missing):
    assert loader(*args, root=library)  # control: present, loads
    (library / missing).unlink()
    with pytest.raises(di.DesignIntelligenceError) as exc:
        loader(*args, root=library)
    assert _code(exc) == "AF-DI-ABSENT"


def test_loaders_return_text_json_and_hashes(library):
    bands = di.load_prompt_bands(root=library)
    assert bands["json"]["version"] == 3
    assert bands["sha256"] == di._sha256((library / "_system" / "prompt-bands.json").read_bytes())
    assert "negative prompting" in di.load_negative_prompting(root=library)["text"]
    assert "NEVER text over faces" in di.load_page_rules(root=library)["text"]


def test_page_category_cannot_leave_the_library(library):
    for bad in ("..", "../x", "a/b", ""):
        with pytest.raises(di.DesignIntelligenceError):
            di.load_page_rules(bad, root=library)


def test_a_library_path_resolving_outside_the_library_is_refused(library, tmp_path):
    (tmp_path / "outside.md").write_text("# outside\n\n### LONG (<=19,000 chars)\n```\nescaped\n```\n", encoding="utf-8")
    assert di._read(library, "INDEX.md")  # control: a path inside the library reads
    with pytest.raises(di.DesignIntelligenceError) as exc:
        di._read(library, "../outside.md")
    assert _code(exc) == "AF-DI-ABSENT" and "outside the design library" in str(exc.value)
    index = (library / "INDEX.md").read_text(encoding="utf-8")
    (library / "INDEX.md").write_text(
        index.replace("funnel-page-designs/FN-001-test.md", "../outside.md"), encoding="utf-8")
    with pytest.raises(di.DesignIntelligenceError) as exc:  # a registered card cannot point out of the library
        di.resolve_style_card("FN-001", library)
    assert _code(exc) == "AF-DI-ABSENT" and "outside the design library" in str(exc.value)


def test_absent_library_is_refused(tmp_path, monkeypatch):
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv(di.LIBRARY_ENV, str(empty))
    with pytest.raises(di.DesignIntelligenceError) as exc:
        di.library_root()
    assert _code(exc) == "AF-DI-ABSENT"
    with pytest.raises(di.DesignIntelligenceError):
        di.resolve_style_card("FN-001")


def test_env_override_wins_and_is_used_by_the_loaders(library, monkeypatch):
    monkeypatch.setenv(di.LIBRARY_ENV, str(library))
    assert di.library_root() == library
    assert di.resolve_style_card("FN-001")["long_tier"] == LONG_TIER


def test_the_real_skill_45_library_loads_without_override(monkeypatch):
    monkeypatch.delenv(di.LIBRARY_ENV, raising=False)
    root = di.library_root()
    assert (root / "INDEX.md").is_file()
    assert di.load_prompt_bands()["json"]["bands"]
    assert di.load_negative_prompting()["text"].strip()
    assert di.load_page_rules()["text"].strip()


def test_receipt_roundtrip_and_drift(library, tmp_path):
    run = tmp_path / "run"
    path = di.write_receipt(run, "FN-001", root=library)
    assert path == run / di.RECEIPT_REL
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["card_id"] == "FN-001"
    assert receipt["card_sha256"] == di._sha256(LONG_TIER.encode("utf-8"))
    assert di.verify_receipt(receipt, library) == []
    # the rules change after the receipt was written: the receipt no longer proves anything
    (library / "funnel-page-designs" / "_RULES.md").write_text("# rules\nchanged\n", encoding="utf-8")
    problems = di.verify_receipt(receipt, library)
    assert problems and all(p.startswith("AF-DI-ABSENT") for p in problems), problems
    assert any("page_rules_sha256" in p for p in problems)


def test_receipt_without_a_card_is_valid_and_null_card_fields(library, tmp_path):
    receipt = di.build_receipt(None, root=library)
    assert receipt["card_id"] is None and receipt["card_sha256"] is None
    assert di.verify_receipt(receipt, library) == []


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("prompt_bands_sha256"),
    lambda r: r.update(negative_prompting_sha256="nothex"),
    lambda r: r.update(card_id="FN-001", card_sha256=None),
])
def test_malformed_receipt_is_refused(library, mutate):
    receipt = di.build_receipt(None, root=library)
    mutate(receipt)
    assert di.verify_receipt(receipt, library)
    assert di.verify_receipt("not a dict", library)


def test_run_style_card_id_reads_the_intake(tmp_path):
    assert di.run_style_card_id(tmp_path) is None
    (tmp_path / "intake.json").write_text(json.dumps({"style_card_id": " FN-001 "}), encoding="utf-8")
    assert di.run_style_card_id(tmp_path) == "FN-001"
    (tmp_path / "intake.json").write_text(json.dumps({"style_card_id": "  "}), encoding="utf-8")
    assert di.run_style_card_id(tmp_path) is None


def test_cli_receipt_and_verify(library, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(di.LIBRARY_ENV, str(library))
    run = tmp_path / "run"
    run.mkdir()
    (run / "intake.json").write_text(json.dumps({"style_card_id": "FN-001"}), encoding="utf-8")
    assert di.main(["verify", "--run-dir", str(run)]) == 1  # no receipt yet
    assert di.main(["receipt", "--run-dir", str(run)]) == 0
    assert json.loads((run / di.RECEIPT_REL).read_text())["card_id"] == "FN-001"
    assert di.main(["verify", "--run-dir", str(run)]) == 0
    (library / "_system" / "NEGATIVE-PROMPTING-SOP.md").write_text("changed\n", encoding="utf-8")
    assert di.main(["verify", "--run-dir", str(run)]) == 1
    (run / "intake.json").write_text(json.dumps({"style_card_id": "FN-404"}), encoding="utf-8")
    assert di.main(["receipt", "--run-dir", str(run)]) == 1
    assert "AF-DI-ABSENT" in capsys.readouterr().out
