"""Staged native purchase-flow dispatcher and independent journey verifier.

The Skill 49 graph is the sole route authority. Jobs use the normal recipe
compiler/executor and are saved individually; this module never publishes or
initiates a payment. A runner interrupted during a stage requires reconciliation.
"""
import json
import os
import re
import fcntl
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

_TOOLS = str(Path(__file__).resolve().parents[1])
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
from ghl_order_elements import approved_routes, graph_hash, OrderPlanError
from playwright_recipes.skill6_playwright import Stop
from playwright_recipes.native_payment_policy import apply_payment_policy

# The caller supplies captured native identities and fully specified jobs. No IDs
# are generated and no synthetic page navigation stands in for purchase controls.
KINDS = {
    'folder': {'funnels.create_folder', 'websites.create_folder'},
    'design': {'pages.install_code', 'pages.install_embed', 'pages.layout', 'pages.responsive', 'pages.saved_section', 'pages.seo'},
    'page': {'funnels.create', 'funnels.add_page', 'websites.create', 'websites.add_page'},
    'wrap': {'checkout.wrap_native'},
    'checkout': {'checkout.configure_native', 'checkout.configure_ui'},
    'purchase': {'checkout.one_click_upsell', 'checkout.configure_native'},
    'decline': {'checkout.one_click_upsell', 'checkout.configure_native'},
    'confirmation': {'forms.submission'},
}


def prepare_flow(graph, stages, page_bindings=None):
    try:
        routes = approved_routes(graph)
    except OrderPlanError as exc:
        raise Stop(str(exc)) from exc
    if not isinstance(stages, list) or not stages:
        raise Stop('Flow requires explicit native jobs')
    location = graph.get('location_id')
    if not location:
        raise Stop('Approved graph requires location_id')
    bindings = page_bindings or {}
    if not isinstance(bindings, dict) or set(bindings) - set(routes):
        raise Stop('Page bindings must be keyed by approved graph role')
    for role, b in bindings.items():
        if (not isinstance(b, dict) or set(b) != {'status','location_id','graph_page_id','native_page_id','native_step_id','source'}
                or b['status'] != 'PASS' or b['location_id'] != location
                or b['graph_page_id'] != routes[role]['page_id']
                or any(not isinstance(b[k], str) or not b[k].strip() for k in ('native_page_id','native_step_id','source'))):
            raise Stop('Page binding requires a location-bound independent native identity readback')
    seen = set()
    action_components = {}
    prepared = []
    from playwright_recipes.recipe_cli import compile_recipe
    for stage in stages:
        if not isinstance(stage, dict) or set(stage) != {'id', 'kind', 'role', 'operation', 'inputs', 'depends_on'}:
            raise Stop('Each flow stage needs exactly id, kind, role, operation, inputs and depends_on')
        ident, kind, role, op = (stage[k] for k in ('id', 'kind', 'role', 'operation'))
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in seen:
            raise Stop('Flow stage IDs must be distinct nonempty strings')
        if kind not in KINDS or op not in KINDS[kind] or role not in routes:
            raise Stop('Flow stage kind, native recipe or approved role is invalid')
        deps = stage['depends_on']
        if not isinstance(deps, list) or len(set(deps)) != len(deps) or any(d not in seen for d in deps):
            raise Stop('Flow dependencies must refer to preceding distinct stages')
        data = stage['inputs']
        if not isinstance(data, dict) or data.get('location_id') != location:
            raise Stop('Every stage must bind the approved graph location')
        if kind in ('checkout', 'purchase', 'decline') and (role not in bindings or data.get('page_id') != bindings[role]['native_page_id']):
            raise Stop('Native checkout and purchase jobs must bind the approved role page')
        if kind in ('checkout', 'purchase', 'decline') and op != 'checkout.configure_ui' and data.get('step_id') != bindings[role]['native_step_id']:
            raise Stop('Checkout step must match the independently read-back native step for its role')
        if kind in ('checkout', 'purchase', 'decline') and bindings[role]['native_page_id'] not in urlsplit(data.get('start_url', '')).path.split('/'):
            raise Stop('Editor URL must bind the approved role page')
        if kind in ('purchase', 'decline') and role not in ('upsell_1', 'downsell_1', 'upsell_2'):
            raise Stop('Purchase controls require an approved extra-offer role')
        if kind in ('purchase', 'decline'):
            action = data.get('purchase_action')
            edge = routes[role]['accept' if kind == 'purchase' else 'decline']
            if (not isinstance(action, dict) or action.get('kind') != ('accept' if kind == 'purchase' else 'decline')
                    or not edge or edge['target_role'] not in bindings
                    or action.get('target_step_id') != bindings[edge['target_role']]['native_step_id']):
                raise Stop('Native purchase/decline target must match the approved graph edge')
        if kind in ('purchase', 'decline'):
            component = data.get('component_id')
            other = action_components.get((role, 'decline' if kind == 'purchase' else 'purchase'))
            if other and component == other:
                raise Stop('Accept and decline cannot overwrite the same native component action')
            if (role, kind) in action_components:
                raise Stop('Duplicate native action for the same graph role')
            action_components[(role, kind)] = component
        if kind == 'confirmation' and role != 'thank_you':
            raise Stop('Confirmation must bind the approved thank-you role')
        if kind == 'confirmation' and data.get('submission', {}).get('mode') != 'Order Confirmation':
            raise Stop('Confirmation requires the native Order Confirmation operation')
        if kind == 'folder':
            from playwright_recipes.page_folders import _plan, _name
            if data.get('allow_creation') is not True:
                raise Stop('Folder creation requires explicit authorization')
            if set(data) - {'location_id','location_name','start_url','folder_name','object_name','allow_creation'}:
                raise Stop('Unsupported folder inputs')
            _plan(location, 'funnel' if op.startswith('funnels.') else 'website', data.get('folder_name'), data.get('start_url'))
            if not data.get('location_name'): raise Stop('Folder location name is required')
            if 'object_name' in data: _name(data['object_name'])
            job = None  # Host executes the dedicated journaled folder leaf.
        else:
            job = compile_recipe(op, data)
        prepared.append({**stage, 'job': job, 'route': routes[role],
                         'policy': apply_payment_policy(op, {})['native_payment_policy']})
        seen.add(ident)
    return {'graph_hash': graph_hash(graph), 'location_id': location, 'page_bindings': bindings, 'stages': prepared}


