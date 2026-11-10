"""Ordered native field, redirect, message and disqualification conditions.

Each saved card remains one native effect. A complete authored ordered stack
and exact existing prefix protect unrelated conditions. An explicit complete
expected_rules inventory also permits removal of identified cards or same-count
in-place edits through the captured editor. Explicit non-message permutations recreate only the changed suffix using captured
Delete and author controls. Rich-message reordering still requires markup-aware
authoring; changing effect families uses explicit removal and append. Native rich-message
card markup is hashed and preserved through append and independent reopen.
The parent runner owns tenant checks, writer lease and uncertain-write journal.
"""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from . import form_conditions as group
    from . import form_condition_stack as stack
    from .assessments import reopen_editor, read_editor_title
    from .field_placement import _close_initial
    from .skill6_playwright import Stop, click, fill, form_builder, wait_until
    from .form_submission import validate as validate_submission
else:
    import form_conditions as group
    import form_condition_stack as stack
    from assessments import reopen_editor, read_editor_title
    from field_placement import _close_initial
    from skill6_playwright import Stop, click, fill, form_builder, wait_until
    from form_submission import validate as validate_submission


REDIRECT='Redirect to URL'
MESSAGE='Display custom message'
DISQUALIFY='Disqualify lead'
SHOW_MESSAGE='Show custom message'
EFFECTS=frozenset(('Show Field','Hide Field',REDIRECT,MESSAGE,DISQUALIFY))
RTE='#richTextEditor .tiptap.ProseMirror[contenteditable="true"]'
_NO_MAPPING=object()


def _url(value):
    try:
        return validate_submission({'mode':REDIRECT,'redirect_url':value})['redirect_url']
    except ValueError:
        raise Stop('Conditional redirect must be an explicit credential-free HTTPS URL') from None


def _message(value):
    if (not isinstance(value,str) or not value.strip() or len(value)>50000
            or any(ord(char)<32 and char not in '\n\r\t' for char in value)):
        raise Stop('Conditional message requires authored plain text within the script limit')
    return value.replace('\r\n','\n').replace('\r','\n').strip()


def _rule(value,*,field_bindings=None):
    if not isinstance(value,dict) or not {'match','clauses','effect'}.issubset(value):
        raise Stop('Each native outcome rule requires an explicit complete predicate and effect')
    effect=value['effect']
    if not isinstance(effect,str) or effect not in EFFECTS:
        raise Stop('Native condition effect was not captured')
    predicate=group.validate({'action':'native_condition_group','match':value['match'],
        'clauses':value['clauses'],'effect':'Hide Field','target':'Phone',
        **({'connectors':value['connectors']} if 'connectors' in value else {}),
        **({'field_bindings':field_bindings} if field_bindings is not None else {})},minimum_clauses=1)
    result={'match':predicate['match'] if len(predicate['clauses'])>1 else 'all',
            'clauses':predicate['clauses'],'effect':effect}
    required={'match','clauses','effect'}
    if 'connectors' in predicate:
        required.add('connectors');result['connectors']=predicate['connectors']
    if effect in ('Show Field','Hide Field'):
        required.add('target')
        targets=group.TARGETS|{field['label'] for field in (field_bindings or [])}
        if not isinstance(value.get('target'),str) or value['target'] not in targets:
            raise Stop('Native field outcome requires one captured target')
        result['target']=value['target']
    elif effect==REDIRECT:
        required.add('redirect_url');result['redirect_url']=_url(value.get('redirect_url'))
    elif effect==MESSAGE:
        required.add('message');result['message']=_message(value.get('message'))
    else:
        required.add('mode')
        if value.get('mode') not in (SHOW_MESSAGE,REDIRECT):
            raise Stop('Disqualify lead requires an explicit captured message/redirect mode')
        result['mode']=value['mode']
        if value['mode']==REDIRECT:
            required.add('redirect_url');result['redirect_url']=_url(value.get('redirect_url'))
        else:
            required.add('message');result['message']=_message(value.get('message'))
    if set(value)!=required:
        raise Stop('Native outcome contains missing or ignored effect properties')
    return result


