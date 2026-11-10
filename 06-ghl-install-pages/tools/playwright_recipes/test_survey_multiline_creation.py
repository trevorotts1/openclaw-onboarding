"""Owned Multi Line insertion, complete inventory and uncertain-write safety."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import sys
import types
import unittest
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
import test_survey_text_questions as base

front=importlib.import_module('playwright_recipes.survey_creation')
text=importlib.import_module('playwright_recipes.survey_text_questions')


def inputs():
    result=base.inputs();result['question_batches'][0]['kind']='multiline'
    return result


def binding(plan):
    return {'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/SURVEY'),
        'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}


class SurveyMultiLineCreation(unittest.TestCase):
    def test_owned_creation_compiles_without_api_and_keeps_legacy_text_plan_unchanged(self):
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',inputs()),Path('.'))
        with patch.object(front.radio,'validate_capability') as api:front.validate_runtime(job,None)
        api.assert_not_called();self.assertEqual(job['steps'][0]['action'],'native_survey_creation')
        plan=front.validate_inputs(inputs());native=front._text_plan(plan,binding(plan),plan['question_batches'][0])
        self.assertEqual(native['_native_field_type'],'LARGE_TEXT')
        legacy=front.validate_inputs(base.inputs())
        self.assertNotIn('_native_field_type',front._text_plan(legacy,binding(legacy),legacy['question_batches'][0]))

    def test_uncaptured_radio_mixed_creation_refuses_before_browser(self):
        for kind in ('radio','radio_after'):
            value=inputs()
            other=deepcopy(value['question_batches'][0]);other['kind']=kind
            if kind in ('radio','radio_after'):
                other['kind']='radio'
                from test_radio_dependencies import question
                other['questions']=[question()]
                if kind=='radio':value['question_batches'].insert(0,other)
                else:value['question_batches'].append(other)
            else:
                other['questions'][0]['query_key']='different';value['question_batches'].append(other)
            with self.subTest(kind=kind),self.assertRaises(runner.Stop):front.validate_inputs(value)

    def test_complete_inventory_binds_actual_textarea_family_and_other_slides(self):
        plan=front.validate_inputs(inputs());owner=binding(plan)
        complete=[{'kind':'multiline','target_slide':1,'api_fields':[],'native_receipt':{}}]
        saved={'slide_labels':owner['slide_labels'],'slides':[
            {'canvas':[{'types':['LARGE_TEXT'],'names':[['TEXTAREA',None,None]]}],
             'radio_fields':[],'text_fields':[base.question()]},{'canvas':[],'radio_fields':[]}]}
        self.assertEqual(front._validate_inventory(saved,plan,owner,complete),saved)
        for mutation in ('family','sibling','property'):
            wrong=deepcopy(saved)
            if mutation=='family':wrong['slides'][0]['canvas'][0]['names']=[['INPUT',None,None]]
            elif mutation=='sibling':wrong['slides'][1]['canvas']=[{'types':['TEXT'],'names':[['INPUT',None,None]]}]
            else:wrong['slides'][0]['text_fields'][0]['label']='wrong'
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front._validate_inventory(wrong,plan,owner,complete)

    def test_native_empty_slide_creation_drags_once_saves_and_reopens(self):
        plan=front.validate_inputs(inputs());native=front._text_plan(plan,binding(plan),plan['question_batches'][0])
        frame=MagicMock();owners=MagicMock();owner=owners.nth.return_value
        wrappers=owner.locator.return_value;wrappers.count.side_effect=[0,1]
        owner.get_by_text.return_value.count.return_value=1
        save=frame.get_by_role.return_value;save.is_enabled.return_value=True
        before=[[],[]];after=[[{'types':['LARGE_TEXT'],'controls':[]}],[]]
        defaults={'label':'Multi Line 7210b0','placeholder':'Type your message here',
            'short_label':'','query_key':'multi_line_7210b0','required':False,'hidden':False}
        with tempfile.TemporaryDirectory() as root,patch.object(text,'_frame',return_value=frame),\
                patch.object(text,'_owners',return_value=owners),patch.object(text,'_one',side_effect=lambda value,*a:value),\
                patch.object(text,'click',side_effect=lambda value:value.click()),\
                patch.object(text,'snapshot',side_effect=[before,after,after,after]),patch.object(text,'_close_initial'),\
                patch.object(text,'read_question',side_effect=[defaults,base.question()]),\
                patch.object(text,'write_question') as write,patch.object(text,'reopen_editor') as reopen:
            result=text.configure(MagicMock(),native,root)
        self.assertEqual(result['status'],'SURVEY_MULTI_LINE_SAVED_AND_REOPENED')
        frame.get_by_role.return_value.locator.assert_any_call('[id="Multi Line1"]')
        frame.get_by_role.return_value.locator.return_value.locator.return_value.drag_to.assert_called_once()
        write.assert_called_once_with(frame,native,base.question());save.click.assert_called();reopen.assert_called_once()

    def test_completed_whole_survey_replay_reopens_inventory_without_recreating(self):
        step=recipe_cli.compile_recipe('surveys.create',inputs())['steps'][0]
        plan=front.validate(step);owner=binding(plan)
        done={'shell_binding':owner,'question_batches':[],'saved_inventory':{'saved':'native inventory'}}
        with patch.object(front,'validate_receipt',return_value=done),patch.object(front,'_binding',return_value=owner),\
                patch.object(front,'reopen_editor') as reopen,patch.object(front,'_inventory',return_value=done['saved_inventory']),\
                patch.object(text,'configure') as writer:
            self.assertEqual(front.verify(MagicMock(),step,{}),done)
        reopen.assert_called_once();writer.assert_not_called()
        with patch.object(front,'validate_receipt',return_value=done),patch.object(front,'_binding',return_value=owner),\
                patch.object(front,'reopen_editor'),patch.object(front,'_inventory',return_value={'changed':True}),\
                self.assertRaises(runner.Stop):front.verify(MagicMock(),step,{})

    def test_cli_completed_creation_reaches_fresh_native_drift_check_without_creation_capability(self):
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',inputs()),Path('.'))
        step=job['steps'][0];plan=front.validate(step);owner=binding(plan)
        done={'shell_binding':owner,'question_batches':[],'saved_inventory':{'old':'inventory'}}
        replay={'results':[{'id':step['id'],'action':step['action'],'result':done}],'replayed':True}
        replay_module=importlib.import_module('playwright_recipes.editor_replay')
        runtime=importlib.import_module('playwright_recipes.survey_radio_creation')
        sync=MagicMock();pw=sync.return_value.__enter__.return_value
        browser=pw.chromium.connect_over_cdp.return_value
        page=MagicMock();page.url=job['start_url'];browser.contexts=[types.SimpleNamespace(pages=[page])]
        module=types.ModuleType('playwright.sync_api');module.sync_playwright=sync
        with tempfile.TemporaryDirectory() as root,patch.dict(sys.modules,{'playwright.sync_api':module}),\
                patch.dict(runner.os.environ,{'GHL_MANAGED_CDP_URL':'http://127.0.0.1:9222','GHL_BROWSER_LOCK_DIR':root}),\
                patch.object(replay_module,'completed_editor_replay',return_value=replay),patch.object(runner,'assert_tenant'),\
                patch.object(runtime,'validate_runtime') as capability,patch.object(front,'validate_receipt',return_value=done),\
                patch.object(front,'_binding',return_value=owner),patch.object(front,'reopen_editor') as reopen,\
                patch.object(front,'_inventory',return_value={'drift':'current native inventory'}),\
                patch.object(text,'configure') as create:
            runner.secure_json(Path(root)/'state.json',{'retained':'completed journal'})
            with self.assertRaisesRegex(runner.Stop,'Completed whole-survey inventory changed'):
                runner.execute(job,root)
        pw.chromium.connect_over_cdp.assert_called_once();reopen.assert_called_once()
        capability.assert_not_called();create.assert_not_called()

    def test_uncertain_multiline_intent_never_repeats_drag_or_save(self):
        plan=front.validate_inputs(inputs());native=front._text_plan(plan,binding(plan),plan['question_batches'][0])
        with tempfile.TemporaryDirectory() as root:
            runner.secure_json(Path(root)/'multi-line-state.json',{'configuration_sha256':text._fingerprint(native),'status':'INTENT_RECORDED'})
            page=MagicMock()
            with patch.object(text,'_frame',return_value=MagicMock()),self.assertRaises(runner.Stop):text.configure(page,native,root)
            page.mouse.down.assert_not_called()


if __name__=='__main__':unittest.main()
