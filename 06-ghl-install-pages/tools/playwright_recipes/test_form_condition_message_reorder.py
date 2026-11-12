"""Message order changes must retain exact saved markup or stop before Save."""
from copy import deepcopy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import form_condition_outcomes as native
import recipe_cli
import skill6_playwright as runner
from test_form_condition_outcomes import rule, record


class MessageRecreationTests(unittest.TestCase):
    def exercise(self, *, formatted=False, unchanged_prefix=False, changed_after_author=False,
                 already=False, stale=False):
        message=rule(native.MESSAGE)
        disqualify=rule(native.DISQUALIFY)
        values=[rule(),message,disqualify] if unchanged_prefix else [message,disqualify,rule()]
        order=[0,2,1] if unchanged_prefix else [2,0,1]
        plan=native.validate({'expected_rules':values,'rules':[values[i] for i in order],
                              'recreate_order':order})
        records=[record(value,('<p>'+value['message']+'</p>') if 'message' in value else None)
                 for value in values]
        if formatted:
            index=0 if unchanged_prefix else 1
            if unchanged_prefix:
                values=[message,rule(),disqualify]
                order=[0,2,1]
                plan=native.validate({'expected_rules':values,'rules':[values[i] for i in order],
                                      'recreate_order':order})
                records=[record(value,('<p>'+value['message']+'</p>') if 'message' in value else None)
                         for value in values]
            value=records[index]['rule']['message']
            markup='<p><strong>'+value+'</strong></p>'
            records[index]['rich_html_sha256']=hashlib.sha256(markup.encode()).hexdigest()
        desired=[records[i] for i in order]
        current=deepcopy(desired if already else records)
        if stale:current[-1]['rule']['redirect_url']='https://example.com/stale'
        events=[]
        def inventory(_):return deepcopy(current)
        def delete(_frame,_dialog,previous,_identity,*,index,inventory):
            nonlocal current
            self.assertEqual(previous,current)
            events.append(('delete',index));current.pop(index)
            return deepcopy(current)
        def author(_frame,_dialog,value,previous,_identity,*,inventory,message_markup=None):
            nonlocal current
            self.assertEqual(previous,current)
            events.append(('author',value['effect']))
            if message_markup is not None:self.assertEqual(message_markup,markup)
            original=next(item for item in records if item['rule']==value)
            created=deepcopy(original)
            if changed_after_author and 'message' in value:
                created['rich_html_sha256']='f'*64
            current.append(created)
            return deepcopy(current)
        dialog=Mock()
        if formatted and not unchanged_prefix:
            card=dialog.locator.return_value.nth.return_value
            card.count.return_value=1
            card.locator.return_value.count.return_value=1
            body=card.locator.return_value.locator.return_value
            body.count.return_value=2;body.nth.return_value.inner_html.return_value=markup
        with patch.object(native.stack,'_delete_card',side_effect=delete), \
             patch.object(native,'_author',side_effect=author):
            try:
                result=native._recreate_order(Mock(),dialog,plan,deepcopy(current),lambda:None,inventory)
            except runner.Stop as error:result=error
        return result,events,desired

    def test_reorders_message_and_disqualification_with_exact_original_markup(self):
        result,events,desired=self.exercise()
        self.assertEqual(result,desired)
        self.assertEqual(events,[('delete',2),('delete',1),('delete',0),
            ('author',native.REDIRECT),('author',native.MESSAGE),('author',native.DISQUALIFY)])

    def test_formatted_suffix_is_recreated_with_original_markup(self):
        result,events,desired=self.exercise(formatted=True)
        self.assertEqual(result,desired)
        self.assertEqual(events,[('delete',2),('delete',1),('delete',0),
            ('author',native.REDIRECT),('author',native.MESSAGE),('author',native.DISQUALIFY)])

    def test_untouched_formatted_prefix_is_preserved_without_reauthoring(self):
        result,events,desired=self.exercise(formatted=True,unchanged_prefix=True)
        self.assertEqual(result,desired)
        self.assertEqual(events,[('delete',2),('delete',1),
            ('author',native.DISQUALIFY),('author',native.REDIRECT)])

    def test_native_reauthor_markup_drift_stops_before_outer_save(self):
        result,events,_=self.exercise(changed_after_author=True)
        self.assertIsInstance(result,runner.Stop)
        self.assertIn('outer Save not attempted',str(result))
        self.assertEqual(events[-1],('author',native.MESSAGE))
        self.assertNotIn(('author',native.DISQUALIFY),events)

    def test_already_reordered_stack_is_read_only_and_stale_stack_never_deletes(self):
        result,events,desired=self.exercise(already=True)
        self.assertEqual(result,desired);self.assertEqual(events,[])
        result,events,_=self.exercise(stale=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(events,[])

    def test_card_comparison_allows_only_empty_paragraph_style_and_checks_raw_hash(self):
        dialog=Mock()
        card=dialog.locator.return_value.nth.return_value
        card.count.return_value=1
        outcome=card.locator.return_value;outcome.count.return_value=1
        spans=outcome.locator.return_value;spans.count.return_value=2
        actual='<p><strong>One</strong></p><p><strong>Two</strong></p>'
        spans.nth.return_value.inner_html.return_value=actual
        saved={'rich_html_sha256':hashlib.sha256(actual.encode()).hexdigest()}
        requested='<p style=""><strong>One</strong></p><p style=""><strong>Two</strong></p>'
        self.assertTrue(native._matches_message_markup(dialog,0,saved,requested))
        self.assertFalse(native._matches_message_markup(dialog,0,{'rich_html_sha256':'0'*64},requested))
        self.assertFalse(native._matches_message_markup(dialog,0,saved,'<p>One</p><p>Two</p>'))

    def test_plain_message_permutation_passes_existing_compiler_without_new_wiring(self):
        values=[rule(native.MESSAGE),rule()]
        condition={'expected_rules':values,'rules':values[::-1],'recreate_order':[1,0]}
        data={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
            'condition':condition}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'native_condition_outcomes')
        self.assertEqual(job['steps'][0]['recreate_order'],[1,0])


if __name__=='__main__':unittest.main()
