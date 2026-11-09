/**
 * Card contract conveyance (RP-046-4, DEFECT-046-C; CTR-138).
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
 *
 * CTR-138, from the round-3 sitting sess-ad4ee659 (2026-10-30):
 * three further rules the validator enforces were missing from the
 * explicit card contract before generation.
 * - The call's round number was absent from that contract, and from
 *   the prompt for seats that already had a challenge assigned, so
 *   seats reported the previous round ("round: challenge cards are
 *   round 3, got 2").
 * - The three approved Jakes lens IDs were named only AFTER a
 *   failure, so the seat invented them
 *   ("source_use JAKES_LENS_UNKNOWN: Lens instinct-intellect-balance
 *   is not one of the seat's three lenses"), and the generated
 *   schema typed lenses_used as free text while the validator
 *   accepts three values.
 * - The closed-object rule was never stated, so an option_scores
 *   entry carried an extra "evidence_ids_note" key and was rejected
 *   ("option_scores.0: Unrecognized key: \"evidence_ids_note\"").
 * The same rules are now stated up front and restated on the one
 * permitted repair.
 */

import { SEAT_ROSTER, cardAuthorJsonSchema } from '../contracts/index.js';

export type CardContractPurpose = 'advisor' | 'ratification' | 'consult';

/** A concrete value in the only due_at shape the validator accepts. */
export const DUE_AT_EXAMPLE = '2026-11-15T17:00:00Z';

/**
 * The three approved lenses of the Jakes seat, read from the same
 * roster the validator checks (src/sources/packs.ts), so the contract
 * can never name a lens the validator rejects.
 */
export const JAKES_LENS_IDS: readonly string[] =
  SEAT_ROSTER.find((s) => s.seat_id === 'td-jakes')?.lenses ?? [];

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
 * The keys one option_scores entry accepts, read from the same
 * generated JSON Schema the validator enforces.
 */
export function optionScoreFields(purpose: CardContractPurpose): string[] {
  const schema = cardAuthorJsonSchema(purpose) as {
    properties?: Record<
      string,
      { items?: { properties?: Record<string, unknown> } }
    >;
  };
  return Object.keys(schema.properties?.option_scores?.items?.properties ?? {});
}

/**
 * Two validator rules the contract never told the model (real-run
 * acceptance, session sess-3d85c907): evidence reference fields accept
 * only evidence manifest IDs, and lenses_used belongs to td-jakes only.
 */
export const EVIDENCE_ID_RULE =
  'Evidence reference arrays (evidence_ids, option_scores[].evidence_ids, framework_applications[].case_evidence_ids) may hold only evidence_id values copied from the evidence manifest in the supplied input. The brief\'s own fact, assumption, unknown, and constraint IDs (for example fact-1, asm-1, unk-1, con-1) are NOT evidence IDs and fail validation if used there. When the evidence manifest is empty or no entry fits, those arrays must be [].';

/** The Jakes lens rule, with the three approved IDs named up front. */
export const LENSES_RULE =
  `lenses_used: omit this field entirely unless seat_id is "td-jakes". Any other seat that includes lenses_used fails validation. For "td-jakes" it may hold only these exact IDs, copied verbatim: ${JAKES_LENS_IDS.join(', ')}. Any other lens name fails validation, and the seat is still ONE seat and ONE vote.`;

/** The object's round number, which the validator checks per round. */
export function roundRule(round: number): string {
  return `The object's "round" field must be the number ${round}, a JSON number, because this call is round ${round}. Any other round value fails validation.`;
}

/**
 * CTR-151 future-generation wording.
 *
 * The reader report builds its summary, its ordered actions, and its
 * "information needed" list from fields the seat already writes. In the
 * observed 47-page report those fields carried round-internal shorthand
 * ("crux-2", "opt-repurpose-longform") that a client cannot act on.
 *
 * This rule names only fields the strict schema ALREADY enforces. It adds
 * no field, relaxes no validation, and spends no extra call. CTR-155: it is
 * sent only for `purpose === 'advisor'`, the one card kind whose schema
 * defines the named fields; ratification and consult never receive it.
 */
export const PLAIN_LANGUAGE_RULE = [
  'Write the reader-facing fields in plain language for a busy non-specialist, using only the fields the schema already defines:',
  'conditions[].description is the ACTION: one concrete instruction a person could start, in ordinary words, with no internal jargon, shorthand, or ID;',
  'critical_unknowns[] is the INFORMATION NEEDED: each entry names one fact the client must supply, phrased as a plain question or as what is missing;',
  'decisive_arguments[] opens with the plain SUMMARY of your reasoning in one short sentence a non-expert could repeat, then the detail that supports it;',
  'change_my_mind is the one piece of evidence that would change your position, in plain words.',
  'Never invent a deadline, metric, result, owner, or approval: if it is not in the supplied input, record it as an unknown or leave it null.',
].join(' ');

/**
 * Every card object is a strict object in the enforced schema: a key
 * the schema does not name fails validation.
 */
