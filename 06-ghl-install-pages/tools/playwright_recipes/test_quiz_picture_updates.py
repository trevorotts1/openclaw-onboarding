"""Existing Picture Choice updates preserve persisted field and whole-quiz owners."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import recipe_cli
import skill6_playwright as runner
from playwright_recipes import quiz_picture_questions as picture
from test_quiz_picture_questions import step, snapshot, question


def update_step():
    value=step();payload=value['payload']
    payload['pages'][0]['questions']=[picture._authored(question())]
    payload['update_question_index']=0
    payload['questions'][0]['options'][0].update(label='New first choice',image_url='https://example.com/new.png')
    payload['questions'][0]['presentation']={'show_option_label':False,'columns':2}
    return value


class PictureUpdateTests(unittest.TestCase):
    def test_existing_update_compiles_and_rejects_foreign_identity(self):
        value=update_step();payload=deepcopy(value['payload'])
        common={key:payload.pop(key) for key in ('location_id','location_name','start_url')}
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',
            {**common,'configuration':{'picture_choice_questions':payload}}),Path('.'))
        self.assertEqual(job['steps'][0]['payload'],value['payload'])
        for defect in ('index','key','question','new_page','type','swap'):
            bad=update_step();plan=bad['payload']
            if defect=='index':plan['update_question_index']=True
            elif defect=='key':plan['questions'][0]['expected_persisted_unique_key']='contact.other'
            elif defect=='question':plan['questions'][0]['question']='Other question'
            elif defect=='new_page':plan.update(create_page=True,new_page_label='Page 2',target_page=2)
            elif defect=='type':plan['pages'][0]['questions'][0]['field_type']='RADIO'
            else:plan['questions'][0]['options'][0]['label']=plan['questions'][0]['options'][1]['label']
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):picture.validate(bad)
        larger=update_step();larger['payload']['questions'][0]['options'].append(
            {'label':'Fourth','image_url':'https://example.com/four.png','media_button_name':'four.png'})
        picture.validate(larger)

    def test_existing_labels_do_not_use_new_card_default_collision_rules(self):
        value=update_step()
        for index,label in enumerate(('Option2','Option3','Option4')):
            value['payload']['pages'][0]['questions'][0]['options'][index]['label']=label
            value['payload']['questions'][0]['options'][index]['label']=label
        picture.validate(value)
        fresh=step();fresh['payload']['questions']=value['payload']['questions']
        with self.assertRaises(runner.Stop):picture.validate(fresh)

    def test_saved_card_update_preserves_field_and_sibling_metadata(self):
        before=snapshot(persisted=True);desired=update_step()['payload']['questions'][0]
        state={'cards':deepcopy(before['_option_identity'])}
        item=MagicMock();label=item.locator.return_value.nth.return_value.locator.return_value
        label.count.return_value=1;label.is_visible.return_value=True
        label.fill.side_effect=lambda value:state['cards'][0].__setitem__('label',value)
        def media(page,frame,node,index,option):state['cards'][index]['image_url']=option['image_url']
        expected_styles={**before['_styles'],'columns':'2','show_option_label':False}
        def read(frame,node):
            return {**before,'options':[{key:v[key] for key in ('label','image_url')} for v in state['cards']],
                '_option_identity':deepcopy(state['cards']),
                '_styles':expected_styles if state['cards'][0]['image_url'].endswith('new.png') else before['_styles']}
        with patch.object(picture,'_read_picture',side_effect=read), \
                patch.object(picture,'_resize_options',side_effect=lambda frame,node,count:deepcopy(state['cards'])), \
                patch.object(picture,'_choices',side_effect=lambda node:deepcopy(state['cards'])), \
                patch.object(picture,'fill',side_effect=lambda node,value:node.fill(value)), \
                patch.object(picture,'_media',side_effect=media), \
                patch.object(picture,'_write_presentation',return_value=expected_styles):
            result=picture._update_options(MagicMock(),MagicMock(),item,desired)
        self.assertEqual(result['_option_identity'][0]['owner'],before['_option_identity'][0]['owner'])
        self.assertEqual(result['_option_identity'][0]['label'],'New first choice')
        self.assertEqual(result['_custom_field_name'],before['_custom_field_name'])
        self.assertEqual(result['_option_identity'][1:],before['_option_identity'][1:])

    def test_transient_field_refuses_before_option_mutation(self):
        before=snapshot(persisted=True)
        before['_option_identity'][0]['owner']='fb3a89f7-cc72-4971-b277-847367ce0184'
        with patch.object(picture,'_read_picture',return_value=before), \
                patch.object(picture,'_resize_options') as resize:
            with self.assertRaisesRegex(runner.Stop,'persisted field'):
                picture._update_options(MagicMock(),MagicMock(),MagicMock(),update_step()['payload']['questions'][0])
            resize.assert_not_called()

    def test_save_reopens_and_lost_saved_update_refuses(self):
        value=update_step();plan=value['payload'];before=[[snapshot(persisted=True)]]
        changed=deepcopy(before[0][0]);changed.update(options=picture._authored(plan['questions'][0])['options'])
        for i,option in enumerate(changed['options']):changed['_option_identity'][i].update(option)
        changed['_styles'].update(columns='2',show_option_label=False);desired=[[changed]]
        for lost in (False,True):
            page=MagicMock();page.url=plan['start_url'];frame=page.frame_locator.return_value
            save=frame.get_by_role.return_value;save.count.return_value=1;save.is_visible.return_value=True
            save.is_enabled.return_value=True
            with patch.object(picture.native,'_owners',return_value=[(MagicMock(),MagicMock())]), \
                    patch.object(picture.native,'_items'), \
                    patch.object(picture,'_update_options',return_value=changed), \
                    patch.object(picture,'_inventory',side_effect=[desired,before if lost else desired]), \
                    patch.object(picture,'click',side_effect=lambda node:node.click()), \
                    patch.object(picture.native,'reopen_editor') as reopen, \
                    patch.object(picture.native,'_wait_editor_identity'), \
                    patch.object(picture,'_wait_baseline'):
                if lost:
                    with self.assertRaisesRegex(runner.Stop,'did not persist'):
                        picture._configure_update(page,frame,value,plan,before,lambda:None)
                else:
                    receipt=picture._configure_update(page,frame,value,plan,before,lambda:None)
                    self.assertEqual(receipt['field_id'],before[0][0]['_option_identity'][0]['owner'])
                    self.assertFalse(receipt['behavior_verified'])
                reopen.assert_called_once();save.click.assert_called_once()

    def test_filled_media_uses_index_bound_change_image_button(self):
        item,media,button,page,frame=MagicMock(),MagicMock(),MagicMock(),MagicMock(),MagicMock()
        item.locator.return_value.nth.return_value.locator.return_value=media
        media.count.return_value=button.count.return_value=1
        media.is_visible.return_value=button.is_visible.return_value=True
        media.get_attribute.return_value=None;media.locator.return_value=button;button.is_enabled.return_value=True
        dialog=page.get_by_role.return_value;dialog.count.return_value=1;dialog.is_visible.return_value=True
        for node in (dialog.get_by_text.return_value,dialog.get_by_role.return_value,
                     dialog.get_by_role.return_value.locator.return_value):
            node.count.return_value=1;node.is_visible.return_value=True
        before=snapshot(persisted=True)['_option_identity'];after=deepcopy(before);after[0]['image_url']='https://example.com/new.png'
        with patch.object(picture,'_choices',side_effect=[before,after]), \
                patch.object(picture,'click',side_effect=lambda node:node.click()), \
                patch.object(picture,'wait_until',side_effect=lambda predicate,reason:self.assertTrue(predicate())):
            picture._media(page,frame,item,0,update_step()['payload']['questions'][0]['options'][0])
        button.click.assert_called_once();media.click.assert_not_called()


if __name__=='__main__':unittest.main()
