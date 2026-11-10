"""New marketing quiz shells compose exact typed question/score/result journals."""
from contextlib import ExitStack
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import host
import recipe_cli
import skill6_playwright as runner
from playwright_recipes import quiz_creation as front, quiz_choice_questions as choice, quiz_written_questions as written, quiz_results
from test_quiz_choice_questions import new_question
from test_quiz_text_questions import question
from test_quiz_loading_readiness import LoadedDom


def inputs():
    first=new_question();second=question('What will you do next?','next_step','TEXT')
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/quiz-builder/main',
        'name':'New marketing quiz','allow_creation':True,'configuration':{
            'question_batches':[
                {'multiple_choice_questions':{'questions':[first],'acknowledge_shared_field_options':True}},
                {'written_answer_questions':{'questions':[second]}}],
            'scoring':{'expected_question_count':2,'questions':[{'index':0,'expected_question':first['question'],
                'expected_query_key':first['query_key'],'options':[
                    {'label':label,'category':'Overall Only','score':index*10} for index,label in enumerate(first['options'])]}]},
            'result_page':{'expected':{'business_name':'Fixture business'},'changes':{'business_name':'Authored business'}}}}


class CapturedHtml(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True);self.root=ET.Element('document');self.stack=[self.root];self.feed(text)
    def handle_starttag(self,tag,attrs):
        node=ET.SubElement(self.stack[-1],tag,dict((key,value or '') for key,value in attrs))
        if tag not in ('img','input','br','hr','meta','link'):self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        ET.SubElement(self.stack[-1],tag,dict((key,value or '') for key,value in attrs))
    def handle_endtag(self,tag):
        if len(self.stack)>1 and self.stack[-1].tag==tag:self.stack.pop()
    def handle_data(self,value):
        self.stack[-1].text=(self.stack[-1].text or '')+value


class CapturedQuizDom(LoadedDom):
    def locator(self,selector):
        if selector=='[data-field-type]':
            return CapturedQuizDom([node for root in self.nodes for node in list(root.iter())[1:]
                if node.get('data-field-type') is not None],self.parents)
        result=super().locator(selector);return CapturedQuizDom(result.nodes,self.parents)
    def nth(self,index):return CapturedQuizDom([self.nodes[index]],self.parents)
    def get_by_text(self,text,*,exact):
        result=super().get_by_text(text,exact=exact);return CapturedQuizDom(result.nodes,self.parents)
    def get_by_role(self,role,*,name,exact):
        if role=='textbox' and name=='Form Name':
            return CapturedQuizDom([node for root in self.nodes for node in list(root.iter())[1:]
                if node.get('role')=='textbox' and node.get('aria-label')=='Form Name'],self.parents)
        result=super().get_by_role(role,name=name,exact=exact);return CapturedQuizDom(result.nodes,self.parents)
    def input_value(self):
        if self.nodes[0].tag not in ('input','textarea','select'):
            raise AssertionError('input_value() cannot read the captured native contenteditable title')
        return super().input_value()
    def wait_for(self,**kwargs):pass


class CapturedQuizShell(unittest.TestCase):
    def test_actual_hydrated_native_owner_reads_contenteditable_title_and_positive_empty_canvas(self):
        text=(Path(__file__).parent/'fixtures/quiz-empty-shell-captured.html').read_text()
        plan=front.validate_inputs(inputs());editor=plan['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED')
        tree=CapturedHtml(text).root;frame=CapturedQuizDom([tree]);page=MagicMock();page.url=editor;page.frame_locator.return_value=frame
        with patch.object(front,'assert_tenant'),patch.object(front.native,'_prepare_inventory'):
            self.assertEqual(front._empty_shell(page,plan,editor),{'editor_url':editor,'pages':[{'label':'Page 1','questions':[]}]})
        for defect in ('title','marker','unowned_field'):
            changed=CapturedHtml(text).root
            if defect=='title':next(node for node in changed.iter() if node.get('aria-label')=='Form Name').text='Other quiz'
            elif defect=='marker':
                next(node for node in changed.iter() if (node.text or '').strip()=='Drag and drop components').text='Loading'
            else:ET.SubElement(changed,'div',{'data-field-type':'uncaptured'})
            page.frame_locator.return_value=CapturedQuizDom([changed])
            def once(predicate,reason):
                if not predicate():raise runner.Stop(reason)
            with self.subTest(defect=defect),patch.object(front,'assert_tenant'), \
                    patch.object(front.native,'_prepare_inventory'),patch.object(front.native,'wait_until',side_effect=once),self.assertRaises(runner.Stop):
                front._empty_shell(page,plan,editor)
    def test_shared_title_reader_preserves_input_support_and_rejects_wrong_contenteditable_owner(self):
        from playwright_recipes.assessments import read_editor_title,AssessmentError
        title=MagicMock();title.get_attribute.return_value=None;title.input_value.return_value='Retained input title'
        self.assertEqual(read_editor_title(title),'Retained input title')
        title.get_attribute.side_effect=lambda key:{'contenteditable':'true','role':'textbox','aria-label':'Other'}.get(key)
        with self.assertRaises(AssessmentError):read_editor_title(title)
        title.input_value.assert_called_once()


class QuizCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'run';self.data=inputs();self.page=MagicMock();self.page.url=self.data['start_url']
        self.editor=self.data['start_url'].replace('/quiz-builder/main','/quiz-builder-v2/CREATED')
        self.calls=[]
    def job(self,data=None):
        return runner.validate_job(recipe_cli.compile_recipe('quizzes.create',data or self.data),Path('.'))
    def writer(self,page,step):
        self.calls.append(step['action']);action=step['action'];page.url=self.editor
        if action=='assessment':return {'status':'ASSESSMENT_SAVE_SUBMITTED','kind':'quiz',
            'editor_url':self.editor,'independent_readback':'REQUIRED'}
        if action=='quiz_configuration':return {'status':'QUIZ_CONFIGURATION_SAVED_AND_REOPENED','kind':'quiz',
            'editor_url':self.editor,'questions':len(step['questions']),'submission_verified':False}
        if action=='quiz_results':return {'status':'QUIZ_RESULTS_SAVED_AND_REOPENED','kind':'quiz_results',
            'editor_url':self.editor,'configuration_sha256':quiz_results.configuration_hash(step),
            'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
        module=choice if action=='quiz_multiple_choices' else written
        return {'status':'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED' if action=='quiz_multiple_choices' else 'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED',
            'kind':action,'editor_url':self.editor,'question_count':1,'target_page':step['payload']['target_page'],
            'configuration_sha256':module.configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False,'dependency_api_used':False}
    def patches(self):
        stack=ExitStack();stack.enter_context(patch.object(runner,'assert_tenant'))
        for action in ('assessment','quiz_multiple_choices','quiz_written_answers','quiz_configuration','quiz_results'):
            stack.enter_context(patch.object(runner,action,side_effect=self.writer))
        stack.enter_context(patch.object(front,'_empty_shell',side_effect=lambda page,plan,editor:{'editor_url':editor,'pages':[{'label':'Page 1','questions':[]}]}))
        stack.enter_context(patch.object(front,'reopen_editor',side_effect=lambda page,kind,name,editor:setattr(page,'url',editor)))
        stack.enter_context(patch.object(front,'_final_inventory'))
        return stack
    def test_compiled_production_action_has_no_fixture_options_or_guessed_editor_identity(self):
        job=self.job();self.assertEqual([s['action'] for s in job['steps']],['native_quiz_creation'])
        plan=job['steps'][0]['payload'];self.assertEqual(plan['name'],'ZHC New marketing quiz')
        self.assertNotIn('SCHEMA_VALIDATION_ONLY',json.dumps(job))
        qjob,pages=front._questions(plan,self.editor)
        self.assertEqual(qjob['steps'][1]['payload']['pages'][0]['questions'],[new_question()])
        self.assertEqual([p['label'] for p in pages],['Page 1','Page 2'])
    def test_foreign_owner_missing_scoring_wrong_option_and_uncaptured_changes_refuse_prewrite(self):
        for defect in ('owner','scoring','results','missing_batch','wrong_label','wrong_key','wrong_count','rewrite','foreign_page','fixture','options','not_new'):
            data=inputs();config=data['configuration'];score=config['scoring']['questions'][0]
            if defect=='owner':data['start_url']=data['start_url'].replace('/LOC/','/FOREIGN/')
            elif defect=='scoring':config.pop('scoring')
            elif defect=='results':config.pop('result_page')
            elif defect=='missing_batch':config['question_batches']=[]
            elif defect=='wrong_label':score['options'][0]['label']='Other'
            elif defect=='wrong_key':score['expected_query_key']='foreign'
            elif defect=='wrong_count':config['scoring']['expected_question_count']=3
            elif defect=='rewrite':score['question']='Different after insertion'
            elif defect=='foreign_page':config['question_batches'][0]['multiple_choice_questions']['target_page']=8
            elif defect=='fixture':data['fixture']=True
            elif defect=='options':data['options']={'capture_source':'generic callback'}
            else:data['allow_creation']=False
            with self.subTest(defect=defect),self.assertRaises((ValueError,runner.Stop)):self.job(data)
    def test_composed_runner_saves_all_child_stages_then_replays_without_a_write(self):
        job=self.job()
        with self.patches():
            first=runner.run_on_page(self.page,job,self.root);self.assertEqual(first['status'],'NEEDS_VERIFICATION')
            replay=runner.run_on_page(self.page,job,self.root);self.assertTrue(replay['replayed'])
        self.assertEqual(self.calls,['assessment','quiz_multiple_choices','quiz_written_answers','quiz_configuration','quiz_results'])
        receipt=first['results'][0]['result'];self.assertEqual(receipt['question_count'],2)
        self.assertEqual(receipt['scored_question_count'],1);self.assertEqual(len(receipt['configuration_receipts']),2)
        for child in ('shell','questions','configuration'):
            self.assertTrue((self.root/'quiz-creation'/child/'state.json').is_file())
        self.assertEqual(front.validate_receipt(receipt,job['steps'][0]),receipt)
    def test_uncertain_later_native_stage_retains_shell_and_questions_without_recreation(self):
        job=self.job()
        with self.patches(),patch.object(runner,'quiz_configuration',side_effect=TimeoutError('uncertain native scoring')) as scoring:
            with self.assertRaises(runner.Stop):runner.run_on_page(self.page,job,self.root)
            with self.assertRaises(runner.Stop):runner.run_on_page(self.page,job,self.root)
            scoring.assert_called_once()
        self.assertEqual(self.calls,['assessment','quiz_multiple_choices','quiz_written_answers'])
        self.assertEqual(json.loads((self.root/'quiz-creation'/'configuration'/'state.json').read_text())['status'],'NEEDS_BROWSER_RECOVERY')
        self.assertEqual(json.loads((self.root/'state.json').read_text())['status'],'NEEDS_BROWSER_RECOVERY')
    def test_receipt_foreign_editor_missing_child_score_mutation_and_false_behavior_refuse(self):
        job=self.job()
        with self.patches():raw=runner.run_on_page(self.page,job,self.root)['results'][0]['result']
        for defect in ('editor','child','score','true','count','shell'):
            value=deepcopy(raw)
            if defect=='editor':value['editor_url']=self.editor.replace('/CREATED','/FOREIGN')
            elif defect=='child':value['configuration_receipts'].pop()
            elif defect=='score':value['configuration_receipts'][0]['step_sha256']='0'*64
            elif defect=='true':value['submission_verified']=True
            elif defect=='count':value['question_count']=True
            else:value['shell_binding']['pages'][0]['questions']=[question()]
            with self.subTest(defect=defect),self.assertRaises(runner.Stop):front.validate_receipt(value,job['steps'][0])
    def test_scoring_child_count_and_claimed_behavior_cannot_contradict_parent_receipt(self):
        job=self.job()
        with self.patches():raw=runner.run_on_page(self.page,job,self.root)['results'][0]['result']
        for changes in ({'questions':0},{'questions':True},{'submission_verified':True},
                        {'behavior_verified':True},{'independent_readback':'REQUIRED'}):
            value=deepcopy(raw);value['configuration_receipts'][0]['result'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(runner.Stop):front.validate_receipt(value,job['steps'][0])

    def test_new_creation_guard_refuses_existing_exact_name_before_any_editor_click(self):
        page=MagicMock();search=page.get_by_role.return_value;search.count.return_value=1
        with patch.object(runner,'navigate'),patch.object(runner,'exact_search',return_value=MagicMock()), \
                patch.object(runner,'click') as click,self.assertRaisesRegex(runner.Stop,'existing exact-name'):
            runner.assessment(page,front._shell_job(front.validate_inputs(inputs()))['steps'][0])
        click.assert_not_called()
    def test_host_uses_maintained_action_with_owned_journal_instead_of_generic_creation_callback(self):
        probes={'lanes':{'playwright':{'available':True}}}
        with self.patches():
            result=host.run_recipe('quizzes.create',inputs(),probes,self.root,input_dir='.',page=self.page)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION');self.assertEqual(self.calls[0],'assessment')


if __name__=='__main__':unittest.main()
