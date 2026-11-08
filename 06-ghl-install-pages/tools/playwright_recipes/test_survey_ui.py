import unittest
from unittest.mock import MagicMock, patch

import survey_ui
import skill6_playwright as runner


def rule():
    return {'expected_slide_count': 3, 'source_slide': 1, 'target_slide': 3,
            'slide_labels': ['P1 - Slide 1', 'P2 - Slide 2', 'P3 - Slide 3'],
            'if_field': 'Email', 'operator': 'Contains', 'value': '@example.com'}


class SurveyRuleValidation(unittest.TestCase):
    def test_forward_rule_preserves_authored_field_operator_value_and_target(self):
        self.assertEqual(survey_ui.validate(rule()), rule())

    def test_backward_self_and_dangling_jumps_are_rejected(self):
        for source, target in ((1, 1), (2, 1), (1, 4), (0, 2), (True, 3)):
            with self.subTest(source=source, target=target), self.assertRaises(survey_ui.SurveyError):
                survey_ui.validate({**rule(), 'source_slide': source, 'target_slide': target})

    def test_slide_labels_must_match_expected_native_numbering_and_count(self):
        for labels in (['P1 - Slide 1'], ['P1 - Slide 1', 'P3 - Slide 2', 'P2 - Slide 3']):
            with self.subTest(labels=labels), self.assertRaises(survey_ui.SurveyError):
                survey_ui.validate({**rule(), 'slide_labels': labels})

    def test_operators_do_not_ignore_or_invent_values(self):
        with self.assertRaises(survey_ui.SurveyError):
            survey_ui.validate({**rule(), 'operator': 'Is Filled'})
        for value in ('', None, True):
            with self.subTest(value=value), self.assertRaises(survey_ui.SurveyError):
                survey_ui.validate({**rule(), 'value': value})
        unary = rule()
        unary['operator'] = 'Is Empty'
        del unary['value']
        self.assertEqual(survey_ui.validate(unary), unary)

    def test_uncaptured_survey_options_are_not_ignored(self):
        with self.assertRaises(survey_ui.SurveyError):
            survey_ui.validate({**rule(), 'show_field': 'Last Name'})


class NativeSurveyExecution(unittest.TestCase):
    def surface(self, *, existing=False, persist=True, source_matches=True, wrong_target=False):
        page, frame, dialog = MagicMock(), MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/survey-builder-v2/survey'
        state = {'count': 5, 'saves': 0, 'reopened': False}
        page.goto.side_effect = lambda *args, **kw: state.__setitem__('reopened', True)
        title = MagicMock()
        title.input_value.return_value = 'ZHC Survey Fixture'
        slides = MagicMock()
        slides.count.return_value = 3
        slide_objects = []
        for index in range(3):
            slide, header = MagicMock(), MagicMock()
            header.count.return_value = 1
            header.inner_text.return_value = 'Slide ' + str(index + 1)
            slide.locator.return_value = header
            field = MagicMock()
            field.count.return_value = int(index == 0 and source_matches)
            slide.get_by_placeholder.return_value = field
            slide_objects.append(slide)
        slides.nth.side_effect = lambda i: slide_objects[i]
        frame.locator.return_value = slides
        inputs, save, rows = MagicMock(), MagicMock(), MagicMock()
        inputs.count.side_effect = lambda: state['count']
        def entry(index):
            loc = MagicMock()
            loc.input_value.return_value = 'Field' if index == 0 else ''
            return loc
        inputs.nth.side_effect = entry
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        rows.count.side_effect = lambda: int((existing or state['saves'] > 0) and (persist or not state['reopened']))
        row, body = MagicMock(), MagicMock()
        row.text_content.return_value = 'IfEmailContains@example.com'
        row.locator.return_value = body
        def card_text(value, **kw):
            loc = MagicMock()
            loc.count.return_value = int(not wrong_target or value != 'P3 - Slide 3')
            return loc
        body.get_by_text.side_effect = card_text
        rows.nth.return_value = row
        dialog.locator.return_value = rows
        def text(value, **kw):
            loc = MagicMock()
            loc.count.return_value = 1
            if value in ('Is Empty', 'Is Filled'):
                loc.click.side_effect = lambda: state.__setitem__('count', 4)
            return loc
        dialog.get_by_text.side_effect = text
        dialog.get_by_role.side_effect = lambda role, **kw: inputs if role == 'textbox' else save
        add_slide = MagicMock()
        add_slide.count.return_value = 3
        def frame_role(role, *, name=None, exact=None):
            if role == 'textbox':
                return title
            if role == 'dialog':
                return dialog
            if role == 'button':
                return save if name == 'Save' else add_slide if name == 'Add Slide' else MagicMock()
            return MagicMock()
        frame.get_by_role.side_effect = frame_role
        page.frame_locator.return_value = frame
        return page, state

    def run_surface(self, page):
        with patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())):
            return survey_ui.configure(page, rule())

    def test_native_survey_rule_requires_three_saves_and_independent_card_readback(self):
        page, state = self.surface()
        result = self.run_surface(page)
        self.assertEqual(state['saves'], 3)
        self.assertTrue(state['reopened'])
        self.assertEqual(result['status'], 'SURVEY_RULE_SAVED_AND_REOPENED')
        self.assertFalse(result['behavior_verified'])
        self.assertFalse(result['submission_verified'])

    def test_matching_existing_rule_is_reused_without_duplicate_save(self):
        page, state = self.surface(existing=True)
        result = self.run_surface(page)
        self.assertEqual(result['status'], 'SURVEY_RULE_ALREADY_PRESENT')
        self.assertEqual(state['saves'], 0)

    def test_wrong_source_owner_and_conflicting_target_stop_before_writes(self):
        for settings in ({'source_matches': False}, {'existing': True, 'wrong_target': True}):
            page, state = self.surface(**settings)
            with self.subTest(settings=settings), self.assertRaises(runner.Stop):
                self.run_surface(page)
            self.assertEqual(state['saves'], 0)

    def test_lost_persisted_rule_does_not_pass(self):
        page, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page)
        self.assertEqual(state['saves'], 3)


if __name__ == '__main__':
    unittest.main()
