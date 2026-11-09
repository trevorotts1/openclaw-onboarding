"""All public delivery fronts refuse unsafe journals and return minimal replays."""
from copy import deepcopy
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock

import delivery
import host
from receipt_validation import CREATE_ROOTS
from skill6_playwright import Stop
import test_delivery as fixtures


class DeliveryReplayTests(unittest.TestCase):
    def operation(self, root, index):
        api = fixtures.FakeTransport()
        if index == 0:
            return ('courses.create','delivery-state.json',api,
                lambda:delivery.run_course(fixtures.inputs(),root,
                    capability=fixtures.capability(),transport=api))
        if index == 1:
            class ExistingLesson(fixtures.FakeTransport):
                def request(self,method,path,**kw):
                    if method == 'GET' and path in ('/courses/products/p','/courses/products/p/lessons/l'):
                        self.calls.append((method,path,kw['location_id'],None,None))
                        return {'id':path.rsplit('/',1)[-1]}
                    if method == 'GET' and path.endswith('/quiz') and path not in self.objects:
                        self.calls.append((method,path,kw['location_id'],None,None))
                        raise delivery.DeliveryApiError(404)
                    return super().request(method,path,**kw)
            api = ExistingLesson()
            data = {'location_id':'fixture','product_id':'p','lesson_id':'l','quiz':fixtures.quiz()}
            return ('courses.lesson_quiz.create','delivery-state.json',api,
                lambda:delivery.run_lesson_quiz(data,root,
                    capability=fixtures.capability(),transport=api))
        if index == 2:
            api.objects['/courses/products/p'] = {'id':'p','title':'Old'}
            data = {'location_id':'fixture','product_id':'p','course_changes':{'title':'Update'}}
            return ('courses.update','delivery-state.json',api,
                lambda:delivery.run_course_update(data,root,
                    capability=fixtures.capability(),transport=api))
        dispatcher, api, data, route = fixtures.CalendarProviderTests().context()
        return ('meetings.integrate','calendar-delivery-state.json',api,
            lambda:delivery.meeting_calendar_executor(operation='meetings.integrate',inputs=data,
                route=route,evidence_root=root,dispatcher=dispatcher))

    def test_all_direct_replays_are_bound_and_reject_corruption_without_network(self):
        changes = [
            lambda p: [],
            lambda p: {**p,'operation':'wrong.operation'},
            lambda p: {**p,'location_id':'foreign'},
            lambda p: {**p,'fingerprint':'wrong'},
            lambda p: {**p,'status':'UNKNOWN'},
            lambda p: {**p,'current_step_status':'INTENT_RECORDED'},
            lambda p: {**p,'objects':None},
            lambda p: {**p,'objects':[]},
            lambda p: {**p,'objects':[{'kind':'secret','id':'safe_id'}]},
            lambda p: {**p,'objects':[{**p['objects'][0],'id':'../unsafe'},*p['objects'][1:]]},
            lambda p: {**p,'objects':[{**p['objects'][0],'id':p['objects'][0]['id']},p['objects'][0],*p['objects'][1:]]},
        ]
        for index in range(4):
            for mutation, change in enumerate(changes):
                with self.subTest(operation=index,mutation=mutation), tempfile.TemporaryDirectory() as root:
                    _, journal, api, execute = self.operation(root,index)
                    self.assertEqual(execute()['status'],'API_STEPS_COMPLETE')
                    path = Path(root,journal)
                    damaged = json.dumps(change(json.loads(path.read_text())))
                    path.write_text(damaged);api.calls.clear()
                    with self.assertRaises(Stop):
                        execute()
                    self.assertEqual(api.calls,[])
                    self.assertEqual(path.read_text(),damaged)

    def test_direct_replays_strip_saved_responses_and_keep_legacy_valid_journals(self):
        for index in range(4):
            with self.subTest(operation=index), tempfile.TemporaryDirectory() as root:
                operation, journal, api, execute = self.operation(root,index)
                execute();path = Path(root,journal);old = json.loads(path.read_text())
                old.pop('operation')  # Pre-fix journals still require the exact plan proof.
                old['private_response'] = 'PRIVATE_NOT_FOR_OUTPUT'
                old['integration'] = {'private_invite':'PRIVATE_NOT_FOR_OUTPUT'}
                old['objects'][0]['private_response'] = 'PRIVATE_NOT_FOR_OUTPUT'
                preserved = json.dumps(old);path.write_text(preserved);api.calls.clear()
                result = execute()
                self.assertEqual(result['status'],'ALREADY_EXECUTED')
                self.assertEqual(result['operation'],operation)
                self.assertTrue(result['verification_required'])
                self.assertNotIn('PRIVATE_NOT_FOR_OUTPUT',json.dumps(result))
                self.assertEqual(path.read_text(),preserved)
                self.assertEqual(api.calls,[])

    def test_direct_replays_keep_explicit_unverified_behavior_pending(self):
        flags = [{'behavior_verified':False},{'submission_verified':False},
                 {'payment_verified':False},{'functional_verified':False},
                 {'checkout_ready':False},{'independent_readback':'REQUIRED'},
                 {'behavior_verification':'REQUIRED'}]
        for index in range(4):
            for flag in flags:
                with self.subTest(operation=index,flag=flag), tempfile.TemporaryDirectory() as root:
                    _, journal, api, execute = self.operation(root,index)
                    execute();path = Path(root,journal);old = json.loads(path.read_text())
                    old.update(flag);preserved = json.dumps(old);path.write_text(preserved)
                    api.calls.clear();result = execute()
                    self.assertEqual(result['status'],'NEEDS_VERIFICATION')
                    self.assertTrue(result['verification_required'])
                    self.assertEqual(path.read_text(),preserved)
                    self.assertEqual(api.calls,[])

    def test_direct_known_target_ids_and_full_outline_must_survive_replay(self):
        for index in (0,2,3):
            with self.subTest(operation=index), tempfile.TemporaryDirectory() as root:
                _, journal, api, execute = self.operation(root,index)
                execute();path = Path(root,journal);old = json.loads(path.read_text())
                if index == 0:
                    old['objects'] = old['objects'][:1]  # Course exists, outline does not.
                else:
                    old['objects'][0]['id'] = 'different_safe_id'
                preserved = json.dumps(old);path.write_text(preserved);api.calls.clear()
                with self.assertRaises(Stop):
                    execute()
                self.assertEqual(api.calls,[])
                self.assertEqual(path.read_text(),preserved)

    def test_every_direct_entry_refuses_dangling_and_external_journal_symlinks(self):
        names = ('state.json','provider-state.json','community-portal-state.json',
                 'community-details-state.json','delivery-state.json',
                 'calendar-delivery-state.json','handoff.json','auth-stop.json')
        for index in range(4):
            for name in names:
                for exists in (False,True):
                    with self.subTest(operation=index,journal=name,external=exists), tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as external:
                        _, _, api, execute = self.operation(root,index)
                        target = Path(external,'original.json')
                        if exists:
                            target.write_text('ORIGINAL_PRIVATE_BYTES');target.chmod(0o640)
                        link = Path(root,name);link.symlink_to(target)
                        with self.assertRaises(Stop):
                            execute()
                        self.assertEqual(api.calls,[])
                        self.assertTrue(link.is_symlink())
                        self.assertEqual(link.readlink(),target)
                        if exists:
                            self.assertEqual(target.read_text(),'ORIGINAL_PRIVATE_BYTES')
                            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o640)
                        else:
                            self.assertFalse(target.exists())

    def test_delivery_lease_symlinks_never_follow_or_chmod_external_targets(self):
        for index in range(4):
            local = 'calendar-delivery.lock' if index == 3 else 'delivery.lock'
            for name in ('.runner.lock','provider.lock',local):
                for exists in (False,True):
                    with self.subTest(operation=index,lease=name,external=exists), tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as external:
                        _, _, api, execute = self.operation(root,index)
                        target = Path(external,'lease')
                        if exists:
                            target.write_text('DO_NOT_CHANGE');target.chmod(0o640)
                        link = Path(root,name);link.symlink_to(target)
                        with self.assertRaises(Stop):
                            execute()
                        self.assertEqual(api.calls,[])
                        self.assertTrue(link.is_symlink())
                        if exists:
                            self.assertEqual(target.read_text(),'DO_NOT_CHANGE')
                            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o640)
                        else:
                            self.assertFalse(target.exists())


