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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
SKILL_ROOT = TOOLS_DIR.parent
REPO_ROOT = SKILL_ROOT.parent
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
