/**
 * CTR-138 regression: the round-3 contract defects from the live sitting
 * sess-ad4ee659 (2026-10-30, T. D. Jakes and Brené Brown blocked).
 *
 * Not executed in the repair lane (Trevor owns the run). It pins the three
 * contract defects the authoritative record proves:
 *   1. The call's round was absent from the explicit contract, and from the
 *      prompt for challenged seats; seven round-3 initial attempts failed
 *      validation with "round: challenge cards are round 3, got 2" (five
 *      recovered on the one repair, two exhausted it).
 *   2. The three approved Jakes lens IDs were named only after a failure,
 *      and the schema typed lenses_used as free text.
 *   3. The closed-object rule was never stated, so an option_scores entry
 *      carried an extra "evidence_ids_note" key.
 *
 * The exact invalid examples from the sitting must remain REJECTED.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import {
  cardContractInstruction,
  cardOutputContract,
  cardRepairInstruction,
  cardRequestSystem,
} from '../src/cli/card-contract.js';
import { advisorCardAuthorSchema } from '../src/contracts/schemas.js';
import { validateCardSourceUse } from '../src/sources/packs.js';

const JAKES_LENSES = ['instinct', 'disruptive-thinking', 'dont-drop-the-mic'];

/** A minimal advisor author card that the strict schema accepts. */
function validAuthorCard(): Record<string, unknown> {
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: 'sess-ad4ee659-cea6-4cb2-acf4-a54f514d49e8',
    brief_revision: 1,
    seat_id: 'brene-brown',
    input_manifest_sha256: 'a'.repeat(64),
    pack_version: 'live-elder-knowledge/v1',
    card_kind: 'advisor',
    round: 3,
    stance: 'support',
    preferred_option_id: 'opt-a',
    option_scores: [
      {
        option_id: 'opt-a',
        score: 7,
        rationale: 'Evidence supports a bounded test.',
        evidence_ids: [],
      },
    ],
    framework_applications: [],
    decisive_arguments: ['The bounded test limits exposure.'],
    strongest_objection: 'The test costs focus.',
    conditions: [],
    critical_unknowns: [],
    change_my_mind: 'A cheaper test would change this.',
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
  };
}

test('the advisor contract states the call round, the three Jakes lens IDs, and the closed-object rule', () => {
  const text = cardContractInstruction('advisor', ['crux-1'], 3);
  assert.match(text, /"round" field must be the number 3/);
  for (const lens of JAKES_LENSES) {
    assert.ok(
      text.includes(lens),
      `contract must name the approved lens ${lens}`,
    );
  }
  assert.match(text, /lenses_used: omit this field entirely unless seat_id is "td-jakes"/);
  assert.match(text, /Each option_scores entry accepts exactly/);
  for (const key of ['option_id', 'score', 'rationale', 'evidence_ids']) {
    assert.ok(
      text.includes(key),
      `contract must name the option_scores key ${key}`,
    );
  }
  assert.match(text, /any extra key fails validation/);
});

test('the model-facing schema carries the exact approved lens enum', () => {
  const contract = cardOutputContract('advisor', [], 3) as {
    json_schema: {
      properties: { lenses_used: { items: { enum?: string[] } } };
    };
  };
  assert.deepEqual(
    contract.json_schema.properties.lenses_used.items.enum,
    JAKES_LENSES,
  );
});

test('the invented Jakes lenses from the sitting stay rejected', () => {
  const diagnostics = validateCardSourceUse({
    seat_id: 'td-jakes',
    lenses_used: ['instinct-intellect-balance', 'inside-out-manifestation'],
  }).filter((d) => d.code === 'JAKES_LENS_UNKNOWN');
  assert.equal(diagnostics.length, 2);
});

test('an option_scores entry with evidence_ids_note stays rejected', () => {
  const card = validAuthorCard();
  (card.option_scores as Array<Record<string, unknown>>)[0].evidence_ids_note =
    'sourced from the seat pack';
  const result = advisorCardAuthorSchema.safeParse(card);
  assert.equal(result.success, false);
  const issues = JSON.stringify(result.success ? [] : result.error.issues);
  assert.match(issues, /evidence_ids_note/);
  assert.match(issues, /Unrecognized key/);
});

test('the one repair turn restates the round, the lens IDs, and the closed-object rule', () => {
  const repair = cardRepairInstruction(
    'advisor',
    ['crux-1'],
    [
      'round: challenge cards are round 3, got 2',
      'source_use JAKES_LENS_UNKNOWN: Lens instinct-intellect-balance is not one of the seat\'s three lenses.',
      'option_scores.0: Unrecognized key: "evidence_ids_note"',
    ],
    3,
  );
  assert.match(repair, /"round" field must be the number 3/);
  for (const lens of JAKES_LENSES) {
    assert.ok(repair.includes(lens));
  }
  assert.match(repair, /any extra key fails validation/);
  const system = cardRequestSystem('BASE', 'advisor', ['crux-1'], [], 3);
  assert.match(system, /"round" field must be the number 3/);
});

test('ratification states round 3; consult states no round', () => {
  assert.match(cardContractInstruction('ratification', null, 3), /"round" field must be the number 3/);
  assert.doesNotMatch(cardContractInstruction('consult', null), /"round" field/);
});

test('the CLI engine passes the call round on the repair turn', () => {
  // The defect was the call site: generation passed the round while the
  // repair turn omitted it, so the restated contract silently dropped the
  // round rule. Pin the argument itself.
  const engineSource = readFileSync(
    new URL('../src/cli/engine.ts', import.meta.url),
    'utf8',
  );
  assert.match(
    engineSource,
    /cardRepairInstruction\(\s*purpose,\s*challengeIds,\s*lastIssues,\s*purpose === 'consult' \? null : round,?\s*\)/,
    'the repair call must pass the same round as generation (null for consult)',
  );
});

test('a consult repair turn states no round rule', () => {
  const repair = cardRepairInstruction(
    'consult',
    null,
    ['response was not valid JSON: unexpected token }'],
    null,
  );
  assert.doesNotMatch(repair, /"round" field/);
});
