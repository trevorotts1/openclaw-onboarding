"""Survey-owned compound condition/outcome stacks reuse captured native controls.

The full survey identity and slide order bind the shared writer. Completed
replay reopens and compares saved rules and rich markup without reauthoring.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes import form_condition_outcomes as shared
from playwright_recipes import survey_text_questions as survey
from playwright_recipes.assessments import reopen_editor
from playwright_recipes.skill6_playwright import Stop,click

ACTION='native_survey_condition_outcomes'
COMMON=('location_id','location_name','start_url')
OWNER=('expected_survey_name','expected_slide_count','slide_labels','outcomes')
JUMP='Jump To'


def validate(step):
    if not isinstance(step,dict) or set(step)-{'id','action','payload'} or step.get('action',ACTION)!=ACTION:
        raise Stop('Unsupported survey condition outcome metadata')
    plan=step.get('payload')
    if not isinstance(plan,dict) or set(plan)!=set(COMMON)|set(OWNER):
        raise Stop('Survey outcomes require exact editor, complete slide owners and authored condition stack')
    for key in (*COMMON,'expected_survey_name'):
        value=plan[key]
        if not isinstance(value,str) or not value.strip() or value!=value.strip() or any(ord(c)<32 for c in value):
            raise Stop('Survey condition owner identity is missing')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',plan['location_id']):raise Stop('Survey outcome location identity is invalid')
    try:url=urlsplit(plan['start_url']);port=url.port
    except ValueError:raise Stop('Survey outcome editor URL is malformed') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None,443) or url.query or url.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',url.path)):
        raise Stop('Survey outcomes require an exact same-location survey editor')
    count=plan['expected_slide_count'];labels=plan['slide_labels']
    if (type(count) is not int or not 1<=count<=100 or not isinstance(labels,list) or len(labels)!=count
            or any(not isinstance(label,str) or not re.fullmatch('P'+str(i)+r' - .+',label) for i,label in enumerate(labels,1))):
        raise Stop('Survey outcomes require every exact numbered slide label')
    authored=plan['outcomes']
    if not isinstance(authored,dict) or set(authored).intersection({'id','action'}):
        raise Stop('Survey outcome inputs cannot override shared runner metadata')
    canonical=shared.validate({'action':'native_condition_outcomes',**authored})
    jumps=lambda rules:[(index,rule) for index,rule in enumerate(rules) if rule['effect']==JUMP]
    expected=canonical.get('expected_rules')
    wanted=canonical['rules']
    if expected is not None:
        old_jumps=jumps(expected);new_jumps=jumps(wanted)
        if old_jumps!=new_jumps:
            raise Stop('Survey Jump To cards must remain unchanged at their complete original ordinals')
    elif any(rule['effect']==JUMP for rule in wanted) and 'recreate_order' in canonical:
        raise Stop('Survey Jump To cards cannot participate in native order recreation')
    for rule in wanted+(expected or []):
        if rule['effect']==JUMP and rule['target_slide'] not in labels:
            raise Stop('Survey Jump To destination must match an exact captured slide label')
    result=deepcopy(plan);result['outcomes']={key:value for key,value in canonical.items() if key!='action'}
    return result


def _step(plan):return {'action':'native_condition_outcomes',**plan['outcomes']}


def _inventory(dialog,*,field_bindings=None,slide_labels=None):
    """Read complete mixed Survey card order, including immutable legacy Jump To cards."""
    cards=dialog.locator(shared.group.CARD)
    empty=dialog.get_by_text('No existing conditions yet',exact=True)
    if not cards.count():
        if empty.count()!=1:raise Stop('Native survey condition inventory is unavailable; no inferred empty set')
        return []
    if empty.count():raise Stop('Native survey condition empty marker conflicts with displayed cards')
    result=[]
    for index in range(cards.count()):
        card=cards.nth(index)
        if card.locator('#edit-condition').count()!=1 or card.locator('#delete-condition').count()!=1:
            raise Stop('Native survey outcome card action inventory changed')
        effect=shared._one(card.locator('.text-sm.font-semibold'),'Native survey outcome heading changed').inner_text().strip()
        outcome=shared._one(card.locator(shared.group.OUTCOME),'Native survey outcome summary changed')
        spans=outcome.locator(':scope > span')
        if spans.count()!=2:raise Stop('Native survey outcome needs its exact mode and value spans')
        mode=spans.nth(0).inner_text().replace('\u00a0',' ').strip()
        text=spans.nth(1).inner_text().strip()
        predicate=shared._predicate(card)
        rule={**predicate,'effect':effect}
        rich=None
        if effect in ('Show Field','Hide Field'):
            if mode!=effect:raise Stop('Native survey field outcome summary disagrees with its heading')
            rule['target']=text
        elif effect==shared.REDIRECT:
            if mode!=shared.REDIRECT:raise Stop('Native survey redirect summary mode changed')
            rule['redirect_url']=text
        elif effect==shared.MESSAGE:
            if mode!='SHOW':raise Stop('Native survey custom-message summary mode changed')
            rule['message']=text;rich=spans.nth(1).inner_html()
        elif effect==shared.DISQUALIFY:
            if mode==shared.REDIRECT:rule.update(mode=shared.REDIRECT,redirect_url=text)
            elif mode=='SHOW':rule.update(mode=shared.SHOW_MESSAGE,message=text);rich=spans.nth(1).inner_html()
            else:raise Stop('Native survey disqualification summary mode is unknown')
        elif effect=='Jump To Slide':
            if mode!='JUMP TO':raise Stop('Native survey Jump To summary mode changed')
            if slide_labels is not None and text not in slide_labels:
                raise Stop('Existing Survey Jump To destination is outside the exact owned slide inventory')
            rule={**predicate,'effect':JUMP,'target_slide':text}
        else:raise Stop('Unknown existing native Survey outcome requires reconciliation before authoring')
        if rich is not None:rule['message']=shared._message_from_native(text,rich)
        canonical=shared._rule(rule,field_bindings=field_bindings)
        result.append({'rule':canonical,'rich_html_sha256':hashlib.sha256(rich.encode()).hexdigest() if isinstance(rich,str) else None})
    return result


def _reader(plan):
    bindings=plan['outcomes'].get('field_bindings')
    return lambda dialog,field_bindings=None:_inventory(dialog,
        field_bindings=bindings if field_bindings is None else field_bindings,slide_labels=plan['slide_labels'])


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_receipt(value,step):
    plan=validate(step);keys={'status','kind','editor_url','rule_count','configuration_sha256','outcomes_sha256',
        'saved_rules','independent_readback','behavior_verified','submission_verified','disqualification_executed'}
    if (not isinstance(value,dict) or set(value)!=keys or value['kind']!='survey_condition_outcomes'
            or value['editor_url']!=plan['start_url'] or value['configuration_sha256']!=configuration_hash(step)
            or value['outcomes_sha256']!=shared.configuration_hash(_step(plan))
            or not isinstance(value['saved_rules'],list) or len(value['saved_rules'])!=len(plan['outcomes']['rules'])):
        raise Stop('Survey condition completion is malformed or belongs to another owner')
    inner={key:item for key,item in value.items() if key not in ('outcomes_sha256','saved_rules')}
    inner.update(kind='form_condition_outcomes',configuration_sha256=value['outcomes_sha256'])
    shared.validate_receipt(inner,_step(plan))
    for row,rule in zip(value['saved_rules'],plan['outcomes']['rules']):
        if (not isinstance(row,dict) or set(row)!={'rule','rich_html_sha256'} or row['rule']!=rule
                or ('message' in rule and (not isinstance(row['rich_html_sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',row['rich_html_sha256'])))
                or 'message' not in rule and row['rich_html_sha256'] is not None):
            raise Stop('Survey condition completion changed a rule or protected rich-message hash')
    return deepcopy(value)


def _frame(page,plan):
    frame=survey._frame(page,plan)
    panel=frame.locator('#survey_custom_sidebar')
    if panel.count()==1 and panel.is_visible():
        click(shared._one(panel.get_by_role('button',name='Back',exact=True),'Survey property sidebar Back changed'))
    return frame


def _verify_saved_timing(page,plan):
    rules=plan['outcomes']['rules']
    if not any(rule['effect']==shared.DISQUALIFY for rule in rules):return
    frame=_frame(page,plan)
    click(shared._one(frame.get_by_role('button',name='Open Conditional Logic',exact=True),'Survey outcome drawer changed'))
    dialog=shared._one(frame.get_by_role('dialog'),'Survey outcome drawer is ambiguous')
    inventory=lambda:_inventory(dialog,field_bindings=plan['outcomes'].get('field_bindings'),slide_labels=plan['slide_labels'])
    before=inventory()
    if [row['rule'] for row in before]!=rules:
        raise Stop('Survey outcomes changed before saved disqualification timing readback')
    for index,rule in enumerate(rules):
        if rule['effect']!=shared.DISQUALIFY:continue
        cards=dialog.locator(shared.group.CARD)
        if cards.count()!=len(rules):raise Stop('Survey outcome card count changed during timing readback')
        click(shared._one(cards.nth(index).locator('#edit-condition'),'Survey disqualification Edit changed'))
        modal=shared._one(frame.get_by_role('dialog'),'Survey disqualification editor is ambiguous')
        if modal.locator('#disqualify-timing .n-base-selection-input').count()!=1:
            raise Stop('Survey disqualification timing control is unavailable')
        shared._disqualify_timing(modal)
        # Captured modal Back returns to the drawer without submitting a rule.
        back=shared._one(modal.locator('.hl-modal-heading svg.h-6.w-6.cursor-pointer'),
                         'Survey disqualification read-only Back changed')
        click(back)
        if inventory()!=before:raise Stop('Survey outcome inventory changed during timing readback')
    click(shared._one(dialog.locator('#conditional-logic-save-close'),'Survey outcome drawer close changed'))
    dialog.wait_for(state='hidden',timeout=45000)


def configure(page,step):
    plan=validate(step);_frame(page,plan)
    done=shared.configure(page,_step(plan),surface='survey',inventory_override=_reader(plan))
    _frame(page,plan)
    _verify_saved_timing(page,plan)
    done['outcomes_sha256']=done['configuration_sha256'];done['configuration_sha256']=configuration_hash(step)
    return validate_receipt(done,step)


def verify_completed(page,step,receipt):
    value=validate_receipt(receipt,step);plan=validate(step)
    reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url'])
    _verify_saved_timing(page,plan)
    frame=_frame(page,plan)
    if 'field_bindings' in plan['outcomes']:
        shared.group.field_identity.preflight(frame,plan['outcomes']['field_bindings'],
            lambda:survey._owners(frame,plan),items_selector='.survey-form-container .form-field-wrapper')
    click(shared._one(frame.get_by_role('button',name='Open Conditional Logic',exact=True),'Survey outcome drawer changed'))
    dialog=shared._one(frame.get_by_role('dialog'),'Survey outcome drawer is ambiguous')
    observed=_inventory(dialog,field_bindings=plan['outcomes'].get('field_bindings'),slide_labels=plan['slide_labels'])
    if observed!=value['saved_rules']:
        raise Stop('Completed survey condition rules or rich markup drifted; no writes repeated')
    click(shared._one(dialog.locator('#conditional-logic-save-close'),'Survey outcome drawer close changed'))
    dialog.wait_for(state='hidden',timeout=45000)
    return value
