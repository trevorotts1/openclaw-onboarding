/**
 * CWE-023 guided intake question flow (directive Sections 9.2, 9.3).
 *
 * One question at a time, asked only when the missing answer could
 * materially change the recommendation. Stable question IDs are the
 * resume contract: the current step is computed from the saved draft,
 * so a refresh, disconnect, or process restart restores the exact
 * step and never re-issues an answered question.
 *
 * Retrieval runs before questions (Section 9.2): confirmed facts the
 * host supplied through CWE-022 at begin time pre-answer the facts
 * step. Intake never asks for what authorized retrieval already holds.
 *
 * Material questions must be answered before freeze; "I don't know
 * yet" is a valid answer where the question allows an explicit
 * unknown. Optional questions may be skipped; the skip is recorded,
 * not treated as an answer.
 */
import type { IntakeDraft } from './types.js';

export type IntakeQuestionId =
  | 'decision'
  | 'options'
  | 'success'
  | 'constraints'
  | 'facts'
  | 'unknowns'
  | 'assumptions'
  | 'stakeholders'
  | 'mode_panel'
  | 'route'
  | 'preference';

export interface IntakeQuestion {
  readonly id: IntakeQuestionId;
  /** Material questions block freeze until answered. */
  readonly material: boolean;
  /** Whether an explicit "I don't know yet" counts as an answer. */
  readonly allows_explicit_unknown: boolean;
  readonly title: string;
  readonly guidance: string;
}

/** The canonical question order. Resume walks this list, nothing else. */
export const INTAKE_QUESTIONS: readonly IntakeQuestion[] = [
  {
    id: 'decision',
    material: true,
    allows_explicit_unknown: false,
    title: 'What decision are you making?',
    guidance:
      'One understandable choice or question, not an entire business plan. Structured flags record whether money, an offer, a pivot, stakeholders, communication, or a professional domain are involved.',
  },
  {
    id: 'options',
    material: true,
    allows_explicit_unknown: false,
    title: 'What are the alternatives?',
    guidance:
      'Two to five explicit options for scored modes; include the status quo and a smaller test when relevant.',
  },
  {
    id: 'success',
    material: true,
    allows_explicit_unknown: true,
    title: 'What would success look like?',
    guidance:
      'The outcome and its horizon. No invented target: an explicit unknown is recorded as an unknown.',
  },
  {
    id: 'constraints',
    material: true,
    allows_explicit_unknown: true,
    title: 'What limits apply?',
    guidance:
      'Budget and cash, time, capacity, obligations, reversibility, and prohibited actions. Ranges are acceptable; exact figures are never forced.',
  },
  {
    id: 'facts',
    material: true,
    allows_explicit_unknown: true,
    title: 'What is already known?',
    guidance:
      'Facts the client states now. Confirmed facts retrieved with authorization are already here and are never asked for again.',
  },
  {
    id: 'unknowns',
    material: true,
    allows_explicit_unknown: true,
    title: 'What is not known yet?',
    guidance:
      'Unknowns that could change the choice, and how each could be resolved. An empty list is an answer: the client states nothing material is unknown.',
  },
  {
    id: 'assumptions',
    material: false,
    allows_explicit_unknown: false,
    title: 'What is being assumed?',
    guidance:
      'Assumptions are labeled as assumptions; they are never silently converted to facts.',
  },
  {
    id: 'stakeholders',
    material: false,
    allows_explicit_unknown: false,
    title: 'Who is affected?',
    guidance: 'People or groups affected by the decision, for stakeholder-aware review.',
  },
  {
    id: 'mode_panel',
    material: true,
    allows_explicit_unknown: false,
    title: 'Which council mode and panel?',
    guidance:
      'Full, quick, selected seats, or one-seat consult. Required critical responsibilities for the panel are computed and shown before start; the panel is never changed silently.',
  },
  {
    id: 'route',
    material: true,
    allows_explicit_unknown: false,
    title: 'Which model route?',
    guidance:
      'The explicitly selected route, or the configured default inherited and displayed. The route snapshot is pinned on the brief revision and never silently replaced.',
  },
  {
    id: 'preference',
    material: false,
    allows_explicit_unknown: false,
    title: 'Which way are you leaning?',
    guidance:
      'Stored separately as client_preference_private. It is never merged into the brief and never reaches Round 1 context.',
  },
];

const QUESTION_BY_ID = new Map(INTAKE_QUESTIONS.map((q) => [q.id, q]));

export function questionById(id: string): IntakeQuestion | null {
  return QUESTION_BY_ID.get(id as IntakeQuestionId) ?? null;
}

/**
 * Whether a question counts as answered for this draft. Facts are
 * answered when the client stated facts OR authorized retrieval
 * already supplied confirmed facts (Section 9.2: never re-ask).
 * Preference is answered exactly when a preference record exists.
 */
export function isQuestionAnswered(draft: IntakeDraft, id: IntakeQuestionId): boolean {
  const a = draft.answers;
  switch (id) {
    case 'decision':
      return a.decision !== null;
    case 'options':
      return a.options !== null;
    case 'success':
      return a.success !== null;
    case 'constraints':
      return a.constraints !== null;
    case 'facts':
      return a.facts !== null || draft.known_facts.length > 0;
    case 'unknowns':
      return a.unknowns !== null;
    case 'assumptions':
      return a.assumptions !== null;
    case 'stakeholders':
      return a.stakeholders !== null;
    case 'mode_panel':
      return draft.mode !== null && draft.panel_seat_ids !== null;
    case 'route':
      return draft.route_choice !== null;
    case 'preference':
      return draft.preference_ref !== null;
  }
}

/**
 * The exact step an interrupted intake resumes at: the first question
 * in canonical order that is neither answered nor explicitly skipped.
 * Null when the flow is complete.
 */
export function currentQuestion(draft: IntakeDraft): IntakeQuestion | null {
  for (const question of INTAKE_QUESTIONS) {
    if (isQuestionAnswered(draft, question.id)) continue;
    if (draft.skipped_question_ids.includes(question.id)) continue;
    return question;
  }
  return null;
}

/** Material questions still blocking freeze, in canonical order. */
export function missingMaterialQuestions(draft: IntakeDraft): IntakeQuestionId[] {
  return INTAKE_QUESTIONS.filter(
    (q) => q.material && !isQuestionAnswered(draft, q.id),
  ).map((q) => q.id);
}

/** Freeze readiness on the question flow alone (panel/route included). */
export function isFlowReadyToFreeze(draft: IntakeDraft): boolean {
  return missingMaterialQuestions(draft).length === 0;
}
