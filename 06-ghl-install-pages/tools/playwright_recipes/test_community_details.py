"""Description-only native edits preserve independently reloaded access settings."""
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import community_portal as portal
import skill6_playwright as core
from test_community_portal import Page, Locator, inputs, read_identity, immediate_wait


def details_inputs():
    value = inputs()
    del value['channels']
    value['portal_url'] = value['portal_url'].replace('/home', '/inactive-group')
    value['details'] = {'expected_description': 'Original authored description.',
                        'description': 'Updated authored description.'}
    return value


class DetailLocator(Locator):
    def count(self):
        p = self.page
        if self.kind == 'button' and self.name == 'SETTINGS':
            return int(p.settings_available)
        if self.kind == 'dialog':
            return int(p.modal) * p.modal_count
        if self.kind == 'menuitem' and self.name == 'Details':
            return int(p.modal)
        if self.kind == 'placeholder' and self.name in ('Group Name', 'Group Slug', 'Enter a brief description'):
            return int(p.modal)
        if self.kind == 'radio' or self.kind == 'checkbox':
            return int(p.modal)
        if self.kind == 'button' and self.name in (*portal._DETAIL_FLAGS.values(), 'Save', 'Cancel'):
            return int(p.modal)
        return super().count()

    def get_by_role(self, role, *, name=None, exact=None):
        if self.kind == 'button' and self.name in portal._DETAIL_FLAGS.values() and role == 'checkbox':
            key = next(key for key, label in portal._DETAIL_FLAGS.items() if label == self.name)
            return DetailLocator(self.page, 'checkbox', key)
        return DetailLocator(self.page, role, name)

    def get_by_placeholder(self, name, *, exact):
        return DetailLocator(self.page, 'placeholder', name)

    def input_value(self):
        p = self.page
        if self.name == 'Group Name':
            return 'Wrong group' if p.wrong_name else p.group_name
        if self.name == 'Group Slug':
            return 'wrong-group' if p.wrong_slug else 'zhc-fixture'
        if self.name == 'Enter a brief description':
            return p.draft_description
        raise AssertionError('Unknown native details input')

    def is_enabled(self):
        return not self.page.save_busy

    def get_attribute(self, name):
        if name == 'aria-checked' and self.kind == 'radio':
            key = self.name.split(' ', 1)[0].lower()
            return str(self.page.protected[key]).lower()
        if name == 'aria-checked' and self.kind == 'checkbox':
            return str(self.page.protected[self.name]).lower()
        return super().get_attribute(name)

    def wait_for(self, *, state='visible', **_):
        if self.kind == 'dialog' and state == 'hidden':
            if self.page.modal:
                raise core.Stop('Settings save did not close the native dialog')
            return
        if not self.count():
            raise core.Stop('Captured details control missing')

    def click(self, **_):
        p = self.page
        p.clicks.append(self.name)
        if self.name == 'SETTINGS':
            p.modal = True
            p.draft_description = p.saved_description
        elif self.name == 'Cancel':
            p.modal = False
        elif self.name == 'Save':
            p.writes += 1
            if not p.lose_save:
                p.saved_description = p.draft_description
            if p.change_access_on_save:
                p.protected['allow_member_invites'] = not p.protected['allow_member_invites']
            if p.change_user_on_save:
                p.identity['user_id'] = 'DIFFERENT_USER'
            p.modal = True

    def fill(self, value):
        if self.name != 'Enter a brief description':
            raise AssertionError('Attempted to edit a protected field')
        self.page.draft_description = value
        self.page.fills += 1
        if self.page.change_user_on_fill:
            self.page.identity['user_id'] = 'DIFFERENT_USER'
        if self.page.change_access_on_fill:
            self.page.protected['accessible_from_switcher'] = not self.page.protected['accessible_from_switcher']


class DetailsPage(Page):
    def __init__(self, data=None):
        data = data or details_inputs()
        super().__init__(data)
        self.settings_available = True
        self.saved_description = data['details']['expected_description']
        self.draft_description = self.saved_description
        self.protected = {'public': True, 'private': False,
                          'accessible_from_switcher': True,
                          'allow_member_invites': False,
                          'mandatory_profile': True}
        self.wrong_name = False
        self.wrong_slug = False
        self.modal_count = 1
        self.change_access_on_save = False
        self.change_access_on_fill = False
        self.change_user_on_save = False
        self.save_busy = False
        self.fills = 0

    def reload(self, **kwargs):
        super().reload(**kwargs)
        self.modal = False

    def get_by_role(self, role, *, name=None, exact=None):
        return DetailLocator(self, role, name)

    def get_by_placeholder(self, name, *, exact):
        return DetailLocator(self, 'placeholder', name)


