/**
 * AUTO-MODE-1062 — automatic deliberation-mode selection.
 *
 * Trevor's binding rule (2026-10-25): EVERY mode seats the whole council —
 * all nine advisors deliberate in every mode. Mode changes only rounds and
 * concurrency: light 2 rounds / max 3 provider calls in parallel (waves of
 * 3) / cap 50 total requests; medium up to 4 rounds / cap 50; heavy up to
 * 10 rounds / cap 100. The 7-of-9 consensus minimum is unchanged. So this
 * selector chooses WORK DEPTH for the question, never the number of seats.
 *
 * An explicit client mode always wins (source = 'client'): every canonical
 * SESSION_MODES value is mapped to a council size, so an explicit quick or
 * consult is honoured rather than re-classified.
 * Otherwise the complexity of the question decides — deterministically:
 * no randomness, no clock, no model call at runtime. Same question in,
 * same mode out.
 *
 * SCORING TABLE (fixed weights, fixed caps, fixed thresholds)
 * ---------------------------------------------------------------------
 *  bucket      signal                                points   cap
 *  stakes      distinct high-impact term               +4      16
 *  breadth     distinct domain named                   +2       8
 *  breadth     distinct sub-question (? ! ; . )        +1       4
 *  ambiguity   distinct hedge / choice marker          +1       3
 *  ambiguity   distinct list connector (and/or/…)      +1       2
 *  ambiguity   question longer than 60 words           +2       4
 *              question longer than 150 words          +4       4  (replaces +2)
 *
 *  total score   0 .. 4   -> light
 *  total score   5 .. 13  -> medium
 *  total score  >= 14     -> heavy
 *
 * Terms match across inflection (lawsuit/lawsuits, sue/suing/sued). A stake
 * term preceded within a short window by no / not / without / zero / never is
 * treated as absent, so "we have no legal risk" does not read as high stakes.
 * ---------------------------------------------------------------------
 */
import { SESSION_MODES, type SessionMode } from '../contracts/enums.js';

export type CouncilMode = 'light' | 'medium' | 'heavy';
export type ModeSource = 'client' | 'auto';

export interface ModeSelection {
  readonly mode: CouncilMode;
  readonly source: ModeSource;
  readonly reason: string;
}

/**
 * Every canonical session mode mapped to the council size it deliberates at.
 *
 * SESSION_MODES (contracts/enums) has seven values and `convene --mode`
 * accepts all of them, so none may fall through to auto-classification.
 * light/medium/heavy pass through unchanged; the four legacy modes keep their
 * own session behaviour and deliberate at the size shown here. Typed as a
 * complete Record so adding a canonical mode without a mapping is a compile
 * error, and a runtime test iterates SESSION_MODES to catch drift.
 */
const SESSION_MODE_SIZES: Readonly<Record<SessionMode, CouncilMode>> = {
  full: 'heavy',
  selected: 'medium',
  quick: 'light',
  consult: 'light',
  light: 'light',
  medium: 'medium',
  heavy: 'heavy',
};

export const MODE_SCORE_THRESHOLDS = { lightMax: 4, heavyMin: 14 } as const;

const STAKE_POINTS = 4;
const STAKE_CAP = 16;
const DOMAIN_POINTS = 2;
const DOMAIN_CAP = 8;
const SUBQUESTION_POINTS = 1;
const SUBQUESTION_CAP = 4;
const MARKER_POINTS = 1;
const MARKER_CAP = 3;
const CONNECTOR_POINTS = 1;
const CONNECTOR_CAP = 2;

/** High-impact terms: irreversible, expensive, or safety/legal bearing. */
const STAKE_TERMS = [
  'lawsuit', 'litigation', 'sue', 'sued', 'legal', 'liability', 'regulator',
  'regulators', 'regulatory', 'compliance', 'contract', 'terminate',
  'termination', 'fire', 'fired', 'layoff', 'lay off', 'hire', 'hiring',
  'acquisition', 'acquire', 'merger', 'merge', 'investor', 'investment',
  'valuation', 'debt', 'loan', 'bankruptcy', 'insolvent', 'shutdown',
  'shut down', 'closure', 'resign', 'resignation', 'divorce', 'custody',
  'health', 'medical', 'diagnosis', 'surgery', 'injury', 'death', 'safety',
  'security', 'breach', 'fraud', 'tax', 'audit', 'retirement', 'mortgage',
  'relocation', 'recall', 'patent', 'trademark', 'severance', 'equity',
  'fundraise', 'runway', 'penalty', 'fine', 'privacy',
] as const;

