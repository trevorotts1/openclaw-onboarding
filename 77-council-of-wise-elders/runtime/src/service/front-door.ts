/**
 * Standalone Council front door (WER-021 dependency-ready slice).
 *
 * One same-origin loopback service exposes the health, identity, session
 * URL and admission contract AROUND the canonical durable owner. It is
 * deliberately not an engine: admissions are forwarded to an injected
 * sink, the event stream is served from an injected adapter over the
 * canonical journal, and the session route reads through an injected
 * reader. With neither adapter bound the service keeps its historical
 * unbound answers byte-for-byte (`EVENT_STREAM_ADAPTER_NOT_BOUND`,
 * `ui: "not_bundled"`) — it never fabricates a stream or a session.
 *
 * Behaviour proven by the colocated tests:
 * - duplicate start resolves and reuses ONLY a verified matching service;
 *   an unrelated listener is refused and left running;
 * - the emitted session URL is derived from the actual bound origin;
 * - a managed session returns its owning external URL and is never
 *   started locally;
 * - drain fences new admissions while existing sessions stay reachable;
 * - browser-open failure preserves the usable URL (WER-005 pattern).
 *
 * Deferred, never claimed: a registered system service, launchd/systemd
 * units, a bundled shared UI, a live event stream, a real browser launch
 * in tests, and any host mutation.
 */

import { existsSync, readFileSync } from 'node:fs';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';

import { openCouncilUrl, type BrowserOpenResult } from '../bridges/browser-open.js';
import {
  formatCouncilEventFrame,
  type CouncilEventCursor,
  type CouncilEventStreamAdapter,
  type CouncilSessionReader,
} from './events.js';
import {
  classifyListener,
  normalizeOrigin,
  SERVICE_IDENTITY_PATH,
} from './identity.js';
import {
  evaluateServiceReadiness,
  type ReadinessOptions,
  type ServiceReadinessDeps,
} from './readiness.js';
import { eventsPath, resolveSessionTarget, sessionUrl } from './sessions.js';
import {
  DEFAULT_SERVICE_HOST,
  DEFAULT_SERVICE_PORTS,
  SERVICE_API_VERSION,
  type AdmissionDecision,
  type AdmissionRequest,
  type AdmissionSink,
  type DrainOutcome,
  type ServiceIdentity,
  type ServiceReadiness,
  type ServiceStartBlocker,
  type ServiceState,
  type SessionAuthorityRecord,
  type SessionTarget,
  type StartOutcome,
  type StopOutcome,
} from './types.js';

export interface OpenSessionResult {
  target: SessionTarget;
  /** Null when the caller asked not to open, or the target is blocked. */
  browser: BrowserOpenResult | null;
}

export type FrontDoorReadinessDeps = Omit<ServiceReadinessDeps, 'origin'>;

export interface FrontDoorOptions {
  /** Owner identity served at the identity endpoint (started_at excluded from matching). */
  identity: ServiceIdentity;
  /** Bind host. Loopback only in this slice; remote exposure belongs to WER-023. */
  host?: string;
  /** Candidate ports, tried in order. Default DEFAULT_SERVICE_PORTS. */
  ports?: readonly number[];
  fetchImpl?: typeof fetch;
  /** Injected browser opener; defaults to the WER-005 helper. */
  openUrl?: (url: string) => BrowserOpenResult;
  /** The owning authority's admission surface (composition root supplies it). */
  admissionSink?: AdmissionSink;
  /**
   * Durable event stream source (composition root supplies it over the
   * canonical journal/outbox). Unbound keeps the 501 contract.
   */
  eventsAdapter?: CouncilEventStreamAdapter;
  /**
   * Durable session reader (composition root supplies it over the
   * canonical repositories). Unbound keeps the historical 200 body.
   */
  sessionReader?: CouncilSessionReader;
  readiness?: FrontDoorReadinessDeps;
}

const MAX_BODY_BYTES = 1_048_576;

/**
 * Packaged chamber assets (WER-021 full packaging).
 *
 * Both roots are tried so the same files resolve from the TypeScript source
 * (src/service), the tsc output (dist/service) and the esbuild single-file
 * bundle (dist). The asset directory is the only file set this route serves;
 * there is no directory listing and no traversal.
 */
