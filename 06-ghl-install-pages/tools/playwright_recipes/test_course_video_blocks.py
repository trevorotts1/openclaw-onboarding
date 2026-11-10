"""Bounded native video lifecycle and replay integration, without live upload claims."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import course_video_blocks as video
import editor_replay
import host
from test_sixth_control_integration import probes
import recipe_cli
import skill6_playwright as runner


def base():
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme'}


def state(src='',poster=''):
    return ({'src':src,'poster':poster},{'attributes':{'class':'w-fill aspect-video rounded-lg w-full',
        'src':src,'poster':poster,'controls':'','controlslist':'nodownload'},'remove_enabled':bool(src)})


class Button:
    def __init__(self,page,name):self.page=page;self.name=name
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return self.page.dirty if self.name=='Save' else True
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        if self.name=='Save':
            self.page.saves+=1;self.page.dirty=False
            if self.page.lose_save:self.page.states['VIDEO']=state('https://example.com/old.mp4')
        if self.name=='Video Block':
            self.page.inventory.append({'id':'ADDED','type':'Video Block'});self.page.states['ADDED']=state()


class Page:
    def __init__(self):
        self.inventory=[{'id':'categoryBlock','type':'Category Block'},{'id':'VIDEO','type':'Video Block'}]
        self.states={'VIDEO':state('https://example.com/old.mp4')};self.dirty=False;self.saves=0;self.lose_save=False
        self.url=video.theme.editor_url(base())
    def get_by_role(self,role,*,name,exact):return Button(self,name)
    def wait_for_load_state(self,*args,**kwargs):pass


class VideoBlocksTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'approved.mp4';self.source.write_bytes(b'\x00\x00\x00\x18ftypmp42APPROVED_VIDEO')
        self.asset={'file':str(self.source),'sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.page=Page();self.data={**base(),'video_blocks':{'expected_inventory':deepcopy(self.page.inventory),
            'updates':[{'id':'VIDEO','expected':deepcopy(self.page.states['VIDEO'][0]),'changes':{'video':self.asset}}],
            'append':[{'video':self.asset}]}}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.open=self.stack.enter_context(patch.object(video.theme,'_open',return_value=('active','Default Theme')))
        self.stack.enter_context(patch.object(video.theme,'_snapshot',return_value={'keep':'theme'}))
        self.stack.enter_context(patch.object(video.theme,'_identity'))
        self.stack.enter_context(patch.object(video,'assert_tenant'))
        self.stack.enter_context(patch.object(video.blocks,'_inventory',side_effect=lambda page,plan:deepcopy(page.inventory)))
        self.stack.enter_context(patch.object(video.blocks,'_snapshot',side_effect=lambda page,plan,inventory:deepcopy(page.states)))
        self.stack.enter_context(patch.object(video,'read_video_block',side_effect=lambda page,plan,identity:deepcopy(page.states[identity])))
        self.stack.enter_context(patch.object(video,'wait_until',side_effect=lambda fn,msg:fn() or (_ for _ in ()).throw(runner.Stop(msg))))
        def write(page,plan,identity,changes,path,size):
            if 'video' in changes:
                self.assertEqual(path.read_bytes(),self.source.read_bytes());self.assertEqual(path.stat().st_mode&0o777,0o600)
                new=state('https://example.com/'+identity+'.mp4','https://example.com/'+identity+'.png')
            else:new=state()
            page.states[identity]=new;page.dirty=True;return deepcopy(new)
        self.writer=self.stack.enter_context(patch.object(video,'_write',side_effect=write))

    def test_replace_append_save_reopen_and_receipts_preserve_exact_order(self):
        receipt=video.configure(self.page,{'payload':self.data})
        self.assertEqual(receipt['block_ids'],['categoryBlock','VIDEO','ADDED'])
        self.assertEqual(receipt['added_block_ids'],['ADDED']);self.assertEqual(self.page.saves,1)
        self.assertEqual(self.open.call_count,2);self.assertEqual(self.writer.call_count,2)
        self.assertFalse(receipt['functional_verified']);self.assertFalse(receipt['activation_performed'])

    def test_removal_and_lost_save_are_distinct_from_a_successful_upload(self):
        self.data['video_blocks']['append']=[]
        self.data['video_blocks']['updates'][0]['changes']={'remove_video':True}
        receipt=video.configure(self.page,{'payload':self.data})
        self.assertIs(receipt['videos'][0]['removed'],True);self.assertIsNone(receipt['videos'][0]['source_sha256'])
        self.page=Page();self.page.lose_save=True
        with self.assertRaisesRegex(runner.Stop,'saved reopen'):video.configure(self.page,{'payload':self.data})

    def test_stale_inventory_or_previous_source_stops_before_writer(self):
        self.page.inventory.reverse()
        with self.assertRaisesRegex(runner.Stop,'inventory is stale'):video.configure(self.page,{'payload':self.data})
        self.writer.assert_not_called();self.page=Page();self.page.states['VIDEO']=state('https://example.com/foreign.mp4')
        with self.assertRaisesRegex(runner.Stop,'source/poster inventory'):video.configure(self.page,{'payload':self.data})
        self.writer.assert_not_called()

    def test_approved_video_copy_rejects_hash_change_symlink_and_wrong_magic(self):
        copied=Path(self.tmp.name)/'good.mp4';video._copy_approved(self.asset,copied)
        self.assertEqual(copied.read_bytes(),self.source.read_bytes())
        for name,asset in [('hash',{**self.asset,'sha256':'0'*64})]:
            with self.assertRaises(runner.Stop):video._copy_approved(asset,Path(self.tmp.name)/(name+'.mp4'))
        link=Path(self.tmp.name)/'link.mp4';link.symlink_to(self.source)
        with self.assertRaises(runner.Stop):video._copy_approved({**self.asset,'file':str(link)},Path(self.tmp.name)/'link-copy.mp4')
        self.source.write_bytes(b'NOT_A_VIDEO_BUT_LONG_ENOUGH')
        with self.assertRaises(runner.Stop):video._copy_approved({**self.asset,'sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()},Path(self.tmp.name)/'bad.mp4')

    def test_intake_runner_receipt_and_completed_replay_bind_live_media(self):
        job=runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',self.data),Path('.'));step=job['steps'][0]
        self.assertEqual(step['action'],'native_course_video_blocks')
        receipt=video.configure(self.page,step);editor_replay._result(step,receipt,job)
        for change in ({'configuration_sha256':'0'*64},{'videos':[]},{'activation_performed':True}):
            with self.assertRaises(runner.Stop):editor_replay._result(step,{**receipt,**change},job)
        video.verify_completed(self.page,step,receipt)
        self.page.states['VIDEO']=state('https://example.com/drift.mp4')
        with self.assertRaisesRegex(runner.Stop,'media drifted'):video.verify_completed(self.page,step,receipt)

    def test_host_routes_video_through_native_writer_and_live_replay_verifier(self):
        job=runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',self.data),Path('.'))
        receipt=video.configure(self.page,job['steps'][0])
        native=__import__('playwright_recipes.course_video_blocks',fromlist=['configure'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value=receipt) as writer, \
                patch.object(native,'verify_completed',return_value=True) as verify:
            for _ in range(2):
                result=host.run_recipe('courses.configure_ui',self.data,probes(self.data),evidence,
                    input_dir='.',page=object())
                self.assertEqual(result['status'],'NEEDS_VERIFICATION')
            writer.assert_called_once();verify.assert_called_once()

    def test_missing_or_mixed_video_plan_is_rejected_before_browser(self):
        for changes in ({'remove_video':False},{'remove_video':True,'video':self.asset}):
            data=deepcopy(self.data);data['video_blocks']['updates'][0]['changes']=changes
            with self.assertRaises(runner.Stop):video.validate_inputs(data)
        self.open.assert_not_called()


if __name__=='__main__':unittest.main()
