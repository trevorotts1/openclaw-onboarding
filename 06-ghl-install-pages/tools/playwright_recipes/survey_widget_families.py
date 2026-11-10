"""Survey property edits reuse captured field-family controls, not form layouts.

Number is grounded by the saved/reopened November 10 survey capture. Checkbox,
File Upload and Signature remain unavailable here until their survey controls
are captured; a form capture is not treated as survey evidence.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes import form_widget_families as shared
from playwright_recipes import survey_text_questions as survey
from playwright_recipes.skill6_playwright import Stop,click,wait_until
from playwright_recipes.assessments import reopen_editor

ACTION='native_survey_widget_fields'
COMMON=('location_id','location_name','start_url')
OWNER={'expected_survey_name','expected_slide_count','slide_labels','widget_fields'}
NUMBER=deepcopy(shared.PROFILES['number'])
NUMBER['properties']={key:selector for key,selector in NUMBER['properties'].items() if key!='width'}
NUMBER['properties']['label']='#fieldTitle input'
NUMBER['defaults'].pop('width',None)
NUMBER['sidebar_header']=False  # Survey capture proves its General Settings, not the form sidebar ID.
PROFILES={'number':NUMBER}


def _properties(kind,value):
    if not isinstance(kind,str) or kind not in PROFILES:
        raise Stop('Survey widget family has no captured survey property profile')
    return shared._properties(kind,value,profile=PROFILES[kind])


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action',ACTION)!=ACTION):
        raise Stop('Unsupported native survey widget metadata')
    plan=step.get('payload')
    if not isinstance(plan,dict) or set(plan)!=set(COMMON)|OWNER:
        raise Stop('Survey widgets require exact editor, complete slide owners and full previous/desired properties')
    for key in (*COMMON,'expected_survey_name'):
        value=plan[key]
        if not isinstance(value,str) or not value.strip() or value!=value.strip() or any(ord(c)<32 for c in value):
            raise Stop('Survey widget owner identity is missing')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',plan['location_id']):
        raise Stop('Survey widget location identity is invalid')
    try:url=urlsplit(plan['start_url']);port=url.port
    except ValueError:raise Stop('Survey widget editor URL is malformed') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None,443) or url.query or url.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',url.path)):
        raise Stop('Survey widgets must bind an exact same-location survey editor')
    count=plan['expected_slide_count'];labels=plan['slide_labels'];fields=plan['widget_fields']
    if (type(count) is not int or not 1<=count<=100 or not isinstance(labels,list) or len(labels)!=count
            or any(not isinstance(label,str) or not re.fullmatch('P'+str(index)+r' - .+',label) for index,label in enumerate(labels,1))):
        raise Stop('Survey widget owners require every exact numbered slide label')
    if not isinstance(fields,dict) or set(fields)!={'expected','desired'}:
        raise Stop('Survey widget editing requires full matching previous and desired inventories')
    for mode in ('expected','desired'):
        rows=fields[mode]
        if not isinstance(rows,list) or len(rows)!=count or any(not isinstance(row,list) or len(row)>100 for row in rows):
            raise Stop('Survey widget inventory must cover each slide')
        keys=[]
        for row in rows:
            indices=[]
            for field in row:
                if (not isinstance(field,dict) or set(field)!={'kind','index','properties'}
                        or type(field['index']) is not int or field['index']<1):
                    raise Stop('Survey widgets require exact one-based positions within each slide')
                props=_properties(field['kind'],field['properties'])
                keys.append(props['query_key']);indices.append(field['index'])
            if indices!=sorted(set(indices)):
                raise Stop('Survey widget positions must be unique and ordered')
        if len(keys)!=len(set(keys)):
            raise Stop('Survey widget Query Keys must be unique across all slides')
    before=fields['expected'];after=fields['desired']
    if not any(before):raise Stop('Survey widget property jobs require existing captured widgets')
    old_keys={field['properties']['query_key']:(slide,field['index']) for slide,row in enumerate(before) for field in row}
    for slide,(old,new) in enumerate(zip(before,after)):
        if len(old)!=len(new):raise Stop('Survey widget property edits cannot create or remove questions')
        for previous,desired in zip(old,new):
            if previous['kind']!=desired['kind'] or previous['index']!=desired['index']:
                raise Stop('Survey widget property edits cannot change question family or order')
            for key in ('custom_field_name','unique_key'):
                if previous['properties'][key]!=desired['properties'][key]:
                    raise Stop('Existing survey custom-field canonical metadata is immutable')
            key=desired['properties']['query_key']
            if key in old_keys and old_keys[key]!=(slide,desired['index']):
                raise Stop('Survey widget Query Key collides with another current question')
    return deepcopy(plan)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _frame(page,plan):
    return survey._frame(page,plan)


def _inventory(frame,plan):
    owners=survey._owners(frame,plan);result=[]
    types={profile['type']:kind for kind,profile in PROFILES.items()}
    for slide in range(owners.count()):
        owner=owners.nth(slide);items=owner.locator('.form-field-wrapper');count=items.count();fields=[]
        for index in range(count):
            if items.count()!=count:raise Stop('Survey widget owner inventory changed while reading')
            item=items.nth(index);label=item.locator('[data-field-type]')
            if label.count()!=1:raise Stop('Survey canvas has an ambiguous field family')
            kind=types.get(label.get_attribute('data-field-type'))
            if kind:
                properties=shared._read(frame,item,kind,profile=PROFILES[kind])
                fields.append({'kind':kind,'index':index+1,'properties':properties})
        result.append(fields)
    return result


def validate_receipt(value,step):
    plan=validate(step)
    if (not isinstance(value,dict) or set(value)!={'status','editor_url','configuration_sha256','widget_fields','saved_snapshot',
                                                   'independent_readback','behavior_verified','submission_verified'}
            or value['status']!='SURVEY_WIDGET_FIELDS_SAVED_AND_REOPENED' or value['editor_url']!=plan['start_url']
            or value['configuration_sha256']!=configuration_hash(step)
            or value['widget_fields']!=plan['widget_fields']['desired']
            or not isinstance(value['saved_snapshot'],list) or len(value['saved_snapshot'])!=plan['expected_slide_count']
            or value['independent_readback']!='VERIFIED' or value['behavior_verified'] is not False or value['submission_verified'] is not False):
        raise Stop('Survey widget completion is malformed or unbound')
    for row,snapshot in zip(value['widget_fields'],value['saved_snapshot']):
        if not isinstance(snapshot,list):raise Stop('Survey widget saved owner snapshot is malformed')
        for field in row:
            index=field['index']-1
            if (index>=len(snapshot) or not isinstance(snapshot[index],dict)
                    or snapshot[index].get('types')!=[PROFILES[field['kind']]['type']]):
                raise Stop('Survey widget completion differs from the saved typed canvas positions')
    return deepcopy(value)


def configure(page,step):
    plan=validate(step);frame=_frame(page,plan)
    before=plan['widget_fields']['expected'];desired=plan['widget_fields']['desired']
    if _inventory(frame,plan)!=before:
        raise Stop('Survey widget full previous property inventory changed before edits')
    snapshot=survey.snapshot(frame,plan)
    renamed=any(old['properties']['query_key']!=new['properties']['query_key']
                for a,b in zip(before,desired) for old,new in zip(a,b))
    if renamed and any(widget['types'] not in ([profile['type']] for profile in PROFILES.values())
                       for owner in snapshot for widget in owner):
        raise Stop('Survey Query Key changes beside other question families require their complete query inventory')
    owners=survey._owners(frame,plan)
    for slide,(old,new) in enumerate(zip(before,desired)):
        for previous,target in zip(old,new):
            if previous==target:continue
            if survey.snapshot(frame,plan)!=snapshot:
                raise Stop('Survey widget sibling canvas changed before the next write')
            index=target['index']-1;item=owners.nth(slide).locator('.form-field-wrapper').nth(index)
            shared._write(frame,item,target['kind'],previous['properties'],target['properties'],profile=PROFILES[target['kind']])
            after=survey.snapshot(frame,plan)
            if len(after)!=len(snapshot) or any(len(a)!=len(b) for a,b in zip(after,snapshot)):
                raise Stop('Survey widget editing changed slide or question counts')
            for owner,(a,b) in enumerate(zip(snapshot,after)):
                for position,(left,right) in enumerate(zip(a,b)):
                    if (owner,position)!=(slide,index) and left!=right:
                        raise Stop('Survey widget editing changed an unrequested sibling')
            snapshot=after
    if _inventory(frame,plan)!=desired or survey.snapshot(frame,plan)!=snapshot:
        raise Stop('Survey widget desired properties or preserved canvas did not stage exactly')
    _frame(page,plan)
    save=shared._one(frame.get_by_role('button',name='Save',exact=True),'Survey widget Save changed')
    click(save);wait_until(lambda:save.count()==1 and save.is_enabled(),'Survey widget Save did not finish')
    reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url']);frame=_frame(page,plan)
    if _inventory(frame,plan)!=desired or survey.snapshot(frame,plan)!=snapshot:
        raise Stop('Survey widget properties or siblings did not persist after independent reopen')
    return validate_receipt({'status':'SURVEY_WIDGET_FIELDS_SAVED_AND_REOPENED','editor_url':plan['start_url'],
        'configuration_sha256':configuration_hash(step),'widget_fields':desired,'saved_snapshot':snapshot,
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False},step)


def verify_completed(page,step,receipt):
    value=validate_receipt(receipt,step);plan=validate(step)
    reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url']);frame=_frame(page,plan)
    if _inventory(frame,plan)!=value['widget_fields'] or survey.snapshot(frame,plan)!=value['saved_snapshot']:
        raise Stop('Completed survey widget properties or siblings drifted; no writes repeated')
    return value
