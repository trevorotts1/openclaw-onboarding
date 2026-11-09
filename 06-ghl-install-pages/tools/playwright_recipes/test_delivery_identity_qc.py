"""Independent API identity boundaries, before and after an uncertain write."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import delivery
from skill6_playwright import Stop


def capability():
    return {'location_id':'fixture', 'version':'v3', 'status':'PASS',
            'source':'fixture:identity-proof',
            'scopes':['courses.readonly','courses.write'],
            'checked_at':datetime.now(timezone.utc).isoformat()}


def update():
    return {'location_id':'fixture', 'product_id':'p',
            'course_changes':{'title':'Approved new title'}}


class UpdateTransport:
    def __init__(self, claims=None, after_claims=None):
        self.course={'id':'p', 'locationId':'fixture', 'title':'Original'}
        self.claims=claims or {}
        self.after_claims=after_claims or {}
        self.changed=False
        self.calls=[]

    def request(self, method, path, *, location_id, body=None, query=None):
        self.calls.append((method,path,location_id))
        if path != '/courses/products/p' or location_id != 'fixture':
            raise AssertionError('Unexpected transport target')
        if method == 'GET':
            return {**deepcopy(self.course),
                    **(self.after_claims if self.changed else self.claims)}
        if method == 'PUT':
            self.changed=True
            self.course.update(deepcopy(body))
            return deepcopy(self.course)
        raise AssertionError('Unexpected transport mutation')


class ApiIdentityTests(unittest.TestCase):
    def test_crosswired_post_identity_retains_only_observed_candidate_for_reconciliation(self):
        import test_delivery as fixtures
        for kind in ('course', 'quiz'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                class CrosswiredPost(fixtures.FakeTransport):
                    def request(self, method, path, **kwargs):
                        value = super().request(method, path, **kwargs)
                        if method == 'POST' and ((kind == 'course' and path == '/courses/products')
                                or (kind == 'quiz' and path.endswith('/quiz'))):
                            value['locationId'] = 'FOREIGN'
                        return value
                api = CrosswiredPost()
                data = fixtures.inputs()
                data['modules'][0]['lessons'][0]['quiz'] = fixtures.quiz()
                with self.assertRaises(Stop):
                    delivery.run_course(data, directory, capability=fixtures.capability(), transport=api)
                state = json.loads(Path(directory, 'delivery-state.json').read_text())
                self.assertEqual(state['status'], 'NEEDS_RECONCILIATION')
                self.assertEqual(state['current_step_status'], 'INTENT_RECORDED')
                self.assertEqual(state['observed_objects'], [{'kind': kind, 'id': 'id_' + str(api.counter)}])
                self.assertFalse(any(row['kind'] == kind for row in state['objects']))
                self.assertEqual(api.calls[-1][0], 'POST')
                before = len(api.calls)
                with self.assertRaises(Stop):
                    delivery.run_course(data, directory, capability=fixtures.capability(), transport=api)
                self.assertEqual(len(api.calls), before)

    def test_created_quiz_reopen_must_still_belong_to_its_lesson(self):
        import test_delivery as fixtures
        class CrosswiredQuiz(fixtures.FakeTransport):
            def request(self,method,path,**kwargs):
                value=super().request(method,path,**kwargs)
                if method == 'GET' and path.endswith('/quiz'):
                    value['lessonId']='another_lesson'
                return value
        data=fixtures.inputs()
        data['modules'][0]['lessons'][0]['quiz']=fixtures.quiz()
        with tempfile.TemporaryDirectory() as directory:
            api=CrosswiredQuiz()
            with self.assertRaises(Stop):
                delivery.run_course(data,directory,capability=fixtures.capability(),transport=api)
            state=json.loads((Path(directory)/'delivery-state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
            self.assertEqual(state['objects'][-1]['kind'],'quiz')
            self.assertFalse(any(method == 'PUT' for method,_,_,_,_ in api.calls))

    def test_quiz_question_identity_corruption_remains_uncertain_without_retry(self):
        import test_delivery as fixtures
        corruptions=(
            lambda value:value['questions'][0].update(quizId='another_quiz'),
            lambda value:value['questions'][0].update(id=None),
            lambda value:value['questions'][0].update(locationId='another_location'),
            lambda value:[option.update(id='duplicate_answer')
                          for option in value['questions'][0]['options']],
        )
        for corrupt in corruptions:
            with self.subTest(corruption=corrupt), tempfile.TemporaryDirectory() as directory:
                class CrosswiredQuestions(fixtures.FakeTransport):
                    def request(self,method,path,**kwargs):
                        value=super().request(method,path,**kwargs)
                        if method == 'GET' and path.endswith('/questions'):corrupt(value)
                        return value
                data=fixtures.inputs()
                data['modules'][0]['lessons'][0]['quiz']=fixtures.quiz()
                api=CrosswiredQuestions()
                with self.assertRaises(Stop):
                    delivery.run_course(data,directory,capability=fixtures.capability(),transport=api)
                state=json.loads((Path(directory)/'delivery-state.json').read_text())
                self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
                self.assertEqual(state['current_kind'],'quiz_questions')
                before=len(api.calls)
                with self.assertRaises(Stop):
                    delivery.run_course(data,directory,capability=fixtures.capability(),transport=api)
                self.assertEqual(len(api.calls),before)

    def test_unknown_existing_appearance_column_cannot_be_silently_lost(self):
        import test_course_configuration as fixtures
        with tempfile.TemporaryDirectory() as directory:
            api=fixtures.CourseApi(directory,existing=True)
            api.course['customizations']['futureAppearance']='preserve'
            before=deepcopy(api.course)
            with self.assertRaises(Stop):
                delivery.run_course_update({
                    'location_id':'COURSE_LOCATION','product_id':'COURSE_ID',
                    'course_changes':{'customizations':{'templateId':'T'}}},
                    directory,capability=fixtures.capability(),transport=api)
            self.assertEqual(api.course,before)
            self.assertEqual([method for method,_,_,_ in api.calls],['GET'])

    def test_explicit_foreign_or_malformed_course_identity_refuses_before_put(self):
        for claims in ({'id':'other'}, {'id':True}, {'id':None},
                       {'locationId':'other'}, {'location_id':'other'},
                       {'locationId':None},
                       {'locationId':'fixture','location_id':'other'}):
            with self.subTest(claims=claims), tempfile.TemporaryDirectory() as directory:
                api=UpdateTransport(claims)
                with self.assertRaises(Stop):
                    delivery.run_course_update(update(),directory,
                        capability=capability(),transport=api)
                self.assertEqual([method for method,_,_ in api.calls],['GET'])
                self.assertFalse((Path(directory)/'delivery-state.json').exists())

    def test_crosswired_post_write_readback_remains_uncertain_and_never_retries(self):
        for claims in ({'id':'other'}, {'locationId':'other'}):
            with self.subTest(claims=claims), tempfile.TemporaryDirectory() as directory:
                api=UpdateTransport(after_claims=claims)
                with self.assertRaises(Stop):
                    delivery.run_course_update(update(),directory,
                        capability=capability(),transport=api)
                state=json.loads((Path(directory)/'delivery-state.json').read_text())
                self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
                self.assertEqual([method for method,_,_ in api.calls],['GET','PUT','GET'])
                before=list(api.calls)
                with self.assertRaises(Stop):
                    delivery.run_course_update(update(),directory,
                        capability=capability(),transport=api)
                self.assertEqual(api.calls,before)

    def test_wrong_existing_lesson_identity_stops_before_quiz_lookup(self):
        class ParentTransport:
            def __init__(self):self.calls=[]
            def request(self,method,path,*,location_id,body=None,query=None):
                self.calls.append((method,path))
                if method != 'GET':raise AssertionError('Parent check must not write')
                if path == '/courses/products/p':return {'id':'p','locationId':'fixture'}
                if path == '/courses/products/p/lessons/l':
                    return {'id':'another_lesson','locationId':'fixture'}
                raise AssertionError('Wrong parent identity must stop before quiz lookup')
        api=ParentTransport()
        quiz={'title':'Fixture quiz','passingGrade':70,'requiredPassingGrade':True,
              'questions':[{'title':'Choose','questionType':'single','sequenceNumber':1,
                'options':[{'title':'Yes','isCorrect':True},
                           {'title':'No','isCorrect':False}]}]}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Stop):
                delivery.run_lesson_quiz({'location_id':'fixture','product_id':'p',
                    'lesson_id':'l','quiz':quiz},directory,
                    capability=capability(),transport=api)
        self.assertEqual(api.calls,[('GET','/courses/products/p'),
            ('GET','/courses/products/p/lessons/l')])


if __name__ == '__main__':unittest.main()