export function closedObjectRule(purpose: CardContractPurpose): string {
  const fields = optionScoreFields(purpose);
  const base =
    'Every JSON object in the card is closed: it accepts only the keys the supplied JSON Schema names, and any extra key fails validation.';
  if (fields.length === 0) {
    return `${base} Do not add explanatory note fields anywhere in the object.`;
  }
  return `${base} Each option_scores entry accepts exactly ${fields.join(', ')}; put any commentary in "rationale" and never add a note or explanation key to an entry.`;
}

/**
 * The contract lines for one operation.
 *
 * `challengeIds` is the per-call challenge issuance: for advisor
 * calls, the challenge IDs issued to this seat for THIS call (an
 * empty array when none have been issued, which is every Round 1
 * call); null for purposes that issue no challenges.
 *
 * `round` is the round number this call must report on the card;
 * null when the purpose carries no round (consult).
 */
export function cardContractLines(
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
  round: number | null = null,
): string[] {
  const fields = requiredCardFields(purpose);
  const lines = [
    'Return exactly one JSON object and nothing else: no prose, no markdown, no code fences.',
    `The object's "card_kind" field must be exactly "${purpose}" and the object must conform to the supplied JSON Schema. No other card_kind value is valid for this call.`,
    ...(round === null ? [] : [roundRule(round)]),
    `Include every required field, with a value for each: ${fields.join(', ')}. A card missing any of these fields fails validation; a partial card is not accepted.`,
    'Copy schema_version, session_id, brief_revision, seat_id, input_manifest_sha256, and pack_version exactly from the supplied input; do not invent or alter them.',
    'Every ID string in the card must be an opaque ID: letters, digits, and the characters . _ : - only, with no spaces. Copy IDs exactly from the supplied input where one is supplied. Never put a person\'s name, a framework name, a title, or a sentence in an ID field.',
    EVIDENCE_ID_RULE,
    closedObjectRule(purpose),
  ];
  if (purpose === 'advisor') {
    // CTR-155: only the advisor schema carries conditions[], critical_unknowns[],
    // decisive_arguments[] and change_my_mind. Sending this rule to
    // ratification or consult invited the model to satisfy fields its own
    // schema does not define, so it is scoped to the advisor purpose.
    lines.push(PLAIN_LANGUAGE_RULE);
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
  round: number | null = null,
): string {
  return cardContractLines(purpose, challengeIds, round).join('\n');
}

/** Marks a repair issue as "the reply did not parse"; the text after it is the parser's message. */
export const NOT_JSON_ISSUE = 'response was not valid JSON: ';

/**
 * For a validation code that concerns a closed set, list the allowed
 * values from the same roster the validator checks against.
 */
function closedSetHints(issues: string[]): string[] {
  if (!issues.some((issue) => issue.includes('JAKES_LENS_UNKNOWN'))) return [];
  return [`lenses_used may contain only these values: ${JAKES_LENS_IDS.join(', ')}.`];
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
  round: number | null = null,
): string {
  const notJson = issues[0]?.startsWith(NOT_JSON_ISSUE) ? issues[0].slice(NOT_JSON_ISSUE.length) : null;
  return [
    notJson !== null
      ? `Your previous reply was not valid JSON: ${notJson}. Reply with exactly one JSON object and nothing else.`
      : `Your previous output failed validation: ${issues.join('; ')}.`,
    ...closedSetHints(issues),
    'The contract for this call, restated in full:',
    ...cardContractLines(purpose, challengeIds, round),
    'Return the complete corrected card only: one JSON object with every required field present, and nothing else (no prose, no markdown, no code fences, no partial card).',
  ].join('\n');
}

/**
 * The generated schema types lenses_used as free text while the
 * validator accepts only the seat's three lenses. Restrict the schema
 * handed to the model to the same closed set, read from the roster, so
 * the two cannot disagree. The generated artifact, the committed
 * contracts, and the validator are untouched.
 */
function restrictLensesToApprovedSet(schema: unknown): unknown {
  if (typeof schema !== 'object' || schema === null) return schema;
  const properties = (schema as { properties?: unknown }).properties;
  if (typeof properties !== 'object' || properties === null) return schema;
  const field = (properties as Record<string, unknown>).lenses_used;
  if (typeof field !== 'object' || field === null) return schema;
  const items = (field as { items?: unknown }).items;
  if (typeof items !== 'object' || items === null) return schema;
  (items as { enum?: readonly string[] }).enum = [...JAKES_LENS_IDS];
  return schema;
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
  round: number | null = null,
) {
  return {
    card_kind: purpose,
    instruction: cardContractInstruction(purpose, challengeIds, round),
    json_schema: restrictLensesToApprovedSet(cardAuthorJsonSchema(purpose)),
  };
}

export function cardRequestSystem(
  baseSystem: string,
  purpose: CardContractPurpose,
  challengeIds: string[] | null,
  repairIssues: string[],
  round: number | null = null,
): string {
  const system = `${baseSystem}\n${cardContractInstruction(purpose, challengeIds, round)}`;
  return repairIssues.length > 0
    ? `${system}\n${cardRepairInstruction(purpose, challengeIds, repairIssues, round)}`
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
  round: number | null = null,
): number {
  return new TextEncoder().encode(
    cardRequestSystem(baseSystem, purpose, [], [REPAIR_ISSUES_RESERVE], round),
  ).length;
}
