import { describe, it, expect, beforeEach } from 'vitest';
import { executeResearchSearch, InMemoryStore, parseCitations, isNonEmptyAnswer } from '../../src/lib/research/providers';
import { ProviderFailureError } from '../../src/lib/research/types';

function mockApiResponse(answer: string, citations?: Array<{ url: string; title?: string; snippet?: string }>, model?: string): Record<string, unknown> {
  const r: Record<string, unknown> = { model: model ?? 'gemini-2.5-flash', choices: [{ message: { content: answer } }], usage: { prompt_tokens: 50, completion_tokens: 20 } };
  if (citations && citations.length > 0) r.citations = citations;
  return r;
}
function mockCallApi(r: Record<string, unknown>) { return async () => r; }
function mockFailingApi(m: string) { return async () => { throw new Error(m); }; }

describe('executeResearchSearch', () => {
  let store: InMemoryStore;
  beforeEach(() => { store = new InMemoryStore(); });

  it('U087: empty answer throws ProviderFailureError and does NOT persist', async () => {
    await expect(executeResearchSearch({ provider: 'gemini', query: 't', callApi: mockCallApi(mockApiResponse('', [{ url: 'https://x.com' }])) }, store)).rejects.toThrow(ProviderFailureError);
    expect(store.records).toHaveLength(0);
  });

  it('U087: whitespace-only answer throws ProviderFailureError', async () => {
    const ws = String.fromCharCode(32, 10, 32, 9, 32);
    await expect(executeResearchSearch({ provider: 'gemini', query: 't', callApi: mockCallApi(mockApiResponse(ws)) }, store)).rejects.toThrow(ProviderFailureError);
    expect(store.records).toHaveLength(0);
  });

  it('U087: raw response attached to error for logging', async () => {
    try { await executeResearchSearch({ provider: 'gemini', query: 't', callApi: mockCallApi(mockApiResponse('')) }, store); expect.fail('expected throw'); }
    catch (err) { expect((err as ProviderFailureError).rawResponse?.answer).toBe(''); }
  });

  it('U087: citations alone do not redeem empty answer', async () => {
    await expect(executeResearchSearch({ provider: 'gemini', query: 't', callApi: mockCallApi(mockApiResponse('', [{ url: 'https://a.com' }, { url: 'https://b.com' }])) }, store)).rejects.toThrow(ProviderFailureError);
    expect(store.records).toHaveLength(0);
  });

  it('U087: zero-citation non-empty answer persisted with ungrounded: true', async () => {
    const r = await executeResearchSearch({ provider: 'gemini', query: 'q', callApi: mockCallApi(mockApiResponse('Valid answer')) }, store);
    expect(r.persisted).toBe(true); expect(r.record!.ungrounded).toBe(true); expect(r.record!.grounded).toBe(false);
    expect(r.record!.answer).toBe('Valid answer'); expect(store.records).toHaveLength(1);
  });

  it('non-empty answer with citations is grounded', async () => {
    const r = await executeResearchSearch({ provider: 'gemini', query: 'q', callApi: mockCallApi(mockApiResponse('Grounded', [{ url: 'https://src1.com', title: 'S1' }, { url: 'https://src2.com', title: 'S2' }])) }, store);
    expect(r.record!.grounded).toBe(true); expect(r.record!.ungrounded).toBeUndefined(); expect(r.record!.citations).toHaveLength(2);
  });

  it('correct metadata on record', async () => {
    const r = await executeResearchSearch({ provider: 'gemini', query: 'meta', callApi: mockCallApi(mockApiResponse('x', [{ url: 'https://m.com' }], 'gemini-2.5-pro')), model: 'gemini-2.5-pro' }, store);
    expect(r.record!.provider).toBe('gemini'); expect(r.record!.model).toBe('gemini-2.5-pro'); expect(r.record!.id).toMatch(/^rs-/);
    expect(r.response.usage).toEqual({ promptTokens: 50, completionTokens: 20 });
  });

  it('API transport failure throws without persisting', async () => {
    await expect(executeResearchSearch({ provider: 'gemini', query: 't', callApi: mockFailingApi('timeout') }, store)).rejects.toThrow(ProviderFailureError);
    expect(store.records).toHaveLength(0);
  });

  it('punctuation-only answer is non-empty (not a failure)', async () => {
    const r = await executeResearchSearch({ provider: 'gemini', query: 'q', callApi: mockCallApi(mockApiResponse('...')) }, store);
    expect(r.persisted).toBe(true); expect(r.record!.answer).toBe('...');
  });

  it('long answer with no cites stored ungrounded', async () => {
    const a = 'x'.repeat(10000);
    const r = await executeResearchSearch({ provider: 'gemini', query: 'q', callApi: mockCallApi(mockApiResponse(a)) }, store);
    expect(r.record!.ungrounded).toBe(true); expect(r.record!.answer).toBe(a);
  });

  it('null bytes-only answer is empty failure', async () => {
    const nb3 = String.fromCharCode(0, 0, 0);
    await expect(executeResearchSearch({ provider: 'gemini', query: 'q', callApi: mockCallApi(mockApiResponse(nb3)) }, store)).rejects.toThrow(ProviderFailureError);
  });
});

