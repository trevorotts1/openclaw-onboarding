"""New inactive-template controls retain exact fresh/replay and transport proof."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import editor_replay
import host
import recipe_cli
import skill6_playwright as runner
from test_course_text_blocks import inputs as text_inputs
from test_course_section_media import inputs as media_inputs
from test_course_image_blocks import inputs as image_inputs


def cases(root):
    image = root/'approved.png';image.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
    text = text_inputs();text['text_blocks']['append']=[{'content':'Authored additional block'}]
    yield 'text',text,'course_text_blocks'
    for sections in (('hero',),('instructor',),('hero','instructor')):
        data = media_inputs(str(image),hashlib.sha256(image.read_bytes()).hexdigest())
        data['theme_images']['images']=[{**data['theme_images']['images'][0],'section':section} for section in sections]
        yield '_'.join(sections),data,'course_section_media'
    for mode in ('url','upload','append'):
        data = image_inputs()
        asset = {'file':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
        if mode == 'upload':data['image_blocks']['updates'][0]['changes']={'image':asset}
        if mode == 'append':data['image_blocks']['append']=[{'image':asset,'url':'https://example.com/new-image-destination'}]
        yield 'image_'+mode,data,'course_image_blocks'


def compile_job(data):
    return runner.validate_job(recipe_cli.compile_recipe('courses.configure_ui',data),Path('.'))


def receipt(job,module):
    step = job['steps'][0];plan = step['payload']
    native = importlib.import_module('playwright_recipes.'+module)
    status = {'course_text_blocks':'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED',
        'course_section_media':'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED',
        'course_image_blocks':'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED'}[module]
    value = {'status':status,'editor_url':native.theme.editor_url(plan),
        'course_id':plan['course_id'],'template_id':plan['template_id'],
        'configuration_sha256':native.configuration_hash(plan),'independent_readback':'VERIFIED',
        'functional_verified':False,'activation_performed':False}
    if module == 'course_text_blocks':
        config = native.validate_inputs(plan)['text_blocks']
        before = [row['id'] for row in config['expected_inventory']]
        added = ['NEW_TEXT_'+str(index) for index in range(len(config['append']))]
        value.update(added_block_ids=added,block_ids=before+added,block_count=len(before+added))
    elif module == 'course_section_media':
        value['images']=[]
        for asset in plan['theme_images']['images']:
            digest = hashlib.sha256(('https://example.com/new-'+asset['section']+'.png').encode()).hexdigest()
            value['images'].append({'section':asset['section'],'source_sha256':asset['sha256'],
                'inspector_url_sha256':digest,'preview_url_sha256':digest})
    else:
        config = native.validate_inputs(plan)['image_blocks']
        before = [row['id'] for row in config['expected_inventory']]
        added = ['NEW_IMAGE_'+str(index) for index in range(len(config['append']))]
        value.update(added_block_ids=added,block_ids=before+added,block_count=len(before+added),images=[])
        requests = [(row['id'],row['changes'],row['expected']) for row in config['updates']]
        requests.extend((identity,row,None) for identity,row in zip(added,config['append']))
        for identity,changes,old in requests:
            new = 'https://example.com/approved-'+identity+'.png'
            inspector = new if 'image' in changes else old['inspector_url']
            preview = new if 'image' in changes else old['preview_url']
            url = changes.get('url',old['url'] if old else '')
            value['images'].append({'block_id':identity,'source_sha256':changes['image']['sha256'] if 'image' in changes else None,
                'inspector_url_sha256':hashlib.sha256(inspector.encode()).hexdigest(),
                'preview_url_sha256':hashlib.sha256(preview.encode()).hexdigest(),
                'url_sha256':hashlib.sha256(url.encode()).hexdigest()})
    return value


def probes(data,*,fallback=False):
    return {'lanes':{'playwright':{'available':not fallback},
        'openclaw_extension':{'available':fallback,'current':fallback}},
        'api_capabilities':{'courses.configure_ui':{'location_id':data['location_id'],
            'observed_at':time.time(),'supported':True,'provider':'public_api','scope_ok':True,'version':'v3'}}}


class SixthControlIntegration(unittest.TestCase):
    def test_actual_compiler_keeps_complete_plan_and_rejects_mixed_or_foreign_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind,data,module in cases(Path(directory)):
                job = compile_job(data);step = job['steps'][0]
                self.assertEqual(step['payload'],data)
                expected = {'course_text_blocks':'native_course_text_blocks','course_section_media':'native_course_section_media',
                    'course_image_blocks':'native_course_image_blocks'}[module]
                self.assertEqual(step['action'],expected)
                foreign = deepcopy(job);foreign['steps'][0]['payload']['location_name']='Another account'
                with self.subTest(kind=kind),self.assertRaises(runner.Stop):runner.validate_job(foreign,Path('.'))
                mixed = deepcopy(data);mixed['changes']={'template_title':'Unexpected sibling change'}
                with self.subTest(mixed=kind),self.assertRaises(runner.Stop):compile_job(mixed)

    def test_owned_native_leaf_runs_once_on_primary_or_fallback_and_replay_stays_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind,data,module in cases(Path(directory)):
                native = importlib.import_module('playwright_recipes.'+module);job = compile_job(data)
                for fallback in (False,True):
                    provider = Mock(return_value={'status':'API_STEPS_COMPLETE','location_id':data['location_id'],'objects':[]})
                    with self.subTest(kind=kind,fallback=fallback),tempfile.TemporaryDirectory() as evidence,patch.object(runner,'assert_tenant'):
                        page = object()
                        def owned_write(actual_page,step):
                            self.assertIs(actual_page,page)
                            self.assertEqual(json.loads(Path(evidence,'state.json').read_text())['current_step_status'],'INTENT_RECORDED')
                            return receipt(job,module)
                        with patch.object(native,'configure',side_effect=owned_write) as write:
                            first = host.run_recipe('courses.configure_ui',data,probes(data,fallback=fallback),evidence,
                                input_dir='.',page=page,executors={'public_api':provider,'openclaw_extension':provider})
                            repeated = host.run_recipe('courses.configure_ui',data,probes(data,fallback=fallback),evidence,
                                input_dir='.',page=page,executors={'public_api':provider,'openclaw_extension':provider})
                            self.assertEqual(first['status'],'NEEDS_VERIFICATION',first)
                            self.assertEqual(repeated['status'],'NEEDS_VERIFICATION',repeated)
                            write.assert_called_once();provider.assert_not_called()
                            self.assertFalse(Path(evidence,'provider-state.json').exists())

    def test_status_only_or_unbound_first_receipt_preserves_uncertain_intent_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind,data,module in cases(Path(directory)):
                job = compile_job(data);native = importlib.import_module('playwright_recipes.'+module)
                valid = receipt(job,module)
                invalid = [{'status':valid['status']},{**valid,'functional_verified':True},
                    {**valid,'activation_performed':0},{**valid,'template_id':'OTHER'},
                    {**valid,'configuration_sha256':'0'*64},{**valid,'private_unbound':'DO_NOT_PERSIST'}]
                if module in ('course_text_blocks','course_image_blocks'):
                    invalid += [{**valid,'block_count':True},{**valid,'added_block_ids':['TEXT_A']}]
                if module != 'course_text_blocks':
                    proof = deepcopy(valid);proof['images'][0]['preview_url_sha256']='f'*64;invalid.append(proof)
                    proof = deepcopy(valid);proof['images'][0]['source_sha256']='0'*64;invalid.append(proof)
                for value in invalid:
                    with self.subTest(kind=kind,value=value),tempfile.TemporaryDirectory() as evidence, \
                            patch.object(runner,'assert_tenant'),patch.object(native,'configure',return_value=value) as write:
                        for _ in range(2):
                            with self.assertRaises(runner.Stop):runner.run_on_page(object(),job,evidence)
                        write.assert_called_once()
                        raw = Path(evidence,'state.json').read_text();state = json.loads(raw)
                        self.assertEqual(state['current_step_status'],'INTENT_RECORDED')
                        self.assertEqual(state['results'],[])
                        self.assertNotIn('DO_NOT_PERSIST',raw)

    def test_completed_receipts_bind_original_lists_and_media_identity_before_generic_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind,data,module in cases(Path(directory)):
                job = compile_job(data);step = job['steps'][0];value = receipt(job,module)
                self.assertEqual(editor_replay._result(step,value,job)['configuration_sha256'],value['configuration_sha256'])
                for change in ({'course_id':'OTHER'},{'editor_url':value['editor_url']+'_OTHER'},
                        {'functional_verified':0},{'independent_readback':'REQUIRED'},{'unexpected':'foreign'}):
                    with self.subTest(kind=kind,change=change),self.assertRaises(runner.Stop):
                        editor_replay._result(step,{**value,**change},job)


if __name__ == '__main__':unittest.main()
