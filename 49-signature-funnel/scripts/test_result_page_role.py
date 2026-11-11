#!/usr/bin/env python3
"""Harmony issue 85: every page result Skill 49 builds echoes its request's page_role.

The one canonical page-result schema (shared-utils/signature_launch/domain/, copied byte for byte
into scripts/vendor/ here and into Skill 71) REQUIRES `page_role`. Skill 49's own result builders
copy it from the request: the downsell wrapper (both builders, through RESULT_FIELDS), the
thank-you translator, the dispatch simulated executor and the tampered-emitter fixture. This test
fails when a builder drops it, and when the vendored schema stops requiring it.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

ROLES = ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"]
REQUEST = {"schema_version": "1.0", "tenant_id": "T", "location_id": "L", "launch_id": "LA", "revision": 1,
           "request_id": "R", "input_hash": "H", "page_id": "P", "page_role": "thank_you", "test_only": True}


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResultsEchoPageRole(unittest.TestCase):
    def test_the_vendored_schema_requires_and_closes_page_role(self):
        schema = json.loads((HERE / "vendor" / "page-result.schema.json").read_text(encoding="utf-8"))
        self.assertIn("page_role", schema["required"])
        self.assertEqual(schema["properties"]["page_role"]["enum"], ROLES)

    def test_the_thank_you_translator_echoes_the_request_role(self):
        translate = load("translate_thank_you_result", "translate_thank_you_result.py")
        result = translate._page_result(
            REQUEST, status="authored", artifacts=[], author_session="a", reviewer_session=None,
            independent_review=False, proof_class="L0", blockers=[], native_bindings_ref=None)
        self.assertEqual(result["page_role"], "thank_you")

    def test_the_dispatch_simulated_executor_echoes_the_request_role(self):
        dispatch = load("dispatch_launch", "dispatch_launch.py")
        for role in ROLES:
            request = dict(REQUEST, page_role=role)
            self.assertEqual(dispatch._simulated_executor("author-1")(request)["page_role"], role)

    def test_the_downsell_wrapper_projects_page_role_into_every_result(self):
        downsell = load("downsell_wrapper", "downsell_wrapper.py")
        self.assertIn("page_role", downsell.RESULT_FIELDS)
        source = (HERE / "downsell_wrapper.py").read_text(encoding="utf-8")
        self.assertIn('"page_id",\n            "page_role")', source, "the downsell_2 builder drops page_role")
        self.assertIn('"page_role": request["page_role"]', source, "the downsell_1 builder drops page_role")

    def test_the_tampered_emitter_fixture_carries_a_page_role(self):
        source = (HERE / "fixtures" / "tampered_emitter.py").read_text(encoding="utf-8")
        self.assertIn('"page_role": "product_selection"', source)


if __name__ == "__main__":
    unittest.main()