const CHAMBER_ASSET_ROOTS: readonly URL[] = [
  new URL('../../public/chamber/', import.meta.url),
  new URL('../public/chamber/', import.meta.url),
];

const CHAMBER_ROOT_FILES: ReadonlyMap<string, string> = new Map([
  ['index.html', 'text/html; charset=utf-8'],
  ['advisors.html', 'text/html; charset=utf-8'],
  ['not-packaged.html', 'text/html; charset=utf-8'],
  ['council-theme.css', 'text/css; charset=utf-8'],
  ['council-room.css', 'text/css; charset=utf-8'],
  ['council-journey.css', 'text/css; charset=utf-8'],
  ['RECEIPT.md', 'text/markdown; charset=utf-8'],
]);

function chamberAssetRoot(): URL | null {
  for (const root of CHAMBER_ASSET_ROOTS) {
    if (existsSync(root)) return root;
  }
  return null;
}

/** The chamber is only a landing target when its own entry page exists. */
function chamberLandingReady(): boolean {
  const root = chamberAssetRoot();
  return root !== null && existsSync(new URL('index.html', root));
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(text),
    'cache-control': 'no-store',
  });
  res.end(text);
}

/** Unknown durable session: one code for the session and events routes. */
function sessionNotFound(sessionId: string): {
  code: 'SESSION_NOT_FOUND';
  session_id: string;
  detail: string;
  recovery: string;
} {
  return {
    code: 'SESSION_NOT_FOUND',
    session_id: sessionId,
    detail: `No durable council session ${sessionId} is known to the composed store.`,
    recovery:
      'Admit the session through POST /api/council/admissions, then use the session id the store returned.',
  };
}

