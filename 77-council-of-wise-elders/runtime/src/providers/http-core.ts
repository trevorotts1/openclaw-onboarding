/**
 * Single-attempt HTTP executor for OpenAI-compatible endpoints
 * (CWE-009; directive Sections 13, 15.5, 15.8, 16.6).
 *
 * One call to executeHttpAttempt performs exactly one network attempt:
 * it never retries, never follows a redirect, and never substitutes
 * anything. Retry policy lives in the transport (compatible.ts); this
 * module owns the wire facts:
 *
 * - the per-operation deadline (an AbortController separate from any
 *   operation lease, Section 15.8) and caller cancellation;
 * - failure classification: a failure provably before acceptance
 *   (connection refused, DNS) is a retryable network failure; a
 *   failure after the request may have been submitted (deadline while
 *   awaiting the response, a broken stream, an ambiguous socket
 *   error) is provider_submitted_unresolved and is never replayed
 *   blindly (Section 15.5);
 * - response parsing: text, the provider's structured reported model
 *   id, usage, and the provider request id, for both the JSON envelope
 *   and server-sent-event streams. Model identity is read ONLY from
 *   structured fields, never from prose content (Section 13.4), and
 *   hidden-reasoning fields are never read into any output;
 * - safe parse diagnostics: a malformed envelope yields only an error
 *   code, a schema path, a byte count, and a body hash (Section 16.6).
 *   Bodies are hashed and counted in memory and never retained.
 */

import { sha256Hex } from '../contracts/index.js';
import { TransportError } from './errors.js';

/** Hard read cap for one response body, in memory. */
export const MAX_RESPONSE_BYTES = 25 * 1024 * 1024;

export interface FetchResponseLike {
  status: number;
  headers: { get(name: string): string | null };
  body: ReadableStream<Uint8Array> | null;
}

export type FetchLike = (
  url: string,
  init: {
    method: string;
    headers: Record<string, string>;
    body: string;
    signal: AbortSignal;
    redirect: 'manual';
  },
) => Promise<FetchResponseLike>;

const defaultFetch: FetchLike = (url, init) =>
  globalThis.fetch(url, init) as Promise<FetchResponseLike>;

export interface HttpAttemptInput {
  url: string;
  headers: Record<string, string>;
  /** Canonical request body text, built once per operation by the transport. */
  bodyText: string;
  /** Request the streaming form of the compatible API. */
  stream: boolean;
  /** Remaining operation deadline for this attempt, in milliseconds. */
  deadlineMs: number;
  /** Caller cancellation (the engine's operation signal). */
  signal?: AbortSignal;
}

export interface HttpAttemptOutcome {
  status: number;
  retryAfterMs: number | null;
  providerRequestId: string | null;
  /** Structured provider-reported model id (2xx only). */
  reportedModelId: string | null;
  /** Model text (2xx only). Hidden-reasoning fields are never included. */
  text: string | null;
  usage: { input_tokens: number | null; output_tokens: number | null };
  bodyBytes: number;
  bodySha256: string;
}

export interface HttpCoreDeps {
  fetchImpl?: FetchLike;
  nowMs?: () => number;
}

/** Parse a Retry-After header (delay-seconds or HTTP-date) to milliseconds. */
export function parseRetryAfterMs(
  headerValue: string | null,
  nowMs: number,
): number | null {
  if (!headerValue) return null;
  const trimmed = headerValue.trim();
  if (/^\d+$/.test(trimmed)) return Number(trimmed) * 1000;
  const dateMs = Date.parse(trimmed);
  if (!Number.isNaN(dateMs)) return Math.max(0, dateMs - nowMs);
  return null;
}

function errorCodes(err: unknown): string[] {
  const codes: string[] = [];
  let current: unknown = err;
  for (let depth = 0; depth < 4 && current !== null && typeof current === 'object'; depth++) {
    const code = (current as { code?: unknown }).code;
    if (typeof code === 'string') codes.push(code);
    current = (current as { cause?: unknown }).cause;
  }
  return codes;
}

const NOT_SUBMITTED_CODES: ReadonlySet<string> = new Set([
  'ECONNREFUSED',
  'ENOTFOUND',
  'EAI_AGAIN',
  'EADDRNOTAVAIL',
  'ENETUNREACH',
  'EHOSTUNREACH',
]);

