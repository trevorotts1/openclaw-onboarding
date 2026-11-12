"""Captured Picture Choice card ownership, native mint and runner boundaries."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import recipe_cli
import skill6_playwright as runner
from playwright_recipes import quiz_picture_questions as picture
from test_quiz_page_heading_dom import Dom


UUID = 'fb3a89f7-cc72-4971-b277-847367ce0184'
SAVED = 'GhGmejw7PpqiB2HkNcNQ'


def question():
    return {'field_type':'PICTURE_CHOICE','question':'Choose your direction',
        'placeholder':'','short_label':'','query_key':'chosen_direction','required':False,'hidden':False,
        'expected_persisted_unique_key':'contact.choose_your_direction',
        'options':[{'label':'Choice '+str(index),'image_url':'https://example.com/'+str(index)+'.png',
            'media_button_name':'image'+str(index)+'.png image'+str(index)+'.png Dimension icon'} for index in range(1,4)]}


def step():
    return {'action':'quiz_picture_choices','payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder-v2/QUIZ',
        'expected_quiz_name':'Exact quiz','pages':[{'label':'Page 1','questions':[]}],
        'target_page':1,'questions':[question()],'acknowledge_shared_field_options':True}}


def request():
    payload=step()['payload'];common={key:payload.pop(key) for key in ('location_id','location_name','start_url')}
    return {**common,'configuration':{'picture_choice_questions':payload}}


def proof(step_value=None):
    value=step_value or step();plan=value['payload']
    return {'status':'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED','kind':'quiz_picture_choices',
        'editor_url':plan['start_url'],'configuration_sha256':picture.configuration_hash(value),
        'question_count':1,'target_page':plan['target_page'],'independent_readback':'VERIFIED',
        'dependency_api_used':False,'behavior_verified':False,'submission_verified':False,
        'field_id':SAVED,'persisted_unique_key':question()['expected_persisted_unique_key'],
        'image_urls_sha256':[hashlib.sha256(option['image_url'].encode()).hexdigest() for option in question()['options']]}


class PictureDom(Dom):
    def locator(self,selector):
        value=super().locator(selector);return PictureDom(value.nodes,value.parents)
    def nth(self,index):return PictureDom([self.nodes[index]],self.parents)
    def get_by_role(self,role,*,name,exact):
        if role=='img':
            return PictureDom([node for root in self.nodes for node in list(root.iter())[1:]
                if node.tag=='img' and node.get('alt')==name],self.parents)
        return super().get_by_role(role,name=name,exact=exact)
    def get_attribute(self,name):
        if len(self.nodes)!=1:raise AssertionError('ambiguous fixture attribute')
        return self.nodes[0].get(name)


def cards(owner=UUID,*,empty=False):
    root=ET.Element('section');grid=ET.SubElement(root,'div',{'data-testid':'picture-choice-grid'})
    for index in range(3):
        card=ET.SubElement(grid,'div',{'data-testid':'picture-choice-card'})
        label='Option'+str(index+1) if empty else question()['options'][index]['label']
        ET.SubElement(card,'input',{'type':'radio','disabled':'','value':'on','name':owner,
            'id':owner+'-'+str(index),'aria-label':label})
        ET.SubElement(card,'span',{'data-testid':'picture-choice-option-label-text','id':owner+'-'+str(index)+'-label',
            'contenteditable':'true','role':'textbox'}).text=label
        media=ET.SubElement(card,'div',{'data-testid':'picture-choice-option-media','role':'button','aria-label':'Upload Image'})
        if empty:ET.SubElement(media,'img',{'data-testid':'picture-choice-empty-image','src':'/assets/picture-choice-empty-42ddee2e.svg'})
        else:ET.SubElement(media,'img',{'alt':label,'src':question()['options'][index]['image_url']})
    return root,PictureDom([root])


def snapshot(*,persisted=False):
    q=picture._authored(question());owner=SAVED if persisted else UUID
    return {**q,'unique_key':q['unique_key'] if persisted else '',
        '_custom_field_name':q['question'],'_unique_key_placeholder':'choose_your_direction',
        '_unique_key_enabled':not persisted,
        '_styles':{'columns':'3','image_fit':'Cover','show_option_label':True,'other_option':False,
            'spread_to_columns':True,'multiple_selection_present':not persisted},
        '_option_identity':[{'owner':owner,'id':owner+'-'+str(i),'label':v['label'],'image_url':v['image_url']}
            for i,v in enumerate(q['options'])]}


class PictureChoiceTests(unittest.TestCase):
    def test_exact_native_owner_and_approved_media_are_compiled_without_losing_identity(self):
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',request()),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'quiz_picture_choices')
        self.assertEqual(job['steps'][0]['payload'],step()['payload'])
        new=step();new['payload'].update(create_page=True,new_page_label='Page 2',target_page=2)
        picture.validate(new)

    def test_unimplemented_counts_missing_media_keys_colliding_prior_key_and_foreign_owner_refuse(self):
        for defect in ('count','url','tile','key','prior_key','owner','ordinary','options','mixed_batches'):
            value=step();q=value['payload']['questions'][0]
            if defect=='count':q['options']=q['options'][:1]
            elif defect=='url':q['options'][0]['image_url']='javascript:alert(1)'
            elif defect=='tile':q['options'][0].pop('media_button_name')
            elif defect=='key':q.pop('expected_persisted_unique_key')
            elif defect=='prior_key':
                from test_quiz_text_questions import question as text_question
                value['payload']['pages'][0]['questions']=[text_question('Existing question',q['query_key'],'TEXT')]
            elif defect=='owner':value['payload']['start_url']=value['payload']['start_url'].replace('/LOC/','/OTHER/')
            elif defect=='ordinary':q['field_type']='RADIO'
            elif defect=='options':value['payload']['acknowledge_shared_field_options']=False
            else:
                data=request();data['configuration']={'question_batches':[data['configuration']]*2}
                with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('quizzes.configure',data)
                continue
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):picture.validate(value)

    def test_dom_cards_bind_hyphen_radio_ids_labels_and_canonical_images(self):
        for owner in (UUID,SAVED):
            _,surface=cards(owner)
            values=picture._choices(surface)
            self.assertEqual([v['id'] for v in values],[owner+'-'+str(i) for i in range(3)])
            self.assertEqual([v['image_url'] for v in values],[v['image_url'] for v in question()['options']])
        _,surface=cards(empty=True)
        self.assertEqual([v['image_url'] for v in picture._choices(surface)],[None]*3)

    def test_persisted_unique_key_collision_in_multi_dropdown_namespace_refuses_before_insert(self):
        from test_quiz_multi_dropdown import step as multi_step
        prior=multi_step()['payload']['questions'][0]
        prior['question']='Prior dropdown'
        for key in ('contact.choose_your_direction','CONTACT.CHOOSE_YOUR_DIRECTION'):
            value=step();old=deepcopy(prior);old['unique_key']=key
            value['payload']['pages']=[{'label':'Page 1','questions':[old]},{'label':'Page 2','questions':[]}]
            value['payload']['target_page']=2
            with self.subTest(key=key),self.assertRaisesRegex(runner.Stop,'Unique Key'):
                picture.validate(value)

    def test_dom_wrong_input_name_label_owner_media_url_or_ordinary_radio_shape_refuse(self):
        for defect in ('owner','label','aria','url','grid','disabled','count'):
            root,surface=cards();items=root.findall('.//div[@data-testid="picture-choice-card"]')
            if defect=='owner':items[1].find('input').set('name',SAVED)
            elif defect=='label':items[0].find('span').set('id','unowned-label')
            elif defect=='aria':items[0].find('input').set('aria-label','Other')
            elif defect=='url':items[0].find('.//img').set('src','http://example.com/insecure.png')
            elif defect=='grid':root[0].set('data-testid','ordinary-radio-grid')
            elif defect=='disabled':items[0].find('input').attrib.pop('disabled')
            else:
                root[0].remove(items[2]);root[0].remove(items[1])
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):picture._choices(surface)

    def test_save_mints_only_one_owner_key_and_known_multiple_selection_transition(self):
        picture._minted(snapshot(),snapshot(persisted=True),question())
        for defect in ('label','image','key','owner','styles','custom_name'):
            after=snapshot(persisted=True)
            if defect=='label':after['options'][0]['label']='Changed'
            elif defect=='image':after['_option_identity'][0]['image_url']='https://example.com/other.png'
            elif defect=='key':after['unique_key']='contact.other'
            elif defect=='owner':after['_option_identity'][0]['owner']=UUID
            elif defect=='styles':after['_styles']['multiple_selection_present']=True
            else:after['_custom_field_name']='Other'
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):picture._minted(snapshot(),after,question())

    def test_bound_fresh_receipt_and_completed_replay_execute_no_duplicate_insert(self):
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',request()),Path('.'))
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(picture,'configure',return_value=proof(job['steps'][0])) as write:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
            self.assertEqual(first['status'],'NEEDS_VERIFICATION');self.assertTrue(replay['replayed']);write.assert_called_once()
        for key,value in (('field_id',UUID),('persisted_unique_key','contact.foreign'),('submission_verified',True),
                          ('image_urls_sha256',['0'*64]*3),('question_count',True)):
            invalid=proof();invalid[key]=value
            with self.subTest(key=key),self.assertRaises(runner.Stop):picture.validate_receipt(invalid,step())

    def test_uncertain_picture_write_never_retries_or_falls_back(self):
        job=runner.validate_job(recipe_cli.compile_recipe('quizzes.configure',request()),Path('.'))
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
                patch.object(picture,'configure',side_effect=TimeoutError('uncertain media/save')) as write:
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,root)
            write.assert_called_once()

    def test_local_approved_asset_staging_and_receipt_binding(self):
        from PIL import Image
        import os
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,'approved.png');Image.new('RGB',(2,2),'red').save(path)
            sha=hashlib.sha256(path.read_bytes()).hexdigest();value=step()
            value['payload']['questions'][0]['options'][0]={'label':'Choice 1','local_file':str(path),'sha256':sha}
            self.assertEqual(picture.validate(value)['questions'][0]['options'][0]['sha256'],sha)
            with tempfile.TemporaryDirectory() as stage:
                staged=picture._stage_local_assets(value['payload'],stage)
                self.assertEqual(staged[0][2:],('image/png',sha));self.assertEqual(staged[0][0].read_bytes(),path.read_bytes())
            observed='https://example.com/new-upload.png';receipt=proof()
            receipt['configuration_sha256']=picture.configuration_hash(value)
            receipt['image_urls_sha256'][0]=hashlib.sha256(observed.encode()).hexdigest()
            receipt['uploaded_media']=[{'index':0,'source_sha256':sha,'url':observed}]
            self.assertEqual(picture.validate_receipt(receipt,value),receipt)
            receipt['uploaded_media'][0]['source_sha256']='0'*64
            with self.assertRaises(runner.Stop):picture.validate_receipt(receipt,value)
            path.write_bytes(b'not an image')
            with tempfile.TemporaryDirectory() as stage,self.assertRaises(runner.Stop):
                picture._stage_local_assets(value['payload'],stage)

    def test_styles_preserve_exact_transient_and_persisted_default_switch_owners(self):
        for transient in (True,False):
            names=['Show option label','Multiple selection','Other option','Spread to Columns'] if transient else [
                'Show option label','Other option','Spread to Columns']
            values=[True,False,False,True] if transient else [True,False,True]
            switches=[]
            for name,value in zip(names,values):
                control=MagicMock();control.count.return_value=1;control.is_visible.return_value=True
                control.locator.return_value.inner_text.return_value=name
                control.get_attribute.return_value=str(value).lower();switches.append(control)
            frame=MagicMock();frame.get_by_role.return_value.count.return_value=len(switches)
            frame.get_by_role.return_value.nth.side_effect=lambda index:switches[index]
            columns,cover=MagicMock(),MagicMock()
            for control in (columns,cover):control.count.return_value=1;control.is_visible.return_value=True
            columns.input_value.return_value='3';cover.inner_text.return_value='Cover';cover.get_attribute.return_value='Cover'
            frame.locator.side_effect=lambda selector:columns if selector=='#picture-choice-columns input' else cover
            self.assertEqual(picture._styles(frame)['multiple_selection_present'],transient)
            switches[-1].get_attribute.return_value='false'
            with self.assertRaises(runner.Stop):picture._styles(frame)

    def test_media_selection_requires_exact_approved_tile_thumbnail_and_preserves_siblings(self):
        for defect in (None,'thumbnail','sibling'):
            page,frame,item,card,media,dialog,tile,image,title=[MagicMock() for _ in range(9)]
            for node in (media,dialog,tile,image,title):node.count.return_value=1;node.is_visible.return_value=True
            page.get_by_role.return_value=dialog;dialog.get_by_text.return_value=title
            dialog.get_by_role.return_value=tile;tile.locator.return_value=image
            item.locator.return_value.nth.return_value=card;card.locator.return_value=media
            current=snapshot()['_option_identity']
            for option in current:option['image_url']=None
            state={'options':deepcopy(current)};option=question()['options'][0]
            if defect=='thumbnail':image.count.return_value=0
            def selected(*args,**kwargs):
                state['options'][0]['image_url']=option['image_url']
                if defect=='sibling':state['options'][1]['label']='Changed sibling'
            tile.dblclick.side_effect=selected
            def wait(predicate,reason):
                if not predicate():raise runner.Stop(reason)
            with patch.object(picture,'_choices',side_effect=lambda *a:deepcopy(state['options'])), \
                    patch.object(picture,'wait_until',side_effect=wait):
                if defect:
                    with self.assertRaises(runner.Stop):picture._media(page,frame,item,0,option)
                else:picture._media(page,frame,item,0,option)
            if defect=='thumbnail':tile.dblclick.assert_not_called()
            else:tile.dblclick.assert_called_once()
            self.assertIn('u_https://example.com/1.png',tile.locator.call_args.args[0])

    def test_configure_independent_save_binds_new_owner_and_refuses_collateral_changes(self):
        for collateral in (False,True):
            value=step();value['payload'].update(create_page=True,new_page_label='Page 2',target_page=2)
            runtime=deepcopy(value['payload']);runtime['pages'].append({'label':'Page 2','questions':[]})
            state={'inventory':[[]],'saves':0}
            page,frame,item=MagicMock(),MagicMock(),MagicMock();page.url=value['payload']['start_url']
            page.frame_locator.return_value=frame
            title,save,label=MagicMock(),MagicMock(),MagicMock()
            title.count.return_value=1;title.input_value.return_value='Exact quiz'
            save.count.return_value=1;save.is_visible.return_value=True;save.is_enabled.return_value=True
            label.inner_text.return_value='Picture Choice 103e3j'
            frame.get_by_role.side_effect=lambda role,**kwargs:title if role=='textbox' else save
            def append(*args,**kwargs):state['inventory']=[[],[snapshot()]];return item
            def write(*args):return snapshot()
            def saved(*args,**kwargs):
                state['saves']+=1;state['inventory']=[[],[snapshot(persisted=True)]]
                if collateral:state['inventory'][0]=[{'field_type':'TEXT','question':'Unexpected old-page mutation'}]
            save.click.side_effect=saved
            with patch.object(picture,'assert_tenant'),patch.object(picture,'_wait_baseline'), \
                    patch.object(picture.native,'_wait_editor_identity'),patch.object(picture,'_inventory',side_effect=lambda *a:deepcopy(state['inventory'])), \
                    patch.object(picture,'_target_page',return_value=(runtime,[[],[]])), \
                    patch.object(picture.native,'_append_tile',side_effect=append),patch.object(picture.native,'_item_kind',return_value=(label,'RADIO')), \
                    patch.object(picture.native,'_activate_item'),patch.object(picture,'_choices',return_value=snapshot()['_option_identity']), \
                    patch.object(picture,'_write',side_effect=write),patch.object(picture.native,'reopen_editor'), \
                    patch.object(picture,'wait_until',side_effect=lambda predicate,reason:self.assertTrue(predicate())):
                if collateral:
                    with self.assertRaises(runner.Stop):picture.configure(page,value)
                else:
                    result=picture.configure(page,value)
                    self.assertEqual(result['field_id'],SAVED)
                    self.assertEqual(result['persisted_unique_key'],'contact.choose_your_direction')
            self.assertEqual(state['saves'],1)


if __name__=='__main__':unittest.main()
