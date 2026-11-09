"""Native embed export is bound to one form and never installation proof."""
from copy import deepcopy
import hashlib
import html
import json
import shutil
import subprocess
from unittest.mock import Mock, patch
import unittest

import form_embed as native
from skill6_playwright import Stop


def plan(**changes):
    result = {'action':'native_form_embed', 'integration':{
        'expected':{}, 'changes':{}, 'form_id':'FORM', 'expected_form_name':'Authored Form',
        'embed_origin':'https://links.example.com', 'script_origin':'https://links.example.com'}}
    result['integration'].update(changes)
    return result


def state(**changes):
    result = {'layout':'Sidebar', 'position':'Left', 'width':800, 'height':'Auto',
        'button_label':'Contact us', 'activation':'alwaysActivated', 'activation_visits':3,
        'trigger':'alwaysShow', 'scroll_percentage':50, 'delay_seconds':5,
        'deactivation':'neverDeactivate', 'deactivation_views':1, 'respect_cookie_consent':True}
    result.update(changes)
    return result


def exported(current=None, appearance=None, **attrs):
    current = current or state()
    layout = {'id':'STICKY_SIDEBAR', 'minimizedTitle':current['button_label'],
        'isLeftAligned':current['position']=='Left', 'isRightAligned':current['position']=='Right',
        'allowMinimize':True, 'buttonColor':'#101828', 'buttonType':'text',
        'buttonSize':'medium', 'buttonIcon':'chat', 'fontSize':16,
        'cornerRadius':{'tl':8,'tr':8,'bl':8,'br':8}}
    if current['layout'] == 'Popover':
        layout['id'] = 'POLITE_SLIDE_IN'
    elif current['layout'] == 'Popup':
        layout['id'] = 'POPUP'
        for key in ('isLeftAligned','isRightAligned','allowMinimize'):layout.pop(key)
    elif current['layout'] == 'Standard':
        layout = {'id':'INLINE'}
    if appearance is not None:
        layout.update(cornerRadius=appearance['corner_radii'],fontSize=appearance['font_size'],
                      buttonType=appearance['button_type'],buttonSize=appearance['button_size'])
    if current['layout'] in ('Popup','Standard') and current['width'] != 800:
        layout['formWidth'] = current['width']
    prefix = {'Sidebar':'sticky-sidebar-' + str(current['position']).lower(),
              'Popover':'polite-slide-in-' + str(current['position']).lower(),
              'Popup':'popup','Standard':'inline'}[current['layout']]
    identity = prefix + '-FORM'
    values = {'src':'https://links.example.com/widget/form/FORM', 'id':identity,
        'style':'display:none;width:100%;height:100%;border:none;border-radius:8px',
        'data-layout':json.dumps(layout).replace('"', "'"),
        'data-trigger-type':current['trigger'], 'data-trigger-value': '',
        'data-activation-type':current['activation'], 'data-activation-value':'',
        'data-deactivation-type':current['deactivation'], 'data-deactivation-value':'',
        'data-form-name':'Authored Form', 'data-height':'727', 'data-layout-iframe-id':identity,
        'data-form-id':'FORM', 'data-cookie-consent':str(current['respect_cookie_consent']).lower(),
        'data-cookie-consent-provider':'auto', 'title':'Authored Form'}
    for key, kind, active in (('activation_visits','activation','activateOnVisit'),
                              ('scroll_percentage','trigger','showOnScrolling'),
                              ('delay_seconds','trigger','showAfter'),
                              ('deactivation_views','deactivation','deactivateAfter')):
        if current[kind] == active:
            values['data-' + kind + '-value'] = str(current[key])
    if current['layout'] == 'Popup' and current['height'] != 'Auto':
        values['data-modal-height'] = str(current['height'])
    values.update(attrs)
    attributes = '\n'.join(key + '="' + html.escape(str(value), quote=True) + '"' for key,value in values.items())
    return '<iframe\n' + attributes + '\n></iframe>\n<script src="https://links.example.com/js/form_embed.js"></script>'


