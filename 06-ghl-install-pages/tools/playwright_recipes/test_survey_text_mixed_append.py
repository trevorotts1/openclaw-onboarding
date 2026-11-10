"""Typed TEXT/LARGE_TEXT prior order, owner properties and uncertain append."""
from copy import deepcopy
from pathlib import Path
import importlib
import unittest
import tempfile
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
import test_survey_text_questions as base

front=importlib.import_module('playwright_recipes.survey_creation')
text=importlib.import_module('playwright_recipes.survey_text_questions')


def inputs():
    value=base.inputs();value['question_batches']=[]
    for index,kind in enumerate(('text','text','multiline','text','multiline'),1):
        value['question_batches'].append({'kind':kind,'target_slide':1,
            'questions':[{**base.question(),'query_key':'owned_'+str(index)}]})
    return value


def binding(plan):
    return {'editor_url':plan['start_url'].replace('survey-builder/main','survey-builder-v2/SURVEY'),
        'slide_labels':['P1 - Slide 1','P2 - Slide 2'],'slides':[{'canvas':[]},{'canvas':[]}]}


class MixedSurveyAppend(unittest.TestCase):
    def test_mixed_owned_batches_keep_complete_prior_order_and_family_positions(self):
        plan=front.validate_inputs(inputs());owner=binding(plan)
        runner.validate_job(recipe_cli.compile_recipe('surveys.create',inputs()),Path('.'))
        before_text=front._text_plan(plan,owner,plan['question_batches'][3])
        self.assertEqual(before_text['text_index'],3)
        self.assertEqual([row['kind'] for row in before_text['expected_prior_widgets']],['text','text','multiline'])
        before_large=front._text_plan(plan,owner,plan['question_batches'][4])
        self.assertEqual(before_large['text_index'],2)
        self.assertEqual([row['kind'] for row in before_large['expected_prior_widgets']],['text','text','multiline','text'])
        grouped=base.inputs();grouped['question_batches'][0]['kind']='multiline'
        grouped['question_batches'][0]['questions'].append({**base.question(),'query_key':'another'})
        self.assertEqual(len(front.validate_inputs(grouped)['question_batches']),2)

    def test_homogeneous_legacy_text_plan_serialization_is_unchanged(self):
        value=base.inputs();value['question_batches'][0]['questions'].append({**base.question(),'query_key':'second'})
        plan=front.validate_inputs(value);owner=binding(plan)
        first=front._text_plan(plan,owner,plan['question_batches'][0]);last=front._text_plan(plan,owner,plan['question_batches'][1])
        self.assertEqual(first['expected_prior'],[]);self.assertEqual(last['expected_prior'],[base.question()])
        self.assertNotIn('expected_prior_widgets',first);self.assertNotIn('_native_field_type',first)

    def test_prior_guard_checks_wrapper_family_order_and_every_question_property(self):
        plan=front.validate_inputs(inputs());native=front._text_plan(plan,binding(plan),plan['question_batches'][3])
        owner=MagicMock();wrappers=owner.locator.return_value;wrappers.count.return_value=3
        observed=[]
        def read(frame,target):
            observed.append((target['_native_field_type'],target['text_index']))
            return native['expected_prior_widgets'][len(observed)-1]['question']
        nodes=[MagicMock() for _ in range(3)]
        for node in nodes:node.locator.return_value.count.return_value=1
        wrappers.nth.side_effect=lambda index:nodes[index]
        with patch.object(text,'read_question',side_effect=read):bound=text._prior_questions(MagicMock(),native,owner)
        self.assertEqual(observed,[('TEXT',1),('TEXT',2),('LARGE_TEXT',1)]);self.assertEqual(len(bound),3)
        nodes[1].locator.return_value.count.return_value=0
        with patch.object(text,'read_question',return_value=native['expected_prior_widgets'][0]['question']),self.assertRaises(runner.Stop):
            text._prior_questions(MagicMock(),native,owner)

    def test_multiline_append_uses_one_blank_tail_drag_and_preserves_prior_texts(self):
        plan=front.validate_inputs(inputs());native=front._text_plan(plan,binding(plan),plan['question_batches'][2])
        prior=[({'_native_field_type':'TEXT','text_index':index},row['question']) for index,row in enumerate(native['expected_prior_widgets'],1)]
        frame=MagicMock();owners=MagicMock();owner=owners.nth.return_value
        owner.locator.return_value.count.return_value=3
        save=frame.get_by_role.return_value;save.is_enabled.return_value=True
        before=[[{'types':['TEXT']},{'types':['TEXT']}],[]];after=deepcopy(before);after[0].append({'types':['LARGE_TEXT']})
        defaults={'label':'Multi Line abc123','placeholder':'Type your message here','short_label':'',
            'query_key':'multi_line_abc123','required':False,'hidden':False}
        reads=[row[1] for row in prior]+[defaults,native['question']]
        with tempfile.TemporaryDirectory() as root,patch.object(text,'_frame',return_value=frame),\
                patch.object(text,'_owners',return_value=owners),patch.object(text,'_prior_questions',return_value=prior),\
                patch.object(text,'_one',side_effect=lambda value,*a:value),patch.object(text,'click',side_effect=lambda value:value.click()),\
                patch.object(text,'snapshot',side_effect=[before,after,after,after]),patch.object(text,'_close_initial'),\
                patch.object(text,'_append_populated') as drag,patch.object(text,'read_question',side_effect=reads),\
                patch.object(text,'write_question') as write,patch.object(text,'reopen_editor') as reopen:
            value=text.configure(MagicMock(),native,root)
        drag.assert_called_once();write.assert_called_once();reopen.assert_called_once()
        self.assertEqual(value['status'],'SURVEY_MULTI_LINE_SAVED_AND_REOPENED')
        self.assertEqual(value['saved_snapshot'],after)

    def test_complete_final_inventory_refuses_cross_family_reorder_and_hidden_property_drift(self):
        plan=front.validate_inputs(inputs());owner=binding(plan)
        complete=[{'kind':batch['kind'],'target_slide':1,'api_fields':[],'native_receipt':{}} for batch in plan['question_batches']]
        canvas=[{'types':['TEXT' if batch['kind']=='text' else 'LARGE_TEXT'],
            'names':[['INPUT' if batch['kind']=='text' else 'TEXTAREA',None,None]]} for batch in plan['question_batches']]
        saved={'slide_labels':owner['slide_labels'],'slides':[{'canvas':canvas,'radio_fields':[],
            'text_fields':[batch['questions'][0] for batch in plan['question_batches']]},{'canvas':[],'radio_fields':[]}]}
        self.assertEqual(front._validate_inventory(saved,plan,owner,complete),saved)
        for mutation in ('family_order','hidden_value'):
            wrong=deepcopy(saved)
            if mutation=='family_order':wrong['slides'][0]['canvas'][0],wrong['slides'][0]['canvas'][2]=wrong['slides'][0]['canvas'][2],wrong['slides'][0]['canvas'][0]
            else:wrong['slides'][0]['text_fields'][2]['hidden']=True;wrong['slides'][0]['text_fields'][2]['hidden_value']='unexpected'
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front._validate_inventory(wrong,plan,owner,complete)


if __name__=='__main__':unittest.main()
