"""Ordered native Show/Hide rules, including one predicate with many targets.

Each native rule still has exactly one target. The full authored rule list is
the contract: existing cards must be its exact prefix before missing cards are
appended, or exactly match an explicit full expected_rules list before edits.
An explicit full expected inventory also permits captured tail-card removal;
cards are never silently reordered. Explicit recreate_order permits a full
permutation through captured Delete/author controls, retaining the unchanged
prefix and recreating the suffix. It does not use or claim native drag order.
Complete independent saved readback is
mandatory, including when all cards appear before Save.
"""
from copy import deepcopy
import hashlib
import json

if __package__:
    from . import form_conditions as group
    from .assessments import reopen_editor, read_editor_title
    from .field_placement import _close_initial
    from .skill6_playwright import Stop,click,fill,form_builder,wait_until
else:
    import form_conditions as group
    from assessments import reopen_editor, read_editor_title
    from field_placement import _close_initial
    from skill6_playwright import Stop,click,fill,form_builder,wait_until


_ROW_DELETE_PATH='M16 6v-.8c0-1.12 0-1.68-.218-2.108a2 2 0 00-.874-.874C14.48 2 13.92 2 12.8 2h-1.6c-1.12 0-1.68 0-2.108.218a2 2 0 00-.874.874C8 3.52 8 4.08 8 5.2V6M3 6h18m-2 0v11.2c0 1.68 0 2.52-.327 3.162a3 3 0 01-1.311 1.311C16.72 22 15.88 22 14.2 22H9.8c-1.68 0-2.52 0-3.162-.327a3 3 0 01-1.311-1.311C5 19.72 5 18.88 5 17.2V6'


def _rules(rules,*,reject_conflicts=True,allow_empty=False,field_bindings=None):
    minimum=0 if allow_empty else 1
    if not isinstance(rules,list) or not minimum<=len(rules)<=50:
        raise Stop('Native condition stacks require '+str(minimum)+' to 50 ordered rules')
    normalized=[];seen=set()
    for rule in rules:
        if (not isinstance(rule,dict) or set(rule)-{'match','connectors','clauses','effect','target'}
                or not {'match','clauses','effect','target'}.issubset(rule)):
            raise Stop('Every condition stack rule needs its complete predicate, effect and one target')
        valid=group.validate({'action':'native_condition_group',**rule,
            **({'field_bindings':field_bindings} if field_bindings is not None else {})},minimum_clauses=1)
        identity=(*group._predicate_identity(valid),valid['target'])
        if reject_conflicts and identity in seen:
            raise Stop('Duplicate or conflicting condition predicates for the same target require reconciliation')
        seen.add(identity)
        normalized.append({key:valid[key] for key in ('match','clauses','effect','target','connectors') if key in valid})
    return normalized


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','rules','expected_rules','recreate_order','field_bindings'}
            or step.get('action','native_condition_stack')!='native_condition_stack'):
        raise Stop('Unsupported native condition stack')
    bindings=group.condition_bindings(step) if 'field_bindings' in step else None
    value={**deepcopy(step),'rules':_rules(step.get('rules'),allow_empty='expected_rules' in step,field_bindings=bindings)}
    if 'expected_rules' in step:
        value['expected_rules']=_rules(step['expected_rules'],reject_conflicts=False,allow_empty=True,field_bindings=bindings)
    if 'recreate_order' in step:
        order=step['recreate_order'];expected=value.get('expected_rules')
        if (expected is None or not isinstance(order,list) or len(expected)<2
                or len(order)!=len(expected) or any(type(index) is not int for index in order)
                or sorted(order)!=list(range(len(expected)))):
            raise Stop('Explicit condition recreation requires a complete prior stack and one full ordinal permutation')
        if value['rules']!=[expected[index] for index in order]:
            raise Stop('Explicit condition recreation must retain every prior Show/Hide rule unchanged in the requested order')
    return value


def configuration_hash(step):
    plan=validate(step)
    binding=({'expected_rules':plan['expected_rules'],'rules':plan['rules']}
             if 'expected_rules' in plan else plan['rules'])
    if 'recreate_order' in plan:binding['recreate_order']=plan['recreate_order']
    if 'field_bindings' in plan:
        binding={'rules':binding,'field_bindings':plan['field_bindings']}
    return hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _expected(plan):
    return [group._expected(rule)[0] for rule in plan['rules']]


def _empty_state(dialog):
    """The measured loaded-empty drawer, never an inferred absent card list."""
    if (dialog.locator(group.CARD).count()!=0
            or dialog.get_by_text('No existing conditions yet',exact=True).count()!=1
            or dialog.get_by_text("You're free to roam without the rules - at least for now",exact=True).count()!=1):
        raise Stop('Native cleared condition inventory lacks its positive loaded-empty state')
    image=group._one(dialog.get_by_role('img',name='No conditions yet',exact=True),
                     'Native cleared condition empty-state image is unavailable or ambiguous')
    if image.get_attribute('src')!='/assets/no-conditions-13c5d8b2.png':
        raise Stop('Native cleared condition empty-state image changed')


