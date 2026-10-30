/**
 * Council service driver (W28, decisions 2 and 5).
 *
 * A session convened through the service must actually be deliberated:
 * create the session, approve the run, then hand it to runSession in the
 * background over the service's own database, so the existing
 * repositories journal every transition, card and verdict into
 * council_events (which the SSE route streams).
 *
 * CONVENING = APPROVAL (Trevor decision 2026-10-19). The client chose
 * the model and pays for it, so the driver builds the run preview and
 * approves it on the owner's behalf in the same call, using the existing
 * authority mode 'local_interactive_owner' with interactive_confirmation
 * true: the confirmation IS the client's convene act. The authority enum
 * and DB CHECK are untouched (no migration). There is no money ceiling
 * and no extra prompt. The approval row plus one append-only JSONL audit
 * line per run is the audit record. The 50-provider-request ceiling is
 * the protocol's own runaway guard, not a spend gate.
 *
 * No content is invented: the sample path only rebinds the built-in
 * synthetic sample brief (cli/fixture-transport.ts) to a new session id,
 * and every card comes from the resolved route's transport.
 */

import { appendFileSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { TrustedPrincipal } from '../authorization/index.js';
import type { PinnedRouteSnapshot } from '../budgets/route-snapshot.js';
import { buildSampleSession } from '../cli/fixture-transport.js';
import type { Clock, IdSource, StoredSession } from '../cli/host-ports.js';
import { isUnresolvedExplorationOption } from '../brief/exploration.js';
import {
  prepareProposals,
  type ProposalInferenceRequest,
  type ProposedOption,
} from '../brief/proposal-stage.js';
import {
  canonicalHash,
  isCouncilSize,
  MODE_ROUND_POLICY,
  SEAT_IDS,
  validateDecisionBrief,
  validateSessionSpec,
  type CouncilSize,
  type DecisionBrief,
  type ModeRoundPolicy,
  type ModelPolicy,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionMode,
  type SessionSpec,
  type SessionVisibility,
} from '../contracts/index.js';
import { selectMode } from '../flow/mode-select.js';
import {
  isOllamaProvider,
  parallelLimitFor,
  type OllamaPlan,
} from '../providers/parallel.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type {
  DeliberationService,
  RunSessionResult,
} from '../protocol/composition.js';

// Structural stand-ins for the route-choice unit's types. They hold only
// what the driver reads, so route-choice's richer exports are assignable.
// ponytail: swap for `import type` from './route-choice.js' once merged.
export type RouteChoiceErrorCode =
  | 'ROUTE_CHOICE_REQUIRED'
  | 'ROUTE_NOT_CONFIGURED'
  | 'ROUTE_NOT_COMPOSABLE'
  | 'ROUTE_MODEL_LIST_UNAVAILABLE'
  | 'ROUTE_LATEST_FLASH_NOT_FOUND'
  | 'ROUTE_MODEL_NOT_OFFERED';
export interface RouteChoiceRequest {
  route_id?: string | null;
  model?: string | null;
  harness?: 'claude-nine' | 'claude-code' | 'deepseek' | 'unknown' | null;
}
export interface ResolvedSessionRoute {
  snapshot: PinnedRouteSnapshot;
  model_policy: ModelPolicy;
  model_label: string;
  selection_source: 'explicit' | 'client_default';
  harness: string | null;
}

/**
 * CTR-134: the configured runtime model request adapter, bound to the exact
 * route/model the caller's convene resolved. The service composition supplies
 * this from `transportForSnapshot(snapshot)` — the SAME adapter the sitting
 * uses — in its one-shot form (one attempt, no retry, no fallback).
 */
export type PreparationInference = (
  route: ResolvedSessionRoute,
  request: ProposalInferenceRequest,
  context: { session_id: string },
) => Promise<{ text: string }>;

/** Bounded preparation accounting shown with the accepted sitting. */
export interface PreparationRecord {
  state: 'prepared';
  request_budget: 1;
  request_count: 1;
  route_id: string;
  model_label: string;
  alternatives_are_proposals: true;
}
/** A web finding gathered by the convening agent (sources/elder-knowledge.ts). */
export interface FreshFact {
  claim: string;
  url: string;
  title: string | null;
  retrieved_at: string;
}

