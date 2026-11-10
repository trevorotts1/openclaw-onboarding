"""Native Image Block UUID/order, source, destination and sibling boundaries."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree as ET

import course_image_blocks as images
from skill6_playwright import Stop
from test_course_text_blocks import Dom,inputs as text_inputs,preview_page


def state(identity='IMAGE_A'):
    return {'inspector_url':'https://example.com/old.png','preview_url':'https://example.com/old.png','url':'https://example.com/old-destination'}


def inputs():
    value=text_inputs();value.pop('text_blocks')
    value['image_blocks']={'expected_inventory':[{'id':'categoryBlock','type':'Category Block'},
        {'id':'IMAGE_A','type':'Image Block'},{'id':'TEXT_B','type':'Text Block'}],
        'updates':[{'id':'IMAGE_A','expected':state(),'changes':{'url':'https://example.com/new-destination'}}]}
    return value


def protected(identity='IMAGE_A',src=None):
    return {'preview_attributes':{'alt':'Image block '+identity,'src':src or state()['preview_url'],'class':'native-image'},'remove_enabled':True}


EMPTY={'inspector_url':'https://example.com/placeholder.svg','preview_url':'https://example.com/placeholder.svg'}


class ImageIdentityAndSchema(unittest.TestCase):
    def test_actual_image_alt_uuid_and_full_wrapper_order_bind_the_active_image(self):
        page,owner=preview_page();inventory=inputs()['image_blocks']['expected_inventory']
        node=owner[1][0];node.set('class','native-image-block');node.remove(node[0])
        ET.SubElement(node,'img',{'alt':'Image block IMAGE_A','src':state()['preview_url']})
        self.assertIs(images.text._selected_preview(page,inventory,'IMAGE_A','Image Block').nodes[0],node)
        node[0].set('alt','Image block OTHER_UUID')
        with self.assertRaises(Stop):images.text._selected_preview(page,inventory,'IMAGE_A','Image Block')
    def test_destinations_source_schema_and_inventory_types_are_explicit(self):
        self.assertEqual(images.validate_inputs(inputs())['image_blocks']['append'],[])
        for defect in ('unsafe_url','wrong_type','remove','incomplete_old','unapproved_image'):
            data=inputs();update=data['image_blocks']['updates'][0]
            if defect=='unsafe_url':update['changes']['url']='javascript:alert(1)'
            elif defect=='wrong_type':data['image_blocks']['expected_inventory'][1]['type']='Video Block'
            elif defect=='remove':update['changes']={'remove':True}
            elif defect=='incomplete_old':update['expected'].pop('preview_url')
            else:update['changes']['image']={'file':'relative.png','sha256':'bad'}
            with self.subTest(defect=defect),self.assertRaises(Stop):images.validate_inputs(data)
    def test_url_only_receipt_must_preserve_both_old_images_and_authored_destination(self):
        data=inputs();step={'action':'native_course_image_blocks','payload':data}
        value={'status':'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED','editor_url':images.theme.editor_url(data),
            'course_id':'COURSE','template_id':'TEMPLATE','configuration_sha256':images.configuration_hash(data),
            'independent_readback':'VERIFIED','added_block_ids':[],'block_ids':['categoryBlock','IMAGE_A','TEXT_B'],
            'block_count':3,'images':[{'block_id':'IMAGE_A','source_sha256':None,
                'inspector_url_sha256':images._sha(state()['inspector_url']),'preview_url_sha256':images._sha(state()['preview_url']),
                'url_sha256':images._sha('https://example.com/new-destination')}],
            'functional_verified':False,'activation_performed':False}
        self.assertEqual(images.validate_receipt(value,step),value)
        invalid=[]
        for change in ({'block_count':True},{'course_id':'OTHER'},{'functional_verified':0},
                {'block_ids':['categoryBlock','TEXT_B','IMAGE_A']},{'added_block_ids':['IMAGE_A']},{'extra':'unbound'}):
            invalid.append({**value,**change})
        for change in ({'block_id':'OTHER'},{'source_sha256':'a'*64},
                {'preview_url_sha256':'b'*64},{'url_sha256':images._sha(state()['url'])}):
            other=deepcopy(value);other['images'][0].update(change);invalid.append(other)
        for other in invalid:
            with self.subTest(other=other),self.assertRaises(Stop):images.validate_receipt(other,step)
    def test_removal_requires_inventoried_empty_urls_and_excludes_upload(self):
        data=inputs();changes=data['image_blocks']['updates'][0]['changes'];changes.clear()
        changes['remove_image']=deepcopy(EMPTY)
        self.assertEqual(images.validate_inputs(data)['image_blocks']['updates'][0]['changes'],changes)
        for removal in (True,{},state(),{'inspector_url':state()['inspector_url'],'preview_url':state()['preview_url']},
                {**EMPTY,'preview_url':'https://example.com/different.svg'}):
            other=deepcopy(data);other['image_blocks']['updates'][0]['changes']['remove_image']=removal
            with self.subTest(removal=removal),self.assertRaises(Stop):images.validate_inputs(other)
        other=deepcopy(data);other['image_blocks']['updates'][0]['changes']['image']={'file':'/tmp/approved.png','sha256':'a'*64}
        with self.assertRaises(Stop):images.validate_inputs(other)


class NativeDestinationWriter(unittest.TestCase):
    def test_correct_selected_image_preview_cannot_bless_a_stale_other_type_inspector(self):
        page=MagicMock();inventory=inputs()['image_blocks']['expected_inventory']
        row=MagicMock();row.count.return_value=1;row.is_visible.return_value=True;page.locator.return_value=row
        row.locator.return_value.count.return_value=1
        preview=MagicMock();image=preview.locator.return_value;image.count.return_value=1;image.is_visible.return_value=True
        page.get_by_text.return_value.count.return_value=0
        with patch.object(images.blocks,'_inventory',return_value=inventory), \
                patch.object(images.text,'_preview_order'),patch.object(images.text,'_selected_preview',return_value=preview), \
                self.assertRaisesRegex(Stop,'inspector heading'):
            images._open(page,{},'IMAGE_A')
    def test_url_only_writer_uses_the_reselected_bound_inspector_and_keeps_image_attributes(self):
        page=MagicMock();current=state();keep=protected();field=MagicMock()
        field.count.return_value=1;field.is_visible.return_value=True
        field.input_value.side_effect=lambda:current['url'];field.fill.side_effect=lambda value:current.__setitem__('url',value)
        page.get_by_placeholder.return_value=field
        with patch.object(images,'read_image_block',side_effect=lambda *a:(deepcopy(current),deepcopy(keep))), \
                patch.object(images,'_open') as select,patch.object(images.theme,'_identity'),patch.object(images,'assert_tenant'):
            result=images._write(page,{},'IMAGE_A',{'url':'https://example.com/new'})
        select.assert_called_once();self.assertEqual(result[0]['url'],'https://example.com/new');self.assertEqual(result[1],keep)
    def test_removal_needs_disabled_remove_and_preserves_bound_image_attributes(self):
        for defect in (None,'enabled','wrong_placeholder','attribute'):
            current=state();keep=protected();page=MagicMock();remove=MagicMock()
            remove.count.return_value=1;remove.is_visible.return_value=True;remove.is_enabled.return_value=True
            def remove_image(**kwargs):
                current.update(EMPTY);keep['preview_attributes']['src']=EMPTY['preview_url'];keep['remove_enabled']=defect=='enabled'
                if defect=='wrong_placeholder':current['preview_url']='https://example.com/other.png'
                if defect=='attribute':keep['preview_attributes']['class']='unrequested-change'
            remove.click.side_effect=remove_image;page.get_by_role.return_value=remove
            with patch.object(images,'read_image_block',side_effect=lambda *a:(deepcopy(current),deepcopy(keep))), \
                    patch.object(images,'_open'),patch.object(images.theme,'_identity'),patch.object(images,'assert_tenant'), \
                    patch.object(images,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))):
                with self.subTest(defect=defect):
                    if defect:
                        with self.assertRaises(Stop):images._write(page,{},'IMAGE_A',{'remove_image':EMPTY})
                    else:
                        result=images._write(page,{},'IMAGE_A',{'remove_image':EMPTY})
                        self.assertEqual(result[0],{**state(),**EMPTY});self.assertIs(result[1]['remove_enabled'],False)
            self.assertEqual(remove.click.call_count,1)


class ImageWriteBoundaries(unittest.TestCase):
    def execute(self,*,defect=None,append=False,upload=False,remove=False):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'approved.png';file.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED_IMAGE_BYTES')
            asset={'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
            data=inputs()
            if upload:data['image_blocks']['updates'][0]['changes']['image']=asset
            if remove:data['image_blocks']['updates'][0]['changes']={'remove_image':deepcopy(EMPTY)}
            if append:data['image_blocks']['append']=[{'image':asset,'url':'https://example.com/append'}]
            if defect=='source':data['image_blocks']['append'][0]['image']['sha256']='0'*64
            if defect=='stale':data['image_blocks']['updates'][0]['expected']['url']='https://example.com/stale'
            inventory=deepcopy(data['image_blocks']['expected_inventory'])
            current={'IMAGE_A':(state(),protected()),'TEXT_B':({'content':'Keep text'},{'content_html':'<p><strong>Keep text</strong></p>','preview_style':'keep colors'})}
            original=deepcopy(current);writes=[];saves=[];dirty={'value':False};page=MagicMock();page.url=images.theme.editor_url(data)
            save=MagicMock();save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.side_effect=lambda:dirty['value']
            def persist(**kwargs):
                saves.append(True);dirty['value']=False
                if defect=='lost':current['IMAGE_A']=original['IMAGE_A']
            save.click.side_effect=persist
            def controls(role,*,name,exact):
                if name=='Save':return save
                control=MagicMock();control.count.return_value=1;control.is_visible.return_value=True
                if name=='Image Block':
                    def add(**kwargs):
                        inventory.append({'id':'NEW_IMAGE','type':'Image Block'})
                        current['NEW_IMAGE']=({'inspector_url':'https://example.com/placeholder.svg','preview_url':'https://example.com/placeholder.svg','url':''},
                            {**protected('NEW_IMAGE','https://example.com/placeholder.svg'),'remove_enabled':False});dirty['value']=True
                    control.click.side_effect=add
                return control
            page.get_by_role.side_effect=controls
            def write(page,plan,identity,changes,path=None,size=None):
                writes.append(identity);dirty['value']=True
                actual,keep=deepcopy(current[identity])
                if 'image' in changes:
                    self.assertEqual(path.read_bytes(),file.read_bytes());self.assertEqual(size,len(file.read_bytes()))
                    self.assertNotEqual(path,file);self.assertEqual(path.stat().st_mode&0o777,0o600)
                    actual.update(inspector_url='https://cdn.example.com/'+identity+'.png',preview_url='https://cdn.example.com/'+identity+'.png')
                    keep['preview_attributes']['src']=actual['preview_url'];keep['remove_enabled']=True
                if 'remove_image' in changes:
                    actual.update(changes['remove_image']);keep['preview_attributes']['src']=actual['preview_url'];keep['remove_enabled']=False
                actual['url']=changes.get('url',actual['url']);current[identity]=(actual,keep)
                if defect=='sibling':current['TEXT_B'][1]['content_html']='<p>Unauthorized sibling edit</p>'
                return deepcopy(current[identity])
            with ExitStack() as stack:
                opened=stack.enter_context(patch.object(images.theme,'_open',return_value=('active','Default Theme')))
                for owner,name,implementation in ((images.theme,'_snapshot',lambda *a:{'protected':'theme'}),
                        (images.theme,'_identity',lambda *a:None),(images,'assert_tenant',lambda *a:None),
                        (images.blocks,'_inventory',lambda *a:deepcopy(inventory)),
                        (images.blocks,'_snapshot',lambda *a:deepcopy(current)),
                        (images.text,'_preview_order',lambda *a:None),
                        (images,'read_image_block',lambda page,plan,identity:deepcopy(current[identity])),
                        (images,'_write',write),(images,'wait_until',lambda predicate,message:predicate() or (_ for _ in ()).throw(Stop(message)))):
                    stack.enter_context(patch.object(owner,name,side_effect=implementation))
                try:result=images.configure(page,{'action':'native_course_image_blocks','payload':data})
                except Stop as error:result=error
                opened_count=opened.call_count
            return result,writes,saves,current,opened_count
    def test_approved_png_append_binds_new_uuid_and_preserves_existing_text_rich_markup(self):
        result,writes,saves,current,_=self.execute(append=True,upload=True)
        self.assertEqual(result['added_block_ids'],['NEW_IMAGE']);self.assertEqual(result['block_count'],4)
        self.assertEqual(writes,['IMAGE_A','NEW_IMAGE']);self.assertEqual(len(saves),1)
        self.assertEqual(current['TEXT_B'][1]['content_html'],'<p><strong>Keep text</strong></p>')
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])
    def test_bad_later_source_or_stale_expected_prevents_first_write(self):
        for defect in ('source','stale'):
            result,writes,saves,_,opened=self.execute(append=True,defect=defect)
            with self.subTest(defect=defect):
                self.assertIsInstance(result,Stop);self.assertEqual(writes,[]);self.assertEqual(saves,[])
                if defect=='source':self.assertEqual(opened,0)
    def test_collateral_sibling_change_and_lost_saved_state_cannot_be_completion(self):
        for defect in ('sibling','lost'):
            result,_,saves,_,_=self.execute(defect=defect)
            with self.subTest(defect=defect):
                self.assertIsInstance(result,Stop);self.assertEqual(len(saves),int(defect=='lost'))
    def test_removal_saves_once_reopens_and_does_not_delete_block_or_change_destination(self):
        result,writes,saves,current,opened=self.execute(remove=True)
        self.assertEqual(writes,['IMAGE_A']);self.assertEqual(len(saves),1);self.assertEqual(opened,2)
        self.assertEqual(result['block_ids'],['categoryBlock','IMAGE_A','TEXT_B'])
        self.assertIs(result['images'][0]['media_removed'],True)
        self.assertEqual(current['IMAGE_A'][0],{**state(),**EMPTY})
        self.assertIs(current['IMAGE_A'][1]['remove_enabled'],False)
        data=inputs();data['image_blocks']['updates'][0]['changes']={'remove_image':deepcopy(EMPTY)}
        for key,value in (('media_removed',False),('inspector_url_sha256',images._sha(state()['inspector_url']))):
            other=deepcopy(result);other['images'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Stop):images.validate_receipt(other,{'payload':data})
    def test_removal_lost_on_reopen_cannot_emit_completion(self):
        result,writes,saves,_,_=self.execute(remove=True,defect='lost')
        self.assertIsInstance(result,Stop);self.assertEqual(writes,['IMAGE_A']);self.assertEqual(len(saves),1)


if __name__=='__main__':unittest.main()
