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
from datetime import datetime, timezone


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


class HostAPICheckTests(unittest.TestCase):
    def check(self, operation, changes, provider='public_api'):
        inputs = {'location_id':'LOC_TEST', 'location_name':'Fixture',
            'start_url':'https://app.convertandflow.com/v2/location/LOC_TEST/dashboard',
            'api_capability': {'location_id':'LOC_TEST', 'version':'v3', 'status':'PASS',
                'source':'fixture receipt', 'scopes':['courses.readonly','courses.write'],
                'checked_at':datetime.now(timezone.utc).isoformat()}, **changes}
        probes = {'api_capabilities':{operation:{'location_id':'LOC_TEST',
            'version':'v3','provider':provider,'supported':True,'scope_ok':True,
            'observed_at':time.time()}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'inputs.json').write_text(json.dumps(inputs))
            (root/'probes.json').write_text(json.dumps(probes))
            evidence = root/'evidence'
            result = subprocess.run([sys.executable, host.__file__, '--operation',operation,
                '--inputs',str(root/'inputs.json'),'--probes',str(root/'probes.json'),
                '--evidence-root',str(evidence),'--check'],capture_output=True,text=True,timeout=10)
            self.assertFalse(evidence.exists())
            return result, json.loads(result.stdout)

    def test_api_check_rejects_missing_course_and_update_payloads(self):
        for operation in ('courses.create','courses.update','courses.lesson_quiz.create'):
            with self.subTest(operation=operation):
                result, receipt = self.check(operation, {})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(receipt['status'], 'STOP_INVALID_INPUT')
                self.assertFalse(receipt['browser_used'])

    def test_api_check_accepts_complete_course_and_update_without_transport(self):
        for operation, changes in (
            ('courses.create', {'course':{'title':'Fixture course'}}),
            ('courses.update', {'product_id':'COURSE_TEST','course_changes':{'description':'Updated fixture'}}),
            ('courses.lesson_quiz.create', {'product_id':'COURSE_TEST','lesson_id':'LESSON_TEST',
                'quiz':{'title':'Fixture quiz', 'questions':[{'title':'Choose one','questionType':'single',
                    'sequenceNumber':1, 'options':[{'title':'Yes','isCorrect':True},{'title':'No','isCorrect':False}]}]}})):

            with self.subTest(operation=operation):
                result, receipt = self.check(operation, changes)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(receipt['status'], 'VALIDATED_ONLY')
                self.assertFalse(receipt['browser_used'])

    def test_api_check_validates_capability_scope_not_only_route_receipt(self):
        result, receipt = self.check('courses.create', {'course':{'title':'Fixture course'},
            'api_capability':{'location_id':'LOC_TEST','version':'v3','status':'PASS'}})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt['status'], 'STOP_INVALID_INPUT')


class NativeCheckoutReadinessTests(unittest.TestCase):
    def probes(self):
        return {'lanes':{'playwright':{'available':True},
            'openclaw_extension':{'available':True,'current':True}},
            'recorded_profiles':['checkout.one_click_upsell']}

    def test_valid_target_bound_native_capture_selects_playwright_without_options(self):
        from test_pages_checkout import inputs, capture
        data = inputs()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'capture.json').write_text(json.dumps(capture()))
            with patch.object(host, 'run_on_page', return_value={'status':'NEEDS_VERIFICATION'}) as runner:
                result = host.run_recipe('checkout.one_click_upsell', data, self.probes(),
                    Path(directory)/'evidence', input_dir=directory, page=object())
            self.assertEqual(result['route']['lane'], 'playwright')
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(runner.call_args.args[1]['steps'][0]['action'], 'native_checkout')

    def test_invalid_or_absent_capture_cannot_be_blessed_by_a_recorded_profile(self):
        from test_pages_checkout import inputs, capture
        for variant in ('missing','wrong_location','unsafe_route'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                data = inputs()
                if variant != 'missing':
                    receipt = capture()
                    if variant == 'wrong_location': receipt['location_id'] = 'OTHER'
                    else: receipt['autosave']['path'] = '//untrusted.invalid/write'
                    Path(directory,'capture.json').write_text(json.dumps(receipt))
                with patch.object(host, 'run_on_page') as runner, patch.object(host, 'execute') as execute:
                    result = host.run_recipe('checkout.one_click_upsell',data,self.probes(),
                        Path(directory)/'evidence',input_dir=directory,page=object())
                self.assertEqual(result['status'], 'NEEDS_BROWSER_RECOVERY')
                self.assertEqual(result['route']['lane'], 'openclaw_extension')
                runner.assert_not_called()
                execute.assert_not_called()

    def test_check_mode_refuses_capture_before_any_browser_or_evidence(self):
        from test_pages_checkout import inputs
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'inputs.json').write_text(json.dumps(inputs()))
            (root/'probes.json').write_text(json.dumps(self.probes()))
            result = subprocess.run([sys.executable,host.__file__,'--operation','checkout.one_click_upsell',
                '--inputs',str(root/'inputs.json'),'--probes',str(root/'probes.json'),
                '--evidence-root',str(root/'evidence'),'--check'],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'STOP_INVALID_CAPTURE')
            self.assertFalse((root/'evidence').exists())


