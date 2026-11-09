"""Ordered native Show/Hide rules, including one predicate with many targets.

Each native rule still has exactly one target. The full authored rule list is
the contract: existing cards must be its exact prefix before missing cards are
appended, or exactly match an explicit full expected_rules list before edits.
Existing cards are never deleted or reordered. Complete independent saved
readback is mandatory, including when all cards appear before Save.
"""
from copy import deepcopy
import hashlib
import json

if __package__:
    from . import form_conditions as group
    from .assessments import reopen_editor
    from .field_placement import _close_initial
    from .skill6_playwright import Stop,click,fill,form_builder,wait_until
else:
    import form_conditions as group
    from assessments import reopen_editor
    from field_placement import _close_initial
    from skill6_playwright import Stop,click,fill,form_builder,wait_until


def _rules(rules,*,reject_conflicts=True):
    if not isinstance(rules,list) or not 1<=len(rules)<=50:
        raise Stop('Native condition stacks require 1 to 50 ordered rules')
    normalized=[];seen=set()
    for rule in rules:
        if not isinstance(rule,dict) or set(rule)!={'match','clauses','effect','target'}:
            raise Stop('Every condition stack rule needs its complete predicate, effect and one target')
        valid=group.validate({'action':'native_condition_group',**rule},minimum_clauses=1)
        predicate=tuple(sorted((clause['if_field'],clause['operator'],clause.get('value',''))
                               for clause in valid['clauses']))
        identity=(('single' if len(predicate)==1 else valid['match']),predicate,valid['target'])
        if reject_conflicts and identity in seen:
            raise Stop('Duplicate or conflicting condition predicates for the same target require reconciliation')
        seen.add(identity)
        normalized.append({key:valid[key] for key in ('match','clauses','effect','target')})
    return normalized


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','rules','expected_rules'}
            or step.get('action','native_condition_stack')!='native_condition_stack'):
        raise Stop('Unsupported native condition stack')
    value={**deepcopy(step),'rules':_rules(step.get('rules'))}
    if 'expected_rules' in step:
        value['expected_rules']=_rules(step['expected_rules'],reject_conflicts=False)
        if len(value['expected_rules'])!=len(value['rules']):
            raise Stop('Native condition edits require equal complete previous and desired rule counts')
        for before,after in zip(value['expected_rules'],value['rules']):
            if len(after['clauses'])<len(before['clauses']):
                raise Stop('Shrinking native clauses requires a captured row removal flow; no writes attempted')
    return value


def configuration_hash(step):
    plan=validate(step)
    binding=({'expected_rules':plan['expected_rules'],'rules':plan['rules']}
             if 'expected_rules' in plan else plan['rules'])
    return hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _expected(plan):
    return [group._expected(rule)[0] for rule in plan['rules']]


def _author(frame,dialog,rule,prefix,identity):
    identity()
    click(group._one(dialog.get_by_text('Show/Hide Fields',exact=True),
                     'Native new Show/Hide rule tile changed'))
    modal=group._one(frame.get_by_role('dialog'),'Native condition rule editor is ambiguous')
    for index,clause in enumerate(rule['clauses']):
        identity()
        if modal.locator('[id^="selectedField-"]').count()!=index+1:
            raise Stop('Native condition rule has unrelated or missing source rows')
        group._choose(frame,'#selectedField-'+str(index),clause['if_field'])
        group._choose(frame,'#selectedOperation-'+str(index),clause['operator'])
        if clause['operator'] in group.BINARY:
            value=group._one(modal.locator('#inputValue-'+str(index)),
                             'Native condition value control changed')
            fill(value,clause['value'])
            if value.input_value()!=clause['value']:
                raise Stop('Native condition value did not accept the authored text')
        if index<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=index+1:
                raise Stop('Native condition row append connector count changed')
            connector=group._one(joins.nth(index).locator('[data-name="'+
                ('and' if rule['match']=='all' else 'or')+'"]'),
                'Native condition append connector is ambiguous')
            click(connector)
            wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==index+2,
                       'Native condition clause did not append exactly once')
    group._choose(frame,'#showHideFieldType',rule['effect'])
    group._choose(frame,'#selectedFieldShowHide',rule['target'])
    group._modal_state(modal,rule)
    identity()
    save=group._one(modal.locator('#modal-footer-btn-positive-action'),
                    'Native condition rule Save changed')
    if not save.is_enabled():raise Stop('Native condition rule is invalid; Save not attempted')
    click(save)
    wanted=[*prefix,group._expected(rule)[0]]
    wait_until(lambda:dialog.locator(group.CARD).count()==len(wanted)
               and dialog.locator('.condition-summary-row').count()==sum(len(row['rows']) for row in wanted),
               'Native appended condition card did not appear once in the full list')
    if group._inventory(dialog)!=wanted:
        raise Stop('Native appended condition changed the authored order, predicate, effect or target')
    return wanted


