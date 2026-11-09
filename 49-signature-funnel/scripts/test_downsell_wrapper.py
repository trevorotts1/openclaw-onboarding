"""Downsell wrapper tests (S49-08 bridge; adoption map 1.5).

No test module existed for downsell_wrapper.py before the adoption
map 1.5 candidate; the upsell and selection wrappers have theirs.
This suite stages a complete local run (test-only values
throughout) and pins:

- the 1.0 control: a page-request 1.0 is consumed end to end
  exactly as before the dual-accept revision, and the enriched
  Skill 81 request it produces satisfies Skill 81's own stdlib
  request validator;
- the 1.1 acceptance: a page-request 1.1 carrying the
  prompt_policy_id citation "kie-rule-12-band" is consumed end to
  end, the citation riding through into the enriched downsell
  request (the Skill 81 contract document), which validates under
  Skill 81's validator at 1.1; the base page-result stays 1.0 and
  carries no policy field;
- the pair rule and the closed shape, fail-closed by name: a 1.1
  request without the field, a 1.0 request carrying it, empty,
  null, non-string and selector-shaped ids, genuinely unknown
  keys, and unknown schema versions;
- the registry-layer allocation, pinned as in the 1.2 and 1.4
  candidates: the id is an open string at this layer (the Q12
  shape); an unregistered non-empty id is consumed here, because
  refusal of unregistered ids is a registry-layer act at dispatch
  and at the Q11 aggregator (adoption map section 4).

- the DTY repair (unit U-downsell-ty-01): real offer ids in `excludes`
  are mapped to the 'U1'/'D1' labels the pinned validator reads, on
  copies; null native ids at design time give the standing blocker
  D1-NATIVE-IDS-PENDING-INSTALL and a placeholder or null is refused at
  the install stage; the entry guard is DESIGN-ONLY with blocker
  D1-ENTRY-GUARD-RUNTIME-ONLY and the result records the sha256 of the
  launch, sidecar, difference table and journey; status is authored / L1
  unless three real-provider stages ran (stub adds D1-STUB-IMAGES); the
  wrapper pins equal the sha256 of the Skill 81 files and the validator
  runs from the bytes that were hashed.

Run: python3 -m unittest test_downsell_wrapper (from this
directory) or python3 test_downsell_wrapper.py.
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
SKILL81 = REPO / "81-signature-downsell"
WRAPPER = SCRIPTS / "downsell_wrapper.py"

sys.path.insert(0, str(SKILL81 / "validators"))
sys.path.insert(0, str(SCRIPTS))
from validate_request import validate_request  # noqa: E402
import downsell_wrapper as dw  # noqa: E402

PAGE_FIXTURE = json.loads(
    (SKILL81 / "fixtures" / "valid-downsell-page.json").read_text())
RESULT_FIXTURE = json.loads(
    (SKILL81 / "fixtures" / "valid-downsell-result.json").read_text())

RENEWAL_PROMISE = 'After the trial, $27 per month continues the membership unless you cancel. The first renewal charge is on day 31, and renewals are monthly after that. You can cancel anytime before a renewal charge to stop future charges. If you cancel, your access continues until the end of the trial or the current paid month, then your membership access ends and you will not be charged again. '


def _one_time_page(amount_minor):
    """The Skill 81 fixture page re-priced to a one-time D1 at `amount_minor`: the fixture's own
    copy is a $1 trial that renews at $27 a month, which no one-time D1 may promise."""
    dollars = "$%d" % (amount_minor // 100)
    text = json.dumps(PAGE_FIXTURE)
    assert RENEWAL_PROMISE in text
    text = re.sub(r"\$1(?!\d)", lambda _m: dollars, text.replace(RENEWAL_PROMISE, ""))
    page = json.loads(text)
    page["page"]["approved_amounts_minor"] = [amount_minor]
    return page


D1_PAGE_ID = "TEST-D1-PAGE"
U2_PAGE_ID = "TEST-UPSELL_2"


def _graph_bytes():
    graph = {
        "nodes": [
            {"page_id": D1_PAGE_ID, "role": "downsell_1"},
            {"page_id": U2_PAGE_ID, "role": "upsell_2"},
        ],
        "edges": [
            {"from": D1_PAGE_ID, "to": U2_PAGE_ID,
             "event": "payment_succeeded"},
        ],
    }
    return (json.dumps(graph, indent=2) + "\n").encode()


def _request(graph_hash, version="1.0", policy_id=None):
    request = {
        "schema_version": version,
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "request_id": "TEST-TENANT:TEST-LAUNCH:rev1:downsell_1:test",
        "page_id": D1_PAGE_ID,
        "page_role": "downsell_1",
        "assigned_skill": 81,
        "approval_ref": "TEST-APPROVAL",
        "input_hash": "TEST-INPUT-HASH",
        "brand_ref": "TEST-BRAND",
        "brand_hash": "TEST-BRAND-HASH",
        "route_graph_ref": "TEST-GRAPH",
        "route_graph_hash": graph_hash,
        "offer_refs": ["TEST-U1-OFFER", "TEST-D1-OFFER"],
        "copy_profile": "TEST-COPY-PROFILE",
        "allowed_write_target": "local_only",
        "test_only": True,
    }
    if policy_id is not None:
        request["prompt_policy_id"] = policy_id
    return request


def _launch(graph_hash):
    return {
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "route_graph_hash": graph_hash,
        "test_only": True,
        "extras": {"upsell_1": True, "downsell_1": True,
                   "upsell_2": True},
        "offers": [
            {"slot": "main", "offer_id": "TEST-MAIN-OFFER",
             "entitlement_ids": ["TEST-ENT-MAIN"],
             "deliverables": ["TEST main program core curriculum"],
             "native_product_id": "TEST-MAIN-PRODUCT",
             "prices": [{"amount_minor": 4900,
                         "billing_type": "one_time",
                         "approval_status": "approved",
                         "native_price_id": "TEST-MAIN-PRICE"}]},
            {"slot": "upsell_1", "offer_id": "TEST-U1-OFFER",
             "excludes": ["D1"],
             "deliverables": [
                 "Weekly live training sessions with the full cohort",
                 "Private community access with daily mentor threads",
                 "Founder critique reviews of every campaign draft"],
             "entitlement_ids": ["TEST-ENT-FULL", "TEST-ENT-COACHING"],
             "native_product_id": "TEST-U1-PRODUCT",
             "prices": [{"amount_minor": 100,
                         "billing_type": "trial",
                         "approval_status": "approved",
                         "native_price_id": "TEST-U1-PRICE",
                         "schedule": [{"amount_minor": 2700}]}]},
            {"slot": "downsell_1", "offer_id": "TEST-D1-OFFER",
             "excludes": ["U1"],
             "deliverables": [
                 "Core field notes digest collected monthly",
                 "Planning worksheet pack for each quarter"],
             "entitlement_ids": ["TEST-ENT-LITE"],
             "native_product_id": "TEST-D1-PRODUCT",
             "prices": [{"amount_minor": 3700,
                         "billing_type": "one_time",
                         "approval_status": "approved",
                         "native_price_id": "TEST-D1-PRICE"}]},
        ],
    }


def stage(request):
    """Write one full run's inputs into a fresh temp directory and
    return (workdir, paths). The graph hash is computed from the
    exact graph bytes staged, as dispatch would bind it."""
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="d1-wrapper-"))
    graph_bytes = _graph_bytes()
    graph_hash = hashlib.sha256(graph_bytes).hexdigest()
    if request is not None and not request.get("route_graph_hash"):
        request["route_graph_hash"] = graph_hash
    paths = {"workdir": workdir}

    def put(name, doc):
        path = workdir / name
        if isinstance(doc, bytes):
            path.write_bytes(doc)
        else:
            path.write_text(json.dumps(doc, indent=2) + "\n")
        paths[name] = path

    put("request-downsell_1.json", request)
    put("launch.json", _launch(graph_hash))
    put("route-graph.json", graph_bytes)
    put("copy-downsell_1.json", _one_time_page(3700))  # the staged D1 is one_time $37
    put("journey-downsell_1.json",
        {"main_purchased_verified": True,
         "u1_event": "explicit_decline", "u1_accepted": False})
    put("enrichment-downsell_1.json",
        {"difference_kind": "reduced_scope",
         "rationale": "TEST ONLY recorded rationale.",
         "entry_guard_ref": "TEST-ENTRY-GUARD",
         "difference_table_ref": "difference-table.md"})
    put("difference-table.md",
        b"TEST ONLY difference table: D1 reduced_scope against U1.\n")
    put("extension-downsell_1.json", RESULT_FIXTURE)
    paths["result"] = workdir / "result-downsell_1.json"
    paths["enriched"] = workdir / "downsell-request-enriched.json"
    return paths


def run_wrapper(paths, *extra, journey=True, skill81=SKILL81):
    return subprocess.run(
        [sys.executable, str(WRAPPER),
         "--request", str(paths["request-downsell_1.json"]),
         "--result", str(paths["result"]),
         "--launch", str(paths["launch.json"]),
         "--route-graph", str(paths["route-graph.json"]),
         "--copy", str(paths["copy-downsell_1.json"]),
         *(["--journey", str(paths["journey-downsell_1.json"])]
           if journey else []),
         "--enrichment", str(paths["enrichment-downsell_1.json"]),
         "--extension", str(paths["extension-downsell_1.json"]),
         "--skill81-root", str(skill81), *extra],
        capture_output=True, text=True, cwd=str(paths["workdir"]))


def stage_and_run(request):
    paths = stage(request)
    return paths, run_wrapper(paths)


class DownsellWrapperEndToEndTests(unittest.TestCase):
    def test_1_0_request_consumed_end_to_end(self):
        paths, proc = stage_and_run(_request(None, "1.0"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["role"], "downsell_1")
        # no Skill 71 image run: capped at authored / L1 (DTY-14)
        self.assertEqual(summary["status"], "authored")
        result = json.loads(paths["result"].read_text())
        self.assertEqual(result["schema_version"], "1.0")
        self.assertNotIn("prompt_policy_id", result)
        enriched = json.loads(paths["enriched"].read_text())
        self.assertEqual(enriched["schema_version"], "1.0")
        self.assertNotIn("prompt_policy_id", enriched)
        self.assertEqual(validate_request(enriched), [])

    def test_1_1_request_with_citation_consumed_end_to_end(self):
        paths, proc = stage_and_run(
            _request(None, "1.1", "kie-rule-12-band"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["role"], "downsell_1")
        enriched = json.loads(paths["enriched"].read_text())
        # The citation's pass-through point: the enriched Skill 81
        # downsell-request carries version and id.
        self.assertEqual(enriched["schema_version"], "1.1")
        self.assertEqual(enriched["prompt_policy_id"],
                         "kie-rule-12-band")
        self.assertEqual(validate_request(enriched), [])
        # The base page-result stays 1.0 with no policy field.
        result = json.loads(paths["result"].read_text())
        self.assertEqual(result["schema_version"], "1.0")
        self.assertNotIn("prompt_policy_id", result)

    def test_1_1_unregistered_id_consumed_at_this_layer(self):
        # Pinned allocation (adoption map section 4): the id is an
        # open string here; refusal of unregistered ids belongs to
        # the registry-reading layers (dispatch, the Q11
        # aggregator), never to this consumer.
        paths, proc = stage_and_run(
            _request(None, "1.1", "no-such-policy-registered"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        enriched = json.loads(paths["enriched"].read_text())
        self.assertEqual(enriched["prompt_policy_id"],
                         "no-such-policy-registered")


class DownsellWrapperFailClosedTests(unittest.TestCase):
    def assert_refused_naming(self, request, *fragments):
        paths, proc = stage_and_run(request)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        for fragment in fragments:
            self.assertIn(fragment, proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_1_1_without_the_field_is_refused(self):
        self.assert_refused_naming(
            _request(None, "1.1"),
            "a 1.1 request must carry prompt_policy_id")

    def test_1_0_carrying_the_field_is_refused(self):
        self.assert_refused_naming(
            _request(None, "1.0", "kie-rule-12-band"),
            "prompt_policy_id requires request schema_version 1.1")

    def test_1_1_malformed_ids_are_refused(self):
        for bad in ("", "   ", None, 42, True,
                    {"policy_id": "kie-rule-12-band"},
                    ["kie-rule-12-band"]):
            with self.subTest(bad=bad):
                request = _request(None, "1.1")
                request["prompt_policy_id"] = bad
                self.assert_refused_naming(
                    request, "is not a non-empty string")

    def test_genuinely_unknown_keys_are_refused(self):
        for version in ("1.0", "1.1"):
            with self.subTest(version=version):
                request = _request(
                    None, version,
                    "kie-rule-12-band" if version == "1.1" else None)
                request["totally_unknown_field"] = "x"
                self.assert_refused_naming(
                    request, "is not part of page-request 1.0 or 1.1")

    def test_unknown_versions_are_refused(self):
        for bad in ("2.0", "1.2", "0.9"):
            with self.subTest(bad=bad):
                self.assert_refused_naming(
                    _request(None, bad), "is not 1.0 or 1.1")


SKILL71 = REPO / "71-blackceo-signature-page"
BRAND_BYTES = (SKILL71 / "assets" / "brand" / "blackceo-brand.json").read_bytes()


def _full_graph_bytes():
    """A route graph that also satisfies Skill 71's route-graph schema."""
    graph = {
        "schema_version": "1.0", "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION", "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "nodes": [{"page_id": "TEST-LANDING", "role": "landing"},
                  {"page_id": D1_PAGE_ID, "role": "downsell_1"},
                  {"page_id": U2_PAGE_ID, "role": "upsell_2"}],
        "edges": [{"from": D1_PAGE_ID, "to": U2_PAGE_ID,
                   "event": "payment_succeeded", "guard": "payment_verified"}],
        "pending_failed_payment_behavior":
            "retain_current_purchase_state_until_resolved_or_explicit_decline",
        "test_only": True,
    }
    return (json.dumps(graph, indent=2) + "\n").encode()


