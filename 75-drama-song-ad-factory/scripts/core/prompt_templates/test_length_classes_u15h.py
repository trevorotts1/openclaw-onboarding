#!/usr/bin/env python3
"""U15h: the length-class table equals the code, and the final QC refuses a
ledger job with no receipt. Stdlib only, offline, no spend.

(a) for each of 60/90/120/180/300/600 the table equals what the code computes:
    `length_formula.plan`, `lipsync_clips.budget`, `ceil(D/4)` shots
    (`shot_planner.plan_generation_count`) and the derived rows (h3 shots and
    seconds, lanes and the per-lane KIE share). Any drift fails;
(b) a final QC that has a paid ledger job and no matching prompt receipt fails
    `prompt_compliance` (and a match does not fail it);
(c) the product seconds of the shot plan fall inside 10-15% of D.

Run: python3 scripts/core/prompt_templates/test_length_classes_u15h.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt_templates as PT  # noqa: E402

FAILS = []
LENGTHS = (60, 90, 120, 180, 300, 600)
#: table field -> the code the table must equal (drift in ANY of them fails).
FIELDS = ("delivered_s", "shots_total", "lipsync_clips", "lipsync_seconds",
          "h3_shots", "h3_seconds", "lanes",
          "kie_new_requests_per_lane_per_10s", "hooks", "song_words",
          "sections", "instrumental_breaks", "spoken_share_planned_pct",
          "product_seconds", "suno_generations")

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _raw_table():
    return PT.load("length_classes")["classes"]

# ---- (a) the table equals the code ---------------------------------------
def test_table_equals_code():
    if not hasattr(PT, "length_class"):
        check("length_class(L) exists (the one table reader)", False,
              "base tree: prompt_templates has no length_class")
        return
    table = _raw_table()
    check("the table carries exactly the six card lengths",
          sorted(int(k) for k in table) == list(LENGTHS),
          sorted(int(k) for k in table))
    for L in LENGTHS:
        row = table[str(L)]
        code = PT.length_class_code(L)
        drift = {f: (row.get(f), code[f]) for f in FIELDS
                 if row.get(f) != code[f]}
        check("table[%d] equals the code (plan, budget, ceil(D/4), lanes)"
              % L, not drift, drift)
        got = PT.length_class(L)     # refuses PROMPT_LENGTH_CLASS_DRIFT itself
        check("length_class(%d) returns the same row" % L,
              got == row, (got.get("lanes"), row.get("lanes")))
    # the drift refusal is real: a stale number fails through the reader
    try:
        PT.length_class_code(60)
        check("length_class_code is callable", True)
    except Exception as e:                                        # noqa: BLE001
        check("length_class_code is callable", False, repr(e))

def test_drift_is_refused():
    if not hasattr(PT, "length_class"):
        check("drift refusal exists", False, "base tree: no length_class")
        return
    import tempfile
    from pathlib import Path
    src = PT.templates_dir()
    d = Path(tempfile.mkdtemp())
    (d / "length-classes.json").write_text(
        json.dumps({"classes": {"60": dict(_raw_table()["60"], shots_total=14)}}),
        encoding="utf-8")
    try:
        PT.length_class(60, root=d)
        check("a drifted table refuses PROMPT_LENGTH_CLASS_DRIFT", False,
              "no error on shots_total 14 != 15")
    except PT.PromptTemplateError as e:
        check("a drifted table refuses PROMPT_LENGTH_CLASS_DRIFT",
              e.code == "PROMPT_LENGTH_CLASS_DRIFT", e)
    del src  # the fixture tree is the only override; the real tree is untouched

def test_three_modules_cross_check():
    if not hasattr(PT, "length_class"):
        check("the three modules read the class", False,
              "base tree: no length_class")
        return
    import length_formula as LF
    import lipsync_clips as LC
    from shot_planner import shot_planner as SP
    for mod, name in ((LF, "length_formula.class_check"),
                      (LC, "lipsync_clips.class_check"),
                      (SP, "shot_planner.shot_planner.class_check")):
        check("%s exists" % name, hasattr(mod, "class_check"), name)
    for L in LENGTHS:
        if hasattr(LF, "class_check"):
            check("length_formula.class_check(%d) is silent" % L,
                  LF.class_check(L) == [], LF.class_check(L))
        if hasattr(LC, "class_check"):
            check("lipsync_clips.class_check(%d) is silent" % (L - 2),
                  LC.class_check(L - 2) == [], LC.class_check(L - 2))
        if hasattr(SP, "class_check"):
            check("shot_planner.class_check(%d) is silent" % (L - 2),
                  SP.class_check(L - 2) == [], SP.class_check(L - 2))

# ---- (b) final QC: a ledger job with no receipt fails prompt_compliance ---
def _final_edit_record(run, stage):
    return {"schema_version": "1.0.0", "check_id": "final-edit-e2e",
            "run_id": run, "stage": stage, "check": "final_edit",
            "verdict": "PASS", "evidence": {"summary": "final edit pass"},
            "checker_version": "1.0.0",
            "reviewer": {"identity": "final_qc/1.0.0", "session": "u15h",
                         "authority": "17.5 final edit QC"}}

def test_final_qc_ledger_job_without_receipt_fails():
    import qc_gate as G
    if not hasattr(G, "prompt_compliance_rows"):
        check("prompt_compliance_rows exists", False,
              "base tree: qc_gate has no prompt_compliance")
        return
    run, stage = "u15h-run", "final-qc"
    job = {"logical_key": "h3-shot-07", "attempt_id": "a1",
           "request_digest": "d07", "prompt_sha256": "deadbeef07",
           "state": "succeeded"}
    rev = {"identity": "prompt_compliance/1.0.0", "session": "u15h-qc",
           "authority": "U15h design 8.9"}
    makers = {"final-edit-e2e": "final_assembler/1.0.0",
              "prompt-compliance": "prompt_templates/1.0.0"}
    master = {"chosen_length_s": 60, "measured_s": 58}
    # no receipt at all -> one row, unmatched, record FAILs
    rows, bad = G.prompt_compliance_rows([job], [])
    check("one row per ledger job", len(rows) == 1, rows)
    check("an unmatched ledger job is complained",
          bool(bad) and "h3-shot-07" in " ".join(bad), bad)
    rec = G.prompt_compliance_record(rows, bad, rev, run, stage)
    check("record validates in qc_gate", G.validate_record(rec) is None,
          G.validate_record(rec))
    gate = G.evaluate(run, stage, [_final_edit_record(run, stage), rec],
                      makers, ["final_edit"], master=master, ledger_jobs=[job])
    check("final QC with a ledger job and no receipt FAILs prompt_compliance",
          gate["gate"] == "FAIL"
          and any(f.get("check_id") in ("prompt_compliance",
                                        "prompt-compliance")
                  for f in gate["failures"]), gate)
    # a matching receipt clears it (PASS receipt)
    receipt = {"logical_key": "h3-shot-07", "attempt_id": "a1",
               "request_digest": "d07", "prompt_sha256": "deadbeef07",
               "check": {"verdict": "PASS", "reasons": []}}
    rows2, bad2 = G.prompt_compliance_rows([job], [receipt])
    check("a matching receipt clears the row", not bad2, bad2)
    rec2 = G.prompt_compliance_record(rows2, bad2, rev, run, stage)
    gate2 = G.evaluate(run, stage, [_final_edit_record(run, stage), rec2],
                       makers, ["final_edit"], master=master, ledger_jobs=[job])
    check("the same final QC PASSes with the receipt",
          gate2["gate"] == "PASS", gate2)
    # the check is REQUIRED when ledger jobs are present: no record -> fails
    gate3 = G.evaluate(run, stage, [_final_edit_record(run, stage)],
                       makers, ["final_edit"], master=master, ledger_jobs=[job])
    check("a missing prompt_compliance record is required, not optional",
          gate3["gate"] != "PASS"
          and any(f.get("check_id") in ("prompt_compliance",
                                        "prompt-compliance")
                  for f in gate3["failures"]), gate3)
    # a REFUSE/TRIM receipt is never compliance
    rows3, bad3 = G.prompt_compliance_rows(
        [job], [dict(receipt, check={"verdict": "TRIM", "reasons": ["x"]})])
    check("a TRIM receipt is not compliance", bool(bad3), bad3)

# ---- (c) product seconds inside 10-15% of D ------------------------------
def _shot(sid, start, end, visibility):
    return {"shot_id": sid, "song_start": start, "song_end": end,
            "product_visibility": visibility}

def test_product_seconds_inside_the_band():
    if not hasattr(PT, "check_product_seconds"):
        check("check_product_seconds exists", False,
              "base tree: prompt_templates has no check_product_seconds")
        return
    D = 58                    # L = 60
    check("the class product band is 10-15% of D",
          PT.product_seconds_bounds(60) == (5.8, 8.7),
          PT.product_seconds_bounds(60))
    shots = [_shot("s1", 0.0, 4.0, "none"), _shot("s2", 4.0, 8.0, "hero"),
             _shot("s3", 8.0, 12.0, "none"), _shot("s4", 12.0, 16.0, "featured")]
    check("in-band product seconds pass", PT.check_product_seconds(shots, 60) == [],
          PT.check_product_seconds(shots, 60))
    thin = [_shot("s1", 0.0, 4.0, "none"), _shot("s2", 4.0, 5.0, "hero")]
    check("out-of-band product seconds are named",
          bool(PT.check_product_seconds(thin, 60)),
          PT.check_product_seconds(thin, 60))
    check("a plan with no product shot is out of band",
          bool(PT.check_product_seconds([_shot("s1", 0.0, 4.0, "none")], 60)))
    del D

def main():
    for fn in (test_table_equals_code, test_drift_is_refused,
               test_three_modules_cross_check,
               test_final_qc_ledger_job_without_receipt_fails,
               test_product_seconds_inside_the_band):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            check("%s raised" % fn.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS: U15h length classes, lanes and prompt compliance.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
