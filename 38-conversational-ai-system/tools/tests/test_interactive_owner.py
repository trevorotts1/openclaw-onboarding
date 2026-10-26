#!/usr/bin/env python3
"""Acceptance proof for the interactive-owner contract (PBB-115 T-19 / C-19).

Each acceptance clause has its own test class, and every refusal case asserts
the exact code and that no route came back -- a refusal that still named a
responder would re-open the two-responder defect the contract exists to close.

Acceptance: "OpenClaw default; workflow controls/callbacks/free text/stale tap;
no two responders."

Run: python3 tools/tests/test_interactive_owner.py
     bash scripts/qc-interactive-owner.sh
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
SKILL_ROOT = TOOLS_DIR.parent
REPO_ROOT = SKILL_ROOT.parent

# The main the bookkeeping gate is pinned to, named by SHA on purpose.
# ``origin/main`` is a moving ref: once main advances past a branch's marker, a
# gate that read the ref reddened every branch cut earlier -- BUILD stuck on
# work that changed nothing here. A branch is measured against this named main;
# raise the pin when the gate should be judged against a newer one. The
# duplicate-version bite still reads live ``origin/main``.
MAIN_PIN_SHA = "a6bfbfb62ff7980ef6aae8ea9e2682fba98a31f8"
SKILL_38_PATH = "38-conversational-ai-system"
sys.path.insert(0, str(TOOLS_DIR))

import interactive_owner as owner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "interactive-owner"


def fixture(name):
    return str(FIXTURES / name)


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def base_contract():
    return load_fixture("valid.json")


def controls_contract(**overrides):
    doc = base_contract()
    doc.update(overrides)
    return doc


class ContractFixtureTests(unittest.TestCase):
    def test_canonical_fixture_validates(self):
        self.assertEqual(owner.validate_contract(base_contract()), [])

    def test_schema_rejects_an_unknown_property(self):
        doc = controls_contract(second_owner="native_ghl")
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertIn("unexpected property", errors[0])

    def test_schema_rejects_an_unknown_free_text_policy(self):
        doc = base_contract()
        doc["steps"][0]["free_text"] = "maybe"
        errors = owner.validate_contract(doc)
        self.assertTrue(any("free_text" in err for err in errors), errors)

    def test_schema_rejects_a_control_list_without_a_control(self):
        doc = base_contract()
        doc["steps"][0]["controls"] = []
        self.assertTrue(owner.validate_contract(doc))

    def test_a_repeated_step_id_is_refused(self):
        doc = base_contract()
        doc["steps"].append(copy.deepcopy(doc["steps"][0]))
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.DUPLICATE_STEP), errors)


class OpenClawDefaultTests(unittest.TestCase):
    """Acceptance clause 1: OpenClaw is the default owner."""

    def test_owner_omitted_defaults_to_openclaw_inbound(self):
        doc = base_contract()
        self.assertNotIn("owner", doc)
        self.assertEqual(owner.validate_contract(doc), [])
        verdict = owner.resolve_event(
            doc,
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["route"]["id"], owner.OWNER_OPENCLAW)
        self.assertEqual(verdict["route"]["kind"], owner.OWNER_OPENCLAW)

    def test_the_default_owner_carries_the_inbound_path(self):
        doc = base_contract()
        verdict = owner.resolve_event(
            doc,
            {
                "kind": "free_text",
                "step_id": "pick_time",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["route"]["inbound_path"], "hooks/skill38-inbound")

    def test_an_explicit_openclaw_owner_still_resolves(self):
        doc = controls_contract(owner={"kind": "openclaw_inbound"})
        verdict = owner.resolve_event(
            doc,
            {
                "kind": "callback",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["route"]["id"], owner.OWNER_OPENCLAW)


class WorkflowControlTests(unittest.TestCase):
    """Acceptance clause 2a: rendered workflow controls resolve to the owner."""

    def test_a_control_press_routes_to_the_owner(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["code"], owner.ROUTED)
        self.assertEqual(verdict["input"], "control")
        self.assertEqual(verdict["control_id"], "wed_2pm")

    def test_a_control_the_step_does_not_offer_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "thu_4pm",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], owner.UNKNOWN_CONTROL)
        self.assertIsNone(verdict["route"])

    def test_a_control_from_an_unknown_step_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "not_a_step",
                "control_id": "tue_10am",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["code"], owner.UNKNOWN_STEP)
        self.assertIsNone(verdict["route"])

    def test_a_control_without_a_control_id_is_malformed(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "control", "step_id": "pick_time", "generation": 3},
        )
        self.assertEqual(verdict["code"], owner.MALFORMED_EVENT)


class CallbackTests(unittest.TestCase):
    """Acceptance clause 2b: provider callbacks resolve to the same owner."""

    def test_a_callback_routes_to_the_same_owner_as_a_control(self):
        doc = base_contract()
        control = owner.resolve_event(
            doc,
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 3,
            },
        )
        callback = owner.resolve_event(
            doc,
            {
                "kind": "callback",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 3,
            },
        )
        self.assertEqual(callback["status"], "accepted")
        self.assertEqual(callback["input"], "callback")
        self.assertEqual(callback["route"], control["route"])

    def test_a_callback_without_a_control_id_is_malformed(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "callback", "step_id": "pick_time", "generation": 3},
        )
        self.assertEqual(verdict["code"], owner.MALFORMED_EVENT)
        self.assertIsNone(verdict["route"])

    def test_a_callback_for_an_unknown_control_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "callback",
                "step_id": "confirm",
                "control_id": "tue_10am",
                "generation": 1,
            },
        )
        self.assertEqual(verdict["code"], owner.UNKNOWN_CONTROL)
        self.assertIsNone(verdict["route"])


class FreeTextTests(unittest.TestCase):
    """Acceptance clause 2c: free text follows the same single owner."""

    def test_free_text_is_routed_when_the_step_accepts_it(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "free_text", "step_id": "pick_time", "generation": 3},
        )
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["input"], "free_text")
        self.assertEqual(verdict["route"]["id"], owner.OWNER_OPENCLAW)

    def test_free_text_is_refused_when_the_step_rejects_it(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "free_text", "step_id": "confirm", "generation": 1},
        )
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], owner.FREE_TEXT_REJECTED)
        self.assertIsNone(verdict["route"])

    def test_free_text_on_an_unknown_step_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "free_text", "step_id": "nope", "generation": 3},
        )
        self.assertEqual(verdict["code"], owner.UNKNOWN_STEP)


class StaleTapTests(unittest.TestCase):
    """Acceptance clause 2d: a stale tap is refused, never answered twice."""

    def test_a_stale_control_tap_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 2,
            },
        )
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], owner.STALE_TAP)
        self.assertIsNone(verdict["route"])

    def test_a_stale_callback_is_refused(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "callback",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 1,
            },
        )
        self.assertEqual(verdict["code"], owner.STALE_TAP)
        self.assertIsNone(verdict["route"])

    def test_a_future_generation_is_refused_too(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 4,
            },
        )
        self.assertEqual(verdict["code"], owner.STALE_TAP)

    def test_the_current_generation_is_accepted(self):
        verdict = owner.resolve_event(
            base_contract(),
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 3,
            },
        )
        self.assertEqual(verdict["status"], "accepted")

    def test_a_missing_generation_is_malformed_not_stale(self):
        verdict = owner.resolve_event(
            base_contract(),
            {"kind": "control", "step_id": "pick_time", "control_id": "tue_10am"},
        )
        self.assertEqual(verdict["code"], owner.MALFORMED_EVENT)


class SingleResponderTests(unittest.TestCase):
    """Acceptance clause 3: no two responders, ever."""

    def test_two_responders_are_refused(self):
        doc = load_fixture("two-responders.json")
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.TWO_RESPONDERS), errors)
        verdict = owner.resolve_event(
            doc,
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 1,
            },
        )
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], owner.TWO_RESPONDERS)
        self.assertIsNone(verdict["route"])

    def test_zero_responders_are_refused(self):
        doc = controls_contract(responders=[])
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.NO_RESPONDER), errors)

    def test_a_responder_kind_that_disagrees_with_the_owner_is_refused(self):
        doc = controls_contract(
            owner={"kind": "openclaw_inbound"},
            responders=[{"id": "openclaw_inbound", "kind": "native_ghl"}],
        )
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.RESPONDER_MISMATCH), errors)

    def test_a_single_matching_responder_passes(self):
        doc = controls_contract(
            owner={"kind": "openclaw_inbound"},
            responders=[{"id": "openclaw_inbound", "kind": "openclaw_inbound"}],
        )
        self.assertEqual(owner.validate_contract(doc), [])

    def test_the_default_derives_exactly_one_responder(self):
        doc = base_contract()
        self.assertNotIn("responders", doc)
        self.assertEqual(owner.validate_contract(doc), [])


class NativeGhlOwnerTests(unittest.TestCase):
    """A native GHL owner is admitted only through the launch gate's verdict."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="interactive-owner-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_bundle(self, reply_owner):
        bundle = self.tmp / "launch-bundle.json"
        bundle.write_text(json.dumps({"reply_owner": reply_owner}), encoding="utf-8")
        return bundle

    def native_doc(self, bundle_name):
        return controls_contract(
            owner={"kind": "native_ghl", "launch_bundle": bundle_name},
            responders=[{"id": "native_ghl", "kind": "native_ghl"}],
        )

    def test_native_ghl_without_a_launch_bundle_is_refused(self):
        doc = controls_contract(
            owner={"kind": "native_ghl"},
            responders=[{"id": "native_ghl", "kind": "native_ghl"}],
        )
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.OWNER_NOT_VERIFIED), errors)

    def test_native_ghl_is_refused_when_the_bundle_names_openclaw(self):
        bundle = self.write_bundle({"kind": "openclaw_inbound"})
        doc = self.native_doc(bundle.name)
        launch_owner = owner.load_launch_owner(bundle.name, self.tmp)
        # The read has to have landed before the refusal means anything: a
        # bundle that names OpenClaw and a bundle that yielded no owner at all
        # are refused with the same code, so only the record itself separates
        # "the gate refused a real verdict" from "nothing was ever read".
        self.assertEqual(launch_owner, {"kind": "openclaw_inbound"})
        errors = owner.validate_contract(doc, launch_owner)
        self.assertTrue(errors)
        self.assertTrue(errors[0].startswith(owner.OWNER_NOT_VERIFIED), errors)
        self.assertIn("does not name native_ghl", errors[0])

    def test_native_ghl_is_allowed_when_the_bundle_names_it(self):
        bundle = self.write_bundle({"kind": "native_ghl"})
        doc = self.native_doc(bundle.name)
        launch_owner = owner.load_launch_owner(bundle.name, self.tmp)
        self.assertEqual(owner.validate_contract(doc, launch_owner), [])
        verdict = owner.resolve_event(
            doc,
            {
                "kind": "callback",
                "step_id": "pick_time",
                "control_id": "tue_10am",
                "generation": 3,
            },
            launch_owner,
        )
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["route"]["kind"], owner.OWNER_NATIVE_GHL)

    def test_this_module_never_judges_translation_approval(self):
        # The launch gate owns REPLY_OWNER_TRANSLATION. A bundle that names
        # native_ghl but carries no approval marker is still admitted HERE, and
        # still refused THERE -- one authority, no second copy of the guard.
        bundle = self.write_bundle({"kind": "native_ghl"})
        doc = self.native_doc(bundle.name)
        launch_owner = owner.load_launch_owner(bundle.name, self.tmp)
        self.assertNotIn("translation_approved", launch_owner)
        self.assertEqual(owner.validate_contract(doc, launch_owner), [])