class SchemaTests(unittest.TestCase):
    def test_export_only_and_exact_previous_desired_keys_are_supported(self):
        self.assertEqual(native.validate(plan()), plan())
        item = plan(expected={'position':'Left'}, changes={'position':'Right'})
        self.assertEqual(native.validate(item), item)
        invalid = [plan(expected={}, changes={'position':'Right'}),
            plan(expected={'respect_cookie_consent':True}, changes={'respect_cookie_consent':'false'}),
            plan(expected={'scroll_percentage':50}, changes={'scroll_percentage':101}),
            plan(expected={'width':800}, changes={'width':True}),
            plan(expected={'unknown':1}, changes={'unknown':2}),
            plan(embed_origin='https://user:pass@links.example.com'),
            plan(expected_form_name='Other\nname')]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(Stop):
                native.validate(value)

    def test_hash_binds_previous_values_desired_values_form_identity_and_origins(self):
        base = plan(expected={'position':'Left'}, changes={'position':'Right'})
        variants = [deepcopy(base) for _ in range(5)]
        variants[0]['integration']['expected']['position']='Right'
        variants[1]['integration']['changes']['position']='Left'
        variants[2]['integration']['form_id']='OTHER'
        variants[3]['integration']['expected_form_name']='Other form'
        variants[4]['integration']['embed_origin']='https://other.example.com'
        self.assertEqual(len({native.configuration_hash(value) for value in [base,*variants]}), 6)


class ExportTests(unittest.TestCase):
    def verify(self, code, current=None):
        return native.verify_export_configuration(code, plan()['integration'], current or state())

    def test_exact_native_fragment_is_retained_byte_for_byte_with_bound_hash(self):
        code=exported()
        result=self.verify(code)
        self.assertEqual(result['embed_code'],code)
        self.assertEqual(result['embed_sha256'],hashlib.sha256(code.encode()).hexdigest())
        self.assertEqual(result['form_id'],'FORM')

    def test_malformed_foreign_or_inline_executable_code_is_refused(self):
        code=exported()
        invalid=[exported(**{'data-form-id':'OTHER'}),
            exported(src='https://links.example.com/widget/form/OTHER'),
            exported(src='https://other.example.com/widget/form/FORM'),
            exported(**{'data-form-name':'Other form'}),
            exported(**{'data-layout-iframe-id':'other-FORM'}),
            exported(srcdoc='<script>bad()</script>'),
            exported(onload='bad()'),
            code.replace('</script>','bad()</script>'),
            code+code,
            code.replace('/js/form_embed.js','/js/other.js'),
            code+'<img src="https://other.example.com/pixel">']
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(Stop):self.verify(value)

    def test_exported_modes_values_and_cookie_choice_must_match_visible_configuration(self):
        current=state(position='Right',activation='activateOnVisit',activation_visits=4,
            trigger='showOnScrolling',scroll_percentage=75,deactivation='deactivateAfter',deactivation_views=2,
            respect_cookie_consent=False,button_label='Book now')
        self.verify(exported(current),current)
        for attrs in ({'data-trigger-value':'50'}, {'data-activation-type':'alwaysActivated'},
                      {'data-cookie-consent':'true'}, {'data-cookie-consent-provider':'other'},
                      {'data-deactivation-value':'1'}):
            with self.subTest(attrs=attrs),self.assertRaises(Stop):
                self.verify(exported(current,**attrs),current)

    def test_all_four_observed_native_layout_id_relations_are_checked(self):
        for mode in native.LAYOUTS:
            current=state(layout=mode)
            if mode in ('Popup','Standard'):current['position']=None
            if mode=='Standard':current['button_label']=None
            if mode in ('Popup','Standard'):current['width']=620
            if mode=='Popup':current['height']=650
            with self.subTest(mode=mode):self.verify(exported(current),current)
        current=state(layout='Popup',position=None,width=620,height=650)
        with self.assertRaises(Stop):
            self.verify(exported(current,**{'data-modal-height':'649'}),current)

    def test_replay_rederives_native_html_hash_form_and_desired_values(self):
        config=plan(expected={'button_label':'Old'},changes={'button_label':'Contact us'})
        code=exported()
        result={'status':'FORM_EMBED_EXPORTED_AND_REREAD','kind':'form_embed','form_id':'FORM',
            'configuration_sha256':native.configuration_hash(config),'embed_code':code,
            'embed_sha256':hashlib.sha256(code.encode()).hexdigest(),'export_settings':state(),
            'independent_readback':'VERIFIED','settings_persisted':False,
            'installation_verified':False,'behavior_verified':False,'submission_verified':False}
        self.assertEqual(native.validate_receipt(result,config)['embed_code'],code)
        mutations=[{'embed_sha256':'0'*64}, {'form_id':'OTHER'}, {'settings_persisted':True},
                   {'export_settings':state(button_label='Different')}, {'embed_code':exported(**{'title':'Other'})}]
        for mutation in mutations:
            with self.subTest(mutation=mutation),self.assertRaises(Stop):
                native.validate_receipt({**result,**mutation},config)

    def test_displayed_code_lines_execute_the_actual_join_javascript(self):
        import playwright_recipes.skill6_playwright as core
        code=exported()
        rendered_lines=code.splitlines()
        frame,dialog,heading,open_button,copy_button,close_button,lines=[Mock() for _ in range(7)]
        for node in (dialog,heading,open_button,copy_button,close_button):
            node.count.return_value=1;node.is_visible.return_value=True
        lines.count.return_value=len(rendered_lines)
        frame.get_by_role.side_effect=lambda role,**kwargs: (
            open_button if role=='button' else heading if role=='heading' else dialog)
        dialog.filter.return_value=dialog
        dialog.locator.side_effect={
            '#copy-embed-code':copy_button,
            '#embed-code-modal-modal-close-btn':close_button,
            'pre.CodeMirror-line':lines}.__getitem__
        javascript_calls=[]
        def execute_actual_source(source):
            javascript_calls.append(source)
            runtime=shutil.which('node')
            self.assertIsNotNone(runtime,'The required source-join regression needs Node')
            program=("const fs=require('node:fs');"
                "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
                "const read=(0,eval)('('+input.source+')');"
                "process.stdout.write(JSON.stringify(read(input.lines.map(textContent=>({textContent})))));")
            completed=subprocess.run([runtime,'-e',program],
                input=json.dumps({'source':source,'lines':rendered_lines}),
                text=True,capture_output=True,check=True)
            return json.loads(completed.stdout)
        lines.evaluate_all.side_effect=execute_actual_source
        with patch.object(core,'click'):
            result=native._export(frame,plan()['integration'],state())
        self.assertEqual(len(javascript_calls),1)
        self.assertEqual(result['embed_code'],code)
        self.assertEqual(result['embed_sha256'],hashlib.sha256(code.encode()).hexdigest())
        self.assertNotIn('\\n',result['embed_code'])

    def test_single_quoted_layout_parser_preserves_literal_boolean_words_in_button_copy(self):
        current=state(button_label='true false null')
        self.verify(exported(current),current)
        with self.assertRaises(Stop):native._layout_data("__import__('os').system('bad')")