class MeetingCalendarRoutingTests(unittest.TestCase):
    def inputs(self):
        return {'location_id':'LOC_TEST','location_name':'Fixture',
            'start_url':'https://app.convertandflow.com/v2/location/LOC_TEST/dashboard',
            'integration_mode':'permanent_calendar_link', 'calendar_id':'CAL_TEST',
            'room':{'status':'PRESENT','location_id':'LOC_TEST','room_id':'ROOM_TEST',
                'url':'https://meet.example.test/permanent','source':'fixture'},
            'api_capability':{'location_id':'LOC_TEST','version':'v3','status':'PASS',
                'source':'fixture', 'scopes':['calendars.readonly','calendars.write'],
                'checked_at':datetime.now(timezone.utc).isoformat()}}

    def probes(self):
        return {'lanes':{'playwright':{'available':True}},
            'api_capabilities':{'meetings.integrate':{'location_id':'LOC_TEST',
                'observed_at':time.time(),'version':'v3','provider':'public_api',
                'supported':True,'scope_ok':True}}}

    def test_static_calendar_mode_uses_actual_installed_provider_callback(self):
        import delivery
        callback = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':'LOC_TEST',
            'objects':[{'kind':'calendar','id':'CAL_TEST'}]})
        with tempfile.TemporaryDirectory() as directory, patch.object(delivery,'meeting_calendar_executor',callback):
            result = host.run_recipe('meetings.integrate',self.inputs(),self.probes(),directory,input_dir='.')
        self.assertEqual(result['status'],'API_STEPS_COMPLETE')
        self.assertEqual(callback.call_count,1)
        self.assertEqual(callback.call_args.kwargs['inputs']['integration_mode'],'permanent_calendar_link')

    def test_missing_or_dynamic_mode_cannot_silently_use_static_provider(self):
        import delivery
        for mode, expected in ((None,'STOP_INTEGRATION_MODE_REQUIRED'),('dynamic_appointment_room','STOP_UNSUPPORTED_INTEGRATION_MODE')):
            inputs = self.inputs()
            if mode is None:inputs.pop('integration_mode')
            else:inputs['integration_mode']=mode
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, patch.object(delivery,'meeting_calendar_executor') as callback:
                result = host.run_recipe('meetings.integrate',inputs,self.probes(),directory,input_dir='.')
                self.assertEqual(result['route']['lane'],expected)
                callback.assert_not_called()

    def test_static_link_requires_api_probe_and_never_becomes_ui_fallback(self):
        inputs=self.inputs();probes=self.probes();probes.pop('api_capabilities')
        self.assertEqual(route.decide('meetings.integrate','LOC_TEST',probes,inputs=inputs)['lane'],'PROBE_API')
        probes=self.probes();probes['api_capabilities']['meetings.integrate'].update(supported=False,reason='unsupported_endpoint')
        self.assertEqual(route.decide('meetings.integrate','LOC_TEST',probes,inputs=inputs)['lane'],'STOP_UNSUPPORTED_CALENDAR_API')

    def test_existing_captured_ui_options_are_separate_from_calendar_api(self):
        inputs = self.inputs();inputs.pop('integration_mode');inputs['options']={'capture_source':'fixture','steps':[]}
        probes=self.probes();probes['recorded_profiles']=['meetings.integrate']
        self.assertEqual(route.decide('meetings.integrate','LOC_TEST',probes,inputs=inputs)['lane'],'playwright')


