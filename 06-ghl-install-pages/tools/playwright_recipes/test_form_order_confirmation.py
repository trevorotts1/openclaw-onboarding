"""Payment outcome configuration never mistakes the canned preview for proof."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

import form_order_confirmation as native
from skill6_playwright import Stop


def plan():
    price={'native_product_id':'PRODUCT','native_price_id':'PRICE','amount_minor':19700,
        'currency':'USD','billing_type':'recurring','recurring_interval':'month','trial_days':None}
    return {'action':'native_order_confirmation','payload':{
        'location_id':'LOC','location_name':'Approved account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
        'form_id':'FORM','expected_form_name':'Payment Form','expected_mode':'Message',
        'ack_conditional_precedence':False,'checkout_contract':{
            'status':'PASS','source':'approved inventory','location_id':'LOC','form_id':'FORM',
            'product_id':'PRODUCT','product_name':'Approved Product','product_type':'DIGITAL',
            'price_id':'PRICE','price_name':'Monthly','price':price,'display_amount':'$197/month',
            'expected_selected':False,'observed_at':datetime.now(timezone.utc).isoformat()}}}


def products_module():
    name='_skill6_order_confirmation_test_products'
    if name not in sys.modules:
        path=Path(native.__file__).resolve().parents[3]/'shared-utils/ghl/products_prices.py'
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]


class SchemaTests(unittest.TestCase):
    def test_contract_is_exact_form_product_price_terms_and_native_display_inventory(self):
        value=plan()
        self.assertEqual(native.validate(value),value)
        mutations=[lambda d:d['checkout_contract'].update(form_id='OTHER'),
            lambda d:d['checkout_contract'].update(payment_element_id='INVENTED'),
            lambda d:d['checkout_contract'].update(expected_selected='false'),
            lambda d:d['checkout_contract'].update(display_amount='$198/month'),
            lambda d:d['checkout_contract']['price'].update(native_price_id='OTHER'),
            lambda d:d.update(start_url='https://app.convertandflow.com/v2/location/OTHER/form-builder-v2/FORM'),
            lambda d:d.update(message='unrequested content')]
        for mutate in mutations:
            value=plan();mutate(value['payload'])
            with self.subTest(value=value),self.assertRaises(Stop):native.validate(value)

    def test_stale_contract_is_structurally_replayable_but_cannot_start_a_new_write(self):
        value=plan();value['payload']['checkout_contract']['observed_at']=(
            datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        native.validate(value)
        self.assertEqual(len(native.configuration_hash(value)),64)
        page=Mock()
        with self.assertRaisesRegex(Stop,'stale'):native.configure(page,value)
        self.assertFalse(page.mock_calls)

    def test_hash_binds_approved_price_identity_checkbox_and_expected_mode(self):
        base=plan();variants=[deepcopy(base) for _ in range(3)]
        variants[0]['payload']['checkout_contract']['expected_selected']=True
        variants[1]['payload']['expected_mode']='Order Confirmation'
        variants[2]['payload']['checkout_contract']['price_id']='OTHER'
        variants[2]['payload']['checkout_contract']['price']['native_price_id']='OTHER'
        self.assertEqual(len({native.configuration_hash(x) for x in [base,*variants]}),4)


class CatalogTests(unittest.TestCase):
    def setup_catalog(self, **changes):
        pp=products_module()
        records={
            '/products/PRODUCT?locationId=LOC':{'_id':'PRODUCT','locationId':'LOC','name':'Approved Product','productType':'DIGITAL'},
            '/products/PRODUCT/price/PRICE?locationId=LOC':{'_id':'PRICE','product':'PRODUCT','name':'Monthly',
                'type':'recurring','currency':'USD','amount':197,'recurring':{'interval':'month','intervalCount':1}},
            '/products/PRODUCT/price?locationId=LOC&limit=100':{'prices':[{'_id':'PRICE'}],'total':1}}
        records.update(changes)
        calls=[]
        class Transport:
            def request(self,method,path,body=None):
                if method!='GET' or body is not None:raise AssertionError('Catalog guard attempted a write')
                calls.append((method,path))
                return pp.Response(200,deepcopy(records[path]))
        catalog=object.__new__(native.ReadOnlyCatalog);catalog.pp=pp
        catalog.adapter=pp.ProductsPricesAdapter(Transport(),pp.InMemoryStore())
        return catalog,records,calls,pp

    def test_real_canonical_adapter_reads_exact_product_price_and_complete_unique_catalog(self):
        catalog,_,calls,_=self.setup_catalog()
        result=catalog.verify(plan()['payload']['checkout_contract'])
        self.assertEqual(result['price_identity'],'UNIQUE_CATALOG_PRICE')
        self.assertEqual(result['price'],plan()['payload']['checkout_contract']['price'])
        self.assertEqual(len(calls),3)
        self.assertTrue(all(method=='GET' for method,_ in calls))

    def test_multiple_truncated_unknown_or_wrong_price_catalog_never_passes(self):
        invalid=[{'prices':[{'_id':'PRICE'},{'_id':'ANNUAL'}],'total':2},
            {'prices':[{'_id':'PRICE'}],'total':2}, {'prices':[{'_id':'PRICE'}]},
            {'prices':[{'_id':'PRICE'}],'total':True}, {'prices':[{'_id':'OTHER'}],'total':1}]
        for listed in invalid:
            catalog,_,calls,_=self.setup_catalog(**{'/products/PRODUCT/price?locationId=LOC&limit=100':listed})
            with self.subTest(listed=listed),self.assertRaisesRegex(Stop,'exactly one price'):
                catalog.verify(plan()['payload']['checkout_contract'])
            self.assertTrue(all(method=='GET' for method,_ in calls))

    def test_wrong_native_location_product_or_terms_fail_in_the_canonical_reader(self):
        for resource,change in (('product',{'locationId':'OTHER'}),('price',{'product':'OTHER'}),
                                 ('price',{'amount':198}),('price',{'recurring':{'interval':'year','intervalCount':1}})):
            catalog,records,calls,pp=self.setup_catalog()
            path='/products/PRODUCT?locationId=LOC' if resource=='product' else '/products/PRODUCT/price/PRICE?locationId=LOC'
            records[path].update(change)
            with self.subTest(change=change),self.assertRaises(pp.ReadbackMismatch):
                catalog.verify(plan()['payload']['checkout_contract'])
            self.assertTrue(all(method=='GET' for method,_ in calls))

    def test_default_transport_reuses_skill44_client_and_denial_is_terminal(self):
        import playwright_recipes.delivery as delivery
        from ghl_auth import AuthBridgeError
        pp=products_module();client=Mock()
        error=RuntimeError('value-free fixture denial');error.response=SimpleNamespace(status_code=403)
        client.get.side_effect=error
        cli=SimpleNamespace(_products_prices=lambda:pp)
        with patch.object(delivery,'Skill44Transport',return_value=SimpleNamespace(client=client)), \
                patch.dict('sys.modules',{'cli_anything.gohighlevel.gohighlevel_cli':cli}):
            catalog=native.ReadOnlyCatalog()
            with self.assertRaises(AuthBridgeError):catalog.verify(plan()['payload']['checkout_contract'])
            with self.assertRaises(Stop):catalog.adapter._t.request('POST','/products/',{})
        self.assertEqual(client.get.call_count,1)
        self.assertEqual(client.get.call_args.kwargs['version'],pp.API_VERSION)


class NativeProductTests(unittest.TestCase):
    def surface(self, *, product='PRODUCT', label='Approved Product', amount='$197/month', selected=False, rows=1):
        labels,item,collection,row,checkbox,name,price=[Mock() for _ in range(7)]
        labels.count.return_value=item.count.return_value=checkbox.count.return_value=name.count.return_value=price.count.return_value=1
        item.is_visible.return_value=name.is_visible.return_value=price.is_visible.return_value=True
        collection.count.return_value=rows;collection.nth.return_value=row
        checkbox.get_attribute.return_value=product;checkbox.is_checked.return_value=selected
        name.inner_text.return_value=label;price.inner_text.return_value=amount
        row.locator.side_effect={'input[type="checkbox"]':checkbox,'.product-label':name,'.product-amount':price}.__getitem__
        item.locator.return_value=collection
        owners=Mock();owners.filter.return_value=item
        frame=Mock();frame.locator.side_effect=lambda selector:labels if selector.startswith('label[') else owners
        return frame,checkbox

    def test_native_product_id_label_price_and_unselected_state_are_read_without_clicking(self):
        frame,checkbox=self.surface()
        result=native._payment(frame,plan()['payload']['checkout_contract'])
        self.assertEqual(result['product_id'],'PRODUCT');self.assertFalse(result['selected'])
        checkbox.click.assert_not_called()

    def test_wrong_product_or_changed_amount_or_checkbox_state_refuses(self):
        for change in ({'product':'OTHER'},{'amount':'$197/year'},{'selected':True},{'rows':2}):
            frame,checkbox=self.surface(**change)
            with self.subTest(change=change),self.assertRaises(Stop):
                native._payment(frame,plan()['payload']['checkout_contract'])
            checkbox.click.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def exercise(self, *, prior='Message', expected='Message', precedence=False,
                 acknowledge=False, lost_save=False, drift_after_save=False, catalog_refused=False):
        from contextlib import ExitStack
        import playwright_recipes.skill6_playwright as core
        import playwright_recipes.field_placement as fields
        import playwright_recipes.assessments as assessments
        data=plan();data['payload']['expected_mode']=expected
        data['payload']['ack_conditional_precedence']=acknowledge
        state={'mode':prior,'persisted':prior,'saves':0,'changes':0,'reopens':0,'settings':{'sticky_contact':False}}
        page=Mock();page.url=data['payload']['start_url']
        frame,title,tab,selector,option,save,menu,warning=[Mock() for _ in range(8)]
        for node in (title,tab,selector,option,save):
            node.count.return_value=1;node.is_visible.return_value=True;node.is_enabled.return_value=True
        title.input_value.return_value='Payment Form'
        frame.get_by_role.side_effect=lambda role,name,exact:title if name=='Form Name' else save if name=='Save' else tab
        frame.locator.return_value=menu;menu.get_by_text.return_value=option
        warning.count.return_value=1;warning.nth.return_value.is_visible.return_value=precedence
        frame.get_by_text.return_value=warning
        def clicked(node):
            if node is option:state['mode']='Order Confirmation';state['changes']+=1
            elif node is save:
                state['saves']+=1
                if not lost_save:state['persisted']=state['mode']
                if drift_after_save:state['settings']['sticky_contact']=True
        def reopened(*args):
            state['reopens']+=1;state['mode']=state['persisted']
        reader=Mock();reader.verify.return_value={'product_id':'PRODUCT','price_identity':'UNIQUE_CATALOG_PRICE'}
        if catalog_refused:reader.verify.side_effect=Stop('Multiple catalog prices')
        with ExitStack() as stack:
            stack.enter_context(patch.object(core,'assert_tenant'))
            stack.enter_context(patch.object(core,'form_builder',return_value=frame))
            stack.enter_context(patch.object(core,'click',side_effect=clicked))
            stack.enter_context(patch.object(core,'wait_until',side_effect=lambda fn,msg:self.assertTrue(fn(),msg)))
            stack.enter_context(patch.object(fields,'_close_initial'))
            stack.enter_context(patch.object(assessments,'reopen_editor',side_effect=reopened))
            stack.enter_context(patch.object(native,'_payment',return_value={'product_id':'PRODUCT','selected':False}))
            stack.enter_context(patch.object(native,'_mode',side_effect=lambda frame:(selector,state['mode'])))
            stack.enter_context(patch.object(native,'_settings',side_effect=lambda frame:deepcopy(state['settings'])))
            stack.enter_context(patch.object(native,'_confirmation'))
            try:result=native.configure(page,data,catalog=reader)
            except Stop as error:result=error
        return result,state,reader,data

    def test_exact_mode_one_save_independent_reopen_and_catalog_product_readback(self):
        result,state,reader,data=self.exercise()
        self.assertEqual(result['status'],'ORDER_CONFIRMATION_SAVED_AND_REOPENED')
        self.assertEqual((state['changes'],state['saves'],state['reopens']),(1,1,1))
        self.assertEqual(reader.verify.call_count,3)
        self.assertEqual(result['configuration_sha256'],native.configuration_hash(data))
        self.assertFalse(result['payment_verified']);self.assertFalse(result['submission_verified'])
        self.assertFalse(result['behavior_verified'])

    def test_replay_rejects_foreign_targets_changed_config_or_payment_claims(self):
        result,_,_,data=self.exercise()
        self.assertTrue(native.validate_receipt(result,data))
        for change in ({'product_id':'OTHER'},{'price_id':'OTHER'},{'form_id':'OTHER'},
                       {'editor_url':data['payload']['start_url']+'OTHER'},
                       {'configuration_sha256':'0'*64},{'payment_verified':True},
                       {'price_identity':'NATIVE_FORM_PRICE_ID'},
                       {'conditional_precedence_present':True}):
            with self.subTest(change=change),self.assertRaises(Stop):
                native.validate_receipt({**result,**change},data)

    def test_stale_mode_unverified_catalog_or_unacknowledged_precedence_stop_before_mode_save(self):
        for change in ({'prior':'Redirect to URL'},{'catalog_refused':True},{'precedence':True}):
            result,state,_,_=self.exercise(**change)
            with self.subTest(change=change):
                self.assertIsInstance(result,Stop)
                self.assertEqual((state['changes'],state['saves']),(0,0))

    def test_saved_mode_loss_or_collateral_settings_change_never_pass(self):
        for change in ({'lost_save':True},{'drift_after_save':True}):
            result,state,_,_=self.exercise(**change)
            with self.subTest(change=change):
                self.assertIsInstance(result,Stop);self.assertEqual(state['saves'],1)

    def test_existing_exact_mode_reopens_without_mode_write_or_save(self):
        result,state,_,_=self.exercise(prior='Order Confirmation',expected='Order Confirmation')
        self.assertEqual(result['status'],'ORDER_CONFIRMATION_REUSED_AND_REOPENED')
        self.assertEqual((state['changes'],state['saves'],state['reopens']),(0,0,1))

    def test_acknowledged_precedence_stays_pending_behavior(self):
        result,_,_,_=self.exercise(precedence=True,acknowledge=True)
        self.assertTrue(result['conditional_precedence_present'])
        self.assertTrue(result['conditional_precedence_acknowledged'])
        self.assertFalse(result['payment_verified'])


if __name__=='__main__':unittest.main()
