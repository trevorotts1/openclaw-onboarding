#!/usr/bin/env python3
"""Native checkout configuration through the existing captured editor adapter.

This is the Playwright transport for Skill 6's canonical order-component
executor. It never launches a browser, mints credentials, purchases, publishes,
or creates an approximation of an upsell. Inputs are validated completely
before the first browser write. Missing live captures remain a named blocker.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import order_components as native


class CheckoutRefused(native.SpecError):
    pass


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CheckoutRefused(label + ' is required')
    return value


def _relative_route(value):
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        raise CheckoutRefused('Captured routes must be same-origin absolute paths')
    if '\\' in value or any(p == '..' for p in value.split('/')) or urlsplit(value).netloc:
        raise CheckoutRefused('Captured route is not a same-origin path')


def load_checkout_capture(path, *, location_id, page_id):
    capture = native.load_managed_adapter_capture(str(path))
    if capture.get('location_id') != location_id or capture.get('page_id') != page_id:
        raise CheckoutRefused('Native element capture belongs to a different location/page')
    _text(capture.get('capture_source'), 'Dated live capture source')
    for key in native.ADAPTER_ROUTE_KEYS:
        _relative_route(capture[key]['path'])
    # Headers are existing non-secret protocol markers, not a second auth store.
    if any(k.lower() in ('authorization', 'cookie', 'token-id') for k in capture.get('headers', {})):
        raise CheckoutRefused('Captured headers must not contain credentials')
    return capture


def validate_checkout_inputs(data):
    """Compile the complete mutation plan before any browser effect."""
    if not isinstance(data, dict):
        raise CheckoutRefused('Checkout inputs must be an object')
    native.assert_no_card_data(data)
    if any(data.get(key) for key in ('publish', 'charge', 'execute_payment')):
        raise CheckoutRefused('This operation configures drafts only; publishing and charging are not supported')
    for key in ('location_id', 'location_name', 'start_url', 'page_id', 'step_id',
                'component_id', 'tab_id', 'frame_name', 'adapter_capture'):
        _text(data.get(key), key)
    if data['frame_name'] != 'funnel-builder':
        raise CheckoutRefused('Use the captured native funnel-builder frame')
    parsed = urlsplit(data['start_url'])
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query
            or parsed.fragment or not re.search(r'/(?:v2/)?location/' + re.escape(data['location_id']) + r'(?:/|$)', parsed.path)):
        raise CheckoutRefused('Editor URL must belong to the exact location')
    if data['page_id'] not in parsed.path.split('/'):
        raise CheckoutRefused('Editor URL must include the exact native page ID')
    contract = data.get('checkout_contract', {})
    if (not isinstance(contract, dict) or contract.get('status') != 'PASS'
            or contract.get('location_id') != data['location_id'] or not contract.get('source')):
        raise CheckoutRefused('Location-bound Skill 44/79 checkout contract required')
    family_data = data.get('family')
    if not isinstance(family_data, dict):
        raise CheckoutRefused('Native component family capability inventory required')
    try:
        family = native.ComponentFamily(**family_data)
    except TypeError:
        raise CheckoutRefused('Invalid native component family') from None
    main = native.validate_price_ref(data['main_price']) if 'main_price' in data else None
    if main and (contract.get('product_id') != main.native_product_id
                 or contract.get('price_id') != main.native_price_id):
        raise CheckoutRefused('Main product/price does not match the checkout contract')
    bumps = []
    for raw in data.get('bumps', []):
        if not isinstance(raw, dict) or raw.get('selected', False) is not False:
            raise CheckoutRefused('A new bump must be explicitly unselected')
        price = native.validate_price_ref(raw['price'])
        receipts = contract.get('verified_bump_prices', [])
        if price.as_fields() not in receipts:
            raise CheckoutRefused('Bump price requires exact verified terms in the checkout contract')
        bumps.append(native.BumpAttach(
            offer_id=raw['offer_id'], headline=raw['headline'],
            benefit_explanation=raw['benefit_explanation'], price=price,
            disclosure_text=raw.get('disclosure_text')))
    if len(bumps) > family.max_bumps:
        raise CheckoutRefused('Requested bump count exceeds native family limit')
    if len({b.offer_id for b in bumps}) != len(bumps) or len({b.price.native_price_id for b in bumps}) != len(bumps):
        raise CheckoutRefused('Duplicate bump identity/price')
    if any(b.price.is_recurring for b in bumps) and not family.allows_recurring_bumps:
        raise CheckoutRefused('Native family does not support recurring bumps')
    if main and any(b.price.currency != main.currency for b in bumps):
        raise CheckoutRefused('Bump and main currencies differ')
    fields = data.get('field_states', {})
    if not isinstance(fields, dict):
        raise CheckoutRefused('field_states must be an object')
    for key, states in fields.items():
        _text(key, 'field key')
        if (not isinstance(states, dict) or not states or set(states) - {'required', 'hidden'}
                or any(type(value) is not bool for value in states.values())):
            raise CheckoutRefused('Field states require explicit required/hidden booleans')
    action = data.get('purchase_action')
    if action is not None:
        if not isinstance(action, dict) or set(action) != {'kind', 'target_step_id'} or action['kind'] not in ('accept', 'decline'):
            raise CheckoutRefused('Use an explicit native accept/decline action and target')
        _text(action['target_step_id'], 'target_step_id')
        if (contract.get('prior_payment_verified') is not True
                or contract.get('upsell_step_id') != data['step_id']
                or not contract.get('source_step_id')):
            raise CheckoutRefused('Native upsell needs a verified prior-payment and source/upsell-step contract')
        if main is None:
            raise CheckoutRefused('Native upsell must bind its verified product/price')
    if not (main or bumps or fields or action):
        raise CheckoutRefused('No native checkout changes requested')
    return {'family': family, 'main': main, 'bumps': bumps, 'fields': fields, 'action': action}


class PlaywrightOrderDriver(native.BrowserManagerDriver):
    """Concrete synchronous Playwright transport, bound to one Page and Frame."""
    def __init__(self, page, *, scope, frame_name, bridge, expected_url):
        self.page, self.scope = page, scope
        self.expected_url, self.frame_name = expected_url, frame_name
        matches = [frame for frame in page.frames if frame.name == frame_name]
        if len(matches) != 1:
            raise CheckoutRefused('Exactly one captured builder frame is required')
        self.frame = matches[0]
        self.checkout_kind = bridge.capture['element_kinds']['checkout']
        super().__init__(runner=self._evaluate, bridge=bridge)

    def _evaluate(self, argv):
        if self.page.url != self.expected_url or self.frame not in self.page.frames:
            raise CheckoutRefused('Checkout page/frame changed; no mutation attempted')
        script = argv[2]
        if script.startswith('window.__ocOrderComponents='):
            return self.frame.evaluate('() => {' + script + ';return "installed";}')
        return self.frame.evaluate(script)

    def _call(self, scope, op, **args):
        if scope != self.scope:
            raise CheckoutRefused('Native checkout operation used a different tab/frame scope')
        result = super()._call(scope, op, **args)
        if op == 'list_components':
            return [{**row, 'kind': 'checkout' if row.get('kind') == self.checkout_kind else row.get('kind')}
                    for row in result] if isinstance(result, list) else result
        return result


def configure_native_checkout(page, data, *, input_dir='.'):
    """Set native bindings, read every result back, never execute a payment.

    Existing host/run_on_page owns intent-before-write state and crash recovery.
    After a partial failure the host must reconcile native component state before
    calling this function again. The return value is never a payment/QC PASS.
    """
    prepared = validate_checkout_inputs(data)
    if __package__:
        from .skill6_playwright import assert_tenant
    else:
        from skill6_playwright import assert_tenant
    assert_tenant(page, data)
    if page.url != data['start_url']:
        raise CheckoutRefused('Open the exact inventoried editor page first')
    capture_path = (Path(input_dir) / data['adapter_capture']).resolve()
    capture = load_checkout_capture(capture_path, location_id=data['location_id'], page_id=data['page_id'])
    scope = native.FrameScope(data['tab_id'], data['frame_name'])
    bridge = native.ManagedEditorBridge(capture, location_id=data['location_id'],
        page_id=data['page_id'], funnel_id=data.get('funnel_id', ''))
    driver = PlaywrightOrderDriver(page, scope=scope, frame_name=data['frame_name'],
        bridge=bridge, expected_url=data['start_url'])
    executor = native.OrderComponentExecutor(driver, scope, prepared['family'])
    component = data['component_id']
    executor.resolve_component(component)
    records = []
    if prepared['main']:
        records.append(executor.bind_main_price(component, prepared['main']))
    for bump in prepared['bumps']:
        # Reconcile by exact native price and offer identity on interrupted runs.
        state = executor.read_component(component) or {}
        existing = [b for b in state.get('bumps', []) if b.get('offer_id') == bump.offer_id]
        if existing:
            if len(existing) != 1 or existing[0] != bump.as_fields():
                raise CheckoutRefused('Existing bump differs from requested binding; reconcile before replay')
        else:
            records.append(executor.attach_bump(component, bump))
    for key, states in prepared['fields'].items():
        records.append(executor.set_field_state(component, key, **states))
    if prepared['action']:
        records.append(executor.set_action(component, prepared['action']['kind'], prepared['action']['target_step_id']))
    assert_tenant(page, data)
    return {'status': 'NATIVE_CONFIGURATION_READBACK_VERIFIED', 'payment_verified': False,
        'verification_required': 'Independent native checkout and test-payment journey',
        'component_id': component, 'page_id': data['page_id'],
        'operations': [asdict(record) for record in records]}


SPLIT_MISSING_DOMAIN_NOTICE = 'Please add a domain in the settings to see your Funnel live!'


def check_split_prerequisites(page, data):
    """Read the exact native step overview before any variation click.

    The missing-domain text and Create variation control were observed in the
    authorized fixture on 2026-11-08. The notice is a concrete missing
    prerequisite; this function does not claim it caused any browser alert.
    Absence of that notice is not proof the native split relation is captured.
    """
    if not isinstance(data, dict):
        raise CheckoutRefused('Split prerequisite inputs must be an object')
    for key in ('location_id', 'location_name', 'start_url', 'funnel_id',
                'step_id', 'funnel_name', 'page_name'):
        _text(data.get(key), key)
    expected = urlsplit(data['start_url'])
    path = ('/v2/location/' + data['location_id'] + '/funnels-websites/funnels/'
            + data['funnel_id'] + '/steps/' + data['step_id'] + '/overview')
    if (expected.scheme != 'https' or expected.username or expected.password
            or expected.query or expected.fragment or expected.path != path):
        raise CheckoutRefused('Split preflight requires the exact location/funnel/step overview URL')
    if page.url != data['start_url']:
        raise CheckoutRefused('Open the exact native control-step overview before split preflight')
    if __package__:
        from .skill6_playwright import assert_tenant
    else:
        from skill6_playwright import assert_tenant
    assert_tenant(page, data)
    for key in ('funnel_name', 'page_name'):
        matches = page.get_by_text(data[key], exact=True)
        if not matches.count() or not any(matches.nth(i).is_visible() for i in range(matches.count())):
            raise CheckoutRefused('Native split overview identity not visible: ' + key)
    base = {'operation': 'funnels.split_variant', 'location_id': data['location_id'],
            'funnel_id': data['funnel_id'], 'step_id': data['step_id'],
            'mutation_attempted': False, 'variant_created': False}
    notice = page.get_by_text(SPLIT_MISSING_DOMAIN_NOTICE, exact=True)
    if any(notice.nth(i).is_visible() for i in range(notice.count())):
        return {**base, 'status': 'DEPENDENCY_DOMAIN_MISSING',
                'observed_notice': SPLIT_MISSING_DOMAIN_NOTICE,
                'required_dependency': 'An explicitly approved domain binding on this funnel',
                'next_action': 'Resolve the domain dependency through the existing domain workflow, then rerun preflight.'}
    create = page.get_by_role('button', name='Create variation', exact=True)
    if create.count() != 1 or not create.is_visible() or not create.is_enabled():
        return {**base, 'status': 'DEPENDENCY_SPLIT_UI_CHANGED',
                'next_action': 'Reconcile the existing variant or capture the current native split controls.'}
    # The canonical native split module owns the relation/traffic capture gate.
    # Do not infer native relations merely because a Create button is present.
    import ghl_split_variant
    state = ghl_split_variant.capability_state()
    return {**base, 'status': 'DEPENDENCY_SPLIT_CAPTURE_REQUIRED',
            'domain_missing_notice_observed': False,
            'native_capability_state': state['state'],
            'next_action': state['next_action']}


_NATIVE_ELEMENT_ID = re.compile(r'^[A-Za-z0-9_-]+$')


def _native_id(value, label):
    if not isinstance(value, str) or not _NATIVE_ELEMENT_ID.fullmatch(value):
        raise CheckoutRefused(label + ' must be an exact native DOM identifier')
    return value


def _select_code_target(frame, element_id, *, section_id=None):
    """Select one inventoried native code element and read its property name.

    Captured 2026-11-08: clicking the .c-custom-code wrapper opens General/Styles
    and the Element name textbox. A breadcrumb button with the custom element
    name appears only after selection, so it is not used for initial targeting.
    No editor text is changed by this operation.
    """
    _native_id(element_id, 'element_id')
    if section_id is not None:
        _native_id(section_id, 'section_id')
    target = frame.locator('.c-custom-code[id=' + json.dumps(element_id) + ']')
    if target.count() != 1:
        raise CheckoutRefused('Native code element is missing or duplicated; no first-match target')
    containing = target.evaluate("el => {const section=el.closest('.c-section');return section ? section.id : null;}")
    if not containing:
        raise CheckoutRefused('Native code element has no containing native section')
    _native_id(containing, 'containing section_id')
    if section_id is not None and containing != section_id:
        raise CheckoutRefused('Native code element belongs to a different section')
    target.click()
    name = frame.get_by_role('textbox', name='Element name', exact=True)
    try:
        name.wait_for(state='visible', timeout=45000)
    except Exception:
        raise CheckoutRefused('Selecting native code did not expose the captured property panel') from None
    if name.count() != 1:
        raise CheckoutRefused('Selecting native code did not expose one Element name control')
    editor = frame.get_by_role('button', name='Open Code Editor', exact=True)
    if editor.count() != 1 or not editor.is_visible():
        raise CheckoutRefused('Selected native element is not the captured code-property panel')
    return {'locator': target, 'element_id': element_id,
            'section_id': containing, 'element_name': name.input_value()}


def resolve_code_target(frame, element_id, expected_name, section_id=None):
    """Resolve/select an exact code element, then verify its saved property name.

    A matching label elsewhere, an arbitrary code block or a breadcrumb from a
    previous selection cannot authorize replacing code. Only selection occurs;
    name mismatch stops before opening or writing the code editor.
    """
    _text(expected_name, 'expected_name')
    result = _select_code_target(frame, element_id, section_id=section_id)
    if result['element_name'] != expected_name:
        raise CheckoutRefused('Selected code Element name does not match the approved target')
    return result


def inventory_code_targets(frame, *, include_names=True):
    """Read native element/section IDs; optionally select each to read its name.

    Selection changes the visible property panel only. No code editor is opened,
    no input is filled, and nothing is saved. The returned element_name comes
    from the visible captured property textbox, never an inferred canvas label.
    """
    nodes = frame.locator('.c-custom-code')
    observed = nodes.evaluate_all("""els => els.map(el => ({
        element_id:el.id,
        section_id:el.closest('.c-section')?.id || null
    }))""")
    if not isinstance(observed, list):
        raise CheckoutRefused('Native code inventory returned an invalid result')
    seen = set()
    for item in observed:
        if not isinstance(item, dict):
            raise CheckoutRefused('Native code inventory contains an invalid row')
        _native_id(item.get('element_id'), 'element_id')
        _native_id(item.get('section_id'), 'section_id')
        if item['element_id'] in seen:
            raise CheckoutRefused('Native code inventory has duplicate element IDs')
        seen.add(item['element_id'])
    results = []
    for item in observed:
        if include_names:
            selected = _select_code_target(frame, item['element_id'], section_id=item['section_id'])
            results.append({key:selected[key] for key in ('element_id','section_id','element_name')})
        else:
            results.append({**item, 'element_name': None})
    return results
