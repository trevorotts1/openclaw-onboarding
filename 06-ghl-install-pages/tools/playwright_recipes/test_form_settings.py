import unittest
from pathlib import Path
from recipe_cli import compile_recipe
from skill6_playwright import Stop, validate_job


class FormSettingsTests(unittest.TestCase):
    def inputs(self, settings):
        return {'location_id':'fixture', 'location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/fixture/form-builder/main',
                'settings':settings}

    def test_explicit_settings_compile_to_native_action(self):
        job = validate_job(compile_recipe('forms.settings', self.inputs(
            {'recommendations':False, 'capture_timezone':True})), Path('.'))
        self.assertEqual(job['steps'][0]['action'], 'form_settings')
        self.assertEqual(job['steps'][0]['settings']['recommendations'], False)

    def test_missing_dependent_settings_and_string_booleans_refused(self):
        for settings in ({}, {'capture_timezone':'false'}, {'schedule_visibility':True}):
            with self.subTest(settings=settings), self.assertRaises(Stop):
                validate_job(compile_recipe('forms.settings', self.inputs(settings)), Path('.'))


if __name__ == '__main__':
    unittest.main()
