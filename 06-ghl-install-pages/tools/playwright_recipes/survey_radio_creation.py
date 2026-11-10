"""Create a native survey shell, reopen it, then place authored Radio questions.

Uses the maintained assessment creator and measured Radio dependency/placement
chain. Shell, API and native writes retain separate uncertain-intent journals.
The enclosing editor runner owns the same-location lease and final receipt.
Each captured standard field owns one new slide; multi-slide plans explicitly
identify the target slide and bind every untouched slide before placement.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright_recipes import radio_dependencies as radio, survey_fields
from playwright_recipes.assessments import reopen_editor, STANDARD_FIELDS, read_editor_title
from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.skill6_playwright import Stop, assert_tenant, secure_json

ACTION='native_survey_radio_creation'
COMMON=('location_id','location_name','start_url')


def validate_inputs(inputs):
    if (not isinstance(inputs,dict)
            or set(inputs)-{'target_slide'}!=set(COMMON)|{'name','allow_creation','standard_fields','radio_questions'}
            or inputs['allow_creation'] is not True
            or not isinstance(inputs['standard_fields'],list)
            or not 1<=len(inputs['standard_fields'])<=len(STANDARD_FIELDS)
            or any(not isinstance(field,str) or field not in STANDARD_FIELDS for field in inputs['standard_fields'])
            or len(set(inputs['standard_fields']))!=len(inputs['standard_fields'])):
        raise Stop('Survey Radio creation requires explicit creation, unique captured standard fields and authored Radio questions')
    count=len(inputs['standard_fields'])
    target=inputs.get('target_slide',1)
    if (count>1 and 'target_slide' not in inputs
            or type(target) is not int or not 1<=target<=count):
        raise Stop('Multi-slide Survey Radio creation requires its explicit existing target slide')
    for key in ('name','location_name'):
        value=inputs[key]
        if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>500 or any(ord(c)<32 for c in value):
            raise Stop('Survey creation requires its exact visible '+key)
    radio.validate_inputs({'location_id':inputs['location_id'],'questions':inputs['radio_questions']})
    try:
        url=urlsplit(inputs['start_url']);port=url.port
    except (TypeError,ValueError):raise Stop('Survey creation list URL is malformed') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or port not in (None,443) or url.query or url.fragment
            or url.path!='/v2/location/'+inputs['location_id']+'/survey-builder/main'):
        raise Stop('Survey Radio creation must start at the exact native survey list')
    return deepcopy(inputs)


def payload_from_inputs(data):
    return validate_inputs({key:value for key,value in data.items() if key not in ('publish','auth_activation')})


def validate(step):
    if isinstance(step,dict) and step.get('action')=='native_survey_creation':
        from playwright_recipes.survey_creation import validate as whole_validate
        return whole_validate(step)
    if not isinstance(step,dict) or set(step)-{'id','action','payload'} or step.get('action',ACTION)!=ACTION:
        raise Stop('Unsupported survey Radio creation action')
    return validate_inputs(step.get('payload'))


def configuration_hash(plan):
    return hashlib.sha256(json.dumps(validate_inputs(plan),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_runtime(job,capability):
    if any(step.get('action')=='native_survey_creation' for step in job.get('steps',[]) if isinstance(step,dict)):
        from playwright_recipes.survey_creation import validate_runtime as whole_runtime
        return whole_runtime(job,capability)
    steps=job.get('steps')
    if not isinstance(steps,list) or len(steps)!=1:
        raise Stop('Survey Radio creation requires its own independently journaled job')
    plan=validate(steps[0])
    if any(plan[key]!=job.get(key) for key in COMMON):raise Stop('Survey creation belongs to another parent location/list')
    radio.validate_capability(capability,plan['location_id'],creation=any(q['expected_id'] is None for q in plan['radio_questions']))


def _standard_binding(standard):
    return {'label':standard,'placeholder':STANDARD_FIELDS[standard][0],
        'type':'email' if standard=='Email' else 'text'}


def _canvas_binding(value,standard):
    expected=_standard_binding(standard);kind=expected['type']
    if (not isinstance(value,dict) or set(value)!={'canvas','standard_field'}
            or value['standard_field']!=expected):
        raise Stop('Survey shell binding changed its authored standard field')
    rows=value['canvas'];standard_count=0
    if not isinstance(rows,list) or not rows:raise Stop('Survey shell canvas is not positively loaded')
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'types','names'}
                or not isinstance(row['types'],list) or len(row['types'])!=1
                or row['types'][0] not in (kind,'submit','h1','terms_and_conditions')
                or not isinstance(row['names'],list)):
            raise Stop('Survey shell binding contains an unsupported canvas row')
        for name in row['names']:
            if (not isinstance(name,list) or len(name)!=3 or name[0] not in ('INPUT','TEXTAREA','SELECT')
                    or any(item is not None and (not isinstance(item,str) or any(ord(c)<32 for c in item)) for item in name[1:])):
                raise Stop('Survey shell binding has malformed canvas control identities')
        if row['types']==[kind]:
            if len(row['names'])!=1 or row['names'][0][:2]!=['INPUT',kind]:
                raise Stop('Survey shell standard field lacks its captured native input type')
            standard_count+=1
    if standard_count!=1:raise Stop('Each survey shell slide must retain exactly one authored standard field')
    return deepcopy(value)


def _binding(value,plan):
    count=len(plan['standard_fields'])
    keys={'editor_url','slide_labels','canvas','standard_field'} if count==1 else {'editor_url','slide_labels','slides'}
    if (not isinstance(value,dict) or set(value)!=keys
            or not isinstance(value['editor_url'],str)):
        raise Stop('Survey shell binding is incomplete')
    url=urlsplit(value['editor_url']);origin=urlsplit(plan['start_url'])
    if ((url.scheme,url.netloc)!=(origin.scheme,origin.netloc) or url.query or url.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',url.path)):
        raise Stop('Survey shell binding changed its exact created origin/location/editor')
    labels=value['slide_labels']
    if (not isinstance(labels,list) or len(labels)!=count
            or any(not isinstance(label,str) or not re.fullmatch('P'+str(index)+r' - .+',label)
                or any(ord(c)<32 for c in label) for index,label in enumerate(labels,1))):
        raise Stop('Survey shell binding needs its complete exact numbered slide inventory')
    if count==1:
        _canvas_binding({key:value[key] for key in ('canvas','standard_field')},plan['standard_fields'][0])
    else:
        if not isinstance(value['slides'],list) or len(value['slides'])!=count:
            raise Stop('Survey shell binding omits a slide owner')
        for slide,standard in zip(value['slides'],plan['standard_fields']):
            _canvas_binding(slide,standard)
    return deepcopy(value)


def _shell(page,plan,editor_url):
    from playwright_recipes.forms_advanced import _canvas_identity
    from playwright_recipes.skill6_playwright import click
    if page.url!=editor_url:raise Stop('Created survey editor identity changed')
    parsed=urlsplit(editor_url);origin=urlsplit(plan['start_url'])
    if ((parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc) or parsed.query or parsed.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/survey-builder-v2/[A-Za-z0-9_-]+',parsed.path)):
        raise Stop('Created survey does not identify one exact same-location editor')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['name']:raise Stop('Created survey name differs from its authored name')
    survey_fields._close_initial(frame)
    click(frame.get_by_role('tab',name='Edit',exact=True))
    slides=frame.locator('.survey-form-container')
    count=len(plan['standard_fields'])
    if slides.count()!=count or frame.get_by_role('button',name='Add Slide',exact=True).count()!=count:
        raise Stop('New survey shell differs from the requested complete slide inventory')
    labels=[];owners=[]
    for index,standard in enumerate(plan['standard_fields']):
        owner=slides.nth(index);label=owner.locator('.builder-form-name')
        if label.count()!=1 or not label.inner_text().strip():raise Stop('New survey slide label is unavailable')
        placeholder,_=STANDARD_FIELDS[standard]
        field=owner.get_by_placeholder(placeholder,exact=True)
        if (field.count()!=1 or not field.is_visible()
                or field.get_attribute('type')!=('email' if standard=='Email' else 'text')):
            raise Stop('New survey slide does not contain its captured authored standard-field type')
        labels.append('P'+str(index+1)+' - '+label.inner_text().strip())
        owners.append({'canvas':_canvas_identity(owner),
            'standard_field':{'label':standard,'placeholder':field.get_attribute('placeholder'),
                'type':field.get_attribute('type')}})
    value={'editor_url':editor_url,'slide_labels':labels}
    if count==1:value.update(owners[0])
    else:value['slides']=owners
    return _binding(value,plan)


def _native_step(plan,binding,fields):
    from playwright_recipes.recipe_cli import compile_recipe
    return compile_recipe('surveys.configure',{**{key:plan[key] for key in COMMON},
        'start_url':binding['editor_url'],'configuration':{'expected_slide_count':len(plan['standard_fields']),
            'slide_labels':binding['slide_labels'],'target_slide':plan.get('target_slide',1),'object_fields':fields,
            'field_dependencies':{'status':'VERIFIED','provider':'skill44',
                'location_id':plan['location_id'],'observed_at':0,
                'operation':'custom_fields.get','http_status':200,'fields':deepcopy(fields)}}})['steps'][0]


def _untouched_slides(page,plan,binding):
    """Read every non-target owner after the native writer's independent reopen.

    The object-field writer proves its target's full before/after inventory.
    Its shared slide guard counts other owners, so multi-slide creation also
    retains their complete control identity, including same-count replacements.
    """
    if len(plan['standard_fields'])==1:return
    from playwright_recipes.forms_advanced import _canvas_identity
    from playwright_recipes.skill6_playwright import click
    if page.url!=binding['editor_url']:raise Stop('Survey changed after its Radio placement read-back')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['name']:raise Stop('Survey name changed after Radio placement')
    survey_fields._close_initial(frame)
    click(frame.get_by_role('tab',name='Edit',exact=True))
    slides=frame.locator('.survey-form-container')
    if (slides.count()!=len(plan['standard_fields'])
            or frame.get_by_role('button',name='Add Slide',exact=True).count()!=len(plan['standard_fields'])):
        raise Stop('Survey slide inventory changed after Radio placement')
    for index,standard in enumerate(plan['standard_fields']):
        owner=slides.nth(index);label=owner.locator('.builder-form-name')
        if label.count()!=1 or 'P'+str(index+1)+' - '+label.inner_text().strip()!=binding['slide_labels'][index]:
            raise Stop('Survey slide order changed after Radio placement')
        if index+1==plan['target_slide']:continue
        expected=binding['slides'][index]
        field=owner.get_by_placeholder(STANDARD_FIELDS[standard][0],exact=True)
        if (field.count()!=1 or not field.is_visible()
                or field.get_attribute('type')!=expected['standard_field']['type']
                or _canvas_identity(owner)!=expected['canvas']):
            raise Stop('Radio placement changed an unrequested survey slide control identity')


def validate_receipt(value,step):
    if isinstance(step,dict) and step.get('action')=='native_survey_creation':
        from playwright_recipes.survey_creation import validate_receipt as whole_receipt
        return whole_receipt(value,step)
    from playwright_recipes.editor_replay import _result
    plan=validate(step)
    keys={'status','location_id','editor_url','configuration_sha256','shell_binding','api_fields',
        'native_receipt','independent_readback','behavior_verified','submission_verified'}
    if (not isinstance(value,dict) or set(value)!=keys or value['status']!='SURVEY_RADIO_SAVED_AND_REOPENED'
            or value['location_id']!=plan['location_id'] or value['configuration_sha256']!=configuration_hash(plan)
            or value['independent_readback']!='VERIFIED' or value['behavior_verified'] is not False
            or value['submission_verified'] is not False):
        raise Stop('Survey Radio creation completion is malformed or unbound')
    binding=_binding(value['shell_binding'],plan)
    if binding['editor_url']!=value['editor_url']:
        raise Stop('Survey Radio completion changed its created editor binding')
    radio._survey_plan({**{key:plan[key] for key in COMMON},'start_url':binding['editor_url'],
        'expected_slide_count':len(plan['standard_fields']),'slide_labels':binding['slide_labels'],
        'target_slide':plan.get('target_slide',1),
        'questions':plan['radio_questions']})
    fields=value['api_fields']
    if not isinstance(fields,list) or len(fields)!=len(plan['radio_questions']):raise Stop('Survey Radio completion omits authored definitions')
    ids=set()
    for requested,field in zip(plan['radio_questions'],fields):
        if (not isinstance(field,dict) or set(field)!={'id','name','field_key','data_type','options'}
                or any(field[key]!=requested[key] for key in ('name','field_key','options')) or field['data_type']!='RADIO'
                or requested['expected_id'] is not None and field['id']!=requested['expected_id']):
            raise Stop('Survey Radio completion changes an authored field definition')
        identity=radio.delivery._id(field['id'],'completed Radio field id')
        if identity in ids:raise Stop('Survey Radio completion repeats a field identity')
        ids.add(identity)
    native=_native_step(plan,binding,fields)
    result=deepcopy(value)
    result['native_receipt']=_result(native,value['native_receipt'],
        {**{key:plan[key] for key in COMMON},'start_url':binding['editor_url']})
    return result


def configure(page,step,evidence_root,*,capability):
    if isinstance(step,dict) and step.get('action')=='native_survey_creation':
        from playwright_recipes.survey_creation import configure as whole_configure
        return whole_configure(page,step,evidence_root,capability=capability)
    from playwright_recipes.recipe_cli import compile_recipe
    from playwright_recipes.skill6_playwright import run_on_page,validate_job
    from playwright_recipes.editor_replay import completed_editor_replay
    plan=validate(step)
    radio.validate_capability(capability,plan['location_id'],creation=any(q['expected_id'] is None for q in plan['radio_questions']))
    root=Path(evidence_root).resolve();shell_root=root/'shell';question_root=root/'questions'
    binding_path=root/'shell-binding.json'
    if any(path.is_symlink() for path in (shell_root,question_root,binding_path)):
        raise Stop('Survey creation evidence contains a symlink')
    shell_inputs={key:value for key,value in plan.items() if key not in ('radio_questions','target_slide')}
    shell_job=validate_job(compile_recipe('surveys.create',shell_inputs),root)
    if journal_present(binding_path):
        binding=read_journal(binding_path)
        original=completed_editor_replay(shell_root/'state.json',shell_job,
            hashlib.sha256(json.dumps(shell_job,sort_keys=True).encode()).hexdigest())
        if (len(original['results'])!=1 or not isinstance(binding,dict)
                or original['results'][0]['result'].get('editor_url')!=binding.get('shell',{}).get('editor_url')):
            raise Stop('Survey shell binding differs from its original creation journal')
    else:
        # A failed/uncertain shell journal refuses replay. A completed shell
        # job may be read back to establish its retained editor before chaining.
        shell_result=run_on_page(page,shell_job,shell_root)
        rows=shell_result.get('results',[])
        if len(rows)!=1 or rows[0].get('result',{}).get('status')!='ASSESSMENT_SAVE_SUBMITTED':
            raise Stop('Survey shell was not a newly created saved assessment')
        editor_url=rows[0]['result'].get('editor_url')
        if page.url!=editor_url:reopen_editor(page,'survey',plan['name'],editor_url)
        before=_shell(page,plan,editor_url)
        reopen_editor(page,'survey',plan['name'],editor_url)
        if _shell(page,plan,editor_url)!=before:raise Stop('New survey complete owner identity did not persist on reopen')
        binding={'configuration_sha256':configuration_hash(plan),'shell':before}
        secure_json(binding_path,binding)
    if (not isinstance(binding,dict) or set(binding)!={'configuration_sha256','shell'}
            or binding['configuration_sha256']!=configuration_hash(plan)):
        raise Stop('Survey creation evidence belongs to another authored plan')
    shell=_binding(binding['shell'],plan)
    # Re-enter only the exact retained editor; never search/create another shell
    # after API or placement uncertainty. The native child journal controls replay.
    if page.url!=shell['editor_url']:
        reopen_editor(page,'survey',plan['name'],shell['editor_url'])
    current=_shell(page,plan,shell['editor_url'])
    if (current['slide_labels']!=shell['slide_labels']
            or not journal_present(question_root/'native'/'state.json') and current!=shell):
        raise Stop('Survey shell changed before its authored Radio dependency/placement chain')
    questions={**{key:plan[key] for key in COMMON},'start_url':shell['editor_url'],
        'expected_slide_count':len(plan['standard_fields']),'slide_labels':shell['slide_labels'],
        'target_slide':plan.get('target_slide',1),
        'questions':plan['radio_questions']}
    raw=radio.build_survey_questions(questions,question_root,page=page,capability=capability)
    _untouched_slides(page,plan,shell)
    api=read_journal(question_root/'delivery-state.json')
    if (api.get('schema')!=radio.SCHEMA or api.get('location_id')!=plan['location_id']
            or api.get('fingerprint')!=radio.configuration_hash({'location_id':plan['location_id'],'questions':plan['radio_questions']})
            or api.get('status')!='API_STEPS_COMPLETE' or api.get('current_step_status')!='VERIFIED'
            or api.get('fields')!=raw.get('object_fields')):
        raise Stop('Survey Radio completion lacks its original verified API journal')
    native_job=read_journal(question_root/'native-question-job.json')
    completed=completed_editor_replay(question_root/'native'/'state.json',native_job,
        hashlib.sha256(json.dumps(native_job,sort_keys=True).encode()).hexdigest())
    if len(completed['results'])!=1:raise Stop('Survey Radio placement has an unexpected native step inventory')
    result={'status':'SURVEY_RADIO_SAVED_AND_REOPENED','location_id':plan['location_id'],
        'editor_url':shell['editor_url'],'configuration_sha256':configuration_hash(plan),'shell_binding':shell,
        'api_fields':raw['object_fields'],'native_receipt':completed['results'][0]['result'],
        'independent_readback':'VERIFIED','behavior_verified':False,'submission_verified':False}
    return validate_receipt(result,step)
