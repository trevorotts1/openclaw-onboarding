#!/usr/bin/env python3
"""Captured native order-form appearance/options, through visible editor UI.

Captured controls: .c-order-form, Element name, Customize order form, the
settings.orderFormSteps group, named Products switches and Contact fields rows.
This module does not
infer native product IDs from display names or execute payment actions.
"""
from __future__ import annotations

import json
import hashlib
import re

if __package__:
    from .pages_checkout import CheckoutRefused, _native_id, _text
else:
    from pages_checkout import CheckoutRefused, _native_id, _text


PRODUCT_SWITCHES = {
    'show_images': 'Show images',
    'show_quantity': 'Show quantity',
    'show_product_description': 'Show product description',
    'show_price_description': 'Show price description',
    'multi_product_selection': 'Enable multi-product selection',
    'coupon_codes': 'Enable coupon codes',
}
CHECKOUT_SWITCHES = {
    'sticky_contact':'Sticky contact',
    'new_contact_every_purchase':'Create new contact on every purchase',
    'validate_disposable_email':'Validate disposable email',
    'postal_code_on_payment_form':'Postal code on payment form',
    'terms_and_conditions':'Terms & conditions',
    'terms_and_conditions_step_2':'Terms & conditions (step 2)',
}
CONTENT_FIELDS = {
    'step_1_headline':('Headlines','Step 1 headline'),
    'step_2_headline':('Headlines','Step 2 headline'),
    'shipping_section_heading':('Headlines','Shipping section heading'),
}
for _group, _labels in (
    ('Products & summary', ('Products heading','Subheadline','Product item column',
        'Product price column','Summary quantity column','Subtotal label','Total label',
        'Savings message','Gift card summary label','Sold out label','No products message')),
    ('Validation messages', ('Full name validation error','Email validation error',
        'Phone validation error','Required field error','Maximum quantity error','Not enough stock error')),
    ('Coupon', ('Coupon input placeholder','Apply coupon button','Remove coupon button',
        'Coupon applied message','Coupon link text')),
    ('Payment & CTA', ('Payment block title','Order button text','Order button subtext',
        'Footer text','Mixed currency error')),
    ('Two-step chrome', ('Continue button text','Back link text','Step 1 label',
        'Step 2 label','Step 1 footer text','Step 1 subtitle','Step 2 subtitle')),
):
    for _label in _labels:
        CONTENT_FIELDS[_label.lower().replace(' ', '_')] = (_group, _label)

THEME_INPUTS = {'appearance':('Appearance', ('Box','Line')), 'labels':('Labels', ('Above','Floating','Hidden'))}
MODES = ('One-step', 'Two-step', 'Split')
CONTACT_FIELDS = {
    'fullName':'Full Name', 'email':'Email', 'phone':'Phone', 'company':'Company',
    'address':'Address', 'country':'Country', 'state':'State', 'city':'City',
    'zip':'Zip Code',
}
MANDATORY_CONTACT_FIELDS = {'fullName', 'email'}



def _legal_plaintext(value, key):
    _text(value, 'Approved legal_copy.' + key)
    if re.search(r'<\s*[!/A-Za-z][^>]*>', value) or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value):
        raise CheckoutRefused('Legal copy must be authored plaintext, not HTML or control characters')
    return value.replace('\r\n','\n').replace('\r','\n')


