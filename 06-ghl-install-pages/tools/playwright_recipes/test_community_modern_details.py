"""Modern description saves retain native identity, privacy and three flags."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import skill6_playwright
from playwright_recipes import community_modern_details as native
from playwright_recipes.skill6_playwright import Stop
from test_community_details import details_inputs


class Node:
    def __init__(self,page,key):self.page=page;self.key=key
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return True
    def wait_for(self,**kwargs):pass
    def locator(self,selector):return self.page.locator(selector)
    def input_value(self):return self.page.values[self.key]
    def is_checked(self):return self.page.values[self.key]
    def get_attribute(self,name):
        if name=='role':return 'checkbox'
        if name=='aria-disabled':return 'false'
        if name=='aria-checked':return str(self.page.values[self.key]).lower()
    def fill(self,value,**kwargs):
        self.page.values[self.key]=value
        if self.page.drift_on_fill:self.page.values['mandatory_profile']=False
    def click(self,**kwargs):
        if self.key!='save':
            if not self.page.access_mode:raise AssertionError('Unexpected native mutation '+self.key)
            if self.key in ('public','private'):
                self.page.values['public']=self.key=='public';self.page.values['private']=self.key=='private'
            else:self.page.values[self.key]=not self.page.values[self.key]
            return
        self.page.saves+=1
        if not self.page.lose_save:self.page.saved=self.page.values['description']
        if self.page.drift_on_save:self.page.values['allow_member_invites']=False


class Page:
    def __init__(self,data):
        self.url=native.details_url(data);self.saved=data['details']['expected_description']
        self.values={'name':data['group_name'],'slug':'zhc-fixture','description':self.saved,
            'accessible_from_switcher':True,'allow_member_invites':True,'mandatory_profile':True,
            'public':True,'private':False}
        self.access_mode=False;self.saves=0;self.reloads=0;self.lose_save=False;self.drift_on_save=False;self.drift_on_fill=False
    def locator(self,selector):
        selectors={'#group-details-card-container':'panel','#group-details-name-input input':'name',
            '#group-details-slug-input input':'slug','#group-details-description-textarea textarea':'description',
            '#group-details-public-group-radio-card':'public','#group-details-private-group-radio-card':'private',
            '#group-settings-save-button':'save',**{value:key for key,value in native.FLAGS.items()}}
        node=Node(self,selectors[selector])
        if node.key in ('public','private'):node.locator=lambda _:Node(self,node.key)
        return node
    def wait_for_load_state(self,*args,**kwargs):pass
    def reload(self,**kwargs):self.reloads+=1;self.values['description']=self.saved


class ModernDetailsTests(unittest.TestCase):
    def data(self):
        data=details_inputs();data['portal_url']=data['portal_url'].replace('/inactive-group','/home');return data
    def run_native(self,page,data,root):
        return native.run_details(page,data,root,portal_context=object())
    def test_description_save_reopen_replay_preserves_every_protected_control(self):
        data=self.data();page=Page(data);before=deepcopy(page.values)
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_check'):
            result=self.run_native(page,data,root)
            self.assertTrue(result['description_verified']);self.assertTrue(result['protected_access_unchanged'])
            self.assertFalse(result['group_activation_attempted']);self.assertFalse(result['behavior_verified'])
            self.assertEqual({key:value for key,value in page.values.items() if key!='description'},
                {key:value for key,value in before.items() if key!='description'})
            self.assertEqual(page.saved,data['details']['description']);self.assertEqual(page.saves,1)
            self.assertTrue(self.run_native(page,data,root)['replayed']);self.assertEqual(page.saves,1)
            self.assertNotIn(data['details']['description'],Path(root,'community-details-state.json').read_text())
            page.saved='External change'
            with self.assertRaisesRegex(Stop,'Completed modern'):self.run_native(page,data,root)
            self.assertEqual(page.saves,1)
    def test_identity_or_access_drift_and_lost_save_never_report_success_or_retry(self):
        for flag in ('wrong_slug','drift_on_fill','drift_on_save','lose_save'):
            data=self.data();page=Page(data)
            if flag=='wrong_slug':page.values['slug']='foreign'
            else:setattr(page,flag,True)
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as root,patch.object(native,'_check'):
                with self.assertRaises(Stop):self.run_native(page,data,root)
                if flag in ('wrong_slug','drift_on_fill'):self.assertEqual(page.saves,0)
                saves=page.saves
                with self.assertRaises(Stop):self.run_native(page,data,root)
                self.assertEqual(page.saves,saves)
    def test_portal_dispatch_uses_existing_payload_and_receipt_contract(self):
        data=self.data();page=Page(data)
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_check'):
            result=native.portal.run_details(page,data,root,portal_context=object())
        self.assertTrue(result['description_verified']);self.assertEqual(page.saves,1)


    def test_modern_access_restrictions_preserve_description_identity_and_replay_without_writes(self):
        from playwright_recipes import community_access as access
        base=self.data();page=Page(base);page.access_mode=True
        data={key:value for key,value in base.items() if key!='details'}
        data['access']={'expected':{'privacy':'public','accessible_from_switcher':True,
            'allow_member_invites':True,'mandatory_profile':True},
            'desired':{'privacy':'private','accessible_from_switcher':False,'allow_member_invites':False}}
        description=page.saved
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_check'):
            result=access.run_access(page,data,root,portal_context=object())
            self.assertTrue(result['description_unchanged']);self.assertFalse(result['access_expansion_performed'])
            self.assertFalse(page.values['public']);self.assertTrue(page.values['private'])
            self.assertFalse(page.values['allow_member_invites']);self.assertTrue(page.values['mandatory_profile'])
            self.assertEqual(page.saved,description);self.assertEqual(page.saves,1)
            self.assertTrue(access.run_access(page,data,root,portal_context=object())['replayed'])
            self.assertEqual(page.saves,1)
            page.values['allow_member_invites']=True
            with self.assertRaisesRegex(Stop,'Completed modern community access'):
                access.run_access(page,data,root,portal_context=object())
            self.assertEqual(page.saves,1)

    def test_modern_access_expansion_keeps_existing_opaque_authorization_gate(self):
        from playwright_recipes import community_access as access
        base=self.data();page=Page(base);page.access_mode=True
        page.values.update(public=False,private=True)
        data={key:value for key,value in base.items() if key!='details'}
        data['access']={'expected':{'privacy':'private','accessible_from_switcher':True,
            'allow_member_invites':True,'mandatory_profile':True},'desired':{'privacy':'public'}}
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_check'):
            with self.assertRaisesRegex(Stop,'ACCESS_CONFIRMATION_REQUIRED'):
                access.run_access(page,data,root,portal_context=object())
            self.assertEqual(page.saves,0);self.assertFalse(Path(root,'community-access-state.json').exists())


if __name__=='__main__':unittest.main()
