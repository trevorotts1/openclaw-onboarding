"""Explicit Custom Block deletion binds exact modal, target and saved survivors."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock,patch

import course_block_delete as deletion
import course_blocks as blocks
import editor_replay
import host
import recipe_cli
import skill6_playwright as runner
from test_course_blocks import inputs as edit_inputs, values
from test_sixth_control_integration import probes


def inputs():
    data=edit_inputs();data['custom_blocks'].pop('updates')
    data['custom_blocks']['deletion']={'action':'delete','id':'BLOCK_A','expected':values('Previous A'),
        'expected_content_html':'<p>Keep <strong>rich A</strong></p>','expected_media_url':'https://example.com/a.png'}
    return data


class Control:
    def __init__(self,page,name,*,present=True):self.page=page;self.name=name;self.present=present
    def count(self):return int(self.present)
    def is_visible(self):return self.present
    def wait_for(self,**kwargs):pass
    def is_enabled(self):return self.page.dirty if self.name=='Save' else True
    def click(self,**kwargs):
        self.page.actions.append(self.name)
        if self.name=='Delete Block':
            self.page.dialog=True
            if self.page.on_delete:self.page.on_delete(self.page)
        elif self.name=='Confirm':
            identity=self.page.actual_removal
            self.page.inventory=[row for row in self.page.inventory if row['id']!=identity]
            self.page.snapshots.pop(identity);self.page.preview.remove(identity)
            self.page.dialog=False;self.page.dirty=True
            if self.page.collateral:self.page.collateral(self.page)
        elif self.name=='Save':
            self.page.dirty=False
            if self.page.lose_save:
                self.page.inventory=deepcopy(self.page.original_inventory)
                self.page.snapshots=deepcopy(self.page.original_snapshots)
                self.page.preview=[row['id'] for row in self.page.inventory]


class Dialog:
    def __init__(self,page):self.page=page
    def count(self):return int(self.page.dialog)
    def is_visible(self):return self.page.dialog
    def wait_for(self,**kwargs):
        if self.page.dialog:raise runner.Stop('Dialog did not close')
    def get_by_role(self,role,*,name,exact):
        present=(name==self.page.heading) if role=='heading' else name in ('Cancel','Confirm')
        return Control(self.page,name,present=present)
    def get_by_text(self,text,*,exact):return Control(self.page,text,present=text==self.page.warning)


class Page:
    def __init__(self):
        data=inputs();self.url=blocks.theme.editor_url(data)
        self.inventory=deepcopy(data['custom_blocks']['expected_inventory'])
        self.snapshots={'BLOCK_A':(values('Previous A'),{'content_html':'<p>Keep <strong>rich A</strong></p>','media_src':'https://example.com/a.png'}),
            'BLOCK_B':(values('Previous B'),{'content_html':'<p>Keep rich B</p>','media_src':'https://example.com/b.png'})}
        self.original_inventory=deepcopy(self.inventory);self.original_snapshots=deepcopy(self.snapshots)
        self.preview=[row['id'] for row in self.inventory];self.selected=None
        self.surroundings={'theme':{'header':'Keep','hero':'Keep','sidebar':'Keep'},'media':['keep-bg','keep-hero','keep-instructor']}
        self.heading=deletion._HEADING;self.warning=deletion._WARNING
        self.actions=[];self.dialog=False;self.dirty=False;self.lose_save=False
        self.actual_removal='BLOCK_A';self.on_delete=None;self.collateral=None
    def get_by_role(self,role,*,name=None,exact=None):
        return Dialog(self) if role=='dialog' else Control(self,name)
    def locator(self,selector):
        match=re.fullmatch(r'div\.custom-block\[id="custom-block-(.+)"\]',selector)
        return Control(self,'preview',present=bool(match and match[1] in self.preview))
    def wait_for_load_state(self,*args,**kwargs):pass


class CustomBlockDeletionTests(unittest.TestCase):
    def setUp(self):
        self.page=Page();self.data=inputs()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.open=self.stack.enter_context(patch.object(blocks.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(blocks.theme,'_identity'))
        self.stack.enter_context(patch.object(deletion,'assert_tenant'))
        self.stack.enter_context(patch.object(deletion,'_surrounding',side_effect=lambda page,plan:deepcopy(page.surroundings)))
        self.stack.enter_context(patch.object(blocks,'_inventory',side_effect=lambda page,plan:deepcopy(page.inventory)))
        self.stack.enter_context(patch.object(blocks,'_visible_inventory',side_effect=lambda page:deepcopy(page.inventory)))
        self.stack.enter_context(patch.object(blocks,'_snapshot',side_effect=lambda page,plan,inventory:deepcopy(page.snapshots)))
        def read(page,plan,identity):
            page.selected=identity
            return deepcopy(page.snapshots[identity])
        self.stack.enter_context(patch.object(blocks,'_read_block',side_effect=read))
        self.stack.enter_context(patch.object(blocks,'_read_selected_block',side_effect=lambda page,identity:deepcopy(page.snapshots[identity])))
        def order(page,inventory):
            if page.preview!=[row['id'] for row in inventory]:raise runner.Stop('Preview order drift')
            return []
        self.stack.enter_context(patch.object(deletion.text,'_preview_order',side_effect=order))
        def selected(page,inventory,identity,kind):
            order(page,inventory)
            if page.selected!=identity:raise runner.Stop('Selected preview changed')
        self.stack.enter_context(patch.object(deletion.text,'_selected_preview',side_effect=selected))
        self.stack.enter_context(patch.object(deletion,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(runner.Stop(message))))

    def run_delete(self):return blocks.configure(self.page,{'payload':self.data})

    def test_only_requested_uuid_is_confirmed_once_then_saved_and_independently_reopened(self):
        original=deepcopy(self.page.snapshots['BLOCK_B'])
        receipt=self.run_delete()
        self.assertEqual(self.page.actions,['Delete Block','Confirm','Save'])
        self.assertEqual(receipt['removed_block_ids'],['BLOCK_A'])
        self.assertEqual(receipt['added_block_ids'],[])
        self.assertEqual(receipt['block_ids'],['categoryBlock','BLOCK_B'])
        self.assertEqual(self.page.snapshots['BLOCK_B'],original)
        self.assertEqual(self.open.call_count,2)
        self.assertFalse(receipt['functional_verified']);self.assertFalse(receipt['activation_performed'])

    def test_all_expected_target_snapshot_and_inventory_must_match_before_delete(self):
        variants=[]
        data=inputs();data['custom_blocks']['deletion']['expected']['heading']='Wrong';variants.append(data)
        data=inputs();data['custom_blocks']['deletion']['expected_content_html']='Wrong';variants.append(data)
        data=inputs();data['custom_blocks']['deletion']['expected_media_url']='https://example.com/wrong.png';variants.append(data)
        data=inputs();data['custom_blocks']['expected_inventory'].reverse();variants.append(data)
        for data in variants:
            self.data=data
            with self.subTest(data=data),self.assertRaises(runner.Stop):self.run_delete()
            self.assertEqual(self.page.actions,[])

    def test_initial_dirty_editor_and_foreign_selection_at_confirm_prevent_destructive_confirm(self):
        self.page.dirty=True
        with self.assertRaisesRegex(runner.Stop,'Unrelated unsaved'):self.run_delete()
        self.assertEqual(self.page.actions,[])
        self.page=Page();self.page.on_delete=lambda page:setattr(page,'selected','BLOCK_B')
        with self.assertRaisesRegex(runner.Stop,'Selected preview changed'):self.run_delete()
        self.assertEqual(self.page.actions,['Delete Block'])

    def test_exact_dialog_and_fresh_target_are_required_before_confirm(self):
        changes=[lambda page:setattr(page,'heading','Delete everything?'),
            lambda page:setattr(page,'warning','Other warning'),
            lambda page:page.snapshots['BLOCK_A'][0].update(heading='Changed target'),
            lambda page:page.inventory.reverse()]
        for changed in changes:
            self.page=Page();self.page.on_delete=changed
            with self.subTest(changed=changed),self.assertRaises(runner.Stop):self.run_delete()
            self.assertEqual(self.page.actions,['Delete Block'])

    def test_captured_heading_accessible_name_contains_question_and_nested_warning(self):
        self.page.dialog=True
        self.assertEqual(deletion._confirm_dialog(self.page)[1].name,'Confirm')
        self.page.heading=deletion._QUESTION
        with self.assertRaisesRegex(runner.Stop,'title or warning'):deletion._confirm_dialog(self.page)

    def test_wrong_removed_uuid_or_survivor_change_stops_before_save(self):
        self.page.actual_removal='BLOCK_B'
        with self.assertRaisesRegex(runner.Stop,'another block'):self.run_delete()
        self.assertEqual(self.page.actions,['Delete Block','Confirm'])
        for collateral in (lambda page:page.snapshots['BLOCK_B'][1].update(content_html='<p>Corrupt rich B</p>'),
                lambda page:page.surroundings['theme'].update(header='Changed header')):
            self.page=Page();self.page.collateral=collateral
            with self.subTest(collateral=collateral),self.assertRaisesRegex(runner.Stop,'protected sibling'):self.run_delete()
            self.assertEqual(self.page.actions,['Delete Block','Confirm'])

    def test_lost_save_requires_reconciliation_without_second_delete(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(runner.Stop,'independent reopen'):self.run_delete()
        self.assertEqual(self.page.actions,['Delete Block','Confirm','Save'])

    def test_schema_refuses_other_types_missing_snapshot_and_combined_changes(self):
        variants=[]
        data=inputs();data['custom_blocks']['deletion']['id']='categoryBlock';variants.append(data)
        data=inputs();data['custom_blocks']['deletion']['action']='remove';variants.append(data)
        data=inputs();data['custom_blocks']['deletion'].pop('expected_content_html');variants.append(data)
        data=inputs();data['custom_blocks']['append']=[];variants.append(data)
        data=inputs();data['custom_blocks']['deletion']['expected_media_url']='javascript:alert(1)';variants.append(data)
        for data in variants:
            with self.subTest(data=data),self.assertRaises(runner.Stop):blocks.validate_inputs(data)
        first=blocks.configuration_hash(inputs())
        data=inputs();data['custom_blocks']['deletion']['expected_content_html']='<p>Other rich content</p>'
        self.assertNotEqual(blocks.configuration_hash(data),first)


class CustomBlockDeletionIntegration(unittest.TestCase):
    def job(self):return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',inputs()),Path('.'))
    def receipt(self,job):
        plan=job['steps'][0]['payload']
        return {'status':'COURSE_BLOCKS_SAVED_AND_REOPENED','editor_url':blocks.theme.editor_url(plan),
            'course_id':plan['course_id'],'template_id':plan['template_id'],
            'configuration_sha256':blocks.configuration_hash(plan),'independent_readback':'VERIFIED',
            'added_block_ids':[],'removed_block_ids':['BLOCK_A'],'block_ids':['categoryBlock','BLOCK_B'],
            'functional_verified':False,'activation_performed':False}

    def test_compiler_primary_fallback_and_replay_keep_one_owned_native_deletion(self):
        job=self.job();self.assertEqual(job['steps'][0]['action'],'native_course_blocks')
        native=__import__('playwright_recipes.course_block_delete',fromlist=['configure'])
        for fallback in (False,True):
            with self.subTest(fallback=fallback),tempfile.TemporaryDirectory() as evidence, \
                    patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=self.receipt(job)) as write:
                provider=Mock()
                for _ in range(2):
                    result=host.run_recipe('courses.configure_ui',inputs(),probes(inputs(),fallback=fallback),evidence,
                        input_dir='.',page=object(),executors={'public_api':provider,'openclaw_extension':provider})
                    self.assertEqual(result['status'],'NEEDS_VERIFICATION')
                write.assert_called_once();provider.assert_not_called()
                self.assertEqual(json.loads(Path(evidence,'state.json').read_text())['results'][0]['result']['removed_block_ids'],['BLOCK_A'])

    def test_original_receipt_binds_exact_removed_uuid_remaining_order_and_full_snapshot_hash(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(job)
        self.assertEqual(editor_replay._result(step,receipt,job)['removed_block_ids'],['BLOCK_A'])
        for change in ({'removed_block_ids':['BLOCK_B']},{'removed_block_ids':[]},
            {'block_ids':['categoryBlock']},{'added_block_ids':['OTHER']},
            {'configuration_sha256':'0'*64},{'activation_performed':True},{'private':'unbound'}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):editor_replay._result(step,{**receipt,**change},job)
        native=__import__('playwright_recipes.course_block_delete',fromlist=['configure'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value={**receipt,'removed_block_ids':['BLOCK_B']}) as write:
            for _ in range(2):
                with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,evidence)
            write.assert_called_once();self.assertEqual(json.loads(Path(evidence,'state.json').read_text())['results'],[])


if __name__=='__main__':unittest.main()
