/**
 * Host PDF renderer capability (CWE-038 PDF deliverable, directive
 * Section 24.3; CTR-136).
 *
 * The print HTML produced by `renderPrintHtml` is the document; this
 * module turns it into real PDF bytes with a renderer the host already
 * has. Nothing new is added to the dependency bill: the same headless
 * Chrome / CUPS filter probe the shipped artifact renderer
 * (`scripts/render-counsel-artifact.mjs`) uses is reused here, extended
 * with the Playwright browser cache paths a box may already carry.
 *
 * Honesty rules carried from CWE-038:
 * - no renderer on the host means the export refuses with
 *   EXPORT_FORMAT_NOT_READY naming the missing piece; bytes are never
 *   faked, and HTML is never renamed `.pdf`;
 * - a renderer that exits non-zero, times out, writes nothing, or
 *   writes something that is not a PDF is EXPORT_RENDER_FAILED;
 * - volatile PDF metadata (`/CreationDate`, `/ModDate`, `/ID`) is
 *   zeroed in place so the same report model renders to the same bytes
 *   and a replay re-checks the same SHA-256. The rewrite is
 *   length-preserving, so the PDF cross-reference table stays valid.
 *
 * Module-load discipline: no process is spawned and no environment is
 * read at import time. `probe()` is pure inspection (file existence),
 * never a browser launch.
 */

import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';

import { ReportExportError } from './errors.js';

export type PdfRenderMethod = 'chrome-headless' | 'cupsfilter';

export interface PdfCapability {
  available: boolean;
  method: PdfRenderMethod | null;
  executable: string | null;
  /** Human detail for the honest not-ready refusal. */
  detail: string;
}

export interface PdfRenderPort {
  probe(): PdfCapability;
  /** Render one print document to PDF bytes; throws a typed error, never returns HTML. */
  render(html: string, options?: { timeout_ms?: number }): Promise<Buffer>;
}

export const PDF_RENDERER_MISSING_PIECE =
  'no headless Chrome/Chromium or CUPS PDF filter (cupsfilter) is installed or discoverable on this host; install one, or set CHROME_PATH to a Chrome/Chromium binary, then retry the export';

const MIN_PDF_BYTES = 1000;

function whichSync(command: string, env: NodeJS.ProcessEnv): string | null {
  const pathVar = env.PATH ?? '';
  for (const dir of pathVar.split(delimiter)) {
    if (dir === '') continue;
    const candidate = join(dir, command);
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      // not in this directory; keep scanning
    }
  }
  return null;
}

/** Browser binaries a Playwright install leaves in the user cache. */
function playwrightCandidates(env: NodeJS.ProcessEnv): string[] {
  const home = env.HOME ?? homedir();
  const roots = [
    join(home, 'Library', 'Caches', 'ms-playwright'),
    join(home, '.cache', 'ms-playwright'),
  ];
  const found: string[] = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    let names: string[];
    try {
      names = readdirSync(root).sort();
    } catch {
      continue;
    }
    for (const name of names) {
      if (!name.startsWith('chromium')) continue;
      const dir = join(root, name);
      found.push(
        join(dir, 'chrome-mac', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
        join(dir, 'chrome-mac-arm64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
        join(dir, 'chrome-mac-x64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
        join(dir, 'chrome-linux', 'chrome'),
        join(dir, 'chrome-linux64', 'chrome'),
        join(dir, 'chrome-linux', 'headless_shell'),
        join(dir, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell'),
        join(dir, 'chrome-headless-shell-mac-x64', 'chrome-headless-shell'),
        join(dir, 'chrome-headless-shell-linux64', 'chrome-headless-shell'),
      );
    }
  }
  return found;
}

/**
 * Pure inspection: which PDF renderer this host has, if any. No spawn,
 * no network, never throws.
 */
export function probePdfCapability(env: NodeJS.ProcessEnv = process.env): PdfCapability {
  if (env.COUNCIL_PDF_DISABLED === '1') {
    return {
      available: false,
      method: null,
      executable: null,
      detail: 'PDF rendering is switched off on this host (COUNCIL_PDF_DISABLED=1)',
    };
  }
  try {
    const chromeCandidates = [
      env.CHROME_PATH,
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      join(env.HOME ?? homedir(), 'Applications', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome'),
      ...playwrightCandidates(env),
      whichSync('google-chrome', env),
      whichSync('google-chrome-stable', env),
      whichSync('chromium', env),
      whichSync('chromium-browser', env),
      whichSync('chrome-headless-shell', env),
      whichSync('chromium-headless-shell', env),
    ];
    for (const candidate of chromeCandidates) {
      if (candidate && existsSync(candidate)) {
        return {
          available: true,
          method: 'chrome-headless',
          executable: candidate,
          detail: `headless Chrome renderer at ${candidate}`,
        };
      }
    }
    const cups = whichSync('cupsfilter', env);
    if (cups) {
      return {
        available: true,
        method: 'cupsfilter',
        executable: cups,
        detail: `CUPS PDF filter at ${cups}`,
      };
    }
    return {
      available: false,
      method: null,
      executable: null,
      detail: PDF_RENDERER_MISSING_PIECE,
    };
  } catch {
    return {
      available: false,
      method: null,
      executable: null,
      detail: PDF_RENDERER_MISSING_PIECE,
    };
  }
}

interface ProcessOutcome {
  status: number | null;
  stdout: Buffer;
  stderr: string;
}

function runProcess(
  command: string,
  args: readonly string[],
  timeoutMs: number,
): Promise<ProcessOutcome> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      fn();
    };
    const child = spawn(command, [...args], { stdio: ['ignore', 'pipe', 'pipe'] });
    const stdout: Buffer[] = [];
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      finish(() =>
        reject(
          new ReportExportError(
            'EXPORT_RENDER_FAILED',
            `the PDF renderer did not finish within ${timeoutMs} ms; no PDF was produced`,
          ),
        ),
      );
    }, timeoutMs);
    timer.unref?.();
    child.stdout?.on('data', (chunk: Buffer) => stdout.push(chunk));
    child.stderr?.on('data', (chunk: Buffer) => {
      if (stderr.length < 4096) stderr += chunk.toString('utf8');
    });
    child.on('error', (error: Error) => {
      clearTimeout(timer);
      finish(() =>
        reject(
          new ReportExportError(
            'EXPORT_RENDER_FAILED',
            `the PDF renderer could not start: ${error.message}`,
          ),
        ),
      );
    });
    child.on('close', (code: number | null) => {
      clearTimeout(timer);
      finish(() => resolve({ status: code, stdout: Buffer.concat(stdout), stderr }));
    });
  });
}

