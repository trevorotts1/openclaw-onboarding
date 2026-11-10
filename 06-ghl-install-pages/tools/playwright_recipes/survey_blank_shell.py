"""Create and independently reopen captured empty survey slide owners.

The 2026-11-10 native survey capture saved/reopened two completely empty
slides. Empty-owner readiness is positive: its header, Add Elements control,
Drag and drop components caption and Add Slide control must all be present.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright_recipes.assessments import read_editor_title,reopen_editor
from playwright_recipes.evidence_lease import journal_present,read_journal
from playwright_recipes.skill6_playwright import Stop,assert_tenant,click,fill,navigate,exact_search,secure_json,wait_until
from playwright_recipes.survey_fields import _close_initial


def _editor_url(value,plan):
    if not isinstance(value,str):raise Stop('New empty survey lacks its exact editor URL')
    parsed=urlsplit(value);origin=urlsplit(plan['start_url'])
    if ((parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc) or parsed.query or parsed.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',parsed.path)):
        raise Stop('New empty survey changed its created origin/location/editor')
    return value


def validate_binding(value,plan,*,count=None):
    wanted=plan['slide_count'] if count is None else count
    if (not isinstance(value,dict) or set(value)!={'editor_url','slide_labels','slides'}
            or value['slide_labels']!=['P'+str(index)+' - Slide '+str(index) for index in range(1,wanted+1)]
            or not isinstance(value['slides'],list) or len(value['slides'])!=wanted
            or any(slide!={'canvas':[]} for slide in value['slides'])):
        raise Stop('Empty survey binding lacks its complete captured blank-slide inventory')
    _editor_url(value['editor_url'],plan)
    return deepcopy(value)


def snapshot(page,plan,editor_url,*,count=None):
    wanted=plan['slide_count'] if count is None else count
    if page.url!=_editor_url(editor_url,plan):raise Stop('Empty survey changed its created editor')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['name']:raise Stop('Empty survey changed its authored name')
    _close_initial(frame)
    click(frame.get_by_role('tab',name='Edit',exact=True))
    owners=frame.locator('.survey-form-container')
    if owners.count()!=wanted or frame.get_by_role('button',name='Add Slide',exact=True).count()!=wanted:
        raise Stop('Empty survey slide inventory changed')
    labels=[]
    for index in range(wanted):
        owner=owners.nth(index);label=owner.locator('.builder-form-name')
        add=owner.get_by_role('button',name='Add Elements',exact=True)
        if (label.count()!=1 or label.inner_text().strip()!='Slide '+str(index+1)
                or owner.locator('.form-field-wrapper').count()!=0
                or owner.get_by_text('Drag and drop components',exact=True).count()!=1
                or add.count()!=1 or not add.is_visible() or add.get_attribute('id')!='add-elements-button'
                or owner.get_by_role('button',name='Add Slide',exact=True).count()!=1):
            raise Stop('A new survey slide is not the positively loaded captured empty owner')
        labels.append('P'+str(index+1)+' - '+label.inner_text().strip())
    return validate_binding({'editor_url':editor_url,'slide_labels':labels,
        'slides':[{'canvas':[]} for _ in range(wanted)]},plan,count=wanted)


def _fingerprint(plan):
    return hashlib.sha256(json.dumps({key:plan[key] for key in
        ('location_id','location_name','start_url','name','allow_creation','slide_count')},sort_keys=True).encode()).hexdigest()


def completed_binding(plan,evidence_root):
    stored=read_journal(Path(evidence_root).resolve()/'blank-shell-state.json')
    if (not isinstance(stored,dict) or set(stored)!={'schema','configuration_sha256','status','binding'}
            or stored['schema']!='skill6-empty-survey-shell/1' or stored['configuration_sha256']!=_fingerprint(plan)
            or stored['status']!='SAVED_AND_REOPENED'):
        raise Stop('Empty-survey shell intent is uncertain; reconcile without another create/Add Slide/Save')
    return validate_binding(stored['binding'],plan)


def configure(page,plan,evidence_root):
    root=Path(evidence_root).resolve();state_path=root/'blank-shell-state.json'
    fingerprint=_fingerprint(plan)
    if journal_present(state_path):
        binding=completed_binding(plan,root)
        reopen_editor(page,'survey',plan['name'],binding['editor_url'])
        if snapshot(page,plan,binding['editor_url'])!=binding:raise Stop('Completed empty-survey shell changed')
        return binding
    navigate(page,'Surveys')
    if exact_search(page,'surveys',plan['name']) is not None:
        raise Stop('An expected-new survey name already exists; refusing unverified reuse')
    assert_tenant(page,plan)
    create=page.get_by_role('button',name='Create survey',exact=True)
    if create.count()!=1 or not create.is_enabled():raise Stop('Captured Create survey control changed')
    state={'schema':'skill6-empty-survey-shell/1','configuration_sha256':fingerprint,'status':'INTENT_RECORDED','step':'create'}
    secure_json(state_path,state)
    try:
        click(create)
        dialog=page.get_by_role('dialog')
        dialog.wait_for(state='visible',timeout=45000)
        if (dialog.count()!=1 or dialog.get_by_text('Create new survey',exact=True).count()!=1
                or dialog.get_by_text('Start from Scratch',exact=True).count()!=1):
            raise Stop('New survey creation modal differs from its captured scratch flow')
        click(dialog.get_by_text('Start from Scratch',exact=True))
        click(dialog.get_by_role('button',name='Create',exact=True))
        frame=page.frame_locator('iframe[name="survey-builder-app"]')
        title=frame.get_by_role('textbox',name='Form Name',exact=True)
        title.wait_for(state='visible',timeout=45000)
        editor_url=_editor_url(page.url,plan)
        state['editor_url']=editor_url;secure_json(state_path,state)
        fill(title,plan['name'])
        snapshot(page,plan,editor_url,count=1)
        for count in range(1,plan['slide_count']):
            state.update(status='INTENT_RECORDED',step='add_slide',next_slide=count+1)
            secure_json(state_path,state)
            owners=frame.locator('.survey-form-container')
            add=owners.nth(count-1).get_by_role('button',name='Add Slide',exact=True)
            if add.count()!=1 or not add.is_enabled():raise Stop('Captured empty-owner Add Slide control changed')
            click(add)
            wait_until(lambda:owners.count()==count+1,'New empty survey slide did not appear')
            snapshot(page,plan,editor_url,count=count+1)
        state.update(status='INTENT_RECORDED',step='save');secure_json(state_path,state)
        save=frame.get_by_role('button',name='Save',exact=True)
        if save.count()!=1 or not save.is_enabled():raise Stop('Captured survey Save control changed')
        click(save)
        wait_until(lambda:save.count()==1 and save.is_enabled(),'Empty survey Save did not finish')
        before=snapshot(page,plan,editor_url)
        reopen_editor(page,'survey',plan['name'],editor_url)
        if snapshot(page,plan,editor_url)!=before:raise Stop('Complete empty-survey slide inventory did not persist')
        secure_json(state_path,{'schema':'skill6-empty-survey-shell/1','configuration_sha256':fingerprint,
            'status':'SAVED_AND_REOPENED','binding':before})
        return before
    except Exception as error:
        state.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__)
        secure_json(state_path,state)
        raise
