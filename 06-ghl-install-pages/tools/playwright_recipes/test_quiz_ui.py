import unittest
from unittest.mock import MagicMock, patch

import quiz_ui
import skill6_playwright as runner
from test_assessments import list_reopen_surface


def configuration():
    return {'expected_question_count': 1, 'questions': [{
        'index': 0, 'expected_question': 'Single Choice fixture', 'expected_query_key': 'radio',
        'options': [{'label': 'Option 1', 'category': 'Overall Only', 'score': 10},
                    {'label': 'Option 2', 'category': 'Overall Only', 'score': -1.5},
                    {'label': 'Option 3', 'category': 'Overall Only', 'score': 20}]}]}


class QuizConfigurationValidation(unittest.TestCase):
    def test_no_invented_score_maximum(self):
        data = configuration()
        data['questions'][0]['options'][0]['score'] = 1000.5
        self.assertEqual(quiz_ui.validate(data), data)

    def test_nonfinite_scores_booleans_and_duplicate_options_refused(self):
        for value in (True, '10', float('inf'), float('nan')):
            data = configuration()
            data['questions'][0]['options'][0]['score'] = value
            with self.subTest(value=value), self.assertRaises(quiz_ui.QuizError):
                quiz_ui.validate(data)
        data = configuration()
        data['questions'][0]['options'][1]['label'] = 'Option 1'
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)

    def test_question_identity_and_count_required(self):
        for key in ('expected_question', 'expected_query_key'):
            data = configuration()
            del data['questions'][0][key]
            with self.subTest(key=key), self.assertRaises(quiz_ui.QuizError):
                quiz_ui.validate(data)
        data = configuration()
        data['questions'][0]['index'] = 1
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)

    def test_three_result_tiers_must_cover_the_full_integer_percent_range(self):
        data = {'expected_tier_labels': ['Low', 'Medium', 'High'], 'tiers': [
            {'label': 'Starting', 'from': 0, 'to': 29},
            {'label': 'Growing', 'from': 30, 'to': 79},
            {'label': 'Advanced', 'from': 80, 'to': 100}]}
        self.assertEqual(quiz_ui.validate(data), data)
        for new_from in (29, 31):
            data['tiers'][1]['from'] = new_from
            with self.subTest(new_from=new_from), self.assertRaises(quiz_ui.QuizError):
                quiz_ui.validate(data)
        data['tiers'].pop()
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)

    def test_categories_are_not_silently_duplicated(self):
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate({'categories': ['Expert', 'EXPERT']})
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate({})

    def test_uncaptured_authored_question_routing_and_tier_colors_refuse_before_writes(self):
        data = configuration()
        data['questions'][0]['question'] = 'An unimplemented text change'
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)
        data = configuration()
        data['questions'][0]['options'][0]['next'] = 2
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate({'categories': ['Test'], 'redirect_url': 'https://example.invalid'})

    def test_authored_question_and_choices_require_acknowledgment_and_unique_final_labels(self):
        data = configuration()
        q = data['questions'][0]
        q['question'] = 'What is your preferred service?'
        q['options'][0]['new_label'] = 'Coaching'
        q['append_options'] = [{'label': 'Consulting', 'category': 'Overall Only', 'score': 5}]
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)
        q['shared_field_change_ack'] = True
        self.assertEqual(quiz_ui.validate(data), data)
        q['append_options'][0]['label'] = 'Coaching'
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(data)


