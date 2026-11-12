"""Survey property edits reuse captured field-family controls, not form layouts.

Survey profiles use separately captured November 10 controls. The File Upload
and Signature sidebars are captured independently from their form equivalents.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit
from pathlib import Path

from playwright_recipes import form_widget_families as shared
from playwright_recipes import survey_text_questions as survey
from playwright_recipes.skill6_playwright import Stop,click,wait_until,secure_json
from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.assessments import reopen_editor

ACTION='native_survey_widget_fields'
COMMON=('location_id','location_name','start_url')
OWNER={'expected_survey_name','expected_slide_count','slide_labels','widget_fields'}
NUMBER=deepcopy(shared.PROFILES['number'])
NUMBER['properties']={key:selector for key,selector in NUMBER['properties'].items() if key!='width'}
NUMBER['properties']['label']='#fieldTitle input'
NUMBER['defaults'].pop('width',None)
NUMBER['sidebar_header']=False  # Survey capture proves its General Settings, not the form sidebar ID.
CHECKBOX=deepcopy(shared.PROFILES['checkbox'])
CHECKBOX['properties']={key:selector for key,selector in CHECKBOX['properties'].items() if key!='width'}
CHECKBOX['properties']['label']='#fieldTitle input'
CHECKBOX['defaults'].pop('width',None)
CHECKBOX['sidebar']='#survey_custom_sidebar'
SINGLE_DROPDOWN=deepcopy(shared.PROFILES['single_dropdown'])
SINGLE_DROPDOWN['properties']={key:selector for key,selector in SINGLE_DROPDOWN['properties'].items() if key!='width'}
SINGLE_DROPDOWN['properties']['label']='#fieldTitle input'
SINGLE_DROPDOWN['defaults'].pop('width',None)
SINGLE_DROPDOWN['sidebar']='#survey_custom_sidebar'
SINGLE_DROPDOWN['creation_drag']='tile'
MULTI_DROPDOWN=deepcopy(shared.PROFILES['multi_dropdown'])
MULTI_DROPDOWN['properties']={key:selector for key,selector in MULTI_DROPDOWN['properties'].items() if key!='width'}
MULTI_DROPDOWN['properties']['label']='#fieldTitle input'
MULTI_DROPDOWN['defaults'].pop('width',None)
MULTI_DROPDOWN['sidebar']='#survey_custom_sidebar'
MULTI_DROPDOWN['creation_drag']='tile'
FILE_UPLOAD=deepcopy(shared.PROFILES['file_upload'])
FILE_UPLOAD['properties']['label']='#fieldTitle input'
FILE_UPLOAD['sidebar']='#survey_custom_sidebar'
FILE_UPLOAD['input']='label.custom-file-upload > svg'
SIGNATURE=deepcopy(shared.PROFILES['signature'])
SIGNATURE['properties']={key:selector for key,selector in SIGNATURE['properties'].items() if key!='width'}
SIGNATURE['properties']['label']='#fieldTitle input'
SIGNATURE['defaults'].pop('width',None)
SIGNATURE['sidebar']='#survey_custom_sidebar'
TEXT_BOX_LIST=deepcopy(shared.PROFILES['text_box_list'])
TEXT_BOX_LIST['properties']={key:selector for key,selector in TEXT_BOX_LIST['properties'].items() if key!='width'}
TEXT_BOX_LIST['properties']['label']='#fieldTitle input'
TEXT_BOX_LIST['defaults'].pop('width',None)
TEXT_BOX_LIST['sidebar']='#survey_custom_sidebar'
BOT_PROTECTION=deepcopy(shared.PROFILES['bot_protection'])
BOT_PROTECTION['sidebar']='#survey_custom_sidebar'
SOURCE=deepcopy(shared.PROFILES['source'])
SOURCE['sidebar']='#survey_custom_sidebar'
MONETARY=deepcopy(shared.PROFILES['monetary'])
MONETARY['properties']={key:selector for key,selector in MONETARY['properties'].items() if key!='width'}
MONETARY['properties']['label']='#fieldTitle input'
MONETARY['defaults'].pop('width',None)
MONETARY['sidebar']='#survey_custom_sidebar'
MONETARY['creation_drag']='tile'
SCORE=deepcopy(shared.PROFILES['score'])
SCORE['properties']={key:selector for key,selector in SCORE['properties'].items() if key!='width'}
SCORE['properties']['label']='#fieldTitle input'
SCORE['defaults'].pop('width',None)
SCORE['sidebar']='#survey_custom_sidebar'
SCORE['suffix']=4
SCORE['key_prefix']='score_'
SCORE['creation_drag']='tile'
TEXT_HEADING=deepcopy(shared.PROFILES['text_heading'])
TEXT_HEADING['sidebar']='#survey_custom_sidebar'
IMAGE=deepcopy(shared.PROFILES['image'])
IMAGE['sidebar']='#survey_custom_sidebar'
IMAGE['general_selector']='#survey_custom_sidebar'
HTML=deepcopy(shared.PROFILES['html'])
HTML['sidebar']='#survey_custom_sidebar'
PICTURE_CHOICE=deepcopy(shared.PROFILES['picture_choice'])
PICTURE_CHOICE['sidebar']='#survey_custom_sidebar'
PICTURE_CHOICE.update({'suffix':6,'key_prefix':'picture_choice_'})
PICTURE_CHOICE['properties']={'label':'#fieldTitle input','placeholder':'#fieldPlaceholder input',
    'short_label':'#shortLabel input','query_key':'#fieldQueryKey input'}
PICTURE_CHOICE['defaults']={'placeholder':'','short_label':'','required':False,'hidden':False,
    'options':[{'label':'Option '+str(i),'image_url':None} for i in (1,2,3)]}
PICTURE_CHOICE['creation_supported']=True
PICTURE_CHOICE['creation_drag']='tile'
URL=deepcopy(shared.PROFILES['url'])
URL['properties']={'label':'#fieldTitle input','placeholder':'#fieldPlaceholder input',
    'short_label':'#shortLabel input','query_key':'#fieldQueryKey input'}
URL['defaults'].pop('width',None)
URL['sidebar']='#survey_custom_sidebar'
URL['suffix']=4
URL['key_prefix']='url_'
URL['creation_drag']='tile'
RATING=deepcopy(shared.PROFILES['rating'])
RATING['sidebar']='#survey_custom_sidebar'
RATING['generated_label_pattern']=r'Rating .+'
RATING['defaults']['lowest_label']=''
RATING['defaults']['highest_label']=''
def _survey_datetime(kind,widget_type,mode,label,tokens,placeholder,input_count):
    profile=deepcopy(shared.PROFILES['date_time'])
    profile['type']=widget_type;profile['tile']=label;profile['suffix']=5
    profile['key_prefix']=tokens;profile['key_property']='unique_key'
    profile['query_pattern']=r'[A-Za-z0-9_.&-]{1,256}'
    profile['properties']={key:selector for key,selector in profile['properties'].items() if key!='width'}
    profile['properties'].update({'label':'#label input','placeholder':'#fieldPlaceholder input',
        'short_label':'#shortLabel input','query_key':'#fieldQueryKey input',
        'custom_field_name':'#custom-field-label input','unique_key':'#uniqueKey input'})
    profile['defaults']={'placeholder':placeholder,'short_label':'','required':False,'hidden':False}
    profile['flags']={'required':'#fieldRequired','hidden':'#fieldCheckbox'}
    profile['input']='.date-time-preview-row input';profile['input_count']=input_count
    profile['hidden_value_captured']=False;profile['sidebar']='#survey_custom_sidebar'
    profile['sidebar_title']='Date & time';profile['general_tab']='[data-name="settings"]'
    profile['general_selector']='#survey_custom_sidebar';profile['datetime_options']=False
    profile['extra']=('collection_mode',);profile['collection_mode']=mode
    profile['generated_label_pattern']=re.escape(label)+r' [a-z0-9]{5}'
    profile['creation_mode']=mode
    return profile
SURVEY_DATE=_survey_datetime('date','DATE','date','Date','date_','YYYY-MM-DD',1)
SURVEY_DATE_TIME=_survey_datetime('date_time','DATE_TIME','date_time','Date & time','date_','YYYY-MM-DD',2)
SURVEY_TIME=_survey_datetime('time','TIME','time','Time','time_','HH:MM',1)
PROFILES={'number':NUMBER,'checkbox':CHECKBOX,'single_dropdown':SINGLE_DROPDOWN,
          'multi_dropdown':MULTI_DROPDOWN,'file_upload':FILE_UPLOAD,'signature':SIGNATURE,
          'text_box_list':TEXT_BOX_LIST,'bot_protection':BOT_PROTECTION,'source':SOURCE,'monetary':MONETARY,
          'score':SCORE,'rating':RATING,'date':SURVEY_DATE,'date_time':SURVEY_DATE_TIME,'time':SURVEY_TIME,
          'text_heading':TEXT_HEADING,'image':IMAGE,'html':HTML,'picture_choice':PICTURE_CHOICE,'url':URL}
# Survey Quick Add drawer and drag handle captured 2026-11-10.
NUMBER_CREATION_TILE='Number3'
CREATION_TILES={'number':NUMBER_CREATION_TILE,'checkbox':'Checkbox2','single_dropdown':'Single Dropdown0',
                'multi_dropdown':'Multi Dropdown1','file_upload':'File Upload1','signature':'Signature5',
                'text_box_list':'Text Box List2','bot_protection':'Bot protection2','source':'Source3','monetary':'Monetary2',
                'score':'Score5','rating':'Rating0','date':'Date & time4','date_time':'Date & time4','time':'Date & time4',
                'text_heading':'Text0','image':'Image0','html':'Html1','picture_choice':'Picture Choice4','url':'URL6'}


def _key(kind):
    return PROFILES[kind].get('key_property','query_key')


def _identity(kind,properties):
    return PROFILES[kind].get('fixed_identity') or properties[_key(kind)]


def _properties(kind,value):
    if not isinstance(kind,str) or kind not in PROFILES:
        raise Stop('Survey widget family has no captured survey property profile')
    if kind=='picture_choice':
        if not isinstance(value,dict) or not isinstance(value.get('options'),list) or len(value['options'])!=3:
            raise Stop('Survey Picture Choice requires its ordered card inventory')
        value=deepcopy(value)
        value['options']=[{**option,'alt':''} if isinstance(option,dict) and set(option)=={'label','image_url'} else option
                          for option in value['options']]
    result=shared._properties(kind,value,profile=PROFILES[kind])
    if kind=='picture_choice':
        result['options']=[{key:item for key,item in option.items() if key!='alt'} for option in result['options']]
    return result


def _read_widget(frame,item,kind):
    properties=shared._read(frame,item,kind,profile=PROFILES[kind])
    if kind=='picture_choice':
        properties['options']=[{key:value for key,value in option.items() if key!='alt'} for option in properties['options']]
    return _properties(kind,properties)


def _write_widget(frame,item,kind,before,desired):
    if kind!='picture_choice':
        return shared._write(frame,item,kind,before,desired,profile=PROFILES[kind])
    if _read_widget(frame,item,kind)!=before:
        raise Stop('Survey Picture Choice changed after complete preflight')
    actual=shared._read(frame,item,kind,profile=PROFILES[kind])
    staged=deepcopy(desired)
    staged['options']=[{'label':target['label'],'image_url':current['image_url'],'alt':current['alt']}
                       for current,target in zip(actual['options'],desired['options'])]
    shared._write(frame,item,kind,actual,staged,profile=PROFILES[kind])


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
                keys.append(_identity(field['kind'],props));indices.append(field['index'])
            if indices!=sorted(set(indices)):
                raise Stop('Survey widget positions must be unique and ordered')
        if len(keys)!=len(set(keys)):
            raise Stop('Survey widget Query Keys must be unique across all slides')
    before=fields['expected'];after=fields['desired']
    if not any(before):raise Stop('Survey widget property jobs require existing captured widgets')
    old_keys={_identity(field['kind'],field['properties']):(slide,field['index']) for slide,row in enumerate(before) for field in row}
    for slide,(old,new) in enumerate(zip(before,after)):
        if len(old)!=len(new):raise Stop('Survey widget property edits cannot create or remove questions')
        for previous,desired in zip(old,new):
            if previous['kind']!=desired['kind'] or previous['index']!=desired['index']:
                raise Stop('Survey widget property edits cannot change question family or order')
            if previous['kind']=='file_upload' and previous['properties']['file_access']!=desired['properties']['file_access']:
                raise Stop('Saved survey File Upload access is immutable; author it only at creation')
            if previous['kind']=='picture_choice':
                old_options=previous['properties']['options'];new_options=desired['properties']['options']
                if (len(old_options)!=len(new_options)
                        or any(old['image_url']!=new['image_url'] for old,new in zip(old_options,new_options))):
                    raise Stop('Saved survey Picture Choice preserves its option count and selected media')
            for key in ('custom_field_name','unique_key'):
                if key in PROFILES[previous['kind']]['properties'] and previous['properties'][key]!=desired['properties'][key]:
                    raise Stop('Existing survey custom-field canonical metadata is immutable')
            key=_identity(desired['kind'],desired['properties'])
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
            if kind=='picture_choice' and item.locator('[data-testid="picture-choice-grid"]').count()!=1:kind=None
            if kind=='text_heading' and item.locator('.tiptap.ProseMirror[contenteditable="true"]').count()!=1:kind=None
            if kind:
                properties=_read_widget(frame,item,kind)
                fields.append({'kind':kind,'index':index+1,'properties':properties})
        result.append(fields)
    return result


def _has_unrecognized_widgets(frame,plan,snapshot):
    owners=survey._owners(frame,plan)
    known={profile['type'] for kind,profile in PROFILES.items() if kind not in ('picture_choice','text_heading')}
    for slide,rows in enumerate(snapshot):
        items=owners.nth(slide).locator('.form-field-wrapper')
        if items.count()!=len(rows):raise Stop('Survey widget type-shape inventory changed')
        for index,row in enumerate(rows):
            types=row['types'];item=items.nth(index)
            if types==['RADIO']:
                if item.locator('[data-testid="picture-choice-grid"]').count()!=1:return True
            elif types==['h1']:
                if item.locator('.tiptap.ProseMirror[contenteditable="true"]').count()!=1:return True
            elif len(types)!=1 or types[0] not in known:return True
    return False


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
    renamed=any(_identity(old['kind'],old['properties'])!=_identity(new['kind'],new['properties'])
                for a,b in zip(before,desired) for old,new in zip(a,b))
    if renamed and _has_unrecognized_widgets(frame,plan,snapshot):
        raise Stop('Survey Query Key changes beside other question families require their complete query inventory')
    owners=survey._owners(frame,plan)
    for slide,(old,new) in enumerate(zip(before,desired)):
        for previous,target in zip(old,new):
            if previous==target:continue
            if survey.snapshot(frame,plan)!=snapshot:
                raise Stop('Survey widget sibling canvas changed before the next write')
            index=target['index']-1;item=owners.nth(slide).locator('.form-field-wrapper').nth(index)
            _write_widget(frame,item,target['kind'],previous['properties'],target['properties'])
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
    if any(field['kind']=='html' for row in desired for field in row):
        shared.html_fields.confirm_save_warning(frame)
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



def validate_creation_question(value,kind='number'):
    """Authoring needs both the survey sidebar and its captured insertion tile."""
    if kind not in CREATION_TILES:
        raise Stop('Survey widget creation tile requires its native capture')
    if kind=='picture_choice':
        if not isinstance(value,dict) or not isinstance(value.get('options'),list):
            raise Stop('Survey Picture Choice requires every authored catalog image')
        projected=deepcopy(value);projected['options']=[]
        from playwright_recipes.quiz_picture_questions import _https
        for option in value['options']:
            if not isinstance(option,dict) or set(option)!={'label','image_url','media_button_name'}:
                raise Stop('Survey Picture Choice requires each exact label, approved media URL and catalog tile')
            if not isinstance(option['media_button_name'],str) or not option['media_button_name'].strip() or option['media_button_name']!=option['media_button_name'].strip():
                raise Stop('Survey Picture Choice media needs its exact approved catalog tile name')
            projected['options'].append({'label':option['label'],'image_url':_https(option['image_url'])})
        _properties(kind,projected)
        return deepcopy(value)
    return _properties(kind,value)


def _creation_kind(plan):
    families={profile['type']:kind for kind,profile in PROFILES.items()}
    kind=families.get(plan.get('_native_field_type','NUMERICAL'))
    if kind not in CREATION_TILES:raise Stop('Uncaptured native survey creation family')
    return kind


def read_creation_question(frame,plan):
    owner=survey._owners(frame,plan).nth(plan['target_slide']-1)
    items=owner.locator('.form-field-wrapper')
    if items.count()!=1:
        raise Stop('Survey widget creation requires its exact single-widget owner')
    kind=_creation_kind(plan)
    return _read_widget(frame,items.nth(0),kind)


def _creation_readback(kind,value):
    result=deepcopy(value)
    if kind=='picture_choice':
        result['options']=[{key:item for key,item in option.items() if key!='media_button_name'} for option in result['options']]
    return result


def _validate_new_default(kind,previous):
    """Match the freshly dragged native default to its captured identity shape."""
    profile=PROFILES[kind]
    if kind=='text_heading':
        if set(previous)!={'text'} or not previous['text'].strip() or any(ord(c)<32 for c in previous['text']):
            raise Stop('New Survey Text heading differs from its native plain-text baseline')
        return
    if kind in ('image','html'):
        expected=set(profile['properties'])|set(profile.get('flags',()))|set(profile.get('extra',()))
        if (set(previous)!=expected or not previous.get('label','').strip()
                or any(previous.get(key)!=value for key,value in profile.get('defaults',{}).items())):
            raise Stop('New Survey media/content widget differs from its native blank baseline')
        return
    if kind=='picture_choice':
        expected=set(profile['properties'])|set(profile['flags'])|set(profile.get('extra',()))
        options=previous.get('options')
        suffix=re.fullmatch(re.escape(profile['tile'])+r' ([a-z0-9]{'+str(profile['suffix'])+'})',previous.get('label',''))
        if (set(previous)!=expected or not suffix or not shared._default_key(profile,previous.get('query_key',''),suffix.group(1))
                or len(options or [])!=3 or previous['required'] is not False
                or previous['hidden'] is not False or not previous['label'].strip() or not previous['query_key'].strip()
                or any(previous.get(key)!=value for key,value in profile['defaults'].items() if key!='options')
                or options!=profile['defaults']['options']
                or any(not option['label'].strip() or option['image_url'] is not None for option in options)):
            raise Stop('New Survey Picture Choice differs from the captured blank three-option baseline')
        return
    if profile.get('fixed_identity'):
        expected=profile['defaults']
        if (set(previous)!=set(profile['properties'])|set(profile['flags'])|set(profile.get('extra',()))|set(profile.get('preview_properties',{}))
                or any(previous.get(key)!=value for key,value in expected.items())
                or profile.get('generated_label_pattern') and not re.fullmatch(profile['generated_label_pattern'],previous.get('label',''))
                or not profile.get('generated_label_pattern') and previous!=expected):
            raise Stop('New survey singleton widget differs from its captured native defaults')
        return
    suffix=re.fullmatch(re.escape(profile['tile'])+r' ([a-z0-9]{'+str(profile['suffix'])+'})',previous['label'])
    if (not suffix or not shared._default_key(profile,previous[_key(kind)],suffix.group(1))
            or 'custom_field_name' in profile['properties'] and previous.get('custom_field_name')!=previous['label']
            or 'unique_key' in profile['properties'] and (not previous.get('unique_key','').startswith('contact.'+profile['key_prefix'])
            or previous['unique_key'][len('contact.'+profile['key_prefix']):].replace('_','')!=suffix.group(1))
            or any(previous[key]!=value for key,value in profile['defaults'].items())):
        raise Stop('New survey widget defaults differ from its captured native identity')


def _creation_hash(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_creation_receipt(value,plan):
    kind=_creation_kind(plan);profile=PROFILES[kind]
    validate_creation_question(plan['question'],kind)
    if (not isinstance(value,dict) or set(value)!={'status','editor_url','target_slide','question',
                'configuration_sha256','saved_snapshot','independent_readback'}
            or value['status']!='SURVEY_'+kind.upper()+'_SAVED_AND_REOPENED'
            or value['editor_url']!=plan['start_url'] or value['target_slide']!=plan['target_slide']
            or value['question']!=plan['question'] or value['configuration_sha256']!=_creation_hash(plan)
            or value['independent_readback']!='VERIFIED'
            or not isinstance(value['saved_snapshot'],list)
            or len(value['saved_snapshot'])!=plan['expected_slide_count']):
        raise Stop('Survey widget creation completion is malformed or unbound')
    row=value['saved_snapshot'][plan['target_slide']-1]
    if not isinstance(row,list) or len(row)!=1 or not isinstance(row[0],dict) or row[0].get('types')!=[profile['type']]:
        raise Stop('Survey widget completion changed its exact saved owner')
    return deepcopy(value)


def configure_creation(page,plan,evidence_root):
    """One captured widget insertion on an owned empty slide, then Save/reopen."""
    kind=_creation_kind(plan);profile=PROFILES[kind]
    validate_creation_question(plan['question'],kind)
    root=Path(evidence_root).resolve();state=root/(kind+'-state.json');fingerprint=_creation_hash(plan)
    if state.is_symlink():raise Stop('Survey widget journal must not be a symlink')
    frame=survey._frame(page,plan)
    if journal_present(state):
        stored=read_journal(state)
        if stored.get('configuration_sha256')!=fingerprint or stored.get('status')!='SAVED_AND_REOPENED':
            raise Stop('Survey widget insertion or Save is uncertain; reconcile without retrying')
        done=validate_creation_receipt(stored.get('receipt'),plan)
        reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url'])
        frame=survey._frame(page,plan)
        if read_creation_question(frame,plan)!=_creation_readback(kind,plan['question']) or survey.snapshot(frame,plan)!=done['saved_snapshot']:
            raise Stop('Completed Survey widget owner or siblings drifted; no insertion repeated')
        return done
    owner=survey._owners(frame,plan).nth(plan['target_slide']-1)
    if owner.locator('.form-field-wrapper').count()!=0 or owner.get_by_text('Drag and drop components',exact=True).count()!=1:
        raise Stop('Survey widget insertion requires its positively empty captured owner')
    before=survey.snapshot(frame,plan)
    click(shared._one(owner.get_by_role('button',name='Add Elements',exact=True),'Survey widget element drawer opener changed'))
    dialog=shared._one(frame.get_by_role('dialog'),'Survey widget element drawer changed')
    shared._one(dialog.get_by_text('Survey Element',exact=True),'Survey widget element drawer title changed')
    click(shared._one(dialog.get_by_text('Quick Add',exact=True),'Survey widget Quick Add tab changed'))
    tile=shared._one(dialog.locator('[id="'+CREATION_TILES[kind]+'"]'),'Captured survey widget tile changed')
    handle=(tile if profile.get('creation_drag')=='tile' else
        shared._one(tile.locator('.gui__builder-card--handler'),'Captured survey widget drag handle changed'))
    drag_options={}
    if profile.get('creation_drag')=='tile':
        icon=shared._one(tile.locator('.gui__builder-card--icon'),'Survey dropdown drag icon changed')
        box=tile.bounding_box();icon_box=icon.bounding_box()
        if (not box or not icon_box or min(box['width'],box['height'],icon_box['width'],icon_box['height'])<4):
            raise Stop('Survey dropdown drag source has no safe geometry')
        drag_options['source_position']={'x':icon_box['x']-box['x']+icon_box['width']/2,
                                         'y':icon_box['y']-box['y']+icon_box['height']/2}
    canvas=shared._one(owner.locator('.builder_sub_container'),'Survey widget insertion boundary changed')
    record={'configuration_sha256':fingerprint,'status':'INTENT_RECORDED'};secure_json(state,record)
    try:
        handle.drag_to(canvas,timeout=45000,**drag_options)
        wait_until(lambda:owner.locator('.form-field-wrapper').count()==1,'Survey widget insertion did not create exactly one widget')
        survey._close_initial(frame)
        if profile.get('collection_mode'):
            shared._set_survey_collection_mode(frame,owner.locator('.form-field-wrapper').nth(0),profile)
        after=survey.snapshot(frame,plan);target=plan['target_slide']-1
        if (len(after)!=len(before) or len(after[target])!=1 or after[target][0]['types']!=[profile['type']]
                or any(row!=before[index] for index,row in enumerate(after) if index!=target)):
            raise Stop('Survey widget insertion changed another slide or field family')
        previous=read_creation_question(frame,plan)
        _validate_new_default(kind,previous)
        item=owner.locator('.form-field-wrapper').nth(0)
        requested=_creation_readback(kind,plan['question'])
        _write_widget(frame,item,kind,previous,requested)
        if kind=='picture_choice':
            from playwright_recipes.quiz_picture_questions import _media
            for index,option in enumerate(plan['question']['options']):
                _media(page,frame,item,index,option)
        desired=survey.snapshot(frame,plan)
        if (len(desired)!=len(before) or len(desired[target])!=1
                or any(row!=before[index] for index,row in enumerate(desired) if index!=target)):
            raise Stop('Survey widget property authoring changed another slide')
        save=shared._one(frame.get_by_role('button',name='Save',exact=True),'Survey widget Save changed')
        click(save);wait_until(lambda:save.count()==1 and save.is_enabled(),'Survey widget Save did not finish')
        if kind=='html':shared.html_fields.confirm_save_warning(frame)
        reopen_editor(page,'survey',plan['expected_survey_name'],plan['start_url']);frame=survey._frame(page,plan)
        if read_creation_question(frame,plan)!=requested or survey.snapshot(frame,plan)!=desired:
            raise Stop('Survey widget did not persist after independent reopen')
        done=validate_creation_receipt({'status':'SURVEY_'+kind.upper()+'_SAVED_AND_REOPENED','editor_url':plan['start_url'],
            'target_slide':plan['target_slide'],'question':deepcopy(plan['question']),
            'configuration_sha256':fingerprint,'saved_snapshot':desired,'independent_readback':'VERIFIED'},plan)
        secure_json(state,{'configuration_sha256':fingerprint,'status':'SAVED_AND_REOPENED','receipt':done})
        return done
    except Exception as error:
        record.update(status='NEEDS_RECONCILIATION',error_type=type(error).__name__);secure_json(state,record)
        raise
