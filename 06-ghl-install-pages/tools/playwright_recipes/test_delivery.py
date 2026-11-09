import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from delivery import run_course, validate_course, validate_quiz, Skill44Transport, course_executor, run_lesson_quiz, DeliveryApiError, run_course_update, configure_community_channels, validate_api_inputs, RegisteredCalendarDispatcher, meeting_calendar_executor, validate_calendar_integration, CalendarHttpTransport
from skill6_playwright import Stop


def capability(location='fixture'):
    return {'location_id':location,'version':'v3','status':'PASS','source':'fixture:probe',
            'scopes':['courses.readonly','courses.write'], 'checked_at':datetime.now(timezone.utc).isoformat()}


def inputs():
    return {'location_id':'fixture','course':{'title':'Course A','description':'Approved'},
            'modules':[{'title':'Module 1','lessons':[{'title':'Lesson 1','description':'Text'}]}]}


def quiz():
    return {'title':'Quiz','passingGrade':70,'requiredPassingGrade':True,'questions':[
        {'title':'Pick one','questionType':'single','sequenceNumber':1,'options':[
            {'title':'Yes','isCorrect':True},{'title':'No','isCorrect':False}]}]}


class FakeTransport:
    def __init__(self):
        self.calls=[]; self.objects={}; self.counter=0; self.fail_post=False
    def request(self,method,path,*,location_id,body=None,query=None):
        self.calls.append((method,path,location_id,body,query))
        if method=='GET' and path=='/courses/products':
            return {'products':[], 'nextCursor':None}
        if method=='POST':
            if self.fail_post: raise TimeoutError('request uncertain')
            self.counter+=1; out={'id':'id_'+str(self.counter),**body}
            self.objects[path+'/'+out['id'] if not path.endswith('/quiz') else path]=out
            return out
        if method=='PUT':
            self.objects[path]=body
            return body
        return self.objects[path]


