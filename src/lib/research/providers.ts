/**
 * providers.ts — Research provider abstraction for the onboarding operator.
 *
 * Every research query flows through executeProviderQuery(), which
 * validates the provider response before it reaches persistence or the
 * vault mirror.  The validation layer enforces two invariants:
 *
 *   1. An empty answer is a provider failure — it MUST NOT be persisted
 *      as a completed search.  The caller receives an upstream error and
 *      nothing is written.
 *   2. A zero-citation result whose answer is non-empty IS stored, but
 *      MUST be stamped as *ungrounded* so downstream consumers can
 *      distinguish it from fully grounded research.
 *
 * Provider adapters implement the ResearchProvider interface and are
 * registered through the provider registry.
 */

// ── Types ────────────────────────────────────────────────────────────────────────

/** Status a provider returns for its own result. */
export interface ProviderResultMeta {
  /** HTTP-or-protocol status code the provider returned. */
  statusCode: number;
  /** Machine-readable provider identifier (e.g. "tavily", "perplexity"). */
  provider: string;
  /** Wall-clock timestamp of the provider response (ISO-8601). */
  respondedAt: string;
}

/** One citation / source returned by the provider. */
export interface Citation {
  url: string;
  title?: string;
  snippet?: string;
}

/** What the provider hands back after a successful call. */
export interface ProviderPayload {
  /** The natural-language answer text.  MUST be non-empty for a valid result. */
  answer: string;
  /** Citations / sources backing the answer.  MAY be empty. */
  citations: Citation[];
  /** Provider-reported token usage (informational). */
  tokensUsed?: number;
  /** Raw provider latency in ms (informational). */
  latencyMs?: number;
}

/**
 * The validated, ready-to-persist result produced by the validation
 * layer.  Upstream callers (API routes, vault mirror) consume this type
 * — never the raw {@link ProviderPayload}.
 */
export interface ResearchResult {
  /** The non-empty answer returned by the provider. */
  answer: string;
  /** Citations returned by the provider (may be empty). */
  citations: Citation[];
  /** Whether the result is grounded by at least one citation. */
  grounded: boolean;
  /**
   * When true the answer is real but no citation backs it.
   * Consumers MUST display an "ungrounded" stamp / annotation.
   */
  ungroundedStamp: boolean;
  /** Provider metadata for audit / tracing. */
  meta: ProviderResultMeta;
}

// ── Errors ───────────────────────────────────────────────────────────────────────

/** Structured error thrown when a provider call fails. */
export class ProviderError extends Error {
  public readonly code: string;
  public readonly statusCode: number;
  public readonly retryable: boolean;

  constructor(message: string, code: string, statusCode: number, retryable = false) {
    super(message);
    this.name = 'ProviderError';
    this.code = code;
    this.statusCode = statusCode;
    this.retryable = retryable;
  }
}

// ── Provider interface ───────────────────────────────────────────────────────────

export interface ResearchProvider {
  /** Unique provider key (e.g. "tavily", "perplexity"). */
  readonly key: string;
  /**
   * Execute a single research query.
   *
   * The provider is responsible for transport and parsing.
   * It MUST throw {@link ProviderError} on transport / auth / protocol
   * failures.  Empty-answer detection is handled by the common validation
   * layer in {@link executeProviderQuery}.
   */
  execute(query: string, options?: ResearchQueryOptions): Promise<ProviderPayload>;
}

export interface ResearchQueryOptions {
  /** Maximum citations to request from the provider. */
  maxCitations?: number;
  /** Override the provider's default search depth. */
  searchDepth?: 'basic' | 'advanced';
  /** Additional provider-specific parameters. */
  extra?: Record<string, unknown>;
}

// ── Provider registry ────────────────────────────────────────────────────────────

const registry = new Map<string, ResearchProvider>();

export function registerProvider(provider: ResearchProvider): void {
  if (registry.has(provider.key)) {
    throw new Error(`Provider "${provider.key}" is already registered.`);
  }
  registry.set(provider.key, provider);
}

export function getProvider(key: string): ResearchProvider | undefined {
  return registry.get(key);
}

