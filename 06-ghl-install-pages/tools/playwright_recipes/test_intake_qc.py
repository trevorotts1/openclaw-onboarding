"""Independent intake refusals: unsupported work must not become partial success."""
from pathlib import Path
import unittest

from recipe_cli import compile_recipe
import skill6_playwright as runner


def base():
    return {'location_id':'FIXTURE','location_name':'Fixture account',
            'start_url':'https://app.convertandflow.com/v2/location/FIXTURE/dashboard'}


def prepare(operation, data):
    return runner.validate_job(compile_recipe(operation,{**base(),**data}),Path('.'))


class IntakeCompletenessTests(unittest.TestCase):
    def test_string_false_never_authorizes_creation_append_or_fixture_bypass(self):
        cases = [
            ('forms.create', {'name': 'Fixture', 'allow_creation': 'false'}),
            ('surveys.create', {'name': 'Fixture', 'allow_creation': 'false'}),
            ('quizzes.create', {'name': 'Fixture', 'fixture': 'false'}),
            ('pages.install_code', {'append': 'false'}),
            ('communities.create', {'community': {'allow_creation': 'false'}}),
            ('communities.create', {'community': {'inactive': 'false'}}),
        ]
        for operation, data in cases:
            with self.subTest(operation=operation, data=data), self.assertRaisesRegex(runner.Stop, 'boolean'):
                prepare(operation, data)

    def test_raw_job_string_flags_also_refuse_before_dispatch(self):
        for flag in ('allow_creation', 'append', 'inactive', 'discovery'):
            job = {**base(), 'steps': [{'id': 'form', 'action': 'form', 'name': 'Fixture', flag: 'false'}]}
            with self.subTest(flag=flag), self.assertRaisesRegex(runner.Stop, 'boolean'):
                runner.validate_job(job, Path('.'))

    def test_explicit_publish_request_is_refused_instead_of_becoming_a_draft(self):
        with self.assertRaises(runner.Stop):
            prepare('forms.settings',{'settings':{'save_progress':True},'publish':True})
        job=prepare('forms.settings',{'settings':{'save_progress':True},'publish':False})
        self.assertIs(job['publish'],False)

    def test_unknown_requested_choices_cannot_be_silently_discarded(self):
        fields=[{'field':'First Name','required':True}]
        for extra in ({'choices':['A','B']}, {'custom_fields':[{'name':'Preferences'}]}):
            with self.subTest(extra=extra), self.assertRaises(runner.Stop):
                prepare('forms.configure',{'fields':fields,**extra})

    def test_combined_supported_placement_and_property_edits_are_preserved(self):
        job=prepare('forms.configure',{'add_fields':['Website'],
            'fields':[{'field':'First Name','required':True}]})
        self.assertEqual([step['action'] for step in job['steps']],
            ['native_field_placement','native_fields'])

    def test_uncaptured_meeting_options_are_rejected_by_prevalidation(self):
        room={'name':'Fixture room','slug':'fixture-room','waiting_room':True,
              'guest_users':False,'open_room':False}
        for extra in ({'recording':True}, {'transcription':True}):
            with self.subTest(extra=extra), self.assertRaises(runner.Stop):
                prepare('meetings.setup',{'meeting':{**room,**extra}})

    def test_assertion_before_last_mutation_is_not_a_readback(self):
        target={'by':'role','role':'textbox','value':'Course title'}
        cases=[
            [{'action':'expect_count','target':target,'value':1},
             {'action':'fill','target':target,'value':'Approved title'}],
            [{'action':'fill','target':target,'value':'Approved title'},
             {'action':'expect_value','target':target,'value':'Approved title'},
             {'action':'click','target':{'by':'role','role':'button','value':'Save'}}],
        ]
        for steps in cases:
            with self.subTest(steps=steps), self.assertRaises(runner.Stop):
                prepare('courses.configure_ui',{'options':{
                    'capture_source':'fixture:recorded-course-controls','steps':steps}})


if __name__ == '__main__':unittest.main()
