import hashlib
import shutil
import subprocess
import unittest
from unittest.mock import patch

from playwright_recipes import page_embeds
from playwright_recipes.skill6_playwright import Stop


HTML = '<section><iframe id="demo-frame" src="https://app.example/embed" title="Demo"></iframe></section>'
HASH = hashlib.sha256(HTML.encode()).hexdigest()
RECEIPT = {'status': 'PASS', 'location_id': 'loc-1', 'html_sha256': HASH,
           'embed_urls': ['https://app.example/embed']}


def config(**kwargs):
    return {'iframe_id': 'demo-frame', 'approved_html_sha256': HASH,
            'height_px': 520, 'min_height_px': 400, 'max_height_px': 700,
            'max_width_px': 1100, **kwargs}


class PageEmbedTests(unittest.TestCase):
    def test_validate_and_emit_scoped_idempotent_initializer(self):
        plan = page_embeds.validate(config(aspect_ratio=1.8, resize_origin='https://app.example'),
                                    approved_html=HTML, receipt=RECEIPT, location_id='loc-1')
        fragment = page_embeds.build_fragment(plan)
        self.assertIn('#demo-frame{', fragment)
        self.assertIn('zhc-embed-style-demo-frame', fragment)
        self.assertIn('__zhcEmbedInit_', fragment)
        self.assertIn("e.origin!==c.resize_origin", fragment)
        self.assertIn('hydrationDone', fragment)
        self.assertIn('1500', fragment)  # published-page fallback
        self.assertIn('height:520px', fragment)
        self.assertEqual(HTML, '<section><iframe id="demo-frame" src="https://app.example/embed" title="Demo"></iframe></section>')

    def test_receipt_and_original_hash_are_mandatory(self):
        with self.assertRaises(Stop):
            page_embeds.validate(config(approved_html_sha256='0' * 64), approved_html=HTML,
                                 receipt=RECEIPT, location_id='loc-1')
        bad_receipt = dict(RECEIPT, location_id='other')
        with self.assertRaises(Stop):
            page_embeds.validate(config(), approved_html=HTML, receipt=bad_receipt, location_id='loc-1')

    def test_rejects_unbound_or_ambiguous_frame(self):
        for html, receipt in (
            (HTML.replace('demo-frame', 'other'), RECEIPT),
            (HTML + HTML, RECEIPT),
            (HTML, dict(RECEIPT, embed_urls=['https://other.example/embed'])),
        ):
            with self.assertRaises(Stop):
                page_embeds.validate(config(), approved_html=html, receipt=receipt, location_id='loc-1')

    def test_rejects_unsafe_resize_origin_and_invalid_bounds(self):
        for change in ({'resize_origin': 'https://app.example/path'},
                       {'resize_origin': 'https://user@app.example'},
                       {'height_px': 800}, {'min_height_px': 701},
                       {'initialize_selector': 'iframe'},
                       {'initialize_call': 'bad function()'}):
            values = config(**change)
            with self.assertRaises(Stop):
                page_embeds.validate(values, approved_html=HTML, receipt=RECEIPT, location_id='loc-1')

    def test_verified_dom_state_checks_bounds_and_identity(self):
        plan = page_embeds.validate(config(), approved_html=HTML, receipt=RECEIPT, location_id='loc-1')
        ok = {'id': 'demo-frame', 'tag': 'IFRAME', 'width': 1000, 'height': 520,
              'display': 'block', 'visible': True}
        self.assertEqual(page_embeds.verify_dom_state(plan, ok)['status'], 'VERIFIED')
        for bad in (dict(ok, height=399), dict(ok, width=1200), dict(ok, visible=False), dict(ok, id='wrong')):
            with self.assertRaises(Stop):
                page_embeds.verify_dom_state(plan, bad)

    def test_ratio_only_embed_sets_auto_height_and_verifies_observed_ratio(self):
        plan = page_embeds.validate({'iframe_id':'demo-frame','approved_html_sha256':HASH,
                                     'aspect_ratio':2}, approved_html=HTML,
                                    receipt=RECEIPT, location_id='loc-1')
        fragment = page_embeds.build_fragment(plan)
        self.assertIn('aspect-ratio:2/1;height:auto', fragment)
        good = {'id':'demo-frame','tag':'IFRAME','width':1000,'height':500,
                'display':'block','visible':True}
        self.assertEqual(page_embeds.verify_dom_state(plan, good)['status'], 'VERIFIED')
        with self.assertRaises(Stop):
            page_embeds.verify_dom_state(plan, dict(good, height=420))

    def test_initializer_retries_late_sdk_and_target_with_correct_receiver_once(self):
        self.assertIsNotNone(shutil.which('node'),
                             'Node.js is required for the bounded custom-JS initialization test')
        plan = page_embeds.validate({'iframe_id':'demo-frame','approved_html_sha256':HASH,
                                     'height_px':520,'initialize_selector':'#app-root',
                                     'initialize_call':'App.initialize'},
                                    approved_html=HTML, receipt=RECEIPT, location_id='loc-1')
        fragment = page_embeds.build_fragment(plan)
        script = fragment.split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
        harness = r'''const vm=require('node:vm'),assert=require('node:assert/strict');
const source=process.argv[1];
const timers=[],events={};let target=null,calls=0;
const frame={tagName:'IFRAME',style:{}};
const doc={readyState:'complete',documentElement:{},getElementById:id=>id==='demo-frame'?frame:null,
  querySelector:selector=>selector==='#app-root'?target:null,addEventListener:(name,fn)=>{events[name]=fn;}};
const win={setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},
  addEventListener:(name,fn)=>{events[name]=fn;},
  MutationObserver:function(){this.observe=()=>{};this.disconnect=()=>{};}};
vm.runInNewContext(source,{window:win,document:doc,MutationObserver:win.MutationObserver,Number,Math});
assert.equal(calls,0);
target={};win.App={initialize:function(el){assert.equal(this,win.App);assert.equal(el,target);calls++;}};
const retry=timers.find(item=>item.ms===250);assert.ok(retry);retry.fn();
assert.equal(calls,1);assert.equal(target.__zhcEmbedTargetInit,true);
events.hydrationDone();
vm.runInNewContext(source,{window:win,document:doc,MutationObserver:win.MutationObserver,Number,Math});
assert.equal(calls,1);'''
        result = subprocess.run(['node','-e',harness,script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_executor_installs_separate_native_code_then_reads_preview(self):
        plan = page_embeds.validate(config(), approved_html=HTML, receipt=RECEIPT, location_id='loc-1')

        class Locator:
            def __init__(self, value=None): self.value = value
            def evaluate_all(self, _): return self.value or []
            def get_attribute(self, _): return '/preview/slug'
            def evaluate(self, _): return 'col-1'
            def count(self): return 1
            def wait_for(self, **_): return None
            def get_by_role(self, *_a, **_k): return self
        class Frame:
            def __init__(self):
                class CodeList:
                    calls = 0
                    def evaluate_all(inner, _):
                        inner.calls += 1
                        return [] if inner.calls == 1 else ['code-new']
                self.codes = CodeList()
                self.dialog = Locator()
            def locator(self, selector):
                if selector == '.c-custom-code': return self.codes
                if selector.startswith('.c-custom-code[id='): return Locator()
                if 'preview' in selector: return Locator()
                raise AssertionError(selector)
            def get_by_role(self, *_a, **_k): return self.dialog
        class Preview:
            url = 'https://example.test/preview/slug'
            def __init__(self): self.context = Context()
            def goto(self, *_a, **_k): return type('Response', (), {'status': 200})()
            def locator(self, _): return self
            def evaluate(self, _): return {'id':'demo-frame','tag':'IFRAME','width':900,'height':520,'display':'block','visible':True}
            def wait_for(self, **_): return None
        class Context:
            def new_page(self): return PreviewPage()
        class PreviewPage(Preview):
            def __init__(self): self.context = Context()
            def close(self): pass
        frame = Frame()
        page = type('Page', (), {'context': Context()})()
        step = {'id':'resize-demo','placement':{'section_id':'s','row_id':'r','column_id':'col-1'},'plan':plan}
        with patch('playwright_recipes.skill6_playwright.builder', return_value=frame), \
             patch('playwright_recipes.skill6_playwright.native_order_inventory', return_value={}), \
             patch('playwright_recipes.skill6_playwright.assert_native_orders_preserved'), \
             patch('playwright_recipes.skill6_playwright.placement_column_id', return_value='col-1'), \
             patch('playwright_recipes.skill6_playwright.page_builder_ready'), \
             patch('playwright_recipes.skill6_playwright.select_install_column'), \
             patch('playwright_recipes.skill6_playwright.add_tile'), \
             patch('playwright_recipes.skill6_playwright.save_page'), \
             patch('playwright_recipes.skill6_playwright.visible', return_value=False), \
             patch('playwright_recipes.skill6_playwright.click'), \
             patch('playwright_recipes.skill6_playwright.fill'), \
             patch('playwright_recipes.skill6_playwright.validate_placement'):
            result = page_embeds.configure(page, step)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['iframe']['height'], 520)

    def test_completed_replay_checks_code_parent_and_preview_without_writes(self):
        plan = page_embeds.validate(config(), approved_html=HTML, receipt=RECEIPT, location_id='loc-1')
        parents = {'section_id':'s','row_id':'r','column_id':'c1'}
        class Code:
            def evaluate(self, _): return parents
        class Link:
            def count(self): return 1
            def get_attribute(self, _): return 'https://example.test/preview/current'
        class Frame:
            def locator(self, selector):
                if 'preview' in selector: return Link()
                raise AssertionError(selector)
        class Preview:
            url = 'https://example.test/preview/current'
            def goto(self, *_a, **_k): return type('Response', (), {'status':200})()
            def locator(self, _): return self
            def wait_for(self, **_): return None
            def evaluate(self, _): return {'id':'demo-frame','tag':'IFRAME','width':900,'height':520,'display':'block','visible':True}
            def close(self): pass
        class Context:
            def new_page(self): return Preview()
        page = type('Page', (), {'context':Context()})()
        result = {'status':'VERIFIED','code_element_id':'code-1',
                  'approved_html_sha256':HASH,'preview_url':'https://example.test/preview/current',
                  'iframe':{'iframe_id':'demo-frame','width':900,'height':520,'visible':True,'status':'VERIFIED'}}
        step = {'id':'resize-demo','placement':{'section_id':'s','row_id':'r','column_id':'c1'},'plan':plan}
        with patch('playwright_recipes.skill6_playwright.builder', return_value=Frame()), \
             patch('playwright_recipes.skill6_playwright.placement_column_id', return_value='c1'), \
             patch('playwright_recipes.skill6_playwright.page_builder_ready'), \
             patch('playwright_recipes.skill6_playwright.validate_placement'), \
             patch('playwright_recipes.pages_checkout.resolve_code_target', return_value={'locator':Code(),'section_id':'s'}) as resolve:
            verified = page_embeds.verify_completed(page, step, result)
        resolve.assert_called_once()
        self.assertEqual(resolve.call_args.args[1:], ('code-1', 'ZHC Embed resize-demo'))
        self.assertEqual(verified['status'], 'VERIFIED')

        parents['column_id'] = 'other-column'
        with patch('playwright_recipes.skill6_playwright.builder', return_value=Frame()), \
             patch('playwright_recipes.skill6_playwright.placement_column_id', return_value='c1'), \
             patch('playwright_recipes.skill6_playwright.page_builder_ready'), \
             patch('playwright_recipes.skill6_playwright.validate_placement'), \
             patch('playwright_recipes.pages_checkout.resolve_code_target', return_value={'locator':Code(),'section_id':'s'}):
            with self.assertRaises(Stop): page_embeds.verify_completed(page, step, result)


if __name__ == '__main__':
    unittest.main()
