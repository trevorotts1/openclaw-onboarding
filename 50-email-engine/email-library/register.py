#!/usr/bin/env python3
# =============================================================================
# 50-email-engine/email-library/register.py
# -----------------------------------------------------------------------------
# Library register / coverage check for the Email Superlibrary (the verify.sh
# "register --check" leg, mirroring Skill 23's register-library-additions.py).
#
# Fail-closed, stdlib-only. Proves:
#   * catalog-index.json is a list of 44 entries with the expected type census
#     (13 framework / 4 buyer-type / 5 objective / 12 persona-style / 10 sequence);
#   * EVERY entry has its paired on-disk <group>/<id>.json + <id>.md;
#   * every <id>.json carries a non-empty tags[] and a rules{} block with a kind;
#   * catalog-built-index.json is in sync (entryCount == 44, all ids present);
#   * the set FULLY COVERS the prover's maps — every one of prove-email.py's 13
#     canonical FRAMEWORKS, 12 PERSONA_STYLES and 5 OBJECTIVES ids, the three
#     legacy sequence types (landing_page_10 / high_ticket_12 / buyer_type_12)
#     and EVERY launch family in profiles/launch-email-families.json is
#     represented, each family's sequence_record is a registered catalog entry
#     whose id is "sequence-" + its sequence_position (the P1 selection gate's
#     rule), and every registered count variant's framework map is valid.
#
# USAGE:  python3 register.py --check     (exit 0 = all good; nonzero = fail)
# =============================================================================
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CATALOG = os.path.join(HERE, "catalog-index.json")
BUILT = os.path.join(HERE, "catalog-built-index.json")
PROVER = os.path.join(SKILL, "tools", "prove-email.py")

GROUP = {"framework": "frameworks", "buyer-type": "buyer-types",
         "objective": "objectives", "persona-style": "persona-styles",
         "sequence": "sequences"}
EXPECTED_CENSUS = {"framework": 13, "buyer-type": 4, "objective": 5,
                   "persona-style": 12, "sequence": 10}
LEGACY_SEQ_TYPES = {"landing_page_10", "high_ticket_12", "buyer_type_12"}


