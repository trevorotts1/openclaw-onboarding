"""Captured form/survey On Submit plain-message/HTTPS-redirect configuration.

The Settings controls and conditional-precedence banner were captured live in
form-builder-app on 2026-11-08. No copy, redirect, pixel, order or consent value
is generated. Payment Order Confirmation remains on the payment-contract rail.
"""
from copy import deepcopy
import hashlib
import re
from urllib.parse import urlsplit


class SubmissionError(ValueError):
    pass


def validate(step):
    if not isinstance(step, dict) or set(step) - {'id', 'action', 'mode', 'message', 'redirect_url', 'ack_conditional_precedence', 'checkout_contract'}:
        raise SubmissionError('Unsupported native form submission setting')
    mode = step.get('mode')
    if mode == 'Order Confirmation':
        contract = step.get('checkout_contract')
        if not isinstance(contract, dict) or contract.get('status') != 'PASS' or not contract.get('source'):
            raise SubmissionError('Order Confirmation requires the native payment-contract dependency')
        raise SubmissionError('Order Confirmation must use the payment-contract executor, not the plain-message/redirect recipe')
    if mode not in ('Message', 'Redirect to URL'):
        raise SubmissionError('Submission mode must be Message or Redirect to URL')
    if 'checkout_contract' in step:
        raise SubmissionError('A plain-message/redirect recipe must not silently consume a payment contract')
    if 'ack_conditional_precedence' in step and type(step['ack_conditional_precedence']) is not bool:
        raise SubmissionError('Conditional precedence acknowledgment must be a boolean')
    result = deepcopy(step)
    if mode == 'Message':
        if not isinstance(step.get('message'), str) or not step['message'].strip():
            raise SubmissionError('Caller-approved plain message text is required')
        if 'redirect_url' in step:
            raise SubmissionError('Message mode must not carry an ignored redirect')
        result['message'] = step['message'].replace('\r\n', '\n').replace('\r', '\n').strip()
    else:
        value = step.get('redirect_url')
        if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
            raise SubmissionError('Caller-approved HTTPS redirect is required')
        try:
            parsed = urlsplit(value)
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            raise SubmissionError('Redirect URL is invalid') from None
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or not valid_port:
            raise SubmissionError('Redirect must be HTTPS without embedded credentials')
        if 'message' in step:
            raise SubmissionError('Redirect mode must not carry ignored message text')
    return result


PROFILES = {
    'form': {'route':'form-builder-v2','iframe':None,'redirect_selector':None,
             'status':'FORM_SUBMISSION_SAVED_AND_REOPENED'},
    'survey': {'route':'survey-builder-v2','iframe':'survey-builder-app','redirect_selector':'#submitMessage input',
               'status':'SURVEY_SUBMISSION_SAVED_AND_REOPENED'},
}


