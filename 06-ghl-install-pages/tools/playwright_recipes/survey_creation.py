"""Journal a complete authored new-survey shell and ordered per-slide writers.

Each question batch has its own child intent/API/native journal. The final
receipt binds the whole saved slide/control inventory after an independent
list reopen; a successful child does not establish whole-survey completion.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright_recipes import radio_dependencies as radio, survey_radio_creation as shell, survey_blank_shell as blank
from playwright_recipes.assessments import STANDARD_FIELDS, reopen_editor, read_editor_title
from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.skill6_playwright import Stop, assert_tenant, click, secure_json, zhc


ACTION='native_survey_creation'
COMMON=('location_id','location_name','start_url')


def _slide_count(plan):
    return plan['slide_count'] if 'slide_count' in plan else len(plan['standard_fields'])


def _binding(value,plan):
    return blank.validate_binding(value,plan) if 'slide_count' in plan else shell._binding(value,plan)


def validate_inputs(value):
    if (not isinstance(value,dict) or set(value) not in (set(COMMON)|{'name','allow_creation','standard_fields','question_batches'},
                set(COMMON)|{'name','allow_creation','slide_count','question_batches'})
            or value['allow_creation'] is not True):
        raise Stop('New survey creation requires an exclusive authored slide/question plan')
    for key in ('location_id','location_name','name'):
        item=value[key]
        if (not isinstance(item,str) or not item.strip() or item!=item.strip() or len(item)>500
                or any(ord(c)<32 for c in item)):
            raise Stop('New survey creation requires its exact '+key)
    radio.delivery._id(value['location_id'],'location_id')
    if 'slide_count' in value:
        if type(value['slide_count']) is not int or not 1<=value['slide_count']<=100:
            raise Stop('New empty survey requires one to 100 explicitly requested slides')
    else:
        standard=value['standard_fields']
        if (not isinstance(standard,list) or not 1<=_slide_count(value)<=len(STANDARD_FIELDS)
                or any(not isinstance(item,str) or item not in STANDARD_FIELDS for item in standard)
                or len(set(standard))!=_slide_count(value)):
            raise Stop('Standard-field survey shell requires unique captured fields, one per slide')
    try:source=urlsplit(value['start_url']);port=source.port
    except (TypeError,ValueError):raise Stop('New survey list URL is malformed') from None
    if (source.scheme!='https' or not source.hostname or source.username is not None or source.password is not None
            or port not in (None,443) or source.query or source.fragment
            or source.path!='/v2/location/'+value['location_id']+'/survey-builder/main'):
        raise Stop('New survey creation must start at its exact same-location native list')
    batches=value['question_batches']
    if not isinstance(batches,list) or not 1<=len(batches)<=100:
        raise Stop('New survey questions require one to 100 explicit ordered batches')
    questions=[]
    for batch in batches:
        if (not isinstance(batch,dict) or set(batch)!={'kind','target_slide','questions'}
                or batch['kind']!='radio' or type(batch['target_slide']) is not int
                or not 1<=batch['target_slide']<=_slide_count(value)):
            raise Stop('Survey question batches need a captured writer and exact existing target slide')
        radio.validate_inputs({'location_id':value['location_id'],'questions':batch['questions']})
        questions.extend(batch['questions'])
    # Cross-batch conflicts must stop before the shell and the first API POST.
    radio.validate_inputs({'location_id':value['location_id'],'questions':questions})
    result=deepcopy(value)
    result['name']=zhc(result['name'])
    return result


def payload_from_inputs(value):
    return validate_inputs({key:item for key,item in value.items() if key not in ('publish','auth_activation')})


def validate(step):
    if (not isinstance(step,dict) or set(step)-{'id','action','payload'}
            or step.get('action',ACTION)!=ACTION):
        raise Stop('Unsupported whole-survey creation action')
    return validate_inputs(step.get('payload'))


def configuration_hash(plan):
    return hashlib.sha256(json.dumps(validate_inputs(plan),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_runtime(job,capability):
    if not isinstance(job.get('steps'),list) or len(job['steps'])!=1:
        raise Stop('Whole-survey creation requires its own independently journaled job')
    plan=validate(job['steps'][0])
    if any(plan[key]!=job.get(key) for key in COMMON):
        raise Stop('Whole-survey creation belongs to another parent location/list')
    questions=[question for batch in plan['question_batches'] for question in batch['questions']]
    radio.validate_capability(capability,plan['location_id'],creation=any(q['expected_id'] is None for q in questions))


def _batch_plan(plan,binding,batch):
    return {**{key:plan[key] for key in COMMON},'start_url':binding['editor_url'],
        'expected_slide_count':_slide_count(plan),'slide_labels':binding['slide_labels'],
        'target_slide':batch['target_slide'],'questions':deepcopy(batch['questions'])}


def _native_step(plan,binding,batch,fields):
    from playwright_recipes.recipe_cli import compile_recipe
    return compile_recipe('surveys.configure',{**{key:plan[key] for key in COMMON},
        'start_url':binding['editor_url'],'configuration':{'expected_slide_count':_slide_count(plan),
            'slide_labels':binding['slide_labels'],'target_slide':batch['target_slide'],'object_fields':deepcopy(fields),
            'field_dependencies':{'status':'VERIFIED','provider':'skill44','location_id':plan['location_id'],
                'observed_at':0,'operation':'custom_fields.get','http_status':200,'fields':deepcopy(fields)}}})['steps'][0]


def _definitions(plan,batch,fields):
    if not isinstance(fields,list) or len(fields)!=len(batch['questions']):
        raise Stop('Survey batch completion omits authored question definitions')
    ids=set()
    for authored,actual in zip(batch['questions'],fields):
        if (not isinstance(actual,dict) or set(actual)!={'id','name','field_key','data_type','options'}
                or actual['data_type']!='RADIO'
                or any(actual[key]!=authored[key] for key in ('name','field_key','options'))
                or authored['expected_id'] is not None and actual['id']!=authored['expected_id']):
            raise Stop('Survey batch completion changed an authored Radio definition')
        identity=radio.delivery._id(actual['id'],'completed Radio field id')
        if identity in ids:raise Stop('Survey batch completion repeats a field identity')
        ids.add(identity)
    return deepcopy(fields)


def _preflight_radio_definitions(plan,capability,api):
    """Prove every reuse/absence before creating any part of the new survey."""
    receipt=radio.validate_capability(capability,plan['location_id'],version_resolver=api.version_for)
    listed=radio._request(api,receipt,'list',plan['location_id'])
    if set(listed)!={'customFields'} or not isinstance(listed['customFields'],list):
        raise Stop('Whole-survey preflight needs the complete measured field inventory')
    identities=set()
    for field in listed['customFields']:
        if (not isinstance(field,dict) or field.get('locationId')!=plan['location_id']
                or not radio._text(field.get('name')) or not isinstance(field.get('fieldKey'),str)):
            raise Stop('Whole-survey field preflight lacks exact same-location identity')
        identity=radio.delivery._id(field.get('id'),'preflight field id')
        if identity in identities:raise Stop('Whole-survey field preflight repeats an API identity')
        identities.add(identity)
    for batch in plan['question_batches']:
        for question in batch['questions']:
            matches=[field for field in listed['customFields'] if field['id']==question['expected_id']
                or field['name'].casefold()==question['name'].casefold()
                or field['fieldKey'].casefold()==question['field_key'].casefold()]
            if question['expected_id'] is None:
                if matches:raise Stop('A whole-survey expected-absent Radio name/key already exists')
            else:
                if len(matches)!=1 or matches[0]['id']!=question['expected_id']:
                    raise Stop('A whole-survey requested Radio reuse identity is absent or conflicted')
                radio._get(api,receipt,plan,question,question['expected_id'])


def _validate_inventory(value,plan,binding,completed):
    if (not isinstance(value,dict) or set(value)!={'slide_labels','slides'}
            or value['slide_labels']!=binding['slide_labels'] or not isinstance(value['slides'],list)
            or len(value['slides'])!=_slide_count(plan)):
        raise Stop('Whole-survey completion lacks its complete saved slide inventory')
    fields_by_slide={index:[] for index in range(1,_slide_count(plan)+1)}
    for authored,done in zip(plan['question_batches'],completed):
        fields_by_slide[authored['target_slide']].extend(done['api_fields'])
    globally_seen=set();native_queries={STANDARD_FIELDS[field][1] for field in plan.get('standard_fields',[])}
    for index,slide in enumerate(value['slides'],1):
        if (not isinstance(slide,dict) or set(slide)!={'canvas','radio_fields'}
                or not isinstance(slide['canvas'],list) or not isinstance(slide['radio_fields'],list)):
            raise Stop('Whole-survey completion contains a malformed slide inventory')
        expected=fields_by_slide[index]
        if len(slide['radio_fields'])!=len(expected):raise Stop('Whole-survey completion omits a saved Radio owner')
        ids={field['id'] for field in expected}
        if globally_seen.intersection(ids):raise Stop('Whole-survey completion repeats a question across owners')
        globally_seen.update(ids)
        for field,observed in zip(expected,slide['radio_fields']):
            if (not isinstance(observed,dict) or set(observed)!={'id','query_key'} or observed['id']!=field['id']
                    or not isinstance(observed['query_key'],str) or not observed['query_key']
                    or any(c.isspace() or ord(c)<32 for c in observed['query_key'])):
                raise Stop('Whole-survey completion changed its exact native question/query identity')
            if observed['query_key'] in native_queries:raise Stop('Whole-survey saved native Query Keys are not unique')
            native_queries.add(observed['query_key'])
        canvas=slide['canvas'];baseline=binding['canvas'] if 'canvas' in binding else binding['slides'][index-1]['canvas']
        original=[];seen=[]
        for row in canvas:
            if not isinstance(row,dict) or set(row)!={'types','names'} or not isinstance(row['names'],list):
                raise Stop('Whole-survey saved canvas row is malformed')
            field=next((f for f in expected if row['types']==['RADIO']
                and row['names']==[['INPUT','radio',f['id']] for _ in f['options']]),None)
            if field is not None:seen.append(field['id'])
            else:original.append(row)
        if original!=baseline or seen!=[field['id'] for field in expected]:
            raise Stop('Whole-survey saved canvas changed an original control or authored question order')
    return deepcopy(value)


def _inventory(page,plan,binding,completed):
    from playwright_recipes.forms_advanced import _canvas_identity,_read_object_binding
    if page.url!=binding['editor_url']:raise Stop('Whole-survey inventory changed its exact editor')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1 or read_editor_title(title)!=plan['name']:raise Stop('Whole-survey inventory changed its exact name')
    shell.survey_fields._close_initial(frame)
    click(frame.get_by_role('tab',name='Edit',exact=True))
    slides=frame.locator('.survey-form-container')
    if slides.count()!=_slide_count(plan) or frame.get_by_role('button',name='Add Slide',exact=True).count()!=_slide_count(plan):
        raise Stop('Whole-survey saved slide count changed')
    rows=[]
    for index in range(1,_slide_count(plan)+1):
        owner=slides.nth(index-1);label=owner.locator('.builder-form-name')
        if label.count()!=1 or 'P'+str(index)+' - '+label.inner_text().strip()!=binding['slide_labels'][index-1]:
            raise Stop('Whole-survey saved slide order/name changed')
        fields=[]
        for authored,done in zip(plan['question_batches'],completed):
            if authored['target_slide']!=index:continue
            for field in done['api_fields']:
                fields.append({'id':field['id'],'query_key':_read_object_binding(frame,owner,field)})
        rows.append({'canvas':_canvas_identity(owner),'radio_fields':fields})
    return _validate_inventory({'slide_labels':deepcopy(binding['slide_labels']),'slides':rows},plan,binding,completed)


def validate_receipt(value,step):
    from playwright_recipes.editor_replay import _result
    plan=validate(step)
    if (not isinstance(value,dict) or set(value)!={'status','location_id','editor_url','configuration_sha256',
            'shell_binding','question_batches','saved_inventory','independent_readback','behavior_verified','submission_verified'}
            or value['status']!='SURVEY_CREATED_SAVED_AND_REOPENED' or value['location_id']!=plan['location_id']
            or value['configuration_sha256']!=configuration_hash(plan) or value['independent_readback']!='VERIFIED'
            or value['behavior_verified'] is not False or value['submission_verified'] is not False):
        raise Stop('Whole-survey completion is malformed or unbound')
    binding=_binding(value['shell_binding'],plan)
    if binding['editor_url']!=value['editor_url']:raise Stop('Whole-survey completion changed its created editor')
    completed=value['question_batches']
    if not isinstance(completed,list) or len(completed)!=len(plan['question_batches']):
        raise Stop('Whole-survey completion omits a question stage')
    for authored,done in zip(plan['question_batches'],completed):
        if (not isinstance(done,dict) or set(done)!={'kind','target_slide','api_fields','native_receipt'}
                or done['kind']!=authored['kind'] or done['target_slide']!=authored['target_slide']):
            raise Stop('Whole-survey question stage changed its authored owner')
        fields=_definitions(plan,authored,done['api_fields'])
        native=_native_step(plan,binding,authored,fields)
        _result(native,done['native_receipt'],{**{key:plan[key] for key in COMMON},'start_url':binding['editor_url']})
    _validate_inventory(value['saved_inventory'],plan,binding,completed)
    return deepcopy(value)


def configure(page,step,evidence_root,*,capability):
    from playwright_recipes.recipe_cli import compile_recipe
    from playwright_recipes.skill6_playwright import run_on_page,validate_job
    from playwright_recipes.editor_replay import completed_editor_replay
    plan=validate(step)
    questions=[q for batch in plan['question_batches'] for q in batch['questions']]
    radio.validate_capability(capability,plan['location_id'],creation=any(q['expected_id'] is None for q in questions))
    root=Path(evidence_root).resolve();shell_root=root/'shell';binding_path=root/'shell-binding.json'
    stage_roots=[root/('question-batch-'+str(index).zfill(3)) for index in range(len(plan['question_batches']))]
    if any(path.is_symlink() for path in [shell_root,binding_path,*stage_roots]):
        raise Stop('Whole-survey evidence contains a symlink')
    api=radio.Skill44RadioTransport()
    # Once any stage intent exists, its exact retained journal governs replay;
    # newly created definitions must never be mistaken for pre-existing keys.
    if not any(journal_present(path/'delivery-state.json') or journal_present(path/'native'/'state.json') for path in stage_roots):
        _preflight_radio_definitions(plan,capability,api)
    shell_inputs={key:value for key,value in plan.items() if key not in ('question_batches','slide_count')}
    shell_job=validate_job(compile_recipe('surveys.create',shell_inputs),root)
    if journal_present(binding_path):
        stored=read_journal(binding_path)
        original=None if 'slide_count' in plan else completed_editor_replay(shell_root/'state.json',shell_job,hashlib.sha256(json.dumps(shell_job,sort_keys=True).encode()).hexdigest())
        if (not isinstance(stored,dict) or set(stored)!={'configuration_sha256','shell'}
                or stored['configuration_sha256']!=configuration_hash(plan)
                or original is not None and (len(original['results'])!=1
                or original['results'][0]['result'].get('editor_url')!=stored.get('shell',{}).get('editor_url'))):
            raise Stop('Whole-survey shell journal belongs to another authored plan')
        binding=_binding(stored['shell'],plan)
        if 'slide_count' in plan and blank.completed_binding(plan,shell_root)!=binding:
            raise Stop('Whole-survey blank shell binding differs from its original creation journal')
    else:
        if 'slide_count' in plan:
            binding=blank.configure(page,plan,shell_root)
        else:
            saved=run_on_page(page,shell_job,shell_root)
            results=saved.get('results',[])
            if len(results)!=1 or results[0].get('result',{}).get('status')!='ASSESSMENT_SAVE_SUBMITTED':
                raise Stop('Whole-survey creation did not create a new saved shell')
            editor_url=results[0]['result'].get('editor_url')
            if page.url!=editor_url:reopen_editor(page,'survey',plan['name'],editor_url)
            binding=shell._shell(page,plan,editor_url)
            reopen_editor(page,'survey',plan['name'],editor_url)
            if shell._shell(page,plan,editor_url)!=binding:raise Stop('Whole-survey initial complete owner inventory did not persist')
        secure_json(binding_path,{'configuration_sha256':configuration_hash(plan),'shell':binding})
    if page.url!=binding['editor_url']:reopen_editor(page,'survey',plan['name'],binding['editor_url'])
    completed=[]
    for batch,stage_root in zip(plan['question_batches'],stage_roots):
        child=radio.build_survey_questions(_batch_plan(plan,binding,batch),stage_root,page=page,capability=capability,transport=api)
        api_state=read_journal(stage_root/'delivery-state.json')
        if (api_state.get('schema')!=radio.SCHEMA or api_state.get('location_id')!=plan['location_id']
                or api_state.get('fingerprint')!=radio.configuration_hash({'location_id':plan['location_id'],'questions':batch['questions']})
                or api_state.get('status')!='API_STEPS_COMPLETE' or api_state.get('current_step_status')!='VERIFIED'
                or api_state.get('fields')!=child.get('object_fields')):
            raise Stop('Whole-survey question stage lacks its original verified API journal')
        job=read_journal(stage_root/'native-question-job.json')
        saved=completed_editor_replay(stage_root/'native'/'state.json',job,hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest())
        if len(saved['results'])!=1:raise Stop('Whole-survey question stage has an unexpected native step inventory')
        completed.append({'kind':batch['kind'],'target_slide':batch['target_slide'],'api_fields':child['object_fields'],
            'native_receipt':saved['results'][0]['result']})
        _inventory(page,plan,binding,completed)
    before=_inventory(page,plan,binding,completed)
    reopen_editor(page,'survey',plan['name'],binding['editor_url'])
    after=_inventory(page,plan,binding,completed)
    if before!=after:raise Stop('Whole-survey complete saved question inventory did not persist on final independent reopen')
    return validate_receipt({'status':'SURVEY_CREATED_SAVED_AND_REOPENED','location_id':plan['location_id'],
        'editor_url':binding['editor_url'],'configuration_sha256':configuration_hash(plan),'shell_binding':binding,
        'question_batches':completed,'saved_inventory':after,'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False},step)