def _rules(rules,*,allow_empty=False,reject_conflicts=True,field_bindings=None):
    minimum=0 if allow_empty else 1
    if not isinstance(rules,list) or not minimum<=len(rules)<=50:
        raise Stop('Native conditional outcomes require '+str(minimum)+' to 50 ordered rules')
    normalized=[];seen=set()
    for value in rules:
        rule=_rule(value,field_bindings=field_bindings)
        # Show/Hide on the same target is one conflict domain. Other native
        # effects are distinct; retain their explicit authored order.
        target=('field',rule['target']) if rule['effect'] in ('Show Field','Hide Field') else ('outcome',rule['effect'])
        identity=(*group._predicate_identity(rule),target)
        if reject_conflicts and identity in seen:
            raise Stop('Duplicate/conflicting predicates for the same native effect require reconciliation')
        seen.add(identity);normalized.append(rule)
    return normalized


def _retained_indices(expected,wanted):
    """Resolve a removal-only subset before any UI operation.

    Exact duplicate prior rules cannot identify which rich-message card the
    owner meant to retain. Never choose one of those cards implicitly.
    """
    indices=[]
    for rule in wanted:
        matches=[index for index,value in enumerate(expected) if value==rule]
        if len(matches)!=1:
            raise Stop('Explicit outcome removal requires one unambiguous unchanged prior card per retained rule; additions and edits are separate')
        indices.append(matches[0])
    if indices!=sorted(indices):
        raise Stop('Explicit outcome removal must preserve the existing card order')
    return indices


def _reconciliation(expected,wanted,source_indices=_NO_MAPPING):
    """Separate captured removal and editing from unsupported reordering.

    The existing full-stack contract identifies the prior owner of each edit.
    Moving an unchanged prior rule is never implemented by writing its copy
    into another card; a native reorder needs a captured reorder control.
    """
    if source_indices is not _NO_MAPPING:
        if not isinstance(source_indices,list) or len(source_indices)!=len(wanted):
            raise Stop('Outcome source_indices must identify exactly one prior card or new tail card for every desired rule')
        seen=set();last=-1;appending=False
        for index,rule in zip(source_indices,wanted):
            if index is None:
                appending=True
                if rule in expected:
                    raise Stop('Recreating an unchanged prior outcome at a new position is not native card reordering')
                continue
            if type(index) is not int or index<0 or index>=len(expected) or index in seen:
                raise Stop('Outcome source_indices contains an invalid or duplicate prior card ordinal')
            if appending or index<=last:
                raise Stop('Existing outcome card ordinals must retain their order before genuinely new tail cards')
            previous=expected[index]
            if rule!=previous:
                if rule in expected:
                    raise Stop('Moving an unchanged prior rule by overwriting another card is not native reordering')
                if _tile(previous)!=_tile(rule):
                    raise Stop('An existing outcome edit must retain its native effect family')
            seen.add(index);last=index
        return 'mapped',list(source_indices)
    try:
        return 'remove',_retained_indices(expected,wanted)
    except Stop:
        if len(expected)!=len(wanted):
            raise Stop('Outcome replacement with a different card count requires explicit source_indices for existing owners and new tail cards') from None
    for index,(previous,rule) in enumerate(zip(expected,wanted)):
        if rule==previous:continue
        if rule in expected:
            raise Stop('Existing outcome card reordering requires a captured native order control')
        if _tile(previous)!=_tile(rule):
            raise Stop('Existing outcome edits must retain the native effect family; remove and append a different effect explicitly')
    return 'edit',list(range(len(expected)))


def _validate_recreation(plan):
    """Explicit unchanged permutation using captured deletion and authoring.

    Rich-message cards require markup-aware reauthoring and are never flattened.
    """
    expected=plan['expected_rules'];order=plan['recreate_order']
    if ('source_indices' in plan or not isinstance(order,list)
            or len(order)!=len(expected) or any(type(i) is not int for i in order)
            or sorted(order)!=list(range(len(expected)))
            or plan['rules']!=[expected[i] for i in order]):
        raise Stop('Outcome recreation requires one complete unchanged ordinal permutation')
    if any('message' in rule for rule in expected):
        raise Stop('Rich-message outcome recreation requires captured markup-preserving authoring')


