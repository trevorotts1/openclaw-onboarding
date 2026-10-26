/**
 * PROVIDER-PARALLEL-1063: the parallel-agent table.
 *
 * Runner (the runtime's own runner; this file lives outside `npm test`'s
 * `tests/*.test.ts` glob, like route-snapshot.test.ts):
 *   node --import tsx --test src/providers/parallel.test.ts
 *
 * Pure table tests: no network, no credentials, no dispatch. Every row of
 * the intelligence is pinned here, and the DeepSeek Direct row is pinned
 * hardest because it was the route that had no coverage.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  OLLAMA_MONTHLY_TIERS,
  OLLAMA_PLAN_QUESTION,
  isOllamaProvider,
  parallelLimitFor,
  providerKindFor,
} from './parallel.js';

const PANEL = 9;
const BIG_PANEL = 12;

// ------------------------------------------------- Ollama: the two plans

test('1063: the $20/month Ollama plan runs at most 3 agents at a time', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '20', panelSize: PANEL }),
    { ok: true, limit: 3 },
  );
  // The same plan, spelled the way config actually carries it.
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: 20, panelSize: PANEL }),
    { ok: true, limit: 3 },
  );
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '$20/mo', panelSize: PANEL }),
    { ok: true, limit: 3 },
  );
});

test('1063: the $100+/month Ollama plan runs at most 10 agents at a time', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '100', panelSize: BIG_PANEL }),
    { ok: true, limit: 10 },
  );
  // "100+" is the tier, not a literal string: 100 and anything above it.
  for (const plan of ['100+', 100, 200, '$100/mo', '100 per month'] as const) {
    assert.deepEqual(
      parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: plan, panelSize: BIG_PANEL }),
      { ok: true, limit: 10 },
      String(plan),
    );
  }
});

test('1063: a wave never exceeds the panel the council actually has', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '100', panelSize: PANEL }),
    { ok: true, limit: 9 },
  );
  // Ollama Cloud is the same account and the same plan.
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama-cloud', ollamaPlan: '100', panelSize: PANEL }),
    { ok: true, limit: 9 },
  );
});

test('1063: an unknown Ollama plan asks once instead of guessing', () => {
  for (const plan of [null, undefined, '', 'free', 'unknown'] as const) {
    assert.deepEqual(
      parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: plan, panelSize: PANEL }),
      { ok: false, code: 'OLLAMA_PLAN_REQUIRED' },
      String(plan),
    );
  }
  // A price that matches no tier is unknown too: never a guess.
  for (const plan of ['50', 35, '19.99'] as const) {
    assert.deepEqual(
      parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: plan, panelSize: PANEL }),
      { ok: false, code: 'OLLAMA_PLAN_REQUIRED' },
      String(plan),
    );
  }
});

test('1063: the ask-once question names both plans', () => {
  assert.match(OLLAMA_PLAN_QUESTION, /\$20/);
  assert.match(OLLAMA_PLAN_QUESTION, /\$100\+/);
  assert.equal(OLLAMA_MONTHLY_TIERS.basic, 20);
  assert.equal(OLLAMA_MONTHLY_TIERS.premium, 100);
});

// ------------------------------------- DeepSeek Direct: the missing row

test('1063: DeepSeek Direct is a recognised provider with no cap', () => {
  for (const slug of [
    'deepseek-direct',
    'deepseek_direct',
    'DeepSeek Direct',
    'deepseek',
    'deepseek-direct-api',
  ]) {
    assert.equal(providerKindFor(slug), 'deepseek-direct', slug);
    assert.equal(isOllamaProvider(slug), false, slug);
    assert.deepEqual(
      parallelLimitFor({ providerSlug: slug, ollamaPlan: null, panelSize: PANEL }),
      { ok: true, limit: PANEL },
      slug,
    );
  }
});

test('1063: DeepSeek Direct never triggers the Ollama plan question', () => {
  const result = parallelLimitFor({
    providerSlug: 'deepseek-direct',
    ollamaPlan: null,
    panelSize: PANEL,
  });
  assert.notEqual(result.ok, false);
  assert.equal(result.ok, true);
  // A stale plan value on a DeepSeek route cannot cap it either.
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'deepseek-direct', ollamaPlan: '20', panelSize: PANEL }),
    { ok: true, limit: PANEL },
  );
});

// --------------------------------------------- Agnes and OpenRouter rows

test('1063: Agnes 3.0 Flash runs any amount of agents at once', () => {
  for (const slug of ['agnes', 'agnes-3.0-flash', 'agnes-3.0-flash-cloud', 'Agnes 3.0 Flash']) {
    assert.equal(providerKindFor(slug), 'agnes', slug);
    assert.deepEqual(
      parallelLimitFor({ providerSlug: slug, ollamaPlan: null, panelSize: 40 }),
      { ok: true, limit: 40 },
      slug,
    );
  }
});

test('1063: OpenRouter runs the whole panel at once', () => {
  for (const slug of ['openrouter', 'openrouter-configured']) {
    assert.equal(providerKindFor(slug), 'openrouter', slug);
    assert.deepEqual(
      parallelLimitFor({ providerSlug: slug, ollamaPlan: null, panelSize: PANEL }),
      { ok: true, limit: PANEL },
      slug,
    );
  }
});

test('1063: an unrecognised provider is uncapped, never plan-questioned', () => {
  const result = parallelLimitFor({
    providerSlug: 'harness-route',
    ollamaPlan: null,
    panelSize: PANEL,
  });
  assert.deepEqual(result, { ok: true, limit: PANEL });
});

// ------------------------------------------------------- slug and bounds

test('1063: isOllamaProvider matches the slug and its variants only', () => {
  assert.equal(isOllamaProvider('ollama'), true);
  assert.equal(isOllamaProvider('OLLAMA'), true);
  assert.equal(isOllamaProvider('ollama-cloud'), true);
  assert.equal(isOllamaProvider('ollama_cloud'), true);
  assert.equal(isOllamaProvider('openrouter-configured'), false);
  assert.equal(isOllamaProvider('deepseek-direct'), false);
  assert.equal(isOllamaProvider('agnes-3.0-flash'), false);
  assert.equal(isOllamaProvider('not-ollama'), false);
});

test('1063: a nonsense panel size never becomes a wave width', () => {
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'deepseek-direct', ollamaPlan: null, panelSize: Number.NaN }),
    { ok: true, limit: 0 },
  );
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'deepseek-direct', ollamaPlan: null, panelSize: -5 }),
    { ok: true, limit: 0 },
  );
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'deepseek-direct', ollamaPlan: null, panelSize: 7.9 }),
    { ok: true, limit: 7 },
  );
  assert.deepEqual(
    parallelLimitFor({ providerSlug: 'ollama', ollamaPlan: '20', panelSize: Number.NaN }),
    { ok: true, limit: 0 },
  );
});
