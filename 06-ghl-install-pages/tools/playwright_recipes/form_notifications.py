"""Native form notification configuration captured 2026-11-08.

Schema: email_notification and/or auto_responder objects. Both require enabled
as an explicit boolean. Enabled configurations require subject, reply_to,
sender_name and attach_pdf. Email notifications additionally require the full
recipients and expected_recipients lists; replacement is refused on mismatch.
Disabled configurations accept enabled only. No body/template/scheduling options
are silently accepted. Saving configuration never proves email delivery.
"""
from copy import deepcopy
import hashlib
import json
import re

if __package__:
    from .skill6_playwright import Stop, assert_tenant, click, fill, form_builder, visible, wait_until
    from .assessments import reopen_editor
else:
    from skill6_playwright import Stop, assert_tenant, click, fill, form_builder, visible, wait_until
    from assessments import reopen_editor


CARDS = {
    'email_notification': ('Email notification', '{form_title} - {name}'),
    'auto_responder': ('Auto responder', 'We have received your response for {form.title} on {submit.date}'),
}
METADATA = {'id','action','_context'}
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+")


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value:
        raise Stop('Notification ' + label + ' must be authored single-line text')
    return value


def _email(value):
    if not isinstance(value, str) or len(value) > 254 or not EMAIL.fullmatch(value):
        raise Stop('Notification email must be a plain valid email address')
    return value


def _addresses(values, *, allow_empty):
    if not isinstance(values, list) or (not values and not allow_empty):
        raise Stop('Notification recipient inventory must be an explicit email list')
    for value in values:
        _email(value)
    if len(set(values)) != len(values):
        raise Stop('Duplicate notification recipients are not supported')
    return list(values)


def validate_notifications(step):
    if not isinstance(step, dict) or set(step) - set(CARDS) - METADATA:
        raise Stop('Unsupported native form notification option')
    if not set(step).intersection(CARDS):
        raise Stop('Specify email_notification or auto_responder')
    if 'action' in step and step['action'] != 'form_notifications':
        raise Stop('Unexpected form notification action')
    if 'id' in step and (not isinstance(step['id'], str) or not re.fullmatch(r'[a-z0-9_-]+', step['id'])):
        raise Stop('Invalid form notification step identity')
    if '_context' in step:
        context = step['_context']
        if not isinstance(context, dict) or set(context) != {'location_id','location_name','start_url'} or any(not isinstance(v,str) or not v for v in context.values()):
            raise Stop('Invalid form notification location context')
    for key in CARDS:
        if key not in step:
            continue
        config = step[key]
        if not isinstance(config, dict) or type(config.get('enabled')) is not bool:
            raise Stop('Every notification configuration needs an explicit enabled boolean')
        expected = {'enabled'}
        if config['enabled']:
            expected |= {'subject','reply_to','sender_name','attach_pdf'}
            if key == 'email_notification':
                expected |= {'recipients','expected_recipients'}
        if set(config) != expected:
            raise Stop('Notification configuration has missing or unsupported options')
        if config['enabled']:
            _text(config['subject'], 'subject')
            _text(config['sender_name'], 'sender name')
            _email(config['reply_to'])
            if type(config['attach_pdf']) is not bool:
                raise Stop('Notification PDF attachment requires an explicit boolean')
            if key == 'email_notification':
                _addresses(config['recipients'], allow_empty=False)
                _addresses(config['expected_recipients'], allow_empty=True)
    return deepcopy(step)


def _card(frame, key):
    cards = frame.locator('.hl-card-content')
    if cards.count() != 2:
        raise Stop('Native notification card count changed')
    title, _ = CARDS[key]
    card = cards.filter(has=frame.get_by_text(title, exact=True))
    if card.count() != 1 or card.get_by_role('switch').count() != 1:
        raise Stop('Native notification card identity changed')
    return card


def _enabled(card):
    state = card.get_by_role('switch').get_attribute('aria-checked')
    if state not in ('true','false'):
        raise Stop('Native notification switch state unavailable')
    return state == 'true'


def _set_enabled(card, value):
    if _enabled(card) != value:
        click(card.get_by_role('switch'))
    wait_until(lambda: _enabled(card) == value, 'Native notification switch did not change')


def _fields(card, key):
    subject = card.get_by_placeholder(CARDS[key][1], exact=True)
    if subject.count() != 1:
        raise Stop('Native notification subject control changed')
    inputs = card.locator('.n-input__input input')
    if inputs.count() != 2:
        raise Stop('Native notification sender controls changed')
    for index, label in enumerate(('Reply-to-email','Sender name')):
        actual = inputs.nth(index).evaluate('el => { let n=el; for(let i=0;i<4;i++) n=n.parentElement; return n.textContent; }')
        if label not in actual:
            raise Stop('Native notification sender control order changed')
    pdf = card.get_by_role('checkbox', name='Send form submission as a PDF', exact=True)
    if pdf.count() != 1:
        raise Stop('Native notification PDF control changed')
    return subject, inputs.nth(0), inputs.nth(1), pdf


