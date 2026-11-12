"""Survey compound outcomes stay bound to full survey owners and rich readback."""
from copy import deepcopy
import hashlib
import importlib
import unittest
from unittest.mock import MagicMock,patch

from skill6_playwright import Stop
native=importlib.import_module('playwright_recipes.survey_condition_outcomes')


def step():
    return {'action':native.ACTION,'payload':{'location_id':'LOC','location_name':'Fixture Account',
        'start_url':'https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY',
        'expected_survey_name':'Approved survey','expected_slide_count':2,
        'slide_labels':['P1 - Contact','P2 - Agreement'],
        'outcomes':{'rules':[{'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'},
            {'if_field':'First Name','operator':'Contains','value':'Trevor'}],
            'effect':'Display custom message','message':'Thanks for applying.'}]}}}


def receipt(spec):
    plan=native.validate(spec)
    return {'status':'CONDITION_OUTCOMES_SAVED_AND_REOPENED','kind':'survey_condition_outcomes',
        'editor_url':plan['start_url'],'rule_count':1,'configuration_sha256':native.configuration_hash(spec),
        'outcomes_sha256':native.shared.configuration_hash(native._step(plan)),
        'saved_rules':[{'rule':deepcopy(plan['outcomes']['rules'][0]),
                        'rich_html_sha256':hashlib.sha256(b'<p>Thanks for applying.</p>').hexdigest()}],
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False,
        'disqualification_executed':False}


