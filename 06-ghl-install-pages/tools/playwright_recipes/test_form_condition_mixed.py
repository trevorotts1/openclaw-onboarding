"""Ordered row connectors survive authoring, saved readback and runtime replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import form_conditions as group
import form_condition_stack as stack
import form_condition_outcomes as outcomes
import editor_replay
import recipe_cli
import skill6_playwright as runner


def mixed(**changes):
    value={'match':'mixed','connectors':['and','or'],
        'clauses':[{'if_field':'Email','operator':'Contains','value':'@'},
                   {'if_field':'First Name','operator':'Is Filled'},
                   {'if_field':'Website','operator':'Is Empty'}],
        'effect':'Hide Field','target':'Last Name'}
    value.update(changes)
    return value


class MixedSchemaTests(unittest.TestCase):
    def test_every_edge_is_explicit_and_the_full_order_survives_validation(self):
        rule=mixed()
        self.assertEqual(group.validate(rule),rule)
        self.assertEqual(stack.validate({'rules':[rule]})['rules'],[rule])
        self.assertEqual(outcomes.validate({'rules':[rule]})['rules'],[rule])
        self.assertEqual(group._expected_rows(rule),[
            ['If','Email','Contains','@'],['And','First Name','Is Filled'],
            ['Or','Website','Is Empty']])
        returned=group.validate(rule);returned['connectors'][0]='or'
        self.assertEqual(rule['connectors'],['and','or'])

    def test_malformed_or_ignored_connectors_refuse_before_browser_access(self):
        invalid=[mixed(connectors=value) for value in (None,False,'and,or',[],['and'],
            ['and','or','and'],['AND','or'],['xor','or'],['and',{}],['and','and'])]
        absent=mixed();absent.pop('connectors');invalid.append(absent)
        invalid.extend((mixed(match='all'),mixed(match='any'),
                        mixed(clauses=mixed()['clauses'][:2])))
        for value in invalid:
            page=Mock()
            with self.subTest(value=value),self.assertRaises(runner.Stop):group.configure(page,value)
            self.assertFalse(page.mock_calls)
            with self.assertRaises(runner.Stop):stack.validate({'rules':[value]})
            with self.assertRaises(runner.Stop):outcomes.validate({'rules':[value]})

    def test_legacy_hashes_are_unchanged_and_mixed_hash_binds_edge_positions(self):
        legacy=mixed(match='all');legacy.pop('connectors')
        payload={key:legacy[key] for key in ('clauses','match','effect','target')}
        expected=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(group.configuration_hash(legacy),expected)
        first=mixed();second=mixed(connectors=['or','and'])
        reordered=mixed();reordered['clauses'].reverse()
        self.assertEqual(len({group.configuration_hash(x) for x in (first,second,reordered)}),3)
        for leaf in (stack,outcomes):
            self.assertNotEqual(leaf.configuration_hash({'rules':[first]}),
                                leaf.configuration_hash({'rules':[second]}))
            with self.assertRaises(runner.Stop):leaf.validate({'rules':[first,first]})
            self.assertEqual(len(leaf.validate({'rules':[first,second]})['rules']),2)


class NativeModal:
    """Captured per-row tab behavior, independent of the handler's expected rows."""
    def __init__(self):
        self.rows=[{}];self.edges=[];self.clicked=[];self.cards=[];self.effect='';self.target='';self.editing=None
        self.modal,self.frame,self.dialog,self.save,self.tile=[Mock() for _ in range(5)]
        for node in (self.modal,self.save,self.tile):node.count.return_value=1
        self.save.is_enabled.return_value=True
        self.save.is_visible.return_value=True
        self.dialog.get_by_text.return_value=self.tile
        self.frame.get_by_role.return_value=self.modal
        self.modal.locator.side_effect=self.locator
        self.dialog.locator.side_effect=self.drawer_locator

    def selection(self,value):
        node=Mock();node.count.return_value=1;node.native_value=value;return node

    def counted(self,callback):
        node=Mock();node.count.side_effect=callback;return node

    def locator(self,selector):
        if selector in ('[id^="selectedField-"]','[id^="selectedOperation-"]'):
            return self.counted(lambda:len(self.rows))
        if selector=='.n-tabs':
            node=self.counted(lambda:len(self.rows));node.nth.side_effect=self.tab;return node
        if selector=='#modal-footer-btn-positive-action':return self.save
        if selector=='#showHideFieldType':return self.selection(self.effect)
        if selector=='#selectedFieldShowHide':return self.selection(self.target)
        for prefix,key in (('#selectedField-','if_field'),('#selectedOperation-','operator')):
            if selector.startswith(prefix):return self.selection(self.rows[int(selector[len(prefix):])].get(key))
        if selector.startswith('#inputValue-'):
            row=self.rows[int(selector[len('#inputValue-'):])]
            node=self.counted(lambda:int(row.get('operator') in group.BINARY))
            node.input_value.side_effect=lambda:row.get('value','');node.row=row;return node
        raise AssertionError('Unexpected modal selector '+selector)

    def tab(self,index):
        node=Mock()
        def locate(selector):
            item=Mock();item.count.return_value=1
            if selector=='.n-tabs-tab--active':
                item.get_attribute.side_effect=lambda key:self.edges[index] if index<len(self.edges) else 'then'
            elif selector in ('[data-name="and"]','[data-name="or"]'):
                item.edge=(index,selector.split('"')[1])
            else:raise AssertionError(selector)
            return item
        node.locator.side_effect=locate;return node

    def drawer_locator(self,selector):
        if selector==group.CARD:
            node=self.counted(lambda:len(self.cards))
            def card(index):
                item,edit=Mock(),Mock();edit.count.return_value=1;edit.editing_index=index
                item.locator.side_effect=lambda selector:edit if selector=='#edit-condition' else self.locator(selector)
                return item
            node.nth.side_effect=card;return node
        if selector=='.condition-summary-row':return self.counted(lambda:sum(len(x['rows']) for x in self.cards))
        raise AssertionError(selector)

    def choose(self,frame,selector,value):
        if selector=='#showHideFieldType':self.effect=value;return
        if selector=='#selectedFieldShowHide':self.target=value;return
        prefix,key=('#selectedField-','if_field') if selector.startswith('#selectedField-') else ('#selectedOperation-','operator')
        self.rows[int(selector[len(prefix):])][key]=value

    def click(self,node):
        if node is self.tile:return
        if node is self.save:
            rows=[]
            for index,row in enumerate(self.rows):
                tokens=['If' if index==0 else self.edges[index-1].title(),row['if_field'],row['operator']]
                if 'value' in row:tokens.append(row['value'])
                rows.append(tokens)
            saved={'effect':self.effect,'rows':rows,'outcome':[self.effect,self.target]}
            if self.editing is None:self.cards.append(saved)
            else:self.cards[self.editing]=saved
            self.save.is_visible.return_value=False;return
        index=getattr(node,'editing_index',None)
        if type(index) is int:self.editing=index;return
        edge=getattr(node,'edge',None)
        if isinstance(edge,tuple):
            index,value=edge;self.clicked.append(edge)
            if index==len(self.edges):self.edges.append(value);self.rows.append({})
            else:self.edges[index]=value
            return
        raise AssertionError('Unexpected native click')


