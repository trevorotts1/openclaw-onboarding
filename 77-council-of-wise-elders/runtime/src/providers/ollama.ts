/**
 * Local Ollama-compatible transport profile (CWE-009; directive
 * Sections 13 and 28.4).
 *
 * This is the SAME OpenAI-compatible adapter as compatible.ts, bound
 * through a local profile: local and remote routes differ only through
 * the adapter's configuration, never through separate council
 * algorithms (T031). The profile exists to hold the local guarantees:
 *
 * - the endpoint is the installation's configured compatible endpoint
 *   for the local daemon (default http://127.0.0.1:11434/v1, the
 *   documented local Ollama surface). A deliberately configured
 *   loopback endpoint is allowed and expected (Section 28.4); there
 *   is no blanket loopback ban;
 * - local and cloud identity are preserved: the pinned model string
 *   reaches the wire byte-identical, including local tags (for
 *   example an `:8b` tag) and cloud suffixes (for example `:cloud`).
 *   Nothing in this profile strips, rewrites, or re-resolves a model
 *   name, and a signed-in local daemon serving cloud models through
 *   the loopback endpoint is used exactly as configured;
 * - no side effects on the daemon: the shared request builder sends
 *   only model, messages, stream, and a mapped reasoning parameter.
 *   This profile never calls a pull, delete, or unload operation,
 *   never sends keep_alive overrides, and never changes context
 *   settings (no num_ctx or other daemon options) as a side effect
 *   of a council request;
 * - credentials: a local route normally records credential state
 *   not_required and sends no Authorization header. When a daemon is
 *   configured to require one, the value still travels only through
 *   the host credential resolver path, exactly as for remote routes.
 */

import {
  CompatibleHttpTransport,
  type CompatibleTransportBinding,
} from './compatible.js';
import { TransportError } from './errors.js';

/** The documented local Ollama compatible base URL, when configuration names none. */
export const DEFAULT_OLLAMA_BASE_URL = 'http://127.0.0.1:11434/v1';

/**
 * The configured Ollama endpoint as the OpenAI-compatible surface:
 * `/v1` is appended when the configuration does not already carry it
 * (`http://127.0.0.1:11434` and `http://127.0.0.1:11434/` both become
 * `.../v1`). Trailing slashes are dropped so no caller composes `//`.
 */
export function ollamaCompatibleBaseUrl(baseUrl?: string | null): string {
  const raw = (baseUrl ?? DEFAULT_OLLAMA_BASE_URL).trim().replace(/\/+$/, '');
  if (raw.length === 0) return DEFAULT_OLLAMA_BASE_URL;
  return /\/v1$/i.test(raw) ? raw : `${raw}/v1`;
}

export interface OllamaTransportBinding
  extends Omit<CompatibleTransportBinding, 'baseUrl'> {
  /** Configured local compatible base URL. Default: the local daemon surface. */
  baseUrl?: string;
}

/**
 * Create a local-profile compatible transport. The binding's selection
 * stays the single source of the wire model; the profile only supplies
 * local defaults and refuses a non-local endpoint unless the binding
 * explicitly marks the route as a configured remote Ollama endpoint
 * through the generic compatible transport instead.
 */
export function createOllamaTransport(
  binding: OllamaTransportBinding,
): CompatibleHttpTransport {
  const baseUrl = ollamaCompatibleBaseUrl(binding.baseUrl);
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new TransportError(
      'TRANSPORT_CONFIG_INVALID',
      'The local Ollama endpoint is not a valid URL.',
    );
  }
  const host = parsed.hostname.toLowerCase();
  const isLocal =
    host === 'localhost' ||
    host === '::1' ||
    host === '[::1]' ||
    /^127\./.test(host);
  // A remote endpoint over TLS (Ollama Cloud) is served by this same
  // OpenAI-compatible profile; plain http to a remote host still needs
  // the explicit opt-in because it exposes the credential in flight.
  const isTls = parsed.protocol === 'https:';
  if (!isLocal && !isTls && binding.allowInsecureRemoteHttp !== true) {
    // A remote plain-http Ollama endpoint is a legitimate route, but it
    // is not a LOCAL transport: it goes through the generic compatible
    // profile with the explicit opt-in so its locality is never
    // mislabeled in attempt records.
    throw new TransportError(
      'TRANSPORT_CONFIG_INVALID',
      'The Ollama local profile serves loopback daemon endpoints and TLS Ollama Cloud endpoints. For a plain-http remote Ollama endpoint, compose the generic compatible transport with the explicit insecure-http opt-in so the route locality is recorded honestly.',
    );
  }
  return new CompatibleHttpTransport({ ...binding, baseUrl });
}
