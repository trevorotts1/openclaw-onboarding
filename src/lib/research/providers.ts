import type { Citation, PersistenceStore, SearchRecord, SearchResponse, SearchResult } from './types';
import { ProviderFailureError } from './types';

export interface ExecuteResearchSearchOpts { provider: string; query: string; callApi: () => Promise<Record<string, unknown>>; model?: string; }

export async function executeResearchSearch(opts: ExecuteResearchSearchOpts, store: PersistenceStore): Promise<SearchResult> {
  let raw: Record<string, unknown>;
  try { raw = await opts.callApi(); } catch (e: unknown) { throw new ProviderFailureError('Provider API call failed: ' + (e instanceof Error ? e.message : String(e))); }
  const choices = raw.choices as Array<{ message: { content: string } }> | undefined;
  const answer = choices?.[0]?.message?.content ?? '';
  const citations = parseCitations(raw.citations);
  if (!isNonEmptyAnswer(answer)) {
    throw new ProviderFailureError(
      'Provider "' + opts.provider + '" returned an empty answer ' +
      '(HTTP 200 / model ' + (opts.model ?? 'unknown') + ') treated as upstream failure. NOT persisted.',
      { answer: answer || '', citations: raw.citations as Array<{ url: string; title?: string; snippet?: string }> | undefined });
  }
  const grounded = citations.length > 0;
  const model = opts.model ?? (raw.model as string) ?? 'unknown';
  const u = raw.usage as { prompt_tokens?: number; completion_tokens?: number } | undefined;
  const record: SearchRecord = {
    id: 'rs-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9),
    query: opts.query, provider: opts.provider, model, answer, citations, grounded,
    ungrounded: grounded ? undefined : true, persistedAt: new Date().toISOString()
  };
  await store.save(record);
  return { persisted: true, record, response: { model, usage: { promptTokens: u?.prompt_tokens ?? 0, completionTokens: u?.completion_tokens ?? 0 }, citations: raw.citations as Citation[] | undefined } };
}

export class InMemoryStore implements PersistenceStore { records: SearchRecord[] = []; async save(r: SearchRecord): Promise<void> { this.records.push(r); } clear(): void { this.records = []; } }

export function parseCitations(raw: unknown): Citation[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((c): c is Record<string, unknown> => typeof c === 'object' && c !== null)
    .filter(c => { const u = c.url as string|undefined; const l = c.link as string|undefined; return (typeof u === 'string' && u.trim().length > 0) || (typeof l === 'string' && l.trim().length > 0); })
    .map(c => ({ url: (typeof c.url === 'string' && c.url.trim().length > 0) ? c.url.trim() : (c.link as string).trim(), title: typeof c.title === 'string' ? c.title : undefined, snippet: typeof c.snippet === 'string' ? c.snippet : typeof c.content === 'string' ? c.content : undefined }));
}

export function isNonEmptyAnswer(answer: unknown): boolean {
  if (typeof answer !== 'string') return false;
  return answer.replace(/\x00/g, '').trim().length > 0;
}
