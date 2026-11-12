#!/usr/bin/env python3
"""Choose an execution lane for one exact operation, using current host probes.

This is a deterministic decision engine. The caller executes the selected API
provider or script. A recovery result is consumed by the host's installed
OpenClaw/Agent Browser tools, never by a guessed shell command.
"""
import json
from pathlib import Path
import time
from collections.abc import Mapping

if __package__:
    from .native_payment_policy import apply_payment_policy, validate_payment_inputs
    from .intake import captured_script_mode
else:
    from native_payment_policy import apply_payment_policy, validate_payment_inputs
    from intake import captured_script_mode


API_OPERATIONS = {
    'funnels.list','pages.list','redirects.manage','forms.list','forms.submissions',
    'surveys.list','surveys.submissions','courses.create','courses.update',
    'courses.lessons','courses.lesson_quiz','courses.lesson_quiz.create','products.manage','prices.manage',
    'tags.manage','fields.manage','media.manage','calendars.appointments',
}


def from_capability_probe(report, *, api_capabilities=None, recorded_profiles=(), computer_use_enabled=False):
    """Consume the existing probe's measured eligible routes, not CLI guesses.

    Its box-default ordering is historical; exact-operation routing below owns
    recipe selection. The probe already gates extension currency and version.
    """
    if not isinstance(report, dict):
        report = {}
    browser = report.get('operationCapabilities',{}).get('transports',{}).get('browser',{})
    routes = browser.get('routes',[])
    return {
        'api_capabilities': api_capabilities or {},
        'recorded_profiles': list(recorded_profiles),
        'lanes': {
            'playwright': {'available':'playwright_direct' in routes},
            'openclaw_extension': {'available':'openclaw_managed_browser' in routes, 'current':'openclaw_managed_browser' in routes},
            'agent_browser': {'available':'agent_browser' in routes},
            'computer_use': {'available':report.get('lanes',{}).get('cua',{}).get('driverPresent') is True,'enabled':computer_use_enabled},
        },
    }


