"""Edit inventoried draft course modules/lessons through documented Courses v3.

https://marketplace.gohighlevel.com/docs/ghl/courses/update-category/index.html
https://marketplace.gohighlevel.com/docs/ghl/courses/update-lesson/index.html

This operation changes existing draft content only. Publication, access rules,
module moves, enrollment and quiz/assignment provisioning retain their own rails.
"""
import fcntl
import json
import os
from pathlib import Path

if __package__:
    from . import delivery
    from .evidence_lease import guard_delivery, journal_present, open_lease, read_journal
    from .receipt_validation import replay_delivery
    from .skill6_playwright import Stop, secure_json, sha
else:
    import delivery
    from evidence_lease import guard_delivery, journal_present, open_lease, read_journal
    from receipt_validation import replay_delivery
    from skill6_playwright import Stop, secure_json, sha


OPERATION = 'courses.lessons'
CATEGORY_CHANGES = frozenset(('title','description','posterImage','sequenceNo','commentPermission'))
LESSON_CHANGES = frozenset(('title','description','posterImage','sequenceNo','commentStatus',
    'contentId','contentType','commentPermission','certificateTemplateId','metaData'))


def _changes(value, kind):
    allowed = CATEGORY_CHANGES if kind == 'category' else LESSON_CHANGES
    if not isinstance(value, dict) or not value or set(value) - allowed:
        raise Stop('Draft outline changes contain unsupported fields or no changes')
    data = delivery._body({'title':'Validation only', **value},
        delivery.CATEGORY_FIELDS if kind == 'category' else delivery.LESSON_FIELDS,
        'module' if kind == 'category' else 'lesson')
    delivery._outline_properties(data, 'module' if kind == 'category' else 'lesson')
    data.pop('visibility', None)
    if 'title' not in value:
        data.pop('title')
    if not data:
        raise Stop('Draft outline update would contain no effective changes')
    if 'contentType' in data and data['contentType'] not in ('video','audio','funnel','quiz','assignment'):
        raise Stop('Invalid lesson content type')
    return data


def validate_inputs(inputs):
    allowed = delivery.COURSE_COMMON_INPUTS | {'product_id','category_changes','lesson_changes'}
    if not isinstance(inputs, dict) or set(inputs) - allowed:
        raise Stop('Unsupported or ignored course outline input')
    if 'publish' in inputs and inputs['publish'] is not False:
        raise Stop('Draft outline edits do not publish or enroll contacts')
    for key in ('location_name','start_url'):
        if key in inputs:
            delivery._text(inputs[key],key)
    plan = {'location_id':delivery._id(inputs.get('location_id'),'location_id'),
            'product_id':delivery._id(inputs.get('product_id'),'product_id'),
            'category_changes':[], 'lesson_changes':[]}
    for group, kind in (('category_changes','category'),('lesson_changes','lesson')):
        edits = inputs.get(group, [])
        if not isinstance(edits, list):
            raise Stop(group + ' must be a list')
        seen = set()
        for edit in edits:
            expected = {'category_id','expected_updated_at','changes'}
            if kind == 'lesson':expected.add('lesson_id')
            if not isinstance(edit, dict) or set(edit) != expected:
                raise Stop('Each outline edit requires exact target, inventory version and changes')
            identity = delivery._id(edit.get(kind+'_id'),kind+'_id')
            if identity in seen:
                raise Stop('Duplicate draft outline target')
            seen.add(identity)
            cooked = {kind+'_id':identity,
                'expected_updated_at':delivery._text(edit['expected_updated_at'],'expected_updated_at'),
                'changes':_changes(edit['changes'],kind)}
            if kind == 'lesson':
                cooked['category_id'] = delivery._id(edit['category_id'],'category_id')
            plan[group].append(cooked)
    if not plan['category_changes'] and not plan['lesson_changes']:
        raise Stop('At least one existing draft outline target is required')
    return plan


def validate_api_inputs(operation, inputs, route):
    plan = validate_inputs(inputs)
    if (operation != OPERATION or not isinstance(route,dict)
            or route.get('operation') != OPERATION or route.get('version') != delivery.VERSION
            or route.get('location_id') != plan['location_id']
            or route.get('lane') not in ('public_api','skill44','official_mcp')):
        raise Stop('Course outline route must match its exact operation, location and v3')
    delivery._capability(inputs.get('api_capability'),plan['location_id'])
    return plan


def course_outline_executor(*, operation, inputs, route, evidence_root):
    validate_api_inputs(operation,inputs,route)
    if route['lane'] not in ('public_api','skill44'):
        raise Stop('Course outline HTTP executor requires its actual API transport')
    return run_outline(inputs,evidence_root,capability=inputs.get('api_capability'))


def _preserved(expected, actual):
    if not delivery._matches(expected,actual):
        return False
    if 'metaData' in expected:
        return delivery._matches(expected['metaData'],actual.get('metaData'),exact=True)
    return True


