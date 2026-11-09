#!/usr/bin/env python3
"""Proofs for launcher_intake: the answers file is the price authority for the Skill 83 intake.

Run: python3 -m pytest shared-utils/client_intake/tests/test_launcher_intake.py -q
No network, no paid call, no model.
"""
import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
sys.path.insert(0, str(PKG))
import engine as e  # noqa: E402
import launcher_intake as li  # noqa: E402

def _skill(name):  # onboarding: 49-signature-funnel; 999: .claude/skills/signature-funnel
    p = REPO / name
    return p if p.is_dir() else REPO / ".claude/skills" / name.split("-", 1)[1]

SKILL83 = _skill("83-black-friday-launcher")
SKILL71 = _skill("71-blackceo-signature-page") / "scripts"
sys.path.insert(0, str(SKILL83))
sys.path.insert(0, str(SKILL83 / "fixtures"))
intake83 = importlib.import_module("launcher_core.intake")

ELEVATION = json.loads((PKG / "fixtures" / "answers.elevation.json").read_text())
_FIX83 = json.loads((SKILL83 / "fixtures" / "elevation" / "intake.json").read_text())
SYSTEM = {k: _FIX83[k] for k in ("tenant_id", "location_id", "launch_id", "brand", "approval")}
HOUSE = "House look (recommended)"


_SAID = {}


def _say(text):  # stores a CLIENT message in the transcript seam, returns its id
    ref = "t-" + hashlib.sha256(str(text).encode()).hexdigest()[:10]  # same words, same id: answers files stay comparable
    _SAID[ref] = {"role": "client", "text": str(text)}
    return ref


def setUpModule():
    e.TRANSCRIPT_LOOKUP = _SAID.get


def tearDownModule():
    e.TRANSCRIPT_LOOKUP = None


_ANSWERS_DIR = tempfile.TemporaryDirectory()  # the answers files the 83 intake reads its provenance from


def elevation(direction=HOUSE):
    """The Elevation answers with the answers a launch intake also needs, asked the way a client answers.
    The checkout terms are the client's own wording. No account-entitlement answer exists to record."""
    doc = copy.deepcopy(ELEVATION)
    doc["meta"]["mode"] = "bf"
    for qid, text in (("plan_approval", "Approve this plan"),
                      ("visual_direction", direction)):
        r = e.record(doc, qid, text, source_message_ref=_say(text) if qid in e.CITED_QUESTIONS else None)
        assert r.get("ok"), (qid, r)
    e._set(doc, "checkout_terms", TERMS, "provided", "client")
    return doc