def validate_checkout_ui(data):
    if not isinstance(data, dict):
        raise CheckoutRefused('Native checkout UI inputs must be an object')
    _native_id(data.get('element_id'), 'element_id')
    _text(data.get('expected_name'), 'expected_name')
    if data.get('section_id') is not None:
        _native_id(data['section_id'], 'section_id')
    if data.get('mode') is not None and data['mode'] not in MODES:
        raise CheckoutRefused('Native order-form mode must be One-step, Two-step or Split')
    products = data.get('products', {})
    if (not isinstance(products, dict) or set(products) - set(PRODUCT_SWITCHES)
            or any(type(value) is not bool for value in products.values())):
        raise CheckoutRefused('Native Products switches require explicit supported booleans')
    options = data.get('checkout_options', {})
    if (not isinstance(options, dict) or set(options) - set(CHECKOUT_SWITCHES)
            or any(type(value) is not bool for value in options.values())):
        raise CheckoutRefused('Native Checkout options require explicit supported booleans')
    legal = data.get('legal_copy', {})
    if not isinstance(legal, dict) or set(legal) - {'terms_text','terms_step2_text'}:
        raise CheckoutRefused('Legal copy requires explicit first-step/second-step plaintext keys')
    legal_keys = {'terms_and_conditions':'terms_text', 'terms_and_conditions_step_2':'terms_step2_text'}
    for option, key in legal_keys.items():
        if options.get(option) is True:
            _legal_plaintext(legal.get(key), key)
        elif key in legal:
            raise CheckoutRefused('Terms text requires the corresponding explicit true switch')
    content = data.get('content', {})
    if not isinstance(content, dict) or set(content) - set(CONTENT_FIELDS):
        raise CheckoutRefused('Use captured native Content field keys')
    for key, value in content.items():
        _text(value, 'Content ' + key)
    theme = data.get('theme_inputs', {})
    if not isinstance(theme, dict) or set(theme) - set(THEME_INPUTS):
        raise CheckoutRefused('Use captured Inputs Appearance/Labels settings')
    if any(value not in THEME_INPUTS[key][1] for key,value in theme.items()):
        raise CheckoutRefused('Unsupported native Inputs appearance or labels mode')
    fields = data.get('contact_fields', {})
    if not isinstance(fields, dict) or set(fields) - set(CONTACT_FIELDS):
        raise CheckoutRefused('Use captured native Contact fields keys')
    for key, states in fields.items():
        if (not isinstance(states, dict) or not states
                or set(states) - {'required','visible','expected_label'}
                or not set(states).intersection({'required','visible'})
                or any(type(states[k]) is not bool for k in ('required','visible') if k in states)):
            raise CheckoutRefused('Contact field required/visible states must be explicit booleans')
        if 'expected_label' in states:
            _text(states['expected_label'], 'expected_label')
        if key in MANDATORY_CONTACT_FIELDS and any(states.get(k) is False for k in ('required','visible')):
            raise CheckoutRefused('Native Full Name and Email remain mandatory and visible')
    if not data.get('mode') and not products and not fields and not options and not content and not theme:
        raise CheckoutRefused('No native checkout UI setting requested')
    if data.get('product_binding') or data.get('product_id') or data.get('price_id'):
        raise CheckoutRefused('Native product IDs require the verified component-binding operation; display names alone are not ID readback')
    if any(data.get(key) for key in ('publish', 'charge', 'execute_payment')):
        raise CheckoutRefused('Native checkout UI configures a draft only')
    return data


def open_native_order_settings(frame, data):
    """Select an exact native order form, verify its property name and open it."""
    _native_id(data.get('element_id'), 'element_id')
    _text(data.get('expected_name'), 'expected_name')
    wrapper = frame.locator('.c-order-form[id=' + json.dumps(data['element_id']) + ']')
    if wrapper.count() != 1:
        raise CheckoutRefused('Native order-form target is missing or duplicated')
    section = wrapper.evaluate("el => el.closest('.c-section')?.id || null")
    _native_id(section, 'containing section_id')
    if data.get('section_id') is not None and section != data['section_id']:
        raise CheckoutRefused('Native order form is in another section')
    wrapper.click()
    name = frame.get_by_role('textbox', name='Element name', exact=True)
    name.wait_for(state='visible', timeout=45000)
    if name.count() != 1 or name.input_value() != data['expected_name']:
        raise CheckoutRefused('Selected order-form property name is not the approved target')
    customize = frame.get_by_role('button', name='Customize order form', exact=True)
    if customize.count() != 1:
        raise CheckoutRefused('Native order-form property control changed')
    customize.click()
    dialog = frame.get_by_role('dialog').filter(has_text='Form settings')
    dialog.wait_for(state='visible', timeout=45000)
    if dialog.count() != 1:
        raise CheckoutRefused('Native Form settings dialog is ambiguous')
    return dialog


def _products_panel(dialog):
    button = dialog.get_by_role('button', name='Products', exact=True)
    if button.count() != 1:
        raise CheckoutRefused('Native Products settings control changed')
    button.click()