class MixedNativeTests(unittest.TestCase):
    def test_real_stack_author_clicks_each_exact_connector_and_reads_full_modal(self):
        state=NativeModal();rule=mixed()
        with patch.object(stack,'click',side_effect=state.click), \
             patch.object(group,'_choose',side_effect=state.choose), \
             patch.object(group,'_selected',side_effect=lambda node:node.native_value), \
             patch.object(stack,'fill',side_effect=lambda node,value:node.row.update(value=value)), \
             patch.object(group,'_inventory',side_effect=lambda _:deepcopy(state.cards)), \
             patch.object(stack,'wait_until',side_effect=lambda fn,message:self.assertTrue(fn(),message)):
            result=stack._author(state.frame,state.dialog,rule,[],lambda:None)
            self.assertEqual(state.clicked,[(0,'and'),(1,'or')])
            self.assertEqual([row[0] for row in result[0]['rows']],['If','And','Or'])
            group._modal_state(state.modal,rule)
            state.edges[1]='and'
            with self.assertRaisesRegex(runner.Stop,'AND/OR connector'):group._modal_state(state.modal,rule)

    def test_edit_changes_existing_connector_tabs_without_appending_predicates(self):
        before=mixed();desired=mixed(connectors=['or','and'])
        state=NativeModal();state.rows=deepcopy(before['clauses']);state.edges=['and','or']
        state.effect='Hide Field';state.target='Last Name'
        state.cards=[{'effect':'Hide Field','rows':[
            ['If','Email','Contains','@'],['And','First Name','Is Filled'],['Or','Website','Is Empty']],
            'outcome':['Hide Field','Last Name']}]
        with patch.object(stack,'click',side_effect=state.click), \
             patch.object(group,'_choose',side_effect=state.choose), \
             patch.object(group,'_selected',side_effect=lambda node:node.native_value), \
             patch.object(stack,'fill',side_effect=lambda node,value:node.row.update(value=value)), \
             patch.object(group,'_inventory',side_effect=lambda _:deepcopy(state.cards)), \
             patch.object(stack,'wait_until',side_effect=lambda fn,message:self.assertTrue(fn(),message)):
            result=stack._edit(state.frame,state.dialog,0,before,desired,deepcopy(state.cards),lambda:None)
        self.assertEqual(state.clicked,[(0,'or'),(1,'and')])
        self.assertEqual(len(state.rows),3)
        self.assertEqual([row[0] for row in result[0]['rows']],['If','Or','And'])

    def test_outcome_reader_preserves_mixed_edges_instead_of_silently_flattening(self):
        card,rows=Mock(),Mock();card.locator.return_value=rows
        tokens=[['If','Email','Contains','@'],['And','First Name','Is Filled'],['Or','Website','Is Empty']]
        nodes=[]
        for value in tokens:
            node=Mock();node.locator.return_value.evaluate_all.return_value=value;nodes.append(node)
        rows.count.return_value=3;rows.nth.side_effect=nodes.__getitem__
        self.assertEqual(outcomes._predicate(card),{key:mixed()[key] for key in ('match','connectors','clauses')})

    def test_saved_mixed_rule_requires_exact_connectors_after_independent_reopen(self):
        rule=mixed();data={'rules':[rule]};wanted=stack._expected(data)
        for drift in (False,True):
            page,frame,title,save,dialog,button,close=[Mock() for _ in range(7)]
            page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
            for node in (title,save,dialog,close):node.count.return_value=1
            title.input_value.return_value='Fixture';save.is_enabled.return_value=True
            frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else dialog if role=='dialog' else save if kw.get('name')=='Save' else button
            dialog.locator.return_value=close
            state={'cards':[]};saved=[];events=[]
            def author(_frame,_dialog,authored,prefix,identity):
                identity();self.assertEqual(authored['connectors'],['and','or'])
                state['cards']=deepcopy(wanted);return deepcopy(wanted)
            def click(node):
                nonlocal saved
                if node is save:saved=deepcopy(state['cards']);events.append('save')
            def reopen(*_):
                events.append('reopen');state['cards']=deepcopy(saved)
                if drift:state['cards'][0]['rows'][2][0]='And'
            with patch.object(stack,'form_builder',return_value=frame),patch.object(stack,'_close_initial'), \
                 patch.object(stack,'click',side_effect=click),patch.object(group,'_inventory',side_effect=lambda _:deepcopy(state['cards'])), \
                 patch.object(stack,'_author',side_effect=author),patch.object(stack,'reopen_editor',side_effect=reopen), \
                 patch.object(group,'_wait_for_form_save'):
                if drift:
                    with self.assertRaisesRegex(runner.Stop,'did not persist'):stack.configure(page,data)
                else:
                    result=stack.configure(page,data)
                    self.assertEqual(result['configuration_sha256'],stack.configuration_hash(data))
                    self.assertEqual(result['independent_readback'],'VERIFIED')
            self.assertEqual(events,['save','reopen'])


