"""Native active-card Login binds reuse to an exact authenticated portal popup."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import community_creation as creation
from skill6_playwright import Stop
from test_community_creation_identity import step


class Ready:
    def __init__(self,count=1,visible=True):self.n=count;self.visible=visible
    def count(self):return self.n
    def is_visible(self):return self.visible
    def get_attribute(self,name):return 'add-channel__btn' if name=='id' else None


class Popup:
    def __init__(self,data):
        self.data=data;self.url='https://portal.example.com/communities/groups/'+data['slug']+'/home'
        self.password=False;self.heading=data['name'];self.closed=False
    def title(self):return self.heading+' | Fixture Company'
    def get_by_placeholder(self,name,*,exact):return Ready(int(self.password))
    def get_by_text(self,name,*,exact):return Ready(int(name==self.heading))
    def locator(self,selector):return Ready()
    def get_by_role(self,role,*,name,exact):return Ready()
    def wait_for_load_state(self,*args,**kwargs):pass
    def is_closed(self):return self.closed
    def close(self):self.closed=True


class CommunityExistingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.data=step();self.context=self.data['_context'];self.popup=Popup(self.data)

    def test_exact_popup_needs_group_slug_name_authenticated_controls(self):
        self.assertEqual(creation._popup_identity(self.popup,self.data),self.popup.url)
        self.popup.heading='Other group'
        self.assertIsNone(creation._popup_identity(self.popup,self.data))
        self.popup.heading=self.data['name'];self.popup.url=self.popup.url.replace(self.data['slug'],'other-slug')
        self.assertIsNone(creation._popup_identity(self.popup,self.data))

    def test_auth_wall_or_credential_query_cannot_confirm_reuse(self):
        self.popup.password=True
        with self.assertRaisesRegex(Stop,'authenticated portal'):creation._popup_identity(self.popup,self.data)
        self.popup.password=False;self.popup.url+='?token=PRIVATE_SHOULD_NOT_LEAVE'
        self.assertIsNone(creation._popup_identity(self.popup,self.data))

    def test_name_only_matches_cannot_skip_native_popup_identity(self):
        page=Mock()
        with patch.object(creation,'inventory',return_value=[{'name':self.data['name'],'status':'Active'}]),\
                patch.object(creation,'_reuse_active',side_effect=Stop('native popup unverified')) as reuse:
            with self.assertRaisesRegex(Stop,'native popup unverified'):creation.configure(page,self.data)
            reuse.assert_called_once()

    def test_duplicate_or_case_variant_existing_match_never_opens_login(self):
        for rows in (
                     [{'name':self.data['name'].upper(),'status':'Active'}],
                     [{'name':self.data['name'],'status':'Active'},{'name':self.data['name'],'status':'Inactive'}]):
            with self.subTest(rows=rows),patch.object(creation,'inventory',return_value=rows),\
                    patch.object(creation,'_reuse_active') as reuse:
                with self.assertRaisesRegex(Stop,'IDENTITY_UNVERIFIED'):creation.configure(Mock(),self.data)
                reuse.assert_not_called()

    def test_inactive_target_request_never_logs_in_or_changes_status(self):
        data=deepcopy(self.data);data['inactive']=True;page=Mock()
        with self.assertRaisesRegex(Stop,'inactive:false'):creation._reuse_active(page,data,self.context)
        page.expect_popup.assert_not_called()

    def test_native_popup_reuse_closes_only_created_popup_and_stays_proof_pending(self):
        page=Mock();page.locator.return_value=Mock();cards=Mock()
        page.locator.return_value.filter.return_value=cards;cards.count.return_value=1
        status=Mock();status.count.return_value=1;status.inner_text.return_value='Active';cards.locator.return_value=status
        login=Mock();login.count.return_value=1;login.is_visible.return_value=True;cards.get_by_text.return_value=login
        pending=Mock();pending.value=self.popup;page.expect_popup.return_value.__enter__=Mock(return_value=pending)
        page.expect_popup.return_value.__exit__=Mock(return_value=False)
        with patch.object(creation,'_read_filter'),patch.object(creation,'_assert_list'),patch.object(creation,'assert_tenant'),\
                patch.object(creation,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
            result=creation._reuse_active(page,self.data,self.context)
        self.assertEqual(result['status'],'GROUP_REUSED_IDENTITY_CONFIRMED')
        self.assertTrue(result['reused']);self.assertTrue(result['portal_identity_verified'])
        self.assertFalse(result['description_verified']);self.assertFalse(result['functional_verified'])
        self.assertTrue(self.popup.closed)


    def test_inactive_name_match_dispatches_only_inactive_reuse_and_never_activation(self):
        data=deepcopy(self.data);data['inactive']=True;page=Mock()
        with patch.object(creation,'inventory',return_value=[{'name':data['name'],'status':'Inactive'}]),\
                patch.object(creation,'_reuse_inactive',return_value={'reused':True}) as inactive,\
                patch.object(creation,'_reuse_active') as active,\
                patch.object(creation,'_deactivate_created') as deactivate:
            self.assertTrue(creation.configure(page,data)['reused'])
        inactive.assert_called_once_with(page,data,data['_context'])
        active.assert_not_called();deactivate.assert_not_called()

    def test_inactive_reuse_requires_captured_modern_home_not_old_inactive_route(self):
        self.assertEqual(creation._popup_identity(self.popup,self.data,status='Inactive'),self.popup.url)
        self.popup.url=self.popup.url.rsplit('/',1)[0]+'/inactive-group'
        self.assertIsNone(creation._popup_identity(self.popup,self.data,status='Inactive'))
        self.popup.url=self.popup.url.rsplit('/',1)[0]+'/home'
        self.popup.password=True
        with self.assertRaisesRegex(Stop,'authenticated portal'):
            creation._popup_identity(self.popup,self.data,status='Inactive')

    def test_active_target_request_never_activates_or_opens_inactive_login(self):
        page=Mock()
        with self.assertRaisesRegex(Stop,'cannot activate'):
            creation._reuse_inactive(page,self.data,self.context)
        page.expect_popup.assert_not_called()

    def test_inactive_popup_requires_both_captured_modern_admin_links(self):
        self.popup.locator=lambda selector:Ready(count=0)
        self.assertIsNone(creation._popup_identity(self.popup,self.data,status='Inactive'))


    def test_inactive_native_login_handoff_closes_popup_without_any_status_change(self):
        data=deepcopy(self.data);data['inactive']=True
        page=Mock();page.locator.return_value=Mock();cards=Mock()
        page.locator.return_value.filter.return_value=cards;cards.count.return_value=1
        status=Mock();status.count.return_value=1;status.inner_text.return_value='Inactive';cards.locator.return_value=status
        login=Mock();login.count.return_value=1;login.is_visible.return_value=True;cards.get_by_text.return_value=login
        pending=Mock();pending.value=self.popup;page.expect_popup.return_value.__enter__=Mock(return_value=pending)
        page.expect_popup.return_value.__exit__=Mock(return_value=False)
        with patch.object(creation,'_read_filter') as read_filter,patch.object(creation,'_assert_list'),\
                patch.object(creation,'assert_tenant'),\
                patch.object(creation,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
            result=creation._reuse_inactive(page,data,data['_context'])
        self.assertEqual(result['group_status'],'Inactive')
        self.assertEqual(result['portal_url'],self.popup.url)
        self.assertFalse(result['group_activation_attempted']);self.assertFalse(result['functional_verified'])
        read_filter.assert_called_once_with(page,data['_context'],'Inactive')
        login.click.assert_called_once();status.click.assert_not_called()
        self.assertTrue(self.popup.closed)


    def test_inactive_identity_reuse_rechecks_native_status_before_completion(self):
        data=deepcopy(self.data);data['inactive']=True
        before=[{'name':data['name'],'status':'Inactive'}]
        after=[{'name':data['name'],'status':'Active'}]
        with patch.object(creation,'inventory',side_effect=[before,after]),\
                patch.object(creation,'_reuse_inactive',return_value={'reused':True}),\
                self.assertRaisesRegex(Stop,'status or unrelated native inventory changed'):
            creation.configure(Mock(),data)


if __name__=='__main__':unittest.main()
