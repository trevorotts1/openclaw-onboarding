"""Survey populated append, complete property edits and maintained dispatch."""
from copy import deepcopy
from pathlib import Path
import importlib
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import recipe_cli
import skill6_playwright as runner
import editor_replay
import test_survey_text_questions as base

front=importlib.import_module('playwright_recipes.survey_creation')
text=importlib.import_module('playwright_recipes.survey_text_questions')
edit=importlib.import_module('playwright_recipes.survey_text_configuration')


def second():return {**base.question(),'label':'Second question','query_key':'owned_second'}


def configuration():
    source=base.inputs()
    before=[[base.question(),second()],[]];after=deepcopy(before)
    after[0][0].update(label='Updated goal',required=False,hidden=True,hidden_value='fixture')
    return {**{key:source[key] for key in text.COMMON},
        'start_url':source['start_url'].replace('survey-builder/main','survey-builder-v2/SURVEY'),
        'configuration':{'expected_survey_name':'ZHC Existing survey','expected_slide_count':2,
            'slide_labels':['P1 - Slide 1','P2 - Slide 2'],
            'text_questions':{'expected':before,'desired':after}}}


class SurveyPopulatedText(unittest.TestCase):
    def test_multiple_same_slide_questions_become_bound_ordered_insertion_stages(self):
        source=base.inputs();source['question_batches'][0]['questions'].append(second())
        plan=front.validate_inputs(source)
        self.assertEqual(len(plan['question_batches']),2)
        binding={'editor_url':configuration()['start_url'],'slide_labels':['P1 - Slide 1','P2 - Slide 2']}
        first=front._text_plan(plan,binding,plan['question_batches'][0]);last=front._text_plan(plan,binding,plan['question_batches'][1])
        self.assertEqual(first['text_index'],1);self.assertEqual(first['expected_prior'],[])
        self.assertEqual(last['text_index'],2);self.assertEqual(last['expected_prior'],[base.question()])
        self.assertEqual(front.validate_inputs(plan),plan)
        completed=[{'kind':'text','target_slide':1,'api_fields':[],'native_receipt':{}} for _ in range(2)]
        binding['slides']=[{'canvas':[]},{'canvas':[]}]
        saved={'slide_labels':binding['slide_labels'],'slides':[
            {'canvas':[{'types':['TEXT'],'names':[['INPUT',None,None]]} for _ in range(2)],
                'radio_fields':[],'text_fields':[base.question(),second()]},{'canvas':[],'radio_fields':[]}]}
        front._validate_inventory(saved,plan,binding,completed)
        bad=deepcopy(saved);bad['slides'][0]['text_fields'].reverse()
        with self.assertRaises(runner.Stop):front._validate_inventory(bad,plan,binding,completed)
    def test_captured_positive_tail_drag_ends_below_existing_wrapper_once(self):
        page=MagicMock();handle=MagicMock();canvas=MagicMock();last=MagicMock()
        handle.bounding_box.return_value={'x':52.988,'y':312.675,'width':17.998,'height':9.473}
        canvas.bounding_box.return_value={'x':249.121,'y':90.859,'width':766.758,'height':400}
        last.bounding_box.return_value={'x':249.121,'y':90.859,'width':766.758,'height':119.268}
        text._append_populated(page,handle,canvas,last)
        page.mouse.down.assert_called_once();page.mouse.up.assert_called_once()
        endpoint=page.mouse.move.call_args_list[-1].args
        self.assertAlmostEqual(endpoint[0],700,places=3);self.assertAlmostEqual(endpoint[1],300,places=3)
        self.assertGreater(endpoint[1],last.bounding_box.return_value['y']+last.bounding_box.return_value['height'])
        page.reset_mock();canvas.bounding_box.return_value['height']=130
        with self.assertRaises(runner.Stop):text._append_populated(page,handle,canvas,last)
        page.mouse.down.assert_not_called()
    def test_property_route_compiles_executes_and_replays_exact_desired_inventory(self):
        source=configuration();job=runner.validate_job(recipe_cli.compile_recipe('surveys.configure',source),Path('.'))
        self.assertEqual(job['steps'][0]['action'],edit.ACTION)
        step=job['steps'][0];desired=source['configuration']['text_questions']['desired']
        receipt={'status':'SURVEY_TEXT_PROPERTIES_SAVED_AND_REOPENED','editor_url':source['start_url'],
            'configuration_sha256':edit.configuration_hash(step),'text_questions':deepcopy(desired),
            'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'),\
                patch.object(edit,'configure',return_value=receipt) as write:
            page=MagicMock();page.url=source['start_url']
            first=runner.run_on_page(page,job,root);again=runner.run_on_page(page,job,root)
        write.assert_called_once();self.assertTrue(again['replayed'])
        self.assertEqual(first['results'][0]['result']['text_questions'],desired)
        bad=deepcopy(receipt);bad['text_questions'][0][1]['query_key']='other'
        with self.assertRaises(runner.Stop):editor_replay._result(step,bad,job)
    def test_property_preflight_rejects_late_owner_drift_before_any_mutation(self):
        step=recipe_cli.compile_recipe('surveys.configure',configuration())['steps'][0]
        bad=deepcopy(step['payload']['text_questions']['expected']);bad[0][1]['query_key']='changed'
        with patch.object(text,'_frame',return_value=MagicMock()),patch.object(edit,'_inventory',return_value=bad),\
                patch.object(text,'write_question') as write,self.assertRaises(runner.Stop):edit.configure(MagicMock(),step)
        write.assert_not_called()
    def test_complete_property_writer_preserves_untouched_siblings_and_reopens(self):
        step=recipe_cli.compile_recipe('surveys.configure',configuration())['steps'][0];plan=edit.validate(step)
        before=plan['text_questions']['expected'];desired=plan['text_questions']['desired']
        a=[[{'types':['TEXT'],'labels':[q['label']],'controls':[]} for q in before[0]],[]]
        b=deepcopy(a);b[0][0]['labels']=['Updated goal']
        frame=MagicMock();save=frame.get_by_role.return_value;save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        with patch.object(text,'_frame',return_value=frame),patch.object(edit,'_inventory',side_effect=[before,desired,desired]),\
                patch.object(text,'snapshot',side_effect=[a,b,b]),patch.object(text,'read_question',return_value=before[0][0]),\
                patch.object(text,'write_question') as write,patch.object(edit,'reopen_editor') as reopen:
            value=edit.configure(MagicMock(),step)
        write.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
        self.assertEqual(value['text_questions'],desired)
    def test_required_hidden_transition_disables_the_old_flag_before_enabling_its_counterpart(self):
        state={'required':False,'hidden':True};events=[];values={**base.question(),'hidden_value':'old'}
        class Node:
            def __init__(self,key,flag=False):self.key=key;self.flag=flag
            def count(self):return 1
            def is_visible(self):return True
            def wait_for(self,**kw):pass
            def input_value(self):return values[self.key]
            def fill(self,value,**kw):values[self.key]=value
            def press(self,*a,**kw):pass
            def get_attribute(self,key):
                if key=='aria-checked':return str(state[self.key]).lower()
                if key=='class':return 'n-checkbox--disabled' if state['hidden' if self.key=='required' else 'required'] else ''
            def set_checked(self,wanted):
                if wanted and state['hidden' if self.key=='required' else 'required']:raise AssertionError('Disabled counterpart must turn off first')
                state[self.key]=wanted;events.append((self.key,wanted))
        nodes={selector:Node(key) for key,selector in text.PROPERTIES.items()}
        nodes.update({selector:Node(key,True) for key,selector in text.FLAGS.items()});nodes['#fieldHiddenvalue input']=Node('hidden_value')
        frame=MagicMock();frame.locator.side_effect=lambda selector:nodes[selector]
        def observed(*a):
            result={key:values[key] for key in text.PROPERTIES};result.update(state)
            if state['hidden']:result['hidden_value']=values['hidden_value']
            return result
        with patch.object(text,'_item'),patch.object(text,'_close_properties'),patch.object(text,'read_question',side_effect=observed):
            text.write_question(frame,{},base.question())
            hidden={**base.question(),'required':False,'hidden':True,'hidden_value':'new'}
            text.write_question(frame,{},hidden)
        self.assertEqual(events,[('hidden',False),('required',True),('required',False),('hidden',True)])

    def test_query_key_swaps_and_partial_slide_inventories_refuse_before_browser(self):
        for mutation in ('swap','omit','count','both'):
            source=configuration();config=source['configuration']['text_questions']
            if mutation=='swap':config['desired'][0][0]['query_key']=config['expected'][0][1]['query_key'];config['desired'][0][1]['query_key']=config['expected'][0][0]['query_key']
            elif mutation=='omit':config['expected'].pop()
            elif mutation=='count':config['desired'][0].pop()
            else:config['desired'][0][0]['required']=True
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.configure',source)


if __name__=='__main__':unittest.main()
