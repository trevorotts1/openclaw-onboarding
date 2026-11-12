#!/usr/bin/env python3
"""Named entry points for the shared Skill 6 Playwright runner."""
import argparse
import json
from pathlib import Path
import sys
if __package__:
    from .skill6_playwright import Stop, execute, validate_job
else:
    from skill6_playwright import Stop, execute, validate_job


def compile_recipe(operation, data):
    if __package__:
        from .intake import validate_intake, condition_request, quiz_creation
    else:
        from intake import validate_intake, condition_request, quiz_creation
    validate_intake(operation, data)
    base={k:data[k] for k in ('location_id','location_name','start_url')}
    if 'auth_activation' in data:
        base['auth_activation'] = data['auth_activation']
    steps=[]
    def add(action,**kw):
        steps.append({'id':kw.pop('id',action+str(len(steps)+1)),'action':action,**kw})
    if operation in ('funnels.create','funnels.add_page','websites.create','websites.add_page'):
        surface='funnel' if operation.startswith('funnels.') else 'website'
        add('navigate',area='Funnels' if surface=='funnel' else 'Websites')
        add('container',surface=surface,name=data['container_name'],allow_creation=operation.endswith('.create'))
        add('page',surface=surface,name=data['page_name'],path=data['path'],allow_creation=True)
        if data.get('file'):
            add('html',id=data.get('code_id','main_code'),file=data['file'],marker=data['marker'],**({'placement':data['placement']} if 'placement' in data else {}))
            add('seo',**data['seo'])
    elif operation in ('pages.install_code','pages.install_embed'):
        if operation=='pages.install_embed':
            receipt=data.get('embed_receipt',{})
            if receipt.get('status')!='PASS' or receipt.get('location_id')!=data['location_id'] or not receipt.get('source'):
                raise Stop('Hosted embed needs the existing embeddability-gate PASS receipt bound to this location')
        add('html',id=data.get('code_id','main_code'),file=data['file'],marker=data['marker'],append=data.get('append',False),**{k:data[k] for k in ('element_id','expected_name','section_id','placement') if k in data},**({'embed_receipt':data['embed_receipt']} if operation=='pages.install_embed' else {}))
        add('seo',**data['seo'])
    elif operation=='checkout.wrap_native':
        add('html',id='checkout_before',file=data['before_file'],marker=data['before_marker'],**({'placement':data['before_placement']} if 'before_placement' in data else {}))
        add('checkout',**data.get('checkout',{}))
        if data.get('after_file'):
            add('html',id='checkout_after',file=data['after_file'],marker=data['after_marker'],append=True,**({'placement':data['after_placement']} if 'after_placement' in data else {}))
        add('seo',**data['seo'])
    elif operation=='pages.layout':
        add('page_layout', layout=data['layout'])
    elif operation=='pages.seo':
        add('seo',**data['seo'])
    elif operation == 'funnels.split_variant' and 'funnel_id' in data:
        from playwright_recipes.split_variant import COMMON, PLAN
        add('native_split_variant', payload={key:data[key] for key in COMMON | PLAN})
    elif operation=='forms.create':
        add('form',name=data['name'],required=data.get('required',{}),allow_creation=data.get('allow_creation',False))
        add('form_css',radius=data.get('radius',12))
    elif operation=='forms.style':
        if 'custom_css' in data:
            if 'radius' in data:
                add('form_css', radius=data['radius'])
            add('native_form_css', custom_css=data['custom_css'],
                **{k:data[k] for k in ('css_key','expect_styles') if k in data})
        else:
            add('form_css',radius=data.get('radius',12))
    elif operation=='forms.settings':
        if not set(data).intersection({'settings', 'schedule', 'tracking'}):
            raise Stop('Form settings require explicit settings, schedule or tracking')
        if 'tracking' in data:
            add('native_form_tracking', tracking=data['tracking'])
        if 'schedule' in data:
            add('native_form_schedule', schedule=data['schedule'])
        if 'settings' in data:
            add('form_settings',settings=data['settings'])
    elif operation=='forms.notifications':
        config = data.get('notifications')
        if not isinstance(config, dict) or set(config).intersection({'id','action','_context'}):
            raise Stop('Native form notifications require a configuration object without runner metadata')
        add('form_notifications', **config)
    elif operation=='forms.submission':
        if not isinstance(data.get('submission'), dict) or 'action' in data['submission']:
            raise Stop('Native form submission must be a configuration object without an executor action override')
        if data['submission'].get('mode') == 'Order Confirmation':
            if set(data['submission']).intersection({'id', 'action', '_context', 'payload'}):
                raise Stop('Order Confirmation inputs must not override runner metadata')
            add('native_order_confirmation', payload={
                **{key:base[key] for key in ('location_id', 'location_name', 'start_url')},
                **{key:value for key,value in data['submission'].items() if key != 'mode'}})
        else:
            add('form_submission', **data['submission'])
    elif operation=='forms.configure' and 'address_parent' in data:
        add('native_address_parent',payload={**{key:data[key] for key in ('location_id','location_name','start_url')},**data['address_parent']})
    elif operation=='forms.configure' and 'contact_field_plan' in data:
        from playwright_recipes.contact_field_frontdoor import payload_from_inputs
        add('native_contact_field_chain', payload=payload_from_inputs(data))
    elif operation=='forms.configure' and 'widget_fields' in data:
        add('native_form_widget_fields',payload={**{key:data[key] for key in ('location_id','location_name','start_url')}, **data['widget_fields']})
    elif operation=='forms.configure' and 'large_text_fields' in data:
        add('native_large_text_fields',payload={key:data[key] for key in ('location_id','location_name','start_url','large_text_fields','field_dependencies')})
    elif operation=='forms.configure' and 'dropdown_fields' in data:
        add('native_dropdown_fields',payload={key:data[key] for key in ('location_id','location_name','start_url','dropdown_fields','field_dependencies')})
    elif operation=='forms.configure' and 'integration' in data:
        add('native_form_embed', integration=data['integration'])
    elif operation=='forms.configure' and set(data).intersection({'add_fields', 'address_fields', 'fields', 'consent', 'object_fields'}):
        if 'add_fields' in data:
            add('native_field_placement', add_fields=data['add_fields'])
        if 'object_fields' in data:
            add('native_object_fields', payload={key:data[key] for key in (
                'location_id', 'location_name', 'start_url', 'object_fields', 'field_dependencies')})
        if 'address_fields' in data:
            add('native_address_fields', address_fields=data['address_fields'])
        if data.get('fields'):
            add('native_fields', fields=data['fields'])
        if 'consent' in data:
            add('native_form_consent', consent=data['consent'])
    elif operation=='forms.conditions':
        action, condition = condition_request(data['condition'])
        add(action, **condition)
    elif operation=='quizzes.configure' and 'question_batches' in data['configuration']:
        from playwright_recipes.quiz_batches import compile_batches
        for action, payload in compile_batches(data):
            add(action, payload=payload)
    elif operation=='quizzes.configure' and quiz_creation(data) is not None:
        action, payload = quiz_creation(data)
        add(action, payload=payload)
    elif operation=='quizzes.configure':
        config = dict(data['configuration'])
        has_results = 'result_page' in config
        result_page = config.pop('result_page', None)
        if config:
            add('quiz_configuration', **config)
        if has_results:
            add('quiz_results', result_page=result_page)
    elif operation=='surveys.configure':
        config = data['configuration']
        if 'outcomes' in config:
            add('native_survey_condition_outcomes',payload={
                **{key:data[key] for key in ('location_id','location_name','start_url')},**config})
        elif 'submission' in config:
            add('survey_submission',**config['submission'])
        elif 'widget_fields' in config:
            add('native_survey_widget_fields',payload={**{key:data[key] for key in ('location_id','location_name','start_url')},**config})
        elif 'multiline_questions' in config:
            add('native_survey_multiline_configuration',payload={
                **{key:data[key] for key in ('location_id','location_name','start_url')},**config})
        elif 'text_questions' in config:
            add('native_survey_text_configuration',payload={
                **{key:data[key] for key in ('location_id','location_name','start_url')},**config})
        elif 'object_fields' in config:
            add('native_survey_object_fields', payload={
                **{key:data[key] for key in ('location_id', 'location_name', 'start_url')}, **config})
        else:
            add('survey_rule_stack' if 'rules' in config else 'survey_configuration', **config)
    elif operation=='checkout.configure_ui':
        add('native_checkout_ui', payload=data)
    elif operation in ('checkout.configure_native','checkout.one_click_upsell') and data.get('adapter_capture'):
        add('native_checkout', payload=data)
    elif operation=='quizzes.create' and 'configuration' in data:
        from playwright_recipes.quiz_creation import payload_from_inputs
        add('native_quiz_creation',payload=payload_from_inputs(data))
    elif operation=='surveys.create' and 'question_batches' in data:
        from playwright_recipes.survey_creation import payload_from_inputs
        add('native_survey_creation',payload=payload_from_inputs(data))
    elif operation=='surveys.create' and 'radio_questions' in data:
        from playwright_recipes.survey_radio_creation import payload_from_inputs
        add('native_survey_radio_creation',payload=payload_from_inputs(data))
    elif operation in ('surveys.create','quizzes.create'):
        add('assessment',kind='survey' if operation=='surveys.create' else 'quiz',name=data['name'],allow_creation=data.get('allow_creation',False),standard_fields=data.get('standard_fields',[]))
        if operation=='quizzes.create' and not data.get('options') and not data.get('fixture'):
            raise Stop('A production marketing quiz needs a captured scoring/result/options profile')
    elif operation=='communities.create':
        add('community',**data['community'])
    elif operation=='communities.configure' and 'branding' in data:
        add('community_branding', payload=data)
    elif operation=='communities.configure' and 'course_associations' in data:
        add('community_courses', payload=data)
    elif operation=='communities.configure' and 'details' in data:
        add('community_details', payload=data)
    elif operation=='communities.configure' and 'channels' in data:
        add('community_channels', payload=data)
    elif operation=='communities.configure' and 'access' in data:
        add('community_access', payload=data)
    elif operation in ('meetings.setup','meetings.update'):
        details = dict(data['meeting'])
        if operation == 'meetings.update':
            if not isinstance(details.get('expected_room_id'),str) or not details['expected_room_id']:
                raise Stop('Meeting update requires the exact existing room identity')
            details['allow_creation'] = False
        if 'cohosts' in details:
            # Roster reconciliation is an independently inventoried operation.
            # Room metadata are expected unchanged values, never an earlier
            # write that could succeed before a later roster preflight fails.
            details['allow_creation'] = False if operation == 'meetings.update' else details.get('allow_creation')
            add('meeting_cohosts', payload={**{key:base[key] for key in ('location_id', 'location_name', 'start_url')}, **details})
        else:
            add('meeting',**details)
    elif operation == 'meetings.integrate' and data.get('integration_mode') == 'course_live_session':
        add('native_course_live_session', payload={key:value for key,value in data.items()
            if key not in ('integration_mode', 'auth_activation', 'publish')})
    elif operation == 'meetings.integrate' and data.get('integration_mode') == 'provider_oauth_handoff':
        add('native_provider_oauth_handoff', payload={key:value for key,value in data.items()
            if key != 'integration_mode'})
    elif operation == 'meetings.integrate' and data.get('integration_mode') == 'community_event_room':
        add('community_event_room', payload={key:value for key,value in data.items() if key != 'integration_mode'})
    elif operation == 'meetings.integrate' and data.get('integration_mode') == 'dynamic_calendar_room':
        add('native_dynamic_meeting_location', payload={key:value for key,value in data.items()
            if key not in ('integration_mode', 'publish', 'auth_activation')})
    elif operation == 'courses.configure_ui' and 'template_id' in data:
        add('native_course_video_blocks' if 'video_blocks' in data else 'native_course_image_blocks' if 'image_blocks' in data else 'native_course_section_media' if 'theme_images' in data else 'native_course_text_blocks' if 'text_blocks' in data else 'native_course_blocks' if 'custom_blocks' in data else 'native_course_theme_media' if 'background_image' in data or 'background_transparency' in data or 'background_removal' in data else 'native_course_block_media' if 'custom_block_image' in data else 'native_course_theme', payload=data)
    elif operation in ('forms.configure','checkout.one_click_upsell','funnels.split_variant','communities.configure','courses.configure_ui','meetings.integrate'):
        if operation=='checkout.one_click_upsell':
            receipt=data.get('checkout_contract',{})
            if receipt.get('status')!='PASS' or receipt.get('location_id')!=data['location_id'] or not all(receipt.get(k) for k in ('product_id','price_id','source_step_id','upsell_step_id','source')) or receipt.get('prior_payment_verified') is not True:
                raise Stop('Native upsell requires a location-bound Skill 44/79 product, price, source/upsell step and verified prior-payment contract')
        if not data.get('options'):
            raise Stop('This operation needs its recorded options profile; hand off for browser capture')
    elif operation in ('courses.create', 'courses.update', 'courses.lessons', 'courses.lesson_quiz.create'):
        raise Stop('API_ROUTE: Use the per-location Courses v3 capability probe and maintained host API executor')
    else:
        raise Stop('Unknown operation')
    if data.get('options'):
        add('options',**data['options'])
    return {**base,'steps':steps,'publish':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe',required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--evidence-root',type=Path)
    a=p.parse_args()
    try:
        job=validate_job(compile_recipe(a.recipe,json.loads(a.inputs.read_text())),a.inputs.resolve().parent)
        if not a.execute:
            print(json.dumps({'status':'VALIDATED_ONLY','recipe':a.recipe,'steps':len(job['steps'])}))
            return 0
        if a.evidence_root is None:
            raise Stop('Durable --evidence-root is required')
        result=execute(job,a.evidence_root)
        print(json.dumps({'status':result['status'],'recipe':a.recipe}))
        return 0 if result['status']=='EDITOR_STEPS_COMPLETE' else 3
    except (Stop,KeyError,ValueError,OSError) as exc:
        print(json.dumps({'status':'NEEDS_BROWSER_RECOVERY','error_type':type(exc).__name__,'reason':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