class NativeQuestionExecution(unittest.TestCase):
    def surface(self, *, persist=True, row_drift=False, category_available=True):
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/quiz-builder-v2/quiz'
        state = {'panel': False, 'selected': None, 'categories': [None] * 3, 'scores': [''] * 3, 'saves': 0, 'labels': ['Option 1', 'Option 2', 'Option 3'], 'question': 'Single Choice fixture', 'appends': 0}
        title = MagicMock()
        title.input_value.return_value = 'ZHC Quiz Fixture'
        noop = MagicMock()
        back = MagicMock()
        back.count.side_effect = lambda: 2 if state['panel'] else 1
        close_panel = MagicMock()
        close_panel.click.side_effect = lambda: state.__setitem__('panel', False)
        back.nth.return_value = close_panel
        def leave():
            if not persist:
                state['categories'] = [None] * 3
                state['scores'] = [''] * 3
                state['labels'] = ['Option 1', 'Option 2', 'Option 3']
                state['question'] = 'Single Choice fixture'
        back.click.side_effect = leave
        page.goto.side_effect = lambda *args, **kwargs: leave()
        open_settings = MagicMock()
        open_settings.click.side_effect = lambda: state.__setitem__('panel', True)
        save = MagicMock()
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        properties = MagicMock()
        properties.count.return_value = 4
        props = []
        for value, label in zip(('Single Choice fixture', '', '', 'radio'), ('Question', 'Placeholder', 'Short Label', 'Query Key')):
            loc = MagicMock()
            loc.input_value.return_value = value
            loc.evaluate.return_value = label
            props.append(loc)
        props[0].input_value.side_effect = lambda: state['question']
        props[0].fill.side_effect = lambda value: state.__setitem__('question', value)
        properties.nth.side_effect = lambda i: props[i]
        labels = MagicMock()
        labels.count.side_effect = lambda: len(state['labels']) + 1 if state['panel'] else 1
        def label_control(index):
            loc = MagicMock()
            loc.input_value.side_effect = lambda: '' if index == 0 else state['labels'][index - 1]
            loc.fill.side_effect = lambda value: state['labels'].__setitem__(index - 1, value)
            return loc
        labels.nth.side_effect = label_control
        scores, pickers = MagicMock(), MagicMock()
        scores.count.side_effect = pickers.count.side_effect = lambda: len(state['labels'])
        def score_control(index):
            score = MagicMock()
            score.is_enabled.side_effect = lambda: state['categories'][index] is not None
            score.input_value.side_effect = lambda: state['scores'][index]
            score.fill.side_effect = lambda value: state['scores'].__setitem__(index, value)
            return score
        def picker_control(index):
            picker = MagicMock()
            picker.click.side_effect = lambda: state.__setitem__('selected', index)
            picker.inner_text.side_effect = lambda: state['categories'][index] or ''
            row = MagicMock()
            row_label = MagicMock()
            row_label.count.return_value = 1
            row_label.input_value.side_effect = lambda: 'Wrong option' if row_drift else state['labels'][index]
            row.get_by_role.return_value = row_label
            picker.locator.return_value.locator.return_value.locator.return_value.locator.return_value = row
            return picker
        scores.nth.side_effect = score_control
        pickers.nth.side_effect = picker_control
        add, append_button = MagicMock(), MagicMock()
        add.count.return_value = 2
        add.nth.return_value = append_button
        append_button.is_enabled.side_effect = lambda: all(state['labels'])
        def append():
            state['labels'].append('')
            state['categories'].append(None)
            state['scores'].append('')
            state['appends'] += 1
        append_button.click.side_effect = append
        menu = MagicMock()
        def choice(name, *, exact):
            option = MagicMock()
            option.count.return_value = int(category_available)
            option.click.side_effect = lambda: state['categories'].__setitem__(state['selected'], name)
            return option
        menu.get_by_text.side_effect = choice
        frame.locator.side_effect = lambda selector: pickers if selector == '[id="category-picker"]' else menu
        def role(role, *, name=None, exact=None):
            if role == 'textbox':
                return {'Form Name': title, 'Label': labels, 'Please Input': properties, '10': scores}[name]
            if role == 'button':
                return {'Back': back, 'Open settings': open_settings, 'Save': save, 'Add option': add}.get(name, noop)
            return noop
        frame.get_by_role.side_effect = role
        page.frame_locator.return_value = frame
        return page, state

    def run_surface(self, page, data=None):
        cell=list_reopen_surface(page)
        page.frame_locator.return_value.get_by_role('textbox',name='Form Name',exact=True).count.return_value=1
        with patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=cell):
            return quiz_ui.configure(page, configuration() if data is None else data)

    def test_native_categories_and_scores_survive_independent_reopen(self):
        page, state = self.surface()
        result = self.run_surface(page)
        self.assertEqual(state['saves'], 1)
        self.assertEqual(state['scores'], ['10', '-1.5', '20'])
        self.assertEqual(result['status'], 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED')
        self.assertFalse(result['submission_verified'])

    def test_authored_question_renamed_and_appended_choices_survive_reopen(self):
        page, state = self.surface()
        data = configuration()
        q = data['questions'][0]
        q.update(question='Choose your service', shared_field_change_ack=True,
                 append_options=[{'label': 'Consulting', 'category': 'Overall Only', 'score': 5}])
        q['options'][0]['new_label'] = 'Coaching'
        result = self.run_surface(page, data)
        self.assertEqual(result['status'], 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED')
        self.assertEqual(state['question'], 'Choose your service')
        self.assertEqual(state['labels'], ['Coaching', 'Option 2', 'Option 3', 'Consulting'])
        self.assertEqual(state['appends'], 1)
        self.assertEqual(state['scores'], ['10', '-1.5', '20', '5'])

    def test_authored_question_lost_on_save_is_not_accepted(self):
        page, state = self.surface(persist=False)
        data = configuration()
        data['questions'][0].update(question='Choose your service', shared_field_change_ack=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, data)
        self.assertEqual(state['saves'], 1)

    def test_lost_save_is_not_a_success(self):
        page, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page)
        self.assertEqual(state['saves'], 1)

    def test_wrong_option_row_stops_before_category_or_score_write(self):
        page, state = self.surface(row_drift=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page)
        self.assertEqual(state['scores'], ['', '', ''])
        self.assertEqual(state['saves'], 0)


    def test_missing_category_does_not_write_a_score(self):
        page, state = self.surface(category_available=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page)
        self.assertEqual(state['scores'], ['', '', ''])
        self.assertEqual(state['saves'], 0)


class NativeCategoriesAndTiers(unittest.TestCase):
    def surface(self, *, persist=True):
        page, frame, modal, popup = (MagicMock() for _ in range(4))
        page.url = 'https://app.convertandflow.com/v2/location/fixture/quiz-builder-v2/quiz'
        state = {'categories': ['Overall Only'], 'labels': ['Low', 'Medium', 'High'],
                 'ranges': ['0', '39', '40', '70', '71', '100'], 'adds': 0, 'saves': 0}
        title = MagicMock()
        title.input_value.return_value = 'ZHC Quiz Fixture'
        back = MagicMock()
        back.count.return_value = 1
        def leave():
            if not persist:
                state['categories'] = ['Overall Only']
                state['labels'] = ['Low', 'Medium', 'High']
                state['ranges'] = ['0', '39', '40', '70', '71', '100']
        back.click.side_effect = leave
        page.goto.side_effect = lambda *args, **kwargs: leave()
        save = MagicMock()
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        names, labels, ranges = (MagicMock() for _ in range(3))
        names.count.side_effect = lambda: len(state['categories'])
        labels.count.return_value = 3
        ranges.count.return_value = 6
        def item(key, index):
            loc = MagicMock()
            loc.input_value.side_effect = lambda: state[key][index]
            loc.fill.side_effect = lambda value: state[key].__setitem__(index, value)
            loc.is_enabled.return_value = not (key == 'ranges' and index in (0, 5))
            return loc
        names.nth.side_effect = lambda i: item('categories', i)
        labels.nth.side_effect = lambda i: item('labels', i)
        ranges.nth.side_effect = lambda i: item('ranges', i)
        add = MagicMock()
        def append_category():
            state['categories'].append('')
            state['adds'] += 1
        add.click.side_effect = append_category
        noop = MagicMock()
        def modal_role(role, *, name=None, exact=None):
            if role == 'textbox':
                return names
            return add if name == 'Add category' else noop
        modal.get_by_role.side_effect = modal_role
        popup.count.return_value = 1
        popup.get_by_role.side_effect = lambda role, name=None, exact=None: (labels if name == 'Label' else ranges) if role == 'textbox' else noop
        frame.locator.return_value.filter.return_value = popup
        def frame_role(role, *, name=None, exact=None):
            if role == 'textbox':
                return title
            if role == 'dialog':
                return modal
            if role == 'button':
                return {'Back': back, 'Save': save}.get(name, noop)
            return noop
        frame.get_by_role.side_effect = frame_role
        page.frame_locator.return_value = frame
        return page, state

    def run_surface(self, page, step):
        cell=list_reopen_surface(page)
        page.frame_locator.return_value.get_by_role('textbox',name='Form Name',exact=True).count.return_value=1
        with patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=cell):
            return quiz_ui.configure(page, step)

    def test_category_creation_reuses_existing_and_reopens_without_duplicates(self):
        page, state = self.surface()
        result = self.run_surface(page, {'categories': ['Overall Only', 'ZHC Category']})
        self.assertEqual(state['categories'], ['Overall Only', 'ZHC Category'])
        self.assertEqual(state['adds'], 1)
        self.assertEqual(result['status'], 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED')

    def test_category_lost_after_save_is_refused(self):
        page, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, {'categories': ['ZHC Category']})
        self.assertEqual(state['saves'], 1)

    def test_native_tier_labels_and_boundaries_reopen_with_disabled_endpoints_preserved(self):
        page, state = self.surface()
        step = {'expected_tier_labels': ['Low', 'Medium', 'High'], 'tiers': [
            {'label': 'Starting', 'from': 0, 'to': 29},
            {'label': 'Growing', 'from': 30, 'to': 79},
            {'label': 'Advanced', 'from': 80, 'to': 100}]}
        self.run_surface(page, step)
        self.assertEqual(state['labels'], ['Starting', 'Growing', 'Advanced'])
        self.assertEqual(state['ranges'], ['0', '29', '30', '79', '80', '100'])
        self.assertEqual(state['saves'], 1)

    def test_tiers_lost_after_save_do_not_pass_readback(self):
        page, state = self.surface(persist=False)
        step = {'expected_tier_labels': ['Low', 'Medium', 'High'], 'tiers': [
            {'label': 'Starting', 'from': 0, 'to': 29},
            {'label': 'Growing', 'from': 30, 'to': 79},
            {'label': 'Advanced', 'from': 80, 'to': 100}]}
        with self.assertRaises(runner.Stop):
            self.run_surface(page, step)
        self.assertEqual(state['saves'], 1)



if __name__ == '__main__':
    unittest.main()
