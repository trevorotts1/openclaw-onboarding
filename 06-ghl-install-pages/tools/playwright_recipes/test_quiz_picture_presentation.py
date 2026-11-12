"""Measured Picture Choice labels/column controls retain protected presentation."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
from playwright_recipes import quiz_picture_questions as picture
import recipe_cli
import skill6_playwright as runner
from test_quiz_picture_questions import question,request


class PicturePresentationTests(unittest.TestCase):
    def surface(self,*,disabled=False,drift=False):
        frame=MagicMock();collection=frame.get_by_role.return_value
        names=['Show option label','Multiple selection','Other option','Spread to Columns']
        state={'switches':[True,False,False,True],'columns':'3'};switches=[]
        for i,name in enumerate(names):
            node=MagicMock();node.count.return_value=1;node.is_visible.return_value=True
            node.is_enabled.return_value=not disabled
            node.locator.return_value.inner_text.return_value=name
            node.get_attribute.side_effect=lambda key,i=i:str(state['switches'][i]).lower() if key=='aria-checked' else None
            def click(i=i):
                state['switches'][i]=not state['switches'][i]
                if drift:state['switches'][2]=True
            node.click.side_effect=click;switches.append(node)
        collection.count.return_value=4;collection.nth.side_effect=lambda i:switches[i]
        columns,cover=MagicMock(),MagicMock()
        for node in (columns,cover):node.count.return_value=1;node.is_visible.return_value=True
        columns.is_enabled.return_value=not disabled
        columns.input_value.side_effect=lambda:state['columns'];columns.fill.side_effect=lambda value:state.__setitem__('columns',value)
        cover.inner_text.return_value='Cover';cover.get_attribute.return_value='Cover'
        frame.locator.side_effect=lambda selector:columns if selector=='#picture-choice-columns input' else cover
        return frame,state

    def test_measured_presentation_routes_and_authored_parent_identity_keeps_style_in_hash(self):
        value=request();q=value['configuration']['picture_choice_questions']['questions'][0]
        q['presentation']={'show_option_label':False,'columns':2}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',value),Path('.'))
        self.assertEqual(job['steps'][0]['payload']['questions'][0]['presentation'],q['presentation'])
        self.assertNotIn('presentation',picture._authored(q))
        self.assertNotEqual(picture.configuration_hash(job['steps'][0]),picture.configuration_hash(
            recipe_cli.compile_recipe('quizzes.configure',request())['steps'][0]))
        for changes in ({'show_option_label':'false','columns':2},{'show_option_label':False,'columns':0},
                        {'show_option_label':False,'columns':2,'image_fit':'Invented'}):
            changed=deepcopy(value);changed['configuration']['picture_choice_questions']['questions'][0]['presentation']=changes
            with self.subTest(changes=changes),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('quizzes.configure',changed)

    def test_label_and_columns_write_once_and_protected_switch_or_disabled_control_refuse(self):
        for disabled,drift in ((False,False),(True,False),(False,True)):
            frame,state=self.surface(disabled=disabled,drift=drift)
            with patch.object(picture,'_open_properties'),patch.object(picture,'_tab'), \
                    patch.object(picture.native,'_close_properties'), \
                    patch.object(picture,'click',side_effect=lambda node:node.click()), \
                    patch.object(picture,'fill',side_effect=lambda node,value:node.fill(value)):
                if disabled or drift:
                    with self.assertRaises(runner.Stop):picture._write_presentation(frame,MagicMock(),{'show_option_label':False,'columns':2})
                else:
                    result=picture._write_presentation(frame,MagicMock(),{'show_option_label':False,'columns':2})
                    self.assertEqual(result['columns'],'2');self.assertFalse(result['show_option_label'])
                    self.assertFalse(result['other_option']);self.assertTrue(result['spread_to_columns'])
                    self.assertEqual(result['image_fit'],'Cover')
            if disabled:self.assertEqual(state,{'switches':[True,False,False,True],'columns':'3'})


if __name__=='__main__':unittest.main()