class OwnershipDocumentTests(unittest.TestCase):
    """The 44-side of the conflict, pinned by content rather than prose trust."""

    def test_skill_44_declares_it_never_answers_an_interactive_step(self):
        text = (REPO_ROOT / "44-convert-and-flow-operator" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("never answers a conversation or an interactive step", text)
        self.assertIn("launch/interactive-owner-contract.md", text)

    def test_skill_38_points_at_the_interactive_contract(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("launch/interactive-owner-contract.md", text)

    def test_the_contract_document_names_all_four_inputs(self):
        text = (SKILL_ROOT / "launch" / "interactive-owner-contract.md").read_text(
            encoding="utf-8"
        )
        for token in ("control", "callback", "free text", "stale tap", "one responder"):
            self.assertIn(token, text.lower())


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="interactive-owner-cli-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(err):
            code = owner.main(list(argv))
        return code, buffer.getvalue(), err.getvalue()

    def test_validate_accepts_the_canonical_fixture(self):
        code, out, _ = self.run_cli("validate", "--contract", fixture("valid.json"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "accepted")

    def test_validate_refuses_two_responders(self):
        code, out, _ = self.run_cli(
            "validate", "--contract", fixture("two-responders.json")
        )
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "refused")
        self.assertTrue(payload["errors"][0].startswith(owner.TWO_RESPONDERS))

    def test_resolve_returns_zero_for_an_accepted_tap(self):
        event = json.dumps(
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 3,
            }
        )
        code, out, _ = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", event
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["route"]["id"], owner.OWNER_OPENCLAW)

    def test_resolve_returns_one_for_a_stale_tap(self):
        event = json.dumps(
            {
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 2,
            }
        )
        code, out, _ = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", event
        )
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["code"], owner.STALE_TAP)
        self.assertIsNone(payload["route"])

    def test_usage_is_exit_two(self):
        code, _, err = self.run_cli("nonsense")
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_an_unparseable_inline_event_is_a_usage_exit_not_a_traceback(self):
        # The inline --event value is caller-controlled text at a trust
        # boundary. Unparseable input must reach the documented exit 2 with the
        # usage error; a raw json traceback is exit 1 and prints no verdict at
        # all, which is neither of the two answers the contract documents.
        code, out, err = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", "{not json"
        )
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON event", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.strip(), "")

    def test_the_same_bad_json_is_the_same_exit_inline_or_in_a_file(self):
        path = self.tmp / "bad-event.json"
        path.write_text("{not json", encoding="utf-8")
        code, out, err = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", str(path)
        )
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.strip(), "")

    def test_resolve_still_reads_a_valid_event_from_a_file(self):
        # Inverse: the file branch of _parse_event is untouched and still
        # routes, so the fix did not narrow what counts as a usable event.
        path = self.tmp / "event.json"
        path.write_text(
            json.dumps({
                "kind": "control",
                "step_id": "pick_time",
                "control_id": "wed_2pm",
                "generation": 3,
            }),
            encoding="utf-8",
        )
        code, out, _ = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", str(path)
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["route"]["id"], owner.OWNER_OPENCLAW)


