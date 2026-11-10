"""Native scheduling request boundaries, independent of client/browser state."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import form_schedule as schedule
from skill6_playwright import Stop, FORM_SETTINGS


def spec():
    return {'action':'native_form_schedule', 'schedule':{
        'enabled':True, 'time_zone':'America/New_York',
        'opens':{'mode':'at','date':'2030-01-15','time':'09:00'},
        'closes':{'mode':'at','date':'2030-01-16','time':'17:00'}}}


class ScheduleValidationTests(unittest.TestCase):
    def test_exact_local_dates_and_zone_are_preserved_without_mutating_input(self):
        value = spec()
        result = schedule.validate(value)
        self.assertEqual(result, value)
        result['schedule']['opens']['date'] = '2030-02-01'
        self.assertEqual(value['schedule']['opens']['date'], '2030-01-15')

    def test_disabled_and_unbounded_windows_are_explicit(self):
        self.assertEqual(schedule.validate({'schedule':{'enabled':False}}),
                         {'schedule':{'enabled':False}})
        value = spec()
        value['schedule'].update(opens={'mode':'immediate'}, closes={'mode':'never'})
        self.assertEqual(schedule.validate(value), value)

    def test_unknown_missing_and_ignored_fields_refuse(self):
        cases = [None, {}, {'schedule':{}}, {'schedule':{'enabled':'true'}},
                 {'schedule':{'enabled':False,'time_zone':'UTC'}},
                 {'schedule':{'enabled':False},'publish':True}]
        for key in ('time_zone','opens','closes'):
            value = spec()
            del value['schedule'][key]
            cases.append(value)
        for key in ('dates','timezone','notifications'):
            value = spec();value['schedule'][key] = 'ignored'
            cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)

    def test_invalid_calendar_dates_times_zones_and_endpoint_modes_refuse(self):
        for zone in ('', 'Unknown/City', '../UTC', 1):
            value = spec();value['schedule']['time_zone'] = zone
            with self.subTest(zone=zone), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)
        for key, invalid in (('date','2030-02-29'), ('date','20300115'),
                             ('time','24:00'), ('time','09:60'), ('time','9:00')):
            value = spec();value['schedule']['opens'][key] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)
        for endpoint in ({'mode':'tomorrow'}, {'mode':'immediate','time':'09:00'},
                         {'mode':'at','date':'2030-01-15','time':'09:00','offset':'-05:00'}):
            value = spec();value['schedule']['opens'] = endpoint
            with self.subTest(endpoint=endpoint), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)

    def test_reversed_or_equal_closing_time_refuses(self):
        for day, clock in (('2030-01-14','09:00'), ('2030-01-15','09:00')):
            value = spec();value['schedule']['closes'].update(date=day,time=clock)
            with self.subTest(day=day,clock=clock), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)

    def test_dst_gap_and_fold_are_not_guessed(self):
        for day, clock in (('2030-03-10','02:30'), ('2030-11-03','01:30')):
            value = spec();value['schedule'].update(closes={'mode':'never'})
            value['schedule']['opens'].update(date=day,time=clock)
            with self.subTest(day=day), self.assertRaisesRegex(schedule.ScheduleError,'ambiguous or nonexistent'):
                schedule.validate(value)

    def test_outside_settings_must_be_authored_and_exclusive(self):
        value = spec();value['schedule']['before'] = {'mode':'redirect','url':'https://example.com/before'}
        value['schedule']['after'] = {'mode':'message','message':'Closed for now.\nPlease return later.'}
        self.assertEqual(schedule.validate(value), value)
        for outside in ({'mode':'redirect','url':'http://example.com'},
                        {'mode':'redirect','url':'https://user:secret@example.com'},
                        {'mode':'redirect','url':'https://example.com','message':'ignored'},
                        {'mode':'message','message':''}, {'mode':'message','message':'x\x00y'},
                        {'mode':'page','html':'<p>unobserved native feature</p>'}):
            value = spec();value['schedule']['before'] = outside
            with self.subTest(outside=outside), self.assertRaises(schedule.ScheduleError):
                schedule.validate(value)


class Control:
    def __init__(self, page, kind, index=None):
        self.page, self.kind, self.index = page, kind, index

    def count(self):
        return 0 if self.kind == 'absent' else 1

    def get_by_role(self, *_args, **_kwargs):
        return Control(self.page, 'absent')

    def wait_for(self, **_kwargs):
        if not self.count():
            raise Stop('Native fixture control missing')

    def is_visible(self):return bool(self.count())
    def is_enabled(self):return True
    def input_value(self):return self.page.name

    def key(self):
        if self.index == 0:return 'enabled'
        if self.page.current['enabled'] and self.index == 1:return 'agency_branding'
        index = self.index - int(self.page.current['enabled'])
        return next(key for key, (ordinal, _) in FORM_SETTINGS.items() if ordinal == index)

    def get_attribute(self, name):
        if self.kind == 'title' and name == 'contenteditable':return None
        assert self.kind == 'switch' and name == 'aria-checked'
        key = self.key()
        value = self.page.current['enabled'] if key == 'enabled' else self.page.current['protected'][key]
        return str(value).lower()

    def evaluate(self, _script):
        key = self.key()
        if key == 'enabled':return 'Schedule form visibility'
        if key == 'agency_branding':return 'Agency branding'
        return self.page.labels.get(key, FORM_SETTINGS[key][1])

    def click(self, **_kwargs):
        page = self.page
        if self.kind == 'switch':
            key = self.key()
            page.clicked.append(key)
            if key == 'enabled':page.current['enabled'] = not page.current['enabled']
            else:page.current['protected'][key] = not page.current['protected'][key]
        elif self.kind == 'save':
            page.saves += 1
            if not page.lose_save:page.persisted = deepcopy(page.current)
        elif self.kind != 'tab':raise AssertionError(self.kind)


class Switches:
    def __init__(self, page):self.page = page
    def count(self):return self.page.count_override or (9 if self.page.current['enabled'] else 8)
    def nth(self, index):return Control(self.page, 'switch', index)


class Page:
    def __init__(self, enabled=False):
        self.name = 'ZHC Schedule Fixture'
        self.url = 'https://fixture.example/v2/location/FIXTURE/form-builder-v2/FORM'
        self.current = {'enabled':enabled,
            'protected':{'agency_branding':True, **{key:bool(index % 2) for index,key in enumerate(FORM_SETTINGS)}},
            'schedule':{'time_zone':'America/New_York', 'opens':{'mode':'immediate'}, 'closes':{'mode':'never'},
                'before':{'mode':'message','message':'Not yet open','html':'<div><p><strong>Not yet open</strong></p></div>'},
                'after':{'mode':'message','message':'Closed','html':'<div><p>Closed</p></div>'}}}
        self.persisted = deepcopy(self.current)
        self.labels = {}
        self.clicked = []
        self.saves = self.reopens = 0
        self.lose_save = False
        self.count_override = None
        self.after_reopen = None

    def frame_locator(self, _selector):return self
    def get_by_role(self, role, name=None, exact=True):
        if role == 'switch':return Switches(self)
        if role == 'dialog':return Control(self, 'absent')
        return Control(self, 'save' if name == 'Save' else 'title' if name == 'Form Name' else 'tab')

    def reopen(self, _page, kind, name, url):
        assert (kind, name, url) == ('form', self.name, self.url)
        self.reopens += 1
        self.current = deepcopy(self.persisted)
        if self.after_reopen:self.after_reopen(self.current)


class NativeScheduleFlowTests(unittest.TestCase):
    def run_schedule(self, page, value):
        def set_endpoint(frame, definition, wanted):
            key = next(key for key,item in schedule._WINDOWS.items() if item == definition)
            frame.current['schedule'][key] = deepcopy(wanted)
        def set_outside(frame, key, wanted):
            frame.current['schedule'][key] = deepcopy(wanted)
            if wanted['mode'] == 'message':frame.current['schedule'][key]['html'] = '<div><p>' + wanted['message'] + '</p></div>'
        with patch.object(schedule, '_read_schedule', side_effect=lambda frame:deepcopy(frame.current['schedule'])), \
             patch.object(schedule, '_set_zone', side_effect=lambda frame,value:frame.current['schedule'].update(time_zone=value)), \
             patch.object(schedule, '_set_endpoint', side_effect=set_endpoint), \
             patch.object(schedule, '_set_outside', side_effect=set_outside), \
             patch('assessments.reopen_editor', side_effect=page.reopen):
            return schedule.configure(page, value)

    def test_enable_window_and_authored_outside_values_save_once_and_reopen(self):
        page = Page()
        protected = deepcopy(page.current['protected'])
        value = spec()
        value['schedule'].update(before={'mode':'redirect','url':'https://example.com/private-fixture'},
                                 after={'mode':'message','message':'Private fixture closed'})
        result = self.run_schedule(page, value)
        self.assertEqual((page.clicked, page.saves, page.reopens), (['enabled'],1,1))
        self.assertEqual(page.current['protected'], protected)
        self.assertEqual(result['configuration_sha256'], schedule.configuration_hash(value['schedule']))
        self.assertEqual(result['status'], 'FORM_SCHEDULE_SAVED_AND_REOPENED')
        self.assertFalse(result['behavior_verified'])
        self.assertFalse(result['submission_verified'])
        self.assertNotIn('private-fixture', json.dumps(result))
        self.assertNotIn('Private fixture closed', json.dumps(result))

    def test_window_only_preserves_exact_existing_outside_html(self):
        page = Page(True)
        before = deepcopy(page.current['schedule'])
        self.run_schedule(page, spec())
        self.assertEqual(page.current['schedule']['before'], before['before'])
        self.assertEqual(page.current['schedule']['after'], before['after'])
        self.assertEqual((page.saves,page.reopens), (1,1))

    def test_other_outside_modes_and_normalized_plaintext_are_preserved(self):
        page = Page(True)
        value = spec()
        value['schedule'].update(before={'mode':'message','message':'  Opening later.\r\nReturn tomorrow.  '},
                                 after={'mode':'redirect','url':'https://example.com/closed'})
        result = self.run_schedule(page, value)
        self.assertEqual(page.current['schedule']['before']['message'], 'Opening later.\nReturn tomorrow.')
        self.assertEqual(page.current['schedule']['after'], {'mode':'redirect','url':'https://example.com/closed'})
        self.assertEqual(result['configuration_sha256'], schedule.configuration_hash(value['schedule']))
        self.assertEqual((page.saves,page.reopens), (1,1))

    def test_lost_save_does_not_report_persistence_or_retry(self):
        page = Page(True);page.lose_save = True
        with self.assertRaisesRegex(Stop, 'window or timezone did not persist'):
            self.run_schedule(page, spec())
        self.assertEqual((page.saves,page.reopens), (1,1))

    def test_disabling_changes_only_scheduler_and_keeps_ordinary_flags(self):
        page = Page(True)
        protected = deepcopy(page.current['protected'])
        window = deepcopy(page.current['schedule'])
        result = self.run_schedule(page, {'schedule':{'enabled':False}})
        self.assertFalse(result['enabled'])
        self.assertFalse(page.current['enabled'])
        self.assertEqual(page.current['protected'], protected)
        self.assertEqual(page.current['schedule'], window)
        self.assertEqual((page.clicked,page.saves,page.reopens), (['enabled'],1,1))

    def test_protected_flag_or_omitted_html_drift_after_save_is_a_failure(self):
        def changed_flag(state):state['protected']['sticky_contact'] = not state['protected']['sticky_contact']
        def changed_html(state):state['schedule']['before']['html'] = '<p>Not yet open</p>'
        for drift in (changed_flag, changed_html):
            page = Page(True);page.after_reopen = drift
            with self.subTest(drift=drift), self.assertRaises(Stop):
                self.run_schedule(page, spec())
            self.assertEqual((page.saves,page.reopens), (1,1))

    def test_changed_settings_inventory_refuses_before_toggle_or_save(self):
        for key in ('labels','count'):
            page = Page()
            if key == 'labels':page.labels['sticky_contact'] = 'Uncaptured option'
            else:page.count_override = 9
            with self.subTest(key=key), self.assertRaises(Stop):
                self.run_schedule(page, spec())
            self.assertEqual((page.clicked,page.saves), ([],0))

    def test_invalid_request_refuses_before_any_browser_read(self):
        value = spec();value['schedule']['closes']['time'] = '99:99'
        with self.assertRaises(schedule.ScheduleError):schedule.configure(object(), value)

    def test_wrong_editor_kind_or_credential_url_refuses_before_toggle(self):
        for url in ('https://fixture.example/v2/location/FIXTURE/survey-builder-v2/FORM',
                    'https://fixture.example/v2/location/FIXTURE/form-builder-v2/FORM?token=not-for-receipts'):
            page = Page();page.url = url
            with self.subTest(url=url), self.assertRaisesRegex(Stop, 'editor identity'):
                self.run_schedule(page, spec())
            self.assertEqual((page.clicked,page.saves), ([],0))


if __name__ == '__main__':
    unittest.main()
