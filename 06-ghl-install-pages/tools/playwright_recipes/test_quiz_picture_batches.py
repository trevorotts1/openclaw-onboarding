"""Picture/media owners survive mixed native question-writer boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recipe_cli
import skill6_playwright as runner
from playwright_recipes import quiz_choice_questions as choice, quiz_picture_questions as picture
from test_quiz_batches import receipt as ordinary_receipt
from test_quiz_choice_questions import new_question
from test_quiz_picture_questions import question as picture_question, proof, snapshot
from test_quiz_text_questions import question
from test_quiz_loading_readiness import LoadedDom, canvas_tree, mount


def request():
    common = {'location_id':'LOC','location_name':'Fixture Account',
              'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'}
    pages = [{'label':'Page 1','questions':[]}]
    values = [('written_answer_questions',question('Your goal?','goal','TEXT')),
              ('picture_choice_questions',picture_question()),
              ('multiple_choice_questions',new_question()),
              ('short_answer_questions',question('Your next step?','next_step','TEXT'))]
    batches = []
    for index,(kind,authored) in enumerate(values):
        payload = {'expected_quiz_name':'Exact quiz','pages':deepcopy(pages),
                   'target_page':index+1,'questions':[authored]}
        if index:
            payload.update(create_page=True,new_page_label='Page '+str(index+1))
        if kind in ('picture_choice_questions','multiple_choice_questions'):
            payload['acknowledge_shared_field_options'] = True
        batches.append({kind:payload})
        if index:pages.append({'label':payload['new_page_label'],'questions':[]})
        pages[index]['questions'].append(picture._authored(authored) if kind=='picture_choice_questions' else authored)
    return {**common,'configuration':{'question_batches':batches}}


class PictureBatches(unittest.TestCase):
    def job(self,value=None):
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',value or request()),Path('.'))

    def test_mixed_compiler_keeps_media_input_and_explicit_persisted_inventory_distinct(self):
        value=request();original=deepcopy(value);job=self.job(value)
        self.assertEqual([step['action'] for step in job['steps']],
            ['quiz_written_answers','quiz_picture_choices','quiz_multiple_choices','quiz_written_answers'])
        self.assertEqual(value,original)
        authored=job['steps'][1]['payload']['questions'][0]
        self.assertIn('expected_persisted_unique_key',authored)
        self.assertIn('media_button_name',authored['options'][0])
        for step in job['steps'][2:]:
            retained=step['payload']['pages'][1]['questions'][0]
            self.assertEqual(retained,picture._authored(authored))
            self.assertNotIn('expected_persisted_unique_key',retained)
            self.assertNotIn('media_button_name',retained['options'][0])

    def test_full_presentation_flows_through_compiler_receipt_and_later_inventory(self):
        value=request();batches=value['configuration']['question_batches']
        presentation={'show_option_label':True,'columns':None,'image_fit':'Contain',
                      'other_option':True,'spread_to_columns':False}
        batches[1]['picture_choice_questions']['questions'][0]['presentation']=presentation
        job=self.job(value);step=job['steps'][1]
        self.assertEqual(step['payload']['questions'][0]['presentation'],presentation)
        for later in job['steps'][2:]:
            self.assertEqual(later['payload']['pages'][0]['questions'],batches[0]['written_answer_questions']['questions'])
            self.assertNotIn('presentation',later['payload']['pages'][1]['questions'][0])
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'quiz_written_answers',side_effect=lambda page,step:ordinary_receipt(step)), \
                patch.object(runner,'quiz_multiple_choices',side_effect=lambda page,step:ordinary_receipt(step)), \
                patch.object(picture,'configure',side_effect=lambda page,step:proof(step)) as handler:
            runner.run_on_page(object(),job,root);replayed=runner.run_on_page(object(),job,root)
            self.assertTrue(replayed['replayed']);handler.assert_called_once()
            self.assertEqual(handler.call_args.args[1]['payload']['questions'][0]['presentation'],presentation)

    def test_short_answer_alias_never_widens_the_authored_type(self):
        value=request();value['configuration']['question_batches'][3]['short_answer_questions']['questions'][0]['field_type']='LARGE_TEXT'
        with self.assertRaisesRegex(runner.Stop,'Short Answer batches'):self.job(value)

    def test_media_key_label_order_and_old_owner_mutations_refuse_before_execution(self):
        for defect in ('image','unique_key','label','order','creation_only'):
            value=request();q=value['configuration']['question_batches'][2]['multiple_choice_questions']['pages'][1]['questions'][0]
            if defect=='image':q['options'][0]['image_url']='https://example.com/foreign.png'
            elif defect=='unique_key':q['unique_key']='contact.foreign'
            elif defect=='label':q['question']='Other picture question'
            elif defect=='order':q['options'].reverse()
            else:q['options'][0]['media_button_name']='unpersisted chooser command'
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):self.job(value)

    def test_native_unique_key_namespace_rejects_picture_to_multi_dropdown_collision(self):
        from test_quiz_multi_dropdown import authored as dropdown_question
        value=request();batch=value['configuration']['question_batches'][2]['multiple_choice_questions']
        q=dropdown_question();q['unique_key']=picture_question()['expected_persisted_unique_key'].upper()
        batch['questions']=[q]
        with self.assertRaisesRegex(runner.Stop,'Unique Keys'):self.job(value)

    def test_runner_typed_receipts_replay_without_repeating_any_picture_or_later_writer(self):
        job=self.job()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'quiz_written_answers',side_effect=lambda page,step:ordinary_receipt(step)) as written, \
                patch.object(runner,'quiz_multiple_choices',side_effect=lambda page,step:ordinary_receipt(step)) as choices, \
                patch.object(picture,'configure',side_effect=lambda page,step:proof(step)) as pictures:
            first=runner.run_on_page(object(),job,root);second=runner.run_on_page(object(),job,root)
            self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertTrue(second['replayed'])
            self.assertEqual(written.call_count,2);choices.assert_called_once();pictures.assert_called_once()
            self.assertEqual(len(json.loads(Path(root,'state.json').read_text())['results']),4)

    def test_uncertain_picture_save_blocks_every_later_writer_and_never_repeats_prefix(self):
        job=self.job()
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'quiz_written_answers',side_effect=lambda page,step:ordinary_receipt(step)) as written, \
                patch.object(runner,'quiz_multiple_choices') as choices, \
                patch.object(picture,'configure',side_effect=TimeoutError('uncertain media/save')) as pictures:
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            written.assert_called_once();pictures.assert_called_once();choices.assert_not_called()
            state=json.loads(Path(root,'state.json').read_text())
            self.assertEqual(state['status'],'NEEDS_BROWSER_RECOVERY');self.assertEqual(len(state['results']),1)

    def test_shared_reader_preserves_picture_style_and_minted_owner_before_ordinary_sibling(self):
        plan=self.job()['steps'][3]['payload'];plan=deepcopy(plan)
        # Use one already populated native page containing both captured shapes.
        plan['pages']=[{'label':'Page 1','questions':[picture._authored(picture_question()),question('Retained','retained','TEXT')]}]
        frame,canvas,items,pic,ordinary=MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock()
        items.count.return_value=2;items.nth.side_effect=lambda index:[pic,ordinary][index]
        pic.locator.return_value.count.return_value=1;ordinary.locator.return_value.count.return_value=0
        actual_picture=snapshot(persisted=True);actual_text=question('Retained','retained','TEXT')
        with patch.object(choice.native,'_prepare_inventory'), \
                patch.object(choice.native,'_owners',return_value=[(MagicMock(),canvas)]), \
                patch.object(choice.native,'_items',return_value=items), \
                patch.object(picture,'_read_picture',return_value=actual_picture) as image_read, \
                patch.object(choice.native,'_read_question',return_value=actual_text) as ordinary_read:
            self.assertEqual(choice._inventory(frame,plan),[[actual_picture,actual_text]])
            image_read.assert_called_once_with(frame,pic)
            ordinary_read.assert_called_once_with(frame,ordinary,field_types=choice.TYPES,metadata_reader=choice._metadata)
            self.assertEqual(choice._properties([[actual_picture,actual_text]]),[plan['pages'][0]['questions']])

    def test_baseline_uses_captured_native_radio_kind_without_erasing_picture_semantics(self):
        native=choice.native;plan=self.job()['steps'][2]['payload']
        plan['pages']=[{'label':'Page 1','questions':[picture._authored(picture_question())]}]
        for kind in ('RADIO','TEXT'):
            root,canvas=canvas_tree();mount(canvas,{**plan['pages'][0]['questions'][0],'field_type':kind})
            with self.subTest(kind=kind),patch.object(native,'_prepare_inventory'), \
                    patch.object(native,'wait_until',side_effect=lambda fn,reason:fn()):
                if kind=='RADIO':native._wait_baseline(LoadedDom([root]),plan)
                else:
                    with self.assertRaises(runner.Stop):native._wait_baseline(LoadedDom([root]),plan)


if __name__=='__main__':unittest.main()