class SurveyConditionOutcomes(unittest.TestCase):
    def test_full_owner_schema_and_mixed_predicates_validate(self):
        spec=step();plan=native.validate(spec)
        self.assertEqual(plan['outcomes']['rules'][0]['clauses'][1]['value'],'Trevor')
        for mutation in ('url','slides','override','effect'):
            bad=step()
            if mutation=='url':bad['payload']['start_url']=bad['payload']['start_url'].replace('/LOC/','/FOREIGN/')
            elif mutation=='slides':bad['payload']['slide_labels'].reverse()
            elif mutation=='override':bad['payload']['outcomes']['action']='native_condition_outcomes'
            else:bad['payload']['outcomes']['rules'][0]['effect']='Jump To'
            with self.subTest(mutation=mutation),self.assertRaises(Stop):native.validate(bad)
    def test_formatted_message_is_forwarded_to_shared_survey_writer(self):
        spec=step();outcomes=spec['payload']['outcomes']
        outcomes['rules'][0]['message']='One\nTwo'
        outcomes['message_markup']=['<p><strong>One</strong></p><p><strong>Two</strong></p>']
        plan=native.validate(spec)
        self.assertEqual(native._step(plan)['message_markup'],outcomes['message_markup'])
        changed=deepcopy(spec);changed['payload']['outcomes'].pop('message_markup')
        self.assertNotEqual(native.configuration_hash(spec),native.configuration_hash(changed))


    def test_existing_forward_jump_card_is_only_preserved_at_its_original_ordinal(self):
        jump={'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'}],
            'effect':'Jump To','target_slide':'P2 - Agreement'}
        spec=step();spec['payload']['outcomes'].update(expected_rules=[deepcopy(jump)],rules=[deepcopy(jump)])
        self.assertEqual(native.validate(spec)['outcomes']['rules'],[jump])
        bad=deepcopy(spec);bad['payload']['outcomes']['rules']=[]
        with self.assertRaisesRegex(Stop,'Jump To cards'):native.validate(bad)
        bad=deepcopy(spec);bad['payload']['outcomes']['rules'][0]['target_slide']='P1 - Contact'
        with self.assertRaisesRegex(Stop,'Jump To cards'):native.validate(bad)
        bad=deepcopy(spec);bad['payload']['outcomes']['rules'][0]['target_slide']='P3 - Missing'
        bad['payload']['outcomes']['expected_rules'][0]['target_slide']='P3 - Missing'
        with self.assertRaisesRegex(Stop,'exact captured slide'):native.validate(bad)

    def test_jump_ordinal_survives_compound_show_hide_message_stack_edits(self):
        hide={'match':'all','clauses':[{'if_field':'Phone','operator':'Is Filled'}],
            'effect':'Hide Field','target':'Phone'}
        jump={'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'}],
            'effect':'Jump To','target_slide':'P2 - Agreement'}
        message={'match':'all','clauses':[{'if_field':'First Name','operator':'Contains','value':'Trevor'},
            {'if_field':'Email','operator':'Is Filled'}], 'effect':'Display custom message','message':'Thank you.'}
        spec=step();spec['payload']['outcomes'].update(expected_rules=[hide,jump,message],
            rules=[{**hide,'clauses':[{'if_field':'Phone','operator':'Is Empty'}]},jump,message])
        plan=native.validate(spec)
        self.assertEqual(plan['outcomes']['expected_rules'][1],jump)
        self.assertEqual(plan['outcomes']['rules'][1],jump)
        bad=deepcopy(spec);bad['payload']['outcomes']['rules']=[hide,message]
        with self.assertRaisesRegex(Stop,'Jump To cards'):native.validate(bad)

    def test_existing_jump_allows_only_new_known_tail_outcomes(self):
        jump={'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'}],
              'effect':'Jump To','target_slide':'P2 - Agreement'}
        message=deepcopy(step()['payload']['outcomes']['rules'][0])
        spec=step();spec['payload']['outcomes'].update(expected_rules=[jump],rules=[jump,message])
        plan=native.validate(spec)['outcomes']
        self.assertEqual(native.shared._reconciliation(plan['expected_rules'],plan['rules']),('mapped',[0,None]))
        for wanted in ([message,jump],[message], [jump,{**jump,'target_slide':'P1 - Contact'}]):
            bad=deepcopy(spec);bad['payload']['outcomes']['rules']=wanted
            with self.subTest(wanted=wanted),self.assertRaises(Stop):native.validate(bad)
        changed=deepcopy(spec);changed['payload']['outcomes']['expected_rules']=[jump,message]
        changed['payload']['outcomes']['rules']=[jump]
        with self.assertRaises(Stop):
            native.shared.configure(MagicMock(),native._step(native.validate(changed)),surface='survey',inventory_override=lambda *a,**k:[])

    def test_survey_reader_normalizes_multiline_text_and_keeps_raw_rich_hash(self):
        rich='<p><strong>One</strong></p><p>Two</p>'
        for effect in ('Display custom message','Disqualify lead'):
            card=MagicMock();heading=MagicMock();heading.count.return_value=1;heading.inner_text.return_value=effect
            mode=MagicMock();mode.inner_text.return_value='SHOW'
            body=MagicMock();body.inner_text.return_value='One\n\nTwo';body.inner_html.return_value=rich
            spans=MagicMock();spans.count.return_value=2;spans.nth.side_effect=lambda index:(mode,body)[index]
            outcome=MagicMock();outcome.count.return_value=1;outcome.locator.return_value=spans
            actions=MagicMock();actions.count.return_value=1
            card.locator.side_effect=lambda selector:{'.text-sm.font-semibold':heading,native.shared.group.OUTCOME:outcome,
                '#edit-condition':actions,'#delete-condition':actions}[selector]
            cards=MagicMock();cards.count.return_value=1;cards.nth.return_value=card
            dialog=MagicMock();dialog.locator.return_value=cards;dialog.get_by_text.return_value.count.return_value=0
            with self.subTest(effect=effect),patch.object(native.shared,'_predicate',return_value={
                    'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'}]}):
                record=native._inventory(dialog)[0]
                self.assertEqual(record['rule']['message'],'One\nTwo')
                self.assertEqual(record['rich_html_sha256'],hashlib.sha256(rich.encode()).hexdigest())

    def test_survey_reader_preserves_jump_card_in_full_mixed_stack_order(self):
        def card(effect,mode,value):
            record=MagicMock();heading=MagicMock();heading.count.return_value=1;heading.inner_text.return_value=effect
            spans=MagicMock();spans.count.return_value=2
            first=MagicMock();first.inner_text.return_value=mode
            second=MagicMock();second.inner_text.return_value=value;second.inner_html.return_value='<p>answer</p>'
            spans.nth.side_effect=lambda index:(first,second)[index]
            outcome=MagicMock();outcome.count.return_value=1;outcome.locator.return_value=spans
            actions=MagicMock();actions.count.return_value=1
            record.locator.side_effect=lambda selector: {
                '.text-sm.font-semibold':heading,native.shared.group.OUTCOME:outcome,
                '#edit-condition':actions,'#delete-condition':actions}[selector]
            return record
        jump=card('Jump To Slide','JUMP TO','P2 - Agreement')
        hide=card('Hide Field','Hide Field','Number 27bpe')
        message=card('Display custom message','SHOW','answer')
        cards=MagicMock();cards.count.return_value=3;cards.nth.side_effect=lambda index:(jump,hide,message)[index]
        dialog=MagicMock();dialog.locator.return_value=cards;dialog.get_by_text.return_value.count.return_value=0
        predicates=[{'match':'all','clauses':[{'if_field':'Email','operator':'Is Filled'}]},
                    {'match':'all','clauses':[{'if_field':'Age','operator':'Is Filled'}]},
                    {'match':'all','clauses':[{'if_field':'First Name','operator':'Is Filled'}]}]
        with patch.object(native.shared,'_predicate',side_effect=predicates),patch.object(native.shared,'_rule',side_effect=lambda rule,**kwargs:rule):
            rows=native._inventory(dialog,slide_labels=['P1 - Contact','P2 - Agreement'])
        self.assertEqual([row['rule']['effect'] for row in rows],['Jump To','Hide Field','Display custom message'])
        self.assertEqual(rows[0]['rule']['target_slide'],'P2 - Agreement')
        self.assertIsNone(rows[0]['rich_html_sha256'])
        self.assertEqual(rows[2]['rich_html_sha256'],hashlib.sha256(b'<p>answer</p>').hexdigest())
    def test_receipt_rejects_owner_rule_rich_hash_and_behavior_overclaims(self):
        spec=step();done=receipt(spec);self.assertEqual(native.validate_receipt(done,spec),done)
        for mutation in ('owner','rule','rich','execution'):
            bad=deepcopy(done)
            if mutation=='owner':bad['editor_url']+='OTHER'
            elif mutation=='rule':bad['saved_rules'][0]['rule']['message']='Changed'
            elif mutation=='rich':bad['saved_rules'][0]['rich_html_sha256']=None
            else:bad['disqualification_executed']=True
            with self.subTest(mutation=mutation),self.assertRaises(Stop):native.validate_receipt(bad,spec)
    def test_configure_binds_survey_owner_and_calls_only_survey_surface(self):
        spec=step();done=receipt(spec);shared=deepcopy(done)
        shared.pop('outcomes_sha256');shared['configuration_sha256']=done['outcomes_sha256']
        page=MagicMock()
        with patch.object(native.survey,'_frame') as owner,patch.object(native.shared,'configure',return_value=shared) as writer:
            self.assertEqual(native.configure(page,spec),done)
        self.assertEqual(owner.call_count,2)
        owner.assert_called_with(page,native.validate(spec))
        writer.assert_called_once()
        self.assertEqual(writer.call_args.args,(page,native._step(native.validate(spec))))
        self.assertEqual(writer.call_args.kwargs['surface'],'survey')
        self.assertTrue(callable(writer.call_args.kwargs['inventory_override']))
    def test_completed_replay_reads_full_saved_rule_hashes_without_reauthoring(self):
        spec=step();done=receipt(spec);frame=MagicMock();dialog=frame.get_by_role.return_value
        for node in (dialog,dialog.locator.return_value):node.count.return_value=1
        with patch.object(native,'reopen_editor') as reopen,patch.object(native.survey,'_frame',return_value=frame),patch.object(native,'_inventory',return_value=done['saved_rules']),patch.object(native.shared,'configure') as writer:
            self.assertEqual(native.verify_completed(MagicMock(),spec,done),done)
        reopen.assert_called_once();writer.assert_not_called()
    def test_completed_drift_stops_before_close_or_any_rewrite(self):
        spec=step();done=receipt(spec);frame=MagicMock();dialog=frame.get_by_role.return_value
        dialog.count.return_value=1
        with patch.object(native,'reopen_editor'),patch.object(native.survey,'_frame',return_value=frame),patch.object(native,'_inventory',return_value=[]),patch.object(native.shared,'configure') as writer,self.assertRaisesRegex(Stop,'drifted'):
            native.verify_completed(MagicMock(),spec,done)
        writer.assert_not_called();dialog.locator.assert_not_called()

    def test_disqualify_timing_rejects_unrecorded_before_submit(self):
        modal=MagicMock();timing=modal.locator.return_value
        timing.count.return_value=1
        timing.get_attribute.return_value='Disqualify After Submit'
        timing.locator.return_value.count.return_value=1
        timing.locator.return_value.inner_text.return_value='Disqualify After Submit'
        native.shared._disqualify_timing(modal)
        timing.get_attribute.return_value='Disqualify Before Submit'
        timing.locator.return_value.inner_text.return_value='Disqualify Before Submit'
        with self.assertRaisesRegex(Stop,'After Submit'):native.shared._disqualify_timing(modal)

    def test_saved_disqualify_timing_reads_modal_and_returns_without_rule_save(self):
        spec=step();spec['payload']['outcomes']['rules'][0].update(effect='Disqualify lead',mode='Show custom message')
        plan=native.validate(spec)
        records=[{'rule':plan['outcomes']['rules'][0],'rich_html_sha256':'a'*64}]
        frame=MagicMock();dialog=frame.get_by_role.return_value
        dialog.count.return_value=1;dialog.locator.return_value.count.return_value=1
        dialog.locator.return_value.nth.return_value.locator.return_value.count.return_value=1
        with patch.object(native,'_frame',return_value=frame),patch.object(native,'_inventory',return_value=records),patch.object(native.shared,'_disqualify_timing') as timing,patch.object(native.shared,'configure') as writer:
            native._verify_saved_timing(MagicMock(),plan)
        timing.assert_called_once();writer.assert_not_called()
        requested=[call.args[0] for call in dialog.locator.call_args_list]
        self.assertIn('.hl-modal-heading svg.h-6.w-6.cursor-pointer',requested)
        self.assertNotIn('#modal-footer-btn-positive-action',requested)

if __name__=='__main__':unittest.main()
