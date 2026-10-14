/**
 * Deterministic fixture transport and sample session (CWE-004).
 *
 * This transport exists ONLY for isolated foundation tests and the
 * labeled sample/replay path. It is never registered by the production
 * composition (local-host.ts registers no transport by default), it
 * spends nothing, and its output is synthetic by construction: for the
 * golden brief shape it answers with the Section 32.2 golden score
 * table, so the full pipeline (validation, scoring, verdict) can be
 * proven end to end deterministically. It proves wiring only
 * (Section 34.2); it is not a model, not a qualification, and not live
 * inference.
 *
 * Sample sessions use CWE-003's synthetic fixtures, are stored with
 * sample: true, carry the sample label in every surface the CLI
 * renders, and can never create production actions: this core exposes
 * no task-creation operation at all, and sample action proposals are
 * data with execution_authorization_required, nothing more.
 */

import {
  canonicalHash,
  GOLDEN_SCORES,
  SEAT_IDS,
  type DecisionBrief,
  type ScopeFields,
  type SessionSpec,
} from '../contracts/index.js';
import {
  validBrief,
  validSessionSpec,
} from '../contracts/fixtures/examples.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from './host-ports.js';

interface FixtureInput {
  brief: DecisionBrief;
  input_manifest_sha256: string;
  pack_version: string;
  draft_resolution?: { recommended_option_id: string; semantic_sha256: string };
  challenges_for_seat?: Array<{ crux_id: string; question: string }>;
}

function goldenScore(seatId: string, optionId: string): number | null {
  const index = SEAT_IDS.indexOf(seatId as (typeof SEAT_IDS)[number]);
  if (index < 0) return null;
  const table = (GOLDEN_SCORES as Record<string, ReadonlyArray<{ score: number | null }>>)[optionId];
  if (!table) return null;
  return table[index]?.score ?? null;
}

function derivedScore(seatId: string, optionId: string): number {
  let h = 0;
  const text = `${seatId}:${optionId}`;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return 4 + (h % 6); // deterministic 4..9
}

function scoreFor(seatId: string, optionId: string): number {
  return goldenScore(seatId, optionId) ?? derivedScore(seatId, optionId);
}

export class DeterministicFixtureTransport implements ModelTransport {
  private counter = 0;

  async generate(request: TransportRequest): Promise<TransportResponse> {
    const input = request.input as FixtureInput;
    const brief = input.brief;
    const evidenceId = brief.evidence_manifest[0]?.evidence_id;
    const base = {
      schema_version: 'wise-elders.card/v1',
      session_id: brief.session_id,
      brief_revision: brief.revision,
      seat_id: request.seat_id,
      input_manifest_sha256: input.input_manifest_sha256,
      pack_version: input.pack_version,
    };
    let card: Record<string, unknown>;
    if (request.purpose === 'consult') {
      card = {
        ...base,
        card_kind: 'consult',
        answer:
          'Fixture answer: examine the decision against the frozen brief, name the binding constraint, and take the smallest reversible step that produces real evidence.',
        framework_applications: [
          {
            framework_id: 'fixture-framework-application',
            source_evidence_ids: evidenceId ? [evidenceId] : [],
            case_evidence_ids: [],
            application:
              'Applied the fixture framework to the facts in the frozen brief only.',
            attribution_kind: 'blackceo_adaptation',
          },
        ],
        evidence_ids: evidenceId ? [evidenceId] : [],
        assumptions: ['Fixture assumption, labeled as such.'],
        limits: ['This is deterministic fixture output, not live model inference.'],
        next_step: 'Review the frozen brief and confirm the constraint still holds.',
      };
    } else if (request.purpose === 'ratification') {
      const recommended = input.draft_resolution?.recommended_option_id ?? brief.options[0].id;
      const scores = brief.options.map((o) => ({
        option_id: o.id,
        score: scoreFor(request.seat_id, o.id),
        rationale: `Fixture ratification score for ${o.id}.`,
        evidence_ids: evidenceId ? [evidenceId] : [],
      }));
      const top = scores.reduce((a, b) => ((b.score ?? 0) > (a.score ?? 0) ? b : a));
      card = {
        ...base,
        card_kind: 'ratification',
        round: 3,
        draft_resolution_sha256:
          input.draft_resolution?.semantic_sha256 ??
          '0000000000000000000000000000000000000000000000000000000000000000',
        resolution_stance: top.option_id === recommended ? 'support' : 'conditional_support',
        stance: top.option_id === recommended ? 'support' : 'conditional',
        preferred_option_id: top.option_id,
        option_scores: scores,
        amendments: [],
        accepted_condition_ids: [],
        unresolved_objections: [],
        evidence_strength: 'medium',
      };
    } else {
      const scores = brief.options.map((o) => ({
        option_id: o.id,
        score: scoreFor(request.seat_id, o.id),
        rationale: `Fixture ${request.round === 2 ? 'challenge-round' : 'opening'} score for ${o.id} from seat ${request.seat_id}.`,
        evidence_ids: evidenceId ? [evidenceId] : [],
      }));
      const top = scores.reduce((a, b) => ((b.score ?? 0) > (a.score ?? 0) ? b : a));
      card = {
        ...base,
        card_kind: 'advisor',
        round: request.round ?? 1,
        stance: 'conditional',
        preferred_option_id: top.option_id,
        option_scores: scores,
        framework_applications: [
          {
            framework_id: 'fixture-framework-application',
            source_evidence_ids: evidenceId ? [evidenceId] : [],
            case_evidence_ids: [],
            application:
              'Applied the fixture framework to the facts in the frozen brief only.',
            attribution_kind: 'blackceo_adaptation',
          },
        ],
        decisive_arguments: [
          `The bounded option produces evidence before the broad commitment is made (fixture seat ${request.seat_id}).`,
        ],
        strongest_objection: 'The fixture objection: retention evidence is not yet measured.',
        conditions: [],
        critical_unknowns: ['Fixture unknown: measured retention for the pilot cohort.'],
        change_my_mind: 'Measured evidence that the binding constraint no longer holds.',
        challenges_answered: (input.challenges_for_seat ?? []).map((c) => c.crux_id),
        quotes: [],
        evidence_strength: 'medium',
        minority_position: null,
      };
    }
    this.counter += 1;
    return {
      text: JSON.stringify(card),
      provider_request_id: `fixture-req-${this.counter}`,
      reported_model_id: 'deterministic-fixture-transport',
      usage: { input_tokens: null, output_tokens: null },
    };
  }
}

/** The labeled synthetic sample session, built from CWE-003 fixtures. */
export function buildSampleSession(): {
  spec: SessionSpec;
  brief: DecisionBrief;
  scope: ScopeFields;
} {
  const spec = JSON.parse(JSON.stringify(validSessionSpec)) as SessionSpec;
  const brief = JSON.parse(JSON.stringify(validBrief)) as DecisionBrief;
  // The CWE-003 fixture carries a placeholder brief hash; the sample
  // session binds the spec to the brief's real canonical hash so the
  // pair passes the same integrity check as any production session.
  spec.brief_sha256 = canonicalHash(brief);
  return {
    spec,
    brief,
    scope: {
      tenant_id: 'sample-tenant',
      company_id: 'sample-company',
      installation_id: 'sample-installation',
      owner_subject: null,
    },
  };
}
