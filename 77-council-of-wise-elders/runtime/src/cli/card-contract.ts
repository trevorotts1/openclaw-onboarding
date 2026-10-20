/**
 * Card contract conveyance (RP-046-4, DEFECT-046-C).
 *
 * Attempt 4 of the D-021 canary proved the transport, the lease
 * heartbeat (RP-046-3), the response extraction, and the strict
 * validator all working as designed, and the session still blocked
 * in Round 1: five of nine seats returned parseable JSON whose
 * CONTENT failed the card schema even after the one permitted
 * repair. Diagnosis from the code, per failure class:
 *
 * - The two format rules that failed (challenges_answered entries
 *   must be opaque IDs; conditions[].due_at must be a UTC ISO 8601
 *   timestamp or null) exist only as zod refinement messages. The
 *   JSON Schema generated from the same definitions drops
 *   refinements, so in the schema the model actually receives those
 *   fields are plain strings: the rules reached the model nowhere,
 *   in prose or in schema.
 * - The complete required-field list existed only as the JSON
 *   Schema's required array, buried in the input payload; the prose
 *   instruction never named the fields, so a partial card had no
 *   checklist to be written against.
 * - For a Round 1 call, no challenge IDs are issued or conveyed at
 *   all (challenges are computed after Round 1 and assigned in
 *   Round 2), so the model had to guess what challenges_answered
 *   should hold; the seats that failed wrote names and text.
 * - The repair turn forwarded only the validator's error strings.
 *   Section 15.5 requires the repair to carry the exact validation
 *   errors AND the original constraints; the constraints were never
 *   restated, so the repair gave the model nothing new to comply
 *   with, and every failed seat failed again in the same shape.
 *
 * This module is the conveyance repair: the exact contract for THIS
 * call, stated in prose, in the composed request and restated in
 * full in the repair instruction. It changes only what the model is
 * told. The validator, the schemas, the single permitted repair,
 * the ledger, and the lease behavior are all unchanged: a
 * non-conforming card still fails validation in exactly the same
 * words as before.
 */

import { SEAT_ROSTER, cardAuthorJsonSchema } from '../contracts/index.js';

export type CardContractPurpose = 'advisor' | 'ratification' | 'consult';

/** A concrete value in the only due_at shape the validator accepts. */
export const DUE_AT_EXAMPLE = '2026-11-15T17:00:00Z';

/**
 * The required field names for a card kind, read from the same
 * generated JSON Schema the validator enforces, so the prose list
 * can never drift from the enforced contract.
 */
export function requiredCardFields(purpose: CardContractPurpose): string[] {
  const schema = cardAuthorJsonSchema(purpose) as { required?: unknown };
  if (!Array.isArray(schema.required)) return [];
  return schema.required.filter(
    (field): field is string => typeof field === 'string',
  );
}

/**
 * Two validator rules the contract never told the model (real-run
 * acceptance, session sess-3d85c907): evidence reference fields accept
 * only evidence manifest IDs, and lenses_used belongs to td-jakes only.
 */
export const EVIDENCE_ID_RULE =
  'Evidence reference arrays (evidence_ids, option_scores[].evidence_ids, framework_applications[].case_evidence_ids) may hold only evidence_id values copied from the evidence manifest in the supplied input. The brief\'s own fact, assumption, unknown, and constraint IDs (for example fact-1, asm-1, unk-1, con-1) are NOT evidence IDs and fail validation if used there. When the evidence manifest is empty or no entry fits, those arrays must be [].';
export const LENSES_RULE =
  'lenses_used: omit this field entirely unless seat_id is "td-jakes". Any other seat that includes lenses_used fails validation.';

/**
 * The contract lines for one operation.
 *
 * `challengeIds` is the per-call challenge issuance: for advisor
 * calls, the challenge IDs issued to this seat for THIS call (an
 * empty array when none have been issued, which is every Round 1
 * call); null for purposes that issue no challenges.
 */