class LifecycleTests(unittest.TestCase):
    def exercise(self, config=None, *, exports_differ=False):
        from contextlib import ExitStack
        import playwright_recipes.skill6_playwright as core
        import playwright_recipes.field_placement as fields
        data=config or plan()
        current=state()
        title=Mock();title.count.return_value=1;title.is_visible.return_value=True
        title.input_value.return_value='Authored Form'
        tab=Mock();tab.count.return_value=1;tab.is_visible.return_value=True
        frame=Mock()
        frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else tab
        page=Mock();page.url='https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM'
        calls=[]
        first=native.verify_export_configuration(exported(),data['integration'],current)
        second={**first,'embed_code':first['embed_code']+' '} if exports_differ else first
        with ExitStack() as stack:
            stack.enter_context(patch.object(core,'form_builder',return_value=frame))
            stack.enter_context(patch.object(core,'click',side_effect=lambda node:calls.append(node)))
            fill=stack.enter_context(patch.object(core,'fill'))
            stack.enter_context(patch.object(fields,'_close_initial'))
            stack.enter_context(patch.object(native,'_read',return_value=current))
            general=stack.enter_context(patch.object(native,'_general',return_value=(current,{})))
            stack.enter_context(patch.object(native,'_advanced',return_value=(current,{})))
            export=stack.enter_context(patch.object(native,'_export',side_effect=[first,second]))
            try:result=native.configure(page,data)
            except Stop as error:result=error
        return result,calls,fill,general,export,frame

    def test_export_only_reads_twice_without_form_save_or_installation(self):
        result,calls,fill,_,export,frame=self.exercise()
        self.assertEqual(result['status'],'FORM_EMBED_EXPORTED_AND_REREAD')
        self.assertEqual(export.call_count,2)
        fill.assert_not_called()
        self.assertFalse(result['settings_persisted'])
        self.assertFalse(result['installation_verified'])
        self.assertFalse(result['behavior_verified'])
        self.assertFalse(result['submission_verified'])
        requested=[call.kwargs.get('name') for call in frame.get_by_role.call_args_list]
        self.assertNotIn('Save',requested)
        self.assertNotIn('Publish',requested)

    def test_stale_expected_values_stop_before_any_local_input_edit_or_export(self):
        result,_,fill,general,export,_=self.exercise(plan(
            expected={'button_label':'Other'},changes={'button_label':'Authored'}))
        self.assertIsInstance(result,Stop)
        fill.assert_not_called();general.assert_not_called();export.assert_not_called()

    def test_second_native_export_drift_never_claims_success(self):
        result,_,_,_,export,_=self.exercise(exports_differ=True)
        self.assertIsInstance(result,Stop)
        self.assertEqual(export.call_count,2)

    def test_popup_cannot_silently_ignore_an_authored_null_button_label(self):
        data=plan(expected={'layout':'Sidebar','position':'Left','width':800,'height':'Auto','button_label':'Contact us'},
            changes={'layout':'Popup','position':None,'width':620,'height':650,'button_label':None})
        result,_,fill,general,export,_=self.exercise(data)
        self.assertIsInstance(result,Stop)
        self.assertIn('authored button text',str(result))
        fill.assert_not_called();general.assert_not_called();export.assert_not_called()

    def test_ignored_standard_height_is_refused_before_any_input_edit(self):
        data=plan(expected={'layout':'Sidebar','position':'Left','width':800,'height':'Auto','button_label':'Contact us'},
            changes={'layout':'Standard','position':None,'width':620,'height':650,'button_label':None})
        result,_,fill,general,export,_=self.exercise(data)
        self.assertIsInstance(result,Stop)
        self.assertIn('Standard ignores height',str(result))
        fill.assert_not_called();general.assert_not_called();export.assert_not_called()