class ProviderRootIdentityTests(unittest.TestCase):
    def test_create_callbacks_require_root_kind_and_accept_survey_with_auxiliary_objects(self):
        for operation, root_kind in CREATE_ROOTS.items():
            for good in (True,False):
                with self.subTest(operation=operation,good=good), tempfile.TemporaryDirectory() as root:
                    kind = root_kind if good else ('calendar' if root_kind != 'calendar' else 'form')
                    data = {'location_id':'fixture'}
                    route = {'lane':'public_api','operation':operation,'location_id':'fixture','version':'v3'}
                    callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'fixture',
                        'objects':[{'kind':kind,'id':'root_id'},{'kind':'page','id':'auxiliary_id'}]})
                    if good:
                        result = host._execute_provider(operation,data,route,Path(root),callback)
                        self.assertEqual(result['status'],'API_STEPS_COMPLETE')
                        callback.reset_mock()
                        replay = host._execute_provider(operation,data,route,Path(root),callback)
                        self.assertEqual(replay['status'],'ALREADY_EXECUTED')
                        callback.assert_not_called()
                    else:
                        with self.assertRaises(Stop):
                            host._execute_provider(operation,data,route,Path(root),callback)
                        self.assertEqual(json.loads(Path(root,'provider-state.json').read_text())['status'],
                                         'PROVIDER_RECONCILIATION_REQUIRED')

    def test_corrupted_create_replay_cannot_substitute_another_known_root_kind(self):
        with tempfile.TemporaryDirectory() as root:
            data = {'location_id':'fixture'}
            route = {'lane':'public_api','operation':'courses.create','location_id':'fixture','version':'v3'}
            callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'fixture',
                'objects':[{'kind':'course','id':'course_id'}]})
            host._execute_provider('courses.create',data,route,Path(root),callback)
            path = Path(root,'provider-state.json');old = json.loads(path.read_text())
            old['outcome']['objects'][0]['kind'] = 'calendar'
            preserved = json.dumps(old);path.write_text(preserved);callback.reset_mock()
            with self.assertRaises(Stop):
                host._execute_provider('courses.create',data,route,Path(root),callback)
            callback.assert_not_called();self.assertEqual(path.read_text(),preserved)


if __name__ == '__main__':
    unittest.main()