function isTlsCode(code: string): boolean {
  return (
    code.startsWith('ERR_TLS') ||
    code.startsWith('ERR_SSL') ||
    code.includes('CERT') ||
    code === 'UNABLE_TO_VERIFY_LEAF_SIGNATURE' ||
    code === 'DEPTH_ZERO_SELF_SIGNED_CERT' ||
    code === 'SELF_SIGNED_CERT_IN_CHAIN'
  );
}

/**
 * Classify a rejected fetch. `submitted` is true once the request has
 * been handed to fetch: from that point an ambiguous failure means the
 * provider may have accepted it, and the honest state is unresolved.
 */
export function classifyFetchFailure(
  err: unknown,
  flags: { deadlineFired: boolean; callerAborted: boolean },
): TransportError {
  if (flags.callerAborted) {
    return new TransportError(
      'TRANSPORT_CANCELLED',
      'The operation was cancelled by the caller while the provider request was in flight.',
      { cancelled: true },
    );
  }
  if (flags.deadlineFired) {
    return new TransportError(
      'TRANSPORT_SUBMITTED_UNRESOLVED',
      'The provider request deadline expired after the request was submitted. Completion is unknown; the request is not assumed failed and is not replayed automatically.',
      { unknownCompletion: true },
    );
  }
  const codes = errorCodes(err);
  if (codes.some((c) => NOT_SUBMITTED_CODES.has(c))) {
    return new TransportError(
      'TRANSPORT_NETWORK_FAILED',
      `The provider endpoint could not be reached (${codes.join(', ')}). The request was not accepted, so a bounded retry is safe.`,
      { retryable: true },
    );
  }
  if (codes.some(isTlsCode)) {
    return new TransportError(
      'TRANSPORT_NETWORK_FAILED',
      `The provider endpoint failed TLS validation (${codes.join(', ')}). This is a configuration problem, not a transient failure.`,
      { retryable: false },
    );
  }
  // Ambiguous: the request may have been accepted. Never blind-retry.
  return new TransportError(
    'TRANSPORT_SUBMITTED_UNRESOLVED',
    'The provider connection failed after the request was submitted. Completion is unknown; the request is not assumed failed and is not replayed automatically.',
    { unknownCompletion: true },
  );
}

interface ParsedEnvelope {
  text: string;
  reportedModelId: string | null;
  providerRequestId: string | null;
  usage: { input_tokens: number | null; output_tokens: number | null };
}

function malformed(
  schemaPath: string,
  byteCount: number,
  responseSha256: string,
  note: string,
): TransportError {
  return new TransportError(
    'TRANSPORT_RESPONSE_MALFORMED',
    `The provider response did not match the compatible envelope at ${schemaPath} (${note}). Only safe metadata was recorded: error code, schema path, byte count, and response hash.`,
    { parseDiagnostics: { schemaPath, byteCount, responseSha256 } },
  );
}

function usageFrom(value: unknown): {
  input_tokens: number | null;
  output_tokens: number | null;
} {
  if (value === null || typeof value !== 'object') {
    return { input_tokens: null, output_tokens: null };
  }
  const usage = value as Record<string, unknown>;
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null;
  return {
    input_tokens: num(usage.prompt_tokens),
    output_tokens: num(usage.completion_tokens),
  };
}

function contentText(content: unknown): string | null {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const part of content) {
      if (typeof part === 'string') parts.push(part);
      else if (
        part !== null &&
        typeof part === 'object' &&
        (part as { type?: unknown }).type === 'text' &&
        typeof (part as { text?: unknown }).text === 'string'
      ) {
        parts.push((part as { text: string }).text);
      }
    }
    return parts.join('');
  }
  return null;
}

