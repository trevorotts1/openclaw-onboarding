"""Native checkout UI tests based on captured roles, never live payment proof."""
import re
import json
import tempfile
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

import checkout_ui as ui
from pages_checkout import CheckoutRefused
import skill6_playwright as core
import host
from recipe_cli import compile_recipe


def inputs():
    return {'element_id':'order-form-fixture','expected_name':'Order Form',
        'section_id':'section-fixture','mode':'Two-step',
        'products':{'show_quantity':True,'coupon_codes':False},
        'location_id':'fixture','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/fixture/page-builder/page-fixture'}


class Locator:
    def __init__(self, frame, kind, name=None):
        self.frame,self.kind,self.name=frame,kind,name
    def count(self):
        if self.kind=='dialog':return int(self.frame.dialog)
        if self.kind=='order':return self.frame.order_count
        if self.kind=='textbox':return 1
        if isinstance(self.name,re.Pattern):return 1
        if self.kind=='switch':return int(self.name in (*ui.PRODUCT_SWITCHES.values(),*ui.CHECKOUT_SWITCHES.values()))
        if isinstance(self.name,str) and self.name.startswith('Steps '):return int(self.name=='Steps '+self.frame.mode)
        return 1
    def wait_for(self, **kwargs):
        if kwargs.get('state')=='hidden':
            if self.frame.dialog:raise AssertionError('dialog still visible')
        elif not self.count():raise AssertionError('control absent')
    def filter(self, **kwargs):return self
    def get_by_test_id(self, value):return ContactRow(self.frame,value.replace('field-row-',''))
    def get_by_role(self, role, **kwargs):
        if self.kind=='group' and self.name in ('Appearance','Labels'):
            return ThemeButton(self.frame,self.name,kwargs.get('name'))
        return Locator(self.frame,role,kwargs.get('name'))
    def get_by_text(self, text, **kwargs):return Locator(self.frame,'accordion',text)
    def locator(self, selector):
        if selector=='.of-terms-content .tiptap.ProseMirror':return TermsCollection(self.frame)
        raise AssertionError('Uncaptured dialog locator '+selector)
    def evaluate(self, _):return self.frame.section
    def input_value(self):return self.frame.name if self.name=='Element name' else self.frame.content.get(self.name,'Original '+str(self.name))
    def fill(self,value):
        if self.kind!='textbox' or self.name=='Element name':raise AssertionError('Unexpected text mutation')
        self.frame.content[self.name]=value
    def is_visible(self):
        if self.kind=='textbox' and self.name!='Element name':
            groups=[group for group,label in ui.CONTENT_FIELDS.values() if label==self.name]
            return bool(groups and groups[0] in self.frame.expanded)
        return bool(self.count())
    def get_attribute(self,key):
        if key=='aria-checked':return str(self.frame.switches.get(self.name,False)).lower()
        return None
    def click(self):
        self.frame.clicks.append((self.kind,str(self.name)))
        if self.name=='Customize order form':self.frame.dialog=True
        elif self.kind=='switch':self.frame.switches[self.name]=not self.frame.switches.get(self.name,False)
        elif self.name in ui.MODES:self.frame.mode=self.name
        elif self.name=='Alternative text for image not provided':self.frame.dialog=False
        elif self.kind=='accordion':self.frame.expanded.add(self.name)


class Frame:
    def __init__(self):
        self.section='section-fixture';self.name='Order Form';self.order_count=1
        self.mode='One-step';self.switches={};self.dialog=False;self.clicks=[]
        self.content={};self.expanded={'Headlines'};self.theme={'Appearance':'Line','Labels':'Above'}
        self.terms_order=['Terms & conditions','Terms & conditions (step 2)']
        self.terms={label:{'text':'I agree to the terms and conditions','links':1} for label in self.terms_order}
        self.fields={key:{'required':False,'visible':True,'label':label} for key,label in ui.CONTACT_FIELDS.items()}
    def locator(self, selector):return Locator(self,'order')
    def get_by_role(self,role,**kwargs):return Locator(self,role,kwargs.get('name'))


