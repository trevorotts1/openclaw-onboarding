"""Captured existing HTML source updates remain bound to native CodeMirror."""
from copy import deepcopy
from pathlib import Path
import importlib
import unittest
from unittest.mock import MagicMock, patch
import recipe_cli
import skill6_playwright as runner
from test_form_widget_families import inputs, receipt

native=importlib.import_module('playwright_recipes.form_widget_families')
html=importlib.import_module('playwright_recipes.form_html')

class ExistingHtml(unittest.TestCase):
    def test_existing_label_owned_html_compiles_without_inventing_contact_identity(self):
        source=inputs('html')
        previous=deepcopy(source['widget_fields']['fields'][0]['desired']);previous['html']='<p>Before</p>'
        source['widget_fields']['expected_fields']=[{'kind':'html','index':1,'properties':previous}]
        source['widget_fields']['fields'][0]['index']=1
        source['widget_fields']['fields'][0]['desired']['html']='<p>After</p>'
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))['steps'][0]
        native.validate_receipt(receipt(spec),spec)
        for mutation in ('query',):
            bad=deepcopy(source)
            if mutation=='newline':bad['widget_fields']['fields'][0]['desired']['html']='<p>Line1</p>\n<p>Line2</p>'
            else:bad['widget_fields']['fields'][0]['desired']['query_key']='invented'
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('forms.configure',bad)

    def modal(self,state):
        modal=MagicMock();lines=MagicMock();editor=MagicMock();save=MagicMock();cancel=MagicMock();box=MagicMock();title=MagicMock()
        for node in (lines,save,cancel,box,title):node.count.return_value=1;node.is_visible.return_value=True
        lines.inner_text.side_effect=lambda:state['source'];editor.count.return_value=1
        editor.press_sequentially.side_effect=lambda value:state.update(source=value)
        editor.press.side_effect=lambda key:state.update(source='') if key=='Backspace' else None
        modal.locator.side_effect=lambda selector:{'pre.CodeMirror-line':lines,'.CodeMirror':box,'.CodeMirror textarea':editor,'.title':title,
            '#modal-footer-btn-positive-action':save,'#modal-footer-btn-negative-action':cancel}[selector]
        return modal,lines,editor,save,cancel

    def test_native_editor_replaces_source_once_then_saves_and_unknown_source_refuses(self):
        state={'source':'<p>Before</p>'};modal,lines,editor,save,cancel=self.modal(state)
        with patch.object(html,'_open',return_value=modal),patch.object(html,'_source',side_effect=lambda _:state['source']),patch.object(html,'click') as click:
            html.write_html(MagicMock(),'<p>Before</p>','<p>After</p>\n<p>Second</p>')
        self.assertEqual(editor.press.call_args_list,[unittest.mock.call('ControlOrMeta+A')])
        editor.press_sequentially.assert_called_once_with('<p>After</p>\n<p>Second</p>')
        self.assertIn(unittest.mock.call(modal.locator('.title')),click.call_args_list)
        self.assertIn(unittest.mock.call(save),click.call_args_list)
        self.assertNotIn(unittest.mock.call(cancel),click.call_args_list)
        editor.press_sequentially.reset_mock();editor.press.reset_mock()
        with patch.object(html,'_open',return_value=modal),patch.object(html,'_source',side_effect=lambda _:state['source']),patch.object(html,'click') as click,self.assertRaisesRegex(runner.Stop,'preflight'):
            html.write_html(MagicMock(),'<p>Before</p>','<p>Another</p>')
        editor.press.assert_not_called();editor.press_sequentially.assert_not_called();click.assert_not_called()

    def test_new_html_compiles_and_exact_empty_marker_is_normalized(self):
        source=inputs('html');source['widget_fields']['fields'][0]['desired']['html']='<p>New content</p>'
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',source),Path('.'))['steps'][0]
        native.validate_receipt(receipt(spec),spec)
        self.assertEqual(html.validate_html('<p>one</p>\n<p>two</p>'),'<p>one</p>\n<p>two</p>')

    def test_numbered_lines_read_and_virtualization_refuses(self):
        modal=MagicMock(); box=MagicMock(); editor=MagicMock(); rows=MagicMock()
        box.count.return_value=1;box.is_visible.return_value=True;editor.count.return_value=1
        nodes=[]
        for n,value in enumerate(('<p>one</p>','','<p>three</p>'),1):
            row=MagicMock();number=MagicMock();line=MagicMock()
            number.count.return_value=1;number.inner_text.return_value=str(n)
            line.count.return_value=1;line.inner_text.return_value=value
            row.locator.side_effect=lambda selector,number=number,line=line: number if selector=='.CodeMirror-linenumber' else line
            nodes.append(row)
        rows.count.return_value=3;rows.nth.side_effect=lambda i:nodes[i]
        modal.locator.side_effect=lambda selector:{'.CodeMirror':box,'.CodeMirror textarea':editor,'.CodeMirror-code > div':rows}[selector]
        with patch.object(html,'click'):
            self.assertEqual(html._source(modal),'<p>one</p>\n\n<p>three</p>')
            nodes[1].locator('.CodeMirror-linenumber').inner_text.return_value='5'
            with self.assertRaisesRegex(runner.Stop,'virtualized'):html._source(modal)

    def test_empty_source_explicitly_deletes_selection(self):
        state={'source':'<p>Remove</p>'};modal,lines,editor,save,cancel=self.modal(state)
        with patch.object(html,'_open',return_value=modal),patch.object(html,'_source',side_effect=lambda _:state['source']),patch.object(html,'click'):
            html.write_html(MagicMock(),state['source'],'')
        self.assertEqual(editor.press.call_args_list,[unittest.mock.call('ControlOrMeta+A'),unittest.mock.call('Backspace')])
        editor.press_sequentially.assert_not_called()

    def test_read_and_unchanged_html_cancel_without_rule_or_code_save(self):
        state={'source':'<p>Unchanged</p>'};modal,lines,editor,save,cancel=self.modal(state)
        with patch.object(html,'_open',return_value=modal),patch.object(html,'_source',side_effect=lambda _:state['source']),patch.object(html,'click') as click:
            self.assertEqual(html.read_html(MagicMock()),state['source'])
            html.write_html(MagicMock(),state['source'],state['source'])
        self.assertEqual(click.call_args_list,[unittest.mock.call(cancel),unittest.mock.call(cancel)])
        editor.press.assert_not_called();editor.press_sequentially.assert_not_called()

    def test_only_exact_html_save_warning_is_confirmed(self):
        frame=MagicMock();dialog=MagicMock();title=MagicMock();description=MagicMock();proceed=MagicMock()
        for item in (dialog,title,description,proceed):item.count.return_value=1;item.is_visible.return_value=True
        frame.locator.return_value=dialog
        dialog.locator.side_effect=lambda selector:title if selector=='.title' else description
        title.inner_text.return_value='Alert!'
        description.inner_text.return_value=('Third-party scripts inside the HTML block can provide powerful functionality, but they also bring risks '
            'to privacy, security, performance and page behavior. Therefore, we recommend that you to review the '
            'contents of this script before saving it to the form.')
        dialog.get_by_role.return_value=proceed
        with patch.object(html,'click') as click:
            html.confirm_save_warning(frame);click.assert_called_once_with(proceed)
            description.inner_text.return_value='Unrelated warning'
            with self.assertRaisesRegex(runner.Stop,'Unrecognized'):html.confirm_save_warning(frame)

if __name__=='__main__':unittest.main()