GOOD_EVENT = json.dumps(
    {"kind": "control", "step_id": "pick_time", "control_id": "wed_2pm", "generation": 3}
)
# Valid JSON that is not an object. Every one is a document a caller can hand
# the tool; none of them is a contract or an event.
NON_OBJECTS = (("null", "null"), ("list", "[]"), ("string", '"hello"'),
               ("int", "5"), ("bool", "true"))


class HostileInputTests(unittest.TestCase):
    """PBB-157 review: a null event was accepted and a non-object contract crashed.

    Every case asserts the exit code, the verdict code, ``route: None`` and no
    traceback, so a test passes only on the documented answer and never on
    "some failure happened".
    """

    setUp = CliTests.setUp
    tearDown = CliTests.tearDown
    run_cli = CliTests.run_cli

    def write(self, name, data):
        path = self.tmp / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return str(path)

    def assert_refused(self, argv, want_code):
        code, out, err = self.run_cli(*argv)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 1, (out, err))
        payload = json.loads(out)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], want_code)
        self.assertIsNone(payload["route"])
        return payload

    def assert_usage(self, argv, needle):
        code, out, err = self.run_cli(*argv)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(out.strip(), "")
        self.assertIn(needle, err)

    # Defect 1 -- fail-open: a null event must never be accepted.

    def test_a_null_inline_event_is_refused_not_accepted(self):
        self.assert_refused(
            ("resolve", "--contract", fixture("valid.json"), "--event", "null"),
            owner.MALFORMED_EVENT,
        )

    def test_a_null_event_file_is_refused_not_accepted(self):
        path = self.write("event-null.json", "null")
        self.assert_refused(
            ("resolve", "--contract", fixture("valid.json"), "--event", path),
            owner.MALFORMED_EVENT,
        )

    def test_resolve_contract_with_a_none_event_is_a_refusal(self):
        verdict = owner.resolve_contract(fixture("valid.json"), None)
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict.get("code"), owner.MALFORMED_EVENT)
        self.assertIsNone(verdict.get("route"))

    def test_every_non_object_event_is_malformed(self):
        for name, text in NON_OBJECTS[1:] + (("object", "{}"),):
            with self.subTest(event=name):
                self.assert_refused(
                    ("resolve", "--contract", fixture("valid.json"), "--event", text),
                    owner.MALFORMED_EVENT,
                )

    def test_omitting_the_event_still_only_validates(self):
        # Inverse: the validate-only path is the omitted event, not a None one.
        result = owner.resolve_contract(fixture("valid.json"))
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["errors"], [])
        refused = owner.resolve_contract(fixture("two-responders.json"))
        self.assertEqual(refused["status"], "refused")
        self.assertTrue(refused["errors"][0].startswith(owner.TWO_RESPONDERS))

    # Defect 2 -- crash: a contract that is not an object is a verdict.

    def test_a_non_object_contract_is_refused_by_validate(self):
        for name, text in NON_OBJECTS:
            with self.subTest(contract=name):
                path = self.write("contract-%s.json" % name, text)
                code, out, err = self.run_cli("validate", "--contract", path)
                self.assertNotIn("Traceback", err)
                self.assertEqual(code, 1, (out, err))
                payload = json.loads(out)
                self.assertEqual(payload["status"], "refused")
                self.assertTrue(
                    payload["errors"][0].startswith(owner.INVALID_CONTRACT), payload
                )

    def test_a_non_object_contract_is_refused_by_resolve(self):
        for name, text in NON_OBJECTS:
            with self.subTest(contract=name):
                path = self.write("contract-%s.json" % name, text)
                self.assert_refused(
                    ("resolve", "--contract", path, "--event", GOOD_EVENT),
                    owner.INVALID_CONTRACT,
                )

    def test_a_non_object_owner_is_refused_not_crashed(self):
        for name, value in (("string", "native_ghl"), ("int", 5), ("list", ["x"])):
            with self.subTest(owner=name):
                path = self.write(
                    "owner-%s.json" % name,
                    json.dumps(controls_contract(owner=value)),
                )
                code, out, err = self.run_cli("validate", "--contract", path)
                self.assertNotIn("Traceback", err)
                self.assertEqual(code, 1, (out, err))
                self.assertTrue(
                    json.loads(out)["errors"][0].startswith(owner.INVALID_CONTRACT)
                )
                self.assert_refused(
                    ("resolve", "--contract", path, "--event", GOOD_EVENT),
                    owner.INVALID_CONTRACT,
                )

    def test_schema_refusals_carry_the_stable_invalid_contract_code(self):
        for doc in (None, [], "hello", controls_contract(second_owner="x")):
            with self.subTest(doc=repr(doc)[:40]):
                errors = owner.validate_contract(doc)
                self.assertTrue(errors)
                self.assertTrue(errors[0].startswith(owner.INVALID_CONTRACT), errors)

    def test_a_valid_contract_from_a_file_still_routes(self):
        # Inverse: the canonical bytes still validate and still route.
        code, out, _ = self.run_cli("validate", "--contract", fixture("valid.json"))
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", GOOD_EVENT
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["route"]["id"], owner.OWNER_OPENCLAW)

    # Same class, IO side: an unreadable caller path is "2 = usage or IO".

    def test_unreadable_paths_are_a_usage_exit_not_a_traceback(self):
        folder = self.tmp / "a-folder"
        folder.mkdir()
        latin = self.write("latin.json", b'{"x": "\xff"}')
        cases = (
            ("contract is a folder", ("validate", "--contract", str(folder))),
            ("contract not UTF-8", ("validate", "--contract", latin)),
            ("event file not UTF-8",
             ("resolve", "--contract", fixture("valid.json"), "--event", latin)),
            ("launch bundle is a folder",
             ("validate", "--contract", fixture("valid.json"),
              "--launch-bundle", str(folder))),
            ("inline event nested past the parser limit",
             ("resolve", "--contract", fixture("valid.json"), "--event", "[" * 1000000)),
            ("contract value nested past the checker limit",
             ("validate", "--contract", self.write(
                 "deep.json",
                 '{"schema_version": 1, "contract_id": "x", "owner": {"kind": '
                 + "[" * 100000 + "]" * 100000 + "}, "
                 + json.dumps({"steps": base_contract()["steps"]})[1:],
             ))),
        )
        for label, argv in cases:
            with self.subTest(case=label):
                self.assert_usage(argv, "usage:")

    def test_a_long_inline_event_is_parsed_not_probed_to_a_crash(self):
        # The file-or-inline probe used to raise OSError (name too long) on
        # Python 3.9 for any inline event longer than one path component, so a
        # valid event crashed instead of routing.
        event = json.dumps(dict(json.loads(GOOD_EVENT), note="x" * 400))
        code, out, err = self.run_cli(
            "resolve", "--contract", fixture("valid.json"), "--event", event
        )
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(json.loads(out)["route"]["id"], owner.OWNER_OPENCLAW)


