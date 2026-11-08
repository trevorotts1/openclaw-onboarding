import copy
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import assessments as a
import skill6_playwright as runner


def quiz():
    return {'kind': 'quiz', 'questions': [
        {'id': 'q1', 'choices': [{'value': 'skip', 'score': 0, 'next': 'submit'},
                                 {'value': 'continue', 'score': 2}]},
        {'id': 'q2', 'choices': [{'value': 'low', 'score': 0}, {'value': 'high', 'score': 3}]},
    ], 'results': [{'id': 'starter', 'min': 0, 'max': 2}, {'id': 'advanced', 'min': 3, 'max': 5}]}


class AssessmentModels(unittest.TestCase):
    def test_branch_scores_only_visited_questions(self):
        result = a.evaluate_model(quiz(), {'q1': 'skip', 'q2': 'high'})
        self.assertEqual(result, {'visited': ['q1'], 'score': 0, 'result': 'starter',
                                  'ignored_unvisited_answers': ['q2']})
        self.assertEqual(a.evaluate_model(quiz(), {'q1': 'continue', 'q2': 'high'})['result'], 'advanced')

    def test_missing_choice_and_missing_visited_answer_refused(self):
        for answers in ({'q1': 'unknown'}, {'q1': 'continue'}, {'q1': 'skip', 'other': 'x'}):
            with self.subTest(answers=answers), self.assertRaises(a.AssessmentError):
                a.evaluate_model(quiz(), answers)

    def test_dangling_and_backward_routes_refused(self):
        for target in ('missing', 'q1'):
            model = quiz()
            model['questions'][1]['choices'][0]['next'] = target
            with self.subTest(target=target), self.assertRaises(a.AssessmentError):
                a.validate_model(model)

    def test_duplicate_choice_and_boolean_scores_refused(self):
        model = quiz()
        model['questions'][0]['choices'][1]['value'] = 'skip'
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)
        model = quiz()
        model['questions'][0]['choices'][0]['score'] = True
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)

    def test_overlap_and_reachable_score_gap_refused(self):
        model = quiz()
        model['results'][1]['min'] = 2
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)
        model = quiz()
        model['results'][0]['max'] = 1
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)

    def test_submission_is_compared_against_authored_model(self):
        answers = {'q1': 'continue', 'q2': 'high'}
        observed = {'visited': ['q1', 'q2'], 'score': 5, 'result': 'advanced'}
        self.assertEqual(a.verify_submission(quiz(), answers, observed)['status'], 'PASS')
        observed['score'] = 2
        self.assertEqual(a.verify_submission(quiz(), answers, observed)['differences'], ['score'])

    def test_survey_forward_jump_and_no_fake_score(self):
        model = {'kind': 'survey', 'questions': [
            {'id': 'q1', 'choices': [{'value': 'bypass', 'next': 'q3'}]},
            {'id': 'q2', 'choices': [{'value': 'unused'}]},
            {'id': 'q3', 'choices': [{'value': 'finish'}]}]}
        result = a.evaluate_model(model, {'q1': 'bypass', 'q3': 'finish'})
        self.assertEqual(result['visited'], ['q1', 'q3'])
        self.assertIsNone(result['score'])