class ContactRow(Locator):
    def __init__(self, frame, key):super().__init__(frame,'row',key);self.key=key
    def count(self):return int(self.key in self.frame.fields)
    def locator(self, selector):return FieldLabel(self.frame,self.key)
    def get_by_role(self, role, **kwargs):
        title=kwargs.get('name')
        state={'Toggle required':'required','Toggle visibility':'visible'}[title]
        return FieldButton(self.frame,self.key,state)


class FieldLabel:
    def __init__(self,frame,key):self.frame,self.key=frame,key
    def count(self):return 1
    def get_attribute(self,key):return self.frame.fields[self.key]['label'] if key=='title' else None


class FieldButton:
    def __init__(self,frame,key,state):self.frame,self.key,self.state=frame,key,state
    def count(self):return int(self.key not in ui.MANDATORY_CONTACT_FIELDS)
    def get_attribute(self,key):return str(self.frame.fields[self.key][self.state]).lower() if key=='aria-pressed' else None
    def click(self):
        self.frame.clicks.append(('field',self.key+'.'+self.state))
        self.frame.fields[self.key][self.state]=not self.frame.fields[self.key][self.state]


class ThemeButton:
    def __init__(self,frame,group,value):self.frame,self.group,self.value=frame,group,value
    def count(self):return 1
    def wait_for(self,**kwargs):return None
    def get_attribute(self,key):return str(self.frame.theme[self.group]==self.value).lower() if key=='aria-pressed' else None
    def click(self):
        self.frame.clicks.append(('theme',self.group+'.'+self.value))
        self.frame.theme[self.group]=self.value


class FixedCount:
    def __init__(self,n):self.n=n
    def count(self):return self.n


class TermsCollection:
    def __init__(self,frame):self.frame=frame
    def labels(self):return [label for label in self.frame.terms_order if self.frame.switches.get(label,False)]
    def count(self):return len(self.labels())
    def nth(self,index):return TermsEditor(self.frame,self.labels()[index])


class TermsEditor:
    def __init__(self,frame,label):self.frame,self.label=frame,label
    def locator(self,selector):
        if selector=='xpath=../../..':return TermsRow(self.frame,self.label)
        if selector=='a':return FixedCount(self.frame.terms[self.label]['links'])
        raise AssertionError('Uncaptured Terms editor locator')
    def wait_for(self,**kwargs):return None
    def inner_text(self):return self.frame.terms[self.label]['text']
    def fill(self,value):
        self.frame.terms[self.label]={'text':value,'links':0}
        self.frame.clicks.append(('terms_text',self.label))


class TermsRow:
    def __init__(self,frame,label):self.frame,self.label=frame,label
    def inner_text(self):return self.label+' Shows a checkbox with your terms.'
    def get_by_role(self,role,**kwargs):
        if kwargs.get('name')!=self.label:return FixedCount(0)
        return Locator(self.frame,'switch',self.label)


