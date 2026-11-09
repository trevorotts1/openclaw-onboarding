from copy import deepcopy
import unittest
from unittest.mock import patch

import meetings as m
from pathlib import Path
from recipe_cli import compile_recipe
from skill6_playwright import validate_job


SPEC = {'location_id':'loc', 'location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/loc/dashboard',
        'name':'Fixture room', 'slug':'fixture-room', 'waiting_room':True,
        'guest_users':False, 'open_room':False, 'allow_creation':True}


def present():
    return {**SPEC, 'status':'PRESENT', 'source':'persisted fixture reader',
            'room_id':'room1', 'url':'https://rooms.example/fixture-room',
            'passcode':'SYNTHETIC-NEVER-RETURN'}


class Control:
    def __init__(self, owner, name, *, state=None):
        self.owner, self.name, self.state = owner, name, state
        self.value = None
    def count(self): return 1
    def is_visible(self): return True
    def is_enabled(self): return True
    def get_attribute(self, name): return self.state if name == 'aria-checked' else None
    def click(self):
        self.owner.actions.append(('click', self.name))
        if self.state in ('true', 'false'):
            self.state = 'false' if self.state == 'true' else 'true'
    def fill(self, value):
        self.owner.actions.append(('fill', self.name, value))
        self.value = value
    def input_value(self): return self.value
    def wait_for(self, **kwargs): pass


class Fields:
    def __init__(self, owner): self.owner = owner
    def count(self): return 3
    def nth(self, index): return self.owner.fields[index]


class Page:
    def __init__(self):
        self.actions = []
        self.fields = [Control(self, 'field'+str(i)) for i in range(3)]
        self.switches = {name:Control(self, name, state='false') for name in m.SECURITY.values()}
    def get_by_role(self, role, name=None, exact=True):
        if role == 'region': return self
        if role == 'textbox': return Fields(self)
        if role == 'switch': return self.switches[name]
        return Control(self, name)
    def wait_for(self, **kwargs): pass
    def count(self): return 1
    def get_by_text(self, text, exact=True): return Control(self, text)


class AbsentCreate(Control):
    def count(self): return 0
    def is_visible(self): return False
    def get_by_role(self, *a, **kw): return self


class ReaderPage(Page):
    def __init__(self):
        super().__init__()
        self.url = SPEC['start_url']
        self.fields[0].value = SPEC['name']
        self.fields[1].value = SPEC['slug']
        self.fields[2].value = 'SYNTHETIC-PASSCODE-NOT-READ'
        self.switches['Waiting room'].state = 'true'
        self.invite = Control(self, 'invite')
        self.invite.value = 'https://rooms.example/meet/fixture-room?pwd=SYNTHETIC-PASSCODE-NOT-READ'
    def get_by_role(self, role, name=None, exact=True):
        if role == 'region' and isinstance(name, str): return AbsentCreate(self, 'absent')
        if role == 'textbox' and name == 'Invite link': return self.invite
        if role == 'complementary': return Control(self, 'owner')
        return super().get_by_role(role, name, exact)
    def get_by_text(self, text, exact=True): return Control(self, text)
    def reload(self, **kwargs): self.actions.append(('reload',))
    def goto(self, url, **kwargs): self.actions.append(('goto',url)); self.url = url


