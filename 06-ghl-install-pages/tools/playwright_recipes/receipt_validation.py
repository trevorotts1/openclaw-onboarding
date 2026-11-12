"""Minimal bound receipts shared by provider and direct-delivery replay paths."""
from collections import Counter
from collections.abc import Mapping
import re

if __package__:
    from .skill6_playwright import Stop
    from .evidence_lease import read_journal
else:
    from skill6_playwright import Stop
    from evidence_lease import read_journal


OBJECT_KINDS = frozenset(('course','category','lesson','quiz','question','page','form',
                         'survey','website','funnel','room','community','channel','calendar'))
CREATE_ROOTS = {'courses.create':'course', 'funnels.create':'funnel',
                'websites.create':'website', 'forms.create':'form',
                'surveys.create':'survey', 'quizzes.create':'quiz',
                'communities.create':'community', 'courses.lesson_quiz.create':'quiz'}


def pending_proof(value):
    return (value.get('status') == 'NEEDS_VERIFICATION'
            or any(value.get(key) is False for key in (
                'behavior_verified','submission_verified','payment_verified','authorization_completed',
                'functional_verified','checkout_ready'))
            or any(value.get(key) == 'REQUIRED' for key in (
                'independent_readback','behavior_verification')))


def minimal_objects(operation, objects):
    """Validate real root kind and strip every non-identity object field."""
    if not isinstance(objects, list) or any(
            not isinstance(obj, Mapping) or not isinstance(obj.get('kind'), str)
            or obj['kind'] not in OBJECT_KINDS or not isinstance(obj.get('id'), str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',obj['id'])
            for obj in objects):
        raise Stop('Object identity receipt malformed')
    required = CREATE_ROOTS.get(operation)
    if ((operation.endswith('.create') and not objects)
            or (required is not None and not any(obj['kind'] == required for obj in objects))):
        raise Stop('Create completion requires its operation-specific object identity')
    return [{'kind':obj['kind'],'id':obj['id']} for obj in objects]


def replay_delivery(path, *, operation, location_id, fingerprint, expected_counts,
                    expected_ids=None):
    """A saved direct API result is replayable only with completed bound proof.

    Legacy journals lack operation, but their exact operation-specific input
    fingerprint, tenant, object inventory and VERIFIED marker are still required.
    New journals explicitly carry the operation. Replay never returns authored
    content, arbitrary response data or a private meeting invitation.
    """
    old = read_journal(path)
    if (not isinstance(old, Mapping) or old.get('fingerprint') != fingerprint
            or old.get('location_id') != location_id
            or ('operation' in old and old['operation'] != operation)):
        raise Stop('Delivery evidence belongs to a different operation or location')
    if (old.get('status') not in ('API_STEPS_COMPLETE','NEEDS_VERIFICATION')
            or old.get('current_step_status') != 'VERIFIED'):
        raise Stop('Interrupted API delivery requires reconciliation')
    objects = minimal_objects(operation,old.get('objects'))
    if Counter(obj['kind'] for obj in objects) != Counter(expected_counts):
        raise Stop('Saved delivery object inventory does not match the completed plan')
    if len({(obj['kind'],obj['id']) for obj in objects}) != len(objects):
        raise Stop('Saved delivery object identities are duplicated')
    for kind, identity in (expected_ids or {}).items():
        if [obj['id'] for obj in objects if obj['kind'] == kind] != [identity]:
            raise Stop('Saved delivery target identity differs from the requested object')
    return {'status':'NEEDS_VERIFICATION' if pending_proof(old) else 'ALREADY_EXECUTED',
            'operation':operation,'location_id':location_id,'fingerprint':fingerprint,
            'objects':objects,'current_step_status':'VERIFIED','verification_required':True}
