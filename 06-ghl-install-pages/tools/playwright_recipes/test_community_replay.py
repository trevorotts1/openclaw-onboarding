"""Saved portal outcomes cannot change tenant, proof level or disclose raw data."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import community_portal as portal
import skill6_playwright as core
from test_community_portal import Page, inputs, read_identity, immediate_wait
from test_community_details import DetailsPage, details_inputs


class CommunityReplayTests(unittest.TestCase):
    def setUp(self):
        waiting = patch.object(portal, 'wait_until', immediate_wait)
        waiting.start()
        self.addCleanup(waiting.stop)

    def exercise_corruption(self, kind, mutate):
        data = details_inputs() if kind == 'details' else inputs()
        page = DetailsPage(data) if kind == 'details' else Page(data)
        run = portal.run_details if kind == 'details' else portal.run_channels
        name = 'community-details-state.json' if kind == 'details' else 'community-portal-state.json'
        reader = Mock(side_effect=read_identity)
        context = portal.capture_context(page, data, identity_reader=reader)
        with tempfile.TemporaryDirectory() as root:
            run(page, data, root, portal_context=context)
            path = Path(root, name)
            original = json.loads(path.read_text())
            corrupted = deepcopy(original)
            mutate(corrupted)
            raw = json.dumps(corrupted)
            path.write_text(raw)
            reader.reset_mock()
            clicks, writes = list(page.clicks), page.writes
            with self.assertRaises(core.Stop) as error:
                run(page, data, root, portal_context=context)
            self.assertNotIn('SHOULD_NOT_LEAVE_JOURNAL', str(error.exception))
            reader.assert_not_called()
            self.assertEqual(page.clicks, clicks)
            self.assertEqual(page.writes, writes)
            self.assertEqual(path.read_text(), raw)

    def test_both_journals_reject_foreign_or_malformed_binding_without_callbacks(self):
        for kind in ('details', 'channels'):
            for key, value in (('schema', 'OTHER'), ('location_id', 'FOREIGN'),
                               ('group_slug', 'foreign-group'), ('fingerprint', 'OTHER'),
                               ('status', 'API_STEPS_COMPLETE')):
                with self.subTest(kind=kind, key=key):
                    self.exercise_corruption(kind, lambda value_, key=key, value=value: value_.update({key: value}))

    def test_details_rejects_foreign_status_objects_hashes_and_proof_changes(self):
        for key, value in (('location_id', 'FOREIGN'), ('status', 'API_STEPS_COMPLETE'),
                           ('objects', [{'kind': 'community', 'id': 'foreign-group'}]),
                           ('description_sha256', '0' * 64), ('description_verified', False),
                           ('protected_access_unchanged', False), ('group_activation_attempted', True),
                           ('verification_required', False), ('behavior_verified', True),
                           ('identity_source', 'UNTRUSTED'), ('reused', 0),
                           ('description_verified', 1), ('verification_required', 1)):
            with self.subTest(key=key, value=value):
                self.exercise_corruption('details', lambda state, key=key, value=value: state['outcome'].update({key: value}))
        self.exercise_corruption('details', lambda state: state.update(description_sha256='0' * 64))

    def test_exact_reported_details_attack_stops_and_preserves_raw_journal(self):
        self.exercise_corruption('details', lambda state: state['outcome'].update(
            location_id='FOREIGN', status='API_STEPS_COMPLETE',
            private_response='SHOULD_NOT_LEAVE_JOURNAL'))

    def test_channels_rejects_wrong_rows_counts_objects_and_proof_changes(self):
        for key, value in (('location_id', 'FOREIGN'), ('status', 'API_STEPS_COMPLETE'),
                           ('objects', [{'kind': 'community', 'id': 'foreign-group'}]),
                           ('channel_count', True), ('channel_count', 2),
                           ('channel_names_seen_after_reload', False), ('description_verified', True),
                           ('behavior_verified', True), ('verification_required', False),
                           ('identity_source', 'UNTRUSTED')):
            with self.subTest(key=key, value=value):
                self.exercise_corruption('channels', lambda state, key=key, value=value: state['outcome'].update({key: value}))
        for mutate in (lambda state: state.update(channels=[]),
                       lambda state: state['channels'][0].update(name_sha256='0' * 64),
                       lambda state: state['channels'][0].update(name_seen_after_reload=1),
                       lambda state: state['channels'][0].update(description_verified=True),
                       lambda state: state.update(current_channel=False),
                       lambda state: state.update(current_name_sha256='0' * 64)):
            self.exercise_corruption('channels', mutate)

    def test_private_extra_outcome_fields_are_never_returned_on_valid_replays(self):
        for kind in ('details', 'channels'):
            data = details_inputs() if kind == 'details' else inputs()
            page = DetailsPage(data) if kind == 'details' else Page(data)
            run = portal.run_details if kind == 'details' else portal.run_channels
            name = 'community-details-state.json' if kind == 'details' else 'community-portal-state.json'
            context = portal.capture_context(page, data, identity_reader=read_identity)
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                original = run(page, data, root, portal_context=context)
                path = Path(root, name)
                state = json.loads(path.read_text())
                state['outcome']['private_response'] = 'SHOULD_NOT_LEAVE_JOURNAL'
                state['outcome']['replayed'] = 'UNTRUSTED'
                state['private_owner_copy'] = 'SHOULD_NOT_LEAVE_JOURNAL'
                raw = json.dumps(state); path.write_text(raw)
                clicks, writes = list(page.clicks), page.writes
                result = run(page, data, root, portal_context=context)
                self.assertEqual(result, {**original, 'replayed': True})
                self.assertNotIn('SHOULD_NOT_LEAVE_JOURNAL', json.dumps(result))
                self.assertEqual(page.clicks, clicks + (['SETTINGS', 'Details', 'Cancel'] if kind == 'details' else []))
                self.assertEqual(page.writes, writes)
                self.assertEqual(path.read_text(), raw)

    def test_details_replay_reloads_native_description_and_refuses_drift_without_rewrite(self):
        data = details_inputs(); page = DetailsPage(data)
        context = portal.capture_context(page, data, identity_reader=read_identity)
        with tempfile.TemporaryDirectory() as root:
            original = portal.run_details(page, data, root, portal_context=context)
            journal = Path(root, 'community-details-state.json')
            saved = journal.read_bytes()
            writes, fills, reloads = page.writes, page.fills, page.reloads
            unchanged = portal.run_details(page, data, root, portal_context=context)
            self.assertEqual(unchanged, {**original, 'replayed': True})
            self.assertEqual(page.reloads, reloads + 1)
            page.saved_description = 'Changed independently after the completed write.'
            clicks = list(page.clicks)
            with self.assertRaisesRegex(core.Stop, 'description changed'):
                portal.run_details(page, data, root, portal_context=context)
            self.assertEqual(page.reloads, reloads + 2)
            self.assertEqual(page.clicks, clicks + ['SETTINGS', 'Details', 'Cancel'])
            self.assertEqual((page.writes, page.fills), (writes, fills))
            self.assertFalse(page.modal)
            self.assertEqual(journal.read_bytes(), saved)

    def test_malformed_json_and_nonobject_outcomes_stop_without_leaking(self):
        for kind in ('details', 'channels'):
            for replacement in (None, [], 'SHOULD_NOT_LEAVE_JOURNAL'):
                with self.subTest(kind=kind, replacement=replacement):
                    self.exercise_corruption(kind, lambda state, replacement=replacement: state.update(outcome=replacement))
            data = details_inputs() if kind == 'details' else inputs()
            page = DetailsPage(data) if kind == 'details' else Page(data)
            run = portal.run_details if kind == 'details' else portal.run_channels
            name = 'community-details-state.json' if kind == 'details' else 'community-portal-state.json'
            reader = Mock(side_effect=read_identity)
            context = portal.capture_context(page, data, identity_reader=reader)
            with tempfile.TemporaryDirectory() as root:
                path = Path(root, name)
                raw = '{"private_response": "SHOULD_NOT_LEAVE_JOURNAL"'
                path.write_text(raw); reader.reset_mock()
                with self.assertRaises(core.Stop) as error:
                    run(page, data, root, portal_context=context)
                self.assertNotIn('SHOULD_NOT_LEAVE_JOURNAL', str(error.exception))
                reader.assert_not_called()
                self.assertEqual(page.clicks, [])
                self.assertEqual(path.read_text(), raw)

    def test_dangling_own_foreign_and_auth_evidence_stops_before_reader_or_clicks(self):
        for kind in ('details', 'channels'):
            for name in ('community-details-state.json', 'community-portal-state.json',
                         'provider-state.json', 'delivery-state.json',
                         'calendar-delivery-state.json', 'state.json',
                         'handoff.json', 'auth-stop.json'):
                data = details_inputs() if kind == 'details' else inputs()
                page = DetailsPage(data) if kind == 'details' else Page(data)
                run = portal.run_details if kind == 'details' else portal.run_channels
                reader = Mock(side_effect=read_identity)
                context = portal.capture_context(page, data, identity_reader=reader)
                with self.subTest(kind=kind, name=name), tempfile.TemporaryDirectory() as root:
                    link = Path(root, name)
                    target = Path(root, 'retained-missing-target')
                    link.symlink_to(target)
                    reader.reset_mock()
                    with self.assertRaises(core.Stop):
                        run(page, data, root, portal_context=context)
                    reader.assert_not_called()
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(link.readlink(), target)
                    self.assertFalse(target.exists())
                    self.assertEqual(page.clicks, [])
                    self.assertEqual(page.writes, 0)

    def test_channel_lock_symlink_is_preserved_and_cannot_be_followed(self):
        for name in ('.runner.lock', 'provider.lock'):
            data = inputs(); page = Page(data)
            reader = Mock(side_effect=read_identity)
            context = portal.capture_context(page, data, identity_reader=reader)
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                link = Path(root, name); target = Path(root, 'unexpected-file')
                link.symlink_to(target); reader.reset_mock()
                with self.assertRaises(core.Stop):
                    portal.run_channels(page, data, root, portal_context=context)
                reader.assert_not_called()
                self.assertTrue(link.is_symlink())
                self.assertFalse(target.exists())
                self.assertEqual(page.clicks, [])


if __name__ == '__main__':
    unittest.main()
