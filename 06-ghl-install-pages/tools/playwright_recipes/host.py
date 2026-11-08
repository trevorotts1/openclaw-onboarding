#!/usr/bin/env python3
"""One deterministic entry point for OpenClaw/Claude-Nine Skill 6 hosts.

The host supplies actual tool capabilities. This adapter never invents shell
commands for extensions/MCP servers or converts UI success into funnel QC PASS.
"""
from copy import deepcopy
from pathlib import Path

if __package__:
    from .recipe_cli import compile_recipe
    from .route import decide, recovery
    from .skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job
else:
    from recipe_cli import compile_recipe
    from route import decide, recovery
    from skill6_playwright import Stop, execute, run_on_page, secure_json, validate_job


def run_recipe(operation, inputs, probes, evidence_root, *, input_dir, page=None):
    observed = deepcopy(probes)
    if inputs.get('options'):
        observed.setdefault('recorded_profiles', []).append(operation)
    route = decide(operation, inputs['location_id'], observed)
    root = Path(evidence_root)
    secure_json(root / 'route.json', route)
    if route['lane'] != 'playwright':
        return {'status': 'HANDOFF_REQUIRED', 'route': route, 'browser_used': False}
    try:
        job = validate_job(compile_recipe(operation, inputs), Path(input_dir))
        result = run_on_page(page, job, root) if page is not None else execute(job, root)
        return {'status': result['status'], 'route': route, 'result': result}
    except Exception as exc:
        # Raw errors may quote client text or credentials. Persist type only.
        handoff = {
            'status': 'NEEDS_BROWSER_RECOVERY', 'operation': operation,
            'location_id': inputs['location_id'], 'error_type': type(exc).__name__,
            'route': recovery(operation, inputs['location_id'], observed),
            'state_file': str(root / 'state.json'),
            'instruction': 'Inspect recorded objects and the failed step. Do not rerun a create/save until its persisted outcome is reconciled.',
        }
        secure_json(root / 'handoff.json', handoff)
        return handoff
