#!/usr/bin/env python3
"""API-first course delivery and captured community channels.

Official Courses v3 schemas inspected 2026-11-08:
https://marketplace.gohighlevel.com/docs/ghl/courses/create-course/
https://marketplace.gohighlevel.com/docs/ghl/courses/create-category/
https://marketplace.gohighlevel.com/docs/ghl/courses/create-lesson/
https://marketplace.gohighlevel.com/docs/ghl/courses/create-lesson-quiz/
https://marketplace.gohighlevel.com/docs/ghl/courses/upsert-quiz-questions/

This module reuses Skill 44's location-token resolver, request headers and write
safety gate. It never seeds a credential, publishes or enrolls a contact.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import fcntl
import os
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit

if __package__:
    from .skill6_playwright import Stop, secure_json, sha, click, fill, wait_until
    from .evidence_lease import guard_delivery, journal_present, open_lease
    from .receipt_validation import replay_delivery
else:
    from skill6_playwright import Stop, secure_json, sha, click, fill, wait_until
    from evidence_lease import guard_delivery, journal_present, open_lease
    from receipt_validation import replay_delivery

class DeliveryApiError(Stop):
    def __init__(self, status=None, error_type='RequestError'):
        self.http_status = status
        super().__init__('Courses API request failed: ' + (str(status) if status else error_type))


VERSION = 'v3'
PRODUCT_FIELDS = {'title','description','posterImage','customJs','customCss','customHeader',
                  'customFooter','commentPrivacy','libraryOrder','customizations'}
CUSTOM_FIELDS = {'logoImage','heroImage','heroOverlayColor','heroTextAlignment','heroSpacing',
                 'favicon','instructorHeading','instructorHeadshot','instructorName',
                 'instructorTitle','instructorBio','templateId','settings','lessonSettings'}
CATEGORY_FIELDS = {'title','description','parentCategory','posterImage','sequenceNo',
                   'dripDays','metadata','commentPermission','lockedBy','lockedByCategory','visibility'}
LESSON_FIELDS = {'title','description','posterImage','sequenceNo','commentStatus','contentId',
                 'contentType','commentPermission','lockedByPost','lockedByCategory',
                 'certificateTemplateId','metaData','visibility'}
QUIZ_FIELDS = {'title','requiredPassingGrade','passingGrade','passMessage','failMessage'}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise Stop(label + ' must be a nonempty string')
    return value


def _id(value, label):
    _text(value, label)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise Stop(label + ' contains invalid path characters')
    return value


def _body(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise Stop(label + ' contains unknown or identity-owned fields')
    out = deepcopy(value)
    _text(out.get('title'), label + '.title')
    # This delivery entry point builds drafts. Publication stays on its existing gate.
    if 'visibility' in allowed:
        if out.get('visibility', 'draft') != 'draft':
            raise Stop('Publishing/locking/dripping belongs to a separately approved operation')
        out['visibility'] = 'draft'
    for key in ('description','posterImage','customJs','customCss','customHeader','customFooter'):
        if key in out and out[key] is not None and not isinstance(out[key], str):
            raise Stop(label + '.' + key + ' must be text or null')
    return out


def validate_course(inputs):
    _id(inputs.get('location_id'), 'location_id')
    if inputs.get('publish') or inputs.get('enrollments'):
        raise Stop('Course delivery does not publish or enroll contacts')
    product = _body(inputs.get('course'), PRODUCT_FIELDS, 'course')
    if 'customizations' in product:
        custom = product['customizations']
        if not isinstance(custom, dict) or set(custom) - CUSTOM_FIELDS:
            raise Stop('Unknown course customization')
        if custom.get('heroTextAlignment', 'left') not in ('left','right','centered'):
            raise Stop('Invalid course hero alignment')
        if custom.get('heroSpacing', 'small') not in ('xs','small','medium','large'):
            raise Stop('Invalid course hero spacing')
    if product.get('commentPrivacy', 'public') not in ('public','instructorOnly','publicAndInstructor'):
        raise Stop('Invalid course comment privacy')
    modules = inputs.get('modules', [])
    if not isinstance(modules, list):
        raise Stop('modules must be a list')
    result = []
    for module in modules:
        if not isinstance(module, dict):
            raise Stop('module must be an object')
        category = _body({k:v for k,v in module.items() if k != 'lessons'}, CATEGORY_FIELDS, 'module')
        lessons = module.get('lessons', [])
        if not isinstance(lessons, list):
            raise Stop('lessons must be a list')
        cooked = []
        for lesson in lessons:
            if not isinstance(lesson, dict):
                raise Stop('lesson must be an object')
            body = _body({k:v for k,v in lesson.items() if k != 'quiz'}, LESSON_FIELDS, 'lesson')
            if body.get('contentType', 'video') not in ('video','assignment','quiz','audio','funnel'):
                raise Stop('Invalid lesson contentType')
            quiz = lesson.get('quiz')
            if quiz is not None:
                quiz = validate_quiz(quiz)
                body['contentType'] = 'quiz'
            cooked.append({'body': body, 'quiz': quiz})
        result.append({'body':category, 'lessons':cooked})
    return {'location_id':inputs['location_id'], 'course':product, 'modules':result}


def validate_quiz(value):
    if not isinstance(value, dict):
        raise Stop('quiz must be an object')
    body = _body({k:v for k,v in value.items() if k != 'questions'}, QUIZ_FIELDS, 'quiz')
    if 'requiredPassingGrade' in body and type(body['requiredPassingGrade']) is not bool:
        raise Stop('requiredPassingGrade must be boolean')
    if 'passingGrade' in body and (type(body['passingGrade']) not in (int,float) or not 0 <= body['passingGrade'] <= 100):
        raise Stop('passingGrade must be 0 to 100')
    questions = value.get('questions', [])
    if not isinstance(questions, list) or not questions:
        raise Stop('Quiz requires questions')
    sequences = set()
    for q in questions:
        if not isinstance(q, dict) or set(q)-{'id','title','questionType','sequenceNumber','options','explanation'}:
            raise Stop('Invalid quiz question')
        _text(q.get('title'),'question.title')
        if q.get('questionType') not in ('single','multiple') or type(q.get('sequenceNumber')) not in (int,float) or q['sequenceNumber'] in sequences:
            raise Stop('Invalid question type/sequence')
        sequences.add(q['sequenceNumber'])
        opts = q.get('options')
        if not isinstance(opts,list) or len(opts)<2:
            raise Stop('Quiz questions need at least two options')
        for opt in opts:
            if not isinstance(opt,dict) or set(opt)-{'id','title','isCorrect'}:
                raise Stop('Invalid answer option')
            _text(opt.get('title'),'option.title')
            if type(opt.get('isCorrect')) is not bool:
                raise Stop('isCorrect must be boolean')
        count = sum(o['isCorrect'] for o in opts)
        if not count or (q['questionType']=='single' and count!=1):
            raise Stop('Quiz correct answers contradict question type')
    return {'body':body, 'questions':deepcopy(questions)}


class Skill44Transport:
    """Use the installed Skill 44 resolver, safety gate and requests client."""
    def __init__(self):
        here = Path(__file__).resolve()
        for root in here.parents:
            engine = root/'44-convert-and-flow-operator/tools/engine'
            if engine.is_dir():
                if str(engine) not in sys.path:
                    sys.path.insert(0, str(engine))
                self.client = importlib.import_module('cli_anything.gohighlevel.utils.ghl_client')
                return
        raise Stop('Skill 44 engine is not installed')

    def request(self, method, path, *, location_id, body=None, query=None):
        query = {'locationId':location_id, **(query or {})}
        url = self.client.BASE_URL + path + '?' + urlencode(query)
        if method != 'GET':
            self.client.check_write(method, url, body, location_id=location_id)
        try:
            response = self.client.requests.request(method, url,
                headers=self.client._headers(VERSION, path, method), json=body, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            status = getattr(getattr(exc,'response',None),'status_code',None)
            raise DeliveryApiError(status,type(exc).__name__) from None


def _capability(record, location_id, scopes=('courses.readonly','courses.write')):
    if not isinstance(record,dict) or record.get('location_id')!=location_id or record.get('version')!=VERSION:
        raise Stop('Courses capability receipt must match location and v3')
    if record.get('status') not in ('PASS','SUPPORTED') or not record.get('source'):
        raise Stop('Courses capability is not proven supported')
    if not set(scopes).issubset(set(record.get('scopes',[]))):
        raise Stop('Courses read/write scopes are required')
    try:
        checked = datetime.fromisoformat(record['checked_at'].replace('Z','+00:00'))
        age = (datetime.now(timezone.utc)-checked).total_seconds()
    except (ValueError,KeyError,TypeError):
        raise Stop('Courses capability timestamp missing or invalid') from None
    if not 0 <= age <= 86400:
        raise Stop('Courses capability receipt is stale')


def _matches(expected, actual):
    if isinstance(expected,dict):
        return isinstance(actual,dict) and all(k in actual and _matches(v,actual[k]) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(actual,list) and len(expected)==len(actual) and all(_matches(e,a) for e,a in zip(expected,actual))
    return expected == actual


@guard_delivery('course')
def run_course(inputs, evidence_root, *, capability, transport=None):
    """Lease this evidence root across direct and host callers before a write."""
    validate_course(inputs)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    fd = open_lease(root/'delivery.lock')
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('Course delivery evidence root is already leased') from None
        return _run_course(inputs,root,capability=capability,transport=transport)
    finally:
        os.close(fd)


def _run_course(inputs, evidence_root, *, capability, transport=None):
    """Create or reconcile a full draft course, modules, lessons and quizzes.

    Never retries a write. A crash/timeout leaves intent requiring reconciliation.
    Existing course IDs are read and compared, not silently overwritten.
    """
    plan = validate_course(inputs)
    loc = plan['location_id']
    _capability(capability,loc)
    root = Path(evidence_root)
    state_file = root/'delivery-state.json'
    digest = sha(json.dumps(plan,sort_keys=True))
    if journal_present(state_file):
        counts = {'course':1}
        for module in plan['modules']:
            counts['category'] = counts.get('category',0) + 1
            for lesson in module['lessons']:
                counts['lesson'] = counts.get('lesson',0) + 1
                if lesson['quiz']:
                    counts['quiz'] = counts.get('quiz',0) + 1
        return replay_delivery(state_file,operation='courses.create',location_id=loc,
                               fingerprint=digest,expected_counts=counts)
    api = transport or Skill44Transport()
    state = {'fingerprint':digest,'operation':'courses.create','location_id':loc,
             'status':'RUNNING','objects':[],'verification_required':True}
    def request(method,path,body=None,query=None):
        return api.request(method,path,location_id=loc,body=body,query=query)
    def create(kind,path,body,read_path):
        state.update(current_kind=kind,current_step_status='INTENT_RECORDED')
        secure_json(state_file,state)
        result = request('POST',path,body)
        identity = _id(result.get('id') if isinstance(result,dict) else None, kind+'.id')
        state['objects'].append({'kind':kind,'id':identity})
        secure_json(state_file,state)
        read = request('GET',read_path(identity))
        if not _matches(body,read):
            raise Stop(kind+' persisted read-back differs from requested values')
        state['current_step_status']='VERIFIED'
        secure_json(state_file,state)
        return identity
    try:
        # List all matching titles before create; pagination never silently truncates.
        matches=[]; cursor=None; seen=set()
        for _ in range(100):
            q={'search':plan['course']['title'],'limit':'50'}
            if cursor: q['cursor']=cursor
            data=request('GET','/courses/products',query=q)
            if not isinstance(data,dict) or not isinstance(data.get('products'),list):
                raise Stop('Course inventory response malformed')
            matches += [p for p in data['products'] if p.get('title')==plan['course']['title']]
            cursor=data.get('nextCursor')
            if not cursor: break
            if cursor in seen: raise Stop('Course inventory cursor repeated')
            seen.add(cursor)
        else: raise Stop('Course inventory exceeded bounded pagination')
        if matches:
            if len(matches)!=1 or plan['modules']:
                raise Stop('Existing course requires outline inventory/reconciliation before reuse')
            course_id=_id(matches[0].get('id'),'course.id')
            if not _matches(plan['course'],request('GET','/courses/products/'+course_id)):
                raise Stop('Existing course differs; explicit update operation required')
            state['objects'].append({'kind':'course','id':course_id,'reused':True})
        else:
            course_id=create('course','/courses/products',plan['course'],lambda i:'/courses/products/'+i)
        base='/courses/products/'+course_id
        for mod in plan['modules']:
            cat_id=create('category',base+'/categories',mod['body'],lambda i:base+'/categories/'+i)
            for lesson in mod['lessons']:
                body={**lesson['body'],'categoryId':cat_id}
                lesson_id=create('lesson',base+'/lessons',body,lambda i:base+'/lessons/'+i)
                if lesson['quiz']:
                    quiz=lesson['quiz']; quiz_path=base+'/lessons/'+lesson_id+'/quiz'
                    quiz_id=create('quiz',quiz_path,quiz['body'],lambda i:quiz_path)
                    question_path=base+'/quizzes/'+quiz_id+'/questions'
                    state.update(current_kind='quiz_questions',current_step_status='INTENT_RECORDED')
                    secure_json(state_file,state)
                    request('PUT',question_path,{'questions':quiz['questions']})
                    result=request('GET',question_path)
                    if not _matches(quiz['questions'],result.get('questions')):
                        # Server-generated IDs are allowed; compare requested fields in sequence.
                        actual=result.get('questions',[])
                        if len(actual)!=len(quiz['questions']) or not all(_matches(e,a) for e,a in zip(quiz['questions'],actual)):
                            raise Stop('Quiz questions persisted read-back differs')
        state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED',meaning='Draft API objects verified; course preview and learner behavior remain separate QC')
        secure_json(state_file,state)
        return state
    except Exception as exc:
        state.update(status='NEEDS_RECONCILIATION',error_type=type(exc).__name__)
        secure_json(state_file,state)
        raise


def configure_community_channels(page, step, *, portal_context=None, evidence_root=None):
    """Compatibility front door for the maintained authenticated portal adapter.

    Bare portal URL/name visibility is not authenticated account/location proof.
    Keep one channel implementation and require the same caller-owned context
    and protected journal used by host.run_recipe.
    """
    if portal_context is None or evidence_root is None:
        raise Stop('Community channels require authenticated same-page portal context and evidence root')
    if __package__:
        from .community_portal import run_channels
    else:
        from community_portal import run_channels
    return run_channels(page, step, evidence_root, portal_context=portal_context)


def validate_api_inputs(operation, inputs, route):
    """Read-only schema and route check for host --check and actual execution."""
    if operation not in ('courses.create','courses.lesson_quiz.create','courses.update'):
        raise Stop('Unsupported delivery API operation')
    if not isinstance(route,dict) or route.get('operation')!=operation or route.get('version')!=VERSION:
        raise Stop('Courses route must match the exact operation and v3')
    if route.get('lane') not in ('public_api','skill44','official_mcp'):
        raise Stop('Courses validation requires a documented API/MCP route')
    if route.get('location_id')!=inputs.get('location_id'):
        raise Stop('API route location mismatch')
    _capability(inputs.get('api_capability'),inputs.get('location_id'))
    if operation=='courses.create':
        return validate_course(inputs)
    loc=_id(inputs.get('location_id'),'location_id')
    product=_id(inputs.get('product_id'),'product_id')
    if operation=='courses.lesson_quiz.create':
        return {'location_id':loc,'product_id':product,
                'lesson_id':_id(inputs.get('lesson_id'),'lesson_id'),
                'quiz':validate_quiz(inputs.get('quiz'))}
    changes=inputs.get('course_changes')
    if not isinstance(changes,dict) or not changes:
        raise Stop('course_changes must be a nonempty object')
    cooked=validate_course({'location_id':loc,'course':{'title':'Validation only',**changes}})['course']
    if 'title' not in changes:cooked.pop('title')
    if inputs.get('expected_updated_at') is not None:
        _text(inputs['expected_updated_at'],'expected_updated_at')
    return {'location_id':loc,'product_id':product,'course_changes':cooked}


def course_executor(*, operation, inputs, route, evidence_root):
    """Host.run_recipe callback; no API handoff masquerading as execution."""
    validate_api_inputs(operation,inputs,route)
    if route.get('lane') not in ('public_api','skill44'):
        raise Stop('Courses HTTP executor requires a public_api or skill44 route')
    runner={'courses.create':run_course,'courses.lesson_quiz.create':run_lesson_quiz,'courses.update':run_course_update}[operation]
    return runner(inputs,evidence_root,capability=inputs.get('api_capability'))


@guard_delivery('course')
def run_lesson_quiz(inputs, evidence_root, *, capability, transport=None):
    """Create a quiz for an existing lesson, preserving any different existing quiz."""
    loc=_id(inputs.get('location_id'),'location_id')
    product=_id(inputs.get('product_id'),'product_id')
    lesson=_id(inputs.get('lesson_id'),'lesson_id')
    quiz=validate_quiz(inputs.get('quiz'))
    _capability(capability,loc)
    root=Path(evidence_root).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    fd=open_lease(root/'delivery.lock')
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('Course delivery evidence root is already leased') from None
        state_path=root/'delivery-state.json'
        digest=sha(json.dumps({'location':loc,'product':product,'lesson':lesson,'quiz':quiz},sort_keys=True))
        if journal_present(state_path):
            return replay_delivery(state_path,operation='courses.lesson_quiz.create',
                location_id=loc,fingerprint=digest,expected_counts={'quiz':1})
        api=transport or Skill44Transport()
        def request(method,path,body=None):
            return api.request(method,path,location_id=loc,body=body)
        base='/courses/products/'+product
        lesson_path=base+'/lessons/'+lesson
        # Both parent reads must succeed with the location-scoped token before a write.
        request('GET',base); request('GET',lesson_path)
        quiz_path=lesson_path+'/quiz'
        try: current=request('GET',quiz_path)
        except DeliveryApiError as exc:
            if exc.http_status!=404: raise
            current=None
        state={'fingerprint':digest,'operation':'courses.lesson_quiz.create','location_id':loc,
               'status':'RUNNING','objects':[],'verification_required':True}
        if current is not None:
            if not _matches(quiz['body'],current):
                raise Stop('Existing lesson quiz differs; explicit update operation required')
            quiz_id=_id(current.get('id'),'quiz.id')
            question_path=base+'/quizzes/'+quiz_id+'/questions'
            if not _matches(quiz['questions'],request('GET',question_path).get('questions')):
                raise Stop('Existing quiz questions differ; refusing implicit replacement')
            state['objects'].append({'kind':'quiz','id':quiz_id,'reused':True})
        else:
            state.update(current_kind='quiz',current_step_status='INTENT_RECORDED')
            secure_json(state_path,state)
            try:
                result=request('POST',quiz_path,quiz['body'])
                quiz_id=_id(result.get('id'),'quiz.id')
                state['objects'].append({'kind':'quiz','id':quiz_id})
                secure_json(state_path,state)
                if not _matches(quiz['body'],request('GET',quiz_path)):
                    raise Stop('Lesson quiz read-back differs')
                question_path=base+'/quizzes/'+quiz_id+'/questions'
                state.update(current_kind='quiz_questions',current_step_status='INTENT_RECORDED')
                secure_json(state_path,state)
                request('PUT',question_path,{'questions':quiz['questions']})
                if not _matches(quiz['questions'],request('GET',question_path).get('questions')):
                    raise Stop('Lesson quiz questions read-back differs')
            except Exception as exc:
                state.update(status='NEEDS_RECONCILIATION',error_type=type(exc).__name__)
                secure_json(state_path,state)
                raise
        state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED')
        secure_json(state_path,state)
        return state
    finally: os.close(fd)


@guard_delivery('course')
def run_course_update(inputs,evidence_root,*,capability,transport=None):
    """Apply only explicit documented course appearance/content changes by API."""
    loc=_id(inputs.get('location_id'),'location_id')
    product=_id(inputs.get('product_id'),'product_id')
    changes=inputs.get('course_changes')
    if not isinstance(changes,dict) or not changes:
        raise Stop('course_changes must be a nonempty object')
    # Reuse the create schema with an internal title for optional-title validation.
    cooked=validate_course({'location_id':loc,'course':{'title':'Validation only',**changes}})['course']
    if 'title' not in changes: cooked.pop('title')
    _capability(capability,loc)
    root=Path(evidence_root).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(root,0o700)
    fd=open_lease(root/'delivery.lock')
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('Course delivery evidence root is already leased') from None
        state_path=root/'delivery-state.json'
        digest=sha(json.dumps({'operation':'courses.update','location':loc,'product':product,'changes':cooked},sort_keys=True))
        if journal_present(state_path):
            return replay_delivery(state_path,operation='courses.update',location_id=loc,
                fingerprint=digest,expected_counts={'course':1},expected_ids={'course':product})
        api=transport or Skill44Transport()
        path='/courses/products/'+product
        current=api.request('GET',path,location_id=loc)
        expected=inputs.get('expected_updated_at')
        if expected is not None and current.get('updatedAt')!=expected:
            raise Stop('Course changed since inventory; refresh before updating')
        state={'fingerprint':digest,'operation':'courses.update','location_id':loc,
               'verification_required':True,'objects':[{'kind':'course','id':product}],
               'status':'RUNNING','current_step_status':'INTENT_RECORDED'}
        secure_json(state_path,state)
        try:
            if not _matches(cooked,current):
                api.request('PUT',path,location_id=loc,body=cooked)
                actual=api.request('GET',path,location_id=loc)
                if not _matches(cooked,actual): raise Stop('Course update read-back differs')
            state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED')
            secure_json(state_path,state)
            return state
        except Exception as exc:
            state.update(status='NEEDS_RECONCILIATION',error_type=type(exc).__name__)
            secure_json(state_path,state)
            raise
    finally: os.close(fd)


class RegisteredCalendarDispatcher:
    """Production calendar rail through the canonical PublicGhlAdapter registry.

    Default capability records remain default-deny. This class never manufactures
    enablement from a recipe input. Tests may inject a genuine CapabilityGate.
    Every HTTP write also passes Skill 44's existing approval/allowlist gate.
    """
    def __init__(self, location_id, *, capability_record=None, capability_gate=None,
                 transport=None, client=None):
        from ghl_public_client import engine
        seams=engine()
        self.location_id=location_id
        self.client=client or Skill44Transport().client
        self.seams=seams
        self.transport=transport or CalendarHttpTransport(self.client,location_id)
        auth=seams['AuthContext'](kind=seams['AuthKind'].location_pit,
            location_id=location_id,source='env:GOHIGHLEVEL_API_KEY',
            resolve_secret=lambda name:self.client._get_token())
        # Resolving through the canonical registry is mandatory, not an injected
        # row or a raw HTTP fallback when the update operation is unavailable.
        row=seams['OPERATIONS'].get('calendars.update')
        if row is None or row.method!='PUT' or row.version!='v3' or row.readback_plan!='calendars.get':
            raise Stop('Canonical calendars.update operation is not registered')
        self.adapter=seams['PublicGhlAdapter'](auth=auth,transport=self.transport,
            capability=capability_gate,capability_record=capability_record)
        self.last_receipt=None

    def __call__(self, operation_id, *, location_id, path_params, body=None):
        from cli_anything.gohighlevel.public.readback import ReadbackSpec
        from cli_anything.gohighlevel.public.idempotency import IdempotencyKey
        if location_id!=self.location_id or operation_id not in ('calendars.get','calendars.update'):
            raise Stop('Calendar dispatcher operation/location mismatch')
        calendar_id=_id(path_params.get('calendarId'),'calendarId')
        if set(path_params)!={'calendarId'}:
            raise Stop('Calendar dispatcher has unexpected path parameters')
        kwargs={'operation_id':operation_id,
            'tenant':self.seams['TenantBinding'](location_id=location_id,source='skill06:meeting-integration'),
            'path_params':path_params}
        if operation_id=='calendars.update':
            if not isinstance(body,dict) or not body or set(body)-{'locationConfigurations','teamMembers'}:
                raise Stop('Room integration may change only calendar meeting locations')
            kwargs.update(body=body,idempotency_key=IdempotencyKey.issue(operation_id).value,
                readback=ReadbackSpec(operation_id='calendars.get',target_params=path_params,
                    expect={'id':calendar_id,'locationId':location_id,**body},scan_nested=True,
                    description='Persisted calendar identity and exact requested meeting locations'))
        result=self.adapter.call(**kwargs)
        self.last_receipt=result
        status=getattr(result.status,'value',str(result.status))
        if status!='ok':
            if result.http_status is not None and result.http_status>=400:
                raise DeliveryApiError(result.http_status)
            raise Stop('Calendar public route refused: '+str((result.error or {}).get('rule',status)))
        return deepcopy(self.transport.last_body)


class CalendarHttpTransport:
    """Adapter transport using existing Skill44 HTTP library and safety gate."""
    def __init__(self, client, location_id):
        self.client=client;self.location_id=location_id;self.last_body=None

    def request(self, *, method, url, version, headers, query, body, timeout_s):
        from cli_anything.gohighlevel.public.transport import TransportResponse
        full=self.client.BASE_URL+url
        if method!='GET':
            # Canonical dry-run output prints payloads. Do not pass a private
            # invitation URL to that printer; host --check is the read-only path.
            if os.environ.get('CAF_DRY_RUN','').lower() in ('1','true','yes','on'):
                raise Stop('Use host --check for credential-safe calendar validation')
            self.client.check_write(method,full,body,location_id=self.location_id)
        h=dict(headers)
        if version is not None:h['Version']=version
        try:
            response=self.client.requests.request(method,full,params=query,json=body,
                headers=h,timeout=timeout_s)
        except self.client.requests.exceptions.Timeout:
            return TransportResponse(status=None,headers={},body=b'',error_kind='timeout')
        except self.client.requests.exceptions.RequestException:
            return TransportResponse(status=None,headers={},body=b'',error_kind='connection')
        raw=response.content
        try:self.last_body=response.json()
        except (ValueError,TypeError):self.last_body=None
        return TransportResponse(status=response.status_code,headers={},body=raw)


def validate_calendar_integration(inputs, route):
    """Pure validation for the static permanent-room calendar integration."""
    if inputs.get('integration_mode')!='permanent_calendar_link':
        raise Stop('Calendar integration requires integration_mode=permanent_calendar_link')
    loc=_id(inputs.get('location_id'),'location_id')
    if not isinstance(route,dict) or route.get('operation')!='meetings.integrate' or route.get('location_id')!=loc or route.get('version')!='v3':
        raise Stop('Calendar integration route must match meetings.integrate, location and v3')
    if route.get('lane') not in ('public_api','skill44','official_mcp'):
        raise Stop('Calendar integration needs a documented API/MCP route')
    _capability(inputs.get('api_capability'),loc,scopes=('calendars.readonly','calendars.write'))
    _id(inputs.get('calendar_id'),'calendar_id')
    room=inputs.get('room')
    if not isinstance(room,dict) or room.get('location_id')!=loc or room.get('status')!='PRESENT' or not room.get('room_id') or not room.get('source'):
        raise Stop('Calendar integration needs a verified room receipt for this location')
    # Detailed room URL and calendar-type constraints are validated by meetings.
    if __package__:
        from .meetings import safe_room_url
    else:
        from meetings import safe_room_url
    safe_room_url(room.get('url'))
    if inputs.get('member_id') is not None:_id(inputs['member_id'],'member_id')
    if inputs.get('replace_index') is not None and (type(inputs['replace_index']) is not int or inputs['replace_index']<0):
        raise Stop('replace_index must be a nonnegative integer')
    return {'location_id':loc,'calendar_id':inputs['calendar_id'],'room':deepcopy(room)}


@guard_delivery('calendar')
def meeting_calendar_executor(*, operation, inputs, route, evidence_root, dispatcher=None):
    """Host provider for static permanent-room links, with durable no-replay state."""
    if operation!='meetings.integrate':raise Stop('Unsupported calendar integration operation')
    validate_calendar_integration(inputs,route)
    if route.get('lane') not in ('public_api','skill44'):
        raise Stop('Calendar HTTP provider does not substitute for official MCP')
    if __package__:
        from .meetings import integrate_calendar
    else:
        from meetings import integrate_calendar
    root=Path(evidence_root).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(root,0o700)
    fd=open_lease(root/'calendar-delivery.lock')
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('Calendar integration run is already leased') from None
        state_path=root/'calendar-delivery-state.json'
        digest=sha(json.dumps({k:inputs.get(k) for k in ('location_id','calendar_id','room','member_id','replace_index','private_invite_url')},sort_keys=True))
        if journal_present(state_path):
            return replay_delivery(state_path,operation='meetings.integrate',
                location_id=inputs['location_id'],fingerprint=digest,
                expected_counts={'calendar':1},expected_ids={'calendar':inputs['calendar_id']})
        state={'fingerprint':digest,'operation':'meetings.integrate','location_id':inputs['location_id'],
            'verification_required':True,'status':'RUNNING',
            'current_step_status':'INTENT_RECORDED','objects':[{'kind':'calendar','id':inputs['calendar_id']}]}
        secure_json(state_path,state)
        api=dispatcher or RegisteredCalendarDispatcher(inputs['location_id'],capability_record=inputs.get('capability_record'))
        try:
            extra={k:inputs[k] for k in ('member_id','replace_index','private_invite_url') if k in inputs}
            result=integrate_calendar(api,location_id=inputs['location_id'],calendar_id=inputs['calendar_id'],room=inputs['room'],**extra)
            state.update(status='API_STEPS_COMPLETE',current_step_status='VERIFIED',integration=result)
            secure_json(state_path,state)
            return state
        except Exception as exc:
            state.update(status='NEEDS_RECONCILIATION',error_type=type(exc).__name__)
            secure_json(state_path,state)
            raise
    finally:os.close(fd)
