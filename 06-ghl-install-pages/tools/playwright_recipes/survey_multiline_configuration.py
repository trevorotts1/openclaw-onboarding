"""Update a complete inventoried set of existing native survey Multi Line properties.

Every Multi Line position and current property is preflighted before the first edit.
Other widget canvases remain semantically bound. Query-key changes are restricted
when an uncaptured other widget could conceal a conflicting native Query Key.
The shared editor runner owns the tenant lease and intent-before-write journal.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from playwright_recipes import survey_text_questions as text
from playwright_recipes.skill6_playwright import Stop,click,wait_until
from playwright_recipes.assessments import reopen_editor

ACTION='native_survey_multiline_configuration'
OWNER={'expected_survey_name','expected_slide_count','slide_labels','multiline_questions'}


def validate(step):
    if not isinstance(step,dict) or set(step)-{'id','action','payload'} or step.get('action',ACTION)!=ACTION:
        raise Stop('Unsupported survey Multi Line property action')
    plan=step.get('payload')
    if not isinstance(plan,dict) or set(plan)!=set(text.COMMON)|OWNER:
        raise Stop('Survey Multi Line properties need exact editor, owner and full previous/desired inventory')
    for key in (*text.COMMON,'expected_survey_name'):
        if not isinstance(plan[key],str) or not plan[key].strip() or plan[key]!=plan[key].strip():
            raise Stop('Survey Multi Line property owner identity is missing')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',plan['location_id']):raise Stop('Survey Multi Line location identity is invalid')
    try:url=urlsplit(plan['start_url']);port=url.port
    except ValueError:raise Stop('Survey Multi Line editor URL is malformed') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None,443) or url.query or url.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',url.path)):
        raise Stop('Survey Multi Line properties must bind their exact same-location editor')
    count=plan['expected_slide_count'];labels=plan['slide_labels'];config=plan['multiline_questions']
    if (type(count) is not int or not 1<=count<=100 or not isinstance(labels,list) or len(labels)!=count
            or any(not isinstance(label,str) or not re.fullmatch('P'+str(index)+r' - .+',label) for index,label in enumerate(labels,1))):
        raise Stop('Survey Multi Line properties require every exact numbered owner label')
    if not isinstance(config,dict) or set(config)!={'expected','desired'}:
        raise Stop('Survey Multi Line properties need complete expected and desired inventories')
    for mode in ('expected','desired'):
        rows=config[mode]
        if not isinstance(rows,list) or len(rows)!=count or any(not isinstance(row,list) or len(row)>100 for row in rows):
            raise Stop('Survey Multi Line property inventory must cover each complete slide')
        keys=[]
        for row in rows:
            for question in row:
                keys.append(text.validate_question(question)['query_key'])
        if len(set(keys))!=len(keys):raise Stop('Survey Multi Line inventory Query Keys must be unique')
    before,after=config['expected'],config['desired']
    if not any(before) or any(len(a)!=len(b) for a,b in zip(before,after)):
        raise Stop('Existing survey Multi Line edits must preserve every question and its position')
    old=[q for row in before for q in row];new=[q for row in after for q in row]
    keys={q['query_key']:index for index,q in enumerate(old)}
    if any(q['query_key'] in keys and keys[q['query_key']]!=index for index,q in enumerate(new)):
        raise Stop('Survey Multi Line Query Key changes must not collide with another current question')
    return deepcopy(plan)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _inventory(frame,plan):
    plan={**plan,'_native_field_type':'LARGE_TEXT'}
    owners=text._owners(frame,plan);result=[]
    for index in range(owners.count()):
        count=owners.nth(index).locator('.form-field-wrapper').filter(has=frame.locator('[data-field-type="LARGE_TEXT"]')).count()
        result.append([text.read_question(frame,{**plan,'target_slide':index+1,'text_index':position+1}) for position in range(count)])
    return result


def validate_receipt(value,step):
    plan=validate(step)
    if (not isinstance(value,dict) or set(value)!={'status','editor_url','configuration_sha256','multiline_questions','independent_readback','behavior_verified','submission_verified'}
            or value['status']!='SURVEY_MULTILINE_PROPERTIES_SAVED_AND_REOPENED' or value['editor_url']!=plan['start_url']
            or value['configuration_sha256']!=configuration_hash(step) or value['multiline_questions']!=plan['multiline_questions']['desired']
            or value['independent_readback']!='VERIFIED' or value['behavior_verified'] is not False or value['submission_verified'] is not False):
        raise Stop('Survey Multi Line property completion is malformed or unbound')
    return deepcopy(value)


def configure(page,step):
    plan={**validate(step),'_native_field_type':'LARGE_TEXT'};frame=text._frame(page,plan)
    if _inventory(frame,plan)!=plan['multiline_questions']['expected']:
        raise Stop('Survey Multi Line full previous property inventory changed before edits')
    before=text.snapshot(frame,plan)
    old=plan['multiline_questions']['expected'];new=plan['multiline_questions']['desired']
    rename=any(a['query_key']!=b['query_key'] for row_a,row_b in zip(old,new) for a,b in zip(row_a,row_b))
    if rename and any(widget['types']!=['LARGE_TEXT'] for owner in before for widget in owner):
        raise Stop('Query Key edits alongside other widget types need their complete captured key inventory')
    for slide,(row_a,row_b) in enumerate(zip(old,new),1):
        for position,(previous,desired) in enumerate(zip(row_a,row_b),1):
            if previous==desired:continue
            target={**plan,'target_slide':slide,'text_index':position}
            if text.read_question(frame,target)!=previous:raise Stop('Survey Multi Line question changed after complete preflight')
            text.write_question(frame,target,desired)
    if _inventory(frame,plan)!=new:raise Stop('Survey Multi Line desired properties did not stage exactly')
    desired_snapshot=text.snapshot(frame,plan)
    # Preserve all non-TEXT widgets and untouched text siblings, including their
    # relative positions, controls, labels and values, before a single Save.
    for index,(a,b) in enumerate(zip(before,desired_snapshot)):
        changed={position for position,(q,r) in enumerate(zip(old[index],new[index])) if q!=r};text_position=0
        if len(a)!=len(b):raise Stop('Survey Multi Line property editing changed the canvas widget count')
        for previous,current in zip(a,b):
            mutable=previous['types']==['LARGE_TEXT'] and text_position in changed
            if previous['types']==['LARGE_TEXT']:text_position+=1
            if not mutable and previous!=current:raise Stop('Survey Multi Line editing changed an unrequested sibling widget')
    save=text._one(frame.get_by_role('button',name='Save',exact=True),'Survey Multi Line Save changed')
    click(save);wait_until(lambda:save.count()==1 and save.is_enabled(),'Survey Multi Line property Save did not finish')
    reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url']);frame=text._frame(page,plan)
    if _inventory(frame,plan)!=new or text.snapshot(frame,plan)!=desired_snapshot:
        raise Stop('Survey Multi Line properties or sibling canvases did not persist on independent reopen')
    return validate_receipt({'status':'SURVEY_MULTILINE_PROPERTIES_SAVED_AND_REOPENED','editor_url':plan['start_url'],
        'configuration_sha256':configuration_hash(step),'multiline_questions':deepcopy(new),
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False},step)


def verify(page,step,receipt):
    """Completed replay must re-read actual current Multi Line properties."""
    done=validate_receipt(receipt,step)
    plan={**validate(step),'_native_field_type':'LARGE_TEXT'}
    if _inventory(text._frame(page,plan),plan)!=plan['multiline_questions']['desired']:
        raise Stop('Completed survey Multi Line properties changed; no write replayed')
    return done
