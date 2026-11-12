"""Read-only co-host capture boundaries; never client assignment proof."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import meeting_cohosts as cohosts
import meetings


def inputs():
    person = {'name':'Fixture Person','email':'fixture@example.invalid'}
    return {'location_id':'loc','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/loc/dashboard',
        'name':'Fixture room','slug':'fixture-room','waiting_room':True,
        'guest_users':False,'open_room':False,'allow_creation':False,
        'expected_room_id':'https://rooms.example/fixture-room',
        'cohosts':{'expected':[person], 'desired':[]}}


class Text:
    def __init__(self, value): self.value = value
    def inner_text(self): return self.value


class Elements:
    def __init__(self, values): self.values = values
    def count(self): return len(self.values)
    def nth(self, index): return self.values[index]


class Candidate:
    def __init__(self, name, email): self.name, self.email = name, email
    def locator(self, selector):
        if selector != '.pr-members__candidate-content p':
            raise AssertionError('Uncaptured selector')
        return Elements([Text(self.name), Text(self.email)])
    def count(self): return 1
    def is_visible(self): return True
    def click(self): raise AssertionError('Read-only preflight must not assign')


class Dialog:
    def __init__(self, values): self.values = values
    def locator(self, selector):
        if selector != '.pr-members__menu-item':
            raise AssertionError('Uncaptured selector')
        return Elements(self.values)


class CoHostPreflightTests(unittest.TestCase):
    def test_roster_name_excludes_same_size_remove_button_paragraph(self):
        class Paragraph(Text):
            def count(self): return 1
            def is_visible(self): return True
        class Button:
            def count(self): return 1
            def is_visible(self): return True
            def is_enabled(self): return True
        name = Paragraph('Fixture Person')
        email = Paragraph('fixture@example.invalid')
        remove_label = Paragraph('')
        class Row:
            def locator(self, selector):
                if selector == 'p.hr-text-lg':
                    return Elements([name,remove_label])  # broad old lookup is ambiguous
                if selector == 'p.hr-text-lg.hr-text-medium': return name
                if selector == 'p.hr-text-md': return email
                raise AssertionError('Uncaptured roster selector')
            def get_by_text(self, text, exact=True):
                if text != 'Co-host': raise AssertionError('Uncaptured role')
                return Paragraph('Co-host')
            def get_by_role(self, role, name=None, exact=True):
                if role != 'button' or name not in (None,'Delete'):
                    raise AssertionError('Uncaptured row button')
                return Button()
        row = Row()
        class Card:
            def count(self): return 1
            def is_visible(self): return True
            def locator(self, selector):
                if selector != '.pr-members__rows > div':
                    raise AssertionError('Uncaptured row selector')
                return Elements([row])
        class Editor:
            def locator(self, selector):
                if selector != '#create-room-members-card':
                    raise AssertionError('Uncaptured card selector')
                return Card()
        self.assertEqual(row.locator('p.hr-text-lg').count(),2)
        self.assertEqual(cohosts.read_roster(Editor()),inputs()['cohosts']['expected'])

    def test_addition_search_fills_input_inside_div_wrapper_without_assignment(self):
        data = inputs()
        data['cohosts']['desired'] = [*data['cohosts']['expected'],
            {'name':'Another Fixture','email':'another@example.invalid'}]
        observed = {**data, 'status':'PRESENT','source':'fixture native read',
                    'room_id':data['expected_room_id'], 'url':data['expected_room_id']}
        actions = []
        class Visible:
            def count(self): return 1
            def is_visible(self): return True
            def is_enabled(self): return True
            def get_attribute(self,name):return 'personal-room-co-hosts-1' if name=='aria-controls' else None
        class Input(Visible):
            def get_attribute(self, name):
                return 'Search users' if name == 'placeholder' else None
            def fill(self, value): actions.append(('search',value))
        search = Input()
        class Wrapper(Visible):
            def get_attribute(self, name): return None  # actual DIV, not input
            def get_by_role(self, role, *, name, exact):
                if (role,name,exact) != ('textbox','Search users',True):
                    raise AssertionError('Search must use captured nested textbox')
                return search
            def fill(self, value): raise AssertionError('Cannot fill DIV wrapper')
        wrapper = Wrapper()
        class Popup(Visible):
            def filter(self, **kwargs): return self
            def get_attribute(self, name):
                return 'personal-room-co-hosts-1-title' if name == 'aria-labelledby' else None
            def get_by_text(self, text, exact=True):
                if text != 'Add co-host': raise AssertionError('Unexpected title')
                return Visible()
            def locator(self, selector):
                if selector != '#personal-room-co-host-search':
                    raise AssertionError('Unexpected search wrapper selector')
                return wrapper
        popup = Popup()
        trigger = Visible()
        class Editor(Visible):
            def locator(self, selector):
                if selector == '#create-room-members-card': return self
                if selector == '.pr-members__add-trigger--link': return trigger
                raise AssertionError('Unexpected co-host card selector')
        class Page:
            def get_by_text(self, text, exact=True): return text
            def get_by_role(self, role):
                if role != 'dialog': raise AssertionError('Unexpected role')
                return popup
            def locator(self, selector):
                if selector != '#personal-room-co-host-search':
                    raise AssertionError('Unexpected dialog anchor')
                return wrapper
        def click(control):
            if control == 'Edit settings': actions.append(('open','edit'))
            elif control is trigger: actions.append(('open','directory'))
            else: raise AssertionError('Read-only preflight cannot assign/remove/save')
        with patch.object(cohosts,'assert_tenant'), patch.object(cohosts,'navigate'), \
             patch.object(meetings,'read_room',return_value=observed), \
             patch.object(cohosts,'click',side_effect=click), \
             patch.object(cohosts,'fill',side_effect=lambda control,value:control.fill(value)), \
             patch.object(cohosts,'_editor',return_value=Editor()), \
             patch.object(cohosts,'read_roster',return_value=data['cohosts']['expected']), \
             patch.object(cohosts,'_candidate',return_value=Visible()):
            result = cohosts.prepare(Page(),data)
        self.assertEqual(actions,[('open','edit'),('open','directory'),('search','another@example.invalid')])
        self.assertEqual(result['addition_count'],1)
        self.assertFalse(result['assignment_supported'])

    def test_malformed_rosters_stop_before_browser_access(self):
        mutations = [
            {'expected':[], 'desired':[{'name':'Fixture Person'}]},
            {'expected':[], 'desired':[{'name':'Fixture Person','email':'bad'}]},
            {'expected':[], 'desired':[{'name':'Fixture Person','email':'fixture@example.invalid', 'user_id':'guessed'}]},
            {'expected':[], 'desired':[], 'approved':True},
        ]
        for configuration in mutations:
            with self.subTest(configuration=configuration), self.assertRaises(meetings.Stop):
                cohosts.prepare(object(), {**inputs(), 'cohosts':configuration})

    def test_duplicate_email_case_is_not_two_people(self):
        data = inputs()
        data['cohosts']['desired'] = [
            {'name':'First','email':'fixture@example.invalid'},
            {'name':'Second','email':'FIXTURE@example.invalid'}]
        with self.assertRaises(meetings.Stop): cohosts.validate_inputs(data)

    def test_hash_binds_exact_expected_roster_and_requested_room(self):
        original = inputs()
        changed = deepcopy(original)
        changed['cohosts']['expected'][0]['name'] = 'Different Fixture'
        self.assertNotEqual(cohosts.configuration_hash(original), cohosts.configuration_hash(changed))
        changed = deepcopy(original)
        changed['expected_room_id'] = 'https://different.example/fixture-room'
        self.assertNotEqual(cohosts.configuration_hash(original), cohosts.configuration_hash(changed))

    def test_candidate_requires_both_exact_name_and_email_and_uniqueness(self):
        wanted = inputs()['cohosts']['expected'][0]
        candidate = Candidate(wanted['name'],wanted['email'])
        same_name = Candidate(wanted['name'],'different@example.invalid')
        same_email = Candidate('Different Person',wanted['email'])
        self.assertIs(cohosts._candidate(Dialog([same_name,candidate,same_email]), wanted), candidate)
        self.assertIsNone(cohosts._candidate(Dialog([same_name,same_email]), wanted))
        self.assertIsNone(cohosts._candidate(Dialog([candidate,candidate]), wanted))

    def test_mismatched_roster_stops_without_selection_removal_or_save(self):
        data = inputs()
        observed = {**data, 'status':'PRESENT','source':'fixture native read',
                    'room_id':data['expected_room_id'], 'url':data['expected_room_id']}
        clicked = []
        class Page:
            def get_by_text(self, text, exact=True): return text
        with patch.object(cohosts,'assert_tenant'), patch.object(cohosts,'navigate'), \
             patch.object(meetings,'read_room',return_value=observed), \
             patch.object(cohosts,'click',side_effect=clicked.append), \
             patch.object(cohosts,'_editor',return_value=object()), \
             patch.object(cohosts,'read_roster',return_value=[]), \
             self.assertRaises(meetings.Stop):
            cohosts.prepare(Page(),data)
        self.assertEqual(clicked,['Edit settings'])

    def test_removal_plan_is_explicitly_read_only_and_never_runs_remove(self):
        data = inputs()
        observed = {**data, 'status':'PRESENT','source':'fixture native read',
                    'room_id':data['expected_room_id'], 'url':data['expected_room_id']}
        clicked = []
        class Page:
            def get_by_text(self, text, exact=True): return text
        with patch.object(cohosts,'assert_tenant'), patch.object(cohosts,'navigate'), \
             patch.object(meetings,'read_room',return_value=observed), \
             patch.object(cohosts,'click',side_effect=clicked.append), \
             patch.object(cohosts,'_editor',return_value=object()), \
             patch.object(cohosts,'read_roster',return_value=data['cohosts']['expected']):
            result = cohosts.prepare(Page(),data)
        self.assertEqual(result['status'],'COHOST_PREFLIGHT_ONLY')
        self.assertEqual(result['removal_count'],1)
        self.assertFalse(result['mutation_attempted'])
        self.assertFalse(result['assignment_supported'])
        self.assertEqual(clicked,['Edit settings'])


if __name__ == '__main__': unittest.main()


class CoHostWriterTests(unittest.TestCase):
    def writer_inputs(self):
        data = inputs()
        data['cohosts']['desired'] = [{'name':'Added Fixture','email':'added@example.invalid'}]
        data['cohosts']['access_change_acknowledged'] = True
        return data

    def test_writer_requires_explicit_complete_scoped_plan_before_browser(self):
        data = self.writer_inputs()
        for config in (
            {'expected':[], 'desired':[]},
            {**data['cohosts'], 'access_change_acknowledged':False},
            {**data['cohosts'], 'access_change_acknowledged':'true'},
            {**data['cohosts'], 'unknown':True},
        ):
            with self.subTest(config=config), self.assertRaises(meetings.Stop):
                cohosts.configure(object(), {**data,'cohosts':config})

    def test_hash_binds_origin_expected_desired_security_and_acknowledgment(self):
        data = self.writer_inputs()
        original = cohosts.write_configuration_hash(data)
        mutations = [
            lambda v:v.update(start_url='https://different.invalid/v2/location/loc/dashboard'),
            lambda v:v.update(guest_users=True),
            lambda v:v['cohosts']['expected'][0].update(name='Another exact name'),
            lambda v:v['cohosts']['desired'][0].update(email='another@example.invalid'),
        ]
        for mutate in mutations:
            changed = deepcopy(data)
            mutate(changed)
            self.assertNotEqual(original,cohosts.write_configuration_hash(changed))

    def exercise(self, *, persisted_override=None, candidate_absent=False, drift=False, no_change=False, empty_before=False, clear_all=False):
        from contextlib import ExitStack
        data = self.writer_inputs()
        if empty_before:
            data['cohosts']['expected'] = []
        if clear_all:
            data['cohosts']['desired'] = []
        if no_change:
            data['cohosts']['desired'] = deepcopy(data['cohosts']['expected'])
        events = []
        state = {'staged':deepcopy(data['cohosts']['expected']),
                 'persisted':deepcopy(data['cohosts']['expected']), 'opens':0}
        class Visible:
            def count(self): return 1
            def is_visible(self): return True
            def is_enabled(self): return True
            def wait_for(self, **kwargs): events.append(('wait',kwargs['state']))
        class Editor(Visible):
            def get_by_role(self, role, name, exact):
                if (role,name,exact) != ('button','Save changes',True):
                    raise AssertionError('Unexpected writer control')
                return save
        editor, dialog, search, candidate, remove, save = (Editor(),Visible(),Visible(),Visible(),Visible(),Visible())
        class Empty:
            def count(self): return 0
        class Page:
            url = 'https://app.convertandflow.com/v2/location/loc/meetings/personal-room'
            def goto(self,url,**kwargs):
                if url != self.url: raise AssertionError('Unexpected navigation')
                events.append(('discard-or-close',))
            def get_by_role(self,role):
                if role != 'dialog': raise AssertionError('Unexpected page role')
                return Empty()
        page = Page()
        def opened(page,data):
            state['opens'] += 1
            state['staged'] = deepcopy(state['persisted'])
            if drift and state['opens'] == 2:
                state['staged'] = []
            if persisted_override is not None and state['opens'] == 3:
                state['staged'] = deepcopy(persisted_override)
            events.append(('open',state['opens']))
            return editor,page.url
        def find(dialog,search,person):
            events.append(('candidate',person['email']))
            if candidate_absent: raise meetings.Stop('Fixture candidate absent')
            return candidate
        def click(control):
            if control is remove:
                events.append(('remove',))
                state['staged'] = [entry for entry in state['staged']
                    if entry != data['cohosts']['expected'][0]]
            elif control is candidate:
                events.append(('add',))
                state['staged'].append(deepcopy(data['cohosts']['desired'][0]))
            elif control is save:
                events.append(('save',))
                state['persisted'] = deepcopy(state['staged'])
            else: raise AssertionError('Unexpected click')
        def wait(fn,message):
            if not fn(): raise meetings.Stop(message)
        with ExitStack() as stack:
            for name,kwargs in (
                ('assert_tenant',{}), ('_open_existing',{'side_effect':opened}),
                ('_editor',{'return_value':editor}),
                ('read_roster',{'side_effect':lambda _,**kwargs:deepcopy(state['staged'])}),
                ('_open_directory',{'return_value':(dialog,search)}),
                ('_find_candidate',{'side_effect':find}),
                ('_remove_control',{'return_value':remove}),
                ('click',{'side_effect':click}), ('wait_until',{'side_effect':wait}),
            ):
                stack.enter_context(patch.object(cohosts,name,**kwargs))
            try:
                result = cohosts.configure(page,data)
            except meetings.Stop as exc:
                result = exc
        return result,events,state,data

    def test_complete_preflight_precedes_any_access_write_then_single_save_and_reopen(self):
        result,events,state,data = self.exercise()
        self.assertIsInstance(result,dict)
        self.assertEqual(result['status'],'COHOSTS_SAVED_AND_REOPENED')
        self.assertEqual(state['persisted'],data['cohosts']['desired'])
        self.assertEqual(events.count(('save',)),1)
        self.assertLess(events.index(('candidate','added@example.invalid')),events.index(('remove',)))
        self.assertLess(events.index(('add',)),events.index(('remove',)))
        self.assertEqual(state['opens'],3)
        self.assertEqual(result['independent_readback'],'VERIFIED')
        self.assertFalse(result['meeting_started'])
        self.assertFalse(result['functional_verified'])
        self.assertFalse(result['notification_behavior_verified'])
        self.assertNotIn('added@example.invalid',str(result))

    def test_absent_candidate_stops_before_remove_add_or_save(self):
        result,events,_,_ = self.exercise(candidate_absent=True)
        self.assertIsInstance(result,meetings.Stop)
        self.assertFalse(any(event[0] in ('remove','add','save') for event in events))

    def test_roster_drift_after_directory_preflight_stops_before_access_write(self):
        result,events,_,_ = self.exercise(drift=True)
        self.assertIsInstance(result,meetings.Stop)
        self.assertFalse(any(event[0] in ('remove','add','save') for event in events))

    def test_reopen_roster_loss_is_uncertain_not_success_or_second_save(self):
        result,events,_,_ = self.exercise(persisted_override=[])
        self.assertIsInstance(result,meetings.Stop)
        self.assertEqual(events.count(('save',)),1)

    def test_exact_noop_reopens_without_access_writes_or_save(self):
        result,events,state,_ = self.exercise(no_change=True)
        self.assertEqual(result['status'],'COHOSTS_REUSED_AND_REOPENED')
        self.assertFalse(any(event[0] in ('candidate','remove','add','save') for event in events))
        self.assertEqual(state['opens'],2)


class CoHostEmptyStateTests(unittest.TestCase):
    def test_nonempty_snapshot_cannot_race_into_an_unproved_empty_roster(self):
        from unittest.mock import MagicMock
        editor,card,rows=(MagicMock() for _ in range(3))
        editor.locator.return_value=card
        card.count.return_value=1;card.is_visible.return_value=True
        card.locator.return_value=rows;rows.count.side_effect=[1,0]
        with self.assertRaisesRegex(meetings.Stop,'changed during'):
            cohosts.read_roster(editor)
        rows.nth.assert_not_called()

    def test_zero_rows_are_unknown_not_an_authoritative_empty_roster(self):
        class Card:
            def count(self): return 1
            def is_visible(self): return True
            def locator(self, selector):
                if selector != '.pr-members__rows > div': raise AssertionError(selector)
                return Elements([])
        class Editor:
            def locator(self, selector):
                if selector != '#create-room-members-card': raise AssertionError(selector)
                return Card()
        with self.assertRaisesRegex(meetings.Stop, 'loaded-empty'):
            cohosts.read_roster(Editor())

    def test_explicit_empty_plans_bind_first_assignment_clear_all_and_acknowledgment(self):
        data = CoHostWriterTests().writer_inputs()
        digests = set()
        for key in ('expected', 'desired'):
            value = deepcopy(data)
            value['cohosts'][key] = []
            with self.subTest(key=key):
                self.assertEqual(cohosts.validate_write_inputs(value)['cohosts'][key], [])
                digests.add(cohosts.write_configuration_hash(value))
                value['cohosts']['access_change_acknowledged'] = False
                with self.assertRaisesRegex(meetings.Stop, 'acknowledgment'):
                    cohosts.validate_write_inputs(value)
        self.assertEqual(len(digests), 2)

    def test_captured_first_assignment_and_clear_all_save_once_and_reopen(self):
        for option in ('empty_before','clear_all'):
            result,events,state,data=CoHostWriterTests().exercise(**{option:True})
            with self.subTest(option=option):
                self.assertIsInstance(result,dict)
                self.assertEqual(result['status'],'COHOSTS_SAVED_AND_REOPENED')
                self.assertEqual(state['persisted'],data['cohosts']['desired'])
                self.assertEqual(events.count(('save',)),1)
                self.assertEqual(result['cohost_count'],len(data['cohosts']['desired']))

    def empty_surface(self, *, busy=False, disabled=False, notice=False, counts=None, wrapper=False):
        from unittest.mock import MagicMock
        page,editor,card,body,add,rows,container,heading,unsafe=(MagicMock() for _ in range(9))
        page.url='https://app.convertandflow.com/v2/location/loc/meetings/personal-room/edit'
        editor.get_attribute.return_value=None
        editor.locator.side_effect=lambda selector:card if selector=='#create-room-members-card' else unsafe
        unsafe.count.return_value=int(notice)
        card.count.return_value=body.count.return_value=heading.count.return_value=1
        card.is_visible.return_value=body.is_visible.return_value=heading.is_visible.return_value=True
        body.locator.return_value.count.return_value=1
        card.get_attribute.side_effect=lambda key:'true' if key=='aria-busy' and busy else None
        add.count.return_value=1;add.is_visible.return_value=True;add.is_enabled.return_value=not disabled
        add.inner_text.return_value=' Add'
        attributes={'type':'button','aria-haspopup':'dialog','aria-expanded':'false','aria-controls':'personal-room-co-hosts-2'}
        add.get_attribute.side_effect=attributes.get
        rows.count.side_effect=counts or [0]*10
        container.count.return_value=int(wrapper)
        card.locator.side_effect=lambda selector:{'.pr-members__rows > div':rows,'.pr-members__rows':container,
            '.pr-members__card':body,'.pr-members__add-trigger--link':add}[selector]
        card.get_by_role.return_value=heading
        data=CoHostWriterTests().writer_inputs();data['cohosts']['expected']=[]
        return page,editor,data

    def test_complete_captured_loaded_empty_card_after_owner_and_network_read_is_positive(self):
        page,editor,data=self.empty_surface()
        with patch.object(cohosts,'_editor',return_value=editor) as identity:
            self.assertEqual(cohosts.read_roster(editor,page=page,data=data),[])
        page.wait_for_load_state.assert_called_once_with('networkidle',timeout=45000)
        identity.assert_called_once_with(page,data)

    def test_stale_busy_error_disabled_unknown_wrapper_and_unstable_zero_never_authorize_empty(self):
        for reason in ('busy','disabled','notice','stale','unstable','owner','wrapper'):
            opts={reason:True} if reason in ('busy','disabled','notice','wrapper') else {}
            if reason=='unstable':opts['counts']=[0,0,1]
            page,editor,data=self.empty_surface(**opts)
            if reason=='stale':page.wait_for_load_state.side_effect=TimeoutError('still loading')
            effect=meetings.Stop('Wrong exact room owner') if reason=='owner' else None
            with self.subTest(reason=reason),patch.object(cohosts,'_editor',return_value=editor,side_effect=effect),self.assertRaises(meetings.Stop):
                cohosts.read_roster(editor,page=page,data=data)


class CapturedEmptyRosterReplay(unittest.TestCase):
    def test_current_empty_replay_reads_native_profile_and_stops_on_later_roster_drift(self):
        from unittest.mock import MagicMock
        done,_,_,data=CoHostWriterTests().exercise(clear_all=True)
        page,editor=MagicMock(),MagicMock()
        detail='https://app.convertandflow.com/v2/location/loc/meetings/personal-room'
        with patch.object(cohosts,'assert_tenant'),patch.object(cohosts,'_open_existing',return_value=(editor,detail)),\
             patch.object(cohosts,'read_roster',return_value=[]) as read,patch.object(cohosts,'click') as write:
            self.assertEqual(cohosts.verify_completed(page,data,done),done)
            read.assert_called_once_with(editor,page=page,data=data)
            read.return_value=deepcopy(data['cohosts']['expected'])
            with self.assertRaisesRegex(meetings.Stop,'roster changed'):cohosts.verify_completed(page,data,done)
            write.assert_not_called()

    def test_saved_zero_state_without_complete_card_never_authorizes_first_assignment(self):
        from unittest.mock import MagicMock
        page,editor,data=CoHostEmptyStateTests().empty_surface(wrapper=True)
        with patch.object(cohosts,'_editor',return_value=editor),self.assertRaises(meetings.Stop):
            cohosts.read_roster(editor,page=page,data=data)
        page.get_by_role.assert_not_called()


class CapturedPickerOwnerTests(unittest.TestCase):
    def test_picker_title_binds_actual_add_control_instance_instead_of_historical_suffix(self):
        from unittest.mock import MagicMock
        page,editor,card,trigger,dialog,wrapper,search=(MagicMock() for _ in range(7))
        editor.locator.return_value=card;card.locator.return_value=trigger
        trigger.get_attribute.return_value='personal-room-co-hosts-2'
        page.get_by_role.return_value=dialog;dialog.filter.return_value=dialog
        dialog.get_attribute.return_value='personal-room-co-hosts-2-title'
        dialog.locator.return_value=wrapper;wrapper.get_by_role.return_value=search
        search.get_attribute.return_value='Search users'
        for node in (card,trigger,dialog,wrapper,search,dialog.get_by_text.return_value):
            node.count.return_value=1;node.is_visible.return_value=True
        with patch.object(cohosts,'click') as click:
            self.assertEqual(cohosts._open_directory(page,editor),(dialog,search))
            click.assert_called_once_with(trigger)
            dialog.get_attribute.return_value='personal-room-co-hosts-1-title'
            with self.assertRaisesRegex(meetings.Stop,'dialog identity'):cohosts._open_directory(page,editor)
