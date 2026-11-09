"""Event room creation cannot escape its live portal context and intent journal."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import community_event_meeting as event
import community_portal as portal
import evidence_lease as lease
import host
import recipe_cli
import route
import skill6_playwright as runner
from test_community_event_meeting import inputs as event_inputs, ROOM
from test_community_portal import inputs as channel_inputs


def inputs():return {**event_inputs(),'integration_mode':'community_event_room'}
def probes():return {'lanes':{'playwright':{'available':True}}}
def job():return runner.validate_job(recipe_cli.compile_recipe('meetings.integrate',inputs()),Path('.'))


class EventHostTests(unittest.TestCase):
    def test_named_operation_compiles_only_concrete_exact_portal_payload(self):
        compiled=job()
        self.assertEqual(len(compiled['steps']),1)
        step=compiled['steps'][0]
        self.assertEqual(step['action'],'community_event_room')
        self.assertEqual(step['payload'],event_inputs())
        for key,value in (('location_id','foreign'),('location_name','foreign'),
                          ('start_url',compiled['start_url'].replace('/loc/','/foreign/'))):
            wrong=deepcopy(compiled);wrong['steps'][0]['payload'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):runner.validate_job(wrong,Path('.'))
        wrong=deepcopy(compiled);wrong['steps'][0]['portal_context']={'authenticated':True}
        with self.assertRaises(runner.Stop):runner.validate_job(wrong,Path('.'))

    def test_cli_check_and_missing_context_never_open_or_seed_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'run'
            source=Path(directory)/'input.json';source.write_text(json.dumps(inputs()))
            measured=Path(directory)/'probes.json';measured.write_text(json.dumps(probes()))
            output=io.StringIO()
            with redirect_stdout(output),patch.object(host,'execute') as execute,patch.object(host,'run_on_page') as app:
                code=host.main(['--operation','meetings.integrate','--inputs',str(source),
                    '--probes',str(measured),'--evidence-root',str(root),'--check'])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(output.getvalue())['status'],'PORTAL_CONTEXT_REQUIRED')
            self.assertFalse(root.exists());execute.assert_not_called();app.assert_not_called()
            for page,context in ((None,None),(Mock(),None),(None,object())):
                with patch.object(host,'execute') as execute,patch.object(host,'run_on_page') as app, \
                        patch.object(event,'run_event') as native:
                    result=host.run_recipe('meetings.integrate',inputs(),probes(),root,
                        input_dir='.',page=page,portal_context=context)
                self.assertEqual(result['status'],'PORTAL_CONTEXT_REQUIRED')
                execute.assert_not_called();app.assert_not_called();native.assert_not_called()

    def test_json_context_is_refused_without_touching_browser(self):
        page=Mock()
        with tempfile.TemporaryDirectory() as directory,patch.object(host,'execute') as execute, \
                patch.object(host,'run_on_page') as app:
            result=host.run_recipe('meetings.integrate',inputs(),probes(),directory,
                input_dir='.',page=page,portal_context={'authenticated':True})
        self.assertEqual(result['status'],'EVENT_PREFLIGHT_REFUSED')
        self.assertEqual(page.mock_calls,[]);execute.assert_not_called();app.assert_not_called()

    def test_success_wrapper_binds_pending_receipt_and_never_uses_app_runner(self):
        expected=event._receipt(event_inputs(),ROOM,changed=True)
        page,context=object(),object()
        with tempfile.TemporaryDirectory() as directory,patch.object(event,'run_event',return_value=expected) as native, \
                patch.object(host,'execute') as execute,patch.object(host,'run_on_page') as app:
            result=host.run_recipe('meetings.integrate',inputs(),probes(),directory,
                input_dir='.',page=page,portal_context=context)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['result'],expected)
        self.assertFalse(result['result']['functional_verified'])
        self.assertFalse(result['result']['notification_behavior_verified'])
        self.assertTrue(result['result']['room_creation_attempted'])
        self.assertIs(native.call_args.kwargs['portal_context'],context)
        execute.assert_not_called();app.assert_not_called()

    def test_forged_native_outcome_cannot_change_ids_hash_status_or_pending_flags(self):
        expected=event._receipt(event_inputs(),ROOM,changed=True)
        changes=({'event_id':'foreign'},{'group_id':'foreign'},{'location_id':'foreign'},
            {'configuration_sha256':'f'*64},{'status':'EDITOR_STEPS_COMPLETE'},
            {'room_id':'https://portal.invalid/meet/'+ROOM},{'room_id':'x'*24},
            {'functional_verified':True},{'notification_behavior_verified':True},
            {'room_creation_attempted':1},{'email_reminders_enabled':0},
            {'reused':True},{'private_copy':'NEVER_RETURN'},{'replayed':False})
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory, \
                    patch.object(event,'run_event',return_value={**expected,**change}):
                result=host.run_recipe('meetings.integrate',inputs(),probes(),directory,
                    input_dir='.',page=object(),portal_context=object())
                self.assertEqual(result['status'],'EVENT_PREFLIGHT_REFUSED')
                self.assertNotIn('NEVER_RETURN',str(result))

    def test_noop_outcome_cannot_report_a_different_room(self):
        data=inputs();data['allow_room_creation']=False
        data['expected']['form'].update(location_type='Live Room',location_url='https://portal.example.invalid/meet/'+ROOM)
        plan={key:value for key,value in data.items() if key!='integration_mode'}
        outcome=event._receipt(plan,'b'*24,changed=False)
        with tempfile.TemporaryDirectory() as directory,patch.object(event,'run_event',return_value=outcome):
            result=host.run_recipe('meetings.integrate',data,probes(),directory,
                input_dir='.',page=object(),portal_context=object())
        self.assertEqual(result['status'],'EVENT_PREFLIGHT_REFUSED')

    def test_api_capability_and_generic_browser_provider_never_bypass_event_context(self):
        measured={**probes(),'api_capabilities':{'meetings.integrate':{'supported':True,
            'provider':'public_api','scope_ok':True,'version':'v3','location_id':'loc','observed_at':time.time()}}}
        self.assertEqual(route.decide('meetings.integrate','loc',measured,inputs=inputs())['lane'],'playwright')
        provider=Mock()
        fallback={'lanes':{'openclaw_extension':{'available':True,'current':True}},
            'api_capabilities':measured['api_capabilities']}
        with tempfile.TemporaryDirectory() as directory:
            result=host.run_recipe('meetings.integrate',inputs(),fallback,directory,
                input_dir='.',page=object(),portal_context=object(),executors={
                    'public_api':provider,'openclaw_extension':provider})
        # A supplied Page uses the owned leaf on this measured transport; the
        # fake opaque context still fails before room creation or provider use.
        self.assertEqual(result['status'],'EVENT_PREFLIGHT_REFUSED')
        provider.assert_not_called()

    def test_event_refuses_fresh_app_auth_and_generic_options_before_browser(self):
        for change in ({'auth_activation':{}},{'options':{'capture_source':'foreign','steps':[]}}):
            data={**inputs(),**change}
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory, \
                    patch.object(host,'execute') as execute,patch.object(event,'run_event') as native:
                result=host.run_recipe('meetings.integrate',data,probes(),directory,
                    input_dir='.',page=object(),portal_context=object())
                self.assertEqual(result['status'],'STOP_INVALID_INPUT')
                execute.assert_not_called();native.assert_not_called()

    def test_uncertain_event_error_preserves_journal_and_never_switches_lane(self):
        prior=b'{"status":"ROOM_GENERATION_INTENT_RECORDED"}'
        with tempfile.TemporaryDirectory() as directory:
            physical=Path(directory)/'evidence';physical.mkdir()
            alias=Path(directory)/'evidence-alias';alias.symlink_to(physical,target_is_directory=True)
            # macOS /var is itself a symlink. Exercise the same alias boundary
            # on every platform and require the host's canonical journal path.
            path=alias/event._JOURNAL;path.write_bytes(prior)
            with patch.object(event,'run_event',side_effect=runner.Stop('uncertain private message')), \
                    patch.object(host,'recovery') as recovery:
                result=host.run_recipe('meetings.integrate',inputs(),probes(),alias,
                    input_dir='.',page=object(),portal_context=object())
            self.assertEqual(result['status'],'EVENT_RECONCILIATION_REQUIRED')
            self.assertEqual(result['state_file'],str(path.resolve()))
            self.assertEqual(path.read_bytes(),prior)
            self.assertFalse((alias/'handoff.json').exists())
            self.assertNotIn('private message',str(result));recovery.assert_not_called()


class EventJournalBoundaryTests(unittest.TestCase):
    def test_event_action_is_refused_by_direct_app_entries_before_browser_or_tenant_read(self):
        compiled=job()
        for entry in (runner.execute,runner.run_on_page,runner._run_on_page):
            with self.subTest(entry=entry.__name__),tempfile.TemporaryDirectory() as directory, \
                    patch.object(runner,'assert_tenant') as tenant, \
                    patch('browser_manager.PlaywrightSession') as browser,patch('ghl_auth.mint_and_bridge') as auth:
                with self.assertRaises(runner.Stop):
                    entry(compiled,directory) if entry is runner.execute else entry(Mock(),compiled,directory)
                tenant.assert_not_called();browser.assert_not_called();auth.assert_not_called()

    def test_foreign_event_journal_blocks_all_other_lease_kinds_and_app_execution(self):
        content=b'{prior-uncertain-room-generation'
        for kind in ('provider','provider_replay','course','calendar','community_details','community_access'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/event._JOURNAL;path.write_bytes(content)
                with self.assertRaises(runner.Stop):
                    with lease.evidence_lease(directory,'loc',kind=kind):self.fail('Foreign event journal admitted')
                with patch.object(runner,'assert_tenant') as tenant,self.assertRaises(runner.Stop):
                    runner.run_on_page(Mock(),{'location_id':'loc'},directory)
                self.assertEqual(path.read_bytes(),content);tenant.assert_not_called()

    def test_foreign_journals_block_event_before_context_or_native_room_generation(self):
        for name in lease.JOURNALS:
            if name==event._JOURNAL:continue
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/name;path.write_bytes(b'{foreign-uncertain')
                with patch.object(event,'_check_context') as context,patch.object(event,'_open_view') as native, \
                        self.assertRaises(runner.Stop):
                    event.run_event(Mock(),event_inputs(),directory,portal_context=object())
                context.assert_not_called();native.assert_not_called()
                self.assertEqual(path.read_bytes(),b'{foreign-uncertain')

    def test_event_lease_rejects_symlink_journal_and_provider_nesting(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/event._JOURNAL;path.symlink_to(Path(directory)/'missing')
            with self.assertRaises(runner.Stop):
                with lease.evidence_lease(directory,'loc',kind='community_event'):self.fail('Symlink admitted')
            self.assertTrue(path.is_symlink())
        with tempfile.TemporaryDirectory() as directory:
            with lease.evidence_lease(directory,'loc',kind='provider'):
                with self.assertRaises(runner.Stop):
                    with lease.evidence_lease(directory,'loc',kind='community_event'):self.fail('Nested event writer admitted')

    def test_legacy_manual_channel_writer_also_refuses_event_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/event._JOURNAL;path.write_bytes(b'{event-uncertain')
            with patch.object(portal,'_check_context') as context, self.assertRaises(runner.Stop):
                portal.run_channels(Mock(),channel_inputs(),directory,portal_context=object())
            context.assert_not_called();self.assertEqual(path.read_bytes(),b'{event-uncertain')


class AllPortalEntryBoundaryTests(unittest.TestCase):
    def test_branding_and_other_portal_jobs_never_seed_or_read_the_app_tenant(self):
        for action in ('community_branding','community_channels','community_details',
                       'community_access','community_courses','community_event_room'):
            compiled={'location_id':'loc','steps':[{'id':'portal','action':action,'payload':{}}]}
            for entry in (runner.execute,runner.run_on_page,runner._run_on_page):
                with self.subTest(action=action,entry=entry.__name__), tempfile.TemporaryDirectory() as directory, \
                        patch.object(runner,'assert_tenant') as tenant, \
                        patch('browser_manager.PlaywrightSession') as browser, \
                        patch('ghl_auth.mint_and_bridge') as auth:
                    with self.assertRaisesRegex(runner.Stop,'caller-owned'):
                        entry(compiled,directory) if entry is runner.execute else entry(Mock(),compiled,directory)
                    tenant.assert_not_called();browser.assert_not_called();auth.assert_not_called()
