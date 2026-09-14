import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE = HERE.parent / 'bridge' / 'intake_bridge.py'
SCRIPTS = HERE.parent.parent.parent / 'scripts'
DRIVER = SCRIPTS / 'deck-intake-driver.py'
RESOLVER = SCRIPTS / 'presentation_job' / 'resolve_intake.py'
sys.path.insert(0, str(SCRIPTS))
from presentation_job import model_router, resource_profile, launcher  # noqa: E402
CC_ROOT = pathlib.Path('/private/tmp/pd025-cc-current')
CC_TSX = CC_ROOT / 'node_modules/.bin/tsx'

spec = importlib.util.spec_from_file_location('operator_contract_bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(bridge)


def contract():
    # Values are explicit non-commercial facts from the authenticated
    # informational-demo contract, never invented commercial claims.
    return {
        'version': 1, 'source': 'operator-delegated',
        'task_id': 'd4e05a2f-f83b-4e87-aabe-d5e31c43867b',
        'execution_id': 'b4cc51f0-0abf-420a-bed2-9cfbb8650e83',
        'title': 'How the Presentation Department Works',
        'presentation_type': 'from_scratch', 'run_mode': 'ultra',
        'workhorse_model': 'deepseek-flash@deepseek-direct',
        'slide_count': 8, 'pitch_included': False,
        'want_teleprompter': 'yes', 'want_speech_script': 'yes',
        'want_audio_deliverable': 'yes', 'want_audio_demo': True,
        'want_ghl_upload': 'yes', 'want_sales_checkout': 'yes', 'want_vsl_page': 'yes',
        'deliverable_set': 'PPTX, PDF, presenter guide, workbook, fillable workbook, infographic',
        'delivery_destinations': ['PPTX', 'PDF', 'presenter guide', 'workbook', 'fillable workbook', 'infographic'],
        'answers': {
            'audience': 'General informational audience learning how to use the Presentation Department',
            'transformation_promise': 'No commercial transformation promise — informational department demonstration',
            'cta_action': 'Request or use the Presentation Department',
            'tone': 'teacher',
        },
    }


def live_contract():
    """Sanitized field-for-field shape of the accepted 1d269693 contract.

    IDs are test-local; all answer/option types match the server-stored signed
    contract so the bridge cannot pass because of a hand-written reduced shape.
    """
    value = contract()
    value["answers"] = {
        "audience": "general informational audience learning how to request and use the Presentation Department",
        "brief": "How the Presentation Department Works",
        "deck_type_source": "presentation_type: from_scratch; pitch_included: false",
        "mode": "general",
    }
    return value


def _profile_with_direct_flash() -> dict:
    return {
        "providers": {"deepseek-direct": {
            "provider": "deepseek-direct", "presence": True,
            "detected": True, "wired_models": ["deepseek-flash"],
        }},
        "model_plan": {"workhorse": {
            "provider": "deepseek-direct", "model": "deepseek-flash",
        }, "reasoning": None, "judge": None, "thinking": None,
            "floor_waivers": [], "source": "interview"},
    }


def cc_signed_receipt(payload, tmp_path, secret='contract-test-secret'):
    """Use CC's real canonical HMAC implementation, never a Python reimplementation."""
    assert CC_TSX.is_file(), 'PD025 fresh CC checkout/runtime missing'
    raw = dict(payload)
    raw.pop('task_id'); raw.pop('execution_id')
    source = tmp_path / 'cc-input.json'; source.write_text(json.dumps(raw))
    code = """import { readFileSync } from 'fs'; import { parseOperatorPresentationContract, bindOperatorPresentationContract, bridgeReceipt } from './src/lib/presentation-operator-contract'; const intake=parseOperatorPresentationContract(JSON.parse(readFileSync(process.env.PD025_INPUT,'utf8'))); const contract=bindOperatorPresentationContract('d4e05a2f-f83b-4e87-aabe-d5e31c43867b',intake); process.stdout.write(JSON.stringify(bridgeReceipt(contract)));"""
    env = dict(os.environ, WEBHOOK_SECRET=secret, PD025_INPUT=str(source))
    proc = subprocess.run([str(CC_TSX), '-e', code], cwd=CC_ROOT, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_contract_runs_real_driver_then_resolver_without_provider(tmp_path, monkeypatch):
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    rd = tmp_path / 'operator-contract-run'
    result = bridge.drive_operator_contract(contract(), rd, driver_path=DRIVER, launch=False)
    assert result['driver_complete'] is True
    receipt = json.loads((rd / 'working/interview/operator_contract.json').read_text())
    assert receipt['source'] == 'operator-delegated'
    assert receipt['task_id'] == contract()['task_id']
    intake = json.loads((rd / 'working/copy/intake.json').read_text())
    assert intake['presentation_type'] == 'from_scratch'
    assert intake['deck_type'] == 'webinar'
    assert intake['pitch_included'] is False
    assert intake['requester_chat_id'] == 'operator-test-route'
    ledger = rd / 'working/interview/intake_ledger.json'
    engine_intake = rd / 'working/checkpoints/engine-intake.json'
    p = subprocess.run([sys.executable, str(RESOLVER), '--ledger', str(ledger), '--out', str(engine_intake), '--source', 'operator-contract-test'], text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    resolved = json.loads(engine_intake.read_text())
    assert resolved['presentation_type'] == 'from_scratch'
    assert resolved['deck_type'] == 'from_scratch'
    assert resolved['requester']['chat_id'] == 'operator-test-route'
    assert resolved['pre_presentation_capture']['WANT_SALES_CHECKOUT'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_VSL_PAGE'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_TELEPROMPTER'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_SPEECH_SCRIPT'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_AUDIO_DELIVERABLE'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_GHL_UPLOAD'] == 'yes'
    assert 'PPTX' in resolved['pre_presentation_capture']['DELIVERY_DESTINATIONS']
    assert 'fillable workbook' in resolved['pre_presentation_capture']['DELIVERABLE_SET']
    entries = json.loads(ledger.read_text())['entries']
    assert entries['RUN_MODE']['value'] == 'ultra'
    assert entries['WORKHORSE_MODEL']['value'] == 'deepseek-flash@deepseek-direct'


def test_live_contract_shape_projects_ultra_and_direct_flash_to_real_consumers(tmp_path, monkeypatch):
    """PD-TEST-035: use the accepted contract shape all the way through the
    real driver and resolver, then make the real router select the workhorse.
    Provider transport is deliberately absent; this test proves only the
    no-spend selection/handoff seam."""
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    profile_dir = tmp_path / 'profile'
    monkeypatch.setenv('PRESENTATION_RESOURCE_PROFILE_DIR', str(profile_dir))
    profile = resource_profile.new_profile()
    profile['providers']['deepseek-direct'] = {
        'provider': 'deepseek-direct', 'presence': True, 'detected': True,
        'wired_models': ['deepseek-flash'], 'consented': True,
    }
    resource_profile.save_profile(profile, profile_dir)
    rd = tmp_path / 'live-contract-shape'
    monkeypatch.setattr(model_router, 'provider_key_resolves', lambda provider: provider == 'deepseek-direct')
    result = bridge.drive_operator_contract(live_contract(), rd, driver_path=DRIVER, launch=False)
    assert result['driver_complete'] is True
    assert result['model_selection'] == {'provider': 'deepseek-direct', 'model': 'deepseek-flash', 'run_mode': 'ultra'}
    ledger = rd / 'working/interview/intake_ledger.json'
    engine_intake = rd / 'working/checkpoints/engine-intake.json'
    proc = subprocess.run([sys.executable, str(RESOLVER), '--ledger', str(ledger),
                           '--out', str(engine_intake), '--source', 'pd035-test'],
                          text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    resolved = json.loads(engine_intake.read_text())
    assert resolved['run_mode'] == 'ultra'
    assert resolved['workhorse_model'] == 'deepseek-flash@deepseek-direct'
    assert not resolved['workhorse_model'].endswith(';')
    assert resolved['pre_presentation_capture']['WANT_VSL_PAGE'] == 'yes'
    assert resolved['pre_presentation_capture']['WANT_SALES_CHECKOUT'] == 'yes'
    # Read the exact profile the real driver just produced. Credentials are
    # isolated at the provider boundary; model-plan persistence is not stubbed.
    profile = resource_profile.load_profile()
    decision = model_router.resolve_route('P4-COPY', profile=profile, mode=resolved['run_mode'])
    assert decision['route'] == {'provider': 'deepseek-direct', 'model': 'deepseek-flash'}
    assert decision['client_plan']['applied'] is True
    assert decision['mode_ceiling']['mode'] == 'ultra'
    assert decision['mode_ceiling']['operator_ceiling'] == 100


def test_launcher_writes_ultra_mode_and_client_route_sidecars(tmp_path, monkeypatch):
    """Exercise launcher preflight with the real supported profile projection.
    The engine executable is a no-provider recorder; no model transport runs."""
    profile_dir = tmp_path / 'profile'
    monkeypatch.setenv('PRESENTATION_RESOURCE_PROFILE_DIR', str(profile_dir))
    profile = resource_profile.new_profile()
    profile['providers']['deepseek-direct'] = {
        'provider': 'deepseek-direct', 'presence': True, 'detected': True,
        'wired_models': ['deepseek-flash', 'deepseek-v4-pro'], 'consented': True,
    }
    profile['model_plan'] = _profile_with_direct_flash()['model_plan']
    resource_profile.save_profile(profile, profile_dir)
    monkeypatch.setattr(model_router, 'provider_key_resolves', lambda provider: provider == 'deepseek-direct')
    monkeypatch.setattr(launcher, 'notify_gate', lambda run: True)
    monkeypatch.setattr(launcher, 'ocr_launch_gate', lambda run: True)
    monkeypatch.setattr(launcher, 'capacity_gate', lambda: (100, {'status': 'MEASURED', 'provider': 'deepseek-direct', 'plan': 'test', 'detection_source': 'test'}))
    monkeypatch.setenv('PRESENTATION_CREDIT_PREFLIGHT', '0')
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    (scripts / 'presentation_job.py').write_text(
        "import json,os,sys\nrd=sys.argv[sys.argv.index('--run-dir')+1]\njson.dump({'mode':os.environ.get('PRESENTATION_MODE')},open(os.path.join(rd,'engine-env.json'),'w'))\n",
        encoding='utf-8')
    monkeypatch.setattr(launcher, 'resolve_scripts_dir', lambda: scripts)
    run = tmp_path / 'run'; (run / 'working/copy').mkdir(parents=True)
    (run / 'working/copy/intake.json').write_text(json.dumps({'presentation_type': 'from_scratch'}))
    rc = launcher.dispatch_new(str(run), client='operator', deck_type='from_scratch', background=False, mode='ultra')
    assert rc == 0
    mode_plan = json.loads((run / '.mode-plan.json').read_text())
    model_plan = json.loads((run / '.model-plan.json').read_text())
    assert mode_plan['mode'] == 'ultra' and mode_plan['declared'] is True
    assert mode_plan['ceiling']['operator_ceiling'] == 100
    assert json.loads((run / 'engine-env.json').read_text())['mode'] == 'ultra'
    authoring = next(row for row in model_plan['decisions'] if row['capability'] == 'authoring')
    assert authoring['provider'] == 'deepseek-direct' and authoring['model'] == 'deepseek-flash'


def test_rejects_client_shaped_or_incomplete_contract(tmp_path):
    bad = contract(); bad['source'] = 'telegram'
    try:
        bridge.drive_operator_contract(bad, tmp_path / 'bad', driver_path=DRIVER, launch=False)
    except ValueError as exc:
        assert 'operator-delegated' in str(exc)
    else:
        raise AssertionError('client-shaped contract was accepted')


def test_contract_delegates_to_bridge_launcher_with_transport_stub(tmp_path, monkeypatch):
    # The provider boundary is stubbed here; the adapter must never substitute
    # direct engine/artifact writes for the bridge's lease/launcher call.
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    seen = {}
    def fake_drive(run_dir, intake, session_id, policy, verbose):
        seen.update(run_dir=pathlib.Path(run_dir), intake=intake, session_id=session_id,
                    policy=policy, verbose=verbose)
        return {'status': 'transport-stubbed'}
    monkeypatch.setattr(bridge, '_drive_submission', fake_drive)
    result = bridge.drive_operator_contract(contract(), tmp_path / 'launch', driver_path=DRIVER, launch=True)
    assert result['bridge'] == {'status': 'transport-stubbed'}
    assert seen['session_id'] == 'operator-' + contract()['task_id']
    assert seen['intake']['pitch_included'] is False
    assert seen['intake']['pre_presentation_capture']['WANT_VSL_PAGE'] == 'yes'
    assert seen['intake']['pre_presentation_capture']['WANT_SALES_CHECKOUT'] == 'yes'


def test_signed_receipt_binds_existing_cc_task_and_replays_once(tmp_path, monkeypatch):
    """The real durable core binds the server task and lease; only launcher is stubbed."""
    import hashlib, hmac, os, types
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    secret = 'contract-test-secret'
    envelope = cc_signed_receipt(contract(), tmp_path, secret)
    payload = envelope['contract']
    assert bridge.verify_operator_contract_receipt(envelope, secret=secret) == payload
    with pytest.raises(ValueError):
        bridge.verify_operator_contract_receipt({**envelope, 'receipt_hmac': '0' * 64}, secret=secret)
    rd = tmp_path / 'core-run'
    bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False)
    intake = json.loads((rd / 'working/copy/intake.json').read_text())
    intake.update(cc_task_id=payload['task_id'], cc_execution_id=payload['execution_id'])
    import presentation_job.lease as real_lease
    calls = []
    class Launcher:
        def dispatch_new(self, run_dir, **kwargs):
            calls.append(kwargs)
            # Transport stub's acknowledgement witness: it is not an engine stage.
            pathlib.Path(run_dir, 'state.json').write_text(json.dumps({'engine_pid': os.getpid(), 'job_id': payload['execution_id']}))
            return os.getpid()
    fake_pj = types.SimpleNamespace(lease=real_lease, launcher=Launcher())
    monkeypatch.setattr(bridge, '_load_presentation_job', lambda: fake_pj)
    monkeypatch.setattr(bridge, '_load_cc_board', lambda: (_ for _ in ()).throw(AssertionError('must reuse authenticated CC task')))
    policy = {'backoff_base_s': 0, 'backoff_cap_s': 0, 'max_attempts': 3, 'notify_thresholds': (), 'claim_ttl_s': 60}
    first = bridge._drive_submission(rd, intake, 'operator-' + payload['task_id'], policy, False)
    assert first['_rc'] == 0, first
    ledger = bridge._ll.load(rd, 'operator-' + payload['task_id'])
    assert ledger['board_task_id'] == payload['task_id']
    assert ledger['execution_id'] == payload['execution_id']
    second = bridge._drive_submission(rd, intake, 'operator-' + payload['task_id'], policy, False)
    assert second['_rc'] == 0
    assert len(calls) == 1


def test_cli_propagates_deferred_bridge_status(tmp_path, monkeypatch, capsys):
    import argparse, hashlib, hmac
    secret = 'contract-test-secret'
    monkeypatch.setenv('WEBHOOK_SECRET', secret)
    payload = contract()
    envelope = {'receipt_version': 1, 'contract': payload,
                'receipt_hmac': hmac.new(secret.encode(), bridge._canonical_contract_bytes(payload), hashlib.sha256).hexdigest()}
    receipt = tmp_path / 'receipt.json'; receipt.write_text(json.dumps(envelope))
    monkeypatch.setattr(bridge, 'drive_operator_contract', lambda *a, **k: {
        'run_dir': '/tmp/contract-run', 'receipt': '/tmp/receipt',
        'bridge': {'_rc': 7, 'verdict': 'launching', 'state': 'launching'}})
    rc = bridge.cmd_operator_contract(argparse.Namespace(contract_file=str(receipt), run_dir=str(tmp_path / 'run'), no_launch=False))
    emitted = json.loads(capsys.readouterr().out)
    assert rc == 7
    assert emitted['status'] == 'deferred'
    assert emitted['task_id'] == payload['task_id']


def test_same_signed_contract_resumes_retry_then_acknowledges_once(tmp_path, monkeypatch):
    import os, types
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    monkeypatch.setenv('PRES008_BACKOFF_BASE_S', '0')
    monkeypatch.setenv('PRES008_BACKOFF_CAP_S', '0')
    envelope = cc_signed_receipt(contract(), tmp_path)
    payload = envelope['contract']; rd = tmp_path / 'resume-run'
    bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False, receipt_hmac=envelope['receipt_hmac'])
    import presentation_job.lease as real_lease
    calls = []
    class Launcher:
        def dispatch_new(self, run_dir, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return -4  # retryable transport refusal; no engine state written
            pathlib.Path(run_dir, 'state.json').write_text(json.dumps({'engine_pid': os.getpid(), 'job_id': payload['execution_id']}))
            return os.getpid()
    monkeypatch.setattr(bridge, '_load_presentation_job', lambda: types.SimpleNamespace(lease=real_lease, launcher=Launcher()))
    first = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac=envelope['receipt_hmac'])
    assert first['bridge']['_rc'] == 7
    second = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac=envelope['receipt_hmac'])
    assert second['bridge']['_rc'] == 0
    third = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac=envelope['receipt_hmac'])
    assert third['bridge']['_rc'] == 0
    assert len(calls) == 2


def test_changed_contract_cannot_resume_authenticated_run(tmp_path, monkeypatch):
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    rd = tmp_path / 'immutable-run'
    bridge.drive_operator_contract(contract(), rd, driver_path=DRIVER, launch=False, receipt_hmac='stable-receipt')
    changed = contract(); changed['slide_count'] = 9
    with pytest.raises(ValueError, match='conflicts'):
        bridge.drive_operator_contract(changed, rd, driver_path=DRIVER, launch=False, receipt_hmac='stable-receipt')


def test_optional_boolean_and_yes_no_types_allow_unselected_extras_without_coercion():
    candidate = contract()
    candidate['want_audio_demo'] = False
    candidate['want_ghl_upload'] = 'no'
    assert bridge.validate_operator_contract(candidate)['want_audio_demo'] is False

def test_general_mode_contract_recovers_receipt_only_run(tmp_path):
    payload = contract()
    payload['answers']['mode'] = 'general'
    rd = tmp_path / 'receipt-only'
    (rd / 'working' / 'interview').mkdir(parents=True)
    receipt = {
        'version': 1, 'source': 'operator-delegated', 'receipt_hmac': 'stable',
        'contract_sha256': hashlib.sha256(bridge._canonical_contract_bytes(payload)).hexdigest(),
        'task_id': payload['task_id'], 'execution_id': payload['execution_id'], 'title': payload['title'],
    }
    (rd / 'working' / 'interview' / 'operator_contract.json').write_text(json.dumps(receipt))
    result = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False, receipt_hmac='stable')
    intake = json.loads((rd / 'working' / 'copy' / 'intake.json').read_text())
    assert result['driver_complete'] is True
    assert intake['run_mode'] == 'ultra'