def _contact_panel(dialog):
    button = dialog.get_by_role('button', name=re.compile(r'^Contact fields \d+ shown$'))
    if button.count() != 1:
        raise CheckoutRefused('Native Contact fields navigation changed')
    button.click()


def _contact_field_controls(dialog, key, states):
    row = dialog.get_by_test_id('field-row-' + key)
    row.wait_for(state='visible', timeout=45000)
    if row.count() != 1:
        raise CheckoutRefused('Native Contact field row is missing or duplicated: ' + key)
    label = row.locator('p.of-field-label')
    expected_label = states.get('expected_label', CONTACT_FIELDS[key])
    if label.count() != 1 or label.get_attribute('title') != expected_label:
        raise CheckoutRefused('Native Contact field label changed: ' + key)
    controls = {}
    for state, title in (('required','Toggle required'),('visible','Toggle visibility')):
        if state not in states:
            continue
        control = row.get_by_role('button', name=title, exact=True)
        if key in MANDATORY_CONTACT_FIELDS:
            if control.count() != 0:
                raise CheckoutRefused('Native mandatory field controls changed: ' + key)
            continue
        if control.count() != 1 or control.get_attribute('aria-pressed') not in ('true','false'):
            raise CheckoutRefused('Native Contact field state unavailable: ' + key + '.' + state)
        controls[state] = control
    return controls


def _contact_fields(dialog, requested, *, write):
    _contact_panel(dialog)
    # Inventory every requested row/state before changing the first field.
    collected = {key:_contact_field_controls(dialog,key,states) for key,states in requested.items()}
    for key, controls in collected.items():
        for state, control in controls.items():
            expected = str(requested[key][state]).lower()
            if write and control.get_attribute('aria-pressed') != expected:
                control.click()
            if control.get_attribute('aria-pressed') != expected:
                raise CheckoutRefused('Native Contact field state does not match: ' + key + '.' + state)




def _terms_editor(dialog, label):
    editors = dialog.locator('.of-terms-content .tiptap.ProseMirror')
    if editors.count() == 0:
        try:
            editors.first.wait_for(state='visible', timeout=45000)
        except Exception:
            raise CheckoutRefused('Enabling native Terms did not expose its captured editor') from None
    if editors.count() not in (1, 2):
        raise CheckoutRefused('Native Terms editor count changed')
    matches = []
    for index in range(editors.count()):
        editor = editors.nth(index)
        row = editor.locator('xpath=../../..')
        switch = row.get_by_role('switch', name=label, exact=True)
        if switch.count() == 1:
            if not row.inner_text().lstrip().startswith(label) or switch.get_attribute('aria-checked') != 'true':
                raise CheckoutRefused('Native Terms row identity or enabled state changed')
            matches.append(editor)
    if len(matches) != 1:
        raise CheckoutRefused('Native Terms editor is not uniquely bound to its named switch')
    matches[0].wait_for(state='visible', timeout=45000)
    return matches[0]


def _checkout_options(dialog, requested, *, write, legal_copy=None):
    panel = dialog.get_by_role('button', name='Checkout options', exact=True)
    if panel.count() != 1:
        raise CheckoutRefused('Native Checkout options navigation changed')
    panel.click()
    collected = {}
    for key in requested:
        control = dialog.get_by_role('switch', name=CHECKOUT_SWITCHES[key], exact=True)
        control.wait_for(state='visible', timeout=45000)
        if control.count() != 1 or control.get_attribute('aria-checked') not in ('true','false'):
            raise CheckoutRefused('Native Checkout option control changed: ' + key)
        collected[key] = control
    for key, control in collected.items():
        expected = str(requested[key]).lower()
        if write and control.get_attribute('aria-checked') != expected:
            control.click()
        if control.get_attribute('aria-checked') != expected:
            raise CheckoutRefused('Native Checkout option does not match: ' + key)
    legal_copy = legal_copy or {}
    for key, legal_key in (('terms_and_conditions','terms_text'),
                           ('terms_and_conditions_step_2','terms_step2_text')):
        if requested.get(key) is not True:
            continue
        expected_text = _legal_plaintext(legal_copy.get(legal_key), legal_key)
        editor = _terms_editor(dialog, CHECKOUT_SWITCHES[key])
        if write:
            editor.fill(expected_text)
        if editor.inner_text().replace('\r\n','\n').replace('\r','\n') != expected_text:
            raise CheckoutRefused('Native Terms text does not match authored plaintext: ' + legal_key)
        if editor.locator('a').count() != 0:
            raise CheckoutRefused('Native Terms plaintext still contains an unapproved link')