class CommunityDetailsTests(unittest.TestCase):
    def setUp(self):
        waiting = patch.object(portal, 'wait_until', immediate_wait)
        waiting.start()
        self.addCleanup(waiting.stop)

    def context(self, page, data=None, **kw):
        return portal.capture_context(page, data or details_inputs(), identity_reader=read_identity, **kw)

    def test_description_saves_reopens_and_preserves_access_on_inactive_view(self):
        data = details_inputs(); page = DetailsPage(data)
        before = deepcopy(page.protected)
        context = self.context(page, data)
        with tempfile.TemporaryDirectory() as root:
            result = portal.run_details(page, data, root, portal_context=context)
            self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
            self.assertTrue(result['description_verified'])
            self.assertTrue(result['protected_access_unchanged'])
            self.assertFalse(result['group_activation_attempted'])
            self.assertFalse(result['behavior_verified'])
            self.assertEqual(page.protected, before)
            self.assertEqual(page.saved_description, data['details']['description'])
            self.assertEqual(page.fills, 1)
            self.assertEqual(page.writes, 1)
            self.assertEqual(page.reloads, 1)
            self.assertEqual(page.clicks.count('SETTINGS'), 2)
            state = Path(root, 'community-details-state.json')
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(data['details']['description'], state.read_text())
            self.assertNotIn(data['details']['expected_description'], state.read_text())
            self.assertNotIn('USER_TEST', state.read_text())
            repeated = portal.run_details(page, data, root, portal_context=context)
            self.assertTrue(repeated['replayed'])
            self.assertEqual(page.writes, 1)

    def test_already_matching_description_is_reopened_without_a_write(self):
        data = details_inputs(); page = DetailsPage(data)
        page.saved_description = data['details']['description']
        with tempfile.TemporaryDirectory() as root:
            result = portal.run_details(page, data, root, portal_context=self.context(page, data))
        self.assertTrue(result['reused'])
        self.assertTrue(result['description_verified'])
        self.assertEqual(page.writes, 0)
        self.assertEqual(page.fills, 0)
        self.assertEqual(page.reloads, 1)

    def test_inventory_mismatch_and_wrong_modal_group_stop_before_edit(self):
        for flag in ('wrong_name', 'wrong_slug', 'wrong_description', 'ambiguous_modal'):
            data = details_inputs(); page = DetailsPage(data)
            if flag == 'wrong_description':
                page.saved_description = 'Another writer changed this.'
            elif flag == 'ambiguous_modal':
                page.modal_count = 2
            else:
                setattr(page, flag, True)
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(core.Stop):
                    portal.run_details(page, data, root, portal_context=self.context(page, data))
                self.assertEqual(page.writes, 0)
                self.assertEqual(page.fills, 0)
                self.assertFalse(Path(root, 'community-details-state.json').exists())

    def test_lost_save_access_drift_and_user_switch_keep_reconciliation_intent(self):
        for flag in ('lose_save', 'change_access_on_save', 'change_access_on_fill', 'change_user_on_fill',
                     'change_user_on_save', 'save_busy'):
            data = details_inputs(); page = DetailsPage(data); setattr(page, flag, True)
            context = self.context(page, data)
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(core.Stop):
                    portal.run_details(page, data, root, portal_context=context)
                state = json.loads(Path(root, 'community-details-state.json').read_text())
                self.assertEqual(state['status'], 'RECONCILIATION_REQUIRED')
                if flag in ('change_access_on_fill', 'change_user_on_fill'):
                    self.assertEqual(page.writes, 0)
                writes = page.writes
                with self.assertRaises(core.Stop):
                    portal.run_details(page, data, root, portal_context=context)
                self.assertEqual(page.writes, writes)

    def test_other_lane_evidence_or_leases_prevent_settings_edits(self):
        for name in ('state.json', 'handoff.json', 'provider-state.json',
                     'community-portal-state.json', 'delivery-state.json',
                     'calendar-delivery-state.json', 'auth-stop.json'):
            data = details_inputs(); page = DetailsPage(data); context = self.context(page, data)
            with self.subTest(journal=name), tempfile.TemporaryDirectory() as root:
                Path(root, name).write_text('{}')
                with self.assertRaises(core.Stop):
                    portal.run_details(page, data, root, portal_context=context)
                self.assertEqual(page.clicks, [])
        for name in ('.runner.lock', 'provider.lock'):
            data = details_inputs(); page = DetailsPage(data); context = self.context(page, data)
            with self.subTest(lease=name), tempfile.TemporaryDirectory() as root:
                with open(Path(root, name), 'w') as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(core.Stop):
                        portal.run_details(page, data, root, portal_context=context)
                self.assertEqual(page.clicks, [])

    def test_auth_stop_prevents_identity_read_and_preserves_evidence(self):
        data = details_inputs(); page = DetailsPage(data)
        reader = Mock(side_effect=read_identity)
        context = portal.capture_context(page, data, identity_reader=reader)
        reader.reset_mock()
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'auth-stop.json').write_text('{"status":"STOP_AUTH"}')
            with self.assertRaises(core.Stop):
                portal.run_details(page, data, root, portal_context=context)
            reader.assert_not_called()
            self.assertEqual(page.clicks, [])

    def test_schema_rejects_access_fields_and_overlong_or_missing_copy(self):
        variants = []
        for key in ('privacy', 'name', 'slug', 'allow_members_to_invite'):
            value = details_inputs(); value['details'][key] = False; variants.append(value)
        for key in ('description', 'expected_description'):
            for bad in ('', 'x' * 151, None, True):
                value = details_inputs(); value['details'][key] = bad; variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(core.Stop):
                portal.validate_details_inputs(value)


if __name__ == '__main__':
    unittest.main()
