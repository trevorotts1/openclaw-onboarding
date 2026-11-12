import unittest
from pathlib import Path

from playwright_recipes import native_course_live_session as live
from playwright_recipes import editor_replay, recipe_cli, skill6_playwright


def valid():
    return {
        'location_id': '9hpz6dwEP5pyj7v2WTHO',
        'location_name': 'Convert & Flow',
        'start_url': 'https://app.convertandflow.com/v2/location/9hpz6dwEP5pyj7v2WTHO/memberships/courses/course-creator-studio?view=manager&sub_view=outline&product_id=6dcf3859-d118-4859-afd3-77d90f48b15d',
        'product_id': '6dcf3859-d118-4859-afd3-77d90f48b15d',
        'session_name': 'Owned Live Session Fixture',
        'description': 'A private draft verification session.',
        'instructor_name': 'Trevor Otts',
        'date': '2026-11-13',
        'start_time': '19:00',
        'end_time': '20:00',
        'timezone': '(GMT-0500) New York',
        'allow_creation': True,
    }


class NativeCourseLiveSessionValidationTests(unittest.TestCase):
    def test_captured_profile_is_accepted(self):
        self.assertEqual(live.validate_inputs(valid())['product_id'], '6dcf3859-d118-4859-afd3-77d90f48b15d')

    def test_wrong_course_identity_is_rejected(self):
        data = valid()
        data['product_id'] = 'another-course'
        with self.assertRaises(live.Stop):
            live.validate_inputs(data)

    def test_iso_date_outside_initial_picker_month_is_accepted(self):
        data = valid()
        data['date'] = '2027-02-01'
        self.assertEqual(live.validate_inputs(data)['date'], '2027-02-01')

    def test_notifications_cannot_be_requested(self):
        data = valid()
        data['notify_on_go_live'] = True
        with self.assertRaises(live.Stop):
            live.validate_inputs(data)

    def test_end_time_must_follow_start(self):
        data = valid()
        data['end_time'] = '18:45'
        with self.assertRaises(live.Stop):
            live.validate_inputs(data)

    def test_creation_requires_explicit_opt_in(self):
        data = valid()
        data['allow_creation'] = False
        with self.assertRaises(live.Stop):
            live.validate_inputs(data)

    def test_meetings_integrate_compiles_to_normal_native_runner_action(self):
        compiled = recipe_cli.compile_recipe('meetings.integrate', {
            **valid(), 'integration_mode': 'course_live_session'})
        job = skill6_playwright.validate_job(compiled, Path('.'))
        self.assertEqual(job['steps'][0]['action'], 'native_course_live_session')
        self.assertEqual(job['steps'][0]['payload']['product_id'], valid()['product_id'])

    def test_native_runner_rejects_course_payload_bound_to_other_location(self):
        compiled = recipe_cli.compile_recipe('meetings.integrate', {
            **valid(), 'integration_mode': 'course_live_session'})
        compiled['steps'][0]['payload']['location_id'] = 'other'
        with self.assertRaises(skill6_playwright.Stop):
            skill6_playwright.validate_job(compiled, Path('.'))

    def test_completed_replay_receipt_is_bound_and_never_marks_functional_proof(self):
        data = valid()
        receipt = {
            'status': 'COURSE_LIVE_SESSION_CREATED_AND_REOPENED',
            'location_id': data['location_id'], 'product_id': data['product_id'],
            'session_name': data['session_name'], 'date': data['date'],
            'start_time': data['start_time'], 'end_time': data['end_time'],
            'timezone': data['timezone'], 'recurrence': 'Does not repeat',
            'learner_notifications_enabled': False, 'personal_room_association': 'UNAVAILABLE',
            'meeting_started': False, 'identity_readback': 'VERIFIED',
            'settings_readback': 'PENDING', 'functional_verified': False,
            'configuration_sha256': live.configuration_hash(data),
        }
        job = skill6_playwright.validate_job(recipe_cli.compile_recipe('meetings.integrate', {
            **data, 'integration_mode': 'course_live_session'}), Path('.'))
        clean = editor_replay._result(job['steps'][0], receipt, job)
        self.assertEqual(clean['configuration_sha256'], receipt['configuration_sha256'])
        self.assertIs(clean['functional_verified'], False)
        receipt['personal_room_association'] = 'AVAILABLE'
        with self.assertRaises(skill6_playwright.Stop):
            editor_replay._result(job['steps'][0], receipt, job)


if __name__ == '__main__':
    unittest.main()