class ContractCodeTests(unittest.TestCase):
    """PBB-261 D3: the codes the contract document names are the codes emitted.

    ``validate_schema`` returns as soon as a field fails its declared type, so
    with the schema first these two declared refusals were unreachable: a
    contract naming ``responders`` as a string answered ``INVALID_CONTRACT:
    $.responders: expected type array`` and a step with ``free_text: "maybe"``
    answered ``INVALID_CONTRACT: $.steps[0].free_text: ...`` -- never the
    ``NO_RESPONDER`` / ``INVALID_STEP`` the contract document tells a caller to
    assert on. Each case asserts the exact code, so it fails on "some refusal
    happened" as well as on acceptance.
    """

    def test_a_non_list_responders_field_reports_no_responder(self):
        doc = controls_contract(responders="openclaw_inbound")
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertEqual(errors[0].split(":", 1)[0], owner.NO_RESPONDER)
        self.assertIn("responders must be a list", errors[0])

    def test_a_non_list_responders_field_is_a_refusal_not_an_acceptance(self):
        path = self.tmp_path("responders-string.json", json.dumps(
            controls_contract(responders="openclaw_inbound")))
        code, out, err = self.run_cli("validate", "--contract", path)
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["errors"][0].split(":", 1)[0], owner.NO_RESPONDER)

    def test_an_unknown_free_text_policy_reports_invalid_step(self):
        doc = base_contract()
        doc["steps"][0]["free_text"] = "maybe"
        errors = owner.validate_contract(doc)
        self.assertTrue(errors)
        self.assertEqual(errors[0].split(":", 1)[0], owner.INVALID_STEP)

    def test_a_missing_free_text_policy_reports_invalid_step_too(self):
        # Class, not instance: the schema's ``required`` list would have
        # swallowed this one as well.
        doc = base_contract()
        del doc["steps"][0]["free_text"]
        errors = owner.validate_contract(doc)
        self.assertEqual(errors[0].split(":", 1)[0], owner.INVALID_STEP)

    def test_the_declared_codes_survive_a_bad_free_text_on_a_non_first_step(self):
        doc = base_contract()
        doc["steps"][1]["free_text"] = "whenever"
        errors = owner.validate_contract(doc)
        self.assertEqual(errors[0].split(":", 1)[0], owner.INVALID_STEP)

    def test_a_contract_that_only_fails_the_schema_still_says_invalid_contract(self):
        # Inverse: moving the guards forward did not steal INVALID_CONTRACT
        # from a document that is simply the wrong shape.
        errors = owner.validate_contract(controls_contract(second_owner="x"))
        self.assertTrue(errors[0].startswith(owner.INVALID_CONTRACT), errors)
        self.assertEqual(owner.validate_contract(None)[0].split(":", 1)[0],
                         owner.INVALID_CONTRACT)

    setUp = CliTests.setUp
    tearDown = CliTests.tearDown
    run_cli = CliTests.run_cli

    def tmp_path(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)


