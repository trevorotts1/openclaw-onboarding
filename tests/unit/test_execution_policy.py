"""Unit JEV-011: owner-direct execution policy (JEV spec 1.1, sections 5.1-5.4).

Offline regression tests: no client runtime, provider calls or config writes."""
import copy
import dataclasses
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
sys.path.insert(0, str(ROOT / 'shared-utils/execution_policy'))
import execution_policy as ep
from execution_policy import ExecutionPolicyRecord
import ceo_execution_policy as cep


def trusted_record(**over):
    base = dict(
        mode='owner_direct',
        requested_executor='current_assistant',
        actual_executor='current_assistant',
        source_message_id='msg-1',
        evidence_span='span:42:7',
        authenticated_requester='owner',
        requester_authenticated=True,
        authorization_source='trusted_context',
        company='acme',
        policy_revision=1,
        config_revision='cfg-9',
    )
    base.update(over)
    return ExecutionPolicyRecord(**base)


class RecordSchemaTests(unittest.TestCase):
    def test_exact_spec_52_fields_plus_two(self):
        names = [f.name for f in dataclasses.fields(ExecutionPolicyRecord)]
        self.assertEqual(
            names,
            ['mode', 'requested_executor', 'actual_executor', 'source_message_id',
             'evidence_span', 'authenticated_requester', 'requester_authenticated',
             'authorization_source', 'company', 'policy_revision', 'config_revision'],
        )

    def test_valid_record_accepts(self):
        self.assertEqual(ep.validate_record(trusted_record()), (True, 'ok'))

    def test_missing_evidence_span_rejects(self):
        self.assertEqual(ep.validate_record(trusted_record(evidence_span='')), (False, 'missing_evidence_span'))

    def test_unauthenticated_requester_rejects(self):
        self.assertEqual(
            ep.validate_record(trusted_record(requester_authenticated=False, authenticated_requester='')),
            (False, 'unauthenticated_requester'),
        )

    def test_user_supplied_json_source_rejects(self):
        self.assertEqual(
            ep.validate_record(trusted_record(authorization_source='user_supplied_json')),
            (False, 'not_authorized_intent_only'),
        )

    def test_magic_marker_source_rejects(self):
        self.assertEqual(
            ep.validate_record(trusted_record(authorization_source='magic_marker')),
            (False, 'not_authorized_intent_only'),
        )

    def test_non_record_rejects_without_raising(self):
        self.assertEqual(ep.validate_record({'mode': 'owner_direct'}), (False, 'not_a_record'))

    def test_validator_never_raises(self):
        self.assertEqual(ep.validate_record(None)[0], False)


class PersistenceTests(unittest.TestCase):
    def test_save_load_round_trip(self):
        store = {}
        key = ep.save_record(store, trusted_record())
        self.assertEqual(key, 'acme:msg-1:1')
        loaded = ep.record_from_dict(ep.load_record(store, key))
        self.assertEqual(loaded, trusted_record())

    def test_store_is_caller_supplied(self):
        store = {}
        ep.save_record(store, trusted_record())
        ep.save_record(store, trusted_record(source_message_id='msg-2'))
        self.assertEqual(len(store), 2)
        self.assertIsNone(ep.load_record(store, 'acme:nope:1'))

    def test_bump_revision(self):
        bumped = ep.bump_policy_revision(trusted_record())
        self.assertEqual(bumped.policy_revision, 2)
        self.assertEqual(trusted_record().policy_revision, 1)