/** Real-PDF assertion: magic header, trailer, and a non-trivial size. */
export function validatePdfBytes(bytes: Uint8Array): void {
  if (bytes.length < MIN_PDF_BYTES) {
    throw new ReportExportError(
      'EXPORT_RENDER_FAILED',
      `the renderer produced ${bytes.length} bytes, which is not a complete PDF`,
    );
  }
  const head = Buffer.from(bytes.subarray(0, 5)).toString('latin1');
  if (head !== '%PDF-') {
    throw new ReportExportError(
      'EXPORT_RENDER_FAILED',
      'the renderer output does not start with the %PDF- header; it is not a PDF and will not be served as one',
    );
  }
  const tail = Buffer.from(bytes.subarray(Math.max(0, bytes.length - 2048))).toString('latin1');
  if (!tail.includes('%%EOF')) {
    throw new ReportExportError(
      'EXPORT_RENDER_FAILED',
      'the renderer output has no %%EOF trailer; it is a truncated PDF and will not be served',
    );
  }
}

/**
 * Zero the volatile PDF metadata a renderer stamps from the clock so
 * the same report model always produces the same bytes. Length-
 * preserving, so the cross-reference table offsets stay correct.
 */
export function pinVolatilePdfMetadata(bytes: Uint8Array): Buffer {
  const text = Buffer.from(bytes).toString('latin1');
  const zeroDigits = (match: string, prefix: string, value: string, suffix: string): string =>
    `${prefix}${value.replace(/[0-9]/g, '0')}${suffix}`;
  const pinned = text
    .replace(/(\/CreationDate\s*\()([^)]*)(\))/g, zeroDigits)
    .replace(/(\/ModDate\s*\()([^)]*)(\))/g, zeroDigits)
    .replace(
      /(\/ID\s*\[\s*<)([0-9A-Fa-f]+)(>\s*<)([0-9A-Fa-f]+)(>)/g,
      (_match, open: string, first: string, between: string, second: string, close: string) =>
        `${open}${'0'.repeat(first.length)}${between}${'0'.repeat(second.length)}${close}`,
    );
  return Buffer.from(pinned, 'latin1');
}

export function sha256OfBytes(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

/**
 * The host renderer port. `render` writes the print document to a
 * private temporary directory, runs the probed renderer, validates and
 * pins the bytes, and removes every temporary file before returning.
 */
export function createHostPdfRenderer(
  env: NodeJS.ProcessEnv = process.env,
): PdfRenderPort {
  return {
    probe(): PdfCapability {
      return probePdfCapability(env);
    },
    async render(html: string, options: { timeout_ms?: number } = {}): Promise<Buffer> {
      const capability = probePdfCapability(env);
      if (!capability.available || capability.executable === null || capability.method === null) {
        throw new ReportExportError(
          'EXPORT_FORMAT_NOT_READY',
          `The pdf deliverable is registered but not ready on this host: ${capability.detail}.`,
          { missing_piece: capability.detail },
        );
      }
      const timeoutMs = options.timeout_ms ?? 60_000;
      const workDir = mkdtempSync(join(tmpdir(), 'council-report-pdf-'));
      const htmlPath = join(workDir, 'report.html');
      const outPath = join(workDir, 'report.pdf');
      try {
        writeFileSync(htmlPath, html, { encoding: 'utf8', mode: 0o600 });
        let raw: Buffer;
        if (capability.method === 'chrome-headless') {
          const outcome = await runProcess(
            capability.executable,
            [
              '--headless',
              '--disable-gpu',
              '--disable-extensions',
              '--disable-background-networking',
              '--no-first-run',
              '--no-default-browser-check',
              '--no-pdf-header-footer',
              `--user-data-dir=${join(workDir, 'profile')}`,
              `--print-to-pdf=${outPath}`,
              htmlPath,
            ],
            timeoutMs,
          );
          if (outcome.status !== 0 || !existsSync(outPath)) {
            throw new ReportExportError(
              'EXPORT_RENDER_FAILED',
              `the headless Chrome renderer exited ${String(outcome.status)} without a PDF${outcome.stderr ? `: ${outcome.stderr.trim().split('\n')[0]}` : ''}`,
            );
          }
          raw = readFileSync(outPath);
        } else {
          const outcome = await runProcess(
            capability.executable,
            ['-m', 'application/pdf', htmlPath],
            timeoutMs,
          );
          if (outcome.status !== 0 || outcome.stdout.length === 0) {
            throw new ReportExportError(
              'EXPORT_RENDER_FAILED',
              `the CUPS PDF filter exited ${String(outcome.status)} without PDF bytes`,
            );
          }
          raw = outcome.stdout;
        }
        validatePdfBytes(raw);
        return pinVolatilePdfMetadata(raw);
      } finally {
        rmSync(workDir, { recursive: true, force: true });
      }
    },
  };
}
