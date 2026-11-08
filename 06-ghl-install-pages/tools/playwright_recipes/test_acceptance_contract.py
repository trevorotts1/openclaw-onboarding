"""Acceptance boundaries across handlers, not selector or implementation mirrors.

These checks deliberately use the public execution seam and a failing handler,
so they catch an incomplete new lane being promoted to a completed build.
No network, browser process, credentials or client account is involved.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import skill6_playwright as runner


def two_steps():
    return {
        'location_id': 'FIXTURE', 'location_name': 'Acceptance fixture',
        'start_url': 'https://app.convertandflow.com/v2/location/FIXTURE/dashboard',
        'steps': [
            {'id': 'one', 'action': 'options'},
            {'id': 'two', 'action': 'options'},
        ],
    }


class AcceptanceBoundaryTests(unittest.TestCase):
    def test_incomplete_handler_cannot_complete_or_continue_build(self):
        for status in ('NEEDS_CAPTURE', 'HANDOFF_REQUIRED', 'BLOCKED', 'API_ROUTE',
                       'NEEDS_VERIFICATION', 'STOP_AUTH', 'PENDING_CAPTURE',
                       'NO_OP', 'UNKNOWN'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                with patch.object(runner, 'assert_tenant'), patch.object(
                    runner, 'options', return_value={'status': status}
                ) as handler:
                    try:
                        result = runner.run_on_page(object(), two_steps(), directory)
                    except runner.Stop:
                        result = None
                state = json.loads(Path(directory, 'state.json').read_text())
                self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
                if result is not None:
                    self.assertNotEqual(result['status'], 'EDITOR_STEPS_COMPLETE')
                self.assertEqual(handler.call_count, 1, 'An incomplete step must stop later writes')

    def test_missing_handler_result_is_not_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, 'assert_tenant'), patch.object(
                runner, 'options', return_value=None
            ) as handler:
                with self.assertRaises(runner.Stop):
                    runner.run_on_page(object(), two_steps(), directory)
            state = json.loads(Path(directory, 'state.json').read_text())
            self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
            self.assertEqual(handler.call_count, 1)

    def test_pending_independent_readback_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            job = two_steps()
            job['steps'] = job['steps'][:1]
            with patch.object(runner, 'assert_tenant'), patch.object(
                runner, 'options', return_value={
                    'status': 'RECORDED_OPTIONS_EXECUTED',
                    'independent_readback': 'REQUIRED',
                }
            ):
                try:
                    result = runner.run_on_page(object(), job, directory)
                except runner.Stop:
                    result = None
            state = json.loads(Path(directory, 'state.json').read_text())
            self.assertNotEqual(state['status'], 'EDITOR_STEPS_COMPLETE')
            if result is not None:
                self.assertNotEqual(result['status'], 'EDITOR_STEPS_COMPLETE')


if __name__ == '__main__':
    unittest.main()