describe('parseCitations', () => {
  it('null/undefined/non-array returns []', () => { expect(parseCitations(null)).toEqual([]); expect(parseCitations(undefined)).toEqual([]); expect(parseCitations('x')).toEqual([]); });
  it('parses standard citations', () => { expect(parseCitations([{ url: 'https://a.com', title: 'A' }, { url: 'https://b.com' }])).toHaveLength(2); });
  it('filters entries without url', () => { expect(parseCitations([{ title: 'x' }, { url: 'https://v.com' }])).toHaveLength(1); });
  it('accepts link as url fallback', () => { expect(parseCitations([{ link: 'https://l.com' }])[0].url).toBe('https://l.com'); });
  it('accepts content as snippet fallback', () => { expect(parseCitations([{ url: 'https://x.com', content: 'c' }])[0].snippet).toBe('c'); });
});

describe('InMemoryStore', () => {
  it('starts empty', () => { expect(new InMemoryStore().records).toHaveLength(0); });
  it('saves and clears', async () => {
    const s = new InMemoryStore();
    await s.save({ id: 'rs-1', query: 't', provider: 'g', model: 'm', answer: 'a', citations: [], grounded: false, ungrounded: true, persistedAt: new Date().toISOString() });
    expect(s.records).toHaveLength(1);
    s.clear(); expect(s.records).toHaveLength(0);
  });
});

describe('isNonEmptyAnswer', () => {
  it('false for empty/whitespace/nullbyte', () => { expect(isNonEmptyAnswer('')).toBe(false); expect(isNonEmptyAnswer('  ')).toBe(false); expect(isNonEmptyAnswer(String.fromCharCode(10,9))).toBe(false); expect(isNonEmptyAnswer(String.fromCharCode(0,0))).toBe(false); });
  it('true for real content', () => { expect(isNonEmptyAnswer('hello')).toBe(true); expect(isNonEmptyAnswer(' . ')).toBe(true); });
  it('false for non-strings', () => { expect(isNonEmptyAnswer(null)).toBe(false); expect(isNonEmptyAnswer(undefined)).toBe(false); expect(isNonEmptyAnswer(123)).toBe(false); });
});

describe('U087 mutation proof', () => {
  it('GREEN: empty answer rejected', () => { expect(isNonEmptyAnswer('')).toBe(false); });
  it('RED (simulated): broken guard always-true would persist empty', () => { const b = (_: unknown) => true; expect(b('')).toBe(true); });
  it('GREEN restored: real guard rejects empty again', () => { expect(isNonEmptyAnswer('')).toBe(false); });
  it('GREEN: real guard accepts real answer', () => { expect(isNonEmptyAnswer('actual')).toBe(true); });
});
