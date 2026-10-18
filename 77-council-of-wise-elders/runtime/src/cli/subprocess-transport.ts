/**
 * Platform-safe bounded subprocess transport (WER-008 slice).
 *
 * This transport consumes the WER-006 frozen route snapshot
 * (`wise-elders.route-snapshot/v1`) instead of re-deriving route,
 * model, effort or profile from a mutable global. The snapshot hash is
 * verified before anything is spawned; a tampered or foreign-schema
 * snapshot refuses dispatch.
 *
 * Laws:
 * - Prompt content goes to the child on STDIN only. The launch plan is
 *   an argument vector built from the executable path and the pinned
 *   CLI flags; prompt text is never interpolated into any argument and
 *   never into a shell string. (The one cmd.exe `/c` payload that exists
 *   on Windows is built from the shim path and those same flags.)
 * - Bounds: stdout over `maxStdoutBytes` refuses the operation and kills
 *   the tree; stderr is truncated at its own bound. Both counts are
 *   BYTE counts, not JavaScript string lengths.
 * - Deadline and abort both terminate the WHOLE child process tree.
 * - The operationId/attemptId are recorded BEFORE launch. A timeout,
 *   abort or non-zero exit is `potentially_dispatched`, never
 *   safe-to-retry; only a spawn error (no provider work possible) is
 *   `failed_definitely`.
 *
 * Scope honesty: the resolver and this transport are proven with
 * simulated shims and local Linux/macOS subprocesses. Native Windows
 * host execution, real provider calls and live transport capture are
 * deferred (WER-027) and are NOT claimed here.
 */

import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { canonicalStringify } from '../contracts/index.js';
import {
  ROUTE_SNAPSHOT_SCHEMA,
  verifyRouteSnapshotHash,
  type CouncilRouteSnapshot,
} from '../providers/route-snapshot.js';
import {
  ExecutableResolutionError,
  resolveCommand,
  type ResolvedInvocation,
  type ResolverPlatform,
} from './executable-resolver.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from './host-ports.js';
import {
  OperationAttemptLedger,
  type AttemptRecord,
} from './operation-attempts.js';

export const DEFAULT_SUBPROCESS_TIMEOUT_MS = 600_000;
export const DEFAULT_MAX_STDOUT_BYTES = 8 * 1024 * 1024;
export const DEFAULT_MAX_STDERR_BYTES = 64 * 1024;

export type SubprocessTransportErrorCode =
  | 'COUNCIL_ROUTE_SNAPSHOT_REFUSED'
  | 'COUNCIL_ROUTE_PIN_MISMATCH'
  | 'COUNCIL_TRANSPORT_SPAWN_FAILED'
  | 'COUNCIL_TRANSPORT_TIMEOUT'
  | 'COUNCIL_TRANSPORT_CANCELLED'
  | 'COUNCIL_TRANSPORT_OUTPUT_BOUND'
  | 'COUNCIL_TRANSPORT_EXIT_FAILED'
  | 'COUNCIL_TRANSPORT_EMPTY_OUTPUT';

/** The exact per-call contract frozen from the snapshot. */
export interface PinnedCallProfile {
  routeId: string;
  /** Configured model id for a fixed route; null for a combination alias. */
  modelId: string | null;
  alias: string | null;
  /** Applied reasoning level; null means nothing was applied. */
  effort: string | null;
  configProfile: string;
  snapshotSha256: string;
}

/** Verify schema and pin before any dispatch. */
export function assertDispatchableSnapshot(snapshot: CouncilRouteSnapshot): void {
  if (!snapshot || typeof snapshot !== 'object') {
    throw new TransportRouteError(
      'COUNCIL_ROUTE_SNAPSHOT_REFUSED',
      'No frozen route snapshot was supplied; dispatch is refused rather than defaulted.',
    );
  }
  if (snapshot.schema !== ROUTE_SNAPSHOT_SCHEMA) {
    throw new TransportRouteError(
      'COUNCIL_ROUTE_SNAPSHOT_REFUSED',
      `Route snapshot schema ${JSON.stringify(snapshot.schema)} is not ${JSON.stringify(ROUTE_SNAPSHOT_SCHEMA)}; dispatch is refused.`,
    );
  }
  if (!verifyRouteSnapshotHash(snapshot)) {
    throw new TransportRouteError(
      'COUNCIL_ROUTE_SNAPSHOT_REFUSED',
      'Route snapshot failed verifyRouteSnapshotHash; the pin body and published hash disagree, so nothing is dispatched.',
    );
  }
}

