"""Offline native component contract tests, never live/payment proof."""
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import subprocess
import unittest

from pages_checkout import (CheckoutRefused, configure_native_checkout,
    load_checkout_capture, validate_checkout_inputs, PlaywrightOrderDriver,
    check_split_prerequisites, SPLIT_MISSING_DOMAIN_NOTICE,
    resolve_code_target, inventory_code_targets)
import order_components as native


PRICE = {'native_product_id':'prod_fixture','native_price_id':'price_fixture',
    'amount_minor':4900,'currency':'USD','billing_type':'one_time',
    'recurring_interval':None,'trial_days':None}


def inputs():
    return {'location_id':'fixture','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/fixture/page-builder/page_fixture',
        'page_id':'page_fixture','step_id':'step_upsell','component_id':'checkout_fixture',
        'tab_id':'tab_fixture','frame_name':'funnel-builder','adapter_capture':'capture.json',
        'family':{'name':'captured_family','max_bumps':2,'allows_recurring_bumps':False},
        'main_price':deepcopy(PRICE),
        'checkout_contract':{'status':'PASS','location_id':'fixture','source':'offline fixture',
            'product_id':'prod_fixture','price_id':'price_fixture','prior_payment_verified':True,
            'source_step_id':'step_main','upsell_step_id':'step_upsell'}}


def capture():
    return {**deepcopy(native._FIXTURE_ADAPTER_CAPTURE), 'location_id':'fixture',
        'page_id':'page_fixture','capture_source':'Offline-only fixture, no live evidence'}


class Frame:
    name = 'funnel-builder'
    def __init__(self):
        self.calls = []
        self.catalog = [{'component_id':'checkout_fixture','kind':'order_form'}]
        self.state = {'bumps':[], 'field_states':{}}
        self.drift = False
        self.installs = 0
    def evaluate(self, script):
        if 'window.__ocOrderComponents=' in script:
            self.installs += 1
            return 'installed'
        req, _ = json.JSONDecoder().raw_decode(script.split('const r = await f(', 1)[1])
        self.calls.append(req)
        if req['op'] == 'list_components':
            result = self.catalog
        elif req['op'] == 'set_state':
            self.state.update(deepcopy(req['patch']))
            result = None
        else:
            result = deepcopy(self.state)
            if self.drift and 'main_price' in result:
                result['main_price']['native_price_id'] = 'drift'
        return json.dumps({'ok':True, 'result':result})


class Page:
    def __init__(self):
        self.url = inputs()['start_url']
        self.frames = [Frame()]
    def locator(self, selector):
        # Match the actual observed page-builder route's exact iframe. A stub
        # reporting every possible iframe present bypasses identity readiness.
        class Locator:
            def count(self):
                return int(selector == 'iframe[name="funnel-builder"]')
            def wait_for(self, *, state, timeout):
                if state != 'visible' or self.count() != 1:
                    raise TimeoutError('Fixture frame is not visible')
        return Locator()


