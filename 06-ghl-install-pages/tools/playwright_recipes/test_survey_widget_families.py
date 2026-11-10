"""Survey Number uses its captured profile and preserves slide ownership."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner

native = importlib.import_module('playwright_recipes.survey_widget_families')


def inputs():
    before = {'label':'Count', 'placeholder':'Enter a number', 'short_label':'',
              'query_key':'count', 'custom_field_name':'Count', 'unique_key':'contact.count',
              'required':False, 'hidden':False}
    after = {**before, 'label':'How many seats?', 'short_label':'Seats', 'required':True}
    return {'location_id':'LOC', 'location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
        'configuration':{'expected_survey_name':'Approved survey', 'expected_slide_count':2,
            'slide_labels':['P1 - Contact', 'P2 - Details'],
            'widget_fields':{
                'expected':[[], [{'kind':'number', 'index':2, 'properties':before}]],
                'desired':[[], [{'kind':'number', 'index':2, 'properties':after}]]}}}


def step():
    return recipe_cli.compile_recipe('surveys.configure', inputs())['steps'][0]


def receipt(spec):
    plan = native.validate(spec)
    return {'status':'SURVEY_WIDGET_FIELDS_SAVED_AND_REOPENED',
        'editor_url':plan['start_url'], 'configuration_sha256':native.configuration_hash(spec),
        'widget_fields':deepcopy(plan['widget_fields']['desired']),
        'saved_snapshot':[[{'types':['TEXT']}], [{'types':['LARGE_TEXT']}, {'types':['NUMERICAL']}]],
        'independent_readback':'VERIFIED', 'behavior_verified':False, 'submission_verified':False}


class SurveyWidgetFamilies(unittest.TestCase):
    def test_number_compiles_with_survey_profile_and_parent_binding(self):
        job = runner.validate_job(recipe_cli.compile_recipe('surveys.configure', inputs()), Path('.'))
        spec = job['steps'][0]
        self.assertEqual(spec['action'], native.ACTION)
        self.assertEqual(native.NUMBER['properties']['label'], '#fieldTitle input')
        self.assertNotIn('width', native.NUMBER['properties'])
        native.validate_receipt(receipt(spec), spec)
        for key in native.COMMON:
            bad = deepcopy(job)
            bad['steps'][0]['payload'][key] += 'foreign'
            with self.subTest(key=key), self.assertRaises(runner.Stop):
                runner.validate_job(bad, Path('.'))

    def test_uncaptured_families_form_width_and_canonical_metadata_refuse(self):
        for key, value in [('kind','checkbox'), ('width',80),
                           ('custom_field_name','Changed global field'), ('unique_key','contact.other')]:
            source = inputs()
            field = source['configuration']['widget_fields']['desired'][1][0]
            if key == 'kind': field[key] = value
            else: field['properties'][key] = value
            with self.subTest(key=key), self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('surveys.configure', source)

    def test_property_edits_preserve_siblings_save_once_and_reopen(self):
        spec = step(); plan = native.validate(spec); frame = MagicMock()
        save = frame.get_by_role.return_value
        save.count.return_value = 1; save.is_visible.return_value = True; save.is_enabled.return_value = True
        before = plan['widget_fields']['expected']; desired = plan['widget_fields']['desired']
        state = {'fields':deepcopy(before)}
        base = receipt(spec)['saved_snapshot']
        def snapshot(*args):
            result = deepcopy(base)
            result[1][1]['label'] = state['fields'][1][0]['properties']['label']
            return result
        def write(*args, **kwargs):
            self.assertEqual(kwargs['profile'], native.NUMBER)
            state['fields'] = deepcopy(desired)
        with patch.object(native,'_frame',return_value=frame), \
                patch.object(native,'_inventory',side_effect=lambda *a:deepcopy(state['fields'])), \
                patch.object(native.survey,'_owners',return_value=MagicMock()), \
                patch.object(native.survey,'snapshot',side_effect=snapshot), \
                patch.object(native.shared,'_write',side_effect=write) as writer, \
                patch.object(native,'reopen_editor') as reopen:
            result = native.configure(MagicMock(), spec)
        writer.assert_called_once(); save.click.assert_called_once(); reopen.assert_called_once()
        self.assertEqual(result['widget_fields'], desired)
        self.assertEqual(result['saved_snapshot'][1][0], base[1][0])

    def test_unknown_family_query_inventory_refuses_rename_before_write(self):
        spec = step()
        spec['payload']['widget_fields']['desired'][1][0]['properties']['query_key'] = 'renamed'
        frame = MagicMock()
        with patch.object(native,'_frame',return_value=frame), \
                patch.object(native,'_inventory',return_value=spec['payload']['widget_fields']['expected']), \
                patch.object(native.survey,'snapshot',return_value=receipt(spec)['saved_snapshot']), \
                patch.object(native.shared,'_write') as writer, self.assertRaises(runner.Stop):
            native.configure(MagicMock(),spec)
        writer.assert_not_called(); frame.get_by_role.assert_not_called()

    def test_runner_completed_replay_reads_fresh_state_and_refuses_drift(self):
        job = runner.validate_job(recipe_cli.compile_recipe('surveys.configure',inputs()), Path('.'))
        spec = job['steps'][0]; saved = receipt(spec); page = MagicMock()
        with tempfile.TemporaryDirectory() as root, patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=saved) as writer:
            runner.run_on_page(page,job,root)
            state = Path(root,'state.json'); previous = state.read_bytes()
            with patch.object(native,'reopen_editor') as reopen, \
                    patch.object(native,'_frame',return_value=MagicMock()), \
                    patch.object(native,'_inventory',return_value=[]), self.assertRaises(runner.Stop):
                runner.run_on_page(page,job,root)
            self.assertEqual(state.read_bytes(),previous)
        writer.assert_called_once(); reopen.assert_called_once()


if __name__ == '__main__': unittest.main()
