#!/usr/bin/env python3
"""Offline fixture-only smoke of the public host --check entry points.

No browser, native writes, payment, or live evidence. Replace fixture data with
real account-bound inputs to use the host in an authorized working session.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

RECIPES = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RECIPES.parent), str(RECIPES)]
from playwright_recipes.host import main


def smoke():
    base = {'location_id':'LOC_TEST','location_name':'Fixture',
            'start_url':'https://app.example/v2/location/LOC_TEST/page-builder/PAGE_TEST'}
    probes = {'api_capabilities':{},'lanes':{'playwright':{'available':True}}}
    seo = {'title':'Fixture','description':'Fixture description','author':'Fixture',
           'canonical':'https://example.com/fixture','canonical_host':'example.com',
           'keywords':['fixture','sample','test'],'page_copy':'fixture sample test',
           'author_source':'fixture','keyword_source':'fixture'}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fragment = '<iframe id="demo-frame" src="https://example.com/app"></iframe>'
        digest = hashlib.sha256(fragment.encode()).hexdigest()
        (root/'embed.html').write_text(fragment)
        (root/'probes.json').write_text(json.dumps(probes))
        graph = json.loads((RECIPES/'examples/native-purchase-flow-manifest.template.json').read_text())['route_graph']
        stage = {'id':'layout','kind':'design','role':'checkout','operation':'pages.layout',
                 'inputs':{**base,'layout':{'section_id':'section_fixture','columns':2}},'depends_on':[]}
        checkout = {'id':'checkout_ui','kind':'checkout','role':'checkout','operation':'checkout.configure_ui',
                    'inputs':{**base,'page_id':'PAGE_TEST','element_id':'checkout_fixture',
                        'expected_name':'Order Form','section_id':'section_fixture','mode':'Two-step'},
                    'depends_on':['layout']}
        binding = {'status':'PASS','location_id':'LOC_TEST','graph_page_id':'SELFTEST-CHECKOUT',
                   'native_page_id':'PAGE_TEST','native_step_id':'STEP_TEST','source':'fixture only'}
        cases = {
            'funnels.create_folder': {**base,'start_url':'https://app.example/v2/location/LOC_TEST/funnels-websites/funnels',
                'folder_name':'Fixture','allow_creation':True},
            'websites.create_folder': {**base,'start_url':'https://app.example/v2/location/LOC_TEST/funnels-websites/websites',
                'folder_name':'Fixture','allow_creation':True},
            'pages.layout': {**base,'layout':{'section_id':'section_fixture','columns':2}},
            'pages.responsive': {**base,'responsive':{'profile':'funnel_row_width_v1','section_id':'section_fixture',
                'row_id':'row_fixture','device':'desktop','width_percent':80}},
            'pages.saved_section': {**base,'saved_section':{'operation':'inventory','profile':'saved-assets-new'}},
            'pages.install_embed': {**base,'file':'embed.html','marker':'example.com/app','seo':seo,
                'embed_receipt':{'status':'PASS','location_id':'LOC_TEST','source':'fixture',
                    'html_sha256':digest,'embed_urls':['https://example.com/app']},
                'embed_config':{'iframe_id':'demo-frame','approved_html_sha256':digest,'height_px':500},
                'embed_placement':{'section_id':'s','row_id':'r','column_id':'c'}},
            'checkout.purchase_flow': {'location_id':'LOC_TEST','route_graph':graph,
                'page_bindings':{'checkout':binding},'stages':[stage,checkout]},
        }
        for index,(operation,inputs) in enumerate(cases.items()):
            path = root/f'inputs-{index}.json'; path.write_text(json.dumps(inputs))
            code = main(['--operation',operation,'--inputs',str(path),'--probes',str(root/'probes.json'),
                         '--evidence-root',str(root/f'evidence-{index}'),'--check'])
            if code: raise SystemExit(f'Fixture check failed: {operation}')


if __name__ == '__main__': smoke()
