"""Bot-protection authoring configures the widget, never the human challenge."""
from copy import deepcopy
from pathlib import Path
import importlib
import unittest
from unittest.mock import MagicMock, patch
import recipe_cli
import skill6_playwright as runner
from test_form_widget_families import inputs, properties, receipt

native=importlib.import_module('playwright_recipes.form_widget_families')
placement=importlib.import_module('playwright_recipes.field_placement')

class BotProtection(unittest.TestCase):
    def test_create_and_edit_bind_single_queryless_interactive_widget(self):
        source=inputs('bot_protection')
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))['steps'][0]
        native.validate_receipt(receipt(spec),spec)
        self.assertEqual(native._identity('bot_protection',properties('bot_protection')),'@captcha')
        self.assertIn('captcha',placement.QUERYLESS_TYPES)
        for key,value in (('query_key','invented'),('verification_mode','invisible')):
            bad=deepcopy(source);bad['widget_fields']['fields'][0]['desired'][key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)
        duplicate=deepcopy(source);duplicate['widget_fields']['fields'].append(deepcopy(duplicate['widget_fields']['fields'][0]))
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',duplicate)

    def test_captured_dynamic_mode_owner_is_read_without_touching_the_challenge(self):
        frame=MagicMock();item=MagicMock();profile=native.PROFILES['bot_protection']
        label=MagicMock();label.count.return_value=1;label.is_visible.return_value=True;label.input_value.return_value='Bot protection'
        missing=MagicMock();missing.count.return_value=0
        sidebar=MagicMock();selected=sidebar.locator.return_value
        selected.count.return_value=1;selected.is_visible.return_value=True;selected.get_attribute.return_value='Interactive'
        frame.locator.side_effect=lambda selector:label if selector=='#captchaLabel input' else sidebar if selector=='#form_custom_sidebar' else missing
        with patch.object(native,'_activate',return_value=profile),patch.object(native,'_close_properties'),patch.object(native,'click') as click:
            self.assertEqual(native._read(frame,item,'bot_protection'),{'label':'Bot protection','verification_mode':'interactive'})
        sidebar.locator.assert_called_once_with('[id^="captcha-verification-mode-"] .n-base-selection-input')
        click.assert_not_called();item.get_by_role.assert_not_called()

    def test_parent_creation_preserves_contact_inventory_and_saves_reopens(self):
        spec=recipe_cli.compile_recipe('forms.configure',inputs('bot_protection'))['steps'][0]
        frame=MagicMock();page=MagicMock();save=frame.get_by_role.return_value
        save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
        # These fixtures contain no HTML widget, so outer Save has no HTML warning dialog.
        frame.locator.return_value.count.return_value=0
        original=[{'types':['text']},{'types':['submit']}]
        state={'created':False,'properties':None};item=MagicMock()
        def snapshot(*args):
            return [deepcopy(original[0])]+([{'types':['captcha'],'label':state['properties']['label']}] if state['created'] else [])+[deepcopy(original[1])]
        def inventory(*args):
            return [{'kind':'bot_protection','index':2,'properties':deepcopy(state['properties'])}] if state['created'] else []
        def append(*args):state.update(created=True,properties=deepcopy(native.PROFILES['bot_protection']['defaults']));return 1,item,deepcopy(state['properties'])
        def write(*args):state['properties']=deepcopy(args[-1])
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',side_effect=inventory),patch.object(native,'_snapshot',side_effect=snapshot),patch.object(native,'_append',side_effect=append) as created,patch.object(native,'_write',side_effect=write),patch.object(placement,'_inventory',return_value={'first_name':'text'}),patch.object(native,'reopen_editor') as reopen:
            done=native.configure(page,spec)
        created.assert_called_once();save.click.assert_called_once();reopen.assert_called_once()
        page.wait_for_load_state.assert_called_once_with('networkidle',timeout=45000)
        self.assertEqual(done['fields'][0]['properties'],properties('bot_protection'))
        self.assertEqual(done['saved_snapshot'][0],original[0])

if __name__=='__main__':unittest.main()
