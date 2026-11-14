"""PD-927: the operator-contract replay path and the PD-913 completion gate.

PD-913 made `deck-intake-driver.py --complete` refuse while a required turn is
unanswered. The bridge replayed a contract's answers and then called
`--complete`, so both directions of this seam need proof:

  * a replay whose contract REALLY carries every required turn still completes;
  * a replay whose contract leaves a required turn unanswered is still refused,
    with the driver's own named reason.

The defect this fixes was NOT the gate. A one-question-per-message bank answers
ATOMIC subfield ids (question_sequence.atomic_questions), and the bridge's
answer whitelist accepted only top-level row ids -- so the very turns the gate
requires could never be replayed. Measured against the pre-PD-913 driver, the
old permissive `--complete` produced an intake that build_deck's own
`_intake_provenance_gate` then REJECTED for missing its six mandatory fields.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE = HERE.parent / 'bridge' / 'intake_bridge.py'
SCRIPTS = HERE.parent.parent.parent / 'scripts'
DRIVER = SCRIPTS / 'deck-intake-driver.py'

spec = importlib.util.spec_from_file_location('pd927_bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(bridge)


def _contract(answers):
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
        'want_ghl_upload': 'yes', 'want_sales_checkout': 'yes',
        'want_vsl_page': 'yes',
        'deliverable_set': 'PPTX, PDF, presenter guide, workbook, fillable workbook, infographic',
        'delivery_destinations': ['PPTX', 'PDF', 'presenter guide', 'workbook',
                                  'fillable workbook', 'infographic'],
        'answers': answers,
    }


# Every required turn the bank asks for this contract, as the ATOMIC ids the
# one-question-per-message bank actually puts in front of a caller. The six the
# downstream build gate names as mandatory are among them.
_FULL = {
    'audience': 'General informational audience learning how to use the department',
    'audience_composition_note': 'department leads and operators; no people in imagery',
    'representation_mix': 'operators and department leads, uniform mix',
    'transformation_promise': 'No commercial transformation promise',
    'cta_action': 'Request or use the Presentation Department',
    'tone': 'teacher',
    'grounded_content': 'the department itself and its SOPs; no named method',
    'goal': 'Show the department end to end',
    'target_feeling': 'Confident the department can be trusted',
    'primary_objection': 'Distrust of unsourced claims',
    'hook_seed': 'propose',
    'deadline': '2026-11-20',
    'visual_mix': 'clean technical diagrams, minimal text',
    'dark_ok': 'no',
    'logo_on_slides': 'no',
    'standard_mode': 'QUICK',
    'style_source': 'create-new',
    'style_prefs': 'navy and gold, clean technical diagrams',
    'brand_primary': 'navy #0b1f3a',
    'style_pick_auto': 'no',
    'client_notes': 'informational demo, no commercial claims',
    'email_sequences_declined_reason': 'Not requested for an informational demo',
    'motion_graphics_declined_reason': 'Not requested for an informational demo',
}


def test_atomic_subfield_answers_are_accepted_not_rejected_as_unknown():
    """The whitelist must mirror the driver's own answerable set.

    Before PD-927 every atomic id below raised
    `ValueError: operator contract has unsupported answer keys`, which is why
    the required turns could never reach the gate.
    """
    parsed = bridge._operator_driver_answers(_contract(_FULL), DRIVER)
    for qid in ('audience_composition_note', 'representation_mix',
                'grounded_content', 'visual_mix', 'dark_ok', 'hook_seed'):
        assert qid in parsed, f'{qid} was not accepted'


def test_unknown_answer_key_is_still_rejected():
    """Widening the whitelist must not turn it into a pass-through."""
    payload = _contract({'unsupported_user_field': 'must never reach the driver'})
    with pytest.raises(ValueError, match='unsupported answer keys'):
        bridge._operator_driver_answers(payload, DRIVER)


def test_replay_whose_contract_carries_every_turn_completes(tmp_path, monkeypatch):
    """PROOF A: the replay path works when the turns were answered upstream."""
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    rd = tmp_path / 'pd927-full'
    result = bridge.drive_operator_contract(_contract(_FULL), rd, driver_path=DRIVER,
                                            launch=False)
    assert result['driver_complete'] is True
    ledger = json.loads((rd / 'working/interview/intake_ledger.json').read_text())
    assert ledger['status'] == 'complete'
    entries = ledger['entries']
    for qid in ('representation_mix', 'audience_composition_note',
                'grounded_content', 'visual_mix', 'dark_ok', 'hook_seed'):
        assert entries[qid]['value'] != '', f'{qid} recorded empty'


def test_replay_with_an_unanswered_required_turn_is_still_refused(tmp_path, monkeypatch):
    """PROOF B: a genuinely unanswered required turn still refuses, by name.

    The refusal must be the driver's own reason, not an empty stderr tail --
    the driver prints it as JSON on STDOUT.
    """
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHAT_ID', 'operator-test-route')
    monkeypatch.setenv('PRESENTATION_REQUESTER_CHANNEL', 'operator-delegated')
    partial = {k: v for k, v in _FULL.items()
               if k not in ('audience_composition_note', 'visual_mix')}
    rd = tmp_path / 'pd927-partial'
    with pytest.raises(RuntimeError) as exc:
        bridge.drive_operator_contract(_contract(partial), rd, driver_path=DRIVER,
                                       launch=False)
    message = str(exc.value)
    assert 'driver completion refused' in message
    assert 'the interview is not finished' in message, message
    assert 'missing' in message, message
    ledger = json.loads((rd / 'working/interview/intake_ledger.json').read_text())
    assert ledger.get('status') != 'complete'
