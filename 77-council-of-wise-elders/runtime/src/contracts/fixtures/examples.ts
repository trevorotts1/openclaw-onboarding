/**
 * Valid and invalid contract fixtures (CWE-003 build step 4).
 *
 * The valid fixtures exercise the frozen Section 11.2 session shape and the
 * Section 11.6 contract inventory. The invalid fixtures each break exactly
 * one named rule, so a validation failure is attributable to the intended
 * boundary (the Section 35 rule for negative tests).
 */

export const FIXTURE_HASH_A =
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
export const FIXTURE_HASH_B =
  'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

export const validSessionSpec = {
  schema_version: 'wise-elders.session/v1',
  session_id: 'sess-fixture-1',
  mode: 'full',
  visibility: 'company',
  brief_revision: 1,
  brief_sha256: FIXTURE_HASH_A,
  options: [
    { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
    { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
    { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' },
  ],
  seat_ids: [
    'simon-sinek',
    'td-jakes',
    'oprah-winfrey',
    'tiffany-aliche',
    'russell-brunson',
    'michelle-obama',
    'brene-brown',
    'dennis-kimbro',
    'les-brown',
  ],
  model_policy: {
    selection: 'explicit',
    route_id: 'route-fixture-1',
    requested_model_id: 'model-selected-by-client',
    reasoning_preference: null,
    fallback_policy: 'none',
  },
  source_pack_version: 'pack-fixture-1.0.0',
  execution_policy: 'advisory_only',
  created_at: '2026-10-14T02:00:00Z',
  display_timezone: 'America/New_York',
} as const;

export const validBrief = {
  schema_version: 'wise-elders.brief/v1',
  brief_id: 'brief-fixture-1',
  session_id: 'sess-fixture-1',
  revision: 1,
  question: 'Should we pilot the revised offer before a broad launch?',
  facts: [
    { id: 'fact-1', statement: 'Current offer converts at a measured baseline.', evidence_ids: ['ev-1'] },
  ],
  assumptions: [
    { id: 'asm-1', statement: 'Pilot capacity exists for one cohort.', evidence_ids: [] },
  ],
  unknowns: [
    { id: 'unk-1', statement: 'Pilot cohort retention is not yet measured.', evidence_ids: [] },
  ],
  constraints: [
    { id: 'con-1', description: 'Pilot spend must stay within the approved budget.', hard: true, applies_to_option_ids: ['B', 'C'] },
  ],
  options: [
    { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
    { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
    { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' },
  ],
  relevance_weights: {
    'simon-sinek': 2,
    'td-jakes': 3,
    'oprah-winfrey': 2,
    'tiffany-aliche': 3,
    'russell-brunson': 3,
    'michelle-obama': 2,
    'brene-brown': 3,
    'dennis-kimbro': 2,
    'les-brown': 2,
  },
  critical_domains: [
    {
      schema_version: 'wise-elders.critical-domain-requirement/v1',
      domain: 'financial_feasibility',
      status: 'unresolved',
      trigger_evidence_ids: ['ev-1'],
      trigger_field_paths: ['constraints.con-1'],
      required_seat_id: 'tiffany-aliche',
      required_checker: 'seat',
      unresolved_questions: ['Is the pilot affordable at committed cash levels?'],
      policy_version: 'critical-domains/v1',
    },
  ],
  evidence_manifest: [
    { evidence_id: 'ev-1', sha256: FIXTURE_HASH_B, source_kind: 'client_document', locator: 'doc:baseline-metrics' },
  ],
  private_preference_ref: null,
  created_at: '2026-10-14T02:00:00Z',
  display_timezone: 'America/New_York',
} as const;

export const validAdvisorCardAuthor = {
  schema_version: 'wise-elders.card/v1',
  card_kind: 'advisor',
  session_id: 'sess-fixture-1',
  brief_revision: 1,
  round: 1,
  seat_id: 'tiffany-aliche',
  input_manifest_sha256: FIXTURE_HASH_B,
  pack_version: 'pack-fixture-1.0.0',
  stance: 'conditional',
  preferred_option_id: 'B',
  option_scores: [
    { option_id: 'A', score: 5, rationale: 'Safe but leaves the pricing question open.', evidence_ids: ['ev-1'] },
    { option_id: 'B', score: 8, rationale: 'Bounded spend with measurable evidence.', evidence_ids: ['ev-1'] },
    { option_id: 'C', score: 6, rationale: 'Broad launch exceeds verified capacity.', evidence_ids: ['ev-1'] },
  ],
  framework_applications: [
    {
      framework_id: 'budget-baseline-check',
      source_evidence_ids: ['ev-1'],
      case_evidence_ids: [],
      application: 'Compared pilot spend against the measured baseline before endorsing launch.',
      attribution_kind: 'source_principle',
    },
  ],
  decisive_arguments: ['The pilot bounds the downside while producing the missing evidence.'],
  strongest_objection: 'Retention for the pilot cohort is unmeasured.',
  conditions: [],
  critical_unknowns: ['Pilot cohort retention'],
  change_my_mind: 'Evidence that committed cash cannot cover the pilot without missing obligations.',
  challenges_answered: [],
  quotes: [],
  evidence_strength: 'medium',
  minority_position: null,
} as const;

export const validHostStamp = {
  scope: {
    tenant_id: 'tenant-fixture',
    company_id: 'company-fixture',
    installation_id: 'install-fixture',
    owner_subject: null,
  },
  operation_id: 'op-fixture-1',
  route_id: 'route-fixture-1',
  session_id: 'sess-fixture-1',
  stamped_at: '2026-10-14T02:05:00Z',
  source_status: 'verified',
} as const;

/** Each invalid fixture breaks exactly one named rule. */
export const invalidFixtures = {
  /** Unknown session state value in a state record. */
  unknownState: {
    schema_version: 'wise-elders.session-state/v1',
    session_id: 'sess-fixture-1',
    mode: 'full',
    state: 'THINKING',
    state_version: 0,
    brief_revision: 1,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: '2026-10-14T02:00:00Z',
  },
  /** Duplicate option id inside one session spec. */
  duplicateOptions: {
    ...validSessionSpec,
    options: [
      { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
      { id: 'A', label: 'Duplicate of A', kind: 'change' },
    ],
  },
  /** Score above the 0..10 range. */
  scoreOutOfRange: {
    ...validAdvisorCardAuthor,
    option_scores: [
      { option_id: 'A', score: 11, rationale: 'Out of range on purpose.', evidence_ids: [] },
      { option_id: 'B', score: 8, rationale: 'In range.', evidence_ids: [] },
      { option_id: 'C', score: 6, rationale: 'In range.', evidence_ids: [] },
    ],
  },
  /** Author payload trying to assign its own tenant (host-only field). */
  authorAssignsTenant: {
    ...validAdvisorCardAuthor,
    tenant_id: 'tenant-forged',
  },
  /** Unknown enum value for mode. */
  unknownMode: {
    ...validSessionSpec,
    mode: 'turbo',
  },
  /** Card whose preferred option does not exist in the brief. */
  invalidPreferredOption: {
    ...validAdvisorCardAuthor,
    preferred_option_id: 'Z',
  },
  /** Card scoring an option that is not in the brief. */
  invalidScoredOption: {
    ...validAdvisorCardAuthor,
    option_scores: [
      { option_id: 'A', score: 5, rationale: 'In the brief.', evidence_ids: [] },
      { option_id: 'B', score: 8, rationale: 'In the brief.', evidence_ids: [] },
      { option_id: 'Z', score: 6, rationale: 'Not in the brief.', evidence_ids: [] },
    ],
  },
  /** Card citing evidence outside the frozen manifest. */
  invalidEvidenceReference: {
    ...validAdvisorCardAuthor,
    option_scores: [
      { option_id: 'A', score: 5, rationale: 'Cites missing evidence.', evidence_ids: ['ev-missing'] },
      { option_id: 'B', score: 8, rationale: 'In range.', evidence_ids: [] },
      { option_id: 'C', score: 6, rationale: 'In range.', evidence_ids: [] },
    ],
  },
} as const;
