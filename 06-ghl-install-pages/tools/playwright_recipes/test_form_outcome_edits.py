"""Existing outcome edits reuse captured predicate/effect controls and save flow."""
from copy import deepcopy
from unittest.mock import Mock,patch
import unittest

import form_condition_outcomes as native
from skill6_playwright import Stop
from test_form_condition_mixed import NativeModal
from test_form_condition_outcomes import rule,record
from test_form_outcome_removal import OutcomeDrawer
from test_form_condition_card_removal import instant_wait


class OutcomeModal(NativeModal):
    def __init__(self,before,*,collateral=False,flatten=False):
        super().__init__()
        self.rows=deepcopy(before['clauses']);self.edges=native.group._connectors(before)
        self.value=deepcopy(before);self.collateral=collateral;self.flatten=flatten
        self.html='<p><strong>'+before['message']+'</strong></p>' if 'message' in before else None
        self.cards=[record(before,self.html),record(rule('Hide Field'))]
        self.heading=Mock();self.heading.count.return_value=1
        self.heading.get_by_text.return_value=self.heading
        self.control=Mock();self.control.count.return_value=1
        self.control.input_value.side_effect=lambda:self.value.get('redirect_url')
        self.control.inner_text.side_effect=lambda:self.value.get('message')
        self.control.get_attribute.return_value='https://www.example.com'
        self.control.locator.return_value.count.return_value=0

    def locator(self,selector):
        if selector=='.hl-modal-heading':return self.heading
        if selector in ('#redirectToUrlInput input',native.RTE):return self.control
        return super().locator(selector)

    def fill(self,node,value):
        if node is self.control:
            key='redirect_url' if 'redirect_url' in self.value else 'message'
            self.value[key]=value
            if key=='message':self.html='<p>'+value+'</p>'
        else:node.row.update(value=value)

    def click(self,node):
        if node is self.save:
            self.value['clauses']=deepcopy(self.rows)
            if len(set(self.edges))>1:self.value.update(match='mixed',connectors=list(self.edges))
            else:
                self.value['match']='any' if self.edges and self.edges[0]=='or' else 'all'
                self.value.pop('connectors',None)
            self.cards[self.editing]=record(self.value,
                '<p>'+self.value['message']+'</p>' if self.flatten else self.html)
            if self.collateral:self.cards[1]['rule']['target']='Last Name'
            self.save.is_visible.return_value=False
            return
        super().click(node)


