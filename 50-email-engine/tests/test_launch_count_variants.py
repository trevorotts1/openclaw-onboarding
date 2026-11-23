#!/usr/bin/env python3
"""RFX-003 (BUG-098): registered launch-family count variants, catalog
registration for every family, and one word_band_override shape.

A client launch plan approved 3 main_launch, 1 doors_closing, 10 welcome_access
(one transactional welcome + nine non-selling event nurture emails) and 2
upsell_followup emails. The registry fixed 10 / 3 / 2 / 3, so the adapter
refused the plan, and the P1 selection gate refused every family but the main
landing-10 because the catalog did not register them. This proves:

  (a) a 3/1/10/2 plan adapts, each brief locked at its planned count, and the
      prover, the emitter, the P1 gate and Skill 44's reader accept it;
  (b) a count the registry does not register is still refused (adapter,
      prover, emitter), and the default counts and maps are unchanged;
  (c) word_band_override round-trips: the adapter emits the [min, max] list
      the prover honors, a legacy {min, max} object normalizes to it, and a
      malformed band is refused.

Hermetic: fictional fixtures, temp dirs only, no network.
Run: python3 50-email-engine/tests/test_launch_count_variants.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TOOLS = SKILL / "tools"
sys.path.insert(0, str(TOOLS))

import launch_intake_adapter as adapter  # noqa: E402
import launch_profiles  # noqa: E402
import s49_launch_shape as s49  # noqa: E402

PROVER = TOOLS / "prove-email.py"
FOUNDER = "Jordan Marsh"
CLIENT_PLAN = {"main_launch": 3, "doors_closing": 1, "welcome_access": 10,
               "upsell_followup": 2}
FAMILIES = launch_profiles.families()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


emitter = _load("rfx003_emit_build_plan", TOOLS / "emit_build_plan.py")
engine = _load("rfx003_run_email_engine", SKILL / "run_email_engine.py")


def _plan(counts):
    plan = adapter.build_launch_plan_fixture()
    for unit in plan["email_sequences"]:
        unit["email_count"] = counts.get(unit["kind"], unit["email_count"])
    return plan


def _adapt(plan, fx=None):
    fx = fx or adapter.build_fixtures()
    return {a["kind"]: a["brief"] for a in adapter.adapt_launch_plan(
        fx["session"], fx["launch"], fx["approval"], fx["brand_facts"],
        fx["landing_facts"], plan, worker_identity_ref=fx["worker_identity_ref"])}


_FILLER = ("steady progress comes from small promises kept daily and measured "
           "honestly over time with patience and care for the people involved").split()


def _body(words, ctas, placed):
    if placed:  # PASTOR slots: CTA at the start, middle and end of the body
        parts = [" ".join((_FILLER * 3)[:45]), ctas[0], " ".join((_FILLER * 4)[:55]),
                 ctas[1], " ".join((_FILLER * 3)[:45]), ctas[2], " ".join(_FILLER[:10]), FOUNDER]
        return "\n\n".join(parts)
    text = " ".join(["value"] * max(1, words - 6))
    paras = [" ".join(text.split()[i:i + 30]) for i in range(0, len(text.split()), 30)]
    return ("{{contact.first_name}},\n\n" + "\n\n".join(p + "." for p in paras)
            + "\n\n" + ctas[0] + "\n\n" + FOUNDER)


_SECTIONS = {
    "pastor-solutions": ["Problem", "Amplify", "Story", "Transformation", "Offer", "Response"],
}


def _emails(brief, pattern=None):
    """An authored sequence shaped exactly by the brief's locked family block."""
    fam = brief["family"]
    full = launch_profiles.resolve(launch_profiles.family_for(fam["profile"]),
                                   fam["email_count"])
    fmap = launch_profiles.framework_map(full, pattern)
    emails = []
    for slot in range(1, fam["email_count"] + 1):
        band = launch_profiles.word_band(full, slot, pattern)
        floor = launch_profiles.cta_floor(full, slot)
        ctas = ["Take step %d now" % (n + 1) for n in range(floor)]
        email = {
            "e_slot": slot, "framework": fmap[slot], "objective": full["objective"],
            "subjects": ["{{contact.first_name}}, the quiet cost of waiting a week",
                         "Everyone booked it but you last call now"],
            "previews": ["Pair A preview line %d" % slot,
                         "Pair B preview line %d" % slot][:full["preview_count"]],
            "body": _body(90 if band[1] < 150 else 200, ctas, floor >= 3),
            "ctas": ctas,
        }
        if full.get("strict_review"):
            email.update({"sections": _SECTIONS[fmap[slot]], "merge_fallback": "friend",
                          "review_label": "P.A.S.T.O.R. V1 (Solutions)",
                          "pain_ref": "landing.section6.pain.%d" % slot})
        emails.append(email)
    doc = {"sequence_type": full["profile"], "profile": full["profile"],
           "sequence_id": full["sequence_id"], "founder_name": FOUNDER, "emails": emails}
    if pattern:
        doc["pattern"] = pattern
    return doc


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, doc):
        path = self.dir / name
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return path

    def prove(self, target, brief=None, kind="sequence"):
        args = [sys.executable, str(PROVER), str(target), "--kind", kind, "--json"]
        if brief is not None:
            args += ["--brief", str(brief)]
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout or "{}")


