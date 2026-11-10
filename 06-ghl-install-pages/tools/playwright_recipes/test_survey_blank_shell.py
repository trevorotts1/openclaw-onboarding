"""Captured saved two-empty-owner DOM, positive readiness and create uncertainty."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from xml.etree import ElementTree

from test_survey_radio_creation import ShellDom
from test_survey_creation import inputs
from skill6_playwright import Stop

blank=importlib.import_module('playwright_recipes.survey_blank_shell')


class Dom(ShellDom):
    def locator(self,selector):
        found=super().locator(selector)
        return Dom(found.nodes,self.parents)
    def nth(self,index):return Dom([self.nodes[index]],self.parents)
    def get_by_role(self,role,*,name=None,exact=False):
        found=super().get_by_role(role,name=name,exact=exact)
        return Dom(found.nodes,self.parents)
    def get_by_text(self,value,*,exact):
        found=[]
        for root in self.nodes:
            for node in root.iter():
                if ''.join(node.itertext()).strip()==value and not any(''.join(child.itertext()).strip()==value for child in node):
                    found.append(node)
        return Dom(found,self.parents)


def plan():
    value=inputs();value.pop('standard_fields');value['slide_count']=2
    return value


class EmptySurveyShell(unittest.TestCase):
    def test_actual_saved_two_empty_owner_capture_is_positive_and_nonempty_drift_refuses(self):
        root=ElementTree.fromstring((Path(__file__).parent/'fixtures/survey-two-empty-owners.html').read_text())
        page=MagicMock();value=plan();page.url=value['start_url'].replace('survey-builder/main','survey-builder-v2/NEW')
        page.frame_locator.return_value=Dom([root])
        with patch.object(blank,'assert_tenant'):
            saved=blank.snapshot(page,value,page.url)
            self.assertEqual(saved['slide_labels'],['P1 - Slide 1','P2 - Slide 2'])
            self.assertEqual(saved['slides'],[{'canvas':[]},{'canvas':[]}])
            owner=root.findall('.//div[@class="survey-form-container"]')[1]
            ElementTree.SubElement(owner,'div',{'class':'form-field-wrapper'})
            with self.assertRaises(Stop):blank.snapshot(page,value,page.url)
    def test_uncertain_create_is_journaled_and_never_repeated(self):
        page=MagicMock();create=page.get_by_role.return_value
        create.count.return_value=1;create.is_enabled.return_value=True
        create.click.side_effect=TimeoutError('create uncertain')
        with tempfile.TemporaryDirectory() as directory,patch.object(blank,'navigate'),patch.object(blank,'exact_search',return_value=None),patch.object(blank,'assert_tenant'):
            with self.assertRaises(TimeoutError):blank.configure(page,plan(),directory)
            with self.assertRaises(Stop):blank.configure(page,plan(),directory)
            state=json.loads((Path(directory)/'blank-shell-state.json').read_text())
        self.assertEqual(state['status'],'NEEDS_RECONCILIATION');create.click.assert_called_once()


if __name__=='__main__':unittest.main()
