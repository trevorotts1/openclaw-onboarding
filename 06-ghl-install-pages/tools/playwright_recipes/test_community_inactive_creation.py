"""New native group deactivation requires create identity and exact scoped proof."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

import community_creation as creation
from skill6_playwright import Stop
from test_community_creation_identity import step


class Field:
    def __init__(self):self.value=''
    def count(self):return 1
    def is_visible(self):return True
    def wait_for(self,**kwargs):pass
    def fill(self,value,**kwargs):self.value=value
    def input_value(self):return self.value
    def press(self,*args,**kwargs):pass


class Button(Field):
    def __init__(self,page):super().__init__();self.page=page
    def is_enabled(self):return True
    def click(self,**kwargs):
        self.page.clicks+=1
        base=self.page.data['_context']['start_url']
        self.page.url=(base.rsplit('/',1)[0]+'/create-group' if self.page.clicks==1 else
            base+'?'+urlencode({'groupCreated':self.page.data['name'],'groupSlug':self.page.data['slug']}))


class Switch(Field):
    def get_attribute(self,name):return 'false'


class Page:
    def __init__(self,data):
        self.data=data;self.url=data['_context']['start_url'];self.clicks=0
        self.fields={key:Field() for key in ('Group Name','Group Slug','Enter a brief description')}
    def get_by_role(self,role,**kwargs):return Switch() if role=='switch' else Button(self)
    def get_by_placeholder(self,name,**kwargs):return self.fields[name]


class CommunityInactiveCreationTests(unittest.TestCase):
    def test_new_default_inactive_group_requires_create_slug_then_scoped_deactivation_and_readback(self):
        data=step();data.pop('inactive');page=Page(data)
        keep={'name':'Keep existing','status':'Active'}
        with patch.object(creation,'inventory',side_effect=[[keep],[keep,{'name':data['name'],'status':'Active'}],
                    [keep,{'name':data['name'],'status':'Inactive'}]]),\
                patch.object(creation,'_read_filter'),patch.object(creation,'assert_tenant'),\
                patch.object(creation,'_deactivate_created') as deactivate,\
                patch.object(creation,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
            result=creation.configure(page,data)
        deactivate.assert_called_once()
        self.assertEqual(result['status'],'GROUP_CREATED_SLUG_IDENTIFIED')
        self.assertEqual(result['group_status'],'Inactive')
        self.assertIs(result['native_deactivation_attempted'],True);self.assertIs(result['inactive_verified'],True)
        self.assertFalse(result['functional_verified']);self.assertFalse(result['group_activation_attempted'])

    def test_unrelated_inventory_loss_stops_before_deactivation(self):
        data=step();data.pop('inactive');page=Page(data)
        with patch.object(creation,'inventory',side_effect=[[{'name':'Keep','status':'Active'}],[{'name':data['name'],'status':'Active'}]]),\
                patch.object(creation,'_read_filter'),patch.object(creation,'assert_tenant'),\
                patch.object(creation,'_deactivate_created') as deactivate,\
                patch.object(creation,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
            with self.assertRaisesRegex(Stop,'unrelated group inventory'):creation.configure(page,data)
        deactivate.assert_not_called()

    def test_explicit_active_create_never_deactivates(self):
        data=step();page=Page(data)
        with patch.object(creation,'inventory',side_effect=[[],[{'name':data['name'],'status':'Active'}]]),\
                patch.object(creation,'_read_filter'),patch.object(creation,'assert_tenant'),\
                patch.object(creation,'_deactivate_created') as deactivate,\
                patch.object(creation,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
            result=creation.configure(page,data)
        deactivate.assert_not_called();self.assertEqual(result['group_status'],'Active')
        self.assertIs(result['native_deactivation_attempted'],False);self.assertIs(result['inactive_verified'],False)

    def native_dialog(self):
        page=Mock();cards=Mock();cards.count.return_value=1
        page.locator.return_value.filter.return_value=cards
        status=Mock();status.count.return_value=1;status.is_visible.return_value=True;status.inner_text.return_value='Active'
        cards.locator.return_value=status
        option=Mock();option.count.return_value=1;option.is_visible.return_value=True;page.get_by_text.return_value=option
        dialog=Mock();dialog.count.return_value=1;dialog.is_visible.return_value=True
        dialog.get_attribute.return_value='n-card n-modal hl-modal communitiesApp';page.get_by_role.return_value=dialog
        title=Mock();title.count.return_value=1;title.inner_text.return_value='Deactivate Group'
        description=Mock();description.count.return_value=1;description.inner_text.return_value='Are you sure you want to deactivate this group?'
        confirm=Mock();confirm.count.return_value=1;confirm.inner_text.return_value='Confirm';confirm.is_enabled.return_value=True
        cancel=Mock();cancel.count.return_value=1;cancel.inner_text.return_value='Cancel'
        dialog.locator.side_effect=lambda selector:{'.title':title,'.description':description,
            '#modal-footer-btn-positive-action':confirm,'#modal-footer-btn-negative-action':cancel}[selector]
        return page,status,option,title,confirm

    def test_scoped_status_and_exact_dialog_are_required_before_confirm(self):
        page,status,option,title,confirm=self.native_dialog();data=step()
        with patch.object(creation,'_read_filter'),patch.object(creation,'_assert_list'),patch.object(creation,'assert_tenant'):
            creation._deactivate_created(page,data,data['_context'])
        status.click.assert_called_once();option.click.assert_called_once();confirm.click.assert_called_once()

    def test_changed_confirmation_dialog_never_confirms(self):
        page,status,option,title,confirm=self.native_dialog();title.inner_text.return_value='Delete Group';data=step()
        with patch.object(creation,'_read_filter'),patch.object(creation,'_assert_list'),patch.object(creation,'assert_tenant'):
            with self.assertRaisesRegex(Stop,'confirmation text/controls'):creation._deactivate_created(page,data,data['_context'])
        confirm.click.assert_not_called()


if __name__=='__main__':unittest.main()
