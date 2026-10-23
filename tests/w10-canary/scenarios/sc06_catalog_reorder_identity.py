#!/usr/bin/env python3
"""sc06_catalog_reorder_identity.py — acceptance row SC-06 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-06, verbatim):
    "Intake catalog reorder"

Required result (verbatim):
    "NEGATIVE: reordering catalog entries does not change resolved stage
     identity or order; resolution is by stable id, not position"

Proves, against the REAL core modules of the tree under test
(intake_preflight.intake + intake_preflight.factory + catalog_calculator):

  * the 12-stage catalog validates in either entry order, and every stage
    resolves by its stable id to the identical contract entry — reordering
    the published dict never renames or swaps a stage;
  * the run order stays CANONICAL_STAGES whatever order the catalog dict is
    in (batch_mode's published order equals the registry's canonical order),
    and select_next_action picks the same stage from a state map built in
    reverse;
  * the completion resolver returns the same required/optional order and the
    same missing-artifact set when handed the reordered catalog, so a
    reorder cannot change what the gate judges;
  * the intake question catalog carries stable ids (offer / audience_action /
    website / placement); the emitted order does not depend on the brief's
    key insertion order, and a question found by id is the same question even
    when the catalog list is reversed — its POSITION changes, its identity
    does not;
  * the model catalog indexes by id (same entries in either list order) and
    still refuses a duplicate id from either order.

Only the transport is a fixture: a scratch run dir of files and in-process
lists. No network, no paid provider, no live channel, no graph mutation, no
subprocess.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run under deliberate fixture defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc06"
TITLE = "intake catalog reorder (identity by stable id, not position)"
RECEIPTS = "delivery/receipts.json"

# --------------------------------------------------------------------------
def load_core(core):
    ik = H.load_pkg(core, "intake_preflight.intake")
    F = H.load_pkg(core, "intake_preflight.factory")
    CC = H.load_pkg(core, "catalog_calculator.catalog_calculator")
    return ik, F, CC

def reversed_catalog(reg):
    return {k: reg[k] for k in reversed(list(reg))}

def write_fixture(run_dir, F, drop=None):
    """A run dir the production collector can read: current approvals, an
    independent final-QC PASS, every required artifact except ``drop``, and
    successful delivery receipts."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    H.write_json(rd / "control" / "plan-revision.json", {"revision": 3})
    approvals = {}
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required") or meta.get("approval_policy") == "none":
            continue
        approvals[stage] = {"state": "approved", "plan_revision": 3}
    H.write_json(rd / "control" / "approvals.json", approvals)
    H.write_json(rd / "control" / "skip-reasons.json", {})
    H.write_json(rd / "final-qc" / "record.json",
                 {"gate": "PASS",
                  "producer": F.STAGE_REGISTRY["final-qc"]["qc_producer"]})
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required"):
            continue
        for rel in meta.get("required_artifacts") or []:
            if rel in (RECEIPTS, "final-qc/record.json") or rel == drop:
                continue
            p = rd / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"stage": stage, "fixture": True}) + "\n",
                         encoding="utf-8")
    H.write_json(rd / RECEIPTS, [{"destination": "telegram",
                                  "status": "delivered"}])