/** Freeze the route/model/effort/profile for every call of this transport. */
export function pinCallProfile(snapshot: CouncilRouteSnapshot): PinnedCallProfile {
  assertDispatchableSnapshot(snapshot);
  const configured = snapshot.identity.configured;
  return Object.freeze({
    routeId: snapshot.selection.routeId,
    modelId: configured.modelId,
    alias: configured.alias,
    effort: snapshot.reasoning.applied,
    configProfile: configured.configProfile,
    snapshotSha256: snapshot.snapshotSha256,
  });
}

export class TransportRouteError extends Error {
  readonly code: SubprocessTransportErrorCode;
  readonly retryable = false;
  readonly unknownCompletion = false;
  constructor(code: SubprocessTransportErrorCode, message: string) {
    super(message);
    this.name = 'TransportRouteError';
    this.code = code;
  }
}

export class BoundedSubprocessError extends Error {
  readonly code: SubprocessTransportErrorCode;
  readonly retryable: boolean;
  readonly unknownCompletion: boolean;
  readonly disposition: 'failed_definitely' | 'potentially_dispatched';
  readonly operationId: string;
  readonly attemptId: string;
  constructor(
    code: SubprocessTransportErrorCode,
    message: string,
    options: {
      operationId: string;
      attemptId: string;
      disposition: 'failed_definitely' | 'potentially_dispatched';
      retryable?: boolean;
    },
  ) {
    super(message);
    this.name = 'BoundedSubprocessError';
    this.code = code;
    this.unknownCompletion = options.disposition === 'potentially_dispatched';
    this.retryable = options.retryable ?? false;
    this.disposition = options.disposition;
    this.operationId = options.operationId;
    this.attemptId = options.attemptId;
  }
}

export interface SubprocessTransportOptions {
  /** The frozen WER-006 snapshot this transport is bound to. */
  snapshot: CouncilRouteSnapshot;
  /** Command name or path; resolved structurally (no shell, no WSL). */
  command: string;
  /** Static CLI arguments. Never prompt content. */
  args?: string[];
  /**
   * Flag names used to carry the pinned model/effort when the target
   * accepts them (for example '--model'). Omit for harnesses that own
   * their own model selection; the pin is still enforced on the request.
   */
  modelFlag?: string | null;
  effortFlag?: string | null;
  /** Environment captured ONCE at construction, then frozen. */
  env?: NodeJS.ProcessEnv;
  /** Pre-resolved launch plan; bypasses resolution when supplied. */
  invocation?: ResolvedInvocation;
  timeoutMs?: number;
  maxStdoutBytes?: number;
  maxStderrBytes?: number;
  /** Injected ledger so a host can persist the same records. */
  ledger?: OperationAttemptLedger;
  /** Deterministic attempt ids for tests; defaults to a1, a2, ... */
  attemptIdFactory?: () => string;
  spawnImpl?: typeof spawn;
  killTreeImpl?: (child: ChildProcess) => void;
  platform?: ResolverPlatform;
  now?: () => Date;
}

interface HarnessResultEnvelope {
  result?: unknown;
  is_error?: unknown;
  subtype?: unknown;
  session_id?: unknown;
  model?: unknown;
  modelUsage?: unknown;
  usage?: unknown;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Deterministic operation identity for one logical provider request. */
export function operationIdFor(request: TransportRequest): string {
  return `${request.session_id}:${request.purpose}:r${request.round ?? 0}:${request.seat_id}`;
}

/** Terminate a child AND its descendants. */
export function terminateProcessTree(
  child: ChildProcess,
  platform: ResolverPlatform = process.platform,
): void {
  const pid = child.pid;
  if (pid === undefined || pid === null) {
    try {
      child.kill('SIGKILL');
    } catch {
      // Already gone.
    }
    return;
  }
  if (platform === 'win32') {
    // taskkill is an executable, never a shell string. /T walks the tree.
    try {
      spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
      return;
    } catch {
      // Fall through to a single-process kill.
    }
  } else {
    try {
      // The child is a process-group leader (detached), so the negative
      // pid reaches every descendant.
      process.kill(-pid, 'SIGKILL');
      return;
    } catch {
      // Fall through to a single-process kill.
    }
  }
  try {
    child.kill('SIGKILL');
  } catch {
    // Already gone.
  }
}

export class BoundedSubprocessTransport implements ModelTransport {
  readonly ledger: OperationAttemptLedger;
  readonly pinnedProfile: PinnedCallProfile;

