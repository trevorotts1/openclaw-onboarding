import copy
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import assessments as a
import skill6_playwright as runner
import recipe_cli


def quiz():
    return {'kind': 'quiz', 'questions': [
        {'id': 'q1', 'choices': [{'value': 'skip', 'score': 0, 'next': 'submit'},
                                 {'value': 'continue', 'score': 2}]},
        {'id': 'q2', 'choices': [{'value': 'low', 'score': 0}, {'value': 'high', 'score': 3}]},
    ], 'results': [{'id': 'starter', 'min': 0, 'max': 2}, {'id': 'advanced', 'min': 3, 'max': 5}]}


class AssessmentModels(unittest.TestCase):
    def test_branch_scores_only_visited_questions(self):
        result = a.evaluate_model(quiz(), {'q1': 'skip', 'q2': 'high'})
        self.assertEqual(result, {'visited': ['q1'], 'score': 0, 'result': 'starter',
                                  'ignored_unvisited_answers': ['q2']})
        self.assertEqual(a.evaluate_model(quiz(), {'q1': 'continue', 'q2': 'high'})['result'], 'advanced')

    def test_missing_choice_and_missing_visited_answer_refused(self):
        for answers in ({'q1': 'unknown'}, {'q1': 'continue'}, {'q1': 'skip', 'other': 'x'}):
            with self.subTest(answers=answers), self.assertRaises(a.AssessmentError):
                a.evaluate_model(quiz(), answers)

    def test_dangling_and_backward_routes_refused(self):
        for target in ('missing', 'q1'):
            model = quiz()
            model['questions'][1]['choices'][0]['next'] = target
            with self.subTest(target=target), self.assertRaises(a.AssessmentError):
                a.validate_model(model)

    def test_duplicate_choice_and_boolean_scores_refused(self):
        model = quiz()
        model['questions'][0]['choices'][1]['value'] = 'skip'
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)
        model = quiz()
        model['questions'][0]['choices'][0]['score'] = True
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)

    def test_overlap_and_reachable_score_gap_refused(self):
        model = quiz()
        model['results'][1]['min'] = 2
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)
        model = quiz()
        model['results'][0]['max'] = 1
        with self.assertRaises(a.AssessmentError):
            a.validate_model(model)

    def test_submission_is_compared_against_authored_model(self):
        answers = {'q1': 'continue', 'q2': 'high'}
        observed = {'visited': ['q1', 'q2'], 'score': 5, 'result': 'advanced'}
        self.assertEqual(a.verify_submission(quiz(), answers, observed)['status'], 'PASS')
        observed['score'] = 2
        self.assertEqual(a.verify_submission(quiz(), answers, observed)['differences'], ['score'])

    def test_survey_forward_jump_and_no_fake_score(self):
        model = {'kind': 'survey', 'questions': [
            {'id': 'q1', 'choices': [{'value': 'bypass', 'next': 'q3'}]},
            {'id': 'q2', 'choices': [{'value': 'unused'}]},
            {'id': 'q3', 'choices': [{'value': 'finish'}]}]}
        result = a.evaluate_model(model, {'q1': 'bypass', 'q3': 'finish'})
        self.assertEqual(result['visited'], ['q1', 'q3'])
        self.assertIsNone(result['score'])


