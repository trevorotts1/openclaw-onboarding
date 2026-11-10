"""Captured empty background must replace one exact present inactive image."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import course_theme_media as media
import editor_replay
import recipe_cli
import skill6_playwright as runner
import test_course_theme_media as upload_tests


def inputs():
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'background_removal':{'expected_url':'https://example.com/old.svg'}}


class Remove:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return self.page.enabled
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        self.page.removes+=1;self.page.dirty=True
        self.page.background['url']=media._EMPTY_BACKGROUND;self.page.enabled=False
        self.page.styles['--lyt-bg-image']="url('')"
        if self.page.collateral:self.page.collateral(self.page)


class Owner:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def locator(self,selector):return Remove(self.page) if selector=='#remove-image' else self


class BackgroundRemovalTests(unittest.TestCase):
    def setUp(self):
        self.data=inputs();self.page=upload_tests.Page();self.page.url=media.theme.editor_url(self.data)
        self.page.enabled=True;self.page.removes=0;self.page.collateral=None
        self.page.styles={'--lyt-bg-image':'url("'+self.page.background['url']+'")','--lyt-bg-color':'#FEFEFF'}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.open=self.stack.enter_context(patch.object(media.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(media.theme,'_identity'))
        self.stack.enter_context(patch.object(media,'assert_tenant'))
        self.stack.enter_context(patch.object(media,'_protected',side_effect=lambda page,plan:deepcopy(page.protected)))
        self.stack.enter_context(patch.object(media,'_removal_state',side_effect=lambda page,plan:{
            **deepcopy(page.background),'remove_enabled':page.enabled,'preview_styles':deepcopy(page.styles)}))
        self.stack.enter_context(patch.object(media,'_background_nodes',side_effect=lambda page,plan:(None,Owner(page),None,None)))
        self.stack.enter_context(patch.object(media,'wait_until',side_effect=lambda fn,msg:fn() or (_ for _ in ()).throw(runner.Stop(msg))))
        self.bytes=self.stack.enter_context(patch.object(media.media,'_bytes'))
        self.upload=self.stack.enter_context(patch.object(media,'_upload'))

    def run_control(self):return media.configure(self.page,{'payload':self.data})

    def test_removes_once_preserves_siblings_then_saves_and_independently_reopens(self):
        result=self.run_control()
        self.assertEqual((self.page.removes,self.page.saves,self.open.call_count),(1,1,2))
        self.assertEqual(result['media_operation'],'removal');self.assertIs(result['background_removed'],True)
        self.assertEqual(result['background_url_sha256'],hashlib.sha256(media._EMPTY_BACKGROUND.encode()).hexdigest())
        self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])
        self.bytes.assert_not_called();self.upload.assert_not_called()

    def test_stale_image_disabled_remove_or_disagreeing_preview_stops_before_click(self):
        for change in ('url','disabled','preview'):
            with self.subTest(change=change):
                self.page.background['url']='https://example.com/old.svg';self.page.enabled=True
                self.page.styles['--lyt-bg-image']='url("https://example.com/old.svg")'
                if change=='url':self.page.background['url']='https://example.com/other.png'
                elif change=='disabled':self.page.enabled=False
                else:self.page.styles['--lyt-bg-image']='url("https://example.com/other.png")'
                with self.assertRaises(runner.Stop):self.run_control()
                self.assertEqual(self.page.removes,0);self.assertEqual(self.page.saves,0)

    def test_empty_result_with_collateral_style_change_never_saves(self):
        self.page.collateral=lambda page:page.styles.update({'--lyt-bg-color':'#000000'})
        with self.assertRaisesRegex(runner.Stop,'captured empty'):self.run_control()
        self.assertEqual(self.page.saves,0)

    def test_lost_save_never_reports_completion(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(runner.Stop,'independent reopen'):self.run_control()
        self.assertEqual(self.page.saves,1)

    def test_schema_rejects_placeholder_unknown_empty_profile_and_mixed_job(self):
        for update in ({'background_removal':{'expected_url':media._EMPTY_BACKGROUND}},
                {'background_removal':{'expected_url':'https://example.com/old.svg','empty_url':'https://example.com/fake.svg'}},
                {'background_transparency':{}},{'publish':True}):
            with self.subTest(update=update),self.assertRaises(runner.Stop):media.validate_inputs({**self.data,**update})

    def test_compilation_and_receipt_replay_keep_removal_bound_and_proof_pending(self):
        job=runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',self.data),Path('.'))
        step=job['steps'][0];self.assertEqual(step['action'],'native_course_theme_media')
        receipt=self.run_control()
        self.assertIs(editor_replay._result(step,receipt,job)['background_removed'],True)
        for change in ({'background_removed':1},{'background_removed':False},
                {'background_url_sha256':'0'*64},{'media_operation':'transparency'},
                {'source_sha256':'0'*64},{'activation_performed':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):
                editor_replay._result(step,{**receipt,**change},job)
        native=__import__('playwright_recipes.course_theme_media',fromlist=['configure'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=receipt) as writer, \
                patch.object(native,'verify_completed',return_value=True) as verify:
            for _ in range(2):runner.run_on_page(object(),job,evidence)
            writer.assert_called_once();verify.assert_called_once()


    def test_completed_replay_reads_native_empty_state_and_refuses_restored_image_without_write(self):
        job=runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',self.data),Path('.'))
        receipt=self.run_control()
        native=__import__('playwright_recipes.course_theme_media',fromlist=['configure'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=receipt) as writer, \
                patch.object(native.theme,'_open',return_value=('active','Default Theme')) as reopen, \
                patch.object(native.theme,'_identity'),patch.object(native,'assert_tenant'), \
                patch.object(native,'_removal_state',side_effect=lambda page,plan:{
                    **deepcopy(page.background),'remove_enabled':page.enabled,'preview_styles':deepcopy(page.styles)}):
            runner.run_on_page(self.page,job,evidence)
            journal=Path(evidence,'state.json').read_bytes()
            runner.run_on_page(self.page,job,evidence)
            self.assertEqual(reopen.call_count,1)
            self.page.background['url']='https://example.com/restored.png';self.page.enabled=True
            self.page.styles['--lyt-bg-image']='url("https://example.com/restored.png")'
            with self.assertRaisesRegex(runner.Stop,'no longer matches'):
                runner.run_on_page(self.page,job,evidence)
            self.assertEqual(reopen.call_count,2);writer.assert_called_once()
            self.assertEqual(Path(evidence,'state.json').read_bytes(),journal)


if __name__=='__main__':unittest.main()
