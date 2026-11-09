"""Named built-in placement must keep compiler, writer and replay boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import field_placement
import host
import recipe_cli
import skill6_playwright as runner


BASE = 'https://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/FORM'


def inputs():
    return {'location_id': 'FIXTURE', 'location_name': 'Placement fixture',
            'start_url': BASE, 'add_fields': ['Website', 'Organization']}


def placement_outcome(labels, *, reused=False):
    return {'status': 'BUILTIN_FIELDS_REUSED_AND_REOPENED' if reused else 'BUILTIN_FIELDS_SAVED_AND_REOPENED',
            'editor_url': BASE, 'submission_verified': False,
            'fields': [{'field': label,
                        'query_keys': list(field_placement.CAPTURED_FIELDS[label]['query_keys']),
                        'placement': 'reused' if reused else 'added'} for label in labels]}


class FieldPlacementIntegrationTests(unittest.TestCase):
    def job(self, data=None):
        return runner.validate_job(recipe_cli.compile_recipe('forms.configure', data or inputs()), Path('.'))

    def test_named_combined_request_keeps_placement_before_property_edits(self):
        data = inputs()
        data['fields'] = [{'field': 'First Name', 'required': True}]
        original = deepcopy(data)
        job = self.job(data)
        self.assertEqual([step['action'] for step in job['steps']],
                         ['native_field_placement', 'native_fields'])
        self.assertEqual(job['steps'][0]['add_fields'], data['add_fields'])
        self.assertEqual(job['steps'][1]['fields'], data['fields'])
        self.assertEqual(len({step['id'] for step in job['steps']}), 2)
        self.assertEqual(data, original)

    def test_invalid_placement_or_later_property_spec_stops_before_browser_reads(self):
        changes = [{'add_fields': []}, {'add_fields': ['Custom Field']},
                   {'add_fields': ['Website', 'Website']},
                   {'add_fields': ['Address', 'City']},
                   {'fields': [{'field': 'First Name', 'required': 'true'}]}]
        for change in changes:
            data = {**inputs(), **change}
            page = Mock()
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root, \
                    patch.object(host, 'execute') as execute:
                result = host.run_recipe('forms.configure', data,
                    {'lanes': {'playwright': {'available': True}}}, root,
                    input_dir='.', page=page)
            self.assertEqual(result['status'], 'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(page.mock_calls, [])
            execute.assert_not_called()

    def test_real_wrapper_dispatch_and_replay_preserve_pending_without_second_placement(self):
        for reused in (False, True):
            data = inputs()
            job = self.job(data)
            outcome = placement_outcome(data['add_fields'], reused=reused)
            with self.subTest(reused=reused), tempfile.TemporaryDirectory() as root, \
                    patch.object(runner, 'assert_tenant'), \
                    patch('playwright_recipes.field_placement.configure', return_value=outcome) as configure:
                first = runner.run_on_page(object(), job, root)
                repeated = runner.run_on_page(object(), job, root)
                self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
                self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
                self.assertEqual(repeated['verification_required'], [job['steps'][0]['id']])
                self.assertTrue(repeated['replayed'])
                self.assertEqual(configure.call_count, 1)
                self.assertEqual(configure.call_args.args[1], job['steps'][0])
                self.assertEqual(repeated['results'][0]['result']['fields'], outcome['fields'])
                state = json.loads(Path(root, 'state.json').read_text())
                self.assertEqual(state['current_step_status'], 'FINISHED')
                self.assertNotIn('failed_step', state)

    def test_combined_dispatch_runs_in_order_and_replay_repeats_neither_write(self):
        data = inputs()
        data['fields'] = [{'field': 'First Name', 'required': True}]
        job = self.job(data)
        calls = []
        def place(page, step):
            calls.append('placement')
            return placement_outcome(data['add_fields'])
        def edit(page, step):
            calls.append('properties')
            return {'status': 'FIELD_PROPERTIES_SAVED_AND_REOPENED',
                    'editor_url': BASE, 'fields': ['First Name'], 'submission_verified': False}
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'assert_tenant'), \
                patch('playwright_recipes.field_placement.configure', side_effect=place), \
                patch('playwright_recipes.assessments.configure_fields', side_effect=edit):
            first = runner.run_on_page(object(), job, root)
            repeated = runner.run_on_page(object(), job, root)
        self.assertEqual(calls, ['placement', 'properties'])
        self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
        self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
        self.assertEqual(repeated['verification_required'], [step['id'] for step in job['steps']])

    def test_corrupt_placement_replay_refuses_before_identity_read_or_mutation(self):
        mutations = [
            lambda result: result['fields'].reverse(),
            lambda result: result['fields'][0].update(query_keys=['foreign_query']),
            lambda result: result['fields'][0].update(placement='unknown'),
            lambda result: result.update(fields=[]),
            lambda result: result.update(status='BUILTIN_FIELDS_REUSED_AND_REOPENED'),
            lambda result: result.update(submission_verified=True),
            lambda result: result.update(editor_url=BASE.replace('/FIXTURE/', '/FOREIGN/')),
        ]
        for index, mutate in enumerate(mutations):
            data = inputs()
            job = self.job(data)
            with self.subTest(corruption=index), tempfile.TemporaryDirectory() as root, \
                    patch.object(runner, 'assert_tenant') as identity, \
                    patch('playwright_recipes.field_placement.configure',
                          return_value=placement_outcome(data['add_fields'])) as configure:
                runner.run_on_page(object(), job, root)
                path = Path(root, 'state.json')
                state = json.loads(path.read_text())
                mutate(state['results'][0]['result'])
                damaged = json.dumps(state)
                path.write_text(damaged)
                identity.reset_mock()
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(object(), job, root)
                identity.assert_not_called()
                self.assertEqual(configure.call_count, 1)
                self.assertEqual(path.read_text(), damaged)

    def test_private_nested_extras_never_escape_a_valid_placement_replay(self):
        data = inputs()
        job = self.job(data)
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'assert_tenant'), \
                patch('playwright_recipes.field_placement.configure',
                      return_value=placement_outcome(data['add_fields'])) as configure:
            runner.run_on_page(object(), job, root)
            path = Path(root, 'state.json')
            state = json.loads(path.read_text())
            state['results'][0]['result']['private_response'] = 'PRIVATE_FIXTURE_ONLY'
            state['results'][0]['result']['fields'][0]['private_response'] = 'PRIVATE_FIXTURE_ONLY'
            damaged = json.dumps(state)
            path.write_text(damaged)
            result = runner.run_on_page(object(), job, root)
            self.assertNotIn('PRIVATE_FIXTURE_ONLY', json.dumps(result))
            self.assertEqual(configure.call_count, 1)
            self.assertEqual(path.read_text(), damaged)


if __name__ == '__main__':
    unittest.main()