def _decide(operation, location_id, probes, catalog=None, failed_lanes=(), inputs=None):
    catalog = catalog or json.loads((Path(__file__).parent/'catalog.json').read_text())
    if not isinstance(operation, str) or not isinstance(location_id, str) or not location_id:
        return {'lane':'STOP_INVALID_INPUT','reason':'Operation and location ID are required'}
    if operation not in API_OPERATIONS and operation not in catalog.get('recipes', {}):
        return {'lane':'STOP_UNKNOWN_OPERATION','operation':operation}
    if not isinstance(probes, dict) or not isinstance(probes.get('api_capabilities', {}), dict):
        return {'lane':'STOP_INVALID_PROBE','operation':operation}
    context = inputs if isinstance(inputs, Mapping) else {}
    captured_mode = captured_script_mode(operation, context)
    calendar_mode = operation == 'meetings.integrate' and context.get('integration_mode') == 'permanent_calendar_link'
    if operation == 'meetings.integrate':
        mode = context.get('integration_mode')
        if mode is not None and mode not in ('permanent_calendar_link', 'dynamic_calendar_room', 'community_event_room', 'course_live_session', 'provider_oauth_handoff'):
            return {'lane':'STOP_UNSUPPORTED_INTEGRATION_MODE','operation':operation,
                    'reason':'Meeting integration requires a separately captured implementation'}
        if mode is None and not context.get('options'):
            return {'lane':'STOP_INTEGRATION_MODE_REQUIRED','operation':operation,
                    'reason':'Choose explicit permanent_calendar_link for calendar API integration; captured options remain a separate UI route'}
    failed = set(failed_lanes)
    caps = probes.get('api_capabilities',{})
    cap = caps.get(operation,{})
    if not isinstance(cap, dict):
        return {'lane':'STOP_INVALID_PROBE','operation':operation}
    fresh = type(cap.get('observed_at')) in (int,float) and 0 <= time.time()-cap['observed_at'] <= 3600
    bound = cap.get('location_id') == location_id and fresh
    if bound and cap.get('http_status') in (401,403):
        return {'lane':'STOP_AUTH','reason':'Credential/scope refusal; do not treat it as an unsupported API or try another identity'}
    portal_course_mode = operation == 'communities.configure' and bool(set(context).intersection({'course_associations', 'branding'}))
    api_eligible = (operation in API_OPERATIONS or calendar_mode) and not portal_course_mode and not captured_mode
    if api_eligible and bound and cap.get('supported') is True and cap.get('provider') in ('public_api','official_mcp','skill44') and cap.get('scope_ok') is True and cap.get('version'):
        return {'lane':cap['provider'],'operation':operation,'version':cap['version'],'location_id':location_id}
    if (operation in API_OPERATIONS or calendar_mode) and not (bound and cap.get('supported') is False and cap.get('reason') in ('unsupported_endpoint','location_feature_unavailable')):
        return {'lane':'PROBE_API','operation':operation,'reason':'Resolve exact supported endpoint, version, token scopes and tenant before opening the editor'}
    if calendar_mode:
        return {'lane':'STOP_UNSUPPORTED_CALENDAR_API','operation':operation,
                'reason':'A permanent calendar link cannot silently become a dynamic/UI integration'}
    entry = catalog['recipes'].get(operation)
    if entry is None:
        return {'lane':'STOP_UNKNOWN_OPERATION','operation':operation}
    if not isinstance(probes.get('lanes', {}), dict):
        return {'lane':'STOP_INVALID_PROBE','operation':operation}
    for lane in ('playwright','openclaw_extension','agent_browser','computer_use'):
        state = probes.get('lanes',{}).get(lane,{})
        if not isinstance(state, dict):
            return {'lane':'STOP_INVALID_PROBE','operation':operation}
        if lane in failed or state.get('available') is not True:
            continue
        if lane == 'openclaw_extension' and state.get('current') is not True:
            continue
        if lane == 'playwright' and not entry.get('implemented'):
            continue
        if lane == 'playwright':
            native_theme = (entry.get('action') == 'native_course_theme_or_options'
                            and 'template_id' in context and 'options' not in context)
            native_dynamic = (operation == 'meetings.integrate'
                              and context.get('integration_mode') in ('dynamic_calendar_room', 'community_event_room', 'course_live_session', 'provider_oauth_handoff')
                              and 'options' not in context)
            if (entry.get('action') in ('options', 'native_course_theme_or_options')
                    and not native_theme and not native_dynamic and operation not in probes.get('recorded_profiles', [])):
                continue
        if lane == 'computer_use' and state.get('enabled') is not True:
            continue
        return {'lane':lane,'operation':operation,'recipe':entry['name'],'proof':entry['proof'],'location_id':location_id,'resume':'Read recorded object IDs before repeating any create/save'}
    return {'lane':'STOP_NO_LANE','operation':operation}


def decide(operation, location_id, probes, catalog=None, failed_lanes=(), inputs=None):
    reason = validate_payment_inputs(operation, inputs)
    if reason:
        return apply_payment_policy(operation, {'lane': 'STOP_INVALID_INPUT', 'operation': operation, 'reason': reason})
    result = apply_payment_policy(operation, _decide(operation, location_id, probes, catalog, failed_lanes, inputs))
    if result.get('native_payment_policy') and result.get('lane') in ('playwright', 'openclaw_extension', 'agent_browser', 'computer_use'):
        result['instruction'] = result['native_payment_policy']['instruction'] + ' ' + result['native_payment_policy']['verification']
    return result


def recovery(operation, location_id, probes, failed_lanes=('playwright',), inputs=None):
    return decide(operation,location_id,probes,failed_lanes=failed_lanes,inputs=inputs)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--operation',required=True)
    p.add_argument('--location-id',required=True)
    p.add_argument('--probes',type=Path,required=True)
    p.add_argument('--inputs',type=Path,help='Operation input context, required for explicit integration modes')
    a=p.parse_args()
    print(json.dumps(decide(a.operation,a.location_id,json.loads(a.probes.read_text()),inputs=json.loads(a.inputs.read_text()) if a.inputs else None)))