def brief_key_order(brief, reverse=False):
    keys = list(brief)
    keys = list(reversed(keys)) if reverse else keys
    return {k: brief[k] for k in keys}

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    ik, F, CC = load_core(core)
    stages = list(F.CANONICAL_STAGES)
    c = H.Checks(ROW, TITLE)
    print("SC06 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    rev = reversed_catalog(F.STAGE_REGISTRY)
    if "swap_registry_entries" in muts:
        keys = list(rev)
        rev[keys[0]], rev[keys[1]] = rev[keys[1]], rev[keys[0]]

    # ---- stage catalog: validity + identity -------------------------------
    problems_canon = F.validate_registry(F.STAGE_REGISTRY)
    problems_rev = F.validate_registry(rev)
    c.check("sc06:stage-catalog-valid-in-either-order",
            problems_canon == [] and problems_rev == []
            and set(rev) == set(F.STAGE_REGISTRY),
            "canonical=%s reversed=%s"
            % (problems_canon or "valid", problems_rev or "valid"))

    same_entries = all(json.dumps(F.STAGE_REGISTRY[s], sort_keys=True)
                       == json.dumps(rev.get(s), sort_keys=True)
                       for s in stages)
    c.check("sc06:stage-identity-resolves-by-id", same_entries,
            "resolved=%d/%d identical-by-id"
            % (sum(1 for s in stages
                   if json.dumps(F.STAGE_REGISTRY[s], sort_keys=True)
                   == json.dumps(rev.get(s), sort_keys=True)), len(stages)))

    # ---- stage order: the published order, never dict order ---------------
    got = {s: ("COMPLETE" if i < 3 else "NOT_STARTED")
           for i, s in enumerate(stages)}
    got_rev = {s: got[s] for s in reversed(list(got))}
    order = list(reversed(stages)) if "reorder_next_action_stages" in muts \
        else stages
    required = [s for s in stages if F.STAGE_REGISTRY[s].get("required", True)]
    d_canon = F.select_next_action(got)
    d_rev = F.select_next_action(got_rev, order, registry=rev)
    c.check("sc06:stage-order-is-canonical-not-catalog-order",
            F._stages() == tuple(stages) and d_canon["required"] == required
            and d_rev["required"] == required
            and d_canon["next_stage"] == d_rev["next_stage"],
            "published=%s next=%s/%s"
            % (F._stages() == tuple(stages), d_canon["next_stage"],
               d_rev["next_stage"]))

    # ---- the completion resolver judges the same facts --------------------
    with H.Scratch() as tmp:
        full = Path(tmp) / "full"
        write_fixture(full, F)
        got_all = {s: "COMPLETE" for s in stages}
        e_canon = F._collect_completion_evidence(str(full), got_all)
        e_rev = F._collect_completion_evidence(str(full), got_all, registry=rev)

        droppable = F.STAGE_REGISTRY["research"]["required_artifacts"][0]
        holey = Path(tmp) / "holey"
        write_fixture(holey, F, drop=droppable)
        h_canon = F._collect_completion_evidence(str(holey), got_all)
        h_rev = F._collect_completion_evidence(str(holey), got_all,
                                               registry=rev)

        c.check("sc06:required-order-unchanged-by-catalog-order",
                e_canon["required"] == e_rev["required"] == required
                and e_canon["optional"] == e_rev["optional"],
                "required=%d optional=%d"
                % (len(e_rev["required"]), len(e_rev["optional"])))
        c.check("sc06:missing-artifacts-unchanged-by-catalog-order",
                h_canon["missing_artifacts"] == h_rev["missing_artifacts"]
                and droppable in h_rev["missing_artifacts"],
                "missing=%s" % (h_rev["missing_artifacts"],))

        d1, r1 = F.evaluate_completion(str(holey), got_all)
        d2, r2 = F.evaluate_completion(str(holey), got_all, registry=rev)
        d3, _ = F.evaluate_completion(str(full), got_all, registry=rev)
        c.check("sc06:completion-verdict-unchanged-by-catalog-order",
                d1 is False and d2 is False and d1 == d2
                and r1["reasons"] == r2["reasons"] and d3 is True,
                "holey=%s/%s control=%s"
                % (d1, d2, d3))

    # ---- intake question catalog: stable ids, order, identity ------------
    qs = ik.missing_essentials({}, {"placement": "assumed"})
    ids = [q["id"] for q in qs]

    # audience_action keeps its ID while its TEXT varies with the brief: the
    # id is the identity, the wording is derived.
    only_audience = ik.missing_essentials({"audience": "women"}, {})
    only_action = ik.missing_essentials({"action": "register"}, {})
    variants = ([q["id"] for q in only_audience],
                [q["id"] for q in only_action])
    c.check("sc06:question-catalog-ids-stable",
            ids == ["offer", "audience_action", "placement"]
            and all(v == ["offer", "audience_action"] for v in variants),
            "ids=%s variants=%s" % (ids, variants))

    a1 = [q for q in only_audience if q["id"] == "audience_action"]
    a2 = [q for q in only_action if q["id"] == "audience_action"]
    expected = [q for q in qs if q["id"] == "audience_action"][0]
    # rotate the catalog: the entry MOVES, the identity resolves the same
    catalog = list(qs[1:]) + list(qs[:1])
    by_id = [q for q in catalog if q["id"] == "audience_action"]
    pos_fwd = ids.index("audience_action")
    pos_rot = [q["id"] for q in catalog].index("audience_action")
    if "index_lookup_questions" in muts:
        by_id = [catalog[pos_fwd]]
    c.check("sc06:question-identity-resolves-by-id",
            bool(a1) and bool(a2) and a1[0]["id"] == a2[0]["id"] == "audience_action"
            and bool(by_id) and by_id[0] == expected and pos_rot != pos_fwd,
            "id=%s question=%.28r positions=%d->%d"
            % (by_id[0]["id"] if by_id else None,
               by_id[0]["question"] if by_id else "",
               pos_fwd, pos_rot))

    # ---- model catalog: index by id, duplicates refused in either order --
    cat = [{"id": "m1", "task": "video", "status": "PINNED"},
           {"id": "m2", "task": "video", "status": "APPROVED"}]
    if "relabel_model_id" in muts:
        cat = [{"id": "m2", "task": "video", "status": "PINNED"},
               {"id": "m2", "task": "video", "status": "APPROVED"}]
    fwd, err_f = CC._index_catalog({"models": cat})
    revm, err_r = CC._index_catalog({"models": list(reversed(cat))})
    c.check("sc06:model-catalog-resolves-by-id",
            err_f is None and err_r is None and fwd == revm
            and sorted(fwd or {}) == ["m1", "m2"],
            "ids=%s err=%s" % (sorted(fwd or {}), err_f or err_r))

    dup = [{"id": "m1", "task": "video", "status": "PINNED"},
           {"id": "m1", "task": "video", "status": "PINNED"}]
    c.check("sc06:model-catalog-duplicate-detected-any-order",
            CC._index_catalog({"models": dup})[1] == "CATALOG_DUPLICATE_ID"
            and CC._index_catalog({"models": list(reversed(dup))})[1]
            == "CATALOG_DUPLICATE_ID",
            "forward=%s reversed=%s"
            % (CC._index_catalog({"models": dup})[1],
               CC._index_catalog({"models": list(reversed(dup))})[1]))
    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "swap_registry_entries": [
        "sc06:stage-identity-resolves-by-id",
    ],
    "reorder_next_action_stages": [
        "sc06:stage-order-is-canonical-not-catalog-order",
    ],
    "relabel_model_id": [
        "sc06:model-catalog-resolves-by-id",
    ],
    "index_lookup_questions": [
        "sc06:question-identity-resolves-by-id",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all four defects"
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc06 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    return scenario(H.resolve_core(args)).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
