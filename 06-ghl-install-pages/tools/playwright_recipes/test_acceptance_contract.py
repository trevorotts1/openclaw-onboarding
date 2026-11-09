"""Acceptance boundaries across handlers, not selector or implementation mirrors.

These checks deliberately use the public execution seam and a failing handler,
so they catch an incomplete new lane being promoted to a completed build.
No network, browser process, credentials or client account is involved.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import skill6_playwright as runner
from recipe_cli import compile_recipe


def two_steps():
    return {
        'location_id': 'FIXTURE', 'location_name': 'Acceptance fixture',
        'start_url': 'https://app.convertandflow.com/v2/location/FIXTURE/dashboard',
        'steps': [
            {'id': 'one', 'action': 'options'},
            {'id': 'two', 'action': 'options'},
        ],
    }


class AcceptanceBoundaryTests(unittest.TestCase):
    def test_saved_form_submission_and_notification_handlers_are_recognized_but_pending(self):
        cases = (
            ('form_submission', 'FORM_SUBMISSION_SAVED_AND_REOPENED',
             {'behavior_verified': False, 'submission_verified': False}),
            ('form_notifications', 'NOTIFICATION_SETTINGS_SAVED_AND_REOPENED',
             {'behavior_verification': 'REQUIRED'}),
        )
        for action, status, flags in cases:
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                job = two_steps()
                job['steps'] = [{'id': 'saved', 'action': action}]
                with patch.object(runner, 'assert_tenant'), patch.object(
                    runner, action, return_value={'status': status,
                                                 'independent_readback': 'VERIFIED', **flags}
                ) as handler:
                    result = runner.run_on_page(object(), job, directory)
                self.assertEqual(handler.call_count, 1)
                self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
                self.assertEqual(result['verification_required'], ['saved'])

    def test_every_explicit_false_verification_flag_is_preserved_globally(self):
        for flag in ('behavior_verified', 'submission_verified', 'payment_verified',
                     'functional_verified'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                job = two_steps()
                job['steps'] = job['steps'][:1]
                with patch.object(runner, 'assert_tenant'), patch.object(
                    runner, 'options', return_value={
                        'status': 'RECORDED_OPTIONS_EXECUTED',
                        'independent_readback': 'VERIFIED', flag: False,
                    }
                ):
                    result = runner.run_on_page(object(), job, directory)
                self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
                self.assertEqual(result['verification_required'], ['one'])

    def test_non_verification_false_values_do_not_create_fake_pending_state(self):
        with tempfile.TemporaryDirectory() as directory:
            job = two_steps()
            job['steps'] = job['steps'][:1]
            with patch.object(runner, 'assert_tenant'), patch.object(
                runner, 'options', return_value={
                    'status': 'RECORDED_OPTIONS_EXECUTED', 'meeting_started': False,
                    'discovery': False,
                }
            ):
                result = runner.run_on_page(object(), job, directory)
            self.assertEqual(result['status'], 'EDITOR_STEPS_COMPLETE')
            self.assertEqual(result['verification_required'], [])

    def test_direct_cli_normalizes_native_helper_refusal_without_traceback(self):
        inputs = {
            'location_id': 'FIXTURE', 'location_name': 'Acceptance fixture',
            'start_url': 'https://app.convertandflow.com/v2/location/FIXTURE/editor/page',
            'element_id': 'native_order', 'expected_name': 'Fixture checkout',
            'products': {'uncaptured_option': False},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'inputs.json')
            source.write_text(json.dumps(inputs))
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name('recipe_cli.py')),
                '--recipe', 'checkout.configure_ui', '--inputs', str(source),
            ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)
        output = json.loads(result.stderr)
        self.assertEqual(output['status'], 'NEEDS_BROWSER_RECOVERY')
        self.assertEqual(output['error_type'], 'Stop')

    def test_script_and_package_imports_share_stop_class(self):
        package = Path(__file__).resolve().parent
        source = (
            'import sys;'
            'sys.path.insert(0,' + repr(str(package)) + ');'
            'sys.path.insert(0,' + repr(str(package.parent)) + ');'
            'import skill6_playwright as direct;'
            'from playwright_recipes import skill6_playwright as packaged;'
            'assert direct is packaged;assert direct.Stop is packaged.Stop;'
            'print("SHARED_CORE")'
        )
        result = subprocess.run([sys.executable, '-c', source],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'SHARED_CORE')

    def test_named_code_update_preserves_native_target_identity(self):
        data = {
            'location_id': 'FIXTURE', 'location_name': 'Acceptance fixture',
            'start_url': 'https://app.convertandflow.com/v2/location/FIXTURE/editor/page',
            'file': 'approved.html', 'marker': 'Approved fixture', 'seo': {},
            'element_id': 'native_code', 'section_id': 'native_section',
            'expected_name': 'Approved Code',
        }
        step = compile_recipe('pages.install_code', data)['steps'][0]
        for key in ('element_id', 'section_id', 'expected_name'):
            self.assertEqual(step.get(key), data[key])

    def test_meeting_update_cannot_downgrade_into_create(self):
        inputs = {
            'location_id': 'FIXTURE', 'location_name': 'Acceptance fixture',
            'start_url': 'https://app.convertandflow.com/v2/location/FIXTURE/dashboard',
            'meeting': {'name': 'Fixture Room', 'slug': 'fixture-room',
                        'waiting_room': True, 'guest_users': False,
                        'open_room': False, 'allow_creation': True},
        }
        with self.assertRaises(runner.Stop):
            compile_recipe('meetings.update', inputs)
        inputs['meeting']['expected_room_id'] = 'https://fixture.example/room/current'
        compiled = compile_recipe('meetings.update', inputs)
        self.assertIs(compiled['steps'][0].get('allow_creation'), False)
        self.assertEqual(compiled['steps'][0]['expected_room_id'],
                         inputs['meeting']['expected_room_id'])

    def test_incomplete_handler_cannot_complete_or_continue_build(self):
        for status in ('NEEDS_CAPTURE', 'HANDOFF_REQUIRED', 'BLOCKED', 'API_ROUTE',
                       'NEEDS_VERIFICATION', 'STOP_AUTH', 'PENDING_CAPTURE',
                       'NO_OP', 'UNKNOWN'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                with patch.object(runner, 'assert_tenant'), patch.object(
                    runner, 'options', return_value={'status': status}
                ) as handler:
                    try:
                        result = runner.run_on_page(object(), two_steps(), directory)
                    except runner.Stop:
                        result = None
                state = json.loads(Path(directory, 'state.json').read_text())
                self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
                if result is not None:
                    self.assertNotEqual(result['status'], 'EDITOR_STEPS_COMPLETE')
                self.assertEqual(handler.call_count, 1, 'An incomplete step must stop later writes')

    def test_missing_handler_result_is_not_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, 'assert_tenant'), patch.object(
                runner, 'options', return_value=None
            ) as handler:
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(object(), two_steps(), directory)
            state = json.loads(Path(directory, 'state.json').read_text())
            self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
            self.assertEqual(handler.call_count, 1)

    def test_pending_independent_readback_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            job = two_steps()
            job['steps'] = job['steps'][:1]
            with patch.object(runner, 'assert_tenant'), patch.object(
                runner, 'options', return_value={
                    'status': 'RECORDED_OPTIONS_EXECUTED',
                    'independent_readback': 'REQUIRED',
                }
            ):
                try:
                    result = runner.run_on_page(object(), job, directory)
                except runner.Stop:
                    result = None
            state = json.loads(Path(directory, 'state.json').read_text())
            self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
            if result is not None:
                self.assertNotEqual(result['status'], 'EDITOR_STEPS_COMPLETE')


if __name__ == '__main__':
    unittest.main()
