"""Offline contract tests. No network, credentials or browser process."""
import copy
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import host
import recipe_cli
import route
import skill6_playwright as runner


def job(step=None):
    return {'location_id':'LOC123','location_name':'Test Client',
            'start_url':'https://app.convertandflow.com/v2/location/LOC123/dashboard',
            'steps':[step or {'id':'nav','action':'navigate','area':'Forms'}]}


class ValidationTests(unittest.TestCase):
    def validate(self, value):
        return runner.validate_job(value, Path('.'))

    def test_rejects_malformed_inputs_before_browser(self):
        cases=[[], {'start_url':8}, {'steps':['click']},
               {'steps':[{'id':'x','action':[]}]},
               {'steps':[{'id':'x','action':'page','surface':'funnel','name':'Test','path':42}]},
               {'steps':[{'id':'x','action':'form_css','radius':True}]},
               {'steps':[{'id':'x','action':'form','name':'Test','required':{'Email':'false'}}]},
               {'steps':[{'id':'x','action':'options','capture_source':'live', 'steps':['click']}]},
               {'steps':[{'id':'x','action':'options','capture_source':'live', 'steps':[{'action':[],'target':{}}]}]},
               {'steps':[{'id':'x','action':'options','capture_source':'live', 'steps':[{'action':'check','target':{'by':'role','role':'checkbox','value':'Required'},'value':'false'}]}]},
               {'steps':[{'id':'x','action':'options','capture_source':'live', 'steps':[{'action':'expect_count','target':{'by':'unsupported','value':'x'},'value':1}]}]}]
        for changes in cases:
            value={**job(),**changes} if isinstance(changes,dict) else changes
            with self.subTest(value=value), self.assertRaises(runner.Stop):
                self.validate(value)

    def test_location_and_url_binding(self):
        for url in ('https://app.convertandflow.com/v2/location/OTHER/dashboard','https://app.convertandflow.com/v2/location/LOC123/dashboard?token=secret','http://app.convertandflow.com/v2/location/LOC123/dashboard'):
            with self.subTest(url=url), self.assertRaises(runner.Stop):
                self.validate({**job(),'start_url':url})

    def test_options_need_readback_and_index_count(self):
        action={'action':'click','target':{'by':'role','role':'button','value':'Save'}}
        with self.assertRaises(runner.Stop):
            self.validate(job({'id':'opts','action':'options','capture_source':'live','steps':[action]}))
        action={'action':'expect_count','target':{'by':'text','value':'Saved','index':0},'value':1}
        with self.assertRaises(runner.Stop):
            self.validate(job({'id':'opts','action':'options','capture_source':'live','steps':[action]}))

    def test_room_requires_explicit_security_choices(self):
        step={'id':'room','action':'meeting','name':'Test','slug':'test-room'}
        with self.assertRaises(runner.Stop):
            self.validate(job(step))
        step.update(waiting_room=True,guest_users=False,open_room=False)
        self.validate(job(step))

    def test_check_execute_are_exclusive(self):
        p=subprocess.run([sys.executable,str(Path(runner.__file__)),'--job','unused','--check','--execute'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2)
        self.assertIn('not allowed with argument',p.stderr)

    def test_embed_requires_bound_receipt(self):
        data={**job(),'file':'embed.html','marker':'Hello','seo':{}}
        with self.assertRaises(runner.Stop):
            recipe_cli.compile_recipe('pages.install_embed',data)

    def test_embed_receipt_binds_payload_and_sources(self):
        with tempfile.TemporaryDirectory() as d:
            html='<iframe src="https://actual.example/app"></iframe>'
            Path(d,'embed.html').write_text(html)
            receipt={'status':'PASS','source':'gate-receipt.json','location_id':'LOC123','html_sha256':runner.sha(html),'embed_urls':['https://other.example/app']}
            j=job({'id':'embed','action':'html','file':'embed.html','marker':'actual.example','embed_receipt':receipt})
            with self.assertRaises(runner.Stop):
                runner.validate_job(j,Path(d))
            receipt['embed_urls']=['https://actual.example/app']
            runner.validate_job(j,Path(d))
            Path(d,'embed.html').write_text(html+'changed')
            with self.assertRaises(runner.Stop):
                runner.validate_job(j,Path(d))

    def test_native_upsell_requires_payment_contract(self):
        data={**job(),'options':{'capture_source':'fixture','steps':[]}}
        with self.assertRaises(runner.Stop):
            recipe_cli.compile_recipe('checkout.one_click_upsell',data)


class RoutingTests(unittest.TestCase):
    def probes(self):
        return {'lanes':{'playwright':{'available':True},'openclaw_extension':{'available':True,'current':True},'agent_browser':{'available':True}}}

    def test_api_first_and_scope_refusal(self):
        p=self.probes()
        self.assertEqual(route.decide('courses.create','LOC123',p)['lane'],'PROBE_API')
        p['api_capabilities']={'courses.create':{'location_id':'LOC123','observed_at':time.time(),'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}
        self.assertEqual(route.decide('courses.create','LOC123',p)['lane'],'public_api')
        p['api_capabilities']['courses.create']['http_status']=403
        self.assertEqual(route.decide('courses.create','LOC123',p)['lane'],'STOP_AUTH')

    def test_receipt_must_be_fresh_and_tenant_bound(self):
        p=self.probes()
        p['api_capabilities']={'courses.create':{'location_id':'OTHER','observed_at':time.time(),'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}
        self.assertEqual(route.decide('courses.create','LOC123',p)['lane'],'PROBE_API')
        p['api_capabilities']['courses.create'].update(location_id='LOC123',observed_at=time.time()-7200)
        self.assertEqual(route.decide('courses.create','LOC123',p)['lane'],'PROBE_API')

    def test_profile_and_recovery_order(self):
        p=self.probes()
        self.assertEqual(route.decide('forms.create','LOC123',p)['lane'],'playwright')
        self.assertEqual(route.decide('funnels.split_variant','LOC123',p)['lane'],'openclaw_extension')
        p['recorded_profiles']=['funnels.split_variant']
        self.assertEqual(route.decide('funnels.split_variant','LOC123',p)['lane'],'playwright')
        p['lanes']['openclaw_extension']['current']=False
        self.assertEqual(route.recovery('forms.create','LOC123',p)['lane'],'agent_browser')

    def test_existing_probe_adapter_does_not_assume_extension(self):
        p=route.from_capability_probe({'operationCapabilities':{'transports':{'browser':{'routes':['playwright_direct','agent_browser']}}}})
        self.assertFalse(p['lanes']['openclaw_extension']['available'])
        self.assertEqual(route.decide('forms.create','LOC123',p)['lane'],'playwright')

    def test_api_handoff_does_not_compile_browser_course(self):
        p=self.probes()
        with tempfile.TemporaryDirectory() as d:
            r=host.run_recipe('courses.create',job(),p,d,input_dir='.')
        self.assertEqual(r['route']['lane'],'PROBE_API')
        self.assertFalse(r['browser_used'])

    def test_invalid_quiz_refuses_before_browser_work_or_recovery_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            r=host.run_recipe('quizzes.create',{**job(),'name':'Fixture'},self.probes(),d,input_dir='.')
            self.assertEqual(r['status'],'STOP_INVALID_INPUT')
            self.assertEqual(r['route']['lane'],'openclaw_extension')
            self.assertFalse(Path(d,'handoff.json').exists())


class RecoveryTests(unittest.TestCase):
    def test_failure_preserves_intent_and_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner,'assert_tenant'), patch.object(runner,'navigate',side_effect=RuntimeError('secret-value')) as click:
            with self.assertRaises(runner.Stop):
                runner.run_on_page(object(),job(),d)
            raw=(Path(d)/'state.json').read_text()
            state=json.loads(raw)
            self.assertEqual(state['status'],'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
            self.assertNotIn('secret-value',raw)
            with self.assertRaises(runner.Stop):
                runner.run_on_page(object(),job(),d)
            self.assertEqual(click.call_count,1)

    def test_completed_run_still_checks_tenant_before_replay(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner,'assert_tenant') as guard, patch.object(runner,'navigate') as nav:
            first=runner.run_on_page(object(),job(),d)
            second=runner.run_on_page(object(),job(),d)
            self.assertEqual(first['status'],'EDITOR_STEPS_COMPLETE')
            self.assertEqual(second['status'],'ALREADY_EXECUTED')
            self.assertEqual(nav.call_count,1)
            guard.side_effect=runner.Stop('Wrong tenant')
            with self.assertRaises(runner.Stop):
                runner.run_on_page(object(),job(),d)

    def test_verification_pending_is_not_success_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'job.json';p.write_text(json.dumps(job()))
            with patch.object(sys,'argv',['runner','--job',str(p),'--execute','--evidence-root',d]), patch.object(runner,'execute',return_value={'status':'NEEDS_VERIFICATION','results':[]}):
                self.assertEqual(runner.main(),3)


class OriginTests(unittest.TestCase):
    def test_real_bridge_origin_guard_refuses_prefix_lookalike(self):
        # Compile the real isolated guard, avoiding unrelated secret resolvers.
        auth=Path(__file__).resolve().parent.parent/'ghl_auth.py'
        if not auth.exists():
            auth=Path('06-ghl-install-pages/tools/ghl_auth.py')
        tree=ast.parse(auth.read_text())
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_page_url','_require_ghl_origin')]
        env={'GHL_APP_ORIGIN':'https://app.gohighlevel.com','_OPAQUE_ORIGIN_PREFIXES':('about:','data:','blob:',''),'AuthBridgeError':runner.Stop}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(auth),'exec'),env)
        class Page:
            url='https://app.convertandflow.com/v2/location/LOC123/dashboard'
        env['_require_ghl_origin'](Page(),'https://app.convertandflow.com')
        for url in ('https://app.convertandflow.com.evil.test/x','https://app.gohighlevel.com@evil.test/x','about:blank'):
            Page.url=url
            with self.subTest(url=url), self.assertRaises(runner.Stop):
                env['_require_ghl_origin'](Page(),'https://app.convertandflow.com')


if __name__=='__main__':
    unittest.main()