def live_authorized_contract_shape():
    """Sanitized shape of task 1d269693's server-stored contract.

    IDs are fixture values and no HMAC/secret is retained; every selected
    option and answer key/type from the accepted request is represented.
    """
    payload = contract()
    payload['answers'] = {
        'deck_type_source': 'presentation_type: from_scratch; pitch_included: false',
        'audience': 'General informational audience learning how to request and use the Presentation Department',
        'mode': 'general',
        'brief': 'How the Presentation Department Works — an informational department demonstration.',
    }
    return payload


def test_live_contract_shape_maps_brief_to_canonical_client_notes_and_seals_all_options(tmp_path, monkeypatch):
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    payload = live_authorized_contract_shape()
    mapped = bridge._operator_driver_answers(payload, DRIVER)
    assert 'brief' not in mapped
    assert 'mode' not in mapped
    assert mapped['client_notes'] == payload['answers']['brief']
    result = bridge.drive_operator_contract(payload, tmp_path / 'live-shape', driver_path=DRIVER, launch=False)
    assert result['driver_complete'] is True
    rd = tmp_path / 'live-shape'
    ledger = json.loads((rd / 'working/interview/intake_ledger.json').read_text())
    assert ledger['status'] == 'complete'
    assert ledger['entries']['client_notes']['value'] == payload['answers']['brief']
    intake = json.loads((rd / 'working/copy/intake.json').read_text())
    assert intake['deck_type'] == 'webinar'
    assert intake['run_mode'] == 'ultra'
    assert intake['pitch_included'] is False
    engine = rd / 'working/checkpoints/engine-intake.json'
    resolved = subprocess.run([sys.executable, str(RESOLVER), '--ledger', str(rd / 'working/interview/intake_ledger.json'), '--out', str(engine), '--source', 'operator-contract-live-shape'], text=True, capture_output=True)
    assert resolved.returncode == 0, resolved.stderr
    final = json.loads(engine.read_text())
    assert final['pre_presentation_capture']['WANT_SALES_CHECKOUT'] == 'yes'
    assert final['pre_presentation_capture']['WANT_VSL_PAGE'] == 'yes'
    assert final['pre_presentation_capture']['WANT_TELEPROMPTER'] == 'yes'
    assert final['pre_presentation_capture']['WANT_SPEECH_SCRIPT'] == 'yes'
    assert final['pre_presentation_capture']['WANT_AUDIO_DELIVERABLE'] == 'yes'
    assert final['pre_presentation_capture']['WANT_AUDIO_DEMO'] is True
    assert final['pre_presentation_capture']['WANT_GHL_UPLOAD'] == 'yes'
    assert all(item in final['pre_presentation_capture']['DELIVERY_DESTINATIONS'] for item in payload['delivery_destinations'])
    assert all(item in final['pre_presentation_capture']['DELIVERABLE_SET'] for item in payload['deliverable_set'].split(', '))


