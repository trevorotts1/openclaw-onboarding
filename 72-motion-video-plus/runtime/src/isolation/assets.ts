// Approved-asset fetching and the controlled local origin (MG-029).
//
// The pipeline's asset rule is: bytes are fetched during PREPARATION,
// verified, and only then rendered; a render never fetches. This
// module is the preparation-side fetcher and the render-side server
// that together implement that rule for URL-sourced assets:
//
//   fetchApprovedAsset  downloads an asset ONLY when the caller
//     supplies the sha256 recorded for it in the job's intake record.
//     "Approved" means exactly that recorded hash: bytes that do not
//     hash to it are refused and nothing is staged. Fetch policy:
//     https only, except http to a loopback host (local intake
//     tooling); redirects are followed hop by hop and every hop must
//     satisfy the same policy; a byte cap bounds the download. The
//     verified file lands in the staging directory atomically under a
//     single safe path segment.
//
//   AssetOriginServer  serves a staging directory over HTTP on
//     127.0.0.1 only. Renders that address assets by URL use this
//     origin and no other: it serves nothing outside the staging root
//     (traversal and symlink escapes are refused and logged), speaks
//     GET/HEAD only, and keeps a request log so a render's asset
//     traffic is auditable. It is a file server for verified bytes,
//     not a proxy: it never fetches anything itself.

import { createHash } from "node:crypto";
import { createReadStream, existsSync, mkdirSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { basename, extname, join, resolve, sep } from "node:path";
import { IsolationError } from "./errors";
import { sanitizeJobSegment } from "./paths";

export interface ApprovedAssetSource {
  url: string;
  /** The sha256 recorded for this asset at intake. The fetch is
   * approved for exactly these bytes. */
  sha256: string;
  /** Staged file name (single path segment). Defaults to the URL
   * path's basename. */
  fileName?: string;
}

export interface FetchedAsset {
  /** Absolute path of the staged, verified file. */
  path: string;
  fileName: string;
  sha256: string;
  bytes: number;
}

const DEFAULT_MAX_BYTES = 256 * 1024 * 1024;
const MAX_REDIRECTS = 5;

function isLoopbackHost(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1" ||
    hostname === "[::1]"
  );
}

function checkFetchUrl(raw: string): URL {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new IsolationError("ASSET_FETCH_REFUSED", `asset URL does not parse: ${raw}`);
  }
  if (url.protocol === "https:") return url;
  if (url.protocol === "http:" && isLoopbackHost(url.hostname)) return url;
  throw new IsolationError(
    "ASSET_FETCH_REFUSED",
    `asset URL ${raw} violates the fetch policy: https only, except http to a loopback host`
  );
}

function stagedFileName(source: ApprovedAssetSource, url: URL): string {
  const raw = source.fileName ?? basename(url.pathname);
  const cleaned = sanitizeJobSegment(raw ?? "");
  if (!cleaned || cleaned === "_" || raw.includes("/") || raw.includes("\\")) {
    throw new IsolationError(
      "ASSET_NAME_INVALID",
      `staged asset name "${raw}" is not a single safe path segment`
    );
  }
  return cleaned;
}

type FetchImpl = (url: string, init?: RequestInit) => Promise<Response>;

/** Fetch one approved asset into the staging directory and verify its
 * bytes against the recorded hash before anything is staged. */
export async function fetchApprovedAsset(
  source: ApprovedAssetSource,
  stagingDir: string,
  opts?: { maxBytes?: number; fetchImpl?: FetchImpl }
): Promise<FetchedAsset> {
  const maxBytes = opts?.maxBytes ?? DEFAULT_MAX_BYTES;
  const fetchImpl: FetchImpl = opts?.fetchImpl ?? ((u, i) => fetch(u, i));
  let url = checkFetchUrl(source.url);
  let response: Response | null = null;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
    response = await fetchImpl(url.toString(), { redirect: "manual" });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (!location) {
        throw new IsolationError(
          "ASSET_FETCH_REFUSED",
          `asset URL ${url} redirected without a Location header`
        );
      }
      if (hop === MAX_REDIRECTS) {
        throw new IsolationError(
          "ASSET_FETCH_REFUSED",
          `asset URL ${source.url} exceeded ${MAX_REDIRECTS} redirects`
        );
      }
      url = checkFetchUrl(new URL(location, url).toString());
      continue;
    }
    break;
  }
  if (!response || !response.ok) {
    throw new IsolationError(
      "ASSET_FETCH_REFUSED",
      `asset URL ${url} returned HTTP ${response?.status ?? "no response"}`
    );
  }
  const declaredLength = Number(response.headers.get("content-length") ?? "NaN");
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new IsolationError(
      "ASSET_FETCH_REFUSED",
      `asset at ${url} declares ${declaredLength} bytes, above the ${maxBytes} byte cap`
    );
  }
  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length > maxBytes) {
    throw new IsolationError(
      "ASSET_FETCH_REFUSED",
      `asset at ${url} delivered ${buffer.length} bytes, above the ${maxBytes} byte cap`
    );
  }
  const sha256 = createHash("sha256").update(buffer).digest("hex");
  if (sha256 !== source.sha256.toLowerCase()) {
    throw new IsolationError(
      "ASSET_HASH_MISMATCH",
      `asset at ${url} hashed to ${sha256}, not the recorded ${source.sha256}; ` +
        "the fetched bytes are not the approved bytes and nothing was staged"
    );
  }
  const fileName = stagedFileName(source, url);
  mkdirSync(stagingDir, { recursive: true });
  const finalPath = join(stagingDir, fileName);
  const tmpPath = `${finalPath}.tmp-${process.pid}`;
  writeFileSync(tmpPath, buffer);
  renameSync(tmpPath, finalPath);
  return { path: finalPath, fileName, sha256, bytes: buffer.length };
}

