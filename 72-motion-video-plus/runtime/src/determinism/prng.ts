// Seeded pseudo-randomness for the determinism verifier (Directive
// MG-026). The randomized frame access pattern must itself be
// reproducible: an unseeded shuffle would make the test suite flaky in
// exactly the way the item exists to forbid in shipped scenes. The
// verifier therefore draws every "random" choice from this seeded
// generator and records the seed in the evidence record, so any run
// can be replayed order for order.

/** mulberry32: a small, well distributed 32 bit seeded generator. The
 * verifier needs reproducibility across processes and Node versions,
 * which Math.random can never promise; integer arithmetic can. */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A Fisher-Yates shuffle driven by the seeded generator. The input
 * array is not mutated. */
export function seededOrder<T>(items: readonly T[], seed: number): T[] {
  const rand = mulberry32(seed);
  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
}

/** Seed used for the randomized access pattern in the MG-026 suite.
 * Recorded here and in the evidence record so the order is replayable. */
export const RANDOM_PATTERN_SEED = 20261014;
