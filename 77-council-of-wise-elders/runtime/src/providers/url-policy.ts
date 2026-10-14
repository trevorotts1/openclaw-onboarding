/**
 * Provider endpoint URL policy (CWE-009; directive Section 28.4).
 *
 * Only an authorized configuration path may add a provider endpoint:
 * for this transport layer, that path is the transport binding a host
 * composes at startup. Every configured endpoint is assessed before
 * the transport is constructed:
 *
 * - scheme must be http or https; plain http is accepted only for
 *   loopback or private-network endpoints (a deliberately configured
 *   local route) unless the binding explicitly allows insecure remote
 *   http;
 * - credentials embedded in the URL (userinfo) are always rejected:
 *   secrets travel only through the host credential resolver;
 * - cloud metadata and link-local targets are always blocked, in every
 *   configuration, including the instance metadata addresses and the
 *   metadata hostname;
 * - loopback endpoints are NOT blanket-banned: a deliberately
 *   configured local Ollama or 9Router loopback endpoint is a first
 *   class local route (Section 28.4), classified as loopback so its
 *   locality is visible in every attempt record;
 * - redirects are never followed by the transport (fetch is issued
 *   with redirect: manual and a 3xx is a typed refusal), so a
 *   configured endpoint cannot bounce a request, or its credential,
 *   to a different origin.
 *
 * Assessment is lexical, on the configured URL itself. It performs no
 * DNS resolution and no network I/O; a host that needs resolution-time
 * checks (rebinding defense) layers them at its own boundary.
 */

import { TransportError } from './errors.js';

export type EndpointLocality = 'loopback' | 'private_network' | 'public';

export interface EndpointAssessment {
  /** The final request URL (base plus chat-completions path). */
  url: string;
  /** scheme://host:port; safe to record (never contains userinfo). */
  origin: string;
  locality: EndpointLocality;
  isLoopback: boolean;
}

/** Hostnames that always name a cloud metadata service. */
const METADATA_HOSTNAMES: ReadonlySet<string> = new Set([
  'metadata.google.internal',
  'metadata.google',
  'instance-data',
]);

/** IP literals that always name a metadata service. */
const METADATA_IPS: ReadonlySet<string> = new Set([
  '169.254.169.254',
  '169.254.170.2',
  '100.100.100.200',
  'fd00:ec2::254',
]);

function parseIpv4(hostname: string): number[] | null {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(hostname);
  if (!match) return null;
  const parts = match.slice(1).map((p) => Number(p));
  if (parts.some((p) => p > 255)) return null;
  return parts;
}

function classifyHostname(hostname: string): EndpointLocality {
  const host = hostname.toLowerCase();
  if (host === 'localhost' || host.endsWith('.localhost')) return 'loopback';
  if (host === '::1' || host === '[::1]') return 'loopback';
  const ip = parseIpv4(host);
  if (ip) {
    const [a, b] = ip;
    if (a === 127) return 'loopback';
    if (a === 10) return 'private_network';
    if (a === 172 && b >= 16 && b <= 31) return 'private_network';
    if (a === 192 && b === 168) return 'private_network';
    if (a === 100 && b >= 64 && b <= 127) return 'private_network';
    return 'public';
  }
  if (host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe80')) {
    return 'private_network';
  }
  return 'public';
}

function isMetadataTarget(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (METADATA_HOSTNAMES.has(host)) return true;
  if (METADATA_IPS.has(host)) return true;
  const ip = parseIpv4(host);
  // The whole link-local range is blocked: cloud metadata services live
  // there, and no deliberately configured council endpoint does.
  if (ip && ip[0] === 169 && ip[1] === 254) return true;
  return false;
}

export interface EndpointPolicyOptions {
  /** Path appended to the configured base URL. Default '/chat/completions'. */
  chatCompletionsPath?: string;
  /** Explicit opt-in for plain http to a public endpoint. Default false. */
  allowInsecureRemoteHttp?: boolean;
}

/**
 * Assess a configured provider base URL. Throws a typed
 * TRANSPORT_ENDPOINT_BLOCKED error for anything the policy refuses;
 * construction of a transport fails closed on a refused endpoint.
 */
export function assessEndpoint(
  baseUrl: string,
  options: EndpointPolicyOptions = {},
): EndpointAssessment {
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new TransportError(
      'TRANSPORT_ENDPOINT_BLOCKED',
      'The configured provider endpoint is not a valid URL.',
    );
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new TransportError(
      'TRANSPORT_ENDPOINT_BLOCKED',
      `Provider endpoint scheme ${parsed.protocol} is not allowed; only http and https endpoints may be configured.`,
    );
  }
  if (parsed.username || parsed.password) {
    throw new TransportError(
      'TRANSPORT_ENDPOINT_BLOCKED',
      'Provider endpoint URLs must not embed credentials. Credentials are supplied only through the host credential resolver.',
    );
  }
  if (isMetadataTarget(parsed.hostname)) {
    throw new TransportError(
      'TRANSPORT_ENDPOINT_BLOCKED',
      'The configured provider endpoint targets a cloud metadata or link-local address, which is never a provider endpoint.',
    );
  }
  const locality = classifyHostname(parsed.hostname);
  if (
    parsed.protocol === 'http:' &&
    locality === 'public' &&
    !options.allowInsecureRemoteHttp
  ) {
    throw new TransportError(
      'TRANSPORT_ENDPOINT_BLOCKED',
      'Plain http is allowed only for loopback or private-network endpoints. Configure https, or explicitly allow insecure remote http in the transport binding.',
    );
  }
  const path = options.chatCompletionsPath ?? '/chat/completions';
  const base = parsed.toString().replace(/\/+$/, '');
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`;
  return {
    url,
    origin: parsed.origin,
    locality,
    isLoopback: locality === 'loopback',
  };
}
