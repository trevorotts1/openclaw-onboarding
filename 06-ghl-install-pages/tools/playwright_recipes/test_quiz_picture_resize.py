"""Indexed Picture Choice count changes retain all existing card ownership."""
from copy import deepcopy
import unittest
from unittest.mock import MagicMock,patch
from playwright_recipes import quiz_picture_questions as picture
from skill6_playwright import Stop
from test_quiz_picture_questions import question


class PictureResizeTests(unittest.TestCase):
    def test_variable_count_schema_preserves_explicit_ordered_media(self):
        for count in (2,4,8):
            value=question();value['options']=[{'label':'Choice '+str(i),
                'image_url':'https://example.com/'+str(i)+'.png','media_button_name':'Approved '+str(i)} for i in range(count)]
            self.assertEqual(picture._question(value,new=True),value)
        for count in (1,51):
            value=question();value['options']=[{'label':'Choice '+str(i),
                'image_url':'https://example.com/'+str(i)+'.png','media_button_name':'Approved '+str(i)} for i in range(count)]
            with self.assertRaises(Stop):picture._question(value,new=True)

    def test_index_bound_tail_add_delete_and_foreign_delta_refusal(self):
        for target,corrupt,other in ((2,False,False),(5,False,True),(4,True,False)):
            owner='FixturePictureOwner1';state={'options':[{'id':owner+'-'+str(i),'owner':owner,
                'label':'Option '+str(i+1),'image_url':None} for i in range(3)]}
            item,collection,control,card=MagicMock(),MagicMock(),MagicMock(),MagicMock()
            control.count.return_value=1;control.is_visible.return_value=True;control.is_enabled.return_value=True
            collection.count.side_effect=lambda:len(state['options'])+int(other);collection.nth.return_value=card
            other_image=MagicMock();other_image.count.return_value=int(other)
            card.locator.return_value=control
            item.locator.side_effect=lambda selector:collection if selector=='[data-testid="picture-choice-card"]' else other_image if selector=='[data-testid="picture-choice-other-image"]' else control
            def mutate():
                count=len(state['options'])
                if count<target:state['options'].append({'id':owner+'-'+str(count),'owner':owner,'label':'New option','image_url':None})
                else:state['options'].pop()
                if corrupt:state['options'][0]['image_url']='https://example.com/foreign.png'
            control.click.side_effect=mutate
            with patch.object(picture,'_choices',side_effect=lambda node:deepcopy(state['options'])), \
                    patch.object(picture,'click',side_effect=lambda node:node.click()), \
                    patch.object(picture,'wait_until',side_effect=lambda pred,reason:self.assertTrue(pred())):
                if corrupt:
                    with self.assertRaises(Stop):picture._resize_options(MagicMock(),item,target)
                else:
                    result=picture._resize_options(MagicMock(),item,target)
                    self.assertEqual(len(result),target);self.assertEqual(result[0]['label'],'Option 1')
            self.assertEqual(control.click.call_count,1 if corrupt else abs(target-3))


if __name__=='__main__':unittest.main()
