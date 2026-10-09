#!/usr/bin/env python3
"""FU-U13: story arc rule + product-connection target (10-15% of runtime).

Run: python3 core/length_formula/test_story_arc_u13.py

Covers:
  * planner computes the product-connection percent for a 60 s and a 180 s
    plan (target midpoint when nothing measured yet);
  * planner measures tagged shots/lines when handed them;
  * checker FLAGs at 5 percent and PASSes at 12 percent (measured);
  * an ad whose product appears only on an end card is flagged;
  * the target is never a blocker (FLAG carries measured seconds, blocking
    stays False).
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, HERE)

# pytest collects this file as part of the length_formula package, so a bare
# `import length_formula` returns the package. Load the module by file path.
_spec = importlib.util.spec_from_file_location(
    "length_formula_u13", os.path.join(HERE, "length_formula.py"))
LF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LF)

from delivery_checklist import delivery_checklist as DC  # noqa: E402

# --- planner: percent computed for a 60 s and a 180 s plan ---------------
p60 = LF.plan(60, (15, 20))
pc60 = p60["product_connection"]
assert pc60["runtime_s"] == 58.0, pc60
assert 10.0 <= pc60["product_percent"] <= 15.0, pc60
assert pc60["verdict"] == "PASS" and pc60["in_target"] is True, pc60
assert pc60["seconds"] if "seconds" in pc60 else pc60["product_seconds"]
assert pc60["blocking"] is False, pc60

p180 = LF.plan(180, (15, 20))
pc180 = p180["product_connection"]
assert pc180["runtime_s"] == 178.0, pc180
assert 10.0 <= pc180["product_percent"] <= 15.0, pc180
assert pc180["verdict"] == "PASS", pc180
# target seconds scale with runtime: 180 s plans more than 60 s
assert pc180["product_seconds"] > pc60["product_seconds"], (pc60, pc180)
assert pc60["product_seconds"] == round(58 * 12.5 / 100.0, 1), pc60
assert pc180["product_seconds"] == round(178 * 12.5 / 100.0, 1), pc180

# arc rule: struggle -> what changed -> the product is why -> get the product
assert pc60["arc"] == ["struggle", "what_changed", "product_is_why",
                       "get_product"], pc60["arc"]
assert "end card" in pc60["arc_rule"], pc60["arc_rule"]

# --- planner: measured shots/lines override the midpoint -----------------
shots = [{"id": "s1", "seconds": 6.96, "tags": ["product", "motion"]},
         {"id": "s2", "seconds": 3.0, "tags": ["struggle", "motion"]},
         {"id": "s3", "seconds": 4.0}]
lines = [{"section": "[Intro]", "tags": ["spoken"], "text": "one two three"},
         {"section": "[Chorus]", "tags": ["product"],
          "text": "this is the thing that changed my life"}]
m = LF.plan_product_connection(p60, shots=shots, lyric_lines=lines)
assert m["measured"] is True, m
assert m["product_seconds"] == round(6.96 + 8 / 1.07, 1), m
assert m["product_percent"] == round(m["product_seconds"] / 58 * 100, 1), m
assert m["requirements"]["spoken_word_parts"] == 1, m
assert m["requirements"]["struggle_motion_shots"] == 1, m
assert m["missing"] == [], m

# a plan with no spoken parts and no struggle motion shots is flagged
thin = LF.plan_product_connection(p60, shots=[{"seconds": 7.0}], lyric_lines=[])
assert "spoken_word_parts" in thin["missing"], thin
assert "struggle_motion_shots" in thin["missing"], thin
assert thin["verdict"] == "FLAG", thin

# --- checker: FLAG at 5 percent, PASS at 12 percent ----------------------
five = DC.measure_product_connection(
    [{"seconds": 3.0, "tags": ["product"]}], [], 60.0)
assert five["percent"] == 5.0, five
assert five["verdict"] == "FLAG", five
assert five["seconds"] == 3.0, five
assert five["blocking"] is False, five
assert "5.0%" in five["measurement"], five

twelve = DC.measure_product_connection(
    [{"seconds": 7.2, "tags": ["product"]}], [], 60.0)
assert twelve["percent"] == 12.0, twelve
assert twelve["verdict"] == "PASS", twelve
assert twelve["in_target"] is True, twelve

# lyric lines count too (words / sung rate), same measurement
lyric_only = DC.measure_product_connection(
    [], [{"tags": ["product"], "text": "a b c d e f g"}], 60.0)
assert lyric_only["seconds"] == round(7 / 1.07, 1), lyric_only
assert lyric_only["verdict"] == "PASS", lyric_only

# --- product only on the end card is flagged ------------------------------
end_card = DC.measure_product_connection(
    [{"seconds": 7.0, "tags": ["product", "end_card"]}], [], 60.0)
assert end_card["end_card_only"] is True, end_card
assert end_card["verdict"] == "FLAG", end_card
assert end_card["blocking"] is False, end_card
assert "end card" in end_card["measurement"], end_card

# a real on-screen product shot plus an end card is not "end-card only"
both = DC.measure_product_connection(
    [{"seconds": 3.0, "tags": ["product", "motion"]},
     {"seconds": 4.2, "tags": ["product", "end_card"]}], [], 60.0)
assert both["end_card_only"] is False and both["verdict"] == "PASS", both

# no runtime -> UNAVAILABLE, still never a blocker
na = DC.measure_product_connection([], [], None)
assert na["verdict"] == "UNAVAILABLE" and na["blocking"] is False, na

# --- the row rides the receipt/checklist output, never blocks the gate ----
receipt = {"runtime_s": 60.0,
           "shots": [{"seconds": 3.0, "tags": ["product"]}],
           "lyrics": []}
res = DC.evaluate(receipt)
row = res["evidence"][DC.PRODUCT_ROW]
assert row["verdict"] == "FLAG" and row["percent"] == 5.0, row
assert DC.PRODUCT_ROW not in res["repair_scope"], res["repair_scope"]
# the measured row still reports even when the gate itself fails on missing
# answers -- a report, not an enforcement
assert res["pass"] is False, res
rec = DC.to_qc_record(res, "run-u13", "final_edit",
                      {"identity": "t", "session": "s", "authority": "a"})
assert "PRODUCT_CONNECTION" in rec["evidence"]["summary"], rec["evidence"]
assert "5.0%" in rec["evidence"]["summary"], rec["evidence"]

print("ok: story_arc_u13")
