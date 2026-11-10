"""Survey completion shares the executor and uses captured survey controls."""
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
from test_form_submission import NativeSubmissionExecution

submission=importlib.import_module('playwright_recipes.form_submission')


def inputs(mode='Message'):
    config=({'mode':mode,'message':'Approved survey completion.'} if mode=='Message' else
            {'mode':mode,'redirect_url':'https://example.com/survey-complete'})
    return {'location_id':'fixture','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/fixture/survey-builder-v2/survey',
        'configuration':{'submission':config}}


def receipt(spec,url):
    value=spec['message'] if spec['mode']=='Message' else spec['redirect_url']
    return {'status':'SURVEY_SUBMISSION_SAVED_AND_REOPENED','mode':spec['mode'],'editor_url':url,
        'value_sha256':hashlib.sha256(value.encode()).hexdigest(), 'conditional_precedence_present':False,
        'conditional_precedence_acknowledged':False, 'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}


class SurveySubmission(unittest.TestCase):
    def surface(self,**kw):
        page,frame,state=NativeSubmissionExecution().surface(**kw)
        page.url=inputs()['start_url'];original=frame.locator.side_effect
        redirect=frame.get_by_placeholder.return_value
        frame.locator.side_effect=lambda selector:redirect if selector=='#submitMessage input' else original(selector)
        roles=frame.get_by_role.side_effect;tab=MagicMock();tab.count.return_value=1;tab.is_visible.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:tab if role=='tab' else roles(role,**kw)
        return page,frame,state

    def configure(self,page,frame,config,**kwargs):
        def reopen(page,kind,name,url):
            self.assertEqual(kind,'survey');page.goto(url)
        with patch.object(runner,'visible',return_value=False), \
                patch.object(runner,'click',side_effect=lambda node:node.click()), \
                patch.object(runner,'fill',side_effect=lambda node,value:node.fill(value)), \
                patch('playwright_recipes.assessments.reopen_editor',side_effect=reopen) as reopen_mock:
            result=submission.configure(page,config,surface='survey',**kwargs)
        return result,reopen_mock

    def test_message_and_saved_value_redirect_control_save_then_independently_reopen(self):
        for mode in ('Message','Redirect to URL'):
            page,frame,state=self.surface()
            spec=inputs(mode)['configuration']['submission']
            result,reopen=self.configure(page,frame,spec)
            with self.subTest(mode=mode):
                self.assertEqual(result['status'],'SURVEY_SUBMISSION_SAVED_AND_REOPENED')
                self.assertEqual(state['saves'],1);reopen.assert_called_once()
                self.assertFalse(result['behavior_verified']);self.assertFalse(result['submission_verified'])
                frame.get_by_placeholder.assert_not_called()
                if mode=='Redirect to URL':self.assertEqual(state['redirect'],spec['redirect_url'])

    def test_precedence_order_and_lost_values_never_claim_success(self):
        page,frame,state=self.surface(precedence=True)
        with self.assertRaises(runner.Stop):self.configure(page,frame,inputs()['configuration']['submission'])
        self.assertEqual((state['saves'],state['fills']),(0,0))
        page,frame,state=self.surface();state['mode']='Order Confirmation'
        with self.assertRaises(runner.Stop):self.configure(page,frame,inputs()['configuration']['submission'])
        self.assertEqual(state['saves'],0)
        page,frame,state=self.surface(persist=False)
        with self.assertRaises(runner.Stop):self.configure(page,frame,inputs()['configuration']['submission'])

    def test_exclusive_intake_and_survey_route_refuse_before_browser(self):
        source=inputs();job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',source),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'survey_submission')
        for change in ('mixed','override','url'):
            bad=inputs()
            if change=='mixed':bad['configuration']['rules']=[]
            elif change=='override':bad['configuration']['submission']['action']='form_submission'
            else:bad['start_url']=bad['start_url'].replace('survey-builder-v2','form-builder-v2')
            with self.subTest(change=change),self.assertRaises((runner.Stop,submission.SubmissionError)):
                runner.validate_job(recipe_cli.compile_recipe('surveys.configure',bad),Path('.'))

    def test_runner_replay_checks_current_saved_value_without_writing_again(self):
        source=inputs();job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',source),Path('.'))
        spec=job['steps'][0];saved=receipt(spec,source['start_url']);page,frame,state=self.surface()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'):
            with patch.object(submission,'configure',return_value=saved) as write:
                runner.run_on_page(page,job,root)
            path=Path(root,'state.json');before=path.read_bytes()
            state['message']=spec['message'];persisted={'message':spec['message']}
            def reopen(current,kind,name,url):
                self.assertIs(current,page);self.assertEqual((kind,url),('survey',source['start_url']))
                state['message']=persisted['message']
            with patch.object(runner,'visible',return_value=False), \
                    patch('playwright_recipes.assessments.reopen_editor',side_effect=reopen) as fresh:
                result=runner.run_on_page(page,job,root)
                self.assertTrue(result['replayed'])
                # Another session saves a change while this page still shows approved text.
                persisted['message']='Changed remotely since completion'
                self.assertEqual(state['message'],spec['message'])
                with self.assertRaises(runner.Stop):runner.run_on_page(page,job,root)
                self.assertEqual(fresh.call_count,2)
            self.assertEqual(path.read_bytes(),before)
        write.assert_called_once();self.assertEqual(state['saves'],0);self.assertEqual(state['fills'],0)
        for changed in ('editor_url','value_sha256','behavior_verified'):
            bad=deepcopy(saved);bad[changed]=True if changed=='behavior_verified' else 'foreign'
            with self.subTest(changed=changed),self.assertRaises(submission.SubmissionError):submission.validate_completion(bad,spec,source['start_url'])


if __name__=='__main__':unittest.main()