/** Domain groups: how many distinct subject areas the question names. */
const DOMAIN_GROUPS: readonly (readonly string[])[] = [
  ['revenue', 'pricing', 'price', 'budget', 'cash', 'profit', 'margin', 'cost', 'costs', 'forecast', 'payroll'],
  ['contract', 'lawsuit', 'legal', 'compliance', 'regulator', 'regulators', 'regulatory', 'terms', 'liability'],
  ['hiring', 'hire', 'layoff', 'lay off', 'headcount', 'recruiter', 'performance', 'promotion', 'severance', 'culture'],
  ['roadmap', 'feature', 'features', 'product', 'release', 'launch', 'redesign'],
  ['architecture', 'migration', 'migrate', 'outage', 'infrastructure', 'deployment', 'database', 'code', 'uptime'],
  ['security', 'breach', 'privacy', 'data', 'encryption', 'incident'],
  ['brand', 'campaign', 'marketing', 'newsletter', 'audience', 'social'],
  ['customers', 'customer', 'churn', 'retention', 'sales', 'pipeline'],
  ['vendor', 'supplier', 'procurement', 'outsourcing'],
  ['lease', 'property', 'office'],
  ['health', 'medical', 'diagnosis', 'treatment', 'therapy'],
  ['family', 'spouse', 'children', 'kids', 'custody', 'divorce'],
  ['school', 'degree', 'course', 'certification', 'training'],
];

/** Hedge / choice markers: the question itself admits it is unsettled. */
const AMBIGUITY_MARKERS = [
  'should i', 'should we', 'which', 'whether', 'option', 'options', 'unclear',
  'unsure', 'not sure', 'don\'t know', 'do not know', 'torn', 'confused',
  'help me', 'what if', 'thinking about', 'considering', 'choosing between',
  'tradeoff', 'trade-off', 'pros and cons',
] as const;

/** List connectors: alternatives or extra parts enumerated in one question. */
const LIST_CONNECTORS = ['and', 'or', 'versus', 'vs', 'plus', 'also', 'both', 'either'] as const;

function escapeToken(token: string): string {
  return token.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
}

function phrase(token: string): RegExp {
  return new RegExp(`\\b${escapeToken(token)}\\b`, 'u');
}

/**
 * Word forms a bare \b...\b match misses: plurals, past tense and gerunds.
 * sue -> sues / sued / suing, merger -> mergers, loan -> loans, tax -> taxes.
 */
function inflections(term: string): string[] {
  const forms = new Set<string>([term, `${term}s`, `${term}es`, `${term}ed`, `${term}ing`]);
  if (term.endsWith('e')) {
    const stem = term.slice(0, -1);
    forms.add(`${stem}ing`); // sue -> suing, hire -> hiring
    forms.add(`${stem}ed`); // sue -> sued
  }
  if (term.endsWith('y')) {
    const stem = term.slice(0, -1);
    forms.add(`${stem}ies`);
    forms.add(`${stem}ied`);
  }
  return [...forms];
}

function inflectedPhrase(term: string, flags = 'u'): RegExp {
  const alternatives = inflections(term)
    .sort((left, right) => right.length - left.length)
    .map(escapeToken)
    .join('|');
  return new RegExp(`\\b(?:${alternatives})\\b`, flags);
}

const STAKE_PATTERNS = STAKE_TERMS.map((term) => inflectedPhrase(term, 'gu'));
const DOMAIN_PATTERNS = DOMAIN_GROUPS.map((group) => group.map((term) => inflectedPhrase(term)));
const MARKER_PATTERNS = AMBIGUITY_MARKERS.map(phrase);
const CONNECTOR_PATTERNS = LIST_CONNECTORS.map(phrase);

/**
 * Negation cues that cancel a stake term shortly after them.
 * ponytail: fixed four-word window inside one clause, not a parser — it can
 * over-cancel on "no legal risk but a big contract dispute". Upgrade to
 * clause-scoped negation attribution if false negatives show up in real use.
 */
const NEGATORS: ReadonlySet<string> = new Set(['no', 'not', 'without', 'zero', 'never']);
const NEGATION_WINDOW_WORDS = 4;
const CLAUSE_BREAKS = /[.,;!?]/u;