def _delete_card(frame,dialog,current,identity,*,index,inventory=None):
    """Delete one inventoried ordinal through the shared captured confirmation.

    A caller-specific inventory reader can preserve richer outcome records;
    both reads before confirmation and the complete post-delete read use it.
    """
    if type(index) is not int or not 0<=index<len(current):
        raise Stop('Native condition Delete requires an exact existing card ordinal')
    inventory=group._inventory if inventory is None else inventory
    identity()
    if inventory(dialog)!=current:
        raise Stop('Native condition cards changed before the requested tail-card removal')
    # Binding the original drawer by its own save-close descendant keeps it
    # distinct from the second role=dialog introduced by Delete Condition.
    dialogs=frame.get_by_role('dialog')
    drawer=group._one(dialogs.filter(has=frame.locator('#conditional-logic-save-close')),
                      'Native condition delete drawer owner is unavailable or ambiguous')
    if inventory(drawer)!=current:
        raise Stop('Native condition delete drawer differs from the inventoried full stack')
    cards=drawer.locator(group.CARD)
    remove=group._one(cards.nth(index).locator('#delete-condition'),
                      'Native tail-card Delete control changed')
    click(remove)
    heading=frame.get_by_role('heading',name='Delete Condition',exact=True)
    wait_until(lambda:dialogs.count()==2 and heading.count()==1,
               'Native condition Delete confirmation did not appear exactly once')
    confirm=group._one(dialogs.filter(has=heading),
                       'Native condition Delete confirmation owner is ambiguous')
    if (confirm.get_by_text('Are you sure you want to delete this condition?',exact=True).count()!=1
            or confirm.locator('#modal-header-modal-close-btn').count()!=1):
        raise Stop('Native condition Delete confirmation text or close control changed')
    cancel=group._one(confirm.locator('#modal-footer-btn-negative-action'),
                      'Native condition Delete Cancel control changed')
    delete=group._one(confirm.locator('#modal-footer-btn-positive-action'),
                      'Native condition Delete confirmation button changed')
    if (cancel.inner_text().strip()!='Cancel' or delete.inner_text().strip()!='Delete'
            or not delete.is_enabled()):
        raise Stop('Native condition Delete confirmation buttons are unavailable or changed')
    # Opening a confirmation does not authorize deleting a concurrently
    # changed card. Recheck the complete protected inventory before confirm.
    identity()
    if inventory(drawer)!=current:
        raise Stop('Native condition cards changed before Delete confirmation')
    click(delete)
    expected=deepcopy(current[:index]+current[index+1:])
    wait_until(lambda:dialogs.count()==1 and drawer.locator(group.CARD).count()==len(expected),
               'Native condition Delete did not remove exactly one tail card and close confirmation')
    if inventory(drawer)!=expected:
        raise Stop('Native condition Delete changed a retained card or removed the wrong card')
    if not expected:_empty_state(drawer)
    return expected


def _delete_tail(frame,dialog,current,identity):
    """Delete exactly the inventoried final Show/Hide card."""
    return _delete_card(frame,dialog,current,identity,index=len(current)-1)


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
            group._write_clause_value(modal,index,clause,writer=fill,frame=frame)
        if index<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=index+1:
                raise Stop('Native condition row append connector count changed')
            connector=group._one(joins.nth(index).locator('[data-name="'+group._connectors(rule)[index]+'"]'),
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
    while count>len(rule['clauses']):
        identity()
        count=_remove_tail(modal,before_rule,count,identity)
    for row,clause in enumerate(rule['clauses']):
        identity()
        if modal.locator('[id^="selectedField-"]').count()!=count:
            raise Stop('Native condition edit row inventory changed')
        group._choose(frame,'#selectedField-'+str(row),clause['if_field'])
        group._choose(frame,'#selectedOperation-'+str(row),clause['operator'])
        if clause['operator'] in group.BINARY:
            group._write_clause_value(modal,row,clause,writer=fill,frame=frame)
        if row<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=count:raise Stop('Native condition edit connector count changed')
            connector=joins.nth(row)
            wanted=group._connectors(rule)[row]
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


def _remove_tail(modal,before_rule,count,identity,*,read_state=None):
    """Remove one captured noninitial predicate row and prove its exact prefix."""
    if type(count) is not int or count<2:
        raise Stop('Native predicate removal never deletes the initial If row')
    read_state=group._modal_state if read_state is None else read_state
    current={**deepcopy(before_rule),'clauses':deepcopy(before_rule['clauses'][:count])}
    if 'connectors' in current:current['connectors']=current['connectors'][:count-1]
    read_state(modal,current)
    source=group._one(modal.locator('#selectedField-'+str(count-1)),
                      'Native tail predicate source changed')
    row=source.locator('..');owner=row.locator('..')
    if (not {'mb-8','flex','gap-x-2','px-0.5'}.issubset((row.get_attribute('class') or '').split())
            or not {'mb-2','flex','flex-col','gap-y-2','text-base'}.issubset((owner.get_attribute('class') or '').split())
            or owner.locator('[id^="selectedField-"]').count()!=1
            or owner.locator('[id^="selectedOperation-"]').count()!=1):
        raise Stop('Native removable predicate row owner changed')
    trash=group._one(owner.locator(':scope > div.flex.items-center.justify-between > svg'),
                     'Native tail predicate delete icon is missing or ambiguous')
    if not {'mr-3','h-4','w-4','cursor-pointer','text-error-700'}.issubset(
            (trash.get_attribute('class') or '').split()):
        raise Stop('Native predicate delete icon class identity changed')
    path=group._one(trash.locator('path'),'Native predicate trash path is ambiguous')
    if path.get_attribute('d')!=_ROW_DELETE_PATH:
        raise Stop('Native predicate delete icon differs from the captured trash control')
    identity();click(trash)
    wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==count-1
               and modal.locator('#selectedField-'+str(count-1)).count()==0
               and modal.locator('#selectedOperation-'+str(count-1)).count()==0
               and modal.locator('#inputValue-'+str(count-1)).count()==0,
               'Native tail predicate did not remove exactly one complete row')
    expected={**deepcopy(before_rule),'clauses':deepcopy(before_rule['clauses'][:count-1])}
    if 'connectors' in expected:expected['connectors']=expected['connectors'][:count-2]
    read_state(modal,expected)
    return count-1


