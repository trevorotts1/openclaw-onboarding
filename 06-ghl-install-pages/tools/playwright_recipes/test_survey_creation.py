"""Whole-survey stages preserve exact owners and stop on later uncertainty."""
from contextlib import ExitStack
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import skill6_playwright as runner
import host
import recipe_cli
from test_radio_dependencies import Api,capability,question

front=importlib.import_module('playwright_recipes.survey_creation')
native=importlib.import_module('playwright_recipes.survey_fields')


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'New authored survey','allow_creation':True,'standard_fields':['First Name','Email'],
        'question_batches':[{'kind':'radio','target_slide':1,'questions':[question()]},
            {'kind':'radio','target_slide':2,'questions':[question('Budget','contact.budget')]}]}


def binding(plan,editor):
    return {'editor_url':editor,'slide_labels':['P1 - Contact','P2 - Questions'],
        'slides':[{'canvas':[{'types':['text'],'names':[['INPUT','text','first_name']]}],
            'standard_field':{'label':'First Name','placeholder':'Enter your first name','type':'text'}},
            {'canvas':[{'types':['email'],'names':[['INPUT','email','email']]}],
            'standard_field':{'label':'Email','placeholder':'your@email.com','type':'email'}}]}


def inventory(plan,snapshot,completed):
    rows=[{'canvas':deepcopy(row['canvas']),'radio_fields':[]} for row in snapshot['slides']]
    for authored,done in zip(plan['question_batches'],completed):
        row=rows[authored['target_slide']-1]
        for field in done['api_fields']:
            row['canvas'].append({'types':['RADIO'],
                'names':[['INPUT','radio',field['id']] for _ in field['options']]})
            row['radio_fields'].append({'id':field['id'],'query_key':field['field_key'].split('.',1)[1]})
    return {'slide_labels':deepcopy(snapshot['slide_labels']),'slides':rows}


