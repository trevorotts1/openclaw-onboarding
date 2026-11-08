"""Native checkout UI tests based on captured roles, never live payment proof."""
import re
import unittest
from unittest.mock import patch

import checkout_ui as ui
from pages_checkout import CheckoutRefused
import skill6_playwright as core


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
        if self.kind=='switch':return int(self.name in ui.PRODUCT_SWITCHES.values())
        if isinstance(self.name,str) and self.name.startswith('Steps '):return int(self.name=='Steps '+self.frame.mode)
        return 1
    def wait_for(self, **kwargs):
        if kwargs.get('state')=='hidden':
            if self.frame.dialog:raise AssertionError('dialog still visible')
        elif not self.count():raise AssertionError('control absent')
    def filter(self, **kwargs):return self
    def get_by_test_id(self, value):return ContactRow(self.frame,value.replace('field-row-',''))
    def get_by_role(self, role, **kwargs):return Locator(self.frame,role,kwargs.get('name'))
    def evaluate(self, _):return self.frame.section
    def input_value(self):return self.frame.name
    def is_visible(self):return bool(self.count())
    def get_attribute(self,key):
        if key=='aria-checked':return str(self.frame.switches.get(self.name,False)).lower()
        return None
    def click(self):
        self.frame.clicks.append((self.kind,str(self.name)))
        if self.name=='Customize order form':self.frame.dialog=True
        elif self.kind=='switch':self.frame.switches[self.name]=not self.frame.switches.get(self.name,False)
        elif self.name in ui.MODES:self.frame.mode=self.name
        elif self.name=='Alternative text for image not provided':self.frame.dialog=False


class Frame:
    def __init__(self):
        self.section='section-fixture';self.name='Order Form';self.order_count=1
        self.mode='One-step';self.switches={};self.dialog=False;self.clicks=[]
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


if __name__=='__main__':unittest.main()
