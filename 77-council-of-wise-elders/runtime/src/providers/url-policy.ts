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
 * - hostnames are normalized before classification: a single trailing
 *   dot (a rooted FQDN such as "metadata.google.internal.") is removed,
 *   because the URL parser preserves it for hostnames while DNS
 *   resolves the dotted and undotted spellings to the same host; and
 *   an IPv4-mapped IPv6 literal ("[::ffff:a9fe:a9fe]") is classified
 *   by its embedded IPv4 address, because a dual-stack connect
 *   through the mapped form reaches that IPv4 service;
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

/**
 * Normalize a hostname for classification: lowercase it and remove a
 * single trailing dot. The trailing dot makes a name a rooted FQDN
 * ("example.com." names the same host as "example.com"); the URL
 * parser strips it from IP literals but preserves it on hostnames,
 * so every name-based comparison below must see the normalized form
 * or "metadata.google.internal." slips past the metadata set while
 * resolving to the same service.
 */
function normalizeHostname(hostname: string): string {
  const host = hostname.toLowerCase();
  return host.endsWith('.') ? host.slice(0, -1) : host;
}

/**
 * The IPv4 address embedded in an IPv4-mapped IPv6 literal, written
 * either as two hex groups ("::ffff:a9fe:a9fe") or in dotted form
 * ("::ffff:169.254.169.254"), or null when the host is not in mapped
 * form. A dual-stack connect through a mapped address reaches the
 * embedded IPv4 service, so the embedded address is what the policy
 * must classify and block.
 */
function parseIpv4MappedIpv6(hostname: string): number[] | null {
  const host = hostname.replace(/^\[|\]$/g, '');
  const match = /^::ffff:(.+)$/.exec(host);
  if (!match) return null;
  const dotted = parseIpv4(match[1]);
  if (dotted) return dotted;
  const hex = /^([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(match[1]);
  if (!hex) return null;
  const high = Number.parseInt(hex[1], 16);
  const low = Number.parseInt(hex[2], 16);
  return [high >> 8, high & 0xff, low >> 8, low & 0xff];
}

/** IPv4 parts for a dotted literal or an IPv4-mapped IPv6 literal. */
function ipv4Parts(hostname: string): number[] | null {
  return parseIpv4(hostname) ?? parseIpv4MappedIpv6(hostname);
}

function classifyHostname(hostname: string): EndpointLocality {
  const host = normalizeHostname(hostname);
  if (host === 'localhost' || host.endsWith('.localhost')) return 'loopback';
  if (host === '::1' || host === '[::1]') return 'loopback';
  const ip = ipv4Parts(host);
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
  const host = normalizeHostname(hostname).replace(/^\[|\]$/g, '');
  if (METADATA_HOSTNAMES.has(host)) return true;
  if (METADATA_IPS.has(host)) return true;
  const ip = ipv4Parts(host);
  if (ip) {
    // An IPv4-mapped IPv6 spelling names its embedded IPv4 address.
    if (METADATA_IPS.has(ip.join('.'))) return true;
    // The whole link-local range is blocked: cloud metadata services live
    // there, and no deliberately configured council endpoint does.
    if (ip[0] === 169 && ip[1] === 254) return true;
  }
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