class MeetingTests(unittest.TestCase):
    def test_unsupported_requested_controls_stop_before_browser_activity(self):
        for settings in ({'recording':False}, {'transcription':True}, {'cohosts':[]},
                         {'passcode':''}, {'native_integration':'calendar'}, {'start_meeting':False}):
            page = Page()
            with self.subTest(settings=settings), self.assertRaises(m.Stop):
                m.create_room(page, {**SPEC, **settings})
            self.assertEqual(page.actions, [])

    def test_compiler_metadata_is_accepted_for_real_setup_and_update_steps(self):
        for operation in ('meetings.setup', 'meetings.update'):
            data = {k:SPEC[k] for k in ('location_id','location_name','start_url')}
            data['meeting'] = {key:value for key,value in SPEC.items() if key not in data}
            if operation == 'meetings.update':
                data['meeting']['expected_room_id'] = 'https://rooms.example/meet/fixture-room'
            job = validate_job(compile_recipe(operation, data), Path('.'))
            step = job['steps'][0]
            inputs = {**step, **step['_context']}
            parsed = m.validate_room(inputs)
            self.assertEqual(parsed['action'], 'meeting')
            self.assertEqual(parsed['location_id'], 'loc')

    def test_mismatched_context_and_string_creation_flag_are_refused(self):
        for change in ({'_context':{'location_id':'other','location_name':'Fixture','start_url':SPEC['start_url']}},
                       {'allow_creation':'false'}):
            with self.subTest(change=change), self.assertRaises(m.Stop):
                m.validate_room({**SPEC, **change})

    def test_native_reader_reloads_and_reads_editor_without_exposing_invite_password(self):
        page = ReaderPage()
        with patch.object(m, 'assert_tenant'), patch.object(m, 'click', side_effect=lambda c:c.click()):
            result = m.read_room(page, SPEC)
        self.assertEqual(result['url'], 'https://rooms.example/meet/fixture-room')
        self.assertEqual(result['name'], SPEC['name'])
        self.assertEqual(result['identity_source'], 'canonical_room_link')
        self.assertNotIn('SYNTHETIC-PASSCODE', str(result))
        self.assertFalse(any(action[0]=='fill' for action in page.actions))
        self.assertEqual(page.actions[0], ('reload',))

    def test_update_reconciles_existing_identity_before_writes(self):
        page = Page()
        with patch.object(m, 'assert_tenant'), patch.object(m, 'navigate'), self.assertRaises(m.Stop):
            m.update_room(page, SPEC, expected_room_id='different', reader=lambda *a:present())
        self.assertEqual(page.actions, [])

    def test_update_saves_and_independently_verifies(self):
        page = Page()
        observations = iter([present(), present()])
        with patch.object(m, 'assert_tenant'), patch.object(m, 'navigate'), \
             patch.object(m, 'click', side_effect=lambda c:c.click()), \
             patch.object(m, 'fill', side_effect=lambda c,v:c.fill(v)):
            result = m.update_room(page, SPEC, expected_room_id='room1', reader=lambda *a:next(observations))
        self.assertEqual(result['status'], 'ROOM_UPDATED_VERIFIED')
        self.assertIn(('click','Save changes'), page.actions)
        self.assertIsNone(page.fields[2].value)

    def test_room_requires_explicit_booleans_and_no_secret_actions(self):
        for change in ({'guest_users':'false'}, {'slug':'Bad Slug'}, {'passcode':'secret'}, {'cohosts':['user']}):
            with self.subTest(change=change), self.assertRaises(m.Stop):
                m.validate_room({**SPEC, **change})

    def test_readback_drops_unrelated_and_secret_fields(self):
        result = m.validate_observation(present(), SPEC)
        self.assertNotIn('passcode', result)
        self.assertEqual(result['source'], 'persisted native Meeting Room read-back')
        self.assertNotIn('start_url', result)
        self.assertEqual(result['room_id'], 'room1')

    def test_readback_refuses_wrong_tenant_unverified_and_secret_urls(self):
        for change in ({'location_id':'other'}, {'source':''}, {'status':'UNKNOWN'},
                       {'url':'https://rooms.example/r?passcode=secret'}, {'waiting_room':False}):
            with self.subTest(change=change), self.assertRaises(m.Stop):
                m.validate_observation({**present(), **change}, SPEC)

    def test_existing_verified_room_never_creates_duplicate(self):
        page = Page()
        with patch.object(m, 'assert_tenant'), patch.object(m, 'navigate'):
            result = m.create_room(page, SPEC, read_room=lambda *a:present())
        self.assertEqual(result['status'], 'ROOM_REUSED_VERIFIED')
        self.assertEqual(page.actions, [])

    def test_unknown_presence_never_creates(self):
        page = Page()
        with patch.object(m, 'assert_tenant'), patch.object(m, 'navigate'), self.assertRaises(m.Stop):
            m.create_room(page, SPEC, read_room=lambda *a:{'status':'UNKNOWN','source':'read','location_id':'loc'})
        self.assertEqual(page.actions, [])

    def test_native_create_sets_three_switches_without_filling_passcode(self):
        page = Page()
        observations = iter([{'status':'ABSENT','location_id':'loc','source':'read'}, present()])
        def once(fn, *args, **kwargs):
            if not fn(): raise m.Stop('Fixture expectation failed')
        with patch.object(m, 'assert_tenant'), patch.object(m, 'navigate'), \
             patch.object(m, 'click', side_effect=lambda c:c.click()), \
             patch.object(m, 'fill', side_effect=lambda c,v:c.fill(v)), \
             patch.object(m, 'wait_until', side_effect=once):
            result = m.create_room(page, SPEC, read_room=lambda *a:next(observations))
        self.assertEqual(result['status'], 'ROOM_CREATED_VERIFIED')
        self.assertIsNone(page.fields[2].value)
        self.assertEqual(page.switches['Waiting room'].state, 'true')
        self.assertFalse(any('Start' in str(action) for action in page.actions))


