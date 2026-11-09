"""Saved editor completion is bound evidence, never an unvalidated response blob."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import skill6_playwright as runner

BASE = 'https://app.convertandflow.com/v2/location/FIXTURE/'


def fixture():
    job = {'location_id':'FIXTURE', 'location_name':'Fixture Account', 'start_url':BASE + 'dashboard',
           'steps':[{'id':name, 'action':'options', 'capture_source':'fixture', 'steps':[{'action':'fixture'}]}
                    for name in ('one', 'two')]}
    state = {'fingerprint':runner.sha(json.dumps(job, sort_keys=True)), 'location_id':'FIXTURE',
             'status':'EDITOR_STEPS_COMPLETE', 'current_step':'two', 'current_step_status':'FINISHED',
             'results':[{'id':step['id'], 'action':'options', 'result':{
                 'status':'RECORDED_OPTIONS_EXECUTED', 'count':1, 'capture_source':'fixture'}}
                 for step in job['steps']], 'verification_required':[]}
    return job, state


def one_state(job, result, pending=False):
    return {'fingerprint':runner.sha(json.dumps(job, sort_keys=True)), 'location_id':job['location_id'],
            'status':'NEEDS_VERIFICATION' if pending else 'EDITOR_STEPS_COMPLETE',
            'current_step':job['steps'][0]['id'], 'current_step_status':'FINISHED',
            'results':[{'id':job['steps'][0]['id'], 'action':job['steps'][0]['action'], 'result':result}],
            'verification_required':[job['steps'][0]['id']] if pending else []}


class EditorReplayTests(unittest.TestCase):
    def replay(self, job, state):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'state.json')
            path.write_text(json.dumps(state))
            before = path.read_bytes()
            page = Mock()
            with patch.object(runner, 'assert_tenant') as tenant:
                result = runner.run_on_page(page, job, directory)
            tenant.assert_called_once_with(page, job)
            self.assertEqual(page.mock_calls, [])
            self.assertEqual(path.read_bytes(), before)
            return result

    def reject(self, job, state):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'state.json')
            path.write_text(json.dumps(state))
            before = path.read_bytes()
            page = Mock()
            with patch.object(runner, 'assert_tenant') as tenant:
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(page, job, directory)
            tenant.assert_not_called()
            self.assertEqual(page.mock_calls, [])
            self.assertEqual(path.read_bytes(), before)

    def test_completed_replay_returns_only_validated_minimal_fields(self):
        job, state = fixture()
        state['private_secret'] = 'DO_NOT_RETURN'
        state['results'][0]['private_secret'] = 'DO_NOT_RETURN'
        state['results'][0]['result']['private_secret'] = 'DO_NOT_RETURN'
        result = self.replay(job, state)
        self.assertEqual(result['status'], 'ALREADY_EXECUTED')
        self.assertTrue(result['replayed'])
        self.assertEqual(result['verification_required'], [])
        self.assertNotIn('DO_NOT_RETURN', json.dumps(result))
        self.assertEqual(set(result['results'][0]['result']), {'status', 'count'})

    def test_pending_verification_is_preserved_on_replay(self):
        job, state = fixture()
        state['results'][0]['result']['submission_verified'] = False
        state['status'] = 'NEEDS_VERIFICATION'
        state['verification_required'] = ['one']
        result = self.replay(job, state)
        self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
        self.assertEqual(result['verification_required'], ['one'])
        self.assertIs(result['results'][0]['result']['submission_verified'], False)

    def test_corrupt_binding_step_order_completion_and_proof_lists_stop_before_browser(self):
        job, base = fixture()
        mutations = (
            lambda s:s.update(fingerprint='foreign'), lambda s:s.update(location_id='FOREIGN'),
            lambda s:s.update(status='RUNNING'), lambda s:s.update(status='NEEDS_VERIFICATION'),
            lambda s:s.update(current_step='one'), lambda s:s.update(current_step_status='INTENT_RECORDED'),
            lambda s:s.update(results=[]), lambda s:s.update(results=s['results'][::-1]),
            lambda s:s['results'].append(copy.deepcopy(s['results'][0])),
            lambda s:s['results'][0].update(id='wrong'), lambda s:s['results'][0].update(action='page'),
            lambda s:s['results'][0].update(result=None),
            lambda s:s['results'][0]['result'].update(status='UNKNOWN'),
            lambda s:s['results'][0]['result'].update(status=[]),
            lambda s:s['results'][0]['result'].update(location_id='FOREIGN'),
            lambda s:s['results'][0]['result'].update(count=2),
            lambda s:s['results'][0]['result'].update(capture_source='other-profile'),
            lambda s:s['results'][0]['result'].update(submission_verified='false'),
            lambda s:s['results'][0]['result'].update(submission_verified=False),
            lambda s:s.update(verification_required=['one']), lambda s:s.pop('verification_required'),
            lambda s:s['results'][0]['result'].pop('count'),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                state = copy.deepcopy(base)
                mutate(state)
                self.reject(job, state)

    def test_arbitrary_nested_fields_do_not_escape_meeting_replay(self):
        job, _ = fixture()
        job['steps'] = [{'id':'room', 'action':'meeting', 'name':'Fixture Room', 'slug':'fixture-room',
                         'waiting_room':True, 'guest_users':False, 'open_room':False}]
        url = 'https://portal.example.com/room/fixture-room'
        result = {'status':'ROOM_CREATED_VERIFIED', 'meeting_started':False, 'room':{
            'status':'PRESENT', 'room_id':url, 'url':url, 'location_id':'FIXTURE',
            'name':'Fixture Room', 'slug':'fixture-room', 'waiting_room':True, 'guest_users':False,
            'open_room':False, 'private_secret':'DO_NOT_RETURN'}}
        replay = self.replay(job, one_state(job, result))
        self.assertEqual(replay['results'][0]['result']['room']['room_id'], url)
        self.assertNotIn('DO_NOT_RETURN', json.dumps(replay))
        foreign = copy.deepcopy(result)
        foreign['room']['location_id'] = 'FOREIGN'
        self.reject(job, one_state(job, foreign))

    def test_native_source_query_is_allowed_but_credential_queries_and_foreign_routes_stop(self):
        job, _ = fixture()
        job['steps'] = [{'id':'page', 'action':'page', 'surface':'website', 'name':'ZHC Fixture Page', 'path':'/fixture'}]
        safe = BASE + 'page-builder/PAGE?source=website'
        result = self.replay(job, one_state(job, {'editor_url':safe}))
        self.assertEqual(result['results'][0]['result']['editor_url'], safe)
        for url in (safe + '&token=DO_NOT_RETURN', safe + '&source=funnel',
                    BASE + 'page-builder/PAGE?passcode=DO_NOT_RETURN',
                    safe.replace('/FIXTURE/', '/FOREIGN/'), safe.replace('app.convertandflow.com', 'foreign.invalid')):
            with self.subTest(url=url):
                self.reject(job, one_state(job, {'editor_url':url}))

    def test_status_from_another_handler_cannot_attest_completion(self):
        job, state = fixture()
        state['results'][0]['result']['status'] = 'RENDERED'
        self.reject(job, state)

    def test_actual_native_css_handler_seam_is_recognized_and_keeps_pending_proof(self):
        job, _ = fixture()
        job['steps'] = [{'id':'css', 'action':'native_form_css', 'custom_css':'.fixture { color: red; }'}]
        outcome = {'status':'NATIVE_FORM_CSS_SAVED_AND_REOPENED',
                   'editor_url':BASE + 'form-builder-v2/FORM', 'css_sha256':'a' * 64,
                   'render_checks':0, 'submission_verified':False}
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'assert_tenant'), \
                patch('playwright_recipes.assessments.configure_css', return_value=outcome) as native:
            first = runner.run_on_page(object(), job, directory)
            repeated = runner.run_on_page(object(), job, directory)
            self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['verification_required'], ['css'])
            self.assertEqual(native.call_count, 1)
            state = json.loads(Path(directory, 'state.json').read_text())
            self.assertEqual(state['current_step_status'], 'FINISHED')
            self.assertNotIn('failed_step', state)

    def test_plain_or_malformed_own_journal_preserved_before_browser_or_auth(self):
        for content in (b'', b'{malformed', b'[]'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory, 'state.json')
                path.write_bytes(content)
                job, _ = fixture()
                page = Mock()
                with patch.object(runner, 'assert_tenant') as tenant:
                    with self.assertRaises(runner.Stop):runner.run_on_page(page, job, directory)
                tenant.assert_not_called()
                self.assertEqual(page.mock_calls, [])
                with patch('browser_manager.PlaywrightSession') as browser, patch('ghl_auth.mint_and_bridge') as auth:
                    with self.assertRaises(runner.Stop):runner.execute(job, directory)
                    browser.assert_not_called()
                    auth.assert_not_called()
                self.assertEqual(path.read_bytes(), content)

    def test_own_symlink_journal_is_never_followed_or_replaced(self):
        for dangling in (True, False):
            with self.subTest(dangling=dangling), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / 'retained-target'
                if not dangling:target.write_bytes(b'RETAINED_PRIVATE_EVIDENCE')
                journal = root / 'state.json'
                journal.symlink_to(target)
                job, _ = fixture()
                page = Mock()
                with patch.object(runner, 'assert_tenant') as tenant:
                    with self.assertRaises(runner.Stop):runner.run_on_page(page, job, root)
                    tenant.assert_not_called()
                with patch('browser_manager.PlaywrightSession') as browser, patch('ghl_auth.mint_and_bridge') as auth:
                    with self.assertRaises(runner.Stop):runner.execute(job, root)
                    browser.assert_not_called()
                    auth.assert_not_called()
                self.assertEqual(page.mock_calls, [])
                self.assertTrue(journal.is_symlink())
                if not dangling:self.assertEqual(target.read_bytes(), b'RETAINED_PRIVATE_EVIDENCE')

    def test_symlink_lease_file_is_not_followed_or_chmodded(self):
        for lease in ('.runner.lock', 'provider.lock'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / 'external-evidence'
                target.write_bytes(b'RETAINED')
                target.chmod(0o640)
                (root / lease).symlink_to(target)
                job, _ = fixture()
                page = Mock()
                with self.assertRaises(runner.Stop):runner.run_on_page(page, job, root)
                self.assertEqual(page.mock_calls, [])
                self.assertEqual(target.read_bytes(), b'RETAINED')
                self.assertEqual(target.stat().st_mode & 0o777, 0o640)


if __name__ == '__main__':
    unittest.main()
