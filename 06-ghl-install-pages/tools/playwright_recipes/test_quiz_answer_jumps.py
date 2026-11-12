"""Captured per-answer Jump To uses exact destinations and preserves raw scores."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
import quiz_ui
import recipe_cli
import skill6_playwright as runner
from playwright_recipes import quiz_answer_jumps as jumps


def config():
    return {'question_labels':['Earlier','Single Choice test','Later'],
        'questions':[{'index':1,'expected_question':'Single Choice test','expected_query_key':'radio',
            'options':[{'label':'Option 1','expected_destination':None,'destination':'Later'},
                       {'label':'Option 2','expected_destination':'Next Question','destination':None}]}]}


def snapshot():
    return {'properties':{'question':'Single Choice test','query_key':'radio','placeholder':'','short_label':''},
        'flags':{'required':False,'hidden':False},'spread_to_columns':False,
        'options':[{'label':item['label'],'destination':item['expected_destination'],
                    'category':'Please Select','score':'0','score_enabled':False}
                   for item in config()['questions'][0]['options']]}


class AnswerJumpTests(unittest.TestCase):
    def test_same_action_compilation_and_backward_self_or_ambiguous_destinations_refuse(self):
        value={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
            'configuration':{'answer_jumps':config()}}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',value),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'quiz_configuration')
        self.assertEqual(job['steps'][0]['answer_jumps'],config())
        for bad in ('Earlier','Single Choice test','Missing',True):
            changed=config();changed['questions'][0]['options'][0]['destination']=bad
            with self.subTest(bad=bad),self.assertRaises(runner.Stop):jumps.validate(changed)
        with self.assertRaises(quiz_ui.QuizError):quiz_ui.validate({'answer_jumps':config(),'categories':['Other']})
        changed=config();changed['question_labels'][2]='Earlier'
        with self.assertRaises(runner.Stop):jumps.validate(changed)

    def test_option_jump_enable_select_disable_and_preserve_raw_score(self):
        for corrupt_menu in (False,True):
            frame,panel,row,select,options,titles=MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock()
            state=snapshot();switches=[]
            for index in range(2):
                switch=MagicMock();switch.is_enabled.return_value=True
                switch.get_attribute.side_effect=lambda key,index=index:'true' if state['options'][index]['destination'] is not None else 'false'
                def click(index=index):
                    state['options'][index]['destination']=None if state['options'][index]['destination'] is not None else 'Next Question'
                switch.click.side_effect=click;switches.append(switch)
            select.count.return_value=1;select.is_visible.return_value=True;row.locator.return_value=select
            menu=['Next Question','Earlier','Foreign' if corrupt_menu else 'Later']
            options.count.return_value=titles.count.return_value=3
            def title(index):
                node=MagicMock();node.inner_text.return_value=menu[index];return node
            titles.nth.side_effect=title;options.locator.return_value=titles
            def option(index):
                node=MagicMock();node.click.side_effect=lambda:state['options'][0].__setitem__('destination',menu[index]);return node
            options.nth.side_effect=option;frame.locator.return_value=options
            wanted=jumps.desired(config(),[snapshot()])
            with patch.object(jumps,'read',side_effect=lambda *args:[deepcopy(state)]), \
                    patch.object(jumps,'_open',return_value=panel), \
                    patch.object(jumps,'_row',side_effect=lambda panel,index,question:(row,switches[index])), \
                    patch.object(jumps,'_selected',side_effect=lambda *args:deepcopy(state)), \
                    patch.object(jumps.native,'_close_properties'), \
                    patch.object(jumps,'click',side_effect=lambda node:node.click()), \
                    patch.object(jumps,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())):
                if corrupt_menu:
                    with self.assertRaisesRegex(runner.Stop,'destination menu'):
                        jumps.write(frame,config(),[snapshot()])
                else:
                    jumps.write(frame,config(),[snapshot()]);self.assertEqual([state],wanted)
                    self.assertFalse(state['options'][0]['score_enabled']);self.assertEqual(state['options'][0]['score'],'0')

    def test_checkbox_next_and_disable_flow_and_forward_target_guard(self):
        value=config();q=value['questions'][0];q['field_type']='CHECKBOX'
        q['options'][0]['destination']='Next Question'
        self.assertEqual(jumps.validate(value),value)
        forward=deepcopy(value);forward['questions'][0]['options'][0]['destination']='Later'
        self.assertEqual(jumps.validate(forward),forward)
        invalid=deepcopy(value);invalid['questions'][0]['options'][0]['destination']='Earlier'
        with self.assertRaises(runner.Stop):jumps.validate(invalid)
        state=snapshot();frame,panel,row=MagicMock(),MagicMock(),MagicMock();switches=[]
        for index in range(2):
            switch=MagicMock();switch.is_enabled.return_value=True
            switch.get_attribute.side_effect=lambda key,index=index:'true' if state['options'][index]['destination'] is not None else 'false'
            def toggle(index=index):
                state['options'][index]['destination']=None if state['options'][index]['destination'] else 'Next Question'
            switch.click.side_effect=toggle;switches.append(switch)
        before=deepcopy(state)
        with patch.object(jumps,'read',side_effect=lambda *args:[deepcopy(state)]), \
                patch.object(jumps,'_open',return_value=panel), \
                patch.object(jumps,'_row',side_effect=lambda panel,index,question:(row,switches[index])), \
                patch.object(jumps,'_selected',side_effect=lambda *args:deepcopy(state)), \
                patch.object(jumps.native,'_close_properties'), \
                patch.object(jumps,'click',side_effect=lambda node:node.click()), \
                patch.object(jumps,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())):
            jumps.write(frame,value,[before])
        self.assertEqual([state],jumps.desired(value,[before]));frame.locator.assert_not_called()
        self.assertEqual(state['options'][0]['score'],'0');self.assertFalse(state['options'][0]['score_enabled'])

    def test_dropdown_and_checkbox_forward_destinations_compile_but_style_requires_choice_cards(self):
        for kind in ('CHECKBOX','SINGLE_OPTIONS','MULTIPLE_OPTIONS'):
            value=config();value['questions'][0]['field_type']=kind
            self.assertEqual(jumps.validate(value),value)
            job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',{
                'location_id':'LOC','location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
                'configuration':{'answer_jumps':value}}),Path('.'))
            self.assertEqual(job['steps'][0]['answer_jumps'],value)
            if kind!='CHECKBOX':
                value['questions'][0]['presentation']={'expected_style':'Standard','style':'Bubble'}
                with self.assertRaises(runner.Stop):jumps.validate(value)

    def test_prior_and_saved_jump_or_protected_metadata_drift_refuse(self):
        before=[snapshot()];changed=deepcopy(before);changed[0]['options'][0]['destination']='Earlier'
        with patch.object(jumps,'read',return_value=changed),self.assertRaisesRegex(runner.Stop,'prior destinations'):
            jumps.preflight(MagicMock(),config())
        with patch.object(jumps,'read',return_value=changed),self.assertRaisesRegex(runner.Stop,'complete preflight'):
            jumps.write(MagicMock(),config(),before)
        desired=jumps.desired(config(),before)
        for defect in ('destination','score','category','spread'):
            bad=deepcopy(desired)
            if defect=='spread':bad[0]['spread_to_columns']=True
            else:bad[0]['options'][0][defect]='wrong'
            with self.subTest(defect=defect),patch.object(jumps,'read',return_value=bad),self.assertRaisesRegex(runner.Stop,'did not persist'):
                jumps.verify(MagicMock(),config(),before)

    def test_parent_recipe_preflights_writes_saves_then_independently_verifies(self):
        import assessments
        page,frame,save,title,back=MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock()
        page.url='https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'
        page.frame_locator.return_value=frame;title.input_value.return_value='Exact quiz'
        save.count.return_value=1;save.is_enabled.return_value=True;back.count.return_value=1
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else back if kw.get('name')=='Back' else save
        events=[]
        save.click.side_effect=lambda:events.append('save')
        with patch.object(jumps,'preflight',side_effect=lambda *args:events.append('preflight') or [snapshot()]), \
                patch.object(jumps,'write',side_effect=lambda *args:events.append('write')), \
                patch.object(jumps,'verify',side_effect=lambda *args:events.append('verify')), \
                patch.object(runner,'visible',return_value=False), \
                patch.object(runner,'click',side_effect=lambda node:node.click()), \
                patch.object(runner,'wait_until',side_effect=lambda predicate,message:self.assertTrue(predicate())), \
                patch.object(assessments,'reopen_editor',side_effect=lambda *args:events.append('reopen')):
            receipt=quiz_ui.configure(page,{'answer_jumps':config()})
        self.assertEqual(events,['preflight','write','save','reopen','verify'])
        self.assertEqual(receipt['questions'],1);self.assertFalse(receipt['submission_verified'])


if __name__=='__main__':unittest.main()
