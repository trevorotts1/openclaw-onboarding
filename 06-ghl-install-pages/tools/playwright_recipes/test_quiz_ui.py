import unittest
from unittest.mock import MagicMock, patch

import quiz_ui
import skill6_playwright as runner


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


class NativeQuestionExecution(unittest.TestCase):
    def surface(self, *, persist=True, row_drift=False, category_available=True):
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/quiz-builder-v2/quiz'
        state = {'panel': False, 'selected': None, 'categories': [None] * 3, 'scores': [''] * 3, 'saves': 0}
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
        properties.nth.side_effect = lambda i: props[i]
        labels = MagicMock()
        labels.count.side_effect = lambda: 4 if state['panel'] else 1
        label_controls = [MagicMock() for _ in range(4)]
        for index, loc in enumerate(label_controls):
            loc.input_value.return_value = '' if index == 0 else 'Option ' + str(index)
        labels.nth.side_effect = lambda i: label_controls[i]
        scores, pickers = MagicMock(), MagicMock()
        scores.count.return_value = pickers.count.return_value = 3
        score_controls, picker_controls = [], []
        for index in range(3):
            score = MagicMock()
            score.is_enabled.side_effect = lambda i=index: state['categories'][i] is not None
            score.input_value.side_effect = lambda i=index: state['scores'][i]
            score.fill.side_effect = lambda value, i=index: state['scores'].__setitem__(i, value)
            score_controls.append(score)
            picker = MagicMock()
            picker.click.side_effect = lambda i=index: state.__setitem__('selected', i)
            picker.inner_text.side_effect = lambda i=index: state['categories'][i] or ''
            row = MagicMock()
            row_label = MagicMock()
            row_label.count.return_value = 1
            row_label.input_value.return_value = 'Wrong option' if row_drift else 'Option ' + str(index + 1)
            row.get_by_role.return_value = row_label
            picker.locator.return_value.locator.return_value.locator.return_value.locator.return_value = row
            picker_controls.append(picker)
        scores.nth.side_effect = lambda i: score_controls[i]
        pickers.nth.side_effect = lambda i: picker_controls[i]
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
                return {'Back': back, 'Open settings': open_settings, 'Save': save}.get(name, noop)
            return noop
        frame.get_by_role.side_effect = role
        page.frame_locator.return_value = frame
        return page, state

    def run_surface(self, page):
        with patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=MagicMock()):
            return quiz_ui.configure(page, configuration())

    def test_native_categories_and_scores_survive_independent_reopen(self):
        page, state = self.surface()
        result = self.run_surface(page)
        self.assertEqual(state['saves'], 1)
        self.assertEqual(state['scores'], ['10', '-1.5', '20'])
        self.assertEqual(result['status'], 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED')
        self.assertFalse(result['submission_verified'])

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
        with patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=MagicMock()):
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