class FieldConfiguration(unittest.TestCase):
    def test_only_captured_standard_properties_accepted(self):
        valid = {'fields': [{'field': 'Last Name', 'label': 'Family Name', 'width_pct': 50,
                             'required': True, 'hidden': False}]}
        self.assertEqual(a.validate_fields(valid), valid)
        cases = [[], [{'field': 'Custom Answer', 'label': 'Unknown'}],
                 [{'field': 'Last Name', 'required': True, 'hidden': True}],
                 [{'field': 'Last Name', 'hidden': False, 'hidden_value': 'ignored'}],
                 [{'field': 'Last Name', 'width_pct': True}],
                 [{'field': 'Last Name', 'placeholder': 'your@email.com'}],
                 [{'field': 'Last Name', 'required': 'false'}]]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(a.AssessmentError):
                a.validate_fields({'fields': fields})

    def test_condition_never_silently_ignores_value_or_action(self):
        valid = {'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name'}
        self.assertEqual(a.validate_condition(valid), valid)
        cases = [{**valid, 'value': 'ignored'}, {**valid, 'action': 'Show Fields'},
                 {**valid, 'operator': 'Is Equal To'}, {**valid, 'target': 'Unknown Field'}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(a.AssessmentError):
                a.validate_condition(case)
        self.assertEqual(a.validate_condition({**valid, 'operator': 'Contains', 'value': 'Test'})['value'], 'Test')

    def test_previously_customized_standard_field_requires_both_identity_anchors(self):
        field = {'field': 'Last Name', 'current_placeholder': 'Family name',
                 'current_query_key': 'family', 'required': True}
        self.assertEqual(a.validate_fields({'fields': [field]})['fields'][0], field)
        del field['current_query_key']
        with self.assertRaises(a.AssessmentError):
            a.validate_fields({'fields': [field]})

    def test_runner_action_metadata_does_not_override_native_condition_effect(self):
        step = {'id': 'native_condition1', 'action': 'native_condition', 'effect': 'Hide Field',
                'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name'}
        self.assertEqual(a.validate_condition(step), step)
        self.assertEqual(a.validate_condition({**step,'effect':'Show Field'})['effect'],'Show Field')
        with self.assertRaises(a.AssessmentError):
            a.validate_condition({**step, 'effect': 'Show Fields'})

    def test_uncaptured_field_and_condition_requests_are_not_silently_ignored(self):
        with self.assertRaises(a.AssessmentError):
            a.validate_fields({'fields': [{'field': 'Last Name', 'required': True}], 'redirect_url': 'https://example.invalid'})
        with self.assertRaises(a.AssessmentError):
            a.validate_condition({'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name', 'send_email': True})

    def test_condition_recipe_normalizes_legacy_effect_and_preserves_runner_action(self):
        base = {'location_id': 'fixture', 'location_name': 'Fixture',
                'start_url': 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'}
        condition = {'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name', 'action': 'Hide Field'}
        job = recipe_cli.compile_recipe('forms.conditions', {**base, 'condition': condition})
        self.assertEqual(job['steps'][0]['action'], 'native_condition')
        self.assertEqual(job['steps'][0]['effect'], 'Hide Field')
        runner.validate_job(job, Path('.'))
        show=recipe_cli.compile_recipe('forms.conditions',{**base,'condition':{**condition,'action':'Show Field'}})
        self.assertEqual(show['steps'][0]['effect'],'Show Field')
        for invalid in ([], {**condition, 'effect': 'Show Field'}, {**condition, 'action': 'Show Fields'}):
            with self.subTest(invalid=invalid), self.assertRaises(runner.Stop):
                recipe_cli.compile_recipe('forms.conditions', {**base, 'condition': invalid})


class NativeFieldExecution(unittest.TestCase):
    def surface(self, *, persist=True, drift=False):
        original = ['Last Name', 'Enter your last name', '', 'last_name', '100']
        state = {'values': original.copy(), 'required': False, 'hidden': False, 'panel': False, 'saves': 0}
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        inputs = []
        labels = ('Label', 'Placeholder', 'Short Label', 'Query Key', 'Field Width', 'Hidden value')
        for index in range(6):
            loc = MagicMock()
            loc.input_value.side_effect = lambda i=index: state['values'][i]
            loc.fill.side_effect = lambda value, i=index: state['values'].__setitem__(i, value)
            loc.evaluate.return_value = 'Wrong control' if drift and index == 3 else labels[index]
            inputs.append(loc)
        group = MagicMock()
        group.count.side_effect = lambda: len(state['values'])
        group.nth.side_effect = lambda i: inputs[i]
        title = MagicMock()
        title.input_value.return_value = 'ZHC Native Fixture'
        title.count.return_value = 1
        back = MagicMock()
        back.count.side_effect = lambda: 2 if state['panel'] else 1
        close_panel = MagicMock()
        close_panel.click.side_effect = lambda **_: state.__setitem__('panel', False)
        back.nth.return_value = close_panel

        def leave():
            if not persist:
                state['values'] = original.copy()
                state['required'] = False
                state['hidden'] = False
        back.click.side_effect = leave
        page.goto.side_effect = lambda *args, **kwargs: leave()
        page.frame_locator.return_value = frame
        save = MagicMock()
        save.count.return_value = 1
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        save.is_enabled.return_value = True
        checks = {}
        for key in ('required', 'hidden'):
            check = MagicMock()
            check.count.return_value = 1
            check.is_checked.side_effect = lambda k=key: state[k]
            def check_value(value, k=key):
                state[k] = value
                if k == 'hidden':
                    if value and len(state['values']) == 5:
                        state['values'].append('')
                    elif not value and len(state['values']) == 6:
                        state['values'].pop()
            check.set_checked.side_effect = check_value
            checks[key.title()] = check
        empty = MagicMock()
        empty.count.return_value = 0

        def role(role, *, name=None, exact=None):
            if role == 'textbox':
                return title if name == 'Form Name' else group
            if role == 'checkbox':
                return checks[name]
            if role == 'button' and name == 'Back':
                return back
            if role == 'button' and name == 'Save':
                return save
            return empty
        frame.get_by_role.side_effect = role
        frame.get_by_text.return_value = empty
        open_settings = MagicMock()
        open_settings.count.return_value = 1
        open_settings.click.side_effect = lambda **_: state.__setitem__('panel', True)
        frame.get_by_label.return_value = open_settings

        wrapper, kind, canvas_input, items = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        wrapper.count.return_value = kind.count.return_value = canvas_input.count.return_value = items.count.return_value = 1
        kind.get_attribute.return_value = 'text'
        wrapper.locator.side_effect = lambda selector: {
            '[data-field-type]':kind, 'input':canvas_input,
            '[aria-label="Open settings"]':open_settings}[selector]
        items.nth.return_value = wrapper
        frame.locator.side_effect = lambda selector: items if selector == '#form-builder-container > .form-field-wrapper' else None

        def placeholder(value, *, exact):
            target = MagicMock()
            target.count.return_value = int(state['values'][1] == value)
            target.locator.side_effect = lambda selector: wrapper if selector == a.FIELD_WRAPPER else None
            return target
        frame.get_by_placeholder.side_effect = placeholder
        return page, frame, state

    def run_surface(self, page, frame, step):
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=MagicMock()):
            return a.configure_fields(page, step)

    def test_native_field_edits_are_independently_reopened(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name',
            'placeholder': 'Type family name', 'short_label': 'Family', 'query_key': 'family',
            'width_pct': 50, 'required': True}]})
        self.assertEqual(result['status'], 'FIELD_PROPERTIES_SAVED_AND_REOPENED')
        self.assertEqual(state['values'], ['Family Name', 'Type family name', 'Family', 'family', '50'])
        self.assertEqual(state['saves'], 1)

    def test_hidden_field_value_is_verified_after_reopen(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame, {'fields': [{'field': 'Last Name',
            'required': False, 'hidden': True, 'hidden_value': 'Saved hidden value'}]})
        self.assertEqual(result['status'], 'FIELD_PROPERTIES_SAVED_AND_REOPENED')
        self.assertTrue(state['hidden'])
        self.assertFalse(state['required'])
        self.assertEqual(state['values'][5], 'Saved hidden value')

    def test_save_click_does_not_mask_lost_persisted_values(self):
        page, frame, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name'}]})
        self.assertEqual(state['saves'], 1)

    def test_property_order_drift_stops_before_any_write(self):
        page, frame, state = self.surface(drift=True)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame, {'fields': [{'field': 'Last Name', 'label': 'Family Name'}]})
        self.assertEqual(state['values'][0], 'Last Name')
        self.assertEqual(state['saves'], 0)


