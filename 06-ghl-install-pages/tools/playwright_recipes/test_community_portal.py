"""Captured community controls with explicit authenticated host context."""
from copy import deepcopy
from contextlib import redirect_stdout
import fcntl
import importlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import community_portal as portal
import host
import recipe_cli
import skill6_playwright as core


def inputs():
    return {'location_id': 'LOC_TEST', 'location_name': 'Fixture',
            'start_url': 'https://app.convertandflow.com/v2/location/LOC_TEST/memberships/communities/community-groups',
            'portal_url': 'https://portal.example.com/communities/groups/zhc-fixture/home',
            'group_name': 'ZHC Fixture',
            'channels': [{'name': 'ZHC Announcements', 'description': 'Authored fixture description'}]}


class Locator:
    def __init__(self, page, kind, name):
        self.page, self.kind, self.name = page, kind, name

    def count(self):
        p = self.page
        if self.kind == 'placeholder' and self.name == 'Password':
            return int(p.password_wall)
        if self.kind == 'text':
            return int((self.name == p.group_name and p.group_ready) or self.name in p.saved)
        if self.kind == 'button' and self.name == '+ Add Channel':
            return int(p.control_available) * p.control_count
        if self.kind == 'button' and self.name == 'CREATE CHANNEL':
            return int(p.modal)
        return int(p.modal)

    def get_attribute(self, name):
        if self.name == '+ Add Channel' and name == 'id':
            return self.page.control_id
        return None

    def is_visible(self):
        return bool(self.count())

    @property
    def first(self):
        return self

    def wait_for(self, **_):
        if self.name == '+ Add Channel' and self.page.hydrate_on_wait:
            self.page.hydrate_on_wait = False
            self.page.control_available = True
            self.page.group_ready = True
            self.page.hydrated += 1
            if self.page.redirect_on_wait:
                self.page.url = 'https://other.example.com/communities/groups/other/home'
            if self.page.change_user_on_wait:
                self.page.identity['user_id'] = 'DIFFERENT_USER'
        if not self.count():
            raise core.Stop('Captured fixture control missing')

    def click(self, **_):
        self.page.clicks.append(self.name)
        if self.name == '+ Add Channel':
            self.page.modal = True
        elif self.name == 'CREATE CHANNEL':
            self.page.writes += 1
            if self.page.fail_submit:
                raise RuntimeError('PRIVATE_RESPONSE_NOT_FOR_LOGS')
            self.page.saved[self.page.fields['e.g Marketing Reports']] = self.page.fields['Enter Description']
            self.page.modal = False

    def fill(self, value):
        self.page.fields[self.name] = value
        if self.page.change_user_on_fill:
            self.page.identity['user_id'] = 'DIFFERENT_USER'


class Page:
    def __init__(self, data=None):
        data = data or inputs()
        self.url = data['portal_url']
        self.group_name = data['group_name']
        self.identity = {'authenticated': True, 'location_id': data['location_id'],
                         'portal_origin': 'https://portal.example.com',
                         'group_slug': 'zhc-fixture', 'group_name': data['group_name'],
                         'user_id': 'USER_TEST', 'source_kind': 'same_session_authenticated_read'}
        self.password_wall = False
        self.control_available = True
        self.control_count = 1
        self.control_id = 'add-channel__btn'
        self.modal = False
        self.saved = {}
        self.fields = {}
        self.clicks = []
        self.writes = 0
        self.reloads = 0
        self.lose_save = False
        self.fail_submit = False
        self.change_user_on_fill = False
        self.hydrate_on_wait = False
        self.hydrated = 0
        self.group_ready = True
        self.delay_after_reload = False
        self.redirect_on_wait = False
        self.change_user_on_wait = False

    def get_by_role(self, role, *, name, exact):
        return Locator(self, role, name)

    def get_by_placeholder(self, name, *, exact):
        return Locator(self, 'placeholder', name)

    def get_by_text(self, name, *, exact):
        return Locator(self, 'text', name)

    def reload(self, **_):
        self.reloads += 1
        if self.delay_after_reload:
            self.control_available = False
            self.group_ready = False
            self.hydrate_on_wait = True
        if self.lose_save:
            self.saved.clear()


def read_identity(page):
    return deepcopy(page.identity)


def immediate_wait(fn, message, **_):
    if not fn():
        raise core.Stop(message)


