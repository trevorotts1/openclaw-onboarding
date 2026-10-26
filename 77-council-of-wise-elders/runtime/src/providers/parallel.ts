/**
 * Parallel dispatch limits (W77S-MODES).
 *
 * One table, read straight off what the client actually pays for:
 *
 * | route                       | agents in parallel              |
 * | --------------------------- | ------------------------------- |
 * | Ollama, $20/month plan      | 3                               |
 * | Ollama, $100+/month plan    | 10                              |
 * | Ollama, plan unknown        | OLLAMA_PLAN_REQUIRED (ask once) |
 * | Agnes 3.0 Flash             | unlimited                       |
 * | OpenRouter                  | unlimited                       |
 * | DeepSeek Direct             | unlimited                       |
 * | any other direct paid route | unlimited                       |
 *
 * OpenRouter stays the recommended route and runs every advisor at once.
 * Agnes 3.0 Flash, when selected, has no parallel limit either. A client's
 * own Ollama does have one, fixed by the plan they pay for; $100 and above
 * is one tier, so "100+" is 10. An unknown plan is a typed refusal, never a
 * guess: ask the client once (OLLAMA_PLAN_QUESTION), then convene again.
 *
 * DeepSeek Direct is a paying provider in its own right. It is recognised
 * explicitly so it can never be mistaken for an Ollama slug and never
 * raises the Ollama plan question.
 *
 * This module is pure: the caller supplies the panel size and the plan.
 */

export type OllamaPlan = '20' | '100';

/**
 * A client-supplied plan as it really arrives from config, a form, or JSON:
 * `'20'`, `20`, `'$100/mo'`, `'100+'`, or absent. Normalised, never trusted.
 */
export type OllamaPlanInput = OllamaPlan | number | string | null | undefined;

/** Ollama's own parallel caps by plan. $100 and above is one tier. */
const OLLAMA_PLAN_LIMITS: Readonly<Record<OllamaPlan, number>> = {
  '20': 3,
  '100': 10,
};

/** The plan tiers this intelligence knows, in dollars per month. */
export const OLLAMA_MONTHLY_TIERS = { basic: 20, premium: 100 } as const;

/** The one question a client is asked, once, when their plan is unknown. */
export const OLLAMA_PLAN_QUESTION =
  'Which Ollama plan do you pay for: the $20/month plan (3 advisors run at a time) or the $100+/month plan (10 run at a time)?';

/** How a route slug is classified for parallel dispatch. */
export type ProviderParallelKind =
  | 'ollama'
  | 'openrouter'
  | 'agnes'
  | 'deepseek-direct'
  | 'uncapped';

/**
 * A slug in one spelling: lowercase, punctuation collapsed to `-`. The
 * same route arrives as `deepseek-direct`, `deepseek_direct`, and
 * `DeepSeek Direct`; all three are one provider.
 */
function normalizeSlug(providerSlug: string): string {
  return providerSlug
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Classify a route slug. Only `ollama` and its variants (`ollama-cloud`,
 * the client's own signed-in daemon) carry a plan cap; every other
 * recognised provider is uncapped, and an unrecognised provider is
 * uncapped by default rather than guessed at.
 */
export function providerKindFor(providerSlug: string): ProviderParallelKind {
  const slug = normalizeSlug(providerSlug);
  if (slug === 'ollama' || slug.startsWith('ollama-')) return 'ollama';
  if (slug === 'openrouter' || slug.startsWith('openrouter-')) return 'openrouter';
  // Agnes 3.0 Flash (and its aliases: agnes, agnes-3-0-flash).
  if (slug === 'agnes' || slug.startsWith('agnes-')) return 'agnes';
  // DeepSeek Direct: deepseek, deepseek-direct, deepseek-direct-api,
  // deepseek_direct, "DeepSeek Direct", deepseekdirect.
  if (slug === 'deepseek' || slug === 'deepseekdirect' || slug.startsWith('deepseek-')) {
    return 'deepseek-direct';
  }
  return 'uncapped';
}

/** True for the `ollama` slug and every `ollama-*` variant (e.g. ollama-cloud). */
export function isOllamaProvider(providerSlug: string): boolean {
  return providerKindFor(providerSlug) === 'ollama';
}

/**
 * The monthly price a plan value states, or null when it states none.
 * `'$20'`, `'20/mo'`, `'100+'` and `20` all name a price; `'free'` and
 * blank values name none.
 */
function monthlyPrice(plan: OllamaPlanInput): number | null {
  if (plan === null || plan === undefined) return null;
  const digits = String(plan).replace(/[^0-9.]/g, '');
  if (digits.length === 0) return null;
  const price = Number(digits);
  return Number.isFinite(price) ? price : null;
}

/**
 * The cap the paid plan carries, or null when the plan is unknown. Only
 * the tiers that exist are answered; a value between them is unknown and
 * gets the question, never a guess.
 */
function ollamaParallelCap(plan: OllamaPlanInput): number | null {
  const price = monthlyPrice(plan);
  if (price === null) return null;
  if (price >= OLLAMA_MONTHLY_TIERS.premium) return OLLAMA_PLAN_LIMITS['100'];
  if (price === OLLAMA_MONTHLY_TIERS.basic) return OLLAMA_PLAN_LIMITS['20'];
  return null;
}

export type ParallelLimitResult =
  | { ok: true; limit: number }
  | { ok: false; code: 'OLLAMA_PLAN_REQUIRED' };

export function parallelLimitFor(input: {
  providerSlug: string;
  ollamaPlan: OllamaPlanInput;
  panelSize: number;
  /**
   * The mode's own wave width. Omitted means the mode adds no cap (the
   * whole panel runs at once, subject to the provider limit).
   */
  waveWidth?: number;
}): ParallelLimitResult {
  // The panel bounds every answer; a non-number never becomes a wave width.
  const panel = Number.isFinite(input.panelSize)
    ? Math.max(0, Math.floor(input.panelSize))
    : 0;
  // The mode's own wave width bounds the panel too. Omitted means the mode
  // adds no cap and the whole panel may run at once.
  const modeCap = Math.max(1, input.waveWidth ?? panel);
  if (providerKindFor(input.providerSlug) !== 'ollama') {
    // OpenRouter, Agnes 3.0 Flash, DeepSeek Direct and every other direct
    // paid route: all at once, up to the mode's wave width.
    return { ok: true, limit: Math.min(panel, modeCap) };
  }
  const cap = ollamaParallelCap(input.ollamaPlan);
  if (cap === null) return { ok: false, code: 'OLLAMA_PLAN_REQUIRED' };
  return { ok: true, limit: Math.min(cap, panel, modeCap) };
}
