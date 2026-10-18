/**
 * Installed-runtime receipt resolution (WER-005).
 *
 * The skill must reach the CLI that WER-004's installer actually activated,
 * not a path guessed from the process working directory and not a `dist/`
 * folder generated inside a checkout. The installer's own staged-release
 * receipt is the single source of truth, consumed here unchanged:
 *
 *   <prefix>/active.json                       wise-elders.council-runtime-active/v1
 *   <prefix>/receipts/<releaseId>.release.json wise-elders.council-runtime-release/v1
 *   <prefix>/receipts/<releaseId>.artifact.json wise-elders.council-runtime-artifact/v1
 *   <prefix>/releases/<releaseId>/dist/blackceo-council.mjs
 *
 * Resolution never reads `process.cwd()`. A relative COUNCIL_RUNTIME_PREFIX
 * is refused rather than silently resolved against the working directory,
 * because that would reintroduce the exact dependency this module removes.
 *
 * When no valid receipt exists the result is an explicit failure carrying
 * the exact paths checked and a concrete recovery command. Callers must not
 * substitute improvised advice, and this module never fabricates a release.
 */

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { basename, isAbsolute, join, resolve } from 'node:path';

/** Same variable the installer honors (install-runtime.mjs defaultPrefix). */
export const RUNTIME_PREFIX_ENV = 'COUNCIL_RUNTIME_PREFIX';

/** Receipt schemas owned by WER-004's installer. Do not fork these. */
export const ACTIVE_RECEIPT_SCHEMA = 'wise-elders.council-runtime-active/v1';
export const RELEASE_RECEIPT_SCHEMA = 'wise-elders.council-runtime-release/v1';
export const ARTIFACT_RECEIPT_SCHEMA = 'wise-elders.council-runtime-artifact/v1';

/** Required build product the installer records and this module resolves. */
export const INSTALLED_CLI_RELATIVE = 'dist/blackceo-council.mjs';

export const INSTALLER_SCRIPT_RELATIVE = join('scripts', 'install-runtime.mjs');

export type InstalledCliFailureCode =
  | 'RUNTIME_PREFIX_INVALID'
  | 'RUNTIME_NOT_INSTALLED'
  | 'RUNTIME_RECEIPT_INVALID'
  | 'RUNTIME_RELEASE_MISSING'
  | 'RUNTIME_ARTIFACT_INVALID';

export interface InstalledCliSuccess {
  ok: true;
  prefix: string;
  releaseId: string;
  releasePath: string;
  /** The active pointer the installer atomically replaced. */
  activeReceiptPath: string;
  /** WER-004's staged-release receipt for this release. */
  releaseReceiptPath: string;
  artifactReceiptPath: string;
  /** Absolute path to the installed CLI. Never a checkout `dist/` path. */
  cliPath: string;
  cliSha256: string;
  nodeExecutable: string;
  nodeVersion: string;
  dataDir: string;
  sourceManifestDigest: string;
  artifactDigest: string;
}

export interface InstalledCliFailure {
  ok: false;
  code: InstalledCliFailureCode;
  message: string;
  /** Concrete next action, naming the installer command and the prefix. */
  recovery: string;
  /** Every receipt/release path this resolution actually probed. */
  checked: string[];
}

export type InstalledCliResolution = InstalledCliSuccess | InstalledCliFailure;

export interface ResolveInstalledCliOptions {
  /** Explicit prefix. Default: COUNCIL_RUNTIME_PREFIX, else the installer default. */
  prefix?: string;
  /** Home directory used only for the installer's default prefix. */
  homeDir?: string;
  env?: NodeJS.ProcessEnv;
  /** Skill folder, used only to spell a concrete installer path in recovery. */
  skillRoot?: string;
}