def _save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise Stop('Flow journal is a symlink; reconciliation required')
    fd, tmp = tempfile.mkstemp(prefix='.flow-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def _dispatch_flow_unlocked(flow, journal_path, run_job):
    """Run validated jobs in order. Persist started/completed before/after calls.

    ``run_job(stage)`` must run the standard executor and return its receipt.
    Failed or interrupted jobs are never silently retried: reconcile externally.
    """
    path = Path(journal_path)
    from playwright_recipes.evidence_lease import journal_present, read_journal
    if journal_present(path):
        state = read_journal(path)
        if state.get('graph_hash') != flow['graph_hash'] or state.get('location_id') != flow['location_id'] or state.get('page_bindings', {}) != flow.get('page_bindings', {}):
            raise Stop('Journal belongs to a different graph or location')
    else:
        state = {'graph_hash': flow['graph_hash'], 'location_id': flow['location_id'], 'page_bindings': flow.get('page_bindings', {}), 'stages': {}}
    for stage in flow['stages']:
        ident = stage['id']
        existing = state['stages'].get(ident)
        if existing:
            if existing.get('stage') != stage:
                raise Stop('Journal stage differs from current job; reconciliation required')
            if existing['status'] == 'complete':
                continue
            raise Stop('Prior stage was interrupted or failed; reconcile before resuming')
        if any(state['stages'].get(d, {}).get('status') != 'complete' for d in stage['depends_on']):
            raise Stop('Stage dependencies are not complete')
        state['stages'][ident] = {'status': 'started', 'stage': stage}
        _save(path, state)
        try:
            receipt = run_job(stage)
            inner = receipt.get('result', receipt) if isinstance(receipt, dict) else {}
            pending = (receipt.get('status') == 'NEEDS_VERIFICATION' and isinstance(inner, dict)
                       and inner.get('status') == 'NEEDS_VERIFICATION'
                       and inner.get('current_step_status') == 'FINISHED'
                       and isinstance(inner.get('results'), list) and bool(inner['results']))
            if not isinstance(receipt, dict) or (receipt.get('status') != 'EDITOR_STEPS_COMPLETE' and not pending):
                raise Stop('Native recipe did not complete; inspect and reconcile its receipt')
            state['stages'][ident].update(status='complete', receipt=receipt)
            _save(path, state)
        except Exception:
            state['stages'][ident]['status'] = 'reconciliation_required'
            _save(path, state)
            raise
    return state


def verify_journey(graph, evidence):
    """Check an independently observed sandbox journey, never perform a charge.

    Evidence must be supplied by the payment-provider and published-page test
    observer, including its source references. This is a consistency check, not
    authentication of those sources or a substitute for independently checking them.
    """
    routes = approved_routes(graph)
    errors = []
    if not isinstance(evidence, dict):
        return {'ok': False, 'errors': ['Evidence must be an object']}
    if (evidence.get('environment') != 'sandbox' or evidence.get('provider_test_mode_verified') is not True
            or not evidence.get('provider_evidence_ref') or not evidence.get('published_journey_evidence_ref')
            or evidence.get('location_id') != graph.get('location_id')):
        errors.append('Independent provider test-mode and published journey references bound to the location are required')
    replay = evidence.get('duplicate_prevention')
    if (not isinstance(replay, dict) or replay.get('repeat_attempt_observed') is not True
            or replay.get('provider_verified') is not True or not replay.get('evidence_ref')
            or not isinstance(replay.get('successful_charge_ids'), list)
            or len(replay['successful_charge_ids']) != 1 or not replay['successful_charge_ids'][0]):
        errors.append('Provider-observed duplicate attempt with exactly one successful charge is required')
    bindings = evidence.get('page_bindings')
    if not isinstance(bindings, dict):
        return {'ok': False, 'errors': errors + ['Native page/step readback bindings are required']}
    for role, binding in bindings.items():
        if (role not in routes or not isinstance(binding, dict) or binding.get('status') != 'PASS'
                or binding.get('location_id') != graph.get('location_id')
                or binding.get('graph_page_id') != routes[role]['page_id']
                or not binding.get('native_page_id') or not binding.get('native_step_id') or not binding.get('source')):
            return {'ok': False, 'errors': errors + ['Invalid native page/step readback binding']}
    def native_page(role):
        return bindings.get(role, {}).get('native_page_id')
    events = evidence.get('events')
    if not isinstance(events, list) or not events:
        return {'ok': False, 'errors': errors + ['Observed journey events are required']}
    current = 'checkout'
    session = evidence.get('native_session_id')
    charges = set()
    paid = False
    for event in events:
        if not isinstance(event, dict):
            errors.append('Malformed event'); break
        if not native_page(current) or not session or event.get('native_session_id') != session or event.get('role') != current:
            errors.append('Native session continuity or current page does not match'); break
        outcome = event.get('outcome')
        if outcome in ('payment_failed', 'payment_pending'):
            if event.get('next_page_id') != native_page(current) or event.get('charge_id'):
                errors.append('Failed or pending payment must stay on the current page without a successful charge')
            continue
        if outcome == 'payment_succeeded':
            charge = event.get('charge_id')
            if not charge or charge in charges or event.get('provider_verified') is not True:
                errors.append('Successful payments require distinct provider-verified charge IDs'); break
            charges.add(charge); paid = True
            edge = routes[current]['accept']
        elif outcome == 'explicit_decline':
            if current == 'checkout' or event.get('charge_id') or event.get('explicit') is not True:
                errors.append('Declines must be explicit and uncharged'); break
            edge = routes[current]['decline']
        else:
            errors.append('Unknown payment outcome'); break
        if not edge or not native_page(edge['target_role']) or event.get('next_page_id') != native_page(edge['target_role']):
            errors.append('Observed destination differs from approved graph'); break
        current = edge['target_role']
    if isinstance(replay, dict) and replay.get('successful_charge_ids') and replay['successful_charge_ids'][0] not in charges:
        errors.append('Duplicate-prevention charge must belong to this journey')
    if not paid or current != 'thank_you' or not native_page('thank_you') or evidence.get('confirmation_page_id') != native_page('thank_you') or evidence.get('confirmation_observed') is not True:
        errors.append('Paid journey must finish on the approved observed confirmation page')
    return {'ok': not errors, 'errors': errors, 'qualification': 'Evidence consistency only; source authenticity requires independent verification'}


@contextmanager
def flow_lock(root):
    """Serialize independent multi-stage orchestration in one evidence root."""
    from playwright_recipes.evidence_lease import open_lease
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = open_lease(root / '.orchestrator.lock')
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('Another orchestration is using this evidence root') from None
        yield
    finally:
        os.close(fd)


def dispatch_flow(flow, journal_path, run_job):
    path = Path(journal_path)
    with flow_lock(path.parent):
        return _dispatch_flow_unlocked(flow, path, run_job)
