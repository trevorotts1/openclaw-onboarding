"""The maintained outline runner must remain bound through host and check mode."""
from contextlib import redirect_stdout
from copy import deepcopy
import fcntl
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import delivery
import host
import test_course_outline as fixtures


def inputs():
    return {**fixtures.plan(), 'api_capability': fixtures.capability()}


def probes():
    return {'api_capabilities': {'courses.lessons': {
        'location_id': 'LOC', 'observed_at': time.time(), 'supported': True,
        'provider': 'public_api', 'scope_ok': True, 'version': 'v3'}}}


class CourseOutlineHostQcTests(unittest.TestCase):
    def test_default_host_executes_real_outline_under_shared_lease_and_replays_pending_without_http(self):
        with tempfile.TemporaryDirectory() as root:
            test = self
            class LeasedApi(fixtures.Api):
                def request(self, *args, **kwargs):
                    provider = json.loads(Path(root, 'provider-state.json').read_text())
                    test.assertEqual(provider['status'], 'PROVIDER_INTENT_RECORDED')
                    for name in ('.runner.lock', 'provider.lock'):
                        fd = os.open(Path(root, name), os.O_RDWR)
                        try:
                            with test.assertRaises(BlockingIOError):
                                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        finally:
                            os.close(fd)
                    return super().request(*args, **kwargs)
            api = LeasedApi(root)
            data, observed = inputs(), probes()
            with patch.object(delivery, 'Skill44Transport', return_value=api) as transport, \
                    patch.object(host, 'execute') as browser:
                first = host.run_recipe('courses.lessons', data, observed, root, input_dir='.')
                before = len(api.calls)
                repeated = host.run_recipe('courses.lessons', data, observed, root, input_dir='.')
            self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(repeated['status'], 'NEEDS_VERIFICATION')
            self.assertFalse(first['browser_used'])
            self.assertFalse(repeated['browser_used'])
            self.assertTrue(repeated['replayed'])
            self.assertIs(first['result']['verification_required'], True)
            self.assertEqual(first['result']['objects'], repeated['result']['objects'])
            self.assertEqual({(row['kind'], row['id']) for row in first['result']['objects']},
                             {('course', 'P'), ('category', 'C1'), ('category', 'C2'), ('lesson', 'L2')})
            self.assertEqual([body for method, _, body in api.calls if method == 'PUT'],
                             [{'title': 'Updated module'}, {'description': 'Updated lesson'}])
            self.assertEqual(len(api.calls), before)
            transport.assert_called_once_with()
            browser.assert_not_called()
            state = json.loads(Path(root, 'delivery-state.json').read_text())
            self.assertEqual(state['completed'], [{'kind': 'category', 'id': 'C1'}, {'kind': 'lesson', 'id': 'L2'}])

    def test_host_invalid_outline_inputs_never_construct_transport_or_fall_back_to_browser(self):
        variants = []
        data = inputs(); data.pop('product_id'); variants.append(data)
        data = inputs(); data['lesson_changes'][0].pop('expected_updated_at'); variants.append(data)
        data = inputs(); data['lesson_changes'][0]['changes'] = {'visibility': 'published'}; variants.append(data)
        for data in variants:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as root, \
                    patch.object(delivery, 'Skill44Transport') as transport, \
                    patch.object(host, 'execute') as browser:
                result = host.run_recipe('courses.lessons', data, probes(), root, input_dir='.')
                self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')
                self.assertFalse(result['browser_used'])
                self.assertFalse(Path(root, 'delivery-state.json').exists())
                transport.assert_not_called()
                browser.assert_not_called()

    def test_http_default_does_not_replace_an_official_mcp_route(self):
        observed = probes()
        observed['api_capabilities']['courses.lessons']['provider'] = 'official_mcp'
        with tempfile.TemporaryDirectory() as root, \
                patch.object(delivery, 'Skill44Transport') as transport, \
                patch.object(host, 'execute') as browser:
            result = host.run_recipe('courses.lessons', inputs(), observed, root, input_dir='.')
            self.assertEqual(result['status'], 'HANDOFF_REQUIRED')
            self.assertEqual(result['route']['lane'], 'official_mcp')
            self.assertFalse(result['browser_used'])
            transport.assert_not_called()
            browser.assert_not_called()

    def test_cli_check_uses_real_outline_schema_without_transport_or_evidence(self):
        variants = [(inputs(), 0, 'VALIDATED_ONLY')]
        for key in ('product_id', 'location_id', 'api_capability'):
            data = inputs(); data.pop(key); variants.append((data, 2, 'STOP_INVALID_INPUT'))
        data = inputs(); data['lesson_changes'][0]['changes'] = {'contentType': 'unknown'}
        variants.append((data, 2, 'STOP_INVALID_INPUT'))
        data = inputs(); data['publish'] = True; variants.append((data, 2, 'STOP_INVALID_INPUT'))
        for data, expected_code, expected_status in variants:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as root, \
                    patch.object(delivery, 'Skill44Transport') as transport, \
                    patch.object(host, 'execute') as browser:
                source, measured, evidence = Path(root, 'inputs.json'), Path(root, 'probes.json'), Path(root, 'evidence')
                source.write_text(json.dumps(data)); measured.write_text(json.dumps(probes()))
                output = io.StringIO()
                with redirect_stdout(output):
                    code = host.main(['--operation', 'courses.lessons', '--inputs', str(source),
                                      '--probes', str(measured), '--evidence-root', str(evidence), '--check'])
                self.assertEqual(code, expected_code)
                self.assertEqual(json.loads(output.getvalue())['status'], expected_status)
                self.assertFalse(evidence.exists())
                transport.assert_not_called()
                browser.assert_not_called()

    def test_host_replay_refuses_foreign_missing_and_duplicate_outline_target_receipts(self):
        corruptions = [
            lambda objects: objects[0].update(id='FOREIGN'),
            lambda objects: objects[-1].update(id='FOREIGN'),
            lambda objects: objects.pop(),
            lambda objects: objects.append(deepcopy(objects[-1])),
        ]
        for index, corrupt in enumerate(corruptions):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as root:
                api = fixtures.Api(root)
                data, observed = inputs(), probes()
                with patch.object(delivery, 'Skill44Transport', return_value=api):
                    first = host.run_recipe('courses.lessons', data, observed, root, input_dir='.')
                    self.assertEqual(first['status'], 'NEEDS_VERIFICATION')
                    path = Path(root, 'provider-state.json')
                    state = json.loads(path.read_text())
                    corrupt(state['outcome']['objects'])
                    damaged = json.dumps(state); path.write_text(damaged)
                    before = len(api.calls)
                    repeated = host.run_recipe('courses.lessons', data, observed, root, input_dir='.')
                self.assertEqual(repeated['status'], 'PROVIDER_RECONCILIATION_REQUIRED')
                self.assertEqual(len(api.calls), before)
                self.assertEqual(path.read_text(), damaged)

    def test_initial_provider_outcome_cannot_claim_another_outline_target(self):
        objects = [{'kind': 'course', 'id': 'FOREIGN'}, {'kind': 'category', 'id': 'C1'},
                   {'kind': 'category', 'id': 'C2'}, {'kind': 'lesson', 'id': 'L2'}]
        def provider(**_kwargs):
            return {'status': 'NEEDS_VERIFICATION', 'location_id': 'LOC', 'objects': objects}
        with tempfile.TemporaryDirectory() as root:
            result = host.run_recipe('courses.lessons', inputs(), probes(), root,
                                     input_dir='.', executors={'public_api': provider})
            self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')
            state = json.loads(Path(root, 'provider-state.json').read_text())
            self.assertEqual(state['status'], 'PROVIDER_RECONCILIATION_REQUIRED')


if __name__ == '__main__':
    unittest.main()
