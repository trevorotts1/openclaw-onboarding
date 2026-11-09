"""Native outcome stacks preserve complete ordered predicates and rich cards."""
from copy import deepcopy
import hashlib
from unittest.mock import Mock,patch
import unittest

import form_condition_outcomes as native
from skill6_playwright import Stop


def rule(effect=native.REDIRECT,**values):
    result={'match':'all','clauses':[{'if_field':'First Name','operator':'Is Empty'}],'effect':effect}
    if effect==native.REDIRECT:result['redirect_url']='https://example.com/approved'
    elif effect==native.MESSAGE:result['message']='Approved message'
    elif effect==native.DISQUALIFY:result.update(mode=native.SHOW_MESSAGE,message='Approved disqualification')
    else:result['target']='Phone'
    result.update(values)
    return result


def record(value,markup=None):
    return {'rule':native._rule(value),'rich_html_sha256':hashlib.sha256(markup.encode()).hexdigest() if markup is not None else None}


class SchemaTests(unittest.TestCase):
    def test_all_captured_effects_share_exact_single_or_homogeneous_compound_predicates(self):
        values=[rule('Show Field'),rule(native.REDIRECT),rule(native.MESSAGE),rule(native.DISQUALIFY)]
        result=native.validate({'rules':values})
        self.assertEqual([value['effect'] for value in result['rules']],
                         ['Show Field',native.REDIRECT,native.MESSAGE,native.DISQUALIFY])
        compound=rule(native.DISQUALIFY,match='any',clauses=[
            {'if_field':'Email','operator':'Contains','value':'@example.com'},
            {'if_field':'First Name','operator':'Is Filled'}])
        self.assertEqual(native.validate({'rules':[compound]})['rules'],[compound])

    def test_single_any_and_all_normalize_to_the_same_native_predicate(self):
        first={'rules':[rule()]};second={'rules':[rule(match='any')]}
        self.assertEqual(native.configuration_hash(first),native.configuration_hash(second))

    def test_duplicate_effect_predicates_or_field_conflicts_are_refused(self):
        invalid=[{'rules':[rule(),rule(redirect_url='https://example.com/other')]},
                 {'rules':[rule('Hide Field'),rule('Show Field')]}]
        for value in invalid:
            with self.subTest(value=value),self.assertRaisesRegex(Stop,'Duplicate/conflicting'):
                native.validate(value)

    def test_explicit_disqualification_modes_never_drop_unrequested_values(self):
        value=rule(native.DISQUALIFY,mode=native.REDIRECT,redirect_url='https://example.com/no')
        value.pop('message')
        self.assertEqual(native.validate({'rules':[value]})['rules'],[value])
        invalid=[rule(native.DISQUALIFY,mode='unknown'),
            rule(native.DISQUALIFY,redirect_url='https://example.com/ignored'),
            rule(native.MESSAGE,redirect_url='https://example.com/ignored'),
            rule(message='ignored'),rule(native.MESSAGE,message=''),
            rule(redirect_url='http://example.com'),rule(redirect_url='https://user:secret@example.com'),
            rule(native.MESSAGE,publish=True)]
        for value in invalid:
            page=Mock()
            with self.subTest(value=value),self.assertRaises(Stop):
                native.configure(page,{'rules':[value]})
            self.assertFalse(page.mock_calls)

    def test_order_plain_copy_mode_and_url_are_all_hash_bound(self):
        base={'rules':[rule(),rule(native.MESSAGE)]}
        variants=[deepcopy(base) for _ in range(3)]
        variants[0]['rules'].reverse()
        variants[1]['rules'][0]['redirect_url']='https://example.com/changed'
        variants[2]['rules'][1]['message']='Different'
        self.assertEqual(len({native.configuration_hash(x) for x in [base,*variants]}),4)


