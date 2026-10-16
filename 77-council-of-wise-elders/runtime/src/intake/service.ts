/**
 * CWE-023 IntakeService: guided intake, brief revisions, freeze,
 * preference storage, and amendment queueing (directive Sections 9,
 * 10, 11).
 *
 * Write discipline:
 * - Every mutation takes the caller's expected intake revision. A
 *   stale writer gets INTAKE_REVISION_CONFLICT and nothing is
 *   overwritten. The same discipline the CWE-006 store enforces on
 *   brief revisions, applied at the intake boundary (Section 17.1's
 *   expected-revision rule).
 * - Brief-affecting answers immediately compose and save the next
 *   immutable brief revision (revisioned draft autosave, Section 34
 *   CWE-023 step 3). A saved revision is never edited; the next
 *   answer creates the next revision.
 * - Freeze is the only path into the canonical CWE-006 store: it
 *   writes the session with its frozen spec and the frozen brief
 *   revision, and records the freeze record. After freeze every
 *   content mutation refuses with INTAKE_FROZEN.
 * - Amendments after freeze are queued records against the frozen
 *   revision. Applying one means a new revision in a child session;
 *   that rerun composition belongs to CWE-050, not this unit.
 */
import {
  evidenceManifestEntrySchema,
  type Clock,
  type DecisionBrief,
  type DecisionOption,
  type EvidenceManifestEntry,
  type IdSource,
  type ScopeFields,
  type SeatId,
  type SessionMode,
  type SessionSpec,
  type SessionStateRecord,
  type SessionVisibility,
  type TypedFact,
} from '../contracts/index.js';
import { briefContentHash, composeBrief, evidenceManifestHash } from './brief.js';
import { classifyIntakeDomains } from './classify.js';
import { assessPanel, validatePanel, type PanelAssessment } from './panel.js';
import {
  currentQuestion,
  missingMaterialQuestions,
  questionById,
  type IntakeQuestion,
  type IntakeQuestionId,
} from './questions.js';
import {
  modelPolicyFromSnapshot,
  resolveRouteSnapshot,
  type RouteCatalogPort,
} from './routes.js';
import type { FreezeResult, IntakeReviewSummary } from './service-types.js';
import type { IntakeBriefStore, IntakeWorkingStore } from './stores.js';
import {
  EMPTY_ANSWERS,
  INTAKE_SCHEMA_VERSION,
  IntakeError,
  type ClientPreferencePrivate,
  type DecisionFlags,
  type IntakeAnswers,
  type IntakeConstraint,
  type IntakeDraft,
  type IntakeFact,
  type ProposedAmendment,
  type RouteChoice,
  type SuccessAnswer,
} from './types.js';

export interface IntakeServiceDeps {
  readonly briefStore: IntakeBriefStore;
  readonly workingStore: IntakeWorkingStore;
  readonly routeCatalog: RouteCatalogPort;
  readonly clock: Clock;
  readonly ids: IdSource;
}

export interface BeginIntakeInput {
  readonly scope: ScopeFields;
  readonly visibility: SessionVisibility;
  readonly display_timezone: string;
  readonly source_pack_version: string;
  /**
   * Confirmed facts supplied through authorized CWE-022 retrieval,
   * each carrying the scope it was retrieved under. Facts whose scope
   * does not match this intake are excluded silently (count only);
   * intake never pulls out-of-scope facts into a brief.
   */
  readonly known_facts?: readonly (IntakeFact & { readonly scope: ScopeFields })[];
}

export type IntakeAnswerValue =
  | { readonly question_id: 'decision'; readonly statement: string; readonly flags: DecisionFlags }
  | { readonly question_id: 'options'; readonly options: readonly DecisionOption[] }
  | { readonly question_id: 'success'; readonly success: SuccessAnswer }
  | { readonly question_id: 'constraints'; readonly constraints: readonly IntakeConstraint[] }
  | { readonly question_id: 'constraints'; readonly explicit_unknown: true }
  | { readonly question_id: 'facts'; readonly facts: readonly IntakeFact[] }
  | { readonly question_id: 'facts'; readonly explicit_unknown: true }
  | { readonly question_id: 'unknowns'; readonly unknowns: readonly TypedFact[] }
  | { readonly question_id: 'assumptions'; readonly assumptions: readonly TypedFact[] }
  | { readonly question_id: 'stakeholders'; readonly stakeholders: readonly string[] };

export class IntakeService {
  constructor(private readonly deps: IntakeServiceDeps) {}

  // ------------------------------------------------------------ lifecycle

