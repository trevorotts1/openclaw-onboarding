"""Validate completed editor journals without reading a browser or replaying writes."""
from collections.abc import Mapping
import hashlib
import re
from urllib.parse import parse_qsl, urlsplit

if __package__:
    from .skill6_playwright import Stop
    from .evidence_lease import read_journal
    from .receipt_validation import pending_proof
else:
    from skill6_playwright import Stop
    from evidence_lease import read_journal
    from receipt_validation import pending_proof


STATUSES = {
    'native_survey_condition_outcomes': {'CONDITION_OUTCOMES_SAVED_AND_REOPENED','CONDITION_OUTCOMES_REUSED_AND_REOPENED'},
    'survey_submission': {'SURVEY_SUBMISSION_SAVED_AND_REOPENED'},
    'native_survey_widget_fields': {'SURVEY_WIDGET_FIELDS_SAVED_AND_REOPENED'},
    'native_split_variant': {'SPLIT_VARIANT_SAVED_AND_REOPENED', 'SPLIT_VARIANT_REUSED_AND_REOPENED'},
    'native_address_parent': {'ADDRESS_PARENT_SAVED_AND_REOPENED'},
    'native_form_widget_fields': {'FORM_WIDGET_FIELDS_SAVED_AND_REOPENED'},
    'native_survey_text_configuration': {'SURVEY_TEXT_PROPERTIES_SAVED_AND_REOPENED'},
    'native_survey_multiline_configuration': {'SURVEY_MULTILINE_PROPERTIES_SAVED_AND_REOPENED'},
    'quiz_picture_choices': {'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED'},
    'native_survey_radio_creation': {'SURVEY_RADIO_SAVED_AND_REOPENED'},
    'native_quiz_creation': {'QUIZ_CREATED_SAVED_AND_REOPENED'},
    'native_survey_creation': {'SURVEY_CREATED_SAVED_AND_REOPENED'},
    'html': {'RENDERED'}, 'seo': {'SEO_RENDERED'}, 'checkout': {'COMPONENT_SAVED'},
    'form': {'SAVED_AND_REOPENED'}, 'form_css': {'FORM_CSS_RENDERED'},
    'native_form_css': {'NATIVE_FORM_CSS_SAVED_AND_REOPENED'},
    'native_fields': {'FIELD_PROPERTIES_SAVED_AND_REOPENED'},
    'native_field_placement': {'BUILTIN_FIELDS_SAVED_AND_REOPENED', 'BUILTIN_FIELDS_REUSED_AND_REOPENED'},
    'native_address_fields': {'ADDRESS_FIELDS_SAVED_AND_REOPENED'},
    'native_form_consent': {'CONSENT_SAVED_AND_REOPENED'},
    'native_object_fields': {'OBJECT_FIELDS_SAVED_AND_REOPENED'},
    'native_dropdown_fields': {'DROPDOWN_FIELDS_SAVED_AND_REOPENED'},
    'native_large_text_fields': {'LARGETEXT_FIELDS_SAVED_AND_REOPENED'},
    'native_contact_field_chain': {'CONTACT_FIELDS_SAVED_AND_REOPENED'},
    'quiz_short_answers': {'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED'},
    'quiz_multiple_choices': {'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED'},
    'quiz_written_answers': {'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED'},
    'native_condition_outcomes': {'CONDITION_OUTCOMES_SAVED_AND_REOPENED','CONDITION_OUTCOMES_REUSED_AND_REOPENED'},
    'native_survey_object_fields': {'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED'},
    'native_condition': {'CONDITION_ALREADY_PRESENT', 'CONDITION_SAVED_AND_REOPENED', 'CONDITION_SAVE_SUBMITTED'},
    'native_condition_group': {'CONDITION_GROUP_SAVED_AND_REOPENED', 'CONDITION_GROUP_REUSED_AND_REOPENED'},
    'native_condition_stack': {'CONDITION_STACK_SAVED_AND_REOPENED', 'CONDITION_STACK_REUSED_AND_REOPENED'},
    'quiz_configuration': {'QUIZ_CONFIGURATION_SAVED_AND_REOPENED'},
    'quiz_results': {'QUIZ_RESULTS_SAVED_AND_REOPENED'},
    'survey_configuration': {'SURVEY_RULE_ALREADY_PRESENT', 'SURVEY_RULE_SAVED_AND_REOPENED'},
    'survey_rule_stack': {'SURVEY_RULE_STACK_SAVED_AND_REOPENED'},
    'assessment': {'ASSESSMENT_REUSED', 'ASSESSMENT_SAVE_SUBMITTED'},
    'form_settings': {'FORM_SETTINGS_PERSISTED'},
    'native_form_schedule': {'FORM_SCHEDULE_SAVED_AND_REOPENED'},
    'native_form_tracking': {'FORM_TRACKING_SAVED_AND_REOPENED'},
    'native_form_embed': {'FORM_EMBED_EXPORTED_AND_REREAD'},
    'native_order_confirmation': {'ORDER_CONFIRMATION_SAVED_AND_REOPENED', 'ORDER_CONFIRMATION_REUSED_AND_REOPENED'},
    'native_course_theme': {'COURSE_THEME_SAVED_AND_REOPENED'},
    'native_course_blocks': {'COURSE_BLOCKS_SAVED_AND_REOPENED'},
    'native_course_text_blocks': {'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED'},
    'native_course_section_media': {'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED'},
    'native_course_image_blocks': {'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED'},
    'native_course_video_blocks': {'COURSE_VIDEO_BLOCKS_SAVED_AND_REOPENED'},
    'native_course_theme_media': {'COURSE_THEME_MEDIA_SAVED_AND_REOPENED'},
    'native_course_block_media': {'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED'},
    'form_submission': {'FORM_SUBMISSION_SAVED_AND_REOPENED'},
    'form_notifications': {'NOTIFICATION_SETTINGS_SAVED_AND_REOPENED'},
    'options': {'RECORDED_OPTIONS_EXECUTED'},
    'community': {'GROUP_RETAINED_INACTIVE', 'GROUP_CREATED', 'GROUP_CREATED_PENDING_IDENTITY', 'GROUP_CREATED_SLUG_IDENTIFIED', 'GROUP_REUSED_IDENTITY_CONFIRMED'},
    'meeting': {'ROOM_CREATED_VERIFIED', 'ROOM_REUSED_VERIFIED', 'ROOM_UPDATED_VERIFIED'},
    'meeting_cohosts': {'COHOSTS_SAVED_AND_REOPENED', 'COHOSTS_REUSED_AND_REOPENED'},
    'native_dynamic_meeting_location': {'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED', 'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED'},
    'native_course_live_session': {'COURSE_LIVE_SESSION_CREATED_AND_REOPENED'},
    'native_provider_oauth_handoff': {'PENDING_USER_AUTHORIZATION'},
    'native_checkout': {'NATIVE_CONFIGURATION_READBACK_VERIFIED'},
    'native_checkout_ui': {'NATIVE_CHECKOUT_UI_READBACK_VERIFIED'},
}
REQUIRED = {
    'native_survey_condition_outcomes': ('kind','editor_url','rule_count','configuration_sha256','outcomes_sha256','saved_rules','independent_readback','behavior_verified','submission_verified','disqualification_executed'),
    'survey_submission': ('mode','editor_url','value_sha256','conditional_precedence_present','conditional_precedence_acknowledged','independent_readback','behavior_verified','submission_verified'),
    'native_survey_widget_fields': ('editor_url','configuration_sha256','widget_fields','saved_snapshot','independent_readback','behavior_verified','submission_verified'),
    'native_split_variant': ('editor_url','configuration_sha256','control_page_id','variant_page_id','control_traffic','variant_traffic','active','created','independent_readback','functional_verified'),
    'native_survey_multiline_configuration': ('editor_url','configuration_sha256','multiline_questions','independent_readback','behavior_verified','submission_verified'),
    'native_address_parent': ('kind','editor_url','configuration_sha256','controls','independent_readback','behavior_verified','submission_verified'),
    'native_form_widget_fields': ('editor_url','configuration_sha256','fields','saved_snapshot','independent_readback','behavior_verified','submission_verified'),
    'native_survey_text_configuration': ('editor_url','configuration_sha256','text_questions','independent_readback','behavior_verified','submission_verified'),
    'quiz_picture_choices': ('kind','editor_url','configuration_sha256','question_count','target_page','independent_readback','dependency_api_used','behavior_verified','submission_verified','field_id','persisted_unique_key','image_urls_sha256'),
    'native_quiz_creation': ('location_id','editor_url','configuration_sha256','shell_binding','question_receipts','configuration_receipts','question_count','scored_question_count','independent_readback','behavior_verified','submission_verified'),
    'native_survey_creation': ('location_id','editor_url','configuration_sha256','shell_binding','question_batches','saved_inventory','independent_readback','behavior_verified','submission_verified'),
    'native_survey_radio_creation': ('location_id','editor_url','configuration_sha256','shell_binding','api_fields','native_receipt','independent_readback','behavior_verified','submission_verified'),
    'navigate': ('area',), 'container': ('container_url', 'name'), 'page': ('editor_url',),
    'html': ('editor_url', 'html_sha256'), 'seo': ('canonical',),
    'checkout': ('mode', 'payment_verified', 'checkout_ready'), 'form': ('form_url',),
    'form_css': ('radius',), 'native_form_css': ('editor_url', 'css_sha256', 'submission_verified'),
    'native_fields': ('editor_url', 'fields', 'submission_verified'),
    'native_field_placement': ('editor_url', 'fields', 'submission_verified'),
    'native_address_fields': ('editor_url', 'fields', 'configuration_sha256', 'independent_readback', 'submission_verified'),
    'native_form_consent': ('editor_url', 'configuration_sha256', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'native_object_fields': ('editor_url', 'fields', 'configuration_sha256', 'independent_readback', 'submission_verified'),
    'native_dropdown_fields': ('editor_url','fields','configuration_sha256','independent_readback','submission_verified','behavior_verified'),
    'native_large_text_fields': ('editor_url','fields','configuration_sha256','independent_readback','submission_verified','behavior_verified'),
    'native_contact_field_chain': ('location_id','editor_url','configuration_sha256','api_fields','native_receipt','field_count','independent_readback','dependency_api_used','native_placement_required','behavior_verified','submission_verified'),
    'quiz_short_answers': ('kind','editor_url','configuration_sha256','question_count','target_page','independent_readback','behavior_verified','submission_verified','dependency_api_used'),
    'quiz_multiple_choices': ('kind','editor_url','configuration_sha256','question_count','target_page','independent_readback','behavior_verified','submission_verified','dependency_api_used'),
    'quiz_written_answers': ('kind','editor_url','configuration_sha256','question_count','target_page','independent_readback','behavior_verified','submission_verified','dependency_api_used'),
    'native_condition_outcomes': ('kind','editor_url','configuration_sha256','rule_count','independent_readback','behavior_verified','submission_verified','disqualification_executed'),
    'native_survey_object_fields': ('kind', 'editor_url', 'target_slide', 'field_count', 'configuration_sha256', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'native_condition': ('kind', 'effect', 'if_field', 'operator', 'target', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'native_condition_group': ('kind', 'editor_url', 'configuration_sha256', 'clause_count', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'quiz_configuration': ('kind', 'editor_url', 'questions', 'submission_verified'),
    'quiz_results': ('kind', 'editor_url', 'configuration_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'survey_configuration': ('kind', 'editor_url', 'source_slide', 'target_slide', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'survey_rule_stack': ('kind', 'editor_url', 'rule_count', 'configuration_sha256', 'independent_readback', 'submission_verified', 'behavior_verified'),
    'assessment': ('kind', 'editor_url', 'independent_readback'),
    'form_settings': ('settings', 'editor_url'),
    'native_form_schedule': ('editor_url', 'enabled', 'configuration_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'native_course_theme': ('editor_url', 'course_id', 'template_id', 'configuration_sha256', 'independent_readback', 'functional_verified', 'activation_performed'),
    'native_course_blocks': ('editor_url', 'course_id', 'template_id', 'configuration_sha256', 'independent_readback', 'functional_verified', 'activation_performed', 'added_block_ids', 'block_ids'),
    'native_course_text_blocks': ('editor_url','course_id','template_id','configuration_sha256','independent_readback','functional_verified','activation_performed','added_block_ids','block_ids','block_count'),
    'native_course_section_media': ('editor_url','course_id','template_id','configuration_sha256','independent_readback','functional_verified','activation_performed','images'),
    'native_course_image_blocks': ('editor_url','course_id','template_id','configuration_sha256','independent_readback','functional_verified','activation_performed','added_block_ids','block_ids','block_count','images'),
    'native_course_video_blocks': ('editor_url','course_id','template_id','configuration_sha256','independent_readback','functional_verified','activation_performed','added_block_ids','block_ids','block_count','videos'),
    'native_course_theme_media': ('editor_url', 'course_id', 'template_id', 'configuration_sha256', 'independent_readback', 'functional_verified', 'activation_performed', 'background_url_sha256'),
    'native_course_block_media': ('editor_url', 'course_id', 'template_id', 'block_id', 'configuration_sha256', 'independent_readback', 'functional_verified', 'activation_performed', 'image_url_sha256'),
    'native_condition_stack': ('kind', 'editor_url', 'configuration_sha256', 'rule_count', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'native_order_confirmation': ('editor_url', 'form_id', 'product_id', 'price_id', 'price_identity', 'configuration_sha256', 'independent_readback', 'conditional_precedence_present', 'conditional_precedence_acknowledged', 'payment_verified', 'behavior_verified', 'submission_verified'),
    'native_form_tracking': ('editor_url', 'configuration_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'native_form_embed': ('kind', 'editor_url', 'form_id', 'configuration_sha256', 'embed_sha256', 'embed_code', 'export_settings', 'independent_readback', 'settings_persisted', 'installation_verified', 'behavior_verified', 'submission_verified'),
    'form_submission': ('mode', 'editor_url', 'value_sha256', 'independent_readback', 'behavior_verified', 'submission_verified'),
    'form_notifications': ('enabled', 'configuration_sha256', 'recipient_count', 'independent_readback', 'behavior_verification'),
    'options': ('count', 'capture_source'), 'community': ('name', 'slug', 'discovery', 'deleted'),
    'meeting': ('room', 'meeting_started'),
    'meeting_cohosts': ('location_id', 'room_id', 'configuration_sha256', 'cohost_count', 'addition_count', 'removal_count', 'independent_readback', 'meeting_started', 'functional_verified', 'notification_behavior_verified'),
    'native_dynamic_meeting_location': ('location_id', 'calendar_id', 'staff_id', 'configuration_sha256', 'independent_readback', 'native_location_kind', 'appointment_created', 'meeting_started', 'dynamic_room_generation_verified', 'functional_verified'),
    'native_course_live_session': ('location_id','product_id','session_name','date','start_time','end_time','timezone','recurrence','learner_notifications_enabled','personal_room_association','meeting_started','identity_readback','settings_readback','functional_verified','configuration_sha256'),
    'native_provider_oauth_handoff': ('location_id','staff_id','provider','configuration_sha256','oauth_popup_opened','authorization_completed','consent_submitted','connection_verified','popup_origin_sha256'),
    'native_checkout': ('component_id', 'page_id', 'operations', 'payment_verified', 'checkout_ready', 'independent_readback'),
    'native_checkout_ui': ('element_id', 'editor_url', 'payment_verified', 'checkout_ready'),
}
BOOLEANS = frozenset(('behavior_verified', 'submission_verified', 'payment_verified',
    'functional_verified', 'checkout_ready', 'meeting_started', 'discovery', 'deleted',
    'products_missing', 'form_submitted', 'notifications_sent', 'legal_copy_saved', 'legal_acceptance',
    'conditional_precedence_present', 'conditional_precedence_acknowledged', 'activation_performed',
    'settings_persisted', 'installation_verified', 'appointment_created', 'dynamic_room_generation_verified', 'notification_behavior_verified', 'native_name_seen_after_reload', 'slug_identity_verified', 'portal_identity_verified', 'description_verified', 'reused', 'discovery_verified', 'group_activation_attempted', 'dependency_api_used', 'native_deactivation_attempted', 'inactive_verified', 'disqualification_executed', 'oauth_popup_opened', 'authorization_completed', 'consent_submitted', 'connection_verified'))
COUNTS = frozenset(('count', 'radius', 'render_checks', 'recipient_count', 'questions', 'source_slide', 'target_slide', 'rule_count', 'field_count', 'cohost_count', 'addition_count', 'removal_count', 'clause_count', 'question_count', 'target_page', 'block_count'))
IDS = frozenset(('element_id', 'section_id', 'component_id', 'page_id', 'calendar_id', 'course_id', 'template_id', 'slug', 'staff_id', 'form_id', 'block_id', 'product_id', 'price_id'))
HASHES = frozenset(('html_sha256', 'css_sha256', 'value_sha256', 'configuration_sha256', 'requested_slug_sha256', 'source_sha256', 'background_url_sha256', 'observed_slug_sha256', 'embed_sha256', 'image_url_sha256', 'popup_origin_sha256'))
ID_PATTERN = re.compile(r'[A-Za-z0-9_-]{1,256}')


def _fail():
    raise Stop('Saved editor completion is malformed or unbound; reconciliation required')


def _url(value, job, *, public_room=False):
    if not isinstance(value, str):
        _fail()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail()
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port not in (None, 443)):
        _fail()
    if public_room:
        if parsed.query or not re.fullmatch(r'/[A-Za-z0-9/_-]+', parsed.path):
            _fail()
    else:
        requested = urlsplit(job['start_url'])
        if parsed.netloc != requested.netloc:
            _fail()
        path = r'/(?:v2/)?location/' + re.escape(job['location_id']) + r'/'
        path += (r'(?:page-builder/[A-Za-z0-9_-]+|(?:form|survey|quiz)-builder-v2/[A-Za-z0-9_-]+'
                 r'|funnels-websites/(?:funnels|websites)/[A-Za-z0-9_-]+(?:/pages|/steps/[A-Za-z0-9_-]+/overview)?)/?')
        if not re.fullmatch(path, parsed.path):
            _fail()
        if parsed.query and (not '/page-builder/' in parsed.path
                or parse_qsl(parsed.query, keep_blank_values=True) not in
                ([('source', 'website')], [('source', 'funnel')])):
            _fail()
    return value


def _operation(value):
    if not isinstance(value, Mapping):
        _fail()
    # Preserve exact component identifiers and readback markers, not arbitrary
    # native adapter responses or authored/payment data nested alongside them.
    if 'op' in value:
        if (value.get('state') != 'bound-verified' or not isinstance(value.get('checkout_component_id'), str)
                or not ID_PATTERN.fullmatch(value['checkout_component_id'])):
            _fail()
        return {'checkout_component_id':value['checkout_component_id'], 'state':'bound-verified', 'op':_operation(value['op'])}
    keys = ('route', 'tab_id', 'frame_id', 'target', 'readback')
    if any(not isinstance(value.get(key), str) or not value[key] for key in keys):
        _fail()
    if value['readback'] != 'verified' or not re.fullmatch(r'[A-Za-z0-9_.-]+', value['route']):
        _fail()
    if any(not ID_PATTERN.fullmatch(value[key]) for key in ('tab_id', 'frame_id', 'target')):
        _fail()
    return {key:value[key] for key in keys}


def _result(step, value, job):
    action = step['action']
    if action == 'meeting_cohosts' and step.get('payload',{}).get('allow_creation') is True:
        from playwright_recipes.meeting_first_cohosts import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step['payload'])
    if action == 'native_survey_condition_outcomes':
        from playwright_recipes.survey_condition_outcomes import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_course_live_session':
        from playwright_recipes.native_course_live_session import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step['payload'])
    if action == 'native_provider_oauth_handoff':
        from playwright_recipes.meeting_oauth_handoff import configuration_hash, validate_inputs
        if (not isinstance(value,Mapping) or value.get('status')!='PENDING_USER_AUTHORIZATION'
                or not isinstance(value.get('popup_origin_sha256'),str)
                or not re.fullmatch(r'[a-f0-9]{64}',value['popup_origin_sha256'])):
            _fail()
        plan=validate_inputs(step['payload'],require_fresh=False)
        if (value.get('location_id')!=job['location_id'] or value.get('staff_id')!=plan['staff_id']
                or value.get('provider')!=plan['provider']
                or value.get('configuration_sha256')!=configuration_hash(plan)
                or value.get('oauth_popup_opened') is not True
                or value.get('authorization_completed') is not False
                or value.get('consent_submitted') is not False
                or value.get('connection_verified') is not False):
            _fail()
        return {'status':'PENDING_USER_AUTHORIZATION','location_id':plan['location_id'],
            'staff_id':plan['staff_id'],'provider':plan['provider'],
            'configuration_sha256':configuration_hash(plan),'oauth_popup_opened':True,
            'authorization_completed':False,'consent_submitted':False,
            'connection_verified':False,'popup_origin_sha256':value['popup_origin_sha256']}
    if action == 'survey_submission':
        from playwright_recipes.form_submission import validate_completion
        return validate_completion(value,step,job['start_url'])
    if action == 'native_survey_widget_fields':
        from playwright_recipes.survey_widget_families import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_split_variant':
        from playwright_recipes.split_variant import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_survey_multiline_configuration':
        from playwright_recipes.survey_multiline_configuration import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_address_parent':
        from playwright_recipes.address_parent import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_form_widget_fields':
        from playwright_recipes.form_widget_families import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_survey_text_configuration':
        from playwright_recipes.survey_text_configuration import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'quiz_picture_choices':
        from playwright_recipes.quiz_picture_questions import validate_receipt
        if any(step['payload'][key] != job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_quiz_creation':
        from playwright_recipes.quiz_creation import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action in ('native_survey_radio_creation','native_survey_creation'):
        from playwright_recipes.survey_radio_creation import validate_receipt
        if any(step['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):_fail()
        return validate_receipt(value,step)
    if action == 'native_contact_field_chain':
        from playwright_recipes.contact_field_frontdoor import validate_receipt
        if any(step['payload'][key] != job[key] for key in ('location_id','location_name','start_url')):
            _fail()
        return validate_receipt(value, step)
    if not isinstance(value, Mapping) or action not in REQUIRED:
        _fail()
    if any(key not in value for key in REQUIRED[action]):
        _fail()
    if action in ('navigate', 'container', 'page'):
        if value.get('status') is not None:
            _fail()
        safe = {}
    else:
        if not isinstance(value.get('status'), str) or value['status'] not in STATUSES.get(action, ()):
            _fail()
        safe = {'status':value['status']}
    if 'location_id' in value and value['location_id'] != job['location_id']:
        _fail()
    embed = None
    insertion = None
    text_blocks = None
    section_media = None
    image_blocks = None
    video_blocks = None
    background_media = None
    if action == 'native_course_theme_media':
        from playwright_recipes.course_theme_media import validate_receipt
        background_media = validate_receipt(dict(value),step)
    custom_image_removal = None
    if action=='native_course_block_media' and 'remove_image' in step.get('payload',{}).get('custom_block_image',{}):
        from playwright_recipes.course_custom_image_removal import validate_receipt
        custom_image_removal=validate_receipt(dict(value),step)
    block_deletion = None
    if action == 'native_course_blocks' and 'deletion' in step.get('payload',{}).get('custom_blocks',{}):
        from playwright_recipes.course_block_delete import validate_receipt
        block_deletion = validate_receipt(dict(value),step)
    if action == 'native_course_video_blocks':
        from playwright_recipes.course_video_blocks import validate_receipt
        video_blocks=validate_receipt(dict(value),step)
    if action == 'native_course_image_blocks':
        from playwright_recipes.course_image_blocks import validate_receipt
        image_blocks = validate_receipt(dict(value),step)
    if action == 'native_course_section_media':
        from playwright_recipes.course_section_media import validate_receipt
        section_media = validate_receipt(dict(value),step)
    if action == 'native_course_text_blocks':
        from playwright_recipes.course_text_blocks import validate_receipt
        text_blocks = validate_receipt(dict(value),step)
    if action == 'native_form_embed':
        from playwright_recipes.form_embed import validate_receipt
        embed = validate_receipt(value, step)
    if action in ('native_dropdown_fields','native_large_text_fields'):
        if action == 'native_dropdown_fields':
            from playwright_recipes.dropdown_fields import validate_receipt
        else:
            from playwright_recipes.large_text_fields import validate_receipt
        # Validate the original outcome before generic retained-field filtering.
        insertion = validate_receipt(dict(value), step)
    if action == 'native_condition_outcomes':
        from playwright_recipes.form_condition_outcomes import validate_receipt
        validate_receipt(dict(value), step)
    extra = {
        'html': {'element_id', 'section_id'}, 'native_form_css': {'render_checks'},
        'meeting': {'previous_room_identity'},
        'native_course_theme_media': {'source_sha256','media_operation','transparency_percentage','background_removed'},
        'native_course_block_media': {'source_sha256','media_removed','inspector_url_sha256'},
        'native_course_blocks': {'removed_block_ids'},
        'community': {'requested_slug_sha256', 'observed_slug_sha256', 'identity_source', 'group_status', 'portal_url'},
        'native_provider_oauth_handoff': {'provider'},
    }.get(action, set())
    # A familiar field on an unrelated handler is still an arbitrary extra.
    allowed = set(REQUIRED[action]) | extra | BOOLEANS | {
        'status', 'independent_readback', 'behavior_verification'}
    value = {key:item for key,item in value.items() if key in allowed}
    for key in BOOLEANS.intersection(value):
        if type(value[key]) is not bool:
            _fail()
        safe[key] = value[key]
    for key in COUNTS.intersection(value):
        if type(value[key]) is not int or value[key] < 0:
            _fail()
        safe[key] = value[key]
    for key in IDS.intersection(value):
        if value[key] is None and key in ('element_id', 'section_id'):
            continue
        if not isinstance(value[key], str) or not ID_PATTERN.fullmatch(value[key]):
            _fail()
        safe[key] = value[key]
    for key in HASHES.intersection(value):
        if not isinstance(value[key], str) or not re.fullmatch(r'[a-f0-9]{64}', value[key]):
            _fail()
        if key in step and step[key] != value[key]:
            _fail()
        safe[key] = value[key]
    for key in ('editor_url', 'container_url', 'form_url'):
        if key in value:
            if action in ('native_course_theme', 'native_course_blocks', 'native_course_theme_media', 'native_course_block_media', 'native_course_text_blocks', 'native_course_section_media', 'native_course_image_blocks', 'native_course_video_blocks') and key == 'editor_url':
                from playwright_recipes.course_theme import editor_url
                expected_url = editor_url(step['payload'])
                if value[key] != expected_url:
                    _fail()
                safe[key] = expected_url
                continue
            safe[key] = _url(value[key], job)
            if key != 'container_url':
                family = ('page-builder' if action in ('page', 'html', 'native_checkout_ui')
                    else 'quiz-builder-v2' if action in ('quiz_configuration', 'quiz_results', 'quiz_short_answers', 'quiz_multiple_choices', 'quiz_written_answers') or (action == 'assessment' and step.get('kind') == 'quiz')
                    else 'survey-builder-v2' if action in ('survey_configuration', 'survey_rule_stack', 'native_survey_object_fields') or action == 'assessment'
                    else 'form-builder-v2')
                if '/' + family + '/' not in urlsplit(safe[key]).path:
                    _fail()
                requested = urlsplit(job['start_url'])
                if '/' + family + '/' in requested.path and requested.path != urlsplit(safe[key]).path:
                    _fail()
    for key in ('independent_readback', 'behavior_verification'):
        if key in value:
            allowed = ('REQUIRED', 'VERIFIED', 'COMPLETE') if key == 'independent_readback' else ('REQUIRED',)
            if value[key] not in allowed:
                _fail()
            safe[key] = value[key]
    if 'kind' in value:
        if value['kind'] not in ('quiz', 'quiz_results', 'survey', 'form_condition', 'survey_condition', 'survey_condition_stack', 'survey_object_fields', 'form_condition_group', 'form_condition_stack', 'form_embed', 'quiz_short_answers', 'quiz_multiple_choices', 'quiz_written_answers', 'form_condition_outcomes'):
            _fail()
        safe['kind'] = value['kind']
    if 'mode' in value and value['mode'] is not None:
        if value['mode'] not in ('Message', 'Redirect to URL', 'One-step', 'Two-step', 'Split'):
            _fail()
        safe['mode'] = value['mode']
    for key in ('area', 'name', 'slug', 'canonical', 'effect', 'if_field', 'operator', 'target', 'source_slide', 'target_slide'):
        if key in value and key in step and value[key] != step[key]:
            _fail()
    if action == 'navigate':
        safe['area'] = step['area']
    if action == 'container':
        safe['name'] = step['name']
        family = '/funnels-websites/' + ('funnels/' if step['surface'] == 'funnel' else 'websites/')
        if family not in urlsplit(safe['container_url']).path:
            _fail()
    if action in ('assessment', 'quiz_configuration') and value.get('kind') != ('quiz' if action == 'quiz_configuration' else step.get('kind')):
        _fail()
    if action in ('native_condition', 'survey_configuration') and value['kind'] != (
            'form_condition' if action == 'native_condition' else 'survey_condition'):
        _fail()
    if action == 'native_condition_stack':
        from playwright_recipes.form_condition_stack import configuration_hash
        if (value['kind'] != 'form_condition_stack' or value['rule_count'] != len(step['rules'])
                or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action == 'native_condition_group':
        from playwright_recipes.form_conditions import configuration_hash
        if (value['kind'] != 'form_condition_group'
                or value['clause_count'] != len(step['clauses'])
                or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action == 'survey_rule_stack':
        from playwright_recipes.survey_ui import configuration_hash
        if (value['kind'] != 'survey_condition_stack'
                or type(value['rule_count']) is not int or value['rule_count'] != len(step['rules'])
                or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action == 'quiz_results':
        from playwright_recipes.quiz_results import configuration_hash
        if (value['kind'] != 'quiz_results'
                or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['behavior_verified'] is not False
                or value['submission_verified'] is not False):
            _fail()
    if action == 'form_settings':
        if value['settings'] != step.get('settings') or not isinstance(value['settings'], dict) or any(type(x) is not bool for x in value['settings'].values()):
            _fail()
        safe['settings'] = dict(value['settings'])
    if action == 'native_form_schedule':
        from playwright_recipes.form_schedule import configuration_hash
        if (type(value['enabled']) is not bool
                or value['enabled'] != step['schedule']['enabled']
                or value['configuration_sha256'] != configuration_hash(step['schedule'])
                or value['independent_readback'] != 'VERIFIED'
                or value['behavior_verified'] is not False
                or value['submission_verified'] is not False):
            _fail()
        safe['enabled'] = value['enabled']
    if action == 'native_course_theme':
        from playwright_recipes.course_theme import configuration_hash
        payload = step['payload']
        if (value['course_id'] != payload['course_id']
                or value['template_id'] != payload['template_id']
                or value['configuration_sha256'] != configuration_hash(payload)
                or value['independent_readback'] != 'VERIFIED'
                or value['functional_verified'] is not False
                or value['activation_performed'] is not False):
            _fail()
    if action == 'native_course_block_media' and custom_image_removal is None:
        if 'source_sha256' not in value:_fail()
        from playwright_recipes.course_block_media import configuration_hash
        plan = step['payload']
        if (value['course_id'] != plan['course_id'] or value['template_id'] != plan['template_id']
                or value['block_id'] != plan['custom_block_image']['block_id']
                or value['configuration_sha256'] != configuration_hash(plan)
                or value['source_sha256'] != plan['custom_block_image']['sha256']
                or value['image_url_sha256'] == hashlib.sha256(plan['custom_block_image']['expected_url'].encode()).hexdigest()
                or value['independent_readback'] != 'VERIFIED'
                or value['functional_verified'] is not False or value['activation_performed'] is not False):
            _fail()
    if custom_image_removal is not None:
        safe['media_removed']=True
        safe['inspector_url_sha256']=custom_image_removal['inspector_url_sha256']
    if action == 'native_course_theme_media':
        if 'media_operation' in background_media:
            safe['media_operation']=background_media['media_operation']
            if background_media['media_operation']=='transparency':
                safe['transparency_percentage']=background_media['transparency_percentage']
            elif background_media['media_operation']=='removal':
                safe['background_removed']=background_media['background_removed']
    if action == 'native_course_video_blocks':
        safe['videos']=video_blocks['videos']
        safe['added_block_ids']=video_blocks['added_block_ids']
        safe['block_ids']=video_blocks['block_ids']
    if action == 'native_course_image_blocks':
        safe['images'] = image_blocks['images']
        safe['added_block_ids'] = image_blocks['added_block_ids']
        safe['block_ids'] = image_blocks['block_ids']
    if action == 'native_course_section_media':
        safe['images'] = section_media['images']
    if action == 'native_course_text_blocks':
        safe['added_block_ids'] = text_blocks['added_block_ids']
        safe['block_ids'] = text_blocks['block_ids']
    if action == 'native_course_blocks':
        from playwright_recipes.course_blocks import configuration_hash, validate_inputs
        plan = validate_inputs(step['payload'])
        config=plan['custom_blocks']
        removed=[config['deletion']['id']] if block_deletion is not None else []
        before = [row['id'] for row in config['expected_inventory'] if row['id'] not in removed]
        added, identities = value['added_block_ids'], value['block_ids']
        if (value['course_id'] != plan['course_id'] or value['template_id'] != plan['template_id']
                or value['configuration_sha256'] != configuration_hash(plan)
                or value['independent_readback'] != 'VERIFIED'
                or value['functional_verified'] is not False or value['activation_performed'] is not False
                or not isinstance(added, list) or len(added) != len(config.get('append',[]))
                or not isinstance(identities, list)
                or any(not isinstance(identity, str) or not ID_PATTERN.fullmatch(identity) for identity in identities)
                or identities != before + added or len(set(identities)) != len(identities)):
            _fail()
        safe['added_block_ids'] = added
        safe['block_ids'] = identities
        if block_deletion is not None:safe['removed_block_ids']=block_deletion['removed_block_ids']
    if action == 'native_fields':
        fields = [field['field'] for field in step.get('fields', [])]
        if value['fields'] != fields:
            _fail()
        safe['fields'] = fields
    if action == 'native_address_parent':
        from playwright_recipes.address_parent import validate_receipt
        validate_receipt(dict(value),step)
    if action == 'native_address_fields':
        from playwright_recipes.forms_advanced import configuration_hash
        fields = [{'field':field['field'], 'query_key':field['query_key']}
                  for field in step['address_fields']]
        if (value['fields'] != fields or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED' or value['submission_verified'] is not False):
            _fail()
        safe['fields'] = fields
    if action == 'native_order_confirmation':
        from playwright_recipes.form_order_confirmation import validate_receipt
        validate_receipt(dict(value), step)
        safe['price_identity'] = 'UNIQUE_CATALOG_PRICE'
    if action == 'native_form_embed':
        if value['form_id'] != step['integration']['form_id']:
            _fail()
        safe.update(embed)
    if action == 'native_form_tracking':
        from playwright_recipes.form_tracking import configuration_hash
        if (value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action == 'native_form_consent':
        from playwright_recipes.forms_advanced import consent_configuration_hash
        if (value['configuration_sha256'] != consent_configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action in ('quiz_short_answers','quiz_multiple_choices','quiz_written_answers'):
        if action == 'quiz_short_answers':
            from playwright_recipes.quiz_text_questions import configuration_hash
        elif action == 'quiz_multiple_choices':
            from playwright_recipes.quiz_choice_questions import configuration_hash
        else:
            from playwright_recipes.quiz_written_questions import configuration_hash
        plan=step['payload']
        if (value['kind']!=action or value['question_count']!=len(plan['questions'])
                or value['target_page']!=plan['target_page']
                or value['configuration_sha256']!=configuration_hash(step)
                or value['independent_readback']!='VERIFIED' or value['dependency_api_used'] is not False
                or value['behavior_verified'] is not False or value['submission_verified'] is not False):
            _fail()
    if action in ('native_dropdown_fields','native_large_text_fields'):
        safe['fields'] = insertion['fields']
    if action == 'native_object_fields':
        from playwright_recipes.forms_advanced import object_fields_configuration_hash
        fields, requested = value['fields'], step['payload']['object_fields']
        if (not isinstance(fields, list) or len(fields) != len(requested)
                or value['configuration_sha256'] != object_fields_configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED' or value['submission_verified'] is not False):
            _fail()
        clean = []
        for field, intended in zip(fields, requested):
            if (not isinstance(field, Mapping) or field.get('placement') not in ('added', 'reused')
                    or any(field.get(key) != intended[key] for key in ('id', 'field_key', 'data_type'))):
                _fail()
            clean.append({**{key:intended[key] for key in ('id', 'field_key', 'data_type')},
                          'placement':field['placement']})
        safe['fields'] = clean
    if action == 'native_survey_object_fields':
        from playwright_recipes.survey_fields import configuration_hash
        payload = step['payload']
        if (value['kind'] != 'survey_object_fields'
                or type(value['target_slide']) is not int or value['target_slide'] != payload['target_slide']
                or type(value['field_count']) is not int or value['field_count'] != len(payload['object_fields'])
                or value['configuration_sha256'] != configuration_hash(step)
                or value['independent_readback'] != 'VERIFIED'
                or value['submission_verified'] is not False or value['behavior_verified'] is not False):
            _fail()
    if action == 'native_field_placement':
        from playwright_recipes.field_placement import CAPTURED_FIELDS
        requested = step.get('add_fields')
        fields = value['fields']
        if not isinstance(requested, list) or not isinstance(fields, list) or len(fields) != len(requested):
            _fail()
        clean = []
        for label, field in zip(requested, fields):
            spec = CAPTURED_FIELDS.get(label)
            if (not spec or not isinstance(field, Mapping)
                    or field.get('field') != label
                    or field.get('query_keys') != list(spec['query_keys'])
                    or field.get('placement') not in ('added', 'reused')):
                _fail()
            clean.append({'field':label, 'query_keys':list(spec['query_keys']), 'placement':field['placement']})
        added = any(field['placement'] == 'added' for field in clean)
        if (not requested or value['submission_verified'] is not False
                or (value['status'] == 'BUILTIN_FIELDS_SAVED_AND_REOPENED') != added):
            _fail()
        safe['fields'] = clean
    if action == 'options':
        if value['count'] != len(step.get('steps', [])) or value['capture_source'] != step.get('capture_source'):
            _fail()
    if action == 'community':
        if (value.get('name') != step.get('name') or value.get('slug') != step.get('slug')
                or value.get('discovery') is not False or value.get('deleted') is not False):
            _fail()
        safe['name'] = step['name']
        if value['status'] == 'GROUP_REUSED_IDENTITY_CONFIRMED':
            from playwright_recipes.community_portal import _portal
            portal_url = value.get('portal_url')
            _, slug = _portal(portal_url)
            digest = hashlib.sha256(step['slug'].encode()).hexdigest()
            inactive = step.get('inactive', True)
            if type(inactive) is not bool:
                _fail()
            expected_status = 'Inactive' if inactive else 'Active'
            expected_route = '/home'
            if (slug != step['slug'] or not urlsplit(portal_url).path.rstrip('/').endswith(expected_route)
                    or value.get('requested_slug_sha256') != digest or value.get('observed_slug_sha256') != digest
                    or value.get('identity_source') != 'native_app_card_login_popup'
                    or value.get('native_name_seen_after_reload') is not True or value.get('group_status') != expected_status
                    or value.get('slug_identity_verified') is not True or value.get('portal_identity_verified') is not True
                    or value.get('description_verified') is not False or value.get('discovery_verified') is not False
                    or value.get('functional_verified') is not False or value.get('group_activation_attempted') is not False
                    or value.get('reused') is not True or value.get('independent_readback') != 'VERIFIED'):
                _fail()
            safe['portal_url'] = portal_url
            safe['group_status'] = expected_status
            safe['identity_source'] = 'native_app_card_login_popup'
        if value['status'] == 'GROUP_CREATED_SLUG_IDENTIFIED':
            digest = hashlib.sha256(step['slug'].encode()).hexdigest()
            inactive=step.get('inactive',True)
            expected_status='Inactive' if inactive else 'Active'
            if (step.get('allow_creation') is not True
                    or value.get('native_deactivation_attempted') is not inactive
                    or value.get('inactive_verified') is not inactive
                    or value.get('requested_slug_sha256') != digest or value.get('observed_slug_sha256') != digest
                    or value.get('identity_source') != 'native_creation_redirect'
                    or value.get('native_name_seen_after_reload') is not True
                    or value.get('group_status') != expected_status
                    or value.get('slug_identity_verified') is not True
                    or value.get('portal_identity_verified') is not False
                    or value.get('discovery_verified') is not False or value.get('functional_verified') is not False
                    or value.get('group_activation_attempted') is not False
                    or value.get('independent_readback') != 'VERIFIED'):
                _fail()
            safe['group_status'] = expected_status
            safe['identity_source'] = 'native_creation_redirect'
        if value['status'] == 'GROUP_CREATED_PENDING_IDENTITY':
            if (step.get('allow_creation') is not True or step.get('inactive', True) is not False
                    or value.get('requested_slug_sha256') != hashlib.sha256(step['slug'].encode()).hexdigest()
                    or value.get('native_name_seen_after_reload') is not True
                    or value.get('group_status') != 'Active'
                    or value.get('slug_identity_verified') is not False
                    or value.get('discovery_verified') is not False
                    or value.get('functional_verified') is not False
                    or value.get('group_activation_attempted') is not False
                    or value.get('independent_readback') != 'REQUIRED'):
                _fail()
            safe['group_status'] = 'Active'
    if action == 'form_notifications':
        expected = {key:step[key]['enabled'] for key in ('email_notification', 'auto_responder') if key in step}
        if value['enabled'] != expected or any(type(x) is not bool for x in value['enabled'].values()):
            _fail()
        safe['enabled'] = expected
    if action == 'native_dynamic_meeting_location':
        from playwright_recipes.meeting_dynamic import validate_inputs, configuration_hash
        plan = validate_inputs(step['payload'], require_fresh=False)
        selected = next(member for member in plan['expected_staff_locations']
                        if member['staff_id'] == plan['staff_id'])
        changed = selected['location_kind'] != 'Meeting Room'
        expected_status = ('DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED' if changed
                           else 'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED')
        if (any(plan[key] != job[key] for key in ('location_id', 'location_name', 'start_url'))
                or value['calendar_id'] != plan['calendar_id'] or value['staff_id'] != plan['staff_id']
                or value['configuration_sha256'] != configuration_hash(plan)
                or value['status'] != expected_status or value['native_location_kind'] != 'Meeting Room'
                or value['independent_readback'] != 'VERIFIED'
                or any(value[key] is not False for key in ('appointment_created', 'meeting_started',
                    'dynamic_room_generation_verified', 'functional_verified'))):
            _fail()
        safe['location_id'] = job['location_id']
        safe['native_location_kind'] = 'Meeting Room'
    if action == 'meeting_cohosts':
        from playwright_recipes.meeting_cohosts import validate_write_inputs, write_configuration_hash
        plan = validate_write_inputs(step['payload'])
        before, after = plan['cohosts']['expected'], plan['cohosts']['desired']
        additions = sum(person not in before for person in after)
        removals = sum(person not in after for person in before)
        expected_status = ('COHOSTS_SAVED_AND_REOPENED' if additions or removals
                           else 'COHOSTS_REUSED_AND_REOPENED')
        if (any(plan[key] != job[key] for key in ('location_id', 'location_name', 'start_url'))
                or value['room_id'] != plan['expected_room_id']
                or value['configuration_sha256'] != write_configuration_hash(plan)
                or value['cohost_count'] != len(after)
                or value['addition_count'] != additions or value['removal_count'] != removals
                or value['status'] != expected_status
                or value['independent_readback'] != 'VERIFIED'
                or any(value[key] is not False for key in (
                    'meeting_started', 'functional_verified', 'notification_behavior_verified'))):
            _fail()
        safe['room_id'] = _url(value['room_id'], job, public_room=True)
        safe['location_id'] = job['location_id']
        safe['independent_readback'] = 'VERIFIED'
    if action == 'meeting':
        room = value['room']
        if not isinstance(room, Mapping) or room.get('location_id') != job['location_id'] or room.get('status') != 'PRESENT':
            _fail()
        url = _url(room.get('url'), job, public_room=True)
        room_id = room.get('room_id')
        if not isinstance(room_id, str):
            _fail()
        if room_id.startswith('https://'):
            _url(room_id, job, public_room=True)
        elif not ID_PATTERN.fullmatch(room_id):
            _fail()
        if (room.get('identity_source') == 'canonical_room_link' and room_id != url
                or room.get('slug') != urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1]):
            _fail()
        safe_room = {'room_id':room_id, 'url':url, 'location_id':job['location_id'], 'slug':room['slug'], 'status':'PRESENT'}
        for key in ('name', 'slug', 'waiting_room', 'guest_users', 'open_room'):
            if key not in room or (key in step and room[key] != step[key]):
                _fail()
            if key in ('waiting_room', 'guest_users', 'open_room'):
                if type(room[key]) is not bool:
                    _fail()
                safe_room[key] = room[key]
        safe['room'] = safe_room
        if 'previous_room_identity' in value:
            if value['previous_room_identity'] != step.get('expected_room_id'):
                _fail()
            previous = value['previous_room_identity']
            if not isinstance(previous, str):
                _fail()
            if previous.startswith('https://'):
                _url(previous, job, public_room=True)
            elif not ID_PATTERN.fullmatch(previous):
                _fail()
            safe['previous_room_identity'] = previous
    if action == 'native_checkout_ui' and value['element_id'] != step.get('payload', {}).get('element_id'):
        _fail()
    if action == 'native_checkout':
        payload = step.get('payload', {})
        if value['page_id'] != payload.get('page_id') or not isinstance(value['operations'], list):
            _fail()
        safe['operations'] = [_operation(record) for record in value['operations']]
    return safe


def completed_editor_replay(path, job, fingerprint):
    """Read and bind saved completion before the caller consults a browser."""
    old = read_journal(path)
    steps = job.get('steps')
    if (not isinstance(old, Mapping) or old.get('fingerprint') != fingerprint
            or old.get('location_id') != job.get('location_id')
            or not isinstance(steps, list) or not steps):
        _fail()
    if old.get('status') not in ('EDITOR_STEPS_COMPLETE', 'NEEDS_VERIFICATION'):
        raise Stop('An interrupted job exists: reconcile recorded objects before any replay')
    if (any(not isinstance(step, Mapping) or not isinstance(step.get('id'), str)
            or not re.fullmatch(r'[a-z0-9_-]+', step['id'])
            or not isinstance(step.get('action'), str) or step['action'] not in REQUIRED for step in steps)
            or len({step['id'] for step in steps}) != len(steps)):
        _fail()
    if (old.get('current_step_status') != 'FINISHED' or old.get('current_step') != steps[-1].get('id')
            or not isinstance(old.get('results'), list) or len(old['results']) != len(steps)):
        _fail()
    results, pending = [], []
    for step, row in zip(steps, old['results']):
        if not isinstance(row, Mapping) or row.get('id') != step.get('id') or row.get('action') != step.get('action'):
            _fail()
        value = row.get('result')
        safe = _result(step, value, job)
        if pending_proof(value) or value.get('kind') == 'quiz':
            pending.append(step['id'])
        results.append({'id':step['id'], 'action':step['action'], 'result':safe})
    if (old.get('verification_required') != pending
            or (old['status'] == 'NEEDS_VERIFICATION') != bool(pending)):
        _fail()
    return {'status':'NEEDS_VERIFICATION' if pending else 'ALREADY_EXECUTED',
            'fingerprint':fingerprint, 'location_id':job['location_id'],
            'current_step':steps[-1]['id'], 'current_step_status':'FINISHED',
            'results':results, 'verification_required':pending, 'replayed':True,
            'meaning':'No writes repeated. Reconcile saved outputs before a new build.'}