def _recreate_order(frame,dialog,plan,current,identity):
    """Replace only the changed suffix using already captured native controls.

    The caller's complete expected stack and explicit ordinal permutation are
    checked before this function. Never reuse this for rich outcome cards or
    infer permission to delete/recreate from an ordinary desired rule list.
    Any partial failure propagates before drawer/outer Save; the parent intent
    journal remains uncertain and requires reconciliation rather than retry.
    """
    wanted=_expected(plan)
    if current==wanted:return current
    expected=_expected({'rules':plan['expected_rules']})
    if current!=expected:
        raise Stop('Native condition recreation inventory differs from the complete expected previous stack')
    prefix=0
    while prefix<len(current) and current[prefix]==wanted[prefix]:prefix+=1
    while len(current)>prefix:
        current=_delete_tail(frame,dialog,current,identity)
    for rule in plan['rules'][prefix:]:
        identity()
        if group._inventory(dialog)!=current:
            raise Stop('Native condition stack changed during explicit order recreation')
        current=_author(frame,dialog,rule,current,identity)
    return current


def configure(page,step):
    plan=validate(step)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():
        raise Stop('Native condition stack form identity is missing or ambiguous')
    name,editor_url=read_editor_title(title),page.url

    def identity():
        if page.url!=editor_url or title.count()!=1 or read_editor_title(title)!=name:
            raise Stop('Native condition stack form identity changed')

    def open_conditions():
        identity()
        _close_initial(frame)
        click(frame.get_by_role('tab',name='Edit',exact=True))
        click(frame.get_by_role('button',name='Open Conditional Logic',exact=True))
        dialog=group._one(frame.get_by_role('dialog'),'Native Conditions drawer is missing or ambiguous')
        return dialog

    group._preflight_fields(frame,plan,identity)
    dialog=open_conditions()
    before,wanted=group._inventory(dialog),_expected(plan)
    current=before
    if 'recreate_order' in plan:
        current=_recreate_order(frame,dialog,plan,current,identity)
    elif 'expected_rules' in plan:
        expected=_expected({'rules':plan['expected_rules']})
        if before!=expected:
            raise Stop('Native condition edit inventory differs from the complete expected previous stack')
        while len(current)>len(wanted):
            current=_delete_tail(frame,dialog,current,identity)
        for index,(previous,rule) in enumerate(zip(plan['expected_rules'],plan['rules'])):
            if current[index]!=wanted[index]:
                current=_edit(frame,dialog,index,previous,rule,current,identity)
        for rule in plan['rules'][len(plan['expected_rules']):]:
            if group._inventory(dialog)!=current:
                raise Stop('Native condition stack changed before an expected-inventory append')
            current=_author(frame,dialog,rule,current,identity)
    else:
        if len(before)>len(wanted) or before!=wanted[:len(before)]:
            raise Stop('Existing native condition stack is not the exact authored prefix; reconcile before writing')
        for rule in plan['rules'][len(before):]:
            if group._inventory(dialog)!=current:
                raise Stop('Native condition stack changed after full preflight')
            current=_author(frame,dialog,rule,current,identity)
    if group._inventory(dialog)!=wanted:
        raise Stop('Native full condition stack differs before drawer Save')
    if not wanted:_empty_state(dialog)
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
    group._preflight_fields(frame,plan,identity)
    dialog=open_conditions()
    if group._inventory(dialog)!=wanted:
        raise Stop('Native condition stack did not persist after independent reopen; do not repeat the write')
    if not wanted:_empty_state(dialog)
    click(group._one(dialog.locator('#conditional-logic-save-close'),
                     'Reopened native Conditions save-close changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return {'status':'CONDITION_STACK_SAVED_AND_REOPENED' if changed else 'CONDITION_STACK_REUSED_AND_REOPENED',
        'kind':'form_condition_stack','editor_url':page.url,'rule_count':len(plan['rules']),
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False}