class DeliveryTests(unittest.TestCase):
    def test_full_outline_uses_v3_contract_and_persisted_readback(self):
        api=FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            out=run_course(inputs(),directory,capability=capability(),transport=api)
            self.assertEqual(out['status'],'API_STEPS_COMPLETE')
            writes=[c for c in api.calls if c[0]=='POST']
            self.assertEqual([c[1] for c in writes],['/courses/products','/courses/products/id_1/categories','/courses/products/id_1/lessons'])
            self.assertEqual(writes[2][3]['categoryId'],'id_2')
            self.assertEqual(writes[2][3]['visibility'],'draft')
            self.assertNotIn('locationId',writes[0][3])
            self.assertEqual(len(out['objects']),3)
            self.assertTrue(all(c[2]=='fixture' for c in api.calls))
            state=json.loads((Path(directory)/'delivery-state.json').read_text())
            self.assertEqual(state['status'],'API_STEPS_COMPLETE')
            calls=len(api.calls)
            self.assertEqual(run_course(inputs(),directory,capability=capability(),transport=api)['status'],'ALREADY_EXECUTED')
            self.assertEqual(len(api.calls),calls)

    def test_quiz_writes_questions_and_reads_them_back(self):
        data=inputs(); data['modules'][0]['lessons'][0]['quiz']=quiz()
        api=FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            out=run_course(data,directory,capability=capability(),transport=api)
            self.assertEqual(out['status'],'API_STEPS_COMPLETE')
            writes=[c for c in api.calls if c[0]=='PUT']
            self.assertEqual(writes[0][1],'/courses/products/id_1/quizzes/id_4/questions')
            self.assertEqual(writes[0][3]['questions'][0]['options'][0]['isCorrect'],True)
            self.assertEqual(api.calls[-1][0],'GET')

    def test_uncertain_create_is_not_replayed(self):
        api=FakeTransport();api.fail_post=True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):run_course(inputs(),directory,capability=capability(),transport=api)
            state=json.loads((Path(directory)/'delivery-state.json').read_text())
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
            calls=len(api.calls)
            with self.assertRaises(Stop):run_course(inputs(),directory,capability=capability(),transport=api)
            self.assertEqual(len(api.calls),calls)

    def test_wrong_tenant_or_stale_capability_stops_before_network(self):
        for cap in (capability('other'),{**capability(),'checked_at':'2020-01-01T00:00:00Z'},
                    {**capability(),'scopes':['courses.write']}):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as directory:
                api=FakeTransport()
                with self.assertRaises(Stop):run_course(inputs(),directory,capability=cap,transport=api)
                self.assertEqual(api.calls,[])

    def test_identity_body_and_publish_refused_before_network(self):
        for extra in ({'locationId':'foreign'},{'userId':'user'},{'id':'id'}):
            data=inputs();data['course'].update(extra)
            with self.assertRaises(Stop):validate_course(data)
        data=inputs(); data['modules'][0]['visibility']='published'
        with self.assertRaises(Stop):validate_course(data)

    def test_bad_quiz_answers_refused(self):
        for value in ('true',False):
            q=quiz();q['questions'][0]['options'][0]['isCorrect']=value
            with self.assertRaises(Stop):validate_quiz(q)
        q=quiz();q['passingGrade']=101
        with self.assertRaises(Stop):validate_quiz(q)

    def test_server_generated_question_ids_do_not_break_readback(self):
        class IDs(FakeTransport):
            def request(self,method,path,**kw):
                out=super().request(method,path,**kw)
                if method=='GET' and path.endswith('/questions'):
                    out=json.loads(json.dumps(out));out['questions'][0]['id']='server_id'
                    out['questions'][0]['options'][0]['id']='answer_id'
                return out
        data=inputs();data['modules'][0]['lessons'][0]['quiz']=quiz()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(run_course(data,directory,capability=capability(),transport=IDs())['status'],'API_STEPS_COMPLETE')

    def test_existing_lesson_quiz_creation_is_real_api_flow(self):
        class ExistingLesson(FakeTransport):
            def request(self,method,path,**kw):
                if method=='GET' and path in ('/courses/products/p','/courses/products/p/lessons/l'):
                    self.calls.append((method,path,kw['location_id'],None,None));return {'id':'parent'}
                if method=='GET' and path.endswith('/quiz') and path not in self.objects:
                    self.calls.append((method,path,kw['location_id'],None,None));raise DeliveryApiError(404)
                return super().request(method,path,**kw)
        api=ExistingLesson()
        with tempfile.TemporaryDirectory() as directory:
            result=run_lesson_quiz({'location_id':'fixture','product_id':'p','lesson_id':'l','quiz':quiz()},directory,capability=capability(),transport=api)
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            self.assertIn(('POST','/courses/products/p/lessons/l/quiz'),[(c[0],c[1]) for c in api.calls])
            self.assertIn(('PUT','/courses/products/p/quizzes/id_1/questions'),[(c[0],c[1]) for c in api.calls])

    def test_quiz_scope_error_never_becomes_creation(self):
        class Denied(FakeTransport):
            def request(self,method,path,**kw):
                self.calls.append((method,path,kw['location_id'],None,None))
                if path.endswith('/quiz'):raise DeliveryApiError(403)
                return {'id':'parent'}
        api=Denied()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DeliveryApiError):run_lesson_quiz({'location_id':'fixture','product_id':'p','lesson_id':'l','quiz':quiz()},directory,capability=capability(),transport=api)
            self.assertFalse(any(c[0]!='GET' for c in api.calls))

    def test_delivery_root_cannot_be_leased_twice(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            with open(Path(directory)/'delivery.lock','a') as held:
                fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                api=FakeTransport()
                with self.assertRaises(Stop):run_course(inputs(),directory,capability=capability(),transport=api)
                self.assertEqual(api.calls,[])

    def test_course_appearance_update_uses_documented_api_fields(self):
        class Update(FakeTransport):
            def __init__(self):
                super().__init__();self.objects['/courses/products/p']={'id':'p','title':'Course','updatedAt':'current'}
        api=Update()
        data={'location_id':'fixture','product_id':'p','expected_updated_at':'current',
              'course_changes':{'customCss':'.brand {}','customizations':{'heroTextAlignment':'centered'}}}
        with tempfile.TemporaryDirectory() as directory:
            result=run_course_update(data,directory,capability=capability(),transport=api)
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            write=next(c for c in api.calls if c[0]=='PUT')
            self.assertEqual(write[1],'/courses/products/p')
            self.assertEqual(write[3],data['course_changes'])
            self.assertNotIn('title',write[3])

    def test_stale_course_update_stops_before_put(self):
        api=FakeTransport();api.objects['/courses/products/p']={'id':'p','title':'Course','updatedAt':'newer'}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Stop):run_course_update({'location_id':'fixture','product_id':'p',
                'expected_updated_at':'old','course_changes':{'customCss':'.brand{}'}},directory,capability=capability(),transport=api)
            self.assertFalse(any(c[0]=='PUT' for c in api.calls))

    def test_api_callback_refuses_operation_version_or_transport_mismatch(self):
        data={**inputs(),'api_capability':capability()}
        base={'operation':'courses.create','version':'v3','lane':'public_api','location_id':'fixture'}
        for change in ({'operation':'courses.update'},{'version':'2021-07-28'},{'version':None},{'lane':'official_mcp'}):
            with self.subTest(change=change), patch('delivery.run_course') as run:
                with self.assertRaises(Stop):course_executor(operation='courses.create',inputs=data,
                    route={**base,**change},evidence_root='unused')
                run.assert_not_called()

    def test_api_schema_check_is_concrete_and_read_only(self):
        route={'operation':'courses.create','version':'v3','lane':'skill44','location_id':'fixture'}
        with patch('delivery.Skill44Transport') as transport:
            result=validate_api_inputs('courses.create',{**inputs(),'api_capability':capability()},route)
            validate_api_inputs('courses.create',{**inputs(),'api_capability':capability()},{**route,'lane':'official_mcp'})
            self.assertEqual(result['course']['title'],'Course A')
            transport.assert_not_called()
            with self.assertRaises(Stop):validate_api_inputs('courses.create',{'location_id':'fixture',
                'course':{'title':''},'api_capability':capability()},route)
            transport.assert_not_called()

    def test_api_callback_validates_route(self):
        with self.assertRaises(Stop):course_executor(operation='courses.create',inputs=inputs(),route={'location_id':'other'},evidence_root='unused')

    def test_real_transport_preserves_skill44_safety_gate_before_request(self):
        api=Skill44Transport()
        client=api.client
        with patch.object(client,'check_write',side_effect=Stop('gate')), patch.object(client.requests,'request') as request:
            with self.assertRaises(Stop):api.request('POST','/courses/products',location_id='fixture',body={'title':'A'})
            request.assert_not_called()

    def test_real_transport_uses_v3_and_query_location(self):
        api=Skill44Transport();client=api.client
        with patch.object(client,'check_write') as gate, patch.object(client,'_headers',return_value={'Version':'v3'}) as headers, patch.object(client.requests,'request') as request:
            request.return_value.json.return_value={'id':'created'}
            api.request('POST','/courses/products',location_id='fixture',body={'title':'A'})
            self.assertEqual(request.call_args.args[:2],('POST','https://services.leadconnectorhq.com/courses/products?locationId=fixture'))
            headers.assert_called_once_with('v3','/courses/products','POST')
            self.assertEqual(gate.call_args.kwargs['location_id'],'fixture')


