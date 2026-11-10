"""Captured Single Line and Multi Line survey questions on inventoried slides.

Captured 2026-11-10: Single Line0 drag handle, empty slide canvas, TEXT input,
General Settings and saved/reopened label, placeholder, short label and Query Key.
Each invocation journals intent before its single insertion; uncertain writes are
never retried. Populated append uses its captured positive blank-tail pointer path.
Multi Line uses its separately captured LARGE_TEXT textarea and initially empty
owner only; populated Multi Line append and other widgets need separate captures.
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
        short_labels:Array.from(item.querySelectorAll('.short-label')).map(e=>e.textContent),
        controls:Array.from(item.querySelectorAll('input,textarea,select')).map(e=>
            [e.tagName,e.getAttribute('type'),e.getAttribute('name'),e.getAttribute('placeholder'),e.value])
    }))''') for index in range(owners.count())]


def _item(frame,plan):
    owner=_owners(frame,plan).nth(plan['target_slide']-1)
    family=plan.get('_native_field_type','TEXT')
    controls={'TEXT':'input.form-placeholder.form-control','LARGE_TEXT':'textarea.form-placeholder.form-control'}
    if family not in controls:raise Stop('Uncaptured native survey text family')
    items=owner.locator('.form-field-wrapper').filter(has=frame.locator('[data-field-type="'+family+'"]'))
    index=plan.get('text_index',1)
    if type(index) is not int or index<1 or items.count()<index or 'text_index' not in plan and items.count()!=1:
        raise Stop('Captured Single Line positional TEXT inventory changed')
    item=items.nth(index-1);label=_one(item.locator('[data-field-type="'+family+'"]'),'Survey native text label changed')
    if item.locator('[data-field-type]').count()!=1:raise Stop('Survey Single Line owner contains another widget type')
    control=_one(item.locator(controls[family]),'Survey native text control changed')
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


def write_question(frame,plan,question):
    validate_question(question)
    _item(frame,plan)
    # Turn active exclusions off before enabling the requested counterpart.
    for key,selector in FLAGS.items():
        node=_one(frame.locator(selector),'Survey Single Line Boolean changed')
        if not question[key] and node.get_attribute('aria-checked')=='true':node.set_checked(False)
    for key,selector in PROPERTIES.items():
        node=_one(frame.locator(selector),'Survey Single Line property changed')
        if node.input_value()!=question[key]:fill(node,question[key]);node.press('Tab')
    for key,selector in FLAGS.items():
        node=_one(frame.locator(selector),'Survey Single Line Boolean changed')
        if (node.get_attribute('aria-checked')=='true')!=question[key]:
            if 'n-checkbox--disabled' in (node.get_attribute('class') or '').split():
                raise Stop('Survey Single Line requested Boolean is disabled')
            node.set_checked(question[key])
    if question['hidden']:
        fill(_one(frame.locator('#fieldHiddenvalue input'),'Survey Single Line Hidden value changed'),question['hidden_value'])
    _close_properties(frame)
    if read_question(frame,plan)!=question:raise Stop('Survey Single Line ignored an authored property')


def _fingerprint(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _creation_profile(plan):
    family=plan.get('_native_field_type','TEXT')
    if family=='TEXT':return ('Single Line0','Single Line','single_line_','Enter your text','single-line-state.json','SURVEY_SINGLE_LINE_SAVED_AND_REOPENED')
    if family=='LARGE_TEXT':return ('Multi Line1','Multi Line','multi_line_','Type your message here','multi-line-state.json','SURVEY_MULTI_LINE_SAVED_AND_REOPENED')
    raise Stop('Uncaptured survey text creation family')


def validate_receipt(value,plan):
    if (not isinstance(value,dict) or set(value)!={'status','editor_url','target_slide','question','configuration_sha256','saved_snapshot','independent_readback'}
            or value['status']!=_creation_profile(plan)[5]
            or value['editor_url']!=plan['start_url'] or value['target_slide']!=plan['target_slide']
            or value['question']!=plan['question'] or value['configuration_sha256']!=_fingerprint(plan)
            or value['independent_readback']!='VERIFIED'
            or not isinstance(value['saved_snapshot'],list) or len(value['saved_snapshot'])!=plan['expected_slide_count']):
        raise Stop('Survey Single Line completion is unbound or malformed')
    return deepcopy(value)


def _append_populated(page,handle,canvas,last):
    """One real pointer drag into the captured blank tail, never a new page."""
    handle.scroll_into_view_if_needed();canvas.scroll_into_view_if_needed()
    source=handle.bounding_box();box=canvas.bounding_box();previous=last.bounding_box()
    if not source or not box or not previous or min(source['width'],source['height'],box['width'],box['height'])<=0:
        raise Stop('Populated survey append geometry is not measurable')
    bottom=previous['y']+previous['height'];tail=box['y']+box['height']-bottom
    if (previous['height']<=0 or previous['y']<box['y']-1 or tail<32
            or previous['x']<box['x']-1 or previous['x']+previous['width']>box['x']+box['width']+1):
        raise Stop('Populated survey append lacks the captured positive blank tail')
    # Captured x450.879 within a766.758 canvas and y89.873 below the prior
    # wrapper; stay inside that tail on smaller rendered layouts as well.
    target=(box['x']+box['width']*(450.879/766.758),bottom+min(89.873,tail/2))
    if not box['x']+8<target[0]<box['x']+box['width']-8 or not bottom+8<target[1]<box['y']+box['height']-8:
        raise Stop('Populated survey append point is outside the captured safe tail')
    page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
    page.mouse.down()
    try:
        page.mouse.move(*target,steps=15)
        for _ in range(3):page.mouse.move(*target)
    finally:page.mouse.up()


def configure(page,plan,evidence_root):
    validate_question(plan['question'])
    profile=_creation_profile(plan)
    root=Path(evidence_root).resolve();state=root/profile[4];fingerprint=_fingerprint(plan)
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
    prior=plan.get('expected_prior',[])
    if plan.get('_native_field_type')=='LARGE_TEXT' and prior:
        raise Stop('Multi Line creation requires its captured initially empty slide; populated append needs a separate capture')
    if not isinstance(prior,list) or owner.locator('.form-field-wrapper').count()!=len(prior):
        raise Stop('Survey Single Line populated owner differs from the complete prior question inventory')
    for index,question in enumerate(prior,1):
        validate_question(question)
        if read_question(frame,{**plan,'text_index':index})!=question:
            raise Stop('Survey Single Line prior question properties changed before append')
    if not prior and owner.get_by_text('Drag and drop components',exact=True).count()!=1:
        raise Stop('Survey Single Line insertion lacks its positively empty captured owner')
    before=snapshot(frame,plan)
    opener=(owner.locator('.form-field-wrapper').nth(len(prior)-1).get_by_role('button',name='Add Element',exact=True) if prior else
        owner.get_by_role('button',name='Add Elements',exact=True))
    click(_one(opener,'Survey Single Line element drawer opener changed'))
    dialog=_one(frame.get_by_role('dialog'),'Survey Element drawer changed')
    _one(dialog.get_by_text('Survey Element',exact=True),'Survey Element title changed')
    click(_one(dialog.get_by_text('Quick Add',exact=True),'Survey Quick Add tab changed'))
    tile=_one(dialog.locator('[id="'+profile[0]+'"]'),'Captured Single Line tile changed')
    handle=_one(tile.locator('.gui__builder-card--handler'),'Captured Single Line drag handle changed')
    canvas=_one(owner.locator('.builder_sub_container'),'Survey Single Line empty canvas changed')
    record={'configuration_sha256':fingerprint,'status':'INTENT_RECORDED'};secure_json(state,record)
    try:
        if prior:
            _append_populated(page,handle,canvas,owner.locator('.form-field-wrapper').nth(len(prior)-1))
        else:handle.drag_to(canvas,timeout=45000)
        wait_until(lambda:owner.locator('.form-field-wrapper').count()==len(prior)+1,'Survey Single Line insertion did not produce exactly one widget')
        _close_initial(frame)
        after=snapshot(frame,plan)
        if (any(row!=before[index] for index,row in enumerate(after) if index!=plan['target_slide']-1)
                or after[plan['target_slide']-1][:-1]!=before[plan['target_slide']-1]):
            raise Stop('Survey Single Line insertion changed an unrequested owner')
        for index,question in enumerate(prior,1):
            if read_question(frame,{**plan,'text_index':index})!=question:
                raise Stop('Survey Single Line append changed an existing question property')
        previous=read_question(frame,plan)
        if (not re.fullmatch(re.escape(profile[1])+r' [a-z0-9]{6}',previous['label'])
                or previous['query_key']!=profile[2]+previous['label'].rsplit(' ',1)[1]
                or previous['placeholder']!=profile[3] or previous['short_label']
                or previous['required'] or previous['hidden']):
            raise Stop('New survey Single Line defaults differ from native capture')
        write_question(frame,plan,plan['question'])
        desired=snapshot(frame,plan)
        if (any(row!=before[index] for index,row in enumerate(desired) if index!=plan['target_slide']-1)
                or desired[plan['target_slide']-1][:-1]!=before[plan['target_slide']-1]):
            raise Stop('Survey Single Line property edit changed an unrequested slide')
        save=_one(frame.get_by_role('button',name='Save',exact=True),'Survey Single Line Save changed')
        click(save);wait_until(lambda:save.is_enabled(),'Survey Single Line Save did not finish')
        reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url'])
        frame=_frame(page,plan)
        if read_question(frame,plan)!=plan['question'] or snapshot(frame,plan)!=desired:
            raise Stop('Survey Single Line did not persist after independent reopen')
        done=validate_receipt({'status':profile[5],'editor_url':plan['start_url'],
            'target_slide':plan['target_slide'],'question':deepcopy(plan['question']),'configuration_sha256':fingerprint,
            'saved_snapshot':desired,'independent_readback':'VERIFIED'},plan)
        secure_json(state,{'configuration_sha256':fingerprint,'status':'SAVED_AND_REOPENED','receipt':done})
        return done
    except Exception as error:
        record.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__);secure_json(state,record)
        raise
