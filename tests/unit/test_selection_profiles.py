#!/usr/bin/env python3
"""Unit JEV-013: selection profiles (JEV spec 1.1, sections 6.1-6.4, 7.1-7.4).

Two fake companies with fully custom departments prove derivation from
caller-supplied config, never a hardcoded roster. Stdlib only.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(
        name, REPO / path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


P = load("shared-utils/decision_engine/profiles/profiles.py", "jev13_profiles")


def dept(dept_id, name=None, **kw):
    name = name if name is not None else "Dept %s" % dept_id
    base = {
        "department_id": dept_id,
        "display_name": name,
        "purpose": "purpose of %s" % dept_id,
        "owned_outcomes": ["outcome-%s" % dept_id],
        "exclusions": [],
        "capabilities": ["cap-%s" % dept_id],
        "neighbors": [],
        "source_text": "config text for %s" % dept_id,
        "source_file": "company.yaml",
        "source_section": "departments.%s" % dept_id,
    }
    base.update(kw)
    return base


# Fake company A: 3 custom departments (aquaculture themed, no legacy names).
COMPANY_A = "acme-aqua-01"
ROSTER_A = [
    dept("kelp-farming", "Kelp Farming",
         owned_outcomes=["harvest schedule", "kelp yield report"],
         capabilities=["tide planning", "harvest logistics"]),
    dept("tide-logistics", "Tide Logistics",
         owned_outcomes=["delivery slots"],
         capabilities=["route planning"],
         neighbors=["kelp-farming"]),
    dept("brine-qa", "Brine QA",
         owned_outcomes=["salinity audit"],
         capabilities=["lab testing"],
         exclusions=["production harvest"]),
]

# Fake company B: 5 different custom departments (observatory themed).
COMPANY_B = "beacon-observatory-02"
ROSTER_B = [
    dept("mirror-alignment"),
    dept("night-scheduling", owned_outcomes=["telescope calendar"]),
    dept("photon-accounting"),
    dept("dome-maintenance", capabilities=["crane ops", "servo repair"]),
    dept("comet-outreach", purpose="public night programs",
         owned_outcomes=["star party newsletter"]),
]

THRESHOLD = 0.5


def role(role_id, dept_id="kelp-farming", **kw):
    base = {
        "role_id": role_id,
        "role_slug": role_id,
        "department_id": dept_id,
        "responsibilities": ["plan %s tides" % role_id],
        "owned_outcomes": ["harvest schedule"],
        "deliverable_types": ["email", "report"],
        "capabilities": ["tide planning"],
        "exclusions": [],
        "source_text": "role doc for %s" % role_id,
        "source_file": "roles/%s.md" % role_id,
        "source_section": "responsibilities",
    }
    base.update(kw)
    return base


def runtime(company=COMPANY_A, workers=("w1",), status="active"):
    return {"company_id": company,
            "availability": {"status": status,
                             "eligible_worker_ids": list(workers)}}


class DeptEligibility(unittest.TestCase):
    def test_custom_roster_passes_through_sorted(self):
        got = P.eligible_department_candidates(ROSTER_A, company_id=COMPANY_A)
        self.assertEqual([c["department_id"] for c in got],
                         ["brine-qa", "kelp-farming", "tide-logistics"])

    def test_second_company_different_custom_roster(self):
        got = P.eligible_department_candidates(ROSTER_B, company_id=COMPANY_B)
        self.assertEqual(len(got), 5)
        self.assertIn("comet-outreach", [c["department_id"] for c in got])

    def test_no_hardcoded_roster_sizes(self):
        # Arbitrary sizes (2 and 31) flow through untouched: no 17/26/96 gate.
        small = [dept("d-%d" % i) for i in range(2)]
        big = [dept("e-%02d" % i) for i in range(31)]
        self.assertEqual(
            len(P.eligible_department_candidates(small, company_id="c1")), 2)
        self.assertEqual(
            len(P.eligible_department_candidates(big, company_id="c1")), 31)

    def test_active_ids_narrow_roster(self):
        got = P.eligible_department_candidates(
            ROSTER_A, company_id=COMPANY_A, active_ids=["brine-qa"])
        self.assertEqual([c["department_id"] for c in got], ["brine-qa"])

    def test_candidate_fields_canonical_and_derived(self):
        got = P.eligible_department_candidates(ROSTER_A, company_id=COMPANY_A)
        kelp = next(c for c in got if c["department_id"] == "kelp-farming")
        self.assertEqual(set(kelp), set(P.DEPT_CANDIDATE_FIELDS))
        self.assertEqual(kelp["display_name"], "Kelp Farming")
        self.assertEqual(kelp["owned_outcomes"],
                         ["harvest schedule", "kelp yield report"])
        self.assertEqual(kelp["capabilities"], ["tide planning", "harvest logistics"])
        self.assertEqual(kelp["neighbors"], [])
        tide = next(c for c in got if c["department_id"] == "tide-logistics")
        self.assertEqual(tide["neighbors"], ["kelp-farming"])
        brine = next(c for c in got if c["department_id"] == "brine-qa")
        self.assertEqual(brine["exclusions"], ["production harvest"])

    def test_unresolvable_dept_id_raises(self):
        with self.assertRaises(ValueError):
            P.build_department_candidate({"display_name": "No Id",
                                          "source_text": "x"},
                                         company_id=COMPANY_A)

    def test_hash_changes_when_source_changes(self):
        a = P.build_department_candidate(dept("k1", source_text="v1"),
                                         company_id=COMPANY_A)
        b = P.build_department_candidate(dept("k1", source_text="v2"),
                                         company_id=COMPANY_A)
        self.assertNotEqual(P.profile_hash(a), P.profile_hash(b))
        ha = a["sources"][0]["content_hash"]
        hb = b["sources"][0]["content_hash"]
        self.assertNotEqual(ha, hb)
        self.assertEqual(ha, P.content_hash("v1"))


class DeptResolution(unittest.TestCase):
    def test_none_suitable_below_threshold(self):
        out = P.resolve_department_selection({"kelp-farming": 0.2},
                                             threshold=THRESHOLD)
        self.assertEqual(out, P.NONE_SUITABLE)

    def test_split_scores_do_not_imply_multi(self):
        # Near-tie 0.9 vs 0.89 with no explicit judgment: winner, not split.
        out = P.resolve_department_selection(
            {"kelp-farming": 0.9, "tide-logistics": 0.89}, threshold=THRESHOLD)
        self.assertEqual(out, "kelp-farming")
        self.assertNotEqual(out, P.NEEDS_MULTIPLE_DEPARTMENTS)

    def test_explicit_multi_judgment_distinct(self):
        out = P.resolve_department_selection(
            {"kelp-farming": 0.9, "tide-logistics": 0.89},
            threshold=THRESHOLD, multi_department=True)
        self.assertEqual(out, P.NEEDS_MULTIPLE_DEPARTMENTS)
        self.assertNotEqual(P.NEEDS_MULTIPLE_DEPARTMENTS, P.NONE_SUITABLE)

    def test_owner_preference_outranks_semantics(self):
        out = P.resolve_department_selection(
            {"kelp-farming": 0.95, "tide-logistics": 0.6},
            threshold=THRESHOLD, owner_preferred="tide-logistics")
        self.assertEqual(out, "tide-logistics")

    def test_unavailable_explicit_request_raises_not_replaced(self):
        with self.assertRaises(ValueError):
            P.resolve_department_selection({"kelp-farming": 0.9},
                                           threshold=THRESHOLD,
                                           owner_preferred="ghost-dept")


class RoleProfiles(unittest.TestCase):
    def test_role_fields_exactly_spec_72(self):
        prof = P.build_role_profile(role("tide-master"), runtime=runtime())
        self.assertEqual(set(prof), set(P.ROLE_PROFILE_FIELDS))
        self.assertEqual(prof["role_id"], "tide-master")
        self.assertEqual(prof["role_slug"], "tide-master")
        self.assertEqual(prof["company_id"], COMPANY_A)
        self.assertEqual(prof["department_id"], "kelp-farming")
        self.assertEqual(prof["availability"]["eligible_worker_ids"], ["w1"])

    def test_sources_carry_file_section_hash(self):
        prof = P.build_role_profile(
            role("tide-master",
                 sources=[{"file": "roles/tide-master.md",
                           "section": "s2",
                           "content": "do tides"}]),
            runtime=runtime())
        src = prof["sources"][0]
        self.assertEqual(src["file"], "roles/tide-master.md")
        self.assertEqual(src["section"], "s2")
        self.assertEqual(src["content_hash"], P.content_hash("do tides"))

    def test_role_hash_changes_when_source_changes(self):
        a = P.build_role_profile(role("r1", source_text="doc v1"),
                                 runtime=runtime())
        b = P.build_role_profile(role("r1", source_text="doc v2"),
                                 runtime=runtime())
        self.assertNotEqual(P.profile_hash(a), P.profile_hash(b))

    def test_capability_fit_input_has_no_load(self):
        fit = P.CapabilityFitInput(
            outcome="harvest schedule", artifact_type="email",
            constraints=("before friday",), department_id="kelp-farming",
            sop_context=("sop-7",),
            worker_responsibilities=("plan tides",))
        self.assertFalse(hasattr(fit, "queue_depth"))
        self.assertFalse(hasattr(fit, "available"))

    def test_idle_unqualified_never_beats_qualified(self):
        qualified = P.build_role_profile(
            role("tide-master", responsibilities=["plan harvest tides",
                                                  "write harvest schedule"]),
            runtime=runtime(workers=("busy-w1",)))
        unqualified = P.build_role_profile(
            role("comet-greeter", dept_id="comet-outreach",
                 responsibilities=["greet star party guests"],
                 owned_outcomes=["star party newsletter"],
                 deliverable_types=["flyer"], capabilities=["public speaking"],
                 source_text="greeter doc"),
            runtime=runtime(company=COMPANY_B, workers=("idle-w9",)))
        fit = P.CapabilityFitInput(outcome="harvest schedule tides plan",
                                   department_id="kelp-farming")
        ranked = P.rank_roles(fit, [unqualified, qualified])
        self.assertEqual(ranked[0][0], "tide-master")
        # Load struct exists but never enters the fit score.
        load_idle = P.WorkerLoad(worker_id="idle-w9", available=True, queue_depth=0)
        load_busy = P.WorkerLoad(worker_id="busy-w1", available=True, queue_depth=9)
        self.assertGreater(load_busy.queue_depth, load_idle.queue_depth)
        self.assertEqual(P.rank_roles(fit, [unqualified, qualified]), ranked)

    def test_acceptance_gate_refuses_weak_winner(self):
        self.assertEqual(P.accept_role([("r1", 0.1)], threshold=THRESHOLD),
                         P.NONE_SUITABLE)
        self.assertEqual(P.accept_role([], threshold=THRESHOLD),
                         P.NONE_SUITABLE)
        self.assertEqual(P.accept_role([("r1", 0.9)], threshold=THRESHOLD), "r1")


class Exclusions(unittest.TestCase):
    ALLOWED = ["fleet-mac", "fleet-vps"]

    def w(self, wid, **kw):
        base = {"worker_id": wid, "company_id": COMPANY_A,
                "status": "active", "runtime": "fleet-mac",
                "qc_only": False}
        base.update(kw)
        return base

    def test_foreign_company_excluded(self):
        self.assertEqual(
            P.exclusion_for(self.w("x", company_id="other-co"),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED),
            P.REASON_FOREIGN_COMPANY)

    def test_offline_excluded(self):
        self.assertEqual(
            P.exclusion_for(self.w("x", status="offline"),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED),
            P.REASON_WORKER_OFFLINE)

    def test_retired_excluded(self):
        self.assertEqual(
            P.exclusion_for(self.w("x", status="retired"),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED),
            P.REASON_WORKER_OFFLINE)

    def test_unauthorized_runtime_excluded(self):
        self.assertEqual(
            P.exclusion_for(self.w("x", runtime="rogue-box"),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED),
            P.REASON_RUNTIME_UNAUTHORIZED)

    def test_qc_only_excluded_from_production(self):
        self.assertEqual(
            P.exclusion_for(self.w("x", qc_only=True),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED),
            P.REASON_QC_ONLY_PRODUCTION)

    def test_busy_is_not_an_exclusion(self):
        self.assertIsNone(
            P.exclusion_for(dict(self.w("x"), queue_depth=99, busy=True),
                            company_id=COMPANY_A, allowed_runtimes=self.ALLOWED))

    def test_owner_direct_exception_is_own_path(self):
        workers = [self.w("foreigner", company_id="other-co"),
                   self.w("off", status="offline"),
                   self.w("qc", qc_only=True),
                   self.w("ok")]
        out = P.eligible_workers(workers, company_id=COMPANY_A,
                                 allowed_runtimes=self.ALLOWED,
                                 owner_direct=True)
        self.assertEqual(out["eligible"],
                         ["foreigner", "off", "ok", "qc"])
        self.assertEqual(out["excluded"], [])
        self.assertTrue(out["owner_direct_exception"])

    def test_production_split_reports_reasons_sorted(self):
        workers = [self.w("z-ok"), self.w("a-foreign", company_id="other-co"),
                   self.w("m-off", status="offline"),
                   self.w("q-qc", qc_only=True),
                   self.w("r-rogue", runtime="rogue-box")]
        out = P.eligible_workers(workers, company_id=COMPANY_A,
                                 allowed_runtimes=self.ALLOWED)
        self.assertEqual(out["eligible"], ["z-ok"])
        self.assertFalse(out["owner_direct_exception"])
        reasons = {e["worker_id"]: e["reason"] for e in out["excluded"]}
        self.assertEqual(reasons, {
            "a-foreign": P.REASON_FOREIGN_COMPANY,
            "m-off": P.REASON_WORKER_OFFLINE,
            "q-qc": P.REASON_QC_ONLY_PRODUCTION,
            "r-rogue": P.REASON_RUNTIME_UNAUTHORIZED,
        })


if __name__ == "__main__":
    unittest.main()
