"""Captured page heading is one child of the full native builder page container.

The fixture deliberately includes question/option/footer text beneath
.builder-form-name. Its real DOM text makes the old container selector fail.
Standard-library DOM parsing keeps this regression mandatory on Mac/Linux.
"""
import re
import unittest
from xml.etree import ElementTree

import quiz_text_questions as text
from skill6_playwright import Stop
from test_quiz_text_questions import step


HTML='''<main><div class="survey-form-container flex">
  <div class="builder-form-name">
    <div class="flex w-full">
      <div class="flex items-center text-sm font-semibold">Page 1</div>
      <div class="ml-2"></div>
    </div>
    <div id="the-form-builder" class="form-element form-builder--wrap">
      <div class="drop"><div class="builder_sub_container">
        <div class="smooth-dnd-draggable-wrapper"><div class="form-builder--item">
          <div>Single Choice 102pjx</div><label>Option1</label><label>Option2</label>
        </div></div>
      </div></div>
    </div>
    <button>Submit</button><button>Add Page</button>
    <section>Result Page Template<button>Edit Template</button></section>
  </div>
</div></main>'''


class Dom:
    """Small CSS-to-DOM adapter; values/counts come from actual fixture nodes."""
    def __init__(self,nodes,parents=None):
        self.nodes=list(nodes)
        self.parents=parents if parents is not None else {child:parent for root in self.nodes for parent in root.iter() for child in parent}
    def count(self):return len(self.nodes)
    def nth(self,index):return Dom([self.nodes[index]],self.parents)
    def is_visible(self):return bool(self.nodes)
    def inner_text(self):
        if len(self.nodes)!=1:raise AssertionError('Ambiguous DOM text')
        return ''.join(self.nodes[0].itertext())
    def input_value(self):return self.nodes[0].get('value','')
    def is_enabled(self):return 'disabled' not in self.nodes[0].attrib
    def get_by_role(self,role,*,name,exact):
        if role!='textbox':raise AssertionError('Uncaptured fixture role '+role)
        nodes=[node for root in self.nodes for node in list(root.iter())[1:]
            if node.tag in ('input','textarea') and node.get('type','text') not in ('hidden','radio','checkbox')
            and node.get('aria-label',node.get('placeholder',''))==name]
        return Dom(nodes,self.parents)
    def locator(self,selector):
        if selector=='..':return Dom([self.parents[node] for node in self.nodes if node in self.parents],self.parents)
        segments=[segment.strip() for segment in selector.split('>')]
        nodes=self.nodes
        for index,segment in enumerate(segments):
            if segment==':scope':continue
            first=segment.endswith(':first-child')
            if first:segment=segment[:-len(':first-child')]
            attributes=re.findall(r'\[([A-Za-z_-]+)="([^"]*)"\]',segment)
            segment=re.sub(r'\[[^\]]+\]','',segment)
            tag=re.match(r'^[A-Za-z][A-Za-z0-9_-]*',segment)
            tag=tag.group() if tag else None
            identity=re.findall(r'#([A-Za-z0-9_-]+)',segment)
            classes=set(re.findall(r'\.([A-Za-z0-9_-]+)',segment))
            found=[]
            for node in nodes:
                candidates=list(node.iter())[1:] if index==0 else list(node)[:1] if first else list(node)
                for candidate in candidates:
                    if ((tag is None or candidate.tag==tag)
                            and (not identity or candidate.get('id')==identity[0])
                            and all(candidate.get(key)==value for key,value in attributes)
                            and classes.issubset(set(candidate.get('class','').split()))):
                        found.append(candidate)
            nodes=found
        return Dom(nodes,self.parents)


class NativePageHeadingDomTests(unittest.TestCase):
    def test_real_builder_container_text_is_not_its_page_heading(self):
        frame=Dom([ElementTree.fromstring(HTML)])
        whole=frame.locator('.builder-form-name').inner_text()
        self.assertIn('Single Choice 102pjx',whole);self.assertIn('Submit',whole)
        self.assertNotEqual(whole.strip(),'Page 1')
        owners=text._owners(frame,step()['payload'])
        self.assertEqual(len(owners),1)
        self.assertEqual(owners[0][0].locator(text.PAGE_HEADING).inner_text(),'Page 1')

    def test_wrong_heading_is_not_hidden_by_matching_footer_or_question_text(self):
        fixture=HTML.replace('>Page 1</div>','>Other page</div>').replace('>Submit</button>','>Page 1</button>')
        with self.assertRaisesRegex(Stop,'page order/label'):
            text._owners(Dom([ElementTree.fromstring(fixture)]),step()['payload'])

    def test_duplicate_or_uncaptured_heading_shape_refuses(self):
        heading='<div class="flex items-center text-sm font-semibold">Page 1</div>'
        for fixture in (HTML.replace(heading,heading+heading),HTML.replace('text-sm font-semibold','different-heading')):
            with self.subTest(fixture=fixture),self.assertRaises(Stop):
                text._owners(Dom([ElementTree.fromstring(fixture)]),step()['payload'])

    def test_native_default_query_token_is_allowed_when_final_keys_are_disjoint(self):
        for target in ('existing','new'):
            value=step()
            question=value['payload']['pages'][0]['questions'][0] if target=='existing' else value['payload']['questions'][0]
            question['query_key']='Single_Line'
            with self.subTest(target=target):self.assertEqual(text.validate(value),value['payload'])


if __name__=='__main__':unittest.main()