  private readonly options: SubprocessTransportOptions;
  private readonly childEnv: Readonly<NodeJS.ProcessEnv>;
  private readonly pinnedArgs: readonly string[];
  private readonly timeoutMs: number;
  private readonly maxStdoutBytes: number;
  private readonly maxStderrBytes: number;
  private attemptCounter = 0;
  private readonly platform: ResolverPlatform;

  constructor(options: SubprocessTransportOptions) {
    this.options = options;
    this.pinnedProfile = pinCallProfile(options.snapshot);
    this.ledger = options.ledger ?? new OperationAttemptLedger({ now: options.now });
    this.childEnv = Object.freeze({ ...process.env, ...(options.env ?? {}) });
    this.platform = options.platform ?? process.platform;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_SUBPROCESS_TIMEOUT_MS;
    this.maxStdoutBytes = options.maxStdoutBytes ?? DEFAULT_MAX_STDOUT_BYTES;
    this.maxStderrBytes = options.maxStderrBytes ?? DEFAULT_MAX_STDERR_BYTES;

    // Pin once: later changes to a global profile cannot reroute this
    // transport's calls.
    const pinned: string[] = [];
    if (options.modelFlag && this.pinnedProfile.modelId !== null) {
      pinned.push(options.modelFlag, this.pinnedProfile.modelId);
    }
    if (options.effortFlag && this.pinnedProfile.effort !== null) {
      pinned.push(options.effortFlag, this.pinnedProfile.effort);
    }
    this.pinnedArgs = Object.freeze(pinned);
  }

  /** Refuse a request whose policy contradicts the frozen pin. */
  private assertRequestMatchesPin(request: TransportRequest): void {
    const routeId = request.route_id;
    if (routeId !== this.pinnedProfile.routeId) {
      throw new TransportRouteError(
        'COUNCIL_ROUTE_PIN_MISMATCH',
        `Request route ${JSON.stringify(routeId)} does not match the frozen route ${JSON.stringify(this.pinnedProfile.routeId)}; nothing is dispatched.`,
      );
    }
    const model = request.model_policy.requested_model_id;
    if (model !== null && model !== this.pinnedProfile.modelId) {
      throw new TransportRouteError(
        'COUNCIL_ROUTE_PIN_MISMATCH',
        `Request model ${JSON.stringify(model)} does not match the pinned model ${JSON.stringify(this.pinnedProfile.modelId)}; the transport never substitutes.`,
      );
    }
    const effort = request.model_policy.reasoning_preference;
    if (effort !== null && effort !== this.pinnedProfile.effort) {
      throw new TransportRouteError(
        'COUNCIL_ROUTE_PIN_MISMATCH',
        `Request reasoning ${JSON.stringify(effort)} does not match the pinned effort ${JSON.stringify(this.pinnedProfile.effort)}; silent substitution is refused.`,
      );
    }
  }

  private resolveInvocation(): ResolvedInvocation {
    if (this.options.invocation) {
      const base = this.options.invocation;
      return { ...base, args: [...base.args, ...this.pinnedArgs] };
    }
    try {
      return resolveCommand({
        command: this.options.command,
        args: [...(this.options.args ?? []), ...this.pinnedArgs],
        platform: this.platform,
        env: this.childEnv,
      });
    } catch (error) {
      if (error instanceof ExecutableResolutionError) {
        throw new TransportRouteError(
          'COUNCIL_TRANSPORT_SPAWN_FAILED',
          error.message,
        );
      }
      throw error;
    }
  }

