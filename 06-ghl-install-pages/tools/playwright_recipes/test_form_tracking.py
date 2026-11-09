"""Native tracking config preserves unrequested settings and checks saved state."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import form_tracking as native
from skill6_playwright import Stop


BASE={'pixel_id':'','page_view_event':'Page View','submission_event':'Submit Application'}


def step(**changes):
    desired=changes or {'pixel_id':'123456789012345'}
    return {'tracking':{'expected':{key:BASE[key] for key in desired},'changes':desired}}


class TrackingSchemaTests(unittest.TestCase):
    def test_explicit_previous_values_and_captured_event_labels(self):
        data=step(page_view_event='Lead',submission_event='CompleteRegistration')
        self.assertEqual(native.validate(data),data)
        for value in ('Lead', 'Page View', 'Submit Application', 'CompleteRegistration'):
            self.assertEqual(native.validate(step(page_view_event=value))['tracking']['changes']['page_view_event'],value)

    def test_numeric_pixel_strings_and_explicit_clear_are_supported(self):
        for value in ('','0','123456789012345'):
            self.assertEqual(native.validate(step(pixel_id=value)),step(pixel_id=value))

    def test_unknown_ignored_or_malformed_options_fail_before_browser(self):
        invalid=[step(pixel_id=123),step(pixel_id=True),step(pixel_id=' 123'),
                 step(pixel_id='<script>'),step(page_view_event='PageView'),
                 step(submission_event=[]),{'tracking':{'expected':{},'changes':{}}}]
        mismatch=step();mismatch['tracking']['expected']={};invalid.append(mismatch)
        extra=step();extra['tracking']['changes']['cookie_consent']=True;invalid.append(extra)
        for item in invalid:
            page=Mock()
            with self.subTest(item=item),self.assertRaises(Stop):native.configure(page,item)
            self.assertFalse(page.mock_calls)

    def test_hash_binds_expected_values_event_labels_and_pixel_id(self):
        base=step()
        changed=step();changed['tracking']['expected']['pixel_id']='999'
        self.assertNotEqual(native.configuration_hash(base),native.configuration_hash(changed))
        self.assertNotEqual(native.configuration_hash(base),native.configuration_hash(step(pixel_id='222')))
        self.assertNotEqual(native.configuration_hash(step(page_view_event='Lead')),
                            native.configuration_hash(step(submission_event='Lead')))


class NativeStateTests(unittest.TestCase):
    def run_handler(self,data,*,lose_save=False,concurrent=None):
        state,saved=deepcopy(BASE),deepcopy(BASE)
        page,frame,title,save,settings,pixel=[Mock() for _ in range(6)]
        page.url='https://app.example.com/v2/location/L/form-builder-v2/F'
        title.count.return_value=1;title.input_value.return_value='Tracking fixture'
        save.count.return_value=1;save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,name,exact: {'Form Name':title,'Save':save,'Settings':settings}[name]
        controls={'pixel_id':pixel,'page_view_event':Mock(),'submission_event':Mock()}
        fills,saves=[],[]
        def fill(node,value):
            self.assertIs(node,pixel);fills.append(value);state['pixel_id']=value
        def choose(_frame,node,value):
            key=next(k for k,v in controls.items() if v is node);state[key]=value
        reads=0
        def read(_frame):
            nonlocal reads
            reads+=1
            if concurrent and reads==concurrent[0]:state[concurrent[1]]=concurrent[2]
            return controls,deepcopy(state)
        def click(node):
            if node is save:
                saves.append(True)
                if not lose_save:saved.update(state)
        def reopen(*_):state.update(saved)
        with patch.object(native,'form_builder',return_value=frame), \
             patch.object(native,'_close_initial'),patch.object(native,'_read',side_effect=read), \
             patch.object(native,'fill',side_effect=fill),patch.object(native,'click',side_effect=click), \
             patch.object(native,'_choose',side_effect=choose), \
             patch.object(native,'reopen_editor',side_effect=reopen):
            try:result=native.configure(page,data)
            except Stop as error:return {'error':str(error),'state':state,'fills':fills,'saves':saves}
        return {'result':result,'state':state,'fills':fills,'saves':saves}

    def test_pixel_only_edit_preserves_both_events_and_returns_pending_behavior(self):
        result=self.run_handler(step())
        self.assertEqual(result['state'],{**BASE,'pixel_id':'123456789012345'})
        self.assertEqual(result['saves'],[True])
        self.assertEqual(result['result']['status'],'FORM_TRACKING_SAVED_AND_REOPENED')
        self.assertIs(result['result']['behavior_verified'],False)
        self.assertIs(result['result']['submission_verified'],False)

    def test_two_event_changes_preserve_pixel_and_check_independent_readback(self):
        result=self.run_handler(step(page_view_event='Lead',submission_event='CompleteRegistration'))
        self.assertEqual(result['state'],{**BASE,'page_view_event':'Lead','submission_event':'CompleteRegistration'})
        self.assertEqual(result['fills'],[])
        self.assertEqual(result['result']['independent_readback'],'VERIFIED')

    def test_wrong_expected_previous_value_does_not_fill_or_save(self):
        data=step();data['tracking']['expected']['pixel_id']='999'
        result=self.run_handler(data)
        self.assertIn('inventoried previous',result['error'])
        self.assertEqual((result['fills'],result['saves']),([],[]))

    def test_concurrent_unrequested_event_change_prevents_save(self):
        result=self.run_handler(step(),concurrent=(3,'submission_event','Purchase'))
        self.assertIn('preserved event values',result['error'])
        self.assertEqual(result['saves'],[])

    def test_lost_native_save_never_returns_verified(self):
        result=self.run_handler(step(),lose_save=True)
        self.assertIn('did not persist',result['error'])
        self.assertEqual(result['saves'],[True])


class VirtualizedEventMenuTests(unittest.TestCase):
    def test_finds_exact_label_after_scrolling_only_the_native_option_list(self):
        frame,node,menu,scroller,option=[Mock() for _ in range(5)]
        frame.locator.return_value=menu;menu.count.return_value=1
        menu.locator.side_effect=lambda selector:scroller if selector==native.SCROLLER else option
        scroller.count.return_value=1
        state={'top':0}
        scrolls=[]
        def evaluate(script,*args):
            if 'new Promise' in script:return {'top':state['top'],'height':100,'total':300}
            state['top']=args[0] if args else 0;scrolls.append(state['top'])
        scroller.evaluate.side_effect=evaluate
        option.get_by_text.return_value=option
        option.count.side_effect=lambda: int(state['top']>=150)
        option.is_visible.return_value=True
        clicks=[]
        with patch.object(native,'click',side_effect=clicks.append),patch.object(native,'_event',return_value='Subscribe'):
            native._choose(frame,node,'Subscribe')
        self.assertEqual(scrolls,[0,75.0,150.0])
        self.assertEqual(clicks,[node,option])

    def test_missing_option_reaches_bottom_and_stops_without_arbitrary_selection(self):
        frame,node,menu,scroller,option=[Mock() for _ in range(5)]
        frame.locator.return_value=menu;menu.count.return_value=1
        menu.locator.side_effect=lambda selector:scroller if selector==native.SCROLLER else option
        scroller.count.return_value=1
        scroller.evaluate.return_value={'top':0,'height':100,'total':100}
        option.get_by_text.return_value=option;option.count.return_value=0
        clicks=[]
        with patch.object(native,'click',side_effect=clicks.append),self.assertRaisesRegex(Stop,'absent'):
            native._choose(frame,node,'Subscribe')
        self.assertEqual(clicks,[node])


if __name__=='__main__':unittest.main()