class ClientPlanIsAccepted(_Tmp):
    def test_registry_registers_the_client_counts(self):
        for kind, n in CLIENT_PLAN.items():
            self.assertIn(n, launch_profiles.allowed_email_counts(FAMILIES[kind]), kind)

    def test_adapter_locks_each_brief_at_its_planned_count(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        for kind, n in CLIENT_PLAN.items():
            self.assertEqual(briefs[kind]["family"]["email_count"], n, kind)
            self.assertEqual(briefs[kind]["family"]["count_variant"], str(n), kind)
            self.assertEqual(len(briefs[kind]["family"]["framework_map"]), n, kind)
        self.assertEqual(briefs["welcome_access"]["answers"]["objective"], "transactional")

    def test_prover_accepts_brief_and_sequence_at_the_variant_counts(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        for kind in CLIENT_PLAN:
            bpath = self.write("brief-%s.json" % kind, briefs[kind])
            rc, out = self.prove(bpath, kind="intake")
            self.assertEqual(rc, 0, (kind, out))
            patterns = ["upsell_1", "upsell_2"] if kind == "upsell_followup" else [None]
            for pattern in patterns:
                epath = self.write("emails-%s-%s.json" % (kind, pattern),
                                   _emails(briefs[kind], pattern))
                rc, out = self.prove(epath, bpath)
                self.assertEqual(rc, 0, (kind, pattern, out))

    def test_emitter_carries_the_variant_count_and_timing(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        for kind, n in CLIENT_PLAN.items():
            plan = emitter.build_plan(briefs[kind], _emails(briefs[kind]))
            self.assertEqual(emitter.validate_plan(plan), [], kind)
            meta = plan["_meta"]
            self.assertEqual((meta["email_count"], meta["expected_email_count"],
                              meta["count_variant"]), (n, n, str(n)), kind)
            self.assertEqual(len(meta["timing_anchors"]["steps"]), n - 1, kind)

    def test_p1_selection_gate_accepts_every_family(self):
        briefs = _adapt(adapter.build_launch_plan_fixture())
        for kind, brief in briefs.items():
            match = {"skill": "email-engine", "resolved": {
                "sequence_id": "sequence-" + brief["answers"]["sequence_position"],
                "objective_id": "objective-" + brief["answers"]["objective"],
                "buyer_type_id": "all",
                "framework_ids": ["framework-" + f for f in
                                  sorted(set(FAMILIES[kind]["framework_map"].values()))],
                "persona_style_id": None}}
            self.assertEqual(engine._email_match_violations(match, brief), [], kind)

    def test_skill_44_reader_does_not_block_the_variant_counts(self):
        reader = _load("rfx003_plan_reader", SKILL.parent / "44-convert-and-flow-operator"
                       / "automation-templates" / "launch-c" / "plan_reader.py")
        plan = _plan(CLIENT_PLAN)
        briefs = _adapt(plan)
        argv = []
        seq_map = {}
        for unit in plan["email_sequences"]:
            doc = emitter.build_plan(briefs[unit["kind"]], _emails(briefs[unit["kind"]]))
            path = self.write("build-%s.json" % unit["id"], doc)
            seq_map[unit["id"]] = str(path)
            argv += ["--build-plan", str(path)]
        plan_path = self.write("launch-plan.json", plan)
        out = self.dir / "automation-builds.json"
        rc = reader.main(["--launch-plan", str(plan_path), "--sequence-map",
                          str(self.write("map.json", seq_map)), "--out", str(out),
                          "--now", "2026-10-01T00:00:00-04:00"] + argv)
        self.assertIn(rc, (0, 4))
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual([w for w in document["warnings"]
                          if w.get("code") == "EMAIL-COUNT-MISMATCH"], [])
        self.assertEqual(document["unused_build_plan_workflows"], [])
        # The reader's own per-sequence count gate (what an automation waiting on
        # each sequence would hit) passes at every planned count.
        read = reader.read_launch_plan(plan)
        bound, _ = reader.bind_build_plans(list(seq_map.values()),
                                           list(read["email_sequences"]), seq_map)
        for unit in plan["email_sequences"]:
            self.assertIsNone(reader._dependency_blocker(unit["id"], read, bound, {}),
                              unit["id"])


class UnregisteredCountsAreRefused(_Tmp):
    def test_defaults_are_unchanged(self):
        want = {"pre_launch": 5, "main_launch": 10, "doors_closing": 3, "upsell_followup": 3,
                "downsell_followup": 3, "abandoned_checkout": 3, "welcome_access": 2}
        self.assertEqual({k: f["email_count"] for k, f in FAMILIES.items()}, want)
        self.assertEqual(launch_profiles.resolve(FAMILIES["main_launch"])["framework_map"],
                         FAMILIES["main_launch"]["framework_map"])

    def test_adapter_refuses_an_unregistered_count(self):
        for kind, n in (("main_launch", 7), ("doors_closing", 2), ("welcome_access", 3),
                        ("upsell_followup", 4), ("pre_launch", 4)):
            with self.assertRaises(adapter.Refusal, msg=(kind, n)) as ctx:
                _adapt(_plan({kind: n}))
            self.assertIn("registers only", str(ctx.exception))
        with self.assertRaises(adapter.Refusal):  # the shared contract refuses 0 first
            _adapt(_plan({"main_launch": 0}))

    def test_prover_refuses_a_variant_length_without_a_locked_brief(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        epath = self.write("short-main.json", _emails(briefs["main_launch"]))
        rc, out = self.prove(epath)  # no brief: the default 10 applies
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-LENGTH", [f["code"] for f in out["failures"]])

    def test_prover_refuses_a_brief_locked_at_an_unregistered_count(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        brief = json.loads(json.dumps(briefs["doors_closing"]))
        emails = _emails(brief)
        brief["family"]["email_count"] = 2
        rc, out = self.prove(self.write("e.json", emails), self.write("b.json", brief))
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-LENGTH", [f["code"] for f in out["failures"]])

    def test_emitter_refuses_an_unregistered_expected_count(self):
        briefs = _adapt(_plan(CLIENT_PLAN))
        plan = emitter.build_plan(briefs["doors_closing"], _emails(briefs["doors_closing"]))
        plan["_meta"]["expected_email_count"] = 2
        self.assertTrue(emitter.validate_plan(plan))

    def test_registry_refuses_a_malformed_variant(self):
        reg = json.loads(launch_profiles.REGISTRY_PATH.read_text(encoding="utf-8"))
        fam = next(f for f in reg["families"] if f["kind"] == "doors_closing")
        fam["count_variants"]["2"] = {"purpose": "x", "framework_map": {"1": "aida"}}
        path = self.write("reg.json", reg)
        with self.assertRaises(launch_profiles.RegistryError):
            launch_profiles.load_registry(path)


class WordBandOverrideRoundTrips(_Tmp):
    def _brief(self, value):
        fx = adapter.build_fixtures()
        fx["session"]["answers"][s49.LEDGER_OVERRIDES] = {"word_band_override": {
            "value": value, "state": "provided", "source_ref": "client answer: exact length"}}
        return adapter.adapt(fx["session"], fx["launch"], fx["approval"], fx["brand_facts"],
                             fx["landing_facts"], worker_identity_ref=fx["worker_identity_ref"])

    def test_list_and_legacy_object_both_emit_the_prover_shape(self):
        for value in ([350, 450], {"min": 350, "max": 450}):
            brief = self._brief(value)
            self.assertEqual(brief["answers"]["locked_overrides"]["word_band_override"],
                             [350, 450], value)
            self.assertIs(brief["answers"]["client_overrode_word_band"], True)

    def test_the_adapted_override_is_honored_by_the_prover(self):
        brief = self._brief({"min": 350, "max": 450})
        email = {"framework": "pas", "objective": "promotional",
                 "subjects": ["{{contact.first_name}}, the quiet cost of waiting a week",
                              "Everyone booked it but you last call now"],
                 "previews": ["Tease the core value without repeating it"],
                 "body": _body(400, ["Read the full story"], False),
                 "ctas": ["Read the full story"], "founder_name": FOUNDER,
                 "word_band_override": [350, 450]}
        rc, out = self.prove(self.write("email.json", email), self.write("brief.json", brief),
                             kind="email")
        self.assertEqual(rc, 0, out)
        email.pop("word_band_override")  # the SACRED 150-300 band re-applies
        rc, out = self.prove(self.write("email2.json", email), self.write("brief.json", brief),
                             kind="email")
        self.assertIn("AF-EMAIL-WORDBAND", [f["code"] for f in out["failures"]])

    def test_a_malformed_band_is_refused(self):
        for value in ({"low": 1}, [450, 350], [0, 10], [1, 2, 3], ["a", "b"], [True, 5], "350-450"):
            with self.assertRaises(adapter.Refusal, msg=value):
                self._brief(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
