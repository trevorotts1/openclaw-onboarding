"""New Score uses captured local identity, not unrelated Advanced metadata."""
from copy import deepcopy
from pathlib import Path
import importlib
import unittest
from unittest.mock import MagicMock,patch
import recipe_cli
import skill6_playwright as runner
from test_form_widget_families import inputs,receipt
native=importlib.import_module('playwright_recipes.form_widget_families')

class ScoreCreation(unittest.TestCase):
    def test_new_score_compiles_without_contact_metadata(self):
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs('score')),Path('.'))['steps'][0]
        self.assertIsNone(spec['payload']['fields'][0]['index'])
        native.validate_receipt(receipt(spec),spec)
        self.assertNotIn('unique_key',native.PROFILES['score']['properties'])
        self.assertNotIn('custom_field_name',native.PROFILES['score']['properties'])

    def test_new_rating_is_queryless_and_requires_no_contact_metadata(self):
        spec=runner.validate_job(recipe_cli.compile_recipe('forms.configure',inputs('rating')),Path('.'))['steps'][0]
        self.assertIsNone(spec['payload']['fields'][0]['index'])
        native.validate_receipt(receipt(spec),spec)
        duplicate=deepcopy(spec)
        duplicate['payload']['fields'].append(deepcopy(duplicate['payload']['fields'][0]))
        with self.assertRaises(runner.Stop):native.validate(duplicate)

    def test_one_native_append_reads_generated_local_key_and_preserves_sibling(self):
        frame=MagicMock();add=MagicMock();dialog=MagicMock();tile=MagicMock();target=MagicMock();items=MagicMock();item=MagicMock()
        for node in (add,dialog,tile,target):
            node.count.return_value=1;node.is_visible.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:dialog if role=='dialog' else add
        frame.locator.side_effect=lambda selector:items if selector==native.CANVAS_ITEMS else target
        items.count.return_value=2;items.nth.return_value=item
        dialog.get_by_text.return_value.count.return_value=1
        dialog.locator.return_value.filter.return_value=tile
        target.bounding_box.return_value={'width':100,'height':40}
        before=[{'types':['submit']}];after=[{'types':['SCORE']},*deepcopy(before)]
        defaults={**deepcopy(native.PROFILES['score']['defaults']),'label':'Score 1p0l','query_key':'score_1p0l'}
        with patch.object(native,'_close_initial'),patch.object(native,'_snapshot',return_value=after),patch.object(native,'_read',return_value=defaults):
            self.assertEqual(native._append(frame,'score',before),(0,item,defaults))
        tile.locator.return_value.drag_to.assert_called_once()
        rating={**deepcopy(native.PROFILES['rating']['defaults']),'label':'Rating rat584 11o3'}
        item.locator.return_value.inner_text.return_value=rating['label']
        rating_after=[{'types':['RATING']},*deepcopy(before)]
        with patch.object(native,'_close_initial'),patch.object(native,'_snapshot',return_value=rating_after),patch.object(native,'_read',return_value=rating):
            self.assertEqual(native._append(frame,'rating',before),(0,item,rating))
        changed={**rating,'lowest_label':'Concurrent edit'}
        with patch.object(native,'_close_initial'),patch.object(native,'_snapshot',return_value=rating_after),patch.object(native,'_read',return_value=changed),self.assertRaisesRegex(runner.Stop,'generated label/defaults'):
            native._append(frame,'rating',before)
        wrong={**defaults,'query_key':'unbound_score'}
        with patch.object(native,'_close_initial'),patch.object(native,'_snapshot',return_value=after),patch.object(native,'_read',return_value=wrong),self.assertRaisesRegex(runner.Stop,'generated identity'):
            native._append(frame,'score',before)

if __name__=='__main__':unittest.main()
