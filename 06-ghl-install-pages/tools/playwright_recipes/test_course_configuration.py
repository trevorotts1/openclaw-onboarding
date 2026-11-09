"""Documented course appearance/order semantics and uncertain-write boundaries."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import delivery
from skill6_playwright import Stop


def capability():
    return {'location_id':'COURSE_LOCATION', 'version':'v3', 'status':'PASS',
        'source':'synthetic-course-capability', 'scopes':['courses.readonly','courses.write'],
        'checked_at':datetime.now(timezone.utc).isoformat()}


class CourseApi:
    """Models create's assigned order and replacement of a customization row."""
    def __init__(self, root, *, existing=False):
        self.root = Path(root)
        self.calls = []
        self.exists = existing
        self.course = {'id':'COURSE_ID', 'title':'Synthetic Course', 'libraryOrder':99,
            'updatedAt':'inventory-version', 'customizations':{
                'id':'READ_ONLY_CUSTOMIZATION_ID', 'logoImage':'https://example.com/logo.png',
                'instructorName':'Fixture Instructor', 'heroTextAlignment':'left',
                'heroSpacing':'medium', 'settings':{'oldSetting':True},
                'lessonSettings':{'sidebar':{'visible':True}}}}
        self.fail_put = False
        self.lose_put = False
        self.corrupt_after_put = None
        self.put_attempted = False
        self.intent_at_put = []

    def request(self, method, path, *, location_id, body=None, query=None):
        assert location_id == 'COURSE_LOCATION'
        self.calls.append((method, path, deepcopy(body), deepcopy(query)))
        if path == '/courses/products' and method == 'GET':
            return {'products':[deepcopy(self.course)] if self.exists else [], 'nextCursor':None}
        if path == '/courses/products' and method == 'POST':
            self.exists = True
            self.course.update(deepcopy(body))
            self.course['libraryOrder'] = 99
            return deepcopy(self.course)
        assert path == '/courses/products/COURSE_ID'
        if method == 'PUT':
            self.put_attempted = True
            self.intent_at_put.append(json.loads((self.root/'delivery-state.json').read_text()))
            if self.fail_put:
                raise TimeoutError('synthetic uncertain response')
            if not self.lose_put:
                self.course.update(deepcopy(body))
                if 'customizations' in body:
                    self.course['customizations']['id'] = 'READ_ONLY_CUSTOMIZATION_ID'
            return deepcopy(self.course)
        assert method == 'GET'
        result = deepcopy(self.course)
        if self.put_attempted and self.corrupt_after_put:
            self.corrupt_after_put(result)
        return result