def test_unknown_answer_is_rejected_before_receipt_or_partial_intake(tmp_path):
    payload = live_authorized_contract_shape()
    payload['answers']['unsupported_user_field'] = 'must never reach driver'
    rd = tmp_path / 'unsupported'
    with pytest.raises(ValueError, match='unsupported answer keys'):
        bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False)
    assert not (rd / 'working/interview/operator_contract.json').exists()
    assert not (rd / 'working/interview/intake_ledger.json').exists()


def test_live_contract_shape_resumes_after_mid_intake_failure_without_duplicate_turns(tmp_path, monkeypatch):
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    payload = live_authorized_contract_shape()
    rd = tmp_path / 'partial-live-shape'
    real_run = subprocess.run
    failed = {'value': False}

    def fail_client_notes(argv, *args, **kwargs):
        if (not failed['value'] and '--answer' in argv and
                argv[argv.index('--answer') + 1] == 'client_notes'):
            failed['value'] = True
            return subprocess.CompletedProcess(argv, 1, '', 'forced mid-intake failure')
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(bridge.subprocess, 'run', fail_client_notes)
    with pytest.raises(RuntimeError, match='driver refused client_notes'):
        bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False)
    ledger = json.loads((rd / 'working/interview/intake_ledger.json').read_text())
    assert ledger['status'] == 'in_progress'
    assert 'client_notes' not in ledger['entries']

    monkeypatch.setattr(bridge.subprocess, 'run', real_run)
    result = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False)
    assert result['driver_complete'] is True
    transcript = json.loads((rd / 'working/interview/intake_transcript_raw.json').read_text())
    owner_qids = [turn['qid'] for turn in transcript if turn['role'] == 'owner']
    assert len(owner_qids) == len(set(owner_qids))
    completed = json.loads((rd / 'working/interview/intake_ledger.json').read_text())
    assert completed['status'] == 'complete'
    assert completed['entries']['client_notes']['value'] == payload['answers']['brief']

