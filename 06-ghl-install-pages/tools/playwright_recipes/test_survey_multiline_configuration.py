"""Captured Multi Line property route, sibling preservation and fresh replay."""
from copy import deepcopy
from pathlib import Path
import importlib
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner
import editor_replay

edit=importlib.import_module('playwright_recipes.survey_multiline_configuration')
text=importlib.import_module('playwright_recipes.survey_text_questions')


def configuration():
    return json.loads((Path(__file__).parent/'examples/survey-multiline-properties.json').read_text())


def receipt(step):
    return {'status':'SURVEY_MULTILINE_PROPERTIES_SAVED_AND_REOPENED',
        'editor_url':step['payload']['start_url'],'configuration_sha256':edit.configuration_hash(step),
        'multiline_questions':deepcopy(step['payload']['multiline_questions']['desired']),
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}


class SurveyMultiLine(unittest.TestCase):
    def test_compile_execute_and_completed_replay_use_native_readback_without_rewriting(self):
        source=configuration();job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',source),Path('.'))
        step=job['steps'][0];self.assertEqual(step['action'],edit.ACTION)
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),\
                patch.object(edit,'configure',return_value=receipt(step)) as write,\
                patch.object(edit,'verify',return_value=receipt(step)) as verify:
            page=MagicMock();page.url=source['start_url']
            first=runner.run_on_page(page,job,root);again=runner.run_on_page(page,job,root)
        write.assert_called_once();verify.assert_called_once_with(page,step,receipt(step))
        self.assertTrue(again['replayed']);self.assertEqual(first['results'][0]['result'],receipt(step))
        bad=receipt(step);bad['multiline_questions'][1][0]['query_key']='other'
        with self.assertRaises(runner.Stop):editor_replay._result(step,bad,job)

    def test_parent_job_identity_cannot_differ_from_bound_native_payload(self):
        for key in ('location_id','location_name','start_url'):
            job=recipe_cli.compile_recipe('surveys.configure',configuration())
            if key=='start_url':job[key]=job[key].replace('/SURVEY','/OTHER')
            else:job[key]='OTHER'
            with self.subTest(key=key),self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))

    def test_complete_preflight_refuses_owner_drift_before_write(self):
        step=recipe_cli.compile_recipe('surveys.configure',configuration())['steps'][0]
        wrong=deepcopy(step['payload']['multiline_questions']['expected']);wrong[1][0]['query_key']='changed'
        with patch.object(text,'_frame',return_value=MagicMock()),patch.object(edit,'_inventory',return_value=wrong),\
                patch.object(text,'write_question') as write,self.assertRaises(runner.Stop):edit.configure(MagicMock(),step)
        write.assert_not_called()

    def test_writer_binds_large_text_and_preserves_single_line_sibling_after_reopen(self):
        step=recipe_cli.compile_recipe('surveys.configure',configuration())['steps'][0];plan=edit.validate(step)
        old=plan['multiline_questions']['expected'];new=plan['multiline_questions']['desired']
        before=[[{'types':['TEXT'],'labels':['Untouched'],'controls':[]}],[{'types':['LARGE_TEXT'],'labels':['Details'],'controls':[]}]]
        after=deepcopy(before);after[1][0]['labels']=['Your details']
        frame=MagicMock();save=frame.get_by_role.return_value;save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        with patch.object(text,'_frame',return_value=frame),patch.object(edit,'_inventory',side_effect=[old,new,new]),\
                patch.object(text,'snapshot',side_effect=[before,after,after]),patch.object(text,'read_question',return_value=old[1][0]),\
                patch.object(text,'write_question') as write,patch.object(edit,'reopen_editor') as reopen:
            result=edit.configure(MagicMock(),step)
        self.assertEqual(write.call_args.args[1]['_native_field_type'],'LARGE_TEXT')
        self.assertEqual(result,receipt(step));save.click.assert_called_once();reopen.assert_called_once()

    def test_completed_replay_detects_drift_without_any_write(self):
        step=recipe_cli.compile_recipe('surveys.configure',configuration())['steps'][0]
        with patch.object(text,'_frame',return_value=MagicMock()),patch.object(edit,'_inventory',return_value=[[],[]]),\
                patch.object(text,'write_question') as write,self.assertRaises(runner.Stop):edit.verify(MagicMock(),step,receipt(step))
        write.assert_not_called()

    def test_query_key_change_with_other_widgets_refuses_before_write(self):
        source=configuration();source['configuration']['multiline_questions']['desired'][1][0]['query_key']='new_details'
        step=recipe_cli.compile_recipe('surveys.configure',source)['steps'][0]
        with patch.object(text,'_frame',return_value=MagicMock()),patch.object(edit,'_inventory',return_value=step['payload']['multiline_questions']['expected']),\
                patch.object(text,'snapshot',return_value=[[{'types':['TEXT']}],[{'types':['LARGE_TEXT']}]]),\
                patch.object(text,'write_question') as write,self.assertRaises(runner.Stop):edit.configure(MagicMock(),step)
        write.assert_not_called()

    def test_incomplete_or_cross_location_profiles_refuse_before_browser(self):
        for mutation in ('omit','count','location','family'):
            source=configuration();config=source['configuration']['multiline_questions']
            if mutation=='omit':config['expected'].pop()
            elif mutation=='count':config['desired'][1].append(deepcopy(config['desired'][1][0]))
            elif mutation=='location':source['start_url']=source['start_url'].replace('/LOC/','/OTHER/')
            else:source['configuration']['_native_field_type']='TEXT'
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',source)


if __name__=='__main__':unittest.main()
