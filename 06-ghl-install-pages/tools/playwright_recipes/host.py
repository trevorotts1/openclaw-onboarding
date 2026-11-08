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
import fcntl
from collections.abc import Mapping

if __package__:
    from .recipe_cli import compile_recipe
    from .route import decide, recovery
    from .skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job
else:
    from recipe_cli import compile_recipe
    from route import decide, recovery
    from skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job


def _execute_provider(operation, inputs, route, root, executor):
    """One writer per evidence root, including caller-injected provider paths."""
    fd = os.open(root / 'provider.lock', os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('Provider evidence root is already leased') from None
        return _execute_provider_owned(operation, inputs, route, root, executor)
    finally:
        os.close(fd)


def _execute_provider_owned(operation, inputs, route, root, executor):
    """Execute only the installed provider callback, journaling before its write.

    This callback is supplied by the authenticated host. The adapter never
    invents a transport command or endpoint. An interrupted provider write is
    reconciled from the saved intent rather than repeated automatically.
    """
    path = root / 'provider-state.json'
    fingerprint = hashlib.sha256(json.dumps(
        {'operation': operation, 'inputs': inputs, 'route': route},
        sort_keys=True).encode()).hexdigest()
    if path.exists():
        prior = json.loads(path.read_text())
        if prior.get('fingerprint') != fingerprint:
            raise Stop('Provider evidence belongs to another job')
        if prior.get('status') == 'PROVIDER_NEEDS_VERIFICATION' or (prior.get('status') == 'PROVIDER_STEPS_COMPLETE' and prior.get('outcome', {}).get('status') == 'NEEDS_VERIFICATION'):
            return {'status': 'NEEDS_VERIFICATION', 'route': route,
                    'browser_used': False, 'result': prior['outcome'],
                    'replayed': True}
        if prior.get('status') == 'PROVIDER_STEPS_COMPLETE':
            return {'status': 'ALREADY_EXECUTED', 'route': route,
                    'browser_used': False, 'result': prior['outcome']}
        raise Stop('Interrupted provider operation requires reconciliation')
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
        # Do not persist arbitrary API responses, credential strings or logs.
        objects = result.get('objects', [])
        allowed_kinds = {'course','category','lesson','quiz','question','page','form',
                         'website','funnel','room','community','channel','calendar'}
        if not isinstance(objects, list) or any(
            not isinstance(obj, Mapping) or obj.get('kind') not in allowed_kinds or
            not isinstance(obj.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', obj['id'])
            for obj in objects):
            raise Stop('Provider object identity receipt malformed')
        if operation.endswith('.create') and not objects:
            raise Stop('Create completion requires concrete object identities')
        outcome = {'status': status, 'location_id': inputs['location_id'],
                   'objects': [{'kind':obj['kind'], 'id':obj['id']} for obj in objects],
                   'verification_required': True}
        state.update(status='PROVIDER_NEEDS_VERIFICATION' if status == 'NEEDS_VERIFICATION' else 'PROVIDER_STEPS_COMPLETE', outcome=outcome)
        secure_json(path, state)
        return {'status': status, 'route': route, 'browser_used': False,
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
    ui = operation == 'checkout.configure_ui'
    if not native and not recorded and not ui:
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


def run_recipe(operation, inputs, probes, evidence_root, *, input_dir, page=None, executors=None):
    if not isinstance(inputs, Mapping) or not isinstance(inputs.get('location_id'), str) or not inputs['location_id']:
        return {'status': 'STOP_INVALID_INPUT', 'browser_used': False,
                'reason': 'A location-bound input mapping is required'}
    if not isinstance(probes, Mapping):
        return {'status': 'STOP_INVALID_PROBE', 'browser_used': False}
    if executors is not None and not isinstance(executors, Mapping):
        return {'status': 'STOP_INVALID_INPUT', 'browser_used': False,
                'reason': 'Installed executors must be a provider mapping'}
    observed, capture_error = _recipe_readiness(operation, inputs, probes, input_dir)
    route = decide(operation, inputs['location_id'], observed, inputs=inputs)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    secure_json(root / 'route.json', route)
    if route['lane'] != 'playwright':
        provider = (executors or {}).get(route['lane'])
        if provider is None and operation in ('courses.create','courses.update','courses.lesson_quiz.create') and route['lane'] in ('public_api','skill44') and inputs.get('api_capability'):
            # Reuse the course implementation's real Skill 44 transport. An
            # official-MCP route always requires its actual injected MCP tool.
            if __package__:
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
        if route['lane'] in ('public_api', 'official_mcp', 'skill44') and callable(provider):
            try:
                return _execute_provider(operation, inputs, route, root, provider)
            except Exception as exc:
                return {'status': 'PROVIDER_RECONCILIATION_REQUIRED', 'route': route,
                        'browser_used': False, 'error_type': type(exc).__name__,
                        'state_file': str(root / 'provider-state.json')}
        return {'status': 'NEEDS_BROWSER_RECOVERY' if capture_error else 'HANDOFF_REQUIRED', 'route': route, 'browser_used': False, **({'error_type':capture_error} if capture_error else {})}
    try:
        job = validate_job(compile_recipe(operation, inputs), Path(input_dir))
        result = run_on_page(page, job, root) if page is not None else execute(job, root)
        return {'status': result['status'], 'route': route, 'result': result}
    except Exception as exc:
        # Raw errors may quote client text or credentials. Persist type only.
        handoff = {
            'status': 'NEEDS_BROWSER_RECOVERY', 'operation': operation,
            'location_id': inputs['location_id'], 'error_type': type(exc).__name__,
            'route': recovery(operation, inputs['location_id'], observed, inputs=inputs),
            'state_file': str(root / 'state.json'),
            'instruction': 'Inspect recorded objects and the failed step. Do not rerun a create/save until its persisted outcome is reconciled.',
        }
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
            if capture_error and selected['lane'] not in ('public_api','skill44','official_mcp'):
                print(json.dumps({'status':'STOP_INVALID_CAPTURE', 'route':selected,
                                  'error_type':capture_error, 'browser_used':False}))
                return 2
            status = 'ROUTE_VALIDATED_ONLY'
            if selected['lane'] == 'playwright':
                validate_job(compile_recipe(args.operation, inputs), args.inputs.resolve().parent)
                status = 'VALIDATED_ONLY'
            elif selected['lane'] in ('public_api','skill44','official_mcp') and args.operation in ('courses.create','courses.update','courses.lesson_quiz.create'):
                if __package__:
                    from .delivery import validate_api_inputs
                else:
                    from delivery import validate_api_inputs
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
            return 2 if selected['lane'].startswith('STOP_') or status == 'API_PROBE_REQUIRED' else 0
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
