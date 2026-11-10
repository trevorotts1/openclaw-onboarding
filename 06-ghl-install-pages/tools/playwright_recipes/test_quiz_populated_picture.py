"""Native populated Picture Choice capture binds whole profiles and old prefixes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch

from playwright_recipes import quiz_picture_questions as picture
from skill6_playwright import Stop
from test_quiz_creation import CapturedHtml
from test_quiz_picture_questions import PictureDom,cards,question,snapshot,step,SAVED
from test_quiz_text_questions import question as written_question

FIXTURE=Path(__file__).parent/'fixtures/quiz-picture-populated-captured.json'


class CapturedPictureDom(PictureDom):
    def locator(self,selector):
        value=super().locator(selector);return CapturedPictureDom(value.nodes,value.parents)
    def nth(self,index):return CapturedPictureDom([self.nodes[index]],self.parents)
    def get_by_role(self,role,*,name,exact):
        value=super().get_by_role(role,name=name,exact=exact);return CapturedPictureDom(value.nodes,value.parents)
    def input_value(self):
        # HTML's missing radio value attribute has the browser value 'on'.
        node=self.nodes[0]
        if node.tag=='input' and node.get('type')=='radio' and node.get('value') is None:return 'on'
        return super().input_value()


def surface(html):return CapturedPictureDom([CapturedHtml('<section>'+html+'</section>').root])


def styles(value):
    state={switch['owner']:switch['checked']=='true' for switch in value['switches']}
    return {'columns':value['columns'],'image_fit':value['cover'],
        'show_option_label':state['Show option label'],'other_option':state['Other option'],
        'spread_to_columns':state['Spread to Columns'],'multiple_selection_present':'Multiple selection' in state}


class CapturedPictureProfile(unittest.TestCase):
    def test_fresh_before_any_media_has_one_complete_spaced_profile_and_three_empty_images(self):
        capture=json.loads(FIXTURE.read_text());values=picture._choices(surface(capture['freshInitialBeforeMedia']['html']))
        self.assertEqual([value['label'] for value in values],['Option 1','Option 2','Option 3'])
        self.assertEqual([value['image_url'] for value in values],[None,None,None])
        self.assertEqual(picture._default_label_profile([value['label'] for value in values]),('Option 1','Option 2','Option 3'))
        _,old=cards(empty=True)
        self.assertEqual(picture._default_label_profile([value['label'] for value in picture._choices(old)]),tuple(picture.DEFAULT_LABELS))
    def test_partial_profiles_and_rename_collisions_under_either_whole_profile_refuse(self):
        for labels in (['Option1','Option 2','Option3'],['Option 1','Option2','Option 3'],['Option 1','Option 2','Other']):
            with self.subTest(labels=labels),self.assertRaises(Stop):picture._default_label_profile(labels)
        for first in ('Option2','Option 2'):
            value=question();value['options'][0]['label']=first
            with self.subTest(label=first),self.assertRaises(Stop):picture._question(value,new=True)
        before=snapshot();before['options'][1]['label']='Option 2'
        with patch.object(picture,'_read_picture',return_value=before),patch.object(picture,'fill') as fill, \
                patch.object(picture,'_media') as media,self.assertRaises(Stop):
            picture._write(object(),object(),object(),question())
        fill.assert_not_called();media.assert_not_called()
    def test_current_filled_container_requires_its_exact_index_bound_change_image_action(self):
        capture=json.loads(FIXTURE.read_text());html=capture['selectedSavedAndReopened']['html']
        self.assertEqual(capture['selectedSavedAndReopened']['active'],'true')
        for defect in ('role','tabindex','actions','index','aria','type','disabled'):
            tree=CapturedHtml('<section>'+html+'</section>').root
            media=next(node for node in tree.iter() if node.get('data-testid')=='picture-choice-option-media')
            action=next(node for node in media.iter() if node.get('data-testid')=='picture-choice-change-image-0')
            if defect=='role':media.set('role','link')
            elif defect=='tabindex':media.set('tabindex','0')
            elif defect=='actions':next(node for node in media.iter() if node.get('data-testid')=='picture-choice-filled-image-actions').set('data-testid','unbound-actions')
            elif defect=='index':action.set('data-testid','picture-choice-change-image-9')
            elif defect=='aria':action.set('aria-label','Other action')
            elif defect=='type':action.set('type','submit')
            else:action.set('disabled','')
            with self.subTest(defect=defect),self.assertRaises(Stop):picture._choices(CapturedPictureDom([tree]))
        with self.assertRaises(Stop):picture._choices(surface(capture['savedAndReopened']['html']))

    def test_actual_populated_save_reopen_preserves_prefix_media_and_only_mints_new_picture_identity(self):
        capture=json.loads(FIXTURE.read_text());before=capture['beforeSave'];after=capture['savedAndReopened']
        self.assertEqual(before['fields'][:-1],after['fields'][:-1]);self.assertEqual(after['pages'],1)
        self.assertEqual([field['type'] for field in after['fields']],['TEXT','TEXT','LARGE_TEXT','RADIO'])
        old_options=picture._choices(surface(before['html']));new_options=picture._choices(surface(capture['selectedSavedAndReopened']['html']))
        q=question();q.update(question=after['customName'],query_key=after['queryKey'],
            expected_persisted_unique_key=after['identity']['value'])
        q['options']=[{'label':value['label'],'image_url':value['image_url'],
            'media_button_name':catalog['buttonName']} for value,catalog in zip(new_options,capture['approvedMedia'])]
        picture._question(q,new=True)
        def record(stage,options,style):
            return {**picture._authored(q),'unique_key':stage['identity']['value'],
                '_unique_key_enabled':not stage['identity']['disabled'],
                '_unique_key_placeholder':stage['identity']['placeholder'],'_custom_field_name':stage['customName'],
                '_styles':styles(style),'_option_identity':options}
        old=record(before,old_options,before['optionsPanel']);new=record(after,new_options,after['styles'])
        picture._minted(old,new,q)
        self.assertEqual([value['image_url'] for value in new_options],['https://cdn.example/approved-'+str(i)+'.png' for i in (1,2,3)])
        self.assertEqual(new['_styles'],{**old['_styles'],'multiple_selection_present':False})
        for defect in ('media','owner','style'):
            changed=deepcopy(new)
            if defect=='media':changed['_option_identity'][1]['image_url']='https://cdn.example/other.png'
            elif defect=='owner':changed['_option_identity'][1]['owner']='ForeignFieldOwner0000'
            else:changed['_styles']['columns']='2'
            with self.subTest(defect=defect),self.assertRaises(Stop):picture._minted(old,changed,q)


class PopulatedPictureExecution(unittest.TestCase):
    def test_same_page_configuration_keeps_prefix_before_write_and_after_independent_save(self):
        for corruption in (None,'before','after'):
            value=step();prior=[{**written_question('Saved first','saved_first','TEXT'),'_widget_inputs':[]},
                {**written_question('Saved second','saved_second','LARGE_TEXT'),'_widget_inputs':[]}]
            value['payload']['pages'][0]['questions']=picture.choice._properties([prior])[0]
            state={'inventory':[deepcopy(prior)],'saves':0,'writes':0}
            page,frame,item,title,save,label=[MagicMock() for _ in range(6)]
            page.url=value['payload']['start_url'];page.frame_locator.return_value=frame
            title.count.return_value=1;title.input_value.return_value='Exact quiz'
            save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
            label.inner_text.return_value='Picture Choice 103e3j'
            frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else save
            def append(*args,**kwargs):
                state['inventory'][0].append(snapshot())
                if corruption=='before':state['inventory'][0][0]['placeholder']='Changed old prefix'
                return item
            def write(*args):state['writes']+=1;return snapshot()
            def saved(*args,**kwargs):
                state['saves']+=1;state['inventory'][0][-1]=snapshot(persisted=True)
                if corruption=='after':state['inventory'][0][0]['_widget_inputs']=[{'unrequested':'replacement'}]
            save.click.side_effect=saved
            with patch.object(picture,'assert_tenant'),patch.object(picture,'_wait_baseline'), \
                    patch.object(picture.native,'_wait_editor_identity'), \
                    patch.object(picture,'_inventory',side_effect=lambda *args:deepcopy(state['inventory'])), \
                    patch.object(picture.native,'_append_tile',side_effect=append), \
                    patch.object(picture.native,'_item_kind',return_value=(label,'RADIO')), \
                    patch.object(picture.native,'_activate_item'), \
                    patch.object(picture,'_choices',return_value=snapshot()['_option_identity']), \
                    patch.object(picture,'_write',side_effect=write),patch.object(picture.native,'reopen_editor') as reopen, \
                    patch.object(picture,'wait_until',side_effect=lambda fn,reason:self.assertTrue(fn())):
                if corruption:
                    with self.assertRaises(Stop):picture.configure(page,value)
                else:
                    receipt=picture.configure(page,value);self.assertEqual(receipt['field_id'],SAVED)
                    self.assertEqual(receipt['target_page'],1);reopen.assert_called_once()
                    self.assertEqual(state['inventory'][0][:-1],prior)
            self.assertEqual(state['writes'],0 if corruption=='before' else 1)
            self.assertEqual(state['saves'],0 if corruption=='before' else 1)


if __name__=='__main__':unittest.main()
