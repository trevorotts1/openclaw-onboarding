#!/usr/bin/env python3
"""Captured native order-form appearance/options, through visible editor UI.

Captured controls: .c-order-form, Element name, Customize order form, the
settings.orderFormSteps group, named Products switches and Contact fields rows.
This module does not
infer native product IDs from display names or execute payment actions.
"""
from __future__ import annotations

import json
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
MODES = ('One-step', 'Two-step', 'Split')
CONTACT_FIELDS = {
    'fullName':'Full Name', 'email':'Email', 'phone':'Phone', 'company':'Company',
    'address':'Address', 'country':'Country', 'state':'State', 'city':'City',
    'zip':'Zip Code',
}
MANDATORY_CONTACT_FIELDS = {'fullName', 'email'}


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
    if not data.get('mode') and not products and not fields:
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
    return {'status':'NATIVE_CHECKOUT_UI_EDITED', 'element_id':data['element_id'],
        'mode':data.get('mode'), 'products':data.get('products', {}),
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
    return {'status':'NATIVE_CHECKOUT_UI_READBACK_VERIFIED',
        'element_id':data['element_id'], 'mode':data.get('mode'),
        'products':data.get('products', {}),
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
            'scope':'Native order-form mode, product-display options and contact field states; no product binding or payment verification'}
