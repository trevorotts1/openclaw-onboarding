"""Captured same-page append remains bound to prefixes, scoring order and receipts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch

from playwright_recipes import quiz_creation as front,quiz_text_questions as native
import recipe_cli
import skill6_playwright as runner
import test_quiz_creation as creation
import test_quiz_text_questions as text_tests
from test_quiz_text_questions import question
from test_quiz_choice_questions import new_question
from test_quiz_picture_questions import question as picture_question

FIXTURE=Path(__file__).parent/'fixtures/quiz-populated-append-captured.json'


def same_page_inputs():
    value=creation.inputs();value['configuration']['question_batches'][1]['written_answer_questions']['target_page']=1
    value['configuration']['question_batches'].append({'written_answer_questions':{
        'target_page':1,'questions':[question('What would change?','desired_change','LARGE_TEXT')]}})
    value['configuration']['scoring']['expected_question_count']=3
    return value


class PopulatedCreation(unittest.TestCase):
    def compile(self,value):
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.create',value),Path('.'))
    def test_explicit_same_page_batches_keep_full_prefix_and_count_questions_independent_of_pages(self):
        value=same_page_inputs();original=deepcopy(value);plan=front.validate_inputs(value)
        job,pages=front._questions(plan,value['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED'))
        self.assertEqual(value,original);self.assertEqual(len(pages),1);self.assertEqual(len(pages[0]['questions']),3)
        self.assertEqual([step['payload']['target_page'] for step in job['steps']],[1,1,1])
        self.assertTrue(all('create_page' not in step['payload'] for step in job['steps']))
        self.assertEqual(job['steps'][2]['payload']['pages'][0]['questions'],pages[0]['questions'][:2])
        harness=creation.QuizCreationTests();harness.setUp();self.addCleanup(harness.doCleanups);harness.data=value
        with harness.patches():result=runner.run_on_page(harness.page,self.compile(value),harness.root)
        receipt=result['results'][0]['result'];self.assertEqual(receipt['question_count'],3)
        self.assertEqual([r['result']['target_page'] for r in receipt['question_receipts']],[1,1,1])
        self.assertEqual(front.validate_receipt(receipt,self.compile(value)['steps'][0]),receipt)
        for wrong in (1,True):
            bad=deepcopy(receipt);bad['question_count']=wrong
            with self.subTest(wrong=wrong),self.assertRaises(runner.Stop):front.validate_receipt(bad,self.compile(value)['steps'][0])
    def test_final_canvas_scoring_indices_follow_page_order_after_appending_to_an_earlier_page(self):
        value=creation.inputs();first=new_question();second=deepcopy(first);second.update(question='Other choice',query_key='other_choice')
        value['configuration']['question_batches'][1]={'multiple_choice_questions':{'questions':[second],'acknowledge_shared_field_options':True}}
        value['configuration']['question_batches'].append({'written_answer_questions':{'target_page':1,
            'questions':[question('Earlier page answer','earlier_answer','TEXT')]}})
        scoring=value['configuration']['scoring'];scoring['expected_question_count']=3
        other=deepcopy(scoring['questions'][0]);other.update(index=2,expected_question=second['question'],expected_query_key=second['query_key'])
        scoring['questions'].append(other)
        plan=front.validate_inputs(value);job,pages=front._questions(plan,value['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED'))
        self.assertEqual([len(page['questions']) for page in pages],[2,1]);self.assertEqual(job['steps'][-1]['payload']['target_page'],1)
        self.assertNotIn('create_page',job['steps'][-1]['payload'])
        value['configuration']['scoring']['questions'][1]['index']=1
        with self.assertRaises(runner.Stop):front.validate_inputs(value)
    def test_default_new_page_remains_next_owner_after_same_page_append_and_invalid_targets_refuse(self):
        value=same_page_inputs();value['configuration']['question_batches'][-1]['written_answer_questions'].pop('target_page')
        plan=front.validate_inputs(value);job,pages=front._questions(plan,value['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED'))
        self.assertEqual([len(page['questions']) for page in pages],[2,1]);self.assertEqual(job['steps'][-1]['payload']['target_page'],2)
        for target in (True,0,3,'1'):
            bad=same_page_inputs();bad['configuration']['question_batches'][1]['written_answer_questions']['target_page']=target
            with self.subTest(target=target),self.assertRaises(runner.Stop):front.validate_inputs(bad)
    def test_picture_choice_populated_page_keeps_complete_prior_and_persisted_following_inventory(self):
        value=creation.inputs();value['configuration']['question_batches'][1]={'picture_choice_questions':{
            'target_page':1,'questions':[picture_question()],'acknowledge_shared_field_options':True}}
        value['configuration']['question_batches'].append({'written_answer_questions':{'target_page':1,
            'questions':[question('After picture','after_picture','TEXT')]}})
        value['configuration']['scoring']['expected_question_count']=3
        plan=front.validate_inputs(value);job,pages=front._questions(plan,value['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED'))
        self.assertEqual(len(pages),1);self.assertEqual(len(pages[0]['questions']),3)
        self.assertEqual(job['steps'][1]['payload']['pages'][0]['questions'],[new_question()])
        saved=job['steps'][2]['payload']['pages'][0]['questions'][1]
        self.assertEqual(saved['unique_key'],picture_question()['expected_persisted_unique_key'])
        self.assertNotIn('media_button_name',saved['options'][0])
        from playwright_recipes import quiz_picture_questions as picture
        from test_quiz_picture_questions import proof
        harness=creation.QuizCreationTests();harness.setUp();self.addCleanup(harness.doCleanups);harness.data=value
        with harness.patches(),patch.object(picture,'configure',side_effect=lambda page,step:proof(step)) as native_picture:
            result=runner.run_on_page(harness.page,self.compile(value),harness.root)
        native_picture.assert_called_once();receipt=result['results'][0]['result']
        self.assertEqual(receipt['question_count'],3);self.assertEqual(receipt['scored_question_count'],1)
        self.assertEqual(receipt['question_receipts'][1]['result']['target_page'],1)
        self.assertEqual(front.validate_receipt(receipt,self.compile(value)['steps'][0]),receipt)


class CapturedAppend(unittest.TestCase):
    def test_saved_reopened_native_dom_retains_two_text_owners_then_one_long_answer(self):
        fixture=json.loads(FIXTURE.read_text());inventories=[]
        for side in ('before','after'):
            tree=creation.CapturedHtml(fixture[side]['html']).root;frame=creation.CapturedQuizDom([tree])
            canvas=frame.locator(native.CANVAS);items=native._items(canvas)
            values=[]
            for index in range(items.count()):
                item=items.nth(index);label=item.get_by_role('textbox',name='Label',exact=True)
                values.append((label.inner_text().strip(),label.get_attribute('data-field-type')))
            inventories.append(values)
        self.assertEqual(inventories[0],[('Short Answer 780li7','TEXT'),('Short Answer 781ejd','TEXT')])
        self.assertEqual(inventories[1][:-1],inventories[0]);self.assertEqual(inventories[1][-1],('Long Answer 7200gj','LARGE_TEXT'))
        self.assertEqual(fixture['after']['pages'],1)
    def test_actual_captured_inside_edge_geometry_issues_one_drag_and_requires_exact_owner_delta(self):
        capture=json.loads(FIXTURE.read_text());frame,canvas,state,handle=text_tests.NativeAppend().surface();page=MagicMock()
        canvas.bounding_box.return_value=capture['before']['sub'];handle.bounding_box.return_value=capture['source']['rect']
        frame.get_by_role.return_value.locator.return_value.filter.return_value.get_attribute.return_value=capture['source']['id']
        items=canvas.locator.return_value;records=[MagicMock() for _ in range(3)]
        for record,row in zip(records,capture['before']['items']):record.bounding_box.return_value=row['rect']
        items.nth.side_effect=lambda index:records[index];state['count']=2
        page.mouse.up.side_effect=lambda:state.__setitem__('count',3)
        with patch.object(native,'_close_properties'),patch.object(native,'_close_drawer'), \
                patch.object(native,'_owners',return_value=[(object(),canvas)]),patch.object(native,'click'), \
                patch.object(native,'wait_until',side_effect=lambda fn,reason:self.assertTrue(fn())):
            self.assertIs(native._append_tile(frame,{'target_page':1},'Long Answer',page=page),records[2])
        page.mouse.down.assert_called_once();page.mouse.up.assert_called_once();handle.drag_to.assert_not_called()
        destination=page.mouse.move.call_args_list[1]
        last=capture['before']['items'][-1]['rect'];self.assertAlmostEqual(destination.args[0],last['x']+last['width']/2)
        self.assertAlmostEqual(destination.args[1],last['bottom']-7);self.assertEqual(destination.kwargs,{'steps':15})
        self.assertEqual([call.args for call in page.mouse.move.call_args_list[2:]],[destination.args]*3)


if __name__=='__main__':unittest.main()