const CONTENT_TYPES: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".txt": "text/plain",
};

export interface OriginRequest {
  method: string;
  path: string;
  status: number;
}

export class AssetOriginServer {
  readonly rootDir: string;
  port = 0;
  url = "";
  /** Every request the origin answered or refused, in order. */
  readonly requests: OriginRequest[] = [];
  private server: Server | null = null;

  private constructor(rootDir: string) {
    this.rootDir = rootDir;
  }

  static async serve(
    rootDir: string,
    opts?: { port?: number }
  ): Promise<AssetOriginServer> {
    const origin = new AssetOriginServer(resolve(rootDir));
    const server = createServer((req, res) => origin.handle(req, res));
    origin.server = server;
    await new Promise<void>((resolveListen, rejectListen) => {
      server.once("error", rejectListen);
      server.listen(opts?.port ?? 0, "127.0.0.1", () => resolveListen());
    });
    const address = server.address();
    if (!address || typeof address === "string") {
      throw new IsolationError("ASSET_FETCH_REFUSED", "asset origin did not bind a TCP port");
    }
    origin.port = address.port;
    origin.url = `http://127.0.0.1:${address.port}`;
    return origin;
  }

  private handle(req: IncomingMessage, res: ServerResponse): void {
    const record = (status: number, path: string): void => {
      this.requests.push({ method: req.method ?? "?", path, status });
    };
    const rawPath = (req.url ?? "/").split("?")[0];
    if (req.method !== "GET" && req.method !== "HEAD") {
      record(405, rawPath);
      res.writeHead(405, { "Content-Type": "text/plain" });
      res.end("method not allowed");
      return;
    }
    let decoded: string;
    try {
      decoded = decodeURIComponent(rawPath);
    } catch {
      record(400, rawPath);
      res.writeHead(400, { "Content-Type": "text/plain" });
      res.end("bad path encoding");
      return;
    }
    const rel = decoded.replace(/^\/+/, "");
    const abs = resolve(this.rootDir, rel);
    if (abs !== this.rootDir && !abs.startsWith(this.rootDir + sep)) {
      record(403, rawPath);
      res.writeHead(403, { "Content-Type": "text/plain" });
      res.end("outside the asset root");
      return;
    }
    if (!existsSync(abs) || !statSync(abs).isFile()) {
      record(404, rawPath);
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("not found");
      return;
    }
    // Symlink containment: the real path must stay under the real root.
    let realRoot = this.rootDir;
    try {
      realRoot = realpathSync(this.rootDir);
    } catch {
      realRoot = this.rootDir;
    }
    const realAbs = realpathSync(abs);
    if (realAbs !== realRoot && !realAbs.startsWith(realRoot + sep)) {
      record(403, rawPath);
      res.writeHead(403, { "Content-Type": "text/plain" });
      res.end("outside the asset root");
      return;
    }
    const type = CONTENT_TYPES[extname(abs).toLowerCase()] ?? "application/octet-stream";
    record(200, rawPath);
    res.writeHead(200, {
      "Content-Type": type,
      "Content-Length": statSync(abs).size,
      "Cache-Control": "no-store",
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    createReadStream(abs).pipe(res);
  }

  async close(): Promise<void> {
    const server = this.server;
    if (!server) return;
    await new Promise<void>((resolveClose) => server.close(() => resolveClose()));
  }
}

/** Remove a staged asset file (cleanup helper for preparation code). */
export function removeStagedAsset(path: string): void {
  rmSync(path, { force: true });
}