export interface ConveneInput {
  /** Built-in harmless sample decision, rebound to a new session id. */
  sample?: boolean;
  brief?: DecisionBrief;
  mode?: SessionMode;
  seat_ids?: SeatId[];
  /** The client's Ollama plan; remembered in <dataDir>/provider-plan.json. */
  ollama_plan?: OllamaPlan | null;
  /** OpenRouter model to fall back to when the primary route is Ollama. */
  fallback_model?: string | null;
  visibility?: SessionVisibility;
  route: RouteChoiceRequest;
  fresh_facts?: FreshFact[];
  requested_by: string;
}

/** Rounds a council size may run, as the client-facing summary prints them. */
export interface ConveneRoundsPolicy {
  min_rounds: number;
  max_rounds: number;
  stop_from_round: number | null;
}

/**
 * Why and how the sitting's mode was chosen (W77S AUTO-MODE-1062). The
 * client sees this with the session: `mode` is the mode the run uses,
 * `source` says who picked it — the client explicitly, or the automatic
 * classification of the question — and `reason` says why.
 */
export interface ModeSelection {
  mode: SessionMode;
  source: 'client' | 'auto';
  reason: string;
}

export interface ConveneAccepted {
  session_id: string;
  state: string;
  sample: boolean;
  route_id: string;
  model_label: string;
  selection_source: 'explicit' | 'client_default';
  grant_id: string;
  session_path: string;
  events_path: string;
  /** Real session mode (light/medium/heavy or one of the four older modes). */
  mode: SessionMode;
  /** The mode, its source (client|auto) and the reason it was chosen. */
  mode_selection: ModeSelection;
  /** Panel seats the run actually uses. */
  seats: number;
  /** null for the four older modes, whose round shape is fixed. */
  rounds: ConveneRoundsPolicy | null;
  /** The enforced provider-request cap for this session. */
  request_cap: number;
  /** Seats dispatched at once (1 for the older modes, today's behaviour). */
  parallel_limit: number;
  /** One plain line: the fallback route, or none and why. */
  fallback: string;
  /**
   * Present only when the brief carried no substantive alternative and ONE
   * preparatory request proposed them. The alternatives are labelled
   * proposals, never client facts, and the sitting's cap already accounts
   * for the request.
   */
  preparation?: PreparationRecord;
}

export type DriverRefusalCode =
  | 'COMPOSITION_NOT_READY'
  | 'CONVENE_INPUT_INVALID'
  | 'COUNCIL_PREPARATION_REQUIRED'
  | 'OLLAMA_PLAN_REQUIRED'
  | RouteChoiceErrorCode;

export class DriverRefusal extends Error {
  constructor(
    readonly code: DriverRefusalCode,
    message: string,
    readonly recovery: string,
    readonly http_status: 409 | 422 | 503,
    readonly detail: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'DriverRefusal';
  }
}

export interface CouncilDriverDeps {
  deliberation: DeliberationService;
  /** Owner write envelope. */
  envelope: AuthorizationEnvelope;
  scope: ScopeFields;
  /** Principal arriving through the local_owner channel. */
  principal: TrustedPrincipal;
  clock: Clock;
  ids: IdSource;
  resolveRoute: (req: RouteChoiceRequest) => Promise<ResolvedSessionRoute>;
  recordFreshFacts?: (sessionId: string, facts: FreshFact[]) => void;
  /** <dataDir>/convening-audit.jsonl */
  auditLogPath: string;
  /** Durable data directory for the remembered Ollama plan. Defaults to dirname(auditLogPath). */
  dataDir?: string;
  onSettled?: (
    sessionId: string,
    result: RunSessionResult | { status: 'error'; code: string },
  ) => void;
  /** Pack version stamped on non-sample sessions. */
  sourcePackVersion?: string;
  /**
   * CTR-134: the configured adapter used for the ONE preparatory request.
   * Absent means an exploratory brief is refused as input-needed instead of
   * being scored on an invented option.
   */
  prepareInference?: PreparationInference;
}

const APPROVAL_BASIS = 'convening_is_approval (Trevor decision 2026-10-19)';
const DEFAULT_PACK_VERSION = 'live-elder-knowledge/v1';

/**
 * Protocol runaway guard only; money and token ceilings stay unset.
 *
 * The four older modes keep exactly the ceiling the client is told and
 * the ceiling they were already enforced at: 50 provider requests, with
 * 9 repairs and 8 transport retries under it (DEFAULT_COUNCIL_SETTINGS).
 * The grant IS the enforced cap, so the printed cap, `status`, the docs
 * and the budget service can never disagree (W77S-MODES review: the
 * earlier 62/27/8 grant was silently raised to 62 by the convening
 * service settings while every client-facing file promised 50).
 *
 * Light/medium/heavy take their ceilings from MODE_ROUND_POLICY instead:
 * the mode's provider cap is the whole guard (money and tokens stay null).
 */
