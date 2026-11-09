"""Regression proofs for cross-entry-point leases and terminal auth outcomes."""
from contextvars import copy_context
import asyncio
import fcntl
import importlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

import delivery
import evidence_lease
import host
from ghl_auth import AuthBridgeError
from skill6_playwright import Stop
import test_delivery as fixtures


class DirectProviderEvidenceTests(unittest.TestCase):
    def browser_probes(self):
        return {'lanes':{'agent_browser':{'available':True}},
            'api_capabilities':{'courses.update':{'location_id':'fixture',
                'observed_at':time.time(),'supported':False,'reason':'unsupported_endpoint'}}}

    def operations(self, root):
        api = fixtures.FakeTransport()
        dispatch, calendar_api, calendar_inputs, route = fixtures.CalendarProviderTests().context()
        return [
            ('course', lambda: delivery.run_course(fixtures.inputs(), root,
                capability=fixtures.capability(), transport=api), api),
            ('lesson_quiz', lambda: delivery.run_lesson_quiz(
                {'location_id':'fixture','product_id':'p','lesson_id':'l','quiz':fixtures.quiz()},
                root, capability=fixtures.capability(), transport=api), api),
            ('course_update', lambda: delivery.run_course_update(
                {'location_id':'fixture','product_id':'p','course_changes':{'title':'Update'}},
                root, capability=fixtures.capability(), transport=api), api),
            ('calendar', lambda: delivery.meeting_calendar_executor(
                operation='meetings.integrate', inputs=calendar_inputs, route=route,
                evidence_root=root, dispatcher=dispatch), calendar_api),
        ]

    def test_every_direct_provider_preserves_existing_cross_lane_journals(self):
        for journal in ('state.json','provider-state.json','community-portal-state.json',
                        'handoff.json','auth-stop.json','community-details-state.json'):
            for index in range(4):
                with self.subTest(journal=journal, operation=index), tempfile.TemporaryDirectory() as root:
                    path = Path(root, journal)
                    preserved = '{"status":"INTENT_RECORDED","location_id":"fixture"}'
                    path.write_text(preserved)
                    _, operation, api = self.operations(root)[index]
                    with self.assertRaises(Stop):
                        operation()
                    self.assertEqual(api.calls, [])
                    self.assertEqual(path.read_text(), preserved)
                    self.assertFalse(Path(root, 'delivery-state.json').exists())
                    self.assertFalse(Path(root, 'calendar-delivery-state.json').exists())

    def test_every_direct_provider_respects_active_editor_and_provider_locks(self):
        for lock in ('.runner.lock','provider.lock'):
            for index in range(4):
                with self.subTest(lock=lock, operation=index), tempfile.TemporaryDirectory() as root:
                    with open(Path(root, lock), 'a') as fd:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        _, operation, api = self.operations(root)[index]
                        with self.assertRaises(Stop):
                            operation()
                        self.assertEqual(api.calls, [])

    def test_course_and_calendar_journals_cannot_authorize_each_other(self):
        for index, journal in ((0,'calendar-delivery-state.json'),
                               (1,'calendar-delivery-state.json'),
                               (2,'calendar-delivery-state.json'),
                               (3,'delivery-state.json')):
            with self.subTest(operation=index), tempfile.TemporaryDirectory() as root:
                path = Path(root, journal); path.write_text('{preserve-uncertain')
                _, operation, api = self.operations(root)[index]
                with self.assertRaises(Stop):
                    operation()
                self.assertEqual(api.calls, [])
                self.assertEqual(path.read_text(), '{preserve-uncertain')

    def test_host_can_call_real_course_provider_under_its_owned_lease(self):
        data = {**fixtures.inputs(), 'api_capability':fixtures.capability()}
        probe = {'api_capabilities':{'courses.create':{
            'location_id':'fixture','observed_at':time.time(),'provider':'public_api',
            'version':'v3','scope_ok':True,'supported':True}}}
        api = fixtures.FakeTransport()
        callback = Mock(side_effect=lambda **kw: delivery.run_course(kw['inputs'],
            kw['evidence_root'], capability=kw['inputs']['api_capability'], transport=api))
        with tempfile.TemporaryDirectory() as root:
            result = host.run_recipe('courses.create',data,probe,root,
                input_dir='.',executors={'public_api':callback})
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            self.assertEqual(callback.call_count,1)
            self.assertTrue(any(c[0]=='POST' for c in api.calls))
            count = len(api.calls)
            result = host.run_recipe('courses.create',data,probe,root,
                input_dir='.',executors={'public_api':callback})
            self.assertEqual(result['status'],'ALREADY_EXECUTED')
            self.assertEqual(callback.call_count,1)
            self.assertEqual(len(api.calls),count)

    def test_direct_api_intent_blocks_fresh_browser_or_api_provider_callback(self):
        data = {'location_id':'fixture','location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/fixture/dashboard',
                'name':'Fixture course'}
        for journal in ('delivery-state.json','calendar-delivery-state.json'):
            for prior in (None,'{malformed',json.dumps({'status':'PROVIDER_INTENT_RECORDED'})):
                with self.subTest(journal=journal,prior=prior), tempfile.TemporaryDirectory() as root:
                    path = Path(root,journal); path.write_text('{uncertain-direct-intent')
                    if prior is not None:
                        Path(root,'provider-state.json').write_text(prior)
                    callback = Mock()
                    result = host.run_recipe('courses.update',data,
                        self.browser_probes(),root,
                        input_dir='.',executors={'agent_browser':callback})
                    self.assertEqual(result['status'],'PROVIDER_RECONCILIATION_REQUIRED')
                    callback.assert_not_called()
                    self.assertEqual(path.read_text(),'{uncertain-direct-intent')
                    if prior is not None:
                        self.assertEqual(Path(root,'provider-state.json').read_text(),prior)
                    else:
                        self.assertFalse(Path(root,'provider-state.json').exists())

    def test_provider_replay_admission_cannot_nest_a_new_direct_api_write(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'provider-state.json').write_text('{prior')
            Path(root,'delivery-state.json').write_text('{prior-direct')
            with evidence_lease.evidence_lease(root,'fixture',kind='provider_replay'):
                with self.assertRaises(Stop):
                    with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                        self.fail('Replay-only lease authorized a fresh write')

    def saved_provider_fixture(self, root, *, operation='courses.update'):
        data = {'location_id':'fixture','location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/fixture/dashboard',
                'name':'Fixture course'}
        if operation == 'courses.create':
            probe = {'api_capabilities':{operation:{'location_id':'fixture',
                'observed_at':time.time(),'provider':'public_api','version':'v3',
                'scope_ok':True,'supported':True}}}
            lane, kind, status = 'public_api', 'course', 'API_STEPS_COMPLETE'
        else:
            probe = self.browser_probes()
            lane, kind, status = 'agent_browser', 'course', 'EDITOR_STEPS_COMPLETE'
        callback = Mock(return_value={'status':status,'location_id':'fixture',
            'objects':[{'kind':kind,'id':'saved_id'}]})
        first = host.run_recipe(operation,data,probe,root,input_dir='.',executors={lane:callback})
        self.assertEqual(first['status'],status)
        callback.assert_called_once()
        callback.reset_mock()
        return data, probe, callback, lane

    def test_corrupted_completed_provider_journals_never_replay_or_call_provider(self):
        changes = [
            lambda p: [],
            lambda p: {**p,'operation':'pages.seo'},
            lambda p: {**p,'location_id':'other'},
            lambda p: {**p,'fingerprint':'wrong'},
            lambda p: {**p,'status':'UNRECOGNIZED'},
            lambda p: {**p,'outcome':None},
            lambda p: {**p,'outcome':{**p['outcome'],'location_id':'other'}},
            lambda p: {**p,'outcome':{**p['outcome'],'status':'UNRECOGNIZED'}},
            lambda p: {**p,'outcome':{**p['outcome'],'status':'API_STEPS_COMPLETE'}},
            lambda p: {**p,'outcome':{**p['outcome'],'verification_required':False}},
            lambda p: {**p,'outcome':{**p['outcome'],'objects':None}},
            lambda p: {**p,'outcome':{**p['outcome'],'objects':[{'kind':'form','id':'../unsafe'}]}},
            lambda p: {**p,'outcome':{**p['outcome'],'objects':[{'kind':'secret','id':'safe_id'}]}},
        ]
        for index, change in enumerate(changes):
            with self.subTest(corruption=index), tempfile.TemporaryDirectory() as root:
                data, probe, callback, lane = self.saved_provider_fixture(root)
                path = Path(root,'provider-state.json')
                damaged = json.dumps(change(json.loads(path.read_text())))
                path.write_text(damaged)
                result = host.run_recipe('courses.update',data,probe,root,
                    input_dir='.',executors={lane:callback})
                self.assertEqual(result['status'],'PROVIDER_RECONCILIATION_REQUIRED')
                callback.assert_not_called()
                self.assertEqual(path.read_text(),damaged)

    def test_completed_create_journal_cannot_lose_its_concrete_object_identity(self):
        with tempfile.TemporaryDirectory() as root:
            data, probe, callback, lane = self.saved_provider_fixture(root,operation='courses.create')
            path = Path(root,'provider-state.json')
            prior = json.loads(path.read_text());prior['outcome']['objects'] = []
            path.write_text(json.dumps(prior))
            result = host.run_recipe('courses.create',data,probe,root,
                input_dir='.',executors={lane:callback})
            self.assertEqual(result['status'],'PROVIDER_RECONCILIATION_REQUIRED')
            callback.assert_not_called()

    def test_replayed_provider_outcome_strips_arbitrary_private_payloads(self):
        with tempfile.TemporaryDirectory() as root:
            data, probe, callback, lane = self.saved_provider_fixture(root)
            path = Path(root,'provider-state.json')
            prior = json.loads(path.read_text())
            prior['private_root'] = 'PRIVATE_MUST_NOT_LEAK'
            prior['outcome']['private_response'] = 'PRIVATE_MUST_NOT_LEAK'
            prior['outcome']['objects'][0]['private_response'] = 'PRIVATE_MUST_NOT_LEAK'
            preserved = json.dumps(prior);path.write_text(preserved)
            result = host.run_recipe('courses.update',data,probe,root,
                input_dir='.',executors={lane:callback})
            self.assertEqual(result['status'],'ALREADY_EXECUTED')
            self.assertEqual(set(result['result']),{'status','location_id','objects','verification_required'})
            self.assertEqual(result['result']['objects'],[{'kind':'course','id':'saved_id'}])
            self.assertNotIn('PRIVATE_MUST_NOT_LEAK',json.dumps(result))
            self.assertEqual(path.read_text(),preserved)
            callback.assert_not_called()

    def test_replay_normalizes_saved_false_verification_flags_to_pending(self):
        flags = [{'behavior_verified':False},{'submission_verified':False},
                 {'payment_verified':False},{'functional_verified':False},
                 {'checkout_ready':False},{'independent_readback':'REQUIRED'},
                 {'behavior_verification':'REQUIRED'}]
        for flag in flags:
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                data, probe, callback, lane = self.saved_provider_fixture(root)
                path = Path(root,'provider-state.json')
                prior = json.loads(path.read_text());prior['outcome'].update(flag)
                preserved = json.dumps(prior);path.write_text(preserved)
                result = host.run_recipe('courses.update',data,probe,root,
                    input_dir='.',executors={lane:callback})
                self.assertEqual(result['status'],'NEEDS_VERIFICATION')
                self.assertEqual(result['result']['status'],'NEEDS_VERIFICATION')
                self.assertEqual(path.read_text(),preserved)
                callback.assert_not_called()

    def test_owned_lease_refuses_wrong_location_different_root_and_copied_thread(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            with evidence_lease.evidence_lease(root,'fixture',kind='provider'):
                for target, loc in ((root,'other'),(other,'fixture')):
                    with self.assertRaises(Stop):
                        with evidence_lease.evidence_lease(target,loc,kind='course'):
                            self.fail('Foreign nested owner accepted')
                errors = []
                context = copy_context()
                def worker():
                    try:
                        with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                            errors.append('unexpected success')
                    except Stop:
                        errors.append('refused')
                thread = threading.Thread(target=lambda:context.run(worker))
                thread.start(); thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,['refused'])

    def test_child_async_task_cannot_inherit_provider_ownership(self):
        async def scenario(root):
            async def child():
                with self.assertRaises(Stop):
                    with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                        self.fail('Child task inherited provider ownership')
            with evidence_lease.evidence_lease(root,'fixture',kind='provider'):
                # The same owning task can call its synchronous API provider.
                with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                    pass
                await asyncio.create_task(child())
        with tempfile.TemporaryDirectory() as root:
            asyncio.run(scenario(root))

    def test_copied_context_cannot_reuse_an_expired_provider_lease(self):
        with tempfile.TemporaryDirectory() as root:
            with evidence_lease.evidence_lease(root,'fixture',kind='provider'):
                captured = copy_context()
            def expired():
                with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                    self.fail('Expired nested owner accepted')
            with self.assertRaises(Stop):
                captured.run(expired)
            # Normal callers can still obtain a new independent lease.
            with evidence_lease.evidence_lease(root,'fixture',kind='course'):
                pass

    def test_details_writer_owns_only_its_own_journal(self):
        with tempfile.TemporaryDirectory() as root:
            own = Path(root,'community-details-state.json')
            own.write_text('{preserved-details')
            with evidence_lease.evidence_lease(root,'fixture',kind='community_details'):
                pass
            with self.assertRaises(Stop):
                with evidence_lease.evidence_lease(root,'fixture',kind='provider'):
                    self.fail('Foreign journal accepted')
            self.assertEqual(own.read_text(),'{preserved-details')

    def test_direct_and_package_import_share_one_ownership_context(self):
        packaged = importlib.import_module('playwright_recipes.evidence_lease')
        self.assertIs(packaged,evidence_lease)
        with tempfile.TemporaryDirectory() as root:
            with evidence_lease.evidence_lease(root,'fixture',kind='provider'):
                with packaged.evidence_lease(root,'fixture',kind='course'):
                    pass

    def test_browser_callback_identity_refusal_is_terminal_without_losing_intent(self):
        data = {'location_id':'fixture','location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/fixture/dashboard',
                'name':'Fixture course'}
        probe = self.browser_probes()
        callback = Mock(side_effect=AuthBridgeError('VALUE_MUST_NOT_BE_PERSISTED'))
        with tempfile.TemporaryDirectory() as root:
            result = host.run_recipe('courses.update',data,probe,root,
                input_dir='.',executors={'agent_browser':callback})
            self.assertEqual(result['status'],'STOP_AUTH')
            self.assertTrue(result['browser_used'])
            state = Path(root,'provider-state.json').read_text()
            self.assertEqual(json.loads(state)['status'],'PROVIDER_RECONCILIATION_REQUIRED')
            auth = Path(root,'auth-stop.json').read_text()
            self.assertNotIn('VALUE_MUST_NOT_BE_PERSISTED',state+auth+json.dumps(result))
            result = host.run_recipe('courses.update',data,probe,root,
                input_dir='.',executors={'agent_browser':callback})
            self.assertEqual(result['status'],'STOP_AUTH_CONTEXT')
            self.assertEqual(callback.call_count,1)
            self.assertEqual(Path(root,'provider-state.json').read_text(),state)


if __name__ == '__main__':
    unittest.main()