def appearance(**changes):
    value={'corner_radii':{'tl':8,'tr':8,'bl':8,'br':8},'font_size':16,'linked':True,
           'button_type':'text','button_size':'medium'}
    value.update(changes)
    return value


class AppearanceTests(unittest.TestCase):
    def test_schema_binds_only_captured_properties_and_states(self):
        item=plan(appearance={'expected':{'font_size':16},'changes':{'font_size':18}})
        self.assertEqual(native.validate(item),item)
        self.assertNotEqual(native.configuration_hash(item),native.configuration_hash(plan()))
        invalid=[{'font_size':0},{'font_size':True},{'font_size':257},
                 {'linked':'false'},{'button_type':'invented'},{'button_size':'tiny'},
                 {'button_color':'#fff'},{'corner_radii':{'tl':10}},
                 {'corner_radii':{'tl':-1,'tr':8,'bl':8,'br':8}}]
        for props in invalid:
            with self.subTest(props=props),self.assertRaises(Stop):
                native.validate(plan(appearance={'expected':props,'changes':props}))

    def test_exact_native_button_metadata_is_checked_without_changing_iframe_border_radius(self):
        desired=appearance(corner_radii={'tl':10,'tr':12,'bl':14,'br':16},font_size=18,
                           linked=False,button_type='textIcon',button_size='large')
        code=exported(appearance=desired)
        config=plan()['integration']
        native.verify_export_configuration(code,config,state(),desired)
        self.assertIn('border-radius:8px',code)
        for change in ({'font_size':17},{'button_size':'small'},{'button_type':'icon'},
                       {'corner_radii':{'tl':10,'tr':12,'bl':14,'br':15}}):
            with self.subTest(change=change),self.assertRaises(Stop):
                native.verify_export_configuration(code,config,state(),{**desired,**change})

    def exercise(self, before, desired):
        import playwright_recipes.skill6_playwright as core
        current=deepcopy(before);events=[]
        controls={key:Mock() for key in (*native.CORNERS,'font_size','linked','button_type','button_size')}
        controls['linked'].get_attribute.side_effect=lambda _:str(current['linked']).lower()
        options={label:Mock() for label in (*native.BUTTON_TYPES.values(),*native.BUTTON_SIZES.values())}
        frame=Mock();frame.locator.return_value.get_by_text.side_effect=lambda label,exact:options[label]
        for option in options.values():
            option.count.return_value=1;option.is_visible.return_value=True
        def click(control):
            if control is controls['linked']:
                current['linked']=not current['linked'];events.append(('linked',current['linked']))
            elif control in options.values():
                label=next(label for label,node in options.items() if node is control)
                for key,labels in (('button_type',native.BUTTON_TYPES),('button_size',native.BUTTON_SIZES)):
                    if label in labels.values():current[key]=next(key_ for key_,text in labels.items() if text==label)
                events.append(('option',label))
        def fill(control,value):
            key=next(key for key,node in controls.items() if node is control)
            if key in native.CORNERS:
                self.assertFalse(current['linked'],'Explicit per-corner edits must unlink propagation first')
                current['corner_radii'][key]=int(value)
            else:current[key]=int(value)
            events.append(('fill',key,value))
        def wait(fn,message):
            if not fn():raise Stop(message)
        with patch.object(native,'_appearance',side_effect=lambda _:(deepcopy(current),controls)), \
             patch.object(native,'_appearance_select',side_effect=lambda _,key,values:(current[key],controls[key])), \
             patch.object(core,'click',side_effect=click),patch.object(core,'fill',side_effect=fill), \
             patch.object(core,'wait_until',side_effect=wait):
            try:result=native._write_appearance(frame,before,desired,lambda:None)
            except Stop as error:result=error
        return result,current,events

    def test_unlinks_before_each_explicit_corner_then_checks_font_and_exact_select_choices(self):
        before=appearance();desired=appearance(corner_radii={'tl':10,'tr':12,'bl':14,'br':16},font_size=18,
                                             linked=False,button_type='textIcon',button_size='large')
        result,current,events=self.exercise(before,desired)
        self.assertIsNone(result);self.assertEqual(current,desired)
        self.assertEqual(events[0],('linked',False))
        self.assertIn(('option','Icon + text'),events)
        self.assertIn(('option','Large'),events)
        self.assertFalse(any('Save' in str(event) for event in events))

    def test_linked_uniform_corners_restore_link_state_after_explicit_values(self):
        result,current,events=self.exercise(appearance(),appearance(corner_radii=dict.fromkeys(native.CORNERS,12)))
        self.assertIsNone(result)
        self.assertTrue(current['linked']);self.assertEqual(events[-1],('linked',True))

    def test_nonuniform_linked_plan_stops_before_any_value_write(self):
        result,_,events=self.exercise(appearance(),appearance(corner_radii={'tl':10,'tr':12,'bl':14,'br':16}))
        self.assertIsInstance(result,Stop);self.assertEqual(events,[])

    def test_native_export_preserves_unrequested_button_color_icon_and_other_layout_keys(self):
        before=exported();desired=appearance(font_size=18)
        after=exported(appearance=desired)
        native._preserved_layout(before,after,state(),state())
        altered=after.replace('#101828','#ffffff')
        with self.assertRaisesRegex(Stop,'unrequested'):
            native._preserved_layout(before,altered,state(),state())

    def test_replay_revalidates_and_retains_the_appearance_artifact(self):
        desired=appearance(font_size=18)
        item=plan(appearance={'expected':{'font_size':16},'changes':{'font_size':18}})
        code=exported(appearance=desired)
        result={'status':'FORM_EMBED_EXPORTED_AND_REREAD','kind':'form_embed','form_id':'FORM',
            'configuration_sha256':native.configuration_hash(item),'embed_code':code,
            'embed_sha256':hashlib.sha256(code.encode()).hexdigest(),'export_settings':state(),
            'appearance_settings':desired,'independent_readback':'VERIFIED','settings_persisted':False,
            'installation_verified':False,'behavior_verified':False,'submission_verified':False}
        self.assertEqual(native.validate_receipt(result,item)['appearance_settings'],desired)
        with self.assertRaises(Stop):
            native.validate_receipt({**result,'appearance_settings':appearance(font_size=17)},item)


if __name__=='__main__':unittest.main()
