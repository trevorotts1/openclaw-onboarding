"""Inactive template Custom Block contracts and sibling/readback boundaries."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import course_blocks as blocks
from skill6_playwright import Stop


def values(heading='Authored heading'):
    return {'heading':heading,'content':'Authored plain text.','button_text':'Continue',
        'button_url':'https://example.com/next','button_visibility':'show',
        'button_type':'solid','button_alignment':'left'}


def inputs():
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'custom_blocks':{'expected_inventory':[{'id':'categoryBlock','type':'Category Block'},
            {'id':'BLOCK_A','type':'Custom Block'},{'id':'BLOCK_B','type':'Custom Block'}],
            'updates':[{'id':'BLOCK_A','expected':values('Previous A'),
                'changes':{'heading':'New A'},'plain_text_content':True}]}}


class Control:
    def __init__(self,page,name):self.page=page;self.name=name
    def count(self):return 1
    def wait_for(self,**kwargs):pass
    def is_visible(self):return True
    def is_enabled(self):return self.page.dirty
    def click(self,**kwargs):
        if self.name=='Save':
            self.page.saves+=1;self.page.dirty=False
            if self.page.lose_save:self.page.values['BLOCK_A']['heading']='Previous A'
        elif self.name=='Custom Block':
            self.page.inventory.append({'id':'GENERATED_UUID','type':'Custom Block'})
            self.page.values['GENERATED_UUID']=values('Heading')
            self.page.dirty=True


class Page:
    url='https://example.com/editor'
    def __init__(self):
        self.inventory=deepcopy(inputs()['custom_blocks']['expected_inventory'])
        self.values={'BLOCK_A':values('Previous A'),'BLOCK_B':values('Previous B')}
        self.dirty=False;self.saves=0;self.lose_save=False;self.collateral=False;self.writes=[]
    def get_by_role(self,role,*,name,exact):return Control(self,name)
    def wait_for_load_state(self,*args,**kwargs):pass


class CourseBlockTests(unittest.TestCase):
    def setUp(self):
        self.page=Page()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        def mocked(target,**kwargs):return self.stack.enter_context(patch.object(blocks,target,**kwargs))
        self.stack.enter_context(patch.object(blocks.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(blocks.theme,'_snapshot',return_value={'keep':'protected theme'}))
        self.stack.enter_context(patch.object(blocks.theme,'_identity'))
        mocked('assert_tenant')
        mocked('_inventory',side_effect=lambda page,plan:deepcopy(page.inventory))
        mocked('_read_block',side_effect=lambda page,plan,identity:
            (deepcopy(page.values[identity]),{'content_html':'<p>Keep markup</p>','media_src':'https://example.com/keep.png'}))
        def write(page,plan,identity,changes):
            page.writes.append(identity);page.values[identity].update(changes);page.dirty=True
            if page.collateral:page.values['BLOCK_B']['heading']='Unexpected sibling edit'
            return blocks._read_block(page,plan,identity)
        mocked('_write_block',side_effect=write)
        mocked('wait_until',side_effect=lambda fn,message: fn() or (_ for _ in ()).throw(Stop(message)))

    def test_edit_preserves_all_siblings_and_independent_reopen(self):
        result=blocks.configure(self.page,{'payload':inputs()})
        self.assertEqual(result['status'],'COURSE_BLOCKS_SAVED_AND_REOPENED')
        self.assertEqual(self.page.values['BLOCK_B'],values('Previous B'))
        self.assertEqual(self.page.saves,1)
        self.assertFalse(result['functional_verified'])
        self.assertFalse(result['activation_performed'])

    def test_later_stale_target_prevents_first_edit(self):
        data=inputs();data['custom_blocks']['updates'].append({'id':'BLOCK_B',
            'expected':values('Wrong previous B'),'changes':{'heading':'New B'},'plain_text_content':True})
        with self.assertRaisesRegex(Stop,'expected previous'):
            blocks.configure(self.page,{'payload':data})
        self.assertEqual(self.page.writes,[])
        self.assertEqual(self.page.saves,0)

    def test_collateral_sibling_edit_and_lost_save_cannot_pass(self):
        for flag in ('collateral','lose_save'):
            page=Page();setattr(page,flag,True)
            with self.subTest(flag=flag),self.assertRaises(Stop):
                blocks.configure(page,{'payload':inputs()})
            self.assertEqual(page.saves,0 if flag=='collateral' else 1)

    def test_append_binds_generated_native_id_and_preserves_existing_order(self):
        data=inputs();data['custom_blocks'].pop('updates');data['custom_blocks']['append']=[values('New block')]
        result=blocks.configure(self.page,{'payload':data})
        self.assertEqual(result['added_block_ids'],['GENERATED_UUID'])
        self.assertEqual(result['block_ids'],['categoryBlock','BLOCK_A','BLOCK_B','GENERATED_UUID'])
        self.assertEqual(self.page.values['GENERATED_UUID'],values('New block'))

    def test_inventory_drift_stops_before_edit(self):
        self.page.inventory.reverse()
        with self.assertRaisesRegex(Stop,'inventory is stale'):
            blocks.configure(self.page,{'payload':inputs()})
        self.assertEqual(self.page.writes,[])

    def test_input_rejects_ambiguous_identity_html_ack_unsupported_fields_and_urls(self):
        variants=[]
        data=inputs();data['custom_blocks']['updates'][0]['plain_text_content']=False;variants.append(data)
        data=inputs();data['custom_blocks']['updates'][0]['changes']['button_url']='javascript:alert(1)';variants.append(data)
        data=inputs();data['custom_blocks']['updates'][0]['changes']['media_file']='image.png';variants.append(data)
        data=inputs();data['custom_blocks']['expected_inventory'][1]['id']='categoryBlock';variants.append(data)
        data=inputs();data['custom_blocks']['expected_inventory'][1]['type']='Video Block';variants.append(data)
        for data in variants:
            with self.subTest(data=data),self.assertRaises(Stop):blocks.validate_inputs(data)

    def test_hash_binds_sibling_order_exact_target_and_authored_content(self):
        data=inputs();original=blocks.configuration_hash(data)
        data['custom_blocks']['expected_inventory'][1:]=reversed(data['custom_blocks']['expected_inventory'][1:])
        self.assertNotEqual(blocks.configuration_hash(data),original)
        data=inputs();data['custom_blocks']['updates'][0]['changes']['heading']='Different heading'
        self.assertNotEqual(blocks.configuration_hash(data),original)

    def test_selected_inspector_requires_exact_unique_active_preview_uuid(self):
        selected=Mock();selected.count.return_value=1;selected.is_visible.return_value=True
        page=Mock();page.locator.return_value=selected
        selected.get_attribute.return_value='custom-block-BLOCK_A'
        self.assertTrue(blocks._selected(page,'BLOCK_A'))
        self.assertFalse(blocks._selected(page,'BLOCK_B'))
        selected.count.return_value=2
        self.assertFalse(blocks._selected(page,'BLOCK_A'))


if __name__=='__main__':unittest.main()
