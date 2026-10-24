#!/usr/bin/env python3
"""S75-T24: the five visual identities are explained by their real differences,
only verified samples are linked, and Canvas to Life never borrows a link.

Run: python3 core/choice_card/intake_card/test_visual_identity_help_s75t24.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402
from choice_card.looks import looks as L  # noqa: E402

IDS = ["lifelike-3d", "2d-hand-painted", "sketch-to-life", "canvas-to-life", "canvas-to-3d"]
ALIASES = ["Lifelike3D", "2DHand-Painted", "SketchtoLife", "CanvastoLife", "Canvasto3D"]

def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)

def _look_text():
    q = next(q for q in IC.QUESTIONS if q["id"] == "look")
    return q, IC.render_step(IC.QUESTIONS.index(q) + 1)

def _lines_under(text, option_no):
    lines = text.split("\n")
    at = next(j for j, line in enumerate(lines) if line.startswith("%d. " % option_no))
    return lines[at + 1]

def test_five_identities_and_compact_aliases_still_resolve():
    assert list(L.LOOK_ORDER) == IDS
    for alias, look_id in zip(ALIASES, IDS):
        assert L.resolve_look(alias) == look_id, alias
    assert len({L.LOOK_LABELS[i] for i in IDS}) == 5

def test_explanations_name_the_actual_difference():
    s = {i: IC._LOOK_SENTENCE[i] for i in IDS}
    assert len(set(s.values())) == 5
    assert "animated" in s["lifelike-3d"] and "footage" not in s["lifelike-3d"]
    assert "hand-painted" in s["2d-hand-painted"] and "real" not in s["2d-hand-painted"]
    assert "sketch" in s["sketch-to-life"] and "real footage" in s["sketch-to-life"]
    assert "painted" in s["canvas-to-life"] and "real footage" in s["canvas-to-life"]
    assert "painted" in s["canvas-to-3d"] and "lifelike 3D" in s["canvas-to-3d"]
    # The two transitions start from different media and end differently.
    assert s["sketch-to-life"] != s["canvas-to-life"]
    assert "real footage" not in s["canvas-to-3d"]

def test_only_verified_samples_render_and_missing_one_says_so():
    _, text = _look_text()
    registry = _load("style_samples.json")
    assert text.count("Watch: https://") == 4
    assert sum(1 for v in registry.values() if v) == 4
    for n, look_id in enumerate(IDS, 1):
        line = _lines_under(text, n)
        if registry[look_id]:
            assert line == "   Watch: " + registry[look_id], look_id
        else:
            assert line == "   " + IC.SAMPLE_MISSING, look_id
            assert "http" not in line
    assert "Watch: None" not in text and "Watch: null" not in text

def test_provenance_matches_the_registry_it_documents():
    registry = _load("style_samples.json")
    prov = _load("style_samples_provenance.json")["samples"]
    assert set(prov) == set(IDS) == set(registry)
    for look_id in IDS:
        assert prov[look_id]["url"] == registry[look_id], look_id
        assert prov[look_id]["status"] in ("verified", "unavailable")
        assert (prov[look_id]["status"] == "verified") == bool(registry[look_id])
        if registry[look_id]:
            assert prov[look_id]["reported_bytes"] > 0
    assert prov["canvas-to-life"]["status"] == "unavailable"
    assert prov["canvas-to-life"]["client_note"] == IC.SAMPLE_MISSING

def test_watching_a_sample_is_not_an_approval():
    _, text = _look_text()
    prov = _load("style_samples_provenance.json")
    assert "not an approval" in prov["note"]
    assert "approv" not in text.lower()          # no sample implies approval in the card

def test_canvas_to_life_stays_selectable():
    assert L.resolve_look("Canvas to Life") == "canvas-to-life"
    assert L.DEFAULT_LOOK_ID == "lifelike-3d"

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    raise SystemExit(1 if fails else 0)
