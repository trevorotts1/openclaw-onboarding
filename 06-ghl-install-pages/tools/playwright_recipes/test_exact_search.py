"""Search absence is current-query proof, never a stale generic empty list."""
import unittest
from unittest.mock import patch

import skill6_playwright as runner


class Locator:
    def __init__(self, page, kind, name=None):
        self.page, self.kind, self.name = page, kind, name

    def count(self):
        state = self.page.state
        if self.kind == 'textbox':
            return state.get('textbox_count',1)
        if self.kind == 'gridcell':
            return state.get('cells',0) if self.name == self.page.requested else 0
        if self.kind == 'text':
            return state.get('texts',[]).count(self.name)
        return 0

    def is_visible(self):
        if self.kind == 'gridcell':
            return self.page.state.get('cell_visible',True)
        return self.name not in self.page.state.get('hidden_texts',[])

    def input_value(self):
        self.page.input_reads += 1
        values = self.page.input_values
        if values:
            return values[min(self.page.input_reads - 1,len(values)-1)]
        return self.page.state.get('query',self.page.requested)

    def wait_for(self, **_):
        if self.count() != 1:
            raise runner.Stop('Fixture input not ready')

    def fill(self, value):
        self.page.fills.append(value)
        self.page.requested = value


class Page:
    def __init__(self, states, *, input_values=None):
        self.states = states
        self.state = states[0]
        self.requested = None
        self.fills = []
        self.input_reads = 0
        self.input_values = input_values
        self.polls = 0

    def get_by_role(self, role, *, name, exact):
        assert exact
        return Locator(self,'textbox' if role == 'textbox' else 'gridcell',name)

    def get_by_text(self, name, *, exact):
        assert exact
        return Locator(self,'text',name)

    def wait(self, predicate, message, **_):
        for state in self.states:
            self.polls += 1
            self.state = state
            if predicate():
                return
        raise runner.Stop(message)


class ExactSearchTests(unittest.TestCase):
    def search(self, page, name='ZHC Exact Fixture', area='funnels'):
        with patch.object(runner,'wait_until',side_effect=page.wait):
            return runner.exact_search(page,area,name)

    def test_native_empty_phrase_is_bound_to_exact_current_query(self):
        name = 'ZHC Exact Fixture'
        page = Page([{'texts':["No results found for '"+name+"'"]}])
        self.assertIsNone(self.search(page,name))
        self.assertEqual(page.fills,[name])

    def test_form_empty_requires_both_exact_visible_heading_and_query(self):
        name = 'ZHC Exact Fixture'
        phrase = 'Your search “'+name+'” did not match any items. Please try again.'
        for texts, accepted in ((['No items found',phrase],True),
                                (['No items found'],False),([phrase],False),
                                (['No items found','Your search “OLD” did not match any items. Please try again.'],False),
                                (['No items found','Your search “'+name+'” did not match any items.'],False)):
            with self.subTest(texts=texts):
                page = Page([{'texts':texts}])
                if accepted:
                    self.assertIsNone(self.search(page,name,area='forms'))
                else:
                    with self.assertRaises(runner.Stop):
                        self.search(page,name,area='forms')

    def test_generic_zero_counts_and_previous_query_empty_never_authorize_creation(self):
        for phrase in ('0 - 0 of 0','0–0 of 0','No results found',
                       'No funnels found',"No results found for 'OLD'",'No websites found'):
            with self.subTest(phrase=phrase):
                page = Page([{'texts':[phrase]}])
                with self.assertRaises(runner.Stop):
                    self.search(page)
                self.assertEqual(page.fills,['ZHC Exact Fixture'])

    def test_current_textbox_value_is_required_even_if_empty_phrase_or_row_matches(self):
        name = 'ZHC Exact Fixture'
        for state in ({'query':'OLD','texts':["No results found for '"+name+"'"]},
                      {'query':'OLD','cells':1}):
            with self.subTest(state=state), self.assertRaises(runner.Stop):
                self.search(Page([state]),name)

    def test_stale_empty_waits_for_exact_existing_result_without_refilling(self):
        page = Page([{'texts':["No results found for 'OLD'"]},
                     {'cells':0,'texts':[]}, {'cells':1}])
        result = self.search(page)
        self.assertIsInstance(result,Locator)
        self.assertEqual(result.kind,'gridcell')
        self.assertEqual(page.polls,3)
        self.assertEqual(page.fills,['ZHC Exact Fixture'])

    def test_form_skeleton_rows_do_not_authorize_absence_before_query_evidence(self):
        name = 'ZHC Exact Fixture'
        skeleton = {'cells':0,'blank_skeleton_rows':20,'texts':[]}
        with self.assertRaises(runner.Stop):
            self.search(Page([skeleton]),name,area='forms')
        phrase = 'Your search “'+name+'” did not match any items. Please try again.'
        page = Page([skeleton,{'texts':['No items found',phrase]}])
        self.assertIsNone(self.search(page,name,area='forms'))
        self.assertEqual(page.polls,2)
        self.assertEqual(page.fills,[name])

    def test_query_bound_empty_uses_literal_punctuation_without_regex_or_substrings(self):
        for name in ("ZHC O'Reilly [A+B].*?",'ZHC (one|two) $ \\ demo',
                     'ZHC “quoted” and \'single\''):
            with self.subTest(name=name):
                exact = "No results found for '"+name+"'"
                self.assertIsNone(self.search(Page([{'texts':[exact]}]),name))
                for wrong in (exact+' extra',"Prefix "+exact,
                              "No results found for '"+name.replace('[','(')+" extra'"):
                    with self.assertRaises(runner.Stop):
                        self.search(Page([{'texts':[wrong]}]),name)

    def test_hidden_or_duplicate_empty_evidence_does_not_authorize_creation(self):
        phrase = "No results found for 'ZHC Exact Fixture'"
        for state in ({'texts':[phrase],'hidden_texts':[phrase]},
                      {'texts':[phrase,phrase]}):
            with self.subTest(state=state), self.assertRaises(runner.Stop):
                self.search(Page([state]))

    def test_duplicate_exact_rows_are_refused_and_hidden_row_is_not_absence(self):
        for state in ({'cells':2},
                      {'cells':1,'cell_visible':False,
                       'texts':["No results found for 'ZHC Exact Fixture'"]}):
            with self.subTest(state=state), self.assertRaises(runner.Stop):
                self.search(Page([state]))

    def test_textbox_drift_after_settlement_refuses_stale_return(self):
        name = 'ZHC Exact Fixture'
        for state, values in (({'cells':1},[name,'OLD']),
                              ({'texts':["No results found for '"+name+"'"]},[name,name,'OLD'])):
            with self.subTest(state=state), self.assertRaises(runner.Stop):
                self.search(Page([state],input_values=values),name)


if __name__ == '__main__':
    unittest.main()