def configure(page, step, *, surface='form', read_only=False):
    """Read precedence first, then write, save and independently reopen values."""
    if __package__:
        from .skill6_playwright import click, fill, visible, form_builder, wait_until, Stop
        from .assessments import reopen_editor, read_editor_title
    else:
        from skill6_playwright import click, fill, visible, form_builder, wait_until, Stop
        from assessments import reopen_editor, read_editor_title
    step = validate(step)
    if surface not in PROFILES:raise Stop('Uncaptured submission editor profile')
    profile=PROFILES[surface]
    editor_url=page.url;parsed=urlsplit(editor_url)
    if parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/'+profile['route']+r'/[A-Za-z0-9_-]+/?', parsed.path):
        raise Stop('Native submission editor identity is not a captured exact HTTPS route')
    frame = form_builder(page) if profile['iframe'] is None else page.frame_locator('iframe[name="'+profile['iframe']+'"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    form_name, editor_url = read_editor_title(title), page.url

    def open_settings():
        if surface=='survey' and visible(frame.get_by_text('Your survey is ready',exact=True)):
            panel_close=frame.get_by_role('button',name='Close',exact=True)
            if panel_close.count()!=1:raise Stop('Survey completion panel Close is ambiguous')
            click(panel_close)
        close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
        if visible(close):
            click(close)
        click(frame.get_by_role('tab', name='Settings', exact=True))
        selected = frame.locator('.n-base-selection-input__content').filter(
            has_text=re.compile(r'^(Message|Redirect to URL|Order Confirmation)$'))
        selected.wait_for(state='visible', timeout=45000)
        if selected.count() != 1:
            raise Stop('Native On Submit mode control changed')
        warning = frame.get_by_text(re.compile(r'Conditional logic will take precedence', re.I))
        precedence = any(loc.is_visible() for loc in warning.all())
        return selected, precedence

    selected, precedence = open_settings()
    if selected.inner_text().strip() == 'Order Confirmation':
        raise Stop('Existing Order Confirmation must be changed through the native payment-contract executor')
    # This read-only inspection happens before changing mode or content.
    if precedence and step.get('ack_conditional_precedence') is not True:
        raise Stop('Existing conditional logic overrides submission settings; explicit acknowledgment is required before edits')
    if read_only and selected.inner_text().strip() != step['mode']:
        raise Stop('Completed survey submission mode drifted; no writes repeated')
    if selected.inner_text().strip() != step['mode']:
        click(selected)
        choice = frame.locator('.n-base-select-option').get_by_text(step['mode'], exact=True)
        if choice.count() != 1:
            raise Stop('Native submission mode choice is absent or ambiguous')
        click(choice)
    wait_until(lambda: selected.inner_text().strip() == step['mode'], 'Native submission mode did not change')

    def control():
        if step['mode'] == 'Message':
            loc = frame.locator('div.tiptap.ProseMirror')
        else:
            loc = (frame.locator(profile['redirect_selector']) if profile['redirect_selector']
                   else frame.get_by_placeholder('https://example.com', exact=True))
        if loc.count() != 1:
            raise Stop('Native submission value editor changed')
        loc.wait_for(state='visible', timeout=45000)
        return loc

    expected = step['message'] if step['mode'] == 'Message' else step['redirect_url']
    if not read_only:
        fill(control(), expected)  # Native fill inserts literal text, never HTML.
        click(frame.get_by_role('button', name='Save', exact=True))
        wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
                   and frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Submission save did not finish')
        reopen_editor(page, surface, form_name, editor_url)
        selected, persisted_precedence = open_settings()
    else:persisted_precedence=precedence
    if selected.inner_text().strip() != step['mode']:
        raise Stop('Native submission mode was not persisted')
    loc = control()
    observed = loc.inner_text().strip() if step['mode'] == 'Message' else loc.input_value()
    if observed != expected:
        raise Stop('Native submission value was not persisted')
    if persisted_precedence and step.get('ack_conditional_precedence') is not True:
        raise Stop('Conditional precedence appeared during verification; reconcile before relying on submission behavior')
    return {'status': profile['status'], 'mode': step['mode'],
            'editor_url': page.url, 'value_sha256': hashlib.sha256(expected.encode()).hexdigest(),
            'conditional_precedence_present': persisted_precedence,
            'conditional_precedence_acknowledged': step.get('ack_conditional_precedence', False),
            'independent_readback': 'VERIFIED', 'behavior_verified': False,
            'submission_verified': False}



def validate_completion(value,step,editor_url):
    """Bind a survey completion receipt to approved mode/value and exact editor."""
    plan=validate(step)
    expected=plan['message'] if plan['mode']=='Message' else plan['redirect_url']
    keys={'status','mode','editor_url','value_sha256','conditional_precedence_present',
          'conditional_precedence_acknowledged','independent_readback','behavior_verified','submission_verified'}
    if (not isinstance(value,dict) or set(value)!=keys
            or value['status']!='SURVEY_SUBMISSION_SAVED_AND_REOPENED'
            or value['mode']!=plan['mode'] or value['editor_url']!=editor_url
            or value['value_sha256']!=hashlib.sha256(expected.encode()).hexdigest()
            or type(value['conditional_precedence_present']) is not bool
            or value['conditional_precedence_acknowledged'] is not plan.get('ack_conditional_precedence',False)
            or value['conditional_precedence_present'] and not value['conditional_precedence_acknowledged']
            or value['independent_readback']!='VERIFIED' or value['behavior_verified'] is not False
            or value['submission_verified'] is not False):
        raise SubmissionError('Survey submission completion is malformed or unbound')
    return deepcopy(value)


def verify_completed(page,step,receipt):
    value=validate_completion(receipt,step,page.url)
    if __package__:
        from .assessments import read_editor_title, reopen_editor
    else:
        from assessments import read_editor_title, reopen_editor
    frame=page.frame_locator('iframe[name="survey-builder-app"]')
    title=frame.get_by_role('textbox',name='Form Name',exact=True)
    title.wait_for(state='visible',timeout=45000)
    if title.count()!=1:raise SubmissionError('Completed survey title is missing or ambiguous')
    survey_name=read_editor_title(title)
    reopen_editor(page,'survey',survey_name,value['editor_url'])
    configure(page,step,surface='survey',read_only=True)
    return value