def _content_fields(dialog, requested, *, write):
    panel = dialog.get_by_role('button', name='Content', exact=True)
    if panel.count() != 1:
        raise CheckoutRefused('Native Content navigation changed')
    panel.click()
    collected = {}
    for key in requested:
        group, label = CONTENT_FIELDS[key]
        control = dialog.get_by_role('textbox', name=label, exact=True)
        if control.count() == 0 or not control.is_visible():
            accordion = dialog.get_by_text(group, exact=True)
            if accordion.count() != 1:
                raise CheckoutRefused('Native Content group changed: ' + group)
            accordion.click()
        control.wait_for(state='visible', timeout=45000)
        if control.count() != 1:
            raise CheckoutRefused('Native Content field is missing or ambiguous: ' + key)
        collected[key] = control
    for key, control in collected.items():
        if write and control.input_value() != requested[key]:
            control.fill(requested[key])
        if control.input_value() != requested[key]:
            raise CheckoutRefused('Native Content value does not match: ' + key)



def _theme_input_controls(dialog, requested, *, write):
    nav = dialog.get_by_role('button', name='Theme & style', exact=True)
    if nav.count() != 1:
        raise CheckoutRefused('Native Theme & style navigation changed')
    nav.click()
    inputs = dialog.get_by_text('Inputs', exact=True)
    if inputs.count() != 1:
        raise CheckoutRefused('Native Inputs styling group changed')
    inputs.click()
    collected = {}
    for key, value in requested.items():
        group_name, _ = THEME_INPUTS[key]
        group = dialog.get_by_role('group', name=group_name, exact=True)
        if group.count() != 1:
            raise CheckoutRefused('Native Inputs property group changed: ' + key)
        control = group.get_by_role('button', name=value, exact=True)
        control.wait_for(state='visible', timeout=45000)
        if control.count() != 1 or control.get_attribute('aria-pressed') not in ('true','false'):
            raise CheckoutRefused('Native Inputs choice state unavailable: ' + key)
        collected[key] = control
    for key, control in collected.items():
        if write and control.get_attribute('aria-pressed') != 'true':
            control.click()
        if control.get_attribute('aria-pressed') != 'true':
            raise CheckoutRefused('Native Inputs choice does not match: ' + key)


def apply_checkout_ui(frame, data):
    """Apply explicit native mode/options and verify visible editor state.

    The enclosing host must save the page and reopen to call verify_checkout_ui.
    A returned editor state is not persisted or payment verification.
    """
    validate_checkout_ui(data)
    dialog = open_native_order_settings(frame, data)
    if data.get('mode'):
        steps = dialog.get_by_role('button', name=re.compile(r'^Steps(?:\s+(?:One-step|Two-step|Split))?$'))
        if steps.count() != 1:
            raise CheckoutRefused('Native Steps navigation changed')
        steps.click()
        group = dialog.get_by_role('group', name='settings.orderFormSteps', exact=True)
        group.wait_for(state='visible', timeout=45000)
        mode = group.get_by_role('button', name=data['mode'], exact=True)
        if mode.count() != 1:
            raise CheckoutRefused('Native Steps mode changed')
        mode.click()
    if data.get('products'):
        _products_panel(dialog)
        for key, value in data['products'].items():
            control = dialog.get_by_role('switch', name=PRODUCT_SWITCHES[key], exact=True)
            if control.count() != 1:
                raise CheckoutRefused('Native Products switch changed: ' + key)
            expected = str(value).lower()
            before = control.get_attribute('aria-checked')
            if before not in ('true', 'false'):
                raise CheckoutRefused('Native Products switch state is unavailable: ' + key)
            if before != expected:
                control.click()
            if control.get_attribute('aria-checked') != expected:
                raise CheckoutRefused('Native Products switch did not change: ' + key)
    if data.get('contact_fields'):
        _contact_fields(dialog, data['contact_fields'], write=True)
    if data.get('checkout_options'):
        _checkout_options(dialog, data['checkout_options'], write=True, legal_copy=data.get('legal_copy'))
    if data.get('content'):
        _content_fields(dialog, data['content'], write=True)
    if data.get('theme_inputs'):
        _theme_input_controls(dialog, data['theme_inputs'], write=True)
    return {'status':'NATIVE_CHECKOUT_UI_EDITED', 'element_id':data['element_id'],
        'mode':data.get('mode'), 'products':data.get('products', {}),
        'theme_inputs':data.get('theme_inputs', {}),
        'checkout_options':data.get('checkout_options', {}), 'content':data.get('content', {}),
        'contact_fields':data.get('contact_fields', {}),
        'independent_readback':'REQUIRED', 'payment_verified':False}


