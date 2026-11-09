import unittest
from pathlib import Path
from recipe_cli import compile_recipe
from skill6_playwright import Stop, validate_job
import skill6_playwright as runner


class SettingsControl:
    def __init__(self, page, kind, index=None, name=None):
        self.page, self.kind, self.index, self.name = page, kind, index, name

    def count(self):
        return 0 if self.kind == 'absent' else 1

    def get_by_role(self, *_args, **_kwargs):
        return SettingsControl(self.page, 'absent')

    def wait_for(self, **_kwargs):
        if not self.count():
            raise Stop('Fixture control absent')

    def is_visible(self):
        return bool(self.count())

    def is_enabled(self):
        return True

    def evaluate(self, _script):
        return self.page.labels[self.index]

    def get_attribute(self, name):
        return str(self.page.current[self.index]).lower() if name == 'aria-checked' else None

    def click(self, **_kwargs):
        if self.kind == 'switch':
            self.page.clicked.append(self.index)
            self.page.current[self.index] = not self.page.current[self.index]
        elif self.name == 'Save':
            self.page.saves += 1
            self.page.persisted = list(self.page.current)
            if self.page.lose_scheduler:
                self.page.persisted[0] = not self.page.persisted[0]


class SwitchCollection:
    def __init__(self, page):
        self.page = page

    def count(self):
        return len(self.page.labels)

    def nth(self, index):
        return SettingsControl(self.page, 'switch', index=index)


class SettingsPage:
    def __init__(self, scheduled=False, branding=True):
        self.url = 'https://fixture.example/v2/location/FIXTURE/form-builder-v2/form'
        self.labels = ['Schedule form visibility', 'Save progress for forms',
                       'Generate submission document', 'Show form recommendations',
                       'Sticky Contact', 'Create Conversation on Submission',
                       'Enable Timezone', 'Use GDPR Compliant Font']
        self.current = [scheduled, True, False, True, False, False, True, False]
        if scheduled:
            self.labels.insert(1, 'Agency branding')
            self.current.insert(1, branding)
        self.persisted = list(self.current)
        self.clicked, self.saves, self.reloads = [], 0, 0
        self.lose_scheduler = False

    def frame_locator(self, _selector):
        return self

    def get_by_role(self, role, name=None, exact=True):
        if role == 'switch':
            return SwitchCollection(self)
        return SettingsControl(self, 'absent' if role == 'dialog' else 'control', name=name)

    def get_by_text(self, name, exact=True):
        return SettingsControl(self, 'control' if name in self.labels else 'absent', name=name)

    def reload(self, **_kwargs):
        self.reloads += 1
        self.current = list(self.persisted)


class FormSettingsTests(unittest.TestCase):
    def inputs(self, settings):
        return {'location_id':'fixture', 'location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/fixture/form-builder/main',
                'settings':settings}

    def test_explicit_settings_compile_to_native_action(self):
        job = validate_job(compile_recipe('forms.settings', self.inputs(
            {'recommendations':False, 'capture_timezone':True})), Path('.'))
        self.assertEqual(job['steps'][0]['action'], 'form_settings')
        self.assertEqual(job['steps'][0]['settings']['recommendations'], False)

    def test_missing_dependent_settings_and_string_booleans_refused(self):
        for settings in ({}, {'capture_timezone':'false'}, {'schedule_visibility':True}):
            with self.subTest(settings=settings), self.assertRaises(Stop):
                validate_job(compile_recipe('forms.settings', self.inputs(settings)), Path('.'))

    def test_ordinary_flags_persist_with_scheduler_off_and_on_without_protected_clicks(self):
        flags = {'save_progress': False, 'submission_document': True,
                 'recommendations': False, 'sticky_contact': True,
                 'conversation_on_submission': True, 'capture_timezone': False,
                 'gdpr_font': True}
        for scheduled, branding in ((False, True), (True, True), (True, False)):
            with self.subTest(scheduled=scheduled, branding=branding):
                page = SettingsPage(scheduled, branding)
                result = runner.form_settings(page, {'settings': flags})
                self.assertEqual(result['status'], 'FORM_SETTINGS_PERSISTED')
                self.assertEqual(page.saves, 1)
                self.assertEqual(page.reloads, 1)
                self.assertEqual(page.current[0], scheduled)
                self.assertNotIn(0, page.clicked)
                if scheduled:
                    self.assertEqual(page.current[1], branding)
                    self.assertNotIn(1, page.clicked)
                for key, value in flags.items():
                    index = runner.FORM_SETTINGS[key][0] + int(scheduled)
                    self.assertIs(page.current[index], value)

    def test_nine_switch_shape_requires_correct_branding_row_before_any_click(self):
        page = SettingsPage(True)
        page.labels[1] = 'Uncaptured additional control'
        with self.assertRaises(Stop):
            runner.form_settings(page, {'settings': {'capture_timezone': False}})
        self.assertEqual((page.clicked, page.saves), ([], 0))

    def test_schedule_state_must_match_eight_or_nine_switch_shape(self):
        for page in (SettingsPage(False), SettingsPage(True)):
            page.current[0] = not page.current[0]
            with self.subTest(count=len(page.labels)), self.assertRaises(Stop):
                runner.form_settings(page, {'settings': {'capture_timezone': False}})
            self.assertEqual((page.clicked, page.saves), ([], 0))

    def test_lost_scheduler_state_after_save_is_not_verified(self):
        page = SettingsPage(True)
        page.lose_scheduler = True
        with self.assertRaises(Stop):
            runner.form_settings(page, {'settings': {'capture_timezone': False}})
        self.assertEqual(page.saves, 1)
        self.assertNotIn(0, page.clicked)
        self.assertNotIn(1, page.clicked)


if __name__ == '__main__':
    unittest.main()
