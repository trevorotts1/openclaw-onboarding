"""A retained API/portal outcome cannot become a new editor/browser run."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import skill6_playwright as runner


class ReverseLaneEditorTests(unittest.TestCase):
    def test_foreign_outcomes_stop_before_any_browser_read_and_preserve_bytes(self):
        journals = ('provider-state.json', 'community-portal-state.json', 'auth-stop.json',
                    'delivery-state.json', 'calendar-delivery-state.json',
                    'community-details-state.json')
        for journal in journals:
            for content in (b'{"status":"INTENT_RECORDED"}',
                            b'{"status":"DELIVERY_COMPLETE"}', b'{malformed', b''):
                with self.subTest(journal=journal, content=content), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / journal).write_bytes(content)
                    page = Mock()
                    with self.assertRaisesRegex(runner.Stop, 'requires reconciliation'):
                        runner.run_on_page(page, {}, root)
                    self.assertEqual(page.mock_calls, [])
                    self.assertEqual((root / journal).read_bytes(), content)
                    self.assertFalse((root / 'state.json').exists())
                    self.assertFalse((root / 'handoff.json').exists())

    def test_direct_execute_stops_before_managed_or_attached_browser_setup(self):
        for journal in ('delivery-state.json', 'calendar-delivery-state.json',
                        'community-details-state.json'):
            for endpoint in ('', 'http://localhost:9222'):
                with self.subTest(journal=journal, endpoint=endpoint), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / journal).write_bytes(b'{prior-uncertain')
                    with patch.dict('os.environ', {'GHL_MANAGED_CDP_URL':endpoint}), \
                            patch('browser_manager.PlaywrightSession') as browser, \
                            patch('ghl_auth.mint_and_bridge') as auth, \
                            patch.object(runner, 'run_on_page') as run:
                        with self.assertRaisesRegex(runner.Stop, 'requires reconciliation'):
                            runner.execute({}, root)
                        browser.assert_not_called()
                        auth.assert_not_called()
                        run.assert_not_called()
                    self.assertEqual((root / journal).read_bytes(), b'{prior-uncertain')
                    self.assertFalse((root / 'auth-runtime').exists())

    def test_dangling_foreign_journal_link_is_not_treated_as_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = root / 'delivery-state.json'
            journal.symlink_to(root / 'missing-original-journal')
            page = Mock()
            with self.assertRaisesRegex(runner.Stop, 'requires reconciliation'):
                runner.run_on_page(page, {}, root)
            self.assertTrue(journal.is_symlink())
            self.assertEqual(page.mock_calls, [])

    def test_unrelated_file_does_not_invent_a_foreign_lane_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notes.txt').write_text('private operator note')
            page = Mock()
            with patch.object(runner, '_run_on_page', return_value={'status':'fixture-only'}) as run:
                result = runner.run_on_page(page, {}, root)
            self.assertEqual(result['status'], 'fixture-only')
            run.assert_called_once_with(page, {}, root.resolve())
            self.assertEqual((root / 'notes.txt').read_text(), 'private operator note')


if __name__ == '__main__':
    unittest.main()