def _edit(frame,dialog,index,before_rule,rule,current,identity):
    """Edit the exact inventoried card without deleting or reordering cards."""
    identity()
    if group._inventory(dialog)!=current:
        raise Stop('Native condition cards changed immediately before the requested edit')
    cards=dialog.locator(group.CARD)
    if cards.count()!=len(current):raise Stop('Native condition card count changed before edit')
    card=cards.nth(index)
    click(group._one(card.locator('#edit-condition'),'Native condition card Edit control changed'))
    modal=group._one(frame.get_by_role('dialog'),'Native condition edit dialog is ambiguous')
    # Saved summary text alone cannot bless a stale modal. Read every current
    # source/operator/value/connector/effect/target before the first edit.
    group._modal_state(modal,before_rule)
    count=len(before_rule['clauses'])
    for row,clause in enumerate(rule['clauses']):
        identity()
        if modal.locator('[id^="selectedField-"]').count()!=count:
            raise Stop('Native condition edit row inventory changed')
        group._choose(frame,'#selectedField-'+str(row),clause['if_field'])
        group._choose(frame,'#selectedOperation-'+str(row),clause['operator'])
        if clause['operator'] in group.BINARY:
            value=group._one(modal.locator('#inputValue-'+str(row)),'Native edited condition value changed')
            fill(value,clause['value'])
            if value.input_value()!=clause['value']:
                raise Stop('Native condition edit ignored the authored binary value')
        if row<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=count:raise Stop('Native condition edit connector count changed')
            connector=joins.nth(row)
            wanted='and' if rule['match']=='all' else 'or'
            active=group._one(connector.locator('.n-tabs-tab--active'),'Native edited connector is ambiguous')
            appending=row==count-1
            if appending or active.get_attribute('data-name')!=wanted:
                click(group._one(connector.locator('[data-name="'+wanted+'"]'),
                                 'Native edited AND/OR control changed'))
                expected_count=count+int(appending)
                wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==expected_count,
                           'Native condition edit changed the wrong row count')
                count=expected_count
    group._choose(frame,'#showHideFieldType',rule['effect'])
    group._choose(frame,'#selectedFieldShowHide',rule['target'])
    group._modal_state(modal,rule)
    identity()
    save=group._one(modal.locator('#modal-footer-btn-positive-action'),'Native condition edit Save changed')
    if not save.is_enabled():raise Stop('Native edited condition is invalid; Save not attempted')
    click(save)
    wait_until(lambda:modal.locator('#modal-footer-btn-positive-action').count()==0
               or not modal.locator('#modal-footer-btn-positive-action').is_visible(),
               'Native condition edit modal did not close')
    wanted=deepcopy(current);wanted[index]=group._expected(rule)[0]
    wait_until(lambda:dialog.locator(group.CARD).count()==len(wanted)
               and dialog.locator('.condition-summary-row').count()==sum(len(item['rows']) for item in wanted),
               'Native edited full condition list did not reappear')
    wait_until(lambda:group._inventory(dialog)==wanted,
               'Native edited card or an untouched sibling differs from the full authored stack')
    return wanted


def configure(page,step):
    plan=validate(step)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not title.input_value().strip():
        raise Stop('Native condition stack form identity is missing or ambiguous')
    name,editor_url=title.input_value(),page.url

    def identity():
        if page.url!=editor_url or title.count()!=1 or title.input_value()!=name:
            raise Stop('Native condition stack form identity changed')

    def open_conditions():
        identity()
        _close_initial(frame)
        click(frame.get_by_role('tab',name='Edit',exact=True))
        click(frame.get_by_role('button',name='Open Conditional Logic',exact=True))
        dialog=group._one(frame.get_by_role('dialog'),'Native Conditions drawer is missing or ambiguous')
        return dialog

    dialog=open_conditions()
    before,wanted=group._inventory(dialog),_expected(plan)
    current=before
    if 'expected_rules' in plan:
        expected=_expected({'rules':plan['expected_rules']})
        if before!=expected:
            raise Stop('Native condition edit inventory differs from the complete expected previous stack')
        for index,(previous,rule) in enumerate(zip(plan['expected_rules'],plan['rules'])):
            if current[index]!=wanted[index]:
                current=_edit(frame,dialog,index,previous,rule,current,identity)
    else:
        if len(before)>len(wanted) or before!=wanted[:len(before)]:
            raise Stop('Existing native condition stack is not the exact authored prefix; reconcile before writing')
        for rule in plan['rules'][len(before):]:
            if group._inventory(dialog)!=current:
                raise Stop('Native condition stack changed after full preflight')
            current=_author(frame,dialog,rule,current,identity)
    if group._inventory(dialog)!=wanted:
        raise Stop('Native full condition stack differs before drawer Save')
    identity()
    click(group._one(dialog.locator('#conditional-logic-save-close'),
                     'Native Conditions save-close control changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    changed=before!=wanted
    if changed:
        identity()
        save=group._one(frame.get_by_role('button',name='Save',exact=True),
                        'Native outer condition stack Save changed')
        click(save)
        group._wait_for_form_save(page,save)
    # A staged card is never enough. Native capture demonstrated that
    # immediate navigation can lose a new card; exact independent reopen must
    # therefore fail closed if persistence did not finish or did not succeed.
    reopen_editor(page,'form',name,editor_url)
    frame=form_builder(page)
    dialog=open_conditions()
    if group._inventory(dialog)!=wanted:
        raise Stop('Native condition stack did not persist after independent reopen; do not repeat the append')
    click(group._one(dialog.locator('#conditional-logic-save-close'),
                     'Reopened native Conditions save-close changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return {'status':'CONDITION_STACK_SAVED_AND_REOPENED' if changed else 'CONDITION_STACK_REUSED_AND_REOPENED',
        'kind':'form_condition_stack','editor_url':page.url,'rule_count':len(plan['rules']),
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}
