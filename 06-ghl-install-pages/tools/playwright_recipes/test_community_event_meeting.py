"""Existing native event room contracts; no portal or notification acceptance."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import community_event_meeting as events
from skill6_playwright import Stop

ROOM='a'*24
ROOM_URL='https://portal.example.invalid/meet/'+ROOM


def inputs():
    title,description='Fixture event','Existing approved description'
    location='https://example.invalid/existing'
    return {'location_id':'loc','location_name':'Fixture account',
        'start_url':'https://app.convertandflow.com/v2/location/loc/memberships/communities/community-groups',
        'portal_url':'https://portal.example.invalid/communities/groups/fixture/home',
        'group_name':'Fixture group','group_id':'group','event_id':'event','allow_room_creation':True,
        'expected':{'view':{'title':title,'date':'Nov 09, 2026','time':'9:00 PM - 10:00 PM',
            'description':description,'attendee_count':'1 guests','fee':'Free',
            'location_text':location,'location_url':location},
            'form':{'title':title,'description':description,'start_date':'Nov 09, 2026',
                'start_time':'9:00','start_ampm':'PM','end_date':'Nov 09, 2026',
                'end_time':'10:00','end_ampm':'PM','timezone':'America/New_York GMT-05:00',
                'recurrence':"Doesn't repeat",'location_type':'Other','location_url':location,
                'hide_location':False,'remind':False,'hide_attendees':False,
                'attendees':'All members','thumbnail_src':None}}}


class EventRoomTests(unittest.TestCase):
    def test_unsupported_or_unsafe_plan_stops_before_context_or_browser(self):
        mutations=(
            lambda d:d.update(allow_room_creation=False),
            lambda d:d.update(allow_room_creation='true'),
            lambda d:d.update(event_id='../foreign'),
            lambda d:d.update(portal_url=d['portal_url'].replace('/home','/events')),
            lambda d:d['expected']['view'].update(fee='Paid'),
            lambda d:d['expected']['form'].update(remind=True),
            lambda d:d['expected']['form'].update(hide_location=True),
            lambda d:d['expected']['form'].update(recurrence='Weekly'),
            lambda d:d['expected']['form'].update(thumbnail_src='https://example.invalid/photo'),
            lambda d:d['expected']['form'].update(attendees='Selected members'),
            lambda d:d['expected']['form'].update(title='Different title'),
            lambda d:d['expected']['form'].pop('start_date'),
        )
        for index,mutate in enumerate(mutations):
            data=inputs();mutate(data)
            with self.subTest(index=index),self.assertRaises(Stop):
                events.run_event(object(),data,'unused',portal_context={})

    def test_generated_room_link_must_remain_exact_portal_and_credential_free(self):
        data=inputs()
        self.assertEqual(events._room_id(ROOM_URL,data),ROOM)
        for url in (ROOM_URL+'?pwd=private',ROOM_URL+'#private',
            ROOM_URL.replace('portal.example.invalid','foreign.invalid'),
            ROOM_URL.replace('/meet/','/groups/'),ROOM_URL[:-1]+'z'):
            with self.subTest(url=url),self.assertRaises(Stop): events._room_id(url,data)

    def exercise(self,*,reused=False,corrupt_after=False,preflight_drift=False):
        data=inputs()
        if reused:
            data['allow_room_creation']=False
            data['expected']['form'].update(location_type='Live Room',location_url=ROOM_URL)
            data['expected']['view'].update(location_text=ROOM,location_url=ROOM_URL)
        state={'form':deepcopy(data['expected']['form']),'saved':False,'reloaded':False}
        log=[]
        class Control:
            def __init__(self,label): self.label=label
            def count(self): return 1
            def is_visible(self): return True
            def is_enabled(self): return False if self.label=='url' else True
            def get_attribute(self,name): return None
            def locator(self,selector):
                if (self.label,selector)!=('url-wrapper','input'):raise AssertionError((self.label,selector))
                return Control('url')
            def wait_for(self,**kwargs):log.append(('wait',kwargs['state']))
        class Dialog(Control):
            def locator(self,selector):
                if selector=='#event-form-location':return Control('select')
                if selector=='#event-form-location-url':return Control('url-wrapper')
                raise AssertionError(selector)
            def get_by_role(self,role,**kwargs):
                if (role,kwargs)!=('button',{'name':'Update Event','exact':True}):raise AssertionError((role,kwargs))
                return Control('update')
        dialog=Dialog('dialog')
        class Keyboard:
            def press(self,key):
                if key!='Escape':raise AssertionError(key)
                log.append(('escape',))
        class Page:
            keyboard=Keyboard()
            def get_by_role(self,role,**kwargs):
                if (role,kwargs)!=('option',{'name':'Live Room','exact':True}):raise AssertionError((role,kwargs))
                return Control('option')
            def reload(self,**kwargs):
                log.append(('reload',));state['reloaded']=True
                if corrupt_after:state['form']['description']='Unexpected saved copy'
        def form(_):
            result=deepcopy(state['form'])
            if preflight_drift and not state['reloaded']:result['title']='Unexpected before write'
            return result
        def view(_):
            result=deepcopy(data['expected']['view'])
            if state['reloaded']:result.update(location_text=ROOM,location_url=ROOM_URL)
            return result
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def click(control):
                if control.label=='option':
                    journal=json.loads((root/events._JOURNAL).read_text())
                    if journal['status']!='ROOM_GENERATION_INTENT_RECORDED':
                        raise AssertionError('Room generation occurred before intent was durable')
                    state['form'].update(location_type='Live Room',location_url=ROOM_URL)
                elif control.label=='update':state['saved']=True
                elif control.label!='select':raise AssertionError(control.label)
                log.append(('click',control.label))
            def wait(fn,message):
                for _ in range(3):
                    if fn():return
                raise Stop(message)
            with ExitStack() as stack:
                for name,kwargs in (
                    ('evidence_lease',{'side_effect':lambda *_a,**_k:nullcontext(root)}),
                    ('_check_context',{}),('_open_view',{'return_value':object()}),
                    ('_read_view',{'side_effect':view}),('_open_edit',{'return_value':dialog}),
                    ('_read_form',{'side_effect':form}),
                    ('_next',{'side_effect':lambda _:log.append(('next',))}),
                    ('_back',{'side_effect':lambda _:log.append(('back',))}),
                    ('_read_fee',{'return_value':{'free':True,'price':'','currency':'USD','test_mode':'false','test_mode_disabled':True}}),
                    ('click',{'side_effect':click}),('wait_until',{'side_effect':wait}),
                ):stack.enter_context(patch.object(events,name,**kwargs))
                try:result=events.run_event(Page(),data,root,portal_context=object())
                except Stop as exc:result=exc
                journal=json.loads((root/events._JOURNAL).read_text()) if (root/events._JOURNAL).exists() else None
                if isinstance(result,dict):
                    replay=events.run_event(Page(),data,root,portal_context=object())
                    self.assertTrue(replay['replayed'])
            return result,log,journal,state,data

    def test_room_generation_intent_precedes_click_then_one_update_and_independent_reopen(self):
        result,log,journal,state,_=self.exercise()
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['room_id'],ROOM)
        self.assertEqual(log.count(('click','option')),1)
        self.assertEqual(log.count(('click','update')),1)
        self.assertTrue(state['saved'])
        self.assertTrue(state['reloaded'])
        self.assertEqual(journal['status'],'NEEDS_VERIFICATION')
        self.assertFalse(result['meeting_started'])
        self.assertFalse(result['event_created'])
        self.assertFalse(result['announcement_attempted'])
        self.assertFalse(result['email_reminders_enabled'])
        self.assertFalse(result['notification_behavior_verified'])
        self.assertNotIn('Existing approved description',str(result))

    def test_existing_room_noop_creates_no_room_and_updates_no_event(self):
        result,log,_,state,_=self.exercise(reused=True)
        self.assertTrue(result['reused'])
        self.assertFalse(result['room_creation_attempted'])
        self.assertFalse(any(item[0]=='click' for item in log))
        self.assertFalse(state['saved'])
        self.assertTrue(state['reloaded'])

    def test_protected_metadata_drift_stops_before_any_room_generation(self):
        result,log,journal,_,_=self.exercise(preflight_drift=True)
        self.assertIsInstance(result,Stop)
        self.assertIsNone(journal)
        self.assertFalse(any(item[0]=='click' for item in log))

    def test_failed_saved_readback_retains_uncertain_journal_without_retry(self):
        result,log,journal,_,_=self.exercise(corrupt_after=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual(journal['status'],'RECONCILIATION_REQUIRED')
        self.assertEqual(log.count(('click','option')),1)
        self.assertEqual(log.count(('click','update')),1)

    def test_replay_rejects_incomplete_forged_or_cross_event_receipts(self):
        data=inputs()
        base={'schema':events._SCHEMA,'configuration_sha256':events.configuration_hash(data),
            'location_id':'loc','group_id':'group','event_id':'event','status':'NEEDS_VERIFICATION',
            'outcome':events._receipt(data,ROOM,changed=True)}
        mutations=(
            lambda v:v.update(status='ROOM_GENERATION_INTENT_RECORDED'),
            lambda v:v.update(event_id='foreign'),
            lambda v:v.update(group_id='foreign'),
            lambda v:v['outcome'].update(reused=True),
            lambda v:v['outcome'].update(room_id='guessed'),
            lambda v:v['outcome'].update(email_reminders_enabled=True),
            lambda v:v['outcome'].update(functional_verified=True),
            lambda v:v['outcome'].update(independent_readback='PENDING'),
        )
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'journal.json'
            for index,mutate in enumerate(mutations):
                state=deepcopy(base);mutate(state);path.write_text(json.dumps(state))
                with self.subTest(index=index),self.assertRaises(Stop):events._replay(path,data)

    def test_json_context_is_not_live_same_session_identity(self):
        with self.assertRaises(Stop):events._check_context(object(),inputs(),{'authenticated':True},lambda:1)


class EventPortalBindingTests(unittest.TestCase):
    def test_native_pencil_signature_cannot_click_adjacent_trash_control(self):
        clicked=[]
        class Control:
            def __init__(self,label,tag='div'):self.label,self.tag=label,tag
            def count(self):return 1
            def is_visible(self):return True
            def evaluate(self,script):return self.tag
        edit=Control('edit')
        trash=Control('trash')
        class Svg(Control):
            def locator(self,selector):
                if selector!='..':raise AssertionError(selector)
                return edit
        svg=Svg('pencil','svg')
        class Path:
            def __init__(self,d,parent):self.d,self.parent=d,parent
            def get_attribute(self,key):
                if key!='d':raise AssertionError(key)
                return self.d
            def locator(self,selector):
                if selector!='..':raise AssertionError(selector)
                return self.parent
        class Paths:
            values=[Path('trash-path',trash),Path(events._PENCIL,svg)]
            def count(self):return len(self.values)
            def nth(self,i):return self.values[i]
        class View:
            def locator(self,selector):
                if selector!='path':raise AssertionError(selector)
                return Paths()
        class Dialog(Control):
            def wait_for(self,**kwargs):pass
            def get_attribute(self,key):return 'event-create-modal' if key=='id' else None
        dialog=Dialog('dialog')
        class Page:
            def get_by_role(self,role,**kwargs):
                if (role,kwargs)!=('dialog',{'name':'Edit Event Event Payment Details','exact':True}):
                    raise AssertionError((role,kwargs))
                return dialog
        with patch.object(events,'click',side_effect=clicked.append):
            self.assertIs(events._open_edit(Page(),View()),dialog)
        self.assertEqual(clicked,[edit])
        self.assertNotIn(trash,clicked)

    def test_context_is_same_page_same_group_fresh_and_rechecks_current_user(self):
        data=inputs()
        class Visible:
            def count(self):return 1
            def nth(self,i):return self
            def is_visible(self):return True
        class Missing:
            def count(self):return 0
        class Page:
            url=events._events_url(data)
            def get_by_placeholder(self,name,exact=True):return Missing()
            def get_by_text(self,name,exact=True):return Visible()
        page=Page()
        origin,slug=events.portal._portal(data['portal_url'])
        facts={'authenticated':True,'source_kind':'same_session_authenticated_read',
            'location_id':'loc','portal_origin':origin,'group_slug':slug,
            'group_id':'group','group_name':data['group_name'],'user_id':'fixture-user'}
        reader=lambda current:dict(facts)
        context=events.capture_context(page,data,identity_reader=reader,clock=lambda:10)
        events._check_context(page,data,context,lambda:11)
        with self.assertRaises(Stop):events._check_context(Page(),data,context,lambda:11)
        with self.assertRaises(Stop):events._check_context(page,data,context,lambda:400)
        facts['user_id']='different-user'
        with self.assertRaises(Stop):events._check_context(page,data,context,lambda:11)


class EventStableViewTests(unittest.TestCase):
    def test_waits_for_complete_link_and_two_consistent_metadata_reads(self):
        expected=deepcopy(inputs()['expected']['view'])
        expected.update(location_url=ROOM_URL)
        transient={**expected,'location_text':ROOM,'location_url':None}
        complete={**expected,'location_text':ROOM_URL}
        observations=iter([transient,complete,complete])
        results=[]
        def wait(fn,message):
            for _ in range(3):
                results.append(fn())
                if results[-1]:return
            raise Stop(message)
        with patch.object(events,'_read_view',side_effect=lambda _:next(observations)), \
                patch.object(events,'wait_until',side_effect=wait):
            self.assertEqual(events._wait_view(object(),expected,room_id=ROOM),complete)
        self.assertEqual(results,[False,False,True])


class EventGeneratedRoomHydrationTests(unittest.TestCase):
    def test_old_nonempty_other_link_is_not_generated_room_proof(self):
        data=inputs()
        old={**data['expected']['form'],'location_type':'Live Room'}
        generated={**old,'location_url':ROOM_URL}
        values=iter([old,generated,generated])
        results=[]
        class Field:
            def locator(self,selector):
                if selector!='input':raise AssertionError(selector)
                return self
            def count(self):return 1
            def is_enabled(self):return False
        class Dialog:
            def locator(self,selector):
                if selector!='#event-form-location-url':raise AssertionError(selector)
                return Field()
        def wait(fn,message):
            for _ in range(3):
                results.append(fn())
                if results[-1]:return
            raise Stop(message)
        with patch.object(events,'_read_form',side_effect=lambda _:next(values)), \
                patch.object(events,'wait_until',side_effect=wait):
            self.assertEqual(events._wait_generated_room(Dialog(),data),generated)
        self.assertEqual(results,[False,False,True])