/** Mirrors install-runtime.mjs defaultPrefix exactly. */
export function defaultRuntimePrefix(
  env: NodeJS.ProcessEnv = process.env,
  home: string = homedir(),
): string {
  const fromEnv = env[RUNTIME_PREFIX_ENV];
  if (fromEnv && fromEnv.trim().length > 0) return resolve(fromEnv);
  if (platform() === 'win32') {
    return join(env.LOCALAPPDATA || home, 'blackceo', 'council-runtime');
  }
  return join(home, '.local', 'share', 'blackceo', 'council-runtime');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readJson(path: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function sha256File(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function recoveryFor(prefix: string, skillRoot: string | undefined): string {
  const installer = skillRoot
    ? join(skillRoot, INSTALLER_SCRIPT_RELATIVE)
    : join('<skill-folder>', INSTALLER_SCRIPT_RELATIVE);
  return (
    'Install or repair the runtime, then retry this command. Run exactly:\n' +
    `  node ${JSON.stringify(installer)} --prefix ${JSON.stringify(prefix)}\n` +
    `Set ${RUNTIME_PREFIX_ENV} only to an absolute path. Do not point it at a checkout dist folder.`
  );
}

function failure(
  code: InstalledCliFailureCode,
  message: string,
  prefix: string,
  checked: string[],
  skillRoot: string | undefined,
): InstalledCliFailure {
  return {
    ok: false,
    code,
    message,
    recovery: recoveryFor(prefix, skillRoot),
    checked: [...checked],
  };
}

/** Treat receipts as path segments, never as path fragments. */
function isSafeReleaseId(releaseId: string): boolean {
  return (
    releaseId.length > 0 &&
    releaseId !== '.' &&
    releaseId !== '..' &&
    !releaseId.includes('/') &&
    !releaseId.includes('\\') &&
    basename(releaseId) === releaseId
  );
}

/**
 * Resolve the ACTIVE installed CLI through WER-004's receipts.
 *
 * Total: every filesystem/parse problem becomes a typed failure result, so a
 * skill front door can print the recovery instead of crashing or inventing a
 * path.
 */
export function resolveInstalledCli(
  options: ResolveInstalledCliOptions = {},
): InstalledCliResolution {
  const env = options.env ?? process.env;
  const home = options.homeDir ?? homedir();
  const checked: string[] = [];

  let prefix: string;
  const explicitPrefix = options.prefix ?? env[RUNTIME_PREFIX_ENV];
  if (explicitPrefix !== undefined && explicitPrefix !== null && String(explicitPrefix).length > 0) {
    if (!isAbsolute(String(explicitPrefix))) {
      const attempted = String(explicitPrefix);
      return {
        ok: false,
        code: 'RUNTIME_PREFIX_INVALID',
        message:
          `Council runtime prefix "${attempted}" is not absolute. A relative prefix would ` +
          'make resolution depend on the process working directory, which is exactly what ' +
          'the installed-runtime bridge must not do.',
        recovery: recoveryFor(attempted, options.skillRoot),
        checked: [attempted],
      };
    }
    prefix = resolve(String(explicitPrefix));
  } else {
    prefix = defaultRuntimePrefix(env, home);
  }

  const activeReceiptPath = join(prefix, 'active.json');
  checked.push(activeReceiptPath);
  if (!existsSync(activeReceiptPath)) {
    return failure(
      'RUNTIME_NOT_INSTALLED',
      `No active Council runtime receipt exists at ${activeReceiptPath}, so no installed CLI can be resolved.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  const active = readJson(activeReceiptPath);
  if (!active) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The active receipt at ${activeReceiptPath} is not readable JSON.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (active.schema !== ACTIVE_RECEIPT_SCHEMA) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The active receipt at ${activeReceiptPath} has schema ${JSON.stringify(active.schema)}; expected ${ACTIVE_RECEIPT_SCHEMA}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  const releaseId = typeof active.releaseId === 'string' ? active.releaseId : '';
  if (!isSafeReleaseId(releaseId)) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The active receipt at ${activeReceiptPath} records an unusable release id ${JSON.stringify(active.releaseId)}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  const expectedReleasePath = join(prefix, 'releases', releaseId);
  const recordedReleasePath =
    typeof active.releasePath === 'string' && isAbsolute(active.releasePath)
      ? resolve(active.releasePath)
      : '';
  checked.push(expectedReleasePath);
  if (recordedReleasePath !== expectedReleasePath) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The active receipt release path ${JSON.stringify(active.releasePath)} does not match the installer layout ${expectedReleasePath}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (!isDirectory(expectedReleasePath)) {
    return failure(
      'RUNTIME_RELEASE_MISSING',
      `The active release directory ${expectedReleasePath} does not exist. The receipt points at a missing release.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  const releaseReceiptPath = join(prefix, 'receipts', `${releaseId}.release.json`);
  checked.push(releaseReceiptPath);
  const recordedReceiptPath =
    typeof active.receiptPath === 'string' && isAbsolute(active.receiptPath)
      ? resolve(active.receiptPath)
      : '';
  if (recordedReceiptPath !== releaseReceiptPath) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The active receipt names release receipt ${JSON.stringify(active.receiptPath)}; the installer writes ${releaseReceiptPath}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (!existsSync(releaseReceiptPath)) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The staged-release receipt ${releaseReceiptPath} is missing.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  const releaseReceipt = readJson(releaseReceiptPath);
  if (!releaseReceipt || releaseReceipt.schema !== RELEASE_RECEIPT_SCHEMA) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The staged-release receipt ${releaseReceiptPath} is unreadable or has the wrong schema.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (releaseReceipt.releaseId !== releaseId) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The staged-release receipt ${releaseReceiptPath} records release ${JSON.stringify(releaseReceipt.releaseId)}, not ${JSON.stringify(releaseId)}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  for (const field of ['sourceManifestDigest', 'artifactDigest'] as const) {
    if (
      typeof active[field] !== 'string' ||
      active[field] !== releaseReceipt[field]
    ) {
      return failure(
        'RUNTIME_RECEIPT_INVALID',
        `Active and staged-release receipts disagree on ${field}, so the active pointer cannot be trusted.`,
        prefix,
        checked,
        options.skillRoot,
      );
    }
  }

  const artifactReceiptPath = join(prefix, 'receipts', `${releaseId}.artifact.json`);
  checked.push(artifactReceiptPath);
  const artifactReceipt = readJson(artifactReceiptPath);
  if (!artifactReceipt || artifactReceipt.schema !== ARTIFACT_RECEIPT_SCHEMA) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The generated-artifact receipt ${artifactReceiptPath} is unreadable or has the wrong schema.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (artifactReceipt.releaseId !== releaseId) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The generated-artifact receipt ${artifactReceiptPath} records release ${JSON.stringify(artifactReceipt.releaseId)}, not ${JSON.stringify(releaseId)}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  if (artifactReceipt.digest !== active.artifactDigest) {
    return failure(
      'RUNTIME_RECEIPT_INVALID',
      `The generated-artifact receipt digest does not match the active pointer, so the installed CLI is not the activated one.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  const cliPath = join(expectedReleasePath, INSTALLED_CLI_RELATIVE);
  checked.push(cliPath);
  if (!isFile(cliPath)) {
    return failure(
      'RUNTIME_ARTIFACT_INVALID',
      `The activated release has no CLI at ${cliPath}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  const entries = Array.isArray(artifactReceipt.entries) ? artifactReceipt.entries : [];
  const recorded = entries.find(
    (entry) =>
      isRecord(entry) &&
      entry.path === INSTALLED_CLI_RELATIVE.replace(/\\/g, '/') &&
      typeof entry.sha256 === 'string',
  );
  if (!recorded || typeof recorded.sha256 !== 'string') {
    return failure(
      'RUNTIME_ARTIFACT_INVALID',
      `The generated-artifact receipt records no hash for ${INSTALLED_CLI_RELATIVE}.`,
      prefix,
      checked,
      options.skillRoot,
    );
  }
  // ponytail: only the activated CLI entry is re-hashed, not the whole dist
  // manifest; upgrade to a full manifest re-hash if release tampering beyond
  // the entry point ever becomes a threat model.
  const actualSha256 = sha256File(cliPath);
  if (actualSha256 !== recorded.sha256) {
    return failure(
      'RUNTIME_ARTIFACT_INVALID',
      `The installed CLI at ${cliPath} does not match the receipt hash (${actualSha256} != ${recorded.sha256}).`,
      prefix,
      checked,
      options.skillRoot,
    );
  }

  return {
    ok: true,
    prefix,
    releaseId,
    releasePath: expectedReleasePath,
    activeReceiptPath,
    releaseReceiptPath,
    artifactReceiptPath,
    cliPath,
    cliSha256: actualSha256,
    nodeExecutable:
      typeof active.nodeExecutable === 'string' ? active.nodeExecutable : '',
    nodeVersion: typeof active.nodeVersion === 'string' ? active.nodeVersion : '',
    dataDir: typeof active.dataDir === 'string' ? active.dataDir : '',
    sourceManifestDigest: active.sourceManifestDigest as string,
    artifactDigest: active.artifactDigest as string,
  };
}
