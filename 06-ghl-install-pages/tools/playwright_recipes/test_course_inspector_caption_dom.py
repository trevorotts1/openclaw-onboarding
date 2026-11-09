"""Caption-equal authored DOM must not substitute for a native inspector."""
import unittest
from xml.etree import ElementTree as ET

import course_text_blocks as blocks
from skill6_playwright import Stop


class CaptionDom:
    def __init__(self,nodes,parents):self.nodes=nodes;self.parents=parents
    def count(self):return len(self.nodes)
    def nth(self,index):return CaptionDom([self.nodes[index]],self.parents)
    def is_visible(self):return self.nodes[0].get('hidden') is None
    def evaluate(self,script,owners):
        # Real native-shaped DOM ancestry, not a pre-baked "is heading" flag.
        # This adapter implements the closest/querySelector reads in the leaf.
        def matches(node,selector):
            if selector==blocks.EDITOR:
                return (node.tag=='div' and node.get('contenteditable')=='true'
                    and {'tiptap','ProseMirror','general-courses-editor'}.issubset(node.get('class','').split()))
            return any(node.get('id')==part[1:] if part.startswith('#')
                else part[1:] in node.get('class','').split() for part in selector.split(', '))
        node=self.nodes[0]
        for selector in owners:
            ancestor=node
            while ancestor is not None:
                if matches(ancestor,selector):return False
                ancestor=self.parents.get(ancestor)
            if any(matches(child,selector) for child in node.iter() if child is not node):return False
        return True


class Page:
    def __init__(self,root):
        self.root=root;self.parents={child:parent for parent in root.iter() for child in parent}
    def get_by_text(self,value,*,exact):
        assert exact
        return CaptionDom([node for node in self.root.iter()
            if ''.join(node.itertext()).strip()==value],self.parents)


def surface(caption,*,native=None):
    root=ET.Element('main')
    inspector=ET.SubElement(root,'div')
    heading=ET.SubElement(inspector,'div');heading.text=native or caption
    ET.SubElement(inspector,'button',{'id':'delete-block-btn'}).text='Delete Block'
    rte=ET.SubElement(inspector,'div',{'class':'tiptap ProseMirror general-courses-editor','contenteditable':'true'})
    ET.SubElement(rte,'p').text=caption
    body=ET.SubElement(root,'div',{'id':'content-container'})
    ET.SubElement(body,'div',{'class':'editor-content rich-text-viewer'}).text=caption
    hero=ET.SubElement(root,'div',{'class':'welcome-hero-image','isediting':'true'})
    ET.SubElement(hero,'div',{'id':'banner-title'}).text=caption
    instructor=ET.SubElement(root,'div',{'class':'instructor-card','data-active':'false'})
    ET.SubElement(instructor,'div').text=caption
    return Page(root),heading


class CapturedInspectorCaptionDom(unittest.TestCase):
    def test_equal_rte_body_hero_course_title_and_instructor_text_do_not_collide(self):
        for caption in ('Text Block','Image'):
            page,heading=surface(caption)
            self.assertGreater(page.get_by_text(caption,exact=True).count(),4)
            actual=blocks._inspector_caption(page,caption)
            self.assertIs(actual.nodes[0],heading)
    def test_wrong_inspector_cannot_borrow_its_caption_from_authored_rte_or_preview(self):
        for caption in ('Text Block','Image'):
            page,_=surface(caption,native='Custom Block')
            with self.subTest(caption=caption),self.assertRaises(Stop):
                blocks._inspector_caption(page,caption)
    def test_uncaptured_duplicate_native_region_and_missing_native_caption_still_refuse(self):
        page,_=surface('Image')
        ET.SubElement(page.root,'div').text='Image'
        page=Page(page.root)
        with self.assertRaises(Stop):blocks._inspector_caption(page,'Image')
        page,heading=surface('Text Block');heading.set('hidden','')
        with self.assertRaises(Stop):blocks._inspector_caption(page,'Text Block')


if __name__=='__main__':unittest.main()
