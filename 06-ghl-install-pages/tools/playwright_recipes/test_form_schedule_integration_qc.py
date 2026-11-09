"""Scheduling receipts must bind editor writes without inventing behavior proof."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import host
import recipe_cli
import skill6_playwright as runner
import test_editor_hydration as hydration
from playwright_recipes import form_schedule


BASE = 'https://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/FORM'


def inputs(enabled=False):
    schedule = {'enabled': False}
    if enabled:
        schedule = {'enabled': True, 'time_zone': 'America/New_York',
                    'opens': {'mode': 'at', 'date': '2030-01-10', 'time': '09:00'},
                    'closes': {'mode': 'at', 'date': '2030-01-11', 'time': '17:30'},
                    'before': {'mode': 'redirect', 'url': 'https://example.com/before'},
                    'after': {'mode': 'message', 'message': 'Registration has closed.'}}
    return {'location_id': 'FIXTURE', 'location_name': 'Schedule fixture',
            'start_url': BASE, 'schedule': schedule}


def outcome(schedule):
    return {'status': 'FORM_SCHEDULE_SAVED_AND_REOPENED', 'editor_url': BASE,
            'enabled': schedule['enabled'],
            'configuration_sha256': form_schedule.configuration_hash(schedule),
            'independent_readback': 'VERIFIED', 'behavior_verified': False,
            'submission_verified': False}


class FormScheduleIntegrationQcTests(unittest.TestCase):
    def job(self, data):
        return runner.validate_job(recipe_cli.compile_recipe('forms.settings', data), Path('.'))

    def test_combined_recipe_keeps_schedule_before_ordinary_flags_without_mutating_input(self):
        data = inputs(True)
        data['settings'] = {'sticky_contact': True}
        original = deepcopy(data)
        job = self.job(data)
        self.assertEqual([s['action'] for s in job['steps']],
                         ['native_form_schedule', 'form_settings'])
        self.assertEqual(job['steps'][0]['schedule'], data['schedule'])
        self.assertEqual(job['steps'][1]['settings'], data['settings'])
        self.assertEqual(data, original)

    def test_invalid_schedule_or_later_flags_refuse_before_browser_acquisition(self):
        variants = [
            {'schedule': {'enabled': 'false'}},
            {'schedule': {'enabled': False, 'before': {'mode': 'message', 'message': 'ignored'}}},
            {'settings': {'sticky_contact': 'true'}},
            {'settings': {'unsupported_setting': True}},
        ]
        for change in variants:
            page = Mock()
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root, \
                    patch.object(host, 'execute') as execute:
                result = host.run_recipe('forms.settings', {**inputs(), **change},
                    {'lanes': {'playwright': {'available': True}}}, root,
                    input_dir='.', page=page)
            self.assertEqual(result['status'], 'STOP_INVALID_INPUT')
            self.assertEqual(page.mock_calls, [])
            execute.assert_not_called()

    def test_wrapper_initial_and_replay_remain_pending_without_another_schedule_write(self):
        for enabled in (False, True):
            data = inputs(enabled)
            job = self.job(data)
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as root, \
                    patch.object(runner, 'assert_tenant'), \
                    patch('playwright_recipes.form_schedule.configure',
                          return_value=outcome(data['schedule'])) as configure:
                first = runner.run_on_page(object(), job, root)
                repeated = runner.run_on_page(object(), job, root)
            self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['verification_required'], [job['steps'][0]['id']])
            self.assertTrue(repeated['replayed'])
            self.assertEqual(configure.call_count, 1)
            self.assertEqual(configure.call_args.args[1], job['steps'][0])
            self.assertIs(repeated['results'][0]['result']['enabled'], enabled)

    def test_corrupt_schedule_receipts_refuse_before_identity_read_or_mutation(self):
        corruptions = [
            lambda state: state['results'][0]['result'].update(configuration_sha256='0' * 64),
            lambda state: state['results'][0]['result'].update(enabled=True),
            lambda state: state['results'][0]['result'].update(enabled=0),
            lambda state: state['results'][0]['result'].update(independent_readback='REQUIRED'),
            lambda state: state['results'][0]['result'].update(behavior_verified=True),
            lambda state: state['results'][0]['result'].update(submission_verified=True),
            lambda state: state['results'][0]['result'].update(editor_url=BASE.replace('/FIXTURE/', '/OTHER/')),
            lambda state: state['results'][0]['result'].update(editor_url=BASE.replace('/FORM', '/DIFFERENT_FORM')),
            lambda state: state.update(verification_required=[]),
            lambda state: state.update(status='EDITOR_STEPS_COMPLETE'),
        ]
        for index, corrupt in enumerate(corruptions):
            data = inputs()
            job = self.job(data)
            with self.subTest(index=index), tempfile.TemporaryDirectory() as root, \
                    patch.object(runner, 'assert_tenant') as identity, \
                    patch('playwright_recipes.form_schedule.configure',
                          return_value=outcome(data['schedule'])) as configure:
                runner.run_on_page(object(), job, root)
                path = Path(root, 'state.json')
                state = json.loads(path.read_text())
                corrupt(state)
                damaged = json.dumps(state)
                path.write_text(damaged)
                identity.reset_mock()
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(object(), job, root)
                identity.assert_not_called()
                self.assertEqual(configure.call_count, 1)
                self.assertEqual(path.read_text(), damaged)

    def test_supplied_same_tenant_foreign_editor_refuses_before_schedule_writer(self):
        job = self.job(inputs())
        page = hydration.Page('form-builder-v2/DIFFERENT_FORM')
        page.frames['form-builder-app'] = 1
        with tempfile.TemporaryDirectory() as root, \
                patch('playwright_recipes.form_schedule.configure',
                      return_value=outcome(inputs()['schedule'])) as configure:
            with self.assertRaises(runner.Stop):
                runner.run_on_page(page, job, root)
            configure.assert_not_called()

    def test_private_authored_schedule_extras_do_not_escape_receipt_replay(self):
        data = inputs(True)
        job = self.job(data)
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'assert_tenant'), \
                patch('playwright_recipes.form_schedule.configure',
                      return_value=outcome(data['schedule'])) as configure:
            runner.run_on_page(object(), job, root)
            path = Path(root, 'state.json')
            state = json.loads(path.read_text())
            state['results'][0]['result']['schedule'] = {'private': 'PRIVATE_QC_MARKER'}
            state['results'][0]['result']['native_response'] = 'PRIVATE_QC_MARKER'
            damaged = json.dumps(state)
            path.write_text(damaged)
            result = runner.run_on_page(object(), job, root)
            self.assertNotIn('PRIVATE_QC_MARKER', json.dumps(result))
            self.assertNotIn(data['schedule']['after']['message'], json.dumps(result))
            self.assertEqual(configure.call_count, 1)
            self.assertEqual(path.read_text(), damaged)


if __name__ == '__main__':
    unittest.main()
