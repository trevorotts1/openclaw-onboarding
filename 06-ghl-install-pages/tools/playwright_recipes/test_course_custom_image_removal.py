"""Exact Custom UUID image removal preserves content, links, siblings and replay."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import course_custom_image_removal as removal
import editor_replay
import recipe_cli
import skill6_playwright as runner
import test_course_block_media as previous
from test_course_video_blocks import base


def inputs():
    return {**base(),'custom_block_image':{'block_id':'BLOCK_A','expected_inventory':[
        {'id':'categoryBlock','type':'Category Block'},{'id':'BLOCK_A','type':'Custom Block'},
        {'id':'BLOCK_B','type':'Custom Block'}],'expected_url':'https://example.com/old.png','remove_image':True}}


class Remove:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return self.page.current['remove_enabled']
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        self.page.removes+=1;self.page.dirty=True
        self.page.current.update(inspector_url=removal.EMPTY_INSPECTOR,preview_url=removal.EMPTY_PREVIEW,remove_enabled=False)
        self.page.current['attributes']['src']=removal.EMPTY_PREVIEW
        self.page.protected['blocks']['BLOCK_A'][1]['media_src']=removal.EMPTY_PREVIEW
        if self.page.collateral:self.page.collateral(self.page)


class CustomRemovalTests(unittest.TestCase):
    def setUp(self):
        self.data=inputs();self.page=previous.Page(self.data);self.page.url=removal.theme.editor_url(self.data)
        self.page.current={'inspector_url':'https://example.com/old.png','preview_url':'https://example.com/old.png',
            'remove_enabled':True,'attributes':{'src':'https://example.com/old.png','alt':'Image block BLOCK_A','class':'keep'},
            'preview_style':'--cb-heading: #1D2939;'}
        self.page.removes=0;self.page.collateral=None;self.page.locator=lambda selector:Remove(self.page)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.open=self.stack.enter_context(patch.object(removal.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(removal.theme,'_identity'))
        self.stack.enter_context(patch.object(removal,'assert_tenant'))
        self.stack.enter_context(patch.object(removal.media,'_protected',side_effect=lambda page,plan:deepcopy(page.protected)))
        self.stack.enter_context(patch.object(removal.blocks,'_inventory',side_effect=lambda page,plan:deepcopy(page.protected['inventory'])))
        self.stack.enter_context(patch.object(removal,'_read',side_effect=lambda page,plan:deepcopy(page.current)))
        self.stack.enter_context(patch.object(removal,'wait_until',side_effect=lambda fn,msg:fn() or (_ for _ in ()).throw(runner.Stop(msg))))

    def step(self):return {'action':'native_course_block_media','payload':self.data}

    def test_distinct_empty_inspector_preview_save_and_reopen_preserve_other_block(self):
        result=removal.configure(self.page,self.step())
        self.assertEqual((self.page.removes,self.page.saves,self.open.call_count),(1,1,2))
        self.assertIs(result['media_removed'],True);self.assertNotIn('source_sha256',result)
        self.assertEqual(self.page.protected['blocks']['BLOCK_B'],self.page.original['blocks']['BLOCK_B'])
        self.assertEqual(self.page.protected['blocks']['BLOCK_A'][0],{'heading':'Keep A'})
        self.assertNotEqual(self.page.current['inspector_url'],self.page.current['preview_url'])

    def test_stale_present_image_disabled_remove_and_inventory_refuse_before_click(self):
        for kind in ('image','disabled','inventory'):
            with self.subTest(kind=kind):
                before=deepcopy(self.page.current);inventory=deepcopy(self.page.protected['inventory'])
                if kind=='image':self.page.current['preview_url']='https://example.com/foreign.png'
                elif kind=='disabled':self.page.current['remove_enabled']=False
                else:self.page.protected['inventory'].reverse()
                with self.assertRaises(runner.Stop):removal.configure(self.page,self.step())
                self.assertEqual(self.page.removes,0)
                self.page.current=before;self.page.protected['inventory']=inventory

    def test_collateral_content_and_lost_save_do_not_report_success(self):
        self.page.collateral=lambda page:page.protected['blocks']['BLOCK_B'][0].update(heading='CORRUPT')
        with self.assertRaisesRegex(runner.Stop,'protected text'):removal.configure(self.page,self.step())
        self.assertEqual(self.page.saves,0)

    def test_receipt_compiler_and_completed_replay_refuse_restored_image_without_second_write(self):
        job=runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',self.data),Path('.'));step=job['steps'][0]
        receipt=removal.configure(self.page,step);editor_replay._result(step,receipt,job)
        for change in ({'media_removed':1},{'inspector_url_sha256':'0'*64},{'source_sha256':'0'*64}):
            with self.assertRaises(runner.Stop):editor_replay._result(step,{**receipt,**change},job)
        native=__import__('playwright_recipes.course_custom_image_removal',fromlist=['verify_completed'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(runner,'native_course_block_media',return_value=receipt) as writer, \
                patch.object(native,'verify_completed',side_effect=lambda page,step,outcome:removal.verify_completed(page,step,outcome)) as verify:
            runner.run_on_page(self.page,job,evidence);runner.run_on_page(self.page,job,evidence)
            saved=Path(evidence,'state.json').read_bytes()
            self.page.current['preview_url']='https://example.com/restored.png'
            with self.assertRaisesRegex(runner.Stop,'empty state drifted'):runner.run_on_page(self.page,job,evidence)
            writer.assert_called_once();self.assertEqual(verify.call_count,2)
            self.assertEqual(Path(evidence,'state.json').read_bytes(),saved)

    def test_native_empty_placeholder_mixed_upload_and_unacknowledged_remove_refuse(self):
        for change in ({'expected_url':removal.EMPTY_PREVIEW},{'remove_image':False},{'file':'/tmp/extra.png'}):
            data=deepcopy(self.data);data['custom_block_image'].update(change)
            with self.assertRaises(runner.Stop):removal.media.validate_inputs(data)


if __name__=='__main__':unittest.main()
