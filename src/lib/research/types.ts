export interface Citation { url: string; title?: string; snippet?: string; }
export class ProviderFailureError extends Error { constructor(message: string, public readonly rawResponse?: { answer: string; citations?: Array<{ url: string; title?: string; snippet?: string }> }) { super(message); this.name = 'ProviderFailureError'; } }
export interface SearchRecord { id: string; query: string; provider: string; model: string; answer: string; citations: Citation[]; grounded: boolean; ungrounded?: boolean; persistedAt: string; }
export interface SearchResponse { model: string; usage: { promptTokens: number; completionTokens: number }; citations?: Citation[]; }
export interface PersistenceStore { save(record: SearchRecord): Promise<void>; }
export interface SearchResult { persisted: boolean; record: SearchRecord | null; response: SearchResponse; }
export interface RegistryEntry { provider: string; modelId: string; web_search: boolean; active: boolean; label?: string; }
export interface ResolvedModel { provider: string; modelId: string; }
export interface ModelResolution { chosen: ResolvedModel | null; reason: string; usedDefault: boolean; }
export interface ResolveModelParams { provider: string; requestedModelId?: string; }
