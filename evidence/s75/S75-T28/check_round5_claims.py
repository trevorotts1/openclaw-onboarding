#!/usr/bin/env python3
"""Discriminating check for S75-T28 round 5.

FAIL at the round-4 head, PASS at the round-5 head.

What it does, in one pass over the four pinned T28 files plus --target:
  1. re-derives every round-5 measurement (M1..M7) from the pinned files,
  2. requires the target's stored measurement records to equal the re-derivation,
  3. requires the seven round-4 false sentences to be absent from the target,
  4. requires the round-4 restorations to survive (over-correction check R1..R10),
  5. re-measures the pinned hashes,
  6. runs a known-good control and an instrument control on the same comparator.

Exit 0 = PASS, 1 = FAIL, 2 = instrument failure (missing/unreadable input).
"""
import hashlib
import json
import sys
from pathlib import Path

EV = Path("/Volumes/mac mini m4/Downloads/git trees and automations/S75_Story_First_Full_Cast_Build_20261024/evidence")

PINNED = {
    "S75-T28.compatibility-map.json": ("e9ab7ac031706ceeec6c460959eea9a0bb4267106ef398f2b74370565eaeee19", 53195),
    "S75-T28.compatibility-map.round2.json": ("459d4bf79f8ddf1ee2802eefc16a8376616bb447e4025c4f8db5bb257ff97d46", 55775),
    "S75-T28.compatibility-map.round3.json": ("bd7b39a728fcd3848d4e963f95879f17dda82335a81031555f8cf8d9a14c75c5", 100968),
    "S75-T28.compatibility-map.round4.json": ("4b942df7511a082c4984fc5dfcd6a96d05f10949c35299111f0a0a18893eb09a", 147635),
}

FALSE_SENTENCES = [
    ("D1", "Three further round-1 strings are absent from this file and are NOT covered by any S entry"),
    ("D2", "4 of 4 change strings and 4 of 4 risk strings are shortened"),
    ("D3", "2 of the 6 strings are shortened relative to round 1"),
    ("D4", "CONFIRMED_PRESERVED key count in this file"),
    ("D5a", "Round 3 records its own."),
    ("D5b", "One new file only: this round-3 map at evidence/S75-T28.compatibility-map.round3.json"),
    ("D5c", "One new file only: this round-3 map"),
    ("D6", "round-1 and round-2 JSON documents into this artifact"),
]


def fail_exit(msg):
    print("INSTRUMENT FAILURE:", msg)
    sys.exit(2)


def load(name):
    p = EV / name
    if not p.is_file():
        fail_exit("missing %s" % p)
    try:
        return json.loads(p.read_text()), p.read_text()
    except Exception as e:  # unreadable is never evidence of absence
        fail_exit("unreadable %s: %s" % (p, e))


def sha(p):
    b = Path(p).read_bytes()
    return hashlib.sha256(b).hexdigest(), len(b)


results = []


def check(cid, desc, ok, detail=""):
    results.append((cid, desc, bool(ok), detail))
    print("%-6s %-4s %s" % (cid, "PASS" if ok else "FAIL", desc))
    if detail:
        print("        %s" % detail)


