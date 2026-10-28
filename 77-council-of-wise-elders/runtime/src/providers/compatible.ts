/**
 * OpenAI-compatible HTTP transport (CWE-009; directive Sections 13
 * and 15). One transport instance is bound to ONE pinned CWE-008
 * selection snapshot and ONE configured endpoint. It works for any
 * configured OpenAI-compatible endpoint (OpenRouter, 9Router remote,
 * a direct provider gateway, a local daemon's compatible surface)
 * without assuming URLs, aliases, or model names: the endpoint comes
 * from the binding, the wire model comes from the pinned selection.
 *
 * Guarantees held here:
 * - Route pinning: the request body is built once per operation from
 *   the frozen selection; the model string is byte-identical to the
 *   selection's pinned model (fixed routes) or pinned route reference
 *   (combinations, whose router may resolve only to approved members).
 *   A TransportRequest naming any other route or model is refused
 *   before dispatch. There is no substitution, no cascade, and no
 *   fallback chain in this module.
 * - Resolution honesty: after every completed response, the transport
 *   reports what actually happened through evaluateRouteResolution
 *   (the CWE-008 guard). A refused resolution returns NO model text.
 *   Identity levels come from structured evidence only, and a probe
 *   never claims resolved or qualified identity (Section 13.4).
 * - Deadlines: the route's verified deadline where the binding
 *   carries one, else the clearly displayed initial default of 600
 *   seconds per operation (Section 15.8), enforced separately from
 *   operation leases and shared across the operation's attempts.
 * - Retries: transient network/429/5xx only. In transport retry mode,
 *   at most one retry per attempted network operation, reserved in the
 *   CWE-004 budget ledger as a transport_retry so it counts toward
 *   the session's 50-request ceiling and the 8-retry session ceiling
 *   the ledger enforces. In engine retry mode the transport performs
 *   one attempt and marks transient errors retryable for the engine's
 *   own bounded loop (which reserves identically). 401/403/404,
 *   invalid auth, missing model, policy denial, and unsupported
 *   endpoint errors stop with no blind retry (Section 15.5).
 * - Uncertain completion: provider_submitted_unresolved is a
 *   first-class attempt state; a timed-out or broken submission keeps
 *   its budget reservation (the engine marks it unknown) and is never
 *   assumed failed or duplicated blindly.
 * - Diagnostics: Section 16.6 governs every record. Attempt records
 *   and the diagnostic sink hold safe metadata only; raw bodies are
 *   memory-only during the attempt and are never persisted, logged,
 *   or exported. The credential value exists only in the in-flight
 *   Authorization header and in the sink's in-memory scan set.
 */