/** Self-contained HTML only: no external asset, script or stylesheet. */
function sendHtml(res: ServerResponse, html: string): void {
  res.writeHead(200, {
    'content-type': 'text/html; charset=utf-8',
    'content-length': Buffer.byteLength(html),
    'cache-control': 'no-store',
  });
  res.end(html);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Observed artifacts are echoed, never with an absolute home path. */
function redactHome(value: string): string {
  return value.replace(
    /(?:\/Users\/[^/\s"'<>]+|\/home\/[^/\s"'<>]+|[A-Za-z]:\\Users\\[^\\\s"'<>]+)/g,
    '~',
  );
}

/** The landing page must not introduce a fetch or name a foreign origin. */
function redactExternalUrls(value: string, origin: string): string {
  return value.replace(/https?:\/\/[^\s"'<>]+/g, (url) =>
    origin.length > 0 && url.startsWith(origin) ? url : '[external-url-redacted]',
  );
}

function redactObserved(value: string, origin: string): string {
  return escapeHtml(redactExternalUrls(redactHome(value), origin));
}

/** Exact loopback set plus the 127/8 block; nothing else is a local front door. */
export function isLoopbackHost(host: string): boolean {
  const value = host.trim().toLowerCase();
  if (value === 'localhost' || value === '::1') return true;
  return /^127(?:\.\d{1,3}){3}$/.test(value);
}

export function originFor(host: string, port: number): string {
  const bracketed = host.includes(':') && !host.startsWith('[') ? `[${host}]` : host;
  return `http://${bracketed}:${port}`;
}

interface ListenSuccess {
  ok: true;
  server: Server;
  origin: string;
  port: number;
}

interface ListenFailure {
  ok: false;
  code: string;
  error: Error;
}

export class CouncilFrontDoor {
  private readonly options: FrontDoorOptions;
  private server: Server | null = null;
  private state: ServiceState = 'idle';
  private origin: string | null = null;
  private boundPort: number | null = null;
  private startResult: StartOutcome | null = null;
  private startPromise: Promise<StartOutcome> | null = null;
  private draining = false;
  private lastServerError: string | null = null;

  constructor(options: FrontDoorOptions) {
    this.options = options;
  }

  getState(): ServiceState {
    return this.state;
  }

  getOrigin(): string | null {
    return this.origin;
  }

  getPort(): number | null {
    return this.boundPort;
  }

  getIdentity(): ServiceIdentity {
    return this.options.identity;
  }

  getLastServerError(): string | null {
    return this.lastServerError;
  }

  /**
   * Start or resolve the local service.
   *
   * Per candidate port: bind; on EADDRINUSE probe the listener's identity.
   * A verified matching service is reused (no second listener, and this
   * handle never drains or stops it). An unrelated listener is recorded
   * as a blocker and the next candidate is tried; it is never killed.
   */
  async start(): Promise<StartOutcome> {
    if (this.startPromise) return this.startPromise;
    this.startPromise = this.doStart();
    try {
      return await this.startPromise;
    } finally {
      this.startPromise = null;
    }
  }

  private refuse(blockers: ServiceStartBlocker[]): StartOutcome {
    this.state = 'refused';
    const result: StartOutcome = {
      outcome: 'refused',
      origin: null,
      port: null,
      identity: null,
      blockers,
    };
    this.startResult = result;
    return result;
  }

  private async doStart(): Promise<StartOutcome> {
    if (this.startResult && this.startResult.outcome !== 'refused') {
      // A reused handle has no local listener to lose; a started handle
      // whose listener was stopped must start again rather than report a
      // stale origin.
      if (this.startResult.outcome === 'reused' || this.server) {
        return this.startResult;
      }
      this.startResult = null;
    }

    const host = this.options.host ?? DEFAULT_SERVICE_HOST;
    if (!isLoopbackHost(host)) {
      return this.refuse([
        {
          code: 'SERVICE_HOST_NOT_LOOPBACK',
          detail: `Refusing to bind ${host}: this slice exposes a loopback-only local service.`,
          recovery:
            'Use a loopback host; authenticated remote exposure belongs to the Cloudflare Tunnel/Access adapter (WER-023).',
        },
      ]);
    }

    const ports = this.options.ports ?? DEFAULT_SERVICE_PORTS;
    if (ports.length === 0) {
      return this.refuse([
        {
          code: 'SERVICE_PORT_CANDIDATES_EMPTY',
          detail: 'No candidate port was supplied for the local service.',
          recovery: 'Supply at least one loopback port candidate.',
        },
      ]);
    }

    const blockers: ServiceStartBlocker[] = [];
    for (const port of ports) {
      if (!Number.isInteger(port) || port < 0 || port > 65_535) {
        blockers.push({
          code: 'SERVICE_PORT_INVALID',
          detail: `Candidate port ${String(port)} is not an integer in 0..65535.`,
          recovery: 'Supply a valid loopback port candidate.',
        });
        continue;
      }

      const attempt = await this.listen(host, port);
      if (attempt.ok) {
        this.server = attempt.server;
        this.origin = attempt.origin;
        this.boundPort = attempt.port;
        this.state = 'running';
        this.draining = false;
        const result: StartOutcome = {
          outcome: 'started',
          origin: attempt.origin,
          port: attempt.port,
          identity: this.options.identity,
          blockers: [],
        };
        this.startResult = result;
        return result;
      }

      if (attempt.code === 'EADDRINUSE') {
        const existingOrigin = originFor(host, port);
        const { classification, probe } = await classifyListener(
          existingOrigin,
          this.options.identity,
          this.options.fetchImpl,
        );
        if (classification === 'matching_service' && probe.identity) {
          this.server = null;
          this.origin = normalizeOrigin(existingOrigin);
          this.boundPort = port;
          this.state = 'reused';
          this.draining = false;
          const result: StartOutcome = {
            outcome: 'reused',
            origin: this.origin,
            port,
            identity: probe.identity,
            blockers: [],
          };
          this.startResult = result;
          return result;
        }
        const observed =
          classification === 'unrelated_listener'
            ? 'a listener that is not this Council service'
            : 'a listener that did not answer the identity check';
        blockers.push({
          code: 'PORT_IN_USE_UNRELATED',
          detail: `${existingOrigin} is held by ${observed}${probe.error ? ` (${probe.error})` : ''}. It was left running.`,
          recovery:
            'Choose another loopback port or stop the unrelated listener yourself; this service never kills an unrelated process.',
        });
        continue;
      }

      blockers.push({
        code: 'SERVICE_LISTEN_FAILED',
        detail: `${originFor(host, port)} could not be bound: ${attempt.error.message}`,
        recovery: 'Fix the host or permission error and retry the service start.',
      });
    }

    return this.refuse(blockers);
  }

  private listen(host: string, port: number): Promise<ListenSuccess | ListenFailure> {
    const server = createServer((req, res) => this.handleRequest(req, res));
    return new Promise((resolve) => {
      const onError = (error: NodeJS.ErrnoException): void => {
        server.removeListener('listening', onListening);
        // A failed listener owns nothing; close is a no-op cleanup.
        server.close(() => undefined);
        resolve({
          ok: false,
          code: error.code ?? 'SERVICE_LISTEN_FAILED',
          error,
        });
      };
      const onListening = (): void => {
        server.removeListener('error', onError);
        const address = server.address();
        if (!address || typeof address === 'string') {
          server.close(() => undefined);
          resolve({
            ok: false,
            code: 'SERVICE_ADDRESS_UNKNOWN',
            error: new Error('The listener did not report a TCP address.'),
          });
          return;
        }
        // Post-bind errors are observed, never allowed to crash the host.
        server.on('error', (error) => {
          this.lastServerError = error instanceof Error ? error.message : String(error);
        });
        resolve({
          ok: true,
          server,
          origin: originFor(host, address.port),
          port: address.port,
        });
      };
      server.once('error', onError);
      server.once('listening', onListening);
      server.listen(port, host);
    });
  }

  private handleRequest(req: IncomingMessage, res: ServerResponse): void {
    void this.route(req, res).catch((error: unknown) => {
      this.lastServerError = error instanceof Error ? error.message : String(error);
      if (!res.headersSent) {
        sendJson(res, 500, {
          code: 'SERVICE_REQUEST_FAILED',
          detail: this.lastServerError,
        });
      } else {
        res.end();
      }
    });
  }

  private async route(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const origin = this.origin ?? 'http://127.0.0.1';
    let path: string;
    try {
      path = new URL(req.url ?? '/', origin).pathname;
    } catch {
      sendJson(res, 400, { code: 'SERVICE_BAD_REQUEST', detail: 'Unparseable request URL.' });
      return;
    }
    const method = req.method ?? 'GET';

    // The chamber is what a person opening this URL came for. When the
    // packaged entry page exists, `/` redirects to it with a relative
    // Location (never an absolute loopback URL an authenticated phone
    // cannot reach). Without the assets the root keeps the honest status
    // page, and the diagnostics always remain reachable at `/status`.
    if (method === 'GET' && path === '/') {
      if (chamberLandingReady()) {
        res.writeHead(302, {
          location: '/chamber/',
          'content-length': 0,
          'cache-control': 'no-store',
        });
        res.end();
        return;
      }
      sendHtml(res, await this.renderLanding());
      return;
    }

    if (method === 'GET' && path === '/status') {
      sendHtml(res, await this.renderLanding());
      return;
    }

    if (method === 'GET' && (path === '/healthz' || path === '/api/council/health')) {
      sendJson(res, 200, {
        ok: this.state === 'running' || this.state === 'draining' || this.state === 'reused',
        state: this.state,
        draining: this.draining,
        api_version: SERVICE_API_VERSION,
        origin: this.origin,
      });
      return;
    }

    if (method === 'GET' && path === SERVICE_IDENTITY_PATH) {
      sendJson(res, 200, this.options.identity);
      return;
    }

    if (method === 'POST' && path === '/api/council/admissions') {
      const body = await readJsonBody(req);
      if (!body.ok) {
        sendJson(res, body.status, {
          code: body.code,
          detail: body.detail,
          recovery: body.recovery,
        });
        return;
      }
      const decision = await this.admit(body.value as AdmissionRequest);
      sendJson(res, decision.accepted ? 202 : 503, decision);
      return;
    }

    const sessionMatch = /^\/council\/([^/]+)$/.exec(path);
    if (method === 'GET' && sessionMatch) {
      let sessionId: string;
      try {
        sessionId = decodeURIComponent(sessionMatch[1]);
      } catch {
        sendJson(res, 400, { code: 'SERVICE_BAD_SESSION_ID', detail: 'Malformed session id.' });
        return;
      }
      const target = resolveSessionTarget(
        { session_id: sessionId, authority: 'standalone' },
        { origin: this.origin },
      );
      if (target.kind === 'blocked') {
        sendJson(res, 503, target);
        return;
      }
      // Bound reader: an id the durable store does not know is a 404,
      // never the unbound page. An id it knows serves that session.
      const sessionReader = this.options.sessionReader;
      if (sessionReader) {
        const record = await sessionReader.read(sessionId);
        if (record === null) {
          sendJson(res, 404, sessionNotFound(sessionId));
          return;
        }
        const authority =
          record.authority === 'managed' || record.authority === 'standalone'
            ? record.authority
            : 'standalone';
        const known = resolveSessionTarget(
          { session_id: sessionId, authority },
          { origin: this.origin },
        );
        if (known.kind === 'blocked') {
          sendJson(res, 503, known);
          return;
        }
        sendJson(res, 200, {
          session_id: sessionId,
          authority,
          url: known.url,
          session: record,
          api: {
            session: known.url,
            events: eventsPath(sessionId),
          },
        });
        return;
      }
      sendJson(res, 200, {
        session_id: sessionId,
        authority: 'standalone',
        url: target.url,
        // Honest: this slice does not package a UI build or a live stream.
        ui: 'not_bundled',
        blocker: {
          code: 'UI_NOT_BUNDLED',
          detail: 'The shared Council UI build is not packaged by this service slice.',
          recovery:
            'Package the accepted shared Council UI build (WER-021 full packaging), then re-run service-readiness.',
        },
        api: {
          session: target.url,
          events: eventsPath(sessionId),
        },
      });
      return;
    }

    const eventsMatch = /^\/api\/council\/sessions\/([^/]+)\/events$/.exec(path);
    if (method === 'GET' && eventsMatch) {
      let sessionId = '';
      try {
        sessionId = decodeURIComponent(eventsMatch[1]);
      } catch {
        sessionId = '';
      }
      const adapter = this.options.eventsAdapter;
      if (adapter) {
        await this.serveEventStream(res, sessionId, adapter);
        return;
      }
      sendJson(res, 501, {
        code: 'EVENT_STREAM_ADAPTER_NOT_BOUND',
        session_id: sessionId,
        detail:
          'The durable event stream adapter is bound by the integration root over the canonical journal/outbox; this slice does not fabricate a live stream.',
        recovery:
          'Bind the durable event stream adapter and re-run service-readiness before advertising events.',
      });
      return;
    }

    // Packaged, fully self-contained chamber UI. Additive: a miss falls
    // through to the unchanged SERVICE_ROUTE_NOT_FOUND catch-all.
    if (method === 'GET' && (path === '/chamber' || path.startsWith('/chamber/'))) {
      if (this.serveChamberAsset(path, res)) return;
    }

    sendJson(res, 404, {
      code: 'SERVICE_ROUTE_NOT_FOUND',
      detail: `No service route for ${method} ${path}.`,
    });
  }

  /**
   * Serve one session's committed events from the injected adapter.
   *
   * Frames are committed journal rows only: `replay` is the catch-up and
   * the optional `subscribe` follows new rows. A failed read is retried
   * by the adapter from the same cursor; nothing is fabricated to cover
   * it. Without a follow hook the response ends after replay (a bounded,
   * honest read), and a browser/harness disconnect detaches at once.
   */
  private async serveEventStream(
    res: ServerResponse,
    sessionId: string,
    adapter: CouncilEventStreamAdapter,
  ): Promise<void> {
    const reader = this.options.sessionReader;
    if (reader && (await reader.read(sessionId)) === null) {
      sendJson(res, 404, sessionNotFound(sessionId));
      return;
    }

    const cursor: CouncilEventCursor | null = await adapter.open(sessionId);
    if (cursor === null) {
      sendJson(res, 404, sessionNotFound(sessionId));
      return;
    }

    res.writeHead(200, {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-store',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
    });

    let closed = false;
    let detach: (() => void) | null = null;
    const close = (): void => {
      if (closed) return;
      closed = true;
      detach?.();
      detach = null;
    };
    res.on('close', close);

    try {
      for (const frame of await cursor.replay(0)) {
        if (closed) return;
        res.write(formatCouncilEventFrame(frame));
      }
    } catch (error) {
      close();
      if (!res.headersSent) throw error;
      res.end();
      return;
    }

    if (!cursor.subscribe) {
      res.end();
      return;
    }

    detach = cursor.subscribe((frame) => {
      if (closed) return;
      res.write(formatCouncilEventFrame(frame));
    });
    if (closed) close();
  }

  /**
   * Serve one packaged chamber asset. Returns false for anything outside the
   * fixed file set (so the caller falls through to the unchanged catch-all).
   * No directory listing, no traversal, no external asset.
   */
  private serveChamberAsset(path: string, res: ServerResponse): boolean {
    const root = chamberAssetRoot();
    if (!root) return false;

    let relative: string;
    let contentType: string;
    if (path === '/chamber' || path === '/chamber/') {
      relative = 'index.html';
      contentType = 'text/html; charset=utf-8';
    } else {
      let decoded: string;
      try {
        decoded = decodeURIComponent(path.slice('/chamber/'.length));
      } catch {
        return false;
      }
      const portrait = /^portraits\/[A-Za-z0-9._-]+\.svg$/.exec(decoded);
      if (portrait) {
        relative = decoded;
        contentType = 'image/svg+xml; charset=utf-8';
      } else if (/^[A-Za-z0-9._-]+$/.test(decoded) && CHAMBER_ROOT_FILES.has(decoded)) {
        relative = decoded;
        contentType = CHAMBER_ROOT_FILES.get(decoded) as string;
      } else {
        return false;
      }
    }

    let body: Buffer;
    try {
      body = readFileSync(new URL(relative, root));
    } catch {
      return false;
    }
    res.writeHead(200, {
      'content-type': contentType,
      'content-length': body.length,
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    });
    res.end(body);
    return true;
  }

  /**
   * Self-contained landing page for `GET /`.
   *
   * Every value is read from this handle — identity, verified origin,
   * readiness layers and service state — so nothing is hardcoded, no
   * external asset is fetched and the page is explicit that the full
   * chamber UI is not packaged.
   */
  private async renderLanding(): Promise<string> {
    const identity = this.options.identity;
    const origin = this.origin ?? '';
    const readiness = await this.readiness();
    const identityRows = [
      ['Service', identity.service],
      ['Composition', identity.composition],
      ['API version', identity.api_version],
      ['Owner tenant', identity.owner.tenant_id],
      ['Owner company', identity.owner.company_id],
      ['Data directory (SHA-256)', identity.owner.data_dir_sha256],
      ['Started at', identity.started_at],
      ['Origin', origin],
      ['State', this.state],
    ]
      .map(
        ([label, value]) =>
          `<tr><th>${escapeHtml(label)}</th><td>${redactObserved(value, origin)}</td></tr>`,
      )
      .join('');
    const layerRows = readiness.layers
      .map((layer) => {
        const artifact =
          layer.artifact === null ? '—' : redactObserved(layer.artifact, origin);
        const blocker = layer.blocker
          ? `${escapeHtml(layer.blocker.code)}: ${redactObserved(layer.blocker.detail, origin)}`
          : '—';
        const recovery =
          layer.recovery === null ? '—' : redactObserved(layer.recovery, origin);
        return `<tr><th>${escapeHtml(layer.layer)}</th><td>${escapeHtml(
          layer.state,
        )}</td><td>${artifact}</td><td>${blocker}</td><td>${recovery}</td></tr>`;
      })
      .join('');
    const identityLink = `${origin}${SERVICE_IDENTITY_PATH}`;
    const sessionLink = `${origin}/council/your-session-id`;
    const eventsLink = `${origin}/api/council/sessions/your-session-id/events`;

    return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Council of Wise Elders — service landing</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
body{margin:0;padding:1.5rem;line-height:1.45}
main{max-width:60rem;margin:0 auto}
h1{font-size:1.4rem;margin:0 0 .25rem}
h2{font-size:1.05rem;margin:1.5rem 0 .5rem}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;vertical-align:top;padding:.35rem .5rem;border-bottom:1px solid #8884}
th{white-space:nowrap;font-weight:600}
.notice{border-left:.25rem solid #c98a00;padding:.5rem .75rem;margin:1rem 0;background:#c98a001a}
.ok{opacity:.85}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
ul{margin:.25rem 0;padding-left:1.25rem}
</style>
</head>
<body>
<main>
<h1>Council of Wise Elders — service landing</h1>
<p class="ok">This is the Council service status and session landing page. It is <strong>not</strong> the full Council chamber UI.</p>
<div class="notice"><strong>UI_NOT_BUNDLED</strong> — the full Council chamber UI is not packaged by this service slice. Packaging the accepted shared Council UI build (WER-021 full packaging) is the path to it, then re-run service-readiness.</div>
<div class="notice"><strong>EVENT_STREAM_ADAPTER_NOT_BOUND</strong> — the durable event stream adapter is not bound here. <code>GET /api/council/sessions/&lt;id&gt;/events</code> answers 501 until the integration root binds the canonical journal/outbox adapter.</div>
<h2>Service identity</h2>
<table>${identityRows}</table>
<h2>Readiness (${escapeHtml(readiness.observed_at)}, usable: ${readiness.usable ? 'yes' : 'no'})</h2>
<table>
<thead><tr><th>Layer</th><th>State</th><th>Artifact</th><th>Blocker</th><th>Recovery</th></tr></thead>
<tbody>${layerRows}</tbody>
</table>
<h2>Routes that work</h2>
<ul>
<li><a href="${escapeHtml(identityLink)}"><code>GET /api/council/service/identity</code></a> — service identity JSON (200)</li>
<li><a href="${escapeHtml(sessionLink)}"><code>GET /council/&lt;sessionId&gt;</code></a> — session record; reports <code>ui: "not_bundled"</code> with blocker <code>UI_NOT_BUNDLED</code> (200)</li>
<li><a href="${escapeHtml(eventsLink)}"><code>GET /api/council/sessions/&lt;id&gt;/events</code></a> — event stream (501, adapter not bound)</li>
</ul>
</main>
</body>
</html>
`;
  }

  /**
   * Admit one operation through the owning authority. Drain fences NEW
   * admissions; already-admitted durable work continues at the owner.
   */
  async admit(request: AdmissionRequest): Promise<AdmissionDecision> {
    if (
      !request ||
      typeof request.session_id !== 'string' ||
      request.session_id.trim().length === 0 ||
      typeof request.operation_id !== 'string' ||
      request.operation_id.trim().length === 0
    ) {
      return {
        accepted: false,
        fenced: false,
        code: 'ADMISSION_INVALID',
        detail: 'An admission requires a non-empty session_id and operation_id.',
        recovery: 'Supply the durable session id and the caller operation identity.',
      };
    }

    if (this.draining || this.state === 'draining') {
      return {
        accepted: false,
        fenced: true,
        code: 'SERVICE_DRAINING',
        detail: 'The service is draining and fences new admissions.',
        recovery:
          'Wait for the restart to complete, then retry the admission against the owning authority.',
      };
    }

    if (this.state === 'reused') {
      return {
        accepted: false,
        fenced: false,
        code: 'SERVICE_NOT_ACTIVE',
        detail:
          'This handle reused an existing service; admissions belong to the owning process, not to the reusing launcher.',
        recovery: 'Send the admission through the verified origin that owns the service.',
      };
    }

    if (this.state !== 'running' || !this.server) {
      return {
        accepted: false,
        fenced: false,
        code: 'SERVICE_NOT_ACTIVE',
        detail: 'The front-door service is not running.',
        recovery: 'Start the local service, then retry the admission.',
      };
    }

    if (!this.options.admissionSink) {
      return {
        accepted: false,
        fenced: false,
        code: 'ADMISSION_SINK_UNBOUND',
        detail:
          'No owning admission authority is bound; the service never claims a queue admission as durable work.',
        recovery:
          'Bind the canonical admission port (approval front door + durable producer) in the composition root.',
      };
    }

    try {
      const receipt = await this.options.admissionSink(request);
      return { accepted: true, fenced: false, receipt };
    } catch (error) {
      return {
        accepted: false,
        fenced: false,
        code: 'ADMISSION_SINK_FAILED',
        detail: error instanceof Error ? error.message : String(error),
        recovery:
          'The owning authority refused or failed the admission; read its receipt and retry idempotently.',
      };
    }
  }

  /** Graceful drain: stop admitting, keep serving existing sessions. */
  drain(): DrainOutcome {
    if (this.state === 'reused') {
      return {
        drained: false,
        fenced: false,
        origin: this.origin,
        reason: 'REUSED_SERVICE_NOT_OWNED',
      };
    }
    if (this.state !== 'running' && this.state !== 'draining') {
      return {
        drained: false,
        fenced: false,
        origin: this.origin,
        reason: 'SERVICE_NOT_ACTIVE',
      };
    }
    this.state = 'draining';
    this.draining = true;
    return { drained: true, fenced: true, origin: this.origin, reason: null };
  }

  /**
   * Stop the listener this handle owns. A reused handle never closes the
   * owning service (launcher exit must not stop admitted work).
   */
  async stop(): Promise<StopOutcome> {
    if (this.state === 'reused') {
      return { stopped: false, reason: 'REUSED_SERVICE_NOT_OWNED' };
    }
    if (!this.server) {
      this.state = this.state === 'idle' ? 'stopped' : this.state;
      return { stopped: false, reason: 'ALREADY_STOPPED' };
    }
    this.state = 'draining';
    this.draining = true;
    const server = this.server;
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
    this.server = null;
    this.state = 'stopped';
    return { stopped: true, reason: null };
  }

  /** Layered readiness against this handle's verified origin. */
  readiness(options: ReadinessOptions = {}): Promise<ServiceReadiness> {
    return evaluateServiceReadiness(
      { ...this.options.readiness, origin: this.origin },
      options,
    );
  }

  /**
   * Resolve and optionally open a session URL. A browser-open failure
   * preserves the verified URL; a blocked target opens nothing.
   */
  openSession(
    record: SessionAuthorityRecord,
    options: { open?: boolean } = {},
  ): OpenSessionResult {
    const target = resolveSessionTarget(record, { origin: this.origin });
    if (target.kind === 'blocked') {
      return { target, browser: null };
    }
    if (options.open === false) {
      return { target, browser: null };
    }
    const opener =
      this.options.openUrl ??
      ((url: string): BrowserOpenResult => openCouncilUrl(url));
    return { target, browser: opener(target.url) };
  }
}

type BodyResult =
  | { ok: true; value: unknown }
  | {
      ok: false;
      status: number;
      code: string;
      detail: string;
      recovery: string;
    };

function readJsonBody(req: IncomingMessage): Promise<BodyResult> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    let size = 0;
    let settled = false;
    const finish = (result: BodyResult): void => {
      if (settled) return;
      settled = true;
      resolve(result);
    };
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        finish({
          ok: false,
          status: 413,
          code: 'ADMISSION_BODY_TOO_LARGE',
          detail: `An admission body must be at most ${MAX_BODY_BYTES} bytes.`,
          recovery: 'Send a bounded admission payload.',
        });
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('error', (error) => {
      finish({
        ok: false,
        status: 400,
        code: 'ADMISSION_BODY_UNREADABLE',
        detail: error.message,
        recovery: 'Retry the admission with a readable JSON body.',
      });
    });
    req.on('end', () => {
      if (settled) return;
      const text = Buffer.concat(chunks).toString('utf8');
      if (text.trim().length === 0) {
        finish({
          ok: false,
          status: 400,
          code: 'ADMISSION_BODY_EMPTY',
          detail: 'An admission requires a JSON body.',
          recovery: 'Send a JSON admission with session_id and operation_id.',
        });
        return;
      }
      try {
        finish({ ok: true, value: JSON.parse(text) as unknown });
      } catch {
        finish({
          ok: false,
          status: 400,
          code: 'ADMISSION_BODY_INVALID_JSON',
          detail: 'The admission body is not valid JSON.',
          recovery: 'Send a JSON admission with session_id and operation_id.',
        });
      }
    });
  });
}

/** Convenience export for the composition root's local session URL. */
export function localSessionUrl(origin: string, sessionId: string): string {
  return sessionUrl(origin, sessionId);
}
