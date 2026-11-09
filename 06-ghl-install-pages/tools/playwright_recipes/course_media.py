"""Upload approved PNGs and attach them to documented Courses API media fields.

Reuses the existing location-PIT media upload rail and course customization
preservation contract. This edits product appearance, not inactive-template
media pickers, custom blocks, publication or learner access.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit

if __package__:
    from . import delivery
    from .evidence_lease import guard_delivery, journal_present, read_journal
    from .skill6_playwright import Stop, secure_json
else:
    import delivery
    from evidence_lease import guard_delivery, journal_present, read_journal
    from skill6_playwright import Stop, secure_json


FIELDS = frozenset(('posterImage', 'logoImage', 'heroImage', 'favicon', 'instructorHeadshot'))
COMMON = frozenset(('location_id', 'location_name', 'start_url', 'publish', 'api_capability'))
_MAX_BYTES = 25 * 1024 * 1024
_PNG = b'\x89PNG\r\n\x1a\n'
_SCHEMA = 'skill6-course-media/1'


def _url(value, *, existing=False):
    if existing and value in (None, ''):
        return value
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise Stop('Course media requires a credential-free HTTPS URL')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise Stop('Course media URL is malformed') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or port not in (None, 443) or parsed.fragment):
        raise Stop('Course media requires a credential-free HTTPS URL')
    return value


def validate_inputs(inputs):
    if (not isinstance(inputs, dict)
            or set(inputs) - COMMON - {'product_id', 'expected_updated_at', 'media_assets'}):
        raise Stop('Unsupported course media input')
    plan = deepcopy(inputs)
    delivery._id(plan.get('location_id'), 'location_id')
    delivery._id(plan.get('product_id'), 'product_id')
    delivery._text(plan.get('expected_updated_at'), 'expected_updated_at')
    if 'publish' in plan and plan['publish'] is not False:
        raise Stop('Course media never publishes or activates a course')
    assets = plan.get('media_assets')
    if not isinstance(assets, list) or not assets or len(assets) > len(FIELDS):
        raise Stop('Course media requires one to five authored PNG assets')
    seen = set()
    for asset in assets:
        if (not isinstance(asset, dict)
                or set(asset) != {'field', 'file', 'sha256', 'name', 'expected_url'}
                or not isinstance(asset.get('field'), str)
                or asset['field'] not in FIELDS or asset['field'] in seen):
            raise Stop('Course media assets require unique documented target fields')
        seen.add(asset['field'])
        if (not isinstance(asset['file'], str) or not Path(asset['file']).is_absolute()
                or not isinstance(asset['sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', asset['sha256'])
                or not isinstance(asset['name'], str) or not asset['name'].strip()
                or len(asset['name']) > 200 or any(ord(char) < 32 for char in asset['name'])):
            raise Stop('Course media requires an absolute file, approved SHA256 and authored media name')
        _url(asset['expected_url'], existing=True)
    return plan


def configuration_hash(inputs):
    plan = validate_inputs(inputs)
    # Identical approved bytes can be materialized at another local path.
    assets = [{key: value for key, value in asset.items() if key != 'file'}
              for asset in plan['media_assets']]
    bound = {key: plan[key] for key in ('location_id', 'product_id', 'expected_updated_at')}
    bound['media_assets'] = assets
    return hashlib.sha256(json.dumps(bound, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _capability(record, location_id):
    scopes = record.get('scopes') if isinstance(record, dict) else None
    if not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes):
        raise Stop('Course media requires explicit proven course and media scopes')
    delivery._capability(record, location_id,
        scopes=('courses.readonly', 'courses.write', 'medias.write'))


def validate_api_inputs(operation, inputs, route):
    """Read-only schema, capability and exact route check for the host front door."""
    plan = validate_inputs(inputs)
    if (operation != 'courses.update' or not isinstance(route, dict)
            or route.get('operation') != operation or route.get('version') != 'v3'
            or route.get('location_id') != plan['location_id']
            or route.get('lane') not in ('public_api', 'skill44', 'official_mcp')):
        raise Stop('Course media requires its exact courses.update location-bound v3 route')
    _capability(inputs.get('api_capability'), plan['location_id'])
    return plan


def course_executor(*, operation, inputs, route, evidence_root):
    validate_api_inputs(operation, inputs, route)
    if route['lane'] not in ('public_api', 'skill44'):
        raise Stop('Course media HTTP executor does not substitute for official MCP')
    return run_media(inputs, evidence_root, capability=inputs.get('api_capability'))


def _bytes(asset):
    descriptor = None
    try:
        descriptor = os.open(asset['file'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 8 < info.st_size <= _MAX_BYTES:
            raise Stop('Course media source must be a regular PNG of at most 25 MiB')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            content = stream.read(_MAX_BYTES + 1)
        if (len(content) > _MAX_BYTES or not content.startswith(_PNG)
                or hashlib.sha256(content).hexdigest() != asset['sha256']):
            raise Stop('Course media bytes differ from the approved PNG hash')
        return content
    except OSError:
        raise Stop('Course media source is unavailable or unsafe') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _current_urls(current, assets):
    custom = current.get('customizations')
    if custom is not None and not isinstance(custom, dict):
        raise Stop('Existing course customizations are malformed')
    return {asset['field']: (current if asset['field'] == 'posterImage' else custom or {}).get(asset['field'])
            for asset in assets}


def _read(api, plan):
    return delivery._bound_resource(api.request('GET', '/courses/products/' + plan['product_id'],
        location_id=plan['location_id']), plan['product_id'], plan['location_id'], 'course')


def _upload(path, location_id, name, api):
    # Existing canonical resolver supplies this same location-class token; the
    # successful course GET and upload's locationId bind both rails to one job.
    import ghl_media
    if not isinstance(api, delivery.Skill44Transport):
        raise Stop('Injected course transport requires its own same-location media uploader')
    api.client.check_write('POST', ghl_media.GHL_SERVICES_ORIGIN + ghl_media.GHL_MEDIA_UPLOAD_PATH,
        {'locationId':location_id, 'name':name, 'hosted':False}, location_id=location_id)
    return ghl_media.upload_media(str(path), location_id, name, api.client._get_token())


@guard_delivery('course')
def run_media(inputs, evidence_root, *, capability, transport=None, uploader=None):
    """Record intent before each upload/PUT; never retry an uncertain upload."""
    plan = validate_inputs(inputs)
    if os.environ.get('CAF_DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on'):
        raise Stop('Use host --check for read-only course media validation')
    _capability(capability, plan['location_id'])
    root = Path(evidence_root).resolve()
    journal = root / 'delivery-state.json'
    digest = configuration_hash(plan)
    if journal_present(journal):
        prior = read_journal(journal)
        if (not isinstance(prior, dict) or prior.get('schema') != _SCHEMA
                or prior.get('operation') != 'courses.update'
                or prior.get('location_id') != plan['location_id']
                or prior.get('product_id') != plan['product_id']
                or prior.get('fingerprint') != digest
                or prior.get('status') != 'API_STEPS_COMPLETE'
                or prior.get('current_step_status') != 'VERIFIED'
                or prior.get('objects') != [{'kind':'course', 'id':plan['product_id']}]
                or type(prior.get('media_count')) is not int
                or prior.get('media_count') != len(plan['media_assets'])
                or prior.get('functional_verified') is not False
                or prior.get('verification_required') is not True):
            raise Stop('Course media journal is uncertain or unbound; reconcile before another write')
        uploaded = prior.get('uploaded_media')
        if not isinstance(uploaded, list) or len(uploaded) != len(plan['media_assets']):
            raise Stop('Course media journal upload evidence is incomplete')
        for asset, result in zip(plan['media_assets'], uploaded):
            if (not isinstance(result, dict)
                    or set(result) != {'field', 'id', 'source_sha256', 'url'}
                    or result['field'] != asset['field'] or result['source_sha256'] != asset['sha256']
                    or not isinstance(result['id'], str) or not result['id']):
                raise Stop('Course media journal upload evidence differs from the approved asset')
            _url(result['url'])
        return {**prior, 'replayed':True}
    # Read every source byte before the first network operation or upload.
    content = [_bytes(asset) for asset in plan['media_assets']]
    api = transport or delivery.Skill44Transport()
    current = _read(api, plan)
    expected_urls = {asset['field']:asset['expected_url'] for asset in plan['media_assets']}
    if (current.get('updatedAt') != plan['expected_updated_at']
            or _current_urls(current, plan['media_assets']) != expected_urls):
        raise Stop('Course media inventory changed; refresh before upload')
    # Prove the replacing customization contract is supported before upload.
    probe = {asset['field']:asset['expected_url'] for asset in plan['media_assets'] if asset['field'] != 'posterImage'}
    if probe:
        delivery._customization_update({'customizations':probe}, current)
    state = {'schema':_SCHEMA, 'operation':'courses.update', 'location_id':plan['location_id'],
        'product_id':plan['product_id'], 'fingerprint':digest,
        'status':'RUNNING', 'current_step_status':'INTENT_RECORDED',
        'verification_required':True, 'functional_verified':False,
        'objects':[{'kind':'course', 'id':plan['product_id']}],
        'uploaded_media':[], 'media_count':len(plan['media_assets'])}
    secure_json(journal, state)
    try:
        changes = {}
        with tempfile.TemporaryDirectory(prefix='skill6-course-media-') as temporary:
            for index, (asset, raw) in enumerate(zip(plan['media_assets'], content)):
                path = Path(temporary) / (str(index) + '.png')
                path.write_bytes(raw)
                path.chmod(0o600)
                state.update(current_kind='media_upload', current_asset=index,
                             current_step_status='INTENT_RECORDED')
                secure_json(journal, state)
                result = (uploader or _upload)(path, plan['location_id'], asset['name'], api)
                if (not isinstance(result, dict) or type(result.get('http')) is not int
                        or not 200 <= result['http'] < 300
                        or not isinstance(result.get('fileId'), str) or not result['fileId']):
                    raise Stop('Course media upload did not return a proven media identity')
                url = _url(result.get('url'))
                state['uploaded_media'].append({'field':asset['field'], 'id':result['fileId'],
                    'source_sha256':asset['sha256'], 'url':url})
                secure_json(journal, state)
                if asset['field'] == 'posterImage':
                    changes['posterImage'] = url
                else:
                    changes.setdefault('customizations', {})[asset['field']] = url
        latest = _read(api, plan)
        if (latest.get('updatedAt') != plan['expected_updated_at']
                or not delivery._matches(current, latest, exact=True)):
            raise Stop('Course changed during upload; uploaded media retained for reconciliation')
        payload, desired = delivery._customization_update(changes, latest)
        state.update(current_kind='course_media', current_step_status='INTENT_RECORDED')
        secure_json(journal, state)
        api.request('PUT', '/courses/products/' + plan['product_id'],
                    location_id=plan['location_id'], body=payload)
        actual = _read(api, plan)
        if not delivery._matches(desired, actual):
            raise Stop('Course media persisted read-back differs')
        state.update(status='API_STEPS_COMPLETE', current_step_status='VERIFIED')
        secure_json(journal, state)
        return state
    except Exception as error:
        state.update(status='NEEDS_RECONCILIATION', error_type=type(error).__name__)
        secure_json(journal, state)
        raise