const CONVENING_CEILINGS: RunCeilings = {
  max_provider_requests: 50,
  max_output_repairs: 9,
  max_transport_retries: 8,
  max_input_tokens: null,
  max_output_tokens: null,
  max_money: null,
};

export function ceilingsForMode(mode: SessionMode): RunCeilings {
  if (!isCouncilSize(mode)) return { ...CONVENING_CEILINGS };
  const cap = MODE_ROUND_POLICY[mode].max_provider_requests;
  return {
    max_provider_requests: cap,
    max_output_repairs: cap,
    max_transport_retries: cap,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: null,
  };
}

/** The round shape a council size runs, for the client-facing summary. */
export function roundsPolicyOf(mode: CouncilSize): ConveneRoundsPolicy {
  const policy: ModeRoundPolicy = MODE_ROUND_POLICY[mode];
  return {
    min_rounds: policy.min_rounds,
    max_rounds: policy.max_rounds,
    stop_from_round: policy.stop_from_round,
  };
}

// ---------------------------------------------------------------------------
// CTR-134: one bounded preparation pass before the sitting
// ---------------------------------------------------------------------------

/**
 * A brief is ready to sit when it names at least two real alternatives. The
 * known unresolved exploration candidate is not one, and it is never counted
 * as a decision option.
 */
function substantiveOptionCount(brief: DecisionBrief | undefined): number {
  if (!brief || !Array.isArray(brief.options)) return 0;
  return brief.options.filter(
    (option) =>
      option &&
      typeof option.label === 'string' &&
      option.label.trim().length > 0 &&
      !isUnresolvedExplorationOption(option),
  ).length;
}

/**
 * The preparation stage reads ONLY what the enqueue token already carries:
 * the question, the evidence-bound facts and their locators, the constraints,
 * and the explicit unknowns. Nothing else is read from disk here, and nothing
 * is filled in when it is absent.
 */
function preparationContext(brief: DecisionBrief) {
  const locatorById = new Map<string, string>();
  for (const entry of Array.isArray(brief.evidence_manifest) ? brief.evidence_manifest : []) {
    if (entry && typeof entry.evidence_id === 'string' && typeof entry.locator === 'string') {
      locatorById.set(entry.evidence_id, entry.locator);
    }
  }
  const facts = (Array.isArray(brief.facts) ? brief.facts : [])
    .filter((fact) => fact && typeof fact.statement === 'string' && fact.statement.trim().length > 0)
    .slice(0, 40)
    .map((fact) => {
      const firstId = Array.isArray(fact.evidence_ids) ? fact.evidence_ids[0] : undefined;
      return {
        statement: fact.statement.trim(),
        source: (typeof firstId === 'string' ? locatorById.get(firstId) : null) ?? null,
      };
    });
  const sourcesRead = [...new Set(
    (Array.isArray(brief.evidence_manifest) ? brief.evidence_manifest : [])
      .map((entry) => (entry && typeof entry.locator === 'string' ? entry.locator : ''))
      .filter((locator) => locator.length > 0),
  )];
  const constraints = (Array.isArray(brief.constraints) ? brief.constraints : [])
    .filter((constraint) => constraint && typeof constraint.description === 'string')
    .slice(0, 40)
    .map((constraint) => constraint.description);
  const unknowns = (Array.isArray(brief.unknowns) ? brief.unknowns : [])
    .filter((unknown) => unknown && typeof unknown.statement === 'string')
    .slice(0, 60)
    .map((unknown) => unknown.statement);
  return {
    sources_read: sourcesRead,
    facts,
    constraints,
    unknowns,
  };
}

/**
 * Attach the proposed alternatives to the enqueue token. Every label is kept
 * verbatim from the preparation response; none is renamed into a fact, price
 * or result, and the placeholder is dropped rather than promoted.
 */
