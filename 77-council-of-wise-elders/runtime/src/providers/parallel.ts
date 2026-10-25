/**
 * Parallel dispatch limits (W77S-MODES).
 *
 * The council tries OpenRouter first and recommends it: every advisor runs
 * at once, no parallel limit. Agnes 3.0 Flash, when selected, has no
 * parallel limit either. A client's own Ollama does have one, fixed by the
 * plan they actually pay for: $20 a month → at most 3 advisors at a time,
 * $100 a month → at most 10. An unknown plan is a typed refusal, never a
 * guess: ask the client once, then convene again.
 *
 * This module is pure: the caller supplies the panel size and the plan.
 */

export type OllamaPlan = '20' | '100';

/** Ollama's own parallel caps by plan. */
const OLLAMA_PLAN_LIMITS: Readonly<Record<OllamaPlan, number>> = {
  '20': 3,
  '100': 10,
};

/** True for the `ollama` slug and every `ollama-*` variant (e.g. ollama-cloud). */
export function isOllamaProvider(providerSlug: string): boolean {
  return providerSlug === 'ollama' || providerSlug.startsWith('ollama-');
}

export type ParallelLimitResult =
  | { ok: true; limit: number }
  | { ok: false; code: 'OLLAMA_PLAN_REQUIRED' };

export function parallelLimitFor(input: {
  providerSlug: string;
  ollamaPlan: OllamaPlan | null;
  panelSize: number;
}): ParallelLimitResult {
  if (!isOllamaProvider(input.providerSlug)) {
    // OpenRouter, Agnes, DeepSeek and harness routes: all at once.
    return { ok: true, limit: input.panelSize };
  }
  if (input.ollamaPlan === null) {
    return { ok: false, code: 'OLLAMA_PLAN_REQUIRED' };
  }
  return {
    ok: true,
    limit: Math.min(OLLAMA_PLAN_LIMITS[input.ollamaPlan], input.panelSize),
  };
}