def verify_checkout_ui(frame, data):
    """Read the same settings after the enclosing host saved and reopened."""
    validate_checkout_ui(data)
    dialog = open_native_order_settings(frame, data)
    if data.get('mode'):
        mode = dialog.get_by_role('button', name='Steps ' + data['mode'], exact=True)
        if mode.count() != 1 or not mode.is_visible():
            raise CheckoutRefused('Saved native Steps mode does not match requested mode')
    if data.get('products'):
        _products_panel(dialog)
        for key, value in data['products'].items():
            control = dialog.get_by_role('switch', name=PRODUCT_SWITCHES[key], exact=True)
            if control.count() != 1 or control.get_attribute('aria-checked') != str(value).lower():
                raise CheckoutRefused('Saved native Products switch does not match: ' + key)
    if data.get('contact_fields'):
        _contact_fields(dialog, data['contact_fields'], write=False)
    if data.get('checkout_options'):
        _checkout_options(dialog, data['checkout_options'], write=False, legal_copy=data.get('legal_copy'))
    if data.get('content'):
        _content_fields(dialog, data['content'], write=False)
    if data.get('theme_inputs'):
        _theme_input_controls(dialog, data['theme_inputs'], write=False)
    legal_digests = {key:hashlib.sha256(_legal_plaintext(value,key).encode()).hexdigest()
                     for key,value in data.get('legal_copy', {}).items()}
    return {'status':'NATIVE_CHECKOUT_UI_READBACK_VERIFIED',
        'element_id':data['element_id'], 'mode':data.get('mode'),
        'legal_copy_saved':bool(legal_digests), 'legal_text_sha256':legal_digests, 'legal_acceptance':False,
        'products':data.get('products', {}),
        'theme_inputs':data.get('theme_inputs', {}),
        'checkout_options':data.get('checkout_options', {}), 'content':data.get('content', {}),
        'contact_fields':data.get('contact_fields', {}), 'payment_verified':False}


def close_native_order_settings(frame):
    dialog = frame.get_by_role('dialog').filter(has_text='Form settings')
    if dialog.count() != 1:
        raise CheckoutRefused('Native Form settings dialog changed before close')
    close = dialog.get_by_role('button', name='Alternative text for image not provided', exact=True)
    if close.count() != 1:
        raise CheckoutRefused('Native Form settings close control changed')
    close.click()
    dialog.wait_for(state='hidden', timeout=45000)


def configure_native_checkout_ui(page, data):
    """Apply -> save draft -> navigate exact editor -> verify persisted settings."""
    validate_checkout_ui(data)
    for key in ('location_id', 'location_name', 'start_url'):
        _text(data.get(key), key)
    if __package__:
        from . import skill6_playwright as core
    else:
        import skill6_playwright as core
    core.assert_tenant(page, data)
    if page.url != data['start_url']:
        raise CheckoutRefused('Open the exact inventoried native checkout editor first')
    editor_url = page.url
    frame = core.builder(page)
    apply_checkout_ui(frame, data)
    close_native_order_settings(frame)
    core.assert_tenant(page, data)
    core.save_page(frame)
    page.goto(editor_url, wait_until='domcontentloaded', timeout=45000)
    if page.url != editor_url:
        raise CheckoutRefused('Native checkout editor changed after reopening')
    core.assert_tenant(page, data)
    frame = core.builder(page)
    result = verify_checkout_ui(frame, data)
    close_native_order_settings(frame)
    return {**result, 'editor_url':editor_url,
            'scope':'Native order-form mode, product display, contact fields, checkout switches and Content text; no product binding or payment verification'}
