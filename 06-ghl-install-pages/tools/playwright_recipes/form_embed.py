"""Captured native Integrate/Embed configuration and exact code export.

The enclosing runner owns tenant checks and write journals. Native export is
never proof that an embed was installed, published or submitted successfully.
"""
from copy import deepcopy
import ast
import hashlib
import io
from html.parser import HTMLParser
import json
import re
import tokenize
from urllib.parse import urlsplit

if __package__:
    from .assessments import read_editor_title
    from .skill6_playwright import Stop
else:
    from assessments import read_editor_title
    from skill6_playwright import Stop


LAYOUTS = ('Sidebar', 'Popover', 'Popup', 'Standard')
POSITIONS = ('Left', 'Right')
# Exact observed labels; other appearance controls need separate captures.
GENERAL = frozenset(('layout', 'position', 'width', 'height', 'button_label'))
ADVANCED = frozenset(('activation', 'activation_visits', 'trigger', 'scroll_percentage', 'delay_seconds',
                      'deactivation', 'deactivation_views', 'respect_cookie_consent'))
ACTIVATIONS = ('activateOnVisit', 'alwaysActivated')
TRIGGERS = ('showOnScrolling', 'showAfter', 'alwaysShow')
DEACTIVATIONS = ('deactivateAfter', 'leadCollected', 'neverDeactivate')


