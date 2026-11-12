"""Real intake/compiler/runner/journal binding for independently captured question paths."""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import editor_replay
import recipe_cli
import skill6_playwright as runner

class QuestionIntegration(unittest.TestCase):
    def dropdown(self):
        from test_dropdown_fields import plan
        data=plan()['payload']
        return runner.validate_job(recipe_cli.compile_recipe('forms.configure',data),Path('.'))
    def large_text(self):
        from test_large_text_fields import plan
        return runner.validate_job(recipe_cli.compile_recipe('forms.configure',plan()['payload']),Path('.'))
    def quiz(self):
        from test_quiz_text_questions import step
        data=step()['payload'];base={k:data.pop(k) for k in ('location_id','location_name','start_url')}
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',{**base,'configuration':{'short_answer_questions':data}}),Path('.'))
    def receipt(self,job):
        step=job['steps'][0];p=step['payload']
        common={'editor_url':job['start_url'],'independent_readback':'VERIFIED','submission_verified':False,'behavior_verified':False}
        if step['action'] in ('native_dropdown_fields','native_large_text_fields'):
            if step['action']=='native_dropdown_fields':
                from playwright_recipes.dropdown_fields import configuration_hash
                key='dropdown_fields';status='DROPDOWN_FIELDS_SAVED_AND_REOPENED'
            else:
                from playwright_recipes.large_text_fields import configuration_hash
                key='large_text_fields';status='LARGETEXT_FIELDS_SAVED_AND_REOPENED'
            return {**common,'status':status,'configuration_sha256':configuration_hash(step),
                'fields':[{**{k:f[k] for k in ('id','field_key','data_type','native_query_key')},'placement':'added'} for f in p[key]]}
        from playwright_recipes.quiz_text_questions import configuration_hash
        return {**common,'status':'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED','kind':'quiz_short_answers',
                'configuration_sha256':configuration_hash(step),'target_page':p['target_page'],
                'question_count':len(p['questions']),'dependency_api_used':False}
    def test_both_paths_bind_real_compiler_and_completed_replay_without_second_insert(self):
        from playwright_recipes import dropdown_fields,quiz_text_questions,large_text_fields
        for job,module in ((self.dropdown(),dropdown_fields),(self.large_text(),large_text_fields),(self.quiz(),quiz_text_questions)):
            with self.subTest(action=job['steps'][0]['action']),tempfile.TemporaryDirectory() as root,ExitStack() as patches:
                patches.enter_context(patch.object(runner,'assert_tenant'))
                write=patches.enter_context(patch.object(module,'configure',return_value=self.receipt(job)))
                verify=None
                if job['steps'][0]['action'] in ('native_dropdown_fields','native_large_text_fields'):
                    verify=patches.enter_context(patch.object(module,'verify_completed',side_effect=lambda page,step,result:module.validate_receipt(result,step)))
                page=object();first=runner.run_on_page(page,job,root)
                with patch('time.time',return_value=time.time()+3700):second=runner.run_on_page(page,job,root)
                self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertEqual(second['status'],'NEEDS_VERIFICATION');write.assert_called_once()
                if verify is not None:verify.assert_called_once_with(page,job['steps'][0],self.receipt(job))
    def test_quiz_receipt_cannot_promote_or_retarget_completed_insert(self):
        job=self.quiz();s=job['steps'][0];r=self.receipt(job)
        for change in ({'question_count':0},{'target_page':2},{'configuration_sha256':'0'*64},{'dependency_api_used':True},{'submission_verified':True},{'kind':'quiz'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):editor_replay._result(s,{**r,**change},job)
    def test_dropdown_receipt_requires_exact_api_and_native_query_identities(self):
        job=self.dropdown();s=job['steps'][0];r=self.receipt(job)
        for key in ('id','field_key','data_type','native_query_key','placement'):
            bad=deepcopy(r);bad['fields'][0][key]='FOREIGN'
            with self.subTest(key=key),self.assertRaises(runner.Stop):editor_replay._result(s,bad,job)
    def test_special_jobs_refuse_discarded_sibling_requests(self):
        from test_dropdown_fields import plan
        from test_quiz_text_questions import step
        data=plan()['payload'];data['fields']=[{'name':'Email'}]
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',data)
        p=step()['payload'];base={k:p.pop(k) for k in ('location_id','location_name','start_url')}
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('quizzes.configure',{**base,'configuration':{'short_answer_questions':p,'result_page':{}}})
    def test_payloads_cannot_cross_parent_tenant_or_editor(self):
        for job in (self.dropdown(),self.large_text(),self.quiz()):
            job['steps'][0]['payload']['location_name']='FOREIGN'
            with self.assertRaises(runner.Stop):runner.validate_job(job,Path('.'))