function negatedBefore(text: string, matchIndex: number): boolean {
  const before = text.slice(0, matchIndex);
  let clauseStart = 0;
  for (let cursor = before.length - 1; cursor >= 0; cursor -= 1) {
    if (CLAUSE_BREAKS.test(before[cursor] as string)) {
      clauseStart = cursor + 1;
      break;
    }
  }
  const window = before
    .slice(clauseStart)
    .split(/\s+/u)
    .filter(Boolean)
    .slice(-NEGATION_WINDOW_WORDS);
  return window.some((word) => NEGATORS.has(word.replace(/[^a-z]/gu, '')));
}

/** True when at least one occurrence of `pattern` is not negated. */
function hasUnnegatedHit(pattern: RegExp, text: string): boolean {
  const scan = new RegExp(pattern.source, 'gu');
  for (const match of text.matchAll(scan)) {
    if (!negatedBefore(text, match.index ?? 0)) return true;
  }
  return false;
}

function countHits(patterns: readonly RegExp[], text: string, cap: number): number {
  let hits = 0;
  for (const pattern of patterns) {
    if (pattern.test(text)) hits += 1;
    if (hits >= cap) return cap;
  }
  return hits;
}

function countStakes(text: string): number {
  const cap = STAKE_CAP / STAKE_POINTS;
  let hits = 0;
  for (const pattern of STAKE_PATTERNS) {
    if (hasUnnegatedHit(pattern, text)) hits += 1;
    if (hits >= cap) return cap;
  }
  return hits;
}

interface ComplexityScore {
  readonly score: number;
  readonly stakes: number;
  readonly breadth: number;
  readonly ambiguity: number;
}

function scoreComplexity(question: string): ComplexityScore {
  const text = question.toLowerCase();

  const stakes = countStakes(text) * STAKE_POINTS;

  const domains = DOMAIN_PATTERNS.filter((group) => group.some((pattern) => pattern.test(text))).length;
  const subQuestions = Math.min((text.match(/[!?;]|\.(?=\s|$)/gu) ?? []).length, SUBQUESTION_CAP);
  const breadth = Math.min(domains * DOMAIN_POINTS, DOMAIN_CAP) + subQuestions * SUBQUESTION_POINTS;

  const words = text.split(/\s+/u).filter(Boolean).length;
  const lengthPoints = words > 150 ? 4 : words > 60 ? 2 : 0;
  const ambiguity =
    countHits(MARKER_PATTERNS, text, MARKER_CAP) * MARKER_POINTS +
    countHits(CONNECTOR_PATTERNS, text, CONNECTOR_CAP) * CONNECTOR_POINTS +
    lengthPoints;

  return { score: stakes + breadth + ambiguity, stakes, breadth, ambiguity };
}

interface NormalizedMode {
  readonly canonical: SessionMode;
  readonly size: CouncilMode;
}

function normalizeMode(explicitMode: string | null | undefined): NormalizedMode | null {
  if (typeof explicitMode !== 'string') return null;
  const candidate = explicitMode.trim().toLowerCase();
  if (!(SESSION_MODES as readonly string[]).includes(candidate)) return null;
  const canonical = candidate as SessionMode;
  return { canonical, size: SESSION_MODE_SIZES[canonical] };
}

function modeForScore(score: number): CouncilMode {
  if (score <= MODE_SCORE_THRESHOLDS.lightMax) return 'light';
  if (score >= MODE_SCORE_THRESHOLDS.heavyMin) return 'heavy';
  return 'medium';
}

/**
 * Pick the deliberation mode for one question.
 *
 * `explicitMode` is the client's own choice: any canonical SESSION_MODES value
 * is honoured (matched case-insensitively) and mapped to its council size, so
 * an explicit quick/consult/full/selected never falls through to automatic
 * classification. An unrecognized value is not a mode and does fall back to
 * the automatic classification. Every mode seats all nine advisors.
 */
export function selectMode(question: string, explicitMode?: string | null): ModeSelection {
  const clientChoice = normalizeMode(explicitMode);
  if (clientChoice !== null) {
    const { canonical, size } = clientChoice;
    return {
      mode: size,
      source: 'client',
      reason:
        canonical === size
          ? `client selected ${canonical}`
          : `client selected ${canonical} (council size ${size})`,
    };
  }

  const { score, stakes, breadth, ambiguity } = scoreComplexity(
    typeof question === 'string' ? question : '',
  );
  const mode = modeForScore(score);
  return {
    mode,
    source: 'auto',
    reason: `complexity score ${score} (stakes ${stakes}, breadth ${breadth}, ambiguity ${ambiguity}) selected ${mode}`,
  };
}