def _recreate_order(frame,dialog,plan,current,identity,inventory):
    wanted=plan['rules']
    if [record['rule'] for record in current]==wanted:return current
    if [record['rule'] for record in current]!=plan['expected_rules']:
        raise Stop('Native outcome recreation differs from complete previous inventory')
    prefix=0
    while prefix<len(current) and current[prefix]['rule']==wanted[prefix]:prefix+=1
    for index in reversed(range(prefix,len(current))):
        current=stack._delete_card(frame,dialog,current,identity,index=index,inventory=inventory)
    for rule in wanted[prefix:]:
        identity()
        if inventory(dialog)!=current:
            raise Stop('Native outcomes changed during explicit order recreation')
        current=_author(frame,dialog,rule,current,identity,inventory=inventory)
    return current


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','rules','expected_rules','source_indices','recreate_order','field_bindings'}
            or step.get('action','native_condition_outcomes')!='native_condition_outcomes'):
        raise Stop('Unsupported native conditional outcome stack')
    bindings=group.condition_bindings(step) if 'field_bindings' in step else None
    plan={**deepcopy(step),'rules':_rules(step.get('rules'),allow_empty='expected_rules' in step,field_bindings=bindings)}
    if 'expected_rules' in step:
        plan['expected_rules']=_rules(step['expected_rules'],allow_empty=True,reject_conflicts=False,field_bindings=bindings)
        if 'recreate_order' in plan:
            _validate_recreation(plan)
        else:
            _reconciliation(plan['expected_rules'],plan['rules'],step.get('source_indices',_NO_MAPPING))
    elif 'recreate_order' in step:
        raise Stop('Outcome recreation requires a complete expected_rules inventory')
    elif 'source_indices' in step:
        raise Stop('Outcome source_indices requires the complete expected_rules inventory')
    return plan


def configuration_hash(step):
    plan=validate(step)
    binding=({'expected_rules':plan['expected_rules'],'rules':plan['rules']}
             if 'expected_rules' in plan else plan['rules'])
    if 'source_indices' in plan:binding['source_indices']=plan['source_indices']
    if 'recreate_order' in plan:binding['recreate_order']=plan['recreate_order']
    if 'field_bindings' in plan:
        binding={'rules':binding,'field_bindings':plan['field_bindings']}
    return hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _one(node,reason):
    try:node.wait_for(state='visible',timeout=45000)
    except Exception:raise Stop(reason) from None
    if node.count()!=1:raise Stop(reason)
    return node


def _predicate(card):
    rows=card.locator('.condition-summary-row')
    if not 1<=rows.count()<=20:
        raise Stop('Native outcome card has missing or excessive predicate rows')
    clauses=[];joins=[]
    for index in range(rows.count()):
        tokens=group._tokens(rows.nth(index))
        if not isinstance(tokens,list) or len(tokens) not in (3,4) or any(not isinstance(token,str) for token in tokens):
            raise Stop('Native outcome predicate summary structure changed')
        if tokens[0] not in (('If',) if index==0 else ('And','Or')):
            raise Stop('Native outcome predicate connector changed')
        if index:joins.append(tokens[0])
        clause={'if_field':tokens[1],'operator':tokens[2]}
        if len(tokens)==4:clause['value']=tokens[3]
        clauses.append(clause)
    if len(set(joins))>1:
        return {'match':'mixed','connectors':[join.lower() for join in joins],'clauses':clauses}
    return {'match':'any' if joins and joins[0]=='Or' else 'all','clauses':clauses}