class ExistingEditTests(unittest.TestCase):
    def run_edit(self,before,desired,**options):
        state=OutcomeModal(before,**options);snapshot=deepcopy(state.cards)
        with patch.object(native,'click',side_effect=state.click), \
             patch.object(native.group,'_choose',side_effect=state.choose), \
             patch.object(native.group,'_selected',side_effect=lambda node:node.native_value), \
             patch.object(native,'fill',side_effect=state.fill), \
             patch.object(native,'_inventory',side_effect=lambda _:deepcopy(state.cards)), \
             patch.object(native,'wait_until',side_effect=instant_wait):
            result=native._edit(state.frame,state.dialog,0,before,desired,snapshot,lambda:None)
        return state,result,snapshot

    def test_edits_exact_existing_redirect_and_grows_predicate_with_captured_connector(self):
        before=rule();desired=rule(redirect_url='https://example.com/new',match='any',clauses=[
            {'if_field':'First Name','operator':'Is Filled'},
            {'if_field':'Email','operator':'Contains','value':'@'}])
        state,result,snapshot=self.run_edit(before,desired)
        self.assertEqual(state.clicked,[(0,'or')]);self.assertEqual(result[0]['rule'],desired)
        self.assertEqual(result[1],snapshot[1])

    def test_predicate_only_message_edit_preserves_saved_rich_html(self):
        before=rule(native.MESSAGE);desired=rule(native.MESSAGE,clauses=[
            {'if_field':'Email','operator':'Is Filled'}])
        state,result,snapshot=self.run_edit(before,desired)
        self.assertEqual(result[0]['rich_html_sha256'],snapshot[0]['rich_html_sha256'])
        self.assertEqual(state.html,'<p><strong>Approved message</strong></p>')

    def test_changed_message_is_authored_as_literal_plain_copy_and_hashes_saved_markup(self):
        before=rule(native.MESSAGE);desired=rule(native.MESSAGE,message='<b>New literal copy</b>')
        _,result,snapshot=self.run_edit(before,desired)
        self.assertEqual(result[0]['rule'],desired)
        self.assertNotEqual(result[0]['rich_html_sha256'],snapshot[0]['rich_html_sha256'])

    def test_sibling_change_or_unrequested_message_flattening_fails_after_rule_save(self):
        before=rule(native.MESSAGE);desired=rule(native.MESSAGE,clauses=[
            {'if_field':'Email','operator':'Is Filled'}])
        for options in ({'collateral':True},{'flatten':True}):
            with self.subTest(options=options),self.assertRaises(Stop):self.run_edit(before,desired,**options)

    def test_actual_existing_modal_mismatch_stops_before_first_edit(self):
        state=OutcomeModal(rule());snapshot=deepcopy(state.cards)
        with patch.object(native,'_inventory',return_value=snapshot),patch.object(native,'click') as click, \
             patch.object(native,'_modal_state',side_effect=Stop('stale persisted modal')), \
             patch.object(native.group,'_choose') as choose,patch.object(native,'fill') as fill, \
             self.assertRaisesRegex(Stop,'stale persisted modal'):
            native._edit(state.frame,state.dialog,0,rule(),rule(redirect_url='https://example.com/new'),snapshot,lambda:None)
        choose.assert_not_called();fill.assert_not_called();self.assertEqual(click.call_count,1)


class ExistingEditPlanTests(unittest.TestCase):
    def test_same_kind_complete_expected_stack_authorizes_edits_but_never_emulated_reorder(self):
        previous=[rule(),rule(native.MESSAGE)]
        desired=[rule(redirect_url='https://example.com/new'),rule(native.MESSAGE,message='New')]
        self.assertEqual(native.validate({'expected_rules':previous,'rules':desired})['rules'],desired)
        for rules in ([previous[1],previous[0]],[rule(native.DISQUALIFY),previous[1]]):
            with self.subTest(rules=rules),self.assertRaises(Stop):native.validate({'expected_rules':previous,'rules':rules})

    def test_disqualify_can_change_its_already_captured_message_redirect_mode(self):
        before=rule(native.DISQUALIFY)
        after=rule(native.DISQUALIFY,mode=native.REDIRECT,redirect_url='https://example.com/disqualified')
        after.pop('message')
        self.assertEqual(native.validate({'expected_rules':[before],'rules':[after]})['rules'],[after])

    def test_explicit_mapped_replacement_rejects_ambiguous_ordinals_and_emulated_reorder_before_browser(self):
        before=[rule(),rule(native.MESSAGE)]
        wanted=[rule(redirect_url='https://example.com/new'),rule(native.MESSAGE,message='New')]
        for indices in (None,False,[0],[True,1],[0,0],[1,0],[None,0],[0,9]):
            data={'expected_rules':before,'rules':wanted,'source_indices':indices};page=Mock()
            with self.subTest(indices=indices),self.assertRaises(Stop):native.configure(page,data)
            self.assertFalse(page.mock_calls)
        for rules,indices in (([before[1]],[0]),([before[0]],[None])):
            with self.subTest(rules=rules),self.assertRaises(Stop):
                native.validate({'expected_rules':before,'rules':rules,'source_indices':indices})
        data={'expected_rules':before,'rules':[wanted[0]],'source_indices':[0]}
        other={'expected_rules':before,'rules':[wanted[0]],'source_indices':[None]}
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash(other))

    def test_shared_tail_predicate_removal_accepts_effect_specific_full_state_reader(self):
        from test_form_predicate_removal import PredicateRemovalTests
        fixture=PredicateRemovalTests().fixture()
        modal,before,click,inspect,clicks,reads,_=fixture
        with patch.object(native.stack,'click',side_effect=click), \
             patch.object(native.group,'_modal_state',side_effect=AssertionError('Wrong Show/Hide reader')):
            self.assertEqual(native.stack._remove_tail(modal,before,2,lambda:None,read_state=inspect),1)
        self.assertEqual(len(clicks),1);self.assertEqual([len(x['clauses']) for x in reads],[2,1])