class WhitespaceIdentityTests(unittest.TestCase):
    """PBB-261 D4: a whitespace-only name is not an identity.

    The event side judged ``step_id`` and ``control_id`` with ``_nonempty``; the
    contract side used the schema's ``minLength: 1``, which a run of spaces
    satisfies. So a step declared ``step_id: "   "`` validated and was then
    unroutable by any event -- its id could only ever be echoed back as
    ``MALFORMED_EVENT``.
    """

    setUp = CliTests.setUp
    tearDown = CliTests.tearDown
    run_cli = CliTests.run_cli

    def tmp_path(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def assert_refused_step(self, doc):
        errors = owner.validate_contract(doc)
        self.assertTrue(errors, "a whitespace-only identity was accepted")
        self.assertEqual(errors[0].split(":", 1)[0], owner.INVALID_STEP, errors)
        return errors

    def test_a_whitespace_only_step_id_is_refused(self):
        doc = base_contract()
        doc["steps"][0]["step_id"] = "   "
        self.assert_refused_step(doc)

    def test_a_whitespace_only_control_id_is_refused(self):
        doc = base_contract()
        doc["steps"][0]["controls"] = ["  "]
        self.assert_refused_step(doc)

    def test_an_empty_step_id_is_refused(self):
        doc = base_contract()
        doc["steps"][0]["step_id"] = ""
        self.assert_refused_step(doc)

    def test_an_empty_control_id_is_refused(self):
        doc = base_contract()
        doc["steps"][0]["controls"] = [""]
        self.assert_refused_step(doc)

    def test_a_whitespace_only_step_id_is_refused_through_the_cli(self):
        doc = base_contract()
        doc["steps"][0]["step_id"] = "   "
        path = self.tmp_path("blank-stepid.json", json.dumps(doc))
        code, out, err = self.run_cli("validate", "--contract", path)
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "refused")
        self.assertIsNone(payload.get("route"))

    def test_a_short_step_id_still_validates(self):
        # Inverse: the rule is "not blank", not "long". A one-character id is
        # legal and still routes, so the fix did not narrow what counts as an
        # identity.
        doc = controls_contract(steps=[
            {"step_id": "s", "generation": 1, "controls": ["a"], "free_text": "accept"},
        ])
        self.assertEqual(owner.validate_contract(doc), [])
        verdict = owner.resolve_event(
            doc, {"kind": "control", "step_id": "s", "control_id": "a", "generation": 1})
        self.assertEqual(verdict["status"], "accepted")

    def test_the_routed_identity_is_the_owner_kind_not_the_responder_label(self):
        # The responder `id` is a label: `_owner_record` builds the route from
        # the owner kind, so a blank label can never become a routing key. The
        # identities an event can echo -- step_id and control_id -- are the ones
        # the contract refuses when blank.
        doc = controls_contract(
            owner={"kind": "openclaw_inbound"},
            responders=[{"id": "  ", "kind": "openclaw_inbound"}],
        )
        self.assertEqual(owner.validate_contract(doc), [])
        verdict = owner.resolve_event(
            doc,
            {"kind": "control", "step_id": "pick_time", "control_id": "tue_10am",
             "generation": 3},
        )
        self.assertEqual(verdict["route"]["id"], owner.OWNER_OPENCLAW)