class InventoryTests(unittest.TestCase):
    def surface(self,values):
        dialog,cards,empty=Mock(),Mock(),Mock()
        cards.count.return_value=len(values);empty.count.return_value=int(not values)
        dialog.locator.return_value=cards;dialog.get_by_text.return_value=empty
        nodes=[]
        for value,html in values:
            card,heading,rows,row,outcome,spans,mode,body=[Mock() for _ in range(8)]
            actions=Mock();actions.count.return_value=1
            heading.count.return_value=outcome.count.return_value=1
            heading.inner_text.return_value=value['effect']
            rows.count.return_value=len(value['clauses']);row_nodes=[]
            for index,clause in enumerate(value['clauses']):
                item=Mock();tokens=['If' if index==0 else 'And' if value['match']=='all' else 'Or',
                                   clause['if_field'],clause['operator']]
                if 'value' in clause:tokens.append(clause['value'])
                item.locator.return_value.evaluate_all.return_value=tokens;row_nodes.append(item)
            rows.nth.side_effect=row_nodes.__getitem__
            spans.count.return_value=2;spans.nth.side_effect=[mode,body].__getitem__
            outcome.locator.side_effect=lambda selector,node=spans:node if selector==':scope > span' else None
            if value['effect'] in ('Show Field','Hide Field'):
                label=value['effect'];text=value['target']
            elif 'redirect_url' in value:label=native.REDIRECT;text=value['redirect_url']
            else:label='SHOW';text=value['message']
            mode.inner_text.return_value=label+' \u00a0 '
            body.inner_text.return_value=text;body.inner_html.return_value=html
            selectors={'#edit-condition':actions,'#delete-condition':actions,
                '.text-sm.font-semibold':heading,'.condition-summary-row':rows,native.group.OUTCOME:outcome}
            card.locator.side_effect=selectors.__getitem__;nodes.append(card)
        cards.nth.side_effect=nodes.__getitem__
        return dialog,empty

    def test_reads_all_mixed_cards_and_hashes_the_actual_rich_html_not_just_plain_copy(self):
        values=[(rule('Show Field'),None),(rule(),None),
            (rule(native.MESSAGE),'<p>Approved <strong>message</strong></p>'),
            (rule(native.DISQUALIFY),'<p>Approved disqualification</p>')]
        dialog,_=self.surface(values)
        actual=native._inventory(dialog)
        self.assertEqual([item['rule'] for item in actual],[native._rule(value) for value,_ in values])
        self.assertEqual(actual[2]['rich_html_sha256'],hashlib.sha256(values[2][1].encode()).hexdigest())
        modified=deepcopy(values);modified[2]=(values[2][0],'<p>Approved message</p>')
        self.assertNotEqual(actual,native._inventory(self.surface(modified)[0]))

    def test_empty_inventory_requires_a_real_empty_marker(self):
        dialog,empty=self.surface([])
        self.assertEqual(native._inventory(dialog),[])
        empty.count.return_value=0
        with self.assertRaisesRegex(Stop,'no inferred'):native._inventory(dialog)

    def test_disqualify_redirect_has_its_own_mode_and_exact_url(self):
        value=rule(native.DISQUALIFY,mode=native.REDIRECT,redirect_url='https://example.com/not-qualified')
        value.pop('message')
        self.assertEqual(native._inventory(self.surface([(value,None)])[0])[0]['rule'],value)


class ModalTests(unittest.TestCase):
    def test_disqualification_dropdown_uses_frame_portal_not_modal_descendants(self):
        modal,frame,selected,option,control,menu=[Mock() for _ in range(6)]
        current={'mode':native.SHOW_MESSAGE,'url':''}
        option.count.return_value=control.count.return_value=1
        control.get_attribute.return_value='https://www.example.com'
        control.input_value.side_effect=lambda:current['url']
        modal.locator.side_effect=lambda selector:control if selector=='#redirectToUrlInput input' else self.fail('Uncaptured modal selector '+selector)
        frame.locator.side_effect=lambda selector:menu if selector=='.n-base-select-option:visible' else self.fail(selector)
        menu.get_by_text.return_value=option
        def click(node):
            if node is option:current['mode']=native.REDIRECT
        def fill(node,value):current['url']=value
        value=rule(native.DISQUALIFY,mode=native.REDIRECT,redirect_url='https://example.com/disqualified')
        value.pop('message')
        with patch.object(native,'_disqualify_mode',side_effect=lambda _:(current['mode'],selected)), \
             patch.object(native,'click',side_effect=click),patch.object(native,'fill',side_effect=fill), \
             patch.object(native,'wait_until',side_effect=lambda fn,message:self.assertTrue(fn(),message)):
            native._effect_value(frame,modal,value,write=True)
        self.assertEqual(current['url'],value['redirect_url'])
        menu.get_by_text.assert_called_once_with(native.REDIRECT,exact=True)

    def test_plain_message_uses_literal_fill_and_rejects_retained_links(self):
        editor,modal=Mock(),Mock();editor.count.return_value=1
        modal.locator.side_effect=lambda selector:editor if selector==native.RTE else self.fail(selector)
        value=rule(native.MESSAGE,message='<b>Literal approved copy</b>')
        state={'text':''};editor.inner_text.side_effect=lambda:state['text']
        editor.locator.return_value.count.return_value=0
        with patch.object(native,'fill',side_effect=lambda node,text:state.update(text=text)) as fill:
            native._effect_value(Mock(),modal,value,write=True)
        fill.assert_called_once_with(editor,value['message'])
        editor.locator.return_value.count.return_value=1
        with self.assertRaises(Stop):native._effect_value(Mock(),modal,value,write=True)

    def test_add_tile_is_scoped_to_heading_even_when_summary_repeats_redirect_label(self):
        value=rule();prefix=[record(rule('Show Field'))];expected=[*prefix,record(value)]
        frame,dialog,heading,tile,modal,modal_heading,save,rows,cards=[Mock() for _ in range(9)]
        for node in (tile,modal,modal_heading,save):node.count.return_value=1
        save.is_enabled.return_value=True
        dialog.get_by_text.side_effect=AssertionError('Global tile text collides with a summary card')
        dialog.get_by_role.side_effect=AssertionError('Use the captured frame heading owner for native tiles')
        heading.get_by_text.return_value=tile
        frame.get_by_role.side_effect=lambda role:heading if role=='heading' else modal if role=='dialog' else self.fail(role)
        modal.locator.side_effect=lambda selector:(rows if selector=='[id^="selectedField-"]' else
            save if selector=='#modal-footer-btn-positive-action' else
            SimpleModalHeading(modal_heading) if selector=='.hl-modal-heading' else self.fail(selector))
        rows.count.return_value=1
        dialog.locator.return_value=cards;cards.count.return_value=2
        with patch.object(native.group,'_choose'),patch.object(native,'_effect_value'), \
             patch.object(native,'_predicate_modal'),patch.object(native,'click'), \
             patch.object(native,'wait_until',side_effect=lambda fn,message:self.assertTrue(fn(),message)), \
             patch.object(native,'_inventory',return_value=expected):
            self.assertEqual(native._author(frame,dialog,value,prefix,lambda:None),expected)
        heading.get_by_text.assert_called_once_with(native.REDIRECT,exact=True)


