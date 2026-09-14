import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE = HERE.parent / 'bridge' / 'intake_bridge.py'
SCRIPTS = HERE.parent.parent.parent / 'scripts'
DRIVER = SCRIPTS / 'deck-intake-driver.py'
RESOLVER = SCRIPTS / 'presentation_job' / 'resolve_intake.py'

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
        'want_sales_checkout': 'yes', 'want_vsl_page': 'yes',
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