class FreeTextGenerationTests(unittest.TestCase):
    """PBB-261 M1: the generation is a tap rule, not a typed-message rule.

    Contract §3 gives ``generation`` to the step re-render and §4 routes free
    text on the step's policy alone, but ``resolve_event`` checked the
    generation before branching, so a typed message was answered ``STALE_TAP``
    and a ``reject`` step with a stale generation said ``STALE_TAP`` instead of
    the ``FREE_TEXT_REJECTED`` §4 promises.
    """

    def test_free_text_routes_on_a_stale_generation(self):
        verdict = owner.resolve_event(
            base_contract(), {"kind": "free_text", "step_id": "pick_time", "generation": 2})
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["code"], owner.ROUTED)
        self.assertEqual(verdict["input"], "free_text")

    def test_free_text_routes_on_a_future_generation(self):
        verdict = owner.resolve_event(
            base_contract(), {"kind": "free_text", "step_id": "pick_time", "generation": 99})
        self.assertEqual(verdict["status"], "accepted")

    def test_free_text_routes_with_no_generation_at_all(self):
        verdict = owner.resolve_event(
            base_contract(), {"kind": "free_text", "step_id": "pick_time"})
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["input"], "free_text")

    def test_rejected_free_text_says_free_text_rejected_on_a_stale_generation(self):
        verdict = owner.resolve_event(
            base_contract(), {"kind": "free_text", "step_id": "confirm", "generation": 2})
        self.assertEqual(verdict["code"], owner.FREE_TEXT_REJECTED)
        self.assertIsNone(verdict["route"])

    def test_rejected_free_text_says_free_text_rejected_on_a_future_generation(self):
        verdict = owner.resolve_event(
            base_contract(), {"kind": "free_text", "step_id": "confirm", "generation": 9})
        self.assertEqual(verdict["code"], owner.FREE_TEXT_REJECTED)

    def test_a_tap_still_needs_the_current_generation(self):
        # Inverse: dropping the generation from the free-text path did not drop
        # it from the tap path. STALE_TAP is still derived for a control.
        for generation in (2, 4):
            verdict = owner.resolve_event(base_contract(), {
                "kind": "control", "step_id": "pick_time", "control_id": "tue_10am",
                "generation": generation})
            self.assertEqual(verdict["code"], owner.STALE_TAP, generation)
            self.assertIsNone(verdict["route"])

    def test_an_unknown_control_answers_unknown_control_whatever_it_carries(self):
        # The class behind "a long inline event is parsed and judged": the
        # control identity is the routing fact, so a tap naming a control the
        # step never rendered is UNKNOWN_CONTROL even when its generation is
        # missing or wrong.
        for event in (
            {"kind": "control", "step_id": "pick_time", "control_id": "x" * 900},
            {"kind": "control", "step_id": "pick_time", "control_id": "zzz",
             "generation": 3},
            {"kind": "control", "step_id": "pick_time", "control_id": "zzz",
             "generation": "3"},
        ):
            with self.subTest(control=event["control_id"][:12]):
                verdict = owner.resolve_event(base_contract(), event)
                self.assertEqual(verdict["code"], owner.UNKNOWN_CONTROL)
                self.assertIsNone(verdict["route"])

    def test_a_known_control_with_no_generation_is_still_malformed(self):
        verdict = owner.resolve_event(base_contract(), {
            "kind": "control", "step_id": "pick_time", "control_id": "tue_10am"})
        self.assertEqual(verdict["code"], owner.MALFORMED_EVENT)


