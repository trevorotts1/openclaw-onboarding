"""Captured TEXT survey path, complete stage binding and uncertainty boundaries."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner
import test_survey_creation as legacy

front=importlib.import_module('playwright_recipes.survey_creation')
text=importlib.import_module('playwright_recipes.survey_text_questions')


def question():
    return {'label':'Tell us your goal','placeholder':'Your answer','short_label':'Goal',
        'query_key':'owned_goal','required':True,'hidden':False}


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'Native text survey','allow_creation':True,'slide_count':2,
        'question_batches':[{'kind':'text','target_slide':1,'questions':[question()]}]}


class SurveyTextPath(unittest.TestCase):
    def test_text_only_compilation_needs_no_radio_api_capability(self):
        job=recipe_cli.compile_recipe('surveys.create',inputs())
        with patch.object(front.radio,'validate_capability') as api:
            front.validate_runtime(job,None)
        api.assert_not_called()
        self.assertEqual(job['steps'][0]['action'],'native_survey_creation')
    def test_hidden_values_are_explicit_and_required_exclusive(self):
        hidden={**question(),'required':False,'hidden':True,'hidden_value':'fixture'}
        self.assertEqual(text.validate_question(hidden),hidden)
        for bad in ({**hidden,'required':True},{**question(),'hidden_value':''},
                {k:v for k,v in hidden.items() if k!='hidden_value'},
                {**question(),'required':1}):
            with self.subTest(bad=bad),self.assertRaises(runner.Stop):text.validate_question(bad)
    def test_text_targets_must_be_initially_empty_and_keys_unique(self):
        for mutation in ('standard','repeat','two','key','after_radio'):
            value=inputs()
            if mutation=='standard':value.pop('slide_count');value['standard_fields']=['Email','First Name']
            elif mutation=='repeat':value['question_batches']*=2
            elif mutation=='two':value['question_batches'][0]['questions']*=2
            elif mutation=='key':value['question_batches'].append({'kind':'text','target_slide':2,'questions':[question()]})
            else:
                from test_radio_dependencies import question as radio_question
                value['question_batches'].insert(0,{'kind':'radio','target_slide':1,'questions':[radio_question()]})
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front.validate_inputs(value)
    def test_incomplete_text_intent_refuses_without_insertion_or_save_retry(self):
        data=front.validate_inputs(inputs());binding={'editor_url':data['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        plan=front._text_plan(data,binding,data['question_batches'][0])
        with tempfile.TemporaryDirectory() as root:
            runner.secure_json(Path(root)/'single-line-state.json',{'configuration_sha256':text._fingerprint(plan),'status':'INTENT_RECORDED'})
            page=MagicMock()
            with patch.object(text,'_frame',return_value=MagicMock()),self.assertRaises(runner.Stop):text.configure(page,plan,root)
            page.mouse.down.assert_not_called()
    def test_saved_inventory_binds_text_properties_owner_and_full_original_canvas(self):
        plan=front.validate_inputs(inputs());binding={'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/NEW'),
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}
        done=[{'kind':'text','target_slide':1,'api_fields':[],'native_receipt':{}}]
        saved={'slide_labels':binding['slide_labels'],'slides':[
            {'canvas':[{'types':['TEXT'],'names':[['INPUT',None,None]]}],'radio_fields':[],'text_fields':[question()]},
            {'canvas':[],'radio_fields':[]}]}
        self.assertEqual(front._validate_inventory(saved,plan,binding,done),saved)
        for mutation in ('query','owner','extra','kind'):
            bad=deepcopy(saved)
            if mutation=='query':bad['slides'][0]['text_fields'][0]['query_key']='other'
            elif mutation=='owner':bad['slides'].reverse()
            elif mutation=='extra':bad['slides'][1]['canvas']=[{'types':['TEXT'],'names':[['INPUT',None,None]]}]
            else:bad['slides'][0]['canvas'][0]['types']=['LARGE_TEXT']
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front._validate_inventory(bad,plan,binding,done)
    def test_text_only_owned_creation_uses_no_schema_transport_and_validates_complete_receipt(self):
        # Reuse the maintained shell harness, replacing only the new native leaf.
        harness=legacy.WholeSurveyCreation('test_two_radio_target_slides_create_once_and_whole_saved_inventory_is_bound')
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        harness.data=inputs();harness.page.url=harness.data['start_url']
        harness.shell={'editor_url':harness.editor,'slide_labels':['P1 - Slide 1','P2 - Slide 2'],
            'slides':[{'canvas':[]},{'canvas':[]}]}
        def blank(page,plan,root):
            harness.shell_calls+=1;page.url=harness.editor
            runner.secure_json(Path(root)/'blank-shell-state.json',{'schema':'skill6-empty-survey-shell/1',
                'configuration_sha256':front.blank._fingerprint(plan),'status':'SAVED_AND_REOPENED','binding':harness.shell})
            return deepcopy(harness.shell)
        def leaf(page,plan,root):
            return {'status':'SURVEY_SINGLE_LINE_SAVED_AND_REOPENED','editor_url':harness.editor,
                'target_slide':1,'question':deepcopy(plan['question']),'configuration_sha256':text._fingerprint(plan),
                'saved_snapshot':[[],[]],'independent_readback':'VERIFIED'}
        saved={'slide_labels':harness.shell['slide_labels'],'slides':[
            {'canvas':[{'types':['TEXT'],'names':[['INPUT',None,None]]}],'radio_fields':[],'text_fields':[question()]},
            {'canvas':[],'radio_fields':[]}]}
        with harness.patches(),patch.object(front.blank,'configure',side_effect=blank),\
                patch.object(text,'configure',side_effect=leaf),patch.object(front,'_inventory',return_value=saved),\
                patch.object(front.radio,'Skill44RadioTransport') as api:
            result=harness.run_chain()
        api.assert_not_called();self.assertEqual(harness.shell_calls,1)
        self.assertEqual(result['question_batches'][0]['kind'],'text')
        self.assertFalse(result['submission_verified'])


if __name__=='__main__':unittest.main()
