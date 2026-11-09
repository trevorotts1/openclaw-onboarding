"""The captured tail trash must remove that row and preserve the full prefix."""
from copy import deepcopy
import unittest
from unittest.mock import Mock,patch

import form_condition_stack as native
from skill6_playwright import Stop


class PredicateRemovalTests(unittest.TestCase):
    def fixture(self,*,wrong_row=False,path_drift=False):
        before={'match':'all','clauses':[{'if_field':'First Name','operator':'Is Empty'},
            {'if_field':'Email','operator':'Is Filled'}],'effect':'Hide Field','target':'Phone'}
        state=deepcopy(before)
        modal,source,row,owner,trash,path,count,operator,value=[Mock() for _ in range(9)]
        source.count.side_effect=lambda:int(len(state['clauses'])==2)
        source.locator.return_value=row;row.locator.return_value=owner
        row.get_attribute.return_value='mb-8 flex gap-x-2 px-0.5'
        owner.get_attribute.return_value='mb-2 flex flex-col gap-y-2 text-base'
        owner.locator.side_effect=lambda selector:trash if selector.startswith(':scope >') else Mock(count=lambda:1)
        trash.count.return_value=1
        trash.get_attribute.return_value='mr-3 h-4 w-4 cursor-pointer text-error-700'
        trash.locator.return_value=path;path.count.return_value=1
        path.get_attribute.return_value='foreign-delete-icon' if path_drift else native._ROW_DELETE_PATH
        count.count.side_effect=lambda:len(state['clauses'])
        operator.count.side_effect=lambda:int(len(state['clauses'])==2)
        value.count.return_value=0
        modal.locator.side_effect={'#selectedField-1':source,'#selectedOperation-1':operator,
            '#inputValue-1':value,'[id^="selectedField-"]':count}.__getitem__
        clicks=[];reads=[]
        def click(node):
            self.assertIs(node,trash);clicks.append(node)
            state['clauses'].pop(0 if wrong_row else -1)
        def inspect(_modal,expected):
            reads.append(deepcopy(expected))
            if state!=expected:raise Stop('Remaining predicate prefix differs from expected native state')
        return modal,before,click,inspect,clicks,reads,state

    def test_tail_delete_has_no_confirmation_and_preserves_initial_if_and_outcome(self):
        modal,before,click,inspect,clicks,reads,state=self.fixture()
        with patch.object(native,'click',side_effect=click),patch.object(native.group,'_modal_state',side_effect=inspect):
            self.assertEqual(native._remove_tail(modal,before,2,lambda:None),1)
        self.assertEqual(len(clicks),1)
        self.assertEqual(state['clauses'],[before['clauses'][0]])
        self.assertEqual((state['effect'],state['target']),('Hide Field','Phone'))
        self.assertEqual([len(read['clauses']) for read in reads],[2,1])

    def test_count_drop_alone_cannot_bless_removing_the_wrong_predicate(self):
        modal,before,click,inspect,clicks,_,_=self.fixture(wrong_row=True)
        with patch.object(native,'click',side_effect=click),patch.object(native.group,'_modal_state',side_effect=inspect), \
             self.assertRaisesRegex(Stop,'prefix differs'):
            native._remove_tail(modal,before,2,lambda:None)
        self.assertEqual(len(clicks),1)

    def test_wrong_svg_path_refuses_before_any_delete_click(self):
        modal,before,click,inspect,clicks,_,_=self.fixture(path_drift=True)
        with patch.object(native,'click',side_effect=click),patch.object(native.group,'_modal_state',side_effect=inspect), \
             self.assertRaisesRegex(Stop,'differs from the captured trash'):
            native._remove_tail(modal,before,2,lambda:None)
        self.assertEqual(clicks,[])

    def test_initial_if_row_is_never_deleted(self):
        with patch.object(native,'click') as click,self.assertRaisesRegex(Stop,'initial If row'):
            native._remove_tail(Mock(),{},1,lambda:None)
        click.assert_not_called()


if __name__=='__main__':unittest.main()