  async generate(request: TransportRequest): Promise<TransportResponse> {
    // Every refusal below happens BEFORE a process exists. The hash is
    // re-verified per dispatch so a snapshot mutated after construction
    // cannot slip through.
    assertDispatchableSnapshot(this.options.snapshot);
    this.assertRequestMatchesPin(request);
    const invocation = this.resolveInvocation();

    if (request.signal?.aborted) {
      throw new BoundedSubprocessError(
        'COUNCIL_TRANSPORT_CANCELLED',
        'The call was cancelled before launch; no child process was started.',
        {
          operationId: operationIdFor(request),
          attemptId: this.nextAttemptId(),
          disposition: 'failed_definitely',
        },
      );
    }

    const operationId = operationIdFor(request);
    const attemptId = this.nextAttemptId();
    // Record BEFORE launch: a crash or timeout can never be read as
    // "the provider certainly did nothing".
    this.ledger.begin({ operationId, attemptId, routeId: this.pinnedProfile.routeId });

    const prompt = `${request.system}\n\n${canonicalStringify(request.input)}`;
    const spawnImpl = this.options.spawnImpl ?? spawn;
    const killTree = this.options.killTreeImpl ?? ((child: ChildProcess) =>
      terminateProcessTree(child, this.platform));

    return new Promise<TransportResponse>((resolve, reject) => {
      let child: ChildProcess;
      try {
        child = spawnImpl(invocation.file, invocation.args, {
          env: this.childEnv,
          stdio: ['pipe', 'pipe', 'pipe'],
          windowsHide: true,
          // POSIX: become a process-group leader so the whole tree can
          // be signalled. Windows uses taskkill /T instead.
          detached: this.platform !== 'win32',
        });
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        this.ledger.markFailedDefinitely(operationId, attemptId, detail);
        reject(
          new BoundedSubprocessError(
            'COUNCIL_TRANSPORT_SPAWN_FAILED',
            `The resolved executable could not be started: ${detail}`,
            { operationId, attemptId, disposition: 'failed_definitely' },
          ),
        );
        return;
      }

      this.ledger.markRunning(operationId, attemptId);

      let stdoutBytes = 0;
      let stderrBytes = 0;
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let settled = false;
      let timedOut = false;
      let aborted = false;
      let overflowed = false;

      const cleanup = (): void => {
        clearTimeout(timer);
        request.signal?.removeEventListener('abort', onAbort);
      };

      const fail = (
        code: SubprocessTransportErrorCode,
        message: string,
        disposition: 'failed_definitely' | 'potentially_dispatched',
      ): void => {
        if (settled) return;
        settled = true;
        cleanup();
        if (disposition === 'potentially_dispatched') {
          this.ledger.markPotentiallyDispatched(operationId, attemptId, message);
        } else {
          this.ledger.markFailedDefinitely(operationId, attemptId, message);
        }
        reject(new BoundedSubprocessError(code, message, { operationId, attemptId, disposition }));
      };

      const timer = setTimeout(() => {
        timedOut = true;
        killTree(child);
      }, this.timeoutMs);

      const onAbort = (): void => {
        aborted = true;
        killTree(child);
      };
      if (request.signal) {
        request.signal.addEventListener('abort', onAbort, { once: true });
      }

      child.stdout?.on('data', (chunk: Buffer) => {
        if (settled) return;
        stdoutBytes += chunk.length;
        if (stdoutBytes > this.maxStdoutBytes) {
          overflowed = true;
          killTree(child);
          fail(
            'COUNCIL_TRANSPORT_OUTPUT_BOUND',
            `The subprocess exceeded the ${this.maxStdoutBytes}-byte stdout bound; the operation was refused.`,
            'potentially_dispatched',
          );
          return;
        }
        stdout.push(chunk);
      });
      child.stderr?.on('data', (chunk: Buffer) => {
        if (settled) return;
        const remaining = this.maxStderrBytes - stderrBytes;
        if (remaining <= 0) return;
        // Truncate at the bound; diagnostics are never allowed to grow
        // without limit.
        const kept = chunk.length > remaining ? chunk.subarray(0, remaining) : chunk;
        stderr.push(kept);
        stderrBytes += kept.length;
      });

      child.on('error', (error) => {
        // A spawn error means the executable never ran, which is the
        // only class that is safe to retry.
        fail(
          'COUNCIL_TRANSPORT_SPAWN_FAILED',
          `The executable failed to run: ${error.message}`,
          'failed_definitely',
        );
      });

      child.on('close', (code) => {
        if (settled) return;
        settled = true;
        cleanup();

        if (timedOut) {
          this.ledger.markPotentiallyDispatched(
            operationId,
            attemptId,
            `exceeded ${this.timeoutMs} ms deadline`,
          );
          reject(
            new BoundedSubprocessError(
              'COUNCIL_TRANSPORT_TIMEOUT',
              `The call exceeded the ${this.timeoutMs} ms deadline and the process tree was terminated; whether the provider completed is unknown, so the operation is never replayed.`,
              { operationId, attemptId, disposition: 'potentially_dispatched' },
            ),
          );
          return;
        }
        if (aborted) {
          this.ledger.markPotentiallyDispatched(
            operationId,
            attemptId,
            'cancelled after launch',
          );
          reject(
            new BoundedSubprocessError(
              'COUNCIL_TRANSPORT_CANCELLED',
              'The call was cancelled and the process tree was terminated; provider completion is unknown, so the operation is never replayed.',
              { operationId, attemptId, disposition: 'potentially_dispatched' },
            ),
          );
          return;
        }
        if (overflowed) return; // Already settled by fail().

        const out = Buffer.concat(stdout).toString('utf8');
        const err = Buffer.concat(stderr).toString('utf8');
        const trimmed = out.trim();

        if (code !== 0 && code !== null) {
          const tail = err.trim().slice(-300);
          const message = `The subprocess exited with code ${code}${tail ? `: ${tail}` : ''}; provider completion is unknown.`;
          this.ledger.markPotentiallyDispatched(operationId, attemptId, message);
          reject(
            new BoundedSubprocessError(
              'COUNCIL_TRANSPORT_EXIT_FAILED',
              message,
              { operationId, attemptId, disposition: 'potentially_dispatched' },
            ),
          );
          return;
        }

        let envelope: HarnessResultEnvelope | null = null;
        try {
          const parsed = JSON.parse(trimmed) as unknown;
          if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
            envelope = parsed as HarnessResultEnvelope;
          }
        } catch {
          envelope = null;
        }

        if (envelope && envelope.is_error === true) {
          const detail =
            typeof envelope.result === 'string'
              ? envelope.result
              : typeof envelope.subtype === 'string'
                ? envelope.subtype
                : 'the subprocess reported an error';
          // The process ran; the provider may have been billed.
          this.ledger.markPotentiallyDispatched(operationId, attemptId, detail);
          reject(
            new BoundedSubprocessError(
              'COUNCIL_TRANSPORT_EXIT_FAILED',
              `The subprocess reported an error: ${detail}`,
              { operationId, attemptId, disposition: 'potentially_dispatched' },
            ),
          );
          return;
        }

        if (envelope && typeof envelope.result === 'string') {
          this.ledger.markCompleted(operationId, attemptId);
          resolve({
            text: envelope.result,
            provider_request_id:
              typeof envelope.session_id === 'string' ? envelope.session_id : null,
            reported_model_id: reportedModelOf(envelope),
            usage: usageOf(envelope.usage),
          });
          return;
        }

        if (trimmed.length > 0) {
          // A target that answers in plain text: the text is the
          // response, identity stays unreported.
          this.ledger.markCompleted(operationId, attemptId);
          resolve({
            text: trimmed,
            provider_request_id: null,
            reported_model_id: null,
            usage: { input_tokens: null, output_tokens: null },
          });
          return;
        }

        this.ledger.markPotentiallyDispatched(operationId, attemptId, 'empty output');
        reject(
          new BoundedSubprocessError(
            'COUNCIL_TRANSPORT_EMPTY_OUTPUT',
            'The subprocess produced no output.',
            { operationId, attemptId, disposition: 'potentially_dispatched' },
          ),
        );
      });

      child.stdin?.on('error', () => {
        // A child that exits before reading stdin reports through close.
      });
      // Prompt content leaves ONLY here.
      child.stdin?.end(prompt);
    });
  }

  private nextAttemptId(): string {
    if (this.options.attemptIdFactory) return this.options.attemptIdFactory();
    this.attemptCounter += 1;
    return `a${this.attemptCounter}`;
  }

  /** Latest recorded attempt for one operation, for host persistence. */
  attemptFor(operationId: string, attemptId: string): AttemptRecord | null {
    return this.ledger.get(operationId, attemptId);
  }
}

function reportedModelOf(envelope: HarnessResultEnvelope): string | null {
  if (typeof envelope.model === 'string') return envelope.model;
  if (
    envelope.modelUsage !== null &&
    typeof envelope.modelUsage === 'object' &&
    !Array.isArray(envelope.modelUsage)
  ) {
    const keys = Object.keys(envelope.modelUsage as Record<string, unknown>);
    if (keys.length === 1) return keys[0];
  }
  return null;
}

function usageOf(value: unknown): { input_tokens: number | null; output_tokens: number | null } {
  const usage = (value ?? {}) as Record<string, unknown>;
  return {
    input_tokens: numberOrNull(usage.input_tokens),
    output_tokens: numberOrNull(usage.output_tokens),
  };
}
