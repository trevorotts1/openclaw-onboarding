"""Caller-owned, authenticated community portal channel configuration.

Create dialog selectors come from SELECTORS-LIVE-community.md, Phase B
2026-07-10; the current Add Channel control and inactive-group admin route
were captured in the authenticated portal on 2026-11-08.
There is deliberately no login, token bridge, domain discovery or membership
change here. A trusted host must capture same-page authenticated identity first.
Channel names can be independently observed after reload; description and
functional behavior remain unverified until their concrete read-back is captured.
"""
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import fcntl
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

# Direct CLI imports and package-host imports must share the live context type;
# a second class would reject a legitimate captured context as a different type.
if __name__ == 'community_portal':
    sys.modules.setdefault('playwright_recipes.community_portal', sys.modules[__name__])
elif __name__ == 'playwright_recipes.community_portal':
    sys.modules.setdefault('community_portal', sys.modules[__name__])

if __package__:
    from .skill6_playwright import Stop, click, fill, secure_json, wait_until
else:
    from skill6_playwright import Stop, click, fill, secure_json, wait_until


_PROOF = object()
_CONTEXT_TTL = 300
_ADD_CHANNEL_NAME = '+ Add Channel'
_ADD_CHANNEL_ID = 'add-channel__btn'


def _has_evidence(path):
    # A broken link is still retained evidence, never permission to overwrite.
    return path.exists() or path.is_symlink()


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise Stop('Community input requires ' + field)
    return value


def _portal(value):
    try:
        u = urlsplit(value)
        port = u.port
    except (TypeError, ValueError):
        raise Stop('Invalid community portal URL') from None
    if (u.scheme != 'https' or not u.hostname or u.username is not None
            or u.password is not None or u.query or u.fragment
            or port not in (None, 443)):
        raise Stop('Supply the exact credential-free HTTPS community portal URL')
    m = re.fullmatch(r'/communities/groups/([a-z0-9-]+)/(?:home|inactive-group)/?', u.path)
    if not m:
        raise Stop('Community portal route is not a captured group admin route')
    origin = 'https://' + u.netloc
    return origin, m.group(1)


def _validate_base(inputs, allowed):
    if not isinstance(inputs, Mapping) or set(inputs) - allowed:
        raise Stop('Unsupported community option; other settings need capture')
    if 'publish' in inputs and inputs['publish'] is not False:
        raise Stop('Community channel script does not publish or change group access')
    loc = _text(inputs.get('location_id'), 'location_id')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', loc):
        raise Stop('Invalid community location identity')
    _text(inputs.get('location_name'), 'location_name')
    _text(inputs.get('group_name'), 'group_name')
    u = urlsplit(_text(inputs.get('start_url'), 'start_url'))
    if (u.scheme != 'https' or u.netloc not in
            ('app.convertandflow.com', 'app.gohighlevel.com')
            or u.username is not None or u.password is not None or u.query
            or u.fragment or not re.fullmatch(
                r'/v2/location/' + re.escape(loc)
                + r'/memberships/communities/community-groups/?', u.path)):
        raise Stop('Community intake requires the canonical location-bound app list URL')
    _portal(_text(inputs.get('portal_url'), 'portal_url'))
    return dict(inputs)


_BASE_INPUTS = {'location_id', 'location_name', 'start_url', 'portal_url',
                'group_name', 'publish'}


def validate_inputs(inputs):
    data = _validate_base(inputs, _BASE_INPUTS | {'channels'})
    channels = inputs.get('channels')
    if not isinstance(channels, list) or not channels:
        raise Stop('Community channels must be a nonempty authored list')
    names = []
    for channel in channels:
        if not isinstance(channel, Mapping) or set(channel) != {'name', 'description'}:
            raise Stop('Each channel requires exactly authored name and description')
        names.append(_text(channel['name'], 'channel.name'))
        _text(channel['description'], 'channel.description')
    if len({n.casefold() for n in names}) != len(names):
        raise Stop('Duplicate community channel names require reconciliation')
    return data


