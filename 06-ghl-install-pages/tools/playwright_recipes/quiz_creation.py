"""Create a marketing quiz through captured shell/question/scoring/result writers.

The fresh shell owns a generated editor identity; no caller-supplied editor ID
can redirect the chain. Every stage keeps its original intent journal and an
independent reopen receipt. Respondent submission and publication are separate.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright_recipes import quiz_choice_questions as choices, quiz_text_questions as native
from playwright_recipes.evidence_lease import journal_present, read_journal
from playwright_recipes.skill6_playwright import Stop, assert_tenant, secure_json, zhc
from playwright_recipes.assessments import reopen_editor

ACTION='native_quiz_creation'
COMMON=('location_id','location_name','start_url')


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _editor_url(plan,editor_url):
    source=urlsplit(plan['start_url'])
    try:target=urlsplit(editor_url);port=target.port
    except (TypeError,ValueError):raise Stop('Created quiz editor binding is malformed') from None
    if ((target.scheme,target.netloc)!=(source.scheme,source.netloc) or port not in (None,443)
            or target.username is not None or target.password is not None or target.query or target.fragment
            or not re.fullmatch('/v2/location/'+re.escape(plan['location_id'])+r'/quiz-builder-v2/[A-Za-z0-9_-]+',target.path)):
        raise Stop('Created quiz editor differs from its exact new same-location owner')
    return editor_url


def _questions(plan,editor_url):
    """Compile each captured insertion against the complete evolving page inventory."""
    from playwright_recipes.intake import QUIZ_CREATION,quiz_creation
    pages=[{'label':'Page 1','questions':[]}];steps=[]
    for index,batch in enumerate(plan['configuration']['question_batches']):
        if not isinstance(batch,dict) or len(batch)!=1 or not set(batch).issubset(QUIZ_CREATION):
            raise Stop('Quiz creation requires one captured question writer in each ordered batch')
        key,value=next(iter(batch.items()))
        allowed={'questions','acknowledge_shared_field_options'} if key in ('multiple_choice_questions','picture_choice_questions') else {'questions'}
        if not isinstance(value,dict) or set(value)-{'target_page'}!=allowed or not isinstance(value['questions'],list) or len(value['questions'])!=1:
            raise Stop('Each new-quiz batch authors one question and an optional exact target page; editor/page inventories remain owned')
        value=deepcopy(value)
        target=value.pop('target_page',1 if index==0 else len(pages)+1)
        if (type(target) is not int or not 1<=target<=len(pages)+1 or index==0 and target!=1):
            raise Stop('New quiz target_page must identify an existing owner or its single next new page')
        create_page=target==len(pages)+1
        if key=='short_answer_questions':
            if not isinstance(value['questions'][0],dict) or value['questions'][0].get('field_type')!='TEXT':
                raise Stop('Short Answer creation requires its captured TEXT type')
            key='written_answer_questions'
        payload={**value,'expected_quiz_name':plan['name'],'pages':deepcopy(pages),'target_page':target}
        if create_page:payload.update(create_page=True,new_page_label='Page '+str(target))
        data={**{key:plan[key] for key in COMMON},'start_url':editor_url,'configuration':{key:payload}}
        action,payload=quiz_creation(data)
        steps.append({'id':'question_'+str(index+1),'action':action,'payload':payload})
        authored=deepcopy(payload['questions'][0])
        if action=='quiz_picture_choices':
            from playwright_recipes.quiz_picture_questions import _authored
            authored=_authored(authored)
        if create_page:pages.append({'label':'Page '+str(target),'questions':[]})
        pages[target-1]['questions'].append(authored)
    return {'location_id':plan['location_id'],'location_name':plan['location_name'],'start_url':editor_url,'steps':steps},pages


def _configuration(plan,editor_url):
    from playwright_recipes.quiz_ui import validate as validate_scoring
    from playwright_recipes.quiz_results import validate as validate_results
    scoring=validate_scoring({'action':'quiz_configuration',**deepcopy(plan['configuration']['scoring'])})
    results=validate_results({'action':'quiz_results','result_page':deepcopy(plan['configuration']['result_page'])})
    return {**{key:plan[key] for key in COMMON},'start_url':editor_url,
            'steps':[{'id':'scoring',**scoring},{'id':'results',**results}]}


def validate_inputs(inputs):
    required=set(COMMON)|{'name','allow_creation','configuration'}
    if not isinstance(inputs,dict) or set(inputs)!=required or inputs['allow_creation'] is not True:
        raise Stop('Marketing quiz creation requires its exact list owner, explicit new creation and complete authored configuration')
    plan=deepcopy(inputs)
    for key in ('name','location_name'):
        value=plan[key]
        if (not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>500
                or any(ord(c)<32 for c in value)):
            raise Stop('Quiz creation requires its exact visible '+key)
    plan['name']=zhc(plan['name'])
    loc=plan['location_id']
    if not isinstance(loc,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',loc):raise Stop('Quiz location ID is invalid')
    try:source=urlsplit(plan['start_url']);port=source.port
    except (TypeError,ValueError):raise Stop('Quiz creation list URL is malformed') from None
    if (source.scheme!='https' or not source.hostname or source.username is not None or source.password is not None
            or port not in (None,443) or source.query or source.fragment
            or source.path!='/v2/location/'+loc+'/quiz-builder/main'):
        raise Stop('Quiz creation must start at its exact native same-location list')
    config=plan['configuration']
    if (not isinstance(config,dict) or set(config)!={'question_batches','scoring','result_page'}
            or not isinstance(config['question_batches'],list) or not 1<=len(config['question_batches'])<=50
            or not isinstance(config['scoring'],dict) or set(config['scoring']).intersection({'id','action'})
            or not isinstance(config['result_page'],dict)):
        raise Stop('Marketing quiz creation needs ordered question batches, explicit scoring and result-page profiles')
    # This synthetic route is used ONLY for preflight schema validation. It is
    # never returned in a job or visited; execution recompiles from the retained
    # independently reopened generated editor binding.
    schema_url=source.scheme+'://'+source.netloc+'/v2/location/'+loc+'/quiz-builder-v2/SCHEMA_VALIDATION_ONLY'
    question_job,pages=_questions(plan,schema_url)
    configuration=_configuration(plan,schema_url)
    scoring=configuration['steps'][0];questions=[question for owner in pages for question in owner['questions']]
    scored=scoring.get('questions',[])
    indexes={index for index,question in enumerate(questions) if question['field_type'] in ('RADIO','CHECKBOX')}
    if (not indexes or scoring.get('expected_question_count')!=len(questions)
            or {question['index'] for question in scored}!=indexes):
        raise Stop('Creation scoring must explicitly cover every authored captured RADIO/CHECKBOX question and full canvas count')
    if scoring.get('category_changes'):
        raise Stop('Fresh quiz category renames require a separately inventoried template')
    available={'Overall Only',*scoring.get('categories',[])}
    for target in scored:
        authored=questions[target['index']]
        if (set(target)!={'index','expected_question','expected_query_key','options'}
                or target['expected_question']!=authored['question'] or target['expected_query_key']!=authored['query_key']
                or [option['label'] for option in target['options']]!=authored['options']
                or any(set(option)!={'label','category','score'} or option['category'] not in available for option in target['options'])):
            raise Stop('Creation scoring must bind the exact authored question/key/options without additional question rewrites')
    if 'tiers' in scoring and 'expected_tiers' not in scoring:
        raise Stop('Fresh quiz tier edits require the complete captured previous range inventory')
    return plan


def payload_from_inputs(data):
    return validate_inputs({key:value for key,value in data.items() if key not in ('publish','auth_activation')})


def validate(step):
    if not isinstance(step,dict) or set(step)-{'id','action','payload'} or step.get('action',ACTION)!=ACTION:
        raise Stop('Unsupported native marketing quiz creation action')
    return validate_inputs(step.get('payload'))


def configuration_hash(plan):return _hash(validate_inputs(plan))


def _binding(value,plan):
    if (not isinstance(value,dict) or set(value)!={'editor_url','pages'}
            or value['pages']!=[{'label':'Page 1','questions':[]}]):
        raise Stop('Created quiz requires one positively empty, exact Page 1 shell binding')
    _editor_url(plan,value['editor_url'])
    return deepcopy(value)


def _shell_job(plan):
    from playwright_recipes.skill6_playwright import validate_job
    return validate_job({**{key:plan[key] for key in COMMON},'steps':[{'id':'create_shell','action':'assessment',
        'kind':'quiz','name':plan['name'],'allow_creation':True,'require_new':True,'standard_fields':[]}]},Path('.'))


def _empty_shell(page,plan,editor_url):
    _editor_url(plan,editor_url)
    if page.url!=editor_url:raise Stop('New quiz shell changed its generated editor before binding')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    owner={'expected_quiz_name':plan['name'],'start_url':editor_url,'pages':[{'label':'Page 1','questions':[]}],
           'questions':[],'target_page':1}
    native._wait_editor_identity(page,title,owner);native._wait_baseline(frame,owner)
    if (choices._inventory(frame,owner)!=[[]] or frame.locator('#add-slide-button').count()!=1
            or frame.locator('[data-field-type]').count()!=0):
        raise Stop('New quiz shell differs from the captured single empty Page 1 owner')
    _,canvas=native._owners(frame,owner)[0]
    native._one(canvas.get_by_text('Move your question to the 1st page using the elements on the left.',exact=True),
                'New quiz shell lacks its captured positive first-page instruction')
    native._one(canvas.locator('button#add-elements-button'),
                'New quiz shell lacks its captured in-canvas Add Elements control')
    return {'editor_url':editor_url,'pages':deepcopy(owner['pages'])}


def _receipts(root,job):
    from playwright_recipes.editor_replay import completed_editor_replay
    # Runner fingerprint uses its original formatting, distinct from leaf hashes.
    fingerprint=hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest()
    value=completed_editor_replay(Path(root)/'state.json',job,fingerprint)
    return [{'action':step['action'],'step_sha256':_hash(step),'result':row['result']}
            for step,row in zip(job['steps'],value['results'])]


def _validated_receipts(values,job):
    from playwright_recipes.editor_replay import _result
    if not isinstance(values,list) or len(values)!=len(job['steps']):raise Stop('Quiz creation omits a requested native stage receipt')
    result=[]
    for wrapper,step in zip(values,job['steps']):
        if (not isinstance(wrapper,dict) or set(wrapper)!={'action','step_sha256','result'}
                or wrapper['action']!=step['action'] or wrapper['step_sha256']!=_hash(step)):
            raise Stop('Quiz creation child completion belongs to another ordered authored stage')
        child=wrapper['result']
        if step['action']=='quiz_configuration' and (not isinstance(child,dict)
                or type(child.get('questions')) is not int or child['questions']!=len(step['questions'])
                or child.get('submission_verified') is not False or child.get('behavior_verified',False) is not False
                or child.get('independent_readback','VERIFIED')!='VERIFIED'):
            raise Stop('Quiz creation scoring completion contradicts its exact question count or pending behavior proof')
        result.append({**deepcopy(wrapper),'result':_result(step,child,job)})
    return result


def validate_receipt(value,step):
    plan=validate(step)
    keys={'status','location_id','editor_url','configuration_sha256','shell_binding','question_receipts',
          'configuration_receipts','question_count','scored_question_count','independent_readback','behavior_verified','submission_verified'}
    if (not isinstance(value,dict) or set(value)!=keys or value['status']!='QUIZ_CREATED_SAVED_AND_REOPENED'
            or value['location_id']!=plan['location_id'] or value['configuration_sha256']!=configuration_hash(plan)
            or value['independent_readback']!='VERIFIED' or value['behavior_verified'] is not False
            or value['submission_verified'] is not False):
        raise Stop('Quiz creation completion is malformed or unbound')
    binding=_binding(value['shell_binding'],plan)
    if value['editor_url']!=binding['editor_url']:raise Stop('Quiz creation completion changed its generated editor')
    question_job,pages=_questions(plan,binding['editor_url']);configuration_job=_configuration(plan,binding['editor_url'])
    if (type(value['question_count']) is not int or value['question_count']!=sum(len(owner['questions']) for owner in pages)
            or type(value['scored_question_count']) is not int
            or value['scored_question_count']!=len(configuration_job['steps'][0]['questions'])):
        raise Stop('Quiz creation completion changed the authored question/score inventory')
    safe=deepcopy(value)
    safe['question_receipts']=_validated_receipts(value['question_receipts'],question_job)
    safe['configuration_receipts']=_validated_receipts(value['configuration_receipts'],configuration_job)
    return safe


def _final_inventory(page,plan,binding,pages):
    if page.url!=binding['editor_url']:raise Stop('Created quiz left its retained generated editor')
    assert_tenant(page,plan)
    frame=page.frame_locator('iframe[name="quiz-builder-app"]')
    owner={'expected_quiz_name':plan['name'],'start_url':binding['editor_url'],'pages':pages,'questions':[],'target_page':len(pages)}
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    native._wait_editor_identity(page,title,owner);native._wait_baseline(frame,owner)
    if choices._properties(choices._inventory(frame,owner))!=[owner['questions'] for owner in pages]:
        raise Stop('Created quiz final result/scoring writes changed its authored page/question inventory')


def configure(page,step,evidence_root):
    from playwright_recipes.skill6_playwright import run_on_page,validate_job
    plan=validate(step);root=Path(evidence_root).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    shell_root=root/'shell';question_root=root/'questions';configuration_root=root/'configuration';binding_path=root/'shell-binding.json'
    if any(path.is_symlink() for path in (shell_root,question_root,configuration_root,binding_path)):
        raise Stop('Quiz creation evidence contains a symlink')
    shell_job=_shell_job(plan)
    if journal_present(binding_path):
        saved=read_journal(binding_path)
        original=_receipts(shell_root,shell_job)
        if (not isinstance(saved,dict) or set(saved)!={'configuration_sha256','shell'}
                or saved['configuration_sha256']!=configuration_hash(plan)
                or len(original)!=1 or original[0]['result']['status']!='ASSESSMENT_SAVE_SUBMITTED'
                or original[0]['result']['editor_url']!=saved.get('shell',{}).get('editor_url')):
            raise Stop('Retained quiz shell differs from its original new-creation journal')
        binding=_binding(saved['shell'],plan)
    else:
        run_on_page(page,shell_job,shell_root)
        original=_receipts(shell_root,shell_job)
        if len(original)!=1 or original[0]['result']['status']!='ASSESSMENT_SAVE_SUBMITTED':
            raise Stop('Quiz creation requires a newly created shell; an existing quiz cannot be adopted')
        editor_url=original[0]['result']['editor_url']
        before=_empty_shell(page,plan,editor_url)
        reopen_editor(page,'quiz',plan['name'],editor_url)
        if _empty_shell(page,plan,editor_url)!=before:raise Stop('New quiz empty shell did not persist on independent reopen')
        binding=_binding(before,plan);secure_json(binding_path,{'configuration_sha256':configuration_hash(plan),'shell':binding})
    editor_url=binding['editor_url']
    if page.url!=editor_url:reopen_editor(page,'quiz',plan['name'],editor_url)
    if not journal_present(question_root/'state.json') and _empty_shell(page,plan,editor_url)!=binding:
        raise Stop('New quiz shell changed before its first authored question')
    question_job,pages=_questions(plan,editor_url);question_job=validate_job(question_job,root)
    run_on_page(page,question_job,question_root);questions=_receipts(question_root,question_job)
    configuration_job=validate_job(_configuration(plan,editor_url),root)
    run_on_page(page,configuration_job,configuration_root);configuration=_receipts(configuration_root,configuration_job)
    reopen_editor(page,'quiz',plan['name'],editor_url);_final_inventory(page,plan,binding,pages)
    return validate_receipt({'status':'QUIZ_CREATED_SAVED_AND_REOPENED','location_id':plan['location_id'],
        'editor_url':editor_url,'configuration_sha256':configuration_hash(plan),'shell_binding':binding,
        'question_receipts':questions,'configuration_receipts':configuration,'question_count':sum(len(owner['questions']) for owner in pages),
        'scored_question_count':len(configuration_job['steps'][0]['questions']),'independent_readback':'VERIFIED',
        'behavior_verified':False,'submission_verified':False},step)