def _inventory(dialog,*,field_bindings=None):
    cards=dialog.locator(group.CARD)
    empty=dialog.get_by_text('No existing conditions yet',exact=True)
    if not cards.count():
        if empty.count()!=1:raise Stop('Native condition inventory is unavailable; no inferred empty set')
        return []
    if empty.count():raise Stop('Native condition empty marker conflicts with displayed cards')
    result=[]
    for index in range(cards.count()):
        card=cards.nth(index)
        if card.locator('#edit-condition').count()!=1 or card.locator('#delete-condition').count()!=1:
            raise Stop('Native outcome card action inventory changed')
        effect=_one(card.locator('.text-sm.font-semibold'),'Native outcome heading changed').inner_text().strip()
        outcome=_one(card.locator(group.OUTCOME),'Native outcome summary row changed')
        spans=outcome.locator(':scope > span')
        if spans.count()!=2:raise Stop('Native outcome requires its exact mode and value spans')
        mode=spans.nth(0).inner_text().replace('\u00a0',' ').strip()
        text=spans.nth(1).inner_text().strip()
        rule={**_predicate(card),'effect':effect}
        rich=None
        if effect in ('Show Field','Hide Field'):
            if mode!=effect:raise Stop('Native field outcome summary disagrees with its heading')
            rule['target']=text
        elif effect==REDIRECT:
            if mode!=REDIRECT:raise Stop('Native redirect summary mode changed')
            rule['redirect_url']=text
        elif effect==MESSAGE:
            if mode!='SHOW':raise Stop('Native custom-message summary mode changed')
            rule['message']=text;rich=spans.nth(1).inner_html()
        elif effect==DISQUALIFY:
            if mode==REDIRECT:rule.update(mode=REDIRECT,redirect_url=text)
            elif mode=='SHOW':rule.update(mode=SHOW_MESSAGE,message=text);rich=spans.nth(1).inner_html()
            else:raise Stop('Native disqualification summary mode is unknown')
        else:raise Stop('Unknown existing native outcome requires reconciliation before append')
        canonical=_rule(rule,field_bindings=field_bindings)
        result.append({'rule':canonical,'rich_html_sha256':(
            hashlib.sha256(rich.encode()).hexdigest() if isinstance(rich,str) else None)})
    return result


def _tile(rule):
    return 'Show/Hide Fields' if rule['effect'] in ('Show Field','Hide Field') else rule['effect']


def _disqualify_mode(modal):
    selected=_one(modal.locator('#disqualify-action .n-base-selection-input'),
                  'Native disqualification mode selector changed')
    text=_one(selected.locator('.n-base-selection-input__content'),
              'Native disqualification mode text changed').inner_text().strip()
    if selected.get_attribute('title')!=text or text not in (SHOW_MESSAGE,REDIRECT):
        raise Stop('Native disqualification mode is unavailable or inconsistent')
    return text,selected


def _effect_value(frame,modal,rule,*,write,identity=lambda:None):
    if rule['effect'] in ('Show Field','Hide Field'):
        if write:
            identity();group._choose(frame,'#showHideFieldType',rule['effect'])
            identity();group._choose(frame,'#selectedFieldShowHide',rule['target'])
        return
    if rule['effect']==DISQUALIFY:
        current,selected=_disqualify_mode(modal)
        if write and current!=rule['mode']:
            identity();click(selected)
            option=frame.locator('.n-base-select-option:visible').get_by_text(rule['mode'],exact=True)
            click(_one(option,'Native disqualification mode choice changed'))
            wait_until(lambda:_disqualify_mode(modal)[0]==rule['mode'],'Native disqualification mode did not stick')
        if _disqualify_mode(modal)[0]!=rule['mode']:
            raise Stop('Native disqualification mode differs from its authored setting')
    if 'redirect_url' in rule:
        control=_one(modal.locator('#redirectToUrlInput input'),'Native conditional redirect input changed')
        if control.get_attribute('placeholder')!='https://www.example.com':
            raise Stop('Native conditional redirect input placeholder changed')
        if write:identity();fill(control,rule['redirect_url'])
        if control.input_value()!=rule['redirect_url']:
            raise Stop('Native conditional redirect did not accept its exact authored HTTPS URL')
    else:
        control=_one(modal.locator(RTE),'Native conditional plain-message editor changed')
        if write:identity();fill(control,rule['message'])
        if _message(control.inner_text())!=rule['message']:
            raise Stop('Native conditional message differs from its authored plain text')
        if write and control.locator('a,script,iframe').count():
            raise Stop('Native plain-message editor retained an unapproved embedded element')


