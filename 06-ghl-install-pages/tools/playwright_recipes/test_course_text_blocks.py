"""UUID-less native Text previews need complete order/selection proof."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree as ET

import course_blocks as blocks
import course_text_blocks as text
from skill6_playwright import Stop


def inputs():
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'text_blocks':{'expected_inventory':[{'id':'categoryBlock','type':'Category Block'},
            {'id':'TEXT_A','type':'Text Block'},{'id':'TEXT_B','type':'Text Block'}],
            'updates':[{'id':'TEXT_A','expected_content':'Previous A','content':'Authored A','plain_text_content':True}]}}


class Dom:
    def __init__(self,nodes):self.nodes=nodes
    def count(self):return len(self.nodes)
    def is_visible(self):return bool(self.nodes)
    def nth(self,index):return Dom([self.nodes[index]])
    def get_attribute(self,key):return self.nodes[0].get(key)
    def locator(self,selector):
        if selector==':scope > div':
            return Dom([child for node in self.nodes for child in node if child.tag=='div'])
        if selector.startswith('.'):
            classes=selector[1:].split('.')
            return Dom([child for node in self.nodes for child in node.iter() if child is not node
                and set(classes).issubset(child.get('class','').split())])
        if selector.startswith('img[alt="') and selector.endswith('"]'):
            value=selector[len('img[alt="'):-2]
            return Dom([child for node in self.nodes for child in node.iter()
                if child.tag=='img' and child.get('alt')==value])
        raise AssertionError(selector)


def preview_page():
    owner=ET.Element('div',{'class':'col-span-9 flex flex-col gap-4'})
    for kind,selected in (('Category Block',False),('Text Block',True),('Text Block',False)):
        wrapper=ET.SubElement(owner,'div')
        block=ET.SubElement(wrapper,'div',{'inbody':'true','data-active':str(selected).lower(),
            'class':'text-block' if kind=='Text Block' else '',
            'style':'--text-background-color: #FEFEFF; --text-color: #1D2939;'})
        if kind=='Category Block':ET.SubElement(block,'div',{'class':'category-list-block','id':'unrelated-native-category-uuid'})
        else:ET.SubElement(block,'div',{'class':'editor-content rich-text-viewer'}).text='Identical text'
    page=MagicMock()
    page.locator.side_effect=lambda selector:Dom([owner]) if selector==text.PREVIEW_OWNER else (_ for _ in ()).throw(AssertionError(selector))
    return page,owner


class NativeOrderBinding(unittest.TestCase):
    def test_identical_uuidless_text_content_is_bound_by_full_sidebar_order_and_unique_active_preview(self):
        page,owner=preview_page();inventory=inputs()['text_blocks']['expected_inventory']
        result=text._selected_preview(page,inventory,'TEXT_A')
        self.assertIs(result.nodes[0],owner[1][0]);self.assertIsNone(result.get_attribute('id'))
        with self.assertRaises(Stop):text._selected_preview(page,inventory,'TEXT_B')
    def test_extra_wrapper_wrong_type_order_or_multiple_active_blocks_are_not_identity(self):
        for defect in ('extra','order','active','child'):
            page,owner=preview_page()
            if defect=='extra':ET.SubElement(owner,'div')
            elif defect=='order':owner[0][0].set('class','text-block')
            elif defect=='active':owner[2][0].set('data-active','true')
            else:ET.SubElement(owner[1],'div')
            with self.subTest(defect=defect),self.assertRaises(Stop):
                text._selected_preview(page,inputs()['text_blocks']['expected_inventory'],'TEXT_A')


class TextSchemaAndReceipts(unittest.TestCase):
    def test_capture_limits_plain_replacement_ack_and_complete_target_type(self):
        self.assertEqual(text.validate_inputs(inputs())['text_blocks']['append'],[])
        changes=[]
        value=inputs();value['text_blocks']['updates'][0]['content']='x'*2501;changes.append(value)
        value=inputs();value['text_blocks']['updates'][0]['plain_text_content']=False;changes.append(value)
        value=inputs();value['text_blocks']['updates'][0]['colors']={};changes.append(value)
        value=inputs();value['text_blocks']['expected_inventory'][1]['type']='Video Block';changes.append(value)
        value=inputs();value['text_blocks']['updates'][0]['id']='categoryBlock';changes.append(value)
        for value in changes:
            with self.subTest(value=value),self.assertRaises(Stop):text.validate_inputs(value)
    def test_original_receipt_binds_course_template_inputs_old_order_new_ids_and_proof_flags(self):
        data=inputs();data['text_blocks']['append']=[{'content':'New plain block'}]
        plan=text.validate_inputs(data);step={'action':'native_course_text_blocks','payload':data}
        value={'status':'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED','editor_url':text.theme.editor_url(plan),
            'course_id':'COURSE','template_id':'TEMPLATE','configuration_sha256':text.configuration_hash(data),
            'independent_readback':'VERIFIED','added_block_ids':['NEW_TEXT'],
            'block_ids':['categoryBlock','TEXT_A','TEXT_B','NEW_TEXT'],'block_count':4,
            'functional_verified':False,'activation_performed':False}
        self.assertEqual(text.validate_receipt(value,step),value)
        for change in ({'course_id':'OTHER'},{'template_id':'OTHER'},{'configuration_sha256':'0'*64},
                {'editor_url':value['editor_url']+'_OTHER'},{'block_count':True},
                {'block_ids':['categoryBlock','TEXT_B','TEXT_A','NEW_TEXT']},
                {'added_block_ids':['TEXT_A']},{'block_ids':['categoryBlock','TEXT_A','TEXT_B','TEXT_A']},
                {'functional_verified':0},{'activation_performed':True},{'surprise':'unbound'}):
            with self.subTest(change=change),self.assertRaises(Stop):text.validate_receipt({**value,**change},step)


class TextWriteBoundaries(unittest.TestCase):
    def run_native(self,*,stale=False,collateral=False,lost=False,append=False):
        data=inputs();plan=text.validate_inputs(data);inventory=deepcopy(plan['text_blocks']['expected_inventory'])
        states={identity:({'content':content},{'content_html':'<p>'+content+'</p>','preview_style':'original colors'})
            for identity,content in (('TEXT_A','Previous A'),('TEXT_B','Previous B'))}
        before=deepcopy(states);writes=[];saves=[]
        if stale:
            data['text_blocks']['updates'].append({'id':'TEXT_B','expected_content':'STALE','content':'New B','plain_text_content':True})
        if append:data['text_blocks']['append']=[{'content':'Appended content'}]
        page=MagicMock();save=MagicMock();dirty={'value':False}
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.side_effect=lambda:dirty['value']
        def control(role,*,name,exact):
            if name=='Save':return save
            value=MagicMock();value.count.return_value=1;value.is_visible.return_value=True
            if name=='Text Block':
                def add(**kwargs):
                    inventory.append({'id':'NEW_TEXT','type':'Text Block'});states['NEW_TEXT']=({'content':''},{'content_html':'<p></p>','preview_style':'original colors'});dirty['value']=True
                value.click.side_effect=add
            return value
        page.get_by_role.side_effect=control
        def persist(**kwargs):
            saves.append(True);dirty['value']=False
            if lost:states['TEXT_A']=before['TEXT_A']
        save.click.side_effect=persist
        def write(page,plan,identity,content):
            writes.append(identity);dirty['value']=True
            states[identity]=({'content':content},{'content_html':'<p>'+content+'</p>','preview_style':'original colors'})
            if collateral:states['TEXT_B'][1]['content_html']='<p>Unexpected rich sibling change</p>'
            return deepcopy(states[identity])
        with ExitStack() as stack:
            for owner,name,value in ((text.theme,'_open',lambda *a:('active','Default Theme')),
                    (text.theme,'_snapshot',lambda *a:{'theme':'protected'}),(text.theme,'_identity',lambda *a:None),
                    (text,'assert_tenant',lambda *a:None),(blocks,'_inventory',lambda *a:deepcopy(inventory)),
                    (blocks,'_snapshot',lambda *a:deepcopy(states)),(text,'_preview_order',lambda *a:None),
                    (text,'read_text_block',lambda page,plan,identity:deepcopy(states[identity])),
                    (text,'_write',write),(text,'wait_until',lambda predicate,message:predicate() or (_ for _ in ()).throw(Stop(message)))):
                stack.enter_context(patch.object(owner,name,side_effect=value))
            try:result=text.configure(page,{'action':'native_course_text_blocks','payload':data})
            except Stop as error:result=error
        return result,writes,saves,states
    def test_later_stale_target_prevents_first_content_write(self):
        result,writes,saves,_=self.run_native(stale=True)
        self.assertIsInstance(result,Stop);self.assertEqual(writes,[]);self.assertEqual(saves,[])
    def test_rich_sibling_change_stops_before_save_and_lost_save_is_not_completion(self):
        for kind in ('collateral','lost'):
            result,_,saves,_=self.run_native(**{kind:True})
            self.assertIsInstance(result,Stop);self.assertEqual(len(saves),int(kind=='lost'))
    def test_append_binds_native_delta_and_readback_retains_old_order_and_colors(self):
        result,writes,saves,states=self.run_native(append=True)
        self.assertEqual(result['added_block_ids'],['NEW_TEXT']);self.assertEqual(result['block_count'],4)
        self.assertEqual(writes,['TEXT_A','NEW_TEXT']);self.assertEqual(len(saves),1)
        self.assertEqual(states['TEXT_B'][1]['content_html'],'<p>Previous B</p>')
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])


if __name__=='__main__':unittest.main()
