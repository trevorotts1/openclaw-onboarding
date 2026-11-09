"""Captured app community inventory and explicitly active, undiscoverable create.

The November 9, 2026 native app has separate Active/Inactive filters, a
non-paginated .grid-custom/.group-card list, and no group slug/id/link on cards.
It has no All filter or group search. Create Group opens a full page with one
Discovery switch; privacy is not a control on that page.

Never turn a name-only card into a verified slug identity. Existing matches stop
for reconciliation. Inactive creation also stops before writes because safely
deactivating a newly named row requires stronger native identity. The active
creation path is available only with explicit inactive=False and Discovery off.
No Login, invitation, ownership transfer or status dropdown is ever clicked here.
"""
from copy import deepcopy
import hashlib
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, wait_until


_CONTEXT = {'location_id', 'location_name', 'start_url'}
_ALLOWED = {'id', 'action', '_context', 'name', 'slug', 'description',
            'allow_creation', 'inactive', 'discovery'}
_TITLE = '.group-footer div.mt-3.truncate.pb-4.text-center.text-lg.font-medium.text-gray-800'
_EMPTY = re.compile(r"^You don[’']t have a community yet$")


def validate(step):
    if (not isinstance(step, dict) or set(step) - _ALLOWED
            or step.get('action', 'community') != 'community'):
        raise Stop('Unsupported community creation option; portal settings need their separate handler')
    data = deepcopy(step)
    context = data.get('_context')
    if (not isinstance(context, dict) or set(context) != _CONTEXT
            or any(not isinstance(context[key], str) or not context[key].strip() for key in _CONTEXT)
            or not re.fullmatch(r'[A-Za-z0-9_-]+', context['location_id'])):
        raise Stop('Community creation requires its canonical location-bound runner context')
    try:
        start = urlsplit(context['start_url'])
        port = start.port
    except ValueError:
        raise Stop('Invalid community app start URL') from None
    if (start.scheme != 'https' or start.netloc not in ('app.convertandflow.com', 'app.gohighlevel.com')
            or start.username is not None or start.password is not None
            or start.query or start.fragment or port not in (None, 443)
            or start.path != '/v2/location/' + context['location_id']
                + '/memberships/communities/community-groups'):
        raise Stop('Community creation requires its exact canonical location-bound Groups list start URL')
    for key, limit in (('name', 100), ('description', 150)):
        value = data.get(key)
        if (not isinstance(value, str) or not value.strip() or len(value) > limit
                or (key == 'name' and value != value.strip())
                or any(ord(char) < 32 and (key == 'name' or char not in '\r\n\t') for char in value)):
            raise Stop('Community ' + key + ' must be authored text within its supported limit')
    slug = data.get('slug')
    if (not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)
            or len(slug) > 50):
        raise Stop('Community slug must be an authored lowercase slug of at most 50 characters')
    for key in ('allow_creation', 'inactive', 'discovery'):
        if key in data and type(data[key]) is not bool:
            raise Stop('Community ' + key + ' requires a real boolean')
    if data.get('discovery', False) is not False:
        raise Stop('Community Discovery exposure is outside this undiscoverable creation path')
    return data


def _list_url(context):
    start = urlsplit(context['start_url'])
    return (start.scheme + '://' + start.netloc + '/v2/location/' + context['location_id']
            + '/memberships/communities/community-groups')


def _assert_list(page, context):
    if page.url != _list_url(context):
        raise Stop('Community inventory moved away from its exact location-bound list')
    assert_tenant(page, context)


def _filter(page):
    shown = []
    for value in ('Active', 'Inactive'):
        button = page.get_by_role('button', name=value, exact=True)
        if button.count() > 1:
            raise Stop('Community status filter is ambiguous')
        if button.count() == 1 and button.is_visible():
            shown.append(value)
    if len(shown) > 1:
        raise Stop('Community list filter layout changed')
    return shown[0] if shown else None


def _snapshot(page, status):
    if _filter(page) != status:
        return None
    # These are refusal-only checks for unsupported list additions, never
    # speculative mutation targets. The captured current list is unpaginated.
    pagination = page.get_by_role('button', name=re.compile(
        r'^(?:Next|Previous|Load more|Next page|Previous page)$', re.IGNORECASE))
    if any(pagination.nth(index).is_visible() for index in range(pagination.count())):
        raise Stop('Community inventory is paginated; complete native enumeration needs capture')
    grids = page.locator('.grid-custom')
    if grids.count() > 1:
        raise Stop('Community list grid is ambiguous')
    cards = page.locator('.grid-custom .group-card')
    if cards.count() != page.locator('.group-card').count():
        raise Stop('Community card layout changed outside the captured inventory grid')
    if not cards.count():
        empty = page.get_by_text(_EMPTY)
        if empty.count() == 1 and empty.is_visible():
            return []
        return None
    if grids.count() != 1:
        return None
    rows = []
    for index in range(cards.count()):
        card = cards.nth(index)
        title = card.locator(_TITLE)
        state = card.locator('#status_button')
        if title.count() > 1 or state.count() > 1:
            raise Stop('Community card title/status identity is ambiguous')
        if title.count() != 1 or state.count() != 1:
            return None
        name, actual_status = title.inner_text().strip(), state.inner_text().strip()
        if not name:
            return None
        if actual_status != status:
            return None
        rows.append({'name': name, 'status': actual_status})
    return rows