def _origin(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        raise Stop('Embed origins must be explicit credential-free HTTPS origins')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                 and not parsed.password and parsed.port in (None, 443)
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise Stop('Embed origins must be explicit credential-free HTTPS origins')
    return parsed.scheme + '://' + parsed.netloc


def _properties(values):
    if not isinstance(values, dict) or set(values) - GENERAL - ADVANCED:
        raise Stop('Unknown native form integration property')
    for key, choices in (('layout', LAYOUTS), ('position', POSITIONS + (None,)),
                         ('activation', ACTIVATIONS), ('trigger', TRIGGERS),
                         ('deactivation', DEACTIVATIONS)):
        if key in values and not (key == 'position' and values[key] is None) and (not isinstance(values[key], str) or values[key] not in choices):
            raise Stop('Uncaptured native form integration choice: ' + key)
    for key in ('width', 'activation_visits', 'scroll_percentage', 'delay_seconds', 'deactivation_views'):
        if key in values and (type(values[key]) is not int or values[key] < 1
                              or values[key] > 100000):
            raise Stop('Integration numeric properties require positive integers: ' + key)
    if values.get('scroll_percentage', 1) > 100:
        raise Stop('Scroll percentage must be 1 to 100')
    if 'height' in values and values['height'] != 'Auto' and (
            type(values['height']) is not int or not 1 <= values['height'] <= 100000):
        raise Stop('Integration height must be Auto or a positive integer')
    if 'button_label' in values and values['button_label'] is not None and (not isinstance(values['button_label'], str)
            or not values['button_label'].strip() or len(values['button_label']) > 500
            or any(ord(c) < 32 for c in values['button_label'])):
        raise Stop('Integration button label must be authored single-line text')
    if 'respect_cookie_consent' in values and type(values['respect_cookie_consent']) is not bool:
        raise Stop('Respect host cookie consent requires an explicit boolean')


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'integration'}
            or step.get('action', 'native_form_embed') != 'native_form_embed'):
        raise Stop('Unsupported native form embed action')
    config = step.get('integration')
    if (not isinstance(config, dict)
            or not {'expected', 'changes', 'embed_origin', 'script_origin', 'form_id', 'expected_form_name'}.issubset(config)
            or set(config)-{'expected', 'changes', 'embed_origin', 'script_origin', 'form_id', 'expected_form_name', 'appearance'}
            or not isinstance(config.get('expected'), dict)
            or not isinstance(config.get('changes'), dict)
            or set(config['expected']) != set(config['changes'])):
        raise Stop('Integration edits require identical explicit expected/changed property keys')
    if (not isinstance(config['form_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', config['form_id'])
            or not isinstance(config['expected_form_name'], str) or not config['expected_form_name'].strip()
            or any(ord(c) < 32 for c in config['expected_form_name'])):
        raise Stop('Embed export requires exact inventoried form ID and name')
    _properties(config['expected'])
    _properties(config['changes'])
    _origin(config['embed_origin'])
    _origin(config['script_origin'])
    if 'appearance' in config:
        appearance=config['appearance']
        if (not isinstance(appearance,dict) or set(appearance)!={'expected','changes'}
                or not isinstance(appearance['expected'],dict) or not isinstance(appearance['changes'],dict)
                or not appearance['changes'] or set(appearance['expected'])!=set(appearance['changes'])):
            raise Stop('Embed appearance requires matching nonempty previous/desired property keys')
        _appearance_values(appearance['expected']);_appearance_values(appearance['changes'])
    plan=deepcopy(step)
    if 'appearance' in config:
        for values in plan['integration']['appearance'].values():
            if 'button_color' in values:values['button_color']=_opaque_hex(values['button_color'])
    return plan


def configuration_hash(step):
    config = validate(step)['integration']
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class _ExportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.stack = []
    def handle_starttag(self, tag, attrs):
        if tag not in ('iframe', 'script') or self.stack:
            raise Stop('Native export contains an unexpected or nested HTML element')
        keys = [key for key, _ in attrs]
        if len(keys) != len(set(keys)) or any(key.startswith('on') or key == 'srcdoc' for key in keys):
            raise Stop('Native export contains duplicate or executable inline attributes')
        self.tags.append((tag, dict(attrs)))
        self.stack.append(tag)
    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise Stop('Native export contains malformed HTML tag boundaries')
    def handle_data(self, data):
        if data.strip():
            raise Stop('Native export contains unexpected inline content')
    def handle_comment(self, data):
        raise Stop('Native export contains an unexpected comment')
    def handle_decl(self, decl):
        raise Stop('Native export must be the native iframe/script fragment')


def validate_export(code, *, form_id, embed_origin, script_origin, form_name):
    """Return the exact native bytes after binding their frame and loader URLs."""
    if (not isinstance(code, str) or not code.strip() or len(code) > 100000
            or any(ord(c) < 32 and c not in '\n\r\t' for c in code)
            or not isinstance(form_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', form_id)):
        raise Stop('Native form embed export or form identity is malformed')
    parser = _ExportParser()
    try:
        parser.feed(code)
        parser.close()
    except (ValueError, AssertionError):
        raise Stop('Native form embed is not a valid iframe/script fragment') from None
    if parser.stack or [tag for tag, _ in parser.tags] != ['iframe', 'script']:
        raise Stop('Native form embed requires exactly one complete iframe and loader')
    iframe, script = (attrs for _, attrs in parser.tags)
    frame_src, loader_src = iframe.get('src'), script.get('src')
    for value in (frame_src, loader_src):
        if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
            raise Stop('Native embed URLs must be literal credential-free HTTPS URLs')
    frame_url, loader_url = urlsplit(frame_src), urlsplit(loader_src)
    if (frame_url.scheme + '://' + frame_url.netloc != _origin(embed_origin)
            or frame_url.path != '/widget/form/' + form_id
            or frame_url.query or frame_url.fragment or frame_url.username or frame_url.password
            or iframe.get('data-form-id') != form_id
            or iframe.get('data-form-name') != form_name or iframe.get('title') != form_name
            or iframe.get('data-layout-iframe-id') != iframe.get('id')
            or not isinstance(iframe.get('id'), str) or not iframe['id'].endswith('-' + form_id)):
        raise Stop('Native embed frame does not belong to the inventoried form and origin')
    if (loader_url.scheme + '://' + loader_url.netloc != _origin(script_origin)
            or loader_url.path != '/js/form_embed.js' or loader_url.query or loader_url.fragment
            or loader_url.username or loader_url.password):
        raise Stop('Native embed loader differs from the inventoried provider origin')
    return {'embed_code': code, 'embed_sha256': hashlib.sha256(code.encode()).hexdigest(),
            'form_id': form_id}


NUMBERS = {'activation_visits':('activateOnVisit', '3'),
           'scroll_percentage':('showOnScrolling', '50'),
           'delay_seconds':('showAfter', '5'),
           'deactivation_views':('deactivateAfter', '1')}
RADIO_VALUES = {'activation':ACTIVATIONS, 'trigger':TRIGGERS, 'deactivation':DEACTIVATIONS}


def _one(node, reason, *, visible=True):
    if visible:
        try:
            node.wait_for(state='visible', timeout=45000)
        except Exception:
            raise Stop(reason) from None
    if node.count() != 1 or visible and not node.is_visible():
        raise Stop(reason)
    return node


def _general_radio(frame, kind, values):
    controls = {}
    selected = []
    for value in values:
        control = _one(frame.locator('#embed-' + kind + '-' + value.lower()),
                       'Native embed radio changed: ' + kind + '.' + value)
        if control.get_attribute('role') != 'radio' or control.get_attribute('aria-checked') not in ('true', 'false'):
            raise Stop('Native embed radio state is unavailable')
        controls[value] = control
        if control.get_attribute('aria-checked') == 'true':
            selected.append(value)
    if len(selected) != 1:
        raise Stop('Native embed selection is ambiguous: ' + kind)
    return selected[0], controls


def _number(control, label, default=None):
    raw = control.input_value()
    if raw == '' and default is not None and control.get_attribute('placeholder') == default:
        raw = default
    if not isinstance(raw, str) or not re.fullmatch(r'[0-9]+', raw):
        raise Stop('Native embed numeric value is unavailable: ' + label)
    return int(raw)


def _general(frame):
    from playwright_recipes.skill6_playwright import click
    click(_one(frame.get_by_role('tab', name='General', exact=True), 'Native embed General tab changed'))
    layout, layouts = _general_radio(frame, 'type', LAYOUTS)
    position, positions = (None, {})
    if layout in ('Sidebar', 'Popover'):
        position, positions = _general_radio(frame, 'position', POSITIONS)
    selectors = {'width':'#integrate-form-width input', 'height':'#integrate-form-height input'}
    if layout != 'Standard':
        selectors['button_label'] = '#integrate-button-label input'
    controls = {key:_one(frame.locator(selector), 'Native embed input changed: ' + key)
                for key, selector in selectors.items()}
    height = controls['height'].input_value()
    if height == '' and controls['height'].get_attribute('placeholder') == 'Auto':
        height = 'Auto'
    else:
        height = _number(controls['height'], 'height')
    state = {'layout':layout, 'position':position,
             'width':_number(controls['width'], 'width', '800'),
             'height':height, 'button_label':(controls['button_label'].input_value() if layout != 'Standard' else None)}
    _properties(state)
    return state, {**controls, 'layout':layouts, 'position':positions}


def _advanced(frame):
    from playwright_recipes.skill6_playwright import click
    click(_one(frame.get_by_role('tab', name='Advanced', exact=True), 'Native embed Advanced tab changed'))
    pane = _one(frame.locator('#embed-advanced-panel'), 'Native embed Advanced panel changed')
    settings = _one(pane.locator('section[data-testid="embed-advanced-settings"]'),
                    'Native embed Advanced settings scope changed')
    state, controls = {}, {}
    for key, values in RADIO_VALUES.items():
        if settings.locator('input[name="embed-' + key + '"]').count() != len(values):
            raise Stop('Native embed Advanced radio group inventory changed: ' + key)
        choices, selected = {}, []
        for value in values:
            label = _one(settings.locator('#integrate-' + value), 'Native embed Advanced choice changed')
            node = _one(label.locator('input[name="embed-' + key + '"][value="' + value + '"]'),
                        'Native embed Advanced radio identity changed', visible=False)
            choices[value] = label
            if node.is_checked():
                selected.append(value)
        if len(selected) != 1:
            raise Stop('Native embed Advanced selected choice is ambiguous: ' + key)
        state[key], controls[key] = selected[0], choices
    for key, (value, default) in NUMBERS.items():
        control = _one(settings.locator('#integrate-' + value + '-value input'),
                       'Native embed Advanced number changed: ' + key)
        state[key], controls[key] = _number(control, key, default), control
    consent = _one(settings.locator('#cookieConsent'), 'Native embed cookie consent switch changed')
    if consent.get_attribute('role') != 'switch' or consent.get_attribute('aria-checked') not in ('true', 'false'):
        raise Stop('Native embed cookie consent state is unavailable')
    state['respect_cookie_consent'] = consent.get_attribute('aria-checked') == 'true'
    provider = settings.locator('#cookieConsentProvider')
    if state['respect_cookie_consent']:
        provider = _one(provider, 'Native embed consent provider changed')
        selected = _one(provider.locator('.n-base-selection-input'),
                        'Native embed cookie provider selection changed').get_attribute('title')
        if selected != 'Auto-detect':
            raise Stop('Native embed consent provider must match inventoried Auto-detect')
    elif provider.count():
        raise Stop('Native embed consent provider should be absent while consent is disabled')
    controls['respect_cookie_consent'] = consent
    _properties(state)
    return state, controls


def _read(frame):
    general, _ = _general(frame)
    advanced, _ = _advanced(frame)
    return {**general, **advanced}


def _layout_data(value):
    """Parse the native single-quoted object without executing JavaScript."""
    if not isinstance(value, str):
        raise Stop('Native embed layout metadata is absent')
    try:
        tokens = []
        for token in tokenize.generate_tokens(io.StringIO(value).readline):
            if token.type == tokenize.NAME and token.string in ('true', 'false', 'null'):
                token = token._replace(string={'true':'True', 'false':'False', 'null':'None'}[token.string])
            tokens.append(token)
        result = ast.literal_eval(tokenize.untokenize(tokens))
    except (ValueError, SyntaxError, tokenize.TokenError):
        raise Stop('Native embed layout metadata is malformed') from None
    if not isinstance(result, dict):
        raise Stop('Native embed layout metadata is not an object')
    return result


def verify_export_configuration(code, config, desired, appearance=None):
    """Check native code metadata as well as the visible builder controls."""
    validated = validate_export(code, form_id=config['form_id'],
        embed_origin=config['embed_origin'], script_origin=config['script_origin'],
        form_name=config['expected_form_name'])
    parser = _ExportParser(); parser.feed(code); parser.close()
    iframe = parser.tags[0][1]
    layout = _layout_data(iframe.get('data-layout'))
    mode = desired['layout']
    mapping = {'Sidebar':('STICKY_SIDEBAR', 'sticky-sidebar-' + str(desired['position']).lower()),
               'Popover':('POLITE_SLIDE_IN', 'polite-slide-in-' + str(desired['position']).lower()),
               'Popup':('POPUP', 'popup'), 'Standard':('INLINE', 'inline')}
    expected_layout, prefix = mapping[mode]
    if iframe.get('id') != prefix + '-' + config['form_id'] or layout.get('id') != expected_layout:
        raise Stop('Native embed layout identity differs from the requested configuration')
    if mode != 'Standard' and layout.get('minimizedTitle') != desired['button_label']:
        raise Stop('Native embed button label differs from the authored configuration')
    if mode in ('Sidebar', 'Popover'):
        left = desired['position'] == 'Left'
        if (layout.get('isLeftAligned') is not left or layout.get('isRightAligned') is not (not left)
                or layout.get('allowMinimize') is not True):
            raise Stop('Native embed position differs from the authored configuration')
    if mode in ('Popup', 'Standard'):
        if layout.get('formWidth', 800) != desired['width']:
            raise Stop('Native embed width differs from the authored configuration')
    if mode == 'Popup':
        actual_height = iframe.get('data-modal-height')
        expected_height = None if desired['height'] == 'Auto' else str(desired['height'])
        if actual_height != expected_height:
            raise Stop('Native Popup embed height differs from the authored configuration')
    for key, attribute in (('activation','data-activation-type'), ('trigger','data-trigger-type'),
                           ('deactivation','data-deactivation-type')):
        if iframe.get(attribute) != desired[key]:
            raise Stop('Native embed exported behavior differs: ' + key)
    for key, kind, active in (('activation_visits','activation','activateOnVisit'),
                              ('scroll_percentage','trigger','showOnScrolling'),
                              ('delay_seconds','trigger','showAfter'),
                              ('deactivation_views','deactivation','deactivateAfter')):
        if desired[kind] == active and iframe.get('data-' + kind + '-value') != str(desired[key]):
            raise Stop('Native embed exported behavior value differs: ' + key)
    providers = ('auto',) if desired['respect_cookie_consent'] else (None, 'auto')
    if (iframe.get('data-cookie-consent') != str(desired['respect_cookie_consent']).lower()
            or iframe.get('data-cookie-consent-provider') not in providers):
        raise Stop('Native embed exported cookie consent differs from its inventoried settings')
    if appearance is not None:
        _appearance_values(appearance,complete=True)
        if (mode=='Standard' or layout.get('cornerRadius')!=appearance['corner_radii']
                or layout.get('fontSize')!=appearance['font_size']
                or layout.get('buttonType')!=appearance['button_type']
                or layout.get('buttonSize')!=appearance['button_size']
                or layout.get('buttonIcon')!=appearance.get('button_icon','chat')
                or 'button_color' in appearance and _opaque_hex(layout.get('buttonColor'))!=appearance['button_color']):
            raise Stop('Native embed button appearance differs from its authored values or captured color/icon binding')
    return validated


def _export(frame, config, desired, appearance=None):
    from playwright_recipes.skill6_playwright import click
    click(_one(frame.get_by_role('button', name='Embed code', exact=True), 'Native Embed code button changed'))
    dialog = _one(frame.get_by_role('dialog').filter(
        has=frame.get_by_role('heading', name='Embed in webpage', exact=True)),
        'Native Embed in webpage dialog is missing or ambiguous')
    _one(dialog.locator('#copy-embed-code'), 'Native Copy code control changed')
    lines = dialog.locator('pre.CodeMirror-line')
    if not 2 <= lines.count() <= 100:
        raise Stop('Native embed displayed code-line inventory changed')
    code = lines.evaluate_all(r'nodes => nodes.map(node => node.textContent).join("\n")')
    result = verify_export_configuration(code, config, desired, appearance)
    click(_one(dialog.locator('#embed-code-modal-modal-close-btn'), 'Native embed dialog close changed'))
    dialog.wait_for(state='hidden', timeout=45000)
    return result



def _supported_desired(config, desired, *, layout_changed):
    if layout_changed and not {'layout','position','width','height','button_label'}.issubset(config['changes']):
        raise Stop('Layout switches require the complete expected/desired General configuration')
    if desired['layout'] != 'Standard' and (not isinstance(desired['button_label'], str)
            or not desired['button_label'].strip()):
        raise Stop('The selected button layout requires authored button text')
    if desired['layout'] in ('Sidebar', 'Popover'):
        if desired['position'] not in POSITIONS:
            raise Stop('Sidebar and Popover need explicit position and button label')
    elif desired['position'] is not None or desired['layout'] == 'Standard' and desired['button_label'] is not None:
        raise Stop('The selected layout has no native position/button-label control')
    if 'width' in config['changes'] and desired['layout'] not in ('Popup', 'Standard') and desired['width'] != 800:
        raise Stop('Nondefault width export is captured for Popup and Standard only')
    if 'height' in config['changes'] and desired['layout'] != 'Popup' and desired['height'] != 'Auto':
        raise Stop('Explicit exported height is captured for Popup only; Standard ignores height')
    for number, kind, active in (('activation_visits','activation','activateOnVisit'),
                                ('scroll_percentage','trigger','showOnScrolling'),
                                ('delay_seconds','trigger','showAfter'),
                                ('deactivation_views','deactivation','deactivateAfter')):
        if number in config['changes'] and desired[kind] != active:
            raise Stop('Requested embed numeric value belongs to an inactive choice: ' + number)


LEGACY_APPEARANCE_FIELDS=frozenset(('corner_radii','font_size','linked','button_type','button_size'))
APPEARANCE_FIELDS=LEGACY_APPEARANCE_FIELDS|{'button_color','button_icon'}
BUTTON_TYPES={'text':'Text','textIcon':'Icon + text','icon':'Icon only'}
BUTTON_SIZES={'small':'Small','medium':'Medium','large':'Large'}
# Captured native material-code/accessible-label catalog; no guessed icon names.
BUTTON_ICONS={'send': 'Send', 'done': 'Done', 'check_circle': 'Check Circle', 'task_alt': 'Task Alt', 'checklist': 'Checklist', 'forward_to_inbox': 'Forward To Inbox', 'shopping_cart': 'Shopping Cart', 'shopping_bag': 'Shopping Bag', 'add_shopping_cart': 'Add Shopping Cart', 'payment': 'Payment', 'credit_card': 'Credit Card', 'account_balance_wallet': 'Account Balance Wallet', 'payments': 'Payments', 'monetization_on': 'Monetization On', 'attach_money': 'Attach Money', 'currency_exchange': 'Currency Exchange', 'receipt_long': 'Receipt Long', 'request_quote': 'Request Quote', 'description': 'Description', 'note_add': 'Note Add', 'upload_file': 'Upload File', 'cloud_upload': 'Cloud Upload', 'file_upload_off': 'File Upload Off', 'file_present': 'File Present', 'archive': 'Archive', 'fact_check': 'Fact Check', 'content_paste': 'Content Paste', 'content_copy': 'Content Copy', 'mail': 'Mail', 'email': 'Email', 'outgoing_mail': 'Outgoing Mail', 'sms': 'Sms', 'chat': 'Chat', 'forum': 'Forum', 'support_agent': 'Support Agent', 'approval': 'Approval', 'rule': 'Rule', 'verified': 'Verified', 'verified_user': 'Verified User', 'how_to_reg': 'How To Reg', 'person_add': 'Person Add', 'done_all': 'Done All', 'arrow_forward': 'Arrow Forward', 'chevron_right': 'Chevron Right', 'double_arrow': 'Double Arrow', 'arrow_circle_right': 'Arrow Circle Right', 'east': 'East', 'done_outline': 'Done Outline', 'exit_to_app': 'Exit To App', 'event_available': 'Event Available', 'event_note': 'Event Note', 'calendar_month': 'Calendar Month', 'book_online': 'Book Online', 'local_activity': 'Local Activity', 'local_offer': 'Local Offer', 'lock': 'Lock', 'login': 'Login', 'logout': 'Logout', 'fingerprint': 'Fingerprint', 'key': 'Key', 'publish': 'Publish', 'rocket_launch': 'Rocket Launch', 'send_and_archive': 'Send And Archive', 'campaign': 'Campaign', 'share': 'Share', 'visibility': 'Visibility', 'download_done': 'Download Done'}
CORNERS=('tl','tr','bl','br')


def _appearance_values(value, *, complete=False):
    if (not isinstance(value,dict) or not value or set(value)-APPEARANCE_FIELDS
            or complete and not LEGACY_APPEARANCE_FIELDS.issubset(value)):
        raise Stop('Embed appearance must use captured button properties')
    if 'button_color' in value:_opaque_hex(value['button_color'])
    if 'corner_radii' in value:
        radii=value['corner_radii']
        if (not isinstance(radii,dict) or set(radii)!=set(CORNERS)
                or any(type(number) is not int or not 0<=number<=1000 for number in radii.values())):
            raise Stop('Button corners require four explicit nonnegative integers within the script limit of 1000')
    if 'font_size' in value and (type(value['font_size']) is not int or not 1<=value['font_size']<=256):
        raise Stop('Button font size must be an integer within the script limit of 1 to 256')
    if 'linked' in value and type(value['linked']) is not bool:
        raise Stop('Corner linking requires a real boolean')
    for key,values in (('button_type',BUTTON_TYPES),('button_size',BUTTON_SIZES),('button_icon',BUTTON_ICONS)):
        if key in value and (not isinstance(value[key],str) or value[key] not in values):
            raise Stop('Uncaptured native button appearance choice: '+key)


def _appearance_select(frame,key,values):
    wrapper=_one(frame.locator('#integrate-'+key.replace('_','-')),
                 'Native embed appearance select changed: '+key)
    selected=_one(wrapper.locator('.n-base-selection-input'),
                  'Native embed appearance selected identity changed: '+key)
    text=_one(selected.locator('.n-base-selection-input__content'),
              'Native embed appearance selected text changed: '+key).inner_text().strip()
    if selected.get_attribute('title')!=text or text not in values.values():
        raise Stop('Native embed button appearance choice is unknown or inconsistent')
    return next(value for value,label in values.items() if label==text),selected


def _appearance(frame, *, extra_fields=(), hidden_icon=None):
    general,_=_general(frame)
    if general['layout']=='Standard':
        raise Stop('Standard embeds have no native button appearance controls')
    controls={};radii={}
    for corner in CORNERS:
        control=_one(frame.locator('#integrate-corner-'+corner+' input'),
                     'Native button corner input changed: '+corner)
        controls[corner]=control;radii[corner]=_number(control,'corner '+corner)
    font=_one(frame.locator('#integrate-button-font-size input'),'Native button font size input changed')
    linked=_one(frame.locator('#embed-corner-link'),'Native corner link button changed')
    if (linked.get_attribute('data-testid')!='embed-corner-link'
            or linked.get_attribute('aria-label')!='Link corner radius values'
            or linked.get_attribute('aria-pressed') not in ('true','false')):
        raise Stop('Native corner link button identity/state changed')
    type_value,type_control=_appearance_select(frame,'button_type',BUTTON_TYPES)
    size_value,size_control=_appearance_select(frame,'button_size',BUTTON_SIZES)
    state={'corner_radii':radii,'font_size':_number(font,'button font size'),
           'linked':linked.get_attribute('aria-pressed')=='true',
           'button_type':type_value,'button_size':size_value}
    if 'button_color' in extra_fields:
        state['button_color'],controls['button_color']=_button_color(frame)
    if 'button_icon' in extra_fields:
        state['button_icon'],controls['button_icon']=_button_icon(frame,type_value,hidden_icon=hidden_icon)
    _appearance_values(state,complete=True)
    return state,{**controls,'font_size':font,'linked':linked,
                  'button_type':type_control,'button_size':size_control}




def _opaque_hex(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}(?:[fF]{2})?',value):
        raise Stop('Native embed button color is not a captured opaque HEX/RGBA value')
    # Native default is RGB6; selecting a palette swatch emits uppercase RGBA8.
    # Canonical input/state stays lowercase RGB6, exact exported bytes are retained.
    return value[:7].lower()


def _button_icon(frame,button_type,*,hidden_icon=None):
    selector='div.cursor-pointer[aria-haspopup="listbox"][aria-expanded]'
    controls=frame.locator(selector)
    if button_type=='text':
        if controls.count() or hidden_icon not in BUTTON_ICONS:
            raise Stop('Hidden native icon requires its exact before-export binding')
        return hidden_icon,None
    control=_one(controls,'Native embed icon selector changed')
    symbol=_one(control.locator('.material-symbols-outlined'),'Native embed selected material icon changed').inner_text().strip()
    label=_one(control.locator('span.truncate.text-gray-900'),'Native embed selected icon label changed').inner_text().strip()
    if symbol not in BUTTON_ICONS or BUTTON_ICONS[symbol]!=label or control.get_attribute('aria-expanded') not in ('true','false'):
        raise Stop('Native embed icon code and label are unknown or disagree')
    return symbol,control


def _write_button_icon(frame,button_type,expected,desired,identity):
    from playwright_recipes.skill6_playwright import click,fill,wait_until
    if button_type=='text':raise Stop('Icon changes require an explicit Icon + text or Icon only button type')
    current,control=_button_icon(frame,button_type)
    # A deliberate button-type switch may reveal the retained icon. The exact
    # authored expected icon has already been checked in the before export.
    if current not in (expected,desired):raise Stop('Native embed icon changed before selection')
    if current==desired:return
    identity();click(control)
    wait_until(lambda:control.get_attribute('aria-expanded')=='true','Native embed icon catalog did not open')
    search=_one(frame.get_by_role('textbox',name='Icon search',exact=True),'Native embed icon search changed')
    fill(search,BUTTON_ICONS[desired])
    option=_one(frame.get_by_role('button',name=BUTTON_ICONS[desired],exact=True),'Native embed captured icon option is missing or ambiguous')
    identity();click(option)
    wait_until(lambda:_button_icon(frame,button_type)[0]==desired,'Native embed selected icon did not stick')

def _color_hex(style):
    if not isinstance(style,str):raise Stop('Native embed color swatch style is unavailable')
    match=re.fullmatch(r'\s*background:\s*rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*;?\s*',style)
    if not match or any(int(value)>255 for value in match.groups()):
        raise Stop('Native embed palette requires captured opaque RGB swatches')
    return '#'+''.join(format(int(value),'02x') for value in match.groups())


def _button_color(frame):
    owner=_one(frame.locator('#colorPicker'),'Native embed Button color owner changed')
    if owner.get_by_text('Button color',exact=True).count()!=1:
        raise Stop('Native embed Button color label changed')
    display=_one(owner.locator('.color-display .hl-text-sm-normal'),'Native button HEX display changed').inner_text().strip()
    display=_opaque_hex(display)
    _appearance_values({'button_color':display})
    trigger=_one(owner.locator('.hr-swatch-tile__pad'),'Native button color picker trigger changed')
    swatch=_one(trigger.locator('.hr-swatch-tile__pad-inner'),'Native button color swatch changed')
    if _color_hex(swatch.get_attribute('style'))!=display:
        raise Stop('Native button color display and swatch disagree')
    return display,trigger


def _write_button_color(frame,expected,desired,identity):
    from playwright_recipes.skill6_playwright import click,wait_until
    current,trigger=_button_color(frame)
    if current!=expected:raise Stop('Native embed Button color changed before picker selection')
    identity();click(trigger)
    palette=_one(frame.locator('.hr-colorpicker__popover-content-section').filter(
        has=frame.get_by_text('Default Colors',exact=True)), 'Captured native Default Colors palette changed')
    tiles=palette.locator('.swatches-container .hr-swatch__container');matches=[]
    for index in range(tiles.count()):
        tile=tiles.nth(index)
        if not tile.is_visible():continue
        swatch=_one(tile.locator('.hr-swatch-tile__pad-inner'),'Native palette swatch is ambiguous')
        if _color_hex(swatch.get_attribute('style'))==desired:
            matches.append(_one(tile.locator('.hr-swatch-tile__pad'),'Native palette selectable tile changed'))
    if len(matches)!=1:
        raise Stop('NEEDS_PALETTE_COLOR: requested Button color is absent or ambiguous in the captured existing palette; no palette entry created or edited')
    identity();click(matches[0])
    wait_until(lambda:_button_color(frame)[0]==desired,'Native embed palette color selection did not stick')


def _read_appearance(frame,reference):
    extras=set(reference)-LEGACY_APPEARANCE_FIELDS
    return _appearance(frame,extra_fields=extras,hidden_icon=reference.get('button_icon')) if extras else _appearance(frame)

def _write_appearance(frame,before,desired,identity):
    from playwright_recipes.skill6_playwright import click,fill,wait_until
    current,controls=_read_appearance(frame,before)
    if current!=before:
        raise Stop('Native button appearance changed after full preflight')
    if 'button_icon' in desired and desired['button_type']=='text':
        raise Stop('Icon changes require an explicit Icon + text or Icon only button type')
    if desired['linked'] and len(set(desired['corner_radii'].values()))!=1:
        raise Stop('Linked button corners require four equal authored radii')
    # Detach propagation while authoring explicit per-corner values, then
    # restore the requested local editing affordance. No global palette Save.
    corners_changed=before['corner_radii']!=desired['corner_radii']
    if before['linked'] and (corners_changed or not desired['linked']):
        identity();click(controls['linked'])
        wait_until(lambda:controls['linked'].get_attribute('aria-pressed')=='false',
                   'Native button corners did not unlink')
    for corner in CORNERS:
        if desired['corner_radii'][corner]!=before['corner_radii'][corner]:
            identity();fill(controls[corner],str(desired['corner_radii'][corner]))
    if desired['font_size']!=before['font_size']:
        identity();fill(controls['font_size'],str(desired['font_size']))
    for key,values in (('button_type',BUTTON_TYPES),('button_size',BUTTON_SIZES)):
        if desired[key]==before[key]:continue
        identity();click(controls[key])
        option=frame.locator('.n-base-select-option:visible').get_by_text(values[desired[key]],exact=True)
        click(_one(option,'Native button appearance option changed: '+key))
        wait_until(lambda:_appearance_select(frame,key,values)[0]==desired[key],
                   'Native button appearance option did not stick: '+key)
    now_linked=controls['linked'].get_attribute('aria-pressed')=='true'
    if now_linked!=desired['linked']:
        identity();click(controls['linked'])
        wait_until(lambda:controls['linked'].get_attribute('aria-pressed')==str(desired['linked']).lower(),
                   'Native button corner link state did not stick')
    if 'button_icon' in desired and (desired['button_icon']!=before['button_icon'] or desired['button_type']!=before['button_type']):
        _write_button_icon(frame,desired['button_type'],before['button_icon'],desired['button_icon'],identity)
    if 'button_color' in desired and desired['button_color']!=before['button_color']:
        _write_button_color(frame,before['button_color'],desired['button_color'],identity)
    if _read_appearance(frame,desired)[0]!=desired:
        raise Stop('Native button appearance did not match the complete desired and protected state')


def _layout_from_code(code):
    parser=_ExportParser();parser.feed(code);parser.close()
    return _layout_data(parser.tags[0][1].get('data-layout'))


def _preserved_layout(before,after,general_before,general_desired,appearance_before=None,appearance_desired=None):
    previous,current=_layout_from_code(before),_layout_from_code(after)
    allowed={'cornerRadius','fontSize','buttonType','buttonSize'}
    if (appearance_before is not None and appearance_desired is not None
            and appearance_before.get('button_color')!=appearance_desired.get('button_color')):allowed.add('buttonColor')
    if (appearance_before is not None and appearance_desired is not None
            and appearance_before.get('button_icon')!=appearance_desired.get('button_icon')):allowed.add('buttonIcon')
    if general_before['button_label']!=general_desired['button_label']:allowed.add('minimizedTitle')
    if general_before['position']!=general_desired['position']:allowed.update(('isLeftAligned','isRightAligned'))
    if general_before['width']!=general_desired['width']:allowed.add('formWidth')
    missing=object()
    if any(previous.get(key,missing)!=current.get(key,missing) for key in set(previous)|set(current) if key not in allowed):
        raise Stop('Button appearance export changed an unrequested native layout property')


def configure(page, step):
    """Configure local embed options, export twice, retain exact native code.

    Integrate generates a per-embed artifact. It has no captured persisted-save
    contract; this handler never clicks the form Save or claims persisted form
    settings. Reopening the code dialog verifies the generated artifact twice.
    """
    from playwright_recipes.skill6_playwright import click, fill, form_builder, wait_until
    from playwright_recipes.field_placement import _close_initial
    plan = validate(step); config = plan['integration']
    frame = form_builder(page)
    title = _one(frame.get_by_role('textbox', name='Form Name', exact=True), 'Native embed form title changed')
    expected_name = config['expected_form_name']
    if read_editor_title(title) != expected_name:
        raise Stop('Native embed form title differs from its inventoried identity')
    editor_url = page.url
    parsed = urlsplit(editor_url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/form-builder-v2/' +
                               re.escape(config['form_id']) + '/?', parsed.path)):
        raise Stop('Native embed editor does not belong to the exact inventoried form')
    def identity():
        if page.url != editor_url or title.count() != 1 or read_editor_title(title) != expected_name:
            raise Stop('Native embed form identity changed during configuration')
    _close_initial(frame)
    click(_one(frame.get_by_role('tab', name='Integrate', exact=True), 'Native form Integrate tab changed'))
    click(_one(frame.get_by_role('tab', name='Embed', exact=True), 'Native form Embed tab changed'))
    before = _read(frame)
    if any(before[key] != value for key, value in config['expected'].items()):
        raise Stop('Native embed settings differ from the inventoried previous values')
    desired = {**before, **config['changes']}
    layout_changed = desired['layout'] != before['layout']
    _supported_desired(config, desired, layout_changed=layout_changed)
    appearance_before=appearance_desired=appearance_export=None
    if 'appearance' in config:
        if layout_changed:
            raise Stop('Layout changes and button appearance require separate fully inventoried export jobs')
        authored=config['appearance']
        extras=set(authored['changes'])-LEGACY_APPEARANCE_FIELDS
        appearance_before,_=(_appearance(frame,extra_fields=extras,hidden_icon=authored['expected'].get('button_icon')) if extras else _appearance(frame))
        if any(appearance_before[key]!=value for key,value in authored['expected'].items()):
            raise Stop('Native button appearance differs from its inventoried previous values')
        appearance_desired={**deepcopy(appearance_before),**authored['changes']}
        _appearance_values(appearance_desired,complete=True)
        if 'button_icon' in appearance_desired and appearance_desired['button_type']=='text':
            raise Stop('Icon changes require an explicit Icon + text or Icon only button type')
        if appearance_desired['linked'] and len(set(appearance_desired['corner_radii'].values()))!=1:
            raise Stop('Linked button corners require four equal authored radii')
        appearance_export=_export(frame,config,before,appearance_before)
    if _read(frame) != before:
        raise Stop('Native embed settings changed after complete preflight')
    general, controls = _general(frame)
    if layout_changed:
        identity(); click(controls['layout'][desired['layout']])
        general, controls = _general(frame)
    for key in ('position', 'width', 'height', 'button_label'):
        if desired[key] is None or desired[key] == general[key]:
            continue
        identity()
        if key == 'position':
            click(controls[key][desired[key]])
        else:
            control = controls[key]
            fill(control, '' if desired[key] == 'Auto' else str(desired[key]))
    advanced, controls = _advanced(frame)
    for key in ('activation', 'trigger', 'deactivation'):
        if desired[key] != advanced[key]:
            identity(); click(controls[key][desired[key]])
    for key in NUMBERS:
        if desired[key] != advanced[key]:
            identity()
            if not controls[key].is_enabled():
                raise Stop('Native embed number remains disabled after its explicit choice')
            fill(controls[key], str(desired[key]))
    if desired['respect_cookie_consent'] != advanced['respect_cookie_consent']:
        identity(); click(controls['respect_cookie_consent'])
    wait_until(lambda: _read(frame) == desired, 'Native embed options did not settle to the complete expected state')
    if appearance_desired is not None:
        _write_appearance(frame,appearance_before,appearance_desired,identity)
    identity()
    first = _export(frame, config, desired,appearance_desired) if appearance_desired is not None else _export(frame,config,desired)
    identity()
    second = _export(frame, config, desired,appearance_desired) if appearance_desired is not None else _export(frame,config,desired)
    if first != second or _read(frame) != desired or (appearance_desired is not None and _read_appearance(frame,appearance_desired)[0]!=appearance_desired):
        raise Stop('Native embed export changed during independent second code-dialog readback')
    if appearance_export is not None:
        _preserved_layout(appearance_export['embed_code'],first['embed_code'],before,desired,appearance_before,appearance_desired)
    return {'status':'FORM_EMBED_EXPORTED_AND_REREAD', 'kind':'form_embed',
        'editor_url':editor_url, 'form_id':config['form_id'],
        'configuration_sha256':configuration_hash(plan), 'export_settings':desired, **first,
        **({'appearance_settings':appearance_desired} if appearance_desired is not None else {}),
        'independent_readback':'VERIFIED', 'settings_persisted':False,
        'installation_verified':False, 'behavior_verified':False, 'submission_verified':False}


def validate_receipt(result, step):
    """Re-derive every retained export binding for journal replay."""
    plan = validate(step); config = plan['integration']
    if (not isinstance(result, dict) or result.get('status') != 'FORM_EMBED_EXPORTED_AND_REREAD'
            or result.get('kind') != 'form_embed' or result.get('form_id') != config['form_id']
            or result.get('configuration_sha256') != configuration_hash(plan)
            or result.get('independent_readback') != 'VERIFIED'
            or any(result.get(key) is not False for key in (
                'settings_persisted', 'installation_verified', 'behavior_verified', 'submission_verified'))):
        raise Stop('Native embed receipt status, input binding or pending proof flags differ')
    settings = result.get('export_settings')
    if (not isinstance(settings, dict) or set(settings) != GENERAL | ADVANCED
            or any(settings[key] != value for key, value in config['changes'].items())):
        raise Stop('Native embed receipt differs from the complete authored export settings')
    _properties(settings)
    _supported_desired(config, settings, layout_changed=(
        'layout' in config['changes'] and config['expected']['layout'] != config['changes']['layout']))
    appearance=result.get('appearance_settings')
    if 'appearance' in config:
        _appearance_values(appearance,complete=True)
        if (not (set(config['appearance']['changes'])-LEGACY_APPEARANCE_FIELDS).issubset(appearance)
                or settings['layout']=='Standard'
                or 'button_icon' in appearance and appearance['button_type']=='text'
                or any(appearance[key]!=value for key,value in config['appearance']['changes'].items())
                or appearance['linked'] and len(set(appearance['corner_radii'].values()))!=1):
            raise Stop('Native embed appearance receipt differs from its authored configuration')
    elif appearance is not None:
        raise Stop('Unrequested button appearance receipt cannot be retained')
    verified = verify_export_configuration(result.get('embed_code'), config, settings, appearance)
    if result.get('embed_sha256') != verified['embed_sha256']:
        raise Stop('Native embed receipt code hash differs from its exact native bytes')
    return {**verified, 'export_settings':deepcopy(settings),
            **({'appearance_settings':deepcopy(appearance)} if appearance is not None else {})}