def _predicate_modal(modal,rule):
    count=len(rule['clauses'])
    if (modal.locator('[id^="selectedField-"]').count()!=count
            or modal.locator('[id^="selectedOperation-"]').count()!=count):
        raise Stop('Native outcome modal predicate row count differs')
    for index,clause in enumerate(rule['clauses']):
        if (group._selected(modal.locator('#selectedField-'+str(index)))!=clause['if_field']
                or group._selected(modal.locator('#selectedOperation-'+str(index)))!=clause['operator']):
            raise Stop('Native outcome modal source/operator differs')
        if clause['operator'] in group.UNARY:
            group._value_input(modal,index,unary=True)
        elif group._value_input(modal,index).input_value()!=clause['value']:
            raise Stop('Native outcome predicate value differs')
    joins=modal.locator('.n-tabs')
    if joins.count()!=count:raise Stop('Native outcome connector count differs')
    for index in range(count):
        selected=_one(joins.nth(index).locator('.n-tabs-tab--active'),'Native outcome connector is ambiguous')
        if selected.get_attribute('data-name')!=('then' if index==count-1 else group._connectors(rule)[index]):
            raise Stop('Native outcome AND/OR connector differs')


def _author(frame,dialog,rule,prefix,identity,*,inventory=None):
    inventory=_inventory if inventory is None else inventory
    identity()
    # A redirect summary card repeats the Redirect to URL text. The measured
    # tile lives under the drawer heading, so never use global text matching.
    tile=frame.get_by_role('heading').get_by_text(_tile(rule),exact=True)
    click(_one(tile,'Native outcome tile is missing or ambiguous in the heading'))
    modal=_one(frame.get_by_role('dialog'),'Native outcome rule editor is ambiguous')
    _one(modal.locator('.hl-modal-heading').get_by_text(_tile(rule),exact=True),
         'Native outcome modal heading differs from the selected tile')
    for index,clause in enumerate(rule['clauses']):
        identity()
        if modal.locator('[id^="selectedField-"]').count()!=index+1:
            raise Stop('Native outcome rule has unrelated or missing source rows')
        group._choose(frame,'#selectedField-'+str(index),clause['if_field'])
        group._choose(frame,'#selectedOperation-'+str(index),clause['operator'])
        if clause['operator'] in group.BINARY:
            value=group._value_input(modal,index)
            fill(value,clause['value'])
        if index<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=index+1:raise Stop('Native outcome append connector count changed')
            choice=joins.nth(index).locator('[data-name="'+group._connectors(rule)[index]+'"]')
            click(_one(choice,'Native outcome append connector is ambiguous'))
            wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==index+2,
                       'Native outcome predicate did not append exactly once')
    _effect_value(frame,modal,rule,write=True,identity=identity)
    _predicate_modal(modal,rule)
    if rule['effect'] in ('Show Field','Hide Field'):group._modal_state(modal,rule)
    else:_effect_value(frame,modal,rule,write=False)
    identity()
    save=_one(modal.locator('#modal-footer-btn-positive-action'),'Native outcome modal Save changed')
    if not save.is_enabled():raise Stop('Native outcome rule remains invalid; Save not attempted')
    click(save)
    wait_until(lambda:dialog.locator(group.CARD).count()==len(prefix)+1,
               'Native outcome card did not append once')
    current=inventory(dialog)
    if (len(current)!=len(prefix)+1 or current[:-1]!=prefix or current[-1]['rule']!=rule):
        raise Stop('Native outcome append changed a prior card, authored order or outcome value')
    return current


def _modal_state(frame,modal,rule):
    _predicate_modal(modal,rule)
    if rule['effect'] in ('Show Field','Hide Field'):
        group._modal_state(modal,rule)
    else:
        _effect_value(frame,modal,rule,write=False)


