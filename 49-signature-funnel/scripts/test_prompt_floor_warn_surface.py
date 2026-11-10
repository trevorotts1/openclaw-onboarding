#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A4 / A3 — the prover SURFACES the 80-to-below-95 percent warn-and-expand warning (it used
to drop it: the string "warning" appeared zero times in the file) and never claims a prompt
"was not sent".

SCOPE-LEDGER PRMPT-001 #2, #3, #4, #8. Ledger ruling G-9: the UNIT says SURFACE only, so a
warning is reported and the prompt still passes; this test pins that choice.

Run: python3 -m pytest 49-signature-funnel/scripts/test_prompt_floor_warn_surface.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import prove_sf_prompt_floor as pf  # noqa: E402

CAP = 20000


def _ledger(prompt: str) -> dict:
    return {"funnel_type": "signature_funnel",
            "prompts": [{"page_type": "main", "section": 1, "text_bearing": False,
                         "prompt": prompt}]}


def test_band_prompt_surfaces_the_warn_and_expand_warning():
    prompt = pf._valid_photo_prompt(17000)
    ratio = len(prompt.strip()) / CAP
    assert 0.80 <= ratio < 0.95, (len(prompt.strip()), ratio)   # 16,000-18,999 at cap 20,000
    violations, notes = pf.verify(_ledger(prompt))
    assert violations == [], violations                          # G-9: surface, do not fail closed
    joined = "\n".join(notes)
    assert "WARNING (prompt policy)" in joined, joined
    assert "in the 80 to 95 percent band" in joined, joined
    assert "of genuine specification to reach" in joined, joined


def test_at_target_prompt_carries_no_warn_and_expand_warning():
    violations, notes = pf.verify(_ledger(pf._valid_photo_prompt()))
    assert violations == [], violations
    joined = "\n".join(notes)
    assert "in the 80 to 95 percent band" not in joined, joined
    assert "of genuine specification to reach" not in joined, joined


def test_over_max_prompt_is_refused_with_an_accurate_message():
    violations, _ = pf.verify(_ledger("x" * 25000))
    codes = [c for c, _ in violations]
    assert "AF-FUN-PROMPT-CEILING" in codes, violations
    msg = " ".join(m for _, m in violations)
    assert "the Kie submit path refuses this prompt before its HTTP call" in msg, msg
    assert "NOT sent to Kie" not in msg


def test_the_false_claim_is_gone_from_the_source():
    src = (HERE / "prove_sf_prompt_floor.py").read_text(encoding="utf-8")
    assert "NOT sent to Kie" not in src