class WholeSurveyCreation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'run';self.data=inputs();self.api=Api();self.page=MagicMock()
        self.page.url=self.data['start_url'];self.editor=self.page.url.replace('survey-builder/main','survey-builder-v2/NEW_SURVEY')
        title=self.page.frame_locator.return_value.get_by_role.return_value
        title.count.return_value=1;title.input_value.return_value=runner.zhc(self.data['name'])
        self.shell=binding(self.data,self.editor);self.shell_calls=0;self.native_targets=[]
    def shell_writer(self,page,step):
        self.assertEqual(step['name'],front.validate_inputs(self.data)['name'])
        self.shell_calls+=1;page.url=self.editor
        return {'status':'ASSESSMENT_SAVE_SUBMITTED','kind':'survey','editor_url':self.editor,
            'independent_readback':'REQUIRED','scoring_and_branches':'No submission'}
    def native_writer(self,page,step):
        self.native_targets.append(step['payload']['target_slide'])
        return {'status':'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED','kind':'survey_object_fields',
            'editor_url':self.editor,'target_slide':step['payload']['target_slide'],
            'field_count':len(step['payload']['object_fields']),
            'configuration_sha256':native.configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
    def patches(self,writer=None):
        stack=ExitStack()
        for module,name,value in ((runner,'assert_tenant',None),(front,'assert_tenant',None),
                (front.shell.survey_fields,'_close_initial',None),(front.shell.survey_fields,'_owner',None),
                (front.shell,'_shell',self.shell)):
            stack.enter_context(patch.object(module,name,return_value=value))
        stack.enter_context(patch.object(front,'reopen_editor',side_effect=lambda page,*a:setattr(page,'url',self.editor)))
        stack.enter_context(patch.object(front.radio,'Skill44RadioTransport',return_value=self.api))
        resolver=MagicMock();resolver.client._resolve_version.side_effect=self.api.version_for
        stack.enter_context(patch.object(front.radio.delivery,'Skill44Transport',return_value=resolver))
        stack.enter_context(patch.object(runner,'assessment',side_effect=self.shell_writer))
        stack.enter_context(patch.object(native,'configure',side_effect=writer or self.native_writer))
        stack.enter_context(patch.object(front,'_inventory',side_effect=lambda page,plan,snap,done:
            front._validate_inventory(inventory(plan,snap,done),plan,snap,done)))
        return stack
    def run_chain(self):
        return front.configure(self.page,{'action':front.ACTION,'payload':self.data},self.root,capability=capability())
    def test_compiled_standard_shell_and_bound_creation_plan_use_the_same_maintained_name(self):
        outer=runner.validate_job(recipe_cli.compile_recipe('surveys.create',self.data),Path(self.temp.name))
        bound=front.validate(outer['steps'][0])
        shell_inputs={key:value for key,value in bound.items() if key!='question_batches'}
        created=runner.validate_job(recipe_cli.compile_recipe('surveys.create',shell_inputs),Path(self.temp.name))
        self.assertEqual(bound['name'],'ZHC New authored survey')
        self.assertEqual(created['steps'][0]['name'],bound['name'])
        self.assertEqual(front.validate_inputs(bound),bound)
        blank={key:value for key,value in self.data.items() if key!='standard_fields'}
        self.assertEqual(front.validate_inputs({**blank,'slide_count':2})['name'],bound['name'])
        self.assertEqual(self.data['name'],'New authored survey')
    def test_two_radio_target_slides_create_once_and_whole_saved_inventory_is_bound(self):
        with self.patches():result=self.run_chain()
        self.assertEqual(result['status'],'SURVEY_CREATED_SAVED_AND_REOPENED')
        self.assertEqual(self.shell_calls,1);self.assertEqual(self.native_targets,[1,2])
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),2)
        self.assertEqual([slide['radio_fields'][0]['id'] for slide in result['saved_inventory']['slides']],['NEW0','NEW1'])
        self.assertFalse(result['submission_verified']);self.assertFalse(result['behavior_verified'])
        step={'action':front.ACTION,'payload':self.data}
        for changed in ('target','field','canvas','order','query','duplicate_query'):
            bad=deepcopy(result)
            if changed=='target':bad['question_batches'][1]['target_slide']=1
            elif changed=='field':bad['question_batches'][1]['api_fields'][0]['options']=['Changed','Other']
            elif changed=='canvas':bad['saved_inventory']['slides'][0]['canvas'][0]['names'][0][2]='other'
            elif changed=='order':bad['saved_inventory']['slide_labels'].reverse()
            elif changed=='query':bad['saved_inventory']['slides'][0]['radio_fields'][0]['query_key']=''
            else:bad['saved_inventory']['slides'][1]['radio_fields'][0]['query_key']='service'
            with self.subTest(changed=changed),self.assertRaises(runner.Stop):front.validate_receipt(bad,step)
    def test_maintained_host_compiles_executes_and_replays_the_whole_bound_creation_job(self):
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}},'radio_field_capability':capability()}
        with self.patches():
            result=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name,page=self.page)
            replay=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name,page=self.page)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION');self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
        self.assertTrue(replay['result']['replayed'])
        self.assertEqual(result['result']['results'][0]['result']['status'],'SURVEY_CREATED_SAVED_AND_REOPENED')
        self.assertEqual(self.shell_calls,1);self.assertEqual(self.native_targets,[1,2])
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),2)
    def test_missing_radio_capability_refuses_before_browser_acquisition(self):
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}}}
        with patch.object(host,'execute') as launch:
            result=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name)
        self.assertEqual(result['status'],'RADIO_FIELD_CAPABILITY_REQUIRED');launch.assert_not_called()
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',self.data),Path(self.temp.name))
        with self.assertRaises(runner.Stop):runner.execute(job,self.root)
    def test_empty_slide_plan_uses_no_forced_contact_fields_and_runs_both_radio_targets(self):
        self.data.pop('standard_fields');self.data['slide_count']=2
        self.shell={'editor_url':self.editor,'slide_labels':['P1 - Slide 1','P2 - Slide 2'],
            'slides':[{'canvas':[]},{'canvas':[]}]}
        def create_blank(page,plan,evidence):
            self.shell_calls+=1;page.url=self.editor
            runner.secure_json(Path(evidence)/'blank-shell-state.json',{
                'schema':'skill6-empty-survey-shell/1','configuration_sha256':front.blank._fingerprint(plan),
                'status':'SAVED_AND_REOPENED','binding':self.shell})
            return deepcopy(self.shell)
        with self.patches(),patch.object(front.blank,'configure',side_effect=create_blank),patch.object(runner,'assessment') as generic:
            result=self.run_chain()
        generic.assert_not_called();self.assertEqual(self.shell_calls,1);self.assertEqual(self.native_targets,[1,2])
        self.assertTrue(all(len(slide['canvas'])==1 for slide in result['saved_inventory']['slides']))
        plan=deepcopy(self.data);plan['slide_count']=8
        self.assertEqual(front.validate_inputs(plan)['slide_count'],8)
    def test_later_uncertain_native_stage_preserves_prior_stage_and_does_not_rewrite(self):
        def write(page,step):
            if step['payload']['target_slide']==2:raise TimeoutError('native Save uncertain')
            return self.native_writer(page,step)
        with self.patches(writer=write):
            with self.assertRaises(runner.Stop):self.run_chain()
            posts=sum(call[0]=='POST' for call in self.api.calls)
            with self.assertRaises(runner.Stop):self.run_chain()
        self.assertEqual(self.shell_calls,1);self.assertEqual(self.native_targets,[1])
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),posts)
    def test_cross_batch_duplicate_schema_and_late_bad_target_refuse_before_shell(self):
        for mutation in ('duplicate','target','kind','choice'):
            data=deepcopy(self.data)
            if mutation=='duplicate':data['question_batches'][1]['questions']=[deepcopy(data['question_batches'][0]['questions'][0])]
            elif mutation=='target':data['question_batches'][1]['target_slide']=True
            elif mutation=='kind':data['question_batches'][1]['kind']='uncaptured'
            else:data['question_batches'][1]['questions'][0]['options']=['same','same']
            with self.subTest(mutation=mutation),self.assertRaises(runner.Stop):front.validate_inputs(data)
        self.assertEqual(self.api.calls,[]);self.assertEqual(self.shell_calls,0)
    def test_missing_later_api_reuse_refuses_before_shell_and_first_schema_post(self):
        self.data['question_batches'][1]['questions'][0].update(expected_id='MISSING',allow_creation=False)
        with self.patches(),self.assertRaises(runner.Stop):self.run_chain()
        self.assertEqual(self.shell_calls,0);self.assertEqual(self.native_targets,[])
        self.assertTrue(self.api.calls);self.assertTrue(all(call[0]=='GET' for call in self.api.calls))
    def test_same_count_unrequested_slide_replacement_is_not_a_complete_saved_inventory(self):
        with self.patches():value=self.run_chain()
        bad=deepcopy(value['saved_inventory']);bad['slides'][1]['canvas'][0]['names'][0][2]='changed'
        with self.assertRaises(runner.Stop):front._validate_inventory(bad,self.data,self.shell,value['question_batches'])


if __name__=='__main__':unittest.main()