class CalendarTests(unittest.TestCase):
    def test_explicit_replacement_does_not_reuse_a_different_slot(self):
        calendar = self.calendar()
        calendar['locationConfigurations'].append({'kind':'custom','location':present()['url']})
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present(), replace_index=0)
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present(), replace_index=9)

    def test_readback_refuses_lost_preserved_locations_and_members(self):
        for kind in ('event', 'personal'):
            calendar = self.calendar(kind)
            if kind == 'personal':
                calendar['teamMembers'].append({'userId':'u2','priority':0.2,'isPrimary':False,
                    'locationConfigurations':[{'kind':'physical','location':'Other office'}]})
            calls = []
            def api(op, **kw):
                calls.append(op)
                if op == 'calendars.update':
                    calendar.update(deepcopy(kw['body']))
                    if kind == 'event':
                        calendar['locationConfigurations'] = calendar['locationConfigurations'][-1:]
                    else:
                        calendar['teamMembers'] = calendar['teamMembers'][:1]
                return {'calendar':deepcopy(calendar)}
            with self.subTest(kind=kind), self.assertRaises(m.Stop):
                m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present(),
                    **({'member_id':'u1','replace_index':0} if kind == 'personal' else {}))
            self.assertEqual(calls, ['calendars.get','calendars.update','calendars.get'])

    def test_duplicate_calendar_member_identity_refused_before_update(self):
        calendar = self.calendar('personal')
        calendar['teamMembers'] *= 2
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present(), member_id='u1', replace_index=0)

    def test_put_excludes_readonly_member_and_location_fields(self):
        calendar = self.calendar('personal')
        calendar['teamMembers'][0].update(id='readonly', email='private@example.invalid', meetingLocationType='custom')
        calendar['teamMembers'][0]['locationConfigurations'][0]['meetingId'] = 'readonly-location-id'
        patch, _ = m.permanent_link_patch(calendar, location_id='loc', room=present(), member_id='u1', replace_index=0)
        self.assertEqual(set(patch['teamMembers'][0]), {'userId','priority','isPrimary','locationConfigurations'})
        self.assertEqual(set(patch['teamMembers'][0]['locationConfigurations'][0]), {'kind','location'})

    def test_legacy_only_location_is_not_silently_discarded(self):
        calendar = self.calendar('personal')
        member = calendar['teamMembers'][0]
        member.pop('locationConfigurations')
        member['meetingLocation'] = 'https://legacy.example/room'
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present(), member_id='u1')

    def test_canonical_link_receipt_explicitly_requires_manual_passcode(self):
        patch, receipt = m.permanent_link_patch(self.calendar(), location_id='loc', room=present())
        self.assertFalse(receipt['credential_link_supplied'])
        self.assertTrue(receipt['passcode_required'])
        self.assertTrue(receipt['manual_passcode_entry_required'])
        self.assertEqual(receipt['join_link_mode'], 'canonical_without_embedded_passcode')

    def test_private_invite_sent_only_in_patch_and_redacted_from_receipt(self):
        invite = present()['url'] + '?pwd=SYNTHETIC-PRIVATE'
        patch, receipt = m.permanent_link_patch(self.calendar(), location_id='loc', room=present(), private_invite_url=invite)
        self.assertEqual(patch['locationConfigurations'][-1]['location'], invite)
        self.assertTrue(receipt['credential_link_supplied'])
        self.assertFalse(receipt['manual_passcode_entry_required'])
        self.assertNotIn('SYNTHETIC-PRIVATE', str(receipt))
        self.assertNotIn('pwd=', str(receipt))
        self.assertEqual(len(receipt['invite_url_sha256']), 64)

    def test_private_invite_wrong_room_extra_parameters_empty_and_duplicate_pwd_refused(self):
        for invite in ('https://other.example/fixture-room?pwd=fake',
                       present()['url'] + '?pwd=fake&token=other',
                       present()['url'] + '?pwd=',
                       present()['url'] + '?pwd=fake&pwd=other',
                       present()['url'] + '?pwd=fake#fragment'):
            with self.subTest(invite=invite), self.assertRaises(m.Stop):
                m.permanent_link_patch(self.calendar(), location_id='loc', room=present(), private_invite_url=invite)

    def test_existing_private_invite_cannot_silently_downgrade_to_clean_link(self):
        calendar = self.calendar()
        calendar['locationConfigurations'] = [{'kind':'custom','location':present()['url']+'?pwd=SYNTHETIC'}]
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present())

    def test_private_integration_checks_full_invite_persisted_and_returns_no_secret(self):
        calendar, calls = self.calendar(), []
        invite = present()['url']+'?pwd=SYNTHETIC-API-PRIVATE'
        def api(op, **kw):
            calls.append(op)
            if op == 'calendars.update':
                self.assertEqual(kw['body']['locationConfigurations'][-1]['location'], invite)
                calendar.update(deepcopy(kw['body']))
            return {'calendar':deepcopy(calendar)}
        result = m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present(), private_invite_url=invite)
        self.assertNotIn('SYNTHETIC-API-PRIVATE', str(result))
        self.assertTrue(result['embedded_passcode'])
        self.assertEqual(calls, ['calendars.get','calendars.update','calendars.get'])

    def calendar(self, kind='event'):
        return {'id':'cal1','locationId':'loc','calendarType':kind,
                'slotDuration':60,'locationConfigurations':[{'kind':'physical','location':'Office'}],
                'teamMembers':[{'userId':'u1','priority':0.5,'isPrimary':True,
                                'locationConfigurations':[{'kind':'custom','location':'https://old.example/room'}]}]}

    def test_event_patch_preserves_existing_and_ignores_schedule_fields(self):
        calendar = self.calendar()
        patch, receipt = m.permanent_link_patch(calendar, location_id='loc', room=present())
        self.assertEqual(set(patch), {'locationConfigurations'})
        self.assertEqual(patch['locationConfigurations'][0], calendar['locationConfigurations'][0])
        self.assertEqual(calendar['slotDuration'], 60)
        self.assertEqual(len(calendar['locationConfigurations']), 1)
        self.assertEqual(receipt['mode'], 'permanent_link')

    def test_personal_requires_exact_member_and_preserves_other_member_settings(self):
        calendar = self.calendar('personal')
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(calendar, location_id='loc', room=present())
        patch, _ = m.permanent_link_patch(calendar, location_id='loc', room=present(), member_id='u1', replace_index=0)
        self.assertEqual(patch['teamMembers'][0]['priority'], 0.5)
        self.assertEqual(patch['teamMembers'][0]['locationConfigurations'][0]['location'], present()['url'])

    def test_class_requires_replacement_instead_of_adding_unsupported_second_location(self):
        with self.assertRaises(m.Stop):
            m.permanent_link_patch(self.calendar('class_booking'), location_id='loc', room=present(), member_id='u1')

    def test_wrong_tenant_never_dispatches_write(self):
        calls = []
        def api(op, **kw):
            calls.append(op)
            return {'calendar':{**self.calendar(), 'locationId':'other'}}
        with self.assertRaises(m.Stop):
            m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present())
        self.assertEqual(calls, ['calendars.get'])

    def test_api_get_put_get_and_replay_do_not_duplicate(self):
        calendar = self.calendar()
        calls = []
        def api(op, **kw):
            calls.append((op, kw))
            if op == 'calendars.update':
                calendar.update(deepcopy(kw['body']))
                return {'calendar':deepcopy(calendar)}
            return {'calendar':deepcopy(calendar)}
        result = m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present())
        self.assertEqual([x[0] for x in calls], ['calendars.get','calendars.update','calendars.get'])
        self.assertFalse(result['dynamic_room_generation'])
        calls.clear()
        m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present())
        self.assertEqual([x[0] for x in calls], ['calendars.get'])

    def test_success_response_without_persisted_change_is_failure(self):
        calls = []
        def api(op, **kw):
            calls.append(op)
            return {'calendar':self.calendar()}
        with self.assertRaises(m.Stop):
            m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present())
        self.assertEqual(calls, ['calendars.get','calendars.update','calendars.get'])

    def test_scope_failure_is_not_reclassified_as_missing_feature(self):
        def api(op, **kw): raise PermissionError('fixture scope refusal')
        with self.assertRaises(PermissionError):
            m.integrate_calendar(api, location_id='loc', calendar_id='cal1', room=present())


if __name__ == '__main__':
    unittest.main()