class ExistingEditLifecycleTests(unittest.TestCase):
    def exercise(self,*,lost=False,stale=False):
        state=OutcomeDrawer(lost_save=lost);before=deepcopy(state.current)
        desired=[deepcopy(item['rule']) for item in before]
        desired[1]['redirect_url']='https://example.com/new'
        data={'expected_rules':[item['rule'] for item in before],'rules':desired}
        if stale:state.current[0]['rule']['target']='Last Name'
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        def edit(_frame,_dialog,index,old,wanted,current,identity):
            identity();self.assertEqual(old,data['expected_rules'][index]);self.assertEqual(current,state.current)
            state.events.append(('edit',index));state.current[index]=record(wanted)
            return deepcopy(state.current)
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click), \
             patch.object(native,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'_edit',side_effect=edit),patch.object(native,'_author') as append, \
             patch.object(native.group,'_wait_for_form_save'), \
             patch.object(native,'reopen_editor',side_effect=state.reopen):
            try:result=native.configure(page,data)
            except Stop as error:result=error
        append.assert_not_called();return state,result,data,before

    def test_edits_only_changed_card_then_one_outer_save_and_independent_reopen(self):
        state,result,data,before=self.exercise()
        self.assertEqual(state.events,[('edit',1),('save',),('reopen',)])
        self.assertEqual(state.persisted[2:],before[2:]);self.assertTrue(native.validate_receipt(result,data))

    def test_stale_sibling_prevents_first_edit_and_lost_save_prevents_success(self):
        state,result,_,_=self.exercise(stale=True)
        self.assertIsInstance(result,Stop);self.assertEqual(state.events,[])
        state,result,_,before=self.exercise(lost=True)
        self.assertIsInstance(result,Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(state.persisted,before)

    def test_mapped_count_change_deletes_only_omitted_cards_edits_original_owner_and_appends_new_tail(self):
        state=OutcomeDrawer();before=deepcopy(state.current)
        desired=[rule(redirect_url='https://example.com/new'),before[3]['rule'],
                 rule(native.MESSAGE,message='New tail message')]
        data={'expected_rules':[item['rule'] for item in before],'rules':desired,'source_indices':[1,3,None]}
        page=Mock();page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        def edit(_frame,_dialog,index,old,wanted,current,identity):
            identity();self.assertEqual(index,0);self.assertEqual(old,before[1]['rule'])
            self.assertEqual(current,state.current);state.events.append(('edit',index))
            state.current[index]=record(wanted);return deepcopy(state.current)
        def append(_frame,_dialog,wanted,current,identity):
            identity();self.assertEqual(current,state.current);state.events.append(('append',len(current)))
            state.current.append(record(wanted,'<p>New tail message</p>'));return deepcopy(state.current)
        with patch.object(native,'form_builder',return_value=state.frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=state.click),patch.object(native.stack,'click',side_effect=state.click), \
             patch.object(native.stack,'wait_until',side_effect=instant_wait), \
             patch.object(native,'_inventory',side_effect=lambda _:deepcopy(state.current)), \
             patch.object(native,'_edit',side_effect=edit),patch.object(native,'_author',side_effect=append), \
             patch.object(native.group,'_wait_for_form_save'),patch.object(native,'reopen_editor',side_effect=state.reopen):
            result=native.configure(page,data)
        self.assertEqual(state.events,[('open_delete',2),('confirm',),('open_delete',0),('confirm',),
            ('edit',0),('append',2),('save',),('reopen',)])
        self.assertEqual([item['rule'] for item in state.persisted],desired)
        self.assertEqual(state.persisted[1],before[3]);self.assertTrue(native.validate_receipt(result,data))


if __name__=='__main__':unittest.main()
