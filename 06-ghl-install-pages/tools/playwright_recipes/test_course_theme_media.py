"""Native inactive-template background uploads remain exact and proof-pending."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import course_theme_media as media
from skill6_playwright import Stop


def inputs(path):
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'background_image':{'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'expected_url':'https://example.com/old.svg'}}


class Save:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def wait_for(self,**kwargs):pass
    def is_enabled(self):return self.page.dirty
    def click(self,**kwargs):
        self.page.dirty=False;self.page.saves+=1
        if self.page.lose_save:self.page.background['url']='https://example.com/old.svg'


class Page:
    url='https://example.com/template'
    def __init__(self):
        self.background={'url':'https://example.com/old.svg',
            'transparency':{'fill_style':'width: 0%;','handle_style':'left: 0%;'}}
        self.protected={'theme':{'heading':'Keep'},'body_inventory':[{'id':'categoryBlock','type':'Category Block'}]}
        self.dirty=False;self.saves=0;self.lose_save=False
    def get_by_role(self,role,*,name,exact):return Save(self)
    def wait_for_load_state(self,*args,**kwargs):pass


class CourseThemeMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.file=Path(self.directory.name)/'source.png';self.file.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED_BYTES')
        self.plan=inputs(self.file);self.page=Page();self.page.url=media.theme.editor_url(self.plan)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.open=self.stack.enter_context(patch.object(media.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(media.theme,'_identity'))
        self.stack.enter_context(patch.object(media,'assert_tenant'))
        self.stack.enter_context(patch.object(media,'_protected',side_effect=lambda page,plan:deepcopy(page.protected)))
        self.stack.enter_context(patch.object(media,'_background',side_effect=lambda page,plan:(None,deepcopy(page.background))))
        self.stack.enter_context(patch.object(media,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(Stop(message))))
        def upload(page,plan,path,size):
            self.assertEqual(path.read_bytes(),self.file.read_bytes())
            self.assertEqual(size,len(self.file.read_bytes()))
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            page.background['url']='https://example.com/uploaded.png';page.dirty=True
            return deepcopy(page.background)
        self.upload=self.stack.enter_context(patch.object(media,'_upload',side_effect=upload))

    def run_background(self):return media.configure(self.page,{'payload':self.plan})

    def test_upload_uses_approved_private_copy_and_exact_independent_readback(self):
        result=self.run_background()
        self.assertEqual(result['status'],'COURSE_THEME_MEDIA_SAVED_AND_REOPENED')
        self.assertEqual(result['source_sha256'],self.plan['background_image']['sha256'])
        self.assertEqual(self.open.call_count,2)
        self.assertEqual(self.page.saves,1)
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])

    def test_stale_preview_or_changed_file_stops_before_upload(self):
        self.page.background['url']='https://example.com/different.png'
        with self.assertRaisesRegex(Stop,'inventoried previous'):self.run_background()
        self.upload.assert_not_called()
        self.file.write_bytes(b'\x89PNG\r\n\x1a\nDIFFERENT')
        with self.assertRaisesRegex(Stop,'approved PNG hash'):self.run_background()
        self.upload.assert_not_called()

    def test_ten_mebibyte_source_stops_before_browser(self):
        with patch.object(media.media,'_bytes',return_value=b'x'*(10*1024*1024)):
            with self.assertRaisesRegex(Stop,'smaller than 10'):self.run_background()
        self.open.assert_not_called()

    def test_lost_save_or_protected_body_change_never_reports_success(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(Stop,'independent reopen'):self.run_background()
        self.page=Page();self.page.url=media.theme.editor_url(self.plan)
        def collateral(page,plan,path,size):
            page.background['url']='https://example.com/new.png';page.dirty=True
            page.protected['body_inventory'].append({'id':'unexpected','type':'Custom Block'})
            return deepcopy(page.background)
        self.upload.side_effect=collateral
        with self.assertRaisesRegex(Stop,'protected theme/body'):self.run_background()
        self.assertEqual(self.page.saves,0)

    def test_hash_binds_asset_and_old_url_but_not_materialization_path(self):
        before=media.configuration_hash(self.plan)
        data=deepcopy(self.plan);data['background_image']['file']='/different/local/path.png'
        self.assertEqual(media.configuration_hash(data),before)
        data['background_image']['expected_url']='https://example.com/different.png'
        self.assertNotEqual(media.configuration_hash(data),before)

    def test_unsupported_media_kind_and_publish_are_refused(self):
        data=deepcopy(self.plan);data['publish']=True
        with self.assertRaises(Stop):media.validate_inputs(data)
        data=deepcopy(self.plan);data['background_image']['transparency']=50
        with self.assertRaises(Stop):media.validate_inputs(data)
        data=deepcopy(self.plan);data['background_image']['expected_url']='https://user:pass@example.com/old.png'
        with self.assertRaises(Stop):media.validate_inputs(data)


if __name__=='__main__':unittest.main()