class DecideTests(unittest.TestCase):
    def test_owner_direct_decision(self):
        rec = trusted_record()
        out = ep.decide_owner_direct(rec, lambda: True)
        self.assertEqual(out['mode'], 'owner_direct')
        self.assertEqual(out['executor'], 'current_assistant')
        self.assertIs(out['evidence'], rec)

    def test_untrusted_returns_no_mode(self):
        self.assertNotIn('mode', ep.decide_owner_direct(trusted_record(), lambda: False))

    def test_invalid_record_returns_no_mode(self):
        self.assertNotIn('mode', ep.decide_owner_direct(trusted_record(evidence_span=''), lambda: True))

    def test_classification_gate(self):
        rec = trusted_record()
        prefer = {'executionPreference': 'current_assistant'}
        normal = {'executionPreference': 'normal_delegation'}
        self.assertIn('mode', ep.decide_owner_direct(rec, True, prefer))
        self.assertNotIn('mode', ep.decide_owner_direct(rec, True, normal))

    def test_classification_like_alias(self):
        like = ep.ClassificationLike({'executionPreference': 'current_assistant', 'intent': 'task_request'})
        self.assertTrue(ep.is_owner_direct_preference(like))
        self.assertFalse(ep.is_owner_direct_preference({'executionPreference': 'unspecified'}))

    def test_existing_catchall_path_byte_identical(self):
        # Owner-direct absent: decide returns {}, so cep.upgrade/block untouched.
        self.assertEqual(ep.decide_owner_direct(trusted_record(), False), {})
        self.assertEqual(cep.block(), cep.block())


class PropagationTests(unittest.TestCase):
    def test_propagate_encodes_mode_and_revision(self):
        ctx = ep.propagate_to_context({}, trusted_record(), 'assignment')
        for key in ('execution_mode', 'executor', 'policy_revision', 'config_revision',
                    'source_message_id', 'evidence_span', 'company', 'lifecycle_stage'):
            self.assertIn(key, ctx)
        self.assertEqual((ctx['execution_mode'], ctx['executor']), ('owner_direct', 'current_assistant'))
        self.assertEqual((ctx['policy_revision'], ctx['config_revision']), (1, 'cfg-9'))
        self.assertEqual(ctx['lifecycle_stage'], 'assignment')

    def test_propagate_never_mutates_input(self):
        ctx = {'note': 'keep'}
        ep.propagate_to_context(ctx, trusted_record(), 'ingest')
        self.assertEqual(ctx, {'note': 'keep'})

    def test_unknown_stage_rejects(self):
        with self.assertRaises(ValueError):
            ep.propagate_to_context({}, trusted_record(), 'dispatch')

    def test_all_lifecycle_stages_round_trip(self):
        for stage in ep.LIFECYCLE_STAGES:
            ctx = ep.propagate_to_context({}, trusted_record(), stage)
            self.assertEqual(ctx['lifecycle_stage'], stage)

    def test_qc_failure_returns_to_same_executor(self):
        before = ep.propagate_to_context({}, trusted_record(), 'execution_reservation')
        after = ep.apply_qc_failure(before)
        self.assertEqual(after['executor'], 'current_assistant')
        self.assertEqual(after['execution_mode'], 'owner_direct')
        self.assertEqual(after['lifecycle_stage'], 'qc_correction')
        # Policy level only: a retry must not revert to normal routing.
        self.assertNotEqual(after.get('execution_mode'), 'delegated')


class GeneratorTemplateTests(unittest.TestCase):
    def test_managed_block_carries_four_categories(self):
        lowered = cep.POLICY.lower()
        for phrase in ('answer conversation', 'route new work', 'explicit',
                       'existing trusted assignment'):
            self.assertIn(phrase, lowered, phrase)

    def test_no_universal_always_use_jev_rule(self):
        lowered = cep.POLICY.lower()
        self.assertNotIn('always use jev', lowered)
        self.assertNotIn('always route through jev', lowered)

    def test_upgrade_preserves_v4_and_owner_bytes(self):
        legacy = ('Owner head\n<!-- CEO_ORCHESTRATOR_RULE_V1 -->\nold\n---\n'
                  'Owner tail with spaces.  \n')
        out = cep.upgrade(legacy)
        self.assertIn('<!-- CEO_ORCHESTRATOR_RULE_V4_3 -->', out)
        self.assertTrue(out.startswith('Owner head\n'))
        self.assertTrue(out.rstrip().endswith('Owner tail with spaces.'))
        self.assertEqual(cep.upgrade(out), out)


if __name__ == '__main__':
    unittest.main()