class NativeCheckoutTests(unittest.TestCase):
    def run_fixture(self, data, page=None):
        page = page or Page()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'capture.json').write_text(json.dumps(capture()))
            return configure_native_checkout(page, data, input_dir=directory), page

    def test_real_executor_binds_fields_and_action_and_reads_back(self):
        data = inputs()
        data['field_states'] = {'email':{'required':True,'hidden':False}}
        data['purchase_action'] = {'kind':'accept','target_step_id':'step_next'}
        result, page = self.run_fixture(data)
        self.assertEqual(result['status'], 'NATIVE_CONFIGURATION_READBACK_VERIFIED')
        self.assertFalse(result['payment_verified'])
        self.assertEqual(len(result['operations']),3)
        self.assertEqual(page.frames[0].state['main_price'], PRICE)
        self.assertEqual(page.frames[0].state['action']['target_step_id'],'step_next')
        self.assertEqual(page.frames[0].installs,1)
        self.assertEqual(sum(call['op']=='get_state' for call in page.frames[0].calls),3)

    def test_contract_failure_happens_before_browser_access(self):
        data = inputs()
        data['checkout_contract']['price_id'] = 'wrong'
        with self.assertRaises(CheckoutRefused):
            configure_native_checkout(object(),data)

    def test_wrong_editor_page_and_payment_requests_fail_before_browser(self):
        for key in ('page_id', 'publish', 'charge', 'execute_payment'):
            data = inputs()
            data[key] = 'different_page' if key == 'page_id' else True
            with self.subTest(key=key), self.assertRaises(CheckoutRefused):
                configure_native_checkout(object(), data)

    def test_prior_payment_required_for_upsell(self):
        data = inputs()
        data['purchase_action'] = {'kind':'accept','target_step_id':'step_next'}
        data['checkout_contract']['prior_payment_verified'] = False
        with self.assertRaises(CheckoutRefused):
            validate_checkout_inputs(data)

    def test_duplicate_component_refused_before_write(self):
        page = Page()
        page.frames[0].catalog *= 2
        with self.assertRaises(native.AmbiguousTarget):
            self.run_fixture(inputs(),page)
        self.assertFalse(any(c['op']=='set_state' for c in page.frames[0].calls))

    def test_readback_drift_is_never_claimed_verified(self):
        page = Page()
        page.frames[0].drift = True
        with self.assertRaises(native.ReadbackMismatch):
            self.run_fixture(inputs(),page)

    def test_capture_target_and_unsafe_route_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory,'capture.json')
            for mutate in ('location','protocol_relative','synthetic'):
                data = capture()
                if mutate == 'location': data['location_id']='another'
                elif mutate == 'protocol_relative': data['autosave']['path']='//host.invalid/write'
                else: data['synthetic']=True
                path.write_text(json.dumps(data))
                with self.subTest(mutate=mutate), self.assertRaises(native.OrderComponentError):
                    load_checkout_capture(path,location_id='fixture',page_id='page_fixture')

    def test_bump_must_be_unselected_and_receipted(self):
        data = inputs()
        bump = {'offer_id':'offer_bump','headline':'Extra','benefit_explanation':'Added benefit',
                'price':{**PRICE,'native_product_id':'prod_bump','native_price_id':'price_bump'}}
        data['bumps']=[bump]
        with self.assertRaises(CheckoutRefused): validate_checkout_inputs(data)
        data['checkout_contract']['verified_bump_prices']=[bump['price']]
        result,page=self.run_fixture(data)
        self.assertFalse(page.frames[0].state['bumps'][0]['selected'])
        bump['selected']=True
        with self.assertRaises(CheckoutRefused): validate_checkout_inputs(data)

    def test_bump_replay_reuses_exact_existing_attachment(self):
        data = inputs()
        bump = {'offer_id':'offer_bump','headline':'Extra','benefit_explanation':'Benefit',
            'price':{**PRICE,'native_product_id':'prod_bump','native_price_id':'price_bump'}}
        data['bumps']=[bump]
        data['checkout_contract']['verified_bump_prices']=[bump['price']]
        _,page=self.run_fixture(data)
        before=len([c for c in page.frames[0].calls if c['op']=='set_state' and 'bumps' in c['patch']])
        self.run_fixture(data,page)
        after=len([c for c in page.frames[0].calls if c['op']=='set_state' and 'bumps' in c['patch']])
        self.assertEqual(before,after)

    def test_generated_adapter_executes_actual_javascript_and_autosaves_draft(self):
        bridge = native.ManagedEditorBridge(capture(), location_id='fixture', page_id='page_fixture')
        script = """
const assert = require('node:assert/strict');
global.window = {__VT:'offline-token'};
let blob = {elements:[{id:'checkout_fixture',type:'order_form',orderBumps:[],fieldStates:{}}]};
const requests = [];
global.fetch = async (url, options={}) => {
  requests.push({url, method:options.method || 'GET'});
  if (url.startsWith('/funnels/page/')) return {ok:true,json:async()=>({pageDataDownloadUrl:'https://fixture.invalid/blob'})};
  if (url === 'https://fixture.invalid/blob') return {ok:true,json:async()=>JSON.parse(JSON.stringify(blob))};
  if (url === '/funnels/builder/autosave/page_fixture') {
    const data = JSON.parse(options.body);
    assert.equal(data.pageType,'draft');
    assert.equal(data.manualSave,true);
    blob = data.pageData;
    return {ok:true,status:200};
  }
  throw new Error('Unexpected route '+url);
};
""" + bridge.install_js() + """
(async()=>{
  const list = await window.__ocOrderComponents({op:'list_components'});
  assert.equal(list.result[0].component_id,'checkout_fixture');
  const price = PRICE;
  assert.equal((await window.__ocOrderComponents({op:'set_state',component_id:'checkout_fixture',patch:{main_price:price}})).ok,true);
  const read = await window.__ocOrderComponents({op:'get_state',component_id:'checkout_fixture'});
  assert.deepEqual(read.result.main_price,price);
  assert.deepEqual(blob.elements[0].mainPrice,price);
  assert.equal(requests.filter(r=>r.method==='POST').length,1);
  console.log(JSON.stringify({verified:true,requests}));
})().catch(error=>{console.error(error);process.exit(1)});
""".replace('PRICE', json.dumps(PRICE))
        result = subprocess.run(['node','-e',script], capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['verified'])

    def test_changed_page_and_frame_scope_stop_transport(self):
        page = Page()
        bridge=native.ManagedEditorBridge(capture(),location_id='fixture',page_id='page_fixture')
        scope=native.FrameScope('tab_fixture','funnel-builder')
        driver=PlaywrightOrderDriver(page,scope=scope,frame_name='funnel-builder',bridge=bridge,expected_url=page.url)
        with self.assertRaises(CheckoutRefused):
            driver.list_components(native.FrameScope('other','funnel-builder'))
        page.url='https://app.convertandflow.com/v2/location/another/editor/page_fixture'
        with self.assertRaises(CheckoutRefused): driver.list_components(scope)
        self.assertEqual(page.frames[0].calls,[])


