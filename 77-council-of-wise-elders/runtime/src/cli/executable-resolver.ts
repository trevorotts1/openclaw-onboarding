/**
 * Structured executable resolver for subprocess routes (WER-008 slice).
 *
 * The resolver turns ONE logical command name (or path) plus an argument
 * vector into a concrete launch plan. It is a pure function of the
 * platform, the environment and the filesystem lookup it is handed, so a
 * Windows shape can be proven in a simulated test without claiming a
 * native Windows run.
 *
 * Laws:
 * - No shell string is ever built for the prompt. The argument vector
 *   carries only the executable path and caller-supplied CLI arguments;
 *   prompt content travels on stdin (see subprocess-transport.ts).
 * - No WSL, no bash, no shebang, no symlink assumption. A `.ps1` file is
 *   invoked through PowerShell with `-File` and a real argv, never
 *   through a shell. A `.cmd`/`.bat` shim on Windows is the ONE place a
 *   command string exists (cmd.exe `/c`), and it is built from
 *   individually quoted, validated arguments that can never contain the
 *   prompt.
 * - Paths with spaces and non-ASCII characters are preserved byte for
 *   byte in the argv / quoted payload; nothing is re-encoded or
 *   normalized.
 * - A command that cannot be resolved fails with a typed error rather
 *   than falling back to a shell, PATH guess, or WSL bridge.
 */

import { statSync } from 'node:fs';
import { delimiter } from 'node:path';

export type ResolverPlatform = 'win32' | 'darwin' | 'linux' | (string & {});

export type InvocationKind =
  | 'native'
  | 'windows-cmd-shim'
  | 'windows-batch-shim'
  | 'powershell-script';

/** A launch plan: exactly what `spawn(file, args)` receives. */
export interface ResolvedInvocation {
  kind: InvocationKind;
  /** Executable handed to spawn (a shell only by name, never by string). */
  file: string;
  /** Argument vector. Never contains prompt content. */
  args: string[];
  /** The resolved native binary or shim script path. */
  target: string;
}

export type ResolverErrorCode =
  | 'EXECUTABLE_NOT_FOUND'
  | 'EXECUTABLE_ARGUMENT_UNSAFE'
  | 'EXECUTABLE_UNSUPPORTED_SCRIPT';

export class ExecutableResolutionError extends Error {
  readonly code: ResolverErrorCode;
  readonly retryable = false;
  constructor(code: ResolverErrorCode, message: string) {
    super(message);
    this.name = 'ExecutableResolutionError';
    this.code = code;
  }
}

export interface ResolveCommandInput {
  /** A command name looked up on PATH, or an explicit path. */
  command: string;
  /** CLI arguments, never prompt content. */
  args?: string[];
  /** Default: the host platform. Tests pass 'win32' explicitly. */
  platform?: ResolverPlatform;
  /** Default: process.env. */
  env?: NodeJS.ProcessEnv;
  /** Injectable file probe so resolution is testable without the real FS. */
  isFile?: (path: string) => boolean;
}

export const WINDOWS_PATH_EXTENSIONS = ['.com', '.exe', '.bat', '.cmd', '.ps1'] as const;

function defaultIsFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function isWindows(platform: ResolverPlatform): boolean {
  return platform === 'win32';
}

/** True when the command already names a location rather than a PATH name. */
export function looksLikePath(command: string): boolean {
  return (
    command.includes('/') ||
    command.includes('\\') ||
    /^[A-Za-z]:/.test(command) ||
    command.startsWith('.')
  );
}

function extensionOf(path: string): string {
  const match = /(\.[^./\\]+)$/.exec(path);
  return match ? match[1].toLowerCase() : '';
}

function withWindowsExtensions(command: string): string[] {
  // PATHEXT appends only when the command has no extension of its own.
  if (extensionOf(command) !== '') return [command];
  return WINDOWS_PATH_EXTENSIONS.map((suffix) => `${command}${suffix}`);
}

/**
 * Join with the target platform's separator. `node:path.join` uses the
 * HOST separator, which would corrupt a simulated Windows path on macOS.
 */
function joinFor(windows: boolean, dir: string, name: string): string {
  const separator = windows ? '\\' : '/';
  const trimmed = dir.replace(/[\\/]+$/, '');
  return trimmed.length === 0 ? `${separator}${name}` : `${trimmed}${separator}${name}`;
}

function pathCandidates(input: ResolveCommandInput, windows: boolean): string[] {
  const command = input.command;
  const executableSuffixes = windows ? withWindowsExtensions(command) : [command];
  if (looksLikePath(command)) {
    return executableSuffixes;
  }
  const env = input.env ?? process.env;
  const searchPath = windows ? (env.PATH ?? env.Path ?? '') : (env.PATH ?? '');
  const dirs = searchPath.split(windows ? ';' : delimiter).filter((dir) => dir.length > 0);
  const candidates: string[] = [];
  for (const dir of dirs) {
    for (const suffix of executableSuffixes) candidates.push(joinFor(windows, dir, suffix));
  }
  return candidates;
}

