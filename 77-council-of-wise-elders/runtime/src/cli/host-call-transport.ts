/**
 * Subprocess host-call delegate for harness routes (RP-046-1 repair
 * for DEFECT-046-A; directive Section 13.4 adapter 3).
 *
 * Adapter 3 integrates through the host harness's OWN supported
 * surface: the skill invokes the harness executable the client's
 * configuration names (the Claude Code / Claude-Nine launcher found
 * by route discovery) as a subprocess, in print mode, and reads its
 * structured JSON result envelope. The harness keeps its own routing,
 * its own configured model, and its own credentials: this delegate
 * passes NO model flag (the council never prescribes a model to the
 * harness), scrapes no OAuth token or cookie, and manufactures no API
 * access from a subscription. What the harness resolves is reported
 * back to the CWE-010 guard by the bridge resolver, never invented
 * here.
 *
 * Failure honesty: a harness that exits non-zero or reports an error
 * envelope fails the operation through the normal transport error
 * path. A delegate killed by the deadline may or may not have
 * completed provider-side, so that failure carries
 * unknownCompletion = true and the engine never replays it
 * (Section 15.5). Response bodies are not persisted by this delegate;
 * only the parsed text and structured identity/usage fields leave it.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { canonicalStringify } from '../contracts/index.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from './host-ports.js';

export const DEFAULT_HOST_CALL_TIMEOUT_MS = 600_000;
const MAX_STDOUT_BYTES = 16 * 1024 * 1024;
const MAX_STDERR_BYTES = 64 * 1024;

export class HostCallTransportError extends Error {
  readonly retryable = false;
  readonly unknownCompletion: boolean;
  constructor(message: string, options: { unknownCompletion?: boolean } = {}) {
    super(message);
    this.name = 'HostCallTransportError';
    this.unknownCompletion = options.unknownCompletion ?? false;
  }
}

export interface HostCallTransportOptions {
  /** Absolute path of the harness executable the configuration names. */
  executable: string;
  /**
   * The harness config root this route serves. Passed to the child as
   * CLAUDE_CONFIG_DIR so a plain harness executable serves the same
   * root the route was discovered from; launcher scripts that set it
   * themselves set the identical value.
   */
  configDir?: string;
  /** Extra environment for the child, merged over the inherited env. */
  env?: NodeJS.ProcessEnv;
  /** Verified operation deadline. Default: Section 15.8 initial default. */
  timeoutMs?: number;
  /** Injectable spawn for embedding; production uses node:child_process. */
  spawnImpl?: typeof spawn;
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

export class SubprocessHostCallTransport implements ModelTransport {
  private readonly options: HostCallTransportOptions;

  constructor(options: HostCallTransportOptions) {
    this.options = options;
  }

  get executable(): string {
    return this.options.executable;
  }

  async generate(request: TransportRequest): Promise<TransportResponse> {
    const spawnImpl = this.options.spawnImpl ?? spawn;
    const timeoutMs = this.options.timeoutMs ?? DEFAULT_HOST_CALL_TIMEOUT_MS;
    const env: NodeJS.ProcessEnv = { ...process.env, ...(this.options.env ?? {}) };
    if (this.options.configDir) {
      env.CLAUDE_CONFIG_DIR = this.options.configDir;
    }
    const prompt = `${request.system}\n\n${canonicalStringify(request.input)}`;

    return new Promise<TransportResponse>((resolve, reject) => {
      let child: ChildProcess;
      try {
        child = spawnImpl(
          this.options.executable,
          ['--print', '--output-format', 'json'],
          { env, stdio: ['pipe', 'pipe', 'pipe'] },
        );
      } catch (err) {
        reject(
          new HostCallTransportError(
            `The configured harness executable could not be started: ${err instanceof Error ? err.message : String(err)}`,
          ),
        );
        return;
      }

      let stdout = '';
      let stderr = '';
      let settled = false;
      let timedOut = false;

      const timer = setTimeout(() => {
        timedOut = true;
        child.kill('SIGKILL');
      }, timeoutMs);

      const onAbort = () => {
        child.kill('SIGKILL');
      };
      if (request.signal) {
        if (request.signal.aborted) onAbort();
        else request.signal.addEventListener('abort', onAbort, { once: true });
      }

      child.stdout?.on('data', (chunk: Buffer) => {
        if (stdout.length < MAX_STDOUT_BYTES) stdout += chunk.toString('utf8');
      });
      child.stderr?.on('data', (chunk: Buffer) => {
        if (stderr.length < MAX_STDERR_BYTES) stderr += chunk.toString('utf8');
      });
      child.on('error', (err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(
          new HostCallTransportError(
            `The configured harness executable failed to run: ${err.message}`,
          ),
        );
      });
      child.on('close', (code) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (timedOut) {
          reject(
            new HostCallTransportError(
              `The harness call exceeded the ${timeoutMs} ms operation deadline and was killed; whether the provider completed is unknown, so the operation is never replayed.`,
              { unknownCompletion: true },
            ),
          );
          return;
        }
        if (request.signal?.aborted) {
          reject(
            new HostCallTransportError('The harness call was aborted by cancellation.', {
              unknownCompletion: true,
            }),
          );
          return;
        }
        const trimmed = stdout.trim();
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
                : 'the harness reported an error';
          reject(
            new HostCallTransportError(`The harness reported an error: ${detail}`),
          );
          return;
        }
        if (code !== 0 && code !== null) {
          const tail = stderr.trim().slice(-300);
          reject(
            new HostCallTransportError(
              `The configured harness executable exited with code ${code}${tail ? `: ${tail}` : ''}`,
            ),
          );
          return;
        }
        if (envelope && typeof envelope.result === 'string') {
          let reportedModelId: string | null =
            typeof envelope.model === 'string' ? envelope.model : null;
          if (reportedModelId === null && envelope.modelUsage !== null && typeof envelope.modelUsage === 'object') {
            const keys = Object.keys(envelope.modelUsage as Record<string, unknown>);
            if (keys.length === 1) reportedModelId = keys[0];
          }
          const usage = (envelope.usage ?? {}) as Record<string, unknown>;
          resolve({
            text: envelope.result,
            provider_request_id:
              typeof envelope.session_id === 'string' ? envelope.session_id : null,
            reported_model_id: reportedModelId,
            usage: {
              input_tokens: numberOrNull(usage.input_tokens),
              output_tokens: numberOrNull(usage.output_tokens),
            },
          });
          return;
        }
        if (trimmed.length > 0) {
          // A harness build that answers in plain text instead of the
          // JSON envelope: the text is the response, identity stays
          // unreported, and nothing is inferred from prose.
          resolve({
            text: trimmed,
            provider_request_id: null,
            reported_model_id: null,
            usage: { input_tokens: null, output_tokens: null },
          });
          return;
        }
        reject(
          new HostCallTransportError(
            'The configured harness executable produced no output.',
          ),
        );
      });

      child.stdin?.on('error', () => {
        // A child that exits before reading its input reports through
        // the close handler; a broken stdin pipe adds no information.
      });
      child.stdin?.end(prompt);
    });
  }
}