  async begin(input: BeginIntakeInput): Promise<IntakeDraft> {
    const now = this.deps.clock.nowUtc();
    const knownFacts: IntakeFact[] = [];
    let dropped = 0;
    for (const fact of input.known_facts ?? []) {
      const sameScope =
        fact.scope.tenant_id === input.scope.tenant_id &&
        fact.scope.company_id === input.scope.company_id &&
        fact.scope.installation_id === input.scope.installation_id;
      if (!sameScope) {
        dropped += 1;
        continue;
      }
      const { scope: _scope, ...rest } = fact;
      knownFacts.push(rest);
    }
    const draft: IntakeDraft = {
      schema_version: INTAKE_SCHEMA_VERSION,
      intake_id: this.deps.ids.newId(),
      session_id: this.deps.ids.newId(),
      brief_id: this.deps.ids.newId(),
      scope: input.scope,
      visibility: input.visibility,
      display_timezone: input.display_timezone,
      source_pack_version: input.source_pack_version,
      status: 'in_progress',
      intake_revision: 1,
      current_brief_revision: 0,
      answers: EMPTY_ANSWERS,
      known_facts: knownFacts,
      dropped_known_fact_count: dropped,
      evidence_manifest: [],
      mode: null,
      panel_seat_ids: null,
      professional_review_arranged: null,
      route_choice: null,
      route_snapshot: null,
      brief_dirty: true,
      constraints_explicit_unknown: false,
      facts_explicit_unknown: false,
      preference_ref: null,
      answered_question_ids: [],
      skipped_question_ids: [],
      created_at: now,
      updated_at: now,
    };
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async resume(intakeId: string): Promise<{
    draft: IntakeDraft;
    current_question: IntakeQuestion | null;
  }> {
    const draft = await this.loadDraft(intakeId);
    return { draft, current_question: currentQuestion(draft) };
  }

  async getDraft(intakeId: string): Promise<IntakeDraft> {
    return this.loadDraft(intakeId);
  }

  // ------------------------------------------------------------ answers

  async answer(
    intakeId: string,
    value: IntakeAnswerValue,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    const question = questionById(value.question_id);
    if (!question) {
      throw new IntakeError('INTAKE_QUESTION_UNKNOWN', `Unknown intake question ${value.question_id}.`);
    }
    draft = this.applyAnswer(draft, value);
    draft = await this.syncBriefRevision(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async skipQuestion(
    intakeId: string,
    questionId: IntakeQuestionId,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    const question = questionById(questionId);
    if (!question) {
      throw new IntakeError('INTAKE_QUESTION_UNKNOWN', `Unknown intake question ${questionId}.`);
    }
    if (question.material) {
      throw new IntakeError(
        'INTAKE_ANSWER_INVALID',
        `Question ${questionId} is material and cannot be skipped; answer it or state an explicit unknown where allowed.`,
      );
    }
    if (!draft.skipped_question_ids.includes(questionId)) {
      draft = {
        ...draft,
        skipped_question_ids: [...draft.skipped_question_ids, questionId],
      };
    }
    draft = this.touch(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  // ------------------------------------------------------------ preference

  /**
   * Store (or clear) the client's private preference. The value lives
   * only in its own record; the draft keeps the opaque reference the
   * brief will carry. Clearing removes the record and the reference.
   */
  async setPreference(
    intakeId: string,
    preference: { leaning_option_id: string | null; statement: string | null } | null,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    if (preference === null) {
      if (draft.preference_ref !== null) {
        await this.deps.workingStore.deletePreference(draft.preference_ref);
      }
      draft = { ...draft, preference_ref: null, brief_dirty: true };
    } else {
      if (
        preference.leaning_option_id !== null &&
        draft.answers.options !== null &&
        !draft.answers.options.some((o) => o.id === preference.leaning_option_id)
      ) {
        throw new IntakeError(
          'INTAKE_ANSWER_INVALID',
          'The preference leans toward an option that is not one of the brief options.',
          { leaning_option_id: preference.leaning_option_id },
        );
      }
      const preferenceId = draft.preference_ref ?? this.deps.ids.newId();
      const record: ClientPreferencePrivate = {
        schema_version: INTAKE_SCHEMA_VERSION,
        preference_id: preferenceId,
        session_id: draft.session_id,
        leaning_option_id: preference.leaning_option_id,
        statement: preference.statement,
        updated_at: this.deps.clock.nowUtc(),
      };
      await this.deps.workingStore.savePreference(record);
      draft = { ...draft, preference_ref: preferenceId, brief_dirty: true };
    }
    draft = await this.syncBriefRevision(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async getPreference(preferenceId: string): Promise<ClientPreferencePrivate | null> {
    return this.deps.workingStore.loadPreference(preferenceId);
  }

  // ------------------------------------------------------------ panel/route

  async chooseModePanel(
    intakeId: string,
    mode: SessionMode,
    seatIds: readonly SeatId[],
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    validatePanel(mode, seatIds);
    draft = { ...draft, mode, panel_seat_ids: [...seatIds], brief_dirty: true };
    draft = await this.syncBriefRevision(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async setProfessionalReviewArranged(
    intakeId: string,
    arranged: boolean,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    draft = { ...draft, professional_review_arranged: arranged, brief_dirty: true };
    draft = await this.syncBriefRevision(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async chooseRoute(
    intakeId: string,
    choice: RouteChoice,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    const snapshot = resolveRouteSnapshot(
      this.deps.routeCatalog,
      choice,
      this.deps.clock.nowUtc(),
    );
    draft = { ...draft, route_choice: choice, route_snapshot: snapshot };
    draft = this.touch(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  async setEvidenceManifest(
    intakeId: string,
    entries: readonly EvidenceManifestEntry[],
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    for (const entry of entries) {
      const parsed = evidenceManifestEntrySchema.safeParse(entry);
      if (!parsed.success) {
        throw new IntakeError('INTAKE_ANSWER_INVALID', 'An evidence manifest entry failed contract validation.', {
          issues: parsed.error.issues.map((i) => i.message),
        });
      }
    }
    draft = { ...draft, evidence_manifest: entries.map((e) => ({ ...e })) };
    draft = await this.syncBriefRevision(draft);
    await this.deps.workingStore.saveDraft(draft);
    return draft;
  }

  // ------------------------------------------------------------ review/freeze

  /** The pre-start review summary (Section 9.4). Pure read. */
  async reviewSummary(intakeId: string): Promise<IntakeReviewSummary> {
    const draft = await this.loadDraft(intakeId);
    let briefPreview: DecisionBrief | null = null;
    if (draft.answers.decision !== null && draft.answers.options !== null) {
      briefPreview = composeBrief({
        draft,
        revision: draft.current_brief_revision + 1,
        createdAt: draft.updated_at,
      });
    }
    let panelAssessment: PanelAssessment | null = null;
    if (draft.mode !== null && draft.panel_seat_ids !== null) {
      panelAssessment = assessPanel({
        mode: draft.mode,
        seatIds: draft.panel_seat_ids,
        requirements: classifyIntakeDomains({
          draft,
          panelSeatIds: draft.panel_seat_ids,
          professionalReviewArranged: draft.professional_review_arranged,
        }),
        professionalReviewArranged: draft.professional_review_arranged,
      });
    }
    const missing = missingMaterialQuestions(draft);
    return {
      session_id: draft.session_id,
      status: draft.status,
      brief_preview: briefPreview,
      panel_assessment: panelAssessment,
      route_snapshot: draft.route_snapshot,
      evidence_manifest_count: draft.evidence_manifest.length,
      missing_material_questions: missing,
      ready_to_freeze: missing.length === 0 && draft.status === 'in_progress',
    };
  }

  /**
   * Freeze the brief revision and evidence manifest for run start.
   * Writes the canonical session into the CWE-006 store and records
   * the freeze. After this, content edits refuse with INTAKE_FROZEN.
   */
  async freeze(intakeId: string, expectedIntakeRevision: number): Promise<FreezeResult> {
    let draft = await this.loadMutableDraft(intakeId, expectedIntakeRevision);
    const missing = missingMaterialQuestions(draft);
    if (missing.length > 0) {
      throw new IntakeError('INTAKE_NOT_READY', 'Material intake questions are still unanswered.', {
        missing_material_questions: missing,
      });
    }
    if (draft.mode === null || draft.panel_seat_ids === null || draft.route_snapshot === null) {
      throw new IntakeError('INTAKE_NOT_READY', 'Mode, panel, and route must be chosen before freeze.');
    }
    const mode = draft.mode;
    const panelSeatIds = draft.panel_seat_ids;
    const routeSnapshot = draft.route_snapshot;
    // Compose the frozen revision: reuse the latest draft revision
    // when nothing brief-affecting changed since it was composed.
    if (draft.brief_dirty || draft.current_brief_revision === 0) {
      draft = await this.syncBriefRevision(draft);
    }
    const brief = await this.deps.workingStore.loadDraftBriefRevision(
      draft.session_id,
      draft.current_brief_revision,
    );
    if (brief === null) {
      throw new IntakeError('INTAKE_NOT_READY', 'No composed brief revision exists to freeze.');
    }
    const frozenAt = this.deps.clock.nowUtc();
    const briefSha = briefContentHash(brief);
    const requirements = classifyIntakeDomains({
      draft,
      panelSeatIds,
      professionalReviewArranged: draft.professional_review_arranged,
    });
    const panelAssessment = assessPanel({
      mode,
      seatIds: panelSeatIds,
      requirements,
      professionalReviewArranged: draft.professional_review_arranged,
    });
    const spec: SessionSpec = {
      schema_version: 'wise-elders.session/v1',
      session_id: draft.session_id,
      mode,
      visibility: draft.visibility,
      brief_revision: brief.revision,
      brief_sha256: briefSha,
      options: brief.options.map((o) => ({ ...o })),
      seat_ids: [...panelSeatIds],
      model_policy: modelPolicyFromSnapshot(routeSnapshot),
      source_pack_version: draft.source_pack_version,
      execution_policy: 'advisory_only',
      created_at: frozenAt,
      display_timezone: draft.display_timezone,
    };
    const existing = await this.deps.briefStore.getSession(draft.session_id);
    if (existing === null) {
      const state: SessionStateRecord = {
        schema_version: 'wise-elders.session-state/v1',
        session_id: draft.session_id,
        mode,
        state: 'READY',
        state_version: 0,
        brief_revision: brief.revision,
        resume_phase: null,
        cancel_generation: 0,
        revocation_generation: 0,
        attempt: 1,
        lease_epoch: 0,
        archived: false,
        updated_at: frozenAt,
      };
      await this.deps.briefStore.createSession({
        spec,
        brief,
        scope: draft.scope,
        state,
        sample: false,
      });
    } else {
      await this.deps.briefStore.saveBriefRevision(brief);
    }
    const freezeRecord = {
      schema_version: INTAKE_SCHEMA_VERSION,
      session_id: draft.session_id,
      brief_revision: brief.revision,
      brief_sha256: briefSha,
      evidence_manifest_sha256: evidenceManifestHash(brief),
      route_snapshot: routeSnapshot,
      panel_assessment: panelAssessment,
      frozen_at: frozenAt,
    } as const;
    await this.deps.workingStore.saveFreezeRecord(freezeRecord);
    draft = { ...draft, status: 'frozen' };
    draft = this.touch(draft);
    await this.deps.workingStore.saveDraft(draft);
    return { brief, spec, freeze_record: freezeRecord };
  }

  // ------------------------------------------------------------ amendments

  /**
   * Queue new factual input received during a round. The frozen brief
   * is never touched; the proposal is recorded against the frozen
   * revision and applies only to a new revision (child session,
   * CWE-050).
   */
  async proposeAmendment(
    sessionId: string,
    input: { statement: string; evidence_ids?: readonly string[] },
  ): Promise<ProposedAmendment> {
    const draft = await this.deps.workingStore.loadDraftBySession(sessionId);
    if (draft === null) {
      throw new IntakeError('INTAKE_NOT_FOUND', 'No intake exists for this session.');
    }
    if (draft.status !== 'frozen') {
      throw new IntakeError(
        'INTAKE_NOT_FROZEN',
        'Amendments queue against a frozen brief; this intake has not frozen yet. Edit the draft instead.',
      );
    }
    const freezeRecord = await this.deps.workingStore.loadFreezeRecord(sessionId);
    if (freezeRecord === null) {
      throw new IntakeError('INTAKE_NOT_FROZEN', 'No freeze record exists for this session.');
    }
    const amendment: ProposedAmendment = {
      schema_version: INTAKE_SCHEMA_VERSION,
      amendment_id: this.deps.ids.newId(),
      session_id: sessionId,
      base_revision: freezeRecord.brief_revision,
      statement: input.statement,
      evidence_ids: [...(input.evidence_ids ?? [])],
      status: 'proposed',
      recorded_at: this.deps.clock.nowUtc(),
    };
    await this.deps.workingStore.saveAmendment(amendment);
    return amendment;
  }

  async listAmendments(sessionId: string): Promise<ProposedAmendment[]> {
    return this.deps.workingStore.listAmendments(sessionId);
  }

  // ------------------------------------------------------------ internals

  private async loadDraft(intakeId: string): Promise<IntakeDraft> {
    const draft = await this.deps.workingStore.loadDraft(intakeId);
    if (draft === null) {
      throw new IntakeError('INTAKE_NOT_FOUND', 'No intake exists with this ID.');
    }
    return draft;
  }

  private async loadMutableDraft(
    intakeId: string,
    expectedIntakeRevision: number,
  ): Promise<IntakeDraft> {
    const draft = await this.loadDraft(intakeId);
    if (draft.status === 'frozen') {
      throw new IntakeError(
        'INTAKE_FROZEN',
        'This brief is frozen for a run. New factual input is queued as a proposed amendment, never applied to the frozen revision.',
      );
    }
    if (draft.intake_revision !== expectedIntakeRevision) {
      throw new IntakeError(
        'INTAKE_REVISION_CONFLICT',
        'The intake changed underneath this writer. Reload the current intake revision and retry; nothing was overwritten.',
        { expected: expectedIntakeRevision, current: draft.intake_revision },
      );
    }
    return draft;
  }

  private touch(draft: IntakeDraft): IntakeDraft {
    return {
      ...draft,
      intake_revision: draft.intake_revision + 1,
      updated_at: this.deps.clock.nowUtc(),
    };
  }

  private markAnswered(draft: IntakeDraft, questionId: IntakeQuestionId): IntakeDraft {
    if (draft.answered_question_ids.includes(questionId)) return draft;
    return {
      ...draft,
      answered_question_ids: [...draft.answered_question_ids, questionId],
      skipped_question_ids: draft.skipped_question_ids.filter((id) => id !== questionId),
    };
  }

  private applyAnswer(draft: IntakeDraft, value: IntakeAnswerValue): IntakeDraft {
    const answers: { -readonly [K in keyof IntakeAnswers]: IntakeAnswers[K] } = {
      ...draft.answers,
    };
    let next: IntakeDraft = draft;
    switch (value.question_id) {
      case 'decision':
        answers.decision = { statement: value.statement, flags: value.flags };
        break;
      case 'options': {
        if (value.options.length < 2 || value.options.length > 5) {
          throw new IntakeError(
            'INTAKE_ANSWER_INVALID',
            'Scored modes need two to five explicit options (Section 9.1).',
          );
        }
        const seen = new Set<string>();
        for (const option of value.options) {
          if (seen.has(option.id)) {
            throw new IntakeError('INTAKE_ANSWER_INVALID', `Duplicate option id ${option.id}.`);
          }
          seen.add(option.id);
        }
        answers.options = value.options.map((o) => ({ ...o }));
        break;
      }
      case 'success':
        answers.success = value.success;
        break;
      case 'constraints':
        if ('explicit_unknown' in value) {
          answers.constraints = [];
          next = { ...next, constraints_explicit_unknown: true };
        } else {
          answers.constraints = value.constraints.map((c) => ({
            ...c,
            applies_to_option_ids: [...c.applies_to_option_ids],
          }));
          next = { ...next, constraints_explicit_unknown: false };
        }
        break;
      case 'facts':
        if ('explicit_unknown' in value) {
          answers.facts = [];
          next = { ...next, facts_explicit_unknown: true };
        } else {
          answers.facts = value.facts.map((f) => ({ ...f, evidence_ids: [...f.evidence_ids] }));
          next = { ...next, facts_explicit_unknown: false };
        }
        break;
      case 'unknowns':
        answers.unknowns = value.unknowns.map((u) => ({ ...u, evidence_ids: [...u.evidence_ids] }));
        break;
      case 'assumptions':
        answers.assumptions = value.assumptions.map((u) => ({ ...u, evidence_ids: [...u.evidence_ids] }));
        break;
      case 'stakeholders':
        answers.stakeholders = [...value.stakeholders];
        break;
    }
    next = { ...next, answers, brief_dirty: true };
    next = this.markAnswered(next, value.question_id);
    return this.touch(next);
  }

  /**
   * Compose and save the next immutable brief revision when the draft
   * is composable (decision and options answered). Called after every
   * brief-affecting mutation; the composed revision records the
   * intake revision it was composed at, which is what lets freeze
   * reuse it byte-for-byte when nothing changed since.
   */
  private async syncBriefRevision(draft: IntakeDraft): Promise<IntakeDraft> {
    if (draft.answers.decision === null || draft.answers.options === null) {
      return draft;
    }
    const revision = draft.current_brief_revision + 1;
    const brief = composeBrief({
      draft,
      revision,
      createdAt: this.deps.clock.nowUtc(),
    });
    await this.deps.workingStore.saveDraftBriefRevision(brief);
    return {
      ...draft,
      current_brief_revision: revision,
      brief_dirty: false,
    };
  }
}