function firstExisting(
  input: ResolveCommandInput,
  windows: boolean,
): string {
  const isFile = input.isFile ?? defaultIsFile;
  for (const candidate of pathCandidates(input, windows)) {
    if (isFile(candidate)) return candidate;
  }
  throw new ExecutableResolutionError(
    'EXECUTABLE_NOT_FOUND',
    `The command ${JSON.stringify(input.command)} was not found${
      looksLikePath(input.command) ? '' : ' on PATH'
    } for platform ${input.platform ?? process.platform}; no shell fallback is attempted.`,
  );
}

/**
 * Quote one argument for the cmd.exe command line.
 *
 * The payload is only ever built from the resolved executable path and
 * caller CLI arguments. Control characters, quotes and `%` are refused:
 * cmd.exe performs environment expansion even inside quotes, and there is
 * no escaping form that is unconditionally safe. Refusing is honest and
 * cannot silently change an argument.
 */
export function quoteForCmdExe(argument: string): string {
  if (/["\r\n\0]/.test(argument)) {
    throw new ExecutableResolutionError(
      'EXECUTABLE_ARGUMENT_UNSAFE',
      `Argument ${JSON.stringify(argument)} contains a quote, newline or NUL; cmd.exe cannot carry it safely, so the launch is refused rather than mis-quoted.`,
    );
  }
  if (argument.includes('%')) {
    throw new ExecutableResolutionError(
      'EXECUTABLE_ARGUMENT_UNSAFE',
      `Argument ${JSON.stringify(argument)} contains "%", which cmd.exe expands even inside quotes; the launch is refused rather than silently altered.`,
    );
  }
  return `"${argument}"`;
}

/**
 * Build the cmd.exe `/c` payload for a shim.
 *
 * `/d` disables AutoRun, `/s` plus one outer quote pair gives the
 * documented "strip exactly the outer quotes" form, so a shim path with
 * spaces and non-ASCII characters survives intact.
 */
export function windowsShimPayload(target: string, args: string[]): string {
  const quoted = [target, ...args].map(quoteForCmdExe).join(' ');
  return `"${quoted}"`;
}

function resolveForPlatform(input: ResolveCommandInput): ResolvedInvocation {
  const platform = input.platform ?? process.platform;
  const windows = isWindows(platform);
  const env = input.env ?? process.env;
  const target = firstExisting(input, windows);
  const args = input.args ?? [];
  const ext = extensionOf(target);

  if (ext === '.cmd' || ext === '.bat') {
    if (!windows) {
      throw new ExecutableResolutionError(
        'EXECUTABLE_UNSUPPORTED_SCRIPT',
        `${target} is a Windows ${ext} shim; it cannot be executed on ${platform} and this resolver never routes it through WSL, bash or a shebang interpreter.`,
      );
    }
    const comspec = env.ComSpec ?? env.COMSPEC ?? 'cmd.exe';
    return {
      kind: ext === '.bat' ? 'windows-batch-shim' : 'windows-cmd-shim',
      file: comspec,
      args: ['/d', '/s', '/c', windowsShimPayload(target, args)],
      target,
    };
  }

  if (ext === '.ps1') {
    if (!windows) {
      throw new ExecutableResolutionError(
        'EXECUTABLE_UNSUPPORTED_SCRIPT',
        `${target} is a PowerShell script; running it on ${platform} would require an unproven PowerShell installation, so the launch is refused instead of being handed to a shell.`,
      );
    }
    const powershell = env.POWERSHELL_EXE ?? 'powershell.exe';
    return {
      kind: 'powershell-script',
      file: powershell,
      args: [
        '-NoLogo',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        target,
        ...args,
      ],
      target,
    };
  }

  return { kind: 'native', file: target, args: [...args], target };
}

/**
 * Resolve a command to a structured launch plan. Pure and total: it
 * either returns a plan or throws a typed resolution error.
 */
export function resolveCommand(input: ResolveCommandInput): ResolvedInvocation {
  if (typeof input.command !== 'string' || input.command.trim().length === 0) {
    throw new ExecutableResolutionError(
      'EXECUTABLE_NOT_FOUND',
      'A command name is required to resolve a launch plan.',
    );
  }
  return resolveForPlatform(input);
}

/** Test/diagnostic helper: list the candidates a resolution would try. */
export function resolutionCandidates(
  command: string,
  platform: ResolverPlatform,
  env: NodeJS.ProcessEnv,
): string[] {
  return pathCandidates({ command, platform, env }, isWindows(platform));
}