def _full_launch(graph_hash, brand_hash):
    """The wrapper's launch record, completed to Skill 71's launch schema."""
    launch = _launch(graph_hash)
    launch.update({
        "schema_version": "1.0", "journey_mode": "multiple_options",
        "status": "approved", "brand_ref": "brand/blackceo-brand.json",
        "brand_hash": brand_hash, "route_graph_ref": "route-graph.json",
        "plan_approval_ref": "TEST-APPROVAL", "bump_enabled": False,
        "image_provider": "agnes", "source_refs": ["TEST-BRIEF"],
        "test_only": True})
    for offer in launch["offers"]:
        offer.setdefault("display_name", offer["offer_id"])
        offer.setdefault("exclusions", [])
        offer.setdefault("requires", [])
        offer.setdefault("excludes", [])
        offer.update({"source_kind": "owner", "source_ref": "TEST-BRIEF",
                      "test_only": True})
        for i, price in enumerate(offer["prices"]):
            price.setdefault("price_choice_id", f"{offer['offer_id']}-pc{i}")
            price.setdefault("currency", "USD")
            price.setdefault("schedule", [])
            price["schedule"] = [
                {"amount_minor": row["amount_minor"], "due": f"day {30 * (n + 1)}"}
                for n, row in enumerate(price["schedule"])]
    return launch