export function cardContractLines(
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
): string[] {
  const fields = requiredCardFields(purpose);
  const lines = [
    'Return exactly one JSON object and nothing else: no prose, no markdown, no code fences.',
    `The object's "card_kind" field must be exactly "${purpose}" and the object must conform to the supplied JSON Schema. No other card_kind value is valid for this call.`,
    `Include every required field, with a value for each: ${fields.join(', ')}. A card missing any of these fields fails validation; a partial card is not accepted.`,
    'Copy schema_version, session_id, brief_revision, seat_id, input_manifest_sha256, and pack_version exactly from the supplied input; do not invent or alter them.',
    'Every ID string in the card must be an opaque ID: letters, digits, and the characters . _ : - only, with no spaces. Copy IDs exactly from the supplied input where one is supplied. Never put a person\'s name, a framework name, a title, or a sentence in an ID field.',
    EVIDENCE_ID_RULE,
  ];
  if (purpose === 'advisor') {
    lines.push(LENSES_RULE);
    if (challengeIds !== null && challengeIds.length > 0) {
      lines.push(
        `challenges_answered must contain exactly the challenge IDs issued to you for this call, copied verbatim, and nothing else: ${challengeIds.join(', ')}.`,
      );
    } else {
      lines.push(
        'challenges_answered: no challenges have been issued to you for this call, so challenges_answered must be an empty array [].',
      );
    }
    lines.push(
      `conditions[].due_at: use null when no date is required. A non-null due_at must be a UTC ISO 8601 timestamp in the exact form ${DUE_AT_EXAMPLE} (date, the letter T, 24-hour time, trailing Z). A date alone, or words such as "next week", fail validation.`,
    );
  }
  return lines;
}

/** The instruction carried in every composed request's output contract. */
export function cardContractInstruction(
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
): string {
  return cardContractLines(purpose, challengeIds).join('\n');
}

/** Marks a repair issue as "the reply did not parse"; the text after it is the parser's message. */
export const NOT_JSON_ISSUE = 'response was not valid JSON: ';

/**
 * For a validation code that concerns a closed set, list the allowed
 * values from the same roster the validator checks against.
 */
function closedSetHints(issues: string[]): string[] {
  if (!issues.some((issue) => issue.includes('JAKES_LENS_UNKNOWN'))) return [];
  const lenses = SEAT_ROSTER.find((s) => s.seat_id === 'td-jakes')?.lenses ?? [];
  return [`lenses_used may contain only these values: ${lenses.join(', ')}.`];
}

/**
 * The repair instruction (Section 15.5: the exact validation errors
 * AND the original constraints). The validator's failures verbatim,
 * then the full contract for this call restated, then the explicit
 * demand for the complete corrected card only.
 */
export function cardRepairInstruction(
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
  issues: string[],
): string {
  const notJson = issues[0]?.startsWith(NOT_JSON_ISSUE) ? issues[0].slice(NOT_JSON_ISSUE.length) : null;
  return [
    notJson !== null
      ? `Your previous reply was not valid JSON: ${notJson}. Reply with exactly one JSON object and nothing else.`
      : `Your previous output failed validation: ${issues.join('; ')}.`,
    ...closedSetHints(issues),
    'The contract for this call, restated in full:',
    ...cardContractLines(purpose, challengeIds),
    'Return the complete corrected card only: one JSON object with every required field present, and nothing else (no prose, no markdown, no code fences, no partial card).',
  ].join('\n');
}

/**
 * The card contract for one request on any path (RP-046-3/4 on the
 * CLI engine; W30 on the service executors): the output_contract
 * object that rides in the request input, and the system text with
 * the contract instruction (plus, on the one permitted repair, the
 * exact validation issues and the full contract restated).
 */
export function cardOutputContract(
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
) {
  return {
    card_kind: purpose,
    instruction: cardContractInstruction(purpose, challengeIds),
    json_schema: cardAuthorJsonSchema(purpose),
  };
}

export function cardRequestSystem(
  baseSystem: string,
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
  repairIssues: string[],
): string {
  const system = `${baseSystem}\n${cardContractInstruction(purpose, challengeIds)}`;
  return repairIssues.length > 0
    ? `${system}\n${cardRepairInstruction(purpose, challengeIds, repairIssues)}`
    : system;
}

/** Issue text allowance reserved beside the restated contract on a repair. */
const REPAIR_ISSUES_RESERVE = 'x'.repeat(2048);

/**
 * Worst-case system bytes for a request (the repair form), so the
 * context budget reserves room for the contract prose it now carries.
 */
export function cardSystemBytes(
  baseSystem: string,
  purpose: CardContractPurpose,
): number {
  return new TextEncoder().encode(
    cardRequestSystem(baseSystem, purpose, [], [REPAIR_ISSUES_RESERVE]),
  ).length;
}
