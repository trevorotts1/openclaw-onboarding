"""Survey shell/API/native journals compose without duplicate writes."""
from contextlib import ExitStack
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree
from test_quiz_page_heading_dom import Dom as BaseDom

import skill6_playwright as runner
import recipe_cli
import host
from test_radio_dependencies import Api,capability,question

front=importlib.import_module('playwright_recipes.survey_radio_creation')
native=importlib.import_module('playwright_recipes.survey_fields')


def inputs():
    return {'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder/main',
        'name':'New authored survey','allow_creation':True,'standard_fields':['Email'],'radio_questions':[question()]}


class ShellDom(BaseDom):
    def locator(self,selector):
        found=super().locator(selector)
        return ShellDom(found.nodes,self.parents)
    def nth(self,index):return ShellDom([self.nodes[index]],self.parents)
    def get_attribute(self,key):return self.nodes[0].get(key)
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):pass
    def get_by_placeholder(self,value,*,exact):
        return ShellDom([node for root in self.nodes for node in root.iter() if node.get('placeholder')==value],self.parents)
    def get_by_role(self,role,*,name=None,exact=False):
        if role in ('button','tab','dialog'):
            return ShellDom([node for root in self.nodes for node in root.iter()
                if (node.get('role')==role or role=='button' and node.tag=='button')
                and (name is None or node.get('aria-label',''.join(node.itertext()))==name)],self.parents)
        found=super().get_by_role(role,name=name,exact=exact)
        return ShellDom(found.nodes,self.parents)
    def evaluate_all(self,script):
        if 'const labels = item.querySelectorAll' not in script:raise AssertionError(script)
        return [{'types':[node.get('data-field-type') for node in item.iter() if node.get('data-field-type') is not None],
            'names':[[node.tag.upper(),node.get('type'),node.get('name')] for node in item.iter()
                if node.tag in ('input','select','textarea')]} for item in self.nodes]


class SurveyShellDom(unittest.TestCase):
    def multi_shell(self):
        root=ElementTree.fromstring("""<main><input aria-label="Form Name" value="New authored survey" />
            <button role="tab">Edit</button><button>Add Slide</button><button>Add Slide</button>
            <section class="survey-form-container"><div class="builder-form-name">Contact</div>
              <div class="form-field-wrapper"><label data-field-type="text">First Name</label>
                <input type="text" name="first_name" placeholder="Enter your first name" /></div>
            </section>
            <section class="survey-form-container"><div class="builder-form-name">Questions</div>
              <div class="form-field-wrapper"><label data-field-type="email">Email</label>
                <input type="email" name="email" placeholder="your@email.com" /></div>
            </section></main>""")
        plan={**inputs(),'standard_fields':['First Name','Email'],'target_slide':2}
        page=MagicMock();page.url=plan['start_url'].replace('survey-builder/main','survey-builder-v2/CREATED')
        page.frame_locator.return_value=ShellDom([root])
        return root,plan,page
    def test_loaded_single_slide_standard_field_and_complete_control_inventory_are_bound(self):
        root=ElementTree.fromstring("""<main><input aria-label="Form Name" value="New authored survey" />
            <button role="tab">Edit</button><button>Add Slide</button>
            <section class="survey-form-container"><div class="builder-form-name">Page 1</div>
              <div class="form-field-wrapper"><label data-field-type="email">Email</label>
                <input type="email" name="email" placeholder="your@email.com" /></div>
            </section></main>""")
        frame=ShellDom([root]);page=MagicMock();plan=inputs()
        page.url=plan['start_url'].replace('survey-builder/main','survey-builder-v2/CREATED')
        page.frame_locator.return_value=frame
        with patch.object(front,'assert_tenant'):
            value=front._shell(page,plan,page.url)
            self.assertEqual(value['slide_labels'],['P1 - Page 1'])
            self.assertEqual(value['canvas'],[{'types':['email'],'names':[['INPUT','email','email']]}])
            root.find('.//section//input').set('type','text')
            with self.assertRaises(runner.Stop):front._shell(page,plan,page.url)
    def test_multi_slide_shell_binds_every_exact_field_and_refuses_swapped_owners(self):
        root,plan,page=self.multi_shell()
        with patch.object(front,'assert_tenant'):
            value=front._shell(page,plan,page.url)
            self.assertEqual(value['slide_labels'],['P1 - Contact','P2 - Questions'])
            self.assertEqual([slide['standard_field']['label'] for slide in value['slides']],['First Name','Email'])
            root.findall('.//section')[0].find('.//input').set('placeholder','your@email.com')
            with self.assertRaises(runner.Stop):front._shell(page,plan,page.url)
    def test_post_placement_preserves_other_slide_full_identity_even_when_count_is_unchanged(self):
        root,plan,page=self.multi_shell()
        with patch.object(front,'assert_tenant'):
            value=front._shell(page,plan,page.url)
            front._untouched_slides(page,plan,value)
            root.findall('.//section')[0].find('.//input').set('name','other_field')
            with self.assertRaises(runner.Stop):front._untouched_slides(page,plan,value)



