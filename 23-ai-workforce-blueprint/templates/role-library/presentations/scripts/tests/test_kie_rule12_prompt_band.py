"""KIE prompt rule 12 on the Presentations render path (owner order 2026-10-05).

build_deck.py and prompt_gate.py keep no 9,000 / 18,000 band: both call the shared enforcer
shared-utils/kie_prompt_enforcer.py (Skill 74 prompt-budget --check). GPT Image 2.5 maxLength 20,000:
79 percent is rejected with the exact characters to ADD, 95 and 100 percent pass, 101 percent is rejected with the
exact characters to CUT; the mandatory English pin counts toward the ceiling. Hermetic: the real adapter answers
from its registry snapshot (empty HOME, no key).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
os.environ["HOME"] = tempfile.mkdtemp()
os.environ.pop("KIE_API_KEY", None)

import build_deck as bd  # noqa: E402
import prompt_gate as pg  # noqa: E402
import prove_pres_prompt_floor as prover  # noqa: E402

MAX = 20000
COPY = "Stop Guessing. Start Closing."


def rich(pct: int) -> str:
    return prover._rich_pass_prompt(MAX * pct // 100)  # carries the English pin, quality teeth satisfied


def _run_dir(tmp_path: Path, text: str) -> Path:
    d = tmp_path / "working" / "prompts"
    d.mkdir(parents=True)
    (d / "slide-01.txt").write_text(text, encoding="utf-8")
    return tmp_path


def test_no_separate_band_constants_remain():
    for mod in (bd, pg):
        for name in ("PROMPT_CHAR_FLOOR", "PROMPT_CHAR_CEILING", "PROMPT_CHAR_TARGET_HIGH", "API_PROMPT_HARD_CEILING"):
            assert not hasattr(mod, name), f"{mod.__name__} still defines {name}"
        assert mod.KPE.__name__ == "kie_prompt_enforcer"


@pytest.mark.parametrize("pct,ok", [(79, False), (95, True), (100, True), (101, False)])
def test_both_modules_apply_the_same_band(pct, ok):
    text = rich(pct)
    assert bool(bd._length_problems(text)) is (not ok)
    assert bool(pg.length_problems(text)) is (not ok)


def test_79_percent_names_the_chars_to_add_and_101_the_chars_to_cut():
    assert "ADD at least 200" in bd._length_problems(rich(79))[0][1]
    assert bd._length_problems(rich(79))[0][0] == "AF-P1"
    assert "CUT exactly 200" in bd._length_problems(rich(101))[0][1]
    assert bd._length_problems(rich(101))[0][0] == "AF-P2"
    assert "ADD at least 200" in pg.length_problems(rich(79))[0]
    assert "CUT exactly 200" in pg.length_problems(rich(101))[0]


def test_the_retired_9000_floor_no_longer_passes():
    assert bd._length_problems(prover._rich_pass_prompt(9000))
    assert pg.length_problems(prover._rich_pass_prompt(9000))


def test_the_english_pin_counts_toward_the_ceiling():
    unpinned = "x" * (MAX - 10)  # fits alone, but the pin appended at submit pushes it over the max
    (code, msg), = bd._length_problems(unpinned)
    assert code == "AF-P2" and "English pin" in msg and "CUT exactly" in msg
    assert pg.length_problems(unpinned)


@pytest.mark.parametrize("pct,ok", [(79, False), (95, True), (100, True), (101, False)])
def test_load_rich_prompt_enforces_the_band(tmp_path, pct, ok):
    run_dir = _run_dir(tmp_path, rich(pct))
    slide = {"slide": 1, "copy": [COPY]}
    if ok:
        assert bd.load_rich_prompt(slide, run_dir)
    else:
        with pytest.raises(ValueError, match="(ADD at least|CUT exactly)"):
            bd.load_rich_prompt(slide, run_dir)


@pytest.mark.parametrize("pct,ok", [(79, False), (95, True), (100, True), (101, False)])
def test_preflight_collect_prompt_problems_enforces_the_band(tmp_path, pct, ok):
    run_dir = _run_dir(tmp_path, rich(pct))
    slides = tmp_path / "slides.json"
    slides.write_text('[{"slide": 1, "copy": ["%s"]}]' % COPY, encoding="utf-8")
    problems = bd._collect_prompt_problems(run_dir, slides)
    assert (problems == []) is ok, problems
    if not ok:
        assert "rich prompt slide-01.txt" in problems[0][1]


@pytest.mark.parametrize("pct,ok", [(79, False), (95, True), (100, True), (101, False)])
def test_verify_prompt_enforces_the_band(pct, ok):
    if ok:
        assert pg.verify_prompt(rich(pct), copy_val=[COPY]) == rich(pct)
    else:
        with pytest.raises(pg.PromptGateError):
            pg.verify_prompt(rich(pct), copy_val=[COPY])