def answers_on_disk(doc):
    """The answers file the intake names (answers_file): written as the generator would read it."""
    fd, name = tempfile.mkstemp(suffix=".json", dir=_ANSWERS_DIR.name)
    with open(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return Path(name)


def delivery_for(doc):
    """What no answer can carry: the owner-confirmed https address where each buyer gets access (83 requires it)."""
    return {o["offer_id"]: {"delivery": {"destination": f"https://delivery.test-only.invalid/{o['offer_id']}",
                                         "owner_confirmed": True}} for o in li.derive_offers(doc)[1]}


def built(doc=None, **kw):
    doc = doc or elevation()
    extra = delivery_for(doc)
    for oid, fields in (kw.pop("extra_offer", None) or {}).items():
        extra[oid] = dict(extra.get(oid, {}), **fields)
    return li.to_launcher_intake(doc, dict(SYSTEM, extra_offer=extra, **kw), answers_path=answers_on_disk(doc))


def refused(test, code, fn, *a, **kw):
    with test.assertRaises(li.AnswersError) as cm:
        fn(*a, **kw)
    test.assertEqual(cm.exception.code, code, str(cm.exception))
    return cm.exception


class ElevationBuildsAValidIntake(unittest.TestCase):
    def test_the_intake_validates_and_every_offer_names_its_answers_file_question(self):
        res = built()
        norm = intake83.validate(res["intake"])  # the real Skill 83 validator accepts it
        self.assertEqual(norm["journey_mode"], ELEVATION["answers"]["funnel_shape"]["value"])
        src = {s["offer_id"]: s for s in res["provenance"]["offers"]}
        self.assertEqual(set(src), {o["offer_id"] for o in res["intake"]["offers"]})
        for o in res["intake"]["offers"]:
            self.assertRegex(src[o["offer_id"]]["source_ref"], r"^answers-file:([A-Za-z0-9_.]+)(?:\[(\d+)\])?$")  # 83 offer_mapper grammar
        packages = ELEVATION["answers"]["packages"]["value"]
        mains = [o for o in res["intake"]["offers"] if o["role"] == "main"]
        self.assertEqual([(o["name"], o["price"]) for o in mains],
                         [(p["display_name"], dict(p["price"], source_ref=f"answers-file:packages[{i}]"))
                          for i, p in enumerate(packages)])  # each price names the answer it came from
        self.assertEqual([src[o["offer_id"]]["source_ref"] for o in mains], [f"answers-file:packages[{i}]" for i in range(len(mains))])
        self.assertEqual([src[o["offer_id"]]["index"] for o in mains], list(range(len(mains))))
        by_role = {o["role"]: o for o in res["intake"]["offers"]}
        self.assertEqual(by_role["upsell_1"]["price"],
                         dict(ELEVATION["answers"]["upsell_1"]["value"]["price"], source_ref="answers-file:upsell_1"))
        self.assertEqual(src[by_role["downsell_1"]["offer_id"]]["source_ref"], "answers-file:downsell_1")
        self.assertNotIn("bump", by_role)  # "none" in the answers: nothing is invented
        self.assertEqual(by_role["upsell_1"]["level"]["deliverables"], ["One private strategy day"])

    def test_a_single_offer_takes_its_price_from_the_price_answer(self):
        doc = elevation()
        for qid, v in (("funnel_shape", "single_simple"), ("price", {"amount_minor": 49700, "currency": "USD"})):
            e._set(doc, qid, v, "provided", "client")
        for qid in ("packages", "upsell_1", "downsell_1"):
            doc["answers"].pop(qid, None)
        res = built(doc)
        self.assertEqual([(o["offer_id"], o["price"]) for o in res["intake"]["offers"]],
                         [("MAIN", {"amount_minor": 49700, "currency": "USD", "source_ref": "answers-file:price"})])
        self.assertEqual(res["provenance"]["offers"][0]["source_ref"], "answers-file:price")
        intake83.validate(res["intake"])

    def test_a_suggested_or_defaulted_commercial_answer_is_refused_by_name(self):
        for qid, status in (("packages", "suggested"), ("upsell_1", "default_to_confirm"), ("funnel_shape", "suggested")):
            doc = elevation()
            doc["answers"][qid]["status"] = status
            err = refused(self, "AF-LAUNCH-ANSWERS-UNAPPROVED", built, doc)
            self.assertEqual(err.field, f"answers-file:{qid}")

    def test_an_unpriced_or_free_offer_is_refused_never_invented(self):
        doc = elevation()
        doc["answers"]["upsell_1"]["value"]["price"] = {"amount_minor": 0, "currency": "USD"}
        refused(self, "AF-LAUNCH-ANSWERS-PRICE", built, doc)
        doc = elevation()
        del doc["answers"]["upsell_1"]["value"]["price"]
        refused(self, "AF-LAUNCH-ANSWERS-PRICE", built, doc)

    def test_missing_approval_and_entitlement_are_refused(self):
        doc = elevation()
        del doc["answers"]["plan_approval"]
        refused(self, "AF-LAUNCH-ANSWERS-MISSING", built, doc)
        doc = elevation()
        e.record(doc, "plan_approval", "I want a change")
        refused(self, "AF-LAUNCH-ANSWERS-APPROVAL", built, doc)
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", li.to_launcher_intake, elevation(), {})

    def test_a_second_downsell_is_refused_by_name(self):  # PRD-30
        doc = elevation()
        e._set(doc, "downsell_2", {"display_name": "Last chance", "price": {"amount_minor": 9900, "currency": "USD"}},
               "provided", "client")
        refused(self, "AF-LAUNCH-ANSWERS-DOWNSELL2", built, doc)

    def test_a_yes_to_a_second_downsell_with_a_price_is_refused_naming_it(self):  # PRD-30
        doc = elevation()
        e._set(doc, "downsell_2", {"display_name": "Yes, I have one", "price": {"amount_minor": 2700, "currency": "USD"}},
               "provided", "client")
        err = refused(self, "AF-LAUNCH-ANSWERS-DOWNSELL2", built, doc)
        self.assertEqual(err.field, "answers-file:downsell_2")
        self.assertIn("a second downsell is not supported in this release", str(err))
        self.assertEqual(err.detail, intake83.UNSUPPORTED_OFFER_ROLES["downsell_2"])  # byte-identical to 83

    def test_no_second_downsell_builds_with_no_trace_of_one(self):  # PRD-30
        doc = elevation()
        e._set(doc, "downsell_2", "none", "provided", "client")
        self.assertNotIn("downsell_2", json.dumps(built(doc)["intake"]))

    def test_the_image_plan_carries_only_confirmed_picture_choices(self):
        plan = built()["intake"]["image_plan"]
        self.assertEqual((plan["design_style"], plan["design_style_source"], plan["image_provider"], plan["image_cap"]),
                         ("B", "client_choice", "kie", 12))
        doc = elevation()
        for qid in ("design_style", "image_cap", "image_provider"):
            doc["answers"][qid]["status"] = "default_to_confirm"
        self.assertNotIn("design_style", built(doc)["intake"].get("image_plan", {}))
        self.assertNotIn("image_cap", built(doc)["intake"].get("image_plan", {}))

    def test_a_cap_below_the_chosen_page_sets_need_is_named(self):
        res = built()
        self.assertEqual(res["provenance"]["image_ceiling"]["images"], 232)  # landing+sales+selection+checkout+U1+D1+thank-you
        self.assertTrue(any("12" in w and "232" in w for w in res["provenance"]["warnings"]))


class TheIntakeIsBoundToTheAnswers(unittest.TestCase):
    def test_an_intake_with_no_answers_hash_is_refused(self):
        res = built()
        refused(self, "AF-LAUNCH-ANSWERS-HASH-MISSING", li.verify, res["intake"], None, elevation())
        refused(self, "AF-LAUNCH-ANSWERS-HASH-MISSING", li.verify, res["intake"], {}, elevation())
        prov = dict(res["provenance"])
        del prov["answers_sha256"]
        refused(self, "AF-LAUNCH-ANSWERS-HASH-MISSING", li.verify, res["intake"], prov, elevation())

    def test_the_matching_answers_pass_and_changed_answers_or_a_hand_edit_do_not(self):
        doc = elevation()
        res = built(doc)
        li.verify(res["intake"], res["provenance"], doc)
        changed = copy.deepcopy(doc)
        changed["answers"]["upsell_1"]["value"]["price"]["amount_minor"] = 1
        refused(self, "AF-LAUNCH-ANSWERS-HASH-MISMATCH", li.verify, res["intake"], res["provenance"], changed)
        edited = copy.deepcopy(res["intake"])
        edited["offers"][0]["price"]["amount_minor"] += 100  # an agent nudging a price in the intake
        err = refused(self, "AF-LAUNCH-ANSWERS-HASH-MISMATCH", li.verify, edited, res["provenance"], doc)
        self.assertEqual(err.field, "intake_sha256")
        forged = dict(res["provenance"], intake_sha256=li.intake_hash(edited))  # ...and re-stamping the hash
        err = refused(self, "AF-LAUNCH-ANSWERS-HASH-MISMATCH", li.verify, edited, forged, doc)
        self.assertEqual(err.field, "offers")

    def test_dispatch_refuses_an_intake_whose_answers_hash_differs_and_runs_83_otherwise(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ans, sysf = d / "answers.json", d / "system.json"
            ans.write_text(json.dumps(elevation()))
            sysf.write_text(json.dumps(SYSTEM))
            self.assertEqual(li.main(["build", str(ans), "--system", str(sysf), "--out", str(d / "run")]), 0)
            flags = ["--answers", str(ans), "--intake", str(d / "run" / "intake.json"), "--out", str(d / "out"),
                     "--approval", "a.json", "--client", "c", "--worker", "w"]
            with mock.patch.object(li, "_delegate", return_value=0) as run83:
                self.assertEqual(li.main(["verify", *flags[:4]]), 0)
                self.assertEqual(li.main(["dispatch", *flags]), 0)
                argv = run83.call_args[0][0]
                self.assertEqual(argv[:3], ["dispatch", "--intake", str(d / "run" / "intake.json")])
                self.assertIn("--worker", argv)
                self.assertNotIn("--answers", argv)
                run83.reset_mock()
                doc = json.loads(ans.read_text())
                doc["answers"]["upsell_1"]["value"]["price"]["amount_minor"] += 1
                ans.write_text(json.dumps(doc))  # the answers move on after the intake was built
                self.assertEqual(li.main(["dispatch", *flags]), 2)
                run83.assert_not_called()
                ans.write_text(json.dumps(elevation()))
                (d / "run" / li.PROVENANCE_NAME).unlink()  # an intake typed by hand: no provenance at all
                self.assertEqual(li.main(["dispatch", *flags]), 2)
                run83.assert_not_called()


TERMS = {"guarantee_ref": "g", "guarantee_text": "30-day money-back", "terms_ref": "t", "terms_text": "Terms apply",
         "consent_ref": "c", "consent_text": "I agree"}


def future83(**over):
    """A stand-in for Skill 83's intake after it grows answers_file, checkout_terms and a price source_ref."""
    base = dict(REQUIRED_FIELDS=dict(intake83.REQUIRED_FIELDS, answers_file="x", checkout_terms="x"),
                OPTIONAL_FIELDS=intake83.OPTIONAL_FIELDS, PERMITTED_DEFAULTS=intake83.PERMITTED_DEFAULTS,
                PRICE_REQUIRED=intake83.PRICE_REQUIRED, PRICE_OPTIONAL=("bounds_confirmed", "source_ref"))
    return types.SimpleNamespace(**dict(base, **over))


def past83():
    """A stand-in for Skill 83's intake before it declared answers_file, checkout_terms and a price source_ref."""
    return types.SimpleNamespace(REQUIRED_FIELDS={k: v for k, v in intake83.REQUIRED_FIELDS.items()
                                                  if k not in ("answers_file", "checkout_terms")},
                                 OPTIONAL_FIELDS=("image_plan",), PERMITTED_DEFAULTS=intake83.PERMITTED_DEFAULTS,
                                 PRICE_REQUIRED=intake83.PRICE_REQUIRED, PRICE_OPTIONAL=("bounds_confirmed",))


class GeneratorFollowsWhatSkill83Declares(unittest.TestCase):
    def _terms_doc(self, value=TERMS):
        doc = elevation()
        e._set(doc, "checkout_terms", value, "provided", "client")
        return doc

    def test_a_field_83_does_not_declare_is_not_emitted(self):
        doc = self._terms_doc()
        intake = li.to_launcher_intake(doc, SYSTEM, intake_module=past83())["intake"]  # an older 83 declares none of the three
        for k in ("answers_file", "checkout_terms"):
            self.assertNotIn(k, intake)
        self.assertNotIn("source_ref", intake["offers"][0]["price"])
        with self.assertRaises(intake83.IntakeError) as cm:  # the 83 in this tree requires them, and says so by name
            intake83.validate(intake)
        self.assertEqual((cm.exception.code, cm.exception.field), ("AF-LAUNCH-INTAKE-MISSING", "checkout_terms"))
        built_now = built(doc)["intake"]  # the 83 in this tree declares all three, so the generator emits them
        for k in ("answers_file", "checkout_terms"):
            self.assertIn(k, built_now)
        self.assertIn("source_ref", built_now["offers"][0]["price"])
        intake83.validate(built_now)

    def test_a_declared_answers_file_checkout_terms_and_price_source_ref_are_built_from_the_answers(self):
        res = li.to_launcher_intake(self._terms_doc(), SYSTEM, answers_path=Path("/x/answers.json"), intake_module=future83())
        intake, src = res["intake"], {s["offer_id"]: s["source_ref"] for s in res["provenance"]["offers"]}
        self.assertEqual(intake["answers_file"], "/x/answers.json")
        self.assertEqual(intake["checkout_terms"], TERMS)
        self.assertEqual(res["provenance"]["checkout_terms"], {"source_ref": "answers-file:checkout_terms"})
        for o in intake["offers"]:
            self.assertEqual(o["price"]["source_ref"], src[o["offer_id"]])
        # the intake still verifies against the answers although each price now carries its source
        li.verify(intake, res["provenance"], self._terms_doc())

    def test_declared_terms_are_never_defaulted_and_all_six_parts_are_needed(self):
        mod = future83()
        build = lambda doc: li.to_launcher_intake(doc, SYSTEM, answers_path=Path("a.json"), intake_module=mod)  # noqa: E731
        no_terms = elevation()
        del no_terms["answers"]["checkout_terms"]
        refused(self, "AF-LAUNCH-ANSWERS-MISSING", build, no_terms)
        err = refused(self, "AF-LAUNCH-ANSWERS-TERMS", build, self._terms_doc("30-day guarantee, see my terms page"))
        self.assertIn("consent_text", err.detail)
        refused(self, "AF-LAUNCH-ANSWERS-TERMS", build, self._terms_doc({k: v for k, v in TERMS.items() if k != "terms_text"}))
        doc = self._terms_doc()
        doc["answers"]["checkout_terms"]["status"] = "suggested"
        refused(self, "AF-LAUNCH-ANSWERS-UNAPPROVED", build, doc)
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", li.to_launcher_intake, self._terms_doc(), SYSTEM, intake_module=mod)  # no answers path

    def test_the_pass_throughs_cannot_replace_what_the_answers_build(self):
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", built, extra_root={"offers": []})
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", built, extra_root={"journey_mode": "single_simple"})
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", built, extra_offer={"MAIN-X": {"price": {"amount_minor": 1, "currency": "USD"}}})
        first = built()["intake"]["offers"][0]["offer_id"]
        refused(self, "AF-LAUNCH-ANSWERS-SYSTEM", built, extra_offer={first: {"name": "Cheaper"}})
        ok = built(extra_offer={first: {"delivery": {"kind": "x"}}})["intake"]["offers"][0]
        self.assertEqual(ok["delivery"], {"kind": "x"})  # what no answer can carry still passes through

    def test_the_promotion_facts_ride_the_intake_only_when_83_declares_them(self):
        doc = elevation()
        for qid, v in (("bf_promotion", "A discount"), ("bf_limitations", "only 50 seats at this price"), ("bf_seat_limit", "Only 50 seats")):
            e._set(doc, qid, v, "provided", "client")
        self.assertNotIn("promotion", li.to_launcher_intake(doc, SYSTEM, intake_module=past83())["intake"])
        promo = built(doc)["intake"]["promotion"]
        self.assertEqual((promo["kind"], promo["seat_limit"], promo["seat_limit_state"]), ("A discount", 50, "limited"))
        self.assertEqual(intake83.validate(built(doc)["intake"])["promotion"], promo)  # 83's own check accepts what the generator emits
        self.assertNotIn("promotion", built(elevation())["intake"])  # nothing answered: nothing invented

    def test_creative_direction_rides_the_image_plan_only_when_83_accepts_it(self):
        named = elevation("Like an outside style: warm editorial magazine")
        with mock.patch.object(li, "_plan_accepts", return_value=True):
            self.assertEqual(built(named)["intake"]["image_plan"]["creative_direction"], "warm editorial magazine")
            self.assertNotIn("creative_direction", built()["intake"]["image_plan"])  # the house look names nothing
        with mock.patch.object(li, "_plan_accepts", return_value=False):
            plan = built(named)["intake"]["image_plan"]
            self.assertNotIn("creative_direction", plan)
            self.assertNotIn("design_style_source", plan)  # kept only when 83 accepts it
        intake83.validate(built(named)["intake"])


class VisualDirection(unittest.TestCase):  # IMG-07
    def _run_71(self, doc, d):
        ans = d / "answers.json"
        ans.write_text(json.dumps(doc))
        run = d / "run"
        run.mkdir()
        cmd = [sys.executable, "-I", str(SKILL71 / "write_intake.py"), str(run), "--answers-file", str(ans), "--test-run",
               *li.write_intake_args(doc)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # the brand supply gate is another check's job: a complete brand file keeps this one about direction
        (run / "brand" / "client-brand.json").write_text(json.dumps(
            {"palette": {"primary": "#0A7E8C"}, "color_tolerance": 5, "fonts": {"display": "Playfair Display"}}))
        return run, json.loads((run / "intake.json").read_text())

    def _bible_check(self, run, selection_mode, style_id=None):
        (run / "visual-mockup").mkdir(exist_ok=True)
        bible = {"selection_mode": selection_mode, "page_tokens": {}, "fonts": {}}
        if style_id:
            bible["style_id"] = style_id
        (run / "visual-mockup" / "page-visual-bible.json").write_text(json.dumps(bible))
        return subprocess.run([sys.executable, "-I", str(SKILL71 / "validate_visual_direction.py"), str(run)],
                              capture_output=True, text=True, timeout=120).returncode

    def test_a_named_direction_reaches_intake_json_and_the_bible_selection_mode_matches(self):
        doc = elevation("Like an outside style: warm editorial magazine")
        direction = li.creative_direction(doc)
        self.assertEqual((direction["kind"], direction["value"], direction["source"]),
                         ("external_direction", "warm editorial magazine", "client_choice"))
        self.assertEqual(li.write_intake_args(doc), ["--creative-direction", "warm editorial magazine"])
        self.assertEqual(built(doc)["provenance"]["creative_direction"]["selection_mode"], "warm editorial magazine")
        with tempfile.TemporaryDirectory() as d:
            run, intake = self._run_71(doc, Path(d))
            self.assertEqual(intake["creative_direction"], "warm editorial magazine")  # non-null
            self.assertEqual(self._bible_check(run, direction["selection_mode"], "warm editorial magazine"), 0)
            self.assertEqual(self._bible_check(run, li.SECRET_SAUCE_ONLY), 0)  # the house look is always allowed
            self.assertEqual(self._bible_check(run, "brutalist poster", "brutalist poster"), 1)  # not the named style

    def test_with_no_direction_the_client_must_have_chosen_the_house_look(self):
        doc = elevation()
        direction = li.creative_direction(doc)
        self.assertEqual((direction["kind"], direction["value"], direction["selection_mode"], direction["source"]),
                         ("house_look", None, li.SECRET_SAUCE_ONLY, "client_choice"))
        self.assertEqual(li.write_intake_args(doc), [])
        with tempfile.TemporaryDirectory() as d:
            run, intake = self._run_71(doc, Path(d))
            self.assertIsNone(intake["creative_direction"])
            self.assertEqual(self._bible_check(run, direction["selection_mode"]), 0)
            self.assertEqual(self._bible_check(run, "warm editorial magazine", "warm editorial magazine"), 1)

    def test_an_unanswered_or_defaulted_direction_is_refused(self):
        doc = elevation()
        del doc["answers"]["visual_direction"]
        refused(self, "AF-LAUNCH-ANSWERS-DIRECTION", li.creative_direction, doc)
        refused(self, "AF-LAUNCH-ANSWERS-DIRECTION", built, doc)
        e.apply_default(doc, "visual_direction")  # the flagged default is a proposal, not the client's choice
        self.assertEqual(doc["answers"]["visual_direction"]["status"], "default_to_confirm")
        refused(self, "AF-LAUNCH-ANSWERS-DIRECTION", li.creative_direction, doc)

    def test_a_chosen_look_must_say_which_one(self):
        for bare in ("Like my own brand or site", "Like an outside style I name"):
            refused(self, "AF-LAUNCH-ANSWERS-DIRECTION", li.creative_direction, elevation(bare))
        own = li.creative_direction(elevation("Like my own site: https://example.com"))
        self.assertEqual((own["kind"], own["value"]), ("own_reference", "https://example.com"))
        said = li.creative_direction(elevation("Soft and earthy, like a spa brochure"))
        self.assertEqual((said["kind"], said["value"]), ("described", "Soft and earthy, like a spa brochure"))


class ProviderAndBank(unittest.TestCase):
    bank = {q["id"]: q for q in e.load_bank()["questions"]}

    def test_agnes_reaches_83s_image_plan_which_refuses_paid_pictures(self):  # IMG-24
        doc = elevation()
        e._set(doc, "image_provider", "agnes", "provided", "client")
        res = built(doc, brand_file="brand/client-brand.json")  # no refusal here: 83's image plan decides
        plan = res["intake"]["image_plan"]
        self.assertEqual(plan["image_provider"], "agnes")
        intake83.validate(res["intake"])
        self.assertTrue(any("KIE" in w and "agnes" in w for w in res["provenance"]["warnings"]), res["provenance"]["warnings"])
        ip = importlib.import_module("launcher_core.image_plan")
        with self.assertRaises(ip.ImagePlanError) as cm:  # a paid run: refused by name, nothing spent
            ip.resolve(dict(plan, paid_render_approval_ref="approval:images"), test_only=False)
        self.assertEqual(cm.exception.code, "AF-LAUNCH-IMAGE-PLAN-PROVIDER")
        self.assertIn("nothing was spent", cm.exception.detail.lower())

    def test_the_provider_answer_maps_like_the_launch_record_and_an_unknown_one_is_refused_by_name(self):
        for said, want in (("connected", "kie"), ("kie", "kie"), ("none", "other_explicit")):
            doc = elevation()
            e._set(doc, "image_provider", said, "provided", "client")
            self.assertEqual(built(doc)["intake"]["image_plan"]["image_provider"], want, said)
        doc = elevation()
        e._set(doc, "image_provider", "midjourney", "provided", "client")
        err = refused(self, "AF-LAUNCH-ANSWERS-PROVIDER", built, doc)
        self.assertIn("kie, agnes, other_explicit", err.detail)

    def test_the_bank_states_the_kie_only_requirement_and_asks_the_visual_direction(self):
        q = self.bank["image_provider"]
        self.assertIn("KIE only", q["why"])
        self.assertIn("practice run", q["why"])
        self.assertIn("KIE", q["choice_explanations"]["My connected service"])
        v = self.bank["visual_direction"]
        self.assertEqual(v["choices"][0], HOUSE)
        self.assertEqual(len(v["choices"]), 3)
        self.assertEqual((v["default"]["value"], v["default"]["flag"], v["never_default"]), ("house look", "to confirm", False))
        bf = e.new_doc("bf")
        self.assertIn("visual_direction", [x["id"] for x in e.applicable(bf)])
        self.assertNotIn("visual_direction", [x["id"] for x in e.applicable(e.new_doc("legacy"))])

    def test_the_seat_limit_is_asked_in_bf_and_becomes_the_only_limit_a_page_may_claim(self):  # PRD-15
        self.assertTrue(self.bank["bf_seat_limit"]["never_default"])
        self.assertIn("bf_seat_limit", [x["id"] for x in e.applicable(e.new_doc("bf"))])
        doc = elevation()
        for text, seats, state in (("Only 20 seats", 20, "limited"), ("No limit", None, "no_limit")):
            e._set(doc, "bf_seat_limit", text, "provided", "client")
            promo = built(doc)["provenance"]["promotion"]
            self.assertEqual((promo["seat_limit"], promo["seat_limit_state"]), (seats, state))
        self.assertIsNone(built(elevation())["provenance"]["promotion"])

    def test_the_paid_image_answer_reaches_image_plan_as_an_approval_ref_with_its_cap(self):  # IMG-03
        for said in ("No paid pieces", "Decide later"):
            doc = elevation()
            e.record(doc, "paid_render_approval", said)
            got = e.image_inputs(doc)
            self.assertEqual((got["allow_paid"], got["paid_render_approval_ref"], got["image_cap_minor"]), (False, None, None), said)
        doc = elevation()
        e.record(doc, "paid_render_approval", "$200")
        self.assertEqual((e.image_inputs(doc)["allow_paid"], e.image_inputs(doc)["paid_render_approval_ref"]), (False, None))  # no CC record yet
        doc["answers"]["paid_render_approval"]["value"]["approval_id"] = "cc-approval-7"
        got = e.image_inputs(doc)
        self.assertEqual((got["allow_paid"], got["paid_render_approval_ref"], got["image_cap_minor"], got["image_currency"]),
                         (True, "cc-approval-7", 20000, "USD"))
        ip = importlib.import_module("launcher_core.image_plan")  # 83's own raw check takes exactly these keys
        ip.validate_raw({k: got[k] for k in ("paid_render_approval_ref", "image_cap_minor", "image_currency")})

    def test_a_second_downsell_is_not_asked_outside_the_legacy_funnel(self):  # PRD-30
        for mode in ("bf", "launch"):
            doc = e.new_doc(mode)
            e._set(doc, "upsell_1", "x", "provided", "client")
            e._set(doc, "upsell_2", "x", "provided", "client")
            self.assertNotIn("downsell_2", [x["id"] for x in e.applicable(doc)], mode)
        self.assertIn("downsell_2", [x["id"] for x in e.applicable(e.new_doc("legacy"))])

    def test_the_banks_picture_ceilings_equal_skill_49s_estimates(self):  # IMG-04 display
        def ceiling(shape, extras, page_set="all", copy_profile="standard"):
            doc = elevation()
            e._set(doc, "funnel_shape", shape, "provided", "client")
            e._set(doc, "page_set", page_set, "provided", "client")
            e._set(doc, "copy_profile", copy_profile, "provided", "client")
            offer = {"display_name": "X", "price": {"amount_minor": 9900, "currency": "USD"}}
            for slot in ("upsell_1", "downsell_1", "upsell_2"):
                e._set(doc, slot, offer if slot in extras else "none", "provided", "client")
            if shape == "single_simple":
                e._set(doc, "price", {"amount_minor": 9900, "currency": "USD"}, "provided", "client")
            return li.image_ceiling(doc)["images"]

        full = ("upsell_1", "downsell_1", "upsell_2")
        got = {"core": ceiling("single_simple", (), "core"), "core_long": ceiling("single_simple", (), "core", "long_form"),
               "smallest_all": ceiling("single_simple", ()), "several_no_extras": ceiling("multiple_options", ()),
               "one_offer_all_extras": ceiling("single_simple", full), "largest": ceiling("multiple_options", full)}
        self.assertEqual(got, {"core": 68, "core_long": 80, "smallest_all": 88, "several_no_extras": 168,
                               "one_offer_all_extras": 244, "largest": 264})
        cap, page_set = self.bank["image_cap"], self.bank["page_set"]
        self.assertEqual(cap["choices"], ["88", "168", "264"])
        self.assertEqual(cap["default"]["value"], got["largest"])
        for n in ("68", "80", "88", "168", "244", "264"):
            self.assertIn(n, cap["help"]["explain"], n)
        self.assertIn("68", page_set["choice_explanations"]["Only the main page and checkout"])
        self.assertIn("88", page_set["choice_explanations"]["Every page my funnel needs (recommended)"])
        self.assertIn("264", page_set["choice_explanations"]["Every page my funnel needs (recommended)"])


if __name__ == "__main__":
    unittest.main()
