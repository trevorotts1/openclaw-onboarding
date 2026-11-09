"""Native dynamic calendar control contracts; no appointment/live acceptance."""
from copy import deepcopy
from contextlib import ExitStack
import time
import unittest
from unittest.mock import patch

import meeting_dynamic as dynamic
from skill6_playwright import Stop


def inputs():
    return {'location_id':'loc','location_name':'Fixture account',
        'start_url':'https://app.convertandflow.com/v2/location/loc/settings/calendars?section=calendars',
        'calendar_id':'calendar','calendar_name':'Fixture personal calendar','staff_id':'staff',
        'connection_staff_label':'Fixture Staff (Me)',
        'expected_staff_locations':[{'staff_id':'staff','staff_name':'Fixture Staff',
            'location_kind':'Custom','location_value':'https://example.invalid/current'}],
        'staff_dependency':{'status':'VERIFIED','provider':'skill44','location_id':'loc',
            'observed_at':time.time(),'operation':'users.search','http_status':200,'complete':True,'total_count':1,
            'users':[{'id':'staff','name':'Fixture Staff','roles':{'locationIds':['loc']}}]}}


class DynamicRoomTests(unittest.TestCase):
    def test_unsupported_or_unbound_input_stops_before_browser(self):
        mutations = (
            lambda v:v.update(staff_id='other'),
            lambda v:v.update(calendar_id='../other'),
            lambda v:v.update(start_url=v['start_url'].replace('/loc/','/other/')),
            lambda v:v.update(start_url=v['start_url']+'&token=private'),
            lambda v:v.update(connection_staff_label='Different Staff'),
            lambda v:v['staff_dependency'].update(observed_at=0),
            lambda v:v['staff_dependency'].update(observed_at=float('nan')),
            lambda v:v['staff_dependency'].update(observed_at=True),
            lambda v:v['staff_dependency'].update(http_status=True),
            lambda v:v['staff_dependency'].update(location_id='other'),
            lambda v:v['staff_dependency'].update(status='UNVERIFIED'),
            lambda v:v['staff_dependency'].update(operation='users.update'),
            lambda v:v['staff_dependency']['users'][0].update(id='other'),
            lambda v:v['staff_dependency']['users'][0].update(name='Other Staff'),
            lambda v:v['staff_dependency']['users'][0]['roles'].update(locationIds=['other']),
            lambda v:v['expected_staff_locations'].append(deepcopy(v['expected_staff_locations'][0])),
            lambda v:v['expected_staff_locations'][0].update(location_kind='Phone'),
            lambda v:v['expected_staff_locations'][0].update(location_kind='Meeting Room',location_value='old'),
            lambda v:v['staff_dependency'].update(complete=False),
            lambda v:v['staff_dependency'].update(total_count=2),
            lambda v:v['staff_dependency'].update(total_count=True),
            lambda v:v['staff_dependency'].update(users=[]),
            lambda v:v.update(appointment_created=False),
        )
        for index,mutate in enumerate(mutations):
            value = inputs()
            mutate(value)
            with self.subTest(index=index), self.assertRaises(Stop):
                dynamic.configure(object(),value)

    def test_hash_keeps_old_receipt_identity_but_expired_receipt_cannot_execute(self):
        value = inputs()
        value['staff_dependency']['observed_at'] = 0
        self.assertEqual(len(dynamic.configuration_hash(value)),64)
        with self.assertRaises(Stop): dynamic.validate_inputs(value)
        changed = deepcopy(value)
        changed['expected_staff_locations'][0]['location_value'] = 'https://example.invalid/changed'
        self.assertNotEqual(dynamic.configuration_hash(value),dynamic.configuration_hash(changed))

    def exercise(self, *, no_change=False, drift=False, failed_readback=False, option_disabled=False):
        data = inputs()
        if no_change:
            data['expected_staff_locations'][0].update(location_kind='Meeting Room',location_value='')
        state = {'value':deepcopy(data['expected_staff_locations'][0]),'persisted':deepcopy(data['expected_staff_locations'][0]),'opens':0}
        events = []
        class Control:
            def __init__(self,label): self.label=label
            def count(self): return 1
            def is_visible(self): return True
            def is_enabled(self): return not (self.label=='option' and option_disabled)
            def get_attribute(self,name): return None
            def filter(self,**kwargs): return self
            def wait_for(self,**kwargs): events.append(('wait',kwargs['state']))
        select,option,save = Control('select'),Control('option'),Control('save')
        class Frame:
            def locator(self,selector):
                if selector != '.n-base-select-option': raise AssertionError(selector)
                return option
            def get_by_text(self,label,exact=True): return Control(label)
            def get_by_role(self,role,**kwargs):
                if (role,kwargs) != ('button',{'name':'Save changes','exact':True}):
                    raise AssertionError((role,kwargs))
                return save
        frame = Frame()
        class Page:
            def goto(self,url,**kwargs): events.append(('goto',url))
        def opened(page,data):
            state['opens'] += 1
            state['value'] = deepcopy(state['persisted'])
            if drift and state['opens'] == 1:
                state['value']['location_value'] = 'https://example.invalid/foreign'
            if failed_readback and state['opens'] == 2:
                state['value']['location_kind'] = 'Custom'
                state['value']['location_value'] = 'https://example.invalid/not-saved'
            events.append(('open',state['opens']))
            return frame
        def click(control):
            events.append(('click',control.label))
            if control is option:
                state['value'].update(location_kind='Meeting Room',location_value='')
            elif control is save:
                state['persisted'] = deepcopy(state['value'])
        def wait(fn,message):
            if not fn(): raise Stop(message)
        with ExitStack() as stack:
            for name,kwargs in (
                ('_connected',{'side_effect':lambda p,d:events.append(('connection',d['staff_id']))}),
                ('_open_calendar',{'side_effect':opened}),('_editor_identity',{}),('_at',{}),
                ('_location_controls',{'side_effect':lambda f,d:(select,deepcopy(state['value']))}),
                ('click',{'side_effect':click}),('wait_until',{'side_effect':wait}),
            ):
                stack.enter_context(patch.object(dynamic,name,**kwargs))
            try: result = dynamic.configure(Page(),data)
            except Stop as exc: result = exc
        return result,events,state

    def test_exact_staff_change_saves_once_then_reopens_without_booking(self):
        result,events,state = self.exercise()
        self.assertEqual(result['status'],'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED')
        self.assertEqual(events.count(('click','save')),1)
        self.assertEqual(state['opens'],2)
        self.assertEqual(events[0],('connection','staff'))
        self.assertEqual(state['persisted']['location_kind'],'Meeting Room')
        self.assertFalse(result['appointment_created'])
        self.assertFalse(result['meeting_started'])
        self.assertFalse(result['dynamic_room_generation_verified'])
        self.assertFalse(result['functional_verified'])
        self.assertNotIn('https://example.invalid/current',str(result))

    def test_already_room_reopens_without_save_or_location_click(self):
        result,events,state = self.exercise(no_change=True)
        self.assertEqual(result['status'],'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED')
        self.assertFalse(any(item[0]=='click' for item in events))
        self.assertEqual(state['opens'],2)

    def test_prior_location_drift_stops_before_mutation(self):
        result,events,_ = self.exercise(drift=True)
        self.assertIsInstance(result,Stop)
        self.assertFalse(any(item[0]=='click' for item in events))

    def test_disabled_native_room_option_stops_before_selection_or_save(self):
        result,events,_ = self.exercise(option_disabled=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual([item for item in events if item[0]=='click'],[('click','select')])

    def test_failed_persistence_is_uncertain_not_success_or_second_write(self):
        result,events,_ = self.exercise(failed_readback=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual(events.count(('click','save')),1)

    def test_exact_route_does_not_accept_foreign_origin_tenant_or_credentials(self):
        class Page: pass
        value = inputs()
        expected='/settings/calendars'
        for url in (
            value['start_url'].replace('/loc/','/other/'),
            value['start_url'].replace('app.convertandflow.com','foreign.invalid'),
            value['start_url']+'&private=token',
        ):
            page = Page(); page.url=url
            with self.subTest(url=url), patch.object(dynamic,'assert_tenant') as tenant, self.assertRaises(Stop):
                dynamic._at(page,value,expected,'section=calendars')
            tenant.assert_not_called()


class NativeStaffLocationShapeTests(unittest.TestCase):
    def test_digit_prefixed_native_staff_ids_use_exact_attribute_selectors(self):
        data = inputs()
        data['staff_id'] = '8digitStaff'
        data['expected_staff_locations'][0]['staff_id'] = data['staff_id']
        class Visible:
            def count(self): return 1
            def is_visible(self): return True
        class Content(Visible):
            def inner_text(self): return 'Custom'
        class Value(Visible):
            def input_value(self): return data['expected_staff_locations'][0]['location_value']
        class Selected(Visible):
            def get_attribute(self,name):
                if name != 'title': raise AssertionError(name)
                return 'Custom'
            def locator(self,selector):
                if selector != '.n-base-selection-input__content': raise AssertionError(selector)
                return Content()
        class Wrapper(Visible):
            def locator(self,selector):
                expected='[id="8digitStaff-team-member-delete"]'
                if selector not in (expected,'#add-location-btn'): raise AssertionError(selector)
                return Visible()
            def get_by_role(self,role,**kwargs):
                if (role,kwargs) != ('textbox',{'name':'Meeting location','exact':True}):
                    raise AssertionError((role,kwargs))
                return Value()
            def get_by_text(self,name,exact=True):
                if (name,exact) != ('Add display label',True): raise AssertionError(name)
                return Visible()
        wrapper=Wrapper()
        class Parent:
            def __init__(self,depth): self.depth=depth
            def locator(self,selector):
                if selector != '..': raise AssertionError(selector)
                return wrapper if self.depth==3 else Parent(self.depth+1)
        class Select(Visible):
            def locator(self,selector):
                if selector=='..': return Parent(1)
                if selector=='.n-base-selection-input[title]': return Selected()
                raise AssertionError(selector)
        select=Select()
        class Frame:
            def locator(self,selector):
                if selector=='[id$="-calendar-team-member-meeting-location-select"]': return Visible()
                if selector=='[id="8digitStaff-calendar-team-member-meeting-location-select"]': return select
                raise AssertionError('Uncaptured or unsafe ID selector: '+selector)
        control,record=dynamic._location_controls(Frame(),data)
        self.assertIs(control,select)
        self.assertEqual(record,data['expected_staff_locations'][0])


class StaffInventoryAmbiguityTests(unittest.TestCase):
    def test_same_named_staff_never_bind_connections_to_one_opaque_id(self):
        for other_name in ('Fixture Staff','fixture staff'):
            data=inputs()
            data['staff_dependency']['users'].append({'id':'other', 'name':other_name,
                'roles':{'locationIds':['loc']}})
            data['staff_dependency']['total_count']=2
            with self.subTest(name=other_name), self.assertRaisesRegex(Stop,'ambiguous'):
                dynamic.configure(object(),data)

    def test_duplicate_api_ids_and_foreign_members_are_refused(self):
        for other in (
            {'id':'staff','name':'Other Staff','roles':{'locationIds':['loc']}},
            {'id':'other','name':'Other Staff','roles':{'locationIds':['foreign']}},
        ):
            data=inputs()
            data['staff_dependency']['users'].append(other)
            data['staff_dependency']['total_count']=2
            with self.subTest(other=other), self.assertRaises(Stop):
                dynamic.configure(object(),data)

    def test_complete_inventory_can_include_other_distinct_staff(self):
        data=inputs()
        data['staff_dependency']['users'].append({'id':'other','name':'Other Staff',
            'roles':{'locationIds':['loc']}})
        data['staff_dependency']['total_count']=2
        self.assertEqual(dynamic.validate_inputs(data)['staff_id'],'staff')