class ReadOnlyLocator:
    def __init__(self, count=1, visible=True, enabled=True):
        self._count, self._visible, self._enabled = count, visible, enabled
    def count(self): return self._count
    def nth(self, index): return self
    def is_visible(self): return self._visible
    def is_enabled(self): return self._enabled
    def get_by_role(self, *args, **kwargs): return self
    def wait_for(self, **kwargs): return None
    def click(self, *args, **kwargs): raise AssertionError('Preflight must never click')


class SplitPage:
    def __init__(self, missing_domain=True, create_count=1):
        self.url = split_inputs()['start_url']
        self.missing_domain, self.create_count = missing_domain, create_count
        self.create_lookups = 0
    def locator(self, selector): return ReadOnlyLocator(count=0)
    def get_by_text(self, text, exact=True):
        return ReadOnlyLocator(count=int(self.missing_domain) if text == SPLIT_MISSING_DOMAIN_NOTICE else 1)
    def get_by_role(self, role, **kwargs):
        if kwargs.get('name') == 'Create variation':
            self.create_lookups += 1
            return ReadOnlyLocator(count=self.create_count)
        return ReadOnlyLocator()


def split_inputs():
    return {'location_id':'fixture','location_name':'Fixture','funnel_id':'funnel_fixture',
        'step_id':'step_fixture','funnel_name':'Fixture Funnel','page_name':'Fixture Page',
        'start_url':'https://app.convertandflow.com/v2/location/fixture/funnels-websites/funnels/funnel_fixture/steps/step_fixture/overview'}


class SplitPrerequisiteTests(unittest.TestCase):
    def test_missing_domain_returns_precise_dependency_without_even_targeting_create(self):
        page = SplitPage()
        result = check_split_prerequisites(page, split_inputs())
        self.assertEqual(result['status'], 'DEPENDENCY_DOMAIN_MISSING')
        self.assertEqual(result['observed_notice'], SPLIT_MISSING_DOMAIN_NOTICE)
        self.assertFalse(result['mutation_attempted'])
        self.assertFalse(result['variant_created'])
        self.assertEqual(page.create_lookups, 0)

    def test_no_missing_notice_never_bypasses_canonical_native_capture(self):
        result = check_split_prerequisites(SplitPage(missing_domain=False), split_inputs())
        self.assertEqual(result['status'], 'DEPENDENCY_SPLIT_CAPTURE_REQUIRED')
        self.assertEqual(result['native_capability_state'], 'PENDING_LIVE_SELECTOR_CAPTURE')
        self.assertFalse(result['mutation_attempted'])

    def test_wrong_step_url_refused_before_dom_access(self):
        page = SplitPage()
        page.url = page.url.replace('/step_fixture/', '/another_step/')
        with self.assertRaises(CheckoutRefused):
            check_split_prerequisites(page, split_inputs())
        self.assertEqual(page.create_lookups, 0)

    def test_changed_split_control_is_reconciliation_dependency(self):
        result = check_split_prerequisites(SplitPage(False, create_count=0), split_inputs())
        self.assertEqual(result['status'], 'DEPENDENCY_SPLIT_UI_CHANGED')
        self.assertFalse(result['mutation_attempted'])