class SimpleModalHeading:
    def __init__(self,node):self.node=node
    def get_by_text(self,*args,**kwargs):return self.node


class LifecycleTests(unittest.TestCase):
    def exercise(self, *, before=None,lost=False,collateral=False):
        values=[rule(),rule(native.MESSAGE)]
        data={'rules':values};wanted=[record(values[0]),record(values[1],'<p>Approved message</p>')]
        persisted=deepcopy(before or []);staged=deepcopy(persisted)
        page,frame,title,save,dialog,tab,close=[Mock() for _ in range(7)]
        page.url='https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM'
        title.count.return_value=save.count.return_value=dialog.count.return_value=close.count.return_value=1
        title.input_value.return_value='Approved Form';save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else dialog if role=='dialog' else save if kw.get('name')=='Save' else tab
        dialog.locator.return_value=close
        events=[]
        def inventory(_):return deepcopy(staged)
        def author(_frame,_dialog,value,prefix,identity):
            nonlocal staged
            identity();events.append(('append',value['effect']))
            staged=[*deepcopy(prefix),deepcopy(wanted[len(prefix)])]
            if collateral and prefix:staged[0]['rule']['redirect_url']='https://example.com/unapproved'
            return deepcopy(staged)
        def click(node):
            nonlocal persisted
            if node is save:
                events.append(('save',))
                if not lost:persisted=deepcopy(staged)
        def reopen(*args):
            nonlocal staged
            events.append(('reopen',));staged=deepcopy(persisted)
        with patch.object(native,'form_builder',return_value=frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=click),patch.object(native,'_inventory',side_effect=inventory), \
             patch.object(native,'_author',side_effect=author),patch.object(native,'reopen_editor',side_effect=reopen), \
             patch.object(native.group,'_wait_for_form_save'):
            try:result=native.configure(page,data)
            except Stop as error:result=error
        return result,events,persisted,wanted

    def test_append_each_outcome_once_save_and_independently_reopen_all_rich_cards(self):
        result,events,persisted,wanted=self.exercise()
        self.assertEqual(result['status'],'CONDITION_OUTCOMES_SAVED_AND_REOPENED')
        self.assertEqual(persisted,wanted);self.assertEqual(events.count(('save',)),1)
        self.assertFalse(result['behavior_verified']);self.assertFalse(result['submission_verified'])
        self.assertFalse(result['disqualification_executed'])

    def test_replay_rejects_changed_intent_and_executed_disqualification_claims(self):
        result,_,_,_=self.exercise()
        data={'rules':[rule(),rule(native.MESSAGE)]}
        self.assertTrue(native.validate_receipt(result,data))
        for change in ({'configuration_sha256':'0'*64},{'rule_count':True},
                       {'rule_count':3},{'disqualification_executed':True},
                       {'submission_verified':True},{'kind':'form_condition_stack'}):
            with self.subTest(change=change),self.assertRaises(Stop):
                native.validate_receipt({**result,**change},data)

    def test_exact_prefix_appends_only_missing_effect(self):
        result,events,_,_=self.exercise(before=[record(rule())])
        self.assertEqual([event for event in events if event[0]=='append'],[('append',native.MESSAGE)])
        self.assertEqual(result['rule_count'],2)

    def test_complete_saved_stack_is_reused_without_append_or_outer_save(self):
        _,_,_,wanted=self.exercise()
        result,events,_,_=self.exercise(before=wanted)
        self.assertEqual(result['status'],'CONDITION_OUTCOMES_REUSED_AND_REOPENED')
        self.assertFalse(any(event[0] in ('append','save') for event in events))

    def test_unrelated_or_reordered_prefix_stops_before_any_append(self):
        result,events,_,_=self.exercise(before=[record(rule(native.MESSAGE),'<p>Approved message</p>')])
        self.assertIsInstance(result,Stop);self.assertEqual(events,[])

    def test_lost_save_never_promotes_staged_cards_to_persistence(self):
        result,events,persisted,_=self.exercise(lost=True)
        self.assertIsInstance(result,Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(persisted,[]);self.assertEqual(events.count(('save',)),1)

    def test_collateral_prior_effect_change_prevents_outer_save(self):
        result,events,_,_=self.exercise(collateral=True)
        self.assertIsInstance(result,Stop)
        self.assertNotIn(('save',),events)


if __name__=='__main__':unittest.main()