def validate_details_inputs(inputs):
    """Only an authored description update; no name, slug or access changes."""
    data = _validate_base(inputs, _BASE_INPUTS | {'details'})
    details = inputs.get('details')
    if not isinstance(details, Mapping) or set(details) != {'description', 'expected_description'}:
        raise Stop('Community details require only authored description and expected_description')
    for key in ('description', 'expected_description'):
        value = details[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 150:
            raise Stop('Community description values must be nonempty text of at most 150 characters')
    return {**data, 'details': dict(details)}


def _context_inputs(inputs):
    return validate_details_inputs(inputs) if isinstance(inputs, Mapping) and 'details' in inputs else validate_inputs(inputs)


def _add_channel(page):
    """Use both captured identity anchors; a similar label is not permission."""
    add = page.get_by_role('button', name=_ADD_CHANNEL_NAME, exact=True)
    add.wait_for(state='visible', timeout=45000)
    if (add.count() != 1 or not add.is_visible()
            or add.get_attribute('id') != _ADD_CHANNEL_ID):
        raise Stop('Captured community channel control unavailable or ambiguous')
    return add


def _facts(page, inputs, reader, *, verify_control=True):
    """The reader is an installed host capability, never a JSON assertion."""
    if not callable(reader):
        raise Stop('Authenticated same-page community identity reader required')
    if page.url.rstrip('/') != inputs['portal_url'].rstrip('/'):
        raise Stop('Community portal context is on a different page or group')
    if page.get_by_placeholder('Password', exact=True).count():
        raise Stop('Community portal authentication required')
    # DOMContentLoaded is not portal readiness. Wait on the captured UI before
    # the single authenticated identity read, then recheck the route: hydration
    # must not bless a redirect or user change that happened during the wait.
    if verify_control:
        if 'details' in inputs:
            settings = page.get_by_role('button', name='SETTINGS', exact=True)
            settings.wait_for(state='visible', timeout=45000)
            if settings.count() != 1 or not settings.is_visible():
                raise Stop('Captured community settings control unavailable or ambiguous')
        else:
            _add_channel(page)
    group = page.get_by_text(inputs['group_name'], exact=True)
    group.first.wait_for(state='visible', timeout=45000)
    if group.count() < 1:
        raise Stop('Expected community name absent from the authenticated portal')
    if page.url.rstrip('/') != inputs['portal_url'].rstrip('/'):
        raise Stop('Community portal route changed during readiness wait')
    if page.get_by_placeholder('Password', exact=True).count():
        raise Stop('Community portal authentication required')
    try:
        value = reader(page)
    except Exception:
        raise Stop('Authenticated same-session community identity read failed') from None
    origin, slug = _portal(inputs['portal_url'])
    if (not isinstance(value, Mapping) or value.get('authenticated') is not True
            or value.get('location_id') != inputs['location_id']
            or value.get('portal_origin') != origin
            or value.get('group_slug') != slug
            or value.get('group_name') != inputs['group_name']
            or not isinstance(value.get('user_id'), str) or not value['user_id']
            or value.get('source_kind') != 'same_session_authenticated_read'):
        raise Stop('Community same-session account/location/group identity unconfirmed')
    if page.url.rstrip('/') != inputs['portal_url'].rstrip('/'):
        raise Stop('Community portal route changed during authenticated identity read')
    return dict(value)


@dataclass(frozen=True)
class PortalContext:
    page: object
    identity_reader: object
    location_id: str
    portal_url: str
    group_name: str
    user_hash: str
    observed_at: float
    _proof: object


def capture_context(page, inputs, *, identity_reader, clock=time.time):
    """Bind an actual trusted host identity read to this exact live Page.

    The host's reader must use this authenticated portal session. A different
    PIT/OAuth credential, route text or caller-authored receipt is not a reader.
    There is no built-in identity reader because that portal contract has not
    yet been captured; absence stays a concrete PORTAL_CONTEXT_REQUIRED stop.
    """
    data = _context_inputs(inputs)
    actual = _facts(page, data, identity_reader)
    return PortalContext(page, identity_reader, data['location_id'],
                         data['portal_url'], data['group_name'],
                         hashlib.sha256(actual['user_id'].encode()).hexdigest(),
                         clock(), _PROOF)


def _check_context(page, inputs, context, *, clock=time.time, verify_control=True):
    if (not isinstance(context, PortalContext) or context._proof is not _PROOF
            or context.page is not page
            or context.location_id != inputs['location_id']
            or context.portal_url.rstrip('/') != inputs['portal_url'].rstrip('/')
            or context.group_name != inputs['group_name']
            or not 0 <= clock() - context.observed_at <= _CONTEXT_TTL):
        raise Stop('Fresh caller-owned authenticated community portal context required')
    actual = _facts(page, inputs, context.identity_reader, verify_control=verify_control)
    if not 0 <= clock() - context.observed_at <= _CONTEXT_TTL:
        raise Stop('Community portal identity context expired during readiness wait')
    if hashlib.sha256(actual['user_id'].encode()).hexdigest() != context.user_hash:
        raise Stop('Community authenticated user changed; no write attempted')


def run_channels(page, inputs, evidence_root, *, portal_context, clock=time.time):
    """Execute the captured native sequence with protected per-run intent."""
    data = validate_inputs(inputs)
    root = Path(evidence_root).resolve()
    # A canonical authentication refusal is terminal across execution lanes.
    # Do not even invoke a different portal identity reader after that marker.
    if _has_evidence(root / 'auth-stop.json'):
        raise Stop('Canonical authentication refusal must be resolved before portal execution')
    if urlsplit(data['portal_url']).path.rstrip('/').endswith('/inactive-group'):
        # The authenticated inactive view exposes an enabled Add Channel button
        # but does not open its creation dialog (captured 2026-11-08). Never
        # activate a group or retry that ineffective click as a recovery path.
        raise Stop('DEPENDENCY_GROUP_INACTIVE: channel creation requires an active group; activation is a separate access change')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    locks = []
    try:
        for name in ('.runner.lock', 'provider.lock'):
            lock_path = root / name
            if lock_path.is_symlink():
                raise Stop('Community portal lock requires reconciliation')
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            except OSError:
                raise Stop('Community portal lock cannot be safely opened') from None
            locks.append(fd)
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop('Community portal evidence root is already leased') from None
        if any(_has_evidence(root / name) for name in
               ('state.json', 'handoff.json', 'provider-state.json', 'auth-stop.json',
                'delivery-state.json', 'calendar-delivery-state.json',
                'community-details-state.json')):
            raise Stop('Another execution lane has evidence here; reconcile before a portal write')
        existing = root / 'community-portal-state.json'
        if _has_evidence(existing):
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            replay = _replay_channels(existing, data, fingerprint)
            _check_context(page, data, portal_context, clock=clock)
            return replay
        _check_context(page, data, portal_context, clock=clock)
        return _run_owned(page, data, root, portal_context, clock)
    finally:
        for fd in reversed(locks):
            os.close(fd)


def _run_owned(page, data, root, context, clock):
    path = root / 'community-portal-state.json'
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if _has_evidence(path):
        return _replay_channels(path, data, fingerprint)
    # Inventory all requested names before the first mutation, avoiding a
    # partially-created batch followed by discovery of an existing target.
    for channel in data['channels']:
        if page.get_by_text(channel['name'], exact=True).count():
            raise Stop('Existing channel requires saved description inventory before reuse')
    _, slug = _portal(data['portal_url'])
    state = {'schema': 'skill6-community-portal/1', 'fingerprint': fingerprint,
             'location_id': data['location_id'], 'group_slug': slug,
             'status': 'STARTED', 'channels': []}
    secure_json(path, state)
    try:
        for index, channel in enumerate(data['channels']):
            _check_context(page, data, context, clock=clock)
            state.update(status='INTENT_RECORDED', current_channel=index,
                         current_name_sha256=hashlib.sha256(channel['name'].encode()).hexdigest())
            secure_json(path, state)
            click(_add_channel(page))
            fill(page.get_by_placeholder('e.g Marketing Reports', exact=True), channel['name'])
            fill(page.get_by_placeholder('Enter Description', exact=True), channel['description'])
            # Recheck the same-session identity immediately before the submit.
            # The dialog can obscure Add Channel, so use the bound reader and
            # page identity; the outer write-control proof was checked above.
            _check_context(page, data, context, clock=clock, verify_control=False)
            click(page.get_by_role('button', name='CREATE CHANNEL', exact=True))
            wait_until(lambda: page.get_by_text(channel['name'], exact=True).count() > 0,
                       'Submitted channel name did not appear')
            page.reload(wait_until='domcontentloaded', timeout=45000)
            _check_context(page, data, context, clock=clock)
            wait_until(lambda: page.get_by_text(channel['name'], exact=True).count() > 0,
                       'Channel name absent after independent portal reload')
            state['channels'].append({'name_sha256': hashlib.sha256(channel['name'].encode()).hexdigest(),
                                      'name_seen_after_reload': True,
                                      'description_verified': False})
            state.update(status='CHANNEL_NAME_OBSERVED_AFTER_RELOAD')
            secure_json(path, state)
        outcome = {'status': 'NEEDS_VERIFICATION', 'location_id': data['location_id'],
                   'objects': [{'kind': 'community', 'id': slug}],
                   'channel_count': len(state['channels']),
                   'channel_names_seen_after_reload': True,
                   'description_verified': False, 'behavior_verified': False,
                   'verification_required': True,
                   'identity_source': 'same_session_authenticated_read'}
        state.update(status='NEEDS_VERIFICATION', outcome=outcome)
        secure_json(path, state)
        return outcome
    except Exception as exc:
        state.update(status='RECONCILIATION_REQUIRED', error_type=type(exc).__name__)
        secure_json(path, state)
        raise


_DETAIL_FLAGS = {
    'accessible_from_switcher': 'Accessible from switcher checkbox',
    'allow_member_invites': 'Allow members to invite checkbox',
    'mandatory_profile': 'Show mandatory profile modal checkbox',
}


def _same_value(actual, expected):
    """Journal booleans and integer counts must not coerce into each other."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _same_value(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_value(left, right) for left, right in zip(actual, expected))
    return actual == expected


def _bound_replay_journal(path, data, fingerprint, schema):
    """Read retained evidence without modifying or echoing malformed contents."""
    if path.is_symlink():
        raise Stop('Community journal link requires independent reconciliation')
    try:
        prior = json.loads(path.read_text())
    except (ValueError, OSError):
        raise Stop('Community journal cannot be read; reconciliation required') from None
    _, slug = _portal(data['portal_url'])
    expected = {'schema': schema, 'fingerprint': fingerprint,
                'location_id': data['location_id'], 'group_slug': slug,
                'status': 'NEEDS_VERIFICATION'}
    if not isinstance(prior, dict) or any(
            not _same_value(prior.get(key), value) for key, value in expected.items()):
        raise Stop('Community journal is unbound or interrupted; independent reconciliation required')
    return prior, slug


def _minimal_replay_outcome(raw, expected):
    # Only known, independently bound proof fields leave the evidence root.
    # Unknown top-level fields remain private in the unchanged journal. Native
    # object identities must match the complete expected shape, with no extras.
    if not isinstance(raw, dict) or any(
            not _same_value(raw.get(key), value) for key, value in expected.items()):
        raise Stop('Community saved outcome is invalid; independent reconciliation required')
    return {**expected, 'replayed': True}


def _replay_channels(path, data, fingerprint):
    prior, slug = _bound_replay_journal(path, data, fingerprint, 'skill6-community-portal/1')
    expected_rows = [{'name_sha256': hashlib.sha256(channel['name'].encode()).hexdigest(),
                      'name_seen_after_reload': True, 'description_verified': False}
                     for channel in data['channels']]
    if (not _same_value(prior.get('channels'), expected_rows)
            or not _same_value(prior.get('current_channel'), len(expected_rows) - 1)
            or not _same_value(prior.get('current_name_sha256'), expected_rows[-1]['name_sha256'])):
        raise Stop('Community channel journal proof is invalid; independent reconciliation required')
    expected = {'status': 'NEEDS_VERIFICATION', 'location_id': data['location_id'],
                'objects': [{'kind': 'community', 'id': slug}],
                'channel_count': len(expected_rows), 'channel_names_seen_after_reload': True,
                'description_verified': False, 'behavior_verified': False,
                'verification_required': True, 'identity_source': 'same_session_authenticated_read'}
    return _minimal_replay_outcome(prior.get('outcome'), expected)


def _replay_details(path, data, fingerprint):
    prior, slug = _bound_replay_journal(path, data, fingerprint, 'skill6-community-details/1')
    digest = hashlib.sha256(data['details']['description'].encode()).hexdigest()
    outcome = prior.get('outcome')
    if (not _same_value(prior.get('description_sha256'), digest)
            or not isinstance(outcome, dict) or type(outcome.get('reused')) is not bool):
        raise Stop('Community details journal proof is invalid; independent reconciliation required')
    expected = {'status': 'NEEDS_VERIFICATION', 'location_id': data['location_id'],
                'objects': [{'kind': 'community', 'id': slug}], 'description_sha256': digest,
                'description_verified': True, 'protected_access_unchanged': True,
                'group_activation_attempted': False, 'reused': outcome['reused'],
                'behavior_verified': False, 'verification_required': True,
                'identity_source': 'same_session_authenticated_read'}
    return _minimal_replay_outcome(outcome, expected)


def _open_details(page, inputs):
    """Captured Details controls; names and slug bind the exact group."""
    click(page.get_by_role('button', name='SETTINGS', exact=True))
    dialog = page.get_by_role('dialog')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1:
        raise Stop('Community settings dialog is ambiguous')
    click(dialog.get_by_role('menuitem', name='Details', exact=True))
    description, protected = _read_details(dialog, inputs)
    return dialog, description, protected


def _read_details(dialog, inputs):
    """Recheck every field that the native Save submits, including access."""
    name = dialog.get_by_placeholder('Group Name', exact=True)
    slug = dialog.get_by_placeholder('Group Slug', exact=True)
    description = dialog.get_by_placeholder('Enter a brief description', exact=True)
    description.wait_for(state='visible', timeout=45000)
    _, expected_slug = _portal(inputs['portal_url'])
    if (name.count() != 1 or slug.count() != 1 or description.count() != 1
            or name.input_value() != inputs['group_name']
            or slug.input_value() != expected_slug):
        raise Stop('Community settings name or slug does not match the bound group')
    protected = {}
    for key in ('Public', 'Private'):
        radio = dialog.get_by_role('radio', name=key + ' Group Radio Button', exact=True)
        value = radio.get_attribute('aria-checked') if radio.count() == 1 else None
        if value not in ('true', 'false'):
            raise Stop('Community privacy control identity or state changed')
        protected[key.lower()] = value == 'true'
    if protected['public'] == protected['private']:
        raise Stop('Community privacy selection is ambiguous')
    for key, label in _DETAIL_FLAGS.items():
        button = dialog.get_by_role('button', name=label, exact=True)
        checkbox = button.get_by_role('checkbox')
        value = checkbox.get_attribute('aria-checked') if button.count() == 1 and checkbox.count() == 1 else None
        if value not in ('true', 'false'):
            raise Stop('Community access flag identity or state changed')
        protected[key] = value == 'true'
    return description, protected


def run_details(page, inputs, evidence_root, *, portal_context, clock=time.time):
    """Save only an authored description; preserve privacy and access flags.

    Active and inactive admin views share the captured Details modal. This
    operation never changes the group status, name, slug, membership or access.
    The exact same-session location/user reader remains mandatory.
    """
    data = validate_details_inputs(inputs)
    root = Path(evidence_root).resolve()
    if _has_evidence(root / 'auth-stop.json'):
        raise Stop('Canonical authentication refusal must be resolved before portal execution')
    if __package__:
        from .evidence_lease import evidence_lease
    else:
        from evidence_lease import evidence_lease
    with evidence_lease(root, data['location_id'], kind='community_details'):
        existing = root / 'community-details-state.json'
        if _has_evidence(existing):
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            replay = _replay_details(existing, data, fingerprint)
            _check_context(page, data, portal_context, clock=clock)
            return replay
        _check_context(page, data, portal_context, clock=clock)
        return _run_details_owned(page, data, root, portal_context, clock)


def _run_details_owned(page, data, root, context, clock):
    path = root / 'community-details-state.json'
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if _has_evidence(path):
        return _replay_details(path, data, fingerprint)
    dialog, description, protected = _open_details(page, data)
    requested = data['details']['description']
    current = description.input_value()
    if current not in (data['details']['expected_description'], requested):
        raise Stop('Community description differs from expected inventory; reconcile before replacement')
    _, slug = _portal(data['portal_url'])
    state = {'schema': 'skill6-community-details/1', 'fingerprint': fingerprint,
             'location_id': data['location_id'], 'group_slug': slug,
             'status': 'INTENT_RECORDED',
             'description_sha256': hashlib.sha256(requested.encode()).hexdigest()}
    secure_json(path, state)
    try:
        reused = current == requested
        if reused:
            click(dialog.get_by_role('button', name='Cancel', exact=True))
        else:
            fill(description, requested)
            _check_context(page, data, context, clock=clock, verify_control=False)
            description, before_save = _read_details(dialog, data)
            if before_save != protected or description.input_value() != requested:
                raise Stop('Community details or protected access changed before Save')
            click(dialog.get_by_role('button', name='Save', exact=True))
            # Native Save keeps the modal open. During persistence the button
            # briefly changes accessible name to "loading Save"; wait for the
            # exact idle Save control, then reload and independently reopen.
            wait_until(lambda: dialog.get_by_role('button', name='Save', exact=True).count() == 1
                       and dialog.get_by_role('button', name='Save', exact=True).is_enabled(),
                       'Community details save did not finish')
        page.reload(wait_until='domcontentloaded', timeout=45000)
        _check_context(page, data, context, clock=clock)
        reopened, description, saved_protected = _open_details(page, data)
        if description.input_value() != requested:
            raise Stop('Community description was not persisted')
        if saved_protected != protected:
            raise Stop('Community privacy or access flags changed while saving the description')
        click(reopened.get_by_role('button', name='Cancel', exact=True))
        _check_context(page, data, context, clock=clock)
        outcome = {'status': 'NEEDS_VERIFICATION', 'location_id': data['location_id'],
                   'objects': [{'kind': 'community', 'id': slug}],
                   'description_sha256': state['description_sha256'],
                   'description_verified': True, 'protected_access_unchanged': True,
                   'group_activation_attempted': False, 'reused': reused,
                   'behavior_verified': False, 'verification_required': True,
                   'identity_source': 'same_session_authenticated_read'}
        state.update(status='NEEDS_VERIFICATION', outcome=outcome)
        secure_json(path, state)
        return outcome
    except Exception as exc:
        state.update(status='RECONCILIATION_REQUIRED', error_type=type(exc).__name__)
        secure_json(path, state)
        raise