def _edit(frame,dialog,index,before_rule,rule,current,identity,*,inventory=None):
    """Edit one exact existing outcome while preserving every sibling record."""
    inventory=_inventory if inventory is None else inventory
    identity()
    if inventory(dialog)!=current:
        raise Stop('Native outcome cards changed immediately before the requested edit')
    cards=dialog.locator(group.CARD)
    if cards.count()!=len(current):raise Stop('Native outcome card count changed before edit')
    click(_one(cards.nth(index).locator('#edit-condition'),'Native outcome card Edit changed'))
    modal=_one(frame.get_by_role('dialog'),'Native outcome edit dialog is ambiguous')
    _one(modal.locator('.hl-modal-heading').get_by_text(_tile(before_rule),exact=True),
         'Native existing outcome editor heading differs from the inventoried card')
    # Before the first mutation, verify the entire persisted predicate and
    # current effect value rather than accepting only the summary card text.
    _modal_state(frame,modal,before_rule)
    count=len(before_rule['clauses'])
    while count>len(rule['clauses']):
        identity()
        count=stack._remove_tail(modal,before_rule,count,identity,
            read_state=lambda node,snapshot:_modal_state(frame,node,snapshot))
    for row,clause in enumerate(rule['clauses']):
        identity()
        if modal.locator('[id^="selectedField-"]').count()!=count:
            raise Stop('Native outcome edit predicate inventory changed')
        group._choose(frame,'#selectedField-'+str(row),clause['if_field'])
        group._choose(frame,'#selectedOperation-'+str(row),clause['operator'])
        if clause['operator'] in group.BINARY:
            control=group._value_input(modal,row)
            fill(control,clause['value'])
            if control.input_value()!=clause['value']:
                raise Stop('Native outcome edit ignored the authored predicate value')
        if row<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=count:raise Stop('Native outcome edit connector inventory changed')
            connector=joins.nth(row)
            active=_one(connector.locator('.n-tabs-tab--active'),'Native outcome edited connector is ambiguous')
            wanted=group._connectors(rule)[row]
            appending=row==count-1
            if appending or active.get_attribute('data-name')!=wanted:
                click(_one(connector.locator('[data-name="'+wanted+'"]'),'Native outcome edited AND/OR control changed'))
                expected=count+int(appending)
                wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==expected,
                           'Native outcome edited connector changed the wrong row count')
                count=expected
    previous_value={key:value for key,value in before_rule.items()
                    if key not in ('match','clauses','connectors')}
    desired_value={key:value for key,value in rule.items()
                   if key not in ('match','clauses','connectors')}
    effect_changed=previous_value!=desired_value
    # Predicate-only edits must preserve existing rich text exactly. Filling
    # unchanged copy would silently flatten the saved message formatting.
    if effect_changed:_effect_value(frame,modal,rule,write=True,identity=identity)
    _modal_state(frame,modal,rule)
    identity()
    save=_one(modal.locator('#modal-footer-btn-positive-action'),'Native existing outcome Save changed')
    if not save.is_enabled():raise Stop('Native edited outcome is invalid; Save not attempted')
    click(save)
    wait_until(lambda:modal.locator('#modal-footer-btn-positive-action').count()==0
               or not modal.locator('#modal-footer-btn-positive-action').is_visible(),
               'Native existing outcome edit modal did not close')
    wait_until(lambda:dialog.locator(group.CARD).count()==len(current),
               'Native existing outcome edit changed the card count')
    after=inventory(dialog)
    if (len(after)!=len(current) or after[:index]!=current[:index] or after[index+1:]!=current[index+1:]
            or after[index]['rule']!=rule):
        raise Stop('Native existing outcome edit changed a sibling, card order or authored value')
    if not effect_changed and after[index]['rich_html_sha256']!=current[index]['rich_html_sha256']:
        raise Stop('Native predicate-only outcome edit changed protected message markup')
    return after