/** Parse one non-streaming chat-completion envelope. Throws safe errors only. */
export function parseChatCompletionEnvelope(
  bodyText: string,
  byteCount: number,
  responseSha256: string,
  headerRequestId: string | null,
): ParsedEnvelope {
  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    throw malformed('$', byteCount, responseSha256, 'body is not valid JSON');
  }
  if (parsed === null || typeof parsed !== 'object') {
    throw malformed('$', byteCount, responseSha256, 'body is not a JSON object');
  }
  const root = parsed as Record<string, unknown>;
  const choices = root.choices;
  if (!Array.isArray(choices) || choices.length === 0) {
    throw malformed('choices', byteCount, responseSha256, 'choices array missing or empty');
  }
  const first = choices[0] as Record<string, unknown> | null;
  const message = first?.message as Record<string, unknown> | null | undefined;
  if (!message || typeof message !== 'object') {
    throw malformed('choices[0].message', byteCount, responseSha256, 'message object missing');
  }
  const text = contentText(message.content);
  if (text === null) {
    throw malformed(
      'choices[0].message.content',
      byteCount,
      responseSha256,
      'message content is neither text nor text parts',
    );
  }
  return {
    text,
    reportedModelId: typeof root.model === 'string' ? root.model : null,
    providerRequestId:
      typeof root.id === 'string' ? root.id : headerRequestId,
    usage: usageFrom(root.usage),
  };
}

/**
 * Perform exactly one HTTP attempt and return its wire outcome. HTTP
 * error statuses are RETURNED (the transport classifies them); network
 * failures, deadline expiry, cancellation, and malformed success
 * envelopes are THROWN as typed TransportErrors.
 */