import { canonicalStringify } from '../contracts/index.js';
import type {
  BudgetLedger,
  BudgetReservation,
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from '../cli/host-ports.js';
import { TransportDiagnosticSink } from './diagnostics.js';
import { TransportError } from './errors.js';
import {
  executeHttpAttempt,
  type FetchLike,
  type HttpAttemptOutcome,
} from './http-core.js';
import { mapReasoningToParams, type ReasoningParamStyle } from './reasoning.js';
import {
  deriveIdentityLevel,
  evaluateRouteResolution,
  freezeSelection,
  maxIdentityLevel,
  selectionSha256,
  type CouncilRouteSelection,
  type RouteIdentityLevel,
  type RouteResolutionOutcome,
} from './selection.js';
import { assessEndpoint, type EndpointAssessment } from './url-policy.js';

/** Section 15.8 initial default provider deadline: 600 seconds per operation. */
export const DEFAULT_OPERATION_DEADLINE_MS = 600_000;

/** Default cap on a single retry delay, whatever Retry-After asks for. */
export const DEFAULT_MAX_RETRY_DELAY_MS = 30_000;

/** Fallback backoff when a transient response carries no Retry-After. */
export const DEFAULT_RETRY_BASE_DELAY_MS = 1_000;

export type TransportRetryMode = 'transport' | 'engine' | 'none';

export interface CompatibleTransportBinding {
  /** The pinned CWE-008 selection snapshot this transport serves. */
  selection: CouncilRouteSelection;
  /** Configured provider base URL (authorized configuration path only). */
  baseUrl: string;
  /** Path appended to baseUrl. Default '/chat/completions'. */
  chatCompletionsPath?: string;
  /** Explicit opt-in for plain http to a public endpoint. Default false. */
  allowInsecureRemoteHttp?: boolean;
  /**
   * Host credential resolver path (the CWE-008 pattern): returns the
   * credential VALUE for the in-flight request only. The value is
   * never recorded. Required unless the selection's credential state
   * is not_required.
   */
  credentialResolver?: (selection: CouncilRouteSelection) => Promise<string | null>;
  /**
   * Route-specific verified deadline in milliseconds (Section 15.8),
   * from verified route data. Absent: the initial default applies and
   * is displayed as such.
   */
  verifiedDeadlineMs?: number;
  /** Request the streaming form of the compatible API. Default false. */
  stream?: boolean;
  /** Reasoning parameter style for this endpoint family. Default 'reasoning_effort'. */
  reasoningParamStyle?: ReasoningParamStyle;
  /** Retry ownership. Default: 'transport' when a budget ledger is composed, else 'engine'. */
  retryMode?: TransportRetryMode;
  /** Budget ledger (CWE-004 port). Required in transport retry mode. */
  budget?: BudgetLedger;
  /** Diagnostic sink. Default: a new sink under the default retention policy. */
  diagnostics?: TransportDiagnosticSink;
  /** Observer for route-resolution outcomes (route-change records). */
  onRouteResolution?: (outcome: RouteResolutionOutcome) => void;
  /** Injectable fetch for tests and host embedding. Default: global fetch. */
  fetchImpl?: FetchLike;
  /** Injectable clock (milliseconds) for deadline accounting. */
  nowMs?: () => number;
  /** Injectable sleep for retry delays. Default: real timers. */
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Injectable random source for bounded jitter. Default Math.random. */
  random?: () => number;
  /** Cap on one retry delay. Default DEFAULT_MAX_RETRY_DELAY_MS. */
  maxRetryDelayMs?: number;
}

/** One network attempt, recorded with safe metadata only (Section 16.6). */
export interface TransportAttemptRecord {
  attemptId: string;
  sessionId: string;
  routeId: string;
  routeRevision: number;
  selectionSha256: string;
  /** The exact model string placed on the wire for this attempt. */
  wireModel: string;
  endpointOrigin: string;
  endpointLocality: EndpointAssessment['locality'];
  /** 0 for the initial attempt, 1 for the single permitted retry. */
  retryIndex: 0 | 1;
  /**
   * Attempt state. provider_submitted_unresolved is the transport name
   * for the canonical provider_completion_unknown operation status.
   */
  state:
    | 'accepted'
    | 'failed'
    | 'provider_submitted_unresolved'
    | 'substitution_refused'
    | 'cancelled';
  canonicalOperationStatus:
    | 'accepted'
    | 'failed'
    | 'provider_completion_unknown'
    | 'cancelled';
  httpStatus: number | null;
  providerRequestId: string | null;
  reportedModelId: string | null;
  /** Strongest identity level the structured evidence supports after this attempt. */
  identityLevelAfter: RouteIdentityLevel;
  identityStatement: string | null;
  /** Resolved combination member, when the provider exposed one (T030). */
  combinationMemberResolved: string | null;
  errorCode: string | null;
  deadlineMs: number;
  deadlineSource: 'route_verified' | 'initial_default';
  responseBytes: number | null;
  responseSha256: string | null;
  startedAt: string;
  durationMs: number;
}

export interface TransportDescription {
  routeId: string;
  routeRevision: number;
  providerSlug: string;
  routeKind: CouncilRouteSelection['routeKind'];
  selectionSha256: string;
  endpointOrigin: string;
  endpointLocality: EndpointAssessment['locality'];
  deadlineMs: number;
  deadlineSource: 'route_verified' | 'initial_default';
  /** Human display, for readiness surfaces (Sections 15.8, 17.3). */
  deadlineDisplay: string;
  credentialState: CouncilRouteSelection['credential']['state'];
  /** Precise readiness blocker, or null when the route can be called (T027). */
  readinessBlocker: string | null;
  identityLevelAtBind: RouteIdentityLevel;
  stream: boolean;
}

const MAX_ATTEMPT_RECORDS = 500;

function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(
        new TransportError('TRANSPORT_CANCELLED', 'Cancelled during retry backoff.', {
          cancelled: true,
        }),
      );
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(
        new TransportError('TRANSPORT_CANCELLED', 'Cancelled during retry backoff.', {
          cancelled: true,
        }),
      );
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Classify an HTTP error status (Section 15.5). Returns a typed error. */
export function classifyHttpStatus(
  status: number,
  retryAfterMs: number | null,
): TransportError {
  if (status === 401 || status === 403) {
    return new TransportError(
      'TRANSPORT_AUTH_FAILED',
      `The provider refused authorization (HTTP ${status}). Authentication and policy failures are never retried blindly.`,
      { httpStatus: status },
    );
  }
  if (status === 404) {
    return new TransportError(
      'TRANSPORT_NOT_FOUND',
      'The provider returned 404: the configured endpoint or the pinned model does not exist there. This is never retried blindly.',
      { httpStatus: status },
    );
  }
  if (status >= 300 && status < 400) {
    return new TransportError(
      'TRANSPORT_REDIRECT_REFUSED',
      `The provider endpoint answered with a redirect (HTTP ${status}). Redirects are never followed, so a configured endpoint cannot move a request or its credential to another origin.`,
      { httpStatus: status },
    );
  }
  if (status === 429) {
    return new TransportError(
      'TRANSPORT_RATE_LIMITED',
      'The provider rate-limited the request (HTTP 429).',
      { httpStatus: status, retryAfterMs, retryable: true },
    );
  }
  if (status >= 500 && status <= 599) {
    return new TransportError(
      'TRANSPORT_PROVIDER_ERROR',
      `The provider returned a server error (HTTP ${status}).`,
      { httpStatus: status, retryAfterMs, retryable: true },
    );
  }
  return new TransportError(
    'TRANSPORT_BAD_REQUEST',
    `The provider rejected the request (HTTP ${status}). Client errors are never retried blindly.`,
    { httpStatus: status, retryAfterMs },
  );
}

function asFinal(error: TransportError): TransportError {
  if (!error.retryable) return error;
  return new TransportError(error.code, error.message, {
    httpStatus: error.httpStatus,
    retryAfterMs: error.retryAfterMs,
    parseDiagnostics: error.parseDiagnostics,
    retryable: false,
    unknownCompletion: error.unknownCompletion,
    cancelled: error.cancelled,
    resolution: error.resolution,
  });
}

export class CompatibleHttpTransport implements ModelTransport {
  readonly selection: CouncilRouteSelection;
  readonly selectionSha256: string;
  private readonly endpoint: EndpointAssessment;
  private readonly binding: CompatibleTransportBinding;
  private readonly diagnostics: TransportDiagnosticSink;
  private readonly retryMode: TransportRetryMode;
  private readonly deadlineMs: number;
  private readonly deadlineSource: 'route_verified' | 'initial_default';
  private readonly attemptLog: TransportAttemptRecord[] = [];
  private readonly resolutions: RouteResolutionOutcome[] = [];
  private callSequence = 0;

  constructor(binding: CompatibleTransportBinding) {
    this.binding = binding;
    // Freeze the pin at construction: the caller's object may be
    // reused or mutated later; the transport's route cannot move.
    this.selection = freezeSelection(binding.selection);
    this.selectionSha256 = selectionSha256(this.selection);
    this.endpoint = assessEndpoint(binding.baseUrl, {
      chatCompletionsPath: binding.chatCompletionsPath,
      allowInsecureRemoteHttp: binding.allowInsecureRemoteHttp,
    });
    this.diagnostics = binding.diagnostics ?? new TransportDiagnosticSink();
    this.retryMode =
      binding.retryMode ?? (binding.budget ? 'transport' : 'engine');
    if (this.retryMode === 'transport' && !binding.budget) {
      throw new TransportError(
        'TRANSPORT_CONFIG_INVALID',
        'Transport retry mode requires the CWE-004 budget ledger, so every retry is reserved and counted toward the session ceilings.',
      );
    }
    if (
      this.selection.credential.state === 'present' &&
      !binding.credentialResolver
    ) {
      throw new TransportError(
        'TRANSPORT_CONFIG_INVALID',
        `Route ${this.selection.routeId} requires a credential, but no host credential resolver was composed. The transport never invents or borrows a credential.`,
      );
    }
    if (binding.verifiedDeadlineMs !== undefined) {
      if (
        !Number.isFinite(binding.verifiedDeadlineMs) ||
        binding.verifiedDeadlineMs <= 0
      ) {
        throw new TransportError(
          'TRANSPORT_CONFIG_INVALID',
          'A verified route deadline must be a positive number of milliseconds.',
        );
      }
      this.deadlineMs = binding.verifiedDeadlineMs;
      this.deadlineSource = 'route_verified';
    } else {
      this.deadlineMs = DEFAULT_OPERATION_DEADLINE_MS;
      this.deadlineSource = 'initial_default';
    }
  }

  /** Readiness and identity description for operator surfaces. */
  describe(): TransportDescription {
    return {
      routeId: this.selection.routeId,
      routeRevision: this.selection.routeRevision,
      providerSlug: this.selection.providerSlug,
      routeKind: this.selection.routeKind,
      selectionSha256: this.selectionSha256,
      endpointOrigin: this.endpoint.origin,
      endpointLocality: this.endpoint.locality,
      deadlineMs: this.deadlineMs,
      deadlineSource: this.deadlineSource,
      deadlineDisplay:
        this.deadlineSource === 'route_verified'
          ? `${Math.round(this.deadlineMs / 1000)} seconds (route verified)`
          : '600 seconds (initial default)',
      credentialState: this.selection.credential.state,
      readinessBlocker: this.readinessBlocker(),
      identityLevelAtBind: this.selection.identityLevel,
      stream: this.binding.stream ?? false,
    };
  }

  /** T027: a missing credential is a precise blocker, never a borrowed one. */
  private readinessBlocker(): string | null {
    const credential = this.selection.credential;
    if (credential.state !== 'absent') return null;
    const names =
      credential.checked.length > 0
        ? credential.checked
        : [credential.envVar ?? 'the provider credential'];
    return (
      `Credential missing for route ${this.selection.routeId} (provider ${this.selection.providerSlug}). ` +
      `Checked: ${names.join(', ')}. ` +
      'Add the credential through the host credential store; the transport never borrows another credential.'
    );
  }

  /** Safe attempt records, in order. Bodies and credentials are never present. */
  attempts(): readonly TransportAttemptRecord[] {
    return this.attemptLog;
  }

  /** Route-resolution outcomes reported by this transport, in order. */
  routeResolutions(): readonly RouteResolutionOutcome[] {
    return this.resolutions;
  }

  /** The wire model for the pinned selection. Byte-identical by construction. */
  private wireModel(): string {
    if (this.selection.routeKind === 'combination') {
      // The combination's own pinned route reference is the wire alias;
      // the router may resolve it only to an approved member, which the
      // resolution guard verifies from the structured report.
      return this.selection.requestedRoute;
    }
    const model = this.selection.requestedModelOrAlias;
    if (!model) {
      throw new TransportError(
        'TRANSPORT_CONFIG_INVALID',
        `Fixed-model selection for route ${this.selection.routeId} carries no requested model. The transport cannot invent one.`,
      );
    }
    return model;
  }

  /**
   * Refuse any request that does not name the pinned route and model.
   * Runs before credential resolution, budget activity, and dispatch.
   */
  private assertPinning(request: TransportRequest): void {
    if (selectionSha256(this.selection) !== this.selectionSha256) {
      throw new TransportError(
        'TRANSPORT_SELECTION_MUTATED',
        'The pinned selection snapshot changed after the transport was constructed. Dispatch refused; a selection moves only through a new reviewed selection and revision.',
      );
    }
    if (
      request.route_id !== this.selection.routeId ||
      request.model_policy.route_id !== this.selection.routeId
    ) {
      throw new TransportError(
        'TRANSPORT_ROUTE_MISMATCH',
        `The request names route ${request.route_id}, but this transport is pinned to route ${this.selection.routeId}. The selected route is never silently replaced.`,
      );
    }
    if (this.selection.routeKind === 'fixed_model') {
      const requested = request.model_policy.requested_model_id;
      if (requested !== null && requested !== this.selection.requestedModelOrAlias) {
        throw new TransportError(
          'TRANSPORT_ROUTE_MISMATCH',
          `The request names model ${requested}, but the pinned selection for route ${this.selection.routeId} is ${this.selection.requestedModelOrAlias}. The selected model is never silently replaced.`,
        );
      }
    }
  }

  private async resolveCredential(): Promise<string | null> {
    const credential = this.selection.credential;
    if (credential.state === 'absent') {
      throw new TransportError(
        'TRANSPORT_CREDENTIAL_MISSING',
        this.readinessBlocker() ?? 'Credential missing for the pinned route.',
      );
    }
    if (credential.state === 'not_required') return null;
    const value = await this.binding.credentialResolver!(this.selection);
    if (value === null || value === '') {
      throw new TransportError(
        'TRANSPORT_CREDENTIAL_MISSING',
        `The host credential resolver returned no credential for route ${this.selection.routeId}, although the selection records one as present${credential.envVar ? ` (${credential.envVar})` : ''}. The transport never borrows another credential.`,
      );
    }
    return value;
  }

  /** Build the request body once per operation: retries send identical bytes. */
  private buildBody(request: TransportRequest, wireModel: string): string {
    const reasoning = mapReasoningToParams(
      this.selection.reasoning,
      this.binding.reasoningParamStyle ?? 'reasoning_effort',
    );
    const stream = this.binding.stream ?? false;
    const body: Record<string, unknown> = {
      model: wireModel,
      messages: [
        { role: 'system', content: request.system },
        { role: 'user', content: canonicalStringify(request.input) },
      ],
      stream,
      ...reasoning.params,
    };
    if (stream) body.stream_options = { include_usage: true };
    // Deliberately absent, for every route (T032): no tools, no
    // tool_choice, no temperature or vendor extensions. A text-only
    // model succeeds through exactly this shape.
    return canonicalStringify(body);
  }

  /** Bounded jittered retry delay: honors Retry-After, capped, never negative. */
  private retryDelayMs(retryAfterMs: number | null): number {
    const cap = this.binding.maxRetryDelayMs ?? DEFAULT_MAX_RETRY_DELAY_MS;
    const base = Math.min(retryAfterMs ?? DEFAULT_RETRY_BASE_DELAY_MS, cap);
    const random = this.binding.random ?? Math.random;
    // Equal jitter: half fixed, half random; deterministic under an
    // injected random source.
    return Math.floor(base / 2 + random() * (base / 2));
  }

  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.assertPinning(request);
    const credentialValue = await this.resolveCredential();
    const wireModel = this.wireModel();
    const bodyText = this.buildBody(request, wireModel);
    const nowMs = this.binding.nowMs ?? Date.now;
    const deadlineEnd = nowMs() + this.deadlineMs;
    this.callSequence += 1;
    const callSeq = this.callSequence;

    const headers: Record<string, string> = {
      'content-type': 'application/json',
      accept: this.binding.stream ? 'text/event-stream' : 'application/json',
    };
    if (credentialValue !== null) {
      headers.authorization = `Bearer ${credentialValue}`;
      this.diagnostics.registerSensitiveValue(credentialValue);
    }

    let retryReservation: BudgetReservation | null = null;
    try {
      for (let retryIndex = 0 as 0 | 1; ; retryIndex = 1) {
        const startedMs = nowMs();
        const remainingMs = deadlineEnd - startedMs;
        if (remainingMs <= 0) {
          // Attempts remain only when a definitive transient failure is
          // already recorded; that failure, not a guess, is the result.
          if (retryReservation && this.binding.budget) {
            this.binding.budget.release(retryReservation);
            retryReservation = null;
          }
          throw new TransportError(
            'TRANSPORT_SUBMITTED_UNRESOLVED',
            'The operation deadline was exhausted before a further attempt could be dispatched.',
            { unknownCompletion: false },
          );
        }

        let outcome: HttpAttemptOutcome | null = null;
        let failure: TransportError | null = null;
        try {
          outcome = await executeHttpAttempt(
            {
              url: this.endpoint.url,
              headers,
              bodyText,
              stream: this.binding.stream ?? false,
              deadlineMs: remainingMs,
              signal: request.signal,
            },
            { fetchImpl: this.binding.fetchImpl, nowMs },
          );
        } catch (err) {
          failure =
            err instanceof TransportError
              ? err
              : new TransportError(
                  'TRANSPORT_SUBMITTED_UNRESOLVED',
                  'The provider request failed in an unclassified way after submission. Completion is unknown.',
                  { unknownCompletion: true },
                );
        }

        if (outcome && (outcome.status < 200 || outcome.status >= 300)) {
          failure = classifyHttpStatus(outcome.status, outcome.retryAfterMs);
          this.diagnostics.recordSafe({
            kind: 'http_error',
            errorCode: failure.code,
            schemaPath: null,
            byteCount: outcome.bodyBytes,
            responseSha256: outcome.bodySha256,
            sessionId: request.session_id,
            routeId: this.selection.routeId,
            note: `HTTP ${outcome.status}`,
          });
        }

        if (outcome && outcome.status >= 200 && outcome.status < 300) {
          // The retry, when one happened, is consumed either way: the
          // request was actually dispatched.
          if (retryReservation && this.binding.budget) {
            this.binding.budget.commit(retryReservation);
            retryReservation = null;
          }
          const resolution = evaluateRouteResolution(this.selection, {
            source: 'explicit_route',
            attemptedModelId:
              this.selection.routeKind === 'combination' ? null : wireModel,
            reportedModelId: outcome.reportedModelId,
          });
          this.resolutions.push(resolution);
          this.binding.onRouteResolution?.(resolution);
          this.recordAttempt(request, {
            retryIndex,
            startedMs,
            nowMs,
            outcome,
            failure: null,
            resolution,
            wireModel,
            callSeq,
          });
          if (resolution.outcome === 'refused') {
            const refusedEvent = resolution.events.find(
              (e) => e.type === 'substitution_refused',
            );
            throw new TransportError(
              'TRANSPORT_ROUTE_REFUSED',
              `The provider resolution for route ${this.selection.routeId} was refused: ${refusedEvent && 'reason' in refusedEvent ? refusedEvent.reason : 'the resolution did not match the pinned selection.'} The response text was not returned.`,
              { resolution },
            );
          }
          return {
            text: outcome.text as string,
            provider_request_id: outcome.providerRequestId,
            reported_model_id: outcome.reportedModelId,
            usage: outcome.usage,
          };
        }

        // Failure path.
        const err = failure as TransportError;
        if (retryReservation && this.binding.budget) {
          // The retry attempt was dispatched; its outcome (failure,
          // unknown) still consumed the request.
          this.binding.budget.commit(retryReservation);
          retryReservation = null;
        }
        this.recordAttempt(request, {
          retryIndex,
          startedMs,
          nowMs,
          outcome,
          failure: err,
          resolution: null,
          wireModel,
          callSeq,
        });
        if (err.parseDiagnostics) {
          this.diagnostics.recordSafe({
            kind: 'parse_failure',
            errorCode: err.code,
            schemaPath: err.parseDiagnostics.schemaPath,
            byteCount: err.parseDiagnostics.byteCount,
            responseSha256: err.parseDiagnostics.responseSha256,
            sessionId: request.session_id,
            routeId: this.selection.routeId,
            note: null,
          });
        }

        const transient = err.retryable && !err.unknownCompletion && !err.cancelled;
        if (!transient || this.retryMode === 'none') throw asFinal(err);
        if (retryIndex === 1) throw asFinal(err);
        if (this.retryMode === 'engine') {
          // One attempt only; the engine performs and reserves the retry.
          throw err;
        }

        // Transport retry mode: reserve the retry in the budget ledger
        // BEFORE dispatch, so it counts toward the 50-request session
        // ceiling and the 8-retry session ceiling (Section 15.9).
        const budget = this.binding.budget!;
        try {
          retryReservation = budget.reserve({
            session_id: request.session_id,
            operation_key: `${this.selection.routeId}:${request.session_id}:call-${callSeq}:transport-retry-1`,
            kind: 'transport_retry',
          });
        } catch {
          throw new TransportError(
            'TRANSPORT_BUDGET_EXHAUSTED',
            `The session budget does not allow a transport retry for route ${this.selection.routeId}. The original failure stands: ${err.message}`,
            { httpStatus: err.httpStatus },
          );
        }
        const delay = this.retryDelayMs(err.retryAfterMs);
        if (deadlineEnd - nowMs() - delay <= 0) {
          budget.release(retryReservation);
          retryReservation = null;
          throw asFinal(err);
        }
        const sleep = this.binding.sleep ?? defaultSleep;
        try {
          await sleep(delay, request.signal);
        } catch (sleepErr) {
          budget.release(retryReservation);
          retryReservation = null;
          throw sleepErr;
        }
        // Loop for the single permitted retry with identical bytes.
      }
    } finally {
      if (credentialValue !== null) this.diagnostics.clearSensitiveValues();
    }
  }

  private recordAttempt(
    request: TransportRequest,
    args: {
      retryIndex: 0 | 1;
      startedMs: number;
      nowMs: () => number;
      outcome: HttpAttemptOutcome | null;
      failure: TransportError | null;
      resolution: RouteResolutionOutcome | null;
      wireModel: string;
      callSeq: number;
    },
  ): void {
    const { outcome, failure, resolution } = args;
    const evidenceLevel = deriveIdentityLevel({
      transportProbed: true,
      reportedModelId: outcome?.reportedModelId ?? null,
      identityVerification: null,
      evaluation: null,
    });
    let state: TransportAttemptRecord['state'] = 'failed';
    if (resolution?.outcome === 'refused') state = 'substitution_refused';
    else if (failure?.unknownCompletion) state = 'provider_submitted_unresolved';
    else if (failure?.cancelled) state = 'cancelled';
    else if (outcome && outcome.status >= 200 && outcome.status < 300) {
      state = 'accepted';
    }
    const canonicalOperationStatus: TransportAttemptRecord['canonicalOperationStatus'] =
      state === 'provider_submitted_unresolved'
        ? 'provider_completion_unknown'
        : state === 'accepted'
          ? 'accepted'
          : state === 'cancelled'
            ? 'cancelled'
            : 'failed';
    const memberEvent = resolution?.events.find(
      (e) => e.type === 'combination_member_resolved',
    );
    const record: TransportAttemptRecord = {
      attemptId: `${this.selection.routeId}:${request.session_id}:call-${args.callSeq}:attempt-${args.retryIndex}`,
      sessionId: request.session_id,
      routeId: this.selection.routeId,
      routeRevision: this.selection.routeRevision,
      selectionSha256: this.selectionSha256,
      wireModel: args.wireModel,
      endpointOrigin: this.endpoint.origin,
      endpointLocality: this.endpoint.locality,
      retryIndex: args.retryIndex,
      state,
      canonicalOperationStatus,
      httpStatus: outcome?.status ?? failure?.httpStatus ?? null,
      providerRequestId: outcome?.providerRequestId ?? null,
      reportedModelId: outcome?.reportedModelId ?? null,
      identityLevelAfter:
        state === 'accepted'
          ? maxIdentityLevel(
              maxIdentityLevel(this.selection.identityLevel, evidenceLevel),
              resolution?.identityLevel ?? 'configured',
            )
          : this.selection.identityLevel,
      identityStatement: resolution?.identityStatement ?? null,
      combinationMemberResolved:
        memberEvent && memberEvent.type === 'combination_member_resolved'
          ? memberEvent.memberModelId
          : null,
      errorCode: failure?.code ?? null,
      deadlineMs: this.deadlineMs,
      deadlineSource: this.deadlineSource,
      responseBytes:
        outcome?.bodyBytes ?? failure?.parseDiagnostics?.byteCount ?? null,
      responseSha256:
        outcome?.bodySha256 ?? failure?.parseDiagnostics?.responseSha256 ?? null,
      startedAt: new Date(args.startedMs).toISOString(),
      durationMs: Math.max(0, args.nowMs() - args.startedMs),
    };
    this.attemptLog.push(record);
    if (this.attemptLog.length > MAX_ATTEMPT_RECORDS) {
      this.attemptLog.splice(0, this.attemptLog.length - MAX_ATTEMPT_RECORDS);
    }
  }
}

/** Factory mirroring the other council module constructors. */
export function createCompatibleTransport(
  binding: CompatibleTransportBinding,
): CompatibleHttpTransport {
  return new CompatibleHttpTransport(binding);
}

/**
 * Registry entries for the CWE-004 host composition
 * (createLocalHost's `transports` option and MapTransportRegistry):
 * each transport registers under exactly its pinned route id. This is
 * the registry re-point the CWE-008 acceptance flagged: hosts register
 * these pinned transports instead of any unpinned adapter, so the
 * engine's route lookup can only ever reach the selected route.
 */
export function pinnedTransportEntries(
  transports: CompatibleHttpTransport[],
): Array<{ routeId: string; transport: CompatibleHttpTransport }> {
  return transports.map((transport) => ({
    routeId: transport.selection.routeId,
    transport,
  }));
}