function withProposals(
  brief: DecisionBrief,
  options: readonly ProposedOption[],
  unknowns: readonly string[],
): DecisionBrief {
  const kept = (Array.isArray(brief.options) ? brief.options : []).filter(
    (option) => option && !isUnresolvedExplorationOption(option),
  );
  const existing = Array.isArray(brief.unknowns) ? brief.unknowns : [];
  const seen = new Set(existing.map((unknown) => unknown.statement));
  const added = [];
  for (const statement of unknowns) {
    if (typeof statement !== 'string' || statement.trim().length === 0) continue;
    const trimmed = statement.trim();
    if (seen.has(trimmed)) continue;
    seen.add(trimmed);
    added.push({
      id: `unknown-proposed-${added.length + 1}`,
      statement: trimmed,
      evidence_ids: [],
    });
    if (added.length >= 40) break;
  }
  return {
    ...brief,
    options: [...kept, ...options.map((option) => ({ ...option }))],
    unknowns: [...existing, ...added],
  };
}

/** <dataDir>/provider-plan.json — the client's Ollama plan, asked once. */
const PROVIDER_PLAN_FILE = 'provider-plan.json';/** The one question asked when an Ollama route has no known plan (design verbatim). */
const OLLAMA_PLAN_ACTION =
  'Ask the client: are you on the Ollama $20 a month plan or the $100 a month plan? Then convene again with --ollama-plan 20 or --ollama-plan 100.';
/** The OpenRouter route the fallback model is resolved on. */
const FALLBACK_ROUTE_ID = 'openrouter-configured';

// ponytail: the six typed route-choice codes map to a fixed status; a
// route-choice error with an unknown code is rethrown untouched.
const ROUTE_STATUS: Record<RouteChoiceErrorCode, 409 | 422 | 503> = {
  ROUTE_CHOICE_REQUIRED: 422,
  ROUTE_MODEL_NOT_OFFERED: 422,
  ROUTE_NOT_CONFIGURED: 409,
  ROUTE_NOT_COMPOSABLE: 409,
  ROUTE_MODEL_LIST_UNAVAILABLE: 503,
  ROUTE_LATEST_FLASH_NOT_FOUND: 503,
};

function invalid(message: string, detail: Record<string, unknown> = {}): DriverRefusal {
  return new DriverRefusal(
    'CONVENE_INPUT_INVALID',
    message,
    'Send either sample:true or a valid decision brief, plus requested_by, then convene again.',
    422,
    detail,
  );
}

function errorCode(error: unknown): string {
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === 'string' ? code : 'RUN_FAILED';
}

/**
 * Resolve the sitting's mode through the ONE selector (flow/mode-select.ts).
 *
 * An explicit client mode always wins verbatim — all seven SESSION_MODES,
 * including the four older ones, whose round shape stays fixed. With no
 * explicit mode the question's complexity decides (light / medium / heavy).
 * A question with no text at all cannot be classified, so the old default
 * holds: medium, with a reason that says so rather than inventing a score.
 */
export function resolveModeSelection(
  explicit: SessionMode | undefined,
  question: string,
): ModeSelection {
  if (explicit !== undefined) {
    return { mode: explicit, source: 'client', reason: `client selected ${explicit}` };
  }
  const text = typeof question === 'string' ? question.trim() : '';
  if (text === '') {
    return {
      mode: 'medium',
      source: 'auto',
      reason: 'no question text to classify; defaulted to medium',
    };
  }
  return selectMode(text);
}

