"""Native checkout and HTML placement must use the requested GHL column."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import skill6_playwright as runner


class PlacementTests(unittest.TestCase):
    def test_html_file_is_checked_before_execution(self):
        job = {'location_id': 'LOC', 'location_name': 'Fixture',
               'start_url': 'https://app.convertandflow.com/v2/location/LOC/',
               'steps': [{'id': 'code', 'action': 'html', 'file': 'page.html', 'marker': 'Welcome'}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'page.html'
            path.write_text('<p>Welcome</p><script src="https://js.stripe.com/v3/"></script>')
            with self.assertRaisesRegex(runner.Stop, 'native GHL'):
                runner.validate_job(job, Path(directory))
            path.write_text('<p>Welcome</p><a href="https://example.com/checkout">Pay</a>')
            prepared = runner.validate_job(job, Path(directory))
            self.assertIn('Welcome', prepared['steps'][0]['html'])

    def test_exact_placement_selects_resolved_column(self):
        frame, target = Mock(), Mock()
        placement = {'section_id': 'section1', 'row_id': 'row2',
                     'column_index': 1, 'expected_columns': 3}
        with patch('playwright_recipes.page_layout.resolve_column', return_value=target) as resolve, \
             patch.object(runner, 'click') as click:
            runner.select_install_column(frame, placement)
        resolve.assert_called_once_with(frame, placement)
        click.assert_called_once_with(target)
        frame.get_by_role.assert_not_called()

    def test_rejects_ambiguous_and_unbounded_placements(self):
        base = {'section_id': 'section1', 'row_id': 'row1'}
        for extra in ({}, {'column_index': 0}, {'column_id': 'x', 'column_index': 0},
                      {'column_index': 2, 'expected_columns': 2},
                      {'column_index': True, 'expected_columns': 2}):
            with self.subTest(extra=extra), self.assertRaises(runner.Stop):
                runner.validate_placement({**base, **extra})

    def test_legacy_shorthand_rejects_multiple_columns(self):
        frame = Mock()
        frame.locator.return_value.count.return_value = 2
        with self.assertRaises(runner.Stop), patch.object(runner, 'click') as click:
            runner.select_install_column(frame)
        click.assert_not_called()

    def test_legacy_shorthand_accepts_only_single_column(self):
        frame = Mock()
        frame.locator.return_value.count.return_value = 1
        frame.get_by_role.return_value.count.return_value = 1
        with patch.object(runner, 'visible', return_value=True), patch.object(runner, 'click') as click:
            runner.select_install_column(frame)
        click.assert_called_once_with(frame.get_by_role.return_value)

    def test_existing_orders_must_remain_in_place(self):
        order = {'id': 'o', 'section_id': 's', 'row_id': 'r', 'column_id': 'c'}
        runner.assert_native_orders_preserved({'o': order}, {'o': order})
        with self.assertRaises(runner.Stop):
            runner.assert_native_orders_preserved({'o': order}, {'o': {**order, 'column_id': 'other'}})
        with self.assertRaises(runner.Stop):
            runner.assert_native_orders_preserved({'o': order}, {})

    def test_checkout_with_placement_always_inserts_native_order_form(self):
        page, frame = Mock(), Mock()
        placement = {'section_id': 's', 'row_id': 'r', 'column_id': 'c'}
        dialog = frame.get_by_role.return_value.filter.return_value
        dialog.get_by_text.return_value.count.return_value = 1
        order = {'id': 'order1', 'section_id': 's', 'row_id': 'r', 'column_id': 'c'}
        frame.locator.return_value.count.return_value = 1
        with patch.object(runner, 'native_order_inventory', side_effect=[{}, {'order1': order}, {'order1': order}]), \
             patch.object(runner, 'placement_column_id', return_value='c'), \
             patch.object(runner, 'wait_until'), \
             patch.object(runner, 'builder', return_value=frame), \
             patch.object(runner, 'select_install_column') as select, \
             patch.object(runner, 'add_tile') as add, \
             patch.object(runner, 'click'), patch.object(runner, 'save_page'):
            result = runner.checkout(page, {'placement': placement})
        select.assert_called_once_with(frame, placement)
        add.assert_called_once_with(frame, 'Elements', 'Order Form')
        self.assertFalse(result['checkout_ready'])
        self.assertFalse(result['payment_verified'])


if __name__ == '__main__':
    unittest.main()