class NativeConditionExecution(unittest.TestCase):
    def surface(self, *, existing=False, enabled=True, persist=True, selected='Hide Field', existing_effect='Hide Field', target_match=True):
        page, frame, dialog = MagicMock(), MagicMock(), MagicMock()
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        state = {'count': 5, 'saves': 0, 'reopened': False,'selected_effect':selected,'target_clicks':0}
        page.goto.side_effect = lambda *args, **kw: state.__setitem__('reopened', True)
        inputs, save = MagicMock(), MagicMock()
        inputs.count.side_effect = lambda: state['count']
        def entry(index):
            control = MagicMock()
            # Real native n-select search inputs are blank, including the action.
            control.input_value.return_value = ''
            control.evaluate.side_effect=lambda *args:{'labels':1,'overlays':1,'title':state['selected_effect'],'text':state['selected_effect']}
            if index == state['count']-1:
                control.click.side_effect=lambda:state.__setitem__('target_clicks',state['target_clicks']+1)
            return control
        inputs.nth.side_effect = entry
        save.count.return_value = 1
        save.is_enabled.return_value = enabled
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        card = MagicMock()
        def card_text(value, **kw):
            loc = MagicMock()
            card_effect=existing_effect if existing else state['selected_effect']
            loc.count.return_value = (2 if value==card_effect else 0) if value in ('Hide Field','Show Field') else int(target_match)
            return loc
        card.get_by_text.side_effect = card_text
        rows=MagicMock()
        rows.count.side_effect=lambda:int((existing or state['saves']>0) and (persist or not state['reopened']))
        row=MagicMock()
        row.text_content.return_value='IfLast NameIs Filled'
        row.locator.return_value.locator.return_value=card
        rows.nth.return_value=row
        dialog.locator.return_value=rows
        def text(value, *, exact):
            loc = MagicMock()
            if value == 'No existing conditions yet':
                loc.count.return_value = int(not existing)
            elif value == 'IfLast NameIs Filled':
                loc.count.return_value = int((existing or state['saves'] > 0) and (persist or not state['reopened']))
                loc.nth.return_value.locator.return_value.locator.return_value.locator.return_value = card
            elif value in ('Hide Field','Show Field'):
                loc.count.return_value = 2 if state['saves'] and value==state['selected_effect'] else 0
            else:
                loc.count.return_value = 1
            if value in ('Is Empty', 'Is Filled'):
                loc.click.side_effect = lambda: state.__setitem__('count', 4)
            return loc
        dialog.get_by_text.side_effect = text
        dialog.get_by_role.side_effect = lambda role, **kw: inputs if role == 'textbox' else save
        title = MagicMock()
        title.input_value.return_value = 'ZHC Condition Fixture'
        def role(role, **kw):
            if role == 'dialog':
                return dialog
            if role == 'textbox':
                return title
            return save if kw.get('name') == 'Save' else MagicMock()
        frame.get_by_role.side_effect = role
        def effect_option(value, **kw):
            option=MagicMock()
            option.count.return_value=1
            option.click.side_effect=lambda:state.__setitem__('selected_effect',value)
            return option
        frame.locator.return_value.get_by_text.side_effect=effect_option
        return page, frame, state

    def run_surface(self, page, frame, step=None):
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'visible', return_value=False):
            return a.configure_condition(page, step or {'if_field': 'Last Name', 'operator': 'Is Filled', 'target': 'First Name'})

    def test_native_condition_requires_all_three_saves_and_reopen(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame)
        self.assertEqual(state['saves'], 3)

        self.assertEqual(result['independent_readback'], 'VERIFIED')
        self.assertFalse(result['submission_verified'])
        self.assertTrue(state['reopened'])

    def test_existing_matching_rule_is_read_without_duplicate_create(self):
        page, frame, state = self.surface(existing=True)
        result = self.run_surface(page, frame)
        self.assertEqual(result['status'], 'CONDITION_ALREADY_PRESENT')
        self.assertEqual(state['saves'], 0)

    def test_blank_search_values_use_captured_selected_label_and_overlay(self):
        page,frame,state=self.surface()
        self.assertEqual(self.run_surface(page,frame)['independent_readback'],'VERIFIED')
        self.assertEqual(state['saves'],3)

    def test_plural_or_wrong_selected_effect_stops_before_target_and_save(self):
        for selected in ('Hide Fields','Show Fields','Unexpected'):
            with self.subTest(selected=selected):
                page,frame,state=self.surface(selected=selected)
                with self.assertRaises(runner.Stop):self.run_surface(page,frame)
                self.assertEqual(state['target_clicks'],0)
                self.assertEqual(state['saves'],0)

    def test_show_selection_saves_and_verifies_captured_reopened_card(self):
        page,frame,state=self.surface()
        result=self.run_surface(page,frame,{'if_field':'Last Name','operator':'Is Filled','target':'First Name','effect':'Show Field'})
        self.assertEqual(state['selected_effect'],'Show Field')
        self.assertEqual(state['saves'],3)
        self.assertEqual(result['independent_readback'],'VERIFIED')
        self.assertFalse(result['behavior_verified'])

    def test_reopened_show_rule_with_wrong_target_is_not_success(self):
        page,frame,state=self.surface(target_match=False)
        with self.assertRaises(runner.Stop):self.run_surface(page,frame,{'if_field':'Last Name','operator':'Is Filled','target':'First Name','effect':'Show Field'})
        self.assertEqual(state['saves'],3)

    def test_lost_show_save_is_not_verified(self):
        page,frame,state=self.surface(persist=False)
        with self.assertRaises(runner.Stop):self.run_surface(page,frame,{'if_field':'Last Name','operator':'Is Filled','target':'First Name','effect':'Show Field'})
        self.assertEqual(state['saves'],3)

    def test_existing_show_rule_is_not_duplicated(self):
        page,frame,state=self.surface(existing=True,existing_effect='Show Field')
        result=self.run_surface(page,frame,{'if_field':'Last Name','operator':'Is Filled','target':'First Name','effect':'Show Field'})
        self.assertEqual(result['status'],'CONDITION_ALREADY_PRESENT')
        self.assertEqual(state['saves'],0)

    def test_existing_opposite_effect_is_not_silently_overwritten(self):
        page,frame,state=self.surface(existing=True,existing_effect='Hide Field')
        with self.assertRaises(runner.Stop):self.run_surface(page,frame,{'if_field':'Last Name','operator':'Is Filled','target':'First Name','effect':'Show Field'})
        self.assertEqual(state['saves'],0)

    def test_disabled_save_does_not_create(self):
        page, frame, state = self.surface(enabled=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame)
        self.assertEqual(state['saves'], 0)

    def test_missing_persisted_card_is_not_success(self):
        page, frame, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame)
        self.assertEqual(state['saves'], 3)


