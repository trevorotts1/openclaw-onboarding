"""Every current concrete editor action requires its maintained native proof path.

The callbacks are deliberately plausible generic provider receipts: operation,
location, a completion status, and a root ID for creation. None contains the
compiled step receipts. A broad capability cannot authorize those native jobs.
"""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import host
import recipe_cli
import skill6_playwright as runner
from receipt_validation import CREATE_ROOTS
from test_native_provider_boundaries import form_cases, other_cases, probes

def native_cases(root):
 asset=root/'approved.png';asset.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
 for k,o,d,*_ in form_cases():yield k,o,d
 yield from other_cases(asset)
 for k in ('short','choice','radio','yes_no','quiz_dropdown','quiz_multi','written'):
  from test_fourth_control_integration import request
  o,d,_=request(k);yield 'quiz_'+k,o,d
 from test_survey_radio_creation import inputs as survey_radio
 yield 'survey_radio_creation','surveys.create',survey_radio()
 from test_quiz_picture_questions import request as picture_choice
 yield 'quiz_picture_choice','quizzes.configure',picture_choice()
 from test_field_placement_integration import inputs
 base=inputs();base.pop('add_fields')
 for k,extra in [('builtin',{'add_fields':['Website']}),('field_properties',{'fields':[{'field':'Last Name','required':True}]}),('address',{'address_fields':[{'field':'Street Address','current_query_key':'address','query_key':'street_address'}]}),('consent',{'consent':{'expected_query_key':'terms_and_conditions','required':True,'expected_required':False}})]:yield k,'forms.configure',{**base,**extra}
 yield 'settings','forms.settings',{**base,'settings':{'save_progress':True}}
 from test_form_schedule import spec
 yield 'schedule','forms.settings',{**base,'schedule':spec()['schedule']}
 from test_form_order_confirmation import plan
 p=plan()['payload'];yield 'paymentoutcome','forms.submission',{**{k:p[k] for k in ('location_id','location_name','start_url')},'submission':{'mode':'Order Confirmation',**{k:v for k,v in p.items() if k not in ('location_id','location_name','start_url')}}}
 yield 'cssradius','forms.style',{**base,'radius':12}
 yield 'singlecondition','forms.conditions',{**base,'condition':{'if_field':'Last Name','operator':'Is Filled','target':'First Name'}}
 from test_form_condition_groups import plan as group
 yield 'compoundcondition','forms.conditions',{**base,'condition':{k:v for k,v in group().items() if k!='action'}}
 from test_next_control_integration import NativeDynamicIntegrationTests
 yield 'dynamic_calendar','meetings.integrate',NativeDynamicIntegrationTests().data()
 from test_community_event_host import inputs as event
 yield 'community_event','meetings.integrate',event()
 from test_quiz_ui import configuration
 yield 'quiz_existing','quizzes.configure',{**base,'start_url':base['start_url'].replace('form-builder-v2','quiz-builder-v2'),'configuration':configuration()}
 for op in ('forms.create','surveys.create','quizzes.create'):
  yield op,op,{**base,'name':'Approved fixture',**({'fixture':True} if op=='quizzes.create' else {})}
 from test_community_creation_identity import step
 c=step();ctx=c.pop('_context');c.pop('action');yield 'community_create','communities.create',{**ctx,'community':c}
 from test_community_portal import inputs as portal
 from test_community_details import details_inputs
 from test_community_courses import inputs as courses
 from test_community_branding import inputs as branding
 for k,fn in [('channels',portal),('details',details_inputs),('community_courses',courses)]:yield k,'communities.configure',fn()
 yield 'branding','communities.configure',branding(asset)
 access=json.loads((Path(__file__).parent/'examples/community-access.json').read_text());yield 'access','communities.configure',access
 from test_course_block_media import inputs as block
 yield 'course_block_image','courses.configure_ui',block(asset)
 from test_course_text_blocks import inputs as text
 yield 'course_text_blocks','courses.configure_ui',text()
 from test_course_section_media import inputs as section_images
 yield 'course_section_media','courses.configure_ui',section_images(str(asset),hashlib.sha256(asset.read_bytes()).hexdigest())
 from test_course_image_blocks import inputs as image_blocks
 yield 'course_image_blocks','courses.configure_ui',image_blocks()
 from test_contact_field_dependencies import large
 yield 'contact_field_chain','forms.configure',{
  'location_id':'LOC','location_name':'Fixture Account',
  'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM',
  'contact_field_plan':{'expected_form_name':'Existing form','fields':[large()],
   'native_bindings':[{'field_key':'contact.audience','native_query_key':'audience:_who?',
    'expected_label':'Audience','expected_placeholder':'Describe your audience. '}]}}
 profile={'capture_source':'fixture exact UI controls','steps':[{'action':'expect_text','target':{'by':'role','role':'heading','value':'Approved fixture'},'value':'Approved fixture'}]}
 for op in ('forms.configure','courses.configure_ui','communities.configure','funnels.split_variant','meetings.integrate'):
  yield op+'_options',op,{**base,'options':profile}
 html=root/'page.html';html.write_text('<p>Approved fixture</p>')
 seo={'title':'Approved fixture','description':'Approved fixture description','author':'Fixture','canonical':'https://example.com/fixture','canonical_host':'example.com','keywords':['approved fixture','fixture','approved'],'page_copy':'approved fixture','author_source':'fixture','keyword_source':'fixture'}
 for op in ('funnels.create','funnels.add_page','websites.create','websites.add_page'):
  yield op,op,{**base,'container_name':'Approved fixture','page_name':'Approved fixture','path':'/fixture'}
 yield 'seo','pages.seo',{**base,'seo':seo}
 yield 'code','pages.install_code',{**base,'file':str(html),'marker':'Approved fixture','seo':seo}
 embed=root/'embed.html';embed.write_text('<iframe src="https://example.com/app"></iframe>')
 yield 'embedpage','pages.install_embed',{**base,'file':str(embed),'marker':'example.com/app','seo':seo,'embed_receipt':{'status':'PASS','location_id':base['location_id'],'source':'fixture','html_sha256':runner.sha(embed.read_text()),'embed_urls':['https://example.com/app']}}
 yield 'checkout_wrap','checkout.wrap_native',{**base,'before_file':str(html),'before_marker':'Approved fixture','seo':seo}
 from test_checkout_ui import inputs as checkoutui
 yield 'checkout_ui','checkout.configure_ui',checkoutui()
 from test_pages_checkout import inputs as checkout,capture
 cap=root/'capture.json';cap.write_text(json.dumps(capture()))
 for op in ('checkout.configure_native','checkout.one_click_upsell'):
  data=checkout();data['adapter_capture']=str(cap);yield op,op,data
 yield 'upsell_options','checkout.one_click_upsell',{**base,'checkout_contract':checkout()['checkout_contract']|{'location_id':base['location_id']},'options':profile}