class SurveyRadioCreation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'run';self.data=inputs();self.api=Api();self.page=MagicMock()
        self.page.url=self.data['start_url'];self.editor=self.page.url.replace('survey-builder/main','survey-builder-v2/NEW_SURVEY')
        title=self.page.frame_locator.return_value.get_by_role.return_value
        title.count.return_value=1;title.input_value.return_value=self.data['name']
        self.snapshot={'editor_url':self.editor,'slide_labels':['P1 - Newly generated slide'],
            'canvas':[{'types':['email'],'names':[['INPUT','email','email']]}],
            'standard_field':{'label':'Email','placeholder':'your@email.com','type':'email'}}
        self.shell_calls=0
    def shell_writer(self,page,step):
        self.shell_calls+=1;page.url=self.editor
        return {'status':'ASSESSMENT_SAVE_SUBMITTED','kind':'survey','editor_url':self.editor,
            'independent_readback':'REQUIRED','scoring_and_branches':'No submission'}
    def receipt(self,page,step):
        self.assertTrue((self.root/'survey-radio-creation'/'questions'/'delivery-state.json').exists())
        return {'status':'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED','kind':'survey_object_fields',
            'editor_url':self.editor,'target_slide':step['payload']['target_slide'],'field_count':1,
            'configuration_sha256':native.configuration_hash(step),'independent_readback':'VERIFIED',
            'behavior_verified':False,'submission_verified':False}
    def patches(self,writer=None):
        stack=ExitStack()
        for owner,name,value in ((runner,'assert_tenant',None),(front,'assert_tenant',None),
                (front.survey_fields,'_close_initial',None),(front.survey_fields,'_owner',None),
                (front,'_shell',self.snapshot),(front,'_untouched_slides',None)):
            stack.enter_context(patch.object(owner,name,return_value=value))
        stack.enter_context(patch.object(front,'reopen_editor',side_effect=lambda page,*a:setattr(page,'url',self.editor)))
        stack.enter_context(patch.object(front.radio,'Skill44RadioTransport',return_value=self.api))
        resolver=MagicMock();resolver.client._resolve_version.side_effect=self.api.version_for
        stack.enter_context(patch.object(front.radio.delivery,'Skill44Transport',return_value=resolver))
        stack.enter_context(patch.object(runner,'assessment',side_effect=self.shell_writer))
        self.writer=stack.enter_context(patch.object(native,'configure',side_effect=writer or self.receipt))
        return stack
    def run_job(self):
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',self.data),Path(self.temp.name))
        return runner.run_on_page(self.page,job,self.root,radio_field_capability=capability())
    def test_named_recipe_composes_and_completed_replay_does_not_create_or_place_twice(self):
        with self.patches():
            result=self.run_job();replay=self.run_job()
        self.assertEqual(result['status'],'NEEDS_VERIFICATION');self.assertTrue(replay['replayed'])
        self.assertEqual(self.shell_calls,1);self.writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        receipt=result['results'][0]['result']
        self.assertEqual(receipt['editor_url'],self.editor);self.assertFalse(receipt['submission_verified'])
    def test_maintained_host_executes_the_compiled_chain_with_measured_radio_capability(self):
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}},'radio_field_capability':capability()}
        with self.patches():
            result=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name,page=self.page)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['result']['results'][0]['result']['status'],'SURVEY_RADIO_SAVED_AND_REOPENED')
        self.writer.assert_called_once();self.assertEqual(self.shell_calls,1)
    def test_multi_slide_host_retains_complete_inventory_and_authored_radio_target_without_duplicate_writes(self):
        self.data.update(standard_fields=['First Name','Email'],target_slide=2)
        self.snapshot={'editor_url':self.editor,'slide_labels':['P1 - Contact','P2 - Questions'],
            'slides':[{'canvas':[{'types':['text'],'names':[['INPUT','text','first_name']]}],
                'standard_field':{'label':'First Name','placeholder':'Enter your first name','type':'text'}},
                {'canvas':[{'types':['email'],'names':[['INPUT','email','email']]}],
                'standard_field':{'label':'Email','placeholder':'your@email.com','type':'email'}}]}
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}},'radio_field_capability':capability()}
        with self.patches():
            result=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name,page=self.page)
            replay=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name,page=self.page)
        self.assertEqual(result['status'],'NEEDS_VERIFICATION');self.assertEqual(replay['status'],'NEEDS_VERIFICATION')
        self.assertEqual(self.shell_calls,1);self.writer.assert_called_once()
        payload=self.writer.call_args.args[1]['payload']
        self.assertEqual(payload['target_slide'],2);self.assertEqual(payload['expected_slide_count'],2)
        self.assertEqual(payload['slide_labels'],self.snapshot['slide_labels'])
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
        receipt=result['result']['results'][0]['result']
        self.assertEqual(receipt['shell_binding'],self.snapshot)
        self.assertEqual(receipt['native_receipt']['target_slide'],2)
        step=recipe_cli.compile_recipe('surveys.create',self.data)['steps'][0]
        for change in ('missing_owner','wrong_field','reordered_labels','other_target'):
            value=deepcopy(receipt)
            if change=='missing_owner':value['shell_binding']['slides'].pop()
            elif change=='wrong_field':value['shell_binding']['slides'][0]['standard_field']['label']='Phone'
            elif change=='reordered_labels':value['shell_binding']['slide_labels'].reverse()
            else:value['native_receipt']['target_slide']=1
            with self.subTest(change=change),self.assertRaises(runner.Stop):front.validate_receipt(value,step)
    def test_invalid_multi_slide_plan_is_refused_at_compile_before_shell_or_api(self):
        plan={**self.data,'standard_fields':['First Name','Email'],'target_slide':2}
        for key,value in (('target_slide',0),('target_slide',3),('target_slide',True),('target_slide','2'),
                ('standard_fields',['Email','Email']),('standard_fields',[{}]),
                ('standard_fields',['Full Name','Email'])):
            with self.subTest(key=key,value=value),self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('surveys.create',{**plan,key:value})
        del plan['target_slide']
        with self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.create',plan)
        self.assertEqual(self.api.calls,[]);self.assertEqual(self.shell_calls,0)
    def test_shell_reopen_mismatch_stops_before_any_schema_or_native_write(self):
        with self.patches(),patch.object(front,'_shell',side_effect=[self.snapshot,{**self.snapshot,'canvas':[]}]),self.assertRaises(runner.Stop):
            self.run_job()
        self.assertEqual(self.api.calls,[]);self.writer.assert_not_called()
    def test_uncertain_native_write_retains_shell_and_never_recreates_or_repeats(self):
        with self.patches(writer=TimeoutError('uncertain native save')):
            with self.assertRaises(runner.Stop):self.run_job()
            with self.assertRaises(runner.Stop):self.run_job()
        self.assertEqual(self.shell_calls,1);self.writer.assert_called_once()
        self.assertEqual(sum(call[0]=='POST' for call in self.api.calls),1)
    def test_mutated_receipt_and_author_plan_are_refused(self):
        with self.patches():value=self.run_job()['results'][0]['result']
        step=recipe_cli.compile_recipe('surveys.create',self.data)['steps'][0]
        for mutate in ('editor','field','native','flags','canvas','triplet','origin'):
            bad=deepcopy(value)
            if mutate=='editor':bad['editor_url']=self.editor.replace('NEW_SURVEY','OTHER')
            elif mutate=='field':bad['api_fields'][0]['options']=['Changed','Other']
            elif mutate=='native':bad['native_receipt']['configuration_sha256']='0'*64
            elif mutate=='flags':bad['submission_verified']=True
            elif mutate=='canvas':bad['shell_binding']['canvas']=['invented']
            elif mutate=='triplet':bad['shell_binding']['canvas'][0]['names']=[['INPUT']]
            else:bad['shell_binding']['editor_url']=bad['editor_url']=self.editor.replace('app.convertandflow.com','foreign.example.com')
            with self.subTest(mutate=mutate),self.assertRaises(runner.Stop):front.validate_receipt(bad,step)
        for key,value in (('allow_creation',False),('standard_fields',[]),('standard_fields',['Email','Phone']),('start_url',self.editor)):
            bad={**self.data,key:value}
            with self.subTest(key=key),self.assertRaises(runner.Stop):recipe_cli.compile_recipe('surveys.create',bad)
    def test_host_and_execute_require_fresh_capability_before_browser(self):
        probes={'lanes':{'playwright':{'available':True,'current':True,'enabled':True}}}
        with patch.object(host,'execute') as launch:
            result=host.run_recipe('surveys.create',self.data,probes,self.root,input_dir=self.temp.name)
        self.assertEqual(result['status'],'RADIO_FIELD_CAPABILITY_REQUIRED');launch.assert_not_called()
        job=runner.validate_job(recipe_cli.compile_recipe('surveys.create',self.data),Path(self.temp.name))
        with self.assertRaises(runner.Stop):runner.execute(job,self.root)


if __name__=='__main__':unittest.main()