class HeadlessShellDetectionTests(unittest.TestCase):
    def fixture(self, directory, revision='1208'):
        root=Path(directory); package=root/'package';package.mkdir()
        (package/'browsers.json').write_text(json.dumps({'browsers':[
            {'name':'chromium','revision':revision},
            {'name':'chromium-headless-shell','revision':revision}]}))
        return package, root/'cache'/('chromium-'+revision)/'chrome-mac'/'Chromium'

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture only, never executed')
        path.chmod(0o700)
        return path

    def test_shell_only_mac_is_detected_even_when_full_chromium_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            package,full=self.fixture(directory)
            shell=self.executable(Path(directory)/'cache/chromium_headless_shell-1208/chrome-mac/headless_shell')
            self.assertFalse(full.exists())
            self.assertEqual(preflight.headless_shell_executable(full,package_root=package,
                system='Darwin',machine='arm64'),shell)

    def test_matching_current_revision_and_arch_layouts(self):
        cases=[('Darwin','arm64','chrome-headless-shell-mac-arm64'),
               ('Darwin','x86_64','chrome-headless-shell-mac-x64'),
               ('Linux','x86_64','chrome-headless-shell-linux64'),
               ('Linux','aarch64','chrome-headless-shell-linux-arm64')]
        for system,machine,layout in cases:
            with self.subTest(system=system,machine=machine), tempfile.TemporaryDirectory() as directory:
                package,full=self.fixture(directory)
                shell=self.executable(Path(directory)/'cache/chromium_headless_shell-1208'/layout/'chrome-headless-shell')
                self.assertEqual(preflight.headless_shell_executable(full,package_root=package,
                    system=system,machine=machine),shell)

    def test_old_revision_nonexecutable_or_wrong_arch_cannot_bless_runtime(self):
        for variant in ('old_revision','nonexecutable','wrong_arch'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                package,full=self.fixture(directory)
                revision='1199' if variant=='old_revision' else '1208'
                layout='chrome-headless-shell-mac-x64' if variant=='wrong_arch' else 'chrome-headless-shell-mac-arm64'
                shell=self.executable(Path(directory)/'cache'/('chromium_headless_shell-'+revision)/layout/'chrome-headless-shell')
                if variant=='nonexecutable':shell.chmod(0o600)
                self.assertIsNone(preflight.headless_shell_executable(full,package_root=package,
                    system='Darwin',machine='arm64'))

    def test_shell_only_runtime_can_be_ready_for_host_probe(self):
        runtime={'package_installed':True,'driver_usable':True,'chromium_installed':False,
            'headless_shell_installed':True,'reason':'READY'}
        with patch.object(preflight,'browser_runtime',return_value=runtime), patch.dict(os.environ,{},clear=True):
            result=preflight.check()
        self.assertFalse(result['chromium_installed'])
        self.assertTrue(result['headless_shell_installed'])
        self.assertEqual(result['status'],'READY_FOR_HOST_PROBE')
        self.assertFalse(result['browser_used'])


class IntegrationCheckpointTests(unittest.TestCase):
    def fixture(self, directory):
        repo=Path(directory)/'repo'
        package=repo/'06-ghl-install-pages/tools/playwright_recipes'
        package.mkdir(parents=True)
        (package/'checkpoint.py').write_text('fixture source')
        (package/'catalog.json').write_text('{}')
        references=repo/'06-ghl-install-pages/references';references.mkdir()
        for name in ('PLAYWRIGHT-RECIPES.md','PLAYWRIGHT-PROGRESS.md','PLAYWRIGHT-REQUIREMENTS.md','PLAYWRIGHT-COMPLETION-MATRIX.md'):
            (references/name).write_text('fixture reference')
        return repo, package

    def test_registry_and_workflow_are_included_with_exact_hashes_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            repo,package=self.fixture(directory)
            selected=[checkpoint.INTEGRATION_SOURCES[0], '.github/workflows/skill6-recipes-portability.yml']
            for relative in selected:
                target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('fixture registry or workflow')
            with patch.object(checkpoint,'__file__',str(package/'checkpoint.py')):
                output=checkpoint.snapshot(Path(directory)/'out')
            with tarfile.open(output) as archive:
                manifest=json.load(archive.extractfile('MANIFEST.json'))
                for relative in selected:
                    self.assertIn(relative,archive.getnames())
                    self.assertIn(relative,manifest['integration_sources']['included'])
                    self.assertIn(relative,manifest['sha256'])
                self.assertFalse(manifest['repository_dependencies']['standalone_installation'])

    def test_standalone_source_reports_missing_integrations_without_reading_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            repo,package=self.fixture(directory)
            for relative in ('.env','AGENTS.md','client/auth-runtime/seed.json','23-ai-workforce-blueprint/private.md'):
                target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('FAKE_PRIVATE_EXCLUDED')
            with patch.object(checkpoint,'__file__',str(package/'checkpoint.py')), patch.object(checkpoint.subprocess,'run',side_effect=FileNotFoundError):
                output=checkpoint.snapshot(Path(directory)/'out')
            with tarfile.open(output) as archive:
                manifest=json.load(archive.extractfile('MANIFEST.json'))
                self.assertEqual(manifest['integration_sources']['included'],[])
                self.assertEqual(set(manifest['integration_sources']['missing']),set(checkpoint.INTEGRATION_SOURCES))
                self.assertTrue(manifest['repository_dependencies']['requires_existing_repository'])
                self.assertTrue(manifest['repository_dependencies']['missing_from_source_tree'])
                for member in archive.getmembers():
                    self.assertNotIn(b'FAKE_PRIVATE_EXCLUDED',archive.extractfile(member).read())


if __name__ == '__main__':
    unittest.main()
