#!/usr/bin/env python3
"""candidate_matrix (Skill 75 v3.0 C1/C3/C4): the 3x3 contract proofs.

(a) a valid matrix yields nine ids 1A-3C with concept grouping;
(b) two identical / reworded cells are REFUSED with typed codes, never merged;
(c) an unknown candidate id is refused;
(d) a selection bound to a different matrix digest is refused;
(e) a partial generation is refused on presentation and resumes only its gaps.

Zero spend, zero provider, zero network: the treatment briefs are the authored
variants.json rows and every cell is a local record.

Run: python3 75-drama-song-ad-factory/scripts/core/song_choices/test_candidate_matrix.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                 # core/

import song_choices.candidate_matrix as M                 # noqa: E402
from song_choices import song_choices as SC               # noqa: E402

FAILS = []
TESTS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def case(fn):
    TESTS.append(fn)
    return fn


def raises(fn, *a, **kw):
    """Run fn; return the MatrixError code, or the exception text if untyped."""
    try:
        fn(*a, **kw)
    except M.MatrixError as exc:
        return exc.code
    except Exception as exc:                              # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc)
    return "NO-RAISE"


STYLE = "rnb-flow"

CONCEPT_1 = {
    "concept_id": 1,
    "title": "The Road I Did Not Take",
    "perspective": "first person, the driver after a rejection",
    "lyrics": (
        "Engine off and the windshield holds the rain\n"
        "I count the exits but I stay\n"
        "Every streetlight knows my name\n"
        "And still I let the quiet win\n"
        "I keep the engine running in my chest\n"
        "Somewhere the old road turns to dust\n"
    ),
}
CONCEPT_2 = {
    "concept_id": 2,
    "title": "Morning Sweeps the Storm",
    "perspective": "first person, the same night answered at first light",
    "lyrics": (
        "First light across the kitchen floor\n"
        "I am sweeping up the storm\n"
        "Left the keys inside the door\n"
        "Told the mirror I am more\n"
        "Than all the voices in the hall\n"
        "I am answering the call\n"
    ),
}
CONCEPT_3 = {
    "concept_id": 3,
    "title": "A Letter Left for You",
    "perspective": "second person, tenderness offered to the same character",
    "lyrics": (
        "Write it down before you sleep\n"
        "Every promise that you keep\n"
        "Let the paper hold the weight\n"
        "Love is not a thing to wait\n"
        "Say it plainly say it twice\n"
        "Tenderness is not a price\n"
    ),
}


def concepts(*overrides):
    rows = [copy.deepcopy(CONCEPT_1), copy.deepcopy(CONCEPT_2),
            copy.deepcopy(CONCEPT_3)]
    for cid, patch in overrides:
        rows[cid - 1].update(patch)
    return rows


def _offer(matrix, ids, audio_root="/tmp/candidate"):
    for cid in ids:
        M.record_cell(matrix, cid, "submitted")
        M.record_cell(matrix, cid, "produced")
        M.record_cell(matrix, cid, "offerable",
                      audio=os.path.join(audio_root, "%s.mp3" % cid),
                      duration_s=61.5)


def _matrix(**kw):
    return M.build_matrix(STYLE, concepts(), run_id="run-fixture", **kw)


# ---- (a) nine ids, concept grouping ------------------------------------

@case
def valid_matrix_has_nine_ids_and_grouping():
    matrix = _matrix()
    ids = [c["candidate_id"] for c in matrix["cells"]]
    check("a. exactly nine cells", len(matrix["cells"]) == 9, ids)
    check("a. ids are 1A-3C in order", ids == list(M.CANDIDATE_IDS), ids)
    check("a. every id matches ^[1-3][A-C]$",
          all(M.CANDIDATE_ID_RE.match(i) for i in ids), ids)
    check("a. status planned before generation", matrix["status"] == "planned",
          matrix["status"])
    check("a. not complete while every cell is pending",
          matrix["status"] != "complete", matrix["status"])
    check("a. present refuses a planned matrix",
          raises(M.present, matrix) == M.MATRIX_INCOMPLETE)
    for concept in matrix["concepts"]:
        group = [c for c in matrix["cells"]
                 if c["concept_id"] == concept["concept_id"]]
        check("a. concept %d groups three treatments" % concept["concept_id"],
              [g["treatment"] for g in group] == ["A", "B", "C"])
        check("a. concept %d cells share one lyric hash" % concept["concept_id"],
              {g["lyric_hash"] for g in group} == {concept["lyric_hash"]})
        check("a. concept %d cells carry three treatment hashes"
              % concept["concept_id"],
              len({g["treatment_hash"] for g in group}) == 3)
    check("a. three concepts carry three distinct lyric hashes",
          len({c["lyric_hash"] for c in matrix["concepts"]}) == 3)
    check("a. cost plan exposes every cell",
          matrix["cost_plan"]["cells"] == 9
          and matrix["cost_plan"]["total_generations"] == 9
          and all("cost" in c and c["cost"]["generations"] == 1
                  for c in matrix["cells"]))
    again = copy.deepcopy(matrix)
    M._finalize(again)
    check("a. digest is stable across recovery re-finalise",
          again["matrix_digest"] == matrix["matrix_digest"])


# ---- (b) identical / near-identical cells refused ----------------------

@case
def identical_cells_are_refused_not_merged():
    code = raises(M.build_matrix, STYLE, concepts((2, {"lyrics":
                                                       CONCEPT_1["lyrics"]})))
    check("b. identical lyrics refused", code == M.MATRIX_CONCEPT_LYRIC_DUPLICATE,
          code)
    reword = CONCEPT_1["lyrics"].replace("rain", "snow")
    code = raises(M.build_matrix, STYLE, concepts((2, {"lyrics": reword})))
    check("b. one-word reword refused as not distinct",
          code == M.MATRIX_CONCEPT_NOT_DISTINCT, code)
    code = raises(M.build_matrix, STYLE, concepts((2, {"title":
                                                       CONCEPT_1["title"]})))
    check("b. same title refused", code == M.MATRIX_CONCEPT_NOT_DISTINCT, code)
    code = raises(M.build_matrix, STYLE,
                  concepts((2, {"perspective": CONCEPT_1["perspective"]})))
    check("b. same perspective refused", code == M.MATRIX_CONCEPT_NOT_DISTINCT,
          code)

    rows = M.treatments_for(STYLE)
    dup = [dict(rows[0]), dict(rows[0]),
           dict(rows[0], treatment="C", variant_id="relabelled-copy")]
    code = raises(M.validate_treatments, dup)
    check("b. relabelled duplicate treatment refused",
          code == M.MATRIX_TREATMENT_NOT_DISTINCT, code)
    near = [dict(rows[0]), dict(rows[1]),
            dict(rows[2], arrangement=rows[1]["arrangement"],
                 vocals=rows[1]["vocals"])]
    code = raises(M.validate_treatments, near)
    check("b. treatment differing in one facet only refused",
          code == M.MATRIX_TREATMENT_NOT_DISTINCT, code)
    check("b. three authored treatments pass",
          len(M.validate_treatments(M.treatments_for(STYLE))) == 3)


# ---- (c) unknown candidate id refused ----------------------------------

@case
def unknown_candidate_id_is_refused():
    matrix = _matrix()
    _offer(matrix, M.CANDIDATE_IDS)
    check("c. full matrix is complete", matrix["status"] == "complete",
          matrix["status"])
    for bad in (2, "B", "4A", "2D", "2b", "", None):
        code = raises(M.select, matrix, bad)
        check("c. select(%r) refused as unknown" % (bad,),
              code in (M.CANDIDATE_ID_UNKNOWN,), code)
    sel = M.select(matrix, "2B")
    check("c. 2B stays a string", sel["candidate_id"] == "2B"
          and isinstance(sel["candidate_id"], str))
    check("c. selection keeps the concept group",
          sel["concept"]["concept_id"] == 2
          and sel["treatment"]["code"] == "B")
    check("c. selection names the matrix digest",
          sel["matrix_digest"] == matrix["matrix_digest"])


# ---- (d) stale / different-matrix selection refused --------------------

@case
def selection_from_a_different_matrix_is_refused():
    first = _matrix()
    _offer(first, M.CANDIDATE_IDS)
    sel = M.select(first, "2B")
    check("d. selection validates against its own matrix",
          M.validate_selection(sel, first) is sel)

    other = M.build_matrix(STYLE, concepts(
        (3, {"lyrics": CONCEPT_3["lyrics"] + "One more line for the morning\n",
             "title": "A Letter Left for You, Revised"})), run_id="run-fixture")
    _offer(other, M.CANDIDATE_IDS)
    code = raises(M.validate_selection, sel, other)
    check("d. selection against a different matrix refused",
          code == M.MATRIX_DIGEST_MISMATCH, code)

    tampered = copy.deepcopy(first)
    tampered["cells"][0]["lyric_hash"] = "0" * 64
    code = raises(M.select, tampered, "1A")
    check("d. tampered matrix digest refused before select",
          code == M.MATRIX_DIGEST_MISMATCH, code)

    recovered = copy.deepcopy(first)
    recovered["cells"][0]["state"] = "pending"      # recovery metadata only
    M._finalize(recovered)
    check("d. recovery state does not move the content digest",
          recovered["matrix_digest"] == first["matrix_digest"]
          and M.validate_selection(sel, recovered) is sel)


# ---- (e) partial generation: fail closed, resumable --------------------

@case
def partial_generation_is_never_complete():
    matrix = _matrix()
    done = ["1A", "1B", "1C", "2A", "2B"]
    _offer(matrix, done)
    check("e. five of nine is partial", matrix["status"] == "partial",
          matrix["status"])
    check("e. counts distinguish offerable from requested",
          matrix["counts"]["offerable"] == 5
          and matrix["counts"]["requested"] == 9, matrix["counts"])
    check("e. presentation refuses the partial matrix",
          raises(M.present, matrix) == M.MATRIX_INCOMPLETE)
    check("e. selection refuses the partial matrix",
          raises(M.select, matrix, "2C")
          == M.MATRIX_INCOMPLETE)
    check("e. resume lists only the four gaps",
          M.pending_ids(matrix) == ["2C", "3A", "3B", "3C"],
          M.pending_ids(matrix))

    matrix["status"] = "complete"                      # a lie
    with tempfile.TemporaryDirectory() as tmp:
        path = M.save_matrix(tmp, matrix)
        check("e. save re-derives a partial status",
              json.load(open(path))["status"] == "partial",
              json.load(open(path))["status"])
        loaded = M.load_matrix(tmp)
        check("e. reloaded matrix is still partial",
              loaded["status"] == "partial")
        check("e. reloaded matrix refuses presentation",
              raises(M.present, loaded)
              == M.MATRIX_INCOMPLETE)

    _offer(matrix, ["2C", "3A", "3B", "3C"])
    check("e. all nine offerable is complete",
          matrix["status"] == "complete", matrix["status"])
    check("e. complete matrix presents nine receipts",
          [r["candidate_id"] for r in M.present(matrix)]
          == list(M.CANDIDATE_IDS))
    code = raises(M.record_cell, matrix, "1A", "submitted")
    check("e. a produced cell is never regenerated", code == M.CELL_STATE_INVALID,
          code)
    code = raises(M.record_cell, matrix, "2C", "offerable", audio="x")
    check("e. unmeasured duration is not offerable",
          code in (M.CELL_STATE_INVALID,), code)


# ---- legacy three-option path untouched --------------------------------

@case
def legacy_three_variant_path_still_works():
    rows = SC.variants_for(STYLE)
    check("legacy. variants_for still yields exactly three", len(rows) == 3)
    check("legacy. _require_three accepts three",
          len(SC._require_three(rows, key=lambda r: r["id"])) == 3)
    nine = [dict(rows[i % 3], id="x%d" % i) for i in range(9)]
    try:
        SC._require_three(nine, key=lambda r: r["id"])
        ok = False
    except SC.ChoiceError:
        ok = True
    check("legacy. nine rows are refused by the old guard", ok)


# ---- C2: matrix cells inherit the re-voicing lead presence -------------

@case
def matrix_cells_keep_the_dry_upfront_lead():
    import suno_recipe as R
    sr = getattr(R, "suno_recipe", R)

    rnb = _matrix()
    styles = {c["candidate_id"]: M.cell_style(rnb, c["candidate_id"])
              for c in rnb["cells"]}
    check("C2. rnb treatments expose revoices_lead",
          [t["revoices_lead"] for t in rnb["treatments"]] == [True, True, True],
          [t["revoices_lead"] for t in rnb["treatments"]])
    missing = [cid for cid, text in styles.items()
               if "dry upfront vocal" not in text.lower()]
    check("C2. all nine rnb matrix cells keep the dry upfront lead",
          not missing, missing)
    tails = [cid for cid, text in styles.items()
             if rnb["treatments"][M.TREATMENT_CODES.index(cid[-1])]["arrangement"]
             not in text]
    check("C2. every cell keeps its own arrangement tail", not tails, tails)

    # The flag is load-bearing, not incidental: same row, flag off, phrase gone.
    row = next(r for r in SC.variants_for("rnb-flow")
               if r["id"] == "warm-live-band")
    without = sr.brief_style_text(
        "rnb-flow", SC._brief_text(row, "f"), None, "f", None,
        tail_clause=row["brief"]["arrangement"], revoices_lead=False)
    check("C2. dropping revoices_lead drops the presence phrase",
          "dry upfront vocal" not in without.lower()
          and "dry upfront vocal" in styles["1B"].lower())
    check("C2. matrix cell composes through the same composer as legacy",
          M.cell_style(rnb, "1B") == sr.brief_style_text(
              "rnb-flow", SC._brief_text(row, "f"), None, "f", None,
              tail_clause=row["brief"]["arrangement"], revoices_lead=True))

    # soul-ballad A does not re-voice; B and C do. The matrix must follow data.
    soul = M.build_matrix("soul-ballad", concepts(), run_id="run-soul")
    flags = [t["revoices_lead"] for t in soul["treatments"]]
    check("C2. soul-ballad flags are data-driven", flags == [False, True, True],
          flags)
    a_style = M.cell_style(soul, "1A").lower()
    b_style = M.cell_style(soul, "1B").lower()
    check("C2. non-revoicing A cell gains no presence phrase",
          "dry upfront vocal" not in a_style)
    check("C2. re-voicing B cell keeps the presence phrase",
          "dry upfront vocal" in b_style)
    check("C2. legacy variants.json still carries the flag",
          SC.variants_for("soul-ballad")[0].get("revoices_lead") is None
          and SC.variants_for("soul-ballad")[1].get("revoices_lead") is True)


def main():
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            check("%s raised" % fn.__name__, False,
                  "%s: %s" % (type(exc).__name__, exc))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
