#!/usr/bin/env python3
"""Explicit router aliases stay literal; admission is not a completed model call.

All request/response data here are offline fixtures. This suite submits no LLM
request and never claims that a real chain member answered.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from choice_card.intake_card import ai_models as AM

BUILD = "deepseek-chain"
CHECK = "opus-chain"
# Identical to the two names confirmed by the owner's read-only live /v1/models
# index. This fixture proves how availability is consumed, not a new live call.
AVAILABLE_ROUTER_IDS = {BUILD, CHECK}


class ExplicitChainContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="skill75-explicit-chain-")
        self.addCleanup(self.tmp.cleanup)
        self.run = self.tmp.name

    def bind(self, **kwargs):
        result = AM.bind_roles(self.run, BUILD, CHECK, **kwargs)
        self.assertTrue(result["ok"], result)
        return result

    def test_explicit_pair_parses_without_provider_or_member_substitution(self):
        selected, error = AM.parse("deepseek-chain builds, opus-chain checks")
        self.assertIsNone(error)
        self.assertEqual(selected, {"build": BUILD, "check": CHECK, "route": "router-alias"})
        for runtime in ("claude-nine", "openclaw", "openrouter-direct"):
            self.assertEqual(AM.dispatch_id(BUILD, runtime), BUILD)
            self.assertEqual(AM.dispatch_id(CHECK, runtime), CHECK)

    def test_route_availability_uses_exact_router_index_ids(self):
        availability = {mid: mid in AVAILABLE_ROUTER_IDS for mid in AM.MODELS}
        result = AM.bind_roles(self.run, BUILD, CHECK, availability=availability)
        self.assertTrue(result["ok"], result)
        unavailable = dict(availability, **{BUILD: False})
        result = AM.check_result(BUILD, CHECK, availability=unavailable)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "MODEL_UNAVAILABLE")

    def test_build_check_and_repair_admit_exact_literal_ids(self):
        bound = self.bind(runtime="claude-nine")
        self.assertEqual(set(bound["bindings"]), {"build", "check"})
        for role, wanted in ((AM.ROLE_BUILD, BUILD), (AM.ROLE_CHECK, CHECK), (AM.ROLE_REPAIR, CHECK)):
            result = AM.admit_dispatch(self.run, role, wanted, route="router-alias", runtime="claude-nine")
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["dispatch"]["call_id"], wanted)
            self.assertEqual(result["binding"]["model_id"], wanted)
            self.assertEqual(result["binding_role"], "check" if role == "repair" else role)
        repair = AM.admit_dispatch(self.run, "repair", CHECK)
        self.assertEqual(repair["binding"]["role_id"], bound["bindings"]["check"]["role_id"])

    def test_unknown_route_or_alias_and_changed_role_are_refused(self):
        result = AM.bind_roles(self.run, "not-configured-chain", CHECK)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "MODEL_UNKNOWN")
        self.assertFalse((Path(self.run) / AM.STORE_NAME).exists())
        self.bind()
        self.assertEqual(AM.admit_dispatch(self.run, "build", BUILD, route="unknown-route")["error_code"], "ROUTE_MISMATCH")
        self.assertEqual(AM.admit_dispatch(self.run, "build", "deepseek")["error_code"], "MODEL_MISMATCH")
        self.assertEqual(AM.admit_dispatch(self.run, "repair", BUILD)["error_code"], "MODEL_MISMATCH")

    def test_same_pair_is_idempotent_and_preserves_existing_attempts(self):
        first = self.bind(now="2026-10-24T15:00:00Z")
        doc = AM.load_bindings(self.run)
        doc["attempts"] = [{"attempt_id": "historical-fixture", "verified": False}]
        doc["keep_owner_record"] = {"untouched": True}
        AM._write_store(self.run, doc)
        path = Path(self.run) / AM.STORE_NAME
        before = path.read_bytes()
        again = self.bind(now="2026-10-24T16:00:00Z", bound_by="confirmed-intake")
        self.assertTrue(again["reused"])
        self.assertEqual(again["binding_id"], first["binding_id"])
        self.assertEqual(path.read_bytes(), before)
        duplicate = AM.record_attempt(self.run, "build", "historical-fixture", requested_model=BUILD,
            resolved_provider_model="fixture/member", response_model="fixture/member")
        self.assertEqual(duplicate["error_code"], "ATTEMPT_EXISTS")
        self.assertEqual(path.read_bytes(), before)

    def test_conflicting_pair_or_runtime_never_rebinds(self):
        self.bind(runtime="claude-nine")
        path = Path(self.run) / AM.STORE_NAME
        before = path.read_bytes()
        for build, check, runtime in ((CHECK, BUILD, "claude-nine"),
                                      (BUILD, CHECK, "openclaw"),
                                      (AM.REC_BUILD, AM.REC_CHECK, "claude-nine")):
            result = AM.bind_roles(self.run, build, check, runtime=runtime)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "ROLE_BINDING_CONFLICT")
            self.assertEqual(path.read_bytes(), before)

    def test_chain_member_or_alias_claim_is_unverified_without_supported_receipt(self):
        self.bind()
        path = Path(self.run) / AM.STORE_NAME
        before = path.read_bytes()
        # 9Router requestDetails records id/provider/model/providerResponse;
        # these uncorrelated offline fields alone never prove the alias request.
        receipt = {"id": "fixture-router-row", "provider": "fixture", "model": "fixture/member",
                   "status": "success", "providerResponse": {"id": "fixture-response", "model": "fixture/member"}}
        for resolved, response, proof in (("fixture/member", "fixture/member", receipt),
                                           (BUILD, BUILD, "alias-only-is-not-proof")):
            result = AM.record_attempt(self.run, "build", "unverified-fixture", requested_model=BUILD,
                resolved_provider_model=resolved, response_model=response, route="router-alias",
                request_receipt="fixture-request", router_receipt=proof, response_evidence="router_receipt")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "CHAIN_RESOLUTION_UNVERIFIED")
            self.assertEqual(path.read_bytes(), before)

    def test_recommended_pair_and_other_approved_choices_are_unchanged(self):
        self.assertEqual(AM.recommended(), {"build": "openrouter/xiaomi/mimo-v2.6-pro",
            "check": "openrouter/z-ai/glm-5.3", "route": "openrouter"})
        self.assertEqual(AM.resolve("deepseek")[0], "openrouter/deepseek/deepseek-v4-flash")
        selected, error = AM.parse("MiniMax M3 builds, GLM 5.3 checks")
        self.assertIsNone(error)
        self.assertEqual(selected["build"], "ollama/minimax-m3")
        self.assertEqual(selected["check"], "openrouter/z-ai/glm-5.3")


if __name__ == "__main__":
    unittest.main()
