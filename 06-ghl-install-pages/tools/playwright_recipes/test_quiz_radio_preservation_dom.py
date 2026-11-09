"""Native option-row DOM labels/categories/scores must survive unrelated inserts."""
from copy import deepcopy
import unittest
from xml.etree import ElementTree

import quiz_text_questions as text
from skill6_playwright import Stop
from test_quiz_page_heading_dom import Dom


HTML='''<main>
<div class="option-row">
  <input aria-label="Label" value="Option A" />
  <input placeholder="10" value="12.5" />
  <div><div><div><div id="category-picker">Overall Only</div></div></div></div>
</div>
<div class="option-row">
  <input aria-label="Label" value="Option B" />
  <input placeholder="10" value="" disabled="disabled" />
  <div><div><div><div id="category-picker">Select category</div></div></div></div>
</div>
</main>'''


class RadioSiblingDomTests(unittest.TestCase):
    def test_real_option_row_ownership_preserves_raw_scoring_states_read_only(self):
        root=ElementTree.fromstring(HTML);before=ElementTree.tostring(root)
        actual=text._radio_options(Dom([root]))
        self.assertEqual(actual,[{'label':'Option A','category':'Overall Only','score':'12.5','score_enabled':True},
            {'label':'Option B','category':'Select category','score':'','score_enabled':False}])
        self.assertEqual(ElementTree.tostring(root),before)

    def test_collateral_label_category_score_or_enabled_change_is_observable(self):
        root=ElementTree.fromstring(HTML);before=text._radio_options(Dom([root]))
        for mutation in ('label','category','score','enabled'):
            changed=deepcopy(root);row=changed[0]
            if mutation=='label':row[0].set('value','Changed option')
            elif mutation=='category':row[2][0][0][0].text='Changed category'
            elif mutation=='score':row[1].set('value','99')
            else:row[1].set('disabled','disabled')
            with self.subTest(mutation=mutation):
                self.assertNotEqual(text._radio_options(Dom([changed])),before)

    def test_missing_or_reparented_option_score_cannot_be_assigned_by_global_index(self):
        for mutation in ('missing','reparented'):
            root=ElementTree.fromstring(HTML)
            if mutation=='missing':root[0].remove(root[0][1])
            else:
                score=root[0][1];root[0].remove(score);root[1].append(score)
            with self.subTest(mutation=mutation),self.assertRaises(Stop):
                text._radio_options(Dom([root]))


if __name__=='__main__':unittest.main()