class CodeLocator:
    def __init__(self, frame, rows):
        self.frame, self.rows = frame, rows
    def count(self): return len(self.rows)
    def evaluate(self, _): return self.rows[0]['section_id']
    def evaluate_all(self, _):
        return [{key:row[key] for key in ('element_id','section_id')} for row in self.rows]
    def click(self):
        self.frame.clicks.append(self.rows[0]['element_id'])
        self.frame.selected = self.rows[0]


class PropertyControl:
    def __init__(self, frame, role): self.frame,self.role=frame,role
    def count(self): return int(self.frame.panel and self.frame.selected is not None)
    def wait_for(self, **_):
        if not self.is_visible(): raise AssertionError('panel missing')
    def is_visible(self): return bool(self.frame.panel and self.frame.selected)
    def input_value(self): return self.frame.selected['element_name']
    def fill(self, *_): raise AssertionError('Resolution must not modify inputs')
    def click(self, *_): raise AssertionError('Resolution must not open code editor')


class CodeFrame:
    def __init__(self):
        self.rows=[{'element_id':'custom-code-fixture1','section_id':'section-fixture1','element_name':'Custom Code'},
                   {'element_id':'custom-code-fixture2','section_id':'section-fixture2','element_name':'Approved Checkout Wrapper'}]
        self.selected=None
        self.clicks=[]
        self.panel=True
    def locator(self, selector):
        if selector=='.c-custom-code': return CodeLocator(self,self.rows)
        target=json.loads(selector.split('[id=',1)[1][:-1])
        return CodeLocator(self,[row for row in self.rows if row['element_id']==target])
    def get_by_role(self, role, **kwargs):
        if kwargs.get('name') not in ('Element name','Open Code Editor'):
            raise AssertionError('Uncaptured property control')
        return PropertyControl(self,role)


class CodeTargetTests(unittest.TestCase):
    def test_exact_native_target_selects_correct_section_among_multiple(self):
        frame=CodeFrame()
        result=resolve_code_target(frame,'custom-code-fixture2','Approved Checkout Wrapper','section-fixture2')
        self.assertEqual(result['section_id'],'section-fixture2')
        self.assertEqual(result['element_name'],'Approved Checkout Wrapper')
        self.assertEqual(frame.clicks,['custom-code-fixture2'])

    def test_section_mismatch_and_duplicate_id_refuse_before_selection(self):
        frame=CodeFrame()
        with self.assertRaises(CheckoutRefused):
            resolve_code_target(frame,'custom-code-fixture1','Custom Code','section-fixture2')
        self.assertEqual(frame.clicks,[])
        frame.rows.append(deepcopy(frame.rows[0]))
        with self.assertRaises(CheckoutRefused):
            resolve_code_target(frame,'custom-code-fixture1','Custom Code')
        self.assertEqual(frame.clicks,[])

    def test_wrong_property_name_never_opens_or_changes_code(self):
        frame=CodeFrame()
        with self.assertRaises(CheckoutRefused):
            resolve_code_target(frame,'custom-code-fixture1','Another Name')
        self.assertEqual(frame.rows[0]['element_name'],'Custom Code')

    def test_missing_panel_stops_instead_of_clicking_guessed_settings(self):
        frame=CodeFrame();frame.panel=False
        with self.assertRaises(CheckoutRefused):
            resolve_code_target(frame,'custom-code-fixture1','Custom Code')

    def test_unsafe_native_id_refused_before_browser_access(self):
        with self.assertRaises(CheckoutRefused):
            resolve_code_target(object(),'custom-code-fixture1] > *','Custom Code')

    def test_inventory_reads_visible_property_names_for_each_native_id(self):
        frame=CodeFrame()
        inventory=inventory_code_targets(frame)
        self.assertEqual(inventory[1]['element_name'],'Approved Checkout Wrapper')
        self.assertEqual(frame.clicks,['custom-code-fixture1','custom-code-fixture2'])
        self.assertTrue(all('locator' not in row for row in inventory))

    def test_id_only_inventory_and_duplicate_detection_never_select(self):
        frame=CodeFrame()
        self.assertTrue(all(row['element_name'] is None for row in inventory_code_targets(frame,include_names=False)))
        self.assertEqual(frame.clicks,[])
        frame.rows.append(deepcopy(frame.rows[0]))
        with self.assertRaises(CheckoutRefused): inventory_code_targets(frame)
        self.assertEqual(frame.clicks,[])


if __name__ == '__main__': unittest.main()