def compiled_cases(root):
    for key,operation,inputs in native_cases(root):
        job=runner.validate_job(recipe_cli.compile_recipe(operation,inputs),Path('.'))
        yield key,operation,inputs,job


def literal_action(expression):
    if isinstance(expression,ast.Constant) and isinstance(expression.value,str):
        return {expression.value}
    if isinstance(expression,ast.IfExp):
        return literal_action(expression.body) | literal_action(expression.orelse)
    return set()


class CompleteNativeProviderBoundaries(unittest.TestCase):
    def test_samples_cover_all_current_concrete_compiler_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            rows=list(compiled_cases(Path(directory)))
        covered={step['action'] for _,_,_,job in rows for step in job['steps']}
        tree=ast.parse(Path(recipe_cli.__file__).read_text())
        named=set()
        for node in ast.walk(tree):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                    and node.func.id=='add' and node.args):
                named |= literal_action(node.args[0])
        self.assertTrue(named <= covered,named-covered)
        self.assertEqual(len(covered),59,'Update the bounded fixtures for newly added dynamic compiler actions')
        self.assertEqual(len(rows),72)

    def test_no_current_native_job_delegates_to_status_only_api_or_extension_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            for key,operation,inputs,job in compiled_cases(Path(directory)):
                objects=([{'kind':CREATE_ROOTS[operation],'id':'FIXTURE_OBJECT'}]
                         if operation in CREATE_ROOTS else [])
                for script,extension in ((True,False),(False,True)):
                    api=Mock(return_value={'status':'API_STEPS_COMPLETE',
                        'location_id':inputs['location_id'],'objects':objects})
                    browser=Mock(return_value={'status':'EDITOR_STEPS_COMPLETE',
                        'location_id':inputs['location_id'],'objects':objects})
                    probe=probes(operation,inputs,script=script,extension=extension)
                    if extension:probe['api_capabilities']={}
                    with self.subTest(case=key,script=script),tempfile.TemporaryDirectory() as evidence, \
                         patch.object(host,'run_on_page',return_value={'status':'NEEDS_VERIFICATION'}):
                        result=host.run_recipe(operation,inputs,probe,evidence,input_dir='.',
                            page=object() if script else None,
                            executors={'public_api':api,'openclaw_extension':browser})
                        api.assert_not_called();browser.assert_not_called()
                        self.assertFalse(Path(evidence,'provider-state.json').exists(),result)
                        self.assertNotIn(result['status'],
                            ('API_STEPS_COMPLETE','EDITOR_STEPS_COMPLETE','ALREADY_EXECUTED'),result)


if __name__=='__main__':unittest.main()
