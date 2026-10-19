/**
 * W30 acceptance fix round 1, blocking defect 1: two validator rules the
 * card contract never told the model. Evidence reference arrays accept only
 * evidence manifest IDs (the brief's fact-1 / asm-1 / unk-1 / con-1 IDs are
 * rejected) and lenses_used is allowed only on td-jakes. Real DeepSeek Flash
 * cards failed on both, so two seats never produced a Round 1 card.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  cardContractInstruction,
  cardRepairInstruction,
  cardRequestSystem,
} from '../src/cli/card-contract.js';

test('advisor contract states the evidence-manifest-only rule and the td-jakes-only lenses rule', () => {
  const text = cardContractInstruction('advisor', []);
  assert.match(text, /option_scores\[\]\.evidence_ids/);
  assert.match(text, /case_evidence_ids/);
  assert.match(text, /fact-1/);
  assert.match(text, /NOT evidence IDs/);
  assert.match(text, /must be \[\]/);
  assert.match(text, /lenses_used: omit this field entirely unless seat_id is "td-jakes"/);
});

test('ratification and consult contracts carry the evidence rule and no lenses rule', () => {
  for (const purpose of ['ratification', 'consult'] as const) {
    const text = cardContractInstruction(purpose, null);
    assert.match(text, /evidence_ids/);
    assert.match(text, /NOT evidence IDs/);
    assert.doesNotMatch(text, /lenses_used/);
  }
});

test('the repair turn restates both rules', () => {
  const repair = cardRepairInstruction('advisor', [], ['option_scores.evidence_ids: evidence fact-1 is not in the frozen evidence manifest']);
  assert.match(repair, /NOT evidence IDs/);
  assert.match(repair, /lenses_used/);
  const system = cardRequestSystem('BASE', 'advisor', [], []);
  assert.match(system, /NOT evidence IDs/);
});
