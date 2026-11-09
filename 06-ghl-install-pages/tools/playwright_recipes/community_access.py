"""Captured classic community privacy/access controls, without activation.

Selectors are the same native Details controls independently read by
community_portal._read_details. This module never logs in, invites members,
publishes/reactivates a group or edits its identity/description.

Access expansion requires an opaque, short-lived authorization produced by the
installed host's action-time confirmation capability. A JSON approval flag is
not authorization. Missing confirmation remains ACCESS_CONFIRMATION_REQUIRED.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import sys
import time

if __package__:
    from . import community_portal as portal
    from .evidence_lease import evidence_lease, journal_present, read_journal
    from .skill6_playwright import Stop, click, secure_json, wait_until
else:
    import community_portal as portal
    from evidence_lease import evidence_lease, journal_present, read_journal
    from skill6_playwright import Stop, click, secure_json, wait_until

if __name__ == 'community_access':
    sys.modules.setdefault('playwright_recipes.community_access', sys.modules[__name__])
elif __name__ == 'playwright_recipes.community_access':
    sys.modules.setdefault('community_access', sys.modules[__name__])


_APPROVAL = object()
_APPROVAL_TTL = 60
_JOURNAL = 'community-access-state.json'
_SCHEMA = 'skill6-community-access/1'
_FIELDS = frozenset(('privacy', *portal._DETAIL_FLAGS))


def _values(value, *, complete):
    if (not isinstance(value, Mapping) or not value or set(value) - _FIELDS
            or (complete and set(value) != _FIELDS)):
        raise Stop('Community access requires exact captured expected/desired control values')
    for key, state in value.items():
        if key == 'privacy':
            if state not in ('public', 'private'):
                raise Stop('Community privacy must be public or private')
        elif type(state) is not bool:
            raise Stop('Community access flags require real booleans')
    return dict(value)


def validate_inputs(inputs):
    data = portal._validate_base(inputs, portal._BASE_INPUTS | {'access'})
    access = inputs.get('access')
    if not isinstance(access, Mapping) or set(access) != {'expected', 'desired'}:
        raise Stop('Community access requires only expected and desired settings')
    expected = _values(access['expected'], complete=True)
    desired = _values(access['desired'], complete=False)
    return {**data, 'access': {'expected': expected, 'desired': desired}}


def configuration_hash(inputs):
    data = validate_inputs(inputs)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _desired(data):
    return {**data['access']['expected'], **data['access']['desired']}


def expands_access(before, after):
    return (before['privacy'] == 'private' and after['privacy'] == 'public'
            or before['accessible_from_switcher'] is False and after['accessible_from_switcher'] is True
            or before['allow_member_invites'] is False and after['allow_member_invites'] is True
            or before['mandatory_profile'] is True and after['mandatory_profile'] is False)


@dataclass(frozen=True)
class AccessAuthorization:
    page: object
    location_id: str
    portal_url: str
    user_hash: str
    configuration_sha256: str
    issued_at: float
    _grant: object
    _proof: object


@dataclass
class _GrantState:
    consumed: bool = False


def authorize_access_change(page, inputs, *, portal_context, confirm_at_action_time, clock=time.time):
    """The trusted host calls its real confirmation capability, never JSON code.

    confirm_at_action_time receives the exact expected/desired controls, location
    and group slug. It must synchronously represent the owner's current action-
    time confirmation. It must not be built from an input-file approval flag.
    No native controls are changed by obtaining this ephemeral authorization.
    """
    data = validate_inputs(inputs)
    portal._check_context(page, data, portal_context, clock=clock)
    if not callable(confirm_at_action_time):
        raise Stop('ACCESS_CONFIRMATION_REQUIRED: installed action-time confirmation capability missing')
    _, slug = portal._portal(data['portal_url'])
    request = {'operation': 'community_access', 'location_id': data['location_id'],
        'group_slug': slug, 'expected': dict(data['access']['expected']),
        'desired': _desired(data), 'expands_access': expands_access(data['access']['expected'], _desired(data))}
    try:
        confirmed = confirm_at_action_time(request)
    except Exception:
        raise Stop('ACCESS_CONFIRMATION_REQUIRED: installed confirmation capability failed') from None
    if confirmed is not True:
        raise Stop('ACCESS_CONFIRMATION_REQUIRED: exact community access change was not confirmed')
    portal._check_context(page, data, portal_context, clock=clock)
    return AccessAuthorization(page, data['location_id'], data['portal_url'], portal_context.user_hash,
        configuration_hash(data), clock(), _GrantState(), _APPROVAL)


def _check_authorization(page, data, context, authorization, clock, *, consume=False):
    if (not isinstance(authorization, AccessAuthorization) or authorization._proof is not _APPROVAL
            or authorization.page is not page or authorization.location_id != data['location_id']
            or authorization.portal_url != data['portal_url']
            or authorization.user_hash != context.user_hash
            or authorization.configuration_sha256 != configuration_hash(data)
            or not isinstance(authorization._grant, _GrantState) or authorization._grant.consumed
            or not 0 <= clock() - authorization.issued_at <= _APPROVAL_TTL):
        raise Stop('ACCESS_CONFIRMATION_REQUIRED: fresh exact same-session authorization required')
    if consume:
        authorization._grant.consumed = True


def _state(protected):
    return {'privacy': 'public' if protected['public'] else 'private',
            **{key:protected[key] for key in portal._DETAIL_FLAGS}}


def _receipt(data, *, reused, description_hash, expanded):
    _, slug = portal._portal(data['portal_url'])
    return {'status': 'NEEDS_VERIFICATION', 'location_id': data['location_id'],
        'objects': [{'kind': 'community', 'id': slug}],
        'configuration_sha256': configuration_hash(data), 'controls_verified': True,
        'protected_description_sha256': description_hash, 'description_unchanged': True,
        'access_expansion_performed': expanded, 'group_activation_attempted': False,
        'reused': reused, 'behavior_verified': False, 'verification_required': True,
        'identity_source': 'same_session_authenticated_read'}


def _replay(path, data):
    prior = read_journal(path)
    _, slug = portal._portal(data['portal_url'])
    if (not isinstance(prior, Mapping) or prior.get('schema') != _SCHEMA
            or prior.get('configuration_sha256') != configuration_hash(data)
            or prior.get('location_id') != data['location_id'] or prior.get('group_slug') != slug
            or prior.get('status') != 'NEEDS_VERIFICATION'):
        raise Stop('Community access journal is interrupted or unbound; reconcile before another write')
    raw = prior.get('outcome')
    if not isinstance(raw, Mapping):
        raise Stop('Community access saved outcome is malformed')
    description_hash = raw.get('protected_description_sha256')
    if (not isinstance(description_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', description_hash)
            or type(raw.get('reused')) is not bool
            or type(raw.get('access_expansion_performed')) is not bool):
        raise Stop('Community access saved proof is malformed')
    expected_expanded = not raw['reused'] and expands_access(data['access']['expected'], _desired(data))
    expected = _receipt(data, reused=raw['reused'], description_hash=description_hash, expanded=expected_expanded)
    if any(not portal._same_value(raw.get(key), value) for key, value in expected.items()):
        raise Stop('Community access saved proof differs from the authored operation')
    return {**expected, 'replayed': True}


def run_access(page, inputs, evidence_root, *, portal_context, access_authorization=None, clock=time.time):
    """Run the captured native Details path with intent, lease and exact readback."""
    data = validate_inputs(inputs)
    root = Path(evidence_root).resolve()
    with evidence_lease(root, data['location_id'], kind='community_access'):
        path = root / _JOURNAL
        if journal_present(path):
            result = _replay(path, data)
            portal._check_context(page, data, portal_context, clock=clock)
            return result
        portal._check_context(page, data, portal_context, clock=clock)
        dialog, description, protected = portal._open_details(page, data)
        current, desired = _state(protected), _desired(data)
        if current not in (data['access']['expected'], desired):
            raise Stop('Community access differs from its inventoried previous values')
        reused = current == desired
        expansion = not reused and expands_access(current, desired)
        if expansion:
            _check_authorization(page, data, portal_context, access_authorization, clock)
        description_before = description.input_value()
        description_hash = hashlib.sha256(description_before.encode()).hexdigest()
        _, slug = portal._portal(data['portal_url'])
        state = {'schema': _SCHEMA, 'configuration_sha256': configuration_hash(data),
            'location_id': data['location_id'], 'group_slug': slug, 'status': 'INTENT_RECORDED'}
        secure_json(path, state)
        try:
            if reused:
                click(dialog.get_by_role('button', name='Cancel', exact=True))
            else:
                if current['privacy'] != desired['privacy']:
                    label = desired['privacy'].title() + ' Group Radio Button'
                    click(dialog.get_by_role('radio', name=label, exact=True))
                for key, label in portal._DETAIL_FLAGS.items():
                    if current[key] != desired[key]:
                        click(dialog.get_by_role('button', name=label, exact=True))
                portal._check_context(page, data, portal_context, clock=clock, verify_control=False)
                description, before_save = portal._read_details(dialog, data)
                if _state(before_save) != desired or description.input_value() != description_before:
                    raise Stop('Community access edit changed protected copy or ignored a desired control')
                if expansion:
                    _check_authorization(page, data, portal_context, access_authorization, clock, consume=True)
                click(dialog.get_by_role('button', name='Save', exact=True))
                wait_until(lambda: dialog.get_by_role('button', name='Save', exact=True).count() == 1
                    and dialog.get_by_role('button', name='Save', exact=True).is_enabled(),
                    'Community access save did not settle')
            page.reload(wait_until='domcontentloaded', timeout=45000)
            portal._check_context(page, data, portal_context, clock=clock)
            reopened, description, after = portal._open_details(page, data)
            if _state(after) != desired or description.input_value() != description_before:
                raise Stop('Community access independent read-back failed or protected copy changed')
            click(reopened.get_by_role('button', name='Cancel', exact=True))
            portal._check_context(page, data, portal_context, clock=clock)
            outcome = _receipt(data, reused=reused, description_hash=description_hash, expanded=expansion)
            state.update(status='NEEDS_VERIFICATION', outcome=outcome)
            secure_json(path, state)
            return outcome
        except Exception as exc:
            state.update(status='RECONCILIATION_REQUIRED', error_type=type(exc).__name__)
            secure_json(path, state)
            raise