export async function executeHttpAttempt(
  input: HttpAttemptInput,
  deps: HttpCoreDeps = {},
): Promise<HttpAttemptOutcome> {
  const fetchImpl = deps.fetchImpl ?? defaultFetch;
  const nowMs = deps.nowMs ?? Date.now;
  const controller = new AbortController();
  let deadlineFired = false;
  let callerAborted = false;
  const timer = setTimeout(() => {
    deadlineFired = true;
    controller.abort();
  }, Math.max(1, input.deadlineMs));
  const onCallerAbort = () => {
    callerAborted = true;
    controller.abort();
  };
  if (input.signal) {
    if (input.signal.aborted) {
      clearTimeout(timer);
      throw new TransportError(
        'TRANSPORT_CANCELLED',
        'The operation was cancelled by the caller before the provider request was dispatched.',
        { cancelled: true },
      );
    }
    input.signal.addEventListener('abort', onCallerAbort, { once: true });
  }

  let totalBytes = 0;
  const hashChunks: Uint8Array[] = [];
  const noteChunk = (chunk: Uint8Array): void => {
    totalBytes += chunk.byteLength;
    hashChunks.push(chunk);
    if (totalBytes > MAX_RESPONSE_BYTES) {
      controller.abort();
    }
  };
  const bodyHash = (): string => {
    const all = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of hashChunks) {
      all.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return sha256Hex(all);
  };

  try {
    let response: FetchResponseLike;
    try {
      response = await fetchImpl(input.url, {
        method: 'POST',
        headers: input.headers,
        body: input.bodyText,
        signal: controller.signal,
        redirect: 'manual',
      });
    } catch (err) {
      throw classifyFetchFailure(err, { deadlineFired, callerAborted });
    }

    const headerRequestId = response.headers.get('x-request-id');
    const retryAfterMs = parseRetryAfterMs(
      response.headers.get('retry-after'),
      nowMs(),
    );

    if (!response.body) {
      const emptyHash = sha256Hex(new Uint8Array(0));
      if (response.status >= 200 && response.status < 300) {
        throw malformed('$', 0, emptyHash, 'response has no body');
      }
      return {
        status: response.status,
        retryAfterMs,
        providerRequestId: headerRequestId,
        reportedModelId: null,
        text: null,
        usage: { input_tokens: null, output_tokens: null },
        bodyBytes: 0,
        bodySha256: emptyHash,
      };
    }

    const reader = response.body.getReader();
    const textChunks: string[] = [];
    let streamText = '';
    let streamModel: string | null = null;
    let streamId: string | null = null;
    let streamUsage: { input_tokens: number | null; output_tokens: number | null } = {
      input_tokens: null,
      output_tokens: null,
    };
    let sawDone = false;
    let sawFinish = false;
    let sseBuffer = '';

    const decoder = new TextDecoder('utf-8');
    const handleSseBlock = (block: string): void => {
      for (const line of block.split(/\r?\n/)) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice('data:'.length).trim();
        if (payload === '[DONE]') {
          sawDone = true;
          continue;
        }
        if (!payload) continue;
        let chunk: Record<string, unknown>;
        try {
          chunk = JSON.parse(payload) as Record<string, unknown>;
        } catch {
          throw malformed(
            'stream.chunk',
            totalBytes,
            bodyHash(),
            'a stream chunk is not valid JSON',
          );
        }
        if (typeof chunk.model === 'string') streamModel = chunk.model;
        if (typeof chunk.id === 'string') streamId = chunk.id;
        if (chunk.usage) streamUsage = usageFrom(chunk.usage);
        const choices = chunk.choices;
        if (Array.isArray(choices) && choices.length > 0) {
          const first = choices[0] as Record<string, unknown>;
          const delta = first.delta as Record<string, unknown> | undefined;
          if (delta && typeof delta.content === 'string') {
            streamText += delta.content;
          }
          if (typeof first.finish_reason === 'string') sawFinish = true;
        }
      }
    };

    for (;;) {
      let read: { done: boolean; value?: Uint8Array };
      try {
        read = await reader.read();
      } catch (err) {
        // Headers already arrived: the request was submitted and its
        // completion is now unknowable unless the caller cancelled.
        if (callerAborted) {
          throw new TransportError(
            'TRANSPORT_CANCELLED',
            'The operation was cancelled by the caller while the provider response was streaming.',
            { cancelled: true },
          );
        }
        throw new TransportError(
          'TRANSPORT_SUBMITTED_UNRESOLVED',
          deadlineFired
            ? 'The provider request deadline expired while the response was in flight. Completion is unknown; the request is not assumed failed and is not replayed automatically.'
            : 'The provider connection broke while the response was in flight. Completion is unknown; the request is not assumed failed and is not replayed automatically.',
          { unknownCompletion: true, httpStatus: response.status },
        );
      }
      if (read.done) break;
      const chunk = read.value as Uint8Array;
      noteChunk(chunk);
      if (totalBytes > MAX_RESPONSE_BYTES) {
        throw malformed('$', totalBytes, bodyHash(), 'response exceeds the maximum in-memory size');
      }
      if (input.stream && response.status >= 200 && response.status < 300) {
        sseBuffer += decoder.decode(chunk, { stream: true });
        let boundary = sseBuffer.indexOf('\n\n');
        while (boundary >= 0) {
          handleSseBlock(sseBuffer.slice(0, boundary));
          sseBuffer = sseBuffer.slice(boundary + 2);
          boundary = sseBuffer.indexOf('\n\n');
        }
      } else {
        textChunks.push(decoder.decode(chunk, { stream: true }));
      }
    }
    const responseSha256 = bodyHash();

    if (response.status < 200 || response.status >= 300) {
      // Error bodies are hashed and counted only; never parsed for text.
      return {
        status: response.status,
        retryAfterMs,
        providerRequestId: headerRequestId,
        reportedModelId: null,
        text: null,
        usage: { input_tokens: null, output_tokens: null },
        bodyBytes: totalBytes,
        bodySha256: responseSha256,
      };
    }

    if (input.stream) {
      if (sseBuffer.trim().length > 0) handleSseBlock(sseBuffer);
      if (!sawDone && !sawFinish) {
        // A partial stream is not a completed response: never hand the
        // engine a truncated answer dressed as success.
        throw new TransportError(
          'TRANSPORT_SUBMITTED_UNRESOLVED',
          'The provider stream ended without a completion marker after a partial response. Completion is unknown; the partial output was discarded, not returned as a result.',
          {
            unknownCompletion: true,
            httpStatus: response.status,
            parseDiagnostics: {
              schemaPath: 'stream',
              byteCount: totalBytes,
              responseSha256,
            },
          },
        );
      }
      return {
        status: response.status,
        retryAfterMs,
        providerRequestId: streamId ?? headerRequestId,
        reportedModelId: streamModel,
        text: streamText,
        usage: streamUsage,
        bodyBytes: totalBytes,
        bodySha256: responseSha256,
      };
    }

    const bodyText = textChunks.join('') + decoder.decode();
    const parsed = parseChatCompletionEnvelope(
      bodyText,
      totalBytes,
      responseSha256,
      headerRequestId,
    );
    return {
      status: response.status,
      retryAfterMs,
      providerRequestId: parsed.providerRequestId,
      reportedModelId: parsed.reportedModelId,
      text: parsed.text,
      usage: parsed.usage,
      bodyBytes: totalBytes,
      bodySha256: responseSha256,
    };
  } finally {
    clearTimeout(timer);
    if (input.signal) input.signal.removeEventListener('abort', onCallerAbort);
  }
}
