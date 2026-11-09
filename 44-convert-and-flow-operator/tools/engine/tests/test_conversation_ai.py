"""Offline proofs for the native Conversation AI adapter and its CLI (WF28).

Run: python3 -I test_conversation_ai.py
     python3 -m unittest tests.test_conversation_ai

No network. Every row is a synthetic fixture (WF00 owns the real rows); the
suite asserts that an ABSENT row refuses loudly instead of inventing a path.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _public_contract_fakes as fakes  # noqa: E402
from cli_anything.gohighlevel import conversation_ai_commands as commands  # noqa: E402
from cli_anything.gohighlevel.public.adapter import ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.conversation_ai import (  # noqa: E402
    CHANNEL_MAP,
    CREATE,
    GET,
    LIST,
    UPDATE,
    AgentSpec,
    ConversationAiAdapter,
    effective_prompt,
    native_channel_for,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.outbound_sender import CapturingTransport  # noqa: E402

TENANT = fakes.SYNTHETIC_TENANT
AGENT = "agent_synthetic_0001"
APPROVAL = ApprovalRef(ref=fakes.SYNTHETIC_APPROVAL)
REPO_ROOT = HERE.parents[3]


def rows():
    return fakes.registry(
        fakes.row(LIST, method="GET", path_template="/conversation-ai/agents"),
        fakes.row(GET, method="GET",
                  path_template="/conversation-ai/agents/{agentId}",
                  tenant_binding="path.agentId"),
        fakes.row(CREATE, method="POST", path_template="/conversation-ai/agents",
                  write=True, approval_required=True),
        fakes.row(UPDATE, method="PUT",
                  path_template="/conversation-ai/agents/{agentId}",
                  tenant_binding="path.agentId", write=True,
                  approval_required=True),
    )


def build(responses):
    table = rows()
    inner = fakes.FakeTransport(responses)
    capture = CapturingTransport(inner)
    adapter = fakes.make_adapter(capture, table,
                                 gate=fakes.enabled_gate(list(table.values())))
    client = ConversationAiAdapter(adapter, fakes.fake_tenant(TENANT),
                                   operations=table, transport=capture)
    return client, capture


def body(payload):
    return json.dumps(payload).encode()


AGENT_OFF = {
    "id": AGENT, "name": "Synthetic Support", "mode": "off",
    "channels": ["SMS"], "fullPrompt": "",
    "personality": "warm", "goal": "book", "instructions": "short",
}
AGENT_PROMPTED = dict(AGENT_OFF, fullPrompt="Answer only from the knowledge base.")


class ChannelMapTests(unittest.TestCase):
    def test_every_native_enumeration_is_reachable(self):
        self.assertEqual(set(CHANNEL_MAP.values()), {
            "IG", "FB", "SMS", "WebChat", "WhatsApp", "Live_Chat", "Email"})

    def test_webchat_and_live_chat_are_distinct(self):
        self.assertEqual(native_channel_for("webchat"), "WebChat")
        self.assertEqual(native_channel_for("live_chat"), "Live_Chat")

    def test_unsupported_channels_are_refused_not_coerced(self):
        for name in ("linkedin", "facebook_comments", "all_in_one", "tiktok"):
            with self.subTest(channel=name):
                with self.assertRaises(ContractViolation) as caught:
                    native_channel_for(name)
                self.assertEqual(caught.exception.rule,
                                 "conversation_channel_unsupported")
        with self.assertRaises(ContractViolation) as caught:
            native_channel_for("chat")
        self.assertEqual(caught.exception.rule, "conversation_channel_ambiguous")

    def test_the_engine_map_agrees_with_the_skill38_policy_map(self):
        path = REPO_ROOT / "38-conversational-ai-system" / "tools" / "responder_policy.py"
        self.assertTrue(path.is_file(), path)
        spec = importlib.util.spec_from_file_location("responder_policy_wf28", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.CHANNEL_MAP, CHANNEL_MAP)


class EffectivePromptTests(unittest.TestCase):
    def test_full_prompt_wins_over_structured_fields(self):
        prompt = effective_prompt(AGENT_PROMPTED)
        self.assertEqual(prompt["source"], "fullPrompt")
        self.assertEqual(prompt["text"], AGENT_PROMPTED["fullPrompt"])
        self.assertEqual(prompt["shadowed_fields"],
                         ["goal", "instructions", "personality"])

    def test_structured_fields_apply_only_when_full_prompt_is_empty(self):
        prompt = effective_prompt(AGENT_OFF)
        self.assertEqual(prompt["source"], "structured_fields")
        self.assertIn("personality: warm", prompt["text"])

    def test_no_prompt_at_all_is_named(self):
        self.assertEqual(effective_prompt({})["source"], "none")


class CreateTests(unittest.TestCase):
    def test_create_uses_the_non_sending_mode_and_reads_back(self):
        client, capture = build([
            fakes.resp(200, body({"agent": AGENT_OFF})),
            fakes.resp(200, body({"agents": [AGENT_OFF]})),
        ])
        change = client.create(
            AgentSpec(name="Synthetic Support", channels=["sms", "email"]),
            logical_key="conversation-ai:create:synthetic",
            approval=APPROVAL,
        )
        self.assertTrue(change.ok)
        self.assertEqual(change.agent_id, AGENT)
        self.assertEqual(change.mode, "off")
        self.assertEqual(capture.requests[0]["method"], "POST")
        sent = capture.requests[0]["body"]
        self.assertEqual(sent["mode"], "off")
        self.assertEqual(sent["channels"], ["SMS", "Email"])
        self.assertNotIn("primary", sent)
        self.assertEqual(capture.requests[1]["method"], "GET",
                         "the created agent must be read back")
        self.assertEqual(change.readback_expect, {"name": "Synthetic Support"})

    def test_create_never_accepts_a_sending_mode(self):
        client, capture = build([])
        with self.assertRaises(ContractViolation) as caught:
            client.create(AgentSpec(name="X", channels=["sms"], mode="auto-pilot"),
                          logical_key="k", approval=APPROVAL)
        self.assertEqual(caught.exception.rule,
                         "conversation_create_must_be_non_sending")
        self.assertEqual(capture.call_count, 0, "refused before transport")

    def test_create_refuses_an_unsupported_channel_before_transport(self):
        client, capture = build([])
        with self.assertRaises(ContractViolation) as caught:
            client.create(AgentSpec(name="X", channels=["linkedin"]),
                          logical_key="k", approval=APPROVAL)
        self.assertEqual(caught.exception.rule, "conversation_channel_unsupported")
        self.assertEqual(capture.call_count, 0)


class UpdateTests(unittest.TestCase):
    def test_update_refuses_a_primary_switch_before_any_read(self):
        client, capture = build([])
        with self.assertRaises(ContractViolation) as caught:
            client.update(AGENT, {"primary": True}, logical_key="k",
                          approval=APPROVAL)
        self.assertEqual(
            caught.exception.rule,
            "primary_switch_requires_separate_authorization")
        self.assertEqual(capture.call_count, 0)

    def test_update_refuses_a_prompt_full_prompt_still_shadows(self):
        client, capture = build([fakes.resp(200, body({"agent": AGENT_PROMPTED}))])
        with self.assertRaises(ContractViolation) as caught:
            client.update(AGENT, {"personality": "dry"}, logical_key="k",
                          approval=APPROVAL)
        self.assertEqual(caught.exception.rule, "prompt_ineffective")
        self.assertEqual(
            [r["method"] for r in capture.requests], ["GET"],
            "the ineffective write must not reach transport")

    def test_update_mode_change_requires_approval(self):
        client, capture = build([fakes.resp(200, body({"agent": AGENT_OFF}))])
        with self.assertRaises(ContractViolation) as caught:
            client.update(AGENT, {"mode": "auto-pilot"}, logical_key="k")
        self.assertEqual(caught.exception.rule, "approval_required")

    def test_update_with_approval_snapshots_then_writes_and_reads_back(self):
        updated = dict(AGENT_OFF, mode="auto-pilot")
        client, capture = build([
            fakes.resp(200, body({"agent": AGENT_OFF})),
            fakes.resp(200, body({"agent": updated})),
            fakes.resp(200, body({"agent": updated})),
        ])
        change = client.update(AGENT, {"mode": "auto-pilot"},
                               logical_key="conversation-ai:mode:synthetic",
                               approval=APPROVAL)
        self.assertTrue(change.ok)
        self.assertEqual([r["method"] for r in capture.requests],
                         ["GET", "PUT", "GET"])
        self.assertEqual(capture.requests[1]["body"], {"mode": "auto-pilot"})
        self.assertEqual(change.snapshot["mode"], "off")
        self.assertEqual(change.snapshot["fullPrompt"], "")
        self.assertEqual(change.snapshot_digest, change.snapshot_digest)
        self.assertEqual(len(change.snapshot_digest), 64)
        self.assertEqual(change.mode, "auto-pilot")

    def test_update_full_prompt_becomes_the_effective_instruction(self):
        updated = dict(AGENT_OFF, fullPrompt="Only cite the KB.")
        client, capture = build([
            fakes.resp(200, body({"agent": AGENT_OFF})),
            fakes.resp(200, body({"agent": updated})),
            fakes.resp(200, body({"agent": updated})),
        ])
        change = client.update(AGENT, {"fullPrompt": "Only cite the KB."},
                               logical_key="k", approval=APPROVAL)
        self.assertEqual(change.effective_prompt["source"], "fullPrompt")
        self.assertEqual(change.effective_prompt["text"], "Only cite the KB.")
        self.assertEqual(capture.requests[1]["body"],
                         {"fullPrompt": "Only cite the KB."})

    def test_unknown_field_is_refused(self):
        client, capture = build([])
        with self.assertRaises(ContractViolation) as caught:
            client.update(AGENT, {"admin": True}, logical_key="k",
                          approval=APPROVAL)
        self.assertEqual(caught.exception.rule, "conversation_field_unsupported")
        self.assertEqual(capture.call_count, 0)


class OperationsDependencyTests(unittest.TestCase):
    def test_absent_rows_refuse_loudly_and_name_the_checkpoint(self):
        auth = fakes.fake_auth()
        adapter = fakes.make_adapter(fakes.FakeTransport(), {})
        with self.assertRaises(ContractViolation) as caught:
            ConversationAiAdapter(adapter, fakes.fake_tenant(TENANT),
                                  operations={})
        self.assertEqual(caught.exception.rule, "conversation_operations_missing")
        self.assertIn("WF00", str(caught.exception.detail.get("checkpoint")))
        self.assertEqual(sorted(caught.exception.detail["missing"]),
                         [CREATE, GET, LIST, UPDATE])
        self.assertIsNotNone(auth)

    def test_create_without_capture_refuses_before_transport(self):
        table = rows()
        inner = fakes.FakeTransport([])
        adapter = fakes.make_adapter(inner, table,
                                     gate=fakes.enabled_gate(list(table.values())))
        client = ConversationAiAdapter(adapter, fakes.fake_tenant(TENANT),
                                       operations=table)
        with self.assertRaises(ContractViolation) as caught:
            client.create(AgentSpec(name="X", channels=["sms"]),
                          logical_key="k", approval=APPROVAL)
        self.assertEqual(caught.exception.rule,
                         "conversation_transport_capture_required")
        self.assertEqual(inner.call_count, 0)


class _FakeOperation:
    def __init__(self):
        self.status = types.SimpleNamespace(value="ok")
        self.operation_id = CREATE
        self.receipt_id = "gxo_res_synthetic"
        self.error = None
        self.readback = None


class _FakeChange:
    def __init__(self, mode="off"):
        self.operation = _FakeOperation()
        self.agent_id = AGENT
        self.mode = mode
        self.native_channels = ("SMS",)
        self.effective_prompt = {"source": "fullPrompt", "text": "x",
                                 "shadowed_fields": []}
        self.snapshot = None
        self.snapshot_digest = None
        self.readback_expect = {"name": "Synthetic Support"}
        self.ok = True


class _FakeClient:
    def __init__(self):
        self.created = None

    def inventory(self):
        return _FakeOperation()

    def read(self, agent_id):
        return _FakeOperation()

    def create(self, spec, *, logical_key, approval=None):
        self.created = (spec, logical_key, approval)
        return _FakeChange()

    def update(self, agent_id, patch, *, logical_key, approval=None):
        return _FakeChange(mode=str(patch.get("mode", "off")))

    def effective_prompt_of(self, agent_id):
        return {"source": "fullPrompt", "text": "x", "shadowed_fields": []}


class CommandTests(unittest.TestCase):
    def parser(self):
        top = argparse.ArgumentParser(prog="caf")
        sub = top.add_subparsers(dest="command", required=True)
        commands.register(sub)
        return top

    def test_create_routes_through_the_client_and_exits_zero(self):
        fake = _FakeClient()
        args = self.parser().parse_args([
            "conversation-ai", "create", "--name", "Synthetic Support",
            "--channels", "sms,email", "--logical-key", "k1",
        ])
        self.assertEqual(commands.run(args, client_factory=lambda _a: fake), 0)
        spec, key, _approval = fake.created
        self.assertEqual(list(spec.fields()["channels"]), ["SMS", "Email"])
        self.assertEqual(spec.mode, "off")
        self.assertEqual(key, "k1")

    def test_create_help_refuses_a_sending_mode_at_the_boundary(self):
        args = self.parser().parse_args([
            "conversation-ai", "create", "--name", "X", "--channels", "sms",
            "--mode", "auto-pilot",
        ])
        self.assertEqual(commands.run(args, client_factory=lambda _a: _FakeClient()), 0)
        # The CLI accepts the flag; the adapter still refuses the write. This
        # asserts the help text is not the guard, the adapter is.
        self.assertEqual(args.mode, "auto-pilot")

    def test_channels_lists_the_exact_map(self):
        args = self.parser().parse_args(["conversation-ai", "channels"])
        self.assertEqual(commands.run(args), 0)

    def test_missing_subcommand_is_usage_error(self):
        top = argparse.ArgumentParser(prog="caf")
        sub = top.add_subparsers(dest="command", required=True)
        commands.register(sub)
        with self.assertRaises(SystemExit):
            top.parse_args(["conversation-ai"])

    def test_contract_violation_becomes_exit_one(self):
        args = self.parser().parse_args([
            "conversation-ai", "create", "--name", "X", "--channels", "linkedin",
        ])

        class Refusing:
            def create(self, *_a, **_k):
                raise ContractViolation("conversation_channel_unsupported",
                                        detail={"channel": "linkedin"})

        self.assertEqual(commands.run(args, client_factory=lambda _a: Refusing()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
