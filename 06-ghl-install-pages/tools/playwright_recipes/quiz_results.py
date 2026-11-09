"""Captured marketing-quiz business-name visibility/copy and tier-specific CTA copy.

Native UI Modal, Header and Call to action controls captured November 9, 2026.
This edits caller-authored plain text/HTTPS links only. It never changes the
dynamic-content mode or score source, sends a submission, or publishes a quiz.
"""
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop, click, fill, wait_until
    from .assessments import reopen_editor
else:
    from skill6_playwright import Stop, click, fill, wait_until
    from assessments import reopen_editor


HEADER_FIELDS = {'business_name', 'business_name_enabled', 'header_layout'}
CTA_FIELDS = {'cta_content', 'cta_button_text', 'cta_url'}
CTA_TEXT = 'Enter button text (e.g., Subscribe, Learn More)'
CTA_URL = 'Enter URL (e.g., https://www.example.com)'
CTA_SOURCE_SELECTOR = None  # Optional exact native wrapper ID, when present in a capture.


def _plain(value):
    if not isinstance(value, str) or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise Stop('Quiz result copy requires explicit plain text')
    return value.replace('\r\n', '\n').replace('\r', '\n').strip()


def _https(value):
    value = _plain(value)
    if not value or any(c.isspace() or ord(c) == 127 for c in value):
        raise Stop('Quiz CTA destination requires an explicit HTTPS URL')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise Stop('Quiz CTA destination is malformed') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or (port is not None and not 1 <= port <= 65535)):
        raise Stop('Quiz CTA destination must be HTTPS without credentials')
    return value


def _pair(expected, changes, allowed):
    if (not isinstance(expected, dict) or not isinstance(changes, dict)
            or not changes or set(expected) != set(changes) or set(changes) - allowed):
        raise Stop('Each result-copy edit requires the exact same previous/authored field keys')
    for key in changes:
        if key == 'header_layout':
            if any(type(value) is not str or value not in ('Default','Reverse')
                   for value in (expected[key],changes[key])):
                raise Stop('Header layout requires exact previous and desired Default/Reverse names')
            continue
        if key == 'business_name_enabled':
            if type(expected[key]) is not bool or type(changes[key]) is not bool:
                raise Stop('Business-name visibility requires exact previous and desired Boolean values')
            continue
        expected[key] = _plain(expected[key])
        changes[key] = _https(changes[key]) if key == 'cta_url' else _plain(changes[key])
        if key in ('business_name', 'cta_button_text') and not changes[key]:
            raise Stop('Authored business name and CTA button text must be nonempty')


def validate(step):
    if (not isinstance(step, dict) or set(step) - {'id', 'action', 'result_page'}
            or step.get('action', 'quiz_results') != 'quiz_results'):
        raise Stop('Unsupported marketing-quiz result runner metadata')
    result = deepcopy(step)
    config = result.get('result_page')
    if (not isinstance(config, dict) or not config
            or set(config) - {'expected', 'changes', 'cta_context', 'cta_variants'}):
        raise Stop('Unsupported marketing-quiz result-page controls')
    if 'expected' in config or 'changes' in config:
        _pair(config.get('expected'), config.get('changes'), HEADER_FIELDS)
    variants = config.get('cta_variants')
    context = config.get('cta_context')
    if variants is not None or context is not None:
        if not isinstance(context, dict) or type(context.get('dynamic')) is not bool:
            raise Stop('CTA edits require the exact expected dynamic-content context')
        if context['dynamic']:
            if set(context) != {'dynamic', 'score_source'} or not _plain(context['score_source']):
                raise Stop('Dynamic CTA edits require the exact existing score source')
            context['score_source'] = _plain(context['score_source'])
        elif set(context) != {'dynamic'}:
            raise Stop('Static CTA edits must not carry ignored category/tier inputs')
        if not isinstance(variants, list) or not variants:
            raise Stop('CTA edits require at least one exact existing content variant')
        if not context['dynamic'] and len(variants) != 1:
            raise Stop('Static CTA content has one variant')
        tiers = set()
        for variant in variants:
            allowed = {'expected', 'changes', 'tier'} if context['dynamic'] else {'expected', 'changes'}
            if not isinstance(variant, dict) or set(variant) != allowed:
                raise Stop('CTA variant requires exact target and previous/authored values')
            if context['dynamic']:
                tier = _plain(variant['tier'])
                if not tier or tier in tiers:
                    raise Stop('Dynamic CTA tiers must be explicit and unique')
                tiers.add(tier)
                variant['tier'] = tier
            _pair(variant['expected'], variant['changes'], CTA_FIELDS)
    if not config.get('changes') and not variants:
        raise Stop('No result-copy changes requested')
    return result


