"""Modern ordinary channel creation preserves siblings and never repeats intent."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import skill6_playwright
from playwright_recipes import community_modern_channels as native
from playwright_recipes.skill6_playwright import Stop
from test_community_portal import inputs


class ModernChannelTests(unittest.TestCase):
    def setUp(self):
        self.section_inventory=patch.object(native,'_section_inventory',return_value=[])
        self.section_inventory.start();self.addCleanup(self.section_inventory.stop)

    def test_creation_replay_and_drift_bind_complete_saved_native_links(self):
        data=inputs();page=Mock();page.rows=[{'name':'Announcements','href':'/communities/groups/zhc-fixture/channels/Announcements-123'}]
        old=deepcopy(page.rows)
        def create(page,data,context,clock,channel):
            page.rows.insert(0,{'name':channel['name'],'href':'/communities/groups/zhc-fixture/channels/ZHC-Announcements-456'})
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_inventory',side_effect=lambda page,data:deepcopy(page.rows)),\
                patch.object(native,'_home'),patch.object(native,'_create',side_effect=create) as writer,\
                patch.object(native,'_read_channel_metadata',side_effect=lambda page,data,context,clock,row:
                    native._expected_metadata(data['channels'][0])):
            result=native.run_owned(page,data,root,object(),lambda:1)
            self.assertEqual(result['channel_count'],1);self.assertTrue(result['description_verified'])
            self.assertEqual(page.rows[1:],old)
            self.assertTrue(native.run_owned(page,data,root,object(),lambda:1)['replayed'])
            writer.assert_called_once()
            page.rows[1]['href']='/communities/groups/zhc-fixture/channels/CHANGED'
            with self.assertRaisesRegex(Stop,'sibling links changed'):native.run_owned(page,data,root,object(),lambda:1)
            writer.assert_called_once()

    def test_new_job_does_not_infer_ordinary_metadata_from_existing_same_name(self):
        data=inputs();page=Mock();rows=[{'name':data['channels'][0]['name'],'href':'/communities/groups/zhc-fixture/channels/EXISTING'}]
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_inventory',return_value=rows),\
                patch.object(native,'_home'),patch.object(native,'_create') as writer,\
                patch.object(native,'_read_channel_metadata',return_value={'name':data['channels'][0]['name'],
                    'description':'different','icon':'Hash02Icon','private':False,'private_visibility':None,'read_only':False}):
            with self.assertRaisesRegex(Stop,'metadata differs'):native.run_owned(page,data,root,object(),lambda:1)
            writer.assert_not_called();self.assertFalse(Path(root,'community-portal-state.json').exists())

    def test_existing_channel_reuse_requires_matching_native_description_icon_and_access(self):
        data=inputs();page=Mock();wanted=data['channels'][0]
        sibling={'name':'Keep','href':'/communities/groups/zhc-fixture/channels/KEEP'}
        target={'name':wanted['name'],'href':'/communities/groups/zhc-fixture/channels/EXISTING'}
        page.rows=[sibling,target];original=deepcopy(page.rows)
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_inventory',side_effect=lambda page,data:deepcopy(page.rows)),\
                patch.object(native,'_home'),patch.object(native,'_create') as writer,\
                patch.object(native,'_read_channel_metadata',side_effect=lambda page,data,context,clock,row:
                    native._expected_metadata(data['channels'][0])):
            result=native.run_owned(page,data,root,object(),lambda:1)
            self.assertEqual(page.rows,original);self.assertTrue(result['access_verified'])
            self.assertTrue(native.run_owned(page,data,root,object(),lambda:1)['replayed'])
            writer.assert_not_called()

    def test_channel_metadata_read_uses_about_details_edit_and_closes_without_saving(self):
        data=inputs();channel=data['channels'][0]
        page=Mock();modal=Mock();form=Mock();trigger=Mock();details=Mock();edits=Mock();edit=Mock();close=Mock()
        page.locator.side_effect=lambda selector: trigger if selector.startswith('#channel-settings-') else modal
        page.goto.side_effect=lambda url,**kwargs:setattr(page,'url',url)
        modal.locator.side_effect=lambda selector: form if selector=='#channels-create-form' else close
        modal.get_by_text.side_effect=lambda value,**kwargs:details if value=='Channel Details' else edits
        edits.count.return_value=2;edits.nth.return_value=edit;edit.count.return_value=1;edit.is_visible.return_value=True
        modal.count.return_value=1;modal.is_visible.return_value=True
        form.count.return_value=1;form.is_visible.return_value=True
        trigger.count.return_value=1;trigger.is_visible.return_value=True
        details.count.return_value=1;details.is_visible.return_value=True
        close.count.return_value=1;close.is_visible.return_value=True
        name=Mock();name.count.return_value=1;name.is_visible.return_value=True;name.input_value.return_value=channel['name']
        icon=Mock();icon.count.return_value=1;icon.is_visible.return_value=True;icon.input_value.return_value='Hash02Icon'
        description=Mock();description.count.return_value=1;description.is_visible.return_value=True;description.input_value.return_value=channel['description']
        private=Mock();private.count.return_value=1;private.is_visible.return_value=True;private.get_attribute.return_value='true'
        readonly=Mock();readonly.count.return_value=1;readonly.is_visible.return_value=True;readonly.get_attribute.return_value='true'
        hidden=Mock();hidden.count.return_value=1;hidden.is_checked.return_value=True
        visible=Mock();visible.count.return_value=1;visible.is_checked.return_value=False
        def field(selector):
            if 'name-input' in selector:return name
            if 'icon-field' in selector:return icon
            if 'description-input' in selector:return description
            if 'private-toggle' in selector:return private
            if 'readonly-toggle' in selector:return readonly
            if 'discoverable-hidden' in selector:return hidden
            if 'discoverable-visible' in selector:return visible
            raise AssertionError(selector)
        form.locator.side_effect=field
        row={'name':channel['name'],'href':'/communities/groups/zhc-fixture/channels/SLUG'}
        with patch.object(native,'_route_identity'),patch.object(native,'click',side_effect=lambda target:None):
            result=native._read_channel_metadata(page,data,object(),lambda:1,row)
        self.assertEqual(result,{'name':channel['name'],'description':channel['description'],
            'icon':'Hash02Icon','private':True,'private_visibility':'hidden','read_only':True})
        modal.locator.assert_any_call('button#hr-modal__close-button')

    def test_custom_icon_selects_unique_captured_svg_signature(self):
        modal=Mock();trigger=Mock();tab=Mock();panel=Mock();buttons=Mock();field=Mock()
        trigger.count.return_value=1;trigger.is_visible.return_value=True
        tab.count.return_value=1;tab.is_visible.return_value=True
        panel.count.return_value=1;panel.is_visible.return_value=True
        modal.locator.return_value=trigger;modal.get_by_role.side_effect=lambda role,**kwargs:tab if role=='tab' else panel
        catalog=native._ICON_CATALOG['Heart'];wrong=Mock();target=Mock()
        for button in (wrong,target):button.is_visible.return_value=True
        paths_wrong=Mock();paths_wrong.count.return_value=1;paths_wrong.nth.return_value=Mock(get_attribute=Mock(return_value='wrong'))
        paths_target=Mock();paths_target.count.return_value=len(catalog)
        paths_target.nth.side_effect=lambda index:Mock(get_attribute=Mock(return_value=catalog[index]))
        wrong.locator.return_value=paths_wrong;target.locator.return_value=paths_target
        buttons.count.return_value=2;buttons.nth.side_effect=lambda index:(wrong,target)[index]
        panel.get_by_role.return_value=buttons
        field.input_value.return_value='Heart';events=[]
        with patch.object(native,'click',side_effect=lambda node:events.append(node)),\
                patch.object(native,'wait_until',side_effect=lambda fn,message:self.assertTrue(fn())):
            native._select_icon(page=Mock(),modal=modal,field=field,icon_name='Heart')
        self.assertEqual(events,[trigger,tab,target])

    def test_section_uses_captured_section_form_icon_name_and_submit_controls(self):
        data=inputs();page=Mock();modal=Mock();entry=Mock();form=Mock();channel=Mock();section_mode=Mock()
        name=Mock();icon=Mock();submit=Mock()
        page.locator.side_effect=lambda selector:entry if selector==native.ENTRY else modal
        modal.locator.side_effect=lambda selector:{
            '#channels-create-channel-radio-card input[type="radio"]':channel,
            '#channels-create-section-radio-card input[type="radio"]':section_mode,
            '#channels-create-section-radio-card':Mock(count=Mock(return_value=1),is_visible=Mock(return_value=True)),
            '#channel-sections-create-form':form,
            '#channel-sections-create-name-input input':name,
            '#channel-sections-create-icon-field input':icon,
            '#channel-sections-create-submit-button':submit,
        }[selector]
        form.locator.side_effect=lambda selector:{
            '#channel-sections-create-name-input input':name,
            '#channel-sections-create-icon-field input':icon,
        }[selector]
        for node in (entry,modal,form,name,icon,submit):node.count.return_value=1;node.is_visible.return_value=True
        channel.count.return_value=1;channel.is_checked.return_value=False
        section_mode.count.return_value=1;section_mode.is_checked.return_value=True
        name.input_value.return_value='Operations';icon.input_value.return_value='Hash02Icon'
        submit.inner_text.return_value='Create Section';submit.is_enabled.return_value=True
        events=[]
        with patch.object(native.portal,'_check_context'),\
                patch.object(native,'click',side_effect=lambda node:events.append(node)),\
                patch.object(native,'fill',side_effect=lambda node,value:setattr(node,'input_value',Mock(return_value=value))):
            native._create_section(page,data,object(),lambda:1,{'name':'Operations'})
        self.assertEqual(events,[entry,submit])
        self.assertEqual(name.input_value(),'Operations')
        self.assertTrue(modal.locator.called)

    def test_section_create_replay_preserves_all_channel_and_section_siblings(self):
        data=inputs();data['channels']=[];data['sections']=[{'name':'Products','icon':'Home02'}]
        page=Mock();page.rows=[{'name':'Keep channel','href':'/communities/groups/zhc-fixture/channels/KEEP'}]
        page.sections=[{'name':'General','id':'channel-sections-toggle-OLD','expanded':'true','icon':'Hash02Icon'}]
        original_links=deepcopy(page.rows);original_sections=deepcopy(page.sections)
        def create_section(page,data,context,clock,section):
            page.sections.insert(0,{'name':section['name'],'id':'channel-sections-toggle-NEW',
                'expanded':'true','icon':section['icon']})
        with tempfile.TemporaryDirectory() as root,\
                patch.object(native,'_inventory',side_effect=lambda page,data:deepcopy(page.rows)),\
                patch.object(native,'_section_inventory',side_effect=lambda page,data:deepcopy(page.sections)),\
                patch.object(native,'_home'),patch.object(native,'_create_section',side_effect=create_section) as writer:
            result=native.run_owned(page,data,root,object(),lambda:1)
            self.assertEqual(result['section_count'],1);self.assertTrue(result['section_icons_verified'])
            self.assertEqual(page.rows,original_links)
            self.assertEqual(page.sections[1:],original_sections)
            self.assertTrue(native.run_owned(page,data,root,object(),lambda:1)['replayed'])
            writer.assert_called_once()
            page.sections[1]['icon']='Heart'
            with self.assertRaisesRegex(Stop,'section or sibling headers changed'):
                native.run_owned(page,data,root,object(),lambda:1)
            writer.assert_called_once()

    def test_section_inventory_binds_captured_header_owner_settings_and_svg_icon(self):
        self.section_inventory.stop()
        data=inputs();page=Mock();sidebar=Mock();group=Mock();toggle=Mock();owner=Mock();settings=Mock()
        icon_owner=Mock();paths=Mock()
        for node in (sidebar,toggle,owner,settings,icon_owner):node.count.return_value=1;node.is_visible.return_value=True
        group.count.return_value=1;group.is_visible.return_value=True
        toggles=Mock();toggles.count.return_value=1;toggles.nth.return_value=toggle
        rows=Mock();rows.filter.return_value=owner
        sidebar.filter.return_value=sidebar
        sidebar.get_by_role.return_value=group;sidebar.locator.side_effect=lambda selector:toggles if selector.startswith('div[id^=') else rows
        page.get_by_role.side_effect=lambda role,**kwargs:sidebar if role=='complementary' else group
        toggle.get_attribute.side_effect=lambda key:{'id':'channel-sections-toggle-6af5079c29834973ef2c95ca','aria-expanded':'true'}[key]
        toggle.inner_text.return_value='ZHC Script Section'
        owner.locator.side_effect=lambda selector:settings if selector.startswith('button[id=') else icon_owner
        toggle.locator.return_value=icon_owner;icon_owner.locator.return_value=paths
        paths.count.return_value=1;paths.nth.return_value=Mock(get_attribute=Mock(return_value=native._ICON_CATALOG['Hash02Icon'][0]))
        result=native._section_inventory(page,data)
        self.assertEqual(result,[{'name':'ZHC Script Section','id':'channel-sections-toggle-6af5079c29834973ef2c95ca',
            'expanded':'true','icon':'Hash02Icon'}])
        owner.locator.assert_any_call('button[id="channel-sections-settings-6af5079c29834973ef2c95ca"][aria-label="Open section settings"]')

    def test_collateral_sibling_change_keeps_uncertain_intent_without_retry(self):
        data=inputs();page=Mock();page.rows=[{'name':'Keep','href':'/communities/groups/zhc-fixture/channels/KEEP'}]
        def create(page,data,context,clock,channel):page.rows=[{'name':channel['name'],'href':'/communities/groups/zhc-fixture/channels/NEW'}]
        with tempfile.TemporaryDirectory() as root,patch.object(native,'_inventory',side_effect=lambda page,data:deepcopy(page.rows)),\
                patch.object(native,'_home'),patch.object(native,'_create',side_effect=create) as writer:
            with self.assertRaisesRegex(Stop,'retained sibling links'):native.run_owned(page,data,root,object(),lambda:1)
            with self.assertRaises(Stop):native.run_owned(page,data,root,object(),lambda:1)
            writer.assert_called_once()

    def test_default_mode_does_not_authorize_sections_private_readonly_or_other_icon(self):
        modal=Mock();modal.get_by_role.return_value.count.return_value=2
        channel=Mock();channel.count.return_value=1;channel.is_checked.return_value=True
        section=Mock();section.count.return_value=1;section.is_checked.return_value=False
        icon=Mock();icon.count.return_value=1;icon.is_visible.return_value=True;icon.input_value.return_value='Hash02Icon'
        toggle=Mock();toggle.count.return_value=1;toggle.is_visible.return_value=True
        toggle.get_attribute.side_effect=lambda name:'switch' if name=='role' else 'false'
        def locator(selector):
            if 'channel-radio' in selector:return channel
            if 'section-radio' in selector:return section
            if 'icon-field' in selector:return icon
            return toggle
        modal.locator.side_effect=locator
        native._defaults(modal)
        section.is_checked.return_value=True
        with self.assertRaisesRegex(Stop,'ordinary Channel mode'):native._defaults(modal)
        section.is_checked.return_value=False;icon.input_value.return_value='OtherIcon'
        with self.assertRaisesRegex(Stop,'default icon'):native._defaults(modal)
        icon.input_value.return_value='Hash02Icon';toggle.get_attribute.side_effect=lambda name:'switch' if name=='role' else 'true'
        with self.assertRaisesRegex(Stop,'private/read-only'):native._defaults(modal)

    def test_private_readonly_hidden_mode_is_bound_to_captured_switches_and_radios(self):
        modal=Mock();modal.get_by_role.return_value.count.return_value=2
        channel=Mock();channel.count.return_value=1;channel.is_checked.return_value=True
        section=Mock();section.count.return_value=1;section.is_checked.return_value=False
        icon=Mock();icon.count.return_value=1;icon.is_visible.return_value=True;icon.input_value.return_value='Hash02Icon'
        private=Mock();private.count.return_value=1;private.is_visible.return_value=True
        readonly=Mock();readonly.count.return_value=1;readonly.is_visible.return_value=True
        private.get_attribute.side_effect=lambda key:'switch' if key=='role' else 'true'
        readonly.get_attribute.side_effect=lambda key:'switch' if key=='role' else 'true'
        visible=Mock();visible.count.return_value=1;visible.is_checked.return_value=False
        hidden=Mock();hidden.count.return_value=1;hidden.is_checked.return_value=True
        def locator(selector):
            if 'channel-radio' in selector:return channel
            if 'section-radio' in selector:return section
            if 'icon-field' in selector:return icon
            if 'private-toggle' in selector:return private
            if 'readonly-toggle' in selector:return readonly
            if 'discoverable-visible' in selector:return visible
            if 'discoverable-hidden' in selector:return hidden
            raise AssertionError(selector)
        modal.locator.side_effect=locator
        native._defaults(modal,{'private':True,'read_only':True,'private_visibility':'hidden'})
        visible.is_checked.return_value=True
        with self.assertRaisesRegex(Stop,'discoverability'):
            native._defaults(modal,{'private':True,'read_only':True,'private_visibility':'hidden'})


if __name__=='__main__':unittest.main()
