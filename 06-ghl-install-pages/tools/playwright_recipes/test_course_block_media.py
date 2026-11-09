"""Custom Block media authoring preserves exact UUID content and siblings."""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import course_block_media as media
from skill6_playwright import Stop


def inputs(path):
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'custom_block_image':{'block_id':'BLOCK_A','expected_inventory':[
            {'id':'categoryBlock','type':'Category Block'},{'id':'BLOCK_A','type':'Custom Block'},
            {'id':'BLOCK_B','type':'Custom Block'}],
            'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'expected_url':'https://example.com/old.png'}}


class Save:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return self.page.dirty
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        self.page.saves+=1;self.page.dirty=False
        if self.page.lose_save:self.page.protected=deepcopy(self.page.original)


class Page:
    url='https://example.com/editor'
    def __init__(self,data):
        self.protected={'theme':{'title':'Keep theme'},'inventory':deepcopy(data['custom_block_image']['expected_inventory']),
            'blocks':{'BLOCK_A':({'heading':'Keep A'},{'content_html':'<p>Keep A HTML</p>','media_src':'https://example.com/old.png'}),
                'BLOCK_B':({'heading':'Keep B'},{'content_html':'<p>Keep B HTML</p>','media_src':'https://example.com/keep.png'})}}
        self.original=deepcopy(self.protected);self.saves=0;self.dirty=False;self.lose_save=False
    def get_by_role(self,role,*,name,exact):return Save(self)
    def wait_for_load_state(self,*args,**kwargs):pass


class CourseBlockMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.file=Path(self.directory.name)/'approved.png';self.file.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
        self.data=inputs(self.file);self.page=Page(self.data)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(media.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(media.theme,'_identity'))
        self.stack.enter_context(patch.object(media,'assert_tenant'))
        self.stack.enter_context(patch.object(media,'_protected',side_effect=lambda page,plan:deepcopy(page.protected)))
        self.stack.enter_context(patch.object(media,'_image',side_effect=lambda page,plan:(None,
            {'url':page.protected['blocks']['BLOCK_A'][1]['media_src'],'block_id':'BLOCK_A'})))
        def upload(page,plan,path,size,*,inspect,expected_url):
            self.assertEqual(path.read_bytes(),self.file.read_bytes())
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(expected_url,'https://example.com/old.png')
            page.protected['blocks']['BLOCK_A'][1]['media_src']='https://example.com/new.png';page.dirty=True
            return {'url':'https://example.com/new.png','block_id':'BLOCK_A'}
        self.upload=self.stack.enter_context(patch.object(media.uploads,'upload_captured_image',side_effect=upload))
        self.stack.enter_context(patch.object(media,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))))

    def run_media(self):return media.configure(self.page,{'payload':self.data})

    def test_exact_image_uuid_reopen_preserves_text_html_siblings_and_pending_proof(self):
        result=self.run_media()
        self.assertEqual(result['status'],'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED')
        self.assertEqual(result['block_id'],'BLOCK_A');self.assertEqual(self.page.saves,1)
        self.assertEqual(self.page.protected['blocks']['BLOCK_B'],self.page.original['blocks']['BLOCK_B'])
        self.assertEqual(self.page.protected['blocks']['BLOCK_A'][0],{'heading':'Keep A'})
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])

    def test_stale_target_image_or_inventory_prevents_upload(self):
        self.page.protected['inventory'].reverse()
        with self.assertRaisesRegex(Stop,'inventory is stale'):self.run_media()
        self.upload.assert_not_called()
        self.page.protected=deepcopy(self.page.original)
        self.page.protected['blocks']['BLOCK_A'][1]['media_src']='https://example.com/different.png'
        with self.assertRaisesRegex(Stop,'previous URL'):self.run_media()
        self.upload.assert_not_called()

    def test_file_source_changed_prevents_browser_upload(self):
        self.file.write_bytes(b'\x89PNG\r\n\x1a\nCHANGED')
        with self.assertRaisesRegex(Stop,'approved PNG hash'):self.run_media()
        self.upload.assert_not_called()

    def test_collateral_text_change_stops_before_save(self):
        original=self.upload.side_effect
        def collateral(*args,**kwargs):
            result=original(*args,**kwargs);args[0].protected['blocks']['BLOCK_B'][0]['heading']='Corrupt sibling'
            return result
        self.upload.side_effect=collateral
        with self.assertRaisesRegex(Stop,'protected block/theme'):self.run_media()
        self.assertEqual(self.page.saves,0)

    def test_lost_save_cannot_claim_independent_readback(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(Stop,'independent reopen'):self.run_media()

    def test_target_must_be_unique_existing_custom_block_and_hash_binds_identity(self):
        original=media.configuration_hash(self.data)
        data=deepcopy(self.data);data['custom_block_image']['block_id']='BLOCK_B'
        self.assertNotEqual(media.configuration_hash(data),original)
        data['custom_block_image']['block_id']='categoryBlock'
        with self.assertRaises(Stop):media.validate_inputs(data)
        data=deepcopy(self.data);data['custom_block_image']['expected_inventory'].append({'id':'BLOCK_A','type':'Custom Block'})
        with self.assertRaises(Stop):media.validate_inputs(data)


if __name__=='__main__':unittest.main()