def _objects(plan):
    categories = {edit['category_id'] for edit in plan['category_changes']}
    categories.update(edit['category_id'] for edit in plan['lesson_changes'])
    return ([{'kind':'course','id':plan['product_id']}]
        + [{'kind':'category','id':identity} for identity in sorted(categories)]
        + [{'kind':'lesson','id':edit['lesson_id']} for edit in plan['lesson_changes']])


@guard_delivery('course')
def run_outline(inputs, evidence_root, *, capability, transport=None):
    plan = validate_inputs(inputs)
    loc, product = plan['location_id'], plan['product_id']
    delivery._capability(capability,loc)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    fd = open_lease(root/'delivery.lock')
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('Course outline evidence root is already leased') from None
        path = root/'delivery-state.json'
        fingerprint = sha(json.dumps({'operation':OPERATION,'plan':plan},sort_keys=True))
        objects = _objects(plan)
        counts = {kind:sum(obj['kind']==kind for obj in objects) for kind in ('course','category','lesson')}
        counts = {kind:count for kind,count in counts.items() if count}
        if journal_present(path):
            result = replay_delivery(path,operation=OPERATION,location_id=loc,fingerprint=fingerprint,
                expected_counts=counts,expected_ids={'course':product})
            if {(obj['kind'],obj['id']) for obj in result['objects']} != {(obj['kind'],obj['id']) for obj in objects}:
                raise Stop('Saved course outline identities differ from the requested targets')
            completed = [{'kind':kind,'id':edit[kind+'_id']}
                for group,kind in (('category_changes','category'),('lesson_changes','lesson'))
                for edit in plan[group]]
            old = read_journal(path)
            if old.get('completed') != completed or old.get('functional_verified') is not False:
                raise Stop('Saved course outline completion ledger or pending functional proof is invalid')
            return result
        api = transport or delivery.Skill44Transport()
        base = '/courses/products/' + product
        def get(kind, identity):
            resource = base if kind == 'course' else base + ('/categories/' if kind=='category' else '/lessons/') + identity
            current = delivery._bound_resource(api.request('GET',resource,location_id=loc),identity,loc,kind,
                **({'productId':product} if kind!='course' else {}))
            if kind != 'course' and current.get('visibility') != 'draft':
                raise Stop('Outline targets and parent modules must remain inventoried drafts')
            return resource,current
        get('course',product)
        snapshots = {}
        for obj in objects[1:]:
            key = (obj['kind'],obj['id'])
            snapshots[key] = get(*key)
        tasks = []
        for group,kind in (('category_changes','category'),('lesson_changes','lesson')):
            for edit in plan[group]:
                identity = edit[kind+'_id']
                resource,current = snapshots[(kind,identity)]
                if current.get('updatedAt') != edit['expected_updated_at']:
                    raise Stop('Course outline target changed since inventory')
                if kind == 'lesson':
                    if current.get('categoryId') != edit['category_id']:
                        raise Stop('Lesson belongs to a different inventoried module')
                    changed_type = edit['changes'].get('contentType',current.get('contentType'))
                    if (changed_type != current.get('contentType')
                            and (changed_type in ('quiz','assignment') or current.get('contentType') in ('quiz','assignment'))):
                        raise Stop('Quiz and assignment transitions require their dedicated content operation')
                    if current.get('contentType') in ('quiz','assignment') and 'contentId' in edit['changes'] and edit['changes']['contentId'] != current.get('contentId'):
                        raise Stop('Existing quiz or assignment content cannot be rebound as an ordinary lesson edit')
                tasks.append((kind,identity,resource,current,edit['changes']))
        # Every target and inventory precondition has been checked before intent
        # or the first HTTP write; no later malformed target can leave half a build.
        state = {'operation':OPERATION,'location_id':loc,'fingerprint':fingerprint,
            'status':'RUNNING','objects':objects,'completed':[],
            'verification_required':True,'functional_verified':False}
        secure_json(path,state)
        try:
            for kind,identity,resource,current,changes in tasks:
                if not _preserved(changes,current):
                    if kind == 'lesson':
                        # A parent becoming live after preflight must not turn
                        # a draft-only edit into an implicit live-content job.
                        get('category',current['categoryId'])
                    _,fresh = get(kind,identity)
                    if not _preserved(current,fresh):
                        raise Stop('Course outline target changed after the complete preflight')
                    state.update(current_kind=kind,current_object_id=identity,current_step_status='INTENT_RECORDED')
                    secure_json(path,state)
                    api.request('PUT',resource,location_id=loc,body=changes)
                    _,actual = get(kind,identity)
                    expected = {key:value for key,value in {**current,**changes}.items() if key != 'updatedAt'}
                    if not _preserved(expected,actual):
                        raise Stop('Draft outline values or protected sibling fields did not persist')
                state['completed'].append({'kind':kind,'id':identity})
                state['current_step_status'] = 'VERIFIED'
                secure_json(path,state)
            state.update(status='NEEDS_VERIFICATION',current_step_status='VERIFIED')
            secure_json(path,state)
            return state
        except Exception as exc:
            state.update(status='NEEDS_RECONCILIATION',error_type=type(exc).__name__)
            secure_json(path,state)
            raise
    finally:
        os.close(fd)
