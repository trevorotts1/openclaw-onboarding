#!/usr/bin/env python3
"""One deterministic entry point for OpenClaw/Claude-Nine Skill 6 hosts.

The host supplies actual tool capabilities. This adapter never invents shell
commands for extensions/MCP servers or converts UI success into funnel QC PASS.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import os
from collections.abc import Mapping


BROWSER_PROVIDERS = frozenset(('openclaw_extension', 'agent_browser', 'computer_use'))

if __package__:
    from .recipe_cli import compile_recipe
    from .evidence_lease import evidence_lease, journal_present, read_journal
    from .receipt_validation import minimal_objects, pending_proof
    from .native_payment_policy import validate_payment_inputs
    from .route import decide, recovery
    from .intake import captured_script_mode
    from .skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job
else:
    from recipe_cli import compile_recipe
    from evidence_lease import evidence_lease, journal_present, read_journal
    from receipt_validation import minimal_objects, pending_proof
    from native_payment_policy import validate_payment_inputs
    from route import decide, recovery
    from intake import captured_script_mode
    from skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job


def _terminal_auth_stop(operation, inputs, root, error_type, *, contract=False, browser_used=None):
    """Record a value-free terminal refusal; another lane cannot change identity."""
    status = 'STOP_AUTH_CONTEXT' if contract else 'STOP_AUTH'
    reason = 'AUTH_ACTIVATION_CONTRACT_UNVERIFIED' if contract else 'AUTH_IDENTITY_UNCONFIRMED'
    receipt = {'status':status, 'operation':operation,
        'location_id':inputs['location_id'], 'browser_used':not contract if browser_used is None else browser_used,
        'error_type':error_type, 'reason':reason,
        'route':{'lane':status, 'operation':operation,
                 'location_id':inputs['location_id'], 'reason':reason},
        'state_file':str(root/'auth-stop.json'),
        'instruction':'Preserve existing evidence. Confirm the same-session account and location before an explicitly reconciled new run; do not switch identities or execution lanes.'}
    if not journal_present(root/'auth-stop.json'):
        secure_json(root/'auth-stop.json', receipt)
    return receipt


def _provider_objects(operation, inputs, objects):
    """Bind receipts to every authored outline target, including on replay."""
    identities = minimal_objects(operation, objects)
    if operation == 'courses.lessons':
        if __package__:
            from .course_outline import _objects, validate_inputs
        else:
            from course_outline import _objects, validate_inputs
        expected = _objects(validate_inputs(inputs))
        actual_keys = sorted((obj['kind'], obj['id']) for obj in identities)
        expected_keys = sorted((obj['kind'], obj['id']) for obj in expected)
        if actual_keys != expected_keys:
            raise Stop('Course outline receipt does not match the exact requested targets')
    if operation == 'courses.update' and 'media_assets' in inputs:
        if __package__:
            from .course_media import validate_inputs
        else:
            from course_media import validate_inputs
        plan = validate_inputs(inputs)
        if identities != [{'kind':'course', 'id':plan['product_id']}]:
            raise Stop('Course media receipt does not match the exact requested course')
    return identities


def _execute_provider(operation, inputs, route, root, executor):
    """Share the editor lease so changing lanes cannot introduce a second writer."""
    replay_only = journal_present(root / 'provider-state.json')
    kind = 'provider_replay' if replay_only else 'provider'
    with evidence_lease(root, inputs['location_id'], kind=kind):
        return _execute_provider_owned(operation, inputs, route, root, executor,
                                       replay_only=replay_only)


def _execute_provider_owned(operation, inputs, route, root, executor, *, replay_only=False):
    """Execute only the installed provider callback, journaling before its write.

    This callback is supplied by the authenticated host. The adapter never
    invents a transport command or endpoint. An interrupted provider write is
    reconciled from the saved intent rather than repeated automatically.
    """
    path = root / 'provider-state.json'
    uses_browser = route['lane'] in BROWSER_PROVIDERS
    fingerprint = hashlib.sha256(json.dumps(
        {'operation': operation, 'inputs': inputs, 'route': route},
        sort_keys=True).encode()).hexdigest()
    if journal_present(path):
        prior = read_journal(path)
        if (not isinstance(prior, Mapping) or prior.get('fingerprint') != fingerprint
                or prior.get('operation') != operation
                or prior.get('location_id') != inputs['location_id']):
            raise Stop('Provider evidence belongs to another job')
        if prior.get('status') not in ('PROVIDER_NEEDS_VERIFICATION', 'PROVIDER_STEPS_COMPLETE'):
            raise Stop('Interrupted provider operation requires reconciliation')
        saved = prior.get('outcome')
        if (not isinstance(saved, Mapping)
                or saved.get('location_id') != inputs['location_id']
                or saved.get('status') not in ('EDITOR_STEPS_COMPLETE', 'NEEDS_VERIFICATION',
                                                'API_STEPS_COMPLETE', 'ALREADY_EXECUTED')
                or saved.get('verification_required') is not True
                or (uses_browser and saved.get('status') == 'API_STEPS_COMPLETE')):
            raise Stop('Saved provider outcome is malformed or belongs to another location')
        objects = _provider_objects(operation, inputs, saved.get('objects'))
        pending = prior['status'] == 'PROVIDER_NEEDS_VERIFICATION' or pending_proof(saved)
        # A journal may predate today's outcome whitelist. Validate its binding,
        # then return only minimal identities/status, never arbitrary saved data.
        outcome = {'status': 'NEEDS_VERIFICATION' if pending else saved['status'],
                   'location_id': inputs['location_id'],
                   'objects': [{'kind': obj['kind'], 'id': obj['id']} for obj in objects],
                   'verification_required': True}
        return {'status': 'NEEDS_VERIFICATION' if pending else 'ALREADY_EXECUTED',
                'route': route, 'browser_used': False, 'result': outcome,
                'replayed': True}
    if replay_only:
        raise Stop('Provider replay journal disappeared; reconciliation required')
    if any(journal_present(root / name) for name in ('delivery-state.json', 'calendar-delivery-state.json')):
        raise Stop('Direct API outcome must be reconciled before provider execution')
    state = {'fingerprint': fingerprint, 'operation': operation,
             'location_id': inputs['location_id'], 'status': 'PROVIDER_INTENT_RECORDED'}
    secure_json(path, state)
    try:
        result = executor(operation=operation, inputs=deepcopy(inputs),
                          route=deepcopy(route), evidence_root=root)
        if not isinstance(result, Mapping) or result.get('location_id') != inputs['location_id']:
            raise Stop('Provider result must independently identify the requested location')
        status = result.get('status')
        if status not in ('EDITOR_STEPS_COMPLETE', 'NEEDS_VERIFICATION', 'API_STEPS_COMPLETE', 'ALREADY_EXECUTED'):
            raise Stop('Provider did not return a recognized completion status')
        if uses_browser and status == 'API_STEPS_COMPLETE':
            raise Stop('Browser provider must report its actual editor outcome')
        # A host callback cannot turn explicit missing functional/read-back
        # evidence into completion merely by selecting a stronger status label.
        if any(result.get(key) is False for key in (
            'behavior_verified', 'submission_verified', 'payment_verified',
            'functional_verified', 'checkout_ready')) or any(
                result.get(key) == 'REQUIRED' for key in (
                    'independent_readback', 'behavior_verification')):
            status = 'NEEDS_VERIFICATION'
        # Do not persist arbitrary API responses, credential strings or logs.
        objects = _provider_objects(operation, inputs, result.get('objects', []))
        outcome = {'status': status, 'location_id': inputs['location_id'],
                   'objects': [{'kind':obj['kind'], 'id':obj['id']} for obj in objects],
                   'verification_required': True}
        state.update(status='PROVIDER_NEEDS_VERIFICATION' if status == 'NEEDS_VERIFICATION' else 'PROVIDER_STEPS_COMPLETE', outcome=outcome)
        secure_json(path, state)
        return {'status': status, 'route': route, 'browser_used': uses_browser,
                'result': outcome}
    except Exception as exc:
        state.update(status='PROVIDER_RECONCILIATION_REQUIRED', error_type=type(exc).__name__)
        secure_json(path, state)
        raise


def _recipe_readiness(operation, inputs, probes, input_dir):
    """Only a validated, target-bound capture makes this job script-ready."""
    observed = deepcopy(probes)
    native = operation in ('checkout.configure_native','checkout.one_click_upsell') and bool(inputs.get('adapter_capture'))
    recorded = bool(inputs.get('options'))
    ui = (operation in ('checkout.configure_ui', 'courses.configure_ui')
          or operation == 'meetings.integrate' and inputs.get('integration_mode') in ('dynamic_calendar_room', 'course_live_session', 'provider_oauth_handoff'))
    event = operation == 'meetings.integrate' and inputs.get('integration_mode') == 'community_event_room'
    portal = operation == 'communities.configure' and bool(set(inputs).intersection({'channels', 'details', 'access', 'course_associations', 'branding'}))
    captured = captured_script_mode(operation, inputs)
    if not native and not recorded and not ui and not portal and not event and not captured:
        return observed, None
    # A receipt for another input/profile cannot bless this specific capture.
    profiles = observed.get('recorded_profiles', [])
    if not isinstance(profiles, (list, tuple)):
        profiles = []
    observed['recorded_profiles'] = [entry for entry in profiles if entry != operation]
    try:
        validate_job(compile_recipe(operation, inputs), Path(input_dir))
        if native:
            if __package__:
                from .pages_checkout import load_checkout_capture
            else:
                from pages_checkout import load_checkout_capture
            path = (Path(input_dir) / inputs['adapter_capture']).resolve()
            load_checkout_capture(path, location_id=inputs['location_id'], page_id=inputs['page_id'])
        observed['recorded_profiles'].append(operation)
        return observed, None
    except Exception as exc:
        # Invalid job/capture is never promoted solely because a path exists.
        lanes = observed.get('lanes', {})
        if isinstance(lanes, dict):
            lanes = deepcopy(lanes)
            lanes['playwright'] = {'available': False}
            observed['lanes'] = lanes
        return observed, type(exc).__name__


def run_recipe(operation, inputs, probes, evidence_root, *, input_dir, page=None, executors=None, portal_context=None, access_authorization=None):
    if not isinstance(inputs, Mapping) or not isinstance(inputs.get('location_id'), str) or not inputs['location_id']:
        return {'status': 'STOP_INVALID_INPUT', 'browser_used': False,
                'reason': 'A location-bound input mapping is required'}
    policy_error = validate_payment_inputs(operation, inputs)
    if policy_error:
        route = decide(operation, inputs['location_id'], probes, inputs=inputs)
        return {'status': 'STOP_INVALID_INPUT', 'route': route, 'browser_used': False, 'reason': policy_error}
    access_mode = operation == 'communities.configure' and 'access' in inputs
    course_association_mode = operation == 'communities.configure' and 'course_associations' in inputs
    branding_mode = operation == 'communities.configure' and 'branding' in inputs
    event_mode = operation == 'meetings.integrate' and inputs.get('integration_mode') == 'community_event_room'
    contact_mode = operation == 'forms.configure' and 'contact_field_plan' in inputs
    survey_radio_mode = operation == 'surveys.create' and bool({'radio_questions','question_batches'}.intersection(inputs))
    captured_mode = captured_script_mode(operation, inputs)
    if event_mode and 'auth_activation' in inputs:
        return {'status':'STOP_INVALID_INPUT','browser_used':False,
                'reason':'Event room integrations require the caller-owned authenticated portal session; no fresh app seed is permitted'}
    if access_authorization is not None and not access_mode:
        return {'status':'STOP_INVALID_INPUT', 'browser_used':False,
                'reason':'A live access authorization applies only to its exact community access operation'}
    if 'auth_activation' in inputs and (page is not None or portal_context is not None or access_authorization is not None):
        return {'status': 'STOP_INVALID_INPUT', 'browser_used': False,
                'reason': 'Fresh authentication activation cannot use a supplied browser or portal context'}
    auth_stop = Path(evidence_root).resolve()/'auth-stop.json'
    if journal_present(auth_stop):
        return {'status':'STOP_AUTH_CONTEXT', 'browser_used':False,
                'reason':'AUTH_IDENTITY_RECONCILIATION_REQUIRED',
                'route':{'lane':'STOP_AUTH_CONTEXT','operation':operation},
                'state_file':str(auth_stop)}
    if not isinstance(probes, Mapping):
        return {'status': 'STOP_INVALID_PROBE', 'browser_used': False}
    if executors is not None and not isinstance(executors, Mapping):
        return {'status': 'STOP_INVALID_INPUT', 'browser_used': False,
                'reason': 'Installed executors must be a provider mapping'}
    observed, capture_error = _recipe_readiness(operation, inputs, probes, input_dir)
    if capture_error and 'auth_activation' in inputs:
        return _terminal_auth_stop(operation, inputs, Path(evidence_root).resolve(), capture_error, contract=True)
    route = decide(operation, inputs['location_id'], observed, inputs=inputs)
    script_lane = (route['lane'] == 'playwright' or
        route['lane'] in BROWSER_PROVIDERS and page is not None)
    if event_mode and not script_lane:
        status = 'STOP_INVALID_INPUT' if capture_error else route['lane'] if route['lane'].startswith('STOP_AUTH') else 'EVENT_SCRIPT_ROUTE_REQUIRED'
        return {'status':status,'route':route,'browser_used':False,
                'reason':'Community event room creation requires its captured script, own journal, and live same-session portal context; another provider cannot authorize it'}
    if branding_mode and not script_lane:
        return {'status':'STOP_INVALID_INPUT' if capture_error else 'BRANDING_SCRIPT_ROUTE_REQUIRED',
                'route':route, 'browser_used':False,
                'reason':'Community Branding requires the captured native script and live same-session portal context'}
    if course_association_mode and not script_lane:
        return {'status':'STOP_INVALID_INPUT' if capture_error else 'COURSE_ASSOCIATION_SCRIPT_ROUTE_REQUIRED',
                'route':route, 'browser_used':False,
                'reason':'Community course associations require the captured script and live same-session portal context; a generic capability or provider cannot authorize this native operation'}
    if access_mode and not script_lane:
        return {'status':'STOP_INVALID_INPUT' if capture_error else 'ACCESS_SCRIPT_ROUTE_REQUIRED',
                'route':route, 'browser_used':False,
                'reason':'Invalid community access configuration' if capture_error else
                    'Community access requires its captured native script and live same-session host context; an authorization cannot be delegated to another lane',
                **({'error_type':capture_error} if capture_error else {})}
    if captured_mode and not script_lane:
        status = ('STOP_INVALID_INPUT' if capture_error else route['lane']
            if route['lane'].startswith('STOP_AUTH') else 'CAPTURED_SCRIPT_ROUTE_REQUIRED')
        return {'status':status,'route':route,'browser_used':False,
                'reason':'Native editor jobs require the maintained compiled leaf and owned receipt journal. Supply a compatible caller-owned Page for a measured browser transport; generic provider callback statuses are not native proof',
                **({'instruction': route['native_payment_policy']['instruction'] + ' ' + route['native_payment_policy']['verification']} if route.get('native_payment_policy') else {})}
    if contact_mode and not journal_present(Path(evidence_root).resolve()/'state.json'):
        try:
            from playwright_recipes.contact_field_frontdoor import validate_capability, payload_from_inputs
            validate_capability({'payload':payload_from_inputs(inputs)}, observed.get('contact_field_capability'))
        except Exception as exc:
            return {'status':'CONTACT_FIELD_CAPABILITY_REQUIRED', 'route':route,
                'browser_used':False, 'error_type':type(exc).__name__,
                'reason':'A fresh same-location Contact v3 capability with the requested read/write scopes is required before browser or API execution'}
    if survey_radio_mode and not journal_present(Path(evidence_root).resolve()/'state.json'):
        try:
            from playwright_recipes.survey_radio_creation import validate_runtime
            validate_runtime(compile_recipe(operation,inputs),observed.get('radio_field_capability'))
        except Exception as exc:
            return {'status':'RADIO_FIELD_CAPABILITY_REQUIRED','route':route,'browser_used':False,'error_type':type(exc).__name__}
    if 'auth_activation' in inputs and route['lane'] != 'playwright':
        return {'status':'STOP_FRESH_ACTIVATION_REQUIRED', 'route':route,
                'browser_used':False,
                'reason':'Fresh managed authentication activation cannot be delegated to another execution lane'}
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    journals = ('state.json', 'provider-state.json', 'community-portal-state.json', 'community-details-state.json', 'community-access-state.json', 'community-event-state.json', 'handoff.json', 'auth-stop.json')
    if not any(journal_present(root / name) for name in journals):
        secure_json(root / 'route.json', route)
    if route['lane'] != 'playwright' and not (captured_mode and script_lane):
        provider = (executors or {}).get(route['lane'])
        if provider is None and operation == 'courses.lessons' and route['lane'] in ('public_api','skill44') and inputs.get('api_capability'):
            if __package__:
                from .course_outline import course_outline_executor
            else:
                from course_outline import course_outline_executor
            provider = course_outline_executor
        if provider is None and operation in ('courses.create','courses.update','courses.lesson_quiz.create') and route['lane'] in ('public_api','skill44') and inputs.get('api_capability'):
            # Reuse the course implementation's real Skill 44 transport. An
            # official-MCP route always requires its actual injected MCP tool.
            if operation == 'courses.update' and 'media_assets' in inputs:
                if __package__:
                    from .course_media import course_executor
                else:
                    from course_media import course_executor
            elif __package__:
                from .delivery import course_executor
            else:
                from delivery import course_executor
            provider = course_executor
        if provider is None and operation == 'meetings.integrate' and inputs.get('integration_mode') == 'permanent_calendar_link' and route['lane'] in ('public_api','skill44') and all(inputs.get(key) for key in ('calendar_id','room','api_capability')):
            if __package__:
                from .delivery import meeting_calendar_executor
            else:
                from delivery import meeting_calendar_executor
            provider = meeting_calendar_executor
        if route['lane'] in ('public_api', 'official_mcp', 'skill44', *BROWSER_PROVIDERS) and callable(provider):
            invoked = False
            def execute_tracked(**kwargs):
                nonlocal invoked
                invoked = True
                return provider(**kwargs)
            try:
                return _execute_provider(operation, inputs, route, root, execute_tracked)
            except Exception as exc:
                from ghl_auth import AuthBridgeError
                if isinstance(exc, AuthBridgeError):
                    return _terminal_auth_stop(operation, inputs, root, type(exc).__name__,
                        browser_used=invoked and route['lane'] in BROWSER_PROVIDERS)
                blocked_state = root / 'state.json'
                if not journal_present(blocked_state):
                    blocked_state = next((root / name for name in (
                        'handoff.json', 'community-portal-state.json', 'community-details-state.json', 'community-access-state.json', 'community-event-state.json', 'provider-state.json',
                        'delivery-state.json', 'calendar-delivery-state.json')
                        if journal_present(root / name)), root / 'provider-state.json')
                return {'status': 'PROVIDER_RECONCILIATION_REQUIRED', 'route': route,
                        'browser_used': invoked and route['lane'] in BROWSER_PROVIDERS,
                        'error_type': type(exc).__name__,
                        'state_file': str(blocked_state)}
        return {'status': 'NEEDS_BROWSER_RECOVERY' if capture_error else 'HANDOFF_REQUIRED', 'route': route, 'browser_used': False, **({'error_type':capture_error} if capture_error else {}), **({'instruction': route['native_payment_policy']['instruction'] + ' ' + route['native_payment_policy']['verification']} if route.get('native_payment_policy') else {})}
    try:
        try:
            job = validate_job(compile_recipe(operation, inputs), Path(input_dir))
        except Exception as exc:
            if 'auth_activation' in inputs:
                return _terminal_auth_stop(operation, inputs, root, type(exc).__name__, contract=True)
            raise
        if event_mode:
            if page is None or portal_context is None:
                return {'status':'PORTAL_CONTEXT_REQUIRED','route':route,'browser_used':False,
                        'reason':'Supply the authenticated caller-owned event portal Page and opaque same-session context; no app/browser seeding attempted'}
            if __package__:
                from .skill6_playwright import community_event_room
            else:
                from skill6_playwright import community_event_room
            result = community_event_room(page, job['steps'][0],
                portal_context=portal_context, evidence_root=root)
            return {'status':result['status'],'route':route,'browser_used':True,'result':result}
        if operation == 'communities.configure' and set(inputs).intersection({'channels', 'details', 'access', 'course_associations', 'branding'}):
            if page is None or portal_context is None:
                return {'status': 'PORTAL_CONTEXT_REQUIRED', 'route': route,
                        'browser_used': False,
                        'reason': 'Supply an authenticated caller-owned portal Page and same-session identity context; no login or token seed attempted'}
            if __package__:
                from .skill6_playwright import community_channels, community_details, community_access, community_courses, community_branding
            else:
                from skill6_playwright import community_channels, community_details, community_access, community_courses, community_branding
            handler = community_access if access_mode else community_branding if branding_mode else community_courses if 'course_associations' in inputs else community_details if 'details' in inputs else community_channels
            arguments = {'portal_context':portal_context, 'evidence_root':root}
            if access_mode:
                arguments['access_authorization'] = access_authorization
            result = handler(page, job['steps'][0], **arguments)
            return {'status': result['status'], 'route': route,
                    'browser_used': True, 'result': result}
        contact_arguments = ({'contact_field_capability':observed.get('contact_field_capability')}
            if operation == 'forms.configure' and 'contact_field_plan' in inputs else {})
        if survey_radio_mode:contact_arguments['radio_field_capability']=observed.get('radio_field_capability')
        result = (run_on_page(page, job, root, **contact_arguments) if page is not None
            else execute(job, root, **contact_arguments))
        return {'status': result['status'], 'route': route, 'result': result}
    except Exception as exc:
        # Raw errors may quote client text or credentials. Persist type only.
        from ghl_auth import AuthBridgeError
        if isinstance(exc, AuthBridgeError):
            return _terminal_auth_stop(operation, inputs, root, type(exc).__name__)
        if event_mode:
            blocked = next((root / name for name in (
                'community-event-state.json','state.json','provider-state.json',
                'community-portal-state.json','community-details-state.json','community-access-state.json',
                'delivery-state.json','calendar-delivery-state.json','handoff.json','auth-stop.json')
                if journal_present(root / name)),None)
            return {'status':'EVENT_RECONCILIATION_REQUIRED' if blocked is not None else 'EVENT_PREFLIGHT_REFUSED',
                'route':route,'browser_used':page is not None,'error_type':type(exc).__name__,
                **({'state_file':str(blocked)} if blocked is not None else {}),
                'instruction':'Preserve evidence and read the same event/room before another attempt; do not rerun room creation or switch execution lanes.'}
        if access_mode and isinstance(exc, Stop) and str(exc).startswith('ACCESS_CONFIRMATION_REQUIRED:'):
            result = {'status':'ACCESS_CONFIRMATION_REQUIRED', 'route':route, 'browser_used':True,
                      'reason':'Fresh same-session authorization for this exact access expansion is required; no alternative execution lane is authorized'}
            if journal_present(root / 'community-access-state.json'):
                result['state_file'] = str(root / 'community-access-state.json')
                result['instruction'] = 'Reconcile the retained access intent before another write.'
            return result
        expected_state = root / ('community-access-state.json' if access_mode else 'community-details-state.json' if operation == 'communities.configure' and bool(set(inputs).intersection({'details', 'course_associations', 'branding'})) else 'community-portal-state.json' if operation == 'communities.configure' and 'channels' in inputs else 'state.json')
        blocked_state = next((root / name for name in (
            'state.json', 'provider-state.json', 'community-portal-state.json', 'community-details-state.json', 'community-access-state.json', 'community-event-state.json')
            if journal_present(root / name)), expected_state)
        handoff = {
            'status': 'NEEDS_BROWSER_RECOVERY', 'operation': operation,
            'location_id': inputs['location_id'], 'error_type': type(exc).__name__,
            'route': recovery(operation, inputs['location_id'], observed, inputs=inputs),
            'state_file': str(blocked_state),
            'instruction': 'Inspect recorded objects and the failed step. Do not rerun a create/save until its persisted outcome is reconciled.',
        }
        if handoff['route'].get('native_payment_policy'):
            policy = handoff['route']['native_payment_policy']
            handoff['instruction'] += ' ' + policy['instruction'] + ' ' + policy['verification']
        if not journal_present(root / 'handoff.json'):
            secure_json(root / 'handoff.json', handoff)
        return handoff


def main(argv=None):
    """Agent-host CLI; route and validate first, then execute the selected lane."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--probes', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Validate and select a lane without opening a browser or writing evidence')
    args = parser.parse_args(argv)
    try:
        inputs = json.loads(args.inputs.read_text())
        probes = json.loads(args.probes.read_text())
        if args.check:
            observed, capture_error = _recipe_readiness(args.operation, inputs, probes, args.inputs.resolve().parent)
            selected = decide(args.operation, inputs['location_id'], observed, inputs=inputs)
            if 'auth_activation' in inputs and selected['lane'] != 'playwright':
                print(json.dumps({'status':'STOP_FRESH_ACTIVATION_REQUIRED',
                                  'route':selected, 'browser_used':False}))
                return 2
            if capture_error and selected['lane'] not in ('public_api','skill44','official_mcp'):
                print(json.dumps({'status':'STOP_INVALID_CAPTURE', 'route':selected,
                                  'error_type':capture_error, 'browser_used':False}))
                return 2
            status = 'ROUTE_VALIDATED_ONLY'
            if selected['lane'] == 'playwright':
                job = validate_job(compile_recipe(args.operation, inputs), args.inputs.resolve().parent)
                if args.operation == 'surveys.create' and bool({'radio_questions','question_batches'}.intersection(inputs)):
                    from playwright_recipes.survey_radio_creation import validate_runtime
                    validate_runtime(job,observed.get('radio_field_capability'))
                if args.operation == 'forms.configure' and 'contact_field_plan' in inputs:
                    from playwright_recipes.contact_field_frontdoor import validate_capability
                    validate_capability(job['steps'][0], observed.get('contact_field_capability'))
                status = 'PORTAL_CONTEXT_REQUIRED' if (args.operation == 'communities.configure' and ('channels' in inputs or 'details' in inputs) or args.operation == 'meetings.integrate' and inputs.get('integration_mode') == 'community_event_room') else 'VALIDATED_ONLY'
            elif selected['lane'] in ('public_api','skill44','official_mcp') and args.operation in ('courses.create','courses.update','courses.lesson_quiz.create'):
                if args.operation == 'courses.update' and 'media_assets' in inputs:
                    if __package__:
                        from .course_media import validate_api_inputs
                    else:
                        from course_media import validate_api_inputs
                elif __package__:
                    from .delivery import validate_api_inputs
                else:
                    from delivery import validate_api_inputs
                validate_api_inputs(args.operation, inputs, selected)
                status = 'VALIDATED_ONLY'
            elif selected['lane'] in ('public_api','skill44','official_mcp') and args.operation == 'courses.lessons':
                if __package__:
                    from .course_outline import validate_api_inputs
                else:
                    from course_outline import validate_api_inputs
                validate_api_inputs(args.operation, inputs, selected)
                status = 'VALIDATED_ONLY'
            elif selected['lane'] in ('public_api','skill44','official_mcp') and args.operation == 'meetings.integrate' and inputs.get('integration_mode') == 'permanent_calendar_link':
                if __package__:
                    from .delivery import validate_calendar_integration
                else:
                    from delivery import validate_calendar_integration
                validate_calendar_integration(inputs, selected)
                status = 'VALIDATED_ONLY'
            elif selected['lane'] == 'PROBE_API':
                status = 'API_PROBE_REQUIRED'
            elif selected['lane'].startswith('STOP_'):
                status = selected['lane']
            print(json.dumps({'status':status, 'route':selected,
                              'browser_used':False}))
            return 2 if selected['lane'].startswith('STOP_') or status in ('API_PROBE_REQUIRED', 'PORTAL_CONTEXT_REQUIRED') else 0
        result = run_recipe(args.operation, inputs, probes, args.evidence_root,
                            input_dir=args.inputs.resolve().parent)
        # Print a small named receipt; provider payloads never reach stdout.
        print(json.dumps({'status':result['status'], 'route':result.get('route'),
                          'browser_used':result.get('browser_used', result.get('route',{}).get('lane') == 'playwright')}))
        if result['status'] in ('EDITOR_STEPS_COMPLETE','API_STEPS_COMPLETE'):
            return 0
        if result['status'] in ('NEEDS_VERIFICATION','ALREADY_EXECUTED'):
            return 3
        return 2
    except Exception as exc:
        print(json.dumps({'status':'STOP_INVALID_INPUT', 'error_type':type(exc).__name__,
                          'browser_used':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
