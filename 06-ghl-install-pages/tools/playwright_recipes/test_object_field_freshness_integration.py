"""Aged API reads may replay completed jobs, never authorize a new insertion."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock

import forms_advanced as native
import recipe_cli
import skill6_playwright as runner
import survey_fields
from test_object_field_dependencies import payload
from skill6_playwright import Stop


def survey_data():
    data=payload()['payload']
    data['start_url']=data['start_url'].replace('/form-builder-v2/','/survey-builder-v2/')
    config={key:data.pop(key) for key in ('object_fields','field_dependencies')}
    config.update(expected_slide_count=1,target_slide=1,slide_labels=['P1 - Welcome'])
    data['configuration']=config
    return data


class FreshnessIntegrationTests(unittest.TestCase):
    def test_survey_intake_compiler_and_job_validator_use_real_shared_validation(self):
        data=survey_data()
        job=recipe_cli.compile_recipe('surveys.configure',data)
        validated=runner.validate_job(job,Path('.'))
        self.assertEqual(validated['steps'][0]['action'],'native_survey_object_fields')
        self.assertEqual(survey_fields.validate(validated['steps'][0]),validated['steps'][0])

    def test_stale_receipt_compiles_and_hashes_but_cannot_start_new_form_execution(self):
        data=payload()
        data['payload']['field_dependencies']['observed_at']=0
        self.assertEqual(native.validate_object_fields(data,require_fresh=False),data)
        digest=native.object_fields_configuration_hash(data)
        self.assertEqual(len(digest),64)
        page=Mock()
        with self.assertRaisesRegex(Stop,'fresh verified'):
            native.configure_object_fields(page,data)
        self.assertFalse(page.mock_calls)

    def test_stale_survey_can_retain_completed_identity_but_not_enter_native_editor(self):
        data=survey_data()
        data['configuration']['field_dependencies']['observed_at']=0
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',data),Path('.'))
        step=job['steps'][0]
        self.assertEqual(len(survey_fields.configuration_hash(step)),64)
        page=Mock()
        with self.assertRaisesRegex(Stop,'fresh verified'):
            survey_fields.configure(page,step)
        self.assertFalse(page.mock_calls)

    def test_structural_validation_does_not_ignore_foreign_or_unverified_receipts(self):
        for change in ({'status':'UNVERIFIED'},{'location_id':'FOREIGN'},
                       {'http_status':True},{'observed_at':float('nan')}):
            data=payload();data['payload']['field_dependencies'].update(change)
            with self.subTest(change=change),self.assertRaises(Stop):
                native.validate_object_fields(data,require_fresh=False)
            with self.subTest(hash_change=change),self.assertRaises(Stop):
                native.object_fields_configuration_hash(data)

    def test_replay_hash_binds_selected_definitions_while_observation_age_changes(self):
        data=payload()
        digest=native.object_fields_configuration_hash(data)
        aged=deepcopy(data);aged['payload']['field_dependencies']['observed_at']=0
        self.assertEqual(native.object_fields_configuration_hash(aged),digest)
        changed=deepcopy(aged)
        changed['payload']['object_fields'][0]['options']=['Different','Options']
        with self.assertRaisesRegex(Stop,'differ'):
            native.object_fields_configuration_hash(changed)


if __name__=='__main__':unittest.main()