class CheckoutUITests(unittest.TestCase):
    def test_mode_and_named_switches_apply_without_payment_or_product_binding(self):
        frame=Frame()
        result=ui.apply_checkout_ui(frame,inputs())
        self.assertEqual(frame.mode,'Two-step')
        self.assertTrue(frame.switches['Show quantity'])
        self.assertFalse(frame.switches.get('Enable coupon codes',False))
        self.assertEqual(result['independent_readback'],'REQUIRED')
        self.assertFalse(result['payment_verified'])
        self.assertFalse(any(name in ('Add Product','Save','Purchase','Publish') for _,name in frame.clicks))

    def test_switches_are_set_not_blind_toggled(self):
        frame=Frame();frame.switches={'Show quantity':True,'Enable coupon codes':False}
        ui.apply_checkout_ui(frame,inputs())
        self.assertEqual([kind for kind,_ in frame.clicks].count('switch'),0)

    def test_invalid_settings_are_refused_before_frame_access(self):
        for change in ({'products':{'show_quantity':'false'}},{'mode':'Uncaptured'},
                       {'product_id':'prod_unknown'},{'publish':True}):
            data={**inputs(),**change}
            with self.subTest(change=change),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),data)

    def test_wrong_section_name_or_duplicate_form_stops_before_customize(self):
        for problem in ('section','name','duplicate'):
            frame=Frame()
            if problem=='section':frame.section='another-section'
            elif problem=='name':frame.name='Different Order Form'
            else:frame.order_count=2
            with self.subTest(problem=problem),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(frame,inputs())
            self.assertNotIn(('button','Customize order form'),frame.clicks)

    def test_independent_readback_rejects_mode_or_switch_drift(self):
        for drift in ('mode','switch'):
            frame=Frame();ui.apply_checkout_ui(frame,inputs())
            if drift=='mode':frame.mode='One-step'
            else:frame.switches['Show quantity']=False
            with self.subTest(drift=drift),self.assertRaises(CheckoutRefused):
                ui.verify_checkout_ui(frame,inputs())

    def test_native_contact_required_visible_set_and_readback(self):
        frame=Frame()
        data={**inputs(),'contact_fields':{'phone':{'required':True,'visible':True},
                                          'company':{'required':False,'visible':False}}}
        ui.apply_checkout_ui(frame,data)
        self.assertTrue(frame.fields['phone']['required'])
        self.assertFalse(frame.fields['company']['visible'])
        result=ui.verify_checkout_ui(frame,data)
        self.assertEqual(result['contact_fields'],data['contact_fields'])
        self.assertFalse(result['payment_verified'])

    def test_contact_fields_inventory_all_labels_before_field_writes(self):
        frame=Frame();frame.fields['company']['label']='Uncaptured Label'
        data={**inputs(),'mode':None,'products':{},'contact_fields':{
            'phone':{'required':True},'company':{'required':False}}}
        with self.assertRaises(CheckoutRefused):ui.apply_checkout_ui(frame,data)
        self.assertEqual([kind for kind,_ in frame.clicks].count('field'),0)

    def test_mandatory_contact_false_and_unknown_fields_refused_upfront(self):
        for fields in ({'fullName':{'required':False}},{'email':{'visible':False}},
                       {'uncaptured':{'visible':True}},{'phone':{'required':'false'}}):
            with self.subTest(fields=fields),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),{**inputs(),'contact_fields':fields})

    def test_mandatory_true_is_verified_without_unavailable_toggles(self):
        frame=Frame();data={**inputs(),'contact_fields':{'fullName':{'required':True,'visible':True},
                                                       'email':{'required':True}}}
        ui.apply_checkout_ui(frame,data)
        ui.verify_checkout_ui(frame,data)
        self.assertEqual([kind for kind,_ in frame.clicks].count('field'),0)

    def test_contact_readback_drift_is_refused(self):
        frame=Frame();data={**inputs(),'contact_fields':{'phone':{'required':True}}}
        ui.apply_checkout_ui(frame,data);frame.fields['phone']['required']=False
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)

    def test_checkout_options_set_and_reopen_readback(self):
        frame=Frame();data={**inputs(),'checkout_options':{
            'sticky_contact':True,'new_contact_every_purchase':False,
            'validate_disposable_email':True,'postal_code_on_payment_form':True,
            'terms_and_conditions':False,'terms_and_conditions_step_2':False}}
        ui.apply_checkout_ui(frame,data)
        self.assertTrue(frame.switches['Sticky contact'])
        self.assertTrue(frame.switches['Validate disposable email'])
        self.assertEqual(ui.verify_checkout_ui(frame,data)['checkout_options'],data['checkout_options'])
        frame.switches['Sticky contact']=False
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)

    def test_legal_terms_enable_and_uncaptured_options_refused_before_browser(self):
        for options in ({'terms_and_conditions':True},{'terms_and_conditions_step_2':True},
                        {'uncaptured_option':False},{'sticky_contact':'true'}):
            with self.subTest(options=options),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),{**inputs(),'checkout_options':options})

    def test_all_captured_content_groups_preserve_supplied_strings(self):
        frame=Frame();content={key:'Approved '+key+' {{contact.first_name}}' for key in ui.CONTENT_FIELDS}
        self.assertEqual(len(content),37)
        data={**inputs(),'mode':None,'products':{},'content':content}
        ui.apply_checkout_ui(frame,data)
        self.assertEqual(frame.content['Order button text'],content['order_button_text'])
        self.assertEqual(frame.content['Full name validation error'],content['full_name_validation_error'])
        groups=[name for kind,name in frame.clicks if kind=='accordion']
        self.assertEqual(len(groups),5)
        self.assertEqual(set(groups),{'Products & summary','Validation messages','Coupon','Payment & CTA','Two-step chrome'})
        frame.expanded={'Headlines'}
        self.assertEqual(ui.verify_checkout_ui(frame,data)['content'],content)
        frame.content['Order button text']='Drift'
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)

    def test_empty_nonstring_or_unknown_content_refused_before_browser(self):
        for content in ({'order_button_text':''},{'step_1_headline':None},{'unknown_field':'Text'}):
            with self.subTest(content=content),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),{**inputs(),'content':content})

    def test_theme_inputs_explicit_choices_and_readback(self):
        frame=Frame();data={**inputs(),'theme_inputs':{'appearance':'Box','labels':'Floating'}}
        ui.apply_checkout_ui(frame,data)
        self.assertEqual(frame.theme,{'Appearance':'Box','Labels':'Floating'})
        self.assertEqual(ui.verify_checkout_ui(frame,data)['theme_inputs'],data['theme_inputs'])
        frame.theme['Labels']='Above'
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)
        for theme in ({'appearance':'Circle'},{'labels':'Invented'},{'radius':12}):
            with self.subTest(theme=theme),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),{**inputs(),'theme_inputs':theme})

    def test_authored_plaintext_terms_replace_placeholder_links_and_reopen(self):
        frame=Frame();data={**inputs(),'checkout_options':{'terms_and_conditions':True},
            'legal_copy':{'terms_text':'Approved fixture terms. No acceptance recorded.'}}
        ui.apply_checkout_ui(frame,data)
        self.assertEqual(frame.terms['Terms & conditions']['text'],data['legal_copy']['terms_text'])
        self.assertEqual(frame.terms['Terms & conditions']['links'],0)
        result=ui.verify_checkout_ui(frame,data)
        self.assertTrue(result['legal_copy_saved'])
        self.assertFalse(result['legal_acceptance'])
        self.assertFalse(result['payment_verified'])
        self.assertEqual(set(result['legal_text_sha256']),{'terms_text'})
        frame.terms['Terms & conditions']['text']='Unapproved drift'
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)

    def test_both_terms_editors_bound_by_named_row_not_dom_index(self):
        frame=Frame();frame.terms_order.reverse()
        data={**inputs(),'checkout_options':{'terms_and_conditions':True,'terms_and_conditions_step_2':True},
            'legal_copy':{'terms_text':'Approved first-step terms.','terms_step2_text':'Approved payment-step terms.'}}
        ui.apply_checkout_ui(frame,data)
        self.assertEqual(frame.terms['Terms & conditions']['text'],'Approved first-step terms.')
        self.assertEqual(frame.terms['Terms & conditions (step 2)']['text'],'Approved payment-step terms.')
        self.assertTrue(ui.verify_checkout_ui(frame,data)['legal_copy_saved'])

    def test_terms_missing_plaintext_or_unbound_extra_copy_fails_before_first_write(self):
        changes=[{'checkout_options':{'terms_and_conditions':True}},
                 {'checkout_options':{'terms_and_conditions_step_2':True},'legal_copy':{'terms_step2_text':'<p>HTML</p>'}},
                 {'checkout_options':{'terms_and_conditions':True},'legal_copy':{'terms_text':' '}},
                 {'checkout_options':{'terms_and_conditions':False},'legal_copy':{'terms_text':'Unused copy'}},
                 {'checkout_options':{'terms_and_conditions':True},'legal_copy':{'terms_text':'Text','unknown':'Other'}}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(CheckoutRefused):
                ui.apply_checkout_ui(object(),{**inputs(),**change})

    def test_terms_links_remaining_after_readback_are_never_claimed_plaintext(self):
        frame=Frame();data={**inputs(),'checkout_options':{'terms_and_conditions':True},
            'legal_copy':{'terms_text':'Approved terms'}}
        ui.apply_checkout_ui(frame,data)
        frame.terms['Terms & conditions']['links']=1
        with self.assertRaises(CheckoutRefused):ui.verify_checkout_ui(frame,data)

    def test_save_reopen_then_verify_and_close(self):
        frame=Frame();events=[]
        class Page:
            url=inputs()['start_url']
            def goto(self,url,**kwargs):
                events.append('reopen')
                self.url=url
        page=Page()
        with (patch.object(core,'assert_tenant',side_effect=lambda *a:events.append('identity')),
              patch.object(core,'builder',return_value=frame),
              patch.object(core,'save_page',side_effect=lambda *a:events.append('save'))):
            result=ui.configure_native_checkout_ui(page,inputs())
        self.assertEqual(result['status'],'NATIVE_CHECKOUT_UI_READBACK_VERIFIED')
        self.assertLess(events.index('save'),events.index('reopen'))
        self.assertFalse(frame.dialog)
        self.assertFalse(result['payment_verified'])


class CheckoutUIIntegrationTests(unittest.TestCase):
    def probes(self):
        return {'api_capabilities':{},'lanes':{
            'playwright':{'available':True},
            'openclaw_extension':{'available':True,'current':True}}}

    def test_named_recipe_compiles_validates_and_selects_script_without_adapter_map(self):
        job=core.validate_job(compile_recipe('checkout.configure_ui',inputs()),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'native_checkout_ui')
        observed,error=host._recipe_readiness('checkout.configure_ui',inputs(),self.probes(),Path('.'))
        self.assertIsNone(error)
        self.assertEqual(host.decide('checkout.configure_ui','fixture',observed)['lane'],'playwright')
        self.assertNotIn('adapter_capture',job['steps'][0]['payload'])

    def test_host_runs_actual_registered_handler_and_keeps_payment_pending(self):
        package_ui=importlib.import_module('playwright_recipes.checkout_ui')
        with (tempfile.TemporaryDirectory() as directory,
                patch.object(core,'assert_tenant'),
                patch.object(package_ui,'configure_native_checkout_ui',return_value={
                    'status':'NATIVE_CHECKOUT_UI_READBACK_VERIFIED','element_id':'order-form-fixture',
                    'payment_verified':False}) as actual_handler):
            result=host.run_recipe('checkout.configure_ui',inputs(),self.probes(),directory,input_dir='.',page=object())
            actual_handler.assert_called_once()
            self.assertEqual(result['status'],'NEEDS_VERIFICATION')
            self.assertEqual(result['route']['lane'],'playwright')
            saved=json.loads(Path(directory,'state.json').read_text())
            self.assertEqual(saved['results'][0]['action'],'native_checkout_ui')
            self.assertFalse(saved['results'][0]['result']['checkout_ready'])
            self.assertFalse(saved['results'][0]['result']['payment_verified'])

    def test_invalid_ui_does_not_navigate_and_selects_current_browser_recovery(self):
        package_ui=importlib.import_module('playwright_recipes.checkout_ui')
        invalid={**inputs(),'contact_fields':{'email':{'required':False}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(package_ui,'configure_native_checkout_ui') as actual_handler:
            result=host.run_recipe('checkout.configure_ui',invalid,self.probes(),directory,input_dir='.',page=object())
            self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(result['route']['lane'],'openclaw_extension')
            actual_handler.assert_not_called()
            self.assertFalse(Path(directory,'state.json').exists())

    def test_nested_payload_cannot_retarget_checkout_away_from_job(self):
        job=compile_recipe('checkout.configure_ui',inputs())
        job['steps'][0]['payload']={**job['steps'][0]['payload'],'location_id':'another'}
        with self.assertRaises(core.Stop):core.validate_job(job,Path('.'))

    def test_only_the_exact_persisted_handler_status_is_accepted(self):
        package_ui=importlib.import_module('playwright_recipes.checkout_ui')
        with (tempfile.TemporaryDirectory() as directory,
                patch.object(core,'assert_tenant'),
                patch.object(package_ui,'configure_native_checkout_ui',return_value={
                    'status':'NATIVE_CHECKOUT_UI_EDITED','payment_verified':False})):
            result=host.run_recipe('checkout.configure_ui',inputs(),self.probes(),directory,input_dir='.',page=object())
            self.assertEqual(result['status'],'NEEDS_BROWSER_RECOVERY')
            saved=json.loads(Path(directory,'state.json').read_text())
            self.assertEqual(saved['status'],'NEEDS_BROWSER_RECOVERY')
            self.assertEqual(saved['results'],[])


if __name__=='__main__':unittest.main()
