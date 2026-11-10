"""Captured palette and icon controls generate per-export artifacts only."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

import form_embed as native
import editor_replay
import recipe_cli
import skill6_playwright as runner
from test_form_embed import appearance,exported,plan,state


def appearance_plan():
    return plan(appearance={'expected':{'button_type':'text','button_color':'#101828','button_icon':'chat'},
        'changes':{'button_type':'textIcon','button_color':'#188BF6FF','button_icon':'mail'}})


def code(props,**changes):
    layout=native._layout_from_code(exported(appearance=props))
    color=props.get('button_color','#101828')
    layout.update(buttonColor=color.upper()+('FF' if len(color)==7 else ''),buttonIcon=props.get('button_icon','chat'))
    layout.update(changes)
    return exported(appearance=props,**{'data-layout':json.dumps(layout).replace('"',"'")})



class ColorIconTests(unittest.TestCase):
    def test_schema_normalizes_native_opaque_rgba_without_changing_legacy_hash(self):
        item=appearance_plan();validated=native.validate(item)
        self.assertEqual(validated['integration']['appearance']['changes']['button_color'],'#188bf6')
        old=plan(appearance={'expected':{'font_size':16},'changes':{'font_size':18}})
        expected=hashlib.sha256(json.dumps(old['integration'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(native.configuration_hash(old),expected)
        for value in ('#188bf680','#fff','red','rgba(1,2,3,1)',True):
            data=deepcopy(item);data['integration']['appearance']['changes']['button_color']=value
            with self.subTest(value=value),self.assertRaises(runner.Stop):native.validate(data)
        data=deepcopy(item);data['integration']['appearance']['changes']['button_icon']='guessed_icon'
        with self.assertRaises(runner.Stop):native.validate(data)
        self.assertEqual(native.BUTTON_ICONS['mail'],'Mail');self.assertEqual(len(native.BUTTON_ICONS),67)

    def test_palette_selection_uses_existing_unique_rgb_tile_and_never_adds_or_saves(self):
        import playwright_recipes.skill6_playwright as core
        current={'color':'#101828'};events=[]
        trigger=Mock();tile=Mock();swatch=Mock();choice=Mock();palette=Mock();tiles=Mock();frame=Mock()
        for control in (tile,swatch,choice,palette):control.count.return_value=1;control.is_visible.return_value=True
        swatch.get_attribute.return_value='background: rgb(24, 139, 246);'
        tile.locator.side_effect=lambda selector:swatch if selector=='.hr-swatch-tile__pad-inner' else choice
        tiles.count.return_value=1;tiles.nth.return_value=tile;palette.locator.return_value=tiles
        frame.locator.return_value.filter.return_value=palette
        def click(control):
            events.append(control)
            if control is choice:current['color']='#188bf6'
        with patch.object(native,'_button_color',side_effect=lambda _:(current['color'],trigger)), \
                patch.object(core,'click',side_effect=click),patch.object(core,'wait_until',side_effect=lambda fn,msg:fn()):
            native._write_button_color(frame,'#101828','#188bf6',lambda:None)
            self.assertEqual(events,[trigger,choice])
            current['color']='#101828';events.clear()
            with self.assertRaisesRegex(runner.Stop,'NEEDS_PALETTE_COLOR'):
                native._write_button_color(frame,'#101828','#abcdef',lambda:None)
            self.assertEqual(events,[trigger])
        self.assertFalse(any('Save' in str(call) or 'Add' in str(call) for call in frame.get_by_role.call_args_list))

    def test_icon_selection_uses_captured_code_label_search_and_checks_readback(self):
        import playwright_recipes.skill6_playwright as core
        current={'icon':'chat','expanded':'false'};events=[];control=Mock();search=Mock();option=Mock();frame=Mock()
        for node in (search,option):node.count.return_value=1;node.is_visible.return_value=True
        control.get_attribute.side_effect=lambda _:current['expanded']
        frame.get_by_role.side_effect=lambda role,**kwargs:search if role=='textbox' else option
        def click(node):
            events.append(node)
            if node is control:current['expanded']='true'
            else:current['icon']='mail';current['expanded']='false'
        with patch.object(native,'_button_icon',side_effect=lambda _,kind:(current['icon'],control)), \
                patch.object(core,'click',side_effect=click),patch.object(core,'fill') as fill, \
                patch.object(core,'wait_until',side_effect=lambda fn,msg:fn()):
            native._write_button_icon(frame,'textIcon','chat','mail',lambda:None)
            self.assertEqual(events,[control,option]);fill.assert_called_once_with(search,'Mail')
            with self.assertRaises(runner.Stop):native._write_button_icon(frame,'text','chat','mail',lambda:None)

    def test_metadata_requires_exact_color_icon_and_preserves_unrequested_layout_properties(self):
        before=appearance(button_color='#101828',button_icon='chat')
        desired=appearance(button_color='#188bf6',button_icon='mail',button_type='textIcon')
        config=native.validate(appearance_plan())['integration'];after=code(desired)
        native.verify_export_configuration(after,config,state(),desired)
        native._preserved_layout(code(before),after,state(),state(),before,desired)
        for altered in (after.replace('#188BF6FF','#000000FF'),code(desired,buttonIcon='chat')):
            with self.assertRaises(runner.Stop):native.verify_export_configuration(altered,config,state(),desired)
        with self.assertRaisesRegex(runner.Stop,'unrequested'):
            native._preserved_layout(code(before),code(desired,allowMinimize=False),state(),state(),before,desired)

    def test_full_export_lifecycle_and_compiled_replay_retain_artifact_without_form_save(self):
        import playwright_recipes.skill6_playwright as core
        import playwright_recipes.field_placement as fields
        item=appearance_plan();settings=state();current=appearance(button_color='#101828',button_icon='chat')
        expected=appearance(button_color='#188bf6',button_icon='mail',button_type='textIcon')
        title=Mock();title.count.return_value=1;title.is_visible.return_value=True;title.input_value.return_value='Authored Form'
        tab=Mock();tab.count.return_value=1;tab.is_visible.return_value=True
        frame=Mock();frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else tab
        page=Mock();page.url='https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM'
        exports=[]
        def export(_,config,desired,props):
            exports.append(deepcopy(props))
            return native.verify_export_configuration(code(props),config,desired,props)
        with ExitStack() as stack:
            stack.enter_context(patch.object(core,'form_builder',return_value=frame));stack.enter_context(patch.object(core,'click'))
            stack.enter_context(patch.object(fields,'_close_initial'));stack.enter_context(patch.object(native,'_read',return_value=settings))
            stack.enter_context(patch.object(native,'_general',return_value=(settings,{})));stack.enter_context(patch.object(native,'_advanced',return_value=(settings,{})))
            stack.enter_context(patch.object(native,'_appearance',side_effect=lambda *args,**kwargs:(deepcopy(current),{})))
            stack.enter_context(patch.object(native,'_write_appearance',side_effect=lambda _,old,new,identity:current.update(deepcopy(new))))
            stack.enter_context(patch.object(native,'_export',side_effect=export));stack.enter_context(patch.object(core,'wait_until',side_effect=lambda fn,msg:fn()))
            result=native.configure(page,item)
        self.assertEqual(exports,[appearance(button_color='#101828',button_icon='chat'),expected,expected])
        self.assertEqual(result['appearance_settings'],expected)
        self.assertIs(result['settings_persisted'],False);self.assertIs(result['installation_verified'],False)
        requested=[call.kwargs.get('name') for call in frame.get_by_role.call_args_list]
        self.assertNotIn('Save',requested);self.assertNotIn('Publish',requested)
        inputs={'location_id':'LOC','location_name':'Fixture','start_url':page.url,'integration':item['integration']}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs),Path('.'));step=job['steps'][0]
        safe=editor_replay._result(step,result,job)
        self.assertEqual(safe['appearance_settings'],expected)
        self.assertEqual(safe['embed_code'],result['embed_code'])
        with self.assertRaises(runner.Stop):native.validate_receipt({**result,'appearance_settings':appearance(button_type='textIcon')},item)
        with self.assertRaises(runner.Stop):native.validate_receipt({**result,'settings_persisted':True},item)


if __name__=='__main__':unittest.main()
