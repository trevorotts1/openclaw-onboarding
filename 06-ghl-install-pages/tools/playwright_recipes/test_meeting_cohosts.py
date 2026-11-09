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
        class Editor:
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