def configure(page,step):
    plan=validate(step)
    frame=form_builder(page)
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or not read_editor_title(title).strip():raise Stop('Native outcome form identity is unavailable')
    name,editor_url=read_editor_title(title),page.url
    def identity():
        if page.url!=editor_url or title.count()!=1 or read_editor_title(title)!=name:
            raise Stop('Native outcome form identity changed')
    def open_conditions():
        identity();_close_initial(frame)
        click(frame.get_by_role('tab',name='Edit',exact=True))
        click(frame.get_by_role('button',name='Open Conditional Logic',exact=True))
        return _one(frame.get_by_role('dialog'),'Native outcome Conditions drawer is ambiguous')
    bindings=plan.get('field_bindings')
    inventory=(lambda dialog:_inventory(dialog,field_bindings=bindings)) if bindings is not None else _inventory
    reader_options={'inventory':inventory} if bindings is not None else {}
    group._preflight_fields(frame,plan,identity)
    dialog=open_conditions()
    before=inventory(dialog);wanted=plan['rules']
    current=before
    if 'recreate_order' in plan:
        current=_recreate_order(frame,dialog,plan,current,identity,inventory)
    elif 'expected_rules' in plan:
        actual=[record['rule'] for record in before]
        if actual!=wanted:
            if actual!=plan['expected_rules']:
                raise Stop('Existing native outcomes differ from the complete expected previous inventory; reconcile before removal')
            _,indices=_reconciliation(plan['expected_rules'],wanted,plan.get('source_indices',_NO_MAPPING))
            retained={index for index in indices if index is not None}
            for index in reversed(range(len(before))):
                if index not in retained:
                    current=stack._delete_card(frame,dialog,current,identity,index=index,inventory=inventory)
            for index,(previous_index,rule) in enumerate(zip(indices,wanted)):
                if previous_index is None:
                    if inventory(dialog)!=current:
                        raise Stop('Native outcome stack changed before an explicit expected-inventory append')
                    current=_author(frame,dialog,rule,current,identity,**reader_options)
                elif plan['expected_rules'][previous_index]!=rule:
                    current=_edit(frame,dialog,index,plan['expected_rules'][previous_index],rule,current,identity,**reader_options)
        if not current:stack._empty_state(dialog)
    else:
        if len(before)>len(wanted) or [record['rule'] for record in before]!=wanted[:len(before)]:
            raise Stop('Existing native outcomes are not the exact authored prefix; reconcile before writing')
        for rule in wanted[len(before):]:
            if inventory(dialog)!=current:raise Stop('Native outcome stack changed after full preflight')
            current=_author(frame,dialog,rule,current,identity,**reader_options)
    if inventory(dialog)!=current or [record['rule'] for record in current]!=wanted:
        raise Stop('Native outcome stack differs before drawer Save')
    identity();click(_one(dialog.locator('#conditional-logic-save-close'),'Native outcome drawer Save changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    changed=before!=current
    if changed:
        identity();save=_one(frame.get_by_role('button',name='Save',exact=True),'Native outcome outer Save changed')
        click(save);group._wait_for_form_save(page,save)
    reopen_editor(page,'form',name,editor_url)
    frame=form_builder(page)
    group._preflight_fields(frame,plan,identity)
    dialog=open_conditions()
    if inventory(dialog)!=current:
        raise Stop('Native outcomes or protected message markup did not persist after independent reopen; do not repeat the write')
    if not current:stack._empty_state(dialog)
    click(_one(dialog.locator('#conditional-logic-save-close'),'Reopened native outcome drawer Save changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return {'status':'CONDITION_OUTCOMES_SAVED_AND_REOPENED' if changed else 'CONDITION_OUTCOMES_REUSED_AND_REOPENED',
        'kind':'form_condition_outcomes','editor_url':page.url,'rule_count':len(wanted),
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False,'disqualification_executed':False}


def validate_receipt(result,step):
    plan=validate(step)
    if (not isinstance(result,dict)
            or result.get('status') not in ('CONDITION_OUTCOMES_SAVED_AND_REOPENED','CONDITION_OUTCOMES_REUSED_AND_REOPENED')
            or result.get('kind')!='form_condition_outcomes'
            or type(result.get('rule_count')) is not int or result['rule_count']!=len(plan['rules'])
            or result.get('configuration_sha256')!=configuration_hash(step)
            or result.get('independent_readback')!='VERIFIED'
            or any(result.get(key) is not False for key in (
                'behavior_verified','submission_verified','disqualification_executed'))):
        raise Stop('Native conditional outcome receipt is unbound or overclaims executed lead behavior')
    return True
