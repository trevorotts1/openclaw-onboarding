"""Custom TEXT identities and virtualized native condition menus fail closed."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

import form_condition_fields as fields
import form_conditions as group
import form_condition_stack as stack
import form_condition_outcomes as outcomes
import recipe_cli
import skill6_playwright as runner
import test_form_condition_outcomes as outcome_fixtures


LABEL='Fixture custom text'
BINDING={'label':LABEL,'query_key':'fixture_custom_text','field_type':'TEXT'}


def rule():
    return {'match':'any','clauses':[
        {'if_field':LABEL,'operator':'Contains','value':'probe'},
        {'if_field':'First Name','operator':'Is Filled'}],
        'effect':'Hide Field','target':LABEL}


def plans():
    value={'rules':[rule()],'field_bindings':[deepcopy(BINDING)]}
    return ((group,{**rule(),'field_bindings':[deepcopy(BINDING)]}),
            (stack,deepcopy(value)),(outcomes,deepcopy(value)))


class BindingSchemaTests(unittest.TestCase):
    def test_all_three_schemas_bind_custom_source_and_target(self):
        for module,data in plans():
            with self.subTest(module=module.__name__):self.assertEqual(module.validate(data),data)

    def test_custom_sources_and_targets_require_their_explicit_binding(self):
        for module,data in plans():
            data.pop('field_bindings');page=Mock()
            with self.subTest(module=module.__name__),self.assertRaises(runner.Stop):module.configure(page,data)
            self.assertFalse(page.mock_calls)

    def test_unsupported_radio_duplicate_labels_keys_and_builtin_shadowing_refuse_before_page(self):
        bad=[[],[{'label':LABEL,'query_key':'x','field_type':'RADIO'}],
             [{**BINDING,'extra':True}],[{**BINDING,'label':'Email'}],
             [{**BINDING,'query_key':'email'}],
             [deepcopy(BINDING),deepcopy(BINDING)],
             [deepcopy(BINDING),{**BINDING,'label':'Another'}],
             [deepcopy(BINDING),{**BINDING,'query_key':'another'}]]
        for module,data in plans():
            for bindings in bad:
                page=Mock();changed={**data,'field_bindings':bindings}
                with self.subTest(module=module.__name__,bindings=bindings),self.assertRaises(runner.Stop):module.configure(page,changed)
                self.assertFalse(page.mock_calls)

    def test_every_hash_binds_query_key_and_complete_custom_sibling_inventory(self):
        for module,data in plans():
            changed=deepcopy(data);changed['field_bindings'][0]['query_key']='changed_key'
            sibling=deepcopy(data);sibling['field_bindings'].append({'label':'Unused sibling','query_key':'unused_sibling','field_type':'TEXT'})
            with self.subTest(module=module.__name__):
                self.assertEqual(len({module.configuration_hash(value) for value in (data,changed,sibling)}),3)

    def test_compiler_threads_bindings_for_show_hide_and_outcome_stacks(self):
        for effect in ('Hide Field',outcomes.REDIRECT):
            value=rule()
            if effect==outcomes.REDIRECT:
                value.pop('target');value.update(effect=effect,redirect_url='https://example.com/next')
            data={'location_id':'LOC','location_name':'Fixture',
                'start_url':'https://app.example.com/v2/location/LOC/form-builder-v2/FORM',
                'condition':{'rules':[value],'field_bindings':[deepcopy(BINDING)]}}
            job=runner.validate_job(recipe_cli.compile_recipe('forms.conditions',data),Path('.'))
            self.assertEqual(job['steps'][0]['field_bindings'],[BINDING])

    def test_rich_outcome_inventory_uses_explicit_custom_binding_without_losing_html_hash(self):
        value=rule();value.pop('target');value.update(effect=outcomes.MESSAGE,message='Hello')
        drawer,_=outcome_fixtures.InventoryTests().surface([(value,'<p><strong>Hello</strong></p>')])
        read=outcomes._inventory(drawer,field_bindings=[BINDING])
        self.assertEqual(read[0]['rule'],value)
        self.assertIsInstance(read[0]['rich_html_sha256'],str)
        with self.assertRaises(runner.Stop):outcomes._inventory(drawer)


def canvas_fixture(bindings):
    frame=Mock();items=Mock();items.count.return_value=len(bindings)
    entries=[];queries=[]
    for binding in bindings:
        item,label,control,gear,query=[Mock() for _ in range(5)]
        label.count.return_value=control.count.return_value=gear.count.return_value=query.count.return_value=1
        attributes={'data-field-type':'TEXT','contenteditable':'true','role':'textbox','aria-label':'Label'}
        label.get_attribute.side_effect=attributes.get;label.inner_text.return_value=binding['label']
        control.get_attribute.return_value=None
        query.is_visible.return_value=True;query.input_value.return_value=binding['query_key']
        item.locator.side_effect={'[data-field-type]':label,'input.form-placeholder.form-control':control,
            '[aria-label="Open settings"]':gear}.__getitem__
        entries.append((item,label,gear));queries.append(query)
    items.nth.side_effect=lambda index:entries[index][0]
    current={'index':None};events=[]
    def locate(selector):
        if selector==fields.CANVAS_ITEMS:return items
        if selector=='#fieldQueryKey input.n-input__input-el':return queries[current['index']]
        raise AssertionError(selector)
    frame.locator.side_effect=locate
    def click(node):
        for index,(_,label,gear) in enumerate(entries):
            if node is label:current['index']=index;events.append(('select',index));return
            if node is gear:events.append(('settings',index));return
        raise AssertionError('Unexpected preflight click')
    return frame,entries,queries,events,click


class CanvasBindingTests(unittest.TestCase):
    def exercise(self,bindings,*,actual=None,wrong_key=False):
        frame,entries,queries,events,click=canvas_fixture(actual if actual is not None else bindings)
        if wrong_key:queries[0].input_value.return_value='wrong'
        with patch.object(fields,'_close_initial'),patch.object(fields,'_close_properties'), \
             patch.object(fields,'click',side_effect=click):
            try:result=fields.preflight(frame,bindings,lambda:None)
            except runner.Stop as error:result=error
        return result,events,frame

    def test_reads_every_custom_text_key_without_filling_a_property(self):
        bindings=[deepcopy(BINDING),{'label':'Unused sibling','query_key':'unused_sibling','field_type':'TEXT'}]
        result,events,frame=self.exercise(bindings)
        self.assertEqual(result,bindings)
        self.assertEqual(events,[('select',0),('settings',0),('select',1),('settings',1)])
        self.assertFalse(any('fill' in str(call) for call in frame.mock_calls))

    def test_extra_or_missing_custom_sibling_refuses_before_selecting_a_field(self):
        for actual in ([],[BINDING,{'label':'Extra','query_key':'extra','field_type':'TEXT'}]):
            result,events,_=self.exercise([BINDING],actual=actual)
            self.assertIsInstance(result,runner.Stop);self.assertEqual(events,[])

    def test_changed_query_key_does_not_get_promoted_to_a_verified_binding(self):
        result,events,_=self.exercise([BINDING],wrong_key=True)
        self.assertIsInstance(result,runner.Stop);self.assertIn('Query Key differs',str(result))
        self.assertEqual(events,[('select',0),('settings',0)])

    def test_duplicate_canvas_labels_refuse_even_with_one_requested_label(self):
        result,events,_=self.exercise([BINDING],actual=[BINDING,BINDING])
        self.assertIsInstance(result,runner.Stop);self.assertEqual(events,[])


class SearchableSelectionTests(unittest.TestCase):
    def test_search_resolves_custom_field_missing_from_initial_virtualized_options(self):
        frame,node,search,menu,option=[Mock() for _ in range(5)]
        node.count.return_value=search.count.return_value=1
        state={'query':'','selected':''};events=[]
        node.locator.side_effect={'input.n-base-selection-input':search}.__getitem__
        frame.locator.side_effect={'#selectedField-0':node,'.n-base-select-option:visible':menu}.__getitem__
        menu.get_by_text.return_value=option
        option.count.side_effect=lambda:int(state['query']==LABEL)
        def fill(node,value):
            self.assertIs(node,search);state['query']=value;events.append(('search',value))
        def click(node):
            events.append(('click','option' if node is option else 'selector'))
            if node is option:state['selected']=LABEL
        def wait(fn,message):
            if not fn():raise runner.Stop(message)
        with patch.object(group,'fill',side_effect=fill),patch.object(group,'click',side_effect=click), \
             patch.object(group,'_selected',side_effect=lambda _:state['selected']),patch.object(group,'wait_until',side_effect=wait):
            group._choose(frame,'#selectedField-0',LABEL)
        self.assertEqual(events,[('click','selector'),('search',LABEL),('click','option')])
        menu.get_by_text.assert_called_once_with(LABEL,exact=True)


class BoundLifecycleTests(unittest.TestCase):
    def exercise(self,module,*,drift_at=None):
        data=next(data for candidate,data in plans() if candidate is module)
        page,frame,title,drawer,close,save,button=[Mock() for _ in range(7)]
        page.url='https://app.example.com/v2/location/LOC/form-builder-v2/FORM'
        for node in (title,close):node.count.return_value=1
        state={'open':False};drawer.count.side_effect=lambda:int(state['open'])
        title.input_value.return_value='Fixture'
        frame.get_by_role.side_effect=lambda role,**kw:(title if role=='textbox' else drawer if role=='dialog'
            else save if kw.get('name')=='Save' else button)
        drawer.locator.side_effect={'#conditional-logic-save-close':close}.__getitem__
        drawer.get_by_text.return_value=Mock(count=lambda:1)
        current=([{'rule':rule(),'rich_html_sha256':None}] if module is outcomes else
                 group._expected(rule()))
        checks=[];clicked=[]
        def click(node):
            clicked.append(node)
            if node is button:state['open']=True
            if node is close:state['open']=False
        def preflight(actual_frame,bindings,identity):
            identity();self.assertIs(actual_frame,frame);self.assertEqual(bindings,[BINDING])
            checks.append(True)
            if len(checks)==drift_at:raise runner.Stop('simulated custom Query Key drift')
        inventory_owner=outcomes if module is outcomes else group
        patches=[patch.object(module,'form_builder',return_value=frame),
            patch.object(module,'click',side_effect=click),
            patch.object(module,'reopen_editor'),patch.object(fields,'preflight',side_effect=preflight),
            patch.object(inventory_owner,'_inventory',return_value=deepcopy(current))]
        if module is not group:patches.append(patch.object(module,'_close_initial'))
        from contextlib import ExitStack
        with ExitStack() as context:
            for pending in patches:context.enter_context(pending)
            try:result=module.configure(page,data)
            except runner.Stop as error:result=error
        return result,checks,clicked,save

    def test_every_handler_rechecks_all_custom_bindings_after_independent_reopen(self):
        for module in (group,stack,outcomes):
            with self.subTest(module=module.__name__):
                result,checks,clicked,save=self.exercise(module)
                self.assertIsInstance(result,dict)
                self.assertEqual(len(checks),2);self.assertNotIn(save,clicked)
                self.assertEqual(result['configuration_sha256'],module.configuration_hash(
                    next(data for candidate,data in plans() if candidate is module)))

    def test_initial_field_drift_prevents_condition_clicks_and_reopened_drift_refuses_success(self):
        for module in (group,stack,outcomes):
            for drift_at in (1,2):
                with self.subTest(module=module.__name__,drift_at=drift_at):
                    result,checks,clicked,save=self.exercise(module,drift_at=drift_at)
                    self.assertIsInstance(result,runner.Stop);self.assertNotIn(save,clicked)
                    self.assertEqual(len(checks),drift_at)
                    if drift_at==1:self.assertEqual(clicked,[])


if __name__=='__main__':unittest.main()