def _load_prover():
    spec = importlib.util.spec_from_file_location("prove_email", PROVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check():
    fails = []
    if not os.path.isfile(CATALOG):
        return ["catalog-index.json not found at %s" % CATALOG]
    catalog = json.load(open(CATALOG, encoding="utf-8"))
    if not isinstance(catalog, list):
        return ["catalog-index.json is not a list"]

    census = {}
    fw_ids, persona_ids, seq_types, obj_ids = set(), set(), set(), set()
    for e in catalog:
        t = e.get("type")
        census[t] = census.get(t, 0) + 1
        group = GROUP.get(t)
        if not group:
            fails.append("%s: unknown type %r" % (e.get("id"), t)); continue
        j = os.path.join(HERE, group, e["id"] + ".json")
        m = os.path.join(HERE, group, e["id"] + ".md")
        if not os.path.isfile(j):
            fails.append("%s: missing paired json (%s/%s.json)" % (e["id"], group, e["id"]))
            continue
        if not os.path.isfile(m):
            fails.append("%s: missing paired md (%s/%s.md)" % (e["id"], group, e["id"]))
        spec = json.load(open(j, encoding="utf-8"))
        if not (isinstance(spec.get("tags"), list) and spec["tags"]):
            fails.append("%s: empty/absent tags[]" % e["id"])
        rules = spec.get("rules")
        if not (isinstance(rules, dict) and rules.get("kind")):
            fails.append("%s: absent/invalid rules{} block" % e["id"])
            rules = rules or {}
        if t == "framework" and rules.get("framework_id"):
            fw_ids.add(rules["framework_id"])
        if t == "persona-style" and rules.get("persona_style_id"):
            persona_ids.add(rules["persona_style_id"])
        if t == "sequence" and rules.get("sequence_type"):
            seq_types.add(rules["sequence_type"])
        if t == "sequence" and rules.get("profile"):
            seq_types.add(rules["profile"])
        if t == "objective" and rules.get("objective_id"):
            obj_ids.add(rules["objective_id"])

    for t, n in EXPECTED_CENSUS.items():
        if census.get(t, 0) != n:
            fails.append("type census: %s = %d, expected %d" % (t, census.get(t, 0), n))
    if len(catalog) != sum(EXPECTED_CENSUS.values()):
        fails.append("catalog has %d entries, expected %d" % (len(catalog), sum(EXPECTED_CENSUS.values())))

    # built index sync
    if not os.path.isfile(BUILT):
        fails.append("catalog-built-index.json not found (run: email_matcher_cli.py --build-index)")
    else:
        built = json.load(open(BUILT, encoding="utf-8"))
        ids_cat = {e["id"] for e in catalog}
        ids_built = {e["id"] for e in built.get("entries", [])}
        if built.get("entryCount") != len(catalog):
            fails.append("built index entryCount %s != catalog %d" % (built.get("entryCount"), len(catalog)))
        missing = ids_cat - ids_built
        if missing:
            fails.append("built index missing ids: %s" % ", ".join(sorted(missing)))

    # coverage vs the prover's SACRED maps
    try:
        pv = _load_prover()
        miss_fw = set(pv.FRAMEWORKS) - fw_ids
        if miss_fw:
            fails.append("frameworks NOT covered by the library: %s" % ", ".join(sorted(miss_fw)))
        miss_p = set(pv.PERSONA_STYLES) - persona_ids
        if miss_p:
            fails.append("persona styles NOT covered by the library: %s" % ", ".join(sorted(miss_p)))
        miss_o = set(pv.OBJECTIVES) - obj_ids
        if miss_o:
            fails.append("objectives NOT covered by the library: %s" % ", ".join(sorted(miss_o)))
        families = pv.launch_profiles.families(pv.launch_profiles.load_registry())
    except Exception as exc:  # pragma: no cover
        fails.append("could not load prover/registry to cross-check coverage: %s" % exc)
        families = {}
    ids_cat = {e.get("id") for e in catalog}
    for kind, fam in families.items():
        rid = os.path.basename(fam["sequence_record"])[:-len(".json")]
        if rid not in ids_cat:
            fails.append("launch family %s record %s is not a catalog entry" % (kind, rid))
        if rid != "sequence-" + fam["sequence_position"]:
            fails.append("launch family %s record id %s is not 'sequence-' + its "
                         "sequence_position %r (the P1 selection gate would refuse it)"
                         % (kind, rid, fam["sequence_position"]))
        for n, var in (fam.get("count_variants") or {}).items():
            for fw in [var.get("framework_map")] + list((var.get("pattern_maps") or {}).values()):
                bad = sorted(set((fw or {}).values()) - fw_ids)
                if bad:
                    fails.append("launch family %s count variant %s uses unknown framework(s): %s"
                                 % (kind, n, ", ".join(bad)))
    miss_seq = (LEGACY_SEQ_TYPES | {f["profile"] for f in families.values()}) - seq_types
    if miss_seq:
        fails.append("sequence types NOT covered: %s" % ", ".join(sorted(miss_seq)))

    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description="Email Superlibrary register/coverage check.")
    ap.add_argument("--check", action="store_true", help="run the fail-closed register check")
    args = ap.parse_args(argv)
    if not args.check:
        ap.error("use --check")
    fails = check()
    if not fails:
        print("== email-library register --check: PASS ==")
        print("   44 entries, all paired (json+md), built index in sync, prover maps fully covered "
              "(13 frameworks / 12 personas / 5 objectives / 3 legacy sequence types + every "
              "launch family and count variant).")
        return 0
    print("== email-library register --check: FAIL — %d issue(s) ==" % len(fails))
    for f in fails:
        print("  - %s" % f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