def _read_filter(page, context, status):
    _assert_list(page, context)
    wait_until(lambda: _filter(page) is not None, 'Community status filter did not hydrate')
    current = _filter(page)
    ready = {}
    def current_ready():
        value = _snapshot(page, current)
        if value is None:
            return False
        ready['rows'] = value
        return True
    wait_until(current_ready, 'Community current filter inventory did not settle')
    if current != status:
        click(page.get_by_role('button', name=current, exact=True))
        option = page.get_by_text(status, exact=True)
        if option.count() != 1:
            raise Stop('Captured community status option is ambiguous')
        click(option)
    def requested_ready():
        value = _snapshot(page, status)
        if value is None:
            return False
        ready['rows'] = value
        return True
    wait_until(requested_ready, 'Community requested filter inventory did not settle')
    _assert_list(page, context)
    return ready['rows']


def inventory(page, context):
    """Read both captured status lists twice, refusing moving/stale inventory."""
    url = _list_url(context)
    snapshots = []
    for _ in range(2):
        if page.url == url:
            page.reload(wait_until='domcontentloaded', timeout=45000)
        else:
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
        rows = _read_filter(page, context, 'Active') + _read_filter(page, context, 'Inactive')
        snapshots.append(sorted((row['name'], row['status']) for row in rows))
    if snapshots[0] != snapshots[1]:
        raise Stop('Community inventory changed during independent enumeration; reconcile before creating')
    return [{'name': name, 'status': status} for name, status in snapshots[1]]


def configure(page, step):
    data = validate(step)
    context = data['_context']
    before = inventory(page, context)
    matches = [row for row in before if row['name'].casefold() == data['name'].casefold()]
    if matches:
        # App cards expose no slug/id/portal link. Never Login into another
        # portal or accept caller-authored slug claims to upgrade this proof.
        raise Stop('EXISTING_GROUP_IDENTITY_UNVERIFIED: same-name native group requires exact slug reconciliation; no write attempted')
    if data.get('allow_creation') is not True:
        raise Stop('GROUP_ABSENT: explicit creation input is required; no write attempted')
    if data.get('inactive', True) is not False:
        raise Stop('GROUP_SLUG_IDENTITY_REQUIRED: inactive creation needs exact post-create identity before safe deactivation; no write attempted')
    _read_filter(page, context, 'Active')
    create = page.get_by_role('button', name='Create Group', exact=True)
    if create.count() != 1 or not create.is_visible():
        raise Stop('Captured native Create Group control changed')
    click(create)
    expected_url = _list_url(context).rsplit('/', 1)[0] + '/create-group'
    wait_until(lambda: page.url == expected_url, 'Native community create page did not open')
    assert_tenant(page, context)
    fields = {key:page.get_by_placeholder(label, exact=True) for key, label in (
        ('name', 'Group Name'), ('slug', 'Group Slug'), ('description', 'Enter a brief description'))}
    for control in fields.values():
        control.wait_for(state='visible', timeout=45000)
        if control.count() != 1:
            raise Stop('Community create field identity changed')
    discovery = page.get_by_role('switch')
    if discovery.count() != 1 or discovery.get_attribute('aria-checked') not in ('true', 'false'):
        raise Stop('Community create Discovery control changed')
    for key in ('name', 'slug', 'description'):
        fill(fields[key], data[key])
        fields[key].press('Tab')
    if discovery.get_attribute('aria-checked') != 'false':
        click(discovery)
    if (any(control.input_value() != data[key] for key, control in fields.items())
            or discovery.get_attribute('aria-checked') != 'false' or page.url != expected_url):
        raise Stop('Community create form ignored an input or changed identity')
    assert_tenant(page, context)
    submit = page.get_by_role('button', name='Create Group', exact=True)
    if submit.count() != 1:
        raise Stop('Community create submit control changed')
    wait_until(lambda: submit.is_enabled(), 'Community create fields or slug are not accepted by the native form')
    click(submit)
    fields['name'].wait_for(state='hidden', timeout=45000)
    after = inventory(page, context)
    actual = [row for row in after if row['name'] == data['name']]
    if len(actual) != 1 or actual[0]['status'] != 'Active':
        raise Stop('Created community is not uniquely present in the native Active inventory')
    # The named app card proves the native create persisted, but still cannot
    # prove a slug, portal identity, privacy or member behavior. Keep that gap.
    return {'status': 'GROUP_CREATED_PENDING_IDENTITY', 'name': data['name'],
        'slug': data['slug'], 'discovery': False, 'deleted': False,
        'requested_slug_sha256': hashlib.sha256(data['slug'].encode()).hexdigest(),
        'native_name_seen_after_reload': True, 'group_status': 'Active',
        'slug_identity_verified': False, 'discovery_verified': False, 'independent_readback': 'REQUIRED',
        'functional_verified': False, 'group_activation_attempted': False}
