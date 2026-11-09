"""Native section uploads bind distinct placeholder previews and preserve siblings."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import course_section_media as images
from skill6_playwright import Stop
from test_course_text_blocks import inputs as text_inputs


def inputs(file='/tmp/approved.png',sha='a'*64):
    value=text_inputs();value.pop('text_blocks')
    value['theme_images']={'expected':{
        'hero':{'inspector_url':'https://example.com/hero-inspector.webp','preview_url':'https://example.com/hero-preview.webp'},
        'instructor':{'inspector_url':'https://example.com/empty-profile.svg','preview_url':'https://example.com/user-avatar.svg'}},
        'images':[{'section':'hero','file':file,'sha256':sha}]}
    return value


class SectionSchema(unittest.TestCase):
    def test_explicit_dual_default_urls_unique_sections_and_hash_binding(self):
        data=inputs();self.assertEqual(images.validate_inputs(data),data)
        digest=images.configuration_hash(data);data['theme_images']['images'][0]['file']='/elsewhere/approved.png'
        self.assertEqual(images.configuration_hash(data),digest)
        data['theme_images']['expected']['instructor']['preview_url']='https://example.com/changed.svg'
        self.assertNotEqual(images.configuration_hash(data),digest)
        for change in ('missing_preview','foreign_section','duplicate'):
            data=inputs()
            if change=='missing_preview':data['theme_images']['expected']['instructor'].pop('preview_url')
            elif change=='foreign_section':data['theme_images']['images'][0]['section']='header'
            else:data['theme_images']['images'].append(deepcopy(data['theme_images']['images'][0]))
            with self.subTest(change=change),self.assertRaises(Stop):images.validate_inputs(data)
    def test_original_receipt_never_promotes_old_preview_retargets_or_boolean_proof(self):
        data=inputs();step={'action':'native_course_section_media','payload':data}
        value={'status':'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED','editor_url':images.theme.editor_url(data),
            'course_id':'COURSE','template_id':'TEMPLATE','configuration_sha256':images.configuration_hash(data),
            'independent_readback':'VERIFIED','images':[{'section':'hero','source_sha256':'a'*64,
                'inspector_url_sha256':'b'*64,'preview_url_sha256':'b'*64}],
            'functional_verified':False,'activation_performed':False}
        self.assertEqual(images.validate_receipt(value,step),value)
        invalid=[]
        for change in ({'course_id':'OTHER'},{'editor_url':value['editor_url']+'_OTHER'},
                {'configuration_sha256':'0'*64},{'functional_verified':0},{'activation_performed':True},{'unknown':'unbound'}):
            invalid.append({**value,**change})
        for change in ({'section':'instructor'},{'source_sha256':'c'*64},{'preview_url_sha256':'c'*64},
                {'inspector_url_sha256':images._sha(data['theme_images']['expected']['hero']['inspector_url'])}):
            other=deepcopy(value);other['images'][0].update(change);invalid.append(other)
        for other in invalid:
            with self.subTest(other=other),self.assertRaises(Stop):images.validate_receipt(other,step)


class CapturedControlReaders(unittest.TestCase):
    def test_checkbox_is_the_captured_custom_div_role_not_an_invented_input(self):
        page=MagicMock();flag=page.locator.return_value;flag.count.return_value=1;flag.is_visible.return_value=True
        values={'role':'checkbox','aria-checked':'true'};flag.get_attribute.side_effect=values.get
        self.assertTrue(images._flag(page,'show-hero-checkbox'));flag.is_checked.assert_not_called()
        values['role']='switch'
        with self.assertRaises(Stop):images._flag(page,'show-hero-checkbox')
    def test_exact_swatch_count_and_native_transparency_styles_are_preserved_verbatim(self):
        panel=MagicMock();swatches,sliders,swatch,slider,fill,handle=[MagicMock() for _ in range(6)]
        panel.locator.side_effect=lambda selector:swatches if selector=='.brand-color-value' else sliders
        swatches.count.return_value=1;swatches.nth.return_value=swatch;swatch.count.return_value=1
        swatch.is_visible.return_value=True;swatch.evaluate.return_value='rgb(0, 0, 0)'
        sliders.count.return_value=1;sliders.nth.return_value=slider;slider.is_visible.return_value=True
        slider.locator.side_effect=lambda selector:fill if 'rail__fill' in selector else handle
        fill.count.return_value=1;handle.count.return_value=1
        fill.get_attribute.return_value='left: 0%; width: 65%;';handle.get_attribute.return_value='left: 65%;'
        actual=images._visible_controls(panel,color_count=1,slider_count=1)
        self.assertEqual(actual,{'colors':['rgb(0, 0, 0)'],'sliders':[{'fill_style':'left: 0%; width: 65%;','handle_style':'left: 65%;'}]})
        swatches.count.return_value=2
        with self.assertRaises(Stop):images._visible_controls(panel,color_count=1,slider_count=1)


class SectionWriteBoundaries(unittest.TestCase):
    def execute(self,*,defect=None):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'approved.png';source.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED_BYTES')
            data=inputs(str(source),hashlib.sha256(source.read_bytes()).hexdigest())
            if defect=='source':data['theme_images']['images'][0]['sha256']='0'*64
            initial={section:{**value,'controls':{'colors':['keep'],'sliders':[],
                'visibility':'keep','remove_enabled':False}} for section,value in data['theme_images']['expected'].items()}
            current=deepcopy(initial);page=MagicMock();page.url=images.theme.editor_url(data)
            save=MagicMock();save.count.return_value=1;save.is_visible.return_value=True;dirty={'value':False}
            save.is_enabled.side_effect=lambda:dirty['value'];page.get_by_role.return_value=save
            uploaded=[];saved=[]
            def persist(**kwargs):
                saved.append(True);dirty['value']=False
                if defect=='lost':current['hero']=deepcopy(initial['hero'])
            save.click.side_effect=persist
            def upload(page,plan,path,size,*,inspect,expected_url):
                uploaded.append(path.read_bytes());self.assertEqual(size,len(source.read_bytes()))
                self.assertNotEqual(path,source);self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(inspect(page,plan)[1]['url'],expected_url)
                current['hero'].update(inspector_url='https://cdn.example.com/new.png',preview_url='https://cdn.example.com/new.png')
                current['hero']['controls']['remove_enabled']=True;dirty['value']=True
                if defect=='preview':current['hero']['preview_url']=initial['hero']['preview_url']
                if defect=='color':current['hero']['controls']['colors']=['unexpected']
                if defect=='sibling':current['instructor']['preview_url']='https://cdn.example.com/unrequested.png'
                return {'url':'https://cdn.example.com/new.png'}
            with ExitStack() as stack:
                opened=stack.enter_context(patch.object(images.theme,'_open',return_value=('active','Default Theme')))
                stack.enter_context(patch.object(images.theme,'_identity'))
                stack.enter_context(patch.object(images,'assert_tenant'))
                stack.enter_context(patch.object(images,'_protected',return_value={'body':'protected'}))
                stack.enter_context(patch.object(images,'_snapshot',side_effect=lambda *a:deepcopy(current)))
                stack.enter_context(patch.object(images,'_open_section',side_effect=lambda page,plan,section:(MagicMock(),deepcopy(current[section]))))
                stack.enter_context(patch.object(images,'upload_captured_image',side_effect=upload))
                stack.enter_context(patch.object(images,'wait_until',side_effect=lambda predicate,message:predicate() or (_ for _ in ()).throw(Stop(message))))
                try:result=images.configure(page,{'action':'native_course_section_media','payload':data})
                except Stop as error:result=error
                calls=opened.call_count
            return result,uploaded,saved,current,calls
    def test_actual_approved_source_is_copied_private_and_both_preview_urls_persist(self):
        result,uploaded,saved,current,_=self.execute()
        self.assertEqual(len(uploaded),1);self.assertEqual(len(saved),1)
        self.assertEqual(result['status'],'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED')
        self.assertEqual(current['instructor']['preview_url'],'https://example.com/user-avatar.svg')
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])
    def test_bad_source_stops_before_editor_and_bad_binding_or_sibling_change_stops_before_save(self):
        for defect in ('source','preview','color','sibling'):
            result,uploaded,saved,_,opened=self.execute(defect=defect)
            with self.subTest(defect=defect):
                self.assertIsInstance(result,Stop);self.assertEqual(saved,[])
                if defect=='source':self.assertEqual(uploaded,[]);self.assertEqual(opened,0)
    def test_lost_saved_preview_cannot_claim_independent_native_readback(self):
        result,uploaded,saved,_,_=self.execute(defect='lost')
        self.assertIsInstance(result,Stop);self.assertEqual(len(uploaded),1);self.assertEqual(len(saved),1)


if __name__=='__main__':unittest.main()