class DownsellWrapperImagesTests(unittest.TestCase):
    """--skill71-root: the wrapper calls Skill 71's shared image service
    once and the downsell page gets wireframes and a visual mockup."""

    def stage_images(self):
        graph_bytes = _full_graph_bytes()
        graph_hash = hashlib.sha256(graph_bytes).hexdigest()
        brand_hash = hashlib.sha256(BRAND_BYTES).hexdigest()
        request = _request(graph_hash)
        request.update({"brand_ref": "brand/blackceo-brand.json",
                        "brand_hash": brand_hash,
                        "route_graph_ref": "route-graph.json"})
        paths = stage(request)
        paths["route-graph.json"].write_bytes(graph_bytes)
        paths["launch.json"].write_text(
            json.dumps(_full_launch(graph_hash, brand_hash), indent=2) + "\n")
        paths["brand"] = paths["workdir"] / "brand.json"
        paths["brand"].write_bytes(BRAND_BYTES)
        return paths

    def run_with_images(self, paths, *extra):
        return subprocess.run(
            [sys.executable, str(WRAPPER),
             "--request", str(paths["request-downsell_1.json"]),
             "--result", str(paths["result"]),
             "--launch", str(paths["launch.json"]),
             "--route-graph", str(paths["route-graph.json"]),
             "--copy", str(paths["copy-downsell_1.json"]),
             "--journey", str(paths["journey-downsell_1.json"]),
             "--enrichment", str(paths["enrichment-downsell_1.json"]),
             "--extension", str(paths["extension-downsell_1.json"]),
             "--skill81-root", str(SKILL81),
             "--skill71-root", str(SKILL71),
             "--brand-file", str(paths["brand"]),
             "--brand-owner", "blackceo", "--image-cap", "40", *extra],
            capture_output=True, text=True, cwd=str(paths["workdir"]))

    def test_images_stages_run_through_the_shared_service(self):
        paths = self.stage_images()
        proc = self.run_with_images(paths)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        summary = json.loads(proc.stdout)
        run_dir = pathlib.Path(summary["images"]["run_dir"])
        # the service staged the request with its marker and the page role
        staged = json.loads((run_dir / "page-request.json").read_text())
        self.assertEqual(staged["page_role"], "downsell_1")
        self.assertEqual(staged["shared_image_service"],
                         "71-blackceo-signature-page")
        # eight sections, desktop and mobile, for each stage that ran
        stages = summary["images"]["stages"]
        self.assertEqual(sorted(stages), ["desktop-wireframe",
                                          "mobile-tablet", "visual-mockup"])
        self.assertEqual(len(list((run_dir / "desktop-wireframe").glob("section-*.png"))), 8)
        self.assertEqual(len(list((run_dir / "mobile-tablet").glob("section-*.png"))), 8)
        self.assertEqual(len(list((run_dir / "visual-mockup" / "desktop").glob("part-*.png"))), 8)
        self.assertEqual(len(list((run_dir / "visual-mockup" / "mobile").glob("part-*.png"))), 8)
        request = json.loads(
            (run_dir / "production-request-desktop-wireframe.json").read_text())
        self.assertEqual(request["page_role"], "downsell_1")
        self.assertEqual(len(request["sections"]), 8)
        # the result names the records as artifacts and the pending chain
        result = json.loads(paths["result"].read_text())
        # stub provider: the images are placeholders, so no L2 claim
        self.assertEqual((result["status"], result["proof_class"]),
                         ("authored", "L1"))
        self.assertTrue(any(b.startswith("D1-STUB-IMAGES")
                            for b in result["blockers"]))
        self.assertTrue(any("stage-executor-record.json" in a["path"]
                            for a in result["artifacts"]))
        self.assertTrue(any(b.startswith("D1-IMAGE-CHAIN-PENDING")
                            for b in result["blockers"]))

    def test_without_skill71_root_no_image_run(self):
        paths, proc = stage_and_run(_request(None, "1.0"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("images", json.loads(proc.stdout))
        # DTY-14: no image run -> authored / L1, never a stub claim
        result = json.loads(paths["result"].read_text())
        self.assertEqual((result["status"], result["proof_class"]),
                         ("authored", "L1"))
        self.assertTrue(any(b.startswith("D1-IMAGES-NOT-RUN")
                            for b in result["blockers"]))
        self.assertFalse(any(b.startswith("D1-STUB-IMAGES")
                             for b in result["blockers"]))

    def test_images_need_their_inputs(self):
        paths = self.stage_images()
        proc = subprocess.run(
            [sys.executable, str(WRAPPER),
             "--request", str(paths["request-downsell_1.json"]),
             "--result", str(paths["result"]),
             "--launch", str(paths["launch.json"]),
             "--route-graph", str(paths["route-graph.json"]),
             "--copy", str(paths["copy-downsell_1.json"]),
             "--journey", str(paths["journey-downsell_1.json"]),
             "--enrichment", str(paths["enrichment-downsell_1.json"]),
             "--extension", str(paths["extension-downsell_1.json"]),
             "--skill81-root", str(SKILL81),
             "--skill71-root", str(SKILL71)],
            capture_output=True, text=True, cwd=str(paths["workdir"]))
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("--brand-file", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_paid_provider_needs_allow_paid(self):
        paths = self.stage_images()
        proc = self.run_with_images(paths, "--image-provider", "kie")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("--allow-paid", proc.stderr)
        self.assertFalse(paths["result"].exists())


def _edit(paths, name, fn):
    """Rewrite one staged JSON document through `fn(doc)`."""
    doc = json.loads(paths[name].read_text())
    fn(doc)
    paths[name].write_text(json.dumps(doc, indent=2) + "\n")


def _offer(doc, slot):
    return next(o for o in doc["offers"] if o["slot"] == slot)


def _sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


class DownsellCopyBoundToOwnPriceTests(unittest.TestCase):
    """F6: the page's approved amounts are D1's own prices, not every offer's in the launch."""
    ONE_DOLLAR = {"amount_minor": 100, "billing_type": "one_time", "approval_status": "approved",
                  "native_price_id": "TEST-D1-PRICE"}

    def run_one_dollar_d1(self, page):
        """D1 is one_time $1.00 with no schedule; U1 (a trial with a $27 schedule) is in the same launch."""
        paths = stage(_request(None, "1.0"))
        _edit(paths, "launch.json",
              lambda doc: _offer(doc, "downsell_1").update(prices=[self.ONE_DOLLAR]))
        _edit(paths, "extension-downsell_1.json",  # the staged extension must agree with the $1 one-time D1
              lambda doc: doc["downsell_result_extension"]["disclosure_audit"].update(due_now_minor=100))
        paths["copy-downsell_1.json"].write_text(json.dumps(page) + "\n")
        return paths, run_wrapper(paths)

    def test_a_one_time_dollar_page_promising_27_a_month_is_refused(self):
        paths, proc = self.run_one_dollar_d1(PAGE_FIXTURE)  # the fixture's "$1 trial, then $27 per month" copy
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("D1-COPY-EXAMPLE-PRICE-LEAK", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_the_same_page_without_the_renewal_promise_is_accepted(self):
        paths, proc = self.run_one_dollar_d1(_one_time_page(100))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_one_time_page_with_a_recurring_price_phrase_is_refused(self):
        page = _one_time_page(100)
        page["page"]["sections"][6]["body"] += " Then $5 per month continues."
        paths, proc = self.run_one_dollar_d1(page)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("D1-COPY-BILLING-MISMATCH", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_a_one_time_page_with_a_dollar_monthly_phrase_is_refused(self):
        for phrase in (" Then $5 monthly continues.", " Then $5 per mo continues.", " Then $5 per-month continues.",
                       " Then $5/monthly continues.", " Then $5/yearly continues."):
            with self.subTest(phrase=phrase):
                page = _one_time_page(100)
                page["page"]["sections"][6]["body"] += phrase
                paths, proc = self.run_one_dollar_d1(page)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("D1-COPY-BILLING-MISMATCH", proc.stderr)

    def test_the_recurring_phrase_catches_every_billing_word_form_and_no_ordinary_words(self):
        for phrase in ("$37/monthly", "$37 per monthly", "$37/yearly", "$37/weekly", "$37/mon",
                       "$37 monthly", "$37 per-month", "$37 annually", "$37 per mo", "$37 a months"):
            with self.subTest(caught=phrase):
                self.assertTrue(dw._RECURRING_PHRASE.search(phrase), phrase)
        for phrase in ("$37 a moment", "$37 per more", "$37 a monday"):
            with self.subTest(clean=phrase):
                self.assertIsNone(dw._RECURRING_PHRASE.search(phrase), phrase)

    def test_a_renewal_amount_on_a_one_time_d1_extension_is_refused(self):
        """The result extension may not claim a renewal for an offer the record prices as one-time."""
        paths = stage(_request(None, "1.0"))
        _edit(paths, "launch.json", lambda doc: _offer(doc, "downsell_1").update(prices=[self.ONE_DOLLAR]))
        _edit(paths, "extension-downsell_1.json",
              lambda doc: doc["downsell_result_extension"]["disclosure_audit"].update(due_now_minor=100,
                                                                                      renewal_amount_minor=2700))
        paths["copy-downsell_1.json"].write_text(json.dumps(_one_time_page(100)) + "\n")
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("D1-RESULT-DISCLOSURE-RENEWAL-ON-ONE-TIME", proc.stderr)
        self.assertFalse(paths["result"].exists())


class DownsellOfferIdNormalisationTests(unittest.TestCase):
    """DTY-03: the launcher writes real offer ids in `excludes`."""

    def real_ids(self, doc):
        _offer(doc, "upsell_1").update(offer_id="BF-U1", excludes=["BF-D1"])
        _offer(doc, "downsell_1").update(offer_id="BF-D1",
                                         excludes=["BF-U1"])

    def test_real_offer_ids_in_excludes_pass(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", self.real_ids)
        before = paths["launch.json"].read_bytes()
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        enriched = json.loads(paths["enriched"].read_text())
        self.assertEqual(enriched["declined_u1_offer_ref"], "BF-U1")
        self.assertEqual(enriched["downsell_offer_ref"], "BF-D1")
        # copies only: the record's own offers are not rewritten
        self.assertEqual(paths["launch.json"].read_bytes(), before)

    def test_d1_not_excluding_u1_still_fails(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", self.real_ids)
        _edit(paths, "launch.json",
              lambda d: _offer(d, "downsell_1").update(excludes=[]))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("D1-OFFER-EXCLUDES-U1-MISSING", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_u1_not_excluding_d1_still_fails(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", self.real_ids)
        _edit(paths, "launch.json",
              lambda d: _offer(d, "upsell_1").update(excludes=["BF-OTHER"]))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("D1-OFFER-U1-EXCLUDES-D1-MISSING", proc.stderr)


class DownsellNativeIdTests(unittest.TestCase):
    """DTY-04: ids exist only after the Skill 6 install."""

    def null_ids(self, doc):
        d1 = _offer(doc, "downsell_1")
        d1["native_product_id"] = None
        d1["prices"][0]["native_price_id"] = None

    def blockers(self, paths):
        return json.loads(paths["result"].read_text())["blockers"]

    def test_null_ids_at_design_exit_0_with_standing_blocker(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", self.null_ids)
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(any(b.startswith("D1-NATIVE-IDS-PENDING-INSTALL")
                            for b in self.blockers(paths)))
        enriched = json.loads(paths["enriched"].read_text())
        self.assertIsNone(enriched["native_product_id"])
        self.assertIsNone(enriched["native_price_id"])
        self.assertEqual(validate_request(enriched), [])

    def test_real_ids_carry_no_pending_blocker(self):
        paths, proc = stage_and_run(_request(None))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(any(b.startswith("D1-NATIVE-IDS-PENDING-INSTALL")
                             for b in self.blockers(paths)))

    def test_install_stage_refuses_null_ids(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", self.null_ids)
        proc = run_wrapper(paths, "--stage", "install")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("native_product_id", proc.stderr)
        self.assertIn("native_price_id", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_install_stage_accepts_real_ids(self):
        paths = stage(_request(None))
        proc = run_wrapper(paths, "--stage", "install")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_placeholder_ids_refused_at_install_and_design(self):
        for bad in ("TBD", "tbd", "TODO", "null", "N/A", " ", "ab",
                    "bad id", "x" * 200):
            for extra in ((), ("--stage", "install")):
                if bad == " " and not extra:
                    continue  # blank at design time is a null, not a value
                with self.subTest(bad=bad, extra=extra):
                    paths = stage(_request(None))
                    _edit(paths, "launch.json", lambda d: _offer(
                        d, "downsell_1").update(native_product_id=bad))
                    proc = run_wrapper(paths, *extra)
                    self.assertEqual(proc.returncode, 2, proc.stdout)
                    self.assertFalse(paths["result"].exists())
        paths = stage(_request(None))
        _edit(paths, "launch.json", lambda d: _offer(
            d, "downsell_1")["prices"][0].update(native_price_id="TBD"))
        proc = run_wrapper(paths, "--stage", "install")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("not a real native id", proc.stderr)


class DownsellEntryGuardAndHashTests(unittest.TestCase):
    """DTY-08: design-time D1 is a design deliverable."""

    def result(self, paths):
        return json.loads(paths["result"].read_text())

    def test_design_marker_without_a_journey_file(self):
        paths = stage(_request(None))
        proc = run_wrapper(paths, journey=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = json.loads(
            (paths["workdir"] / "entry-guard-downsell_1.json").read_text())
        self.assertEqual(record["mode"], "DESIGN-ONLY")
        self.assertEqual(record["journey_source"], "design-time marker")
        self.assertTrue(any(
            b.startswith("D1-ENTRY-GUARD-RUNTIME-ONLY")
            for b in self.result(paths)["blockers"]))

    def test_blocker_present_with_a_staged_journey(self):
        paths, proc = stage_and_run(_request(None))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(any(
            b.startswith("D1-ENTRY-GUARD-RUNTIME-ONLY")
            for b in self.result(paths)["blockers"]))

    def test_guard_still_refuses_a_disabled_u1(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json",
              lambda d: d["extras"].update(upsell_1=False))
        proc = run_wrapper(paths, journey=False)
        self.assertEqual(proc.returncode, 2, proc.stdout)

    def test_artifacts_record_the_input_hashes(self):
        paths, proc = stage_and_run(_request(None))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        by_path = {os.path.realpath(a["path"]): a["sha256"]
                   for a in self.result(paths)["artifacts"]}
        for name in ("launch.json", "enrichment-downsell_1.json",
                     "difference-table.md", "journey-downsell_1.json",
                     "entry-guard-downsell_1.json"):
            with self.subTest(name=name):
                self.assertEqual(by_path[os.path.realpath(
                    paths["workdir"] / name)],
                                 _sha(paths["workdir"] / name))

    def test_journey_claiming_a_purchase_on_a_live_launch_is_refused(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", lambda d: d.update(test_only=False))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("journey.main_purchased_verified", proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_live_launch_without_a_journey_is_a_design_run(self):
        paths = stage(_request(None))
        _edit(paths, "launch.json", lambda d: d.update(test_only=False))
        proc = run_wrapper(paths, journey=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_staged_journey_is_never_evaluated(self):
        # QC defect (attempt 2): every real dispatch passes --journey; a
        # non-claiming staged journey must not drive the guard.
        cases = {
            "live, no purchase": (False, {"main_purchased_verified": False,
                                          "u1_event": None,
                                          "u1_accepted": False}),
            "live, failed u1 payment": (False, {"main_purchased_verified": False,
                                                "u1_event": "payment_failed",
                                                "u1_accepted": False}),
            "test, no purchase": (True, {"main_purchased_verified": False,
                                         "u1_event": None,
                                         "u1_accepted": False}),
        }
        for name, (test_only, facts) in cases.items():
            with self.subTest(case=name):
                paths = stage(_request(None))
                _edit(paths, "launch.json",
                      lambda d, t=test_only: d.update(test_only=t))
                _edit(paths, "journey-downsell_1.json",
                      lambda d, f=facts: d.update(f))
                proc = run_wrapper(paths)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                record = json.loads((paths["workdir"]
                                     / "entry-guard-downsell_1.json").read_text())
                self.assertEqual(record["journey_source"], "design-time marker")
                self.assertIs(record["staged_journey_evaluated"], False)
                self.assertIs(record["evaluated_state"]["main_purchased_verified"],
                              True)
                self.assertEqual(record["evaluated_state"]["u1_event"],
                                 "explicit_decline")
                self.assertTrue(any(
                    b.startswith("D1-ENTRY-GUARD-RUNTIME-ONLY")
                    for b in self.result(paths)["blockers"]))
                by_path = {os.path.realpath(a["path"]): a["sha256"]
                           for a in self.result(paths)["artifacts"]}
                journey_file = paths["workdir"] / "journey-downsell_1.json"
                self.assertEqual(by_path[os.path.realpath(journey_file)],
                                 _sha(journey_file))

    def test_malformed_staged_journey_is_still_refused(self):
        paths = stage(_request(None))
        _edit(paths, "journey-downsell_1.json",
              lambda d: d.update(main_purchased_verified="yes"))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("journey.main_purchased_verified: must be a boolean",
                      proc.stderr)
        self.assertFalse(paths["result"].exists())

    def test_sidecar_must_cite_a_difference_table(self):
        paths = stage(_request(None))
        _edit(paths, "enrichment-downsell_1.json",
              lambda d: d.pop("difference_table_ref"))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("difference_table_ref", proc.stderr)

    def test_missing_or_mismatched_difference_table_is_refused(self):
        paths = stage(_request(None))
        _edit(paths, "enrichment-downsell_1.json", lambda d: d.update(
            difference_table_sha256="0" * 64))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("difference_table_sha256", proc.stderr)
        paths = stage(_request(None))
        paths["difference-table.md"].unlink()
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("difference table", proc.stderr)

    def test_matching_pinned_table_sha_is_accepted(self):
        paths = stage(_request(None))
        digest = _sha(paths["difference-table.md"])
        _edit(paths, "enrichment-downsell_1.json",
              lambda d: d.update(difference_table_sha256=digest))
        proc = run_wrapper(paths)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class DownsellHonestStatusTests(unittest.TestCase):
    """DTY-14: L2 only for three real-provider stage records."""

    def run_main(self, provider):
        paths = stage(_request(None))
        stages = {s: {"images": 8} for s in dw.IMAGES_RUN_STAGES}
        original = dw._run_images
        dw._run_images = lambda *a, **k: {
            "run_dir": str(paths["workdir"]), "artifacts": [],
            "stages": stages}
        try:
            code = dw.main([
                "--request", str(paths["request-downsell_1.json"]),
                "--result", str(paths["result"]),
                "--launch", str(paths["launch.json"]),
                "--route-graph", str(paths["route-graph.json"]),
                "--copy", str(paths["copy-downsell_1.json"]),
                "--enrichment", str(paths["enrichment-downsell_1.json"]),
                "--extension", str(paths["extension-downsell_1.json"]),
                "--skill81-root", str(SKILL81),
                "--skill71-root", str(SKILL71),
                "--image-provider", provider, "--allow-paid"])
        finally:
            dw._run_images = original
        return code, json.loads(paths["result"].read_text())

    def test_three_stage_records_and_a_real_provider_reach_l2(self):
        code, result = self.run_main("kie")
        self.assertEqual(code, 0)
        self.assertEqual((result["status"], result["proof_class"]),
                         ("locally_verified", "L2"))
        self.assertFalse(any(b.startswith("D1-STUB-IMAGES")
                             for b in result["blockers"]))

    def test_stub_provider_stays_authored_with_the_blocker(self):
        code, result = self.run_main("stub")
        self.assertEqual(code, 0)
        self.assertEqual((result["status"], result["proof_class"]),
                         ("authored", "L1"))
        self.assertTrue(any(b.startswith("D1-STUB-IMAGES")
                            for b in result["blockers"]))


class DownsellPinTests(unittest.TestCase):
    """DTY-27: the pins constrain the bytes, and the bytes that run are
    the bytes that were hashed."""

    PINS = {"validators/validate_downsell.py": dw.PIN_VALIDATE_DOWNSELL,
            "schemas/downsell-request.schema.json": dw.PIN_REQUEST_SCHEMA,
            "schemas/downsell-result-extension.schema.json":
                dw.PIN_EXTENSION_SCHEMA}

    def copy_tree(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="d1-pins-"))
        for rel in self.PINS:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes((SKILL81 / rel).read_bytes())
        return root

    def test_pins_equal_sha256_of_the_skill_81_files(self):
        # A pin edit and a byte edit must travel together, and a pin
        # change is an owner-approved act (CODEOWNERS on this file).
        for rel, pin in self.PINS.items():
            with self.subTest(rel=rel):
                self.assertEqual(_sha(SKILL81 / rel), pin)

    def test_one_changed_byte_fails_the_run(self):
        for rel in self.PINS:
            with self.subTest(rel=rel):
                root = self.copy_tree()
                with open(root / rel, "ab") as handle:
                    handle.write(b" ")
                paths = stage(_request(None))
                proc = run_wrapper(paths, skill81=root)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertIn("hash to", proc.stderr)
                self.assertIn(rel, proc.stderr)
                self.assertFalse(paths["result"].exists())

    def test_validator_runs_from_the_hashed_bytes(self):
        root = self.copy_tree()
        target = root / "validators" / "validate_downsell.py"
        real_read, swapped = dw._read_bytes, []

        def read_then_swap(path, what):
            raw = real_read(path, what)
            if path == target and not swapped:  # swap after the hash read
                swapped.append(True)
                path.write_text("def check_entry_guard(state):\n"
                                "    return ['TAMPERED']\n")
            return raw

        dw._read_bytes = read_then_swap
        try:
            mod, _, _ = dw._load_skill81(root)
        finally:
            dw._read_bytes = real_read
        self.assertTrue(swapped)
        self.assertNotEqual(mod.check_entry_guard({}), ["TAMPERED"])
        self.assertIn("D1-GUARD-NO-VERIFIED-MAIN-PURCHASE",
                      mod.check_entry_guard({}))


if __name__ == "__main__":
    unittest.main()
