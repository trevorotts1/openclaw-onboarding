import importlib.util
import json
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
        'want_audio_deliverable': 'yes', 'want_audio_demo': 'yes',
        'want_ghl_upload': 'yes', 'want_sales_checkout': 'yes', 'want_vsl_page': 'yes',
        'delivery_destinations': ['PPTX', 'PDF', 'presenter notes', 'workbooks', 'infographic'],
        'answers': {
            'audience': 'General informational audience learning how to use the Presentation Department',
            'named_methodology': 'No named method — informational department demonstration',
            'transformation_promise': 'No commercial transformation promise — informational department demonstration',
            'time_to_result': 'Not applicable — informational department demonstration',
            'cta_action': 'Request or use the Presentation Department',
            'tone': 'teacher',
            'offer_name': 'No offer — informational department demonstration',
            'final_price': 'No price — informational department demonstration',
        },
    }


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
    entries = json.loads(ledger.read_text())['entries']
    assert entries['RUN_MODE']['value'] == 'ultra'
    assert entries['WORKHORSE_MODEL']['value'] == 'deepseek-flash@deepseek-direct'


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
    payload = contract()
    envelope = {'receipt_version': 1, 'contract': payload,
                'receipt_hmac': hmac.new(secret.encode(), bridge._canonical_contract_bytes(payload), hashlib.sha256).hexdigest()}
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
    payload = contract(); rd = tmp_path / 'resume-run'
    bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=False, receipt_hmac='stable-receipt')
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
    first = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac='stable-receipt')
    assert first['bridge']['_rc'] == 7
    second = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac='stable-receipt')
    assert second['bridge']['_rc'] == 0
    third = bridge.drive_operator_contract(payload, rd, driver_path=DRIVER, launch=True, receipt_hmac='stable-receipt')
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