class MixedCompilerReplayTests(unittest.TestCase):
    def job(self,condition):
        data={'location_id':'LOC','location_name':'Fixture Account',
            'start_url':'https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM','condition':condition}
        return runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))

    def test_all_existing_front_doors_retain_the_ordered_connector_data(self):
        for condition,action in ((mixed(),'native_condition_group'),
                ({'rules':[mixed()]},'native_condition_stack'),
                ({'rules':[dict(match='mixed',connectors=['and','or'],clauses=mixed()['clauses'],
                    effect='Redirect to URL',redirect_url='https://example.com/approved')]},'native_condition_outcomes')):
            with self.subTest(action=action):
                step=self.job(condition)['steps'][0];self.assertEqual(step['action'],action)
                self.assertEqual((step if 'clauses' in step else step['rules'][0])['connectors'],['and','or'])

    def test_group_runtime_replays_once_and_rejects_receipt_after_connector_intent_change(self):
        from playwright_recipes import form_conditions as native
        job=self.job(mixed());step=job['steps'][0]
        result={'status':'CONDITION_GROUP_SAVED_AND_REOPENED','kind':'form_condition_group',
            'editor_url':job['start_url'],'configuration_sha256':native.configuration_hash(step),
            'clause_count':3,'independent_readback':'VERIFIED','submission_verified':False,'behavior_verified':False}
        with tempfile.TemporaryDirectory() as root,patch.object(runner,'assert_tenant'), \
             patch.object(native,'configure',return_value=result) as writer:
            first=runner.run_on_page(object(),job,root);replay=runner.run_on_page(object(),job,root)
        self.assertEqual(first['status'],'NEEDS_VERIFICATION')
        self.assertEqual(replay['status'],'NEEDS_VERIFICATION');self.assertTrue(replay['replayed'])
        writer.assert_called_once()
        changed=deepcopy(step);changed['connectors'].reverse()
        with self.assertRaises(runner.Stop):editor_replay._result(changed,result,job)


if __name__=='__main__':unittest.main()