def configuration_hash(step):
    value = validate(step)
    return hashlib.sha256(json.dumps(value['result_page'], sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _one(control, message):
    if control.count() != 1 or not control.is_visible():
        raise Stop(message)
    return control


def _pane(modal, label):
    # Native result navigation uses paragraphs, rather than tab/button roles.
    item = modal.locator('p:not(.tiptap *)').filter(
        has_text=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
    click(_one(item, 'Native quiz result sidebar changed: ' + label))


def _rte(modal):
    return _one(modal.locator('.tiptap.ProseMirror[contenteditable="true"]:visible'),
                'Quiz result plain-text editor is missing or ambiguous')


def _toggle(modal):
    control = _one(modal.get_by_role('switch', name='toggle', exact=True),
                   'Quiz result context switch changed')
    value = control.get_attribute('aria-checked')
    if value not in ('true', 'false'):
        raise Stop('Quiz result context switch state is unavailable')
    return value == 'true'


def _header(modal):
    _pane(modal, 'Header')
    # This switch controls only the business name. The logo/layout remain
    # independent Header controls. The RTE stays visible with this switch off.
    label = modal.locator('.switch-handle').filter(
        has_text=re.compile(r'^\s*Business\s*name\s*$'))
    _one(label, 'Native Header Business name switch label changed')
    _,layout = _layout_controls(modal)
    return {'business_name':_plain(_rte(modal).inner_text()),
            'business_name_enabled':_toggle(modal), 'header_layout':layout}


def _layout_controls(modal):
    heading = modal.get_by_text(re.compile(r'^\s*Header\s*layout\s*$'))
    _one(heading, 'Native Header layout label is missing or ambiguous')
    cards = modal.locator('div.flex.w-full.cursor-pointer.flex-col.items-center')
    if cards.count() != 2:
        raise Stop('Native Header layout card inventory changed')
    baseline = {'flex','h-8','w-full','items-center','justify-center','gap-2',
        'rounded-lg','border','border-gray-300','px-6','py-[18px]','pl-3',
        'font-medium','text-gray-700','transition-colors','duration-200'}
    controls,selected = {},[]
    for name in ('Default','Reverse'):
        card = cards.filter(has=modal.get_by_text(name,exact=True))
        _one(card, 'Native Header layout card is absent or ambiguous: '+name)
        label = _one(card.get_by_text(name,exact=True), 'Native Header layout text changed')
        classes = set((label.get_attribute('class') or '').split())
        if not baseline.issubset(classes):
            raise Stop('Native Header layout card shape changed')
        if 'layout-card-active' in classes:
            if not {'bg-gray-100','text-primary-700'}.issubset(classes):
                raise Stop('Native Header selected-layout classes changed')
            selected.append(name)
        controls[name] = card
    if len(selected) != 1:
        raise Stop('Native Header layout selection is missing or ambiguous')
    return controls,selected[0]


def _header_logo(modal):
    # Read-only preservation of captured Header logo fields. No URL is fetched
    # and no image chooser or uploader is opened by a layout edit.
    image = _one(modal.locator('#bgImage[name="bgImage"]'), 'Native Header logo URL control changed')
    sizes = modal.get_by_role('textbox',name='Please Input',exact=True)
    if sizes.count() != 2:
        raise Stop('Native Header logo width/height control inventory changed')
    return {'url':image.input_value(), 'width':sizes.nth(0).input_value(),
            'height':sizes.nth(1).input_value()}


def _cta_context(modal, context):
    _pane(modal, 'Call to action')
    if _toggle(modal) != context['dynamic']:
        raise Stop('Native CTA dynamic-content mode differs from the expected context')
    if context['dynamic']:
        if CTA_SOURCE_SELECTOR is not None:
            source = _one(modal.locator(CTA_SOURCE_SELECTOR), 'Native CTA score-source selector changed')
        else:
            # The captured score-source paragraph and native select family are
            # semantic anchors. Bind their smallest actual DOM container rather
            # than guessing an unobserved ID or indexing the six modal selects.
            label = _one(modal.locator('p:not(.tiptap *)').filter(
                has_text=re.compile(r'^\s*Dynamic content is based on\s*$')),
                'Native CTA score-source label changed')
            parent = label
            source = None
            for _ in range(5):
                parent = parent.locator('..')
                selects = parent.locator('.n-select:visible')
                if parent.locator('#dynamic-content-tier').count() or selects.count() > 1:
                    raise Stop('CTA score-source container includes another native select')
                if selects.count() == 1:
                    source = _one(selects.locator('.n-base-selection'),
                                  'Native CTA score-source value changed')
                    break
            if source is None:
                raise Stop('Native CTA score-source label has no unique related select')
        if source.inner_text().strip() != context['score_source']:
            raise Stop('CTA copy belongs to another score-source context')


def _tier(frame, modal, variant, context):
    _cta_context(modal, context)
    if not context['dynamic']:
        return
    selected = _one(modal.locator('#dynamic-content-tier .n-base-selection'),
                    'Native CTA editing-tier selector changed')
    if selected.inner_text().strip() != variant['tier']:
        click(selected)
        option = frame.locator('.n-base-select-option:visible').get_by_text(variant['tier'], exact=True)
        click(_one(option, 'Requested existing CTA tier is absent or ambiguous'))
    wait_until(lambda: selected.inner_text().strip() == variant['tier'],
               'Native CTA editing tier did not change')


def _cta_values(modal):
    text = _one(modal.get_by_placeholder(CTA_TEXT, exact=True), 'Native CTA button-text input changed')
    url = _one(modal.get_by_placeholder(CTA_URL, exact=True), 'Native CTA destination input changed')
    return {'cta_content':_plain(_rte(modal).inner_text()),
            'cta_button_text':_plain(text.input_value()), 'cta_url':_plain(url.input_value())}


def _write(modal, key, value):
    if key == 'header_layout':
        controls,current = _layout_controls(modal)
        if current != value:
            click(controls[value])
            wait_until(lambda:_layout_controls(modal)[1] == value,
                       'Native Header layout did not select the authored card')
        return
    if key == 'business_name_enabled':
        control = _one(modal.get_by_role('switch', name='toggle', exact=True),
                       'Native Header Business name switch changed')
        if not control.is_enabled():
            raise Stop('Native Header Business name switch is disabled')
        if _toggle(modal) != value:
            click(control)
            wait_until(lambda:_toggle(modal) == value, 'Native business-name visibility did not change')
        return
    if key in ('business_name', 'cta_content'):
        control = _rte(modal)
    else:
        control = _one(modal.get_by_placeholder(CTA_TEXT if key == 'cta_button_text' else CTA_URL, exact=True),
                       'Native CTA authored-value input changed')
    fill(control, value)
    control.press('Tab')
    current = _plain(control.inner_text()) if key in ('business_name', 'cta_content') else _plain(control.input_value())
    if current != value:
        raise Stop('Native quiz result editor ignored an authored value')


def configure(page, step):
    plan = validate(step)
    config = plan['result_page']
    editor_url = page.url
    parsed = urlsplit(editor_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.port not in (None, 443)
            or not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/quiz-builder-v2/[A-Za-z0-9_-]+/?', parsed.path)):
        raise Stop('Result-copy editor must be an exact native marketing quiz URL')
    frame = page.frame_locator('iframe[name="quiz-builder-app"]')
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    name = title.input_value()
    if not isinstance(name, str) or not name.strip():
        raise Stop('Quiz identity is unavailable before result-copy editing')

    def identity():
        if page.url != editor_url or title.input_value() != name:
            raise Stop('Quiz identity changed during result-copy editing')

    def open_results():
        identity()
        existing = frame.get_by_role('dialog')
        if existing.count():
            if (existing.count() != 1
                    or existing.get_by_text('Form Element', exact=True).count()
                       + existing.get_by_text('Quiz Element', exact=True).count() != 1):
                raise Stop('Unexpected quiz modal requires reconciliation before result-copy edits')
            close = existing.get_by_role('button', name='Close', exact=True)
            click(_one(close, 'Native initial quiz drawer close control changed'))
        click(frame.get_by_role('button', name='Edit Template', exact=True))
        modal = frame.get_by_role('dialog', name='UI Modal', exact=True)
        modal.get_by_text('Customise result page', exact=True).wait_for(state='visible', timeout=45000)
        _one(modal, 'Native quiz result modal is ambiguous')
        return modal

    modal = open_results()
    header_before = _header(modal) if config.get('changes') else None
    preserve_header_markup = (header_before is not None
        and bool({'business_name_enabled','header_layout'}.intersection(config['changes']))
        and 'business_name' not in config['changes'])
    header_markup = _rte(modal).inner_html() if preserve_header_markup else None
    header_logo = _header_logo(modal) if header_before is not None and 'header_layout' in config['changes'] else None
    if preserve_header_markup and not isinstance(header_markup, str):
        raise Stop('Business-name stored markup is unavailable before visibility editing')
    if (header_before is not None and 'business_name_enabled' in config['changes']
            and header_before['business_name_enabled'] != config['changes']['business_name_enabled']
            and not _one(modal.get_by_role('switch',name='toggle',exact=True),
                         'Native Header Business name switch changed').is_enabled()):
        raise Stop('Native Header Business name switch is disabled before result editing')
    if header_before is not None and any(header_before[key] != value for key, value in config['expected'].items()):
        raise Stop('Quiz header copy differs from the inventoried previous values')
    variant_before = []
    for variant in config.get('cta_variants', []):
        _tier(frame, modal, variant, config['cta_context'])
        before = _cta_values(modal)
        if any(before[key] != value for key, value in variant['expected'].items()):
            raise Stop('CTA copy differs from the expected score/tier-specific previous values')
        variant_before.append(before)
    # Every requested native target has now been read before the first copy write.
    if header_before is not None:
        _header(modal)
        for key, value in config['changes'].items():
            identity()
            if header_before[key] != value:
                _write(modal, key, value)
        if _header(modal) != {**header_before, **config['changes']}:
            raise Stop('Quiz header desired state did not stick before Save')
    for variant, before in zip(config.get('cta_variants', []), variant_before):
        _tier(frame, modal, variant, config['cta_context'])
        for key, value in variant['changes'].items():
            identity()
            if before[key] != value:
                _write(modal, key, value)
        if _cta_values(modal) != {**before, **variant['changes']}:
            raise Stop('CTA desired state or untouched copy changed before Save')
    if header_before is not None and _header(modal) != {**header_before, **config['changes']}:
        raise Stop('Another result-copy edit changed the requested business name before Save')
    for variant, before in zip(config.get('cta_variants', []), variant_before):
        _tier(frame, modal, variant, config['cta_context'])
        if _cta_values(modal) != {**before, **variant['changes']}:
            raise Stop('Another tier edit changed a previously authored CTA before Save')
    if preserve_header_markup:
        _header(modal)
        if _rte(modal).inner_html() != header_markup:
            raise Stop('Header controls changed protected stored markup before Save')
    if header_logo is not None:
        _header(modal)
        if _header_logo(modal) != header_logo:
            raise Stop('Header layout changed protected logo URL/width/height before Save')
    identity()
    save = _one(modal.get_by_role('button', name='Save', exact=True), 'Native result-modal Save changed')
    if not save.is_enabled():
        raise Stop('Native result-copy configuration remains invalid; Save not attempted')
    click(save)
    modal.wait_for(state='hidden', timeout=45000)
    click(frame.get_by_role('button', name='Save', exact=True))
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).count() == 1
               and frame.get_by_role('button', name='Save', exact=True).is_enabled(),
               'Quiz result outer Save did not finish')
    reopen_editor(page, 'quiz', name, editor_url)
    title = frame.get_by_role('textbox', name='Form Name', exact=True)
    title.wait_for(state='visible', timeout=45000)
    modal = open_results()
    if header_before is not None and _header(modal) != {**header_before, **config['changes']}:
        raise Stop('Quiz header copy did not persist after independent reopen')
    if preserve_header_markup and _rte(modal).inner_html() != header_markup:
        raise Stop('Business-name stored markup changed after independent reopen')
    if header_logo is not None and _header_logo(modal) != header_logo:
        raise Stop('Header logo URL/width/height changed after independent reopen')
    for variant, before in zip(config.get('cta_variants', []), variant_before):
        _tier(frame, modal, variant, config['cta_context'])
        if _cta_values(modal) != {**before, **variant['changes']}:
            raise Stop('CTA copy did not persist for the requested score/tier context')
    click(modal.get_by_role('button', name='Cancel', exact=True))
    modal.wait_for(state='hidden', timeout=45000)
    return {'status':'QUIZ_RESULTS_SAVED_AND_REOPENED', 'kind':'quiz_results',
            'editor_url':page.url, 'configuration_sha256':configuration_hash(plan),
            'independent_readback':'VERIFIED', 'behavior_verified':False,
            'submission_verified':False}
