"""A full expected inventory can grow after guarded edits without dropping cards."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

import form_condition_stack as native
import recipe_cli
import skill6_playwright as runner
from test_form_condition_stack import rule


def plan():
    return {'expected_rules':[rule('Phone')],
        'rules':[rule('Phone',effect='Show Field'),rule('Email')]}


class StackGrowthTests(unittest.TestCase):
    def test_full_expected_before_inventory_and_longer_desired_stack_compile_unchanged(self):
        data=plan();self.assertEqual(native.validate(data),data)
        inputs={'location_id':'LOC','location_name':'Fixture',
            'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM','condition':data}
        job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',inputs),Path('.'))
        self.assertEqual(job['steps'][0]['action'],'native_condition_stack')
        self.assertEqual(job['steps'][0]['expected_rules'],data['expected_rules'])
        self.assertEqual(job['steps'][0]['rules'],data['rules'])

    def test_empty_expected_inventory_is_explicit_and_hash_bound(self):
        data={'expected_rules':[],'rules':[rule()]}
        self.assertEqual(native.validate(data),data)
        self.assertNotEqual(native.configuration_hash(data),native.configuration_hash({'rules':[rule()]}))

    def test_contraction_requires_an_explicit_complete_before_inventory(self):
        data={'expected_rules':[rule('Phone'),rule('Email')],'rules':[rule('Phone')]}
        self.assertEqual(native.validate(data),data)
        with self.assertRaises(runner.Stop):native.validate({'rules':[]})

    def exercise(self,*,drift_before=False,drift_after_edit=False,lost=False,empty=False):
        data={'expected_rules':[],'rules':[rule()]} if empty else plan()
        state={'cards':native._expected({'rules':data['expected_rules']})}
        if drift_before:state['cards'][0]['outcome']=['Hide Field','Last Name']
        saved=deepcopy(state['cards']);events=[]
        page,frame,title,save,dialog,button,close=[Mock() for _ in range(7)]
        page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        for node in (title,save,dialog,close):node.count.return_value=1
        title.input_value.return_value='Fixture';save.is_enabled.return_value=True
        frame.get_by_role.side_effect=lambda role,**kw:title if role=='textbox' else dialog if role=='dialog' else save if kw.get('name')=='Save' else button
        dialog.locator.return_value=close
        def edit(_frame,_dialog,index,before,desired,current,identity):
            identity();events.append(('edit',index));self.assertEqual(current,state['cards'])
            state['cards'][index]=native.group._expected(desired)[0]
            result=deepcopy(state['cards'])
            if drift_after_edit:state['cards'][index]['outcome']=['Show Field','Last Name']
            return result
        def author(_frame,_dialog,desired,prefix,identity):
            identity();events.append(('append',desired['target']));self.assertEqual(prefix,state['cards'])
            state['cards'].append(native.group._expected(desired)[0]);return deepcopy(state['cards'])
        def click(node):
            nonlocal saved
            if node is save:
                events.append(('save',))
                if not lost:saved=deepcopy(state['cards'])
        def reopen(*_):
            events.append(('reopen',));state['cards']=deepcopy(saved)
        with patch.object(native,'form_builder',return_value=frame),patch.object(native,'_close_initial'), \
             patch.object(native,'click',side_effect=click),patch.object(native.group,'_inventory',side_effect=lambda _:deepcopy(state['cards'])), \
             patch.object(native,'_edit',side_effect=edit),patch.object(native,'_author',side_effect=author), \
             patch.object(native,'reopen_editor',side_effect=reopen),patch.object(native.group,'_wait_for_form_save'):
            try:result=native.configure(page,data)
            except runner.Stop as error:result=error
        return result,events,saved,data

    def test_edits_exact_existing_prefix_then_appends_once_and_independently_reopens(self):
        result,events,saved,data=self.exercise()
        self.assertEqual(events,[('edit',0),('append','Email'),('save',),('reopen',)])
        self.assertEqual(saved,native._expected(data))
        self.assertEqual(result['status'],'CONDITION_STACK_SAVED_AND_REOPENED')
        self.assertEqual(result['rule_count'],2)
        self.assertEqual(result['configuration_sha256'],native.configuration_hash(data))

    def test_positive_empty_native_inventory_can_grow_without_an_existing_card_edit(self):
        result,events,saved,data=self.exercise(empty=True)
        self.assertEqual(events,[('append','Phone'),('save',),('reopen',)])
        self.assertEqual(saved,native._expected(data));self.assertEqual(result['rule_count'],1)

    def test_stale_full_before_inventory_prevents_every_write(self):
        result,events,_,_=self.exercise(drift_before=True)
        self.assertIsInstance(result,runner.Stop);self.assertEqual(events,[])

    def test_inventory_drift_after_edit_prevents_append_and_outer_save(self):
        result,events,_,_=self.exercise(drift_after_edit=True)
        self.assertIsInstance(result,runner.Stop)
        self.assertEqual(events,[('edit',0)])

    def test_lost_outer_save_cannot_certify_the_longer_staged_stack(self):
        result,events,saved,data=self.exercise(lost=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('did not persist',str(result))
        self.assertEqual(events,[('edit',0),('append','Email'),('save',),('reopen',)])
        self.assertEqual(saved,native._expected({'rules':data['expected_rules']}))


if __name__=='__main__':unittest.main()