class NativeCSS(unittest.TestCase):
    def test_owned_css_replacement_preserves_foreign_css_and_is_idempotent(self):
        step = {'custom_css': 'input { border-radius: 12px; }', 'css_key': 'form-look'}
        existing = '/* Client styles */\nbody { color: purple; }\n'
        first = a.merge_css(existing, step)
        self.assertTrue(first.startswith(existing))
        self.assertEqual(a.merge_css(first, step), first)
        changed = a.merge_css(first, {**step, 'custom_css': 'input { border-radius: 18px; }'})
        self.assertTrue(changed.startswith(existing))
        self.assertNotIn('12px', changed)
        self.assertEqual(changed.count('form-look-BEGIN'), 1)

    def test_invalid_markers_and_invalid_style_checks_refuse(self):
        marker = '/* ZHC-SKILL6-APPROVED-CSS-approved-css-'
        for existing in (marker + 'BEGIN */', marker + 'END */' + marker + 'BEGIN */'):
            with self.subTest(existing=existing), self.assertRaises(a.AssessmentError):
                a.merge_css(existing, {'custom_css': 'input {}'})
        for step in ({'custom_css': ''}, {'custom_css': 'input {}', 'css_key': '../bad'},
                     {'custom_css': 'input {}', 'expect_styles': [{'selector': 'input', 'count': True, 'properties': {'color': 'red'}}]},
                     {'custom_css': marker + 'BEGIN */'}, {'custom_css': 'input {}', 'unimplemented': True}):
            with self.subTest(step=step), self.assertRaises(a.AssessmentError):
                a.validate_css(step)

    def test_custom_css_recipe_keeps_optional_radius_and_compiles_native_action(self):
        base = {'location_id': 'fixture', 'location_name': 'Fixture',
                'start_url': 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form',
                'custom_css': 'input {color:red}', 'radius': 12}
        job = recipe_cli.compile_recipe('forms.style', base)
        self.assertEqual([step['action'] for step in job['steps']], ['form_css', 'native_form_css'])
        runner.validate_job(job, Path('.'))

    def surface(self, persist=True):
        page, frame, pane, editor = (MagicMock() for _ in range(4))
        page.url = 'https://app.convertandflow.com/v2/location/fixture/form-builder-v2/form'
        original = 'input { color: purple; }\n'
        state = {'css': original, 'saves': 0}
        title = MagicMock()
        title.input_value.return_value = 'ZHC CSS Fixture'
        save = MagicMock()
        save.count.return_value = 1
        save.is_enabled.return_value = True
        save.click.side_effect = lambda: state.__setitem__('saves', state['saves'] + 1)
        def goto(*args, **kwargs):
            if not persist:
                state['css'] = original
        page.goto.side_effect = goto
        pane.count.return_value = editor.count.return_value = 1
        editor.evaluate.side_effect = lambda *args: state['css']
        editor.fill.side_effect = lambda value: state.__setitem__('css', value)
        pane.get_by_role.side_effect = lambda role, **kw: editor if role == 'textbox' else MagicMock()
        dialogs = MagicMock()
        dialogs.filter.return_value = pane
        def role(role, *, name=None, exact=None):
            if role == 'textbox':
                return title
            if role == 'dialog':
                return dialogs
            return save if name == 'Save' else MagicMock()
        frame.get_by_role.side_effect = role
        page.frame_locator.return_value = frame
        return page, frame, state

    def run_surface(self, page, frame, step=None):
        with patch.object(runner, 'form_builder', return_value=frame), \
             patch.object(runner, 'click', side_effect=lambda loc: loc.click()), \
             patch.object(runner, 'fill', side_effect=lambda loc, value: loc.fill(value)), \
             patch.object(runner, 'visible', return_value=False), \
             patch.object(runner, 'wait_until', side_effect=lambda predicate, message: self.assertTrue(predicate())), \
             patch.object(runner, 'exact_search', return_value=MagicMock()):
            return a.configure_css(page, {'custom_css': 'input {border-radius:12px}'} if step is None else step)

    def test_native_css_save_preserves_client_css_and_reopens_exact_content(self):
        page, frame, state = self.surface()
        result = self.run_surface(page, frame)
        self.assertEqual(result['status'], 'NATIVE_FORM_CSS_SAVED_AND_REOPENED')
        self.assertTrue(state['css'].startswith('input { color: purple; }'))
        self.assertIn('border-radius:12px', state['css'])
        self.assertEqual(state['saves'], 1)

    def test_native_css_lost_save_is_not_reported_success(self):
        page, frame, state = self.surface(persist=False)
        with self.assertRaises(runner.Stop):
            self.run_surface(page, frame)
        self.assertEqual(state['saves'], 1)

    def test_requested_render_checks_require_exact_count_and_values(self):
        step = {'custom_css': 'input {border-radius:12px}', 'expect_styles': [
            {'selector': 'input', 'count': 4, 'properties': {'border-top-left-radius': '12px'}}]}
        for observed in (['12px'] * 4, ['12px'] * 3, ['12px', '12px', '12px', '0px'], []):
            page, frame, state = self.surface()
            preview, elements = MagicMock(), MagicMock()
            page.context.expect_page.return_value.__enter__.return_value.value = preview
            preview.locator.return_value = elements
            elements.count.return_value = 4
            elements.evaluate_all.return_value = observed
            with self.subTest(observed=observed):
                if observed == ['12px'] * 4:
                    self.assertEqual(self.run_surface(page, frame, step)['render_checks'], 1)
                else:
                    with self.assertRaises(runner.Stop):
                        self.run_surface(page, frame, step)
                preview.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
