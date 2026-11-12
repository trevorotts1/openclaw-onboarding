"""Native same-step split variants; canonical API traffic guard is unchanged.

Selectors are bound to the November 10–11, 2026 authorized staging captures. Page
identities come from each card's actual Edit navigation, never thumbnails or
two disconnected pages. The shared runner journals intent before mutation.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, wait_until
else:
    from skill6_playwright import Stop, assert_tenant, click, wait_until


COMMON = {'location_id', 'location_name', 'start_url'}
PLAN = {'funnel_id', 'step_id', 'funnel_name', 'page_name', 'step_url',
        'control_page_id', 'expected_variant_id', 'allow_creation',
        'expected_control_traffic', 'control_traffic', 'expected_active', 'active',
        'traffic_change_authorized'}
ID = re.compile(r'[A-Za-z0-9_-]{1,256}')
MISSING_DOMAIN = 'Please add a domain in the settings to see your Funnel live!'


def _text(value):
    return (isinstance(value, str) and bool(value.strip()) and value == value.strip()
            and len(value) <= 1000 and not any(ord(c) < 32 for c in value))


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'payload'}
            or step.get('action', 'native_split_variant') != 'native_split_variant'):
        raise Stop('Unsupported native split metadata')
    data = step.get('payload')
    if not isinstance(data, dict) or set(data) != COMMON | PLAN:
        raise Stop('Split variants require exact control, variant, URL and allocation inventories')
    for key in COMMON | {'funnel_name', 'page_name'}:
        if not _text(data.get(key)):
            raise Stop('Split identity requires ' + key)
    for key in ('location_id', 'funnel_id', 'step_id', 'control_page_id'):
        if not isinstance(data[key], str) or not ID.fullmatch(data[key]):
            raise Stop('Split identity requires a literal native ' + key)
    variant = data['expected_variant_id']
    if variant is not None and (not isinstance(variant, str) or not ID.fullmatch(variant)
                                or variant == data['control_page_id']):
        raise Stop('Expected split variant must have a distinct native page ID')
    if any(type(data[k]) is not bool for k in ('allow_creation', 'expected_active', 'active',
                                             'traffic_change_authorized')):
        raise Stop('Split creation and activation choices must be explicit Boolean values')
    if any(type(data[k]) is not int or not 0 <= data[k] <= 100
           for k in ('expected_control_traffic', 'control_traffic')):
        raise Stop('Split traffic must be an explicit whole percentage from 0 through 100')
    if not data['expected_active'] and data['expected_control_traffic'] != 100:
        raise Stop('Inactive split baselines require the captured full control allocation')
    if data['expected_active'] and not 1 <= data['expected_control_traffic'] <= 99:
        raise Stop('Active split baselines require traffic for both same-step pages')
    if data['active'] and not 1 <= data['control_traffic'] <= 99:
        raise Stop('Active split allocation must assign traffic to both same-step pages')
    if variant is None and (not data['allow_creation'] or data['expected_active']
                            or data['expected_control_traffic'] != 100):
        raise Stop('A new variant needs explicit creation and an inactive 100-percent control baseline')
    if variant is not None and data['allow_creation']:
        raise Stop('An inventoried existing variant must not request another creation')
    if not data['active'] and (data['control_traffic'] != 100 or data['expected_active']):
        raise Stop('Inactive split variants retain all control traffic; stopping an active test needs separate capture')
    changes_traffic = (data['control_traffic'] != data['expected_control_traffic']
                       or data['active'] != data['expected_active'])
    if changes_traffic and not data['traffic_change_authorized']:
        raise Stop('Split traffic changes require the already-authorized exact plan acknowledgment')
    if not data['expected_active'] and data['active'] and data['control_traffic'] == 100:
        raise Stop('Captured activation uses changed allocation plus Apply; activation at unchanged 100 requires capture')
    parsed = urlsplit(data['start_url'])
    expected_path = ('/v2/location/' + data['location_id'] + '/funnels-websites/funnels/'
                     + data['funnel_id'] + '/steps/' + data['step_id'] + '/overview')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.port not in (None, 443) or parsed.path != expected_path):
        raise Stop('Split variants must bind the exact native funnel-step overview')
    public = urlsplit(data['step_url']) if isinstance(data['step_url'], str) else None
    if (not public or public.scheme != 'https' or not public.hostname
            or public.username is not None or public.password is not None
            or public.query or public.fragment or public.port not in (None, 443)):
        raise Stop('Split variants require the inventoried credential-free public step URL')
    return deepcopy(step)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step)['payload'], sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _one(node, reason):
    if node.count() != 1 or not node.is_visible():
        raise Stop(reason)
    return node


def _overview(page, data):
    if page.url != data['start_url']:
        raise Stop('Split editor changed its exact overview identity')
    assert_tenant(page, data)
    panel = page.locator('#steps-tab[role="tabpanel"]')
    wait_until(lambda: panel.count() == 1 and panel.is_visible()
               and panel.locator('#funnel-page-card').count() == 2,
               'Split overview card inventory did not load')
    for key in ('funnel_name', 'page_name'):
        matches = page.get_by_text(data[key], exact=True)
        if not any(matches.nth(i).is_visible() for i in range(matches.count())):
            raise Stop('Native split identity changed: ' + key)
    notice = panel.get_by_text(MISSING_DOMAIN, exact=True)
    if any(notice.nth(i).is_visible() for i in range(notice.count())):
        raise Stop('Split domain prerequisite is missing; no variant mutation attempted')
    _one(panel.get_by_text(data['step_url'], exact=True), 'Native split step URL differs from inventory')
    cards = panel.locator('#funnel-page-card')
    if cards.count() != 2:
        raise Stop('Split native card inventory changed')
    control = _one(cards.filter(has=panel.get_by_text('CONTROL', exact=True)), 'Split control card changed')
    variant = _one(cards.filter(has=panel.get_by_text('VARIATION', exact=True)), 'Split variation card changed')
    if control.get_by_text('VARIATION', exact=True).count() or variant.get_by_text('CONTROL', exact=True).count():
        raise Stop('Native split cards do not distinguish control and variation')
    _one(control.get_by_role('button', name='Edit', exact=True), 'Native control Edit is missing')
    return panel, control, variant


def _page_id(page, data, card):
    """Read the platform page ID through the captured same-tab Edit route."""
    origin = urlsplit(data['start_url'])
    click(_one(card.get_by_role('button', name='Edit', exact=True), 'Native split Edit is ambiguous'))
    route = re.compile(r'/(?:v2/)?location/' + re.escape(data['location_id'])
                       + r'/page-builder/([A-Za-z0-9_-]+)')
    def reached():
        current = urlsplit(page.url)
        return ((current.scheme, current.netloc) == (origin.scheme, origin.netloc)
                and not current.query and not current.fragment and route.fullmatch(current.path))
    wait_until(reached, 'Native split Edit did not expose a same-origin same-location page ID')
    identity = route.fullmatch(urlsplit(page.url).path).group(1)
    page.go_back(wait_until='domcontentloaded', timeout=45000)
    wait_until(lambda: page.url == data['start_url'], 'Native split Edit did not return to its exact overview')
    _overview(page, data)
    return identity


def _variant_present(variant):
    edit = variant.get_by_role('button', name='Edit', exact=True)
    create = variant.get_by_role('button', name='Create variation', exact=True)
    if edit.count() == 1 and edit.is_visible() and create.count() == 0:
        return True
    if edit.count() == 0 and create.count() == 1 and create.is_visible() and create.is_enabled():
        return False
    raise Stop('Native variant presence is not authoritative; reconcile before creating')


def _slider(panel):
    value = _one(panel.get_by_role('slider', name='Slider Handle', exact=True),
                 'Native split traffic slider is missing or ambiguous')
    if (value.get_attribute('aria-valuemin') != '0' or value.get_attribute('aria-valuemax') != '100'
            or value.get_attribute('aria-disabled') != 'false'
            or value.get_attribute('aria-orientation') != 'horizontal'):
        raise Stop('Native split traffic slider limits or availability changed')
    raw = value.get_attribute('aria-valuenow')
    if not isinstance(raw, str) or not re.fullmatch(r'100|[0-9]|[1-9][0-9]', raw):
        raise Stop('Native split traffic percentage is not exposed as an exact integer')
    return value, int(raw)


def _ui_state(page, data):
    panel, control, variant = _overview(page, data)
    present = _variant_present(variant)
    if not present:
        if panel.get_by_role('slider').count():
            raise Stop('A missing split variant unexpectedly has allocation controls')
        return {'variant_present': False, 'control_traffic': 100, 'active': False}
    _, traffic = _slider(panel)
    # A staged Apply is not saved state and must never be blessed as readback.
    if panel.get_by_role('button', name='Apply', exact=True).count():
        raise Stop('Native split allocation is still staged; reconcile before another operation')
    inactive = panel.get_by_role('button', name='Start split test', exact=True)
    if inactive.count() == 1 and inactive.is_visible():
        _one(panel.get_by_text('Almost there!', exact=True), 'Native inactive split marker changed')
        if traffic != 100:
            raise Stop('Native inactive split does not preserve full control traffic')
        return {'variant_present': True, 'control_traffic': traffic, 'active': False}
    running = panel.get_by_text('Split test is running from', exact=True)
    if running.count() == 1 and running.is_visible() and inactive.count() == 0:
        _one(panel.locator('.split-stats-table'), 'Native running split statistics are unavailable')
        if not 1 <= traffic <= 99:
            raise Stop('Native active split does not assign traffic to both pages')
        return {'variant_present': True, 'control_traffic': traffic, 'active': True}
    raise Stop('Native split has neither a captured inactive nor running state')


def read_inventory(page, step):
    data = validate(step)['payload']
    before = _ui_state(page, data)
    _, control, _ = _overview(page, data)
    control_id = _page_id(page, data, control)
    if _ui_state(page, data) != before:
        raise Stop('Native split allocation changed during page identity readback')
    variant_id = None
    if before['variant_present']:
        _, _, variant = _overview(page, data)
        variant_id = _page_id(page, data, variant)
        if variant_id == control_id:
            raise Stop('Native split control and variant resolve to the same page')
        if _ui_state(page, data) != before:
            raise Stop('Native split inventory changed during variant identity readback')
    return {**before, 'control_page_id': control_id, 'variant_page_id': variant_id}


def _create(page, data):
    panel, _, variant = _overview(page, data)
    if _variant_present(variant):
        raise Stop('A variant already exists; creation was not repeated')
    click(_one(variant.get_by_role('button', name='Create variation', exact=True),
               'Native Create variation is missing'))
    for name in ('Duplicate Control Page', 'Use existing', 'Create from blank', 'Cancel'):
        choice = _one(variant.get_by_role('button', name=name, exact=True),
                      'Native split creation choices changed')
        if not choice.is_enabled():
            raise Stop('Native split creation choice is unavailable')
    click(variant.get_by_role('button', name='Duplicate Control Page', exact=True))
    wait_until(lambda: _overview(page, data)[2].get_by_role('button', name='Edit', exact=True).count() == 1,
               'Native variant duplication did not finish; do not repeat Create')


_START_CONFIRM = 'Please confirm that you would like to apply these changes and start the split test.'
_RESTART_CONFIRM = ('Changing the configuration will invalidate previous results. '
                    'Please confirm that you would like to apply these changes and start the test over.')


def _apply(page, panel):
    """Accept the one captured JS confirm caused by this exact Apply control.

    The extension exposed the native dialog type, but not its message. The
    normal Python Playwright dialog API is used here; no message is invented.
    An unexpected dialog is dismissed, never approved as a split allocation.
    """
    apply = _one(panel.get_by_role('button', name='Apply', exact=True),
                 'Native split Apply is unavailable or ambiguous')
    if not apply.is_enabled():
        raise Stop('Native split Apply is disabled')
    dialogs = []
    def confirm(dialog):
        accepted = not dialogs and dialog.type == 'confirm'
        dialogs.append(accepted)
        if accepted:dialog.accept()
        else:dialog.dismiss()
    page.on('dialog', confirm)
    try:
        click(apply)
        wait_until(lambda: bool(dialogs), 'Native split Apply did not expose its captured confirmation')
        if dialogs != [True]:
            raise Stop('Native split Apply exposed an unexpected dialog; allocation is uncertain')
        wait_until(lambda: panel.get_by_role('button', name='Apply', exact=True).count() == 0,
                   'Native split Apply remains staged; reconcile without another write')
    finally:
        page.remove_listener('dialog', confirm)


def _allocate(page, data, baseline):
    """Stage authored whole percentages through the captured keyboard slider."""
    if not data['traffic_change_authorized'] or not data['active']:
        raise Stop('Native split allocation requires the explicit authorized active plan')
    if _ui_state(page, data) != {key: baseline[key] for key in ('variant_present','control_traffic','active')}:
        raise Stop('Native split changed immediately before allocation staging')
    panel, _, _ = _overview(page, data)
    if not baseline['active']:
        click(_one(panel.get_by_role('button', name='Start split test', exact=True),
                   'Native split Start control changed'))
        wait_until(lambda: panel.get_by_role('button', name='Apply', exact=True).count() == 1,
                   'Native split activation did not stage its captured Apply control')
    slider, traffic = _slider(panel)
    wanted = data['control_traffic']
    while traffic != wanted:
        # The captured ArrowLeft decrements one point; the opposite key uses
        # the same standard native range control and is verified after each key.
        _overview(page, data)
        slider, observed = _slider(panel)
        if observed != traffic:
            raise Stop('Native split traffic changed during allocation staging')
        next_value = traffic + (1 if wanted > traffic else -1)
        slider.press('ArrowRight' if next_value > traffic else 'ArrowLeft', timeout=45000)
        wait_until(lambda: _slider(panel)[1] == next_value,
                   'Native split keyboard did not stage exactly one traffic percentage')
        traffic = next_value
    prompt = _RESTART_CONFIRM if baseline['active'] else _START_CONFIRM
    _one(panel.get_by_text(prompt, exact=True), 'Native split allocation confirmation copy changed')
    _one(panel.get_by_role('button', name='Cancel', exact=True), 'Native split allocation Cancel changed')
    _overview(page, data)
    if _slider(panel)[1] != wanted:
        raise Stop('Native split allocation differs immediately before Apply')
    _apply(page, panel)
    wait_until(lambda: panel.get_by_text('Split test is running from', exact=True).count() == 1,
               'Native split did not expose its saved running state')


def _receipt(step, observed, *, created):
    data = validate(step)['payload']
    changed = (created or data['control_traffic'] != data['expected_control_traffic']
               or data['active'] != data['expected_active'])
    return {'status': 'SPLIT_VARIANT_SAVED_AND_REOPENED' if changed else 'SPLIT_VARIANT_REUSED_AND_REOPENED',
            'editor_url': data['start_url'], 'configuration_sha256': configuration_hash(step),
            'control_page_id': observed['control_page_id'], 'variant_page_id': observed['variant_page_id'],
            'control_traffic': observed['control_traffic'], 'variant_traffic': 100 - observed['control_traffic'],
            'active': observed['active'], 'created': created, 'independent_readback': 'VERIFIED',
            'functional_verified': False}


def validate_receipt(value, step):
    data = validate(step)['payload']
    fields = {'status', 'editor_url', 'configuration_sha256', 'control_page_id', 'variant_page_id',
              'control_traffic', 'variant_traffic', 'active', 'created', 'independent_readback',
              'functional_verified'}
    if not isinstance(value, dict) or set(value) != fields:
        raise Stop('Split completion must contain its exact bound native receipt')
    if (value['editor_url'] != data['start_url'] or value['configuration_sha256'] != configuration_hash(step)
            or value['control_page_id'] != data['control_page_id']
            or not isinstance(value['variant_page_id'], str) or not ID.fullmatch(value['variant_page_id'])
            or value['variant_page_id'] == value['control_page_id']
            or data['expected_variant_id'] is not None and value['variant_page_id'] != data['expected_variant_id']
            or type(value['created']) is not bool or value['created'] != (data['expected_variant_id'] is None)
            or type(value['control_traffic']) is not int or value['control_traffic'] != data['control_traffic']
            or type(value['variant_traffic']) is not int or value['variant_traffic'] != 100 - data['control_traffic']
            or type(value['active']) is not bool or value['active'] != data['active']
            or value['independent_readback'] != 'VERIFIED' or value['functional_verified'] is not False):
        raise Stop('Split completion differs from the requested native identities or traffic')
    expected = _receipt(step, {'control_page_id': value['control_page_id'],
        'variant_page_id': value['variant_page_id'], 'control_traffic': value['control_traffic'],
        'active': value['active']}, created=value['created'])
    if value != expected:
        raise Stop('Split completion status is inconsistent with its exact plan')
    return deepcopy(value)


def verify_completed(page, step, receipt):
    expected = validate_receipt(receipt, step)
    page.goto(step['payload']['start_url'], wait_until='domcontentloaded', timeout=45000)
    observed = read_inventory(page, step)
    if (observed['control_page_id'] != expected['control_page_id']
            or observed['variant_page_id'] != expected['variant_page_id']
            or observed['control_traffic'] != expected['control_traffic']
            or observed['active'] != expected['active']):
        raise Stop('Saved native split changed; reconcile without creating another variant')
    return expected


def configure(page, step):
    """Create/reuse one captured native variant, then independently reload.

    Native page identity and the complete baseline are read before creation or
    allocation changes. Authored traffic must survive an independent reload.
    """
    data = validate(step)['payload']
    page.goto(data['start_url'], wait_until='domcontentloaded', timeout=45000)
    before = read_inventory(page, step)
    if (before['control_page_id'] != data['control_page_id']
            or before['variant_page_id'] != data['expected_variant_id']
            or before['control_traffic'] != data['expected_control_traffic']
            or before['active'] != data['expected_active']):
        raise Stop('Native split baseline differs from complete expected inventory; no creation attempted')
    created = data['expected_variant_id'] is None
    if created:
        _create(page, data)
    after = read_inventory(page, step)
    if (after['control_page_id'] != before['control_page_id'] or after['variant_page_id'] is None
            or not created and after['variant_page_id'] != before['variant_page_id']
            or after['active'] != before['active'] or after['control_traffic'] != before['control_traffic']):
        raise Stop('Native variant creation or identity reading changed the original allocation')
    if after['active'] != data['active'] or after['control_traffic'] != data['control_traffic']:
        allocated_variant = after['variant_page_id']
        _allocate(page, data, after)
        after = read_inventory(page, step)
        if (after['control_page_id'] != before['control_page_id']
                or after['variant_page_id'] != allocated_variant
                or after['active'] != data['active']
                or after['control_traffic'] != data['control_traffic']):
            raise Stop('Native split allocation differs after Apply; do not repeat the write')
    page.reload(wait_until='domcontentloaded', timeout=45000)
    reopened = read_inventory(page, step)
    if reopened != after:
        raise Stop('Native split relation did not survive independent reopen')
    return validate_receipt(_receipt(step, reopened, created=created), step)
