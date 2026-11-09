"""Result-copy execution and replay contracts without native client writes."""
import copy
import unittest
from pathlib import Path

import editor_replay
import quiz_results
import recipe_cli
import route
import skill6_playwright as runner


BASE = {'location_id':'FIXTURE', 'location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/FIXTURE/quiz-builder-v2/QUIZ'}


def config():
    return {'expected':{'business_name':'Previous'}, 'changes':{'business_name':'Authored'}}


class ResultIntegrationTests(unittest.TestCase):
    def job(self, extra=None):
        data = {**BASE, 'configuration':{'result_page':config(), **(extra or {})}}
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.configure', data), Path('.'))

    def receipt(self, step):
        return {'status':'QUIZ_RESULTS_SAVED_AND_REOPENED', 'kind':'quiz_results',
                'editor_url':BASE['start_url'], 'configuration_sha256':quiz_results.configuration_hash(step),
                'independent_readback':'VERIFIED', 'behavior_verified':False, 'submission_verified':False}

    def test_result_only_job_compiles_to_executable_native_action(self):
        job = self.job()
        self.assertEqual([s['action'] for s in job['steps']], ['quiz_results'])

    def test_existing_scoring_configuration_is_retained_before_results(self):
        job = self.job({'categories':['Approved category']})
        self.assertEqual([s['action'] for s in job['steps']], ['quiz_configuration', 'quiz_results'])

    def test_bad_result_payload_refuses_before_execution(self):
        data = {**BASE, 'configuration':{'categories':['Approved'], 'result_page':config()}}
        data['configuration']['result_page']['changes']['unknown'] = 'ignored'
        with self.assertRaises(runner.Stop):
            runner.validate_job(recipe_cli.compile_recipe('quizzes.configure', data), Path('.'))

    def test_explicit_null_results_cannot_be_dropped_before_scoring_writes(self):
        data = {**BASE, 'configuration':{'categories':['Approved'], 'result_page':None}}
        with self.assertRaises(runner.Stop):
            runner.validate_job(recipe_cli.compile_recipe('quizzes.configure', data), Path('.'))

    def test_replay_binds_config_editor_kind_and_pending_proof(self):
        job = self.job()
        step = job['steps'][0]
        receipt = self.receipt(step)
        self.assertEqual(editor_replay._result(step, receipt, job)['kind'], 'quiz_results')
        mutations = [
            {'configuration_sha256':'0'*64}, {'kind':'quiz'},
            {'editor_url':BASE['start_url'].replace('/QUIZ','/FOREIGN')},
            {'submission_verified':True}, {'behavior_verified':True},
            {'independent_readback':'REQUIRED'},
        ]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(runner.Stop):
                editor_replay._result(step, {**copy.deepcopy(receipt), **change}, job)

    def test_native_theme_does_not_require_generic_recorded_profile(self):
        probes = {'lanes':{'playwright':{'available':True}}}
        self.assertEqual(route.decide('courses.configure_ui','FIXTURE',probes,
                         inputs={'template_id':'EXISTING'})['lane'], 'playwright')
        self.assertEqual(route.decide('courses.configure_ui','FIXTURE',probes,
                         inputs={'options':{}})['lane'], 'STOP_NO_LANE')