class FieldConfiguration(unittest.TestCase):
    def test_only_captured_standard_properties_accepted(self):
        valid = {'fields': [{'field': 'Last Name', 'label': 'Family Name', 'width_pct': 50,
                             'required': True, 'hidden': False}]}
        self.assertEqual(a.validate_fields(valid), valid)
        cases = [[], [{'field': 'Custom Answer', 'label': 'Unknown'}],
                 [{'field': 'Last Name', 'required': True, 'hidden': True}],
                 [{'field': 'Last Name', 'hidden': True}],
                 [{'field': 'Last Name', 'width_pct': True}],
                 [{'field': 'Last Name', 'placeholder': 'your@email.com'}],
                 [{'field': 'Last Name', 'required': 'false'}]]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(a.AssessmentError):
                a.validate_fields({'fields': fields})

    def test_condition_never_silently_ignores_value_or_action(self):
        valid = {'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name'}
        self.assertEqual(a.validate_condition(valid), valid)
        cases = [{**valid, 'value': 'ignored'}, {**valid, 'action': 'Show Field'},
                 {**valid, 'operator': 'Is Equal To'}, {**valid, 'target': 'Unknown Field'}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(a.AssessmentError):
                a.validate_condition(case)
        self.assertEqual(a.validate_condition({**valid, 'operator': 'Contains', 'value': 'Test'})['value'], 'Test')

    def test_previously_customized_standard_field_requires_both_identity_anchors(self):
        field = {'field': 'Last Name', 'current_placeholder': 'Family name',
                 'current_query_key': 'family', 'required': True}
        self.assertEqual(a.validate_fields({'fields': [field]})['fields'][0], field)
        del field['current_query_key']
        with self.assertRaises(a.AssessmentError):
            a.validate_fields({'fields': [field]})


class NativeFieldExecution(unittest.TestCase):
    def surface(self, *, persist=True, drift=False):
        original = ['Last Name', 'Enter your last name', '', 'last_name', '100']
        state = {'values': original.copy(), 'required': False, 'hidden': False, 'panel': False, 'saves': 0}
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        inputs = []
        labels = ('Label', 'Placeholder', 'Short Label', 'Query Key', 'Field Width')
        for index in range(5):
            loc = MagicMock()
            loc.input_value.side_effect = lambda i=index: state['values'][i]
            loc.fill.side_effect = lambda value, i=index: state['values'].__setitem__(i, value)
            loc.evaluate.return_value = 'Wrong control' if drift and index == 3 else labels[index]
            inputs.append(loc)
        group = MagicMock()
        group.count.return_value = 5
        group.nth.side_effect = lambda i: inputs[i]
        title = MagicMock()
        title.input_value.return_value = 'ZHC Native Fixture'
        back = MagicMock()
        back.count.side_effect = lambda: 2 if state['panel'] else 1
        close_panel = MagicMock()
        close_panel.click.side_effect = lambda: state.__setitem__('panel', False)
        back.nth.return_value = close_panel

        def leave():
            if not persist:
                state['values'] = original.copy()
                state['required'] = False
                state['hidden'] = False
        back.click.side_effect = leave
        page.goto.side_effect = lambda *args, **kwargs: leave()
        page.frame_locator.return_value = frame
        save = MagicMock()
        save.count.return_value = 1
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        save.is_enabled.return_value = True
        checks = {}
        for key in ('required', 'hidden'):
            check = MagicMock()
            check.is_checked.side_effect = lambda k=key: state[k]
            check.set_checked.side_effect = lambda value, k=key: state.__setitem__(k, value)
            checks[key.title()] = check
        empty = MagicMock()

        def role(role, *, name=None, exact=None):
            if role == 'textbox':
                return title if name == 'Form Name' else group
            if role == 'checkbox':
                return checks[name]
            if role == 'button' and name == 'Back':
                return back
            if role == 'button' and name == 'Save':
                return save
            return empty
        frame.get_by_role.side_effect = role
        frame.get_by_text.return_value = empty
        open_settings = MagicMock()
        open_settings.click.side_effect = lambda: state.__setitem__('panel', True)
        frame.get_by_label.return_value = open_settings

        def placeholder(value, *, exact):
            target = MagicMock()
            target.count.return_value = int(state['values'][1] == value)
            return target
        frame.get_by_placeholder.side_effect = placeholder
        return page, frame, state

    def run_surface(self, page, frame, step):
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=MagicMock()):
            return a.configure_fields(page, step)

    def test_native_field_edits_are_independently_reopened(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name',
            'placeholder': 'Type family name', 'short_label': 'Family', 'query_key': 'family',
            'width_pct': 50, 'required': True}]})
        self.assertEqual(result['status'], 'FIELD_PROPERTIES_SAVED_AND_REOPENED')
        self.assertEqual(state['values'], ['Family Name', 'Type family name', 'Family', 'family', '50'])
        self.assertEqual(state['saves'], 1)

    def test_save_click_does_not_mask_lost_persisted_values(self):
        page, frame, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name'}]})
        self.assertEqual(state['saves'], 1)

    def test_property_order_drift_stops_before_any_write(self):
        page, frame, state = self.surface(drift=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name'}]})
        self.assertEqual(state['values'][0], 'Last Name')
        self.assertEqual(state['saves'], 0)


class NativeConditionExecution(unittest.TestCase):
    def surface(self, *, existing=False, enabled=True, persist=True):
        page, frame, dialog = MagicMock(), MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        state = {'count': 5, 'saves': 0, 'reopened': False}
        page.goto.side_effect = lambda *args, **kw: state.__setitem__('reopened', True)
        inputs, save = MagicMock(), MagicMock()
        inputs.count.side_effect = lambda: state['count']
        def entry(index):
            control = MagicMock()
            control.input_value.return_value = 'Hide Field' if index == state['count'] - 2 else ''
            return control
        inputs.nth.side_effect = entry
        save.count.return_value = 1
        save.is_enabled.return_value = enabled
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        card = MagicMock()
        def card_text(value, **kw):
            loc = MagicMock()
            loc.count.return_value = 2 if value == 'Hide Field' else 1
            return loc
        card.get_by_text.side_effect = card_text
        def text(value, *, exact):
            loc = MagicMock()
            if value == 'No existing conditions yet':
                loc.count.return_value = int(not existing)
            elif value == 'IfLast NameIs Filled':
                loc.count.return_value = int((existing or state['saves'] > 0) and (persist or not state['reopened']))
                loc.nth.return_value.locator.return_value.locator.return_value.locator.return_value = card
            elif value == 'Hide Field':
                loc.count.return_value = 2 if state['saves'] else 0
            else:
                loc.count.return_value = 1
            if value in ('Is Empty', 'Is Filled'):
                loc.click.side_effect = lambda: state.__setitem__('count', 4)
            return loc
        dialog.get_by_text.side_effect = text
        dialog.get_by_role.side_effect = lambda role, **kw: inputs if role == 'textbox' else save
        title = MagicMock()
        title.input_value.return_value = 'ZHC Condition Fixture'
        def role(role, **kw):
            if role == 'dialog':
                return dialog
            if role == 'textbox':
                return title
            return save if kw.get('name') == 'Save' else MagicMock()
        frame.get_by_role.side_effect = role
        return page, frame, state

    def run_surface(self, page, frame):
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'visible', return_value=False):
            return a.configure_condition(page, {'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name'})

    def test_native_condition_requires_all_three_saves_and_reopen(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame)
        self.assertEqual(state['saves'], 3)
        self.assertEqual(result['independent_readback'], 'VERIFIED')
        self.assertFalse(result['submission_verified'])
        self.assertTrue(state['reopened'])

    def test_existing_matching_rule_is_read_without_duplicate_create(self):
        page, frame, state = self.surface(existing=True)
        result = self.run_surface(page, frame)
        self.assertEqual(result['status'], 'CONDITION_ALREADY_PRESENT')
        self.assertEqual(state['saves'], 0)

    def test_disabled_save_does_not_create(self):
        page, frame, state = self.surface(enabled=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame)
        self.assertEqual(state['saves'], 0)

    def test_missing_persisted_card_is_not_success(self):
        page, frame, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame)
        self.assertEqual(state['saves'], 3)


if __name__ == '__main__':
    unittest.main()
