"""Ordered native field, redirect, message and disqualification conditions.

Each saved card remains one native effect. A complete authored ordered stack
and exact existing prefix protect unrelated conditions. An explicit complete
expected_rules inventory also permits removal of identified cards or same-count
in-place edits through the captured editor. Explicit permutations recreate only the
changed suffix using captured Delete and author controls. Plain single-paragraph
message cards retain their exact native markup hash; formatted messages require
markup-aware authoring. Changing effect families uses explicit removal and append. Native rich-message
card markup is hashed and preserved through append and independent reopen.
The parent runner owns tenant checks, writer lease and uncertain-write journal.
"""
from copy import deepcopy
import hashlib
from html import escape
import json
import re
from urllib.parse import urlsplit

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
JUMP='Jump To'
EFFECTS=frozenset(('Show Field','Hide Field',REDIRECT,MESSAGE,DISQUALIFY,JUMP))
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


def _message_from_native(text,markup):
    """Normalize only captured paragraph boundaries, retaining raw markup hashes."""
    if __package__:
        from .condition_message_markup import parse
    else:
        from condition_message_markup import parse
    try:paragraphs=parse(markup)
    except Stop:return _message(text)
    parts=[''.join(run[0] for run in paragraph) for paragraph in paragraphs]
    rendered=_message(text)
    if rendered not in ('\n'.join(parts),'\n\n'.join(parts)):
        raise Stop('Native conditional message text and protected markup disagree')
    return _message('\n'.join(parts))


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
    elif effect==JUMP:
        required.add('target_slide')
        target=value.get('target_slide')
        if not isinstance(target,str) or not re.fullmatch(r'P[1-9][0-9]* - .+',target) or target!=target.strip() or any(ord(c)<32 for c in target):
            raise Stop('Survey Jump To requires an exact numbered slide label')
        result['target_slide']=target
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
    if (source_indices is _NO_MAPPING and len(wanted)>len(expected)
            and wanted[:len(expected)]==expected):
        return 'mapped',list(range(len(expected)))+[None]*(len(wanted)-len(expected))
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

    Message markup is preflighted from the actual native inventory before deletion.
    """
    expected=plan['expected_rules'];order=plan['recreate_order']
    if ('source_indices' in plan or not isinstance(order,list)
            or len(order)!=len(expected) or any(type(i) is not int for i in order)
            or sorted(order)!=list(range(len(expected)))
            or plan['rules']!=[expected[i] for i in order]):
        raise Stop('Outcome recreation requires one complete unchanged ordinal permutation')


def _matches_message_markup(dialog,index,record,markup):
    if __package__:
        from .condition_message_markup import comparable
    else:
        from condition_message_markup import comparable
    card=_one(dialog.locator(group.CARD).nth(index),'Native message comparison card changed')
    body=_one(card.locator(group.OUTCOME),'Native message comparison outcome changed').locator(':scope > span')
    if body.count()!=2:raise Stop('Native message comparison summary owner changed')
    actual=body.nth(1).inner_html()
    return (hashlib.sha256(actual.encode()).hexdigest()==record['rich_html_sha256']
            and comparable(actual)==comparable(markup))


def _recreate_order(frame,dialog,plan,current,identity,inventory):
    wanted=plan['rules']
    if [record['rule'] for record in current]==wanted:return current
    if [record['rule'] for record in current]!=plan['expected_rules']:
        raise Stop('Native outcome recreation differs from complete previous inventory')
    prefix=0
    while prefix<len(current) and current[prefix]['rule']==wanted[prefix]:prefix+=1
    original=deepcopy(current)
    # Preflight every changed message before deleting the first card. The
    # existing literal writer remains the fast path for one plain paragraph.
    markup_by_source={}
    for index,record in enumerate(original[prefix:],start=prefix):
        if 'message' not in record['rule']:continue
        message=record['rule']['message']
        plain='<p>'+escape(message,quote=False)+'</p>'
        if (not any(char in message for char in '\n\r\t')
                and record['rich_html_sha256']==hashlib.sha256(plain.encode()).hexdigest()):continue
        card=_one(dialog.locator(group.CARD).nth(index),'Native message recreation card changed')
        body=_one(card.locator(group.OUTCOME),'Native message recreation outcome row changed').locator(':scope > span')
        if body.count()!=2:raise Stop('Native message recreation summary owner changed')
        markup=body.nth(1).inner_html()
        if hashlib.sha256(markup.encode()).hexdigest()!=record['rich_html_sha256']:
            raise Stop('Native message markup changed before order recreation; no cards deleted')
        if __package__:
            from .condition_message_markup import parse
        else:
            from condition_message_markup import parse
        parse(markup)
        markup_by_source[index]=markup
    expected_records=[original[index] for index in plan['recreate_order']]
    for index in reversed(range(prefix,len(current))):
        current=stack._delete_card(frame,dialog,current,identity,index=index,inventory=inventory)
    for index,rule in enumerate(wanted[prefix:],start=prefix):
        identity()
        if inventory(dialog)!=current:
            raise Stop('Native outcomes changed during explicit order recreation')
        markup=markup_by_source.get(plan['recreate_order'][index])
        options={'message_markup':markup} if markup is not None else {}
        current=_author(frame,dialog,rule,current,identity,inventory=inventory,**options)
        if current[-1]!=expected_records[index]:
            raise Stop('Recreated native outcome changed protected message markup; outer Save not attempted')
    return current


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','rules','expected_rules','source_indices','recreate_order','field_bindings','message_markup'}
            or step.get('action','native_condition_outcomes')!='native_condition_outcomes'):
        raise Stop('Unsupported native conditional outcome stack')
    bindings=group.condition_bindings(step) if 'field_bindings' in step else None
    plan={**deepcopy(step),'rules':_rules(step.get('rules'),allow_empty='expected_rules' in step,field_bindings=bindings)}
    if 'message_markup' in step:
        values=step['message_markup']
        if not isinstance(values,list) or len(values)!=len(plan['rules']):
            raise Stop('Message markup must identify each desired rule by ordinal')
        if __package__:
            from .condition_message_markup import parse
        else:
            from condition_message_markup import parse
        for rule,markup in zip(plan['rules'],values):
            if markup is None:continue
            if 'message' not in rule:raise Stop('Message markup requires a message outcome')
            paragraphs=parse(markup)
            text='\n'.join(''.join(run[0] for run in paragraph) for paragraph in paragraphs)
            if _message(text)!=rule['message']:
                raise Stop('Message markup text must equal the authored message')
        if 'expected_rules' in step or 'recreate_order' in step:
            raise Stop('Authored message markup currently supports append-only creation')
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
    if 'message_markup' in plan:binding={'rules':binding,'message_markup':plan['message_markup']}
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
        if tokens[2]=='Between':
            if len(tokens)!=4 or len(tokens[3].split(' And '))!=2:
                raise Stop('Native Between summary range structure changed')
            clause['value']=tokens[3].split(' And ')
        elif len(tokens)==4:clause['value']=tokens[3]
        elif len(tokens)!=3:raise Stop('Native non-range summary contains ignored values')
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
        if rich is not None:rule['message']=_message_from_native(text,rich)
        canonical=_rule(rule,field_bindings=field_bindings)
        result.append({'rule':canonical,'rich_html_sha256':(
            hashlib.sha256(rich.encode()).hexdigest() if isinstance(rich,str) else None)})
    return result


def _tile(rule):
    return 'Show/Hide Fields' if rule['effect'] in ('Show Field','Hide Field') else rule['effect']


def _disqualify_timing(modal):
    timing=modal.locator('#disqualify-timing .n-base-selection-input')
    # Forms without this survey-only control retain their existing profile.
    if not timing.count():return
    timing=_one(timing,'Native disqualification timing is ambiguous')
    text=_one(timing.locator('.n-base-selection-input__content'),
              'Native disqualification timing text changed').inner_text().strip()
    if text!='Disqualify After Submit' or timing.get_attribute('title')!=text:
        raise Stop('Only the captured Disqualify After Submit timing is supported')


def _disqualify_mode(modal):
    _disqualify_timing(modal)
    selected=_one(modal.locator('#disqualify-action .n-base-selection-input'),
                  'Native disqualification mode selector changed')
    text=_one(selected.locator('.n-base-selection-input__content'),
              'Native disqualification mode text changed').inner_text().strip()
    if selected.get_attribute('title')!=text or text not in (SHOW_MESSAGE,REDIRECT):
        raise Stop('Native disqualification mode is unavailable or inconsistent')
    return text,selected


def _effect_value(frame,modal,rule,*,write,identity=lambda:None,message_markup=None):
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
        if write:
            identity()
            if message_markup is None:fill(control,rule['message'])
            else:
                if __package__:
                    from .condition_message_markup import write as write_markup
                else:
                    from condition_message_markup import write as write_markup
                write_markup(modal,control,message_markup,identity,frame=frame)
        if _message_from_native(control.inner_text(),control.inner_html())!=rule['message']:
            raise Stop('Native conditional message differs from its authored plain text')
        if write and (control.locator('script,iframe').count() or message_markup is None and control.locator('a').count()):
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
        group._read_clause_value(modal,index,clause)
    joins=modal.locator('.n-tabs')
    if joins.count()!=count:raise Stop('Native outcome connector count differs')
    for index in range(count):
        selected=_one(joins.nth(index).locator('.n-tabs-tab--active'),'Native outcome connector is ambiguous')
        if selected.get_attribute('data-name')!=('then' if index==count-1 else group._connectors(rule)[index]):
            raise Stop('Native outcome AND/OR connector differs')


def _author(frame,dialog,rule,prefix,identity,*,inventory=None,message_markup=None):
    if rule['effect']==JUMP:raise Stop('Survey Jump To cards are immutable in the shared outcome writer')
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
            group._write_clause_value(modal,index,clause,writer=fill,frame=frame)
        if index<len(rule['clauses'])-1:
            joins=modal.locator('.n-tabs')
            if joins.count()!=index+1:raise Stop('Native outcome append connector count changed')
            choice=joins.nth(index).locator('[data-name="'+group._connectors(rule)[index]+'"]')
            click(_one(choice,'Native outcome append connector is ambiguous'))
            wait_until(lambda:modal.locator('[id^="selectedField-"]').count()==index+2,
                       'Native outcome predicate did not append exactly once')
    options={'message_markup':message_markup} if message_markup is not None else {}
    _effect_value(frame,modal,rule,write=True,identity=identity,**options)
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
    if before_rule['effect']==JUMP or rule['effect']==JUMP:
        raise Stop('Survey Jump To cards are immutable in the shared outcome writer')
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
            group._write_clause_value(modal,row,clause,writer=fill,frame=frame)
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


def configure(page,step,*,surface='form',inventory_override=None):
    plan=validate(step)
    if surface not in ('form','survey'):raise Stop('Uncaptured native condition editor surface')
    contains_jump=any(rule['effect']==JUMP for rule in plan['rules']+plan.get('expected_rules',[]))
    if (contains_jump or inventory_override is not None) and (surface!='survey' or inventory_override is None):
        raise Stop('Jump To inventory is supported only by the survey-owned immutable reader')
    if contains_jump:
        expected=plan.get('expected_rules')
        if expected is None or 'recreate_order' in plan or len(expected)>len(plan['rules']):
            raise Stop('Survey Jump To requires a complete inventory without removal or recreation')
        if len(expected)<len(plan['rules']) and (plan['rules'][:len(expected)]!=expected or 'source_indices' in plan):
            raise Stop('Survey Jump To permits only an unchanged prefix and a new outcome suffix')
        if any(rule['effect']==JUMP for rule in plan['rules'][len(expected):]):
            raise Stop('Survey Jump To cannot be newly authored by the shared outcome writer')
        for index,(old,new) in enumerate(zip(expected,plan['rules'])):
            if (old['effect']==JUMP or new['effect']==JUMP) and old!=new:
                raise Stop('Survey Jump To cards must remain unchanged at their original ordinal')
    editor_route='form-builder-v2' if surface=='form' else 'survey-builder-v2'
    route=urlsplit(page.url)
    if (route.scheme!='https' or route.username is not None or route.password is not None
            or route.query or route.fragment
            or not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/'+editor_route+r'/[A-Za-z0-9_-]+/?',route.path)):
        raise Stop('Native conditional outcomes require their exact captured editor route')
    def builder():
        return form_builder(page) if surface=='form' else page.frame_locator('iframe[name="survey-builder-app"]')
    frame=builder()
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
    reader=inventory_override if inventory_override is not None else _inventory
    inventory=(lambda dialog:reader(dialog,field_bindings=bindings)) if bindings is not None or inventory_override is not None else reader
    reader_options={'inventory':inventory} if bindings is not None or inventory_override is not None else {}
    def preflight():
        if surface=='survey' and bindings is not None:
            group.field_identity.preflight(frame,bindings,identity,items_selector='.survey-form-container .form-field-wrapper')
        else:group._preflight_fields(frame,plan,identity)
    preflight()
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
        markup_values=plan.get('message_markup',[None]*len(wanted))
        for index,record in enumerate(before):
            markup=markup_values[index] if index<len(markup_values) else None
            if markup is not None and not _matches_message_markup(dialog,index,record,markup):
                raise Stop('Existing message markup differs from the authored markup; no writes attempted')
        if len(before)>len(wanted) or [record['rule'] for record in before]!=wanted[:len(before)]:
            raise Stop('Existing native outcomes are not the exact authored prefix; reconcile before writing')
        for index in range(len(before),len(wanted)):
            rule=wanted[index];markup=markup_values[index]
            if inventory(dialog)!=current:raise Stop('Native outcome stack changed after full preflight')
            options={'message_markup':markup} if markup is not None else {}
            current=_author(frame,dialog,rule,current,identity,**reader_options,**options)
            if markup is not None and not _matches_message_markup(dialog,index,current[-1],markup):
                raise Stop('Authored message markup changed in the native card; outer Save not attempted')
    if inventory(dialog)!=current or [record['rule'] for record in current]!=wanted:
        raise Stop('Native outcome stack differs before drawer Save')
    identity();click(_one(dialog.locator('#conditional-logic-save-close'),'Native outcome drawer Save changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    changed=before!=current
    if changed:
        identity();save=_one(frame.get_by_role('button',name='Save',exact=True),'Native outcome outer Save changed')
        click(save);group._wait_for_form_save(page,save)
    reopen_editor(page,surface,name,editor_url)
    frame=builder()
    preflight()
    dialog=open_conditions()
    if inventory(dialog)!=current:
        raise Stop('Native outcomes or protected message markup did not persist after independent reopen; do not repeat the write')
    if not current:stack._empty_state(dialog)
    click(_one(dialog.locator('#conditional-logic-save-close'),'Reopened native outcome drawer Save changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return {'status':'CONDITION_OUTCOMES_SAVED_AND_REOPENED' if changed else 'CONDITION_OUTCOMES_REUSED_AND_REOPENED',
        'kind':surface+'_condition_outcomes','editor_url':page.url,'rule_count':len(wanted),
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False,'disqualification_executed':False,
        **({'saved_rules':deepcopy(current)} if surface=='survey' else {})}


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