class CourseConfigurationTests(unittest.TestCase):
    def create_inputs(self, **course):
        return {'location_id':'COURSE_LOCATION', 'course':{'title':'Synthetic Course', **course}}

    def update_inputs(self, changes, **extra):
        return {'location_id':'COURSE_LOCATION', 'product_id':'COURSE_ID',
                'course_changes':changes, **extra}

    def test_create_applies_nondefault_library_order_with_followup_intent_put(self):
        with tempfile.TemporaryDirectory() as root:
            api = CourseApi(root)
            data = self.create_inputs(libraryOrder=3)
            result = delivery.run_course(data, root, capability=capability(), transport=api)
            self.assertEqual(result['status'], 'API_STEPS_COMPLETE')
            post = next(call for call in api.calls if call[0] == 'POST')
            self.assertNotIn('libraryOrder',post[2])
            self.assertEqual([call[2] for call in api.calls if call[0] == 'PUT'], [{'libraryOrder':3}])
            self.assertEqual(api.course['libraryOrder'],3)
            self.assertEqual(api.intent_at_put[0]['current_kind'],'course_order')
            self.assertEqual(api.intent_at_put[0]['current_step_status'],'INTENT_RECORDED')
            calls = len(api.calls)
            self.assertEqual(delivery.run_course(data,root,capability=capability(),transport=api)['status'], 'ALREADY_EXECUTED')
            self.assertEqual(len(api.calls), calls)

    def test_create_does_not_reorder_an_existing_different_course_implicitly(self):
        with tempfile.TemporaryDirectory() as root:
            api = CourseApi(root,existing=True)
            with self.assertRaisesRegex(Stop,'explicit update'):
                delivery.run_course(self.create_inputs(libraryOrder=3),root,capability=capability(),transport=api)
            self.assertFalse(any(call[0] != 'GET' for call in api.calls))

    def test_uncertain_order_put_retains_created_course_and_never_retries(self):
        with tempfile.TemporaryDirectory() as root:
            api = CourseApi(root)
            api.fail_put = True
            data = self.create_inputs(libraryOrder=3)
            with self.assertRaises(TimeoutError):
                delivery.run_course(data,root,capability=capability(),transport=api)
            state = json.loads(Path(root,'delivery-state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
            self.assertEqual(state['current_kind'],'course_order')
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            self.assertEqual(state['objects'],[{'kind':'course','id':'COURSE_ID'}])
            calls = len(api.calls)
            with self.assertRaises(Stop):
                delivery.run_course(data,root,capability=capability(),transport=api)
            self.assertEqual(len(api.calls), calls)

    def test_lost_library_order_or_boolean_numeric_readback_is_not_success(self):
        for mode in ('lost','bool'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root)
                if mode == 'lost':api.lose_put = True
                else:api.corrupt_after_put = lambda course:course.update(libraryOrder=True)
                with self.assertRaisesRegex(Stop,'library order'):
                    delivery.run_course(self.create_inputs(libraryOrder=1),root,capability=capability(),transport=api)
                self.assertEqual(json.loads(Path(root,'delivery-state.json').read_text())['status'],'NEEDS_RECONCILIATION')

    def test_theme_update_preserves_other_appearance_columns_and_opaque_settings(self):
        with tempfile.TemporaryDirectory() as root:
            api = CourseApi(root,existing=True)
            before = deepcopy(api.course['customizations'])
            data = self.update_inputs({'customizations':{'templateId':'APPROVED_TEMPLATE'}})
            result = delivery.run_course_update(data,root,capability=capability(),transport=api)
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            payload = next(call[2] for call in api.calls if call[0]=='PUT')
            self.assertNotIn('id',payload['customizations'])
            self.assertEqual(api.course['customizations'],{**before,'templateId':'APPROVED_TEMPLATE'})
            self.assertEqual(api.intent_at_put[0]['current_step_status'],'INTENT_RECORDED')

    def test_explicit_settings_object_replaces_only_that_blob_and_can_clear_to_null(self):
        for settings in ({'colors':{'accent':'#123456'}}, {}, None):
            with self.subTest(settings=settings), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root,existing=True)
                data = self.update_inputs({'customizations':{'settings':settings}})
                delivery.run_course_update(data,root,capability=capability(),transport=api)
                self.assertEqual(api.course['customizations']['settings'],settings)
                self.assertEqual(api.course['customizations']['lessonSettings'],{'sidebar':{'visible':True}})

    def test_ignored_clear_or_lost_sibling_does_not_pass_authored_subset_readback(self):
        for mode in ('retained-setting','lost-sibling'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root,existing=True)
                if mode == 'retained-setting':
                    api.corrupt_after_put = lambda course:course['customizations']['settings'].update(unrequested=True)
                    changes = {'customizations':{'settings':{}}}
                else:
                    api.corrupt_after_put = lambda course:course['customizations'].pop('logoImage')
                    changes = {'customizations':{'templateId':'APPROVED_TEMPLATE'}}
                data = self.update_inputs(changes)
                with self.assertRaisesRegex(Stop,'read-back'):
                    delivery.run_course_update(data,root,capability=capability(),transport=api)
                calls = len(api.calls)
                with self.assertRaises(Stop):
                    delivery.run_course_update(data,root,capability=capability(),transport=api)
                self.assertEqual(len(api.calls),calls)

    def test_nullable_read_enum_is_not_written_as_invalid_null_but_must_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            api = CourseApi(root,existing=True)
            api.course['customizations']['heroSpacing'] = None
            # This replacing fake would lose an omitted null, so preserve it as
            # the membership partial writer does for this nullable read column.
            original = api.request
            def request(method,path,**kw):
                result = original(method,path,**kw)
                if method == 'PUT':api.course['customizations']['heroSpacing'] = None
                return result
            delivery.run_course_update(self.update_inputs({'customizations':{'templateId':'TEMPLATE'}}),root,
                capability=capability(),transport=type('Transport',(),{'request':staticmethod(request)})())
            payload = next(call[2] for call in api.calls if call[0]=='PUT')
            self.assertNotIn('heroSpacing',payload['customizations'])
            self.assertIsNone(api.course['customizations']['heroSpacing'])

    def test_customization_types_and_non_json_settings_refuse_before_network(self):
        bad = [ {'logoImage':True}, {'instructorName':{}}, {'templateId':[]},
            {'heroSpacing':None}, {'heroTextAlignment':'center'}, {'settings':[]},
            {'lessonSettings':False}, {'settings':{1:'non-string-key'}},
            {'settings':{'bad':float('nan')}}, {'settings':{'bad':set()}},
            {'customizationId':'injected'} ]
        for custom in bad:
            with self.subTest(custom=custom), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root)
                with self.assertRaises(Stop):
                    delivery.run_course(self.create_inputs(customizations=custom),root,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_library_order_rejects_bool_nonfinite_and_overflow_before_network(self):
        for value in (True,False,'3',None,float('inf'),float('nan'),10**1000):
            with self.subTest(value=str(value)[:20]), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root)
                with self.assertRaises(Stop):
                    delivery.run_course(self.create_inputs(libraryOrder=value),root,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_unsupported_top_level_requests_are_not_silently_dropped(self):
        for extra in ({'publish':True},{'publish':0},{'enrollments':[]},{'options':{}},
                      {'modules':[]},{'expected_updated_at':None},{'auth_activation':{}},
                      {'course_changse':{'title':'Typo'}}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as root:
                api = CourseApi(root,existing=True)
                data = self.update_inputs({'description':'Approved'},**extra)
                with self.assertRaises(Stop):
                    delivery.run_course_update(data,root,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_nonfinite_quiz_sequence_is_rejected_before_use(self):
        for value in (float('inf'),float('nan'),10**1000):
            with self.subTest(value=str(value)[:20]), self.assertRaises(Stop):
                delivery.validate_quiz({'title':'Synthetic Quiz','questions':[{'title':'Choose',
                    'questionType':'single','sequenceNumber':value,'options':[
                    {'title':'Yes','isCorrect':True},{'title':'No','isCorrect':False}]}]})

    def test_transport_query_cannot_override_the_bound_location(self):
        api = delivery.Skill44Transport()
        for query in ({'locationId':'FOREIGN'}, {'location_id':'FOREIGN'},
                      {'locationId':None}, ['invalid']):
            with self.subTest(query=query), patch.object(api.client.requests,'request') as request:
                with self.assertRaises(Stop):
                    api.request('GET','/courses/products',location_id='COURSE_LOCATION',query=query)
                request.assert_not_called()

    def test_invalid_later_outline_properties_refuse_before_creating_the_course(self):
        for kind, bad in (
            ('module',{'sequenceNo':True}), ('module',{'dripDays':float('nan')}),
            ('module',{'metadata':{'dripUnit':'weeks'}}),
            ('module',{'metadata':{'dripDate':'not-a-date'}}),
            ('module',{'metadata':{'invented':True}}),
            ('module',{'parentCategory':True}),
            ('lesson',{'commentStatus':'invented'}),
            ('lesson',{'commentPermission':None}),
            ('lesson',{'metaData':{'nonJson':set()}}),
            ('lesson',{'sequenceNo':float('inf')}),
            ('lesson',{'contentId':{'invented':'id'}})):
            with self.subTest(kind=kind,bad=bad), tempfile.TemporaryDirectory() as root:
                data = self.create_inputs()
                data['modules'] = [{'title':'Module', 'lessons':[{'title':'Lesson'}]}]
                target = data['modules'][0] if kind == 'module' else data['modules'][0]['lessons'][0]
                target.update(bad)
                api = CourseApi(root)
                with self.assertRaises(Stop):
                    delivery.run_course(data,root,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_null_category_comment_permission_has_documented_omitted_semantics(self):
        result = delivery.validate_course({**self.create_inputs(), 'modules':[
            {'title':'Module', 'commentPermission':None,
             'metadata':{'dripUnit':'hours','dripDate':None}}]})
        self.assertNotIn('commentPermission',result['modules'][0]['body'])
        self.assertEqual(result['modules'][0]['body']['metadata'],{'dripUnit':'hours','dripDate':None})

    def test_quiz_messages_and_authored_ids_are_validated_before_use(self):
        def quiz():
            return {'title':'Quiz','questions':[{'title':'Choose',
                'questionType':'single','sequenceNumber':1,'options':[
                    {'title':'Yes','isCorrect':True},{'title':'No','isCorrect':False}]}]}
        for mutate in (
            lambda q:q.update(passMessage=False),
            lambda q:q.update(failMessage=None),
            lambda q:q['questions'][0].update(explanation={}),
            lambda q:q['questions'][0].update(id=12),
            lambda q:[option.update(id='DUPLICATE') for option in q['questions'][0]['options']]):
            value = quiz();mutate(value)
            with self.subTest(value=value), self.assertRaises(Stop):
                delivery.validate_quiz(value)


if __name__ == '__main__':
    unittest.main()