class CommunityChannelTests(unittest.TestCase):
    def test_legacy_front_door_requires_authenticated_portal_context(self):
        page = Mock()
        with self.assertRaises(Stop):
            configure_community_channels(page, {'portal_url':'https://portal.example/communities/groups/demo/home',
                                               'channels':[{'name':'Introductions','description':'Say hello'}]})
        page.get_by_role.assert_not_called()

    def test_legacy_front_door_requires_protected_evidence_root(self):
        page = Mock()
        with self.assertRaises(Stop):
            configure_community_channels(page, {}, portal_context=object())
        page.get_by_role.assert_not_called()

    def test_legacy_front_door_forwards_to_the_one_maintained_adapter(self):
        import community_portal
        page, context, step = object(), object(), {'authored':'fixture'}
        expected = {'status':'NEEDS_VERIFICATION'}
        with patch.object(community_portal, 'run_channels', return_value=expected) as run:
            result = configure_community_channels(page, step, portal_context=context, evidence_root='/fixture')
        self.assertIs(result, expected)
        run.assert_called_once_with(page, step, '/fixture', portal_context=context)


class CalendarProviderTests(unittest.TestCase):
    def context(self, mutate=True, forbidden=False):
        from types import SimpleNamespace
        from ghl_public_client import engine
        seams=engine()
        api_client=SimpleNamespace(_get_token=lambda:'pit-fixture-placeholder-for-offline-test')
        gate=seams['CapabilityGate']({name:seams['Capability'](operation_id=name,
            contract_verified=True,adapter_built=True,offline_tests_passed=True,
            read_verified=True,canary_verified=True,enabled=True,tenant='fixture',activation='VERIFIED')
            for name in ('calendars.get','calendars.update')},tenant='fixture')
        class Transport:
            def __init__(self):
                self.calendar={'id':'cal','locationId':'fixture','calendarType':'event','locationConfigurations':[]}
                self.calls=[];self.last_body=None
            def request(self,**kw):
                self.calls.append(kw)
                status=403 if forbidden else 200
                if kw['method']=='PUT' and mutate:self.calendar.update(kw['body'])
                self.last_body={'calendar':json.loads(json.dumps(self.calendar))}
                return seams['TransportResponse'](status=status,headers={},body=json.dumps(self.last_body).encode())
        transport=Transport()
        dispatcher=RegisteredCalendarDispatcher('fixture',capability_gate=gate,transport=transport,client=api_client)
        inputs={'location_id':'fixture','calendar_id':'cal','integration_mode':'permanent_calendar_link',
            'room':{'location_id':'fixture','status':'PRESENT','room_id':'room','source':'fixture:room',
                    'url':'https://portal.example/meeting-room/room'},
            'api_capability':{**capability(),'scopes':['calendars.readonly','calendars.write']}}
        route={'operation':'meetings.integrate','version':'v3','lane':'public_api','location_id':'fixture'}
        return dispatcher,transport,inputs,route

    def test_calendar_update_is_registered_with_contract_and_readback(self):
        dispatcher,_,_,_=self.context()
        row=dispatcher.seams['OPERATIONS'].get('calendars.update')
        self.assertEqual((row.method,row.path_template,row.version),('PUT','/calendars/{calendarId}','v3'))
        self.assertEqual(row.scopes_candidate,('calendars.write',))
        self.assertEqual(row.readback_plan,'calendars.get')
        self.assertEqual(row.doc_fetch_date,'2026-11-08')

    def test_registered_provider_updates_and_independently_reads_back(self):
        dispatcher,transport,inputs,route=self.context()
        with tempfile.TemporaryDirectory() as directory:
            result=meeting_calendar_executor(operation='meetings.integrate',inputs=inputs,route=route,evidence_root=directory,dispatcher=dispatcher)
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            self.assertEqual([c['method'] for c in transport.calls],['GET','PUT','GET','GET'])
            self.assertTrue(all(c['version']=='v3' for c in transport.calls))
            self.assertEqual(result['objects'],[{'kind':'calendar','id':'cal'}])

    def test_readback_mismatch_is_failure_not_success(self):
        dispatcher,transport,inputs,route=self.context(mutate=False)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Stop):meeting_calendar_executor(operation='meetings.integrate',inputs=inputs,route=route,evidence_root=directory,dispatcher=dispatcher)
            state=json.loads((Path(directory)/'calendar-delivery-state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_RECONCILIATION')
            self.assertEqual(sum(c['method']=='PUT' for c in transport.calls),1)

    def test_403_never_falls_back_or_writes(self):
        dispatcher,transport,inputs,route=self.context(forbidden=True)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DeliveryApiError):meeting_calendar_executor(operation='meetings.integrate',inputs=inputs,route=route,evidence_root=directory,dispatcher=dispatcher)
            self.assertEqual([c['method'] for c in transport.calls],['GET'])

    def test_private_invite_is_only_in_api_request_not_state(self):
        dispatcher,transport,inputs,route=self.context()
        secret='fixture-invite-only-in-memory'
        inputs['private_invite_url']=inputs['room']['url']+'?pwd='+secret
        with tempfile.TemporaryDirectory() as directory:
            result=meeting_calendar_executor(operation='meetings.integrate',inputs=inputs,route=route,evidence_root=directory,dispatcher=dispatcher)
            self.assertEqual(result['status'],'API_STEPS_COMPLETE')
            writes=[c for c in transport.calls if c['method']=='PUT']
            self.assertIn(secret,json.dumps(writes[0]['body']))
            for path in Path(directory).glob('*.json'):
                self.assertNotIn(secret,path.read_text())
                self.assertNotIn('?pwd=',path.read_text())

    def test_calendar_http_transport_keeps_skill44_write_gate(self):
        client=Skill44Transport().client
        transport=CalendarHttpTransport(client,'fixture')
        with patch.object(client,'check_write',side_effect=Stop('gate')),patch.object(client.requests,'request') as request:
            with self.assertRaises(Stop):transport.request(method='PUT',url='/calendars/cal',version='v3',headers={},query={},body={'locationConfigurations':[]},timeout_s=30)
            request.assert_not_called()

    def test_calendar_mode_must_be_explicit(self):
        _,_,inputs,route=self.context()
        for mode in (None,'dynamic_native','typo'):
            with self.subTest(mode=mode),self.assertRaises(Stop):
                validate_calendar_integration({**inputs,'integration_mode':mode},route)

    def test_default_deny_is_not_replaced_by_recipe_receipt(self):
        dispatcher,transport,inputs,route=self.context()
        dispatcher.adapter._capability=dispatcher.seams['CapabilityGate'](tenant='fixture')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Stop):meeting_calendar_executor(operation='meetings.integrate',inputs=inputs,route=route,evidence_root=directory,dispatcher=dispatcher)
            self.assertEqual(transport.calls,[])


if __name__=='__main__':unittest.main()
