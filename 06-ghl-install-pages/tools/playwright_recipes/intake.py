"""Reject unimplemented or discarded recipe requests before browser acquisition."""

if __package__:
    from .skill6_playwright import Stop
else:
    from skill6_playwright import Stop


COMMON = {'location_id', 'location_name', 'start_url', 'auth_activation', 'publish'}
CONTAINER = {'container_name', 'page_name', 'path', 'file', 'marker', 'code_id', 'seo'}
CODE = {'file', 'marker', 'code_id', 'append', 'element_id', 'expected_name', 'section_id', 'seo'}
CHECKOUT = {'page_id', 'step_id', 'component_id', 'tab_id', 'frame_name', 'adapter_capture',
            'checkout_contract', 'family', 'main_price', 'bumps', 'field_states',
            'purchase_action', 'funnel_id', 'charge', 'execute_payment'}
FIELDS = {
    **{name: CONTAINER for name in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page')},
    'pages.install_code': CODE, 'pages.install_embed': CODE | {'embed_receipt'},
    'pages.seo': {'seo'},
    'checkout.wrap_native': {'before_file', 'before_marker', 'checkout', 'after_file', 'after_marker', 'seo'},
    'checkout.configure_native': CHECKOUT,
    'checkout.one_click_upsell': CHECKOUT,
    'checkout.configure_ui': {'element_id', 'expected_name', 'section_id', 'mode', 'products',
        'contact_fields', 'checkout_options', 'content', 'theme_inputs', 'legal_copy',
        'product_binding', 'product_id', 'price_id', 'charge', 'execute_payment'},
    'forms.create': {'name', 'required', 'allow_creation', 'radius'},
    'forms.configure': {'fields', 'add_fields', 'address_fields', 'consent', 'object_fields', 'field_dependencies'},
    'forms.style': {'custom_css', 'radius', 'css_key', 'expect_styles'},
    'forms.settings': {'settings', 'schedule', 'tracking'},
    'forms.submission': {'submission'}, 'forms.notifications': {'notifications'},
    'forms.conditions': {'condition'},
    'surveys.create': {'name', 'allow_creation', 'standard_fields'},
    'quizzes.create': {'name', 'allow_creation', 'standard_fields', 'fixture'},
    'surveys.configure': {'configuration'}, 'quizzes.configure': {'configuration'},
    'communities.create': {'community'},
    'communities.configure': {'portal_url', 'group_name', 'channels', 'details', 'access'},
    'meetings.setup': {'meeting'}, 'meetings.update': {'meeting'},
    'meetings.integrate': {'integration_mode'},
    'courses.configure_ui': {'course_id', 'template_id', 'expected_template_title', 'changes', 'expected_values', 'custom_blocks'},
    'funnels.split_variant': set(),
}
REQUIRED = {
    **{name: {'container_name', 'page_name', 'path'} for name in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page')},
    'pages.install_code': {'file', 'marker', 'seo'},
    'pages.install_embed': {'file', 'marker', 'seo', 'embed_receipt'},
    'pages.seo': {'seo'},
    'checkout.wrap_native': {'before_file', 'before_marker', 'seo'},
    'forms.create': {'name'}, 'forms.submission': {'submission'},
    'forms.notifications': {'notifications'}, 'forms.conditions': {'condition'},
    'surveys.create': {'name'}, 'quizzes.create': {'name'},
    'surveys.configure': {'configuration'}, 'quizzes.configure': {'configuration'},
    'communities.create': {'community'}, 'meetings.setup': {'meeting'}, 'meetings.update': {'meeting'},
}


def validate_intake(operation, data):
    if not isinstance(data, dict):
        raise Stop('Recipe inputs must be a JSON object')
    if 'publish' in data and data['publish'] is not False:
        raise Stop('Recipe scripts save drafts; publishing requires its existing separate operation')
    for flag in ('allow_creation', 'append', 'fixture'):
        if flag in data and type(data[flag]) is not bool:
            raise Stop(flag + ' requires a real boolean')
    if operation not in FIELDS:
        return  # API-only and unknown operations retain their explicit dispatch refusal.
    unknown = set(data) - COMMON - FIELDS[operation] - {'options'}
    if unknown:
        raise Stop('Unsupported recipe inputs require an implementation: ' + ', '.join(sorted(unknown)))
    missing = (REQUIRED.get(operation, set()) | {'location_id', 'location_name', 'start_url'}) - set(data)
    if operation in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page'):
        if data.get('file'):
            missing |= {'marker', 'seo'} - set(data)
        elif set(data).intersection({'marker', 'code_id', 'seo'}):
            raise Stop('Code/SEO inputs require the corresponding HTML file')
    if operation == 'checkout.wrap_native':
        if data.get('after_file'):
            missing |= {'after_marker'} - set(data)
        elif 'after_marker' in data:
            raise Stop('after_marker requires after_file')
    if operation == 'checkout.one_click_upsell' and not data.get('adapter_capture'):
        unused = set(data).intersection(CHECKOUT - {'checkout_contract'})
        if unused:
            raise Stop('Native checkout inputs require their captured adapter: ' + ', '.join(sorted(unused)))
    if operation == 'communities.configure' and not set(data).intersection({'channels', 'details', 'access'}):
        if set(data).intersection({'portal_url', 'group_name'}):
            raise Stop('Portal identity requires a concrete channel or details operation')
    if missing:
        raise Stop('Missing required recipe inputs: ' + ', '.join(sorted(missing)))
    if operation == 'courses.configure_ui':
        native = set(data).intersection(FIELDS[operation])
        if native and 'options' in data:
            raise Stop('Native course theme edits and recorded options require separate jobs')
        if native:
            if 'custom_blocks' in data:
                from playwright_recipes.course_blocks import validate_inputs
            else:
                from playwright_recipes.course_theme import validate_inputs
            validate_inputs(data)
    for key in ('seo', 'checkout', 'configuration', 'submission', 'notifications', 'community', 'meeting', 'options'):
        if key in data and (not isinstance(data[key], dict)
                or set(data[key]).intersection({'action', '_context'})):
            raise Stop(key + ' must be a configuration object without runner-owned metadata')
    if 'options' in data and not data['options']:
        raise Stop('Explicit options must contain a captured executable profile')
    if operation == 'communities.create' and 'options' in data:
        raise Stop('Community creation must reconcile its native identity before a separate portal operation')
    for nested in ('community', 'meeting'):
        for flag in ('allow_creation', 'inactive', 'discovery'):
            if nested in data and flag in data[nested] and type(data[nested][flag]) is not bool:
                raise Stop(nested + '.' + flag + ' requires a real boolean')
    if operation == 'forms.configure':
        for key in ('fields', 'add_fields', 'address_fields', 'object_fields'):
            if key in data and (not isinstance(data[key], list) or not data[key]):
                raise Stop(key + ' must be a nonempty list when supplied')
        if ('object_fields' in data) != ('field_dependencies' in data):
            raise Stop('Native object fields require their matching API dependency inventory')
        if 'object_fields' in data:
            from playwright_recipes.forms_advanced import validate_object_fields
            validate_object_fields({'payload':{key:data[key] for key in (
                'location_id', 'location_name', 'start_url', 'object_fields', 'field_dependencies')}})
        if 'consent' in data:
            from playwright_recipes.forms_advanced import validate_consent
            validate_consent({'consent':data['consent']})
        if 'address_fields' in data:
            from playwright_recipes.forms_advanced import validate
            validate({'address_fields':data['address_fields']})
    if operation == 'forms.style' and 'custom_css' not in data and set(data).intersection({'css_key', 'expect_styles'}):
        raise Stop('CSS identity and render checks require custom_css')
    if operation == 'surveys.configure' and isinstance(data.get('configuration'), dict):
        config = data['configuration']
        if set(config).intersection({'object_fields', 'field_dependencies'}):
            if set(config).intersection({'location_id', 'location_name', 'start_url'}):
                raise Stop('Survey object-field owner identity must come from its parent inputs')
            if 'rules' in config:
                raise Stop('Survey object questions and conditional rule stacks require separate jobs')
            from playwright_recipes.survey_fields import validate
            validate({'payload':{**{key:data[key] for key in ('location_id', 'location_name', 'start_url')}, **config}})
    if operation == 'communities.configure':
        if len(set(data).intersection({'channels', 'details', 'access'})) > 1:
            raise Stop('Community channels, details and access require separately journaled jobs')
        if set(data).intersection({'channels', 'details', 'access'}) and 'options' in data:
            raise Stop('Concrete community operations and generic options require separate jobs')
    if operation in ('meetings.setup', 'meetings.update') and 'cohosts' in data['meeting']:
        if 'options' in data:
            raise Stop('Co-host roster reconciliation and recorded options require separate jobs')
    if operation == 'meetings.integrate' and data.get('integration_mode') is not None:
        raise Stop('Native calendar API integration must use the measured API host route')