def _recipients(card):
    buttons = card.locator('button[id="remove-email"]')
    if buttons.count() and any(buttons.evaluate_all('els => els.map(el => el.textContent.trim())')):
        raise Stop('Notification recipient chip structure changed')
    values = buttons.evaluate_all('els => els.map(el => el.parentElement.textContent.trim())')
    return _addresses(values, allow_empty=True)


def _recipient_input(card):
    control = card.locator('input#email-to-input')
    if control.count() != 1:
        raise Stop('Native email-recipient control changed')
    return control


def _outer_save(frame):
    matches = [loc for loc in frame.get_by_role('button', name='Save', exact=True).all()
               if loc.evaluate('el => el.closest(".hl-card-content") === null')]
    if len(matches) != 1:
        raise Stop('Native outer form Save is ambiguous')
    return matches[0]


def configure_notifications(page, step):
    plan = validate_notifications(step)
    context = plan.get('_context')
    if not context:
        raise Stop('Canonical form notification location context is required')
    assert_tenant(page, context)
    editor_url = page.url
    frame = form_builder(page)
    name = frame.get_by_role('textbox', name='Form Name', exact=True).input_value()
    if not name:
        raise Stop('Native form identity is unreadable')
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Notifications', exact=True))
    # Inspect every requested card before replacing recipients or saving a card.
    for key in CARDS:
        if key not in plan:
            continue
        card = _card(frame, key)
        config = plan[key]
        if config['enabled']:
            _set_enabled(card, True)
            _fields(card, key)
            if key == 'email_notification':
                _recipient_input(card)
                if sorted(_recipients(card)) != sorted(config['expected_recipients']):
                    raise Stop('Existing notification recipient inventory differs; reconcile before replacement')
    assert_tenant(page, context)
    for key in CARDS:
        if key not in plan:
            continue
        card = _card(frame, key)
        config = plan[key]
        _set_enabled(card, config['enabled'])
        if not config['enabled']:
            continue
        if key == 'email_notification' and sorted(config['recipients']) != sorted(config['expected_recipients']):
            buttons = card.locator('button[id="remove-email"]')
            for _ in config['expected_recipients']:
                click(buttons.first)
            if _recipients(card):
                raise Stop('Existing recipient chips did not clear')
            for index, address in enumerate(config['recipients']):
                field = _recipient_input(card)
                fill(field, address)
                field.press('Enter')
                wait_until(lambda: sorted(_recipients(card)) == sorted(config['recipients'][:index+1]), 'Notification recipient chip was not accepted')
        subject, reply_to, sender, pdf = _fields(card, key)
        fill(subject, config['subject'])
        fill(reply_to, config['reply_to'])
        fill(sender, config['sender_name'])
        pdf.set_checked(config['attach_pdf'])
        inner = card.get_by_role('button', name='Save', exact=True)
        if inner.count() != 1:
            raise Stop('Native notification inner Save changed')
        click(inner)
    save = _outer_save(frame)
    click(save)
    wait_until(lambda: save.is_enabled() and not save.locator('img[alt="loading"]').count(), 'Native form notification Save remained busy')
    reopen_editor(page, 'form', name, editor_url)
    assert_tenant(page, context)
    frame = form_builder(page)
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Notifications', exact=True))
    for key in CARDS:
        if key not in plan:
            continue
        card, config = _card(frame, key), plan[key]
        if _enabled(card) != config['enabled']:
            raise Stop('Notification enabled state did not persist')
        if not config['enabled']:
            continue
        subject, reply_to, sender, pdf = _fields(card, key)
        if (subject.input_value(), reply_to.input_value(), sender.input_value(), pdf.is_checked()) != (config['subject'],config['reply_to'],config['sender_name'],config['attach_pdf']):
            raise Stop('Native notification authored settings did not persist')
        if key == 'email_notification' and sorted(_recipients(card)) != sorted(config['recipients']):
            raise Stop('Notification recipient list did not persist')
    public = {key:plan[key]['enabled'] for key in CARDS if key in plan}
    authored = {key:plan[key] for key in CARDS if key in plan}
    return {'status':'NOTIFICATION_SETTINGS_SAVED_AND_REOPENED', 'enabled':public,
            'configuration_sha256':hashlib.sha256(json.dumps(authored,sort_keys=True).encode()).hexdigest(),
            'recipient_count':len(plan.get('email_notification',{}).get('recipients',[])),
            'independent_readback':'COMPLETE', 'behavior_verification':'REQUIRED', 'email_delivery':'NOT_TESTED',
            'form_submitted':False, 'notifications_sent':False}