export function createCouncilDriver(deps: CouncilDriverDeps): {
  convene(input: ConveneInput): Promise<ConveneAccepted>;
  inFlight(): number;
  drain(): Promise<void>;
} {
  const running = new Set<Promise<void>>();

  function planFilePath(): string {
    return join(deps.dataDir ?? dirname(deps.auditLogPath), PROVIDER_PLAN_FILE);
  }

  /** The remembered Ollama plan; null when the client has not been asked yet. */
  function readOllamaPlan(): OllamaPlan | null {
    try {
      const raw = JSON.parse(readFileSync(planFilePath(), 'utf8')) as { ollama_plan?: unknown };
      return raw.ollama_plan === '20' || raw.ollama_plan === '100' ? raw.ollama_plan : null;
    } catch {
      return null;
    }
  }

  /**
   * <dataDir>/provider-plan.json, written when the client supplies the
   * plan and read back when they do not. A failed write loses only the
   * memory (the question is asked once more), never the run.
   */
  function writeOllamaPlan(plan: OllamaPlan): void {
    try {
      const path = planFilePath();
      mkdirSync(dirname(path), { recursive: true });
      const tmp = `${path}.tmp.${process.pid}`;
      writeFileSync(tmp, `${JSON.stringify({ ollama_plan: plan }, null, 2)}\n`);
      renameSync(tmp, path);
    } catch {
      /* ponytail: best-effort memory; the session still runs on the supplied plan */
    }
  }

  function resolveOllamaPlan(supplied: unknown): OllamaPlan | null {
    if (supplied === '20' || supplied === '100') {
      writeOllamaPlan(supplied);
      return supplied;
    }
    if (supplied !== undefined && supplied !== null) {
      throw invalid('ollama_plan must be "20" or "100".');
    }
    return readOllamaPlan();
  }

  /**
   * The fallback route for an Ollama primary: the named model on the
   * OpenRouter route. Anything that cannot be resolved is reported as
   * "none (<reason>)" and the convene proceeds on the primary route.
   */
  async function resolveFallback(
    primary: ResolvedSessionRoute,
    fallbackModel: string | null,
    councilMode: boolean,
  ): Promise<{ snapshot: PinnedRouteSnapshot | null; line: string }> {
    if (!councilMode) return { snapshot: null, line: 'none (the older modes keep their existing route)' };
    if (!isOllamaProvider(primary.snapshot.providerSlug)) {
      return { snapshot: null, line: 'none (primary route is not Ollama)' };
    }
    if (fallbackModel === null || fallbackModel.trim() === '') {
      return { snapshot: null, line: 'none (no fallback model given)' };
    }
    try {
      const resolved = await deps.resolveRoute({ route_id: FALLBACK_ROUTE_ID, model: fallbackModel });
      return {
        snapshot: resolved.snapshot,
        line: `${resolved.snapshot.routeId} / ${resolved.model_label}`,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { snapshot: null, line: `none (${message})` };
    }
  }

  async function route(request: RouteChoiceRequest): Promise<ResolvedSessionRoute> {
    try {
      return await deps.resolveRoute(request);
    } catch (error) {
      const code = errorCode(error) as RouteChoiceErrorCode;
      if (code in ROUTE_STATUS) {
        const e = error as Error & { recovery?: string };
        throw new DriverRefusal(
          code,
          e.message,
          e.recovery ?? 'Choose a route from GET /api/council/routes and convene again.',
          ROUTE_STATUS[code],
          { summary: e.message },
        );
      }
      throw error;
    }
  }

  function buildSession(
    input: ConveneInput,
    sessionId: string,
    resolved: ResolvedSessionRoute,
  ): { session: StoredSession; selection: ModeSelection } {
    const now = deps.clock.nowUtc();
    const sample = input.sample === true;
    if (sample === (input.brief !== undefined)) {
      throw invalid(
        sample
          ? 'Send sample:true or a brief, not both.'
          : 'Nothing to convene: send sample:true or a decision brief.',
      );
    }
    let baseSpec: SessionSpec;
    let brief: DecisionBrief;
    if (sample) {
      const built = buildSampleSession();
      baseSpec = built.spec;
      brief = { ...built.brief, created_at: now };
    } else {
      brief = { ...input.brief! };
      baseSpec = {
        schema_version: 'wise-elders.session/v1',
        session_id: sessionId,
        mode: 'full',
        visibility: 'company',
        brief_revision: 1,
        brief_sha256: '',
        options: brief.options.map((o) => ({ ...o })),
        seat_ids: [...SEAT_IDS],
        model_policy: resolved.model_policy,
        source_pack_version: deps.sourcePackVersion ?? DEFAULT_PACK_VERSION,
        execution_policy: 'advisory_only',
        created_at: now,
        display_timezone: brief.display_timezone,
      };
    }
    brief = {
      ...brief,
      brief_id: `brief-${sessionId}`,
      session_id: sessionId,
      revision: 1,
    };
    // The sitting's mode. An explicit client mode wins verbatim; with none
    // the question decides (W77S auto-mode), and the response plus the audit
    // line say which happened and why. The built-in sample keeps the mode its
    // fixture carries when the client names none: it is a harmless demo, not
    // a client decision to size.
    const selection: ModeSelection =
      input.mode !== undefined
        ? resolveModeSelection(input.mode, '')
        : sample
          ? {
              mode: baseSpec.mode,
              source: 'auto',
              reason: `built-in sample keeps its fixture mode ${baseSpec.mode}`,
            }
          : resolveModeSelection(undefined, brief.question);
    const mode: SessionMode = selection.mode;
    // Every council size seats the full roster (Trevor decision
    // 2026-10-25): mode changes rounds and concurrency, never the panel.
    // A named panel still wins, so an explicit seat list is honoured.
    const seatIds: SeatId[] = input.seat_ids
      ? [...input.seat_ids]
      : [...baseSpec.seat_ids];
    // Every panel seat carries a weight: a seat missing from the brief's
    // relevance_weights blocks the sitting at DRAFT_RESOLUTION. A seat
    // that is NOT on the panel carries none: publication recomputes the
    // decision over every weighted seat, so a sitting that kept weights
    // for seats it does not seat scored the verdict over its own card set
    // but recomputed it over every weighted seat and failed its own
    // scores_recomputed check (W77S-MODES review).
    const panel = new Set<SeatId>(seatIds);
    const relevanceWeights: DecisionBrief['relevance_weights'] = {};
    for (const [seatId, weight] of Object.entries(brief.relevance_weights)) {
      if (panel.has(seatId as SeatId)) relevanceWeights[seatId as SeatId] = weight;
    }
    for (const seatId of seatIds) {
      if (relevanceWeights[seatId] === undefined) relevanceWeights[seatId] = 1;
    }
    brief = { ...brief, relevance_weights: relevanceWeights };
    const briefCheck = validateDecisionBrief(brief);
    if (!briefCheck.ok) {
      throw invalid('The decision brief failed validation.', { issues: briefCheck.issues });
    }
    const spec: SessionSpec = {
      ...baseSpec,
      session_id: sessionId,
      brief_revision: 1,
      brief_sha256: canonicalHash(brief),
      mode,
      visibility: input.visibility ?? baseSpec.visibility,
      seat_ids: seatIds,
      model_policy: resolved.model_policy,
      created_at: now,
    };
    const specCheck = validateSessionSpec(spec);
    if (!specCheck.ok) {
      throw invalid('The session settings failed validation.', { issues: specCheck.issues });
    }
    return {
      session: {
        spec,
        brief,
        scope: { ...deps.scope },
        state: {
          schema_version: 'wise-elders.session-state/v1',
          session_id: sessionId,
          mode: spec.mode,
          state: 'DRAFT',
          state_version: 0,
          brief_revision: 1,
          resume_phase: null,
          cancel_generation: 0,
          revocation_generation: 0,
          attempt: 1,
          lease_epoch: 0,
          archived: false,
          updated_at: now,
        },
        sample,
      },
      selection,
    };
  }

  /** A run that threw leaves its session mid-round; make that visible as BLOCKED. */
  function blockStranded(sessionId: string): void {
    try {
      const stored = deps.deliberation.repositories.getSession(deps.envelope, sessionId);
      if (stored && !['COMPLETED', 'BLOCKED', 'CANCELLED'].includes(stored.state.state)) {
        deps.deliberation.repositories.transitionState(
          deps.envelope,
          sessionId,
          'BLOCKED',
          stored.state.state_version,
        );
      }
    } catch {
      // best effort: the typed error still reaches onSettled
    }
  }

  async function convene(input: ConveneInput): Promise<ConveneAccepted> {
    const readiness = deps.deliberation.readiness();
    if (!readiness.ready) {
      const unbound = readiness.checks.filter((c) => !c.bound);
      throw new DriverRefusal(
        'COMPOSITION_NOT_READY',
        `The council is not ready to convene: ${unbound.map((c) => c.name).join(', ')} not bound.`,
        'Bind the missing services (see detail.checks), then convene again.',
        503,
        {
          unbound: unbound.map((c) => c.name),
          checks: unbound.map((c) => ({ name: c.name, detail: c.detail })),
        },
      );
    }
    if (typeof input.requested_by !== 'string' || input.requested_by.trim() === '') {
      throw invalid('requested_by is required.');
    }
    const resolved = await route(input.route ?? {});
    // CTR-134: one preparation pass, on the SAME route/model the caller's
    // convene resolved, before any session exists. A brief that names fewer
    // than two real alternatives cannot be scored honestly; the known
    // unresolved exploration candidate is never counted, never renamed, and
    // never scored. With a bound configured adapter the single request
    // proposes alternatives and the sitting proceeds on them, labelled as
    // proposals. Without one, the request is refused as input-needed.
    let sessionInput = input;
    let preparation: PreparationRecord | null = null;
    if (!input.sample && substantiveOptionCount(input.brief) < 2) {
      const token = input.brief;
      const question = typeof token?.question === 'string' ? token.question.trim() : '';
      if (token === undefined || question.length === 0) {
        throw invalid(
          'The brief carries fewer than two substantive alternatives and no question to prepare from.',
          { substantive_options: token === undefined ? 0 : substantiveOptionCount(token) },
        );
      }
      if (typeof deps.prepareInference !== 'function') {
        throw new DriverRefusal(
          'COUNCIL_PREPARATION_REQUIRED',
          'No configured inference adapter is bound, so real alternatives cannot be prepared and none is invented.',
          'Bind the service transport, then convene again; or state two to five real alternatives in the brief.',
          422,
          {
            preparation: {
              state: 'input-needed',
              question,
              request_budget: 0,
              requires_new_inference: false,
              missing: ['a configured inference adapter for the one preparation request'],
            },
          },
        );
      }
      // A preparation request must not be spent on a route the sitting could
      // not size (an Ollama route with no known plan). Check that gate FIRST;
      // it is the same selector the sitting below uses.
      const provisionalMode =
        input.mode !== undefined
          ? resolveModeSelection(input.mode, '').mode
          : resolveModeSelection(undefined, question).mode;
      if (isCouncilSize(provisionalMode)) {
        const plan = resolveOllamaPlan(input.ollama_plan);
        const parallel = parallelLimitFor({
          providerSlug: resolved.snapshot.providerSlug,
          ollamaPlan: plan,
          panelSize: (input.seat_ids ?? SEAT_IDS).length,
          waveWidth: MODE_ROUND_POLICY[provisionalMode].max_concurrent_calls,
        });
        if (!parallel.ok) {
          throw new DriverRefusal(
            'OLLAMA_PLAN_REQUIRED',
            'The client chooses their own Ollama, and its plan is not known yet, so the council cannot size how many advisors run at once.',
            OLLAMA_PLAN_ACTION,
            409,
          );
        }
      }
      const preparationSessionId = `prep-${deps.ids.newId()}`;
      let requestsUsed = 0;
      const infer = async (request: ProposalInferenceRequest) => {
        if (requestsUsed >= 1) {
          throw new Error(
            'The preparation stage is limited to ONE provider request; a second request was refused, not sent.',
          );
        }
        requestsUsed += 1;
        return deps.prepareInference!(resolved, request, { session_id: preparationSessionId });
      };
      const prepared = await prepareProposals(
        {
          question,
          permitted_context: preparationContext(token),
          display_timezone:
            typeof token.display_timezone === 'string' && token.display_timezone.trim().length > 0
              ? token.display_timezone
              : 'UTC',
          max_options: 5,
          request_budget: 1,
        },
        { infer, max_requests: 1 },
      );
      if (!prepared.ok) {
        throw new DriverRefusal(
          'COUNCIL_PREPARATION_REQUIRED',
          prepared.detail,
          'State two to five real alternatives in the brief, then convene again. No decision was scored and no alternative was invented.',
          422,
          {
            preparation: {
              state: prepared.state,
              question,
              request_budget: prepared.request_budget,
              request_count: prepared.request_count,
              requires_new_inference: false,
              missing: prepared.missing,
            },
          },
        );
      }
      sessionInput = {
        ...input,
        brief: withProposals(token, prepared.options, prepared.unknowns),
      };
      preparation = {
        state: 'prepared',
        request_budget: 1,
        request_count: 1,
        route_id: resolved.snapshot.routeId,
        model_label: resolved.model_label,
        alternatives_are_proposals: true,
      };
    }
    const sessionId = `sess-${deps.ids.newId()}`;
    const { session, selection } = buildSession(sessionInput, sessionId, resolved);
    const mode = session.spec.mode;
    const councilMode = isCouncilSize(mode);

    // The Ollama plan is remembered once, then reused. An Ollama route
    // with no known plan is a typed refusal, never a guess.
    const plan = resolveOllamaPlan(input.ollama_plan);
    let parallelLimit = 1;
    if (councilMode) {
      const parallel = parallelLimitFor({
        providerSlug: resolved.snapshot.providerSlug,
        ollamaPlan: plan,
        panelSize: session.spec.seat_ids.length,
        // The mode's wave width: light runs 3 at a time, medium/heavy the
        // whole roster (contracts/modes.ts).
        waveWidth: MODE_ROUND_POLICY[mode as CouncilSize].max_concurrent_calls,
      });
      if (!parallel.ok) {
        throw new DriverRefusal(
          'OLLAMA_PLAN_REQUIRED',
          'The client chooses their own Ollama, and its plan is not known yet, so the council cannot size how many advisors run at once.',
          OLLAMA_PLAN_ACTION,
          409,
        );
      }
      parallelLimit = parallel.limit;
    }
    const fallback = await resolveFallback(
      resolved,
      input.fallback_model ?? null,
      councilMode,
    );
    const ceilings = ceilingsForMode(mode);
    // The one preparation request already spent part of the caller's existing
    // cap; the sitting's grant keeps the SAME total ceiling by reserving that
    // one request here. No second cap, no money or token ceiling added.
    if (preparation !== null) {
      ceilings.max_provider_requests = Math.max(1, ceilings.max_provider_requests - 1);
    }

    const repos = deps.deliberation.repositories;
    repos.createSession(deps.envelope, session);
    if (input.fresh_facts?.length) deps.recordFreshFacts?.(sessionId, input.fresh_facts);

    const grants = deps.deliberation.grants;
    const preview = grants.previewRun(deps.envelope, {
      session_id: sessionId,
      purpose: 'council_run',
      route_snapshot: resolved.snapshot,
      route_policy_sha256: canonicalHash({ route_snapshot: resolved.snapshot }),
      ceilings,
    });
    const grant = grants.approveRun(deps.envelope, preview.preview_id, {
      principal: deps.principal,
      authority_mode: 'local_interactive_owner',
      interactive_confirmation: true,
      expected_session_id: sessionId,
    });
    // A fallback route needs its own approved grant: the grant's route
    // pin is a security invariant, so a grant approved on the primary
    // snapshot admits nothing on the fallback snapshot. Both grants carry
    // the same mode ceilings; the budget service counts reservations per
    // session, so the fallback never doubles the cap.
    let fallbackGrantId: string | undefined;
    if (fallback.snapshot !== null) {
      const fallbackPreview = grants.previewRun(deps.envelope, {
        session_id: sessionId,
        purpose: 'council_run',
        route_snapshot: fallback.snapshot,
        route_policy_sha256: canonicalHash({ route_snapshot: fallback.snapshot }),
        ceilings,
      });
      fallbackGrantId = grants.approveRun(deps.envelope, fallbackPreview.preview_id, {
        principal: deps.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
        expected_session_id: sessionId,
      }).grant_id;
    }

    mkdirSync(dirname(deps.auditLogPath), { recursive: true });
    appendFileSync(
      deps.auditLogPath,
      `${JSON.stringify({
        at: deps.clock.nowUtc(),
        session_id: sessionId,
        route_id: resolved.snapshot.routeId,
        model_label: resolved.model_label,
        selection_source: resolved.selection_source,
        harness: resolved.harness,
        grant_id: grant.grant_id,
        fallback_grant_id: fallbackGrantId ?? null,
        mode: selection.mode,
        mode_source: selection.source,
        mode_reason: selection.reason,
        requested_by: input.requested_by,
        approval_basis: APPROVAL_BASIS,
      })}\n`,
    );

    // Background run: never awaited by the caller. runSession and the
    // service's own workers share one store; the settle callback gets
    // the typed result (or a typed error code), never a swallowed one.
    const run = (async (): Promise<void> => {
      let settled: RunSessionResult | { status: 'error'; code: string };
      try {
        settled = await deps.deliberation.runSession(deps.envelope, sessionId, {
          grant_id: grant.grant_id,
          route_snapshot: resolved.snapshot,
          parallel_limit: parallelLimit,
          fallback_route_snapshot: fallback.snapshot,
          fallback_grant_id: fallbackGrantId,
        });
      } catch (error) {
        settled = { status: 'error', code: errorCode(error) };
        blockStranded(sessionId);
      }
      try {
        deps.onSettled?.(sessionId, settled);
      } catch {
        // an observer failure must not turn a finished run into an unhandled rejection
      }
    })();
    running.add(run);
    void run.finally(() => running.delete(run));

    return {
      session_id: sessionId,
      state: repos.getSession(deps.envelope, sessionId)?.state.state ?? session.state.state,
      sample: session.sample,
      route_id: resolved.snapshot.routeId,
      model_label: resolved.model_label,
      selection_source: resolved.selection_source,
      grant_id: grant.grant_id,
      session_path: `/council/${sessionId}`,
      events_path: `/api/council/sessions/${sessionId}/events`,
      mode,
      mode_selection: selection,
      seats: session.spec.seat_ids.length,
      rounds: councilMode ? roundsPolicyOf(mode as CouncilSize) : null,
      request_cap: ceilings.max_provider_requests,
      parallel_limit: parallelLimit,
      fallback: fallback.line,
      ...(preparation !== null ? { preparation } : {}),
    };
  }

  return {
    convene,
    inFlight: () => running.size,
    drain: async () => {
      while (running.size > 0) await Promise.allSettled([...running]);
    },
  };
}
