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

Run: python3 -m unittest test_downsell_wrapper (from this
directory) or python3 test_downsell_wrapper.py.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
SKILL81 = REPO / "81-signature-downsell"
WRAPPER = SCRIPTS / "downsell_wrapper.py"

sys.path.insert(0, str(SKILL81 / "validators"))
from validate_request import validate_request  # noqa: E402

PAGE_FIXTURE = json.loads(
    (SKILL81 / "fixtures" / "valid-downsell-page.json").read_text())
RESULT_FIXTURE = json.loads(
    (SKILL81 / "fixtures" / "valid-downsell-result.json").read_text())

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
    put("copy-downsell_1.json", PAGE_FIXTURE)
    put("journey-downsell_1.json",
        {"main_purchased_verified": True,
         "u1_event": "explicit_decline", "u1_accepted": False})
    put("enrichment-downsell_1.json",
        {"difference_kind": "reduced_scope",
         "rationale": "TEST ONLY recorded rationale.",
         "entry_guard_ref": "TEST-ENTRY-GUARD"})
    put("extension-downsell_1.json", RESULT_FIXTURE)
    paths["result"] = workdir / "result-downsell_1.json"
    paths["enriched"] = workdir / "downsell-request-enriched.json"
    return paths


def run_wrapper(paths):
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
         "--skill81-root", str(SKILL81)],
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
        self.assertEqual(summary["status"], "locally_verified")
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


if __name__ == "__main__":
    unittest.main()
