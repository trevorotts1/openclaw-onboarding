"""Reject unimplemented or discarded recipe requests before browser acquisition."""
from collections.abc import Mapping

if __package__:
    from .skill6_playwright import Stop
else:
    from skill6_playwright import Stop


COMMON = {'location_id', 'location_name', 'start_url', 'auth_activation', 'publish'}
CONTAINER = {'container_name', 'page_name', 'path', 'file', 'marker', 'code_id', 'seo', 'placement'}
CODE = {'file', 'marker', 'code_id', 'append', 'element_id', 'expected_name', 'section_id', 'seo', 'placement'}
CHECKOUT = {'page_id', 'step_id', 'component_id', 'tab_id', 'frame_name', 'adapter_capture',
            'checkout_contract', 'family', 'main_price', 'bumps', 'field_states',
            'purchase_action', 'funnel_id', 'charge', 'execute_payment'}
FIELDS = {
    **{name: CONTAINER for name in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page')},
    'pages.install_code': CODE, 'pages.install_embed': CODE | {'embed_receipt', 'embed_config', 'embed_placement'},
    'pages.seo': {'seo'}, 'pages.layout': {'layout'}, 'pages.responsive': {'responsive'}, 'pages.saved_section': {'saved_section'},
    'checkout.wrap_native': {'before_file', 'before_marker', 'checkout', 'after_file', 'after_marker', 'seo', 'before_placement', 'after_placement'},
    'checkout.configure_native': CHECKOUT,
    'checkout.one_click_upsell': CHECKOUT,
    'checkout.configure_ui': {'page_id', 'element_id', 'expected_name', 'section_id', 'mode', 'products',
        'contact_fields', 'checkout_options', 'content', 'theme_inputs', 'theme_profile', 'theme_preset', 'theme_typography', 'theme_colors', 'contact_field_order', 'legal_copy',
        'product_binding', 'product_id', 'price_id', 'charge', 'execute_payment'},
    'forms.create': {'name', 'required', 'allow_creation', 'radius'},
    'forms.configure': {'address_parent', 'widget_fields', 'fields', 'add_fields', 'address_fields', 'consent', 'object_fields', 'dropdown_fields', 'large_text_fields', 'field_dependencies', 'integration', 'contact_field_plan'},
    'forms.style': {'custom_css', 'radius', 'css_key', 'expect_styles'},
    'forms.settings': {'settings', 'schedule', 'tracking'},
    'forms.submission': {'submission'}, 'forms.notifications': {'notifications'},
    'forms.conditions': {'condition'},
    'surveys.create': {'name', 'allow_creation', 'standard_fields', 'radio_questions', 'target_slide', 'question_batches', 'slide_count'},
    'quizzes.create': {'name', 'allow_creation', 'standard_fields', 'fixture', 'configuration'},
    'surveys.configure': {'configuration'}, 'quizzes.configure': {'configuration'},
    'communities.create': {'community'},
    'communities.configure': {'portal_url', 'group_name', 'channels', 'details', 'access', 'course_associations', 'api_capability', 'branding'},
    'meetings.setup': {'meeting'}, 'meetings.update': {'meeting'},
    'meetings.integrate': {'integration_mode', 'calendar_id', 'calendar_name', 'staff_id', 'staff_name', 'provider', 'connection_staff_label', 'expected_staff_locations', 'staff_dependency', 'portal_url', 'group_name', 'group_id', 'event_id', 'allow_room_creation', 'expected', 'product_id', 'session_name', 'description', 'instructor_name', 'date', 'start_time', 'end_time', 'timezone', 'allow_creation'},
    'courses.configure_ui': {'course_id', 'template_id', 'expected_template_title', 'changes', 'expected_values', 'custom_blocks', 'background_image', 'background_transparency', 'background_removal', 'custom_block_image', 'text_blocks', 'theme_images', 'image_blocks', 'video_blocks'},
    'funnels.split_variant': {'funnel_id', 'step_id', 'funnel_name', 'page_name', 'step_url',
        'control_page_id', 'expected_variant_id', 'allow_creation', 'expected_control_traffic',
        'control_traffic', 'expected_active', 'active', 'traffic_change_authorized'},
}
REQUIRED = {
    **{name: {'container_name', 'page_name', 'path'} for name in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page')},
    'pages.install_code': {'file', 'marker', 'seo'},
    'pages.install_embed': {'file', 'marker', 'seo', 'embed_receipt'},
    'pages.seo': {'seo'}, 'pages.layout': {'layout'}, 'pages.responsive': {'responsive'}, 'pages.saved_section': {'saved_section'},
    'checkout.wrap_native': {'before_file', 'before_marker', 'seo'},
    'forms.create': {'name'}, 'forms.submission': {'submission'},
    'forms.notifications': {'notifications'}, 'forms.conditions': {'condition'},
    'surveys.create': {'name'}, 'quizzes.create': {'name'},
    'surveys.configure': {'configuration'}, 'quizzes.configure': {'configuration'},
    'communities.create': {'community'}, 'meetings.setup': {'meeting'}, 'meetings.update': {'meeting'},
}


QUIZ_CREATION = {
    'picture_choice_questions': ('quiz_picture_choices', 'quiz_picture_questions'),
    'short_answer_questions': ('quiz_short_answers', 'quiz_text_questions'),
    'multiple_choice_questions': ('quiz_multiple_choices', 'quiz_choice_questions'),
    'written_answer_questions': ('quiz_written_answers', 'quiz_written_questions'),
}


def captured_script_mode(operation, inputs):
    """Every registered editor schema owns native proof by default.

    API-owned course/media/outline operations are outside FIELDS. The one mixed
    schema has an explicit permanent-link API mode; no broad capability can
    silently convert any other editor recipe into an API/provider completion.
    """
    return operation in FIELDS and not (
        operation == 'meetings.integrate' and isinstance(inputs, Mapping)
        and inputs.get('integration_mode') == 'permanent_calendar_link')


def condition_request(value):
    if not isinstance(value, dict):
        raise Stop('Native form condition must be a configuration object')
    condition = dict(value)
    if 'action' in condition:
        effect = condition.pop('action')
        if effect not in ('Hide Field','Show Field') or condition.get('effect',effect) != effect:
            raise Stop('Conflicting or uncaptured native condition effect')
        condition['effect'] = effect
    if 'rules' in condition:
        rules = condition['rules']
        if (not isinstance(rules,list) or not rules and 'expected_rules' not in condition
                or any(not isinstance(rule,dict) for rule in rules)):
            raise Stop('Native conditions require a complete ordered rule list; clearing also needs the full expected inventory')
        expected = condition.get('expected_rules', [])
        if not isinstance(expected,list) or any(not isinstance(rule,dict) for rule in expected):
            raise Stop('Expected native conditions require a complete ordered rule inventory')
        outcomes = any(rule.get('effect') not in ('Hide Field','Show Field') for rule in rules + expected)
        if outcomes:
            from playwright_recipes.form_condition_outcomes import validate
            action = 'native_condition_outcomes'
        else:
            from playwright_recipes.form_condition_stack import validate
            action = 'native_condition_stack'
    elif 'clauses' in condition:
        from playwright_recipes.form_conditions import validate
        action = 'native_condition_group'
    else:
        from playwright_recipes.assessments import validate_condition as validate
        action = 'native_condition'
    validate({'action':action, **condition})
    return action, condition


def quiz_creation(data):
    """Bind an exclusive native creation request to its exact parent owner."""
    config = data['configuration']
    keys = set(config).intersection(QUIZ_CREATION)
    if not keys:
        return None
    if len(keys) != 1 or set(config) != keys or 'options' in data:
        raise Stop('Native quiz question creation requires its own independently journaled job')
    key = next(iter(keys))
    value = config[key]
    if not isinstance(value, dict) or set(value).intersection({'location_id', 'location_name', 'start_url'}):
        raise Stop('Quiz question owner identity belongs to parent inputs')
    action, module = QUIZ_CREATION[key]
    payload = {**{name:data[name] for name in ('location_id','location_name','start_url')}, **value}
    native = __import__('playwright_recipes.' + module, fromlist=['validate'])
    native.validate({'action':action, 'payload':payload})
    return action, payload


def validate_intake(operation, data):
    if not isinstance(data, dict):
        raise Stop('Recipe inputs must be a JSON object')
    if 'publish' in data and data['publish'] is not False:
        raise Stop('Recipe scripts save drafts; publishing requires its existing separate operation')
    for flag in ('allow_creation', 'append', 'fixture'):
        if flag in data and type(data[flag]) is not bool:
            raise Stop(flag + ' requires a real boolean')
    from playwright_recipes.native_payment_policy import validate_payment_inputs
    reason = validate_payment_inputs(operation, data)
    if reason:
        raise Stop(reason)
    if operation not in FIELDS:
        return  # API-only and unknown operations retain their explicit dispatch refusal.
    unknown = set(data) - COMMON - FIELDS[operation] - {'options'}
    if unknown:
        raise Stop('Unsupported recipe inputs require an implementation: ' + ', '.join(sorted(unknown)))
    missing = (REQUIRED.get(operation, set()) | {'location_id', 'location_name', 'start_url'}) - set(data)
    if operation in ('funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page'):
        if data.get('file'):
            missing |= {'marker', 'seo'} - set(data)
        elif set(data).intersection({'marker', 'code_id', 'seo', 'placement'}):
            raise Stop('Code/SEO inputs require the corresponding HTML file')
    if operation == 'pages.install_embed' and ('embed_config' in data or 'embed_placement' in data):
        if not isinstance(data.get('embed_config'), dict) or 'embed_placement' not in data:
            raise Stop('Embed configuration and exact native placement are both required')
        from playwright_recipes.skill6_playwright import validate_placement
        validate_placement(data['embed_placement'])
    if operation == 'pages.responsive':
        from playwright_recipes.page_layout import validate_responsive
        validate_responsive({'responsive': data.get('responsive')})
    if operation == 'pages.saved_section':
        from playwright_recipes.saved_section import validate
        validate({'saved_section': data.get('saved_section')})
    if operation == 'pages.layout' and 'layout' in data:
        from playwright_recipes.page_layout import validate
        validate({'layout': data['layout']})
    for key in ('placement', 'before_placement', 'after_placement'):
        if key in data:
            from playwright_recipes.skill6_playwright import validate_placement
            validate_placement(data[key])
    if 'placement' in data and set(data).intersection({'section_id', 'element_id', 'expected_name'}):
        raise Stop('Explicit column placement cannot be combined with legacy element or section targeting')
    if operation == 'checkout.wrap_native' and 'checkout' in data:
        checkout = data['checkout']
        if not isinstance(checkout, dict) or set(checkout) - {'mode', 'placement', 'coupon_codes', 'quantity', 'multi_product'}:
            raise Stop('Native checkout accepts only mode, placement and captured switch settings')
        if checkout.get('mode', 'One-step') not in ('One-step', 'Two-step', 'Split'):
            raise Stop('Unsupported checkout mode')
        for flag in ('coupon_codes', 'quantity', 'multi_product'):
            if flag in checkout and type(checkout[flag]) is not bool:
                raise Stop('Native checkout switches require real booleans')
        if 'placement' in checkout:
            from playwright_recipes.skill6_playwright import validate_placement
            validate_placement(checkout['placement'])
    if operation == 'pages.layout' and 'options' in data:
        raise Stop('Layout preparation requires an independently journaled job')
    if operation == 'checkout.wrap_native':
        if 'after_placement' in data and not data.get('after_file'):
            raise Stop('after_placement requires after_file')
        if data.get('after_file'):
            missing |= {'after_marker'} - set(data)
        elif 'after_marker' in data:
            raise Stop('after_marker requires after_file')
    if operation == 'checkout.one_click_upsell' and not data.get('adapter_capture'):
        unused = set(data).intersection(CHECKOUT - {'checkout_contract'})
        if unused:
            raise Stop('Native checkout inputs require their captured adapter: ' + ', '.join(sorted(unused)))
    if operation == 'communities.configure' and not set(data).intersection({'channels', 'details', 'access', 'course_associations', 'branding'}):
        if set(data).intersection({'portal_url', 'group_name'}):
            raise Stop('Portal identity requires a concrete channel or details operation')
    if missing:
        raise Stop('Missing required recipe inputs: ' + ', '.join(sorted(missing)))
    if operation == 'funnels.split_variant' and set(data).intersection(FIELDS[operation]):
        from playwright_recipes.split_variant import validate, COMMON as SPLIT_COMMON, PLAN
        if 'options' in data:
            raise Stop('Native split variants and recorded options require separate jobs')
        validate({'action':'native_split_variant', 'payload':{key:data[key] for key in SPLIT_COMMON | PLAN if key in data}})
    if operation == 'quizzes.create' and 'configuration' in data:
        from playwright_recipes.quiz_creation import payload_from_inputs
        payload_from_inputs(data)
    if operation == 'surveys.create' and 'question_batches' in data:
        from playwright_recipes.survey_creation import payload_from_inputs
        payload_from_inputs(data)
    elif operation == 'surveys.create' and 'radio_questions' in data:
        from playwright_recipes.survey_radio_creation import payload_from_inputs
        payload_from_inputs(data)
    elif operation == 'surveys.create' and set(data).intersection({'target_slide','slide_count'}):
        raise Stop('Survey target_slide requires the authored Radio creation flow')
    if operation == 'courses.configure_ui':
        native = set(data).intersection(FIELDS[operation])
        if native and 'options' in data:
            raise Stop('Native course theme edits and recorded options require separate jobs')
        if native:
            if 'video_blocks' in data:
                from playwright_recipes.course_video_blocks import validate_inputs
            elif 'image_blocks' in data:
                from playwright_recipes.course_image_blocks import validate_inputs
            elif 'theme_images' in data:
                from playwright_recipes.course_section_media import validate_inputs
            elif 'text_blocks' in data:
                from playwright_recipes.course_text_blocks import validate_inputs
            elif 'custom_blocks' in data:
                from playwright_recipes.course_blocks import validate_inputs
            elif 'background_image' in data or 'background_transparency' in data or 'background_removal' in data:
                from playwright_recipes.course_theme_media import validate_inputs
            elif 'custom_block_image' in data:
                from playwright_recipes.course_block_media import validate_inputs
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
    if operation == 'forms.configure' and 'address_parent' in data:
        if set(data).intersection((FIELDS['forms.configure']-{'address_parent'})|{'options'}):
            raise Stop('Parent Address controls require an independent preservation-bound job')
        from playwright_recipes.address_parent import validate
        config=data['address_parent']
        if not isinstance(config,dict) or set(config).intersection({'location_id','location_name','start_url'}):
            raise Stop('Parent Address configuration must not override parent job identity')
        validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**config}})
    if operation == 'forms.configure' and 'integration' in data:
        if set(data).intersection({'fields', 'add_fields', 'address_fields', 'consent',
                                    'object_fields', 'dropdown_fields', 'large_text_fields', 'field_dependencies', 'options'}):
            raise Stop('Native form embed export requires its own independently journaled job')
        from playwright_recipes.form_embed import validate
        validate({'integration':data['integration']})
    if operation == 'forms.configure':
        if 'widget_fields' in data:
            if set(data).intersection(FIELDS['forms.configure'] - {'widget_fields'} | {'options'}):
                raise Stop('Native form widget fields require their own independently journaled job')
            from playwright_recipes.form_widget_families import validate
            value=data['widget_fields']
            if not isinstance(value,dict) or set(value).intersection({'location_id','location_name','start_url'}):
                raise Stop('Form widget owner identity belongs to the parent inputs')
            validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**value}})
        if 'contact_field_plan' in data:
            if set(data) - COMMON - {'contact_field_plan'}:
                raise Stop('Contact field dependency creation and placement require their own independently journaled job')
            from playwright_recipes.contact_field_frontdoor import payload_from_inputs
            payload_from_inputs(data)
        for key in ('fields', 'add_fields', 'address_fields', 'object_fields'):
            if key in data and (not isinstance(data[key], list) or not data[key]):
                raise Stop(key + ' must be a nonempty list when supplied')
        if 'large_text_fields' in data:
            if set(data).intersection({'fields','add_fields','address_fields','consent','object_fields','dropdown_fields','integration','options'}):
                raise Stop('Native Large Text placement requires a separate independently journaled job')
            from playwright_recipes.large_text_fields import validate
            validate({'payload':{key:data[key] for key in ('location_id','location_name','start_url','large_text_fields','field_dependencies') if key in data}})
        if 'dropdown_fields' in data:
            if set(data).intersection({'fields','add_fields','address_fields','consent','object_fields','large_text_fields','integration','options'}):
                raise Stop('Native dropdown placement requires a separate independently journaled job')
            from playwright_recipes.dropdown_fields import validate
            validate({'payload':{key:data[key] for key in ('location_id','location_name','start_url','dropdown_fields','field_dependencies') if key in data}})
        if ('object_fields' in data or 'dropdown_fields' in data or 'large_text_fields' in data) != ('field_dependencies' in data):
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
    if operation == 'forms.conditions':
        action, _ = condition_request(data['condition'])
        if action == 'native_condition_outcomes' and 'options' in data:
            raise Stop('Native conditional outcomes require their own independently journaled job')
    if operation == 'quizzes.configure':
        from playwright_recipes.quiz_batches import compile_batches
        if compile_batches(data) is None:
            quiz_creation(data)
    if operation == 'surveys.configure' and isinstance(data.get('configuration'), dict):
        config = data['configuration']
        if 'outcomes' in config:
            if 'options' in data:
                raise Stop('Survey conditional outcomes require their own independently journaled job')
            if set(config).intersection({'location_id','location_name','start_url'}):
                raise Stop('Survey conditional outcome owner identity belongs to its parent inputs')
            from playwright_recipes.survey_condition_outcomes import validate
            validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**config}})
        if 'submission' in config:
            if set(config)!={'submission'} or 'options' in data:
                raise Stop('Survey completion settings require their own independently journaled job')
            if not isinstance(config['submission'],dict) or set(config['submission']).intersection({'id','action','_context'}):
                raise Stop('Survey submission inputs must not override runner metadata')
            from playwright_recipes.form_submission import validate
            validate(config['submission'])
        if 'widget_fields' in config:
            if 'options' in data:raise Stop('Survey widget fields require their own independently journaled job')
            if set(config).intersection({'location_id','location_name','start_url'}):
                raise Stop('Survey widget owner identity belongs to its parent inputs')
            from playwright_recipes.survey_widget_families import validate
            validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**config}})
        if 'multiline_questions' in config:
            if 'options' in data:raise Stop('Survey Multi Line properties require their own independently journaled job')
            from playwright_recipes.survey_multiline_configuration import validate
            if set(config).intersection({'location_id','location_name','start_url'}):
                raise Stop('Survey Multi Line owner identity must come from its parent inputs')
            validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**config}})
        if 'text_questions' in config:
            if 'options' in data:raise Stop('Survey TEXT properties require their own independently journaled job')
            from playwright_recipes.survey_text_configuration import validate
            if set(config).intersection({'location_id','location_name','start_url'}):
                raise Stop('Survey TEXT owner identity must come from its parent inputs')
            validate({'payload':{**{key:data[key] for key in ('location_id','location_name','start_url')},**config}})
        if set(config).intersection({'object_fields', 'field_dependencies'}):
            if set(config).intersection({'location_id', 'location_name', 'start_url'}):
                raise Stop('Survey object-field owner identity must come from its parent inputs')
            if 'rules' in config:
                raise Stop('Survey object questions and conditional rule stacks require separate jobs')
            from playwright_recipes.survey_fields import validate
            validate({'payload':{**{key:data[key] for key in ('location_id', 'location_name', 'start_url')}, **config}})
    if operation == 'communities.configure' and 'branding' in data:
        from playwright_recipes.community_branding import validate_inputs
        validate_inputs(data)
    if operation == 'communities.configure' and 'course_associations' in data:
        from playwright_recipes.community_courses import validate_inputs
        validate_inputs(data)
    if operation == 'communities.configure':
        if len(set(data).intersection({'channels', 'details', 'access', 'course_associations', 'branding'})) > 1:
            raise Stop('Community channels, details and access require separately journaled jobs')
        if set(data).intersection({'channels', 'details', 'access', 'course_associations', 'branding'}) and 'options' in data:
            raise Stop('Concrete community operations and generic options require separate jobs')
    if operation in ('meetings.setup', 'meetings.update') and 'cohosts' in data['meeting']:
        if 'options' in data:
            raise Stop('Co-host roster reconciliation and recorded options require separate jobs')
    if operation == 'meetings.integrate' and data.get('integration_mode') is not None:
        mode = data['integration_mode']
        if mode not in ('dynamic_calendar_room', 'community_event_room', 'course_live_session', 'provider_oauth_handoff'):
            raise Stop('Meeting integration mode requires a captured native or measured API profile')
        if 'options' in data:
            raise Stop('Concrete native room integrations and recorded options require separate jobs')
        if mode == 'course_live_session':
            from playwright_recipes.native_course_live_session import validate_inputs
            validate_inputs({key:value for key,value in data.items()
                if key not in ('integration_mode', 'auth_activation', 'publish')})
        elif mode == 'provider_oauth_handoff':
            if 'auth_activation' in data or 'publish' in data:
                raise Stop('Provider OAuth handoff cannot use app-auth activation or publish inputs')
            from playwright_recipes.meeting_oauth_handoff import validate_inputs
            validate_inputs({key:value for key,value in data.items() if key!='integration_mode'},require_fresh=False)
        elif mode == 'community_event_room':
            if 'auth_activation' in data:
                raise Stop('Community event rooms require a caller-owned authenticated portal session')
            from playwright_recipes.community_event_meeting import validate_inputs
            validate_inputs({key:value for key,value in data.items() if key != 'integration_mode'})
        else:
            from playwright_recipes.meeting_dynamic import validate_inputs
            validate_inputs({key:value for key,value in data.items() if key not in ('integration_mode', 'publish', 'auth_activation')}, require_fresh=False)
