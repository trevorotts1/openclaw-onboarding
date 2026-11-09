"""Existing variable-length tier layouts retain row/range ownership guards."""
import copy
import unittest
from unittest.mock import MagicMock, patch

import assessments
import quiz_ui
import skill6_playwright as runner


def config():
    old = [{'label':'Tier ' + str(i + 1), 'from':low, 'to':high}
           for i, (low, high) in enumerate(((0, 24), (25, 49), (50, 74), (75, 100)))]
    return {'expected_tier_labels':[tier['label'] for tier in old],
            'expected_tiers':old,
            'tiers':[{'label':'New ' + str(i + 1), 'from':low, 'to':high}
                     for i, (low, high) in enumerate(((0, 19), (20, 39), (40, 79), (80, 100)))]}


class ExistingTierLayouts(unittest.TestCase):
    def test_complete_four_tier_inventory_is_accepted_without_creating_rows(self):
        value = config()
        self.assertEqual(quiz_ui.validate(value), value)
        del value['expected_tiers']
        with self.assertRaises(quiz_ui.QuizError):
            quiz_ui.validate(value)

    def test_expected_ranges_and_labels_are_complete_unambiguous_and_contiguous(self):
        for change in ('missing_row', 'wrong_label', 'bool_range', 'gap', 'duplicate_label'):
            value = config()
            if change == 'missing_row':
                value['expected_tiers'].pop()
            elif change == 'wrong_label':
                value['expected_tiers'][0]['label'] = 'Unrelated'
            elif change == 'bool_range':
                value['expected_tiers'][0]['from'] = False
            elif change == 'gap':
                value['expected_tiers'][1]['from'] = 26
            else:
                value['expected_tier_labels'][1] = value['expected_tier_labels'][0]
            with self.subTest(change=change), self.assertRaises(quiz_ui.QuizError):
                quiz_ui.validate(value)

    def surface(self, *, drift=False, shape=False, lost=False):
        value = config()
        state = {'labels':copy.deepcopy(value['expected_tier_labels']),
                 'ranges':[str(tier[key]) for tier in value['expected_tiers'] for key in ('from', 'to')],
                 'fills':0, 'saves':0, 'reopened':False}
        if drift:
            state['ranges'][2] = '26'
        page, frame, popup, modal = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/quiz-builder-v2/quiz'
        page.frame_locator.return_value = frame
        title = MagicMock()
        title.input_value.return_value = 'Exact quiz'
        labels, ranges = MagicMock(), MagicMock()
        labels.count.return_value = 3 if shape else 4
        ranges.count.return_value = 8
        controls = {}
        def control(group, index):
            if (group, index) in controls:
                return controls[group, index]
            item = MagicMock()
            item.input_value.side_effect = lambda:state[group][index]
            item.is_enabled.return_value = group == 'labels' or index not in (0, 7)
            def write(text):
                state['fills'] += 1
                state[group][index] = text
            item.fill.side_effect = write
            controls[group, index] = item
            return item
        labels.nth.side_effect = lambda index:control('labels', index)
        ranges.nth.side_effect = lambda index:control('ranges', index)
        popup.count.return_value = 1
        popup.filter.return_value = popup
        frame.locator.return_value = popup
        save = MagicMock()
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda:state.__setitem__('saves', state['saves'] + 1)
        popup.get_by_role.side_effect = lambda role, **kw: (labels if kw.get('name') == 'Label' else ranges) if role == 'textbox' else save
        modal.get_by_role.return_value = save
        back = MagicMock()
        back.count.return_value = 1
        frame.get_by_role.side_effect = lambda role, **kw: (title if role == 'textbox' else modal if role == 'dialog' else back if kw.get('name') == 'Back' else save)
        def reopen(*args):
            state['reopened'] = True
            if lost:
                state['ranges'][2] = '25'
        return page, state, reopen

    def run_surface(self, page, reopen):
        with patch.object(runner, 'click', side_effect=lambda loc:loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value:loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda pred, message:self.assertTrue(pred())), \
             patch.object(assessments, 'reopen_editor', side_effect=reopen):
            return quiz_ui.configure(page, config())

    def test_four_existing_native_rows_save_and_independently_reopen(self):
        page, state, reopen = self.surface()
        result = self.run_surface(page, reopen)
        self.assertTrue(state['reopened'])
        self.assertEqual(state['labels'], [tier['label'] for tier in config()['tiers']])
        self.assertEqual(state['ranges'], [str(tier[key]) for tier in config()['tiers'] for key in ('from', 'to')])
        self.assertEqual(result['status'], 'QUIZ_CONFIGURATION_SAVED_AND_REOPENED')
        self.assertFalse(result['submission_verified'])

    def test_old_range_drift_or_row_shape_stops_before_first_fill(self):
        for params in ({'drift':True}, {'shape':True}):
            page, state, reopen = self.surface(**params)
            with self.subTest(params=params), self.assertRaises(runner.Stop):
                self.run_surface(page, reopen)
            self.assertEqual(state['fills'], 0)
            self.assertFalse(state['reopened'])

    def test_lost_range_after_reopen_is_not_completion(self):
        page, state, reopen = self.surface(lost=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, reopen)
        self.assertTrue(state['reopened'])


if __name__ == '__main__':
    unittest.main()