export function listProviders(): string[] {
  return Array.from(registry.keys());
}

// ── Validation layer ─────────────────────────────────────────────────────────────

/**
 * Validate the raw provider payload and produce a {@link ResearchResult}.
 *
 * ## Validation rules
 *
 * | Condition                                    | Outcome                          |
 * |----------------------------------------------|----------------------------------|
 * | `answer` is empty / whitespace-only          | throws {@link ProviderError}     |
 * | `answer` is non-empty, `citations` non-empty | `grounded=true`, stored normally |
 * | `answer` is non-empty, `citations` empty     | `grounded=false`, `ungroundedStamp=true`, stored |
 *
 * @throws {ProviderError} when the answer is empty — the caller MUST NOT
 *   persist the result and MUST surface the error upstream.
 */
function validatePayload(
  payload: ProviderPayload,
  meta: ProviderResultMeta,
): ResearchResult {
  // ── lines ~134-136: empty-answer guard ───────────────────────────────────
  //
  // Prior behaviour (bug): empty successful responses flowed through to
  // persistence.  The rendered output showed "(no answer returned)" but
  // the record status said nothing about the empty result, and anything
  // counting completed searches treated it as real.
  //
  // Fix: treat an empty answer as a provider failure.  Throw an upstream
  // error so the caller never persists the record.

  if (!payload.answer || payload.answer.trim().length === 0) {
    throw new ProviderError(
      `Provider "${meta.provider}" returned an empty answer — treating as provider failure`,
      'EMPTY_ANSWER',
      meta.statusCode,
      true, // retryable — transient provider hiccup
    );
  }

  // ── Zero-citation guard: store but stamp as ungrounded ────────────────────
  const hasCitations = payload.citations && payload.citations.length > 0;

  return {
    answer: payload.answer.trim(),
    citations: payload.citations ?? [],
    grounded: hasCitations,
    ungroundedStamp: !hasCitations,
    meta,
  };
}

// ── Public API ───────────────────────────────────────────────────────────────────

/**
 * Execute a research query through a named provider and return a validated,
 * persistence-ready {@link ResearchResult}.
 *
 * Callers (API routes, vault mirror) MUST use this function instead of
 * calling providers directly.  It enforces the empty-answer and
 * zero-citation invariants at a single choke-point so bugs cannot
 * reappear in individual call-sites.
 *
 * @param providerKey - Registered provider key (e.g. "tavily").
 * @param query       - Natural-language research query.
 * @param options     - Optional provider-specific tuning.
 * @returns A validated result safe for persistence.
 * @throws {ProviderError} on transport failure, empty answer, or unknown provider.
 */
export async function executeProviderQuery(
  providerKey: string,
  query: string,
  options?: ResearchQueryOptions,
): Promise<ResearchResult> {
  const provider = registry.get(providerKey);
  if (!provider) {
    throw new ProviderError(
      `Unknown research provider: "${providerKey}"`,
      'UNKNOWN_PROVIDER',
      404,
    );
  }

  let payload: ProviderPayload;
  try {
    payload = await provider.execute(query, options);
  } catch (err) {
    // Re-throw ProviderErrors as-is; wrap unexpected errors.
    if (err instanceof ProviderError) {
      throw err;
    }
    throw new ProviderError(
      `Provider "${providerKey}" execution failed: ${(err as Error).message}`,
      'PROVIDER_EXECUTION_FAILED',
      502,
      true,
    );
  }

  const meta: ProviderResultMeta = {
    statusCode: 200,
    provider: providerKey,
    respondedAt: new Date().toISOString(),
  };

  return validatePayload(payload, meta);
}

// ── Convenience: pre-built providers ─────────────────────────────────────────────

/**
 * Create an in-memory research provider backed by a static payload factory.
 * Useful for testing and for providers whose transport is handled elsewhere.
 */
export function createStaticProvider(
  key: string,
  factory: (query: string, options?: ResearchQueryOptions) => ProviderPayload | Promise<ProviderPayload>,
): ResearchProvider {
  return {
    key,
    execute: (q, opts) => Promise.resolve(factory(q, opts)),
  };
}