def test_same_contract_reopens_only_obsolete_webinar_block(tmp_path, monkeypatch):
    """Only the obsolete type rejection is reopened through the real core.

    The fake launcher is the sole external transport boundary. The lease,
    board binding, durable ledger and blocked-state behavior remain real.
    """
    import os, types
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    profile_dir = tmp_path / 'profile'; monkeypatch.setenv('PRESENTATION_RESOURCE_PROFILE_DIR', str(profile_dir))
    profile = resource_profile.new_profile(); profile['providers']['deepseek-direct'] = {'provider':'deepseek-direct','presence':True,'detected':True,'wired_models':['deepseek-flash'],'consented':True}; resource_profile.save_profile(profile, profile_dir)
    monkeypatch.setattr(model_router, 'provider_key_resolves', lambda p: p == 'deepseek-direct')
    rd = tmp_path / 'resume'; payload = live_contract()
    bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False)
    sid = 'operator-' + payload['task_id']; import launch_ledger as ll
    (rd / 'working/checkpoints').mkdir(parents=True, exist_ok=True)
    doc = {'version': 1, 'session_id': sid, 'state': ll.STAGED,
           'run_dir': str(rd), 'history': [], 'board_task_id': payload['task_id']}
    ll.mark_blocked(rd, sid, doc,
                    reason="engine dispatch permanently refused: AF-DECK-TYPE-UNKNOWN (rc=-5) (deck_type 'webinar')",
                    remediation='old type path')
    import presentation_job.lease as real_lease
    calls = []
    class Launcher:
        def dispatch_new(self, run_dir, **kwargs):
            calls.append(kwargs)
            pathlib.Path(run_dir, 'state.json').write_text(json.dumps({
                'engine_pid': os.getpid(), 'job_id': payload['execution_id']}))
            return os.getpid()
    monkeypatch.setattr(bridge, '_load_presentation_job', lambda: types.SimpleNamespace(lease=real_lease, launcher=Launcher()))
    monkeypatch.setattr(bridge, '_load_cc_board', lambda: (_ for _ in ()).throw(AssertionError('must reuse authenticated CC task')))
    out = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True)
    state = ll.load(rd, sid)
    assert out['bridge']['_rc'] == 0
    assert len(calls) == 1
    assert state['state'] == ll.WORKER_ACKNOWLEDGED
    assert state['recovery_history'][0]['prior_block']['reason'].endswith("deck_type 'webinar')")
    # A distinct permanent failure remains final: no generic unblock or second launch.
    other = tmp_path / 'distinct-block'
    bridge.drive_operator_contract(payload, other, driver_path=DRIVER, launch=False)
    other_sid = sid
    (other / 'working/checkpoints').mkdir(parents=True, exist_ok=True)
    other_doc = {'version': 1, 'session_id': other_sid, 'state': ll.STAGED,
                 'run_dir': str(other), 'history': [], 'board_task_id': payload['task_id']}
    ll.mark_blocked(other, other_sid, other_doc,
                    reason='AF-MODEL-PLAN-UNSATISFIED', remediation='real gate')
    again = bridge.drive_operator_contract(payload, other, driver_path=DRIVER, launch=True)
    assert again['bridge']['_rc'] == 8
    assert ll.load(other, other_sid)['state'] == ll.BLOCKED_ACTIONABLE
    assert len(calls) == 1
    # A composite operator note quoting the old code is not the exact legacy
    # refusal and must remain final as well.
    composite = tmp_path / 'composite-block'
    bridge.drive_operator_contract(payload, composite, driver_path=DRIVER, launch=False)
    (composite / 'working/checkpoints').mkdir(parents=True, exist_ok=True)
    composite_doc = {'version': 1, 'session_id': other_sid, 'state': ll.STAGED,
                     'run_dir': str(composite), 'history': [],
                     'board_task_id': payload['task_id']}
    ll.mark_blocked(composite, other_sid, composite_doc,
                    reason="AF-MODEL-PLAN-UNSATISFIED; prior note AF-DECK-TYPE-UNKNOWN (rc=-5) (deck_type 'webinar')",
                    remediation='real model gate')
    composite_out = bridge.drive_operator_contract(payload, composite, driver_path=DRIVER, launch=True)
    assert composite_out['bridge']['_rc'] == 8
    assert ll.load(composite, other_sid)['state'] == ll.BLOCKED_ACTIONABLE
    assert len(calls) == 1
