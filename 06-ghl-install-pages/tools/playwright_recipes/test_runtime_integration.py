"""Real host/provider seams; fake transport only, no live credentials or writes."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import host
import route
import preflight
import os
import checkpoint
import tarfile
import subprocess
import fcntl


class HostRuntimeTests(unittest.TestCase):
    def inputs(self):
        return {'location_id':'LOC_TEST', 'location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/LOC_TEST/dashboard'}

    def probes(self):
        return {'lanes': {'playwright':{'available':True}},
                'api_capabilities': {'courses.create':{
                    'location_id':'LOC_TEST', 'observed_at':time.time(),
                    'provider':'public_api', 'version':'v3', 'scope_ok':True,
                    'supported':True}}}

    def test_package_import_uses_existing_host_modules(self):
        tools = Path(__file__).resolve().parent.parent
        with patch.object(sys, 'path', [str(tools), *sys.path]):
            module = importlib.import_module('playwright_recipes.host')
            self.assertTrue(callable(module.run_recipe))
            self.assertTrue(callable(importlib.import_module('browser_manager').PlaywrightSession))
            self.assertTrue(callable(importlib.import_module('ghl_auth').mint_and_bridge))

    def test_api_callback_executes_once_and_retains_only_minimal_outcome(self):
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE',
            'location_id':'LOC_TEST', 'objects':[{'kind':'course','id':'course_fixture'}], 'private_response':'FAKE_SECRET_NOT_FOR_LOGS'})
        with tempfile.TemporaryDirectory() as directory:
            one = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.', executors={'public_api':callback})
            # Match the same probe's exact route, not a new dispatch fingerprint.
            two = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.', executors={'public_api':callback})
            self.assertEqual(one['status'], 'API_STEPS_COMPLETE')
            self.assertEqual(two['status'], 'ALREADY_EXECUTED')
            self.assertEqual(callback.call_count, 1)
            state = Path(directory, 'provider-state.json')
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(directory).stat().st_mode & 0o777, 0o700)
            self.assertNotIn('FAKE_SECRET_NOT_FOR_LOGS', state.read_text())
            self.assertNotIn('FAKE_SECRET_NOT_FOR_LOGS', json.dumps(one))
            self.assertTrue(one['result']['verification_required'])
            self.assertEqual(one['result']['objects'], [{'kind':'course','id':'course_fixture'}])

    def test_pending_verification_remains_pending_without_reexecuting_provider(self):
        callback = Mock(return_value={'status':'NEEDS_VERIFICATION',
            'location_id':'LOC_TEST', 'objects':[{'kind':'course','id':'course_fixture'}]})
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                    input_dir='.', executors={'public_api':callback})
                self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
                self.assertTrue(result['result']['verification_required'])
            self.assertEqual(callback.call_count, 1)
            state = json.loads(Path(directory, 'provider-state.json').read_text())
            self.assertEqual(state['status'], 'PROVIDER_NEEDS_VERIFICATION')
            # Old journals used the completed wrapper for a pending outcome.
            state['status'] = 'PROVIDER_STEPS_COMPLETE'
            Path(directory, 'provider-state.json').write_text(json.dumps(state))
            result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.', executors={'public_api':callback})
            self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
            self.assertEqual(callback.call_count, 1)

    def test_course_update_uses_builtin_executor_after_api_receipt(self):
        import delivery
        inputs = self.inputs()
        inputs['api_capability'] = {'status':'fixture'}
        probes = self.probes()
        probes['api_capabilities']['courses.update'] = probes['api_capabilities']['courses.create']
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE',
            'location_id':'LOC_TEST','objects':[{'kind':'course','id':'existing_course'}]})
        with tempfile.TemporaryDirectory() as directory, patch.object(delivery, 'course_executor', callback):
            result = host.run_recipe('courses.update', inputs, probes, directory, input_dir='.')
            self.assertEqual(result['status'], 'API_STEPS_COMPLETE')
            self.assertEqual(callback.call_args.kwargs['operation'], 'courses.update')
        self.assertEqual(route.decide('courses.update','LOC_TEST',{'lanes':{'playwright':{'available':True}}})['lane'], 'PROBE_API')

    def test_active_provider_lease_blocks_second_writer_before_callback(self):
        callback = Mock()
        with tempfile.TemporaryDirectory() as directory:
            with open(Path(directory)/'provider.lock', 'w') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                    input_dir='.', executors={'public_api':callback})
                self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')
                callback.assert_not_called()
                self.assertFalse(Path(directory,'provider-state.json').exists())

    def test_provider_failure_preserves_intent_and_never_retries(self):
        callback = Mock(side_effect=RuntimeError('DO_NOT_LOG_SECRET'))
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                    input_dir='.', executors={'public_api':callback})
                self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')
            self.assertEqual(callback.call_count, 1)
            self.assertNotIn('DO_NOT_LOG_SECRET', Path(directory,'provider-state.json').read_text())

    def test_create_without_concrete_identity_never_becomes_complete(self):
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'LOC_TEST'})
        with tempfile.TemporaryDirectory() as directory:
            result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.', executors={'public_api':callback})
            self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')

    def test_wrong_location_result_never_becomes_complete(self):
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'OTHER'})
        with tempfile.TemporaryDirectory() as directory:
            result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.', executors={'public_api':callback})
            self.assertEqual(result['status'], 'PROVIDER_RECONCILIATION_REQUIRED')

    def test_unsupported_api_keeps_existing_handoff_without_guessing_command(self):
        with tempfile.TemporaryDirectory() as directory:
            result = host.run_recipe('courses.create', self.inputs(), self.probes(), directory,
                input_dir='.')
            self.assertEqual(result['status'], 'HANDOFF_REQUIRED')
            self.assertFalse(result['browser_used'])

    def test_supported_course_uses_builtin_http_executor_only_for_http_routes(self):
        import delivery
        inputs = self.inputs()
        inputs['api_capability'] = {'status':'fixture'}
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'LOC_TEST','objects':[{'kind':'course','id':'course_fixture'}]})
        with tempfile.TemporaryDirectory() as directory, patch.object(delivery, 'course_executor', callback):
            result = host.run_recipe('courses.create', inputs, self.probes(), directory, input_dir='.')
            self.assertEqual(result['status'], 'API_STEPS_COMPLETE')
            self.assertEqual(callback.call_count, 1)
        probes = self.probes()
        probes['api_capabilities']['courses.create']['provider'] = 'official_mcp'
        with tempfile.TemporaryDirectory() as directory, patch.object(delivery, 'course_executor', callback):
            result = host.run_recipe('courses.create', inputs, probes, directory, input_dir='.')
            self.assertEqual(result['status'], 'HANDOFF_REQUIRED')
            self.assertEqual(callback.call_count, 1)

    def test_auth_refusal_never_invokes_provider(self):
        probes = self.probes()
        probes['api_capabilities']['courses.create']['http_status'] = 403
        callback = Mock()
        with tempfile.TemporaryDirectory() as directory:
            result = host.run_recipe('courses.create', self.inputs(), probes, directory,
                input_dir='.', executors={'public_api':callback})
            self.assertEqual(result['route']['lane'], 'STOP_AUTH')
            callback.assert_not_called()

    def test_invalid_input_and_probe_are_named_without_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(host.run_recipe('forms.create', None, {}, directory,
                input_dir='.')['status'], 'STOP_INVALID_INPUT')
            self.assertEqual(host.run_recipe('forms.create', self.inputs(), None, directory,
                input_dir='.')['status'], 'STOP_INVALID_PROBE')
        for probes in ({'api_capabilities':[]}, {'api_capabilities':{'forms.create':[]}}, {'lanes':[]}):
            self.assertEqual(route.decide('forms.create','LOC_TEST',probes)['lane'], 'STOP_INVALID_PROBE')
        # A supplied capability receipt cannot turn an unregistered operation into a write.
        probes = self.probes()
        probes['api_capabilities']['invented.write'] = probes['api_capabilities']['courses.create']
        self.assertEqual(route.decide('invented.write','LOC_TEST',probes)['lane'], 'STOP_UNKNOWN_OPERATION')


class PreflightRuntimeTests(unittest.TestCase):
    def test_pip_without_browser_cannot_report_ready(self):
        runtime = {'package_installed':True,'driver_usable':True,
                   'chromium_installed':False,'reason':'CHROMIUM_EXECUTABLE_MISSING'}
        with patch.object(preflight, 'browser_runtime', return_value=runtime), patch.dict(os.environ, {}, clear=True):
            result = preflight.check()
        self.assertEqual(result['status'], 'HOST_SETUP_REQUIRED')
        self.assertEqual(result['browser_runtime_reason'], 'CHROMIUM_EXECUTABLE_MISSING')
        self.assertFalse(result['browser_used'])

    def test_loopback_cdp_can_use_existing_host_but_public_endpoint_cannot(self):
        runtime = {'package_installed':True,'driver_usable':True,
                   'chromium_installed':False,'reason':'CHROMIUM_EXECUTABLE_MISSING'}
        for endpoint, expected in [('http://127.0.0.1:9222', True),
                                   ('http://public.example:9222', False),
                                   ('http://secret@localhost:9222', False)]:
            with self.subTest(endpoint=endpoint), patch.object(preflight, 'browser_runtime', return_value=runtime), patch.dict(os.environ, {'GHL_MANAGED_CDP_URL':endpoint}, clear=True):
                result = preflight.check()
                self.assertEqual(result['managed_loopback_cdp_configured'], expected)
                self.assertNotIn(endpoint, json.dumps(result))

    def test_unsupported_platform_does_not_report_ready(self):
        runtime = {'package_installed':True,'driver_usable':True,
                   'chromium_installed':True,'reason':'READY'}
        with patch.object(preflight, 'browser_runtime', return_value=runtime), patch.object(preflight.platform, 'system', return_value='Windows'):
            self.assertEqual(preflight.check()['status'], 'HOST_SETUP_REQUIRED')


class StandaloneCheckpointTests(unittest.TestCase):
    def test_checkpoint_survives_missing_git_on_an_installed_host(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(checkpoint.subprocess, 'run', side_effect=FileNotFoundError):
            output = checkpoint.snapshot(directory)
            with tarfile.open(output) as archive:
                manifest = json.load(archive.extractfile('MANIFEST.json'))
            self.assertIsNone(manifest['base_commit'])
            self.assertTrue(manifest['sha256'])


class HostCLITests(unittest.TestCase):
    def test_check_mode_selects_lane_without_opening_browser_or_writing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {'location_id':'LOC_TEST','location_name':'Fixture',
                'start_url':'https://app.convertandflow.com/v2/location/LOC_TEST/dashboard',
                'name':'Fixture Form','allow_creation':True}
            (root/'inputs.json').write_text(json.dumps(inputs))
            (root/'probes.json').write_text(json.dumps({'lanes':{'playwright':{'available':True}}}))
            evidence = root/'evidence'
            result = subprocess.run([sys.executable, host.__file__, '--operation','forms.create',
                '--inputs',str(root/'inputs.json'),'--probes',str(root/'probes.json'),
                '--evidence-root',str(evidence),'--check'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['status'], 'VALIDATED_ONLY')
            self.assertFalse(receipt['browser_used'])
            self.assertFalse(evidence.exists())


if __name__ == '__main__':
    unittest.main()