def main():
    target_name = sys.argv[sys.argv.index("--target") + 1] if "--target" in sys.argv else "S75-T28.compatibility-map.round5.json"
    r1, t1 = load("S75-T28.compatibility-map.json")
    r2, t2 = load("S75-T28.compatibility-map.round2.json")
    r3, t3 = load("S75-T28.compatibility-map.round3.json")
    r4, t4 = load("S75-T28.compatibility-map.round4.json")
    tgt_path = EV / target_name
    if not tgt_path.is_file():
        fail_exit("missing target %s" % tgt_path)
    tgt, ttext = load(target_name)

    print("TARGET:", tgt_path.name)

    # ---- pinned hashes (nothing earlier may move) ----
    for name, (h, n) in PINNED.items():
        got = sha(EV / name)
        check("P", "pinned %s unchanged" % name, got == (h, n), "measured %s %d bytes" % got)

    # ---- re-derive the seven measurements ----
    rest = r4["emergency_owner_handoff_CORRECTED"]["round_1_material_restored_verbatim"]
    three = {
        "doctrine_full": r1["emergency_owner_handoff"]["doctrine"],
        "does_merged_work_preserve_it_answer": r1["emergency_owner_handoff"]["does_merged_work_preserve_it"]["answer"],
        "does_merged_work_preserve_it_residual": r1["emergency_owner_handoff"]["does_merged_work_preserve_it"]["residual"],
    }
    m1_present = {k: rest.get(k) == v for k, v in three.items()}

    d1, d4 = r1["described_changes_not_applied"], r4["described_changes_not_applied_CARRIED"]
    chg_short = chg_same = risk_short = 0
    short_change_idx, short_risk_idx = [], []
    for i, (a, b) in enumerate(zip(d1, d4)):
        for key in ("change", "risk"):
            va, vb = a.get(key), b.get(key)
            if va == vb:
                if key == "change":
                    chg_same += 1
            elif isinstance(va, str) and isinstance(vb, str) and len(vb) < len(va):
                if key == "change":
                    chg_short += 1
                    short_change_idx.append(i + 1)
                else:
                    risk_short += 1
                    short_risk_idx.append(i + 1)

    n1, n2, n4 = r1["does_not_establish"], r2["does_not_establish"], r4["does_not_establish"]
    short, same, short_idx = 0, 0, []
    for i, (a, b) in enumerate(zip(n1, n4)):
        if a == b:
            same += 1
        elif isinstance(a, str) and isinstance(b, str) and len(b) < len(a):
            short += 1
            short_idx.append(i + 1)

    cp2, cp4 = r2["CONFIRMED_PRESERVED"], r4["CONFIRMED_PRESERVED"]
    gk = ["grouping_basis", "grouping_basis_source", "grouping_numbers"]
    keys_excl = [k for k in cp4 if k not in gk]
    keys_total = len(keys_excl)
    finding_blocks = keys_total - (1 if "provenance" in cp4 else 0)
    c1_blocks = len([k for k in keys_excl if k.startswith("C1_")])
    grouped = finding_blocks - (c1_blocks - 1)

    print()
    print("RE-DERIVED: M1 all three present=%s | M2 change shortened %d of 4 (items %s), change identical %d of 4, "
          "risk shortened %d of 4 (items %s) | M3 shortened %d of 6 (items %s), identical %d of 6, == round2 %s"
          % (all(m1_present.values()), chg_short, short_change_idx, chg_same, risk_short, short_risk_idx,
             short, short_idx, same, n4 == n2))
    print("RE-DERIVED: M4 key count excl grouping %d (plain count %d, round2 %d), finding blocks %d, C1 blocks %d, "
          "grouped %d | M5 anything_i_mutated == round3 %s | M6 commands == round3 %s"
          % (keys_total, len(cp4), len(cp2), finding_blocks, c1_blocks, grouped,
             r4["anything_i_mutated"] == r3["anything_i_mutated"], r4["commands_run_this_round"] == r3["commands_run_this_round"]))
    print()

    # ---- 1 + 2: the target's stored measurement records must equal the re-derivation ----
    recs = {r.get("id"): r for r in tgt.get("round_5_measurements", [])}
    has_block = bool(tgt.get("round_5_measurements"))
    check("M0", "target carries a round_5_measurements block (round-4 head has none)", has_block)

    if has_block:
        m1 = recs.get("M1", {})
        check("M1", "M1: three round-1 handoff strings present and deep-equal",
              m1.get("measured") is True and all(m1_present.values()) and
              m1.get("observed") == "all three values deep-equal to round 1: " + json.dumps(m1_present),
              "re-derived %s" % json.dumps(m1_present))
        m2 = recs.get("M2", {}).get("observed", {})
        check("M2", "M2: change/risk shortening counts match re-derivation",
              isinstance(m2, dict) and m2.get("change_shortened") == chg_short and
              m2.get("change_byte_identical") == chg_same and m2.get("risk_shortened") == risk_short,
              "stored %s vs re-derived change_short=%d change_same=%d risk_short=%d"
              % (json.dumps({k: v for k, v in m2.items() if k != "per_item"}), chg_short, chg_same, risk_short))
        m3 = recs.get("M3", {}).get("observed", {})
        check("M3", "M3: does_not_establish shortening count matches re-derivation",
              isinstance(m3, dict) and m3.get("shortened_vs_round_1") == short and
              m3.get("byte_identical_vs_round_1") == same and
              m3.get("whole_list_byte_identical_to_round_2") == (n4 == n2),
              "stored short=%s same=%s vs re-derived short=%d same=%d"
              % (m3.get("shortened_vs_round_1"), m3.get("byte_identical_vs_round_1"), short, same))
        m4 = recs.get("M4", {}).get("observed", {})
        check("M4", "M4: grouping numbers re-derived and sources that produce them",
              isinstance(m4, dict) and m4.get("key_count_excluding_grouping_keys") == keys_total and
              m4.get("finding_blocks_measured") == finding_blocks and
              m4.get("grouped_finding_count_measured") == grouped and
              m4.get("round_2_keys_equal_round_4_keys_excluding_grouping") == (sorted(cp2) == sorted(keys_excl)),
              "re-derived keys=%d finding=%d grouped=%d" % (keys_total, finding_blocks, grouped))
        m5 = recs.get("M5", {}).get("observed", {})
        check("M5", "M5: stale round-3 self-description measured and recorded",
              isinstance(m5, dict) and m5.get("anything_i_mutated_byte_identical_to_round_3") ==
              (r4["anything_i_mutated"] == r3["anything_i_mutated"]) and
              m5.get("row_16_note_says_round_3_records_its_own") ==
              ("Round 3 records its own" in r4["carry_forward_table"][16]["note"]),
              "re-derived mutated_identical=%s row16_stale=%s"
              % (r4["anything_i_mutated"] == r3["anything_i_mutated"],
                 "Round 3 records its own" in r4["carry_forward_table"][16]["note"]))
        m6 = recs.get("M6", {}).get("observed", {})
        check("M6", "M6: command-list provenance measured and recorded",
              isinstance(m6, dict) and m6.get("byte_identical_to_round_3_list") ==
              (r4["commands_run_this_round"] == r3["commands_run_this_round"]),
              "re-derived identical=%s" % (r4["commands_run_this_round"] == r3["commands_run_this_round"]))
        m7 = recs.get("M7", {})
        check("M7", "M7: numbers-discipline record present and its inventory is the round-4 list",
              m7.get("measured") is True and
              isinstance(m7.get("observed", {}).get("round_4_unsourced_inventory"), list) and
              len(m7["observed"]["round_4_unsourced_inventory"]) == 11,
              "inventory items=%s" % len(m7.get("observed", {}).get("round_4_unsourced_inventory", [])))

        # every stored measurement must name the field paths it compared
        check("M8", "every measurement record names field paths, comparator and a measured boolean",
              all(r.get("field_paths_compared") and r.get("method") and ("measured" in r)
                  for r in tgt.get("round_5_measurements", [])),
              "%d records" % len(tgt.get("round_5_measurements", [])))

    # ---- 3: the seven round-4 false sentences must be gone ----
    # supersession quotes are not assertions: drop the values of the keys that carry them
    QUOTE_KEYS = {"round_4_claim_quoted", "superseded_source_round_4", "corrects",
                  "question", "expected", "round_4_unsourced_inventory"}

    def assertions(node, out_list):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in QUOTE_KEYS:
                    continue
                assertions(v, out_list)
        elif isinstance(node, list):
            for v in node:
                assertions(v, out_list)
        elif isinstance(node, str):
            out_list.append(node)

    chunks = []
    assertions(tgt, chunks)
    assertion_text = "\n".join(chunks)
    for cid, s in FALSE_SENTENCES:
        check("F-" + cid, "false round-4 sentence absent from every assertion field: %r" % s[:60],
              s not in assertion_text)

    # ---- 4: over-correction, the round-4 restorations survive ----
    ev_r1 = [e for c in r1["conflicts_with_merged_units"] for e in c.get("evidence", [])]
    ev_t = [e for c in tgt.get("conflicts_with_merged_units_CARRIED", []) for e in c.get("evidence", [])]
    check("R1", "29 round-1 conflict evidence lines intact in target", ev_r1 == ev_t and len(ev_t) == 29)
    rd_r1 = [c.get("required_decision_for_T29_T30") for c in r1["conflicts_with_merged_units"] if "required_decision_for_T29_T30" in c]
    rd_t = [c.get("required_decision_for_T29_T30") for c in tgt.get("conflicts_with_merged_units_CARRIED", []) if "required_decision_for_T29_T30" in c]
    check("R2", "7 required_decision_for_T29_T30 strings intact", rd_r1 == rd_t and len(rd_t) == 7)
    st_r1 = [c.get("conflict") for c in r1["conflicts_with_merged_units"]]
    st_t = [c.get("conflict") for c in tgt.get("conflicts_with_merged_units_CARRIED", [])]
    check("R3", "9 conflict statements intact", st_r1 == st_t and len(st_t) == 9)
    check("R4", "precursors_consumed block intact", r1["precursors_consumed"] == tgt.get("precursors_consumed"))
    check("R5", "old_run_inventory block intact", r1["old_run_inventory"] == tgt.get("old_run_inventory"))
    rows1, rowst = r1["emergency_behaviour_map"], tgt.get("emergency_behaviour_map", [])
    extra = sorted({k for r in rowst for k in r} - {k for r in rows1 for k in r})
    check("R6", "emergency_behaviour_map: 13 rows, every round-1 field deep-equal (round-4 annotation keys named)",
          len(rowst) == len(rows1) == 13
          and all(all(r.get(k) == b.get(k) for k in b) for r, b in zip(rowst, rows1))
          and set(extra) <= {"behaviour_text_source", "round_2_file_preservation_recheck", "round_2_recheck", "round_3_note", "round_2_recheck", "round_3_note"},
          "round-4-only keys: %s" % extra)
    check("R7", "not_found_named_sources 3 items intact", r1["not_found_named_sources"] == tgt.get("not_found_named_sources"))
    check("R8", "acceptance_criterion_verbatim and exact_deliverable_verbatim intact",
          r1["acceptance_criterion_verbatim"] == tgt.get("acceptance_criterion_verbatim") and
          r1["exact_deliverable_verbatim"] == tgt.get("exact_deliverable_verbatim"))
    check("R9", "the three round-1 handoff strings still in the target", all(
        tgt.get("emergency_owner_handoff_CORRECTED", {}).get("round_1_material_restored_verbatim", {}).get(k) == v
        for k, v in three.items()))
    o1, ot = r1["old_run_fields_found"], tgt.get("old_run_fields_found_CARRIED", {})
    same_keys = sorted(k for k in o1 if o1[k] == ot.get(k))
    diff_keys = sorted(k for k in o1 if o1[k] != ot.get(k))
    check("R10", "old_run_fields_found: 8 records, 6 of 8 byte-identical to round 1, exactly the 2 reworded shape keys",
          len(o1) == len(ot) == 8 and len(same_keys) == 6
          and diff_keys == ["card_answers_dialect_A_current", "card_answers_dialect_B_legacy"],
          "identical %d of 8, differing %s" % (len(same_keys), diff_keys))
    check("R11", "what_remains_unverified still 10 items", len(tgt.get("what_remains_unverified", [])) == 10)
    check("R12", "does_not_establish still 6 items, byte-identical to round 2",
          tgt.get("does_not_establish") == n2 and len(tgt.get("does_not_establish", [])) == 6)
    check("R13", "described_changes_not_applied_CARRIED still 4 items, all applied:false",
          len(tgt.get("described_changes_not_applied_CARRIED", [])) == 4 and
          all(x.get("applied") is False for x in tgt.get("described_changes_not_applied_CARRIED", [])))

    # ---- 4b: edit surface, recomputed independently round 4 -> target ----
    def diff_paths(a, b, path="", changed=None, added=None, removed=None):
        changed = [] if changed is None else changed
        added = [] if added is None else added
        removed = [] if removed is None else removed
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k not in b:
                    removed.append(path + "." + k)
                else:
                    diff_paths(a[k], b[k], path + "." + k, changed, added, removed)
            for k in b:
                if k not in a:
                    added.append(path + "." + k)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                changed.append(path + " (list length %d -> %d)" % (len(a), len(b)))
            for i in range(min(len(a), len(b))):
                diff_paths(a[i], b[i], "%s[%d]" % (path, i), changed, added, removed)
        else:
            if a != b:
                changed.append(path)
        return changed, added, removed

    chg, add, rem = diff_paths(r4, {k: v for k, v in tgt.items() if k != "round_5_edit_surface"})
    ALLOWED = ("schema", "round", "generated_at", "mode", "supersedes.relationship", "reason_for_round_5",
               "carry_forward_table[8]", "carry_forward_table[15]", "carry_forward_table[16]",
               "carry_forward_table[17]", "carry_forward_table[18]",
               "CONFIRMED_PRESERVED.grouping_basis_source", "CONFIRMED_PRESERVED.grouping_numbers",
               "anything_i_mutated", "commands_run_this_round", "numbers_and_their_sources",
               "completeness_claim_audit", "round_5_measurements", "round_5_regression_set",
               "round_5_corrections", "round_5_pinned_hashes", "does_not_establish_round_5",
               "round_5_edit_surface")
    outside = [p for p in chg + add if not p.lstrip(".").startswith(tuple(x.lstrip(".") for x in ALLOWED))]
    check("S1", "no field deleted relative to the round-4 artefact (over-correction guard)",
          len(rem) == 0, "removed paths: %s" % (rem or "none"))
    check("S2", "every change falls inside the seven targeted edits (no drive-by edit)",
          len(outside) == 0, "outside paths: %s" % (outside or "none"))
    stored = tgt.get("round_5_edit_surface", {})
    check("S3", "target's stored edit-surface record equals the independent recomputation",
          stored.get("changed_paths") == sorted(chg) and stored.get("added_paths") == sorted(add)
          and stored.get("removed_paths") == sorted(rem) and stored.get("removed_paths_count") == len(rem),
          "stored changed=%d added=%d removed=%d vs recomputed changed=%d added=%d removed=%d"
          % (len(stored.get("changed_paths", [])), len(stored.get("added_paths", [])),
             len(stored.get("removed_paths", [])), len(chg), len(add), len(rem)))

    # ---- 5: controls ----
    print()
    check("C1", "KNOWN-GOOD CONTROL: a string that IS in the target is found by the same substring instrument",
          r1["exact_deliverable_verbatim"] in ttext and all(v in ttext for v in three.values()),
          "the instrument finds material that is present, so its absence reports are meaningful")
    mutated = ttext.replace("scoped per artifact and never fleet-wide", "scoped per artifact and never fleet_wide")
    check("C2", "INSTRUMENT CONTROL: the same substring instrument DETECTS a one-character mutation",
          mutated != ttext and ("scoped per artifact and never fleet-wide" in ttext) and
          ("scoped per artifact and never fleet_wide" not in ttext) and
          ("scoped per artifact and never fleet_wide" in mutated),
          "in-memory mutation detected before/after; the real file is unmodified")

    print()
    failed = [r for r in results if not r[2]]
    print("RESULT: %d checks, %d failed" % (len(results), len(failed)))
    for cid, desc, ok, detail in failed:
        print("  FAILED %s: %s" % (cid, desc))
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