class DepthLimitTests(unittest.TestCase):
    """PBB-261 M2: contract §7's exit 2 for over-deep input now exists.

    3 000-deep and 100 000-deep JSON used to parse and return a verdict, so
    "input nested deeper than the checker can walk" documented a failure mode
    the tool did not have.
    """

    setUp = CliTests.setUp
    tearDown = CliTests.tearDown
    run_cli = CliTests.run_cli

    def tmp_path(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def assert_usage(self, argv):
        code, out, err = self.run_cli(*argv)
        self.assertNotIn("Traceback", err)
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(out.strip(), "")
        self.assertIn("usage:", err)

    def test_a_deep_event_is_a_usage_exit(self):
        for depth in (200, 3000):
            with self.subTest(depth=depth):
                self.assert_usage(("resolve", "--contract", fixture("valid.json"),
                                   "--event", "[" * depth + "]" * depth))

    def test_a_deep_contract_is_a_usage_exit(self):
        for depth in (200, 3000):
            with self.subTest(depth=depth):
                path = self.tmp_path("deep-%d.json" % depth,
                                     '{"a":' * depth + "1" + "}" * depth)
                self.assert_usage(("validate", "--contract", path))

    def test_a_contract_at_the_depth_a_real_one_uses_still_validates(self):
        # Inverse: the limit is far above any real contract (four or five
        # levels), so the guard never fires on a document a caller can write.
        code, out, _ = self.run_cli("validate", "--contract", fixture("valid.json"))
        self.assertEqual(code, 0)
        self.assertEqual(owner.DEPTH_LIMIT, 64)


class BookkeepingTests(unittest.TestCase):
    """PBB-261 D1/D2: the shipped version is above main's, and unique.

    The marker is compared remote-against-local by ``check-updates.sh``, so a
    version at or below main's reads as "not newer" on every deployed box; and a
    CHANGELOG number already published on ``main`` for another task makes one
    number name two changes. These tests read the named main below, so they fail
    on the regression and pass on the fix.

    Scoped to branches that change ``38-conversational-ai-system``. A branch
    that touches nothing here ships main's own marker and CHANGELOG, so judging
    them as "this change" reddened unrelated work -- the BUILD stall. Within
    that scope only a branch that actually ships a version is judged: a branch
    that changes skill-38 code without moving ``skill-version.txt`` or
    ``CHANGELOG.md`` has no shipped version to check. Everything else is
    skipped, and the duplicate-version bite is untouched where it applies.

    Skipped when the checkout cannot resolve the pinned main; on the reviewed
    bytes (which regress the marker to v2.0.31) every one of them fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.git_ok = False
        try:
            probe = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify",
                 MAIN_PIN_SHA + "^{commit}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except OSError:
            return
        cls.git_ok = probe.returncode == 0

    def setUp(self):
        if not self.git_ok:
            self.skipTest("the pinned main %s is not in this checkout"
                          % MAIN_PIN_SHA)
        if not self.touches_skill_38():
            self.skipTest("this branch does not change %s" % SKILL_38_PATH)
        if not self.ships_a_version():
            self.skipTest("this branch changes %s without shipping a version"
                          % SKILL_38_PATH)

    def changed_paths(self):
        """Paths this branch itself changed, or None when git cannot say.

        Three-dot against the pinned main: the branch's own divergence, with
        everything it merged from main excluded -- so merging main never counts
        as this branch's change, while bumping the marker does.
        """
        done = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--name-only",
             "%s...HEAD" % MAIN_PIN_SHA],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if done.returncode != 0:
            return None
        return [line.strip() for line in done.stdout.splitlines() if line.strip()]

    def touches_skill_38(self):
        paths = self.changed_paths()
        if paths is None:
            return True          # cannot tell -> leave the gate armed
        return any(p.startswith(SKILL_38_PATH + "/") for p in paths)

    def ships_a_version(self):
        """The two files that carry a shipped version, and only those."""
        paths = self.changed_paths()
        if paths is None:
            return True          # cannot tell -> leave the gate armed
        return any(p in (SKILL_38_PATH + "/skill-version.txt",
                         SKILL_38_PATH + "/CHANGELOG.md") for p in paths)

    def git(self, *argv):
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + list(argv),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

    def main_marker(self):
        return self.git("show", MAIN_PIN_SHA + ":38-conversational-ai-system/"
                                "skill-version.txt").stdout.strip()

    def local_marker(self):
        return (SKILL_ROOT / "skill-version.txt").read_text(encoding="utf-8").strip()

    def changelog_versions(self):
        text = (SKILL_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        return [tuple(int(p) for p in m.split("."))
                for m in re.findall(r"^## \[?v?(\d+\.\d+\.\d+)\]?", text, re.M)]

    def owned_changelog_versions(self):
        """The CHANGELOG headings this change adds (owner decision #237).

        The window used to be ``changelog_versions()[:4]`` -- the file's top
        four headings. After any faithful merge of ``origin/main`` those are
        main's own numbers, and the tests then asserted that main's numbers are
        absent from main. This reads the headings the change itself adds since
        the merge base, so a number this change adds that main already uses
        still appears and the duplicate rule still bites.
        """
        if not self.git_ok:
            return self.changelog_versions()
        out = self.git("diff", "--unified=0", "origin/main...HEAD", "--",
                       "38-conversational-ai-system/CHANGELOG.md").stdout
        added = "\n".join(line[1:] for line in out.splitlines()
                          if line.startswith("+")
                          and not line.startswith("+++"))
        return [tuple(int(p) for p in m.split("."))
                for m in re.findall(r"^## \[?v?(\d+\.\d+\.\d+)\]?", added, re.M)]

    def test_the_shipped_version_is_strictly_above_main_s(self):
        if not self.git_ok:
            self.skipTest("the pinned main is not in this checkout")
        local = tuple(int(p) for p in self.local_marker().lstrip("v").split("."))
        main = tuple(int(p) for p in self.main_marker().lstrip("v").split("."))
        self.assertGreater(local, main,
                           "the shipped version must never be at or below main's")

    def test_no_version_this_branch_ships_appears_on_main(self):
        if not self.git_ok:
            self.skipTest("no origin/main in this checkout to compare against")
        main_headers = {"%d.%d.%d" % v for v in self.main_changelog_versions()}
        shipped = {self.local_marker().lstrip("v")}
        shipped.update("%d.%d.%d" % v for v in self.owned_changelog_versions())
        for version in sorted(shipped):
            with self.subTest(version=version):
                # Compare headings, not a whole-file fixed-string scan: a
                # version named only in prose is not a published entry.
                self.assertNotIn(version, main_headers,
                                 "%s is already on origin/main" % version)

    def main_changelog_versions(self):
        text = self.git("show", MAIN_PIN_SHA + ":38-conversational-ai-system/"
                                "CHANGELOG.md").stdout
        return [tuple(int(p) for p in m.split("."))
                for m in re.findall(r"^## \[?v?(\d+\.\d+\.\d+)\]?", text, re.M)]

    def test_the_changelog_is_strictly_monotonic_where_this_change_speaks(self):
        # Newest-first, and the entries this change adds must each be distinct
        # and above main's newest. Below main's newest the file is main's own
        # legacy history -- it already carries one deliberate reversal (1.0.0
        # then a v2.0.0 generation roll) -- and rewriting it is not this task's.
        versions = self.owned_changelog_versions()
        self.assertTrue(versions,
                        "this change adds no CHANGELOG entry of its own to check")
        for earlier, later in zip(versions, versions[1:]):
            self.assertGreater(earlier, later,
                               "the entries this change adds must be newest-first "
                               "and distinct: %s" % (versions,))
        if not self.git_ok:
            self.skipTest("no origin/main in this checkout to compare against")
        main_top = max(self.main_changelog_versions())
        self.assertGreater(versions[0], main_top,
                           "the newest entry must sit above main's newest")
        owned = [v for v in versions if v >= main_top]
        for earlier, later in zip(owned, owned[1:]):
            self.assertGreater(earlier, later,
                               "the entries this change adds must be newest-first "
                               "and distinct: %s" % (owned,))
        if not owned:
            return
        if not self.git_ok:
            self.skipTest("the pinned main is not in this checkout")
        main_top = max(self.main_changelog_versions())
        self.assertGreater(owned[0], main_top,
                           "the newest entry must sit above main's newest")

    def test_no_version_names_two_different_changes(self):
        # D2 in its own words: "the same number now names three different
        # changes". The rule is pinned against what this change adds: every
        # number it adds is distinct and none may already name an entry on
        # main.
        owned = self.owned_changelog_versions()
        self.assertEqual(len(set(owned)), len(owned),
                         "the entries this change adds must not share a "
                         "version: %s" % (owned,))
        if not self.git_ok:
            self.skipTest("the pinned main is not in this checkout")
        main_headers = set(self.main_changelog_versions())
        for version in owned:
            self.assertNotIn(version, main_headers,
                             "%s already names an entry on origin/main"
                             % (version,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
