"""Captured Single Line survey questions on explicitly empty slide owners.

Captured 2026-11-10: Single Line0 drag handle, empty slide canvas, TEXT input,
General Settings and saved/reopened label, placeholder, short label and Query Key.
Each invocation journals intent before its single insertion; uncertain writes are
never retried. Populated-slide append and other widgets require separate captures.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright_recipes.assessments import read_editor_title, reopen_editor
from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.skill6_playwright import Stop, assert_tenant, click, fill, secure_json, wait_until
from playwright_recipes.survey_fields import _close_initial
from playwright_recipes.field_placement import _close_properties

PROPERTIES={'label':'#fieldTitle input','placeholder':'#fieldPlaceholder input',
            'short_label':'#shortLabel input','query_key':'#fieldQueryKey input'}
FLAGS={'required':'#fieldRequired','hidden':'#fieldCheckbox'}
QUESTION=set(PROPERTIES)|set(FLAGS)
COMMON=('location_id','location_name','start_url')


def validate_question(value):
    if not isinstance(value,dict) or set(value)!=(QUESTION|({'hidden_value'} if value.get('hidden') is True else set())):
        raise Stop('Survey Single Line needs complete authored text, Query Key and Boolean flags')
    for key in PROPERTIES:
        item=value[key]
        if (not isinstance(item,str) or len(item)>1000 or any(ord(c)<32 for c in item)
                or key in ('label','query_key') and not item.strip()):
            raise Stop('Survey Single Line properties must be explicit bounded text')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',value['query_key']):
        raise Stop('Survey Single Line Query Key must be an exact native token')
    if any(type(value[key]) is not bool for key in FLAGS) or value['required'] and value['hidden']:
        raise Stop('Survey Single Line Required and Hidden must be exclusive real booleans')
    if value['hidden'] and (not isinstance(value['hidden_value'],str) or len(value['hidden_value'])>1000
            or any(ord(c)<32 for c in value['hidden_value'])):
        raise Stop('Hidden survey Single Line needs its explicit captured hidden value')
    return deepcopy(value)


def _one(node,message):
    if node.count()!=1 or not node.is_visible():raise Stop(message)
    return node


def _owners(frame,plan):
    owners=frame.locator('.survey-form-container')
    if owners.count()!=plan['expected_slide_count'] or frame.get_by_role('button',name='Add Slide',exact=True).count()!=owners.count():
        raise Stop('Survey Single Line complete slide owner inventory changed')
    for index,label in enumerate(plan['slide_labels']):
        heading=owners.nth(index).locator('.builder-form-name')
        if heading.count()!=1 or 'P'+str(index+1)+' - '+heading.inner_text().strip()!=label:
            raise Stop('Survey Single Line slide label/order changed')
    return owners


def _frame(page,plan):
    if page.url!=plan['start_url']:raise Stop('Survey Single Line editor URL changed')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['expected_survey_name']:
        raise Stop('Survey Single Line exact title changed')
    _close_initial(frame);click(frame.get_by_role('tab',name='Edit',exact=True))
    _owners(frame,plan)
    return frame


def snapshot(frame,plan):
    """Stable semantic canvas inventory, excluding transient selection controls."""
    owners=_owners(frame,plan)
    return [owners.nth(index).locator('.form-field-wrapper').evaluate_all('''items => items.map(item => ({
        types:Array.from(item.querySelectorAll('[data-field-type]')).map(e=>e.getAttribute('data-field-type')),
        labels:Array.from(item.querySelectorAll('[data-field-type]')).map(e=>e.textContent.trim()),
        short_labels:Array.from(item.querySelectorAll('[aria-label="Short Label"]')).map(e=>e.textContent),
        controls:Array.from(item.querySelectorAll('input,textarea,select')).map(e=>
            [e.tagName,e.getAttribute('type'),e.getAttribute('name'),e.getAttribute('placeholder'),e.value])
    }))''') for index in range(owners.count())]


def _item(frame,plan):
    owner=_owners(frame,plan).nth(plan['target_slide']-1)
    items=owner.locator('.form-field-wrapper').filter(has=frame.locator('[data-field-type="TEXT"]'))
    if items.count()!=1:raise Stop('Captured Single Line owner must contain exactly its sole authored TEXT question')
    item=items.nth(0);label=_one(item.locator('[data-field-type="TEXT"]'),'Survey Single Line TEXT label changed')
    if item.locator('[data-field-type]').count()!=1:raise Stop('Survey Single Line owner contains another widget type')
    control=_one(item.locator('input.form-placeholder.form-control'),'Survey Single Line input changed')
    if any(control.get_attribute(key) is not None for key in ('id','name','type')) or control.input_value()!='':
        raise Stop('Survey Single Line differs from its captured empty no-ID input')
    click(label);click(_one(item.get_by_role('button',name='Open settings',exact=True),'Survey Single Line settings control changed'))
    _one(frame.locator('#general-settings'),'Survey Single Line General Settings changed')
    return item


def read_question(frame,plan):
    _item(frame,plan)
    values={key:_one(frame.locator(selector),'Survey Single Line property control changed').input_value()
        for key,selector in PROPERTIES.items()}
    for key,selector in FLAGS.items():
        node=_one(frame.locator(selector),'Survey Single Line Boolean control changed')
        value=node.get_attribute('aria-checked')
        if value not in ('true','false') or node.get_attribute('role')!='checkbox':
            raise Stop('Survey Single Line Boolean state is unexposed')
        values[key]=value=='true'
    hidden_value=frame.locator('#fieldHiddenvalue input')
    if values['hidden']:
        values['hidden_value']=_one(hidden_value,'Survey Single Line Hidden value changed').input_value()
    elif hidden_value.count():raise Stop('Unhidden survey Single Line unexpectedly exposes a Hidden value')
    _close_properties(frame)
    return values


def _fingerprint(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_receipt(value,plan):
    if (not isinstance(value,dict) or set(value)!={'status','editor_url','target_slide','question','configuration_sha256','saved_snapshot','independent_readback'}
            or value['status']!='SURVEY_SINGLE_LINE_SAVED_AND_REOPENED'
            or value['editor_url']!=plan['start_url'] or value['target_slide']!=plan['target_slide']
            or value['question']!=plan['question'] or value['configuration_sha256']!=_fingerprint(plan)
            or value['independent_readback']!='VERIFIED'
            or not isinstance(value['saved_snapshot'],list) or len(value['saved_snapshot'])!=plan['expected_slide_count']):
        raise Stop('Survey Single Line completion is unbound or malformed')
    return deepcopy(value)


def configure(page,plan,evidence_root):
    validate_question(plan['question'])
    root=Path(evidence_root).resolve();state=root/'single-line-state.json';fingerprint=_fingerprint(plan)
    if state.is_symlink():raise Stop('Survey Single Line journal must not be a symlink')
    frame=_frame(page,plan)
    if journal_present(state):
        stored=read_journal(state)
        if (stored.get('configuration_sha256')!=fingerprint or stored.get('status')!='SAVED_AND_REOPENED'):
            raise Stop('Survey Single Line insertion/Save is uncertain; reconcile without retrying')
        done=validate_receipt(stored.get('receipt'),plan)
        if read_question(frame,plan)!=plan['question']:
            raise Stop('Completed Survey Single Line saved owner changed')
        return done
    owners=_owners(frame,plan);owner=owners.nth(plan['target_slide']-1)
    if (owner.locator('.form-field-wrapper').count()!=0
            or owner.get_by_text('Drag and drop components',exact=True).count()!=1):
        raise Stop('Survey Single Line insertion requires its positively empty captured owner')
    before=snapshot(frame,plan)
    click(_one(owner.get_by_role('button',name='Add Elements',exact=True),'Survey empty-owner Add Elements changed'))
    dialog=_one(frame.get_by_role('dialog'),'Survey Element drawer changed')
    _one(dialog.get_by_text('Survey Element',exact=True),'Survey Element title changed')
    click(_one(dialog.get_by_text('Quick Add',exact=True),'Survey Quick Add tab changed'))
    tile=_one(dialog.locator('[id="Single Line0"]'),'Captured Single Line tile changed')
    handle=_one(tile.locator('.gui__builder-card--handler'),'Captured Single Line drag handle changed')
    canvas=_one(owner.locator('.builder_sub_container'),'Survey Single Line empty canvas changed')
    record={'configuration_sha256':fingerprint,'status':'INTENT_RECORDED'};secure_json(state,record)
    try:
        handle.drag_to(canvas,timeout=45000)
        wait_until(lambda:owner.locator('.form-field-wrapper').count()==1,'Survey Single Line insertion did not produce exactly one widget')
        _close_initial(frame)
        after=snapshot(frame,plan)
        if any(row!=before[index] for index,row in enumerate(after) if index!=plan['target_slide']-1):
            raise Stop('Survey Single Line insertion changed an unrequested owner')
        previous=read_question(frame,plan)
        if (not re.fullmatch(r'Single Line [a-z0-9]{6}',previous['label'])
                or previous['query_key']!='single_line_'+previous['label'].rsplit(' ',1)[1]
                or previous['placeholder']!='Enter your text' or previous['short_label']
                or previous['required'] or previous['hidden']):
            raise Stop('New survey Single Line defaults differ from native capture')
        _item(frame,plan)
        for key,selector in PROPERTIES.items():
            node=_one(frame.locator(selector),'Survey Single Line property changed')
            fill(node,plan['question'][key]);node.press('Tab')
        for key,selector in FLAGS.items():
            node=_one(frame.locator(selector),'Survey Single Line Boolean changed')
            wanted=plan['question'][key]
            if (node.get_attribute('aria-checked')=='true')!=wanted:
                if 'n-checkbox--disabled' in (node.get_attribute('class') or '').split():
                    raise Stop('Survey Single Line requested Boolean is disabled')
                node.set_checked(wanted)
        if plan['question']['hidden']:
            fill(_one(frame.locator('#fieldHiddenvalue input'),'Survey Single Line Hidden value changed'),plan['question']['hidden_value'])
        _close_properties(frame)
        if read_question(frame,plan)!=plan['question']:raise Stop('Survey Single Line ignored an authored property')
        desired=snapshot(frame,plan)
        if any(row!=before[index] for index,row in enumerate(desired) if index!=plan['target_slide']-1):
            raise Stop('Survey Single Line property edit changed an unrequested slide')
        save=_one(frame.get_by_role('button',name='Save',exact=True),'Survey Single Line Save changed')
        click(save);wait_until(lambda:save.is_enabled(),'Survey Single Line Save did not finish')
        reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url'])
        frame=_frame(page,plan)
        if read_question(frame,plan)!=plan['question'] or snapshot(frame,plan)!=desired:
            raise Stop('Survey Single Line did not persist after independent reopen')
        done=validate_receipt({'status':'SURVEY_SINGLE_LINE_SAVED_AND_REOPENED','editor_url':plan['start_url'],
            'target_slide':plan['target_slide'],'question':deepcopy(plan['question']),'configuration_sha256':fingerprint,
            'saved_snapshot':desired,'independent_readback':'VERIFIED'},plan)
        secure_json(state,{'configuration_sha256':fingerprint,'status':'SAVED_AND_REOPENED','receipt':done})
        return done
    except Exception as error:
        record.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__);secure_json(state,record)
        raise
