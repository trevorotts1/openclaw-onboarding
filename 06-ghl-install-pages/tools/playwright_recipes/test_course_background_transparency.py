"""Measured background slider changes preserve image and inactive-template state."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import course_theme_media as media
import editor_replay
import host
import recipe_cli
import skill6_playwright as runner
from test_sixth_control_integration import probes


def inputs(old=100,new=65):
    return {'location_id':'LOC','location_name':'Fixture',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/memberships/courses/course-creator-studio?view=manager&sub_view=customize&product_id=COURSE',
        'course_id':'COURSE','template_id':'TEMPLATE','expected_template_title':'Inactive theme',
        'background_transparency':{'expected_url':'https://example.com/existing.svg',
            'expected_percentage':old,'percentage':new}}


def state(percent,url='https://example.com/existing.svg',focus_stack=0):
    return {'url':url,'transparency':{'fill_style':'left: 0%; width: '+str(percent)+'%;',
        'handle_style':'left: '+str(percent)+'%; z-index: '+str(focus_stack)+';'}}


class Handle:
    def __init__(self,page):self.page=page
    def press(self,key):
        self.page.keys.append(key)
        self.page.focus_stack=1
        self.page.percent+=1 if key=='ArrowRight' else -1
        self.page.dirty=True
        if self.page.collateral:self.page.collateral(self.page)


class Save:
    def __init__(self,page):self.page=page
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return self.page.dirty
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        self.page.saves+=1;self.page.dirty=False
        if self.page.lose_save:self.page.percent=self.page.old


class Page:
    def __init__(self,data):
        self.url=media.theme.editor_url(data);self.percent=data['background_transparency']['expected_percentage']
        self.old=self.percent;self.image=data['background_transparency']['expected_url']
        self.focus_stack=0
        self.protected={'theme':{'heading':'Keep'},'body_inventory':[{'id':'categoryBlock','type':'Category Block'}]}
        self.keys=[];self.saves=0;self.dirty=False;self.lose_save=False;self.collateral=None
    def get_by_role(self,role,*,name,exact):return Save(self)
    def wait_for_load_state(self,*args,**kwargs):pass


class BackgroundTransparencyTests(unittest.TestCase):
    def setUp(self):
        self.data=inputs();self.page=Page(self.data)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        def opened(page,plan,title):
            page.focus_stack=0
            return ('active','Default Theme')
        self.open=self.stack.enter_context(patch.object(media.theme,'_open',side_effect=opened))
        self.stack.enter_context(patch.object(media.theme,'_identity'))
        self.stack.enter_context(patch.object(media,'assert_tenant'))
        self.stack.enter_context(patch.object(media,'_protected',side_effect=lambda page,plan:deepcopy(page.protected)))
        self.stack.enter_context(patch.object(media,'_background',side_effect=lambda page,plan:(None,state(page.percent,page.image,page.focus_stack))))
        self.stack.enter_context(patch.object(media,'_background_nodes',side_effect=lambda page,plan:(None,None,None,Handle(page))))
        self.stack.enter_context(patch.object(media,'wait_until',side_effect=lambda fn,message:fn() or (_ for _ in ()).throw(runner.Stop(message))))
        self.source=self.stack.enter_context(patch.object(media.media,'_bytes'))
        self.upload=self.stack.enter_context(patch.object(media,'_upload'))

    def run_control(self):return media.configure(self.page,{'payload':self.data})

    def test_full_measured_range_uses_only_one_point_arrow_keys_then_save_and_reopen(self):
        for old,new,key in ((100,0,'ArrowLeft'),(0,100,'ArrowRight')):
            self.data=inputs(old,new);self.page=Page(self.data)
            with self.subTest(old=old,new=new):
                result=self.run_control()
                self.assertEqual(self.page.keys,[key]*100)
                self.assertEqual(self.page.saves,1);self.assertEqual(self.page.image,self.data['background_transparency']['expected_url'])
                self.assertEqual(result['transparency_percentage'],new)
                self.assertEqual(result['media_operation'],'transparency')
                self.assertFalse(result['functional_verified']);self.assertFalse(result['activation_performed'])
                self.assertNotIn('source_sha256',result)
                self.assertEqual(self.page.focus_stack,0)
        self.source.assert_not_called();self.upload.assert_not_called();self.assertEqual(self.open.call_count,4)

    def test_wrong_expected_percentage_or_image_stops_before_first_key(self):
        self.page.percent=99
        with self.assertRaisesRegex(runner.Stop,'inventoried percentage'):self.run_control()
        self.assertEqual(self.page.keys,[]);self.assertEqual(self.page.saves,0)
        self.page.percent=100;self.page.image='https://example.com/foreign.svg'
        with self.assertRaisesRegex(runner.Stop,'inventoried previous URL'):self.run_control()
        self.assertEqual(self.page.keys,[])

    def test_each_key_checks_exact_progress_and_preserved_image_before_any_further_key(self):
        for collateral in (lambda page:setattr(page,'percent',page.percent-1),
                           lambda page:setattr(page,'image','https://example.com/unexpected.png')):
            self.page=Page(self.data);self.page.collateral=collateral
            with self.subTest(collateral=collateral),self.assertRaisesRegex(runner.Stop,'key changed'):self.run_control()
            self.assertEqual(self.page.keys,['ArrowLeft']);self.assertEqual(self.page.saves,0)

    def test_protected_content_drift_and_lost_save_cannot_report_completion(self):
        self.page.collateral=lambda page:page.protected['theme'].update(heading='Changed sibling')
        with self.assertRaisesRegex(runner.Stop,'protected theme/body'):self.run_control()
        self.assertEqual(self.page.saves,0)
        self.page=Page(self.data);self.page.lose_save=True
        with self.assertRaisesRegex(runner.Stop,'independent reopen'):self.run_control()
        self.assertEqual(self.page.saves,1)

    def test_style_readback_requires_matching_integer_percent_and_unchanged_anchor(self):
        self.assertEqual(media._percentage(state(0)),0);self.assertEqual(media._percentage(state(100)),100)
        for field,text in (('fill_style','left: 1%; width: 65%;'),('fill_style','left: 0%; width: 65.5%;'),
            ('fill_style','left: 0%; width: 101%;'),('handle_style','left: 64%;'),
            ('fill_style','left: 0%; width: 65%; width: 60%;')):
            data=state(65);data['transparency'][field]=text
            with self.subTest(field=field,text=text),self.assertRaises(runner.Stop):media._percentage(data)

    def test_only_captured_focus_stacking_transition_is_ignored(self):
        self.assertEqual(media._transparency_readback(state(65,focus_stack=0)),
            media._transparency_readback(state(65,focus_stack=1)))
        for unknown in (-1,2,'auto'):
            with self.subTest(unknown=unknown),self.assertRaises(runner.Stop):
                media._transparency_readback(state(65,focus_stack=unknown))
        changed=state(65);changed['transparency']['handle_style']+=' transform: scale(2);'
        self.assertNotEqual(media._transparency_readback(state(65)),media._transparency_readback(changed))

    def test_schema_refuses_bool_fraction_out_of_range_noop_mixed_upload_and_publication(self):
        for value in (True,65.5,-1,101,'65',None):
            data=inputs();data['background_transparency']['percentage']=value
            with self.subTest(value=value),self.assertRaises(runner.Stop):media.validate_inputs(data)
        for data in (inputs(100,100),{**inputs(),'background_image':{}},{**inputs(),'publish':True}):
            with self.assertRaises(runner.Stop):media.validate_inputs(data)
        first=media.configuration_hash(inputs())
        self.assertNotEqual(first,media.configuration_hash(inputs(99,65)))
        self.assertNotEqual(first,media.configuration_hash(inputs(100,66)))


class BackgroundTransparencyIntegration(unittest.TestCase):
    def job(self):return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',inputs()),Path('.'))
    def receipt(self,job):
        plan=job['steps'][0]['payload']
        return {'status':'COURSE_THEME_MEDIA_SAVED_AND_REOPENED','editor_url':media.theme.editor_url(plan),
            'course_id':plan['course_id'],'template_id':plan['template_id'],
            'configuration_sha256':media.configuration_hash(plan),'independent_readback':'VERIFIED',
            'background_url_sha256':hashlib.sha256(plan['background_transparency']['expected_url'].encode()).hexdigest(),
            'functional_verified':False,'activation_performed':False,
            'media_operation':'transparency','transparency_percentage':65}

    def test_actual_frontdoor_selects_maintained_leaf_and_replays_without_second_write(self):
        job=self.job();self.assertEqual(job['steps'][0]['action'],'native_course_theme_media')
        native=__import__('playwright_recipes.course_theme_media',fromlist=['configure'])
        for fallback in (False,True):
            with self.subTest(fallback=fallback),tempfile.TemporaryDirectory() as evidence, \
                    patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=self.receipt(job)) as write:
                provider=Mock()
                for _ in range(2):
                    result=host.run_recipe('courses.configure_ui',inputs(),probes(inputs(),fallback=fallback),evidence,
                        input_dir='.',page=object(),executors={'public_api':provider,'openclaw_extension':provider})
                    self.assertEqual(result['status'],'NEEDS_VERIFICATION')
                write.assert_called_once();provider.assert_not_called()
                recorded=json.loads(Path(evidence,'state.json').read_text())['results'][0]['result']
                self.assertEqual(recorded['transparency_percentage'],65)

    def test_original_fresh_and_replay_receipts_bind_percentage_image_type_and_pending_flags(self):
        job=self.job();step=job['steps'][0];receipt=self.receipt(job)
        self.assertEqual(editor_replay._result(step,receipt,job)['media_operation'],'transparency')
        for change in ({'transparency_percentage':True},{'transparency_percentage':64},
                {'background_url_sha256':'0'*64},{'media_operation':'upload'},
                {'source_sha256':'0'*64},{'unexpected':'private'},{'activation_performed':True}):
            with self.subTest(change=change),self.assertRaises(runner.Stop):editor_replay._result(step,{**receipt,**change},job)
        native=__import__('playwright_recipes.course_theme_media',fromlist=['configure'])
        with tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'), \
                patch.object(native,'configure',return_value={**receipt,'transparency_percentage':64}) as write:
            for _ in range(2):
                with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,evidence)
            write.assert_called_once();self.assertEqual(json.loads(Path(evidence,'state.json').read_text())['results'],[])


if __name__=='__main__':unittest.main()
