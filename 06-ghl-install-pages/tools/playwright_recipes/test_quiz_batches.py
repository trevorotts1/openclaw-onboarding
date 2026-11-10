"""Mixed authoring retains full prior inventories and journal boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recipe_cli
import skill6_playwright as runner
import quiz_batches
from test_quiz_text_questions import question
from test_quiz_choice_questions import new_question


def request():
    common = {'location_id': 'LOC', 'location_name': 'Fixture Account',
              'start_url': 'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ'}
    first = question('Your goal?', 'goal', 'TEXT')
    second = new_question()
    pages = [{'label': 'Page 1', 'questions': []}]
    batches = [{'written_answer_questions': {'expected_quiz_name': 'Exact quiz',
        'pages': deepcopy(pages), 'target_page': 1, 'questions': [first]}}]
    pages[0]['questions'].append(first)
    batches.append({'multiple_choice_questions': {'expected_quiz_name': 'Exact quiz',
        'pages': deepcopy(pages), 'target_page': 2, 'questions': [second],
        'create_page': True, 'new_page_label': 'Page 2', 'acknowledge_shared_field_options': True}})
    pages.append({'label': 'Page 2', 'questions': [second]})
    batches.append({'written_answer_questions': {'expected_quiz_name': 'Exact quiz',
        'pages': deepcopy(pages), 'target_page': 3,
        'questions': [question('Your next step?', 'next_step', 'LARGE_TEXT')],
        'create_page': True, 'new_page_label': 'Page 3'}})
    return {**common, 'configuration': {'question_batches': batches}}


def receipt(step):
    from playwright_recipes import quiz_choice_questions, quiz_written_questions
    action = step['action']
    module = quiz_choice_questions if action == 'quiz_multiple_choices' else quiz_written_questions
    return {'status': ('QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED' if action == 'quiz_multiple_choices'
                       else 'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED'),
        'kind': action, 'editor_url': step['payload']['start_url'],
        'configuration_sha256': module.configuration_hash(step),
        'question_count': 1, 'target_page': step['payload']['target_page'],
        'independent_readback': 'VERIFIED', 'dependency_api_used': False,
        'behavior_verified': False, 'submission_verified': False}


class QuizBatches(unittest.TestCase):
    def job(self):
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.configure', request()), Path('.'))

    def test_mixed_native_actions_keep_separate_intents_and_full_inventories(self):
        value = request(); original = deepcopy(value)
        job = self.job()
        self.assertEqual([s['action'] for s in job['steps']],
                         ['quiz_written_answers', 'quiz_multiple_choices', 'quiz_written_answers'])
        self.assertEqual(len({s['id'] for s in job['steps']}), 3)
        self.assertEqual(job['steps'][2]['payload']['pages'][1]['questions'][0], new_question())
        quiz_batches.compile_batches(value)
        self.assertEqual(value, original)

    def test_dropped_prior_options_renamed_owner_or_unsafe_append_refuse_before_execution(self):
        for defect in ('options', 'name', 'prior_text', 'append', 'many', 'foreign', 'mixed', 'malformed'):
            data = request(); batches = data['configuration']['question_batches']
            if defect == 'options':
                batches[2]['written_answer_questions']['pages'][1]['questions'][0]['options'][0] = 'Lost option'
            elif defect == 'name':batches[1]['multiple_choice_questions']['expected_quiz_name'] = 'Other quiz'
            elif defect == 'prior_text':batches[1]['multiple_choice_questions']['pages'][0]['questions'][0]['question'] = 'Other'
            elif defect == 'append':
                item = batches[1]['multiple_choice_questions'];item.pop('create_page');item.pop('new_page_label');item['target_page'] = 1
            elif defect == 'many':batches[0]['written_answer_questions']['questions'].append(question('Other?', 'other', 'TEXT'))
            elif defect == 'foreign':batches[0]['written_answer_questions']['location_id'] = 'FOREIGN'
            elif defect == 'mixed':data['configuration']['result_page'] = {}
            else:data['configuration']['question_batches'] = None
            with self.subTest(defect=defect), self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('quizzes.configure', data)

    def test_actual_runner_saves_typed_results_and_replays_without_repeating_writers(self):
        job = self.job(); observed = []
        def write(page, step):
            observed.append(step['id']);return receipt(step)
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'assert_tenant'), \
                patch.object(runner, 'quiz_written_answers', side_effect=write) as written, \
                patch.object(runner, 'quiz_multiple_choices', side_effect=write) as choices:
            first = runner.run_on_page(object(), job, root)
            repeated = runner.run_on_page(object(), job, root)
            self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(written.call_count, 2);self.assertEqual(choices.call_count, 1)
            self.assertEqual(observed, [step['id'] for step in job['steps']])
            self.assertEqual(len(json.loads(Path(root, 'state.json').read_text())['results']), 3)

    def test_interrupted_later_batch_never_replays_earlier_question_insertion(self):
        job = self.job()
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'assert_tenant'), \
                patch.object(runner, 'quiz_written_answers', side_effect=lambda page, step: receipt(step)) as written, \
                patch.object(runner, 'quiz_multiple_choices', side_effect=runner.Stop('uncertain native write')) as choice:
            with self.assertRaises(runner.Stop):runner.run_on_page(object(), job, root)
            with self.assertRaises(runner.Stop):runner.run_on_page(object(), job, root)
            self.assertEqual(written.call_count, 1);self.assertEqual(choice.call_count, 1)
            saved = json.loads(Path(root, 'state.json').read_text())
            self.assertEqual(saved['status'], 'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(len(saved['results']), 1)


if __name__ == '__main__':unittest.main()