class CommunityPortalTests(unittest.TestCase):
    def setUp(self):
        self.wait_patch = patch.object(portal, 'wait_until', immediate_wait)
        self.wait_patch.start()
        self.addCleanup(self.wait_patch.stop)

    def context(self, page, data=None, **kw):
        return portal.capture_context(page, data or inputs(), identity_reader=read_identity, **kw)

    def test_native_create_reloads_and_stays_pending_without_description_proof(self):
        page, data = Page(), inputs()
        context = self.context(page)
        with tempfile.TemporaryDirectory() as root:
            result = portal.run_channels(page, data, root, portal_context=context)
            self.assertEqual(page.clicks, ['+ Add Channel', 'CREATE CHANNEL'])
            self.assertEqual(page.reloads, 1)
            self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
            self.assertFalse(result['description_verified'])
            self.assertFalse(result['behavior_verified'])
            state = Path(root, 'community-portal-state.json')
            payload = state.read_text()
            self.assertNotIn(data['channels'][0]['name'], payload)
            self.assertNotIn(data['channels'][0]['description'], payload)
            self.assertNotIn('USER_TEST', payload)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            repeated = portal.run_channels(page, data, root, portal_context=context)
            self.assertTrue(repeated['replayed'])
            self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(page.writes, 1)

    def test_wrong_page_origin_group_and_identity_cannot_capture_context(self):
        for change in ({'location_id': 'OTHER'}, {'group_slug': 'other'},
                       {'portal_origin': 'https://other.example.com'},
                       {'user_id': ''}, {'authenticated': False},
                       {'source_kind': 'pit_other_credential'}, {'group_name': 'Wrong'}):
            page = Page(); page.identity.update(change)
            with self.subTest(change=change), self.assertRaises(core.Stop):
                self.context(page)
            self.assertEqual(page.writes, 0)
        page = Page(); page.url = 'https://other.example.com/communities/groups/zhc-fixture/home'
        with self.assertRaises(core.Stop):
            self.context(page)

    def test_password_wall_and_missing_write_control_refuse_before_mutation(self):
        for key in ('password_wall', 'control_available'):
            page = Page(); setattr(page, key, key == 'password_wall')
            with self.subTest(key=key), self.assertRaises(core.Stop):
                self.context(page)
            self.assertEqual(page.clicks, [])

    def test_context_is_page_bound_fresh_and_not_a_json_receipt(self):
        page = Page(); context = self.context(page, clock=lambda: 10)
        with tempfile.TemporaryDirectory() as root:
            for owner, candidate, now in ((Page(), context, 11),
                                           (page, context, 311),
                                           (page, {'authenticated': True}, 11)):
                with self.subTest(now=now, owner=owner), self.assertRaises(core.Stop):
                    portal.run_channels(owner, inputs(), root, portal_context=candidate, clock=lambda: now)
            self.assertFalse(Path(root, 'community-portal-state.json').exists())

    def test_same_session_user_change_before_submit_stops_and_keeps_intent(self):
        page = Page(); context = self.context(page); page.change_user_on_fill = True
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(core.Stop):
                portal.run_channels(page, inputs(), root, portal_context=context)
            self.assertEqual(page.writes, 0)
            state = json.loads(Path(root, 'community-portal-state.json').read_text())
            self.assertEqual(state['status'], 'RECONCILIATION_REQUIRED')

    def test_inventory_all_names_before_first_create(self):
        data = inputs(); data['channels'].append({'name': 'Existing', 'description': 'Expected'})
        page = Page(data); page.saved['Existing'] = 'Unknown description'
        with tempfile.TemporaryDirectory() as root, self.assertRaises(core.Stop):
            portal.run_channels(page, data, root, portal_context=self.context(page, data))
        self.assertEqual(page.clicks, [])

    def test_lost_save_and_uncertain_submit_never_auto_replay(self):
        for flag in ('lose_save', 'fail_submit'):
            page = Page(); context = self.context(page); setattr(page, flag, True)
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(Exception):
                    portal.run_channels(page, inputs(), root, portal_context=context)
                first_writes = page.writes
                with self.assertRaises(core.Stop):
                    portal.run_channels(page, inputs(), root, portal_context=context)
                self.assertEqual(page.writes, first_writes)
                self.assertNotIn('PRIVATE_RESPONSE_NOT_FOR_LOGS', Path(root, 'community-portal-state.json').read_text())

    def test_common_locks_and_other_lane_evidence_block_before_write(self):
        for lock_name in ('.runner.lock', 'provider.lock'):
            with self.subTest(lock=lock_name), tempfile.TemporaryDirectory() as root:
                page = Page(); context = self.context(page)
                with open(Path(root, lock_name), 'w') as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(core.Stop):
                        portal.run_channels(page, inputs(), root, portal_context=context)
                self.assertEqual(page.writes, 0)
        for name in ('state.json', 'handoff.json', 'provider-state.json', 'auth-stop.json',
                     'delivery-state.json', 'calendar-delivery-state.json',
                     'community-details-state.json'):
            with self.subTest(evidence=name), tempfile.TemporaryDirectory() as root:
                Path(root, name).write_text('{}')
                page = Page()
                with self.assertRaises(core.Stop):
                    portal.run_channels(page, inputs(), root, portal_context=self.context(page))
                self.assertEqual(page.writes, 0)

    def test_terminal_auth_refusal_blocks_portal_identity_read_and_keeps_marker(self):
        page = Page()
        reader = Mock(side_effect=read_identity)
        context = portal.capture_context(page, inputs(), identity_reader=reader)
        reader.reset_mock()
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root, 'auth-stop.json')
            original = '{"status":"CANONICAL_AUTH_REFUSED"}'
            marker.write_text(original)
            with self.assertRaises(core.Stop):
                portal.run_channels(page, inputs(), root, portal_context=context)
            reader.assert_not_called()
            self.assertEqual(page.clicks, [])
            self.assertEqual(page.writes, 0)
            self.assertEqual(marker.read_text(), original)
            self.assertFalse(Path(root, 'community-portal-state.json').exists())

    def test_schema_refuses_other_settings_duplicate_names_and_unsafe_urls(self):
        bad = []
        for url in ('http://portal.example.com/communities/groups/zhc/home',
                    'https://u:p@portal.example.com/communities/groups/zhc/home',
                    'https://portal.example.com/communities/groups/zhc/home?secret=x'):
            data = inputs(); data['portal_url'] = url; bad.append(data)
        data = inputs(); data['privacy'] = 'private'; bad.append(data)
        data = inputs(); data['channels'] *= 2; bad.append(data)
        for data in bad:
            with self.subTest(data=data), self.assertRaises(core.Stop):
                portal.validate_inputs(data)

    def test_sections_allow_section_only_jobs_and_reject_ambiguous_names(self):
        data=inputs();data['channels']=[];data['sections']=[{'name':'Operations','icon':'Heart'}]
        self.assertEqual(portal.validate_inputs(data)['sections'],data['sections'])
        duplicate=inputs();duplicate['sections']=[{'name':'Operations'},{'name':'operations'}]
        with self.assertRaisesRegex(core.Stop,'Duplicate community section'):
            portal.validate_inputs(duplicate)
        conflict=inputs();conflict['sections']=[{'name':conflict['channels'][0]['name']}]
        with self.assertRaisesRegex(core.Stop,'share an ambiguous sidebar name'):
            portal.validate_inputs(conflict)

    def test_current_add_button_requires_both_name_and_stable_id(self):
        for key, value in (('control_id', 'similar-untrusted-button'),
                           ('control_count', 2)):
            page = Page(); setattr(page, key, value)
            with self.subTest(key=key), self.assertRaises(core.Stop):
                self.context(page)
            self.assertEqual(page.clicks, [])

    def test_inactive_admin_route_can_be_read_but_cannot_create_channels(self):
        data = inputs()
        data['portal_url'] = data['portal_url'].replace('/home', '/inactive-group')
        page = Page(data)
        context = self.context(page, data)
        self.assertEqual(context.portal_url, data['portal_url'])
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(core.Stop, 'DEPENDENCY_GROUP_INACTIVE'):
                portal.run_channels(page, data, root, portal_context=context)
            self.assertEqual(page.clicks, [])
            self.assertFalse(Path(root, 'community-portal-state.json').exists())

    def test_home_context_does_not_authorize_inactive_redirect_or_other_routes(self):
        page = Page(); context = self.context(page)
        page.url = page.url.replace('/home', '/inactive-group')
        with tempfile.TemporaryDirectory() as root, self.assertRaises(core.Stop):
            portal.run_channels(page, inputs(), root, portal_context=context)
        for tail in ('settings', 'members', 'inactive-group/other', 'home/other'):
            data = inputs(); data['portal_url'] = data['portal_url'].replace('/home', '/' + tail)
            with self.subTest(tail=tail), self.assertRaises(core.Stop):
                portal.validate_inputs(data)

    def test_named_compiler_validation_and_host_execution_reach_concrete_handler(self):
        data = inputs()
        job = core.validate_job(recipe_cli.compile_recipe('communities.configure', data), Path('.'))
        self.assertEqual(job['steps'][0]['action'], 'community_channels')
        page = Page(); context = self.context(page)
        probes = {'lanes': {'playwright': {'available': True}}}
        with tempfile.TemporaryDirectory() as root:
            result = host.run_recipe('communities.configure', data, probes, root,
                                     input_dir='.', page=page, portal_context=context)
            self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
            self.assertTrue(result['browser_used'])
            self.assertEqual(page.writes, 1)
        with tempfile.TemporaryDirectory() as root:
            with patch.object(host, 'execute') as execute:
                result = host.run_recipe('communities.configure', data, probes, root, input_dir='.')
            self.assertEqual(result['status'], 'PORTAL_CONTEXT_REQUIRED')
            execute.assert_not_called()

    def test_raw_execute_does_not_seed_or_launch_for_portal_job(self):
        job = recipe_cli.compile_recipe('communities.configure', inputs())
        with self.assertRaises(core.Stop):
            core.execute(job, '/unused')

    def test_broad_api_receipt_cannot_replace_native_portal_context(self):
        data = inputs()
        callback = Mock(return_value={'status': 'API_STEPS_COMPLETE',
                                     'location_id': 'LOC_TEST', 'objects': []})
        probes = {'lanes': {'playwright': {'available': True}},
                  'api_capabilities': {'communities.configure': {
                      'supported': True, 'location_id': 'LOC_TEST',
                      'observed_at': time.time(), 'provider': 'official_mcp',
                      'scope_ok': True, 'version': 'captured-version'}}}
        with tempfile.TemporaryDirectory() as root:
            result = host.run_recipe('communities.configure', data, probes, root,
                                     input_dir='.', executors={'official_mcp': callback})
            self.assertEqual(result['route']['lane'], 'playwright')
            callback.assert_not_called()
            self.assertEqual(result['status'], 'PORTAL_CONTEXT_REQUIRED')

    def test_direct_and_package_context_types_are_identical(self):
        packaged = importlib.import_module('playwright_recipes.community_portal')
        self.assertIs(packaged.PortalContext, portal.PortalContext)

    def test_cli_check_is_schema_only_and_requires_live_portal_context(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, 'inputs.json'); source.write_text(json.dumps(inputs()))
            probes = Path(root, 'probes.json')
            probes.write_text(json.dumps({'lanes': {'playwright': {'available': True}}}))
            evidence = Path(root, 'evidence')
            output = io.StringIO()
            with redirect_stdout(output):
                code = host.main(['--operation', 'communities.configure', '--inputs', str(source),
                                  '--probes', str(probes), '--evidence-root', str(evidence), '--check'])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['status'], 'PORTAL_CONTEXT_REQUIRED')
            self.assertFalse(evidence.exists())

    def test_identity_reader_error_is_sanitized(self):
        def error_reader(page):
            raise RuntimeError('PRIVATE_IDENTITY_RESPONSE')
        with self.assertRaises(core.Stop) as error:
            portal.capture_context(Page(), inputs(), identity_reader=error_reader)
        self.assertNotIn('PRIVATE_IDENTITY_RESPONSE', str(error.exception))

    def test_delayed_portal_hydration_after_reload_uses_captured_ready_control(self):
        page = Page(); context = self.context(page)
        page.delay_after_reload = True
        with tempfile.TemporaryDirectory() as root:
            result = portal.run_channels(page, inputs(), root, portal_context=context)
        self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
        self.assertEqual(page.hydrated, 1)
        self.assertEqual(page.writes, 1)

    def test_readiness_redirect_or_user_change_never_authorizes_a_write(self):
        for flag in ('redirect_on_wait', 'change_user_on_wait'):
            page = Page(); context = self.context(page)
            page.control_available = False; page.hydrate_on_wait = True
            setattr(page, flag, True)
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(core.Stop):
                    portal.run_channels(page, inputs(), root, portal_context=context)
                self.assertEqual(page.writes, 0)

    def test_context_lifetime_is_rechecked_after_ui_wait(self):
        page = Page(); context = self.context(page, clock=lambda: 10)
        readings = iter((309, 311))
        with tempfile.TemporaryDirectory() as root, self.assertRaises(core.Stop):
            portal.run_channels(page, inputs(), root, portal_context=context,
                                clock=lambda: next(readings))
        self.assertEqual(page.writes, 0)


if __name__ == '__main__':
    unittest.main()
